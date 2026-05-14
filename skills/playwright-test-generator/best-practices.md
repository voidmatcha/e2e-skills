# Playwright Best Practices

From [playwright.dev/docs/best-practices](https://playwright.dev/docs/best-practices).

| Category | Rule |
|----------|------|
| Locators | Prefer `getByRole`, `getByLabel`, `getByText` over CSS/XPath |
| Locators | Chain + filter: `getByRole('listitem').filter({ hasText: 'X' }).getByRole('button')` |
| Assertions | Web-first only — `toBeVisible()`, `toHaveText()` auto-retry until condition met |
| Assertions | Never `expect(await el.isVisible()).toBe(true)` — resolves once, no retry |
| Isolation | Each test: own storage, session, cookies — no shared state |
| Isolation | Mock external APIs — never call real third-party services in tests |
| Anti-patterns | No XPath — brittle, no auto-wait semantics |
| Anti-patterns | No CSS class chains tied to styling — breaks on redesign |
| Anti-patterns | No `waitUntil: 'networkidle'` — unreliable on SPAs with long-polling/WebSockets |
| Anti-patterns | Avoid direct `page.click(selector)` / `page.fill(selector, value)` — prefer locator-first actions such as `page.locator(selector).click()` |
| Anti-patterns | No `expect()` or action without `await` — silently skips verification |
| CI | `tsc --noEmit` before every commit |
| CI | `--trace on-first-retry` for CI debugging — not `--trace on` (too expensive) |
