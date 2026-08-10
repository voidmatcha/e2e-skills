<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — Playwright와 Cypress용 Agent Skills: 신뢰할 수 있는 E2E 테스트를 생성, 리뷰, 디버깅합니다." width="100%" />
</div>

# e2e-skills: 기능이 깨져도 통과하는 Playwright와 Cypress E2E 테스트 찾기

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
<a href="README.md">🇺🇸 English</a> | <strong>🇰🇷 한국어</strong> | <a href="README.ja.md">🇯🇵 日本語</a> | <a href="README.zh-cn.md">🇨🇳 简体中文</a>
</p>

<!-- README-CANONICAL-REVISION: sha256=ccdd5be58c599b15a7c911a1923c758831ac091d08d25a1f1835a69e2f551911; bytes=exact-README.md-UTF-8; translation-quality=not-attested -->

CI는 통과하지만 사용자가 실제로 겪는 동작은 검증하지 못하는 Playwright와 Cypress E2E 테스트를 찾아냅니다.

`e2e-skills`는 AI 코딩 에이전트가 E2E 테스트를 작성하고 검토하며 디버깅할 때 쓰는 네 가지 스킬을 묶은 프로젝트입니다. 새 Playwright 테스트 작성, 기능이 깨져도 통과하는 Playwright/Cypress 테스트 검토, 실패한 Playwright 또는 Cypress 보고서 분석을 지원합니다. 기계적으로 판별할 수 있는 허위 통과 패턴을 찾는 결정적 스캐너도 들어 있습니다.

**왜 써야 하나요?** `e2e-reviewer`가 찾아낸 문제를 고친 PR 14건이 Storybook, SvelteKit, code-server, Strapi, Carbon Design System, Ghost, MUI X를 비롯한 [업스트림 프로젝트에 병합되었습니다](#open-source-adoption).

> code-server에서는 저장소에 들어간 `it.only` 하나가 7개월 동안 테스트 8개를 조용히 비활성화했습니다. 건너뛴 테스트 중 하나는 이미 깨져 있었지만 CI는 계속 통과했습니다.

## 기능이 깨져도 통과하는 테스트

**false-green** 테스트는 이름에 적힌 동작이 되든 안 되든 통과합니다. 불안정한(flaky) 테스트와는 다릅니다. 불안정한 테스트는 가끔 실패하므로 재시도 대시보드나 flake 분석이 결국 잡아냅니다. false-green 테스트는 **제품이 깨졌을 때조차 실패하지 않으므로**, 테스트가 뒤집히는지 감시하는 어떤 도구에도 절대 잡히지 않습니다.

이 Playwright 테스트는 그럴듯해 보이지만 `Locator` 객체가 생성됐다는 사실만 증명합니다.

```typescript
import { expect, test } from '@playwright/test';

test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();
  expect(page.locator('.user-badge')).not.toBeNull();
});
```

제대로 된 테스트라면 사용자가 보는 동작을 검증하고, 그 동작이 깨졌을 때 실패해야 합니다.

```diff
- expect(page.getByText('Welcome back')).toBeDefined()
+ await expect(page.getByText('Welcome back')).toBeVisible()
```

함께 제공되는 스캐너는 별도의 프로젝트 설정 없이 이런 허위 검증문을 찾아냅니다.

```console
$ /bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests/

[P0] #4f Locator always-true assertion (truthy/defined/not-null) (2 hits)
  tests/login.spec.ts:6:  expect(page.getByText('Welcome back')).toBeDefined();
  tests/login.spec.ts:8:  expect(page.locator('.user-badge')).not.toBeNull();

Summary: 2 total hit(s), 2 P0
```

`eslint-plugin-playwright`도 `no-unnecessary-assertions`로 이 형태를 잡습니다. 그 규칙을 켜세요 — 매 커밋마다 도는 규칙이, 기억해서 돌려야 하는 검토보다 낫습니다. 스캐너는 실행할 때마다 어떤 지적이 이미 여러분의 lint 설정이 맡아야 할 몫인지 함께 출력하므로, 둘은 경쟁하지 않고 서로를 보완합니다.

## 테스트가 실패할 수 있음을 증명하기

검증문이 잘 생겼다고 통과하는 테스트는 아닙니다. 린트는 `toBeVisible()`이 올바른 matcher라는 건 알려주지만, 기능이 깨졌을 때 그 테스트가 빨개지는지는 알려주지 못합니다.

`playwright-test-generator`가 이 질문에 직접 답합니다. 프로젝트가 승인한 임시 복사본에서 핵심 검증문을 반전하고(V2), 근거가 확인된 제품 결함을 주입한 뒤(V3), 미리 지정한 위치에서 예상한 불일치로 실패할 것을 요구합니다. 제한 시간, 브라우저 충돌, 설정 오류로 실패한 실행은 인정하지 않습니다. 안전하게 증명할 수 없는 것은 추측하지 않고 `CANNOT_VERIFY`로 보고합니다.

이것은 후보 spec 하나로 범위를 좁힌 뮤테이션 테스팅입니다. 그 좁힘이 비용을 감당 가능하게 만듭니다 — E2E에서 스위트 전체를 뮤테이션하는 것은 그렇지 않기 때문입니다.

## 설치하고 사용해 보기

### Claude Code

플러그인 마켓플레이스에서 설치합니다.

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

또는 검증된 버전으로 고정한 공통 설치 CLI를 사용해 네 스킬을 복사본으로 설치합니다.

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

네 가지 스킬을 `~/.agents/skills/`에 설치합니다.

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a codex
```

Codex가 작업을 나눌 때 `e2e-reviewer`, `playwright-debugger`, `cypress-debugger`는 네이티브 역할이나 그와 동등한 내장 대체 경로를 사용할 수 있습니다. `playwright-test-generator`에는 더 엄격한 V6 경계가 적용됩니다. 새 문맥에서 검토할 별도 리뷰어가 없으면 `CANNOT_VERIFY`와 `PARTIAL/BLOCKED`를 보고합니다. 소스 체크아웃에는 `.codex/agents/` 아래에 선택적으로 설치할 수 있는 네이티브 에이전트도 들어 있습니다. 패키징 경계는 [AGENTS.md](AGENTS.md)에서 확인할 수 있습니다.

Codex 플러그인 마켓플레이스를 쓰는 다른 설치 경로:

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

### 그 외 에이전트

`skills` CLI가 지원하는 모든 실행 환경에 전역 설치합니다.

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all
```

특정 실행 환경 하나에만 설치하려면 `--all`을 `-a <agent>`로 바꿉니다. 지원하는 실행 환경은 [supported agents](https://github.com/vercel-labs/skills#supported-agents) 목록에서 확인할 수 있습니다. 검증되지 않은 새 버전이 실행되지 않도록, 위 명령은 검증된 CLI 릴리스로 버전을 고정합니다.

### Claude Code 수동 체크아웃

체크아웃은 `~/.claude/skills/` 밖에 두고, 공개 스킬 디렉터리 네 개를 각각 연결합니다.

```bash
git clone https://github.com/voidmatcha/e2e-skills.git "$HOME/.claude/e2e-skills"
mkdir -p "$HOME/.claude/skills"

for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
  ln -s "$HOME/.claude/e2e-skills/skills/$skill" "$HOME/.claude/skills/$skill"
done
```

같은 이름의 스킬이 이미 있으면 링크 생성은 기존 파일을 덮어쓰지 않고 실패합니다. Claude Code에서 `/skills`를 실행해 네 스킬이 모두 표시되는지 확인합니다.

### 첫 요청

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

## 제공 내용

| 필요 | 스킬 | 결과 |
| --- | --- | --- |
| 새 Playwright 테스트 작성 | `playwright-test-generator` | 탐색, 승인, 검토를 거친 Playwright 테스트 |
| 통과 중인 Playwright/Cypress 테스트 검토 | `e2e-reviewer` | 구체적인 수정안과 함께 검증된 P0/P1/P2 지적 사항 |
| 실패한 Playwright 실행 분석 | `playwright-debugger` | F1–F15 근본 원인, 근거, 수정안 |
| 실패한 Cypress 실행 분석 | `cypress-debugger` | F1–F15 근본 원인, 근거, 수정안 |
| 결정적 로컬 스캔 | `skills/e2e-reviewer/scripts/scan.sh` | 대상 프로젝트의 패키지 없이 기계적으로 찾은 후보 |

AI가 만들었거나 기존에 물려받은 E2E 테스트가 의도한 결과를 증명하지 못한 채 통과할 수 있다면 이 스킬 묶음을 사용하세요. 애플리케이션과 실제 E2E 테스트 모음 실행, 일반 린트 프리셋, 프레임워크 공통 테스트 도구를 대신하는 용도로는 쓰지 마세요. Playwright와 Cypress를 지원하며, 새 테스트 작성은 현재 Playwright만 지원합니다.

새로 만든 테스트가 통과한다고 해서 충분한 것은 아닙니다. `Locator`나 `Promise` 자체를 검증하거나, 테스트 이름에 적힌 동작과 무관한 상태를 확인하거나, 핵심 검증문이 실패 여부를 좌우하지 않을 수 있습니다. 그래서 생성기는 적용 가능한 [V1–V6 검증](skills/playwright-test-generator/verification-rules.md)을 모두 통과하기 전까지 새 테스트를 후보로 취급합니다.

프로젝트가 승인한 임시 복사본에서 V2는 핵심 검증문을 반전하고, V3는 근거가 확인된 제품 결함을 주입합니다. 미리 지정한 핵심 검증문이 예상한 위치에서 예상한 불일치로 실패해야만 결함을 잡은 것으로 인정합니다. 설정, 제한 시간, 브라우저, 인프라 오류로 실행이 실패한 경우는 인정하지 않습니다. 원본 후보는 바이트 단위로 그대로 유지하며, 안전하게 실행할 수 없는 검증은 추측하지 않고 `CANNOT_VERIFY`로 보고합니다.

## 검토 방식

실행 가능한 테스트 코드를 만드는 것과 제품에 문제가 생겼을 때 제대로 실패하는 테스트를 만드는 것은 별개의 일입니다. 이 절차는 기계적 탐지와 문맥에 따른 판단을 분리합니다.

1. 스캐너는 Locator의 참·거짓 판정, focused test, 누락된 `await`, 포괄적인 오류 억제처럼 기계적으로 확정할 수 있는 후보를 찾습니다.
2. `e2e-reviewer`는 지적 사항을 확정하기 전에 테스트 이름, 동작, 검증문, 헬퍼, Page Object, fixture, 설정을 읽습니다.
3. 각 지적 사항에는 안정적인 패턴 ID와 P0/P1/P2 심각도를 붙이므로 수정 전후와 회귀 여부를 비교할 수 있습니다.
4. 수정한 뒤에는 스캐너와 프로젝트에서 승인한 E2E 또는 린트 명령을 다시 실행합니다.

스캐너가 찾은 결과는 후보일 뿐 최종 판정이 아닙니다. 인증 누락, 네트워크 호출을 입증하지 않는 낙관적 UI, 이름과 검증문 불일치, 렌더링 가드를 통과하지 못하는 fixture처럼 여러 파일을 함께 살펴야 하는 문제에는 문맥 검토가 필요합니다.

## 근거와 한계

현재 근거로 뒷받침할 수 있는 주장은 제한적입니다. 이 프로젝트에는 동작으로 확인한 개발 근거와 실제 오픈소스 적용 사례가 있지만, 이를 바탕으로 일반적인 검토 정확도를 주장하지는 않습니다.

- 브라우저 결함 주입은 **Playwright/Cypress 셀 36개 중 36개**에서 완료했습니다.
- 정밀 리뷰어 벤치마크는 **입증된 허위 통과 사례 12개와 정상 코드 보호 사례 12개**를 다룹니다. 결함 사례 중 10개는 바이트 단위로 동일한 연산자 변이입니다.
- 독립 견고성 게이트 v4, v5, v7, v8은 사전 등록 기준에 실패했습니다. V6와 v9은 실행하지 않았고, v10은 동결됐지만 실행하지 않았습니다.

점수, 실패한 게이트, 대체된 실행, 주장 범위는 [벤치마크 현황](benchmarks/STATUS.md)을 참고하세요. [연구 근거 원장](docs/llm-generated-e2e-test-evidence.md)은 인접 분야의 단위 테스트나 맞춤형 에이전트 연구를 이 프로젝트가 직접 측정한 결과처럼 취급하지 않고, 외부 출처 59개를 구분해 검토합니다.

## E2E 리뷰 목록

목록에는 ID가 안정적으로 유지되는 Playwright/Cypress 테스트 냄새 24개가 들어 있습니다. 대표적인 허위 통과 유형으로는 Locator의 참·거짓 판정, 검증문 누락, 오류 삼키기, focused test, 인증 누락, 네트워크 호출을 입증하지 않는 낙관적 UI 검증이 있습니다. [전체 분류와 근거](docs/e2e-test-smells.md)를 참고하세요.

<details>
<summary>심각도별 24개 패턴 보기</summary>

### 24개 패턴 — 심각도별 분류

#### P0 — 반드시 수정 (문제가 있어도 통과)

기능이 깨져도 테스트가 통과합니다. 실제 검증이 일어나지 않습니다.

| # | 패턴 | 수정 전 | 수정 후 |
|---|---------|--------|-------|
| 1 | **이름과 검증문 불일치** | 이름에는 "status"가 있지만 `toBeVisible()`만 확인 | 상태 내용을 검증하거나 실제 검증 내용에 맞게 이름 변경 |
| 2 | **Then 누락** | 취소한 뒤 텍스트 복원만 확인하고 입력란이 사라졌는지는 확인하지 않음 | 복원된 상태와 입력란이 닫힌 상태를 모두 검증 |
| 3 | **오류 삼키기** | 테스트의 `try/catch`, POM의 `.catch(() => {})` | 오류가 테스트 실패로 이어지게 하고 POM 메서드의 무시하는 catch 제거 |
| 3b | **Cypress `uncaught:exception` 억제** | `cy.on('uncaught:exception', () => false)`가 모든 애플리케이션 오류를 무시 | 이미 알려진 특정 오류에만 핸들러를 적용하고 알 수 없는 오류는 다시 throw |
| 4 | **무의미하거나 재시도를 약화하는 검증문** (P0/P1) | P0: 항상 같은 결과를 내는 조건식과 Locator의 참·거짓 판정. P1: 약한 DOM 연결 확인, 한 번만 읽은 값/URL, 제한 시간 0으로 인한 재시도·마감 위험, 사전 입증 없는 요소 부재, 약속한 접근성 이름이 빠진 ARIA 스냅샷 | 의미 있는 범위와 자동 재시도를 지원하는 web-first 검증문 사용. 부재를 확인하기 전에 존재를 입증하고, 약속한 접근성 이름을 핵심 검증 조건으로 유지 |
| 5 | **우회 패턴** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`, 근거 주석 없는 `{ force: true }` | 조건 없이 항상 검증. 환경 확인은 `beforeEach`로 이동하고 `force: true`에는 `// JUSTIFIED:` 추가 |
| 7 | **Focused test 유출** | `test.only(...)`가 커밋되어 CI가 테스트 하나만 실행하고 나머지는 조용히 건너뜀 | `.only` 삭제. 로컬에서 일부만 실행할 때는 `--grep` 또는 `--spec` 사용 |
| 8 | **검증문 누락** | 사용하지 않는 locator/boolean이 시나리오의 유일한 검증 | `await expect(locator).toBeVisible()` 추가. 별도의 검증이나 실패 근거가 이미 있으면 #8 제외 |
| 12 | **인증 설정 누락** | 로그인, `storageState`, 인증 fixture가 없어 보호된 경로의 테스트가 로그인 화면이나 엉뚱한 화면의 일반적인 요소를 보고도 통과 | `beforeEach` 로그인, `storageState` 설정, 인증 fixture 중 하나 사용. 정상적인 인증 실패를 P0으로 분류하지 않음 |

#### P1 — 수정 권장 (진단 품질 저하 / CI 시간 낭비)

테스트는 동작하지만 개발자를 오도하거나 CI 시간을 낭비하거나 미래 회귀를 유발할 수 있습니다.

| # | 패턴 | 수정 전 | 수정 후 |
|---|---------|--------|-------|
| 6 | **직접 DOM 쿼리** | `evaluate()` 안에서 `document.querySelector` 사용 | 프레임워크의 locator/query API(`locator` / `cy.get`) 사용 |
| 9 | **고정 시간 대기** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | 프레임워크의 자동 대기를 활용하고 조건 기반 대기 사용 |
| 10 | **불안정한 테스트 패턴** | 근거 주석 없는 `items.nth(2)`, `test.describe.serial()`, 범위가 정해지지 않은 접근성 이름 부분 문자열(10c), Cypress 비동기 콜백, 변수에 할당한 `cy` 명령, 계속 이어지는 동작 체인(10d–10f) | 안정적이고 범위가 명확한 locator와 독립적인 테스트 사용. Cypress 작업은 명령 체인 안에 유지하고 Chainable을 값으로 할당하지 않으며 동작 후 다시 쿼리 |
| 13 | **일관되지 않은 POM 사용** | POM을 import했지만 테스트가 POM이 맡은 동작에 직접 `page.fill`/`page.click` 사용 | 모든 상호작용을 POM으로 보내 UI 변경 지점을 한곳으로 통합 |
| 14 | **하드코딩된 자격 증명** | 테스트 코드에 `loginPage.login('demo-admin', '<literal-password>')` 사용 | `process.env.TEST_USER`, Playwright 설정의 secret, 테스트 데이터 fixture 사용 |
| 15 | **`expect()`의 `await` 누락** | 비동기 Locator/Page web-first matcher Promise의 실행 순서와 결과를 확인하지 않음. 거부된 Promise는 대개 나중에 엉뚱한 위치의 오류로 나타남 | matcher Promise를 `await`하거나 반환. 동기 값 matcher는 제외 |
| 16 | **동작의 `await` 누락** | actionability 확인, 동작 순서, 탐색이 뒤따르는 작업과 경합할 수 있음. 거부된 Promise는 대개 나중에 엉뚱한 위치의 오류로 나타남 | 동작 Promise를 `await`하거나 반환 |
| 17 | **권장하지 않는 Page 셀렉터 API 직접 사용** | 셀렉터 기반 `page.click`, `page.fill`과 관련 Page 동작이 Locator 계층을 건너뜀 | 조합성, strictness, 재사용성, 명확한 실패 메시지를 위해 Locator 동작 사용 |
| 18 | **`expect.soft()` 과다 사용** | 필수 조건을 엄격하게 확인하기 전에 핵심 soft assertion을 실행해 전제 조건이 깨진 뒤에도 후속 작업이 계속됨 | 핵심 상태를 먼저 일반 검증문으로 차단하고, `soft`는 서로 독립적인 세부 항목에만 사용 |
| 19 | **테스트 코드의 모듈 수준 가변 상태** | 테스트 유틸리티 0열의 `let testNotebookSequence = 0;`가 오래 실행되는 worker에 남아 병렬 worker 사이에서 충돌 | 카운터 삭제. `Date.now()`와 `Math.random().toString(36).slice(2, 8)`로 고유한 값을 만들거나 상태를 `test.beforeEach`로 이동 |
| 20 | **모의 처리하지 않은 실제 백엔드 쓰기** | 회원 가입/결제 테스트가 통제된 테스트 경계 없이 공유 또는 영구 상태에 접근 | 쓰기 요청을 stub 처리하거나 일회용 컨테이너, rollback fixture, 격리된 tenant/database처럼 통제된 백엔드임을 입증 |
| 22 | **호출 근거 없는 낙관적 UI** | 좋아요 전환 테스트가 `aria-pressed` 변경만 검증. UI가 낙관적으로 갱신되면 POST가 사라져도 통과 | UI 검증을 클릭 전에 준비한 `page.waitForRequest()` 또는 route 적중 flag와 함께 사용 |

#### P2 — 개선 권장 (유지보수성 / 견고성)

약하지만 틀린 것은 아닙니다. 리팩터링할 때 처리합니다.

| # | 패턴 | 수정 전 | 수정 후 |
|---|---------|--------|-------|
| 11 | **YAGNI와 좀비 테스트** | 호출되지 않는 `clickEdit()`, 근거 없이 비어 있는 wrapper class, 다른 테스트와 완전히 중복되는 테스트 | 사용하지 않는 멤버와 좀비 테스트 삭제. 의미 없는 간접 계층을 분명히 줄일 수 있을 때만 한 번 쓰는 헬퍼를 인라인화 |
| 21 | **수동으로 캡처한 세션 파일 의존성** | 수동 캡처 스크립트로만 만드는 `storageState: 'auth/member.json'`이 CI에는 없고 예고 없이 만료 | API 로그인 헬퍼 또는 `setup` 프로젝트로 세션을 자동 생성. 수동 파일은 자동 생성 대체 경로가 있는 캐시로만 사용 |
| 23 | **렌더링 가드를 무시하는 fixture** | liked 탭의 fixture가 `liked: false`를 넣어 카드 컴포넌트가 모든 항목에서 `return null`을 실행. 빈 UI가 인프라 불안정처럼 보임 | 데이터를 넣기 전에 항목 컴포넌트의 조기 반환과 필터를 읽고, 테스트할 화면의 모든 가드를 통과하도록 필드 설정 |

</details>

## 실패 디버깅

두 디버거는 동일한 F1–F15 근본 원인 분류를 사용합니다. Playwright 디버거는 `playwright-report/`, HTML 보고서, `trace.zip`, 스크린샷, 범위가 정해진 GitHub Actions 산출물을 입력으로 받습니다. Cypress 디버거는 mochawesome 또는 JUnit 보고서, 스크린샷, 영상, 범위가 정해진 CI 산출물을 받습니다.

<details>
<summary>F1–F15 분류 보기</summary>

| # | 범주 | 주요 신호 |
|---|----------|---------|
| F1 | **불안정성 / 타이밍** | `TimeoutError`, 재시도에서 통과 |
| F2 | **깨진 셀렉터** | `locator not found`, strict mode 위반 |
| F3 | **네트워크 의존성** | `net::ERR_*`, 예상하지 못한 API 응답 |
| F4 | **검증값 불일치** | `Expected X to equal Y`, 실제값과 기대값의 순서 반전 |
| F5 | **Then 누락** | 동작은 끝났지만 잘못된 상태가 남음 |
| F6 | **조건 분기 누락** | 요소는 조건부로 나타나지만 검증문은 항상 실행 |
| F7 | **테스트 격리 실패** | 단독으로는 통과하지만 테스트 모음에서는 실패 |
| F8 | **환경 불일치** | CI에서만 또는 로컬에서만 발생. viewport, OS, timezone 차이 |
| F9 | **데이터 의존성** | seed data 누락, 하드코딩된 ID |
| F10 | **인증 / 세션** | 세션 만료, 역할별 UI가 렌더링되지 않음 |
| F11 | **비동기 순서 가정** | `Promise.all` 순서 가정, 병렬 실행 경합 |
| F12 | **POM / Locator 불일치** | DOM 구조가 바뀌었지만 POM은 갱신되지 않음 |
| F13 | **오류 삼키기** | `.catch(() => {})`가 실제 실패를 숨김 |
| F14 | **애니메이션 경합** | 콘텐츠가 아직 렌더링되지 않았거나 일시적인 요소가 관찰 전에 사라짐 |
| F15 | **Hydration 경합** | 동작은 성공하지만 효과가 없음. SSR 페이지의 hydration이 끝나기 전에 다음 검증문이 실행되어 실패 |

</details>

디버거는 제품 회귀와 깨지기 쉬운 테스트를 구분해 분류하고, 근거와 구체적인 수정안을 제시합니다. 실패한 Playwright 또는 Cypress 테스트 산출물이 없으면 애플리케이션이나 백엔드를 진단하지 않습니다.

## 독립 실행 스캐너

기계적으로 판별할 수 있는 탐지 계층을 직접 실행합니다.

```bash
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

스캐너에는 PCRE2를 지원하는 `rg`와 Python 3가 필요합니다. Python이 NUL-safe 후보 식별 레코드를 생성하고 검증하므로 후보 드리프트나 손상된 레코드는 fail-closed로 처리됩니다. 이 필수 기록 작업은 선택적인 Tier 2 AST 도구와 별개입니다. 기본적으로 대상 프로젝트가 제어하는 ESLint 실행 파일, 플러그인, 파서, 설정을 실행하지 않으며 도구도 내려받지 않습니다. `E2E_SMELL_ALLOW_PROJECT_ESLINT=1`은 신뢰하는 체크아웃에서 프로젝트 ESLint 실행을 명시적으로 켭니다. `E2E_SMELL_NO_ESLINT_DOWNLOAD=0`과 `E2E_SMELL_NO_AST_GREP_DOWNLOAD=0`은 각각 고정 버전 다운로드를 명시적으로 켭니다. 이식성 확인에서 미리 설치된 호스트 실행 파일을 무시해야 할 때는 `E2E_SMELL_DISABLE_AST_GREP=1`을 설정합니다.

> **Read boundary.**
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> 공통 소스 범위는 요청한 path 아래입니다. 번들 lexical filter를 포함한 포함 검사는 그 소스를 보고합니다. 프레임워크 출처 확인은 포함 프로젝트의 다른 위치에 있는 relative fixture/support import도 읽을 수 있습니다.
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->

<!-- README-CONTRACT:SCANNER-EXTENSIONS:START -->
번들 검사는 `.ts`, `.js`, `.tsx`, `.jsx`, `.mts`, `.mjs`, `.cts`, `.cjs` 소스를 읽습니다.
<!-- README-CONTRACT:SCANNER-EXTENSIONS:END -->

Tier 3는 기본으로 제공되는 대체 경로입니다. 선택적으로 사용하는 ESLint와 ast-grep 계층은 정밀도를 높이지만 문맥 검토를 대신하지 않습니다. 인프라 또는 파일시스템 오류가 발생하면 스캐너는 문제가 없다고 잘못 보고하지 않고 종료 코드 2로 끝납니다. 신뢰와 네트워크 경계는 [SECURITY.md](SECURITY.md)를 참고하세요.

## ESLint 플러그인과의 차이

`eslint-plugin-playwright`와 `eslint-plugin-cypress`는 커밋할 때마다 구문 규칙을 확인하기에 좋은 출발점입니다. `e2e-skills`는 여기에 두 가지 계층을 더합니다.

- 사용자가 명시적으로 허용하지 않는 한 대상 프로젝트의 린트 도구를 실행하지 않는 안전한 기본 설정의 스캐너
- 테스트 의도나 여러 파일의 문맥을 확인해야 하는 문제를 위한 의미 검토

린터는 Locator의 참·거짓만 확인하는 검증문이나 누락된 `await`를 찾을 수 있습니다. 하지만 "shows a duplicate-name error"라는 테스트가 실제로 오류를 확인하는지, 보호된 경로의 테스트가 인증을 빠뜨렸는지, 낙관적 UI 검증문이 백엔드 요청까지 증명하는지는 판단할 수 없습니다. 지속적인 린트에는 플러그인을, 테스트 신뢰도 점검에는 `e2e-reviewer`를 사용하세요.

<a id="open-source-adoption"></a>

## 오픈소스 적용 사례

`e2e-reviewer`가 찾아낸 문제를 고친 PR **14건이 업스트림에 병합되었습니다**. 직접 선별한 이 사례들은 실제 활용 사례와 수정 내용을 보여주지만, 전체를 대표하는 검증 표본이나 정확도 추정치는 아닙니다.

| 저장소 | PR | 수정한 패턴 |
| --- | --- | --- |
| Storybook | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Playwright 검증문의 `await` 누락 |
| code-server | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | focused test 유출, matcher 없는 `expect`, 사용하지 않는 가시성 확인 |
| Strapi | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | 사용하지 않는 탐색·상태 확인 |
| SvelteKit | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | 기다리지 않는 Playwright 검증문 |
| Carbon Design System | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | Locator의 참·거짓 판정을 web-first 검증문으로 교체 |
| Ghost | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise인 비활성화 상태를 직접 검증 |
| Cal.com | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | E2E 흐름의 약한 검증 패턴 |
| Bruno | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | 검증과 대기의 안정성 문제 |
| Qwik | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/handle 존재 여부만 확인 |
| Element Web | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator가 null이 아닌지만 확인 |
| MUI X | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | UI handle 확인을 상태 검증으로 교체 |
| module-federation/core | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Cypress 테스트의 불필요하고 포괄적인 `uncaught:exception` 억제 |
| FiftyOne | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Locator 정의 여부 확인을 화면에 나타난 중복 이름 오류 검증으로 교체 |
| Rancher Desktop | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `not.toBeNull()` Locator 검증을 화면에 나타난 WSL 통합 이름 검증으로 교체 |

## 자주 묻는 질문

### 통과하지만 아무것도 테스트하지 않는 Playwright 또는 Cypress 테스트를 어떻게 찾나요?

<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->
`e2e-reviewer`는 안정적인 ID와 P0/P1/P2 심각도가 있는 목록 패턴 24개를 모두 리뷰합니다. 독립 실행 `scan.sh` 스캐너는 결정적으로 잡을 수 있는 기계적 부분집합만 다룹니다. 스캐너 일치는 후보일 뿐 최종 지적이 아닙니다. 이 스킬은 판정을 보고하기 전에 의도와 주변 코드를 확인합니다.

디버거는 안정적인 F1–F15 분류에 맞춰 실패를 분류합니다. 디버거와 생성기는 저장소를 신뢰하고 환경 변수와 플래그를 포함한 정확한 명령을 승인한 뒤에만 대상 프로젝트가 제어하는 코드를 실행합니다.

비공개 벤치마크 실행에서는 `--isolation-wrapper`가 필수 훅이지만 격리 증명은 아닙니다. 지속적 통합(CI)은 래퍼 계약을 검증하지만 파일시스템, 프로세스, 네트워크 격리를 증명하지 않습니다.
<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

검토할 테스트 디렉터리를 `e2e-reviewer`에 지정하세요. 기계적으로 찾은 후보와 문맥 검토 결과를 종합해 지적 사항을 제시합니다.

### 이것이 Playwright 또는 Cypress 테스트 실행을 대체하나요?

아니요. 변경할 때마다 애플리케이션과 실제 E2E 테스트 모음을 실행하세요. 이 스킬 묶음은 테스트 품질을 검토하고, Playwright 테스트를 작성하며, 기존 실패를 진단합니다. 테스트 실행기는 아닙니다.

### AI가 생성한 E2E 테스트는 어떻게 리뷰하나요?

병합하기 전에 생성된 테스트를 `e2e-reviewer`에 지정하세요. 각 테스트가 이름에 적힌 사용자 동작을 실제로 입증하는지 확인하고, 기계적으로 찾은 후보와 문맥 판단이 필요한 지적 사항을 구분해 보고합니다.

### Playwright뿐 아니라 Cypress도 지원하나요?

리뷰와 실패 디버깅은 두 프레임워크를 모두 지원합니다. 새 테스트 생성은 현재 Playwright만 지원합니다. Cypress 디버거는 mochawesome과 JUnit 보고서를 받습니다.

### CI에서만 실패하는 테스트도 디버깅할 수 있나요?

예. 로컬 보고서 산출물이나 지원되는 GitHub Actions 실행 정보를 제공하면 됩니다. 디버거는 F1–F15 분류를 사용해 환경, 타이밍, 셀렉터, 데이터, 인증, 제품 회귀 원인을 구분합니다.

### 어떤 AI 코딩 에이전트가 지원되나요?

Claude Code, Codex와 `skills` CLI가 지원하는 55개 이상의 실행 환경에서 공개 `SKILL.md` 계약을 불러올 수 있습니다. 실행 환경별 에이전트 파일을 선택적으로 설치하면 지원되는 환경에서 작업 분담이 나아지지만, 공개 스킬은 해당 파일 없이도 사용할 수 있습니다.

## 상세 문서

- [Playwright와 Cypress E2E 테스트 냄새 24개](docs/e2e-test-smells.md)
- [규칙 자체 감사](docs/rule-self-audit.md)
- [오픈소스 사례 연구](docs/case-studies.md)
- [벤치마크 현황과 실패 결과](benchmarks/STATUS.md)
- [외부 연구 근거 원장](docs/llm-generated-e2e-test-evidence.md)
- [과거 AI 리뷰어 벤치마크](docs/ai-reviewer-benchmark.md)
- [디버거 벤치마크 프로토콜](docs/debugger-benchmark/README.md)
- [지원 프레임워크 범위](docs/framework-scope.md)
- [로드맵](docs/roadmap.md)

앞으로 모델 간 규칙 적용의 일관성을 높이고 기계적 탐지를 강화할 계획입니다. 전용 검증을 통과하기 전에는 로드맵의 어떤 항목도 출시된 기능으로 설명하지 않습니다.

## 기여

버그 제보, 오탐 방지 사례, 새로운 안티패턴, 번역 기여를 환영합니다. 설정 방법과 검증 요구사항은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요. 에이전트가 따라야 할 유지보수 규칙은 [AGENTS.md](AGENTS.md)에 있습니다.

## 라이선스

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha). [LICENSE](LICENSE)를 참고하세요.
