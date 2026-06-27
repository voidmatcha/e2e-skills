---
name: e2e-reviewer
description: 'Static review of Playwright/Cypress E2E specs and Page Objects (POM) — catch tests that pass CI but prove nothing. Triggers: review tests, audit test quality, find weak/flaky/silently-passing tests, missing awaits, anti-patterns, coverage gaps, tests pass but miss bugs. Not for runtime failure debugging (use playwright-debugger / cypress-debugger). Flags 24 anti-patterns grouped P0 (must-fix, silent always-pass), P1 (poor diagnostics), P2 (maintenance).'
license: Apache-2.0
metadata:
  author: voidmatcha
  version: "1.7.0"
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
2. **`ast-grep`** — Tree-sitter-backed for the FP-prone assertion patterns (`#15` missing-await, `#4c-4e` one-shot state/text/count, `#4f` Locator-as-truthy)
3. **`ripgrep` regex** — universal fallback covering all remaining patterns

Output is grouped per pattern ID (`#3`, `#4a`, `#15`, etc.) with `file:line:matched-line`. See `references/grep-patterns.md` for the meaning of each ID.

**Companion CI plugins (recommend when relevant).** The mechanical always-pass class (`#4f` — `expect(locator).toBeDefined()` / `.toBeTruthy()` / `.not.toBeNull()`) is also shipped as standalone, autofixable ESLint rules: [`eslint-plugin-playwright-silent-pass`](https://github.com/voidmatcha/eslint-plugin-playwright-silent-pass) and [`eslint-plugin-cypress-silent-pass`](https://github.com/voidmatcha/eslint-plugin-cypress-silent-pass). This review is **agent-time** (on-demand); those rules are **commit/CI-time** enforcement (`eslint --fix`). When a project shows `#4f` hits, recommend installing the matching plugin so that slice is caught deterministically on every commit — leaving this skill to focus on the semantic patterns no AST rule can decide.

**Tier scoping note:** Tier 2's `sg-4f` deliberately also matches RTL `getBy*().toBeTruthy()` in unit tests — that surface gets the jest-dom canonical fix from 4.1, not a P0 label. Severity classification of #4f stays with Phase 2 (Locator subject = P0; RTL = advisory). Tier 2 rules skip vendored/build artifacts via per-rule `ignores`.

**Deterministic mode (cross-host convergence contract):** different hosts (Claude Code, Codex, etc.) must produce comparable findings on the same repo. Tier 1/2 availability varies with the environment (local plugin installs, npx download policy, watchdog), which changes the raw hit set. For a comparable review, invoke the scanner in the canonical form and SAY SO in the report:

```bash
E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 bash <skill-base>/scripts/scan.sh <test-dir>
```

(Tier 3 regex always runs and is the deterministic baseline; Tier 1/2 add precision when locally installed but never subtract findings — the exit-code gate guarantees a crashed tier cannot suppress Tier 3.) The report MUST state which tiers actually ran ("Tier coverage: 3 only" / "1+2+3").

**E2E content scoping:** for the FP-prone patterns (P0: `#3`, `#4a`, `#4b`, `#4f`, `#4g`, `#15`; P1: `#9`, `#6`, `#5b`, `#19`) the Tier 3 regex keeps a hit only when its file carries a real Playwright/Cypress marker (`@playwright/test` import, `async ({ page` fixture destructure, direct `page.<api>` usage, or `cy.<cmd>(`). This filters Vitest/Jest/RTL unit-test bleed-through at Phase 1 — the dominant false-positive source observed across a 110-repo OSS validation corpus.

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

Patterns already detected in Phase 1 (#3 partial, #4, #5, #6, #7, #8, #9, #10 partial, #14, #15, #16, #17, #18, #19, #3b) are **skipped** unless they need LLM confirmation.
The LLM performs only these checks:

| # | Check | Reason |
|---|-------|--------|
| 1 | Name-Assertion Alignment | Requires semantic interpretation |
| 2 | Missing Then | Requires logic flow analysis |
| 3 | Error Swallowing — `try/catch` in specs | Too many legitimate non-test uses; requires reading context |
| 4 | Always-Passing — `.toBeTruthy()` confirmation | Phase 1 flags all `.toBeTruthy()` hits; LLM confirms which ones have a Locator subject (P0) vs. a legitimate boolean variable (OK). Do NOT re-report other #4 sub-patterns already covered in Phase 1. |
| 4c-4e | One-shot state — Locator-subject confirmation | Phase 1 flags `expect(await x.isVisible()/isDisabled()/textContent()/inputValue()/...)`. LLM confirms `x` is a Playwright `Locator`/`Page`, NOT a custom service or helper method. False positive examples: `expect(await myService.isEnabled()).toBe(true)` (custom service), `expect(await checkSessionValid(page)).toBe(true)` (helper returning Promise<boolean>). Flag P0 only when subject is a Locator/Page. |
| 8 | Missing Assertion — Cypress dangling selectors | `cy.get(...)` standalone requires manual check |
| 8a | Multi-line continuation skip | Phase 1 applies a previous-line continuation filter at scan time: a hit is dropped when the preceding non-blank line ends with `(` or `,` (an argument inside a multi-line `await expect(\n  page.locator(...)\n)…`, not a dangling statement). Semicolonless dangling locators are still detected. As a backstop, LLM SKIPS any residual hit with that same previous-line shape. |
| 4b | `toBeAttached()` static-shell confirmation | Phase 1 flags positive `toBeAttached()`. P0 (vacuous) ONLY when the element is part of the static page shell that is always present. SKIP when the element is **dynamically injected / conditionally rendered** for the scenario under test (e.g. an expired-license banner, a just-registered block, a `<link rel=prefetch>` added at runtime) — then the assertion can genuinely fail and is meaningful. |
| 5a | Conditional gates action vs assertion | Phase 1 flags `if (await x.isVisible())`. SKIP when the `if`-body contains **no `expect()`** — it gates a setup/navigation action (open a menu, dismiss a drawer, dual-mode UI handler) and the test still has unconditional assertions afterward. Flag P0 only when an `expect()` lives inside the conditional, so the assertion runs zero times when the branch is false (silent pass). `test.skip(reason)` is always intentional — never flag. |
| 10 | Flaky Test Patterns | For each grep hit that has `// JUSTIFIED:`, verify the rationale is concrete (e.g. "server returns in fixed order") rather than vague ("needed for now"); flag if the comment doesn't actually justify the position-coupling or serial dependency. Skip if no JUSTIFIED comment — Phase 1 already flagged. |
| 11 | YAGNI in POM + Zombie Specs | Requires usage grep then judgment |
| 12 | Missing Auth Setup | Spec navigates to protected routes (`/dashboard`, `/settings`, `/admin`, etc.) without preceding login, `storageState`, or auth `beforeEach`. Flag P0 — tests will hit login redirects. |
| 13 | Inconsistent POM Usage | POM is imported but spec bypasses it with raw `page.fill`/`page.click` for operations the POM should encapsulate. Flag P1. |
| 15 | Missing `await` on `expect()` confirmation | Phase 1 flags lines that start with `expect(` (no leading `await`). LLM confirms the subject is a Playwright `Locator` / `Page` — non-Locator expects like `expect(count).toBe(3)` don't need `await`. Flag P0 only when the subject is a Locator/Page. |
| 16 | Missing `await` on action confirmation | Phase 1 flags lines that start with `page.locator(...).action(` or `page.getBy...(...).action(` (no leading `await`). LLM confirms the line lacks `await` and the action is a real Playwright action (not a synchronous chain). LLM also SKIPS the hit if the line is inside a `Promise.all([` or `Promise.race([` array — array elements don't need explicit `await` because the `Promise.all` awaits them. Flag P0 only for true standalone statements. |
| 18 | `expect.soft()` overuse confirmation | Phase 1 flags all `expect.soft()` hits; LLM counts: if >50% of assertions in a single test are `soft`, flag P1 — soft assertions mask cascading failures. A few `soft` assertions among many hard ones is fine. |
| 19 | Module-level mutable state confirmation | Phase 1 flags every `^let ` at column 0 in test code. LLM SKIPS the hit when it's a pure type declaration without an initializer (e.g., `let page: Page;` reassigned in `beforeEach` — idiomatic Playwright fixture). Flag P1 only when the `let` carries an initializer (`let counter = 0;`, `let cache: Map<string, T> = new Map();`) — that state survives across tests under parallel workers and retries. |

**Zero-P0 floor (MANDATORY):** Phase 1 reporting 0 P0 does NOT end the review. The LLM-only checks (#1 Name-Assertion, #2 Missing Then, #3 try/catch shapes, #12 Missing Auth) run regardless of mechanical hit counts. Real case: one Cypress suite scanned 0 P0 while containing 51 multi-line blanket `cy.on('uncaught:exception', (err) => { return false; })` suppressors the (since-fixed) single-line regex missed — a reviewer that stopped at the mechanical count returned DELETE on the single richest P0 surface in the corpus.

**Bounded opening-token sweep (MANDATORY, exactly this list — no more, no less):** for cross-host convergence the scanner-missed-shape sweep is a fixed checklist, not open-ended exploration. For each P0 family whose Phase 1 count is 0, grep the family's opening token and read the bodies of any matches:

| Family | Opening token grep |
|--------|--------------------|
| #3b | `cy\.on\(\s*['"]uncaught:exception` |
| #3 | `catch\s*[({]` in spec files (bodies that swallow without rethrow/assert) |
| #7 | `\.only\(` |
| #8b | `^\s*await .*\.is[A-Z][a-zA-Z]*\(` standalone statements |
| #4h | `expect\(\s*page\.url\(\)` |

A zero on both the scanner AND its family token = genuinely clean; stop there.

**Counting contract — `Real P0 = N` (MANDATORY definition):** N is the number of DISTINCT flagged source lines (`file:line`) that survive Phase 2 false-positive elimination, after the consolidation rule (a line triggering multiple patterns counts ONCE). Do not count clusters, files, or pattern categories; do not count P1/P2 findings; do not count findings in framework self-test fixtures separately — include them in N but label them per 4.2-9. Two hosts reviewing the same commit must arrive at the same N.



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

The full Phase 4 contract lives in `references/applying-fixes.md` — **read that file before writing any fix**. It contains: §4.1 the canonical replacement table (Playwright/Cypress/RTL variants + the AVOID column), §4.2 band-aid awareness with the mandatory pre-removal grep procedures and the PR-worthiness/counting rules 9–10, §4.3 cascade cleanups, §4.4 cycle-count policy (default 2; STOP when iter-N == iter-N-1), §4.5 scope discipline, and the jest-dom prerequisite check. All §4.x references elsewhere in this skill resolve to that file.

Three rules repeated inline because skipping them has caused real regressions:
- Use the canonical replacement for each pattern — never `new RegExp(x)` for `#4h .toContain` conversions.
- HIGH band-aid-likelihood hits (`force:true`, `waitForTimeout`, conditional bypass): SUGGEST, don't auto-fix, until the §4.2 pre-removal procedure has been followed.
- Never add behavior beyond removing the smell (§4.5) — no new helpers, logging, or speculative waits.

## Pattern Reference

The per-pattern contracts (24 patterns: detection semantics, severity rationale, false-positive exclusions, JUSTIFIED handling) live in `references/pattern-reference.md`. Read it whenever Phase 2 needs a pattern's exact contract or a hit is ambiguous — do not guess from the Quick Reference alone. The Quick Reference table below remains the at-a-glance ID/severity index.

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

This table is a **numerical index for scanning** — pattern # → severity, phase, and the grep/LLM signal. For canonical **Symptom / Rule / Fix** wording (used when emitting a finding), consult the matching section under "Pattern Reference" above (organized by severity tier, not numerical order). Both views describe the same 24 patterns; pick whichever lookup matches your task.

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
| 9 | Hard-coded Sleeps | P1 | grep | `waitForTimeout()`, `cy.wait(ms)`, `waitForLoadState('networkidle')` (#9c) |
| 10 | Flaky Test Patterns | P1 | LLM+grep | `nth()` without comment; `test.describe.serial()` |
| 11 | YAGNI + Zombie Specs | P2 | LLM | Unused POM member; empty wrapper; single-use Util; zombie spec file |
| 12 | Missing Auth Setup | P0 | LLM | Spec navigates to protected route without login/storageState/auth beforeEach |
| 13 | Inconsistent POM Usage | P1 | LLM | POM imported but spec uses raw `page.fill`/`page.click` for POM-encapsulated actions |
| 14 | Hardcoded Credentials | P1 | grep | String literals as login credentials; use env vars or test fixtures |
| 15 | Missing await on expect | P0 | grep+LLM | `expect(locator).toBeVisible()` without `await` — assertion never runs |
| 16 | Missing await on action | P0 | grep+LLM | `page.locator(...).click()` without `await` — action may never execute |
| 17 | Deprecated page action API | P1 | grep | `page.click(selector)` instead of `page.locator(selector).click()` |
| 18 | `expect.soft()` overuse | P1 | grep+LLM | >50% soft assertions in a test masks cascading failures |
| 19 | Module-Level Mutable State | P1 | grep+LLM | `let x = ...` at column 0 in test code — survives across tests within a worker |
| 20 | Unmocked Real-Backend Writes | P1 | LLM | Form submit / mutation request with no route stub in spec or fixtures |
| 21 | Manual Session-File Dependency | P2 | LLM | `storageState` JSON produced only by a manual capture script |
| 22 | Optimistic UI Without Call Proof | P1 | LLM | Write-control click asserted only via optimistically-updated UI state — no `waitForRequest`/route-hit proof |
| 23 | Fixture Ignores Render Guards | P2 | LLM | Seeded item fails the display component's early-return guards (e.g. `liked: false` in a Liked view) |
| 3b | Cypress uncaught:exception suppression | P0 | grep | `cy.on('uncaught:exception', () => false)` globally swallows app errors |

---

## Suppression

When a grep-detected pattern is intentional, add `// JUSTIFIED: [reason]`. The final report skips a hit when `// JUSTIFIED:` appears in any of these three positions:

1. The line **immediately preceding** the hit
2. The line immediately preceding the **enclosing call/block** when the hit sits inside a body (e.g., `// JUSTIFIED:` above `page.evaluate(() => { … document.querySelector(…) … })` covers every qualifying pattern inside that callback)
3. For chained calls split across lines, the line immediately preceding the chain's **starting expression** covers `.nth()` / `.first()` / `.last()` further down the chain

**Phase 1 vs Phase 2 suppression.** The mechanical scan (`scripts/scan.sh`) only pre-suppresses **position 1** — a contiguous `//`-comment block directly above the hit *line* (it walks up to 5 comment lines for wrapped rationales). Positions **2 and 3** (enclosing block / multi-line-chain start) require knowing the surrounding structure and are applied in **Phase 2 (LLM review)** only. So a hit JUSTIFIED via position 2 or 3 — e.g. `// JUSTIFIED:` above `await expect(` with `.first()` two lines down — **still appears in the Phase 1 mechanical output** and must be skipped during Phase 2, not counted in the final report. This is by design (Phase 1 over-flags; Phase 2 triages with full context), not a missed suppression.

**Exception — #7 Focused Test Leak:** `// JUSTIFIED:` does not suppress `.only` hits. There are no legitimate committed uses of `test.only` / `it.only` / `describe.only` — every hit is P0.
