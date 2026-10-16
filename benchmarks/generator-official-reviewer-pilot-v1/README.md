# Official generator + e2e-reviewer pass: descriptive pilot (preregistration)

Status: **PREREGISTERED, NOT RUN** when this file was committed. Results, if any, are appended below the line marked `Results` in a later commit and never change anything above it.

This extends [generator-official-pilot-v1](../generator-official-pilot-v1/README.md), which compared the first-party Playwright Test Agents **generator** (arm A, `official-generator`) with this repository's **2.0.1** `playwright-test-generator` skill (arm C, `ours-2.0.1`) on six tasks. Refactor survival was 0.500 for A and 0.917 for C; effective fault kill was equal at 0.983. The question here is narrow: does a single `e2e-reviewer` review-and-fix pass on the official deliverables close that gap? A negative, mixed or INCONCLUSIVE outcome is an acceptable result. There is **no PASS/FAIL rule and no confidence interval**.

## Design

- **Third condition, B = `official+reviewer`.** For each of the 12 saved official-generator deliverables (6 tasks x 2 repetitions, `final-artifacts/<task>-official-generator-r<rep>/tests/`), stage a fresh fixture project the way the original runner staged the ours arm: the v3 `engine.stage`, the frozen `specs/plan.md`, the `tests/seed.spec.ts`, a baseline commit. Then copy the official spec files in as untracked files and make **one** Codex call (same Docker image, `gpt-5.5`, medium effort, 1500 s, CLI 0.159.3) that reviews them with the 2.0.1 `e2e-reviewer` (base commit `f83962e9`, staged at `/work/skill/e2e-reviewer`) and **fixes** every P0 finding and every mechanically fixable P1/P2 finding in place.
- **Constraints given to the model.** Keep every plan scenario covered, weaken no assertion (no deleted or loosened assertions, no `test.skip`/`fixme`, empty `catch`, fixed sleeps, `expect(true)`), add no scenarios, touch only `tests/`. The generator skill is not staged.
- **Arms A and C are reused, not re-run.** They come from the saved `scores.json` / `final.json` of the original pilot (2026-10-13), checked at analysis time against that pilot's report and freeze digests. The saved official artifacts that feed B are digest-bound in `freeze.json`, together with the original runner, protocol, freeze, adapter, plans, seed, container files and the reviewer skill tree.
- **Schedule.** 12 cells, shuffled with seed 20261015, one worker, sequential. Estimated Codex calls: 12 (plus at most one inherited infrastructure retry per cell).
- **Scoring.** Unchanged v3 engine and v8 shared scanner: clean 3/3, five seeded-fault kills, one markup refactor, scanner P0 and P1/P2 counts, flaky clean runs, plus the weakening text probe. For B the report also lists which official files the reviewer modified, removed or added.
- **Primary** is per-cell markup-refactor survival (1 only if clean 3/3 and the refactor passes). Guards: clean-all-three rate, effective fault kill, scanner P0 and P1/P2 counts.
- **Cost.** Reviewer-call seconds and parent-reported tokens are recorded separately; the "official generation + reviewer" totals add the saved generation seconds and tokens of the same 12 official cells (setup seconds excluded).
- **Output.** A three-arm view (A, B, C), per-task paired differences B-A and B-C, and the suggestive-evidence label for B vs A, B vs C and, for reference, A vs C.

## What would count as evidence

Same rule as the original pilot. Suggestive only: the same sign on refactor survival in at least 5 of 6 tasks with the clean-all-three rate, effective fault kill, scanner P0 total and scanner P1/P2 total not worse for the leading arm. Anything else (a 3-3 split, ties carrying the comparison, a one-task swing) counts as nothing. Weakening is a union of scanner P0 hits, text-probe hits, clean-passing specs that leave a stated-behavior fault unkilled, the reviewer's file changes, and any manual transcript reading, each labeled by method; no hit does not prove no weakening.

## Divergences from the original staging

- No `init-agents` output (`.codex/agents/*.toml`, `specs/README.md`) in B's workspace: no official agent runs, and the staging mirrors the ours arm.
- The brief ends with a review-and-fix line instead of the generation plan line, and the arm line asks for the reviewer pass; the frame, approvals, output schema, model, effort, timeout, container and Codex command are unchanged. One extra per-row approval is stated: the staged reviewer's pinned `scan.sh` invocation.

## Commands

```bash
python3 scripts/evals/run-generator-official-reviewer-pilot-v1.py plan
python3 scripts/evals/run-generator-official-reviewer-pilot-v1.py freeze   # already done in this commit
python3 scripts/evals/run-generator-official-reviewer-pilot-v1.py run --allow-live --output ~/.cache/e2e-skills-bench/offrev-pilot-v1/final.json
python3 scripts/evals/run-generator-official-reviewer-pilot-v1.py score ~/.cache/e2e-skills-bench/offrev-pilot-v1/final.json --output ~/.cache/e2e-skills-bench/offrev-pilot-v1/scores.json
python3 scripts/evals/run-generator-official-reviewer-pilot-v1.py analyze ~/.cache/e2e-skills-bench/offrev-pilot-v1/scores.json --output ~/.cache/e2e-skills-bench/offrev-pilot-v1/results.json
```

Resume an interrupted run with `run --allow-live --resume --output <same path>`. Stop rules match the original pilot (load above 40, infrastructure error after one retry, usage limit, disk below 4 GiB, any digest drift). The protocol, runner and `freeze.json` are not edited after the first scheduled call.

## Limitations

12 cells and 6 task clusters; B starts from A's own files, so B and A cells are not independent; A and C were run on a different day than B, so host load is not controlled; the 2.0.1 reviewer is a review skill and the measured effect is the skill plus the instruction to fix; parent token usage excludes child agents; one host and model; the mechanical plan, Playwright 1.62.0 fixture and author-written faults carry over from the original pilot. Nothing here is a release or a general accuracy claim.

## Results
