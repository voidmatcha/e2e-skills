# Changelog

## [1.1.1] - 2026-03-18

### Changed
- **`e2e-reviewer` #4 Always-Passing — expanded with three new sub-cases**:
  - Non-retrying state snapshot: `expect(await el.isDisabled()).toBe(true)` resolves a one-shot boolean with no auto-retry; use web-first assertions (`toBeDisabled()`, `toBeEnabled()`, `toBeChecked()`, `toBeHidden()`) instead. New grep pattern: `expect\(await.*\.(isDisabled|isEnabled|isChecked|isHidden)\(\)\)`.
  - Assertion weakening — `toBeDefined()` passes for `null`; `not.toBeNull()` passes for `""`. Use `not.toBeNull()` when `null` is the sole invalid case; use `toBeTruthy()` when empty string is also invalid (OAuth codes, secrets, slugs).
  - SKILL.md #4 section updated with concrete bad/good examples for assertion weakening.

## [1.1.0] - 2026-03-17

### Added
- **`playwright-test-generator`** — new skill for generating Playwright E2E tests from scratch
  - 7-step pipeline: environment detection → coverage gap analysis → live browser exploration (Playwright CLI / agent-browser) → scenario design with Plan Mode approval gate → code generation → YAGNI audit + e2e-reviewer → TS compile + test run
  - Structure-aware: auto-detects POM vs flat spec pattern, extends existing POMs when present
  - Coverage gap analysis: scans Angular, Next.js, React Router routing files; maps existing specs to routes; flags auth and form-heavy pages as high priority
  - Browser exploration via Playwright CLI (`playwright-cli open/snapshot/close`); falls back to agent-browser tools
  - Approval gate: EnterPlanMode with scenario list + locator mapping table before any code is written
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
- **`npx skills` installation** method in README (recommended)

### Changed
- Review workflow is now two-phase: mechanical grep first, LLM second — reduces token usage and ensures deterministic results for pattern-based checks
- **Framework-agnostic grep patterns** — Phase 1 now covers Playwright (`toBeGreaterThanOrEqual`, `waitForTimeout`), Cypress (`should('be.gte')`, `cy.wait()`), and Puppeteer in a single command using `-E` extended regex

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
- **Framework-agnostic**: Principles are now framework-independent with specific guidance for Playwright, Cypress, and Puppeteer where they differ (#5, #7, #12)
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
