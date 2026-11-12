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
  <a href="https://skills.sh/voidmatcha/e2e-skills"><img alt="Installs on skills.sh" src="https://img.shields.io/badge/skills.sh_installs-700%2B-1FC07C?style=flat-square&labelColor=black"></a>
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

`e2e-reviewer` uses a code scanner to find possible problems, then reads the test and surrounding code to decide whether they are real. When needed, it can propose changing an assertion or introducing a bug in a separate app copy to check whether the test fails. The reviewer can offer these additional checks; execution requires a trusted local environment and command approval. Existing approval for the same scope remains valid.

`e2e-reviewer` findings led to [15 merged upstream PRs](#merged-upstream-fixes).

| Need | Skill | Result |
| --- | --- | --- |
| Generate new Playwright coverage | [`playwright-test-generator`](skills/playwright-test-generator/SKILL.md) | Playwright tests based on the observed page, with scanner and test-execution results |
| Review Playwright/Cypress tests or PR/diff changes | [`e2e-reviewer`](skills/e2e-reviewer/SKILL.md) | Problems ranked by severity, with evidence and suggested fixes; for changes, whether each problem is new, worsened, or pre-existing |
| Debug and fix a failing Playwright/Cypress test | [`e2e-debugger`](skills/e2e-debugger/SKILL.md) | The cause split into FLAKY, APP-REGRESSION, TEST-DEFECT-FIXED, ENV or UNCLEAR with evidence; only safe test-file fixes, never product code |
| Run a deterministic local scan | `e2e-skills scan` | Possible code problems without installing the target project’s packages |

Review results use P0/P1/P2 for severity: P0 means a test can pass despite a broken feature, P1 concerns reliability or diagnosis, and P2 concerns maintenance.

**Test generation:** After installation, tell the agent which local project to test. It checks the required setup and guides you through anything missing.

<p align="center">
  <img src="docs/assets/demo.gif" alt="Demo: a refactor drops the POST /api/like call. The UI-only Playwright test still passes because the screen says Liked; the request-aware test fails because the POST never left. Recorded from the runnable example in examples/optimistic-like-demo." width="100%" />
  <br />
  <sub>Watch the <a href="docs/assets/demo.mp4">full-quality video (MP4)</a> or <a href="examples/optimistic-like-demo/README.md">run it yourself</a>.</sub>
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
$ npx --yes --package=@voidmatcha/e2e-skills-scanner@3.5.1 e2e-skills scan tests/ --format text
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

`eslint-plugin-playwright` also flags this shape via `no-unnecessary-assertions`; enable it so commit-time lint owns what it can and the scanner fills the gaps.

**Executable example:** [React optimistic-write proof](examples/react-optimistic-write/README.md) shows why optimistic UI needs request and persistence proof, not just visible state.

**Talk demo:** [Optimistic Like demo](examples/optimistic-like-demo/README.md) is a runnable app with two faults where a passing UI-only test does not prove the write.

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

### 1. Add the free memo

Copy the [memo block](docs/test-authoring-memo.md#the-memo) into your project’s `AGENTS.md` (Codex) or `CLAUDE.md` (Claude Code), keeping existing instructions, or insert it from the project directory (Node.js 22+). Use `--host claude` for `CLAUDE.md` and `--dry-run` to preview; the command writes the memo, not skills:

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.5.1 e2e-skills guidance --host codex --project . --memo
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
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.5.1 e2e-skills scan tests/ --format text --fail-on p0 --allow-incomplete
```

`INCOMPLETE` in the report means some code was not analysed, so exit 0 is not a clean result ([terms](docs/scanner-cli.md#glossary)).

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

`--no-install` uses the Playwright already installed in the project and never downloads another one. In Playwright 1.62 the command loads your `playwright.config.*` and then writes:

- `--loop=claude`: `.claude/agents/playwright-test-planner.md`, `playwright-test-generator.md` and `playwright-test-healer.md`, plus `.mcp.json` declaring the `playwright-test` server (`npx playwright run-test-mcp-server`). An existing `.mcp.json` is replaced, not merged, so back it up first.
- `--loop=codex`: `.codex/agents/playwright_test_planner.toml`, `playwright_test_generator.toml` and `playwright_test_healer.toml`, each declaring the `playwright-test` server inside the agent file. It writes no `.codex/config.toml`.
- Both: `specs/README.md` when there is no `specs/` directory, and a `seed.spec.ts` in your test directory when the project has no seed test.

Then restart your agent in the project. In Claude Code, approve the project's `playwright-test` MCP server. In Codex, also declare `playwright-test` in the trusted project's `.codex/config.toml`, as the [installation guide](docs/installation.md#codex) shows, because the generator needs a session-wide server. Generation is ready once the session shows the `generator_write_test` tool.

Optionally, add the [test-authoring memo](docs/test-authoring-memo.md) to the instruction file your agent loads, so agents also test failure paths. For Claude Code, use your E2E test directory; for Codex, use the repository root, or the E2E test directory if you start Codex there. Add `--dry-run` first to preview:

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.5.1 e2e-skills guidance --host claude --project path/to/e2e-tests --memo
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.5.1 e2e-skills guidance --host codex --project path/to/repository --memo
```

In our dev pilot the memo file made the biggest difference: without it the skills caught fewer failure-path faults (Claude 42/54, Codex 27/54) than with the memo in the root instruction file (53/54, 45/54).

### Scan in CI without installing

The scanner runs without installing the skills, so you can use it locally or in CI:

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.5.1 e2e-skills scan path/to/tests --format text
```

On a real repository the scan often ends `INCOMPLETE` with exit code 2: some code could not be analysed, which does not mean your tests failed. Ask your agent to run the `e2e-reviewer` skill on the same tests; in CI, add `--allow-incomplete` so the exit code follows only the analysed findings. Reading the report: a `P0` (`[P0][CONFIRMED]`) is a mechanically confirmed test that can pass without checking anything; `LLM-TRIAGE` marks an unconfirmed candidate for the `e2e-reviewer` skill to confirm or reject, and a `P0 candidate` (`[P0?]`) is one that would be P0 if confirmed. `provenance-unsupported` means the scanner could not prove where a value such as `page` came from, so that code was not checked. Every other term in the report is defined in the [glossary](docs/scanner-cli.md#glossary).

If `npx` fails with `ETARGET` ("No matching version found ... with a date before"), your `.npmrc` sets `min-release-age`, which hides releases newer than that many days. Lift it for this one pinned command only, without editing `.npmrc`: `npm_config_min_release_age=0 npx --yes --package=@voidmatcha/e2e-skills-scanner@3.5.1 e2e-skills scan path/to/tests --format text`.

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

If a skill does not appear or generation stays not ready, run the read-only diagnostic. It reports installed skill copies (including stale duplicates and leftover copies of the removed debugger skills), official agents and MCP configuration, and next steps, and changes nothing:

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.5.1 e2e-skills doctor --host claude --project /path/to/playwright-project
```

Use `--host codex` for Codex. See the [installation guide](docs/installation.md) for prerequisites, an installer that also prepares the project setup, and manual setup.

## Supported environments

<details>
<summary>Supported environments and execution requirements</summary>

Use the skills alongside a real application and its E2E suite. Review and failing-test fixes support Playwright and Cypress; generation supports Playwright only.

The bundled shell scripts target conventional macOS/Linux layouts with `/bin/bash` and the fixed system executable paths required by their launchers. Windows users need a compatible WSL distribution and projects inside the WSL filesystem; native Windows is not supported. NixOS and Nix-, pyenv-, Conda-, or nvm-only tool installations are not universally auto-discovered. Missing trusted tools stop the affected operation; do not bypass that boundary with ambient `PATH` lookup. Resolve skill resources from the actual host-provided skill location, including plugin caches and custom installs, not a guessed home directory.

The generator prepends `thin-rules.md`, the test-authoring memo and safety instructions to the official planner and generator, then runs the reviewer scanner and the new tests. It installs nothing, changes no agent or MCP configuration, and uses no CLI fallback or healer. Missing configuration is reported with setup guidance and the read-only `e2e-skills doctor`, which also reports the Playwright config's owning package in a monorepo, a missing `e2e-reviewer` and optional lint.

Generation uses the loopback addresses common in local development (`localhost`, `127.0.0.1`, or `::1`). Reuse your approved development server and its existing test backend or mocks. Before browser work, confirm only the services the scenario uses. Writes require isolated test data and cleanup or reset; read-only scenarios need no reset. A new mock server or deployment is not required. Unused API or database services are N/A; shared or production data remain ineligible. Executable navigation and request destinations must resolve to approved origins, matching scheme, hostname and effective port; separately approved loopback API destinations are allowed. Other or unresolved destinations are BLOCKED. These checks do not provide browser-wide origin containment.

Only proven generation errors permit up to two parent-owned repairs. Required outcomes and expected values stay intact; test data is safely cleaned up or reset before repeating writes and origin/scanner gates repeated using the same approved execution method. Product defects, uncertain causes, and remaining failures stay BLOCKED. See the [generator contract](skills/playwright-test-generator/SKILL.md) for the full procedure.

Probe execution requires a trusted project and approval of the exact command, including environment variables and flags. Reports identify skipped checks; mutation and app-fault probes are optional follow-ups, never reported as measured without execution.

Version history and the previous generator workflow are documented in [CHANGELOG.md](CHANGELOG.md).

</details>

## Check whether generated tests catch bugs

The official Playwright agents handle generation. The generator skill then runs the `e2e-reviewer` scanner when installed and fixes P0/P1 findings in at most three passes. It stops if issues remain or scanning is incomplete; otherwise, it runs new specs only with the approved project test command, for approved projects or the confirmed sole project, and reports native passed/failed/skipped counts. Without an approved test command it reports the tests as not run. Missing or skipped checks are reported as incomplete. Request `e2e-reviewer` separately for a semantic review of the generated tests.

Start with a regular `e2e-reviewer` review of whether the tests check the intended behavior. When a specific question needs runtime evidence, add a probe for only that assertion or behavior. You choose where to spend the extra tokens and execution time; mutation and app-fault probes do not run automatically on every review:

- **Assertion mutation:** reverse an assertion in a copy of the test and check whether it fails. This checks that the assertion can fail, not whether the original test catches an app bug.
- **App-fault injection:** introduce a specific bug in a copy of the app and check whether the unchanged test catches it.

For example: “Check whether this test catches a broken save operation.” The reviewer examines the local project and proposes a check. Execution requires a trusted, prepared local environment and your approval of the commands. Results apply to the selected assertion or bug; they do not prove that every bug will be caught.

See the [execution procedure and requirements](skills/e2e-reviewer/references/runtime-probes.md) and [two OSS workflow examples](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/release-readiness-v1/README.md#portable-integration).

Optionally, to have agents also test failure paths when they write tests, paste the [test-authoring memo](docs/test-authoring-memo.md) unchanged into your project's `CLAUDE.md` or `AGENTS.md`. That always-loaded file is its supported place. On some hosts sub-agents do not inherit it, so the generator skill also passes the memo to the official agents it delegates to, and offers the `guidance` command below when the file lacks it, writing nothing without your yes. No other skill loads it; read its measured effect and limits first. The optional [test-failure policy](docs/test-failure-policy.md) is a separate snippet for the same files that asks agents not to rewrite a failing test without a named requirement. Instead of pasting, `e2e-skills guidance --host claude|codex --project PATH --memo --policy` writes either or both unchanged between HTML comment markers, only when asked; see [installation](docs/installation.md#optional-memo-and-failure-policy).

## Evidence and limits

Prevalence: Claude source review found 34/200 repositories (17.0%, 95% CI 12.4–22.8%); independent Claude/Codex agreement confirmed the same location in 32/200. The figures include a [timeout re-audit correction](CHANGELOG.md#swallowed-wait-re-audit); the linked HF snapshot retains the original figures. [Scope and method](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/oss-cases/summary.md) · [Results](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/oss-cases/CODEX-EXPANDED-REPORT.md)

Memo and healer: in a prepared 16-regression study, app-code edits fell from 10/16 with a 136-word memo to 0/16 with memo v5, separately on Claude and Codex. The measured setup requires the memo in the project instruction file. [Setup and limits](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/5ba1d3e97f9dd810cf03ebc3b01dca54b12b4c6f/raw/evidence-20261106b/healer-memo-v5/tab2-results/memov5-heal-20261106.md)

Review cost: roughly $1–2 per repository in the recorded Claude `claude-sonnet-5-5`, high-effort runs (expanded set: $0.58–1.96). [Cost table](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/reviewer-cost-table.md)

These are scoped observations, not general accuracy or causal claims: source judgments are not runtime proof, the sample is not random, and review results depend on model and project. [Data and limits](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/tree/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106)

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

**Replaced in 3.5.** One thin `e2e-debugger` replaces `playwright-debugger` and `cypress-debugger`. In two Claude measurements on 24 real failure cases each, the old debuggers were no more accurate than a plain agent (20/24 vs 22/24; 22/24 vs 23/24 on 3.4.0), at about 1.6–1.7× the cost and 1.8× the runtime. To fix a failing test, ask for it in plain language ("This test is failing, fix it.") and [`e2e-debugger`](skills/e2e-debugger/SKILL.md) loads the failure-handling rules of the [test-authoring memo](docs/test-authoring-memo.md#failure-handling) for that request, so no instruction-file setup is needed. It reruns the test three times with retries off and stops at FLAKY on mixed results; otherwise it decides whether the app or the test is wrong, reports a suspected app regression without changing product code or the test, and repairs only a proven test defect without weakening it, then scans the changed spec and requires three passing reruns. It may hand the repair to the official Playwright healer with the same rules pasted into the prompt. Why: in a [prepared healer study](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/5ba1d3e97f9dd810cf03ebc3b01dca54b12b4c6f/raw/evidence-20261106b/healer-memo-v5/tab2-results/memov5-heal-20261106.md), Claude Sonnet 5.5 and Codex GPT-6 Sol each edited app code in 10/16 regression cases with a 136-word memo and 0/16 with memo v5 (301 words). Both arms placed the memo in the root instruction file, with one run per case; the study does not separate wording from length effects. The skill delivers the failure-handling rules without the instruction file; that delivery has not been measured yet. For a test made green by weakening it, use `e2e-reviewer`. The installer and `e2e-skills doctor` warn about a copy of a removed debugger left by an older install and never delete it; remove it yourself if you no longer use it.

## Standalone scanner

Run the code scanner directly without asking an AI agent. It reports possible problems for review; it does not run your tests or decide whether they prove the intended behavior.

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.5.1 e2e-skills scan path/to/tests --format text
```

Requires Node.js 22 or newer; the TypeScript parser is bundled. npx downloads the package and its dependencies if they are not already cached. The scanner itself does not download tools or load executable project configuration, and it does not execute tests. Use `--format json` for structured output or `--report-file <new-file>` to save a full report without overwriting an existing file.

The reviewer includes the same Node scanner and runs it without a separate npm installation. For its offline launcher and runtime requirements, see the [scanner guide](docs/scanner-cli.md#installed-scanner).

Scanning does not start assertion mutation or fault injection. Those checks require a trusted, prepared project; see the [CLI and probe guide](docs/scanner-cli.md).

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

The default `p0` policy exits 1 for confirmed mechanical P0 findings. Choose `--fail-on p0-candidate` to also gate retained P0 candidates; `any` gates confirmed findings and `none` is report-only. Exit 0 means only that the selected threshold was not reached, not that the tests are sound. The gate fails only on mechanically confirmed findings. These now include one narrow #5a shape, an `if` that gates a test's only assertions, and two narrow #4a shapes, an `expect(x || true)` truthiness check and a Locator `count()` compared as `>= 0` or `> -1`; most other P0 issues still surface as candidates that need the `e2e-reviewer` LLM review step. Retained candidates and review obligations still need review, including when execution completed with P0=0. Missing inputs, source-integrity or analysis failures produce INCOMPLETE and exit 2. For a CI gate that should not stop on unresolved analysis, add `--allow-incomplete`: the exit then reflects the policy on the findings that were analyzed, and the report states how many files and locations were not analyzed and are not checked; missing inputs and source-integrity failures still exit 2. If your tests import `test` or `expect` from a workspace package, add `--trust-module <package>=<path to its source entry inside the scan root>` so that import can be followed. The scanner does not establish complete semantic coverage. See [SECURITY.md](SECURITY.md) for the trust and network boundary.

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
The `e2e-reviewer` skill reviews all 24 catalog patterns with stable IDs and P0/P1/P2 severity. Its standalone `e2e-skills scan` scanner covers only a deterministic mechanical subset. Scanner matches are candidates, not final findings; the skill checks intent and surrounding code before reporting a verdict.

Assertion-mutation and app-fault probes execute target-controlled code only after you trust the repository and approve the exact command, including its environment and flags. The generator runs the reviewer scanner, then executes only the specs it wrote with the approved project test command.

For non-public benchmark runs, `--isolation-wrapper` is a required hook, not proof of isolation. Continuous integration (CI) validates the wrapper contract but does not attest filesystem, process, or network isolation.
<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

</details>

### Does this replace Playwright or Cypress test execution?

No. This bundle reviews test quality, generates Playwright coverage and fixes a failing test with your approved test command; it is not a test runner.

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

The `v3` tag must point to a release containing this action before this example can run; this local change does not create that tag.

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
- [Framework scope](docs/framework-scope.md)
- [Local E2E rule bridge and recommended lint](docs/installation.md#optional-project-lint)
- [Roadmap](docs/roadmap.md)
- [Archived reviewer evidence plan](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/a8279e972f2ae5b7628ac9ec8ccfc4cdac380a1d/releases/v3.3.1/docs-archive-20261028/README.md)

</details>

## Contributing

Bug reports, false-positive guards, new anti-patterns, and translations are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md) for setup and verification requirements. Cross-agent maintenance contracts live in [AGENTS.md](AGENTS.md).

## License

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha). See [LICENSE](LICENSE).

Some benchmark transcripts quote Playwright's own agent definitions (Apache-2.0, Microsoft); see [NOTICE](NOTICE). Playwright is a trademark of Microsoft Corporation; this project is not affiliated with or endorsed by Microsoft.
