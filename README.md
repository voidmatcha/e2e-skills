# e2e-skills — Playwright and Cypress E2E Test Generation, Review, and Debugging

E2E tests that always pass are worse than no tests — they give false confidence while real bugs slip through. `e2e-skills` is an AI agent testing toolkit for Playwright and Cypress: generate end-to-end tests, review existing specs for false positives and test smells, debug flaky E2E failures, and turn noisy CI reports into root-cause fixes. It runs as an Agent Skills bundle for [Claude Code](https://claude.com/product/claude-code) and [Codex](https://github.com/openai/codex) (and other [`AGENTS.md`](https://agents.md)-compatible runtimes via the `skills` CLI) by [@voidmatcha](https://github.com/voidmatcha), catching what CI misses: **tests that pass but prove nothing**, and **failures that are hard to trace**.

Four complementary skills cover the full E2E testing lifecycle, from Playwright test generation to Cypress test review and failure debugging:

1. **`playwright-test-generator`** — generates Playwright E2E tests from scratch, from coverage gap analysis to passing, reviewed tests
2. **`e2e-reviewer`** — static analysis of existing Playwright and Cypress specs; flags 24 anti-patterns (P0 silent always-pass, P1 poor diagnostics, P2 maintenance) that can make tests pass CI while missing real regressions
3. **`playwright-debugger`** — diagnoses failures from `playwright-report/` and classifies root causes (flaky timing, selector drift, auth, environment mismatch, and more)
4. **`cypress-debugger`** — same for Cypress report files

### Contents

- [Install](#install) · [Workflow](#workflow) · [Standalone scanner](#standalone-scanner) · [Proven in OSS](#proven-in-open-source)
- Skills: [generator](#skill-1-playwright-test-generator--test-generation) · [reviewer](#skill-2-e2e-reviewer--quality-review) · [playwright-debugger](#skill-3-playwright-debugger--playwright-failure-debugger) · [cypress-debugger](#skill-4-cypress-debugger--cypress-failure-debugger)
- [License](#license)

## Install

```bash
# Recommended — install for Claude Code + Codex (most common)
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code -a codex

# Install everywhere — every agent the `skills` CLI supports
npx skills add voidmatcha/e2e-skills --skill '*' -g --agent '*'

# Claude Code plugin marketplace
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha

# Manual clone (Claude Code)
git clone https://github.com/voidmatcha/e2e-skills.git ~/.claude/skills/e2e-skills
```

Codex users: install via the `npx skills add` route above (`-a codex` drops the bundle into `~/.codex/skills/`, where Codex auto-discovers it).

### Quick Example

```
You: Review my Playwright tests in apps/viewer/src/test/

e2e-reviewer:

  [P0] settings.spec.ts:88, 99 — #4h One-shot URL read
    expect(page.url()).toEqual(`${baseURL}/${id}-public`);   // sync read, no auto-retry
    → fix: await expect(page).toHaveURL(`${baseURL}/${id}-public`);
    (also removes redundant `await page.waitForTimeout(1000)` above)

  [P0] fileUpload.spec.ts:67 — #16 Missing await on action
    page.getByRole('button', { name: 'Delete' }).click();   // fire-and-forget, races next line
    → fix: await page.getByRole('button', { name: 'Delete' }).click();

  Total: 3 P0 (2 #4h, 1 #16), 0 P1, 0 P2 in 24 spec files.
  P1/P2 candidates (not yet flagged as bugs): 20× positional .nth() selectors, 5× direct page.click(selector).
```

Real findings from a recent typebot.io scan — silent always-pass bugs your test suite was hiding.

### Workflow

1. Run `playwright-test-generator` → generate with approval → auto-reviewed by `e2e-reviewer`
2. Generated tests fail → `playwright-debugger` invoked automatically after 3 fix attempts
3. Existing tests: `e2e-reviewer` → fix → re-run
4. Tests fail → `playwright-debugger` or `cypress-debugger` → fix → re-run

### Standalone Scanner

```bash
./skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

Three tiers run in priority order: (1) `eslint-plugin-playwright` / `eslint-plugin-cypress` — uses your local install if present, otherwise auto-downloads via `npx --yes` (set `E2E_SMELL_NO_ESLINT_DOWNLOAD=1` to disable); (2) `ast-grep` Tree-sitter rules for FP-prone patterns — uses `ast-grep` / `sg` on PATH if present, otherwise auto-downloads via `npx --yes @ast-grep/cli` (set `E2E_SMELL_NO_AST_GREP_DOWNLOAD=1` to disable); (3) bundled regex coverage for grep-detectable P0/P1/P2 patterns and gaps the lint plugins miss — Cypress `cy.on('uncaught:exception', () => false)` blanket suppression (#3b), `{timeout:0}.should("not.exist")` (#4g), and cross-framework heuristics. See [`docs/e2e-test-smells.md`](docs/e2e-test-smells.md) for the full P0/P1/P2 model. Use `// JUSTIFIED: <reason>` on (or in the comment block directly above) an intentional pattern to suppress it in the bundled scanner output; the eslint tier does not parse JUSTIFIED markers — pair with an `eslint-disable` comment there if needed. The eslint tier also runs under a hang watchdog (`E2E_SMELL_ESLINT_TIMEOUT_SECS`, default 300s) and never blocks Tier 2/3 coverage when it fails.

The `e2e-reviewer` skill adds what no lint can reach: semantic checks (name-assertion mismatch, missing Then, YAGNI/zombie specs, POM consistency, auth setup analysis) and fix guidance with band-aid awareness. Run [`eslint-plugin-playwright`](https://github.com/playwright-community/eslint-plugin-playwright) / [`eslint-plugin-cypress`](https://github.com/cypress-io/eslint-plugin-cypress) as your every-commit baseline; invoke the skill for PR review, suspected silent-pass bugs, or before bulk fixes.

### Proven in Open Source

Three real merged PRs, not synthetic examples:

| Repository | Merged PR | What it fixed |
|------------|-----------|---------------|
| Cal.com | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | False-passing Playwright assertions, no-op state checks, hard-coded waits → web-first assertions + condition waits |
| Storybook | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Unawaited Playwright actions and discarded `isVisible()` calls that made E2E checks silently weak |
| Element Web | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Always-passing assertions, unawaited checks, `toBeAttached()` misuse, debugging leftovers |

The skill was further iterated against 13 OSS Playwright/Cypress repos (1k+ stars) in a local testbed — zero GitHub side effects. The 4.4 cycle-count rule, 4.2 PR-culture cross-check, and Phase 2 retry-wrapper skip all came from observed agent behavior in those runs. See [`docs/case-studies.md`](docs/case-studies.md) for before/after lessons.

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

1. **Detect environment** — config, baseURL, test dir, POM structure, existing conventions doc
2. **Coverage gap analysis** — user picks target (skipped when target given as argument)
3. **Live browser exploration** — via agent-browser tools (no hallucinated selectors); accessible-name reality check for label-less inputs
4. **Scenario design + approval gate** — shows plan and locator table before any code
5. **Code generation** — POM + spec or flat spec, auto-detected from project conventions; writes must be route-stubbed (see Network Determinism in `code-rules.md`)
6. **Conventions & seed scaffolding** (first run on a project) — appends a project-adapted E2E section to `AGENTS.md` and designates a seed spec, so future AI-generated tests (Claude Code, Codex, Playwright Agents) stay consistent
7. **YAGNI audit + e2e-reviewer** — removes unused locators, catches P0 issues before first run
8. **TS compile + test run** — 3 auto-fix attempts on failure (heal-by-intent locator re-resolution), then hands off to `playwright-debugger`

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

### 24 Patterns Detected — Grouped by Severity

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
| 9 | **Hard-coded sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | Rely on framework auto-wait; use condition-based waits |
| 10 | **Flaky test patterns** | `items.nth(2)` without comment; `test.describe.serial()` | Use `data-testid` or role selectors; replace serial with self-contained tests |
| 13 | **Inconsistent POM usage** | POM imported but spec uses raw `page.fill`/`page.click` for POM-owned actions | Route all interactions through the POM so UI changes update in one place |
| 14 | **Hardcoded credentials** | `loginPage.login('demo-admin', '<literal-password>')` in test code | Use `process.env.TEST_USER`, Playwright config secrets, or test data fixtures |
| 17 | **Direct `page.click(selector)` API** | `page.click('#submit')` / `page.fill('#input', 'text')` skips the Locator layer | Use `page.locator(selector).click()` for auto-wait and better error messages |
| 18 | **`expect.soft()` overuse** | All assertions in a test are `expect.soft()` — test never fails early | Ensure at least one hard `expect()` gates per test; use `soft` only for independent details |
| 19 | **Module-level mutable state in test code** | `let testNotebookSequence = 0;` at column 0 in a test utility — collides across parallel workers and survives retries | Drop the counter; derive uniqueness from `Date.now()` + `Math.random().toString(36).slice(2, 8)`, or move state into `test.beforeEach` |
| 20 | **Unmocked real-backend writes** | Signup/checkout spec submits real mutations — every CI run creates real accounts/orders | Stub write/credential endpoints with `page.route()` / `cy.intercept()`; one designated real-backend smoke spec max |
| 22 | **Optimistic UI without call proof** | Like-toggle test asserts `aria-pressed` flip — UI updates optimistically, passes with the POST deleted | Pair UI assertion with `page.waitForRequest()` (armed before the click) or a route-hit flag |

#### P2 — Nice to Fix (maintenance / robustness)

Weak but not wrong — addressed when refactoring.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | `clickEdit()` never called; empty wrapper class; single-use Util; entire spec duplicated by another | Delete unused members; inline single-use Util methods; delete zombie spec files |
| 21 | **Manually-captured session-file dependency** | `storageState: 'auth/member.json'` produced only by a manual capture script — absent on CI, silently expires | Regenerate session programmatically (API-login helper or `setup` project); manual files only as a cache with a programmatic fallback |
| 23 | **Fixture ignores render guards** | Liked-tab fixture seeds `liked: false`; the card component `return null`s every item — empty UI looks like infra flake | Read the item component's early returns/filters before seeding; seed fields to pass every guard for the view under test |

### References

[Playwright best practices](https://playwright.dev/docs/best-practices) · [Cypress best practices](https://docs.cypress.io/app/core-concepts/best-practices) · [Testing Library guiding principles](https://testing-library.com/docs/guiding-principles)

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
| F11 | **Command Queue / Intercept Race** | `cy.intercept` registered after request fires; `.then()` chain order swap; parallel `cy.request()` race against an unfinished `cy.visit()` |
| F12 | **Selector Drift** | DOM changed, custom command or POM selector not updated |
| F13 | **Error Swallowing** | `cy.on('uncaught:exception', () => false)` hiding failures |
| F14 | **Animation Race** | Element visible but content not yet rendered |

### Debug Workflow

1. **Extract** — parse `mochawesome.json` or JUnit XML for failed tests, error messages, duration
2. **Classify** — map each failure to F1–F14 using error signals (most failures resolved here)
3. **Screenshot/Video** — if still unclear, inspect `cypress/screenshots/` and `cypress/videos/`
4. **Fix** — concrete code suggestion per failure, P0/P1/P2 priority

---

## License

Apache-2.0. See [LICENSE.txt](./LICENSE.txt).
