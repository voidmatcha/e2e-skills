# Pattern ID Reference

**This file is a lookup table, not a dispatch procedure.** Phase 1 runs `bash <skill-base>/scripts/scan.sh` (the runtime source of truth); use this file to interpret what each pattern ID means when reading scanner output, doing Phase 2 review, or mapping debugger failure categories back to review patterns. Do NOT hand-dispatch these greps.

Treat `// JUSTIFIED:` as a request to suppress a documented exception, not as
proof that every marked hit is safe. For P1/P2, skip a hit after confirming a
concrete rationale in one of the positions below. For P0, keep the hit visible
as a deduplicated `[P0?][JUSTIFIED-REVIEW]` candidate until Phase 2 or an
external verifier confirms the rationale; it still gates
`E2E_SMELL_FAIL_ON=p0-candidate` before that confirmation. #7 Focused Test
Leak is never suppressible:
1. The line **immediately preceding** the hit.
2. The line immediately preceding the **enclosing call/block** when the hit is inside a callback body — e.g., `// JUSTIFIED:` above `page.evaluate(() => { … document.querySelector(…) … })` covers every qualifying pattern inside that callback.
3. For chained calls split across lines (`page.locator(…)\n  .filter(…)\n  .first()`), the line immediately preceding the chain's starting expression covers `.nth()` / `.first()` / `.last()` further down the chain.

The scanner applies the direct-line and bounded fluent-chain forms itself, and
also the enclosing-block form for brace-delimited Playwright
`evaluate()`/`waitForFunction()` callbacks. The
marker must be the immediately preceding pure `//` comment; another comment,
code line, semicolon, block boundary, or second independent expression ends
that boundary.

When raw grep output is the only thing you have, always read 1–3 lines of surrounding context before flagging — most false positives come from JUSTIFIED comments sitting just above the visible match.

**Discovery and tool trust:** filename validation, Tier 2, and every Tier-3
rule use no-ignore mode; repository, parent, global Git, `.ignore`, and
`.rgignore` configuration cannot hide candidates. Explicit `node_modules`,
generated, vendor, report, eval-fixture, and minified-output exclusions still
win in every tier. Tier 2 requests a bounded ast-grep JSON stream, validates
each record before counting it, and fails closed on malformed or unconsumed
output. The scanner replaces inherited `PATH` before external commands and
binds `rg`, optional
`node`/`npx`, and optional `ast-grep` from deterministic locations or explicit
absolute `E2E_SMELL_*_BIN` overrides.

**Tier-3 workload ceiling:** each rule accepts at most 1,000 raw candidates by
default. `E2E_SMELL_MAX_RULE_HITS` may be set from 1 through 10,000. Exceeding
it prints `INCOMPLETE` and exits 2 before findings or Summary output. Tier 2
and Tier 3 tool output, plus opted-in Tier 1 ESLint output, is streamed through
the same line ceiling and a byte
ceiling before shell materialization; `E2E_SMELL_MAX_RULE_BYTES` defaults to
1 MiB and may be set up to 16 MiB. Do not interpret either infrastructure
failure as a P0 count.

**Phase-0 e2e-file scope filter (Tier 3):** the scanner drops hits in files that carry no executable Playwright/Cypress marker — `.cy.` / `.e2e.` names, Cypress paths, Playwright imports (including namespace aliases and transitive relative ESM/CommonJS fixture modules), Playwright fixture/type provenance, or executable `page.<api>` / `cy.<cmd>(` usage. Framework-looking text inside comments and strings does not create scope. A known foreign test-module import overrides a `.cy.*` basename for Cypress-only rules unless the same file also has executable Cypress module/runtime provenance. Playwright-only rules additionally require Playwright provenance, so a Cypress file with an unrelated object named `page` does not become a Playwright file. Skipped files are counted and reported on a `Scope filter:` line before the Summary — never silently.

---

## Group 1 — error swallowing, focus leaks, sleeps, raw DOM

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #3 Error Swallowing | `\.catch(?:\?\.)?\(\s*(async\s*)?\(\)\s*=>` plus function-expression forms | `*.{ts,js,cy.*}` | `.catch(() => {})`, `.catch?.(() => {})`, and equivalent function callbacks in POM/spec silently hide failures |
| #7 Focused Test Leak | `\.(only)(?:\?\.)?\(` plus immutable one-hop alias declarations/calls | `*.{spec.*,test.*,cy.*}` + `**/cypress/integration/**/*.{js,ts}` | `test.only` / `it.only` / `describe.only`, optional-call variants, `const focused = test.only[.bind(test)]`, `const { only } = test`, and `const { only: focused } = test` followed by the alias call — zero legitimate committed uses, always P0. Playwright named/default/CommonJS/namespace receivers follow the exact `test` binding through relative re-exports; a sibling Playwright export cannot promote an unrelated receiver. Cypress-proven spec context is required for Cypress globals. Reassigned, shadowed, foreign-framework, ordinary-method, and wrong-receiver aliases are excluded. Glob also covers the legacy `cypress/integration` layout (plain `.js`, no `.cy.`/`.spec.`/`.test.` suffix). |
| #9 Hard-coded Sleeps | `<proven Page>.waitForTimeout` | Playwright-proven JS/TS | Explicit sleeps cause flakiness. Receiver fixture/type provenance is required; `fakeClock.waitForTimeout()` is not a finding. |
| #9b Cypress Sleeps | `cy\.wait\(\d` | `*.{cy.*}` | Cypress numeric waits |
| #6 Raw DOM Queries | `document\.querySelector` | `*.{ts,js,cy.*}` | LLM-triage candidate: confirm the framework API can express the same condition; allow necessary computed-style, child-count, multi-condition, cross-element, or whole-body-text logic. Search POM files too. |

## Group 2 — vacuous and one-shot assertions

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #4a Always-true math | `toBeGreaterThanOrEqual\(0\)` | E2E-scoped JS/TS plus unresolved-package-fixture triage | Mathematically always true. An unresolved package/workspace `test` fixture retains the candidate as `[LLM-TRIAGE]`; known unit-framework imports do not establish E2E scope. |
| #4b Vacuous attached | `\btoBeAttached\b` name candidate, then a lexical filter drops quoted/comment-only names, requires `(` within a bounded 24-line/500-character whitespace gap, and excludes `.not` chains across whitespace/comments/lines (positive form only) | `*.{ts,js,cy.*}` | P1, grep-undecidable: this is deliberately a finite lexical scan, not unbounded parser semantics. The scanner tags each hit `[P1?][LLM-TRIAGE]`. Phase 2 must confirm destructive-action context (the element should have been removed) before reporting — on client-rendered apps a positive `toBeAttached(...)` is usually a legitimate render-gate (~90% FP); CSS-hidden intent takes `// JUSTIFIED:` → skip |
| #4c One-shot isVisible | `expect(… await <locator>.isVisible(…) …)` — the scanner runs #4c/#4d/#4e as ONE combined `#4c-4e` check whose leading `(?:[!(\s+-]\|[A-Za-z_$][\w$.]*\()*` group also admits wrapped forms: `expect((await …).trim())`, `expect(Number(await …))`, `expect(!(await …))` | `*.{spec.*,test.*}` | P1 one-shot boolean, no auto-retry. Sync-matcher reads like these are #4c-4e, NOT #15 — the `await` resolves a value, nothing floats (see #15 row) |
| #4d One-shot state | `expect(… await <locator>.(isDisabled\|isEnabled\|isChecked\|isHidden\|isEditable)(…) …)` (part of the combined `#4c-4e` check) | `*.{spec.*,test.*}` | Same one-shot boolean problem |
| #4e One-shot content | `expect(… await <locator>.(textContent\|innerText\|getAttribute\|inputValue\|allTextContents\|allInnerTexts\|count)(…) …)` (part of the combined `#4c-4e` check) | `*.{spec.*,test.*}` | Resolves immediately; use `toHaveText()`, `toHaveAttribute()`, `toHaveValue()`, `toHaveCount()`. One-shot `.count()` is caught here because the regex anchors it inside `expect(await ….count())` — a bare `count` regex would over-flag ORM/array `.count()`; the Tier-2 ast-grep `sg-4ce-count` rule additionally covers matcher-on-next-line/AST-only shapes |
| #4h One-shot URL | `<Playwright expect binding>(<proven Page>.url())` | Playwright-proven JS/TS | The scanner follows provenance-backed aliases of Playwright `expect` and renamed/typed `Page` receivers. `page.url()` reads URL at one instant with no retry; use `await expect(page).toHaveURL(...)`. |
| #4i Unproven absence | `.not.toBeVisible(` / `.not.toBeAttached(` / `.toBeHidden(` / `.toHaveCount(0)` / `.should('not.exist'\|'not.be.visible')` | `*.{spec.*,test.*,cy.*}` + `**/cypress/{integration,e2e}/**` | Grep-undecidable: an absence assertion is satisfied by zero matches (Playwright defines `toBeHidden` as "does not resolve to any DOM node, **or** resolves to a non-visible one"), so a rotted selector passes forever. Scanner tags each hit `[P1?][LLM-TRIAGE]`, outside the exit gate. Phase 2 skips the hit when the same locator is asserted present / acted on earlier in the test or `beforeEach`, or when an empty-state test asserts a positive counterpart; flags only when the locator appears nowhere else. Empty-state tests dominate raw hits. |
| #4j Under-specified ARIA snapshot name | `toMatchAriaSnapshot(` opening-token sweep, then inspect YAML role nodes whose accessible name is omitted | Playwright-proven JS/TS, LLM-only | Playwright partial matching accepts any accessible name when a role node omits it. Flag P1 only when the title/action contract promises that label or control identity. Skip intentional structure-only snapshots with a separate accessible-name/complete-outcome assertion, named nodes, or concrete `// JUSTIFIED:` rationale. The bundled scanner does not emit this ID. |

## Group 3 — truthiness traps, bypasses, ordering

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #4f Locator always-true | `\.toBeTruthy\(\)` / `\.toBeDefined\(\)` / `\.not\.toBeNull\(\)` / `\.not\.toBeUndefined\(\)` / `\.not\.to\.equal\(null\)` / `\.not\.to\.be\.null` | `*.{ts,js,cy.*}` | Flag hits where the subject is a Locator: a Locator is always a truthy, non-null, defined JS object regardless of element existence, so `toBeTruthy`/`toBeDefined`/`not.toBeNull`/`not.toBeUndefined`/`not.to.equal(null)`/`not.to.be.null` on it never fail. Non-Locator subjects (e.g., boolean variables, a `textContent()` string that can legitimately be null) are fine — confirm in Phase 2. |
| #4f Cypress jQuery object | `expect(Cypress.$(...)).to.exist` / truthiness | Cypress JS/TS | A jQuery wrapper exists even when it contains zero elements; structurally certain forms are P0. Assert `.length` or use `cy.get(...).should(...)`. |
| #4g Timeout zero | `timeout:\s*0` in bounded Playwright/Cypress call context | E2E-scoped JS/TS | P1 retry/deadline hazard. Standalone option objects and unrelated clients are excluded. Playwright 1.62 removes the assertion-local deadline and can retry until the enclosing test/hook timeout; Cypress removes the normal command retry window. Flag unless a concrete `// JUSTIFIED:` documents the bounded outer deadline or intentional immediate check. |
| #5a Conditional bypass | `if.*(isVisible\(\|is\(.*:visible.*\))` | `*.{spec.*,test.*,cy.*}` | `[LLM-TRIAGE]` Candidate runtime branch. Report P0 only when the branch body gates an assertion; action-only setup/navigation branches remain outside the scanner's P0 exit gate. Requires the `.isVisible(` call form, so a bare boolean variable named `isVisible` is not matched. |
| #5b Force true | `force:\s*true` within a Playwright/Cypress action call | E2E-scoped JS/TS | Bypasses actionability checks (visibility, enabled state). `fs.rm` / API-client options with the same property are excluded. |
| #10b Serial ordering | `.describe.serial(` or bounded `.describe.configure({ mode: 'serial' })` | Playwright-proven JS/TS | `[Playwright only]` — same-line and multiline configuration forms are covered; order-dependent tests break parallel sharding. |

## Group 4 — no-op statements, positional selectors, credentials

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #8a Dangling locator | `^\s*(await\s+)?page\.(locator\|getBy*)\(...\)\s*;?\s*(//.*)?$` + previous-line continuation filter (a hit is dropped when the preceding non-blank line ends with `(` or `,`) | framework-proven JS/TS | `[P0?][LLM-TRIAGE]`, Playwright only — locator created as standalone statement, no `expect()`, no action, no assignment. Report P0 only when it was the test's intended verification and no independent verification/failure evidence exists. |
| #8b Boolean discarded | `^\s*await .*\.(isVisible\|isEnabled\|isChecked\|isDisabled\|isEditable\|isHidden)\([^)]*\)\s*;?\s*(//.*)?$` | framework-proven JS/TS | `[P0?][LLM-TRIAGE]` — boolean result computed and thrown away; selector-arg and no-semicolon forms included, end anchor excludes `.catch()`/chained reads. Skip when the test already has real assertions or immediately acts on the same locator; a missing outcome is #2. |
| #10a Positional selectors | `\.nth\(\|\.first\(\)\|\.last\(\)` | E2E-scoped JS/TS, including POM/support files | `[P1?][LLM-TRIAGE]` — first prove the receiver is a Playwright/Cypress locator; unrelated APIs such as database query builders are never final findings. Then apply the documented exemptions and any concrete `// JUSTIFIED:` rationale. Scan Playwright/Cypress-proven POM/support files as well as specs for positional locators. POM encapsulation is not an exemption: moving a positional locator into a semantically named Page Object method does not make it stable. Only a method name that explicitly promises positional access may use the method-name exemption. When a positional locator targets a collection that is conditionally rendered or reordered by viewport, feature flags, permissions, or state, inspect those render conditions before resolving the candidate. |
| #10c Unscoped name substring | Playwright `page.getByRole/getByLabel/getByPlaceholder` or Cypress Testing Library `cy.findByRole/findByLabelText/findByPlaceholderText` with `name:` and no `exact: true` | framework-proven JS/TS | `name` without `exact: true` can substring-collide with dynamic page text. LLM confirms page/Cypress-chain scope plus dynamic-content risk. Skip container-scoped Playwright accessors, `exact: true`, or regex names. |
| #10d Cypress async callback | Cypress `it/test/specify/before/beforeEach/after/afterEach(..., async arrow/function ...)` + bounded callback-body `cy.*` confirmation | `*.{cy.*,spec.*,test.*}` + Cypress directories | `[LLM-TRIAGE]` Cypress queues commands and rejects mixing returned promises/async callbacks with queued `cy` commands. Native-Promise-only async callbacks are excluded. |
| #10e Assigned Cypress command | `(const\|let\|var) name [: Type] = cy.<command>` except `cy.spy()`/`cy.stub()` | `*.{cy.*,spec.*,test.*}` + Cypress directories | Same-line declarations, including TypeScript annotations. A queued command returns a Chainable, not the yielded application value; Phase 2 checks split declarations. Synchronous Sinon utilities intentionally return their doubles. |
| #10f Unsafe Cypress action chain | action (`click/type/check/...`) followed by another assertion/action in the same bounded chain | `*.{cy.*,spec.*,test.*}` + Cypress directories | `[LLM-TRIAGE]` Bundled reconstruction covers same-line and multiline candidates. Actions execute once, so continued chains can observe detached/stale state. End the chain and re-query. |
| #14 Hardcoded credentials | credential/auth token + UI login, API auth payload, or reusable valid-user fixture | standard E2E JS/TS extensions + Cypress layouts | Literal candidates are LLM-TRIAGE; confirm positive authentication use and skip input-validation or intentional invalid-credential data. |

## Group 5 — missing awaits, direct page APIs, suppression

#3b scans both spec and support files through the combined Cypress/TypeScript glob.

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #15 Missing await on expect | Provenance-backed web-first matchers (including `toBeOK()`) plus `expect.poll(...).toX()` / `expect(fn).toPass()` without `await`/`return` | Playwright-proven JS/TS | `[Playwright]` P1; legal block comments between `expect` and `(` are accepted, while strings/comments remain inert. |
| #16 Missing await on action | Locator actions plus Page navigation/history operations without `await`/`return` | Playwright-proven JS/TS | `[Playwright]` P1; legal block comments before `()` are accepted, proven direct chains are final, broader POM/variable chains are triage, observed aggregates are excluded. |
| #17 Discouraged direct Page selector API | Literal or variable selector arguments on a fixture/type-proven Playwright `Page`; `[LLM-TRIAGE]` for unproven `page`, `this.page`, and other Page-shaped receiver names | Playwright-proven JS/TS, plus unresolved-fixture `.e2e` triage | Proven receivers can be final; variable selector and unresolved-fixture candidates remain triage until receiver provenance is confirmed. Prefer Locator actions for composition, strictness, reuse, and clearer failures. P1. |
| #9c Networkidle | `waitForLoadState('networkidle')` / `waitUntil: 'networkidle'` (API shapes only, e2e-scoped) | `*.{ts,js}` | Playwright docs warn against `networkidle` — unreliable on modern SPAs. P1. |
| #18 expect.soft dependency leak | `<proven Playwright expect binding>.soft(` | Playwright-proven JS/TS | `[Playwright]` `[LLM-TRIAGE]` — provenance-backed aliases are included. Playwright still fails the test. In Phase 2, flag P1 only when a soft prerequisite is followed by dependent work without an intervening hard gate; skip terminal sets of independent soft details regardless of their count or ratio. |
| #3b Cypress uncaught:exception opening | `(cy\|Cypress)\.on\(` | `*.{cy.ts,cy.js,ts,js}` | `[Cypress]` `[LLM-TRIAGE]` — generic assertions do not excuse unconditional `return false`; safe handlers conditionally allowlist a named regression and rethrow all others. |

## Group 6 — module-level state

| Check | Pattern | Glob | What it detects |
|-------|---------|------|-----------------|
| #19 Module-Level Mutable State | top-level `let` with an initializer (the contract also covers `var` and mutated `const` containers, which reach Phase 2 through the sweep) | `*.{ts,js,tsx,jsx,cy.ts,cy.js}` | The scanner emits only initialized top-level state such as `let counter = 0;`; declaration-only bindings such as `let page: Page;` are excluded mechanically. Initialized state persists across tests within a long-lived worker and can collide across parallel workers. Playwright retries in a fresh worker after failure, so retry survival is not part of the rule. P1. |
