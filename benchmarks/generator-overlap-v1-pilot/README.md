# Generator overlap v1 pilot

Status: **PILOT_NOT_PROMISING**. Six fresh Codex generations and all six independent scoring cells completed. This public-development, one-factor pilot compares the prior generator snapshot with the current skill's narrow overlapping-response verification guidance on the spent v3-13 search-race fixture. The frozen protocol, arm snapshots, schedule, and input digests are in this directory. The raw report, scores, decision, generated specs, and transcripts remain in the operator's external `e2e-skills-bench/generator-overlap-v1-pilot/` cache; they are not committed benchmark artifacts.

Both arms detected `f2-stale-response-wins` in **3/3** generations. Both also recorded raw kills of the other four seeded faults in 3/3. The prior arm's third spec failed on the correct app in all three clean reruns, so its raw fault kills do not count as effective coverage for that cell; the current arm passed clean 3/3, refactor, and P0=0 in all three cells. The prior arm's third call also self-reported `partial_or_blocked`. These observations do not establish an incremental target-fault gain from the new wording: the required strict improvement over the prior arm was absent, and the frozen decision returned `PILOT_NOT_PROMISING`.

The current arm took longer in each of the three paired generations (380 vs 254 seconds, 423 vs 416 seconds, and 479 vs 262 seconds; rounded). The paired median elapsed-time reduction was **-49.86%**, descriptive only. Parent-recorded input-token totals were higher for the current arm, but child usage is incomplete and billed cost is unknown. Do not claim speed or cost savings. The spent public fixture and three pairs cannot establish causality, release equivalence, or general behavior. V4 execution and V6 reviewer correctness still require separate transcript adjudication.

The scoring process paused automatically when host load exceeded its frozen threshold, without changing the protocol. The 4 GiB disk floor was maintained; about 8.0 GiB was available at closeout. The pilot does not justify expanding the overlap wording. It also does not, by itself, prove that the current wording should be removed: the prior arm's clean failure and current arm's clean pass are output observations on this small fixture, not an isolated causal attribution.

## Post-hoc process audit

The six preserved parent JSONL transcripts each show a separate V6 reviewer invocation and an eventual `V6 VERDICT: PASS P0=0 P1=0 P2=0` after any reviewer-requested repair. Each outgoing reviewer packet contains the `## V1 — Primary Outcome` heading and scenario `V1 completion` fields; the three after-arm packets also contain the overlapping-actions subsection. This presence check does not adjudicate every field against the approved plan or establish that the reviewer was semantically correct.

None of the six parent transcripts records a V4 failed-write injection run. The fixture's `GET /api/search` mutates recent-search state, which the generated scenarios exercise across reloads; this is a write-producing outcome despite the endpoint's GET method. A normal test run or the independent V6 verdict cannot substitute for V4's failed-write proof. Therefore the recorded `complete` self-reports are **not** independently validated as full generator-contract completion. The frozen fault-kill and clean/refactor scores remain output measurements, but no arm gets V4 process credit from this pilot. The audit is post-hoc and does not revise the frozen decision or scores.

The product skill now makes this method-versus-effect distinction explicit at Step 7, with eval 53 covering a side-effectful GET, a read-only GET, and an unapproved probe. A fresh read-only Codex check of the updated source answered the side-effectful case `V4 CANNOT_VERIFY` and `PARTIAL/BLOCKED`, while treating the read-only GET as V4 `N/A`. This is one interpretation check, not a generated-spec or failed-write execution result, and the new wording was not in either frozen arm.

## Follow-up direction

A post-hoc audit of the six preserved parent transcripts found failed reads of generator Markdown under a nonexistent `references/` subdirectory in three calls (one prior, two current). All six had the expected initially refused preflight probe; neither arm had a missing-default-Chrome event. Two calls had a port-in-use event, one in each arm. These are observed events, not time attribution or a measure of billed cost. The product skill now states the direct-sibling reference location, and eval 52 covers that routing decision; this edit was **not** in either frozen arm and has no measured behavioral effect yet. The frozen runner intentionally refuses current-product drift; its offline contract test checks the archived snapshots separately.

A bounded fresh read-only Codex routing check read the updated source `SKILL.md`, then opened all three requested references from the installed skill's direct-sibling paths, without a guessed `references/` read. This is one successful path-selection check, not a repeatable behavioral or performance measurement. The installed global copy is older than the source and was not updated in this check; do not treat this result as validation of a refreshed runtime install. For a performance or quality claim, freeze a separate paired multi-case protocol before generation: use tasks where the baseline does not already saturate the target metric, score only fault kills from clean-passing specs as effective, retain clean 3/3, refactor, P0, write-scope and complete-attempt guards, and adjudicate V4/V6 from transcripts. Keep elapsed time descriptive until the paired comparison and full usage accounting support a cost claim. Do not reuse this spent search-race pilot as a positive holdout or silently alter its frozen inputs.

The next validation has two separate lanes, with no shared positive claim. First, test the one-line reference-path change against a snapshot differing only by that line in fresh contexts and record actual file-read commands: wrong `references/` reads, successful direct-sibling opens, retries, and write scope. A routing-only result cannot establish generated-test quality or elapsed-time savings. Second, develop distinct asynchronous-overlap fixtures and validate their fault operators without model calls. Screen baseline behavior on development fixtures, then freeze a disjoint, non-ceiling multi-case comparison with identical runner, approvals, model, and scorer across arms. Its primary metric is paired **effective** target-fault kill (only a clean 3/3 spec can kill a fault); `complete` additionally requires reviewed V4 evidence for write-producing scenarios and an outgoing V6 packet plus independent verdict. Test the V4 clarification as its own one-factor intervention, not bundled with overlap or path routing. Any missing V4/V6 evidence is an incomplete cell, not a successful generation. Keep a 4 GiB free-space floor before each artifact-heavy call. No current fixture or result has yet passed these prerequisites for a new quality or cost claim.

Run sequence, with outputs outside the checkout:

```bash
python3 scripts/ci/test-generator-overlap-v1-pilot.py
python3 scripts/evals/run-generator-overlap-v1-pilot.py plan
python3 scripts/evals/run-generator-overlap-v1-pilot.py freeze
python3 scripts/evals/run-generator-overlap-v1-pilot.py run --allow-live --output <external-final.json>
python3 scripts/evals/run-generator-overlap-v1-pilot.py score <external-final.json> --output <external-scores.json>
python3 scripts/evals/run-generator-overlap-v1-pilot.py analyze <external-scores.json> --output <external-results.json>
```

Do not overwrite the frozen inputs or existing outputs. A future sealed or release claim needs a separate corpus and execution boundary.

License: Apache-2.0.
