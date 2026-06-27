# Upstream Contributions: Track Record and Roadmap

e2e-skills is validated by contributing real fixes upstream. This page is both the
**track record** (the merged PRs below are the proof that the skill flags bugs
maintainers agree are worth fixing) and the **contribution roadmap** (in review,
queued, and backlog). It tracks the upstream pull requests that the `e2e-reviewer`
skill surfaced across open-source Playwright and Cypress test suites.

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

| Repository | ★ | PR | What it fixed | Lesson |
|------------|----|----|---------------|--------|
| Cal.com | ★45.8k | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | Locator truthiness, no-op disabled checks, one-shot assertions, hard-coded waits | Green tests are not trustworthy if assertions do not wait for user-visible state. |
| Storybook | ★90.4k | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Missing `await` on `fill()`/`blur()`, discarded `isVisible()` checks | Playwright promises must be awaited, and `isVisible()` is a point-in-time query, not a web-first assertion. |
| Element Web | ★13.2k | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Always-passing assertions, unawaited checks, `toBeAttached()` misuse, dead code | Static review can find tests that pass while proving nothing in large E2E suites. |
| code-server | ★78.1k | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | An `it.only` that silently skipped 8 unit tests for 7 months (one had broken), 4x matcher-less `expect()`, a dangling locator, 16x one-shot `isVisible()` reads | A focused-test leak removes whole suites from CI without ever failing; the gap is invisible until something inside the skipped block regresses. |
| Ghost | ★54.1k | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | `expect(likeButton.isDisabled()).toBeTruthy()` x3 plus a one-shot re-enable read in the comments-ui like-button suite | An un-awaited `isDisabled()` returns a Promise that is always truthy, so the debounce-guard tests passed no matter what the button did. |
| SvelteKit | ★20.6k | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | Unawaited `expect(page)` web-first assertions in the basics client E2E tests | A floating web-first assertion never runs; the missing `await` is the whole bug, and adding it is what makes the check assert. |
| Strapi | ★72.5k | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | Discarded `isVisible()`/`isHidden()`/`isEnabled()` reads that were the sole assertion of each visibility test, plus one-shot reads and unawaited clicks | A discarded boolean read asserts nothing, so the test's whole visibility contract passed unconditionally. |
| bruno | ★45.2k | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | A missing `await` on the sole web-first visibility assertion in the WebSocket spec — the floating Promise never ran | An un-awaited web-first `expect()` returns a Promise that is never observed, so the assertion never executes and the test passes no matter what the UI shows. |

## In review

| Repository | ★ | PR | Status | Anti-pattern family |
|------------|----|----|--------|---------------------|
| Qwik | ★22k | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | In review | Non-asserting e2e checks — discarded assertion promises, `toBeDefined()` on locators, bare locators |
| module-federation/core | ★2.6k | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Approved | Redundant blanket `uncaught:exception` suppression removed from the memory-router cypress spec |
| hcengineering/platform | ★26.3k | [hcengineering/platform#10922](https://github.com/hcengineering/platform/pull/10922) | In review | `expect(locator).toBeDefined()` always-true checks in the recruiting navigator test (sole verification) replaced with web-first `toBeVisible()` |
| TanStack Router | ★14.7k | [TanStack/router#7616](https://github.com/TanStack/router/pull/7616) | In review | `expect(locator).toBeTruthy()` (always true), masked expected-value typo |
| voxel51/fiftyone | ★10.8k | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | In review | `expect(this.svp.nameError()).toBeDefined()` (no `await`/matcher) replaced with web-first `toBeVisible()` in the saved-views duplicate-name path |
| expo | ★50.3k | [expo/expo#46699](https://github.com/expo/expo/pull/46699) | Review requested | Unawaited web-first assertions in router E2E |
| supabase | ★104.8k | [supabase/supabase#47053](https://github.com/supabase/supabase/pull/47053) | Review requested | Grid-cell `textContent()` to web-first `toHaveText` |

## Queued

Highest-conviction candidates: each was necessity-audited (adversarial skeptical-maintainer
re-read of the actual code) and graded **NECESSARY** or **WORTHWHILE**. Re-screened 2026-06-20
on three axes — policy blockers (frappe-style suspension / CLA / anti-AI), the finding still
reproducing at the live default-branch HEAD, and the installed scanner actually detecting it.
Re-sorted 2026-06-24 by **maintainer-acceptance likelihood**: rows are ordered best-first, and
candidates whose acceptance was doubtful (solo maintainer with no external-PR precedent, or a
finding a maintainer could reasonably defend as intentional) were dropped rather than padded.
SUBMIT = clean-enough policy + live finding a maintainer should accept; CAUTION = a real finding
behind a gate (CLA / issue-first) that must be cleared first. A fresh convention check runs
before any submission. Candidates are gated to **>=1000 stars** to match the large-repo bar of
the track record above; clean but smaller finds (for example trivy-vulnerability-explorer, ★176)
are parked rather than queued.

| Repository | ★ | Framework | Status | Why a maintainer must accept |
|------------|----|-----------|--------|------------------------------|
| mui/mui-x | ★5.8k | Playwright | SUBMIT | `expect(getByText(...)).not.to.equal(null)` is always true (a Locator is never null) and is the sole check of the dateTime-cell edit; a silently broken edit ships green. Finding lives in `test/e2e/` — outside the CLA-required folders. |
| carbon-design-system/carbon | ★9.2k | Playwright | SUBMIT | Two ProgressIndicator tests whose only assertion is `expect(page.locator(...)).toBeTruthy()` — always true on a Locator, so the CSS-class check never runs. Same file has real assertions; frame as the only broken lines. (DCO sign-off.) |
| rancher-sandbox/rancher-desktop | ★7.2k | Playwright | SUBMIT | `expect(getByText('alpha'/'beta'/'gamma')).not.toBeNull()` is always true (a Locator is never null) and is the sole content check of the "should list integrations" test; a dropped or renamed integration ships green. (DCO sign-off.) |
| ever-co/ever-gauzy | ★3.7k | Cypress | SUBMIT | The `Should be able to edit payment` test installs a blanket `cy.on('uncaught:exception', () => false)` (#3b) that swallows every app error, so a runtime exception in the edit flow is suppressed and the test passes regardless of whether the feature works. (★3,742; `PaymentsTest.ts:53`; confirm the test still passes after scoping the handler before submitting.) |
| RocketChat/Rocket.Chat | ★45.7k | Playwright | CAUTION | Five bare matcher-less `expect(locator)` lines disable every assertion in three CI-gated admin import tests; an import regression passes green. (CLA bot blocks merge until signed.) |
| lightdash | ★5.9k | Cypress | CAUTION | A committed `it.only` silently skips nine authorization tests in CI; removing it restores coverage. (Hard issue-first + #community-contributors Slack claim before any PR.) |
| xyflow | ★37.3k | Cypress | CAUTION | `addEdge` never throws, so the lone assertion in graph-utils.cy.ts never executes and the test cannot fail. Semantic-only (no scanner/lint rule can detect it). (Issue-first / Discord contact before PR.) |
| elastic/kibana | ★21.2k | Cypress | CAUTION | A committed `context.only` silently skips five sibling alert-workflow tests (open / acknowledge / close) on every security CI run; removing it restores coverage. (Elastic CLA + high review bar; file moved to `x-pack/solutions/security/.../changing_alert_status.cy.ts` — update path before PR.) |
| DefGuard/defguard | ★2.7k | Playwright | SUBMIT | The `createNetworkDevice` e2e controller picks the target row with `deviceRows.find(async (val) => ...)` — an async callback always returns a truthy Promise, so `find` returns the first row regardless of name, and the follow-up `expect(row).toBeDefined()` is always true (a Locator is never undefined). The name match is silently ignored, so the helper can drive every later assertion against the wrong device. (★2,744; `e2e/utils/controllers/vpn/createNetworkDevice.ts:25`; verify CLA/DCO at submission; LLM Phase-2 verified.) |
| valor-software/ngx-bootstrap | ★5.5k | Playwright + Jest | SUBMIT | Two silently-skipped-assertion findings. In the timepicker unit spec roughly twenty mousewheel / arrow-key tests bury their `expect().toEqual()` calls inside `jest.spyOn(...).mockImplementation(() => {...})` callbacks that are never invoked, so the assertions never execute and the tests pass unconditionally; and `e2e/issues/issue-823.spec.ts` wraps every assertion in `if (count > 0)` guards, so a selector that matches nothing passes having asserted nothing. (★5,519; `src/timepicker/testing/timepicker.component.spec.ts`, `e2e/issues/issue-823.spec.ts`; active org, verify conventions at submission; LLM Phase-2 verified.) |
| perses/perses | ★2.2k | Playwright | CAUTION | `DashboardPage.isDarkMode()` / `isLightMode()` assert the active theme with `expect(this.themeToggle.locator('#dark')).toBeDefined()` (no `await`, no matcher) — a Locator is always defined, so the theme guard used by `forEachTheme` passes whether or not the theme actually switched. (★2,237; `ui/e2e/src/pages/DashboardPage.ts:159`; CNCF project, verify CLA/DCO and the review bar before PR; LLM Phase-2 verified.) |

## Backlog

Necessity-audited as **WORTHWHILE**: real, idiom-aligned improvements a maintainer would
likely accept, but the suite passes correctly today (the finding is backstopped by an
adjacent assertion, or flakes red rather than silently green). Ordered most-convincing first.
The `Patterns` column lists the anti-pattern IDs the scan surfaced (see
[`docs/e2e-test-smells.md`](e2e-test-smells.md) for the ID legend).

| Repository | ★ | Framework | Patterns |
|------------|----|-----------|----------|
| microsoft/fluentui | ★20.1k | Playwright | #4h |
| penpot/penpot | ★53.6k | Playwright | #8b, #4c, #4h |
| vercel/ai-chatbot | ★20.5k | Playwright | #2, #3, #10a |
| surveyjs/survey-library | ★4.8k | Playwright | #4c-4e |
| web-infra-dev/rspack | ★12.8k | Playwright | #4c-4e |
| saleor/saleor-dashboard | ★1k | Playwright | #4c, #8b |
| jupyterlab/jupyterlab | ★15.2k | Playwright | #4c-4e, #8b |
| react-router | ★56.5k | Playwright | #4c-4e, #15 |
| actual | ★27.2k | Playwright | #4c-4e, #4h |
| mui/material-ui | ★98.5k | Playwright | #4c |
| freeCodeCamp/freeCodeCamp | ★450.5k | Playwright | #4f, #8b |
| WordPress/gutenberg | ★11.7k | Playwright | #4h |
| Kong/insomnia | ★39.7k | Playwright | #8b |
| handsontable/handsontable | ★21.9k | Playwright | #4c-4e, #9 |
| vendure | ★8.2k | Playwright | #3, #5a |
| nhost/nhost | ★9.2k | Playwright | #15 |
| astro | ★60.5k | Playwright | #4c-4e |
| openobserve/openobserve | ★19.4k | Playwright | #4c |
| builderio | ★8.7k | Playwright | #4c-4e |
| rallly | ★5.1k | Playwright | #3, #15 |
| react-navigation | ★24.5k | Playwright | #4c |
| superset | ★73.5k | Cypress | #3b, #4h |
| semi-design | ★10k | Cypress | #3b, #5b, #9b |
| kestra | ★27.1k | Playwright | #4f, #15 |
| elementor | ★7k | Playwright | #4, #8b |
| AgentOps-AI/agentops | ★5.6k | Cypress | #5a |
| naomiaro/waveform-playlist | ★1.7k | Playwright | #2 |
| katspaugh/wavesurfer.js | ★10.3k | Cypress | #2 |
