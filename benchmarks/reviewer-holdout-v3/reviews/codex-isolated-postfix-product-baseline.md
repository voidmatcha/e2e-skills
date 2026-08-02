# Isolated post-fix Codex product review baseline

Date: 2026-07-30  
Decision: **REQUEST CHANGES**  
Score: **74/100**

## Isolation

The reviewer ran from a temporary `HOME` and `CODEX_HOME` with only the
authentication file exposed. User configuration, rules, Git history, global
skills, and the following repository evidence were absent:

- `scripts/evals/files/holdout/**`
- `scripts/evals/files/holdout-v3/**`
- `scripts/evals/reviewer-holdout*.json`
- `benchmarks/reviewer-holdout-v2/**`
- `benchmarks/reviewer-holdout-v3/**`
- `docs/benchmarks/**`

The reviewer explicitly reported the contamination check as clean.

## Score

| Category | Score |
|---|---:|
| Behavior correctness | 17/25 |
| Scanner precision/recall robustness | 16/20 |
| Benchmark validity/unbiasedness | 14/20 |
| Executable evidence | 13/15 |
| Documentation/product clarity | 8/10 |
| Maintainability/security | 6/10 |
| **Total** | **74/100** |

## Ordered findings

1. **HIGH — Generator YAGNI audit can delete internally used POM locators.**
   It searched only spec files before deleting zero-use locators. A locator
   used by a POM method but not referenced directly by a spec could be removed.
2. **HIGH — Known P0 defects could advance through verification.** After
   three unsuccessful repair attempts the workflow proceeded to Step 7 with a
   warning instead of returning a blocked or incomplete result.
3. **HIGH — Post-fix AST verification failed open on ast-grep errors.** The
   verifier masked every ast-grep status with `|| true` and inferred success
   from formatted finding counts.
4. **MEDIUM — Post-fix verification could automatically download an unpinned
   tool.** Its `npx --yes @ast-grep/cli` fallback conflicted with the
   no-install verification contract.
5. **MEDIUM — Scanner #6 recall did not match its documented contract.**
   `document.getElementById` was documented but not scanned.
6. **LOW — Playwright blob-report merge assumed its output directory already
   existed.**

## Supported claims and limits

The reviewer credited the semantic-triage and framework-boundary contracts,
scanner lexical and scope controls, executable 11-operator/33-cell matrix,
debugger contracts, V1-V6 parity, and the Playwright/Cypress semantic archives.
It did not credit current model accuracy because labeled corpora and model
reports were intentionally removed. The read-only sandbox also prevented a
fresh browser replay and tests that require temporary workspaces.

This is a pre-remediation baseline. The findings above must be independently
fixed and retested before any later score is compared with it.
