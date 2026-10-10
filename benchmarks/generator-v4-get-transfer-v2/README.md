# Generator V4 post-failure re-read transfer screen

Status: **NO_FULL_V4 / PARTIAL_TRANSFER**. This public-development one-pair comparison tests whether the point-of-use post-failure persistent-state re-read rule changes V4 behavior on a different side-effectful GET case. It is not a sealed holdout or release-acceptance run. The before skill is the frozen transfer-v1 after arm; the after skill is the product as snapshotted immediately after the re-read rule edit, not later mutable product bytes. The snapshots differ only in `SKILL.md` and `verification-rules.md`; evals are excluded. Both arms use identical [poll-tally fixture](cases/poll-tally/README.md), approvals, model, pinned container, reviewer, and scorer.

Model-free validation passed before freeze: strong test clean, five of five fault kills, markup-refactor survival, naive test zero kills and refactor failure, and equal ARIA snapshots. The normal task is Ruby → Blue → reload → Ruby, with exactly one state-changing `GET /api/vote?choice=...` per click and final Ruby 2, Blue 1, total 3. V4 adjudication requires a product-recognized failed GET at the retained candidate's final click, unchanged primary or declared gate, and a post-failure reload or app re-fetch before claiming persistent state remained unchanged. Printing the complete temporary verifier source is a shared approval for both arms. A model's `complete` report, red assertion alone, or functional kills are not full V4 proof.

```bash
python3 scripts/ci/test-generator-v4-get-transfer-v2.py
python3 scripts/evals/run-generator-v4-get-transfer-v2.py plan
python3 scripts/evals/run-generator-v4-get-transfer-v2.py freeze
python3 scripts/evals/run-generator-v4-get-transfer-v2.py run --allow-live --output <external-final.json>
python3 scripts/evals/run-generator-v4-get-transfer-v2.py score <external-final.json> --output <external-scores.json>
python3 scripts/evals/run-generator-v4-get-transfer-v2.py analyze <external-scores.json> --output <external-results.json>
```

The runner binds the validated fixture, oracle, protocol, snapshots, container, and scorer in `freeze.json`. It checks the 4 GiB disk floor before model work and stores generated artifacts outside the checkout. It intentionally leaves V4 `UNADJUDICATED` until a separate source/output audit. Do not repeat this spent case merely to chase a favorable result. A positive one-pair result would be a mechanism signal, not a generalized lift, speed, cost, or release claim.

License: Apache-2.0.

## Completed comparison and independent V4 adjudication

The complete `final.json`, `scores.json`, `results.json`, candidate specs, and sanitized transcripts are under `~/.cache/e2e-skills-bench/generator-v4-get-transfer-v2/`. Both model calls and independent scores completed without infrastructure errors or out-of-scope writes. Each candidate passed clean 3/3, killed all five faults, survived the markup refactor, and scanned at P0 0. A separate read-only V6 reviewer returned `PASS P0=0 P1=0 P2=0` for the after candidate. Both parent calls self-reported `complete`. The single-call elapsed times were 212.1 seconds before and 391.7 seconds after; billed cost is unavailable, and no speed or cost claim follows.

The before verifier printed its temporary source, intercepted the final Ruby vote with HTTP 500, preserved the Ruby → Blue → reload → Ruby action sequence and primary total-3 assertion, and went red at total 2. It did not re-read stored state after the failed response, so its red DOM may be stale. V4 is `CANNOT_VERIFY`.

The after candidate counted the exact browser-originated `ruby, blue, ruby` vote request sequence. Browser exploration separately showed three GET requests to `/api/vote?choice=...`. The after temporary verifier initially went red at total 2 without re-reading; the model then revised it to reload before the unchanged primary, and it again went red at total 2. This fixes the prior missing-reload behavior, but the final source still calls `await click(); await page.reload();` without awaiting the intercepted HTTP 500 response or another product-recognized failure signal before reload. A reload racing or aborting that request could produce the same red result. The transcript does not establish that the re-read occurred **after** the injected failure response. After V4 remains `CANNOT_VERIFY`, and the `complete` report is not supported by the skill's completion matrix. The machine analyzer intentionally reports `PROCESS_ADJUDICATION_PENDING`; this manual adjudication is separate.

The next narrow product edit clarified response-before-re-read ordering in the V4 failed-write procedure and Step 7, and added a positive/false-positive eval. Its targeted contracts, eval validation, and skill validation passed; this later edit has not yet had a live behavioral remeasurement. A new independently validated case is needed for that comparison. Do not rerun the spent poll-tally pair for a favorable sample or infer generalized lift, release equivalence, speed gain, or cost saving from it.
