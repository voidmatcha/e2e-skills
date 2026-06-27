# Changelog

## [1.7.0] - 2026-06-27

### Added
- **Companion ESLint plugins — published and dogfooded.** Shipped [`eslint-plugin-playwright-silent-pass`](https://github.com/voidmatcha/eslint-plugin-playwright-silent-pass) and [`eslint-plugin-cypress-silent-pass`](https://github.com/voidmatcha/eslint-plugin-cypress-silent-pass) (Apache-2.0, on npm): autofixable rules for the mechanical always-pass class (`#4f` — `expect(locator).toBeDefined()` / `.toBeTruthy()` / `.not.toBeNull()`) that the official `eslint-plugin-playwright` / `-cypress` do not cover. The scanner's Tier 1 now runs them via npx when available — best-effort, so a missing/offline package never breaks Tier 1 and Tier 2/3 still cover `#4f`. `e2e-reviewer` SKILL.md (Phase 1) positions them as the commit/CI-time companion to this agent-time review and recommends installing the matching plugin on `#4f` hits.

### Docs
- README: cross-link the two plugins; add a sourced AI-evidence note (LLM-generated tests reproduce human anti-patterns, and the "iterate until the suite is green" agent loop weakens assertions to vacuity); correct PR-status claims (Qwik#8727 closed → current in-review PRs across module-federation, qwik#8777, mui-x, Supabase, Expo, TanStack Router); remove the demo GIF from the README.
- `docs/roadmap.md`: synced the In-review table to current PR states (Qwik#8727 closed → #8777 in review; module-federation approved) and restored newline-merged rows; queued candidates gated to ≥1000 stars.
- `scripts/ci/test-parity.sh`: the Case 7 docs-orphan drift check now strips both README → `docs/roadmap.md` links so the orphan assertion still fires after the README gained a second reference.
- `e2e-reviewer/SKILL.md`: shortened the trigger `description` (927 → 457 chars) to a lean WHAT + triggers form per Anthropic/Codex skill-description guidance; the 24-pattern P0/P1/P2 catalog now lives in the three manifests and the SKILL body Quick Reference, not the frontmatter. `scripts/ci/review.sh` Check 5 now sources phrase parity from `.claude-plugin/plugin.json` (manifest↔manifest) instead of the SKILL frontmatter; `AGENTS.md` and `test-parity.sh` Case 11 updated to match.

## [1.6.0] - 2026-06-26

### Changed
- **All three generation/debugging skills hardened after a cross-skill audit, then empirically verified on both Claude and Codex (no pattern ID or failure-category change).** A cross-host run confirmed Claude and Codex reach the same diagnosis on the same input, and the cypress parser fix below was confirmed real (the old query returned nothing on a realistic report; the new one returns the screenshot path).
  - `cypress-debugger`: Phase-3 screenshot extraction now parses mochawesome's JSON-stringified `context` (`fromjson`) instead of treating it as a nested object. Phase-1 now carries the spec `file`/`fullFile` and the retry `attempts[]` so "passes on retry" is verifiable from the data, and the skill gained a `cypress.config` `retries`/`testIsolation` reference, a Cypress "heal by intent" note, a `mochawesome-merge` step for split `mochawesome*.json`, and a `cy.intercept` alias-ordering example. New eval fixtures: `mochawesome-screenshot-context.json`, `mochawesome-retries.json`.
  - `playwright-debugger`: report handling now detects the reporter in use (HTML report directory vs `results.json` vs `blob-report/`) instead of assuming `results.json`; the Phase-1 projection surfaces `errorLocation` (the failing call's file:line, distinct from the spec line); added first-class signals for fixture/`beforeEach` setup failures and unmerged-shard artifacts, a "real product bug vs test bug" decision gate before any test fix, and `playwright show-trace` as the primary trace path. Output format aligned with `cypress-debugger` for cross-host parity.
  - `playwright-test-generator`: the live-exploration step now names its tool source and adds a deterministic ARIA-snapshot fallback plus an app-reachability probe (read and await the configured `webServer`) so the pipeline no longer stalls when the dev server is down; the verification run emits `--trace on-first-retry --reporter=html` for the debugger handoff; selector priority raises `getByTestId` when a project standardizes on it; `best-practices.md` and `code-rules.md` were refreshed (storageState/projects/test-id/ARIA snapshot) with a top-of-file hard-rules checklist.

### Added
- **`e2e-reviewer` #2 (Missing Then) accept-criteria guards.** `pattern-reference.md` documents the contexts that must not be flagged (API-404 negative checks, cleanup/teardown, success-toast-only flows, helper-embedded assertions, non-entity removes). New evals: a delete-verification case (one true positive plus false-positive guards) and an always-true-locator fixture; minor scanner and grep-pattern touch-ups.
- **AI-reviewer benchmark cross-model re-judge.** The contestable unique catches were re-judged by an independent cross-model judge (OpenAI gpt-5.5 via Codex), which agreed on 13/15 (87%); recorded in `docs/ai-reviewer-benchmark.md` and surfaced in the README.
- **Hero banner (`docs/assets/hero.png`).** A liquid-glass hero image for the README.

### Docs
- README: hero banner, flat status badges (with a "merged PRs" and "55+ agents" badge), a "Why I built this" section, an intent-vs-assertion thesis leading "What a linter structurally cannot catch", a top-of-readme before/after impact diff, a "Roadmap" (planned, not shipped) section, and a simpler `--all` install one-liner.
- `docs/roadmap.md`: retitled to "Upstream Contributions: Track Record and Roadmap"; added a star-count column to every table; added new queued candidates (DefGuard, valor-software/ngx-bootstrap, perses) and three backlog entries; moved voxel51/fiftyone to In review; removed verbose drop notes.

## [1.5.6] - 2026-06-17

### Docs
- **README improved for OSS conventions and SEO/GEO discoverability.** Added a status-badge row, a one-line value proposition, and an eight-question FAQ (definitional, answer-shaped entries that AI search engines and LLMs can cite). Updated the "Proven in Open Source" section to reflect validation against 100+ open-source Playwright and Cypress test suites in the local testbed (zero GitHub side effects), and the rule changes those scans drove.
- **Added `docs/roadmap.md` (contribution roadmap) and removed `docs/case-studies.md`.** The roadmap folds in the merged-PR lessons and adds the live contribution plan: merged, in review, 21 prepared candidates, and 29 backlog candidates (50 total), plus the cadence (about 10 PRs open at a time, replenished as each merges) and the goal of at least 25 merged PRs as real-world validation. README and the drift smoke test (`test-parity.sh` Case 7 orphan check) repointed from case-studies to roadmap.

### Changed
- **`e2e-reviewer` scanner — two detection-coverage fixes surfaced during an upstream-PR campaign (no pattern ID or severity change).** (1) **Legacy Cypress layout** `cypress/integration/**/*.js` (plain `.js`, no `.cy.`/`.spec.`/`.test.` suffix) was invisible to the suffix-globbed checks, so a committed `it.only` and other smells in that classic layout were silently missed. `run_check` now supports a `;`-separated multi-glob include, and the Cypress-intended checks (#3, #7, #9b, #5a, #8b, #10a, #14) additionally scan `**/cypress/integration/**/*.{js,ts}`. (2) **Misplaced-await variant of #15**: `expect(await locator).toBeVisible()` placed the `await` on the locator (a no-op, since a Locator is not thenable) instead of on `expect`, so the web-first matcher promise still floated and the base #15 check skipped it by design. A second #15 detection now catches the awaited-locator form, bounded to web-first matchers so value-resolving one-shot reads (`expect(await x.isVisible()).toBe(true)`, which is #4c-4e) are not double-flagged. New evals: id 11 (legacy `cypress/integration` `it.only` true positive) and id 12 (awaited-locator true positives plus valid-`await expect` and `#4c-4e` false-positive guards).

## [1.5.5] - 2026-06-16

### Added
- **`playwright-test-generator/code-rules.md` — two harness patterns distilled from production E2E practice (no pattern ID or reviewer change).** `## Network Determinism` gains a "the mock layer is decided by where the call originates" rule: `page.route()` only intercepts browser-issued requests, so server-side traffic (Next.js SSR/RSC, route handlers, a BFF, `getServerSideProps`) silently bypasses it and hits the real backend — mock those at a server-side seam (an E2E-only env var that returns canned payloads) and detect the origin by whether the data appears in the initial SSR HTML. New `## Branch State Seeding` section: for multi-step funnels, seed the user to the branch's starting state through a test-only API instead of re-driving the shared prefix (consent → phone-auth → …) through the UI in every spec — faster, and one prefix change no longer breaks every downstream test; drive the prefix via UI only in the single spec that verifies it, and record seeding endpoints in the conventions doc (Step 5b).

## [1.5.4] - 2026-06-13

### Fixed
- **Documentation and eval-precision polish (no detection-behavior change).** README F14 "Animation Race" signal cells (both Playwright and Cypress rows) updated to the bidirectional wording shipped in 1.5.3. `sg-4f-locator-as-truthy.yml` drops `getByName` from its method whitelist — it is neither a Playwright Locator method nor an RTL query (it was the documented n8n ~2200-FP culprit). Eval id 2's false-positive-guard line citations corrected (unit-helpers.test.ts 10/15 to 11/16). cypress-debugger eval id 2 severity assertion reworded to match the SKILL.md P0 rubric (P0 is reserved for silent-pass F6/F13, not a loud uncaught TypeError). `scan.sh` dedup comment clarified: the Tier-2/Tier-3 skip is eslint-conditional and LINT_COVERS-scoped, and the ast-grep rules are TypeScript-only by design with `.js`/`.jsx`/`.tsx` delegated to the always-on Tier-3 regex net.

## [1.5.3] - 2026-06-13

### Fixed
- **playwright-debugger Phase 1 extraction was broken.** The documented `jq` selected at result-level, which dropped the flaky-vs-unexpected signal the classification step depends on and returned `title`/`file` as null on a standard Playwright JSON report. Rewritten to select at the spec level (preserving `title`/`file`/`line`, the per-test `outcome`, the `final` result, and `retries`); validated against all five debugger fixtures. Also added `mkdir -p playwright-report` before the reporter redirect (prerequisites case 2), and broadened the F14 ("Animation Race") signal to cover both the not-yet-rendered and removed-before-observed directions, reconciled with the F14-vs-F15 distinguisher and mirrored into cypress-debugger for cross-skill parity.
- **cypress-debugger JUnit extraction captured the wrong test name.** The regex matched `name="..."` inside `classname="..."`; it now requires an attribute boundary (`\sname=` / `\smessage=`). Eval id 3 relabeled (it leaked the playwright debugger's F11 name "Async Order"; cypress F11 is "Command Queue / Intercept Race", and the postMessage/DOM race is F1 with F14 as the secondary).
- **`scripts/pr-preflight.sh`** — committed the previously-uncommitted stage-7 authoring-hygiene block (AI-tell punctuation guard, added-comment cap, test-rename guard) and added a `PREFLIGHT_ALLOW_SLOP=1` override so the punctuation check does not false-positive on intended string-literal content.

## [1.5.2] - 2026-06-13

### Fixed
- **Scanner false positives in three Tier-3 rules (no pattern ID or severity change).** `#15` (missing-await on expect) no longer flags non-Locator expects: `getBy[A-Za-z]+` is tightened to `getBy[A-Z]` (so `getByteLength`/`getBytes` are excluded) and the bare `page)` alternative is anchored with a negative lookbehind, so a dotted `.page` member such as `expect(response.body.page).toBe(2)` or `expect(config.page).toEqual(x)` is no longer a P0. `#5a` (conditional bypass) now requires the `.isVisible(` call form, so a bare boolean variable `if (isVisible)` is not flagged. `#8a` (dangling locator) gains the trailing-line-comment tolerance `#8b` already had, so `page.locator('.x'); // note` is detected. New eval `id 10` (`evals/files/fp-guards.spec.ts`) locks in a true-positive and a false-positive guard for each; `references/grep-patterns.md` synced.

## [1.5.1] - 2026-06-13
### Changed
- **`skills/e2e-reviewer/scripts/scan.sh` — widened Tier-3 detection for two existing P0 patterns (IDs and severity unchanged).** `#8b` (discarded boolean) now matches the selector-argument shorthand (`await page.isVisible('sel');`) and the no-semicolon form, with an end-of-statement anchor so handled reads like `await x.isVisible().catch(() => false)` and chained expressions are not flagged. `#4c-4e` (one-shot read) adds `allTextContents` to its method list, so `expect(await locator.allTextContents()).toContain(v)` is caught in the deterministic Tier-3 baseline. (`count` was intentionally NOT added to Tier-3: a bare regex `.count()` over-flags ORM/array idioms such as `expect(await prisma.user.count()).toBe(n)`; one-shot locator `count` detection stays with the Tier-2 ast-grep `sg-4ce-count` rule.) `references/grep-patterns.md` synced to match. New eval `id 9` (`evals/files/widened-reads.spec.ts`) adds true-positive assertions plus two false-positive guards (`.catch()` chain, assigned-and-used read). Out of scope by design: two-statement read-then-assert (`const t = await x.textContent(); expect(t)...`) and `new URL(page.url()).searchParams.get()` reads remain Phase 2 manual findings — unsafe for line-based Tier-3 regex.

## [1.5.0] - 2026-06-11

Progressive-disclosure restructure of the flagship skill, a new failure category, and the PR-preflight harness that gates the upstream-contribution campaign.

### Added
- **F15 Hydration Race** — new failure category in both debuggers (`playwright-debugger`, `cypress-debugger`): action reported success but had no effect because the first interaction after `goto`/`cy.visit()` landed on a server-rendered page before the framework attached event listeners. Distinguished explicitly from F14 (F14: element not rendered yet; F15: rendered but inert). Classification step, fix guidance (hydration marker gate → self-verifying click; never a blind sleep), README tables, and one new eval per debugger with committed fixtures (`results-hydration-race.json`, `mochawesome-hydration-race.json`) including a false-positive guard case each.
- **`playwright-test-generator/code-rules.md` — SSR & Hydration section.** Gate the first interaction on hydration for SSR apps (marker first, self-verifying `.toPass()` action second, never `waitForTimeout` after `goto`); Qwik resumability and Astro per-island nuances noted.
- **`scripts/pr-preflight.sh`** — six-stage preflight for upstream E2E-fix PRs prepared in `testbed/` clones: smell delta (baseline-vs-working-tree scan), sed-artifact AST check, nearest-tsconfig targeted `tsc`, the repo's own lint on changed files, best-effort headless run of changed specs (env failures classified as SKIP, not FAIL), and diff hygiene (stray tracked-file changes, whitespace-only churn). Every SKIP is reported so the PR body can disclose what was not verified locally — adding the previously missing "run the affected specs before submitting upstream" verification step.
- **`skills/e2e-reviewer/references/pattern-reference.md`** and **`references/applying-fixes.md`** — the 522-line Pattern Reference and the 266-line Phase 4 contract moved out of the SKILL.md body verbatim, read on demand.

### Changed
- **`e2e-reviewer/SKILL.md` body cut from 1,066 to 291 lines (~22k → ~7k tokens per invocation).** The body now holds the executable workflow (Phases 0–3, output format, Quick Reference, suppression); per-pattern contracts and the Phase 4 fix tables live in `references/` with explicit read-on-demand pointers (the three regression-prone Phase 4 rules stay inline). CI parity Checks 3b/3c and drift-smoke Case 4 now validate `references/pattern-reference.md`.
- **`scripts/verify-fixes.sh`** — accepts an explicit changed-file list (`verify-fixes.sh <repo> -- <file>...`) so the postfix AST rules no longer fail on pre-existing upstream artifacts outside the diff; `VERIFY_FIXES_SKIP_TSC=1` lets callers that own typechecking (pr-preflight) skip the root-level `tsc`.
- **`e2e-reviewer/references/grep-patterns.md`** — retitled to "Pattern ID Reference" and stripped of the retired 6-batch Grep dispatch imperatives that contradicted the scanner-based Phase 1 since 1.3.0; ID → regex → meaning tables unchanged.

### Fixed
- README documented the wrong Codex install location (`~/.codex/skills/` → `~/.agents/skills/`), completing the v1.4.2 correction that had only been applied to AGENTS.md.
- AGENTS.md drift: nonexistent `scripts/ci/validate-evals.sh` path, "20 pattern phrases" (actual: 24), "10 drift smoke checks" (actual: 14), failure-code range F1–F14 → F1–F15.

## [1.4.5] - 2026-06-06

Follow-up patch to v1.4.4 from the same production suite (71 tests): the inverse of "prove the call".

### Added
- **`playwright-test-generator/code-rules.md` — Prove the call HAPPENS before asserting it.** Companion rule to "prove the call, not just the pixels": call-proof assertions only apply to calls the app actually makes at runtime. Unmount-cleanup API calls are the canonical trap — an empty-deps effect's cleanup captures guard variables as a stale closure from mount time, so a guard that's empty at mount (e.g. an id that arrives with the fetch response) makes the cleanup call a dead path forever, and a `waitForRequest` assertion times out against correct test code. Verify the request fires at least once before shipping the assertion; otherwise assert the user-visible outcome, file the stale closure as an app defect, and leave a file:line comment for when it's fixed.

### Changed
- Version metadata bumped to 1.4.5 across plugin manifests and all four skill frontmatters.

## [1.4.4] - 2026-06-06

Production-feedback patch from extending the same Pages-Router functional suite to 68 tests (quiz solve loops, logout, password change, modal-gated entry flows): two failure modes that survived a clean v1.4.3 review and only surfaced at runtime, fed back into the debugger playbook and generator rules.

### Added
- **`playwright-debugger/SKILL.md` — Visible-but-unmatchable elements (`aria-hidden` ancestor).** New F2-family diagnosis: a role+name locator stuck at "waiting for" while the screenshot plainly shows the element means an ancestor `aria-hidden="true"` removed the subtree from the accessibility tree — `getByRole` can never match, `getByText` still can. Covers the nastier same-name variant where the role query silently resolves to a control *outside* the hidden subtree and the click is then blocked by the modal overlay. Fix pattern: text locator scoped to a stable container inside the hidden subtree (e.g. `locator('#modalBox').getByText(...)`) + report the root upstream as an app accessibility defect.
- **`playwright-test-generator/code-rules.md` — Wire evidence before `when.params` narrowing.** Third hard rule for request-aware mocks: prove the app actually sends a param at that point in time before keying a rule on it. A `router.query` read in a first-render initializer fires the initial fetch during hydration (before `router.isReady`), silently dropping the param from the wire — a param-narrowed rule then never matches and a previously-green test fails for a contract the app never honors. If the param is best-effort in practice, keep the broad rule and record the WHY with a file:line citation.

### Changed
- Version metadata bumped to 1.4.4 across plugin manifests and all four skill frontmatters.

## [1.4.3] - 2026-06-05

Production-feedback update: patterns proven during a 38-test Wave 1–4 functional suite build on a Next.js Pages-Router app (proxy-cmd API, member-area mocking, write interactions), fed back into the generator rules, reviewer catalog, and debugger playbook.

### Added
- **`code-rules.md` — Request-aware mock rules.** Ordered `MockRule[]` per endpoint (`when: { method, params }`, first match wins; params compare only listed keys — URL query for GET/DELETE, urlencoded body for POST with body precedence). Two hard rules: a registered-but-unmatched rule array must answer empty-success + loud warning, never fall through to the network (param typos must not become real-backend writes); pagination contracts via per-page `start`/`offset` rules — seed page 1 at exactly the page size so the client's "loaded end" flag doesn't suppress the page-2 request, then assert append-not-replace.
- **`code-rules.md` — "Prove the call, not just the pixels."** Write interactions with optimistic UI must pair the UI assertion with request proof (`waitForRequest` armed before the click).
- **`code-rules.md` Auth & Session — login-success hybrid.** Route mocks can't mint server-issued session cookies; mock the login POST for form behavior, seed cookies through the project's sanctioned test seam, then assert the full post-login redirect chain — with a WHY comment in the spec.
- **`e2e-reviewer` #22 — Optimistic UI Without Call Proof (P1, LLM).** Interaction test asserts only optimistically-updated UI state; passes even with the API wiring deleted. Require `waitForRequest`/route-hit proof for every write interaction.
- **`e2e-reviewer` #23 — Fixture Ignores Conditional Render Guards (P2, LLM).** Type-correct fixtures aren't render-correct: components self-hide on field+view-state combos (e.g. `liked: false` items in a Liked view return `null`), producing empty-UI "flake" or wrong-reason negative passes. Read the item component's early returns before seeding.
- **`playwright-debugger` — accessible-name collision guidance.** On role+name strict-mode violations between semantically different controls (tab vs toggle sharing a name), disambiguate by the semantic attribute (`[aria-pressed]` / `:not([aria-pressed])`) instead of downgrading to `.nth()`.

### Changed
- Catalog count 22 → 24 across SKILL.md Quick Reference, README, and plugin description.

## [1.4.2] - 2026-06-05

### Added
- **Cross-host convergence contract** (motivated by a 10-repo Claude-vs-Codex comparison where verdicts agreed 9/10 but `Real P0` counts varied by host discretion): Phase 1 "Deterministic mode" — canonical scanner invocation with download tiers pinned off and a mandatory tier-coverage statement in the report; Phase 2 "Counting contract" — `Real P0 = N` is the number of distinct surviving `file:line` entries after FP elimination and consolidation; Phase 2 "Bounded opening-token sweep" — the scanner-missed-shape hunt is a fixed 5-family token checklist instead of open-ended exploration.

### Fixed
- **`scan.sh` `#3b` matches every `uncaught:exception` handler opening** (single- or multi-line body). The old `.*false` suffix only caught one-line `() => false` and missed 51 multi-line blanket suppressors in one OSS Cypress suite — Phase 1 reported 0 P0 on the corpus's richest #3b surface. Blanket-vs-scoped classification stays with Phase 2 (handler containing `expect()` is exempt). Cross-host verification (Codex/omx, 10 repos) surfaced the gap: a host that trusted the mechanical zero stopped early and returned the only verdict mismatch of the run.
- **`e2e-reviewer/SKILL.md` Phase 2 zero-P0 floor.** Explicit MANDATORY rule: Phase 1 reporting 0 P0 does not end the review — LLM-only checks and a scanner-missed-shape sweep always run.
- **`AGENTS.md` Codex install path corrected** to `~/.agents/skills/` (empirically verified discovery path; was documented as `~/.codex/skills/`).

## [1.4.1] - 2026-06-05

Research-driven update: folds 2025–2026 community/official findings on AI-generated E2E tests (Playwright Agents planner/generator/healer model, seed-spec + conventions-doc leverage, network determinism, storageState auth) into the generator pipeline and reviewer catalog.

### Added
- **`playwright-test-generator` Step 5b — Conventions & Seed Artifacts.** On first run in a project (no testing-conventions doc detected in Step 1), the pipeline now scaffolds a project-adapted E2E section into root `AGENTS.md` (+ `CLAUDE.md` pointer) and designates the best generated spec as the seed to copy. Rationale: across practitioner reports, a conventions doc + seed spec is the highest-leverage artifact for keeping AI-generated tests consistent across sessions and agents — without one, every session re-derives locator/auth/mocking decisions and drifts. New `conventions-template.md` carries the fill-from-observed-reality template.
- **`playwright-test-generator` — `playwright-agents.md` interop reference.** When to keep this pipeline vs hand off to Playwright ≥ 1.56 first-party agents (`npx playwright init-agents --loop=claude`), how Step 5b artifacts feed the planner/generator, and why projects pinned below 1.56 (e.g. pixel-perfect visual baselines that an upgrade would invalidate) should not upgrade just for agents.
- **`code-rules.md` — Network Determinism section.** Per-endpoint strategy table: write/credential paths must be stubbed (`page.route()`) — generated tests must never create real accounts or hit real payment providers; stable first-party reads may stay real; at most one designated real-backend smoke spec. Includes the shared proxy route-mock helper pattern (match on decoded routing param, e.g. `/api/request?cmd=`) and the fall-through write-leak caveat.
- **`code-rules.md` — Auth & Session section.** Authenticate once programmatically + `storageState` reuse; UI login only in login-flow specs; manually captured session files forbidden as hard dependencies.
- **`e2e-reviewer` #20 — Unmocked Real-Backend Writes (P1, LLM).** Spec drives signup/login/checkout/mutation with no route stub in spec or fixtures — data pollution, rate-limit flakiness, PII exposure, backend-state-dependent results. Exemption: one `// JUSTIFIED:` designated real-backend smoke spec.
- **`e2e-reviewer` #21 — Manually-Captured Session-File Dependency (P2, LLM).** `storageState` JSON produced only by a manual capture script — absent on fresh clones/CI, silently expires. Session state must be reproducible from code.

### Changed
- **`playwright-test-generator` selector priority** — added `getByPlaceholder` as tier 3 and a label-existence precondition on `getByLabel`: label-less inputs (placeholder/title only) are common in real apps and `getByLabel` on them matches nothing. Step 3 now includes an accessible-name reality check against the live snapshot before locators enter the mapping table.
- **`playwright-test-generator` Step 3 — programmatic-auth guidance** for generated tests (API login / setup project + `storageState`), aligned with reviewer #21.
- **`playwright-test-generator` Step 7 / `playwright-debugger` F2·F12 — heal by intent.** Selector-failure fixes now re-resolve the element a step semantically targets from a fresh snapshot at the highest stable locator tier, instead of patching the old selector string (the approach Playwright's healer agent uses).
- Catalog count 20 → 22 across SKILL.md, README, and plugin description.

## [1.4.0] - 2026-06-04

### Added
- **`scan.sh` — E2E content scoping for FP-prone patterns.** Tier 3 hits for `#3`, `#4a`, `#4b`, `#4f`, `#4g`, `#15` (P0) and `#9`, `#6`, `#5b`, `#19` (P1) are now kept only when the containing file carries a real Playwright/Cypress marker (`@playwright/test` import, `async ({ page` fixture destructure, direct `page.<api>` usage, or `cy.<cmd>(`). Eliminates Vitest/Jest/RTL unit-test bleed-through — the dominant false-positive root cause observed across a 110-repo OSS validation corpus (52/77 review reports flagged it). Measured: one design-system repo's `#4f` dropped 107 → 0, a component library's `#4g` token collisions (`<Tooltip timeout={0}>` props) 3 → 0, with zero loss of confirmed real P0 signals on control repos.
- **`scan.sh` — ESLint watchdog.** The Tier 1 `npx eslint` invocation now runs under a kill-after-timeout guard (`E2E_SMELL_ESLINT_TIMEOUT_SECS`, default 300s; pure bash — macOS has no `timeout(1)`). The npx auto-download could previously hang indefinitely on large repos or constrained networks, stalling the whole scan.
- **ast-grep rules — vendored/build-artifact `ignores`.** All five detection rules now skip `node_modules`, `dist`, `build`, `.next`, `out`, `coverage`, `public`, minified bundles, and `evals/files` — mirroring Tier 3's rg glob excludes (previously Tier 2 had no such scoping and could report hits in vendored `dist/` bundles).
- **`e2e-reviewer/SKILL.md` 4.2 — two new PR-culture points.** (9) Framework self-test gray zone: hits in framework/component-library test fixtures are mechanically real but carry different PR-worthiness — lead with the smallest high-signal subset. (10) PR-worthiness triage: a finding justifies an upstream PR iff at least one real P0 is a silent-always-pass/race defect in a user-facing E2E spec; fixture-only, unit-scope, or cosmetic findings do not — the empirical KEEP/DELETE bar from the 110-repo validation.
- **`e2e-reviewer/SKILL.md` Phase 2 — three codified FP rules.** `#4b` static-shell vs dynamically-injected decision rule; `#5a` action-gate vs assertion-gate rule (`if`-body without `expect()` gates setup, not verification); `#8a` note that the scanner now pre-filters continuation lines.
- **Committed eval fixtures — all four skills.** `skills/*/evals/files/**` (28 files: 12 e2e-reviewer specs/POMs, 4 Playwright-reporter JSON and 4 mochawesome JSON debugger reports, 8 generator project-scaffold files) now exist in-repo so every `evals.json` assertion's exact `file:line` reference is reproducible from a fresh clone. The previous `.gitignore` rule treating fixtures as local-only mock data is reversed; the scanner excludes `**/evals/files/**` in all three tiers so the intentional anti-patterns cannot fail the repo's own smell-scan CI gate.

### Fixed
- **`scan.sh` — Tier 1 ESLint never worked via npx and its failure silently disabled Tier 2/3 coverage.** Two stacked bugs: (1) the invocation used `--no-eslintrc`/`--ext`/inline-JSON `-c`, all removed in ESLint v9+, so the npx path always exited 2; (2) the success check only grepped stdout for `error|warning` and set the `*_lint_done` coverage flags unconditionally — a crashed Tier 1 therefore reported "no findings" AND made Tier 2/3 skip `#7 #9 #15 #16` (`#7 #9b` Cypress). Rewritten: generated flat `eslint.config.mjs` with absolute plugin paths resolved inside the npx env (npm ≥9 sets no NODE_PATH), `@typescript-eslint/parser` for TS specs, and an exit-code gate — coverage flags are only set when eslint exits 0/1; any rc ≥ 2 falls through loudly to Tier 2/3. Verified end-to-end on Playwright (`no-focused-test`, `missing-playwright-await`, `no-wait-for-timeout`) and Cypress (`mocha/no-exclusive-tests`, `cypress/no-unnecessary-waiting`).
- **`scan.sh` — `// JUSTIFIED:` suppression implemented in Tier 3** (was documented in SKILL.md/README but never implemented). A hit is dropped when the marker is on the hit line or anywhere in the contiguous `//`-comment block immediately above it (≤5 lines). Block-level placements remain Phase 2 responsibility.
- **`scan.sh` — Cypress framework detection over-match.** The bare `cy\.` alternation matched `agency.`/`privacy.` etc., triggering spurious eslint-plugin-cypress downloads on non-Cypress repos; now anchored to real Cypress commands (`cy.visit|get|contains|…(`).
- **`scripts/validate-evals.sh` — fixture-existence gate.** Every path in an eval's `files[]` must now resolve on disk, CI-enforcing the committed-fixtures contract.
- **Re-adjudication round (previously-rejected findings re-verified):** e2e marker set extended with Playwright-only idioms (`test.describe(` family, fixtures-module imports, column-0 `page.`) after a probe proved POM-only specs were being dropped; `#9c` tightened to the real API shapes (`waitForLoadState('networkidle')` / `waitUntil:`) and e2e-scoped; `#4c-4e` regex now matches state reads with arguments (`getAttribute('src')` was unmatchable with the empty-parens form); watchdog now kills the npx/node descendant tree, not just the subshell; `#9b`/`#9c` sub-variants documented in the SKILL.md/README pattern rows; Phase 2 skip-list includes `#19`; `#3b` true-positive + scoped-handler guard added to the Cypress eval fixture.
- **`scan.sh` — rg glob precedence bug.** ripgrep gives precedence to later globs; the basename include glob was declared last, silently re-including files inside the `!dist/**`-style excluded directories whenever the target repo did not gitignore its build output (the long-standing "vendored `dist/cli.js` hits" symptom). The include glob now comes first so every negation wins.

### Changed
- **`scan.sh` `#8a` — previous-line continuation filter.** A hit is dropped at scan time when the preceding non-blank line ends with `(` or `,` — the matched line is an argument inside a multi-line `await expect(\n  page.locator(...)\n).toBeVisible();`, not a dangling statement. Kills the single biggest FP source (measured: 520 → 3, 323 → 0, 71 → 0 on three monorepos) while still catching semicolonless dangling locators. The argument matcher also accepts one level of nested parentheses (`getByRole('button', { name: 'Save (draft)' })`). The Phase 2 previous-line backstop remains for residual shapes.
- **`scan.sh` `#15` regex excludes `expect(await …)`** — those are one-shot reads (`#4c-4e` territory), not missing-await-on-expect; previously both patterns could claim the same line. Uses a possessive `\s*+` before the negative lookahead so whitespace variants (`expect( await …)`) cannot backtrack around it.
- **`scan.sh` — eval-fixture exclusion is conditional.** `**/evals/files/**` is excluded from normal scans but re-included automatically when the scan root itself is inside an `evals/files` tree, so the bundled fixtures can be self-tested directly.
- **`evals.json` — +4 assertions** covering the two scanner behavior changes (one true-positive and one false-positive guard each for the `#8a` trailing-`;` rule and for E2E content scoping).
- All four skill `SKILL.md` files and the three manifests bumped to `1.4.0` in lock-step; `scripts/ci/test-parity.sh` version constants updated.

### Security
- No security-relevant changes; scanner still performs no writes to the target repo.


## [1.3.4] - 2026-06-01

### Added
- **`e2e-reviewer/SKILL.md` — new anti-pattern `#19` Module-Level Mutable State In Test Utilities** (`P1`, grep + LLM). Catches top-level `let X = …` declarations in test utilities, helpers, and POMs — state that survives across tests within a Playwright/Cypress worker and across retries, breaking the "unique" contract counter-based identifiers were supposed to provide. Surfaced by the Zeppelin `fix/e2e-flaky-final` review where `let testNotebookNameSequence = 0;` collided under `workers > 1`. Phase 1 grep (`^let\s+`, glob `*.{ts,js,tsx,jsx,cy.ts,cy.js}`) flags every column-0 `let`; Phase 2 LLM filter SKIPS pure type declarations (`let page: Page;` reassigned in `beforeEach` — idiomatic Playwright fixture) and only confirms hits that carry an initializer. Suppress with `// JUSTIFIED: [reason]` for intentionally shared worker-scoped state. Fix pattern documented inline: derive uniqueness from `Date.now()` + `Math.random().toString(36).slice(2, 8)`, use `testInfo.workerIndex`, or move state into `test.beforeEach`.

### Changed
- **`e2e-reviewer/SKILL.md` — extended `#11` YAGNI scope from Page Objects to Page Objects + Utility Modules.** The procedure now lists exported symbols of `utils.ts` / `helpers.ts` / `fixtures.ts` alongside POM members and applies the 2+ call-site threshold uniformly. The rationalization for the extension is the same one as the original POM scope — single-use indirection adds maintenance cost without reuse benefit. Common new patterns explicitly enumerated: single-use auth helpers, single-use REST helpers, single-use waits. The `Rule` row clarifies that utility-module helpers used only inside their own module should drop the `export` keyword.
- **Pattern count `19 → 20` across all parity surfaces** — frontmatter description ("Reviews 20 anti-patterns"), Quick Reference table (now 20 rows), Pattern Reference text, `docs/e2e-test-smells.md` P1 table, `README.md` Skill 2 description + Standalone Scanner blurb + P1 quick-reference table, `AGENTS.md` (pattern IDs `#1`–`#19` plus `#3b`; `20 Patterns table` in the editor guidance), `scripts/ci/review.sh` Check 3c QR row-count guard, `scripts/ci/review.sh` Check 5 frontmatter phrase-count guard, `scripts/ci/test-parity.sh` Case 3c expected substring, `skills/e2e-reviewer/scripts/scan.sh` Tier 3 banner. The `module-level mutable state in test utilities` phrase is appended to the P1 section of every manifest description (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`) so the severity-grouped parity check stays green.
- **`evals.json` — added eval id `8`** covering `#19` true-positive flagging plus four false-positive guards: pure type declarations, JUSTIFIED-marked worker-scoped state, indented locals inside function bodies, and the canonical fix suggestion. Eval count `7 → 8`.
- All four skill `SKILL.md` files and the three manifests (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`) bumped to `1.3.4` in lock-step per the cross-host parity contract. `scripts/ci/test-parity.sh` Cases 8 and 12 updated to mutate the new version string.

### Rejected
- **`#19` Debug Console Output In Test Code** was prototyped as a third addition and rejected before commit. `console.log` / `console.info` / `console.warn` / `console.debug` in spec, POM, or utility files do pollute the framework reporter output, but the harm is purely cosmetic — they cannot turn a real failure into a silent pass, which is the rule-set's defining concern. ESLint's `no-console` rule covers the same ground in a single line of config, and adding the pattern would have widened the scope of `e2e-reviewer` into general TypeScript cleanliness territory and diluted its identity. The Zeppelin PR cleanup that motivated the proposal was PR hygiene, not a test-correctness fix. Decision recorded here so the pattern is not re-proposed without new evidence of silent-pass harm specific to Playwright/Cypress.

### Verified
- `bash scripts/ci/ci-local.sh` — Review parity 10/10, Drift smoke 12/12, Security clean, E2E smell scan 0 hits against the repo itself.
- Bundled scanner verified against a synthetic fixture: 1 true-positive flagged (`let testNotebookSequence = 0;` in a utility module), 3 expected false-positive candidates surfaced for Phase 2 LLM to filter (two pure type declarations + one JUSTIFIED-marked worker-scoped state).

## [1.3.3] - 2026-05-20

### Security
- **`playwright-debugger/SKILL.md` — tightened external-command guidance** to reduce shell-injection and unintended-download risk surface flagged by SAST scanners:
  - `gh run download` now uses an explicit `$RUN_ID` variable plus `-D playwright-report` destination, with a documented prohibition on downloading artifacts from forked-PR runs or arbitrary URLs.
  - `find` is restricted to regular files (`-type f`) under `playwright-report/`; `unzip` arguments are always quoted; trace-derived strings must never be used unquoted as filenames or shell arguments.
  - `npx playwright test` invocations switched to `npx --no-install playwright test` so the agent uses the project-pinned Playwright instead of auto-installing.
- **`playwright-test-generator/SKILL.md` — narrowed browser navigation and disabled `npx` auto-install**:
  - `browser_navigate` calls must stay under the detected/approved `baseURL`; off-origin links discovered in page content, error messages, or test data must not be followed.
  - `npx playwright codegen`, `npx playwright test`, and `npx tsc --noEmit` all switched to `npx --no-install …` so missing packages are surfaced to the user rather than silently fetched from npm.
- **`e2e-reviewer/SKILL.md` — removed external-action suggestion** in the cycle-decision section ("file an issue against the upstream repo" → "document them in the review report"); avoids encouraging out-of-band state changes during a review pass.

### Changed
- All four skill `SKILL.md` files and the three manifests (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`) bumped to `1.3.3` in lock-step per the cross-host parity contract.

## [1.3.2] - 2026-05-20

### Changed
- **Discovery metadata refresh** — README, Claude plugin, Codex plugin, and Claude marketplace surfaces now describe the bundle as an AI agent testing toolkit for E2E test automation, Playwright test generation, Cypress test review, flaky test root-cause analysis, false-positive detection, and test smell scanning. Added matching discovery keywords to the Codex and Claude marketplace manifests.
- **`e2e-reviewer` frontmatter description length** — shortened the `SKILL.md` description to stay under the 1024-character skill-loader limit while preserving the P0/P1/P2 pattern phrase order required by CI.
- All four skill `SKILL.md` files and the three manifests (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`) bumped to `1.3.2` in lock-step per the cross-host parity contract.

### Fixed
- **Installed skill loader warning** — `e2e-reviewer` no longer exceeds the loader description limit after reinstalling from this release.

## [1.3.1] - 2026-05-20

### Added
- **Codex plugin `interface` schema validation** — `scripts/ci/review.sh` and `scripts/ci/pre-push-security.sh` now enforce the Codex-specific block in `.codex-plugin/plugin.json`: `displayName`, `shortDescription`, `longDescription`, `developerName`, `category`, `websiteURL`, `brandColor` must be non-empty strings; `capabilities` must be a non-empty string array; `defaultPrompt` must contain 1–3 prompts of 1–128 characters each (matches Codex's display limits). `skills` must be a relative path starting with `./` and must expose exactly the four `skills/<name>` directories. Catches drift where one host's manifest is bumped without the other. The validator lives in `scripts/ci/lib/validate_codex.py` and is imported by both shells (single source of truth — no copy-paste drift between the two CI gates).
- **SKILL.md ↔ manifest version parity check** — `scripts/ci/review.sh` now reads each skill's `metadata.version` from its YAML frontmatter and fails if it does not match `.claude-plugin/plugin.json` `version`. Closes the gap that let `skills/playwright-test-generator/SKILL.md` stay on `1.3.0` while the other three SKILL.md files and all three manifests were bumped to `1.3.1`. Without this check, lock-step bumps could silently miss individual SKILL.md files.
- **Drift smoke Case 10 (defaultPrompt) and Case 12 (SKILL.md version)** — `scripts/ci/test-parity.sh` now mutates the Codex `defaultPrompt` array to 4 entries (confirms the `≤3` guard fires) and bumps a SKILL.md frontmatter version out of sync with the manifest (confirms the new parity check above fires).
- **`E2E_SMELL_NO_AST_GREP_DOWNLOAD=1`** — opt-out env var that disables the `npx --yes @ast-grep/cli` fallback in `skills/e2e-reviewer/scripts/scan.sh` Tier 2 (matches the existing `E2E_SMELL_NO_ESLINT_DOWNLOAD=1` escape hatch). Documented in `README.md` Standalone Scanner section.
- **Prompt-injection safety section in all three browsing/reporting skills** — `playwright-debugger/SKILL.md`, `cypress-debugger/SKILL.md`, and `playwright-test-generator/SKILL.md` add an explicit "untrusted data" section. Test titles, error messages, DOM snapshots, AT-SPI trees, console output, network responses, screenshots, videos, and target-project source code may contain attacker-controlled text and must not be executed or followed as instructions. The generator's block covers Step 3 (browser exploration via agent-browser) and Step 6 (e2e-reviewer + YAGNI audit reading target source code) in addition to the report-reading surface the two debuggers already had.

### Fixed
- **`cypress-debugger` F11 README drift** — `README.md` Skill 4 table still listed F11 as "Async Order Assumption" with a `Promise.all`-flavored signal, contradicting v1.3.0's redefinition to "Command Queue / Intercept Race" (`cy.intercept` registered after the request fires, `.then()` chain order swap, parallel `cy.request()` race against an unfinished `cy.visit()`). README updated to match `cypress-debugger/SKILL.md:74`.
- **`e2e-reviewer/SKILL.md` Suppression section consistency** — the standalone `## Suppression` block at the end of the file said "Each individual flagged line needs its own `// JUSTIFIED:` — a comment higher up in the block does not count", contradicting Phase 1 (which explicitly allows JUSTIFIED above the enclosing call/block or above a multi-line chain's starting expression). Rewrote the standalone block to enumerate the same three positions Phase 1 uses, with the wording "enclosing call/block" aligned word-for-word with Phase 1.
- **`skills/playwright-test-generator/SKILL.md` left behind on v1.3.0** — the lock-step bump claim in v1.3.1's `### Changed` section was previously false for this file. Now `1.3.1` like the other three SKILL.md files and the three manifests. Caught by the new parity check above; absent the check, this would have shipped as a silent CHANGELOG lie.
- **`scripts/ci/pre-push-security.sh` hardcoded-path scope blind spot** — initial v1.3.1 narrowing to `scripts/` + `skills/` removed `.claude-plugin/`, `.codex-plugin/`, and `docs/` from the scan. A leaked `/Users/...` path in any plugin manifest would have shipped directly to every plugin user. Scan roots now include the two plugin manifest directories. (Manifests are small enough that there is no FP risk; docs remain excluded because `~/` and `example` placeholders are intentional there.)
- **`scripts/ci/test-parity.sh` cleanup-trap brittleness under `set -euo pipefail`** — the cleanup loop ran `mv "$b" "$f"` without `|| true`, so a single failing `mv` would abort the loop and leave the remaining `.parity-backup` files on disk. Restoration is now best-effort.
- **Codex `interface` validator duplication** — the ~30-line schema-check block previously existed verbatim in both `scripts/ci/review.sh` and `scripts/ci/pre-push-security.sh`. Without a CI guard, the two copies could drift when the Codex display spec changed (prompt limit, required keys). Extracted to `scripts/ci/lib/validate_codex.py`; both shells now import it. See `### Added`.
- **`scripts/ci/test-parity.sh` `restore()` unbound-variable risk** — under `set -euo pipefail`, the rebuild loop iterated `"${BACKUPS[@]}"` without the `:-` default. Aligned with the cleanup trap at line 22 (`"${BACKUPS[@]:-}"`).
- **`scripts/validate-evals.sh` rewritten in Python** — was Ruby while every other CI script uses `python3`. The previous Ruby version only worked because `ubuntu-latest` GitHub Actions runners happen to preinstall Ruby; the new version uses the same `python3` already required by `pre-push-security.sh` and `review.sh`.
- **`skills/e2e-reviewer/scripts/scan.sh` Cypress eslint args** — the `try_eslint` cypress branch built the `eslint-plugin-mocha` flag via an inline `$(... && printf '-p\neslint-plugin-mocha\n')` that depended on bash word-splitting `\n`-delimited subshell output into array fields. Replaced with an explicit `if [[ "$plugin" == "cypress" ]]; then npx_args+=(-p eslint-plugin-mocha); fi` so the array build is unambiguous.
- **`.github/workflows/e2e-smell-scan.yml` ast-grep version pin** — `npm i -g @ast-grep/cli` was unversioned and would silently break Tier 2 on a major release. Pinned to `^0.39` (the 0.x line ast-grep is currently on).

### Changed
- All four skill `SKILL.md` files and the three manifests (`.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`) bumped to `1.3.1` in lock-step per the cross-host parity contract.

## [1.3.0] - 2026-05-16

### Added
- **Bundled scanner inside the skill** — moved `e2e-smell-scan.sh` and the `ast-grep-rules/` directory from `scripts/` to `skills/e2e-reviewer/scripts/`. Now installed via `npx skills add` automatically — no separate clone needed for users to invoke the scanner from the agent runtime.
- **3-tier scanner integration** — `skills/e2e-reviewer/scripts/scan.sh` now runs in priority order: (1) `eslint-plugin-playwright` / `eslint-plugin-cypress` when locally installed in the target project (AST-based, lowest FP rate), (2) `ast-grep` Tree-sitter rules for FP-prone patterns (`#15`, `#4ce-state-bool/text/count`, `#4f`), (3) bundled `ripgrep` regex as universal fallback covering all 19 patterns including gaps the eslint plugins miss (`#3b` Cypress `uncaught:exception` blanket, `#4g` `{timeout:0}.should("not.exist")`). Output groups results per tier with framework auto-detection.
- **Phase 4 (Applying Fixes) in `e2e-reviewer/SKILL.md`** — `4.1` Canonical Replacements table (Playwright + Cypress + RTL/Vitest sub-tables with jest-dom prereq check), `4.2` Band-Aid Awareness with HIGH/MEDIUM/LOW likelihood per pattern + mandatory pre-removal procedure for `force:true` after readiness check, `4.2` PR-culture cross-check section (8 numbered points: when to invoke, CI execution check, canonical form discipline, one mental migration per PR, attribution verification, etc.), `4.3` Cascade cleanups, `4.4` Empirical cycle-count rule (default 2, condition-based STOP), `4.5` Avoid scope creep with budget interpretation rule.
- **`scripts/verify-fixes.sh`** — post-bulk-fix verification (TypeScript static check + ast-grep detection of sed artifacts: double await, empty `expect()`, orphan `.then()` after web-first migration). Catches the failure modes regex-class fixes can introduce.
- **Phase 0 framework-detection guards** — explicit warnings against false signals: `nx.json` `e2eTestRunner` field is a generator default (real case observed where Cypress was deleted in a merged PR but the field remained), `package-lock.json` cached transitive deps, `.spec.ts` filename alone (could be Jest unit). Inspect imports first.
- **Phase 2 retry-wrapper skip rule** — `expect(() => ...).toPass(...)` (Playwright) and `expect.poll(() => ...)...` callbacks re-run the body until it passes; one-shot reads / unawaited expects inside are NOT silent-always-pass. SKIP `#4c-4e`, `#4h`, `#15`, `#16` hits inside these wrappers. Distinct from the existing `Promise.all([])` skip rule.
- **`#3b` Cypress `uncaught:exception` Phase 2 distinction** — handlers that contain an `expect(err.message.includes(...))` call are *scoped negative-regression tests* (asserting on error properties), not blanket suppression. NOT P0.
- **Phase 3 Coverage Gap categories expanded** — added Race/concurrent (optimistic-update rollback, double-click submit, in-flight request when navigating away) and Responsive/device (mobile viewport, touch vs hover, locale formatting/RTL) on top of error paths / edge cases / accessibility / auth boundaries. Triage rule: gaps interacting with a P0 finding are highest value.
- **`cypress-debugger` F11 redefinition** — was "Async Order Assumption" (Playwright-style `Promise.all` model), redefined as "Command Queue / Intercept Race" matching Cypress's actual chain semantics: `cy.intercept` registered after the request fires, `.then()` chain order swap, parallel `cy.request()` race against an unfinished `cy.visit()`.
- **`cypress-debugger` F13 expansion** — covers blanket `cy.on('uncaught:exception', () => false)`, `.catch(() => {})` / `.catch(() => false)` on POM helpers, and explicitly excludes scoped negative-regression tests (handler asserting on error properties).
- **`playwright-debugger` Prereq #3 — CI artifact local repro** — concrete `gh run download` + `--trace=retain-on-failure --video=retain-on-failure` recipe, `PLAYWRIGHT_BASE_URL` env mirroring, and short-circuit hypothesis (locally pass + CI fail → F7/F8) so debuggers don't waste cycles trying to repro environment-specific failures.
- **README — "Quick Example" section** — real findings from a typebot.io scan showing exact `[P0] file:line — # rule` output shape so first-time visitors see what the skill produces.
### Changed
- **`e2e-reviewer/SKILL.md` Phase 1 simplified** — replaced the 50-line `Grep tool` 5-batch parallel dispatch instruction (referencing `references/grep-patterns.md`) with a 12-line `bash <skill-base>/scripts/scan.sh <test-dir>` invocation. Scanner is now the runtime source of truth; `references/grep-patterns.md` becomes an ID-meaning reference for Phase 2 / debugger lookup. Reduces dispatch errors and makes scanner improvements (eslint integration, ast-grep tier) automatic from the agent's perspective.
- **README structure** — Install moved up to right under the 4-skill bullet (was 4th major section); FAQ and Compatibility sections removed (FAQ content was redundant with the rest of the doc; Compatibility duplicated the per-skill descriptions). 437 → ~310 lines.
- **`e2e-reviewer/SKILL.md` anonymized internal references** — replaced specific repo names (posthog, typebot, rocket-chat, affine, etc.) with generic descriptors ("a SQL editor scene in an analytics product", "an OSS Playwright suite", "two large monorepos"). The empirical numbers (cycle convergence %, before/after counts) preserved as evidence; only the provenance labels (v1/v3/v4 trial markers) anonymized.
- **`scripts/ci/review.sh`** — markdown link check excludes `testbed/`, `node_modules/`; pattern-parity Check 1 `scan_text` source path updated to `skills/e2e-reviewer/scripts/scan.sh`; orphan check kept README-only (CONTRIBUTING.md ended up not shipping after the audit pass).
- **`scripts/ci/pre-push-security.sh`** — all grep/find calls now exclude `testbed/` so external OSS clones don't trigger false-positive blockers (eval(), /tmp paths, hardcoded user-home paths) on this repo's CI.
- **`.github/workflows/e2e-smell-scan.yml`** — collapsed to a single scanner step (was eslint + ripgrep + ast companion in 3 separate steps); the bundled scanner now invokes all 3 tiers internally.

### Removed
- **README FAQ section** — 7 questions, mostly redundant with the body content. ESLint-complement positioning absorbed into Standalone Scanner; suppression guidance also moved there; framework-scope answer moved to `docs/framework-scope.md`.
- **README Compatibility section** — duplicated the per-skill "When to Use" / "Usage" sections and the framework-detection details.
- **`docs/agent-compatibility.md`** — duplicated the README Install section after the cleanup; the Compatibility Rule sentence (host-agnostic skill phrasing) moved into the Skills Conventions block in `AGENTS.md`.
- **`docs/evals.md`** — eval-running rules folded into `AGENTS.md` "When You Edit Skills" #3 (one true positive + one false-positive guard per new assertion).
- **`docs/oss-validation-playbook.md`** — 318-line maintainer-internal procedure deleted. Most content was either a one-time validation campaign procedure or duplicated `e2e-reviewer/SKILL.md` Phase 4. The two genuinely portable bits were preserved: BSD vs GNU sed quirks moved to `skills/e2e-reviewer/scripts/scan.sh` header comment; no-side-effect rule for OSS validation moved to `AGENTS.md` "What Not to Do".
- **`CONTRIBUTING.md`** — also deleted as part of the same audit. The "Quick start" was a duplicate of `AGENTS.md` "Verification gate"; the eval procedures collapsed into `AGENTS.md` "When You Edit Skills" #3.
- **CLAUDE.md preamble** — trimmed to a single `@AGENTS.md` import line. The 5-line preamble explaining why the file existed was decorative; the import is the load-bearing piece for Claude Code's auto-context.
- **`scripts/e2e-smell-scan-ast.sh`** — separate ast-grep companion deleted; logic merged into the bundled `skills/e2e-reviewer/scripts/scan.sh` Tier 2 block.
- **Mandatory pre-removal Procedures 2 + 3** — `waitForTimeout` `git blame` cascade procedure and `if (await x.isVisible())` rg-context procedure were never used in the 13-repo OSS validation runs (subagents reliably distinguished band-aids via Phase 2 LLM judgment alone). Procedure 1 (`force:true` after readiness check) retained because it explicitly references the SQL-editor anti-example that recurred in two trial rounds.

### Fixed
- **`e2e-reviewer/SKILL.md` `#7 Focused Test Leak` severity tier** — single-test-file `.only` was previously P0 ("CI silent disaster"). Reality: in a 1-test file, `.only` has no behavior change. Tiered into P0 (file with ≥2 declarations — non-focused tests silently skip) and P1 (singleton `.only` — debug leak that becomes load-bearing if anyone adds a 2nd test). Phase 2 LLM downgrades singletons.
- **`e2e-reviewer/SKILL.md` `#15`/`#16` Locator/Page subject confirmation** — Phase 1 grep flagged any line starting with `expect(` or `page.locator(...).action(`. Phase 2 now confirms the subject is a Locator/Page before flagging P0; non-Locator subjects (booleans, primitives, custom service methods like `expect(await myService.isEnabled()).toBe(true)`) explicitly skipped.
- **`e2e-reviewer/SKILL.md` Phase 2 multi-line continuation skip for `#8a`** — the regex `^\s*page\.(locator|getBy*)(...)` flags continuation lines inside multi-line `await expect(\n  page.locator(...)\n).toBeVisible()` chains as dangling locators. Phase 2 now skips when the previous non-empty line ends with `(` or `,`.
- **`e2e-reviewer/SKILL.md` Phase 2 `Promise.all` skip for `#16`** — actions inside `Promise.all([waitForEvent(...), action()])` arrays are awaited by the wrapping `Promise.all`; explicit `await` on the array element is wrong syntax. Phase 2 skips these hits.
- **AGENTS.md parity-surface list** — referenced "README.md Quick Reference table" that doesn't exist; the list also missed `skills/e2e-reviewer/scripts/scan.sh`. Updated.
- **AGENTS.md `When You Edit Skills` paired-file rule** — said "do not edit `references/grep-patterns.md` without checking that the matching `Phase 1` block in `SKILL.md` still lines up". Phase 1 was rewritten to call `scan.sh` instead of inlining grep tables. Updated to "scan.sh is now the runtime source of truth, grep-patterns.md is an ID-meaning reference".
- **`.gitignore`** — added `.serena/` so Serena MCP tool's local config doesn't get committed.
- **`.codex-plugin/plugin.json` `longDescription`** — corrected stale references discovered during the cross-host audit: removed "OpenCode" from the host list (only Claude Code and Codex are explicitly supported in user-facing surfaces), and updated the standalone scanner path from the old `scripts/e2e-smell-scan.sh` to the current `skills/e2e-reviewer/scripts/scan.sh`.
- **`playwright-test-generator/SKILL.md` Step 4 host-specific phrasing** — generalized "In Codex/OpenCode, stop after presenting the plan" to "In hosts without [a planning mode]" so the instruction holds across all `skills` CLI hosts, not just two named ones.
- **README + `AGENTS.md` Codex install path** — was "register via the Codex marketplace UI (reads `.codex-plugin/plugin.json`)", which was wrong on two counts: (a) Codex's plugin marketplace is a CLI (`codex plugin marketplace add ...`), not a UI, and (b) without an `.agents/plugins/marketplace.json` index the manifest alone is unreachable. After surveying real-world usage (anthropics/skills 135k★ and vercel-labs/agent-skills 26k★ both ship zero `.agents/plugins/marketplace.json`; the `..` path traversal needed for a single-source-of-truth layout is hard-blocked by `codex-rs/core-plugins/src/manifest.rs:421-424`; the `npx skills add -a codex` route already drops the bundle into `~/.codex/skills/` for auto-discovery), we intentionally did NOT ship the native marketplace path. README now points Codex users at the cross-agent CLI route, which is functionally equivalent for skill-only plugins.

### Added (folded from earlier 1.2.2 work; entries below were never tagged)
- **`.codex-plugin/plugin.json`** — added a dedicated Codex plugin manifest (peer to `.claude-plugin/plugin.json`) carrying the Codex-specific `interface` block (`displayName`, `shortDescription`, `longDescription`, `developerName`, `category`, `capabilities`, `websiteURL`, `defaultPrompt[]` per skill, `brandColor`) while pointing to the same shared `skills/` directory used by Claude Code. Both hosts now read from one source of truth for skill behavior with host-specific display surfaces.
- **Manifest version parity CI** — `scripts/ci/review.sh` Check 6 verifies that `.claude-plugin/plugin.json`, the `e2e-skills` entry in `.claude-plugin/marketplace.json`, and `.codex-plugin/plugin.json` share the same `version` string. `scripts/ci/test-parity.sh` Case 8 mutates `.codex-plugin/plugin.json` to assert the parity check fires; Case 9 mutates the Codex description out of order to confirm the existing description-parity loop also covers it.
- **Root `AGENTS.md`** — added a cross-agent canonical contributor guide at repo root following the [AGENTS.md convention](https://agents.md). Auto-loaded by Codex CLI, OpenCode, Cursor, and GitHub Copilot at session start; opt-in via config for Aider (`--read AGENTS.md` or `.aider.conf.yml`) and Gemini CLI (`.gemini/settings.json` `context.fileName`). Covers verification gate, directory layout, pattern/failure-code conventions, framework scope, local development commands, lock-step parity surfaces, cross-host parity rules, and installation paths. CLAUDE.md / agent-specific files can defer to this when present.
- **SKILL.md `license` + `metadata` frontmatter** — added `license: Apache-2.0` and `metadata: { author: voidmatcha, version: "1.2.2" }` to all four `skills/<name>/SKILL.md` files to match the canonical Agent Skills frontmatter shape used by `anthropics/skills` and `vercel-labs/agent-skills`.
- **README SEO/GEO improvements** — added Contents TOC under the intro, a "Comparison with Other Tools" table positioning `e2e-reviewer` against `eslint-plugin-playwright` / Playwright docs / raw grep, and a 7-question FAQ covering common pre-install user questions.

### Added (dev tooling)
- **Testbed for live OSS validation** — added `testbed/` (gitignored) as the canonical location to clone real-world Playwright/Cypress repos against which the skills can be exercised. Clone manually (`git clone --depth 1 <url> testbed/<name>`); then `bash scripts/e2e-smell-scan.sh testbed/<name>` or invoke `e2e-reviewer` on the path.
- **Local-install reinstall script** — `scripts/dev/reinstall-skills.sh` runs `npx skills remove` then `npx skills add <repo-root> --copy` scoped to the four e2e-skills via `--skill <csv>`, so other installed skills are untouched. Uses `--copy` mode (not the default symlink) so that uncommitted local edits in this repo do not leak into the Claude Code / Codex runtime — the installed copy reflects pushed state, not working-tree state. Override the agent list via `E2E_SKILLS_AGENTS` (default at the time of this entry was `-a claude-code -a codex -a opencode`; reduced to `-a claude-code -a codex` in 1.3.0).
- **Pre-push git hook** — `scripts/hooks/pre-push` runs `npx skills update` on every `git push`, refreshing the installed copies so they match HEAD. `scripts/dev/install-hooks.sh` wires the hook in via `core.hooksPath=scripts/hooks` (one-time, opt-in). With `--copy` install + `skills update` on push, pushed code equals installed code, and the working tree can hold WIP edits without affecting the agent runtime.

### Fixed (additional)
- **`e2e-reviewer/SKILL.md` frontmatter YAML parse regression** — description re-introduced `): ` (colon-space) tokens forbidden in YAML plain scalars when the severity-first restructure added phrases like `P0 must-fix (silent always-pass):`. Same failure mode as v0.7.3 (`YAMLException` in gray-matter, skills CLI silently skips the skill). Fix: wrap the description in single quotes. Also updated `scripts/ci/review.sh` Check 5 regex lookahead to accept the closing single quote (`\.(?=[\s']|$)`) and added a stdlib-only frontmatter guard that fails any unquoted `description:` value containing `: `. Drift smoke Case 10 covers the regression.
- **Pattern parity CI check** — added a "Pattern and description parity" section to `scripts/ci/review.sh` that programmatically catches the drift categories surfaced manually across the v1.2.2 audit rounds. Verifies: (1) every pattern id in `grep-patterns.md`, `e2e-smell-scan.sh`, and `docs/e2e-test-smells.md` maps back to a base id in the `e2e-reviewer/SKILL.md` Quick Reference; (1b) every Quick Reference base id appears in `docs/e2e-test-smells.md` (reverse completeness); (2) docs P0/P1/P2 section placement agrees with QR severity (composite severities like `P0/P1` tolerated); (3) README severity-section placement (`#### P0 / P1 / P2`) agrees with QR severity; (3b) `e2e-reviewer/SKILL.md` Review Checklist severity-section placement (`### P0 / P1 / P2`) agrees with QR severity; (3c) Quick Reference has exactly 19 rows and the set of `####` ids across `### P0 / P1 / P2` sections equals the set of Quick Reference ids; (4) `playwright-debugger` and `cypress-debugger` `evals.json` only reference F-codes present in their `SKILL.md` taxonomy; (5) the 19 pattern phrases from the SKILL.md frontmatter (grouped P0 → P1 → P2) appear in order in both `plugin.json` and `marketplace.json` descriptions (with punctuation-tolerant normalization).
- **Drift smoke test** — added `scripts/ci/test-parity.sh` that mutates `grep-patterns.md`, `docs/e2e-test-smells.md`, `README.md`, `e2e-reviewer/SKILL.md`, and `.claude-plugin/plugin.json` in known-bad ways, asserts `review.sh` exits non-zero with the expected error substring, and restores each file from backup. Validates that the parity checks themselves actually catch drift (not just the current state). Wired into `scripts/ci/ci-local.sh` between review checks and the smell scan; gated by `E2E_SKILLS_SKIP_PARITY_SMOKE=1` for parity with the existing skip-flag pattern.
- **Codex/OpenAI metadata** — added `agents/openai.yaml` metadata for all four skills to improve Codex skill discovery and display.
- **README OSS proof section** — documents merged open-source E2E/testing contributions by `voidmatcha` across Cal.com, Storybook, and Element Web.
- **README review surface expansion** — adds broader E2E review guidance for selectors, waits, isolation, network boundaries, auth, accessibility, visual checks, CI diagnostics, and test scope.
- **Standalone E2E smell scanner** — added `scripts/e2e-smell-scan.sh` for agent-free P0/P1 mechanical checks.
- **Eval validator** — added `scripts/validate-evals.sh` to keep skill eval definitions structurally valid.
- **Convention/security CI** — added `scripts/ci/ci-local.sh`, `scripts/ci/review.sh`, and `scripts/ci/pre-push-security.sh` to validate skill metadata, eval metadata, shell syntax, local links, agent manifests, version sync, and high-confidence security patterns.
- **GitHub Action example** — added `.github/workflows/e2e-smell-scan.yml` to run convention/security checks, run the scanner in CI, and upload a report.
- **Open-source docs** — added E2E smell taxonomy, OSS case studies, eval guidance, framework scope, and agent compatibility.

### Changed
- **Namespace rename `dididy` → `voidmatcha`** — replaced legacy GitHub namespace with `voidmatcha` across `.claude-plugin/marketplace.json` (`name`), README install commands, and `docs/agent-compatibility.md`. Author display field `YONGJAE LEE` preserved across the three `author` entries (plugin.json, marketplace.json, .codex-plugin/plugin.json).
- **README installation docs** — added Codex/OpenCode user-skill installation commands.
- **`playwright-test-generator` approval gate wording** — replaced Claude-only planning-mode wording with Claude Code, Codex, and OpenCode-compatible approval instructions.
- **`marketplace.json` keywords** — removed a stale unsupported automation keyword after scope was narrowed to Playwright and Cypress.

### Fixed
- **`e2e-reviewer` JUSTIFIED scope extended to enclosing block and chained calls** — the Phase 1 interpretation rule and `references/grep-patterns.md` both said "Lines where the **immediately preceding line** contains `// JUSTIFIED:` are intentional — skip them". A real-world Zeppelin Angular review surfaced two routine false-positive shapes the rule did not cover: (1) `document.querySelector` inside a `page.evaluate(() => { ... })` or `page.waitForFunction(() => { ... })` callback where the JUSTIFIED comment sits above the *enclosing call*, not above each `querySelector` line; (2) chained Playwright calls split across lines (`page.locator(...)\n  .filter(...)\n  .first()`) where the JUSTIFIED comment sits above the chain's starting expression, not above the `.first()` line. Extended the rule (in `SKILL.md` Phase 1 and the `references/grep-patterns.md` header) to recognize `// JUSTIFIED:` in three positions: immediately preceding the hit, immediately preceding the enclosing callback/block, or immediately preceding a multi-line chain's starting expression. Added a "read 1–3 lines of surrounding context before flagging" reminder so grep-only review output does not become the source of false positives.
- **`e2e-reviewer` #4 multi-URL substring fix guidance** — Fix list said `expect(page.url()).toContain(x)` → `await expect(page).toHaveURL(x)`. A real fix pass converted *consecutive* `expect(page.url()).toContain('A'); expect(page.url()).toContain('B');` calls into a single `await expect(page).toHaveURL(/A.*B/)` — which silently introduces an ordering constraint not in the original substring checks (passes only when A precedes B in the URL). Added explicit guidance to replace each call with its own `await expect(page).toHaveURL(/.../)` and not combine them into one regex with `.*`.
- **`e2e-reviewer` #4 compound boolean expression variant** — the #4 anti-pattern catalogue covered `expect(await el.isVisible()).toBe(true)` but not the equivalent compound form `expect(visible1 || visible2).toBe(true)` where two boolean variables are or'd together inside `expect()`. Added the compound boolean case to the fix list with guidance: prefer locator-level `expect(page.locator('.a, .b')).toBeVisible()` or gate the test with `test.skip()` on the unsupported branch rather than collapsing into a one-shot boolean check.
- **`e2e-reviewer` #10a method-name and fallback-loop exemptions** — `.nth()` / `.first()` / `.last()` had a binary "needs `// JUSTIFIED:`" rule that produced false positives on two routine self-documenting shapes: (a) POM methods whose names already encode positional intent like `getParagraphByIndex(index) { return this.paragraphs.nth(index); }`; (b) fallback-selector loops `for (const sel of fallbackSelectors) { ... locator(sel).first() ... }` where `.first()` means "any match for this candidate selector", not positional. Added explicit exemption bullets to #10a so reviewers skip these shapes without requiring a `// JUSTIFIED:` comment. Also exempted `await expect(items).toHaveCount(1); const only = items.first();` where the adjacent count assertion already documents that exactly one element exists.
- **`e2e-reviewer` #14 scope narrowed to actual auth usage** — #14 Hardcoded Credentials flagged any literal matching `(login|fill|type).*(password|secret|admin)`. This produced false positives on input-behavior tests like `passwordInput.fill('typed text'); await expect(passwordInput).toHaveValue('typed text');` where the literal is test data for verifying form input acceptance, never used as an actual credential. Tightened the rule: only flag literals passed to authentication operations (`loginPage.login(...)`, password fields immediately followed by submit, API auth posts, or fixtures named `validUser` / `testAdmin`). Input-acceptance testing and intentional invalid-creds fixtures with dummy username/password values for negative-path tests are explicitly excluded. Reviewers must read 2–3 lines below a literal to confirm a login/auth call follows.
- **`e2e-reviewer` Phase 2.5 framework-agnostic selector check** — the systemic "CSS-only selectors" row only listed Playwright APIs (`getByRole` / `getByTestId` / `getByLabel` / `getByPlaceholder` / `getByText`). Running on a Cypress project that used `cy.get('[data-cy=...]')` exclusively (a perfectly good user-facing selector strategy) would still hit zero `getBy*` and emit a false-positive P2 finding. Renamed the row to "No stable user-facing selectors" and made the detection rule framework-aware: Playwright keeps the `getBy*` check; Cypress checks zero `[data-cy=]` / `[data-testid=]` selectors and zero `cy.findBy*` (cypress-testing-library) usage.
- **`e2e-reviewer` Review Checklist reframed as Pattern Reference** — the section header `## Review Checklist` plus the intro "Run each check against every non-skipped test" framed the 19-pattern catalogue as a *separate execution phase* placed after Phase 3. Phase 1 / Phase 2 / Phase 2.5 already execute all 19 patterns, so the wording risked LLMs running the full check set a second time as a duplicate pass. Renamed to `## Pattern Reference` with intro "Do **not** re-run these checks as a separate pass — the phases above already cover them. When emitting a finding, consult the matching section here for the canonical Symptom / Rule / Fix wording." CI Check 3b is unaffected (it parses `### P0 / P1 / P2` subsection headers, not the parent heading).
- **`e2e-reviewer` Phase 2 #10 LLM role made concrete** — the Phase 2 LLM Review table row for `#10 Flaky Test Patterns` said "Requires context judgment for nth() and serial ordering", but the Phase 1 grep + `// JUSTIFIED:` mechanical check already handles both `#10a nth/first/last` and `#10b describe.serial`. It was unclear what additional judgment Phase 2 should add. Replaced with an explicit task: verify that any `// JUSTIFIED:` comment on a `#10` hit gives a *concrete* rationale (e.g. "server returns in fixed order") rather than a vague one ("needed for now"); flag if the comment doesn't actually justify the position-coupling or serial dependency. Hits without a JUSTIFIED comment are skipped here — Phase 1 already flagged them.
- **`e2e-reviewer` Output Format heading simplified** — the example finding heading was `## [P0/P1/P2] Task N: [filename] — [issue type]`. There is no "Task" concept anywhere in the Phase 0 / 1 / 2 / 2.5 / 3 workflow — it was a leftover artifact from a previous tasking structure. Simplified to `## [P0/P1/P2] [filename] — [issue type]` and the per-finding sub-heading from `### N-1.` to `###`.
- **`playwright-test-generator` Step 7 attempt categories reframed as heuristic** — the failure handling table had `Attempt 1 → Selector mismatches`, `Attempt 2 → Assertion failures`, `Attempt 3 → Structural issues`. Real failures don't arrive in that order, so the strict per-attempt category mapping was misleading. Reframed as a "Likely cause / Fix" table with explicit note that "the order is heuristic — the real failure dictates which category to try first". The max-3-attempts ceiling and `playwright-debugger` handoff are unchanged.
- **`playwright-test-generator` Step 6 e2e-reviewer P0 loop ceiling** — Step 6 said "P0 issues found: fix immediately, re-invoke `e2e-reviewer`, repeat until 0 P0s" — no maximum attempt count. Unfixable P0s (e.g. an intentional `test.only` left during development, or a `force: true` with no JUSTIFIED rationale that the model can't infer) would loop indefinitely. Capped at 3 fix attempts to match Step 7's max-3-attempts pattern; remaining P0s are listed in the final report and the pipeline proceeds to Step 7 with a warning.
- **`e2e-reviewer` Phase 2.5 deduplication wording made unambiguous** — the No-auth systemic row read "Skip if Phase 2 already reported #12 on every affected file individually — only surface the suite-wide rollup", which could be read as "skip the Phase 2.5 rollup entirely when Phase 2 covers every file". The Deduplication Rule paragraph below it said the opposite (always emit one rollup line; just don't enumerate per-file findings). Reworded the row to "Always emit a single rollup line here; do not enumerate per-file findings — those belong in Phase 2" so the table cell and the paragraph agree.
- **`e2e-reviewer` `#11` Pattern Reference heading aligned with Quick Reference** — Quick Reference shows `#11` as "YAGNI + Zombie Specs" but the Pattern Reference section heading read `#### 11. YAGNI — Dead Test Code`. Body content covers both `11a` POM YAGNI and `11b` Zombie spec files correctly, but the heading dropped the zombie-spec naming. Renamed to `#### 11. YAGNI + Zombie Specs` for grep parity with Quick Reference and `docs/e2e-test-smells.md`.
- **`e2e-reviewer` Phase 0 framework-skip lists made symmetric** — the Cypress-skip list under "If Playwright" was prose (`cy.wait`, `#3b uncaught:exception`) while the Playwright-skip list under "If Cypress" enumerated explicit pattern IDs (`describe.serial`, dangling `page.locator`, `#18`, `#15/#16`, `#17`). Made the lists symmetric with pattern IDs on both sides: `#9b cy.wait(ms)` / `#3b Cypress uncaught:exception` for Playwright reviews, `#8a` / `#10b` / `#15` / `#16` / `#17` / `#18` for Cypress reviews.
- **README Phase 1 grep enumeration** — README "How E2E Reviewer Works → Phase 1" listed the early grep targets as `#3 error swallowing, #5 bypass patterns, #8 missing assertions, #9 hard-coded sleeps, ... and supplementary code-quality checks`. The trailing catch-all hid `#14` Hardcoded Credentials, `#15` Missing await on expect, `#16` Missing await on action, `#17` Direct page action API, and `#18` `expect.soft()` overuse — five grep-detectable patterns reviewers using only the README would not know to look for. Replaced with an explicit enumeration of all grep-phase ids so the README matches the Phase 1 grep tables in `e2e-reviewer/SKILL.md`.
- **`#5` Bypass Patterns composite severity marker** — `#5` is composite (`5a` P0 `evaluate()` DOM bypass / `5b` P1 `nth()` index reliance) but the SKILL.md Review Checklist heading and the README severity row presented it as a single item without disclosing the sub-pattern severity split. Annotated the SKILL.md heading as `#### 5. Bypass Patterns [grep-detectable] (5a P0, 5b P1)` and the README P0 row as `(5a P0, 5b P1)` so reviewers see the split without opening the body. Quick Reference already uses `P0/P1` in the severity cell; CI Check 3 / 3b tolerate composite severities.
- **`e2e-reviewer` SKILL.md frontmatter description compaction** — description was 1538 chars (compared to 461–682 chars for the other three skills) after the severity-first restructure expanded the pattern list. Dropped the parenthetical sub-pattern enumerations (already documented in the body) while keeping the P0/P1/P2 severity grammar Check 5 depends on. New length 1193 chars; trigger phrase coverage preserved.
- **`e2e-reviewer` CI parity hardening — Check 3c** — added a Quick Reference / Review Checklist set-equality check in `scripts/ci/review.sh`. Verifies (a) the Quick Reference table has exactly 19 rows and (b) the set of `####` ids across `### P0 / P1 / P2` sections equals the set of Quick Reference ids. Catches drift where a pattern is added to one place but not the other.
- **`e2e-reviewer` Phase 2.5 `#12` double-report** — Phase 2.5 "No authentication strategy" systemic row duplicated `#12 Missing Auth Setup`. Both were P0 with no rule distinguishing when to report which. Added an explicit suite-level rollup contract: Phase 2 emits one finding per affected file, Phase 2.5 rolls up only when 3+ files share the issue, and a deduplication rule paragraph spells out that Phase 2.5 must not also list every file.
- **`e2e-reviewer/agents/openai.yaml` description alignment** — the Codex manifest description listed "false-passing assertions, missing assertions, flaky selectors, sleeps, auth gaps, POM drift" — a stale curated list that predated the 19-pattern severity taxonomy. Updated to reference the P0/P1/P2 taxonomy with representative pattern examples per severity.
- **`e2e-reviewer` Review Checklist restructured to severity-first organization** — replaced the `Tier 1 (always check)` / `Tier 2 (check when time permits)` / `Supplementary Checks` split with explicit `### P0 — Must Fix`, `### P1 — Should Fix`, and `### P2 — Nice to Fix` sections in both `e2e-reviewer/SKILL.md` and README. The previous Tier/Supplementary structure had two structural problems: (1) "Supplementary Checks" contained three P0 items (`#12` Missing Auth Setup, `#15` Missing await on expect, `#16` Missing await on action) — equally critical silent-pass bugs as the Tier 1 P0s, but the "Supplementary" label made them look optional; (2) `#6` Raw DOM Queries was under Tier 1 "always check" despite being P1 in the Quick Reference, while `#11` YAGNI was under Tier 2 P1/P2 despite being P2. The new severity-first layout aligns SKILL.md, README, plugin/marketplace descriptions, and the canonical Quick Reference table on a single P0/P1/P2 taxonomy: P0 (11 items), P1 (7 items), P2 (1 item) — 19 anti-patterns total. Frontmatter description rewritten to enumerate patterns under each severity. `scripts/ci/review.sh` Checks 3 / 3b / 5 rewritten to verify (a) every `####` id under each `### P0 / P1 / P2` section in SKILL.md matches that severity in the Quick Reference, (b) every README severity-table row matches Quick Reference severity, and (c) the 19 patterns from the SKILL.md frontmatter appear in order in plugin.json / marketplace.json descriptions.
- **README duplicate Supplementary Check** — `Weak CI observability` was listed both under `### Supplementary Checks` and `### Full Review Surface` (as `CI diagnostics`). Removed the duplicate row from `Supplementary Checks`; the substantive item stays in `Full Review Surface` where it semantically belongs (it is a review-surface concern, not a code-level check).
- **`.gitignore`** — ignores local `.sisyphus/` continuation state so generated session files are not committed accidentally.
- **`playwright-debugger` evals F-code taxonomy** — `evals/evals.json` assertions used F-codes that did not match the `SKILL.md` F1–F14 table: selector-not-found was mislabeled F1 (should be F2 Selector Broken), timeout was mislabeled F2 (should be F1 Flaky/Timing), API 500 was mislabeled F5 (should be F3 Network Dependency), session expiry was mislabeled F7 (should be F10 Auth/Session), and race condition / animation race were mislabeled F8 / F12 (should be F1 / F14). Eval expected_output and per-assertion F-codes corrected to match `SKILL.md`.
- **`e2e-reviewer` Phase 2 LLM table coverage** — `#15 Missing await on expect` and `#16 Missing await on action` had per-rule "confirm in Phase 2" instructions but no corresponding rows in the Phase 2 LLM Review table. Rows added: `#15` confirms the subject is a Locator/Page (not a primitive), `#16` confirms the line lacks leading `await` for a real Playwright action.
- **`playwright-test-generator` frontmatter and Pipeline overview** — descriptions said "Playwright CLI or agent-browser" but Step 3 body already documents agent-browser as primary and `npx playwright codegen` as a manual fallback (set in 1.1.2). Frontmatter description and Pipeline overview now match.
- **`e2e-reviewer` frontmatter wording** — described `#12 Missing Auth Setup` and `#13 Inconsistent POM Usage` as "supplementary grep checks", but both are LLM-only in `SKILL.md`. Reworded to "supplementary checks" with detection method tagged per item. Cypress `uncaught:exception` suppression broken out as its own group so the "13 anti-pattern groups" count matches the README Tier tables and Quick Reference.
- **`#9` Hard-coded Sleeps pattern label alignment** — `playwright-debugger` and `cypress-debugger` Phase 2 classification tables pointed to `#9a` for F1 Flaky/Timing and F14 Animation Race, and `scripts/e2e-smell-scan.sh` used `#9a` for the Playwright `waitForTimeout` check. The canonical label in `e2e-reviewer/SKILL.md` and `references/grep-patterns.md` is `#9` (with `#9b` Cypress and `#9c` networkidle as variants). All five references updated to `#9`.
- **README Tier placement of `#3b`** — `Cypress uncaught:exception suppression` was listed under Tier 2 (P1/P2) but is P0 in Quick Reference, `grep-patterns.md`, and `e2e-smell-scan.sh`. Moved to Tier 1 (P0/P1) where it belongs as a P0 sub-variant of `#3 Error Swallowing`.
- **README Phase 2 description coverage** — Phase 2 LLM workflow summary omitted `#4 .toBeTruthy()` Locator-subject confirmation, `#15` missing-await-on-expect Locator confirmation, and `#16` missing-await-on-action confirmation. Added so the README description matches the actual Phase 2 LLM Review table in `SKILL.md`.
- **`docs/e2e-test-smells.md` taxonomy alignment** — public taxonomy doc had two ID divergences from the canonical `SKILL.md` Quick Reference: `#3b Cypress uncaught:exception suppression` was described inside `#3` instead of getting its own P0 row, and an invented `#11b Zombie spec` row existed under P2 even though `SKILL.md` covers zombie specs inside `#11 YAGNI + Zombie Specs`. Added a dedicated `#3b` P0 row and folded `#11b` content into the `#11` row so the doc reflects the IDs the reviewer and scanner actually emit.
- **`plugin.json` / `marketplace.json` 13-group description** — marketplace description listed the 13 anti-pattern groups in a non-numerical order (`#8 missing assertions` before `#5/#6/#7`), labeled `#10` as "flaky selectors" (which omits the `describe.serial` sub-pattern), and labeled `#11` as "YAGNI" (which omits zombie specs). Aligned to `SKILL.md` frontmatter wording and numerical order so marketplace listing matches the canonical skill description.

## [1.2.1] - 2026-04-12

### Changed
- **`e2e-reviewer` unsupported automation scope removed** — the description previously listed an automation target with zero grep patterns and zero eval coverage. Scope narrowed to Playwright and Cypress with full grep + LLM analysis. General principles (name-assertion alignment, missing Then, YAGNI) still apply to any framework.
- **`e2e-reviewer` Phase 1 grep tables extracted** to `references/grep-patterns.md` — SKILL.md reduced from 625 to 571 lines. Patterns loaded on demand, not always in context.
- **`e2e-reviewer` test directory auto-detection** — Phase 1 no longer hardcodes `e2e/`; instructs auto-detection from project structure (`tests/`, `__tests__/`, `spec/`, `cypress/e2e/`, etc.).
- **`e2e-reviewer` #14 credentials grep pattern expanded** — now catches `cy.get('#password').type('<literal-secret>')` and `page.getByLabel('Password').fill('test')` in addition to `loginPage.login('admin', 'pass')`.

### Improved
- **`e2e-reviewer` evals strengthened** — all 7 eval assertions now include line numbers, specific context, and P0/P1/P2 severity tags. False positive assertions added to eval 1 (public route not flagged as missing auth), eval 2 (toBeVisible not flagged as always-passing), and eval 6 (chained cy.get not flagged as dangling).

## [1.2.0] - 2026-03-30

### Added
- **`e2e-reviewer` #18 `expect.soft()` overuse** (P1, grep+LLM) — Phase 1 grep detects all `expect.soft()` hits; Phase 2 LLM confirms if >50% of assertions in a single test are soft. Tests with only soft assertions never fail early, functionally equivalent to error swallowing.
- **`e2e-reviewer` #3b Cypress `uncaught:exception` suppression** (P0, grep) — detects `cy.on('uncaught:exception', () => false)` in both spec files and `cypress/support/` directory. Blanket suppression is P0; scoped handlers with `// JUSTIFIED:` are acceptable.
- **`playwright-test-generator` forbidden patterns expanded** — `toBeAttached()`, `expect(locator).toBeTruthy()`, direct `page.click(selector)`, `{ force: true }`, `waitUntil: 'networkidle'`, `expect(page.url()).toContain(x)` added to code-rules.md forbidden table.
- **`playwright-test-generator` await rule** — explicit rule: every `expect()` on a Locator and every Playwright action must be `await`ed.
- **`playwright-test-generator` Suppression Convention section** — documents `// JUSTIFIED:` pattern for unavoidable forbidden patterns (`nth()`, `force: true`, `timeout: 0`, `evaluate()`), bridging generator output to `e2e-reviewer` grep checks.
- **`best-practices.md` anti-patterns expanded** — `networkidle`, direct `page.click(selector)`, missing `await` added.

### Changed
- **`e2e-reviewer` selector priority (#10a)** — updated from `data-testid → role/label` to Playwright official order: `getByRole` → `getByLabel` → `getByTestId` → `getByText` → attribute → class → generic. Now consistent with `playwright-test-generator` code-rules.md.
- **`e2e-reviewer` Phase 0 framework skip** — expanded to include new checks: Playwright skips `#3b`; Cypress skips `#18`, `#15/#16`, `#17`.
- **`e2e-reviewer` pattern count** — 11 → 13 (description, README, Quick Reference updated).
- **`playwright-test-generator` `expect.soft()` guidance** — changed from unconditional recommendation to conditional: at least one hard `expect()` must gate per test.
- **`playwright-test-generator` spec example credentials** — replaced hardcoded sample user/password literals with `process.env.TEST_USER`/`process.env.TEST_PASSWORD`.
- **README** — pattern count 11 → 13, Tier 2 table updated, Review Workflow updated.

## [1.1.3] - 2026-03-22

### Added
- **`e2e-reviewer` supplementary grep checks** — 6 additional patterns for general code quality (missing auth setup, inconsistent POM usage, hardcoded credentials, missing await on expect/action, direct page action API usage, networkidle). These supplement the core 11 anti-patterns during review.
- **Evals for all 4 skills** — `e2e-reviewer` (7 evals), `playwright-debugger` (4 evals), `cypress-debugger` (4 evals), `playwright-test-generator` (3 evals)
- **`.gitignore`** — eval fixture files and workspace dirs excluded from git

## [1.1.2] - 2026-03-19

### Fixed
- **`playwright-test-generator` Step 3 — browser exploration method corrected**: `playwright-cli` (non-existent package) removed entirely. Agent-browser tools (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_close`) are now the primary exploration method. `npx playwright codegen` documented as a manual reference only — interactive, not automatable in an agent pipeline.
- **README Compatibility** — `playwright-test-generator` Compatibility section updated to reflect agent-browser as primary exploration method.

### Changed
- **`e2e-reviewer` renumbered to 11 checks** — #8 Missing Assertion inserted (Tier 1, P0); Flaky Test Patterns reordered to #10, YAGNI to #11. Final order: #1–#8 Tier 1, #9 Hard-coded Sleeps, #10 Flaky, #11 YAGNI.
- **`e2e-reviewer` #4 Always-Passing expanded** — four new sub-cases: one-shot DOM reads (`textContent/getAttribute`), Locator-as-truthy (`toBeTruthy()` on Locator), assertion retry disabled (`{ timeout: 0 }`), and explicit `toBeAttached\(\)` grep pattern added to Phase 1.
- **`e2e-reviewer` #8 Missing Assertion** (new, P0) — merged from former #11/#12: 8a dangling locator `[Playwright grep]`, 8b boolean result discarded `[all frameworks grep]`. Cypress dangling selectors require Phase 2 manual check.
- **`e2e-reviewer` #3 Error Swallowing** — `try/catch` in specs moved to Phase 2 LLM (false positive risk in setup/teardown); `.catch(() => {})` in POM remains Phase 1 grep. Quick Reference updated to `grep+LLM`.
- **`e2e-reviewer` #5a Conditional Bypass** — clarified as runtime `if`-gated assertion only; removed misleading "mid-test `test.skip()`" reference.
- **`e2e-reviewer` #9 Hard-coded Sleeps** — severity P2 → P1 (direct flakiness cause); added BAD/GOOD code example.
- **`e2e-reviewer` assertion weakening removed** — `toBeDefined()` / `not.toBeNull()` dropped; unit-test concern, low ROI in E2E context.
- **`e2e-reviewer` code examples simplified** — generic placeholders throughout; `async ({ page })` signatures added to #1/#2; `// JUSTIFIED:` colon normalized.
- **`e2e-reviewer` sub-label corrections** — Flaky: `8a/8b` → `10a/10b`; YAGNI: `10a/10b` → `11a/11b`; Phase 1 grep list reordered #3–#10 sequential.
- **README** — pattern count 10 → 11, #4/#8 table entries updated, Review Workflow updated, Phase 1 range noted as partial for #10.
- **plugin.json** / **marketplace.json** — version 1.1.2, pattern count updated to 11.

## [1.1.1] - 2026-03-18

### Changed
- **`e2e-reviewer` #4 Always-Passing — expanded with three new sub-cases**:
  - Non-retrying state snapshot: `expect(await el.isDisabled()).toBe(true)` resolves a one-shot boolean with no auto-retry; use web-first assertions (`toBeDisabled()`, `toBeEnabled()`, `toBeChecked()`, `toBeHidden()`) instead. New grep pattern: `expect\(await.*\.(isDisabled|isEnabled|isChecked|isHidden)\(\)\)`.
  - Assertion weakening — `toBeDefined()` passes for `null`; `not.toBeNull()` passes for `""`. Use `not.toBeNull()` when `null` is the sole invalid case; use `toBeTruthy()` when empty string is also invalid (OAuth codes, secrets, slugs).
  - SKILL.md #4 section updated with concrete bad/good examples for assertion weakening.

## [1.1.0] - 2026-03-17

### Added
- **`playwright-test-generator`** — new skill for generating Playwright E2E tests from scratch
  - 7-step pipeline: environment detection → coverage gap analysis → live browser exploration (Playwright CLI / agent-browser) → scenario design with an approval gate → code generation → YAGNI audit + e2e-reviewer → TS compile + test run
  - Structure-aware: auto-detects POM vs flat spec pattern, extends existing POMs when present
  - Coverage gap analysis: scans Angular, Next.js, React Router routing files; maps existing specs to routes; flags auth and form-heavy pages as high priority
  - Browser exploration via Playwright CLI (`playwright-cli open/snapshot/close`); falls back to agent-browser tools
  - Approval gate: scenario list + locator mapping table before any code is written
  - Quality loop: YAGNI audit removes unused locators immediately after generation; `e2e-reviewer` runs automatically (P0 issues fix-looped, P1/P2 reported)
  - Failure handling: 3 targeted auto-fix attempts (selectors → assertions → structure), then hands off to `playwright-debugger`
  - Companion files: `code-rules.md` (selector priority, POM/spec rules, forbidden patterns) and `best-practices.md` (Playwright official best practices reference)
- **README**: added `playwright-test-generator` as Skill 1; updated workflow to include generation step; added Compatibility entry

## [1.0.1] - 2026-03-15

### Added
- **`e2e-reviewer` References**: Added Playwright and Cypress best-practices links at top of SKILL.md.
- **`e2e-reviewer` #4 Always-Passing — `isVisible()` boolean trap**: Added `expect(await.*\.isVisible\(\))` as a new grep-detectable variant. `isVisible()` resolves a one-shot boolean with no auto-retry; a transiently absent element can cause a silent pass. Rule extended to flag these and direct to `expect(locator).toBeVisible()` (web-first, auto-retries). Fix line and Quick Reference Detection Signal updated accordingly.
- **`e2e-reviewer` #7 Focused Test Leak** (new check, P0, grep): `test.only` / `it.only` / `describe.only` committed to source silently skips the entire suite in CI — all other tests show as "not run" but the step passes. No `// JUSTIFIED:` exemption. Pattern: `\.(only)\(` in spec files. Added to Phase 1 grep, Tier 1 section, and Quick Reference.
- **`e2e-reviewer` #8a Positional selectors — selector priority ranking**: Added one-line selector priority guide. Priority order (best → worst): `data-testid`/`data-cy` → role/label → `name` attr → `id` → class → generic. Class and generic selectors are "Never."

### Changed
- **`e2e-reviewer` Duplicate Scenarios removed**: Dropped the fuzzy per-test 70% overlap check — subjective threshold, expensive cross-file comparison, high false positive rate. Zombie spec file detection (entire file covered by another) absorbed into #10 YAGNI as sub-pattern 10b.
- **`e2e-reviewer` Renumbered to 10 checks**: #7 Focused Test Leak inserted (Tier 1, P0); Flaky Test Patterns (P1) reordered before Hard-coded Sleeps (P2). Final order: #1–#7 Tier 1, #8 Flaky, #9 Hard-coded Sleeps, #10 YAGNI.
- **`e2e-reviewer` #10 YAGNI expanded**: Added sub-pattern 10b zombie spec files + single-use Util wrapper rule (2+ threshold). Section renamed to "YAGNI — Dead Test Code."
- **`e2e-reviewer` Suppression rule**: `// JUSTIFIED:` now suppresses on the **line above** the flagged pattern instead of on the same line. Updated across all grep-checked patterns (#3, #4, #5, #8 partial, #9). Exception: #7 Focused Test Leak has no `// JUSTIFIED:` exemption.
- **`e2e-reviewer` #8b Serial**: Added explicit note that `// JUSTIFIED:` on the line above suppresses the `describe.serial` flag.
- **`e2e-reviewer` #6 Raw DOM Queries**: Simplified code examples — redundant BAD example removed; "Why it matters" moved above the code block.
- **`e2e-reviewer` frontmatter description**: Updated to reflect 10 checks, zombie spec files, and focused test leak.

## [1.0.0] - 2026-03-14

### Added
- **`e2e-reviewer` #5 expanded → "Bypass Patterns"**: Added `{ force: true }` detection (P1, grep) as sub-pattern 5b alongside existing conditional assertion bypass (5a). `force: true` without `// JUSTIFIED:` hides real actionability failures that real users would encounter.
- **`e2e-reviewer` #9 expanded → "Flaky Test Patterns"**: Added `test.describe.serial()` detection (P1, grep) `[Playwright only]` as sub-pattern 9b alongside existing positional selectors (9a). `describe.serial` creates order-dependent tests that break parallel sharding.
- **`e2e-reviewer` trigger phrases expanded**: Added "my tests are fragile", "tests break on every UI change", "test suite is hard to maintain", "we have coverage but bugs still slip through" to SKILL.md frontmatter description
- **`marketplace.json` keywords expanded**: Added `fragile-test`, `brittle-test`, `static-analysis`, `test-maintenance`, `test-smell`, `false-positive`, `end-to-end`, `spec`
- **README Key Insight** moved to top (after workflow section) for GEO discoverability

### Changed
- **`e2e-reviewer` reduced to 10 patterns** — removed 3 more checks that weren't reliably detectable via static analysis:
  - **#5 Boolean Trap removed** — `expect(locator).toBeTruthy()` is rare in practice among Playwright/Cypress users; low ROI
  - **#10b Animation Race removed** from Flaky Patterns — cannot be detected statically; requires running the tests to confirm
  - **#4 Always-Passing `toBeAttached()` simplified** — replaced multi-step template-reading decision tree with a single rule: flag any `toBeAttached()` with no inline comment. No template analysis required.
- **Description updated** across `marketplace.json` and `plugin.json` — new hook: "catch what CI misses — tests that pass but prove nothing, and failures that are hard to trace"
- **Project-specific examples removed** from SKILL.md — replaced with generic element/variable names throughout
- **`e2e-reviewer` reduced to 11 patterns** — removed 4 checks that were too subjective or context-dependent for general use:
  - **#8 Render-Only removed** — smoke tests legitimately use only `toBeVisible()`; too many false positives
  - **#10 Misleading Names removed** — absorbed into #1 (Name-Assertion Alignment); a name that implies a mechanism the test doesn't use is already a name-assertion mismatch
  - **#11 Over-Broad Assertions removed** — too domain-specific; "known enum values" is not universally determinable
  - **#12 Subject-Inversion removed** — `expect([200, 202]).toContain(status)` is a common and readable pattern in many teams
  - **#13b Missing Network Mock removed** from Flaky Patterns — real E2E philosophy intentionally avoids mocks; prescribing mocks conflicts with team conventions
  - **#13 Hard-coded Timeout narrowed** — now only flags explicit sleeps (`waitForTimeout`, `cy.wait(ms)`); no longer flags `timeout:` option values in `waitFor` calls
- **Renumbered**: 1–7 unchanged; 8=Duplicate, 9=Hard-coded Sleep, 10=Flaky Patterns, 11=YAGNI

## [0.8.2] - 2026-03-14

### Added
- **`e2e-reviewer` #9 Zombie spec file detection**: Added "zombie spec file" pattern — if ALL tests in a spec file are subsets of tests in another file covering the same feature, flag the entire file for deletion. Previously only individual test-level overlap was detected; whole-file redundancy (e.g., a 1-test file that duplicates a test in a larger suite) was missed.
- **`e2e-reviewer` #14 Empty wrapper class detection**: Added check for POM classes that extend a parent but declare zero additional members (`class Foo extends Bar` with constructor-only body). Flags these for review (P2) — may be intentional convention or future-extension placeholder, so automatic deletion is not prescribed. Previously YAGNI only checked individual unused members, not the class itself.

## [0.8.1] - 2026-03-14

### Fixed
- **`e2e-reviewer` #4 toBeAttached() grep scope**: Extended search target from spec files only to `.ts/.js/.cy.*` (all files including POM/util) — `toBeAttached()` in POM helper methods was previously invisible to Phase 1 grep
- **`e2e-reviewer` #6 Conditional Bypass POM gap**: Added explicit note that the Phase 1 grep only covers spec files; POM/util methods with `if (await el.isVisible())` guards must be reviewed manually in Phase 2

## [0.8.0] - 2026-03-13

### Added
- **`e2e-reviewer` #4 Always-Passing — `toBeAttached()` detection**: Added grep + LLM template check for `toBeAttached()` on unconditionally rendered elements (elements always present in DOM regardless of app state). Decision tree: unconditionally rendered or in static HTML shell → flag P0; CSS `visibility:hidden` variant or conditionally rendered → skip (meaningful assertion).
- **`e2e-reviewer` Suppression — same-line rule**: `// JUSTIFIED:` comment must appear on the **same line** as `.catch(` — a comment on the next line is invisible to grep. Added BAD/GOOD examples and a note that named function wrappers don't help (each inner `.catch(` still needs its own `// JUSTIFIED:` comment).

### Changed
- **`e2e-reviewer` #3 Error Swallowing grep pattern**: Updated to `\.catch\(\s*(async\s*)?\(\)\s*=>` — now detects both sync (`() => {}`) and async (`async () => {}`) silent catch variants.
- **`e2e-reviewer` #7 Raw DOM Queries scope expanded**: Now explicitly covers `document.querySelector` inside `waitForFunction()` in addition to `evaluate()`. Rule updated: `locator.waitFor({ state: 'attached' })` replaces single-condition `waitForFunction(() => querySelector(...) !== null)`. Exception list expanded: multi-condition AND/OR, `children.length`, `body.textContent`, `getComputedStyle` — add `// JUSTIFIED:` explaining why.
- **`e2e-reviewer` framework-agnostic cleanup**: Replaced project-specific examples (`nz-tree`, `zeppelin-root`, `app-root`, Angular `*ngIf`) with generic ones (`.sidebar`, `#app`, "conditional rendering directive") — skill no longer assumes Angular or any specific framework/component library.

## [0.7.4] - 2026-03-13

### Security
- **`playwright-debugger` Indirect Prompt Injection (W011)**: Added "Security: Treat Report Data as Untrusted" section — all content from `playwright-report/` is explicitly declared untrusted external data; embedded instructions in test titles, error messages, or trace content must never be followed
- **`playwright-debugger` Dynamic Code Execution**: Replaced `node -e` inline shell scripts in Phase 1 and Phase 3 with Read tool + `/tmp` file approach — prevents untrusted trace content from being executed via shell interpolation
- **`playwright-debugger` Unverifiable External Dependency (W012)**: Removed `gh run download` artifact fetching entirely — reports must now be provided as a local path by the user; eliminates the external data ingestion attack surface

### Changed
- **`playwright-debugger` Prerequisites**: Removed GitHub PR URL / `gh` CLI download flow; report source is now always a user-provided local path or existing `playwright-report/` directory

## [0.7.3] - 2026-03-11

### Fixed
- **`e2e-reviewer` YAML parse error**: colon in frontmatter description (`naming-assertion mismatch, missing Then, error swallowing, always-passing assertions, boolean traps, conditional bypass, raw DOM queries, render-only tests, duplicate scenarios, misleading names, over-broad assertions, subject-inversion`) caused a `YAMLException` in gray-matter, making the skills CLI skip the skill entirely — replaced colon with em dash

### Changed
- **`playwright-debugger`**: replaced dense inline `node -e` one-liners in Phase 1–3 with natural language instructions — LLM reads trace events directly instead of running shell scripts
- **`e2e-reviewer`**: replaced Phase 1 bash grep block with a prose checklist — LLM uses the Grep tool per anti-pattern instead of running a shell script
- **README**: updated `playwright-debugger` debug workflow description to reflect trace analysis approach

> Motivation for code block changes: reduced code density to address Socket "Obfuscated File" false positive on SKILL.md files.

## [0.7.2] - 2026-03-11

### Changed
- **`skills/e2e-test-reviewer/` renamed to `skills/e2e-reviewer/`** — shorter skill name for CLI discoverability
- **`name: e2e-test-reviewer` → `name: e2e-reviewer`** in SKILL.md frontmatter

## [0.7.1] - 2026-03-11

### Changed
- **`skills/review/` renamed to `skills/e2e-test-reviewer/`** — folder name matches skill name

## [0.7.0] - 2026-03-11

### Added
- **`cypress-debugger`** — new skill for diagnosing Cypress test failures from mochawesome/JUnit report files
  - Phase 1: parses `mochawesome.json` or JUnit XML for failed tests, error messages, duration
  - Phase 2: classifies each failure into F1–F14 root cause categories
  - Phase 3: screenshot and video analysis via `cypress/screenshots/` and `cypress/videos/`
  - Phase 4: concrete fix suggestion per failure with P0/P1/P2 severity
- **`playwright-debugger` GitHub PR integration** — given a PR URL, automatically finds the failed CI run and downloads the playwright-report artifact via `gh`; reuses PR URL from conversation context when user says "failed again"

### Changed
- **`e2e-test-debugger` renamed to `playwright-debugger`** — reflects Playwright-only scope
- **`skills/debug/` renamed to `skills/playwright-debug/`** — consistent naming with new `cypress-debug/`
- **`playwright-debugger` title** updated to "Playwright Failed Test Debugger" — removes ambiguous "E2E" prefix
- **Repository renamed** to `e2e-skills` — shorter, cleaner package name
- **README**: restructured with "When to Use" sections, three-skill pipeline, Compatibility section
- **Installation**: fixed install command typo (`e2e-test-skill` → `e2e-skills`)
- **Skill descriptions** disambiguated: `e2e-test-reviewer` is static code analysis; `playwright-debugger` and `cypress-debugger` are runtime failure diagnosis — prevents incorrect skill selection on "flaky tests" queries
- **`marketplace.json`**: added `ci`, `ci-failure`, `playwright-debugger`, `cypress-debugger`, `test-review`, `test-audit`, `regression` keywords

## [0.6.1] - 2026-03-11

### Changed
- **Skill names** renamed to `e2e-test-reviewer` and `e2e-test-debugger` — shorter, more intuitive

## [0.6.0] - 2026-03-10

### Changed
- **Plugin renamed** from `e2e-test-reviewer` to `e2e-test-skill` — reflects expanded scope
- **Mono-skill structure**: skills now live in `skills/review/` and `skills/debug/` subdirectories
- **Skill names** updated to `e2e-test-skill-review` and `e2e-test-skill-debug`
- **plugin.json** skills array updated to `["./skills/review", "./skills/debug"]`

### Added
- **`e2e-test-skill-debug`** — new skill for diagnosing Playwright test failures
  - Phase 1: parses `results.json` to extract failed tests, error messages, duration
  - Phase 2: classifies each failure into F1–F14 root cause categories using error signals
  - Phase 3: trace analysis via direct `trace.zip` parsing (`unzip -p | node`) — no extra dependencies; covers failed steps, DOM snapshot, network failures, JS console errors
  - Phase 4: concrete fix suggestion per failure with P0/P1/P2 severity
  - Cross-references `e2e-test-skill-review` pattern numbers (e.g. F2 → #14 POM Drift)
  - Temporary `page.screenshot()` + browser agent pattern for cases trace alone can't resolve

## [0.5.3] - 2026-03-07

### Added
- **#11b Subject-Inversion** (P1): Detects `expect([expected]).toContain(actual)` where expected values are placed as the subject instead of the actual value — produces confusing failure messages like "Expected [200, 202] to contain 204"

### Context
Discovered during n8n (177k stars) review.

## [0.5.2] - 2026-03-06

### Changed
- **#5 Boolean Trap**: No longer flags `toBeTruthy()` on actual boolean return values (`response.ok()`, `isVisible()`, `isChecked()`, etc.). Only flags when used on non-boolean objects (Locator, ElementHandle) that are always truthy — the real bug. Phase 1 grep now excludes known boolean-returning methods via `grep -v`.
- **Quick Reference** updated to clarify boolean trap scope

### Context
Validated against 5 major open-source projects (Cal.com, Ghost, Grafana, Documenso, Appsmith). Documenso had 230+ `expect(response.ok()).toBeTruthy()` instances — these are working assertions on actual booleans, not bugs. Previous versions would have flagged all of them as P1.

## [0.5.1] - 2026-03-06

### Changed
- **SKILL.md moved to repo root** — eliminates redundant `e2e-test-reviewer/skills/e2e-test-reviewer/` nesting when installed as a plugin
- **plugin.json skills path** updated from `./skills/e2e-test-reviewer` to `./`

## [0.5.0] - 2026-03-06

### Added
- **P0/P1/P2 severity classification** for all 14 checks — P0 (must fix), P1 (should fix), P2 (nice to fix)
- **Phase 3: Coverage Gap Analysis** — identifies missing error paths, edge cases, accessibility, and auth boundary tests after review
- **Review Summary table** in output format — aggregates findings by severity with affected file list
- **Flaky sub-patterns** in #13: network dependency without mock (13b), animation race conditions (13c)
- **Procedure + Common patterns** for checks #1 (Name-Assertion), #2 (Missing Then), #9 (Duplicate Scenarios) — matching depth of #14 YAGNI
- **Network mock grep** in Phase 1 — detects `page.goto`/`cy.visit` without nearby route/intercept setup

### Changed
- **#13 renamed** from "Flaky Selectors" to "Flaky Patterns" — now covers positional selectors, network mocks, and animation timing
- **Tier headers** updated to show severity range (P0/P1 for Tier 1, P1/P2 for Tier 2)
- **Severity guide** changed from HIGH/MEDIUM/LOW to P0/P1/P2 with clearer definitions
- **Quick Reference table** replaced Tier column with Sev column

## [0.4.1] - 2026-03-02

### Fixed
- **#14 YAGNI in POM**: Clarified scope of "2+ specs" rule — it applies when **creating** new shared utils, not as grounds for deleting existing util files/classes that are actively imported and used. The rule now explicitly states: only flag unused individual members within util files, do not delete entire files that specs depend on.

## [0.4.0] - 2026-02-27

### Added
- **Phase 1: Automated Grep Checks** — deterministic pattern detection via `grep` before LLM analysis. Covers checks #3 (Error Swallowing), #4 (Always-Passing), #5 (Boolean Trap), #6 (Conditional Bypass), #7 (Raw DOM), #12 (Hard-coded Timeout), and `page.isClosed()` guards
- **Phase 2: LLM-only Checks** — LLM now only performs subjective checks (#1, #2, #8-11, #13, #14) that require semantic interpretation
- **`[grep-detectable]` / `[LLM-only]` tags** on each checklist item for quick classification
- **Phase column** in Quick Reference table to indicate grep vs LLM detection
- **Suppression mechanism** — `// JUSTIFIED: [reason]` inline comment excludes lines from Phase 1 grep results
- **Installer CLI method** in README (historical; current docs use one-command global installs with `npx skills add --skill '*' -g -a claude-code -a codex -a opencode`, include `--agent '*'` for every supported agent, and show `skills add` when the CLI is already installed)

### Changed
- Review workflow is now two-phase: mechanical grep first, LLM second — reduces token usage and ensures deterministic results for pattern-based checks
- **Framework-agnostic grep patterns** — Phase 1 covered Playwright (`toBeGreaterThanOrEqual`, `waitForTimeout`), Cypress (`should('be.gte')`, `cy.wait()`), and an additional automation target in a single command using `-E` extended regex (historical; current supported automation scope is Playwright and Cypress)

## [0.3.0] - 2026-02-27

### Added
- **Raw DOM Queries** check (#7, Tier 1): Detects `document.querySelector*` / `getElementById` inside `evaluate()` / `waitForFunction()` that bypass framework element APIs
- **Hard-coded Timeouts** check (#12, Tier 2): Detects `waitForTimeout()` / `cy.wait(ms)` and magic timeout numbers without explanation
- **POM error swallowing** detection in #3: `.catch(() => {})` / `.catch(() => false)` on POM wait/assertion methods
- **POM boolean trap** detection in #5: Methods returning `Promise<boolean>` instead of exposing element handles
- **Cross-file duplicate** detection in #9: Cross-check similar test names across different spec files
- **Severity guide** in output format: HIGH / MEDIUM / LOW classification for findings
- **Quick Reference** table restored (14 items, compressed)
- **Skip protection** rule: `test.skip()` with a reason comment or string is intentional — do not flag

### Changed
- **Framework-agnostic**: Principles were documented as framework-independent with specific guidance for Playwright, Cypress, and another automation target where they differ (#5, #7, #12) (historical; current supported automation scope is Playwright and Cypress)
- **POM files in scope**: Review checklist now explicitly covers Page Object Model files, not just spec files
- Renumbered all checks (1-7 Tier 1, 8-14 Tier 2) to accommodate new items
- Updated README pattern tables to 14 items with framework-agnostic examples
- Updated plugin.json and marketplace.json descriptions and keywords

### Removed
- Playwright-only assumptions from rules and examples

## [0.2.0] - 2026-02-26

### Added
- **Tier structure**: Checks split into Tier 1 (high-impact bugs, always check) and Tier 2 (quality improvements, check when time permits)
- **Flaky Selectors** check (#11): Detects positional selectors (`nth()`, `first()`) and unstable raw text matching that break across environments or i18n changes

### Changed
- Merged "Conditional Assertions" and "Conditional Skip" into a single **Conditional Bypass** check (#6) — both are symptoms of the same root cause
- Trimmed examples for obvious patterns (Always-Passing, Boolean Trap) — kept only BAD examples where the anti-pattern is self-evident
- Renumbered all checks to reflect tier ordering (1-6 Tier 1, 7-12 Tier 2)
- Updated README pattern tables to match new tier structure

### Removed
- Quick Reference table (redundant with detailed check sections)
- Verification section (too generic to be useful)
- "When to Use" section (redundant with frontmatter description)
- ~48% reduction in SKILL.md line count while preserving all detection rules

## [0.1.0] - 2025-06-15

### Added
- Initial release with 12-point checklist
- Detects: name-assertion mismatch, missing Then, render-only tests, duplicate scenarios, misleading names, over-broad assertions, always-passing assertions, conditional assertions, error swallowing, boolean traps, conditional skips, YAGNI in Page Objects
- Framework-agnostic design with Playwright examples
- YAGNI audit procedure with classification table output
- Task-based output format with concrete code fixes
