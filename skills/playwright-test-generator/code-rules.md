# Code Generation Rules

## Hard rules (always)

Non-negotiable for every generated spec, regardless of project shape:

- **`await` everything** — every `expect()` on a Locator and every Playwright action (`.click()`, `.fill()`, `.press()`, `.check()`, `.selectOption()`, `.hover()`). A missing `await` silently skips the assertion or action.
- **Web-first assertions only** — `toBeVisible()`, `toHaveText()`, `toHaveURL()`, etc. Never `expect(await el.isVisible()).toBe(true)` (resolves once, no retry).
- **Stub all writes** — signup, login, payment, any mutation goes through `page.route()`. A generated test never mutates real shared backend data.
- **Gate hydration** — on SSR/SSG apps, gate the first interaction on a hydration signal, never `waitForTimeout()` after `goto`.
- **One hard `expect()` per test** — a test built only from `expect.soft()` never fails early.

## Structure Detection

| What you find | What to generate |
|---------------|-----------------|
| POM directory exists, no POM for this page | New POM class (extends `BasePage` if present) + spec file |
| POM directory exists, POM for this page already exists | Extend existing POM — add new locators only + new spec file |
| No POM directory anywhere | Flat spec file only |

**Extending an existing POM:** Read the file first. Match its existing naming and structural patterns — even if they differ from the rules below. Apply rules below only to newly added code.

---

## Selector Priority (best → worst)

1. `getByRole('button', { name: 'Submit' })` — role + accessible name
2. `getByLabel('Email')` — form label — **only when the label/aria-label actually exists**; verify in the Step 3 snapshot before using
3. `getByPlaceholder('Email')` — for label-less inputs (placeholder/title only). Common in real-world apps; `getByLabel` on these matches nothing and the test dies in `beforeEach`
4. `getByTestId('submit-btn')` / `[data-testid="submit-btn"]` — explicit test hook
5. `getByText('Save')` / `.filter({ hasText: 'text' })` — visible text
6. attribute selector `[formControlName="email"]` — stable attribute
7. CSS class — **POM files only**, stable structural classes only (not styling classes)
8. `.nth()` / `.first()` / `.last()` — **forbidden** without `// JUSTIFIED:` on the line above

**Project-configured test ids rank with role+name.** When `playwright.config.*` sets `use: { testIdAttribute: '...' }`, or `data-testid` (or the project's equivalent) is pervasive in the components under test, treat `getByTestId` as a **tier-1 locator alongside role+name** — not #4. A deliberate, stable test hook beats reaching past it for brittle text/placeholder locators. Keep `getByText`/`getByPlaceholder` as the fallback when no role or test id fits.

Never use XPath. Never use CSS class chains that couple to styling.

---

## POM Rules (new files only)

```typescript
import { Page, Locator } from '@playwright/test';

export class LoginPage {
  readonly form: {
    emailInput: Locator;
    passwordInput: Locator;
    submitButton: Locator;
  };
  readonly errorMessage: Locator;

  constructor(private page: Page) {
    this.form = {
      emailInput: page.getByLabel('Email'),
      passwordInput: page.getByLabel('Password'),
      submitButton: page.getByRole('button', { name: 'Sign in' }),
    };
    this.errorMessage = page.getByText('Invalid credentials');
  }

  async navigate() {
    await this.page.goto('/login');
  }
}
```

- `readonly` locators only — no getter methods
- Composition pattern: group related locators into named objects
- `navigate()` uses `page.goto(path)` unless a custom navigation utility exists in the project

---

## Spec Rules

```typescript
import { test, expect } from '@playwright/test';
import { LoginPage } from '../models/login-page';

test.describe('Login', () => {
  let loginPage: LoginPage;

  test.beforeEach(async ({ page }) => {
    loginPage = new LoginPage(page);
    await loginPage.navigate();
  });

  test('should sign in with valid credentials', async ({ page }) => {
    // Given: user is on the login page (handled by beforeEach)

    // When: user fills in valid credentials and submits
    await loginPage.form.emailInput.fill(process.env.TEST_USER!);
    await loginPage.form.passwordInput.fill(process.env.TEST_PASSWORD!);
    await loginPage.form.submitButton.click();

    // Then: user is redirected to the dashboard
    await expect(page).toHaveURL('/dashboard');
  });

  test('should show error for invalid credentials', async () => {
    // Given: user is on the login page

    // When: user submits invalid credentials
    await loginPage.form.emailInput.fill('nonexistent@test.invalid');
    await loginPage.form.passwordInput.fill('wrongpassword');
    await loginPage.form.submitButton.click();

    // Then: error message is shown
    await expect(loginPage.errorMessage).toBeVisible();
  });
});
```

- BDD comments: `// Given:`, `// When:`, `// Then:`
- Each test fully independent — own storage, session, cookies
- `beforeEach` for shared navigation setup only — never for shared state
- Mock external APIs with Playwright Network API; do not call real third-party services
- **Auto-waiting assertions only:** `toBeVisible()`, `toBeHidden()`, `toHaveText()`, `toContainText()`, `toHaveCount()`, `toHaveURL()`
- Use `expect.soft()` for independent, non-critical checks — but ensure at least one hard `expect()` gates on the primary condition per test. A test with only `expect.soft()` assertions never fails early.

**Forbidden:**

| Forbidden | Use instead |
|-----------|-------------|
| `waitForTimeout(N)` | `await expect(el).toBeVisible({ timeout: N })` |
| `expect(await el.isVisible()).toBe(true)` | `await expect(el).toBeVisible()` |
| `const n = await el.count()` | `await expect(el).toHaveCount(N)` or `.first()` + `toBeVisible()` |
| `toBeAttached()` | `toBeVisible()` — `toBeAttached` is vacuous on always-rendered elements Negative `not.toBeAttached()` and checks on dynamically-injected elements are acceptable (matches e2e-reviewer 4.1). |
| `expect(locator).toBeTruthy()` | `await expect(locator).toBeVisible()` — Locator is always a truthy JS object |
| `page.click(selector)` / `page.fill(selector, v)` | `page.locator(selector).click()` / `.fill(v)` — locator-first actions are easier to compose and review |
| `{ force: true }` | Fix the root cause (element not actionable); if unavoidable, add `// JUSTIFIED:` |
| `waitUntil: 'networkidle'` | `waitUntil: 'domcontentloaded'` or condition-based wait — unreliable on SPAs |
| `expect(page.url()).toContain(x)` | `await expect(page).toHaveURL(x)` — one-shot, no retry |
| Framework component selectors in spec (`app-button`, `my-component`) | POM only |
| XPath selectors | `getByRole` / `getByLabel` / `getByTestId` |

**Await rule:** Every `expect()` on a Locator and every Playwright action (`.click()`, `.fill()`, `.type()`, `.press()`, `.check()`, `.selectOption()`, `.hover()`) **must** be `await`ed. Missing `await` silently skips the assertion or action.

---

## Network Determinism

Decide per endpoint, not per suite:

| Traffic | Strategy |
|---------|----------|
| **Writes / credential paths** (signup, login, payment, any mutation) | **Always stub** with `page.route()`. A generated test must never create real accounts, hit real payment providers, or mutate shared backend data — data pollution, rate-limit flakiness, and PII exposure in third-party logs are all silent until they aren't. |
| Stable first-party reads | Real backend acceptable when responses are deterministic enough to assert on |
| Third-party services | Always stub (also covered by Spec Rules above) |
| Real-backend smoke | At most one small, clearly named smoke spec may exercise the real backend end-to-end (e.g. a throwaway guest session) — keep it isolated |

When the app funnels API calls through a proxy endpoint (e.g. `/api/request?cmd=<path>`), write ONE shared route-mock helper that matches on the decoded routing parameter and exposes response builders — not per-test `page.route()` calls with duplicated URL parsing:

```typescript
// helpers/mockApi.ts — match on the decoded routing param; unlisted calls fall through
await page.route('**/api/request?**', route => {
  const cmd = decodeCmd(route.request().url());
  const hit = map[cmd];
  return hit
    ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(hit) })
    : route.continue();
});
```

Fall-through (`route.continue()`) keeps reads real, but it means **a misspelled key silently leaks a write to the real backend** — list every write endpoint explicitly, and record that requirement in the project's conventions doc (Step 5b).

**The mock layer is decided by where the call originates, not just the URL.** `page.route()` only intercepts requests the *browser* makes. Calls issued server-side — Next.js SSR/RSC, route handlers, a BFF, `getServerSideProps` — never pass through the browser, so a `page.route()` mock silently misses them and the test hits the real backend (the same root cause as the cookie note under Auth & Session). For server-originated traffic, mock at a server-side seam instead: an E2E-only env var that flips the server's fetch boundary to fixed responses (`process.env.E2E_MOCK` → return canned payloads), or the project's existing test double. Detect the origin before choosing: if the data appears in the initial SSR HTML (view-source), it's a server call and `page.route()` won't help.

**Request-aware rules.** When the same endpoint must answer differently by method or parameters (tab filters, pagination pages, POST toggles), extend the helper with an ordered rule list instead of sprinkling conditional logic in specs:

```typescript
type MockRule = {
  when?: { method?: string; params?: Record<string, string> };
  response: { status?: number; body: unknown };
};
// map value: single response (back-compat) OR MockRule[] — first match wins.
// params compare only the listed keys: URL query for GET/DELETE,
// urlencoded body for POST (body value wins if a key exists in both).
```

Two hard rules learned from production use:

- **A registered-but-unmatched rule array must NOT fall through to the network.** If the cmd is in the map but no rule matches, answer with an empty success + a loud warning that includes the method and params — a param typo (`liked: 'True'`) must surface as a warning, never as a real-backend write.
- Pagination contracts become testable with a `start`/`offset` param rule per page: seed page 1 at exactly the page size (a short page often sets an internal "loaded end" flag that suppresses the next request), then assert the page-2 item appears after scroll *and* a page-1 item is still attached (append, not replace).
- **Before narrowing a rule with `when.params`, prove the app actually sends that param at that point in time — wire evidence, not source intent.** A component that reads `router.query` in a first-render `useRef`/initializer fires its initial fetch during hydration, before `router.isReady`, so the query param is silently dropped from the wire even though the source clearly "passes" it. A param-narrowed rule then never matches, the strict fallback answers empty, and a previously-green render test fails for a contract the app never honors. If the param is best-effort in practice, keep the broad rule and record the WHY as a comment citing the file:line of the early read.

**Prove the call, not just the pixels.** For write interactions with optimistic UI (like toggles, deletes), the UI updates before — and regardless of — the request. Pair every such assertion with request proof:

```typescript
const call = page.waitForRequest(r => r.method() === 'POST' && r.url().includes('cmd=%2Fv2%2Fuser%2Fsentence%2Flike'));
await likeToggle.click();
await call; // without this line the test passes even if the wiring to the API is deleted
await expect(likeToggle).toHaveAttribute('aria-pressed', 'true');
```

**…but prove the call HAPPENS before asserting it (the inverse trap).** "Prove the call" only applies to calls the app actually makes at runtime. Unmount-cleanup API calls are the canonical counterexample: an empty-deps effect's cleanup captures its guard variables as a stale closure from mount time — if the guard (e.g. a `quizSetId` that arrives with the fetch response) was empty at mount, the cleanup's `if (id) api.cancel(id)` is a dead path forever, even though the source reads as an obvious contract. A `waitForRequest` assertion on such a call times out against correct test code. Before shipping a call-proof assertion on exit/unmount/cleanup paths, verify the request fires at least once (solo run, network log); if it never does, assert the user-visible outcome instead, file the stale closure as an app defect, and leave a comment with the file:line so the proof can be added when the defect is fixed.

---

## SSR & Hydration

- **Gate the first interaction on hydration for server-rendered apps** (Next.js, Nuxt, SvelteKit, Astro, Remix). SSR paints interactive-looking elements before the framework attaches event listeners; Playwright's actionability checks pass against that inert DOM, so the first click is reported successful but does nothing and the spec fails at the *next* assertion — intermittently, because hydration sometimes wins the race. Detect SSR from the framework config/`package.json` before generating.
- Preferred gate, in order:
  1. An app-provided hydration marker: `await expect(page.locator('html[data-hydrated]')).toBeAttached();` — if the app exposes none, propose the one-line marker upstream (set an attribute in a root `useEffect`/`onMounted`); it fixes every spec at once.
  2. A self-verifying first action: `await expect(async () => { await button.click(); await expect(dialog).toBeVisible({ timeout: 1000 }); }).toPass();` — retries the click until it lands.
- Never `page.waitForTimeout()` after `goto` as a hydration guard — it's the #9 band-aid the reviewer flags, and it still races on slow CI.
- Nuance: Qwik apps are resumable, not hydrated — no page-global gate needed. Island frameworks (Astro) hydrate per-island according to their `client:*` directive — gate on the specific island's readiness (its own marker or a self-verifying action on that island), not a page-global signal.

---

## Auth & Session

- Authenticate **once**, programmatically (API-login helper or a `setup` project), persist with `storageState`, reuse it in specs that need a session. UI-driven login belongs only in specs that test the login flow itself.
- Never hard-depend on a **manually captured** session file — a locally generated `auth/*.json` that a fresh clone or CI won't have, and that silently expires. Generated tests must be able to recreate their session from code.
- Logged-out scenarios use a fresh context (no `storageState`) — don't "log out first" inside a test.
- **Login-success flows: route mocks can't mint cookies.** Session cookies are usually issued server-side (the app server proxies the login call and sets cookies from the backend response); a browser-layer route mock returns the success body but no `Set-Cookie`, so the post-login SSR still sees an anonymous user. Hybrid pattern: mock the login POST for the form/UX behavior, seed the session cookies through the project's sanctioned test seam (test-auth endpoint, API login helper) right before submit, then assert the full redirect chain. Comment WHY in the spec — it reads like cheating until you know cookie issuance is server-side.

---

## Branch State Seeding

- For multi-step funnels (onboarding, checkout, multi-page applications), do **not** drive the shared prefix (consent → phone-auth → …) through the UI in every spec. Each test re-running the common steps is slow, and one change to the prefix breaks every downstream test at once — the opposite of the independence Playwright recommends.
- Instead, seed the user to the **branch's starting state** through a test-only API/endpoint, then exercise only the branch under test. This mirrors the `storageState` approach for auth, extended to application state.
- Use real UI steps for the prefix **only** in the one spec that specifically verifies that prefix. Everywhere else, seed and skip ahead.
- Record which seeding endpoints/fixtures exist in the project's conventions doc (Step 5b) so later runs reuse them instead of re-driving the funnel.

---

## Suppression Convention

When a forbidden pattern is genuinely unavoidable, add `// JUSTIFIED: <reason>` on the **line immediately above**. This tells the `e2e-reviewer` to skip the hit during grep checks.

Patterns that accept `// JUSTIFIED:`:
- `.nth()` / `.first()` / `.last()` — explain why positional selection is required
- `{ force: true }` — explain why the element is not normally actionable
- `{ timeout: 0 }` — explain why auto-retry must be disabled
- `evaluate()` / `waitForFunction()` with raw DOM — explain why the framework API can't express the condition

**No suppression exists for:** `test.only` / `it.only` (always remove before commit).
