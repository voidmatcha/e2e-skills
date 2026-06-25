# Playwright Best Practices

Condensed from [playwright.dev/docs/best-practices](https://playwright.dev/docs/best-practices) and the current Playwright API. This is the *why* reference; the enforceable generation rules (selector priority, forbidden patterns, await rule) live in `code-rules.md`.

## Locators

| Rule | Detail |
|------|--------|
| User-facing first | Prefer `getByRole`, `getByLabel`, `getByText` over CSS/XPath — they survive redesigns and carry auto-wait semantics. |
| Test ids when configured | If `playwright.config.*` sets `use: { testIdAttribute: 'data-test' }` (or test ids are pervasive), `getByTestId` is a tier-1 locator alongside role+name — not a last resort. |
| Chain + filter | `getByRole('listitem').filter({ hasText: 'X' }).getByRole('button')` to scope without positional `.nth()`. |
| No XPath / styling CSS | XPath is brittle and has no auto-wait; CSS class chains tied to styling break on redesign. |

## Assertions (web-first)

| Rule | Detail |
|------|--------|
| Auto-retrying matchers only | `toBeVisible()`, `toHaveText()`, `toHaveURL()`, `toHaveCount()` poll until the condition holds or the timeout expires. |
| Never one-shot | `expect(await el.isVisible()).toBe(true)` resolves once with no retry — a race waiting to flake. |
| `expect.poll` for non-DOM state | Poll an API/computed value that has no web-first matcher: `await expect.poll(() => fetchStatus()).toBe('ready')`. |
| `expect.toPass` for compound steps | Retry a small action+assert block (e.g. a click that must take effect) until it passes, instead of `waitForTimeout`. |
| `toMatchAriaSnapshot` for structure | Assert a subtree's roles + accessible names as a unit: `await expect(page.getByRole('navigation')).toMatchAriaSnapshot(...)`. Catches structural regressions one `toBeVisible` at a time would miss. |

## Isolation & Auth

| Rule | Detail |
|------|--------|
| Per-test isolation | Each test gets its own storage, session, cookies — no shared mutable state between tests. |
| Authenticate once via `storageState` | Use a `setup` project (a dependency project that logs in and writes `storageState` to disk), then point dependent projects at that state via `use: { storageState }`. Don't drive UI login in every spec. |
| Recreate sessions from code | Never hard-depend on a manually captured `auth/*.json` a fresh clone or CI won't have, and that silently expires. The setup project must regenerate it. |
| Mock external APIs | Never call real third-party services; stub all writes/credential paths with `page.route()`. |

## Projects

| Rule | Detail |
|------|--------|
| Cross-browser via `projects` | Define `chromium`/`firefox`/`webkit` (and device emulation) as projects rather than looping inside tests. |
| Dependencies | A `setup` project listed in another project's `dependencies` runs first — the canonical auth/seed pattern. |

## Anti-patterns

| Avoid | Why |
|-------|-----|
| `waitForTimeout(N)` | Fixed sleep — races on slow CI, wastes time on fast. Use a web-first assertion or `toPass`. |
| `waitUntil: 'networkidle'` | Unreliable on SPAs with long-polling / WebSockets. Use `domcontentloaded` or a condition-based wait. |
| `page.click(selector)` / `page.fill(selector, v)` | Prefer locator-first actions (`page.locator(selector).click()`) — composable and reviewable. |
| `expect()` or action without `await` | Silently skips the assertion or action. |

## CI

| Rule | Detail |
|------|--------|
| Type-check first | `tsc --noEmit` before every commit. |
| `forbidOnly` | Set `forbidOnly: !!process.env.CI` so a stray `test.only` fails CI instead of silently skipping the suite. |
| Cheap tracing | `--trace on-first-retry` for CI debugging — not `--trace on` (too expensive). Pair with `--reporter=html` so failures leave inspectable artifacts. |
