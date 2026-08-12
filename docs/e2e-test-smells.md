# E2E Test Smell Taxonomy

This catalog is the public reference behind `e2e-reviewer` and `skills/e2e-reviewer/scripts/scan.sh`. It focuses on tests that pass while proving little, tests that hide application bugs, and tests that fail for reasons unrelated to user behavior.

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
| #4 | Vacuous or retry-weakening assertion (P0/P1) | Invariant predicates and Locator-object truthiness are P0; weak attachment proof, one-shot values/URL, zero-timeout retry/deadline hazards, unproven absence, and an ARIA snapshot that omits a promised accessible name are P1. | Use web-first assertions such as `toBeVisible()`, `toHaveText()`, `toHaveURL()`, and `toHaveAccessibleName()` with finite local bounds. |
| #5 | Bypass pattern | Runtime `if (isVisible)` gates and `{ force: true }` skip the framework checks that should catch broken UI. | Assert the condition directly; use `// JUSTIFIED:` for rare forced actions. |
| #7 | Focused test leak | `test.only`, `it.only`, or `describe.only` makes CI run a subset of the suite. | Remove `.only`; use CLI filters locally. |
| #8 | Missing assertion | A dangling locator or discarded boolean is the scenario's only intended verification. | Confirm no independent verification/failure evidence, then feed the locator into `expect()` or report the missing outcome as #2. |
| #12 | Missing auth setup | Protected-route tests can silently pass when a generic assertion also matches the login or another wrong surface. | Use `storageState`, auth fixtures, or explicit login setup; reserve P0 for demonstrated wrong-surface passes. |

## P1: Fix Before Trusting The Suite

| ID | Smell | Why it matters | Better pattern |
|----|-------|----------------|----------------|
| #6 | Raw DOM query | `document.querySelector` inside browser evaluation bypasses framework retry and actionability. | Use Playwright locators or Cypress queries. |
| #9 | Hard-coded sleep (incl. `cy.wait(ms)` #9b, `waitForLoadState('networkidle')` #9c) | Fixed waits are both slow and still racy. | Wait for UI state, URL state, or a specific network response. |
| #10 | Flaky selector/order pattern | `.nth()`, serial suites, unscoped accessible-name substrings, and Cypress async/assigned/continued action chains couple tests to unstable DOM, order, or command-queue state. | Use scoped semantic locators and self-contained setup; keep Cypress work in its command chain and re-query after actions. |
| #13 | Inconsistent POM usage | Specs bypass a POM that already owns the page, causing duplicate selector maintenance. | Put page interactions behind the existing POM. |
| #14 | Hardcoded credentials | Public repos leak secrets and private repos become tied to one environment. | Use environment variables, fixtures, or test accounts. |
| #15 | Missing await on Playwright expect | The async Locator/Page web-first assertion starts, but its Promise is not sequenced or observed; rejection is normally reported as an unhandled test/worker error with degraded attribution, while resolution can race later work. Sync value matchers are excluded. | `await expect(locator).toBeVisible()`. |
| #16 | Missing await on Playwright action | The action starts without an observed Promise, so actionability, ordering, and navigation can race later work; rejection is normally reported as an unhandled test/worker error with degraded attribution. | `await locator.click()` / `return Promise.all([locator.drop()])`. |
| #17 | Discouraged direct Page selector API | Selector-based Page actions give weaker locator composition, strictness, reuse, and error context. | Use `page.locator(selector).action()` or user-facing locators. |
| #18 | `expect.soft()` overuse | Critical soft assertions before a hard scenario gate let dependent work continue after a broken prerequisite. Playwright still fails the test at the end. | Hard-gate the scenario's primary state first; reserve soft assertions for independent details. |
| #19 | Module-level mutable state in test code | Top-level (column-0) mutable state in a test utility or POM — an initialised `let`, a `var`, or a mutated `const` container — persists across tests within a long-lived worker. Independent worker copies can generate the same supposedly unique value during parallel execution. | Move mutable state behind per-test setup (`beforeEach`, fixtures, or factories), or use runtime-unique values such as `Date.now()` plus random data or `testInfo`-scoped identifiers. |
| #20 | Unmocked real-backend writes | Confirmed writes reach shared or persistent state without a controlled test boundary. | Stub the write or document a disposable container, rollback fixture, isolated tenant/database, or equivalent controlled backend. |
| #22 | Optimistic UI without call proof | A write-control click asserted only via optimistically-updated UI can pass while the request never fires or fails server-side. | Pair the UI assertion with request proof: `page.waitForRequest()` / route-hit flag / `cy.wait('@alias')`. |

## P2: Maintainability

| ID | Smell | Why it matters | Better pattern |
|----|-------|----------------|----------------|
| #11 | YAGNI POM/util code + zombie specs | Unused locators, empty wrappers, single-use helpers, and specs that duplicate another file's coverage hide real coverage and slow review. | Delete unused members; inline single-use helpers; delete zombie spec files or merge unique assertions into the stronger suite. |
| #21 | Manually-captured session-file dependency | `storageState` JSON produced only by a human-run capture script rots silently — suites fail when the session expires and nobody remembers why. | Generate auth state programmatically in a setup project (API login + `storageState` write) on every run. |
| #23 | Fixture ignores render guards | A seeded fixture that fails the display component's early-return guards renders nothing — the test asserts on an empty view. | Mirror every guard condition of the component under test in the fixture (e.g. `liked: true` for a Liked view). |

## Review Surface Beyond Grep

Some high-value checks need human or agent judgment:

- Does the suite cover error paths, empty states, edge cases, and role boundaries?
- Are third-party services mocked or avoided?
- Are route/intercept handlers registered before navigation or the triggering action?
- Can every test run alone, in parallel, and under sharding?
- Are accessibility semantics, keyboard navigation, and focus states covered for critical flows?
- Should visual appearance be covered by visual diffing instead of brittle CSS assertions?
