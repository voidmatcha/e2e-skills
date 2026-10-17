"""Batch C of the v8 extension: async-order, missing-wait and shared-state real cases (F5, F7, F11)."""
CASES = []


def add(**kw):
    CASES.append(kw)


add(id="pw-n37", framework="playwright", repo="garaemon/meme-generator", license="Apache-2.0", pr=17, merged="2026-09-27",
    test="e2e/meme-creation.spec.ts > Meme Creation Flow > should create a meme from a fixed image template with multiple texts",
    observed="Failed about 1 run in 3 locally on Chromium, Firefox and WebKit, and intermittently in CI. The failure comes after the test selects the first text a second time; the second text is added without problems. The portrait Two Buttons template is used.",
    error="Error: expect(locator).toHaveValue(expected) failed\nExpected: \"First Text\"\nReceived: \"\"   (after reselecting the first text)",
    environment="Canvas-based editor; the template image is loaded asynchronously after the editor tools appear.",
    spec_before="// 2. Verify we are in the editor\nawait expect(page.getByText('Editor Tools')).toBeVisible();\n\n// 3. Add first text\nawait page.getByRole('button', { name: 'Add Text' }).click();",
    diag="test_defect", side="Test (missing wait)",
    explanation="The editor starts with a 600x600 canvas and places the first text relative to it. The portrait template then loads and the canvas narrows, so the test's later click at a quarter of the width misses the first text. The test clicked Add Text before the template image had loaded.",
    fix="Poll the editor canvas's bounding box and wait until its width is below 600 (the narrowed portrait canvas) before adding text.",
    f="F11", second="F1", fit="clean",
    rationale="The step assumes an asynchronous load has finished; the order of image load and test action decides the outcome.")

add(id="cy-n13", framework="cypress", repo="wso2/apim-apps", license="Apache-2.0", pr=1423, merged="2026-09-07",
    test="tests/cypress/e2e/devportal/005-mcp-servers/02-devportal-mcp-playground.cy.js",
    observed="Intermittent failure in the dev portal integration tests, at the step that saves a newly created application. The create command visits the page and then registers an intercept for the application-attributes request and waits on it with a 300 s timeout; the form is filled right after that wait.",
    error="AssertionError: the application was not created after Save (shaped; the pull request describes the failure without quoting its text)",
    environment="Dev portal React app; the page fetches the application attributes and the throttling tiers on mount.",
    spec_before="Cypress.Commands.add('createApp', (appName, appDescription) => {\n    cy.visit(`/devportal/applications/create?tenant=carbon.super`);\n    cy.intercept('**/application-attributes').as('attrGet');\n    cy.wait('@attrGet', { timeout: 300000 }).then(() => {\n        // Filling the form\n        cy.get('#application-name').click();",
    diag="test_defect", side="Test (race on unordered async results)",
    explanation="The intercept is registered after the visit, so it can miss the app's own on-mount fetch, and the test waits only for the attribute request, not for the tiers request. Save can run its validation before the attribute list has loaded and fail.",
    fix="Register both intercepts (@attrGet and @tiersGet) before cy.visit() and cy.wait(['@attrGet', '@tiersGet']) before touching the form.",
    f="F11", second="F1", fit="clean",
    rationale="Two asynchronous loads and an intercept registered after the navigation: the order in which responses and test steps happen is not controlled.")

add(id="cy-n14", framework="cypress", repo="stackrox/stackrox", license="Apache-2.0", pr=22436, merged="2026-08-26",
    test="ui/apps/platform/cypress/integration/violations/violations.test.js > Violations > should sort the Severity column",
    observed="Flaked in the nightly runs from August 10, 2026: three failures in eleven days across all three GKE nightly variants. It passes on the PR runs and on other nights. The assertion fails on the order of the rows, not on a missing element. Two small UI changes that added content to the violations page had merged shortly before the first failure.",
    error="AssertionError: expected the Severity column rows to be sorted by severity, but they are ordered by violation time.",
    environment="Cypress against the platform UI; the violations table refreshes itself on a timer.",
    spec_before="it('should sort the Severity column', () => {\n    interactAndWaitForViolationsResponses(() => {\n        visitViolations();\n    });",
    diag="test_defect", side="Test (race on unordered async results)",
    explanation="The violations page polls the server every 5 seconds. When the test reaches the sort click at about 4 seconds, the poll fires at 5 seconds and its response, sorted by violation time, is intercepted by interactAndWaitForViolationsResponses before the sort-click response arrives. The assertion then runs on time-sorted data. The race existed since polling was introduced; the extra page content only moved the test into that window.",
    fix="Freeze setInterval at the start of the test with cy.clock(Date.now(), ['setInterval']) so the poll cannot fire during the test.",
    f="F11", second="F1", fit="clean",
    rationale="Two server responses (the poll and the sort click) can arrive in either order; the test assumes the sort response is the one it intercepted.")

add(id="pw-n38", framework="playwright", repo="openooxml/betteroffice", license="Apache-2.0", pr=1386, merged="2026-10-15",
    test="e2e/browser/plugin-host/xlsx-worker-editor.browser.ts > default worker API stages proposals after typing and supports accepting and rejecting them",
    observed="Flaked in its proposal assertion. When it fails, the old text of the proposed change reads 'initialtyped before proposal' where the test typed 'typed before proposal' into a cell that starts with the value 'initial'. With the worker's reply artificially delayed by 1 s it failed 20 of 20 runs; undelayed it passed 50 of 50 on the same machine.",
    error="Error: expect(received).toEqual(expected)\nReceived oldText: \"initialtyped before proposal\"\nExpected oldText: \"typed before proposal\"",
    environment="Browser spreadsheet editor with a worker engine; the edit key (function key 2) opens the cell editor, which loads the cell's current input from the worker asynchronously.",
    spec_before="await page.getByTestId('xlsx-scroll').focus();\nawait page.getByTestId('xlsx-scroll').press('F2');\nawait page.getByTestId('xlsx-cell-editor').fill('typed before proposal');\nconst proposed = await page.evaluate(() => window.__xlsxWorkerEditor.peerless!.editor.proposeChanges!({",
    diag="test_defect", side="Test (order assumption)",
    explanation="The edit key (function key 2) mounts the cell editor empty and fetches the cell's input from the worker asynchronously. Edits made while that prefill is pending are held and replayed onto the prefilled value, so fill() queued before the prefill landed ends up appended after it: 'initial' plus 'typed before proposal'. The ordering barrier itself held; only the draft text was wrong.",
    fix="After the edit key, wait for the editor to have the prefilled value: expect(editor).toHaveValue('initial'), then fill as before.",
    f="F11", second="F5", fit="clean",
    rationale="An asynchronous prefill and the test's fill race, and the replay order depends on which finishes first.")

add(id="pw-n39", framework="playwright", repo="surveyjs/survey-library", license="MIT", pr=11955, merged="2026-10-05",
    test="e2e/questions/dropdown.spec.ts > react Dropdown question > Check dropdown key press without searchEnabled",
    observed="Flaky on the react framework run. The keyboard sequence (Tab, four ArrowDown, Enter) is sent right after the survey is re-initialised; nothing is selected. The same sequence works when the page has had time to render. The assertion for the selected value reports that its element does not exist.",
    error="Error: expect(locator).toHaveText(expected) failed\nLocator: .sd-dropdown__value .sv-string-viewer\nReceived: <element(s) not found>",
    environment="React 18 survey renderer; the helper that re-initialises the survey unmounts the old root and renders the new one.",
    spec_before="await initSurvey(page, framework, json);\nconst popupContainer = page.locator(\".sv-popup__container\").filter({ visible: true });\n\nawait page.keyboard.press(\"Tab\");\nawait page.keyboard.press(\"ArrowDown\");",
    diag="test_defect", side="Test (missing wait)",
    explanation="initSurvey unmounts the old React root synchronously and schedules the new render asynchronously. Pressing Tab right after it returns hits an empty #surveyElement, so focus is never established and the following arrow and Enter keys go nowhere.",
    fix="Wait for the first .sd-dropdown to be visible after initSurvey before any keyboard input (and replace the later fixed 100 ms wait with an assertion that the popup is hidden).",
    f="F11", second="F1", fit="forced",
    rationale="Keyboard input assumes the re-render scheduled by the helper has completed; the race is between an asynchronous render and the test, not a pure duration.")

add(id="pw-n40", framework="playwright", repo="Inkaengine/inka", license="MIT", pr=483, merged="2026-10-07",
    test="tests-playwright/helpers/BlockVerificationHelper.ts > verifyBlockRendering (block sanity checks)",
    observed="Block sanity checks failed on one frontend and passed on others. It passed when the frontend's own script ran slower than the checks. The failure is reported by the single-element checks that run after the block becomes visible.",
    error="Error: strict mode violation: locator('[data-block-uid=\"…\"]') resolved to 2 elements",
    environment="Headless CMS admin with an embedded frontend; the frontend adds a part for a block with its own script and tags it with the block's uid.",
    spec_before="if ((await block.count()) > 1) {\n  await checkEditAnnotations(block.first(), blockData);\n  return;\n}\n// ... single-element checks on `block`",
    diag="test_defect", side="Test (order assumption)",
    explanation="The helper decides between single-element and multi-element checks from one count taken the moment the block is visible. A frontend can add a second element for the block later, so the count says one while the following single-element checks meet two.",
    fix="Count with a new settledCount helper that reads until three consecutive reads agree, and use it in the branch condition.",
    f="F11", second="F2", fit="forced",
    rationale="A one-time read assumes the page has finished adding elements; whether the second element exists yet depends on script timing.")

add(id="pw-n41", framework="playwright", repo="eddieland/canopy", license="MIT", pr=367, merged="2026-10-14",
    test="ui/e2e/pull-requests.spec.ts > the pull requests list has each PR once, and a PR's page its runs, reviews…",
    observed="Intermittent failure in the pull-requests spec. The step that opens a review and asserts the new URL passes; the next line, which clicks the link back to the PR, fails on some runs. 30 of 30 passed after the change.",
    error="Error: locator.click: strict mode violation: getByRole('link', { name: 'acme/web#88', exact: true }) resolved to 3 elements",
    environment="React Router app; navigations run inside a transition.",
    spec_before="await page.getByTestId('pull-request-review-4').getByRole('link', { name: 'review:4' }).click()\nawait expect(page).toHaveURL(/\\/reviews\\/4$/u)\nawait page.getByRole('link', { name: 'acme/web#88', exact: true }).click()",
    diag="test_defect", side="Test (missing wait)",
    explanation="Navigations run in a transition, so the URL changes while the previous page, which links to its PR three times, is still on screen. The test waited for the URL and not for the new page, so the click can run against the old page and match several links.",
    fix="After the URL assertion, wait for the review page's heading: expect(page.getByRole('heading', { level: 1 })).toHaveText('review:4').",
    f="F5", second="F11", fit="forced",
    rationale="The navigation step is reported as complete (URL changed) while the page state the next action needs is not there yet; the missing wait is for the new content.")

add(id="pw-n42", framework="playwright", repo="cieyhomelab/mounjaro-przepisy", license="MIT", pr=89, merged="2026-10-11",
    test="tests/e2e/s14-offline.spec.ts > S14: dane offline > S14: offline aplikacja otwiera się po pierwszej wizycie…",
    observed="Flaky on the mobile-chromium project. The test seeds a recipe with a photo and a second recipe, reloads, waits for the offline-data status to read current, goes offline and reloads again. When it fails, the recipes or the photo are missing in the offline reload. Application code did not change between passing and failing runs.",
    error="Error: expect(locator).toBeVisible() failed (offline reload)\nLocator: getByRole('link', { name: /Zupa/ })\nReceived: <element(s) not found>",
    environment="PWA with a service worker; the status line 'Dane offline: aktualne' is stored after the first sync and is shown immediately after a reload.",
    spec_before="const id = await seedWithPhoto(page, 'Kurczak z ryżem');\nawait seedRecipe(page, { title: 'Zupa' });\nawait page.reload();\nawait waitForOfflineData(page);\n\nawait goOffline(context, page);",
    diag="test_defect", side="Test (missing wait)",
    explanation="The status the test waits for was saved by the first sync and is visible right after the reload, before the new recipes and the photo have reached the device. The test therefore went offline too early.",
    fix="Before going offline, wait for the links to both recipes and poll the 'photos' cache until it holds one entry, then wait for the offline status.",
    f="F5", second="F11", fit="forced",
    rationale="The wait signal was already true, so the action proceeded while the state it needs was absent; the missing condition is the data itself.")

add(id="pw-n43", framework="playwright", repo="dam-agents/dam", license="Apache-2.0", pr=4396, merged="2026-10-07",
    test="packages/e2e/playwright/src/tests/smoke/08-session-delete.spec.ts > deleting inactive and active sessions preserves the right navigation",
    observed="Flaked once in CI on a pull request that does not touch the UI. The test deletes an inactive session in step B and the active session in step C, and asserts the same 'Session deleted' toast after each. It failed in step C.",
    error="Error: strict mode violation: getByText('Session deleted') resolved to 2 elements",
    environment="Toast notifications are shown for 4 seconds and dismiss themselves; the e2e needs a cluster.",
    spec_before="await expect(page.getByText(secondPrompt, { exact: true })).toBeVisible();\n});\n\nawait test.step(\"(C) deleting the active session removes it without a refresh\", async () => {",
    diag="test_defect", side="Test (shared state across steps)",
    explanation="The toast from step B is still on screen when step C triggers its own, so the page-wide text locator matches both. Step C would also pass on B's stale toast if it used .last(). The run depends on whether B's toast auto-dismissed before C ran.",
    fix="End step B by asserting that its toast is hidden, so step C's assertion proves that its own toast appeared.",
    f="F7", second="F11", fit="forced",
    rationale="State left by an earlier step (a toast) leaks into the next step; it is the same test, so the fit to the suite-level isolation definition is loose.")
