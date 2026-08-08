<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — 面向 Playwright 和 Cypress 的 Agent Skills：生成、审查并调试可靠的端到端测试。" width="100%" />
</div>

# e2e-skills：找出 false-green Playwright 和 Cypress E2E 测试

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
<a href="README.md">🇺🇸 English</a> | <a href="README.ko.md">🇰🇷 한국어</a> | <a href="README.ja.md">🇯🇵 日本語</a> | <strong>🇨🇳 简体中文</strong>
</p>
<!-- README-CANONICAL-REVISION: sha256=03ecf4339e9d1ba4dae90dee5d8faa35866f1d4fa9813da1cb42aaab39800efc; bytes=exact-README.md-UTF-8; translation-quality=not-attested -->

找出那些能通过 CI、却没有验证用户可见行为的 Playwright 和 Cypress E2E 测试。

`e2e-skills` 为 AI 编程代理提供四个聚焦的工作流：生成 Playwright 覆盖、审查 Playwright/Cypress spec 中的 false-green 测试，以及调试失败的 Playwright 或 Cypress 报告。它还包含一个确定性扫描器，用来识别机械性的 silent-pass 模式。

**为什么值得一试：** `e2e-reviewer` 的发现已经促成 [14 个合入上游的 PR](#open-source-adoption)，包括 Storybook、SvelteKit、code-server、Strapi、Carbon Design System、Ghost 和 MUI X 中的修复。

> 在 code-server 中，一个提交进仓库的 `it.only` 曾默默禁用 8 个测试长达 7 个月。其中一个被跳过的测试早已损坏，而 CI 仍然保持绿色。

## 看一个 false-green 测试

**false-green**（假绿）测试无论它所声称的行为是否正常都会通过。它不是 flaky 测试：flaky 测试偶尔会失败，因此重试面板和 flake 分析最终能发现它。false-green 测试**即使产品已经损坏也从不失败**，所以任何监视测试状态翻转的工具都永远不会暴露它。

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

内置扫描器无需项目配置即可捕获这些 false-green assertions：

```console
$ /bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests/

[P0] #4f Locator always-true assertion (truthy/defined/not-null) (2 hits)
  tests/login.spec.ts:6:  expect(page.getByText('Welcome back')).toBeDefined();
  tests/login.spec.ts:8:  expect(page.locator('.user-badge')).not.toBeNull();

Summary: 2 total hit(s), 2 P0
```

`eslint-plugin-playwright` 也会通过 `no-unnecessary-assertions` 标记这种写法。请启用该规则——每次提交都运行的规则，胜过需要你记得执行的评审。扫描器每次运行都会输出哪些发现本应由你的 lint 配置负责，因此两者是互补而非竞争。

## 证明测试会失败

写法规范的断言不等于有效的测试。lint 能告诉你 `toBeVisible()` 是正确的 matcher，却无法告诉你功能损坏时这个测试会不会变红。

`playwright-test-generator` 直接回答这个问题。在项目批准的临时副本上，它反转主断言（V2）并注入有据可查的产品缺陷（V3），然后要求测试在预定位置以预定的不匹配失败。因超时、浏览器崩溃或配置错误导致的失败不算数。无法安全证明的内容会报告为 `CANNOT_VERIFY`，而不是猜测。

这是把范围收窄到单个候选 spec 的变异测试。正是这种收窄让成本可以承受——因为在 E2E 上对整个套件做变异测试并不可行。

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

对于 Codex 委派，`e2e-reviewer`、`playwright-debugger` 和 `cypress-debugger` 可以使用 native roles，也可以使用等价的 inline fallbacks。`playwright-test-generator` 的 V6 边界更严格：如果没有独立的 fresh-context reviewer，它会报告 `CANNOT_VERIFY` 和 `PARTIAL/BLOCKED`。源码 checkout 也在 `.codex/agents/` 下包含可选的 native agents；贡献者可查看 [AGENTS.md](AGENTS.md) 了解 packaging boundary。

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

如需只针对一个宿主，把 `--all` 替换为 `-a <agent>`；参见 [supported agents](https://github.com/vercel-labs/skills#supported-agents)。这些命令固定使用已审查的 CLI release，而不是执行未经审查的新版本。

### 手动 Claude Code checkout

把 checkout 放在 `~/.claude/skills/` 之外，然后链接每个 public Skill 目录：

```bash
git clone https://github.com/voidmatcha/e2e-skills.git "$HOME/.claude/e2e-skills"
mkdir -p "$HOME/.claude/skills"

for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
  ln -s "$HOME/.claude/e2e-skills/skills/$skill" "$HOME/.claude/skills/$skill"
done
```

如果已有同名 Skill，这些链接会失败，而不会替换它。在 Claude Code 中运行 `/skills`，确认四个名称都出现。

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

## 你会得到什么

| 需求 | Skill | 结果 |
| --- | --- | --- |
| 生成新的 Playwright 覆盖 | `playwright-test-generator` | 已探索、已批准、已审查的 Playwright specs |
| 审查正在通过的 Playwright/Cypress 测试 | `e2e-reviewer` | 带具体修复的已验证 P0/P1/P2 发现 |
| 调试失败的 Playwright 运行 | `playwright-debugger` | F1–F15 根因、证据和修复 |
| 调试失败的 Cypress 运行 | `cypress-debugger` | F1–F15 根因、证据和修复 |
| 运行确定性的本地扫描 | `skills/e2e-reviewer/scripts/scan.sh` | 不依赖目标项目 package 的机械候选项 |

当 AI 生成或继承来的 E2E 测试可能在没有证明预期结果的情况下通过时，请使用这套 bundle。不要把它当作运行应用及其真实 E2E suite 的替代品，也不要把它当作通用 lint preset 或框架无关的测试工具。Playwright 和 Cypress 在支持范围内；生成目前只面向 Playwright。

生成的测试仅仅通过还不够：它可能断言的是 `Locator` 或 `Promise` 本身，观察的状态与测试名称所描述的行为无关，或者主要断言根本不影响测试结果。因此，在所有适用的 [V1–V6 验证](skills/playwright-test-generator/verification-rules.md) 通过之前，生成器始终把新 spec 视为候选项。

在项目批准的临时副本上，V2 可以反转主要断言，V3 可以注入有证据支持的产品故障。只有预先指定的主要断言在预期位置因预期不匹配而失败，才算成功杀死 mutant；由 setup、timeout、browser 或 infrastructure 错误导致的失败不作数。源候选文件保持 byte-identical，无法安全运行的探针会报告为 `CANNOT_VERIFY`，而不是靠猜测得出结论。

## 审查如何工作

语法有效的测试代码，不等于会在产品出错时失败的测试。该工作流把机械检测和语义判断分开：

1. 扫描器会发现确定性候选项，例如 Locator truthiness、focused tests、缺失的 `await` 和 blanket error suppression。
2. `e2e-reviewer` 会先读取测试名称、操作、断言、helpers、Page Objects、fixtures 和配置，再确认一项发现。
3. 发现使用稳定的 pattern IDs 和 P0/P1/P2 severity，让修复与回归保持可比较。
4. 修复后，工作流会重新运行扫描器，以及项目已批准的 E2E 或 lint 命令。

扫描器命中只是候选项，不是 verdict。跨文件发现，例如缺失认证、没有 call proof 的 optimistic UI、name/assertion mismatch，以及被 render guards 阻塞的 fixtures，都需要语义审查。

## 证据与限制

当前证据只支持一个窄口径声明：项目拥有 behavior-backed 开发证据和真实开源采用，但不声称具备可泛化的 reviewer accuracy。

- Browser fault injection 已完成 **36/36 Playwright/Cypress cells**。
- Exact reviewer benchmark 覆盖 **12 个已证实的 false-green cases 和 12 个 clean guards**；其中 10 个 fault cases 是 byte-identical operator mutants。
- Independent robustness gates v4、v5、v7 和 v8 未达到其预注册标准。V6 和 v9 未运行，v10 已冻结但未运行。

查看 [benchmark status](benchmarks/STATUS.md) 了解分数、失败的 gates、被取代的 runs 和 claim 边界。[research evidence ledger](docs/llm-generated-e2e-test-evidence.md) 审计了 59 个外部来源，避免把相邻的 unit-test 或 custom-agent 研究当作本项目的测量结果。

## E2E 审查目录

该目录包含 24 个稳定的 Playwright/Cypress test smells。最常见的 false-green 形态包括 Locator truthiness、缺失 assertion、吞掉错误、focused tests、缺失认证，以及没有 network proof 的 optimistic UI checks。参见 [完整 taxonomy 和 rationale](docs/e2e-test-smells.md)。

<details>
<summary>按严重程度查看全部 24 个模式</summary>

### 检测到的 24 个模式 — 按严重程度分组

#### P0 — 必须修复（silent always-pass）

功能损坏时测试仍会通过，因为没有发生真实验证。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 1 | **Name-assertion mismatch** | 名称说的是 "status"，但只检查 `toBeVisible()` | 添加 status 内容断言，或重命名为匹配实际检查 |
| 2 | **Missing Then** | 执行 cancel action，验证文本已恢复，但输入框仍然可见？ | 同时验证 restored state 和 dismissed state |
| 3 | **Error swallowing** | spec 中的 `try/catch`，POM 中的 `.catch(() => {})` | 让错误导致失败；从 POM methods 中移除 silent catch |
| 3b | **Cypress `uncaught:exception` suppression** | `cy.on('uncaught:exception', () => false)` blanket-swallows app errors | 将 handler 限定到特定已知错误；重新抛出未知错误 |
| 4 | **Vacuous or retry-weakening assertion** (P0/P1) | P0：invariant predicates 和 Locator truthiness。P1：weak attachment proof；one-shot values/URL；zero-timeout retry/deadline hazards；unproven absence；遗漏已承诺 accessible name 的 ARIA snapshots | 使用有意义的边界和 web-first auto-retrying assertions；先证明 presence，再证明 absence，并让已承诺的 accessible names 保持 load-bearing |
| 5 | **Bypass patterns** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`；没有注释的 `{ force: true }` | 始终断言；把 env checks 移到 `beforeEach`；给 force:true 添加 `// JUSTIFIED:` |
| 7 | **Focused test leak** | 提交了 `test.only(...)` — CI 只运行一个测试，默默跳过其余测试 | 删除 `.only`；使用 `--grep` 或 `--spec` 做本地聚焦 |
| 8 | **Missing assertion** | 被丢弃的 locator/boolean 是该场景唯一的验证 | 添加 `await expect(locator).toBeVisible()`；当独立 verification/failure evidence 已存在时跳过 #8 |
| 12 | **Missing auth setup** | 缺少 login/`storageState`/auth fixture 时，protected-route spec 会通过，因为泛化断言也匹配 login/wrong surface | 添加 `beforeEach` login，配置 `storageState`，或使用 auth fixture；不要把正常的 auth-caused failure 归类为 P0 |

#### P1 — 应修复（poor diagnostics / wastes CI time）

测试能运行，但会误导开发者、浪费 CI 时间，或埋下未来回归。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 6 | **Raw DOM queries** | `evaluate()` 中的 `document.querySelector` | 使用 framework locator/query APIs（`locator` / `cy.get`） |
| 9 | **Hard-coded sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | 依赖 framework auto-wait；使用 condition-based waits |
| 10 | **Flaky test patterns** | 没有注释的 `items.nth(2)`；`test.describe.serial()`；未限定作用域的 accessible-name substring（10c）；Cypress async callbacks、被赋值的 `cy` commands，或继续串接的 action chains（10d–10f） | 使用稳定且限定作用域的 locators 和 self-contained tests；让 Cypress 工作留在其 command chain 中，不要把 Chainables 赋值为普通值，并在 actions 后重新 query |
| 13 | **Inconsistent POM usage** | 已导入 POM，但 spec 对 POM-owned actions 使用 raw `page.fill`/`page.click` | 将所有交互路由到 POM，使 UI 变化只需在一个地方更新 |
| 14 | **Hardcoded credentials** | 测试代码中的 `loginPage.login('demo-admin', '<literal-password>')` | 使用 `process.env.TEST_USER`、Playwright config secrets 或 test data fixtures |
| 15 | **Missing `await` on `expect()`** | Async Locator/Page web-first matcher Promise 没有被排序或观察；rejection 通常稍后才暴露，归因更差 | `await` 或 return matcher Promise；sync value matchers 被排除 |
| 16 | **Missing `await` on action** | Actionability、action ordering 或 navigation 可能与后续工作竞态；rejection 通常稍后才暴露，归因更差 | `await` 或 return action Promise |
| 17 | **Discouraged direct Page selector API** | 基于 selector 的 `page.click`、`page.fill` 及相关 Page actions 跳过 Locator 层 | 使用 Locator actions，以获得组合性、strictness、复用和更清晰的 failure |
| 18 | **`expect.soft()` overuse** | 关键 soft assertions 在 hard scenario gate 之前运行，因此前置条件损坏后 dependent work 仍会继续 | 先对主要状态做 hard-gate；仅对独立细节使用 `soft` |
| 19 | **Module-level mutable state in test code** | 测试工具中第 0 列的 `let testNotebookSequence = 0;`，它会在长生命周期 worker 中跨测试保留，并在并行 workers 间冲突 | 删除 counter；从 `Date.now()` + `Math.random().toString(36).slice(2, 8)` 派生唯一性，或把状态移入 `test.beforeEach` |
| 20 | **Unmocked real-backend writes** | Signup/checkout spec 触达共享或持久状态，却没有受控测试边界 | Stub 该写入，或证明存在 disposable container、rollback fixture、isolated tenant/database 或等价的受控 backend |
| 22 | **Optimistic UI without call proof** | Like-toggle test 断言 `aria-pressed` 翻转 — UI 乐观更新，POST 被删除时仍会通过 | 将 UI assertion 与 `page.waitForRequest()`（点击前 armed）或 route-hit flag 配对 |

#### P2 — 可择机修复（maintenance / robustness）

弱但不一定错误；重构时处理。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | `clickEdit()` 从未被调用；无理由的空 wrapper class；整个 spec 被另一个 spec 重复 | 删除未使用成员和 zombie specs；只有在确实能移除无意义间接层时，才内联 single-use helpers |
| 21 | **Manually-captured session-file dependency** | `storageState: 'auth/member.json'` 只由手动 capture script 生成；CI 上会缺失，也会悄悄过期 | 以编程方式重新生成 session（API-login helper 或 `setup` project）；manual files 只作为带 programmatic fallback 的 cache |
| 23 | **Fixture ignores render guards** | Liked-tab fixture seed 了 `liked: false`；card component 对每个 item 都 `return null`，让空 UI 看起来像 infra flake | 在 seeding 前读取 item component 的 early returns/filters；seed fields 以通过被测 view 的每个 guard |

</details>

## 失败调试

两个 debugger 使用同一套稳定的 F1–F15 root-cause taxonomy。Playwright 接受 `playwright-report/`、HTML reports、`trace.zip`、screenshots 和有界的 GitHub Actions artifacts。Cypress 接受 mochawesome 或 JUnit reports、screenshots、videos 和有界 CI artifacts。

<details>
<summary>查看 F1–F15 taxonomy</summary>

| # | 类别 | 信号 |
|---|----------|---------|
| F1 | **Flaky / Timing** | `TimeoutError`，retry 后通过 |
| F2 | **Selector Broken** | `locator not found`，strict mode violation |
| F3 | **Network Dependency** | `net::ERR_*`，unexpected API response |
| F4 | **Assertion Mismatch** | `Expected X to equal Y`，subject-inversion |
| F5 | **Missing Then** | Action completed 但错误状态仍然存在 |
| F6 | **Condition Branch Missing** | Element conditionally present，但 assertion 总是运行 |
| F7 | **Test Isolation Failure** | 单独运行通过，suite 中失败 |
| F8 | **Environment Mismatch** | 只在 CI vs local 出现；viewport、OS、timezone |
| F9 | **Data Dependency** | 缺失 seed data，hardcoded IDs |
| F10 | **Auth / Session** | Session expired，role-based UI 未渲染 |
| F11 | **Async Order Assumption** | `Promise.all` order，parallel race |
| F12 | **POM / Locator Drift** | DOM structure changed，POM 未更新 |
| F13 | **Error Swallowing** | `.catch(() => {})` 隐藏实际 failure |
| F14 | **Animation Race** | Content 尚未渲染，或 transient element 在被观察前移除 |
| F15 | **Hydration Race** | Action 成功但没有效果：SSR page 尚未 hydrated；在下一个 assertion 失败 |

</details>

debuggers 会把产品回归与脆弱测试分开分类，并返回证据和具体修复。没有失败的 Playwright 或 Cypress 测试 artifact 时，它们不会诊断应用或 backend。

## 独立扫描器

直接运行确定性的机械层：

```bash
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

扫描器需要 Python 3 和支持 PCRE2 的 `rg`。默认情况下，它不会执行目标项目控制的 ESLint binaries、plugins、parsers 或 configuration，也不会下载工具。`E2E_SMELL_ALLOW_PROJECT_ESLINT=1` 会让可信 checkout 进入项目 ESLint 执行；`E2E_SMELL_NO_ESLINT_DOWNLOAD=0` 和 `E2E_SMELL_NO_AST_GREP_DOWNLOAD=0` 会分别选择启用 pinned downloads。当 portability check 必须忽略 host 预装 binaries 时，设置 `E2E_SMELL_DISABLE_AST_GREP=1`。

> **读取边界。**
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> Bundled checks 会报告请求路径下的 source。Framework provenance resolution 也可能读取同一项目其他位置的相对 fixture/support imports。
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->

Tier 3 是内置 fallback。可选的 ESLint 和 ast-grep tiers 会提高精度，但不会替代语义审查。扫描器遇到基础设施或文件系统错误时会以 2 退出，而不是报告虚假的 clean 结果。参见 [SECURITY.md](SECURITY.md) 了解 trust 和 network boundary。

## 它与 ESLint plugins 有何不同

`eslint-plugin-playwright` 和 `eslint-plugin-cypress` 是很好的每次提交基线，用于 syntactic rules。`e2e-skills` 另外提供两层能力：

- secure-default scanner，除非显式启用，否则不会运行目标项目的 lint stack
- 对需要测试意图或跨文件上下文的发现做 semantic review

linter 可以捕获直接的 Locator truthiness assertion 或缺失的 `await`。它无法判断名为“shows a duplicate-name error”的测试是否真的检查了该错误，protected-route test 是否忘了认证，或 optimistic UI assertion 是否证明了 backend request 发生。用 plugins 做持续 linting，用 `e2e-reviewer` 判断测试可信度。

<a id="open-source-adoption"></a>

## 开源采用

`e2e-reviewer` 的发现已促成 **14 个合入上游的 PR**。这些自选案例展示了实际使用，也让读者可以检查修复；它们不是代表性 validation sample 或 accuracy estimate。

| 仓库 | PR | 已修复模式 |
| --- | --- | --- |
| Storybook | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Playwright assertions 缺失 `await` |
| code-server | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | Focused test leak、matcher-less `expect`、被丢弃的 visibility read |
| Strapi | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | 被丢弃的 navigation/state checks |
| SvelteKit | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | Floating Playwright assertions |
| Carbon Design System | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | Locator truthiness 替换为 web-first assertions |
| Ghost | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise-valued disabled-state assertion |
| Cal.com | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | E2E flow 中的 weak assertion patterns |
| Bruno | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | Assertion 和 wait reliability fixes |
| Qwik | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/handle existence checks |
| Element Web | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator null-check style assertions |
| MUI X | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | UI handle checks 替换为 state assertions |
| module-federation/core | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Cypress spec 中冗余的 blanket `uncaught:exception` suppression |
| FiftyOne | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Locator-defined check 替换为可见的 duplicate-name error assertion |
| Rancher Desktop | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `not.toBeNull()` locator checks 替换为可见的 WSL integration-name assertions |

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

### 如何审查 AI 生成的 E2E 测试？

合并前，将生成的 spec 交给 `e2e-reviewer`。它会检查每个测试是否真正证明了名称所描述的用户可见结果，并区分确定性的扫描候选项和需要结合上下文判断的发现。

### 它是否同时支持 Cypress 和 Playwright？

审查和失败调试支持两个框架。新测试生成目前只支持 Playwright。Cypress debuggers 接受 mochawesome 和 JUnit reports。

### 它能调试只在 CI 中失败的测试吗？

可以，前提是你提供本地 report artifacts 或受支持的 GitHub Actions run。debugger 会使用 F1–F15 taxonomy 区分 environment、timing、selector、data、authentication 和 product-regression causes。

### 支持哪些 AI 编程代理？

Claude Code、Codex，以及 `skills` CLI 支持的 55+ 宿主都可以加载公开的 `SKILL.md` contracts。可选的 host-specific agent files 会在可用时改善委派；即使没有这些文件，public Skills 仍然可用。

## 详细文档

- [24 Playwright and Cypress E2E test smells](docs/e2e-test-smells.md)
- [Open-source case studies](docs/case-studies.md)
- [Benchmark status and negative results](benchmarks/STATUS.md)
- [External evidence ledger](docs/llm-generated-e2e-test-evidence.md)
- [Historical AI reviewer benchmark](docs/ai-reviewer-benchmark.md)
- [Debugger benchmark protocol](docs/debugger-benchmark/README.md)
- [Framework scope](docs/framework-scope.md)
- [Roadmap](docs/roadmap.md)

计划中的工作包括 cross-model convention consistency 和更强的确定性检测。在对应的专门验证通过之前，任何 roadmap item 都不会被描述为已交付。

## 贡献

欢迎提交 bug reports、false-positive guards、新 anti-patterns 和 translations。请从 [CONTRIBUTING.md](CONTRIBUTING.md) 开始了解 setup 和 verification requirements。跨代理维护契约位于 [AGENTS.md](AGENTS.md)。

## 许可证

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha)。参见 [LICENSE](LICENSE)。
