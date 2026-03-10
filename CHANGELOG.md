# Changelog

## [4.0.1] - 2026-03-11

### Changed
- **Skill names** renamed to `e2e-test-reviewer` and `e2e-test-debugger` — shorter, more intuitive

## [4.0.0] - 2026-03-10

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

## [3.3.0] - 2026-03-07

### Added
- **#11b Subject-Inversion** (P1): Detects `expect([expected]).toContain(actual)` where expected values are placed as the subject instead of the actual value — produces confusing failure messages like "Expected [200, 202] to contain 204"

### Context
Discovered during n8n (177k stars) review.

## [3.2.0] - 2026-03-06

### Changed
- **#5 Boolean Trap**: No longer flags `toBeTruthy()` on actual boolean return values (`response.ok()`, `isVisible()`, `isChecked()`, etc.). Only flags when used on non-boolean objects (Locator, ElementHandle) that are always truthy — the real bug. Phase 1 grep now excludes known boolean-returning methods via `grep -v`.
- **Quick Reference** updated to clarify boolean trap scope

### Context
Validated against 5 major open-source projects (Cal.com, Ghost, Grafana, Documenso, Appsmith). Documenso had 230+ `expect(response.ok()).toBeTruthy()` instances — these are working assertions on actual booleans, not bugs. Previous versions would have flagged all of them as P1.

## [3.1.0] - 2026-03-06

### Changed
- **SKILL.md moved to repo root** — eliminates redundant `e2e-test-reviewer/skills/e2e-test-reviewer/` nesting when installed as a plugin
- **plugin.json skills path** updated from `./skills/e2e-test-reviewer` to `./`

## [3.0.0] - 2026-03-06

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

## [2.1.1] - 2026-03-02

### Fixed
- **#14 YAGNI in POM**: Clarified scope of "2+ specs" rule — it applies when **creating** new shared utils, not as grounds for deleting existing util files/classes that are actively imported and used. The rule now explicitly states: only flag unused individual members within util files, do not delete entire files that specs depend on.

## [2.1.0] - 2026-02-27

### Added
- **Phase 1: Automated Grep Checks** — deterministic pattern detection via `grep` before LLM analysis. Covers checks #3 (Error Swallowing), #4 (Always-Passing), #5 (Boolean Trap), #6 (Conditional Bypass), #7 (Raw DOM), #12 (Hard-coded Timeout), and `page.isClosed()` guards
- **Phase 2: LLM-only Checks** — LLM now only performs subjective checks (#1, #2, #8-11, #13, #14) that require semantic interpretation
- **`[grep-detectable]` / `[LLM-only]` tags** on each checklist item for quick classification
- **Phase column** in Quick Reference table to indicate grep vs LLM detection
- **Suppression mechanism** — `// justified: [reason]` inline comment excludes lines from Phase 1 grep results
- **`npx skills` installation** method in README (recommended)

### Changed
- Review workflow is now two-phase: mechanical grep first, LLM second — reduces token usage and ensures deterministic results for pattern-based checks
- **Framework-agnostic grep patterns** — Phase 1 now covers Playwright (`toBeGreaterThanOrEqual`, `waitForTimeout`), Cypress (`should('be.gte')`, `cy.wait()`), and Puppeteer in a single command using `-E` extended regex

## [2.0.0] - 2026-02-27

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

## [1.1.0] - 2026-02-26

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

## [1.0.0] - 2025-06-15

### Added
- Initial release with 12-point checklist
- Detects: name-assertion mismatch, missing Then, render-only tests, duplicate scenarios, misleading names, over-broad assertions, always-passing assertions, conditional assertions, error swallowing, boolean traps, conditional skips, YAGNI in Page Objects
- Framework-agnostic design with Playwright examples
- YAGNI audit procedure with classification table output
- Task-based output format with concrete code fixes
