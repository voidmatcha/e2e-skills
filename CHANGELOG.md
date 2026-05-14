# Changelog

## [1.2.2] - 2026-05-13

### Added
- **`.codex-plugin/plugin.json`** — added a dedicated Codex plugin manifest (peer to `.claude-plugin/plugin.json`) carrying the Codex-specific `interface` block (`displayName`, `shortDescription`, `longDescription`, `developerName`, `category`, `capabilities`, `websiteURL`, `defaultPrompt[]` per skill, `brandColor`) while pointing to the same shared `skills/` directory used by Claude Code. Both hosts now read from one source of truth for skill behavior with host-specific display surfaces.
- **Manifest version parity CI** — `scripts/ci/review.sh` Check 6 verifies that `.claude-plugin/plugin.json`, the `e2e-skills` entry in `.claude-plugin/marketplace.json`, and `.codex-plugin/plugin.json` share the same `version` string. `scripts/ci/test-parity.sh` Case 8 mutates `.codex-plugin/plugin.json` to assert the parity check fires; Case 9 mutates the Codex description out of order to confirm the existing description-parity loop also covers it.
- **Root `AGENTS.md`** — added a cross-agent canonical contributor guide at repo root following the AGENTS.md convention used by Codex, Cursor, Copilot, Gemini CLI, OpenCode, and other agents. Covers verification gate, directory layout, pattern/failure-code conventions, framework scope, local development commands, lock-step parity surfaces, cross-host parity rules, and installation paths. CLAUDE.md / agent-specific files can defer to this when present.
- **SKILL.md `license` + `metadata` frontmatter** — added `license: Apache-2.0` and `metadata: { author: voidmatcha, version: "1.2.2" }` to all four `skills/<name>/SKILL.md` files to match the canonical Agent Skills frontmatter shape used by `anthropics/skills` and `vercel-labs/agent-skills`.
- **README SEO/GEO improvements** — added Contents TOC under the intro, a "Comparison with Other Tools" table positioning `e2e-reviewer` against `eslint-plugin-playwright` / Playwright docs / raw grep, and a 7-question FAQ covering common pre-install user questions.

### Added (dev tooling)
- **Testbed for live OSS validation** — added `testbed/` (gitignored) as the canonical location to clone real-world Playwright/Cypress repos against which the skills can be exercised. Clone manually (`git clone --depth 1 <url> testbed/<name>`); then `bash scripts/e2e-smell-scan.sh testbed/<name>` or invoke `e2e-reviewer` on the path.
- **Local-install reinstall script** — `scripts/dev/reinstall-skills.sh` runs `npx skills remove` then `npx skills add <repo-root> --copy` scoped to the four e2e-skills via `--skill <csv>`, so other installed skills are untouched. Uses `--copy` mode (not the default symlink) so that uncommitted local edits in this repo do not leak into the Claude Code / Codex runtime — the installed copy reflects pushed state, not working-tree state. Override the agent list via `E2E_SKILLS_AGENTS` (default: `-a claude-code -a codex -a opencode`).
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
- **`e2e-reviewer` #14 scope narrowed to actual auth usage** — #14 Hardcoded Credentials flagged any literal matching `(login|fill|type).*(password|secret|admin)`. This produced false positives on input-behavior tests like `passwordInput.fill('typed text'); await expect(passwordInput).toHaveValue('typed text');` where the literal is test data for verifying form input acceptance, never used as an actual credential. Tightened the rule: only flag literals passed to authentication operations (`loginPage.login(...)`, password fields immediately followed by submit, API auth posts, or fixtures named `validUser` / `testAdmin`). Input-acceptance testing and intentional invalid-creds fixtures (e.g. `INVALID_USER = { username: 'wronguser', password: 'wrongpass' }` for negative-path tests) are explicitly excluded. Reviewers must read 2–3 lines below a literal to confirm a login/auth call follows.
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
- **`e2e-reviewer` #14 credentials grep pattern expanded** — now catches `cy.get('#password').type('secret')` and `page.getByLabel('Password').fill('test')` in addition to `loginPage.login('admin', 'pass')`.

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
- **`playwright-test-generator` spec example credentials** — replaced hardcoded `'user@example.com'`/`'password123'` with `process.env.TEST_USER`/`process.env.TEST_PASSWORD`.
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
