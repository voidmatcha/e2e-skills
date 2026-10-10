# Generator V4 ordered failed-write transfer screen

Status: **NO_FULL_V4 / PARTIAL_TRANSFER**. This public-development one-pair comparison tests whether the ordered failed-write checklist changes V4 behavior on a distinct state-changing GET toggle case. It is not a sealed holdout or release-acceptance run. The before skill is the frozen transfer-v3 after arm; the after skill is the product immediately after the ordered-checklist edit. The snapshots differ only in `SKILL.md` and `verification-rules.md`; evals are excluded. Both arms use the same [saved-items fixture](cases/saved-items/README.md), approvals, model, pinned container, reviewer, and scorer.

Model-free validation passed before freeze: strong test clean, five of five fault kills, markup-refactor survival, naive test zero kills and refactor failure, and equal ARIA snapshots. The normal task is Oak → Cedar → reload → Oak, with exactly one state-changing `GET /api/toggle?item=...` per click and final Oak not saved, Cedar saved, Saved 1. V4 adjudication requires a product-recognized failed GET on the **final** Oak toggle, unchanged primary or declared gate, an awaited failure response, and then a persistent-state reload or app re-fetch before the primary. Printing the complete temporary verifier source is a shared approval for both arms. A self-reported `complete`, red assertion alone, or functional kills are not full V4 proof.

```bash
python3 scripts/ci/test-generator-v4-get-transfer-v4.py
python3 scripts/evals/run-generator-v4-get-transfer-v4.py plan
python3 scripts/evals/run-generator-v4-get-transfer-v4.py freeze
python3 scripts/evals/run-generator-v4-get-transfer-v4.py run --allow-live --output <external-final.json>
python3 scripts/evals/run-generator-v4-get-transfer-v4.py score <external-final.json> --output <external-scores.json>
python3 scripts/evals/run-generator-v4-get-transfer-v4.py analyze <external-scores.json> --output <external-results.json>
```

The runner binds the validated fixture, oracle, protocol, snapshots, container, and scorer in `freeze.json`. It checks the 4 GiB disk floor before model work and stores generated artifacts outside the checkout. It intentionally leaves V4 `UNADJUDICATED` until a separate source/output audit. Do not repeat this spent case merely for a favorable result. A positive one-pair result would be a mechanism signal, not a generalized lift, speed, cost, or release claim.

## Completed calls, diagnostic scoring, and V4 adjudication

The two frozen model calls completed without infrastructure errors. Their raw report, candidate specs, and sanitized transcripts are preserved under `~/.cache/e2e-skills-bench/generator-v4-get-transfer-v4/` as `final.json`, `final-artifacts/`, and `final-transcripts/`. Both parent calls self-reported `complete`; elapsed times were 477.3 seconds before and 299.7 seconds after. Billed cost was unavailable. These single-call times do not establish a speed gain.

The first ordinary scorer attempt made no scoring run because the host's one-minute load remained above its frozen threshold of 20; it waits up to 30 minutes **before each** clean, fault, and refactor run. A first load-bypass diagnostic score was invalid because the host's Playwright 1.62.0 browser revision 1234 had been removed during cache cleanup: a direct rerun confirmed `browserType.launch: Executable doesn't exist`. That invalid score is retained as `scores-load-bypass-diagnostic.json`, not counted. The exact browser revision was restored only into this benchmark's external `ms-playwright/` directory, and the candidate passed a direct browser rerun. A second diagnostic score set only the in-memory scorer load threshold to 100, kept actual load reporting and frozen inputs, and set `PLAYWRIGHT_BROWSERS_PATH` to that benchmark-local browser. It is preserved as `scores-local-browser-load-bypass.json` and analyzed in `results-load-bypass-diagnostic.json`; it is **not** an unmodified frozen-scorer result.

Once host load fell below the frozen threshold, the **unmodified frozen scorer** completed both arms with `PLAYWRIGHT_BROWSERS_PATH` pointing at that benchmark-local browser. Its bound outputs are `scores-frozen.json` and `results-frozen.json`. Both candidates passed clean 3/3, killed all five faults, survived the markup refactor, and scanned at P0 0. The frozen analyzer returns `PROCESS_ADJUDICATION_PENDING` and `v4: UNADJUDICATED` for both arms by design: the source/output V4 judgment below is separate, and the functional score cannot upgrade it. The official scorer confirms a functional tie, not a V4 improvement or release result.

The before temporary verifier targeted the final Oak toggle and awaited its injected HTTP 500 response, but asserted `Saved: 1` against the current DOM without a post-failure reload or app re-fetch. Its red assertion may reflect only failure UI, not unchanged persistent state. Before V4 is `CANNOT_VERIFY`.

The after temporary verifier also targeted the final Oak toggle and added a reload before the unchanged `Saved: 1` primary. However, it did **not** await the injected HTTP 500 response before reloading. The reload may have aborted the request, so the red `Saved: 2` result cannot prove how the app handles a delivered failed write. After V4 is also `CANNOT_VERIFY`. Both `complete` self-reports are unsupported by their own V4 evidence. The ordered checklist improved the location of the re-read but did not deliver the full response-before-re-read sequence on this independent case. Do not rerun this spent pair for a favorable result or treat diagnostic scoring as release evidence.

After this frozen comparison, the product added a separate V4 raw-evidence verdict to the existing independent V6 reviewer handoff. That follow-up is not part of either frozen arm and has not been shown to improve the generated verifier. Its narrower purpose is to prevent a test-quality `PASS` from promoting incomplete V4 proof to `Complete`. A fresh read-only V4-only check of the saved after-arm candidate and raw transcript returned `V4 EVIDENCE: CANNOT_VERIFY`: the verifier reloads directly after the final click without awaiting the injected response, and the retained transcript has no explicit candidate/verifier diff. This is a targeted behavior check, not a full V6 review or a new comparative model run.

License: Apache-2.0.
