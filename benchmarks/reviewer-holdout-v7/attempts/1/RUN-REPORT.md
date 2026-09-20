# Reviewer holdout v7 run report

## Outcome

The matrix stopped after the `full` arm, as required by the frozen stop conditions. The arm recorded 35 infrastructure errors and exited with report status `INCONCLUSIVE` (process exit code 2). It was not rerun. The `catalog-only` and `no-skill` arms were not started, and the comparator was not run.

- Worktree: `bench/v7-run` at `110f2ea6a6e4876f601fa3b2cb6bd2ead40e48ab`
- Cases SHA-256: `50c828c5e267a683ced73a161a645af0b73f305f6391b6fe0e8ee150ec419849` (matched frozen README)
- Protocol SHA-256: `e379edfc7ad04e4ff92134f3f5952bda7f146e0f80667726283a2a60de08daf2` (matched frozen README)
- Matrix calls: 60/180 scheduled calls attempted; 25/180 successful and scoreable.

## Arm 1: full

```bash
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --runner codex --runner-path ~/.local/bin/codex --model gpt-5.6-sol \
  --arm full --repetitions 3 --allow-live --report-only \
  --output benchmarks/reviewer-holdout-v7/reports/full-codex.json
```

- Start: 2026-09-19T15:06:27.350560+00:00 / 2026-09-20T00:06:27.350560+09:00
- End (`created_at`): 2026-09-19T16:56:47.463418+00:00 / 2026-09-20T01:56:47.463418+09:00
- Elapsed: 1:50:20.112858
- Runs: 60; successful runs: 25; infrastructure errors: 35
- Report status: `INCONCLUSIVE`; `complete: false`; `execution_complete: false`; `release_eligible: false`
- Status reason, verbatim: `35 scheduled runs were not scoreable`

Summary metrics printed by the runner:

| Metric | Value |
|---|---:|
| TP / FP / FN | 31 / 2 / 1 |
| Precision | 0.9393939393939394 |
| Recall | 0.96875 |
| F1 | 0.9538461538461539 |
| Runs / successful runs / infrastructure errors | 60 / 25 / 35 |

Runner identity recorded in the report:

| Field | Recorded value |
|---|---|
| Runner / model | `codex` / `gpt-5.6-sol` |
| Requested runner path | `~/.local/bin/codex` |
| Resolved `runner_executable` | `/Users/user/.codex/packages/standalone/releases/0.154.0-aarch64-apple-darwin/bin/codex` |
| `runner_identity` | `codex-cli 0.154.0` |
| `reasoning_effort` | `null` |
| Identity policy / match | `minimum` / `exact` |

Infrastructure errors, verbatim: every failed run recorded `error: "timeout"`, `exit_code: 124`, and `duration_ms: 180000`. Failed schedule entries (`ordinal:case:repetition`) were:

```text
3:cy-c03:2   4:pw-a04:1   8:pw-c01:1   9:pw-a04:3   10:cy-a02:2
11:pw-c04:3  13:pw-a06:1  14:cy-a05:1  16:cy-c01:2  17:cy-c01:3
19:cy-c03:3  21:cy-a04:1  23:pw-c02:2  24:cy-c03:1  25:pw-a02:3
26:cy-c02:2  29:cy-c02:3  33:pw-a03:1  34:pw-a06:2  35:pw-a03:3
36:cy-c01:1  37:cy-c04:3  38:cy-c04:2  47:cy-c04:1  50:pw-c04:2
51:cy-a03:1  52:cy-a04:2  53:pw-a05:1  54:pw-a03:2  55:pw-a06:3
56:cy-a03:3  57:pw-a05:2  58:pw-a05:3  59:cy-a02:1  60:cy-c02:1
```

## Arm 2: catalog-only

```bash
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --runner codex --runner-path ~/.local/bin/codex --model gpt-5.6-sol \
  --arm catalog-only --repetitions 3 --allow-live --report-only \
  --output benchmarks/reviewer-holdout-v7/reports/catalog-only-codex.json
```

Not started because the full arm reported infrastructure errors. Start/end time, runs, successful runs, infrastructure errors, summary metrics, and runner identity are unavailable because no report was produced.

## Arm 3: no-skill

```bash
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --runner codex --runner-path ~/.local/bin/codex --model gpt-5.6-sol \
  --arm no-skill --repetitions 3 --allow-live --report-only \
  --output benchmarks/reviewer-holdout-v7/reports/no-skill-codex.json
```

Not started because the full arm reported infrastructure errors. Start/end time, runs, successful runs, infrastructure errors, summary metrics, and runner identity are unavailable because no report was produced.

## Comparator

```bash
python3 scripts/evals/compare-reviewer-holdouts.py \
  benchmarks/reviewer-holdout-v7/reports/full-codex.json \
  benchmarks/reviewer-holdout-v7/reports/catalog-only-codex.json \
  benchmarks/reviewer-holdout-v7/reports/no-skill-codex.json \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --output benchmarks/reviewer-holdout-v7/reports/arm-comparison.json
```

Comparator decision: **not produced**. It was not run because the full arm was incomplete and the two control reports do not exist.

Frozen full-arm absolute gates:

| Metric | Threshold |
|---|---:|
| Stable precision | >= 0.95 |
| Stable recall | >= 0.85 |
| P0 stable-label recall | >= 0.90 |
| Stable guard-hit rate | <= 0.05 |
| Clean-case specificity | >= 0.95 |
| Case macro recall | >= 0.80 |
| Pattern macro recall | >= 0.80 |
| Framework macro recall | >= 0.80 |
| Repeated precision | >= 0.90 |

Frozen lift gates, each required independently for both `full` vs. `catalog-only` and `full` vs. `no-skill`:

| Metric | Threshold |
|---|---:|
| Stable F1 delta | >= 0.05 |
| Stable F1 delta paired-bootstrap 95% CI lower bound | >= 0.01 |
| Stable precision delta | >= -0.02 |
| Stable recall delta | >= -0.02 |
| Clean-case specificity delta | >= 0 |
| Repeated precision delta | >= 0 |

The protocol also fixes singleton-host agreement gates at stable-prediction Jaccard >= 0.80 and stable-recall gap <= 0.10; no values or decision were produced.

## Unexpected observations

- The full arm took 1:50:20 rather than the README's rough 12:41 historical reference. The report explains most of the difference: 35 calls each reached the fixed 180-second timeout.
- The specified runner's version preflight printed `WARNING: proceeding, even though we could not create PATH aliases: Operation not permitted (os error 1)` before `codex-cli 0.154.0`. This did not prevent launch; 25 calls completed and the expected identity was recorded.
- A separate read-only liveness probe during the long silent run was denied with `zsh:1: operation not permitted: ps`. It did not affect the benchmark or files and was not a runner-launch error.
- No usage/rate-limit error or reset time was reported.
- No arm was rerun, no alternate sandbox setting was used, and no comparator/control arm was started after the infrastructure-error stop condition.
