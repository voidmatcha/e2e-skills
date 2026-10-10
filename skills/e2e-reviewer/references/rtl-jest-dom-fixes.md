# Conditional RTL / Jest / Vitest `#4f` fix

Read this reference only before proposing or applying a `#4f` fix for an RTL/Testing-Library helper inside an otherwise in-scope Playwright/Cypress spec. It supplies the exact §4.1 row and the prerequisite checks routed from `applying-fixes.md`.

## §4.1 canonical replacement row

| Anti-pattern (#) | Idiomatic fix | Notes |
|------------------|---------------|-------|
| `#4f` `expect(screen.getBy*(...)).toBeTruthy()` | `expect(screen.getBy*(...)).toBeInTheDocument()` | jest-dom matcher — see prereq check below |

Quote that row for the finding's `**§4.1 row:**` attribution.

## Scope boundary

**Scope note (Phase 0 + 4.1 reconciliation):** e2e-reviewer covers Playwright and Cypress only. Pure Jest/Vitest unit tests and Storybook interaction tests are out of scope, even when they use Testing Library helpers; do not report or auto-fix them through this skill. The RTL row applies only when RTL/Testing-Library helpers appear inside an otherwise in-scope Playwright/Cypress spec (rare).

## `#4f` RTL / Jest / Vitest jest-dom prerequisite check (MANDATORY before bulk replacement)

This prerequisite applies only to the React Testing Library / Jest / Vitest row above. Playwright Locators use awaited Playwright assertions such as `await expect(locator).toBeVisible()` or `await expect(locator).toBeAttached()` and must not be converted to jest-dom matchers.

`.toBeInTheDocument()` is a `jest-dom` matcher — without it, the assertion throws `TypeError: expect(...).toBeInTheDocument is not a function`. Verify presence before replacing an RTL assertion:

1. **Search for global setup**:
   ```bash
   rg -l 'jest-dom' jest.config* vitest.config* setupTests* test/setup* __tests__/setup* package.json | head
   ```
   If found in a setup file referenced by `setupFilesAfterEach` (Jest) or `setupFiles` (Vitest config), no per-file import needed.

2. **Check for shared preset**: some monorepos route jest-dom through a shared package (workspace preset, design-system shared setup, internal test-utils). If `jest.config`/`vitest.config` references a preset by name (`preset:` field, `setupFilesAfterEach: ["<package-name>/setup"]`), open the preset's setup file and grep for `jest-dom`. Common shapes: a framework-specific `*-jest-presets` package, a shared design-system test-utils setup, or an internal `@<org>/test-utils` workspace package. Your monorepo's preset name will differ but the pattern is the same.

3. **If neither**: add a per-file import. Choose by test runner:
   - **Jest**: `import '@testing-library/jest-dom';`
   - **Vitest**: `import '@testing-library/jest-dom/vitest';` (the `/vitest` subpath wires `expect.extend` into Vitest's expect — without it, Vitest sees Jest's global expect being extended, not Vitest's)

4. **Sanity check**: after changes, verify package.json includes `@testing-library/jest-dom` (or `@types/testing-library__jest-dom`); if not, add as devDependency.
