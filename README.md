# e2e-test-skill

A [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) plugin with two complementary E2E testing skills: one for reviewing test quality, one for debugging failures.

## Installation

### npx skills (recommended)

```bash
npx skills install dididy/e2e-test-skill
```

### Marketplace

```shell
/plugin marketplace add dididy/e2e-test-skill
/plugin install e2e-test-skill@dididy
```

### Clone directly

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/dididy/e2e-test-skills.git ~/.claude/skills/e2e-test-skill
```

---

## Skill 1: `e2e-test-reviewer` — Quality Review

Catches issues in E2E tests that pass CI but fail to catch real regressions.

### Usage

```
Review these E2E tests for quality
Audit the spec files in tests/
Are there any always-passing tests?
```

### 14 Patterns Detected

#### Tier 1 — P0/P1 (always check)

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 1 | **Name-assertion mismatch** | Name says "status" but only checks `toBeVisible()` | Add assertion for status content, or rename |
| 2 | **Missing Then** | Cancel action, verify text restored — input still visible? | Verify both `text.toBeVisible()` and `input.toBeHidden()` |
| 3 | **Error swallowing** | `try/catch` in spec, `.catch(() => {})` in POM | Let errors fail; remove silent catch from POM methods |
| 4 | **Always-passing assertion** | `expect(count).toBeGreaterThanOrEqual(0)` | `expect(count).toBeGreaterThan(0)` |
| 5 | **Boolean trap** | `expect(locator).toBeTruthy()` on non-boolean objects (always passes) | Use framework assertion (`toBeVisible()`); skip when value is actual boolean like `response.ok()` |
| 6 | **Conditional bypass** | `if (visible) { expect(...) }` or mid-test `test.skip()` | Always assert; move env checks to `beforeEach` |
| 7 | **Raw DOM queries** | `document.querySelector` in `evaluate()` | Use framework element API (`locator` / `cy.get` / `page.$`) |

#### Tier 2 — P1/P2 (check when time permits)

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 8 | **Render-only test** | `expect(title).toBeVisible()` | Add `expect(title).not.toBeEmpty()` |
| 9 | **Duplicate scenario** | Two tests share 90% of steps (within or cross-file) | Merge into one comprehensive test |
| 10 | **Misleading name** | `should add a paragraph` (uses REST API) | `should reflect paragraph added via API after reload` |
| 11 | **Over-broad assertion** | `expect(s.includes('%')).toBe(true)` | `expect(['%python', '%md']).toContain(s)` |
| 11b | **Subject-inversion** | `expect([200, 202]).toContain(status)` | `expect(status === 200 \|\| status === 202).toBe(true)` |
| 12 | **Hard-coded timeout** | `waitForTimeout(2000)` / `cy.wait(2000)` | Rely on framework auto-wait; extract named constants |
| 13 | **Flaky patterns** | `items.nth(2).toContainText('Settings')` | Use `data-testid`, role-based selectors; mock network; wait for animation completion |
| 14 | **Unused Page Object member** | `clickEdit()` never called by any spec | Delete unused members or make `private`; do not delete actively-used util files |

### Review Workflow

Three-phase review with P0/P1/P2 severity:

1. **Phase 1: Automated grep** — mechanically detects error swallowing, always-passing, boolean traps, conditional bypass, raw DOM, timeouts, missing network mocks
2. **Phase 2: LLM analysis** — semantic checks for naming, missing assertions, duplicates, flaky patterns, YAGNI
3. **Phase 3: Coverage gaps** — suggests missing error paths, edge cases, accessibility, and auth boundary tests

---

## Skill 2: `e2e-test-debugger` — Failure Debugger

Diagnoses Playwright test failures from report files. Classifies root causes and provides concrete fixes.

### Usage

```
Debug these failing tests
Why did these tests fail?
Analyze playwright-report/
Investigate CI failures
```

### 14 Root Cause Categories

| # | Category | Signals |
|---|----------|---------|
| F1 | **Flaky / Timing** | `TimeoutError`, passes on retry |
| F2 | **Selector Broken** | `locator not found`, strict mode violation |
| F3 | **Network Dependency** | `net::ERR_*`, unexpected API response |
| F4 | **Assertion Mismatch** | `Expected X to equal Y`, subject-inversion |
| F5 | **Missing Then** | Action completed but wrong state remains |
| F6 | **Condition Branch Missing** | Element conditionally present, assertion always runs |
| F7 | **Test Isolation Failure** | Passes alone, fails in suite |
| F8 | **Environment Mismatch** | CI vs local only; viewport, OS, timezone |
| F9 | **Data Dependency** | Missing seed data, hardcoded IDs |
| F10 | **Auth / Session** | Session expired, role-based UI not rendered |
| F11 | **Async Order Assumption** | `Promise.all` order, parallel race |
| F12 | **POM / Locator Drift** | DOM structure changed, POM not updated |
| F13 | **Error Swallowing** | `.catch(() => {})` hiding actual failure |
| F14 | **Animation Race** | Element visible but content not yet rendered |

### Debug Workflow

1. **Extract** — parse `results.json` for failed tests, error messages, duration
2. **Classify** — map each failure to F1–F14 using error signals (most failures resolved here)
3. **Trace** — if still unclear, parse `trace.zip` directly (`unzip -p | node`) for step-by-step analysis
4. **Fix** — concrete code suggestion per failure, P0/P1/P2 priority

Trace analysis uses direct zip parsing (`unzip` + `node`) — no extra dependencies required.

---

## Compatibility

Framework-agnostic principles with framework-specific guidance for [Playwright](https://playwright.dev/), [Cypress](https://www.cypress.io/), and [Puppeteer](https://pptr.dev/).

## Key Insight

> AI-generated E2E tests tend toward the statistically likely result — visibility checks that always pass, loose assertions that accept anything, and convenience methods that nobody calls. These skills catch what CI misses: **tests that pass but prove nothing**, and **failures that are hard to trace**.

## License

Apache-2.0 — same as [anthropics/skills](https://github.com/anthropics/skills).
