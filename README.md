# e2e-test-reviewer

A [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) skill that catches quality issues in E2E tests that pass CI but fail to catch real regressions.

## Installation

### npx skills (recommended)

```bash
npx skills install dididy/e2e-test-reviewer
```

### Marketplace

```shell
/plugin marketplace add dididy/e2e-test-reviewer
/plugin install e2e-test-reviewer@dididy
```

### Clone directly

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/dididy/e2e-test-reviewer.git ~/.claude/skills/e2e-test-reviewer
```

## Usage

In Claude Code, ask naturally:

```
Review these E2E tests for quality
```
```
Audit the spec files in tests/
```
```
Are there any always-passing tests?
```

## 14 Patterns Detected

### Tier 1 — High-Impact Bugs (always check)

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 1 | **Name-assertion mismatch** | Name says "status" but only checks `toBeVisible()` | Add assertion for status content, or rename |
| 2 | **Missing Then** | Cancel action, verify text restored — input still visible? | Verify both `text.toBeVisible()` and `input.toBeHidden()` |
| 3 | **Error swallowing** | `try/catch` in spec, `.catch(() => {})` in POM | Let errors fail; remove silent catch from POM methods |
| 4 | **Always-passing assertion** | `expect(count).toBeGreaterThanOrEqual(0)` | `expect(count).toBeGreaterThan(0)` |
| 5 | **Boolean trap** | POM returns `Promise<boolean>`, spec does `expect(bool).toBe(true)` | POM exposes element handle, spec uses framework assertion |
| 6 | **Conditional bypass** | `if (visible) { expect(...) }` or mid-test `test.skip()` | Always assert; move env checks to `beforeEach` |
| 7 | **Raw DOM queries** | `document.querySelector` in `evaluate()` | Use framework element API (`locator` / `cy.get` / `page.$`) |

### Tier 2 — Quality Improvements (check when time permits)

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 8 | **Render-only test** | `expect(title).toBeVisible()` | Add `expect(title).not.toBeEmpty()` |
| 9 | **Duplicate scenario** | Two tests share 90% of steps (within or cross-file) | Merge into one comprehensive test |
| 10 | **Misleading name** | `should add a paragraph` (uses REST API) | `should reflect paragraph added via API after reload` |
| 11 | **Over-broad assertion** | `expect(s.includes('%')).toBe(true)` | `expect(['%python', '%md']).toContain(s)` |
| 12 | **Hard-coded timeout** | `waitForTimeout(2000)` / `cy.wait(2000)` | Rely on framework auto-wait; extract named constants |
| 13 | **Flaky selectors** | `items.nth(2).toContainText('Settings')` | Use `data-testid`, role-based, or attribute selectors |
| 14 | **Unused Page Object member** | `clickEdit()` never called by any spec | Delete unused members or make `private`; do not delete actively-used util files |

## Compatibility

Framework-agnostic principles with framework-specific guidance for [Playwright](https://playwright.dev/), [Cypress](https://www.cypress.io/), and [Puppeteer](https://pptr.dev/). Checks apply to any E2E test suite with a Page Object Model pattern.

## Key Insight

> AI-generated E2E tests tend toward the statistically likely result — visibility checks that always pass, loose assertions that accept anything, and convenience methods that nobody calls. This skill catches what CI misses: **tests that pass but prove nothing**.

## License

Apache-2.0 — same as [anthropics/skills](https://github.com/anthropics/skills).
