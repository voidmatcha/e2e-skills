# Phase 4: Applying Fixes — full contract

Read on demand when SKILL.md Phase 4 begins (producing fixes). This file is the authority for
canonical replacements, band-aid handling, cascade cleanups, cycle count, and scope discipline.

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
| `#4c-4e` `expect(await x.allTextContents()).toContain(v)` | `await expect(x).toContainText(v)` | `allTextContents()` returns `string[]`; on a multi-element locator `toContainText(v)` auto-retries and passes if any matched element contains `v`. For a single element prefer `toHaveText`. |
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

6. **Match the codebase's EXACT canonical form. Do not invent variants.** When the §4.1 table above prescribes a fix (e.g., `expect(page.url()).toContain(x)` → `await expect.poll(() => page.url()).toContain(x)`), use that exact shape unless you observe the codebase using something equivalent. Inventing new forms (e.g., `await expect(page).toHaveURL((url) => url.toString().includes(x))`) — even when they're valid Playwright — creates idiom drift that reviewers will push back on. Before introducing any form not already present in the file, count its usage in the repo: if zero existing callsites use it, prefer the form the codebase already uses. (Real case: a repo had 5 existing `expect.poll(() => page.url()).toContain(x)` callsites; a fix-PR introduced 8 callback-form `toHaveURL((url) => url.includes(x))` conversions — functionally correct, stylistically out of step.)

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

9. **Framework self-test gray zone.** When the target repo is itself a framework or component library (Nuxt, SvelteKit, React Router, Ionic, Qwik, design systems), most Playwright/Cypress hits live in **framework test fixtures** — apps that exist only to test the framework. Real P0 mechanics (one-shot reads, missing awaits) still apply, but PR-worthiness differs: maintainers treat fixture tests as internal scaffolding, and a large mechanical migration there may be unwanted churn. Before proposing a PR on a framework repo, check whether the affected specs test the framework's own behavior (fixtures/examples/e2e harness) vs. a user-facing product surface, and say which in the finding. Lead with the smallest, highest-signal subset rather than the full bulk count.

10. **PR-worthiness triage (when the goal is an upstream PR, not just a report).** A finding is PR-worthy if and only if at least one real P0 is a silent-always-pass or race defect in a real user-facing E2E spec. Findings that are only (a) framework self-test fixtures (see 9), (b) unit-test-scope smells (Vitest/Jest/RTL — out of e2e scope), or (c) cosmetic dead code with no masked behavior, do not justify an upstream PR on their own — fold them into an issue or skip. This is the empirical KEEP/DELETE bar from a 110-repo OSS validation: roughly half of scanned repos had zero PR-worthy surface despite nonzero raw P0 counts.

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

**Do NOT add cycles past 5% marginal gain.** That's diminishing returns. For residual hits, document them in the review report or add `// JUSTIFIED:` comments when editing is in scope — don't manufacture cycles.

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

