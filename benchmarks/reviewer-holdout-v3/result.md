# Reviewer holdout v3 result

Status: **INCOMPLETE — no final cross-model score**

Patterns #15 and #16 were subsequently reclassified from P0 to P1. A later
blind source-only audit also rejected the original #2 and #8 source examples as
too ambiguous or contradictory. Their fixtures were clarified before the
latest completed Codex run without changing the labels, thresholds, prompt, or
schedule. Those changes invalidated the earlier metrics. Subsequent skill
hardening changed the evaluated skill digest again, so the latest completed
Codex report is also historical and does not measure the current snapshot. The
underlying reports remain unchanged.

## Latest completed pre-hardening Codex run

The latest completed Codex `gpt-5.6-sol` run completed all 24 scheduled calls
with zero infrastructure errors. Its exact preregistered verdict for that
pre-hardening snapshot is **FAIL**:

- stable unique TP / FP / FN: 23 / 1 / 1
- stable precision / recall / F1: 0.9583 / 0.9583 / 0.9583
- stable false-positive-guard hits: 0 / 24
- repeated TP / FP / FN: 67 / 7 / 5
- repeated precision / recall / F1: 0.9054 / 0.9306 / 0.9178
- P0 stable-label recall: 0.8571 (required at least 0.90)

The only stable miss is the #2 archive-undo case. All three repetitions report
the same underlying missing restoration proof as #1 at the test declaration
instead of #2 at the undo action. The exact taxonomy/anchor scorer therefore
counts one FP and one FN. Two source-only auditors had independently preferred
#2, so the preregistered score is preserved rather than retroactively accepting
the model's alternative classification.

The complete historical report is `reports/full-codex.json`. Its evaluated
skill digest is
`400a93e8a6955491b938911188b9503968979d87bf428a7fdd17b95d4de115fc`.
`evidence-status.json` records the current checked-out skill digest and marks
this report stale when the two differ. It cannot be counted as the required
current-snapshot Codex report.

The first historical Codex `gpt-5.6-sol` snapshot completed 24/24 calls with no
infrastructure errors. It produced 23 stable true positives, 2 stable false
positives, and 1 stable false negative:

- stable precision: 0.9200
- stable recall: 0.9583
- stable F1: 0.9388
- repeated precision: 0.9079
- P0 stable-label recall: 0.8889
- frozen verdict: **FAIL**

The failed thresholds were stable precision (required at least 0.95) and P0
stable-label recall (required at least 0.90). The thresholds and report were not
changed after seeing the result. It is preserved as
`reports/pre-product-review-codex.json`.

An independent post-run product review then confirmed semantic defects in the
#16 missing-action-await surface and the #18 soft-assertion contract. The
product was corrected rather than leaving those defects in place to preserve a
score. That intentionally invalidates the old Codex report as evidence for the
current skill snapshot, so Codex must also rerun from the first scheduled call.

The 2026-07-30 fresh Fable run completed 11 calls before Claude Code returned
the account-level weekly-limit message on the next call. The fresh Opus run
returned the same limit immediately. Both attempts remain published as
`incomplete-limit-final-*.json`. Partial attempts are not merged, and
infrastructure errors are not converted into model false negatives.

Because the declared three-model matrix is incomplete, this bundle does not
issue:

- a cross-model comparison,
- a final Development Evidence Score,
- a 72-run benchmark viewer, or
- a passing v3 evidence manifest.

The machine-readable `evidence-status.json` therefore marks this bundle
`INCOMPLETE`, non-release-eligible, and unavailable for cross-host or score
claims. Its missing-artifact list and existing-artifact digests are enforced by
deterministic CI, along with a stale-required-artifact list and each report's
evaluated skill digest. This is an accepted documentation/evidence state, not
a passing benchmark result; claiming `COMPLETE` still requires the full
manifest, three fresh current-snapshot reports, and strict metric
re-derivation.

The corrected snapshot is frozen. Two initial source-only auditors
independently reconstructed only 22 findings, which forced the #2/#8 fixture
repair. Two new auditors then independently reconstructed all 24 current
findings, one representative guard per family, and the 7 P0 / 14 P1 / 3 P2
distribution. Codex completed a rerun from the first scheduled call for the
pre-hardening snapshot. Both Claude configurations must still wait for the
documented account-limit reset, after which they restart from call one. Because
further skill hardening made the completed Codex rerun historical, Codex must
also restart from call one. The frozen comparator runs only when all three
current-snapshot reports complete, without changing the corpus, prompt,
thresholds, or schedule.

This public synthetic development corpus is not a hidden benchmark and does
not establish unbiased generalization to unseen repositories.

Licensed under Apache-2.0 with the repository.
