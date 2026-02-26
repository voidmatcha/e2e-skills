---
name: e2e-test-reviewer
description: Use when reviewing, auditing, or improving existing E2E test specs. Triggers on tasks like "review tests", "improve test quality", "audit specs", "check test scenarios". Detects naming-assertion mismatch, missing Then, duplicate scenarios, render-only tests, over-broad assertions, always-passing assertions, error swallowing, boolean traps, and YAGNI violations in Page Objects.
---

# E2E Test Scenario Quality Review

Systematic checklist for reviewing E2E spec files against YAGNI, DRY, KISS, and SOLID principles. Framework-agnostic but examples use Playwright syntax.

## When to Use

- Reviewing existing spec files for quality
- After generating new E2E tests (post-generation audit)
- Periodic spec hygiene sweeps
- When test suites grow large and need cleanup

## Review Checklist

Run each check against every **non-skipped** test in the target spec files.

### 1. Name-Assertion Alignment (KISS)

**Symptom:** Test name promises something the assertions don't verify.

```typescript
// BAD: Name says "status" but only checks visibility
test('should display paragraph status', () => {
  await expect(status).toBeVisible();  // Where's the status content check?
});

// GOOD: Name matches what's actually verified
test('should display paragraph control area', () => {
  await expect(status).toBeVisible();
  await expect(settingsDropdown).toBeVisible();
});
```

**Rule:** Every noun in the test name must have a corresponding assertion. If the assertion is missing, either add it or rename the test.

### 2. Missing Then (Incomplete Verification)

**Symptom:** Test performs actions but doesn't verify the final expected state.

```typescript
// BAD: Toggles but doesn't verify the reverse state
test('should cancel edit on Escape', () => {
  await input.click();                    // enter edit mode
  await page.keyboard.press('Escape');
  await expect(text).toBeVisible();       // text is back...
  // BUT: is the input actually hidden?
});

// GOOD: Verify both sides of the state change
test('should cancel edit on Escape', () => {
  await input.click();
  await page.keyboard.press('Escape');
  await expect(text).toBeVisible();
  await expect(input).toBeHidden();
});
```

**Rule:** For toggle/cancel/close actions, verify both the restored state AND the dismissed state.

### 3. Render-Only Tests (Low E2E Value)

**Symptom:** Test only calls `toBeVisible()` with no interaction or content assertion.

```typescript
// LOW VALUE: Pure render check
test('should display title', () => {
  await expect(title.container).toBeVisible();
});

// HIGHER VALUE: Render + content
test('should display title', () => {
  await expect(title.text).toBeVisible();
  await expect(title.text).not.toBeEmpty();
});
```

**Rule:** Strengthen render-only tests by adding at least one of:
- Content assertion (`not.toBeEmpty()`, `toContainText()`)
- Count assertion (`toHaveCount(n)`)
- Sibling element assertion (related controls visible alongside main element)

### 4. Duplicate Scenarios (DRY)

**Symptom:** Two tests share >70% of their steps with minor variations.

```typescript
// BAD: Test 2 and Test 3 do nearly the same thing
test('should show modal and allow running', ...);
test('should show modal for items without results', ...);

// GOOD: Merge into one comprehensive test
test('should show confirmation modal with preview and allow running', ...);
```

**Rule:** If two tests differ only in setup or a single assertion, merge them. Use the richer verification set from both.

### 5. Misleading Test Names

**Symptom:** Name implies UI interaction but test uses API/REST, or name implies feature X but tests feature Y.

```typescript
// BAD: Sounds like UI action, but uses REST API + reload
test('should add a new paragraph', ...);

// GOOD: Name reflects actual mechanism
test('should reflect paragraph added via API after reload', ...);
```

**Rule:** If the test uses REST API, reload, or indirect methods, the name must make that explicit.

### 6. Over-Broad Assertions (KISS)

**Symptom:** Assertion is too loose to catch regressions.

```typescript
// BAD: Any string containing '%' passes
expect(content.includes('%')).toBe(true);

// GOOD: Explicit expected values
expect(['', '%python', '%md']).toContain(content.trim());
```

**Rule:** Prefer exact matches or explicit value lists over `.includes()` or loose regex when the set of valid values is known and small.

### 7. Always-Passing Assertions (Tautology)

**Symptom:** Assertion that can never fail regardless of application state.

```typescript
// BAD: count >= 0 is always true
const count = await items.count();
expect(count).toBeGreaterThanOrEqual(0);

// GOOD: Assert meaningful minimum
await expect(items).toHaveCount(5);
// or at least:
expect(count).toBeGreaterThan(0);
```

**Rule:** Search for `toBeGreaterThanOrEqual(0)`, `toBeTruthy()` on strings that are always truthy, and `||` chains in `expect().toBe(true)` that accept empty/default values as valid.

### 8. Conditional Assertions (Silent Pass)

**Symptom:** `expect()` inside an `if` block — when the condition is false, the test passes without asserting anything.

```typescript
// BAD: If spinner is not visible, assertion never runs — test passes silently
if (await spinner.isVisible()) {
  await expect(spinner).toBeHidden({ timeout: 5000 });
}

// GOOD: Always assert
await expect(spinner).toBeVisible();
await expect(spinner).toBeHidden({ timeout: 5000 });
```

Also catches: `if (count > 0) { /* all assertions here */ } else { console.log('skipped'); }`

**Rule:** Every test path must contain at least one `expect()`. If a condition might skip assertions, the test setup is wrong, not the assertion.

### 9. Error Swallowing (try/catch)

**Symptom:** Test catches errors and logs instead of failing.

```typescript
// BAD: Test passes even on timeout/network error
try {
  await page.goto('/dashboard');
  await expect(header).toBeVisible();
} catch (error) {
  console.log('Navigation skipped:', error);
}

// GOOD: Let errors fail the test. Use test.fixme() or test.skip() if known broken
test('should navigate to dashboard', async ({ page }) => {
  await page.goto('/dashboard');
  await expect(header).toBeVisible();
});
```

**Rule:** Never wrap assertions in try/catch. If the test can't run in certain environments, use `test.skip()` with a clear reason in `beforeEach`, not a silent catch.

### 10. Boolean Trap Assertions

**Symptom:** `expect(complexCondition).toBe(true)` — when it fails, error message is just "expected false to be true" with no diagnostic context.

```typescript
// BAD: Failure message is useless
const isVisible = await element.isVisible();
expect(isVisible).toBe(true);

// GOOD: Playwright auto-retries and gives clear error
await expect(element).toBeVisible();
```

```typescript
// BAD: Which condition failed?
expect(a === 'x' || b === 'y').toBe(true);

// GOOD: Separate assertions with clear messages
expect(a).toBe('x');
// or if genuinely OR:
expect([a, b]).toEqual(expect.arrayContaining(['x']));
```

**Rule:** Replace `expect(bool).toBe(true/false)` with specific matchers (`toBeVisible()`, `toContainText()`, `toHaveCount()`). If unavoidable, add a message: `expect(condition, 'element should be in edit mode').toBe(true)`.

### 11. Conditional Skip Hiding Failures

**Symptom:** Mid-test `test.skip()` inside a condition — test silently skips when the feature is broken.

```typescript
// BAD: If autocomplete is broken, test reports "skipped" not "failed"
const isVisible = await autocomplete.isVisible();
if (!isVisible) {
  test.skip();
  return;
}

// GOOD: If autocomplete is expected, fail. If environment-dependent, skip in beforeEach
test.beforeEach(({ page }) => {
  test.skip(!hasAutoComplete, 'Autocomplete not available in this environment');
});
```

**Rule:** Mid-test skips mask failures. Move environment checks to `beforeEach`. If the feature should work, let the test fail.

### 12. YAGNI in Page Objects (Unused Members Audit)

**Symptom:** Page Object Model has locators/methods never referenced by any spec.

**Procedure:**
1. For each changed/staged Page Object file, list all public members (properties, sub-properties, methods)
2. Grep each member name across all test files and other Page Objects
3. Classify each member:

| Status | Meaning | Action |
|--------|---------|--------|
| USED | Referenced in 1+ spec or Page Object | Keep |
| INTERNAL-ONLY | Used only by other methods in same class | Change to `private` |
| UNUSED | Not referenced anywhere outside definition | Delete |

**Common YAGNI patterns to catch:**
- Convenience wrappers: `clickEdit()` when specs use `editButton.click()` directly
- Getter methods: `getItemCount()` when specs use `toHaveCount()` assertion
- State checkers: `isEditMode()` when specs assert on visible elements directly
- Pre-built locators: `addLinks` defined "just in case"
- Sub-properties in composed objects: `title.container` when only `title.text` is used

**Rule:** Delete unused members. Make internal-only members `private`. Shared utility methods must be used by 2+ specs or be deleted.

**Output:** Include YAGNI audit table in findings:
```
| File | Member | Used In | Status |
|------|--------|---------|--------|
| item-page.ts | addLinks | (none) | DELETE |
| form-page.ts | searchDialog | internal only | PRIVATE |
```

## Output Format

Present findings as a plan with:

```markdown
## Task N: [filename] - [issue type]

### N-1. `[test name]`
- **Issue:** [description]
- **Fix:** [name change / assertion addition / merge / deletion]
- **Code:**
  ```typescript
  // concrete code to add or change
  ```
```

## Verification

After applying fixes:
```bash
# Type check (adjust path to your tsconfig)
npx tsc --noEmit --project e2e/tsconfig.json

# Run affected tests
npx playwright test --project=chromium [changed files]
```

## Quick Reference

| Check | Principle | Detection Signal |
|-------|-----------|-----------------|
| Name-Assertion mismatch | KISS | Noun in name with no matching `expect()` |
| Missing Then | Complete | Action without final state verification |
| Render-only | E2E value | Only `toBeVisible()`, no content/count |
| Duplicate scenario | DRY | >70% shared steps between tests |
| Misleading name | KISS | API/reload in "should [UI verb]" test |
| Over-broad assertion | KISS | `.includes()` where enum values known |
| Always-passing assertion | Tautology | `>=0`, truthy on non-empty strings |
| Conditional assertion | Silent pass | `expect()` inside `if` block |
| Error swallowing | Reliability | `try/catch` around assertions |
| Boolean trap | Debuggability | `expect(bool).toBe(true)` |
| Conditional skip | Reliability | Mid-test `test.skip()` inside `if` |
| Unused Page Object member | YAGNI | Property/method not referenced in any spec |
| Internal-only member | SRP | Public member used only within same class |
| Convenience wrapper | YAGNI | `clickX()` wrapping `xButton.click()` |
