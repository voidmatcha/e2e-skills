# Reproduce reviewer holdout v3 evidence

This directory records a three-model public-development benchmark for the
`e2e-reviewer` skill: Codex plus two Claude configurations, spanning two
provider/runtime families. It is development confirmation, not a blind or
sealed estimate of generalization.

> **Historical snapshot notice (2026-07-30):** Patterns #15 and #16 were
> reclassified from P0 to P1 after this evidence was recorded. A later blind
> source-only audit also rejected the original #2/#8 fixtures until their
> promised-outcome and no-postcondition boundaries were made unambiguous. Those
> source changes invalidate every committed v3 metric/report as evidence for
> the current snapshot; historical reports are preserved unchanged and require
> a fresh full-matrix run before new current metrics can be claimed.

The v3 corpus began as a frozen snapshot, but pre-remediation Codex output and
incomplete Claude attempts were inspected while the skill, scanner, and corpus
were being corrected. The then-evaluated snapshot was re-audited and frozen
again before the declared final run attempts. It contains eight repository-shaped
cases, 24 labeled findings, and 24 explicit false-positive guards. The findings
cover every stable base family in the 24-pattern catalog across Playwright and
Cypress. Because earlier output and product-review feedback informed the
remediation, the final run must not be described as a blind preregistration.
After the #15/#16 reclassification, two source-only auditors independently
reconstructed only 22 findings and exposed ambiguous/contradictory #2/#8
fixtures. The sources were clarified without changing their labels. Two fresh
auditors then independently reconstructed all 24 findings, one representative
guard per family, and the current 7 P0 / 14 P1 / 3 P2 distribution. The full
labeled corpus still contains 24 finding anchors and 24 guard anchors.

The fixed release matrix is:

- Codex `gpt-5.6-sol`
- Claude `claude-opus-5`
- Claude `claude-fable-5`
- three repetitions per case and model configuration
- SHA-256-seeded schedule
- strict-majority stability

`oracle-audit.md` records two source-only model audits performed before the
live model run. When the matrix is complete, `reports/` contains raw per-run
model output, parsed predictions, metrics, and a cross-model comparison. Files prefixed
`incomplete-` preserve infrastructure-failed attempts and are never scored as
complete results. `reviews/` contains a frozen review protocol and separate
read-only product critiques. Pre-fix and remediation critiques are development
feedback, not independent benchmark scoring or blind adjudication.

## Reproduce the model runs

Run each model configuration with the same frozen corpus, protocol, and
repetition count:

Each command writes its report before exiting. Exit codes are `0` for `PASS`,
`1` for `FAIL`, and `2` for `INCONCLUSIVE`; `--report-only` preserves the
artifact but never suppresses a failing decision.

```bash
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v3.json \
  --protocol scripts/evals/reviewer-validation-protocol-v3.json \
  --runner codex --model gpt-5.6-sol --repetitions 3 --allow-live \
  --report-only \
  --output benchmarks/reviewer-holdout-v3/reports/full-codex.json

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v3.json \
  --protocol scripts/evals/reviewer-validation-protocol-v3.json \
  --runner claude --model claude-opus-5 \
  --repetitions 3 --timeout 300 --allow-live \
  --report-only \
  --output benchmarks/reviewer-holdout-v3/reports/full-opus.json

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v3.json \
  --protocol scripts/evals/reviewer-validation-protocol-v3.json \
  --runner claude --model claude-fable-5 \
  --repetitions 3 --timeout 300 --allow-live \
  --report-only \
  --output benchmarks/reviewer-holdout-v3/reports/full-fable.json
```

After all three reports complete, compare them:

```bash
python3 scripts/evals/compare-reviewer-holdouts.py \
  benchmarks/reviewer-holdout-v3/reports/full-codex.json \
  benchmarks/reviewer-holdout-v3/reports/full-opus.json \
  benchmarks/reviewer-holdout-v3/reports/full-fable.json \
  --cases scripts/evals/reviewer-holdout-v3.json \
  --protocol scripts/evals/reviewer-validation-protocol-v3.json \
  --output benchmarks/reviewer-holdout-v3/reports/cross-host.json
```

This is a public development holdout, not a hidden or sealed benchmark.
The source-only model auditors used the same model family as the implementation
host and are not human annotators. The run can demonstrate reproducibility on
these cases; it cannot establish unbiased generalization to unseen repositories
or all future model versions.

Live runner children receive a strict environment allowlist. Codex receives a
fresh private home containing only a verified 0600 copy of the parent
`auth.json`; parent settings, plugins, skills, and other Codex config are not
staged. Claude receives only its named authentication/config path, and a custom
runner receives no Codex/Claude authentication variables. Generic tokens,
cloud credentials, proxy variables, and shell/runtime injection variables are
removed. Parent authentication is not a disposable scoped credential, so this
development boundary does not replace release isolation.
An arbitrary executable wrapper is not an isolation proof: the bundled harness
keeps non-public reports `INCONCLUSIVE` even when execution is delegated.
Corpus paths are rejected when they collide with runner-control surfaces,
including `.skill/` and agent instruction files. Every call records and checks
the actual staged-skill digest against the frozen evaluated-skill digest before
and after execution. The model prompt contains only `SKILL.md`,
`references/pattern-reference.md`, and `references/verification-rules.md`, plus
the complete case sources. Reports keep the full canonical evaluated-skill
digest separate from the model-visible prompt-set digest. A full,
required-repetition development run may return performance `PASS` or `FAIL`
while remaining `release_eligible: false`; `execution_complete` and
`evidence_limitations` record those independent facts.
Here `--arm full` means the full zero-tool semantic-review prompt, not the
scanner/browser/subagent production workflow. The `catalog-only` and
`no-skill` ablations are named in report provenance. All arms share only a
minimal ID/title/severity output legend for exact-match comparability, so the
no-skill arm is not a taxonomy-free baseline.

If the matrix completes, any **Development Evidence Score** must follow the
published [`scorecard.md`](scorecard.md) rather than a post-hoc subjective
grade. The separate
[`methodology bias audit`](reviews/methodology-bias-audit.md) rejects that
score type as an unbiased general skill-quality score.

## Current execution status

The first historical 2026-07-30 Codex snapshot completed all 24 calls with zero
infrastructure errors, but its frozen result was `FAIL`: stable precision was
0.9200 against a 0.95 floor, and P0 stable-label recall was 0.8889 against a
0.90 floor. That report is preserved as
`reports/pre-product-review-codex.json` without threshold changes. A subsequent
independent product review found real #16 and #18 contract defects and later
reviews found incomplete Promise-consumer, action-method, and POM scope. The
skill was corrected, then #15/#16 were reclassified from P0 to P1 on runtime
evidence and the #2/#8 fixtures were clarified after blind source audit. The
old report therefore measures neither the current skill nor the current
oracle.

The latest completed, pre-hardening Codex rerun completed 24/24 calls with no
infrastructure errors.
Stable unique precision/recall/F1 are each 0.9583 (23 TP, 1 FP, 1 FN), with
zero stable guard hits. Repeated precision/recall/F1 are
0.9054/0.9306/0.9178 (67 TP, 7 FP, 5 FN). The preregistered verdict remains
`FAIL` because P0 stable-label recall is 0.8571 against the 0.90 floor. The
stable error is an exact #1-versus-#2 taxonomy/anchor disagreement on the same
missing restoration proof; it was not post-hoc rescored.
Its evaluated skill digest is
`0ef4839b6bde078a4599e6354dcd60bb522c01a91534086d6f292d5217018214`;
the current hardened skill digest is
`33832ed8029e2fdff37c5f72b7e68539a9e6f28fc03fc16d514057c0bdc88e0b`.
The report is therefore historical and does not satisfy the current-snapshot
Codex requirement.

The fresh Fable attempt completed 11 calls before Claude Code returned
`You've hit your weekly limit · resets Aug 3 at 4am (Asia/Seoul)` on the next
call. The fresh Opus attempt returned the same limit immediately. Their
checkpoint reports are preserved with `incomplete-` prefixes. They are not
merged with older attempts, scored as false negatives, or used to create a
cross-model aggregate. Consequently, there is no final Development Evidence
Score or 72-run viewer yet. `evidence-status.json` records the exact missing
and stale release artifacts, forbids cross-host, score, and release-eligibility
claims, and pins both the file and evaluated-skill digests of the historical
Codex report and the two final incomplete Claude attempts. Deterministic CI
accepts that explicit non-release state but still fails on a stale
missing/stale-file list, changed evidence, a false current-snapshot claim, or
any partial claim of completion. Once the status changes to `COMPLETE`, the
same check requires the full manifest and re-derives all three current-snapshot
reports and the cross-host comparison before accepting the bundle.

The first Fable attempt exposed that the runner's default 180-second call cap
was too short for one successful response. That incomplete attempt remains
published, and the fresh Claude runs use a 300-second infrastructure cap.
The latest completed pre-hardening Codex run completed every call under 300
seconds with no timeout.
Timeout was not preregistered in the v3 protocol;
this post-freeze operational adjustment is a limitation even though no label,
prompt, schedule, model, or decision threshold changed.

Licensed under Apache-2.0 with the repository.
