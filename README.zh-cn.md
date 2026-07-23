<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — 面向 Playwright 和 Cypress 的 Agent Skills：生成、审查并调试可靠的端到端测试。" width="100%" />
</div>

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-4-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#在开源项目中得到验证"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-14-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://agents.md"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="https://www.npmjs.com/package/eslint-plugin-playwright-silent-pass"><img alt="playwright silent-pass npm" src="https://img.shields.io/npm/v/eslint-plugin-playwright-silent-pass?style=flat-square&label=playwright%20lint&labelColor=black&color=1FC07C"></a>
  <a href="https://www.npmjs.com/package/eslint-plugin-cypress-silent-pass"><img alt="cypress silent-pass npm" src="https://img.shields.io/npm/v/eslint-plugin-cypress-silent-pass?style=flat-square&label=cypress%20lint&labelColor=black&color=37B0E6"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<a href="README.md">🇺🇸 English</a> | <a href="README.ko.md">🇰🇷 한국어</a> | <a href="README.ja.md">🇯🇵 日本語</a> | <strong>🇨🇳 简体中文</strong>
</p>

找出那些能通过 CI，却几乎证明不了任何东西的 Playwright/Cypress 端到端测试。

**并非纸上谈兵——`e2e-reviewer` 的发现已经促成了 [14 个合入上游的 PR](#在开源项目中得到验证)**，涉及真实仓库，包括 SvelteKit、Storybook、code-server、Strapi、Carbon Design System、Ghost 和 MUI X。

> 其中一个仓库是 code-server（78k&#9733;）。一个 `it.only` 在七个月里悄悄禁用了 8 个测试——其中一个早已损坏。而 CI 全程保持绿色。

`e2e-skills` 是一套 Agent Skills，外加一个确定性扫描器，专门针对那些让端到端测试悄悄变绿的失败模式：弱断言、漏掉的 `await`、被丢弃的等待/读取、藏在条件里的断言、聚焦测试，以及一刀切的错误抑制。

它不是测试运行器，不是宽泛的 lint 预设，也不是通用的浏览器自动化工具包。它只聚焦于一个问题：

> 当用户可见的行为真的出问题时，这个端到端测试会失败吗？

## 为什么需要它

AI 智能体能很快生成端到端测试，但这些测试往往乍看很有说服力，实际检查的却是句柄、Promise 或一次性快照，而不是用户可见的状态。

```diff
- expect(page.getByText('SWE')).toBeDefined()
+ await expect(page.getByText('SWE')).toBeVisible()
```

第一行只能证明存在一个 Playwright `Locator` 对象。第二行才能证明用户可以看到这段文本。

生成式测试的问题不止静默通过。模型还会无视 YAGNI、KISS 这类原则，生成没有任何地方用到的代码——比如一个方法从未被任何测试调用的 Page Object。多个模型往同一个套件里写用例时，还会各写各的风格。这套工具把这些工作分开处理：用不上的抽象由 reviewer 以 #11（YAGNI + 僵尸 Spec）标记；generator 会在首次运行时脚手架出项目约定（`AGENTS.md` 的 E2E 部分加一个种子 spec），让之后的每个模型都按同一风格来写。更深入的自动推断版本在[路线图](#路线图)上。

`e2e-skills` 把这一过程变成一个可重复的审查工作流：

1. 扫描确定性的静默通过坏味道，
2. 用 Agent Skill 审查含糊不清的端到端测试意图，
3. 在缺失某个流程时生成更好的 Playwright 覆盖，
4. 把失败的 Playwright/Cypress 报告调试成根因修复。

## 看它运行

一个能通过 CI 却什么都没检查的 Playwright 测试——`Locator` 永远不会是 undefined，而 `.not.toBeNull()` 无论元素是否渲染都成立：

```ts
test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();   // always passes
  expect(page.locator('.user-badge')).not.toBeNull();     // always passes
});
```

扫描器确定性地捕捉到这两处，无需任何配置：

```console
$ bash skills/e2e-reviewer/scripts/scan.sh tests/

[P0] #4f Locator always-true assertion (truthy/defined/not-null) (2 hits)
  tests/login.spec.ts:6:  expect(page.getByText('Welcome back')).toBeDefined();
  tests/login.spec.ts:8:  expect(page.locator('.user-badge')).not.toBeNull();

Summary: 2 total hit(s), 2 P0
```

## 速览

| 需求 | 使用 |
| --- | --- |
| 生成新的 Playwright 端到端覆盖 | [`playwright-test-generator`](#skill-1-playwright-test-generator--测试生成) |
| 审查现有 Playwright/Cypress 测试中的静默通过坏味道 | [`e2e-reviewer`](#skill-2-e2e-reviewer--质量审查) |
| 调试失败的 Playwright 报告 | [`playwright-debugger`](#skill-3-playwright-debugger--playwright-失败调试器) |
| 调试失败的 Cypress 报告 | [`cypress-debugger`](#skill-4-cypress-debugger--cypress-失败调试器) |
| 运行确定性的本地扫描 | [`skills/e2e-reviewer/scripts/scan.sh`](#独立扫描器) |

实用文档：[案例研究](docs/case-studies.md)、[路线图](docs/roadmap.md)、[24 种坏味道分类法](docs/e2e-test-smells.md)、[框架范围](docs/framework-scope.md)、[AI 审查器基准测试](docs/ai-reviewer-benchmark.md)。

## 安装

不同宿主的安装方式各异：[Claude Code](#claude-code) · [Codex](#codex) · [其他所有智能体](#其他所有智能体-cursor-opencode-gemini-cli-等) · [手动克隆](#手动克隆claude-code)

### Claude Code

插件市场：

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

或通过跨智能体的 `skills` CLI：

```bash
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

`skills` CLI 是推荐的 Codex 安装方式。它会把整套技能放到 `~/.agents/skills/`；Codex 会在那里发现这些技能，并读取 `.codex-plugin/plugin.json` 中的接口块：

```bash
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code -a codex
```

备选方案——Codex 插件市场：

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

### 其他所有智能体 (Cursor, OpenCode, Gemini CLI 等)

跨智能体的 `skills` CLI 支持 55+ 个宿主。一条命令即可为它支持的所有智能体全局安装：

```bash
npx skills add voidmatcha/e2e-skills -g --all
```

如果只想安装到某一个智能体，把 `--all` 换成 `-a <agent>` 即可（如 `-a cursor`、`-a opencode`、`-a gemini-cli`），参见[支持的智能体列表](https://github.com/vercel-labs/skills#supported-agents)。

### 手动克隆（Claude Code）

```bash
git clone https://github.com/voidmatcha/e2e-skills.git ~/.claude/skills/e2e-skills
```

## 试用

```text
Review my Playwright tests in tests/e2e with e2e-reviewer.
```

```text
Generate Playwright E2E coverage for apps/web/e2e.
```

```text
Debug the failed Playwright report in playwright-report/.
```

## 是否适合

在以下情况使用 `e2e-skills`：

- Playwright/Cypress 测试通过了，但你不确定它们是否断言了真实的用户可见状态。
- AI 生成的端到端测试在合并前需要一道质量关卡。
- 测试套件中包含可疑模式，例如 `locator().toBeTruthy()`、`not.toBeNull()`、未 await 的 `expect(...)`、被丢弃的 `isVisible()`、`waitForTimeout()`、`it.only`，或全局的 `uncaught:exception` 抑制。
- 你希望有一个智能体来审查测试意图，而不仅仅是语法。

不要把它当作：

- 运行应用及其真实端到端测试套件的替代品，
- 通用的 lint 预设，
- 修复每一个不稳定测试的承诺，
- 与框架无关的测试工具。Playwright 和 Cypress 是受支持的范围。

## 在开源项目中得到验证

这不是凭空捏造的证明。`e2e-reviewer` 的发现已被用于在多个知名仓库中合入 **14 个上游 PR**，包括 SvelteKit、Storybook、code-server、Strapi、Carbon Design System、Ghost、Cal.com、Bruno、Qwik、Element Web、MUI X 和 Rancher Desktop。

这组实战记录也有可复现的 pilot benchmark 支撑：在 77 个 repository 的 100 个已由 AI reviewer review 过的开源 PR 中，neutral LLM judge 标出 110 个 material E2E test-trust issue；`e2e-reviewer` 找到 78 个且 0 false positive，lint 找到 45 个，general AI PR reviewer 的 inline spec comment 找到 10 个。见 [方法论与 case evidence](docs/ai-reviewer-benchmark.md)。

全部已合并修复：

| 仓库 | PR | 修复的模式 |
| --- | --- | --- |
| Storybook | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Playwright 断言缺失 `await` |
| code-server | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | 聚焦测试泄漏、缺少匹配器的 `expect`、被丢弃的可见性读取 |
| Strapi | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | 被丢弃的导航/状态检查 |
| SvelteKit | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | 游离的 Playwright 断言 |
| Carbon Design System | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | 用 web-first 断言替换 Locator 真值判断 |
| Ghost | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | 对 Promise 值进行的禁用状态断言 |
| Cal.com | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | 端到端流程中的弱断言模式 |
| Bruno | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | 断言与等待可靠性修复 |
| Qwik | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/句柄存在性检查 |
| Element Web | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator 空值检查式断言 |
| MUI X | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | 用状态断言替换 UI 句柄检查 |
| module-federation/core | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | 移除 Cypress spec 中多余的一刀切 `uncaught:exception` 抑制 |
| FiftyOne | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | 将 Locator 是否定义的检查改为可见的重复名称错误断言 |
| Rancher Desktop | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | 将 `not.toBeNull()` locator 检查改为可见的 WSL 集成名称断言 |

## 工作流

```text
1. Ask e2e-reviewer to inspect the target test directory.
2. Confirm P0 findings first: these are silent-pass or always-green risks.
3. Patch one smell family at a time.
4. Re-run the deterministic scanner and the target E2E/lint checks.
5. Use playwright-debugger or cypress-debugger only for real failed reports.
```

审查器输出示例：

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

## 独立扫描器

```bash
./skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

该扫描器有意保持确定性，优先捕捉其中高置信度的那部分；Agent Skill 再在扫描结果之上做读懂意图的审查。

> **网络行为。** 扫描器只读取你指定的文件，不上传任何内容。为达到其精度层级，它优先使用项目本地的 lint 工具；在缺失时，会通过 `npx` 自动下载固定版本的公开包（`eslint`、`eslint-plugin-playwright`/`-cypress`、`ast-grep`）。设置 `E2E_SMELL_NO_ESLINT_DOWNLOAD=1` 和 `E2E_SMELL_NO_AST_GREP_DOWNLOAD=1` 可完全离线运行。完整说明见：[SECURITY.md](./SECURITY.md)。

## Skill 1: `playwright-test-generator` — 测试生成

从零为任意项目生成 Playwright 端到端测试。它从覆盖缺口分析开始，通过浏览器自动化工具（Playwright MCP / webapp-testing）探索实时应用，在你批准下设计场景，并用 `e2e-reviewer` 自动审查生成的测试。

> **建议：** 先配置浏览器工具——[Playwright MCP](https://github.com/microsoft/playwright-mcp#getting-started) 或 `webapp-testing` 技能。若没有，则回退到只看页面初始状态的静态 ARIA 快照（无法交互），对简单页面够用，但对真实流程（弹窗、提交后、错误态、多步骤）受限。

### 何时使用

- 你有一个页面或功能，尚无端到端覆盖
- 你想为现有应用搭建一套测试套件
- 你需要在发布前快速补充测试

### 用法

```
Generate playwright tests
Generate playwright tests for the login page
Write e2e tests for the settings page
Add playwright coverage for checkout flow
```

### 流程

1. **检测环境**——配置、baseURL、测试目录、POM 结构、现有约定文档
2. **覆盖缺口分析**——由用户选定目标（当目标作为参数给出时跳过）
3. **实时浏览器探索**——通过浏览器自动化工具（[Playwright MCP](https://github.com/microsoft/playwright-mcp#getting-started) / webapp-testing；不臆造选择器）；对无标签输入做可访问名称的真实性校验
4. **场景设计 + 批准关卡**——在编写任何代码前展示计划和定位器表格
5. **代码生成**——POM + spec 或扁平 spec，根据项目约定自动检测；写操作必须做路由打桩（见 `code-rules.md` 中的 Network Determinism）
6. **约定与种子脚手架**（在项目上首次运行时）——向 `AGENTS.md` 追加一节针对项目适配的端到端内容，并指定一个种子 spec，从而让未来 AI 生成的测试（Claude Code、Codex、Playwright Agents）保持一致
7. **YAGNI 审计 + e2e-reviewer**——移除未使用的定位器，在首次运行前捕捉 P0 问题
8. **TS 编译 + 测试运行**——失败时进行 3 次自动修复尝试（按意图修复的定位器重新解析），随后移交给 `playwright-debugger`

---

## Skill 2: `e2e-reviewer` — 质量审查

捕捉那些能通过 CI、却抓不到真实回归的端到端测试问题。

每条 finding 在报告前都会经过 refute-first 的 adversarial 验证 —— 在 Claude Code 插件安装中由 read-only 子代理执行，在其他宿主中则 inline 执行。正是这道独立的验证环节，让审查器在基准测试中把 false positive 保持为零。

### 何时使用

- 你的测试总是通过，但缺陷仍会溜到生产环境
- 测试通过了 CI，但你怀疑它们漏掉了真实回归
- 你的测试套件很脆弱——每次 UI 变更都会导致测试失败
- 你想在发布或代码审查前审计测试质量
- 你正在审查 Playwright 或 Cypress 的 spec

### 用法

```
Review my E2E tests
Audit the spec files in tests/
Find weak tests in my test suite
My tests always pass but miss bugs
Tests pass CI but miss regressions
My tests are fragile and break on every UI change
We have coverage but bugs still slip through
```

### 检测到的 24 种模式——按严重程度分组

#### P0 — 必须修复（静默的永远通过）

当功能已损坏时测试仍然通过。没有发生任何真正的验证。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 1 | **名称与断言不匹配** | 名称写的是 "status"，但只检查了 `toBeVisible()` | 为状态内容添加断言，或重命名以匹配实际检查 |
| 2 | **缺失 Then** | 取消操作，验证文本已恢复——但输入框仍然可见？ | 同时验证已恢复状态和已消失状态 |
| 3 | **吞掉错误** | spec 中的 `try/catch`，POM 中的 `.catch(() => {})` | 让错误导致失败；从 POM 方法中移除静默的 catch |
| 3b | **Cypress `uncaught:exception` 抑制** | `cy.on('uncaught:exception', () => false)` 一刀切地吞掉应用错误 | 将处理器限定到特定的已知错误；对未知错误重新抛出 |
| 4 | **永远通过的断言** | `toBeGreaterThanOrEqual(0)`；无注释的 `toBeAttached()`；`expect(await el.isVisible()).toBe(true)`（一次性）；`expect(await el.textContent()).toBe(x)`（一次性）；`expect(locator).toBeTruthy()`（Locator 永远为真值）；断言上的 `{ timeout: 0 }`（禁用重试） | `toBeGreaterThan(0)`；`toBeVisible()`；带自动重试的 web-first 断言 |
| 5 | **绕过模式**（5a P0，5b P1） | `if (await el.isVisible()) { expect(...) }`；无注释的 `{ force: true }` | 始终进行断言；把环境检查移到 `beforeEach`；给 force:true 添加 `// JUSTIFIED:` |
| 7 | **聚焦测试泄漏** | 提交了 `test.only(...)`——CI 只运行一个测试，静默跳过其余 | 删除 `.only`；用 `--grep` 或 `--spec` 做本地聚焦 |
| 8 | **缺失断言** | `await page.locator('.x');`（被丢弃）；`await el.isVisible();`（布尔值被丢弃） | 添加 `await expect(locator).toBeVisible()` 或删除该行 |
| 12 | **缺失鉴权设置** | 受保护路由的 spec 导航到 `/dashboard`，却没有登录/`storageState`/鉴权 fixture | 添加 `beforeEach` 登录、配置 `storageState`，或使用鉴权 fixture——否则测试会对着登录页通过 |
| 15 | **`expect()` 上缺失 `await`** | `expect(page.locator('.toast')).toBeVisible()` 返回一个未被观察的 Promise | 添加 `await`，让断言真正执行 |
| 16 | **动作上缺失 `await`** | `page.locator('#submit').click()` 可能在下一行之前尚未执行 | 添加 `await`，让动作完成 |

#### P1 — 应当修复（诊断信息差 / 浪费 CI 时间）

测试能工作，但会误导开发者、浪费 CI 时间，或为将来的回归埋下隐患。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 6 | **原生 DOM 查询** | `evaluate()` 中的 `document.querySelector` | 使用框架的定位器/查询 API（`locator` / `cy.get`） |
| 9 | **硬编码 sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | 依赖框架的自动等待；使用基于条件的等待 |
| 10 | **不稳定测试模式** | 无注释的 `items.nth(2)`；`test.describe.serial()` | 使用 `data-testid` 或角色选择器；用自包含测试替换 serial |
| 13 | **POM 使用不一致** | 导入了 POM，但 spec 对 POM 所属动作使用原生 `page.fill`/`page.click` | 让所有交互都经过 POM，这样 UI 变更只需在一处更新 |
| 14 | **硬编码凭据** | 测试代码中的 `loginPage.login('demo-admin', '<literal-password>')` | 使用 `process.env.TEST_USER`、Playwright 配置密钥或测试数据 fixture |
| 17 | **直接使用 `page.click(selector)` API** | `page.click('#submit')` / `page.fill('#input', 'text')` 跳过了 Locator 层 | 使用 `page.locator(selector).click()` 以获得自动等待和更好的错误信息 |
| 18 | **`expect.soft()` 滥用** | 一个测试中的所有断言都是 `expect.soft()`——测试永远不会提前失败 | 确保每个测试至少有一个硬 `expect()` 作为关卡；`soft` 仅用于相互独立的细节 |
| 19 | **测试代码中的模块级可变状态** | 测试工具中位于第 0 列的 `let testNotebookSequence = 0;`——会在并行 worker 之间冲突，并在重试后残留 | 去掉该计数器；用 `Date.now()` + `Math.random().toString(36).slice(2, 8)` 派生唯一性，或把状态移入 `test.beforeEach` |
| 20 | **未打桩的真实后端写操作** | 注册/结账 spec 提交真实变更——每次 CI 运行都会创建真实账户/订单 | 用 `page.route()` / `cy.intercept()` 打桩写/凭据端点；最多保留一个指定的真实后端冒烟 spec |
| 22 | **没有调用证明的乐观 UI** | 点赞切换测试断言 `aria-pressed` 翻转——UI 乐观更新，即使删掉 POST 也能通过 | 把 UI 断言与 `page.waitForRequest()`（在点击前预先设置）或路由命中标志配对 |

#### P2 — 建议修复（可维护性 / 健壮性）

弱但不算错——在重构时处理。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 11 | **YAGNI + 僵尸 Spec** | `clickEdit()` 从未被调用；空的包装类；一次性使用的 Util；整个 spec 被另一个重复 | 删除未使用的成员；内联一次性使用的 Util 方法；删除僵尸 spec 文件 |
| 21 | **手动捕获的会话文件依赖** | `storageState: 'auth/member.json'` 仅由手动捕获脚本生成——在 CI 上缺失，会静默过期 | 以编程方式重新生成会话（API 登录辅助或 `setup` 项目）；手动文件仅作为带编程回退的缓存 |
| 23 | **Fixture 忽略渲染守卫** | 点赞标签页 fixture 种入 `liked: false`；卡片组件对每一项 `return null`——空白 UI 看起来像基础设施抖动 | 在种入数据前先读取项组件的提前返回/过滤条件；为被测视图种入能通过每个守卫的字段 |

### 静态检查器从结构上无法捕捉的内容

**静态检查器能查出一个断言写得规不规范，却查不出这个测试到底有没有证明它名字里声称的东西。** 测试声称的意图和它实际验证的内容，中间这道缝正是 `e2e-reviewer` 要找的核心，而任何逐文件的 AST 或 grep 规则都看不见它：`should show an error when the name is duplicate` 可以在一个从不触及错误的断言下通过，语法却毫无瑕疵。要判定它，得把测试的名称、它执行的动作以及周围的代码放在一起读，这比单文件规则的运作层级高出一层。

`e2e-reviewer` 把 `eslint-plugin-playwright` / `eslint-plugin-cypress` 作为它的第一层，因此机械性的规则（`#6`、`#7`、`#9`、`#15`、`#16`、`#5a`、`#5b`）已经被这些事实标准的插件覆盖。永远通过的 Locator 断言坏味道（`#4f`）现在也被覆盖了——它由本项目贡献到官方 `eslint-plugin-playwright`，作为 [`no-unnecessary-assertions`](https://github.com/mskelton/eslint-plugin-playwright/pull/470) 规则已合并（将随下一个版本发布），Cypress 一侧则由 [`eslint-plugin-cypress-silent-pass`](https://github.com/voidmatcha/eslint-plugin-cypress-silent-pass) 覆盖。在其之上再加 `e2e-reviewer` 的理由，是那些**任何 AST 或 grep 规则都触及不到**的坏味道，因为确认它们需要读取规则永远看不到的代码——其他函数、组件、CI 配置、测试自身的意图：

| 坏味道 | 为什么 lint 无法判定 |
|-------|---------------------------|
| `#1` 名称与断言不匹配 | 需要把测试的*名称/意图*与它实际断言的内容进行比较。从语法上看断言没问题。 |
| `#3` / `#3b` 吞掉错误与一刀切的 `cy.on('uncaught:exception', () => false)` | 语法有效；只有意图才能揭示它禁用了失败。一个单行正则在某个套件中漏掉了 **51 处多行实例**。 |
| `#4f` Locator 当作真值（`expect(locator).toBeTruthy()` / `.toBeDefined()` / `.not.toBeNull()`） | 读起来像一个正常的断言。你必须*知道* Locator 永远不会是假值，才能看出它总是通过。 |
| `#4` 一次性读取（`expect(await el.isVisible()).toBe(true)`） | 一个有效的 `expect`；只有知道它是不重试的、某一时刻的点读取，才会把它标记为反模式。 |
| `#12` 缺失鉴权设置 | 需要跨文件推理配置、fixture 和 `storageState`，才能知道该路由未经鉴权。 |
| `#20` / `#22` 未打桩的写操作 / 没有调用证明的乐观 UI | 需要知道某个端点会产生变更，或 UI 是乐观更新而背后没有任何网络断言。 |
| `#11` / `#23` 僵尸 spec / fixture 忽略渲染守卫 | 跨文件：重复 spec 检测，或在信任种子数据前先读取组件的提前 `return null`。 |
| **最难的情形** | 一个 `try/catch` 包裹着一个*从不抛出*的函数，只在 `catch` 内部断言（真实案例：xyflow 的 `graph-utils.cy.ts` 中的 `addEdge`）。要确认它，就得读取另一个文件里的函数体——这对 grep 或任何单文件 AST 规则都是不可能的。 |

这部分靠的是判断力，而不是模式匹配。`e2e-reviewer` 会先读候选项周围的代码和 CI 配置来**验证**它，再把它算作正式发现——也就是上文提到的[候选项而非定论](#scanner-findings-are-candidates-not-verdicts)原则——这也是为什么每个发现都附带一个避免治标不治本的修复方案，而不是一处原始匹配。

### 参考资料

[Playwright 最佳实践](https://playwright.dev/docs/best-practices) · [Cypress 最佳实践](https://docs.cypress.io/app/core-concepts/best-practices) · [Testing Library 指导原则](https://testing-library.com/docs/guiding-principles)

---

## Skill 3: `playwright-debugger` — Playwright 失败调试器

从 `playwright-report/` 目录诊断 Playwright 测试失败——无论失败发生在本地还是 CI。对根因进行分类并提供具体修复。

### 何时使用

- 你有一个 `playwright-report/` 目录（本地或从 CI 下载），其中有需要理解的失败
- 测试在本地通过，但在 CI 失败
- 你正在处理不稳定或间歇性的测试失败
- 你遇到 `TimeoutError` 或 `locator not found`，却找不到明确原因

### 用法

```
Debug these failing tests
Why did these tests fail?
Tests pass locally but fail in CI
```

> **注意：** 既可以传入本地报告路径，也可以直接给出 GitHub Actions 的 run——技能会在用户确认 run ID 后通过 `gh run download` 自行下载工件（fork PR 的 run 除外）。

### 15 种根因分类

| # | 分类 | 信号 |
|---|----------|---------|
| F1 | **不稳定 / 时序** | `TimeoutError`，重试后通过 |
| F2 | **选择器损坏** | `locator not found`，strict mode 违规 |
| F3 | **网络依赖** | `net::ERR_*`，意外的 API 响应 |
| F4 | **断言不匹配** | `Expected X to equal Y`，主体倒置 |
| F5 | **缺失 Then** | 动作已完成，但残留了错误的状态 |
| F6 | **缺失条件分支** | 元素有条件地存在，断言却总是执行 |
| F7 | **测试隔离失败** | 单独运行通过，在套件中失败 |
| F8 | **环境不匹配** | 仅 CI 与本地之间；视口、操作系统、时区 |
| F9 | **数据依赖** | 缺失种子数据，硬编码 ID |
| F10 | **鉴权 / 会话** | 会话过期，基于角色的 UI 未渲染 |
| F11 | **异步顺序假设** | `Promise.all` 顺序，并行竞态 |
| F12 | **POM / Locator 漂移** | DOM 结构变了，POM 未更新 |
| F13 | **吞掉错误** | `.catch(() => {})` 隐藏了真实失败 |
| F14 | **动画竞态** | 内容尚未渲染，或某个瞬态元素在被观察前就已移除 |
| F15 | **水合竞态** | 动作成功但没有效果——SSR 页面尚未水合；在下一个断言处失败 |

### 调试流程

1. **提取**——解析 `results.json`，获取失败的测试、错误信息、耗时
2. **分类**——用错误信号把每个失败映射到 F1–F15（大多数失败在此阶段解决）
3. **追踪**——若仍不清楚，解压 `trace.zip` 并逐步检查：失败的动作、DOM 快照、网络错误、JS 控制台错误
4. **修复**——针对每个失败给出具体的代码建议，按 P0/P1/P2 排定优先级

---

## Skill 4: `cypress-debugger` — Cypress 失败调试器

从 mochawesome 或 JUnit 报告文件诊断 Cypress 测试失败。对根因进行分类并提供具体修复。

### 何时使用

- 你有一个 `cypress/reports/` 目录（本地或从 CI 下载），其中有需要理解的失败
- Cypress 测试在本地通过，但在 CI 失败
- 你正在处理不稳定或间歇性的 Cypress 失败
- 你遇到 `Timed out retrying` 或 `Expected to find element`，却找不到明确原因

### 用法

```
Debug these failing Cypress tests
Why did these Cypress tests fail?
Analyze cypress/reports/
Cypress tests pass locally but fail in CI
```

### 15 种根因分类

| # | 分类 | 信号 |
|---|----------|---------|
| F1 | **不稳定 / 时序** | `Timed out retrying`，重试后通过 |
| F2 | **选择器损坏** | `Expected to find element`，`cy.get() failed` |
| F3 | **网络依赖** | `cy.intercept()` 未匹配，`XHR failed` |
| F4 | **断言不匹配** | `expected X to equal Y`，`AssertionError` |
| F5 | **缺失 Then** | 动作已完成，但残留了错误的状态 |
| F6 | **缺失条件分支** | 元素有条件地存在，断言却总是执行 |
| F7 | **测试隔离失败** | 单独运行通过，在套件中失败 |
| F8 | **环境不匹配** | 仅 CI 与本地之间；baseUrl、视口、操作系统 |
| F9 | **数据依赖** | 缺失种子数据，`cy.fixture()` 不匹配 |
| F10 | **鉴权 / 会话** | `cy.session()` 过期，基于角色的 UI 未渲染 |
| F11 | **命令队列 / 拦截竞态** | `cy.intercept` 在请求发出之后才注册；`.then()` 链顺序交换；并行的 `cy.request()` 与尚未完成的 `cy.visit()` 竞争 |
| F12 | **选择器漂移** | DOM 变了，自定义命令或 POM 选择器未更新 |
| F13 | **吞掉错误** | `cy.on('uncaught:exception', () => false)` 隐藏了失败 |
| F14 | **动画竞态** | 内容尚未渲染，某个瞬态元素在被观察前就已移除，或 CSS 过渡尚未完成 |
| F15 | **水合竞态** | `cy.visit()` 之后的首次点击成功但没有效果——SSR 页面尚未水合；在下一个断言处失败 |

### 调试流程

1. **提取**——解析 `mochawesome.json` 或 JUnit XML，获取失败的测试、错误信息、耗时
2. **分类**——用错误信号把每个失败映射到 F1–F15（大多数失败在此阶段解决）
3. **截图/视频**——若仍不清楚，检查 `cypress/screenshots/` 和 `cypress/videos/`
4. **修复**——针对每个失败给出具体的代码建议，按 P0/P1/P2 排定优先级

---

## 常见问题

### 什么是 e2e-skills？

e2e-skills 是一个面向 Playwright 和 Cypress 的开源 AI 智能体测试工具包。它打包了四个 Agent Skills，用于生成端到端测试、审查现有 spec 里静默的永远通过反模式，并调试不稳定的失败——可运行在 Claude Code、Codex 以及其他兼容 `AGENTS.md` 的 AI 编码智能体上。

### 如何找出那些能通过、却实际什么都没测的 Playwright 或 Cypress 测试？

针对你的 spec 目录运行 `e2e-reviewer` 技能（或其独立扫描器 `scan.sh`）。它会标记按严重程度（P0/P1/P2）分组的 24 种反模式——包括断言缺失 `await`、一次性 `isVisible()` 读取、缺少匹配器的 `expect()`，以及提交的 `.only` 泄漏——这些都会让一个测试在其覆盖的功能已损坏时仍保持绿色。

### 它与 eslint-plugin-playwright 或 eslint-plugin-cypress 有何不同？

eslint 插件是你每次提交时针对语法规则的基线，扫描器会先运行它们（第 1 层）——所以它并不取代它们，而是在其之上再加一层。这一层就是静态检查器[从结构上无法判定](#静态检查器从结构上无法捕捉的内容)的坏味道：名称与断言不匹配、包裹着一个从不抛出的函数的 `try/catch`、一个永远为真的 `expect(locator).toBeTruthy()`、一条缺失鉴权的路由——每一个都需要读取 AST 规则永远看不到的代码（另一个函数、组件、CI 配置、测试的意图）。`e2e-reviewer` 会读取这些周围代码以验证发现，并给出一个避免治标不治本的修复，而 lint 只能标记单文件语法。

### 这不就是又一个像 CodeRabbit、Copilot 或 Cursor BugBot 那样的 AI 代码审查器吗？

那些都是出色的通用审查器——其中几个对开源免费，而且现在可以本地运行（CodeRabbit 的 CLI 会在终端里审查已暂存的改动）。区别在于专精，而非能力：通用审查器对任何交给它的 diff 进行推理，而 `e2e-reviewer` 携带一份精心整理、稳定、按严重程度分级的端到端静默永远通过反模式目录（24 种带固定 ID 的模式，外加 15 种失败调试分类），并按需针对整个 spec 目录运行，而不仅是一个 PR diff。通用审查器可用于一切；当你在意的是端到端测试的可信度时，就用这个。想看在 100 个已审查 PR 上的真实正面对比（附带诚实的局限性），见 [AI 审查器基准测试](docs/ai-reviewer-benchmark.md)。

### 它对 Cypress 和 Playwright 都适用吗？

是的。两者都是一等公民：测试生成和最丰富的审查针对 Playwright，而审查与失败调试则完整覆盖 Cypress（mochawesome 和 JUnit 报告）。

### 它能调试那些只在 CI 失败的不稳定测试吗？

可以。`playwright-debugger` 和 `cypress-debugger` 会读取你的报告文件（`playwright-report/`、`cypress/reports/`），并把每个失败归类到 15 种根因分类中——不稳定时序、选择器漂移、测试隔离、环境不匹配、水合竞态等等——并为每个失败给出具体修复。

### 如何审查 AI 生成的端到端测试？

把 `e2e-reviewer` 指向生成的 spec。AI 编写的测试经常包含看起来很自信、实则静默永远通过的断言；审查器会在它们进入你的主分支之前，用修改前/修改后的修复把它们暴露出来。

### 支持哪些 AI 编码智能体？

Claude Code（插件市场或 `skills` CLI）、Codex，以及任何 `skills` CLI 通过 `AGENTS.md` 支持的智能体（55+ 个宿主）。一次安装，处处可用。

### 它是否支持 Playwright 和 Cypress 以外的测试框架？

不——按设计只支持 Playwright 和 Cypress。理由见[框架范围](docs/framework-scope.md)。

## 路线图

已规划、尚未发布（这些描述的是方向，而非当前行为）：

- **跨模型一致性。** 不同的 AI 智能体各自以自己的风格编写 spec，于是用多个模型搭出来的套件会渐渐散成一块拼布，没有哪一条约定能把它统合起来。计划是：推断你项目的约定（POM 形态、定位器策略、fixture 和结构模式；“不做抽象”也是有效答案，两页的流程不会被套上多余的 Page Object 层），只在代码库确实含糊时才问你，并把这些答案存下来，让此后每个模型都照着走。关键在于，记录下来的约定始终只是*智能体给出理由后就能偏离的默认值*，而不是硬性规则，所以针对某个具体测试更好的做法永远不会被挡住——而一次有理由的偏离，正是这条约定往前演进的契机。这恰恰是静态检查器从结构上做不到的：它只会强制执行固定规则，学不会、也遵循不了*你的*约定。
- **确定性检测层。** 把逐文件、类型可判定的坏味道（Locator 当作真值、游离断言）从提示和启发式挪到类型感知的 AST 处理上，让检测变得可复现，也把 LLM 留给单文件规则无法做出的判断。那些明显可 lint 的规则会贡献到上游的 `eslint-plugin-playwright`，而不是另起炉灶重新实现——其中第一个、用于检测永远通过的 Locator 断言的 `no-unnecessary-assertions` 规则已[合并](https://github.com/mskelton/eslint-plugin-playwright/pull/470)。

另外，上游贡献路线图追踪着更广的流水线：**已合并 14、审查与排队合计 14**。队列里只放经过审核的 1,000+ 星候选——实时表格见[上游贡献](docs/roadmap.md)。

## 贡献

欢迎提交缺陷报告、误报防护、新的反模式和翻译。请从 [CONTRIBUTING.md](./CONTRIBUTING.md) 开始，了解环境搭建、验证关卡（`bash scripts/ci/ci-local.sh`）以及冻结 ID / 一致性约定。更深入的跨智能体细节见 [AGENTS.md](./AGENTS.md)。

## 许可证

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha)。见 [LICENSE](./LICENSE)。
