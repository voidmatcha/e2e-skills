# Clean blind Codex product review

Date: 2026-07-30  
Decision: **REQUEST CHANGES**  
Score: **77/100**

## Blindness check

The reviewer inspected a 204-file snapshot with no Git metadata and confirmed
the absence of:

- `scripts/evals/files/holdout/**`
- `scripts/evals/files/holdout-v3/**`
- `scripts/evals/reviewer-holdout*.json`
- `benchmarks/reviewer-holdout-v2/**`
- `benchmarks/reviewer-holdout-v3/**`
- `docs/benchmarks/**`

It did not inspect the working repository, history, labels, oracle audits,
prior reviews, reports, or prior scores.

## Score

| Category | Score |
|---|---:|
| Behavior correctness | 20/25 |
| Scanner precision/recall robustness | 14/20 |
| Benchmark validity/unbiasedness | 14/20 |
| Executable evidence | 13/15 |
| Documentation/product clarity | 8/10 |
| Maintainability/security | 8/10 |
| **Total** | **77/100** |

## Confirmed findings

1. **High — valid Locator value assertion becomes a false P0.** The scanner
   reported both `#4c-4e` P1 and `#4f` P0 for
   `expect(await page.locator(...).getAttribute(...)).toBeTruthy()`. The
   resolved attribute value may be falsy; the Locator object itself is not the
   assertion subject.
2. **Medium — semantic rules are emitted as resolved scanner findings.**
   `#4c-4e` and `#10c` require project-context confirmation in the skill but
   lacked the scanner's triage flag.
3. **Medium — current performance evidence is development evidence, not an
   unbiased estimate.** The runner controls are strong, but the public corpus
   and same-family oracle audits cannot establish unseen-repository
   generalization.
4. **Medium — debugger commands can implicitly install packages.** Some
   documented `npx playwright` and `npx cypress` commands lacked
   `--no-install`, contradicting the skills' own no-install boundary.

## Supported claims

- Security checks, JSON/shell validity, parity guards, scanner scope tests,
  debugger contracts, and executable archive validators passed.
- The executable evidence covered 33 browser cells across 11 fault operators,
  plus 6/6 Playwright floating-Promise cells and the timeout-zero matrix.
- The benchmark runner freezes inputs, records exact provenance, re-parses raw
  output, checks pre/post workspace digests, and remains candid about public
  corpus and isolation limits.

This review is an independent Codex-family critique of the product surface. It
is not a model-accuracy result and is not treated as human adjudication.

