<!-- Generated from applying-fixes.md §4.1 by scripts/dev/split-pattern-reference.py; edit the source, not this copy. -->
### 4.1 Canonical Replacements

Use these idiomatic fixes. Don't invent alternatives. Preserve the original assertion contract first; where the contract permits a retrying Playwright matcher or `expect.poll`, use it to replace a one-shot read that can race against async state.

#### Playwright

| Anti-pattern (#) | Idiomatic fix | Notes |
|------------------|---------------|-------|
| `#4c-4e` `expect(await x.isVisible()).toBe(true)` | `await expect(x).toBeVisible()` | Auto-retry until visible |
| `#4c-4e` `expect(await x.isDisabled()).toBe(true)` | `await expect(x).toBeDisabled()` | Auto-retry |
| `#4c-4e` `expect(await x.isChecked()).toBe(true)` | `await expect(x).toBeChecked()` | Auto-retry |
| `#4c-4e` `expect(await x.textContent()).toBe(v)` | `await expect.poll(() => x.textContent()).toBe(v)` | Preserves raw `textContent()` equality. Use `toHaveText(v)` only when Playwright's whitespace normalization is the intended contract. |
| `#4c-4e` `expect(await x.innerText()).toContain(v)` | `await expect.poll(() => x.innerText()).toContain(v)` | Preserves `innerText()` substring semantics instead of changing the source value or normalization rules. |
| `#4c-4e` `expect(await x.inputValue()).toBe(v)` | `await expect(x).toHaveValue(v)` | Verify subject is `<input>`/`<textarea>`/`<select>` |
| `#4c-4e` `expect(await x.count()).toBe(N)` | `await expect(x).toHaveCount(N)` | **Common pattern** — applies to bare locator OR chained (`x.locator(y).count()`, `x.nth(i).count()`). Auto-retry until count settles. |
| `#4c-4e` `expect(await x.allTextContents()).toContain(v)` | `await expect.poll(() => x.allTextContents()).toContain(v)` | Preserves exact membership in the returned `string[]`. Scalar `toContainText(v)` instead checks substring text and may fail strictness on a multi-element locator. |
| `#4c-4e` `expect(await x.all()).toHaveLength(N)` | `await expect(x).toHaveCount(N)` | Same as above; `.all()` form is just verbose |
| `#4h` `expect(page.url()).toBe(x)` / `.toEqual(x)` | `await expect(page).toHaveURL(x)` | **NOT `expect.poll`** — `toHaveURL` is canonical |
| `#4h` `expect(page.url()).not.toMatch(re)` | `await expect(page).not.toHaveURL(re)` | Auto-retry |
| `#4h` `expect(page.url()).toContain(x)` (substring) | `await expect.poll(() => page.url()).toContain(x)` | **CANONICAL — use this form**. **❌ AVOID `await expect(page).toHaveURL(new RegExp(x))`** — `x` may contain regex metacharacters (`.`, `+`, `?`, `(`, `)`, `[`, `]`, `\`, `^`, `$`, `*`, `{`, `}`, `|`) that need escaping. Without escaping, the match silently broadens (`.` matches any char) or breaks (`(` opens a group). **❌ AVOID `await expect(page).toHaveURL((url) => url.toString().includes(x))`** — functionally correct but creates idiom drift; the `expect.poll().toContain()` form above is the canonical web-first substring assertion. `await page.waitForURL(url => url.toString().includes(x))` is acceptable ONLY when you need to wait BEFORE the next action runs (i.e., as a navigation gate) rather than to assert. |
| `#4b` (positive) `await x.click(); await expect(x).toBeAttached()` | Remove it only when the action already proves attachment, or replace it with the promised visible/result-state assertion | Keep `toBeAttached()` when DOM attachment itself is the contract |
| `#4f` `expect(page.getByText(...)).toBeTruthy()` | `await expect(page.getByText(...)).toBeVisible()` | Playwright Locator assertion; auto-retries. If hidden-but-attached is the intended contract, use `await expect(...).toBeAttached()` instead. **Do not use jest-dom matchers in Playwright tests.** |
| `#15` `expect(locator).toBeVisible()` (no await) | `await expect(locator).toBeVisible()` | The async matcher already retries; `await` makes the test observe its completion or rejection before proceeding. |
| `#16` `page.locator(...).click()` (statement, no await) | `await page.locator(...).click()` | |
| `#8b` `await x.isVisible();` (boolean discarded) | `await expect(x).toBeVisible();` | P0 only after confirming the discarded boolean was the scenario's sole verification; otherwise delete the dead read or address a separate #2 outcome gap |
| `#7` `test.describe.only(...)` / `it.only(...)` | `test.describe(...)` / `it(...)` | Every committed focus modifier is P0. Even a current singleton silently narrows future discovery and turns the next sibling test into skipped coverage; no `JUSTIFIED` exemption exists. |

#### Cypress

| Anti-pattern (#) | Idiomatic fix | Notes |
|------------------|---------------|-------|
| `#4g` `cy.X(..., { timeout: 0 }).should("not.exist")` | Remove `, { timeout: 0 }` only when the intended contract is retry-until-absent | With `timeout: 0`, this is an immediate snapshot after the test's causal gate; it does not prove the element never appeared. Without `timeout: 0`, the negative assertion can still pass as soon as absence is observed, so it also does not prove temporal non-appearance. Keep an intentional, causally gated snapshot and document that intent. The same review applies to chained positive assertions with `{ timeout: 0 }`. |
| `should("be.visible").click({ force: true })` | Verify the actual actionability blocker and intent before removing `force` | Visibility alone does not prove the element is enabled, stable, uncovered, or otherwise actionable. Remove `force` only after the relevant test passes with the default actionability checks. |
| `scrollIntoView().click({ force: true })` | Verify the actual actionability blocker and intent before removing `force` | Scrolling does not by itself prove full actionability. Remove `force` only after the relevant test passes with the default actionability checks. |
| `expect(cy.url()).toContain(x)` (raw Chai assertion on a Cypress chain) | `cy.url().should("include", x)` | Cypress `should` auto-retries. **AVOID** raw `expect(...)` against a Cypress chain — `expect.poll` is Playwright-only. |

#### Conditional React Testing Library / Jest / Vitest fix

Before proposing or applying any `#4f` fix for an RTL/Testing-Library helper inside an otherwise in-scope Playwright/Cypress spec, read [`rtl-jest-dom-fixes.md`](rtl-jest-dom-fixes.md). It contains the scope boundary, the exact §4.1 replacement row to quote for `**§4.1 row:**` attribution, and the mandatory Jest/Vitest setup and dependency checks. Do not load it for ordinary Playwright Locator or Cypress fixes.

**Note:** `not.toBeAttached()` is the canonical assertion for "element is not in DOM." A positive `.toBeAttached()` is also meaningful when DOM attachment itself is the promised state. Report #4b only when attachment adds no evidence for the action's promised outcome.

#### Flake-protective vs Flake-neutral

Most replacements above are **flake-protective**: the new form auto-retries where the old read once. Examples:
- `expect(await x.isVisible()).toBe(true)` reads ONCE → races against async render
- `await expect(x).toBeVisible()` retries until visible OR timeout → handles async render gracefully
- Playwright `expect(page.getByText(...)).toBeTruthy()` always passes on the Locator object; `await expect(page.getByText(...)).toBeVisible()` retries and verifies rendered UI

A few replacements are **flake-neutral** (semantic improvement only, not flake-fixing):
- RTL / Jest / Vitest `#4f` toBeTruthy → toBeInTheDocument (`screen.getByText` already throws on miss; both pass on success)
- `#7` `.only` removal (no flake change; just removes debug leak)
- `#4b` weak positive `toBeAttached()` replacement/removal when attachment adds no outcome proof

When the user says "test was already flaky and I added the band-aid for that reason" — see 4.2 below.
