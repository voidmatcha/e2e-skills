# Blind F-code mapping packet, extension ext2 (v8)

7 already-diagnosed E2E failures. For each item you see only the root-cause statement and the fix.

## item-96 (playwright)

Root cause: While a streamed page is still arriving, React parks the next segment's markup, shell included, in a hidden div until an inline script swaps it in. visit() returns at the navigation commit, so WebKit can query mid-stream and see both copies of the shell.

Fix: Scope the locator to the visible shell with .filter({ visible: true }) at all four call sites; two visible shells would still fail strict mode, so nothing is weakened.

## item-97 (playwright)

Root cause: The measurement is camera-position delta over a fixed wall-clock hold. On an overloaded host the number of rendered frames inside that hold varies and can be zero, so the two samples are not comparable.

Fix: Keep one real Shift+w keydown to prove the binding arms speedBoost, then drive the physics directly inside a single synchronous page.evaluate (set the flags, call controls.update(dt) a fixed number of times) and assert the exact 2x speed ratio.

## item-98 (playwright)

Root cause: The test clicks the first unit after a fixed 4 s wait. Under load the camera may not have finished centering on the base, so the unit sits off-screen or under a HUD panel; the mousedown never reaches the canvas and nothing is selected.

Fix: Centre the camera on the player's town centre, move the pointer to the canvas centre, poll until a unit projects onto the canvas, then stop the loop and click; assert that selectedUnits contains the clicked id.

## item-99 (playwright)

Root cause: The Ctrl+wheel of the pinch test zooms the page out to 90%, and Firefox remembers page zoom per site for the whole browser, so the next test of the same worker starts in a zoomed page where its click lands elsewhere. The state leaks from one test to the next in the same browser.

Fix: Set the Firefox user pref browser.zoom.siteSpecific to false in the project's launch options so the zoom dies with its tab.

## item-100 (playwright)

Root cause: goToCompliancePage returns as soon as the filter bar is visible, while the entry overview request can still be in flight. The test then arms a waiter that matches any overview response and changes the preset; when the entry response lands after the waiter is armed, the waiter resolves on it instead of on the request for the new preset. The application is correct.

Fix: Arm a waiter for the entry overview response before page.goto(PAGE_URL) and await it inside goToCompliancePage, so every test starts with nothing in flight and its waiter can only match its own request.

## item-101 (playwright)

Root cause: In headless Chromium a full-page capture can report a 1 x 1 window for a moment. That flips the min-width media query, so the app swaps the desktop editor for the phone editor and back; the new desktop editor opens on its default Fabrics tab, where no round-trip panel exists, and the locator waits for a panel that never returns.

Fix: Wait for the Pattern tab to settle, measure the panel in one evaluate before any capture, and record it with a viewport capture (which never captures beyond the viewport) instead of a full-page screenshot.

## item-102 (playwright)

Root cause: Under load the form can still be loading, and can remount once its values arrive, when the network is cut. The remount resets the checkbox, so Save has nothing to save offline and the offline alert never shows.

Fix: Wait for the checkbox to be visible and the loading text to be hidden before going offline, and assert toBeChecked after checking it and before pressing Save.
