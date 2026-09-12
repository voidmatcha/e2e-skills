# Pilot B-S1 Plan Deltas — Add Bin to New Layout

## Application Overview

This document contains PLAN DELTAS ONLY for the single frozen scenario B-S1. It does not add, split, or reword the scenario. It supplements the approved scenario with additional acceptance criteria, an observed role/name/state map, observed state transitions, and honesty-rule limitations, gathered by live exploration of the Gridfinity Layout Tool at http://localhost:5174/ (fresh profile). All items are labeled `observed`, `inference`, `verification condition`, or `limitation` per instructions.

Frozen scenario (unchanged, reproduced for reference only):
- Given: the application is served at http://localhost:5174, fresh browser profile, empty client-side storage
- When: the user performs the actions the outcome below requires
- Then: Adding a bin to a new layout places it on the baseplate grid and the layout summary reflects the added bin.

## Test Scenarios

### 1. B-S1 Plan Deltas (reference only, not new test cases)

**Seed:** `e2e/seed.spec.ts`

#### 1.1. Delta notes for: Adding a bin to a new layout places it on the baseplate grid and the layout summary reflects the added bin

**File:** `specs/pilot-b-s1-planner-plan.md`

**Steps:**
  1. [observed] Navigate to http://localhost:5174/ with a fresh profile.
    - expect: The app auto-redirects to a generated per-layout URL of the form /l/<id>/untitled-layout (observed redirect target during exploration: /l/dWekRSz3vNyR/untitled-layout). This confirms a fresh, empty layout is created automatically on first load; there is no separate 'New Layout' button to click for the base case.
    - expect: [verification condition] The final spec should assert the URL matches /^\/l\/[^/]+\/untitled-layout$/ (or similar) after navigating to '/', to prove it is starting from a genuinely fresh/empty layout rather than a previously-created one. This guards against a bug where the app reuses a stale layout from storage that already has bins.
  2. [observed] Capture the empty/before state of every element the outcome depends on.
    - expect: Grid container: role=application, accessible name exactly 'Gridfinity drawer grid, 10 columns by 8 rows'. Inside it, when empty, there is a paragraph with text exactly 'Click and drag to draw a bin' plus a decorative icon — this is the empty-state placeholder, not a bin.
    - expect: Layer summary line (left sidebar, under 'Layers' region): two generic (non-interactive) text nodes read exactly '0% filled · 0 bins' and '3/12u' before any bin exists.
    - expect: Bin List panel (right sidebar Inspector, 'Bin List' accordion): heading/button accessible name is exactly 'Bin List' (no numeric badge). Body contains paragraph 'No bins to print' and paragraph 'Add bins to the grid to see the print list'.
    - expect: Selection panel (right sidebar Inspector, top accordion): accessible name 'Selection', body contains paragraph 'No bin selected' and paragraph 'Click a bin on the grid or draw to create one'.
    - expect: Left sidebar 'Clear layer' button: role=button, disabled=true, accessible name exactly 'Clear layer' before any bin exists.
    - expect: Left sidebar 'Fill 80 gaps' button: role=button, enabled, accessible name exactly 'Fill 80 gaps' (this number is drawer-size dependent: 10x8 grid = 80 cells, so this is 'inference'-adjacent but was directly read off the live page for the default 10x8 drawer).
    - expect: Top toolbar 'Undo (Ctrl+Z)' button: disabled=true before any action.
    - expect: [verification condition] All six of the above before-states should be asserted (or at minimum the grid empty-state paragraph, the layer summary text, and the Bin List empty-state text) BEFORE performing the add-bin action, so the test proves a real 0-to-1 transition rather than asserting a static end state that could trivially pass on a stale/pre-populated layout.
  3. [observed] Perform a click-and-drag gesture inside the grid application element (mouse down inside one cell, move to an adjacent cell, mouse up) to draw a bin, matching the documented affordance 'Click and drag to draw a bin' / keyboard-panel hint 'Drag → Draw to create a bin'.
    - expect: [observed] A new element appears inside the grid application with role=button and accessible name matching the pattern 'Bin {W} by {D}, category {CategoryName}' — observed exact string: 'Bin 2 by 2, category Coral' (size varies with drag distance; the pattern '^Bin \\d+ by \\d+, category .+$' is the stable, non-tautological locator to use, not a hardcoded '2 by 2').
    - expect: [observed] The new bin button has aria-pressed/state 'pressed' = true immediately after creation, i.e. it is auto-selected. It also exposes 8 resize handles (role=slider, names 'Resize left edge', 'Resize right edge', 'Resize top edge', 'Resize bottom edge', 'Resize top-left corner', 'Resize top-right corner', 'Resize bottom-left corner', 'Resize bottom-right corner').
    - expect: [observed] The grid's empty-state paragraph 'Click and drag to draw a bin' is gone (no longer present in the accessibility tree) once a bin exists.
    - expect: [verification condition] Assert the count of elements matching role=button with name pattern '^Bin \\d+ by \\d+, category .+$' inside the grid application goes from 0 (before) to exactly 1 (after) — not 'at least 1' — to catch a bug where a single drag gesture erroneously creates duplicate/ghost bins.
    - expect: [verification condition] Assert grid alignment/snapping, i.e. that the outcome's claim 'places it on the baseplate grid' is real, not just 'a bin-shaped element exists somewhere on screen'. Observed measurement: grid application bounding box was {x:350,y:119,width:551,height:441} for a 10x8 grid (cell ≈55.1w × 55.1h px at the exploration zoom level of 170%), and the created bin's bounding box was {x:351,y:120,width:109,height:109} — i.e. offset from the grid's top-left corner by ≈0.018 of a cell width/height (effectively 0, within a hairline/border tolerance) and sized ≈1.98 x 1.98 cells (effectively 2x2). The final spec should compute (binBox.x - gridBox.x) / cellWidth and (binBox.y - gridBox.y) / cellHeight and assert each is within a small epsilon (e.g. 0.1) of an integer, using the grid's own bounding box and column/row count (10, 8) read from its accessible name rather than hardcoded pixel constants, since pixel geometry depends on zoom/viewport.
  4. [observed] Re-capture the same elements enumerated in the 'before' step to confirm the layout summary changed.
    - expect: [observed] Layer summary text changed from '0% filled · 0 bins' to '5% filled · 1 bins' (percentage is size-dependent — the stable assertion is the ' bins' suffix count going 0 → 1 and the percentage becoming non-zero, not the literal '5%'). The '3/12u' headroom text is unchanged (unaffected by bin count, only by layer height), confirming the test should NOT assert this value changes.
    - expect: [observed] Bin List accordion header accessible name changed from 'Bin List' to 'Bin List 1' (a numeric badge/count of 1 is appended). A sibling 'Copy bin list as TSV' button (role=button) also newly appears — it was not present in the empty state.
    - expect: [observed] Bin List body changed from the two empty-state paragraphs to a table (role=table) with columnheaders exactly 'Size', 'H', 'Qty', 'Fil.' and one data row whose cells read 'Coral 2×2' (category + size), '3u' (height), '1' (qty), '21.45' (filament estimate, numeric/variable).
    - expect: [observed] The right-sidebar 'Selection' accordion is entirely replaced by a 'Bin Properties' accordion (different accessible name, not just different body content) containing heading level 2 'Bin 2×2' region text '2×2 Bin' and a 'Deselect bin' button — i.e. selecting/creating a bin swaps which accordion section is present, this is a strong, hard-to-fake signal that the created bin is the one being summarized.
    - expect: [observed] Left sidebar 'Clear layer' button becomes enabled and its accessible name changes to 'Clear 1 bins' (was disabled/'Clear layer'). 'Fill 80 gaps' becomes 'Fill 76 gaps' (80 - 4 cells consumed by the 2x2 bin = 76) — a secondary, size-dependent but internally-consistent cross-check.
    - expect: [observed] Top toolbar 'Undo (Ctrl+Z)' button becomes enabled (was disabled) — evidence the action was recorded in history, not just rendered transiently.
    - expect: [verification condition] The final spec's core assertions for 'the layout summary reflects the added bin' should target at least: (a) the Bin List accordion header text containing '1' / a bin-count badge, AND (b) the layer summary text containing '1 bins' (not '0 bins') with a non-zero fill percentage. Relying on only one of these is weaker; a bug could update the layer stats but leave the Bin List panel stale (or vice versa), and a naive single-signal assertion would miss that desync.
    - expect: [verification condition] Do not assert the literal fill percentage ('5%'), filament estimate ('21.45'), print time, cost, or gap count as exact strings — these are derived from bin size/drag distance and are not stable/deterministic across test runs unless the drag gesture is pixel-exact. Assert their presence/non-zero-ness and the count fields ('1 bins', 'Bin List 1', qty cell '1') which are deterministic for 'exactly one bin was added'.
  5. [observed] Note a non-blocking background console error unrelated to the feature.
    - expect: [observed] A single console error was logged: 'Failed to load resource: the server responded with a status of 404 (Not Found) @ http://localhost:5174/api/ml-telemetry'. This fired once on page load, independent of the bin-add action, and is an unrelated analytics/telemetry call failing in the local dev environment. [limitation] This should NOT be treated as a failure condition for this scenario; flagging it only so the implementing agent doesn't mistake it for a real functional regression or accidentally assert 'no console errors' as part of this scenario (which would make the test fail for reasons unrelated to bin placement).
