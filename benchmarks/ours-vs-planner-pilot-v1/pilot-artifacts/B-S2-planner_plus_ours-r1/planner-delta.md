# Planner delta ledger — Scenario B-S2 (cell B-S2-planner_plus_ours-r1)

planner_status: **READY**

Admission gate (playwright-test-planner subagent, MCP server `playwright-test`):

- `planner_setup_page` visible: yes
- `planner_save_plan` visible: yes
- browser launched and navigated to `http://localhost:5174/` (landed on
  `/l/AupaEDj5S0Ih/untitled-layout`, live accessibility snapshot returned): yes

Planner plan saved by the planner at `specs/pilot-b-s2-planner-plan.md`.
Frozen scenario scope preserved by the planner (exactly one scenario, Given/When/Then
unchanged, entry route `/`). Planner reported **no** scenario-changing proposals of its own.

Candidate implemented by this skill (the planner did not write test code):
`e2e/pilot-b-s2.spec.ts`.

## Ledger

| # | Delta | Planner label | Disposition | Note |
|---|-------|---------------|-------------|------|
| D1 | Width control = `getByRole('spinbutton', { name: 'Drawer width in grid units' })` (+ stepper buttons) | observed | **absorbed** | Independently re-resolved live by this skill (value `10` in `[data-sidebar]`, clean profile). |
| D2 | Depth control = `getByRole('spinbutton', { name: 'Drawer depth in grid units' })` | observed | declined | Scenario exercised on the width axis only; an unused locator would fail the Step 6 YAGNI audit. |
| D3 | Recomputed column/row count is exposed **only** in the grid's accessible name `Gridfinity drawer grid, N columns by M rows` | observed | **absorbed** | Re-resolved live; used as both the settle gate and the "baseplate grid recomputed" assertion. |
| D4 | Grid bin = `role=button`, `aria-label="Bin W by D, category X"`, attribute `data-bin-id` | observed | **absorbed (attribute form only)** | `data-bin-id` is the repo-native handle (`e2e/README.md`); the category word in the aria-label is colour-assignment dependent, so it is not asserted. |
| D5 | Stash container role/name is state-dependent: `role=status` name `Stash` when empty → `role=button` name `Stash {N} bins` when non-empty | observed | **absorbed** | Re-resolved live: `Stash 1 bins` visible after displacement. This is the report surface. |
| D6 | Stashed bin = `data-staging-bin-id`; its accessible name (`1×1`-style size text) is **not** unique | observed | **absorbed** | Test disambiguates by `data-staging-bin-id`, never by size text. |
| D7 | Identity link: `data-staging-bin-id` after displacement equals the prior `data-bin-id` | observed | **absorbed — primary outcome (V1)** | Re-resolved live (same id before/after). Load-bearing: it proves *the bin that no longer fits* is the one reported, not a re-created placeholder. |
| D8 | The width/depth spinbutton commits **on blur**, not on `fill()` alone | observed | **absorbed** | Load-bearing: without the explicit `blur()` the recompute never runs and the test would assert against pre-change state. Recorded as a comment in the spec. |
| D9 | Axis asymmetry: a width shrink trims the **highest-index** column and does **not** renumber surviving bins; a depth shrink trims **row 1** and renumbers | observed | **absorbed (width half)** | Load-bearing for probe placement: the probe bin is drawn in the two right-most columns, which the width shrink is proven to drop. Depth half is not exercised (see D2). |
| D10 | Bin must be drawn by mouse drag against the grid bounding box (element-target drag cannot express it) | observed | **absorbed** | Matches the repo's own `drawBinOnGrid` fixture pattern. |
| D11 | Assert the grid label decrements the **correct axis by exactly the stepped amount, other axis unchanged** | verification condition | **absorbed** | New failure condition: a regression that recomputes/resets the depth axis, or clamps the width to a floor, turns the test red. Implemented as an exact-name match on `... 5 columns by 8 rows`. |
| D12 | Assert **no** bin remains on the grid application after displacement | verification condition | **absorbed** | New failure condition: this is the "rather than silently kept" half of the frozen Then; a build that keeps the bin in place stays green without it. |
| D13 | Assert the stash trigger's accessible name equals `Stash {N} bins` for the number displaced | verification condition | **absorbed** | New failure condition: catches a build that moves the bin to staging but never surfaces a count to the user (silent move). |
| D14 | Settle gate: wait for the grid accessible name to match the expected `N columns by M rows` before asserting bin presence/absence; stash name updates separately | observed | **absorbed** | Implemented as an ordered web-first assertion chain (grid name → grid count → stash name → staged id); no sleeps. |
| D15 | Layers summary `X% filled · Y bins` decrements | verification condition | declined | Outside the frozen Then; couples the spec to an unrelated panel. |
| D16 | `Fill N gaps` button recomputes against the shrunk grid | verification condition | declined | Outside the frozen Then (separate feature surface). |
| D17 | Right-panel Bin List excludes stashed bins | verification condition | declined | Outside the frozen Then; already covered by `e2e/staging.spec.ts` territory. |
| D18 | Category usage counter must NOT reset when a bin is stashed | verification condition | declined | Outside the frozen Then; a distinct invariant deserving its own scenario. |
| D19 | Physical dimension readout `420 × 336 × 84 mm` → `378 × 336 × 84 mm` recomputes | verification condition | declined | Outside the frozen Then; the approved Then names the baseplate grid, which D3/D11 already prove. |
| D20 | A single Undo reverts grid size, bin position and stash state atomically; Redo re-applies them | verification condition | **RETURNED_TO_APPROVAL_GATE (not applied)** | Adds a new user action (undo/redo) to the frozen When → scenario-changing. Recorded, never applied; there is no human in this session to approve it. |
| D21 | Depth-shrink probe recipe (place probe bin in row 1, assert unchanged `data-bin-id` + updated `grid-area`) | observed + verification condition | **RETURNED_TO_APPROVAL_GATE (not applied)** | Would add a second flow (depth axis) → scenario-changing (scenario count is frozen at one). |
| L1 | **No** toast/`role=alert` announces the displacement; no textual "no longer fits" reason exists | limitation (observed) | **absorbed as a limitation** | The app *does* report the displacement — structurally, via the Stash panel and its `Stash N bins` count. The test asserts that real surface; no invented toast locator, no fabricated message. |
| L2 | The only aria-live announcement (`↩ Undid: Updated drawer`) is emitted by Undo/Redo, not by the resize itself | limitation (observed) | **absorbed as a limitation** | Reinforces L1; the test does not assert any live-region announcement for the resize. |
| L3 | Planner's "no sleep is required in principle" claim | inference | not relied upon | The spec uses Playwright auto-retrying assertions, which is a framework property, not a planner-supplied fact. No inferred claim reaches the test. |

## Summary

- absorbed: 13 (D1, D3, D4, D5, D6, D7, D8, D9, D10, D11, D12, D13, D14) + 2 limitations (L1, L2)
- returned to approval gate (recorded, never applied): 2 (D20, D21)
- declined: 6 (D2, D15, D16, D17, D18, D19); 1 inference not relied upon (L3)

New verification conditions absorbed (failure condition → why load-bearing):

1. D11 — grid accessible name must read exactly `5 columns by 8 rows` after the shrink: a build that recomputes the wrong axis, resets depth, or refuses the shrink turns the test red.
2. D12 — zero `[data-bin-id]` on the grid after the shrink: this is the literal "rather than silently kept" clause; without it a build that keeps the out-of-fit bin on the grid stays green.
3. D13 — stash trigger must read `Stash 1 bins`: catches a build that displaces the bin internally but never reports it to the user.
4. D7/D14 — the staged `data-staging-bin-id` must equal the captured `data-bin-id`, asserted after the grid-name settle gate: catches a build that drops the bin and creates a different one, and removes cross-step timing ambiguity.

No inferred (source-only) locator reached the final test. Every locator in
`e2e/pilot-b-s2.spec.ts` was re-resolved against the live page by this skill in
this session before it was written.
