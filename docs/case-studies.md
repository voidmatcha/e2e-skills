# E2E Silent-Pass Case Studies

These are real merged upstream PRs found while reviewing Playwright/Cypress suites with `e2e-skills/e2e-reviewer`. The common pattern: CI was green, but the test either asserted nothing, skipped the assertion, or checked a value that could never fail.

## Carbon Design System: locator truthiness did not prove progress state

- Repo: [`carbon-design-system/carbon`](https://github.com/carbon-design-system/carbon)
- PR: [`carbon-design-system/carbon#22564`](https://github.com/carbon-design-system/carbon/pull/22564) — merged
- Pattern: `expect(page.locator(...)).toBeTruthy()` asserted the Locator object, not the rendered step state.

```diff
- expect(page.locator('.cds--progress-step--complete')).toBeTruthy();
+ await expect(page.locator('.cds--progress-step--complete')).toBeVisible();
```

Why it matters: `page.locator()` returns a Locator handle even when no matching element is visible. The fixed assertion waits for user-visible progress state.

## Storybook: unawaited actions and discarded checks

- Repo: [`storybookjs/storybook`](https://github.com/storybookjs/storybook)
- PR: [`storybookjs/storybook#34141`](https://github.com/storybookjs/storybook/pull/34141) — merged
- Pattern: Playwright actions were not awaited, and point-in-time `isVisible()` reads were discarded.

Why it matters: Playwright promises must be awaited, and boolean reads do not become assertions unless their result is asserted.

## code-server: focused test leak and non-asserting checks

- Repo: [`coder/code-server`](https://github.com/coder/code-server)
- PR: [`coder/code-server#7845`](https://github.com/coder/code-server/pull/7845) — merged
- Pattern: `it.only` skipped part of the suite for months; several checks used matcher-less `expect()` calls or one-shot reads.

Why it matters: focused-test leaks silently remove coverage from CI, while matcher-less `expect()` calls create false confidence.

## SvelteKit: floating web-first assertions

- Repo: [`sveltejs/kit`](https://github.com/sveltejs/kit)
- PR: [`sveltejs/kit#16068`](https://github.com/sveltejs/kit/pull/16068) — merged
- Pattern: web-first assertions were created but not awaited.

```diff
- expect(page).toHaveURL(expectedUrl);
+ await expect(page).toHaveURL(expectedUrl);
```

Why it matters: a missing `await` can make a Playwright assertion float without participating in the test result.

## Strapi: discarded boolean reads

- Repo: [`strapi/strapi`](https://github.com/strapi/strapi)
- PR: [`strapi/strapi#26630`](https://github.com/strapi/strapi/pull/26630) — merged
- Pattern: `isVisible()` / `isHidden()` / `isEnabled()` results were read and discarded.

Why it matters: reading a boolean is not a test assertion. The fixed tests assert user-visible state with awaited matchers.

## Ghost: async disabled-state checks always passed

- Repo: [`TryGhost/Ghost`](https://github.com/TryGhost/Ghost)
- PR: [`TryGhost/Ghost#28712`](https://github.com/TryGhost/Ghost/pull/28712) — merged
- Pattern: `expect(likeButton.isDisabled()).toBeTruthy()` checked a promise-like value instead of the button state.

Why it matters: async checks need `await` or a web-first assertion; otherwise the test can pass without proving the disabled state.

## Cal.com: weak assertions and hard waits

- Repo: [`calcom/cal.diy`](https://github.com/calcom/cal.diy)
- PR: [`calcom/cal.diy#28486`](https://github.com/calcom/cal.diy/pull/28486) — merged
- Pattern: weak assertions and fixed sleeps in E2E tests.

Why it matters: replacing hard waits with web-first assertions makes tests fail on real regressions instead of timing artifacts.

## More merged examples

- [`usebruno/bruno#8317`](https://github.com/usebruno/bruno/pull/8317) — awaited a WebSocket visibility assertion so it actually ran.
- [`QwikDev/qwik#8777`](https://github.com/QwikDev/qwik/pull/8777) — replaced discarded assertion promises, locator `toBeDefined()`, and bare locator checks.
- [`element-hq/element-web#32801`](https://github.com/element-hq/element-web/pull/32801) — fixed always-passing assertions, unawaited checks, `toBeAttached()` misuse, and dead code.
- [`mui/mui-x#22982`](https://github.com/mui/mui-x/pull/22982) — replaced an always-true Locator null check with a user-visible edit assertion.
- [`rancher-sandbox/rancher-desktop#10557`](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) — replaced `getByText(...).not.toBeNull()` (always true) with web-first visibility assertions for each WSL integration name.
