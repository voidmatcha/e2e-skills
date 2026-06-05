# Code Generation Rules

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

**Prove the call, not just the pixels.** For write interactions with optimistic UI (like toggles, deletes), the UI updates before — and regardless of — the request. Pair every such assertion with request proof:

```typescript
const call = page.waitForRequest(r => r.method() === 'POST' && r.url().includes('cmd=%2Fv2%2Fuser%2Fsentence%2Flike'));
await likeToggle.click();
await call; // without this line the test passes even if the wiring to the API is deleted
await expect(likeToggle).toHaveAttribute('aria-pressed', 'true');
```

---

## Auth & Session

- Authenticate **once**, programmatically (API-login helper or a `setup` project), persist with `storageState`, reuse it in specs that need a session. UI-driven login belongs only in specs that test the login flow itself.
- Never hard-depend on a **manually captured** session file — a locally generated `auth/*.json` that a fresh clone or CI won't have, and that silently expires. Generated tests must be able to recreate their session from code.
- Logged-out scenarios use a fresh context (no `storageState`) — don't "log out first" inside a test.
- **Login-success flows: route mocks can't mint cookies.** Session cookies are usually issued server-side (the app server proxies the login call and sets cookies from the backend response); a browser-layer route mock returns the success body but no `Set-Cookie`, so the post-login SSR still sees an anonymous user. Hybrid pattern: mock the login POST for the form/UX behavior, seed the session cookies through the project's sanctioned test seam (test-auth endpoint, API login helper) right before submit, then assert the full redirect chain. Comment WHY in the spec — it reads like cheating until you know cookie issuance is server-side.

---

## Suppression Convention

When a forbidden pattern is genuinely unavoidable, add `// JUSTIFIED: <reason>` on the **line immediately above**. This tells the `e2e-reviewer` to skip the hit during grep checks.

Patterns that accept `// JUSTIFIED:`:
- `.nth()` / `.first()` / `.last()` — explain why positional selection is required
- `{ force: true }` — explain why the element is not normally actionable
- `{ timeout: 0 }` — explain why auto-retry must be disabled
- `evaluate()` / `waitForFunction()` with raw DOM — explain why the framework API can't express the condition

**No suppression exists for:** `test.only` / `it.only` (always remove before commit).
