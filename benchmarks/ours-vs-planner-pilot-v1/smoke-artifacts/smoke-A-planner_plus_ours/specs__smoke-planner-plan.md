# Smoke Planner Plan Deltas

## Application Overview

Delta-only hardening notes for Scenario 1 (Application shell loads with primary navigation) on http://localhost:5174/. This is not a full test plan; it augments an existing draft with live-observed evidence, inferences, verification conditions, and limitations. No scope changes proposed.

## Test Scenarios

### 1. Deltas

**Seed:** `e2e/seed.spec.ts`

#### 1.1. Delta notes for Scenario 1

**File:** `specs/smoke-planner-plan.md`

**Steps:**
  1. observed | (browser_navigate result) Nav landmark 'Main' and h1 'Playwright Chat Lab' both present in the very first snapshot after page.goto resolves
    - expect: No visible flash/reorder observable via snapshot timing; treat as same-paint, not proven pre-hydration state
  2. inference | React SPA renders nav and header from the same top-level component tree
    - expect: No separate async fetch gates the nav; only the chat message list depends on the failing localhost:3001 fetch
  3. verification condition | Use getByRole('navigation', { name: 'Main' }) visible AND getByRole('heading', { level: 1, name: 'Playwright Chat Lab' }) visible as settled-state gate
    - expect: Both are visible together; no additional hydration signal found or needed
  4. limitation | Could not empirically prove zero frame where nav is absent/empty before hydration
    - expect: Residual risk is low but unverified; snapshot tool cannot capture pre-JS paint
  5. observed | (browser_evaluate) document.querySelectorAll('nav').length === 1 on /
    - expect: Nav accessible name 'Main' is unambiguous; exactly one navigation landmark exists
  6. observed | (browser_evaluate) link textContent values are exactly 'Chat', 'Search', 'Message history', 'Playground', 'Help'
    - expect: No whitespace/icon-text pollution; ordered-text assertion is safe as drafted
  7. observed | (browser_evaluate) aria-current='page' set only on the Chat link
    - expect: Does not alter accessible name/text; safe to ignore for text-order assertion, could be added as bonus check
  8. observed | (browser_navigate snapshot) role+name locators clean and stable; data-testid attributes also present as fallback
    - expect: No evidence favors testid over role+name for this page since role+name already works without ambiguity
  9. observed | (browser_navigate snapshot) A second 'Help' element exists: button 'Help' (ref e26) unrelated to nav, distinct role from nav link 'Help'
    - expect: getByRole('link', { name: 'Help' }) remains unambiguous; role-less text locators like getByText('Help') would be a strict-mode hazard — scope all link assertions to the nav landmark
  10. verification condition | Falsification probe: assert nav.getByRole('link') count === 5
    - expect: Fails if a 6th link is ever injected (e.g. future 'Settings' link)
  11. verification condition | Falsification probe: assert nav link texts equal exact array in order
    - expect: Fails on reorder, rename, or added icon/text prefix
  12. observed | (browser_navigate events log) Two ERR_CONNECTION_REFUSED console errors for http://localhost:3001/api/messages occur on every load
    - expect: Do not block or delay rendering of header/nav; non-flaky for this scenario's assertions, but would cause false failures if test asserts 'no console errors'
  13. limitation | Did not test theme-switcher (Aurora/Test Runner buttons) interaction since scope is frozen to read-only observation of /
    - expect: Cannot confirm nav is unaffected by theme changes; per scope this must not be probed
  14. limitation | Google Fonts stylesheet (fonts.googleapis.com) network dependency noted via inference, not re-verified live this session
    - expect: Could add latency/flakiness in offline CI; recommend not waiting on networkidle, rely on role-based assertions instead
