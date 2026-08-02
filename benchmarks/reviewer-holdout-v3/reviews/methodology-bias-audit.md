# Independent methodology and bias audit

Verdict: **REJECT as an unbiased general skill-quality score.**

Confidence: high (0.94) on the methodology assessment and medium (0.78) on
the numerical consequences. The auditor was barred from the labeled corpus,
holdout sources, scored report bodies, oracle audits, and model reviews.

The existing 100-point rubric can describe maturity of the self-authored
public-development evidence bundle. It cannot defensibly estimate unbiased
general skill quality:

1. The freeze chronology is not independently timestamped. The rubric itself
   records that partial Fable calls, a pre-remediation Codex run, and product
   reviews were already visible.
2. A public synthetic, output-informed corpus can earn up to 95/100 without a
   sealed external set or human adjudication.
3. The behavior dimension awards full credit for six operators across two
   frameworks. The current 11-operator matrix covers fewer than half of the 24
   families and proves fault sensitivity of fixture tests, not reviewer
   detection of every fault.
4. Three repetitions of the same eight cases are correlated stability trials,
   not independent accuracy samples. Several rubric dimensions reuse the same
   outcomes, and label-level Wilson intervals are not generalization bounds.
5. The declared matrix is three model configurations but only two
   runtime/provider families: Codex plus two Claude models. Calling these three
   independent hosts overstates independence and gives one provider family
   two-thirds of the performance mean.
6. V3 has no catalog-only or no-skill control, so it cannot identify skill lift
   separately from the base model.
7. The comparator imports the runner's parsing, scoring, metric, and status
   functions. It independently re-parses serialized raw output, but is a
   shared-evaluator deterministic re-derivation, not an independently
   implemented scorer.
8. The public-oracle 0–5 points and clarity deductions are not fully
   mechanical.
9. Runner/model/CLI identity is declared local provenance, not signed
   execution attestation.

## Required interpretation

- Call the published number a **Development Evidence Score**, not an unbiased
  skill-quality probability.
- Report external validity separately and mark it unestablished for v3.
- Treat repetitions only as stability evidence.
- Describe the matrix as three models across two provider/runtime families.
- Describe comparator evidence as shared-evaluator deterministic
  re-derivation.

## Next benchmark

A generalization claim needs a pre-call timestamped commit or tag, fixed
timeout/order/rubric, an external sealed real-repository sample, two
independent human annotators plus a third adjudicator, case/repository-level
statistical units, equal-weight independent provider/runtime families, full
skill/catalog-only/no-skill arms, behavior coverage tied to taxonomy families
and reviewer detection, and either an independently implemented scorer or a
more limited integrity claim.

Licensed under Apache-2.0 with the repository.
