# Scanner 2.0.0 release check

This record measures the scanner correctness repair included in 2.0.0. It is a
bounded release check, not a general performance or model-quality benchmark.
The machine-readable observations are in [`report.json`](report.json).

## Claim and acceptance rule

The repair must preserve direct findings while removing false findings caused
by retry callbacks and shadowed Locator names. The repository regression suite
is the correctness gate. Real-repository timing is descriptive: the change is
acceptable when the three final outputs are stable across repetitions and its
runtime stays close to the immediate pre-fix tree. No speedup is claimed.

## Revisions and environment

- `origin/main`: `16463a426fa98e64ae62bfb1d9e24052dc20bb71`
- previous local 2.0.0 tag: `ed9489c9d9418e0dd1fd60a5cab6b1bef8006c5f`
- immediate pre-fix tree: `5e0650009505e04a1fb5226adee85854e939bebb`
- final scanner bytes: SHA-256
  `b919d26f8768034104abdd9f3bdc78b96754f66a3194eb8cf3cd5ae822d5936c`

Measurements ran on an Apple M1 Pro, arm64, macOS 26.5.2. Every scan used
`/bin/bash -p`, disabled ast-grep, disabled finding-based failure, and raised
the per-rule cap so truncation could not decide the comparison:

```bash
E2E_SMELL_DISABLE_AST_GREP=1 \
E2E_SMELL_FAIL_ON=none \
E2E_SMELL_MAX_RULE_HITS=10000 \
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh TARGET
```

Each arm ran three times in the same session. The targets were pinned to:

- the first ten sorted `react-router` integration specs importing Playwright at
  `7aea711dd1ae2bc5a076d13ff17291829690fa74`;
- all of `medium-zoom/cypress/integration` at
  `21332eb3c5abc181b48251a06ee19fd7792fab22`;
- all of `livestore/tests/integration/src/tests/playwright` at
  `583bf8420b43eb32b2335c22e440d14ad73c1b9c`.

## Result

| Target | origin/main | old 2.0.0 | pre-fix | final | Final vs pre-fix | Final output |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| React Router sample | 24.07 s | 24.01 s | 25.20 s | 25.38 s | +0.71% | 28 hits, 1,411 tokens |
| medium-zoom | 4.57 s | 4.20 s | 4.38 s | 4.40 s | +0.46% | 5 hits, 503 tokens |
| LiveStore | 10.90 s | 10.83 s | 11.27 s | 11.36 s | +0.80% | 14 hits, 1,138 tokens |

All three final outputs were byte-identical across their three repetitions.
Against the immediate pre-fix tree the median changes range from +0.46% to
+0.80%, so this check finds no material runtime regression. Against older
baselines the largest observed increase is +5.71%; the sample is too small to
separate implementation cost from run variance.

LiveStore is the only target where the older arms differ from the pre-fix and
final arms: the newer output contains one additional finding. Pre-fix and final
are byte-identical there, so that difference predates this repair.

## Scanner-report tokens

On the focused 87-line regression fixture, `tiktoken==0.11.0` with
`o200k_base` counted:

| Scanner report | Bytes | Tokens |
| --- | ---: | ---: |
| origin/main | 4,025 | 1,263 |
| old 2.0.0 tag | 4,025 | 1,263 |
| immediate pre-fix | 3,029 | 944 |
| final | 2,519 | 779 |

The final report is 484 tokens smaller than origin/main and the old tag
(-38.3%), and 165 tokens smaller than the immediate pre-fix report (-17.5%).
The final scanner was rerun on the same frozen source after the lexical-scope
repair; after path normalization its output remained byte-identical to the
measured 779-token report.

One diagnostic Codex call per endpoint consumed the two scanner reports as
input with model `gpt-6-sol`, ephemeral execution, and tools disabled. The
origin report used 16,967 input, 222 output, and 165 reasoning tokens; the final
report used 16,483 input, 111 output, and 55 reasoning tokens. The 484-token
input delta exactly matches the tokenizer result. This is one paired diagnostic,
not a statistical latency or cost claim; the final call also reported 9,600
cached input tokens while the origin call reported none.

## Boundary coverage

The committed scanner suite now checks retry callbacks at 0, 41, and 100 lines,
named aliases and namespace imports, direct assertions immediately outside the
callbacks, and Locator names shadowed by a block declaration, destructuring,
typed arrow/function parameters, typed object methods, a declaration after an
inline opening brace, and a `for` binding whose iterable contains an object
literal. A normal `if` block and the restored outer binding after each scope are
positive controls. These deterministic boundary cases are the release's
fuzz-style coverage; they do not constitute parser completeness.

## Limits

The timing sample is one machine, three repetitions, and three selected trees.
Concurrent exploratory full-root scans were stopped after five minutes for
React Router and SweetAlert2; a contended whole-repository LiveStore warm-up
completed in 257.18 seconds. Those exploratory runs are not included in the
table. Scanner-output token counts measure report size, not total agent context,
and the single model pair cannot establish a distribution.
