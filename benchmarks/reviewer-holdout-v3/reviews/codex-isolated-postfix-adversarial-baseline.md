# Isolated post-fix Codex adversarial review baseline

Date: 2026-07-30  
Decision: **REQUEST CHANGES**  
Score: **67/100**

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

The reviewer explicitly reported the contamination check as clean and made no
edits.

## Score

| Category | Score |
|---|---:|
| Behavior correctness | 17/25 |
| Scanner precision/recall robustness | 11/20 |
| Benchmark validity/unbiasedness | 13/20 |
| Executable evidence | 13/15 |
| Documentation/product clarity | 7/10 |
| Maintainability/security | 6/10 |
| **Total** | **67/100** |

## Ranked findings

1. **CRITICAL — Scanner failed open when temporary storage was unavailable.**
   With an unwritable temporary directory, `mktemp` and here-document creation
   failed, findings collapsed to zero, and the scanner exited successfully.
2. **HIGH — Post-fix AST verification downloaded code and masked tool
   crashes.** An unpinned `npx --yes` fallback and `|| true` could convert
   installation, parsing, or execution errors into a clean result.
3. **HIGH — Custom Playwright fixture imports could evade scanner scope.**
   NodeNext `./fixtures.js` to `fixtures.ts` substitution, TypeScript path
   aliases, and workspace fixture provenance were not resolved.
4. **MEDIUM — A one-repetition custom runner could receive an undifferentiated
   `PASS`.** Release repetition sufficiency was enforced only for the literal
   `codex` and `claude` runner names.
5. **MEDIUM — Browser evidence execution inherited the full ambient
   environment.** The fixture runner exposed unnecessary credentials, proxy,
   shell, and telemetry variables to dependency code.
6. **MEDIUM — Generic `getBy*` AST hits could enter the #4f P0 gate before
   receiver provenance was established.** RTL or custom throwing queries
   require triage, not mechanical P0.

The reviewer also observed missing benchmark links in the sanitized snapshot.
That was an intentional property of the blind-review artifact, not a defect in
the full repository, so it is not a remediation item.

## Supported claims and limits

The reviewer re-derived the 11-operator/33-cell fixture evidence, Playwright
floating-Promise 6/6 evidence, Playwright timeout-zero `1/0/1`, Cypress
timeout-zero `0/1/1`, debugger contracts, manifest version parity, and the
holdout runner's mutation/digest controls. It did not inspect excluded labeled
corpora, reports, Git history, or external skill installations.

This is a pre-remediation baseline. The findings above must be independently
fixed and retested before any later score is compared with it.
