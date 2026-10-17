"""Batch E of the v8 extension: later top-up cases from a relaxed second scan (F1, F7, F8, F11, F14)."""
CASES = []


def add(**kw):
    CASES.append(kw)


add(id="pw-n47", framework="playwright", repo="antoniohg/astro-image-zoom", license="MIT", pr=47, merged="2026-10-10",
    test="packages/astro-image-zoom/e2e/zoom.spec.ts (Firefox project) > locks the page scroll...; shows the thumbnail when the full-size image fails to load",
    observed="Every one of the last 62 CI attempts had at least one flaky e2e test and 8 ended red; 61 of the 62 were on Firefox. Which test fails depends on which one the worker ran after the touchpad pinch test: the next test loads a 1429x804 viewport (seen in the trace) and its click misses, the second one after a 30 s timeout. Each of these tests passes when it runs alone.",
    error="TimeoutError: locator.click: Timeout 30000ms exceeded.\nwaiting for getByRole('button', ...) ; the trace shows a 1429x804 viewport instead of the configured size",
    environment="Playwright Firefox project, several tests per worker; the previous test dispatches Ctrl+wheel (a touchpad pinch) on the page.",
    spec_before="{ name: \"firefox\", use: { ...devices[\"Desktop Firefox\"] } },",
    diag="test_defect", side="Test (shared state across tests)",
    explanation="The Ctrl+wheel of the pinch test zooms the page out to 90%, and Firefox remembers page zoom per site for the whole browser, so the next test of the same worker starts in a zoomed page where its click lands elsewhere. The state leaks from one test to the next in the same browser.",
    fix="Set the Firefox user pref browser.zoom.siteSpecific to false in the project's launch options so the zoom dies with its tab.",
    f="F7", second="F8", fit="clean",
    rationale="State left by one test (browser zoom) breaks the next test of the same worker and each of the failing tests passes in isolation.")

add(id="pw-n48", framework="playwright", repo="jakemismas/QREP", license="MIT", pr=235, merged="2026-10-13",
    test="web/e2e/lightbox.spec.ts:83 > photo-flow components in the editor at 1440 x 900 (round-trip panel)",
    observed="Main went red and the test hung until its 600 s timeout. The artifact of the failing run shows the Fabrics tab although the test had clicked Pattern, and its screenshot size (1672 x 1937) is the size the Pattern tab produces. A passing run shows the Pattern tab at the same size. The unchanged test reproduced it locally, about 1 run in 5.",
    error="Test timeout of 600000ms exceeded.\nwaiting for getByTestId('roundtrip-panel') to be visible",
    environment="Headless Chromium at 1440 x 900; the app picks the desktop or phone editor from a (min-width: 720px) media query. The test takes a full-page screenshot of the record after clicking the Pattern tab.",
    spec_before="await page.getByRole(\"tab\", { name: \"Pattern\" }).click();\nconst panel = page.getByTestId(\"roundtrip-panel\");\nawait expect(panel).toBeVisible();\nawait expect(panel).toHaveCSS(\"display\", \"flex\");\n// ... later: await page.screenshot({ fullPage: true, path: ... })",
    diag="test_defect", side="Test (viewport during capture)",
    explanation="In headless Chromium a full-page capture can report a 1 x 1 window for a moment. That flips the min-width media query, so the app swaps the desktop editor for the phone editor and back; the new desktop editor opens on its default Fabrics tab, where no round-trip panel exists, and the locator waits for a panel that never returns.",
    fix="Wait for the Pattern tab to settle, measure the panel in one evaluate before any capture, and record it with a viewport capture (which never captures beyond the viewport) instead of a full-page screenshot.",
    f="F8", second="F14", fit="forced",
    rationale="The failure depends on the browser's viewport behaviour during a capture (a headless-Chromium environment effect on a viewport media query), not on the application logic.")

add(id="pw-n49", framework="playwright", repo="microting/eform-backendconfiguration-plugin", license="MIT", pr=1319, merged="2026-09-18",
    test="eform-client/playwright/e2e/plugins/backend-configuration-pn/s/compliance-page-shell.spec.ts > År til dato + 1 år (#1299)",
    observed="Intermittent on the stable branch (one run) and on a later pull request. The test expects the overview request to carry a dateTo of today plus one year but receives today. The error-context snapshot shows the select already on År til dato + 1 år, and the asserted request body is the one the page sends on entry (1 January to today).",
    error="Error: expect(received).toBe(expected)\nExpected dateTo: today + 1 year\nReceived dateTo: today",
    environment="Angular admin page; entering the compliance page triggers an overview request, and changing the period preset triggers another one after a debounce.",
    spec_before="async function goToCompliancePage(page: Page): Promise<void> {\n  await page.goto(BASE_URL);\n  await new LoginPage(page).login();\n  await page.waitForTimeout(2000);\n  await page.goto(PAGE_URL);\n  await page.locator('#complianceFilterProperty').waitFor({ state: 'visible' });\n}",
    diag="test_defect", side="Test (race on unordered async results)",
    explanation="goToCompliancePage returns as soon as the filter bar is visible, while the entry overview request can still be in flight. The test then arms a waiter that matches any overview response and changes the preset; when the entry response lands after the waiter is armed, the waiter resolves on it instead of on the request for the new preset. The application is correct.",
    fix="Arm a waiter for the entry overview response before page.goto(PAGE_URL) and await it inside goToCompliancePage, so every test starts with nothing in flight and its waiter can only match its own request.",
    f="F11", second="F5", fit="clean",
    rationale="Two responses for the same endpoint can arrive in either order; the waiter assumes the wrong one is first.")

add(id="pw-n50", framework="playwright", repo="royerlab/luxar", license="BSD-3-Clause", pr=3076, merged="2026-10-06",
    test="packages/luxar-viewer/src/tests/e2e/keyboard-input-system.spec.ts > Shift+W speed boost (two tests)",
    observed="Flaky on loaded hosts. The tests hold W, wait a fixed time and measure how far the camera moved, then do the same with Shift+W and compare. Run on a heavily loaded machine (about 6 to 8 frames per second) the old test reproduced the failure: the comparison between normal and boosted movement inverts or flattens. The number of rendered frames in the hold can be zero.",
    error="Error: expect(received).toBeGreaterThan(expected)\nExpected: > <normal W distance>\nReceived: <boosted distance, no greater>",
    environment="Browser 3D viewer with a fly-camera that moves a fixed distance per rendered frame while a key is held.",
    spec_before="await page.keyboard.down('Shift');\nawait page.keyboard.down('w');\nawait page.waitForTimeout(500);\nawait page.keyboard.up('w');\nawait page.keyboard.up('Shift');\n// compare the camera position delta against the same hold without Shift",
    diag="test_defect", side="Test (fixed sleep)",
    explanation="The measurement is camera-position delta over a fixed wall-clock hold. On an overloaded host the number of rendered frames inside that hold varies and can be zero, so the two samples are not comparable.",
    fix="Keep one real Shift+w keydown to prove the binding arms speedBoost, then drive the physics directly inside a single synchronous page.evaluate (set the flags, call controls.update(dt) a fixed number of times) and assert the exact 2x speed ratio.",
    f="F1", second="F8", fit="clean",
    rationale="A fixed wall-clock sleep decides how much work happens; on a slow host the sample is too small, a classic timing flake.")

add(id="pw-n51", framework="playwright", repo="simstudioai/sim", license="Apache-2.0", pr=8951, merged="2026-10-13",
    test="apps/sim/scripts/test-mobile-e2e.ts > e2e (mobile, webkit): phone chat/resources, phone and tablet workflow controls",
    observed="The mobile webkit e2e failed on every run, on staging and every pull request for several hours, after mobile e2e moved to a production build. A different check fails each time with the same message. The visible shell is correct when the page is inspected afterwards, and the mobile chromium job is not affected.",
    error="Error: strict mode violation: locator('.workspace-content-shell') resolved to 2 elements:\n  1) <div class=\"workspace-content-shell ...\">...</div>\n  2) <div class=\"workspace-content-shell ...\"> aka locator('[id=\"S:0\"] > ... > .workspace-content-shell')\n... unexpected value \"hidden\"",
    environment="Next.js production build with streaming server rendering; the test helper returns at the navigation commit.",
    spec_before="await expect(page.locator('.workspace-content-shell')).toBeVisible()\n// ... and in expectNoOverflow:\nconst shell = await page.locator('.workspace-content-shell').boundingBox()",
    diag="test_defect", side="Test (read inside a transient window)",
    explanation="While a streamed page is still arriving, React parks the next segment's markup, shell included, in a hidden div until an inline script swaps it in. visit() returns at the navigation commit, so WebKit can query mid-stream and see both copies of the shell.",
    fix="Scope the locator to the visible shell with .filter({ visible: true }) at all four call sites; two visible shells would still fail strict mode, so nothing is weakened.",
    f="F14", second="F2", fit="forced",
    rationale="A second copy of the element exists only until the streamed segment is swapped in; the query lands inside that window.")

add(id="pw-n52", framework="playwright", repo="joseamaya/edades-del-peru", license="MIT", pr=47, merged="2026-10-15",
    test="tests/e2e/boot.spec.ts:37 > selects a unit on click",
    observed="A pre-existing @smoke test that failed about 19 of 20 runs in the full suite and was hidden by retries: 1 in CI. On a slow runner no selection happens after the click. A diagnostic print in the run showed all five player units projecting to about x=2857, y=1164 in a 1280 x 800 viewport.",
    error="Error: expect(received).toBeGreaterThan(expected)\nExpected: > 0\nReceived: 0   (selected units after the click)",
    environment="WebGL game page; the test stops the game loop after a fixed wait and clicks the projection of the first player unit.",
    spec_before="await page.waitForTimeout(4000);\nawait page.evaluate(() => game.loop.stop());\nconst pos = await page.evaluate(() => {\n  const u = [...g.units.values()].find((x) => x.owner === 0);\n  // project the unit to screen coordinates\n});\nawait page.mouse.move(pos.x, pos.y);",
    diag="test_defect", side="Test (fixed sleep)",
    explanation="The test clicks the first unit after a fixed 4 s wait. Under load the camera may not have finished centering on the base, so the unit sits off-screen or under a HUD panel; the mousedown never reaches the canvas and nothing is selected.",
    fix="Centre the camera on the player's town centre, move the pointer to the canvas centre, poll until a unit projects onto the canvas, then stop the loop and click; assert that selectedUnits contains the clicked id.",
    f="F1", second="F8", fit="forced",
    rationale="A fixed wait decides whether the camera has settled before the click; slow runners need longer, which is timing.")

add(id="pw-n53", framework="playwright", repo="cieyhomelab/mounjaro-przepisy", license="MIT", pr=72, merged="2026-10-10",
    test="tests/e2e/s23-notifications.spec.ts > S23: przypomnienie o zastrzyku, zgoda na powiadomienia > bez internetu włączenie przypomnienia…",
    observed="Flaky on the mobile-chromium project under heavy load. The test opens the reminder settings, cuts the network, ticks the reminder checkbox and presses Save, then expects an offline alert. When it fails the alert never appears. Five repeated runs after the change were green.",
    error="Error: expect(locator).toBeVisible() failed\nLocator: getByRole('alert').filter({ hasText: <offline message> })\nReceived: <element(s) not found>",
    environment="PWA with a settings form that shows a loading line while it fetches its values; context.setOffline(true) is used to simulate no network.",
    spec_before="await openReminderSettings(page);\nawait context.setOffline(true);\nawait expect.poll(() => page.evaluate(() => navigator.onLine)).toBe(false);\n\nawait page.getByRole('checkbox', { name: 'Przypominaj o zastrzyku' }).check();\nawait page.getByRole('button', { name: 'Zapisz' }).click();",
    diag="test_defect", side="Test (missing wait)",
    explanation="Under load the form can still be loading, and can remount once its values arrive, when the network is cut. The remount resets the checkbox, so Save has nothing to save offline and the offline alert never shows.",
    fix="Wait for the checkbox to be visible and the loading text to be hidden before going offline, and assert toBeChecked after checking it and before pressing Save.",
    f="F11", second="F1", fit="clean",
    rationale="The test cuts the network and acts before the form's asynchronous load and remount have finished; the order of load and action decides the result.")
