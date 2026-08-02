# Clean blind Codex adversarial review

Date: 2026-07-30  
Decision: **REJECT**  
Score: **72/100**

## Blindness check

The reviewer inspected the same sanitized 204-file snapshot and confirmed that
all prohibited holdout sources, labeled corpora, reports, v2/v3 benchmark
bundles, and `docs/benchmarks/**` were absent. It did not inspect the working
repository, Git history, oracle files, prior reviews, or prior scores.

## Score

| Category | Score |
|---|---:|
| Behavior correctness | 19/25 |
| Scanner precision/recall robustness | 11/20 |
| Benchmark validity/unbiasedness | 16/20 |
| Executable evidence | 10/15 |
| Documentation/product clarity | 8/10 |
| Maintainability/security | 8/10 |
| **Total** | **72/100** |

## Confirmed findings

1. **High — comment-only framework text can gate a unit file as P0.** A Vitest
   file containing only a comment mentioning `@playwright/test` plus
   `expect(rowLocator).toBeTruthy()` entered Playwright scope and failed the P0
   gate.
2. **High — nested scan roots miss custom Playwright fixture modules.** A spec
   importing `../fixtures` or a shared `test-base` outside the requested test
   directory was skipped even though the module remained inside the detected
   project root. Root scans found it; documented `scan.sh path/to/tests` scans
   did not.
3. **Medium — selected AST-tool failures fail open.** The optional AST command
   discarded its exit status, so a selected tool exiting 2 could silently lose
   multiline `#15` coverage.
4. **Medium — `#10c` is semantic triage but was emitted as a confirmed P1.**
   A distinctive static accessible name could fail `FAIL_ON=any` before the
   required dynamic substring-collision analysis.
5. **Medium — a subset `--case` report can say complete/PASS.** The comparator
   later rejects an incomplete matrix, but an individual partial report did
   not mark its scope or remain inconclusive.
6. **Low — the shared `#4g` contract lacks equivalent Cypress behavioral
   evidence.** Documentation correctly labels the existing probe Playwright
   only, making this a coverage gap rather than a false claim.

## Supported claims

- PCRE2/ripgrep errors fail closed.
- `JUSTIFIED` lexical parsing rejects empty, negated, string, template, and
  block-comment bypasses, and never suppresses committed focused tests.
- Corpus, protocol, staged skill, workspace, and runner provenance checks are
  strong and infrastructure errors remain unscored.
- Repeated-run statistics are separated from unique-label primary metrics.

This is a Codex-family adversarial product review, not independent human
ground truth or a benchmark score.

