# Reviewer holdout v6 evidence — incomplete

Protocol `reviewer-holdout-v6` never produced a complete preregistered matrix. Reviewer holdout v6 did execute its nine preregistered cells once. The incomplete archive is caused by post-run report loss: four reports were lost before they were copied out of temporary directories. Finishing the matrix now requires manually re-fetching a CLI build that the standard installer no longer keeps. CLI rotation is the rerun obstacle, not the reason those first-run reports are missing. This directory preserves the five reports that survived, the driver logs, and the rerun obstacle, rather than deleting a partial run.

No v6 accuracy result is claimed. No skill-lift result is claimed.

## Rerun obstacle

v6 preregisters an exact CLI identity:

```
codex:  codex-cli 0.149.0
claude: Claude Code 2.1.239
```

`scripts/evals/run-reviewer-holdout.py` enforces that identity by equality and refuses to run on any other build. The Claude Code installer keeps only a short window of versions, and `2.1.239` is no longer among them locally; the retained builds are `2.1.247`, `2.1.248`, `2.1.250`, `2.1.251`. The codex build is still installed, but `arm_comparison.required_matrix` is `exact-three-profiles-by-three-hosts`, and six of the nine cells need the Claude host.

This is not a permanent loss. The vendor release channel still serves both `2.1.239` and v5's `2.1.220`, and the runner takes an explicit `--runner-path` with no trusted-root restriction, matching identity on `--version` output alone. Re-fetching the pinned build and passing its path would complete the matrix. What the exact pin actually costs is that a protocol stops being runnable from an ordinary checkout the moment the local installer rotates the build, which is also what stalled v5. Treat CDN retention as convenience, not a guarantee. See the "Execution identity drift" section of `../STATUS.md`.

## What survived

Nine cells were preregistered. Every cell ran once. CLI rotation is the rerun obstacle, not the reason those first-run reports are missing. Four reports were lost before they were copied out of a temporary directory (`full-codex`, `catalog-only-codex`, `no-skill-codex`, `full-opus`), and the archived logs preserve only their aggregate summary lines. Five reports remain, in `reports/`:

| Report | Arm | Model | Execution complete | Status | Unique P / R / F1 | Infra errors |
| --- | --- | --- | --- | --- | --- | --- |
| `no-skill-opus.json` | no-skill | claude-opus-5 | yes | FAIL | 0.441 / 0.625 / 0.517 | 0/60 |
| `catalog-only-opus.json` | catalog-only | claude-opus-5 | yes | FAIL | 0.885 / 0.958 / 0.920 | 0/60 |
| `no-skill-fable.json` | no-skill | claude-fable-5 | no | INCONCLUSIVE | 0.452 / 0.583 / 0.509 | 2/60 |
| `catalog-only-fable.json` | catalog-only | claude-fable-5 | no | INCONCLUSIVE | 0.913 / 0.875 / 0.894 | 6/60 |
| `full-fable.json` | full | claude-fable-5 | no | INCONCLUSIVE | 0.882 / 0.625 / 0.732 | 22/60 |

Metrics are the protocol's primary unit: unique majority-stable labels and predictions, not repeated run totals.

## How to read these numbers

**`FAIL` on a control arm is the expected outcome, not a defect.** The protocol applies one threshold set to every arm, including `no-skill`. A baseline arm that receives no pattern contracts is supposed to miss those thresholds. Read `status_reasons` in each report for the specific metric.

**The `full` arm has no usable report on any host.** `full-codex` and `full-opus` were both lost. `full-opus` did run to completion — `opus.log` preserves its aggregate line (60/60 scoreable, 0 infrastructure errors, precision 0.907, recall 0.944, `FAIL` on thresholds) — but only that summary survives, not the per-run records the protocol's primary unique majority-stable metric is computed from. `full-fable` lost 22 of 60 scheduled runs, and a label needs 2 of 3 repetitions to become majority-stable, so the missing runs suppress stable labels and depress its unique recall (0.625). That figure is an artifact of infrastructure loss and must not be read as the full arm performing worse than `catalog-only`.

**Only one arm contrast is defensible here:** `no-skill-opus` against `catalog-only-opus`. Both are execution-complete with zero infrastructure errors, same host, same model, same corpus:

| | Unique precision | Unique recall |
| --- | --- | --- |
| no-skill | 0.441 | 0.625 |
| catalog-only | 0.885 | 0.958 |

That is a single-host, single-model contrast on an inspectable public development corpus. It is directionally consistent with the degraded fable pair, and it is not a generalization result.

## What this evidence does not support

Every report carries `release_eligible: false`, `evidence_scope: "development"`, and `corpus_visibility: "public-development"`, with the corpus declaring:

> Frozen public development corpus for balanced cross-provider regression
> measurement. It is not sealed and does not establish generalization.

The reports also record `development_only_no_release_isolation_attestation`. Nothing here is a release gate, a generalized reviewer accuracy figure, or a sealed holdout result. A release-grade run needs an external sealed `--cases` bundle and an independently isolated environment; the bundled harness records wrapper isolation as not proven and keeps such a report `INCONCLUSIVE`.

## Files

- `reports/*.json` — the five surviving reports, with raw model output, parsed findings, per-case scores, and provenance. Not rewritten or rescored.
- `driver-{codex,opus,fable}.log` — per-host driver timing and exit codes.
- `codex.log`, `opus.log`, `fable.log`, `redo.log` — runner console output, including the summary lines for the four reports that were later lost.

Absolute paths in these artifacts use the `/Users/user` placeholder, not a contributor identity.
