# Reviewer holdout v23: Luna development comparison

Status: **execution COMPLETE, scientific FAIL**. All **540/540** calls scored on 2026-10-20 (local date), with zero infrastructure errors and retries. No skill-lift claim is eligible.

## Result

| Arm | Scored calls | Stable precision | Stable recall | Stable F1 |
| --- | ---: | ---: | ---: | ---: |
| full | 180/180 | 0.897436 | 0.875000 | 0.886076 |
| catalog-only | 180/180 | 0.888889 | 0.800000 | 0.842105 |
| no-skill | 180/180 | 0.272727 | 0.225000 | 0.246575 |

Full failed four frozen absolute gates: stable precision 0.897436 < 0.95, repeated precision 0.851282 < 0.90, P0 recall 0.823529 < 0.90, and guard-hit rate 0.066667 > 0.05. Full minus no-skill stable F1 was +0.639501 (paired case-bootstrap 95% CI [+0.443109, +0.820952]); passing those two lift thresholds does not override the required full-arm PASS. Full minus catalog-only was descriptively +0.043971, CI [−0.007662, +0.100582]. Five repetitions measure stability across 36 public cases, not 180 independent defects per arm.

## Frozen scope

The [v23 protocol](../../scripts/evals/reviewer-validation-protocol-v23.json) uses Codex `gpt-6-luna`, the unchanged public AI-authored 36-case v17 corpus and five repetitions. Arms ran sequentially in order: full, catalog-only, no-skill. The reviewer SHA-256 is `7ff53a2999b80f2f777679fe8dd80941f6ad84b74d36ada43084573f3eeb3c10`, the same snapshot as [v22](../reviewer-holdout-v22/README.md). The later ESLint configuration/import-resolution changes to `scan.sh` and `scanner-workflow.md` are outside this snapshot; this is not an exact-byte evaluation of the final 3.0.0 payload.

All arms used the frozen output legend and strict schema with tools disabled. The local audit reparsed and rescored 540 final-answer payloads and reproduced the comparison. Original CLI event streams were not retained, so retrospective per-call tool-event recount is unavailable. Interrupted cohort-1 remains locally retained and excluded; no selective scored-cell replacement is counted.

[Outcome and provenance](outcome.json) contain a portable derived summary with exact metrics, failed gates, model/CLI identity, input digests and SHA-256 receipts for the original reports. The original comparison, three arm reports and raw final-answer payloads remain unmodified. They are now available in the [revision-pinned Hugging Face evidence package](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/tree/ba80292b2531ddac654134ba4aa319da1e3a2b3a/raw/reviewer-holdout-v22-v24-20261020), together with the frozen evaluated skill, corpus, model-specific evaluators, SHA-256 receipts and an offline replay script. This repository directory remains a portable derived summary.

## Interpretation

The earlier `gpt-6-sol` v22 run passed; Luna v23 failed. Both are public development evidence from different execution times with model-specific default reasoning, and Luna added deliberate pacing. They do not establish a randomized model ranking, equal reasoning depth, latency or cost advantage. No sealed release accuracy, unseen-project accuracy, scanner causal benefit or complete release readiness follows from either result. See [benchmark status](../STATUS.md) for the model comparison and snapshot limits.
