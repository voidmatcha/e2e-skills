---
name: playwright-test-rules
description: 'Benchmark-only reduced variant of playwright-test-generator for generator-skill-effect-v3: the written locator and assertion rules only, copied verbatim from the full-fixed skill text, with no workflow steps, no run-and-fix loop and no scanner. Not a shipped skill.'
license: Apache-2.0
metadata:
  author: voidmatcha
  frameworks: playwright
  testing-types: e2e
  languages: typescript,javascript
  version: "2.0.0-rules-only-bench"
---

# Playwright test-writing rules (rules-only benchmark variant)

The sections below are copied verbatim from `code-rules.md` and `best-practices.md` of the `playwright-test-generator` skill (see `TRACE.md`). Apply them while writing the tests. References to "Step 1", "Step 3", "Step 4", the "Locator Mapping Table", "V-rules" and the "approved plan" point at workflow steps this variant does not include; read them as "what you observed in the application and its config".

## Hard rules (always)

Non-negotiable for every generated spec, regardless of project shape:

- **`await` everything** — every `expect()` on a Locator and every Playwright action (`.click()`, `.fill()`, `.press()`, `.check()`, `.selectOption()`, `.hover()`). Missing `await` breaks test sequencing: the promise may still start, but its result is no longer ordered with the next step and a rejection may surface late as an unhandled rejection or after the test has ended.
- **Web-first assertions only** — `toBeVisible()`, `toHaveText()`, `toHaveURL()`, etc. Never `expect(await el.isVisible()).toBe(true)` (resolves once, no retry).
- **Control writes at their actual seam** — signup, login, payment, and other mutations must use the project's deterministic browser- or server-side test seam. A generated test never mutates real shared backend data.
- **Freeze network identity before exploration** — use one approved DNS address snapshot, pin every preflight peer, reject drift or mixed unsafe answers, and use the bundled executable preflight helper for special-address classification. The helper binds a root-owned absolute curl executable instead of ambient `PATH`, records its hash, and rejects credential-bearing or ambiguous queries before subprocess launch; ordinary non-secret route parameters may remain. A protected local route may prove reachability with matching peer-wide `401`/`403` or one non-followed same-origin redirect to a validated login URL; authenticate only afterward under the same guards. Live remote exploration is limited to an explicitly approved non-production target in an externally isolated controlled browser harness with enforceable egress. Shared, production, or unknown remote targets are snapshot-only. Sanitize user-provided snapshots from those targets by removing credentials, cookies, authentication/session tokens, sensitive query values, PII, customer data, secrets, and internal hostnames as appropriate; use stable placeholders and preserve only non-sensitive roles, names, labels, testids, and structure. Application-layer URL checks alone are not DNS-rebinding protection.
- **Credential values stay outside the agent context** — the user sets specifically named environment variables locally; the agent checks only presence and non-empty status and never requests, reads, prints, echoes, logs, or asks the user to paste a value.
- **Gate hydration** — on SSR/SSG apps, gate the first interaction on a hydration signal, never `waitForTimeout()` after `goto`.
- **One hard `expect()` per test** — a test built only from `expect.soft()` never fails early.

---

## Selector Priority (best → worst)

1. `getByRole('button', { name: 'Submit' })` — role + accessible name
2. `getByLabel('Email')` — form label — **only when the label/aria-label actually exists**; verify in the Step 3 snapshot before using
3. `getByPlaceholder('Email')` — only for an actual `placeholder` attribute
4. `getByTitle('Email')` — only for an actual `title` attribute; do not treat `title` as a placeholder
5. `getByTestId('submit-btn')` / `[data-testid="submit-btn"]` — explicit test hook
6. `getByText('Save')` / `.filter({ hasText: 'text' })` — visible text
7. attribute selector `[formControlName="email"]` — stable attribute
8. CSS `#id` / `.class` — last resort, `// JUSTIFIED:` required (see **Text-bearing elements without a role, label, or test id** below); stable structural attributes only, never styling classes
9. `.nth()` / `.first()` / `.last()` — **forbidden** without `// JUSTIFIED:` on the line above

**Project-configured test ids rank with role+name.** When the loaded Playwright config (Step 1) sets `use: { testIdAttribute: '...' }`, or `data-testid` (or the project's equivalent) is pervasive in the components under test, treat `getByTestId` as a **tier-1 locator alongside role+name** — not a fixed lower-tier fallback. A deliberate, stable test hook beats reaching past it for brittle text/placeholder locators. Keep `getByText`/`getByPlaceholder` as the fallback when no role or test id fits.

**Text-bearing elements without a role, label, or test id.** A counter, status line, badge, or list cell often has visible text but no role, label, or test id. Locate it by that text, `getByText('0 entries')` or an anchored pattern such as `getByText(/^\d+ entries?$/)`, or scope from a labeled ancestor, `getByRole('list', { name: 'Records' }).getByRole('listitem').filter({ hasText: 'Record 1' })`. Do not reach for `locator('#gb-count')` or `locator('.title')` because the element lacks a role: a behavior-preserving markup refactor renames ids and classes while roles, labels, and visible text stay, so an id or class selector fails exactly the refactor the test should survive. When the text may repeat, scope it with a role-based ancestor instead of `.nth()`. `#id` and `.class` selectors need `// JUSTIFIED: <reason>` on the line above, except when the project's Playwright config sets `testIdAttribute` to that attribute or its conventions doc documents the id or class scheme as the locator convention; record either exception in the Locator Mapping Table.

Never use XPath. Never use CSS class chains that couple to styling.

---

## Locators

| Rule | Detail |
|------|--------|
| User-facing first | Prefer `getByRole`, `getByLabel`, `getByText` over CSS/XPath — they survive redesigns and carry auto-wait semantics. |
| Test ids when configured | If the loaded Playwright config (Step 1) sets `use: { testIdAttribute: 'data-test' }` (or test ids are pervasive), `getByTestId` is a tier-1 locator alongside role+name — not a last resort. |
| Chain + filter | `getByRole('listitem').filter({ hasText: 'X' }).getByRole('button')` to scope without positional `.nth()`. |
| Text-only elements | A counter or status line with no role or label is located by its visible text (`getByText(/^\d+ entries?$/)`) or from a labeled ancestor, not by `#id` or `.class`: a markup refactor renames those and keeps the text. |
| No XPath / styling CSS | XPath locators still participate in Playwright's locator auto-waiting, but they are brittle because they couple tests to DOM structure; styling-class chains similarly break on redesign. |

---

## Assertions (web-first)

| Rule | Detail |
|------|--------|
| Auto-retrying matchers only | `toBeVisible()`, `toHaveText()`, `toHaveURL()`, `toHaveCount()` poll until the condition holds or the timeout expires. |
| Never one-shot | `expect(await el.isVisible()).toBe(true)` resolves once with no retry — a race waiting to flake. |
| `expect.poll` for non-DOM state | Poll an API/computed value that has no web-first matcher: `await expect.poll(() => fetchStatus()).toBe('ready')`. |
| `expect.toPass` for compound steps | Retry a small action+assert block only when every repeated action is proven idempotent (for example, opening an already-openable disclosure). For submit, delete, payment, message-send, and other non-idempotent writes, establish an explicit hydration/readiness gate and perform the action once. |
| `toMatchAriaSnapshot` for structure | Assert a subtree's roles + accessible names as a unit: `await expect(page.getByRole('navigation')).toMatchAriaSnapshot(...)`. Catches structural regressions one `toBeVisible` at a time would miss. |

---

## Forbidden patterns (from code-rules.md § Spec Rules)

**Forbidden:**

> Maintenance: the rules below (and the mirrored entries elsewhere in this file) duplicate e2e-reviewer patterns for generation-time convenience. Pattern semantics — IDs, severities, false-positive exclusions — are owned by `skills/e2e-reviewer/references/pattern-reference.md`; on conflict, that file wins.

| Forbidden | Use instead |
|-----------|-------------|
| `waitForTimeout(N)` | `await expect(el).toBeVisible({ timeout: N })` |
| `expect(await el.isVisible()).toBe(true)` | `await expect(el).toBeVisible()` |
| `const n = await el.count()` as the sole outcome assertion or readiness gate | `await expect(el).toHaveCount(N)` when cardinality is the contract, or another web-first assertion for the promised user-visible postcondition. Raw `count()` remains valid for evidenced data collection or bounded iteration after readiness when a separate web-first assertion proves the outcome. |
| `toBeAttached()` when the approved contract promises visibility or removal | Match the promise: use `toBeVisible()` for visibility and `not.toBeAttached()` for removal. Positive `toBeAttached()` is valid when DOM attachment itself is the approved contract, including a CSS-hidden element that must persist or an app-provided hydration marker. |
| `expect(locator).toBeTruthy()` | Replace it with a web-first matcher that expresses the approved contract: `toBeVisible()` only for promised visibility, `toBeAttached()` for promised DOM presence (including a CSS-hidden element), or another matching outcome assertion. Locator is always a truthy JS object, so the original assertion does not reveal intent. Do not infer visibility from the invalid truthiness assertion or change the approved expected value. |
| `page.click(selector)` / `page.fill(selector, v)` | `page.locator(selector).click()` / `.fill(v)` — locator-first actions are easier to compose and review |
| `{ force: true }` | Fix the root cause (element not actionable); if unavoidable, add `// JUSTIFIED:` |
| `waitUntil: 'networkidle'` | `waitUntil: 'domcontentloaded'` or condition-based wait — unreliable on SPAs |
| `expect(page.url()).toContain(x)` | `await expect.poll(() => page.url()).toContain(x)` — preserves substring semantics and retries |
| Framework component selectors in spec (`app-button`, `my-component`) | POM only |
| XPath selectors | `getByRole` / `getByLabel` / `getByTestId` |

**Await rule:** Every `expect()` on a Locator and every Playwright action (`.click()`, `.fill()`, `.type()`, `.press()`, `.check()`, `.selectOption()`, `.hover()`) **must** be `await`ed. Missing `await` breaks test sequencing; the operation can still run, but its rejection may be unhandled, reported after the test ends, or race the following step.
