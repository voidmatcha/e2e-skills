# How to Review AI-Generated Playwright and Cypress E2E Tests

AI-generated E2E tests should be reviewed before merge even when they compile and pass. The key question is not only whether a test is green, but whether it would turn red when the behavior named by the test is broken.

`e2e-reviewer` provides an independent quality gate for Playwright and Cypress specs written or repaired by people, coding agents, Playwright Test Agents, or Cypress AI Skills. It combines deterministic candidates with semantic review, assigns stable pattern IDs and P0/P1/P2 severity, and reports concrete fixes without treating a scanner match as a verdict.

## Quick workflow

1. Generate or repair the test with your normal authoring tool.
2. Review the changed spec, Page Object, fixture, helper, and configuration context with `e2e-reviewer`.
3. Fix confirmed P0/P1/P2 findings without weakening the test's stated outcome.
4. Run the project's approved Playwright or Cypress command.
5. When safe, inject an evidenced fault in a disposable copy and confirm that the test fails at the predicted assertion.

For a Playwright change:

```text
Review the AI-generated Playwright tests under tests/e2e with e2e-reviewer.
Check whether each test proves the behavior named in its title, and attribute
confirmed findings as introduced, worsened, or pre-existing.
```

For a Cypress change:

```text
Review the AI-generated Cypress specs under cypress/e2e with e2e-reviewer.
Check for false-green assertions, swallowed application errors, command-order
races, and tests whose titles promise behavior that their assertions do not prove.
```

## Review one false-green test

This Playwright test passes because it checks the `Locator` object rather than the rendered message:

```typescript
import { expect, test } from '@playwright/test';

test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();
});
```

The deterministic scanner reports the load-bearing line:

```console
$ /bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests/
[P0] #4f Locator always-true assertion (truthy/defined/not-null) (1 hit)
  .../tests/login.spec.ts:5:  expect(page.getByText('Welcome back')).toBeDefined();

Summary: 1 total hit(s), 1 P0
```

Replace the object check with a web-first assertion that observes the page:

```diff
- expect(page.getByText('Welcome back')).toBeDefined();
+ await expect(page.getByText('Welcome back')).toBeVisible();
```

The corrected assertion retries until the message becomes visible and fails if the page never renders it. Run the project test command after the review, then use a safe fault injection when you need stronger proof that the test can fail.

## Read the semantic review result

The scanner reports candidates. A semantic review verifies each candidate against the test title and surrounding project context. This excerpt shows the review contract's load-bearing evidence fields:

```markdown
## Review Scope and Evidence
- **Mode:** diff mode
- **Behavior under review:** dashboard welcome message
- **Diff base/range:** supplied patch
- **Changed E2E artifacts:** tests/login.spec.ts
- **Context-only files consulted:** none
- **Static evidence:** Tier 3 #4f candidate; semantic check confirmed
- **Runtime evidence:** not executed; run the approved Playwright command
- **Independent verification:** V1 recommended; not executed
- **Limitations/exclusions:** application runtime unavailable

## P0 tests/login.spec.ts — #4f Locator object asserted instead of state

### `shows the welcome message`
- **Issue:** `toBeDefined()` observes the Locator, not rendered text
- **Attribution (diff mode):** introduced
- **Fix:** use awaited `toBeVisible()` on the welcome-message Locator
- **Verification:** V1 recommended; not executed
```

The complete report also includes the required summary table and top priorities. The evidence fields separate the mechanical match from the final verdict, attribute the finding, and state what verification remains.

## What to check before merge

| Review question | Failure shape |
| --- | --- |
| Does the primary assertion observe user-visible or system behavior? | A Locator, Chainable, Promise, or handle is asserted instead of its state |
| Would the assertion fail if the named behavior broke? | The test passes against an evidenced product fault |
| Did generation or healing weaken an assertion? | A specific outcome becomes existence, visibility, a broad substring, or no assertion |
| Did the tool suppress an error to get green? | Empty catches, blanket Cypress exception handlers, focused tests, or skips hide failures |
| Does the test prove the side effect it claims? | Optimistic UI is visible but the request, response, or persisted result is not verified |
| Does the test use the project's real context? | Authentication, fixtures, helpers, or configuration are missing or bypassed |

The full reviewer contract contains [24 stable Playwright and Cypress test-smell patterns](e2e-test-smells.md). Some findings require application context; source-only review must not guess when the relevant behavior cannot be observed.

## After Playwright Test Agents

Playwright documents three built-in agents: planner, generator, and healer. The generator produces executable tests from a Markdown plan, and the healer can repair a failing test into a passing or skipped result. Those outputs remain reviewable test changes.

Use `e2e-reviewer` after generation or healing to check that:

- the generated assertions prove the plan's user-visible outcome;
- a healer did not remove, broaden, skip, or replace the load-bearing assertion;
- seed tests, fixtures, and authentication still match the target project's conventions;
- the resulting test can fail for the behavior it claims to protect.

Source: [Playwright Test Agents](https://playwright.dev/docs/test-agents).

## After Cypress AI Skills

Cypress AI Skills can author, review, run, explain, and debug Cypress tests. The official guidance already emphasizes project conventions, missing assertions, brittle selectors, arbitrary waits, and hidden dependencies. `e2e-reviewer` adds a separate cross-framework review pass with stable pattern IDs, PR/diff attribution, false-positive guards, and false-green checks that include blanket `uncaught:exception` suppression.

Use the independent pass after an authoring or repair step, especially when the generated change alters assertions, exception handling, intercept registration, fixtures, or test isolation. The same applies to Cypress Studio's DOM-delta recordings: treat its suggested assertions as review input for this independent pass, not as a final authority, since Studio does not see application code or backend rules.

Sources: [Cypress AI Skills](https://docs.cypress.io/app/tooling/ai-skills), the [Cypress AI Toolkit](https://github.com/cypress-io/ai-toolkit), and [Cypress Studio](https://docs.cypress.io/app/guides/cypress-studio).

## Run the deterministic scanner

The bundled scanner finds the mechanically detectable subset without loading the target project's packages:

```bash
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

Scanner matches are candidates, not final findings. Context-dependent problems such as missing authentication, name/assertion mismatch, and optimistic UI without network proof require semantic review.

## Evidence and claim boundary

This project has behavior-backed development evidence and [14 merged upstream fixes](case-studies.md), but it does not claim generalized reviewer accuracy.

- The archived browser fault matrix completed 36/36 cells (12 fault operators x 3 expected outcomes) across Playwright/Cypress fixtures.
- The exact reviewer benchmark covers 12 proven false-green cases and 12 clean guards.
- The paired Playwright generation example is a development observation, not a framework-wide accuracy estimate.
- Current failed, incomplete, and superseded benchmark rounds remain visible in [Benchmarks and Evidence Status](../benchmarks/STATUS.md).

The executable [React optimistic-write example](../examples/react-optimistic-write/README.md) demonstrates why a visible optimistic state does not by itself prove that a request was sent or persisted.

## Install and start a review

Install the four skills for all supported agents:

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all
```

Then start with one scoped request:

```text
Review the AI-generated Playwright tests in tests/e2e with e2e-reviewer.
```

Review and failure debugging support both Playwright and Cypress. New-test generation currently targets Playwright only.

## Frequently asked questions

### What is a false-green E2E test?

A false-green E2E test passes even when the behavior named in its title is broken. Common causes include asserting a Locator object, swallowing application errors, skipping coverage with a focused test, or checking optimistic UI without proving the side effect.

### Can the deterministic scanner replace semantic review?

No. The scanner finds mechanically detectable candidates. `e2e-reviewer` checks project context, verifies each candidate, and reviews semantic risks that have no reliable grep or abstract syntax tree rule.

### Does `e2e-reviewer` support Playwright and Cypress?

Yes. Review and failure debugging support Playwright and Cypress. New-test generation supports Playwright only.

_Sources and product behavior on this page were rechecked on 2026-09-01._
