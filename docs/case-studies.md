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
