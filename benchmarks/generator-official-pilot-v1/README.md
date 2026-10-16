# Official Playwright generator vs 2.0.1 generator skill: descriptive pilot (preregistration)

Status: **PREREGISTERED, NOT RUN** when this file was committed. Results, if any, are appended below the line marked `Results` in a later commit and never change anything above it.

This is a small pilot, not a benchmark verdict. It asks one narrow question on a spent public development pool: when both receive the same frozen approved plan, how do the first-party Playwright Test Agents **generator** (`npx --no-install playwright init-agents --loop=codex`, Playwright 1.62.0 in the fixture) and this repository's **2.0.1** `playwright-test-generator` skill compare on the v8 scoring? A negative, mixed or INCONCLUSIVE outcome is an acceptable result. There is **no PASS/FAIL rule and no confidence interval**.

## Design

- **Tasks (6 of the 36 validated v3 tasks), fixed before any call by a deterministic rule.** Strata come from the historical no-skill refactor score in `benchmarks/generator-skill-effect-v3/protocol.json`: floor (== 0, 18 tasks), middle (0 < x < 1, 9), ceiling (== 1, 9). Draw 3 / 2 / 1 with `random.Random(20261013).sample` over each ID-sorted stratum, in that order. Result: `v2-22 v3-04 v3-09` (floor), `v2-06 v3-06` (middle), `v2-23` (ceiling). The union of their seeded-fault classes covers surface, interaction, precision, persistence, boundary and a11y.
- **Arms.** `official-generator`: the initialized `playwright_test_generator` custom agent, spawned natively by a Codex parent. `ours-2.0.1`: the full skill and reviewer at base commit `f83962e9` (release/2.0.1), staged with the v8 skill line. Healer and planner are not used.
- **Same input.** Both arms get the identical `specs/plan.md` (derived mechanically from the task text by `run-generator-official-pilot-v1.py write-plans`, committed under `plans/`), the identical `tests/seed.spec.ts`, and the identical plan sentence. The official arm additionally holds the `init-agents` output and one extra command approval for its project-local MCP server. Setup time is recorded and never counted as quality.
- **Schedule.** 6 tasks x 2 repetitions x 2 arms = 24 calls, shuffled with seed 20261014, one worker, sequential. Same model, effort and timeout as v8: Codex CLI 0.159.3, `gpt-5.5`, medium, 1500 s, immutable Docker image `sha256:687b18c4...`.
- **Scoring.** The unchanged v3 engine and v8 shared scanner: clean 3/3, five seeded-fault kills, one markup refactor, scanner P0 and P1/P2 counts, flaky clean runs, generation seconds, parent-reported tokens. Added: a weakening text probe (`test.skip`, `test.fixme`, empty `catch`, `expect(true)`, `toBeTruthy()`, `waitForTimeout`).
- **Primary** is per-cell markup-refactor survival. Guards: clean-all-three, effective fault kill, scanner P0 and P1/P2.
- **Output.** Per-task paired outcomes (official minus ours), an as-run view and an available-only view, never a verdict.

## Cell labels

A cell where `init-agents` fails, omits the generator, or whose three agent-file digests differ from the frozen ones is `UNAVAILABLE`: no model call, reported apart, excluded from available-only, scored 0 in as-run. It is never an application failure. Engagement of the official generator's MCP tools is **not observable** from the parent transcript; it is reported by a file-signature proxy (`// spec:` and `// seed:` headers on every delivered spec).

## What would count as evidence

Suggestive only: the same sign on refactor survival in at least 5 of 6 tasks with neither guard worse for that arm. Anything else (a 3-3 split, a one-task swing, differences carried by UNAVAILABLE or blocked cells) counts as nothing. Weakening is reported as a union of scanner P0 hits, text-probe hits, clean-passing specs that leave a stated-behavior fault unkilled, and manual transcript reading, each labeled by method; no hit does not prove no weakening.

## Stop rules and resume

Pause when 1-minute load exceeds 40 (up to 1800 s per wait); one model call at a time. Stop on an infrastructure error after the inherited single retry, a usage limit, disk below 4 GiB, or any digest drift. Resume with `python3 scripts/evals/run-generator-official-pilot-v1.py run --allow-live --resume --output <same path>`. The protocol, runner, adapter, plans and `freeze.json` are not edited after the first scheduled call.

```bash
python3 scripts/evals/run-generator-official-pilot-v1.py plan
python3 scripts/evals/run-generator-official-pilot-v1.py freeze
python3 scripts/evals/run-generator-official-pilot-v1.py run --allow-live --output ~/.cache/e2e-skills-bench/offgen-pilot-v1/final.json
python3 scripts/evals/run-generator-official-pilot-v1.py score  ~/.cache/e2e-skills-bench/offgen-pilot-v1/final.json --output ~/.cache/e2e-skills-bench/offgen-pilot-v1/scores.json
python3 scripts/evals/run-generator-official-pilot-v1.py analyze ~/.cache/e2e-skills-bench/offgen-pilot-v1/scores.json --output ~/.cache/e2e-skills-bench/offgen-pilot-v1/results.json
```

## Setup preflight (not pilot data)

Before freeze, one unscheduled call per arm on task `v2-01` (not in the pilot set) proved the container, `init-agents`, native agent spawn and scoring pipeline. Official arm: 5 spec files in 216.7 s, clean 3/3, refactor survived, effective kill 0.8. Ours: 1 spec in 530.3 s, clean 3/3, refactor survived, kill 1.0. These were not used to pick tasks, arms or metrics. Two things changed because of them before freeze: the adapter's event-census merge, and the file-signature engagement proxy (child MCP calls are invisible to the parent transcript).

## Limitations

12 cells and 6 task clusters per arm; one host and model; Codex's custom-agent path is one of several documented hosts for the official agents; the mechanical plan is not what the official planner would write and may under- or over-constrain either arm; the 2.0.1 arm normally designs its own scenarios; parent token usage excludes child agents for both arms, so the official arm's generation tokens are undercounted by an unknown amount; the fixture pins Playwright 1.62.0, not the documented 1.62.1; scoring uses author-written faults with one id/class refactor per task. A full run would need all 36 tasks x 3 repetitions (216 calls), a sealed pool for any release claim, a planner-produced plan arm, and a paired decision rule fixed in advance (at paired SD 0.35, about 0.16 detectable lift at 80% power on 36 tasks).

## Results
