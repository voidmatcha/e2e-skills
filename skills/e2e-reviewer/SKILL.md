---
name: e2e-reviewer
description: 'Use when reviewing, auditing, or improving E2E test specs for Playwright or Cypress — static code analysis of existing test files, not diagnosing runtime failures. Triggers on "review my tests", "audit test quality", "find weak tests", "my tests always pass but miss bugs", "tests pass CI but miss regressions", "improve playwright tests", "improve cypress tests", "check test coverage gaps", "my tests are fragile", "tests break on every UI change", "test suite is hard to maintain", "we have coverage but bugs still slip through", "flaky tests", "test anti-patterns", "check my e2e tests", "tests pass locally but fail in CI". Reviews 19 anti-patterns grouped by severity. P0 must-fix (silent always-pass): name-assertion mismatch, missing Then, error swallowing, Cypress uncaught:exception suppression, always-passing assertions, bypass patterns, focused test leak, missing assertions, missing auth setup, missing await on expect, missing await on action. P1 should-fix (poor diagnostics): raw DOM queries, hard-coded sleeps, flaky test patterns, inconsistent POM usage, hardcoded credentials, direct page action API, expect.soft overuse. P2 nice-to-fix (maintenance): YAGNI + zombie specs.'
license: Apache-2.0
metadata:
  author: voidmatcha
  version: "1.3.0"
---

# E2E Test Scenario Quality Review

Systematic checklist for reviewing E2E **spec files AND Page Object Model (POM) files**. Covers Playwright and Cypress with full grep + LLM analysis. General principles (name-assertion alignment, missing Then, YAGNI) apply to any framework, but automated grep patterns are Playwright/Cypress-specific.

**Reference:**
- Playwright best practices: https://playwright.dev/docs/best-practices
- Cypress best practices: https://docs.cypress.io/app/core-concepts/best-practices

## Phase 0: Framework Detection

Before running checks, determine the framework by grepping for **actual import statements** in `.ts`/`.js` files:
- `@playwright/test` → Playwright
- `cypress` (as a module import or `cy.` call) → Cypress

**Do NOT use these as signals:**
- `nx.json` `"e2eTestRunner"` field — a generator-default, often left in place after Cypress/Playwright was removed (observed in OSS trial: repo had `"e2eTestRunner": "cypress"` but Cypress infra was deleted 17 days prior in a merged PR; only `.spec.ts` files were Jest unit tests)
- `package-lock.json` cached transitive deps — Cypress can appear in lockfile long after removal
- `.spec.ts` filename alone — could be Jest/Vitest unit tests, not Playwright/Cypress E2E

When `.spec.ts` files exist without `@playwright/test` or `cy.` imports, inspect 1-2 of them: presence of `TestBed`/`describe()` + `it()` without `page.goto`/`cy.visit` indicates Jest unit tests → **out of e2e-reviewer scope**.

**Skip framework-irrelevant checks:** If Playwright, skip Cypress-specific greps (`#9b cy.wait(ms)`, `#3b Cypress uncaught:exception`). If Cypress, skip Playwright-specific greps (`#8a dangling page.locator`, `#10b describe.serial`, `#15 missing await on expect`, `#16 missing await on action`, `#17 direct page action API`, `#18 expect.soft overuse`). This eliminates noise in Phase 1 output.

---

## Phase 1: Mechanical Scan

Run the bundled scanner against the test directory:

```bash
bash <skill-base>/scripts/scan.sh <test-dir>
```

`<skill-base>` is the directory shown in the Skill tool's "Base directory" output (e.g., `~/.claude/skills/e2e-reviewer/`). Auto-detect `<test-dir>` from project structure (common: `e2e/`, `tests/`, `__tests__/`, `spec/`, `cypress/e2e/`).

The scanner internally uses, in priority order:
1. **`eslint-plugin-playwright` / `eslint-plugin-cypress`** — when locally installed in the target project (AST-based, most accurate, lowest FP rate)
2. **`ast-grep`** — Tree-sitter-backed for patterns the eslint plugins miss (e.g., `#3b` Cypress `uncaught:exception` blanket, `#4g` `{timeout:0}.should("not.exist")`, `#4f` Locator-as-truthy)
3. **`ripgrep` regex** — universal fallback covering all remaining patterns

Output is grouped per pattern ID (`#3`, `#4a`, `#15`, etc.) with `file:line:matched-line`. See `references/grep-patterns.md` for the meaning of each ID.

**Evidence rule:** scanner hits are mechanical review signals. Report exact matches, then use Phase 2 where the rule requires intent or project context.

**Suppression — `// JUSTIFIED:`:** a hit is intentional and must be **skipped** when `// JUSTIFIED:` appears in any of these positions (exception: `#7` Focused Test Leak has no exemption):
1. The line **immediately preceding** the hit
2. The line immediately preceding the **enclosing call/block** when the hit is inside a callback body — e.g., `// JUSTIFIED:` above `page.evaluate(() => { … document.querySelector(…) … })` or `page.waitForFunction(() => { … })` covers every qualifying pattern inside that callback
3. For chained calls split across lines (`page.locator(…)\n  .filter(…)\n  .first()`), the line immediately preceding the chain's **starting expression** covers `.nth()` / `.first()` / `.last()` further down the chain

Phase 2 also recognizes these as JUSTIFIED-equivalent (informal):
- `// eslint-disable-next-line <rule> -- <concrete rationale>` with concrete reason
- Author rationale comments above the hit (signals intentional vs accidental — see 4.2 band-aid awareness)
- Comments describing dual-mode UI handlers (e.g., `// Single workspace mode — no workspace selection` above `if (await x.isVisible())` indicates intentional dual-mode, not a band-aid)

**Comment / string-literal false positives** (mostly handled by ast-grep and eslint when available; remaining ones for Phase 2 LLM):
- Trailing `// comment` on a code line — token in code triggers, comment is noise
- Block comment `/* … { timeout: 0 } … */` containing the token
- String literal containing the token (e.g., `"test.only('focused', ...)"` in a meta-test for the rule itself)
- Same token in a different language API (e.g., Node `fs.rm(path, { force: true })`)

`try/catch` wrapping in spec files (#3 partial) requires LLM judgment (Phase 2) — too many legitimate uses to scan reliably.

---

## Phase 2: LLM Review (Semantic And Context Checks Only)

Patterns already detected in Phase 1 (#3 partial, #4, #5, #6, #7, #8, #9, #10 partial, #14, #15, #16, #17, #18, #3b) are **skipped** unless they need LLM confirmation.
The LLM performs only these checks:

| # | Check | Reason |
|---|-------|--------|
| 1 | Name-Assertion Alignment | Requires semantic interpretation |
| 2 | Missing Then | Requires logic flow analysis |
| 3 | Error Swallowing — `try/catch` in specs | Too many legitimate non-test uses; requires reading context |
| 4 | Always-Passing — `.toBeTruthy()` confirmation | Phase 1 flags all `.toBeTruthy()` hits; LLM confirms which ones have a Locator subject (P0) vs. a legitimate boolean variable (OK). Do NOT re-report other #4 sub-patterns already covered in Phase 1. |
| 4c-4e | One-shot state — Locator-subject confirmation | Phase 1 flags `expect(await x.isVisible()/isDisabled()/textContent()/inputValue()/...)`. LLM confirms `x` is a Playwright `Locator`/`Page`, NOT a custom service or helper method. False positive examples: `expect(await myService.isEnabled()).toBe(true)` (custom service), `expect(await checkSessionValid(page)).toBe(true)` (helper returning Promise<boolean>). Flag P0 only when subject is a Locator/Page. |
| 8 | Missing Assertion — Cypress dangling selectors | `cy.get(...)` standalone requires manual check |
| 8a | Multi-line continuation skip | Phase 1 flags standalone `page.locator(...)` lines via `^\s*page\.(locator|getBy*)(...)$`. LLM SKIPS the hit if the previous non-empty line ends with `(` or `,` — it's a continuation inside a multi-line `await expect(\n  page.locator(...)\n)…`, not a dangling statement. |
| 10 | Flaky Test Patterns | For each grep hit that has `// JUSTIFIED:`, verify the rationale is concrete (e.g. "server returns in fixed order") rather than vague ("needed for now"); flag if the comment doesn't actually justify the position-coupling or serial dependency. Skip if no JUSTIFIED comment — Phase 1 already flagged. |
| 11 | YAGNI in POM + Zombie Specs | Requires usage grep then judgment |
| 12 | Missing Auth Setup | Spec navigates to protected routes (`/dashboard`, `/settings`, `/admin`, etc.) without preceding login, `storageState`, or auth `beforeEach`. Flag P0 — tests will hit login redirects. |
| 13 | Inconsistent POM Usage | POM is imported but spec bypasses it with raw `page.fill`/`page.click` for operations the POM should encapsulate. Flag P1. |
| 15 | Missing `await` on `expect()` confirmation | Phase 1 flags lines that start with `expect(` (no leading `await`). LLM confirms the subject is a Playwright `Locator` / `Page` — non-Locator expects like `expect(count).toBe(3)` don't need `await`. Flag P0 only when the subject is a Locator/Page. |
| 16 | Missing `await` on action confirmation | Phase 1 flags lines that start with `page.locator(...).action(` or `page.getBy...(...).action(` (no leading `await`). LLM confirms the line lacks `await` and the action is a real Playwright action (not a synchronous chain). LLM also SKIPS the hit if the line is inside a `Promise.all([` or `Promise.race([` array — array elements don't need explicit `await` because the `Promise.all` awaits them. Flag P0 only for true standalone statements. |
| 18 | `expect.soft()` overuse confirmation | Phase 1 flags all `expect.soft()` hits; LLM counts: if >50% of assertions in a single test are `soft`, flag P1 — soft assertions mask cascading failures. A few `soft` assertions among many hard ones is fine. |

**Retry-wrapper skip (applies to #4c-4e, #4h, #15, #16):** When a Phase 1 hit's enclosing function is the callback argument of `await expect(async () => { ... }).toPass({...})` (Playwright) or `await expect.poll(async () => { ... }).toX(...)`, the Playwright harness re-runs the callback until it passes or times out — one-shot reads and unawaited `expect()` lines inside are not silent-always-pass. SKIP P0 reporting for these hits. (Distinct from the Promise.all/Promise.race skip on the #16 row, which is about array elements, not retry callbacks.) Real case: a `payload` review found 9/20 `#4h` raw hits sat inside `.toPass(...)` callbacks — none were real P0.

**Consolidation rule:** If a single code block triggers multiple checks (e.g., `page.evaluate` + `toBeTruthy` + `document.querySelector`), report it as ONE finding with all rule numbers in the heading (e.g., `[P0] #4f + #6: ...`). Do not create 3-4 separate findings for the same lines of code.

**#11 YAGNI — grep-assisted procedure:** For each POM file in scope, list all public members (locators + methods). Then grep each member name across all spec files and other POMs in a single parallel batch:
```
Grep pattern: "memberName1|memberName2|memberName3|..."
Glob: "*.{spec.*,test.*,cy.*}"
```
This is much faster than grepping each member individually. Classify results: USED / INTERNAL-ONLY (make `private`) / UNUSED (delete).

---

## Phase 2.5: Systemic Issues

After individual findings are catalogued, synthesize cross-cutting patterns that affect the test suite as a whole. Check for:

| Issue | How to check | Sev |
|-------|-------------|-----|
| **No authentication strategy** (suite-level rollup of #12) | 3+ specs across the suite navigate to protected routes without login/storageState. Always emit a single rollup line here; do not enumerate per-file findings — those belong in Phase 2. | P0 |
| **No stable user-facing selectors** | [Playwright] Zero uses of `getByRole` / `getByTestId` / `getByLabel` / `getByPlaceholder` / `getByText` across all files. [Cypress] Zero uses of `[data-cy=]` / `[data-testid=]` selectors and no `cy.findBy*` calls (cypress-testing-library). | P2 |
| **Missing `beforeEach`** | 3+ tests in a `describe` repeat the same setup code (POM instantiation + navigation) | P2 |

**Deduplication rule:** Phase 2.5 issues are *suite-wide* findings. If an issue is already raised once per file in Phase 2 (e.g. #12 Missing Auth Setup), do not also list each file under Phase 2.5 — emit a single rollup line with the affected file count.

Output as a dedicated section:
```markdown
## Systemic Issues
- **No authentication strategy:** N tests navigate to protected routes without auth setup. Add `storageState` or auth fixture. (Rolls up #12 across N files.)
- **No stable user-facing selectors:** [Playwright] 0 uses of getByRole/getByTestId across N files. [Cypress] 0 uses of `[data-cy=]`/`[data-testid=]` across N files. Migrate to user-facing locators.
```

Only report systemic issues that are actually present. Skip this section if none apply.

---

## Phase 3: Coverage Gap Analysis (After Review)

After completing Phase 1 + 2 + 2.5, identify scenarios the test suite does NOT cover. Scan the page/feature under test and flag missing:

| Gap Type | What to look for |
|----------|-----------------|
| Error paths | Form validation errors, API failure states (4xx/5xx), network offline, timeout retry, partial-success batches |
| Edge cases | Empty state, max-length input, special characters, zero-result lists, very-long content (overflow/truncation) |
| Race / concurrent | Optimistic-update rollback, double-click submit, in-flight request when user navigates away, stale-while-revalidate display |
| Accessibility | Keyboard navigation order, screen reader labels (`aria-label`/`aria-describedby`), focus management after modal close, focus trap on dialog |
| Auth boundaries | Unauthorized redirect (`/login?from=...`), expired session mid-action, role-based UI visibility, multi-tenant scope leak |
| Responsive / device | Mobile viewport (< 768px), touch vs hover interactions, locale-dependent formatting (date/currency/RTL) |

**Context-aware suggestions are mandatory.** Each gap must reference a SPECIFIC finding from Phase 1/2 — pattern ID (`#4a`), file:line, or assertion target. Generic suggestions ("add error path tests") that could apply to any test suite are LOW value and should be omitted. If you can't tie a gap to an observed pattern, don't list it.

**Triage rule**: gaps that "interact with" a P0 finding are highest value. Example: a #5a conditional bypass observed in profile.spec.ts → suggest a coverage gap test for the OPPOSITE branch (the one the `if` skipped) — that branch was the unintentional silent-pass surface.

**Output:** List up to 5 highest-value missing scenarios as suggestions, not requirements. Format:

```markdown
## Coverage Gaps (Suggestions)
1. **[Edge case]** No test for empty dashboard state — currently `toBeGreaterThanOrEqual(0)` masks this (see #4a-1). Verify empty-state message when no metrics exist.
2. **[Error path]** No test for form submission with server error — the profile update test (settings:9) has no error path at all.
3. **[Race]** `if (await spinner.isVisible())` at checkout.spec.ts:42 (see #5a above) skips the slow-network branch entirely — add a route-throttled variant that forces the spinner path.
```

---

## Phase 4: Applying Fixes (Canonical Replacements + Band-Aid Awareness)

When you go beyond reviewing into fixing, follow these rules. They prevent two common failure modes: (1) using a non-canonical replacement that re-introduces flake, and (2) ripping out a "band-aid" anti-pattern that was actually load-bearing for an upstream flake.

### 4.1 Canonical Replacements

Use these idiomatic fixes. Don't invent alternatives. **The replacements below are flake-protective by design** — every web-first matcher (`toBeVisible`, `toHaveText`, `toHaveCount`, `toHaveURL`, etc.) auto-retries until the assertion passes or times out, replacing one-shot reads that race against async state.

#### Playwright

| Anti-pattern (#) | Idiomatic fix | Notes |
|------------------|---------------|-------|
| `#4c-4e` `expect(await x.isVisible()).toBe(true)` | `await expect(x).toBeVisible()` | Auto-retry until visible |
| `#4c-4e` `expect(await x.isDisabled()).toBe(true)` | `await expect(x).toBeDisabled()` | Auto-retry |
| `#4c-4e` `expect(await x.isChecked()).toBe(true)` | `await expect(x).toBeChecked()` | Auto-retry |
| `#4c-4e` `expect(await x.textContent()).toBe(v)` | `await expect(x).toHaveText(v)` | Auto-retry until text settles |
| `#4c-4e` `expect(await x.innerText()).toContain(v)` | `await expect(x).toContainText(v)` | Auto-retry |
| `#4c-4e` `expect(await x.inputValue()).toBe(v)` | `await expect(x).toHaveValue(v)` | Verify subject is `<input>`/`<textarea>`/`<select>` |
| `#4c-4e` / `#15` `expect(await x.count()).toBe(N)` | `await expect(x).toHaveCount(N)` | **Common pattern** — applies to bare locator OR chained (`x.locator(y).count()`, `x.nth(i).count()`). Auto-retry until count settles. |
| `#15` `expect(await x.all()).toHaveLength(N)` | `await expect(x).toHaveCount(N)` | Same as above; `.all()` form is just verbose |
| `#4h` `expect(page.url()).toBe(x)` / `.toEqual(x)` | `await expect(page).toHaveURL(x)` | **NOT `expect.poll`** — `toHaveURL` is canonical |
| `#4h` `expect(page.url()).not.toMatch(re)` | `await expect(page).not.toHaveURL(re)` | Auto-retry |
| `#4h` `expect(page.url()).toContain(x)` (substring) | `await expect.poll(() => page.url()).toContain(x)` | **CANONICAL — use this form**. **❌ AVOID `await expect(page).toHaveURL(new RegExp(x))`** — `x` may contain regex metacharacters (`.`, `+`, `?`, `(`, `)`, `[`, `]`, `\`, `^`, `$`, `*`, `{`, `}`, `|`) that need escaping. Without escaping, the match silently broadens (`.` matches any char) or breaks (`(` opens a group). **❌ AVOID `await expect(page).toHaveURL((url) => url.toString().includes(x))`** — functionally correct but creates idiom drift; the `expect.poll().toContain()` form above is the canonical web-first substring assertion. `await page.waitForURL(url => url.toString().includes(x))` is acceptable ONLY when you need to wait BEFORE the next action runs (i.e., as a navigation gate) rather than to assert. |
| `#4b` (positive) `await x.click(); await expect(x).toBeAttached()` | Remove the assertion | Vacuous after action |
| `#4f` `expect(getByText(...)).toBeTruthy()` | `expect(getByText(...)).toBeInTheDocument()` | **REQUIRES jest-dom — see prereq check below** |
| `#15` `expect(locator).toBeVisible()` (no await) | `await expect(locator).toBeVisible()` | Adding `await` makes it auto-retry |
| `#16` `page.locator(...).click()` (statement, no await) | `await page.locator(...).click()` | |
| `#8b` `await x.isVisible();` (boolean discarded) | `await expect(x).toBeVisible();` | Silent always-pass case — the `await x.isVisible()` returned a Promise<boolean> nobody read |
| `#7` `test.describe.only(...)` / `it.only(...)` | `test.describe(...)` / `it(...)` | **Severity tier**: in a file with N≥2 tests, `.only` SILENT-SKIPS them all (CRITICAL). In a single-test file, removing `.only` is just debug-leak cleanup (smell only). |

#### Cypress

| Anti-pattern (#) | Idiomatic fix | Notes |
|------------------|---------------|-------|
| `#4c-4e` `expect(await x.count()).toBe(N)` (rare in Cypress) | `cy.get(selector).should("have.length", N)` | Cypress built-in retries `should` automatically |
| `#15` Cypress equivalent | `cy.get(selector).should("be.visible")` | `should` retries; never use `expect(await ...)` against a Cypress chain |
| `#4g` `cy.X(..., { timeout: 0 }).should("not.exist")` | Remove `, { timeout: 0 }` | **Caveat**: see 4.2 — may be intentional snapshot-of-absence. If author intent is "MUST NOT appear at any moment", keep with JUSTIFIED comment. Cypress canonical: `cy.X(...).should("not.exist")` (no timeout option), relying on `defaultCommandTimeout` from `cypress.config.ts`. The same anti-pattern exists chained as `cy.X(..., {timeout: 0}).should("exist")` — also remove. |
| `should("be.visible").click({ force: true })` | `should("be.visible").click()` | Visibility check covers force's purpose; force is redundant. **CAVEAT**: visibility check must be on the SAME element as the click — not on a parent (see 4.2). |
| `scrollIntoView().click({ force: true })` | `scrollIntoView().click()` | scrollIntoView ensures interactability; force is redundant |
| `expect(cy.url()).toContain(x)` (rare; Cypress equivalent of `#4h .toContain`) | `cy.url().should("include", x)` | Cypress `should` auto-retries; no need for `expect.poll` workaround. **AVOID** raw `expect(...)` against a Cypress chain — `expect.poll` is Playwright-only |

#### React Testing Library / Vitest / Jest unit tests

| Anti-pattern (#) | Idiomatic fix | Notes |
|------------------|---------------|-------|
| `#4f` `expect(screen.getBy*(...)).toBeTruthy()` | `expect(screen.getBy*(...)).toBeInTheDocument()` | jest-dom matcher — see prereq check below |

**Scope note (Phase 0 + 4.1 reconciliation):** Phase 0 puts pure Jest/Vitest **unit-test** files (`.test.tsx`/`.test.ts` with no Playwright/Cypress import, no `page.goto`/`cy.visit`) out of e2e-reviewer scope — **do NOT auto-apply** this RTL row to those files. The row applies when (a) RTL/Testing-Library helpers appear inside an in-scope Playwright/Cypress spec (rare), or (b) Storybook interaction tests (`.stories.ts*`) that use `storybook/test`'s `within()` + Testing-Library `getBy*` — those exercise rendered UI and are treated as in-scope component E2E. For pure Jest/Vitest unit tests, REPORT the smell but defer to a unit-test reviewer; do not bulk-fix. (Observed divergence in 13-repo OSS trial: same row was applied to Storybook stories in one repo and refused in `.test.tsx` Jest files in another — the rule above resolves both.)

**Note:** `not.toBeAttached()` is NOT vacuous — it's the canonical assertion for "element is not in DOM". Only the positive `.toBeAttached()` (after an action that already required attachment) is vacuous.

#### `#4f` jest-dom prerequisite check (MANDATORY before bulk replacement)

`.toBeInTheDocument()` is a `jest-dom` matcher — without it, the assertion throws `TypeError: expect(...).toBeInTheDocument is not a function`. Verify presence before replacing:

1. **Search for global setup**:
   ```bash
   rg -l 'jest-dom' jest.config* vitest.config* setupTests* test/setup* __tests__/setup* package.json | head
   ```
   If found in a setup file referenced by `setupFilesAfterEach` (Jest) or `setupFiles` (Vitest config), no per-file import needed.

2. **Check for shared preset**: some monorepos route jest-dom through a shared package (workspace preset, design-system shared setup, internal test-utils). If `jest.config`/`vitest.config` references a preset by name (`preset:` field, `setupFilesAfterEach: ["<package-name>/setup"]`), open the preset's setup file and grep for `jest-dom`. Common shapes: a framework-specific `*-jest-presets` package, a shared design-system test-utils setup, or an internal `@<org>/test-utils` workspace package. Your monorepo's preset name will differ but the pattern is the same.

3. **If neither**: add a per-file import. Choose by test runner:
   - **Jest**: `import '@testing-library/jest-dom';`
   - **Vitest**: `import '@testing-library/jest-dom/vitest';` (the `/vitest` subpath wires `expect.extend` into Vitest's expect — without it, Vitest sees Jest's global expect being extended, not Vitest's)

4. **Sanity check**: after changes, verify package.json includes `@testing-library/jest-dom` (or `@types/testing-library__jest-dom`); if not, add as devDependency.

#### Flake-protective vs Flake-neutral

Most replacements above are **flake-protective**: the new form auto-retries where the old read once. Examples:
- `expect(await x.isVisible()).toBe(true)` reads ONCE → races against async render
- `await expect(x).toBeVisible()` retries until visible OR timeout → handles async render gracefully

A few replacements are **flake-neutral** (semantic improvement only, not flake-fixing):
- `#4f` toBeTruthy → toBeInTheDocument (RTL `getByText` already throws on miss; both pass on success)
- `#7` `.only` removal (no flake change; just removes debug leak)
- `#4b` positive `toBeAttached()` removal (vacuous either way)

When the user says "test was already flaky and I added the band-aid for that reason" — see 4.2 below.

### 4.2 Band-Aid Awareness

Some anti-patterns may have been added DELIBERATELY by a test author trying to suppress an existing flake. Removing the band-aid without addressing the root cause will break the test in CI.

| Pattern | Likely a band-aid? | If you remove and test breaks, root cause is usually... |
|---------|--------------------|--------------------------------------------------------|
| `force: true` (bare, no preceding readiness check) | **HIGH** | Element occluded by overlay, animation in progress, scroll needed. Add explicit wait for the actual blocker, don't re-add force. |
| `should("be.visible").click({force: true})` or `scrollIntoView().click({force: true})` | **LOW** | Preceding readiness check covers force's purpose — auto-fixable; see 4.1 Cypress table. **CRITICAL CAVEAT**: the readiness check must be on the SAME element as the click. If `await expect(parentScene).toBeVisible()` is followed by `await childButton.click({force:true})`, the visibility was on parent — child may still be obscured/animating. Verify subject identity before removing force. (Anti-example: removing force from `getByTestId('sql-editor-materialization-button').click({force:true})` after `expect(page.locator('.scene-name h1 span').getByText(...)).toBeVisible()` is WRONG — scene title visibility ≠ button actionability.) |
| `waitForTimeout(N)` / `cy.wait(ms)` | **HIGH** | Author saw a flake, picked a number. Find the specific async signal: `waitForResponse`, `waitForSelector`, custom condition. |
| `if (await x.isVisible({timeout: N}))` (#5a) | **HIGH** | UI state is non-deterministic. Find the missing prerequisite that makes visibility deterministic. |
| `{ timeout: 0 }` on `cy.X(...).should("not.exist")` (#4g) | **MEDIUM** | Snapshot-of-absence semantic ("never appeared") may be intentional. If element flickers briefly, restructure to wait for the right state. |
| `expect.soft(...)` (#18) overuse | MEDIUM | Author wanted to see all failures at once. Consider whether each soft assertion should be a separate test. |
| `expect(await x.isVisible()).toBe(true)` (#4c-4e) | LOW | Usually just unawareness of `toBeVisible()`. Direct mechanical replacement. |
| `not.toBeAttached()` (#4b negative) | LOW | Both forms work. Functional equivalence. (Actually NOT vacuous — see 4.1.) |
| `expect(getByText(...)).toBeTruthy()` (#4f) | LOW | Just verbose. Direct replacement. |

**Rule for batch-fix scenarios** (e.g., applying skill to someone else's repo where you can't run tests):

- **LOW band-aid likelihood** → auto-fix
- **MEDIUM/HIGH band-aid likelihood** → SUGGEST in the report; do not auto-fix; if you do fix, attach a `// JUSTIFIED-CHECK: removed force:true after .scrollIntoView() — verify CI doesn't regress` comment to surface the assumption to the reviewer

This produces a two-tier fix plan in the report:
- **Safe to auto-apply** (LOW): mechanical replacements
- **Requires test verification** (MEDIUM/HIGH): proposed change + investigation hint

#### Cross-checking against PR culture (when GitHub is available)

**When to invoke this check** (ALL of):
1. Repo is a public GitHub OSS project AND `gh auth status` works
2. You're APPLYING fixes (not just generating a review report)
3. AT LEAST one MEDIUM/HIGH band-aid is in the fix set, OR you found a P0 in code recently introduced (last 6 months) by a merged PR

Skip otherwise — the check costs 30-60s wall-time and several thousand tokens per repo, so don't run it for pure-LOW band-aid sets or private code.

**Critical caveat: Approved PR ≠ correct convention.** Empirically observed in a 13-repo OSS trial: multi-round-reviewed merged PRs in 3 different projects (a workflow engine, a chat platform, a chat server) introduced silent-pass P0 bugs that no reviewer caught — `expect(await locator).toBeFocused()` (assertion Promise unawaited), `await locator.isVisible()` (boolean discarded), committed `test.describe.only` (federation suite silently skipped for 9+ months). PR culture check is a **band-aid judgment aid**, NOT an **anti-pattern justification tool**. If `gh pr blame` shows a P0 hit was introduced by a recent merged PR, that is NOT evidence the pattern is intentional — reviewer culture has blind spots, especially for `await` placement and silent skip directives.

When reviewing a public repo, `gh pr list/view/diff` (read-only) on the repo's recent merged test-PRs sharpens band-aid judgment in three ways:

1. **Approved PRs CAN introduce silent-pass P0s.** Real cases observed in OSS trials: multi-round-reviewed PRs introducing `expect(await locator).toBeFocused()` (assertion Promise never awaited) and `await locator.isVisible()` (boolean discarded). If a pattern looks like a P0 but exists in a recently-merged PR, that is NOT evidence it's intentional — reviewer culture has blind spots, especially for `await` placement.

2. **"Replace, don't annotate" is the dominant maintainer fix style.** Multiple repos (one Cypress UI builder, one note-taking app, one workflow engine, one form-builder) have merged "flaky test fix" PRs that DELETE `{ timeout: 0 }`, `waitForTimeout`, and `force:true` rather than wrap them with `// JUSTIFIED:`. If a repo has 0 existing `// JUSTIFIED:` comments and many anti-pattern hits, do NOT introduce the convention unilaterally — direct replacement matches house style better.

3. **Within-file idiom symmetry > Playwright-canonical fix.** When a dangling locator (#8a) has two valid fixes (`.waitFor()` vs `await expect(...).toBeVisible()`), prefer whichever the maintainers used for the **parallel/adjacent test in the same file** even if the other is more canonical per Playwright docs. Aesthetic symmetry within a file is what reviewers compare against. Search the same file (and sibling specs in the same test suite) for the closest precedent before choosing.

4. **`page.url()` as a read (not assertion) is fine.** `const originalUrl = page.url();` followed later by `await expect(page).not.toHaveURL(originalUrl)` is the canonical baseline-then-assert pattern. Phase 2 should distinguish `expect(page.url()).X()` (anti-pattern) from bare `page.url()` reads.

5. **CI execution check (do this before claiming "silent CI disaster").** Before framing a finding as a CI-impacting silent-pass, verify the spec is actually executed in CI. Read `.github/workflows/*.yml` (or `.gitlab-ci.yml`, `.circleci/`, etc.) and find which job runs the affected file. Also check `playwright.config.ts` for `testIgnore`, `testMatch`, or project filters that might exclude it. If the spec is NOT in CI, downgrade the finding from "CI gate broken" to "developer experience defect" — both worth fixing, but the PR narrative differs. (Real case: a federation spec with `test.describe.only` had been on master 2.5 years, but the federation Playwright suite was `testIgnore`'d from CI — local dev impact only, not CI impact.)

6. **Match the codebase's EXACT canonical form. Do not invent variants.** When the SKILL.md 4.1 table prescribes a fix (e.g., `expect(page.url()).toContain(x)` → `await expect.poll(() => page.url()).toContain(x)`), use that exact shape unless you observe the codebase using something equivalent. Inventing new forms (e.g., `await expect(page).toHaveURL((url) => url.toString().includes(x))`) — even when they're valid Playwright — creates idiom drift that reviewers will push back on. Before introducing any form not already present in the file, count its usage in the repo: if zero existing callsites use it, prefer the form the codebase already uses. (Real case: a repo had 5 existing `expect.poll(() => page.url()).toContain(x)` callsites; a fix-PR introduced 8 callback-form `toHaveURL((url) => url.includes(x))` conversions — functionally correct, stylistically out of step.)

7. **PR scope: one mental migration per PR, not one anti-pattern ID.** Group fixes by the umbrella concept reviewers will see, not by the skill's pattern numbers:

- **OK as one PR**: 18 fixes spanning `#4` (`.all().toHaveLength` → `.toHaveCount`) + `#15` (missing await) + `#8b` (discarded boolean → web-first) + `#16` (missing await on action). All under the umbrella "migrate this file family to web-first matchers" — reviewers see ONE coherent move.
- **SPLIT into separate PRs**: `#4h` URL migration + `#4b` `toBeAttached` cleanup + `#4a` vacuous `>=0` removal + Vitest unit-test `>=0` fix. These are 4 DIFFERENT mental migrations that happen to all be valid P0; bundling them risks partial reverts where each reviewer disagrees with one umbrella.

Heuristic: if you can describe the PR in one phrase that captures all changes ("migrate to web-first matchers", "remove vacuous toBeAttached"), one PR is fine. If you need "and also" / "plus" / "while we're at it" to describe the scope, split it.

8. **Verify PR attribution before claiming "follow-up to #X".** Before writing "follow-up to #15498" in a PR body, read #15498's full diff (`gh pr diff 15498`) and confirm: (a) it actually touched the same pattern, (b) it touched files in the same area, (c) the author/reviewers signal openness to similar follow-ups. Misattributing a maintainer's intent in a PR body invites the response "that's not what we did" — which kills momentum. If you can't find a clean precedent, frame as standalone: "this PR migrates X anti-pattern across Y files" — no false-citation needed.

#### Mandatory pre-removal procedures (LOW does not mean "skip the check")

Even for LOW-rated band-aids, run these checks BEFORE removing. The check is mechanical and fast — skipping it has caused recurring mistakes (see anti-example below).

**Procedure 1: `force: true` after readiness check**

Before removing `{ force: true }` from `X.click({ force: true })` preceded by `Y.should("be.visible")` (Cypress) or `await expect(Y).toBeVisible()` (Playwright):

1. Extract the click TARGET selector (X) and visibility check SUBJECT selector (Y)
2. Confirm X === Y, OR Y is a child container that DEFINITELY guarantees X's actionability
3. If X is a different element from Y (e.g., Y is a parent scene title, X is a button inside), the visibility check does NOT cover force's purpose — KEEP force, mark JUSTIFIED with "{ force: true } needed: visibility check on parent ${Y}, not on click target ${X}"

**Anti-example (real case from a SQL editor scene in a large analytics product)**:

```ts
// WRONG to remove force here:
await expect(page.locator('.scene-name h1 span').getByText(uniqueViewName)).toBeVisible({ timeout: 60000 })
// ... 5 lines of unrelated steps ...
await page.getByTestId('sql-editor-materialization-button').click({ force: true })
//                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
//                  click target ≠ visibility check subject
//                  visibility was on '.scene-name h1 span' (page header)
//                  click is on '[data-testid="sql-editor-materialization-button"]' (button)
//                  REMOVING force here can re-expose timing race during materialization
```

This is a recurring mistake: agents frequently re-introduce the same regression even when prior context warns against it. The grep procedure above is the formal guard.

For other band-aids (`waitForTimeout`, `#5a` conditional `if (isVisible())`), the 4.2 band-aid table + 4.3 cascade cleanup rule + Phase 2 LLM context-reading are sufficient guards — no separate pre-removal procedure is needed. The 13-repo OSS trial showed agents reliably distinguish "conditional gating an action vs gating an assertion" via Phase 2 alone, and `git blame` on `waitForTimeout` produces too many false signals (generic commit messages on intentional pacing patterns).

### 4.3 Cascade cleanups (look up after a #4h or web-first fix)

After applying `#4h` `expect.poll`/`toHaveURL` or any `#4c-4e`/`#15` web-first replacement, the line(s) **immediately above** the new assertion may now be vestigial. Specifically check for:

- `await page.waitForTimeout(N)` — frequently added defensively to make a one-shot assertion pass; once the new assertion auto-retries, the timeout is dead weight
- `await page.waitForLoadState('networkidle')` — same logic; web-first matchers usually subsume this
- `await page.waitForLoadState('domcontentloaded')` — sometimes also redundant if assertion polls

**Remove ONLY when ALL of the following hold:**
1. The new web-first assertion clearly handles the wait the timeout was for (e.g., `expect.poll(() => page.url())` waits for URL change)
2. There's NO other assertion or action between the timeout and the now-fixed assertion that depended on the wait
3. The timeout is within ~3 lines of the fix (further away → likely waiting for something else)

**If unsure**, leave the timeout and add `// TODO: verify still needed after expect.poll above` comment. Don't speculatively remove.

This rule is OBSERVATION-BASED (in an OSS Playwright suite, removing `waitForTimeout(1000)` between `goto` and the new `expect.poll(() => page.url())` was clean). It is also a partial test of 4.2 — the timeout MAY have been a band-aid; removing it tests whether the new web-first form covers the same case. If the test breaks in CI, the original timeout was load-bearing for a deeper flake — investigate root cause per 4.2.

### 4.4 How many cycles? (empirical recommendation)

A "cycle" = (1) run scanner, (2) apply canonical fixes from 4.1 to flagged hits, (3) re-scan. Empirically validated against a 13-repo OSS trial across Playwright and Cypress suites (see project `results/` directory for raw data):

| Cycles | Cumulative P0 fixed | Marginal % |
|--------|---------------------|------------|
| 1 | 48% | — |
| 2 | 97% | +49% |
| 3 | 100% | **+3%** ⬇ (elbow) |

**Default: 2 cycles.** This captures 97% of fixable P0 hits.

**Why not 1 comprehensive cycle?** A follow-up trial tested single-cycle-comprehensive on 2 successful repos:

| Repo | Multi-cycle (3 thematic) | Single comprehensive | Gap | Effective |
|------|------|------|------|------|
| Repo A (large Playwright monorepo) | 22 P0 | 24 P0 | +2 | 91% |
| Repo B (large multi-product monorepo) | 148 P0 | 151 P0 | +3 | 98% |

**Outcome equivalence validated** — single comprehensive cycle reaches within 2-3% of multi-cycle final. The 3% residual is the SAME band-aid / Phase-2-LLM-territory hits that multi-cycle also leaves.

**Why default to multi-cycle anyway?** Operational reasons:
1. **Each cycle is bounded scope** — easier to checkpoint, recover from agent timeout, verify intermediate state
2. **Reviewer clarity** — thematic cycles in the SUMMARY ("Cycle 1: bulk #4c-4e, Cycle 2: federation perl, Cycle 3: JUSTIFIED") read better than a single dump
3. **Agent execution budget** — single-cycle runs on the two large monorepos in the trial took 17 min and ~25 min wall time respectively; long-running agents risk watchdog timeouts. Multi-cycle splits this naturally.

If you can guarantee per-cycle execution under ~5 min and don't need thematic SUMMARY structure, single-comprehensive is correct. Otherwise multi-cycle is safer.

**Single cycle suffices** for ~70% of repos in the trial — those with:
- Small actionable surface (< 30 P0 hits)
- Patterns covered by single-pass sed transforms
- No multi-line patterns or regex variants
- Per-cycle execution can complete within reasonable wall time (< 5 min)

**Add a 2nd cycle** when:
- Repo has multi-line patterns your sed implementation can't span (BSD/macOS sed lacks multi-line; GNU/Linux sed has `-z` for null-separated input). Use `perl -i -0pe` for portability in cycle 2.
- Multiple regex variants of the same anti-pattern (e.g., `expect(await x.method())` for `isVisible`/`isDisabled`/`textContent`/`inputValue` plus chained variants — sed needs a 2nd pass to catch chained forms)
- You want thematic organization for clarity in the SUMMARY (e.g., cycle 1 = bulk #4c-4e, cycle 2 = #4h, cycle 3 = JUSTIFIED comments)

**Add a 3rd cycle** ONLY when:
- The 2nd cycle's scanner output STILL shows actionable hits the canonical table covers
- Cascade cleanups from 4.3 emerged after the 2nd cycle's web-first replacements
- Marginal gain in cycle 2 was > 10% (signals there might be more in cycle 3)

**Do NOT add cycles past 5% marginal gain.** That's diminishing returns. For residual hits, file an issue against the upstream repo or add `// JUSTIFIED:` comments — don't manufacture cycles.

**Quick decision flowchart**:
```
After cycle N scan:
  If iter-N P0 == iter-N-1 P0       → STOP (converged)
  If marginal fix < 5% of total     → STOP (diminishing returns)
  If pattern still actionable AND <5% marginal → STOP, document residual
  Otherwise                          → run cycle N+1
```

### 4.5 Avoid Scope Creep

When fixing a flagged anti-pattern, do ONLY the fix:
- Don't add new logging (`console.warn`) where there was none
- Don't speculatively remove `waitForTimeout` calls that aren't directly tied to the assertion you're fixing
- Don't reformat surrounding code
- If the fix exposes related issues, note them in the report — don't cascade

The scanner is the source of truth for what to change. If the line isn't flagged, leave it alone.

**Budget interpretation**: When a dispatch prompt caps you at N fixes, **N counts distinct patterns / instance-clusters, not raw lines**. One bug repeated 45 times across a single file (or a few files in the same test family) is ONE finding — fix the whole cluster. Five raw lines distributed across five unrelated bugs is FIVE findings. The cap exists to prevent unfocused exploration, not to leave silent-pass bugs in place when one mechanical pattern resolves them all.

Examples:
- ✅ ONE finding: 45× `expect(await locator).toBeFocused()` across 4 accessibility specs in the same suite → fix all 45 lines as one batch.
- ✅ FIVE findings: one #4h, one #16, one #8b, one #7, one #4c-4e across five different files → at the cap.
- ❌ Over-fix: cluster of 200+ `#4c-4e textContent → toHaveText` across an entire repo when the budget is 5. That's a codemod scope, not a surgical pass — flag in the report and request codemod authority before bulk applying.

---

## Pattern Reference

Detailed specification for the 19 anti-patterns that Phase 1, Phase 2, and Phase 2.5 execute. Do **not** re-run these checks as a separate pass — the phases above already cover them. When emitting a finding, consult the matching section here for the canonical Symptom / Rule / Fix wording. Grouped by severity: P0 items are silent always-pass bugs, P1 items waste CI time or mislead developers, P2 items are maintenance concerns.

**Important:** `test.skip()` with a reason comment or reason string is intentional — do NOT flag or remove these. Only flag assertions gated behind a runtime `if` check that cause the test to pass silently (see #5a).

---

### P0 — Must Fix (silent always-pass)

Tests pass when the feature is broken. No real verification is happening. Always check these.

#### 1. Name-Assertion Alignment `[LLM-only]`

**Symptom:** Test name promises something the assertions don't verify.

```typescript
// BAD — name says "status" but only checks visibility
test('should display user status', async ({ page }) => {
  await expect(status).toBeVisible();  // no status content check
});
```

**Rule:** Every noun in the test name must have a corresponding assertion. Add it or rename.

**Procedure:**
1. Extract all nouns from the test name (e.g., "should display user **status**")
2. For each noun, search the test body for `expect()` that verifies it
3. Missing noun → add assertion or remove noun from name

**Common patterns:** "should display X" with only `toBeVisible()` (no content check), "should update X and Y" with assertion for X but not Y, "should validate form" with only happy-path assertion.

#### 2. Missing Then `[LLM-only]`

**Symptom:** Test acts but doesn't verify the final expected state.

```typescript
// BAD — toggles but doesn't verify the dismissed state
test('should cancel edit on Escape', async ({ page }) => {
  await input.click();
  await page.keyboard.press('Escape');
  await expect(text).toBeVisible();
  // input still hidden?
});
```

**Rule:** For toggle/cancel/close actions, verify both the restored state AND the dismissed state.

**Procedure:**
1. Identify the action verb (toggle, cancel, close, delete, submit, undo)
2. List the expected state changes (element appears/disappears, text changes, count changes)
3. Check that BOTH sides of the state change are asserted

**Common patterns:** Cancel/Escape without verifying input is hidden, delete without verifying count decreased, submit without verifying form resets, tab switch without verifying previous tab content is hidden.

#### 3. Error Swallowing `[grep-detectable + LLM]`

**Symptom (POM — grep):** `.catch(() => {})` or `.catch(() => false)` on awaited operations — caller never sees the failure.

**Symptom (spec — LLM):** `try/catch` wrapping assertions — test passes on error instead of failing.

```typescript
// BAD POM — caller thinks execution succeeded
await loadingSpinner.waitFor({ state: 'detached' }).catch(() => {});

// BAD spec — silent pass on assertion failure
try { await expect(header).toBeVisible(); }
catch { console.log('skipped'); }
```

**Rule (POM):** Remove `.catch(() => {})` / `.catch(() => false)` from wait/assertion methods. If the operation can legitimately fail, the caller should decide how to handle it. Only keep catch for UI stabilization like `input.click({ force: true }).catch(() => textarea.focus())`.

**Rule (spec):** Never wrap assertions in `try/catch`. Use `test.skip()` in `beforeEach` if the test can't run. `try/catch` in non-assertion code (setup, teardown, optional cleanup) is fine — LLM must read context before flagging.

#### 3b. Cypress `uncaught:exception` Suppression `[grep-detectable, Cypress only]`

**Symptom:** `cy.on('uncaught:exception', () => false)` globally suppresses all unhandled app errors, hiding real bugs.

```javascript
// BAD — blanket suppression
Cypress.on('uncaught:exception', () => false);

// BETTER — scoped to a specific known error
Cypress.on('uncaught:exception', (err) => {
  if (err.message.includes('ResizeObserver loop')) return false;
  throw err;
});
```

**Rule:** Blanket `() => false` is P0 — equivalent to `.catch(() => {})`. Two patterns are NOT P0 and should be skipped in Phase 2:

1. **Scoped handlers** that filter specific known errors and re-throw others — acceptable with `// JUSTIFIED:`.
2. **Scoped negative-regression test** — `cy.on('uncaught:exception', (err) => { expect(err.message.includes('X')).to.be.false; });` — the handler is **asserting on the error properties**, not swallowing the error. The test deliberately runs scenarios that historically threw and verifies they no longer do. Phase 2 distinction: does the handler contain an `expect(...)` call? If yes, it's a test assertion, not suppression — NOT P0.

#### 4. Always-Passing Assertions `[grep-detectable + LLM confirmation]`

**Symptom:** Assertion that can never fail.

```typescript
// BAD — count >= 0 is always true
expect(count).toBeGreaterThanOrEqual(0);

// BAD — element always present in DOM; assertion never fails
await expect(page.locator('header')).toBeAttached();

// BAD — one-shot boolean, no auto-retry
expect(await el.isVisible()).toBe(true);
expect(await el.textContent()).toBe('expected text');
expect(await el.getAttribute('attr')).toBe('value');

// BAD — Locator is always a truthy JS object regardless of element existence
expect(page.locator('.selector')).toBeTruthy();

// BAD — disables auto-retry entirely
await expect(el).toHaveCount(0, { timeout: 0 });
```

**Rule:** `toBeAttached()` on an unconditionally rendered element (always in the static HTML shell) is vacuous → P0. The only legitimate use is asserting that an element exists in the DOM but is CSS-hidden (`visibility:hidden`, not `display:none`) — add `// JUSTIFIED: visibility:hidden` in that case.

**Fix:**
- `toBeGreaterThanOrEqual(0)` → `toBeGreaterThan(0)`
- `toBeAttached()` → `toBeVisible()`, or remove if other assertions cover the element
- `expect(await el.isVisible()).toBe(true)` → `await expect(el).toBeVisible()`
- `expect(await el.textContent()).toBe(x)` → `await expect(el).toHaveText(x)`
- `expect(await el.getAttribute('x')).toBe(y)` → `await expect(el).toHaveAttribute('x', y)`
- `expect(locator).toBeTruthy()` → `await expect(locator).toBeVisible()`
- `{ timeout: 0 }` on assertions → remove unless preceded by an explicit wait; add `// JUSTIFIED:` if intentional
- `expect(page.url()).toContain(x)` → `await expect(page).toHaveURL(x)` (one-shot URL read with no retry)
- **Multiple `expect(page.url()).toContain(...)` in sequence** → replace each call with its **own** `await expect(page).toHaveURL(/.../) `. Do NOT combine them into a single regex with `.*` (e.g., `toHaveURL(/A.*B/)`) — that adds an ordering constraint not present in the original substring checks.
- **Compound boolean expression** like `expect(visible1 || visible2).toBe(true)` is the same one-shot anti-pattern as `expect(await el.isVisible()).toBe(true)`. Prefer a locator-level web-first assertion such as `await expect(page.locator('.a, .b')).toBeVisible()`. If both branches require independent assertions (e.g., different post-actions per branch), gate the test with `test.skip()` on the unsupported branch rather than collapsing into a single boolean check.

#### 5. Bypass Patterns `[grep-detectable]` (5a P0, 5b P1)

Two sub-patterns that suppress what the framework would normally catch — making tests pass when they should fail. Listed under P0 because 5a is a silent-pass bug; 5b is a P1 actionability issue documented in the same section for proximity.

**5a. Conditional assertion bypass** — `expect()` gated behind a runtime `if` check. If the condition is false, no assertion runs and the test passes vacuously.

```typescript
// BAD — if spinner never appears, assertion never runs
if (await spinner.isVisible()) {
  await expect(spinner).toBeHidden({ timeout: 5000 });
}
```

**Rule:** Every test path must contain at least one unconditional `expect()`. Move environment- or feature-flag checks to `beforeEach` / declaration-level `test.skip()` so the test is skipped entirely rather than passing silently.

**5b. Force true bypass** — `{ force: true }` skips actionability checks (visibility, enabled state, pointer-events), hiding real UX problems that real users would encounter.

**Rule:** Each `{ force: true }` must have `// JUSTIFIED:` on the line above explaining why the element is not normally actionable. Without a comment, flag P1.

#### 7. Focused Test Leak (`test.only` / `it.only`) `[grep-detectable]`

**Symptom:** A `.only` modifier left in committed code. Severity depends on whether the file has other tests that get silently skipped.

```typescript
// CRITICAL SILENT-SKIP — file has multiple tests; the others never run
test.only('should show user profile', async ({ page }) => { ... });
test('should show settings', ...);   // ← never runs in CI

// SMELL ONLY (no behavior change) — file has only one test, so .only skips nothing
test.only('the only test in this file', ...);
```

**Severity tiers** (LLM check during Phase 2):

| Tier | Condition | Severity | Rationale |
|------|-----------|----------|-----------|
| P0 (CRITICAL) | The same file has ≥2 `it`/`test`/`describe` declarations | P0 — silent CI disaster | The non-focused tests never execute; CI passes anyway |
| P1 (smell) | The `.only` is the file's only `it`/`test` | P1 — debug leak | Behavior unchanged at file level; still a debug artifact that should be removed for cleanliness. If anyone ADDS a second test to this file, it will silently skip — the leak becomes load-bearing. |

**Rule** (Playwright & Cypress best practices): `.only` is a development-time focus tool. It must never be committed regardless of tier. Search `.spec.*/.test.*/.cy.*` for `\.(only)\(` — Phase 1 flags every hit; Phase 2 LLM downgrades singletons to P1.

**Fix:** Delete the `.only` modifier. If the test is intentionally isolated, use `test.skip()` with a reason on the others, or run a single file via the CLI (`--grep` / `--spec`). For P1 (singleton), the fix is mechanical — no behavior change. For P0, fix immediately and audit CI history for skipped runs.

No `// JUSTIFIED:` exemption exists for either tier — there are no legitimate committed uses.

#### 8. Missing Assertion `[grep-detectable]`

Two sub-patterns where no assertion ever occurs — the test executes code but verifies nothing.

**8a. Dangling locator** `[Playwright grep / Cypress LLM]` — a locator created as a standalone statement, not assigned to a variable, not passed to `expect()`, and not chained with an action. The statement is a complete no-op.

```typescript
// BAD — locator created and immediately discarded
await page.locator('.selector');
page.getByRole('button'); // also bad — not even awaited
```

**8b. Boolean result discarded** — `isVisible()` / `isEnabled()` / `isChecked()` / `isDisabled()` / `isEditable()` awaited as a standalone statement. The boolean resolves and is thrown away.

```typescript
// BAD — boolean computed but never checked; asserts nothing
await el.isVisible();
await el.isEnabled();
```

**Rule:** Every locator expression and every boolean state call must either feed into `expect()`, be assigned and used later, or be chained with an action. Standalone expressions are always bugs.

**Fix:** Replace with web-first assertion — `await expect(locator).toBeVisible()` / `toBeEnabled()` etc. These also auto-retry. Or delete the line if it's leftover debug code.

#### 12. Missing Auth Setup `[LLM-only]`

**Symptom:** Spec navigates to protected routes (`/dashboard`, `/settings`, `/admin`, `/account`, etc.) without any preceding login action, `storageState` configuration, or authentication `beforeEach` hook.

**Why it matters:** Tests hit a login redirect instead of the intended page, making all assertions vacuous — they verify the login page, not the feature under test.

**Rule:** Every spec that navigates to a route requiring authentication must either: (a) perform login in `beforeEach`, (b) use `storageState` from Playwright config, or (c) use a custom auth fixture. Flag P0 if no auth mechanism is visible.

#### 15. Missing `await` on `expect()` `[grep-detectable]`

**Symptom:** `expect(locator).toBeVisible()` without `await` — the expression returns a Promise that is never awaited. The test moves on immediately and the assertion never actually runs.

```typescript
// BAD — Promise returned but never awaited; test always passes
expect(page.locator('.toast')).toBeVisible();

// GOOD
await expect(page.locator('.toast')).toBeVisible();
```

**Why it matters:** This is a silent P0. The test compiles and runs green, but zero verification happens. Extremely common mistake, especially when converting from non-async test frameworks.

**Rule:** Every `expect()` on a Playwright Locator must be `await`ed. Grep flags lines starting with `expect(` — confirm in Phase 2 that the line lacks `await` and involves a Locator (non-Locator expects like `expect(count).toBe(3)` don't need `await`). Flag P0.

#### 16. Missing `await` on Playwright Actions `[grep-detectable]`

**Symptom:** `page.locator(...).click()` without `await` — the action is fired but never awaited. It may not execute at all, or execute out of order.

```typescript
// BAD — click may never complete before next line runs
page.locator('#submit').click();

// GOOD
await page.locator('#submit').click();
```

**Why it matters:** Silent no-op. The test passes because it never waits for the action. Subsequent assertions may run against stale page state.

**Rule:** Every Playwright action (`.click()`, `.fill()`, `.type()`, `.press()`, `.check()`, `.selectOption()`, `.setInputFiles()`, `.hover()`, `.focus()`, `.blur()`) must be `await`ed. Flag P0.

---

### P1 — Should Fix (poor diagnostics / wastes CI time)

Tests work but mislead developers, waste CI time, or set up future regressions. Check on every review.

#### 6. Raw DOM Queries (Bypassing Framework API) `[grep-detectable]`

**Symptom:** Test or POM uses `document.querySelector*` / `document.getElementById` inside `evaluate()` or `waitForFunction()` when the framework's element API could do the same job. Check both spec files and POM files — raw DOM in a POM helper is equally harmful since it bypasses the same auto-wait guarantees.

**Why it matters:** No auto-waiting, no retry, boolean trap, framework error messages lost.

```typescript
// BAD
await page.waitForFunction(() => document.querySelectorAll('.item').length > 0);
const has = await page.evaluate(() => !!document.querySelector('.result'));

// GOOD
await page.locator('.item').waitFor({ state: 'attached' });
await expect(page.locator('.result')).toBeVisible();
```

**Rule:** Use the framework's element API instead of raw DOM:
- **Playwright:** `locator.waitFor({ state: 'attached' })` replaces `waitForFunction(() => querySelector(...) !== null)`; `page.locator()` + web-first assertions replaces `evaluate(() => querySelector(...))`
- **Cypress:** `cy.get()` / `cy.find()` — avoid `cy.window().then(win => win.document.querySelector(...))`

Only use `evaluate`/`waitForFunction` when the framework API genuinely can't express the condition: multi-condition AND/OR logic, `getComputedStyle`, `children.length`, cross-element DOM relationships, or `body.textContent` checks. Add `// JUSTIFIED:` explaining why.

#### 9. Hard-coded Sleeps `[grep-detectable]`

**Symptom:** Explicit sleep calls pause execution for a fixed duration instead of waiting for a condition.

```typescript
// BAD — arbitrary delay; still races if render takes longer
await page.waitForTimeout(2000);
cy.wait(1000);

// GOOD — wait for condition
await expect(modal).toBeVisible();
cy.get('[data-testid="modal"]').should('be.visible');
```

**Rule:** Never use explicit sleep (`waitForTimeout` / `cy.wait(ms)`) — rely on framework auto-wait or condition-based waits.

Note: `timeout` option values in `waitFor({ timeout: N })` or `toBeVisible({ timeout: N })` are NOT flagged — these are bounds, not sleeps.

#### 10. Flaky Test Patterns `[LLM-only + grep]`

Two sub-patterns that cause tests to fail intermittently in CI or parallel runs.

**10a. Positional selectors** — `nth()`, `first()`, `last()` without a comment break when DOM order changes.

```typescript
// BAD — breaks if DOM order changes
await expect(items.nth(2)).toContainText('expected text');
```

**Rule:** Prefer `data-testid`, role-based, or attribute selectors. If `nth()` is unavoidable, add `// JUSTIFIED:` explaining why.

**Exemptions (no `// JUSTIFIED:` needed):**
- **Method-name self-documents intent** — when the enclosing method's name explicitly conveys positional access (e.g., `getParagraphByIndex(index) { return this.paragraphs.nth(index); }`, `nthRowOf(...)`, `firstResult()`). The name documents the intent.
- **Fallback selector loops** — `.first()` inside `for (const selector of fallbackSelectors) { … this.page.locator(selector).first() … }`. Here `.first()` means "any match for this candidate selector", not "the first of multiple known elements".
- **Single-result `toHaveCount(1)` adjacent** — `await expect(items).toHaveCount(1); const only = items.first();` (the count assertion documents that exactly one element exists).

**Selector priority** (best → worst, per [Playwright docs](https://playwright.dev/docs/best-practices#use-locators)): `getByRole` → `getByLabel` → `getByTestId`/`data-cy` → `getByText` → attribute (`[name]`, `[id]`) → class → generic. Class and generic selectors are "Never" — coupled to CSS and DOM structure.

**10b. Serial test ordering** `[Playwright only]` — `test.describe.serial()` makes tests order-dependent: a single failure cascades to all subsequent tests, and the suite can't be sharded.

**Rule:** Replace serial suites with self-contained tests using `beforeEach` for shared setup. If sequential flow is genuinely required, use a single test with `test.step()` blocks. If serial is unavoidable, add `// JUSTIFIED:` on the line above `test.describe.serial(`.

#### 13. Inconsistent POM Usage `[LLM-only]`

**Symptom:** A POM class is imported and used for some actions, but the spec also uses raw `page.fill()` / `page.click()` for operations the POM should encapsulate.

**Why it matters:** Defeats the purpose of the POM pattern — when the UI changes, you must update both the POM and the spec. DRY principle violated.

**Rule:** If a POM exists for a page, all interactions with that page should go through the POM. Flag P1 if spec bypasses POM with raw `page.*` calls for actions the POM should own. Suggest adding missing methods to the POM.

#### 14. Hardcoded Credentials `[grep-detectable]`

**Symptom:** String literals used as usernames, passwords, or API keys directly in test code.

```typescript
// BAD — credentials as string literals
await loginPage.login('admin', 'password123');
await page.fill('#password', 'secret');
```

**Why it matters:** Security risk if repo is public, couples tests to specific credentials, prevents running tests against different environments.

**Rule:** Use environment variables (`process.env.TEST_USER`), Playwright config secrets, or test data fixtures. Flag P1.

**Scope — only flag actual credentials, not input test data:**
- **Flag** literals passed to authentication operations: `loginPage.login('admin', 'password')`, `page.locator('#password').fill('realPassword') ` followed by submit, API calls posting credentials, fixtures named `validUser` / `testAdmin`.
- **Do NOT flag** literals used only to verify form input behavior (no auth attempt follows): `passwordInput.fill('anyText'); await expect(passwordInput).toHaveValue('anyText');` — this is input-acceptance testing, not credential storage. Intentional invalid-creds fixtures like `INVALID_USER = { username: 'wronguser', password: 'wrongpass' }` are also fine because they document a negative-path scenario.

When grep flags a literal, read 2–3 lines below to confirm a login/auth call follows. If none, skip.

#### 17. Direct `page.click(selector)` API `[grep-detectable, Playwright only]`

**Symptom:** Using `page.click('#button')` or `page.fill('#input', 'text')` instead of the locator-based API.

```typescript
// BAD — direct page action
await page.click('#submit');
await page.fill('#email', 'user@test.com');

// GOOD — locator-based, auto-wait, better errors
await page.locator('#submit').click();
await page.locator('#email').fill('user@test.com');
```

**Why it matters:** `page.click(selector)` skips the Locator layer, losing locator composition and producing worse review/error context. Playwright docs recommend locator-based actions.

**Rule:** Flag P1. Suggest migrating to `page.locator(selector).action()`.

#### 18. `expect.soft()` Overuse `[grep-detectable + LLM]`

**Symptom:** Most or all assertions in a test use `expect.soft()`, so the test continues past failures and may mask cascading issues — functionally equivalent to error swallowing.

```typescript
// BAD — all assertions are soft; test never fails early
test('should display profile', async ({ page }) => {
  await expect.soft(page.locator('.name')).toBeVisible();
  await expect.soft(page.locator('.email')).toBeVisible();
  await expect.soft(page.locator('.avatar')).toBeVisible();
});

// GOOD — one hard assertion gates, soft assertions for independent checks
test('should display profile', async ({ page }) => {
  await expect(page.locator('.profile')).toBeVisible();          // hard gate
  await expect.soft(page.locator('.name')).toHaveText('Alice');  // independent detail
  await expect.soft(page.locator('.email')).toHaveText('a@b.c'); // independent detail
});
```

**Rule:** `expect.soft()` is fine for independent, non-critical checks alongside hard assertions. Flag P1 when >50% of assertions in a single test are `soft` — the test likely needs at least one hard assertion to gate on the primary condition.

---

### P2 — Nice to Fix (maintenance / robustness)

Weak but not wrong. Address when refactoring or before adopting wider conventions.

#### 11. YAGNI + Zombie Specs `[LLM-only]`

Two sub-patterns: unused code in Page Objects, and zombie spec files.

**11a. YAGNI in Page Objects** — POM has locators or methods never referenced by any spec. Or a POM class extends a parent with zero additional members (empty wrapper class).

**Procedure:**
1. List all public members of each changed POM file
2. Grep each member across all test files and other POMs
3. Classify: USED / INTERNAL-ONLY (`private`) / UNUSED (delete)
4. Check if any POM class has zero members beyond what it inherits — empty wrappers add no value unless the convention is intentional

**Common patterns:** Convenience wrappers (`clickEdit()` when specs use `editButton.click()`), getter methods (`getCount()` when specs use `toHaveCount()`), state checkers (`isVisible()` when specs assert on locators directly), pre-built "just in case" locators, empty subclass created for future expansion.

**Single-use Util wrappers** — a separate `*Util` / `*Helper` class whose methods are each called from only one test. These add indirection with no reuse benefit; inline them. Keep a Util method only if called from **2+ tests** or invoked **2+ times** within one test.

**Rule:** Delete unused members. Make internal-only members `private`. Apply the 2+ threshold before creating or keeping Util methods — if a helper is called from only one place, inline it. Flag empty wrapper classes for review — they may be intentional convention or dead code.

**11b. Zombie spec files** — An entire spec file whose tests are all subsets of tests in another spec file covering the same feature. The file adds no coverage that isn't already verified elsewhere.

**Procedure:** After reviewing all files in scope, cross-check spec files with similar names or feature coverage. If every test in file A is a subset of a test in file B, flag file A for deletion.

**Common patterns:** `feature-basic.spec.ts` where every case also appears in `feature-full.spec.ts`; a 1–2 test file created as a "quick smoke" that was never expanded while a comprehensive suite grew alongside it.

**Rule:** Delete the zombie file. If any test in it is not covered elsewhere, migrate it to the comprehensive suite first.

**Output:**
```
| File | Member | Used In | Status |
|------|--------|---------|--------|
| modal-page.ts | openModal() | (none) | DELETE |
| modal-page.ts | closeButton | internal only | PRIVATE |
| search-page.ts | (class body empty) | — | REVIEW |
| basic.spec.ts | (entire file) | covered by full.spec.ts | DELETE |
```

---

## Output Format

Present findings grouped by severity:

```markdown
## [P0/P1/P2] [filename] — [issue type]

### `[test name or POM method]`
- **Issue:** [description]
- **Fix:** [name change / assertion addition / merge / deletion]
- **Code:**
  ```typescript
  // concrete code to add or change
  ```
```

**After all findings, append a summary table and top priorities:**

```markdown
## Review Summary

| Sev | Count | Top Issue | Affected Files |
|-----|-------|-----------|----------------|
| P0  | 3     | Missing Then | auth.spec.ts, form.spec.ts |
| P1  | 5     | Flaky Selectors | settings.spec.ts |
| P2  | 2     | Hard-coded Sleeps | dashboard.spec.ts |

**Total: 10 issues across 4 files.**

### Top 3 Priorities
1. **Remove `test.only`** in auth.spec.ts — CI is running only 1 of 6 tests
2. **Remove try/catch** around assertion in settings.spec.ts — test can never fail
3. **Add assertions** to 4 tests with zero verification (redirect, export, toggle, notification)
```

The "Top N Priorities" section should list the 3-5 highest-impact fixes in concrete, actionable terms. This helps developers know where to start without scanning all P0 findings.

**Severity classification:**
- **P0 (Must fix):** Test silently passes when the feature is broken — no real verification happening
- **P1 (Should fix):** Test works but gives poor diagnostics, wastes CI time, or misleads developers
- **P2 (Nice to fix):** Weak but not wrong — maintenance and robustness improvements

## Quick Reference

This table is a **numerical index for scanning** — pattern # → severity, phase, and the grep/LLM signal. For canonical **Symptom / Rule / Fix** wording (used when emitting a finding), consult the matching section under "Pattern Reference" above (organized by severity tier, not numerical order). Both views describe the same 19 patterns; pick whichever lookup matches your task.

| # | Check | Sev | Phase | Detection Signal |
|---|-------|-----|-------|-----------------|
| 1 | Name-Assertion | P0 | LLM | Noun in name with no matching `expect()` |
| 2 | Missing Then | P0 | LLM | Action without final state verification |
| 3 | Error Swallowing | P0 | grep+LLM | `.catch(() => {})` in POM (grep); `try/catch` around assertions in spec (LLM) |
| 4 | Always-Passing | P0 | grep+LLM | `>=0`; `toBeAttached()`; one-shot booleans (`isVisible/textContent/getAttribute`); `locator.toBeTruthy()`; `{ timeout: 0 }` on assertions |
| 5 | Bypass Patterns | P0/P1 | grep | `expect()` inside `if`; `force: true` without `// JUSTIFIED:` |
| 6 | Raw DOM Queries | P1 | grep | `document.querySelector` in `evaluate` |
| 7 | Focused Test Leak | P0 | grep | `test.only(`, `it.only(`, `describe.only(` — no `// JUSTIFIED:` exemption |
| 8 | Missing Assertion | P0 | grep | 8a: `page.locator(...)` standalone; 8b: `await el.isVisible();` standalone — nothing ever asserts |
| 9 | Hard-coded Sleeps | P1 | grep | `waitForTimeout()`, `cy.wait(ms)` |
| 10 | Flaky Test Patterns | P1 | LLM+grep | `nth()` without comment; `test.describe.serial()` |
| 11 | YAGNI + Zombie Specs | P2 | LLM | Unused POM member; empty wrapper; single-use Util; zombie spec file |
| 12 | Missing Auth Setup | P0 | LLM | Spec navigates to protected route without login/storageState/auth beforeEach |
| 13 | Inconsistent POM Usage | P1 | LLM | POM imported but spec uses raw `page.fill`/`page.click` for POM-encapsulated actions |
| 14 | Hardcoded Credentials | P1 | grep | String literals as login credentials; use env vars or test fixtures |
| 15 | Missing await on expect | P0 | grep+LLM | `expect(locator).toBeVisible()` without `await` — assertion never runs |
| 16 | Missing await on action | P0 | grep+LLM | `page.locator(...).click()` without `await` — action may never execute |
| 17 | Deprecated page action API | P1 | grep | `page.click(selector)` instead of `page.locator(selector).click()` |
| 18 | `expect.soft()` overuse | P1 | grep+LLM | >50% soft assertions in a test masks cascading failures |
| 3b | Cypress uncaught:exception suppression | P0 | grep | `cy.on('uncaught:exception', () => false)` globally swallows app errors |

---

## Suppression

When a grep-detected pattern is intentional, add `// JUSTIFIED: [reason]` on the **line immediately above** the flagged line. When reviewing grep hits, if the line immediately above contains `// JUSTIFIED:`, skip the hit. Each individual flagged line needs its own `// JUSTIFIED:` — a comment higher up in the block does not count.

**Exception — #7 Focused Test Leak:** `// JUSTIFIED:` does not suppress `.only` hits. There are no legitimate committed uses of `test.only` / `it.only` / `describe.only` — every hit is P0.
