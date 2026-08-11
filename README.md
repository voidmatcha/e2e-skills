<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — Agent skills for Playwright and Cypress: generate, review, and debug reliable end-to-end tests." width="100%" />
</div>

# e2e-skills: Find false-green Playwright and Cypress E2E tests

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-4-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#open-source-adoption"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-14-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://agents.md"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<strong>🇺🇸 English</strong> | <a href="README.ko.md">🇰🇷 한국어</a> | <a href="README.ja.md">🇯🇵 日本語</a> | <a href="README.zh-cn.md">🇨🇳 简体中文</a>
</p>

Find Playwright and Cypress E2E tests that pass CI but fail to verify user-visible behavior.

`e2e-skills` gives AI coding agents four focused workflows: generate Playwright coverage, review Playwright/Cypress specs for false-green tests, and debug failed Playwright or Cypress reports. It also includes a deterministic scanner for mechanical silent-pass patterns.

**Why try it:** `e2e-reviewer` findings have contributed to [14 merged upstream PRs](#open-source-adoption), including fixes in Storybook, SvelteKit, code-server, Strapi, Carbon Design System, Ghost, and MUI X.

> In code-server, a committed `it.only` silently disabled eight tests for seven months. One skipped test was already broken while CI remained green.

**Executable example:** [React optimistic-write proof](examples/react-optimistic-write/README.md) shows why optimistic UI needs request and persistence proof, not just visible state.

## See a false-green test

A **false-green** test passes whether or not the behavior it names works. It is not a flaky test: a flaky test fails sometimes, so retry dashboards and flake analytics eventually see it. A false-green test never fails — including when the product is broken — so nothing that watches for tests flipping will ever surface it.

This Playwright test looks reasonable but proves only that `Locator` objects were created:

```typescript
import { expect, test } from '@playwright/test';

test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();
  expect(page.locator('.user-badge')).not.toBeNull();
});
```

A useful test verifies visible behavior and can fail when that behavior breaks:

```diff
- expect(page.getByText('Welcome back')).toBeDefined()
+ await expect(page.getByText('Welcome back')).toBeVisible()
```

The bundled scanner catches the false-green assertions without project configuration:

```console
$ /bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests/

[P0] #4f Locator always-true assertion (truthy/defined/not-null) (2 hits)
  tests/login.spec.ts:6:  expect(page.getByText('Welcome back')).toBeDefined();
  tests/login.spec.ts:8:  expect(page.locator('.user-badge')).not.toBeNull();

Summary: 2 total hit(s), 2 P0
```

`eslint-plugin-playwright` flags this exact shape too, through `no-unnecessary-assertions`. Enable it — a rule that runs on every commit beats a review you have to remember. Every run of the scanner prints which of its findings your lint config should already own, so the two compose instead of competing.

## Prove the test can fail

A well-formed assertion is not a passing test. Lint can tell you `toBeVisible()` is the right matcher; it cannot tell you the test goes red when the feature breaks.

`playwright-test-generator` answers that directly. On a scratch copy the project approves, it inverts the primary assertion (V2) and injects an evidenced product fault (V3), then requires the test to fail at the predicted line with the predicted mismatch. A run that fails for a timeout, a browser crash, or a config error does not count. Anything that cannot be proven safely is reported `CANNOT_VERIFY` rather than guessed.

That is mutation testing scoped to one candidate spec — which is what makes it affordable, because whole-suite mutation on E2E is not.

## Install and try it

### Claude Code

Install from the plugin marketplace:

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

Or install copied skills through the pinned cross-agent CLI:

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

Install the four skills into `~/.agents/skills/`:

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a codex
```

For Codex delegation, `e2e-reviewer`, `playwright-debugger`, and `cypress-debugger` can use native roles or their equivalent inline fallbacks. `playwright-test-generator` has a stricter V6 boundary: without a distinct fresh-context reviewer it reports `CANNOT_VERIFY` and `PARTIAL/BLOCKED`. Source checkouts also include optional native agents under `.codex/agents/`; contributors can see [AGENTS.md](AGENTS.md) for the packaging boundary.

Alternative Codex plugin marketplace path:

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

### Other agents

Install globally for every host supported by the `skills` CLI:

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all
```

To target one host, replace `--all` with `-a <agent>`; see the [supported agents](https://github.com/vercel-labs/skills#supported-agents). The commands pin the reviewed CLI release instead of executing an unreviewed newer version.

### Manual Claude Code checkout

Keep the checkout outside `~/.claude/skills/`, then link each public skill directory:

```bash
git clone https://github.com/voidmatcha/e2e-skills.git "$HOME/.claude/e2e-skills"
mkdir -p "$HOME/.claude/skills"

for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
  ln -s "$HOME/.claude/e2e-skills/skills/$skill" "$HOME/.claude/skills/$skill"
done
```

The links fail rather than replacing existing same-named skills. Run `/skills` in Claude Code and confirm all four names appear.

### First prompts

```text
Review my Playwright tests in tests/e2e with e2e-reviewer.
```

```text
Generate Playwright E2E coverage for apps/web/e2e.
```

```text
Debug the failed Playwright report in playwright-report/.
Debug the failed Cypress report in cypress/reports/.
```

## What you get

| Need | Skill | Result |
| --- | --- | --- |
| Generate new Playwright coverage | `playwright-test-generator` | Explored, approved, reviewed Playwright specs |
| Review passing Playwright/Cypress tests | `e2e-reviewer` | Verified P0/P1/P2 findings with concrete fixes |
| Debug a failed Playwright run | `playwright-debugger` | F1–F15 root cause, evidence, and fix |
| Debug a failed Cypress run | `cypress-debugger` | F1–F15 root cause, evidence, and fix |
| Run a deterministic local scan | `skills/e2e-reviewer/scripts/scan.sh` | Mechanical candidates without target-project packages |

Use this bundle when AI-generated or inherited E2E tests may pass without proving the intended result. Do not use it as a replacement for running the application and its real E2E suite, a general lint preset, or a framework-agnostic test tool. Playwright and Cypress are the supported scope; generation currently targets Playwright only.

A green generated test is not enough: it may assert a `Locator` or `Promise`, observe state unrelated to the behavior named by the test, or leave its primary assertion non-load-bearing. The generator therefore treats every new spec as a candidate until all applicable [V1–V6 verification](skills/playwright-test-generator/verification-rules.md) passes.

On a project-approved scratch copy, V2 can invert the primary assertion and V3 can inject an evidenced product fault. A red run counts only when the predeclared primary assertion fails at the expected location with the expected mismatch; setup, timeout, browser, or infrastructure failures do not kill the mutant. The source candidate remains byte-identical, and a probe that cannot run safely is reported as `CANNOT_VERIFY` rather than guessed.

## How the review works

Generating valid test code is not the same as generating a test that fails when the product is wrong. The workflow separates mechanical detection from semantic judgment:

1. The scanner finds deterministic candidates such as Locator truthiness, focused tests, missing `await`, and blanket error suppression.
2. `e2e-reviewer` reads test names, actions, assertions, helpers, Page Objects, fixtures, and configuration before confirming a finding.
3. Findings use stable pattern IDs and P0/P1/P2 severity so fixes and regressions remain comparable.
4. After a fix, the workflow reruns the scanner and the project's approved E2E or lint command.

A scanner match is a candidate, not a verdict. Cross-file findings such as missing authentication, optimistic UI without call proof, name/assertion mismatch, and fixtures blocked by render guards require semantic review.

## Evidence and limits

The current evidence supports a narrow claim: the project has behavior-backed development evidence and real open-source adoption, but it does not claim generalized reviewer accuracy.

- Browser fault injection completed **36/36 Playwright/Cypress cells**.
- The exact reviewer benchmark covers **12 proven false-green cases and 12 clean guards**; ten fault cases are byte-identical operator mutants.
- Independent robustness gates v4, v5, v7, and v8 failed their preregistered criteria. V6 and v9 were not run, and v10 is frozen but not run.

See [benchmark status](benchmarks/STATUS.md) for scores, failed gates, superseded runs, and claim boundaries. The [research evidence ledger](docs/llm-generated-e2e-test-evidence.md) audits 59 external sources instead of treating adjacent unit-test or custom-agent studies as measurements of this project.

## E2E review catalog

The catalog contains 24 stable Playwright/Cypress test smells. The most common false-green shapes include Locator truthiness, missing assertions, swallowed errors, focused tests, missing authentication, and optimistic UI checks without network proof. See the [full taxonomy and rationale](docs/e2e-test-smells.md).

Some patterns need the application in scope, not just the tests. `#22` optimistic UI is the clearest case: whether a click issues a mutation cannot be decided from a spec, so on a repository that holds tests alone the review reports nothing for it rather than guessing. That is deliberate false-positive control, and it is why the executable example ships with a component.

<details>
<summary>View all 24 patterns by severity</summary>

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

</details>

## Failure debugging

Both debuggers use the same stable F1–F15 root-cause taxonomy. Playwright accepts `playwright-report/`, HTML reports, `trace.zip`, screenshots, and bounded GitHub Actions artifacts. Cypress accepts mochawesome or JUnit reports, screenshots, videos, and bounded CI artifacts.

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


The debuggers classify product regressions separately from brittle tests and return evidence plus a concrete fix. They do not diagnose an application or backend without a failing Playwright or Cypress test artifact.

## Standalone scanner

Run the deterministic mechanical layer directly:

```bash
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

The scanner requires a PCRE2-capable `rg` and Python 3. Python creates and validates NUL-safe candidate identity records so candidate drift or malformed records fail closed; this mandatory bookkeeping is separate from optional Tier 2 AST tooling. It does not execute target-controlled ESLint binaries, plugins, parsers, or configuration by default, and it does not download tools by default. `E2E_SMELL_ALLOW_PROJECT_ESLINT=1` opts a trusted checkout into project ESLint execution; `E2E_SMELL_NO_ESLINT_DOWNLOAD=0` and `E2E_SMELL_NO_AST_GREP_DOWNLOAD=0` separately opt into pinned downloads. Set `E2E_SMELL_DISABLE_AST_GREP=1` when a portability check must ignore preinstalled host binaries.

> **Read boundary.**
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> Bundled checks report source beneath the requested path. Framework provenance resolution may also read relative fixture/support imports elsewhere in the containing project.
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->

<!-- README-CONTRACT:SCANNER-EXTENSIONS:START -->
Bundled checks read `.ts`, `.js`, `.tsx`, `.jsx`, `.mts`, `.mjs`, `.cts`, and `.cjs` sources.
<!-- README-CONTRACT:SCANNER-EXTENSIONS:END -->

Tier 3 is the bundled fallback. Optional ESLint and ast-grep tiers add precision but do not replace semantic review. The scanner exits 2 on infrastructure or filesystem errors rather than reporting a false clean result. See [SECURITY.md](SECURITY.md) for the trust and network boundary.

## How this differs from ESLint plugins

`eslint-plugin-playwright` and `eslint-plugin-cypress` are good every-commit baselines for syntactic rules. `e2e-skills` adds two different layers:

- A secure-default scanner that does not run the target project's lint stack unless explicitly enabled
- Semantic review for findings that need test intent or cross-file context

A linter can catch a direct Locator truthiness assertion or missing `await`. It cannot decide whether a test named “shows a duplicate-name error” ever checks the error, whether a protected-route test forgot authentication, or whether an optimistic UI assertion proves the backend request happened. Use the plugins for continuous linting and `e2e-reviewer` for test trustworthiness.

<a id="open-source-adoption"></a>

## Open-source adoption

`e2e-reviewer` findings have contributed to **14 merged upstream PRs**. These self-selected cases show practical use and let readers inspect the fixes; they are not a representative validation sample or an accuracy estimate.

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

## Frequently asked questions

### How do I find Playwright or Cypress tests that pass but test nothing?

<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->
The `e2e-reviewer` skill reviews all 24 catalog patterns with stable IDs and P0/P1/P2 severity. Its standalone `scan.sh` scanner covers only a deterministic mechanical subset. Scanner matches are candidates, not final findings; the skill checks intent and surrounding code before reporting a verdict.

The debuggers classify failures against the stable F1–F15 taxonomy. They and the generator execute target-controlled code only after you trust the repository and approve the exact command, including its environment and flags.

For non-public benchmark runs, `--isolation-wrapper` is a required hook, not proof of isolation. Continuous integration (CI) validates the wrapper contract but does not attest filesystem, process, or network isolation.
<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

Point `e2e-reviewer` at the relevant spec directory. It combines deterministic candidates with semantic review before returning findings.

### Does this replace Playwright or Cypress test execution?

No. Run the application and its real E2E suite after every change. This bundle reviews test quality, generates Playwright coverage, and diagnoses existing failures; it is not a test runner.

### How do I review AI-generated E2E tests?

Point `e2e-reviewer` at the generated specs before merge. It checks whether each test proves its stated user-visible outcome, then separates deterministic scanner candidates from context-dependent findings.

### Does it support Cypress as well as Playwright?

Review and failure debugging support both frameworks. New-test generation currently supports Playwright only. Cypress debuggers accept mochawesome and JUnit reports.

### Can it debug tests that fail only in CI?

Yes, when you provide the local report artifacts or a supported GitHub Actions run. The debugger separates environment, timing, selector, data, authentication, and product-regression causes using the F1–F15 taxonomy.

### Which AI coding agents are supported?

Claude Code, Codex, and the 55+ hosts supported by the `skills` CLI can load the public `SKILL.md` contracts. Optional host-specific agent files improve delegation where available, but the public skills remain usable without them.

## Detailed documentation

- [24 Playwright and Cypress E2E test smells](docs/e2e-test-smells.md)
- [Self-audit of the rules](docs/rule-self-audit.md)
- [Open-source case studies](docs/case-studies.md)
- [Benchmark status and negative results](benchmarks/STATUS.md)
- [External evidence ledger](docs/llm-generated-e2e-test-evidence.md)
- [Historical AI reviewer benchmark](docs/ai-reviewer-benchmark.md)
- [Debugger benchmark protocol](docs/debugger-benchmark/README.md)
- [Framework scope](docs/framework-scope.md)
- [Roadmap](docs/roadmap.md)

Planned work includes cross-model convention consistency and stronger deterministic detection. No roadmap item is described as shipped before its dedicated verification passes.

## Contributing

Bug reports, false-positive guards, new anti-patterns, and translations are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for setup and verification requirements. Cross-agent maintenance contracts live in [AGENTS.md](AGENTS.md).

## License

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha). See [LICENSE](LICENSE).
