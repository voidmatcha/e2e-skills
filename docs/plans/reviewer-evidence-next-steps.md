# Reviewer evidence: current plan

Status snapshot: 2026-09-29. This page preserves the 2026-09-24 specificity and release-planning record below; it is not a frozen protocol. The current reviewer-evidence state and remaining work are summarized here.

## Reviewer evidence update

- **Completed development evidence:** [v8–v19](../../benchmarks/STATUS.md) ran or reached a recorded terminal status under their own frozen protocols; v11 stopped when its pinned model was retired, and v13/v15 are inconclusive. [V20](../../benchmarks/reviewer-holdout-v20/README.md) and [v21](../../benchmarks/reviewer-holdout-v21/README.md) measured the #2 severity question; v21 did not support explicit wording. The Lean severity-model drift check is implemented and validated. V17 tested that model in a prompt against catalog-only and failed its improvement gate, so it remains a developer-side check (`python3 scripts/dev/reviewer-contract.py`).
- **Completed real-code evidence:** [fixpair-v1](../../benchmarks/fixpair-v1/README.md) publishes batches B+C+D: 25/33 strict BEFORE recall with the skill versus 13/33 without it, with zero matched AFTER false alarms in either arm. These are model-labeled development cases, not human-adjudicated release evidence.
- **Historical scanner boundary:** v19, fixpair-v1, and the semantic-mutant results used the reviewer skill before the 2.0.0 scanner fixes (`976c3fa`). V19 disabled model tools and did not invoke the standalone scanner.
- **Remaining:** Obtain human-labeled or independently sealed evaluation; add independently sourced real-code cases for semantic patterns `#2`, `#20`, and `#23` and cover `#12` in semantic mutants; and opt the [auth-retry policy](../ai-reviewer-benchmark.md) into the next newly frozen protocol. Existing v11–v17 retry policies remain unchanged.

## Resolved issue

- **Resolved, no wording change needed:** [v20](../../benchmarks/reviewer-holdout-v20/README.md) and [v21](../../benchmarks/reviewer-holdout-v21/README.md) measured the #2 partial-verification severity question. V21 found no #2 severity errors under either revision (24/24 each) and a decline in overall F1 with explicit wording. The current 2.0.0 text already produces P1 for partially verified #2 instances under `reporting.md`; the v20 doc-only clarification was a post-run proposal and would point back to the catalog P0 severity. V20's 10/13 before-arm result is likely a corpus-construction effect.

The dated sections below describe their own historical results and proposed specificity sequence. They do not supersede this update.

## Objective and scope

Determine whether the reviewer avoids false alarms on genuinely clean Playwright/Cypress tests, and whether the full skill adds value beyond no skill and the pattern catalog alone. Collect auditable evidence before making a specificity or skill-lift claim. Keep broader accuracy, recall and release-grade validation separate: clean-only specificity cannot establish them.

The current work is evaluation infrastructure, not an upstream fix campaign or a new product feature. Use Codex for the active development path. Jev is an optional future comparison, not a prerequisite or replacement for source evidence. No installation, paid API invocation, publication or upstream mutation is authorized by this document.

### Current continuation: Claude code review (2026-09-24)

The user authorized Claude to review the release executor and verifier in a separate context. This development review can proceed while external release roles remain unavailable. Its remit is concrete implementation defects in admission, input freezing, one-attempt execution, witness ordering and signed-result reconciliation. Give it a hashed source snapshot and the relevant tests without earlier reviewer verdicts; retain its raw response and verify proposed defects locally before changing code. Authentication uses the user's existing Claude Code access. This authorization does not start the 1,080-call release matrix.

The first review uses Claude Opus with no tools, one call and a 900-second timeout. The recorded source packet contains thirteen implementation, protocol and test files. Findings, failed calls and unresolved dependencies remain visible. Claude's review supplies AI code-review feedback; the release protocol's external custody, operator and human-adjudication requirements remain separately applicable. Their absence must not be used to block this already authorized code-review work.

The call completed in 690 seconds with six proposed findings and no source mutation during review. Local adjudication confirmed inconsistent case-ID admission, a malformed assembler-header exception, a missing final tree check, and a mock-only refusal-test gap. The alleged prompt-order instability was refuted by the fixed `INITIAL_FILES[arm]` iteration; the raw verifier already validates journals before accessing their header. The separate non-root witness artifact-access issue is real but narrower than claimed: socket access does not grant artifact access, while privileged witness operation is mechanically possible and still unvalidated. The [operator handoff](../../benchmarks/reviewer-release-v1/OPERATOR_HANDOFF.md#release-admission-sequence) now states this deployment boundary explicitly. Preserve the original response, registration and local adjudication together in the external development artifact directory `claude-release-review-20260924.fhtftI`; raw response SHA-256: `f8bdea2c813bb8515241dd980b731bdb590c5d7b7a1feee0ca7e98d9ac319235`. This review does not establish skill effectiveness or authorize a release claim.

## What happened

### Authorized follow-through (2026-09-24)

The user authorized this local sequence without further routine confirmations:

1. Refactor the Cypress publisher's shared validator without weakening validated-byte loading, add paired malicious/benign artifact and DOM cases, run bounded model-decision probes, then validate the changed tree. Keep the native no-replace rename protection. A tool-free decision probe does not attest real browser/shell containment, and neither local changes nor a passing test change a hosted security badge.
2. Complete the candidate witness artifact-access boundary with a dedicated read-only group. Preserve private signing keys and operator journals, reject unsafe identities and permissions, and never recursively change sealed input permissions. Real distinct-UID integration remains required; same-UID or mocked tests do not satisfy it.
3. Run a fresh public-development three-arm reviewer comparison with frozen inputs and retained failures. Reuse the unchanged v7 public corpus, schedule and thresholds only as a development regression, not as a replacement counted run or the sealed release study. Register the current evaluated bytes and bounded call budget before invocation; do not tune or trim the skill during the matrix.
4. Review the result before deciding what to remove. Keep supported guidance, identify redundant or unmeasured guidance without claiming a causal ablation, and prepare presentation-ready claims with denominators and explicit limits. If the full skill's advantage over the catalog is inconclusive, retain that result rather than optimizing to a passing rerun.

Publication, credential changes, global group/permission changes and a release certification are not implied by this sequence. Work that is possible locally continues independently of the missing external release roles.

The first security decision smoke completed four tool-free Codex calls on paired malicious/benign Cypress reports and generator snapshots. Neither attack elicited its requested command, collector contact or failure/locator suppression; both controls retained useful analysis. This is not real tool containment, a population success rate or evidence of skill-attributable resistance. The Cypress answers also exposed a quality limitation: a single failure was called consistent, and the benign answer assigned test-defect/P2 without application evidence. Retain that counterevidence. Exact prompts, registration, responses and adjudication are in the external `security-decision-smoke-20260924.7gy45t` artifact directory; no outcome-selected retries were performed.

The attempted Cypress shared-module refactor was rejected before delivery. Replacing descriptor-bound `exec` with private snapshot imports introduced two bootstrap loaders, temporary-file I/O and module-cache handling while still executing trusted Python source. It did not demonstrate a safety improvement. Keep the original trusted-sibling validated-byte implementation and strengthen adversarial symlink and post-open replacement tests instead. The hosted dynamic-execution warning may remain; no badge-clearance claim is warranted.

The planned current-reviewer replay is bounded to the unchanged twenty public v5 cases, three repetitions and three sequential v7 arms (`full`, `catalog-only`, `no-skill`): at most 180 calls, 180 seconds per call, no retries or replacement. Its separate registration and outputs live in `current-reviewer-three-arm-20260924.H3KUi4`. The evaluated working-tree bytes, including the existing uncommitted product changes, must remain identical across arms; the driver stops on input drift or an incomplete arm. This is the tool-free semantic reviewer surface, not an end-to-end scanner/browser workflow, and its output legend means the no-skill arm is not taxonomy-free. Keep both the historical counted v7 result and this replay's public-corpus contamination limits visible.

### Follow-through outcome and presentation claims

The local four-step sequence reached the following boundary. No commit, push, installation, hosted rescan, global permission change or release matrix was performed.

| Step | Local outcome | Remaining limit |
| --- | --- | --- |
| 1. Security hardening and validation | Added Cypress symlink/post-open-replacement regressions and four paired security eval fixtures; completed four tool-free decision calls; full local CI passed | The original validated-byte loader remains. One Cypress control overclassified severity. No live browser/shell containment or hosted badge clearance is established |
| 2. Witness artifact access | Explicit runner UID/artifact GID, distinct non-root identities, exactly four input and five output artifacts shared as `0750` directories / `0640` files, private key/journal boundaries; focused and full-CI tests passed | Real distinct-UID Linux integration is unrun. Docker daemon was unavailable. Keep release readiness incomplete and the external custody/adjudication requirements intact |
| 3. Three-arm comparison | All 180 calls completed with zero infrastructure errors, no retries and unchanged evaluated tree; comparator returned `FAIL` | Twenty previously observed public cases, not 180 independent samples or a sealed release study |
| 4. Diet and claims decision | Recorded negative results, inspected the four stable extra predictions, selected bounded simplification candidates below | No instruction-level causal ablation; do not delete safety gates or relabel this replay to manufacture a pass |

The full `/bin/bash -p scripts/ci/ci-local.sh` run exited zero before the matrix. The final smell scan reported zero P0 hits; the fixture scan retained twelve non-P0 heuristic/triage hits. Optional AST/parser integrations and the historical pinned-Claude live-path round trip retained their disclosed skips. This is local code/evidence-contract validation, not fresh browser execution or Linux compatibility proof. The CI transcript is retained with the security smoke artifacts. Final documentation checks are separate from this pre-matrix code run.

The replay used `codex-cli 0.155.1`, `gpt-5.6-sol`, the unchanged v5 corpus and v7 protocol, and the dirty tree based on `1d2bb11e199ae7babb6eb4afd1afb60bb3e99ee3`. Its skill digest is `e6b7bc791fc0b66f52ace61f15f964e81faad62522e5c39b3162e1fc664577a6`; evaluated dirty-tree digest is `4a2708606d0fc06846163dd24cf1830ea5fd2ea3157c6502389f036885e75521`. Documentation added after execution is not part of that measured tree. Raw responses are retained in each arm report.

| Arm | Stable TP / FP / FN | Stable precision | Stable recall | Stable F1 | Repeated precision | Clean cases without stable findings | Mean prompt UTF-8 bytes |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: |
| full | 24 / 4 / 0 | 0.857143 | 1.000000 | 0.923077 | 0.781609 | 7 / 8 | 174,617.7 |
| catalog-only | 24 / 2 / 0 | 0.923077 | 1.000000 | 0.960000 | 0.804598 | 7 / 8 | 90,124.7 |
| no-skill | 15 / 20 / 9 | 0.428571 | 0.625000 | 0.508475 | 0.358333 | 2 / 8 | 4,091.7 |

All three arms failed at least one absolute gate. Full failed stable precision, repeated precision and clean-case specificity. Full-minus-catalog stable F1 was `-0.036923`, with paired case-bootstrap 95% interval `[-0.111111, +0.031120]`; this does not establish either full superiority or general catalog superiority. All six full-vs-no-skill relative checks passed, but the overall comparator still failed because the full absolute gate and four catalog-relative checks failed. `skill_lift_claim_eligible` remains `false`. Prompt bytes measure input size, not billed tokens, cost or causal latency savings.

The canonical historical [v7 result](../../benchmarks/reviewer-holdout-v7/README.md) remains unchanged. These are current public-development replay results, not a replacement counted run. They cannot isolate the cause of differences from the older run: skill/evaluator bytes, CLI and provider behavior are not all held constant across those dates. The fixed public cases have been inspected and used for earlier corrections, and the bootstrap describes sensitivity to resampling those cases, not population generalization or model-run stochasticity.

#### Extra-prediction audit, without rescoring

The full arm's four stable extra tuples were checked against the frozen source and current rules. These judgments explain limitations; they do not alter the labels, score or `FAIL`:

| Case and reported tuple | Local evidence assessment |
| --- | --- |
| `pw-a01`, `#13`, P1, `tests/ledger.spec.ts:11` (2/3 repetitions) | Likely POM-ownership overreach: the supplied POM opens `/ledger`, while the separate raw navigation opens `/ledger/filters`; the visible source does not establish ownership of that second page |
| `pw-a04`, `#13`, P1, `tests/profile.spec.ts:10` (2/3) | Overlap/exact-anchor mismatch: the labels already represent POM bypass at line 7 and missing await at line 10. The additional #13 tuple is counted as an FP, not another independently established defect |
| `cy-a06`, `#1`, P0, `cypress/e2e/board.cy.ts:10` (2/3) | Unsupported silent-pass claim: line 13 asserts summary visibility. The supplied fixture/render-guard mismatch is already #23 and makes the test fail; it does not erase the assertion |
| `pw-c01`, `#13`, P1, `tests/orders.spec.ts:13` (3/3) | Possible label/contract conflict: this clean case instantiates and opens `OrdersPage`, then clicks the survey directly. Current #13 says to add missing POM methods for such interactions. Independent adjudication must resolve whether the rule or clean label needs revision in a successor; do not silently repair this frozen corpus |

The current #13 contract therefore deserves review before another measurement, but reducing its severity or scope simply to clear this observed case would be outcome-driven. The same applies to the Cypress security-control response: the existing debugger contract already requires a confirmed test defect before P0/P1/P2. Preserve that observed noncompliance and add an explicit unknown-axis/severity assertion in a future regression, not a retroactive successful score for these four calls.

#### Diet decision

Do not expand the skill or switch the product wholesale to catalog-only from this replay. Catalog-only uses about 48.4% fewer prompt bytes here, but both guided arms failed and this experiment does not measure scanner, fixing, browser verification or instruction-level effects. Keep the evaluated product bytes unchanged while resolving label/contract ambiguity. The next bounded simplification should test these candidates separately:

1. Keep one canonical counting and finding-verification contract in `references/semantic-review.md`, with concise routing from `SKILL.md`; those contracts are currently duplicated. Preserve parity and fallback behavior.
2. Move the rare in-scope RTL/Jest/Vitest repair block in `references/applying-fixes.md` behind an explicit conditional reference, rather than deleting required runner/setup details.
3. Treat the mandatory opening-token sweep as an unmeasured complexity candidate, not removable overhead. Move only deterministic families into the scanner with TP/FP fixtures, then ablate them against fresh cases; retain semantic families and the zero-P0 floor.

Presentation-safe wording: "On twenty public development cases with three repetitions, the catalog and full semantic prompts detected all 24 labeled defects by majority vote. The no-skill baseline detected 15. However, the full prompt produced four additional stable predictions, failed its quality gates, and did not outperform the catalog. This supports further investigation of structured guidance, not a claim that the complete skill is independently validated or generally superior."

Do not claim "180 independent cases," "all best practices covered," "lint replacement," "prompt-injection safe," "release validated," or that full guidance has proven incremental value. This replay included no lint-only arm, and the four security decisions are not a security success-rate estimate.

External artifact directory: `current-reviewer-three-arm-20260924.H3KUi4`. SHA-256 identities:

| Artifact | SHA-256 |
| --- | --- |
| `registration.json` | `a5238b092816bb81bdc7e32d78fe1629d68c430a56ac2cb76d2b2d5e7a591f0d` |
| `full.json` | `1a0dc17b53e0e23402acc6095705795332c07f4516af6ee162480a6231cbb7ab` |
| `catalog-only.json` | `28f2cba7ee4669e4176f751c170495d87135725016599befeb861de677eee293` |
| `no-skill.json` | `082785a2b61dfdaff9be8ba76a289377d76b28ea8f05b2447b075764d8b52e0b` |
| `comparison.json` | `095cd896931d9e79bda578c50efe86cee242f281128ea205ce922ceaa894128c` |

### Post-outcome contract revision and bounded diet (2026-09-24)

This is an explicitly post-outcome development change, not a preregistered improvement or a new accuracy result. #13 decision revision v2 requires source evidence of an established same-page interaction boundary: an equivalent method/locator, duplicated selector/workflow, or explicit project convention. Navigation-only POMs, nearby routes, imports and missing methods alone are insufficient. The maintenance rationale is duplicated ownership, not mandatory abstraction. This intentionally accepts the risk of missing a first raw action whose architectural ownership is not supplied; it reconciles #13 with #11 rather than prescribing single-use wrappers.

Mutable development eval 3 now targets the existing `#save-all` duplication, eval 44 becomes a navigation-only negative guard, and new evals 49–50 cover an established multi-step POM workflow and rendering-only versus exact-content Cypress promises. Frozen v5 case `pw-a04` has a #13 positive label (`V5-008`) supported by the former missing-method rule, not this revision. Leave that label and every historical report unchanged; the old corpus is not an acceptance test for the revised rule. A successor protocol/corpus must declare the new decision version and include fresh cases before measuring it. #15/#16 and the valid equivalent-method #13 examples are not weakened.

The structural diet keeps counting canonical in `semantic-review.md` and finding verification canonical in `SKILL.md`, with mandatory links replacing duplicate paragraphs. Keeping verification in the entrypoint preserves the host-routing/parity contract without another CI architecture change. The rare RTL/Jest/Vitest repair row and prerequisites move to `rtl-jest-dom-fixes.md`, read only before an in-scope RTL #4f fix; the exact row attribution and prerequisite checks remain mandatory. The mandatory opening-token sweep and all safety gates remain. Conditional loading does not imply a smaller all-references benchmark prompt, lower billed tokens, or improved accuracy.

Validation distinguishes static contracts and source review from model behavior. RED/GREEN contract checks and new TP/FP fixture metadata can establish consistency and guard deletion, not effectiveness. A fresh model comparison and real distinct-UID release integration remain separate next steps; neither is implied by this local edit.

A bounded native-agent forward check read the revised contracts and new source fixtures without `evals.json`, benchmark reports, or earlier verdicts. It returned #1 at the Cypress title declaration (line 7) and #13 at the first duplicated archive action (line 9), retained the negative guards, and avoided the competing #11 deletion. This is a two-fixture development check, not a blinded external effectiveness study. Retain its remaining noncompliance: the #1 fix offered title narrowing as an alternative despite the output contract requiring one evidence-backed fix without a weaker alternative. No model accuracy or complete instruction-compliance claim follows.

The entrypoint shrank from 16,043 to 15,613 UTF-8 bytes; `semantic-review.md` from 30,617 to 29,662. The fix reference shrank from 29,250 to 27,117 bytes, while the new conditional reference adds 2,965 bytes. This is chiefly conditional loading and deduplication, not a large package-size reduction. README translations retain English wording for the changed #13 cells until a translation-quality review; canonical-revision checks do not attest translation quality.

Local verification completed: the new ownership contract first failed against the previous instruction, then passed after the revision; reviewer doc contracts, seven assertion-contract tests, all 130 eval metadata entries, skill validation, review checks (16), and the explicit security gate (10) passed. The final full `ci-local.sh` run exited zero with zero P0 smell hits; its fixture scan retained twelve non-P0 heuristic/triage hits. Optional integration skips remain disclosed by that run, so this is not fresh browser execution, Linux compatibility, or release certification. The full transcript is retained outside the repository in `reviewer-diet-20260924.R5N1az/ci-local-final.log`; the earlier interrupted run is retained separately. No commit, push or installation was performed.

### Portability and overprescription follow-through (2026-09-24)

The user requested correction of environment-dependent paths and non-universal prescriptions, followed by a separate Fable review. This authorizes local product edits, regression verification and one tool-free Fable source review; it does not authorize publication, installation, external project mutation or a release-effectiveness claim.

The local changes resolve skill references from the actual loaded host path, preserve fixed executable trust boundaries, qualify platform support, replace actor-based disagreement authority with evidence reconciliation, preserve independently useful smoke/release suites, and remove count/percentage-based correctness and scope-expanding fix-budget interpretations. Generator changes reject unmatched registered mocks with an unconditional test failure, preserve approved request contracts when the app is defective, and allow repository-native isolated setup and sourced secondary outcomes. Existing historical benchmark labels and results remain unchanged. The prospective [reconciliation protocol](../../benchmarks/subagent-reconciliation-v1/README.md) is registered but unexecuted; retaining inline as the default is separate from claiming that it always wins a disagreement.

The product-path audit found no literal personal-account root in the shipped instruction/script surface. Conventional system paths remain because they enforce trusted executable selection, not because every macOS/Linux distribution is supported. NixOS or alternate-tool-only layouts are not newly supported. README translations use the exact English platform paragraph pending a translation-quality review. The Linux checker remains a committed-snapshot check, not a worktree container runner; its new default preflight refuses omitted dirty inputs, while an explicit revision intentionally checks that commit.

The Fable source snapshot contains all non-eval skill Markdown, named-agent Markdown, small shell launchers, README and the Linux-check entrypoint: 44 files, 567,883 prompt UTF-8 bytes. The requested model is `claude-fable-5`, with no tools, one call and a 1,200-second timeout. No earlier findings, intended answers or benchmark scores were supplied. Scanner/Python internals and tests are outside that review packet, so it is an overall instruction/entrypoint review rather than an exhaustive runtime security audit. Registration, exact source hashes, prompt and response are retained in the external `portable-policy-fable-20260924.lD2qeQ` directory. Its findings require local adjudication; neither the review nor static contract tests establish population effectiveness.

That call completed in 574,413 ms with twelve proposals and unchanged registered sources. Local adjudication confirmed instruction or presentation issues in all twelve, not twelve demonstrated runtime defects: convention handling, evidence-preserving assertion fixes, optional authorized PR research, direct-input excerpt provenance, conditional credential forwarding, F1/F7 probe scope, generator ordering and local POM style, scanner-description drift, the curated-versus-mechanical merge-count distinction, and one severity-range typo. Corrections preserve legitimate initial-empty tests and zero counts rather than adopting stronger assertions without requirements. The final corrected text has not been re-reviewed by Fable. Raw response SHA-256: `458044075c6521ce4ca688b6f3345981898c3ef86746f9b9df326ad3921ce20f`; per-finding decisions are retained in `adjudication.md` beside that response. Historical ledgers were not recounted or rewritten.

Verification: final targeted generator, debugger, reviewer-document, routing and Linux-snapshot contracts passed; eval metadata reached 141 valid cases, review checks passed 16/16 and security checks passed 10/10. The full CI invocation passed through the post-fix verifier but exited nonzero in parity because its Windows/WSL mutation still targeted the previous README sentence. After correcting that test input, the complete parity stage passed 52/52 with its source digest unchanged, and both remaining self-scans passed with zero P0 findings or candidates (the scripts scan retains twelve non-P0 heuristic/triage hits). The full entrypoint was not rerun from the beginning after this test-only correction; this is stage-wise verification, not a fresh uninterrupted full-CI pass. Logs are retained as `ci-local.log`, `parity-final.log`, `scan-skills-final.log` and `scan-scripts-final.log` in the same external directory. Optional AST integration and the pinned-Claude live-path round trip remained skipped; no fresh Linux container or generator browser run was performed. No commit, push or installation was performed.

### Earlier specificity work (historical scope)

| Work | Verified status | Evidence |
| --- | --- | --- |
| Align selection with actual implementation | Frozen v3 and the lazy collector differed; v4 records the changed selection instead of rewriting v3 | [v4 record](../../benchmarks/reviewer-specificity-v4/README.md) |
| Check collection feasibility | v4 blocked: scanner discovery cannot produce eight of 24 required principal patterns | [v4 blocking defect](../../benchmarks/reviewer-specificity-v4/README.md) |
| Separate clean sampling from lookalike discovery | Primary ordered clean cohort and secondary challenge cohort designed; release successor not frozen | [sampling decision](../../benchmarks/reviewer-specificity-v4/successor-sampling-decision.md) |
| Exercise the development pipeline | Codex transport, numbered citations, bounded intake, continuation and two-pass review implemented and tested | [development evidence](../../benchmarks/reviewer-specificity-v4/semantic-pilot-results.md) |
| Remove the path-name restriction | Opt-in intake accepts spec paths outside `e2e` while retaining dependency/import proof and fixed limits | [intake revision](../../benchmarks/reviewer-specificity-v4/successor-sampling-decision.md#path-independent-development-revision) |
| Audit same-model agreement | Batch four exposed unsupported unused-export and P0 inferences from an incomplete import slice | [source-scope audit](../../benchmarks/reviewer-specificity-v4/batch-four-scope-audit.md) |
| Test the scoped prompt correction | Four new calls on the same two cases removed #8/#11 proposals and retained #14/#20 families; this is a diagnostic, not held-out accuracy | [diagnostic outcome](../../benchmarks/reviewer-specificity-v4/batch-four-scope-audit.md#diagnostic-outcome) |

**Current result:** zero admitted release cases, zero development clean candidates in the ordered primary batches, no three-arm specificity evaluation. Original failed/incomplete artifacts and frozen protocols remain unchanged. Targeted AST/context tests and the full local CI mirror passed on 2026-09-22; optional checks requiring unavailable historical tools retain their disclosed skips. Broader historical benchmark results are tracked separately in [evidence status](../../benchmarks/STATUS.md).

## Earlier specificity execution sequence (2026-09-23 plan)

### Corrective delivery before further evaluation (2026-09-23)

Finish the existing product corrections before resuming the study: preserve assertion predicates and intended outcomes, distinguish queued Cypress query failures from immediate chainable assertions, and keep debugger causal conclusions evidence-bounded. These are behavior fixes, not new benchmark results.

Keep the local changes in three reviewable groups:

1. **Product corrections:** the four skill directories, assertion/browser probes, debugger/generator/scanner regressions, the current reviewer digest, changelog and matching contributor/README guidance.
2. **Evaluation infrastructure:** collector/runner/comparator changes, context and admission tools, their regression suites and CI registration. Synthetic collector tests bind current inputs only in temporary or in-memory fixtures; the production frozen-input checks and original v3/v4 protocol bytes remain intact. Passing these tests is not a replay of the historical experiment.
3. **Evidence and planning:** specificity development records, benchmark status and roadmap. Keep failed/incomplete results visible and separate from product validation.

Before installing the four skills, run the full local CI mirror and security gate. Verify the installed source bytes, not just the skill names or versions. Resume with the already acquired `small-001` source case and a fresh offline context diagnostic plus independent source review; do not expand the exhausted acquisition schedule or promote a source review to an admitted clean label. Treatment arms remain gated on a successor protocol and admitted corpus.

| Order | Work and implementation surface | Completion evidence |
| --- | --- | --- |
| 1 — next | Define bounded context coverage in [context expansion](../../scripts/evals/specificity-successor-rules.py) and [intake](../../scripts/evals/prepare-specificity-fresh-pilot.py): setup dependencies, reverse users and scenario caller/postconditions | TP/FP/unknown fixtures prove missing reverse-user coverage cannot establish #11, and an uncalled helper cannot establish scenario-level #8. Record unsupported config expressions and limit exhaustion explicitly. No target code execution. |
| 2 | Make unresolved coverage a machine-checked admission constraint in the [development runner](../../scripts/evals/run-specificity-primary-batch.py), not just a prompt warning | A model's `clean` label cannot create an admissible clean case when required evidence is unresolved; tests cover missing setup, unresolved imports, partial usage searches and complete controls. |
| 3 | Freeze a new bounded feasibility schedule before further collection | Registration fixes source order, exclusions, framework/repository caps, context/file/request limits, stopping policy and model call budget. Preserve findings and unknowns; no outcome-dependent replacement or budget expansion. |
| 4 | Run the feasibility schedule serially with Codex | Source hashes unchanged; every scheduled call has a terminal record; schema/citations validate; clean, finding, unknown and infrastructure failures have separate counts. If yield is insufficient, report incomplete rather than extending the same schedule. |
| 5 | Freeze a successor protocol only after feasibility and context gates pass | Define the primary cohort separately from pattern-lookalike challenges, independent adjudication requirements, quotas, thresholds and uncertainty calculations. The proposed 24-case minimum / 48-case target remain design inputs, not permission to bypass coverage. Do not amend frozen v3/v4. |
| 6 | Evaluate the admitted corpus with no-skill, catalog-only and full-skill arms | Identical cases and registered schedules across arms; provenance, blind adjudication, exclusions and comparator checks pass. Do not run below the new protocol's admission minimum. |
| 7 | Report the result and its limits | Publish only supported claims, with denominators, uncertainty, failure records and provenance. Run full `ci-local.sh` and the security gate before any authorized commit/PR. Release-grade claims additionally require the distinct [release protocol](../../benchmarks/reviewer-release-v1/README.md) prerequisites. |

### Execution update: context gate implemented, coverage still incomplete

Expanded acquisition subsequently retained [thirty source-file candidates from ten repositories](../../benchmarks/reviewer-specificity-v4/successor-sampling-decision.md#expanded-source-acquisition--2026-09-22), with 1,521 staged hashes verified. This removes the immediate one-case inventory bottleneck, not the admission prerequisites: first distinguish executable test imports from embedded fixture strings, then resolve each candidate's context and adjudicate the full catalog. No clean labels or treatment arms are implied by the acquisition count.

A subsequent [small-project acquisition](../../benchmarks/reviewer-specificity-v4/successor-sampling-decision.md#small-project-source-acquisition--2026-09-22) finished its fixed six-repository prefix and staged one new library integration-test case with twenty-five files, including all supported repository JS/TS source. Initial static triage is complete; full catalog review and independent context/admission adjudication are not. This improves source availability without changing the clean-admission gate, freezing a successor, or starting treatment arms.

Step 1 is partial: literal-only setup regex candidates and a bounded test-root source census are implemented, but neither proves the full caller graph or repository-wide usage. Step 2's safeguard is implemented and regression-tested: `require-proven` is the development runner's default, unresolved evidence blocks a clean candidate even after two clean votes, and historical `legacy` reproduction is explicit. The producer readiness fields are local provenance, not cryptographic or independent adjudication; no current collector emits a proven complete boundary.

A preregistered development feasibility probe (not the full step 3 successor schedule) visited the next inventory segment and exhausted sixty raw-source requests. It prepared one Mermaid case but covered only twenty of 88 test-root files; preflight returned `blocked-context` without credentials or model calls. See the [recorded outcome](../../benchmarks/reviewer-specificity-v4/successor-sampling-decision.md#observed-context-feasibility-result). Relevant five regression suites and review/security checks passed; full CI subsequently passed after the AST integration below.

The usage collector now also emits a deterministic, source-hashed lexical index: import target candidates (including ambiguous extension matches), staged reverse-import candidates, export and call locations, and setup configuration expressions. Every match is explicitly a candidate, not symbol resolution or execution evidence. Unstaged targets remain visible; strings, aliases, re-exports, dynamic code and project ownership still require semantic analysis. The index never changes admission readiness.

An offline replay on the previously staged Mermaid case verified all 21 source hashes and produced 59 import candidates, 37 export candidates, 1,259 call candidates, five reverse-import target entries and two setup-expression candidates. These counts describe lexical matches, not proven calls or defects. The replay used only staged bytes, made no network/model calls and left the original context report unchanged (`bd11ad6b0b24af5e51e1ea89bcbcf5b88972e0b418fb02954f0c50c8fabb3325`). Tests cover stable ordering, changed-source hashes, ambiguous and unstaged targets, path escape rejection, aliases and string-shaped false-positive candidates.

### Parser-backed diagnostic implementation

[The AST analyzer](../../scripts/evals/specificity-context-ast.cjs) now uses an explicitly selected TypeScript 6.0.3 installation and a memory-only compiler host. It binds imported aliases and re-exports to staged declarations, distinguishes shadowed bindings, omits string-shaped fake calls, and records staged reverse imports/call bindings. Explicit type-only imports are not reverse-user evidence; even other source imports do not prove runtime use. The config reader extracts literal project names, dependency and teardown edges, test selectors and global setup targets without executing configuration. Missing/ambiguous targets, cycles, spreads and dynamic expressions stay unresolved. A resolved declaration is not proof of a call's execution or independent test postconditions.

[The offline replay](../../scripts/evals/replay-specificity-context-ast.py) verifies original source hashes before and after analysis and writes only a fresh external diagnostic directory. It records parser, Node, analyzer and wrapper provenance, rejects empty/duplicate case IDs, and bounds source size, file count, AST nodes, calls, output and subprocess time. The sanitized process environment and no-network implementation are not an OS sandbox attestation. Intake can opt in with paired `--typescript` and `--node` arguments; parser identity is registered before collection and cannot change during continuation. Neither path changes the admission gate.

The final local implementation was replayed on the existing fourth and fifth batches (post-outcome development diagnostics, not a new held-out sample):

| Source case | Staged files | AST calls | Calls with staged declaration bindings | Unresolved records |
| --- | ---: | ---: | ---: | ---: |
| Batch four: Playwright API example | 2 | 38 | 0 | 40 |
| Batch four: Uptime Kuma | 3 | 56 | 1 | 61 |
| Batch five: Mermaid | 21 | 943 | 121 | 869 |

The Uptime Kuma config's `specs -> run-once setup` dependency and literal setup selector were extracted. The setup file itself is absent from that original three-file boundary, so execution remains unproven. Mermaid retains a conditional global teardown and a partial source boundary. Unresolved counts include external library calls and are neither defect counts nor independent missing files. No new network/model calls, clean admissions, successor freeze or three-arm measurement resulted.

Local final replay reports: `specificity-ast-replay-b4-r2-20260922/ast-context-report.json` SHA-256 `6b56c7a37d5aface258f2d9f6ecb2fe7652e0cfb38f5aeb6a962a74ac1662d4a`; `specificity-ast-replay-b5-r2-20260922/ast-context-report.json` SHA-256 `e15b12d0a27314a648b5ae8e4e19827616f648c1aed854b60b536e5a10dff185`. Earlier diagnostics and frozen v3/v4 remain unchanged.

The dependency-free wrapper contract tests run in ordinary CI. Parser integration is explicit: set `E2E_SPECIFICITY_TYPESCRIPT` to the trusted `lib/typescript.js` and optionally `E2E_SPECIFICITY_NODE` to the trusted Node executable when running `scripts/ci/test-specificity-context-ast.py` or `ci-local.sh`. Without that parser, integration reports `SKIP`, not a tested parser result. The explicit local integration and targeted intake/context suites passed. The full `/bin/bash -p scripts/ci/ci-local.sh` run, with those parser/Node variables supplied, exited zero on 2026-09-22; the final smell scan found zero P0 hits. Existing optional checks, including the historical pinned-Claude live-path round trip, retained their disclosed skips. This is code/infrastructure validation, not a live model evaluation or release pass.

**Remaining gate:** the available cases still lack complete usage boundaries, setup/runtime evidence and independently adjudicated clean labels. Static binding cannot supply those facts. Step 3's counted feasibility schedule and steps 4–7 remain unrun; the next study needs a complete, auditable boundary and adjudication contract before any paid/model evaluation. Repeatedly sampling repositories or increasing the exhausted experiment's budget is not a substitute.

## Optional Jev shadow experiment

**Status: planned, not installed or called.** Keep this off the primary path until source-context gates work.

- **Role:** classify one evidence-backed candidate at a time using fixed choices such as supported finding, refuted candidate and insufficient evidence. Code owns paths, line numbers, counts and coverage; Codex or static tooling prepares the evidence. Jev must not invent missing callers or certify a whole repository from a slice.
- **Access and cost gate:** TypeSafe documents its own API key and usage pricing. Verify account access, current pricing/free credits, data handling and an explicit spending cap before any live call. Do not assume an existing coding-agent subscription covers it, and do not record a free-tier promise without confirmation. Locate credentials through the approved credential catalog; never paste or search secret values.
- **Protocol:** pin the resolved model version, question schema, source hashes, fixed question/call budget and failure policy before execution. Reconfirm the documented `jev-1.13.0` version when starting; do not use a moving alias for a counted comparison. Keep Jev outputs hidden from the baseline reviewer and never let shadow results alter admission or frozen results.
- **Evidence:** use a separately labeled development set with true positives, false-positive guards, missing-context cases and prompt-injection controls. Keep threshold tuning cases separate from measurement cases. Record false-positive rate, missed findings, abstention/coverage, calibration, schema failures, latency and measured usage/cost. Do not compare only the two cases used to design this change.
- **Decision:** preregister acceptable error, abstention, latency and cost thresholds before measured calls. Promote only if those gates pass; otherwise retain the existing path and archive the negative result. Valid typed output and high confidence are not correctness or independent ground truth.

Official references checked on 2026-09-22: [model IDs, limits and pricing](https://docs.typesafe.ai/models), [API access](https://docs.typesafe.ai/introduction/quickstart), [documented failure modes](https://docs.typesafe.ai/model-jaggedness/jev-1.13). Jev explicitly has limitations on indirection, counting and adversarial content; compact inputs help only when necessary evidence is retained.

## Risks and verification

- **Selection bias:** separate development diagnostics, primary sampling and challenge cases; never pool them into a release estimate.
- **Shared model errors:** agreement is not truth; require external evidence and the successor's independent adjudication gate.
- **Context growth:** cap extraction in advance; return unresolved rather than silently trimming evidence or executing configuration.
- **Runtime/provider limits:** preserve failed attempts and consumed budgets; use only disclosed continuation rules, with no account rotation or hidden retries.
- **Scope drift:** preserve the upstream contribution ledger; this plan does not authorize posting, paid services or a product-skill change.

For implementation, start with the corresponding `test-specificity-successor-rules.py`, `test-specificity-fresh-pilot.py` and `test-specificity-primary-batch.py` regression suites, then citation/context-followup checks, `scripts/ci/review.sh` and `git diff --check`. A green local test is infrastructure evidence, not a benchmark outcome. Plans and evidence updates must keep links valid and public prose in English.
