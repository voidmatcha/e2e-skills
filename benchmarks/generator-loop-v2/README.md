# Generator autoresearch loop v2

Status: **offline build; not frozen; no calls made; model-selection justification unresolved**. This is a restart protocol for improving `playwright-test-generator` on five development tasks. The machine-readable contract is [protocol.json](protocol.json); the runner is [run-generator-loop-v2.py](../../scripts/evals/run-generator-loop-v2.py), with [offline tests](../../scripts/ci/test-generator-loop-v2.py). It makes no release or unseen-task claim.

The earlier `generator-loop-v1` adopted nothing. Its fixed `gpt-5.5` became unavailable with HTTP 400 on 2026-10-14 at about 23:50 KST, according to the stored final report. Iteration 1 is REJECT/hold under A1; its confirmation batch is void. Historical cells, partial confirmation results and the prepared iteration 2 edit are not v2 baselines or candidates.

The independent audit motivates the safeguards here: the old quality path ignored cost; overall fault kill concealed a clean-cell regression; the observed +0.20 had task-stratified permutation p about .133; styling-class state assertions explained the sidebar failures, while the container clause did not; the added self-search was not observed in the sidebar cells; and the rule text named a development selector and mirrored the grader perturbation. This does not preregister a replacement rule. The researcher must support each new hypothesis with failing cells from the fresh loop.

## Model selection is unresolved

The requested fixed model is **Codex `gpt-6-luna`, medium effort**, selected by the requested outcome-blind rule “highest arm-C process fidelity and delivery among the Codex v2 models in the first campaign attempt.” Only C process and delivery fields were inspected in the stored `multimodel-v2-codex-attempt1-armA-invalid` attempt. A/B and quality, survival and fault outcomes were not inspected for this selection.

That rule does **not** reproduce the requested choice:

| Model | Scheduled C cells | Delivered | Core fidelity | Independent review observed | Self-reported complete |
|---|---:|---:|---:|---:|---:|
| gpt-6-sol | 24 | 24 | 24 | 0 | 11 |
| gpt-6-luna | 24 | 23 | 23 | 0 | 12 |

These are the stored `itt_arm_summary["ours-2.0.1"]` delivery counts and `fidelity_table.arm_c` fields, checked against C-filtered raw records. Core fidelity means skill read, reference read and scanner execution in the imported evidence contract. Luna leads self-reported completion, which does not establish better process fidelity. Partial Terra data cannot supply a complete campaign comparison. Source result digests are in `protocol.json`.

The build retains the explicit Luna pin and records `selection_status: NOT_REPRODUCED`. **Freeze and every live command refuse before importing or configuring machinery**, even with `--allow-live`. Resolve the selection justification with the owner in a successor preregistration before execution. Do not silently redefine fidelity, substitute Sol or choose a model by quality. This build neither resolves that decision nor creates a freeze.

## Treatment, tasks and machinery

Every scheduled cell is arm C (`ours-2.0.1`); the label identifies the inherited workflow, while the candidate skill digest identifies its actual revision. No official-generator or reviewer-only comparison arm runs. The reviewer invoked inside the generator workflow stays fixed, as does the scanner.

The synthetic DEV allowlist is exactly `v2-11`, `v3-08`, `v2-18`, preserving the old hash-based split. The OSS DEV allowlist is exactly `zep-sidebar`, `zep-note-rename`. The runner never enumerates other task directories, opens `sealed-eval`, calls final evaluation or imports historical quality measurements. There is no final-eval subcommand. Neither a winning development candidate nor an adoption authorizes evaluation.

The runner imports the [Codex v2 machinery](../generator-multimodel-v2-codex/README.md) and the current [OSS machinery](../generator-oss-eval-v1/README.md), rather than copying or editing them. Their CHANGES files explain why the OSS runner now uses the corrected v3 transport over the v2 design: predecessor freezes remain intact. Synthetic generation uses v2's generation-only `reuseExistingServer: true` transformation; scoring retains the original false setting. Zeppelin uses the OSS DEV runtime, campaign lock, namespace cleanup, serial proxy/scoring phases and adjudicated fault scoring. No inherited multi-arm entry, drive, summary or broad task-binding function is called.

The OSS repair notes still defer predecessor rollout root-ID mismatch and ambient Git configuration defects. This wrapper adds an explicit-root mismatch refusal for cost completeness and sanitizes Git configuration/routing for its own disposable synthetic/research/review staging. It does not claim to repair every imported Git path; the inherited Zeppelin staging path remains a live review item. Existing source files and freeze bindings are untouched.

## Batches and decision

Iteration 0 consists of two fresh ten-cell baseline batches, `aa1` and `aa2`. Each has two repetitions of every DEV task. Pair order is seeded; the two slots for each task/repetition are adjacent, with randomized slot order. Their spread is the initial A/A noise estimate. A different model requires entirely new baseline data.

Iterations 1 through 8 each use ten fresh incumbent cells and ten candidate cells, interleaved in the same way. Only that iteration's fresh pair determines adoption. Historical measurements do not become the next control. The adopted skill tree becomes the incumbent; all subsequent comparisons regenerate the incumbent batch. Stop after eight iterations or three consecutive non-adoptions. A void batch produces no decision and terminates execution pending a new preregistration, rather than silently dropping missing cells.

Primary quality is the unweighted task mean of delivered, clean-3/3 and refactor-pass outcomes; a valid no-delivery cell is zero. Every task and both repetitions must be present. Candidate clean rate must not fall; scanner P0 and P1/P2 totals must not rise. Both fault-kill views must hold: all cells, with unclean cells zero, and the cell-weighted clean-only mean. No clean cells or missing fault attribution prevents adoption. Positive mutant failure credit requires independent attribution, rather than merely observing that some test failed.

Adopt for quality at survival delta at least +0.10 with processed token growth at most +10%, after all guards pass. Seconds are informational on this path. Otherwise adopt for cost if survival is not lower, all guards pass, and either tokens or seconds fall at least 15% while the other rises at most 10%. Otherwise reject. One cell moves quality by .10; adoption is a deterministic development decision, not a statistical significance claim.

Every decision includes the exact one-sided task-stratified permutation p, with hypergeometric task distributions convolved using rational arithmetic. It also reports min/max/range of every metric across equal-size batches of the exact incumbent digest, and whether the survival difference is within that width. At least two incumbent batches are required. On adoption, the adopted candidate batch and its subsequent fresh control provide that revision's initial spread. Within-task exchangeability is an assumption, not proven by interleaving; adaptive task reuse and temporal dependence limit the p-value. No cell-level p-value is reported or used to decide.

Generation cost sums every attempt's uncached input plus output, parent and linked child rollouts together. Cached input is reported separately. Missing usage, persistence gaps, mismatched root IDs or incomplete child linkage make costs incomplete; no zero filling permits adoption. Generation seconds also include retries. Researcher usage and elapsed seconds are recorded separately as overhead and are not hidden inside generation efficiency. There are no invented dollar costs.

## Researcher and deterministic stages

The Codex researcher receives a disposable container workspace containing only the incumbent skill and a scrubbed packet of failing DEV cell outcomes, delivered specs and recorded failure messages. No repository, campaign, task truth, patches, reference tests or evaluation directories are mounted. It may not fetch material from the internet. The adapter requires API networking; prompt restrictions and absent mounts do not prove complete outbound isolation or erase public training exposure.

Each iteration preserves `packet.json`, exactly one hypothesis in `hypothesis.json`, readable `hypothesis.md`, one unified `diff`, a separate `candidate/` skill tree and `researcher-run.json`. The hypothesis must cite failing call IDs, state one mechanism, predict an effect and specify falsification. The researcher cannot decide adoption. Raw generated reports go under `batches/<slot>/`, separate from the candidate source.

Added rule text must express a general principle, with no development-task-specific selector, regex, identifier, element/control name or example, and no restatement of grader perturbations. An automated screen catches obvious task literals and locator examples. A separate semantic reviewer must inspect all added wording and record `wording-review.json` with `diff_sha256`, `verdict: PASS`, reviewer identity and reason. That semantic assessment is not mechanically provable and must not be a researcher self-attestation. `review-candidate` runs repository checks on a disposable tracked checkout with the candidate overlaid, preserving a diff-bound PASS record. Neither step changes the repository skill.

All model-visible scope, plan, failure excerpts and prompt bodies pass through the provenance scrub, removing PR identifiers, public URLs and source file/line pointers. Exact final prompt artifacts are saved. This is heuristic removal: inspect live prompt and transcript artifacts before claiming that arbitrary prose or external fetching cannot leak pointers.

## Commands and artifacts

Safe offline inspection needs only the standard library:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/ci/test-generator-loop-v2.py
python3 scripts/evals/run-generator-loop-v2.py plan --iteration 0
python3 scripts/evals/run-generator-loop-v2.py plan --iteration 1
/bin/bash -p scripts/ci/review.sh
/bin/bash -p scripts/ci/pre-push-security.sh
```

After the unresolved model-selection decision has a successor preregistration, `prepare --campaign <new-external-root> --pool <dev-pool> --loop-runner <read-only-v1-runner> --dists <prebuilt-dev-dists> --source <isolated-source>` can snapshot inputs and scrubbed plans offline. It writes only to the new external root; repository and benchmark-cache outputs are refused. Do not pass an evaluation vault, a pool root containing model-visible evaluation source, or an existing campaign root. Preparation never creates a freeze or calls a model. Missing installed prerequisites and prebuilt distributions are errors, not permission to install or build them.

The future stages are non-model DEV `calibrate`, `freeze`, `run --iteration 0`, `score --iteration 0`, offline `adjudicate`, `analyze`, `decide`, then `packet`, `researcher`, semantic wording review, `review-candidate`, `validate-candidate`, `run`, `score`, `adjudicate`, `analyze`, `decide` for the next iteration. Every stage takes `--campaign`; stages after the baseline take `--iteration`. Calibration, freeze, researcher, run and browser score additionally require `--allow-live`, a resolved selection and matching bindings. Calibration uses the exact OSS same-test title/reason checks and binds only the registered DEV inputs; its PASS artifact is mandatory at freeze and rechecked thereafter. No such stage was executed in this build. No automatic all-iterations driver bypasses the reviews.

Offline adjudications use `--adjudications <json>` with `{slot: {call_id: {defect_id: boolean}}}`. The first score records raw clean/fault/refactor evidence; `adjudicate` requires attribution for every positive failure and creates a separate score artifact without rerunning models or browsers. Unknown fault credit in raw scores remains unknown and prevents adoption. `analyze` rederives metrics and costs; `decide` checks complete paired results and candidate provenance. Generated specs, transcripts and sessions are digest-bound before scoring; both initial A/A and historical noise inputs are checked against their backing reports and scores. Outputs are exclusive: interruptions and partial attempts cannot be overwritten as a successful resume. Keep all failed and rejected artifacts.

Freeze would bind protocol, README, runner, tests, imported source scripts, selected DEV bytes and distributions, exact plans, schedules, baseline/reviewer/scanner trees and one external campaign root. Candidates and reviews are bound before generation. Drift, rate/usage limits, namespace cleanup failure or terminal infrastructure outcomes end the attempt. The future runtime inherits the OSS disk floor, load pause and shared campaign lock. No model switching, automatic dependency installation, implicit variant build, commit or push is supported.

## Verification limits and required live checks

This build is offline only. The model selection justification is contradicted by the inspected C records, so the current protocol is intentionally not execution-ready. Offline synthetic tests can verify calculations, boundaries and imported API wiring; they cannot establish model availability, successful skill engagement, cost accuracy in a new CLI build or browser correctness.

Before any successor live loop, separately authorize and verify: the pinned image and installed CLI; current Luna availability; parent/child session persistence, root identity and additive token accounting; actual C skill/reference/scanner/reviewer behavior; generated prompt and plan scrubbing; container API networking and absence of evaluation mounts; synthetic generation/scoring config separation; Zeppelin bridge/proxy routing and exclusive lock; clean 3/3, refactor and same-test title/reason reference calibration for both DEV tasks; notePath creation, rename, DELETE/trash cleanup and namespace escape handling; remaining inherited Git staging isolation; and interrupted generation/scoring refusal. Reference calibration must be bound before a usable successor freeze. None was run here.

Five reused tasks, two OSS tasks from the same application, one model and adaptive repeated decisions cannot establish generalization. Any adopted skill would need a separately preregistered evaluation with genuinely unexposed material and another model; this build does not prepare, inspect or authorize it.
