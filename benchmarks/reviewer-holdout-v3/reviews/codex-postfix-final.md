# Independent corrected-product review

Reviewer input was an isolated product snapshot that excluded the labeled
holdout corpus, model reports, scorecards, prior reviews, and chat conclusions.

## Product Review

**Score: 84/100 — REQUEST CHANGES**

| Category | Score |
|---|---:|
| Taxonomy correctness and coverage | 18/20 |
| Playwright/Cypress semantic accuracy | 17/20 |
| False-positive controls | 13/15 |
| Executable mutation/behavior evidence | 13/15 |
| Runner integrity/reproducibility | 14/15 |
| Documentation honesty/persuasion | 9/15 |

## Confirmed defects

### High: `#16` suppresses actions inside an unobserved Promise aggregate

The filter removed every action inside `Promise.all`, `Promise.race`,
`Promise.allSettled`, or `Promise.any` without checking whether the aggregate
itself was awaited or returned. Therefore
`Promise.all([locator.click()]);` remained a floating Promise but produced no
P0 finding.

Recommended repair: suppress an array element only after proving that the
enclosing aggregate is observed. Add both awaited and unawaited aggregate
regressions.

### High: Playwright 1.62 `locator.drop()` is missing from `#16`

The pinned Playwright API exposes `Locator.drop(...): Promise<void>`, but the
scanner and documented action list omitted it. An unawaited
`locator.drop(...)` was therefore missed.

Recommended repair: add `drop` across the contract, scanner, fixtures, and
executable assertions, and compare the inventory with the pinned API.

### Medium: deterministic `#16/#17` coverage excludes POM files and aliased Page receivers

Both rules scanned only `*.spec.*` and `*.test.*`; `#17` also required the
literal receiver `page`. That missed `this.page.fill(...)`,
`appPage.click(...)`, and floating Locator actions inside POM methods.

Recommended repair: include POM/support TypeScript and JavaScript files, then
use import/property provenance before assigning severity. Keep uncertain
receivers in LLM triage.

### Medium: cited benchmark evidence was absent from the isolated snapshot

The reviewer could not follow several README benchmark links because the
benchmark corpus, reports, and scorecards were deliberately excluded from the
blind product-review snapshot. This is an isolation artifact, not a defect in
the full repository, where the cited files are present and link checks pass.

### Low: a historical public plan still calls direct Page APIs deprecated

`docs/superpowers/plans/2026-04-12-eval-verification-system.md` used deprecated
wording that conflicts with the current, accurate discouraged-selector-API
contract.

## Confirmed strengths

- The 24-pattern taxonomy is stable, severity-organized, and substantially more
  nuanced than a grep catalog.
- `#17` is accurately distinguished from `playwright/no-element-handle`.
- `#18` correctly states that soft assertions still fail the test and flags
  prerequisite-dependent work rather than independent terminal details.
- False-positive controls cover framework scoping, `JUSTIFIED`, LLM triage,
  exact deduplication, continuation handling, and framework boundaries.
- The live fixture matrix completed 33/33 cells across 11 operators.
- The archive sanitizer handled `/var` versus `/private/var`, file URLs,
  relative-parent prefixes, secrets, ANSI escapes, and output bounds.
- Runner provenance includes fixture, operator, runner, lockfile, and runtime
  digests or versions.

## Limitations, not defects

- Behavioral mutation evidence covers 11 of 24 pattern families.
- Minimal fixtures prove those operators, not production-scale topology or
  general model accuracy.
- The isolated snapshot had no Git metadata.
- Holdout reports and scorecards were not used by the reviewer.

## Highest-value improvements

1. Make Promise-combinator suppression observation-aware.
2. Derive `#16` action coverage from the pinned Playwright API and add
   `locator.drop()`.
3. Extend `#16/#17` coverage to POMs and aliased Page/Locator receivers.
4. Keep benchmark claims auditable on the full published surface.
5. Add executable operators for `#15`, `#16`, `#17`, and `#18` where their
   semantics fit the evidence model.

The reviewer did not read the parent worktree, the labeled v3 corpus, model
reports, scorecards, previous reviews, or chat conclusions.
