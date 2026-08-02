# Playwright Best Practices

Condensed from [playwright.dev/docs/best-practices](https://playwright.dev/docs/best-practices) and the current Playwright API. This is the *why* reference; the enforceable generation rules (selector priority, forbidden patterns, await rule) live in `code-rules.md`.

## Locators

| Rule | Detail |
|------|--------|
| User-facing first | Prefer `getByRole`, `getByLabel`, `getByText` over CSS/XPath — they survive redesigns and carry auto-wait semantics. |
| Test ids when configured | If `playwright.config.*` sets `use: { testIdAttribute: 'data-test' }` (or test ids are pervasive), `getByTestId` is a tier-1 locator alongside role+name — not a last resort. |
| Chain + filter | `getByRole('listitem').filter({ hasText: 'X' }).getByRole('button')` to scope without positional `.nth()`. |
| No XPath / styling CSS | XPath locators still participate in Playwright's locator auto-waiting, but they are brittle because they couple tests to DOM structure; styling-class chains similarly break on redesign. |

## Assertions (web-first)

| Rule | Detail |
|------|--------|
| Auto-retrying matchers only | `toBeVisible()`, `toHaveText()`, `toHaveURL()`, `toHaveCount()` poll until the condition holds or the timeout expires. |
| Never one-shot | `expect(await el.isVisible()).toBe(true)` resolves once with no retry — a race waiting to flake. |
| `expect.poll` for non-DOM state | Poll an API/computed value that has no web-first matcher: `await expect.poll(() => fetchStatus()).toBe('ready')`. |
| `expect.toPass` for compound steps | Retry a small action+assert block only when every repeated action is proven idempotent (for example, opening an already-openable disclosure). For submit, delete, payment, message-send, and other non-idempotent writes, establish an explicit hydration/readiness gate and perform the action once. |
| `toMatchAriaSnapshot` for structure | Assert a subtree's roles + accessible names as a unit: `await expect(page.getByRole('navigation')).toMatchAriaSnapshot(...)`. Catches structural regressions one `toBeVisible` at a time would miss. |

## Isolation & Auth

| Rule | Detail |
|------|--------|
| Per-test isolation | Each test gets its own storage, session, cookies — no shared mutable state between tests. |
| Authenticate once via `storageState` | Use a `setup` project (a dependency project that logs in and writes `storageState` to disk), then point dependent projects at that state via `use: { storageState }`. Don't drive UI login in every spec. |
| Recreate sessions from code | Never hard-depend on a manually captured `auth/*.json` a fresh clone or CI won't have, and that silently expires. The setup project must regenerate it. |
| Credential values remain local | Check credential environment variables for presence only. The user sets named variables locally; never request, read, print, echo, log, or paste their values into the agent conversation. |
| Mock external APIs | Never call real third-party services. Control writes at their actual browser or server seam: `page.route()` for browser requests, or the project's server-side test double/E2E boundary for SSR, RSC, route-handler, or BFF traffic. |

## Exploration Network Boundary

| Rule | Detail |
|------|--------|
| One DNS identity | Pin preflight probes to the one approved DNS snapshot. Probe each approved peer with curl `--resolve`; reject empty, unsafe, mixed, or drifting address sets. |
| Executable address validation | Invoke the bundled `scripts/run-preflight-target.sh` launcher directly from the physical target-project working directory; it binds the sibling `preflight_target.py` under an isolated Python 3.10+ runtime and rejects a fixed interpreter located under that project root. Do not classify alternate literals, IPv4-mapped IPv6, NAT64, scoped IPv6, or other special-use ranges by model judgment. |
| Trusted probe executable | Never resolve curl from ambient `PATH`. The helper accepts only a root-owned, non-writable absolute curl under `/usr/bin` or `/bin`, records its path and SHA-256, and gives the child a fixed minimal environment. |
| Query secrecy | Ordinary non-secret route parameters may remain. Reject duplicate/ambiguous parameters, credential-bearing names, and token-shaped values before placing a URL in curl argv or a process listing. Apply the same rule before normalizing a login redirect. |
| Protected-route reachability | Treat matching peer-wide `401`/`403`, or a non-followed same-origin `3xx` to one validated login URL, as reachability only. Authenticate later under the same request and egress guards. |
| Remote browser containment | Live remote exploration is limited to explicitly approved non-production targets inside an externally isolated controlled browser harness with enforceable egress that pins approved peers and denies every other destination. Shared, production, and unknown remote targets are user-provided-snapshot only. Playwright URL routing is defense in depth, not DNS-rebinding containment. |
| Snapshot sanitization | Before using a user-provided snapshot from a shared, production, or unknown remote target, remove credentials, cookies, authentication/session tokens, sensitive query values, PII, customer data, secrets, and internal hostnames as appropriate. Use stable placeholders and preserve only non-sensitive roles, names, labels, testids, and structure. |

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
| `expect()` or action without `await` | Breaks sequencing: the promise can race later steps, reject after the test ends, or surface as an unhandled rejection. |

Raw `locator.count()` is not categorically wrong. Do not use one sampled count
as the sole outcome assertion or readiness gate. It is acceptable for evidenced
data collection or bounded iteration after the relevant state is ready, as long
as a separate web-first assertion proves the user-visible postcondition.

Use `toBeAttached()` when DOM attachment is itself the approved contract, such
as a CSS-hidden panel that must persist in the DOM or a hydration marker. Do not
substitute attachment for a promised visible state, or for removal when the
contract requires detachment.

## CI

| Rule | Detail |
|------|--------|
| Type-check first | `tsc --noEmit` before every commit. |
| `forbidOnly` | Set `forbidOnly: !!process.env.CI` so a stray `test.only` fails CI instead of silently skipping the suite. |
| Cheap tracing | `--trace on-first-retry` for CI debugging — not `--trace on` (too expensive). Pair with `--reporter=html` so failures leave inspectable artifacts. |
