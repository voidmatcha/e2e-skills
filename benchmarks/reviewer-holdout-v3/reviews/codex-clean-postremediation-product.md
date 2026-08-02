# Clean post-remediation product audit

Date: 2026-07-30  
Verdict: **90/100**

This was an offline, source-only Codex `gpt-5.6-sol` audit. Benchmark reports,
benchmark and eval corpora, executable fixtures, semantic-probe sources, Git
metadata, prior reviews, global skills, memories, and network access were
excluded. No benchmark-performance credit was awarded.

The audit used a fresh HOME/CODEX_HOME containing authentication only and a
109-file clean snapshot at
`/private/tmp/e2e-review-postremediation-v7c-clean.IZa0cd`. The launcher
recorded the start-of-run snapshot fingerprint as
`70f6432aecd200cb655fb2bbb09589189831233310f811aaba7c97e8f4140827`.
Temporary `.audit-*` reproductions were removed before the audit exited.

## Score

| Area | Score |
| --- | ---: |
| Reviewer/scanner detection coverage | 28/30 |
| False-positive resistance and adjudication | 13/15 |
| Generator/debugger operational safety | 15/20 |
| Runner/CI/security fail-closed behavior | 15/15 |
| Cross-host packaging/parity | 10/10 |
| Truthful actionable documentation | 9/10 |
| **Total** | **90/100** |

## Confirmed defects

1. **V2 assertion inversion was not a sound falsification oracle.** Separate
   runs of a transitional assertion and its negation can both pass at different
   points in the transition.
2. **The deterministic scanner missed ordinary #15/#16 forms.** Its async
   matcher list omitted `toHaveId` and `toMatchAriaSnapshot`, and an action
   Promise assigned and then explicitly discarded was not surfaced.
3. **Strings became confirmed mechanical findings.** Documentation text
   containing `waitForTimeout` or `timeout: 0` could fail
   `E2E_SMELL_FAIL_ON=any`.
4. **V6 independence was stated but not enforced.** An inline review in the
   writer's existing context could be recorded as independent.

The audit also recorded non-deducted limits around JUnit input bounds,
host-specific installation behavior, and LLM-triage quality.

## Positive evidence

- Deterministic findings and LLM-triage candidates are separated.
- Semantic findings use a refute-first verifier with a three-verdict outcome.
- Scanner roots, filenames, PATH tools, symlinks, PCRE2 support, and ripgrep
  errors are guarded fail-closed.
- Target-controlled generator/debugger commands require trust and approval.
- CI refuses skip flags and maintains cross-host version and skill-surface
  parity.

This score is a product/source review, not a benchmark result or an unbiased
estimate of generalization.
