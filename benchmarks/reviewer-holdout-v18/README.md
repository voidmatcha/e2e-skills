# Reviewer holdout v18

V18 preregistered a release-confirmation run of the final 2.0.0 reviewer skill. It reuses the frozen v17 public, AI-authored 36-case corpus through the shared-corpus binding, at the v17 file and corpus digests. V17 tested a prompt-side Lean block that was not adopted; its result was not used to tune skill wording. Since v17, the skill changed only by the finding-heading level rule and documentation. The heading-level rule was checked on mutation recall: strict 33/36 and anchor-aware 34/36 versus a 35/36 baseline, with one flaky #3 mutant.

The single host is Codex `gpt-6-sol`, minimum `codex-cli 0.155.1`. The protocol pins the current skill digest and refuses another skill. It requires native `--output-schema`, usage capture, five repetitions, strict-majority scoring, v12 per-report thresholds, and v11's two-attempt infrastructure retry policy plus the opt-in `runner_auth_error` reason. The three arms run sequentially: full, catalog-only, no-skill. The primary gate requires a `PASS` full report, full minus no-skill stable F1 of at least +0.30, and a paired stratified bootstrap 95% lower bound greater than zero. Full minus catalog-only is descriptive without a lift gate. The v17 full-arm stable F1 of 0.964 on this same corpus is historical descriptive context.

This public corpus and single host support development evidence only. The model-authored cases and model-only adjudication, prior corpus exposure, and local runner identity limit any generalization claim.

Status: **run at clean commit `ebd34a2` on Codex `gpt-6-sol`; arm comparison `INCONCLUSIVE` (`arm_input_incomplete`), so no skill-lift claim**.

## Result

The three arm reports and `arm-comparison.json` are in `reports/`, copied byte for byte from the external run cache. Of 540 scheduled calls, 537 scored: full and catalog-only scored 180/180 each, and no-skill scored 177/180. There were 0 retries, including 0 `runner_auth_error` retries. Full passed its per-report thresholds; catalog-only failed stable precision (0.870 < 0.95), repeated precision (0.865 < 0.90), and stable guard-hit rate (0.10 > 0.05). No-skill is `INCONCLUSIVE` because three calls were unscoreable.

The unscoreable no-skill calls were `v17-pw-09` repetition 3, `v17-cy-04` repetition 5, and `v17-pw-06` repetition 2. Each ended with `unexpected tool or item in Codex event stream`, the runner's fail-closed guard. This is not a retryable reason under the frozen protocol, so each had one attempt. The comparator returned `INCONCLUSIVE` (`arm_input_incomplete`) and withheld matrix metrics.

Descriptive strict-majority metrics from each arm report, which support no preregistered comparison claim:

| Arm | Status | Scored calls | Stable TP / FP / FN | Stable P / R / F1 | Repeated TP / FP / FN |
|---|---|---:|---|---|---|
| full | `PASS` | 180 | 40 / 2 / 0 | 0.952 / 1.000 / 0.976 | 200 / 11 / 0 |
| catalog-only | `FAIL` | 180 | 40 / 6 / 0 | 0.870 / 1.000 / 0.930 | 198 / 31 / 2 |
| no-skill | `INCONCLUSIVE` | 177 | 16 / 29 / 24 | 0.356 / 0.400 / 0.376 | 80 / 159 / 117 |

Full minus no-skill descriptive stable F1 is +0.599, above the preregistered +0.30 point threshold. The incomplete matrix prevents the paired-bootstrap comparison and **does not satisfy the gate**. Full minus catalog-only descriptive stable F1 is +0.045; v17's full-arm 0.964 is historical context only.

**Follow-up.** [V19](../reviewer-holdout-v19/README.md) completed the same-corpus, same-skill rerun with an opt-in unexpected-item retry and returned `PASS`; v18's frozen retry policy and reports remain unchanged.

## Exact run commands

The official run wrote its reports outside the checkout to preserve clean Git provenance. To reproduce it, run these commands sequentially from a clean checkout at `ebd34a2`, using an explicit trusted Codex executable. `$OUT` must be a durable cache path outside the checkout, with no symlinks. The comparator exits nonzero for this `INCONCLUSIVE` result while still writing its report; copy the completed reports afterward.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v18-ebd34a2"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v18 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"
python3 scripts/evals/run-reviewer-holdout.py --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v18.json --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol --arm full --repetitions 5 --allow-live --report-only --output "$OUT/full.json"
python3 scripts/evals/run-reviewer-holdout.py --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v18.json --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol --arm catalog-only --repetitions 5 --allow-live --report-only --output "$OUT/catalog-only.json"
python3 scripts/evals/run-reviewer-holdout.py --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v18.json --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol --arm no-skill --repetitions 5 --allow-live --report-only --output "$OUT/no-skill.json"
python3 scripts/evals/compare-reviewer-holdouts.py "$OUT/full.json" "$OUT/catalog-only.json" "$OUT/no-skill.json" --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v18.json --compare-arms --output "$OUT/arm-comparison.json"
mkdir -p benchmarks/reviewer-holdout-v18/reports
cp "$OUT/full.json" "$OUT/catalog-only.json" "$OUT/no-skill.json" "$OUT/arm-comparison.json" benchmarks/reviewer-holdout-v18/reports/
```

Expected schedule: 36 cases × 5 repetitions × 3 arms = **540 scheduled model calls**, with at most **540 additional retry attempts** under the pinned infrastructure policy.
