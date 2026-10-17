# Blind F-code mapping packet, extension (v8)

35 already-diagnosed E2E failures. For each item you see only the root-cause statement and the fix.

## item-61 (playwright)

Root cause: Navigations run in a transition, so the URL changes while the previous page, which links to its PR three times, is still on screen. The test waited for the URL and not for the new page, so the click can run against the old page and match several links.

Fix: After the URL assertion, wait for the review page's heading: expect(page.getByRole('heading', { level: 1 })).toHaveText('review:4').

## item-62 (playwright)

Root cause: The status the test waits for was saved by the first sync and is visible right after the reload, before the new recipes and the photo have reached the device. The test therefore went offline too early.

Fix: Before going offline, wait for the links to both recipes and poll the 'photos' cache until it holds one entry, then wait for the offline status.

## item-63 (cypress)

Root cause: The host name s3.localhost can resolve to the IPv6 loopback, while LocalStack listens only on the IPv4 loopback. When the browser picks the wrong address the redirected request gets an empty response, and the download never completes.

Fix: Map s3.localhost to 127.0.0.1 with the Cypress hosts setting so redirected downloads reach the IPv4 loopback endpoint.

## item-64 (playwright)

Root cause: The fixture socket server has no error handler on accepted sockets. When the app resets a subscription, which happens often on a loaded runner, a later write raises EPIPE or ECONNRESET as an unhandled error that Playwright attributes to the running test.

Fix: Add socket.on('error', () => socket.destroy()) so the reset connection is dropped instead of surfacing as an unhandled error.

## item-65 (playwright)

Root cause: The text= selector matches by substring, and the phrase Perjanjian Kinerja appears in several places on the page (headings, card titles, menu labels). The locator was never specific enough to name one element.

Fix: Use exact, specific text locators: page.getByText('Perjanjian Kinerja (PK)', { exact: true }) and page.getByText('Evaluasi & Perilaku SAFTI', { exact: true }).

## item-66 (cypress)

Root cause: The command closes and reopens the dropdown immediately before asserting on an option. Every open re-fetches the pollers and clears them on close, so the click on the option races that fetch: fine locally, occasionally too slow under CI load.

Fix: Intercept GET /configuration/monitoring-servers as @getPollers (also in 05-ACC-check-permissions), open the dropdown once and cy.wait('@getPollers') before clicking the option; remove the stray double click.

## item-67 (playwright)

Root cause: getByRole('button') matches every button on the page. When the Next.js dev server's own Dev Tools button has rendered by the time of the click, the locator resolves to two elements; when it renders later the test passes. The click is on an unscoped locator, and the filter is applied only to the wait.

Fix: Name the counter button: getByRole('button', { name: /\d$/ }), since its name always ends in its count and the Dev Tools button's does not.

## item-68 (playwright)

Root cause: The sidebar change added a plus link named New session to each group, so the project home's quick action of the same name is no longer the only match. The page-wide locator was written before the sidebar link existed.

Fix: Scope the locator to the project home region: page.getByTestId('project-home').getByRole('link', { name: 'New session', exact: true }).

## item-69 (playwright)

Root cause: The last alternative of the selector, main ol li, also matches the ten footnotes of the collapsed All metrics block. The feed renders after the names request ends, and network idle can return before that, so until then .first() resolves to a footnote far below the feed. The test then clicks and measures a different element than the one it means.

Fix: Remove the main ol li alternative so the selector matches only feed rows; Playwright then waits until the feed exists.

## item-70 (playwright)

Root cause: The filter settles per input sample, not per millisecond. A fixed 800 ms of wall clock is enough on a fast browser but, on a loaded CI browser that runs fewer simulation ticks in that time, leaves the steer short of its target when the value is read.

Fix: Wait for 60 simulation ticks (about a second of game time) with page.waitForFunction on the game's tick counter instead of waitForTimeout(800); keep the assertion and tolerance.

## item-71 (cypress)

Root cause: Each refetch of the services table gives every row a new generated id, so the rows are replaced. The test can match 6.42 from an earlier fetch and grab the button just before a later fetch replaces its row, and this Cypress version does not re-query detached elements.

Fix: Wait for the table's loading class (euiBasicTable-loading or ouiBasicTable-loading) to be absent before finding and clicking the flyout button.

## item-72 (playwright)

Root cause: After a Tab press the focus can briefly be on nothing or on the body. Reading innerText of the :focus locator then waits for an element until the test timeout, and a slower runner needs more than eight Tab presses to reach the button.

Fix: Raise the traversal budget to twelve presses, skip iterations where nothing or BODY has focus, and read the text with a short 250 ms timeout and a fallback.

## item-73 (playwright)

Root cause: The hero headline was renamed in the page component and the spec still asserts the old wording, so the locator finds nothing. The product behaves correctly; the assertion is stale.

Fix: Assert the current headline with a role-based locator: getByRole('heading', { level: 1, name: 'Close your Stellar account' }).

## item-74 (playwright)

Root cause: The toast from step B is still on screen when step C triggers its own, so the page-wide text locator matches both. Step C would also pass on B's stale toast if it used .last(). The run depends on whether B's toast auto-dismissed before C ran.

Fix: End step B by asserting that its toast is hidden, so step C's assertion proves that its own toast appeared.

## item-75 (playwright)

Root cause: The hero re-measures from a resize listener that the page runs on a frame after setViewportSize has returned. The test slept a fixed 100 ms and read the height; on a slow runner the listener has not run yet and the old pin is still in place.

Fix: Register a one-shot resize listener (plus a frame) before resizing and await it instead of sleeping; use the same signal in the touch case that asserts nothing changes.

## item-76 (cypress)

Root cause: The intercept is registered after the visit, so it can miss the app's own on-mount fetch, and the test waits only for the attribute request, not for the tiers request. Save can run its validation before the attribute list has loaded and fail.

Fix: Register both intercepts (@attrGet and @tiersGet) before cy.visit() and cy.wait(['@attrGet', '@tiersGet']) before touching the form.

## item-77 (playwright)

Root cause: The new footer newsletter input has aria-label Email address, and getByLabel('Email') matches by substring, so the join form's lookup now resolves to two inputs. The author did not rerun the smoke tests after adding the field.

Fix: Scope the lookup to the main landmark: page.getByRole('main').getByLabel('Email'), which the footer is outside of.

## item-78 (playwright)

Root cause: The first-slide disabled state of Previous is baked into the server-rendered HTML, so the assertion used as the readiness signal passes before the carousel library's dynamic import has resolved and wired its click handlers. A click in that window does nothing and Previous stays disabled.

Fix: Retry the click until Previous becomes enabled with expect(async () => { await nextBtn.click(); await expect(prevBtn).not.toBeDisabled({ timeout: 500 }) }).toPass(); remove the fixed 300 ms sleeps.

## item-79 (playwright)

Root cause: After the mark-done, the old row stays on screen while it animates out and the done row is already there, so for a short window two rows contain the same title. The click runs inside that window and the locator matches both.

Fix: Before the click, wait for the done row to appear (done-toggle[aria-checked="true"] count 1) and then for the open-list row to leave (the row locator count 1), then click.

## item-80 (cypress)

Root cause: When Cypress has located a radio input and is waiting for it to become actionable, an update in flight or a late pricing response replaces that element, so the subject is detached and the click times out. Queueing the updates changed the timing of the re-renders relative to the test.

Fix: Assert the dialog is visible and the updating message is gone before interacting, split the chained get/should/click into separate commands so Cypress re-queries, wait for pricing, click with force, and check the updating message is gone again afterwards.

## item-81 (playwright)

Root cause: The Sales room replaced the filtered order report: order-filter-status, reports-content and reports-print-button no longer exist, and Free is no longer behind an upgrade overlay. The spec still describes the old screen.

Fix: Rewrite the checks for the new test ids (scope chips, period cards, the hero print button), replace the two overlay checks with one that expects the day report and no upgrade title, and remove the five quarantine entries.

## item-82 (playwright)

Root cause: While Settings is still streaming and hydrating, the page briefly holds two Appearance labels, only one of them inside main. A strict mode violation fails the expect at once instead of retrying, so a poll that lands in that window ends the test after about 400 ms. Once loading finishes only one label is visible.

Fix: Scope both readiness checks to main: getByRole('main').getByText('Appearance'), which targets the copy that becomes visible.

## item-83 (playwright)

Root cause: axe computes contrast from resolved styles. When the scan runs before the first paint has settled it cannot resolve an element's background and substitutes #c0c0c0, which is a sign that it ran too early rather than that a contrast defect exists.

Fix: Before scanning, wait for the page's own first heading, document.fonts.ready and two animation frames, rather than for a duration.

## item-84 (playwright)

Root cause: The test clicks sign out and immediately calls sign in. signIn sees a URL that is not /login yet and navigates to /login while the sign-out action is still in flight; the navigation cancels the action, so the cookie is never cleared and /login redirects the still-signed-in browser home. The login form never renders.

Fix: Add a signOut helper that clicks sign out and then waits for /login and the login form; make signIn assert that it actually reached /login; use the helper at all three sign-out sites.

## item-85 (playwright)

Root cause: initSurvey unmounts the old React root synchronously and schedules the new render asynchronously. Pressing Tab right after it returns hits an empty #surveyElement, so focus is never established and the following arrow and Enter keys go nowhere.

Fix: Wait for the first .sd-dropdown to be visible after initSurvey before any keyboard input (and replace the later fixed 100 ms wait with an assertion that the popup is hidden).

## item-86 (playwright)

Root cause: The edit key (function key 2) mounts the cell editor empty and fetches the cell's input from the worker asynchronously. Edits made while that prefill is pending are held and replayed onto the prefilled value, so fill() queued before the prefill landed ends up appended after it: 'initial' plus 'typed before proposal'. The ordering barrier itself held; only the draft text was wrong.

Fix: After the edit key, wait for the editor to have the prefilled value: expect(editor).toHaveValue('initial'), then fill as before.

## item-87 (playwright)

Root cause: The page object was changed to match the current client's single-line input. Released clients still render the access token as a textarea, so the shared locator finds nothing on them and fill waits until the test ends.

Fix: Let the locator match either element: '.e2e-accessToken input, .e2e-accessToken textarea'. Each client renders exactly one, so strict mode still holds.

## item-88 (playwright)

Root cause: The editor starts with a 600x600 canvas and places the first text relative to it. The portrait template then loads and the canvas narrows, so the test's later click at a quarter of the width misses the first text. The test clicked Add Text before the template image had loaded.

Fix: Poll the editor canvas's bounding box and wait until its width is below 600 (the narrowed portrait canvas) before adding text.

## item-89 (playwright)

Root cause: The component page's link to the documentation is now labeled View TechDocs. The test still looks for a link whose accessible name is TechDocs, so the wait runs out.

Fix: Update the locator to the current label: page.getByRole('link', { name: 'View TechDocs' }).

## item-90 (cypress)

Root cause: The violations page polls the server every 5 seconds. When the test reaches the sort click at about 4 seconds, the poll fires at 5 seconds and its response, sorted by violation time, is intercepted by interactAndWaitForViolationsResponses before the sort-click response arrives. The assertion then runs on time-sorted data. The race existed since polling was introduced; the extra page content only moved the test into that window.

Fix: Freeze setInterval at the start of the test with cy.clock(Date.now(), ['setInterval']) so the poll cannot fire during the test.

## item-91 (playwright)

Root cause: The Vite dev server transforms modules on first request. With four workers opening the app at once on a cold server, the first tests spend most of their 30 s budget loading the page, so a later short step crosses the limit.

Fix: Add a Playwright globalSetup that loads the harness page once in Chromium and WebKit until network idle before any test runs, without raising any timeout or adding retries.

## item-92 (playwright)

Root cause: getByRole('heading', { name: 'Billing' }) matches by substring. The new Billing details h2 also contains the word Billing, so the locator now finds both the page's h1 and the new h2. The locator was written for a page with one such heading.

Fix: Match the h1 exactly: getByRole('heading', { level: 1, name: 'Billing', exact: true }).

## item-93 (playwright)

Root cause: The helper decides between single-element and multi-element checks from one count taken the moment the block is visible. A frontend can add a second element for the block later, so the count says one while the following single-element checks meet two.

Fix: Count with a new settledCount helper that reads until three consecutive reads agree, and use it in the branch condition.

## item-94 (cypress)

Root cause: Adding a subtask makes the panel re-read its data, and while it does the whole form is swapped for a loading line. The command types the next title right after clicking add, so on a slower machine Cypress grabs an input that is already on its way out and finds it disabled.

Fix: After each add, wait for the subtask to appear in the list and for the input to come back empty ('.subtask-input' should have value ''), and drop the fixed cy.wait(300).

## item-95 (playwright)

Root cause: The menu item's accessible name contains the binding subtitle in addition to the role title. An exact name match against the title alone can therefore never succeed.

Fix: Select the radio menu item that contains the exact visible title: getByRole('menuitemradio').filter({ has: page.getByText(roleName, { exact: true }) }).
