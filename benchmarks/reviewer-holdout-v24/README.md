# Reviewer holdout v24: GPT-6.1 Sol development comparison

Status: **execution COMPLETE, scientific PASS, independent integrity PASS**. All **540/540** calls scored on 2026-10-20, with zero infrastructure errors and retries. The frozen development skill-lift gates passed; release eligibility remains false.

## Result

Primary metrics count unique labels or predictions that appeared in a strict majority of five repetitions.

| Arm | Stable TP / FP / FN | Stable precision | Stable recall | Stable F1 |
| --- | ---: | ---: | ---: | ---: |
| full | 40 / 0 / 0 | 1.000000 | 1.000000 | 1.000000 |
| catalog-only | 40 / 4 / 0 | 0.909091 | 1.000000 | 0.952381 |
| no-skill | 17 / 26 / 23 | 0.395349 | 0.425000 | 0.409639 |

Repeated-run counts are secondary and do not represent additional independent defects.

| Arm | Scored calls | Repeated TP / FP / FN | Repeated precision | Repeated recall |
| --- | ---: | ---: | ---: | ---: |
| full | 180/180 | 200 / 2 / 0 | 0.990099 | 1.000000 |
| catalog-only | 180/180 | 200 / 23 / 0 | 0.896861 | 1.000000 |
| no-skill | 180/180 | 81 / 149 / 119 | 0.352174 | 0.405000 |

Full passed the frozen absolute gates. Full minus no-skill stable F1 was **+0.590361**, paired case-bootstrap 95% CI **[+0.443299, +0.741176]**, satisfying the frozen lift thresholds. Full minus catalog-only was descriptively +0.047619, CI [+0.011765, +0.090909]; that comparison has no lift gate. Catalog-only and no-skill each failed their absolute arm gates. Exact values and gate checks are preserved in [outcome.json](outcome.json).

## Frozen scope and provenance

The [v24 protocol](../../scripts/evals/reviewer-validation-protocol-v24.json) uses native Codex `gpt-6.1-sol`, CLI `0.159.3`, the unchanged public AI-authored 36-case v17 corpus, and five repetitions. Arms ran sequentially: full, catalog-only, no-skill. Reasoning effort was omitted, using the isolated CLI model default. Attempts retained the 180-second timeout, at most two declared infrastructure attempts, and 12-hour matrix window. Fixed 10-second pacing preceded native invocations except `--version`.

The evaluated reviewer SHA-256 is `7ff53a2999b80f2f777679fe8dd80941f6ad84b74d36ada43084573f3eeb3c10`, shared with [Sol v22](../reviewer-holdout-v22/README.md) and [Luna v23](../reviewer-holdout-v23/README.md). All arms used the frozen output legend and strict native output schema with tools disabled. Complete original CLI event streams were not retained, so retrospective raw tool-event recount is unavailable.

The independent audit reparsed and rescored all 540 final-answer payloads, reran the frozen comparator, verified 6,102 frozen files, and checked wrapper/native hashes, the unchanged source product, and four historical Sol report/comparison hashes. A separate final summary reparsed and rescored all 1,620 payloads across the three model cohorts. [Outcome and provenance](outcome.json) retain exact metrics and SHA-256 receipts for those checks and their source reports.

This archive is a portable derived summary. Original reports and raw final-answer payloads remain unmodified in the local run cache; they are not copied or uploaded here. Hash receipts identify those originals and do not prove that an external reader can access or independently reparse them.

## Applicability

The successor product differs from this evaluated snapshot in exactly two of 229 compared skill files: `skills/e2e-reviewer/scripts/scan.sh` and `skills/e2e-reviewer/references/scanner-workflow.md`. Their later ESLint configuration/import-resolution and scan-scope changes require separate executable evidence. This tool-free matrix did not execute the scanner and is not an exact-byte evaluation of those changed successor files.

Sol v22 passed, Luna v23 failed, and Sol6.1 v24 passed on the same public cases. Different execution times, model-specific default reasoning, and deliberate pacing limit that comparison to descriptive results. Equal effective reasoning, a randomized model ranking, speed or cost advantage, sealed release accuracy, scanner causal benefit, and complete release readiness are not established.
