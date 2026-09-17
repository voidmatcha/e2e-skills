# Upstream Contributions: Track Record and Roadmap

This page tracks self-selected upstream contributions and future candidates. Merged PRs are adoption and case evidence: they show that maintainers accepted specific fixes, but they are not a representative validation set or a product-accuracy estimate. Open false-green fixes show the next contribution queue; reviewer-informed maintenance that does not repair a false-green test is tracked separately.

**Goal:** at least 25 merged upstream PRs. Each merge should be a small, reviewable Playwright/Cypress test-trust fix. Most should target demonstrated false-green behavior; P1 sequencing or diagnostics fixes must be labeled as such rather than counted as silent-pass evidence.

## Cadence and status

- **Merged:** 15 upstream PRs accepted in real projects.
- **In review:** 6 active/open upstream PRs.
- **Closed without merge:** 5. Recorded below rather than dropped; the merge count above is meaningless without them.
- **Generated ledger:** the counts above cover this hand-curated page. [Field review v1](../benchmarks/field-review-v1/README.md) is generated from GitHub for every pull request whose body names the skill and currently records more submissions, merges, and rejections than this page lists. Neither is complete: this page omits some marked pull requests, and the ledger cannot see an unmarked one such as [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486).
- **Upstream tooling:** the always-passing-Locator-assertion smell (`#4f`) was contributed to the official [`eslint-plugin-playwright`](https://github.com/mskelton/eslint-plugin-playwright) as the `no-unnecessary-assertions` rule ([#470](https://github.com/mskelton/eslint-plugin-playwright/pull/470), merged) — tracked separately from the test-fix count below.
- **Queue policy:** prefer high-signal P0 silent-pass fixes; accept concrete P1 sequencing or diagnostics fixes without relabeling them as P0 evidence, and avoid padding with subjective P1/P2 style findings.
- **Submission policy:** one narrow anti-pattern per PR where possible, local verification first, and an `e2e-reviewer` footer only when it is useful context.

## Merged

Selected merged PRs below are sorted roughly by repository recognition, not chronology.

| Repository | ★ | PR | What it fixed | Lesson |
|------------|----|----|---------------|--------|
| Storybook | ★90.4k | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Missing `await` on `fill()` / `blur()`, discarded `isVisible()` checks | Playwright promises must be awaited, and `isVisible()` is a point-in-time query, not a web-first assertion. |
| code-server | ★78.1k | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | `it.only` silently skipped tests for months, plus matcher-less `expect()`, dangling locators, and one-shot visibility reads | Focused-test leaks remove coverage without failing CI; weak checks hide inside the green suite. |
| Strapi | ★72.5k | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | Discarded `isVisible()` / `isHidden()` / `isEnabled()` reads and unawaited clicks | Discarded boolean reads assert nothing, even when they look like the test's main contract. |
| Ghost | ★54.1k | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise-valued disabled-state checks passed without proving button state | Async state checks need awaited web-first assertions. |
| Cal.com | ★45.8k | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | Weak assertions and hard waits in E2E tests | Replacing timing sleeps with web-first checks makes the test fail on real regressions. |
| Bruno | ★45.2k | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | WebSocket visibility assertion was not awaited | Floating assertions race later work and normally surface rejection with degraded attribution. |
| Qwik | ★22k | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Discarded assertion promises, `toBeDefined()` on locators, and bare locators | Locators are handles; only awaited web-first matchers prove rendered state. |
| SvelteKit | ★20.6k | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | Floating web-first assertions | Missing `await` leaves the assertion Promise outside the test's intended sequence and can degrade failure attribution. |
| Element Web | ★13.2k | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Always-passing assertions, unawaited checks, `toBeAttached()` misuse, dead code | Static review can find tests that pass while proving nothing in large E2E suites. |
| FiftyOne | ★10.8k | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Duplicate-name error asserted via locator definition instead of visible UI state | A defined locator proves nothing; assert the error the user actually sees. |
| Carbon Design System | ★9.2k | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | `expect(locator).toBeTruthy()` used as CSS-state verification | Locator truthiness never proves an element exists or is visible. |
| Rancher Desktop | ★7.2k | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `getByText(...).not.toBeNull()` checks replaced with web-first visible assertions for the WSL integration names | A Locator is never `null`; assert the names are actually visible to the user. |
| MUI X | ★5.8k | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | Always-true Locator null check replaced with a real date-time cell edit assertion | Locator objects are never `null`; assert user-visible state instead. |
| Apache Zeppelin | ★6.7k | [apache/zeppelin#5180](https://github.com/apache/zeppelin/pull/5180) | `toBeGreaterThanOrEqual(0)` and `toBeAttached()` on static elements always passed; `if (isVisible) { expect() }` silently skipped | An assertion that cannot fail is not coverage, and a guarded assertion removes coverage without failing. |
| module-federation/core | ★2.6k | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Redundant blanket `uncaught:exception` suppression removed from a Cypress spec | Blanket exception handlers swallow real app errors; suppress only the specific expected error, with a comment. |

## In review

| Repository | ★ | PR | Status | Anti-pattern family |
|------------|----|----|--------|---------------------|
| hcengineering/platform | ★26.3k | [hcengineering/platform#10922](https://github.com/hcengineering/platform/pull/10922) | Open | `expect(locator).toBeDefined()` checks replaced with `toBeVisible()`. |
| TanStack Router | ★14.7k | [TanStack/router#7616](https://github.com/TanStack/router/pull/7616) | Open | Always-passing E2E assertions and missing awaits. |
| ngx-bootstrap | ★5.5k | [valor-software/ngx-bootstrap#6820](https://github.com/valor-software/ngx-bootstrap/pull/6820) | Open | Guarded / non-executing assertions converted into effective checks. |
| Rocket.Chat | ★46.1k | [RocketChat/Rocket.Chat#41792](https://github.com/RocketChat/Rocket.Chat/pull/41792) | Open | Imported users and rooms were never asserted in the import e2e tests. |
| Kong Insomnia | ★40.0k | [Kong/insomnia#10405](https://github.com/Kong/insomnia/pull/10405) | Open | Prompt template tag visibility was not asserted in the smoke test. |
| DefGuard | ★2.7k | [DefGuard/defguard#3146](https://github.com/DefGuard/defguard/pull/3146) | Open | Async `find()` callback selected the wrong row; follow-up `toBeDefined()` was always true. |

## Closed without merge

Every submission that closed without merging, with the reason it closed. They are kept here so the merged count above has a denominator: a merge rate is not a rate until the rejections are counted alongside it.

| Repository | ★ | PR | Why it closed | Anti-pattern family |
|------------|----|----|---------------|---------------------|
| n8n | ★203.5k | [n8n-io/n8n#27035](https://github.com/n8n-io/n8n/pull/27035) | Closed 2026-05-21 without merging. | Hard-coded sleeps and forced hover replaced with conditional waits. |
| Qwik | ★22.1k | [QwikDev/qwik#8727](https://github.com/QwikDev/qwik/pull/8727) | Closed 2026-06-26; superseded by [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777), which merged and is counted above. | Non-asserting e2e checks and missing awaits. |
| Cal.com | ★45.8k | [calcom/cal.diy#28466](https://github.com/calcom/cal.diy/pull/28466) | Closed 2026-03-18; superseded by [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486), which merged and is counted above. | False-passing assertions and brittle waits. |
| Supabase | ★104.8k | [supabase/supabase#47053](https://github.com/supabase/supabase/pull/47053) | Closed 2026-08-20 under the repository's 60-day staleness policy, unreviewed. | One-shot grid-cell text read replaced with web-first text assertion. |
| Expo | ★50.3k | [expo/expo#46699](https://github.com/expo/expo/pull/46699) | Closed 2026-08-14 as superseded; the maintainer pointed to [expo/expo#48706](https://github.com/expo/expo/pull/48706) as where the wait-for-visible assertions landed. Not counted as a merge here. | Router E2E assertions wait for UI state instead of racing. |

## Reviewer-informed maintenance

These contributions came from E2E review but do not fix a false-green test, so they do not change the merged or in-review campaign counts above.

| Repository | ★ | PR | Status | What it changes |
|------------|----|----|--------|-----------------|
| Apache Zeppelin | ★6.7k | [apache/zeppelin#5262](https://github.com/apache/zeppelin/pull/5262) | Merged | Fixes three real races behind a flaky Playwright job (shared session cookie, unbound form control, missing transition waits). A flaky test is not a false-green test, so it is not counted in the campaign above. |
| Apache Zeppelin | ★6.7k | [apache/zeppelin#5348](https://github.com/apache/zeppelin/pull/5348) | Merged | Puts the e2e suite under lint and documents its conventions. The PR states it changes no test behaviour. |
| ToolJet | ★38.5k | [ToolJet/ToolJet#17492](https://github.com/ToolJet/ToolJet/pull/17492) | Open | Removes unused Cypress multipage helper exports (`#11`); maintenance cleanup, not a false-green test fix. |

## Queued

Queue entries must be re-verified against upstream `main` before submission.

| Repository | ★ | Framework | Priority | Finding family |
|------------|----|-----------|----------|----------------|
| Kibana | ★21.2k | Cypress | P0 | Committed focused test skips sibling alert-workflow coverage. |
| Astro | ★60.5k | Playwright | P0/P1 | One-shot state reads and assertion shape review. |
| React Router | ★56.5k | Playwright | P0/P1 | One-shot state reads and weak locator assertions. |
| Material UI | ★98.5k | Playwright | P0/P1 | Locator truthiness / one-shot state assertions. |
| Superset | ★73.5k | Cypress | P0/P1 | Blanket exception suppression and one-shot URL reads. |
| freeCodeCamp | ★450k+ | Playwright | P0/P1 | Weak assertions and guarded checks. |

## Operating rules

- Prefer high-signal merged case evidence over volume: one clear P0 fix is better than several subjective cleanups.
- Keep PRs small enough for maintainers to review in one pass.
- Run the target repo's local test or the narrowest available verification before submission.
- Mention `e2e-skills/e2e-reviewer` only as transparent provenance, not as a sales pitch.
- Update this roadmap when a PR merges, closes, or moves from queue to review.
