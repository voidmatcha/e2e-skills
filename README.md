# e2e-skills

A [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) plugin with three complementary E2E testing skills designed to work together:

1. **`e2e-reviewer`** — finds issues in your tests and suggests fixes (Playwright, Cypress, Puppeteer)
2. **`playwright-debugger`** — diagnoses failures from `playwright-report/` after you apply fixes and re-run
3. **`cypress-debugger`** — diagnoses failures from Cypress report files after you apply fixes and re-run

The typical workflow:

1. Run `e2e-reviewer` → fix issues → re-run tests
2. If tests fail → run `playwright-debugger` or `cypress-debugger` → fix → re-run tests
3. Once tests pass → run `e2e-reviewer` again to confirm no new issues

## Installation

```bash
# npx skills (recommended)
npx skills install dididy/e2e-skills

# Claude Code plugin marketplace
/plugin marketplace add dididy/e2e-skills
/plugin install e2e-skills@dididy

# Clone directly
mkdir -p ~/.claude/skills
git clone https://github.com/dididy/e2e-skills.git ~/.claude/skills/e2e-skills
```

---

## Skill 1: `e2e-reviewer` — Quality Review

Catches issues in E2E tests that pass CI but fail to catch real regressions.

### When to Use

- Your tests always pass but you suspect they don't catch real bugs
- You want to audit test quality before a release
- You're reviewing Playwright, Cypress, or Puppeteer specs
- You need to justify test coverage in a code review

### Usage

```
Review these E2E tests for quality
Audit the spec files in tests/
Are there any always-passing tests?
My tests pass CI but I think they miss regressions
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

## Skill 2: `playwright-debugger` — Failure Debugger

Diagnoses Playwright test failures from a `playwright-report/` directory — whether failures happened locally or in CI. Classifies root causes and provides concrete fixes.

### When to Use

- You have a `playwright-report/` directory (local or downloaded from CI) with failures to understand
- Tests pass locally but fail in CI
- You're dealing with flaky or intermittent test failures
- You get `TimeoutError` or `locator not found` without a clear cause

### Usage

```
Debug these failing tests
Why did these tests fail?
Tests pass locally but fail in CI
```

> **Note:** Provide the report as a local path. Download CI artifacts manually from GitHub Actions and pass the directory path — automatic artifact fetching is not supported.

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
3. **Trace** — if still unclear, extract `trace.zip` and inspect step-by-step: failed actions, DOM snapshots, network errors, JS console errors
4. **Fix** — concrete code suggestion per failure, P0/P1/P2 priority

---

## Skill 3: `cypress-debugger` — Cypress Failure Debugger

Diagnoses Cypress test failures from mochawesome or JUnit report files. Classifies root causes and provides concrete fixes.

### When to Use

- You have a `cypress/reports/` directory (local or downloaded from CI) with failures to understand
- Cypress tests pass locally but fail in CI
- You're dealing with flaky or intermittent Cypress failures
- You get `Timed out retrying` or `Expected to find element` without a clear cause

### Usage

```
Debug these failing Cypress tests
Why did these Cypress tests fail?
Analyze cypress/reports/
Cypress tests pass locally but fail in CI
```

### 14 Root Cause Categories

| # | Category | Signals |
|---|----------|---------|
| F1 | **Flaky / Timing** | `Timed out retrying`, passes on retry |
| F2 | **Selector Broken** | `Expected to find element`, `cy.get() failed` |
| F3 | **Network Dependency** | `cy.intercept()` not matched, `XHR failed` |
| F4 | **Assertion Mismatch** | `expected X to equal Y`, `AssertionError` |
| F5 | **Missing Then** | Action completed but wrong state remains |
| F6 | **Condition Branch Missing** | Element conditionally present, assertion always runs |
| F7 | **Test Isolation Failure** | Passes alone, fails in suite |
| F8 | **Environment Mismatch** | CI vs local only; baseUrl, viewport, OS |
| F9 | **Data Dependency** | Missing seed data, `cy.fixture()` mismatch |
| F10 | **Auth / Session** | `cy.session()` expired, role-based UI not rendered |
| F11 | **Async Order Assumption** | `.then()` chain order, parallel `cy.request()` race |
| F12 | **Selector Drift** | DOM changed, custom command or POM selector not updated |
| F13 | **Error Swallowing** | `cy.on('uncaught:exception', () => false)` hiding failures |
| F14 | **Animation Race** | Element visible but content not yet rendered |

### Debug Workflow

1. **Extract** — parse `mochawesome.json` or JUnit XML for failed tests, error messages, duration
2. **Classify** — map each failure to F1–F14 using error signals (most failures resolved here)
3. **Screenshot/Video** — if still unclear, inspect `cypress/screenshots/` and `cypress/videos/`
4. **Fix** — concrete code suggestion per failure, P0/P1/P2 priority

---

## Compatibility

**`e2e-reviewer`** — Framework-agnostic. Covers [Playwright](https://playwright.dev/), [Cypress](https://www.cypress.io/), and [Puppeteer](https://pptr.dev/).

**`playwright-debugger`** — Playwright only. Parses `results.json` and `trace.zip` from `playwright-report/`.

**`cypress-debugger`** — Cypress only. Parses `mochawesome.json` or JUnit XML from `cypress/reports/`.

## Key Insight

> AI-generated E2E tests tend toward the statistically likely result — visibility checks that always pass, loose assertions that accept anything, and convenience methods that nobody calls. These skills catch what CI misses: **tests that pass but prove nothing**, and **failures that are hard to trace**.

## License

Apache-2.0 — same as [anthropics/skills](https://github.com/anthropics/skills).
