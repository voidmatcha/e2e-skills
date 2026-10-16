# Codex v4 and OSS repair handoff

This handoff describes the latest Codex/OSS repair. It supersedes the supplied generator-loop-v2 builder message and the prior material-deferral handoff as evidence for this work. Both material findings and both cheap minor findings are repaired in an unfrozen Codex v4 successor plus unfrozen OSS files. No frozen predecessor file was edited.

## Baseline and exact artifact inventory

Baseline HEAD: 265b0c478fb1404d95863db64853941bd3901a9e. The checkout already contained untracked Codex/Claude successor and other benchmark work. Before editing, this worker recorded SHA-256 digests of 5,566 preexisting files, including all 30 existing freeze.json files. The baseline inventory excludes Git internals, bytecode, testbed and dependency directories. It establishes preservation during this repair, without claiming the checkout began clean or certifying earlier builders.

Six new v4 files:

- [V4 runner](../../scripts/evals/run-generator-multimodel-v4-codex.py).
- [V4 evidence parser](../../scripts/evals/generator_v4_codex_evidence.py).
- [V4 repair and inherited-contract tests](../../scripts/ci/test-generator-v4-codex-repairs.py).
- [V4 protocol](../generator-multimodel-v4-codex/protocol.json).
- [V4 README](../generator-multimodel-v4-codex/README.md).
- [V4 changes](../generator-multimodel-v4-codex/CHANGES.md).

Six modified unfrozen OSS files:

- [OSS runner](../../scripts/evals/run-generator-oss-eval-v1.py): import the repaired v4 runner/evidence; retain the frozen v3 adapter and pooled analysis.
- [OSS tests](../../scripts/ci/test-generator-oss-eval-v1.py): require the v4 import path.
- [OSS protocol](protocol.json): select v4 imports and record identity/Git policy and frozen predecessor status.
- [OSS README](README.md): identify v4, frozen v3 and live limitations.
- [OSS changes](CHANGES.md): append this repair and validation record.
- [This handoff](HANDOFF.md): matching baseline, inventory, results and limitations.

The external worker history was not overwritten. Frozen v1/v2/v3 runners, evidence, protocols, README prefixes and all freeze records remain preserved. Claude successor files remain outside this repair.

## Repairs and verification

Explicit conflicting identities invalidate fidelity/admission, harness verification and cost completeness; root fallback requires an unnamed transcript. Unrelated rollouts contribute no tool or token evidence. Correct matching identities and unnamed-root positive controls still work. Entry remains undecided on observation conflicts. Smoke Git initialization strips inherited routing/configuration, disables system/global configuration/templates, explicitly targets disposable project-local metadata and verifies the local HEAD. Actual temporary Git regressions assert sibling destinations stay absent, including at the mocked smoke-call boundary.

Eight existing offline suites pass 352 tests: v3 protocol 49, v3 harness 71, v3 smoke 14, v2 protocol 49, v2 harness 68, v2 smoke 11, container adapter 11 and OSS 79. The v4 suite passes 147 checks: 134 inherited contracts plus 13 new regressions, totaling 499 passing checks across the nine suites. Two more mutation checks confirm that the old parser and ambient Git initialization each fail the corresponding regression. The frozen source suites are unchanged; two inherited expectations are explicitly replaced in memory for the repaired semantics. No tests were skipped.

The temporary launcher disables bytecode, blocks real model/container/network/socket/signal/system operations and uses an audit hook to confine writes and actual Git init/add/status to disposable temporary fixtures. Exact historical baseline commit commands are stubbed; no commit is created. Hostile regression environments reach Git unchanged from the helper, so launcher sanitization cannot mask a broken repair. The final v4 run stubbed four baseline commits and allowed 14 temporary Git operations; the eight predecessor/OSS suites stubbed eight baseline commits. Initial launcher cleanup false positives and a documentation-case assertion were fixed before the final passing run.

Repository gates pass: /bin/bash -p scripts/ci/review.sh reports 16 passed, zero warnings/errors; /bin/bash -p scripts/ci/pre-push-security.sh reports 10 passed, zero warnings/blockers. Two additional read-only checks validate actual v1/v2/v3 frozen() bindings, including README prefixes and recursive predecessor inputs, and current v4/OSS protocol wiring.

The final pre/post SHA-256 inventory confirms exactly the six modified OSS files and six new v4 files listed above. Every other inventoried preexisting file retains its bytes, including all Claude successor files and all 30 existing freeze.json files. No changed preexisting digest occurs in any existing freeze binding. No freeze file was added. This is a repair-session preservation check, not an attestation about historical exposure or earlier builders.

## Remaining owner decisions and validation gaps

No material code finding remains deferred. Freeze/campaign authorization, reference calibration acceptance and independent exposure acceptance remain owner decisions. V4 and OSS are unfrozen and no prior admission or harness pass is reused. Live configuration enforcement, child tool/approval inheritance and token additivity, real generator delivery/browser scoring, Zeppelin calibration and cleanup remain unverified. Historical non-exposure is not certified; existing OSS exposure disclosures remain intact.

No model CLI call, container, server, listening-port/process operation, network access, dependency install, live benchmark, campaign-cache write, freeze, commit or push was performed.
