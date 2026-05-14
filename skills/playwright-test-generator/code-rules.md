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
2. `getByLabel('Email')` — form label
3. `getByTestId('submit-btn')` / `[data-testid="submit-btn"]` — explicit test hook
4. `getByText('Save')` / `.filter({ hasText: 'text' })` — visible text
5. attribute selector `[formControlName="email"]` — stable attribute
6. CSS class — **POM files only**, stable structural classes only (not styling classes)
7. `.nth()` / `.first()` / `.last()` — **forbidden** without `// JUSTIFIED:` on the line above

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
| `toBeAttached()` | `toBeVisible()` — `toBeAttached` is vacuous on always-rendered elements |
| `expect(locator).toBeTruthy()` | `await expect(locator).toBeVisible()` — Locator is always a truthy JS object |
| `page.click(selector)` / `page.fill(selector, v)` | `page.locator(selector).click()` / `.fill(v)` — locator-first actions are easier to compose and review |
| `{ force: true }` | Fix the root cause (element not actionable); if unavoidable, add `// JUSTIFIED:` |
| `waitUntil: 'networkidle'` | `waitUntil: 'domcontentloaded'` or condition-based wait — unreliable on SPAs |
| `expect(page.url()).toContain(x)` | `await expect(page).toHaveURL(x)` — one-shot, no retry |
| Framework component selectors in spec (`app-button`, `my-component`) | POM only |
| XPath selectors | `getByRole` / `getByLabel` / `getByTestId` |

**Await rule:** Every `expect()` on a Locator and every Playwright action (`.click()`, `.fill()`, `.type()`, `.press()`, `.check()`, `.selectOption()`, `.hover()`) **must** be `await`ed. Missing `await` silently skips the assertion or action.

---

## Suppression Convention

When a forbidden pattern is genuinely unavoidable, add `// JUSTIFIED: <reason>` on the **line immediately above**. This tells the `e2e-reviewer` to skip the hit during grep checks.

Patterns that accept `// JUSTIFIED:`:
- `.nth()` / `.first()` / `.last()` — explain why positional selection is required
- `{ force: true }` — explain why the element is not normally actionable
- `{ timeout: 0 }` — explain why auto-retry must be disabled
- `evaluate()` / `waitForFunction()` with raw DOM — explain why the framework API can't express the condition

**No suppression exists for:** `test.only` / `it.only` (always remove before commit).
