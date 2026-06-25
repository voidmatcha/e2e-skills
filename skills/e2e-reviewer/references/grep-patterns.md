# Pattern ID Reference

**This file is a lookup table, not a dispatch procedure.** Phase 1 runs `bash <skill-base>/scripts/scan.sh` (the runtime source of truth); use this file to interpret what each pattern ID means when reading scanner output, doing Phase 2 review, or mapping debugger failure categories back to review patterns. Do NOT hand-dispatch these greps.

A hit is intentional and must be **skipped** when `// JUSTIFIED:` appears in any of these positions (exception: #7 Focused Test Leak has no `// JUSTIFIED:` exemption):
1. The line **immediately preceding** the hit.
2. The line immediately preceding the **enclosing call/block** when the hit is inside a callback body — e.g., `// JUSTIFIED:` above `page.evaluate(() => { … document.querySelector(…) … })` covers every qualifying pattern inside that callback.
3. For chained calls split across lines (`page.locator(…)\n  .filter(…)\n  .first()`), the line immediately preceding the chain's starting expression covers `.nth()` / `.first()` / `.last()` further down the chain.

When raw grep output is the only thing you have, always read 1–3 lines of surrounding context before flagging — most false positives come from JUSTIFIED comments sitting just above the visible match.

---

## Group 1 — error swallowing, focus leaks, sleeps, raw DOM

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #3 Error Swallowing | `\.catch\(\s*(async\s*)?\(\)\s*=>` | `*.{ts,js,cy.*}` | `.catch(() => {})` in POM/spec silently hides failures |
| #7 Focused Test Leak | `\.(only)\(` | `*.{spec.*,test.*,cy.*}` + `**/cypress/integration/**/*.{js,ts}` | `test.only` / `it.only` / `describe.only` — zero legitimate committed uses, always P0. Glob also covers the legacy `cypress/integration` layout (plain `.js`, no `.cy.`/`.spec.`/`.test.` suffix). |
| #9 Hard-coded Sleeps | `waitForTimeout` | `*.{ts,js,cy.*}` | Explicit sleeps cause flakiness |
| #9b Cypress Sleeps | `cy\.wait\(\d` | `*.{cy.*}` | Cypress numeric waits |
| #6 Raw DOM Queries | `document\.querySelector` | `*.{ts,js,cy.*}` | Bypasses framework auto-wait (covers `evaluate()` and `waitForFunction()`). Search POM files too. |

## Group 2 — vacuous and one-shot assertions

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #4a Always-true math | `toBeGreaterThanOrEqual\(0\)` | `*.{ts,js,cy.*}` | Mathematically always true |
| #4b Vacuous attached | `toBeAttached\(\)` | `*.{ts,js,cy.*}` | Flag every hit; confirm in Phase 2 whether the element is unconditionally rendered (→ P0 vacuous) or CSS-hidden (`// JUSTIFIED:` → skip) |
| #4c One-shot isVisible | `expect\(await.*\.isVisible\([^)]*\)\)` (state/text/attribute reads accept arguments, e.g. `getAttribute('src')`) | `*.{spec.*,test.*}` | One-shot boolean, no auto-retry |
| #4d One-shot state | `expect\(await.*\.(isDisabled\|isEnabled\|isChecked\|isHidden)\(\)\)` | `*.{spec.*,test.*}` | Same one-shot boolean problem |
| #4e One-shot content | `expect\(await.*\.(textContent\|innerText\|getAttribute\|inputValue\|allTextContents)\([^)]*\)\)` | `*.{spec.*,test.*}` | Resolves immediately; use `toHaveText()`, `toHaveAttribute()`, `toHaveValue()`. (One-shot `.count()` is left to the Tier-2 ast-grep `sg-4ce-count` rule — a bare regex `count` over-flags ORM/array `.count()`.) |
| #4h One-shot URL | `expect\(page\.url\(\)\)` | `*.{spec.*,test.*}` | `page.url()` reads URL at one instant with no retry; use `await expect(page).toHaveURL(...)` |

## Group 3 — truthiness traps, bypasses, ordering

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #4f Locator always-true | `\.toBeTruthy\(\)` / `\.toBeDefined\(\)` / `\.not\.toBeNull\(\)` / `\.not\.to\.equal\(null\)` | `*.{ts,js,cy.*}` | Flag hits where the subject is a Locator: a Locator is always a truthy, non-null, defined JS object regardless of element existence, so `toBeTruthy`/`toBeDefined`/`not.toBeNull`/`not.to.equal(null)` on it never fail. Non-Locator subjects (e.g., boolean variables, a `textContent()` string that can legitimately be null) are fine — confirm in Phase 2. |
| #4g Timeout zero | `timeout:\s*0` | `*.{ts,js,cy.*}` | Disables auto-retry entirely; flag unless `// JUSTIFIED:` on line above |
| #5a Conditional bypass | `if.*(isVisible\(\|is\(.*:visible.*\))` | `*.{spec.*,test.*,cy.*}` | `expect()` gated behind runtime `if` — silently skips assertions. Requires the `.isVisible(` call form, so a bare boolean variable named `isVisible` is not matched. |
| #5b Force true | `force:\s*true` | `*.{ts,js,cy.*}` | Bypasses actionability checks (visibility, enabled state) |
| #10b Serial ordering | `\.describe\.serial\(` | `*.{spec.*,test.*}` | `[Playwright only]` — order-dependent tests break parallel sharding |

## Group 4 — no-op statements, positional selectors, credentials

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #8a Dangling locator | `^\s*(await\s+)?page\.(locator\|getBy*)\(...\)\s*;?\s*(//.*)?$` + previous-line continuation filter (a hit is dropped when the preceding non-blank line ends with `(` or `,`) | `*.{spec.*,test.*}` | `[Playwright only]` — locator created as standalone statement, no `expect()`, no action, no assignment. A complete no-op. A trailing line comment is tolerated (lock-step with #8b). |
| #8b Boolean discarded | `^\s*await .*\.(isVisible\|isEnabled\|isChecked\|isDisabled\|isEditable\|isHidden)\([^)]*\)\s*;?\s*(//.*)?$` | `*.{spec.*,test.*,cy.*}` | Boolean result computed and thrown away; selector-arg and no-semicolon forms included, end anchor excludes `.catch()`/chained reads — asserts nothing |
| #10a Positional selectors | `\.nth\(\|\.first\(\)\|\.last\(\)` | `*.{spec.*,test.*,cy.*}` | Breaks when DOM order changes; needs `// JUSTIFIED:` |
| #14 Hardcoded credentials | `(login\|fill\|type).*(['"].*password\|['"].*secret\|['"]admin['"])` | `*.{spec.*,test.*,cy.*}` | String literals as credentials; use env vars or fixtures |

## Group 5 — missing awaits, direct page APIs, suppression

#3b appears twice because spec files and Cypress support files use different globs.

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #15 Missing await on expect | `^\s*expect\(` excluding `expect(await ...)`, **plus** the awaited-locator form `expect(await <locator>).<web-first matcher>(` (value-resolving one-shot reads like `expect(await x.isVisible())` still belong to #4c-4e) | `*.{spec.*,test.*}` | `[Playwright]` — `expect(locator).toBeVisible()` without `await`, or `expect(await locator).toBeVisible()` (await on the locator is a no-op), silently resolves to a Promise that is never checked. Always P0. |
| #16 Missing await on action | `^\s*page\.(locator\|getBy\w+)\(.*\)\.(click\|fill\|type\|press\|check\|uncheck\|selectOption\|setInputFiles\|hover\|focus\|blur)\(` | `*.{spec.*,test.*}` | `[Playwright]` — Action without `await` creates an unresolved Promise. Always P0. Confirm in Phase 2 that the hit line lacks a leading `await`. |
| #17 Direct page action API | `page\.(click\|fill\|type\|check\|uncheck\|selectOption)\(["'\`]` | `*.{spec.*,test.*}` | `[Playwright]` — prefer locator-based `page.locator(selector).click()` / `.fill()` for composition and clearer failures. P1. |
| #9c Networkidle | `waitForLoadState('networkidle')` / `waitUntil: 'networkidle'` (API shapes only, e2e-scoped) | `*.{ts,js}` | Playwright docs warn against `networkidle` — unreliable on modern SPAs. P1. |
| #18 expect.soft overuse | `expect\.soft\(` | `*.{spec.*,test.*}` | `[Playwright]` — `expect.soft()` continues on failure; flag in Phase 2 if >50% of assertions in a single test are `soft`. P1. |
| #3b Cypress uncaught:exception (specs) | `on\('uncaught:exception'.*false` | `*.{cy.*}` | `[Cypress]` — blanket suppression of app errors. P0 unless scoped with `// JUSTIFIED:`. |
| #3b Cypress uncaught:exception (support) | `on\('uncaught:exception'.*false` | `cypress/support/**/*.{ts,js}` | Same check in support files where global suppression is often placed. |

## Group 6 — module-level state

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #19 Module-Level Mutable State | `^let\s+` | `*.{ts,js,tsx,jsx,cy.ts,cy.js}` | Top-level (column-0) `let` declaration in test code. Persists across tests within a worker; collides under parallel workers and retries. Confirm in Phase 2 that the `let` has an initializer (`let counter = 0;`) — pure type declarations (`let page: Page;` reassigned in `beforeEach`) are idiomatic Playwright fixtures and must be SKIPPED. P1. |
