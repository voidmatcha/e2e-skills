# Blind F-code mapping packet (v8)

60 already-diagnosed E2E failures. For each item you see only the root-cause statement and the fix.

## item-01 (cypress)

Root cause: With testIsolation off, cookies and localStorage persist between tests and specs. The preference set to German by the profile spec is still active when the settings spec runs.

Fix: Turn testIsolation back on (or clear cookies and localStorage in beforeEach) and set the locale explicitly in the settings spec.

## item-02 (playwright)

Root cause: locator.allTextContents() reads once and does not wait. When the test ran before the grid had mounted it got an empty list, so the regex matched an empty string.

Fix: Replace the one-shot read with the retrying assertion expect(grid.getByRole('columnheader')).toContainText([...headers in order]).

## item-03 (cypress)

Root cause: The background export legitimately takes between about 2 and 7.5 seconds, and the Cypress default command timeout of 4 seconds is shorter than the slow end of that range, so the test fails when the job is slow and passes when it is fast.

Fix: Give the download-csv lookup an explicit timeout of about 15 s (cy.get(..., { timeout: 15000 })).

## item-04 (playwright)

Root cause: Fluent renders the toast message twice: once in its screen-reader live region and once in the visible toast title. The page-wide exact getByText locator intermittently matched both elements, which is a strict mode violation.

Fix: Scope the assertion to the visible title: page.locator('.fui-ToastTitle').filter({ hasText: /^Phase 3 toast bridge$/ }).

## item-05 (cypress)

Root cause: Deleting a List widget puts 4 errors in the debugger for about 50 ms and then they clear. AssertErrorCount read the counter once because its assertion was chained after a .then(), where Cypress does not retry. On a fast runner the read came after the flash; on a slow runner it landed inside the flash.

Fix: Assert directly on the element query (GetElement(...).should('have.text', assertion)) so the check retries until the counter settles, within the default command timeout.

## item-06 (playwright)

Root cause: Both tests share a page and browser context created in beforeAll. The cart is stored in localStorage, so the item added by the first test is still there when the second test starts.

Fix: Create a fresh context and page per test (use the default fixtures instead of a beforeAll page) or clear storage in beforeEach.

## item-07 (cypress)

Root cause: The tests visited /applications while logged out, so the getAllWorkspaces request aliased by the next login command was a 401 response with no responseMeta, which processNetworkStatus then dereferenced. The working test performs logout, login page, LoginFromAPI, then /applications.

Fix: Match test 5's order (logout, login page, LoginFromAPI, then /applications), drop the redundant visits and reloads, and log test 2 in explicitly.

## item-08 (cypress)

Root cause: invoke('text') followed by .then() reads the counter once, immediately after the click, before the PATCH request returns and the UI updates. Cypress does not retry an assertion made inside .then().

Fix: Use a retrying assertion on the element (should(($el) => expect(Number($el.text())).to.equal(before - 1))) or wait on the intercepted PATCH request before reading.

## item-09 (cypress)

Root cause: The seed is stored as a local wall-clock string without a zone (the ISO string is cut to the minute). At 23:30 UTC the event is one hour later, i.e. 00:30 the next day, so the app labels it 'Tomorrow'. The behaviour depends on the hour and the zone of the machine.

Fix: Create the seed with an explicit UTC timestamp and freeze the clock with cy.clock so the label does not depend on the time of the run.

## item-10 (cypress)

Root cause: The Cancel button only exists for orders that are not delivered. The test assumes the first order is always cancellable; in a tenant whose orders are all delivered the button is never rendered.

Fix: Pick an order that is cancellable (filter by status) or create one in the test, and handle the absence of the button explicitly.

## item-11 (playwright)

Root cause: The storage state file holds a session cookie from Friday. The app's sessions expire after 72 hours, so from Monday the saved session is no longer valid and the app redirects every request to the login page.

Fix: Regenerate the storage state on every run (or when it is older than the session lifetime) in the global setup.

## item-12 (cypress)

Root cause: The page is server-rendered and the burger button is visible and actionable before Vue has attached its click handler. A click in that window is swallowed, so the drawer never opens.

Fix: Wait until the app is hydrated (for example a data-hydrated attribute set on mount) before clicking, or retry the click until the drawer is visible.

## item-13 (cypress)

Root cause: The badge is computed from both responses, but the test waits only for /api/counts and assumes /api/feed has already arrived. Which one finishes first varies.

Fix: Wait for both aliases (cy.wait(['@counts', '@feed'])) before asserting.

## item-14 (playwright)

Root cause: startGame() returned right after the click while the start mutation was still in progress, so Bob's reload could happen before the game entered its started state and left him on the stale lobby view.

Fix: Wait for Alice's galaxy URL (which is reached only after the start mutation succeeds) before startGame() returns.

## item-15 (playwright)

Root cause: On redhat-3.16 the org page mounts the Logs tab eagerly, so the hidden usage-logs table also renders the 'org/repo' text and the getByText locator resolves to three elements. Master gates the Logs fetch on the active tab, so the problem is latent there.

Fix: Use getByRole('link', { name, exact: true }) for the three repository locators and the created repo's name for the 'nowrite-repo' substring match.

## item-16 (playwright)

Root cause: openTimeline() returns after any slot is done, while the guard test counts chips across the whole document. Because the fake server randomizes response delay, whichever post finishes first decides whether the global >= 6 count holds.

Fix: Wait for the specific Scheduler-latency post's own slot to be done, scope the chip reads to that slot, and assert the deterministic 5-item Signal v2 compact result.

## item-17 (cypress)

Root cause: MarketListingsPage renders a seller block and formatListingDelivery(listing.delivery). The mock listing lacked the delivery object and the seller reputation fields, so rendering threw and the page crashed into the error boundary. In addition the price formatter was changed to print numbers without the currency symbol.

Fix: Add the delivery object and seller reputation fields (verified, ratingAvg, ratingCount, salesCount) to the mock listing and change the price assertion from '฿15,000' to '15,000'.

## item-18 (cypress)

Root cause: The login happens once, before all specs, and the cookie it sets expires after 30 minutes. By the time the audit log spec runs the session is no longer valid and the app redirects to the sign-in page.

Fix: Use cy.session (or log in in beforeEach) so each spec obtains a fresh, validated session.

## item-19 (cypress)

Root cause: The search box fires a request for each input without cancelling or ignoring the older ones. When the response to q=a arrives after the response to q=ab, it overwrites the newer result. The assertion is correct.

Fix: Cancel the previous request (AbortController) or ignore responses that do not belong to the latest query.

## item-20 (cypress)

Root cause: The body-parsing intercepts match any HTTP method on the shared /post-only URL. A request fired by the sibling test (a GET with no content-type header) can arrive after its test ended and is matched against the next test's still-registered route, so the handler sees content-type undefined. The proxy matches incoming requests only by URL and method against whichever routes are registered, with no marker of which test they came from.

Fix: Scope the three body-parsing intercepts to POST ({ method: 'POST', url: '/post-only' }) so a leaked GET can no longer match.

## item-21 (playwright)

Root cause: The inline error paragraph in PropertyEditor.svelte picked up role="alert" in a later accessibility pass. It now collides with Toast.svelte's toast under the bare role selector the script was written with.

Fix: Scope the locator to [role="alert"][class*="preset-filled"], which only Toast.svelte uses, instead of changing the inline error's (correct) role.

## item-22 (cypress)

Root cause: A portaled menu is positioned once when it opens, so closeMenuOnScroll closes it as soon as anything scrolls. With menuPosition 'absolute' react-select scrolls the page itself to make room for a menu that does not fit below the fold; that scroll event closes the menu a few milliseconds after it opened. The test was also fragile: it clicked a snapshot with force, its menu selector also matched layout icons, and it asserted nothing.

Fix: Render the select menu with menuPosition 'fixed' so react-select does not scroll the page, and rewrite the test to click the control through a data-cy hook, pick the option by text inside .react-select__menu with scrollBehavior: false, and assert the house is selected.

## item-23 (playwright)

Root cause: The test reloads immediately after clicking Save. The PATCH request is still in flight on slower runs, so the reload aborts it or reads the old profile. Nothing in the test waits for the save to finish.

Fix: Wait for the save to complete before reloading (await the PATCH response, or assert the 'Saved' toast), then reload and check the value.

## item-24 (playwright)

Root cause: The assertion is inside a try/catch that only logs, so a failing avatar check never fails the test. The upload really does not update the avatar.

Fix: Remove the try/catch so the assertion fails the test, then fix the upload flow it exposes.

## item-25 (playwright)

Root cause: The expected value was computed by hand and rounded up. 24.48 plus 12.3% tax is 27.49104, which the page correctly shows as $27.49; the test's hand-written $27.50 is simply wrong.

Fix: Correct the expected total to $27.49 (or compute it from the seeded prices and the documented tax rate).

## item-26 (playwright)

Root cause: Sub-pages rendered inside the Preferences layout contain links with the same names as the sidebar links, so the page object's page-wide link locators resolve to two elements (the sidebar link and the skill details tab).

Fix: Scope all SettingsPage sidebar link locators to the nav with aria-label 'PreferencesNavigation'.

## item-27 (playwright)

Root cause: The server-rendered trigger is visible before the client framework attaches its click handler. Under CPU contention the gap is wide enough that the first click is swallowed without any error, so the menu never opens.

Fix: A private openDropdown() helper in the page object clicks the trigger, verifies the target menu item actually appeared, and retries the click up to three times; logout(), openTokenDebug() and openManageProfile() use it.

## item-28 (cypress)

Root cause: The What's new modal is shown only once per browser profile, but the test closes it unconditionally. When it has already been dismissed (in the session of an earlier spec) the click target does not exist, and when it is shown late it covers the link.

Fix: Dismiss the modal conditionally or pre-set the 'seen' flag in localStorage before the visit, then click the navigation link.

## item-29 (cypress)

Root cause: The warm-up request to the search API returns 404 and is deliberately allowed to fail with failOnStatusCode: false without reading the response, so the real problem (the changed search URL) is never reported and only a downstream assertion fails.

Fix: Check the response status in the test (or remove failOnStatusCode: false) so the failing search call is reported, and update the search URL.

## item-30 (playwright)

Root cause: The search endpoint matches a query against the product description as well as the name since the catalogue import, so 'Standing desk' (whose description mentions a lamp holder) is returned for 'lamp'. The test's check that no non-matching product appears is correct and is now failing for a real reason.

Fix: Restrict the search to the name and tags field (or weight description matches below a threshold) and keep the negative assertion.

## item-31 (playwright)

Root cause: The earlier docs PR added a 'Portable physics joints' demo to the physics guide, which introduced a second 'Run Interactive Game' button on the same page. The test's page-wide locator was written for a page with one such button.

Fix: Scope the button to the '.cabinet-card' that contains 'Rigid-body physics playground'.

## item-32 (playwright)

Root cause: The row shows as soon as the list comes back, but the add form closes a tick later (setValue('') and setOpen(false) run after an await). React keeps the controlled input's value attribute in sync, so page.content() read in between still contains the token.

Fix: Wait for the form (getByLabel('value')) to be gone before reading page.content().

## item-33 (playwright)

Root cause: Both waitForResponse calls match the same pattern, and the test assumes the first resolved response is the stats response. Which of the two requests completes first varies, so the objects are sometimes swapped.

Fix: Wait for each response with its own distinct URL predicate and use the matching payload.

## item-34 (playwright)

Root cause: The page computes today's date in UTC while the test computes it with new Date().getDate() in the machine's local zone. In the hours when UTC and the runner/laptop zone fall on different calendar days the two disagree.

Fix: Compute the expected date in UTC in the test, or fix the browser context and test process to the same time zone (timezoneId in the Playwright config).

## item-35 (playwright)

Root cause: The banner exists only for non-paid accounts, but the spec always clicks its Dismiss button. For paid accounts there is no such button and the click times out.

Fix: Branch on the plan: only dismiss and assert when the banner is present (or assert that it is absent for paid accounts).

## item-36 (cypress)

Root cause: The test depends on a specific user record that exists in the long-lived QA database but is not created by the current seed script, so login returns 401 on fresh databases.

Fix: Create the user inside the test (API or cy.task seed) and use its credentials instead of a pre-existing record.

## item-37 (playwright)

Root cause: The cookie dialog is only rendered when no consent cookie exists. The test clicks 'Accept all' unconditionally, so with a reused browser profile the button never appears and the click waits until it times out.

Fix: Handle the conditional dialog: click 'Accept all' only when it is visible (or seed the consent cookie in the fixture) and then continue.

## item-38 (playwright)

Root cause: The waitForResponse for a successful refund is wrapped in .catch(() => {}), so the test passed although the refund request failed with HTTP 500. The empty refund list only surfaces in the following test.

Fix: Remove the catch so a failed or missing response fails the test, and assert the refund result (response status or the new row) in the same test.

## item-39 (playwright)

Root cause: The visible question is the server-rendered fallback form. React replaces its radios wholesale when it hydrates, so a Space press that lands before hydration checks a control that is then unmounted: no answer is posted and nothing errors. The spec hand-rolls its entry and so skipped the hydration wait that the shared helpers perform.

Fix: Call the exported waitForHydration(page) after the question is visible and before the first key press; keep the toPass retry for later re-renders.

## item-40 (cypress)

Root cause: Cypress appends a relative request URL to baseUrl, and baseUrl already carries the servlet context path, so the explicit JAHIA_CONTEXT prefix is applied twice. The doubled path matches no servlet, Jahia routes it to the render servlet, which reads 'custom-context' as a locale and answers 400. The plain SN entry cannot reproduce it because its context path is empty.

Fix: Request the liveness probe with a relative URL and let baseUrl supply the context path; remove the unused JAHIA_CONTEXT import.

## item-41 (playwright)

Root cause: The case-insensitive substring name /Pasta 360/i matches both the h3 'Pasta 360 Consolidada' and the h2 'Pasta 360', so the role locator resolves to two elements and Playwright's strict mode throws.

Fix: Add .first() to the heading locators and to the 'Enviar' button locator so each resolves to one element.

## item-42 (playwright)

Root cause: The test moved on to the reconciliation import right after the start toast. The backend rejects a reconciliation import while the payment is still in progress, so the dialog state was reset and the button stayed disabled.

Fix: Call the existing waitForPaymentToComplete() helper after the payment is started, and drop the redundant page-title check.

## item-43 (playwright)

Root cause: The test proxied every same-origin request, including hundreds of tile range requests, through route.fetch to add the production headers. Under CI load the preview server sometimes dropped a socket on one of those proxied requests.

Fix: Proxy only documents and scripts, where the CSP takes effect, and let every other request continue to the server; also allow one retry on CI.

## item-44 (cypress)

Root cause: The product intentionally changed the label of the status from 'Paid' to 'Settled'; the expectation in the test was not updated.

Fix: Update the expected status text to 'Settled' (or assert on a stable data attribute instead of the label).

## item-45 (playwright)

Root cause: The new chat rail renders an <li>@handle</li> row for everyone the viewer follows, so on the following page a followed user has a row in both the rail and the list. FollowListPage's unscoped listitem locator resolves to two elements. The collision appears only once the rail's follow list has been fetched.

Fix: Scope every FollowListPage locator to the page's own <main>; the rail <aside> is a sibling.

## item-46 (playwright)

Root cause: The checkbox is rendered by the server and can be ticked natively before the client code attaches the change handler. The check shows as checked, but the handler that updates the URL and the list never runs.

Fix: Wait for hydration before interacting, or use a retrying toPass block that re-checks until the URL changes.

## item-47 (cypress)

Root cause: The runs list is derived from a subscription that resolves in stages and re-renders the list as it settles. A re-render during the within() block replaces the captured card, so the nested assertions run against a detached element. The sibling test asserted before the list had resolved, so it saw the transient empty state.

Fix: Wait for a resolved run to render (cy.findByText('fix: using Git data CANCELLED').should('be.visible')) before asserting, and re-query the card for each assertion with cy.get('@firstRun').find(...) instead of holding it inside within().

## item-48 (cypress)

Root cause: The test sleeps a fixed 3 seconds and then asserts, but generation takes 1 to 6 seconds, so on slow runs only a part of the rows has arrived.

Fix: Remove the cy.wait(3000) and rely on a retrying assertion with a timeout that covers the slowest report (should('have.length', 5, { timeout: 15000 })).

## item-49 (playwright)

Root cause: After the dialog is closed it plays a ~200 ms close animation, during which its own embedded SourcePicker still has an 'Upload files' input in the DOM. Opening Sources before that finishes makes the label match two inputs.

Fix: Wait for the dialog to be hidden (expect(page.getByRole('dialog')).toBeHidden()) before opening Sources.

## item-50 (playwright)

Root cause: getByRole('heading', { name: 'Tasks' }) is a case-insensitive substring match. Once the list loads and the 'All tasks' subhead renders, it resolves to two headings (h1 'Tasks' and h2 'All tasks'), a strict mode violation. Before the load only the h1 existed, which is why it looked flaky.

Fix: Use { name: 'Tasks', exact: true } so only the h1 matches.

## item-51 (playwright)

Root cause: The Approve button is rendered only for users with the manager role. Run under the standard-user project, the logged-in user has no such button, so the click waits until it times out.

Fix: Run this spec only under the manager project (project-specific testMatch) and add a separate permission test that expects no Approve button for standard users.

## item-52 (playwright)

Root cause: The server-side export legitimately takes between about 3 and 6 seconds on the CI runner, and the assertion allows the default 5 seconds, so it fails whenever the export is slower than the budget and passes on retry when it is faster.

Fix: Give the Download PDF assertion an explicit timeout sized for the export (for example 20 s) instead of the global 5 s default.

## item-53 (cypress)

Root cause: The custom command converts any error into a false return value that the test ignores, and the final assertion checks something that is always true, so the declined payment never fails the test.

Fix: Let the command fail (remove the error handler) and assert the visible outcome, e.g. the order confirmation after a successful payment.

## item-54 (playwright)

Root cause: The test relies on an order with id 10482 that exists in the old staging data but not in a database created by migrations alone.

Fix: Create the order through the API or a seed fixture in the test and use its returned id.

## item-55 (cypress)

Root cause: The navbar's background cart request had no intercept, so it reached the backend and returned HTTP 401, and the app responded by clearing the session and redirecting to /login. Generic intercepts such as **/cart* also matched Vite source modules in dev.

Fix: Add a mock for GET **/api/v1/cart*, prefix all intercepts with **/api/v1/, and make sure the dialog entrance transition completes before typing into displayName.

## item-56 (cypress)

Root cause: The stub redirects the test's own tab to the external docs site. If that site is slow or unreachable from CI, Cypress blocks indefinitely because there is no timeout for cross-origin page loads, so the job hangs.

Fix: Stub window.open without navigating and assert that the stub was called with the expected URL (stub.firstCall.args[0]), which removes the external dependency.

## item-57 (playwright)

Root cause: The landing page is server-rendered, so the Pricing button is visible and clickable before React has attached its handlers. A click in that window is swallowed without any error, and the menu never opens.

Fix: Wait until the page is hydrated before interacting (for example wait for a hydration marker the app sets, or retry the click until the menu opens).

## item-58 (cypress)

Root cause: The spec reuses one page across tests, so the second test inherits the first test's dialog state. Reading win.frappe immediately after the visit also raced with the app boot.

Fix: Visit the page in beforeEach so each test gets a fresh page, and use cy.window().its('frappe') so Cypress retries until boot completes.

## item-59 (cypress)

Root cause: The test depends on a live third-party API; from the CI network the request is refused, so the widget never receives a forecast.

Fix: Stub the forecast request with cy.intercept and a fixture so the test does not depend on the third-party service or the network policy.

## item-60 (playwright)

Root cause: The flick was driven through the runner's mouse, so its speed depended on how fast the test runner executed each step; on slow runners it fell under the speed threshold.

Fix: Dispatch the pointer events inside the page 5 ms apart with page.evaluate, so the gesture speed no longer depends on the runner.
