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

## In review

| Repository | PR | Anti-pattern family |
|------------|----|---------------------|
| expo | [expo/expo#46699](https://github.com/expo/expo/pull/46699) | Unawaited web-first assertions in router E2E |
| Qwik | [QwikDev/qwik#8727](https://github.com/QwikDev/qwik/pull/8727) | Discarded assertion promises, `toBeDefined()` on locators, bare locators |
| TanStack Router | [TanStack/router#7616](https://github.com/TanStack/router/pull/7616) | `expect(locator).toBeTruthy()` (always true), masked expected-value typo |
| Strapi | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | One-shot reads, missing `await`, discarded `isVisible/isHidden/isEnabled`, unawaited clicks |

## Queued

Candidates prepared in the local testbed (branch + signed commit + preflight green),
pending a fresh convention check before opening. Each is a single anti-pattern family.

| Repository | Framework | Anti-pattern family |
|------------|-----------|---------------------|
| web-infra-dev/rspack | Playwright | One-shot `textContent()` reads to web-first `toHaveText` |
| Kong/kong-manager | Playwright | Discarded `isVisible`/`innerText`/`count` to web-first assertions |
| supabase/supabase | Playwright | Grid-cell `textContent()` to `toHaveText` |
| clerk/javascript | Playwright | `count` / discarded `isVisible` / URL reads to web-first |
| mui/material-ui | Playwright | `page.isVisible()` to `toBeVisible`/`toBeHidden` |
| freeCodeCamp/freeCodeCamp | Playwright | Discarded `isVisible`/`isEnabled`, `.all().toBeTruthy()` to `toHaveCount` |
| Shopify/hydrogen | Playwright | URL reads to `toHaveURL` / `expect.poll` |
| saleor/saleor-dashboard | Playwright | Checkbox `isChecked` to `toBeChecked`, discarded `isVisible` |
| woocommerce/woocommerce | Playwright | Padded `page.url()` to `expect.poll` |
| WordPress/gutenberg | Playwright | `searchParams.get()` / `count` to `expect.poll` |
| direktiv/direktiv | Playwright | Missing `await` on web-first matchers (#15) |
| surveyjs/survey-library | Playwright | One-shot `textContent()` to `toHaveText` |
| CourtHive/TMX | Playwright | One-shot `isVisible()` to `toBeVisible` |
| walkframe/gridsheet | Playwright | One-shot `textContent()` to `toHaveText` |
| openobserve/openobserve | Playwright | One-shot `isVisible()` to `toBeVisible` |
| coveo/search-ui | Playwright | One-shot `textContent()` to `toHaveText` |
| mui/mui-x | Playwright | Matcher-less always-true assertion to a real assertion |
| nhost/nhost | Playwright | Missing `await` on `expect()` (#15) |
| frappe/frappe | Cypress | Committed `it.only` removed (restores skipped suite) |
| module-federation/core | Cypress | Redundant blanket `uncaught:exception` handler removed |
| RocketChat/Rocket.Chat | Playwright | Matcher-less `expect(locator)` to `await expect(locator).toBeVisible()` in the admin import spec |

## Backlog

Scored candidates from the research corpus, not yet prepared. Ranked by a blend of
merge likelihood, finding quality, effort, and finding freshness. The `Patterns`
column lists the anti-pattern IDs the scan surfaced (see
[`docs/e2e-test-smells.md`](e2e-test-smells.md) for the ID legend).

| Repository | Framework | Patterns |
|------------|-----------|----------|
| Kong/insomnia | Playwright | #8b |
| actual | Playwright | #4c-4e, #4h |
| jupyterlab/jupyterlab | Playwright | #4c-4e, #8b |
| react-router | Playwright | #4c-4e, #15 |
| TryGhost/Ghost | Playwright | #4c, #4d, #4e, #4f, #4h |
| sveltejs/kit | Playwright | #4c-4e, #4e, #4h, #15 |
| carbon-design-system/carbon | Playwright | #4f |
| vendure | Playwright | #3, #5a |
| react-navigation | Playwright | #4c |
| uptime-kuma | Playwright | #4x, #8b |
| superset | Cypress | #3b, #4h |
| astro | Playwright | #4c-4e |
| usebruno/bruno | Playwright | #3, #4c, #15 |
| xyflow | Cypress | #3, #3b, #4b |
| hcengineering/platform (Huly) | Playwright | #4, #4c-4e, #4x, #8b, #9 |
| vercel/ai-chatbot | Playwright | #2, #3, #10a |
| builderio | Playwright | #4c-4e |
| rallly | Playwright | #3, #15 |
| penpot/penpot | Playwright | #4c, #4c-4e, #4h, #8b |
| mattermost/mattermost | Playwright | #4a, #4c-4e, #4h, #8b, #15 |
| kestra | Playwright | #4f, #15 |
| handsontable/handsontable | Playwright | #4c-4e, #9 |
| microsoft/fluentui | Playwright | #4h |
| semi-design | Cypress | #3b, #5b, #9b |
| plasmicapp/plasmic | Playwright | #4, #4h, #8b |
| lightdash | Cypress | #3b, #7 |
| redwoodjs/redwood | Playwright | #4, #4f, #4h |
| ag-grid/ag-grid | Playwright | #4c, #15 |
| elementor | Playwright | #4, #8b |
