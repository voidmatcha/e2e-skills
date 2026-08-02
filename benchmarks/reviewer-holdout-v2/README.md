# Reviewer holdout v2 evidence

This directory freezes the evidence behind the public-development benchmark
table in `docs/ai-reviewer-benchmark.md`.

- `oracles/initial-oracle-25.json` is the exact 25-positive/28-guard oracle used
  by the first complete Codex and Claude runs.
- `oracles/current-oracle-r4-30.json` freezes the later 30-positive/31-guard
  development oracle used to audit the output-conditioned reports. It is kept
  here rather than pointing at the mutable current corpus or taxonomy.
- `reports/initial-full-*.json` contain every scheduled run's raw model output,
  parsed findings, exact-match score, stable aggregation, and provenance from
  that historical evaluator.
- `reports/catalog-control-*.json` and `reports/ablation-*.json` freeze the
  catalog-only controls and the preregistered comparison.
- `oracle-revisions.json` records every later output-conditioned correction.
- `post-run-adjudications.json` records the four stable predictions from the
  hardened r3 run that isolated verifiers confirmed were real findings omitted
  by the oracle. The original report is not rescored.
- `evidence-manifest.json` pins every immutable artifact by SHA-256. CI
  re-derives the documented score table and rejects artifact drift.

The historical reports predate the hardened evaluator now in
`scripts/evals/run-reviewer-holdout.py`. They remain evidence for the initial
oracle only and are intentionally not rewritten to the current schema. The
current evaluator snapshots its corpus and skill, rejects source drift,
gates repeated precision, and the cross-host comparator re-parses raw outputs
instead of trusting serialized scores.

This is auditable public development evidence, not a sealed or unbiased
generalization benchmark. The r2/r3 oracle changes were informed by model
outputs and are marked `output_conditioned: true`. The r3 performance result is
also marked oracle-invalidated after its post-run adjudication.
