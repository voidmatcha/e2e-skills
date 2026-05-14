# Phase 1: Grep Patterns Reference

Each batch contains independent grep checks. Call all Grep tools within one batch in a SINGLE assistant message so they execute in parallel — each batch = one assistant turn with multiple Grep tool_use blocks.

A hit is intentional and must be **skipped** when `// JUSTIFIED:` appears in any of these positions (exception: #7 Focused Test Leak has no `// JUSTIFIED:` exemption):
1. The line **immediately preceding** the hit.
2. The line immediately preceding the **enclosing call/block** when the hit is inside a callback body — e.g., `// JUSTIFIED:` above `page.evaluate(() => { … document.querySelector(…) … })` covers every qualifying pattern inside that callback.
3. For chained calls split across lines (`page.locator(…)\n  .filter(…)\n  .first()`), the line immediately preceding the chain's starting expression covers `.nth()` / `.first()` / `.last()` further down the chain.

When raw grep output is the only thing you have, always read 1–3 lines of surrounding context before flagging — most false positives come from JUSTIFIED comments sitting just above the visible match.

---

## Batch 1 — send all 5 Grep calls in ONE message

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #3 Error Swallowing | `\.catch\(\s*(async\s*)?\(\)\s*=>` | `*.{ts,js,cy.*}` | `.catch(() => {})` in POM/spec silently hides failures |
| #7 Focused Test Leak | `\.(only)\(` | `*.{spec.*,test.*,cy.*}` | `test.only` / `it.only` / `describe.only` — zero legitimate committed uses, always P0 |
| #9 Hard-coded Sleeps | `waitForTimeout` | `*.{ts,js,cy.*}` | Explicit sleeps cause flakiness |
| #9b Cypress Sleeps | `cy\.wait\(\d` | `*.{cy.*}` | Cypress numeric waits |
| #6 Raw DOM Queries | `document\.querySelector` | `*.{ts,js,cy.*}` | Bypasses framework auto-wait (covers `evaluate()` and `waitForFunction()`). Search POM files too. |

## Batch 2 — send all 6 Grep calls in ONE message

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #4a Always-true math | `toBeGreaterThanOrEqual\(0\)` | `*.{ts,js,cy.*}` | Mathematically always true |
| #4b Vacuous attached | `toBeAttached\(\)` | `*.{ts,js,cy.*}` | Flag every hit; confirm in Phase 2 whether the element is unconditionally rendered (→ P0 vacuous) or CSS-hidden (`// JUSTIFIED:` → skip) |
| #4c One-shot isVisible | `expect\(await.*\.isVisible\(\)\)` | `*.{spec.*,test.*}` | One-shot boolean, no auto-retry |
| #4d One-shot state | `expect\(await.*\.(isDisabled\|isEnabled\|isChecked\|isHidden)\(\)\)` | `*.{spec.*,test.*}` | Same one-shot boolean problem |
| #4e One-shot content | `expect\(await.*\.(textContent\|innerText\|getAttribute\|inputValue)\(\)\)` | `*.{spec.*,test.*}` | Resolves immediately; use `toHaveText()`, `toHaveAttribute()`, `toHaveValue()` |
| #4h One-shot URL | `expect\(page\.url\(\)\)` | `*.{spec.*,test.*}` | `page.url()` reads URL at one instant with no retry; use `await expect(page).toHaveURL(...)` |

## Batch 3 — send all 5 Grep calls in ONE message

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #4f Locator-as-truthy | `\.toBeTruthy\(\)` | `*.{ts,js,cy.*}` | Flag hits where the subject is a Locator (always truthy JS object regardless of element existence). Non-Locator subjects (e.g., boolean variables) are fine — confirm in Phase 2. |
| #4g Timeout zero | `timeout:\s*0` | `*.{ts,js,cy.*}` | Disables auto-retry entirely; flag unless `// JUSTIFIED:` on line above |
| #5a Conditional bypass | `if.*(isVisible\|is\(.*:visible.*\))` | `*.{spec.*,test.*,cy.*}` | `expect()` gated behind runtime `if` — silently skips assertions |
| #5b Force true | `force:\s*true` | `*.{ts,js,cy.*}` | Bypasses actionability checks (visibility, enabled state) |
| #10b Serial ordering | `\.describe\.serial\(` | `*.{spec.*,test.*}` | `[Playwright only]` — order-dependent tests break parallel sharding |

## Batch 4 — send all 4 Grep calls in ONE message

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #8a Dangling locator | `^\s*(page\.locator\(\|page\.getBy)` | `*.{spec.*,test.*}` | `[Playwright only]` — locator created as standalone statement, no `expect()`, no action, no assignment. A complete no-op. |
| #8b Boolean discarded | `^\s*await .*\.(isVisible\|isEnabled\|isChecked\|isDisabled\|isEditable\|isHidden)\(\)\s*;` | `*.{spec.*,test.*,cy.*}` | Boolean result computed and thrown away — asserts nothing |
| #10a Positional selectors | `\.nth\(\|\.first\(\)\|\.last\(\)` | `*.{spec.*,test.*,cy.*}` | Breaks when DOM order changes; needs `// JUSTIFIED:` |
| #14 Hardcoded credentials | `(login\|fill\|type).*(['"].*password\|['"].*secret\|['"]admin['"])` | `*.{spec.*,test.*,cy.*}` | String literals as credentials; use env vars or fixtures |

## Batch 5 — send all 7 Grep calls in ONE message

#3b requires two Grep calls for different globs.

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #15 Missing await on expect | `^\s*expect\(` | `*.{spec.*,test.*}` | `[Playwright]` — `expect(locator).toBeVisible()` without `await` silently resolves to a Promise that is never checked. Always P0. |
| #16 Missing await on action | `^\s*page\.(locator\|getBy\w+)\(.*\)\.(click\|fill\|type\|press\|check\|uncheck\|selectOption\|setInputFiles\|hover\|focus\|blur)\(` | `*.{spec.*,test.*}` | `[Playwright]` — Action without `await` creates an unresolved Promise. Always P0. Confirm in Phase 2 that the hit line lacks a leading `await`. |
| #17 Direct page action API | `page\.(click\|fill\|type\|check\|uncheck\|selectOption)\(["'\`]` | `*.{spec.*,test.*}` | `[Playwright]` — prefer locator-based `page.locator(selector).click()` / `.fill()` for composition and clearer failures. P1. |
| #9c Networkidle | `networkidle` | `*.{ts,js}` | Playwright docs warn against `networkidle` — unreliable on modern SPAs. P1. |
| #18 expect.soft overuse | `expect\.soft\(` | `*.{spec.*,test.*}` | `[Playwright]` — `expect.soft()` continues on failure; flag in Phase 2 if >50% of assertions in a single test are `soft`. P1. |
| #3b Cypress uncaught:exception (specs) | `on\('uncaught:exception'.*false` | `*.{cy.*}` | `[Cypress]` — blanket suppression of app errors. P0 unless scoped with `// JUSTIFIED:`. |
| #3b Cypress uncaught:exception (support) | `on\('uncaught:exception'.*false` | `cypress/support/**/*.{ts,js}` | Same check in support files where global suppression is often placed. |
