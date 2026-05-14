# E2E Test Smell Taxonomy

This catalog is the public reference behind `e2e-reviewer` and `scripts/e2e-smell-scan.sh`. It focuses on tests that pass while proving little, tests that hide application bugs, and tests that fail for reasons unrelated to user behavior.

## Evidence Levels

Not every rule has the same kind of evidence. Treat mechanical checks as prompts for review, not as a replacement for reading the test.

| Evidence | Meaning | Examples |
|----------|---------|----------|
| Official practice | Matches Playwright/Cypress guidance or framework behavior. | Web-first assertions, user-facing locators, avoiding hard waits, avoiding focused tests in committed code. |
| Mechanical signal | Grep can reliably flag a suspicious pattern, but a reviewer may still need context. | `{ force: true }`, `.nth()`, `toBeAttached()`, `document.querySelector`. |
| Semantic heuristic | Requires human or LLM judgment over the test intent and surrounding code. | Name-assertion mismatch, missing Then, YAGNI POM members, zombie specs. |

The standalone scanner only fails CI on P0 findings by default. P1/P2 findings are review signals unless the project chooses a stricter threshold.

## P0: Must Fix

| ID | Smell | Why it matters | Better pattern |
|----|-------|----------------|----------------|
| #1 | Name-assertion mismatch | The test name promises coverage the assertions never verify. | Add assertions for each important noun, or rename the test. |
| #2 | Missing Then | The test performs an action but never verifies the final user-visible state. | Assert the expected result and the dismissed/removed prior state. |
| #3 | Error swallowing | `try/catch`, `.catch(() => {})` in POM/spec hide failures. | Let the error fail the test; scope and justify known third-party noise. |
| #3b | Cypress `uncaught:exception` suppression | `cy.on('uncaught:exception', () => false)` globally swallows app errors; can mask real production bugs. | Scope the handler to specific known errors and re-throw anything unexpected. |
| #4 | Always-passing assertion | Assertions like `toBeGreaterThanOrEqual(0)`, `expect(locator).toBeTruthy()`, or `toBeAttached()` can pass when the feature is broken. | Use web-first assertions such as `toBeVisible()`, `toHaveText()`, `toHaveURL()`, and meaningful bounds. |
| #5 | Bypass pattern | Runtime `if (isVisible)` gates and `{ force: true }` skip the framework checks that should catch broken UI. | Assert the condition directly; use `// JUSTIFIED:` for rare forced actions. |
| #7 | Focused test leak | `test.only`, `it.only`, or `describe.only` makes CI run a subset of the suite. | Remove `.only`; use CLI filters locally. |
| #8 | Missing assertion | Dangling locators and discarded booleans execute no verification. | Feed locators into `expect()`, an action, or a later used variable. |
| #12 | Missing auth setup | Protected-route tests can pass against a login redirect instead of the intended feature. | Use `storageState`, auth fixtures, or explicit login setup. |
| #15 | Missing await on Playwright expect | The assertion promise is created but never observed. | `await expect(locator).toBeVisible()`. |
| #16 | Missing await on Playwright action | Actions can run out of order or not finish before assertions. | `await locator.click()` / `await locator.fill(value)`. |

## P1: Fix Before Trusting The Suite

| ID | Smell | Why it matters | Better pattern |
|----|-------|----------------|----------------|
| #6 | Raw DOM query | `document.querySelector` inside browser evaluation bypasses framework retry and actionability. | Use Playwright locators or Cypress queries. |
| #9 | Hard-coded sleep | Fixed waits are both slow and still racy. | Wait for UI state, URL state, or a specific network response. |
| #10 | Flaky selector/order pattern | `.nth()`, `.first()`, `.last()`, and serial suites couple tests to DOM/order. | Use role, label, test ID, or self-contained setup. |
| #13 | Inconsistent POM usage | Specs bypass a POM that already owns the page, causing duplicate selector maintenance. | Put page interactions behind the existing POM. |
| #14 | Hardcoded credentials | Public repos leak secrets and private repos become tied to one environment. | Use environment variables, fixtures, or test accounts. |
| #17 | Direct page action API | `page.click(selector)` and friends give weaker locator semantics and poorer errors. | Use `page.locator(selector).click()` or user-facing locators. |
| #18 | `expect.soft()` overuse | A test with mostly soft assertions may continue after the primary condition is broken. | Keep at least one hard assertion for the scenario's main outcome. |

## P2: Maintainability

| ID | Smell | Why it matters | Better pattern |
|----|-------|----------------|----------------|
| #11 | YAGNI POM/util code + zombie specs | Unused locators, empty wrappers, single-use helpers, and specs that duplicate another file's coverage hide real coverage and slow review. | Delete unused members; inline single-use helpers; delete zombie spec files or merge unique assertions into the stronger suite. |

## Review Surface Beyond Grep

Some high-value checks need human or agent judgment:

- Does the suite cover error paths, empty states, edge cases, and role boundaries?
- Are third-party services mocked or avoided?
- Are route/intercept handlers registered before navigation or the triggering action?
- Can every test run alone, in parallel, and under sharding?
- Are accessibility semantics, keyboard navigation, and focus states covered for critical flows?
- Should visual appearance be covered by visual diffing instead of brittle CSS assertions?
