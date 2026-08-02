#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Executable budget for the residual-credential regexes.

WHY THIS FILE EXISTS. The shared redactor and the fail-closed gate in
``skills/*/scripts/residual_credentials.py`` are a pile of alternations,
optional groups and nested quantifiers that sit directly on attacker-supplied
artifact text. Every comment in that module claims the patterns stay linear --
the lookbehind that pins a keyword to the start of an identifier run, the
lead-character guard in front of the stray-hyphen branch, the bounded key
tail, the newline loop in the cross-line value extent. Until now those claims
lived only in prose and in one-off measurements pasted into review notes. A
regression that turned any of them quadratic would have shipped green.

WHAT IS ASSERTED, AND WHY IT IS SHAPED THIS WAY. A wall-clock threshold tight
enough to catch a real regression is also tight enough to flake on a loaded
CI box, and a threshold loose enough never to flake catches nothing. So there
are two independent assertions per input family:

  1. AN ABSOLUTE CEILING, deliberately generous -- roughly two orders of
     magnitude above the measured cost -- which exists to turn catastrophic
     backtracking into a failure rather than a hang.

  2. A SCALING ASSERTION, which is the one that actually has teeth. Each
     family is measured at three sizes, N, 4N and 16N. Linear work quadruples
     between steps; quadratic work grows sixteenfold. The assertion allows a
     factor well above 4 and well below 16, so it is insensitive to how fast
     or how loaded the machine is -- a slow machine is slow at every size --
     while still failing on the first quadratic term anybody reintroduces.

Timings are the MINIMUM of several repetitions, which is the right statistic
for "how much work is this", because scheduler noise can only ever add time.
A watchdog arms before the first probe so that exponential backtracking dies
with a traceback instead of hanging the run.
"""

from __future__ import annotations

import faulthandler
import importlib.util
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
RESIDUAL_MODULE = (
    ROOT / "skills/playwright-debugger/scripts/residual_credentials.py"
)
CYPRESS_RESIDUAL_MODULE = (
    ROOT / "skills/cypress-debugger/scripts/residual_credentials.py"
)

# Sizes in characters. 400_000 is the adversarial-input size the audit that
# prompted this file measured against, so the ceiling stays comparable to the
# number that was reported.
BASE_SIZE = 25_000
SIZES = (BASE_SIZE, BASE_SIZE * 4, BASE_SIZE * 16)

# One family, at the largest size, may take this long. The measured cost of
# the whole table is a fraction of a second per family; this is the "not
# catastrophic" line, not a performance target.
ABSOLUTE_CEILING_SECONDS = 5.0
# Linear growth across a 4x step is 4x. Quadratic is 16x. Anything at or above
# this is a superlinear term that has to be explained before it ships.
MAX_GROWTH_PER_4X_STEP = 10.0
# Timings below this are dominated by interpreter overhead rather than by the
# regex, and dividing by them manufactures ratios out of noise.
NOISE_FLOOR_SECONDS = 0.002
REPETITIONS = 3
# The whole table below runs in a few seconds. This is two orders of magnitude
# above that: generous enough that an honest slow machine never reaches it,
# short enough that a run wedged on exponential backtracking is reported as a
# failure rather than sitting on a CI worker until the job timeout.
WATCHDOG_SECONDS = 120


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Assembled from pieces rather than written out, so the repository's own
# secret scanner does not read this budget input as an actual key block.
PEM_BEGIN_MARKER = "-" * 5 + "BEGIN PRIVATE KEY" + "-" * 5


def repeat_to(unit: str, size: int) -> str:
    return unit * max(1, size // max(1, len(unit)))


# Every entry names the construct it is aimed at. Adding a quantifier to the
# module without adding the input that would make it backtrack is how the
# previous budget went unmeasured.
INPUT_FAMILIES = (
    (
        "keyword-prefix-run",
        # KEYWORD_PREFIX `[A-Za-z0-9_-]*` with the lookbehind removed
        # re-anchors at every offset inside one long identifier.
        lambda size: "A" * size + "_PASSWORD=hunter2",
    ),
    (
        "two-word-key-window",
        # KEY_RUN's optional space-separated second run, offered at every
        # word boundary of a long space-separated line.
        lambda size: repeat_to("api key ", size) + "= hunter2",
    ),
    (
        "stray-hyphen-gap",
        # KEY_GAP's optional `-\s+` branch behind SEPARATOR_GUARD.
        lambda size: "password " + "- " * (size // 2) + "= hunter2",
    ),
    (
        "whitespace-gap",
        # KEY_GAP's leading `\s*` against a separator that never arrives.
        lambda size: "password" + " " * size + "x",
    ),
    (
        "key-tail-closers",
        # KEY_TAIL's bounded closer repetition, fed far more closers than
        # its bound.
        lambda size: "password" + repeat_to('"]', size) + "= hunter2",
    ),
    (
        "separator-run",
        # The separator alternation, longest-token-first, on a run of the
        # character every token shares.
        lambda size: "password" + "=" * size + " hunter2",
    ),
    (
        "operator-soup",
        # The lead-character guard: every character passes it and no token
        # ever completes.
        lambda size: "password " + repeat_to("<>?!^&%", size),
    ),
    (
        "many-sites",
        # The redactor's site loop and slice splicing rather than any one
        # quantifier.
        lambda size: repeat_to("password=hunter2 ", size),
    ),
    (
        "marker-run",
        # ASSIGNMENT_VALUE's marker branch and its boundary lookahead.
        lambda size: "password=" + repeat_to("[REDACTED]", size),
    ),
    (
        "unterminated-quote",
        # ASSIGNMENT_VALUE's quoted branch failing, then the wide body.
        lambda size: "password=" + '"' * size,
    ),
    (
        "blank-continuation-lines",
        # The cross-line extent's `(?:\r?\n[^\S\r\n]*)+` loop over a run of
        # blank lines that never yields a content line.
        lambda size: "password:" + "\n" * size,
    ),
    (
        "indented-continuation",
        # The same loop where every blank line also carries indentation, so
        # the horizontal-whitespace class inside the loop does real work.
        lambda size: "password:" + repeat_to("\n    ", size),
    ),
    (
        "keyword-per-line",
        # One site per line, each of which looks at the line below it for a
        # continuation and has to stop at the next site.
        lambda size: repeat_to("credentials:\n  password:\n", size),
    ),
    (
        "homoglyph-run",
        # The per-character rendering classes the closure rule added.
        lambda size: "password" + "\uff1d" * size + " hunter2",
    ),
    (
        "header-keyword-prefix-run",
        # KEYWORD_PREFIX's `[A-Za-z0-9_-]*` in front of the header keywords,
        # reached through build_header_pattern rather than the assignment
        # site. Its lookbehind carries the same linearity claim and nothing
        # else in this table exercises it.
        lambda size: "A" * size + "_AUTHORIZATION: hunter2",
    ),
    (
        "pem-without-end",
        # CREDENTIAL_SHAPE_PATTERNS' lazy `[\s\S]*?` block, whose END marker
        # never arrives, followed by the greedy truncation fallback.
        lambda size: PEM_BEGIN_MARKER + "\n" + repeat_to("QUJD", size),
    ),
    (
        "url-query-pairs",
        # RESIDUAL_URL plus RESIDUAL_QUERY_VALUE over one enormous URL.
        lambda size: "https://example.test/p?" + repeat_to("token=abc&", size),
    ),
    (
        "mixed-artifact-lines",
        # A plausible artifact rather than a pathological one, so a
        # regression that only shows up on ordinary text is visible too.
        lambda size: repeat_to(
            "  at Object.<anonymous> (/app/tests/e2e/login.spec.ts:42:18)\n"
            "Locator: getByRole('button', { name: 'Sign in' })\n"
            'cy.get(\'[data-testid="password-input"]\').should("be.visible")\n',
            size,
        ),
    ),
)


def assert_scales_linearly(name: str, timings: list[float]) -> None:
    """Reject growth that a 4x input step cannot explain.

    Split out from the measurement loop so it can be exercised on fabricated
    timings, which is the only way to demonstrate that this assertion has
    teeth without waiting for a machine slow enough to prove it.
    """
    for index in range(len(timings) - 1):
        smaller = max(timings[index], NOISE_FLOOR_SECONDS)
        growth = timings[index + 1] / smaller
        assert growth < MAX_GROWTH_PER_4X_STEP, (
            f"{name} grew {growth:.1f}x across a 4x input step "
            f"({SIZES[index]} -> {SIZES[index + 1]} characters, "
            f"{timings[index]:.4f}s -> {timings[index + 1]:.4f}s); "
            "linear is 4x and quadratic is 16x, so a superlinear "
            "term has been reintroduced"
        )


def assert_growth_check_has_teeth() -> None:
    """The budget's own regression test.

    Both assertions in this file are only as good as the arithmetic behind
    them, and the arithmetic is never exercised by a green run. Feed it a
    linear series and a quadratic one and check it separates them. Fabricated
    timings, so this is deterministic and says nothing about the machine.
    """
    assert_scales_linearly("linear-probe", [0.010, 0.040, 0.160])
    assert_scales_linearly("noise-floor-probe", [0.0000, 0.0005, 0.0019])
    for quadratic in ([0.010, 0.160, 2.560], [0.050, 0.800, 12.80]):
        try:
            assert_scales_linearly("quadratic-probe", quadratic)
        except AssertionError:
            continue
        raise AssertionError(
            "the growth assertion accepted a quadratic timing series "
            f"({quadratic}); it would not catch a real one either"
        )


def measure(work, text: str) -> float:
    best = float("inf")
    for _ in range(REPETITIONS):
        start = time.perf_counter()
        work(text)
        best = min(best, time.perf_counter() - start)
    return best


def main() -> None:
    playwright_copy = RESIDUAL_MODULE.read_bytes()
    cypress_copy = CYPRESS_RESIDUAL_MODULE.read_bytes()
    assert playwright_copy == cypress_copy, (
        "the two residual_credentials.py copies have drifted; the budget "
        "below would then describe only one of the two shipped readers"
    )

    residual = load_module("residual_credentials_redos_budget", RESIDUAL_MODULE)
    redact = residual.build_assignment_redactor()
    header = residual.build_header_pattern()

    def work(text: str) -> None:
        # Every pattern the module hands the readers, on the same input: the
        # header pattern, the assignment redactor that walks every site and
        # splices, and the gate, which walks every site to check the marker and
        # sweeps the keyword-free shape table over the whole string.
        header.sub(residual.header_substitution, text)
        redact(text)
        residual.string_has_residual_credential(text)

    assert_growth_check_has_teeth()

    faulthandler.dump_traceback_later(WATCHDOG_SECONDS, exit=True)
    try:
        for name, build in INPUT_FAMILIES:
            timings = []
            for size in SIZES:
                text = build(size)
                elapsed = measure(work, text)
                timings.append(elapsed)
                assert elapsed < ABSOLUTE_CEILING_SECONDS, (
                    f"{name} at {len(text)} characters took {elapsed:.3f}s, "
                    f"over the {ABSOLUTE_CEILING_SECONDS}s ceiling; that is "
                    "catastrophic backtracking, not a slow machine"
                )
            assert_scales_linearly(name, timings)
            report = " ".join(
                f"{size}:{elapsed * 1000:.1f}ms"
                for size, elapsed in zip(SIZES, timings)
            )
            print(f"  {name}: {report}")
    finally:
        faulthandler.cancel_dump_traceback_later()

    print(
        "residual credential regex budget: pass "
        f"({len(INPUT_FAMILIES)} adversarial families, "
        f"{SIZES[0]}-{SIZES[-1]} characters, "
        f"absolute ceiling {ABSOLUTE_CEILING_SECONDS}s, "
        f"growth ceiling {MAX_GROWTH_PER_4X_STEP}x per 4x step)"
    )


if __name__ == "__main__":
    sys.exit(main())
