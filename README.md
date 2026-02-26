# e2e-review-test-quality

A Claude Code skill for reviewing E2E test spec quality against YAGNI, DRY, KISS, and SOLID principles.

## What it does

Provides a systematic 7-point checklist for auditing E2E test specs:

1. **Name-Assertion Alignment** — Test name matches what assertions verify
2. **Missing Then** — Toggle/cancel/close actions verify both states
3. **Render-Only Tests** — Strengthen pure visibility checks with content/count assertions
4. **Duplicate Scenarios** — Merge tests sharing >70% of steps
5. **Misleading Names** — Names reflect actual mechanism (API vs UI)
6. **Over-Broad Assertions** — Explicit values over loose `.includes()`
7. **YAGNI in Page Objects** — Delete unused locators/methods, privatize internal-only members

## Install

### As a Claude Code plugin marketplace

```bash
# In Claude Code
/plugin marketplace add <your-github-username>/e2e-review-test-quality
```

### Manual install

```bash
cd ~/.claude/skills
git clone https://github.com/<your-github-username>/e2e-review-test-quality.git
```

## Usage

The skill triggers automatically when you ask Claude Code to review or audit E2E test specs. Examples:

- "Review these E2E tests for quality"
- "Audit the spec files in tests/notebook/"
- "Check test scenarios for issues"
- "Find unused Page Object members"

## Framework

Framework-agnostic, but examples use [Playwright](https://playwright.dev/) syntax. Works with any Page Object Model-based E2E test suite.

## License

Apache-2.0
