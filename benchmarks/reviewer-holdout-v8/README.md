# Reviewer holdout v8

Reviewer holdout v8 is a Codex-only rerun protocol for the v5 public-development cases. It keeps the v7 host, prompt arms, thresholds, schedule seed, and strict-majority stability rule. It changes how sources are shown to the model, revises three labels in a separate corpus file, and raises each arm to five repetitions.

Status: **run at `56e4b0f`; arm comparison `FAIL`, so no skill-lift claim**. The corpus is public development evidence that was inspected while this protocol was designed; it is not sealed and does not establish generalization.

## Result

The counted run is attempt 2, in `reports/`. Attempt 1, in `attempts/1/`, was `INCONCLUSIVE` because 2 of the 100 full-arm calls were not scoreable (infrastructure errors). It contributes no metric.

| Arm | Status | Stable P / R / F1 | Repeated TP / FP / FN |
|---|---|---|---|
| full | `PASS` | 1.000 / 1.000 / 1.000 | 107 / 0 / 3 |
| catalog-only | `PASS` | 1.000 / 1.000 / 1.000 | 108 / 3 / 2 |
| no-skill | `FAIL` | 0.359 / 0.636 / 0.459 | 70 / 134 / 40 |

The arm comparison is `FAIL`. Against no-skill, the full arm's stable F1 lift was +0.541 with a 95% lower bound of +0.424, above the preregistered thresholds. Against catalog-only, the lift was 0.000 because both arms reached the ceiling, so the required +0.05 was not met. The full workflow is not shown to add accuracy over the pattern catalog alone on this corpus. The 20 cases are too easy to separate the two arms, and v8 cannot say more than that.

## Why v8 exists

Seven single 60-call runs of the v7 full arm (Codex `gpt-5.6-sol`, prompt-complete, tools disabled) swung between `PASS` and `FAIL`. No wording effect was established. The variance had three causes:

1. **Unnumbered sources and an exact-line scorer.** The v7 prompt embeds each source file without line numbers, while the scorer matches the exact `(pattern_id, severity, file, line)` tuple. On `pw-a04` the model often cited `#15` at `profile.spec.ts:8` and `#16` at `:9` instead of `9` and `10`. Each offset counted as one false negative plus one false positive.
2. **Three labels that the current contracts leave ambiguous or unreachable.**
   - `V5-008` (`#13` P1, `tests/profile.spec.ts:7`, case `pw-a04`) cannot be reached. The `#13` v2 ownership contract in `skills/e2e-reviewer/references/pattern-reference.md` says a navigation-only POM or a missing method is not ownership evidence, and `pages/profile-page.ts` has only `open()`.
   - `V5-007` (`#12` P0, `tests/billing.spec.ts:14`, case `pw-a03`) is equally readable as `#1` P0 at the test declaration on line 13: the test is named "opens the team invoices route" but asserts the `Sign in` heading.
   - `V5-026` (`#22` P1, `cypress/e2e/board.cy.ts:6`, case `cy-a06`) is a contract boundary. `Board.tsx` updates optimistically, and the test title promises UI state only, not a backend call.
3. **Three repetitions.** With three repetitions, a single rotating miss or extra prediction decides whether a label is stable.

## Differences from v7

- **Numbered source lines.** For v8 only, every embedded source line is prefixed with its 1-based number, right-aligned to six columns, and a tab, the same format `nl -ba` prints. The prompt states that the numbers are display-only and that findings must cite them. The scorer still matches exact lines. Protocols v2–v7 keep their prompts byte for byte.
- **Revised labels in `scripts/evals/reviewer-holdout-v8.json`.** The cases, source files, and every other label are copied from v5 unchanged. Label IDs are stable, and each change is recorded with its reason in the top-level `label_revisions` array and in the label's `reason` field:
  - `V5-007` keeps `#12` P0 at line 14 and adds `accepted_alternatives` with `#1` P0 at line 13. A report on either tuple is the same single true positive; reporting both still counts once.
  - `V5-008` becomes an `fp_guard`. Reporting `#13` at `tests/profile.spec.ts:7` counts as a guard hit and a false positive.
  - `V5-026` becomes `optional`. A matching report is neither a true positive nor a false positive, a missing one is not a false negative, and matches are counted separately as `optional_matched_ids` per run and `stable_optional_matches` per report.
- **Stability over the revised label set.** A finding label is stable when a strict majority of repetitions matched any of its accepted tuples, so a model that alternates between line 13 `#1` and line 14 `#12` still earns one stable true positive for `V5-007`, which stays a P0 label. `V5-026` is excluded from recall and P0 denominators; `V5-008` counts toward the guard hit rate. Precision, recall, macro recall, and clean-case specificity keep their v7 definitions.
- **Five repetitions.** `default_repetitions` and `release_repetitions` are both 5, so a label needs three of five hits to be stable.
- **Runner floor.** `execution_identity.version_policy` is `minimum` with expected `codex-cli 0.155.1`. Every report still records the resolved CLI identity, and the comparator requires one identical identity across the three arms.

The protocol binds its corpus by path and digest in a `corpus` block and declares the scoring rules in a `scoring` block. The runner and comparator refuse a v8 protocol with any other corpus, and refuse a revised-label corpus with any earlier protocol.

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v8.json
cases SHA-256: 85f072589d5d3f3cb32aa478f8872682f3cff29014d1b06e6d8b4f01d7a8fe97
corpus SHA-256: 15a53df7366b229bf76bf1b5f22a7a4e6a8580ee18623397678a5f2022665c86
protocol: scripts/evals/reviewer-validation-protocol-v8.json
protocol SHA-256: 87a9e0b7c6a0b891862d370fb6e260cda0bf7de03e803d14b1ce797f1ddcb1ab
```

## Exact rerun command

Run the three cells sequentially from the repository root in an ordinary host shell, not from inside a Codex sandbox. A nested `codex` call from a workspace-write sandbox hangs until timeout. Start from a clean tree so every arm records the same Git provenance. Set `CODEX_RUNNER` once to the explicit executable that reports `codex-cli 0.155.1` or later; do not use a changing command name between cells. Keep all generated reports outside the checkout until the comparison is complete, then copy the four JSON artifacts into the benchmark directory.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v8"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v8 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v8.json \
  --protocol scripts/evals/reviewer-validation-protocol-v8.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-codex.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v8.json \
  --protocol scripts/evals/reviewer-validation-protocol-v8.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm catalog-only --repetitions 5 --allow-live --report-only \
  --output "$OUT/catalog-only-codex.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v8.json \
  --protocol scripts/evals/reviewer-validation-protocol-v8.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm no-skill --repetitions 5 --allow-live --report-only \
  --output "$OUT/no-skill-codex.json"

python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  --cases scripts/evals/reviewer-holdout-v8.json \
  --protocol scripts/evals/reviewer-validation-protocol-v8.json \
  --compare-arms \
  --output "$OUT/arm-comparison.json"

mkdir -p benchmarks/reviewer-holdout-v8/reports
cp "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  "$OUT/arm-comparison.json" \
  benchmarks/reviewer-holdout-v8/reports/
```

The full run is exactly **300 model calls**: 20 cases x 5 repetitions x 3 prompt arms. A v7 Codex arm of 60 calls took about 13 minutes, so three sequential 100-call arms are expected to take roughly 60–75 minutes under similar service conditions. The frozen hard limit remains 12 hours from the first start to the last completion.

## Claim limits

The v8 result is single-host, single-model evidence on an inspectable public development corpus whose labels were revised after observing v7 runs. It is not sealed, release-grade, cross-provider, cryptographically attested, or evidence of population-level generalization. A `PASS` supports only the declared development skill-lift claim for this corpus, execution, and schedule; `FAIL` or `INCONCLUSIVE` supports no skill-lift claim.
