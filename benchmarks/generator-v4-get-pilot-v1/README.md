# Generator V4 side-effectful GET pilot

Status: **INCOMPLETE_V4_PROOF**. All six fresh calls and six independent functional scores completed. The after arm attempted a failed-write probe in two of three calls versus zero of three before calls, but the third after call still reported `complete` without a V4 probe. The temporary probe source was removed during the calls and not retained by the frozen runner, so the two red probe outputs do not establish the complete V4 request/injection contract. This public-development process pilot compares the current generator skill with an otherwise byte-identical snapshot lacking only the Step 7 side-effectful-GET V4 clarification. The spent `v3-13` library-search fixture is suitable for a bounded mechanism check because `GET /api/search` changes server-side recent-search history, which the generated scenario checks across reload. It is not an independent quality holdout.

The frozen plan is three fresh paired Codex generations, alternating arm order, one worker, using the same pinned image, fixture, prompt, approvals, and scorer. The primary observation is whether each generated candidate actually proves V4: normal request method/endpoint/query/cardinality and user-visible outcome, plus a temporary-copy failed-write run that turns red at the unchanged primary assertion or declared settled-state gate for the intended reason. `Complete` without that proof is a false completion. Read the parent transcripts and failed-write output to adjudicate this; neither a V4 mention nor the model's status suffices. A separate V6 reviewer packet and final verdict, clean 3/3, refactor, zero P0, scope, and infrastructure attempts are guards. The runner's analyzer intentionally returns `PROCESS_ADJUDICATION_PENDING` rather than awarding a positive process verdict automatically.

The one-factor snapshot, protocol, and schedule are checked before any call. Outputs and raw transcripts go outside the checkout. Stop before a call if free disk is under 4 GiB; preserve partial results rather than deleting evidence. Even a complete three-pair result would be a small development signal only, not general quality, speed, cost, or release evidence.

```bash
python3 scripts/ci/test-generator-v4-get-pilot-v1.py
python3 scripts/evals/run-generator-v4-get-pilot-v1.py plan
python3 scripts/evals/run-generator-v4-get-pilot-v1.py freeze
python3 scripts/evals/run-generator-v4-get-pilot-v1.py run --allow-live --output <external-final.json>
python3 scripts/evals/run-generator-v4-get-pilot-v1.py score <external-final.json> --output <external-scores.json>
python3 scripts/evals/run-generator-v4-get-pilot-v1.py analyze <external-scores.json> --output <external-results.json>
```

Do not modify the frozen snapshots, protocol, runner, or existing report after the live run starts. A missing cell, infrastructure attempt, or absent transcript makes the comparison incomplete; the final V4/V6 judgment remains a separate evidence-backed adjudication.

## Adjudication of the completed pilot

The frozen report, scores, result, and six sanitized transcripts are under `~/.cache/e2e-skills-bench/generator-v4-get-pilot-v1/` as `final.json`, `scores.json`, `results.json`, and `final-transcripts/`. The analyzer correctly remains `PROCESS_ADJUDICATION_PENDING`; the following is the separate source-and-transcript judgment, not a rewrite of that result. All six calls returned `complete` without timeout or infrastructure error. Independent rescoring found clean 3/3, primary fault kill 1.0, refactor pass, and zero P0 for all six generated specs. Each final independent V6 review was PASS with zero P0/P1/P2.

| Pair | Before V4 failed-write run | After V4 failed-write run | After elapsed versus before |
| --- | --- | --- | --- |
| 1 | Not observed | Temporary probe red at recent-search assertion | +46% |
| 2 | Not observed | Temporary probe red at recent-search assertion | +27% |
| 3 | Not observed | Not observed; still `complete` | +94% |

The app's `GET /api/search?q=...` updates its in-memory `recent` history for queries of at least three characters, so this is a V4 write despite the method. In after calls 1 and 2, the parent transcript shows a temporary verifier spec run with exit 1 and a `toHaveText` mismatch on the recent-search list. The runner did not preserve the deleted verifier source or a complete normal-request method/endpoint/query/cardinality evidence line. Consequently those cells show **probe attempts with a relevant red assertion**, not proven V4 PASS. After call 3 is a confirmed V4 omission and false `complete` under the product contract; all three before calls also omitted the probe. The six functional scores therefore do not imply completion-contract compliance. This spent single-fixture sample supports a narrow attempt-frequency signal, not reliable V4 adherence, speed/cost improvement, or release equivalence. Billed cost was unavailable; after was slower in all three pairs.

Next narrow iteration: bring side-effect classification into the scenario verification plan and require an explicit V4 two-line evidence check before `Complete`; make a successor runner retain temporary probe evidence before testing this change live. Do not retroactively credit the two red probes or modify this frozen protocol and output.

License: Apache-2.0.
