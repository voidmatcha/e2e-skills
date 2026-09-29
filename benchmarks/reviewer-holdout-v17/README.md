# Reviewer holdout v17

V17 preregistered a public development comparison of three prompt arms on 36 original synthetic Playwright and Cypress cases. Codex `gpt-6-sol` authored the cases and labels with current reviewer references in view. A Claude subagent and Codex `gpt-6-sol` labeled all 36 cases blind from sources and skill only; 35 of 40 author findings matched both. A Claude subagent arbiter resolved disputes from quoted reference text on 2026-09-28. No human labeled. The blind outputs and adjudication ledger are in `labeling/`.

The primary hypothesis is that adding the compiled Lean 4 severity model to the catalog improves instance-severity, anchoring, and consolidation decisions. The model was written by this project after the v16 result. The `catalog-formal` arm embeds `references/pattern-reference.md`, then the verbatim `scripts/dev/reviewer-contract/ReviewerContract.lean`, with its SHA-256 pinned in the protocol. `catalog-only` embeds the catalog alone; `full` embeds the existing full reviewer prompt. There is no no-skill arm. The host is Codex `gpt-6-sol`, with a minimum `codex-cli 0.155.1` floor and enforced `--output-schema`. The schedule has five repetitions per case and arm, strict-majority scoring, usage capture, and at most one infrastructure retry per scheduled call.

The fixed primary comparison is catalog-formal minus catalog-only stable F1 with a paired stratified case bootstrap. “Formal helps” requires a point delta of at least +0.03, a 95% bootstrap lower bound greater than zero, and no rise in stable guard-hit rate. The secondary comparison repeats the F1 delta on the explicit case IDs in `formal_comparison.secondary_case_ids`; full versus catalog-only is descriptive. Per-report absolute thresholds follow v12. This public, AI-authored corpus and one host support development evidence only.

Status: **run at `085f99b` on Codex `gpt-6-sol`; `FAIL` (`formal_comparison_gate_not_met`)**. The formal model did not improve this public development holdout.

## Result

The three arm reports and `arm-comparison.json` are in `reports/`, copied byte for byte from the external run cache. All 540 scheduled calls scored on the first attempt, with 0 infrastructure errors and 0 retries.

| Arm | Stable F1 | Stable guard-hit rate |
|---|---:|---:|
| catalog-only | 0.941 | 0.10 |
| catalog-formal | 0.920 | 0.10 |
| full | 0.964 | 0.00 |

Catalog-formal minus catalog-only stable F1 was −0.022 (paired 95% interval −0.052 to 0.000). On the 20-case secondary subset it was −0.017 (−0.054 to 0.000). The primary point estimate and lower bound miss the preregistered improvement gate; the stable guard-hit rate did not rise. Full minus catalog-only stable F1 was +0.023, a descriptive comparison only.

The catalog-formal arm added two stable, unlabeled `#1` P0 predictions: `v17-pw-09` at `tests/tag-forge.spec.ts:3` and `v17-pw-15` at `tests/chimes.spec.ts:2`. It dropped two stable optional-label matches: `#10f` on `v17-cy-10` and `#4i` on `v17-pw-02`. These are the four stable-prediction differences between catalog-only and catalog-formal.

**Follow-up.** The Lean model is not added to the skill prompt. It remains a developer-side consistency check in `scripts/dev/reviewer-contract.py`.

## Reproduction commands

The official run wrote its reports outside the checkout to preserve clean Git provenance. To reproduce it, run these sequentially from a clean checkout at `085f99b`, with a trusted explicit Codex executable. Keep `$OUT` on a path without symlinks and copy the finished reports into the benchmark directory afterward.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v17-085f99b"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v17 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"
python3 scripts/evals/run-reviewer-holdout.py --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v17.json --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol --arm catalog-only --repetitions 5 --allow-live --report-only --output "$OUT/catalog-only.json"
python3 scripts/evals/run-reviewer-holdout.py --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v17.json --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol --arm catalog-formal --repetitions 5 --allow-live --report-only --output "$OUT/catalog-formal.json"
python3 scripts/evals/run-reviewer-holdout.py --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v17.json --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol --arm full --repetitions 5 --allow-live --report-only --output "$OUT/full.json"
python3 scripts/evals/compare-reviewer-holdouts.py "$OUT/catalog-only.json" "$OUT/catalog-formal.json" "$OUT/full.json" --cases scripts/evals/reviewer-holdout-v17.json --protocol scripts/evals/reviewer-validation-protocol-v17.json --compare-arms --output "$OUT/arm-comparison.json"
mkdir -p benchmarks/reviewer-holdout-v17/reports
cp "$OUT/catalog-only.json" "$OUT/catalog-formal.json" "$OUT/full.json" "$OUT/arm-comparison.json" benchmarks/reviewer-holdout-v17/reports/
```

Expected schedule: 36 cases × 5 repetitions × 3 arms = **540 model calls**, with up to 540 additional attempts only for the preregistered infrastructure retry conditions. The comparator exits 1 for this `FAIL` result while still writing `arm-comparison.json`; run the copy command after that expected exit.
