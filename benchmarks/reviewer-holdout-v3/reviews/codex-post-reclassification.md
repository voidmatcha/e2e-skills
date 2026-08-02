# Codex post-reclassification product review

Review date: 2026-07-30  
Snapshot: isolated copy excluding the raw v3 corpus, raw model reports, prior
product reviews, scorecards, and Git history.

## Verdict

**REQUEST CHANGES — 74/100**

| Area | Score |
|---|---:|
| Taxonomy and contract coherence | 14/20 |
| Playwright/Cypress semantic accuracy | 14/20 |
| False-positive controls and context boundaries | 9/15 |
| Executable fixture/fault evidence | 12/15 |
| Benchmark integrity and fail-closed behavior | 14/15 |
| Documentation honesty and usability | 11/15 |

The reviewer inspected 23 core files and reported three high- and three
medium-priority findings.

## Findings

### High: default Tier 1 crosses the target-code trust boundary

The scanner trusts the target repository's local ESLint executable, imports
its flat config, and runs both with the caller's environment. A malicious
checkout, plugin, or config can therefore execute code, read inherited
credentials, or make network requests during a scan described as read-only and
offline.

Remediation: disable local Tier 1 by default behind an explicit trust opt-in,
say that the opt-in executes target-controlled code, minimize inherited
sensitive environment, and avoid claiming an OS sandbox that does not exist.

### High: Tier 1 ignores the E2E scope

The generated ESLint config applies the Playwright/Cypress rules to every
TypeScript/JavaScript file, and Tier 1 counts focused-test output without the
Tier 3 `file_in_e2e_scope` predicate. A temporary repository containing one
Playwright spec and a neighboring Vitest `test.only` produced a P0 finding and
exit 1 from the unit-test file.

Remediation: pass only E2E-proven files to ESLint or discard Tier 1 hits outside
the same E2E scope, with a real-plugin Vitest/Jest neighbor regression.

### High: multiline conditional state reads become false #8b P0 findings

The scanner recognizes `#5a` only on a same-line `if`, while `#8b` treats a
physical line containing only `await spinner.isVisible()` as a discarded
boolean:

```typescript
if (
  await spinner.isVisible()
) {
  await expect(spinner).toBeHidden();
}
```

That shape was reproduced as a mechanical #8b P0 instead of a #5a triage
candidate.

Remediation: inspect bounded structural context before classifying #8b and
exclude values consumed by conditions, returns, assignments, arguments, or
ternaries.

### Medium: the #4g `timeout: 0` contract reverses Playwright 1.62 behavior

The current contract calls `{ timeout: 0 }` a one-shot assertion. The reviewer
found that Playwright 1.62 creates no matcher deadline for zero and continues
retrying until an outer deadline, normally the test timeout.

Remediation: redefine #4g as a disabled assertion deadline coupled to an outer
timeout and add a delayed-DOM browser probe.

### Medium: POM `.catch(() => {})` lacks a reliable scanner path

The canonical #3 contract covers POM catches, but the scanner's glob excludes
ordinary POM/support filenames and the Phase 2 text describes only spec
`try/catch`. A temporary POM probe was not reported.

Remediation: scan Playwright/Cypress-proven POM/support files, route ambiguous
bodies to semantic review, and add exact positive plus cleanup/fallback guards.

### Medium: the #4b attachment boundary contradicts itself

The pattern reference says CSS-hidden DOM presence is the only legitimate
positive `toBeAttached()` use, then says positive attachment is usually a
legitimate dynamic render gate.

Remediation: remove the absolute statement and judge attachment against the
promised DOM-presence contract and destructive-action context.

## Strengths

- The #15/#16 P1 reclassification is semantically sound and backed by a
  focused Playwright 1.62 six-cell probe.
- The fixture evidence is auditable: 11 operators, 33 browser cells,
  mutation/source hashes, normalized commands, sanitized output, and explicit
  scope limitations.
- The benchmark infrastructure fails closed through copied input snapshots,
  pre/post digests, incomplete-schedule handling, raw-output reparsing, and
  cross-model provenance checks.
- Public documentation keeps the v3 result incomplete and does not convert
  historical or contaminated evidence into a passing current score.

## Validation and stop condition

The isolated review passed scanner regressions, fixture contract validation,
the archived 33-cell and six-cell validators, the behavioral harness, eval
schema validation, and shell/Python syntax checks. It could not rerun browsers
because isolated fixture dependencies were intentionally absent.

The review's higher-score stop condition is to fix all three high findings,
correct and runtime-probe #4g, close the POM #3 gap, and add real-ESLint plus
multiline-condition regressions. A score above 90 also requires a fresh
complete current-taxonomy model matrix and a human or model-family-independent
oracle audit.

Licensed under Apache-2.0 with the repository.
