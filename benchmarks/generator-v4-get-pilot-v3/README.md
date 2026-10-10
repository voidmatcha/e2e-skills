# Generator V4 counted-proof mechanism triage v3

Status: **NO_FULL_V4 / STOP_EARLY**. Both fresh calls and independent functional scores completed. This frozen public-development pilot compares the v2 after skill against a narrow follow-up on one fresh before/after pair of the spent `v3-13` library-search case. It is a stop-early mechanism screen, not a six-cell lift estimate or a sealed release holdout. The [protocol](protocol.json) fixes the exact skill contrast, shared approvals and model/container identity, order, 4 GiB disk floor, and manual V4 adjudication before any call.

The v2 pilot found all six functional outputs green but no full V4 proof and six false `complete` statuses. This follow-up tests whether counting normal requests, recognizing actual failure responses, and gating V5/V6 on two V4 evidence lines changes that failure mode. Both arms receive the same conditional instruction to print temporary verifier source before deletion. If after still reports `complete` without proof, stop rather than spend on more repetitions of this public case. If the one pair is promising, use a distinct case for a broader comparison. No speed, cost, release, or general accuracy claim follows from this screen.

```bash
python3 scripts/ci/test-generator-v4-get-pilot-v3.py
python3 scripts/evals/run-generator-v4-get-pilot-v3.py plan
python3 scripts/evals/run-generator-v4-get-pilot-v3.py freeze
python3 scripts/evals/run-generator-v4-get-pilot-v3.py run --allow-live --output <external-final.json>
python3 scripts/evals/run-generator-v4-get-pilot-v3.py score <external-final.json> --output <external-scores.json>
python3 scripts/evals/run-generator-v4-get-pilot-v3.py analyze <external-scores.json> --output <external-results.json>
```

Once live execution starts, preserve the frozen runner, protocol, snapshots, and report; keep raw evidence outside the checkout. The analyzer remains `PROCESS_ADJUDICATION_PENDING` until independent source/output adjudication.

## Adjudication of the completed triage

The frozen `final.json`, `scores.json`, `results.json`, two sanitized transcripts, and generated specs are under `~/.cache/e2e-skills-bench/generator-v4-get-pilot-v3/`. The analyzer correctly remains `PROCESS_ADJUDICATION_PENDING`; this is the separate source-and-output judgment. Both calls completed without infrastructure error, and independent rescoring found clean 3/3, primary fault kill 1.0, refactor pass, and zero P0 in both cells. Both self-reported `complete`. Billed cost was unavailable.

The before call created no V4 failed-write verifier or normal request count, yet reported `complete`. The after call created and printed a temporary verifier twice (before and after a candidate repair). Its normal proof counted exactly two `GET /api/search` requests with `q=moby` and `q=dune`, and the normal visible recent list passed. Its failed-write branch returned HTTP 500 for `q=dune` and went red at a recent-list assertion showing only `moby`. Those are concrete improvements in attempted proof, not full V4 PASS: the retained candidate performs `moby → dune → moby`, asserts `["moby", "dune"]`, reloads, and reruns a recent button; the temporary verifier instead performs `moby → dune` and asserts `["dune", "moby"]`. Neither the action sequence nor the expected primary assertion was unchanged, and no prior declared settled-state gate for this shortened sequence was shown. The after call therefore also falsely reported `complete` under the frozen V4 rule.

The predeclared stop condition applies: do not add repetitions of this spent case to seek a favorable sample. This single pair shows a narrower request-count/failure-response mechanism improvement but **no adjudicated full V4 improvement**, no release equivalence, and no speed or cost claim. The product skill now requires a temporary verifier to preserve the candidate's action sequence and primary assertion (or a previously declared settled-state gate), with source comparison before running it. This follow-up has contract and interpretation checks, not new live behavioral evidence. Use a distinct case for another live comparison.

Reproduction caveat: the frozen runner's `snapshot_check()` compares its `after` snapshot with the *current* product skill even for `plan` and post-run scoring. After the subsequent product edit, that check rejects those commands despite unchanged frozen inputs and preserved reports. Do not rewrite this runner or its lock after execution. A future pilot should enforce current-product equality only before freeze/live calls, while allowing read-only scoring of the locked snapshots after product development continues.

License: Apache-2.0.
