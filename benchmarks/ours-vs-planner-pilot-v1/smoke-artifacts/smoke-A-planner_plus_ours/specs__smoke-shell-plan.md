# Smoke Shell Plan Deltas

## Application Overview

AUXILIARY PLAN-HARDENING output. Scope is FROZEN to exactly one scenario, read-only, route `/` only, on http://localhost:5176. No new scenarios, no writes, no off-origin navigation. This document supplies plan deltas (locators, acceptance criteria, readiness gate, state-transition guard) for that single scenario only.

### Observed role/name/state mapping (live, resolved this session via browser_navigate + browser_evaluate on http://localhost:5176/)

| Role | Accessible name | Visible | Enabled/State | Notes |
|---|---|---|---|---|
| navigation | "Main" (aria-label="Main", tag=NAV, class="app-nav") | yes | n/a | The primary navigation container |
| link (in nav) | "Chat" (href="/") | yes | aria-current="page" | Default/active route on load |
| link (in nav) | "Search" (href="/search") | yes | no aria-current | |
| link (in nav) | "Message history" (href="/history") | yes | no aria-current | |
| link (in nav) | "Playground" (href="/playground") | yes | no aria-current | |
| link (in nav) | "Help" (href="/help") | yes | no aria-current | |
| banner | (contains heading + button) | yes | n/a | role="banner" wraps app header |
| button | "Go to the chat screen" | yes | enabled | Inside banner |
| heading (level 1) | "Playwright Chat Lab" | yes | n/a | App title, inside banner |

Evidence: `observed` — resolved live via `browser_navigate` to http://localhost:5176/ and `browser_evaluate` querying `document.querySelector('nav')` and its child `<a>` elements; snapshot also independently confirmed the same 5 links and roles.

Also `observed` live via `browser_network_requests`: two `GET http://localhost:3001/api/messages` requests appear with no successful status (console shows `net::ERR_CONNECTION_REFUSED` for both) — this is the expected-down backend mentioned in the task and must NOT be treated as a load failure.


## Test Scenarios

### 1. Smoke - Application Shell (frozen scope, deltas only)

**Seed:** `e2e/seed.spec.ts`

#### 1.1. Scenario 1: Application shell loads with primary navigation

**File:** `specs/smoke-shell.spec.ts`

**Steps:**
  1. [unchanged from frozen scope] Given the application is served at http://localhost:5176, when a user opens `/`, then the application shell loads and the primary navigation is visible. Navigate to http://localhost:5176/ from a fresh/blank browser context (no auth, no prior state).
    - expect: [observed] Page loads with title 'Playwright Chat Lab'; DOM contains a <nav aria-label="Main" class="app-nav"> element with 5 child links.
    - expect: [observed] Two GET requests to http://localhost:3001/api/messages fail with net::ERR_CONNECTION_REFUSED (backend intentionally down per task instructions) — this must be treated as an EXPECTED, ignorable console/network error, not a test failure.
  2. DELTA 1 (locator, observed): Use `page.getByRole('navigation', { name: 'Main' })` as the primary-navigation locator. For tab items, use `page.getByRole('navigation', { name: 'Main' }).getByRole('link')`, which live-resolves to exactly 5 items in this order: 'Chat' (href=/), 'Search' (href=/search), 'Message history' (href=/history), 'Playground' (href=/playground), 'Help' (href=/help).
    - expect: [observed] Locator `page.getByRole('navigation', { name: 'Main' })` resolves to exactly one element live.
    - expect: [observed] Locator `.getByRole('link')` under it resolves to exactly 5 elements live, with the accessible names listed above, all visible (offsetWidth/offsetHeight/getClientRects confirmed non-empty).
  3. DELTA 2 (acceptance criteria / failure conditions, verification condition): Define the smoke test as load-bearing rather than vacuous by asserting on concrete, resolved values rather than mere presence.
    - expect: [verification condition] PASS requires ALL of: (a) `page.getByRole('navigation', { name: 'Main' })` is visible; (b) it contains exactly 5 links with the exact accessible names listed in the observed table, in that order; (c) each link has the exact href listed; (d) the 'Chat' link has `aria-current="page"` (confirms the shell rendered the correct default route, not a blank/error shell); (e) `page.getByRole('heading', { level: 1, name: 'Playwright Chat Lab' })` is visible (confirms the app shell/banner rendered, not just the nav in isolation).
    - expect: [verification condition] FAIL conditions that must be distinguished from the expected backend-down noise: (a) nav locator count is 0 or not exactly 5 links; (b) any nav link text/href/order differs from the observed table (indicates shell mis-render or unrelated regression); (c) page title is empty or an error page renders instead of 'Playwright Chat Lab'; (d) a JS console error occurs that is NOT the whitelisted `net::ERR_CONNECTION_REFUSED @ http://localhost:3001/api/messages`.
    - expect: [verification condition] The test must explicitly allow/ignore the two known `http://localhost:3001/api/messages` connection-refused failures (e.g. via an explicit console/network filter) so the smoke test does not flake or false-fail on the known-down dependency, while still failing on any *other* unexpected console error or network 4xx/5xx from the app's own origin (localhost:5176).
  4. DELTA 3 (readiness/settled-state gate, observed + verification condition): Do NOT gate the assertion on Playwright's default `networkidle` wait or on the `/api/messages` request settling, since that request never resolves successfully in this environment (observed: ERR_CONNECTION_REFUSED, connection never completes) and networkidle-style waits would time out or produce false negatives.
    - expect: [observed] Live network trace shows the `/api/messages` GET requests never reach a resolved (2xx/4xx/5xx) state — they fail at the connection layer, so any 'wait for network idle' style gate is unsafe for this app.
    - expect: [verification condition] Instead, gate readiness on a DOM-visibility condition local to the shell itself, e.g. `await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible()` and/or `await expect(page.getByRole('heading', { name: 'Playwright Chat Lab' })).toBeVisible()`, each with Playwright's built-in auto-retry, before asserting on the link list. This avoids racing hydration without depending on the down backend.
  5. DELTA 4 (state-transition / read-only guard, verification condition, read-only — no navigation performed): Assert the initial rendered state is the default 'Chat' route and that the page remains read-only/idle after shell load, without clicking any nav item or submitting anything (frozen scope forbids navigating off `/` or performing writes).
    - expect: [observed] On initial load of `/`, the 'Chat' nav link already carries `aria-current="page"`, confirming the shell resolves to a default active tab state without requiring any user interaction.
    - expect: [verification condition] Assert no outgoing POST/PUT/PATCH/DELETE network requests occur during initial shell load (only GET requests to /api/messages and the static asset GETs were observed live), confirming the load is read-only as required by frozen scope.
    - expect: [limitation] Clicking through the other nav tabs ('Search', 'Message history', 'Playground', 'Help') to verify they each load their own shell was NOT performed and is explicitly OUT OF SCOPE for this frozen single-scenario plan. Any such addition would increase scenario count / change tested behavior and must be returned to an approval gate before being added — it is NOT applied here.
