# Pilot B-S1 Planner Plan — Add Bin to New Layout

## Application Overview

Frozen scenario B-S1 (scope preserved byte-for-byte, no additions/splits/rewording):
Given the application is served at http://localhost:5174, fresh browser profile, empty client-side storage
When the user performs the actions the outcome below requires
Then adding a bin to a new layout places it on the baseplate grid and the layout summary reflects the added bin.

This document contains ONLY hardening deltas for the single frozen scenario above, grounded by live exploration of http://localhost:5174 in this session plus a read of e2e/fixtures.ts and e2e/test-utils.ts. Every delta below is labeled `observed`, `inference`, `verification condition`, or `limitation` per the required taxonomy. No new scenarios were added.

## Test Scenarios

### 1. Add Bin to New Layout

**Seed:** `e2e/seed.spec.ts`

#### 1.1. B-S1: Adding a bin to a new layout places it on the baseplate grid and the layout summary reflects the added bin

**File:** `e2e/pilot-b-s1/add-bin-to-new-layout.spec.ts`

**Steps:**
  1. PRECONDITION [observed]: Start from a fresh browser context/profile with storage cleared (localStorage.clear(), sessionStorage.clear(), and delete all IndexedDB databases via indexedDB.databases()/deleteDatabase — mirrors e2e/test-utils.ts clearAllStorage). Navigate to http://localhost:5174/.
    - expect: [observed] The app auto-provisions a layout and rewrites the URL from '/' to a path of the shape /l/<random-id>/untitled-layout (observed id 'HRJg5aH2ChFR' in this session). The id is non-deterministic per fresh profile — assertions MUST NOT hardcode the id; match the path shape only (e.g. regex /^\/l\/[^/]+\/untitled-layout$/) or avoid asserting on the URL at all.
    - expect: [observed] Page title is 'Gridfinity Planner & Layout Tool — Free Online Drawer Organizer'.
    - expect: [observed] readiness gate: a 'banner' header region and an element with role=application are both present immediately (matches e2e/test-utils.ts waitForAppReady, which waits for selectors 'header' and '[role="application"]'). No loading spinner/dialog blocks interaction after these are present.
    - expect: [observed] The grid element has role=application and accessible name 'Gridfinity drawer grid, 10 columns by 8 rows' (default 10x8 size). Inside it, an empty-state hint is shown: an icon plus paragraph text 'Click and drag to draw a bin'. No element matching '[data-bin-id]' exists (count 0).
    - expect: [observed] Layers panel (left sidebar, region 'Layers') shows a summary line with exact text '0% filled · 0 bins' next to a separate '3/12u' height-budget indicator.
    - expect: [observed] Left sidebar bulk-action buttons read exactly 'Fill 80 gaps' (enabled) and 'Clear layer' (disabled) — 80 = 10x8 empty cells.
    - expect: [observed] Right panel 'Selection' region shows 'No bin selected' and 'Click a bin on the grid or draw to create one'.
    - expect: [observed] Right panel 'Bin List' region header has no numeric badge and its body shows the empty-state copy 'No bins to print' / 'Add bins to the grid to see the print list'.
    - expect: [observed] Header toolbar Undo button is disabled and Redo button is disabled.
    - expect: [observed] Categories panel shows a 'Coral' swatch button labeled 'Coral (selected for new bins)' with pressed=true, i.e. Coral is the default active category applied to new bins; other swatches (Sky, Green, Cloud, Charcoal) are labeled 'Select {Name} for new bins' and each exposes a 'Delete {Name}' action.
    - expect: [limitation] Could not find a stable non-text hook (e.g. data-testid) for the header's save-status indicator in this session; it is only identifiable by transient text content while mounted (see next step).
  2. ACTION [observed]: Draw one bin on the grid by a single mouse drag inside the grid's bounding box — mouse.move to a start point near the grid's top-left cell, mouse.down, mouse.move (with intermediate steps) to a point ~1 cell down and ~1 cell right (covering roughly 2 grid cells x 2 grid cells given cell size ≈ grid_width/10 x grid_height/8), mouse.up. This reproduces e2e/fixtures.ts drawBinOnGrid. No prior click/mode-selection was required — direct drag on the empty grid created a bin on the first attempt.
    - expect: [observed] Exactly one element matching '[data-bin-id]' now exists in the grid (attribute value observed as an opaque id like 'mtxpc8c1-d4f0f744b1' — treat as opaque, do not assert its literal value).
    - expect: [observed] That element has role=button, aria-label exactly 'Bin 2 by 2, category Coral' (size and category reflected in the accessible name), and aria-pressed='true' (the newly created bin is auto-selected).
    - expect: [observed] That element's inline style includes 'grid-area: 1 / 1 / span 2 / span 2' — i.e. it starts at column 1 / row 1 and spans 2 columns x 2 rows, which must fall within the grid's declared bounds (columns 1..10, rows 1..8 per the grid's accessible name captured in the precondition step). It also carries 'background-color: rgb(248, 113, 113)' matching the active 'Coral' category's swatch color.
    - expect: [observed] The grid's empty-state hint ('Click and drag to draw a bin' paragraph + icon) is no longer present.
    - expect: [verification condition] Assert the bin's grid-area/columns+rows are inside the grid's bounds — a bin rendered off-grid or overflowing the drawer boundary would still satisfy a naive count-only assertion but must fail this check.
    - expect: [verification condition] Assert the aria-label encodes both the drawn size and the currently active category together (e.g. via regex /^Bin \d+ by \d+, category \w+$/) — this catches a bin created with the wrong dimensions or an unassigned/wrong category, which a bare '[data-bin-id]' toHaveCount(1) would miss entirely.
  3. VERIFY layout-summary surfaces update together [observed].
    - expect: [observed] Layers panel summary line changes from '0% filled · 0 bins' to exactly '5% filled · 1 bins' (4 of 80 cells filled by the 2x2 bin = 5%).
    - expect: [observed] Left sidebar bulk-action buttons change to exactly 'Fill 76 gaps' (80-4) and 'Clear 1 bins' (now enabled, was disabled 'Clear layer').
    - expect: [observed] Right panel switches from the 'Selection' region ('No bin selected') to a 'Bin Properties' region with heading exactly '2×2 Bin', Width spinbutton value '2', Depth spinbutton value '2', size readout '84 × 84 × 21 mm', Height spinbutton value '21' (= 3u, matching the currently selected Layer 1's height), and a 'Bin category' combobox with 'Coral' selected.
    - expect: [observed] Right panel 'Bin List' region header changes to exactly 'Bin List 1' with a numeric badge '1', and its body changes from the empty-state copy to a table with header row cells 'Size', 'H', 'Qty', 'Fil.' and one data row showing category+size 'Coral 2×2', height '3u', qty '1', and a filament-grams figure '21.45'. An accompanying summary shows time '~1h 36m', cost '$1.30', bin total 'text containing 1 bins', filament length '~21.5m filament', and a spool-usage figure '6.5%'.
    - expect: [observed] Header toolbar Undo button transitions from disabled to enabled; Redo remains disabled.
    - expect: [observed] Categories panel's Coral swatch button relabels from 'Coral (selected for new bins)' to 'Apply Coral to 1 selected bin(s)' (still pressed) and shows a new 'Coral 1 bin(s) use this category' badge in place of its prior 'Delete Coral' affordance; the other four category swatches keep their 'Delete {Name}' affordance but their select-action relabels to 'Apply {Name} to 1 selected bin(s)' while a bin is selected.
    - expect: [verification condition] Assert the Layers-panel percentage AND bin-count portions of the single summary string move together and are numerically consistent with the drawn bin's cell area — a regression that appends a DOM node without recomputing the derived summary text would pass a naive '[data-bin-id]' count check but fail this string-level assertion.
    - expect: [verification condition] Assert the Bin List table row's category/size/height/qty match the bin actually drawn — this catches a bin added to the canvas that is not reflected in the derived print-list aggregation (a distinct code path from grid rendering).
    - expect: [verification condition] Assert Undo becomes enabled — this catches a bin that renders visually but is not pushed onto the undo/history stack, which would also silently break later undo/redo and persistence-diffing behavior.
    - expect: [verification condition] If the test suite also asserts 'no unexpected console errors' for this flow, it must allow-list the pre-existing, functionality-unrelated background error observed in this session: 'Failed to load resource: the server responded with a status of 404 (Not Found) @ http://localhost:5174/api/ml-telemetry' — this fires on page load regardless of the bin-adding action and is unrelated to it.
  4. READINESS/PERSISTENCE GATE [observed + limitation]: Immediately after the drag-drop action in step 2, observe the header save-status indicator.
    - expect: [observed] A transient element (role=status at the time it is present) shows text 'Saving...' and then 'Saved' shortly after the mutation. Re-querying the DOM a short time later shows this element and its container removed entirely — it is NOT a persistent status region (unlike the separate Stash status region, which has a stable aria-label 'Stash' and remains in the DOM). A deterministic test must assert on the 'Saved' text appearing in a bounded window right after the action, and must not assume the node remains queryable afterward.
    - expect: [limitation] e2e/test-utils.ts exposes a `waitForAutoSave` helper that polls localStorage for keys 'gridfinity-library-v1' and 'gridfinity-layout-${activeId}' as its persistence-readiness signal. Live inspection of localStorage after creating a layout and adding a bin in this session shows NEITHER key exists; the observed localStorage keys were: gridfinity-library-active-id, gridfinity-migration-analytics-v1, gridfinity-migration-ml-to-idb-v1, gridfinity-localstorage-cleaned, gridfinity-migration-onboarding-kebab-v1, gridfinity-device-id, gridfinity-analytics-v1, gridfinity-settings-v1, gridfinity-migration-hints-v1, gridfinity-migration-shared-with-me-idb-v1, gridfinity-onboarding-draw-tutorial-seen, gridfinity-whats-new-v1, gridfinity-nudges-v1. Live IndexedDB inspection shows three databases instead: gridfinity-db, gridfinity-designer-v1, gridfinity-events-db — the app now persists layout/bin data in IndexedDB, not localStorage. Conclusion: `waitForAutoSave` as currently written is stale relative to the live app and MUST NOT be relied on as the save/persistence gate for this scenario; use the transient 'Saved' status text as the readiness signal instead, or poll IndexedDB directly.
    - expect: [limitation] This session did not attempt to force a save/persistence failure (e.g. simulated IndexedDB write error) to observe failure-mode UI, since the frozen scenario B-S1 covers only the happy-path outcome and probing failure UI would exceed the frozen scope.
