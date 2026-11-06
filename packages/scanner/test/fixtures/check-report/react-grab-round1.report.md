## Review Scope and Evidence
- **Mode:** full mode. Evidence route: complete semantic review (scanner, then Phase 2, with all mandatory sweeps).
- **Behavior under review:** the Playwright suite in `packages/react-grab/e2e` (about 60 specs, fixtures and perf helpers). It covers activation, selection, drag, toolbar, context menu, framework contract checks and perf benchmarks.
- **Diff base/range:** N/A
- **Changed E2E artifacts:** N/A (full mode)
- **Context-only files consulted:** `packages/react-grab/e2e/fixtures.ts` (the `reactGrab` page object, `getState`, `getDragBoxBounds`, `getToolbarInfo`, `waitForCallback` and others). I did not open `playwright.config.ts` or the app source.
- **Static evidence:**
  - **Scanner coverage:** the bundled scanner ran on `packages/react-grab/e2e` and ended `INCOMPLETE` (exit 2). There are 715 unresolved `provenance-unsupported` items because `test` is a custom `base.extend` fixture. I treated that as "not clean" and covered the gap with the Phase 2 sweeps below.
  - **Scanner hits:** 362 total. They break down as 0 confirmed P0, 44 P0 candidates, 124 heuristic P1/P2 and 238 LLM-triage.
  - **Project ESLint:** not run.
  - **Verdict on each of the 44 scanner `[P0?]` lines:**
    - `#5a` confirmed at 19 lines. These are `packages/react-grab/e2e/api-methods.spec.ts:136`, `context-menu.spec.ts:391`, `context-menu.spec.ts:404`, `drag-selection.spec.ts:438`, `drag-selection.spec.ts:476`, `event-callbacks.spec.ts:231`, `focus-trap.spec.ts:140`, `framework/list-keys.spec.ts:74`, `freeze-animations.spec.ts:153`, `overlay-filtering.spec.ts:77`, `selection.spec.ts:228`, `toolbar.spec.ts:286`, `toolbar.spec.ts:469`, `touch-mode.spec.ts:194`, `viewport.spec.ts:131` and `visual-feedback.spec.ts:12`, `:31`, `:47`, `:87`.
    - `#5a` false positive at 19 lines:
      - `packages/react-grab/e2e/activation-edge-cases.spec.ts:206`: both bounds are asserted non-null unconditionally at lines 198 and 205, so the branch is always taken.
      - `packages/react-grab/e2e/visual-feedback.spec.ts:187`, `:207` and `:227`: the guard follows `expect(bounds?.arrow).not.toBeNull()`, so it is always true.
      - `packages/react-grab/e2e/framework-production.spec.ts:33` and `:84`: an unconditional assertion on the same property precedes the branch.
      - `packages/react-grab/e2e/framework-production.spec.ts:101`: the `if` states the exact property under test.
      - `packages/react-grab/e2e/framework/list-keys.spec.ts:16`, `:68` and `:73`: the unconditional `not.toContain('key: "c"')` and the `:69` prerequisite cover them.
      - `packages/react-grab/e2e/framework/owner-semantics.spec.ts:19`, `:26` and `:71`: line 25 is unconditional, and both branches at line 71 assert.
      - `packages/react-grab/e2e/framework/production.spec.ts:51`: when the source map is absent there is nothing to leak, and `blockedMapRequests` is asserted unconditionally.
      - `packages/react-grab/e2e/perf-bench.spec.ts:143`, `perf-heavy.spec.ts:69`, `perf-heavy.spec.ts:97` and `perf-interference.spec.ts:236`: these are env-gated soft perf budgets.
      - `packages/react-grab/e2e/solid-source-location.spec.ts:36`: both branches assert.
    - `#3` false positive at 3 lines:
      - `packages/react-grab/e2e/app-theme-detection.spec.ts:21`: the wait is best-effort, and every test re-reads the attribute and asserts it with `toBe`.
      - `packages/react-grab/e2e/fixtures.ts:662`: this is a best-effort scroll wait, not an assertion.
      - `packages/react-grab/e2e/perf-bench.spec.ts:172`: this is a fire-and-forget load generator.
    - `#4a` false positive at `packages/react-grab/e2e/visual-feedback.spec.ts:188`, `:208` and `:228`. The bounds are layout-dependent and the product can violate them. They sit inside `toPass`, after `not.toBeNull`.
  - **Other triage verdicts:**
    - `#18` at `packages/react-grab/e2e/perf-bench.spec.ts:200-201` is a false positive. The soft assertions are terminal and nothing depends on them.
    - `#4b` at `packages/react-grab/e2e/solid-source-location.spec.ts:14` is a false positive. It is a render gate for an element the next step reads.
    - `#11c`: all 20 skips carry a reason string or a condition, so none are flagged.
    - `analysisTasks`: the `provenance-unsupported` items are resolved as `SOURCE_CONTEXT_ESTABLISHED`. `test`/`expect` come from `fixtures.ts`, which imports `@playwright/test` (`base.extend`, `fixtures.ts:1854`).
  - **Mandatory sweep rows (hits):**

    | Row | Hits |
    |---|---|
    | `#3b` | N/A (Playwright) |
    | `#3` | 70 `catch` lines. All spec-level ones propagate, are best-effort cleanup, or are re-asserted afterwards. |
    | `#5a` | scanner 38; bare-`return` and `if`-then-`expect` sweeps added the lines above. `interference-ui.spec.ts:196` and `keyboard-navigation.spec.ts:191` are false positives. |
    | `#7` | 0 |
    | `#9b` | N/A |
    | `#9c` | 16, all `domcontentloaded` and none `networkidle` |
    | `#19` | 0 |
    | `#10b` | 4. `shift-multi-select.spec.ts:15` is a literal `serial`; the 3 perf files pass a constant mode. |
    | `#10d` | N/A |
    | `#4a` | 141 comparisons. No `count >= 0` shape. |
    | `#4f` | 130; resolved in the findings below. |
    | `#4i` | 0 negative-count or absence hits outside `interference-ui.spec.ts:131` |
    | `#4k` | 0 |
    | `#11c` | 20 |
    | `#10c` | 1 (`hit-test-shield.spec.ts:70`, with `level` and `.first()`). Not flagged. |
    | `#18` | 6 |
    | `#4g`, `#5b` (Cypress), `#10f` | N/A |
    | `#9` | see the `#9` finding |
    | `#17` | 0 |
    | `#8b` | 0 standalone |
    | `#15`, `#16` | no scanner hits; none found |

    `#1`, `#2`, `#12` and `#20–#23`:
    - `#12`: no protected surfaces, so not applicable.
    - `#20–#23`: the suite has no backend writes or `storageState`, and nothing is fulfilled by a stub that is then read back.
    - `#1`/`#2`: I used a script to find any `test(` body with no `expect`. It found one, `freeze-updates.spec.ts:93`. That test fails if the evaluate throws, so it is not flagged.
    - `#13`: no ownership conflicts found in the sampled specs. Not exhaustive.
- **Runtime evidence:** not executed. I recommend running `npx playwright test` in `packages/react-grab`.
- **Independent verification:** V1–V6 recommended/unexecuted. No delegated verifier was used; every finding was checked inline against its fixture source.
- **Limitations/exclusions:**
  - The scanner was INCOMPLETE.
  - The 145 `#6` candidates were only sampled. The ones I read are legitimate shadow-DOM or one-shot DOM snapshot reads.
  - The 16 `#10a` and 9 `#9` non-`Page` candidates were not resolved individually.
  - The `perf-*` files were exempted from the `#1`/`#2` script and the vacuous-assertion greps.
  - I did not open `playwright.config.ts`.

## [P0] packages/react-grab/e2e/visual-feedback.spec.ts — #4f #5a Drag-box and bounds tests that cannot fail

### `drag box should appear during drag` (line 54)
- **Issue:** the only assertion is `expect(dragBounds).toBeDefined()` (`:66`). `getDragBoxBounds` returns `{...} | null` and never `undefined` (`fixtures.ts:1288-1314`), so a missing drag box still passes. The next test (`:110`) uses `toBeNull()` for the same helper, which shows the intended contract.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** assert non-null.
- **Verification:** recommended: V2 mutation (stub the drag box off) should fail it.
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  expect(dragBounds).not.toBeNull();
  ```

### `selection box should match element bounds` (`:12`), `should update when hovering different elements` (`:31`), `should track scrolling element` (`:47`), `drag box should grow with drag distance` (`:87`)
- **Issue:** each test's only assertions sit inside `if (a && b)` on nullable bounds. The false branch has no assertion and no failing action. If the bounds helpers return `null`, for example when the target has zero size or the drag box is hidden, the test passes with nothing checked.
- **Fix:** assert the bounds are non-null (matching `activation-edge-cases.spec.ts:198`) and drop the `if`.
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  expect(elementBounds).not.toBeNull();
  expect(selectionBounds).not.toBeNull();
  expect(Math.abs(selectionBounds!.x - elementBounds!.x)).toBeLessThan(5);
  ```

### `label should show element count for multi-select` (`:155`)
- **Issue:** `expect(state).toBeDefined()` can never fail because `getState` returns a fallback object when the API is missing (`fixtures.ts:1353-1371`). The title promises an element count that nothing checks.
- **Fix:** read the count from `getSelectionLabelInfo()` and assert it. That helper's field names are not in what I read, so I am not proposing code.
- **§4.1 row:** no row (judgement call)

## [P0] State-fallback tests that assert nothing — #4a (packages/react-grab/e2e)
`getState()` falls back to an object with `isActive: false`, and `isOverlayVisible()` ends in `?? false` (`fixtures.ts:252-257`, `fixtures.ts:1353-1371`). Both are always defined and always boolean, whatever the product does, so these assertions are invariant. In most of them nothing else is checked.
- **Issue:**
  - `packages/react-grab/e2e/activation-key-config.spec.ts:11`, `:20`, `:30`, `:40`, `:49`, `:58`, `:70`: "should accept … option" tests assert only `typeof state.isActive === "boolean"`. Nothing checks that the option took effect.
  - `packages/react-grab/e2e/edge-cases.spec.ts:33`, `:59`, `:97`, `:265`: `typeof … === "boolean"`.
  - `packages/react-grab/e2e/edge-cases.spec.ts:125`, `:143`, `:164`: `state` is `toBeDefined`.
  - `packages/react-grab/e2e/activation.spec.ts:163` and `packages/react-grab/e2e/api-methods.spec.ts:78`: `typeof … === "boolean"`.
  - `packages/react-grab/e2e/touch-mode.spec.ts:24`, `:60`, `:219`, `:236`: `state` is `toBeDefined`.
  - `packages/react-grab/e2e/toolbar.spec.ts:607` and `packages/react-grab/e2e/open-file.spec.ts:396`: `typeof … === "boolean"`.
  - `packages/react-grab/e2e/drag-selection.spec.ts:427`: `state` is `toBeDefined`.
  - `packages/react-grab/e2e/theme-customization.spec.ts:87`: `dragBounds` is `toBeDefined`, but the helper returns `null` and never `undefined`. The title is "should show drag box by default".
  - `packages/react-grab/e2e/toolbar.spec.ts:229`: `snapEdge` is `toBeDefined`, but the default is `null` (`fixtures.ts:780-782`). The title is "should snap to edges after drag".
- **Fix:** assert each test's real promise.
  - Option tests: apply the option, then check its effect. For example, with `activationKey: "g"`, `g` activates and the default key does not.
  - Drag-box and toolbar tests: use `not.toBeNull()` plus the expected edge value.
  - Crash-resilience tests: add a `pageerror` listener, as `malformed-events.spec.ts:5` already does, and assert the post-state is correct, for example `isActive === false` after a deactivate.
- **§4.1 row:** no row (judgement call)

## [P0] Conditional assertions that skip silently — #5a
- **Issue:** in each location below, the only verification is inside an `if` on a nullable value, with no unconditional assertion in the false branch:
  - `packages/react-grab/e2e/api-methods.spec.ts:136` (`state.dragBounds`).
  - `packages/react-grab/e2e/context-menu.spec.ts:391` and `:404` (`menuInfo.position`). The tests open the menu but never assert it opened.
  - `packages/react-grab/e2e/drag-selection.spec.ts:438` (`count > 0`) and `:476` (`box`). If the list or the scroll container is missing, the test passes.
  - `packages/react-grab/e2e/event-callbacks.spec.ts:231`. If either callback is missing, the order check is skipped.
  - `packages/react-grab/e2e/focus-trap.spec.ts:140`.
  - `packages/react-grab/e2e/framework/list-keys.spec.ts:74`. A missing key after reorder passes on non-production projects.
  - `packages/react-grab/e2e/freeze-animations.spec.ts:153`. It is gated on `shadowAnimationCountBefore > 0`, which is never asserted, so zero animations passes.
  - `packages/react-grab/e2e/overlay-filtering.spec.ts:77`.
  - `packages/react-grab/e2e/selection.spec.ts:228`.
  - `packages/react-grab/e2e/toolbar.spec.ts:286` and `:469`.
  - `packages/react-grab/e2e/touch-mode.spec.ts:194`. If the box is null, nothing is tapped or asserted.
  - `packages/react-grab/e2e/viewport.spec.ts:131`. If `newBounds` is null, nothing is asserted.
- **Fix:** replace the gate with an unconditional precondition and assert in both outcomes. Do not wrap it in `test.skip`.
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  // packages/react-grab/e2e/context-menu.spec.ts:391
  expect(menuInfo.isVisible).toBe(true);
  expect(menuInfo.position).not.toBeNull();
  expect(menuInfo.position!.y).toBeLessThan(viewport.height);
  ```

## [P1] packages/react-grab/e2e — #9 Hard-coded sleeps
- **Issue:** the scanner confirmed 115 `waitForTimeout` hits. The heaviest files are `perf-bench.spec.ts` (40), `perf-heavy.spec.ts` (28), `perf-interference.spec.ts` (11), `freeze-animations.spec.ts` (9), `interference-ui.spec.ts` (7) and `hover-reveal.spec.ts` (6). Examples are `visual-feedback.spec.ts:24`, `:28` and `:43`.
- **Fix:** wait on state instead. The suite already has helpers such as `hoverUntilSelected`, `waitForSelectionBox` and `expect.poll`. Keep the perf sleeps that pace input on purpose and add `// JUSTIFIED:` to them.
- **§4.1 row:** no row (judgement call)

## [P1] #5b `force: true` without `// JUSTIFIED:`
- **Issue:** `packages/react-grab/e2e/heavy-ui.spec.ts:50` and `:53` (the filter-input clicks), and `packages/react-grab/e2e/perf-bench.spec.ts:317`, `:764`, `:790`, `:876`, `:881` and `:898`. Forced clicks bypass the actionability checks that a real user would hit.
- **Fix:** confirm what blocks the click. If react-grab's overlay is meant to be bypassed, add `// JUSTIFIED:` with that reason. Otherwise drop `force`.
- **§4.1 row:** no row (judgement call)

## [P1] packages/react-grab/e2e/shift-multi-select.spec.ts:15 — #10b Serial mode
- **Issue:** `test.describe.configure({ mode: "serial" })` couples the tests, so one failure skips the rest, and there is no comment explaining why.
- **Fix:** make the tests independent. If they genuinely share state, document that.
- **§4.1 row:** no row (judgement call)

## [P1] packages/react-grab/e2e/interference-ui.spec.ts:131 — #4c-4e One-shot absence count
- **Issue:** `expect(await page.locator("[data-testid='kanban-drag-ghost']").count()).toBe(0)` is a one-shot read with no retry. The selector is only used positively in a different test (`:152`), so a rename would not be caught here.
- **Fix:** use the retrying matcher.
- **§4.1 row:** `#4c-4e` `expect(await x.count()).toBe(N)` → `await expect(x).toHaveCount(N)`
- **Code:**
  ```typescript
  await expect(page.locator("[data-testid='kanban-drag-ghost']")).toHaveCount(0);
  ```

## [P1] #1 Titles promise more than they check
- `packages/react-grab/e2e/context-menu.spec.ts:372`: "should appear near click position" asserts visibility plus `position` `toBeDefined`, which `null` also satisfies. Nothing compares the position to the click.
- `packages/react-grab/e2e/visual-feedback.spec.ts:158`: "label should position below element by default" asserts label visibility and `elementBounds` `toBeDefined`. Nothing checks the "below" placement.
- **Fix:** assert the relation, for example `labelInfo` y is greater than `elementBounds.y + elementBounds.height`. I did not confirm the label geometry field names, so I am not giving code.
- **§4.1 row:** no row (judgement call)

## Review Summary

| Sev | Count | Top Issue | Affected Files |
|-----|-------|-----------|----------------|
| P0 | 46 | Assertions that cannot fail (`#4a`/`#4f`) and silent conditional skips (`#5a`) | about 18 files, including `visual-feedback.spec.ts`, `edge-cases.spec.ts`, `activation-key-config.spec.ts` and `touch-mode.spec.ts` |
| P1 | 127 lines (115 `#9`, 8 `#5b`, 1 `#10b`, 1 `#4c-4e`, 2 `#1`) | Fixed sleeps | `perf-*.spec.ts`, `freeze-animations.spec.ts`, `interference-ui.spec.ts` |
| P2 | 0 | | |

**Real P0 = 46 distinct `file:line` locations.** This counts `#4a`/`#4f` and `#5a` lines after false-positive elimination, based on reading source and not on running the suite. **Total: 173 issues.**

### Top Priorities
1. **Fix the state-fallback and `toBeDefined` tests** (`activation-key-config`, `edge-cases`, `touch-mode`, `activation`, `api-methods`, `toolbar`, `open-file`, `drag-selection`). They pass even when react-grab is missing. Give each a real post-condition.
2. **Remove the `if (bounds…)` gates** in the 19 `#5a` locations, and add an unconditional `not.toBeNull()` first.
3. **Fix the nullable `toBeDefined` checks** (`visual-feedback.spec.ts:66`, `theme-customization.spec.ts:87`, `toolbar.spec.ts:229`). Use `not.toBeNull()` plus the expected value.
4. **Replace non-perf `waitForTimeout` calls** with state waits, and justify or drop the `force: true` clicks.

## Coverage Gaps (Suggestions)
1. **[Edge case]** `packages/react-grab/e2e/freeze-animations.spec.ts:153` is gated on a pre-count that is never asserted. Add a case that guarantees at least one shadow-DOM animation exists before deactivation.
2. **[Race]** `packages/react-grab/e2e/context-menu.spec.ts:391` and `:404` pass without an open menu. Add an assertion that the menu is visible at each edge.
3. **[Error path]** `packages/react-grab/e2e/activation-key-config.spec.ts:11-70` has no negative case. Add one showing the old activation key stops working after `reinitialize`.

## Optional follow-up
I can run a V3 app-fault probe on `drag box should appear during drag` (`packages/react-grab/e2e/visual-feedback.spec.ts:54`). I would disable drag-box rendering and check that the test fails. Right now I expect it to pass. It needs the e2e dev server and Playwright browsers, and would cost extra tokens and several minutes. Nothing has been executed. Say if you want it.