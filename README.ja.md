<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — Playwright と Cypress 向けの Agent skills: 信頼できるエンドツーエンドテストを生成・レビュー・デバッグする。" width="100%" />
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
<a href="README.md">🇺🇸 English</a> | <a href="README.ko.md">🇰🇷 한국어</a> | <strong>🇯🇵 日本語</strong> | <a href="README.zh-cn.md">🇨🇳 简体中文</a>
</p>

<!-- README-CANONICAL-REVISION: sha256=79b0cbd3931bc84a8c791e11f7486732cfd98b408730be420a617b641e988498; bytes=exact-README.md-UTF-8; translation-quality=not-attested -->

証拠の範囲: ここに示した merge 済み PR 15 件は選んだ例であり、総数ではありません。Field review v1 は、スキル名を含めるという基準のもとで、提出 29 件、merge 16 件、クローズ 6 件、オープン 7 件を別に記録しています。2 つの母数を合算しないでください。いずれも記録時点のスナップショットで、現在の GitHub の集計ではありません。

`e2e-skills` は、AI コーディングエージェントが Playwright/Cypress の E2E テスト作業に使える 4 つのワークフローを提供します。Playwright カバレッジの生成、既存のテスト仕様または PR/diff 範囲の変更レビュー、失敗した Playwright レポートのデバッグ、失敗した Cypress レポートのデバッグを扱います。レビューカタログのうち、機械的に判定できる部分集合を検出する決定論的スキャナーも含まれます。

<p align="center">
  <a href="https://www.kimi.ai/resources/software-testing-skills">
    <img src="docs/assets/kimi-software-testing-skills.png" alt="Kimi 公式サイトの「AI Software Testing Skills for Smarter QA Automation」に掲載された e2e-skills" width="100%" />
  </a>
  <br />
  <sub><a href="https://www.kimi.ai/resources/software-testing-skills">Kimi 公式サイトの「AI Software Testing Skills for Smarter QA Automation」で紹介されています。</a></sub>
</p>

人間または AI が作成したテストでは、`e2e-reviewer` を独立した品質ゲートとして利用できます。合格したテストが、タイトルに書かれた動作を本当に証明しているかを確認します。

スキルごとに証拠の水準は異なります。レビュアーが最も強い測定結果を持ち、ジェネレーターは 2.x パイプラインのみが公開タスクで測定され、3.0.0 のルーターには公式エージェントとの開発段階の比較（モデル 2 つ、合成タスク 6 件）しかなく、デバッガーは通常のプロンプトより正確だと測定されたものではなく、アーティファクトが裏付ける原因だけを報告する安全なアーティファクトリーダーです。[ベンチマーク状況](benchmarks/STATUS.md)にスキルごとの証拠カードがあります。

| 必要なこと | スキル | 結果 |
| --- | --- | --- |
| 新しい Playwright カバレッジを生成 | `playwright-test-generator` | 観測したロケーターで書き、スキャナー確認と 1 回の実行を経た Playwright テスト仕様 |
| Playwright/Cypress テストまたは PR/diff 変更をレビュー | `e2e-reviewer` | 具体的な修正と introduced/worsened/pre-existing の帰属を伴い、各判断の根拠を示す検証済み P0/P1/P2 指摘 |
| 失敗した Playwright 実行をデバッグ | `playwright-debugger` | F1–F15 の根本原因、根拠、修正 |
| 失敗した Cypress 実行をデバッグ | `cypress-debugger` | F1–F15 の根本原因、根拠、修正 |
| 決定論的なローカルスキャンを実行 | `skills/e2e-reviewer/scripts/scan.sh` | 対象プロジェクトの package に依存しない機械的候補 |

生成器はルーターです。Playwright CLI でライブページを探索するか、すでにセットアップ済みの公式 Playwright エージェントへ委譲し、短いルールのチェックリストに従って仕様を書き、レビュアーのスキャナーを実行してから、テストを 1 回実行します。開発段階の比較では、CLI 経路は公式エージェントに対して事前登録した品質基準の範囲内で、測定した処理トークンのコストは公式エージェントの 0.56〜0.60 倍でした(95% 区間 0.45〜0.74)。品質向上は主張しません([thin-eval](benchmarks/generator-thin-eval-v1/README.md))。2 つのデバッガーは失敗した実行の artifact から始め、分類した根本原因、根拠、具体的な修正を返します。

false-green 検出はレビューワークフローの重要な一部ですが、このバンドル全体の目的ではありません。`e2e-reviewer` の指摘に基づく修正は、Storybook、SvelteKit、code-server、Strapi、Carbon Design System、Ghost、MUI X などの [15 件のマージ済み upstream PR](#merged-upstream-fixes) に取り込まれています。

> code-server では、コミット済みの `it.only` が 7 か月にわたって 8 件のテストを静かに無効化していました。そのうち 1 件の skip されたテストはすでに壊れていたにもかかわらず、CI は green のままでした。

**実行可能な例:** [React optimistic-write の証明](examples/react-optimistic-write/README.md) は、optimistic UI には画面に見える状態だけでなく、リクエストと永続化の証明も必要な理由を示します。

## 役割分担

フレームワーク別の支援ツールを比べると、役割は単純です。

| 必要 | 最適な選択 |
| --- | --- |
| 計画から Playwright coverage を生成 | [Playwright Test Agents](https://playwright.dev/docs/test-agents) |
| Cypress ワークフローを公式ドキュメントとともに作成・説明・活用 | [Cypress AI Skills / Cypress AI Toolkit](https://docs.cypress.io/app/tooling/ai-skills) |
| false-green のレビューと失敗レポートのデバッグ | `e2e-skills` |

`e2e-skills` はこうした公式ツールキットを補完します。テストが名前どおりの動作を本当に証明しているか、変更が静かな通過を生んでいないか、そして失敗した Playwright/Cypress artifact が実際に何を示しているかに焦点を当てます。

<a id="merged-upstream-fixes"></a>

## アップストリームにマージされた修正

`e2e-reviewer` の指摘は **15 件のマージ済み upstream PR** に取り込まれています。これらは実用例を示し、読者が修正内容を確認できるようにするために選んだ事例です。代表的な検証サンプルでも、正確度の推定値でもありません。

マージだけでなく却下も公開しています。[Field review v1](benchmarks/field-review-v1/README.md) では、提出 29 件、マージ 16 件、マージなしクローズ 6 件、オープン 7 件を記録しています。却下を含まないマージ件数は率ではないためです。

以下のリポジトリの GitHub stars は、2026-09-16 の GitHub API スナップショットで合計 **493,657** です。Stars はプロジェクトの規模と認知度を示す参考情報であり、レビュー精度やプロジェクトによる推奨を示すものではありません。

| リポジトリ | GitHub Stars | PR | 修正したパターン |
| --- | ---: | --- | --- |
| Storybook | ★91.1k | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Playwright assertions の missing `await` |
| code-server | ★79.3k | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | Focused test leak、matcher-less `expect`、discarded visibility read |
| Strapi | ★73.2k | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | Discarded navigation/state checks |
| Ghost | ★55.3k | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise-valued disabled-state assertion |
| Cal.com | ★48.5k | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | E2E flow の weak assertion patterns |
| Bruno | ★47.0k | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | Assertion と wait reliability fixes |
| Qwik | ★22.1k | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/handle existence checks |
| SvelteKit | ★20.8k | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | Floating Playwright assertions |
| Element Web | ★13.5k | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator null-check style assertions |
| FiftyOne | ★11.1k | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Locator-defined check を visible duplicate-name error assertion に置き換え |
| Carbon Design System | ★9.5k | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | Locator truthiness を web-first assertions に置き換え |
| Rancher Desktop | ★7.3k | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `not.toBeNull()` locator checks を visible WSL integration-name assertions に置き換え |
| Apache Zeppelin | ★6.7k | [apache/zeppelin#5180](https://github.com/apache/zeppelin/pull/5180) | 常に真の assertion と、暗黙にスキップされるガード付きチェック |
| MUI X | ★5.8k | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | UI handle checks を state assertions に置き換え |
| module-federation/core | ★2.6k | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Cypress spec 内の redundant blanket `uncaught:exception` suppression |

## false-green テストを見る

**false-green** なテストは、名前に書かれた挙動が動いていようといまいと通ります。flaky なテストとは違います。flaky なテストは時々失敗するので、リトライダッシュボードや flake 分析がいずれ検知します。false-green なテストは**製品が壊れていても失敗しない**ため、pass/fail の監視だけでは表面化しません。

この Playwright テストはもっともらしく見えますが、証明しているのは `Locator` オブジェクトが作られたことだけです。

```typescript
import { expect, test } from '@playwright/test';

test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();
  expect(page.locator('.user-badge')).not.toBeNull();
});
```

有用なテストは、ユーザーに見える挙動を検証し、その挙動が壊れたときに失敗します。

```diff
- expect(page.getByText('Welcome back')).toBeDefined()
+ await expect(page.getByText('Welcome back')).toBeVisible()
```

同梱スキャナーは、プロジェクト設定なしで false-green assertion を検出します。以下は対応に必要な行だけを抜粋した出力です。

```console
$ /bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests/

[P0] #4f Locator always-true assertion (truthy/defined/not-null) (2 hits)
  .../tests/login.spec.ts:5:  expect(page.getByText('Welcome back')).toBeDefined();
  .../tests/login.spec.ts:6:  expect(page.locator('.user-badge')).not.toBeNull();

Summary: 2 total hit(s), 2 P0
```

この実行は P0 指摘を報告するため、`scan.sh` は exit 1 で終了します。

`eslint-plugin-playwright` も `no-unnecessary-assertions` でこの形を検出します。コミット時の lint が扱える問題を担当し、残りをスキャナーが補えるよう、このルールを有効にしてください。

## 生成したテストを信頼する前に確認する

良い matcher だけでは不十分で、挙動が壊れたときにテストが red になる必要があります。3.0.0 から生成器はこれを証明しません。`e2e-reviewer` がインストールされていればスキャナーを実行して P0 と P1 の検出をすべて修正し（最大 3 回）、プロジェクトのテストを 1 回実行します。スキップしたゲートや実行は完了ではないと報告します。主要な assertion の反転、障害注入、独立した再レビューはもう行わないため、必要なら `e2e-reviewer` にレビューを依頼してください。これらの 2.x の手順はタグ `v2.0.1` に残っています。

## インストールして試す

### Claude Code

プラグインマーケットプレイスからインストールします。

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

または、バージョン固定の cross-agent CLI で、コピー形式のスキルをインストールします。

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

4 つのスキルを `~/.agents/skills/` にインストールします。

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a codex
```

Codex の delegation では、`e2e-reviewer`、`playwright-debugger`、`cypress-debugger` が native role の delegation を試みるか、同等の inline fallback を使えます。`playwright-test-generator` は既定の経路では delegation を必要としません。Playwright CLI のワークフローは Codex のシェルで動くためです。公式 Playwright generator への delegation は任意で、`spawn_agent` では role を選べないため、session-wide な `playwright-test` MCP サーバーがある場合にのみ動作します。

**2026-09 時点で、Codex 上の native role delegation は動作が検証されておらず、依存すべきではありません。** 実測パイロットで、セッション内 delegation が内部の `collab spawn failed: no thread with id` エラーで決定的に失敗することが分かりました — 既知の、まだ open な upstream issue([openai/codex#41474](https://github.com/openai/codex/issues/41474)、[#33672](https://github.com/openai/codex/issues/33672))です。エラーが出ない場合でも、モデル自身の成功の自己申告は信用できません。詳しい根拠は [`benchmarks/subagent-routing-v1/`](benchmarks/subagent-routing-v1/README.md) を参照。各 skill の inline fallback が同じ verdict に到達するため正確性自体には影響しませんが、現時点では named agent を install しても Codex 上で実測された利点はありません。

ここでいう native role とは、optional な subagent である `e2e-finding-verifier` と `e2e-failure-classifier` のことで、**Codex はこの 2 つを plugin から install できません。** Codex の plugin manifest に agents フィールドはなく、agent role は config layer からのみ読み込まれるため、`codex plugin add` も `skills` CLI もこれらを登録しません。supported な経路は 2 つです。`bash scripts/dev/install-codex-agents.sh` を実行して `~/.codex/agents/` に global install するか、この repository の checkout で作業すると、Codex session が install 手順なしで `.codex/agents/` を認識します。どちらも省略して構いません。inline fallback が動作します — これが現時点でこの host で信頼できる経路です。packaging boundary については [AGENTS.md](AGENTS.md) を参照してください。

別ルートとして、Codex plugin marketplace からもインストールできます:

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

### その他のエージェント

`skills` CLI がサポートするすべてのホストへ、グローバルにインストールします。

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all
```

1 つのホストだけを対象にするには、`--all` を `-a <agent>` に置き換えてください。[supported agents](https://github.com/vercel-labs/skills#supported-agents) も参照してください。これらのコマンドは、未レビューの新しいバージョンではなく、レビュー済みの CLI release を固定して実行します。

### 手動 Claude Code checkout

checkout は `~/.claude/skills/` の外に置き、各 public skill directory をリンクします。

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

`~/.claude/skills/` に 4 つの名前のいずれかがすでにある場合は、そのパスを表示して何もリンクしないため、既存のスキルを上書きしたり、その中にリンクを作ったりしません。Claude Code で `/skills` を実行し、4 つの名前がすべて表示されることを確認してください。

### 最初のプロンプト

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

## スコープと制限

このバンドルは、E2E テストの生成・レビューと、失敗した Playwright/Cypress 実行の原因分析に使います。アプリケーションと実際の E2E suite に加えて使うものであり、それらの代替ではありません。汎用 lint preset やフレームワーク非依存のテストツールでもありません。Playwright と Cypress をサポートし、新規テスト生成は現在 Playwright のみを対象にしています。

同梱のシェルスクリプトとアーティファクトリーダーは、`/bin/bash` と、ランチャーが要求する固定のシステム実行ファイルパスを使う一般的な macOS/Linux 構成を対象としています。Windows ユーザーには互換性のある WSL ディストリビューションと、WSL ファイルシステム内のアーティファクトが必要で、ネイティブ Windows はサポートしていません。NixOS や、Nix・pyenv・Conda・nvm だけで導入したツールは、すべてが自動検出されるわけではありません。レビュアーのスキャナーは、検証済みの絶対パスによる `E2E_SMELL_*_BIN` の上書きに対応していますが、デバッガーのランチャーに同じ上書きがあるという意味ではありません。信頼できるツールが見つからない場合は、該当の操作が停止します。環境の `PATH` を探索してこの境界を回避しないでください。スキルのリソースは、推測したホームディレクトリではなく、プラグインキャッシュやカスタムインストールを含め、ホストが実際に提供するスキルの場所から解決してください。

生成したテストが通るだけでは不十分です。`Locator` や `Promise` 自体を検証していたり、テスト名に記した動作と無関係な状態を見ていたり、主要な assertion がテストの成否に影響していないことがあります。そのため生成器は `e2e-reviewer` のスキャナーを実行して P0 と P1 の検出をすべて修正してから、プロジェクトのテストを 1 回実行します。スキャナーは決定的で、カタログのうち機械的に検出できる一部だけを扱います。assertion が失敗しうることの証明にはなりません。

生成器は `playwright.config.*` から `baseURL` を読み、公式 Playwright planner と generator のエージェント定義と `playwright-test` MCP ツールがすでにある場合にのみそれらを使います。そうでなければ、シェルと Playwright だけで Playwright CLI を自ら使って探索します。 MCP の設定を求めず、何もインストールせず、公式 healer を実行せず、テストを通すために assertion を弱めません。失敗したテストは `playwright-debugger` に渡すか、手で修正します。

探索は loopback の対象で許可されます。リモート origin は、ユーザーがチャットで指定し、使い捨ての非本番環境だと明言した場合にのみ許可され、その origin は CLI の origin allowlist（`network.allowedOrigins`）に固定されます。本番、共有、または未指定の対象は拒否され、公式エージェントへの delegation 経路は origin を固定できないため loopback 専用です。CLI が使えない場合は、サニタイズ済みスナップショットかユーザー自身がインストールした CLI を求め、ロケーターを未検証と表示します。

2.x の生成器（承認表と V1–V6）に戻すには `v2.0.1` タグをインストールします。skills CLI は `npx --yes skills@1.5.21 add voidmatcha/e2e-skills#v2.0.1 --skill '*' -g -a claude-code`、Claude Code マーケットプレイスは `/plugin marketplace add voidmatcha/e2e-skills#v2.0.1` の後に `/plugin install e2e-skills@voidmatcha` です。どちらも使い捨てディレクトリでそのタグに対して確認しました（skills CLI は `-g` なしのプロジェクトスコープ）。既存の `voidmatcha` マーケットプレイス項目の置き換えは確認していません。

## レビューの仕組み

有効なテストコードを生成することと、プロダクトが間違っているときに失敗するテストを生成することは別です。このワークフローは、機械的な検出と意味的な判断を分離します。

1. スキャナーは Locator truthiness、focused tests、`await` の欠落、blanket error suppression など、決定論的に見つけられる候補を検出します。
2. `e2e-reviewer` は指摘を確定する前に、テスト名、操作、assertion、helper、Page Object、fixture、設定を読みます。
3. 指摘は安定した pattern ID と P0/P1/P2 severity を使うため、修正と回帰を比較できます。
4. 修正後、ワークフローはスキャナーと、プロジェクトで承認された E2E または lint コマンドを再実行します。

スキャナーの一致は候補であり、判定ではありません。認証の欠落、呼び出し証明のない optimistic UI、name/assertion mismatch、render guard に阻まれる fixture など、複数ファイルにまたがる指摘には意味的なレビューが必要です。

## 根拠と限界

現在の根拠で支えられる主張は限定的です。このプロジェクトには動作で裏付けた開発根拠とアップストリームにマージされた 15 件の修正がありますが、一般化されたレビュー精度は主張しません。

マージ件数に分母がつきました。[Field review v1](benchmarks/field-review-v1/README.md) は、このアカウントが出したプルリクエストのうち本文にスキル名を含むものをすべて走査し、GitHub が報告する結果をそのまま記録します。26 リポジトリに 29 件提出、マージ 16 件、マージなしクローズ 6 件、オープン 7 件です。手作業の一覧ではなく GitHub から生成したことで、ロードマップに載っていなかった 7 件が見つかり、うち 2 件はマージ、3 件は却下でした。本文にスキル名を含まないプルリクエストはこの走査に現れないため、分母は下限値です。上の表にあるマージ済みの [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) がその例です。

これも精度の数値ではありません。マージはメンテナーがパッチを受け入れたことを意味し、指摘の重大度分類が正しかったことを保証しません。提出署名は任意なので、署名のない却下は比率を上振れさせます。ただしこの判定だけは、このプロジェクトの管理下にありません。

決定的スキャナーは別途測定します。[Field scan v1](benchmarks/field-scan-v1/README.md) では、同じ 12 件の公開リポジトリを固定したコミットで再スキャンし、従来の 30 分の制限とデフォルトの候補数上限を適用しています。**12 件中 10 件はルールの抑制なしにスキャンを完了し、P0 0 件を報告しました**。残る 2 件はタイムアウトしました。これらの所要時間は 2026-09-18 の hot path 改善([scanner hot path v1](benchmarks/scanner-hot-path-v1/README.md)、密なフィクスチャでヒットあたりのコストが約 4 分の 1)より前の測定であり、ここで測り直してはいません。2026-09-19 のスコープ検証の改善後、タイムアウトした 2 件のうち `ever-gauzy` のルート全体のスキャンは 5,932 秒から 1,226 秒に短縮され、出力はバイト単位で同一でした。この値はこの一覧のプロトコル外で測定したものです。結果一覧では要レビューの候補を別に示しており、再現率や適合率を証明するものではありません。以前の「`#3` の確定ヒット 294 件」という報告は、スキャナーの分類上の欠陥によるものでした。訂正内容と当時の変更前後の比較結果は、リンク先に記載しています。その後、別途公開されたプロトコル（30 分の制限を撤廃し、スキャナーの上限を文書化されたハード上限まで引き上げ）を用いた[完了拡張作業](benchmarks/field-scan-v1-extension/README.md)が、当初設計された 12 件のサンプルを完成させました — タイムアウトしていた 2 件はいずれも抑制されたルールなしに正常終了し、P0 0 件を報告しました。この拡張作業は固定された v1 台帳を書き換えるものではありません。

- 最も強い独立した signal はスコアではありません。常に通過する Locator アサーションのパターン (`#4f`) が公式の `eslint-plugin-playwright` に `no-unnecessary-assertions` ルールとして採用されました (マージ済みのプルリクエストは [ロードマップ](docs/roadmap.md) を参照)。このプロジェクトと利害関係のない外部メンテナーがルール定義を受け入れたということです。同時に、現在の lint がその形状を検出するようになったため、このプロジェクトはもうその事例を自分の成果として主張しません。
- `docs/rule-self-audit.md` は、2 つのモデル系統による敵対的監査で、このプロジェクト**自身**の P0 ルールに見つかった欠陥を記録しています。単一のレビューアーであれば通過させていたルールが含まれます。
- ブラウザー障害注入は、**12 個の障害演算子と 3 種類の期待結果を組み合わせた Playwright/Cypress セル 36 件すべて**で完了しています。これはハーネスの自己テストです。アプリケーション、堅牢なテスト、注入した障害、脆弱なテストのすべてをこのリポジトリで書いているため、検出器が設計どおりに動作することを示すだけであり、一般化を意味しません。
- [Healer perturbation v1](benchmarks/healer-perturbation-v1/README.md) は、**凍結済みの Codex セル 30 件すべて**を完了し、`REJECT` を返しました。ガード付きの公式 healer prompt と、このリポジトリが提案した Step 7 workflow は、どちらも修復不可能な honesty control 3 件すべてを弱めました。この結果は両 healer 経路を安全なデフォルトとして採用しないことを意味しますが、Claude、一般的な healer 品質、reviewer 精度を測定したものではなく、product instructions も変更していません。
- exact レビューベンチマークは **証明済みの false-green 事例 12 件と正常コードの保護事例 12 件**を対象にしています。10 件の障害事例は byte-identical operator mutants です。
- [実コードの修正前後ペア](benchmarks/fixpair-v1/README.md)の B+C+D バッチでは、`gpt-6-sol` の厳密な再現率が**スキルあり 25/33、なし 13/33**、修正後（AFTER）の誤検出は両群とも **0/33** でした。統制した 3 モデルの再実行では差が縮まりモデルごとに異なり、スキャナ修正後に再実行した BEFORE 33 件中 `gpt-6-sol` **26 対 14**、`gpt-6-astra` **27 対 22**、`claude-sonnet-5-5` **27 対 21** でした。別モデル `gpt-6-astra` の B バッチでは **10/15 対 10/15**、誤検出は両群とも **0/15** でした。
- [意味的ミュータント v1](benchmarks/semantic-mutants-v1/README.md) は実際のテストファイルにモデルが注入した欠陥を扱います。厳密な再現率は S1 が **7/10 対 5/10** でした。元ファイルで各 1 件と集計された警告は、どちらも「編集画面」のテストがなお作成画面へ移動する同じケースから生じています。S2 は **8/9 対 2/9**（警告は各 0 件）、S3 は **5/6 対 2/6**（0 件対 2 件）でした。各サンプル 1 回の開発測定であり、#12 は対象外です。
- [Debugger skill-effect v1](benchmarks/debugger-skill-effect-v1/README.md) はデバッガーの初のライブ測定です。新規作成した 30 件の F1–F15 ケースで、スキル本文はカテゴリ一覧のみのプロンプトよりツールなしの F コード精度を両ホストで高めました。Claude Sonnet **0.944 vs 0.756**、Codex Sol **1.000 vs 0.800**、対応のある 95% 区間は 0 を上回ります。作成者が類似症状を仕込んだモデル作成の公開ケースで、ベースラインも一覧のみのため、リリース主張ではなく、実際の失敗へ一般化できるとも示されていません（v2 参照）。 [Debugger skill-effect v2](benchmarks/debugger-skill-effect-v2/README.md) は実際のアップストリーム修正 26 件を正解とし、分類体系なしのベースラインを置きました。厳密な機構一致率は**スキル 0.872 vs 分類体系なし 0.897**（lift −0.026、CI −0.090〜+0.026）で `FAIL`、ブラインドのマッパー 2 名が F コードに合意した実修正は 26 件中 15 件のみでした。 [Debugger skill-effect v3](benchmarks/debugger-skill-effect-v3/README.md) は F1/F14/F11/F7 のタイブレーク候補を、さらに 28 件の実修正で測定しました。機構一致率は変わらず（**0.810 vs 0.798**、`FAIL`）、合意ラベルでの F コード正解率は **0.638 → 0.812**（CI 下限 0.000）ですが、このラベルは新しい表で付与され、不一致 5 件は除外されたため新テキストに有利であり、診断が改善した証拠ではありません。マッパー合意は 28 件中 23 件でした。このタイブレークは v3 でのみ試験し、2.0.0 には含めていません。 [Debugger skill-effect v4](benchmarks/debugger-skill-effect-v4/README.md) はツール使用の呼び出しに実際の Playwright レポートを与え決定的に採点しましたが `INCONCLUSIVE` でした（完全一致 **スキルあり 0.882 vs なし 0.917**、コスト 2.6 倍）。v1–v4 を通じて根本原因特定の改善は示されていません。
- [Debugger skill-effect v5](benchmarks/debugger-skill-effect-v5/README.md) はより軽い回答形式を実際の修正事例 14 件で試しましたが、現在の出荷テキストと区別できず（strict 一致 0.762 対 0.738、分類なしプロンプト 0.786）、2.0.0 のデバッガーのテキストは変更せず、2.0.1 で[ローカル開発用の比較](benchmarks/debugger-dev-comparison-v1/README.md)の後に Root Cause と Fix の文言を変更し、3.0.0 では診断精度の測定された変化なしに両デバッガーのエントリーポイントを縮小しました。デバッガーが示す価値は、通常の「根本原因を診断して」プロンプトを上回る精度ではなく、安全なアーティファクト処理です。
- 廃止された 2.x ジェネレーターについて: [Generator skill-effect v1](benchmarks/generator-skill-effect-v1/README.md) はジェネレーターの初のライブ測定です。新規作成した 10 件の小さなアプリで決定論的な欠陥検出スコアリングを行ったところ、スキルを使った `claude-sonnet-5-5` は 30/30 の呼び出しで正常なアプリに通り、注入した欠陥 **150/150** を検出するテストを書きました。スキルなしの有効検出率は **0.927**、コストは 6.05 倍でした。事前登録した判定は `INCONCLUSIVE` です。ベースラインが上限 0.90 を超えたため、向上は主張できません。スキルで書いたテストはマークアップのリファクタリングに 23/30 の呼び出しで耐え、スキルなしでは 12/28 でした。
- 廃止された 2.x ジェネレーターについて: [Generator skill-effect v2](benchmarks/generator-skill-effect-v2/README.md) は、より難しいブリーフ形式の 24 タスクを、群比較の前にスキルなし群だけでスクリーニングしました。事前に定めた 0.40–0.80 の帯に入ったのは **24 件中 3 件**のみで（正常なアプリで緑になったスキルなしの成果物 44 件が注入欠陥 **216/220** を検出）、予定していた full / lean / スキルなしの比較は実行せず、判定は `INCONCLUSIVE`（プール不足）です。このモデルでは欠陥検出率が 2 つのプロトコル続けて上限に達し、リファクタリング耐性と正常アプリでの成功だけが依然ばらついています。
- 廃止された 2.x ジェネレーターについて: [Generator skill-effect v3](benchmarks/generator-skill-effect-v3/README.md) は、動作を保持するマークアップのリファクタリング後もテストが通るかを主要指標として、検証済みの 36 タスクをスクリーニングしました。事前登録した 3 回目の反復を追加しても、0.25–0.75 の帯に入ったのは **36 件中 9 件**で、最低条件の 12 件に届きませんでした。そのため 5 群比較は実行せず、判定は `INCONCLUSIVE`（プール不足）です。スキルなしの成果物 101 件はすべて正常なアプリで通り、37 件がリファクタリング後も通過し、注入欠陥 **498/505** を検出しました。スキルを使う群は実行していないため、ジェネレータースキルの効果はどちらの方向にも測定されていません。
- 廃止された 2.x ジェネレーターについて: [Generator skill-effect v8](benchmarks/generator-skill-effect-v8/README.md) は公開 v3 プールで Codex 呼び出し 216/216 を採点し、合格しました。マークアップ・リファクタ生存率は **0.954 対 0.435**（+0.519、95% CI +0.398〜+0.630）です。欠陥検出の向上は示されておらず（+0.017、CI は 0 を含む）、生成時間は 6.74 倍で、公開開発エビデンスでありリリース主張ではありません。 v8 は固定された v3 full-fixed の 2.x 生成テキストを測定しており、3.0.0 のルーターはそのテキストを含みません。ルーターには、公式エージェントとの開発段階の比較（モデル 2 つ、合成タスク 6 つ）が別にあります。CLI 経路は事前登録した品質基準の範囲内で、処理トークンは公式エージェントの 0.56〜0.60 倍でした。品質が優れているとは主張しません（[thin-eval](benchmarks/generator-thin-eval-v1/README.md)）。これらの結果が扱う承認表と V1–V6 受け入れ手順を含む 2.x の生成器は、タグ `v2.0.1` と `benchmarks/generator-skill-v2.0.1-archive/` に残っています。
- [Reviewer holdout v19](benchmarks/reviewer-holdout-v19/README.md) は**リリース前の 2.0.0 候補**レビュアー（スキル digest `aa88145d…`、コミット `976c3fa`）に対してリリース確認ゲートを通過しました（full − no-skill の安定 F1 **+0.571**、95% CI +0.411〜+0.738、540 回の呼び出し）。同じコーパスの [v18](benchmarks/reviewer-holdout-v18/README.md) は `INCONCLUSIVE` でした。出荷されたレビュアーはその候補から後続の変更（Tier 2 ast-grep 設定の固定、`#14` の `cy.env()` 除外、`#4h` の修正と 4 件の境界明確化、`#8c`、`#3b` fail ハンドラ契約）の分だけ異なり、これらはどの holdout でも測定されていません。
- [Reviewer holdout v21](benchmarks/reviewer-holdout-v21/README.md) は #2 の明示的な文言を支持しませんでした。480 回の呼び出しで full の安定 F1 は **1.000 → 0.980** に低下しました。2.0.0 の文言を維持します。部分的に検証された #2 は両群ですでに P1 と判定されました。
- 公開対象から除いたローカル専用の AGPL バッチを含む全バッチの集計は **36/44 対 23/44**、修正後（AFTER）の誤検出は **0 対 1** でした。[フィールドモデル比較](docs/ai-reviewer-benchmark.md#field-model-comparison)では、実リポジトリのテストファイル 19 件について別のローカル測定を報告しています。
**どのモデルを選ぶべきか。** このローカル評価では、スキル使用時の再現率は `gpt-6-sol` が最も高い結果でした。`claude-sonnet-5-5` は実際のテストファイル 19 件すべてで手順を守り、測定された入力トークン使用量も最少でしたが、小規模な修正前後ペアと意味的ミュータントではスキルによる再現率向上はほとんどなく、主な効果は誤検出の減少でした。`gpt-6-astra` と Sonnet 5.5 のような強力なモデルは、スキルなしでも機械的な問題を多く検出しました。`claude-fable-5` も高得点でしたが、[Anthropic によると Fable はプランの利用枠をより速く消費し、Max では週間上限の 50% に制限されます](https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan)。これらは各サンプル 1 回、記載したモデルのバージョンに限る開発測定です。

- Reviewer holdout v7 は `no-skill` に対する 6 件の lift check をすべて通過しましたが、事前登録済みの `catalog-only` lift bar には失敗しました。Full は precision (`0.956522` 対 `0.884615`) と clean specificity (`1.0` 対 `0.75`) が向上した一方、recall は低下 (`0.916667` 対 `0.958333`) したため、skill-lift は主張しません。
- Independent product-review robustness gates v4、v5、v7、v8、v11 は事前登録した基準を満たしませんでした。v6 と v9 は未実行で、v10 は 3 回の試行のうち 1 回を実行した時点で、凍結済みのレビュー入力を再利用する v11 に置き換えました。v1 から v11 は、現在のリリースゲートではなく、過去の robustness evidence として保持しています。
- デバッガー protocol は再実行可能な 30-case synthetic corpus を提供しますが、独立に確立されたデバッガー精度は主張しません。

スコア、失敗したゲート、置き換えられた実行、主張の境界については [ベンチマーク状況](benchmarks/STATUS.md) を参照してください。[研究根拠台帳](docs/llm-generated-e2e-test-evidence.md) は、隣接する unit-test や custom-agent studies をこのプロジェクトの測定値として扱わず、62 件の外部 source を監査しています。

これらのスコアの根拠となる実行ごとの生アーティファクト(フォルダ 23 個、ファイル 2,152 個、約 51 MB)は Hugging Face の [`voidmatcha/e2e-skills-benchmarks`](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks) データセットにあり、[`benchmarks/external-evidence.json`](benchmarks/external-evidence.json) で 1 つのリビジョンに固定されています。数値を監査したり比較を再実行したりする前に `scripts/dev/fetch-benchmark-evidence.sh`(`--dry-run` は計画のみ表示)を実行すると、バイト単位で同一に復元されます。

## E2E レビューカタログ

カタログには、24 個の安定した Playwright/Cypress test smells が含まれます。代表的な false-green には、Locator truthiness、assertion の欠落、握りつぶされたエラー、focused tests、認証の欠落、network proof のない optimistic UI checks があります。[分類体系と根拠の詳細](docs/e2e-test-smells.md) を参照してください。

一部のパターンは、テストだけでなくアプリケーションがレビュー範囲に含まれている必要があります。`#22` optimistic UI が最も明確な例です。クリックが実際に mutation を送るかどうかは spec だけでは判断できないため、テストのみのリポジトリでは推測せず何も報告しません。これは意図した false-positive 抑制であり、実行可能な例が component と共に提供される理由です。

### 検出対象の 24 パターン — 重要度別

#### P0 — 必ず修正 (壊れていても静かに通る)

機能が壊れていてもテストが通ります。実質的な検証がありません。

| # | パターン | 修正前 | 修正後 |
|---|---------|--------|-------|
| 1 | **Name-assertion mismatch** | 名前は "status" と言っているのに `toBeVisible()` しか確認していない | `status` の内容に対する assertion を追加するか、実際の check に合わせて rename する |
| 2 | **Missing Then** | Cancel 操作とテキスト復元は検証している。でも input はまだ visible? | restored state と dismissed state の両方を検証する |
| 3 | **Error swallowing** | spec 内の `try/catch`、POM 内の `.catch(() => {})` | error で fail させる。POM methods から silent catch を取り除く |
| 3b | **Cypress `uncaught:exception` suppression** | `cy.on('uncaught:exception', () => false)` がアプリケーションエラーを一律に握りつぶす | handler を特定の known errors に限定し、unknown errors は re-throw する |
| 4 | **Vacuous or retry-weakening assertion** (P0/P1) | P0: invariant predicates と Locator truthiness。P1: weak attachment proof、one-shot values/URL、zero-timeout retry/deadline hazards、証明されていない absence、空の可能性があるコレクションの assertion loop、promised accessible name を省いた ARIA snapshots | 意味のある境界と web-first auto-retrying assertions を使う。absence の前に presence を証明し、assertion loop の前にコレクションが空でないことを証明し、promised accessible names を load-bearing に保つ |
| 5 | **Bypass patterns** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`; comment なしの `{ force: true }` | 常に assert する。env checks は `beforeEach` に移し、force:true には `// JUSTIFIED:` を追加する |
| 7 | **Focused test leak** | `test.only(...)` が commit され、CI は 1 件だけ実行して残りを静かに skip する | `.only` を削除する。local focus には `--grep` または `--spec` を使う |
| 8 | **Missing assertion** | 捨てられた locator/boolean が scenario 唯一の verification になっている | `await expect(locator).toBeVisible()` を追加する。independent verification/failure evidence がすでにある場合は #8 を skip する |
| 12 | **Missing auth setup** | login/`storageState`/auth fixture がなく、protected-route テスト仕様が汎用的なアサーションで login/wrong surface にも一致して通る | `beforeEach` login を追加する、`storageState` を設定する、または auth fixture を使う。通常の認証起因の失敗を P0 に分類しない |

#### P1 — 修正推奨 (診断が悪い / CI 時間を浪費)

テストは動きますが、開発者を誤解させたり、CI 時間を浪費したり、将来の regression を招いたりします。

| # | パターン | 修正前 | 修正後 |
|---|---------|--------|-------|
| 6 | **Raw DOM queries** | `evaluate()` 内の `document.querySelector` | フレームワークの locator/query APIs (`locator` / `cy.get`) を使う |
| 9 | **Hard-coded sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | フレームワークの auto-wait に任せ、condition-based waits を使う |
| 10 | **Flaky test patterns** | comment なしの `items.nth(2)`; `test.describe.serial()`; scope されていない accessible-name substring (10c); Cypress async callbacks、assigned `cy` commands、continued action chains (10d–10f) | stable/scoped locators と self-contained tests を使う。Cypress work は command chain 内に保ち、Chainables を values として代入せず、actions 後は re-query する |
| 13 | **Inconsistent POM usage** | Raw actions bypass a source-established same-page POM boundary; existence alone is insufficient | Reuse the proven boundary; do not invent a wrapper merely because a POM exists |
| 14 | **Hardcoded credentials** | test code 内の `loginPage.login('demo-admin', '<literal-password>')` | `process.env.TEST_USER`、Playwright config secrets、または test data fixtures を使う |
| 15 | **Missing `await` on `expect()`** | Async Locator/Page web-first matcher Promise が sequenced も observed もされず、rejection が後から悪い attribution で表面化しがち | matcher Promise を `await` または return する。sync value matchers は除外 |
| 16 | **Missing `await` on action** | Actionability、action ordering、navigation が後続処理と race し、rejection が後から悪い attribution で表面化しがち | action Promise を `await` または return する |
| 17 | **Discouraged direct Page selector API** | Selector-based `page.click`、`page.fill`、関連 Page actions は Locator layer を skip する | composition、strictness、reuse、clearer failures のために Locator actions を使う |
| 18 | **`expect.soft()` overuse** | critical soft assertions が hard scenario gate の前に走り、broken prerequisite の後も dependent work が続く | primary state を先に hard-gate する。`soft` は independent details にだけ使う |
| 19 | **Module-level mutable state in test code** | test utility の column 0 にある `let seq = 0;` または mutate される `const cache = new Map()` — long-lived worker の tests 間で残り、parallel workers 間で衝突する | counter を削除する。`Date.now()` + `Math.random().toString(36).slice(2, 8)` から uniqueness を作るか、state を `test.beforeEach` に移す |
| 20 | **Unmocked real-backend writes** | Signup/checkout spec が controlled test boundary なしで shared or persistent state に到達する | write を stub するか、disposable container、rollback fixture、isolated tenant/database、または同等の controlled backend を証明する |
| 22 | **Optimistic UI without call proof** | Like-toggle test が `aria-pressed` flip を assert するだけ。UI は optimistic に更新されるため、POST を削除しても通る | UI assertion に、click 前に準備した `page.waitForRequest()` または route-hit flag を組み合わせる |

#### P2 — 余裕があれば修正 (保守性 / 堅牢性)

弱いものの、誤りではありません。refactoring 時に対応します。

| # | パターン | 修正前 | 修正後 |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | 一度も呼ばれない `clickEdit()`; unjustified empty wrapper class; 別 spec と丸ごと重複した spec; 理由のない skip | unused members と zombie specs を削除する。残す skip には理由を明記し、長期保留には再確認の目安を付ける。single-use helpers は meaningless indirection を明確に減らす場合だけ inline する |
| 21 | **Manually-captured session-file dependency** | manual capture script でしか生成されない `storageState: 'auth/member.json'` — CI にはなく、静かに期限切れになる | session を programmatically regenerate する (API-login helper または `setup` project)。manual files は programmatic fallback 付き cache としてのみ使う |
| 23 | **Fixture ignores render guards** | Liked-tab fixture が `liked: false` を seed し、card component がすべての item を `return null` する。empty UI が infra flake に見える | seed 前に item component の early returns/filters を読み、対象 view のすべての guard を通る fields を seed する |

## 失敗デバッグ

両方のデバッガーは、同じ安定した F1–F15 root-cause taxonomy を使います。Playwright は `playwright-report/`、HTML report、`trace.zip`、screenshot、範囲を限定した GitHub Actions artifact を受け付けます。Cypress は mochawesome または JUnit report、screenshot、video、範囲を限定した CI artifact を受け付けます。

| # | 分類 | 手がかり |
|---|----------|---------|
| F1 | **不安定 / タイミング** | `TimeoutError`, 再試行では通る |
| F2 | **セレクター破損** | `locator not found`, `strict mode violation` |
| F3 | **ネットワーク依存** | `net::ERR_*`, 予期しない API レスポンス |
| F4 | **アサーション不一致** | `Expected X to equal Y`, subject の取り違え |
| F5 | **Then の欠落** | 操作は完了したが、誤った状態が残る |
| F6 | **条件分岐の欠落** | 要素が条件付きで存在するのに、アサーションが常に実行される |
| F7 | **テスト分離の失敗** | 単独では通り、テストスイートでは失敗する |
| F8 | **環境差異** | CI とローカルの片方でだけ発生する。viewport、OS、timezone |
| F9 | **データ依存** | seed データの欠落、hardcoded IDs |
| F10 | **認証 / セッション** | セッション期限切れ、role-based UI が描画されない |
| F11 | **非同期/コマンド順序の競合** | Playwright の `Promise.all` 順序・並行処理の競合、Cypress のリクエスト後の intercept 登録・コマンドチェーン順序の入れ替わり・visit/request 競合 |
| F12 | **POM / Locator のずれ** | DOM 構造が変わったのに POM が更新されていない |
| F13 | **エラー握りつぶし** | `.catch(() => {})` が実際の失敗を隠している |
| F14 | **アニメーション競合** | 内容がまだ描画されていない、または一時的な要素が観測前に削除される |
| F15 | **ハイドレーション競合** | 操作は成功するが効果がない — SSR ページのハイドレーションがまだ完了しておらず、次のアサーションで失敗する |

ここでは F11 と F12 に framework 共通の名称を使用しています。各 `debugger` は、同じ stable code に対応する framework 固有の名称を報告します。


デバッガーはプロダクト回帰と壊れやすいテストを分けて分類し、根拠と具体的な修正を返します。失敗した Playwright または Cypress テスト artifact がないアプリケーションや backend は診断しません。

## スタンドアロンスキャナー

決定論的な機械的レイヤーを直接実行できます。

```bash
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

スキャナーには PCRE2 対応の `rg` と Python 3 が必要です。Python が NUL-safe な candidate identity records を作成・検証するため、candidate drift や不正な record は fail closed になります。この必須の bookkeeping は optional な Tier 2 AST tooling とは別です。デフォルトでは、target-controlled な ESLint binaries、plugins、parsers、configuration を実行せず、tools も download しません。`E2E_SMELL_ALLOW_PROJECT_ESLINT=1` は trusted checkout で project ESLint execution を opt in します。`E2E_SMELL_NO_ESLINT_DOWNLOAD=0` と `E2E_SMELL_NO_AST_GREP_DOWNLOAD=0` は、それぞれ pinned downloads を opt in します。portability check で preinstalled host binaries を無視する必要がある場合は、`E2E_SMELL_DISABLE_AST_GREP=1` を設定してください。

> **読み取り範囲。**
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> 同梱 checks は、requested path 配下の source を report します。Framework provenance resolution は、containing project 内の別の場所にある relative fixture/support imports も読む場合があります。
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->

<!-- README-CONTRACT:SCANNER-EXTENSIONS:START -->
同梱 checks は `.ts`, `.js`, `.tsx`, `.jsx`, `.mts`, `.mjs`, `.cts`, `.cjs` の source を読み取ります。
<!-- README-CONTRACT:SCANNER-EXTENSIONS:END -->

Tier 3 は同梱 fallback です。optional ESLint と ast-grep tiers は精度を高めますが、semantic review を置き換えるものではありません。scanner は infrastructure または filesystem errors では false clean result を報告せず、exit 2 で終了します。trust と network boundary については [SECURITY.md](SECURITY.md) を参照してください。

## ESLint plugin との違い

`eslint-plugin-playwright` と `eslint-plugin-cypress` は、構文ルールの every-commit baseline として優れています。`e2e-skills` は、そこに 2 つの異なる layer を追加します。

- 明示的に有効化されない限り target project の lint stack を実行しない secure-default scanner
- テスト意図や複数ファイルの文脈が必要な指摘に対する意味的なレビュー

linter は直接的な Locator truthiness assertion や missing `await` を検出できます。しかし、「shows a duplicate-name error」という名前の test がその error を本当に確認しているか、protected-route test が authentication を忘れていないか、optimistic UI assertion が backend request の発生を証明しているかは判断できません。継続的な linting には plugin を使い、test trustworthiness には `e2e-reviewer` を使ってください。

## よくある質問

### 通るのに何もテストしていない Playwright/Cypress テストを見つけるには?

<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->
`e2e-reviewer` skill は、安定した ID と P0/P1/P2 severity を持つ 24 個すべての catalog patterns をレビューします。standalone の `scan.sh` scanner が扱うのは、決定論的で機械的な subset のみです。scanner matches は候補であり、final findings ではありません。skill は verdict を報告する前に intent と surrounding code を確認します。

debugger は、安定した F1–F15 taxonomy に照らして failures を分類します。debugger は、repository を信頼し、environment と flags を含む exact command を承認した後にのみ target-controlled code を実行します。generator は、自身が書いた仕様に対してレビュアーのスキャナーとプロジェクトのテストコマンドを 1 回だけ実行します。

non-public benchmark runs では、`--isolation-wrapper` は required hook であり、isolation の証明ではありません。Continuous integration (CI) は wrapper contract を検証しますが、filesystem、process、network isolation は attestation しません。
<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

該当する spec directory を `e2e-reviewer` に渡してください。指摘を返す前に、決定論的候補と意味的なレビューを組み合わせます。

### これは Playwright/Cypress のテスト実行を置き換えますか?

いいえ。変更のたびにアプリケーションと実際の E2E suite を実行してください。このバンドルはテスト品質をレビューし、Playwright カバレッジを生成し、既存の失敗を診断します。テスト runner ではありません。

### AI が生成した Playwright/Cypress テストはマージ前にどうレビューすればいいですか?

マージ前に、生成された spec を `e2e-reviewer` に渡してください。各テストが名前どおりのユーザー向け動作を本当に証明しているか確認し、false-green のリスクを拾い、決定論的なスキャナー候補と文脈による判断が必要な指摘を分けて報告します。

### Playwright だけでなく Cypress もサポートしますか?

レビューと失敗デバッグは両方の framework をサポートします。新規テスト生成は現在 Playwright のみをサポートします。Cypress デバッガーは mochawesome と JUnit report を受け付けます。

### CI でだけ失敗するテストをデバッグできますか?

はい。ローカル report artifact またはサポート対象の GitHub Actions run を提供した場合に対応できます。デバッガーは F1–F15 taxonomy を使い、環境、timing、selector、data、認証、product-regression の原因を分離します。

### どの AI コーディングエージェントがサポートされていますか?

Claude Code、Codex、そして `skills` CLI がサポートする 55+ hosts は public `SKILL.md` contracts を読み込めます。optional host-specific agent files は利用可能な環境で delegation を改善しますが、public skills はそれらなしでも利用できます。

## 詳細ドキュメント

- [AI が生成した Playwright/Cypress E2E テストをレビューする方法](docs/review-ai-generated-e2e-tests.md)
- [Playwright/Cypress E2E テストスメル 24 種](docs/e2e-test-smells.md)
- [ルールの自己監査](docs/rule-self-audit.md)
- [オープンソースの事例集](docs/case-studies.md)
- [ベンチマーク状況と否定的結果](benchmarks/STATUS.md)
- [生のベンチマーク実行アーティファクト(Hugging Face データセット)](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks)
- [外部根拠台帳](docs/llm-generated-e2e-test-evidence.md)
- [過去の AI レビューベンチマーク](docs/ai-reviewer-benchmark.md)
- [デバッガーベンチマーク手順](docs/debugger-benchmark/README.md)
- [フレームワークの対象範囲](docs/framework-scope.md)
- [ローカル E2E ルールブリッジと推奨 lint](docs/recommended-lint.md)
- [ロードマップ](docs/roadmap.md)
- [Reviewer evidence execution plan and optional Jev experiment](docs/plans/reviewer-evidence-next-steps.md)

予定している作業には cross-model convention consistency と stronger deterministic detection が含まれます。専用の verification が pass する前に、roadmap item を shipped とは説明しません。

## コントリビューション

bug report、false-positive guard、新しい anti-pattern、翻訳を歓迎します。setup と verification requirements については [CONTRIBUTING.md](CONTRIBUTING.md) から始めてください。cross-agent maintenance contracts は [AGENTS.md](AGENTS.md) にあります。

## ライセンス

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha)。詳細は [LICENSE](LICENSE) を参照してください。

一部のベンチマーク記録には、Playwright 公式エージェント定義（Apache-2.0、Microsoft）の引用が含まれています。詳細は [NOTICE](NOTICE) を参照してください。Playwright は Microsoft Corporation の商標であり、このプロジェクトは Microsoft と提携しておらず、承認も受けていません。
