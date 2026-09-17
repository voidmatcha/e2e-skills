<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — 面向 Playwright 和 Cypress 的 Agent Skills：生成、审查并调试可靠的端到端测试。" width="100%" />
</div>

<h1 align="center">E2E Skills</h1>

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-4-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#merged-upstream-fixes"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-15-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://github.com/vercel-labs/skills#supported-agents"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="https://www.skills.sh/voidmatcha/e2e-skills"><img alt="Installs on skills.sh" src="https://img.shields.io/badge/skills.sh_installs-700%2B-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://www.kimi.ai/resources/software-testing-skills"><img alt="Listed in Kimi testing skills" src="https://img.shields.io/badge/%F0%9F%8E%89_listed_in-Kimi_testing_skills-8B5CF6?style=flat-square&labelColor=black"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<a href="README.md">🇺🇸 English</a> | <a href="README.ko.md">🇰🇷 한국어</a> | <a href="README.ja.md">🇯🇵 日本語</a> | <strong>🇨🇳 简体中文</strong>
</p>
<!-- README-CANONICAL-REVISION: sha256=54ceb11293dcb2af85af10dc6ade05fd828d3502448c33408511dc0d893a902b; bytes=exact-README.md-UTF-8; translation-quality=not-attested -->

`e2e-skills` 为 AI 编程代理提供四个面向 E2E 测试工作的聚焦工作流：生成 Playwright 覆盖、审查现有 spec 或 PR/diff 范围内的测试变更、调试失败的 Playwright 报告，以及调试失败的 Cypress 报告。它还包含一个确定性扫描器，用于发现审查目录中可机械判定的子集。

<p align="center">
  <a href="https://www.kimi.ai/resources/software-testing-skills">
    <img src="docs/assets/kimi-software-testing-skills.png" alt="Kimi 官方网站的《AI Software Testing Skills for Smarter QA Automation》中收录的 e2e-skills" width="100%" />
  </a>
  <br />
  <sub><a href="https://www.kimi.ai/resources/software-testing-skills">已收录于 Kimi 官方网站的《AI Software Testing Skills for Smarter QA Automation》。</a></sub>
</p>

对于人工或 AI 编写的测试，可以把 `e2e-reviewer` 用作独立的质量门禁。它会检查一个通过的测试是否真的证明了标题所描述的行为。

| 需求 | Skill | 结果 |
| --- | --- | --- |
| 生成新的 Playwright 覆盖 | `playwright-test-generator` | 经过探索、批准和审查的 Playwright spec |
| 审查 Playwright/Cypress 测试或 PR/diff 变更 | `e2e-reviewer` | 带有具体修复建议及 introduced/worsened/pre-existing 归属的已验证 P0/P1/P2 发现 |
| 调试失败的 Playwright 运行 | `playwright-debugger` | F1–F15 根本原因、证据和修复 |
| 调试失败的 Cypress 运行 | `cypress-debugger` | F1–F15 根本原因、证据和修复 |
| 运行确定性本地扫描 | `skills/e2e-reviewer/scripts/scan.sh` | 不依赖目标项目 package 的机械候选项 |

生成器先分析覆盖缺口并通过真实浏览器探索，再在场景获批后生成测试并验证每个候选。两个调试器从失败运行的 artifact 入手，返回已分类的根本原因、支持证据和具体修复。

false-green 检测是审查工作流的重要组成部分，但不是整个 bundle 的唯一用途。基于 `e2e-reviewer` 发现的修复已通过 [15 个合入上游的 PR](#merged-upstream-fixes) 合入，其中包括 Storybook、SvelteKit、code-server、Strapi、Carbon Design System、Ghost 和 MUI X。

> 在 code-server 中，一个提交进仓库的 `it.only` 曾默默禁用 8 个测试长达 7 个月。其中一个被跳过的测试早已损坏，而 CI 仍然保持绿色。

**可执行示例：** [React 乐观写入证明](examples/react-optimistic-write/README.md) 展示了为什么乐观 UI 需要请求和持久化证明，而不只是可见状态。

## 如何分工

如果对比按框架划分的助手，分工其实很简单。

| 需求 | 最佳选择 |
| --- | --- |
| 从计划生成 Playwright 覆盖 | [Playwright Test Agents](https://playwright.dev/docs/test-agents) |
| 结合官方文档来编写、解释或接入 Cypress 工作流 | [Cypress AI Skills / Cypress AI Toolkit](https://docs.cypress.io/app/tooling/ai-skills) |
| 审查 false-green 并调试失败报告 | `e2e-skills` |

`e2e-skills` 是对这些官方工具包的补充。它关注测试是否真的证明了名称所写的行为、一次改动是否引入了静默通过，以及失败的 Playwright/Cypress artifact 实际说明了什么。

<a id="merged-upstream-fixes"></a>

## 已合入上游的修复

`e2e-reviewer` 的发现已促成 **15 个合入上游的 PR**。这些自选案例展示了实际使用，也让读者可以检查修复；它们不是代表性验证样本，也不是准确率估计。

以下仓库在 2026-09-16 的 GitHub API 快照中共有 **493,657** 个 star。Star 仅用于说明项目规模与知名度，不代表审查准确率或项目方背书。

| 仓库 | GitHub Stars | PR | 已修复模式 |
| --- | ---: | --- | --- |
| Storybook | ★91.1k | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Playwright 断言缺失 `await` |
| code-server | ★79.3k | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | Focused test 泄漏、没有 matcher 的 `expect`、被丢弃的可见性读取 |
| Strapi | ★73.2k | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | 被丢弃的导航/状态检查 |
| Ghost | ★55.3k | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise 值的禁用状态断言 |
| Cal.com | ★48.5k | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | E2E 流程中的弱断言模式 |
| Bruno | ★47.0k | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | 断言与等待可靠性修复 |
| Qwik | ★22.1k | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/handle 存在性检查 |
| SvelteKit | ★20.8k | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | 未等待的 Playwright 断言 |
| Element Web | ★13.5k | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator null-check 风格断言 |
| FiftyOne | ★11.1k | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Locator 定义检查改为可见的 duplicate-name 错误断言 |
| Carbon Design System | ★9.5k | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | Locator 真值判断改为 web-first 断言 |
| Rancher Desktop | ★7.3k | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `not.toBeNull()` Locator 检查改为可见的 WSL integration-name 断言 |
| Apache Zeppelin | ★6.7k | [apache/zeppelin#5180](https://github.com/apache/zeppelin/pull/5180) | 恒为真的断言与静默跳过的守卫检查 |
| MUI X | ★5.8k | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | UI handle 检查改为状态断言 |
| module-federation/core | ★2.6k | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Cypress spec 中冗余的 blanket `uncaught:exception` 抑制 |

## 看一个 false-green 测试

**false-green**（假绿）测试无论它所声称的行为是否正常都会通过。它不是 flaky 测试：flaky 测试偶尔会失败，因此重试面板和 flake 分析最终能发现它。false-green 测试**即使产品已经损坏也不会失败**，因此仅监控 pass/fail 状态无法暴露它。

这个 Playwright 测试看起来合理，但它只证明 `Locator` 对象被创建了：

```typescript
import { expect, test } from '@playwright/test';

test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();
  expect(page.locator('.user-badge')).not.toBeNull();
});
```

有效测试会验证可见行为，并在行为损坏时失败：

```diff
- expect(page.getByText('Welcome back')).toBeDefined()
+ await expect(page.getByText('Welcome back')).toBeVisible()
```

内置扫描器无需项目配置即可捕获这些 false-green 断言。下面只摘录需要处理的输出：

```console
$ /bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests/

[P0] #4f Locator always-true assertion (truthy/defined/not-null) (2 hits)
  .../tests/login.spec.ts:5:  expect(page.getByText('Welcome back')).toBeDefined();
  .../tests/login.spec.ts:6:  expect(page.locator('.user-badge')).not.toBeNull();

Summary: 2 total hit(s), 2 P0
```

由于这次运行报告了 P0 发现，`scan.sh` 会以 exit 1 结束。

`eslint-plugin-playwright` 也会通过 `no-unnecessary-assertions` 标记这种写法。请启用该规则，让提交时的 lint 负责它能捕获的问题，其余由扫描器补充。

## 证明测试会失败

好的 matcher 还不够；行为损坏时测试必须变红。对每个候选，V2 会反转主断言，V3 会在已批准的临时副本中注入有依据的产品缺陷，并要求它在预定位置以预期的不匹配失败。源候选文件保持 byte-identical；超时、浏览器崩溃和配置错误不算，无法安全验证的探针会报告为 `CANNOT_VERIFY`。

## 安装并试用

### Claude Code

从插件市场安装：

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

或者用固定版本的跨代理 CLI 安装 Skill 副本：

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

把四个 Skill 安装到 `~/.agents/skills/`：

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a codex
```

对于 Codex 委派，`e2e-reviewer`、`playwright-debugger` 和 `cypress-debugger` 可以尝试 native role 委派，也可以使用等价的 inline fallback。`playwright-test-generator` 的 V6 边界更严格：如果没有独立的 fresh-context reviewer，它会报告 `CANNOT_VERIFY` 和 `PARTIAL/BLOCKED`。

**截至 2026 年 9 月，Codex 上的 native role 委派尚未验证能正常工作，不应依赖它。** 实测发现会话内委派会确定性地失败，报出内部错误 `collab spawn failed: no thread with id` —— 这是一个已知的、仍未解决的上游问题（[openai/codex#41474](https://github.com/openai/codex/issues/41474)、[#33672](https://github.com/openai/codex/issues/33672)）。即使没有报错，模型自己声称委派成功的说法也不可信。完整证据见 [`benchmarks/subagent-routing-v1/`](benchmarks/subagent-routing-v1/README.md)。每个 skill 的 inline fallback 都会得出相同结论，所以正确性不受影响——但目前安装这些 named agent 在 Codex 上并不能带来任何实测到的好处。

这里所说的 native roles 就是两个可选子代理 `e2e-finding-verifier` 和 `e2e-failure-classifier`，而 **Codex 无法通过插件安装它们。** Codex 的插件清单没有 agents 字段，agent role 只从 config 层加载，因此 `codex plugin add` 和 `skills` CLI 都不会注册它们。受支持的路径有两条：运行 `bash scripts/dev/install-codex-agents.sh` 将两者全局安装到 `~/.codex/agents/`，或者在本仓库的 checkout 中工作，此时 Codex 会话无需任何安装步骤即可识别 `.codex/agents/`。两者都跳过也没问题，你会得到 inline fallback —— 这是目前在该宿主上可靠的路径。有关打包边界，请参阅 [AGENTS.md](AGENTS.md)。

也可以走 Codex plugin marketplace 路径：

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

### 其他代理

面向 `skills` CLI 支持的所有宿主全局安装：

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all
```

如需只针对一个宿主，把 `--all` 替换为 `-a <agent>`；参见 [支持的代理](https://github.com/vercel-labs/skills#supported-agents)。这些命令固定使用已审查的 CLI release，而不是执行未经审查的新版本。

### 手动 Claude Code checkout

把 checkout 放在 `~/.claude/skills/` 之外，然后链接每个公开 Skill 目录：

```bash
git clone https://github.com/voidmatcha/e2e-skills.git "$HOME/.claude/e2e-skills"
mkdir -p "$HOME/.claude/skills"

skip_link=
for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
  if [ -e "$HOME/.claude/skills/$skill" ] || [ -L "$HOME/.claude/skills/$skill" ]; then
    echo "Already exists, nothing linked: $HOME/.claude/skills/$skill" >&2
    skip_link=1
  fi
done

if [ -z "$skip_link" ]; then
  for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
    ln -s "$HOME/.claude/e2e-skills/skills/$skill" "$HOME/.claude/skills/$skill"
  done
fi
```

如果 `~/.claude/skills/` 下已存在四个名称中的任何一个，命令会打印该路径且不创建任何链接，因此不会替换现有 Skill，也不会在其中嵌套链接。在 Claude Code 中运行 `/skills`，确认四个名称都出现。

### 首次提示词

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

## 范围与限制

这套 bundle 用于生成或审查 E2E 测试，以及分析失败的 Playwright/Cypress 运行。它应与应用及其真实 E2E suite 配合使用，而不是替代它们；它也不是通用 lint preset 或框架无关的测试工具。它支持 Playwright 和 Cypress；新测试生成目前只面向 Playwright。

内置 shell scripts 和 artifact readers 面向 macOS/Linux shell。Windows 用户应通过 WSL 运行，并把 scan/report artifacts 保存在 WSL filesystem 内。

生成的测试仅仅通过还不够：它可能断言的是 `Locator` 或 `Promise` 本身，观察的状态与测试名称所描述的行为无关，或者主要断言根本不影响测试结果。因此，在所有适用的 [V1–V6 验证](skills/playwright-test-generator/verification-rules.md) 通过之前，生成器始终把新 spec 视为候选项。

在生成完整测试集之前，生成器会确认每个场景是否覆盖与现有测试不同的用户风险、E2E 是否是合适的测试层，以及是否有可用于定位失败原因的证据。首次引入测试或处理高风险工作时，会先通过 `e2e-reviewer` 和 V1–V6 验证一个代表性场景，再生成其余测试。在此之前，会用已批准的命令把目标区域的现有测试运行一次，把原本就失败的测试记录下来，而不是算到新测试头上。错误场景必须写明能把该失败原因与其他原因区分开的信号。

测试生成遵循 CLI-first、verification-first 流程。实时探索依次优先使用与项目兼容的 Playwright CLI（`playwright cli`）、单独安装的 `@playwright/cli` 包所提供的命令（`playwright-cli`）、`agent-browser`、运行环境中已经连接的 Playwright MCP，以及受限的 ARIA fallback。已弃用的无作用域 `playwright-cli` 包不会被使用。这些工具只用于探索，不是测试运行器；生成的候选测试仍必须使用仓库原生的 Playwright Test 命令运行。当项目支持 Playwright Test Agents 且已经完成初始化时，它们可以在满足 admission gate 后提供带证据的规划建议；最终实现仍由本生成器负责，V1–V6 验证仍是验收边界。

## 审查如何工作

语法有效的测试代码，不等于会在产品出错时失败的测试。该工作流把机械检测和语义判断分开：

1. 扫描器会发现确定性候选项，例如 Locator 真值判断、focused tests、缺失的 `await` 和 blanket error suppression。
2. `e2e-reviewer` 会先读取测试名称、操作、断言、helper、Page Object、fixture 和配置，再确认一项发现。
3. 发现使用稳定的 pattern IDs 和 P0/P1/P2 严重程度，让修复与回归保持可比较。
4. 修复后，工作流会重新运行扫描器，以及项目已批准的 E2E 或 lint 命令。

扫描器命中只是候选项，不是判定。跨文件发现，例如缺失认证、没有调用证明的乐观 UI、名称/断言不匹配，以及被渲染保护条件阻塞的 fixture，都需要语义审查。

## 证据与限制

当前证据只支持一个窄口径声明：项目拥有行为支持的开发证据和 15 个已合入上游的修复，但不声称具备可泛化的审查准确率。

合并数量现在有了分母。[Field review v1](benchmarks/field-review-v1/README.md) 会扫描该账号提交的、正文中提到本技能的全部 pull request，并按 GitHub 的报告如实记录：在 26 个仓库提交 29 个，合并 16 个，未合并关闭 6 个，仍开启 7 个。改为从 GitHub 生成而非手工维护列表后，发现路线图遗漏了 7 个，其中 2 个是合并，3 个是被拒。正文未提到本技能的 pull request 不会出现在扫描中，因此分母只是下限；上表中已合并的 [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) 就是一例。

这仍然不是精确率。合并意味着维护者接受了补丁，并不证明该指摘的严重级别分类正确；提交署名是可选的，因此未署名的拒绝会把比率往上偏。它真正提供的，是本项目无法控制的裁决。

确定性扫描器单独测量。[Field scan v1](benchmarks/field-scan-v1/README.md) 在固定提交上重新扫描同一组 12 个公开仓库，沿用原有的 30 分钟时限和默认候选数上限。**其中 10/12 个仓库在没有规则被抑制的情况下完成扫描，并报告了 0 个 P0 命中**；另外 2 个扫描超时。结果清单单独列出待审查的候选项，并不能证明召回率或精确率。此前关于 294 个已确认 `#3` 命中的说法源于扫描器的分类缺陷；更正说明及当时的修改前后对比证据均记录在链接页面中。随后，一项采用另行公开协议（取消 30 分钟时限，并将扫描器的限制提高到其文档规定的硬上限）的[完成扩展工作](benchmarks/field-scan-v1-extension/README.md)补齐了最初设计的 12 个样本：此前超时的两个仓库均在没有规则被抑制的情况下正常结束，并报告了 0 个 P0 命中。该扩展工作不会改写已冻结的 v1 台账。

- 最强的独立信号不是分数：始终通过的 Locator 断言模式（`#4f`）已被官方 `eslint-plugin-playwright` 采纳为 `no-unnecessary-assertions` 规则（已合并的 pull request 见[路线图](docs/roadmap.md)）。这是一位与本项目没有利害关系的外部维护者接受了该规则定义。同时这也意味着当前的 lint 已能检出这种形状，因此本项目不再将其作为自己的成果来声称。
- `docs/rule-self-audit.md` 记录了由两个模型系列进行的对抗性审计在本项目**自身** P0 规则中发现的缺陷，其中包括单一审查者会放行的规则。
- 浏览器故障注入已完成 **12 个故障算子与 3 种预期结果组合形成的全部 36 个 Playwright/Cypress 单元**。这是对测试台自身的检验：应用、健壮的测试、注入的故障和脆弱的测试都由本仓库编写，因此它只能说明检测器按设计触发，并不代表可以泛化。
- [Healer perturbation v1](benchmarks/healer-perturbation-v1/README.md) 已完成**全部 30 个冻结的 Codex 单元**并返回 `REJECT`：带保护约束的官方 healer prompt 与本仓库提议的 Step 7 工作流，都削弱了全部 3 个不可修复的诚实性对照项。该结果否决了把这两条 healer 路径作为安全默认值；它没有测量 Claude、通用 healer 质量或审查准确率，也没有修改产品指令。
- Exact reviewer benchmark 覆盖 **12 个已证实的 false-green cases 和 12 个 clean guards**；其中 10 个 fault cases 是 byte-identical operator mutants。
- Independent product-review robustness gates v4、v5、v7、v8 和 v11 未达到其预注册标准。v6 和 v9 未运行，v10 在 3 次尝试中仅运行 1 次后，被复用其冻结评审输入的 v11 取代；v1 至 v11 仅作为既有的 robustness evidence 保留，不是当前的 release gates。
- Debugger protocol 提供可重放的 30-case synthetic corpus，但不声称已独立建立调试器准确率。

查看 [基准状态](benchmarks/STATUS.md) 了解分数、失败的 gates、被取代的 runs 和声明边界。[研究证据台账](docs/llm-generated-e2e-test-evidence.md) 审计了 62 个外部来源，避免把相邻的 unit-test 或 custom-agent 研究当作本项目的测量结果。

## E2E 审查目录

该目录包含 24 个稳定的 Playwright/Cypress 测试异味。最常见的 false-green 形态包括 Locator 真值判断、缺失断言、吞掉错误、focused tests、缺失认证，以及没有网络调用证明的乐观 UI 检查。参见 [完整分类与依据](docs/e2e-test-smells.md)。

有些模式需要应用代码在审查范围内，而不仅仅是测试。`#22` 乐观 UI 是最明显的例子：点击是否真的发出 mutation，无法仅从 spec 判断，因此在只有测试的仓库中，审查不会猜测，而是不报告。这是有意的误报控制，也是可执行示例附带组件的原因。

### 检测到的 24 个模式：按严重程度分组

#### P0：必须修复（静默恒绿）

功能损坏时测试仍会通过，因为没有发生真实验证。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 1 | **名称与断言不匹配** | 名称说的是 "status"，但只检查 `toBeVisible()` | 添加 status 内容断言，或重命名为匹配实际检查 |
| 2 | **Then 缺失** | 执行 cancel action，验证文本已恢复，但输入框仍然可见？ | 同时验证已恢复状态和已关闭状态 |
| 3 | **吞掉错误** | spec 中的 `try/catch`，POM 中的 `.catch(() => {})` | 让错误导致失败；从 POM methods 中移除 silent catch |
| 3b | **Cypress `uncaught:exception` 抑制** | `cy.on('uncaught:exception', () => false)` blanket-swallows app errors | 将 handler 限定到特定已知错误；重新抛出未知错误 |
| 4 | **空洞或削弱重试的断言** (P0/P1) | P0：不变量谓词和 Locator 真值判断。P1：较弱的挂载证明；一次性读取的值/URL；zero-timeout 重试/截止时间风险；未证明的缺失状态；可能为空的集合上的断言循环；遗漏已承诺 accessible name 的 ARIA snapshots | 使用有意义的边界和 web-first 自动重试断言；先证明存在，再证明不存在，在断言循环前证明集合非空，并让已承诺的 accessible names 保持 load-bearing |
| 5 | **绕过模式** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`；没有注释的 `{ force: true }` | 始终断言；把环境检查移到 `beforeEach`；给 force:true 添加 `// JUSTIFIED:` |
| 7 | **Focused test 泄漏** | 提交了 `test.only(...)` — CI 只运行一个测试，默默跳过其余测试 | 删除 `.only`；使用 `--grep` 或 `--spec` 做本地聚焦 |
| 8 | **断言缺失** | 被丢弃的 locator/boolean 是该场景唯一的验证 | 添加 `await expect(locator).toBeVisible()`；当独立 verification/failure evidence 已存在时跳过 #8 |
| 12 | **认证设置缺失** | 缺少 login/`storageState`/auth fixture 时，protected-route spec 会通过，因为泛化断言也匹配 login/wrong surface | 添加 `beforeEach` login，配置 `storageState`，或使用 auth fixture；不要把正常的 auth-caused failure 归类为 P0 |

#### P1：应修复（诊断质量差 / 浪费 CI 时间）

测试能运行，但会误导开发者、浪费 CI 时间，或埋下未来回归。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 6 | **直接 DOM 查询** | `evaluate()` 中的 `document.querySelector` | 使用框架的 locator/query API（`locator` / `cy.get`） |
| 9 | **硬编码等待** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | 依赖框架自动等待；使用基于条件的等待 |
| 10 | **不稳定测试模式** | 没有注释的 `items.nth(2)`；`test.describe.serial()`；未限定作用域的 accessible-name substring（10c）；Cypress async callbacks、被赋值的 `cy` commands，或继续串接的 action chains（10d–10f） | 使用稳定且限定作用域的 locators 和自包含测试；让 Cypress 工作留在其 command chain 中，不要把 Chainables 赋值为普通值，并在 actions 后重新查询 |
| 13 | **POM 使用不一致** | 已导入 POM，但 spec 对 POM-owned actions 使用 raw `page.fill`/`page.click` | 将所有交互路由到 POM，使 UI 变化只需在一个地方更新 |
| 14 | **硬编码凭据** | 测试代码中的 `loginPage.login('demo-admin', '<literal-password>')` | 使用 `process.env.TEST_USER`、Playwright config secrets 或 test data fixtures |
| 15 | **`expect()` 缺失 `await`** | Async Locator/Page web-first matcher Promise 没有被排序或观察；rejection 通常稍后才暴露，归因更差 | `await` 或 return matcher Promise；sync value matchers 被排除 |
| 16 | **action 缺失 `await`** | Actionability、action ordering 或 navigation 可能与后续工作竞态；rejection 通常稍后才暴露，归因更差 | `await` 或 return action Promise |
| 17 | **不建议直接使用 Page selector API** | 基于 selector 的 `page.click`、`page.fill` 及相关 Page actions 跳过 Locator 层 | 使用 Locator actions，以获得组合性、strictness、复用和更清晰的 failure |
| 18 | **过度使用 `expect.soft()`** | 关键 soft assertions 在 hard scenario gate 之前运行，因此前置条件损坏后 dependent work 仍会继续 | 先对主要状态做 hard-gate；仅对独立细节使用 `soft` |
| 19 | **测试代码中的模块级可变状态** | 测试工具中第 0 列的 `let seq = 0;` 或被修改的 `const cache = new Map()`，它会在长生命周期 worker 中跨测试保留，并在并行 workers 间冲突 | 删除 counter；从 `Date.now()` + `Math.random().toString(36).slice(2, 8)` 派生唯一性，或把状态移入 `test.beforeEach` |
| 20 | **未 mock 的真实后端写入** | Signup/checkout spec 触达共享或持久状态，却没有受控测试边界 | Stub 该写入，或证明存在 disposable container、rollback fixture、isolated tenant/database 或等价的受控 backend |
| 22 | **乐观 UI 缺少调用证明** | Like-toggle test 断言 `aria-pressed` 翻转 — UI 乐观更新，POST 被删除时仍会通过 | 将 UI assertion 与 `page.waitForRequest()`（点击前 armed）或 route-hit flag 配对 |

#### P2：可择机修复（维护性 / 鲁棒性）

弱但不一定错误；重构时处理。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | `clickEdit()` 从未被调用；无理由的空 wrapper class；整个 spec 被另一个 spec 重复；没有理由或复查期限的 skip | 删除未使用成员和 zombie specs；为保留的 skip 写明理由和期限；只有在确实能移除无意义间接层时，才内联 single-use helpers |
| 21 | **手动捕获的 session 文件依赖** | `storageState: 'auth/member.json'` 只由手动 capture script 生成；CI 上会缺失，也会悄悄过期 | 以编程方式重新生成 session（API-login helper 或 `setup` project）；manual files 只作为带 programmatic fallback 的 cache |
| 23 | **Fixture 忽略渲染保护条件** | Liked-tab fixture seed 了 `liked: false`；card component 对每个 item 都 `return null`，让空 UI 看起来像 infra flake | 在 seeding 前读取 item component 的 early returns/filters；seed fields 以通过被测 view 的每个 guard |

## 失败调试

两个调试器使用同一套稳定的 F1–F15 根本原因分类。Playwright 接受 `playwright-report/`、HTML reports、`trace.zip`、screenshots 和有界的 GitHub Actions artifacts。Cypress 接受 mochawesome 或 JUnit reports、screenshots、videos 和有界 CI artifacts。

| # | 类别 | 信号 |
|---|----------|---------|
| F1 | **不稳定 / 时序** | `TimeoutError`，重试后通过 |
| F2 | **Selector 失效** | `locator not found`，strict mode violation |
| F3 | **网络依赖** | `net::ERR_*`，意外的 API 响应 |
| F4 | **断言不匹配** | `Expected X to equal Y`，实际值/期望值反置 |
| F5 | **Then 缺失** | 动作已完成，但错误状态仍然存在 |
| F6 | **条件分支缺失** | 元素有条件出现，但断言总是运行 |
| F7 | **测试隔离失败** | 单独运行通过，suite 中失败 |
| F8 | **环境不匹配** | 只在 CI vs local 出现；viewport、OS、timezone |
| F9 | **数据依赖** | 缺失 seed data，hardcoded IDs |
| F10 | **认证 / Session** | 会话过期，role-based UI 未渲染 |
| F11 | **异步/命令顺序竞态** | Playwright 的 `Promise.all` 顺序或并行竞态；Cypress 在请求发出后注册 intercept、命令链顺序颠倒或 visit/request 竞态 |
| F12 | **POM / Locator 漂移** | DOM 结构已变化，POM 未更新 |
| F13 | **吞掉错误** | `.catch(() => {})` 隐藏实际 failure |
| F14 | **动画竞态** | 内容尚未渲染，或 transient element 在被观察前移除 |
| F15 | **Hydration 竞态** | Action 成功但没有效果：SSR page 尚未 hydrated；在下一个 assertion 失败 |

这里的 F11 和 F12 使用跨框架的统一名称。每个 `debugger` 会为同一个稳定代码报告对应框架的专用名称。


调试器会把产品回归与脆弱测试分开分类，并返回证据和具体修复。没有失败的 Playwright 或 Cypress 测试 artifact 时，它们不会诊断应用或 backend。

## 独立扫描器

直接运行确定性的机械层：

```bash
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

扫描器需要支持 PCRE2 的 `rg` 和 Python 3。Python 会创建并校验 NUL-safe 候选标识记录，因此候选漂移或损坏的记录会 fail closed；这项必需的记录工作与可选的 Tier 2 AST 工具无关。默认情况下，它不会执行目标项目控制的 ESLint binaries、plugins、parsers 或 configuration，也不会下载工具。`E2E_SMELL_ALLOW_PROJECT_ESLINT=1` 会让可信 checkout 进入项目 ESLint 执行；`E2E_SMELL_NO_ESLINT_DOWNLOAD=0` 和 `E2E_SMELL_NO_AST_GREP_DOWNLOAD=0` 会分别选择启用 pinned downloads。当 portability check 必须忽略 host 预装 binaries 时，设置 `E2E_SMELL_DISABLE_AST_GREP=1`。

> **读取边界。**
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> Bundled checks 会报告请求路径下的 source。Framework provenance resolution 也可能读取同一项目其他位置的相对 fixture/support imports。
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->

<!-- README-CONTRACT:SCANNER-EXTENSIONS:START -->
内置检查读取 `.ts`、`.js`、`.tsx`、`.jsx`、`.mts`、`.mjs`、`.cts`、`.cjs` 源文件。
<!-- README-CONTRACT:SCANNER-EXTENSIONS:END -->

Tier 3 是内置 fallback。可选的 ESLint 和 ast-grep tiers 会提高精度，但不会替代语义审查。扫描器遇到基础设施或文件系统错误时会以 2 退出，而不是报告虚假的 clean 结果。参见 [SECURITY.md](SECURITY.md) 了解 trust 和 network boundary。

## 它与 ESLint plugins 有何不同

`eslint-plugin-playwright` 和 `eslint-plugin-cypress` 是很好的每次提交基线，用于 syntactic rules。`e2e-skills` 另外提供两层能力：

- 默认安全的扫描器，除非显式启用，否则不会运行目标项目的 lint stack
- 对需要测试意图或跨文件上下文的发现做语义审查

linter 可以捕获直接的 Locator 真值断言或缺失的 `await`。它无法判断名为“shows a duplicate-name error”的测试是否真的检查了该错误，protected-route test 是否忘了认证，或乐观 UI 断言是否证明了 backend request 发生。用 plugins 做持续 linting，用 `e2e-reviewer` 判断测试可信度。

## 常见问题

### 如何找到那些能通过但什么也没测的 Playwright 或 Cypress 测试？

<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->
`e2e-reviewer` Skill 会用稳定 IDs 和 P0/P1/P2 severity 审查目录中的全部 24 个模式。它的独立 `scan.sh` 扫描器只覆盖确定性的机械子集。扫描器命中是候选项，不是最终发现；该 Skill 会先检查意图和周边代码，再报告 verdict。

debuggers 会按稳定的 F1–F15 taxonomy 对 failures 分类。只有在你信任该仓库并批准精确命令（包括其 environment 和 flags）之后，它们和 generator 才会执行 target-controlled code。

对于非公开 benchmark runs，`--isolation-wrapper` 是必需 hook，而不是 isolation proof。Continuous integration (CI) 会验证 wrapper contract，但不会证明 filesystem、process 或 network isolation。
<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

将 `e2e-reviewer` 指向相关 spec directory。它会结合确定性候选项与语义审查，再返回发现。

### 这会替代 Playwright 或 Cypress 测试执行吗？

不会。每次修改后都要运行应用及其真实 E2E suite。这套 bundle 用于审查测试质量、生成 Playwright 覆盖，并诊断已有失败；它不是 test runner。

### 如何在合并前审查 AI 生成的 Playwright 或 Cypress 测试？

合并前，将生成的 spec 交给 `e2e-reviewer`。它会检查每个测试是否真正证明了名称所描述的用户可见结果，捕捉 false-green 风险，并区分确定性的扫描候选项和需要结合上下文判断的发现。

### 它是否同时支持 Cypress 和 Playwright？

审查和失败调试支持两个框架。新测试生成目前只支持 Playwright。Cypress 调试器接受 mochawesome 和 JUnit reports。

### 它能调试只在 CI 中失败的测试吗？

可以，前提是你提供本地 report artifacts 或受支持的 GitHub Actions run。调试器会使用 F1–F15 taxonomy 区分 environment、timing、selector、data、authentication 和 product-regression causes。

### 支持哪些 AI 编程代理？

Claude Code、Codex，以及 `skills` CLI 支持的 55+ 宿主都可以加载公开的 `SKILL.md` contracts。可选的 host-specific agent files 会在可用时改善委派；即使没有这些文件，公开 Skills 仍然可用。

## 详细文档

- [如何审查 AI 生成的 Playwright 和 Cypress E2E 测试](docs/review-ai-generated-e2e-tests.md)
- [24 个 Playwright 和 Cypress E2E 测试异味](docs/e2e-test-smells.md)
- [规则自审](docs/rule-self-audit.md)
- [开源案例研究](docs/case-studies.md)
- [基准状态与负面结果](benchmarks/STATUS.md)
- [外部证据台账](docs/llm-generated-e2e-test-evidence.md)
- [历史 AI 审查器基准](docs/ai-reviewer-benchmark.md)
- [调试器基准协议](docs/debugger-benchmark/README.md)
- [框架范围](docs/framework-scope.md)
- [路线图](docs/roadmap.md)

计划中的工作包括提升跨模型规则一致性，以及增强确定性检测。在对应的专门验证通过之前，任何路线图条目都不会被描述为已交付。

## 贡献

欢迎提交 bug reports、误报防护、新 anti-patterns 和 translations。请从 [CONTRIBUTING.md](CONTRIBUTING.md) 开始了解 setup 和 verification requirements。跨代理维护契约位于 [AGENTS.md](AGENTS.md)。

## 许可证

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha)。参见 [LICENSE](LICENSE)。
