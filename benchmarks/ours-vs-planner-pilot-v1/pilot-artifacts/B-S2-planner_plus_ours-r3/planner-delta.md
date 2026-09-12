# Pilot B-S2 — planner delta reconciliation ledger

Arm: `planner_plus_ours`. Planner status: **READY** (admission gate passed — the
delegated `playwright-test-planner` confirmed it could see both
`planner_setup_page` and `planner_save_plan`, and its browser launched and
reached `http://localhost:5174/`).

Planner plan saved by the planner itself at `specs/pilot-b-s2-planner-plan.md`.
Final implementation is `e2e/pilot-b-s2.spec.ts`, written by this skill run.

Frozen scenario (unchanged, byte-for-byte):

> ## Scenario B-S2
> - Given: the application is served at http://localhost:5174, fresh browser profile, empty client-side storage
> - When: the user performs the actions the outcome below requires
> - Then: Changing the drawer dimensions recomputes the baseplate grid, and a bin that no longer fits is reported rather than silently kept.

## Delta ledger

| # | Delta | Class | Disposition | Note |
|---|-------|-------|-------------|------|
| D1 | Width `spinbutton` does not recompute the grid on input alone; the value commits on blur (Tab confirmed). Enter not tested. | observed | **absorbed** | Spec uses `fill('8')` then `blur()`; matches the repo's existing `drawer-settings.spec.ts` idiom. |
| D2 | Displaced bins keep their identity: the pre-resize `data-bin-id` string reappears verbatim as `data-staging-bin-id` (planner cited ids `mtxsstav-f29cf688fd`, `mtxsstaw-d94f6a14b2`). | observed | **absorbed** | Independently re-observed in this run (`mtxslh0m-514e78a5fa` 4×6, `mtxslh0m-2403ae69d5` 4×2). Spec captures the id before the resize and asserts on that exact id. |
| D3 | Grid bins expose position via inline `style="grid-area: <row> / <col> / span <rows> / span <cols>"`. | observed | **absorbed** | Independently re-verified this session (`grid-area: 3 / 1 / span 6 / span 6`). Used for the geometry-level boundary check. |
| D4 | Stash bins carry no `aria-label`; their accessible name is plain text (`4×2`, `4×6`), unlike grid bins (`Bin W by D, category X`). | observed | **absorbed** | Spec does not use a role+name locator for stash bins; it uses the `data-staging-bin-id` identity attribute. |
| D5 | Route `/` redirects to a persisted `/l/<id>/...`; `localStorage.clear()` + `sessionStorage.clear()` alone do **not** reset the app — layout state lives in IndexedDB (`gridfinity-baseplate-v1`, `gridfinity-db`, `gridfinity-designer-v1`, `gridfinity-events-db`). A genuinely empty Given requires a fresh browser context. | observed | **absorbed** | Independently reproduced this session. Playwright's default context-per-test already satisfies it; the spec additionally asserts the empty precondition (10×8 grid, 0 stashed bins) instead of assuming it. |
| D6 | Widening the drawer does **not** auto-restore previously stashed bins (corrects a "widening displaces nothing" reading that only holds from an empty stash). | observed | **noted, not applied** | The approved scenario only shrinks; recorded so the counter-case evidence is not overstated. |
| D7 | No toast/alert/`role=status` report accompanies the displacing resize; the stash is the only displacement report. Bin List (grid-only count) and the category badge (grid+stash total) are not displacement reports; History is an autosave-checkpoint list, not an event log. | limitation | **absorbed as a scoping fact** | Confirms the stash is the honest "reported" surface; no invented toast locator. |
| D8 | No more direct baseplate-grid readout exists inside the Layout tool at `/` than the `[role="application"]` aria-label; the sidebar "Baseplate" section only offers an active-design combobox. The top-level "Baseplate" tab navigates to the separate `/baseplate` tool. | limitation | **absorbed as a scoping fact** | Spec asserts grid recompute via the `[role="application"]` aria-label **and** the `Select bins in column N` header count (two independent observables at route `/`). |
| D9 | Verification condition: fail if a bin whose footprint exceeds the new width remains under `[data-bin-id]`. | verification condition | **absorbed** | Load-bearing: this is the "silently kept" failure the scenario names. Without it the test would pass on an app that keeps the oversized bin *and* also copies it into the stash. |
| D10 | Verification condition: fail if a displaced bin's `data-staging-bin-id` does not equal its prior `data-bin-id` (catches delete-and-recreate masquerading as "stashed"). | verification condition | **absorbed** | Load-bearing: a count-only assertion would stay green if the app destroyed the bin and minted an unrelated stash entry — that is data loss reported as a successful stash. |
| D11 | Verification condition: fail if any remaining grid bin's `grid-area` column-start + column-span − 1 exceeds the committed width. | verification condition | **absorbed** | Load-bearing: catches an app that recomputes the grid label but leaves a bin visually clipped/overhanging the new boundary — a state both the count and identity assertions would miss. |
| D12 | Verification condition: fail if the stash toggle's accessible name count desyncs from the actual `[data-staging-bin-id]` count. | verification condition | **absorbed** | Load-bearing: the toggle name (`Stash 2 bins`) is the *user-visible* report; a correct internal move with a stale header would still leave the user uninformed. |
| D13 | Verification condition: category total (grid + stash) conserved at 4 across the resize, as corroborating evidence. | verification condition | **declined** | Redundant with D9+D10+D12 and adds a locator with no distinct failure mode; YAGNI. |
| D14 | Enter-to-commit and a depth-axis (rather than width-axis) shrink were not tested. | limitation | **recorded** | Out of the frozen scenario's single-outcome scope; not added. |
| D15 | Background `POST /api/ml-telemetry` returns 404 in dev. | limitation | **recorded** | Pre-existing app behavior, unrelated to the outcome; not stubbed, not asserted on. |

## Counts

- absorbed: 9 (D1, D2, D3, D4, D5, D9, D10, D11, D12)
- returned_to_approval_gate: 0 — the planner flagged no scope-changing delta, and this run found none.
- declined: 1 (D13)
- recorded-only limitations: 5 (D6, D7, D8, D14, D15)

## Inferred locators

The planner reported **no** `inference`-class deltas: every locator claim it
returned was resolved on the live page. No inferred locator reaches
`e2e/pilot-b-s2.spec.ts`; every locator in the final spec was additionally
re-observed by this run in its own browser session.
