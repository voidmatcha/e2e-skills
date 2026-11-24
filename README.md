<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills: generate Playwright tests, review Playwright and Cypress tests, and fix failing tests with e2e-debugger." width="100%" />
</div>

<h1 align="center">E2E Skills</h1>

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-3-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#merged-upstream-fixes"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-15-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://github.com/vercel-labs/skills#supported-agents"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="https://www.skills.sh/voidmatcha/e2e-skills"><img alt="Installs on skills.sh" src="https://img.shields.io/badge/skills.sh_installs-900%2B-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://www.kimi.ai/resources/software-testing-skills"><img alt="Listed in Kimi testing skills" src="https://img.shields.io/badge/%F0%9F%8E%89_listed_in-Kimi_testing_skills-8B5CF6?style=flat-square&labelColor=black"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<strong>English</strong> | <a href="README.ko.md">한국어</a> | <a href="README.ja.md">日本語</a> | <a href="README.zh-cn.md">简体中文</a>
</p>

`e2e-skills` provides three open-source skills for Playwright and Cypress end-to-end (E2E) testing with Claude Code, Codex, and other compatible AI coding agents. Generate Playwright tests, review existing Playwright/Cypress tests and PRs, and fix a failing test without changing product code.

**Your E2E test is green. Is the feature?** In 34 of 200 popular React repositories, we found a test that can stay green while the feature it names is broken. [Scope and limits](#evidence-and-limits) · [Data](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/oss-cases/summary.md)

`e2e-skills` helps check whether tests prove the behavior they name. Start with [Install and try it](#install-and-try-it): add the free memo, install the skills, then run a 30-second scan.

<p align="center">
  <a href="https://www.kimi.ai/resources/software-testing-skills">
    <img src="docs/assets/kimi-software-testing-skills.png" alt="Kimi's official website listing e2e-skills in AI Software Testing Skills for Smarter QA Automation" width="100%" />
  </a>
  <br />
  <sub><a href="https://www.kimi.ai/resources/software-testing-skills">Featured on Kimi's official website: "AI Software Testing Skills for Smarter QA Automation".</a></sub>
</p>

`e2e-reviewer` uses a code scanner to find possible problems, then reads the test and surrounding code to decide whether they are real. [Experimental runtime probes](#experimental-runtime-proof-opt-in) are available only on explicit request.

| Need | Skill | Result |
| --- | --- | --- |
| Generate new Playwright coverage | [`playwright-test-generator`](skills/playwright-test-generator/SKILL.md) | Playwright tests based on the observed page, with scanner and test-execution results |
| Review Playwright/Cypress tests or PR/diff changes | [`e2e-reviewer`](skills/e2e-reviewer/SKILL.md) | Problems ranked by severity, with evidence and suggested fixes; for changes, whether each problem is new, worsened, or pre-existing |
| Debug and fix a failing Playwright/Cypress test | [`e2e-debugger`](skills/e2e-debugger/SKILL.md) | The cause split into FLAKY, APP-REGRESSION, TEST-DEFECT-FIXED, ENV or UNCLEAR with evidence; only safe test-file fixes, never product code |
| Run a deterministic local scan | `e2e-skills scan` | Possible code problems without installing the target project’s packages |

Review results use P0/P1/P2 for severity: P0 means a test can pass despite a broken feature, P1 concerns reliability or diagnosis, and P2 concerns maintenance.

**Test generation:** After installation, tell the agent which local project to test. It checks the required setup and guides you through anything missing.

https://github.com/user-attachments/assets/4457b99a-f6f4-4023-94d3-cbf3a48387d6

<p align="center">
  <sub>A refactor drops the POST /api/like call. The UI-only Playwright test still passes because the screen says Liked; the request-aware test fails because the POST never left. Recorded from the runnable example in examples/optimistic-like-demo.<br />Download the <a href="docs/assets/demo.mp4">MP4</a> or <a href="docs/assets/demo.gif">GIF</a>, or <a href="examples/optimistic-like-demo/README.md">run it yourself</a>.</sub>
</p>

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

The bundled scanner catches the false-green assertions without project configuration. Here is the text report (without `--format text` the scanner prints the same result as JSON):

```console
$ npx --yes --package=@voidmatcha/e2e-skills-scanner@3.8.0 e2e-skills scan tests/ --format text
Node source scan (canonical report view)
Status: COMPLETE; confirmed P0: 2, P0 candidates: 0, unresolved locations: 0.
Next:
  - Fix 2 confirmed P0 finding(s) ([P0][CONFIRMED] below).
Terms: https://github.com/voidmatcha/e2e-skills/blob/main/docs/scanner-cli.md#glossary

Coverage: BOUNDED; discovery: COMPLETE.
Semantic review: no LLM-triage candidates or source-linked analysis tasks; compatibility contract: DEVELOPMENT.
Review obligations: 0 unresolved location(s) covered by reviewing a retained candidate.
Unresolved analysis: 0 location(s) in 0 file(s), not findings; 0 of them are source-linked review tasks; execution status unchanged.
Project configuration: UNAVAILABLE; declared settings only, runner selection unchanged.
Configuration files: 0; unresolved configuration observations: 1.
Project ESLint effective rule states: NOT EXECUTED; static declarations do not establish active rules.

[P0][CONFIRMED] #4f Static finding (2 hits)
  "login.spec.ts":5: #4f
  "login.spec.ts":6: #4f

AST-origin total: 2 hit(s); retained findings, not ast-grep execution.

Summary: 2 total hit(s), 2 P0, 0 P1/P2 heuristic, 0 LLM-triage, 0 P0 candidate; 2 AST-origin hit(s), canonical retained findings.
```

Because this run reports P0 findings, `e2e-skills scan` exits 1.

**Executable example:** [React optimistic-write proof](examples/react-optimistic-write/README.md) shows why optimistic UI needs request and persistence proof, not just visible state.

</details>

## Talks

<table align="center">
<tr>
<td align="center" valign="top" width="50%">
<a href="https://voidmatcha.art/talks/awskrug-e2e-2026-en"><img src="docs/assets/talk-cover-en.png" alt="Can You Trust E2E Tests That Pass?" width="400" /></a>
<p><b>Can You Trust E2E Tests That Pass?</b><br />AWSKRUG Frontend Meetup</p>
<p><a href="https://voidmatcha.art/talks/awskrug-e2e-2026-en">Read the slides (English)</a></p>
</td>
<td align="center" valign="top" width="50%">
<a href="https://voidmatcha.art/talks/react-day-berlin-2026-en"><img src="https://voidmatcha.art/assets/green-isnt-proof-v260-thumb.jpg" alt="Green Isn’t Proof" width="400" /></a>
<p><b>Green Isn’t Proof</b><br />React Day Berlin 2026</p>
<p><a href="https://voidmatcha.art/talks/react-day-berlin-2026-en">Read the slides (English)</a></p>
</td>
</tr>
</table>

## Install and try it

### 1. Add the free memo

Copy the [memo block](docs/test-authoring-memo.md#the-memo) into your project’s `AGENTS.md` (Codex) or `CLAUDE.md` (Claude Code), keeping existing instructions, or insert it from the project directory (Node.js 22+). Use `--host claude` for `CLAUDE.md` and `--dry-run` to preview; the command writes the memo, not skills:

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.8.0 e2e-skills guidance --host codex --project . --memo
```

### 2. Install the skills

This one command installs the three skills globally for all [supported agents](https://github.com/vercel-labs/skills#supported-agents), including Claude Code and Codex. The CLI version is pinned. To install for one agent only, use `npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a <agent>`, for example `-a claude-code` or `-a codex`. Start a new agent session, then check that `e2e-reviewer`, `e2e-debugger` and `playwright-test-generator` appear in its skill list (for example `/skills` in Claude Code).

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all
```

Review and debugging work right away. Test generation also needs Playwright's official test agents and their `playwright-test` MCP server, set up once per project with `npx playwright init-agents`; see [one-time project setup](#test-generation-one-time-project-setup).

### 3. Scan your tests

A static scan takes about 30 seconds on a typical test directory (Node.js 22+):

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.8.0 e2e-skills scan tests/ --format text --fail-on p0 --allow-incomplete
```

See [scanner results and CI options](#standalone-scanner) before treating exit 0 as a clean result.

### Use it

Ask your agent in plain language:

```text
Review my Playwright tests in tests/e2e with e2e-reviewer.
If useful, offer an assertion mutation or app-fault probe as a follow-up.
```

```text
Generate Playwright E2E coverage for apps/web/e2e.
```

```text
This test is failing, fix it.
```

Review and failing-test fixes work right away. Test generation needs the one-time project setup below.

### Test generation: one-time project setup

`playwright-test-generator` drives Playwright's official test agents through the `playwright-test` MCP server. On first use, if those agents are missing, it stops and tells you to run one command in your Playwright project's root. It never runs the command itself:

```bash
npx --no-install playwright init-agents --loop=claude   # Claude Code
npx --no-install playwright init-agents --loop=codex    # Codex
```

`--no-install` uses the Playwright already installed in the project. The command can write agent definitions, MCP configuration and seed files; review its effects in the [installation guide](docs/installation.md#manual-generator-setup). Then restart the agent and approve the project's `playwright-test` MCP server. Codex also needs a session-wide entry in the trusted project's `.codex/config.toml` ([setup](docs/installation.md#codex)). Generation is ready once the session shows the `generator_write_test` tool.

For instruction-file placement, the optional memo, and its measured limits, see [test-authoring memo](docs/test-authoring-memo.md) and [installation](docs/installation.md#optional-memo-and-failure-policy).

### Alternatives and troubleshooting

Instead of the skills CLI, you can install the same three skills as a plugin. Use one method, not both: plugin skills are namespaced, so both would load every skill twice.

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

The first pair is for Claude Code, the second for Codex. Test generation still needs the project setup above.

If a skill does not appear or generation stays not ready, run the read-only diagnostic for installed skills, official agents and MCP configuration:

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.8.0 e2e-skills doctor --host claude --project /path/to/playwright-project
```

Use `--host codex` for Codex. See the [installation guide](docs/installation.md) for prerequisites, an installer that also prepares the project setup, and manual setup.

## Supported environments

<details>
<summary>Supported environments and execution requirements</summary>

Use the skills alongside a real application and its E2E suite. Review and failing-test fixes support Playwright and Cypress; generation supports Playwright only.

The bundled shell scripts target conventional macOS/Linux layouts with `/bin/bash` and the fixed system executable paths required by their launchers. Windows users need a compatible WSL distribution and projects inside the WSL filesystem; native Windows is not supported. NixOS and Nix-, pyenv-, Conda-, or nvm-only tool installations are not universally auto-discovered. Missing trusted tools stop the affected operation; do not bypass that boundary with ambient `PATH` lookup. Resolve skill resources from the actual host-provided skill location, including plugin caches and custom installs, not a guessed home directory.

Generation requires approved loopback origins and isolated test data for writes; see the [generator safety rules](skills/playwright-test-generator/SKILL.md) and [trust boundaries](SECURITY.md).

Version history is documented in [CHANGELOG.md](CHANGELOG.md).

</details>

## Check whether generated tests catch bugs

After the official Playwright agents generate tests, the skill scans them and runs only the new specs with your approved command; skipped or incomplete checks are reported. A scan alone does not establish behavior coverage: request `e2e-reviewer` for semantic review or explicitly opt into [runtime proof](#experimental-runtime-proof-opt-in) for one behavior. See the [generation gates and repair limits](skills/playwright-test-generator/references/execution-and-report.md) and optional [failure policy](docs/test-failure-policy.md).

## Evidence and limits

Prevalence: Claude source review found 34/200 repositories (17.0%, 95% CI 12.4–22.8%); independent Claude/Codex agreement confirmed the same location in 32/200. The figures include a [timeout re-audit correction](CHANGELOG.md#swallowed-wait-re-audit); the linked HF snapshot retains the original figures. [Scope and method](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/oss-cases/summary.md) · [Results](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/oss-cases/CODEX-EXPANDED-REPORT.md)

Memo and healer: in a prepared 16-regression study, app-code edits fell from 10/16 with a 136-word memo to 0/16 with memo v5, separately on Claude and Codex. The measured setup requires the memo in the project instruction file. [Setup and limits](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/5ba1d3e97f9dd810cf03ebc3b01dca54b12b4c6f/raw/evidence-20261106b/healer-memo-v5/tab2-results/memov5-heal-20261106.md) Development data, not held-out. See also a [separate development replication of the failure-handling note](docs/test-authoring-memo.md#failure-handling).

Review cost: roughly $1–2 per repository in the recorded Claude `claude-sonnet-5-5`, high-effort runs (expanded set: $0.58–1.96). [Cost table](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/reviewer-cost-table.md)

These are scoped observations, not general accuracy or causal claims: source judgments are not runtime proof, the sample is not random, and review results depend on model and project. [Data and limits](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/tree/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106)

<details>
<summary>Benchmark scope and model results</summary>

The [3.0.0 validation record](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/release-readiness-v1/README.md) covers installation, scanner behavior, safety rules, and selected Playwright/Cypress runs, with retained evidence and result scope.

Reviewer development results differ by model and do not establish scanner benefit or accuracy on unseen projects. See [benchmark status](benchmarks/STATUS.md) for the model-specific results and limits.

The entire frozen historical benchmark snapshot, including protocols, inputs, summaries and raw run artifacts, is pinned in [the evidence manifest](benchmarks/external-evidence.json) and available from the [Hugging Face dataset](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks).

</details>

## E2E review catalog

The catalog contains 24 stable Playwright/Cypress test smells. The most common false-green shapes include Locator truthiness, missing assertions, swallowed errors, focused tests, missing authentication, and optimistic UI checks without network proof. See the [full taxonomy and rationale](docs/e2e-test-smells.md).

Some patterns need application code, not just tests. For `#22` optimistic UI, a review needs a test or acceptance contract that promises the write and relevant application code; it does not infer a missing request from the spec alone.

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
| 4 | **Vacuous or retry-weakening assertion** (P0/P1) | P0: invariant predicates and Locator truthiness. P1: weak attachment proof; one-shot values/URL; zero-timeout retry/deadline hazards; unproven absence; assertion loops over possibly empty collections; ARIA snapshots that omit a promised accessible name | Use meaningful bounds and web-first auto-retrying assertions; validate absence using same-locator evidence or exact selector/fixture mapping plus a relevant positive state check, preserve the scenario, prove collections non-empty before assertion loops, and keep promised accessible names load-bearing |
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

Ask in plain language ("This test is failing, fix it.") to use [`e2e-debugger`](skills/e2e-debugger/SKILL.md). It reruns the selected test three times with retries off and reports FLAKY on mixed results. It reports suspected app regressions without changing product code and repairs only proven test defects without weakening assertions. A changed spec must pass its scanner check and three reruns. See the [failure-handling memo](docs/test-authoring-memo.md#failure-handling) for the rules and evidence; use `e2e-reviewer` for a test made green by weakening it.

## Experimental runtime proof (opt in)

`e2e-reviewer` starts with static review. It never offers or runs runtime proof unless you explicitly ask. For example, ask whether a selected green test catches a broken save operation. The experimental workflow can prepare an assertion mutation or a sourced app fault in disposable copies; multiple probes are offered as a batch only after an explicit request. Running target code requires a trusted checkout and approval of the exact commands. A result applies only to the selected test and fault, not the whole suite. Real-project reach and benefit over static review remain unproven. See the [runtime procedure](skills/e2e-reviewer/references/runtime-probes.md) and [release notes](CHANGELOG.md#experimental-reviewer-runtime-proof).

## How this differs from ESLint plugins

`eslint-plugin-playwright` and `eslint-plugin-cypress` catch common test-code mistakes. The `e2e-skills` scanner also uses these plugins as an optional checking layer.

This project also contributed the `no-unnecessary-assertions` rule to `eslint-plugin-playwright` ([mskelton/eslint-plugin-playwright#470](https://github.com/mskelton/eslint-plugin-playwright/pull/470), merged). It catches assertions that check only whether a Locator object exists, rather than application state. It also contributed a Cypress rule with the same name, released in `eslint-plugin-cypress` 7.2.0 ([cypress-io/eslint-plugin-cypress#400](https://github.com/cypress-io/eslint-plugin-cypress/pull/400), merged). It flags an outer Chai assertion on a queued Cypress chain, such as `expect(cy.get('.badge')).to.exist`. This is an assertion-clarity rule: the queued command still fails when the element is missing, so the test does not always pass.

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
The `e2e-reviewer` skill reviews all 24 catalog patterns with stable IDs and P0/P1/P2 severity. Its standalone `e2e-skills scan` scanner covers only a deterministic mechanical subset. The scanner reports mechanically confirmed findings and unconfirmed candidates; the reviewer checks intent and context before its final semantic verdict.

Assertion-mutation and app-fault probes execute target-controlled code only after you trust the repository and approve the exact command, including its environment and flags. The generator runs the reviewer scanner, then executes only the specs it wrote with the approved project test command.

<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

</details>

### Does this replace Playwright or Cypress test execution?

No. This bundle reviews test quality, generates Playwright coverage and fixes a failing test with your approved test command; it is not a test runner.

<a id="scan-in-ci-without-installing"></a>

## Standalone scanner

Run the scanner locally or in CI without installing the skills (Node.js 22+):

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.8.0 e2e-skills scan path/to/tests --format text
```

The reviewer includes the same scanner. It reports mechanically confirmed findings and unconfirmed candidates, does not execute tests, and cannot decide whether they prove the intended behavior. The TypeScript parser is bundled; the bundled scanner does not download tools or load project configuration by default.

`INCOMPLETE` means some code was not analysed, not that tests failed, and normally means exit 2. With `--allow-incomplete`, exit 0 still does not establish a clean result. Retained candidates still need review in Phase 2; `P0=0` does not clear them. Use `--format json` for JSON or `--report-file <new-file>` for a private text report.

When analysis is incomplete, text output groups unresolved causes under **Why incomplete** with counts, affected files and hints. JSON adds `incompleteSummary` (`total` and `groups`) while retaining the full `execution.diagnostics` list. These hints identify code to inspect; they do not mean it was checked. The Action job summary shows the same causes with a display cap.

Executing project ESLint with `--project-eslint --trust-project` requires explicit checkout trust and approval of the exact command. See the [scanner guide](docs/scanner-cli.md) for `--fail-on p0-candidate`, `--allow-incomplete`, `--trust-module`, exit codes, coverage limits and installation troubleshooting, and [SECURITY.md](SECURITY.md) for trust boundaries.

> **Read boundary.**
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> Bundled checks report source beneath the requested path. Framework provenance resolution may also read relative fixture/support imports elsewhere in the containing project.
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->

<!-- README-CONTRACT:SCANNER-EXTENSIONS:START -->
Bundled checks read `.ts`, `.js`, `.tsx`, `.jsx`, `.mts`, `.mjs`, `.cts`, and `.cjs` sources.
<!-- README-CONTRACT:SCANNER-EXTENSIONS:END -->

## Add a static scan to GitHub Actions

The action reports candidates in the job summary and fails on confirmed P0 findings by default. It does not execute the reviewed project. [Inputs and behavior](docs/github-action.md).

```yaml
permissions:
  contents: read
jobs:
  e2e-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - uses: voidmatcha/e2e-skills@v3
        with:
          path: tests/
          fail-on: p0
          allow-incomplete: 'true'
          format: text
```

The action is also listed on the GitHub Marketplace as [E2E Skills static scan](https://github.com/marketplace/actions/e2e-skills-static-scan).

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
- [Framework scope](docs/framework-scope.md)
- [Local E2E rule bridge and recommended lint](docs/installation.md#optional-project-lint)
- [Roadmap](docs/roadmap.md)

</details>

## Contributing

Bug reports, false-positive guards, new anti-patterns, and translations are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for setup and verification requirements. Cross-agent maintenance contracts live in [AGENTS.md](AGENTS.md).

## License

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha). See [LICENSE](LICENSE).

Some benchmark transcripts quote Playwright's own agent definitions (Apache-2.0, Microsoft); see [NOTICE](NOTICE). Playwright is a trademark of Microsoft Corporation; this project is not affiliated with or endorsed by Microsoft.
