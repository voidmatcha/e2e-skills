# Scanner hot path v1 — per-hit cost on a pinned dense fixture

The bundled scanner spent roughly a tenth of a second per reported hit, so a
dense file turned a review into minutes of waiting. This record fixes the
fixture, the measurement, and the acceptance rule, and reports what changed.

## Acceptance rule

**Byte-identical output is the gate; speed is the hypothesis.** An optimization
is acceptable only when the scanner's stdout and exit code are unchanged on the
comparison set below. A speed target does not license a different verdict on any
file.

## Fixture (pinned)

[`make_fixture.py`](make_fixture.py) writes one spec whose every third line is a
hit: a positional `.first()` (`#10a`), a web-first assertion, and a one-shot
`textContent()` read (`#4c-4e`). The 300-hit fixture is the measured case; the
generator takes `--hits` so the same shape scales.

```bash
python3 benchmarks/scanner-hot-path-v1/make_fixture.py /tmp/dense300 --hits 300
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh /tmp/dense300
```

## Measurement

macOS 15 on Apple silicon, `/bin/bash -p` (bash 3.2), ripgrep 15.2.0, Tier 1
off, Tier 2 from the deterministic host binary. Wall clock, single run per
configuration, same machine and same fixture.

| Configuration | 300-hit fixture | Per hit |
| --- | ---: | ---: |
| Before (the 1.17.0 scanner, before this change) | 30.9 s | 103 ms |
| After all three changes | 7.5 s | 25 ms |

**4.1x faster.** A separate 100-hit run moved 12.3 s to about 4 s, so the gain
is in the per-hit path rather than in startup.

## What changed

A `bash -x` trace with per-line timestamps attributed the time before blaming
anything:

1. **`// JUSTIFIED:` resolution was quadratic.** `_line_is_justified` ran one
   awk pass per hit, and each pass lexed the file from line 1 to the hit. The
   same program now reports every justified line in one pass per file
   (`_justified_lines_in_file`), and the per-hit check is a cached lookup. The
   classification rules are unchanged; only the driver changed.
2. **Path resolution and temp allocation forked per hit.** `absolute_hit_file`
   re-resolved the same few paths hundreds of times through a subshell, and
   `allocate_temp` ran `mktemp` for every scratch file. Resolution is now
   memoized per spelling, including failures, and file allocation uses a private
   counter inside the scanner's own 0700 temp root. Directory allocation still
   uses `mktemp`. Both caches are parallel arrays walked linearly: bash 3.2 has
   no associative arrays, and the security gate refuses `eval` in shipped shell.

## Output equality check

Identical stdout and exit code on: the 300-hit fixture; the repository's own
`skills/`, `scripts/`, and `skills/e2e-reviewer/evals/files/` trees; and ten
adversarial fixtures covering JUSTIFIED forms, regex literals with quotes,
option-object chains, multi-line chain heads, CRLF, tokenizer edge cases, and
focused-suite forms. `test-reviewer-scanner.py` (including `--preflight-only`),
`test-scanner-bounded-rule-v1.py`, and `test-scanner-conditional-discovery.py`
all pass.

## Limits

One machine, one dense synthetic shape, single runs — this is a before/after
record, not a distribution. Real repositories are dominated by file discovery
and rule startup as much as by per-hit work, so a 4.1x gain here does not
predict a 4.1x gain on an arbitrary repository. Nothing here measures review
quality.

## Addendum 2026-09-18: one real repository

A descriptive check of the Limits section above, not a new acceptance test: one machine (Apple silicon, macOS), one run per version, the same ast-grep 0.45.3 binary pinned through `E2E_SMELL_AST_GREP_BIN`, ESLint download off. Target: `apps/web/playwright` in `calcom/cal.com` at `e91bb0c`, the directory that holds most of its Playwright specs; the repository root itself was refused by both versions' symbolic-link preflight, as designed.

| Scanner | Wall time | Summary line |
|---|---:|---|
| v1.16.3 | 212 s | 812 hits, 2 P0, 33 P0 candidates |
| 1.18.0 working tree | 192 s | 813 hits, 2 P0, 34 P0 candidates |

About 10% faster, which is what the Limits section predicts for a repository whose time is not dominated by per-hit JUSTIFIED resolution. The outputs differ by exactly one hit: the newer scanner reports a `#5a` candidate at `embed-code-generator.e2e.ts:471` that v1.16.3 missed, because the regex literal `/.*Cal\.ns[^(]+\("ui/` on line 410 contains a double quote that the older lexer read as the start of a string. That is the regex-literal fix in 1.17.0 working on real code.

A second repository, `ever-gauzy` at `54b537b`, was not measured: v1.16.3 was stopped after more than 64 minutes, with nearly all of its CPU time in the `scope-worker.py` scope-graph helper rather than in the code this benchmark changed. The hot-path change did not touch that helper, so its cost on large monorepos was left as an open performance question, not a result; the next addendum answers it.

## Addendum 2026-09-19: the scope-worker validation cost

The ever-gauzy question above has an answer. With the C-locale fix a full scan of `ever-gauzy` at `54b537b` completes, and an instrumented copy of the scanner showed where its time went: 5,932 s in total, of which 4,683 s was `scope-worker.py` re-validating every recorded dependency (about 240,000 paths at the end, roughly 0.44 s per pass) before and after each of its 5,568 operations. The queries themselves took 123 s.

The worker now re-stamps only the sources and resolution candidates each query traversed, and validates the full set at every tier checkpoint and before the Summary. Same machine, same revision, one run each:

| Target | Before | After | Output |
|---|---:|---:|---|
| `ever-gauzy` full scan | 5,932 s | 1,226 s | byte-identical |
| cal.com `apps/web/playwright` (7 scope queries) | 171 s | 171 s | byte-identical |

About 4.8x on the repository whose scope graph is large, and no change where the scope worker was already idle. The cal.com pair is a later pair of runs than the 192 s above, with the C-locale fix in both; run-to-run variance on this machine was not measured.
