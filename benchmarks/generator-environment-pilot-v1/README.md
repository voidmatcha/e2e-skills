# Generator environment pilot v1

Status: PILOT_NOT_PROMISING. All twelve fresh generations, scoring, and analysis completed on 2026-10-08. The frozen schedule and implementation remain unchanged. See the archived [generation report](reports/final.json), [scores](reports/scores.json), and [comparison](reports/results.json).

Paired median elapsed reduction was 3.46%, below the frozen 25% threshold. Total elapsed time was 1,881.912 seconds for current and 2,004.857 seconds for environment-guided. All twelve outputs passed three clean runs and the markup refactor, with zero P0 scanner findings; however, v3-02 fault detection declined from 1.0 to 0.8. Both v3-02 outputs self-reported partial completion. This pilot does not justify adopting the environment-guidance bundle or claiming cost savings. Billed dollars and complete child usage remain unknown; V4 execution and V6 reviewer correctness remain unverified pending transcript adjudication.

A subsequent generator instruction correction addresses stale assertions for asynchronous actions whose expected value was already true. That correction was not present in either frozen pilot arm, has not been rerun in this comparison, and is not measured performance evidence. Raw transcripts remain in the external execution cache; generated specs are archived alongside the report.

This is a new, public-development pilot, not a change to the frozen v8 experiment. Both arms use the same frozen full-fixed generator and shared reviewer snapshots, model, effort, immutable container image, tools, scorer, and timeout. Only explicit exploration-browser selection and owned-server lifecycle guidance differ. Document trimming, independent-review removal, and relaxed V4/V5/V6 checks are out of scope.

Six tasks were selected from their task descriptions and fixture READMEs without consulting v8 per-case outcomes: v3-02 (recipe cards, numeric boundaries, aggregate persistence), v3-03 (roster rows and confirmation/cancellation), v3-05 (nested options, reordering, conditional preview), v3-07 (accessible selection limits and reservation persistence), v3-13 (search races and recent-search replay), and v3-14 (nested comments, editing, confirmation dialogs). These are the same public spent development fixtures, not a sealed or independent release holdout. Only each task string, never its fault or refactor truth, enters the model prompt.

The planned schedule is six paired tasks, two arms, one repetition, one worker. Each task gets fresh generation in both arms; arm order is balanced across pairs. Both start with no application server running. Existing v8 outputs are not reused. The guided arm must retain the skill's failed initial pinned preflight before starting the approved local app, origin containment, owned-process cleanup, and independent review. No application/configuration edits, package installs, or shared-process cleanup are authorized.

Before freezing or spending model usage, an opt-in model-free successor probe must demonstrate the exact CLI browser choice, pre-dispatch origin guard, app readiness, owned cleanup, and three clean smoke runs in the pinned image. The earlier Node-API Chromium probe alone is insufficient. The archived [successor probe](reports/environment-successor-probe.json) records `PASS`: explicit `--browser chromium`, a fresh origin-allowlisted session, blocked unapproved-origin fetch before navigation, owned cleanup, and three smoke passes. The exact installed CLI help/code and runtime were checked; official web documentation was not retrieved because the configured research CLI was unavailable. This is environment-readiness evidence only.

The comparison will include every attempt in elapsed time, report paired median time reduction, and retain clean 3/3, markup-refactor survival, seeded-fault detection, and P0 scanner guards. A 25% time reduction with no observed quality regression is only a practical signal for a larger comparison. It cannot establish quality equivalence, causal contributions of each environment change, dollar savings, complete child token accounting, or release readiness. Actual V4 and V6 correctness require separate transcript examination; aggregate tool counters are not proof.

Execution is opt-in. A frozen protocol and create-only binding record must exist before any live model call; partial or drifted matrices are never positive evidence. A 4 GiB free-disk floor protects existing evidence. Outputs and transcripts stay outside the checkout until explicitly reviewed and archived.

The new probe and pilot contract suites passed 5 and 11 offline tests respectively; the review and security gates passed before launch. The preceding full CI pass predates these new pilot files. A fresh full CI is still required before any commit; do not imply that the earlier pass validated the new implementation.

Inspect without model usage:

```bash
python3 scripts/evals/run-generator-environment-pilot-v1.py plan
python3 scripts/ci/test-generator-environment-successor-probe.py
python3 scripts/ci/test-generator-environment-pilot-v1.py
```

The CLI supports `run --allow-live --output <external-final.json>`, then `score <external-final.json> --output <external-scores.json>`, then `analyze <external-scores.json> --output <new-external-results.json>`. Never start another copy alongside an active invocation. Resume generation or scoring only with `--resume` after verifying the original process has exited and the freeze, image, report, and artifacts still match. An infrastructure attempt makes this pilot incomplete even when its internal retry produced a file; do not edit that record to resume a positive comparison. Analysis is create-only and does not overwrite an existing result.

License: Apache-2.0.
