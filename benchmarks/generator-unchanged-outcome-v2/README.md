# Unchanged-outcome v2 directional measurement

Apache-2.0. This is a new development comparison; v1 remains immutable.

Status: **NO_DIRECTIONAL_SIGNAL**. The final 30-run browser readiness matrix passed; 26 offline runner tests and the review/security gate passed before launch. Both arms and the twelve-attempt schedule were frozen before the first model call. All 12 generation calls completed without retries, infrastructure errors, or timeouts. The first two model-free browser scoring attempts stopped at the mandatory 4 GiB disk floor after 7 and 8 candidates; both incomplete outputs are preserved externally. After capacity was restored, a third create-only scoring pass completed all 12 candidates, followed by source/report/trace adjudication. The full local CI mirror and separate pre-push security rerun passed after closeout. No push was performed.

The verified causal primary kills were **before 6/6 and after 6/6**: each arm killed the fault at its unchanged-DOM assertion after action-linked render completion. Each candidate passed clean 3/3, the markup refactor, and both corresponding synchronous/disabled fault guards, with zero scanner P0 hits. This paired development comparison has no headroom to show an additional detection benefit from the revised guidance. The frozen scope guard also failed: before `response-before-render` repetition 1 wrote four `.playwright-cli/page-*.yml` files outside the approved test-file scope. The analyzer therefore reports `NO_DIRECTIONAL_SIGNAL`, `guards: false`, and `release_equivalence: false`; billed USD was not available.

Posthoc scope adjudication: that candidate used the project-local Playwright CLI, whose documented output location is `.playwright-cli/` in the worktree (`skills/playwright-test-generator/exploration-preflight.md` § Guard for Playwright CLI); the generator contract says to list this as exploration runtime output, not a generated file or stage it. The inherited scorer counted every changed path outside `tests/` as `out_of_scope_writes`, without distinguishing this exact approved runtime output. The frozen `guards: false` result is preserved, but it does **not** by itself prove a product write-scope violation. A successor must freeze a narrow, provenance-checked runtime-output rule before execution; arbitrary scratch, app, config, or instruction-file writes must still fail.

The separate descriptive transcript audit found that all 12 reviewer packets named the approved scenarios and completion sequence, but none included the verbatim applicable V1 subsection or a full structured V1 plan; explicit per-scenario V1 labels appeared in 5/6 after packets and 0/6 before packets. These observations do not establish V1/V6 workflow compliance. The two fixtures are correlated timing variants of one constructed stale-state defect class. This result neither repairs the adverse v1 result by causal proof nor establishes a general improvement or release readiness.

`reports/` retains the final generation report, generated specs, complete scoring report, bound causal audit, analyzer result, descriptive process audit, and the earlier resource-blocked closeout. The 12-call transcripts, raw browser JSON/trace files, and both partial scoring attempts remain in the external `gen-unchanged-outcome-v2-run` cache; they were not copied into the repository because raw diagnostics can contain machine-local paths. The archived scores and audit bind to those originals by SHA-256, so full evidence replay requires the external files. No originals were deleted.

Two new fixtures exercise enabled asynchronous unchanged outcomes, including a response that precedes rendering. Each also includes synchronous and disabled controls. The before arm is the exact v1 after-snapshot; the after arm overlays only the current scenario-design and verification-rules references. No root eval changes enter either arm.

The completed schedule had twelve sequential generation attempts: two fixtures, two arms, three repetitions. The fixtures are correlated timing variants of one stale-state defect class, not two independent defects; neither are the three repetitions independent defects. This experiment cannot establish statistical significance, generalized quality, or release equivalence.

## Commands

Run from the repository root. All execution outputs must be outside the checkout. No dependency installation or model call occurs in plan, readiness, freeze, score, or analyze.

```sh
python3 scripts/evals/run-generator-unchanged-outcome-v2.py plan
python3 scripts/evals/run-generator-unchanged-outcome-v2.py readiness --output /absolute/external/readiness.json
python3 scripts/evals/run-generator-unchanged-outcome-v2.py freeze --readiness /absolute/external/readiness.json
# Historical live step: the twelve authorized model attempts are already spent; do not repeat them.
python3 scripts/evals/run-generator-unchanged-outcome-v2.py run --allow-live --output /absolute/external/final.json
python3 scripts/evals/run-generator-unchanged-outcome-v2.py score /absolute/external/final.json --output /absolute/external/scores.json
python3 scripts/evals/run-generator-unchanged-outcome-v2.py analyze /absolute/external/scores.json --audit /absolute/external/audit.json --output /absolute/external/analysis.json
```

Freeze is create-only. Readiness must prove three clean runs, stale assertions surviving the delayed DOM mutant, request-only gating surviving the response-before-render mutant, and render-complete gating killing at the final DOM assertion. Reference tests live outside the model fixtures. The app's mutation keeps response payload and completion acknowledgement correct. Guard reference tests must detect their corresponding synchronous and disabled mutants. No paid run starts until readiness is bound into a freeze. Freeze snapshots the then-current references, so freeze only after product edits finish.

Scores retain every browser JSON report and trace archive with hashes and sanitized paths. Scoring retains ordinary any-red kills as secondary evidence. Primary credit is adjudicated separately using generated source, error location, and trace evidence establishing successful action-linked render completion before the DOM outcome assertion. A response assertion or failed completion wait cannot earn primary credit.

The scorer emits an audit template. Fill each candidate entry with `status` (`VERIFIED` or `UNVERIFIED`), `primary_causal_dom_kill`, `synchronous_covered`, `disabled_covered`, `synchronous_guard_killed`, `disabled_guard_killed`, and evidence. Evidence must identify generated source paths/lines, bound raw report paths, and the completion and final-assertion trace events. `analyze` rejects unbound reports, changed artifacts, missing entries, inconsistent any-red kills, and unverified attribution. A truthful primary miss may be VERIFIED with `primary_causal_dom_kill: false`; a failed setup/gate or ambiguous failure must stay UNVERIFIED.

Full causal adjudication remains a human/agent review step; the harness intentionally does not infer completion or coverage from regexes or self-reported workflow status. V1 plan and V6 approved-plan handoff are descriptive transcript-audit evidence and must be reported separately from primary outcomes.
