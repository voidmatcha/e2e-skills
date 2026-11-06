## Review Scope and Evidence
- **Mode:** full mode; evidence route: semantic review (broad review).
- **Behavior under review:** the two Playwright suites. `platform/wab/playwright` has 77 specs plus models, utils and fixtures. `platform/loader-tests/src/playwright-tests` has 66 files.
- **Diff base/range:** N/A
- **Changed E2E artifacts:** none (full mode).
- **Context-only files consulted:** `platform/wab/playwright/playwright.config.ts`, `platform/wab/playwright/fixtures/test.ts`, `platform/wab/playwright/models/studio-model.ts`, `platform/wab/playwright/utils/*`, and loader helpers.
- **Static evidence:**
  - **Scanner:** bundled `scan.sh` ran once per root and ended `INCOMPLETE` on both (coverage BOUNDED). It found 0 confirmed P0.
    - `platform/wab/playwright`: 680 hits, 78 P0 candidates. Its 155 unresolved analysis tasks, mostly `provenance-unsupported`, trace back to the `base.extend` fixtures; I did not disposition them task by task.
    - `platform/loader-tests`: 28 hits, 20 P0 candidates. One unresolved task is `analysis-unknown` at `platform/loader-tests/src/playwright-tests/auth-test-utils.ts:125`, which I did not read, plus 44 more diagnostics.
    - Project ESLint did not run.
  - **Bounded sweeps:**
    - **N/A (Playwright):** #3b, #9b, #10d, #4g, #5b-Cypress, #10f.
    - **Zero hits:** #7 `.only` 0, #18 `expect.soft` 0, #19 `var` 0.
    - **Hits, all reviewed:**
      - #3: 10 bare `catch` blocks, all retry/fallback or best-effort.
      - #9c: 7 `waitUntil:` hits, all `domcontentloaded`.
      - #10b: 2, `describe.configure` with literals.
      - #11c: 9, 2 bare skips.
      - #4k: 2, both guarded.
      - #4a: 10, all legitimate bounds.
      - #4f: about 40, one finding.
      - #19 col-0 `let`: 6.
      - #17: 0 renamed `page`.
      - #8b: 10, all `custom-auth` (a skipped file) or `.catch(() => false)` probes.
    - **Hits, partly read:** #4i 201 lines, #5a (one-line `if (...) return` found nothing; I did not read every other `if`), #10c `getByRole` (counted, collision analysis not done).
    - **#15/#16:** 0 unawaited statements. Hits were inside `Promise.all` at `platform/wab/playwright/e2e/variants.spec.ts:296` and `platform/wab/playwright/e2e/signup.spec.ts:120`.
    - **#9:** only `setTimeout` in `platform/loader-tests/src/playwright-tests/playwright-utils.ts:37`.
  - **Per-line P0 candidate verdicts** (all paths below are under `platform/wab/playwright/` unless noted):
    - **#3, hidden-wait with `.catch(() => {})` (best-effort, no assertion swallowed), all FALSE-POSITIVE:**
      - `e2e/antd5/pagination.spec.ts`: lines 75, 96, 114, 133, 158, 201, 244, 287, 380
      - `e2e/antd5/segmented.spec.ts`: lines 102, 286
      - `e2e/arbitrary-css-selectors.spec.ts:86`
      - `e2e/hostless-antd.spec.ts`: lines 41, 59
      - `e2e/hostless-antd5.spec.ts`: lines 41, 59
      - `e2e/hostless-tiptap.spec.ts:58`
      - `e2e/hostless-rich-layout.spec.ts:165`
      - `models/studio-model.ts`: lines 564, 875, 897
      - `e2e/imported-token-overrides.spec.ts`: lines 212, 270
    - **#3, hidden-wait with an Escape fallback, FALSE-POSITIVE:** `e2e/hostless-rich-calendar.spec.ts` lines 242 and 328, and `e2e/hostless-rich-table.spec.ts:139`.
    - **#3, `isVisible().catch(() => false)` used as a one-shot probe to gate an optional click, FALSE-POSITIVE:**
      - `e2e/data-rep.spec.ts`: lines 64, 76, 86, 110, 124, 137
      - `e2e/forms/dynamic-initial-value.spec.ts:196`
      - `e2e/imported-token-overrides.spec.ts`: lines 113, 142
      - `models/components/right-panel.ts`: lines 390, 552
      - `models/studio-model.ts`: lines 605, 669, 846, 861, 882, 887
      - `utils/import-utils.ts`: lines 13, 64, 110
      - `utils/studio-utils.ts:25`
    - **#3, other FALSE-POSITIVE:**
      - `e2e/copilot-chat.spec.ts:149`: `route.abort().catch` is cleanup.
      - `e2e/routing-branches.spec.ts:38`: inside an `expect.poll` callback.
      - `models/components/right-panel.ts:893`: a request probe that returns false and is polled.
      - `utils/studio-utils.ts:121`: returns null to the caller.
      - `platform/loader-tests/src/playwright-tests/playwright-utils.ts` lines 72 and 113: browser-side font/image preload inside `page.evaluate`.
    - **#5a, FALSE-POSITIVE (the false branch still has an unconditional assertion or action, or the condition is an option or parameter):**
      - `e2e/data-tokens.spec.ts:434`: an optional edit step, with unconditional assertions around it.
      - `e2e/hostless-tiptap.spec.ts:201`: unconditional text assertions at 195–198 carry the outcome.
      - `e2e/imported-token-overrides.spec.ts` lines 1716 and 1718: sampled call sites at 768–806 always pass a defined frame.
      - `e2e/page-links.spec.ts:121`: data-driven.
      - `e2e/plexus-installation.spec.ts:102`: a pre-action state check.
      - `models/components/left-panel.ts:149`: option flag.
      - `models/studio-model.ts:1153`: option flag.
      - `utils/auto-open-utils.ts`: lines 125, 136 (optional parameter, core assertion unconditional), then 176, 181, 193, 198, 210, 215, 324, 384, 534, 592, 608, 710, 715 (every branch asserts).
      - `utils/studio-utils.ts:164`: every branch asserts.
      - `utils/studio-utils.ts:198`: the `Select` value check is skipped, with a comment stating that intent.
      - `platform/loader-tests/src/playwright-tests/nextjs/nextjs-plasmic-react-aria.spec.ts` lines 1104, 1118, 1129, 1144, 1231, 1241, 1251, 1261, 1271, 1281, 1291, 1301, 1311, 1321: config-driven, and both arms assert.
      - `platform/loader-tests/src/playwright-tests/nextjs/shared/cms-test.ts` lines 22 and 41: option flags, with unconditional assertions.
    - **Confirmed findings:** `platform/loader-tests/src/playwright-tests/helpers/website.ts:66` (#5a), `platform/loader-tests/src/playwright-tests/nextjs/vanilla-cookieconsent.spec.ts:187` (#4f), and `platform/wab/playwright/e2e/hostless-tiptap.spec.ts:112,117` (#5a, reported with the #1 at line 102).
    - **Other candidate groups dismissed:**
      - #4b at `platform/wab/playwright/e2e/plasmic-hosting.spec.ts` lines 33 and 34 (DNS records appear after the input) and `platform/wab/playwright/utils/auto-open-utils.ts` lines 622, 638, 659 (rendered state under test).
      - #4i at `platform/wab/playwright/e2e/copilot-chat.spec.ts` lines 107, 115, 133, 134, 161, 171, 180, 184 and 264, each paired with a positive use of the same locator (all but 264) or a positive assertion of the intended state (264).
      - #4k at `platform/loader-tests/src/playwright-tests/nextjs/nextjs-app-components.spec.ts:71`, guarded by `toHaveCount(2)`.
      - #10a: no evidence of ambiguous matches.
      - #6 at `platform/loader-tests/src/playwright-tests/playwright-utils.ts` lines 59 and 177 is browser-side logic.
  - **Coverage:**
    - #1: sampled 12/143 files. I scanned all 77 wab titles and read the bodies of about 12.
    - #2: sampled 12/143.
    - #12: 3/143. No `storageState` file; login goes through `apiClient` or `models.auth`; no wrong-surface pass found.
    - #13: sampled 6/143.
    - #20: sampled 8/143. Backend is a local dev server (`WAB_HOST` defaults to `localhost:3003`) and no shared-state evidence was found.
    - #21: 143/143. No file-backed `storageState`.
    - #22: sampled 8/143.
    - #23: sampled 4/143.
- **Runtime evidence:** not executed. Running both suites needs a Plasmic dev server and browsers, so I did not start them.
- **Independent verification:** each finding was refuted against its source inline; no delegated verifier was used. V2/V3 are recommended but unexecuted (see the end).
- **Limitations/exclusions:** the scan is `INCOMPLETE`, so there is no clean-scan claim. Four unread-in-full areas remain: the `provenance-unsupported` tasks, #1/#2/#13/#22/#23 only sampled, #10c collision analysis not done, and `auth-test-utils.ts:125`. Scratch report files from an earlier run already existed at the paths I first tried, so I wrote to new paths and did not read them.

## [P0] platform/loader-tests/src/playwright-tests/helpers/website.ts:66 — #5a Conditional assertion bypass
### `testWebsiteComponents` (called by "should render components" in the cra, gatsby and nextjs website specs)
- **Issue:** if `/components` returns 404, the test asserts `404 === 404` and returns. A removed or broken page therefore passes. Nothing documents 404 as expected, and the other two website helpers always assert content.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** skip visibly instead of passing, using `test.skip(reason)`, the documented fix for #5a. The requirement is unsourced: if every host must serve `/components`, assert a 200 instead.
- **Verification:** recommended: run against a host with no `/components` route and confirm it now reports skipped, not passed.
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  import { expect, Page, test } from "@playwright/test";
  // ...
  const response = await page.goto(`${ctx.host}/components`);
  test.skip(response?.status() === 404, "/components is not served by this host");
  ```

## [P0] platform/wab/playwright/e2e/hostless-tiptap.spec.ts:102 — #1 #5a Name-assertion gap with conditional assertions
### `has no extensions added by default`
- **Issue:** the title promises "no extensions", but no assertion covers extensions. The only checks are `body` visible and two element-visible checks gated on `count() > 0` (lines 112 and 117, one-shot reads). If the tiptap element never renders, the test passes.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** make the visibility checks unconditional, and add an assertion for the "no extensions" outcome. Only the author knows what is observable for that, so I did not invent one.
- **Verification:** recommended: remove the tiptap component from the project and confirm the test now fails.
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  await expect(liveFrame.locator("div.tiptap")).toBeVisible();
  await expect(liveFrame.locator("#tiptap-state-text")).toBeVisible();
  ```
  This assumes both elements always render in live mode, which I did not confirm.

## [P0] platform/wab/playwright/e2e/publish.spec.ts:20 — #1 Name-assertion mismatch
### `allows external users to see other projects in read mode.`
- **Issue:** the body (lines 20–96) is a single-user flow: publish, preview, revert, reload. No second user or read-only mode appears. A regression in external read access would not fail it. Read access is covered separately in `platform/wab/playwright/e2e/project-access.spec.ts`.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** rename the test to what it verifies.
- **Verification:** N/A
- **§4.1 row:** no row (judgement call)
- **Code:**
  ```typescript
  test("publishes versions, previews them and reverts to an earlier one", async ({
  ```

## [P0] platform/loader-tests/src/playwright-tests/nextjs/vanilla-cookieconsent.spec.ts:187 — #4f #4i #9 Vacuous Locator assertion
### `No modal appears when autoShow is false`
- **Issue:** `expect(locator).toBeDefined()` always passes, because a Locator object is always defined. The only real check is `.cm-wrapper .cm` not visible (line 194), after a fixed 2s sleep (line 190). That absence check passes if the page fails to load or the selector rots. Only sibling tests prove the selector.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** replace line 187 with a real positive assertion, so the absence check is meaningful.
- **Verification:** recommended: change `.cm-wrapper .cm` and confirm this test now fails.
- **§4.1 row:** `#4f` `expect(page.getByText(...)).toBeTruthy()` → `await expect(page.getByText(...)).toBeVisible()`. "If hidden-but-attached is the intended contract, use `await expect(...).toBeAttached()` instead."
- **Code:**
  ```typescript
  await expect(page.locator("#plasmic-cookie-consent")).toBeAttached();
  ```
  I used `toBeAttached` because the original line implies the container exists, not that it is visible; `#plasmic-cookie-consent` is not asserted anywhere else in this file, so confirm it first.

## [P1] platform/wab/playwright — #9 Hard-coded sleeps
- **Issue:** the scanner confirmed 543 sleeps plus 25 more candidates in `platform/wab/playwright`, mostly `page.waitForTimeout`. The heaviest files are `e2e/registered-variants.spec.ts` (53), `e2e/imported-token-overrides.spec.ts` (49), `e2e/hostless-cms.spec.ts` (28), `e2e/hostless-react-slick-slider-carousel.spec.ts` (27) and `e2e/right-panel.spec.ts` (26). Helpers `utils/auto-open-utils.ts`, `utils/import-utils.ts` and `models/studio-model.ts` repeat the pattern.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** replace each sleep with a web-first wait on the state it stands in for. Most have an obvious `waitFor` or `expect` target nearby.
- **Verification:** N/A
- **§4.1 row:** no row (judgement call)

## [P1] platform/wab/playwright/e2e/comments.spec.ts:94 — #4h One-shot URL read
### `should open, close thread dialog, update url and arenas for comment` and the deleted-subject test
- **Issue:** `expect(page.url()).toContain(...)` reads the URL once (lines 94, 114, 191). The `arena=` part can still be settling when it runs.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** use the retrying form.
- **Verification:** recommended: run `comments.spec.ts` repeatedly in CI.
- **§4.1 row:** `#4h` `expect(page.url()).toContain(x)` (substring) → `await expect.poll(() => page.url()).toContain(x)`
- **Code:**
  ```typescript
  await expect
    .poll(() => page.url())
    .toContain(`/-/${componentName}?arena_type=component&arena=${componentUuid}&comment=${threadIdValue}`);
  ```

## [P1] platform/wab/playwright/e2e/hostless-cms.spec.ts:69 — #5b Unjustified `force: true`
- **Issue:** `page.locator("text=Save").click({ force: true })` has no `// JUSTIFIED:` marker. It bypasses actionability, and the next assertion (`Saved!`) only checks the outcome.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** suggest only, no auto-fix. Find the real blocker first and remove `force` only if the test still passes without it. I did not read the §4.2 pre-removal procedure, so none of that was done here.
- **Verification:** recommended: run without `force`.
- **§4.1 row:** no row (judgement call)

## [P1] platform/wab/playwright/e2e/hostless-rich-layout.spec.ts:6 — #19 Module-level mutable state
- **Issue:** `let isWithinLiveFrame = false` is set to true at line 313 and never reset. `models`, `liveFrame` and `canvasFrame` are also shared module state. It is low-impact today, since the file has one test, but a second test in the same worker would inherit the state.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** move these into the test or a `beforeEach` closure.
- **Verification:** N/A
- **§4.1 row:** no row (judgement call)

## [P1] platform/wab/playwright/fixtures/test.ts:61 — #14 Hard-coded credentials
- **Issue:** login uses literal credentials in the `apiClient` fixture (`user2@example.com` / `!53kr3tz!`). The same literals appear in `platform/wab/playwright/e2e/auth.spec.ts:12`, `platform/wab/playwright/e2e/project-access.spec.ts` (lines 12, 28, 50, 66), `platform/wab/playwright/e2e/signup.spec.ts:35`, and in `removeProjectAfterTest` calls across many specs. `platform/loader-tests/src/playwright-tests/nextjs/nextjs-plasmic-auth.spec.ts` (lines 36, 37, 104, 105) has the same issue. These look like seeded dev-user credentials, but they are still duplicated literals.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** read them from one env-backed constant, defaulting to the seed values.
- **Verification:** N/A
- **§4.1 row:** no row (judgement call)

## [P1] platform/wab/playwright/e2e/ui-config-hostless.spec.ts:66 — #4i Unproven absence
### `plume whitelist entry gates installables`
- **Issue:** `toHaveCount(0)` on `li[data-plasmic-add-item-name="Plasmic Design System"]` passes if the selector rots. The positive proof of that selector is in the sibling test (line 46), which does not count. The test's other positive check is a different item.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** assert the locator is present before the plume gate is applied, as the first test does.
- **Verification:** recommended: change the item name in the selector and confirm the test fails.
- **§4.1 row:** no row (judgement call)

## [P1] platform/wab/playwright/e2e/copilot-chat.spec.ts:185 — #4i Unproven absence
### `stops a queued send or an in-flight response`
- **Issue:** `expect(page.getByRole("alert")).toBeHidden()` has no positive counterpart for the alert locator. It passes if errors surface with a different role.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** assert the specific error element for the failure path in a paired case, or scope the locator to a known error container.
- **Verification:** recommended: make the stop path surface an error and confirm this fails.
- **§4.1 row:** no row (judgement call)

## [P2] platform/loader-tests/src/playwright-tests/nextjs/nextjs-app-components.spec.ts:31 — #11c Bare skip
- **Issue:** `test.skip("it works", ...)` has no reason or comment. `platform/loader-tests/src/playwright-tests/nextjs/nextjs-custom-auth.spec.ts:6` skips the whole `PlasmicRootProvider Auth` block the same way, and its `isVisible` assertions (#4c) are dead code while it is skipped.
- **Attribution (diff mode):** N/A in full mode
- **Fix:** add a reason string or a comment saying why coverage was dropped.
- **Verification:** N/A
- **§4.1 row:** no row (judgement call)

## Review Summary

| Sev | Count | Top Issue | Affected Files |
|-----|-------|-----------|----------------|
| P0 | 4 (Real P0 = 4 distinct lines) | 404 passes the components test | `helpers/website.ts`, `hostless-tiptap.spec.ts`, `publish.spec.ts`, `vanilla-cookieconsent.spec.ts` |
| P1 | 7 | 568 hard-coded sleeps in wab | `platform/wab/playwright` (wab suite-wide), `comments.spec.ts`, `hostless-cms.spec.ts`, `hostless-rich-layout.spec.ts`, `fixtures/test.ts`, `ui-config-hostless.spec.ts`, `copilot-chat.spec.ts` |
| P2 | 1 (2 lines) | Bare skips with no reason | `nextjs-app-components.spec.ts`, `nextjs-custom-auth.spec.ts` |

**Total: 12 findings across 13 files, with a bounded and incomplete scan.**

### Top Priorities
1. **`platform/loader-tests/src/playwright-tests/helpers/website.ts:66`**: a missing `/components` page passes three "should render components" tests.
2. **`platform/loader-tests/src/playwright-tests/nextjs/vanilla-cookieconsent.spec.ts:187`**: the `toBeDefined()` on a Locator is vacuous, and the only real check is an unproven absence.
3. **`platform/wab/playwright/e2e/publish.spec.ts:20` and `platform/wab/playwright/e2e/hostless-tiptap.spec.ts:102`**: the titles promise outcomes that no assertion checks.

## Coverage Gaps (Suggestions)
1. **[Error path]** The 404 branch at `platform/loader-tests/src/playwright-tests/helpers/website.ts:66` skips the normal render. Add a variant that asserts the page is served when it should be.
2. **[Auth boundaries]** `publish.spec.ts:20` never exercises an external user. `platform/wab/playwright/e2e/project-access.spec.ts` already shows the pattern: a second login plus the "read permission" banner.
3. **[Edge case]** `hostless-tiptap.spec.ts:102` has no check that distinguishes "no extensions" from "extensions present". Define one observable (for example, toolbar actions absent) and assert it.

**Optional follow-up:** I can run one V3 app-fault probe, with nothing executed yet. The test would be "should render components" in `platform/loader-tests/src/playwright-tests/nextjs/nextjs-website.spec.ts`. The fault is a host that returns 404 for `/components`, and I would confirm the test still passes today and fails after the fix. This needs a trusted checkout, your approval of the exact command, and the loader-tests Next.js host setup. It would cost extra tokens plus a Next.js build and browser run. Tell me if you want it.