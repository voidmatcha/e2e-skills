# Pilot B-S2: Drawer resize displaces non-fitting bin to Stash

## Application Overview

Gridfinity Layout Tool (http://localhost:5174/). Entry route `/` self-navigates to `/l/<id>/untitled-layout` with a fresh layout. The left sidebar "Grid Size" region controls drawer width/depth in grid units (`Drawer width in grid units` / `Drawer depth in grid units` spinbuttons, with Increase/Decrease buttons). The grid canvas is `[role="application"]` with aria-label `Gridfinity drawer grid, {cols} columns by {rows} rows`. Bins are drawn by drag on the canvas and rendered as `[data-bin-id]` elements with an inline `grid-area: {row} / {col} / span {h} / span {w}` style (CSS grid numbering: column 1 = left/anchored edge, highest column = right edge; row 1 = top/edge that gets truncated on depth decrease, highest row = bottom/anchored edge). When a resize makes a bin's cell(s) fall outside the new grid bounds, that exact bin (same id) is removed from `[data-bin-id]` and re-appears inside the Stash panel (`[data-stash]`) as `[data-staging-bin-id]`. This is the single frozen scenario B-S2: "Changing the drawer dimensions recomputes the baseplate grid, and a bin that no longer fits is reported rather than silently kept."

LIVE-OBSERVED DELTAS FOR RECONCILIATION (all resolved on the live app this session unless marked otherwise):

(a) Locators — additional/better quality, all `observed` live this session:
  - Stash bin count / header toggle: `button[aria-expanded]` inside `[data-stash]`, accessible name is exactly `Stash {N} bins` (e.g. `Stash 1 bins`, `Stash 2 bins`) — a single robust role=button + accessible-name locator for "how many bins are currently stashed", better than parsing raw text. `page.getByRole('button', { name: /^Stash \d+ bins$/ })`.
  - Stash bin card: `button` with accessible name exactly `1×1` inside `#staging-stash-panel` (the `aria-controls` target of the toggle button above), also carries a nested control `Rotate bin (R)`.
  - Drawer width/depth decrease/increase buttons resolve reliably via plain CSS attribute selector `button[aria-label="Decrease Drawer width in grid units"]` / `...depth...` (used directly, no ref needed).
  - Grid canvas: `[role="application"]` aria-label pattern confirmed as `Gridfinity drawer grid, {N} columns by {M} rows`, updates synchronously (readable immediately after the click resolves, no extra wait required).
  - Empty-stash-only status: `[data-stash]` div carries `role="status"` (implicit aria-live=polite) ONLY while empty (text `Stash — Drag a bin here to stash it`). This is `observed`.

(b) Most valuable finding — user-visible-but-NOT-screen-reader-announced signal: `observed`. Immediately after a resize displaces a bin, there is NO `[role="status"]`, `[role="alert"]`, or `[aria-live]` element anywhere on the page (verified via `document.querySelectorAll('[role="status"],[role="alert"],[aria-live]')` returning `[]` right after the resize click). The `role="status"` that exists on the empty Stash placeholder is REMOVED once the stash becomes non-empty (confirmed via raw `outerHTML` dump — the populated stash header is a plain `<div>` containing a `<button aria-expanded="true" aria-controls="staging-stash-panel">`, no live-region role at all). So "reported rather than silently kept" is evidenced ONLY by structural/visual DOM changes (bin disappears from `[data-bin-id]`, reappears under `[data-staging-bin-id]` with the same id, stash header text/count changes, grid aria-label changes) — there is no toast, no alert, and no ARIA live-region announcement a screen reader would pick up. This is a `limitation`, not an inference.

(c) Race/flake hazards, `observed`:
  - No debounce observed: state (grid aria-label, `[data-bin-id]` set, stash contents) is fully updated synchronously by the time the click's evaluate call runs; no artificial wait was needed between the resize click and reading DOM state.
  - The header autosave indicator (`status` region showing "Saving...") is transient and was already gone (no `role="status"` matched, no "sav" text anywhere in `<header>`) a few actions later — tests must not assert on "Saving..." appearing/disappearing as a synchronization signal for this scenario; it is unrelated and flaky to key off.
  - The app fires background `POST /api/ml-telemetry` requests that return `404 Not Found` and log as console errors, repeatedly, unrelated to grid/bin/resize logic — a test must not fail merely because "a console error was logged"; it should filter for/ignore `ml-telemetry` 404s.

(d) Verification conditions the test MUST encode, `observed` (all confirmed live):
  - Control condition (still-fits bin is NOT displaced): a bin placed at the anchored edge (column 1 for width; the highest row index / bottom edge for depth) remains in `[data-bin-id]` with an updated (but still present) `grid-area` after the resize — proves the mechanism is selective, not "clear everything."
  - Width truncation removes columns from the HIGH-index (right) edge: a bin at the last column is displaced; a bin at column 1 is untouched (`grid-area` unchanged).
  - Depth truncation removes rows from the LOW-index (CSS `grid-row` 1 / visual top) edge — this is a DIFFERENT edge than width's anchor side. A bin placed at `grid-row 1` IS displaced to the stash on depth decrease. A bin placed at the last/highest row (bottom, "anchored") is NOT displaced — instead its `grid-row` index is renumbered/shifted down by exactly 1 to keep tracking the new last row, and it stays on the grid across multiple successive depth decreases (verified across 6 consecutive decreases from depth 8 down to depth 1, with the anchored bin's row index shifting 8→7→6→5→4→3→2→1, never displaced). A depth-only test must therefore place its "displaced" probe bin at row 1 (top), mirroring width's probe at the last column — using the SAME edge convention (column 1 / last row) for the "control, stays" bin would give a false negative for depth.
  - Same-id continuity: the displaced bin's `data-bin-id` value found in `[data-staging-bin-id]` after resize must equal the `data-bin-id` it had before resize (confirmed identical ids across the transition in all trials).

(e) What the app does NOT do, honestly reported:
  - `limitation`: No toast/snackbar/alert appears when a bin is displaced.
  - `limitation`: No ARIA live-region announcement fires for the displacement (see (b) above) — accessible-technology users get no auditory/status cue distinct from the empty-state placeholder text.
  - `limitation`: Depth decreases do not always displace bins the way width decreases do — most existing bins are simply renumbered/shifted in place as long as they still fit somewhere in the shrunk grid on the anchored side; only bins that actually fall outside the new bounds (at the row-1/top edge for depth) get displaced. This is not a bug per the scenario ("a bin that no longer fits is reported") but testers should not assume every bin near a resized edge gets displaced — only ones that literally no longer fit do.


## Test Scenarios

### 1. Baseplate grid resize / bin displacement

**Seed:** `e2e/seed.spec.ts`

#### 1.1. B-S2: Changing drawer dimensions recomputes the grid and displaces a bin that no longer fits into the Stash, rather than silently keeping/dropping it

**File:** `specs/pilot-b-s2.spec.ts`

**Steps:**
  1. Navigate to http://localhost:5174/ with a fresh browser profile and empty client-side storage.
    - expect: The app self-navigates to a URL matching /l/{id}/untitled-layout.
    - expect: The grid canvas [role="application"] has accessible name (aria-label) exactly "Gridfinity drawer grid, 10 columns by 8 rows".
    - expect: The sidebar 'Grid Size' region shows spinbutton 'Drawer width in grid units' = 10 and 'Drawer depth in grid units' = 8.
    - expect: The sidebar shows the drawer size summary text "420 × 336 × 84 mm".
  2. On the grid canvas, click-and-drag to draw a 1x1 bin whose top-left cell lands in the last (10th) column, row 1 (i.e. click inside the cell under the 'Select bins in column 10' header, near the bottom/anchored row). Record the resulting element's data-bin-id attribute and its inline grid-area style as bin A.
    - expect: A new element matching [data-bin-id] appears with accessible name 'Bin 1 by 1, category Coral' and an inline style containing 'grid-area: {row} / 10 / span 1 / span 1'.
  3. On the grid canvas, click-and-drag to draw a second 1x1 bin whose top-left cell lands in column 1 (the anchored/left edge). Record its data-bin-id and grid-area style as bin B (control bin).
    - expect: A second [data-bin-id] element appears with an inline style containing 'grid-area: {row} / 1 / span 1 / span 1'.
    - expect: There are now exactly 2 elements matching [data-bin-id] on the grid, and 0 matching [data-staging-bin-id] in the Stash.
  4. Click the button with accessible name 'Decrease Drawer width in grid units' exactly once.
    - expect: The grid canvas [role="application"] accessible name updates to 'Gridfinity drawer grid, 9 columns by 8 rows'.
    - expect: The 'Drawer width in grid units' spinbutton value updates to 9.
    - expect: The sidebar drawer size summary updates to "378 × 336 × 84 mm".
    - expect: Bin A's id is NO LONGER present among [data-bin-id] elements on the grid (it was reported/removed, not silently left in an invalid position).
    - expect: An element matching [data-staging-bin-id] whose data-staging-bin-id equals bin A's original data-bin-id now exists inside the Stash panel [data-stash] (specifically inside the region with id 'staging-stash-panel').
    - expect: Bin B's id is STILL present among [data-bin-id] on the grid, with its grid-area column index unchanged at 1 (control condition: a still-fitting bin is not touched).
    - expect: The Stash toggle button's accessible name is exactly 'Stash 1 bins', and a button with accessible name '1×1' is present inside the stash contents.
  5. Verify no ARIA live-region communicates the displacement: query the page for [role="status"], [role="alert"], and [aria-live] immediately after the previous step.
    - expect: No element matches any of [role="status"], [role="alert"], or [aria-live] once the Stash is non-empty (the role="status" that exists only on the empty-Stash placeholder is gone). This is expected/known app behavior — the test must not assert an aria-live announcement exists; it must rely on the structural/visual signals asserted in the previous step instead.
  6. On the grid canvas (now 9 columns by 8 rows), draw a 1x1 bin at CSS grid row 1 (the visual top edge of the grid) — this is bin C, the depth-side displacement probe. Also draw a 1x1 bin at the highest/last row (visual bottom, the depth-anchored edge) — this is bin D, the depth-side control bin. Record both ids and grid-area styles.
    - expect: Bin C's inline style contains 'grid-area: 1 / {col} / span 1 / span 1'.
    - expect: Bin D's inline style contains 'grid-area: 8 / {col} / span 1 / span 1'.
  7. Click the button with accessible name 'Decrease Drawer depth in grid units' exactly once.
    - expect: The grid canvas accessible name updates to 'Gridfinity drawer grid, 9 columns by 7 rows'.
    - expect: Bin C's id is NO LONGER present among [data-bin-id] on the grid, and an element matching [data-staging-bin-id] with that same id now exists in the Stash (it was reported, not silently dropped).
    - expect: Bin D's id IS STILL present among [data-bin-id] on the grid; its grid-area row index has shifted from 8 to 7 (it was renumbered to stay on the anchored/bottom edge, not displaced, because it still fits) — this must be asserted explicitly as a control condition distinct from bin C's outcome.
    - expect: The Stash toggle button's accessible name is now 'Stash 2 bins'.
