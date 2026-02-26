# e2e-test-reviewer

A [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) skill for reviewing E2E test spec quality against YAGNI, DRY, KISS, and SOLID principles.

## The Problem

AI-generated E2E tests often contain subtle quality issues that silently pass CI but fail to catch real regressions:

| Issue | Impact |
|-------|--------|
| `expect(count).toBeGreaterThanOrEqual(0)` | Always passes — validates nothing |
| `try { ... } catch { console.log(...) }` | Errors swallowed — test never fails |
| `if (visible) { expect(...) }` | Assertion skipped — silent pass |
| `expect(bool).toBe(true)` | Failure says "expected false to be true" — no context |
| Test name says "status" but only checks visibility | Name-assertion mismatch |
| Two tests share 90% of steps | Duplicate maintenance burden |

## What it Does

Provides a systematic **12-point checklist** for auditing E2E test specs:

| # | Check | Principle |
|---|-------|-----------|
| 1 | Name-Assertion Alignment | KISS |
| 2 | Missing Then (incomplete toggle/cancel verification) | Completeness |
| 3 | Render-Only Tests (low E2E value) | E2E Value |
| 4 | Duplicate Scenarios | DRY |
| 5 | Misleading Test Names | KISS |
| 6 | Over-Broad Assertions | KISS |
| 7 | Always-Passing Assertions (tautology) | Reliability |
| 8 | Conditional Assertions (silent pass) | Reliability |
| 9 | Error Swallowing (try/catch) | Reliability |
| 10 | Boolean Trap Assertions | Debuggability |
| 11 | Conditional Skip Hiding Failures | Reliability |
| 12 | YAGNI in Page Objects (unused members audit) | YAGNI |

## Install

### As a Claude Code plugin

```bash
/install-plugin <your-github-username>/e2e-test-reviewer
```

### Manual

```bash
cd ~/.claude/skills
git clone https://github.com/<your-github-username>/e2e-test-reviewer.git
```

## Usage

The skill triggers automatically when you ask Claude Code to review or audit E2E test specs:

- "Review these E2E tests for quality"
- "Audit the spec files in tests/"
- "Check test scenarios for issues"
- "Find unused Page Object members"
- "Are there any always-passing tests?"

## Compatibility

Framework-agnostic. Examples use [Playwright](https://playwright.dev/) syntax, but the checks apply to any E2E test suite with a Page Object Model pattern (Cypress, Selenium, etc).

## License

Apache-2.0 — same as [anthropics/skills](https://github.com/anthropics/skills).
