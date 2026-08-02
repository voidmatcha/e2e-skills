#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Shared credential redaction patterns and the fail-closed residual gate.

DESIGN AND POLICY -- read this before "fixing" the aggressiveness back.

The gate does not parse values. Its whole question is a marker invariant:

    for every sensitivity keyword occurrence in POST-redaction text that is
    followed by an assignment-ish separator, the token immediately after that
    separator must be exactly the redaction marker; otherwise fail closed.

Three earlier passes had the gate re-extract the value and judge whether it
looked safe. That cannot converge. The gate's value extent had to mirror the
redactor's exactly: too narrow and a half-redacted line was certified clean (a
leak, e.g. `password=[REDACTED] hunter2`); too wide and the gate consumed past
a closing quote or a space and failed closed on genuine prose (an availability
bug). Every correction in one direction opened the other. The marker invariant
deletes value extent from the gate entirely, so the two sides no longer have to
agree about where a value ends.

What replaces "the gate is an independent keyword detector" -- it never was one,
because its keyword class is derived from the redactor's and so structurally
cannot catch a redactor keyword miss -- is a containment property:

    GATE_SEPARATOR_TOKENS is a superset of REDACTOR_SEPARATOR_TOKENS.

Any separator form the redactor does not rewrite is therefore still a form the
gate recognises, and an unrewritten value at a recognised separator fails
closed. That is the safe direction, and `scripts/ci/test-debugger-contracts.py`
asserts both the containment and the required separator floor.

THE POLICY THIS TRADES AWAY -- intended outcome, not a regression:
redaction is now aggressive. A sensitivity keyword followed by ANY
assignment-ish separator has its value replaced whether or not the value looks
secret. `credentials: 'include' is not a valid enum value` becomes
`credentials:'[REDACTED]' is not a valid enum value`, and
`const authorization = () => next()` becomes
`const authorization=[REDACTED] => next()`. Fidelity loss next to a sensitivity
keyword is recoverable -- the reader is looking at their own source and their
own report -- and a leak is not. Do not narrow this back to "only redact values
that look secret"; that reasoning produced all three previous bypasses.

That aggressiveness now reaches ONE LINE PAST the separator. A value can start
on the line after the keyword claims it -- a bare `password:` ending a line, or
`password: |` opening a YAML block -- so the extent claims the next content
line, clamped so it can never swallow the next credential site. Until it did,
a keyword at the end of a line got a marker minted out of an empty value, the
marker satisfied the gate, and the secret one line down shipped at exit 0. The
exact bound, and the residual it leaves, are at ASSIGNMENT_VALUE below.

The bar that still matters is AVAILABILITY: the readers must keep exiting 0 and
emitting output. Failing closed on genuine non-secret text is still a defect.
Redacting more of it is not.

Cost is measured rather than asserted. Every claim below that a pattern stays
linear on adversarial input is an executable one:
``scripts/ci/test-residual-redos-budget.py`` holds this module to an absolute
ceiling and a scaling budget over a table of inputs aimed at each quantifier.

The keyword-free CREDENTIAL_SHAPE_PATTERNS table (PEM, AKIA/ASIA, gh?_, xox*,
sk_live/test, AIza, JWT) is the one genuinely independent layer. It stays as a
second, orthogonal check that no keyword or separator list can shadow.

Each debugger skill installs on its own, so both skills ship a byte-identical
copy of this file. ``scripts/ci/test-debugger-contracts.py`` asserts the two
copies stay identical.
"""

from __future__ import annotations

import json
import re
from typing import Callable
from urllib.parse import urlsplit


REDACTED = "[REDACTED]"
DIAGNOSTIC_WITHHELD = (
    "artifact diagnostic withheld: the message carried a residual "
    "credential shape"
)

# A leading `\b` is useless in front of these keywords. Underscore is a word
# character in Python `re`, so `\btoken\b` never matches inside GITHUB_TOKEN,
# AUTH_TOKEN, or id_token, and `\bapi[-_ ]?key\b` never matches inside
# X_API_KEY -- yet env-var-style names are the most common way credentials
# reach stdout and stack traces. The negative lookbehind pins each match to the
# start of an identifier run while the prefix class still admits the `GITHUB_`,
# `X_`, and `id_` prefixes. Pinning the run start also stops the `*` from
# re-anchoring at every offset inside a long identifier, which keeps matching
# linear on adversarially long inputs.
KEYWORD_PREFIX = r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]*"

HEADER_KEYWORDS = (
    "authorization|proxy-authorization|cookie|set-cookie|"
    "x-api-key|api[-_ ]?key"
)
# Bare `pass` is deliberately in this list. It is what covers `passphrase=`,
# `passcode=`, `userPass=`, and the `user['pass']=` subscript form without an
# ever-growing spelling list, and the measured cost is nil: across the 2,444
# strings in every committed Playwright/Cypress artifact fixture in this
# repository it adds zero new redactions. The only text it touches is
# runner-summary prose such as `Passing:      2` or `passes=5`, which reaches
# the projection as integers under JSON keys, not as inline `key: value` text,
# because the inline redactor only ever rewrites string values. Under this
# module's policy losing a pass count to `Passing:[REDACTED]` is survivable;
# emitting a passphrase is not.
ASSIGNMENT_KEYWORDS = (
    "authorization|proxy-authorization|cookie|set-cookie|"
    "x-api-key|api[-_ ]?key|"
    "access[_-]?token|refresh[_-]?token|token|"
    "password|passwd|passphrase|passcode|pass|pwd|"
    "secret|client[_-]?secret|"
    "private[_-]?key|credentials?|signature"
)
# The gate must never anchor on a narrower keyword class than the redactor, or
# it certifies as clean exactly the assignments the redactor did not rewrite.
# Deriving it from the same string makes that drift unrepresentable instead of
# merely discouraged.
#
# Deliberately NOT folded in here: the transport-shaped fragments the readers
# carry in their own SENSITIVE_KEY_FRAGMENTS for structured keys (`body`,
# `payload`, `postdata`, `formdata`, `query`). Those are per-reader redaction
# policy, not credential shapes -- the Cypress redactor passes no extras, so
# anchoring the shared gate on them would fail closed on clean Cypress output
# that no redactor ever rewrites. Every fragment that names a credential is
# already in ASSIGNMENT_KEYWORDS or HEADER_KEYWORDS above. A reader may
# therefore redact MORE than the gate checks; it may never redact less.
RESIDUAL_ASSIGNMENT_KEYWORDS = ASSIGNMENT_KEYWORDS

# The gate's separator alphabet.
#
# The redactor's alphabet is DERIVED from this one below, so "the redactor
# understands a separator the gate does not" is unrepresentable rather than
# merely discouraged. Adding a separator here without teaching the redactor
# about it is the safe failure: the gate sees an unrewritten value and fails
# closed. The reverse is the leak this design exists to make impossible.
#
# THE CLOSURE RULE -- do not extend this list by intuition, extend the rule.
# A token belongs here iff it is VALUE-INTRODUCING: the name on its left
# stands for the operand on its right, in some language that reaches an E2E
# artifact or a CI log. The first spelling of this rule was "every ECMAScript
# punctuator that contains `=`, plus `->`, `:=`, `:`", and an audit found two
# whole classes sitting just outside it -- assignment operators from
# non-JavaScript languages, and Unicode renderings of the ASCII tokens. Both
# are now inside it, and the rule is spelled in three layers so a future
# reader can check exhaustiveness without re-deriving it:
#
#   LAYER 1 -- every ECMAScript punctuator containing `=` (23):
#     simple + compound assignment (16): += -= *= /= %= **= <<= >>=
#                                        >>>= &= |= ^= &&= ||= ??=
#     equality + relational        ( 6): == === != !== <= >=
#     arrow                        ( 1): =>
#
#   LAYER 2 -- value-introducing punctuators from the other languages that
#   reach artifacts, CI logs and config dumps (12). This is the class the
#   first rule missed twice over: `?=`, `//=` and `@=` do contain `=` but are
#   not ECMAScript punctuators, and `<-`, `<<-`, `->>`, `|>`, `~=` contain no
#   `=` at all, so "contains `=`" could never have reached them.
#     :          JSON, YAML, HTTP header, prose
#     ->         thin arrow, logs from other languages
#     :=         Go / Pascal / Python walrus / Make simple assignment
#     <-         Go channel receive, R and OCaml assignment
#     <<-  ->>   R super-assignment, both directions
#     ?=         Make conditional assignment
#     //=  @=    Python floor-division and matrix-multiplication assignment
#     =~   ~=    Perl / Ruby bind, Lua / Julia compare
#     |>         Elixir / F# / OCaml / JS-proposal pipeline
#
#   LAYER 3 -- Unicode. Two sub-layers, because they close differently:
#     3a. CHARACTER renderings, in SEPARATOR_CHARACTER_RENDERINGS below.
#         Every token is compiled character by character through that table,
#         so each ASCII separator character also matches its compatibility
#         and lookalike renderings. That closes `password=x` over
#         `password<U+FF1D>x`, `password:x` over `password<U+FF1A>x`, and --
#         because the closure is per character, not per token -- `password==x`
#         over `password<U+FF1D><U+FF1D>x` as well, without spelling one new
#         token. The mechanical statement is "every single Unicode character
#         whose NFKC normalisation is one of the separator characters", which
#         CI re-derives by sweeping the entire codepoint range.
#     3b. TOKEN renderings, listed in the tuple below. These are single
#         characters that render a MULTI-character ASCII token, so layer 3a
#         cannot reach them (U+2254, U+2255, U+2A75, U+2A76, U+2261, U+2260,
#         U+2264, U+2265, U+2192, U+21D2, U+2190, U+21D0, U+21A6).
#
# Enumeration, not normalisation. An NFKC pre-pass would have to run over
# every artifact string, would shift every offset the redactor splices on,
# and would rewrite unrelated CJK and ligature text on the way to stdout.
# Enumeration keeps ONE alphabet that the gate and the redactor share, which
# is the property the whole design rests on.
#
# Bare `>` and `<` are absent on purpose. A bare `>` as a separator would
# mangle every `<input type="password">` in a DOM dump; `=>`, `->`, `<=` and
# `>=` carry `>`/`<` next to an `=` or another operator character, so they
# cannot match a tag close. Bare `??`, `||`, `&&` and `?:` are absent for a
# different reason: they select BETWEEN values rather than introducing one,
# and wherever they carry a credential the governing `=` or `:` already
# claims the site (`const pw = env.PW ?? 'hunter2'` is redacted from the `=`).
# CSS-only `$=` stays out: its left side is an attribute name inside a
# selector, never a credential key, and `$` is a shell value sigil that would
# drag every `${VAR}` in a log into the lead-character guard for no closure.
GATE_SEPARATOR_TOKENS = (
    ">>>=",
    "<<=",
    ">>=",
    "**=",
    "??=",
    "||=",
    "&&=",
    "===",
    "!==",
    "<<-",
    "->>",
    "//=",
    "==",
    "!=",
    "<=",
    ">=",
    "=>",
    "->",
    ":=",
    "<-",
    "?=",
    "@=",
    "=~",
    "~=",
    "|>",
    "+=",
    "-=",
    "*=",
    "/=",
    "%=",
    "|=",
    "&=",
    "^=",
    "=",
    ":",
    # Layer 3b: one character carrying a multi-character ASCII token.
    "\u2254",  # COLON EQUALS                 reads as :=
    "\u2255",  # EQUALS COLON                 reads as =:
    "\u2a75",  # TWO CONSECUTIVE EQUALS SIGNS reads as ==
    "\u2a76",  # THREE CONSECUTIVE EQUALS     reads as ===
    "\u2261",  # IDENTICAL TO                 reads as ===
    "\u2260",  # NOT EQUAL TO                 reads as !=
    "\u2264",  # LESS-THAN OR EQUAL TO        reads as <=
    "\u2265",  # GREATER-THAN OR EQUAL TO     reads as >=
    "\u2192",  # RIGHTWARDS ARROW             reads as ->
    "\u21d2",  # RIGHTWARDS DOUBLE ARROW      reads as =>
    "\u2190",  # LEFTWARDS ARROW              reads as <-
    "\u21d0",  # LEFTWARDS DOUBLE ARROW       reads as <=
    "\u21a6",  # RIGHTWARDS ARROW FROM BAR    reads as |->
)
# Layer 3a of the closure rule. `_separator_group` compiles every token
# character by character through this table, so a rendering closes over every
# token that contains the character instead of only over the bare character.
#
# The NFKC half is mechanical: `scripts/ci/test-debugger-contracts.py` sweeps
# the whole Unicode codepoint range and fails if any character normalises into
# a separator character without appearing here. The curated half is the
# characters that do not normalise but read as the separator anyway -- the
# modifier letters U+A78A and U+A789, U+2236 RATIO, and the raised colons
# U+02D0 and U+02F8.
SEPARATOR_CHARACTER_RENDERINGS = {
    "=": "\uff1d\ufe66\u207c\u208c\ua78a",
    ":": "\uff1a\ufe55\ufe13\u2236\ua789\u02d0\u02f8",
    "<": "\uff1c\ufe64",
    ">": "\uff1e\ufe65",
    "-": "\uff0d\ufe63",
    "+": "\uff0b\ufe62\u207a\u208a\ufb29",
    "*": "\uff0a\ufe61",
    "/": "\uff0f",
    "%": "\uff05\ufe6a",
    "^": "\uff3e",
    "&": "\uff06\ufe60",
    "|": "\uff5c",
    "!": "\uff01\ufe57\ufe15",
    "?": "\uff1f\ufe56\ufe16",
    "@": "\uff20\ufe6b",
    "~": "\uff5e",
}
# Separators the redactor deliberately declines to rewrite. Anything listed
# here still reaches the gate and therefore still fails closed: skipping a
# rewrite is survivable, skipping a check is not. Empty today; it exists so the
# redactor alphabet stays a derivation rather than a second hand-maintained
# list that can drift the unsafe way.
REDACTOR_SEPARATOR_EXCLUSIONS: tuple[str, ...] = ()
REDACTOR_SEPARATOR_TOKENS = tuple(
    token
    for token in GATE_SEPARATOR_TOKENS
    if token not in REDACTOR_SEPARATOR_EXCLUSIONS
)

# `key` window, key tail, and the gap between them and the separator -- all
# three shared verbatim by the redactor and the gate.
#
# Window: one identifier run, optionally plus one space-separated second run so
# the spaced header spelling `api key=` stays a single key. The lookbehind pins
# the window to the start of an identifier run, which is what keeps matching
# linear: without it the engine re-anchors at every offset inside a long
# identifier.
#
# THE SECOND RUN MUST BEGIN WITH A CORE IDENTIFIER CHARACTER. `-` is the only
# character that belongs to both the key alphabet and the operator alphabet, so
# an unrestricted second run absorbed the head of an operator: `password -=
# secret` parsed as key `password -` + separator `=`, and
# `key_names_credential` then rejected `password -` because the run against the
# separator was `-` rather than a keyword. That was a SILENT rejection, not a
# failed match -- the regex had already succeeded, so it never backtracked to
# the `password` + `-=` reading the way `password -> secret` does. Requiring
# the run to START with `[A-Za-z0-9_]` makes an operator head unabsorbable
# while keeping `api key=` and `api key-v2=` intact. The run is deliberately
# NOT also anchored to end on `[A-Za-z0-9_]`: a trailing hyphen changes nothing
# (`password x-= v` assigns to `x`, and the keyword test rejects that window
# either way) and the `[A-Za-z0-9_-]*[A-Za-z0-9_]` spelling needed to express
# it costs a backtrack per attempt on long space-separated input.
#
# Gap: whitespace, optionally with ONE stray hyphen that is itself surrounded
# by whitespace. Every token in the separator alphabet is contiguous, so a
# hyphen with whitespace on both sides cannot be the head of one; it is loose
# text sitting between the key and the separator, and `password - = secret` is
# the form that exploits it. The trailing `\s+` is mandatory precisely so
# `<!-- password --> value` keeps its comment marker: there the hyphens are
# adjacent, so the gap declines them and no site is found. `??` (lazy) means
# the empty gap is always tried first, which is what keeps `password -= secret`
# matching the `-=` token rather than splitting into a `-` in the gap plus a
# bare `=`.
#
# SEPARATOR_GUARD sits BEFORE the optional hyphen, not after it, and that
# placement is the whole performance story. Every separator token and the stray
# hyphen alike begin with a character in this class, so one character-class
# test rejects a gap that is followed by ordinary text -- and it rejects it
# without ever attempting the hyphen branch. Text like `api key api key ...`
# therefore costs exactly what it cost before the hyphen was admitted. The
# second copy of the guard is inside the optional group, where it is only ever
# reached on input that really did carry a stray hyphen.
#
# Key tail: an assignment can close a subscript or a quoted key before the
# separator (`user[password]=`, `headers["authorization"]=`, `user['pass']=`).
# Eight closers, not two. Two parsed `obj[cfg["password"]]=` -- three
# closers -- as a non-site, and all three readers emitted the value. Eight
# covers four levels of subscript nesting, and the class now also holds `)`,
# `}` and a backtick so `get("password")=`, `${password}=` and
# `` cfg[`password`]= `` are sites too. It stays a bounded repetition of a
# closer-only class, so the site regex keeps its linear cost, and the class
# still holds ONLY closers, so `[data-testid="password-input"]` still finds
# no separator after `password`.
KEY_RUN = (
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]+"
    r"(?:[ ][A-Za-z0-9_][A-Za-z0-9_-]*)?"
)
KEY_TAIL = r"[\"'\]\)\}`]{0,8}"
# The lead-character guard is DERIVED from the alphabet, so a token whose
# first character is not in the guard class can never be silently unreachable.
SEPARATOR_LEAD_CHARACTERS = "".join(
    sorted(
        {
            character
            for token in GATE_SEPARATOR_TOKENS
            for character in (
                token[0] + SEPARATOR_CHARACTER_RENDERINGS.get(token[0], "")
            )
        }
    )
)
SEPARATOR_GUARD = r"(?=[" + re.escape(SEPARATOR_LEAD_CHARACTERS) + r"])"
KEY_GAP = r"\s*" + SEPARATOR_GUARD + r"(?:-\s+" + SEPARATOR_GUARD + r")??"


def _character_class(character: str) -> str:
    """One separator character, closed over its Unicode renderings."""
    renderings = SEPARATOR_CHARACTER_RENDERINGS.get(character, "")
    if not renderings:
        return re.escape(character)
    return "[" + re.escape(character + renderings) + "]"



def _separator_group(tokens: tuple[str, ...]) -> str:
    """Compile a separator alternation, longest token first.

    Longest-first is a correctness requirement, not a style choice. Leftmost
    alternation would otherwise take `=` out of `===`, leave `==` standing as
    the start of the value, and split `password === secret` into a key the
    redactor rewrote and a value it did not -- which is exactly how
    `password=[REDACTED] hunter2LiveProdPassword` used to reach stdout.

    The performance guard that used to lead this group now lives in KEY_GAP,
    which is the last position both the plain and the stray-hyphen spelling
    pass through. It has no effect on the language matched either way: every
    separator token starts with a character in that class.
    """
    ordered = sorted(tokens, key=lambda token: (-len(token), token))
    alternatives = [
        "".join(_character_class(character) for character in token)
        for token in ordered
    ]
    return r"(?P<sep>" + "|".join(alternatives) + r")"


def _assignment_site(tokens: tuple[str, ...]) -> str:
    """`key`, optional closing tail, gap, separator -- and no value."""
    return (
        r"(?P<key>" + KEY_RUN + r")(?P<kq>" + KEY_TAIL + r")" + KEY_GAP
        + _separator_group(tokens)
    )


def _quoted_value(group: str) -> str:
    return rf"(?P<{group}>[\"'])[^\"'\r\n]*(?P={group})"


def _keyword_alternation(keywords: str) -> re.Pattern[str]:
    return re.compile(r"(?i)(?:" + keywords + r")")


def key_names_credential(key: str, keywords: re.Pattern[str]) -> bool:
    """True when a sensitivity keyword sits against the separator.

    The keyword may be any SUBSTRING of the identifier adjacent to the
    separator, which is what covers `passwordConfirm=`, `api_key_v2=` and
    `AUTH_SECRET=`. Whole-token and prefix-run matching missed all three.

    Only identifier characters may sit between the keyword and the separator.
    That is what stops the two-word window -- which exists solely so `api key=`
    stays one key -- from reading `token expired:` as a credential site.
    """
    tail_start = key.rfind(" ") + 1
    return any(match.end() >= tail_start for match in keywords.finditer(key))


def build_header_pattern() -> re.Pattern[str]:
    """Match `Cookie: v`, `"cookie":"v"`, and `X_API_KEY: v` header forms.

    The optional key-side quote is what lets the quoted-JSON header form
    (`{"cookie":"sid=..."}`) match at all: a bare `\\s*:\\s*` cannot cross the
    quote that closes the key. This pattern runs before the assignment pattern
    and differs from it only by taking the whole rest of the line as the value,
    which is what keeps a multi-pair `Cookie:` header from surviving in part.
    """
    return re.compile(
        r"(?i)(?P<key>" + KEYWORD_PREFIX + r"(?:" + HEADER_KEYWORDS + r"))"
        r"(?P<kq>" + KEY_TAIL + r")\s*:\s*(?!\[REDACTED\])"
        r"(?:" + _quoted_value("vq") + r"|[^\r\n]+)"
    )


def header_substitution(match: re.Match[str]) -> str:
    quote = match.group("vq") or ""
    return f"{match.group('key')}{match.group('kq')}: {quote}{REDACTED}{quote}"


REDACTOR_ASSIGNMENT_SITE = re.compile(
    r"(?i)" + _assignment_site(REDACTOR_SEPARATOR_TOKENS)
)

# Value extents, matched separately at the offset just past a separator that a
# keyword actually claimed. They are never applied to a site the keyword test
# rejected, which is the whole reason redaction scans sites instead of running
# one `re.sub` over `site + value`: a single pattern that carries the value has
# to CONSUME that value even when it declines to rewrite it, so the harmless
# `TypeError:` at the head of a line swallowed the rest of it and hid the
# `credentials:` site sitting behind it.
#
# ONE extent for every separator. There used to be two: `:` ran to the end of
# the line or the next `,`/`;`, and everything else stopped at the first space
# so that `TOKEN=x PATH=/usr/bin` kept its PATH. That second, narrower extent
# was a fidelity compromise from the era when redaction tried to touch as
# little as possible, and under the current policy it is simply a leak:
#
#     PASSWORD=correct horse battery staple
#         -> PASSWORD=[REDACTED] horse battery staple
#     AUTHORIZATION=Token hunter2LiveProdPassword
#         -> AUTHORIZATION=[REDACTED] hunter2LiveProdPassword
#
# Multi-word secrets -- passphrases, and `<scheme> <credential>` header values
# -- survived every whitespace-terminated separator while the colon form of the
# same text was fully closed. Losing an unrelated `PATH=...` to the same line's
# `TOKEN=` is the documented cost, and it is recoverable; the passphrase is
# not. Do not reintroduce the narrow extent.
#
# THE CROSS-LINE EXTENT, and how far it is allowed to run. This used to say
# "the extent refuses to cross a newline", and that sentence was the sharpest
# leak left in the module. A keyword ending a line got a marker minted out of
# an empty value, the marker satisfied the gate, and the secret on the next
# line was emitted at exit 0:
#
#     credentials:
#       password:
#         hunter2LiveProdPassword     <- emitted, exit 0
#
# Declining to rewrite those sites instead is not an option: the gate would
# then fail closed on every `password:` that ends a line, and availability is
# the hard bar. So the value may cross a newline, under two bounds:
#
#   ONE content line. Blank and whitespace-only lines in between are skipped,
#   then exactly one line of content is claimed. A bare continuation line is
#   the real shape in YAML and in `key:`-per-line config dumps, and a YAML
#   block-scalar header (`|`, `>`, with the usual chomping and indentation
#   indicators) counts as no value at all, so `password: |` continues onto the
#   next line the same way a bare `password:` does. Prose wrapping and stack
#   frames are NOT this shape, and an indentation-following extent would eat a
#   whole stack trace under one accidental `credentials:` -- the fidelity cost
#   we are not willing to pay. The residual is stated rather than hidden: the
#   SECOND and later lines of a multi-line block scalar stay outside the
#   extent, and a value that starts on the separator's own line and wraps is
#   claimed only as far as that line.
#
#   NEVER ACROSS THE NEXT CREDENTIAL SITE. `redact_assignments` clamps the
#   continuation at the start of the next site it will rewrite. Without the
#   clamp, `credentials:` would swallow the `password:` line whole, that site
#   would never be visited, and the secret one line further down would be
#   emitted -- the same leak one line lower. With it, `credentials:` stops,
#   `password:` claims its own continuation, and the secret is gone.
#
# The continuation is redacted in place rather than collapsed: the newline and
# the indentation are re-emitted and the content becomes a second marker, so
# `password:\n  hunter2` reads back as `password:[REDACTED]\n  [REDACTED]`.
# Keeping the marker on the separator's own line is what keeps the gate --
# which requires the marker immediately after the separator, on that line --
# satisfied, and keeping the newline is what stops line numbers in a stack
# trace from shifting under the reader.
#
# THE MARKER ALTERNATIVE IS WHAT KEEPS REDACTION A FIXED POINT, which both
# readers require: they run the redactor twice and refuse to emit anything if
# the second pass moves. On its own the wide body is already stable, because
# it stops exactly where the previous pass stopped -- but the readers run
# QUERY_ASSIGNMENT after the redactor, and that pass rewrites `?k=v` pairs
# whose value class swallows the `,` this extent had stopped at:
#
#     ?access_token=x, browser_click, and ...
#     pass 1 -> ?access_token=[REDACTED] browser_click, and ... (comma eaten)
#     pass 2 -> ?access_token=[REDACTED] and ...                (moved again)
#
# A value that is ALREADY the marker therefore ends at the marker. The
# lookahead stops that from becoming a smuggling channel: artifact text
# spelling `password=[REDACTED]hunter2` finds no boundary after the marker,
# falls through to the wide body, and is closed. `password=[REDACTED] hunter2`
# does survive -- but that is pre-existing and deliberate, the reading of the
# marker invariant that is identical to `TOKEN=[REDACTED] PATH=/usr/bin`,
# which the gate has always certified clean.
ASSIGNMENT_VALUE = re.compile(
    r"[^\S\r\n]*(?:"
    + _quoted_value("vq")
    + r"|" + re.escape(REDACTED) + r"(?![^\s,;])"
    + r"|(?P<blk>[|>][+-]?[0-9]?[+-]?[^\S\r\n]*)?"
    + r"(?P<nl>(?:\r?\n[^\S\r\n]*)+)(?P<cont>\S[^\r\n]*)"
    + r"|[^\r\n,;]+"
    + r")?"
)


def build_assignment_redactor(extra_keywords: str = "") -> Callable[[str], str]:
    """Return a redactor for `key<separator>value` credential assignments.

    The returned callable and `assignment_marker_violation` walk the SAME site
    regex and apply the SAME keyword test, differing only in separator alphabet
    -- and that difference is a containment, checked in CI. Nothing about the
    value extents below has to agree with anything on the gate side, because
    the gate never looks at a value.
    """
    keywords = ASSIGNMENT_KEYWORDS
    if extra_keywords:
        keywords = f"{keywords}|{extra_keywords}"
    keyword_test = _keyword_alternation(keywords)

    def redact_assignments(text: str) -> str:
        # Materialised rather than streamed because the cross-line extent has
        # to know where the NEXT site it will rewrite begins, so that a bare
        # `credentials:` can never swallow the `password:` line under it.
        sites = [
            site
            for site in REDACTOR_ASSIGNMENT_SITE.finditer(text)
            if key_names_credential(site.group("key"), keyword_test)
        ]
        pieces: list[str] = []
        cursor = 0
        for index, site in enumerate(sites):
            if site.start() < cursor:
                # Inside a value an earlier site already replaced.
                continue
            value = ASSIGNMENT_VALUE.match(text, site.end())
            quote = (value.group("vq") or "") if value is not None else ""
            head = (
                f"{site.group('key')}{site.group('kq')}{site.group('sep')}"
                f"{quote}{REDACTED}{quote}"
            )
            pieces.append(text[cursor:site.start()])
            if value is None:
                pieces.append(head)
                cursor = site.end()
                continue
            if value.group("nl") is None:
                pieces.append(head)
                cursor = value.end()
                continue
            next_site = (
                sites[index + 1].start()
                if index + 1 < len(sites)
                else len(text)
            )
            body_start = value.start("cont")
            body_end = min(value.end("cont"), next_site)
            if body_end <= body_start:
                # The continuation line opens the next site we will rewrite.
                # Leave it to that site; claiming it would hide it.
                pieces.append(head)
                cursor = value.start("nl")
            else:
                pieces.append(f"{head}{value.group('nl')}{REDACTED}")
                cursor = body_end
        pieces.append(text[cursor:])
        return "".join(pieces)

    return redact_assignments


# Keyword-free credential shapes. Every keyword-anchored detector inherits the
# redactor's blind spots by construction, so a bare PEM block, AWS key, Slack
# token, JWT, GitHub token, Stripe key, or Google API key sitting in an error
# message used to pass through untouched and undetected. These patterns are
# deliberately prefix-anchored rather than entropy-based: ordinary selectors,
# stack frames, file paths, UUIDs, and base64 screenshots must keep flowing.
CREDENTIAL_SHAPE_PATTERNS = (
    # Complete PEM / OpenSSH / PGP private key block.
    re.compile(
        r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY(?: BLOCK)?-----"
        r"[\s\S]*?"
        r"-----END(?: [A-Z0-9]+)* PRIVATE KEY(?: BLOCK)?-----"
    ),
    # Key block whose END marker was lost to truncation: drop the remainder.
    re.compile(
        r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY(?: BLOCK)?-----[\s\S]*"
    ),
    # AWS access key id (AKIA/ASIA/AROA/... + 16 uppercase-or-digit chars).
    re.compile(
        r"(?<![A-Za-z0-9])"
        r"(?:A3T[A-Z0-9]|ABIA|ACCA|AGPA|AIDA|AIPA|AKIA|ANPA|ANVA|APKA|AROA|"
        r"ASCA|ASIA)"
        r"[A-Z0-9]{16}"
        r"(?![A-Za-z0-9])"
    ),
    # Slack bot/user/app tokens.
    re.compile(r"(?<![A-Za-z0-9])xox[a-z]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])xapp-[0-9]-[A-Za-z0-9-]{10,}"),
    # GitHub personal access / OAuth / server / refresh tokens.
    re.compile(
        r"(?<![A-Za-z0-9_])"
        r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"
    ),
    # Stripe secret and restricted keys (publishable pk_ keys are not secret).
    re.compile(
        r"(?<![A-Za-z0-9_])(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{10,}"
    ),
    # Google API key.
    re.compile(
        r"(?<![A-Za-z0-9_-])AIza[0-9A-Za-z_-]{30,}(?![A-Za-z0-9_-])"
    ),
    # JSON Web Token. `eyJ` is base64 for `{"`, so requiring it plus three
    # dot-separated segments keeps ordinary base64 blobs out of scope.
    re.compile(
        r"(?<![A-Za-z0-9_-])"
        r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{4,}"
        r"(?![A-Za-z0-9_-])"
    ),
)


def redact_credential_shapes(text: str) -> str:
    for pattern in CREDENTIAL_SHAPE_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def text_has_credential_shape(text: str) -> bool:
    return any(pattern.search(text) for pattern in CREDENTIAL_SHAPE_PATTERNS)


SAFE_CREDENTIAL_VALUE = re.compile(
    r"(?ix)^(?:"
    r"\[redacted\]|\[masked\]|<[^<>]+>|\$[a-z_][a-z0-9_]*|"
    r"\$\{[a-z_][a-z0-9_]*\}|"
    r"\{\{[a-z_][a-z0-9_]*\}\}|"
    r"your[-_ ]?[a-z0-9_-]+|example|placeholder|masked|redacted|"
    r"x+|\*+"
    r")$"
)
SAFE_AUTH_PROSE = {
    "authentication",
    "authorization",
    "credential",
    "credentials",
    "header",
    "scheme",
    "token",
    "value",
}
RESIDUAL_SENSITIVE_KEYS = {
    "apikey",
    "authorization",
    "clientsecret",
    "cookie",
    "password",
    "passwd",
    "proxyauthorization",
    "secret",
    "setcookie",
    "token",
    "accesstoken",
    "refreshtoken",
    "xapikey",
}

# The marker invariant. The gate locates assignment SITES and never captures a
# value, so nothing here has to agree with how wide the redactor's value is.
RESIDUAL_ASSIGNMENT_SITE = re.compile(
    r"(?i)" + _assignment_site(GATE_SEPARATOR_TOKENS)
)
RESIDUAL_ASSIGNMENT_KEYWORD_TEST = _keyword_alternation(
    RESIDUAL_ASSIGNMENT_KEYWORDS
)
# What must follow a separator that follows a keyword: the marker, and nothing
# else. The optional quote is the one `build_assignment_redactor` preserves
# around a quoted value; the horizontal whitespace is the single space
# `header_substitution` re-inserts. Neither can carry a secret.
RESIDUAL_MARKER_AFTER_SEPARATOR = re.compile(
    r"[^\S\r\n]*[\"']?" + re.escape(REDACTED)
)

# HTTP authentication schemes whose credential is the next whitespace-separated
# word. Both readers build their own `AUTH_SCHEME` redaction pattern from this
# same string, so the gate can never recognise a scheme that neither redactor
# rewrites (which would fail an ordinary line closed) and no reader can rewrite
# a scheme the gate does not check.
#
# `negotiate` (RFC 4559) is here because it costs nothing: zero matches across
# the 78,924 unique strings in this repository's artifact sweep.
#
# `token` and `digest` are DELIBERATELY ABSENT, and this is the one place in
# this module where "redact more" loses. They are real IANA schemes, but as
# bare words followed by a word they are ordinary English: measured over the
# same sweep, `token <word>` matches 210 strings and `digest <word>` matches
# 154, none of them credentials (`token attestation`, `Digest every ...`).
# Case-sensitivity does not rescue them (5 and 4). Nothing is lost by leaving
# them out: `Authorization: Token secret` is already taken by the header
# pattern, which claims the whole rest of the line, and `AUTHORIZATION=Token
# secret` by the assignment redactor now that its value extent runs to the end
# of the line. What stays uncovered is a bare `Token secret` with no
# authorization key anywhere on the line -- narrower than the prose these two
# would eat.
AUTH_SCHEME_NAMES = "bearer|basic|negotiate"
RESIDUAL_AUTH_VALUE = re.compile(
    r"(?i)\b(?:" + AUTH_SCHEME_NAMES + r")\s+(?P<value>[^\s\"',;}]+)"
)
RESIDUAL_URL = re.compile(r"https?://[^\s\"'<>]+")
RESIDUAL_QUERY_VALUE = re.compile(r"[?&][^=\s&#]+\s*=\s*(?P<value>[^&#\s\"']*)")


PEELABLE_TRAILING = "}]),;:.'\" \t"


def _candidate_is_safe(candidate: str, *, auth_scheme: bool) -> bool:
    if not candidate:
        return True
    if SAFE_CREDENTIAL_VALUE.fullmatch(candidate):
        return True
    return auth_scheme and candidate.lower() in SAFE_AUTH_PROSE


def residual_value_is_safe(value: str, *, auth_scheme: bool = False) -> bool:
    """Judge a value the URL, auth-scheme, and structured checks lifted out.

    The assignment gate no longer calls this: it asks about a marker, not about
    a value. What is left here parses values whose extent is fixed by a grammar
    the redactor does not choose -- URL userinfo, URL query parameters, the
    token after a `Bearer`/`Basic` scheme, and JSON object members -- so there
    is no redactor value extent for it to mirror.
    """
    candidate = value.strip().strip("'\"").strip()
    # A capture lifted out of prose or JSON drags along the punctuation that
    # closed the enclosing construct (`'<YOUR_API_KEY>' }`), which stops a
    # placeholder from being recognised as one. Peel that punctuation, but test
    # for safety before every peel: `[REDACTED]` ends in `]` and must never be
    # peeled down to `[REDACTED`. `>` is never peeled either -- it terminates
    # the `<TOKEN>` placeholder form.
    # One character per pass: peeling the whole trailing run at once would take
    # `[REDACTED]}` down to `[REDACTED` and call a correctly redacted value a
    # leak.
    for _ in range(8):
        if _candidate_is_safe(candidate, auth_scheme=auth_scheme):
            return True
        if not candidate or candidate[-1] not in PEELABLE_TRAILING:
            return False
        candidate = candidate[:-1].strip()
    return _candidate_is_safe(candidate, auth_scheme=auth_scheme)


def normalized_residual_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower()) if isinstance(value, str) else ""


def structured_residual_credential(value: object) -> bool:
    if isinstance(value, dict):
        header_name = normalized_residual_key(value.get("name"))
        header_value = value.get("value")
        if (
            header_name in RESIDUAL_SENSITIVE_KEYS
            and isinstance(header_value, str)
            and not residual_value_is_safe(header_value)
        ):
            return True
        for key, item in value.items():
            if (
                normalized_residual_key(key) in RESIDUAL_SENSITIVE_KEYS
                and isinstance(item, str)
                and not residual_value_is_safe(item)
            ):
                return True
            if structured_residual_credential(item):
                return True
    elif isinstance(value, list):
        return any(structured_residual_credential(item) for item in value)
    return False


def assignment_marker_violation(value: str) -> bool:
    """The marker invariant, evaluated over post-redaction text."""
    for match in RESIDUAL_ASSIGNMENT_SITE.finditer(value):
        if not key_names_credential(
            match.group("key"), RESIDUAL_ASSIGNMENT_KEYWORD_TEST
        ):
            continue
        if RESIDUAL_MARKER_AFTER_SEPARATOR.match(value, match.end()) is None:
            return True
    return False


def string_has_residual_credential(value: str) -> bool:
    if text_has_credential_shape(value):
        return True
    if assignment_marker_violation(value):
        return True

    for match in RESIDUAL_AUTH_VALUE.finditer(value):
        if not residual_value_is_safe(match.group("value"), auth_scheme=True):
            return True

    for match in RESIDUAL_URL.finditer(value):
        raw_url = match.group(0).rstrip(".,;:)}")
        try:
            parts = urlsplit(raw_url)
        except ValueError:
            return True
        if parts.username is not None or parts.password is not None:
            userinfo = parts.netloc.rsplit("@", 1)[0]
            if not all(
                residual_value_is_safe(component)
                for component in userinfo.split(":", 1)
            ):
                return True
        for query_match in RESIDUAL_QUERY_VALUE.finditer(f"?{parts.query}"):
            if not residual_value_is_safe(query_match.group("value")):
                return True
    return False


def structure_has_residual_credential(value: object) -> bool:
    """Reject credential-shaped values left anywhere in an emitted structure."""
    if structured_residual_credential(value):
        return True

    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            stack.extend(current.keys())
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        elif isinstance(current, str) and string_has_residual_credential(current):
            return True
    return False


def has_residual_credential(payload: str) -> bool:
    """Independently reject credential-shaped values left in emitted JSON."""
    try:
        structured = json.loads(payload)
    except (json.JSONDecodeError, RecursionError):
        return string_has_residual_credential(payload)
    return structure_has_residual_credential(structured)


def sanitize_diagnostic(message: object, redact: Callable[[str], str]) -> str:
    """Make an error message safe to write to stderr.

    Diagnostics leave through `parser.error`, which never passes through the
    emission-path gate. Artifact-controlled text reaching that branch has to be
    redacted here and then withheld outright if anything credential-shaped
    survives.
    """
    text = redact(str(message))
    if string_has_residual_credential(text):
        return DIAGNOSTIC_WITHHELD
    return text
