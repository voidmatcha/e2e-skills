# Pattern Reference

Read on demand from SKILL.md Phase 2: the exact contract for each of the 24 patterns —
detection semantics, severity rationale, false-positive exclusions, JUSTIFIED handling.
The Quick Reference table in SKILL.md is the at-a-glance ID/severity index; this file is the
authority for per-pattern behavior. CI parity (scripts/ci/review.sh Checks 3b/3c) validates the
`### P0/P1/P2 —` section placement and `#### <id>.` headers in THIS file against that table.

Detailed specification for the 24 anti-patterns that Phase 1, Phase 2, and Phase 2.5 execute. Do **not** re-run these checks as a separate pass — the phases above already cover them. When emitting a finding, consult the matching section here for the canonical Symptom / Rule / Fix wording. Grouped by severity: P0 items are silent always-pass bugs, P1 items waste CI time or mislead developers, P2 items are maintenance concerns.

**Important:** `test.skip()` with a reason comment or reason string is intentional — do NOT flag or remove these. Only flag assertions gated behind a runtime `if` check that cause the test to pass silently (see #5a).

---

### P0 — Must Fix (silent always-pass)

Tests pass when the feature is broken. No real verification is happening. Always check these.

#### 1. Name-Assertion Alignment `[LLM-only]`

**Symptom:** Test name promises something the assertions don't verify.

```typescript
// BAD — name says "status" but only checks visibility
test('should display user status', async ({ page }) => {
  await expect(status).toBeVisible();  // no status content check
});
```

**Rule:** Every noun in the test name must have a corresponding assertion. Add it or rename.

**Procedure:**
1. Extract all nouns from the test name (e.g., "should display user **status**")
2. For each noun, search the test body for `expect()` that verifies it
3. Missing noun → add assertion or remove noun from name

**Common patterns:** "should display X" with only `toBeVisible()` (no content check), "should update X and Y" with assertion for X but not Y, "should validate form" with only happy-path assertion.

#### 2. Missing Then `[LLM-only]`

**Symptom:** Test acts but doesn't verify the final expected state.

```typescript
// BAD — toggles but doesn't verify the dismissed state
test('should cancel edit on Escape', async ({ page }) => {
  await input.click();
  await page.keyboard.press('Escape');
  await expect(text).toBeVisible();
  // input still hidden?
});
```

**Rule:** For toggle/cancel/close actions, verify both the restored state AND the dismissed state.

**Procedure:**
1. Identify the action verb (toggle, cancel, close, delete, submit, undo)
2. List the expected state changes (element appears/disappears, text changes, count changes)
3. Check that BOTH sides of the state change are asserted

**Common patterns:** Cancel/Escape without verifying input is hidden, delete without verifying count decreased, submit without verifying form resets, tab switch without verifying previous tab content is hidden.

**Do NOT flag (Phase 2 accept-criteria) — the verification is often non-obvious; confirm it is *truly* absent before flagging.** A delete/remove test is fine when any of these is present:

- **API / request test:** a `request('DELETE')` / `request.delete()` followed by a GET asserting `status()` is `404` — the 404 *is* the removal assertion (not a missing-then).
- **Cleanup / teardown:** the delete sits in `afterEach`/`afterAll`/`after()` or a test titled `Cleanup:`/`teardown` — its job is teardown, not user-facing verification (the create test owns that assertion).
- **Success-confirmation:** a post-delete success toast/snackbar matching `/deleted|removed/i`, or a redirect (`toHaveURL` back to the list/index) — both count as verifying the delete happened.
- **Helper-embedded assertion:** the delete runs through a shared helper (e.g. `deleteElement(name)`, `deleteRancherResource(...)`) that asserts removal internally — read the helper before flagging.
- **Non-standard negative assertion:** `toHaveCount(0)`, `toBeEmpty()`, `toBeNull()`, or `isVisible()` captured into a variable then `toBe(false)` are all valid absence checks.
- **Non-entity "remove":** editor text/image, a CSS class/style, diacritics, or whitespace being "removed" is not entity deletion — judge by the noun in the title, not the verb.

Only flag when the test performs a real entity-delete action (a click/dispatch on a delete/trash/remove control) and **none** of the above verifications follow.

#### 3. Error Swallowing `[grep-detectable + LLM]`

**Symptom (POM — grep):** `.catch(() => {})` or `.catch(() => false)` on awaited operations — caller never sees the failure.

**Symptom (spec — LLM):** `try/catch` wrapping assertions — test passes on error instead of failing.

```typescript
// BAD POM — caller thinks execution succeeded
await loadingSpinner.waitFor({ state: 'detached' }).catch(() => {});

// BAD spec — silent pass on assertion failure
try { await expect(header).toBeVisible(); }
catch { console.log('skipped'); }
```

**Rule (POM):** Remove `.catch(() => {})` / `.catch(() => false)` from wait/assertion methods. If the operation can legitimately fail, the caller should decide how to handle it. Only keep catch for UI stabilization like `input.click({ force: true }).catch(() => textarea.focus())`.

**Rule (spec):** Never wrap assertions in `try/catch`. Use `test.skip()` in `beforeEach` if the test can't run. `try/catch` in non-assertion code (setup, teardown, optional cleanup) is fine — LLM must read context before flagging.

#### 3b. Cypress `uncaught:exception` Suppression `[grep-detectable, Cypress only]`

**Symptom:** `cy.on('uncaught:exception', () => false)` globally suppresses all unhandled app errors, hiding real bugs.

```javascript
// BAD — blanket suppression
Cypress.on('uncaught:exception', () => false);

// BETTER — scoped to a specific known error
Cypress.on('uncaught:exception', (err) => {
  if (err.message.includes('ResizeObserver loop')) return false;
  throw err;
});
```

**Rule:** Blanket `() => false` is P0 — equivalent to `.catch(() => {})`. Two patterns are NOT P0 and should be skipped in Phase 2:

1. **Scoped handlers** that filter specific known errors and re-throw others — acceptable with `// JUSTIFIED:`.
2. **Scoped negative-regression test** — `cy.on('uncaught:exception', (err) => { expect(err.message.includes('X')).to.be.false; });` — the handler is **asserting on the error properties**, not swallowing the error. The test deliberately runs scenarios that historically threw and verifies they no longer do. Phase 2 distinction: does the handler contain an `expect(...)` call? If yes, it's a test assertion, not suppression — NOT P0.

#### 4. Always-Passing Assertions `[grep-detectable + LLM confirmation]`

**Symptom:** Assertion that can never fail.

```typescript
// BAD — count >= 0 is always true
expect(count).toBeGreaterThanOrEqual(0);

// BAD — element always present in DOM; assertion never fails
await expect(page.locator('header')).toBeAttached();

// BAD — one-shot boolean, no auto-retry
expect(await el.isVisible()).toBe(true);
expect(await el.textContent()).toBe('expected text');
expect(await el.getAttribute('attr')).toBe('value');
expect(await el.allTextContents()).toContain('expected item');

// BAD — Locator is always a truthy JS object regardless of element existence
expect(page.locator('.selector')).toBeTruthy();

// BAD — a Locator is never null/undefined, so these never fail either (same #4f family)
expect(page.getByText('1/31/2025')).not.toBeNull();
expect(page.getByText('1/31/2025')).not.to.equal(null);
expect(page.locator('.selector')).toBeDefined();

// BAD — disables auto-retry entirely
await expect(el).toHaveCount(0, { timeout: 0 });
```

**Rule:** `toBeAttached()` on an unconditionally rendered element (always in the static HTML shell) is vacuous → P0. The only legitimate use is asserting that an element exists in the DOM but is CSS-hidden (`visibility:hidden`, not `display:none`) — add `// JUSTIFIED: visibility:hidden` in that case.

**Fix:**
- `toBeGreaterThanOrEqual(0)` → `toBeGreaterThan(0)`
- `toBeAttached()` → `toBeVisible()`, or remove if other assertions cover the element
- `expect(await el.isVisible()).toBe(true)` → `await expect(el).toBeVisible()`
- `expect(await el.textContent()).toBe(x)` → `await expect(el).toHaveText(x)`
- `expect(await el.getAttribute('x')).toBe(y)` → `await expect(el).toHaveAttribute('x', y)`
- `expect(await el.allTextContents()).toContain(x)` → `await expect(el).toContainText(x)`
- `expect(locator).toBeTruthy()` → `await expect(locator).toBeVisible()`
- `expect(locator).not.toBeNull()` / `.not.to.equal(null)` / `.toBeDefined()` → `await expect(locator).toBeVisible()` (a Locator is never null/undefined; assert the user-visible state instead)
- `{ timeout: 0 }` on assertions → remove unless preceded by an explicit wait; add `// JUSTIFIED:` if intentional
- `expect(page.url()).toContain(x)` → `await expect(page).toHaveURL(x)` (one-shot URL read with no retry)
- **Multiple `expect(page.url()).toContain(...)` in sequence** → replace each call with its **own** `await expect(page).toHaveURL(/.../) `. Do NOT combine them into a single regex with `.*` (e.g., `toHaveURL(/A.*B/)`) — that adds an ordering constraint not present in the original substring checks.
- **Compound boolean expression** like `expect(visible1 || visible2).toBe(true)` is the same one-shot anti-pattern as `expect(await el.isVisible()).toBe(true)`. Prefer a locator-level web-first assertion such as `await expect(page.locator('.a, .b')).toBeVisible()`. If both branches require independent assertions (e.g., different post-actions per branch), gate the test with `test.skip()` on the unsupported branch rather than collapsing into a single boolean check.

#### 5. Bypass Patterns `[grep-detectable]` (5a P0, 5b P1)

Two sub-patterns that suppress what the framework would normally catch — making tests pass when they should fail. Listed under P0 because 5a is a silent-pass bug; 5b is a P1 actionability issue documented in the same section for proximity.

**5a. Conditional assertion bypass** — `expect()` gated behind a runtime `if` check. If the condition is false, no assertion runs and the test passes vacuously.

```typescript
// BAD — if spinner never appears, assertion never runs
if (await spinner.isVisible()) {
  await expect(spinner).toBeHidden({ timeout: 5000 });
}
```

**Rule:** Every test path must contain at least one unconditional `expect()`. Move environment- or feature-flag checks to `beforeEach` / declaration-level `test.skip()` so the test is skipped entirely rather than passing silently.

**5b. Force true bypass** — `{ force: true }` skips actionability checks (visibility, enabled state, pointer-events), hiding real UX problems that real users would encounter.

**Rule:** Each `{ force: true }` must have `// JUSTIFIED:` on the line above explaining why the element is not normally actionable. Without a comment, flag P1.

#### 7. Focused Test Leak (`test.only` / `it.only`) `[grep-detectable]`

**Symptom:** A `.only` modifier left in committed code. Severity depends on whether the file has other tests that get silently skipped.

```typescript
// CRITICAL SILENT-SKIP — file has multiple tests; the others never run
test.only('should show user profile', async ({ page }) => { ... });
test('should show settings', ...);   // ← never runs in CI

// SMELL ONLY (no behavior change) — file has only one test, so .only skips nothing
test.only('the only test in this file', ...);
```

**Severity tiers** (LLM check during Phase 2):

| Tier | Condition | Severity | Rationale |
|------|-----------|----------|-----------|
| P0 (CRITICAL) | The same file has ≥2 `it`/`test`/`describe` declarations | P0 — silent CI disaster | The non-focused tests never execute; CI passes anyway |
| P1 (smell) | The `.only` is the file's only `it`/`test` | P1 — debug leak | Behavior unchanged at file level; still a debug artifact that should be removed for cleanliness. If anyone ADDS a second test to this file, it will silently skip — the leak becomes load-bearing. |

**Rule** (Playwright & Cypress best practices): `.only` is a development-time focus tool. It must never be committed regardless of tier. Search `.spec.*/.test.*/.cy.*` for `\.(only)\(` — Phase 1 flags every hit; Phase 2 LLM downgrades singletons to P1.

**Fix:** Delete the `.only` modifier. If the test is intentionally isolated, use `test.skip()` with a reason on the others, or run a single file via the CLI (`--grep` / `--spec`). For P1 (singleton), the fix is mechanical — no behavior change. For P0, fix immediately and audit CI history for skipped runs.

No `// JUSTIFIED:` exemption exists for either tier — there are no legitimate committed uses.

#### 8. Missing Assertion `[grep-detectable]`

Two sub-patterns where no assertion ever occurs — the test executes code but verifies nothing.

**8a. Dangling locator** `[Playwright grep / Cypress LLM]` — a locator created as a standalone statement, not assigned to a variable, not passed to `expect()`, and not chained with an action. The statement is a complete no-op.

```typescript
// BAD — locator created and immediately discarded
await page.locator('.selector');
page.getByRole('button'); // also bad — not even awaited
```

**8b. Boolean result discarded** — `isVisible()` / `isEnabled()` / `isChecked()` / `isDisabled()` / `isEditable()` awaited as a standalone statement. The boolean resolves and is thrown away.

```typescript
// BAD — boolean computed but never checked; asserts nothing
await el.isVisible();
await el.isEnabled();
await page.isVisible('[data-testid="foo"]'); // page-level shorthand with a selector arg — same discard
```

**Rule:** Every locator expression and every boolean state call must either feed into `expect()`, be assigned and used later, or be chained with an action. Standalone expressions are always bugs.

**Fix:** Replace with web-first assertion — `await expect(locator).toBeVisible()` / `toBeEnabled()` etc. These also auto-retry. Or delete the line if it's leftover debug code.

**Detection note:** the scanner flags both the empty-parens form and the page-level selector-argument shorthand (`await page.isVisible('sel')`), with or without a trailing semicolon. The end-of-statement anchor means handled/chained forms are NOT flagged: `await el.isVisible().catch(() => false)` (covered by `#3` error-swallow), `&& ...`, ternaries, and assigned reads (`const v = await el.isVisible()`) all pass.

#### 12. Missing Auth Setup `[LLM-only]`

**Symptom:** Spec navigates to protected routes (`/dashboard`, `/settings`, `/admin`, `/account`, etc.) without any preceding login action, `storageState` configuration, or authentication `beforeEach` hook.

**Why it matters:** Tests hit a login redirect instead of the intended page, making all assertions vacuous — they verify the login page, not the feature under test.

**Rule:** Every spec that navigates to a route requiring authentication must either: (a) perform login in `beforeEach`, (b) use `storageState` from Playwright config, or (c) use a custom auth fixture. Flag P0 if no auth mechanism is visible.

#### 15. Missing `await` on `expect()` `[grep-detectable]`

**Symptom:** `expect(locator).toBeVisible()` without `await` — the expression returns a Promise that is never awaited. The test moves on immediately and the assertion never actually runs.

```typescript
// BAD — Promise returned but never awaited; test always passes
expect(page.locator('.toast')).toBeVisible();

// BAD — await is on the locator (a no-op; a Locator is not thenable), not on expect;
//       the web-first matcher promise still floats and never settles
expect(await page.getByTestId('toast')).toBeVisible();

// GOOD
await expect(page.locator('.toast')).toBeVisible();
```

**Why it matters:** This is a silent P0. The test compiles and runs green, but zero verification happens. Extremely common mistake, especially when converting from non-async test frameworks.

**Rule:** Every `expect()` on a Playwright Locator must be `await`ed. Grep flags two forms: lines starting with `expect(` without `await`, and the awaited-locator form `expect(await <locator>).<web-first matcher>(` where the `await` sits on the locator instead of on `expect`. Confirm in Phase 2 that the subject is a Locator (non-Locator expects like `expect(count).toBe(3)` don't need `await`, and value-resolving one-shot reads like `expect(await x.isVisible()).toBe(true)` are #4c-4e, not this). Flag P0.

#### 16. Missing `await` on Playwright Actions `[grep-detectable]`

**Symptom:** `page.locator(...).click()` without `await` — the action is fired but never awaited. It may not execute at all, or execute out of order.

```typescript
// BAD — click may never complete before next line runs
page.locator('#submit').click();

// GOOD
await page.locator('#submit').click();
```

**Why it matters:** Silent no-op. The test passes because it never waits for the action. Subsequent assertions may run against stale page state.

**Rule:** Every Playwright action (`.click()`, `.fill()`, `.type()`, `.press()`, `.check()`, `.selectOption()`, `.setInputFiles()`, `.hover()`, `.focus()`, `.blur()`) must be `await`ed. Flag P0.

---

### P1 — Should Fix (poor diagnostics / wastes CI time)

Tests work but mislead developers, waste CI time, or set up future regressions. Check on every review.

#### 6. Raw DOM Queries (Bypassing Framework API) `[grep-detectable]`

**Symptom:** Test or POM uses `document.querySelector*` / `document.getElementById` inside `evaluate()` or `waitForFunction()` when the framework's element API could do the same job. Check both spec files and POM files — raw DOM in a POM helper is equally harmful since it bypasses the same auto-wait guarantees.

**Why it matters:** No auto-waiting, no retry, boolean trap, framework error messages lost.

```typescript
// BAD
await page.waitForFunction(() => document.querySelectorAll('.item').length > 0);
const has = await page.evaluate(() => !!document.querySelector('.result'));

// GOOD
await page.locator('.item').waitFor({ state: 'attached' });
await expect(page.locator('.result')).toBeVisible();
```

**Rule:** Use the framework's element API instead of raw DOM:
- **Playwright:** `locator.waitFor({ state: 'attached' })` replaces `waitForFunction(() => querySelector(...) !== null)`; `page.locator()` + web-first assertions replaces `evaluate(() => querySelector(...))`
- **Cypress:** `cy.get()` / `cy.find()` — avoid `cy.window().then(win => win.document.querySelector(...))`

Only use `evaluate`/`waitForFunction` when the framework API genuinely can't express the condition: multi-condition AND/OR logic, `getComputedStyle`, `children.length`, cross-element DOM relationships, or `body.textContent` checks. Add `// JUSTIFIED:` explaining why.

#### 9. Hard-coded Sleeps `[grep-detectable]`

**Symptom:** Explicit sleep calls pause execution for a fixed duration instead of waiting for a condition.

Sub-variants share this entry: `#9` Playwright `waitForTimeout`, `#9b` Cypress `cy.wait(ms)`, `#9c` Playwright `waitForLoadState('networkidle')` — networkidle is explicitly discouraged by Playwright docs as unreliable on modern SPAs; replace with a web-first assertion on the element the test actually needs.

```typescript
// BAD — arbitrary delay; still races if render takes longer
await page.waitForTimeout(2000);
cy.wait(1000);

// GOOD — wait for condition
await expect(modal).toBeVisible();
cy.get('[data-testid="modal"]').should('be.visible');
```

**Rule:** Never use explicit sleep (`waitForTimeout` / `cy.wait(ms)`) — rely on framework auto-wait or condition-based waits.

Note: `timeout` option values in `waitFor({ timeout: N })` or `toBeVisible({ timeout: N })` are NOT flagged — these are bounds, not sleeps.

#### 10. Flaky Test Patterns `[LLM-only + grep]`

Two sub-patterns that cause tests to fail intermittently in CI or parallel runs.

**10a. Positional selectors** — `nth()`, `first()`, `last()` without a comment break when DOM order changes.

```typescript
// BAD — breaks if DOM order changes
await expect(items.nth(2)).toContainText('expected text');
```

**Rule:** Prefer `data-testid`, role-based, or attribute selectors. If `nth()` is unavoidable, add `// JUSTIFIED:` explaining why.

**Exemptions (no `// JUSTIFIED:` needed):**
- **Method-name self-documents intent** — when the enclosing method's name explicitly conveys positional access (e.g., `getParagraphByIndex(index) { return this.paragraphs.nth(index); }`, `nthRowOf(...)`, `firstResult()`). The name documents the intent.
- **Fallback selector loops** — `.first()` inside `for (const selector of fallbackSelectors) { … this.page.locator(selector).first() … }`. Here `.first()` means "any match for this candidate selector", not "the first of multiple known elements".
- **Single-result `toHaveCount(1)` adjacent** — `await expect(items).toHaveCount(1); const only = items.first();` (the count assertion documents that exactly one element exists).

**Selector priority** (best → worst, per [Playwright docs](https://playwright.dev/docs/best-practices#use-locators)): `getByRole` → `getByLabel` → `getByTestId`/`data-cy` → `getByText` → attribute (`[name]`, `[id]`) → class → generic. Class and generic selectors are "Never" — coupled to CSS and DOM structure.

**10b. Serial test ordering** `[Playwright only]` — `test.describe.serial()` makes tests order-dependent: a single failure cascades to all subsequent tests, and the suite can't be sharded.

**Rule:** Replace serial suites with self-contained tests using `beforeEach` for shared setup. If sequential flow is genuinely required, use a single test with `test.step()` blocks. If serial is unavoidable, add `// JUSTIFIED:` on the line above `test.describe.serial(`.

#### 13. Inconsistent POM Usage `[LLM-only]`

**Symptom:** A POM class is imported and used for some actions, but the spec also uses raw `page.fill()` / `page.click()` for operations the POM should encapsulate.

**Why it matters:** Defeats the purpose of the POM pattern — when the UI changes, you must update both the POM and the spec. DRY principle violated.

**Rule:** If a POM exists for a page, all interactions with that page should go through the POM. Flag P1 if spec bypasses POM with raw `page.*` calls for actions the POM should own. Suggest adding missing methods to the POM.

#### 14. Hardcoded Credentials `[grep-detectable]`

**Symptom:** String literals used as usernames, passwords, or API keys directly in test code.

```typescript
// BAD — credentials as string literals
await loginPage.login('demo-admin', '<literal-password>');
await page.fill('#password', '<literal-secret>');
```

**Why it matters:** Security risk if repo is public, couples tests to specific credentials, prevents running tests against different environments.

**Rule:** Use environment variables (`process.env.TEST_USER`), Playwright config secrets, or test data fixtures. Flag P1.

**Scope — only flag actual credentials, not input test data:**
- **Flag** literals passed to authentication operations: `loginPage.login('demo-admin', '<literal-password>')`, `page.locator('#password').fill('<literal-password>')` followed by submit, API calls posting credentials, fixtures named `validUser` / `testAdmin`.
- **Do NOT flag** literals used only to verify form input behavior (no auth attempt follows): `passwordInput.fill('anyText'); await expect(passwordInput).toHaveValue('anyText');` — this is input-acceptance testing, not credential storage. Intentional invalid-creds fixtures with dummy username/password values are also fine because they document a negative-path scenario.

When grep flags a literal, read 2–3 lines below to confirm a login/auth call follows. If none, skip.

#### 17. Direct `page.click(selector)` API `[grep-detectable, Playwright only]`

**Symptom:** Using `page.click('#button')` or `page.fill('#input', 'text')` instead of the locator-based API.

```typescript
// BAD — direct page action
await page.click('#submit');
await page.fill('#email', 'user@test.com');

// GOOD — locator-based, auto-wait, better errors
await page.locator('#submit').click();
await page.locator('#email').fill('user@test.com');
```

**Why it matters:** `page.click(selector)` skips the Locator layer, losing locator composition and producing worse review/error context. Playwright docs recommend locator-based actions.

**Rule:** Flag P1. Suggest migrating to `page.locator(selector).action()`.

#### 18. `expect.soft()` Overuse `[grep-detectable + LLM]`

**Symptom:** Most or all assertions in a test use `expect.soft()`, so the test continues past failures and may mask cascading issues — functionally equivalent to error swallowing.

```typescript
// BAD — all assertions are soft; test never fails early
test('should display profile', async ({ page }) => {
  await expect.soft(page.locator('.name')).toBeVisible();
  await expect.soft(page.locator('.email')).toBeVisible();
  await expect.soft(page.locator('.avatar')).toBeVisible();
});

// GOOD — one hard assertion gates, soft assertions for independent checks
test('should display profile', async ({ page }) => {
  await expect(page.locator('.profile')).toBeVisible();          // hard gate
  await expect.soft(page.locator('.name')).toHaveText('Alice');  // independent detail
  await expect.soft(page.locator('.email')).toHaveText('a@b.c'); // independent detail
});
```

**Rule:** `expect.soft()` is fine for independent, non-critical checks alongside hard assertions. Flag P1 when >50% of assertions in a single test are `soft` — the test likely needs at least one hard assertion to gate on the primary condition.

#### 19. Module-Level Mutable State In Test Utilities `[grep-detectable + LLM]`

**Symptom:** A top-level (column-0) `let` declaration with an initializer in a test utility, helper, or POM file — state that persists across test invocations within the same worker.

```typescript
// BAD — module-level counter; survives across tests in the worker
let testNotebookSequence = 0;

export async function createTestNotebook(page: Page) {
  testNotebookSequence += 1;
  const name = `notebook_${testNotebookSequence}_${Date.now()}`;
  // ...
}

// GOOD — derive uniqueness from data that's already unique
export async function createTestNotebook(page: Page) {
  const name = `notebook_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  // ...
}
```

**Why it matters:** Playwright/Cypress run specs across multiple worker processes in parallel and retry failed tests within a worker. Module-level mutable state survives across tests within a worker but is independent across workers — so the same counter value can appear in two specs running concurrently in different workers, breaking the "unique" contract the variable was supposed to provide. Retries reuse the worker, so the second attempt sees state from the first. Both are silent bugs that only surface as intermittent name collisions or flake.

**Rule:** Flag P1 when a `let` at column 0 has an initializer. Suppress with `// JUSTIFIED: [reason]` when the state is intentionally shared (e.g., a worker-scoped cache the framework's parallelism guarantees won't collide).

**Phase 2 LLM filter:**
- SKIP pure type declarations: `let page: Page;`, `let context: BrowserContext;` — these are idiomatic Playwright fixtures, reassigned in `beforeEach`, and never carry data across tests.
- FLAG initialized lets: `let counter = 0;`, `let cache = new Map();`, `let lastResult: Result | null = null;`.

**Fix pattern:** Replace counter-based uniqueness with `Date.now()` + `Math.random().toString(36).slice(2, 8)`, or use Playwright's `testInfo.workerIndex` for worker-scoped uniqueness, or move the state into a `test.beforeEach` so it's per-test rather than per-worker.

---

#### 20. Unmocked Real-Backend Writes `[LLM-only]`

**Symptom:** A spec drives a write or credential path — signup, login, checkout, any data mutation — and no route stub (`page.route()` / `cy.intercept()`) in the spec or its fixtures covers the endpoint, so every run reaches a real backend.

**Why it matters:** Each CI run creates real accounts, real orders, or real charges: shared-environment data pollution, rate-limit and quota flakiness, and PII/credential exposure in backend or third-party logs. The test is also non-deterministic — backend state, not the code under test, decides whether it passes.

```typescript
// BAD — every run registers a real account on the shared backend
await signUpPage.fillForm(`test+${Date.now()}@corp.com`, 'hunter22!');
await signUpPage.submitButton.click();

// GOOD — the write is stubbed; the test asserts the app's handling of the response
await page.route('**/api/auth/join**', r =>
  r.fulfill({ status: 200, contentType: 'application/json', body: '{"result":"SUCCESS"}' }));
await signUpPage.fillForm('user@example.com', 'hunter22!');
await signUpPage.submitButton.click();
```

**Rule:** Write/credential endpoints must be stubbed in specs. One clearly named real-backend smoke spec (e.g. a throwaway guest session) is the only exemption — mark it `// JUSTIFIED: designated real-backend smoke`.

**Detection (LLM):** In each spec, list actions that submit forms or trigger mutation-shaped requests (signup/login/checkout/save/delete). Check whether a route stub or mock fixture covers each one — read helper and fixture files before flagging; the stub may live there. Client-side-only validation tests (no request fired) are not hits.

#### 22. Optimistic UI Without Call Proof `[LLM-only]`

**Symptom:** An interaction test clicks a write control (like toggle, delete, save) and asserts only the resulting UI state — but the app updates that UI *optimistically*, before (and regardless of) the network call. The assertion passes even if the wiring to the API is deleted.

**Why it matters:** This is a false positive specific to write interactions: the visible behavior under test is produced client-side, so the test proves the click handler ran, not that the write reached the backend contract. A regression that drops the API call (refactor, early return, swallowed promise) ships green.

```typescript
// BAD — aria-pressed flips optimistically; passes with the POST deleted
await likeToggle.click();
await expect(likeToggle).toHaveAttribute('aria-pressed', 'true');

// GOOD — request proof + UI state
const call = page.waitForRequest(r =>
  r.method() === 'POST' && r.url().includes('/user/sentence/like'));
await likeToggle.click();
await call;
await expect(likeToggle).toHaveAttribute('aria-pressed', 'true');
```

**Rule:** Every write-interaction test pairs its UI assertion with proof the request fired: `page.waitForRequest()`, a route-handler hit flag, or an assertion on mocked-request capture. Set up `waitForRequest` *before* the click to avoid racing fast responses.

**Detection (LLM):** For each test that clicks a control whose handler issues a mutation (read the component if unsure), check whether the spec awaits any request evidence. If the only assertions are on DOM/UI state that the component updates optimistically, flag. Tests of pure client-side state (no request in the handler) are not hits.

---

### P2 — Nice to Fix (maintenance / robustness)

Weak but not wrong. Address when refactoring or before adopting wider conventions.

#### 11. YAGNI + Zombie Specs `[LLM-only]`

Two sub-patterns: unused code in Page Objects, and zombie spec files.

**11a. YAGNI in Page Objects and Utility Modules** — POM or utility/helper file has locators, methods, or exported functions never referenced (or referenced exactly once) by any spec or other module. Or a POM class extends a parent with zero additional members (empty wrapper class).

**Procedure:**
1. List all public members of each changed POM file AND all exported symbols of each changed utility module (`utils.ts`, `helpers.ts`, `fixtures.ts`, etc.)
2. Grep each member/export across all test files, POMs, and other utility modules
3. Classify: USED / INTERNAL-ONLY (`private` for POMs, non-`export` for utility modules) / UNUSED (delete) / SINGLE-USE (inline at the call site)
4. Check if any POM class has zero members beyond what it inherits — empty wrappers add no value unless the convention is intentional

**Common patterns:** Convenience wrappers (`clickEdit()` when specs use `editButton.click()`), getter methods (`getCount()` when specs use `toHaveCount()`), state checkers (`isVisible()` when specs assert on locators directly), pre-built "just in case" locators, empty subclass created for future expansion. In utility modules: single-use auth helpers (`isLoginPageVisible()` called by exactly one other utility), single-use REST helpers (`getDefaultInterpreterGroup()` called by exactly one create function), single-use waits (`waitForNotebookParagraphVisible()` invoked from one navigation helper).

**Single-use Util wrappers** — a separate `*Util` / `*Helper` class OR a standalone exported function in a utility module whose body is called from only one place. These add indirection with no reuse benefit; inline them at the single call site. Keep a Util method or exported helper only if called from **2+ call sites** or invoked **2+ times** within one test.

**Rule:** Delete unused members and exports. Make internal-only POM members `private`; drop the `export` keyword from utility functions used only inside their own module. Apply the 2+ call-site threshold before creating or keeping any helper — if it's called from only one place, inline it. Flag empty wrapper classes for review — they may be intentional convention or dead code.

**11b. Zombie spec files** — An entire spec file whose tests are all subsets of tests in another spec file covering the same feature. The file adds no coverage that isn't already verified elsewhere.

**Procedure:** After reviewing all files in scope, cross-check spec files with similar names or feature coverage. If every test in file A is a subset of a test in file B, flag file A for deletion.

**Common patterns:** `feature-basic.spec.ts` where every case also appears in `feature-full.spec.ts`; a 1–2 test file created as a "quick smoke" that was never expanded while a comprehensive suite grew alongside it.

**Rule:** Delete the zombie file. If any test in it is not covered elsewhere, migrate it to the comprehensive suite first.

**Output:**
```
| File | Member | Used In | Status |
|------|--------|---------|--------|
| modal-page.ts | openModal() | (none) | DELETE |
| modal-page.ts | closeButton | internal only | PRIVATE |
| search-page.ts | (class body empty) | — | REVIEW |
| basic.spec.ts | (entire file) | covered by full.spec.ts | DELETE |
```

#### 21. Manually-Captured Session-File Dependency `[LLM-only]`

**Symptom:** A spec, fixture, or project config loads a `storageState` JSON (e.g. `auth/member.json`) that only a manual capture script or a developer's one-off login produces — nothing in the automated test setup can regenerate it.

**Why it matters:** The file is absent on fresh clones and CI, and silently expires. The suite then fails — or worse, soft-skips — for reasons unrelated to the code under test, and nobody trusts the signal.

**Rule:** Session state must be reproducible from code: an API-login helper or a `setup` project that writes `storageState` before dependent specs run. A committed or manually captured file may serve only as a cache with a programmatic fallback.

**Detection (LLM):** For each `storageState:` reference (spec, fixture, or `playwright.config` project), trace what writes that path. If only a manual script — or nothing in-repo — produces it, flag.

#### 23. Fixture Ignores Conditional Render Guards `[LLM-only]`

**Symptom:** A seeded list/item fixture satisfies the API type but not the *render guards* of the component that displays it — e.g. a "Liked" tab whose item component does `if (tabIsLiked && !item.liked) return null;`, while the fixture seeds `liked: false`. The UI renders an empty container; the test fails with "element not found" that looks like infra flake, or—worse—a negative assertion (`toHaveCount(0)`, empty-state check) passes for the wrong reason.

**Why it matters:** Type-correct fixtures aren't render-correct fixtures. Components self-hide on field+view-state combinations (`liked` in a liked view, `enabled`, `membershipOnly`, date windows, `items.slice(1)` init drops), and these guards live in the component, not the API contract. Hours go to debugging "flaky" tests whose mock data was simply unrenderable.

**Rule:** Before seeding a list fixture, read the item component's early returns and filters; seed fields so the item passes every guard for the view under test. Document each discovered guard next to the fixture (e.g. "Like-tab items must seed `liked: true`") so the next generated test doesn't rediscover it.

**Detection (LLM):** For each fixture consumed by a list/card component, open the component and collect conditions that suppress rendering (early `return null`, `.filter()`, `.slice()`). Cross-check fixture field values against them. Flag mismatches, and flag negative assertions whose truth could come from a guard-suppressed render rather than the intended state.

---

