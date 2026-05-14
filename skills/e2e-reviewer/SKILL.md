---
name: e2e-reviewer
description: 'Use when reviewing, auditing, or improving E2E test specs for Playwright or Cypress — static code analysis of existing test files, not diagnosing runtime failures. Triggers on "review my tests", "audit test quality", "find weak tests", "my tests always pass but miss bugs", "tests pass CI but miss regressions", "improve playwright tests", "improve cypress tests", "check test coverage gaps", "my tests are fragile", "tests break on every UI change", "test suite is hard to maintain", "we have coverage but bugs still slip through", "flaky tests", "test anti-patterns", "check my e2e tests", "tests pass locally but fail in CI". Reviews 19 anti-patterns grouped by severity. P0 must-fix (silent always-pass): name-assertion mismatch, missing Then, error swallowing, Cypress uncaught:exception suppression, always-passing assertions, bypass patterns, focused test leak, missing assertions, missing auth setup, missing await on expect, missing await on action. P1 should-fix (poor diagnostics): raw DOM queries, hard-coded sleeps, flaky test patterns, inconsistent POM usage, hardcoded credentials, direct page action API, expect.soft overuse. P2 nice-to-fix (maintenance): YAGNI + zombie specs.'
license: Apache-2.0
metadata:
  author: voidmatcha
  version: "1.2.2"
---

# E2E Test Scenario Quality Review

Systematic checklist for reviewing E2E **spec files AND Page Object Model (POM) files**. Covers Playwright and Cypress with full grep + LLM analysis. General principles (name-assertion alignment, missing Then, YAGNI) apply to any framework, but automated grep patterns are Playwright/Cypress-specific.

**Reference:**
- Playwright best practices: https://playwright.dev/docs/best-practices
- Cypress best practices: https://docs.cypress.io/app/core-concepts/best-practices

## Phase 0: Framework Detection

Before running checks, determine the framework by grepping for import statements:
- `@playwright/test` → Playwright
- `cypress` → Cypress

**Skip framework-irrelevant checks:** If Playwright, skip Cypress-specific greps (`#9b cy.wait(ms)`, `#3b Cypress uncaught:exception`). If Cypress, skip Playwright-specific greps (`#8a dangling page.locator`, `#10b describe.serial`, `#15 missing await on expect`, `#16 missing await on action`, `#17 direct page action API`, `#18 expect.soft overuse`). This eliminates noise in Phase 1 output.

---

## Phase 1: Automated Grep Checks

Once the review target files are determined, use the Grep tool to mechanically detect known anti-patterns **before** LLM analysis. Run each check against the test directory (auto-detect from project structure — common paths: `e2e/`, `tests/`, `__tests__/`, `spec/`, `cypress/e2e/`).

**Evidence rule:** Phase 1 grep hits are mechanical review signals. Report exact matches, then use Phase 2 where the rule requires intent or project context. Official framework rules (web-first assertions, focused tests, missing awaits) can be reported directly; heuristic rules (`nth()`, `toBeAttached()`, `force:true`, raw DOM queries) need the `// JUSTIFIED:` and context checks below.

**Read `references/grep-patterns.md` for the full pattern tables organized in 5 batches.** Execute all Grep calls within each batch in a SINGLE assistant message so they run in parallel — running greps one-by-one wastes 3-4x the wall-clock time.

**Interpreting results:**
- Zero hits → no mechanical issues found, proceed to Phase 2
- Any hit → report each line as an issue (includes file:line)
- A hit is intentional and must be **skipped** when `// JUSTIFIED:` appears in any of these positions (exception: #7 Focused Test Leak has no `// JUSTIFIED:` exemption):
  1. The line **immediately preceding** the hit
  2. The line immediately preceding the **enclosing call/block** when the hit is inside a callback body — e.g., `// JUSTIFIED:` above `page.evaluate(() => { … document.querySelector(…) … })` or `page.waitForFunction(() => { … })` covers every qualifying pattern inside that callback
  3. For chained calls split across lines (`page.locator(…)\n  .filter(…)\n  .first()`), the line immediately preceding the chain's **starting expression** covers `.nth()` / `.first()` / `.last()` further down the chain
- Before reporting any hit, read 1–3 lines of context above to verify a JUSTIFIED comment does not cover it. Stale grep output without surrounding context is the #1 source of false positives in this review.

`try/catch` wrapping in spec files (#3 partial) requires LLM judgment (Phase 2) — too many legitimate uses to grep reliably.

Output Phase 1 results as-is — do not reinterpret them as semantic findings until Phase 2 confirms context where needed.

---

## Phase 2: LLM Review (Semantic And Context Checks Only)

Patterns already detected in Phase 1 (#3 partial, #4, #5, #6, #7, #8, #9, #10 partial, #14, #15, #16, #17, #18, #3b) are **skipped** unless they need LLM confirmation.
The LLM performs only these checks:

| # | Check | Reason |
|---|-------|--------|
| 1 | Name-Assertion Alignment | Requires semantic interpretation |
| 2 | Missing Then | Requires logic flow analysis |
| 3 | Error Swallowing — `try/catch` in specs | Too many legitimate non-test uses; requires reading context |
| 4 | Always-Passing — `.toBeTruthy()` confirmation | Phase 1 flags all `.toBeTruthy()` hits; LLM confirms which ones have a Locator subject (P0) vs. a legitimate boolean variable (OK). Do NOT re-report other #4 sub-patterns already covered in Phase 1. |
| 8 | Missing Assertion — Cypress dangling selectors | `cy.get(...)` standalone requires manual check |
| 10 | Flaky Test Patterns | For each grep hit that has `// JUSTIFIED:`, verify the rationale is concrete (e.g. "server returns in fixed order") rather than vague ("needed for now"); flag if the comment doesn't actually justify the position-coupling or serial dependency. Skip if no JUSTIFIED comment — Phase 1 already flagged. |
| 11 | YAGNI in POM + Zombie Specs | Requires usage grep then judgment |
| 12 | Missing Auth Setup | Spec navigates to protected routes (`/dashboard`, `/settings`, `/admin`, etc.) without preceding login, `storageState`, or auth `beforeEach`. Flag P0 — tests will hit login redirects. |
| 13 | Inconsistent POM Usage | POM is imported but spec bypasses it with raw `page.fill`/`page.click` for operations the POM should encapsulate. Flag P1. |
| 15 | Missing `await` on `expect()` confirmation | Phase 1 flags lines that start with `expect(` (no leading `await`). LLM confirms the subject is a Playwright `Locator` / `Page` — non-Locator expects like `expect(count).toBe(3)` don't need `await`. Flag P0 only when the subject is a Locator/Page. |
| 16 | Missing `await` on action confirmation | Phase 1 flags lines that start with `page.locator(...).action(` or `page.getBy...(...).action(` (no leading `await`). LLM confirms the line lacks `await` and the action is a real Playwright action (not a synchronous chain). Flag P0. |
| 18 | `expect.soft()` overuse confirmation | Phase 1 flags all `expect.soft()` hits; LLM counts: if >50% of assertions in a single test are `soft`, flag P1 — soft assertions mask cascading failures. A few `soft` assertions among many hard ones is fine. |

**Consolidation rule:** If a single code block triggers multiple checks (e.g., `page.evaluate` + `toBeTruthy` + `document.querySelector`), report it as ONE finding with all rule numbers in the heading (e.g., `[P0] #4f + #6: ...`). Do not create 3-4 separate findings for the same lines of code.

**#11 YAGNI — grep-assisted procedure:** For each POM file in scope, list all public members (locators + methods). Then grep each member name across all spec files and other POMs in a single parallel batch:
```
Grep pattern: "memberName1|memberName2|memberName3|..."
Glob: "*.{spec.*,test.*,cy.*}"
```
This is much faster than grepping each member individually. Classify results: USED / INTERNAL-ONLY (make `private`) / UNUSED (delete).

---

## Phase 2.5: Systemic Issues

After individual findings are catalogued, synthesize cross-cutting patterns that affect the test suite as a whole. Check for:

| Issue | How to check | Sev |
|-------|-------------|-----|
| **No authentication strategy** (suite-level rollup of #12) | 3+ specs across the suite navigate to protected routes without login/storageState. Always emit a single rollup line here; do not enumerate per-file findings — those belong in Phase 2. | P0 |
| **No stable user-facing selectors** | [Playwright] Zero uses of `getByRole` / `getByTestId` / `getByLabel` / `getByPlaceholder` / `getByText` across all files. [Cypress] Zero uses of `[data-cy=]` / `[data-testid=]` selectors and no `cy.findBy*` calls (cypress-testing-library). | P2 |
| **Missing `beforeEach`** | 3+ tests in a `describe` repeat the same setup code (POM instantiation + navigation) | P2 |

**Deduplication rule:** Phase 2.5 issues are *suite-wide* findings. If an issue is already raised once per file in Phase 2 (e.g. #12 Missing Auth Setup), do not also list each file under Phase 2.5 — emit a single rollup line with the affected file count.

Output as a dedicated section:
```markdown
## Systemic Issues
- **No authentication strategy:** N tests navigate to protected routes without auth setup. Add `storageState` or auth fixture. (Rolls up #12 across N files.)
- **No stable user-facing selectors:** [Playwright] 0 uses of getByRole/getByTestId across N files. [Cypress] 0 uses of `[data-cy=]`/`[data-testid=]` across N files. Migrate to user-facing locators.
```

Only report systemic issues that are actually present. Skip this section if none apply.

---

## Phase 3: Coverage Gap Analysis (After Review)

After completing Phase 1 + 2 + 2.5, identify scenarios the test suite does NOT cover. Scan the page/feature under test and flag missing:

| Gap Type | What to look for |
|----------|-----------------|
| Error paths | Form validation errors, API failure states, network offline, 404/500 pages |
| Edge cases | Empty state, max-length input, special characters, concurrent actions |
| Accessibility | Keyboard navigation, screen reader labels, focus management after modal/dialog |
| Auth boundaries | Unauthorized access redirects, expired session handling, role-based visibility |

**Context-aware suggestions:** Each gap MUST reference a specific finding from Phase 1/2 when possible. Generic suggestions that could apply to any test suite are less valuable. Connect the gap to what you observed in the code.

**Output:** List up to 5 highest-value missing scenarios as suggestions, not requirements. Format:

```markdown
## Coverage Gaps (Suggestions)
1. **[Edge case]** No test for empty dashboard state — currently `toBeGreaterThanOrEqual(0)` masks this (see #4a-1). Verify empty-state message when no metrics exist.
2. **[Error path]** No test for form submission with server error — the profile update test (settings:9) has no error path at all.
```

---

## Pattern Reference

Detailed specification for the 19 anti-patterns that Phase 1, Phase 2, and Phase 2.5 execute. Do **not** re-run these checks as a separate pass — the phases above already cover them. When emitting a finding, consult the matching section here for the canonical Symptom / Rule / Fix wording. Grouped by severity: P0 items are silent always-pass bugs, P1 items waste CI time or mislead developers, P2 items are maintenance concerns.

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

**Rule:** Blanket `() => false` is P0 — equivalent to `.catch(() => {})`. Scoped handlers that filter specific known errors and re-throw others are acceptable with `// JUSTIFIED:`.

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

// BAD — Locator is always a truthy JS object regardless of element existence
expect(page.locator('.selector')).toBeTruthy();

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
- `expect(locator).toBeTruthy()` → `await expect(locator).toBeVisible()`
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

**Symptom:** A `.only` modifier left in committed code causes CI to run only the focused test(s) and silently skip the rest of the suite — all other tests show as "not run" but the CI step passes.

```typescript
// SILENT CI DISASTER — every other test in the suite is skipped
test.only('should show user profile', async ({ page }) => { ... });
it.only('submit form', () => { ... });      // Jest / Cypress
describe.only('auth flow', () => { ... });
```

**Rule** (Playwright & Cypress best practices): `.only` is a development-time focus tool. It must never be committed. Search `.spec.*/.test.*/.cy.*` for `\.(only)\(` — every hit is P0. No `// JUSTIFIED:` exemption exists; there are no legitimate committed uses.

**Fix:** Delete the `.only` modifier. If the test is intentionally isolated, use `test.skip()` with a reason on the others, or run a single file via the CLI (`--grep` / `--spec`).

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
```

**Rule:** Every locator expression and every boolean state call must either feed into `expect()`, be assigned and used later, or be chained with an action. Standalone expressions are always bugs.

**Fix:** Replace with web-first assertion — `await expect(locator).toBeVisible()` / `toBeEnabled()` etc. These also auto-retry. Or delete the line if it's leftover debug code.

#### 12. Missing Auth Setup `[LLM-only]`

**Symptom:** Spec navigates to protected routes (`/dashboard`, `/settings`, `/admin`, `/account`, etc.) without any preceding login action, `storageState` configuration, or authentication `beforeEach` hook.

**Why it matters:** Tests hit a login redirect instead of the intended page, making all assertions vacuous — they verify the login page, not the feature under test.

**Rule:** Every spec that navigates to a route requiring authentication must either: (a) perform login in `beforeEach`, (b) use `storageState` from Playwright config, or (c) use a custom auth fixture. Flag P0 if no auth mechanism is visible.

#### 15. Missing `await` on `expect()` `[grep-detectable]`

**Symptom:** `expect(locator).toBeVisible()` without `await` — the expression returns a Promise that is never awaited. The test moves on immediately and the assertion never actually runs.

```typescript
// BAD — Promise returned but never awaited; test always passes
expect(page.locator('.toast')).toBeVisible();

// GOOD
await expect(page.locator('.toast')).toBeVisible();
```

**Why it matters:** This is a silent P0. The test compiles and runs green, but zero verification happens. Extremely common mistake, especially when converting from non-async test frameworks.

**Rule:** Every `expect()` on a Playwright Locator must be `await`ed. Grep flags lines starting with `expect(` — confirm in Phase 2 that the line lacks `await` and involves a Locator (non-Locator expects like `expect(count).toBe(3)` don't need `await`). Flag P0.

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
await loginPage.login('admin', 'password123');
await page.fill('#password', 'secret');
```

**Why it matters:** Security risk if repo is public, couples tests to specific credentials, prevents running tests against different environments.

**Rule:** Use environment variables (`process.env.TEST_USER`), Playwright config secrets, or test data fixtures. Flag P1.

**Scope — only flag actual credentials, not input test data:**
- **Flag** literals passed to authentication operations: `loginPage.login('admin', 'password')`, `page.locator('#password').fill('realPassword') ` followed by submit, API calls posting credentials, fixtures named `validUser` / `testAdmin`.
- **Do NOT flag** literals used only to verify form input behavior (no auth attempt follows): `passwordInput.fill('anyText'); await expect(passwordInput).toHaveValue('anyText');` — this is input-acceptance testing, not credential storage. Intentional invalid-creds fixtures like `INVALID_USER = { username: 'wronguser', password: 'wrongpass' }` are also fine because they document a negative-path scenario.

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

---

### P2 — Nice to Fix (maintenance / robustness)

Weak but not wrong. Address when refactoring or before adopting wider conventions.

#### 11. YAGNI + Zombie Specs `[LLM-only]`

Two sub-patterns: unused code in Page Objects, and zombie spec files.

**11a. YAGNI in Page Objects** — POM has locators or methods never referenced by any spec. Or a POM class extends a parent with zero additional members (empty wrapper class).

**Procedure:**
1. List all public members of each changed POM file
2. Grep each member across all test files and other POMs
3. Classify: USED / INTERNAL-ONLY (`private`) / UNUSED (delete)
4. Check if any POM class has zero members beyond what it inherits — empty wrappers add no value unless the convention is intentional

**Common patterns:** Convenience wrappers (`clickEdit()` when specs use `editButton.click()`), getter methods (`getCount()` when specs use `toHaveCount()`), state checkers (`isVisible()` when specs assert on locators directly), pre-built "just in case" locators, empty subclass created for future expansion.

**Single-use Util wrappers** — a separate `*Util` / `*Helper` class whose methods are each called from only one test. These add indirection with no reuse benefit; inline them. Keep a Util method only if called from **2+ tests** or invoked **2+ times** within one test.

**Rule:** Delete unused members. Make internal-only members `private`. Apply the 2+ threshold before creating or keeping Util methods — if a helper is called from only one place, inline it. Flag empty wrapper classes for review — they may be intentional convention or dead code.

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

---

## Output Format

Present findings grouped by severity:

```markdown
## [P0/P1/P2] [filename] — [issue type]

### `[test name or POM method]`
- **Issue:** [description]
- **Fix:** [name change / assertion addition / merge / deletion]
- **Code:**
  ```typescript
  // concrete code to add or change
  ```
```

**After all findings, append a summary table and top priorities:**

```markdown
## Review Summary

| Sev | Count | Top Issue | Affected Files |
|-----|-------|-----------|----------------|
| P0  | 3     | Missing Then | auth.spec.ts, form.spec.ts |
| P1  | 5     | Flaky Selectors | settings.spec.ts |
| P2  | 2     | Hard-coded Sleeps | dashboard.spec.ts |

**Total: 10 issues across 4 files.**

### Top 3 Priorities
1. **Remove `test.only`** in auth.spec.ts — CI is running only 1 of 6 tests
2. **Remove try/catch** around assertion in settings.spec.ts — test can never fail
3. **Add assertions** to 4 tests with zero verification (redirect, export, toggle, notification)
```

The "Top N Priorities" section should list the 3-5 highest-impact fixes in concrete, actionable terms. This helps developers know where to start without scanning all P0 findings.

**Severity classification:**
- **P0 (Must fix):** Test silently passes when the feature is broken — no real verification happening
- **P1 (Should fix):** Test works but gives poor diagnostics, wastes CI time, or misleads developers
- **P2 (Nice to fix):** Weak but not wrong — maintenance and robustness improvements

## Quick Reference

| # | Check | Sev | Phase | Detection Signal |
|---|-------|-----|-------|-----------------|
| 1 | Name-Assertion | P0 | LLM | Noun in name with no matching `expect()` |
| 2 | Missing Then | P0 | LLM | Action without final state verification |
| 3 | Error Swallowing | P0 | grep+LLM | `.catch(() => {})` in POM (grep); `try/catch` around assertions in spec (LLM) |
| 4 | Always-Passing | P0 | grep+LLM | `>=0`; `toBeAttached()`; one-shot booleans (`isVisible/textContent/getAttribute`); `locator.toBeTruthy()`; `{ timeout: 0 }` on assertions |
| 5 | Bypass Patterns | P0/P1 | grep | `expect()` inside `if`; `force: true` without `// JUSTIFIED:` |
| 6 | Raw DOM Queries | P1 | grep | `document.querySelector` in `evaluate` |
| 7 | Focused Test Leak | P0 | grep | `test.only(`, `it.only(`, `describe.only(` — no `// JUSTIFIED:` exemption |
| 8 | Missing Assertion | P0 | grep | 8a: `page.locator(...)` standalone; 8b: `await el.isVisible();` standalone — nothing ever asserts |
| 9 | Hard-coded Sleeps | P1 | grep | `waitForTimeout()`, `cy.wait(ms)` |
| 10 | Flaky Test Patterns | P1 | LLM+grep | `nth()` without comment; `test.describe.serial()` |
| 11 | YAGNI + Zombie Specs | P2 | LLM | Unused POM member; empty wrapper; single-use Util; zombie spec file |
| 12 | Missing Auth Setup | P0 | LLM | Spec navigates to protected route without login/storageState/auth beforeEach |
| 13 | Inconsistent POM Usage | P1 | LLM | POM imported but spec uses raw `page.fill`/`page.click` for POM-encapsulated actions |
| 14 | Hardcoded Credentials | P1 | grep | String literals as login credentials; use env vars or test fixtures |
| 15 | Missing await on expect | P0 | grep+LLM | `expect(locator).toBeVisible()` without `await` — assertion never runs |
| 16 | Missing await on action | P0 | grep+LLM | `page.locator(...).click()` without `await` — action may never execute |
| 17 | Deprecated page action API | P1 | grep | `page.click(selector)` instead of `page.locator(selector).click()` |
| 18 | `expect.soft()` overuse | P1 | grep+LLM | >50% soft assertions in a test masks cascading failures |
| 3b | Cypress uncaught:exception suppression | P0 | grep | `cy.on('uncaught:exception', () => false)` globally swallows app errors |

---

## Suppression

When a grep-detected pattern is intentional, add `// JUSTIFIED: [reason]` on the **line immediately above** the flagged line. When reviewing grep hits, if the line immediately above contains `// JUSTIFIED:`, skip the hit. Each individual flagged line needs its own `// JUSTIFIED:` — a comment higher up in the block does not count.

**Exception — #7 Focused Test Leak:** `// JUSTIFIED:` does not suppress `.only` hits. There are no legitimate committed uses of `test.only` / `it.only` / `describe.only` — every hit is P0.
