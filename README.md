<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — Agent skills for Playwright and Cypress: generate, review, and debug reliable end-to-end tests." width="100%" />
</div>

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-4-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#open-source-adoption-and-case-evidence"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-14-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://agents.md"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="https://www.npmjs.com/package/eslint-plugin-cypress-silent-pass"><img alt="cypress silent-pass npm" src="https://img.shields.io/npm/v/eslint-plugin-cypress-silent-pass?style=flat-square&label=cypress%20lint&labelColor=black&color=37B0E6"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<strong>🇺🇸 English</strong> | <a href="README.ko.md">🇰🇷 한국어</a> | <a href="README.ja.md">🇯🇵 日本語</a> | <a href="README.zh-cn.md">🇨🇳 简体中文</a>
</p>

Find Playwright/Cypress E2E tests that pass CI while proving little or nothing.

**Open-source adoption — `e2e-reviewer` findings have been used in [14 merged upstream PRs](#open-source-adoption-and-case-evidence)** across repositories including SvelteKit, Storybook, code-server, Strapi, Carbon Design System, Ghost, and MUI X.

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

Silent passes are not the only way generated tests go wrong. Models also ignore YAGNI and KISS, emitting code nothing uses — a Page Object full of methods no test ever calls — and when several models write into one suite, each brings its own style. The bundle divides that work: the reviewer flags unused abstraction (#11, YAGNI + zombie specs), and on first run the generator can optionally propose project conventions (an `AGENTS.md` E2E section plus a seed-spec designation). It creates, appends, or designates only the exact paths the user approves; each proposed path can be skipped independently. A deeper self-inferring version is on the [roadmap](#roadmap).

`e2e-skills` turns this into a repeatable review workflow:

1. scan for deterministic silent-pass smells,
2. review ambiguous E2E intent with an Agent Skill,
3. generate better Playwright coverage when a flow is missing,
4. debug failed Playwright/Cypress reports into root-cause fixes.

## Methodology

Generating a test is easy. Generating a test that **fails when the product is wrong** is the harder problem. An LLM can produce valid syntax, execute the intended flow, and still finish green because the assertion is always truthy, checks the wrong state, or never verifies the outcome.

This is not only a hypothetical failure mode. [Test Smells in LLM-Generated Unit Tests](https://arxiv.org/abs/2410.10628) analyzed 20,505 generated test suites, while a controlled study of 86 programmers found that incorrect LLM-generated postconditions were classified correctly only [49.0% of the time](https://arxiv.org/abs/2607.08885). Those studies concern unit-level oracles, not browser E2E fault detection, so this repository treats them as design evidence rather than an E2E accuracy estimate.

That evidence motivates a review-first method rather than trust in a green run:

1. Name the behavior the test is supposed to prove before writing or accepting the assertion.
2. Prefer framework-native, retry-aware assertions that can fail for the right reason.
3. Reject always-truthy assertions, missing post-state checks, and name↔assertion mismatches even when CI is green.
4. Use deterministic checks for mechanical smells and LLM review only for semantic judgment calls.

### Evidence and benchmark status

The current evidence supports a narrow conclusion: the project has behavior-backed development evidence and **14 merged upstream PRs**, but it does **not** yet claim generalized reviewer accuracy.

- Browser fault injection completed **36/36 Playwright/Cypress cells**.
- The exact reviewer benchmark covers **12 proven false-green cases, including 10 byte-identical mutants, plus 12 clean guards**.
- Independent robustness gates v4, v5, v7, and v8 failed their preregistered criteria; v6 and v9 were not run, and v10 is frozen but not run.

See [Benchmarks and Evidence Status](benchmarks/STATUS.md) for scores, protocols, negative results, and the limits of each claim. The separate [research evidence ledger](docs/llm-generated-e2e-test-evidence.md) audits the external sources behind the methodology.

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
$ /bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests/

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
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

The `skills` CLI is the recommended Codex path. It places the four skill copies
in `~/.agents/skills/`, which Codex discovers directly from their `SKILL.md`
files. This route does not install the repository-root
`.codex-plugin/plugin.json`; that interface manifest belongs to the alternative
Codex plugin-marketplace path below.

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a codex
```

This command targets Codex only. To install for Claude Code too, use the
separate Claude Code command above.

Alternative — Codex plugin marketplace:

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

When a Codex host exposes native role routing, `e2e-reviewer`,
`playwright-debugger`, and `cypress-debugger` can use its built-in
`verifier`/`debugger` subagent roles without installing custom agents; those
three skills preserve the same verdict or failure taxonomy through their inline
fallback when native delegation is unavailable. `playwright-test-generator`
has a stricter boundary: V6 requires a distinct fresh-context, read-only
reviewer. Without that independent context it reports `CANNOT_VERIFY` and
`PARTIAL/BLOCKED`, not an equivalent inline review. A source checkout also
includes stricter named agents under `.codex/agents/`. `reinstall-skills.sh`
does not install those global agents by default. Contributors can run
`bash scripts/dev/install-codex-agents.sh` separately, or set
`E2E_SKILLS_INSTALL_CODEX_AGENTS=1` for an explicit combined reinstall, then
restart Codex.

### All other agents (Cursor, OpenCode, Gemini CLI, and more)

The cross-agent `skills` CLI covers 55+ hosts. One command installs the bundle globally for every agent it supports:

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all
```

To target a single agent instead, swap `--all` for `-a <agent>` (e.g. `-a cursor`, `-a opencode`, `-a gemini-cli`) — see the [supported-agents list](https://github.com/vercel-labs/skills#supported-agents).

The commands above pin the tested `skills` CLI release so a global install does
not execute an unreviewed newer CLI. Upgrade that version deliberately after
reviewing its release notes.

### Manual clone (Claude Code)

Claude Code discovers personal skills only when each skill directory is a
direct child of `~/.claude/skills/`. Keep the repository checkout outside that
directory, then expose the four skill roots with
[supported per-skill symlinks](https://code.claude.com/docs/en/skills#where-skills-live):

```bash
git clone https://github.com/voidmatcha/e2e-skills.git "$HOME/.claude/e2e-skills"
mkdir -p "$HOME/.claude/skills"

for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
  ln -s "$HOME/.claude/e2e-skills/skills/$skill" "$HOME/.claude/skills/$skill"
done
```

The links fail instead of replacing an existing same-named skill. Run
`/skills` in Claude Code and confirm that all four names appear.

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

## Open-source adoption and case evidence

`e2e-reviewer` findings have been used to land **14 upstream PRs** across recognizable repositories, including SvelteKit, Storybook, code-server, Strapi, Carbon Design System, Ghost, Cal.com, Bruno, Qwik, Element Web, MUI X, and Rancher Desktop. These self-selected contributions show adoption and provide concrete case evidence; they are not a representative validation sample or an accuracy estimate.

For historical context, a model-authored pilot examined 100 already-AI-reviewed open-source PRs across 77 repositories. Its judge labeled a 110-issue reference set; `e2e-reviewer` matched 78 with no judged false positives in that sample, lint matched 45, and general AI PR reviewers' inline spec comments had matched 10. The judge was not neutral ground truth, so this pilot is archived case evidence rather than current product validation or proof; see its [methodology and limitations](docs/ai-reviewer-benchmark.md).

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
[P1] settings.spec.ts:88, 99 — #4h One-shot URL read
expect(page.url()).toEqual(`${baseURL}/${id}-public`);
→ await expect(page).toHaveURL(`${baseURL}/${id}-public`);

[P1] fileUpload.spec.ts:67 — #16 Missing await on action
page.getByRole('button', { name: 'Delete' }).click();
→ await page.getByRole('button', { name: 'Delete' }).click();

Total: 0 P0, 2 P1, 0 P2 in 24 spec files.
```

<a id="scanner-findings-are-candidates-not-verdicts"></a>

## Standalone scanner

```bash
./skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

The scanner has three tiers with different guarantees. Tier 1 runs the target
project's ESLint stack only after
`E2E_SMELL_ALLOW_PROJECT_ESLINT=1`. Tier 2 runs `ast-grep` only when a trusted
`ast-grep`/`sg` executable is available or its pinned `npx` fallback is
explicitly enabled. Set `E2E_SMELL_DISABLE_AST_GREP=1` when a portable or
offline contract must ignore even preinstalled host binaries. The output prints
a Tier 2 heading only when that tier ran;
no heading means it was unavailable or disabled. On a successful scan, Tier 3
runs the bundled PCRE2 checks as the fallback for grep-detectable patterns, but
it does not reproduce every AST-only Tier 2 match. The Agent Skill handles
intent-aware review around all scanner findings.

Its shared source boundary covers `.ts`, `.js`, `.tsx`, `.jsx`, `.mts`,
`.mjs`, `.cts`, and `.cjs`. Bundled lexical filters keep focused-test strings
out of the unsuppressible #7 gate and cover formatted multi-line #4f Locator
assertions without relying on optional AST tooling. Framework-content detection
runs after extension discovery, so custom Playwright `testMatch` names such as
`login.e2e.ts` are not excluded by basename. The scanner requires a
PCRE2-capable `rg` and Python 3. Python creates and validates NUL-safe candidate
identity records so candidate drift or malformed records fail closed; this
mandatory bookkeeping is separate from optional Tier 2 AST tooling. The
scanner exits 2 on engine/filesystem scan errors instead of turning them into a
clean result. Suppression requires a lexical
`// JUSTIFIED: <nonempty rationale>` comment.

> **Trust and network behavior.** By default the scanner evaluates no
> target-controlled executable, plugin, parser, or ESLint config.
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> Its bundled checks report only source beneath the requested path; framework-provenance
> resolution may read relative fixture/support imports elsewhere inside the
> containing project.
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->
> The scanner contains no telemetry or intentional network
> operation. PATH-resolved `rg`, `ast-grep`, or `sg` executables located
> anywhere inside the containing target project are rejected, including when
> the requested path is only a subdirectory.
> `E2E_SMELL_ALLOW_PROJECT_ESLINT=1` explicitly
> opts into executing the target project's local ESLint stack with an
> environment allowlist and E2E-scoped file arguments. That mode is **not
> sandboxed**: trusted project code can still read/write accessible files,
> spawn processes, or use the network. Legacy `npx` downloads are separate
> opt-ins via `E2E_SMELL_NO_ESLINT_DOWNLOAD=0` and
> `E2E_SMELL_NO_AST_GREP_DOWNLOAD=0`; they execute downloaded third-party code.
> Full disclosure: [SECURITY.md](./SECURITY.md).

## Skill 1: `playwright-test-generator` — Test Generation

Generates Playwright E2E tests from scratch for any project. It starts from coverage-gap analysis, explores a local/disposable app through browser automation, designs scenarios with your approval, and auto-reviews generated tests with `e2e-reviewer`. Remote live exploration is limited to explicitly approved non-production targets inside an externally isolated controlled browser harness; shared, production, and unknown remote targets use sanitized user-provided snapshots only.

> **Recommended for an eligible live target:** set up a browser tool first — [Playwright MCP](https://github.com/microsoft/playwright-mcp#getting-started) or the `webapp-testing` skill. Without one, a local/disposable target can fall back to a static ARIA snapshot that sees only the page's initial state (no interactions); a snapshot-only remote requires sanitized snapshots from the user. The bundled executable preflight validates URL/IP classes, pins every DNS peer, binds and records a trusted absolute curl instead of ambient `PATH`, and keeps credential-bearing or ambiguous queries out of process arguments. Ordinary non-secret route parameters may remain. Matching `401`/`403` or one validated same-origin login redirect proves protected-route reachability, not success.

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
3. **Bounded exploration** — live browser automation for local/disposable targets, or externally isolated approved non-production remotes; sanitized user-provided snapshots for shared, production, or unknown remotes; executable URL/DNS/redirect preflight and no hallucinated selectors
4. **Scenario design + approval gate** — shows plan and locator table before any code
5. **Code generation** — POM + spec or flat spec, auto-detected from project conventions; state-changing flows must use a controlled boundary at the actual write seam: a browser route/intercept when the browser request is the seam, or a disposable, rollback-backed, or isolated server/backend when the write occurs there (see Network Determinism in `code-rules.md`)
6. **Optional conventions & seed scaffolding** (first run on a project) — proposes exact `AGENTS.md` and seed-spec designation paths, then creates/appends/designates only the individually approved paths; any row can be skipped without blocking test generation
7. **YAGNI audit + e2e-reviewer** — removes unused locators, catches P0 issues before first run
8. **TS compile + test run** — 3 auto-fix attempts on failure (heal-by-intent locator re-resolution), then hands off to `playwright-debugger`

---

## Skill 2: `e2e-reviewer` — Quality Review

Catches issues in E2E tests that pass CI but fail to catch real regressions.

Every semantic finding is adversarially verified — refute-first — before it is reported: a read-only subagent on Claude Code plugin installs, inline on other hosts. This review procedure reduces unsupported findings but is not a guarantee for every repository.

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
| 4 | **Vacuous or retry-weakening assertion** (P0/P1) | P0: invariant predicates and Locator truthiness. P1: weak attachment proof; one-shot values/URL; zero-timeout retry/deadline hazards; unproven absence; ARIA snapshots that omit a promised accessible name | Use meaningful bounds and web-first auto-retrying assertions; prove presence before absence and keep promised accessible names load-bearing |
| 5 | **Bypass patterns** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`; `{ force: true }` without comment | Always assert; move env checks to `beforeEach`; add `// JUSTIFIED:` to force:true |
| 7 | **Focused test leak** | `test.only(...)` committed — CI runs one test, silently skips the rest | Delete `.only`; use `--grep` or `--spec` for local focus |
| 8 | **Missing assertion** | Discarded locator/boolean is the scenario's only verification | Add `await expect(locator).toBeVisible()`; skip #8 when independent verification/failure evidence already exists |
| 12 | **Missing auth setup** | With no login/`storageState`/auth fixture, a protected-route spec passes because its generic assertion also matches the login/wrong surface | Add `beforeEach` login, configure `storageState`, or use an auth fixture; do not classify a normal auth-caused failure as P0 |

#### P1 — Should Fix (poor diagnostics / wastes CI time)

Tests work but mislead developers, waste CI time, or set up future regressions.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 6 | **Raw DOM queries** | `document.querySelector` in `evaluate()` | Use framework locator/query APIs (`locator` / `cy.get`) |
| 9 | **Hard-coded sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | Rely on framework auto-wait; use condition-based waits |
| 10 | **Flaky test patterns** | `items.nth(2)` without comment; `test.describe.serial()`; unscoped accessible-name substring (10c); Cypress async callbacks, assigned `cy` commands, or continued action chains (10d–10f) | Use stable/scoped locators and self-contained tests; keep Cypress work in its command chain, do not assign Chainables as values, and re-query after actions |
| 13 | **Inconsistent POM usage** | POM imported but spec uses raw `page.fill`/`page.click` for POM-owned actions | Route all interactions through the POM so UI changes update in one place |
| 14 | **Hardcoded credentials** | `loginPage.login('demo-admin', '<literal-password>')` in test code | Use `process.env.TEST_USER`, Playwright config secrets, or test data fixtures |
| 15 | **Missing `await` on `expect()`** | Async Locator/Page web-first matcher Promise is not sequenced or observed; rejection usually surfaces later with worse attribution | `await` or return the matcher Promise; sync value matchers are excluded |
| 16 | **Missing `await` on action** | Actionability, action ordering, or navigation can race later work; rejection usually surfaces later with worse attribution | `await` or return the action Promise |
| 17 | **Discouraged direct Page selector API** | Selector-based `page.click`, `page.fill`, and related Page actions skip the Locator layer | Use Locator actions for composition, strictness, reuse, and clearer failures |
| 18 | **`expect.soft()` overuse** | Critical soft assertions run before a hard scenario gate, so dependent work continues after a broken prerequisite | Hard-gate the primary state first; use `soft` only for independent details |
| 19 | **Module-level mutable state in test code** | `let testNotebookSequence = 0;` at column 0 in a test utility — persists across tests in a long-lived worker and collides across parallel workers | Drop the counter; derive uniqueness from `Date.now()` + `Math.random().toString(36).slice(2, 8)`, or move state into `test.beforeEach` |
| 20 | **Unmocked real-backend writes** | Signup/checkout spec reaches shared or persistent state with no controlled test boundary | Stub the write or prove a disposable container, rollback fixture, isolated tenant/database, or equivalent controlled backend |
| 22 | **Optimistic UI without call proof** | Like-toggle test asserts `aria-pressed` flip — UI updates optimistically, passes with the POST deleted | Pair UI assertion with `page.waitForRequest()` (armed before the click) or a route-hit flag |

#### P2 — Nice to Fix (maintenance / robustness)

Weak but not wrong — addressed when refactoring.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | `clickEdit()` never called; unjustified empty wrapper class; entire spec duplicated by another | Delete unused members and zombie specs; inline single-use helpers only when that clearly removes meaningless indirection |
| 21 | **Manually-captured session-file dependency** | `storageState: 'auth/member.json'` produced only by a manual capture script — absent on CI, silently expires | Regenerate session programmatically (API-login helper or `setup` project); manual files only as a cache with a programmatic fallback |
| 23 | **Fixture ignores render guards** | Liked-tab fixture seeds `liked: false`; the card component `return null`s every item — empty UI looks like infra flake | Read the item component's early returns/filters before seeding; seed fields to pass every guard for the view under test |

### What lint alone does not establish

**A linter checks that an assertion is well-formed. It cannot check that the test proves what its name claims.** That gap, between a test's stated intent and what it actually verifies, is the core of what `e2e-reviewer` looks for, and it is invisible to any per-file AST or grep rule: `should show an error when the name is duplicate` can pass with an assertion that never touches the error, and the syntax is flawless. Deciding it needs the test's name, the action it performs, and the surrounding code read together, which is a level above where a single-file rule operates.

When the caller explicitly sets `E2E_SMELL_ALLOW_PROJECT_ESLINT=1`,
`e2e-reviewer` reuses compatible project-local
`eslint-plugin-playwright` / `eslint-plugin-cypress` for part of the mechanical
surface (`#6`, `#7`, `#9`, `#15`, `#16`, `#5a`, `#5b`) and supplements them
with bundled scanner checks. Coverage is intentionally partial: rule versions,
configuration, receiver provenance, and multiline shapes still require the
scanner or Phase 2 confirmation. The Locator-as-truthy smell (`#4f`) also has
an official `eslint-plugin-playwright` rule,
[`no-unnecessary-assertions`](https://github.com/mskelton/eslint-plugin-playwright/pull/470)
(shipped in v2.11.0 and enabled by its `recommended` config), while
[`eslint-plugin-cypress-silent-pass`](https://github.com/voidmatcha/eslint-plugin-cypress-silent-pass)
covers related Cypress shapes. The reason to add semantic review is the set of
smells **a single-file AST or grep rule cannot decide on its own**, because
confirming them requires reading other functions, components, config, or the
test's stated intent:

| Smell | Why lint cannot decide it |
|-------|---------------------------|
| `#1` Name-assertion mismatch | Needs to compare the test's *name/intent* against what it actually asserts. Syntactically the assertion is fine. |
| `#3` / `#3b` Error swallowing & blanket `cy.on('uncaught:exception', () => false)` | Valid syntax; only intent reveals it disables failure. A single-line regex missed **51 multi-line instances** in one suite. |
| `#4f` Locator-as-truthy (`expect(locator).toBeTruthy()` / `.toBeDefined()` / `.not.toBeNull()`) | A framework-aware rule catches direct Locator shapes; semantic review still traces aliases, POM properties, and helper-returned Locators. |
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

> **Note:** Point the skill at a local report path, or hand it a GitHub Actions run. With a user-confirmed strict `owner/repo` slug and numeric run ID, its bounded `gh api` helper resolves and binds the repository's numeric identity on `github.com`, uses explicit endpoints independent of ambient checkout configuration, and downloads the fixed artifact without giving `gh` an extraction destination; forked-PR runs are rejected.

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

<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->
The `e2e-reviewer` skill reviews all 24 catalog patterns with stable IDs and P0/P1/P2 severity. Its standalone `scan.sh` scanner covers only a deterministic mechanical subset. Scanner matches are candidates, not final findings; the skill checks intent and surrounding code before reporting a verdict.

The debuggers classify failures against the stable F1–F15 taxonomy. They and the generator execute target-controlled code only after you trust the repository and approve the exact command, including its environment and flags.

For non-public benchmark runs, `--isolation-wrapper` is a required hook, not proof of isolation. Continuous integration (CI) validates the wrapper contract but does not attest filesystem, process, or network isolation.
<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

The 24-pattern catalog includes silent always-pass bugs, missing `await` on assertions and Locator/Page Object Model (POM) actions, one-shot `isVisible()` reads, and committed `.only` leaks. Missing awaits are P1 sequencing and failure-attribution risks, not unconditional silent passes.

### How is this different from eslint-plugin-playwright or eslint-plugin-cypress?

The eslint plugins are your every-commit baseline for syntactic rules. The
scanner does not execute a target project's lint stack by default; run the
project's documented lint command separately, or explicitly opt into scanner
Tier 1 with `E2E_SMELL_ALLOW_PROJECT_ESLINT=1` for a trusted checkout. In that
mode the scanner layers the project's flat config over the plugin's
`recommended` preset, so a deliberately disabled rule stays disabled in Tier
1. The semantic layer is the smells
[lint alone does not establish](#what-lint-alone-does-not-establish): a
name-assertion mismatch, a swallowed error, an unverified delete, or a
missing-auth route can require another function, component, CI config, or the
test's intent. The mechanical Locator-truthiness case is single-file lintable
and is covered by `eslint-plugin-playwright/no-unnecessary-assertions`; the
bundled scanner remains the secure-default baseline.

### Isn't this just an AI code reviewer like CodeRabbit, Copilot, or Cursor BugBot?

Those are excellent general reviewers — several are free for open source and now run locally (CodeRabbit's CLI reviews staged changes in the terminal). The difference is specialization, not capability: a general reviewer reasons over whatever diff it is handed, while `e2e-reviewer` carries a curated, stable, severity-graded catalog of E2E silent always-pass anti-patterns (24 patterns with fixed IDs, plus 15 failure-debugging categories) and runs on demand against a whole spec directory, not only a PR diff. Use a general reviewer for everything; use this when E2E test trustworthiness is the thing you care about. A historical model-authored 100-PR comparison, retained as sample-specific case evidence rather than current validation, is documented in the [AI-reviewer benchmark](docs/ai-reviewer-benchmark.md).

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

- **Cross-model consistency.** Different AI agents each write specs in their own style, so a suite built with several models drifts into a patchwork no single convention holds together. The planned first increment is generator-only: infer scoped structure, locator, fixture, and path defaults; record them as a versioned structured block inside the already approved `AGENTS.md` E2E section; and attach evidence plus `user-confirmed`, `inferred`, or `product-default` provenance to each field. A directory's existence alone will not require a Page Object. With no active POM evidence, the default is a flat spec; "no abstraction" is a valid answer. Only convention fields that are genuinely ambiguous for the current target should prompt a question. Target, command, safety, scenario, and control-file approvals remain mandatory. Recorded conventions stay *defaults an agent can deviate from with a scoped reason*, and those deviations can evolve soft conventions but can never weaken P0 or safety contracts. This is the part a linter structurally cannot do: it enforces fixed rules; it cannot learn and conform to *your* conventions. A dedicated convention-inference benchmark must pass before this is described as shipped.
- **Deterministic detection layer.** Move the per-file, type-decidable smells (locator-as-truthy, floating assertions) from prompt-and-heuristic onto an optional scanner-owned TypeScript compiler pass, so detection is reproducible and the LLM is reserved for judgment calls a type checker cannot prove. The scanner will bind a trusted, pinned compiler rather than executing the target project's ESLint config or plugins by default; existing structural and regex tiers remain fail-closed fallbacks, and unresolved types remain review triage rather than forced findings. Clearly lintable rules are contributed upstream to `eslint-plugin-playwright` rather than re-implemented — the first, `no-unnecessary-assertions` for always-passing Locator assertions, is [merged](https://github.com/mskelton/eslint-plugin-playwright/pull/470).

Separately, the upstream contribution roadmap tracks the broader pipeline: **14 PRs merged, 6 in review, and 8 queued**. The queue holds only vetted 1,000+ star candidates — live tables in [upstream contributions](docs/roadmap.md).

## Contributing

Bug reports, false-positive guards, new anti-patterns, and translations are all
welcome. Start with [CONTRIBUTING.md](./CONTRIBUTING.md) for the setup, the
verification gate (`/bin/bash -p scripts/ci/ci-local.sh`), and the frozen-ID / parity
conventions. Deeper cross-agent detail lives in [AGENTS.md](./AGENTS.md).

## License

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha). See [LICENSE](./LICENSE).
