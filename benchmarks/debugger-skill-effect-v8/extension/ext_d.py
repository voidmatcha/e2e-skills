"""Batch D of the v8 extension: transient-element, network and session real cases (F3, F10, F14)."""
CASES = []


def add(**kw):
    CASES.append(kw)


add(id="pw-n44", framework="playwright", repo="super-productivity/super-productivity", license="MIT", pr=10596, merged="2026-10-09",
    test="e2e/tests/task-dragdrop/task-multi-drag.spec.ts > Multi-task drag > keeps single-task dragging and plain-click clearing intact on 500 rendered tasks",
    observed="Failed in the 2026-10-08 nightly run. The trace shows that right after the multi-select mark-done, the open-list row for the task is still animating out (scale-up class, unchecked) while the done row has already appeared (checked). The test's restore click runs during that overlap. Locally it failed 3 of 5 runs when the test waited only for one row.",
    error="Error: locator.click: strict mode violation: locator('task').filter({ has: task-title 'Large 496' }).locator('done-toggle') resolved to 2 elements",
    environment="Angular app with 500 rendered tasks; rows animate when a task moves between the open and done lists.",
    spec_before="await expect(page.locator('task-multi-select-bar .bar')).toHaveCount(0);\n// Restore the task, then dragging an unselected row must remain a single drag.\nawait page\n  .locator('task')\n  .filter({ has: page.locator('task-title', { hasText: 'Large 496', exact: true }) })\n  .locator('done-toggle')\n  .click();",
    diag="test_defect", side="Test (race with an animation)",
    explanation="After the mark-done, the old row stays on screen while it animates out and the done row is already there, so for a short window two rows contain the same title. The click runs inside that window and the locator matches both.",
    fix="Before the click, wait for the done row to appear (done-toggle[aria-checked=\"true\"] count 1) and then for the open-list row to leave (the row locator count 1), then click.",
    f="F14", second="F2", fit="clean",
    rationale="An element is present twice only during an animation window, which the click can hit or miss; the fix waits for the transient element to go away.")

add(id="cy-n15", framework="cypress", repo="opensearch-project/opensearch-dashboards-functional-test", license="Apache-2.0", pr=2171, merged="2026-10-15",
    test="cypress/integration/plugins/observability-dashboards/2_trace_analytics_services.spec.js > Testing services table > Opens service flyout",
    observed="Flaky in the 2.19.7 integration test run on linux/arm64 with security enabled: the click on the flyout action button times out after 60 s while the button is found. The step before it, finding the service row by its latency text, passes. Cypress 9.5.4 is pinned on this branch.",
    error="CypressError: Timed out retrying after 60050ms: `cy.click()` failed because this element is detached from the DOM.\n<button ... data-test-subj=\"service-flyout-action-btntrace_service_f030dd15-...\">",
    environment="OpenSearch Dashboards observability plugin; the services table re-requests its data when time range, app config, mode or index-existence checks change.",
    spec_before="it('Opens service flyout', () => {\n  cy.contains('6.42').should('exist');\n  cy.get('button[data-test-subj^=\"service-flyout-action-btn\"]')\n    .first()\n    .click();",
    diag="test_defect", side="Test (holds a stale element)",
    explanation="Each refetch of the services table gives every row a new generated id, so the rows are replaced. The test can match 6.42 from an earlier fetch and grab the button just before a later fetch replaces its row, and this Cypress version does not re-query detached elements.",
    fix="Wait for the table's loading class (euiBasicTable-loading or ouiBasicTable-loading) to be absent before finding and clicking the flyout button.",
    f="F14", second="F11", fit="forced",
    rationale="The element the test holds is replaced within a short window by a re-render; the test acts on a node that no longer exists.")

add(id="cy-n16", framework="cypress", repo="SAP/spartacus", license="Apache-2.0", pr=21798, merged="2026-07-28",
    test="projects/storefrontapp-e2e-cypress/cypress/e2e/.../product-configurator-vc-conflict-dialog.e2e-flaky.cy.ts",
    observed="The spec frequently fails on the test server. The failure appears more often since the configuration update effect was changed to process updates one after another instead of in parallel. It is on a click inside the conflict-solver dialog, not on a missing element.",
    error="CypressError: `cy.click()` failed because the page updated while this command was executing. The element has detached from the DOM (https://on.cypress.io/element-has-detached-from-dom)",
    environment="Angular storefront; the conflict dialog re-renders on every configuration or pricing store update, and its radio inputs are wrapped in an async pipe for price changes.",
    spec_before="cy.get('cx-configurator-conflict-solver-dialog').within(() =>\n  configurationVc.selectAttributeAndWait(\n    attributeName,\n    uiType,\n    value,\n    false,\n    false\n  )\n);",
    diag="test_defect", side="Test (holds a stale element)",
    explanation="When Cypress has located a radio input and is waiting for it to become actionable, an update in flight or a late pricing response replaces that element, so the subject is detached and the click times out. Queueing the updates changed the timing of the re-renders relative to the test.",
    fix="Assert the dialog is visible and the updating message is gone before interacting, split the chained get/should/click into separate commands so Cypress re-queries, wait for pricing, click with force, and check the updating message is gone again afterwards.",
    f="F14", second="F11", fit="forced",
    rationale="The target element is replaced by Angular re-renders in the window between locating it and clicking it.")

add(id="cy-n17", framework="cypress", repo="IQSS/dataverse-frontend", license="Apache-2.0", pr=1086, merged="2026-09-25",
    test="tests/e2e-integration/... file download integration test",
    observed="Intermittent. The download request (a POST) succeeds, the browser is redirected to the object store, and the redirected request fails. Cypress then times out waiting for the download. The same spec passes on other runs without any change.",
    error="net::ERR_EMPTY_RESPONSE (redirected GET to http://s3.localhost/...)\nCypressError: Timed out retrying after 4000ms",
    environment="LocalStack object store exposed on the IPv4 loopback interface; the browser follows a redirect to the host name s3.localhost.",
    spec_before="export default defineConfig({\n  video: false,\n  e2e: {\n    baseUrl: 'http://localhost:8000',\n    specPattern: 'tests/e2e-integration/**/*.spec.{js,jsx,ts,tsx}',",
    diag="test_defect", side="Test (external dependency)",
    explanation="The host name s3.localhost can resolve to the IPv6 loopback, while LocalStack listens only on the IPv4 loopback. When the browser picks the wrong address the redirected request gets an empty response, and the download never completes.",
    fix="Map s3.localhost to 127.0.0.1 with the Cypress hosts setting so redirected downloads reach the IPv4 loopback endpoint.",
    f="F3", second="F8", fit="clean",
    rationale="A net::ERR_ failure on the request to an external service endpoint in the test environment, with the test and the application unchanged.")

add(id="pw-n45", framework="playwright", repo="funsaized/herdr-mise", license="MIT", pr=283, merged="2026-09-25",
    test="critical-accessibility spec > fixture fallback leaves the pane locator copy control clickable",
    observed="Failed twice in one managed verification run, once on chromium and then on firefox, after the parallel lanes began running concurrently on a 4-vCPU runner. The error is raised from outside the test body and is attributed to the running test. The full spec passes locally.",
    error="Error: write EPIPE   (chromium)\nError: read ECONNRESET   (firefox)",
    environment="The test starts a fake local socket server (fixture-app) that the app subscribes to; several test lanes run at the same time.",
    spec_before="fixtureServer = createServer((socket) => {\n  sockets.add(socket);\n  socket.on(\"close\", () => sockets.delete(socket));\n  let request = \"\";\n  socket.on(\"data\", (chunk) => {",
    diag="test_defect", side="Test (external dependency)",
    explanation="The fixture socket server has no error handler on accepted sockets. When the app resets a subscription, which happens often on a loaded runner, a later write raises EPIPE or ECONNRESET as an unhandled error that Playwright attributes to the running test.",
    fix="Add socket.on('error', () => socket.destroy()) so the reset connection is dropped instead of surfacing as an unhandled error.",
    f="F3", second="F8", fit="forced",
    rationale="The failure is a connection error from a network endpoint (here a local fixture server), reported as EPIPE or ECONNRESET, and it appears only under load.")

add(id="pw-n46", framework="playwright", repo="kiani66/hospital-shift-planning", license="MIT", pr=16, merged="2026-10-04",
    test="tests/e2e/personnel-identity.spec.ts:121 > admin imports nurses from CSV; the Head Nurse adds one to a draft schedule…",
    observed="Failed on the mobile-ios (WebKit) project on main after a recent merge, and failed the same way on the retry. Chromium usually passes. The test signs out the admin and signs in as the head nurse; it waits 60 s for the identifier field of the login form and the field never appears.",
    error="TimeoutError: locator.fill: Timeout 60000ms exceeded.\nwaiting for getByLabel('شماره پرسنلی یا ایمیل')",
    environment="Next.js app with a sign-out Server Action; /login redirects an already signed-in user to their home page.",
    spec_before="await page.getByRole(\"button\", { name: \"خروج\" }).click();\nawait signInAndWait(page, fixture.people.head.email);",
    diag="test_defect", side="Test (session ordering)",
    explanation="The test clicks sign out and immediately calls sign in. signIn sees a URL that is not /login yet and navigates to /login while the sign-out action is still in flight; the navigation cancels the action, so the cookie is never cleared and /login redirects the still-signed-in browser home. The login form never renders.",
    fix="Add a signOut helper that clicks sign out and then waits for /login and the login form; make signIn assert that it actually reached /login; use the helper at all three sign-out sites.",
    f="F10", second="F11", fit="clean",
    rationale="The session was not actually ended when the test proceeded, so the next step sees a signed-in browser where it expects a signed-out one.")
