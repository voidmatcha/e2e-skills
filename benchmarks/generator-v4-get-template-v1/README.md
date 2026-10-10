# Generator V4 executable-template transfer screen

Status: **COMPLETE / NO_V4_GAIN / TEMPLATE_NOT_RETAINED**. This public-development one-pair comparison tested whether a copyable response-before-read V4 code shape changed actual proof behavior on a distinct state-changing GET queue-promotion case. It is not a sealed holdout or release-acceptance run. The before snapshot is the product after its independent V4 raw-evidence audit; the after snapshot adds only the executable V4 template in `verification-rules.md`. Evals are excluded. Both arms share the same fixture, approvals, model, container, and scorer. The frozen snapshots and raw reports remain intact although the tested template was removed from the live product after the negative screen.

The normal approved task is Finch → reload → Raven → Finch, with exactly one state-changing `GET /api/promote?item=...` per click and final order Finch, Raven. A V4 proof must inject a recognized failed GET on the **final** Finch promotion, wait for that response, then read persisted order before the unchanged Finch-first primary turns red. A click, route `fulfill`, red DOM assertion, or self-reported `complete` alone is not proof. Preserve the full temporary verifier source and diff, normal request observation, targeted command, and failed-run output.

```bash
python3 scripts/evals/run-generator-v4-get-template-v1.py validate --output benchmarks/generator-v4-get-template-v1/validation.json
python3 scripts/evals/run-generator-v4-get-template-v1.py plan
python3 scripts/evals/run-generator-v4-get-template-v1.py freeze
python3 scripts/evals/run-generator-v4-get-template-v1.py run --allow-live --output <external-final.json>
python3 scripts/evals/run-generator-v4-get-template-v1.py score <external-final.json> --output <external-scores.json>
python3 scripts/evals/run-generator-v4-get-template-v1.py analyze <external-scores.json> --output <external-results.json>
```

The runner refuses model work below the 4 GiB disk floor and binds fixture, oracle, protocol, snapshots, container, and scorer at freeze. Frozen scoring measures functional behavior; V4/V6 remains separately adjudicated from raw source and output. A positive pair is only a mechanism signal, not generalized lift, speed, cost, or release equivalence. If the template is ignored or incomplete, do not extend this instruction-edit series with another checklist or reuse the spent case for a favorable result.

The first model-free fixture validation found that the strong reference test missed a persistence fault; its failed `validation-first.json` is retained. The reference test was corrected before freeze, and `validation.json` then showed clean pass, five of five fault kills, and refactor survival while the naive test killed zero of five. The frozen live run completed both calls without infrastructure error, artifact drift, or out-of-scope writes. The unmodified scorer found clean 3/3, refactor pass, and P0 zero in both arms. Before killed five of five seeded faults; after killed four of five, missing `f3-status-stale` because its candidate checked priority order but not the first-item status. This observed one-pair functional difference does not prove the template caused the omission.

Independent raw-source/output audit found **V4 PASS in both arms**: each counted the state-changing GET per click, intercepted only the final Finch promotion, awaited the injected HTTP 500 before reload, and failed at the unchanged Finch-first primary after the persistent re-read. The before transcript preserves this in items 72–75; the after transcript preserves it in items 56–58. Both model calls self-reported `complete`, but that status is not the audit. The frozen analyzer deliberately remains `PROCESS_ADJUDICATION_PENDING` with V4/V6 `UNADJUDICATED`; the separate manual audit is not written back into the frozen score. With no V4 gain and a narrower functional result in the after candidate, the copyable template and its proposed eval were removed from the live skill. No further instruction-only V4 checklist edit is supported by this screen.

Local raw evidence is under `<local-cache>/e2e-skills-bench/generator-v4-get-template-v1/`: `final.json`, `final-transcripts/`, `final-artifacts/`, `scores-frozen.json`, and `results-frozen.json`. The cache path is local provenance, not a public sealed corpus or an installation requirement. Billed cost is unavailable; elapsed call time is descriptive only (before 294.939 s, after 259.700 s).

License: Apache-2.0.
