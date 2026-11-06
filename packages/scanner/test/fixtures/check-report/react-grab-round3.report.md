## Review Scope and Evidence
- **Mode:** full mode; evidence route: semantic review (scanner plus manual Phase 2).
- **Behavior under review:** the react-grab Playwright suite in `packages/react-grab/e2e` (about 84 files, 731 KB), looking for weak or always-passing assertions.
- **Diff base/range:** N/A
- **Changed E2E artifacts:** N/A (full mode)
- **Context-only files consulted:** `packages/react-grab/e2e/fixtures.ts` (the `reactGrab` fixture, `getState`, `hoverUntilSelected`, `getContextMenuInfo`, `waitForCallback`, `isOverlayVisible`, `isToolbarVisible`).
- **Static evidence:**
  - **Scanner:** the bundled scanner ran on `packages/react-grab/e2e` and finished **INCOMPLETE** (exit 2). It listed 30 `provenance-unsupported` analysis tasks, with 0 confirmed P0, 238 triage candidates, 44 P0 candidates and 124 P1/P2 heuristic hits. It reports Playwright provenance as unsupported for the specs.
  - **Likely cause:** every spec imports `test` and `expect` from `./fixtures.js`, a `.js` specifier that points at `fixtures.ts`. I did not confirm that cause, so the scan is not clean. I read the fixture import chain by hand: `fixtures.ts` imports `@playwright/test` and calls `base.extend`, so Playwright provenance holds.
  - **Project ESLint:** not executed.
  - **Not clean:** the scanner's INCOMPLETE status stands, and no part of this review rests on a "clean scan".
  - **Candidate verdicts:**
    - #5a: 12 line-level verdicts below. I did not give a separate verdict to every #5a candidate line the scanner listed (the full list is in the report file).
    - #3: `app-theme-detection.spec.ts:21` (best-effort wait; the returned attribute is asserted afterwards), `fixtures.ts:662` (best-effort scroll wait) and `perf-bench.spec.ts:172` (fire-and-forget load fetch) are FALSE-POSITIVE.
    - #4a, `visual-feedback.spec.ts:188/208/228`: FALSE-POSITIVE. The bound `label.x >= 0` can fail when the label is off-screen, and the `if (bounds?.arrow)` guard sits after `expect(bounds?.arrow).not.toBeNull()`.
    - #11c: all 20 bare-`skip` candidates pass a reason string, so they are cleared.
    - #5a:
      - `activation-edge-cases.spec.ts:206`: FALSE-POSITIVE, both bounds are asserted non-null above the `if`.
      - `focus-trap.spec.ts:140`, `selection.spec.ts:228`, `visual-feedback.spec.ts:12/31/47`: FALSE-POSITIVE, `hoverUntilSelected` throws unless a selection box exists.
      - `viewport.spec.ts:131`: FALSE-POSITIVE, `initialBounds` is asserted non-null above the `if`; I did not trace what happens when `newBounds` is null.
      - `perf-*.spec.ts` `expect.soft` inside `if (SHOULD_ASSERT_INP)`: FALSE-POSITIVE, a documented environment gate.
      - `framework/*` and `framework-production.spec.ts` conditionals: FALSE-POSITIVE, they depend on the project (dev, production or Next.js) and each test has unconditional assertions.
      - `heavy-ui.spec.ts`, `hit-test-shield.spec.ts` and `shadow-dom.spec.ts` bare `return`s: FALSE-POSITIVE, an `expect(box).not.toBeNull()` runs just before each one.
  - **Not individually resolved:** the #6 (145 hits) and #10a (16 hits) candidates. They are mostly `page.evaluate` shadow-DOM reads, and I did not give each its own verdict.
  - **Sweeps (hits):**
    - #3b: N/A (Playwright).
    - #3: 9 hits, no P0 (the matches are `.catch()` calls and retry loops that rethrow on the last attempt).
    - #5a: all rows run.
    - #7: 0.
    - #9b: N/A.
    - #9c: 15 (all `domcontentloaded`, not `networkidle`).
    - #19: 0.
    - #10b: 4 (`shift-multi-select.spec.ts:15` is a finding; the three `perf-*` configure calls take their mode from a constant).
    - #10d: N/A.
    - #4a: 3 (cleared).
    - #4f: 147 raw hits, resolved in the #4 finding.
    - #4i: 0.
    - #4k: 0.
    - #11c: 20.
    - #10c: 1 (`hit-test-shield.spec.ts:70`, `level: 1` heading with no name).
    - #18: 6 (all `perf-*`, environment-gated).
    - #4g: 0.
    - #5b: 15 (8 are findings).
    - #9: 115.
    - #10f: N/A.
    - #17: 29.
    - #8b: 0 real.
    - #15: 0.
    - #16: 1 (`toolbar-selection-hover.spec.ts:6`, which returns the promise from an arrow function, so it is fine).
  - **Per-procedure file coverage:**
    - #1: sampled.
    - #2: sampled.
    - #12: N/A (see below).
    - #13: sampled.
    - #20–#23: N/A (see below).
  - **Per-procedure notes:**
    - #1/#2: I read the tests behind each finding below. I did not read all 84 files line by line, so this is sampled and not N/N.
    - #12: N/A. The suite has no auth surface, since it tests a client-side overlay library.
    - #13: I found no established same-page POM boundary that raw selectors bypass, so there is no finding. I read only a sample of files.
    - #20, #21, #22, #23: N/A. There are no backend writes, no `storageState` and no list fixtures.
  - **Analysis tasks:** I did not disposition the 30 scanner analysis tasks one by one. The one common cause is the import specifier described above.
- **Runtime evidence:** not executed. Running the suite needs the dev servers and checkout trust.
- **Independent verification:** inline only. I re-read each finding's test body and the fixture code it depends on. I did not use the delegated verifier.
- **Limitations/exclusions:** the scan is INCOMPLETE. The #6 and #10a candidates, the 30 analysis tasks and most #1/#2/#13 coverage are not exhaustively reviewed. `perf-*.ts` helper files are mostly unread.

## [P0] packages/react-grab/e2e/activation-key-config.spec.ts:11 — #4a/#4f Invariant assertions
### `Activation Key Configuration › should accept … option` and 20 similar tests
- **Issue:** these assertions are true whatever the product does. `getState()` in `fixtures.ts` returns a fallback object when `__REACT_GRAB__` is missing, so `expect(state).toBeDefined()` can never fail. `isOverlayVisible()` ends in `?? false`, and `isToolbarVisible()` returns `false` on every miss path, so `typeof x === "boolean"` can never fail. The tests do exercise an action, but nothing checks its result: `reinitialize({ activationKey })` is never followed by a check that the key activates anything.
- **Lines (28):**
  - `activation-key-config.spec.ts:11, 20, 30, 40, 49, 58, 70`
  - `edge-cases.spec.ts:33, 59, 97, 125, 143, 164, 265`
  - `activation.spec.ts:163`
  - `api-methods.spec.ts:78, 121`
  - `toolbar.spec.ts:607`
  - `open-file.spec.ts:396`
  - `touch-mode.spec.ts:24, 60, 219, 236`
  - `malformed-events.spec.ts:281`
  - `drag-selection.spec.ts:427`
  - `visual-feedback.spec.ts:66, 155`
  - `theme-customization.spec.ts:87`
- **Notes:** I read the test bodies for most of these. I did not open `touch-mode.spec.ts:60`, and I relied on its matching shape. At `visual-feedback.spec.ts:66` and `theme-customization.spec.ts:87`, `getDragBoxBounds()` returns `… | null`, so `toBeDefined()` passes on `null` too. The "does not throw" cases (`edge-cases.spec.ts`, `malformed-events.spec.ts:281`) do check one thing, that no page error was thrown, but the closing assertion adds nothing to that.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** assert the effect each title promises. For example, after `reinitialize({ activationKey: "g" })`, press `g` and expect `getState().isActive` to be `true`.
- **Verification:** recommended — run one test with the assertion deleted; it should still pass, which shows the assertion adds nothing (V2).
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  await reactGrab.reinitialize({ activationKey: "g" });
  await reactGrab.page.keyboard.press("g");
  await expect.poll(() => reactGrab.isOverlayVisible()).toBe(true);
  ```

## [P0] packages/react-grab/e2e/api-methods.spec.ts:136 — #5a Conditional assertion bypass
### `should return dragBounds during drag` and 10 similar tests
- **Issue:** the only assertions sit inside an `if` on the thing being verified. If the feature breaks (no drag bounds, no context menu, no callbacks recorded, no toolbar position), the `if` is false and the test passes with nothing checked. The context-menu pair is worse, because `getContextMenuInfo()` itself returns `position: null` when no menu rendered.
- **Lines (11):**
  - `api-methods.spec.ts:136` (`state.dragBounds`)
  - `context-menu.spec.ts:391, 404` (`menuInfo.position`; also a one-sided bound)
  - `drag-selection.spec.ts:438` (`count > 0`)
  - `drag-selection.spec.ts:476` (`box`)
  - `event-callbacks.spec.ts:231` (the order check is skipped when either callback is missing)
  - `overlay-filtering.spec.ts:77` (`toolbarInfo.position`)
  - `touch-mode.spec.ts:194` (`box`)
  - `visual-feedback.spec.ts:87` (drag-box bounds)
  - `toolbar.spec.ts:286` (`should not drag when collapsed`)
  - `toolbar.spec.ts:469` (`snapEdge`; the weakest — I did not read how the test sets the edge before the reload)
- **Attribution (diff mode):** N/A in full mode
- **Fix:** assert the guard value first, then check the dependent value. Keep the fix to this.
- **Verification:** recommended — break the drag-bounds feature and confirm the test fails (V3).
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  const state = await reactGrab.getState();
  expect(state.dragBounds).not.toBeNull();
  expect(state.dragBounds!.width).toBeGreaterThan(0);
  expect(state.dragBounds!.height).toBeGreaterThan(0);
  ```

## [P1] packages/react-grab/e2e/hover-reveal.spec.ts:123 — #9 Hard-coded sleeps
### 115 `waitForTimeout` calls
- **Issue:** the scanner confirmed 115 fixed sleeps, concentrated in `perf-bench.spec.ts`, `freeze-animations.spec.ts`, `hover-reveal.spec.ts`, `interference-ui.spec.ts`, `heavy-ui.spec.ts` and `event-callbacks.spec.ts`. Many sit just before an assertion that already polls or waits (for example `event-callbacks.spec.ts` waits 500 ms and then calls `getCallbackHistory()`, which could be `waitForCallback`). Sleeps inside the perf load generators are deliberate pacing and are not the target.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** replace each sleep that precedes an assertion with `expect.poll` or `waitForFunction` on the condition it waits for.
- **Verification:** recommended — run the affected specs with `--repeat-each` after the change.
- **§4.1 row:** no row (judgement call)

## [P1] packages/react-grab/e2e/activation.spec.ts:110 — #17 Selector-based Page actions
- **Issue:** `reactGrab.page.click("...")` and `.fill("...")` are the discouraged selector-string form, about 29 call sites. They are in `activation.spec.ts`, `activation-edge-cases.spec.ts`, `activation-key-config.spec.ts`, `malformed-events.spec.ts`, `freeze-updates.spec.ts`, `hold-activation.spec.ts`, `edge-cases.spec.ts` and `combinatorial-interactions.spec.ts`. The scanner did not flag them, because the receiver is `reactGrab.page` and its Page provenance was unsupported.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** use `reactGrab.page.locator("[data-testid='test-input']").click()` or `getByTestId(...)`.
- **Verification:** N/A
- **§4.1 row:** no row (judgement call)

## [P1] packages/react-grab/e2e/heavy-ui.spec.ts:50 — #5b `force: true` without `// JUSTIFIED:`
- **Issue:** forced clicks bypass actionability checks with no rationale comment. Lines: `heavy-ui.spec.ts:50, 53` and `perf-bench.spec.ts:317, 764, 790, 876, 881, 898`. At `heavy-ui.spec.ts:50, 53` the title promises "filter input still types while selection mode is active", and `force` hides the case where the overlay blocks the input.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** suggest only; first check why the default actionability checks fail. Remove `force` only if the test still passes without it.
- **Verification:** recommended — run the test without `force`.
- **§4.1 row:** the table lists `scrollIntoView().click({ force: true })` and `should("be.visible").click({ force: true })`; the rule is "Verify the actual actionability blocker and intent before removing `force`".

## [P1] packages/react-grab/e2e/shift-multi-select.spec.ts:15 — #10b Serial describe
- **Issue:** `test.describe.configure({ mode: "serial" })` couples the tests, so one failure skips the rest of the file.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** remove the serial mode if the tests do not share state, or document the dependency with `// JUSTIFIED:`.
- **Verification:** recommended — run the file with `--shard` or `--workers=4`.
- **§4.1 row:** no row (judgement call)

## Review Summary

| Sev | Count | Top Issue | Affected Files |
|-----|-------|-----------|----------------|
| P0  | 39 lines (`Real P0 = 39`: 28 invariant + 11 conditional) | Invariant assertions (#4a/#4f) and conditional bypass (#5a) | `activation-key-config.spec.ts`, `edge-cases.spec.ts`, `touch-mode.spec.ts`, `context-menu.spec.ts`, `drag-selection.spec.ts`, `api-methods.spec.ts`, and about 10 more |
| P1  | 4 grouped findings (115 sleeps, about 29 #17 calls, 8 `force` clicks, 1 serial) | Hard-coded sleeps | `perf-bench.spec.ts`, `freeze-animations.spec.ts`, `hover-reveal.spec.ts`, and others |
| P2  | 0 confirmed | | |

**Total: 39 P0 lines and 4 grouped P1 findings across about 18 files.** The scan was INCOMPLETE, so this is not a whole-suite verdict.

### Top 3 Priorities
1. **Replace the 28 invariant assertions** (`typeof … === "boolean"`, `toBeDefined()` on `getState()`) with checks of the promised effect, starting with `activation-key-config.spec.ts`.
2. **Assert the guard before the guarded checks** in the 11 conditional-bypass tests, starting with `context-menu.spec.ts:391, 404` and `event-callbacks.spec.ts:231`.
3. **Fix the `./fixtures.js` provenance problem for the scanner** (or pass the right scan flag) and rerun it, so the 238 triage candidates get a complete mechanical pass.

## Coverage Gaps (Suggestions)
1. **[Edge case]** No test breaks the context menu and expects failure. The `position` guard at `context-menu.spec.ts:391` lets a missing menu pass.
2. **[Race]** The `if (count > 0)` at `drag-selection.spec.ts:438` skips the post-scroll drag case when no items are found.
3. **[Edge case]** `event-callbacks.spec.ts:231` never covers the case where `onAfterCopy` is missing from the history.

**Follow-up offer (not executed):** I can run a V2 assertion-sensitivity probe on `activation-key-config.spec.ts › should accept activationKey option`. It would delete the `typeof` assertion and confirm the test still passes. It needs the dev server and checkout trust, takes a few minutes of run time and adds a modest token cost. Say if you want it.