<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills: Agent skills for Playwright and Cypress: generate, review, and debug reliable end-to-end tests." width="100%" />
</div>

<h1 align="center">E2E Skills</h1>

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-4-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#merged-upstream-fixes"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-15-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://github.com/vercel-labs/skills#supported-agents"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="https://skills.sh/voidmatcha/e2e-skills"><img alt="Installs on skills.sh" src="https://img.shields.io/badge/skills.sh_installs-700%2B-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://www.kimi.ai/resources/software-testing-skills"><img alt="Listed in Kimi testing skills" src="https://img.shields.io/badge/%F0%9F%8E%89_listed_in-Kimi_testing_skills-8B5CF6?style=flat-square&labelColor=black"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<strong>English</strong> | <a href="README.ko.md">한국어</a> | <a href="README.ja.md">日本語</a> | <a href="README.zh-cn.md">简体中文</a>
</p>

`e2e-skills` provides four open-source skills for Playwright and Cypress end-to-end (E2E) testing with Claude Code, Codex, and other compatible AI coding agents. Generate Playwright tests, review existing Playwright/Cypress tests and PRs, and debug failed runs.

<p align="center">
  <a href="https://www.kimi.ai/resources/software-testing-skills">
    <img src="docs/assets/kimi-software-testing-skills.png" alt="Kimi's official website listing e2e-skills in AI Software Testing Skills for Smarter QA Automation" width="100%" />
  </a>
  <br />
  <sub><a href="https://www.kimi.ai/resources/software-testing-skills">Featured on Kimi's official website: "AI Software Testing Skills for Smarter QA Automation".</a></sub>
</p>

A passing test can still miss a broken feature. `e2e-skills` helps check whether tests prove the behavior they name.

`e2e-reviewer` uses a code scanner to find possible problems, then reads the test and surrounding code to decide whether they are real. When needed, it can propose changing an assertion or introducing a bug in a separate app copy to check whether the test fails. The reviewer can offer these additional checks; execution requires a trusted local environment and command approval. Existing approval for the same scope remains valid.

`e2e-reviewer` findings led to [15 merged upstream PRs](#merged-upstream-fixes).

| Need | Skill | Result |
| --- | --- | --- |
| Generate new Playwright coverage | [`playwright-test-generator`](skills/playwright-test-generator/SKILL.md) | Playwright tests based on the observed page, with scanner and test-execution results |
| Review Playwright/Cypress tests or PR/diff changes | [`e2e-reviewer`](skills/e2e-reviewer/SKILL.md) | Problems ranked by severity, with evidence and suggested fixes; for changes, whether each problem is new, worsened, or pre-existing |
| Debug a failed Playwright run | [`playwright-debugger`](skills/playwright-debugger/SKILL.md) | Likely cause, supporting evidence, and a suggested fix |
| Debug a failed Cypress run | [`cypress-debugger`](skills/cypress-debugger/SKILL.md) | Likely cause, supporting evidence, and a suggested fix |
| Run a deterministic local scan | `skills/e2e-reviewer/scripts/scan.sh` | Possible code problems without installing the target project’s packages |

Review results use P0/P1/P2 for severity: P0 means a test can pass despite a broken feature, P1 concerns reliability or diagnosis, and P2 concerns maintenance. Debuggers use F1–F15 to label 15 failure categories, such as timing, selectors, and authentication.

**Test generation:** After installation, tell the agent which local project to test. It checks the required setup and guides you through anything missing.

<a id="merged-upstream-fixes"></a>

## Merged upstream fixes

`e2e-reviewer` findings have led to **15 merged upstream PRs**. Every patch is linked below.

The repositories below had **496,650 combined GitHub stars** on 2026-10-20 (GitHub API snapshot).

| Repository | GitHub Stars | PR | Pattern fixed |
| --- | ---: | --- | --- |
| Storybook | ★91.3k | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Missing `await` on Playwright actions; discarded visibility checks |
| code-server | ★79.7k | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | Focused test leak, matcher-less `expect`, discarded visibility read |
| Strapi | ★73.3k | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | Discarded navigation/state checks |
| Ghost | ★55.6k | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise-valued disabled-state assertion |
| Cal.com | ★49.2k | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | Weak assertion patterns in E2E flow |
| Bruno | ★47.7k | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | Assertion and wait reliability fixes |
| Qwik | ★22.1k | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/handle existence checks |
| SvelteKit | ★20.9k | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | Floating Playwright assertions |
| Element Web | ★13.6k | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator null-check style assertions |
| FiftyOne | ★11.2k | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Locator-defined check replaced with a visible duplicate-name error assertion |
| Carbon Design System | ★9.6k | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | Locator truthiness replaced with web-first assertions |
| Rancher Desktop | ★7.4k | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `not.toBeNull()` locator checks replaced with visible WSL integration-name assertions |
| Apache Zeppelin | ★6.7k | [apache/zeppelin#5180](https://github.com/apache/zeppelin/pull/5180) | Always-true assertions and guarded checks that silently skipped |
| MUI X | ★5.9k | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | UI handle checks replaced with state assertions |
| module-federation/core | ★2.7k | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Redundant blanket `uncaught:exception` suppression in a Cypress spec |

## See a false-green test

A **false-green** test passes even when the behavior it is meant to check is broken. The change below checks the visible message instead of merely checking that a Locator object exists.

```diff
- expect(page.getByText('Welcome back')).toBeDefined()
+ await expect(page.getByText('Welcome back')).toBeVisible()
```

<details>
<summary>Full example and scanner output</summary>

This Playwright test looks reasonable but proves only that `Locator` objects were created:

```typescript
import { expect, test } from '@playwright/test';

test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();
  expect(page.locator('.user-badge')).not.toBeNull();
});
```

The bundled scanner catches the false-green assertions without project configuration. Here is the relevant output:

```console
$ /bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests/

[P0][CONFIRMED] #4f Static finding (2 hits)
  "login.spec.ts":5: #4f
  "login.spec.ts":6: #4f

AST-origin total: 2 hit(s); retained findings, not ast-grep execution.

Summary: 2 total hit(s), 2 P0, 0 P1/P2 heuristic, 0 LLM-triage, 0 P0 candidate; 2 AST-origin hit(s), canonical retained findings.
```

Because this run reports P0 findings, `scan.sh` exits 1.

`eslint-plugin-playwright` also flags this shape via `no-unnecessary-assertions`; enable it so commit-time lint owns what it can and the scanner fills the gaps.

**Executable example:** [React optimistic-write proof](examples/react-optimistic-write/README.md) shows why optimistic UI needs request and persistence proof, not just visible state.

</details>

## Talk: Can You Trust E2E Tests That Pass?

Starting with cases where tests pass despite bugs, the talk covers combining lint with LLM review, verification through assertion mutation and app-fault injection, benchmark results, and open-source contributions.

<p align="center">
<a href="https://voidmatcha.art/talks/awskrug-e2e-2026-en">
  <img src="docs/assets/talk-cover-en.png" alt="Talk: Can You Trust E2E Tests That Pass?" width="640" />
</a>
</p>

<p align="center">
  <a href="https://voidmatcha.art/talks/awskrug-e2e-2026-en">Read the slides (English)</a>
</p>

## Install and try it

### Install with your coding agent (recommended)

To include test generation, paste the prompt below into Claude Code or Codex and identify your existing local Playwright project:

```text
Install https://github.com/voidmatcha/e2e-skills using its install.sh for my current host and Playwright project. Run the printed --check command when authorized for that exact command, then verify generator_write_test is available in this session. If a restart is needed, tell me how to resume verification afterward. Report installation, server tools, session tools, and approval separately; do not claim readiness until the required session tools are visible. Respect host trust and tool permissions; do not edit global configuration or restart the host automatically.
```

1. Tell your agent which existing local Playwright project to use. The installer prepares the skills, dedicated agents, official Playwright agents and project MCP configuration, then prints a diagnostic command.
2. Authorize that exact command in a trusted project: `bash install.sh --host codex --project /path/to/playwright-project --check` (use `--host claude` for Claude Code). It skips installation and configuration writes, starts the configured local MCP server and checks `initialize` and `tools/list` only. It executes project code/configuration, without calling tools, opening a browser or running tests.
3. If needed, restart your coding agent yourself, complete host trust/approval, and ask it to resume verification. It must see `generator_write_test` in the active session before proceeding with generation.

The diagnostic verifies server tools only; it cannot establish active session tool availability or approval. A missing tool alone does not prove an approval problem.

After this setup, you do not need to repeat the manual installation steps. Use the [installation guide](docs/installation.md) only for prerequisites, conflicts or manual setup.

**Only reviewing or debugging?** Tell the agent to install the skills and dedicated agents only, without Playwright generator setup. Official Playwright agents and the `playwright-test` MCP server are required for generation, not for reviewing or diagnosing existing Playwright/Cypress tests.

### Install directly with the CLI

Install without a repository clone. Replace `codex` with `claude` for Claude Code; add `--dry-run` to preview changes. See the [installation guide](docs/installation.md#cli-installer) for diagnosis, prerequisites and conflicts.

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.3.0 e2e-skills install --host codex --project /path/to/playwright-project
```

<details>
<summary>Other installation methods: skills.sh and plugins</summary>

### Install skills with skills.sh

For all hosts supported by [skills.sh](https://skills.sh/voidmatcha/e2e-skills), install the four skills with one command:

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all
```

This installs skills only; dedicated agents and Playwright generator setup are separate. To target one host, replace `--all` with `-a <agent>` from the [supported agents](https://github.com/vercel-labs/skills#supported-agents). The CLI version is pinned.

### Claude Code

Alternatively, install the plugin, which includes the four skills and two dedicated agents:

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

For generation, use the all-in-one setup above or follow the [installation guide](docs/installation.md).

### Codex

Alternatively, install the four skills through the plugin marketplace:

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

The plugin does not install the two dedicated agents. For those, run `bash scripts/dev/install-codex-agents.sh` from this checkout. Review and debugging also work inline without them.

For generation, use the all-in-one setup above or follow the [installation guide](docs/installation.md#codex).

</details>

### First prompts

```text
Review my Playwright tests in tests/e2e with e2e-reviewer.
If useful, offer an assertion mutation or app-fault probe as a follow-up.
```

```text
Generate Playwright E2E coverage for apps/web/e2e.
```

```text
Debug the failed Playwright report in playwright-report/.
Debug the failed Cypress report in cypress/reports/.
```

## Supported environments

<details>
<summary>Supported environments and execution requirements</summary>

Use the skills alongside a real application and its E2E suite. Review and debugging support Playwright and Cypress; generation supports Playwright only.

The bundled shell scripts and artifact readers target conventional macOS/Linux layouts with `/bin/bash` and the fixed system executable paths required by their launchers. Windows users need a compatible WSL distribution and artifacts inside the WSL filesystem; native Windows is not supported. NixOS and Nix-, pyenv-, Conda-, or nvm-only tool installations are not universally auto-discovered. Missing trusted tools stop the affected operation; do not bypass that boundary with ambient `PATH` lookup. Resolve skill resources from the actual host-provided skill location, including plugin caches and custom installs, not a guessed home directory.

The generator prepends `thin-rules.md` and safety instructions to the official planner and generator, then runs the reviewer scanner and the new tests. It installs nothing, changes no agent or MCP configuration, and uses no CLI fallback or healer. Missing configuration is reported with setup guidance.

Generation uses the loopback addresses common in local development (`localhost`, `127.0.0.1`, or `::1`). Reuse your approved development server and its existing test backend or mocks. Before browser work, confirm only the services the scenario uses. Writes require isolated test data and cleanup or reset; read-only scenarios need no reset. A new mock server or deployment is not required. Unused API or database services are N/A; shared or production data remain ineligible. Executable navigation and request destinations must resolve to approved origins, matching scheme, hostname and effective port; separately approved loopback API destinations are allowed. Other or unresolved destinations are BLOCKED. These checks do not provide browser-wide origin containment.

Only proven generation errors permit up to two parent-owned repairs. Required outcomes and expected values stay intact; test data is safely cleaned up or reset before repeating writes and origin/scanner gates repeated using the same approved execution method. Product defects, uncertain causes, and remaining failures stay BLOCKED. See the [generator contract](skills/playwright-test-generator/SKILL.md) for the full procedure.

Debugger and probe execution require a trusted project and approval of the exact command, including environment variables and flags. Reports identify skipped checks; mutation and app-fault probes are optional follow-ups, never reported as measured without execution.

Version history and the previous generator workflow are documented in [CHANGELOG.md](CHANGELOG.md).

</details>

## Check whether generated tests catch bugs

The official Playwright agents handle generation. The generator skill then runs the `e2e-reviewer` scanner when installed and fixes P0/P1 findings in at most three passes. It stops if issues remain or scanning is incomplete; otherwise, it runs the approved project test command on new specs only. Missing or skipped checks are reported as incomplete. Request `e2e-reviewer` separately for a semantic review of the generated tests.

Start with a regular `e2e-reviewer` review of whether the tests check the intended behavior. When a specific question needs runtime evidence, add a probe for only that assertion or behavior. You choose where to spend the extra tokens and execution time; mutation and app-fault probes do not run automatically on every review:

- **Assertion mutation:** reverse an assertion in a copy of the test and check whether it fails. This checks that the assertion can fail, not whether the original test catches an app bug.
- **App-fault injection:** introduce a specific bug in a copy of the app and check whether the unchanged test catches it.

For example: “Check whether this test catches a broken save operation.” The reviewer examines the local project and proposes a check. Execution requires a trusted, prepared local environment and your approval of the commands. Results apply to the selected assertion or bug; they do not prove that every bug will be caught.

See the [execution procedure and requirements](skills/e2e-reviewer/references/runtime-probes.md) and [two OSS workflow examples](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/release-readiness-v1/README.md#portable-integration).

Optionally, to have agents also test failure paths when they write tests, paste the [test-authoring memo](docs/test-authoring-memo.md) unchanged into your project's `CLAUDE.md` or `AGENTS.md`. No skill loads it; read its measured effect and limits first. The optional [test-failure policy](docs/test-failure-policy.md) is a separate snippet for the same files that asks agents not to rewrite a failing test without a named requirement.

## Evidence and limits

The [3.0.0 validation record](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/release-readiness-v1/README.md) covers installation, scanner behavior, safety rules, and selected Playwright/Cypress runs, with retained evidence and result scope.

The [October 20 checks](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/release-readiness-v1/README.md#october-20-successor) exercise isolated installation, official-agent/MCP test generation and execution in Claude Code and Codex, and selected Cypress assertion-mutation and app-fault probes. The original generator cohort and later replay remain separately reported.

<details>
<summary>Benchmark scope and model results</summary>

Reviewer results depend on the model: on the same frozen snapshot and 36 public development cases with five repetitions per arm, `gpt-6-sol` passed [v22](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/reviewer-holdout-v22/README.md), `gpt-6.1-sol` passed [v24](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/reviewer-holdout-v24/README.md), and `gpt-6-luna` failed [v23](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/reviewer-holdout-v23/README.md), with all three models completing all 540 calls in each run. These tool-free results measure supplied instructions, not scanner benefit or accuracy on unseen projects. Scores apply only to the reported snapshots. See [benchmark status](benchmarks/STATUS.md) for model-specific scores, protocols, negative findings, and claim boundaries, and [CHANGELOG.md](CHANGELOG.md) for behavior changes.

The entire frozen historical benchmark snapshot, including protocols, inputs, summaries and raw run artifacts, is pinned in [the evidence manifest](benchmarks/external-evidence.json) and available from the [Hugging Face dataset](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks). Use `scripts/dev/fetch-benchmark-evidence.sh --dry-run` to inspect the restore plan before auditing a past score.

</details>

## E2E review catalog

The catalog contains 24 stable Playwright/Cypress test smells. The most common false-green shapes include Locator truthiness, missing assertions, swallowed errors, focused tests, missing authentication, and optimistic UI checks without network proof. See the [full taxonomy and rationale](docs/e2e-test-smells.md).

Some patterns need the application in scope, not just the tests. `#22` optimistic UI is the clearest case: whether a click issues a mutation cannot be decided from a spec, so on a repository that holds tests alone the review reports nothing for it rather than guessing. That is deliberate false-positive control, and it is why the executable example ships with a component.

<details>
<summary>All 24 patterns by severity</summary>

### 24 Patterns Detected: Grouped by Severity

#### P0: Must Fix (silent always-pass)

Tests pass when the feature is broken. No real verification is happening.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 1 | **Name-assertion mismatch** | Name says "status" but only checks `toBeVisible()` | Add assertion for status content, or rename to match actual check |
| 2 | **Missing Then** | Cancel action, verify text restored: but input still visible? | Verify both restored state and dismissed state |
| 3 | **Error swallowing** | `try/catch` in spec, `.catch(() => {})` in POM | Let errors fail; remove silent catch from POM methods |
| 3b | **Cypress `uncaught:exception` suppression** | `cy.on('uncaught:exception', () => false)` blanket-swallows app errors; a `fail` handler that never rethrows passes every failing test | Scope handler to specific known errors; re-throw unknown errors; end `fail` handlers with `throw error` |
| 4 | **Vacuous or retry-weakening assertion** (P0/P1) | P0: invariant predicates and Locator truthiness. P1: weak attachment proof; one-shot values/URL; zero-timeout retry/deadline hazards; unproven absence; assertion loops over possibly empty collections; ARIA snapshots that omit a promised accessible name | Use meaningful bounds and web-first auto-retrying assertions; prove presence before absence, prove collections non-empty before assertion loops, and keep promised accessible names load-bearing |
| 5 | **Bypass patterns** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`; `{ force: true }` without comment | Always assert; move env checks to `beforeEach`; add `// JUSTIFIED:` to force:true |
| 7 | **Focused test leak** | `test.only(...)` committed: CI runs one test, silently skips the rest | Delete `.only`; use `--grep` or `--spec` for local focus |
| 8 | **Missing assertion** | Discarded locator/boolean is the scenario's only verification; `expect(x).toBeVisible;` never calls the matcher | Add `await expect(locator).toBeVisible()`; skip 8a/8b when independent verification/failure evidence already exists |
| 12 | **Missing auth setup** | With no login/`storageState`/auth fixture, a protected-route spec passes because its generic assertion also matches the login/wrong surface | Add `beforeEach` login, configure `storageState`, or use an auth fixture; do not classify a normal auth-caused failure as P0 |

#### P1: Should Fix (poor diagnostics / wastes CI time)

Tests work but mislead developers, waste CI time, or set up future regressions.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 6 | **Raw DOM queries** | `document.querySelector` in `evaluate()` | Use framework locator/query APIs (`locator` / `cy.get`) |
| 9 | **Hard-coded sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | Rely on framework auto-wait; use condition-based waits |
| 10 | **Flaky test patterns** | `items.nth(2)` without comment; `test.describe.serial()`; unscoped accessible-name substring (10c); Cypress async callbacks, assigned `cy` commands, or continued action chains (10d–10f) | Use stable/scoped locators and self-contained tests; keep Cypress work in its command chain, do not assign Chainables as values, and re-query after actions |
| 13 | **Inconsistent POM usage** | Raw actions bypass a source-established same-page POM boundary; existence alone is insufficient | Reuse the proven boundary; do not invent a wrapper merely because a POM exists |
| 14 | **Hardcoded credentials** | `loginPage.login('demo-admin', '<literal-password>')` in test code | Use `process.env.TEST_USER`, Playwright config secrets, or test data fixtures |
| 15 | **Missing `await` on `expect()`** | Async Locator/Page web-first matcher Promise is not sequenced or observed; rejection usually surfaces later with worse attribution | `await` or return the matcher Promise; sync value matchers are excluded |
| 16 | **Missing `await` on action** | Actionability, action ordering, or navigation can race later work; rejection usually surfaces later with worse attribution | `await` or return the action Promise |
| 17 | **Discouraged direct Page selector API** | Selector-based `page.click`, `page.fill`, and related Page actions skip the Locator layer | Use Locator actions for composition, strictness, reuse, and clearer failures |
| 18 | **`expect.soft()` overuse** | Critical soft assertions run before a hard scenario gate, so dependent work continues after a broken prerequisite | Hard-gate the primary state first; use `soft` only for independent details |
| 19 | **Module-level mutable state in test code** | `let seq = 0;` or a mutated `const cache = new Map()` at column 0 in a test utility: persists across tests in a long-lived worker and collides across parallel workers | Drop the counter; derive uniqueness from `Date.now()` + `Math.random().toString(36).slice(2, 8)`, or move state into `test.beforeEach` |
| 20 | **Unmocked real-backend writes** | Signup/checkout spec reaches shared or persistent state with no controlled test boundary | Stub the write or prove a disposable container, rollback fixture, isolated tenant/database, or equivalent controlled backend |
| 22 | **Optimistic UI without call proof** | Like-toggle test asserts `aria-pressed` flip: UI updates optimistically, passes with the POST deleted | Pair UI assertion with `page.waitForRequest()` (armed before the click) or a route-hit flag |

#### P2: Nice to Fix (maintenance / robustness)

Weak but not wrong: addressed when refactoring.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | `clickEdit()` never called; unjustified empty wrapper class; entire spec duplicated by another; unexplained skip | Delete unused members and zombie specs; explain remaining skips and add revisit anchors for long-lived ones; inline single-use helpers only when that clearly removes meaningless indirection |
| 21 | **Manually-captured session-file dependency** | `storageState: 'auth/member.json'` produced only by a manual capture script: absent on CI, silently expires | Regenerate session programmatically (API-login helper or `setup` project); manual files only as a cache with a programmatic fallback |
| 23 | **Fixture ignores render guards** | Liked-tab fixture seeds `liked: false`; the card component `return null`s every item: empty UI looks like infra flake | Read the item component's early returns/filters before seeding; seed fields to pass every guard for the view under test |

</details>

## Failure debugging

Both debuggers use the same stable F1–F15 root-cause taxonomy. Playwright accepts `playwright-report/`, HTML reports, `trace.zip`, screenshots, and bounded GitHub Actions artifacts. Cypress accepts mochawesome or JUnit reports, screenshots, videos, and bounded CI artifacts.

<details>
<summary>All 15 failure categories</summary>

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
| F11 | **Async / Command-Order Race** | Playwright `Promise.all` order or parallel race; Cypress intercept registered after the request, chain-order swap, or visit/request race |
| F12 | **POM / Locator Drift** | DOM structure changed, POM not updated |
| F13 | **Error Swallowing** | `.catch(() => {})` hiding actual failure |
| F14 | **Animation Race** | Content not yet rendered, or a transient element removed before it is observed |
| F15 | **Hydration Race** | Action succeeds but has no effect: SSR page not yet hydrated; fails at the next assertion |

F11 and F12 use unified cross-framework names here. Each debugger reports its framework-specific label for the same stable code.

</details>

The debuggers classify product regressions separately from brittle tests and return evidence plus a concrete fix. They do not diagnose an application or backend without a failing Playwright or Cypress test artifact.

## Standalone scanner

Run the code scanner directly without asking an AI agent. It reports possible problems for review; it does not run your tests or decide whether they prove the intended behavior.

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.3.0 e2e-skills-scan --scan path/to/tests --format text
```

Requires Node.js 22 or newer; the TypeScript parser is bundled. npx downloads the package and its dependencies if they are not already cached. Scanning does not execute tests or project configuration. Use `--format json` for structured output or `--report-file <new-file>` to save a full report without overwriting an existing file.

The reviewer already includes an offline copy of the scanner; no npm installation is needed. By default, this bundled scanner does not download tools or load project configuration. From an installed skill or source checkout, use:

```bash
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

Scanning does not start assertion mutation or fault injection. Those checks require a trusted, prepared project; see the [CLI and probe guide](packages/scanner/README.md).

<details>
<summary>Advanced scanner options and file access</summary>

To run installed project ESLint with its configuration, add `--project-eslint --trust-project` after explicitly trusting the checkout and approving the exact command. This executes project-controlled code with host access; no sandbox or dependency installation is provided. Bundled checks run without that opt-in.

> **Read boundary.**
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> Bundled checks report source beneath the requested path. Framework provenance resolution may also read relative fixture/support imports elsewhere in the containing project.
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->

<!-- README-CONTRACT:SCANNER-EXTENSIONS:START -->
Bundled checks read `.ts`, `.js`, `.tsx`, `.jsx`, `.mts`, `.mjs`, `.cts`, and `.cjs` sources.
<!-- README-CONTRACT:SCANNER-EXTENSIONS:END -->

The default `p0` policy exits 1 for confirmed mechanical P0 findings. Choose `--fail-on p0-candidate` to also gate retained P0 candidates; `any` gates confirmed findings and `none` is report-only. Exit 0 means only that the selected threshold was not reached. Retained candidates and review obligations still need review, including when execution completed with P0=0. Missing inputs, source-integrity or analysis failures produce INCOMPLETE and exit 2. The scanner does not establish complete semantic coverage. See [SECURITY.md](SECURITY.md) for the trust and network boundary.

</details>

## How this differs from ESLint plugins

`eslint-plugin-playwright` and `eslint-plugin-cypress` catch common test-code mistakes. The `e2e-skills` scanner also uses these plugins as an optional checking layer.

This project also contributed the `no-unnecessary-assertions` rule to `eslint-plugin-playwright` ([merged PR #470](https://github.com/mskelton/eslint-plugin-playwright/pull/470)). It catches assertions that check only whether a Locator object exists, rather than application state.

Plugin execution requires your explicit permission; the bundled checks run without it. On top of the plugin rules, `e2e-skills` provides:

- Its own code checks to complement the plugin rules
- Review of test intent and surrounding code for problems that require context

A linter can catch a direct Locator truthiness assertion or missing `await`. It cannot decide whether a test named "shows a duplicate-name error" ever checks the error, whether a protected-route test forgot authentication, or whether an optimistic UI assertion proves the backend request happened. Use the plugins for continuous linting and `e2e-reviewer` for test trustworthiness.

## Frequently asked questions

### How do I find Playwright or Cypress tests that pass but test nothing?

Point `e2e-reviewer` at the relevant spec directory. It combines deterministic candidates with semantic review before returning findings.

<details>
<summary>Review coverage and execution safety details</summary>

<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->
The `e2e-reviewer` skill reviews all 24 catalog patterns with stable IDs and P0/P1/P2 severity. Its standalone `scan.sh` scanner covers only a deterministic mechanical subset. Scanner matches are candidates, not final findings; the skill checks intent and surrounding code before reporting a verdict.

The debuggers classify failures against the stable F1–F15 taxonomy. They execute target-controlled code only after you trust the repository and approve the exact command, including its environment and flags. The generator runs only the reviewer scanner and the project's own test command on the specs it wrote.

For non-public benchmark runs, `--isolation-wrapper` is a required hook, not proof of isolation. Continuous integration (CI) validates the wrapper contract but does not attest filesystem, process, or network isolation.
<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

</details>

### Does this replace Playwright or Cypress test execution?

No. This bundle reviews test quality, generates Playwright coverage, and diagnoses existing failures; it is not a test runner.

### Can it debug tests that fail only in CI?

Yes, when you provide the local report artifacts or a supported GitHub Actions run. The debugger separates environment, timing, selector, data, authentication, and product-regression causes using the F1–F15 taxonomy.

## Detailed documentation

- [How to review AI-generated Playwright and Cypress E2E tests](docs/review-ai-generated-e2e-tests.md)
- [24 Playwright and Cypress E2E test smells](docs/e2e-test-smells.md)
- [Benchmark status and negative results](benchmarks/STATUS.md)
- [Optional test-authoring memo](docs/test-authoring-memo.md) and its [evidence record](docs/benchmarks/test-authoring-memo-v1.md)
- [Optional test-failure policy](docs/test-failure-policy.md) and its [measurement summary](docs/benchmarks/test-failure-policy-v1.md)

<details>
<summary>More references</summary>

- [Self-audit of the rules](docs/rule-self-audit.md)
- [Open-source case studies](docs/case-studies.md)
- [Frozen historical benchmark snapshot (Hugging Face dataset)](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks)
- [External evidence ledger](docs/llm-generated-e2e-test-evidence.md)
- [Historical AI reviewer pilot](docs/ai-reviewer-benchmark.md)
- [Debugger benchmark protocol](docs/debugger-benchmark/README.md)
- [Framework scope](docs/framework-scope.md)
- [Local E2E rule bridge and recommended lint](docs/recommended-lint.md)
- [Roadmap](docs/roadmap.md)
- [Reviewer evidence execution plan and optional Jev experiment](docs/plans/reviewer-evidence-next-steps.md)

</details>

## Contributing

Bug reports, false-positive guards, new anti-patterns, and translations are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for setup and verification requirements. Cross-agent maintenance contracts live in [AGENTS.md](AGENTS.md).

## License

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha). See [LICENSE](LICENSE).

Some benchmark transcripts quote Playwright's own agent definitions (Apache-2.0, Microsoft); see [NOTICE](NOTICE). Playwright is a trademark of Microsoft Corporation; this project is not affiliated with or endorsed by Microsoft.
