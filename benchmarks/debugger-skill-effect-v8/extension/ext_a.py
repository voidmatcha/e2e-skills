"""Batch A of the v8 extension: locator-side real cases (F2 / F12). Authored from public merged PRs, labeled from the merged fix."""
CASES = []


def add(**kw):
    CASES.append(kw)


add(id="pw-n19", framework="playwright", repo="adrirubio/claude-deck", license="MIT", pr=692, merged="2026-10-13",
    test="frontend/e2e/lane-c/feed.spec.ts > opening a detail keeps it at its row",
    observed="Intermittent: about 1 failure in 15 runs, and 4 of 30 in an earlier run. The journey opens the first row of the Audit feed and then checks that the page is still scrolled to that row. When it fails, the recorded box of the clicked element is at y=2866 where a passing run records y=313, and the page's main scroll height is 1106 instead of 2959. The Audit page itself behaves correctly in both runs.",
    error="Error: expect(received).toBeCloseTo(expected)\nExpected: 313\nReceived: 2866   (row position after opening the detail)",
    environment="Playwright against the built frontend. The row list is rendered after a names request finishes; the test waits for network idle before it starts.",
    spec_before="const FEED_ROW = 'main [role=\"feed\"] article, main [data-testid=\"audit-feed-row\"], main ol li'\n// ...\nconst row = page.locator(FEED_ROW).first()\nawait row.click()",
    diag="test_defect", side="Test (over-broad locator)",
    explanation="The last alternative of the selector, main ol li, also matches the ten footnotes of the collapsed All metrics block. The feed renders after the names request ends, and network idle can return before that, so until then .first() resolves to a footnote far below the feed. The test then clicks and measures a different element than the one it means.",
    fix="Remove the main ol li alternative so the selector matches only feed rows; Playwright then waits until the feed exists.",
    f="F2", second="F1", fit="clean",
    rationale="The locator was too broad from the start (it also matched footnotes); the DOM did not change. The wrong element is picked only while the feed is still missing.")

add(id="pw-n20", framework="playwright", repo="cipansor/cipansor", license="Apache-2.0", pr=427, merged="2026-09-01",
    test="apps/web/e2e/performance.spec.ts > Integrated Performance Management (/kinerja) E2E Flows > (the test that loads /kinerja)",
    observed="The first test of the file fails on every run against the /kinerja page. The URL check and the h1 text check before it pass; the failure is reported at the first text locator after them.",
    error="Error: strict mode violation: locator('text=Perjanjian Kinerja') resolved to 4 elements",
    environment="Next.js app, Playwright with the default strict locators.",
    spec_before="await page.goto(\"/kinerja\");\nawait expect(page).toHaveURL(/\\/kinerja/);\nawait expect(page.locator(\"h1\")).toContainText(/Perencanaan Strategis hingga Perjanjian & Evaluasi Kinerja/i);\nawait expect(page.locator(\"text=Perjanjian Kinerja\")).toBeVisible();\nawait expect(page.locator(\"text=Evaluasi Periodik\")).toBeVisible();",
    diag="test_defect", side="Test (locator)",
    explanation="The text= selector matches by substring, and the phrase Perjanjian Kinerja appears in several places on the page (headings, card titles, menu labels). The locator was never specific enough to name one element.",
    fix="Use exact, specific text locators: page.getByText('Perjanjian Kinerja (PK)', { exact: true }) and page.getByText('Evaluasi & Perilaku SAFTI', { exact: true }).",
    f="F2", second="F12", fit="clean",
    rationale="Playwright strict mode violation on a substring text locator that matches four elements; the page content did not change.")

add(id="pw-n21", framework="playwright", repo="rust-js-lang/rust-js", license="MIT", pr=20, merged="2026-10-06",
    test="test/next.test.ts > rust-js-next dev serves Rust routes, refreshes a save in place, and recove…",
    observed="Failed on both CI attempts of a pull request that does not touch this code. The previous pull request's run passed, and the test passes locally (2 tests). The test waits for the counter button to read Count 0 and then clicks it.",
    error="Error: locator.click: strict mode violation: getByRole('button') resolved to 2 elements",
    environment="Next.js dev server started by the test; Chromium launched from bun test.",
    spec_before="const button = page.getByRole(\"button\");\nawait button.filter({ hasText: \"Count 0\" }).waitFor();\nawait button.click();\nawait button.filter({ hasText: \"Count 1\" }).waitFor();",
    diag="test_defect", side="Test (locator)",
    explanation="getByRole('button') matches every button on the page. When the Next.js dev server's own Dev Tools button has rendered by the time of the click, the locator resolves to two elements; when it renders later the test passes. The click is on an unscoped locator, and the filter is applied only to the wait.",
    fix="Name the counter button: getByRole('button', { name: /\\d$/ }), since its name always ends in its count and the Dev Tools button's does not.",
    f="F2", second="F1", fit="clean",
    rationale="Unscoped getByRole('button') is ambiguous as soon as a second button exists; the failure only looks intermittent because the extra button appears at a variable time.")

add(id="pw-n22", framework="playwright", repo="samuel-burke/shiftview", license="MIT", pr=116, merged="2026-10-14",
    test="e2e/contrast.spec.ts > /settings (manager) holds text contrast in dark at 1440px; switching theme in Settings recolors the app without a reload",
    observed="Two tests failed on a push run to dev while the pull-request run on the same commit passed. Locally it failed once in a full mobile-chrome run and once in a stress run (--workers=6 --repeat-each=3). The trace shows the expect failing after about 400 ms, not after the 5 s expect timeout.",
    error="Error: expect.toBeVisible: strict mode violation: getByText('Appearance') resolved to 2 elements (both hidden at that moment)",
    environment="Playwright against a Next.js app with mocked APIs; /settings streams and hydrates.",
    spec_before="{ path: \"/settings\", role: \"manager\", ready: (p) => expect(p.getByText(\"Appearance\")).toBeVisible() },\n// ...\nawait page.goto(\"/settings\");\nawait expect(page.getByText(\"Appearance\")).toBeVisible();",
    diag="test_defect", side="Test (locator)",
    explanation="While Settings is still streaming and hydrating, the page briefly holds two Appearance labels, only one of them inside main. A strict mode violation fails the expect at once instead of retrying, so a poll that lands in that window ends the test after about 400 ms. Once loading finishes only one label is visible.",
    fix="Scope both readiness checks to main: getByRole('main').getByText('Appearance'), which targets the copy that becomes visible.",
    f="F2", second="F1", fit="clean",
    rationale="Locator ambiguity (two matches) is reported as a strict mode violation that does not retry; the second copy exists only during streaming.")

add(id="pw-n23", framework="playwright", repo="akash-network/console", license="Apache-2.0", pr=4381, merged="2026-10-14",
    test="apps/deploy-web/tests/ui/onboarding-gate.spec.ts > Onboarding gate — not-onboarded user > (step: allowed on billing, where the trial converts)",
    observed="The beta e2e gate for console-web 3.319.0 failed and blocked the production promotion; the previous release passed. The failure is deterministic on the new build. The release added a Billing details section to the billing page.",
    error="Error: expect.toBeVisible: strict mode violation: getByRole('heading', { name: 'Billing' }) resolved to 2 elements",
    environment="Playwright against the deployed beta build of the console web app.",
    spec_before="await visit(page, \"/billing\");\nawait expect(page.getByRole(\"heading\", { name: \"Billing\" })).toBeVisible({ timeout: 30_000 });\nawait expect(page).not.toHaveURL(/\\/onboarding/);",
    diag="test_defect", side="Test (locator not updated)",
    explanation="getByRole('heading', { name: 'Billing' }) matches by substring. The new Billing details h2 also contains the word Billing, so the locator now finds both the page's h1 and the new h2. The locator was written for a page with one such heading.",
    fix="Match the h1 exactly: getByRole('heading', { level: 1, name: 'Billing', exact: true }).",
    f="F12", second="F2", fit="clean",
    rationale="A page change (a new heading) made an existing substring locator ambiguous; the product change is named and the test locator was not updated.")

add(id="pw-n24", framework="playwright", repo="OBLIQ-in/OBLIQ-Website", license="MIT", pr=163, merged="2026-10-14",
    test="e2e/smoke.spec.ts > join form shows validation errors",
    observed="The E2E job on main has failed every run since a pull request that added a newsletter input to the site footer was merged. The earlier steps of the test (empty-submit errors for name and resume) pass. Without that pull request the same test passed.",
    error="Error: locator.fill: Error: strict mode violation: getByLabel('Email') resolved to 2 elements",
    environment="Playwright against a production build of the site.",
    spec_before="await expect(page.getByText(\"Please add a link to your resume.\")).toBeVisible();\n\nawait page.getByLabel(\"Email\").fill(\"not-an-email\");\nawait page.getByRole(\"button\", { name: \"Submit\" }).click();",
    diag="test_defect", side="Test (locator not updated)",
    explanation="The new footer newsletter input has aria-label Email address, and getByLabel('Email') matches by substring, so the join form's lookup now resolves to two inputs. The author did not rerun the smoke tests after adding the field.",
    fix="Scope the lookup to the main landmark: page.getByRole('main').getByLabel('Email'), which the footer is outside of.",
    f="F12", second="F2", fit="clean",
    rationale="A DOM addition elsewhere on the page broke a previously unambiguous locator, and the cause pull request is named.")

add(id="pw-n25", framework="playwright", repo="raphaeldenis/openfleet", license="Apache-2.0", pr=248, merged="2026-10-05",
    test="apps/desktop/e2e/project-home.spec.ts > Project home shows the project, its docs folder and its sessions, and star…",
    observed="main has been red in the e2e job since two pull requests merged in sequence (a sidebar change and a project-home change). The second pull request was green only on its base from before the first. The steps that check the sessions region and the Counts group pass; the click at line 27 fails.",
    error="Error: strict mode violation: getByRole('link', { name: 'New session', exact: true }) resolved to 2 elements",
    environment="Electron desktop app driven by Playwright; the sidebar and the project home are on the same screen.",
    spec_before="await expect(page.getByRole('group', { name: 'Counts' })).toContainText('Notes');\n\nawait page.getByRole('link', { name: 'New session', exact: true }).click();",
    diag="test_defect", side="Test (locator not updated)",
    explanation="The sidebar change added a plus link named New session to each group, so the project home's quick action of the same name is no longer the only match. The page-wide locator was written before the sidebar link existed.",
    fix="Scope the locator to the project home region: page.getByTestId('project-home').getByRole('link', { name: 'New session', exact: true }).",
    f="F12", second="F2", fit="clean",
    rationale="A merged UI change added a second element with the same accessible name; the test locator was not updated and the cause is named.")

add(id="pw-n26", framework="playwright", repo="LumenWipe/lumenwipe", license="Apache-2.0", pr=607, merged="2026-10-12",
    test="apps/web/tests/e2e/demolisher.spec.ts > home page renders the entry form and headline",
    observed="The nightly e2e went red after a change that renamed the hero headline; 1 failed, 43 passed, and the single failure is identical on both retries. The page loads and the page snapshot is complete; the other assertions in the test are not reached.",
    error="Error: expect(locator).toBeVisible() failed\nLocator: getByText('Wind down your Stellar account')\nExpected: visible\nReceived: <element(s) not found>",
    environment="Playwright against the testnet route of the web app (/testnet). The page snapshot in the report shows the h1 reading: Close your Stellar account.",
    spec_before="await page.goto(\"/testnet\");\nawait expect(page.getByText(\"Wind down your Stellar account\")).toBeVisible();\nawait expect(page.getByText(\"Account details\")).toBeVisible();",
    diag="test_defect", side="Test (expected text not updated)",
    explanation="The hero headline was renamed in the page component and the spec still asserts the old wording, so the locator finds nothing. The product behaves correctly; the assertion is stale.",
    fix="Assert the current headline with a role-based locator: getByRole('heading', { level: 1, name: 'Close your Stellar account' }).",
    f="F12", second="F4", fit="clean",
    rationale="Page copy changed and the test still looks for the old text; the DOM drift is the only cause.")

add(id="pw-n27", framework="playwright", repo="redhat-developer/rhdh-plugin-export-overlays", license="Apache-2.0", pr=4332, merged="2026-10-13",
    test="workspaces/backstage/e2e-tests/tests/specs/techdocs.spec.ts > TechDocs > (the test that opens a component's TechDocs link)",
    observed="The step after opening the Red Hat Developer Hub component page times out waiting for the TechDocs link. The sidebar navigation, the Component kind filter and the component click before it succeed. The link is on the page but its label differs from what the test looks for.",
    error="TimeoutError: locator.waitFor: Timeout exceeded.\nwaiting for getByRole('link', { name: 'TechDocs' }) to be visible",
    environment="Backstage-based Developer Hub, Playwright with a shared UI helper class.",
    spec_before="await uiHelper.clickLink(\"Red Hat Developer Hub\");\nconst linkLocator = page.getByRole(\"link\", { name: \"TechDocs\" });\nawait linkLocator.waitFor({ state: \"visible\" });\nawait linkLocator.click();",
    diag="test_defect", side="Test (locator not updated)",
    explanation="The component page's link to the documentation is now labeled View TechDocs. The test still looks for a link whose accessible name is TechDocs, so the wait runs out.",
    fix="Update the locator to the current label: page.getByRole('link', { name: 'View TechDocs' }).",
    f="F12", second="F2", fit="clean",
    rationale="The UI label changed and the test locator was not updated; the element exists under a new accessible name.")

add(id="pw-n28", framework="playwright", repo="super-productivity/super-productivity", license="MIT", pr=10816, merged="2026-10-14",
    test="E2E Tests (Released Clients) > the @supersync released suite and the v18.14.0 to v19.0.1 upgrade suite (setupSuperSync)",
    observed="The nightly Released Clients job has been red on master since a change that turned the SuperSync access-token field into a single-line input: 9 failed and 20 did not run in the v19.1.0 suite, and 2 failed in the v18.14.0 to v19.0.1 upgrade suite. The same code passes against the current build. Every failure stops at the step that fills the access token.",
    error="Error: locator.fill: Test ended.\n  - waiting for locator('.e2e-accessToken input')",
    environment="The same page object drives both the current build and bundles of released clients (v19.1.0, v19.0.1, v18.14.0).",
    spec_before="this.baseUrlInput = page.locator('.e2e-baseUrl input');\nthis.accessTokenInput = page.locator('.e2e-accessToken input');",
    diag="test_defect", side="Test (page object locator)",
    explanation="The page object was changed to match the current client's single-line input. Released clients still render the access token as a textarea, so the shared locator finds nothing on them and fill waits until the test ends.",
    fix="Let the locator match either element: '.e2e-accessToken input, .e2e-accessToken textarea'. Each client renders exactly one, so strict mode still holds.",
    f="F12", second="F8", fit="clean",
    rationale="A shared page-object locator was updated for the new DOM and no longer matches the older clients' DOM; the change is named.")

add(id="pw-n29", framework="playwright", repo="LodyAI/Lody", license="Apache-2.0", pr=895, merged="2026-09-23",
    test="LODY-ROLE-001 (Desktop Daily journey)",
    observed="The Desktop Daily run failed LODY-ROLE-001 on both macOS and Ubuntu. The Role menu opens and the submenu is shown with the expected entries; the step that picks the role by name fails. The unrelated session-bootstrap failures in the same run are tracked separately.",
    error="Error: expect(locator).toBeEnabled() failed\nLocator: getByRole('menuitemradio', { name: '<role title>', exact: true })\nReceived: <element(s) not found>",
    environment="Desktop app driven by Playwright. Each role menu item shows the role title and a smaller binding subtitle.",
    spec_before="const roleOption = this.page.getByRole('menuitemradio', {\n  name: this.fixture.roleName,\n  exact: true,\n});\nawait expect(roleOption).toBeEnabled();\nawait roleOption.press('Enter');",
    diag="test_defect", side="Test (page object locator)",
    explanation="The menu item's accessible name contains the binding subtitle in addition to the role title. An exact name match against the title alone can therefore never succeed.",
    fix="Select the radio menu item that contains the exact visible title: getByRole('menuitemradio').filter({ has: page.getByText(roleName, { exact: true }) }).",
    f="F12", second="F2", fit="forced",
    rationale="The element exists under a different accessible name than the page object expects, which is locator drift; no specific product change is named, so the fit is only partial.")

add(id="pw-n30", framework="playwright", repo="wcpos/monorepo", license="MIT", pr=2340, merged="2026-09-30",
    test="apps/main/e2e/reports.spec.ts > Reports Page (Free) > should show upgrade overlay on Reports; should show View Demo button on upgrade overlay; Reports Page (Pro) > should show filter pills; should show print button; should show report content",
    observed="Five reports tests sit in the quarantine list and fail in a quarantine-only run on the mini store: two Free tests and three Pro tests. They all fail on a missing test id, not on a timeout. The reports screen itself loads and is usable. The screen was redesigned as the Sales room before this run.",
    error="Error (Free x2): getByTestId('upgrade-title') ... element(s) not found\nError (Pro): getByTestId('order-filter-status') ... element(s) not found\nError (Pro): getByTestId('reports-content') ... element(s) not found\nError (Pro): getByTestId('reports-print-button') ... element(s) not found",
    environment="Playwright e2e on a mini store with Free and Pro projects. The spec keeps a quarantine list for known failures.",
    spec_before="test('should show filter pills', async ({ posPage: page }) => {\n  await navigateToPage(page, 'reports');\n  const screen = page.getByTestId('screen-reports');\n  // ... then looks for order-filter-status, reports-content and reports-print-button\n});",
    diag="test_defect", side="Test (stale spec)",
    explanation="The Sales room replaced the filtered order report: order-filter-status, reports-content and reports-print-button no longer exist, and Free is no longer behind an upgrade overlay. The spec still describes the old screen.",
    fix="Rewrite the checks for the new test ids (scope chips, period cards, the hero print button), replace the two overlay checks with one that expects the day report and no upgrade title, and remove the five quarantine entries.",
    f="F12", second="F4", fit="clean",
    rationale="Product screen redesigned; every locator in the spec points at removed elements. The product change is named.")
