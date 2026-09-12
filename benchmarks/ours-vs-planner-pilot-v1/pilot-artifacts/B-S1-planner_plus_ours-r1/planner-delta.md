# Pilot B-S1 — planner delta reconciliation ledger

Arm: `planner_plus_ours`. Auxiliary planner: first-party `playwright-test-planner`
(from `.claude/agents/playwright-test-planner.md`, MCP server `playwright-test`).
Reconciled per `playwright-agents.md` "Recommended auxiliary mode: harden the plan",
steps 2–4. Implementation of the hardened plan was done by the
`playwright-test-generator` skill pipeline, not by the first-party generator/healer.

- **planner_status:** READY
- **Admission gate:** PASSED — the delegated planner reported it could see both
  `planner_setup_page` and `planner_save_plan`, and its browser launched and
  navigated to `http://localhost:5174/` successfully.
- **Planner plan file:** `specs/pilot-b-s1-planner-plan.md` (saved by the planner
  through `planner_save_plan`).
- **Scope:** frozen scenario B-S1 preserved — exactly one scenario, entry route `/`.
  The planner added no scenario, split none, and reworded none.
- **Candidate implemented:** `e2e/pilot-b-s1.spec.ts`.

## Ledger

| # | Delta | Label | Disposition | Notes |
|---|-------|-------|-------------|-------|
| D1 | `/` auto-redirects to `/l/<id>/untitled-layout`; assert that URL shape to prove the layout under test is the fresh auto-created one | observed + verification condition | **ABSORBED** | Re-resolved live by me (`http://localhost:5174/l/RPszZzIB5nvh/untitled-layout`) before absorbing. In spec as `toHaveURL(/\/l\/[^/]+\/untitled-layout$/)` |
| D2 | Grid container: `role=application`, name exactly `Gridfinity drawer grid, 10 columns by 8 rows` | observed | **ABSORBED** | Independently observed in my own Step 3 pass; already in the Locator Mapping Table |
| D3 | Grid empty-state paragraph `Click and drag to draw a bin` disappears once a bin exists | observed | **DECLINED** | Redundant with the 0→1 bin-count transition; adds a placeholder-copy coupling without adding a failure condition |
| D4 | Layer summary before state reads exactly `0% filled · 0 bins` | observed | **ABSORBED** | Independently observed; asserted as the "before" half of the transition |
| D5 | Bin List empty state reads `No bins to print` / `Add bins to the grid to see the print list` | observed | **ABSORBED** | First paragraph asserted as the "before" half of the print-list surface |
| D6 | Right panel `Selection` accordion is wholly replaced by `Bin Properties` / heading `2×2 Bin` | observed | **DECLINED** | That is the selection inspector, not the layout summary; already covered by `e2e/add-bins.spec.ts` ("shows bin inspector when bin is selected"). Keeping it would duplicate existing E2E coverage |
| D7 | `Clear layer` (disabled) → `Clear 1 bins` (enabled); `Fill 80 gaps` → `Fill 76 gaps`; `Undo (⌘+Z)` disabled → enabled | observed | **DECLINED** | Secondary corroboration only; the two-independent-summary-surfaces requirement (D12) is already met by the layer summary + Bin List. Undo-enabledness is history state, outside this scenario's outcome |
| D8 | Created bin: `role=button`, name `^Bin \d+ by \d+, category .+$` (exact observed `Bin 2 by 2, category Coral`), `aria-pressed=true`, 8 resize-handle sliders | observed | **ABSORBED** | Independently observed. Spec locates the bin by role+name inside the grid and gates on `aria-pressed="true"` via the repo's `waitForBinSelected` helper |
| D9 | Assert the bin-button count goes 0 → **exactly 1**, not "at least 1" | verification condition | **ABSORBED** | Load-bearing: a single drag that produced a duplicate/ghost bin would pass an "at least one" assertion |
| D10 | Substantiate "places it on the baseplate grid" by deriving cell size from the grid's own live-read bounding box + 10×8 and asserting the bin's offset/size land on whole cells — never hardcoded pixels | observed + verification condition | **ABSORBED** | This is the load-bearing placement proof. Spec polls `{column,row,columnSpan,rowSpan}` derived from both bounding boxes and asserts `{0,0,2,2}`. Without it the test would only prove "a bin element exists somewhere" |
| D11 | Bin List accordion accessible name gains a count badge: `Bin List` → `Bin List 1`; body swaps to a `table` (`Size/H/Qty/Fil.`) with one data row | observed | **ABSORBED** | Re-resolved live by me before absorbing: with bins present, `getByRole('region', { name: 'Bin List', exact: true })` resolves to **0** while the default substring form resolves to **1**, and `getByRole('button', { name: 'Bin List 1', exact: true })` resolves to 1. This corrected a latent break in my own draft locator |
| D12 | Assert at least two independent summary surfaces, because a bug could update one and leave the other stale | verification condition | **ABSORBED** | Spec asserts both the layer summary line and the Bin List (header count badge + `2×2` print-list row) |
| D13 | Do not assert derived literals (fill %, filament estimate, print time, cost, gap count) as exact strings — "not deterministic unless the drag gesture is pixel-exact" | verification condition | **PARTIALLY ABSORBED** | Filament/time/cost/gap-count literals are **not** asserted. The fill-summary literal `5% filled · 1 bins` **is** asserted: the spec's gesture is not pixel-based — it is derived from the live-measured cell pitch and drags between two cell centres, so the bin is deterministically 2×2 (reproduced on three independent fresh-state runs, always `5% filled · 1 bins`). Keeping the literal is what lets the V3 fault probe fail at the primary assertion with a legible mismatch instead of silently surviving |
| D14 | One unrelated console 404 (`/api/ml-telemetry`) fires on load in dev; do not treat it as a regression or assert "no console errors" | limitation | **ABSORBED** | No console assertion in the spec |
| D15 | `3/12u` headroom text does **not** change when a bin is added | observed | **ABSORBED (negative)** | Recorded so it is not asserted as part of the transition |

## Summary

- absorbed: 11 (D1, D2, D4, D5, D8, D9, D10, D11, D12, D14, D15)
- partially absorbed: 1 (D13)
- declined: 3 (D3, D6, D7)
- **RETURNED_TO_APPROVAL_GATE: 0** — no planner delta changed the scenario count,
  the product behaviour under test, an expected value in the approved outcome, a
  target-controlled command, or a control file. Nothing was returned unapplied.

## New verification conditions that are load-bearing

1. **D9** — exact 0→1 bin-count transition: a drag that creates duplicate or ghost
   bins stays green under an "at least one bin" assertion.
2. **D10** — cell-derived placement proof: a bin rendered detached from the
   baseplate (wrong container, unsnapped offset, wrong span) stays green under an
   existence-only assertion, yet the scenario explicitly promises grid placement.
3. **D12** — two independent summary surfaces: a desync where the layer stats
   update but the print list stays stale (or vice versa) is invisible to a
   single-surface assertion.
4. **D11** — count-badge accessible-name change: the Bin List region must be
   matched on a substring, otherwise the post-add locator silently fails to
   resolve for a reason unrelated to the product.

## Honesty notes

- No inferred locator reached the final test. Every locator in
  `e2e/pilot-b-s1.spec.ts` was resolved against the live page in this session; the
  two planner-sourced ones that affect locator validity (D1, D11) were
  re-resolved by me before absorption.
- The planner supplied no capability the application does not have. Every
  absorbed delta describes behaviour that was observed on the running app.
