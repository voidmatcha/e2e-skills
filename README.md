# e2e-test-reviewer

A [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) skill that catches quality issues in E2E tests that pass CI but fail to catch real regressions.

## Installation

### Recommended (clone directly)

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/<your-username>/e2e-test-reviewer.git ~/.claude/skills/e2e-test-reviewer
```

### Manual (skill file only)

```bash
mkdir -p ~/.claude/skills/e2e-test-reviewer
cp skills/e2e-test-reviewer/SKILL.md ~/.claude/skills/e2e-test-reviewer/
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

## 12 Patterns Detected (with Before/After)

### Reliability Patterns

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 7 | **Always-passing assertion** | `expect(count).toBeGreaterThanOrEqual(0)` | `expect(count).toBeGreaterThan(0)` |
| 8 | **Conditional assertion** | `if (visible) { expect(x).toBeHidden() }` | `await expect(x).toBeVisible(); await expect(x).toBeHidden()` |
| 9 | **Error swallowing** | `try { ... } catch { console.log() }` | Let errors fail the test |
| 11 | **Conditional skip** | `if (!ready) { test.skip(); return }` | Move env checks to `beforeEach` |

### Naming & Completeness

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 1 | **Name-assertion mismatch** | Name says "status" but only checks `toBeVisible()` | Add assertion for status content, or rename |
| 2 | **Missing Then** | Cancel action, verify text restored — input still visible? | Verify both `text.toBeVisible()` and `input.toBeHidden()` |
| 5 | **Misleading name** | `should add a paragraph` (uses REST API) | `should reflect paragraph added via API after reload` |

### Assertion Quality

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 3 | **Render-only test** | `expect(title).toBeVisible()` | Add `expect(title).not.toBeEmpty()` |
| 6 | **Over-broad assertion** | `expect(s.includes('%')).toBe(true)` | `expect(['%python', '%md']).toContain(s)` |
| 10 | **Boolean trap** | `expect(isVisible).toBe(true)` | `await expect(element).toBeVisible()` |

### Code Maintenance

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 4 | **Duplicate scenario** | Two tests share 90% of steps | Merge into one comprehensive test |
| 12 | **Unused Page Object member** | `clickEdit()` never called by any spec | Delete or make `private` |

## Compatibility

Framework-agnostic. Examples use [Playwright](https://playwright.dev/) syntax, but the checks apply to any E2E test suite with a Page Object Model pattern (Cypress, Selenium, etc).

## Key Insight

> AI-generated E2E tests tend toward the statistically likely result — visibility checks that always pass, loose assertions that accept anything, and convenience methods that nobody calls. This skill catches what CI misses: **tests that pass but prove nothing**.

## License

Apache-2.0 — same as [anthropics/skills](https://github.com/anthropics/skills).
