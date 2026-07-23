# Upstream Contributions: Track Record and Roadmap

`e2e-skills` is validated by contributing real E2E test fixes upstream. This page is both a track record and a contribution roadmap: merged PRs prove maintainers accepted the findings, while open PRs show the next verification queue.

**Goal:** at least 25 merged upstream PRs. Each merge should be a small, reviewable fix for a Playwright/Cypress test that previously passed while proving too little.

## Cadence and status

- **Merged:** 14 upstream PRs accepted in real projects.
- **In review:** 6 active/open upstream PRs.
- **Upstream tooling:** the always-passing-Locator-assertion smell (`#4f`) was contributed to the official [`eslint-plugin-playwright`](https://github.com/mskelton/eslint-plugin-playwright) as the `no-unnecessary-assertions` rule ([#470](https://github.com/mskelton/eslint-plugin-playwright/pull/470), merged) — tracked separately from the test-fix count below.
- **Queue policy:** prefer high-signal P0 silent-pass fixes; avoid padding with subjective P1/P2 style findings.
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
| Bruno | ★45.2k | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | WebSocket visibility assertion was not awaited | Floating assertions can be skipped entirely. |
| Qwik | ★22k | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Discarded assertion promises, `toBeDefined()` on locators, and bare locators | Locators are handles; only awaited web-first matchers prove rendered state. |
| SvelteKit | ★20.6k | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | Floating web-first assertions | Missing `await` can make the assertion never participate in the test outcome. |
| Element Web | ★13.2k | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Always-passing assertions, unawaited checks, `toBeAttached()` misuse, dead code | Static review can find tests that pass while proving nothing in large E2E suites. |
| FiftyOne | ★10.8k | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Duplicate-name error asserted via locator definition instead of visible UI state | A defined locator proves nothing; assert the error the user actually sees. |
| Carbon Design System | ★9.2k | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | `expect(locator).toBeTruthy()` used as CSS-state verification | Locator truthiness never proves an element exists or is visible. |
| Rancher Desktop | ★7.2k | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `getByText(...).not.toBeNull()` checks replaced with web-first visible assertions for the WSL integration names | A Locator is never `null`; assert the names are actually visible to the user. |
| MUI X | ★5.8k | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | Always-true Locator null check replaced with a real date-time cell edit assertion | Locator objects are never `null`; assert user-visible state instead. |
| module-federation/core | ★2.6k | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Redundant blanket `uncaught:exception` suppression removed from a Cypress spec | Blanket exception handlers swallow real app errors; suppress only the specific expected error, with a comment. |

## In review

| Repository | ★ | PR | Status | Anti-pattern family |
|------------|----|----|--------|---------------------|
| Supabase | ★104.8k | [supabase/supabase#47053](https://github.com/supabase/supabase/pull/47053) | Open | One-shot grid-cell text read replaced with web-first text assertion. |
| Expo | ★50.3k | [expo/expo#46699](https://github.com/expo/expo/pull/46699) | Open | Router E2E assertions wait for UI state instead of racing. |
| hcengineering/platform | ★26.3k | [hcengineering/platform#10922](https://github.com/hcengineering/platform/pull/10922) | Open | `expect(locator).toBeDefined()` checks replaced with `toBeVisible()`. |
| TanStack Router | ★14.7k | [TanStack/router#7616](https://github.com/TanStack/router/pull/7616) | Open | Always-passing E2E assertions and missing awaits. |
| ngx-bootstrap | ★5.5k | [valor-software/ngx-bootstrap#6820](https://github.com/valor-software/ngx-bootstrap/pull/6820) | Open | Guarded / non-executing assertions converted into effective checks. |
| DefGuard | ★2.7k | [DefGuard/defguard#3146](https://github.com/DefGuard/defguard/pull/3146) | Open | Async `find()` callback selected the wrong row; follow-up `toBeDefined()` was always true. |

## Queued

Queue entries must be re-verified against upstream `main` before submission.

| Repository | ★ | Framework | Priority | Finding family |
|------------|----|-----------|----------|----------------|
| Rocket.Chat | ★45.7k | Playwright | P0 | Bare matcher-less `expect(locator)` lines. |
| Kibana | ★21.2k | Cypress | P0 | Committed focused test skips sibling alert-workflow coverage. |
| Astro | ★60.5k | Playwright | P0/P1 | One-shot state reads and assertion shape review. |
| React Router | ★56.5k | Playwright | P0/P1 | One-shot state reads and weak locator assertions. |
| Material UI | ★98.5k | Playwright | P0/P1 | Locator truthiness / one-shot state assertions. |
| Superset | ★73.5k | Cypress | P0/P1 | Blanket exception suppression and one-shot URL reads. |
| freeCodeCamp | ★450k+ | Playwright | P0/P1 | Weak assertions and guarded checks. |
| Kong Insomnia | ★39k+ | Playwright | P1 | Hard waits and weak post-state checks. |

## Operating rules

- Prefer merged-proof quality over volume: one clear P0 fix is better than several subjective cleanups.
- Keep PRs small enough for maintainers to review in one pass.
- Run the target repo's local test or the narrowest available verification before submission.
- Mention `e2e-skills/e2e-reviewer` only as transparent provenance, not as a sales pitch.
- Update this roadmap when a PR merges, closes, or moves from queue to review.
