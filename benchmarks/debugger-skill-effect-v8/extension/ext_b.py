"""Batch B of the v8 extension: timing / race real cases (F1, F11, F14, F15)."""
CASES = []


def add(**kw):
    CASES.append(kw)


add(id="pw-n31", framework="playwright", repo="joshuasundance-swca/throttlebrawl", license="MIT", pr=507, merged="2026-10-05",
    test="tests/e2e/ui-settings.spec.ts > every setting on screen persists across a reload and changes something observable (tilt sensitivity probe)",
    observed="Failed on two unrelated pull requests, in browser shard 2 of 4 each time, on a loaded CI browser: once the steer read 72 and then 68 on the retry, and once 69 and then 66, where the probe expects 73 plus or minus 4. Neither pull request touches input. The assertion and its tolerance are the same on every run that passes.",
    error="Error: tilt sensitivity 2: 8.0 degrees steers 68; expected 73 (tolerance 4)",
    environment="Browser game page driven by Playwright; the tilt input passes through a smoothing filter with a time constant of 0.1 s that advances once per input sample, one per simulation tick.",
    spec_before="await tiltTo(page, 0, 0);\nawait tiltTo(page, 8, 8);\n// eslint-disable-next-line no-restricted-syntax -- debt: the tilt filter settles per input sample (sim ticks), so this should wait on ticks\nawait page.waitForTimeout(800); // the tilt filter (0.1 s) settles\nconst last = await waitLast(page, (s) => s.steer !== 0);",
    diag="test_defect", side="Test (fixed sleep)",
    explanation="The filter settles per input sample, not per millisecond. A fixed 800 ms of wall clock is enough on a fast browser but, on a loaded CI browser that runs fewer simulation ticks in that time, leaves the steer short of its target when the value is read.",
    fix="Wait for 60 simulation ticks (about a second of game time) with page.waitForFunction on the game's tick counter instead of waitForTimeout(800); keep the assertion and tolerance.",
    f="F1", second="F8", fit="clean",
    rationale="A fixed wall-clock sleep that is sometimes too short on a slow runner: timing flake that passes on a fast run and fails near the sleep budget.")

add(id="pw-n32", framework="playwright", repo="oxyc/den-edge", license="MIT", pr=401, merged="2026-10-11",
    test="web/e2e/billboard-viewport.spec.mjs > billboard viewport stability: desktop resize",
    observed="Flaky in CI. The failure is on the line that expects the hero to grow after the viewport is enlarged, and the received height equals the old height. Taking the sleep out of the test fails 11 of 30 repeated runs with the same numbers. The app behaves correctly when checked by hand.",
    error="Error: expect(received).toBeGreaterThan(expected)\nExpected: > 608\nReceived: 608",
    environment="Chromium; the hero element pins its height from a resize listener.",
    spec_before="await page.evaluate(() => scrollTo(0, 250));\nawait page.setViewportSize({ width: 390, height: 950 });\nawait page.waitForTimeout(100);\nconst after = await hero.boundingBox();",
    diag="test_defect", side="Test (fixed sleep)",
    explanation="The hero re-measures from a resize listener that the page runs on a frame after setViewportSize has returned. The test slept a fixed 100 ms and read the height; on a slow runner the listener has not run yet and the old pin is still in place.",
    fix="Register a one-shot resize listener (plus a frame) before resizing and await it instead of sleeping; use the same signal in the touch case that asserts nothing changes.",
    f="F1", second="F11", fit="clean",
    rationale="Fixed 100 ms wait followed by a read that races a later frame; the read is too early on a slow run and passes on a fast one.")

add(id="pw-n33", framework="playwright", repo="smart-ssh/smart_ssh", license="Apache-2.0", pr=438, merged="2026-10-12",
    test="apps/smart-ssh-community/frontend/e2e/tests/long-content-dialogs.spec.ts:98 (webkit-small); server-tree.spec.ts:43; server-management-review.spec.ts:194",
    observed="Sporadic timeouts mostly in the WebKit projects: the import spec failed 2 of 30 repeated runs in webkit-small. The trace of a failing run shows newPage taking about 7 s and the wait for #root about 15 s, so the 30 s test timeout expires during the next usability check. Two other specs have the same shape (a late, short step hits the test timeout) but did not fail locally.",
    error="Error: Test timeout of 30000ms exceeded.",
    environment="Four workers run the specs in parallel against a Vite dev server started for the suite; fullyParallel is on.",
    spec_before="export default defineConfig({\n  testDir: \"./tests\",\n  outputDir: \"./test-results\",\n  fullyParallel: true,\n  // ... four workers; the first spec of each worker opens the harness page cold",
    diag="test_defect", side="Test (timeout budget)",
    explanation="The Vite dev server transforms modules on first request. With four workers opening the app at once on a cold server, the first tests spend most of their 30 s budget loading the page, so a later short step crosses the limit.",
    fix="Add a Playwright globalSetup that loads the harness page once in Chromium and WebKit until network idle before any test runs, without raising any timeout or adding retries.",
    f="F1", second="F8", fit="clean",
    rationale="Failures are timeouts near the budget that pass on a warm server; the load-dependent slow start is the timing cause.")

add(id="cy-n11", framework="cypress", repo="centreon/centreon", license="Apache-2.0", pr=12013, merged="2026-10-13",
    test="centreon/tests/e2e/features/Additional-connectors/04-ACC-update (updateAcc)",
    observed="Reported as flaky. It passes locally and fails occasionally under CI load, at the step that picks the poller option after the Select poller(s) dropdown is opened. The same command is shared with the 05-ACC-check-permissions suite.",
    error="AssertionError: Timed out retrying after 4000ms: Expected to find content: '<poller name>' within the dropdown but never did.",
    environment="MUI autocomplete backed by a fetch with no cache (staleTime 0, gcTime 0); its options are cleared when it closes and fetched again when it opens.",
    spec_before="cy.getByLabel({ label: 'Select poller(s)', tag: 'input' }).click();\ncy.get('svg[class*=\"deleteIcon\"]').click();\ncy.getByLabel({ label: 'Select poller(s)', tag: 'input' }).click().click();\ncy.contains(body.pollers[0]).click();",
    diag="test_defect", side="Test (missing wait)",
    explanation="The command closes and reopens the dropdown immediately before asserting on an option. Every open re-fetches the pollers and clears them on close, so the click on the option races that fetch: fine locally, occasionally too slow under CI load.",
    fix="Intercept GET /configuration/monitoring-servers as @getPollers (also in 05-ACC-check-permissions), open the dropdown once and cy.wait('@getPollers') before clicking the option; remove the stray double click.",
    f="F11", second="F1", fit="clean",
    rationale="The test acts before an asynchronous fetch it depends on has completed; guessing the timing with an extra click is the race.")

add(id="pw-n34", framework="playwright", repo="kernelKain/footwork", license="MIT", pr=11, merged="2026-10-11",
    test="frontend/tests/shell.spec.ts > keyboard reaches the example action",
    observed="The frontend GitHub Actions job failed on this test on some runs. The test presses Tab up to eight times and reads the focused element's text each time, looking for the Hear an example button. When it fails it stalls on the focus read until the test timeout; it passes on other runs of the same commit.",
    error="Error: Test timeout exceeded while waiting for locator(':focus') (locator.innerText)",
    environment="Playwright on a GitHub Actions runner; the page is a static shell.",
    spec_before="for (let step = 0; step < 8; step += 1) {\n  await page.keyboard.press(\"Tab\");\n  const focused = page.locator(\":focus\");\n  const text = await focused.innerText();\n  if (text.includes(\"Hear an example\")) {",
    diag="test_defect", side="Test (non-retrying read)",
    explanation="After a Tab press the focus can briefly be on nothing or on the body. Reading innerText of the :focus locator then waits for an element until the test timeout, and a slower runner needs more than eight Tab presses to reach the button.",
    fix="Raise the traversal budget to twelve presses, skip iterations where nothing or BODY has focus, and read the text with a short 250 ms timeout and a fallback.",
    f="F1", second="F5", fit="forced",
    rationale="The failure is a timeout on a read that only succeeds when the runner is fast enough; the fix is defensive, so the mechanism is only loosely a timing one.")

add(id="pw-n35", framework="playwright", repo="sean1093/kaeru", license="MIT", pr=112, merged="2026-10-05",
    test="e2e/smoke.spec.ts > app shell > home and settings have no serious or critical accessibility violations",
    observed="Intermittent color-contrast violation in the accessibility gate. The reported background colour is #c0c0c0, a grey that is in no palette of the app. CI runs with retries: 1, so the failure is mostly invisible there. It could not be reproduced locally in 20 repeated runs with 3 workers, before or after the change; it was reproduced in the full three-project matrix.",
    error="Error: expect(received).toEqual(expected)\nExpected: []\nReceived: [{ id: 'color-contrast', impact: 'serious', ... background '#c0c0c0' ... }]",
    environment="axe-core run through @axe-core/playwright on two routes; the app uses web fonts.",
    spec_before="for (const route of ROUTES) {\n  await page.goto(route);\n  const results = await new AxeBuilder({ page })\n    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])\n    .analyze();",
    diag="test_defect", side="Test (read inside a transient window)",
    explanation="axe computes contrast from resolved styles. When the scan runs before the first paint has settled it cannot resolve an element's background and substitutes #c0c0c0, which is a sign that it ran too early rather than that a contrast defect exists.",
    fix="Before scanning, wait for the page's own first heading, document.fonts.ready and two animation frames, rather than for a duration.",
    f="F14", second="F1", fit="forced",
    rationale="The assertion reads a state that exists only before rendering settles: content not yet painted. The window is a render, not a duration, so the fit is imperfect.")

add(id="pw-n36", framework="playwright", repo="piconic-ai/barefootjs", license="MIT", pr=3077, merged="2026-09-19",
    test="site/ui/e2e/carousel.spec.ts > clicking next navigates to next slide; clicking next in vertical carousel navigates",
    observed="Both navigation tests failed on one shard of a pull request that touches nothing near the carousel. The same shard was green on the base branch three minutes earlier. The first assertion (Previous is disabled at the first slide) passes; the one after the click fails after the 5 s window.",
    error="Error: expect(locator).not.toBeDisabled() failed\nLocator: locator('[data-slot=\"carousel\"]').first().locator('[data-slot=\"carousel-previous\"]')\nExpected: not disabled\nReceived: disabled",
    environment="Server-rendered carousel page; the carousel library is loaded by a dynamic import after the page appears.",
    spec_before="// Wait for embla to initialize (prev button disabled at first slide)\nawait expect(prevBtn).toBeDisabled({ timeout: 5000 })\n\n// Click next\nawait nextBtn.click()\nawait page.waitForTimeout(300)\n\n// Previous button should now be enabled\nawait expect(prevBtn).not.toBeDisabled()",
    diag="test_defect", side="Test (interaction before hydration)",
    explanation="The first-slide disabled state of Previous is baked into the server-rendered HTML, so the assertion used as the readiness signal passes before the carousel library's dynamic import has resolved and wired its click handlers. A click in that window does nothing and Previous stays disabled.",
    fix="Retry the click until Previous becomes enabled with expect(async () => { await nextBtn.click(); await expect(prevBtn).not.toBeDisabled({ timeout: 500 }) }).toPass(); remove the fixed 300 ms sleeps.",
    f="F15", second="F5", fit="clean",
    rationale="First interaction on a server-rendered page before the client handlers are attached: the click reports success but has no effect and the failure appears at the next assertion.")

add(id="cy-n12", framework="cypress", repo="dominiksmolinski3/KanbanProject", license="MIT", pr=219, merged="2026-09-23",
    test="frontend/cypress/e2e/subtasks.cy.js > creates subtasks within a task",
    observed="Fails intermittently with a disabled-element error on a slower machine. It failed on main's images locally in 2 of 2 runs and in 1 of 2 runs on the frontend from before an earlier change, and 3 times in 5 runs on the local compose stack. CI runners are fast enough that main's e2e is green. The failure screenshot shows the task panel in the middle of reloading.",
    error="CypressError: cy.type() failed because it targeted a disabled element.",
    environment="Docker compose stack; adding a subtask makes the task panel re-read itself and show a loading line in place of the form.",
    spec_before="subtasks.forEach(subtask => {\n  cy.get('.subtask-input').type(`${subtask}`);\n  cy.wait(300);\n  cy.get('.add-subtask-btn').click();\n});",
    diag="test_defect", side="Test (order assumption)",
    explanation="Adding a subtask makes the panel re-read its data, and while it does the whole form is swapped for a loading line. The command types the next title right after clicking add, so on a slower machine Cypress grabs an input that is already on its way out and finds it disabled.",
    fix="After each add, wait for the subtask to appear in the list and for the input to come back empty ('.subtask-input' should have value ''), and drop the fixed cy.wait(300).",
    f="F11", second="F14", fit="clean",
    rationale="The step assumes the previous add has finished re-rendering before the next input is used; the condition, not a sleep, is what is missing.")
