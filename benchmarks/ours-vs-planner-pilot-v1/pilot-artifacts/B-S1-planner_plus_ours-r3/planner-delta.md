# Planner delta ledger — Scenario B-S1

`planner_status: READY`

Admission gate: the delegated `playwright-test-planner` confirmed it could see both
`planner_setup_page` and `planner_save_plan`, and its browser launched and navigated to
`http://localhost:5174`. Its plan is saved at `specs/pilot-b-s1-planner-plan.md`.

Frozen scenario scope was preserved: exactly one scenario, entry route `/`, no rewording.

Implementer (this session) explored the same target independently with `playwright-cli`
before delegating, so several planner deltas are corroborated by two independent live
observations. "Absorbed" means the delta reached the candidate spec or constrained how it
was written; "declined" means it was evaluated and deliberately not applied; nothing
classified `RETURNED_TO_APPROVAL_GATE` was applied.

| #   | Delta (planner) | Class | Disposition |
| --- | --------------- | ----- | ----------- |
| D1 | `/` auto-provisions a layout and rewrites the URL to `/l/<random-id>/untitled-layout`; the id is non-deterministic per profile | observed | **Absorbed** as a constraint — the spec asserts no URL and no layout id |
| D2 | App-ready gate: `header` + `role=application` present on load, no blocking dialog | observed | **Absorbed** — spec uses the repo's `waitForAppReady` |
| D3 | Grid is `role=application`, accessible name `Gridfinity drawer grid, 10 columns by 8 rows`; zero `[data-bin-id]` before any bin | observed | **Absorbed** — spec locates the grid by role+name (stronger than the repo's raw `[role="application"]`) and uses the 10×8 name to justify its cell-pitch arithmetic |
| D4 | Created bin: `[data-bin-id]`, `role=button`, `aria-label="Bin 2 by 2, category Coral"`, `aria-pressed="true"`, inline `grid-area: 1 / 1 / span 2 / span 2` | observed | **Absorbed** for the role+name locator. Sub-item declined: the inline `grid-area` style is an implementation detail, so placement is asserted geometrically instead |
| D5 | Layers-panel summary `0% filled · 0 bins` → `5% filled · 1 bins` after a 2×2 bin | observed | **Absorbed** — this is the V1 primary assertion |
| D6 | Bin List empty copy `No bins to print` → table row `Coral 2×2 / 3u / 1 / 21.45` | observed | **Absorbed** — used as the pre-state gate and as the supporting summary assertion |
| D7 | Other surfaces also change: `Fill 80 gaps`→`Fill 76 gaps`, `Clear layer`→`Clear 1 bins`, right panel `Selection`→`Bin Properties` (`2×2 Bin`), category badge `1 bin(s) use this category` | observed | **Declined** — redundant with D5/D6; asserting all of them is over-assertion that raises maintenance cost without adding a distinct failure mode |
| D8 | A transient header status shows `Saving...` then `Saved`, then unmounts | observed | **Declined** as a readiness gate — transient and text-only; the approved `Then` makes no persistence claim |
| D9 | `waitForAutoSave` (e2e/test-utils.ts) polls `gridfinity-library-v1` / `gridfinity-layout-<id>`, but the live app persists to IndexedDB (`gridfinity-db`, …); those localStorage keys never appear | observed | **Absorbed** — the spec deliberately does not call `waitForAutoSave` |
| D10 | No stable non-text hook exists for the save-status indicator | limitation | **Absorbed** as the rationale for D8 |
| D11 | Forced save/persistence-failure UI was not probed (outside the frozen happy path) | limitation | **Recorded** — consistent with this session's V4 finding (the action issues no HTTP write at all) |
| D12 | Verification condition: assert the bin lands *within* the declared grid bounds, not merely that a `[data-bin-id]` exists | verification condition | **Absorbed** — geometric containment + covers both dragged cell centers |
| D13 | Verification condition: assert the `aria-label` encodes size *and* category together | verification condition | **Absorbed** — the bin locator is `Bin 2 by 2, category Coral` |
| D14 | Verification condition: coverage % and bin count must move together and match the drawn cell area (4/80 = 5%) | verification condition | **Absorbed** — primary assertion pins the whole string `5% filled · 1 bins` |
| D15 | Verification condition: assert the Bin List row, a separate derived-aggregation code path from grid rendering | verification condition | **Absorbed** — size cell `2×2` and quantity cell `1` |
| D16 | Verification condition: assert Undo transitions disabled → enabled (bin renders but is never pushed onto the history stack) | verification condition | **RETURNED_TO_APPROVAL_GATE — not applied** |
| D17 | Verification condition: if asserting "no console errors", allow-list the pre-existing `404 /api/ml-telemetry` | verification condition | **Declined** — the spec makes no console assertion, so the allow-list has nothing to attach to |

Totals: absorbed 12, returned to approval gate 1, declined 3 (D4's `grid-area` sub-item is
declined inside an otherwise-absorbed row and is not double-counted).

## Why D16 is scenario-changing

The approved `Then` is *"places it on the baseplate grid and the layout summary reflects the
added bin"*. Undo/redo enablement is a third, distinct outcome on the history stack — a new
Then clause, not a sharper reading of the approved one. There is no human in this session to
approve that widening, so it is recorded here and left unapplied.

## Honesty check on planner deltas

Every absorbed delta names a surface this session also resolved on the live page with
`playwright-cli` (grid accessible name, bin accessible name, summary strings before/after,
Bin List empty copy and table cells, absence of the `waitForAutoSave` localStorage keys). No
delta supplied a capability the application does not have, and no inferred (source-only)
locator reached the candidate spec.
