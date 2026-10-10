# Generator V4 failed-response ordering transfer screen

Status: **NO_FULL_V4 / PARTIAL_TRANSFER**. This public-development one-pair comparison tests whether the response-before-persistent-re-read rule changes V4 behavior on a distinct state-changing GET inventory case. It is not a sealed holdout or release-acceptance run. The before skill is the frozen transfer-v2 after arm; the after skill is the product as snapshotted immediately after the response-order rule edit, not later mutable product bytes. The snapshots differ only in `SKILL.md` and `verification-rules.md`; evals are excluded. Both arms use the same [stock-claim fixture](cases/stock-claim/README.md), approvals, model, pinned container, reviewer, and scorer.

Model-free validation passed before freeze: strong test clean, five of five fault kills, markup-refactor survival, naive test zero kills and refactor failure, and equal ARIA snapshots. The normal task is Lamp → Desk → reload → Lamp, with exactly one state-changing `GET /api/claim?sku=...` per click and final Lamp 1, Desk 2, Claimed 3. V4 adjudication requires a product-recognized failed GET at the retained candidate's final click, the unchanged primary or declared gate, and an explicitly awaited failure response **before** a persistent-state reload or app re-fetch. Printing the complete temporary verifier source is a shared approval for both arms. A self-reported `complete`, red assertion alone, or functional kills are not full V4 proof.

```bash
python3 scripts/ci/test-generator-v4-get-transfer-v3.py
python3 scripts/evals/run-generator-v4-get-transfer-v3.py plan
python3 scripts/evals/run-generator-v4-get-transfer-v3.py freeze
python3 scripts/evals/run-generator-v4-get-transfer-v3.py run --allow-live --output <external-final.json>
python3 scripts/evals/run-generator-v4-get-transfer-v3.py score <external-final.json> --output <external-scores.json>
python3 scripts/evals/run-generator-v4-get-transfer-v3.py analyze <external-scores.json> --output <external-results.json>
```

The runner binds the validated fixture, oracle, protocol, snapshots, container, and scorer in `freeze.json`. It checks the 4 GiB disk floor before model work and stores generated artifacts outside the checkout. It intentionally leaves V4 `UNADJUDICATED` until a separate source/output audit. Do not repeat this spent case merely for a favorable result. A positive one-pair result would be a mechanism signal, not a generalized lift, speed, cost, or release claim.

## Completed comparison and V4 adjudication

The complete `final.json`, `scores.json`, `results.json`, candidate specs, and sanitized transcripts are under `~/.cache/e2e-skills-bench/generator-v4-get-transfer-v3/`. Both model calls and independent scores completed without infrastructure errors or out-of-scope writes. Both candidates passed clean 3/3, killed all five seeded faults, survived the markup refactor, and scanned at P0 0. A separate read-only V6 reviewer returned `PASS P0=0 P1=0 P2=0` for the after candidate. Both parent calls self-reported `complete`. Single-call elapsed times were 220.1 seconds before and 274.5 seconds after; billed cost is unavailable, and no speed or cost claim follows.

The before temporary verifier printed its source and injected HTTP 500 for **every** Lamp claim, including the first. It failed at the early expected `Lamp: 2 left` checkpoint, never reaching the final primary assertion. V4 is `CANNOT_VERIFY`; an early red does not prove the intended final write contract.

The after temporary verifier printed its source, scoped the HTTP 500 to the second Lamp claim, and awaited the matching response before the unchanged `Claimed: 3` primary. It went red with actual `Claimed: 2`. This corrects the before arm's wrong write target and the prior poll-tally arm's response-order gap. However, it never reloaded or awaited an app re-fetch **after** the failed final response and before that red primary. Its prior reload happened before the final claim. The red DOM can therefore be stale rather than proof that persistent state stayed unchanged. After V4 is also `CANNOT_VERIFY`, so its `complete` report is unsupported. The machine analyzer intentionally reports `PROCESS_ADJUDICATION_PENDING`; this manual adjudication is separate.

The next narrow product edit should make the failed-write procedure an explicit ordered sequence: target the intended write, await its recognized failure, re-read persisted state, then run the unchanged primary. Validate any edit before another independently validated state-changing GET comparison. Do not rerun this spent inventory pair to chase a favorable result. No generalized lift, release equivalence, cost saving, or speed gain is established.

License: Apache-2.0.
