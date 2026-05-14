# e2e-skills — E2E Test Generation, Review, and Debugging

E2E tests that always pass are worse than no tests — they give false confidence while real bugs slip through. An Agent Skills bundle for [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview), Codex, and OpenCode by [@voidmatcha](https://github.com/voidmatcha) that catches what CI misses: **tests that pass but prove nothing**, and **failures that are hard to trace**.

Four complementary skills that cover the full E2E lifecycle:

1. **`playwright-test-generator`** — generates Playwright E2E tests from scratch, from coverage gap analysis to passing, reviewed tests
2. **`e2e-reviewer`** — static analysis of existing Playwright and Cypress specs; flags 19 anti-patterns (P0 silent always-pass, P1 poor diagnostics, P2 maintenance) that can make tests pass CI while missing real regressions
3. **`playwright-debugger`** — diagnoses failures from `playwright-report/` and classifies root causes (flaky timing, selector drift, auth, environment mismatch, and more)
4. **`cypress-debugger`** — same for Cypress report files

### Contents

- [Workflow](#workflow) · [Standalone scanner](#standalone-scanner) · [Open source proof](#proven-in-open-source) · [Installation](#installation)
- Skills: [generator](#skill-1-playwright-test-generator--test-generation) · [reviewer](#skill-2-e2e-reviewer--quality-review) · [playwright-debugger](#skill-3-playwright-debugger--playwright-failure-debugger) · [cypress-debugger](#skill-4-cypress-debugger--cypress-failure-debugger)
- [Comparison with other tools](#comparison-with-other-tools) · [FAQ](#faq) · [Compatibility](#compatibility)

### Workflow

1. Run `playwright-test-generator` → generate with approval → auto-reviewed by `e2e-reviewer`
2. Generated tests fail → `playwright-debugger` invoked automatically after 3 fix attempts
3. Existing tests: `e2e-reviewer` → fix → re-run
4. Tests fail → `playwright-debugger` or `cypress-debugger` → fix → re-run

### Standalone Scanner

Run the mechanical smell checks without an agent:

```bash
./scripts/e2e-smell-scan.sh path/to/tests

# Report only, never fail CI
E2E_SMELL_FAIL_ON=none ./scripts/e2e-smell-scan.sh .

# Fail on any finding, not just P0
E2E_SMELL_FAIL_ON=any ./scripts/e2e-smell-scan.sh .
```

The scanner is intentionally conservative as a first pass: it catches obvious P0/P1 smells, then `e2e-reviewer` handles semantic review and false-positive judgment. It reports justified patterns too; use `// JUSTIFIED:` to explain intent for human and agent review, not to hide findings.

### Proven in Open Source

The checklist is grounded in real merged OSS work, not just synthetic examples:

| Repository | Merged PR | What it fixed |
|------------|-----------|---------------|
| Cal.com | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | Replaced false-passing Playwright assertions, no-op state checks, and hard-coded waits with web-first assertions and condition waits |
| Storybook | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Fixed unawaited Playwright actions and discarded `isVisible()` calls that made E2E checks silently weak |
| Element Web | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Removed always-passing assertions, unawaited checks, `toBeAttached()` misuse, and debugging leftovers |

See [Open Source Case Studies](docs/case-studies.md) for short before/after lessons from these PRs.

### Open Source Assets

| Asset | Purpose |
|-------|---------|
| [E2E Test Smell Taxonomy](docs/e2e-test-smells.md) | Shareable reference for the P0/P1/P2 smell model |
| [`scripts/e2e-smell-scan.sh`](scripts/e2e-smell-scan.sh) | Agent-free scanner for obvious E2E smell patterns |
| [`scripts/ci/ci-local.sh`](scripts/ci/ci-local.sh) | Local mirror for convention, security, eval, scanner, and pattern/description parity checks |
| [GitHub Action](.github/workflows/e2e-smell-scan.yml) | CI example that runs convention/security checks, scanner checks, and uploads a report |
| [Evals](docs/evals.md) | How to validate and extend skill eval definitions |
| [Framework Scope](docs/framework-scope.md) | Explicit Playwright/Cypress support boundary |
| [Agent Compatibility](docs/agent-compatibility.md) | Claude Code, Codex, and OpenCode setup notes |

## Installation

```bash
# Claude Code / Codex / OpenCode quick install: install all four skills
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code -a codex -a opencode

# If the skills CLI is already installed, skip npx:
skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code -a codex -a opencode

# Install to every supported agent instead:
npx skills add voidmatcha/e2e-skills --skill '*' -g --agent '*'

# Alternative: Claude Code plugin marketplace
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha

# Codex plugin (registered via the Codex marketplace UI; reads .codex-plugin/plugin.json)

# Claude Code manual clone
mkdir -p ~/.claude/skills
git clone https://github.com/voidmatcha/e2e-skills.git ~/.claude/skills/e2e-skills
```

---

## Skill 1: `playwright-test-generator` — Test Generation

Generates Playwright E2E tests from scratch for any project. Starts from coverage gap analysis, explores the live app via agent-browser tools, designs scenarios with your approval, and auto-reviews generated tests with `e2e-reviewer`.

### When to Use

- You have a page or feature with no E2E coverage
- You want to bootstrap a test suite for an existing app
- You need to quickly add tests before a release

### Usage

```
Generate playwright tests
Generate playwright tests for the login page
Write e2e tests for the settings page
Add playwright coverage for checkout flow
```

### Pipeline

```
Step 1: Detect environment (config, baseURL, test dir, POM structure)
Step 2: Coverage gap analysis → user picks target
Step 3: Live browser exploration via agent-browser tools
Step 4: Scenario design → approval gate → user approves
Step 5: Code generation (POM + spec or flat spec, auto-detected)
Step 6: YAGNI audit + e2e-reviewer quality gate
Step 7: TS compile + test run → playwright-debugger on failure
```

### Key Behaviors

- **Structure-aware**: detects POM pattern and matches project conventions
- **No hallucinated selectors**: explores real DOM before writing any code
- **Approval gate**: shows scenario plan and locator table before generating code
- **Quality loop**: YAGNI audit removes unused locators; `e2e-reviewer` catches P0 issues before you ever run the tests
- **Self-healing**: 3 auto-fix attempts on failure, then hands off to `playwright-debugger`

---

## Skill 2: `e2e-reviewer` — Quality Review

Catches issues in E2E tests that pass CI but fail to catch real regressions.

### When to Use

- Your tests always pass but bugs still slip through to production
- Tests pass CI but you suspect they miss real regressions
- Your test suite is fragile — tests break on every UI change
- You want to audit test quality before a release or code review
- You're reviewing Playwright or Cypress specs

### Usage

```
Review my E2E tests
Audit the spec files in tests/
Find weak tests in my test suite
My tests always pass but miss bugs
Tests pass CI but miss regressions
My tests are fragile and break on every UI change
We have coverage but bugs still slip through
```

### 19 Patterns Detected — Grouped by Severity

#### P0 — Must Fix (silent always-pass)

Tests pass when the feature is broken. No real verification is happening.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 1 | **Name-assertion mismatch** | Name says "status" but only checks `toBeVisible()` | Add assertion for status content, or rename to match actual check |
| 2 | **Missing Then** | Cancel action, verify text restored — but input still visible? | Verify both restored state and dismissed state |
| 3 | **Error swallowing** | `try/catch` in spec, `.catch(() => {})` in POM | Let errors fail; remove silent catch from POM methods |
| 3b | **Cypress `uncaught:exception` suppression** | `cy.on('uncaught:exception', () => false)` blanket-swallows app errors | Scope handler to specific known errors; re-throw unknown errors |
| 4 | **Always-passing assertion** | `toBeGreaterThanOrEqual(0)`; `toBeAttached()` with no comment; `expect(await el.isVisible()).toBe(true)` (one-shot); `expect(await el.textContent()).toBe(x)` (one-shot); `expect(locator).toBeTruthy()` (Locator always truthy); `{ timeout: 0 }` on assertions (disables retry) | `toBeGreaterThan(0)`; `toBeVisible()`; web-first assertions with auto-retry |
| 5 | **Bypass patterns** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`; `{ force: true }` without comment | Always assert; move env checks to `beforeEach`; add `// JUSTIFIED:` to force:true |
| 7 | **Focused test leak** | `test.only(...)` committed — CI runs one test, silently skips the rest | Delete `.only`; use `--grep` or `--spec` for local focus |
| 8 | **Missing assertion** | `await page.locator('.x');` (discarded); `await el.isVisible();` (boolean thrown away) | Add `await expect(locator).toBeVisible()` or delete the line |
| 12 | **Missing auth setup** | Protected-route spec navigates to `/dashboard` with no login/`storageState`/auth fixture | Add `beforeEach` login, configure `storageState`, or use auth fixture — otherwise test passes against the login page |
| 15 | **Missing `await` on `expect()`** | `expect(page.locator('.toast')).toBeVisible()` returns an unobserved Promise | Add `await` so the assertion actually runs |
| 16 | **Missing `await` on action** | `page.locator('#submit').click()` may not execute before the next line | Add `await` so the action completes |

#### P1 — Should Fix (poor diagnostics / wastes CI time)

Tests work but mislead developers, waste CI time, or set up future regressions.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 6 | **Raw DOM queries** | `document.querySelector` in `evaluate()` | Use framework locator/query APIs (`locator` / `cy.get`) |
| 9 | **Hard-coded sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` | Rely on framework auto-wait; use condition-based waits |
| 10 | **Flaky test patterns** | `items.nth(2)` without comment; `test.describe.serial()` | Use `data-testid` or role selectors; replace serial with self-contained tests |
| 13 | **Inconsistent POM usage** | POM imported but spec uses raw `page.fill`/`page.click` for POM-owned actions | Route all interactions through the POM so UI changes update in one place |
| 14 | **Hardcoded credentials** | `loginPage.login('admin', 'password123')` in test code | Use `process.env.TEST_USER`, Playwright config secrets, or test data fixtures |
| 17 | **Direct `page.click(selector)` API** | `page.click('#submit')` / `page.fill('#input', 'text')` skips the Locator layer | Use `page.locator(selector).click()` for auto-wait and better error messages |
| 18 | **`expect.soft()` overuse** | All assertions in a test are `expect.soft()` — test never fails early | Ensure at least one hard `expect()` gates per test; use `soft` only for independent details |

#### P2 — Nice to Fix (maintenance / robustness)

Weak but not wrong — addressed when refactoring.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | `clickEdit()` never called; empty wrapper class; single-use Util; entire spec duplicated by another | Delete unused members; inline single-use Util methods; delete zombie spec files |

### Full Review Surface

After the grep and LLM checks, review the suite at the scenario level:

| Area | Review questions |
|------|------------------|
| User intent | Does the test name match the actual assertions? Does every important noun in the scenario get verified? |
| Selector strategy | Are locators based on role, label, accessible name, or stable test IDs instead of CSS classes, XPath, or DOM position? |
| Waiting model | Does the test wait for a real UI, URL, or network signal instead of sleeping? Are Playwright `waitForResponse()` promises created before the triggering action? |
| Isolation and state | Can each test run alone and in parallel? Is state created in `beforeEach` or fixtures rather than inherited from earlier tests? |
| Network boundaries | Are third-party services and flaky/slow APIs mocked or routed? Are route/intercept handlers registered before navigation or the action that fires the request? |
| Auth and permissions | Do protected pages use `storageState`, auth fixtures, or explicit login? Are expired-session and role-boundary states covered? |
| Accessibility | Do flows cover keyboard navigation, focus after dialogs, labels/names for controls, and critical ARIA state? |
| Visual confidence | If the test is mostly checking layout or style, should it use a visual diff instead of many fragile CSS assertions? |
| CI diagnostics | Are Playwright traces captured on first retry, Cypress screenshots/videos or Test Replay available, and reports uploaded as artifacts? |
| Test scope | Is this truly an E2E concern, or should logic-heavy branches move to unit/component/API tests? Are smoke and regression paths separated? |

### References

- [Playwright best practices](https://playwright.dev/docs/best-practices)
- [Playwright locators](https://playwright.dev/docs/locators)
- [Playwright auto-waiting and actionability](https://playwright.dev/docs/actionability)
- [Playwright test isolation](https://playwright.dev/docs/browser-contexts)
- [Playwright authentication](https://playwright.dev/docs/auth)
- [Playwright network mocking](https://playwright.dev/docs/network)
- [Playwright accessibility testing](https://playwright.dev/docs/accessibility-testing)
- [Playwright trace viewer](https://playwright.dev/docs/trace-viewer)
- [Cypress best practices](https://docs.cypress.io/app/core-concepts/best-practices)
- [Cypress test isolation](https://docs.cypress.io/guides/core-concepts/test-isolation)
- [Cypress session](https://docs.cypress.io/api/commands/session)
- [Cypress retry-ability](https://docs.cypress.io/guides/core-concepts/retry-ability)
- [Cypress intercept](https://docs.cypress.io/api/commands/intercept)
- [Cypress screenshots and videos](https://docs.cypress.io/app/guides/screenshots-and-videos)
- [Cypress visual testing](https://docs.cypress.io/guides/tooling/visual-testing)
- [Testing Library guiding principles](https://testing-library.com/docs/guiding-principles)

### Review Workflow

Three-phase review with P0/P1/P2 severity:

1. **Phase 1: Automated grep** — mechanically detects #3 (POM `.catch()`), #3b (Cypress `uncaught:exception`), #4 (always-passing), #5 (bypass patterns), #6 (raw DOM queries), #7 (focused test leak), #8 (missing assertions), #9 (hard-coded sleeps), #10 partial (positional selectors, describe.serial), #14 (hardcoded credentials), #15 (missing await on expect), #16 (missing await on action), #17 (direct page action API), and #18 (`expect.soft()`)
2. **Phase 2: LLM analysis** — #1 name-assertion alignment, #2 missing Then, #3 `try/catch` in specs (context-dependent), #4 `.toBeTruthy()` Locator-subject confirmation, #8 Cypress dangling selectors, #10 flaky pattern judgment, #11 YAGNI + zombie specs, #12 auth setup, #13 POM consistency, #15 missing-await-on-expect Locator confirmation, #16 missing-await-on-action confirmation, and #18 `expect.soft()` overuse confirmation
3. **Phase 3: Coverage gaps** — suggests missing error paths, edge cases, accessibility, auth boundaries, network failure states, visual regressions, and CI observability gaps

---

## Skill 3: `playwright-debugger` — Playwright Failure Debugger

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

## Skill 4: `cypress-debugger` — Cypress Failure Debugger

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

## Comparison with Other Tools

| Tool | What it is | Catches | Limits |
|------|------------|---------|--------|
| **`e2e-reviewer`** (this skill) | Agent skill: grep + LLM semantic review | All 19 anti-patterns including name-assertion mismatch, missing Then, YAGNI/zombie specs | Requires an agent runtime (Claude Code, Codex, or OpenCode) |
| **`e2e-smell-scan.sh`** (this repo) | Standalone shell scanner | Grep-detectable P0/P1 subset (always-passing, `force: true`, `.only`, missing await, hard-coded sleeps) | Misses semantic checks (#1 name-assertion, #2 missing Then, #11 zombie specs) |
| [`eslint-plugin-playwright`](https://github.com/playwright-community/eslint-plugin-playwright) | ESLint plugin | Playwright lint rules: missing await, no-focused-test, no-conditional-in-test | Playwright only; no Cypress; no semantic name-assertion check |
| [Playwright best-practices docs](https://playwright.dev/docs/best-practices) | Reference guide | Official guidance — locators, web-first assertions, isolation | Not enforced; reviewer/scanner needed to catch drift |
| Raw `grep` patterns | DIY | Whatever you write | High false-positive rate without `// JUSTIFIED:` convention |

`e2e-reviewer` is closest in spirit to `eslint-plugin-playwright` but covers both frameworks and adds semantic checks (name-assertion alignment, missing-Then state restoration, zombie specs) that ESLint cannot reason about.

## FAQ

**How is this different from `eslint-plugin-playwright`?**
ESLint catches syntactic patterns (missing await, focused tests, conditional in test). `e2e-reviewer` adds semantic checks an LLM can perform — does the test name match what's asserted, does an action verify both the new state and the dismissed prior state, are POM members actually used. It also covers Cypress.

**Do I need both `e2e-reviewer` and the standalone scanner?**
No. The standalone scanner is a CI-friendly subset for projects without an agent runtime. If you use Claude Code / Codex / OpenCode, `e2e-reviewer` does everything the scanner does plus the LLM-only checks.

**Why do my tests pass CI but still miss bugs?**
The most common causes are name-assertion mismatch (#1), always-passing assertions like `toBeAttached()` or `toBeGreaterThanOrEqual(0)` (#4), missing `await` (#15, #16), and missing auth setup that lets tests pass against the login page (#12). `e2e-reviewer` flags all of these.

**Does this require modifying my existing tests?**
No — `e2e-reviewer` and the debuggers are read-only by default. They produce findings; you decide what to fix. `playwright-test-generator` writes new test files (with your approval at the scenario gate).

**Does it work with TypeScript-only repos?**
Yes. Both Playwright and Cypress projects are detected by config files (`playwright.config.{ts,js}`, `cypress.config.{ts,js}`) and conventional report directories (`playwright-report/`, `cypress/reports/`).

**Can I suppress a false positive?**
Yes — add `// JUSTIFIED: <reason>` on the line above the pattern (or above the enclosing block / multi-line chain). The scanner and reviewer both honor this. Use it to explain intent for the next reviewer, not to silently hide findings.

**Does it support other E2E frameworks?**
No. Scope is explicit: Playwright and Cypress only. See [Framework Scope](docs/framework-scope.md) for the full list of out-of-scope frameworks and the rationale.

## Compatibility

**`playwright-test-generator`** — Playwright only. Generates tests for any project with a `playwright.config.ts`. Uses agent-browser tools for live exploration; falls back to `npx playwright codegen` for manual selector discovery.

**`e2e-reviewer`** — Covers [Playwright](https://playwright.dev/) and [Cypress](https://www.cypress.io/) with full grep + LLM analysis. General principles (name-assertion alignment, missing Then, YAGNI) apply to any framework.

**`playwright-debugger`** — Playwright only. Parses `results.json` and `trace.zip` from `playwright-report/`.

**`cypress-debugger`** — Cypress only. Parses `mochawesome.json` or JUnit XML from `cypress/reports/`.

## License

Apache-2.0 — same as [anthropics/skills](https://github.com/anthropics/skills).
