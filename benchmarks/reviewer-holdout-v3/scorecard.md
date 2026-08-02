# Development Evidence Score (100-point rubric)

This rubric was frozen before complete Fable or Opus results were available,
after four successful Fable calls and one infrastructure timeout had been
observed. It limits post-hoc scoring discretion, but it is not a fully blind
preregistration because those partial calls, a pre-remediation Codex run, and
development product reviews were already visible.

No score is currently available. `evidence-status.json` forbids publishing a
Development Evidence Score while the declared matrix is incomplete; this
rubric becomes applicable only after strict verification of a `COMPLETE`
status and its full evidence manifest.

This is a self-authored public-development evidence-maturity score, not an
unbiased general skill-quality score. V3 external validity is **not
established**: there is no sealed real-repository sample, human oracle, or
control arm. See `reviews/methodology-bias-audit.md`.

| Dimension | Points | Fixed scoring rule |
|---|---:|---|
| Taxonomy and corpus design | 15 | 8 for all 24 stable base families represented; 4 for an explicit near-miss guard per family; 3 for two source-only auditors independently reconstructing the exact set. |
| Executable behavior proof | 15 | 10 for a complete strong-pass / fault-fail / weak-green matrix; 5 for both Playwright and Cypress with at least six distinct behavior or assertion operators. This measures fixture-test fault sensitivity, not reviewer detection across all 24 families. |
| Repeated exact-match performance | 30 | Across the three declared model configurations: 10 × mean stable precision, 10 × mean stable recall, 5 × mean repeated precision, and 5 × mean P0 stable-label recall. Infrastructure-incomplete reports receive zero for this dimension until completed. |
| Cross-configuration robustness | 10 | 4 if every individual report passes its preregistered gate; 3 if maximum pairwise stable-recall gap is at most 0.10; 3 if minimum pairwise stable-prediction Jaccard is at least 0.80. |
| Evaluator integrity and reproducibility | 15 | 5 for frozen final skill/corpus/protocol/schedule and pre/post digests; 4 for fail-closed parse, mutation, timeout, and incomplete-run handling; 3 for shared-evaluator deterministic raw-output re-parsing and rescoring; 3 for fixed N-configuration comparison. |
| Oracle and generalization quality | 10 | A public synthetic corpus with source-only model adjudication is capped at 3. Two additional points require executable causal linkage from labeled weak tests to browser-level app faults. The remaining 5 require a sealed external corpus with two independent human annotators, a third adjudicator, and a generated-test fault-detection arm rather than reviewer exact-match alone. |
| User-facing clarity | 5 | Reproducible install/run instructions, exact scope, honest limitations, and an auditable result viewer. Independent product reviews may reduce this score for confirmed documentation or usability defects. |

Use unrounded metric values in the calculation and round only the final total
to one decimal place. Do not award partial credit inside the binary dimensions
unless the rule explicitly uses a metric. A recovered infrastructure retry may
support a complete result only when the failed attempt remains published and no
semantic input or threshold changes.

This score measures the current public-development evidence bundle when all
declared reports are present. It is not a probability that an arbitrary future
finding is correct and must not be presented as a general skill-quality score.

Licensed under Apache-2.0 with the repository.
