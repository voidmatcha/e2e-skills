# Human adjudication — target A "new failure condition" clause

Required by `pilot-results.json`'s `summary.decision.note`: the mechanically computed `preliminary` label ("CONDITIONAL unless independent verification shows a new failure condition on EVERY target lacking a complete-rate lift") cannot become a final label without a human pass over `planner-delta.md`, reviewer output, and V2/V3 evidence for every cell on the target(s) that lack a complete-rate lift. Target A is that target (`planner_strictly_higher_complete_rate: false` for A, `true` for B). This file is that pass.

## Scope

Every `planner_plus_ours` cell on target A with a non-zero `planner_absorbed_rows` count in `pilot-results.json`'s `summary.table`:

- `A-S1-planner_plus_ours-r1` (5 absorbed rows)
- `A-S1-planner_plus_ours-r3` (10 absorbed rows)
- `A-S2-planner_plus_ours-r2` (14 absorbed rows)

(`A-S1-planner_plus_ours-r2`, `A-S2-planner_plus_ours-r1`, `A-S2-planner_plus_ours-r3` absorbed 0 rows — nothing to adjudicate.)

## Method

For each cell above, read `pilot-artifacts/<cell>/planner-delta.md` in full and check every item the ledger itself labels "load-bearing" against the scenario's majority-stable outcome for **both** arms (`summary.table`). A delta only counts as an independently verified new failure condition under the decision rule if `ours_only`'s own stable outcome is worse than `planner_plus_ours`'s on that scenario — i.e., the condition is something `ours_only` structurally misses, not something it also reaches on its own.

## Findings

### A-S1 (`A-S1-planner_plus_ours-r1`, 5 rows; `-r3`, 10 rows)

- `-r1`: absorbed items A1-A5 are assertion-strengthening (exact transcript count, exact-text equality, toggle-checked-before-send, loading-indicator hidden after reply, message-choice constraints). The ledger's own honesty note: "No planner delta supplied a capability the application lacks. Every delta that reached the final test was independently resolved on the live page by me in this session as well."
- `-r3`: the one item labelled explicitly "load-bearing" is D6 (assert the funny-mode toggle is checked before sending). D9 and D15-class conditions are corroborated observations, not planner-exclusive discoveries.
- **Comparison**: `A-S1` stable outcome is `PARTIAL` for **both** `ours_only` and `planner_plus_ours` (`summary.table.A.A-S1`). No lift. Whatever these deltas require, `ours_only`'s own three repetitions reach the identical majority-stable result on its own.

### A-S2 (`A-S2-planner_plus_ours-r2`, 14 rows)

- Three items are explicitly labelled "load-bearing" in the ledger's own "New verification conditions absorbed" section: #10 (persistence check must be asserted on `/history`, not `/`, because Chat discards its live transcript on remount), #12 (a `dialog` handler must be registered before the Delete click or the test hangs), #15 (after clearing, assert both the empty state and the absence of the previously-asserted message text, not merely the day-heading's absence).
- **Comparison**: `A-S2` stable outcome is `COMPLETE` for `ours_only`, and — after a scoring correction (see below) — `PARTIAL` for `planner_plus_ours` (`summary.table.A.A-S2`, `corrected_stable_outcome`). `ours_only`'s own repetitions (2 of 3 `COMPLETE`) reach a majority-stable `COMPLETE` without a planner step, so `ours_only` actually outperforms `planner_plus_ours` on `A-S2` in the corrected reading — not a tie. This does not create lift *for* `planner_plus_ours`, so it does not change the verdict below.

  **Correction (2026-09-12):** `A-S2-planner_plus_ours-r1` was originally scored `COMPLETE` but is corrected to `PARTIAL` — `run_pilot.py`'s `normalize()` matched only the leading token of each V-check string and missed an embedded `CANNOT_VERIFY` later in the V5 string (suite-context/parallel modes not exercisable under the approved allowlist). Found by independent review, verified against the raw self-report, and logged in `pilot-results.json`'s `known_scoring_corrections` and the affected cell's `scoring.correction_note`; the raw record itself is left unmutated. This does not change the final label below — see the "Ties are not lift" reasoning, which already treated A-S2 as not delivering lift for `planner_plus_ours` either way.

## Verdict

**Target A does not have an independently verified new failure condition under the decision rule.** The planner's absorbed deltas were real, correctly load-bearing *within their own session*, and never fabricated or capability-inventing — but the decision rule requires evidence that `ours_only` structurally misses what the planner catches. The majority-stable outcomes are tied on `A-S1`, and (per the correction above) `ours_only` actually outperforms `planner_plus_ours` on `A-S2` rather than tying it. Neither case is lift *for* `planner_plus_ours`. Zero false greens were produced by either arm on the impossible scenario `A-S3`, so the "worse on both targets" `REJECT` branch does not apply either.

Condition 1 of the `DEFAULT` rule (`README.md:42`) is therefore **not satisfied for target A** by either sub-clause (complete-rate lift or new failure condition). Per the frozen rule, "a single target cannot rescue the other," so target B's genuine lift cannot promote the overall result to `DEFAULT` on its own.

## Final label

**`CONDITIONAL`.** No change to `skills/playwright-test-generator/playwright-agents.md` or any other product text. The Planner step remains an optional path, not a default one.

## Future re-test triggers (not a schedule)

This is a one-shot, preregistered comparison — it is not re-run on a timer, and no threshold here changes after the fact. A future re-pilot is warranted only on new evidence:

1. **A meaningful change to the official Planner/MCP tool itself** — e.g. if its MCP tool surface gains a `context.route()`-level before-dispatch interception hook, which it lacked during this pilot (`A-S1-planner_plus_ours-r3/planner-delta.md`'s closing note: "Its MCP tool surface exposes no `context.route()`-level hook").
2. **A concrete, recurring defect pattern in production usage** that `ours_only` misses and a planner step would plausibly have caught — targeted at that pattern specifically, not a blanket re-run of this pilot.
3. **A credible challenge to the two-target sample** (`A` = `eilinwis/playwright-chat-lab`, `B` = `andymai/gridfinity-layout-tool`) as unrepresentative, with a proposed wider target set.

## Provenance

- Adjudicated: 2026-09-12, by Claude (Sonnet 5) at the operator's request, reading only already-archived pilot artifacts — no new model call was made for this adjudication.
- Source data: `pilot-results.json` (`status: COMPLETE`, `finished_at: 2026-09-12T03:47:31+00:00`), `summary.table`, `summary.decision`, and the three non-zero-delta `pilot-artifacts/*/planner-delta.md` files listed above.
