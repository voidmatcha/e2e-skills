# Generator V4 evidence-gate pilot v2

Status: **NO_V4_LIFT / INCOMPLETE_V4_PROOF**. All six fresh calls and independent functional scores completed. This public-development successor uses the v1 after skill as its before arm and the new scenario-plan and completion-evidence wording as its after arm. It tests one spent library-search fixture in three fresh pairs, not a sealed release holdout. Both arms receive the same additional instruction to print any temporary V4 verifier source before removing it; this improves auditability but means the v1 report is not a direct control for v2.

The [frozen protocol](protocol.json) specifies the one-factor skill contrast, shared runner and approvals, alternating schedule, disk floor, and PASS guards before any model call. The analyzer intentionally returns `PROCESS_ADJUDICATION_PENDING`: a human must verify normal request method/endpoint/query/cardinality, the temporary source's route and failure, and red at the unchanged primary assertion or declared gate. Missing proof or a false `complete` blocks a positive claim even when generated tests pass. Stop before a call below 4 GiB free and preserve any partial results. No release, speed, or billed-cost claim follows from this development pilot.

```bash
python3 scripts/ci/test-generator-v4-get-pilot-v2.py
python3 scripts/evals/run-generator-v4-get-pilot-v2.py plan
python3 scripts/evals/run-generator-v4-get-pilot-v2.py freeze
python3 scripts/evals/run-generator-v4-get-pilot-v2.py run --allow-live --output <external-final.json>
python3 scripts/evals/run-generator-v4-get-pilot-v2.py score <external-final.json> --output <external-scores.json>
python3 scripts/evals/run-generator-v4-get-pilot-v2.py analyze <external-scores.json> --output <external-results.json>
```

Once live execution starts, do not change the frozen runner, protocol, snapshots, or report. Preserve failed and incomplete evidence.

## Adjudication of the completed pilot

The frozen report, scores, result, six sanitized parent transcripts, and generated specs are under `~/.cache/e2e-skills-bench/generator-v4-get-pilot-v2/` as `final.json`, `scores.json`, `results.json`, `final-transcripts/`, and `final-artifacts/`. The analyzer correctly remains `PROCESS_ADJUDICATION_PENDING`; this is the separate source-and-transcript judgment, not a rewrite of that result. All six calls returned `complete` without timeout or infrastructure error. Independent scoring found clean 3/3, primary fault kill 1.0, refactor pass, and zero P0 in every cell. Billed cost was unavailable.

| Cell | Preserved temporary V4 source and red outcome | Missing V4 proof |
| --- | --- | --- |
| Before 1 | HTTP 500; red at a status expectation, not the unchanged recent-search primary or declared settled-state gate | Normal request cardinality; relevant failed-write red |
| After 1 | HTTP 500; red at the recent-search assertion | Normal request cardinality and the required two concrete evidence lines |
| After 2 | HTTP 200 with a success-shaped response but no recent-search update; red at the recent-search assertion | An evidenced failed-write response; normal request cardinality |
| Before 2 | HTTP 200 with a success-shaped response but no recent-search update; red at the recent-search assertion | An evidenced failed-write response; normal request cardinality |
| Before 3 | HTTP 500; red at the recent-search assertion | Normal request cardinality |
| After 3 | No temporary V4 verifier created or run; still reported `complete` | Failed-write run and normal request cardinality |

The app's `GET /api/search?q=...` changes server-side recent-search history for queries of at least three characters, so V4 is applicable. A `waitForResponse` predicate or passing UI assertion is not proof of the expected request cardinality. HTTP 200 with `{recent: []}` is an altered success response, not the documented failure response the product could receive. All six cells therefore lack full V4 proof and nevertheless reported `complete`; the after arm meets neither the frozen two-PASS threshold nor its no-false-Complete guard. The new planning/evidence wording did not establish a directional V4 lift on this spent fixture. The preserved source makes this a stronger negative finding than v1's probe-attempt count, but it is still a one-case development result, not a general accuracy or release judgment.

Next iteration should not add another generic completion reminder. The repeated omission points to the need for a small, auditable V4 evidence artifact or executable check that captures normal request count and the injected response/unchanged assertion before a `Complete` verdict. Test that mechanism on a distinct case or with a controlled local negative fixture before another costly live comparison.

A narrow post-pilot skill change now requires a counted normal request and a product-recognized failure response, and gates V5/V6 on both V4 evidence lines. Eval 55 includes the documented-HTTP-200-error exception. Generator contract tests, eval validation, skill validation, a fresh read-only Codex interpretation check, and the full local CI passed. This change was **not** in either frozen v2 arm, and the interpretation check is not a live generation result. No behavioral gain is claimed for it yet; a distinct case and frozen comparison are needed before promoting it.

License: Apache-2.0.
