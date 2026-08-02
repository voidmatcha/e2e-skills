# Blind adversarial product review before final fixes

Date: 2026-07-30

Snapshot: `/private/tmp/e2e-review-blind-final.Oy44Vy`

Status: **REQUEST CHANGES — 75/100**

This is pre-fix development feedback, not benchmark scoring. The reviewer was
isolated from the labeled holdout corpus, previous model reports, scorecards,
prior reviews, the source worktree, and Git history. Numerical claims in the
public documentation were treated as untrusted marketing rather than evidence.

## Fixed rubric

| Category | Score |
|---|---:|
| Taxonomy correctness and severity | 17/20 |
| Semantic and detection correctness | 12/20 |
| False-positive defenses and scope | 11/15 |
| Executable fixture and mutation evidence | 15/15 |
| Benchmark runner integrity and reproducibility | 12/15 |
| Public docs, security, and install honesty | 8/15 |
| **Total** | **75/100** |

## Confirmed defects

1. **High — target-controlled `ast-grep`/`sg` could execute by default.**
   The scanner rejected a binary only when it was beneath the requested scan
   root. Scanning `<repo>/tests` could therefore execute
   `<repo>/node_modules/.bin/ast-grep` from `PATH`, contradicting the default
   no-target-executable claim.
2. **High — supported module and JSX extensions bypassed mechanical rules.**
   Important rules, including P0 #7 and #8a, omitted one or more of
   `.mjs`, `.mts`, `.cjs`, `.cts`, `.jsx`, and `.tsx`, even though executable
   fixtures used these module forms.
3. **Medium — #14 mixed false negatives with false positives.**
   The regex missed a literal password supplied through a credential-labeled
   locator, while it could flag an environment-backed password. The mechanical
   result was not routed through semantic confirmation.
4. **Medium — #4a treated every `>= 0` assertion as invariant.**
   Signed balances, deltas, and offsets can meaningfully be negative, so the
   subject's domain must be confirmed before issuing a P0 verdict.
5. **Medium — `--skill-dir` used the default taxonomy for label validation.**
   Alternate skill snapshots could be evaluated while corpus severities were
   checked against `DEFAULT_SKILL_DIR`.

The reviewer gave full credit to the executable fixture and mutation evidence:
the public archive, separate floating-Promise probe, and timeout-zero probe
were internally consistent under the available validators.

Licensed under Apache-2.0 with the repository.
