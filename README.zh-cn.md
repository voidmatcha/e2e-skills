<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills：生成 Playwright 测试，审查 Playwright 和 Cypress 测试，通过 e2e-debugger 修复失败测试。" width="100%" />
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
<a href="README.md">English</a> | <a href="README.ko.md">한국어</a> | <a href="README.ja.md">日本語</a> | <strong>简体中文</strong>
</p>
<!-- README-CANONICAL-REVISION: sha256=f3348d74f145b6e100a6ee55b16246a3c428514ecbff52e7a8546a9dff2152f7; bytes=exact-README.md-UTF-8; translation-quality=not-attested -->

`e2e-skills` 是面向 Claude Code、Codex 等兼容 AI 编程 agent 的开源 Playwright 和 Cypress E2E 测试 skill 集。三个 skill 分别用于生成 Playwright 测试、审查已有的 Playwright/Cypress 测试与 PR，以及在不改产品代码的前提下修复失败的测试。

**E2E 测试通过了，功能真的正常吗？** 在 200 个热门 React 仓库中，有 34 个存在这样的测试：它所命名的功能已经损坏，测试却仍可能通过。[范围与局限](#evidence-and-limits) · [数据](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/oss-cases/summary.md)

`e2e-skills` 帮助检查测试是否真正验证了名称所描述的行为。请先从[安装并试用](#install-and-try-it)开始：添加免费备忘录，安装 skill，然后运行 30 秒扫描。

<p align="center">
  <a href="https://www.kimi.ai/resources/software-testing-skills">
    <img src="docs/assets/kimi-software-testing-skills.png" alt="Kimi 官方网站的《AI Software Testing Skills for Smarter QA Automation》中收录的 e2e-skills" width="100%" />
  </a>
  <br />
  <sub><a href="https://www.kimi.ai/resources/software-testing-skills">已收录于 Kimi 官方网站的《AI Software Testing Skills for Smarter QA Automation》。</a></sub>
</p>

`e2e-reviewer` 用代码扫描器查找候选问题，再阅读测试和周边代码，判断是否确实存在问题。[实验性运行时验证](#experimental-runtime-proof-opt-in)仅在明确请求时可用。

| 需求 | Skill | 结果 |
| --- | --- | --- |
| 生成新的 Playwright 覆盖 | [`playwright-test-generator`](skills/playwright-test-generator/SKILL.md) | 根据实际页面编写的测试，以及扫描器检查和执行结果 |
| 审查 Playwright/Cypress 测试或 PR/diff 变更 | [`e2e-reviewer`](skills/e2e-reviewer/SKILL.md) | 按严重程度排列的问题、判断依据和修复建议；对变更区分新增、恶化和已有问题 |
| 调试并修复失败的 Playwright/Cypress 测试 | [`e2e-debugger`](skills/e2e-debugger/SKILL.md) | 附证据把原因归为 FLAKY、APP-REGRESSION、TEST-DEFECT-FIXED、ENV 或 UNCLEAR；只做安全的测试文件修复，从不改产品代码 |
| 运行确定性本地扫描 | `e2e-skills scan` | 无需安装目标项目 package 即可发现的候选问题 |

P0/P1/P2 表示审查的严重程度：P0 是功能损坏仍通过的问题，P1 影响可靠性或诊断，P2 涉及维护改进。

**测试生成：** 安装后，告诉 agent 要测试哪个本地项目。它会检查所需配置，并说明还需要哪些准备。

https://github.com/user-attachments/assets/4457b99a-f6f4-4023-94d3-cbf3a48387d6

<p align="center">
  <sub>一次重构删掉了 POST /api/like 调用。由于界面显示 Liked，仅检查 UI 的 Playwright 测试仍然通过；而检查请求的测试因为 POST 从未发出而失败。录制自 examples/optimistic-like-demo 中的可运行示例。<br />下载 <a href="docs/assets/demo.mp4">MP4</a> 或 <a href="docs/assets/demo.gif">GIF</a>，或<a href="examples/optimistic-like-demo/README.md">亲自运行</a>。</sub>
</p>

<a id="merged-upstream-fixes"></a>

## 已合入上游的修复

`e2e-reviewer` 发现的问题促成了 **15 个合入上游的 PR**。下表链接了每个补丁。

以下仓库的 GitHub star 合计 **496,650**，数据来自 2026-10-20 的 GitHub API 快照。

| 仓库 | GitHub Stars | PR | 已修复模式 |
| --- | ---: | --- | --- |
| Storybook | ★91.3k | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Playwright 操作缺失 `await`，且未验证可见性查询的返回值 |
| code-server | ★79.7k | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | Focused test 泄漏、没有 matcher 的 `expect`、被丢弃的可见性读取 |
| Strapi | ★73.3k | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | 被丢弃的导航/状态检查 |
| Ghost | ★55.6k | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise 值的禁用状态断言 |
| Cal.com | ★49.2k | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | E2E 流程中的弱断言模式 |
| Bruno | ★47.7k | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | 断言与等待可靠性修复 |
| Qwik | ★22.1k | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/handle 存在性检查 |
| SvelteKit | ★20.9k | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | 未等待的 Playwright 断言 |
| Element Web | ★13.6k | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator null-check 风格断言 |
| FiftyOne | ★11.2k | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Locator 定义检查改为可见的 duplicate-name 错误断言 |
| Carbon Design System | ★9.6k | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | Locator 真值判断改为 web-first 断言 |
| Rancher Desktop | ★7.4k | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `not.toBeNull()` Locator 检查改为可见的 WSL integration-name 断言 |
| Apache Zeppelin | ★6.7k | [apache/zeppelin#5180](https://github.com/apache/zeppelin/pull/5180) | 恒为真的断言与静默跳过的守卫检查 |
| MUI X | ★5.9k | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | UI handle 检查改为状态断言 |
| module-federation/core | ★2.7k | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Cypress spec 中冗余的 blanket `uncaught:exception` 抑制 |

## 看一个 false-green 测试

**false-green** 指要检查的行为已经损坏，测试却仍然通过。下面的修改检查消息是否真的显示在页面上，而不只是检查 Locator 对象是否存在。

```diff
- expect(page.getByText('Welcome back')).toBeDefined()
+ await expect(page.getByText('Welcome back')).toBeVisible()
```

<details>
<summary>完整示例和 scanner 输出</summary>

这个 Playwright 测试看起来合理，但它只证明 `Locator` 对象被创建了：

```typescript
import { expect, test } from '@playwright/test';

test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();
  expect(page.locator('.user-badge')).not.toBeNull();
});
```

内置扫描器无需项目配置即可捕获这些 false-green 断言。下面是文本报告（不加 `--format text` 时，扫描器以 JSON 输出相同结果）：

```console
$ npx --yes --package=@voidmatcha/e2e-skills-scanner@3.7.0 e2e-skills scan tests/ --format text
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

由于这次运行报告了 P0 发现，`e2e-skills scan` 会以 exit 1 结束。

**可执行示例：** [React 乐观写入证明](examples/react-optimistic-write/README.md) 展示了为什么乐观 UI 需要请求和持久化证明，而不只是可见状态。

</details>

## 演示文稿

<table align="center">
<tr>
<td align="center" valign="top" width="50%">
<a href="https://voidmatcha.art/talks/awskrug-e2e-2026-en"><img src="docs/assets/talk-cover-en.png" alt="通过的 E2E 测试值得信任吗？" width="400" /></a>
<p><b>通过的 E2E 测试值得信任吗？</b><br />AWSKRUG Frontend Meetup</p>
<p><a href="https://voidmatcha.art/talks/awskrug-e2e-2026-en">查看演示文稿（英文）</a></p>
</td>
<td align="center" valign="top" width="50%">
<a href="https://voidmatcha.art/talks/react-day-berlin-2026-en"><img src="https://voidmatcha.art/assets/green-isnt-proof-v260-thumb.jpg" alt="Green Isn’t Proof" width="400" /></a>
<p><b>Green Isn’t Proof</b><br />React Day Berlin 2026</p>
<p><a href="https://voidmatcha.art/talks/react-day-berlin-2026-en">查看演示文稿（英文）</a></p>
</td>
</tr>
</table>

<a id="install-and-try-it"></a>

## 安装并试用

### 1. 添加免费备忘录

将[备忘录正文](docs/test-authoring-memo.md#the-memo)复制到项目的 `AGENTS.md`（Codex）或 `CLAUDE.md`（Claude Code），并保留现有指令；也可以在项目目录中用 CLI 写入（需要 Node.js 22+）。写入 `CLAUDE.md` 时使用 `--host claude`，添加 `--dry-run` 可预览。此命令只写入备忘录，不安装 skill：

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.7.0 e2e-skills guidance --host codex --project . --memo
```

### 2. 安装 skill

这一条命令会为包括 Claude Code 和 Codex 在内的所有[支持的代理](https://github.com/vercel-labs/skills#supported-agents)全局安装三个技能。CLI 版本已固定。如果只想为一个代理安装，请使用 `npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a <agent>`（例如 `-a claude-code` 或 `-a codex`）。开启一个新的代理会话，然后确认技能列表（例如 Claude Code 中的 `/skills`）里出现了 `e2e-reviewer`、`e2e-debugger` 和 `playwright-test-generator`。

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all
```

审查和调试可以直接使用。测试生成还需要 Playwright 官方测试 agents 及其 `playwright-test` MCP 服务器，每个项目用 `npx playwright init-agents` 设置一次；参见[一次性的项目设置](#test-generation-one-time-project-setup)。

### 3. 扫描测试

对典型的测试目录，静态扫描约需 30 秒（需要 Node.js 22+）：

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.7.0 e2e-skills scan tests/ --format text --fail-on p0 --allow-incomplete
```

将退出码 0 视为干净结果之前，请先查看[扫描结果和 CI 选项](#standalone-scanner)。

### 开始使用

用日常语言向代理提出请求即可：

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

审查和修复失败测试可以直接使用。测试生成需要先完成下面一次性的项目设置。

<a id="test-generation-one-time-project-setup"></a>

### 测试生成：一次性的项目设置

`playwright-test-generator` 通过 `playwright-test` MCP 服务器使用 Playwright 官方测试代理。首次使用时，如果缺少这些代理，它会停止生成，并告诉你在 Playwright 项目根目录中运行一条命令。技能本身从不运行这条命令：

```bash
npx --no-install playwright init-agents --loop=claude   # Claude Code
npx --no-install playwright init-agents --loop=codex    # Codex
```

`--no-install` 使用项目中已安装的 Playwright。该命令可能写入代理定义、MCP 配置和 seed 文件；请先在[安装指南](docs/installation.md#manual-generator-setup)中查看其影响。然后重启代理，批准项目的 `playwright-test` MCP 服务器。Codex 还需要在受信任项目的 `.codex/config.toml` 中添加会话级条目（[设置步骤](docs/installation.md#codex)）。会话中出现 `generator_write_test` 工具后即可开始生成。

指令文件的位置、可选备忘录及其测量限制，请参阅[测试编写备忘](docs/test-authoring-memo.md)和[安装指南](docs/installation.md#optional-memo-and-failure-policy)。

### 其他安装方式与故障排查

除了 skills CLI，也可以把同样的三个技能作为插件安装。两种方式只选一种：插件技能带有命名空间，同时安装会让每个技能加载两次。

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

第一组用于 Claude Code，第二组用于 Codex。测试生成仍然需要上面的项目设置。

如果技能没有出现，或生成一直未就绪，请运行只读诊断，检查已安装的技能、官方代理和 MCP 配置：

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.7.0 e2e-skills doctor --host claude --project /path/to/playwright-project
```

Codex 请使用 `--host codex`。前提条件、可同时完成项目设置的安装器以及手动设置，请参阅[安装指南](docs/installation.md)。

## 支持环境

<details>
<summary>查看支持环境和执行条件</summary>

请用这些 skill 补充真实应用及其 E2E suite。审查和修复失败测试支持 Playwright/Cypress，生成仅支持 Playwright。

随附的 shell 脚本面向常规的 macOS/Linux 布局，使用 `/bin/bash` 以及启动器所需的固定系统可执行文件路径。Windows 用户需要兼容的 WSL 发行版，并把项目放在 WSL 文件系统内；不支持原生 Windows。NixOS，以及仅通过 Nix、pyenv、Conda 或 nvm 安装的工具，并不都能被自动发现。缺少受信任的工具时，相关操作会停止；不要通过环境中的 `PATH` 查找绕过这一边界。请从宿主实际提供的 Skill 位置解析 Skill 资源，包括插件缓存和自定义安装位置，而不是猜测的主目录。

生成需要获批的 loopback origin，写入还需要隔离的测试数据；请参阅[生成安全规则](skills/playwright-test-generator/SKILL.md)和[信任边界](SECURITY.md)。

版本历史见 [CHANGELOG.md](CHANGELOG.md)。

</details>

## 检查生成的测试能否发现缺陷

官方 Playwright 代理生成测试后，skill 会扫描这些测试，并仅使用你批准的命令运行新 spec；跳过或未完成的检查都会报告。仅凭扫描不能证明行为覆盖：请让 `e2e-reviewer` 进行语义审查，或明确选择对某项行为进行[运行时验证](#experimental-runtime-proof-opt-in)。另见[生成门禁和修复次数限制](skills/playwright-test-generator/references/execution-and-report.md)及可选的[失败策略](docs/test-failure-policy.md)。

<a id="evidence-and-limits"></a>

## 证据与限制

出现比例：Claude 源码审查确认了 34/200 个仓库（17.0%，95% CI 12.4–22.8%）；Claude 和 Codex 在同一位置均确认问题的仓库为 32/200 个。这些数字已反映 [timeout 复核更正](CHANGELOG.md#swallowed-wait-re-audit)；链接的 HF 快照仍保留原始数字。[范围与方法](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/oss-cases/summary.md) · [结果](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/oss-cases/CODEX-EXPANDED-REPORT.md)

备忘录与 healer：在准备好的 16 个 regression 案例中，使用 136 词 memo 时有 10/16 次修改应用代码，使用 memo v5 时为 0/16 次。Claude 和 Codex 分别测量，结果相同。测量时的配置要求项目指令文件中包含备忘录。[实验条件与局限](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/5ba1d3e97f9dd810cf03ebc3b01dca54b12b4c6f/raw/evidence-20261106b/healer-memo-v5/tab2-results/memov5-heal-20261106.md) 这些是开发数据上的结果，不是留出集评估。另见[失败处理备忘录的独立开发阶段复现实验](docs/test-authoring-memo.md#failure-handling)。

审查费用：记录中的 Claude `claude-sonnet-5-5`、high effort 运行每个仓库约 $1–2（扩展样本范围 $0.58–1.96）。[费用表](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106/reviewer-cost-table.md)

这些数据仅代表所述条件下的观察。源码判断不是实际运行证明，样本并非随机，审查结果取决于模型和项目。[数据与范围](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/tree/770f2de79848c65b80116219ce2d03747a3ae370/raw/oss-prevalence-and-reviewer-20261106)

<details>
<summary>基准测量范围与模型结果</summary>

[3.0.0 验证记录](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/release-readiness-v1/README.md)涵盖安装、扫描器行为、安全规则和部分 Playwright/Cypress 运行，并列出保留的证据和结果的适用范围。

审查器的开发阶段结果因模型而异，不能证明扫描器的效果或在未见项目上的准确率。各模型的结果与限制见[基准状态](benchmarks/STATUS.md)。

包含协议、输入资料、摘要和原始运行资料的完整历史基准冻结 snapshot 由[证据 manifest](benchmarks/external-evidence.json)固定，可从 [Hugging Face 数据集](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks)获取。

</details>

## E2E 审查目录

该目录包含 24 个稳定的 Playwright/Cypress 测试异味。最常见的 false-green 形态包括 Locator 真值判断、缺失断言、吞掉错误、focused tests、缺失认证，以及没有网络调用证明的乐观 UI 检查。参见 [完整分类与依据](docs/e2e-test-smells.md)。

有些模式需要应用代码，而不仅是测试。对于 `#22` 乐观 UI，审查需要承诺写入的测试或验收约定，以及相关应用代码；不会仅凭 spec 推断请求缺失。

<details>
<summary>按严重程度查看全部 24 个模式</summary>

### 检测到的 24 个模式：按严重程度分组

#### P0：必须修复（静默恒绿）

功能损坏时测试仍会通过，因为没有发生真实验证。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 1 | **名称与断言不匹配** | 名称说的是 "status"，但只检查 `toBeVisible()` | 添加 status 内容断言，或重命名为匹配实际检查 |
| 2 | **Then 缺失** | 执行 cancel action，验证文本已恢复，但输入框仍然可见？ | 同时验证已恢复状态和已关闭状态 |
| 3 | **吞掉错误** | spec 中的 `try/catch`，POM 中的 `.catch(() => {})` | 让错误导致失败；从 POM methods 中移除 silent catch |
| 3b | **Cypress `uncaught:exception` 抑制** | `cy.on('uncaught:exception', () => false)` 会忽略所有应用错误；不重新抛出错误的 `fail` handler 也会让失败的测试通过 | 将 handler 限定到特定已知错误；重新抛出未知错误；`fail` handler 必须以 `throw error` 结束 |
| 4 | **空洞或削弱重试的断言** (P0/P1) | P0：不变量谓词和 Locator 真值判断。P1：较弱的挂载证明；一次性读取的值/URL；zero-timeout 重试/截止时间风险；未证明的缺失状态；可能为空的集合上的断言循环；遗漏已承诺 accessible name 的 ARIA snapshots | 使用有意义的边界和 web-first 自动重试断言；通过同一 locator 的证据，或精确的 selector/fixture 映射及相关状态的正向断言验证缺失状态，保持原场景，在断言循环前证明集合非空，并让已承诺的 accessible names 保持 load-bearing |
| 5 | **绕过模式** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`；没有注释的 `{ force: true }` | 始终断言；把环境检查移到 `beforeEach`；给 force:true 添加 `// JUSTIFIED:` |
| 7 | **Focused test 泄漏** | 提交了 `test.only(...)`: CI 只运行一个测试，默默跳过其余测试 | 删除 `.only`；使用 `--grep` 或 `--spec` 做本地聚焦 |
| 8 | **断言缺失** | 被丢弃的 locator/boolean 是该场景唯一的验证，或像 `expect(x).toBeVisible;` 一样未调用 matcher | 添加 `await expect(locator).toBeVisible()`；当独立 verification/failure evidence 已存在时，仅排除 8a/8b |
| 12 | **认证设置缺失** | 缺少 login/`storageState`/auth fixture 时，protected-route spec 会通过，因为泛化断言也匹配 login/wrong surface | 添加 `beforeEach` login，配置 `storageState`，或使用 auth fixture；不要把正常的 auth-caused failure 归类为 P0 |

#### P1：应修复（诊断质量差 / 浪费 CI 时间）

测试能运行，但会误导开发者、浪费 CI 时间，或埋下未来回归。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 6 | **直接 DOM 查询** | `evaluate()` 中的 `document.querySelector` | 使用框架的 locator/query API（`locator` / `cy.get`） |
| 9 | **硬编码等待** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | 依赖框架自动等待；使用基于条件的等待 |
| 10 | **不稳定测试模式** | 没有注释的 `items.nth(2)`；`test.describe.serial()`；未限定作用域的 accessible-name substring（10c）；Cypress async callbacks、被赋值的 `cy` commands，或继续串接的 action chains（10d–10f） | 使用稳定且限定作用域的 locators 和自包含测试；让 Cypress 工作留在其 command chain 中，不要把 Chainables 赋值为普通值，并在 actions 后重新查询 |
| 13 | **POM 使用不一致** | Raw actions bypass a source-established same-page POM boundary; existence alone is insufficient | Reuse the proven boundary; do not invent a wrapper merely because a POM exists |
| 14 | **硬编码凭据** | 测试代码中的 `loginPage.login('demo-admin', '<literal-password>')` | 使用 `process.env.TEST_USER`、Playwright config secrets 或 test data fixtures |
| 15 | **`expect()` 缺失 `await`** | Async Locator/Page web-first matcher Promise 没有被排序或观察；rejection 通常稍后才暴露，归因更差 | `await` 或 return matcher Promise；sync value matchers 被排除 |
| 16 | **action 缺失 `await`** | Actionability、action ordering 或 navigation 可能与后续工作竞态；rejection 通常稍后才暴露，归因更差 | `await` 或 return action Promise |
| 17 | **不建议直接使用 Page selector API** | 基于 selector 的 `page.click`、`page.fill` 及相关 Page actions 跳过 Locator 层 | 使用 Locator actions，以获得组合性、strictness、复用和更清晰的 failure |
| 18 | **过度使用 `expect.soft()`** | 关键 soft assertions 在 hard scenario gate 之前运行，因此前置条件损坏后 dependent work 仍会继续 | 先对主要状态做 hard-gate；仅对独立细节使用 `soft` |
| 19 | **测试代码中的模块级可变状态** | 测试工具中第 0 列的 `let seq = 0;` 或被修改的 `const cache = new Map()`，它会在长生命周期 worker 中跨测试保留，并在并行 workers 间冲突 | 删除 counter；从 `Date.now()` + `Math.random().toString(36).slice(2, 8)` 派生唯一性，或把状态移入 `test.beforeEach` |
| 20 | **未 mock 的真实后端写入** | Signup/checkout spec 触达共享或持久状态，却没有受控测试边界 | Stub 该写入，或证明存在 disposable container、rollback fixture、isolated tenant/database 或等价的受控 backend |
| 22 | **乐观 UI 缺少调用证明** | Like-toggle test 断言 `aria-pressed` 翻转: UI 乐观更新，POST 被删除时仍会通过 | 将 UI assertion 与 `page.waitForRequest()`（点击前 armed）或 route-hit flag 配对 |

#### P2：可择机修复（维护性 / 鲁棒性）

弱但不一定错误；重构时处理。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | `clickEdit()` 从未被调用；无理由的空 wrapper class；整个 spec 被另一个 spec 重复；没有理由的 skip | 删除未使用成员和 zombie specs；为保留的 skip 说明理由，并为长期跳过项设置复查节点；只有在确实能移除无意义间接层时，才内联 single-use helpers |
| 21 | **手动捕获的 session 文件依赖** | `storageState: 'auth/member.json'` 只由手动 capture script 生成；CI 上会缺失，也会悄悄过期 | 以编程方式重新生成 session（API-login helper 或 `setup` project）；manual files 只作为带 programmatic fallback 的 cache |
| 23 | **Fixture 忽略渲染保护条件** | Liked-tab fixture seed 了 `liked: false`；card component 对每个 item 都 `return null`，让空 UI 看起来像 infra flake | 在 seeding 前读取 item component 的 early returns/filters；seed fields 以通过被测 view 的每个 guard |

</details>

## 失败调试

用日常语言提出请求（"This test is failing, fix it."）即可使用 [`e2e-debugger`](skills/e2e-debugger/SKILL.md)。它在关闭重试的情况下重跑选定测试三次，结果有成有败时报告 FLAKY。它不会修改产品代码，只报告疑似应用回归，并且仅修复已证实的测试缺陷，不削弱断言。改动的 spec 必须通过扫描器检查和三次重跑。规则和证据见[失败处理备忘](docs/test-authoring-memo.md#failure-handling)；对于通过削弱断言而变绿的测试，请使用 `e2e-reviewer`。

<a id="experimental-runtime-proof-opt-in"></a>

## 实验性运行时验证（仅在明确请求时）

`e2e-reviewer` 从静态审查开始。没有明确请求时，既不会提出也不会执行运行时验证。例如，可以询问某个已通过的测试能否发现保存操作损坏。实验性流程可以在一次性副本中准备断言变异或有依据的应用故障；只有在明确请求后，才会将多个验证作为一批提出。执行目标代码需要受信任的 checkout，并批准准确的命令。结果只适用于选定的测试和故障，不适用于整套测试。在真实项目中能否成功执行，以及是否优于静态审查，仍未得到证明。请参阅[运行步骤](skills/e2e-reviewer/references/runtime-probes.md)和[发布说明](RELEASE-NOTES-3.7.0.md#experimental-reviewer-runtime-proof)。

## 它与 ESLint plugins 有何不同

`eslint-plugin-playwright` 和 `eslint-plugin-cypress` 用于发现测试代码中的常见错误。`e2e-skills` 扫描器也将这两个插件用作可选检查层。

本项目还向 `eslint-plugin-playwright` 贡献了 `no-unnecessary-assertions` 规则（[mskelton/eslint-plugin-playwright#470](https://github.com/mskelton/eslint-plugin-playwright/pull/470)，已合并）。该规则检测仅检查 Locator 对象是否存在、而非应用状态的断言。本项目也贡献了同名的 Cypress 规则，已进入 `eslint-plugin-cypress` 7.2.0（[cypress-io/eslint-plugin-cypress#400](https://github.com/cypress-io/eslint-plugin-cypress/pull/400)，已合并）。它检测对已排队的 Cypress 命令链施加外层 Chai 断言的代码，例如 `expect(cy.get('.badge')).to.exist`。排队的命令在元素不存在时仍会失败，因此这不是总能通过的测试，而是断言清晰度问题。

执行插件需要用户明确许可；未获许可时仍运行内置检查。在现有插件规则之外，`e2e-skills` 还提供：

- 补充插件规则的自有代码检查
- 针对需要结合测试意图和周边代码判断的问题进行审查

linter 可以捕获直接的 Locator 真值断言或缺失的 `await`。它无法判断名为"shows a duplicate-name error"的测试是否真的检查了该错误，protected-route test 是否忘了认证，或乐观 UI 断言是否证明了 backend request 发生。用 plugins 做持续 linting，用 `e2e-reviewer` 判断测试可信度。

## 常见问题

### 如何找到那些能通过但什么也没测的 Playwright 或 Cypress 测试？

将 `e2e-reviewer` 指向相关 spec directory。它会结合确定性候选项与语义审查，再返回发现。

<details>
<summary>审查范围和执行安全条件详情</summary>

<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->
`e2e-reviewer` Skill 会用稳定 IDs 和 P0/P1/P2 severity 审查目录中的全部 24 个模式。它的独立 `e2e-skills scan` 扫描器只覆盖确定性的机械子集。扫描器命中是候选项，不是最终发现；该 Skill 会先检查意图和周边代码，再报告 verdict。

只有在你信任该仓库并批准精确命令（包括其 environment 和 flags）之后，assertion mutation 和应用 fault probe 才会执行 target-controlled code。generator 先运行审查器扫描器，再用已获批准的项目测试命令，仅执行自己写的 spec。

<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

</details>

### 这会替代 Playwright 或 Cypress 测试执行吗？

不会。这套 bundle 用于审查测试质量、生成 Playwright 覆盖，并用你批准的测试命令修复失败的测试；它不是 test runner。

<a id="scan-in-ci-without-installing"></a>

<a id="standalone-scanner"></a>

## 独立扫描器

无需安装 skill，即可在本地或 CI 中运行扫描器（需要 Node.js 22+）：

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.7.0 e2e-skills scan path/to/tests --format text
```

审查器内置了相同的扫描器。它报告候选，不执行测试，也无法判断测试是否证明了预期行为。TypeScript 解析器已随附；内置扫描器默认不下载工具，也不加载项目配置。

`INCOMPLETE` 表示部分代码未被分析，并不表示测试失败，通常对应退出码 2。即使使用 `--allow-incomplete`，退出码 0 仍不能证明结果干净。保留的候选仍需在 Phase 2 审查；`P0=0` 不能清除这些候选。JSON 报告使用 `--format json`，私有文本报告使用 `--report-file <new-file>`。

使用 `--project-eslint --trust-project` 执行项目 ESLint 需要明确信任 checkout，并批准准确的命令。`--fail-on p0-candidate`、`--allow-incomplete`、`--trust-module`、退出码、覆盖限制和安装故障排查见[扫描器指南](docs/scanner-cli.md)，信任边界见 [SECURITY.md](SECURITY.md)。

> **读取边界。**
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> Bundled checks 会报告请求路径下的 source。Framework provenance resolution 也可能读取同一项目其他位置的相对 fixture/support imports。
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->

<!-- README-CONTRACT:SCANNER-EXTENSIONS:START -->
内置检查读取 `.ts`、`.js`、`.tsx`、`.jsx`、`.mts`、`.mjs`、`.cts`、`.cjs` 源文件。
<!-- README-CONTRACT:SCANNER-EXTENSIONS:END -->

## 在 GitHub Actions 中加入静态扫描

默认将候选问题写入 job summary，仅在存在已确认的 P0 时失败。不执行被审查项目。[输入和行为](docs/github-action.md)。

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

此 Action 也已在 GitHub Marketplace 上架：[E2E Skills static scan](https://github.com/marketplace/actions/e2e-skills-static-scan)。

## 详细文档

- [如何审查 AI 生成的 Playwright 和 Cypress E2E 测试](docs/review-ai-generated-e2e-tests.md)
- [24 个 Playwright 和 Cypress E2E 测试异味](docs/e2e-test-smells.md)
- [基准状态与负面结果](benchmarks/STATUS.md)
- [可选的测试编写备忘](docs/test-authoring-memo.md)及其[证据记录](docs/benchmarks/test-authoring-memo-v1.md)
- [可选的测试失败策略](docs/test-failure-policy.md)及其[测量摘要](docs/benchmarks/test-failure-policy-v1.md)

<details>
<summary>更多参考资料</summary>

- [规则自审](docs/rule-self-audit.md)
- [开源案例研究](docs/case-studies.md)
- [完整历史基准冻结 snapshot（Hugging Face 数据集）](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks)
- [外部证据台账](docs/llm-generated-e2e-test-evidence.md)
- [框架范围](docs/framework-scope.md)
- [本地 E2E 规则桥接与推荐 lint](docs/installation.md#optional-project-lint)
- [路线图](docs/roadmap.md)

</details>

## 贡献

欢迎提交 bug reports、误报防护、新 anti-patterns 和 translations。请从 [CONTRIBUTING.md](CONTRIBUTING.md) 开始了解 setup 和 verification requirements。跨代理维护契约位于 [AGENTS.md](AGENTS.md)。

## 许可证

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha)。参见 [LICENSE](LICENSE)。

部分基准测试记录引用了 Playwright 官方代理定义（Apache-2.0，Microsoft），详见 [NOTICE](NOTICE)。Playwright 是 Microsoft Corporation 的商标，本项目与 Microsoft 没有关联，也未获其认可。
