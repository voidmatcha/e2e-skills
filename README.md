<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — Agent skills for Playwright and Cypress: generate, review, and debug reliable end-to-end tests." width="100%" />
</div>

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-4-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#proven-in-open-source"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-14-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://agents.md"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="https://www.npmjs.com/package/eslint-plugin-playwright-silent-pass"><img alt="playwright silent-pass npm" src="https://img.shields.io/npm/v/eslint-plugin-playwright-silent-pass?style=flat-square&label=playwright%20lint&labelColor=black&color=1FC07C"></a>
  <a href="https://www.npmjs.com/package/eslint-plugin-cypress-silent-pass"><img alt="cypress silent-pass npm" src="https://img.shields.io/npm/v/eslint-plugin-cypress-silent-pass?style=flat-square&label=cypress%20lint&labelColor=black&color=37B0E6"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<strong>🇺🇸 English</strong> | <a href="README.ko.md">🇰🇷 한국어</a> | <a href="README.ja.md">🇯🇵 日本語</a> | <a href="README.zh-cn.md">🇨🇳 简体中文</a>
</p>

Find Playwright/Cypress E2E tests that pass CI while proving little or nothing.

**Not theoretical — `e2e-reviewer` findings have landed [14 merged upstream PRs](#proven-in-open-source)** in real repositories, including SvelteKit, Storybook, code-server, Strapi, Carbon Design System, Ghost, and MUI X.

> One of those repos was code-server (78k&#9733;). An `it.only` had silently disabled 8 tests for seven months — one of them was already broken. CI stayed green the entire time.

`e2e-skills` is a bundle of Agent Skills plus a deterministic scanner for the failure modes that make end-to-end tests silently green: weak assertions, missing `await`, discarded waits/reads, guarded assertions, focused tests, and blanket error suppression.

It is not a test runner, not a broad lint preset, and not a generic browser automation toolkit. It is focused on one question:

> Does this E2E test fail when the user-visible behavior is actually broken?

## Why this exists

AI agents can generate E2E tests quickly, but generated tests often look convincing while checking handles, promises, or one-shot snapshots instead of user-visible state.

```diff
- expect(page.getByText('SWE')).toBeDefined()
+ await expect(page.getByText('SWE')).toBeVisible()
```

The first line only proves that a Playwright `Locator` object exists. The second line proves that the user can see the text.

Silent passes are not the only way generated tests go wrong. Models also ignore YAGNI and KISS, emitting code nothing uses — a Page Object full of methods no test ever calls — and when several models write into one suite, each brings its own style. The bundle divides that work: the reviewer flags unused abstraction (#11, YAGNI + zombie specs), and the generator scaffolds your project's conventions (an `AGENTS.md` E2E section plus a seed spec) on first run so later models write in the same style; a deeper self-inferring version of that is on the [roadmap](#roadmap).

`e2e-skills` turns this into a repeatable review workflow:

1. scan for deterministic silent-pass smells,
2. review ambiguous E2E intent with an Agent Skill,
3. generate better Playwright coverage when a flow is missing,
4. debug failed Playwright/Cypress reports into root-cause fixes.

## See it run

A Playwright test that passes CI but checks nothing — a `Locator` is never undefined, and `.not.toBeNull()` holds whether the element rendered or not:

```ts
test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();   // always passes
  expect(page.locator('.user-badge')).not.toBeNull();     // always passes
});
```

The scanner catches both deterministically, no config:

```console
$ bash skills/e2e-reviewer/scripts/scan.sh tests/

[P0] #4f Locator always-true assertion (truthy/defined/not-null) (2 hits)
  tests/login.spec.ts:6:  expect(page.getByText('Welcome back')).toBeDefined();
  tests/login.spec.ts:8:  expect(page.locator('.user-badge')).not.toBeNull();

Summary: 2 total hit(s), 2 P0
```

## At a glance

| Need | Use |
| --- | --- |
| Generate new Playwright E2E coverage | [`playwright-test-generator`](#skill-1-playwright-test-generator--test-generation) |
| Review existing Playwright/Cypress tests for silent-pass smells | [`e2e-reviewer`](#skill-2-e2e-reviewer--quality-review) |
| Debug failed Playwright reports | [`playwright-debugger`](#skill-3-playwright-debugger--playwright-failure-debugger) |
| Debug failed Cypress reports | [`cypress-debugger`](#skill-4-cypress-debugger--cypress-failure-debugger) |
| Run a deterministic local scan | [`skills/e2e-reviewer/scripts/scan.sh`](#standalone-scanner) |

Useful docs: [case studies](docs/case-studies.md), [roadmap](docs/roadmap.md), [24-smell taxonomy](docs/e2e-test-smells.md), [framework scope](docs/framework-scope.md), [AI reviewer benchmark](docs/ai-reviewer-benchmark.md).

## Install

Installation differs by host: [Claude Code](#claude-code) · [Codex](#codex) · [all other agents](#all-other-agents-cursor-opencode-gemini-cli-and-more) · [manual clone](#manual-clone-claude-code)

### Claude Code

Plugin marketplace:

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

Or via the cross-agent `skills` CLI:

```bash
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

The `skills` CLI is the recommended Codex path. It places the bundle in `~/.agents/skills/`; Codex discovers the skills there and reads `.codex-plugin/plugin.json` for the interface block:

```bash
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code -a codex
```

Alternative — Codex plugin marketplace:

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

### All other agents (Cursor, OpenCode, Gemini CLI, and more)

The cross-agent `skills` CLI covers 55+ hosts. One command installs the bundle globally for every agent it supports:

```bash
npx skills add voidmatcha/e2e-skills -g --all
```

To target a single agent instead, swap `--all` for `-a <agent>` (e.g. `-a cursor`, `-a opencode`, `-a gemini-cli`) — see the [supported-agents list](https://github.com/vercel-labs/skills#supported-agents).

### Manual clone (Claude Code)

```bash
git clone https://github.com/voidmatcha/e2e-skills.git ~/.claude/skills/e2e-skills
```

## Try it

```text
Review my Playwright tests in tests/e2e with e2e-reviewer.
```

```text
Generate Playwright E2E coverage for apps/web/e2e.
```

```text
Debug the failed Playwright report in playwright-report/.
```

## Quick fit

Use `e2e-skills` when:

- Playwright/Cypress tests are passing, but you are not sure they assert real user-visible state.
- AI-generated E2E tests need a quality gate before merge.
- A suite contains suspicious patterns such as `locator().toBeTruthy()`, `not.toBeNull()`, un-awaited `expect(...)`, discarded `isVisible()`, `waitForTimeout()`, `it.only`, or global `uncaught:exception` suppression.
- You want an agent to review test intent, not just syntax.

Do not use it as:

- a replacement for running the application and its real E2E suite,
- a general-purpose lint preset,
- a promise to fix every flaky test,
- a framework-agnostic test tool. Playwright and Cypress are the supported scope.

## Proven in open source

The proof is not synthetic. `e2e-reviewer` findings have been used to land **14 upstream PRs** across recognizable repositories, including SvelteKit, Storybook, code-server, Strapi, Carbon Design System, Ghost, Cal.com, Bruno, Qwik, Element Web, MUI X, and Rancher Desktop.

That track record is paired with a reproducible pilot benchmark: on 100 already-AI-reviewed open-source PRs across 77 repositories, a neutral LLM judge identified 110 material E2E-test trust issues; `e2e-reviewer` found 78 with 0 false positives, lint found 45, and general AI PR reviewers' inline spec comments had found 10. See the [methodology and case evidence](docs/ai-reviewer-benchmark.md).

All merged fixes:

| Repository | PR | Pattern fixed |
| --- | --- | --- |
| Storybook | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Missing `await` on Playwright assertions |
| code-server | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | Focused test leak, matcher-less `expect`, discarded visibility read |
| Strapi | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | Discarded navigation/state checks |
| SvelteKit | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | Floating Playwright assertions |
| Carbon Design System | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | Locator truthiness replaced with web-first assertions |
| Ghost | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise-valued disabled-state assertion |
| Cal.com | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | Weak assertion patterns in E2E flow |
| Bruno | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | Assertion and wait reliability fixes |
| Qwik | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/handle existence checks |
| Element Web | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator null-check style assertions |
| MUI X | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | UI handle checks replaced with state assertions |
| module-federation/core | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Redundant blanket `uncaught:exception` suppression in a Cypress spec |
| FiftyOne | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Locator-defined check replaced with a visible duplicate-name error assertion |
| Rancher Desktop | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `not.toBeNull()` locator checks replaced with visible WSL integration-name assertions |

## Workflow

```text
1. Ask e2e-reviewer to inspect the target test directory.
2. Confirm P0 findings first: these are silent-pass or always-green risks.
3. Patch one smell family at a time.
4. Re-run the deterministic scanner and the target E2E/lint checks.
5. Use playwright-debugger or cypress-debugger only for real failed reports.
```

Example reviewer output:

```text
You: Review my Playwright tests in apps/viewer/src/test/

e2e-reviewer:
[P0] settings.spec.ts:88, 99 — #4h One-shot URL read
expect(page.url()).toEqual(`${baseURL}/${id}-public`);
→ await expect(page).toHaveURL(`${baseURL}/${id}-public`);

[P0] fileUpload.spec.ts:67 — #16 Missing await on action
page.getByRole('button', { name: 'Delete' }).click();
→ await page.getByRole('button', { name: 'Delete' }).click();

Total: 3 P0, 0 P1, 0 P2 in 24 spec files.
```

## Standalone scanner

```bash
./skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

The scanner is intentionally deterministic. It catches the high-confidence subset first; the Agent Skill handles intent-aware review around the scanner findings.

> **Network behavior.** The scanner reads only the files you point it at and uploads nothing. For its precision tier it prefers project-local lint tools and, when absent, auto-downloads pinned public packages (`eslint`, `eslint-plugin-playwright`/`-cypress`, `ast-grep`) via `npx`. Set `E2E_SMELL_NO_ESLINT_DOWNLOAD=1` and `E2E_SMELL_NO_AST_GREP_DOWNLOAD=1` to run fully offline. Full disclosure: [SECURITY.md](./SECURITY.md).

## Skill 1: `playwright-test-generator` — Test Generation

Generates Playwright E2E tests from scratch for any project. Starts from coverage gap analysis, explores the live app via browser automation tools (Playwright MCP / webapp-testing), designs scenarios with your approval, and auto-reviews generated tests with `e2e-reviewer`.

> **Recommended:** set up a browser tool first — [Playwright MCP](https://github.com/microsoft/playwright-mcp#getting-started) or the `webapp-testing` skill. Without one, generation falls back to a static ARIA snapshot that sees only the page's initial state (no interactions) — fine for a simple page, limited for real flows (modals, post-submit, error states, multi-step).

### When to Use

- You have a page or feature with no E2E coverage
- You want to bootstrap a test suite for an existing app
- You need to quickly add tests before a release

### Usage

```
Generate playwright tests
Generate playwright tests for the login page
Write e2e tests for the settings page
Add playwright coverage for checkout flow
```

### Pipeline

1. **Detect environment** — config, baseURL, test dir, POM structure, existing conventions doc
2. **Coverage gap analysis** — user picks target (skipped when target given as argument)
3. **Live browser exploration** — via browser automation tools ([Playwright MCP](https://github.com/microsoft/playwright-mcp#getting-started) / webapp-testing; no hallucinated selectors); accessible-name reality check for label-less inputs
4. **Scenario design + approval gate** — shows plan and locator table before any code
5. **Code generation** — POM + spec or flat spec, auto-detected from project conventions; writes must be route-stubbed (see Network Determinism in `code-rules.md`)
6. **Conventions & seed scaffolding** (first run on a project) — appends a project-adapted E2E section to `AGENTS.md` and designates a seed spec, so future AI-generated tests (Claude Code, Codex, Playwright Agents) stay consistent
7. **YAGNI audit + e2e-reviewer** — removes unused locators, catches P0 issues before first run
8. **TS compile + test run** — 3 auto-fix attempts on failure (heal-by-intent locator re-resolution), then hands off to `playwright-debugger`

---

## Skill 2: `e2e-reviewer` — Quality Review

Catches issues in E2E tests that pass CI but fail to catch real regressions.

Every finding is adversarially verified — refute-first — before it's reported: a read-only subagent on Claude Code plugin installs, inline on other hosts. That separate verification pass is how the reviewer kept false positives at zero in the benchmark.

### When to Use

- Your tests always pass but bugs still slip through to production
- Tests pass CI but you suspect they miss real regressions
- Your test suite is fragile — tests break on every UI change
- You want to audit test quality before a release or code review
- You're reviewing Playwright or Cypress specs

### Usage

```
Review my E2E tests
Audit the spec files in tests/
Find weak tests in my test suite
My tests always pass but miss bugs
Tests pass CI but miss regressions
My tests are fragile and break on every UI change
We have coverage but bugs still slip through
```

### 24 Patterns Detected — Grouped by Severity

#### P0 — Must Fix (silent always-pass)

Tests pass when the feature is broken. No real verification is happening.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 1 | **Name-assertion mismatch** | Name says "status" but only checks `toBeVisible()` | Add assertion for status content, or rename to match actual check |
| 2 | **Missing Then** | Cancel action, verify text restored — but input still visible? | Verify both restored state and dismissed state |
| 3 | **Error swallowing** | `try/catch` in spec, `.catch(() => {})` in POM | Let errors fail; remove silent catch from POM methods |
| 3b | **Cypress `uncaught:exception` suppression** | `cy.on('uncaught:exception', () => false)` blanket-swallows app errors | Scope handler to specific known errors; re-throw unknown errors |
| 4 | **Always-passing assertion** | `toBeGreaterThanOrEqual(0)`; `toBeAttached()` with no comment; `expect(await el.isVisible()).toBe(true)` (one-shot); `expect(await el.textContent()).toBe(x)` (one-shot); `expect(locator).toBeTruthy()` (Locator always truthy); `{ timeout: 0 }` on assertions (disables retry); absence assertion on a locator never proven able to match (4i, P1) | `toBeGreaterThan(0)`; `toBeVisible()`; web-first assertions with auto-retry; assert the element present once before asserting it gone |
| 5 | **Bypass patterns** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`; `{ force: true }` without comment | Always assert; move env checks to `beforeEach`; add `// JUSTIFIED:` to force:true |
| 7 | **Focused test leak** | `test.only(...)` committed — CI runs one test, silently skips the rest | Delete `.only`; use `--grep` or `--spec` for local focus |
| 8 | **Missing assertion** | `await page.locator('.x');` (discarded); `await el.isVisible();` (boolean thrown away) | Add `await expect(locator).toBeVisible()` or delete the line |
| 12 | **Missing auth setup** | Protected-route spec navigates to `/dashboard` with no login/`storageState`/auth fixture | Add `beforeEach` login, configure `storageState`, or use auth fixture — otherwise test passes against the login page |
| 15 | **Missing `await` on `expect()`** | `expect(page.locator('.toast')).toBeVisible()` returns an unobserved Promise | Add `await` so the assertion actually runs |
| 16 | **Missing `await` on action** | `page.locator('#submit').click()` may not execute before the next line | Add `await` so the action completes |

#### P1 — Should Fix (poor diagnostics / wastes CI time)

Tests work but mislead developers, waste CI time, or set up future regressions.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 6 | **Raw DOM queries** | `document.querySelector` in `evaluate()` | Use framework locator/query APIs (`locator` / `cy.get`) |
| 9 | **Hard-coded sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | Rely on framework auto-wait; use condition-based waits |
| 10 | **Flaky test patterns** | `items.nth(2)` without comment; `test.describe.serial()`; unscoped `getByRole`/`getByLabel`/`getByPlaceholder` name without `exact: true` (10c) | Use `data-testid` or role selectors; replace serial with self-contained tests; scope the accessor to a container or pass `exact: true` |
| 13 | **Inconsistent POM usage** | POM imported but spec uses raw `page.fill`/`page.click` for POM-owned actions | Route all interactions through the POM so UI changes update in one place |
| 14 | **Hardcoded credentials** | `loginPage.login('demo-admin', '<literal-password>')` in test code | Use `process.env.TEST_USER`, Playwright config secrets, or test data fixtures |
| 17 | **Direct `page.click(selector)` API** | `page.click('#submit')` / `page.fill('#input', 'text')` skips the Locator layer | Use `page.locator(selector).click()` for auto-wait and better error messages |
| 18 | **`expect.soft()` overuse** | All assertions in a test are `expect.soft()` — test never fails early | Ensure at least one hard `expect()` gates per test; use `soft` only for independent details |
| 19 | **Module-level mutable state in test code** | `let testNotebookSequence = 0;` at column 0 in a test utility — collides across parallel workers and survives retries | Drop the counter; derive uniqueness from `Date.now()` + `Math.random().toString(36).slice(2, 8)`, or move state into `test.beforeEach` |
| 20 | **Unmocked real-backend writes** | Signup/checkout spec submits real mutations — every CI run creates real accounts/orders | Stub write/credential endpoints with `page.route()` / `cy.intercept()`; one designated real-backend smoke spec max |
| 22 | **Optimistic UI without call proof** | Like-toggle test asserts `aria-pressed` flip — UI updates optimistically, passes with the POST deleted | Pair UI assertion with `page.waitForRequest()` (armed before the click) or a route-hit flag |

#### P2 — Nice to Fix (maintenance / robustness)

Weak but not wrong — addressed when refactoring.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | `clickEdit()` never called; empty wrapper class; single-use Util; entire spec duplicated by another | Delete unused members; inline single-use Util methods; delete zombie spec files |
| 21 | **Manually-captured session-file dependency** | `storageState: 'auth/member.json'` produced only by a manual capture script — absent on CI, silently expires | Regenerate session programmatically (API-login helper or `setup` project); manual files only as a cache with a programmatic fallback |
| 23 | **Fixture ignores render guards** | Liked-tab fixture seeds `liked: false`; the card component `return null`s every item — empty UI looks like infra flake | Read the item component's early returns/filters before seeding; seed fields to pass every guard for the view under test |

### What a linter structurally cannot catch

**A linter checks that an assertion is well-formed. It cannot check that the test proves what its name claims.** That gap, between a test's stated intent and what it actually verifies, is the core of what `e2e-reviewer` looks for, and it is invisible to any per-file AST or grep rule: `should show an error when the name is duplicate` can pass with an assertion that never touches the error, and the syntax is flawless. Deciding it needs the test's name, the action it performs, and the surrounding code read together, which is a level above where a single-file rule operates.

`e2e-reviewer` runs `eslint-plugin-playwright` / `eslint-plugin-cypress` as its first tier, so the mechanical rules (`#6`, `#7`, `#9`, `#15`, `#16`, `#5a`, `#5b`) are already covered by the de-facto-standard plugins. The always-passing-Locator-assertion smell (`#4f`) is now covered too: it was contributed upstream from this project as the official `eslint-plugin-playwright` rule [`no-unnecessary-assertions`](https://github.com/mskelton/eslint-plugin-playwright/pull/470) (merged; ships in the next release), with [`eslint-plugin-cypress-silent-pass`](https://github.com/voidmatcha/eslint-plugin-cypress-silent-pass) covering the Cypress side. The reason to add `e2e-reviewer` on top is the smells **no AST or grep rule can reach**, because confirming them requires reading code the rule never sees — other functions, the component, the CI config, the test's own intent:

| Smell | Why lint cannot decide it |
|-------|---------------------------|
| `#1` Name-assertion mismatch | Needs to compare the test's *name/intent* against what it actually asserts. Syntactically the assertion is fine. |
| `#3` / `#3b` Error swallowing & blanket `cy.on('uncaught:exception', () => false)` | Valid syntax; only intent reveals it disables failure. A single-line regex missed **51 multi-line instances** in one suite. |
| `#4f` Locator-as-truthy (`expect(locator).toBeTruthy()` / `.toBeDefined()` / `.not.toBeNull()`) | Reads as a normal assertion. You must *know* a Locator is never falsy to see it always passes. |
| `#4` One-shot reads (`expect(await el.isVisible()).toBe(true)`) | A valid `expect`; only knowing it is a non-retrying point-in-time read marks it as an anti-pattern. |
| `#12` Missing auth setup | Requires cross-file reasoning over config, fixtures, and `storageState` to know the route is unauthenticated. |
| `#20` / `#22` Unmocked writes / optimistic-UI without call proof | Requires knowing an endpoint mutates, or that the UI updates optimistically with no network assertion behind it. |
| `#11` / `#23` Zombie specs / fixture ignores render guards | Cross-file: duplicate-spec detection, or reading a component's early `return null` before trusting a seed. |
| **The hard case** | A `try/catch` wrapping a function that *never throws*, asserting only inside `catch` (real case: `addEdge` in xyflow's `graph-utils.cy.ts`). Confirming it means reading the function body in another file — impossible for grep or any single-file AST rule. |

This is the part that needs judgment, not a pattern match. `e2e-reviewer` reads the surrounding code and CI config to **verify** each candidate before it becomes a finding — the [candidates-not-verdicts](#scanner-findings-are-candidates-not-verdicts) discipline above — which is also why every finding ships with a band-aid-aware fix rather than a raw match.

### References

[Playwright best practices](https://playwright.dev/docs/best-practices) · [Cypress best practices](https://docs.cypress.io/app/core-concepts/best-practices) · [Testing Library guiding principles](https://testing-library.com/docs/guiding-principles)

---

## Skill 3: `playwright-debugger` — Playwright Failure Debugger

Diagnoses Playwright test failures from a `playwright-report/` directory — whether failures happened locally or in CI. Classifies root causes and provides concrete fixes.

### When to Use

- You have a `playwright-report/` directory (local or downloaded from CI) with failures to understand
- Tests pass locally but fail in CI
- You're dealing with flaky or intermittent test failures
- You get `TimeoutError` or `locator not found` without a clear cause

### Usage

```
Debug these failing tests
Why did these tests fail?
Tests pass locally but fail in CI
```

> **Note:** Point the skill at a local report path, or hand it a GitHub Actions run — it downloads the artifact itself via `gh run download` with a user-confirmed run ID (forked-PR runs excluded).

### 15 Root Cause Categories

| # | Category | Signals |
|---|----------|---------|
| F1 | **Flaky / Timing** | `TimeoutError`, passes on retry |
| F2 | **Selector Broken** | `locator not found`, strict mode violation |
| F3 | **Network Dependency** | `net::ERR_*`, unexpected API response |
| F4 | **Assertion Mismatch** | `Expected X to equal Y`, subject-inversion |
| F5 | **Missing Then** | Action completed but wrong state remains |
| F6 | **Condition Branch Missing** | Element conditionally present, assertion always runs |
| F7 | **Test Isolation Failure** | Passes alone, fails in suite |
| F8 | **Environment Mismatch** | CI vs local only; viewport, OS, timezone |
| F9 | **Data Dependency** | Missing seed data, hardcoded IDs |
| F10 | **Auth / Session** | Session expired, role-based UI not rendered |
| F11 | **Async Order Assumption** | `Promise.all` order, parallel race |
| F12 | **POM / Locator Drift** | DOM structure changed, POM not updated |
| F13 | **Error Swallowing** | `.catch(() => {})` hiding actual failure |
| F14 | **Animation Race** | Content not yet rendered, or a transient element removed before it is observed |
| F15 | **Hydration Race** | Action succeeds but has no effect — SSR page not yet hydrated; fails at the next assertion |

### Debug Workflow

1. **Extract** — parse `results.json` for failed tests, error messages, duration
2. **Classify** — map each failure to F1–F15 using error signals (most failures resolved here)
3. **Trace** — if still unclear, extract `trace.zip` and inspect step-by-step: failed actions, DOM snapshots, network errors, JS console errors
4. **Fix** — concrete code suggestion per failure, P0/P1/P2 priority

---

## Skill 4: `cypress-debugger` — Cypress Failure Debugger

Diagnoses Cypress test failures from mochawesome or JUnit report files. Classifies root causes and provides concrete fixes.

### When to Use

- You have a `cypress/reports/` directory (local or downloaded from CI) with failures to understand
- Cypress tests pass locally but fail in CI
- You're dealing with flaky or intermittent Cypress failures
- You get `Timed out retrying` or `Expected to find element` without a clear cause

### Usage

```
Debug these failing Cypress tests
Why did these Cypress tests fail?
Analyze cypress/reports/
Cypress tests pass locally but fail in CI
```

### 15 Root Cause Categories

| # | Category | Signals |
|---|----------|---------|
| F1 | **Flaky / Timing** | `Timed out retrying`, passes on retry |
| F2 | **Selector Broken** | `Expected to find element`, `cy.get() failed` |
| F3 | **Network Dependency** | `cy.intercept()` not matched, `XHR failed` |
| F4 | **Assertion Mismatch** | `expected X to equal Y`, `AssertionError` |
| F5 | **Missing Then** | Action completed but wrong state remains |
| F6 | **Condition Branch Missing** | Element conditionally present, assertion always runs |
| F7 | **Test Isolation Failure** | Passes alone, fails in suite |
| F8 | **Environment Mismatch** | CI vs local only; baseUrl, viewport, OS |
| F9 | **Data Dependency** | Missing seed data, `cy.fixture()` mismatch |
| F10 | **Auth / Session** | `cy.session()` expired, role-based UI not rendered |
| F11 | **Command Queue / Intercept Race** | `cy.intercept` registered after request fires; `.then()` chain order swap; parallel `cy.request()` race against an unfinished `cy.visit()` |
| F12 | **Selector Drift** | DOM changed, custom command or POM selector not updated |
| F13 | **Error Swallowing** | `cy.on('uncaught:exception', () => false)` hiding failures |
| F14 | **Animation Race** | Content not yet rendered, a transient element removed before observed, or CSS transition not complete |
| F15 | **Hydration Race** | First click after `cy.visit()` succeeds but has no effect — SSR page not yet hydrated; fails at the next assertion |

### Debug Workflow

1. **Extract** — parse `mochawesome.json` or JUnit XML for failed tests, error messages, duration
2. **Classify** — map each failure to F1–F15 using error signals (most failures resolved here)
3. **Screenshot/Video** — if still unclear, inspect `cypress/screenshots/` and `cypress/videos/`
4. **Fix** — concrete code suggestion per failure, P0/P1/P2 priority

---

## FAQ

### What is e2e-skills?

e2e-skills is an open-source AI agent testing toolkit for Playwright and Cypress. It bundles four Agent Skills that generate end-to-end tests, review existing specs for silent always-pass anti-patterns, and debug flaky failures — running inside Claude Code, Codex, and other `AGENTS.md`-compatible AI coding agents.

### How do I find Playwright or Cypress tests that pass but don't actually test anything?

Run the `e2e-reviewer` skill (or its standalone scanner, `scan.sh`) against your spec directory. It flags 24 anti-patterns grouped by severity (P0/P1/P2) — including missing `await` on assertions, one-shot `isVisible()` reads, matcher-less `expect()`, and committed `.only` leaks — that let a test stay green while the feature it covers is broken.

### How is this different from eslint-plugin-playwright or eslint-plugin-cypress?

The eslint plugins are your every-commit baseline for syntactic rules, and the scanner runs them first (Tier 1) — so it does not replace them, it adds a layer on top. The layer is the smells a linter [structurally cannot decide](#what-a-linter-structurally-cannot-catch): a name-assertion mismatch, a `try/catch` around a function that never throws, a delete test that never checks the row is gone, a missing-auth route — each needs reading code the AST rule never sees (another function, the component, the CI config, the test's intent). (The mechanical always-true case — `expect(locator).toBeTruthy()` — *is* single-file lintable, which is why it was contributed upstream as the official `eslint-plugin-playwright` rule `no-unnecessary-assertions`; the scanner's first tier runs it.) `e2e-reviewer` reads that surrounding code to verify the finding and ships a band-aid-aware fix, where lint can only flag single-file syntax.

### Isn't this just an AI code reviewer like CodeRabbit, Copilot, or Cursor BugBot?

Those are excellent general reviewers — several are free for open source and now run locally (CodeRabbit's CLI reviews staged changes in the terminal). The difference is specialization, not capability: a general reviewer reasons over whatever diff it is handed, while `e2e-reviewer` carries a curated, stable, severity-graded catalog of E2E silent always-pass anti-patterns (24 patterns with fixed IDs, plus 15 failure-debugging categories) and runs on demand against a whole spec directory, not only a PR diff. Use a general reviewer for everything; use this when E2E test trustworthiness is the thing you care about. For a real head-to-head on 100 reviewed PRs (with honest limitations), see the [AI-reviewer benchmark](docs/ai-reviewer-benchmark.md).

### Does it work with Cypress as well as Playwright?

Yes. Both are first-class: test generation and the richest review target Playwright, while review and failure debugging fully cover Cypress (mochawesome and JUnit reports).

### Can it debug flaky tests that only fail in CI?

Yes. `playwright-debugger` and `cypress-debugger` read your report files (`playwright-report/`, `cypress/reports/`) and classify each failure into 15 root-cause categories — flaky timing, selector drift, test isolation, environment mismatch, hydration race, and more — with a concrete fix per failure.

### How do I review AI-generated E2E tests?

Point `e2e-reviewer` at the generated specs. AI-written tests frequently contain confident-looking but silent always-pass assertions; the reviewer surfaces them with before/after fixes before they reach your main branch.

### Which AI coding agents are supported?

Claude Code (plugin marketplace or the `skills` CLI), Codex, and any agent the `skills` CLI supports via `AGENTS.md` (55+ hosts). Install once, use everywhere.

### Does it support test frameworks other than Playwright and Cypress?

No — Playwright and Cypress only, by design. See [framework scope](docs/framework-scope.md) for the rationale.

## Roadmap

Planned, not yet shipped (these describe direction, not current behavior):

- **Cross-model consistency.** Different AI agents each write specs in their own style, so a suite built with several models drifts into a patchwork no single convention holds together. The plan: infer your project's conventions (POM shape, locator strategy, fixture and structure patterns) — where "no abstraction" is a valid answer, so a two-page flow does not get a Page Object layer it never needed — ask you only where the codebase is genuinely ambiguous, and persist the answers so every model conforms afterward. Crucially, the recorded conventions stay a *default the agent can deviate from with a stated reason*, not a hard rule, so a better approach for a specific test is never blocked — and a justified deviation becomes a prompt to evolve the convention. This is the part a linter structurally cannot do: it enforces fixed rules; it cannot learn and conform to *your* conventions.
- **Deterministic detection layer.** Move the per-file, type-decidable smells (locator-as-truthy, floating assertions) from prompt-and-heuristic onto a type-aware AST pass, so detection is reproducible and the LLM is reserved for the judgment calls a single-file rule cannot make. The clearly lint-able rules are contributed upstream to `eslint-plugin-playwright` rather than re-implemented — the first, `no-unnecessary-assertions` for always-passing Locator assertions, is [merged](https://github.com/mskelton/eslint-plugin-playwright/pull/470).

Separately, the upstream contribution roadmap tracks the broader pipeline: **14 PRs merged, 14 in review or queued**. The queue holds only vetted 1,000+ star candidates — live tables in [upstream contributions](docs/roadmap.md).

## Contributing

Bug reports, false-positive guards, new anti-patterns, and translations are all
welcome. Start with [CONTRIBUTING.md](./CONTRIBUTING.md) for the setup, the
verification gate (`bash scripts/ci/ci-local.sh`), and the frozen-ID / parity
conventions. Deeper cross-agent detail lives in [AGENTS.md](./AGENTS.md).

## License

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha). See [LICENSE](./LICENSE).
