# Open Source Case Studies

These merged PRs show the patterns in this repository applied to real projects.

## Cal.com: false-passing Playwright assertions

- PR: [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486)
- Fixed: locator truthiness, no-op disabled checks, one-shot assertions, and hard-coded waits.
- Lesson: Green tests are not trustworthy if assertions do not wait for user-visible state.

## Storybook: unawaited Playwright actions

- PR: [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141)
- Fixed: missing `await` on `fill()` / `blur()` and discarded `isVisible()` checks.
- Lesson: Playwright promises must be awaited, and `isVisible()` is a point-in-time query rather than a web-first assertion.

## Element Web: E2E quality cleanup

- PR: [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801)
- Fixed: always-passing assertions, unawaited checks, `toBeAttached()` misuse, and dead code.
- Lesson: Static review can find tests that pass while proving nothing in large E2E suites.

## code-server: skipped tests and non-asserting checks

- PR: [coder/code-server#7845](https://github.com/coder/code-server/pull/7845)
- Fixed: a committed `it.only` that silently skipped 8 Heart unit tests for 7 months (one had broken while disabled and was repaired with a microtask drain), 4× matcher-less `expect()`, a dangling `getByText()` locator, and 16× one-shot `page.isVisible()` reads converted to web-first assertions.
- Lesson: A focused-test leak removes whole suites from CI without failing; the gap is invisible until something inside the skipped block regresses.
