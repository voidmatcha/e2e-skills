# Reviewer specificity v1 — superseded before run

Protocol status: **FROZEN / SUPERSEDED_BEFORE_RUN**. Corpus status: **NOT_CREATED**. Execution status: **NOT_RUN**. Result: **NONE**.

V1 is preserved byte-for-byte but must not be run. It required independent confirmation, clean rationales, licence evidence, and 24-pattern coverage without defining where those artifacts lived, their machine-readable form, or how the runner rejected missing or stale evidence. No corpus case, adjudication pass, evaluated-model call, or result exists under v1. [Reviewer specificity v2](../reviewer-specificity-v2/README.md) supersedes it with an explicit model-adjudication ledger and pre-run validation; the measurement design and thresholds remain otherwise unchanged.

This specificity-only benchmark was intended to contain only whole-case clean oracles: no finding for any frozen pattern in the submitted spec or its local dependency closure. It could not measure recall, finding precision, or F1.

No case, ledger, rationale, model report, or result exists under v1. The historical runbook is not evidence that the current runner supports this protocol.

## Why this design

The deferred full corpus requires positive-case discovery and exhaustive finding adjudication that is not affordable now. Clean cases still require complete review, but reviewers confirm candidates are non-findings instead of enumerating every true finding.

V7's eight clean cases produced the following when findings are counted anywhere in each case, rather than only at preregistered guard lines:

| Arm | Stably clean cases | Per-case specificity | Reported FPs over 24 case-repetitions | Repeated-run FPs/case |
| --- | ---: | ---: | ---: | ---: |
| full | 8/8 | 1.000000 | 1 | 0.125000 |
| catalog-only | 6/8 | 0.750000 | 6 | 0.750000 |
| no-skill | 1/8 | 0.125000 | 42 | 5.250000 |

Catalog-only's counts were `pw-c01=2`, `pw-c03=1`, and `cy-c04=3`; full had one on `cy-c04`. The catalog-only findings make `pw-c01` and `cy-c04` non-clean in a strict majority of repetitions, while full's single finding does not make its case non-clean.

V7's own `clean_case_specificity` is a different metric: it asks whether preregistered guard lines were flagged. A false positive elsewhere in a clean case does not reduce it, which is why V7 reports both full and catalog-only as `1.000000`. This protocol asks whether an arm reported any finding anywhere in the case before majority aggregation. The two numbers must not be compared as if they were the same metric. Guard-line hits remain a secondary diagnostic because they identify which lookalike shapes attract false positives.

All thresholds below were selected after these V7 results were observed. V7 is the calibration starting point and cannot validate them.

## Frozen inputs

```text
protocol: scripts/evals/reviewer-specificity-protocol-v1.json
protocol SHA-256: c3d8c035f40be955647ab552dfa934949a9098e35a6185ae5fea317e1f7a19fc
scanner SHA-256: 3056aa13c55f337dbd6a24f6a61859fdd47e0b3758e4cb4cbe795d050b04f3de
pattern reference SHA-256: 9c27480bd0fdde91d865c095de67bc0fc96606da79b13ed64e7e07807d5d5708
cases file and SHA-256: NOT_CREATED / NOT_AVAILABLE
corpus content SHA-256: NOT_AVAILABLE
selection ledger and SHA-256: NOT_CREATED / NOT_AVAILABLE
clean rationales and SHA-256: NOT_CREATED / NOT_AVAILABLE
evaluated skill snapshot and SHA-256: NOT_FROZEN / NOT_AVAILABLE
```

Freeze every missing input before the first model call. Any later edit requires a new protocol version.

## Corpus construction

Capture complete GitHub query snapshots before inspection. Apply the explicit 38-repository list and broader exclusions for all prior scans, case studies, PR targets, evals, holdouts, reviews, fixtures, and testbeds. Follow the frozen repository and scanner-candidate order; accept at most two unrelated cases per repository.

Every accepted case must be a lookalike: it must contain a scanner-produced, preregistered guard line that resembles a catalogued anti-pattern but is a non-finding in context. At the 24-case run minimum, fill one principal-guard slot for each of the 24 pattern IDs, assigning odd taxonomy-order slots to Playwright and even slots to Cypress for a frozen 12/12 split. At the 48-case target, fill one Playwright and one Cypress slot per pattern for a 24/24 split. Visit slots in frozen order and accept the first eligible clean candidate. If a slot cannot be filled, stop and version a new protocol; do not swap its framework or pattern. Selection may use only the frozen scanner, taxonomy and source order, framework and lineage constraints, and blinded adjudication. It must not use V7 error identities, model outputs, observed arm gaps, or discretionary similarity judgments. This makes the corpus rich in taxonomy-wide lookalikes without selecting around treatment weaknesses by another name.

For each candidate group, inspect the full spec-plus-reachable-dependencies boundary and write a non-finding rationale for all 24 patterns. A genuine finding discards the case; it is never repaired, trimmed, or relabelled here. Scanner output generates candidates only and proves neither a finding nor cleanliness.

### Independence

The maintainer also tuned the skill. Maintainer-only review is cheapest and supports only debugging or descriptive metrics. One non-author independently confirming every accepted case is the minimum claim-eligible tier. Two blinded reviewers plus a tie-breaker are stronger and more costly, but still do not make this public corpus sealed or representative.

## Metrics, thresholds, and size

The primary definition is:

> A clean case counts as clean for an arm in a repetition when that arm reports no finding of any pattern at any line in any file of the case; a case is stably clean when that holds in a strict majority of repetitions; per-arm specificity is the share of stably clean cases.

This aggregation is deliberately case-first. It does not require the same false-positive tuple to recur: any finding makes that case-repetition non-clean, and case-repetition cleanliness is then majority-aggregated.

The co-primary count metric sums every distinct reported `(pattern ID, severity, file, line)` tuple in every successful repetition, counting a tuple at most once within a case-repetition, and divides by the number of clean cases. It does not majority-collapse findings. This retains the V7 effect of 1 full-arm false positive versus 6 catalog-only false positives across 24 case-repetitions, or `0.125` versus `0.75` per case.

Secondary diagnostics are stable false positives per case, the share of case-repetitions containing any finding, and guard-line hit rates by guard ID. Guard diagnostics explain which lookalikes attract errors; they do not determine primary cleanliness.

| Gate | Threshold | V7 basis |
| --- | ---: | --- |
| Full per-case specificity | >= 0.95 | Under the new metric, V7 full was 8/8; at 48 this permits at most two non-clean cases. |
| Full repeated-run FPs/case | <= 0.125 | V7 full produced 1/8 FPs per case. |
| Full minus each control specificity | >= 0.125 | New-metric V7 full minus catalog-only was 0.25; require half that observed gap. |
| Specificity paired-bootstrap 95% lower bound | > 0 | Advantage must survive case resampling. |
| Each control minus full repeated-run FPs/case | >= 0.5 | V7 catalog-only minus full was `(6 - 1) / 8 = 0.625`; retain four fifths of that count-rate gap. |
| Count-rate paired-bootstrap 95% lower bound | > 0 | Carry all repetitions with the sampled case; repetitions are not bootstrap units. |

These are post-V7 calibration choices, not V7-validated thresholds. The `0.95` absolute floor preserves the observed perfect full score with limited tolerance. The `0.125` specificity lift requires a material case-level effect while allowing the new corpus's effect to be half the observed V7 full-versus-catalog gap. The `0.125` full count ceiling preserves V7's one-finding-per-eight-cases level. The `0.5` count-rate advantage requires most, but not all, of V7's observed `0.625` advantage. The paired interval is fixed-set resampling sensitivity, not population inference.

The observed full-versus-catalog paired discordance is **2 of 8**, both full-favouring, with one discordance in each four-case framework stratum. If that one-sided `1/4` rate repeats, a paired stratified bootstrap sample has no discordance with probability `(3/4)^N`. For a two-sided 95% percentile lower bound to exclude zero, that probability must be below `0.025`; algebra gives `N >= 13`.

The paired interval alone first becomes defensible at **16**, balanced 8/8, with two projected discordances per framework. Its zero-discordance probability is `(3/4)^16 = 0.0100226`. The protocol run minimum is nevertheless **24**, balanced 12/12, because the case-selection contract also requires one principal lookalike for every one of the 24 pattern IDs. At the observed rate that projects three discordances per framework and `(3/4)^24 = 0.00100339` zero-discordance probability. Do not run below 24: a smaller corpus either abandons taxonomy-wide lookalike coverage or lacks the paired justification.

The target remains **48 clean cases**, balanced 24/24. The observed rate projects to 12 full-favouring discordances; six net discordances meet the `0.125` point-delta gate. The `1/48` step also estimates the case and count rates more usefully than the minimum-size design.

This is analytic resampling sensitivity, not statistical power. Opposite discordances, a smaller new-corpus effect, finite-bootstrap Monte Carlo variation, or framework imbalance can keep the interval at zero. Forty-eight cases do not guarantee decisiveness.

## Superseded runbook — retained for history, do not execute

The commands below are preserved as v1's historical design, not as instructions. The runner and comparator now reject v1 and direct callers to v2.

V1 never reached corpus construction or a model call. Do not register inputs, execute these commands, bypass the supersession guard, or rename this protocol to another supported ID.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-specificity-v1"
CASES=scripts/evals/reviewer-specificity-v1.json
# Run these commands from a normal host shell, not an agent sandbox.
test -z "$(git status --porcelain)" || exit 1
test -f "$CASES" || exit 1
test "$(git rev-parse --show-toplevel)" = "$PWD" || exit 1
case "$OUT/" in "$PWD/"*) exit 1 ;; esac
mkdir -p "$OUT"

for ARM in full catalog-only no-skill; do
  python3 scripts/evals/run-reviewer-holdout.py \
    --cases "$CASES" \
    --protocol scripts/evals/reviewer-specificity-protocol-v1.json \
    --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
    --arm "$ARM" --repetitions 3 --allow-live --report-only \
    --output "$OUT/$ARM-codex.json"
done

python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  --cases "$CASES" \
  --protocol scripts/evals/reviewer-specificity-protocol-v1.json \
  --compare-arms --output "$OUT/arm-comparison.json"

# Copy artifacts into the checkout only after comparison completed.
mkdir -p benchmarks/reviewer-specificity-v1/reports
cp \
  "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  "$OUT/arm-comparison.json" \
  benchmarks/reviewer-specificity-v1/reports/
```

At 48 cases the matrix is `48 x 3 repetitions x 3 arms = 432` model calls; at the 24-case run minimum it is 216. Repetitions are not independent cases.

## Result and claim limits

There is no result. `FROZEN / NOT_RUN` is not PASS or evidence of lift.

If every gate later passes with independent clean confirmation, it supports only a same-model, same-runner, fixed-public-corpus statement: full met the declared specificity rate and exceeded each control by the paired margin.

It will not support recall, finding precision, F1, pattern detection, repair quality, usefulness, prevalence, time saved, cross-provider performance, population generalization, sealed evaluation, release-grade evidence, or cryptographic attestation. A maintainer-only corpus remains descriptive even with green gates.
