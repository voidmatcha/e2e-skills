# Benchmarks and Evidence Status

This directory preserves the benchmark inputs, protocols, raw reports, and negative results behind the short conclusion in the project README.

Historical raw archives may retain normalized host-path shapes, temporary workspace paths, process identifiers, invocation identifiers, and runner diagnostics when those bytes are bound by evidence hashes. Generic account components such as `/Users/user/` and `/home/user/` are placeholders, not a contributor identity. Treat those fields as local run provenance, not as setup instructions or evidence that another machine will use the same paths. New producers must redact credentials and normalize real account names before committing artifacts; do not rewrite a frozen archive merely to make its diagnostics look platform-neutral.

## Current conclusion

`e2e-skills` has useful behavior-backed development evidence and concrete open-source adoption, but it does **not** yet have a passing release-grade benchmark for generalized reviewer accuracy.

- [Reviewer release v1](reviewer-release-v1/README.md) is the new from-scratch release protocol: 120 externally held sealed cases, three paired arms, blinded human adjudication, and explicit correctness, lift, stability, and user-helpfulness gates. It has not been run and remains `NOT_RUN` / `INCONCLUSIVE`; without a machine-verifiable signed isolation attestation it can produce development evidence only. The current decision is `PROCEED_WITH_INFRASTRUCTURE_ONLY` until those prerequisites exist.

- The browser fixture archive completed **36/36 cells (12 fault operators x 3 expected outcomes)**: for each operator, the strong test passed on correct behavior, the strong test failed after its paired application fault, and the deliberately weakened test stayed green against that fault.
- The exact-artifact reviewer benchmark contains **12 proven false-green cases and 12 separate clean guards**. Ten fault cases are byte-identical operator mutants; two remove only answer-leading comments. It measures recognition of known fault shapes, not production accuracy.
- Reviewer holdout v5 is a **pre-live corpus** with 24 expected findings and 24 matched false-positive guards. No live Reviewer holdout v5 result is claimed.
- Reviewer holdout v5 can no longer complete from an ordinary checkout. It preregistered `Claude Code 2.1.220`, that build is no longer installed locally, and the protocol requires a complete three-host matrix.
- Reviewer holdout v6 reused the Reviewer holdout v5 corpus byte-for-byte — identical case and corpus digests — and changed only the frozen CLI identity. Reviewer holdout v6 did execute its nine preregistered cells once. The incomplete archive is caused by post-run report loss: four reports were lost before they were copied out of temporary directories. CLI rotation is the rerun obstacle, not the reason those first-run reports are missing. It preregistered `Claude Code 2.1.239`, the local installer has since rotated that build away, and six of its nine cells need the Claude host for a rerun. The build is still served by the vendor channel, so the matrix is recoverable by re-fetching it, not permanently lost. Five partial reports are archived in [Reviewer holdout v6](reviewer-holdout-v6/README.md). No Reviewer holdout v6 result is claimed.
- Completed independent product-review robustness gates v4, v5, v7, and v8 all failed their preregistered all-attempt criteria. Independent product-review v6 and Independent product-review v9 were superseded before model calls. Independent product-review v10 is frozen but has not been run. Archived v1-v10 independent product-review rounds are retained as legacy robustness evidence, not current release gates.
- Findings have contributed to **15 merged upstream PRs**. Those are self-selected case studies, not a representative validation sample. [Field review v1](field-review-v1/README.md) reports the same campaign with a denominator — 29 submissions, 16 merged, 6 closed without merging, 7 open — because a merge count without its rejections is not a rate.

## Evidence map

| Evidence | Status | What it supports | What it does not support |
| --- | --- | --- | --- |
| [Field review v1](field-review-v1/README.md) | Complete; 29 submissions across 26 repositories, 16 merged / 6 closed / 7 open | Third-party adjudication: unrelated maintainers accepted or rejected these specific changes, each decision public and checkable | Reviewer precision or recall; a merge accepts a patch, it does not certify the finding's severity |
| [Field scan v1](field-scan-v1/README.md) | Incomplete; 10/12 pinned repositories completed with no suppressed rules; 2 timed out. Complete scans reported 0 P0 hits | Observed scanner candidates at pinned commits under frozen limits, with incomplete results marked explicitly | Precision, recall, reviewer lift, or complete coverage of incomplete rows |
| [Field scan v1 extension](field-scan-v1-extension/README.md) | Complete; completes the 12-repository sample v1's own selection rule designed but v1 itself marked "Incomplete: 10/12" — both former timeout rows (`ever-co/ever-gauzy`, `open-mercato/open-mercato`) now reach a natural exit with 0 suppressed rules and 0 P0 hits, under a separate disclosed protocol (removed wall-clock cutoff, hard-ceiling bounded limits) | All 12 originally designed repositories now have a completed measurement, split across two disclosed protocols; does not rewrite the frozen v1 ledger | The original 30-minute-budget v1 protocol itself completing; precision, recall, or reviewer lift |
| [Reviewer release v1](reviewer-release-v1/README.md) | Preregistered design; `NOT_RUN` / `INCONCLUSIVE` | A release-grade measurement contract once external custody and signed isolation are supplied | Any current accuracy, lift, or helpfulness result |
| [Browser fault injection](fixture-faults/README.md) | Complete, 36/36 cells (12 fault operators x 3 expected outcomes) | The bundled fault operators distinguish strong tests from paired weak tests for the archived fixtures | Reviewer accuracy, generator quality, or production prevalence |
| [`reviewer-fault-causal-v3.json`](../scripts/evals/reviewer-fault-causal-v3.json) | 12 false-green cases + 12 clean guards; 10 fault cases are byte-identical mutants | Exact linkage between known false-green shapes and reviewer expectations | A sealed or independently sampled holdout |
| [Reviewer holdout v5](../scripts/evals/reviewer-holdout-v5.json) | Pre-live; 24 findings + 24 guards | A balanced public corpus and preregistered evaluation surface | Any live Reviewer holdout v5 accuracy or skill-lift result |
| [Reviewer holdout v6](reviewer-holdout-v6/README.md) | Incomplete; 5 of 9 reports survived, 2 execution-complete reports | An auditable record of first-run report loss, later rerun blockage from local CLI rotation, and one same-host no-skill/catalog-only contrast | Any Reviewer holdout v6 matrix result, any `full` arm report, or generalization |
| [Independent product reviews](independent-product-review-v1/README.md) | Legacy evidence; v4/v5/v7/v8 failed, v6/v9 not run, v10 frozen/not run | Repeated adversarial defect discovery and remediation tracking | A current release gate, full-product coverage, or generalized accuracy |
| [Reviewer holdout v2](reviewer-holdout-v2/README.md) | Invalidated for performance estimation | An auditable negative result: apparent false positives exposed oracle omissions | A clean precision estimate |
| [Debugger protocol](../docs/debugger-benchmark/README.md) | Synthetic 30-case corpus; no independent oracle audit | F1-F15 framework/category coverage and replayable scoring contracts | Independently established debugger accuracy |

## Independent review chronology

- **Independent product-review v4:** scores 90.50, 92.50, and 91.50; overall `FAIL` because the first attempt reopened a High-severity issue.
- **Independent product-review v5:** scores 87.33, 88.00, and 88.00; `COMPLETE` / `FAIL` because every attempt reported at least one High-severity issue.
- **Independent product-review v6:** `SUPERSEDED_BEFORE_FREEZE` / `NOT_RUN` after a prompt-byte accounting defect was found before model calls.
- **Independent product-review v7:** attempts `PASS`, `PASS`, `FAIL`; overall `FAIL` because all three attempts were required to pass.
- **Independent product-review v8:** attempts `INCONCLUSIVE`, `FAIL`, `PASS`; overall `FAIL`.
- **Independent product-review v9:** superseded before freeze because its preregistered Codex-only host was unavailable; no model calls were made.
- **Independent product-review v10:** reduced seven-surface packet frozen for Claude Opus/Fable attempts; no result is claimed, and the archive is legacy design evidence rather than an active pending release gate.

The archives intentionally retain failed and superseded rounds instead of rewriting the score after defects or oracle problems are discovered.

**Packet discontinuity.** The README section exclusions that keep a reviewer from being pre-fed this project's own case (`README_EXCLUDED_HEADINGS` in `scripts/evals/run-independent-review.py`) named headings that a later README rewrite had renamed or deleted, so the exclusion silently became a no-op and those sections shipped inside the packet. The names have been repaired and the runner now refuses to build a packet when a configured heading no longer resolves. Rounds built before and after that repair used different README content and are not directly comparable.

## Execution identity drift

A protocol pins the CLI builds it was cut against, and `require_explicit_runner_path` exists so a run names the build it used instead of whatever is currently on `PATH`. Both matter more than they look:

- The installed `codex` entry point is a symlink to an auto-updating `current` release. Between cutting v6 and running it, that pointer moved twice (`0.146.0` to `0.147.0` to `0.149.0`), and Claude Code moved as well. Passing the plain command name makes the recorded identity a race, not a pin.
- Pass the versioned install path instead. Retained release directories are what make an older pinned identity reproducible from an ordinary checkout; once the installer rotates a build away, a protocol pinned to it stops being runnable without manual recovery, which is what stalled v5's Claude host.
- Local rotation has now stalled two protocols in a row. v5 pinned `Claude Code 2.1.220` and v6 pinned `2.1.239`; the Claude installer keeps roughly four recent versions, so both pins left the local install within days of being cut. Neither build was deleted at the source: the vendor release channel still serves both, and the runner accepts an explicit `--runner-path`, so re-fetching the pinned build completes the matrix. What exact-equality enforcement costs is that the protocol cannot be run from a normal checkout the moment the local build rotates, and it buys nothing the comparator's within-matrix identity checks do not already provide.

Treat a pinned identity as reproducible while that exact build is still addressable — on disk, or re-fetchable from the vendor channel, which is a convenience and not a guarantee. This is provenance, not attestation.

## External research

The [LLM-generated test evidence review](../docs/llm-generated-e2e-test-evidence.md) tracks 59 named sources: 21 verified, 14 qualified, and 24 not cleared. External studies motivate the methodology, but results from unit testing, custom browser agents, or vendor tools are not presented as measurements of this project.
