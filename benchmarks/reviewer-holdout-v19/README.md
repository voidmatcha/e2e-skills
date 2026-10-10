# Reviewer holdout v19

V19 preregisters a rerun of v18 for 2.0.0 release confirmation. It uses the same frozen v17 public, AI-authored 36-case corpus and digests, the same pinned reviewer skill digest (`aa88145dda8b95fcd7c59cbf64de28ae4beeafe3451b739a46ae202b3cb0d57f`), Codex `gpt-6-sol` with minimum `codex-cli 0.155.1`, native output-schema enforcement, usage capture, and five strict-majority repetitions. Its three arms run sequentially: full, catalog-only, no-skill. The v18 decision rule remains: full must pass v12 per-report thresholds, full minus no-skill stable F1 must be at least +0.30 with paired stratified bootstrap 95% lower bound greater than zero; full minus catalog-only is descriptive. The only operational change is an opt-in `codex_unexpected_stream_item` infrastructure retry, allowing one fresh call at the same schedule position. If the retry also emits the unexpected item, the call remains unscoreable.

V18 on this same corpus and skill was **INCONCLUSIVE** because three no-skill calls failed the tools-disabled Codex event-stream guard. Descriptive stable F1 was full 0.976, catalog-only 0.930, and no-skill 0.376. V19 is a rerun to obtain a complete matrix, **not fresh independent evidence**. The public model-authored corpus and single host limit generalization. The completed v19 run confirms v18 on the same corpus and skill; it is not fresh evidence.

Status: **PASS** (`release_confirmation_passed`) at clean commit `1723a34` on Codex `gpt-6-sol`.

## Result

The three arm reports and `arm-comparison.json` in `reports/` were copied byte for byte from the external run cache. All **540/540** scheduled calls scored (180/180 per arm). There were **0 retries of any reason** and no `codex_unexpected_stream_item` occurrence. Full passed all per-report thresholds; catalog-only and no-skill failed their per-report thresholds.

| Arm | Report status | Scored calls | Stable F1 |
|---|---|---:|---:|
| full | `PASS` | 180/180 | 0.976 |
| catalog-only | `FAIL` | 180/180 | 0.941 |
| no-skill | `FAIL` | 180/180 | 0.405 |

Full minus no-skill strict-majority stable F1 was **+0.571**, paired stratified bootstrap 95% CI **[+0.411, +0.738]**. The frozen release-confirmation rule passed. Full minus catalog-only was **+0.034**, 95% CI **[0.000, +0.072]**; this comparison is descriptive and has no lift gate. This is a single-host development result on the same public, model-authored corpus and same skill as v18, not an independent replication.

The comparator crashed with a `KeyError` on the first complete v18/v19 matrix: its generic lift path had not implemented the frozen v18/v19 decision block. After the model run, the comparator was fixed to implement that frozen rule exactly, with regression tests. The recorded `arm-comparison.json` is the corrected comparator's output. **No thresholds were changed.**

## Exact run commands

From a clean checkout containing this protocol, set `CODEX_RUNNER` to the trusted executable path. Run the arms in order. `$OUT` is a durable cache directory outside the checkout; the comparator writes its report even when it exits nonzero for `FAIL` or `INCONCLUSIVE`. Review the reports before copying them into the benchmark directory.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v19"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v19 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"
python3 scripts/evals/run-reviewer-holdout.py --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v19.json --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol --arm full --repetitions 5 --allow-live --report-only --output "$OUT/full.json"
python3 scripts/evals/run-reviewer-holdout.py --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v19.json --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol --arm catalog-only --repetitions 5 --allow-live --report-only --output "$OUT/catalog-only.json"
python3 scripts/evals/run-reviewer-holdout.py --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v19.json --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol --arm no-skill --repetitions 5 --allow-live --report-only --output "$OUT/no-skill.json"
python3 scripts/evals/compare-reviewer-holdouts.py "$OUT/full.json" "$OUT/catalog-only.json" "$OUT/no-skill.json" --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v19.json --compare-arms --output "$OUT/arm-comparison.json"
```

Expected schedule: 36 cases × 5 repetitions × 3 arms = **540 scheduled calls**, with at most one retry per call. The protocol SHA-256 is `e1bdc533f596884d0b3de286882bb97aeca5327010e59b65df47c8fe2ebfc90b`.
