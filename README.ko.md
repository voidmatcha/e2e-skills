<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — Playwright와 Cypress용 Agent Skills: 신뢰할 수 있는 E2E 테스트를 생성, 리뷰, 디버깅합니다." width="100%" />
</div>

# e2e-skills: Playwright와 Cypress에서 문제 있어도 통과하는 E2E 테스트 찾기

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-4-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#open-source-adoption"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-14-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://agents.md"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="https://www.npmjs.com/package/eslint-plugin-cypress-silent-pass"><img alt="cypress silent-pass npm" src="https://img.shields.io/npm/v/eslint-plugin-cypress-silent-pass?style=flat-square&label=cypress%20lint&labelColor=black&color=37B0E6"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<a href="README.md">🇺🇸 English</a> | <strong>🇰🇷 한국어</strong> | <a href="README.ja.md">🇯🇵 日本語</a> | <a href="README.zh-cn.md">🇨🇳 简体中文</a>
</p>

<!-- README-CANONICAL-REVISION: sha256=f5317938a16fda8b59854508c845b707b92073db1b24a6781f06d9564e0cdf94; bytes=exact-README.md-UTF-8; translation-quality=not-attested -->

CI는 통과하지만 사용자에게 보이는 동작은 검증하지 못하는 Playwright와 Cypress E2E 테스트를 찾아냅니다.

`e2e-skills`는 AI 코딩 에이전트가 E2E 테스트를 생성, 리뷰, 디버깅할 때 쓰는 네 가지 스킬을 묶은 프로젝트입니다. Playwright 테스트 보강, 문제 있어도 통과하는 Playwright/Cypress 명세 리뷰, 실패한 Playwright 또는 Cypress 보고서 디버깅을 다룹니다. 기계적으로 판별할 수 있는 조용한 통과 패턴을 찾는 결정적 스캐너도 포함합니다.

**써볼 이유:** `e2e-reviewer`가 찾아낸 문제는 Storybook, SvelteKit, code-server, Strapi, Carbon Design System, Ghost, MUI X를 포함한 [14건의 업스트림 병합 PR](#open-source-adoption)에 기여했습니다.

> code-server에서는 저장소에 들어간 `it.only` 하나가 7개월 동안 테스트 8개를 조용히 비활성화했습니다. 건너뛴 테스트 중 하나는 이미 깨져 있었지만 CI는 계속 통과했습니다.

## 문제 있어도 통과하는 테스트 보기

이 Playwright 테스트는 그럴듯해 보이지만 `Locator` 객체가 생성됐다는 사실만 증명합니다.

```typescript
import { expect, test } from '@playwright/test';

test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();
  expect(page.locator('.user-badge')).not.toBeNull();
});
```

유용한 테스트는 사용자에게 보이는 동작을 검증하고, 그 동작이 깨지면 실패해야 합니다.

```diff
- expect(page.getByText('Welcome back')).toBeDefined()
+ await expect(page.getByText('Welcome back')).toBeVisible()
```

포함된 스캐너는 프로젝트 설정 없이 문제 있어도 통과하는 검증문을 찾아냅니다.

```console
$ /bin/bash -p skills/e2e-reviewer/scripts/scan.sh tests/

[P0] #4f Locator always-true assertion (truthy/defined/not-null) (2 hits)
  tests/login.spec.ts:6:  expect(page.getByText('Welcome back')).toBeDefined();
  tests/login.spec.ts:8:  expect(page.locator('.user-badge')).not.toBeNull();

Summary: 2 total hit(s), 2 P0
```

## 설치하고 사용해 보기

### Claude Code

플러그인 마켓플레이스에서 설치합니다.

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

또는 검토된 버전으로 고정한 공통 설치 CLI로 네 스킬의 복사본을 설치합니다.

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

네 가지 스킬을 `~/.agents/skills/`에 설치합니다.

```bash
npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a codex
```

Codex가 작업을 나눠 맡길 때 `e2e-reviewer`, `playwright-debugger`, `cypress-debugger`는 네이티브 역할 또는 동등한 내장 대체 경로를 사용할 수 있습니다. `playwright-test-generator`에는 더 엄격한 V6 경계가 적용됩니다. 별도의 새 문맥 리뷰어가 없으면 `CANNOT_VERIFY`와 `PARTIAL/BLOCKED`를 보고합니다. 소스 체크아웃에는 `.codex/agents/` 아래 선택적 네이티브 에이전트도 포함되어 있습니다. 기여자는 패키징 경계를 [AGENTS.md](AGENTS.md)에서 확인할 수 있습니다.

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

특정 실행 환경 하나만 대상으로 설치하려면 `--all`을 `-a <agent>`로 바꿉니다. [supported agents](https://github.com/vercel-labs/skills#supported-agents)를 참고하세요. 이 명령들은 검토되지 않은 새 버전이 실행되지 않도록 검토된 CLI 릴리스를 고정합니다.

### Claude Code 수동 체크아웃

체크아웃은 `~/.claude/skills/` 밖에 두고, 공개 스킬 디렉터리 네 개를 각각 연결합니다.

```bash
git clone https://github.com/voidmatcha/e2e-skills.git "$HOME/.claude/e2e-skills"
mkdir -p "$HOME/.claude/skills"

for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
  ln -s "$HOME/.claude/e2e-skills/skills/$skill" "$HOME/.claude/skills/$skill"
done
```

링크는 같은 이름의 기존 스킬을 덮어쓰지 않고 실패합니다. Claude Code에서 `/skills`를 실행해 네 이름이 모두 표시되는지 확인합니다.

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
| 새 Playwright 테스트 보강 | `playwright-test-generator` | 탐색, 승인, 리뷰를 거친 Playwright 명세 |
| 통과 중인 Playwright/Cypress 테스트 리뷰 | `e2e-reviewer` | 구체적인 수정안이 포함된 검증된 P0/P1/P2 지적 |
| 실패한 Playwright 실행 디버깅 | `playwright-debugger` | F1–F15 근본 원인, 근거, 수정안 |
| 실패한 Cypress 실행 디버깅 | `cypress-debugger` | F1–F15 근본 원인, 근거, 수정안 |
| 결정적 로컬 스캔 실행 | `skills/e2e-reviewer/scripts/scan.sh` | 대상 프로젝트 패키지 없이 기계적 후보 산출 |

AI가 생성했거나 물려받은 E2E 테스트가 의도한 결과를 증명하지 못한 채 통과할 수 있을 때 이 묶음을 사용하세요. 애플리케이션과 실제 E2E 묶음 실행, 일반 린트 프리셋, 프레임워크 공통 테스트 도구를 대체하는 용도로는 쓰지 마세요. 지원 범위는 Playwright와 Cypress이며, 새 테스트 생성은 현재 Playwright만 대상으로 합니다.

## 리뷰 동작 방식

유효한 테스트 코드를 생성하는 일과 제품이 잘못됐을 때 실패하는 테스트를 생성하는 일은 다릅니다. 이 흐름은 기계적 탐지와 의미 판단을 분리합니다.

1. 스캐너는 Locator truthiness, focused test, 누락된 `await`, 포괄적 오류 억제처럼 결정적으로 잡을 수 있는 후보를 찾습니다.
2. `e2e-reviewer`는 지적을 확정하기 전에 테스트 이름, 동작, 검증문, 헬퍼, Page Object, fixture, 설정을 읽습니다.
3. 지적에는 안정적인 패턴 ID와 P0/P1/P2 심각도를 붙이므로 수정과 회귀를 비교 가능한 상태로 유지합니다.
4. 수정 후에는 이 흐름이 스캐너와 프로젝트에서 승인한 E2E 또는 린트 명령을 다시 실행합니다.

스캐너 일치는 후보일 뿐 최종 판정이 아닙니다. 인증 누락, 호출 근거 없는 낙관적 UI, 이름과 검증문 불일치, 렌더링 가드에 막힌 fixture처럼 여러 파일을 함께 봐야 하는 지적에는 의미 검토가 필요합니다.

## 근거와 한계

현재 근거가 뒷받침하는 주장은 제한적입니다. 이 프로젝트에는 동작으로 확인한 개발 근거와 실제 오픈소스 적용 사례가 있지만, 일반화된 리뷰 정확도를 주장하지는 않습니다.

- 브라우저 결함 주입은 **36/36 Playwright/Cypress cells**를 완료했습니다.
- 정밀 리뷰어 벤치마크는 **입증된 false-green case 12개와 clean guard 12개**를 다룹니다. 결함 사례 10개는 바이트 단위로 같은 연산자 변이입니다.
- 독립 견고성 게이트 v4, v5, v7, v8은 사전 등록 기준에 실패했습니다. V6와 v9은 실행하지 않았고, v10은 동결됐지만 실행하지 않았습니다.

점수, 실패한 게이트, 대체된 실행, 주장 범위는 [benchmark status](benchmarks/STATUS.md)를 참고하세요. [Research evidence ledger](docs/llm-generated-e2e-test-evidence.md)는 인접한 단위 테스트나 맞춤 에이전트 연구를 이 프로젝트의 측정값처럼 취급하지 않고 59개 외부 출처를 감사합니다.

## E2E 리뷰 목록

목록에는 안정적으로 유지되는 Playwright/Cypress 테스트 냄새 24개가 들어 있습니다. 가장 흔한 false-green 형태는 Locator truthiness, missing assertion, swallowed error, focused test, missing authentication, network proof 없는 optimistic UI check입니다. [전체 분류와 근거](docs/e2e-test-smells.md)를 참고하세요.

<details>
<summary>심각도별 24개 패턴 보기</summary>

### 24개 패턴 — 심각도별 분류

#### P0 — 반드시 수정 (문제가 있어도 통과)

기능이 깨져도 테스트가 통과합니다. 실제 검증이 일어나지 않습니다.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 1 | **Name-assertion mismatch** | Name은 "status"라고 하지만 `toBeVisible()`만 확인함 | Status content assertion을 추가하거나 실제 check와 맞게 이름 변경 |
| 2 | **Missing Then** | Cancel action 후 text restored 확인. 하지만 input은 여전히 visible? | Restored state와 dismissed state를 모두 검증 |
| 3 | **Error swallowing** | Spec의 `try/catch`, POM의 `.catch(() => {})` | Error가 실패로 이어지게 두고 POM method의 silent catch 제거 |
| 3b | **Cypress `uncaught:exception` suppression** | `cy.on('uncaught:exception', () => false)`가 app error를 blanket-swallow함 | Handler를 특정 known error로 scope하고 unknown error는 re-throw |
| 4 | **Vacuous or retry-weakening assertion** (P0/P1) | P0: invariant predicate와 Locator truthiness. P1: 약한 attachment proof, one-shot value/URL, zero-timeout retry/deadline hazard, 입증되지 않은 absence, 약속한 accessible name을 빠뜨린 ARIA snapshot | Meaningful bound와 web-first auto-retrying assertion 사용. Absence 전에 presence를 증명하고 약속한 accessible name을 load-bearing으로 유지 |
| 5 | **Bypass patterns** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`; comment 없는 `{ force: true }` | 항상 assert. Env check는 `beforeEach`로 이동. force:true에는 `// JUSTIFIED:` 추가 |
| 7 | **Focused test leak** | `test.only(...)`가 commit되어 CI가 test 하나만 실행하고 나머지를 조용히 skip | `.only` 삭제. Local focus에는 `--grep` 또는 `--spec` 사용 |
| 8 | **Missing assertion** | 버려진 locator/boolean이 scenario의 유일한 verification임 | `await expect(locator).toBeVisible()` 추가. 독립 verification/failure evidence가 이미 있으면 #8 skip |
| 12 | **Missing auth setup** | Login/`storageState`/auth fixture가 없어 protected-route spec이 login/wrong surface에도 맞는 generic assertion 때문에 통과 | `beforeEach` login 추가, `storageState` 설정, 또는 auth fixture 사용. 정상 auth-caused failure를 P0로 분류하지 않음 |

#### P1 — 수정 권장 (진단 품질 저하 / CI 시간 낭비)

테스트는 동작하지만 개발자를 오도하거나 CI 시간을 낭비하거나 미래 회귀를 유발할 수 있습니다.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 6 | **Raw DOM queries** | `evaluate()` 안의 `document.querySelector` | Framework locator/query API(`locator` / `cy.get`) 사용 |
| 9 | **Hard-coded sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | Framework auto-wait에 의존하고 condition-based wait 사용 |
| 10 | **Flaky test patterns** | Comment 없는 `items.nth(2)`, `test.describe.serial()`, scope 없는 accessible-name substring(10c), Cypress async callback, 할당된 `cy` command, 이어지는 action chain(10d-10f) | Stable/scoped locator와 self-contained test 사용. Cypress 작업은 command chain 안에 유지하고 Chainable을 value로 할당하지 않으며 action 후 다시 query |
| 13 | **Inconsistent POM usage** | POM을 import했지만 spec이 POM-owned action에 raw `page.fill`/`page.click` 사용 | 모든 interaction을 POM으로 route해 UI 변경을 한 곳에서 update |
| 14 | **Hardcoded credentials** | Test code의 `loginPage.login('demo-admin', '<literal-password>')` | `process.env.TEST_USER`, Playwright config secret, 또는 test data fixture 사용 |
| 15 | **Missing `await` on `expect()`** | Async Locator/Page web-first matcher Promise가 sequenced/observed되지 않음. Rejection은 보통 나중에 더 나쁜 attribution으로 드러남 | Matcher Promise를 `await`하거나 return. Sync value matcher는 제외 |
| 16 | **Missing `await` on action** | Actionability, action ordering, navigation이 이후 작업과 race할 수 있음. Rejection은 보통 나중에 더 나쁜 attribution으로 드러남 | Action Promise를 `await`하거나 return |
| 17 | **Discouraged direct Page selector API** | Selector 기반 `page.click`, `page.fill` 및 관련 Page action이 Locator layer를 건너뜀 | Composition, strictness, reuse, 더 명확한 failure를 위해 Locator action 사용 |
| 18 | **`expect.soft()` overuse** | Critical soft assertion이 hard scenario gate 전에 실행되어 prerequisite가 깨진 뒤에도 dependent work가 계속됨 | Primary state를 먼저 hard-gate. `soft`는 independent detail에만 사용 |
| 19 | **Module-level mutable state in test code** | Test utility의 column 0에 있는 `let testNotebookSequence = 0;`가 long-lived worker 전반에 남아 parallel worker 사이에서 충돌 | Counter 제거. `Date.now()` + `Math.random().toString(36).slice(2, 8)`에서 uniqueness를 만들거나 state를 `test.beforeEach`로 이동 |
| 20 | **Unmocked real-backend writes** | Signup/checkout spec이 controlled test boundary 없이 shared 또는 persistent state에 도달 | Write를 stub하거나 disposable container, rollback fixture, isolated tenant/database, 또는 동등한 controlled backend를 증명 |
| 22 | **Optimistic UI without call proof** | Like-toggle test가 `aria-pressed` flip을 assert함. UI가 optimistic update하면 POST가 삭제되어도 통과 | UI assertion을 `page.waitForRequest()`(click 전에 arm) 또는 route-hit flag와 pair |

#### P2 — 개선 권장 (유지보수성 / 견고성)

약하지만 틀린 것은 아닙니다. 리팩터링할 때 처리합니다.

| # | Pattern | Before | After |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | `clickEdit()`가 호출되지 않음. 정당화되지 않은 빈 wrapper class. 다른 spec과 전체가 중복됨 | Unused member와 zombie spec 삭제. Meaningless indirection을 분명히 줄일 때만 single-use helper inline |
| 21 | **Manually-captured session-file dependency** | Manual capture script로만 만들어지는 `storageState: 'auth/member.json'`. CI에는 없고 조용히 만료됨 | Session을 programmatically 재생성(API-login helper 또는 `setup` project). Manual file은 programmatic fallback이 있는 cache로만 사용 |
| 23 | **Fixture ignores render guards** | Liked-tab fixture가 `liked: false`를 seed함. Card component가 모든 item에서 `return null`하므로 빈 UI가 infra flake처럼 보임 | Seed 전에 item component의 early return/filter를 읽고, test 대상 view의 모든 guard를 통과하도록 field seed |

</details>

## 실패 디버깅

두 디버거는 같은 안정적 F1–F15 근본 원인 분류를 사용합니다. Playwright는 `playwright-report/`, HTML 보고서, `trace.zip`, 스크린샷, 범위가 정해진 GitHub Actions 산출물을 받습니다. Cypress는 mochawesome 또는 JUnit 보고서, 스크린샷, 영상, 범위가 정해진 CI 산출물을 받습니다.

<details>
<summary>F1–F15 taxonomy 보기</summary>

| # | Category | Signals |
|---|----------|---------|
| F1 | **Flaky / Timing** | `TimeoutError`, retry에서 통과 |
| F2 | **Selector Broken** | `locator not found`, strict mode violation |
| F3 | **Network Dependency** | `net::ERR_*`, unexpected API response |
| F4 | **Assertion Mismatch** | `Expected X to equal Y`, subject-inversion |
| F5 | **Missing Then** | Action은 완료됐지만 wrong state가 남음 |
| F6 | **Condition Branch Missing** | Element가 조건부로 존재하지만 assertion은 항상 실행 |
| F7 | **Test Isolation Failure** | 단독 실행은 통과, suite에서는 실패 |
| F8 | **Environment Mismatch** | CI vs local only; viewport, OS, timezone |
| F9 | **Data Dependency** | Missing seed data, hardcoded IDs |
| F10 | **Auth / Session** | Session expired, role-based UI not rendered |
| F11 | **Async Order Assumption** | `Promise.all` order, parallel race |
| F12 | **POM / Locator Drift** | DOM structure changed, POM not updated |
| F13 | **Error Swallowing** | `.catch(() => {})` hiding actual failure |
| F14 | **Animation Race** | Content가 아직 render되지 않았거나 transient element가 관찰 전에 제거됨 |
| F15 | **Hydration Race** | Action은 성공하지만 효과가 없음. SSR page가 아직 hydrated되지 않았고 다음 assertion에서 실패 |

</details>

디버거는 제품 회귀와 깨지기 쉬운 테스트를 구분해 분류하고 근거와 구체적인 수정안을 반환합니다. 실패한 Playwright 또는 Cypress 테스트 산출물 없이는 애플리케이션이나 백엔드를 진단하지 않습니다.

## 독립 실행 스캐너

결정적 기계 탐지 계층을 직접 실행합니다.

```bash
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

스캐너에는 Python 3와 PCRE2를 지원하는 `rg`가 필요합니다. 기본적으로 대상 프로젝트가 제어하는 ESLint 실행 파일, 플러그인, 파서, 설정을 실행하지 않으며 도구도 내려받지 않습니다. `E2E_SMELL_ALLOW_PROJECT_ESLINT=1`은 신뢰하는 체크아웃에서 프로젝트 ESLint 실행을 명시적으로 켭니다. `E2E_SMELL_NO_ESLINT_DOWNLOAD=0`과 `E2E_SMELL_NO_AST_GREP_DOWNLOAD=0`은 각각 고정 버전 다운로드를 명시적으로 켭니다. 이식성 확인에서 미리 설치된 호스트 실행 파일을 무시해야 할 때는 `E2E_SMELL_DISABLE_AST_GREP=1`을 설정합니다.

> **Read boundary.**
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->
> 공통 소스 범위는 요청한 path 아래입니다. 번들 lexical filter를 포함한 포함 검사는 그 소스를 보고합니다. 프레임워크 출처 확인은 포함 프로젝트의 다른 위치에 있는 relative fixture/support import도 읽을 수 있습니다.
> <!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:END -->

Tier 3는 포함된 대체 경로입니다. 선택적 ESLint와 ast-grep tier는 정밀도를 높이지만 의미 검토를 대체하지 않습니다. 스캐너는 인프라 또는 파일시스템 오류가 발생하면 문제가 없다는 잘못된 결과를 보고하지 않고 exit 2로 종료합니다. 신뢰와 네트워크 경계는 [SECURITY.md](SECURITY.md)를 참고하세요.

## ESLint 플러그인과의 차이

`eslint-plugin-playwright`와 `eslint-plugin-cypress`는 구문 규칙을 매 커밋마다 확인하기 위한 좋은 기본선입니다. `e2e-skills`는 여기에 두 가지 계층을 추가합니다.

- 명시적으로 켜지 않는 한 대상 프로젝트의 린트 스택을 실행하지 않는 보안 기본값 스캐너
- 테스트 의도나 여러 파일의 문맥이 필요한 지적을 위한 의미 검토

린터는 직접적인 Locator truthiness 검증문이나 missing `await`를 잡을 수 있습니다. 하지만 "shows a duplicate-name error"라는 테스트가 실제로 오류를 확인하는지, 보호된 라우트 테스트가 인증을 빠뜨렸는지, 낙관적 UI 검증문이 백엔드 요청 발생을 증명하는지는 판단할 수 없습니다. 지속적 린트에는 플러그인을 쓰고, 테스트 신뢰도 점검에는 `e2e-reviewer`를 사용하세요.

<a id="open-source-adoption"></a>

## 오픈소스 적용 사례

`e2e-reviewer`가 찾아낸 문제는 **14건의 업스트림 병합 PR**에 기여했습니다. 이 자체 선별 사례들은 실제 사용 사례를 보여주고 독자가 수정 내용을 확인할 수 있게 하지만, 대표 검증 표본이나 정확도 추정치는 아닙니다.

| Repository | PR | Pattern fixed |
| --- | --- | --- |
| Storybook | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Playwright assertion의 missing `await` |
| code-server | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | Focused test leak, matcher-less `expect`, discarded visibility read |
| Strapi | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | Discarded navigation/state check |
| SvelteKit | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | Floating Playwright assertion |
| Carbon Design System | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | Locator truthiness를 web-first assertion으로 교체 |
| Ghost | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise-valued disabled-state assertion |
| Cal.com | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | E2E flow의 weak assertion pattern |
| Bruno | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | Assertion과 wait reliability fix |
| Qwik | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/handle existence check |
| Element Web | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator null-check style assertion |
| MUI X | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | UI handle check를 state assertion으로 교체 |
| module-federation/core | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Cypress spec의 redundant blanket `uncaught:exception` suppression |
| FiftyOne | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Locator-defined check를 visible duplicate-name error assertion으로 교체 |
| Rancher Desktop | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `not.toBeNull()` locator check를 visible WSL integration-name assertion으로 교체 |

## 자주 묻는 질문

### 통과하지만 아무것도 테스트하지 않는 Playwright 또는 Cypress 테스트를 어떻게 찾나요?

<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->
`e2e-reviewer`는 안정적인 ID와 P0/P1/P2 심각도가 있는 목록 패턴 24개를 모두 리뷰합니다. 독립 실행 `scan.sh` 스캐너는 결정적으로 잡을 수 있는 기계적 부분집합만 다룹니다. 스캐너 일치는 후보일 뿐 최종 지적이 아닙니다. 이 스킬은 판정을 보고하기 전에 의도와 주변 코드를 확인합니다.

디버거는 안정적인 F1–F15 분류에 맞춰 실패를 분류합니다. 디버거와 생성기는 저장소를 신뢰하고 환경 변수와 플래그를 포함한 정확한 명령을 승인한 뒤에만 대상 프로젝트가 제어하는 코드를 실행합니다.

비공개 벤치마크 실행에서는 `--isolation-wrapper`가 필수 훅이지만 격리 증명은 아닙니다. 지속적 통합(CI)은 래퍼 계약을 검증하지만 파일시스템, 프로세스, 네트워크 격리를 증명하지 않습니다.
<!-- README-I18N-CONTRACT:CORE-SAFETY:END -->

관련 명세 디렉터리를 `e2e-reviewer`에 지정하세요. 지적을 반환하기 전에 결정적 후보와 의미 검토를 결합합니다.

### 이것이 Playwright 또는 Cypress 테스트 실행을 대체하나요?

아니요. 변경할 때마다 애플리케이션과 실제 E2E 묶음을 실행하세요. 이 묶음은 테스트 품질을 리뷰하고, Playwright 테스트를 보강하며, 기존 실패를 진단합니다. 테스트 실행기가 아닙니다.

### AI가 생성한 E2E 테스트는 어떻게 리뷰하나요?

병합하기 전에 생성된 명세를 `e2e-reviewer`에 지정하세요. 각 테스트가 이름에 적힌 사용자 동작을 실제로 증명하는지 확인하고, 결정적 스캐너 후보와 문맥 판단이 필요한 지적을 나눠 보고합니다.

### Playwright뿐 아니라 Cypress도 지원하나요?

리뷰와 실패 디버깅은 두 프레임워크를 모두 지원합니다. 새 테스트 생성은 현재 Playwright만 지원합니다. Cypress 디버거는 mochawesome과 JUnit 보고서를 받습니다.

### CI에서만 실패하는 테스트도 디버깅할 수 있나요?

예. 로컬 보고서 산출물이나 지원되는 GitHub Actions 실행을 제공하면 가능합니다. 디버거는 F1–F15 분류를 사용해 환경, 타이밍, 셀렉터, 데이터, 인증, 제품 회귀 원인을 분리합니다.

### 어떤 AI 코딩 에이전트가 지원되나요?

Claude Code, Codex, 그리고 `skills` CLI가 지원하는 55개 이상의 실행 환경은 공개 `SKILL.md` 계약을 불러올 수 있습니다. 선택적 실행 환경별 에이전트 파일은 사용할 수 있는 곳에서 작업 분담을 개선하지만, 공개 스킬은 그것 없이도 사용할 수 있습니다.

## 상세 문서

- [24 Playwright and Cypress E2E test smells](docs/e2e-test-smells.md)
- [Open-source case studies](docs/case-studies.md)
- [Benchmark status and negative results](benchmarks/STATUS.md)
- [External evidence ledger](docs/llm-generated-e2e-test-evidence.md)
- [Historical AI reviewer benchmark](docs/ai-reviewer-benchmark.md)
- [Debugger benchmark protocol](docs/debugger-benchmark/README.md)
- [Framework scope](docs/framework-scope.md)
- [Roadmap](docs/roadmap.md)

예정 작업에는 모델 간 관례 일관성과 더 강한 결정적 탐지가 포함됩니다. 전용 검증을 통과하기 전에는 어떤 로드맵 항목도 출시된 것으로 설명하지 않습니다.

## 기여

버그 보고, 오탐 방지 사례, 새 안티패턴, 번역 기여를 환영합니다. 설정과 검증 요구사항은 [CONTRIBUTING.md](CONTRIBUTING.md)에서 확인하세요. 에이전트 간 유지보수 계약은 [AGENTS.md](AGENTS.md)에 있습니다.

## 라이선스

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha). [LICENSE](LICENSE)를 참고하세요.
