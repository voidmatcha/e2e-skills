# Benchmarks and Evidence Status

This directory preserves the benchmark inputs, protocols, raw reports, and negative results behind the short conclusion in the project README.

## Current conclusion

`e2e-skills` has useful behavior-backed development evidence and concrete open-source adoption, but it does **not** yet have a passing release-grade benchmark for generalized reviewer accuracy.

- The browser fixture archive completed **36/36 cells**: each strong Playwright/Cypress test passed on correct behavior and failed after its paired application fault, while the deliberately weakened test stayed green against that fault.
- The exact-artifact reviewer benchmark contains **12 proven false-green cases and 12 separate clean guards**. Ten fault cases are byte-identical operator mutants; two remove only answer-leading comments. It measures recognition of known fault shapes, not production accuracy.
- The current reviewer holdout is a **pre-live corpus** with 24 expected findings and 24 matched false-positive guards. No live v5 result is claimed.
- Completed independent robustness gates v4, v5, v7, and v8 all failed their preregistered all-attempt criteria. V6 and v9 were superseded before model calls. V10 is frozen but has not been run.
- Findings have contributed to **14 merged upstream PRs**. Those are self-selected case studies, not a representative validation sample.

## Evidence map

| Evidence | Status | What it supports | What it does not support |
| --- | --- | --- | --- |
| [Browser fault injection](fixture-faults/README.md) | Complete, 36/36 cells | The bundled fault operators distinguish strong tests from paired weak tests for the archived fixtures | Reviewer accuracy, generator quality, or production prevalence |
| [`reviewer-fault-causal-v3.json`](../scripts/evals/reviewer-fault-causal-v3.json) | 12 false-green cases + 12 clean guards; 10 fault cases are byte-identical mutants | Exact linkage between known false-green shapes and reviewer expectations | A sealed or independently sampled holdout |
| [`reviewer-holdout-v5.json`](../scripts/evals/reviewer-holdout-v5.json) | Pre-live; 24 findings + 24 guards | A balanced public corpus and preregistered evaluation surface | Any live v5 accuracy or skill-lift result |
| [Independent product reviews](independent-product-review-v1/README.md) | v4/v5/v7/v8 failed; v6/v9 not run; v10 frozen/not run | Repeated adversarial defect discovery and remediation tracking | A passing release gate, full-product coverage, or generalized accuracy |
| [Reviewer holdout v2](reviewer-holdout-v2/README.md) | Invalidated for performance estimation | An auditable negative result: apparent false positives exposed oracle omissions | A clean precision estimate |
| [Debugger protocol](../docs/debugger-benchmark/README.md) | Synthetic 30-case corpus; no independent oracle audit | F1-F15 framework/category coverage and replayable scoring contracts | Independently established debugger accuracy |

## Independent review chronology

- **v4:** scores 90.50, 92.50, and 91.50; overall `FAIL` because the first attempt reopened a High-severity issue.
- **v5:** scores 87.33, 88.00, and 88.00; `COMPLETE` / `FAIL` because every attempt reported at least one High-severity issue.
- **v6:** `SUPERSEDED_BEFORE_FREEZE` / `NOT_RUN` after a prompt-byte accounting defect was found before model calls.
- **v7:** attempts `PASS`, `PASS`, `FAIL`; overall `FAIL` because all three attempts were required to pass.
- **v8:** attempts `INCONCLUSIVE`, `FAIL`, `PASS`; overall `FAIL`.
- **v9:** superseded before freeze because its preregistered Codex-only host was unavailable; no model calls were made.
- **v10:** reduced seven-surface packet frozen for Claude Opus/Fable attempts; no result is claimed until the preregistered run completes.

The archives intentionally retain failed and superseded rounds instead of rewriting the score after defects or oracle problems are discovered.

**Packet discontinuity.** The README section exclusions that keep a reviewer from being pre-fed this project's own case (`README_EXCLUDED_HEADINGS` in `scripts/evals/run-independent-review.py`) named headings that a later README rewrite had renamed or deleted, so the exclusion silently became a no-op and those sections shipped inside the packet. The names have been repaired and the runner now refuses to build a packet when a configured heading no longer resolves. Rounds built before and after that repair used different README content and are not directly comparable.

## External research

The [LLM-generated test evidence review](../docs/llm-generated-e2e-test-evidence.md) tracks 59 named sources: 21 verified, 14 qualified, and 24 not cleared. External studies motivate the methodology, but results from unit testing, custom browser agents, or vendor tools are not presented as measurements of this project.
