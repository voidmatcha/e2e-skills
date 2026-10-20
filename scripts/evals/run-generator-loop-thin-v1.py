#!/usr/bin/env python3
"""DEV-only autoresearch loop over the thin rules layer. Apache-2.0.

The edited object is exactly one file, a copy of THIN-RULES.md, changed by one checklist
line per iteration. A researcher command (default: a Claude subagent run by the owner,
never Codex) proposes; deterministic code stages, runs, scores and decides.

Imports of the shared machinery are lazy. Offline commands never configure Docker, call
a model, open an evaluation task, inspect processes or create a freeze.
"""
import argparse
import ast
from collections import Counter, defaultdict
import contextlib
import difflib
from fractions import Fraction
import hashlib
import importlib.util
import json
from math import ceil, comb, exp, isfinite, log
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import types

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
ID = "generator-loop-thin-v1"
BENCH = ROOT / "benchmarks" / ID
LAYER_V0 = ROOT / "benchmarks/generator-thin-layer-v1/THIN-RULES.md"
THIN_EVAL = ROOT / "benchmarks/generator-thin-eval-v1"
THIN_EVAL_PROTOCOL, THIN_EVAL_FREEZE = THIN_EVAL / "protocol.json", THIN_EVAL / "freeze.json"
V3_PROTOCOL = ROOT / "benchmarks/generator-multimodel-v3-codex/protocol.json"
REFERENCE_DIR = ROOT / "skills/playwright-test-generator"
REFERENCE_FILES = ("code-rules.md", "best-practices.md", "scenario-design.md")

ARM_A = "official-generator"
PROBE_ARM = "loop-probe"
ARM_D = "official+thin-rules"
D_LINE = "Read and follow /work/skill/thin-rules/SKILL.md; pass this instruction to the generating child."
LAYER_TARGET = "/work/skill/thin-rules/SKILL.md"
LAYER_H1 = "# Playwright thin rules\n\n"
RULE_PREFIX = "- [ ] "

DEV_SYNTH = ("v2-11", "v3-08", "v2-18")
# Owner decision 2026-10-15: the dev tasks are the synthetic dev split only at first. The Zeppelin dev tasks are an opt-in
# list (prepare --include-zeppelin) because the shared external proxy leaves the F3 stale-server hazard unrepaired there.
DEV_OSS = ("zep-sidebar", "zep-note-rename")
DEV = DEV_SYNTH
OSS_ACTIVE = ()


def use_zeppelin(include):
    """Select the task list for this process: synthetic only (default) or synthetic plus the opt-in Zeppelin dev tasks."""
    global DEV, OSS_ACTIVE
    DEV = DEV_SYNTH + (DEV_OSS if include else ())
    OSS_ACTIVE = DEV_OSS if include else ()


def batch_cells():
    """Cells in one batch: every active dev task, two repetitions each."""
    return 2 * len(DEV)
# Tasks used by thin-eval-v1, the Zeppelin evaluation pair and the sealed vault: never touched.
FORBIDDEN_TASKS = ("v2-06", "v2-22", "v2-23", "v3-04", "v3-06", "v3-09",
                   "zep-about-modal", "zep-home-links", "sealed-eval")
ADOPTIONS = {"ADOPT_QUALITY", "ADOPT_COST"}
NON_ADOPTIONS = {"REJECT", "NOT_APPLIED", "NO_CANDIDATE", "REJECT_ON_CONFIRMATION"}

SEED = 20261017
MAX_ITERATIONS = 6
MAX_CONSECUTIVE_NON_ADOPTIONS = 2
MAX_DRAWS = 2
RESEARCHER_DRAW_BUDGET = 12
LAYER_MAX_BYTES = 2400
LAYER_HARD_CEILING = 2500  # thin-eval's own hard limit; the loop stays below it
LAYER_MAX_LINE = 260
LAYER_MAX_GROWTH = 250
LAYER_MAX_RULES = 12
LAYER_MIN_RULE_BYTES = 40
LAYER_READ_MIN = 0.9
SLOW_S, MAX_SLOW_CELLS = 1200, 1
FIDELITY_OFFICIAL = "official-tool"  # thin-eval's arm A/D process-fidelity class: the official generator surface was used
# Second-review F4: one cell moves the 3-task mean by .167, so a +.10 screening delta is a single net cell. Adoption therefore
# also needs no per-task regression in the stage, and for the quality path a pooled net gain over screening plus confirmation.
QUALITY_POOLED_MIN_CELLS = 3
FIDELITY_MIN_RATE = 1.0  # official-tool share required of every cell of a D-v0 batch at entry and of both batches of every pair
# Second-review F3: a void batch is never silently lost. Its scheduled cells count toward the budget and one bounded, recorded
# retry per stage (two per campaign) is allowed only for an infrastructure void, before anything was scored or analyzed.
MAX_STAGE_RETRIES, MAX_CAMPAIGN_RETRIES = 1, 2
QUALITY_DELTA, TOKEN_GROWTH_CAP, COST_REDUCTION = 0.10, 0.10, 0.15
HEADROOM_SURVIVAL, HEADROOM_KILL = 0.95, 0.95
FAIL_KILL_BELOW = 0.8
GENERIC_MIN_COUNT = 3
PACKET_MAX_FAILURES, PACKET_SKELETON_CELLS, PACKET_SKELETON_CHARS = 8, 3, 2500
TASK_TIMEOUT_S = 1500
GUARD_KEYS = ("clean_all_three_rate", "effective_kill_all_cells", "effective_kill_clean_cells",
              "scanner_p0_total", "scanner_p1p2_total")
# strict is the audit's A1 rule (no tolerance). noise-tolerant is an owner-decision proposal sized to one
# cell of clean-rate noise, a half-cell of kill noise and about one standard deviation of scanner totals.
DEFAULT_GUARD_PROFILE = "strict"  # owner decision 2026-10-15
GUARD_PROFILES = {
    "strict": dict(clean_all_three_rate=0.0, effective_kill_all_cells=0.0, effective_kill_clean_cells=0.0,
                   scanner_p0_total=0, scanner_p1p2_total=0),
    "noise-tolerant": dict(clean_all_three_rate=0.10, effective_kill_all_cells=0.05, effective_kill_clean_cells=0.05,
                           scanner_p0_total=1, scanner_p1p2_total=3),
}
SELECTION_RULE = "outcome-blind-ad-v1"
SELECTION_MIN_A_CELLS = 12
SELECTION_MIN_D_CELLS = 12
STAGES = ("baseline", "screening", "confirmation")
ALLOWED_REVIEWER_FAMILIES = ("claude",)
GRADER_WORDS = re.compile(r"(?i)refactor|restyl|renam|re-?skin|markup|perturb|grader|scorer|mutant|mutation|held-?out|benchmark|\bevals?\b|\bevaluations?\b"
                          r"|\boracles?\b|\brubrics?\b|\bscor(?:e[sd]?|ing)\b|\bgrad(?:e[sd]?|ing)\b|\bhidden tests?\b|\breference (?:spec|solution)s?\b"
                          r"|\bfaults?\b|\binjected\b|\bkill[ -]?rates?\b|\bsurvival\b|\bpre-?registered\b|\bcalibrat\w*")
MACHINERY = None
METRICS = None


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    """Exclusive outputs: interrupted work is evidence, never silently replaced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False, sort_keys=True)
        handle.write("\n")


def write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        handle.write(text)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha_text(text):
    return hashlib.sha256(text.encode()).hexdigest()


def tree(path):
    path = Path(path)
    if not path.is_dir() or path.is_symlink():
        raise ValueError("missing or linked input tree")
    result = {}
    for f in sorted(path.rglob("*")):
        if f.is_symlink():
            raise ValueError("linked input refused")
        if f.is_file() and not {"__pycache__", "evals"}.intersection(f.relative_to(path).parts):
            result[f.relative_to(path).as_posix()] = sha(f)
    if not result:
        raise ValueError("empty input tree")
    return result


def assert_dev(case):
    if case not in DEV or case in FORBIDDEN_TASKS:
        raise ValueError("task outside the DEV allowlist")


assert not set(DEV_SYNTH + DEV_OSS) & set(FORBIDDEN_TASKS)


# ------------------------------------------------------------------ the edited object: one rules file

def layer_header(v0_text):
    """The frozen frontmatter plus H1: everything up to and including the heading."""
    index = v0_text.find(LAYER_H1)
    if index < 0 or not v0_text.startswith("---\n"):
        raise ValueError("baseline layer lacks frontmatter and the frozen heading")
    return v0_text[:index + len(LAYER_H1)]


def parse_layer(text, header):
    """Return the checklist lines of a grammar-valid layer; raise on any other shape."""
    if not isinstance(text, str) or not text.isascii():
        raise ValueError("layer must be ASCII text")
    if "```" in text or any(ord(ch) < 32 and ch != "\n" or ord(ch) == 127 for ch in text):
        raise ValueError("layer must not contain control characters, tabs, carriage returns or code fences")
    if not text.startswith(header):
        raise ValueError("frontmatter and heading are frozen")
    body = text[len(header):]
    if not body.endswith("\n") or body.endswith("\n\n"):
        raise ValueError("layer must end with exactly one newline after its checklist")
    rules = body[:-1].split("\n")
    for rule in rules:
        if (not rule.startswith(RULE_PREFIX) or not rule[len(RULE_PREFIX):].strip()
                or rule != rule.strip()):
            raise ValueError("every body line must be one non-empty checklist line")
        if len(rule.encode()) > LAYER_MAX_LINE:
            raise ValueError("checklist line exceeds the byte cap")
    if not 1 <= len(rules) <= LAYER_MAX_RULES or len(set(rules)) != len(rules):
        raise ValueError("checklist must have 1 to 12 distinct lines")
    if len(text.encode()) > LAYER_MAX_BYTES:
        raise ValueError("layer exceeds the byte cap")
    return rules


def layer_info(text, header):
    rules = parse_layer(text, header)
    return dict(bytes=len(text.encode()), sha256=sha_text(text), rules=len(rules),
                estimated_tokens=ceil(len(text.encode()) / 4))


def validate_edit(before, after, header):
    """Exactly one checklist line added, deleted, or reworded in place. No moves."""
    a, b = parse_layer(before, header), parse_layer(after, header)
    if before == after:
        raise ValueError("candidate made no change")
    if len(a) == len(b):
        changed = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(changed) != 1:
            raise ValueError("a reword changes exactly one line in place")
        op, index, added, removed = "reword", changed[0], [b[changed[0]]], [a[changed[0]]]
    elif len(b) == len(a) + 1:
        spots = [i for i in range(len(b)) if b[:i] + b[i + 1:] == a]
        if not spots:
            raise ValueError("an addition inserts exactly one new line")
        op, index, added, removed = "add", spots[0], [b[spots[0]]], []
    elif len(a) == len(b) + 1:
        spots = [i for i in range(len(a)) if a[:i] + a[i + 1:] == b]
        if not spots:
            raise ValueError("a deletion removes exactly one line")
        op, index, added, removed = "delete", spots[0], [], [a[spots[0]]]
    else:
        raise ValueError("more than one checklist line changed")
    growth = len(after.encode()) - len(before.encode())
    if growth > LAYER_MAX_GROWTH:
        raise ValueError("net growth exceeds the per-iteration cap")
    return dict(op=op, index=index, added=added, removed=removed, growth=growth)


def layer_diff(before, after):
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        fromfile="a/THIN-RULES.md", tofile="b/THIN-RULES.md"))


def at_ceiling(text):
    """No further line of the minimum size fits; only shrinking edits can remain valid."""
    return len(text.encode()) + LAYER_MIN_RULE_BYTES + len(RULE_PREFIX) + 1 > LAYER_MAX_BYTES


def at_rule_cap(text, header):
    """The checklist already has the maximum number of lines: an added line is invalid whatever the byte room."""
    return len(parse_layer(text, header)) >= LAYER_MAX_RULES


def add_possible(text, header):
    """Second-review F10: one saturation rule for both limits. A line can be added only below the rule cap AND with room for a
    minimum-size line; a reword or a delete stays possible (a reword may not grow the file once the byte ceiling is reached)."""
    return not at_ceiling(text) and not at_rule_cap(text, header)


def saturation_notice(text, header):
    """The sentence the researcher task states about the limits, derived from the same two predicates the ingest enforces."""
    notes = []
    if at_ceiling(text):
        notes.append("The file is at its size ceiling: only an edit that does not grow it is valid.")
    if at_rule_cap(text, header):
        notes.append("The checklist is at its line cap: adding a line is invalid; reword or delete a line instead.")
    return " ".join(notes)


# ------------------------------------------------------------------ packet-derived wording screen

STRUCTURAL = frozenset("""
async await function const let var return if else for while new class import export from default try catch throw
test describe expect page browser context locator frame request response route beforeEach afterEach beforeAll afterAll
step use skip only fixme fail slow serial parallel configure title fixture
goto reload click dblclick fill type press check uncheck hover focus blur select selectOption setInputFiles dragTo
getByRole getByText getByLabel getByPlaceholder getByTestId getByAltText getByTitle filter first last nth and or not
waitFor waitForURL waitForLoadState waitForTimeout waitForResponse waitForSelector evaluate innerText textContent
inputValue isVisible isHidden isChecked isEnabled isDisabled count all allTextContents url keyboard mouse
name exact timeout hasText has hasNot level checked disabled expanded pressed selected includeHidden
true false null undefined this constructor
button link heading textbox checkbox radio combobox listbox option menu menuitem dialog alert tab tablist tabpanel
list listitem row cell grid navigation main banner img
""".split())


def string_literals(source):
    """Contents of quoted and template literals in a source text (naive, comment-aware)."""
    out, i, n = [], 0, len(source)
    while i < n:
        ch = source[i]
        if source.startswith("//", i):
            i = source.find("\n", i)
            i = n if i < 0 else i
        elif source.startswith("/*", i):
            j = source.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif ch in "\"'`":
            j, buf = i + 1, []
            while j < n and source[j] != ch:
                if source[j] == "\\" and j + 1 < n:
                    buf.append(source[j + 1])
                    j += 2
                    continue
                if source[j] == "\n" and ch != "`":
                    break
                buf.append(source[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
        else:
            i += 1
    return out


def words_of(text):
    return re.findall(r"[A-Za-z]{4,}", text)


STRUCTURAL_LOWER = frozenset(w.lower() for w in STRUCTURAL)
API_NAME = re.compile(r"(?:getBy|to|wait|is|set|expect|page|locator)[A-Z]\w*")


def is_structural(word):
    return word in STRUCTURAL or word.lower() in STRUCTURAL_LOWER or bool(API_NAME.fullmatch(word))


def split_identifier(token):
    return [p.lower() for p in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", token) if len(p) >= 4]


def generic_vocabulary(corpus_text, incumbent_text):
    """Words common in public product guidance, plus the incumbent's own words."""
    counts = Counter(w.lower() for w in words_of(corpus_text))
    common = {w for w, n in counts.items() if n >= GENERIC_MIN_COUNT}
    return common | {w.lower() for w in words_of(incumbent_text)}


def css_tokens(text):
    """Id-like and class-like selector tokens found in text."""
    found = set(re.findall(r"(?<![\w-])#[A-Za-z_][\w-]*", text))
    found |= set(re.findall(r"(?<![\w.)\]])\.[A-Za-z_][\w-]*(?![\w-]*\()", text))
    return {t.lower() for t in found if len(t) >= 3}


def code_identifiers(code):
    """Application-specific identifiers in code outside literals: camelCase, snake_case, kebab-case."""
    found = set(re.findall(r"\b[a-z]+[A-Z]\w*\b", code))
    found |= set(re.findall(r"\b[A-Za-z]+(?:_[A-Za-z0-9]+)+\b", code))
    found |= set(re.findall(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)+\b", code))
    return {t.lower() for t in found if not is_structural(t) and len(t) >= 5}


def derive_forbidden(specs, errors, scopes, task_ids, generic):
    """Everything model-visible dev evidence contains that new rule text must not echo."""
    phrases, tokens, words = set(), set(), set()
    for source in specs:
        modules = set(re.findall(r"(?:\bfrom|\bimport|\brequire\()\s*['\"]([^'\"]+)['\"]", source))
        for lit in string_literals(source):
            if lit in modules:
                continue
            norm = " ".join(lit.lower().split())
            lit_words = [w.lower() for w in words_of(lit)]
            tokens |= css_tokens(lit)
            generic_literal = bool(lit_words) and all(w in generic or w in STRUCTURAL_LOWER for w in lit_words)
            if len(norm) >= 4 and not generic_literal:
                phrases.add(norm)
            words |= {w for w in lit_words if w not in generic and w not in STRUCTURAL_LOWER}
        code = re.sub(r"(['\"`]).*?\1", " ", source, flags=re.S)
        tokens |= code_identifiers(code)
        for ident in re.findall(r"[A-Za-z_]\w*", code):
            if not is_structural(ident):
                words |= {p for p in split_identifier(ident) if p not in generic and p not in STRUCTURAL_LOWER}
    for text in list(errors) + list(scopes):
        tokens |= css_tokens(text)
        for found in re.findall(r"'([^'\n]{2,})'|\"([^\"\n]{2,})\"", text):
            norm = " ".join("".join(found).lower().split())
            if len(norm) >= 4 and not all(w.lower() in generic or w.lower() in STRUCTURAL_LOWER for w in words_of(norm)):
                phrases.add(norm)
        words |= {w.lower() for w in words_of(text) if w.lower() not in generic and w.lower() not in STRUCTURAL_LOWER}
    near = lambda a, b: a == b or ((a.startswith(b) or b.startswith(a)) and min(len(a), len(b)) >= 5)
    words = {w for w in words if not any(near(w, g) for g in generic)}
    return dict(phrases=sorted(phrases), tokens=sorted(tokens), words=sorted(words),
                task_ids=sorted({t.lower() for t in task_ids}),
                counts=dict(phrases=len(phrases), tokens=len(tokens), words=len(words)))


def plan_behaviors(plan_text):
    """The scrubbed behavior sentences of an approved plan (its Expected Results lines)."""
    return [line[4:].strip() for line in plan_text.splitlines() if line.startswith("  - ")]


def text_variants(text):
    """The text as written plus the evasions a wording screen must see through (second-review F7): separators inside a word
    ("side-bar", "re_name"), punctuation splitting a word, and single letters spaced out ("r e f a c t o r")."""
    low = " ".join(text.lower().split())
    glue = r"(?<=[a-z0-9])[-_.`'\"*/\\|](?=[a-z0-9])"
    joined = re.sub(glue, "", low)
    spaced = re.sub(glue, " ", low)
    letters = re.sub(r"\b(?:[a-z] ){3,}[a-z]\b", lambda found: found.group(0).replace(" ", ""), low)
    return list(dict.fromkeys([low, joined, spaced, letters]))


def squash(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


SQUASH_MIN = 8  # a squashed needle shorter than this could match across ordinary word boundaries


def screen_added(added_lines, forbidden):
    """Return violation categories (never the tokens themselves) for added rule text."""
    text = "\n".join(added_lines)
    variants = text_variants(text)
    squashed = squash(text)
    hits = []
    if any(GRADER_WORDS.search(v) for v in variants):
        hits.append("grader-mirroring-vocabulary")
    if any(p in v for v in variants for p in forbidden["phrases"]) or any(
            len(squash(p)) >= SQUASH_MIN and squash(p) in squashed for p in forbidden["phrases"]):
        hits.append("echoes-a-quoted-dev-literal")
    if any(t in v for v in variants for t in forbidden["tokens"]) or any(
            len(squash(t)) >= SQUASH_MIN and squash(t) in squashed for t in forbidden["tokens"]):
        hits.append("echoes-a-selector-or-identifier-token")
    if any(re.search(r"(?<![\w-])" + re.escape(t).replace(r"\-", "[-_. ]?") + r"(?![\w-])", v)
           for v in variants for t in forbidden["task_ids"]):
        hits.append("names-a-dev-task")
    stems = set()
    for v in variants:
        stems |= set(re.findall(r"[a-z]{4,}", v))
    for forb in forbidden["words"]:
        if any(w == forb or ((w.startswith(forb) or forb.startswith(w)) and min(len(w), len(forb)) >= 5) for w in stems):
            hits.append("echoes-application-vocabulary")
            break
    return hits


# ------------------------------------------------------------------ static inner stage (offline, pre-registered, second-review F5/F7)
# Runs on the candidate rule text alone, before any of the live cells. The e2e-reviewer scanner reads specs, not rule text, so
# running it "under the candidate rules" would not depend on the candidate; this stage instead screens the rule text against the
# scanner's own anti-pattern vocabulary and against risky-action wording, with fixed regular expressions registered here.
RISK_PATTERNS = (
    ("directs-install-or-download", re.compile(
        r"(?i)\b(?:npm|npx|pnpm|yarn|pip3?|pipx|brew|apt(?:-get)?|cargo|curl|wget|docker|git clone)\b|\b(?:install|download)\w*")),
    ("directs-network-access", re.compile(
        r"(?i)https?://|\bwww\.|\binternet\b|\bweb search\b|\bsearch the web\b|\bbrowse the web\b|\bexternal (?:service|site|api|server|network)s?\b"
        r"|\bthird-party (?:service|site|api)s?\b|\boutbound\b|\bremote (?:server|host)s?\b|\bupload\w*|\bwebhooks?\b|\bproxy\b|\bfetch\w*\s+(?:from|the (?:internet|web))")),
    ("touches-credentials-or-secrets", re.compile(
        r"(?i)\b(?:passwords?|passwd|secrets?|credentials?|api[ _-]?keys?|private[ _-]?keys?|ssh|keychain|bearer|oauth|dotenv"
        r"|(?:access|auth|session|refresh)[ _-]?tokens?|environment variables?|env vars?|home directory)\b|\.env\b|~/|/etc/|\$HOME")),
    ("directs-writes-outside-tests-or-destructive-commands", re.compile(
        r"(?i)\b(?:write|save|create|edit|modify|change|patch|overwrite|delete|remove|rename|append)\w*\b[^.;]{0,60}?"
        r"(?:\boutside\b|\bconfig(?:uration)?\b|playwright\.config|package(?:-lock)?\.json|\bsource (?:code|files?)\b|\b(?:application|app|production) (?:code|files?|source)\b"
        r"|\.github|\.gitignore|\bsrc\b|node_modules|\bglobal\b|\bsystem\b)"
        r"|\b(?:modify|change|edit|fix|patch)\s+(?:the\s+)?(?:app|application|product|production|implementation)\b"
        r"|\bsudo\b|\bchmod\b|\bchown\b|\brm\s+-|\bgit\s+(?:push|commit|reset|checkout|clean|stash|rebase|config|remote)\b|--force\b|--no-verify\b|\bdangerous\w*"
        r"|\b(?:disable|turn off)\w*\s+(?:the\s+)?(?:sandbox|safety|hooks?|lint\w*|checks?|verification|approvals?|permissions?)\b")),
    ("directs-bypassing-the-official-generator", re.compile(
        r"(?i)\b(?:skip|bypass|ignore|omit|disable|stop using|do not use|don't use|never use|avoid|without)\b[^.;]{0,30}?"
        r"\b(?:generator|planner|planning|mcp|browser tools?|playwright[- ]test tools?|exploration|explor\w+|sub-?agents?|child(?:ren)?|skills?|official|instructions?|approved plan)\b"
        r"|\b(?:write|author|generate)\b[^.;]{0,30}?\b(?:directly|by hand|from memory)\b"
        r"|\bignore\b[^.;]{0,25}?\b(?:previous|above|prior|earlier|other|all|any)\b|/work/skill|SKILL\.md|thin-rules")),
)

# Patterns the e2e-reviewer scanner flags (see skills/e2e-reviewer/references/grep-patterns.md). A rule may mention one only
# to forbid it; a positive directive to use one would train the generator toward a flagged smell.
FLAGGED_PATTERNS = (
    re.compile(r"waitForTimeout|waitForSelector|networkidle|\bsleep\b|setTimeout"),
    re.compile(r"force\s*:\s*true|\{\s*force\b|\bforce[- ]click"),
    re.compile(r"test\.(?:only|skip|fixme)\b|\.only\b|\bskip(?:ping)?\s+(?:the\s+)?(?:failing\s+)?tests?\b"),
    re.compile(r"\.catch\(|swallow|toBeAttached|toBeGreaterThanOrEqual\(0\)|expect\(true\)|\bisVisible\(\)"),
    re.compile(r"document\.querySelector|page\.\$|xpath|\btoHaveClass\b|css selector|\.(?:nth|first|last)\b\s*\("),
)
EXEMPT_CLAUSE = re.compile(r"JUSTIFIED|\bonly (?:with|when|if|after)\b|\bunless\b")
NEGATION = re.compile(r"(?i)\b(?:never|avoid|do not|don't|not|no|without|instead of|reject|forbid\w*|ban\w*|rather than|except|unless|only with)\b")
DIRECTIVE = re.compile(r"(?i)\b(?:prefer|use|avoid|never|always|must|should|do not|don't|only|assert|await|wait|scope|give|group|keep|run|reject|name|verify|ensure|check|delete|remove|limit|write|select|target|make|add|set|treat|read|match|fix|fail)\b")
HEDGES = re.compile(r"(?i)\b(?:maybe|perhaps|possibly|might|could|consider|try to|if possible|when convenient|ideally)\b")
NEAR_DUPLICATE = 0.7


def risk_screen(added_lines):
    """Second-review F7: rule text may not direct an install, network use, credential access, a write outside the tests
    or a bypass of the official generator. Categories only, never the matched text."""
    variants = text_variants("\n".join(added_lines))
    return sorted({name for name, pattern in RISK_PATTERNS if any(pattern.search(v) for v in variants)})


def _api_polarity(text):
    """API names a rule mentions, each with the polarity of the clause that mentions it (negative wins within a clause)."""
    found = {}
    for clause in re.split(r";|\.(?=\s|$)", text):
        if EXEMPT_CLAUSE.search(clause):
            continue
        names = {n.lower() for n in re.findall(r"`([^`]+)`", clause)}
        names |= {n.lower() for n in re.findall(r"\b(?:getBy\w+|waitFor\w*|toHave\w+|toBe\w+|toContain\w+)\b", clause)}
        polarity = "negative" if NEGATION.search(clause) else "positive" if re.search(r"(?i)\b(?:prefer|use|always|must|should)\b", clause) else None
        for name in {re.sub(r"[^a-z]", "", n) for n in names} - {""}:
            if polarity:
                found.setdefault(name, set()).add(polarity)
    return found


def static_screen(edit, after_rules):
    """The cheap static inner stage: deterministic checks on the added line(s) that reject a candidate before generation.
    Returns sorted category names; an empty list lets the candidate reach the live stages."""
    hits = list(risk_screen(edit["added"]))
    others = [r for r in after_rules if r not in edit["added"]]
    for line in edit["added"]:
        body = line[len(RULE_PREFIX):] if line.startswith(RULE_PREFIX) else line
        if len(body.encode()) < LAYER_MIN_RULE_BYTES:
            hits.append("rule-too-short")
        if not DIRECTIVE.search(body):
            hits.append("no-directive-verb")
        if HEDGES.search(body):
            hits.append("hedged-rule")
        tokens = set(re.findall(r"[a-z]{3,}", body.lower()))
        for other in others:
            theirs = set(re.findall(r"[a-z]{3,}", other.lower()))
            if tokens and theirs and len(tokens & theirs) / len(tokens | theirs) >= NEAR_DUPLICATE:
                hits.append("near-duplicate-of-existing-rule")
                break
        for clause in re.split(r";|\.(?=\s|$)", body):
            if EXEMPT_CLAUSE.search(clause):
                continue
            found = [m_ for pattern in FLAGGED_PATTERNS for m_ in pattern.finditer(clause)]
            if any(not NEGATION.search(clause[:m_.start()]) for m_ in found):
                hits.append("endorses-a-scanner-flagged-pattern")
                break
        mine = _api_polarity(body)
        for other in others:
            theirs = _api_polarity(other)
            if any(len(mine[n]) == len(theirs[n]) == 1 and mine[n] != theirs[n] for n in mine.keys() & theirs.keys()):
                hits.append("contradicts-an-existing-rule")
                break
    return sorted(set(hits))


# ------------------------------------------------------------------ deterministic redaction for the researcher

ERROR_CLASSES = (
    ("strict_mode_violation", r"strict mode violation"),
    ("test_timeout", r"Test timeout of \d+\s*ms exceeded"),
    ("locator_wait_timeout", r"waiting for (?:locator|getBy)|locator\.\w+: Timeout|Timeout \d+\s*ms exceeded"),
    ("navigation_error", r"net::ERR|ERR_CONNECTION|ERR_NAME|page\.goto"),
    ("not_actionable", r"not visible|not enabled|not editable|intercepts pointer events|element is detached"),
    ("assertion_mismatch", r"expect\(|Expected|Received|toHave|toBe|toContain|toEqual"),
    ("syntax_or_reference", r"SyntaxError|Cannot find module|Unexpected token|is not defined|TypeError|ReferenceError"),
)


def error_class(message):
    for name, pattern in ERROR_CLASSES:
        if re.search(pattern, str(message), re.I):
            return name
    return "other"


def literal_kind(content):
    if re.match(r"\s*#[\w-]", content):
        return "css-id"
    if re.match(r"\s*\.[\w-]", content) or "[class" in content:
        return "css-class"
    if content.lstrip().startswith("[") or re.match(r"\s*(?:css|xpath|id|data-testid)\s*=", content):
        return "css-attribute"
    return "text"


def redact_spec(source, max_chars=PACKET_SKELETON_CHARS):
    """Keep statement structure and Playwright API shape; drop every literal and unknown identifier."""
    out, i, n = [], 0, len(source)
    structural = {s for s in STRUCTURAL}
    while i < n:
        ch = source[i]
        if source.startswith("//", i):
            i = source.find("\n", i)
            i = n if i < 0 else i
        elif source.startswith("/*", i):
            j = source.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif ch in "\"'`":
            j, buf = i + 1, []
            while j < n and source[j] != ch:
                if source[j] == "\\" and j + 1 < n:
                    buf.append(source[j + 1])
                    j += 2
                    continue
                if source[j] == "\n" and ch != "`":
                    break
                buf.append(source[j])
                j += 1
            content = "".join(buf)
            out.append('"<tpl>"' if ch == "`" and "${" in content else '"<%s>"' % literal_kind(content))
            i = j + 1
        elif ch == "/" and re.search(r"[(,=:\[!&|?{};]\s*$", "".join(out[-8:])):
            j = i + 1
            while j < n and source[j] not in "/\n":
                j += 2 if source[j] == "\\" else 1
            if j < n and source[j] == "/":
                j += 1
                while j < n and source[j].isalpha():
                    j += 1
                out.append("<re>")
                i = j
            else:
                out.append(ch)
                i += 1
        elif ch.isalpha() or ch in "_$":
            j = i
            while j < n and (source[j].isalnum() or source[j] in "_$"):
                j += 1
            word = source[i:j]
            known = (word in structural or re.fullmatch(r"(?:getBy|to|wait|is|set|expect)[A-Z]\w*", word)
                     or re.fullmatch(r"[A-Z]?[a-z]{1,3}", word))
            out.append(word if known else "<id>")
            i = j
        elif ch.isdigit():
            j = i
            while j < n and (source[j].isalnum() or source[j] == "."):
                j += 1
            out.append(source[i:j])
            i = j
        else:
            out.append(ch)
            i += 1
    text = re.sub(r"\n\s*\n+", "\n", "".join(out)).strip()
    return text[:max_chars]


# ------------------------------------------------------------------ schedule and statistics

def stage_slots(stage, aa3=False):
    if stage == "baseline":
        return ("aa1", "aa2") + (("aa3",) if aa3 else ()) + ("ref-A",)
    if stage in ("screening", "confirmation"):
        return ("incumbent", "candidate")
    raise ValueError("unregistered stage")


def stage_seed(iteration, stage):
    return SEED + (0 if stage == "baseline" else 10 * iteration + (1 if stage == "screening" else 2))


def check_stage(iteration, stage):
    if type(iteration) is not int or not 0 <= iteration <= MAX_ITERATIONS:
        raise ValueError("iteration must be 0 through 6")
    if (iteration == 0) != (stage == "baseline") or stage not in STAGES:
        raise ValueError("baseline is iteration 0; later iterations use screening or confirmation")


def schedule(iteration=0, stage=None, aa3=False):
    stage = stage or ("baseline" if iteration == 0 else "screening")
    check_stage(iteration, stage)
    rng = random.Random(stage_seed(iteration, stage))
    pairs = [(case, rep) for case in DEV for rep in (1, 2)]
    rng.shuffle(pairs)
    rows = []
    for case, rep in pairs:
        slots = list(stage_slots(stage, aa3))
        rng.shuffle(slots)
        for slot in slots:
            rows.append(dict(case=case, repetition=rep, slot=slot, ordinal=len(rows) + 1,
                             treatment="A" if slot == "ref-A" else "D", stage=stage, iteration=iteration))
    return rows


def cell_serial(iteration, stage, slot, repetition):
    """Unique integer so each slot's Zeppelin cell gets its own namespace and artifacts."""
    return 1000 * iteration + 100 * STAGES.index(stage) + 10 * (list(stage_slots(stage, True)).index(slot) + 1) + repetition


def budget_cells(aa3=False):
    return (3 * batch_cells() + (batch_cells() if aa3 else 0)) + MAX_ITERATIONS * 4 * batch_cells()


def number(value, name, lower=0, upper=None):
    if type(value) not in (int, float) or not isfinite(value) or value < lower or (upper is not None and value > upper):
        raise ValueError("invalid or missing " + name)
    return value


def check_cell(c, treatment):
    assert_dev(c["case"])
    if type(c["repetition"]) is not int or not isinstance(c["call_id"], str) or not c["call_id"]:
        raise ValueError("malformed repetition or call ID")
    if type(c["clean"]) is not bool or c["refactor_score"] not in (0, 1) or type(c["refactor_score"]) is bool:
        raise ValueError("malformed clean or binary survival")
    if c["refactor_score"] and not c["clean"]:
        raise ValueError("unclean cell cannot survive")
    if c.get("infrastructure_error") or c.get("cost_complete") is False:
        raise ValueError("infrastructure or incomplete cost makes batch void")
    if type(c["timeout"]) is not bool:
        raise ValueError("timeout flag must be boolean")
    # A timed-out cell may lack child or root usage; its recorded cost is then a lower bound. Understated cost can only make a
    # candidate look more expensive against it, and a timeout in the candidate batch blocks adoption anyway.
    if c.get("cost_lower_bound") not in (None, False) and not (c["cost_lower_bound"] is True and c["timeout"]):
        raise ValueError("only a timed-out cell may carry a lower-bound cost")
    if c["timeout"] and (c["clean"] or c["refactor_score"] or c["kill_rate"]):
        raise ValueError("a timed-out cell must be scored zero")
    number(c["kill_rate"], "kill rate", upper=1)
    for key in ("tokens", "cached_tokens", "generation_s", "max_attempt_s", "scan_p0", "scan_p1p2"):
        number(c[key], key)
    if any(type(c[k]) is not int for k in ("scan_p0", "scan_p1p2")):
        raise ValueError("scanner counts must be integers")
    if c.get("fidelity_class") is not None and not isinstance(c["fidelity_class"], str):
        raise ValueError("fidelity class must be a string or unknown")
    for key in ("layer_read", "verification_executed"):
        if c.get(key) is not None and type(c[key]) is not bool:
            raise ValueError(key + " must be boolean or unknown")
    if treatment == "D" and "layer_read" not in c:
        raise ValueError("layer-read indicator required for D cells")


def summarize(cells, treatment="D"):
    expected = {(case, rep) for case in DEV for rep in (1, 2)}
    if len(cells) != batch_cells() or {(c["case"], c["repetition"]) for c in cells} != expected:
        raise ValueError("batch incomplete, duplicate or foreign task")
    if len({c["call_id"] for c in cells}) != batch_cells():
        raise ValueError("duplicate call ID")
    for c in cells:
        check_cell(c, treatment)
    mean = lambda values: sum(values) / len(values)
    clean = [c for c in cells if c["clean"]]
    verification = [c.get("verification_executed") for c in cells]
    return dict(dev_refactor_survival=mean([c["refactor_score"] for c in cells]),
                clean_all_three_rate=mean([int(c["clean"]) for c in cells]),
                effective_kill_all_cells=mean([c["kill_rate"] if c["clean"] else 0 for c in cells]),
                effective_kill_clean_cells=mean([c["kill_rate"] for c in clean]) if clean else None,
                scanner_p0_total=sum(c["scan_p0"] for c in cells),
                scanner_p1p2_total=sum(c["scan_p1p2"] for c in cells),
                tokens_mean=mean([c["tokens"] for c in cells]),
                tokens_incl_cached_mean=mean([c["tokens"] + c["cached_tokens"] for c in cells]),
                generation_s_mean=mean([c["generation_s"] for c in cells]),
                timeouts=sum(c["timeout"] for c in cells),
                slow_cells=sum(c["max_attempt_s"] > SLOW_S for c in cells),
                layer_read_rate=mean([int(c["layer_read"] is True) for c in cells]) if treatment == "D" else None,
                official_tool_rate=mean([int(c.get("fidelity_class") == FIDELITY_OFFICIAL) for c in cells]),
                verification_rate=None if any(v is None for v in verification) else mean([int(v) for v in verification]),
                cells=batch_cells())


def permutation(candidate, incumbent):
    """Exact one-sided task-stratified label permutation; descriptive only."""
    summarize(candidate)
    summarize(incumbent)
    distribution = {Fraction(0): Fraction(1)}
    observed = Fraction(0)
    for task in DEV:
        c = [int(r["refactor_score"]) for r in candidate if r["case"] == task]
        b = [int(r["refactor_score"]) for r in incumbent if r["case"] == task]
        observed += Fraction(sum(c), 2) - Fraction(sum(b), 2)
        k = sum(c + b)
        step = {Fraction(x, 2) - Fraction(k - x, 2): Fraction(comb(k, x) * comb(4 - k, 2 - x), 6)
                for x in range(max(0, k - 2), min(2, k) + 1)}
        new = defaultdict(Fraction)
        for a, pa in distribution.items():
            for b2, pb in step.items():
                new[a + b2] += pa * pb
        distribution = new
    return dict(p_one_sided=float(sum(p for v, p in distribution.items() if v >= observed)),
                observed_mean_task_difference=float(observed / len(DEV)), tasks=len(DEV),
                interpretation="descriptive; within-task exchangeability is not established")


def per_task(cells):
    return {t: dict(survival=sum(c["refactor_score"] for c in cells if c["case"] == t),
                    clean=sum(c["clean"] for c in cells if c["case"] == t), cells=2) for t in DEV}


def decide(candidate_cells, incumbent_cells, history_batches, context, with_permutation=True):
    """One paired batch decision. All guards must hold; a layer that was not read earns no credit."""
    c, b = summarize(candidate_cells), summarize(incumbent_cells)
    if len(history_batches) < 2:
        raise ValueError("at least two incumbent batches required for A/A spread")
    summaries = [summarize(batch) for batch in history_batches]
    noise = {}
    for key, value in c.items():
        if key == "cells" or value is None:
            continue
        values = [s[key] for s in summaries if s[key] is not None]
        noise[key] = dict(min=min(values), max=max(values), width=max(values) - min(values)) if values else None
    base_tokens, base_cached = number(context["baseline_tokens_mean"], "baseline tokens", lower=1e-9), \
        number(context["baseline_tokens_incl_cached_mean"], "baseline cached-inclusive tokens", lower=1e-9)
    cand_bytes, inc_bytes = context["candidate_layer_bytes"], context["incumbent_layer_bytes"]
    rel = lambda x, y: x / y - 1 if y > 0 else None
    tokens, cached = rel(c["tokens_mean"], b["tokens_mean"]), rel(c["tokens_incl_cached_mean"], b["tokens_incl_cached_mean"])
    seconds = rel(c["generation_s_mean"], b["generation_s_mean"])
    cum_tokens, cum_cached = rel(c["tokens_mean"], base_tokens), rel(c["tokens_incl_cached_mean"], base_cached)
    cap = TOKEN_GROWTH_CAP + 1e-12
    tol = context.get("tolerance") or GUARD_PROFILES["strict"]
    if set(tol) != set(GUARD_KEYS):
        raise ValueError("guard tolerance must name exactly the five guards")
    guards = {k: c[k] is not None and b[k] is not None and c[k] >= b[k] - tol[k] - 1e-12
              for k in ("clean_all_three_rate", "effective_kill_all_cells", "effective_kill_clean_cells")}
    guards.update({k: c[k] <= b[k] + tol[k] for k in ("scanner_p0_total", "scanner_p1p2_total")})
    guards.update(timeouts_zero=c["timeouts"] == 0, slow_cells_ok=c["slow_cells"] <= MAX_SLOW_CELLS,
                  layer_bytes_ok=cand_bytes <= LAYER_MAX_BYTES,
                  layer_growth_ok=cand_bytes - inc_bytes <= LAYER_MAX_GROWTH,
                  tokens_vs_incumbent=tokens is not None and tokens <= cap,
                  tokens_cached_vs_incumbent=cached is not None and cached <= cap,
                  tokens_vs_iteration0=cum_tokens is not None and cum_tokens <= cap,
                  tokens_cached_vs_iteration0=cum_cached is not None and cum_cached <= cap)
    delta = c["dev_refactor_survival"] - b["dev_refactor_survival"]
    applied = (c["layer_read_rate"] or 0) >= LAYER_READ_MIN - 1e-12 and (b["layer_read_rate"] or 0) >= LAYER_READ_MIN - 1e-12
    verification_ok = (c["verification_rate"] is not None and b["verification_rate"] is not None
                       and c["verification_rate"] >= b["verification_rate"] - 1e-12)
    # Second-review F1/F4: adoption requirements that are not rate guards. A candidate (and the incumbent it is compared with)
    # must keep the official-tool process: a rule that makes the model bypass the official generator could otherwise win on cost.
    # And no task may regress, because one cell moves a 3-task mean by .17 and a net +1 cell must not hide a regressed task.
    per = dict(candidate=per_task(candidate_cells), incumbent=per_task(incumbent_cells))
    requirements = dict(
        official_tool_fidelity=c["official_tool_rate"] >= FIDELITY_MIN_RATE - 1e-12 and b["official_tool_rate"] >= FIDELITY_MIN_RATE - 1e-12,
        no_task_regression=all(per["candidate"][t]["survival"] >= per["incumbent"][t]["survival"] for t in DEV))
    verdict = "REJECT"
    if not applied:
        verdict = "NOT_APPLIED"
    elif all(guards.values()) and all(requirements.values()):
        if delta >= QUALITY_DELTA - 1e-12:
            verdict = "ADOPT_QUALITY"
        elif (delta >= -1e-12 and verification_ok and seconds is not None and tokens is not None and (
                (tokens <= -COST_REDUCTION + 1e-12 and seconds <= .10 + 1e-12) or
                (seconds <= -COST_REDUCTION + 1e-12 and tokens <= .10 + 1e-12))):
            verdict = "ADOPT_COST"
    width = noise["dev_refactor_survival"]["width"]
    out = dict(verdict=verdict, guards=guards, requirements=requirements, applied=applied, candidate=c, incumbent=b, delta=delta,
               cell_ids=dict(candidate=sorted(x["call_id"] for x in candidate_cells), incumbent=sorted(x["call_id"] for x in incumbent_cells)),
               tokens_change=tokens, tokens_incl_cached_change=cached, seconds_change=seconds,
               tokens_change_vs_iteration0=cum_tokens, tokens_incl_cached_change_vs_iteration0=cum_cached,
               verification_not_lower=verification_ok, noise=noise, within_batch_width=abs(delta) <= width + 1e-12,
               per_task=per,
               layer=dict(candidate_bytes=cand_bytes, incumbent_bytes=inc_bytes, growth=cand_bytes - inc_bytes),
               evidence_label="development evidence; adoption is not a significance or release claim")
    if with_permutation:
        out["task_stratified_exact_permutation"] = permutation(candidate_cells, incumbent_cells)
    return out


def combine_stages(screening, confirmation=None):
    """Adoption needs ADOPT in the screening pair and again in a fresh confirmation pair."""
    s = screening["verdict"]
    if s not in ADOPTIONS:
        return dict(verdict=s, decided_at="screening")
    if confirmation is None:
        return dict(verdict="CONFIRMATION_REQUIRED", decided_at="screening")
    if confirmation["verdict"] not in ADOPTIONS:
        return dict(verdict="REJECT_ON_CONFIRMATION", decided_at="confirmation",
                    confirmation_verdict=confirmation["verdict"])
    kind = "ADOPT_QUALITY" if s == confirmation["verdict"] == "ADOPT_QUALITY" else "ADOPT_COST"
    return dict(verdict=kind, decided_at="confirmation")


def pooled_check(screening, confirmation):
    """Second-review F4. The confirmation pair re-runs the same three tasks (fresh cells, same tasks), so a task-specific lucky
    streak or an overfit to those tasks can repeat. Adoption therefore also needs the screening and confirmation batches pooled
    (twelve cells per arm by default): disjoint cells, no task that the candidate loses on, and, on the quality path, a net gain
    of at least QUALITY_POOLED_MIN_CELLS cells."""
    def total(arm, task):
        return screening["per_task"][arm][task]["survival"] + confirmation["per_task"][arm][task]["survival"]
    net = sum(total("candidate", t) - total("incumbent", t) for t in DEV)
    regressed = [t for t in DEV if total("candidate", t) < total("incumbent", t)]
    first = {k for ids in screening["cell_ids"].values() for k in ids}
    second = {k for ids in confirmation["cell_ids"].values() for k in ids}
    distinct = not (first & second)
    quality_path = screening["verdict"] == "ADOPT_QUALITY" and confirmation["verdict"] == "ADOPT_QUALITY"
    return dict(net_cells=net, required_net_cells=QUALITY_POOLED_MIN_CELLS, regressed_tasks=len(regressed), distinct_cells=distinct,
                quality_path=quality_path,
                passes=distinct and not regressed and (net >= QUALITY_POOLED_MIN_CELLS or not quality_path))


def combine_with_pooled_gate(screening, confirmation):
    """combine_stages plus the pooled confirmation gate; used by the live decision and by the offline simulation alike."""
    combined = combine_stages(screening, confirmation)
    if combined["verdict"] not in ADOPTIONS:
        return combined
    check = pooled_check(screening, confirmation)
    combined["pooled_check"] = check
    if not check["passes"]:
        return dict(verdict="REJECT_ON_CONFIRMATION", decided_at="confirmation", confirmation_verdict=confirmation["verdict"],
                    reason="pooled screening plus confirmation gate", pooled_check=check)
    return combined


def headroom_gate(d_batches, reference=None):
    """Stop with NO_HEADROOM when the layer v0 already saturates the dev set, and with LAYER_NOT_READ when the D-v0 batches
    miss the layer-read rate that every later decision needs (otherwise screening cells would be spent on NOT_APPLIED pairs)."""
    summaries = [summarize(b) for b in d_batches]
    if len(summaries) < 2:
        raise ValueError("at least two D-v0 batches required")
    read_rates = [s["layer_read_rate"] for s in summaries]
    not_read = any(r is None or r < LAYER_READ_MIN - 1e-12 for r in read_rates)
    fidelity_rates = [s["official_tool_rate"] for s in summaries]
    low_fidelity = any(r < FIDELITY_MIN_RATE - 1e-12 for r in fidelity_rates)
    cells = [c for b in d_batches for c in b]
    survival = sum(c["refactor_score"] for c in cells) / len(cells)
    kill = sum((c["kill_rate"] if c["clean"] else 0) for c in cells) / len(cells)
    out = dict(cells=len(cells), d_survival=survival, d_kill_all_cells=kill,
               verdict=("LAYER_NOT_READ" if not_read else
                        "LOW_FIDELITY" if low_fidelity else
                        "NO_HEADROOM" if survival >= HEADROOM_SURVIVAL - 1e-12 and kill >= HEADROOM_KILL - 1e-12 else "HEADROOM"),
               thresholds=dict(survival=HEADROOM_SURVIVAL, kill=HEADROOM_KILL, layer_read_per_batch=LAYER_READ_MIN,
                               official_tool_per_batch=FIDELITY_MIN_RATE),
               layer_read_rates=read_rates, official_tool_rates=fidelity_rates,
               aa_spread={k: dict(min=min(s[k] for s in summaries), max=max(s[k] for s in summaries))
                          for k in ("dev_refactor_survival", "effective_kill_all_cells", "tokens_mean")})
    if reference is not None:
        r = summarize(reference, treatment="A")
        out["reference_a"] = dict(survival=r["dev_refactor_survival"], kill_all_cells=r["effective_kill_all_cells"],
                                  tokens_mean=r["tokens_mean"], cells=batch_cells(),
                                  d_minus_a_survival=survival - r["dev_refactor_survival"],
                                  note=f"descriptive; one batch of {batch_cells()} cells")
    return out


def stop_reason(decisions, state=None):
    """First applicable stop; precedence is fixed and documented in the protocol."""
    state = state or {}
    if state.get("blocked"):
        return "BLOCKED"
    if state.get("no_headroom"):
        return "NO_HEADROOM"
    if state.get("layer_not_read"):
        return "LAYER_NOT_READ"
    if state.get("low_fidelity"):
        return "LOW_FIDELITY"
    if len(decisions) >= MAX_ITERATIONS:
        return "iteration cap"
    if len(decisions) >= MAX_CONSECUTIVE_NON_ADOPTIONS and all(
            d["verdict"] not in ADOPTIONS for d in decisions[-MAX_CONSECUTIVE_NON_ADOPTIONS:]):
        return "two consecutive non-adoptions"
    if state.get("ceiling_without_candidate"):
        return "layer ceiling without a valid shrinking candidate"
    if state.get("cells_spent", 0) >= state.get("budget", budget_cells()):
        return "generation budget exhausted"
    if state.get("draws_spent", 0) >= RESEARCHER_DRAW_BUDGET:
        return "researcher draw budget exhausted"
    return None


# ------------------------------------------------------------------ offline Monte Carlo of the decision rule

def _poisson(rng, lam):
    limit, k, p = exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def sim_batch(rng, qs, shift, tag):
    cells = []
    for case in DEV:
        for rep in (1, 2):
            q = min(1.0, max(0.0, qs[case] + shift))
            clean = rng.random() < 0.92
            survive = int(clean and rng.random() < q)
            cells.append(dict(case=case, repetition=rep, call_id=f"{tag}-{case}-{rep}", clean=clean,
                              refactor_score=survive, kill_rate=rng.choices([.6, .8, 1.0], [.2, .3, .5])[0] if clean else 0,
                              scan_p0=_poisson(rng, .15), scan_p1p2=_poisson(rng, 1.2),
                              tokens=100000 * rng.lognormvariate(0, .15), cached_tokens=400000 * rng.lognormvariate(0, .15),
                              generation_s=600 * rng.lognormvariate(0, .25), max_attempt_s=600 * rng.lognormvariate(0, .25),
                              timeout=False, layer_read=rng.random() < .97, verification_executed=True,
                              fidelity_class=FIDELITY_OFFICIAL, deliverable=True))
    return cells


def simulate(replicates=2000, seed=20261017, base=0.6, effect=0.0, task_sd=0.6, profile="strict"):
    """Adopt probabilities of the two-stage rule under a constant true candidate effect.
    Candidates never differ in cost, scanner counts or clean rate; only survival moves by `effect`."""
    rng = random.Random(seed)
    logit = lambda p: log(p / (1 - p))
    counts = Counter()
    for _ in range(replicates):
        qs = {t: 1 / (1 + exp(-(logit(base) + rng.gauss(0, task_sd)))) for t in DEV}
        history = [sim_batch(rng, qs, 0, "aa1"), sim_batch(rng, qs, 0, "aa2")]
        base_tokens = sum(c["tokens"] for b in history for c in b) / (2 * batch_cells())
        base_cached = sum(c["tokens"] + c["cached_tokens"] for b in history for c in b) / (2 * batch_cells())
        shift, non_adopt, adopted_any = 0.0, 0, False
        context = dict(baseline_tokens_mean=base_tokens, baseline_tokens_incl_cached_mean=base_cached,
                       candidate_layer_bytes=2000, incumbent_layer_bytes=1900, tolerance=GUARD_PROFILES[profile])
        for _iteration in range(MAX_ITERATIONS):
            inc = sim_batch(rng, qs, shift, "inc")
            cand = sim_batch(rng, qs, shift + effect, "cand")
            screen = decide(cand, inc, history + [inc], context, with_permutation=False)
            counts["screens"] += 1
            counts["screen_guards_pass"] += all(screen["guards"].values())
            counts["screen_adopt"] += screen["verdict"] in ADOPTIONS
            final, new_batches, new_history = screen["verdict"], [inc], None
            if screen["verdict"] in ADOPTIONS:
                inc2 = sim_batch(rng, qs, shift, "inc2")
                cand2 = sim_batch(rng, qs, shift + effect, "cand2")
                confirm = decide(cand2, inc2, history + [inc, inc2], context, with_permutation=False)
                counts["confirmations"] += 1
                counts["confirm_adopt"] += confirm["verdict"] in ADOPTIONS
                final = combine_with_pooled_gate(screen, confirm)["verdict"]
                new_batches, new_history = [inc, inc2], [cand, cand2]
            counts["iterations"] += 1
            if final in ADOPTIONS:
                counts["adoptions"] += 1
                adopted_any, shift, non_adopt, history = True, shift + effect, 0, new_history
            else:
                non_adopt += 1
                history = history + new_batches
                if non_adopt >= MAX_CONSECUTIVE_NON_ADOPTIONS:
                    break
        counts["loops_with_adoption"] += adopted_any
    n = replicates
    return dict(replicates=n, seed=seed, guard_profile=profile, base_survival=base, true_effect=effect, task_logit_sd=task_sd,
                p_all_guards_pass_screening=counts["screen_guards_pass"] / counts["screens"],
                p_screening_adopts=counts["screen_adopt"] / counts["screens"],
                p_confirmation_adopts_given_screen=(counts["confirm_adopt"] / counts["confirmations"]) if counts["confirmations"] else None,
                p_iteration_adopts=counts["adoptions"] / counts["iterations"],
                p_loop_adopts_at_least_once=counts["loops_with_adoption"] / n,
                mean_adoptions_per_loop=counts["adoptions"] / n)


# ------------------------------------------------------------------ outcome-blind model rule and gates

def hard_official(cell):
    return cell.get("fidelity_class") == "official-tool" and \
        ((cell.get("fidelity") or {}).get("evidence") or {}).get("strength") == "hard"


def select_model(results, order):
    """Rank on arm A/D process and delivery fields only. Quality, kill, selector, scanner and cost
    fields are never read, so no outcome can steer the choice. A model whose thin-eval evidence is
    unfinished (still running, or too few A or D cells) is skipped and reported, never ranked: the chosen
    model must be able to pass the thin-eval gate that prepare requires."""
    rows, skipped = [], []
    for model in order:
        result = results.get(model)
        if result is None:
            continue
        cells = result["cells"]
        a = [c for c in cells if c["arm"] == ARM_A]
        d = [c for c in cells if c["arm"] == ARM_D]
        reason = None
        if not result.get("complete"):
            reason = "thin-eval results not complete"
        elif len(a) < SELECTION_MIN_A_CELLS:
            reason = f"fewer than {SELECTION_MIN_A_CELLS} arm A cells"
        elif len(d) < SELECTION_MIN_D_CELLS:
            reason = f"fewer than {SELECTION_MIN_D_CELLS} arm D cells (finished thin-eval evidence required)"
        if reason:
            skipped.append(dict(model=model, reason=reason))
            continue
        both = a + d
        rows.append(dict(model=model, order=order.index(model), cells=len(both),
                         hard_official=sum(hard_official(c) for c in both),
                         delivered=sum(bool(c.get("deliverable")) for c in both),
                         d_cells=len(d), d_layer_read=sum(bool(c.get("thin_layer_read_indicator")) for c in d)))
    if not rows:
        raise ValueError("no candidate model has finished thin-eval evidence: " + json.dumps(skipped))
    rows.sort(key=lambda r: (-r["hard_official"] / r["cells"], -r["delivered"] / r["cells"],
                             -(r["d_layer_read"] / r["d_cells"] if r["d_cells"] else 0), r["order"]))
    return dict(rule_version=SELECTION_RULE, chosen=rows[0]["model"], ranking=rows, skipped=skipped,
                fields_read=["arm", "deliverable", "fidelity_class", "fidelity.evidence.strength", "thin_layer_read_indicator"],
                fields_never_read=["clean", "refactor_score", "effective_fault_kill", "selector_hygiene",
                                   "scanner", "tokens", "cost", "elapsed"])


def thin_eval_gate(result, model):
    """Headroom and layer-application evidence for the chosen model from a finished thin-eval result."""
    cells = result["cells"]
    d = [c for c in cells if c["arm"] == ARM_D]
    a = [c for c in cells if c["arm"] == ARM_A]
    if not result.get("complete") or len(d) < 12 or len(a) < 12:
        raise ValueError("finished thin-eval result with at least 12 A and 12 D cells required")
    for c in d + a:
        if c.get("refactor_score") is None or (c.get("effective_fault_kill") is None and c.get("clean")):
            raise ValueError("incomplete quality fields in thin-eval result")
    survival = sum(c["refactor_score"] for c in d) / len(d)
    kill = sum((c.get("effective_fault_kill") or 0) if c.get("clean") else 0 for c in d) / len(d)
    a_survival = sum(c["refactor_score"] for c in a) / len(a)
    read = sum(bool(c.get("thin_layer_read_indicator")) for c in d) / len(d)
    if read < LAYER_READ_MIN - 1e-12:
        verdict = "LAYER_NOT_READ"
    elif survival >= HEADROOM_SURVIVAL and kill >= HEADROOM_KILL:
        verdict = "NO_HEADROOM"
    else:
        verdict = "HEADROOM"
    return dict(model=model, verdict=verdict, d_cells=len(d), a_cells=len(a), d_survival=survival, d_kill=kill,
                a_survival=a_survival, d_minus_a_survival=survival - a_survival, d_layer_read_rate=read,
                layer_effect_observed=abs(survival - a_survival) >= 0.05,
                rule="loop starts only on HEADROOM: D below .95 survival or kill, and the layer read in at least 90 percent of D cells "
                     "(the same rate every loop decision needs)")


# ------------------------------------------------------------------ repository script closure

def static_script_refs(path):
    """Repo scripts a Python file imports or names as a path string."""
    refs = set()
    try:
        tree_ = ast.parse(Path(path).read_text())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return refs
    names = []
    for node in ast.walk(tree_):
        if isinstance(node, ast.Import):
            names += [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.append(node.module.split(".")[0])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith(".py"):
            names.append(node.value)
    for name in names:
        for base in (ROOT, ROOT / "scripts/evals", ROOT / "scripts/ci/lib", ROOT / "scripts"):
            for candidate in (base / name, base / (name + ".py")):
                if candidate.is_file() and (ROOT / "scripts") in candidate.resolve().parents:
                    refs.add(candidate.resolve())
    return refs


def script_closure(seeds):
    """Static closure of repo scripts. Test files are bound separately and never widen the set."""
    seen, queue = set(), [Path(s).resolve() for s in seeds]
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        queue.extend(r for r in static_script_refs(path) - seen if not r.name.startswith("test-"))
    return seen


def loaded_repo_scripts(modules):
    """Repo scripts reachable through the module-attribute graph of already loaded modules."""
    found, queue, seen = set(), list(modules), set()
    while queue:
        module = queue.pop()
        if id(module) in seen or not isinstance(module, types.ModuleType):
            continue
        seen.add(id(module))
        file = getattr(module, "__file__", None)
        if not file:
            continue
        path = Path(file).resolve()
        if (ROOT / "scripts") not in path.parents:
            continue
        found.add(path)
        queue.extend(v for v in list(vars(module).values()) if isinstance(v, types.ModuleType))
    return found


# ------------------------------------------------------------------ machinery (lazy, one stack)

def machinery():
    """The Zeppelin OSS runner and the Codex v4 modules it imports are the only machinery stack.
    Synthetic and Zeppelin cells are generated, scored and costed through the same instances."""
    global MACHINERY
    if MACHINERY is None:
        sys.path.insert(0, str(ROOT / "scripts/evals"))
        spec = importlib.util.spec_from_file_location("loop_thin_oss", ROOT / "scripts/evals/run-generator-oss-eval-v1.py")
        oss = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(oss)
        MACHINERY = oss
    return MACHINERY


def metrics():
    global METRICS
    if METRICS is None:
        sys.path.insert(0, str(ROOT / "scripts/evals"))
        spec = importlib.util.spec_from_file_location("loop_thin_metrics", ROOT / "scripts/evals/generator_thin_metrics_v1.py")
        METRICS = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(METRICS)
    return METRICS


def seed_scripts():
    return [Path(__file__), ROOT / "scripts/evals/run-generator-oss-eval-v1.py",
            ROOT / "scripts/evals/generator_thin_metrics_v1.py"]


def bound_scripts():
    """The freeze set: static closure of the seeds, united with every repo script actually loaded."""
    oss = machinery()
    metrics()
    loaded = loaded_repo_scripts([oss, METRICS, oss.v2])
    closure = script_closure(seed_scripts() + sorted(loaded))
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(closure | loaded)}


def external(path):
    if path is None:
        raise ValueError("--campaign required")
    raw = Path(path).expanduser().absolute()
    for parent in (raw, *raw.parents):
        if parent.is_symlink() or (parent / ".git").exists() or parent.name == "e2e-skills-bench":
            raise ValueError("campaign must be external, unlinked and outside every repository/cache")
    return raw.resolve()


def docker_root():
    """Container bind mounts of the campaign need a root under the home directory (as the Zeppelin smoke requires)."""
    return Path.home().resolve()


FORBIDDEN_POOL_NAMES = re.compile(r"(?i)^(?:sealed|evals?\b|evaluation|author-patches|defect-meta|mutant|verified|results|harness)")


def check_pool(pool):
    """Only a staged DEV-only pool is acceptable: tasks/<dev>/ and nothing else."""
    pool = Path(pool)
    if not pool.is_dir() or pool.is_symlink():
        raise ValueError("pool must be a real directory")
    if {p.name for p in pool.iterdir()} != {"tasks"}:
        raise ValueError("pool must contain only tasks/ (no sealed-eval, harness or results)")
    if {p.name for p in (pool / "tasks").iterdir()} != set(DEV_OSS):
        raise ValueError("pool tasks must be exactly the two Zeppelin DEV tasks")
    for item in pool.rglob("*"):
        if item.is_symlink():
            raise ValueError("linked pool entry refused")
        if FORBIDDEN_POOL_NAMES.search(item.name):
            raise ValueError("pool entry resembles evaluation or answer-key material")
    return True


def disposable_git(cmd, project, identity):
    """Do not let ambient Git routing/configuration escape disposable staging."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(identity, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    subprocess.run([cmd[0], "-c", "core.hooksPath=" + os.devnull, *cmd[1:]],
                   cwd=project, env=env, capture_output=True, check=True)


def reject_root_mismatch(evidence, rec, transcripts, events):
    """Do not accept a parentless fallback for a conflicting explicit root ID."""
    root = evidence.root_thread_of(events or [])
    directory = evidence.sessions_dir_for(rec, transcripts)
    rollouts = evidence.load_sessions(directory) if directory else []
    if root and len([r for r in rollouts if r.get("thread_id") == root and not r.get("parent_thread_id")]) != 1:
        raise ValueError("explicit transcript/rollout root identity mismatch")


def scrub_prompt(text):
    pattern = (r"(?i)\b(?:PR|pull\s+request|issue)\s*#?\s*\d+|/pull/\d+|"
               r"https?://|github\.com|\bprovenance\b|source\s*(?:of\s+scope|:)|"
               r"[\w./-]+\.(?:[cm]?[jt]sx?|html|java|py|vue|svelte)(?::\d+|#L\d+|\s+lines?\s+\d+)|"
               r"\b(?:source\s+)?lines?\s+\d+")
    return "\n".join(line for line in text.splitlines() if not re.search(pattern, line)).strip()


def scrub_runtime_prompt(text):
    origins = {}

    def remember(match):
        key = "__APP_ORIGIN_" + str(len(origins)) + "__"
        origins[key] = match.group(0)
        return key
    text = re.sub(r"http://(?:127\.0\.0\.1|localhost|host\.docker\.internal):\d+", remember, text)
    text = scrub_prompt(text)
    for key, origin in origins.items():
        text = text.replace(key, origin)
    return text


# ------------------------------------------------------------------ campaign layout and bindings

def iteration_dir(campaign, iteration):
    check_stage(iteration, "baseline" if iteration == 0 else "screening")
    return Path(campaign) / "iterations" / f"{iteration:02d}"


def stage_dir(campaign, iteration, stage):
    check_stage(iteration, stage)
    return iteration_dir(campaign, iteration) / stage


def batch_dir(directory, slot):
    if slot not in stage_slots("baseline", True) + stage_slots("screening"):
        raise ValueError("unregistered batch slot")
    return Path(directory) / "batches" / slot


def baseline_layer(campaign):
    return Path(campaign) / "baseline/THIN-RULES.md"


def require_headroom(campaign):
    """No candidate work before the iteration-0 gate has recorded HEADROOM."""
    path = iteration_dir(campaign, 0) / "headroom.json"
    if not path.exists() or read(path).get("verdict") != "HEADROOM":
        raise ValueError("the iteration-0 headroom gate must record HEADROOM before any candidate work")


def bindings(config, campaign):
    campaign = Path(campaign)
    oss = machinery()
    loop = Path(config["loop_runner"])
    pool, dists = Path(config["pool"]), Path(config["dists"])
    thin_protocol = read(THIN_EVAL_PROTOCOL)
    if thin_protocol["layer"]["prompt_line"] != D_LINE:
        raise ValueError("D prompt line differs from the thin-eval preregistration")
    return dict(protocol=sha(BENCH / "protocol.json"), readme=sha(BENCH / "README.md"),
                tests=sha(ROOT / "scripts/ci/test-generator-loop-thin-v1.py"), scripts=bound_scripts(), thin_eval_protocol=sha(THIN_EVAL_PROTOCOL), config=config,
                layer_v0=sha(LAYER_V0), baseline_layer=sha(baseline_layer(campaign)),
                library={n: sha(REFERENCE_DIR / n) for n in REFERENCE_FILES},
                model_selection=sha(campaign / "model-selection.json"), thin_eval_gate=sha(campaign / "thin-eval-gate.json"),
                runtime_protocol=sha(oss.PROTOCOL), scanner=tree(oss.engine.REV_SKILL),
                loop_runner=sha(loop), loop_adapter=sha(loop.parent / "generator_codex_loop_adapter.py"),
                proxy=sha(loop.parents[2] / "benchmarks/generator-loop-v1/harness/serve.mjs"),
                synthetic={c: dict(case=tree(oss.engine.CASES / c), truth=sha(oss.engine.TRUTH / (c + ".json"))) for c in DEV_SYNTH},
                oss_tasks=oss.task_bindings(pool, DEV_OSS), oss_dists=oss.dist_bindings(dists, DEV_OSS),
                fixture_lock=sha(ROOT / "scripts/evals/fixtures/package-lock.json"),
                source_lock=sha(Path(config["source"]) / "package-lock.json"),
                plans=tree(campaign / "plans"),
                schedules={f"{i}/{s}": schedule(i, s, config["aa3"]) for i in range(MAX_ITERATIONS + 1)
                           for s in (("baseline",) if i == 0 else ("screening", "confirmation"))})


def model_of(campaign):
    selection = read(Path(campaign) / "model-selection.json")
    if selection.get("rule_version") != SELECTION_RULE or not selection.get("chosen"):
        raise ValueError("model selection record missing or from another rule")
    return selection["chosen"]


def prepare(args):
    campaign = external(args.campaign)
    if docker_root() not in campaign.parents:
        raise ValueError("the campaign root must be under the home directory so container bind mounts work")
    if campaign.exists():
        raise ValueError("prepare needs a new campaign root")
    required = ("pool", "loop_runner", "dists", "source", "model_selection", "thin_eval_gate")
    if any(getattr(args, key) is None for key in required):
        raise ValueError("prepare requires explicit DEV input locations, the model selection and the thin-eval gate")
    check_pool(args.pool)
    selection, gate = read(args.model_selection), read(args.thin_eval_gate)
    if selection.get("rule_version") != SELECTION_RULE or gate.get("model") != selection.get("chosen"):
        raise ValueError("model selection and thin-eval gate must refer to the same chosen model")
    if gate.get("verdict") != "HEADROOM":
        raise ValueError("sequencing rule: the loop starts only after thin-eval-v1 shows headroom (" + str(gate.get("verdict")) + ")")
    if not THIN_EVAL_FREEZE.is_file() or read(THIN_EVAL_FREEZE)["bindings"]["files"].get(
            LAYER_V0.relative_to(ROOT).as_posix()) != sha(LAYER_V0):
        raise ValueError("thin-eval freeze must exist and bind the same layer v0 bytes")
    inputs = gate.get("inputs") or {}
    if (inputs.get("thin_eval_freeze_sha256") != sha(THIN_EVAL_FREEZE) or not inputs.get("results_sha256")
            or (selection.get("inputs") or {}).get(selection["chosen"]) != inputs["results_sha256"]):
        raise ValueError("the thin-eval gate record must bind the thin-eval freeze and the same results the model selection read")
    parse_layer(LAYER_V0.read_text(), layer_header(LAYER_V0.read_text()))
    config = {key: str(Path(getattr(args, key)).resolve()) for key in ("pool", "loop_runner", "dists", "source")}
    args.guard_profile = args.guard_profile or DEFAULT_GUARD_PROFILE
    if args.guard_profile not in GUARD_PROFILES:
        raise ValueError("prepare needs a registered --guard-profile (strict or noise-tolerant); it is bound at freeze before any data")
    config.update(model=selection["chosen"], campaign_root=str(campaign), aa3=bool(args.aa3), library=bool(args.library),
                  guard_profile=args.guard_profile, include_zeppelin=bool(args.include_zeppelin),
                  campaign_id=ID + "-" + hashlib.sha256(str(campaign).encode()).hexdigest()[:12])
    campaign.mkdir(mode=0o700, parents=True)
    (campaign / "baseline").mkdir()
    shutil.copyfile(LAYER_V0, baseline_layer(campaign))
    if args.library:
        (campaign / "library").mkdir()
        for name in REFERENCE_FILES:
            shutil.copyfile(REFERENCE_DIR / name, campaign / "library" / name)
    shutil.copyfile(args.model_selection, campaign / "model-selection.json")
    shutil.copyfile(args.thin_eval_gate, campaign / "thin-eval-gate.json")
    oss = machinery()
    (campaign / "plans").mkdir()
    for case in DEV:
        if case in DEV_SYNTH:
            scope = oss.engine.load_truth(case)["task"]
        else:
            scope = (Path(config["pool"]) / "tasks" / case / "scope.md").read_text()
        scope = scrub_prompt(oss.scrub_scope(scope))
        (campaign / "plans" / (case + ".md")).write_text(oss.approved_plan(case, scope))
    write(campaign / "config.json", config)
    write(campaign / "prepared-bindings.json", bindings(config, campaign))


def validate_independent_review(campaign):
    """No freeze without a recorded independent PASS review bound to the exact reviewed bytes."""
    record = read(Path(campaign) / "independent-review.json")
    reviewer, builder = record.get("reviewer") or {}, record.get("builder") or {}
    reviewed = {"runner": sha(Path(__file__)), "protocol": sha(BENCH / "protocol.json"),
                "readme": sha(BENCH / "README.md"), "tests": sha(ROOT / "scripts/ci/test-generator-loop-thin-v1.py")}
    if (record.get("verdict") != "PASS" or record.get("open_material_findings") != 0
            or not reviewer.get("id") or not reviewer.get("model") or not builder.get("id")
            or reviewer.get("id") == builder.get("id") or reviewer.get("model") == builder.get("model")
            or record.get("reviewed_sha256") != reviewed):
        raise ValueError("an independent PASS review of the exact runner, protocol, README and tests is required before freeze")
    return record


def require_live(args):
    if not args.allow_live:
        raise ValueError(args.command + " requires --allow-live")
    campaign = external(args.campaign)
    config = read(campaign / "config.json")
    if config.get("campaign_root") != str(campaign):
        raise ValueError("campaign differs from its single canonical root")
    if (campaign / "BLOCKED.json").exists():
        raise ValueError("campaign is BLOCKED; a successor preregistration is required")
    if model_of(campaign) != config["model"]:
        raise ValueError("configured model differs from the outcome-blind selection")
    now = bindings(config, campaign)
    if now != read(campaign / "prepared-bindings.json"):
        raise ValueError("prepared inputs drifted; stop this protocol")
    if args.command == "freeze":
        validate_independent_review(campaign)
    if args.command not in ("freeze", "calibrate") and now != read(campaign / "freeze.json")["bindings"]:
        raise ValueError("freeze drift")
    if args.command not in ("freeze", "calibrate"):
        validate_independent_review(campaign)
        if read(campaign / "freeze.json")["independent_review_sha256"] != sha(campaign / "independent-review.json"):
            raise ValueError("independent review record drift")
    if args.command != "calibrate":
        validate_calibration(campaign, config)
        if args.command != "freeze" and read(campaign / "freeze.json")["calibration_sha256"] != sha(campaign / "calibration/_scorer-calibration.json"):
            raise ValueError("frozen calibration drift")
    return campaign, config, now


def verify_campaign(campaign):
    config = read(campaign / "config.json")
    if config.get("campaign_root") != str(campaign.resolve()):
        raise ValueError("campaign canonical root drift")
    if bindings(config, campaign) != read(campaign / "freeze.json")["bindings"]:
        raise ValueError("campaign input drift; stop this protocol")
    validate_calibration(campaign, config)
    if read(campaign / "freeze.json")["calibration_sha256"] != sha(campaign / "calibration/_scorer-calibration.json"):
        raise ValueError("calibration drift")


CALIBRATION_KIND_SYNTHETIC = "offline-mutant-applicability"


def validate_calibration(campaign, config):
    """Second-review F2: the calibration must cover the tasks this campaign actually uses (the active mode's DEV list), every
    record must pass, and the synthetic records must be the offline applicability kind. Previously the two Zeppelin tasks were
    required even in the default synthetic-only mode, where no Zeppelin cell is ever scored."""
    data = read(campaign / "calibration/_scorer-calibration.json")
    tasks = data.get("tasks") or {}
    if (data.get("status") != "PASS" or data.get("campaign_id") != config["campaign_id"]
            or data.get("bindings") != {"prepared_sha256": sha(campaign / "prepared-bindings.json")}
            or set(tasks) != set(DEV) or data.get("model_calls") != 0
            or any(not isinstance(r, dict) or r.get("pass") is not True for r in tasks.values())
            or any(tasks[t].get("kind") != CALIBRATION_KIND_SYNTHETIC for t in DEV_SYNTH)):
        raise ValueError("matching DEV calibration of exactly the active tasks required")


def synthetic_calibration(oss, cases=None):
    """Offline, model-free scorer calibration of the synthetic dev tasks. The synthetic tasks ship no reference spec, so a
    reference run (as the Zeppelin calibration does) is not available. This checks the part of the scorer that needs no
    browser: every registered fault edit applies exactly once to the case application, every fault yields a distinct mutant that
    differs from the clean app, and the refactor edits apply and change it. It cannot show that a good spec kills each mutant;
    that remains a live check."""
    records = {}
    for case in (cases or DEV_SYNTH):
        truth = oss.engine.load_truth(case)
        case_dir = oss.engine.CASES / case
        clean = (case_dir / "app.mjs").read_text()
        mutants, problems = {}, []
        with tempfile.TemporaryDirectory(prefix="loop-thin-calibration-") as tmp:
            app = Path(tmp) / "app.mjs"
            for fault in truth["faults"]:
                app.write_text(clean)
                try:
                    oss.engine.apply_edits(app, fault.get("edits") or [fault], False)
                except RuntimeError:
                    problems.append("fault edit does not apply exactly once")
                    continue
                mutants[fault["id"]] = sha_text(app.read_text())
            app.write_text(clean)
            try:
                oss.engine.apply_edits(app, truth["refactor"], True)
            except RuntimeError:
                problems.append("refactor edit does not apply")
            refactor_changes = app.read_text() != clean
        clean_hash = sha_text(clean)
        ok = (not problems and bool(truth["faults"]) and len(mutants) == len(truth["faults"])
              and len(set(mutants.values())) == len(mutants) and clean_hash not in mutants.values() and refactor_changes)
        records[case] = dict(**{"pass": bool(ok)}, kind=CALIBRATION_KIND_SYNTHETIC, faults=len(truth["faults"]),
                             distinct_mutants=len(set(mutants.values())), refactor_edits=len(truth["refactor"]),
                             case_sha256=sha_text(json.dumps(tree(case_dir), sort_keys=True)),
                             truth_sha256=sha(oss.engine.TRUTH / (case + ".json")), live_reference_run=False)
    return records


# ------------------------------------------------------------------ live context (unexercised offline)

def runtime_args(config):
    fields = {k: config[k] for k in ("pool", "dists", "source", "loop_runner", "campaign_id")}
    return argparse.Namespace(**fields, lock_file=machinery().SHARED_LOCK)


def d_command(original, engine_arg, work, private, name, model, arm=None, sessions=None):
    """The A argv plus exactly one nested read-only rules mount (same shape as thin-eval arm D)."""
    argv = original(engine_arg, work, private, name, model, arm, sessions)
    index = argv.index(engine_arg.CODEX_CONTAINER_IMAGE)
    return argv[:index] + ["--mount", f"type=bind,src={Path(work) / 'skill/thin-rules'},dst=/work/skill/thin-rules,readonly"] + argv[index:]


def stage_layer(work, layer_path):
    target = Path(work) / "skill/thin-rules/SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(layer_path, target)
    target.chmod(0o444)
    return target


# ------------------------------------------------------------------ generation-phase repairs (F3 and F5)
# These functions are line-for-line the thin-eval-v1 repairs (an offline test compares their syntax trees with the thin-eval
# runner; only the name `integration` resolves, lazily, to this campaign's single machinery stack instead of the thin
# integration module). F3: the MCP session explores on its own port, so the parent's single test run starts a fresh
# application process (reuseExistingServer false, as in scoring) and never reuses a server that exploration mutated; the
# synthetic dev tasks are all stateful. F5: .playwright-mcp/ snapshots and the node_modules link are git-excluded and never
# counted as out-of-scope writes. They apply to the synthetic cells (arms A and D alike). The Zeppelin cells use one shared
# external proxy with per-cell note namespaces and have no per-session port to split: they receive only the F5 repair.
A = ARM_A
EXPLORE_ENV = "GEN_EXPLORE_PORT"
EXPLORE_PORT_OFFSET = 10000
MCP_ARTIFACT_DIR = ".playwright-mcp"
GIT_EXCLUDES = ("node_modules", MCP_ARTIFACT_DIR + "/")
EXPLORE_MARKER = re.compile(r'const APP_PORT = process\.env\.' + EXPLORE_ENV + r' \?\? "(\d+)";')
SPLIT_ROLE = {"active": False}


class _Integration:
    """Resolve `integration.<name>` against the campaign's one machinery stack (the OSS runner's Codex v4 module)."""

    def __getattr__(self, name):
        return getattr(machinery().v2, name)


integration = _Integration()


def split_config_text(scoring_text, port):
    """The staged scoring config (port substituted) with a role-dependent port; refuses any config that is not the exact frozen shape."""
    base, health = f'"http://127.0.0.1:{port}"', f'"http://127.0.0.1:{port}/health"'
    if (scoring_text.count(integration.SCORING_REUSE) != 1 or "reuseExistingServer: true" in scoring_text
            or scoring_text.count(base) != 1 or scoring_text.count(health) != 1
            or scoring_text.count("export default defineConfig(") != 1 or EXPLORE_ENV in scoring_text):
        raise ValueError("case config is not the exact frozen single-port shape")
    text = scoring_text.replace(base, "`http://127.0.0.1:${APP_PORT}`").replace(health, "`http://127.0.0.1:${APP_PORT}/health`")
    text = text.replace(integration.SCORING_REUSE, f"reuseExistingServer: process.env.{EXPLORE_ENV} !== undefined")
    header = f'const APP_PORT = process.env.{EXPLORE_ENV} ?? "{port}";\n\n'
    return text.replace("export default defineConfig(", header + "export default defineConfig(", 1)


def split_app_text(app_text, port):
    literal = f"const PORT = {port};"
    if app_text.count(literal) != 1 or EXPLORE_ENV in app_text:
        raise ValueError("case app is not the exact frozen single-port shape")
    return app_text.replace(literal, f"const PORT = Number(process.env.{EXPLORE_ENV} ?? {port});")


def make_split_stage(log):
    """engine.stage replacement for MCP-arm generation only; `log` collects the per-stage evidence for the cell record."""
    def stage(case_dir, port, work, git):
        project = integration._REAL_STAGE(case_dir, port, work, git)
        config, app = project / "playwright.config.mjs", project / "app.mjs"
        scoring_text, app_text = config.read_text(), app.read_text()
        config.write_text(split_config_text(scoring_text, port))
        app.write_text(split_app_text(app_text, port))
        norm = lambda text: integration.orig.sha(text.replace(str(port), "__PORT__"))
        entry = {"case": Path(case_dir).name, "reuse_existing_server": False, "server_isolation": "split-ports",
                 "config_sha256_port_normalized": norm(config.read_text()),
                 "scoring_config_sha256_port_normalized": norm(scoring_text)}
        integration.GENERATION["staged"].append(entry)
        log.append(dict(entry, app_sha256_port_normalized=norm(app.read_text()),
                        scoring_app_sha256_port_normalized=norm(app_text), explore_port=port + EXPLORE_PORT_OFFSET, test_run_port=port))
        return project
    return stage


def explore_port_of(work):
    text = (Path(work) / "project" / "playwright.config.mjs").read_text()
    found = EXPLORE_MARKER.search(text)
    if found is None:
        raise ValueError("generation config lacks the split-port marker; refusing to start the MCP session")
    return int(found.group(1)) + EXPLORE_PORT_OFFSET


def explore_command(original, engine_arg, work, private, name, model, arm=None, sessions=None):
    """A-arm argv plus exactly one MCP-server-only environment entry: the exploration port. Shell commands never receive it."""
    argv = original(engine_arg, work, private, name, model, arm, sessions)
    if arm != A:  # the harness-check arm has no application server
        return argv
    if argv[-1] != "-":
        raise ValueError("unexpected adapter argv tail")
    return argv[:-1] + ["-c", f'mcp_servers.playwright-test.env.{EXPLORE_ENV}="{explore_port_of(work)}"'] + argv[-1:]


def excluding_baseline(original):
    """Write .git/info/exclude before the baseline commit so harness-owned paths are neither tracked nor listed by git status."""
    def baseline(project, case):
        info = Path(project) / ".git" / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "exclude").write_text("# harness-owned paths, never part of the deliverable\n" + "".join(x + "\n" for x in GIT_EXCLUDES))
        return original(project, case)
    return baseline


def mcp_artifact_listing(project):
    root = Path(project) / MCP_ARTIFACT_DIR
    if root.is_symlink() or not root.is_dir():
        return []
    return sorted(path.relative_to(project).as_posix() for path in root.rglob("*") if path.is_symlink() or not path.is_dir())


def scoped_collector(original):
    """Deliverable collection with .playwright-mcp/ outside the out-of-scope write check, kept as separate fidelity evidence."""
    def collect(project, destination):
        out = original(project, destination)
        kept = [w for w in out.get("out_of_scope_writes") or [] if not w.startswith(MCP_ARTIFACT_DIR + "/")]
        return dict(out, out_of_scope_writes=kept, mcp_artifact_writes=mcp_artifact_listing(project))
    return collect


@contextlib.contextmanager
def split_generation_staging(oss, log):
    """The v4 generation staging with the split-port stage in place of its single-port reuse flip; always restored."""
    saved = oss.v2._generation_stage
    oss.v2._generation_stage = make_split_stage(log)
    try:
        with oss.v2.generation_staging() as staged:
            yield staged
    finally:
        oss.v2._generation_stage = saved


def split_generation_summary(oss, staged, split_log):
    """The cell's generation_config: the v4 summary plus the same split-port evidence thin-eval-v1 records for A and D."""
    return dict(oss.v2.generation_summary(list(staged)), server_isolation="split-ports", explore_env=EXPLORE_ENV,
                explore_port_offset=EXPLORE_PORT_OFFSET, explore_role_reuse_existing_server=True,
                test_run_reuse_existing_server=False, git_excludes=list(GIT_EXCLUDES),
                app_sha256_port_normalized=sorted({s["app_sha256_port_normalized"] for s in split_log}),
                scoring_app_sha256_port_normalized=sorted({s["scoring_app_sha256_port_normalized"] for s in split_log}))


def check_generation_isolation(rec):
    """A synthetic cell is only valid when it was generated with split ports and a fresh test-run server."""
    config = rec.get("generation_config") or {}
    if (config.get("server_isolation") != "split-ports" or config.get("test_run_reuse_existing_server") is not False
            or config.get("explore_role_reuse_existing_server") is not True
            or list(config.get("git_excludes") or []) != list(GIT_EXCLUDES)):
        raise ValueError("synthetic cell lacks the split-port generation repair")


@contextlib.contextmanager
def split_role():
    """Mark the current generation as a synthetic split-port cell so the exploration port reaches the MCP server."""
    SPLIT_ROLE["active"] = True
    try:
        yield
    finally:
        SPLIT_ROLE["active"] = False


@contextlib.contextmanager
def live_context(campaign, config, layer_path=None, integrity=None):
    """Patch only inside an authorized live command: scrubbed plans, then (for D) the layer mount and D line."""
    oss = machinery()
    compat, engine = oss.compat, oss.engine
    p = oss.protocol()
    saved = (oss.scrub_scope, oss.approved_plan, engine.FRAME, compat.command, dict(compat.ARM_LINES), engine.call_model)
    model = config["model"]
    try:
        oss.scrub_scope = scrub_prompt

        def plan(case, scope):
            assert_dev(case)
            return (Path(campaign) / "plans" / (case + ".md")).read_text()
        oss.approved_plan = plan
        with oss.codex_context(Path(campaign) / "runtime", p):
            real = engine.call_model
            compat.ARM_LINES[PROBE_ARM] = ""
            a_line = compat.ARM_LINES[oss.ARM_A]
            treated = layer_path is not None
            original_command = compat.command

            def layered(*a, **kw):
                """The exploration port reaches the MCP server of synthetic cells only (F3); Zeppelin has no split port."""
                if SPLIT_ROLE["active"]:
                    return explore_command(original_command, *a, **kw)
                return original_command(*a, **kw)
            compat.command = layered
            if treated:
                compat.ARM_LINES[oss.ARM_A] = a_line + "\n" + D_LINE
                compat.command = lambda *a, **kw: d_command(layered, *a, **kw)

            def call(project, work, arm, task, model_id, timeout, budget):
                if arm not in (oss.ARM_A, PROBE_ARM) or model_id != model:
                    raise ValueError("unregistered treatment/model")
                if arm == PROBE_ARM:  # a bare availability question: no frame, no generator instructions, no layer
                    frame = engine.FRAME
                    engine.FRAME = "{task}"
                    try:
                        return real(project, work, arm, task, model_id, timeout, budget)
                    finally:
                        engine.FRAME = frame
                prompt = scrub_runtime_prompt(engine.FRAME.format(task=task))
                suffix = compat.ARM_LINES[oss.ARM_A]
                prompts = Path(campaign) / "prompts"
                prompts.mkdir(exist_ok=True)
                name = hashlib.sha256((prompt + suffix).encode()).hexdigest() + ".txt"
                if not (prompts / name).exists():
                    (prompts / name).write_text(prompt + suffix)
                staged = before = None
                if treated:
                    staged = stage_layer(work, layer_path)
                    before = sha(staged)
                frame = engine.FRAME
                engine.FRAME = "{task}"
                try:
                    result = real(project, work, arm, prompt, model_id, timeout, budget)
                finally:
                    engine.FRAME = frame
                if treated:
                    after = sha(staged)
                    if integrity is not None:
                        integrity.append(dict(before=before, after=after, read_only_mount=True))
                    if before != after or before != sha(layer_path):
                        raise ValueError("staged thin layer drift")
                return result
            engine.call_model = call
            yield oss
    finally:
        oss.scrub_scope, oss.approved_plan, engine.FRAME, compat.command = saved[0], saved[1], saved[2], saved[3]
        engine.call_model = saved[5]
        compat.ARM_LINES.clear()
        compat.ARM_LINES.update(saved[4])


def synthetic_generate(item, args, campaign, directory, oss, config, integrity):
    case = item["case"]
    if case not in DEV_SYNTH:
        raise ValueError("unregistered synthetic cell")
    serial = cell_serial(item["iteration"], item["stage"], item["slot"], item["repetition"])
    oss_item = dict(item, arm=oss.ARM_A, repetition=serial)
    # The record carries the OSS arm so the shared evidence functions (cell_extras and the fidelity classifier) can read it.
    rec = dict(item, arm=oss.ARM_A, call_id=oss.v2.v1.call_id_of(oss_item), attempts=[])
    oss.engine.wait_for_load(rec)
    v2 = oss.v2
    for attempt in (1, 2):
        split_log = []
        with tempfile.TemporaryDirectory(prefix="loop-thin-cell-") as tmp:
            work = Path(tmp).resolve()
            with split_generation_staging(oss, split_log) as staged:
                project = oss.engine.stage(oss.engine.CASES / case, args.ports.take(), work, git=False)
                rec["generation_config"] = split_generation_summary(oss, staged, split_log)
            setup = v2.v1._init_codex(project)
            rec["setup"] = setup
            if setup["status"] != "ready":
                result = dict(infrastructure_error=True, unavailable=setup.get("reason"), elapsed_ms=0)
            else:
                def baseline(path, case_name):
                    (path / "specs").mkdir(exist_ok=True)
                    (path / "specs/plan.md").write_text((campaign / "plans" / (case_name + ".md")).read_text())
                    (path / "tests").mkdir(exist_ok=True)
                    (path / "tests/seed.spec.ts").write_text(v2.orig.SEED)
                    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "baseline"]):
                        disposable_git(cmd, path, oss.engine.GIT_ENV)
                excluding_baseline(baseline)(project, case)
                oss.engine.CODEX_TRANSCRIPTS = directory / "final-transcripts"
                task = scrub_prompt(oss.engine.load_truth(case)["task"]) + v2.orig.PLAN_LINE
                with split_role():
                    result = oss.engine.call_model(project, work, oss.ARM_A, task, config["model"], TASK_TIMEOUT_S, None)
                if not result.get("infrastructure_error"):
                    rec.update(scoped_collector(oss.engine.collect_deliverable)(project, directory / "final-artifacts" / rec["call_id"]))
            result["attempt"] = attempt
            rec["attempts"].append(result)
            rec.update({k: v for k, v in result.items() if k != "attempt"})
        if not result.get("infrastructure_error") or result.get("fatal_infrastructure"):
            break
    rec.update(deliverable=bool(rec.get("spec_files")), infrastructure_error="spec_files" not in rec)
    rec["layer_integrity"] = list(integrity)
    return rec


def zeppelin_generate(item, args, rt, config, directory, oss, integrity):
    """Zeppelin cells use the shared external proxy and per-cell note namespaces, so only the F5 repair applies:
    harness-owned paths are git-excluded before the baseline commit and kept out of the out-of-scope write check."""
    serial = cell_serial(item["iteration"], item["stage"], item["slot"], item["repetition"])
    oss_item = dict(item, arm=oss.ARM_A, repetition=serial)
    loop = rt._configured_loop()
    original_commit, original_collect = loop.commit_baseline, oss.engine.collect_deliverable

    def commit(project, *rest, **named):
        return excluding_baseline(lambda path, _case: original_commit(path, *rest, **named))(project, None)
    loop.commit_baseline, oss.engine.collect_deliverable = commit, scoped_collector(original_collect)
    try:
        rec = oss.generate(oss_item, args, rt, config["model"], directory, list(DEV_OSS))
    finally:
        loop.commit_baseline, oss.engine.collect_deliverable = original_commit, original_collect
    rec["generation_config"] = dict(rec.get("generation_config") or {}, server_isolation="shared-proxy-note-namespace",
                                    split_port_repair=False, git_excludes=list(GIT_EXCLUDES))
    rec.update(slot=item["slot"], repetition=item["repetition"], treatment=item["treatment"],
               oss_serial=serial, layer_integrity=list(integrity))
    return rec


RATE_LIMIT = re.compile(r"(?i)rate[ _-]?limit|usage[ _-]?limit|too many requests|\b429\b|quota|limit (?:reached|exceeded)|weekly limit")


def probe_once(campaign, config, directory):
    with live_context(campaign, config) as active, tempfile.TemporaryDirectory(prefix="loop-thin-probe-") as tmp:
        work = Path(tmp).resolve()
        project = work / "project"
        project.mkdir()
        (project / "node_modules").symlink_to(active.engine.FIXTURE_MODULES)
        for cmd in (["git", "init", "-q"], ["git", "commit", "-q", "--allow-empty", "-m", "baseline"]):
            disposable_git(cmd, project, active.engine.GIT_ENV)
        active.engine.CODEX_TRANSCRIPTS = directory / "transcripts"
        return active.engine.call_model(project, work, PROBE_ARM, "Reply with the single word ok and nothing else.",
                                        config["model"], 300, None)


def probe(campaign, config):
    """One-token availability probe, called inside the machine-wide lock; one retry after a failure. A rate or usage limit
    is transient: it is recorded and refuses the batch without BLOCKING the campaign. Any other failure after the retry ends
    the loop as BLOCKED; there is never a model switch."""
    directory = Path(campaign) / "probe"
    failures = []
    for attempt in (1, 2):
        ordinal = len(list(directory.glob("*.json"))) + 1 if directory.exists() else 1
        result = probe_once(campaign, config, directory)
        error = result.get("error")
        limited = bool(result.get("infrastructure_error")) and bool(RATE_LIMIT.search(str(error or "")))
        status = "AVAILABLE" if not result.get("infrastructure_error") else ("RATE_LIMITED" if limited else "FAILED")
        write(directory / f"{ordinal:03d}.json",
              dict(status=status, attempt=attempt, model=config["model"], error=error, elapsed_ms=result.get("elapsed_ms")))
        if status == "AVAILABLE":
            return status
        failures.append(status)
        if limited:
            break  # a retry cannot help before the limit resets
    if "RATE_LIMITED" in failures:
        raise ValueError("model rate limited: the campaign is not blocked; rerun after the limit resets")
    write(Path(campaign) / "BLOCKED.json", dict(reason="availability probe failed twice", error=error, attempts=len(failures)))
    raise ValueError("model unavailable: campaign BLOCKED (never switch models)")


# ------------------------------------------------------------------ batch generation, scoring, analysis

def artifact_tree(path):
    path = Path(path)
    if not path.exists():
        return {}
    if path.is_symlink():
        raise ValueError("linked generated root")
    result = {}
    for f in sorted(path.rglob("*")):
        if f.is_symlink():
            raise ValueError("linked generated artifact")
        if f.is_file():
            result[f.relative_to(path).as_posix()] = sha(f)
    return result


def generation_inputs(target):
    return {name: artifact_tree(Path(target) / name) for name in ("final-artifacts", "final-transcripts", "codex-sessions")}


def verify_report(target):
    report = read(target / "final.json")
    if report["generation_inputs"] != generation_inputs(target):
        raise ValueError("generated spec, transcript or session drift")
    generated = read(target.parents[1] / "generated.json")
    if generated["reports"].get(target.name) != sha(target / "final.json"):
        raise ValueError("generated report changed")
    return report


def void_marker(directory):
    return any((Path(directory) / n).exists() for n in ("VOID.json", "SCORE-VOID.json", "POST-VOID.json"))


def verified_result(directory, slot):
    if void_marker(directory):
        raise ValueError("void batch cannot enter a decision or noise estimate")
    target = batch_dir(directory, slot)
    result = read(target / "results.json")
    if read(directory / "analyzed.json")[slot] != sha(target / "results.json"):
        raise ValueError("analyzed result drift")
    report = verify_report(target)
    score_path = target / result["score_file"]
    treatment = "A" if slot == "ref-A" else "D"
    if (result["report_sha256"] != sha(target / "final.json") or result["scores_sha256"] != sha(score_path)
            or result["layer_sha256"] != report["layer_sha256"] or result["summary"] != summarize(result["cells"], treatment)):
        raise ValueError("result provenance mismatch")
    return result


def previous_decisions(campaign):
    decisions = []
    for i in range(1, MAX_ITERATIONS + 1):
        path = iteration_dir(campaign, i) / "decision.json"
        if not path.exists():
            break
        decisions.append(read(path))
    return decisions


def incumbent_layer(campaign, iteration):
    """Path of the layer the iteration starts from; adopted candidates are re-verified by digest."""
    decisions = previous_decisions(campaign)
    if len(decisions) != iteration - 1:
        raise ValueError("iteration order refuses further work")
    result = baseline_layer(campaign)
    for i, decision in enumerate(decisions, 1):
        if decision["verdict"] in ADOPTIONS:
            result = iteration_dir(campaign, i) / "candidate/THIN-RULES.md"
            if sha(result) != decision["candidate_layer_sha256"]:
                raise ValueError("adopted incumbent drift")
    return result


class InfrastructureVoid(ValueError):
    """A batch stopped for a reason independent of any outcome (an unavailable or failed harness), not because of a result."""


BATCH_FILES = ("final.json", "results.json", "scores.json", "adjudicated-scores.json")


def cell_records(directory):
    """Per-cell generation records of a stage directory, by relative name: the only batch content the retry path touches."""
    found = {}
    for slot_dir in sorted((Path(directory) / "batches").glob("*")) if (Path(directory) / "batches").is_dir() else []:
        for f in sorted(slot_dir.glob("*.json")):
            if f.name not in BATCH_FILES:
                found[slot_dir.name + "/" + f.name] = sha(f)
    return found


def stage_cells_spent(directory):
    """Second-review F3: cells charged to the generation budget by one stage directory, void or not. A completed stage costs its
    reports; a void stage costs the cells it started (the void marker records them) and, when that count is unknown, its whole
    schedule; a stage that started and left no verdict is charged its whole schedule."""
    directory = Path(directory)
    if (directory / "generated.json").exists():
        return len(read(directory / "generated.json")["reports"]) * batch_cells()
    if (directory / "started.json").exists():
        scheduled = read(directory / "started.json").get("schedule")
        if (directory / "VOID.json").exists():
            started = read(directory / "VOID.json").get("cells_started")
            if type(started) is int and started >= 0 and (scheduled is None or started <= len(scheduled)):
                return started
        if scheduled is not None:
            return len(scheduled)
    return 0


def retry_ledger(campaign):
    ledger = Path(campaign) / "retries"
    return [read(f) for f in sorted(ledger.glob("*.json"))] if ledger.is_dir() else []


def iteration_state(campaign):
    decisions = previous_decisions(campaign)
    base = iteration_dir(campaign, 0)
    config = read(Path(campaign) / "config.json")
    spent = 0
    for i in range(0, MAX_ITERATIONS + 1):
        for s in (("baseline",) if i == 0 else ("screening", "confirmation")):
            spent += stage_cells_spent(stage_dir(campaign, i, s))
        archive = iteration_dir(campaign, i) / "void"
        for voided in sorted(archive.glob("*")) if archive.is_dir() else []:
            spent += stage_cells_spent(voided)
    draws = sum(len(list((iteration_dir(campaign, i) / "draws").glob("d*"))) for i in range(1, MAX_ITERATIONS + 1)
                if (iteration_dir(campaign, i) / "draws").exists())
    headroom = (base / "headroom.json")
    verdict = read(headroom)["verdict"] if headroom.exists() else None
    packet_stop = any((iteration_dir(campaign, i) / "no-headroom.json").exists() for i in range(1, MAX_ITERATIONS + 1))
    return dict(decisions=decisions, cells_spent=spent, budget=budget_cells(config["aa3"]), draws_spent=draws,
                blocked=(Path(campaign) / "BLOCKED.json").exists(),
                no_headroom=verdict == "NO_HEADROOM" or packet_stop, layer_not_read=verdict == "LAYER_NOT_READ",
                low_fidelity=verdict == "LOW_FIDELITY")


def run_stage(args, campaign, config):
    iteration, stage = args.iteration, args.stage or ("baseline" if args.iteration == 0 else "screening")
    directory = stage_dir(campaign, iteration, stage)
    if (directory / "VOID.json").exists():
        raise ValueError("this stage is void: retry-void (bounded, infrastructure only) or stop; a void stage is never rerun in place")
    state = iteration_state(campaign)
    lock = None
    if iteration == 0:
        layers = {slot: None if slot == "ref-A" else baseline_layer(campaign) for slot in stage_slots("baseline", config["aa3"])}
    else:
        require_headroom(campaign)
        if stop_reason(state["decisions"], state):
            raise ValueError("stop rule refuses further work: " + stop_reason(state["decisions"], state))
        if state["cells_spent"] + 2 * batch_cells() > state["budget"]:
            raise ValueError("generation budget would be exceeded")
        if stage == "confirmation" and read(iteration_dir(campaign, iteration) / "screening/decision.json")["verdict"] not in ADOPTIONS:
            raise ValueError("confirmation runs only after an ADOPT screening verdict")
        before = incumbent_layer(campaign, iteration)
        lock = validate_candidate(iteration_dir(campaign, iteration), before, campaign)
        layers = {"incumbent": before, "candidate": iteration_dir(campaign, iteration) / "candidate/THIN-RULES.md"}
    rows = schedule(iteration, stage, config["aa3"])
    reports = {slot: {"model": config["model"], "runs": []} for slot in layers}
    oss = machinery()
    args.ports = oss.engine.Ports(23000)
    rt = oss.runtime(runtime_args(config))
    progress = dict(started=0)
    with rt.campaign():  # the machine-wide lock is held for the whole batch; nothing else runs on the host
        probe(campaign, config)
        write(directory / "started.json", dict(schedule=rows, freeze_sha256=sha(campaign / "freeze.json"),
              layers={k: (sha(v) if v else None) for k, v in layers.items()}, candidate=lock))
        try:
            for row in rows:
                slot = row["slot"]
                progress["started"] += 1  # the cell in flight is charged to the budget even if it never finishes
                target = batch_dir(directory, slot)
                target.mkdir(parents=True, exist_ok=True)
                integrity = []
                with live_context(campaign, config, layers[slot], integrity) as active:
                    if row["case"] in OSS_ACTIVE:
                        rec = zeppelin_generate(row, runtime_args(config), rt, config, target, active, integrity)
                    else:
                        rec = synthetic_generate(row, args, campaign, target, active, config, integrity)
                rec["slot"], rec["treatment"] = slot, row["treatment"]
                reports[slot]["runs"].append(rec)
                write(target / (rec["call_id"] + ".json"), rec)
                if rec.get("infrastructure_error") or rec.get("fatal_infrastructure"):
                    raise InfrastructureVoid("infrastructure-invalid batch")
                if rec.get("note_isolation_violations"):
                    raise ValueError("Zeppelin namespace violation makes batch void")
                if bindings(config, campaign) != read(campaign / "freeze.json")["bindings"]:
                    raise ValueError("bound input drift")
                if lock and validate_candidate(iteration_dir(campaign, iteration), layers["incumbent"], campaign) != lock:
                    raise ValueError("candidate changed during run")
            for slot, report in reports.items():
                path = layers[slot]
                report.update(layer_sha256=sha(path) if path else None, layer_bytes=path.stat().st_size if path else 0,
                              treatment="A" if path is None else "D", freeze_sha256=sha(campaign / "freeze.json"),
                              generation_inputs=generation_inputs(batch_dir(directory, slot)))
                write(batch_dir(directory, slot) / "final.json", report)
            write(directory / "generated.json", {"status": "COMPLETED", "reports":
                  {slot: sha(batch_dir(directory, slot) / "final.json") for slot in reports}})
        except BaseException as exc:
            write(directory / "VOID.json", {"error": type(exc).__name__, "message": str(exc),
                  "retryable": isinstance(exc, InfrastructureVoid), "cells_started": progress["started"],
                  "records": cell_records(directory)})
            raise


def retry_void(campaign, iteration, stage):
    """Second-review F3: the clean resume path after an infrastructure void. The voided directory is archived untouched (its
    cells stay charged to the budget and its partial records are never scored, analyzed or shown to anyone), a ledger entry is
    written, and the stage is rerun from scratch on the SAME deterministic schedule, so a retry cannot be used to resample a
    disliked outcome: nothing about the voided cells can enter a decision, and the retry count is bounded. No cell content is
    read here; only the void marker and the digests of the partial records."""
    config = read(Path(campaign) / "config.json")
    directory = stage_dir(campaign, iteration, stage)
    marker = directory / "VOID.json"
    if not marker.exists():
        raise ValueError("only a void generation can be retried")
    void = read(marker)
    if void.get("retryable") is not True:
        raise ValueError("only an infrastructure void is retryable; this one is an integrity or result stop")
    if any((directory / n).exists() for n in ("generated.json", "score-started.json", "scored.json", "analyzed.json", "SCORE-VOID.json", "POST-VOID.json")):
        raise ValueError("a stage that was completed, scored or analyzed cannot be retried")
    if void.get("records") != cell_records(directory):
        raise ValueError("the partial records changed after the void; retry refused")
    ledger = retry_ledger(campaign)
    n = 1 + sum(1 for r in ledger if (r["iteration"], r["stage"]) == (iteration, stage))
    if n > MAX_STAGE_RETRIES or len(ledger) >= MAX_CAMPAIGN_RETRIES:
        raise ValueError("retry budget spent (one per stage, two per campaign); the stage stays void")
    planned = len(schedule(iteration, stage, config["aa3"]))
    state = iteration_state(campaign)
    if state["blocked"] or state["cells_spent"] + planned > state["budget"]:
        raise ValueError("a retry would exceed the generation budget or the campaign is blocked")
    archive = iteration_dir(campaign, iteration) / "void" / f"{stage}-{n}"
    archive.parent.mkdir(exist_ok=True)
    directory.rename(archive)
    entry = dict(iteration=iteration, stage=stage, attempt=n, void_sha256=sha(archive / "VOID.json"),
                 started_sha256=sha(archive / "started.json") if (archive / "started.json").exists() else None,
                 cells_charged=stage_cells_spent(archive), reason=void.get("error"), schedule_unchanged=True,
                 archive=archive.relative_to(Path(campaign)).as_posix())
    write(Path(campaign) / "retries" / f"{iteration:02d}-{stage}-{n}.json", entry)
    return entry


def timed_out(rec):
    attempts = rec.get("attempts") or []
    return bool(attempts) and bool(attempts[-1].get("timeout"))


def score_stage(args, campaign, config):
    iteration, stage = args.iteration, args.stage or ("baseline" if args.iteration == 0 else "screening")
    directory = stage_dir(campaign, iteration, stage)
    if void_marker(directory) or not (directory / "generated.json").exists():
        raise ValueError("void or incomplete generation")
    oss = machinery()
    rt = oss.runtime(runtime_args(config))
    ports = oss.engine.Ports(24000)
    annotations = read(args.adjudications) if args.adjudications else {}
    write(directory / "score-started.json", {"freeze_sha256": sha(campaign / "freeze.json")})
    try:
        with live_context(campaign, config) as active, rt.campaign():
            active.v2.scoring_guard(list(DEV_SYNTH))
            for slot in read(directory / "generated.json")["reports"]:
                target = batch_dir(directory, slot)
                scores, slot_annotations = [], annotations.get(slot, {})
                for rec in verify_report(target)["runs"]:
                    assert_dev(rec["case"])
                    if timed_out(rec):
                        result = dict(clean=False, refactor_score=0, kill_rate=0, scan={"p0": 0, "p1p2": 0}, timeout=True)
                    elif rec["case"] in OSS_ACTIVE:
                        result = active.score_rows(target, rt, {"model": config["model"], "runs": [rec]}, slot_annotations)[0]
                    elif rec.get("spec_files"):
                        tests = target / "final-artifacts" / rec["call_id"] / "tests"
                        result = active.engine.evaluate_specs(rec["case"], active.engine.CASES / rec["case"], tests, rec["spec_files"], ports)
                        scan = active.engine.scan_smells(tests, [f.removeprefix("tests/") for f in rec["tests_files"]])
                        for defect, fault in result["faults"].items():
                            if defect in slot_annotations.get(rec["call_id"], {}):
                                annotation = slot_annotations[rec["call_id"]][defect]
                                if type(annotation) is not bool:
                                    raise ValueError("attribution must be boolean")
                                fault["valid_detection"] = annotation
                        result = active.score_measurements(result["clean_runs"], result["faults"], result["refactor"], scan)
                    else:
                        result = dict(clean=False, refactor_score=0, kill_rate=0, scan={"p0": 0, "p1p2": 0})
                    result.update({k: rec[k] for k in ("call_id", "case", "repetition")})
                    scores.append(result)
                    write(target / "raw-scores" / (rec["call_id"] + ".json"), result)
                verify_report(target)
                write(target / "scores.json", {"scores": scores, "report_sha256": sha(target / "final.json")})
        write(directory / "scored.json", {"status": "COMPLETED"})
    except BaseException as exc:
        write(directory / "SCORE-VOID.json", {"error": type(exc).__name__, "message": str(exc)})
        raise


def adjudicate_stage(campaign, iteration, stage, annotations):
    """Attribute saved mutant failures offline; never relaunch a browser or model."""
    verify_campaign(campaign)
    directory = stage_dir(campaign, iteration, stage)
    if not (directory / "scored.json").is_file() or (directory / "SCORE-VOID.json").exists():
        raise ValueError("completed scoring required")
    oss = machinery()
    outputs = []
    for slot in read(directory / "generated.json")["reports"]:
        target = batch_dir(directory, slot)
        verify_report(target)
        data = read(target / "scores.json")
        for row in data["scores"]:
            if not row.get("faults"):
                continue
            for defect, fault in row["faults"].items():
                annotation = annotations.get(slot, {}).get(row["call_id"], {}).get(defect)
                if annotation is not None:
                    if type(annotation) is not bool:
                        raise ValueError("attribution must be boolean for exact slot/call/defect")
                    fault["valid_detection"] = annotation
            row.update(oss.score_measurements(row["clean_runs"], row["faults"], row["refactor"], row.get("scan")))
            if row.get("fault_attribution_complete") is not True:
                raise ValueError("complete positive-failure attribution required before publishing adjudications")
        data["raw_scores_sha256"] = sha(target / "scores.json")
        outputs.append((target, data))
    for target, data in outputs:
        write(target / "adjudicated-scores.json", data)


def layer_read_indicator(oss, rec, transcripts):
    """Parent-stream indicator that the exact layer path was read or named in a command."""
    attempt = (rec.get("attempts") or [None])[-1]
    if attempt is None:
        return None
    events = oss.v2.transcript_events(attempt, transcripts)
    if events is None:
        return None
    return any(kind in {"read", "command"} and any(t in value for t in (LAYER_TARGET, "<work>/skill/thin-rules/SKILL.md"))
               for kind, value in oss.evidence.tool_uses(events))


def verification_indicator(oss, rec, transcripts):
    attempt = (rec.get("attempts") or [None])[-1]
    events = oss.v2.transcript_events(attempt, transcripts) if attempt else None
    if events is None:
        return None
    return any(kind == "command" and re.search(r"playwright\s+test", value) for kind, value in oss.evidence.tool_uses(events))


def analyze_stage(campaign, iteration, stage):
    verify_campaign(campaign)
    directory = stage_dir(campaign, iteration, stage)
    if void_marker(directory) or not (directory / "scored.json").exists():
        raise ValueError("void or incomplete batch cannot be analyzed for decisions")
    oss = machinery()
    config = read(Path(campaign) / "config.json")
    digests, outputs = {}, []
    for slot in read(directory / "generated.json")["reports"]:
        target = batch_dir(directory, slot)
        score_path = target / "adjudicated-scores.json" if (target / "adjudicated-scores.json").exists() else target / "scores.json"
        report, scored = verify_report(target), read(score_path)
        if report["freeze_sha256"] != sha(campaign / "freeze.json") or report["model"] != config["model"]:
            raise ValueError("report freeze or model differs")
        if "raw_scores_sha256" in scored and scored["raw_scores_sha256"] != sha(target / "scores.json"):
            raise ValueError("raw score provenance drift")
        if scored["report_sha256"] != sha(target / "final.json"):
            raise ValueError("score provenance drift")
        indexed = {r["call_id"]: r for r in scored["scores"]}
        n = batch_cells()
        if len(scored["scores"]) != n or len(report["runs"]) != n or len(indexed) != n or set(indexed) != {r["call_id"] for r in report["runs"]}:
            raise ValueError("scores incomplete or duplicated")
        treatment = report["treatment"]
        cells = []
        for rec in report["runs"]:
            assert_dev(rec["case"])
            if rec.get("infrastructure_error"):
                raise ValueError("aborted result")
            if rec["case"] in DEV_SYNTH:
                check_generation_isolation(rec)
            raw = indexed[rec["call_id"]]
            is_timeout = timed_out(rec)
            if rec.get("spec_files") and not is_timeout:
                raw = oss.score_measurements(raw["clean_runs"], raw["faults"], raw["refactor"], raw.get("scan"))
            costs = []
            for attempt in rec["attempts"]:
                events = oss.v2.transcript_events(attempt, target / "final-transcripts")
                sess = oss.v2.rollout_summary(attempt, target / "final-transcripts", events)
                reject_root_mismatch(oss.evidence, attempt, target / "final-transcripts", events)
                costs.append(oss.evidence.cell_tokens(attempt, sess))
            incomplete = not costs or not all(c["complete"] for c in costs)
            if incomplete and not (is_timeout and costs):
                raise ValueError("all-attempt parent/child cost incomplete")
            scan = raw.get("scan")
            if rec.get("spec_files") and not is_timeout and (not scan or scan.get("error") or "p0" not in scan or "p1p2" not in scan):
                raise ValueError("delivered cell scanner evidence missing")
            extra = oss.v2.cell_extras(rec, target / "final-transcripts", target)
            specs = [target / "final-artifacts" / rec["call_id"] / f for f in rec.get("spec_files") or []]
            hygiene = metrics().analyze_delivered_specs(specs) if specs else None
            cells.append(dict(case=rec["case"], repetition=rec["repetition"], call_id=rec["call_id"],
                clean=False if is_timeout else raw["clean"], refactor_score=0 if is_timeout else raw["refactor_score"],
                kill_rate=0 if is_timeout else raw["kill_rate"],
                scan_p0=(scan or {}).get("p0", 0), scan_p1p2=(scan or {}).get("p1p2", 0),
                tokens=sum(c["processed"] for c in costs), cached_tokens=sum(c["total"] - c["processed"] for c in costs),
                generation_s=sum(a["elapsed_ms"] / 1000 for a in rec["attempts"]),
                max_attempt_s=max(a["elapsed_ms"] / 1000 for a in rec["attempts"]), timeout=is_timeout,
                layer_read=layer_read_indicator(oss, rec, target / "final-transcripts") if treatment == "D" else None,
                verification_executed=verification_indicator(oss, rec, target / "final-transcripts"),
                cost_complete=True, cost_lower_bound=bool(incomplete), fidelity_class=extra.get("fidelity_class"), deliverable=bool(rec.get("spec_files")),
                hygiene=(hygiene or {}).get("counts") if hygiene and hygiene.get("available") else None))
        result = dict(cells=cells, summary=summarize(cells, treatment), layer_sha256=report["layer_sha256"],
                      layer_bytes=report["layer_bytes"], treatment=treatment, report_sha256=sha(target / "final.json"),
                      scores_sha256=sha(score_path), score_file=score_path.name)
        outputs.append((target, result))
    for target, result in outputs:
        write(target / "results.json", result)
        digests[target.name] = sha(target / "results.json")
    write(directory / "analyzed.json", digests)


def headroom_stage(campaign):
    verify_campaign(campaign)
    directory = stage_dir(campaign, 0, "baseline")
    config = read(Path(campaign) / "config.json")
    d = [verified_result(directory, s)["cells"] for s in stage_slots("baseline", config["aa3"]) if s != "ref-A"]
    ref = verified_result(directory, "ref-A")["cells"]
    result = headroom_gate(d, ref)
    write(iteration_dir(campaign, 0) / "headroom.json", result)
    return result


def history_for(campaign, iteration, stage, layer_sha):
    """Verified batches that ran exactly this layer, from the baseline through the current stage."""
    batches = []
    for i in range(0, iteration + 1):
        for s in (("baseline",) if i == 0 else ("screening", "confirmation")):
            if (i, STAGES.index(s)) > (iteration, STAGES.index(stage)):
                continue
            directory = stage_dir(campaign, i, s)
            if not (directory / "analyzed.json").exists():
                continue
            for slot in read(directory / "analyzed.json"):
                if slot == "ref-A":
                    continue
                result = verified_result(directory, slot)
                if result["layer_sha256"] == layer_sha:
                    batches.append(result["cells"])
    return batches


def decide_stage(campaign, iteration, stage):
    verify_campaign(campaign)
    directory = stage_dir(campaign, iteration, stage)
    before = incumbent_layer(campaign, iteration)
    header = layer_header(baseline_layer(campaign).read_text())
    lock = validate_candidate(iteration_dir(campaign, iteration), before, campaign)
    if read(directory / "started.json")["candidate"] != lock:
        raise ValueError("candidate provenance changed since generation")
    current = {slot: verified_result(directory, slot) for slot in ("candidate", "incumbent")}
    if [current["candidate"]["layer_sha256"], current["incumbent"]["layer_sha256"]] != [lock["candidate_layer_sha256"], lock["incumbent_layer_sha256"]]:
        raise ValueError("result treatment differs from candidate/incumbent")
    base = [verified_result(stage_dir(campaign, 0, "baseline"), s) for s in stage_slots("baseline", read(Path(campaign) / "config.json")["aa3"]) if s != "ref-A"]
    context = dict(baseline_tokens_mean=sum(r["summary"]["tokens_mean"] for r in base) / len(base),
                   baseline_tokens_incl_cached_mean=sum(r["summary"]["tokens_incl_cached_mean"] for r in base) / len(base),
                   candidate_layer_bytes=current["candidate"]["layer_bytes"], incumbent_layer_bytes=current["incumbent"]["layer_bytes"],
                   tolerance=GUARD_PROFILES[read(Path(campaign) / "config.json")["guard_profile"]])
    history = history_for(campaign, iteration, stage, lock["incumbent_layer_sha256"])
    decision = decide(current["candidate"]["cells"], current["incumbent"]["cells"], history, context)
    decision.update(iteration=iteration, stage=stage, candidate_binding=lock)
    path = directory / "decision.json"
    if path.exists():
        if read(path) != json.loads(json.dumps(decision, sort_keys=True)):
            raise ValueError("recomputed stage decision differs from the recorded one")
        return read(path)
    write(path, decision)
    return decision


def decide_iteration(campaign, iteration):
    screening = decide_stage(campaign, iteration, "screening")
    confirm_dir = stage_dir(campaign, iteration, "confirmation")
    confirmation = decide_stage(campaign, iteration, "confirmation") if (confirm_dir / "analyzed.json").exists() else None
    combined = combine_with_pooled_gate(screening, confirmation) if confirmation is not None else combine_stages(screening, None)
    if combined["verdict"] == "CONFIRMATION_REQUIRED":
        return combined
    lock = screening["candidate_binding"]
    final = dict(combined, iteration=iteration, screening_verdict=screening["verdict"],
                 confirmation_verdict=(confirmation or {}).get("verdict"),
                 candidate_layer_sha256=lock["candidate_layer_sha256"], candidate_binding=lock,
                 researcher_overhead=read(iteration_dir(campaign, iteration) / "researcher-run.json"),
                 note="Development evidence only; adoption is not a significance or release claim.")
    final["stop_reason"] = stop_reason(previous_decisions(campaign) + [final], iteration_state(campaign))
    write(iteration_dir(campaign, iteration) / "decision.json", final)
    return final


# ------------------------------------------------------------------ researcher: packet, draws, review

def failing(cell):
    return (not cell["deliverable"] or cell["timeout"] or not cell["clean"] or cell["refactor_score"] == 0
            or cell["kill_rate"] < FAIL_KILL_BELOW or cell.get("fidelity_class") != FIDELITY_OFFICIAL)


def severity(cell):
    return (0 if not cell["deliverable"] else 1 if cell["timeout"] else 2 if not cell["clean"]
            else 3 if cell["refactor_score"] == 0 else 4, cell["kill_rate"], cell["call_id"])


def cell_ref(call_id):
    return "c" + hashlib.sha256(call_id.encode()).hexdigest()[:8]


def build_packet(campaign, iteration):
    """Redacted researcher evidence: labels and counters, plus a literal-free skeleton of a few specs.
    Raw literals feed only the private forbidden-token screen."""
    before = incumbent_layer(campaign, iteration)
    sources = []
    sha_before = sha(before)
    for i in range(0, iteration):
        for s in (("baseline",) if i == 0 else ("screening", "confirmation")):
            directory = stage_dir(campaign, i, s)
            if not (directory / "analyzed.json").exists():
                continue
            for slot in read(directory / "analyzed.json"):
                if slot == "ref-A":
                    continue
                result = verified_result(directory, slot)
                if result["layer_sha256"] == sha_before:
                    sources.append((directory, slot, result))
    if not sources:
        raise ValueError("no verified batch of the incumbent layer to learn from")
    labels = {t: f"T{k}" for k, t in enumerate(DEV, 1)}
    all_cells, fails = [], []
    for directory, slot, result in sources:
        target = batch_dir(directory, slot)
        report = read(target / "final.json")
        scores = {r["call_id"]: r for r in read(target / ("adjudicated-scores.json" if (target / "adjudicated-scores.json").exists() else "scores.json"))["scores"]}
        recs = {r["call_id"]: r for r in report["runs"]}
        for cell in result["cells"]:
            all_cells.append(cell)
            if failing(cell):
                fails.append((cell, target, scores.get(cell["call_id"], {}), recs[cell["call_id"]]))
    if not fails:
        raise ValueError("NO_HEADROOM: no failing DEV cell supports another hypothesis")
    fails.sort(key=lambda f: severity(f[0]))
    shown, private, spec_texts, error_texts = [], {}, [], []
    for index, (cell, target, raw, rec) in enumerate(fails):
        texts = []
        for name in rec.get("spec_files", []):
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts or rel.parts[0] != "tests":
                raise ValueError("unsafe delivered test path")
            f = target / "final-artifacts" / rec["call_id"] / rel
            if f.is_symlink():
                raise ValueError("linked spec refused")
            texts.append(f.read_text())
        spec_texts += texts
        errors = [str(m) for run in raw.get("clean_runs", []) for m in run.get("errors", [])]
        refactor_errors = [str(m) for m in (raw.get("refactor") or {}).get("errors", [])]
        error_texts += errors + refactor_errors
        if index >= PACKET_MAX_FAILURES:
            continue
        ref = cell_ref(cell["call_id"])
        private[ref] = cell["call_id"]
        shown.append(dict(
            cell_ref=ref, task=labels[cell["case"]],
            outcome=dict(delivered=cell["deliverable"], timeout=cell["timeout"], clean_3_of_3=cell["clean"],
                         refactor_pass=bool(cell["refactor_score"]), kill_rate=round(cell["kill_rate"], 2)),
            error_classes=dict(clean=dict(Counter(error_class(m) for m in errors)),
                               refactor=dict(Counter(error_class(m) for m in refactor_errors))),
            hygiene_counts=cell.get("hygiene"),
            skeleton=redact_spec("\n".join(texts)) if index < PACKET_SKELETON_CELLS and texts else None))
    totals = Counter()
    for cell in all_cells:
        totals.update(cell.get("hygiene") or {})
    packet = dict(schema=1, incumbent_layer_sha256=sha_before, batches=len(sources), cells=len(all_cells),
                  failing_cells=len(fails), failure_rule="not delivered, timeout, not clean 3/3, refactor failure, kill rate below %.1f, or the official generator surface was not used" % FAIL_KILL_BELOW,
                  survival=sum(c["refactor_score"] for c in all_cells) / len(all_cells),
                  hygiene_totals=dict(totals), failures=shown)
    scopes = [b for p in sorted((Path(campaign) / "plans").glob("*.md")) for b in plan_behaviors(p.read_text())]
    generic = generic_vocabulary("\n".join((REFERENCE_DIR / n).read_text() for n in REFERENCE_FILES), before.read_text())
    forbidden = derive_forbidden(spec_texts, error_texts, scopes, DEV, generic)
    return packet, dict(cell_refs=private, forbidden=forbidden)


def write_packet(campaign, iteration):
    require_headroom(campaign)
    directory = iteration_dir(campaign, iteration)
    try:
        packet, secret = build_packet(campaign, iteration)
    except ValueError as exc:
        if str(exc).startswith("NO_HEADROOM") and not (directory / "no-headroom.json").exists():
            write(directory / "no-headroom.json", dict(iteration=iteration, verdict="NO_HEADROOM", reason=str(exc)))
        raise
    write(directory / "packet.json", packet)
    write(directory / "forbidden-tokens.json", secret["forbidden"])
    write(directory / "packet-private.json", dict(cell_refs=secret["cell_refs"], packet_sha256=sha(directory / "packet.json"),
          forbidden_sha256=sha(directory / "forbidden-tokens.json")))
    return packet


TASK_TEXT = """You maintain a short checklist of Playwright test-writing rules (incumbent/THIN-RULES.md).
Read packet.json: redacted evidence from generated tests that failed. Propose exactly ONE edit to the
checklist, supported by the failing cells you cite (use their cell_ref values).

Edit grammar (machine-checked): exactly one checklist line added, deleted, or reworded in place. The
frontmatter and heading are frozen. ASCII only, each line at most {line} bytes, the file at most {total}
bytes, net growth at most {growth} bytes, at most {rules} lines. Deleting a rule is a legal hypothesis.
{ceiling}
Wording: general principles only. Never name or paraphrase a selector, identifier, element, label,
control, page or example from the evidence, and never describe how a test might be graded or how markup
might change. A rule may not direct an install, a download, network use, credential use, a write outside
the generated tests, or skipping the official generator and its tools. Each rule must be a complete
directive of at least {minimum} bytes, not a near-copy of another rule, and may mention a pattern the
reviewer scanner flags only to forbid it. Do not retrieve anything from the internet. Do not look for other files.

Write to out/ exactly: THIN-RULES.md (the complete edited file), hypothesis.json, hypothesis.md.
hypothesis.json: {{"hypotheses": [{{"edit_kind": "add|delete|reword", "mechanism": "...",
"evidence_cell_refs": ["..."], "expected_effect": "...", "falsification": "..."}}]}} with one entry.
"""


def new_workspace():
    return Path(tempfile.mkdtemp(prefix="loop-thin-researcher-")).resolve()


def stage_draw(campaign, iteration):
    directory = iteration_dir(campaign, iteration)
    require_headroom(campaign)
    state = iteration_state(campaign)
    if stop_reason(state["decisions"], state):
        raise ValueError("stop rule refuses further work: " + stop_reason(state["decisions"], state))
    if (directory / "candidate").exists() or (directory / "decision.json").exists():
        raise ValueError("iteration already has a candidate or decision")
    draws = directory / "draws"
    existing = sorted(draws.glob("d*")) if draws.exists() else []
    if len(existing) >= MAX_DRAWS:
        raise ValueError("at most two researcher draws per iteration")
    packet = read(directory / "packet.json") if (directory / "packet.json").exists() else write_packet(campaign, iteration)
    before = incumbent_layer(campaign, iteration)
    k = len(existing) + 1
    draw = draws / f"d{k}"
    # The workspace lives in a fresh private directory OUTSIDE the campaign tree, so the researcher's working
    # directory has no relative path to the forbidden-token file, the private packet records, raw artifacts or scores.
    draw.mkdir(parents=True)
    work = new_workspace()
    (work / "incumbent").mkdir()
    (work / "out").mkdir()
    shutil.copyfile(before, work / "incumbent/THIN-RULES.md")
    write(work / "packet.json", packet)
    config = read(Path(campaign) / "config.json")
    if config.get("library"):
        for name in REFERENCE_FILES:
            (work / "library").mkdir(exist_ok=True)
            shutil.copyfile(Path(campaign) / "library" / name, work / "library" / name)
    ceiling = saturation_notice(before.read_text(), layer_header(before.read_text()))
    write_text(work / "TASK.md", TASK_TEXT.format(line=LAYER_MAX_LINE, total=LAYER_MAX_BYTES, growth=LAYER_MAX_GROWTH,
                                                 rules=LAYER_MAX_RULES, ceiling=ceiling, minimum=LAYER_MIN_RULE_BYTES))
    write(draw / "staged.json", dict(draw=k, workspace=str(work), packet_sha256=sha(directory / "packet.json"),
          task_sha256=sha(work / "TASK.md"), incumbent_sha256=sha(before)))
    return draw


def draw_workspace(draw):
    work = Path(read(Path(draw) / "staged.json")["workspace"])
    if work.is_symlink() or not work.is_dir():
        raise ValueError("researcher workspace missing or linked")
    return work


def researcher_identity(identity):
    if (not isinstance(identity, dict) or identity.get("family") not in ALLOWED_REVIEWER_FAMILIES
            or not identity.get("id") or not identity.get("model")):
        raise ValueError("researcher identity must name an allowed non-Codex family, a model and a session id")
    return identity


def run_researcher_command(draw, argv, identity, timeout=3600):
    """Run a pluggable researcher command inside the staged workspace. Never Codex."""
    researcher_identity(identity)
    if not argv or any(Path(a).name.lower().startswith("codex") or "codex" in a.lower().split() for a in argv):
        raise ValueError("the researcher must not be Codex")
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TERM")}
    work = draw_workspace(draw)
    env["LOOP_WORKSPACE"] = str(work)
    started = subprocess.run(argv, cwd=work, env=env, capture_output=True, text=True, timeout=timeout)
    write(Path(draw) / "command.json", dict(argv=argv, exit=started.returncode, identity=identity))
    return started.returncode


def ingest_draw(campaign, iteration, k, identity, usage=None):
    """Validate one researcher draw against the grammar, hypothesis format and the packet-derived screen."""
    directory = iteration_dir(campaign, iteration)
    draw = directory / "draws" / f"d{k}"
    work = draw_workspace(draw)
    researcher_identity(identity)
    before = incumbent_layer(campaign, iteration)
    private = read(directory / "packet-private.json")
    forbidden = read(directory / "forbidden-tokens.json")
    status, category, text = "VALID", None, None
    if (work / "out").is_dir() and not (draw / "researcher-out").exists():  # every draw is kept, valid or not
        shutil.copytree(work / "out", draw / "researcher-out", symlinks=True)
    try:
        if {p.name for p in (work / "out").iterdir()} != {"THIN-RULES.md", "hypothesis.json", "hypothesis.md"}:
            raise ValueError("researcher outputs must be exactly the three registered files")
        for name in ("THIN-RULES.md", "hypothesis.json", "hypothesis.md"):
            if (work / "out" / name).is_symlink():
                raise ValueError("linked output refused")
        text = (work / "out/THIN-RULES.md").read_text()
        edit = validate_edit(before.read_text(), text, layer_header(before.read_text()))
        validate_hypothesis(read(work / "out/hypothesis.json"), private["cell_refs"], edit)
        hits = screen_added(edit["added"], forbidden)
        if hits:
            raise ValueError("automated wording screen: " + ",".join(sorted(set(hits))))
        static = static_screen(edit, parse_layer(text, layer_header(before.read_text())))
        if static:
            raise ValueError("static inner stage: " + ",".join(static))
        if at_ceiling(before.read_text()) and edit["growth"] > 0:
            raise ValueError("layer at its ceiling: only non-growing edits are valid")
        if edit["op"] == "add" and not add_possible(before.read_text(), layer_header(before.read_text())):
            raise ValueError("layer cannot take another line: reword or delete")
    except (ValueError, OSError, KeyError, UnicodeError) as exc:
        status, category = "INVALID", str(exc)[:200]
    record = dict(draw=k, status=status, category=category, identity=identity, usage=usage,
                  usage_known=usage is not None, packet_sha256=private["packet_sha256"])
    if status == "VALID":
        (draw / "candidate").mkdir()
        shutil.copyfile(work / "out/THIN-RULES.md", draw / "candidate/THIN-RULES.md")
        for name in ("hypothesis.json", "hypothesis.md"):
            shutil.copyfile(work / "out" / name, draw / name)
        write_text(draw / "diff", layer_diff(before.read_text(), text))
        record["diff_sha256"] = sha(draw / "diff")
        write(draw / "researcher-run.json", dict(identity=identity, usage=usage, usage_known=usage is not None,
                                                 draw=k, draws_spent=len(list((directory / "draws").glob("d*")))))
    write(draw / "ingest.json", record)
    return record


def validate_hypothesis(hypothesis, refs, edit):
    if set(hypothesis) != {"hypotheses"} or not isinstance(hypothesis["hypotheses"], list) or len(hypothesis["hypotheses"]) != 1:
        raise ValueError("exactly one hypothesis required")
    h = hypothesis["hypotheses"][0]
    if (set(h) != {"edit_kind", "mechanism", "evidence_cell_refs", "expected_effect", "falsification"}
            or not isinstance(h["evidence_cell_refs"], list) or not h["evidence_cell_refs"]
            or not set(h["evidence_cell_refs"]) <= set(refs)
            or any(not isinstance(h[k], str) or not h[k].strip() for k in ("mechanism", "expected_effect", "falsification"))):
        raise ValueError("hypothesis must cite failing cells and state one falsifiable mechanism")
    if h["edit_kind"] != edit["op"]:
        raise ValueError("declared edit kind differs from the edit")


def wording_prompt(before_text, after_text, edit):
    """Deterministic prompt for the independent wording reviewer."""
    return ("You review ONE edit to a short checklist of Playwright test-writing rules. Answer PASS only if every\n"
            "added line is a general principle that could apply to any web application, and does NOT:\n"
            "(1) name or hint at a selector, identifier, element, label, control, page or concrete example;\n"
            "(2) describe how tests are graded, scored, mutated or how page markup may change;\n"
            "(3) smuggle a task-specific instruction in general words;\n"
            "(4) direct an install, a download, network access, credential or secret use, a write outside the generated tests,\n"
            "or skipping, bypassing or replacing the official generator and its tools.\n"
            "Reply with a first line of exactly PASS or FAIL, then one sentence of reason.\n\n"
            f"Edit: {edit['op']}\nRemoved lines:\n" + "\n".join(edit["removed"]) + "\nAdded lines:\n" + "\n".join(edit["added"]) +
            "\n\nFull checklist after the edit:\n" + after_text)


def validate_review(draw_dir, edit, before_text, after_text, generator_model, researcher):
    review = read(draw_dir / "wording-review.json")
    prompt_path, output_path = draw_dir / "wording-review-prompt.txt", draw_dir / "wording-review-output.txt"
    reviewer = review.get("reviewer") or {}
    if (review.get("diff_sha256") != sha(draw_dir / "diff") or review.get("verdict") != "PASS"
            or reviewer.get("family") not in ALLOWED_REVIEWER_FAMILIES or not reviewer.get("id") or not reviewer.get("model")
            or reviewer.get("id") == researcher.get("id") or reviewer.get("model") == generator_model
            or review.get("prompt_sha256") != sha(prompt_path) or review.get("output_sha256") != sha(output_path)
            or prompt_path.read_text() != wording_prompt(before_text, after_text, edit)
            or not output_path.read_text().lstrip().startswith("PASS")):
        raise ValueError("independent Claude-family wording review of this exact diff, prompt and output required")


def review_candidate(campaign, iteration, k):
    """Run repository checks on a disposable tracked checkout with the candidate overlaid."""
    directory = iteration_dir(campaign, iteration) / "draws" / f"d{k}"
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    with tempfile.TemporaryDirectory(prefix="loop-thin-review-") as tmp:
        checkout = Path(tmp).resolve()
        for rel in filter(None, tracked):
            src, dst = ROOT / rel, checkout / rel
            if src.is_symlink():
                raise ValueError("tracked symlink refused in review snapshot")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.copy2(src, dst)
        target = checkout / LAYER_V0.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(directory / "candidate/THIN-RULES.md", target)
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"]):
            disposable_git(cmd, checkout, {})
        done = subprocess.run(["/bin/bash", "-p", "scripts/ci/review.sh"], cwd=checkout, capture_output=True, text=True, timeout=300)
        write_text(directory / "repository-review.log", done.stdout + done.stderr)
        write(directory / "repository-review.json", {"diff_sha256": sha(directory / "diff"),
              "command": "/bin/bash -p scripts/ci/review.sh", "exit": done.returncode})
        if done.returncode:
            raise ValueError("candidate repository review failed")


def accept_draw(campaign, iteration, k):
    """Bind one fully reviewed draw as the iteration's candidate (the first accepted draw wins)."""
    directory = iteration_dir(campaign, iteration)
    draw = directory / "draws" / f"d{k}"
    if (directory / "candidate").exists():
        raise ValueError("iteration already has a candidate")
    if read(draw / "ingest.json")["status"] != "VALID":
        raise ValueError("only a valid draw can be accepted")
    before = incumbent_layer(campaign, iteration)
    validate_candidate(directory, before, campaign, material=draw)  # nothing is copied unless every check passes
    shutil.copytree(draw / "candidate", directory / "candidate")
    for name in ("diff", "hypothesis.json", "hypothesis.md", "researcher-run.json", "wording-review.json",
                 "wording-review-prompt.txt", "wording-review-output.txt", "repository-review.json"):
        shutil.copyfile(draw / name, directory / name)
    return validate_candidate(directory, before, campaign)


def validate_candidate(directory, before, campaign, material=None):
    """Recompute every candidate property from files; nothing is trusted. The packet records live in the
    iteration directory; the candidate material lives there too once accepted, or in a draw before."""
    directory, before = Path(directory), Path(before)
    material = Path(material) if material else directory
    config = read(Path(campaign) / "config.json")
    header = layer_header(baseline_layer(campaign).read_text())
    before_text, after_text = before.read_text(), (material / "candidate/THIN-RULES.md").read_text()
    edit = validate_edit(before_text, after_text, header)
    private = read(directory / "packet-private.json")
    if private["packet_sha256"] != sha(directory / "packet.json") or private["forbidden_sha256"] != sha(directory / "forbidden-tokens.json"):
        raise ValueError("packet or forbidden-token record changed")
    validate_hypothesis(read(material / "hypothesis.json"), private["cell_refs"], edit)
    if layer_diff(before_text, after_text) != (material / "diff").read_text():
        raise ValueError("diff does not match candidate")
    hits = screen_added(edit["added"], read(directory / "forbidden-tokens.json"))
    if hits:
        raise ValueError("automated wording screen: " + ",".join(sorted(set(hits))))
    static = static_screen(edit, parse_layer(after_text, header))
    if static:
        raise ValueError("static inner stage: " + ",".join(static))
    run = read(material / "researcher-run.json")
    researcher_identity(run["identity"])
    validate_review(material, edit, before_text, after_text, config["model"], run["identity"])
    if read(material / "repository-review.json") != {"diff_sha256": sha(material / "diff"),
            "command": "/bin/bash -p scripts/ci/review.sh", "exit": 0}:
        raise ValueError("repository review PASS for this diff required")
    return dict(incumbent_layer_sha256=sha_text(before_text), candidate_layer_sha256=sha_text(after_text),
                edit=dict(op=edit["op"], growth=edit["growth"]), hypothesis=sha(material / "hypothesis.json"),
                packet=sha(directory / "packet.json"), diff=sha(material / "diff"),
                wording=sha(material / "wording-review.json"), repository_review=sha(material / "repository-review.json"))


def no_candidate(campaign, iteration):
    """Record NO_CANDIDATE once both draws are spent without an accepted candidate."""
    directory = iteration_dir(campaign, iteration)
    draws = sorted((directory / "draws").glob("d*")) if (directory / "draws").exists() else []
    if (directory / "candidate").exists() or len(draws) < MAX_DRAWS:
        raise ValueError("NO_CANDIDATE needs two spent draws and no accepted candidate")
    before = incumbent_layer(campaign, iteration)
    decision = dict(verdict="NO_CANDIDATE", iteration=iteration, decided_at="researcher",
                    draws=[read(d / "ingest.json") if (d / "ingest.json").exists() else {"status": "MISSING"} for d in draws],
                    ceiling_without_candidate=at_ceiling(before.read_text()),
                    rule_cap_reached=at_rule_cap(before.read_text(), layer_header(before.read_text())),
                    researcher_overhead=dict(draws=len(draws)), candidate_layer_sha256=None)
    decision["stop_reason"] = stop_reason(previous_decisions(campaign) + [decision],
                                          dict(iteration_state(campaign), ceiling_without_candidate=decision["ceiling_without_candidate"]))
    write(directory / "decision.json", decision)
    return decision


# ------------------------------------------------------------------ command line

def calibrate(args, campaign, config):
    """Default (synthetic only): the offline synthetic calibration alone, with no Zeppelin machinery run. Opt-in: the Zeppelin
    reference calibration as before, with the synthetic records merged into the same file."""
    oss = machinery()
    target = campaign / "calibration"
    target.mkdir()
    synthetic = synthetic_calibration(oss)
    prepared = {"prepared_sha256": sha(campaign / "prepared-bindings.json")}
    if not OSS_ACTIVE:
        status = "PASS" if all(r["pass"] for r in synthetic.values()) else "FAIL"
        write(target / "_scorer-calibration.json", dict(protocol_id=ID, status=status, campaign_id=config["campaign_id"],
              no_freeze_required=True, model_calls=0, bindings=prepared, tasks=synthetic, scope="synthetic-only"))
        if status != "PASS":
            raise ValueError("synthetic scorer calibration failed; no data calls are authorized")
        validate_calibration(campaign, config)
        return
    old = oss.bindings
    try:
        oss.bindings = lambda *a, **kw: prepared
        with live_context(campaign, config) as active:
            rt = active.runtime(runtime_args(config))
            with rt.campaign():
                active.calibrate_references(runtime_args(config), rt, target)
        path = target / "_scorer-calibration.json"
        data = read(path)
        data["tasks"].update(synthetic)
        data["scope"] = "synthetic-plus-zeppelin-opt-in"
        if not all(r["pass"] for r in synthetic.values()):
            data["status"] = "FAIL"
        path.write_text(json.dumps(data, indent=2, allow_nan=False, sort_keys=True) + "\n")
        validate_calibration(campaign, config)
    finally:
        oss.bindings = old


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "plan", "simulate", "select-model", "thin-eval-gate", "prepare", "calibrate", "freeze", "probe", "run", "score",
        "adjudicate", "analyze", "headroom", "packet", "researcher-stage", "researcher-run", "researcher-ingest",
        "wording-prompt", "review-candidate", "accept-draw", "no-candidate", "validate-candidate", "retry-void", "decide"))
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--iteration", type=int, default=0)
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--draw", type=int)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--aa3", action="store_true")
    parser.add_argument("--library", action="store_true")
    parser.add_argument("--guard-profile", default=None, choices=sorted(GUARD_PROFILES),
                        help="prepare and simulate default to strict (owner decision 2026-10-15); noise-tolerant stays registered but is not the chosen profile")
    parser.add_argument("--include-zeppelin", action="store_true",
                        help="opt in to the Zeppelin dev tasks at prepare (the shared-proxy F3 hazard is not repaired there); default is the synthetic dev split only")
    parser.add_argument("--effect", type=float, default=0.0)
    parser.add_argument("--base", type=float, default=0.6)
    parser.add_argument("--replicates", type=int, default=2000)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--identity", help="JSON {family, model, id} of the researcher")
    parser.add_argument("--usage", help="JSON usage of the researcher, if known")
    for key in ("pool", "loop-runner", "dists", "source", "adjudications", "model-selection", "thin-eval-gate"):
        parser.add_argument("--" + key, type=Path)
    parser.add_argument("researcher_argv", nargs="*")
    args = parser.parse_args(argv)
    if args.command != "prepare" and args.campaign and (Path(args.campaign) / "config.json").exists():
        use_zeppelin(bool(read(Path(args.campaign) / "config.json").get("include_zeppelin", False)))
    else:
        use_zeppelin(bool(args.include_zeppelin))
    if args.command in ("calibrate", "freeze", "probe", "run", "score"):
        campaign, config, bound = require_live(args)  # Before any machinery import or setup beyond bindings.
        if args.command == "freeze":
            write(campaign / "freeze.json", {"bindings": bound,
                  "calibration_sha256": sha(campaign / "calibration/_scorer-calibration.json"),
                  "independent_review_sha256": sha(campaign / "independent-review.json")})
        elif args.command == "calibrate":
            calibrate(args, campaign, config)
        elif args.command == "probe":
            oss = machinery()
            with oss.runtime(runtime_args(config)).campaign():
                print(probe(campaign, config))
        elif args.command == "run":
            run_stage(args, campaign, config)
        else:
            score_stage(args, campaign, config)
        if bindings(config, campaign) != bound and args.command in ("run", "score"):
            write(stage_dir(campaign, args.iteration, args.stage or ("baseline" if args.iteration == 0 else "screening")) / "POST-VOID.json",
                  {"reason": "post-operation binding drift"})
            raise ValueError("post-operation binding drift; output void")
    elif args.command == "plan":
        print(json.dumps(schedule(args.iteration, args.stage, args.aa3), indent=2))
    elif args.command == "simulate":
        print(json.dumps(simulate(args.replicates, base=args.base, effect=args.effect, profile=args.guard_profile or "strict"), indent=2))
    elif args.command == "select-model":
        if args.evidence is None or args.out is None:
            raise ValueError("--evidence and --out required")
        order = [m["id"] for m in read(V3_PROTOCOL)["models"]]
        results = {mid: read(args.evidence / mid / "results.json") for mid in order if (args.evidence / mid / "results.json").exists()}
        selection = select_model(results, order)
        selection["inputs"] = {mid: sha(args.evidence / mid / "results.json") for mid in results}
        write(args.out, selection)
    elif args.command == "thin-eval-gate":
        if args.evidence is None or args.model is None or args.out is None:
            raise ValueError("--evidence, --model and --out required")
        results = args.evidence / args.model / "results.json"
        record = thin_eval_gate(read(results), args.model)
        record["inputs"] = dict(results_sha256=sha(results),
                                thin_eval_freeze_sha256=sha(THIN_EVAL_FREEZE) if THIN_EVAL_FREEZE.is_file() else None)
        write(args.out, record)
    elif args.command == "prepare":
        prepare(args)
    else:
        campaign = external(args.campaign)
        if args.command == "headroom":
            print(json.dumps(headroom_stage(campaign), indent=2))
        elif args.command == "analyze":
            analyze_stage(campaign, args.iteration, args.stage or ("baseline" if args.iteration == 0 else "screening"))
        elif args.command == "adjudicate":
            if args.adjudications is None:
                raise ValueError("--adjudications required")
            adjudicate_stage(campaign, args.iteration, args.stage or ("baseline" if args.iteration == 0 else "screening"), read(args.adjudications))
        elif args.command == "packet":
            write_packet(campaign, args.iteration)
        elif args.command == "researcher-stage":
            draw = stage_draw(campaign, args.iteration)
            print(json.dumps(dict(draw=str(draw), workspace=str(draw_workspace(draw)))))
        elif args.command == "researcher-run":
            draw = stage_draw(campaign, args.iteration)
            code = run_researcher_command(draw, args.researcher_argv, json.loads(args.identity))
            print(json.dumps(ingest_draw(campaign, args.iteration, int(draw.name[1:]), json.loads(args.identity), json.loads(args.usage) if args.usage else None)))
            if code:
                raise ValueError("researcher command exited nonzero")
        elif args.command == "researcher-ingest":
            print(json.dumps(ingest_draw(campaign, args.iteration, args.draw, json.loads(args.identity), json.loads(args.usage) if args.usage else None)))
        elif args.command == "wording-prompt":
            directory = iteration_dir(campaign, args.iteration) / "draws" / f"d{args.draw}"
            before = incumbent_layer(campaign, args.iteration).read_text()
            after = (directory / "candidate/THIN-RULES.md").read_text()
            edit = validate_edit(before, after, layer_header(before))
            write_text(directory / "wording-review-prompt.txt", wording_prompt(before, after, edit))
        elif args.command == "review-candidate":
            review_candidate(campaign, args.iteration, args.draw)
        elif args.command == "accept-draw":
            print(json.dumps(accept_draw(campaign, args.iteration, args.draw)))
        elif args.command == "no-candidate":
            no_candidate(campaign, args.iteration)
        elif args.command == "retry-void":
            print(json.dumps(retry_void(campaign, args.iteration, args.stage or ("baseline" if args.iteration == 0 else "screening"))))
        elif args.command == "validate-candidate":
            print(json.dumps(validate_candidate(iteration_dir(campaign, args.iteration), incumbent_layer(campaign, args.iteration), campaign)))
        else:
            print(json.dumps(decide_iteration(campaign, args.iteration)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
