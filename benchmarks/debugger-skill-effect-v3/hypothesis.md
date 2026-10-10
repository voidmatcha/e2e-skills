# Stage 2 hypothesis (written before any skill edit)

Source: [`stage1-findings.md`](stage1-findings.md), from the v2 reports and blind-mapping ledger.

## Hypotheses

- **H1 (boundary rule).** Adding one explicit F1 / F14 / F11 / F7 tie-break to both debugger skills (Phase 2 table rows and `classification-procedure.md`) raises agreement between independent mappers and the F-code exact match of a zero-tool model on real merged fixes, without changing any other code's definition. Prediction: on a fresh real-fix corpus, the share of cases on which two blind mappers agree rises from v2's 15/26 (58%), and the new-skill arm's F-code exact match on agreed labels exceeds the 2.0.0 skill arm's.
- **H2 (root-cause shape).** Requiring the Root Cause line to name the trigger, the mechanism, and the observed effect (cause and effect, not a timeline or a category restatement) raises the strict judge match of the new-skill arm over the 2.0.0 skill arm. Prediction: new-skill strict match is at least as high as 2.0.0's; the three v2 patterns (temporal wording, category restatement, F5 "missing verification" framing on a missed target) do not recur.
- **H3 (no harm).** The edits do not lower product-versus-test attribution or lenient match, and do not move any case away from a code it was already getting right in v2.

## What will change (smallest edits)

1. `skills/playwright-debugger/SKILL.md` and `skills/cypress-debugger/SKILL.md`, Phase 2 table: sharpen the F1, F5, F11 and F14 signal cells so each names the evidence that separates it from its neighbours; add one tie-break paragraph after the table. Titles, IDs, order, and the Review Pattern column are unchanged.
2. `references/classification-procedure.md` in both skills: one paragraph with the same tie-break so the on-demand reference and the always-loaded table agree.
3. The Root Cause line of the finding format in both `SKILL.md`: state what the sentence must contain.
4. No file layout change, no reference moved, no token-cost restructuring: v2 showed no diagnosis-side cost of the reference size, and the CI debugger contracts pin the reference routing. Token cost is reported, not optimised.

## What will not change

F-code numbers, titles, and order; the F1-versus-F7 probe procedure; the F15 paragraphs; the Cypress F3/F11 intercept-ordering rule; evals that CI pins; the output schema used by the holdout runners.

## Decision (fixed before the edits)

Stage 3 compares `new skill` against `current (2.0.0) skill` and against the taxonomy-free arm on fresh real cases with the same blind judging as v2. The old text stays recoverable at git commit `ed9489c` (release 2.0.0) and by the per-file SHA-256 digests the v3 protocol records for both skill snapshots.
