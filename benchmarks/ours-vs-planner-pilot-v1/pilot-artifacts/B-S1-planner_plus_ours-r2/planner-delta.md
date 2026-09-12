# Pilot B-S1 — planner reconciliation ledger

- Arm: `planner_plus_ours` (cell `B-S1-planner_plus_ours-r2`)
- Planner status: **READY** — the delegated `playwright-test-planner` confirmed it could see both
  `planner_setup_page` and `planner_save_plan`, and its browser launched (`planner_setup_page` → `about:blank`).
- Planner output saved by the planner itself: `specs/pilot-b-s1-planner-plan.md` (12 deltas).
- Frozen scope preserved: exactly one scenario (B-S1), entry route `/`, target `http://localhost:5174`.
- Scenario-changing deltas: **none**. `RETURNED_TO_APPROVAL_GATE` count = 0.
- Candidate implemented by this skill (not by the first-party generator/healer): `e2e/pilot-b-s1.spec.ts`.

Authoritative locator mapping remains the one this skill observed live with `playwright-cli`
(Step 3). Planner deltas were absorbed only as verification conditions, determinism guards,
and corroboration — no inferred locator reached the final test.

## Delta ledger

| # | Planner claim (abridged) | Class | Disposition | Notes |
|---|---|---|---|---|
| D1 | chromium viewport 1280×720; fresh 10×8 grid bbox 350,119,551×441 (cell ≈55.1×55.125), zoom 170% auto-fit | observed | **Absorbed** (context) | Matches this skill's own live measurement exactly (`boundingBox` → `{x:350,y:119,width:551,height:441}`). |
| D2 | `drawBinOnGrid()` takes literal pixel offsets and `add-bins.spec.ts:107` hardcodes them; zoom is auto-fit, so a B-S1 test must derive drag endpoints from `bounds.width/10` and `bounds.height/8` at run time | verification condition | **Absorbed** | Final test computes `cellWidth`/`cellHeight` from the live `getGridBounds()` box; no literal pixel constants. |
| D3 | Replayed the runtime-computed drag live: 1 `[data-bin-id]`, name `Bin 3 by 3, category Coral`, `aria-pressed=true`, `grid-area: 1 / 1 / span 3 / span 3`; stats span exactly `11% filled · 1 bins` (U+00B7) | observed | **Absorbed** (corroboration) | Independently observed by this skill in two separate fresh profiles. |
| D4 | `coverage = Math.round(cells/total*100)`; 3×3 on 10×8 → 11%; near-miss sizes give 8% / 15%, so `11%` is a proxy for bin *size*, not just presence — do not weaken to a substring/regex match | observed | **Absorbed** | Primary assertion kept as exact `toHaveText('11% filled · 1 bins')`. |
| D5 | `layers.stats` is translated in 20+ locales; an exact English assertion is coupled to the browser locale — force `locale: 'en-US'` | verification condition | **Absorbed** | Independently confirmed: `src/i18n/detection.ts:103` selects the UI locale from `navigator.languages`. Added `test.use({ locale: 'en-US' })` (a pattern the repo already uses, e.g. `e2e/context-menu.spec.ts:18`). |
| D6 | The stats span is bare, with sibling bare spans (`·`, `3/12u`); `region('Layers').getByText(/filled/)` resolves uniquely, a generic `span` locator matches 3 and risks strict mode | observed | **Absorbed** | Final locator is the Layers region scoped to `/^\d+% filled · \d+ bins$/`; verified `count() === 1` in both states. |
| D7 | `getByRole('button', { name: 'Select bins in column 1' })` without `exact: true` matches 2 elements (collides with "column 10") and throws strict mode | verification condition | **Absorbed** | Reproduced (`count() === 2`). The column locator in the final test passes `exact: true`. |
| D8 | Column/row header buttons give a stronger, non-CSS placement proof: column 1/2/3 select the bin, column 4 does not; rows 6/7/8 select it, rows 1–5 do not | observed | **Partially absorbed** | **Not reproducible as stated.** From the post-draw state (bin already `aria-pressed=true`) this skill observed the bin stay `true` after clicking column 4 *and* row 1 — header clicks are additive to the current selection (clicking column 9 after column 1 also left it `true`). Only after an explicit `Escape` deselect did `column 4 → false` / `column 1 → true` hold. **Absorbed:** `Escape` (bin → `false`) then `Select bins in column 1` (bin → `true`), i.e. two positive transitions that prove the bin occupies grid column 1. **Declined:** the `column 4 → false` negative — from a deselected state it asserts an unchanged value and cannot distinguish "bin is not in column 4" from "the click has not been processed yet". |
| D9 | Row numbering is inverted (row "1" = bottom/front, "8" = top/back) and undocumented in UI copy | limitation | **Declined** (recorded) | Informational; the final test asserts no row-label placement, so the trap is not reachable. |
| D10 | `waitForAutoSave()` only checks key existence, and an empty layout is saved on load, so it can resolve on the pre-bin save rather than the post-bin debounced save (1000 ms, `useAutoSave.ts`) | verification condition / limitation | **Absorbed** (as a constraint) | The candidate deliberately uses no `waitForAutoSave()` and asserts no persistence outcome; persistence is outside the frozen B-S1 outcome. |
| D11 | Repo convention clears storage in `afterEach`, so a test's initial empty state relies on Playwright's fresh-context-per-test default | verification condition | **Absorbed** | Convention kept (`clearAllStorage` + `resetViewport` in `afterEach`), and the Given block now asserts the empty precondition (`0` bins, `0% filled · 0 bins`) instead of assuming it. This fresh-context-per-attempt disposability is also the V5 replay-safety basis. |
| D12 | Pre-state (`0% filled · 0 bins`, 0 bins) and post-state (`11% filled · 1 bins`, 1 bin) both live-verified | observed | **Absorbed** (corroboration) | Same two states observed independently by this skill. |

Totals: absorbed 10, partially absorbed 1 (D8), declined 2 (D9, and the negative half of D8),
returned to approval gate 0.

## Planner limitation recorded

The planner's D8 negative discriminator did not reproduce in this skill's own live session, so it
was not promoted into the test. Grid *row* occupancy was never proven by this skill through a
user-visible affordance and is reported as an unobserved capability rather than asserted.
