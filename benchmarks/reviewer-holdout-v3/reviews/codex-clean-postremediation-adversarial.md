# Clean post-remediation adversarial audit

Date: 2026-07-30  
Verdict: **64/100 — changes required**

This was an independent offline, source-only Codex `gpt-5.6-sol` attack review.
It used the same 109-file clean snapshot and exclusions documented in
[`codex-clean-postremediation-product.md`](codex-clean-postremediation-product.md).
No benchmark-performance credit was awarded. The reviewer created narrow
hostile fixtures to reproduce suspected failures, then removed them and
terminated the detached-process probe before exiting.

## Score

| Area | Score |
| --- | ---: |
| Silent false-negative resistance | 21/30 |
| False-positive resistance | 11/15 |
| Hostile-input and executable trust boundaries | 7/15 |
| Generator/debugger/runner operational safety | 8/15 |
| Fail-closed CI and portability | 10/15 |
| Truthful user-facing contracts | 7/10 |
| **Total** | **64/100** |

## Confirmed defects

1. **Namespace Playwright APIs bypassed the complete review path.**
   `pw.test['only']`, floating `pw.expect(...).toBeVisible()`, and
   `pw.expect(locator).toBeTruthy()` produced zero scanner hits and were not
   covered by the fixed mandatory semantic sweep.
2. **Post-fix and preflight tools executed project-controlled binaries.**
   A malicious target-local `tsc` created a marker when `verify-fixes.sh` ran.
3. **A shadowed application receiver caused a gate-blocking #7 false
   positive.** A local object named `it` was treated as a Cypress global.
4. **A crashing compiler was labeled PASS.** A target-local `tsc` that exited
   2 without diagnostics was reported as `tsc PASS`.
5. **The bundled JUnit parser read through a report-root symlink.**
6. **Browser exploration could cross the approved origin through redirects.**
7. **Process-group timeout cleanup was not full containment.** A custom runner
   descendant that created a new session survived until the reviewer killed it.
8. **Contradictory duplicate keys in model JSON were accepted.**
9. **JSON manifest validation accepted duplicate keys.**
10. **Translation parity did not protect semantic feature/safety surfaces.**
11. **README overstated standalone scanner coverage.** The skill covers the
    24-pattern taxonomy; the shell scanner covers only a deterministic subset
    plus candidates.

## Non-deducted risks

- Nested symlinked specs may be omitted by discovery.
- Opted-in project ESLint remains explicitly unsandboxed.
- Comprehensive archive/XML/JSON resource limits are not universal.
- Translation quality itself cannot be proven by structural parity checks.

This deliberately harsh score is not combined with the 90/100 product score.
Both are retained to prevent favorable-review selection bias. Remediation and
any later score must use a new source snapshot and a new independent audit.
