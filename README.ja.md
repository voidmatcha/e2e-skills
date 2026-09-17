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

<!-- README-CANONICAL-REVISION: sha256=2e9549e2984735412031c61f14c30c7c9eecb2d1e4a5c996d37b607ba643cefb; bytes=exact-README.md-UTF-8; translation-quality=not-attested -->

`e2e-skills` は、AI コーディングエージェントが Playwright/Cypress の E2E テスト作業に使える 4 つのワークフローを提供します。Playwright カバレッジの生成、既存のテスト仕様または PR/diff 範囲の変更レビュー、失敗した Playwright レポートのデバッグ、失敗した Cypress レポートのデバッグを扱います。レビューカタログのうち、機械的に判定できる部分集合を検出する決定論的スキャナーも含まれます。

<p align="center">
  <a href="https://www.kimi.ai/resources/software-testing-skills">
    <img src="docs/assets/kimi-software-testing-skills.png" alt="Kimi 公式サイトの「AI Software Testing Skills for Smarter QA Automation」に掲載された e2e-skills" width="100%" />
  </a>
  <br />
  <sub><a href="https://www.kimi.ai/resources/software-testing-skills">Kimi 公式サイトの「AI Software Testing Skills for Smarter QA Automation」で紹介されています。</a></sub>
</p>

人間または AI が作成したテストでは、`e2e-reviewer` を独立した品質ゲートとして利用できます。合格したテストが、タイトルに書かれた動作を本当に証明しているかを確認します。

| 必要なこと | スキル | 結果 |
| --- | --- | --- |
| 新しい Playwright カバレッジを生成 | `playwright-test-generator` | 探索、承認、レビューを経た Playwright テスト仕様 |
| Playwright/Cypress テストまたは PR/diff 変更をレビュー | `e2e-reviewer` | 具体的な修正と introduced/worsened/pre-existing の帰属を伴う検証済み P0/P1/P2 指摘 |
| 失敗した Playwright 実行をデバッグ | `playwright-debugger` | F1–F15 の根本原因、根拠、修正 |
| 失敗した Cypress 実行をデバッグ | `cypress-debugger` | F1–F15 の根本原因、根拠、修正 |
| 決定論的なローカルスキャンを実行 | `skills/e2e-reviewer/scripts/scan.sh` | 対象プロジェクトの package に依存しない機械的候補 |

生成器はカバレッジ不足を分析し、実ブラウザーで探索してから、シナリオ承認後にテストを生成し、各候補を検証します。2 つのデバッガーは失敗した実行の artifact から始め、分類した根本原因、根拠、具体的な修正を返します。

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

## テストが失敗しうることを証明する

良い matcher だけでは不十分で、挙動が壊れたときにテストが red になる必要があります。各候補について、V2 は主要な assertion を反転し、V3 は承認済みの一時コピーへ根拠のある製品障害を注入して、予告した箇所と不一致での失敗を要求します。元の候補は byte-identical のまま保ち、timeout、ブラウザークラッシュ、設定エラーは認めず、安全でない検証は `CANNOT_VERIFY` と報告します。

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

Codex の delegation では、`e2e-reviewer`、`playwright-debugger`、`cypress-debugger` が native role の delegation を試みるか、同等の inline fallback を使えます。`playwright-test-generator` には、より厳格な V6 境界があります。独立した fresh-context reviewer がない場合は、`CANNOT_VERIFY` と `PARTIAL/BLOCKED` を報告します。

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

for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
  ln -s "$HOME/.claude/e2e-skills/skills/$skill" "$HOME/.claude/skills/$skill"
done
```

同名のスキルがすでにある場合、リンク作成は上書きせずに失敗します。Claude Code で `/skills` を実行し、4 つの名前がすべて表示されることを確認してください。

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

同梱の shell scripts と artifact readers は macOS/Linux shell を対象にしています。Windows ユーザーは WSL 経由で実行し、scan/report artifacts を WSL filesystem 内に置いてください。

生成したテストが通るだけでは不十分です。`Locator` や `Promise` 自体を検証していたり、テスト名に記した動作と無関係な状態を見ていたり、主要な assertion がテストの成否に影響していないことがあります。そのため生成器は、適用可能な [V1–V6 verification](skills/playwright-test-generator/verification-rules.md) をすべて通過するまで、新しい spec を候補として扱います。

テスト一式を生成する前に、各シナリオが既存のテストとは異なるユーザーリスクを扱うか、E2E が適切なテスト層か、失敗原因を特定できる根拠があるかを確認します。初回導入またはリスクの高い作業では、代表シナリオを 1 件だけ `e2e-reviewer` と V1–V6 で検証してから、残りのテストを生成します。

テスト生成は CLI-first、verification-first のフローに従います。ライブ探索では、互換性のあるプロジェクトローカルの Playwright CLI（`playwright cli`）、別途インストール済みの `@playwright/cli` パッケージが提供するコマンド（`playwright-cli`）、`agent-browser`、実行環境に既に接続されている Playwright MCP、制限付き ARIA fallback の順に使います。非推奨のスコープなし `playwright-cli` パッケージは使用しません。これらは探索手段であり、テストランナーではありません。生成した候補は、必ずリポジトリ標準の Playwright Test コマンドで実行します。プロジェクトが Playwright Test Agents をサポートし、それらが初期化済みであれば、admission gate に応じて根拠付きの計画案を補助できます。ただし、最終実装はこの生成器が担い、V1–V6 verification を合格条件とします。

## レビューの仕組み

有効なテストコードを生成することと、プロダクトが間違っているときに失敗するテストを生成することは別です。このワークフローは、機械的な検出と意味的な判断を分離します。

1. スキャナーは Locator truthiness、focused tests、`await` の欠落、blanket error suppression など、決定論的に見つけられる候補を検出します。
2. `e2e-reviewer` は指摘を確定する前に、テスト名、操作、assertion、helper、Page Object、fixture、設定を読みます。
3. 指摘は安定した pattern ID と P0/P1/P2 severity を使うため、修正と回帰を比較できます。
4. 修正後、ワークフローはスキャナーと、プロジェクトで承認された E2E または lint コマンドを再実行します。

スキャナーの一致は候補であり、判定ではありません。認証の欠落、呼び出し証明のない optimistic UI、name/assertion mismatch、render guard に阻まれる fixture など、複数ファイルにまたがる指摘には意味的なレビューが必要です。

## 根拠と限界

現在の根拠で支えられる主張は限定的です。このプロジェクトには動作で裏付けた開発根拠とアップストリームにマージされた 15 件の修正がありますが、一般化されたレビュー精度は主張しません。

マージ件数に分母がつきました。[Field review v1](benchmarks/field-review-v1/README.md) は、このアカウントが出したプルリクエストのうち本文にスキル名を含むものをすべて走査し、GitHub が報告する結果をそのまま記録します。26 リポジトリに 29 件提出、マージ 16 件、マージなしクローズ 6 件、オープン 7 件です。手作業の一覧ではなく GitHub から生成したことで、ロードマップに載っていなかった 7 件が見つかり、うち 2 件はマージ、3 件は却下でした。

これも精度の数値ではありません。マージはメンテナーがパッチを受け入れたことを意味し、指摘の重大度分類が正しかったことを保証しません。提出署名は任意なので、署名のない却下は比率を上振れさせます。ただしこの判定だけは、このプロジェクトの管理下にありません。

決定的スキャナーは別途測定します。[Field scan v1](benchmarks/field-scan-v1/README.md) では、同じ 12 件の公開リポジトリを固定したコミットで再スキャンし、従来の 30 分の制限とデフォルトの候補数上限を適用しています。**12 件中 10 件はルールの抑制なしにスキャンを完了し、P0 0 件を報告しました**。残る 2 件はタイムアウトしました。結果一覧では要レビューの候補を別に示しており、再現率や適合率を証明するものではありません。以前の「`#3` の確定ヒット 294 件」という報告は、スキャナーの分類上の欠陥によるものでした。訂正内容と当時の変更前後の比較結果は、リンク先に記載しています。その後、別途公開されたプロトコル（30 分の制限を撤廃し、スキャナーの上限を文書化されたハード上限まで引き上げ）を用いた[完了拡張作業](benchmarks/field-scan-v1-extension/README.md)が、当初設計された 12 件のサンプルを完成させました — タイムアウトしていた 2 件はいずれも抑制されたルールなしに正常終了し、P0 0 件を報告しました。この拡張作業は固定された v1 台帳を書き換えるものではありません。

- 最も強い独立した signal はスコアではありません。常に通過する Locator アサーションのパターン (`#4f`) が公式の `eslint-plugin-playwright` に `no-unnecessary-assertions` ルールとして採用されました (マージ済みのプルリクエストは [ロードマップ](docs/roadmap.md) を参照)。このプロジェクトと利害関係のない外部メンテナーがルール定義を受け入れたということです。同時に、現在の lint がその形状を検出するようになったため、このプロジェクトはもうその事例を自分の成果として主張しません。
- `docs/rule-self-audit.md` は、2 つのモデル系統による敵対的監査で、このプロジェクト**自身**の P0 ルールに見つかった欠陥を記録しています。単一のレビューアーであれば通過させていたルールが含まれます。
- ブラウザー障害注入は、**12 個の障害演算子と 3 種類の期待結果を組み合わせた Playwright/Cypress セル 36 件すべて**で完了しています。これはハーネスの自己テストです。アプリケーション、堅牢なテスト、注入した障害、脆弱なテストのすべてをこのリポジトリで書いているため、検出器が設計どおりに動作することを示すだけであり、一般化を意味しません。
- [Healer perturbation v1](benchmarks/healer-perturbation-v1/README.md) は、**凍結済みの Codex セル 30 件すべて**を完了し、`REJECT` を返しました。ガード付きの公式 healer prompt と、このリポジトリが提案した Step 7 workflow は、どちらも修復不可能な honesty control 3 件すべてを弱めました。この結果は両 healer 経路を安全なデフォルトとして採用しないことを意味しますが、Claude、一般的な healer 品質、reviewer 精度を測定したものではなく、product instructions も変更していません。
- exact レビューベンチマークは **証明済みの false-green 事例 12 件と正常コードの保護事例 12 件**を対象にしています。10 件の障害事例は byte-identical operator mutants です。
- Independent product-review robustness gates v4、v5、v7、v8 は事前登録した基準を満たしませんでした。v6 と v9 は未実行で、v10 は凍結済みですが未実行です。v1 から v10 は、現在のリリースゲートではなく、過去の robustness evidence として保持しています。
- デバッガー protocol は再実行可能な 30-case synthetic corpus を提供しますが、独立に確立されたデバッガー精度は主張しません。

スコア、失敗したゲート、置き換えられた実行、主張の境界については [ベンチマーク状況](benchmarks/STATUS.md) を参照してください。[研究根拠台帳](docs/llm-generated-e2e-test-evidence.md) は、隣接する unit-test や custom-agent studies をこのプロジェクトの測定値として扱わず、59 件の外部 source を監査しています。

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
| 13 | **Inconsistent POM usage** | POM を import しているのに、POM-owned actions に raw `page.fill`/`page.click` を使っている | すべての interactions を POM 経由にし、UI changes の更新箇所を 1 か所にまとめる |
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
| 11 | **YAGNI + Zombie Specs** | 一度も呼ばれない `clickEdit()`; unjustified empty wrapper class; 別 spec と丸ごと重複した spec; 理由も再確認の目安もない skip | unused members と zombie specs を削除する。残す skip には理由と期限を明記し、single-use helpers は meaningless indirection を明確に減らす場合だけ inline する |
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

debugger は、安定した F1–F15 taxonomy に照らして failures を分類します。debugger と generator は、repository を信頼し、environment と flags を含む exact command を承認した後にのみ target-controlled code を実行します。

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
- [外部根拠台帳](docs/llm-generated-e2e-test-evidence.md)
- [過去の AI レビューベンチマーク](docs/ai-reviewer-benchmark.md)
- [デバッガーベンチマーク手順](docs/debugger-benchmark/README.md)
- [フレームワークの対象範囲](docs/framework-scope.md)
- [ロードマップ](docs/roadmap.md)

予定している作業には cross-model convention consistency と stronger deterministic detection が含まれます。専用の verification が pass する前に、roadmap item を shipped とは説明しません。

## コントリビューション

bug report、false-positive guard、新しい anti-pattern、翻訳を歓迎します。setup と verification requirements については [CONTRIBUTING.md](CONTRIBUTING.md) から始めてください。cross-agent maintenance contracts は [AGENTS.md](AGENTS.md) にあります。

## ライセンス

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha)。詳細は [LICENSE](LICENSE) を参照してください。
