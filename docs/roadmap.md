# Contribution Roadmap

e2e-skills is validated by contributing real fixes upstream. This page tracks the
upstream pull requests that the `e2e-reviewer` skill surfaced across open-source
Playwright and Cypress test suites: merged, in review, and queued.

Research runs in a local testbed with zero GitHub side effects (no forks or PRs
opened during scanning). Only vetted fixes become PRs, under a strict bar: one
anti-pattern family per PR, a small diff (roughly <=50 changed lines), assertions
strengthened never removed, and a fresh check of each repo's contribution
conventions before submission.

## Cadence and goal

We keep about **10 PRs open at a time**. Each time one merges (or is declined), we
top the queue back up to 10 from the prepared and backlog lists below, so there is
always a steady, reviewable flow rather than a one-time dump.

**Goal: at least 25 merged PRs.** Each merge is independent, real-world proof that
the skill flags genuine silent-always-pass anti-patterns that maintainers agree are
worth fixing — validation no synthetic benchmark can provide.

## Merged

These merged PRs show the patterns in this repository applied to real projects.

| Repository | PR | What it fixed | Lesson |
|------------|----|---------------|--------|
| Cal.com | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | Locator truthiness, no-op disabled checks, one-shot assertions, hard-coded waits | Green tests are not trustworthy if assertions do not wait for user-visible state. |
| Storybook | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Missing `await` on `fill()`/`blur()`, discarded `isVisible()` checks | Playwright promises must be awaited, and `isVisible()` is a point-in-time query, not a web-first assertion. |
| Element Web | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Always-passing assertions, unawaited checks, `toBeAttached()` misuse, dead code | Static review can find tests that pass while proving nothing in large E2E suites. |
| code-server | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | An `it.only` that silently skipped 8 unit tests for 7 months (one had broken), 4x matcher-less `expect()`, a dangling locator, 16x one-shot `isVisible()` reads | A focused-test leak removes whole suites from CI without ever failing; the gap is invisible until something inside the skipped block regresses. |
| Ghost | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | `expect(likeButton.isDisabled()).toBeTruthy()` x3 plus a one-shot re-enable read in the comments-ui like-button suite | An un-awaited `isDisabled()` returns a Promise that is always truthy, so the debounce-guard tests passed no matter what the button did. |
| SvelteKit | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | Unawaited `expect(page)` web-first assertions in the basics client E2E tests | A floating web-first assertion never runs; the missing `await` is the whole bug, and adding it is what makes the check assert. |

## In review

| Repository | PR | Anti-pattern family |
|------------|----|---------------------|
| expo | [expo/expo#46699](https://github.com/expo/expo/pull/46699) | Unawaited web-first assertions in router E2E |
| Qwik | [QwikDev/qwik#8727](https://github.com/QwikDev/qwik/pull/8727) | Discarded assertion promises, `toBeDefined()` on locators, bare locators |
| TanStack Router | [TanStack/router#7616](https://github.com/TanStack/router/pull/7616) | `expect(locator).toBeTruthy()` (always true), masked expected-value typo |
| Strapi | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | One-shot reads, missing `await`, discarded `isVisible/isHidden/isEnabled`, unawaited clicks |
| supabase | [supabase/supabase#47053](https://github.com/supabase/supabase/pull/47053) | Grid-cell `textContent()` to web-first `toHaveText` |
| module-federation/core | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Redundant blanket `uncaught:exception` suppression removed from the memory-router cypress spec |

## Queued

Highest-conviction candidates: each was necessity-audited (adversarial skeptical-maintainer
re-read of the actual code) and graded **NECESSARY** — a finding a maintainer should accept
because a real bug ships green, retries cannot save it, and it is the sole/headline check of
an active CI test. Ordered most-convincing first. "Prepared" = branch + signed commit +
preflight green in the testbed; the rest are next to prepare. A fresh convention check runs
before any submission.

| Repository | Framework | Why a maintainer must accept |
|------------|-----------|------------------------------|
| mui/mui-x | Playwright | `expect(getByText(...)).not.to.equal(null)` is always true (a Locator is never null) and is the sole check of the dateTime-cell edit; a silently broken edit ships green. Runs in CircleCI. |
| RocketChat/Rocket.Chat | Playwright | Five bare matcher-less `expect(locator)` lines disable every assertion in three CI-gated admin import tests; an import regression passes green. |
| lightdash | Cypress | A committed `it.only` silently skips nine authorization tests in CI; removing it restores coverage. Prepared. (issue-first + Slack claim) |
| frappe/frappe | Cypress | A committed `it.only` (a real maintainer mistake) has silently skipped five sibling awesome-bar tests on every PR since 2026-06-03. Same family as the merged code-server fix. |
| carbon-design-system/carbon | Playwright | Two ProgressIndicator tests whose only assertion is `expect(page.locator(...)).toBeTruthy()` — always true on a Locator, so the CSS-class check never runs. |
| redwoodjs/redwood | Playwright | `expect(locator).toBeTruthy()` is the only check of the requireAuth error UI; it always passes, so a broken auth-error screen ships green. |
| hcengineering/platform | Playwright | Seven bare matcher-less `expect(...)` in recruiting/inbox are terminal no-ops; the modal-closed and calendar checks silently always pass. |
| xyflow | Cypress | `addEdge` never throws, so the lone assertion in graph-utils.cy.ts never executes and the test cannot fail. |
| ag-grid/ag-grid | Playwright | A misplaced `await` leaves `toHaveCount` floating (never asserts); one site is broken-but-green today. Prepared. (CLA) |
| usebruno/bruno | Playwright | A missing `await` leaves the sole connection-visibility assertion floating — silently always passes. Friendly maintainers, no CLA. |
| walkframe/gridsheet | Playwright | A one-shot `textContent()` is the sole, non-retrying check fired right after an async store dispatch; a wrong cell value races and can ship green. |
| direktiv/direktiv | Playwright | Unawaited negative visibility assertions in live CI tests (run.spec.ts); the cancel-closes-dialog check passes unconditionally. (scope to run.spec.ts) |
| plasmicapp/plasmic | Playwright | A one-shot `page.url()` is the sole check while the arena path is pushed in a later await; it races a correct app and can ship green. |
| Kong/kong-manager | Playwright | The negative "invalid expression" test's only check is a discarded `isVisible()` on the form error; an invalid route silently accepted passes green. (scope to the form-error line) |
| louislam/uptime-kuma | Playwright | Five floating web-first assertions, each the sole check of its friendly-name test. Prepared — but submission BLOCKED by the maintainer's AI-PR instant-ban policy; hold until that policy changes. |

## Backlog

Necessity-audited as **WORTHWHILE**: real, idiom-aligned improvements a maintainer would
likely accept, but the suite passes correctly today (the finding is backstopped by an
adjacent assertion, or flakes red rather than silently green). Ordered most-convincing first.
The `Patterns` column lists the anti-pattern IDs the scan surfaced (see
[`docs/e2e-test-smells.md`](e2e-test-smells.md) for the ID legend).

| Repository | Framework | Patterns |
|------------|-----------|----------|
| microsoft/fluentui | Playwright | #4h |
| penpot/penpot | Playwright | #8b, #4c, #4h |
| vercel/ai-chatbot | Playwright | #2, #3, #10a |
| surveyjs/survey-library | Playwright | #4c-4e |
| coveo/search-ui | Playwright | #4c-4e |
| web-infra-dev/rspack | Playwright | #4c-4e |
| saleor/saleor-dashboard | Playwright | #4c, #8b |
| jupyterlab/jupyterlab | Playwright | #4c-4e, #8b |
| react-router | Playwright | #4c-4e, #15 |
| actual | Playwright | #4c-4e, #4h |
| mui/material-ui | Playwright | #4c |
| freeCodeCamp/freeCodeCamp | Playwright | #4f, #8b |
| WordPress/gutenberg | Playwright | #4h |
| Kong/insomnia | Playwright | #8b |
| handsontable/handsontable | Playwright | #4c-4e, #9 |
| vendure | Playwright | #3, #5a |
| CourtHive/TMX | Playwright | #4c |
| nhost/nhost | Playwright | #15 |
| astro | Playwright | #4c-4e |
| openobserve/openobserve | Playwright | #4c |
| builderio | Playwright | #4c-4e |
| rallly | Playwright | #3, #15 |
| react-navigation | Playwright | #4c |
| superset | Cypress | #3b, #4h |
| semi-design | Cypress | #3b, #5b, #9b |
| kestra | Playwright | #4f, #15 |
| elementor | Playwright | #4, #8b |

Dropped in the 2026-06-19 re-audit (declined as churn/marginal, not maintainer-convincing):
clerk/javascript (the "hardened" selector matches nothing, so the check is a no-op before and
after), Shopify/hydrogen (one-shot read is the correct tool for the "did not navigate"
assertion; the other read is on an already-settled URL), woocommerce/woocommerce (the URL
assertions already assert correctly; only SPA flake-hardening), and mattermost/mattermost
(every cited finding is dead code or backstopped at HEAD).
