<div align="center">
  <img src="docs/assets/hero.png" alt="e2e-skills — Playwright와 Cypress를 위한 Agent Skills: 신뢰할 수 있는 E2E 테스트를 생성, 리뷰, 디버깅합니다." width="100%" />
</div>

<p align="center">
  <a href="https://github.com/voidmatcha/e2e-skills"><img alt="Agent Skills" src="https://img.shields.io/badge/Agent_Skills-4-1FC07C?style=flat-square&labelColor=black"></a>
  <a href="https://claude.com/product/claude-code"><img alt="Claude Code" src="https://img.shields.io/badge/Claude_Code-compatible-D97757?style=flat-square&labelColor=black&logo=anthropic&logoColor=white"></a>
  <a href="https://github.com/openai/codex"><img alt="Codex" src="https://img.shields.io/badge/Codex-compatible-412991?style=flat-square&labelColor=black&logo=openai&logoColor=white"></a>
  <a href="https://playwright.dev"><img alt="Playwright | Cypress" src="https://img.shields.io/badge/Playwright_%7C_Cypress-supported-2EAD33?style=flat-square&labelColor=black&logo=playwright&logoColor=white"></a>
  <a href="#오픈소스에서-검증됨"><img alt="Merged PRs" src="https://img.shields.io/badge/merged_PRs-14-1FC07C?style=flat-square&labelColor=black&logo=github"></a>
  <a href="https://agents.md"><img alt="Runs in 55+ agents" src="https://img.shields.io/badge/runs_in-55%2B_agents-37B0E6?style=flat-square&labelColor=black"></a>
  <a href="https://www.npmjs.com/package/eslint-plugin-playwright-silent-pass"><img alt="playwright silent-pass npm" src="https://img.shields.io/npm/v/eslint-plugin-playwright-silent-pass?style=flat-square&label=playwright%20lint&labelColor=black&color=1FC07C"></a>
  <a href="https://www.npmjs.com/package/eslint-plugin-cypress-silent-pass"><img alt="cypress silent-pass npm" src="https://img.shields.io/npm/v/eslint-plugin-cypress-silent-pass?style=flat-square&label=cypress%20lint&labelColor=black&color=37B0E6"></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/github/license/voidmatcha/e2e-skills?style=flat-square&labelColor=black&color=37B0E6"></a>
</p>

<p align="center">
<a href="README.md">🇺🇸 English</a> | <strong>🇰🇷 한국어</strong> | <a href="README.ja.md">🇯🇵 日本語</a> | <a href="README.zh-cn.md">🇨🇳 简体中文</a>
</p>

CI는 통과하지만 실제로는 거의 아무것도 증명하지 못하는 Playwright/Cypress E2E 테스트를 찾아냅니다.

**이론에만 머무는 이야기가 아닙니다. `e2e-reviewer`가 찾아낸 문제는 SvelteKit, Storybook, code-server, Strapi, Carbon Design System, Ghost, MUI X 같은 실제 저장소에서 [14건의 merge된 upstream PR](#오픈소스에서-검증됨)로 이어졌습니다.**

> 그중 하나가 code-server(78k&#9733;)였습니다. `it.only` 하나가 7개월 동안 8개의 테스트를 조용히 비활성화하고 있었고, 그중 하나는 이미 깨져 있었습니다. 그동안 CI는 내내 조용히 통과하고 있었습니다.

`e2e-skills`는 실패해야 할 E2E 테스트가 조용히 통과하는 유형을 잡기 위한 Agent Skill 묶음과 재현 가능한 스캐너입니다. 약한 assertion, 누락된 `await`, 버려진 대기/읽기, 조건문으로 감싼 assertion, focused test, 광범위한 오류 억제 같은 문제를 다룹니다.

테스트 runner도, 광범위한 lint preset도, 범용 브라우저 자동화 도구도 아닙니다. 초점은 한 가지 질문입니다:

> 사용자에게 보이는 동작이 실제로 깨졌을 때 이 E2E 테스트가 실패하는가?

## 만든 이유

AI 에이전트는 E2E 테스트를 금방 만들어 냅니다. 문제는 그렇게 나온 테스트가 사용자에게 보이는 상태 대신 handle, Promise, 일회성 snapshot을 검사하면서도 겉보기에는 그럴듯하다는 점입니다.

```diff
- expect(page.getByText('SWE')).toBeDefined()
+ await expect(page.getByText('SWE')).toBeVisible()
```

첫 줄은 Playwright `Locator` 객체가 있다는 사실만 증명합니다. 두 번째 줄이어야 사용자가 그 텍스트를 실제로 본다는 점까지 검증합니다.

생성형 테스트의 문제가 silent-pass만은 아닙니다. 모델은 YAGNI, KISS 같은 원칙을 무시하고 아무 데서도 쓰지 않는 코드를 만들어 내기도 합니다. 어떤 테스트도 호출하지 않는 메서드로 가득한 Page Object가 대표적입니다. 여러 모델이 한 suite에 테스트를 쓰면 스타일이 제각각이 되는 문제도 있습니다. 이 묶음은 그 일을 나눠 맡습니다: 쓰이지 않는 추상화는 리뷰어가 #11(YAGNI + 좀비 spec)로 잡아내고, generator는 첫 실행에서 프로젝트 컨벤션(`AGENTS.md` E2E 섹션 + seed spec)을 읽어 들여, 이후 어떤 모델이 와도 같은 스타일로 쓰게 합니다. 더 깊은 자동 추론 버전은 [로드맵](#로드맵)에 있습니다.

`e2e-skills`는 이 문제를 반복 가능한 리뷰 흐름으로 바꿉니다:

1. silent-pass smell을 항상 같은 방식으로 스캔하고,
2. 모호한 E2E 의도를 Agent Skill로 리뷰하고,
3. 빠진 flow가 있으면 더 나은 Playwright coverage를 생성하고,
4. 실패한 Playwright/Cypress 리포트를 디버깅해 근본 원인부터 고칩니다.

## 실제 동작 예시

CI는 통과하지만 실제로는 아무것도 검사하지 않는 Playwright 테스트입니다. `Locator`는 절대 undefined가 되지 않으므로, 요소가 렌더링되지 않아도 `.not.toBeNull()`은 통과합니다:

```ts
test('shows the welcome message', async ({ page }) => {
  await page.goto('/dashboard');
  expect(page.getByText('Welcome back')).toBeDefined();   // always passes
  expect(page.locator('.user-badge')).not.toBeNull();     // always passes
});
```

스캐너는 별도 설정 없이 두 건 모두 항상 같은 방식으로 잡아냅니다:

```console
$ bash skills/e2e-reviewer/scripts/scan.sh tests/

[P0] #4f Locator always-true assertion (truthy/defined/not-null) (2 hits)
  tests/login.spec.ts:6:  expect(page.getByText('Welcome back')).toBeDefined();
  tests/login.spec.ts:8:  expect(page.locator('.user-badge')).not.toBeNull();

Summary: 2 total hit(s), 2 P0
```

## 한눈에 보기

| 필요한 것 | 사용할 것 |
| --- | --- |
| 새 Playwright E2E coverage 생성 | [`playwright-test-generator`](#skill-1-playwright-test-generator--테스트-생성) |
| 기존 Playwright/Cypress 테스트의 silent-pass smell 리뷰 | [`e2e-reviewer`](#skill-2-e2e-reviewer--품질-리뷰) |
| 실패한 Playwright 리포트 디버깅 | [`playwright-debugger`](#skill-3-playwright-debugger--playwright-실패-debugger) |
| 실패한 Cypress 리포트 디버깅 | [`cypress-debugger`](#skill-4-cypress-debugger--cypress-실패-debugger) |
| deterministic 로컬 스캔 실행 | [`skills/e2e-reviewer/scripts/scan.sh`](#독립-실행형-스캐너) |

유용한 문서: [case study](docs/case-studies.md), [로드맵](docs/roadmap.md), [24개 smell 분류 체계](docs/e2e-test-smells.md), [프레임워크 범위](docs/framework-scope.md), [AI reviewer benchmark](docs/ai-reviewer-benchmark.md).

## 설치

설치 방법은 호스트에 따라 다릅니다: [Claude Code](#claude-code) · [Codex](#codex) · [그 외 모든 에이전트](#그-외-모든-에이전트-cursor-opencode-gemini-cli-등) · [수동 clone](#수동-clone-claude-code)

### Claude Code

plugin marketplace:

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

또는 cross-agent `skills` CLI로:

```bash
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code
```

### Codex

Codex에서는 `skills` CLI 설치를 권장합니다. 이 명령은 번들을 `~/.agents/skills/`에 설치합니다. Codex는 거기서 skill을 찾아 쓰고, 인터페이스 블록은 `.codex-plugin/plugin.json`에서 읽습니다:

```bash
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code -a codex
```

Codex plugin marketplace를 써도 됩니다:

```text
codex plugin marketplace add voidmatcha/e2e-skills
codex plugin add e2e-skills@voidmatcha
```

### 그 외 모든 에이전트 (Cursor, OpenCode, Gemini CLI 등)

크로스 에이전트 `skills` CLI가 55개 이상의 호스트를 지원합니다. 명령 하나면 지원되는 모든 에이전트에 전역으로 설치됩니다:

```bash
npx skills add voidmatcha/e2e-skills -g --all
```

특정 에이전트만 대상으로 하려면 `--all` 대신 `-a <agent>`를 쓰세요. 예를 들어 `-a cursor`, `-a opencode`, `-a gemini-cli`처럼 지정할 수 있습니다. [지원 에이전트 목록](https://github.com/vercel-labs/skills#supported-agents)을 참고하세요.

### 수동 clone (Claude Code)

```bash
git clone https://github.com/voidmatcha/e2e-skills.git ~/.claude/skills/e2e-skills
```

## 사용해 보기

```text
Review my Playwright tests in tests/e2e with e2e-reviewer.
```

```text
Generate Playwright E2E coverage for apps/web/e2e.
```

```text
Debug the failed Playwright report in playwright-report/.
```

## 빠른 적합성 판단

다음과 같을 때 `e2e-skills`를 사용하세요:

- Playwright/Cypress 테스트가 통과하고는 있지만, 실제 사용자에게 보이는 상태를 검증하는지 확신이 없을 때.
- AI가 생성한 E2E 테스트에 merge 전 품질 게이트가 필요할 때.
- 테스트 suite에 `locator().toBeTruthy()`, `not.toBeNull()`, `await` 없는 `expect(...)`, 버려진 `isVisible()`, `waitForTimeout()`, `it.only`, 전역 `uncaught:exception` 억제 같은 의심스러운 패턴이 들어 있을 때.
- 문법만이 아니라 테스트의 의도까지 에이전트가 리뷰해 주기를 원할 때.

다음 용도로는 사용하지 마세요:

- 애플리케이션과 실제 E2E suite 실행을 대체하는 수단,
- 범용 lint preset,
- 모든 flaky 테스트를 고쳐 준다는 약속,
- 프레임워크에 구애받지 않는 테스트 도구. 지원 범위는 Playwright와 Cypress입니다.

## 오픈소스에서 검증됨

일부러 꾸며 낸 증거가 아닙니다. `e2e-reviewer`가 찾아낸 문제를 바탕으로 SvelteKit, Storybook, code-server, Strapi, Carbon Design System, Ghost, Cal.com, Bruno, Qwik, Element Web, MUI X, Rancher Desktop 같은 잘 알려진 저장소에서 **14건의 upstream PR**이 merge됐습니다.

그 실전 기록은 재현 가능한 pilot benchmark와도 연결됩니다. 이미 AI reviewer가 검토한 오픈소스 PR 100건, 77개 저장소에서 neutral LLM judge가 실질적인 E2E test-trust issue 110개를 식별했고, `e2e-reviewer`는 그중 78개를 false positive 없이 찾았습니다. lint는 45개, general AI PR reviewer의 inline spec comment는 10개를 찾았습니다. [방법론과 사례 근거](docs/ai-reviewer-benchmark.md)를 참고하세요.

merge된 수정 전체:

| 저장소 | PR | 수정된 패턴 |
| --- | --- | --- |
| Storybook | [storybookjs/storybook#34141](https://github.com/storybookjs/storybook/pull/34141) | Playwright assertion의 `await` 누락 |
| code-server | [coder/code-server#7845](https://github.com/coder/code-server/pull/7845) | focused test 유출, matcher 없는 `expect`, 버려진 가시성 읽기 |
| Strapi | [strapi/strapi#26630](https://github.com/strapi/strapi/pull/26630) | 버려진 내비게이션/상태 검사 |
| SvelteKit | [sveltejs/kit#16068](https://github.com/sveltejs/kit/pull/16068) | 떠 있는(floating) Playwright assertion |
| Carbon Design System | [carbon-design-system/carbon#22564](https://github.com/carbon-design-system/carbon/pull/22564) | Locator truthy 검사를 web-first assertion으로 교체 |
| Ghost | [TryGhost/Ghost#28712](https://github.com/TryGhost/Ghost/pull/28712) | Promise 값을 그대로 검사하는 disabled 상태 assertion |
| Cal.com | [calcom/cal.diy#28486](https://github.com/calcom/cal.diy/pull/28486) | E2E flow의 약한 assertion 패턴 |
| Bruno | [usebruno/bruno#8317](https://github.com/usebruno/bruno/pull/8317) | assertion 및 대기 안정성 수정 |
| Qwik | [QwikDev/qwik#8777](https://github.com/QwikDev/qwik/pull/8777) | Locator/handle 존재 여부 검사 |
| Element Web | [element-hq/element-web#32801](https://github.com/element-hq/element-web/pull/32801) | Locator null 검사 방식의 assertion |
| MUI X | [mui/mui-x#22982](https://github.com/mui/mui-x/pull/22982) | UI handle 검사를 상태 assertion으로 교체 |
| module-federation/core | [module-federation/core#4826](https://github.com/module-federation/core/pull/4826) | Cypress spec의 불필요한 블랭킷 `uncaught:exception` 억제 제거 |
| FiftyOne | [voxel51/fiftyone#7851](https://github.com/voxel51/fiftyone/pull/7851) | Locator 정의 여부 대신 눈에 보이는 중복 이름 오류를 검증 |
| Rancher Desktop | [rancher-sandbox/rancher-desktop#10557](https://github.com/rancher-sandbox/rancher-desktop/pull/10557) | `not.toBeNull()` locator 검사를 눈에 보이는 WSL 통합 이름 assertion으로 교체 |

## workflow

```text
1. Ask e2e-reviewer to inspect the target test directory.
2. Confirm P0 findings first: these are silent-pass or always-green risks.
3. Patch one smell family at a time.
4. Re-run the deterministic scanner and the target E2E/lint checks.
5. Use playwright-debugger or cypress-debugger only for real failed reports.
```

리뷰어 출력 예시:

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

## 독립 실행형 스캐너

```bash
./skills/e2e-reviewer/scripts/scan.sh path/to/tests
```

스캐너는 의도적으로 deterministic입니다. 확실하게 잡을 수 있는 것부터 먼저 잡고, 스캐너 발견 주변의 의도까지 읽어야 하는 리뷰는 Agent Skill이 맡습니다.

> **네트워크 동작.** 스캐너는 지정한 파일만 읽으며 아무것도 업로드하지 않습니다. 정밀 계층에서는 프로젝트 로컬 lint 도구를 우선 사용하고, 없으면 버전이 고정된 공개 패키지(`eslint`, `eslint-plugin-playwright`/`-cypress`, `ast-grep`)를 `npx`로 자동 다운로드합니다. 완전히 오프라인으로 실행하려면 `E2E_SMELL_NO_ESLINT_DOWNLOAD=1`과 `E2E_SMELL_NO_AST_GREP_DOWNLOAD=1`을 설정하세요. 전체 공개 내역: [SECURITY.md](./SECURITY.md).

## Skill 1: `playwright-test-generator` — 테스트 생성

어떤 프로젝트에서든 Playwright E2E 테스트를 처음부터 만듭니다. 먼저 coverage gap을 분석한 뒤 브라우저 자동화 도구(Playwright MCP / webapp-testing)로 실제 앱을 탐색하고, 사용자의 승인을 받아 시나리오를 설계합니다. 생성된 테스트는 `e2e-reviewer`가 자동으로 리뷰합니다.

> **권장:** 먼저 브라우저 도구를 설정하세요: [Playwright MCP](https://github.com/microsoft/playwright-mcp#getting-started) 또는 `webapp-testing` 스킬. 없으면 페이지 초기 상태만 보는 정적 ARIA 스냅샷으로 대체합니다(상호작용 불가). 단순 페이지에는 괜찮지만 실제 흐름(모달, 제출 후, 에러 상태, 다단계)에는 제한적입니다.

### 사용 시점

- E2E coverage가 없는 페이지나 기능이 있을 때
- 기존 앱의 test suite를 bootstrap하고 싶을 때
- 릴리스 전에 빠르게 테스트를 추가해야 할 때

### 사용법

```
Generate playwright tests
Generate playwright tests for the login page
Write e2e tests for the settings page
Add playwright coverage for checkout flow
```

### 파이프라인

1. **환경 감지** — 설정, baseURL, 테스트 디렉터리, POM 구조, 기존 컨벤션 문서
2. **coverage gap 분석** — 사용자가 대상을 선택합니다(대상이 인수로 주어지면 생략)
3. **라이브 브라우저 탐색** — 브라우저 자동화 도구([Playwright MCP](https://github.com/microsoft/playwright-mcp#getting-started) / webapp-testing)로 실제 화면을 확인합니다. 환각으로 셀렉터를 지어내지 않고, 레이블 없는 입력은 accessible name까지 직접 확인합니다.
4. **시나리오 설계 + 승인 게이트** — 코드를 작성하기 전에 계획과 locator 표를 보여 줍니다
5. **코드 생성** — 프로젝트 컨벤션에서 자동 감지한 POM + spec 또는 플랫 spec; 쓰기 작업은 반드시 route 스텁 처리(`code-rules.md`의 Network Determinism 참고)
6. **컨벤션 및 시드 스캐폴딩**(프로젝트 첫 실행 시) — 프로젝트에 맞춘 E2E 섹션을 `AGENTS.md`에 추가하고 시드 spec을 지정해, 이후 AI가 생성하는 테스트(Claude Code, Codex, Playwright Agents)가 일관성을 유지하게 합니다
7. **YAGNI 감사 + e2e-reviewer** — 사용되지 않는 locator를 제거하고 첫 실행 전에 P0 이슈를 잡아냅니다
8. **TS 컴파일 + 테스트 실행** — 실패 시 3회 자동 수정 시도(의도 기반 locator 재해석), 이후 `playwright-debugger`에 인계

---

## Skill 2: `e2e-reviewer` — 품질 리뷰

CI는 통과하지만 실제 회귀를 잡지 못하는 E2E 테스트를 찾아냅니다.

모든 발견 항목은 보고 전에 refute-first 방식으로 반증 검증을 거칩니다. Claude Code 플러그인 설치에서는 read-only 서브에이전트가 검증하고, 그 외 호스트에서는 inline으로 검증합니다. 이 별도 검증 단계 덕분에 벤치마크에서 false positive를 0으로 유지했습니다.

### 사용 시점

- 테스트는 항상 통과하는데 버그가 계속 프로덕션으로 새어 나갈 때
- 테스트가 CI는 통과하지만 실제 회귀를 놓치는 것으로 의심될 때
- test suite가 취약해 UI가 바뀔 때마다 테스트가 깨질 때
- 릴리스나 코드 리뷰 전에 테스트 품질을 감사하고 싶을 때
- Playwright 또는 Cypress spec을 리뷰하고 있을 때

### 사용법

```
Review my E2E tests
Audit the spec files in tests/
Find weak tests in my test suite
My tests always pass but miss bugs
Tests pass CI but miss regressions
My tests are fragile and break on every UI change
We have coverage but bugs still slip through
```

### 감지하는 24개 패턴 — 심각도별 분류

#### P0 — 반드시 수정 (조용한 상시 통과)

기능이 깨져도 테스트가 통과합니다. 실제 검증이 전혀 일어나지 않습니다.

| # | 패턴 | 수정 전 | 수정 후 |
|---|---------|--------|-------|
| 1 | **Name-assertion mismatch** | 이름은 "status"라고 말하는데 `toBeVisible()`만 검사 | status 내용에 대한 assertion을 추가하거나, 실제 검사에 맞게 이름 변경 |
| 2 | **Missing Then** | 취소 동작 후 텍스트 복원을 검증 — 그런데 입력창이 여전히 보인다면? | 복원된 상태와 닫힌 상태를 모두 검증 |
| 3 | **Error swallowing** | spec 안의 `try/catch`, POM 안의 `.catch(() => {})` | 오류가 실패로 이어지게 두고, POM 메서드에서 조용한 catch 제거 |
| 3b | **Cypress `uncaught:exception` suppression** | `cy.on('uncaught:exception', () => false)`가 앱 오류를 통째로 삼킴 | 핸들러를 특정 알려진 오류로 한정하고, 알 수 없는 오류는 다시 던지기 |
| 4 | **Always-passing assertion** | `toBeGreaterThanOrEqual(0)`; 주석 없는 `toBeAttached()`; `expect(await el.isVisible()).toBe(true)` (일회성); `expect(await el.textContent()).toBe(x)` (일회성); `expect(locator).toBeTruthy()` (Locator는 항상 truthy); assertion의 `{ timeout: 0 }` (재시도 비활성화) | `toBeGreaterThan(0)`; `toBeVisible()`; 자동 재시도가 있는 web-first assertion |
| 5 | **우회 패턴** (5a P0, 5b P1) | `if (await el.isVisible()) { expect(...) }`; 주석 없는 `{ force: true }` | 항상 assertion 수행; 환경 검사는 `beforeEach`로 이동; force:true에는 `// JUSTIFIED:` 추가 |
| 7 | **Focused test leak** | `test.only(...)`가 커밋됨 — CI가 테스트 하나만 실행하고 나머지를 조용히 건너뜀 | `.only` 삭제; 로컬 포커스에는 `--grep`이나 `--spec` 사용 |
| 8 | **Missing assertion** | `await page.locator('.x');` (버려짐); `await el.isVisible();` (boolean을 버림) | `await expect(locator).toBeVisible()` 추가 또는 해당 줄 삭제 |
| 12 | **Missing auth setup** | 보호된 route의 spec이 로그인/`storageState`/인증 fixture 없이 `/dashboard`로 이동 | `beforeEach` 로그인 추가, `storageState` 설정, 또는 인증 fixture 사용 — 그러지 않으면 로그인 페이지를 상대로 테스트가 통과함 |
| 15 | **Missing `await` on `expect()`** | `expect(page.locator('.toast')).toBeVisible()`가 관찰되지 않는 Promise를 반환 | assertion이 실제로 실행되도록 `await` 추가 |
| 16 | **Missing `await` on action** | `page.locator('#submit').click()`이 다음 줄 전에 실행되지 않을 수 있음 | 액션이 완료되도록 `await` 추가 |

#### P1 — 수정 권장 (진단 품질 저하 / CI 시간 낭비)

테스트 자체는 돌아가지만 개발자를 엉뚱한 방향으로 이끌거나, CI 시간을 잡아먹거나, 나중에 터질 회귀의 씨앗을 심어 둡니다.

| # | 패턴 | 수정 전 | 수정 후 |
|---|---------|--------|-------|
| 6 | **Raw DOM queries** | `evaluate()` 안의 `document.querySelector` | 프레임워크의 locator/쿼리 API 사용 (`locator` / `cy.get`) |
| 9 | **Hard-coded sleep** | `waitForTimeout(2000)` / `cy.wait(2000)` / `waitForLoadState('networkidle')` | 프레임워크의 자동 대기에 의존; 조건 기반 대기 사용 |
| 10 | **Flaky test patterns** | 주석 없는 `items.nth(2)`; `test.describe.serial()` | `data-testid`나 role 셀렉터 사용; serial을 자기 완결적 테스트로 교체 |
| 13 | **Inconsistent POM usage** | POM을 임포트해 놓고 POM 소관 동작에 원시 `page.fill`/`page.click` 사용 | 모든 상호작용을 POM으로 거치게 해 UI 변경이 한 곳에서 반영되게 함 |
| 14 | **Hardcoded credentials** | 테스트 코드 안의 `loginPage.login('demo-admin', '<literal-password>')` | `process.env.TEST_USER`, Playwright 설정의 secret, 또는 테스트 데이터 fixture 사용 |
| 17 | **Direct `page.click(selector)` API** | `page.click('#submit')` / `page.fill('#input', 'text')`는 Locator 계층을 건너뜀 | 자동 대기와 더 나은 오류 메시지를 위해 `page.locator(selector).click()` 사용 |
| 18 | **`expect.soft()` overuse** | 테스트의 모든 assertion이 `expect.soft()` — 테스트가 조기에 실패하지 않음 | 테스트마다 최소 하나의 hard `expect()`가 게이트 역할을 하게 함; `soft`는 독립적인 세부 사항에만 사용 |
| 19 | **Module-level mutable state in test code** | 테스트 유틸리티의 0번째 열에 있는 `let testNotebookSequence = 0;` — 병렬 워커 간에 충돌하고 재시도 후에도 살아남음 | 카운터 제거; `Date.now()` + `Math.random().toString(36).slice(2, 8)`로 고유값 도출, 또는 상태를 `test.beforeEach`로 이동 |
| 20 | **Unmocked real-backend writes** | 가입/결제 spec이 실제 뮤테이션을 전송 — CI가 실행될 때마다 실제 계정/주문이 생성됨 | 쓰기/자격 증명 엔드포인트를 `page.route()` / `cy.intercept()`로 스텁; 실제 백엔드 스모크 spec은 지정된 하나까지만 |
| 22 | **Optimistic UI without call proof** | 좋아요 토글 테스트가 `aria-pressed` 전환만 검증 — UI가 낙관적으로 갱신되므로 POST를 지워도 통과 | UI assertion에 `page.waitForRequest()`(클릭 전에 준비) 또는 route 히트 플래그를 짝지어 사용 |

#### P2 — 고치면 좋음 (유지보수 / 견고성)

약한 assertion이지만 틀린 assertion은 아닙니다. 리팩터링할 때 처리하면 됩니다.

| # | 패턴 | 수정 전 | 수정 후 |
|---|---------|--------|-------|
| 11 | **YAGNI + Zombie Specs** | 한 번도 호출되지 않는 `clickEdit()`; 빈 래퍼 클래스; 한 곳에서만 쓰이는 Util; 다른 spec과 통째로 중복된 spec | 사용되지 않는 멤버 삭제; 단일 사용 Util 메서드는 인라인; 좀비 spec 파일 삭제 |
| 21 | **Manually-captured session-file dependency** | 수동 캡처 스크립트로만 만들어지는 `storageState: 'auth/member.json'` — CI에는 없고 조용히 만료됨 | 세션을 프로그래밍 방식으로 재생성(API 로그인 헬퍼 또는 `setup` 프로젝트); 수동 파일은 프로그래밍 방식 폴백이 있는 캐시로만 사용 |
| 23 | **Fixture ignores render guards** | 좋아요 탭 fixture가 `liked: false`를 시드; 카드 컴포넌트가 모든 항목에 `return null` — 빈 UI가 인프라 문제처럼 보임 | 시드하기 전에 항목 컴포넌트의 조기 return/필터를 읽고, 대상 뷰의 모든 가드를 통과하도록 필드를 시드 |

### linter가 구조적으로 잡을 수 없는 것

**linter는 assertion이 형식적으로 올바른지 검사합니다. 테스트가 그 이름이 주장하는 바를 증명하는지는 검사할 수 없습니다.** `e2e-reviewer`가 보는 핵심은 테스트의 명시된 의도와 실제 검증 내용 사이의 간극입니다. 이 간극은 파일 단위 AST나 grep 규칙에는 보이지 않습니다. 예를 들어 `should show an error when the name is duplicate`는 오류를 전혀 확인하지 않는 assertion으로도 통과할 수 있고, 문법에도 문제는 없습니다. 이를 판별하려면 테스트 이름, 수행 동작, 주변 코드를 함께 읽어야 합니다. 단일 파일 규칙보다 한 단계 위의 판단입니다.

`e2e-reviewer`는 첫 번째 계층으로 `eslint-plugin-playwright` / `eslint-plugin-cypress`를 실행합니다. 따라서 기계적인 규칙(`#6`, `#7`, `#9`, `#15`, `#16`, `#5a`, `#5b`)은 사실상 표준인 이 plugin들이 이미 담당합니다. 항상 통과하는 Locator assertion smell(`#4f`)도 이제 담당됩니다 — 이 프로젝트에서 공식 `eslint-plugin-playwright`에 [`no-unnecessary-assertions`](https://github.com/mskelton/eslint-plugin-playwright/pull/470) 규칙으로 기여해 merge됐고(다음 릴리스에 포함), Cypress 쪽은 [`eslint-plugin-cypress-silent-pass`](https://github.com/voidmatcha/eslint-plugin-cypress-silent-pass)가 담당합니다. 그 위에 `e2e-reviewer`를 얹는 이유는 **어떤 AST나 grep 규칙도 닿을 수 없는** smell 때문입니다. 이런 smell을 확정하려면 규칙이 보지 못하는 코드, 즉 다른 함수, 컴포넌트, CI 설정, 테스트 자체의 의도까지 읽어야 합니다:

| smell | lint가 판별할 수 없는 이유 |
|-------|---------------------------|
| `#1` 이름-assertion 불일치 | 테스트의 *이름/의도*와 실제 assertion 내용을 비교해야 합니다. 문법적으로는 assertion에 아무 문제가 없습니다. |
| `#3` / `#3b` error swallowing 및 광범위한 `cy.on('uncaught:exception', () => false)` | 문법은 유효합니다. 의도를 봐야만 실패를 비활성화한다는 것이 드러납니다. 단일 줄 정규식은 한 suite에서 **여러 줄에 걸친 51개 인스턴스**를 놓쳤습니다. |
| `#4f` Locator를 truthy로 검사 (`expect(locator).toBeTruthy()` / `.toBeDefined()` / `.not.toBeNull()`) | 평범한 assertion처럼 읽힙니다. Locator가 결코 falsy가 아니라는 것을 *알아야만* 항상 통과함이 보입니다. |
| `#4` 일회성 읽기 (`expect(await el.isVisible()).toBe(true)`) | 유효한 `expect`입니다. 재시도 없는 특정 시점 읽기라는 것을 알아야만 안티패턴으로 표시할 수 있습니다. |
| `#12` 인증 설정 누락 | route가 미인증 상태임을 알려면 설정, fixture, `storageState`에 걸친 파일 간 추론이 필요합니다. |
| `#20` / `#22` 모킹 없는 쓰기 / 호출 증거 없는 낙관적 UI | 엔드포인트가 뮤테이션을 수행한다는 것, 또는 UI가 네트워크 assertion 없이 낙관적으로 갱신된다는 것을 알아야 합니다. |
| `#11` / `#23` 좀비 spec / 렌더 가드를 무시하는 fixture | 파일 간 문제입니다: 중복 spec 탐지, 또는 시드를 신뢰하기 전에 컴포넌트의 조기 `return null`을 읽는 일. |
| **어려운 사례** | *결코 throw하지 않는* 함수를 감싼 `try/catch`가 `catch` 안에서만 assertion을 수행하는 경우(실제 사례: xyflow의 `graph-utils.cy.ts`에 있는 `addEdge`). 확정하려면 다른 파일에 있는 함수 본문을 읽어야 하는데, 이는 grep이나 어떤 단일 파일 AST 규칙으로도 불가능합니다. |

이 부분은 패턴 매칭이 아니라 판단이 필요한 영역입니다. `e2e-reviewer`는 후보를 발견 항목으로 보고하기 전에 주변 코드와 CI 설정을 읽어 **검증**합니다. 위에서 말한 [후보이지 판결이 아니라는](#scanner-findings-are-candidates-not-verdicts) 원칙 그대로입니다. 모든 발견 항목에 단순 매치 결과가 아니라 임시방편을 경계한 수정 제안이 딸려 나오는 것도 이 검증 덕분입니다.

### 참고 자료

[Playwright 모범 사례](https://playwright.dev/docs/best-practices) · [Cypress 모범 사례](https://docs.cypress.io/app/core-concepts/best-practices) · [Testing Library 기본 원칙](https://testing-library.com/docs/guiding-principles)

---

## Skill 3: `playwright-debugger` — Playwright 실패 debugger

`playwright-report/` 디렉터리를 읽어 Playwright 테스트 실패를 진단합니다. 실패가 로컬에서 났든 CI에서 났든 상관없습니다. 근본 원인을 분류하고 구체적인 수정안을 제시합니다.

### 사용 시점

- 파악해야 할 실패가 담긴 `playwright-report/` 디렉터리(로컬 또는 CI에서 다운로드)가 있을 때
- 테스트가 로컬에서는 통과하는데 CI에서는 실패할 때
- flaky하거나 간헐적인 테스트 실패를 겪고 있을 때
- 명확한 원인 없이 `TimeoutError`나 `locator not found`가 발생할 때

### 사용법

```
Debug these failing tests
Why did these tests fail?
Tests pass locally but fail in CI
```

> **참고:** 리포트는 로컬 경로로 넘겨도 되고, GitHub Actions run을 그대로 줘도 됩니다. 스킬은 사용자가 확인한 run ID로 `gh run download`를 실행해 아티팩트를 직접 내려받습니다. forked PR run은 제외합니다.

### 15개 근본 원인 카테고리

| # | 카테고리 | 신호 |
|---|----------|---------|
| F1 | **Flaky / Timing** | `TimeoutError`, 재시도 시 통과 |
| F2 | **Selector Broken** | `locator not found`, strict mode 위반 |
| F3 | **Network Dependency** | `net::ERR_*`, 예기치 않은 API 응답 |
| F4 | **Assertion Mismatch** | `Expected X to equal Y`, 주체 역전(subject-inversion) |
| F5 | **Missing Then** | 액션은 완료됐지만 잘못된 상태가 남아 있음 |
| F6 | **Condition Branch Missing** | 요소가 조건부로 존재하는데 assertion은 항상 실행됨 |
| F7 | **Test Isolation Failure** | 단독으로는 통과, suite에서는 실패 |
| F8 | **Environment Mismatch** | CI 또는 로컬에서만 발생; 뷰포트, OS, 시간대 |
| F9 | **Data Dependency** | 시드 데이터 누락, 하드코딩된 ID |
| F10 | **Auth / Session** | 세션 만료, 역할 기반 UI가 렌더링되지 않음 |
| F11 | **Async Order Assumption** | `Promise.all` 순서, 병렬 경쟁 |
| F12 | **POM / Locator Drift** | DOM 구조가 바뀌었는데 POM이 갱신되지 않음 |
| F13 | **Error Swallowing** | 실제 실패를 숨기는 `.catch(() => {})` |
| F14 | **Animation Race** | 콘텐츠가 아직 렌더링되지 않았거나, 일시적 요소가 관찰되기 전에 제거됨 |
| F15 | **Hydration Race** | 액션은 성공하지만 효과가 없음 — SSR 페이지가 아직 하이드레이션되지 않음; 다음 assertion에서 실패 |

### 디버그 workflow

1. **추출** — `results.json`에서 실패한 테스트, 오류 메시지, 소요 시간을 파싱
2. **분류** — 오류 신호를 이용해 각 실패를 F1–F15에 매핑(대부분의 실패가 여기서 해결됨)
3. **트레이스** — 그래도 불명확하면 `trace.zip`을 풀어 단계별로 검사: 실패한 액션, DOM snapshot, 네트워크 오류, JS 콘솔 오류
4. **수정** — 실패별 구체적 코드 제안, P0/P1/P2 우선순위

---

## Skill 4: `cypress-debugger` — Cypress 실패 debugger

mochawesome 또는 JUnit 리포트 파일을 바탕으로 Cypress 테스트 실패를 진단합니다. 근본 원인을 분류하고 구체적인 수정을 제시합니다.

### 사용 시점

- 파악해야 할 실패가 담긴 `cypress/reports/` 디렉터리(로컬 또는 CI에서 다운로드)가 있을 때
- Cypress 테스트가 로컬에서는 통과하는데 CI에서는 실패할 때
- flaky하거나 간헐적인 Cypress 실패를 겪고 있을 때
- 명확한 원인 없이 `Timed out retrying`이나 `Expected to find element`가 발생할 때

### 사용법

```
Debug these failing Cypress tests
Why did these Cypress tests fail?
Analyze cypress/reports/
Cypress tests pass locally but fail in CI
```

### 15개 근본 원인 카테고리

| # | 카테고리 | 신호 |
|---|----------|---------|
| F1 | **Flaky / Timing** | `Timed out retrying`, 재시도 시 통과 |
| F2 | **Selector Broken** | `Expected to find element`, `cy.get() failed` |
| F3 | **Network Dependency** | `cy.intercept()` 미매칭, `XHR failed` |
| F4 | **Assertion Mismatch** | `expected X to equal Y`, `AssertionError` |
| F5 | **Missing Then** | 액션은 완료됐지만 잘못된 상태가 남아 있음 |
| F6 | **Condition Branch Missing** | 요소가 조건부로 존재하는데 assertion은 항상 실행됨 |
| F7 | **Test Isolation Failure** | 단독으로는 통과, suite에서는 실패 |
| F8 | **Environment Mismatch** | CI 또는 로컬에서만 발생; baseUrl, 뷰포트, OS |
| F9 | **Data Dependency** | 시드 데이터 누락, `cy.fixture()` 불일치 |
| F10 | **Auth / Session** | `cy.session()` 만료, 역할 기반 UI가 렌더링되지 않음 |
| F11 | **Command Queue / Intercept Race** | 요청이 발생한 뒤에 등록된 `cy.intercept`; `.then()` 체인 순서 뒤바뀜; 끝나지 않은 `cy.visit()`과 병렬 `cy.request()`의 경쟁 |
| F12 | **Selector Drift** | DOM이 바뀌었는데 커스텀 커맨드나 POM 셀렉터가 갱신되지 않음 |
| F13 | **Error Swallowing** | 실패를 숨기는 `cy.on('uncaught:exception', () => false)` |
| F14 | **Animation Race** | 콘텐츠 미렌더링, 일시적 요소가 관찰 전에 제거됨, 또는 CSS 트랜지션 미완료 |
| F15 | **Hydration Race** | `cy.visit()` 후 첫 클릭이 성공하지만 효과가 없음 — SSR 페이지가 아직 하이드레이션되지 않음; 다음 assertion에서 실패 |

### 디버그 workflow

1. **추출** — `mochawesome.json` 또는 JUnit XML에서 실패한 테스트, 오류 메시지, 소요 시간을 파싱
2. **분류** — 오류 신호를 이용해 각 실패를 F1–F15에 매핑(대부분의 실패가 여기서 해결됨)
3. **스크린샷/비디오** — 그래도 불명확하면 `cypress/screenshots/`와 `cypress/videos/`를 검사
4. **수정** — 실패별 구체적 코드 제안, P0/P1/P2 우선순위

---

## FAQ

### e2e-skills란 무엇인가요?

e2e-skills는 Playwright와 Cypress를 위한 오픈소스 AI 에이전트 테스트 도구 묶음입니다. E2E 테스트를 생성하고, 기존 spec에서 조용한 상시 통과 안티패턴을 리뷰하고, flaky 실패를 디버깅하는 네 개의 Agent Skill을 한데 묶었습니다. Claude Code, Codex를 비롯한 `AGENTS.md` 호환 AI 코딩 에이전트 안에서 실행됩니다.

### 통과는 하지만 실제로는 아무것도 테스트하지 않는 Playwright/Cypress 테스트는 어떻게 찾나요?

spec 디렉터리를 대상으로 `e2e-reviewer` 스킬 또는 독립 실행형 스캐너 `scan.sh`를 실행하세요. assertion의 `await` 누락, 일회성 `isVisible()` 읽기, matcher 없는 `expect()`, 커밋된 `.only` 유출처럼 담당 기능이 깨져도 테스트를 통과 상태로 남겨 두는 안티패턴 24개를 심각도(P0/P1/P2)별로 표시합니다.

### eslint-plugin-playwright나 eslint-plugin-cypress와는 무엇이 다른가요?

eslint plugin은 커밋마다 문법 규칙을 걸러 주는 기본 방어선이며, 스캐너는 이를 가장 먼저(Tier 1) 실행합니다. `e2e-skills`는 이를 대체하지 않고 그 위에 한 계층을 더합니다. 그 계층은 linter가 [구조적으로 판별할 수 없는](#linter가-구조적으로-잡을-수-없는-것) smell입니다: 이름-assertion 불일치, 결코 throw하지 않는 함수를 감싼 `try/catch`, 항상 참인 `expect(locator).toBeTruthy()`, 인증이 빠진 route. 이런 문제를 확정하려면 AST 규칙이 보지 못하는 코드, 즉 다른 함수, 컴포넌트, CI 설정, 테스트의 의도까지 읽어야 합니다. `e2e-reviewer`는 그 주변 코드를 읽어 발견을 검증하고 임시방편을 피하는 수정안을 제시하지만, lint는 단일 파일의 문법만 표시할 수 있습니다.

### CodeRabbit, Copilot, Cursor BugBot 같은 AI 코드 리뷰어와 다를 게 없지 않나요?

그것들은 훌륭한 범용 리뷰어입니다. 상당수가 오픈소스 프로젝트에는 무료이고, 이제 로컬에서도 실행됩니다(CodeRabbit의 CLI는 터미널에서 스테이징된 변경을 리뷰합니다). 차이는 능력이 아니라 전문화입니다: 범용 리뷰어는 건네받은 diff가 무엇이든 그 위에서 추론하지만, `e2e-reviewer`는 엄선되고 안정적이며 심각도가 매겨진 E2E 조용한 상시 통과 안티패턴 카탈로그를 갖추고 있습니다. 고정 ID의 24개 패턴과 15개 실패 디버깅 카테고리를 함께 봅니다. 또한 PR diff만이 아니라 전체 spec 디렉터리를 대상으로 필요할 때마다 실행됩니다. 모든 것에는 범용 리뷰어를 쓰고, E2E 테스트의 신뢰성이 정말 중요한 문제일 때 이것을 쓰세요. 리뷰된 PR 100건에 대한 실제 비교(솔직한 한계 포함)는 [AI reviewer benchmark](docs/ai-reviewer-benchmark.md)를 참고하세요.

### Playwright뿐 아니라 Cypress에서도 동작하나요?

네. 둘 다 일급으로 지원합니다: 테스트 생성과 가장 풍부한 리뷰는 Playwright를 대상으로 하고, 리뷰와 실패 디버깅은 Cypress(mochawesome 및 JUnit 리포트)를 완전히 커버합니다.

### CI에서만 실패하는 flaky 테스트도 디버깅할 수 있나요?

네. `playwright-debugger`와 `cypress-debugger`가 리포트 파일(`playwright-report/`, `cypress/reports/`)을 읽고 각 실패를 15개 근본 원인 카테고리(flaky 타이밍, 셀렉터 드리프트, 테스트 격리, 환경 불일치, 하이드레이션 경쟁 등)로 분류하며, 실패별로 구체적인 수정안을 제시합니다.

### AI가 생성한 E2E 테스트는 어떻게 리뷰하나요?

생성된 spec을 대상으로 `e2e-reviewer`를 실행하세요. AI가 작성한 테스트에는 자신감 있어 보이지만 조용히 항상 통과하는 assertion이 자주 들어 있습니다. 리뷰어는 이런 assertion이 메인 브랜치에 들어가기 전에 수정 전/후 예시와 함께 짚어 줍니다.

### 어떤 AI 코딩 에이전트를 지원하나요?

Claude Code(plugin marketplace 또는 `skills` CLI), Codex, 그리고 `skills` CLI가 `AGENTS.md`를 통해 지원하는 모든 에이전트입니다. 55개 이상의 호스트에서 한 번 설치해 사용할 수 있습니다.

### Playwright와 Cypress 외의 테스트 프레임워크도 지원하나요?

아니요. 의도적으로 Playwright와 Cypress만 지원합니다. 자세한 이유는 [프레임워크 범위](docs/framework-scope.md)를 참고하세요.

## 로드맵

아래는 계획이지 아직 출시된 기능이 아닙니다. 현재 동작이 아니라 앞으로의 방향을 설명합니다:

- **모델 간 일관성.** AI 에이전트마다 자기 스타일로 spec을 작성하기 때문에, 여러 모델이 함께 만든 suite는 하나의 컨벤션으로 묶이지 않은 채 제각각으로 흘러갑니다. 계획은 프로젝트의 컨벤션(POM 형태, locator 전략, fixture와 구조 패턴)을 추론하고, 코드베이스가 정말로 모호한 지점에서만 질문하며, 답을 기록해 이후 모든 모델이 따르게 하는 것입니다. '추상화 없음'도 유효한 답입니다. 두 페이지짜리 flow에 불필요한 Page Object 계층을 깔지 않습니다. 핵심은 기록된 컨벤션이 딱딱한 규칙이 아니라, *이유를 밝히면 에이전트가 벗어날 수 있는 기본값*으로 남는다는 점입니다. 그래서 특정 테스트에 더 맞는 접근을 가로막지 않고, 정당한 이탈은 오히려 컨벤션을 다듬는 계기가 됩니다. 이것이 linter가 구조적으로 할 수 없는 부분입니다: linter는 고정된 규칙을 강제할 뿐, *여러분의* 컨벤션을 학습해 따를 수는 없습니다.
- **deterministic 감지 계층.** 파일 단위로 타입만 알면 판별 가능한 smell(Locator를 truthy로 검사, 떠 있는 assertion)을 프롬프트와 휴리스틱에서 타입 인지 AST 패스로 옮겨, 감지를 재현 가능하게 만들고 LLM은 단일 파일 규칙이 내릴 수 없는 판단에만 사용합니다. 명확히 lint화할 수 있는 규칙은 다시 구현하는 대신 `eslint-plugin-playwright` upstream에 기여합니다 — 그 첫 번째로 항상 통과하는 Locator assertion을 잡는 `no-unnecessary-assertions` 규칙이 [merge됐습니다](https://github.com/mskelton/eslint-plugin-playwright/pull/470).

이와 별개로 upstream 기여 로드맵에서는 더 넓은 파이프라인을 추적합니다: **merge 14건, 리뷰/대기 14건**. 대기열에는 검증을 마친 1,000+ 스타 후보만 올립니다. 최신 표는 [upstream 기여](docs/roadmap.md)에 있습니다.

## 기여하기

버그 리포트, 오탐(false-positive) 가드, 새 안티패턴, 번역을 모두 환영합니다. 설정 방법, 검증 게이트(`bash scripts/ci/ci-local.sh`), 고정 ID / 패리티 컨벤션은 [CONTRIBUTING.md](./CONTRIBUTING.md)에서 시작하세요. 더 깊은 cross-agent 세부 사항은 [AGENTS.md](./AGENTS.md)에 있습니다.

## 라이선스

Apache-2.0 &copy; [voidmatcha](https://github.com/voidmatcha). [LICENSE](./LICENSE)를 참고하세요.
