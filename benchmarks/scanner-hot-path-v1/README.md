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
| Before (v1.17.0, `fbcee47`) | 30.9 s | 103 ms |
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
and rule startup as much as by per-hit work, so a 3.4x gain here does not
predict a 3.4x gain on an arbitrary repository. Nothing here measures review
quality.
