# Independent evaluator-integrity audit

Final verdict: **APPROVE, 97/100**.

The auditor was barred from the v3 labeled corpus, holdout sources, scored
reports, oracle audits, scorecard, and model reviews. It used synthetic
reports and temporary mutations to test the evaluator boundary.

The initial 78/100 audit reproduced three fail-open defects:

- reports with one repetition could satisfy a protocol declaring three release
  repetitions;
- missing or null workspace/snapshot provenance could be treated as scoreable;
  and
- an empty evidence manifest could satisfy the manifest validator.

The repaired comparator now requires the protocol's exact release repetition
count, lowercase SHA-256 values for input/snapshot/run digests, unchanged
source and snapshot inputs, declared provenance enums, and a valid
public-corpus/external-wrapper combination. Regressions reject one-run reports,
null workspace digests, missing snapshots, invalid provenance, and empty or
extra manifest entries.

A separate cross-version regression handles the approximately `1e-16`
difference between Python 3.9 and Python 3.14 float summation. Recursive metric
comparison accepts only a `1e-15` numerical tolerance; a `1e-12` change and any
non-numeric status change remain rejected. The frozen Codex report re-computed
to the same verdict under both Python versions.

The exact manifest set now pins the corpus and source fixtures, protocol,
runner, comparator, complete evaluated skill surface, three final model
reports, cross-model result, fixture-fault runner/classifier/report, frozen
review protocol, methodology and integrity audits, final Fable/Opus/Codex
product reviews, Development Evidence Score result, and official iteration-6
viewer artifacts. Future artifacts remain fail-closed until they exist and
their SHA-256 values match.

The remaining three points reflect external limitations rather than a
confirmed code defect: public development data, unattested local runner/model
identity, and a shared-evaluator rather than independently implemented scorer.

Licensed under Apache-2.0 with the repository.
