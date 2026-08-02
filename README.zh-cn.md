<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — 面向 Playwright 和 Cypress 的 Agent Skills：生成、审查并调试可靠的端到端测试。" width="100%" />
</div>

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-4-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#开源采用与案例证据"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-14-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://agents.md"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="https://www.npmjs.com/package/eslint-plugin-cypress-silent-pass"><img alt="cypress silent-pass npm" src="https://img.shields.io/npm/v/eslint-plugin-cypress-silent-pass?style=flat-square&label=cypress%20lint&labelColor=black&color=37B0E6"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<a href="README.md">🇺🇸 English</a> | <a href="README.ko.md">🇰🇷 한국어</a> | <a href="README.ja.md">🇯🇵 日本語</a> | <strong>🇨🇳 简体中文</strong>
</p>

<!-- README-CANONICAL-REVISION: sha256=d43f04103606ac031358ffc49d8212f8d3699598bb43a7eccf442b6bd0bc41c6; bytes=exact-README.md-UTF-8; translation-quality=not-attested -->

找出那些能通过 CI，却几乎证明不了任何东西的 Playwright/Cypress 端到端测试。

**开源采用案例——`e2e-reviewer` 的发现已用于 [14 个合入上游的 PR](#开源采用与案例证据)**，涉及 SvelteKit、Storybook、code-server、Strapi、Carbon Design System、Ghost 和 MUI X 等仓库。

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

## 方法论

生成测试很容易。更难的是生成一个在产品出错时**能够正确失败的测试**。LLM 可以写出语法有效、能够执行预期流程的测试，却因为恒真 assertion、错误的状态检查或缺失的结果验证而一直保持 green。

这并非只有理论上的风险。[Test Smells in LLM-Generated Unit Tests](https://arxiv.org/abs/2410.10628) 分析了 20,505 个生成 test suite；一项包含 86 名开发者的对照研究中，错误 LLM-generated postcondition 的正确识别率仅为 [49.0%](https://arxiv.org/abs/2607.08885)。不过这些都是 unit-level oracle 研究，并非 browser E2E fault detection，因此本仓库只把它们当作设计依据，而不是 E2E accuracy 估计。

因此，这组 skills 采用 review-first 方法，而不是直接相信 green run：

1. 在编写或接受 assertion 之前，先明确测试应该证明的 behavior。
2. 优先使用 framework-native、retry-aware、能够因为正确原因失败的 assertions。
3. 即使 CI 是 green，也拒绝 always-truthy assertions、缺失的 post-state checks，以及 name↔assertion mismatches。
4. 对机械性 smells 使用 deterministic checks，只把 semantic judgment 交给 LLM review。

### 更多证据与实践资料

- **已审计 source ledger：** [LLM-generated test evidence review](docs/llm-generated-e2e-test-evidence.md) 将指定的 59 个 source 分为 21 个 verified、14 个 qualified 和 24 个 not cleared。它修正误导性的 denominator，保留被拒绝或收窄的 claim，并把向 browser E2E 的外推作为单独步骤处理。
- **已有直接的 browser E2E 研究，但范围仍然有限：** peer-reviewed [WebTestPilot](https://doi.org/10.1145/3797115) 在 4 个 open-source app 上用 100 个手工注入 bug 评估 Playwright-backed browser-oracle system，报告 96% precision/recall。另一项 real-bug replication study 检出了 23 个 GitHub issue bug 中的 22 个。但它评估的是一个 custom agent/benchmark，而不是普通 reusable suite、本 skill 或 sealed production sample。
- **生产过滤：** Meta 的 [TestGen-LLM study](https://doi.org/10.1145/3663529.3663839) 使用 build、stable-pass 和 coverage filter。57% 与 25% 的分母是单个生成 test case，而不是 test class 或 mutation-based fault detection。
- **Pass-rate 偏差：** [Python study](https://arxiv.org/abs/2412.14137) 表明，在当前 buggy program 上失败的 candidate 可能被修复或丢弃，使 final suite 固化 bug。68.1% 是特定 tool/data set 的结果，不是 browser E2E prevalence。
- **Wait-fault repair 证据：** WEFix 从 7 个 open-source project 中删除开发者添加的 waits，重构出 122 个 UI-wait flaky test，并修复了其中 120 个。这是 Cypress 和 Selenium wait fault repair 的直接 peer-reviewed evidence，不是 Playwright generation 或自然抽样 flake prevalence 估计。
- **Peer-reviewed autonomous E2E generation：** AutoE2E 是 agentic E2E generation 的 peer-reviewed evidence，但不能证明本 skill 的 reviewer accuracy 或 reusable-suite fault detection rate。
- **Browser industry evidence：** Slack 的 [Playwright agent study](https://slack.engineering/agentic-testing-where-agents-fit-in-the-e2e-testing-stack/) 在 5 configurations 和 2 个 test-workspace flow 中观察到 simple flow 约 8%、medium flow 约 48% 的 execution failure。“20 runs” 究竟是 independent generation，还是经过迭代修改的 test 的重复执行并不明确，因此 ledger 将 denominator 标为 qualified。它没有测量 semantic correctness 或 mutant kill。
- **Vendor limitations：** [Vitest](https://vitest.dev/guide/learn/writing-tests-with-ai#do-the-tests-actually-assert-something-meaningful) 警告 no-throw 与 mock-focused test 会带来 false confidence。[Cypress](https://docs.cypress.io/app/guides/cypress-studio#types-of-assertions-studio-ai-recommends) 明确 Studio AI 无法访问 business logic/backend rules；[Playwright](https://playwright.dev/docs/aria-snapshots#partial-matching) 则记录了省略 accessible name 的 ARIA snapshot 会无视 label 继续 pass。
- **框架依据：** [Playwright assertions](https://playwright.dev/docs/test-assertions) 和 [Cypress retry-ability](https://docs.cypress.io/app/core-concepts/retry-ability) 提供了这些检查背后的 native contract。
- **Runtime 先例：** [`playwright-mutation-gate`](https://github.com/VladyslavDmitriiev/playwright-mutation-gate) 展示 assertion/behavior mutation， [`ai-qa-pipeline`](https://github.com/VladyslavDmitriiev/ai-qa-pipeline) 展示独立 writer/judge、有限 repair、scratch candidate 和 post-debug review。
- **行为支撑的 fault injection：** `scripts/evals/run-fixture-faults.py` 用 36 个 browser cell 验证 Playwright/Cypress 的 12 个 fault operator。每个强测试在正确行为下 pass，在注入 app fault 后 fail，而削弱 assertion 或 call proof 的 mutant 面对同一 fault 仍保持 green。当前 2026-07-31 archive 是完整的 36/36 cell，并包含 unnamed ARIA snapshot label-fault operator。
- **精确的因果 reviewer linkage：** `scripts/evals/reviewer-fault-causal-v3.json` 是当前 public exact-artifact benchmark。它保留 10 个 byte-identical operator mutant，只 neutralize 2 条 answer-leading comment，并保留 12 个独立 clean guard。`causal-v2` 因 answer-leading comments 泄露预期 verdict，对当前 claim 来说是 historical/invalid。它衡量已证实 false-green shape 的 reviewer detection，是 public development evidence，不衡量 generator quality。
- **Floating Promise 语义控制：** 单独的 Playwright 1.62 六单元 probe 只删除会触发 fault 的 #15 和 #16 call 前面的 `await`。两个 unawaited mutation 仍然 exit 1，因此不把这两个案例计为 weak-green mutant；证据支持的是 P1 sequencing/attribution 风险，而不是无条件的 P0 always-pass。
- **Zero-timeout 语义控制：** 单独的 Playwright 1.62 #4g probe 记录精确的 `1/0/1` exit：100ms assertion 在延迟 DOM 更新前 fail，`{ timeout: 0 }` 会持续 retry 并在更新后 pass，而缺失 target 会在 enclosing test timeout 时 fail。这证明 zero timeout 删除的是 matcher-local deadline，而不是把检查变成 one-shot。
- **当前 reviewer holdout：** `scripts/evals/reviewer-holdout-v5.json` 是当前 pre-live public development corpus。它在 20 个 repository-shaped case 和 50 个 source file 中分离 24 个 exact finding 与 24 个 matched false-positive guard：12 个 positive case、8 个 globally clean case，并保持 Playwright/Cypress 10/10 split。live run 前 independent positive/clean source audit 已通过。`v4` 在 oracle audit 后对 performance claim 来说是 historical/invalid，且只执行过 3 个 diagnostic call。
- **已声明的跨模型重复测量与 control：** v5 protocol 要求完整的 9-report model/arm matrix：`full`、`catalog-only`、`no-skill` 分别在 Codex、Claude Opus、Claude Fable 上运行。它在 live call 前固定 schedule、3-run majority rule、每个 model 的 threshold、provider-family 等权重和 arm-comparison gate。descriptive partial metrics 可以发布，但 partial result 不能支持 causal、release-grade、generalized 或 skill-lift claim。report 固定 corpus、semantic skill payload、protocol、prompt、schedule、CLI、model、Git state、timing、raw output 和运行前后 workspace digest。这里不声明任何 live v5 result。
- **Fresh-context 的精选子集 review：** independent-review runner 排除 holdout、eval、benchmark result、scorecard、过往 review 和 Git history，从明确选取的 high-signal contract 与 implementation 中冻结 prompt-complete packet。每个 zero-tool finding 都必须引用 packet 内的原始 file/line。[v1 review/remediation archive](benchmarks/independent-product-review-v1/) 中 preregistered v4 repetition 得分为 90.50、92.50、91.50，但第一次 attempt 的 1 个 High 使 all-three gate 失败。[v5 remediation-confirmation archive](benchmarks/independent-product-review-v5-remediation/) 也以 87.33、88.00、88.00 分保持 `COMPLETE` / `FAIL`。raw-ARIA DNS-boundary High 已修复为仅允许 canonical numeric loopback，另一个 High 则由 executable scanner regression 证明是 false positive。[v6 selected-remediation archive](benchmarks/independent-product-review-v6-remediation/) 在 pre-call independent audit 中被发现 byte budget 作用于 transformed source 而非实际的 line-annotated prompt，因此在没有任何 packet、attempt 或 model call 的情况下以 `SUPERSEDED_BEFORE_FREEZE` / `NOT_RUN` 结束。修正后的 [v7 archive](benchmarks/independent-product-review-v7-remediation/) 保持原有阈值不变，并分别限制 transformed source、annotated content、canonical packet 与 rendered prompt，最终以 `COMPLETE` / `FAIL` 完成。三个 Codex attempt 得分为 91.83、92.83、93.33，但第三次并非因为分数，而是重新打开了一个 bound remediation target 而未通过 gate。[v8 remediation-confirmation archive](benchmarks/independent-product-review-v8-remediation/) 同样是 `COMPLETE` / `FAIL`：一次因 runner 非零退出而 `INCONCLUSIVE`，一次以 87.67 分并带两个 High finding，一次以 92.67 分通过。已完成的 v8 FAIL 的 5 个 finding，加上归档后由内部 adversarial re-review 关闭的 4 类缺陷，作为 9 个 bound target 预注册在 [`independent-review-remediation-ledger-v10.json`](scripts/evals/independent-review-remediation-ledger-v10.json) 中。V9 因为本操作者已无法运行其 Codex 专用 host，在 [`independent-review-v9-supersession.json`](scripts/evals/independent-review-v9-supersession.json) 中记为 `SUPERSEDED_BEFORE_FREEZE` / `NOT_RUN`；后继的 v10 仅使用 `claude-opus-5` 与 `claude-fable-5`，是 Claude 专用。两个 model 属于同一 provider family，因此即使 v10 完成，也只是 Anthropic 内部的 cross-model，而不是 cross-provider 证据。在第一次 model call 之前，v10 以缩减后的 packet 重新预注册。两次独立的 pre-call audit 将 33 个 surface 的 packet prompt 测得 877,407 字节，并确认 `claude-opus-5` 会因长度直接拒绝它；protocol 将该拒绝记为 `INCONCLUSIVE`，而预注册的三次 attempt 中有两次使用该 model。现在冻结的 packet 只包含 9 个 bound target 所指的 7 个 surface，prompt 为 440,800 字节，`claude-opus-5` 与 `claude-fable-5` 都能接受。因此 v10 中没有任何 target 被重新打开这一结果，只是关于这 7 个 surface 的证据，而不是关于其他产品 surface 的证据。V10 同样不声明 context window 与 output reserve 预算，因为没有 local 来源能确定这两个 model 的 context window：prompt 大小仅以精确的 UTF-8 字节和固定的 `o200k_base` 计数来限制。该计数只是可复现的大小 proxy，既不是 model 自身的 tokenization，也不是 prompt 能放进任何 context window 的证据。V4、v5、v7 与 v8 的失败保持不变，v6 与 v9 不是 benchmark result。runner/model 标识只是 caller-declared 的 local provenance，不是 remote vendor/model attestation。这些 curated review 不是 unbiased defect discovery、full-product coverage、skill-accuracy estimate、human/sealed review、independent ground truth 或 remote attestation。
- **Debugger coverage：** `scripts/evals/debugger-holdout-v1.json` 提供 30 个短 sanitized report excerpt，在每个 framework 中各覆盖一次 F1–F15。schema-v2 report 使用 strict-majority stable unique-case metrics 与 Wilson intervals、repeated accuracy 和 macro precision、framework/category worst slices，并通过 raw-output re-deriving comparator 在固定的 Codex / Claude Opus / Claude Fable provider-family matrix 上重新解析 raw output 和重新计算 score。label 仍是 author-created synthetic label，未经过 independent oracle audit。参见 [debugger benchmark protocol](docs/debugger-benchmark/README.md)。
- **Generator fault-kill planning：** `scripts/evals/generator-faultkill-v1.py` 把封闭的 declarative plan language compile 成 trusted Playwright template，评估 behavior、label、auth、write fault，并评分 case、fault-mode macro 和 worst-case performance。`generator-validation-protocol-v2.json` 定义了跨 `full-skill`、`rules-only`、`no-skill` 的 prompt-complete 27-call runner，但目前还没有 live v2 result。它衡量把既定 acceptance criteria 忠实 encoding 到 frozen planning DSL 的能力，不声称 source generation、autonomous oracle discovery，也不执行 model-generated code。
- **可审计的负面结果：** [`benchmarks/reviewer-holdout-v2/`](benchmarks/reviewer-holdout-v2/) 固化了初始 oracle、Claude/Codex raw report、catalog-only control、oracle revision ledger 和强化后的重跑。该重跑完成了 Codex 24/24 次调用，但未通过 precision gate；事后独立判定又确认 4 个 stable “false positive” 全部是 oracle 遗漏。我们没有改写分数，而是把它保留为该 corpus 不足以估计性能的证据。
- **旧版技能效果 smoke：** `scripts/evals/run-behavioral-evals.py` 仍会重复比较 `with_skill` 和 `without_skill`，报告每个 case 的 lift，并标记被 baseline 饱和的 case。
- **不修改目标项目的 package：** e2e-skills 将适用语义独立实现为本地 Playwright/Cypress 规则和 V1–V7 验证契约。应用这些技能不会在目标项目中添加或修改 dependency 或 package 文件。已有的 project-native runner 和规则会被复用；另行披露的安装与 scanner 路径可能调用 `npx` 等外部工具。

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
$ /bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests/

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
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

`skills` CLI 是推荐的 Codex 安装方式。它会把四个技能副本放到 `~/.agents/skills/`，Codex 直接发现其中的 `SKILL.md`。该路径不会安装仓库根目录的 `.codex-plugin/plugin.json`；这个接口 manifest 仅用于下面的 Codex plugin marketplace 路径：

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a codex
```

此命令仅安装到 Codex。若还要安装到 Claude Code，请另行运行上面的 Claude
Code 命令。

备选方案——Codex 插件市场：

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

当 Codex 宿主提供 native role routing 时，`e2e-reviewer`、
`playwright-debugger` 和 `cypress-debugger` 无需额外安装 custom agent
即可使用内置的 `verifier` / `debugger` 子智能体角色。native delegation
不可用时，这三个技能的 inline fallback 仍保持相同判定或 failure taxonomy。
`playwright-test-generator` 的边界更严格：V6 需要一个独立的、
fresh-context、read-only reviewer。无法提供这个独立 context 时，它会报告
`CANNOT_VERIFY` 和 `PARTIAL/BLOCKED`，而不会把 inline review 声称为等价验证。
源码 checkout 还包含 `.codex/agents/` 下更严格的 named agent。
`reinstall-skills.sh` 默认不会安装这些 global agent。贡献者可以单独运行
`bash scripts/dev/install-codex-agents.sh`，或设置
`E2E_SKILLS_INSTALL_CODEX_AGENTS=1` 进行明确的一体化重装，然后重启 Codex。

### 其他所有智能体 (Cursor, OpenCode, Gemini CLI 等)

跨智能体的 `skills` CLI 支持 55+ 个宿主。一条命令即可为它支持的所有智能体全局安装：

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all
```

如果只想安装到某一个智能体，把 `--all` 换成 `-a <agent>` 即可（如 `-a cursor`、`-a opencode`、`-a gemini-cli`），参见[支持的智能体列表](https://github.com/vercel-labs/skills#supported-agents)。

以上命令固定了已验证的 `skills` CLI 版本，避免全局安装时执行未经审查的新版本。升级前请查看 release note，并显式修改版本号。

### 手动克隆（Claude Code）

Claude Code 仅会把 `~/.claude/skills/` 的直接子目录识别为个人技能。
请将仓库 checkout 放在该目录之外，再通过
[官方支持的逐技能符号链接](https://code.claude.com/docs/en/skills#where-skills-live)
暴露四个技能根目录：

```bash
git clone https://github.com/voidmatcha/e2e-skills.git "$HOME/.claude/e2e-skills"
mkdir -p "$HOME/.claude/skills"

for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
  ln -s "$HOME/.claude/e2e-skills/skills/$skill" "$HOME/.claude/skills/$skill"
done
```

如果同名技能已经存在，链接命令会失败而不会覆盖它。请在 Claude Code
中运行 `/skills`，确认四个名称都已显示。

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

## 开源采用与案例证据

`e2e-reviewer` 的发现已被用于在多个知名仓库中合入 **14 个上游 PR**，包括 SvelteKit、Storybook、code-server、Strapi、Carbon Design System、Ghost、Cal.com、Bruno、Qwik、Element Web、MUI X 和 Rancher Desktop。这些自行选择的贡献展示了采用情况并提供了具体案例证据，但不是具有代表性的验证样本或准确率估计。

作为历史参考，一个由模型编写的 pilot 检查了 77 个 repository 中 100 个已由 AI reviewer review 过的开源 PR。judge 建立了 110 个 E2E test-trust issue 的 reference label set；`e2e-reviewer` 匹配其中 78 个，并且该样本中没有被 judge 判定为 false positive 的 finding。lint 匹配 45 个，general AI PR reviewer 的 inline spec comment 匹配 10 个。由于 judge 不是中立的 ground truth，这个 pilot 只是存档的案例证据，而不是当前产品验证或证明。见 [方法论与局限](docs/ai-reviewer-benchmark.md)。

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
[P1] settings.spec.ts:88, 99 — #4h One-shot URL read
expect(page.url()).toEqual(`${baseURL}/${id}-public`);
→ await expect(page).toHaveURL(`${baseURL}/${id}-public`);

[P1] fileUpload.spec.ts:67 — #16 Missing await on action
page.getByRole('button', { name: 'Delete' }).click();
→ await page.getByRole('button', { name: 'Delete' }).click();

Total: 0 P0, 2 P1, 0 P2 in 24 spec files.
```

<a id="scanner-findings-are-candidates-not-verdicts"></a>

## 独立扫描器

```bash
./skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

扫描器的三个 Tier 提供不同保证。只有设置 `E2E_SMELL_ALLOW_PROJECT_ESLINT=1` 时，Tier 1 才会执行目标项目的 ESLint stack。只有存在可信的 `ast-grep`/`sg` executable，或显式启用固定版本的 `npx` fallback 时，Tier 2 才会执行。输出出现 Tier 2 heading 表示该层已执行；没有 heading 表示该层不可用或已禁用。在成功完成的 scan 中，Tier 3 会执行内置 PCRE2 check，作为 grep 可判定 pattern 的 fallback，但不会重现所有仅 AST 可识别的 Tier 2 match。Agent Skill 负责扫描结果周围需要理解意图的审查。

统一 source 边界覆盖 `.ts`、`.js`、`.tsx`、`.jsx`、`.mts`、`.mjs`、`.cts` 和 `.cjs`。枚举扩展名后再判断 framework content，因此 `login.e2e.ts` 等 custom Playwright `testMatch` 名称不会因 basename 被漏掉。内置 lexical filter 会把字符串中的 focused-test token 排除在 #7 P0 gate 之外，并且无需 optional AST tool 也能检查多行 #4f Locator assertion。扫描器必须同时具备支持 PCRE2 的 `rg` 和 Python 3。Python 会创建并验证 NUL-safe candidate identity record，使 candidate drift 或错误 record 以 fail-closed 方式终止；这项必需的 bookkeeping 与 optional Tier 2 AST tooling 相互独立。engine/filesystem 错误会以 exit 2 失败，而不是伪装成 clean。suppression 只接受真实的 `// JUSTIFIED: <非空理由>` 注释。

> **信任边界与网络行为。** 默认扫描器不会执行目标仓库中的 executable、plugin、parser 或 ESLint config。
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> 内置检查只报告指定路径下的 source。不过在解析 framework provenance 时，它可能读取同一上层项目内、指定路径之外的相对 fixture/support import。
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->
> 扫描器不含 telemetry 或有意的网络操作。即使指定路径只是 subdirectory，也会拒绝目标 project 内通过 PATH 解析到的 `rg`、`ast-grep`、`sg`。`E2E_SMELL_ALLOW_PROJECT_ESLINT=1` 会显式允许执行目标项目的本地 ESLint stack；该模式会缩减环境变量并只传入 E2E 范围文件，但它不是 sandbox，受信任的项目代码仍可读写可访问文件、启动进程或使用网络。旧版 `npx` download 是独立 opt-in，只能通过 `E2E_SMELL_NO_ESLINT_DOWNLOAD=0` / `E2E_SMELL_NO_AST_GREP_DOWNLOAD=0` 启用。完整说明见 [SECURITY.md](./SECURITY.md)。

## Skill 1: `playwright-test-generator` — 测试生成

从零为任意项目生成 Playwright 端到端测试。它先分析覆盖缺口，再通过浏览器自动化探索本地或一次性应用，在你批准下设计场景。远程实时探索仅限于外部隔离、受控浏览器环境中的明确获批非生产目标；共享、生产或状态不明的远程目标只使用用户提供且已净化的快照。生成的测试会由 `e2e-reviewer` 自动审查。

> **对于允许实时探索的目标，建议：** 先配置浏览器工具——[Playwright MCP](https://github.com/microsoft/playwright-mcp#getting-started) 或 `webapp-testing` 技能。若没有，本地或一次性目标可回退到只看页面初始状态的静态 ARIA 快照；而仅允许快照的远程目标必须由用户提供已净化的快照。内置的可执行 preflight 会验证 URL/IP 分类并固定所有 DNS peer；它不使用 ambient `PATH`，而是绑定并记录可信的绝对 curl 路径及哈希，同时在含 credential 或有歧义的 query 进入进程参数前将其拒绝。普通的非 secret 路由参数可以保留。只有当所有 peer 一致返回 `401`/`403`，或重定向到已验证的同源登录 URL 时，才证明受保护路由可达，而不是成功。

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
3. **有边界的探索**——仅对本地、一次性目标或外部隔离且获批的非生产远程目标进行实时浏览器探索；共享、生产或状态不明的远程目标使用用户提供且已净化的快照，并通过可执行的 URL/DNS/redirect preflight 和真实 accessible name 防止臆造选择器
4. **场景设计 + 批准关卡**——在编写任何代码前展示计划和定位器表格
5. **代码生成**——POM + spec 或扁平 spec，根据项目约定自动检测；改变状态的 flow 必须在实际写入边界受控。浏览器 request 是边界时使用 route/intercept；写入发生在 server/backend 时使用 disposable、支持 rollback 或隔离的环境（见 `code-rules.md` 中的 Network Determinism）
6. **约定与种子脚手架**（在项目上首次运行时）——向 `AGENTS.md` 追加一节针对项目适配的端到端内容，并指定一个种子 spec，从而让未来 AI 生成的测试（Claude Code、Codex、Playwright Agents）保持一致
7. **YAGNI 审计 + e2e-reviewer**——移除未使用的定位器，在首次运行前捕捉 P0 问题
8. **TS 编译 + 测试运行**——失败时进行 3 次自动修复尝试（按意图修复的定位器重新解析），随后移交给 `playwright-debugger`

---

## Skill 2: `e2e-reviewer` — 质量审查

捕捉那些能通过 CI、却抓不到真实回归的端到端测试问题。

每条 semantic finding 在报告前都会经过 refute-first 的 adversarial 验证 —— 在 Claude Code 插件安装中由 read-only 子代理执行，在其他宿主中则 inline 执行。这一审查流程会减少缺乏依据的 finding，但不保证在每个 repository 中都得到同样结果。

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
| 4 | **空泛或削弱重试的断言**（P0/P1） | P0：恒真条件与 Locator truthiness。P1：薄弱的 attachment 证明、一次性值/URL、zero-timeout retry/deadline 风险、未证明的缺失、遗漏约定 accessible name 的 ARIA snapshot | 使用有意义的边界与自动重试的 web-first assertion；在断言缺失前先证明存在，并让约定的 accessible name 参与验证 |
| 5 | **绕过模式**（5a P0，5b P1） | `if (await el.isVisible()) { expect(...) }`；无注释的 `{ force: true }` | 始终进行断言；把环境检查移到 `beforeEach`；给 force:true 添加 `// JUSTIFIED:` |
| 7 | **聚焦测试泄漏** | 提交了 `test.only(...)`——CI 只运行一个测试，静默跳过其余 | 删除 `.only`；用 `--grep` 或 `--spec` 做本地聚焦 |
| 8 | **缺失断言** | 被丢弃的 locator/布尔值是场景唯一的验证 | 添加 `await expect(locator).toBeVisible()`；已有独立验证/失败证据时跳过 #8 |
| 12 | **缺失鉴权设置** | 没有登录/`storageState`/鉴权 fixture 时，通用断言仍会匹配登录页或错误页面，导致受保护路由的 spec 通过 | 添加 `beforeEach` 登录、`storageState` 或鉴权 fixture；不要把因缺失鉴权而正常失败的情况归为 P0 |

#### P1 — 应当修复（诊断信息差 / 浪费 CI 时间）

测试能工作，但会误导开发者、浪费 CI 时间，或为将来的回归埋下隐患。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 6 | **原生 DOM 查询** | `evaluate()` 中的 `document.querySelector` | 使用框架的定位器/查询 API（`locator` / `cy.get`） |
| 9 | **硬编码 sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | 依赖框架的自动等待；使用基于条件的等待 |
| 10 | **不稳定测试模式** | 无注释的 `items.nth(2)`；`test.describe.serial()`；未限定范围的 accessible-name substring（10c）；Cypress async callback、被赋值的 `cy` command、action 后继续 chaining（10d–10f） | 使用稳定且有 scope 的 locator 和自包含测试；把 Cypress 工作保留在 command chain 中，不把 Chainable 当值赋给变量，并在 action 后重新 query |
| 13 | **POM 使用不一致** | 导入了 POM，但 spec 对 POM 所属动作使用原生 `page.fill`/`page.click` | 让所有交互都经过 POM，这样 UI 变更只需在一处更新 |
| 14 | **硬编码凭据** | 测试代码中的 `loginPage.login('demo-admin', '<literal-password>')` | 使用 `process.env.TEST_USER`、Playwright 配置密钥或测试数据 fixture |
| 15 | **`expect()` 上缺失 `await`** | 异步 Locator/Page web-first matcher Promise 未被排序或观察，拒绝通常稍后以较差归因报告 | `await` 或返回 matcher Promise；同步值 matcher 不在范围内 |
| 16 | **动作上缺失 `await`** | actionability、动作顺序或导航可能与后续工作竞争，拒绝归因通常会变差 | `await` 或返回动作 Promise |
| 17 | **不建议直接使用 Page selector API** | 基于 selector 的 `page.click`、`page.fill` 及相关 Page action 跳过了 Locator 层 | 使用 Locator action 以获得组合、strictness、复用和更清晰的失败信息 |
| 18 | **`expect.soft()` 滥用** | 关键 soft assertion 在 hard scenario gate 之前运行，前置条件损坏后依赖操作仍会继续 | 先用 hard assertion 验证主要状态；`soft` 只用于独立细节 |
| 19 | **测试代码中的模块级可变状态** | 测试工具中位于第 0 列的 `let testNotebookSequence = 0;`——会在长生命周期 worker 的测试间残留，并在并行 worker 之间冲突 | 去掉该计数器；用 `Date.now()` + `Math.random().toString(36).slice(2, 8)` 派生唯一性，或把状态移入 `test.beforeEach` |
| 20 | **未打桩的真实后端写操作** | 注册/结账 spec 在没有受控测试边界的情况下写入共享或持久状态 | 对写操作打桩，或证明后端采用一次性容器、回滚 fixture、隔离租户/数据库等受控策略 |
| 22 | **没有调用证明的乐观 UI** | 点赞切换测试断言 `aria-pressed` 翻转——UI 乐观更新，即使删掉 POST 也能通过 | 把 UI 断言与 `page.waitForRequest()`（在点击前预先设置）或路由命中标志配对 |

#### P2 — 建议修复（可维护性 / 健壮性）

弱但不算错——在重构时处理。

| # | 模式 | 修改前 | 修改后 |
|---|---------|--------|-------|
| 11 | **YAGNI + 僵尸 Spec** | `clickEdit()` 从未被调用；无依据的空包装类；整个 spec 被另一个重复 | 删除未使用的成员和僵尸 spec；只有在明显减少无意义间接层时才内联单次使用的 helper |
| 21 | **手动捕获的会话文件依赖** | `storageState: 'auth/member.json'` 仅由手动捕获脚本生成——在 CI 上缺失，会静默过期 | 以编程方式重新生成会话（API 登录辅助或 `setup` 项目）；手动文件仅作为带编程回退的缓存 |
| 23 | **Fixture 忽略渲染守卫** | 点赞标签页 fixture 种入 `liked: false`；卡片组件对每一项 `return null`——空白 UI 看起来像基础设施抖动 | 在种入数据前先读取项组件的提前返回/过滤条件；为被测视图种入能通过每个守卫的字段 |

### 仅靠 lint 无法确定的内容

**静态检查器能查出一个断言写得规不规范，却查不出这个测试到底有没有证明它名字里声称的东西。** 测试声称的意图和它实际验证的内容，中间这道缝正是 `e2e-reviewer` 要找的核心，而任何逐文件的 AST 或 grep 规则都看不见它：`should show an error when the name is duplicate` 可以在一个从不触及错误的断言下通过，语法却毫无瑕疵。要判定它，得把测试的名称、它执行的动作以及周围的代码放在一起读，这比单文件规则的运作层级高出一层。

只有在信任兼容的项目本地插件并设置
`E2E_SMELL_ALLOW_PROJECT_ESLINT=1` 时，`e2e-reviewer` 才会复用
`eslint-plugin-playwright` / `eslint-plugin-cypress` 检查部分机械规则
（`#6`、`#7`、`#9`、`#15`、`#16`、`#5a`、`#5b`），再由内置
scanner 补充。规则版本、配置、receiver provenance 和多行格式都会影响
coverage，因此不能把插件视为完整覆盖。Locator 真值断言（`#4f`）已有
官方 `eslint-plugin-playwright` 的
[`no-unnecessary-assertions`](https://github.com/mskelton/eslint-plugin-playwright/pull/470)
规则（v2.11.0，`recommended`），Cypress 的相关形状则由
[`eslint-plugin-cypress-silent-pass`](https://github.com/voidmatcha/eslint-plugin-cypress-silent-pass)
补充。之所以仍需要 semantic review，是因为有些坏味道**无法仅靠单文件
AST 或 grep 判定**；必须读取其他函数、组件、CI 配置和测试自身的意图。

| 坏味道 | 为什么 lint 无法判定 |
|-------|---------------------------|
| `#1` 名称与断言不匹配 | 需要把测试的*名称/意图*与它实际断言的内容进行比较。从语法上看断言没问题。 |
| `#3` / `#3b` 吞掉错误与一刀切的 `cy.on('uncaught:exception', () => false)` | 语法有效；只有意图才能揭示它禁用了失败。一个单行正则在某个套件中漏掉了 **51 处多行实例**。 |
| `#4f` Locator 当作真值（`expect(locator).toBeTruthy()` / `.toBeDefined()` / `.not.toBeNull()`） | framework-aware rule 能捕获直接的 Locator 形状；alias、POM property 和 helper 返回的 Locator 仍需 semantic trace。 |
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

> **注意：** 既可以传入本地报告路径，也可以直接给出 GitHub Actions 的 run。用户确认严格的 `owner/repo` slug 和数字 run ID 后，bounded `gh api` helper 会在 `github.com` 上解析并绑定 repository 数字 ID，使用不依赖当前 checkout 配置的显式 endpoint，并在不把 extraction 目标交给 `gh` 的情况下下载固定 artifact；fork PR 的 run 会被拒绝。

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

<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->
`e2e-reviewer` 技能会审查分类目录中的全部 24 个模式，每个模式都有稳定 ID 和 P0/P1/P2 严重级别。独立的 `scan.sh` 扫描器只覆盖其中可确定性判断的机械子集。扫描器匹配是候选项，不是最终结论；技能会检查测试意图和周边代码后再确认 finding。

调试器使用稳定的 F1–F15 分类体系对失败分类。只有在你信任仓库并批准包含环境变量和参数的准确命令后，调试器和生成器才会执行目标仓库代码。

对于非公开 benchmark，`--isolation-wrapper` 是必需的 hook，但不是隔离证明。持续集成（CI）会验证 wrapper contract，但不会证明 filesystem、process 或 network 已隔离。
<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

24 个模式目录包括静默常绿缺陷、断言与 Locator/Page Object Model（POM）操作缺失 `await`、一次性 `isVisible()` 读取和提交的 `.only` 泄漏。缺失 `await` 是 P1 的执行顺序与失败归因风险，不代表必然静默通过。

### 它与 eslint-plugin-playwright 或 eslint-plugin-cypress 有何不同？

eslint plugin 是每次提交时的语法规则 baseline。扫描器默认不会执行目标项目的 lint stack；请单独运行项目 lint，或仅在受信任的 checkout 中通过 `E2E_SMELL_ALLOW_PROJECT_ESLINT=1` 启用第 1 层。此时项目 flat config 会叠加在 plugin 的 `recommended` 之上，因此有意关闭的 rule 在第 1 层仍保持关闭。新增的一层是[仅靠 lint 无法确定](#仅靠-lint-无法确定的内容)的坏味道：名称/断言不匹配、swallowed error、未验证的删除、missing-auth route 都需要读取其他 function、component、CI config 与 test intent。Locator truthiness 这类可由单文件 lint 判定的问题由官方 `no-unnecessary-assertions` 和内置 scanner 处理。

### 这不就是又一个像 CodeRabbit、Copilot 或 Cursor BugBot 那样的 AI 代码审查器吗？

那些都是出色的通用审查器——其中几个对开源免费，而且现在可以本地运行（CodeRabbit 的 CLI 会在终端里审查已暂存的改动）。区别在于专精，而非能力：通用审查器对任何交给它的 diff 进行推理，而 `e2e-reviewer` 携带一份精心整理、稳定、按严重程度分级的端到端静默永远通过反模式目录（24 种带固定 ID 的模式，外加 15 种失败调试分类），并按需针对整个 spec 目录运行，而不仅是一个 PR diff。通用审查器可用于一切；当你在意的是端到端测试的可信度时，就用这个。由模型编写的历史 100-PR 对比作为样本限定的案例证据保存在 [AI 审查器基准测试](docs/ai-reviewer-benchmark.md) 中，而不是当前验证。

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

另外，上游贡献路线图追踪着更广的流水线：**已合并 14、审查中 6、排队 8**。队列里只放经过审核的 1,000+ 星候选——实时表格见[上游贡献](docs/roadmap.md)。

## 贡献

欢迎提交缺陷报告、误报防护、新的反模式和翻译。请从 [CONTRIBUTING.md](./CONTRIBUTING.md) 开始，了解环境搭建、验证关卡（`/bin/bash -p scripts/ci/ci-local.sh`）以及冻结 ID / 一致性约定。更深入的跨智能体细节见 [AGENTS.md](./AGENTS.md)。

## 许可证

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha)。见 [LICENSE](./LICENSE)。
