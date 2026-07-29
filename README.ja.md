<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — Playwright と Cypress のためのエージェントスキル：信頼できるエンドツーエンドテストの生成・レビュー・デバッグ。" width="100%" />
</div>

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-4-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#オープンソースでの実績"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-14-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://agents.md"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="https://www.npmjs.com/package/eslint-plugin-cypress-silent-pass"><img alt="cypress silent-pass npm" src="https://img.shields.io/npm/v/eslint-plugin-cypress-silent-pass?style=flat-square&label=cypress%20lint&labelColor=black&color=37B0E6"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<a href="README.md">🇺🇸 English</a> | <a href="README.ko.md">🇰🇷 한국어</a> | <strong>🇯🇵 日本語</strong> | <a href="README.zh-cn.md">🇨🇳 简体中文</a>
</p>

CI は通るのに、ほとんど何も証明していない Playwright/Cypress の E2E テストを見つけ出します。

**机上の空論ではありません。`e2e-reviewer` の指摘は [14 件のマージ済みアップストリーム PR](#オープンソースでの実績) につながっています。** 対象には SvelteKit、Storybook、code-server、Strapi、Carbon Design System、Ghost、MUI X といった実在のリポジトリが含まれます。

> そのうちの 1 つが code-server（78k&#9733;）でした。`it.only` が 7 か月にわたって 8 件のテストを黙って無効化しており、そのうち 1 件はすでに壊れていました。その間、CI はずっとグリーンのままでした。

`e2e-skills` は、エンドツーエンドテストを「静かにグリーン」にしてしまう失敗モードを扱う Agent Skills のバンドルと決定論的スキャナーです。弱いアサーション、`await` の欠落、破棄された待機/読み取り、条件でガードされたアサーション、フォーカスされたままのテスト、エラーの一括抑制がその対象です。

テストランナーでもなければ、幅広い lint プリセットや汎用のブラウザ自動化ツールキットでもありません。問うのはこれだけです。

> この E2E テストは、ユーザーに見える挙動が実際に壊れたときに失敗するか？

## なぜ存在するのか

AI エージェントは E2E テストを素早く生成してくれます。ただ、その多くは一見説得力があるのに、ユーザーに見える状態ではなくハンドルや Promise、一回きりのスナップショットしか検証していません。

```diff
- expect(page.getByText('SWE')).toBeDefined()
+ await expect(page.getByText('SWE')).toBeVisible()
```

1 行目は Playwright の `Locator` オブジェクトが存在することしか証明しません。2 行目はユーザーがそのテキストを見られることを証明します。

生成されたテストの問題はサイレントパスだけではありません。モデルは YAGNI や KISS といった原則を無視して、どこからも使われないコードを生み出します — どのテストからも呼ばれないメソッドだらけの Page Object のように。複数のモデルが同じスイートに書き込むと、スタイルがばらばらになる問題もあります。このバンドルは役割を分担します。使われない抽象化はレビュアーが #11（YAGNI + ゾンビ spec）として検出し、ジェネレーターは初回実行時にプロジェクトの規約（`AGENTS.md` の E2E セクションとシード spec）をスキャフォールドして、以降どのモデルにも同じスタイルで書かせます。より深い自動推論版は[ロードマップ](#ロードマップ)にあります。

`e2e-skills` はこれを再現可能なレビューワークフローに落とし込みます。

1. 決定論的なサイレントパスのスメルをスキャンする
2. 意図が曖昧な E2E テストを Agent Skill でレビューする
3. フローのカバレッジが欠けていれば、より良い Playwright テストを生成する
4. 失敗した Playwright/Cypress のレポートをデバッグし、根本原因の修正につなげる

## 方法論

テストを生成するのは簡単です。製品が間違っているときに**正しく失敗するテスト**を作ることの方が困難です。LLM は構文的に正しく意図したフローを実行していても、常に真になる assertion、誤った状態の検証、結果検証の欠落によって green で終わるテストを生成できます。

これは仮説上のリスクだけではありません。[Test Smells in LLM-Generated Unit Tests](https://arxiv.org/abs/2410.10628) は複数のモデル群が生成した 20,505 件のテストを分析しています。[強い LLM-generated test oracle の研究](https://arxiv.org/abs/2405.03786) は、単なる実行ではなく assertion の品質を bug detection の中核として扱います。[Cypress の産業事例研究](https://doi.org/10.1109/AST66626.2025.00007) でも、生成された acceptance test の一部は再生成が必要、または重大な問題により破棄されました。

そのため、このスキル群は green run をそのまま信頼せず、review-first の方法を採ります。

1. テストを書く、または受け入れる前に、そのテストが証明すべき behavior を名付けます。
2. 正しい理由で失敗できる framework-native、retry-aware な assertion を優先します。
3. CI が green でも、always-truthy assertion、欠落した post-state check、name↔assertion mismatch は拒否します。
4. 機械的に判定できる smell は deterministic check で検出し、semantic judgment が必要な箇所だけ LLM review を使います。

### 追加の根拠と実務資料

- **本番環境の方法論:** Meta の [LLM-based test improvement 研究](https://arxiv.org/abs/2402.09171) は、生成テストをそのまま採用せず、測定可能な改善でフィルタします。
- **Assertion の信頼性:** [ChatGPT vs SBST](https://doi.org/10.1109/TSE.2024.3382365) は coverage と assertion correctness を別々に評価し、誤って生成された expected value の事例を報告しています。
- **実践的な反証:** [Your green tests are lying](https://dev.to/dubcrab/your-green-tests-are-lying-5h5m) は、assertion を反転しても green のままなら、そのテストは主張を証明していないという方法を示します。
- **実務家からの報告:** Playwright の実務家も同じ weak-green-test 問題を独立して指摘しています（[David Kirwan](https://www.linkedin.com/posts/davidjkirwan_most-ai-generated-playwright-tests-are-not-activity-7436406467827527680-vy32)、[Michal Jarczewski](https://www.linkedin.com/posts/michal-jarczewski_your-ai-generated-test-is-green-that-does-activity-7475305026672885760-qKF8)、[Aston Cook](https://www.linkedin.com/posts/aston-cook_save-this-if-your-playwright-tests-pass-when-activity-7473185238395797504-_ag4)）。これらは学術的証拠ではなく practitioner signal です。
- **関心度のシグナル:** [Gen AI Promised Perfect Tests. Here's What Actually Happened](https://www.youtube.com/watch?v=TjTygGqP5JQ) は 2026-07-28 時点で 74,797 views でした。変動する view count は正しさの証拠ではなく、関心度のシグナルにすぎません。
- **フレームワーク上の根拠:** [Playwright assertions](https://playwright.dev/docs/test-assertions) と [Cypress retry-ability](https://docs.cypress.io/app/core-concepts/retry-ability) が検査基準の native contract を提供します。
- **Runtime の先行事例:** [`playwright-mutation-gate`](https://github.com/VladyslavDmitriiev/playwright-mutation-gate) は assertion/behavior mutation を、[`ai-qa-pipeline`](https://github.com/VladyslavDmitriiev/ai-qa-pipeline) は独立した writer/judge、制限付き repair、scratch candidate、post-debug review を示しています。
- **スキル効果の測定:** `scripts/evals/run-behavioral-evals.py` は `with_skill` と `without_skill` を繰り返し比較し、ケースごとの lift と baseline の飽和を報告します。実モデルの実行は opt-in であり、一般的な precision/recall やモデル間の優位性を主張するものではありません。
- **依存関係なしの採用:** e2e-skills は適用可能な意味をローカルの Playwright/Cypress ルールと V1–V6 検証契約として独立実装します。これらのプロジェクト、ESLint plugin、package install、`npx` は必須ではなく、既存の project-native runner とルールがあれば再利用します。

## 動作を見る

CI は通るのに何も検証していない Playwright テストの例です。`Locator` は決して undefined にならず、`.not.toBeNull()` は要素が描画されていてもいなくても成立します。

```ts
test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();   // always passes
  expect(page.locator('.user-badge')).not.toBeNull();     // always passes
});
```

スキャナーは設定不要で、両方を決定論的に検出します。

```console
$ bash skills/e2e-reviewer/scripts/scan.sh tests/

[P0] #4f Locator always-true assertion (truthy/defined/not-null) (2 hits)
  tests/login.spec.ts:6:  expect(page.getByText('Welcome back')).toBeDefined();
  tests/login.spec.ts:8:  expect(page.locator('.user-badge')).not.toBeNull();

Summary: 2 total hit(s), 2 P0
```

## 一目でわかる使い分け

| 目的 | 使うもの |
| --- | --- |
| 新しい Playwright E2E カバレッジを生成する | [`playwright-test-generator`](#スキル-1-playwright-test-generator--テスト生成) |
| 既存の Playwright/Cypress テストをサイレントパスのスメルについてレビューする | [`e2e-reviewer`](#スキル-2-e2e-reviewer--品質レビュー) |
| 失敗した Playwright レポートをデバッグする | [`playwright-debugger`](#スキル-3-playwright-debugger--playwright-失敗デバッガー) |
| 失敗した Cypress レポートをデバッグする | [`cypress-debugger`](#スキル-4-cypress-debugger--cypress-失敗デバッガー) |
| 決定論的なローカルスキャンを実行する | [`skills/e2e-reviewer/scripts/scan.sh`](#スタンドアロンスキャナー) |

参考ドキュメント: [ケーススタディ](docs/case-studies.md)、[ロードマップ](docs/roadmap.md)、[24 種のスメル分類](docs/e2e-test-smells.md)、[フレームワークスコープ](docs/framework-scope.md)、[AI レビュアーベンチマーク](docs/ai-reviewer-benchmark.md)。

## インストール

インストール方法はホストによって異なります: [Claude Code](#claude-code) · [Codex](#codex) · [その他のエージェント](#その他のエージェント-cursor-opencode-gemini-cli-など) · [手動クローン](#手動クローン-claude-code)

### Claude Code

プラグインマーケットプレイスから:

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

またはクロスエージェントの `skills` CLI から:

```bash
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

Codex では `skills` CLI が推奨ルートです。バンドルは `~/.agents/skills/` に配置され、Codex はそこでスキルを検出し、インターフェイスブロックとして `.codex-plugin/plugin.json` を読み込みます。

```bash
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code -a codex
```

別の方法 — Codex プラグインマーケットプレイス:

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

Codex ホストが native role routing を提供する場合、custom agent を追加インストールせずに組み込みの `verifier` / `debugger` サブエージェント役割を利用でき、native delegation がない環境でもスキルの inline fallback が同じ判定を維持します。ソース checkout には `.codex/agents/` のより厳格な named agent も含まれます。他のリポジトリでもその名前を使うコントリビューターは、`bash scripts/dev/install-codex-agents.sh` でグローバルに登録してから Codex を再起動してください。

### その他のエージェント (Cursor, OpenCode, Gemini CLI など)

クロスエージェントの `skills` CLI は 55 以上のホストに対応しています。次の 1 コマンドで、対応するすべてのエージェントにグローバルインストールできます:

```bash
npx skills add voidmatcha/e2e-skills -g --all
```

特定のエージェントだけに入れる場合は、`--all` の代わりに `-a <agent>` を指定してください（例: `-a cursor`、`-a opencode`、`-a gemini-cli`）。[対応エージェント一覧](https://github.com/vercel-labs/skills#supported-agents)を参照してください。

### 手動クローン (Claude Code)

```bash
git clone https://github.com/voidmatcha/e2e-skills.git ~/.claude/skills/e2e-skills
```

## 試してみる

```text
Review my Playwright tests in tests/e2e with e2e-reviewer.
```

```text
Generate Playwright E2E coverage for apps/web/e2e.
```

```text
Debug the failed Playwright report in playwright-report/.
```

## 使いどころ

`e2e-skills` が向いているのは次のような場合です。

- Playwright/Cypress のテストは通っているものの、実際にユーザーに見える状態を検証できているか確信が持てない。
- AI が生成した E2E テストに、マージ前の品質ゲートが必要。
- スイートに `locator().toBeTruthy()`、`not.toBeNull()`、`await` されていない `expect(...)`、破棄された `isVisible()`、`waitForTimeout()`、`it.only`、グローバルな `uncaught:exception` 抑制といった疑わしいパターンが含まれている。
- 構文だけでなく、テストの意図までエージェントにレビューさせたい。

次の用途には使わないでください。

- アプリケーションと実際の E2E スイートを実行することの代わりとして
- 汎用の lint プリセットとして
- あらゆる不安定なテストを直すという約束として
- フレームワークを問わないテストツールとして。サポート対象は Playwright と Cypress です。

## オープンソースでの実績

作り物の実績ではありません。`e2e-reviewer` の指摘をもとに、SvelteKit、Storybook、code-server、Strapi、Carbon Design System、Ghost、Cal.com、Bruno、Qwik、Element Web、MUI X、Rancher Desktop など、よく知られたリポジトリで **14 件のアップストリーム PR** がマージされています。

この実績は再現可能な pilot benchmark とも対応しています。AI reviewer が review 済みの OSS PR 100 件（77 repository）で、neutral LLM judge が material な E2E test-trust issue 110 件を特定し、`e2e-reviewer` はそのうち 78 件を 0 false positive で検出しました。lint は 45 件、general AI PR reviewer の inline spec comment は 10 件を検出しました。[方法論と case evidence](docs/ai-reviewer-benchmark.md) を参照してください。

マージ済みの修正一覧:

| リポジトリ | PR | 修正したパターン |
| --- | --- | --- |
| Storybook | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Playwright アサーションの `await` 欠落 |
| code-server | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | フォーカステストの残留、matcher のない `expect`、破棄された可視性読み取り |
| Strapi | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | 破棄されたナビゲーション/状態チェック |
| SvelteKit | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | 待たれないままの Playwright アサーション |
| Carbon Design System | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | Locator の truthy 判定を web-first アサーションに置き換え |
| Ghost | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise のままの disabled 状態アサーション |
| Cal.com | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | E2E フローの弱いアサーションパターン |
| Bruno | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | アサーションと待機の信頼性修正 |
| Qwik | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/ハンドルの存在チェック |
| Element Web | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator の null チェック型アサーション |
| MUI X | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | UI ハンドルチェックを状態アサーションに置き換え |
| module-federation/core | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Cypress spec から冗長な一括 `uncaught:exception` 抑制を削除 |
| FiftyOne | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Locator 定義の確認を可視の重複名エラーアサーションに置き換え |
| Rancher Desktop | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `not.toBeNull()` の Locator チェックを可視の WSL 統合名アサーションに置き換え |

## ワークフロー

```text
1. Ask e2e-reviewer to inspect the target test directory.
2. Confirm P0 findings first: these are silent-pass or always-green risks.
3. Patch one smell family at a time.
4. Re-run the deterministic scanner and the target E2E/lint checks.
5. Use playwright-debugger or cypress-debugger only for real failed reports.
```

レビュアーの出力例:

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

## スタンドアロンスキャナー

```bash
./skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

このスキャナーはあえて決定論的に作ってあります。確度の高いサブセットはスキャナーが拾い、その結果を踏まえた意図面のレビューは Agent Skill が引き受けます。

> **ネットワーク動作について。** スキャナーは指定されたファイルだけを読み取り、何もアップロードしません。プロジェクトに存在する場合はローカルの ESLint と Playwright/Cypress plugin を直接実行し、デフォルトではパッケージを自動ダウンロードしません。依存関係のない regex/AST fallback でオフライン実行できます。従来の `npx` ダウンロードは `E2E_SMELL_NO_ESLINT_DOWNLOAD` と `E2E_SMELL_NO_AST_GREP_DOWNLOAD` を空にして明示的に有効化できます。詳細な開示は [SECURITY.md](./SECURITY.md) を参照してください。

## スキル 1: `playwright-test-generator` — テスト生成

あらゆるプロジェクトで Playwright の E2E テストをゼロから生成します。カバレッジギャップの分析から始め、ブラウザ自動化ツール（Playwright MCP / webapp-testing）で実際に動いているアプリを探索し、承認を得ながらシナリオを設計し、生成したテストを `e2e-reviewer` で自動レビューします。

> **推奨:** まずブラウザツールを設定してください — [Playwright MCP](https://github.com/microsoft/playwright-mcp#getting-started) または `webapp-testing` スキル。ない場合はページの初期状態のみを見る静的 ARIA スナップショットにフォールバックし（操作不可）、単純なページには十分ですが実際のフロー（モーダル・送信後・エラー状態・多段階）には限定的です。

### 使いどころ

- E2E カバレッジがまったくないページや機能がある
- 既存アプリのテストスイートを立ち上げたい
- リリース前に手早くテストを追加する必要がある

### 使い方

```
Generate playwright tests
Generate playwright tests for the login page
Write e2e tests for the settings page
Add playwright coverage for checkout flow
```

### パイプライン

1. **環境検出** — 設定、baseURL、テストディレクトリ、POM 構造、既存の規約ドキュメント
2. **カバレッジギャップ分析** — 対象はユーザーが選択（引数で対象が指定された場合はスキップ）
3. **ライブブラウザ探索** — ブラウザ自動化ツール経由（[Playwright MCP](https://github.com/microsoft/playwright-mcp#getting-started) / webapp-testing。でっち上げたセレクターは使わない）。ラベルのない入力にはアクセシブルネームの実地確認を行う
4. **シナリオ設計 + 承認ゲート** — コードを書く前に計画とロケーターテーブルを提示
5. **コード生成** — POM + spec かフラットな spec かをプロジェクトの規約から自動判別。書き込み系はルートスタブ必須（`code-rules.md` の Network Determinism を参照）
6. **規約とシードのスキャフォールディング**（プロジェクト初回のみ）— プロジェクトに合わせた E2E セクションを `AGENTS.md` に追記し、シード spec を指定。以降の AI 生成テスト（Claude Code、Codex、Playwright Agents）の一貫性を保つ
7. **YAGNI 監査 + e2e-reviewer** — 未使用のロケーターを削除し、初回実行前に P0 の問題を検出
8. **TS コンパイル + テスト実行** — 失敗時は自動修正を 3 回試行（意図ベースのロケーター再解決による修復）し、その後 `playwright-debugger` に引き継ぐ

---

## スキル 2: `e2e-reviewer` — 品質レビュー

CI は通るのに実際のリグレッションを捕まえられない E2E テストの問題を検出します。

すべての finding は報告前に refute-first で adversarial に検証されます — Claude Code のプラグインインストールでは read-only のサブエージェントで、それ以外のホストでは inline で。この独立した検証パスが、ベンチマークで false positive をゼロに保った仕組みです。

### 使いどころ

- テストは常に通るのに、バグは本番まですり抜けている
- CI は通るが、実際のリグレッションを見逃していると疑っている
- テストスイートが脆く、UI を変更するたびにテストが壊れる
- リリースやコードレビューの前にテスト品質を監査したい
- Playwright または Cypress の spec をレビューしている

### 使い方

```
Review my E2E tests
Audit the spec files in tests/
Find weak tests in my test suite
My tests always pass but miss bugs
Tests pass CI but miss regressions
My tests are fragile and break on every UI change
We have coverage but bugs still slip through
```

### 検出する 24 パターン — 重大度別

#### P0 — 必須修正（サイレントな常時パス）

機能が壊れていてもテストが通ってしまいます。実質的な検証が行われていません。

| # | パターン | Before | After |
|---|---------|--------|-------|
| 1 | **テスト名とアサーションの不一致** | 名前は「status」なのに `toBeVisible()` しか確認していない | status の内容に対するアサーションを追加するか、実際の検証内容に合わせて改名する |
| 2 | **Then の欠落** | キャンセル操作後にテキストの復元は検証 — しかし入力欄はまだ表示されたまま？ | 復元された状態と閉じられた状態の両方を検証する |
| 3 | **エラーの握りつぶし** | spec 内の `try/catch`、POM 内の `.catch(() => {})` | エラーで失敗させる。POM メソッドから silent catch を取り除く |
| 3b | **Cypress の `uncaught:exception` 抑制** | `cy.on('uncaught:exception', () => false)` がアプリのエラーを一括で握りつぶす | ハンドラーを既知の特定エラーに限定し、未知のエラーは再スローする |
| 4 | **常にパスするアサーション** | `toBeGreaterThanOrEqual(0)`; コメントなしの `toBeAttached()`; `expect(await el.isVisible()).toBe(true)`（ワンショット）; `expect(await el.textContent()).toBe(x)`（ワンショット）; `expect(locator).toBeTruthy()`（Locator は常に truthy）; アサーションでの `{ timeout: 0 }`（リトライ無効化）; マッチしうることが一度も証明されていない locator への不在アサーション（4i, P1） | `toBeGreaterThan(0)`; `toBeVisible()`; 自動リトライ付きの web-first アサーション; 消えたことを検証する前に、まず存在を一度検証する |
| 5 | **バイパスパターン**（5a P0、5b P1） | `if (await el.isVisible()) { expect(...) }`; コメントなしの `{ force: true }` | 常にアサートする。環境チェックは `beforeEach` に移し、force:true には `// JUSTIFIED:` を添える |
| 7 | **フォーカステストの残留** | `test.only(...)` がコミットされ、CI は 1 件だけ実行して残りを黙ってスキップ | `.only` を削除し、ローカルでの絞り込みには `--grep` や `--spec` を使う |
| 8 | **アサーションの欠落** | `await page.locator('.x');`（破棄）; `await el.isVisible();`（真偽値が捨てられている） | `await expect(locator).toBeVisible()` を追加するか、その行を削除する |
| 12 | **認証セットアップの欠落** | 保護ルートの spec が、ログイン/`storageState`/認証フィクスチャなしで `/dashboard` に遷移する | `beforeEach` でのログイン追加、`storageState` の設定、または認証フィクスチャの利用 — さもないとログインページに対してテストが通ってしまう |
| 15 | **`expect()` の `await` 欠落** | `expect(page.locator('.toast')).toBeVisible()` が観測されない Promise を返す | `await` を追加してアサーションを実際に実行させる |
| 16 | **アクションの `await` 欠落** | `page.locator('#submit').click()` が次の行までに実行されない可能性がある | `await` を追加してアクションを完了させる |

#### P1 — 修正推奨（診断性の低下 / CI 時間の浪費）

テストは動くものの、開発者を誤解させたり、CI 時間を浪費したり、将来のリグレッションの温床になったりします。

| # | パターン | Before | After |
|---|---------|--------|-------|
| 6 | **生の DOM クエリ** | `evaluate()` 内の `document.querySelector` | フレームワークのロケーター/クエリ API（`locator` / `cy.get`）を使う |
| 9 | **ハードコードされたスリープ** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | フレームワークの自動待機に任せ、条件ベースの待機を使う |
| 10 | **フレーキーテストのパターン** | コメントなしの `items.nth(2)`; `test.describe.serial()`; scope されていない accessible-name substring（10c）; Cypress の async callback、代入された `cy` command、action 後に続く chain（10d–10f） | 安定して scope された locator と自己完結型テストを使い、Cypress 処理は command chain 内に置き、Chainable を値として代入せず、action 後は再 query する |
| 13 | **一貫しない POM 利用** | POM をインポートしているのに、POM が担うべき操作を生の `page.fill`/`page.click` で行っている | すべての操作を POM 経由にし、UI 変更時の修正箇所を一箇所にまとめる |
| 14 | **ハードコードされた認証情報** | テストコード内の `loginPage.login('demo-admin', '<literal-password>')` | `process.env.TEST_USER`、Playwright config のシークレット、またはテストデータフィクスチャを使う |
| 17 | **直接の `page.click(selector)` API** | `page.click('#submit')` / `page.fill('#input', 'text')` は Locator 層を素通りする | 自動待機とわかりやすいエラーメッセージのために `page.locator(selector).click()` を使う |
| 18 | **`expect.soft()` の乱用** | テスト内のアサーションがすべて `expect.soft()` で、テストが決して早期に失敗しない | 各テストに最低 1 つはハードな `expect()` のゲートを置き、`soft` は独立した詳細の確認だけに使う |
| 19 | **テストコードのモジュールレベル可変状態** | テストユーティリティのカラム 0 にある `let testNotebookSequence = 0;` — 並列ワーカー間で衝突し、リトライをまたいで残り続ける | カウンターをやめて `Date.now()` + `Math.random().toString(36).slice(2, 8)` から一意性を導き出すか、状態を `test.beforeEach` に移す |
| 20 | **モックされていない実バックエンドへの書き込み** | サインアップ/チェックアウトの spec が実ミューテーションを送信し、CI 実行のたびに実アカウント/注文が作られる | 書き込み・認証系エンドポイントを `page.route()` / `cy.intercept()` でスタブ化する。実バックエンドへのスモーク spec は指定した 1 本まで |
| 22 | **呼び出しの証拠がない楽観的 UI** | いいねトグルのテストが `aria-pressed` の切り替えだけをアサート — UI は楽観的に更新されるため、POST を削除しても通ってしまう | UI アサーションに、（クリック前に仕掛けた）`page.waitForRequest()` またはルート到達フラグを組み合わせる |

#### P2 — 余裕があれば修正（保守性 / 堅牢性）

弱いものの誤りではないパターンです。リファクタリングの際に対処します。

| # | パターン | Before | After |
|---|---------|--------|-------|
| 11 | **YAGNI + ゾンビ spec** | 一度も呼ばれない `clickEdit()`; 空のラッパークラス; 一度しか使われない Util; 別の spec と丸ごと重複した spec | 未使用メンバーの削除、単一利用の Util メソッドのインライン化、ゾンビ spec ファイルの削除 |
| 21 | **手動キャプチャしたセッションファイルへの依存** | 手動のキャプチャスクリプトでしか生成されない `storageState: 'auth/member.json'` — CI には存在せず、黙って期限切れになる | セッションをプログラムで再生成する（API ログインヘルパーまたは `setup` プロジェクト）。手動ファイルはプログラムによるフォールバック付きのキャッシュとしてのみ使う |
| 23 | **レンダーガードを無視したフィクスチャ** | いいねタブのフィクスチャが `liked: false` をシードし、カードコンポーネントが全項目を `return null` する — 空の UI がインフラ起因のフレークに見える | シードする前に項目コンポーネントの early return やフィルターを読み、対象ビューのすべてのガードを通過する値をシードする |

### リンターが構造的に検出できないもの

**リンターが確認できるのはアサーションの形式までで、テストがその名前の主張どおりのことを証明しているかは判定できません。** テストの宣言された意図と実際に検証している内容のあいだのギャップこそ、`e2e-reviewer` が探すものの核心であり、ファイル単位の AST ルールや grep ルールからは見えません。`should show an error when the name is duplicate` というテストは、エラーに一切触れないアサーションでも通ってしまい、構文は完璧です。それを判定するにはテストの名前、実行するアクション、周囲のコードを合わせて読む必要があり、単一ファイルのルールが動くレベルより一段上の作業になります。

`e2e-reviewer` は第 1 ティアとして `eslint-plugin-playwright` / `eslint-plugin-cypress` を実行するため、機械的なルール（`#6`、`#7`、`#9`、`#15`、`#16`、`#5a`、`#5b`）はデファクトスタンダードのプラグインで既にカバーされています。常にパスする Locator アサーションのスメル（`#4f`）も今やカバーされます — 本プロジェクトから公式 `eslint-plugin-playwright` に [`no-unnecessary-assertions`](https://github.com/mskelton/eslint-plugin-playwright/pull/470) ルールとして貢献してv2.11.0 でリリースされ、`recommended` 設定で既定で有効です、Cypress 側は [`eslint-plugin-cypress-silent-pass`](https://github.com/voidmatcha/eslint-plugin-cypress-silent-pass) がカバーします。その上に `e2e-reviewer` を重ねる理由は、**どんな AST ルールや grep ルールも届かない**スメルにあります。それらを確認するには、他の関数、コンポーネント、CI 設定、テスト自身の意図といった、ルールが決して見ないコードまで読む必要があるからです。

| スメル | lint が判定できない理由 |
|-------|---------------------------|
| `#1` テスト名とアサーションの不一致 | テストの*名前/意図*と実際にアサートしている内容を比較する必要がある。構文的にはアサーションに問題はない。 |
| `#3` / `#3b` エラーの握りつぶしと一括の `cy.on('uncaught:exception', () => false)` | 構文としては正当で、失敗を無効化していることは意図からしかわからない。単一行の正規表現は、あるスイートで**複数行にまたがる 51 件**を見逃した。 |
| `#4f` Locator の truthy 扱い（`expect(locator).toBeTruthy()` / `.toBeDefined()` / `.not.toBeNull()`） | 普通のアサーションに見える。Locator が決して falsy にならないと*知っていて*初めて、常にパスするとわかる。 |
| `#4` ワンショット読み取り（`expect(await el.isVisible()).toBe(true)`） | 正当な `expect` であり、リトライしない一時点の読み取りだと知って初めてアンチパターンだとわかる。 |
| `#12` 認証セットアップの欠落 | ルートが未認証であることを知るには、設定・フィクスチャ・`storageState` にまたがるファイル横断の推論が必要。 |
| `#20` / `#22` モックなしの書き込み / 呼び出し証拠のない楽観的 UI | エンドポイントがミューテーションを行うこと、あるいは UI がネットワークアサーションの裏付けなしに楽観的に更新されることを知っている必要がある。 |
| `#11` / `#23` ゾンビ spec / レンダーガードを無視したフィクスチャ | ファイル横断の作業。重複 spec の検出や、シードを信頼する前にコンポーネントの early `return null` を読むこと。 |
| **最難関のケース** | *決して throw しない*関数を `try/catch` で包み、`catch` の中でだけアサートしている（実例: xyflow の `graph-utils.cy.ts` の `addEdge`）。確認するには別ファイルにある関数本体を読む必要があり、grep やあらゆる単一ファイル AST ルールには不可能。 |

ここはパターンマッチではなく判断が必要な部分です。`e2e-reviewer` は、候補が指摘になる前に周囲のコードと CI 設定を読んで**検証**します。前述の [candidates-not-verdicts](#scanner-findings-are-candidates-not-verdicts) の規律です。だからこそ、すべての指摘には生のマッチではなく、その場しのぎの修正を避けた（band-aid-aware）修正案が添えられます。

### 参考資料

[Playwright best practices](https://playwright.dev/docs/best-practices) · [Cypress best practices](https://docs.cypress.io/app/core-concepts/best-practices) · [Testing Library guiding principles](https://testing-library.com/docs/guiding-principles)

---

## スキル 3: `playwright-debugger` — Playwright 失敗デバッガー

`playwright-report/` ディレクトリから Playwright テストの失敗を診断します。失敗がローカルで起きたか CI で起きたかは問いません。根本原因を分類し、具体的な修正を提示します。

### 使いどころ

- 内容を把握したい失敗を含む `playwright-report/` ディレクトリ（ローカル、または CI からダウンロード）がある
- テストがローカルでは通るのに CI では失敗する
- フレーキーで断続的なテスト失敗に悩まされている
- 明確な原因が見えない `TimeoutError` や `locator not found` が出る

### 使い方

```
Debug these failing tests
Why did these tests fail?
Tests pass locally but fail in CI
```

> **注:** レポートはローカルパスで渡すか、GitHub Actions の run をそのまま渡してください — スキルがユーザー確認済みの run ID で `gh run download` を実行し、アーティファクトを自分でダウンロードします（フォーク PR の run は対象外）。

### 15 の根本原因カテゴリー

| # | カテゴリー | シグナル |
|---|----------|---------|
| F1 | **フレーキー / タイミング** | `TimeoutError`、リトライすると成功する |
| F2 | **セレクター破損** | `locator not found`、strict モード違反 |
| F3 | **ネットワーク依存** | `net::ERR_*`、想定外の API レスポンス |
| F4 | **アサーション不一致** | `Expected X to equal Y`、主語の取り違え（subject-inversion） |
| F5 | **Then の欠落** | アクションは完了したのに誤った状態が残っている |
| F6 | **条件分岐の欠落** | 要素が条件付きでしか存在しないのに、アサーションが常に実行される |
| F7 | **テスト分離の失敗** | 単体では通るがスイート内では失敗する |
| F8 | **環境不一致** | CI とローカルの一方でのみ発生。ビューポート、OS、タイムゾーン |
| F9 | **データ依存** | シードデータの欠落、ハードコードされた ID |
| F10 | **認証 / セッション** | セッション期限切れ、ロール依存の UI が描画されない |
| F11 | **非同期順序の思い込み** | `Promise.all` の順序、並列実行のレース |
| F12 | **POM / ロケーターのドリフト** | DOM 構造が変わったのに POM が更新されていない |
| F13 | **エラーの握りつぶし** | 実際の失敗を隠す `.catch(() => {})` |
| F14 | **アニメーションレース** | コンテンツがまだ描画されていない、または一時的な要素が観測される前に削除される |
| F15 | **ハイドレーションレース** | アクションは成功するのに効果がない — SSR ページがまだハイドレーションされておらず、次のアサーションで失敗する |

### デバッグワークフロー

1. **抽出** — `results.json` をパースし、失敗したテスト、エラーメッセージ、所要時間を取得
2. **分類** — エラーシグナルに基づき各失敗を F1–F15 に対応付け（ほとんどの失敗はここで解決）
3. **トレース** — まだ不明なら `trace.zip` を展開してステップごとに調査: 失敗したアクション、DOM スナップショット、ネットワークエラー、JS コンソールエラー
4. **修正** — 失敗ごとに具体的なコード提案を P0/P1/P2 の優先度付きで提示

---

## スキル 4: `cypress-debugger` — Cypress 失敗デバッガー

mochawesome または JUnit のレポートファイルから Cypress テストの失敗を診断します。根本原因を分類し、具体的な修正を提示します。

### 使いどころ

- 内容を把握したい失敗を含む `cypress/reports/` ディレクトリ（ローカル、または CI からダウンロード）がある
- Cypress テストがローカルでは通るのに CI では失敗する
- フレーキーで断続的な Cypress の失敗に悩まされている
- 明確な原因が見えない `Timed out retrying` や `Expected to find element` が出る

### 使い方

```
Debug these failing Cypress tests
Why did these Cypress tests fail?
Analyze cypress/reports/
Cypress tests pass locally but fail in CI
```

### 15 の根本原因カテゴリー

| # | カテゴリー | シグナル |
|---|----------|---------|
| F1 | **フレーキー / タイミング** | `Timed out retrying`、リトライすると成功する |
| F2 | **セレクター破損** | `Expected to find element`、`cy.get() failed` |
| F3 | **ネットワーク依存** | `cy.intercept()` がマッチしない、`XHR failed` |
| F4 | **アサーション不一致** | `expected X to equal Y`、`AssertionError` |
| F5 | **Then の欠落** | アクションは完了したのに誤った状態が残っている |
| F6 | **条件分岐の欠落** | 要素が条件付きでしか存在しないのに、アサーションが常に実行される |
| F7 | **テスト分離の失敗** | 単体では通るがスイート内では失敗する |
| F8 | **環境不一致** | CI とローカルの一方でのみ発生。baseUrl、ビューポート、OS |
| F9 | **データ依存** | シードデータの欠落、`cy.fixture()` の不一致 |
| F10 | **認証 / セッション** | `cy.session()` の期限切れ、ロール依存の UI が描画されない |
| F11 | **コマンドキュー / インターセプトのレース** | リクエスト発火後に登録された `cy.intercept`、`.then()` チェーンの順序の入れ替わり、完了していない `cy.visit()` に対する並列 `cy.request()` のレース |
| F12 | **セレクタードリフト** | DOM が変わったのに、カスタムコマンドや POM のセレクターが更新されていない |
| F13 | **エラーの握りつぶし** | 失敗を隠す `cy.on('uncaught:exception', () => false)` |
| F14 | **アニメーションレース** | コンテンツが未描画、一時的な要素が観測前に削除される、または CSS トランジションが未完了 |
| F15 | **ハイドレーションレース** | `cy.visit()` 後の最初のクリックは成功するのに効果がない — SSR ページがまだハイドレーションされておらず、次のアサーションで失敗する |

### デバッグワークフロー

1. **抽出** — `mochawesome.json` または JUnit XML をパースし、失敗したテスト、エラーメッセージ、所要時間を取得
2. **分類** — エラーシグナルに基づき各失敗を F1–F15 に対応付け（ほとんどの失敗はここで解決）
3. **スクリーンショット/動画** — まだ不明なら `cypress/screenshots/` と `cypress/videos/` を確認
4. **修正** — 失敗ごとに具体的なコード提案を P0/P1/P2 の優先度付きで提示

---

## FAQ

### e2e-skills とは何ですか？

e2e-skills は、Playwright と Cypress のためのオープンソースの AI エージェントテストツールキットです。エンドツーエンドテストの生成、サイレントな常時パスのアンチパターンに対する既存 spec のレビュー、フレーキーな失敗のデバッグを担う 4 つの Agent Skills をバンドルし、Claude Code、Codex、その他 `AGENTS.md` 互換の AI コーディングエージェントの中で動作します。

### 通るのに実際には何も検証していない Playwright / Cypress のテストはどう見つけますか？

`e2e-reviewer` スキル（またはそのスタンドアロンスキャナー `scan.sh`）を spec ディレクトリに対して実行してください。アサーションの `await` 欠落、ワンショットの `isVisible()` 読み取り、matcher のない `expect()`、コミットされた `.only` の残留など、対象の機能が壊れていてもテストがグリーンのままになる 24 のアンチパターンを、重大度別（P0/P1/P2）にフラグします。

### eslint-plugin-playwright や eslint-plugin-cypress と何が違いますか？

eslint プラグインは構文ルールのための毎コミットのベースラインで、スキャナーもまずそれらを実行します（Tier 1）。その際、プロジェクトの flat config をプラグインの `recommended` の上に重ねるため、意図的に無効化したルールは Tier 1 でも無効のままです。既存の lint 設定を置き換えるのではなく、その上に足す一段です。足しているのは、リンターには[構造的に判定できない](#リンターが構造的に検出できないもの)スメルの検出です。テスト名とアサーションの不一致、決して throw しない関数を包む `try/catch`、削除テストなのに行が消えたかを確認しないケース、認証のないルート — いずれも AST ルールが決して見ないコード（別の関数、コンポーネント、CI 設定、テストの意図）を読む必要があります。（機械的に常に真になるケース — `expect(locator).toBeTruthy()` — は単一ファイルで lint 可能で、だからこそ公式 `eslint-plugin-playwright` ルール `no-unnecessary-assertions` としてアップストリームに貢献されました。スキャナーの第 1 ティアがこれを実行します。）`e2e-reviewer` はその周辺コードを読んで指摘を検証し、その場しのぎを避けた修正案を提示します。lint にできるのは単一ファイルの構文をフラグすることだけです。

### CodeRabbit、Copilot、Cursor BugBot のような AI コードレビュアーと同じではありませんか？

それらは優れた汎用レビュアーであり、オープンソース向けに無料のものも多く、いまではローカル実行にも対応しています（CodeRabbit の CLI はターミナルでステージ済みの変更をレビューします）。違うのは能力ではなく、特化の度合いです。汎用レビュアーは渡された diff について推論しますが、`e2e-reviewer` は E2E のサイレントな常時パス・アンチパターンに絞った、安定 ID と重大度グレード付きの厳選カタログ（固定 ID の 24 パターンに加え、失敗デバッグ用の 15 カテゴリー）を携えており、PR の diff だけでなく spec ディレクトリ全体に対してオンデマンドで実行できます。普段の用途には汎用レビュアーを、E2E テストの信頼性が問題になるときにはこちらを使ってください。レビュー済みの 100 PR での実際の比較（率直な制約の記載付き）は [AI レビュアーベンチマーク](docs/ai-reviewer-benchmark.md)を参照してください。

### Playwright だけでなく Cypress でも使えますか？

はい。どちらも第一級のサポート対象です。テスト生成と最も充実したレビューは Playwright を対象とし、レビューと失敗デバッグは Cypress（mochawesome と JUnit のレポート）を完全にカバーします。

### CI でしか失敗しないフレーキーテストもデバッグできますか？

はい。`playwright-debugger` と `cypress-debugger` はレポートファイル（`playwright-report/`、`cypress/reports/`）を読み、各失敗を 15 の根本原因カテゴリー（フレーキーなタイミング、セレクタードリフト、テスト分離、環境不一致、ハイドレーションレースなど）に分類し、失敗ごとに具体的な修正を提示します。

### AI が生成した E2E テストはどうレビューしますか？

生成された spec に `e2e-reviewer` を向けてください。AI が書いたテストには、自信ありげに見えて実はサイレントに常時パスするアサーションが頻繁に含まれます。レビュアーはそれらを before/after の修正付きで、メインブランチに届く前に洗い出します。

### 対応している AI コーディングエージェントは？

Claude Code（プラグインマーケットプレイスまたは `skills` CLI）、Codex、そして `skills` CLI が `AGENTS.md` 経由で対応するあらゆるエージェント（55 以上のホスト）です。一度インストールすれば、どこでも使えます。

### Playwright と Cypress 以外のテストフレームワークには対応していますか？

いいえ — 設計上、Playwright と Cypress のみです。理由は[フレームワークスコープ](docs/framework-scope.md)を参照してください。

## ロードマップ

計画中で、まだ提供していない項目です（現在の挙動ではなく方向性を示します）。

- **モデル横断の一貫性。** AI エージェントはそれぞれ独自のスタイルで spec を書くため、複数のモデルで構築されたスイートは、どの規約にも収まらないパッチワークになっていきます。計画はこうです。プロジェクトの規約（POM の形、ロケーター戦略、フィクスチャや構造のパターン。「抽象化しない」も有効な答えで、2 ページのフローに不要な Page Object 層は作りません）を推論し、コードベースが本当に曖昧な箇所だけを質問し、回答を永続化して、以降はすべてのモデルをそれに従わせます。ただし、記録された規約は硬いルールではなく、*理由を明示すればエージェントが逸脱できるデフォルト*にとどめます。特定のテストにもっと良いアプローチがあるなら妨げませんし、筋の通った逸脱はむしろ規約を育てるきっかけになります。この部分はリンターには構造的にできません。固定ルールを強制するだけで、そのプロジェクト*固有の*規約を学んで従うことはないからです。
- **決定論的検出レイヤー。** ファイル単位で型情報から判定できるスメル（Locator の truthy 扱い、待たれないアサーション）を、プロンプトとヒューリスティックから型認識の AST パスに移して検出を再現可能にし、単一ファイルのルールでは下せない判断にだけ LLM を使うようにします。明確に lint 化できるルールは再実装せず、`eslint-plugin-playwright` にアップストリームで貢献します — その第一弾として、常にパスする Locator アサーションを検出する `no-unnecessary-assertions` ルールが[マージされました](https://github.com/mskelton/eslint-plugin-playwright/pull/470)。

これとは別に、アップストリーム貢献のロードマップではより広いパイプラインを管理しています: **マージ済み 14 件、レビュー中・キュー合わせて 14 件**。キューに載るのは審査済みの 1,000 スター超の候補だけです。最新の表は[アップストリーム貢献](docs/roadmap.md)にあります。

## コントリビューション

バグ報告、偽陽性ガード、新しいアンチパターン、翻訳、いずれも歓迎します。セットアップ、検証ゲート（`bash scripts/ci/ci-local.sh`）、凍結 ID / パリティの規約については [CONTRIBUTING.md](./CONTRIBUTING.md) から始めてください。エージェント横断のより詳しい情報は [AGENTS.md](./AGENTS.md) にあります。

## ライセンス

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha)。[LICENSE](./LICENSE) を参照してください。
