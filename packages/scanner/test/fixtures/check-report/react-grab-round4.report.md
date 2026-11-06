## Review Scope and Evidence
- **Mode:** full mode; evidence route: semantic review (complete)
- **Behavior under review:** the React Grab Playwright suite in `packages/react-grab/e2e` (64 specs plus fixtures and helpers), checked for weak, vacuous or always-passing assertions.
- **Diff base/range:** N/A
- **Changed E2E artifacts:** N/A (full mode)
- **Context-only files consulted:** `packages/react-grab/playwright.config.ts` and `packages/react-grab/e2e/fixtures.ts` (the `reactGrab` page object, with return types for `getState`, `getToolbarInfo`, `getContextMenuInfo`, `getDragBoxBounds`, `getSelectionBoxBounds`, `waitForCallback`).
- **Static evidence:**
  - **Scanner:** the bundled scanner ran on `packages/react-grab/e2e`. The result is **INCOMPLETE** (exit 2): 685 provenance-unsupported diagnostics, because `test` and `reactGrab` come from a custom `base.extend` fixture. The scanner therefore never saw the helper-based assertions. Its summary is 362 hits, 0 confirmed P0, 44 P0 candidates and 30 unresolved analysis tasks. I did not use it as clearance. Project ESLint was not executed.
  - **Sweeps:** I ran every row of the bounded opening-token sweep.

    | Row | Result |
    |---|---|
    | #3b | 0 |
    | #3 | 7 in spec/fixture files |
    | #7 | 0 |
    | #9b | N/A (Playwright) |
    | #9c | 10 `waitForLoadState`, all `domcontentloaded`, so no hit |
    | #19 | 0 |
    | #10b | 1 |
    | #10d | N/A |
    | #4a | 3 `>=0` sites, all false positives |
    | #4f | sweep done; confirmed hits are in the findings |
    | #4i | 0 Locator absence assertions in non-perf specs, 1 one-shot count (P1 below) |
    | #4k | 0 |
    | #11c | 20, all with a reason or condition |
    | #10c | 1 (`getByRole` heading, page-scoped, static surface), skip |
    | #18 | 6 (4 perf env-gated, 2 perf-bench false positives) |
    | #4g | N/A |
    | #5b | 16 |
    | #9 | 372 non-perf `waitForTimeout` |
    | #10f | N/A |
    | #17 | 33 |
    | #8b | 0 |
    | #15 | 0 |
    | #16 | 0 real, 10 inside `evaluate` (DOM elements, not Locators) |

  - **#1/#2:** a mechanical zero-`expect` pass covered 64/64 spec files and found one test, which is the P1 finding below. I read the assertions in about 25 specs by hand, so this is sampled, not exhaustive.
  - **#12, #21, #22:** N/A. There is no auth, no `storageState` and no backend write path in these specs.
  - **#13:** no confirmed raw-versus-page-object equivalence. The raw mid-drag mouse sequences need state the `dragSelect` helper hides.
  - **#20 and #23:** not applicable to a local fixture app, and not traced beyond that.
  - **Every #5a candidate:**

    | Candidate | Verdict |
    |---|---|
    | `activation-edge-cases.spec.ts:206` | FALSE-POSITIVE, lines 198 and 205 assert non-null unconditionally |
    | `framework-production.spec.ts:33` | FALSE-POSITIVE, line 20 (`expectActionableContext`) asserts the same unconditionally |
    | `framework-production.spec.ts:84` | FALSE-POSITIVE, line 83 is unconditional |
    | `framework-production.spec.ts:101` | CONFIRMED, below |
    | `framework/list-keys.spec.ts:16` | FALSE-POSITIVE, line 15 is unconditional and the gate is project-based |
    | `framework/list-keys.spec.ts:68` | FALSE-POSITIVE, it is a project-gated precondition |
    | `framework/list-keys.spec.ts:73` | FALSE-POSITIVE, line 69 proves the key is non-null for dev projects |
    | `framework/list-keys.spec.ts:74` | CONFIRMED |
    | `framework/owner-semantics.spec.ts:19` | FALSE-POSITIVE, line 25 is unconditional |
    | `framework/owner-semantics.spec.ts:26` | FALSE-POSITIVE, line 25 is unconditional |
    | `framework/owner-semantics.spec.ts:71` | FALSE-POSITIVE, both branches assert |
    | `framework/production.spec.ts:51` | FALSE-POSITIVE, lines 56 and 57 are unconditional |
    | `solid-source-location.spec.ts:36` | FALSE-POSITIVE, both branches assert |
    | `perf-bench.spec.ts:143` | FALSE-POSITIVE, the gate is documented as intentional and the metric is recorded |
    | `perf-heavy.spec.ts:69` | FALSE-POSITIVE, documented env-gated guardrail |
    | `perf-heavy.spec.ts:97` | FALSE-POSITIVE, documented env-gated guardrail |
    | `perf-interference.spec.ts:236` | FALSE-POSITIVE, documented env-gated guardrail |

    The other 20 candidates are confirmed in the P0 finding below.
  - **Other candidates:**

    | Candidate | Verdict |
    |---|---|
    | #3 at `app-theme-detection.spec.ts:21` | FALSE-POSITIVE, the attribute read after the catch is asserted later |
    | #3 at `fixtures.ts:662` | FALSE-POSITIVE, best-effort wait, later bounds assertions depend on the scroll |
    | #3 at `perf-bench.spec.ts:172` | FALSE-POSITIVE, cleanup that nothing depends on |
    | #4a at `visual-feedback.spec.ts:188`, `:208`, `:228` | FALSE-POSITIVE, a label x of 0 or less can fail |
    | #4b at `solid-source-location.spec.ts:14` | FALSE-POSITIVE, readiness gate before real assertions |
    | #18 at `perf-bench.spec.ts:200`, `:201` | FALSE-POSITIVE, soft assertion with no dependent work, and 0 is a real sentinel |
    | #11c | FALSE-POSITIVE, every site has a reason or condition |
    | #4c-4e at `interference-ui.spec.ts:131` | CONFIRMED, below |

  - **Not individually triaged (NEEDS-CONTEXT):** the #6 candidates (145 hits), #10a (16) and the 9 #9 candidates in helper files.
  - **Analysis tasks:** I did not give the 30 `review.analysisTasks` individual dispositions.
- **Runtime evidence:** not executed. I recommend running the suite, per project, for the "Verification" lines below.
- **Independent verification:** all findings were verified inline against source and helper return types. No delegated verifier was used. V2/V3 probes are recommended but unexecuted (see the end).
- **Limitations/exclusions:**
  - The scan is INCOMPLETE, as above.
  - The `perf-*.spec.ts` and `perf-*.ts` benchmarks (`@perf`) were not reviewed for #1/#2, because their INP gating is documented as intentional.
  - `react-grab.expect.ts` and the coverage files were not reviewed beyond the sweeps.
  - `/tmp/e2erev` already held other files from earlier runs. I did not read or modify them. My scratch outputs are `/tmp/e2erev/report1.txt` and the empty `/tmp/e2erev-mine.mzkOrF`.

**Real P0 = 47** distinct lines: 15 in the first finding, 12 in the second and 20 in the third.

## [P0] packages/react-grab/e2e/*.spec.ts — #4a `typeof x === "boolean"` on a value that is boolean by construction
`isOverlayVisible` returns `api?.isActive() ?? false`, and `getState`, `isToolbarVisible` and the `?? false` evaluate in `open-file` all fall back to booleans. `expect(typeof …).toBe("boolean")` therefore cannot fail, whatever the app does.

Sites:
- `packages/react-grab/e2e/activation-key-config.spec.ts:11`, `:20`, `:30`, `:40`, `:49`, `:58`, `:70`
- `packages/react-grab/e2e/edge-cases.spec.ts:33`, `:59`, `:97`, `:265`
- `packages/react-grab/e2e/api-methods.spec.ts:78`, `:121`
- `packages/react-grab/e2e/toolbar.spec.ts:607`
- `packages/react-grab/e2e/open-file.spec.ts:396`

### `should accept activationKey option` (and the other 14 tests above)
- **Issue:** each test promises an outcome, such as an accepted option, a consistent state after rapid toggles, or the toolbar surviving a small viewport. The only assertion is the type check. A reinitialize that ignores `activationKey` still passes.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** assert the promised effect, for example that the new key activates the overlay and the old one doesn't.
- **Verification:** V2 recommended (not run); a mutation that changes the option should survive today.
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  await reactGrab.reinitialize({ activationKey: "g" });
  await reactGrab.page.keyboard.press("g");
  await expect.poll(() => reactGrab.isOverlayVisible()).toBe(true);
  ```

## [P0] packages/react-grab/e2e/*.spec.ts — #4f + #1 `toBeDefined()` on a value that is always defined
`getState()` returns a fallback object. `getDragBoxBounds()`, `getToolbarInfo().snapEdge` and `getContextMenuInfo().position` are typed `T | null`, and `null` is "defined", so these assertions cannot fail.

Sites:
- `packages/react-grab/e2e/visual-feedback.spec.ts:66` (drag box should appear during drag)
- `packages/react-grab/e2e/visual-feedback.spec.ts:155` (label should show element count for multi-select; no count is checked)
- `packages/react-grab/e2e/drag-selection.spec.ts:427`
- `packages/react-grab/e2e/edge-cases.spec.ts:125`, `:143`, `:164`
- `packages/react-grab/e2e/touch-mode.spec.ts:24`, `:60`, `:219`, `:236`
- `packages/react-grab/e2e/theme-customization.spec.ts:87` (drag box shown by default)
- `packages/react-grab/e2e/toolbar.spec.ts:229` (snaps to edges after drag)

### `label should show element count for multi-select` (representative of the 12 lines above)
- **Issue:** each test's only assertion passes whether or not the promised UI appears.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** assert the concrete value. Use `not.toBeNull()` for drag bounds, and a non-null `snapEdge` (or the expected edge) for the toolbar.
- **Verification:** V2 recommended (not run).
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  const dragBounds = await reactGrab.getDragBoxBounds();
  expect(dragBounds).not.toBeNull();
  ```

## [P0] packages/react-grab/e2e/*.spec.ts — #5a Assertion gated by a data-dependent `if`
In each case the only load-bearing assertion sits inside an `if` on a nullable read. When the value is null the test finishes with no check of the promised outcome. Some of these reads, such as `getSelectionBoxBounds`, return null on zero-size or hidden boxes.

Sites (20):
- `packages/react-grab/e2e/visual-feedback.spec.ts:12`, `:31`, `:47`, `:87`
- `packages/react-grab/e2e/event-callbacks.spec.ts:231` (order test, silent if either callback is missing)
- `packages/react-grab/e2e/viewport.spec.ts:131` (only `initialBounds` is asserted non-null, not `newBounds`)
- `packages/react-grab/e2e/overlay-filtering.spec.ts:77` (title says the underlying element is selected, but the only check is `isActive`, which activation already makes true)
- `packages/react-grab/e2e/api-methods.spec.ts:136`
- `packages/react-grab/e2e/context-menu.spec.ts:391`, `:404`
- `packages/react-grab/e2e/toolbar.spec.ts:286`, `:469`
- `packages/react-grab/e2e/touch-mode.spec.ts:194` (a null `boundingBox` skips the tap and the assertion)
- `packages/react-grab/e2e/selection.spec.ts:228`
- `packages/react-grab/e2e/focus-trap.spec.ts:140`
- `packages/react-grab/e2e/freeze-animations.spec.ts:153` (no shadow animations before means no check)
- `packages/react-grab/e2e/drag-selection.spec.ts:438`, `:476`
- `packages/react-grab/e2e/framework-production.spec.ts:101` (the test's only assertion is conditional)
- `packages/react-grab/e2e/framework/list-keys.spec.ts:74` (a key lost after reorder passes on dev projects)

### `copy callbacks should fire in correct order` (representative)
- **Issue:** the ordering assertion is skipped when `onBeforeCopy` or `onAfterCopy` never fired. A regression that drops either callback passes. `copy callbacks should fire` at `:216` covers other tests only.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** assert both indices exist, then the ordering. Do the same for each site: replace the `if` with a hard non-null assertion on the value it tests.
- **Verification:** V2 recommended (not run).
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  expect(beforeIndex).not.toBe(-1);
  expect(afterIndex).not.toBe(-1);
  expect(beforeIndex).toBeLessThan(afterIndex);
  ```

## [P1] packages/react-grab/e2e/interference-ui.spec.ts:131 — #4c-4e + #4i One-shot absence count on an unproven selector
### `detection survives pointer-capture drag` (line 131)
- **Issue:** `expect(await page.locator("[data-testid='kanban-drag-ghost']").count()).toBe(0)` reads once, and it passes if the selector is wrong. The selector is asserted present only in a sibling test (`:152`), which does not count as proof.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** use a retrying web-first assertion, and add a positive check inside the test (for example the drag-ghost start state) so the absence has meaning.
- **Verification:** V2 recommended (not run).
- **§4.1 row:** `#4c-4e` `expect(await x.count()).toBe(N)` → `await expect(x).toHaveCount(N)` (Auto-retry until count settles).
- **Code:**
  ```typescript
  await expect(page.locator("[data-testid='kanban-drag-ghost']")).toHaveCount(0);
  ```

## [P1] packages/react-grab/e2e/visual-feedback.spec.ts:158, packages/react-grab/e2e/context-menu.spec.ts:372 — #1 Title promise not verified
### `label should position below element by default` and `context menu should appear near click position`
- **Issue:** the tests verify visibility only. The "below the element" and "near click position" promises are not checked: `:166` is `expect(elementBounds).toBeDefined()` and `:380` is `expect(menuInfo.position).toBeDefined()`, and both always pass.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** compare the label's y against the element's bottom, and the menu position against the click point.
- **Verification:** V2 recommended (not run).
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  expect(labelBounds.y).toBeGreaterThanOrEqual(elementBounds.y + elementBounds.height);
  ```

## [P1] packages/react-grab/e2e/freeze-updates.spec.ts:93 — #2 No assertion
### `ignores malformed renderer registrations`
- **Issue:** the only failure source is an exception inside `page.evaluate`. Console or page errors from `freezeReactGrab` are not captured, as `malformed-events.spec.ts` does with `errors`.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** collect `pageerror` events and assert there are none, and assert that freeze state is unchanged.
- **Verification:** V3 recommended (not run).
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  const errors: string[] = [];
  reactGrab.page.on("pageerror", (e) => errors.push(e.message));
  // ... existing evaluate ...
  expect(errors).toEqual([]);
  ```

## [P1] packages/react-grab/e2e/fixtures.ts:325 + others — #5b `force: true` without a `// JUSTIFIED:` marker
Sites: `fixtures.ts:325`, `:332`, `:529`, `heavy-ui.spec.ts:50`, `:53`, `keyboard-navigation.spec.ts:420`, `:423`, `iframe.spec.ts:27`, `:132`, `:133`, `context-menu.spec.ts:44`, `copy-failure.spec.ts:228`, and the perf-bench sites.
- **Issue:** the overlay shield likely intercepts pointer events, which would explain `force`. But no site documents why, so a real hit-testing regression can be bypassed. This is a SUGGEST item, not an auto-fix.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** add a `// JUSTIFIED: <shield intercepts pointer events>` marker, and in `fixtures.ts` limit `force` to when the overlay is active.
- **Verification:** N/A
- **§4.1 row:** no row (judgement call)

## [P1] packages/react-grab/e2e/shift-multi-select.spec.ts:15 — #10b Serial describe
- **Issue:** `test.describe.configure({ mode: "serial" })` couples the tests, so one failure skips the rest and hides independent regressions.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** remove it and make each test independent.
- **Verification:** N/A
- **§4.1 row:** no row (judgement call)

## [P1] packages/react-grab/e2e/*.spec.ts — #17 Selector-based Page API calls, #9 fixed sleeps
The #17 and #9 hits are rolled up under Systemic Issues, not enumerated.

## Systemic Issues
- **Hard-coded sleeps:** the scanner confirmed 115 `waitForTimeout` hits (#9). My sweep counted 372 across non-perf specs and fixtures, including `fixtures.ts:326` (`hoverElement` waits 350 ms). Replace them with state waits such as `waitForActive` or `expect.poll`.
- **Selector-based Page APIs (#17):** 33 non-perf hits use `reactGrab.page.click(selector)`, `.fill` or `waitForSelector` (for example `freeze-updates.spec.ts:84`, `activation.spec.ts:110`, `fixtures.ts:271`). Use Locator actions. The scanner missed these because `reactGrab.page` isn't a proven `Page`.
- **Fixture-wrapped assertion style:** most assertions go through `reactGrab` helpers that return `boolean | null`. This is what hides the three P0 shapes from the scanner. Consider `expect.poll(...).toBe()` on helper results throughout.

## Review Summary

| Sev | Count | Top Issue | Affected Files |
|-----|-------|-----------|----------------|
| P0 | 47 lines | Vacuous `typeof`/`toBeDefined` (27), conditional bypass (20) | `visual-feedback`, `edge-cases`, `touch-mode`, `activation-key-config`, `toolbar`, `api-methods`, `event-callbacks`, `viewport`, `context-menu`, `drag-selection`, `selection`, `focus-trap`, `freeze-animations`, `overlay-filtering`, `theme-customization`, `open-file`, `framework-production`, `framework/list-keys` |
| P1 | 5 findings | One-shot absence, unproven title promise, no assertion, `force:true`, serial describe | `interference-ui`, `visual-feedback`, `context-menu`, `freeze-updates`, `fixtures`, `heavy-ui`, `shift-multi-select` |
| P2 | 0 | | |

**Total: 47 P0 lines and 5 P1 findings, plus 2 systemic issues, across 21 files.**

### Top Priorities
1. Replace the 15 `typeof … "boolean"` assertions with checks of the promised effect, starting with `activation-key-config.spec.ts`, where all 7 tests assert nothing real.
2. Replace the 12 `toBeDefined()` assertions on nullable or always-defined values with concrete checks. The drag-box and snap-edge tests currently cannot fail.
3. Turn the 20 `if (a && b) { expect… }` gates into hard assertions on the nullable values first.
4. Fix `interference-ui.spec.ts:131` with `toHaveCount(0)` plus a positive check, and add error capture to `freeze-updates.spec.ts:93`.
5. Document or remove the unmarked `force: true` calls, starting with `fixtures.ts`.

## Coverage Gaps (Suggestions)
1. **[Edge case]** `event-callbacks.spec.ts:231` skips the ordering check when a callback is missing. Add a test where `onAfterCopy` must fire after a forced copy failure.
2. **[Error path]** `activation-key-config.spec.ts` never checks that an invalid or conflicting `activationKey` is rejected. Every test passes today whatever the option does.
3. **[Responsive / device]** `touch-mode.spec.ts:194` silently skips the tap when `boundingBox` is null. Add a case with a failing tap that must produce no clipboard write.

I can run an optional V2 assertion-mutation probe on `activation-key-config.spec.ts:5` ("should accept activationKey option"). It would mutate `activationKey` in `reinitialize` and check whether the test notices. That costs a Playwright run, roughly one browser session plus the dev server on port 5175, and needs your explicit approval of the exact command and a trusted checkout. Nothing has been executed. Do you want that probe?