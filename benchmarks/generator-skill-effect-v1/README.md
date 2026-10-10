# Generator skill-effect v1: does `playwright-test-generator` write tests that catch more faults? (2026-10-05)

Status: **`INCONCLUSIVE` under the frozen rule: the no-skill baseline scored 0.927 on the primary metric, above the preregistered 0.90 ceiling, so this task set has no room to show a fault-detection lift.** All 60 calls completed and were scored ($11.72, no retries, no timeouts, no drift). Descriptively, the skill arm scored **1.000** (30/30 deliverables green on the correct app, 150/150 seeded faults killed) against **0.927** without the skill (paired lift +0.073, 95% CI 0.000 to +0.167; better on 3 of 10 cases, worse on none), at **6.05 times the cost** and 3.2 times the wall time. The clearer difference is in the secondaries: specs written with the skill survived a behavior-preserving markup refactor in 23/30 calls versus 12/28 without it. This is not evidence that the skill is unnecessary; it is evidence that `claude-sonnet-5-5` already verifies nearly every stated criterion of these small apps without it, and that the design needs harder tasks before the primary metric can separate the arms.

## Why this experiment exists

`playwright-test-generator` had no live quality measurement. The closest evidence, the [36/36 fixture-fault matrix](../fixture-faults/README.md), shows that the fault operators separate strong tests from weak ones; it says nothing about the tests the generator writes. The debugger skill-effect series ([v1](../debugger-skill-effect-v1/README.md) to [v4](../debugger-skill-effect-v4/README.md)) also taught four lessons that this design applies: zero-tool prompts over curated artifacts hit a ceiling and author-written notes leaked the answer, so here the model works with tools in a real project and nothing it sees names a fault; labels assigned with the skill's own tables biased the result, so here the truth is seeded application behavior and scoring is a Playwright exit status, not a judge; a hand-typed timestamp was wrong, so the freeze records `date -u` at freeze time plus SHA-256 digests of every input; and parallel load left calls unscored, so model calls run two at a time and scoring runs alone, sequentially, after every call has finished.

## Design

Ten fresh single-page apps ([`cases/`](cases/)), each a Node server with in-memory state, a Playwright 1.62 config whose `webServer` starts the app on a loopback port, a `README.md`, one existing spec, and a Git baseline commit: a guestbook, product search, a cart, a sign-in portal, a preferences form, a task board, a newsletter signup, a poll, a notes list with inline editing, and a paginated list. None reuses the archived counter fixture, the writescope-demo todo app, or any case from the skills' own evals or the debugger benchmarks. The task for each case lists numbered acceptance criteria (for example "entries are stored on the server, not only in the page"); the model sees the task, the project and the correct app, and is asked to add E2E tests under `tests/`.

Truth ([`truth/`](truth/)) is five seeded faults per case, applied to a copy of `app.mjs` only at scoring time, one per stated criterion plus one surface fault: a surface fault that breaks the happy path, and four that break only a stated detail (`precision`: exact text, count, order, absence, which item changed), the server side of a write (`persistence`: the page shows success but a reload or API read does not), a stated keyboard, focus or enabled/disabled behavior (`interaction`), or an edge value (`boundary`). Each case also has a behavior-preserving refactor of the markup (ids, classes and nesting change; roles, labels, names and visible text do not). Before the freeze, `validate` proved for every case that the existing spec stays green under every fault, an author-written strong spec passes twice, kills all five faults and survives the refactor, and an author-written happy-path spec misses at least two faults (it missed three or four in every case; [`reports/validation.json`](reports/validation.json)). Neither author spec is ever shown to a model.

Arms: `skill` (same prompt, tools, approvals and project, plus "read and follow the working-tree `playwright-test-generator` skill", staged outside the project with the working-tree `e2e-reviewer` skill that its Step 6 invokes; the `Skill` tool is unavailable, so the skill's own inline-fallback instruction applies, as on a Codex install) and `no-skill`. Host: Claude Code 2.1.289, `claude-sonnet-5-5`, tools `Read,Grep,Glob,Bash,Write,Edit,Agent`, no settings, no MCP, no session persistence. Ten cases, two arms, three repetitions, seeded shuffle, 60 calls, two workers, per-call budget $4, run cap $90, wall-clock limit 1500 s per call. The prompt tells both arms that the run is non-interactive and grants, as explicit per-row approvals, every scenario, every file under `tests/`, and the exact Playwright, `node app.mjs` and `playwright cli` exploration commands; control-file rows are opted out. A call that hits its wall-clock or budget limit is scored on whatever it wrote (an agent outcome); only a CLI crash or a non-JSON envelope is retried, once. [`protocol.json`](protocol.json) was frozen with digests of every case, truth file, both skills, the fixture lockfile, the prompt frame, the output schema and the runner before the first scored call. Two unscored smoke calls on an out-of-corpus tip calculator ([`smoke/`](smoke/), [`reports/smoke-skill.json`](reports/smoke-skill.json), [`reports/smoke-no-skill.json`](reports/smoke-no-skill.json)) calibrated the budget and timeout before the freeze.

Scoring, per call, is deterministic: the delivered spec files (every new or modified `*.spec.*` under `tests/`, read from `git status` against the baseline) run three times on the correct app (`clean` needs 3/3 green), once on each fault variant (`killed` when at least one test fails with no Playwright-level error), and once on the refactor; `skills/e2e-reviewer/scripts/scan.sh` counts P0 and P1/P2 smells on the delivered files alone. Writes outside `tests/` are recorded and discarded. **Primary metric: effective fault-kill rate**, faults killed / 5, counted 0 when the deliverable is not clean or absent.

Decision rule (frozen): `PASS` needs paired lift (skill minus no-skill, per-case means) >= +0.10, a case-cluster bootstrap 95% CI lower bound > 0, a skill clean-pass rate not more than 0.05 below no-skill, and a no-skill primary below the 0.90 ceiling; `INCONCLUSIVE` on any unscored call, drift, spend-cap stop, incomplete schedule, or a baseline at or above the ceiling; otherwise `FAIL`. Power: with ten cases and an assumed paired-difference SD of 0.25, the minimum detectable lift is about 0.22 at 80% power, so `FAIL` means "no large effect shown", not "no effect". The skill/no-skill cost multiple is reported, not gated.

## Results

Machine-readable: [`reports/claude-sonnet-results.json`](reports/claude-sonnet-results.json) (decision), [`reports/claude-sonnet-scores.json`](reports/claude-sonnet-scores.json) (per-call scoring), [`reports/claude-sonnet.json`](reports/claude-sonnet.json) (raw calls, envelopes and self-reports), and the delivered files under [`reports/claude-sonnet-artifacts/`](reports/claude-sonnet-artifacts/).

| Measure | `skill` | `no-skill` |
| --- | ---: | ---: |
| Calls scored | 30 of 30 | 30 of 30 |
| **Primary: effective fault-kill rate** | **1.000** | **0.927** |
| Deliverable written | 30/30 | 30/30 |
| Green on the correct app 3/3 (`clean`) | 30/30 | 28/30 |
| Faults killed, given clean | 150/150 | 139/140 |
| Refactor survival, given clean | 23/30 (0.767) | 12/28 (0.429) |
| Scanner P0 / P1-P2 heuristic hits | 0 / 0 | 0 / 0 |
| Scanner LLM-triage hits (not findings) | 313 (10.4 per call) | 339 (11.4 per call) |
| Self-reported status | 3 complete, 27 partial/blocked | 30 complete |
| Cost (list price) | $10.06 ($0.335 per call) | $1.66 ($0.055 per call) |
| Summed call time, turns | 2463 s, 281 | 779 s, 155 |
| Input tokens (incl. cache) / output tokens | 6.36 M / 124 k | 1.17 M / 60 k |

Paired lift +0.073 (bootstrap 95% CI 0.000 to +0.167); per-case differences: gen-02 +0.333, gen-06 +0.333, gen-03 +0.067, the other seven 0. Frozen checks: lift >= 0.10 **not met**, CI lower bound > 0 **not met**, clean-pass not worse met, baseline below ceiling **not met**; the ceiling failure makes the status `INCONCLUSIVE` rather than `FAIL`.

The three no-skill misses were: `gen-06` r2, a spec that hard-coded its staging port (`page.goto("http://127.0.0.1:5107/")` in a two-client test) and so failed 3/3 on every other port; `gen-02` r3, a spec that passed 2 of 3 clean runs and timed out in the third (flaky); and `gen-03` r1, a green spec that did not check the quantity floor and so missed `f3-quantity-below-one`, the only fault missed by any clean deliverable. By fault class, given clean, every class was killed 1.000 by both arms except `boundary` without the skill (10/11). The 11 refactor failures in the skill arm and 16 without it were all CSS id or `#id`-scoped locators on elements the refactor renamed; roles, labels and visible text were unchanged.

Chronology: the protocol was frozen at 2026-10-05T09:08:43Z (18:08 KST) after the three cases that failed the first model-free validation (a `form.reset()` race in gen-01 and gen-09, a wrong expected count in the gen-02 strong spec) had been fixed and spot-validated; the full validation of the frozen bytes then ran to completion at about 09:50Z with zero problems ([`reports/validation.json`](reports/validation.json)), and the first scored call started at 09:50:52Z, after it. No case, truth file, skill file or runner byte changed after the freeze (`input_drift: false`).

What the skill arm did with its workflow is visible in the self-reports: 27 of 30 calls ended `PARTIAL/BLOCKED`, most often because V6 needed a separate reviewer actor, V2/V3 probes were skipped or `CANNOT_VERIFY`, or live exploration was replaced by reading `app.mjs`; 11 of 30 mention running the scanner. The skill's completion matrix therefore judged its own output stricter than this benchmark did, while the no-skill arm reported `complete` 30 times, including the two deliverables that were not green here.

## Limits

- **Ceiling.** The headroom rule was checked against an author-written happy-path spec, which missed three or four faults per case, not against the model; the model without the skill read the numbered criteria and verified almost all of them, killing 139 of 140 faults on its clean deliverables. A null result on the primary says nothing about whether the skill is needed; it says these criteria-listed tasks on small apps were too easy for the baseline. A rerun needs tasks whose criteria are not spelled out, larger or noisier apps, or faults the model does not already catch (hidden server-side writes, timing, multi-page flows), and a smaller baseline model as a second host.
- One host and model family, three repetitions, ten author-written apps with in-memory state. Faults are seeded one per stated criterion, so this measures whether the delivered tests verify what the task stated, not fault prevalence in production suites.
- Refactor survival, scanner counts, flake and the two non-green no-skill deliverables are secondary and descriptive: no threshold was preregistered for them and none is claimed. The refactor variant is one author-written rename per case, so 23/30 versus 12/28 is a difference on these ten pages, not a general locator-robustness rate.
- The skill is built around an interactive approval gate and a user who answers it. The harness grants every approval in the shared prompt; how far a headless skill call follows its own workflow (exploration, scanner, V2-V5 probes) is part of what is measured, and the smoke call already showed it skipping exploration and the scanner.
- The `Skill` tool path to `e2e-reviewer` is unavailable here; the skill arm uses the skill's documented inline fallback.
- Scanner smell counts are mechanical (Tier 2/3) and secondary; LLM-triage hits are reported separately and are not findings.
- The cases and the smoke case are spent: a rerun needs new cases and a new protocol version.

## Reproduce

```bash
npm ci --prefix scripts/evals/fixtures
python3 scripts/evals/run-generator-skill-effect-v1.py validate --output /abs/validation.json
python3 scripts/evals/run-generator-skill-effect-v1.py run --output /abs/report.json --allow-live --workers 2
python3 scripts/evals/run-generator-skill-effect-v1.py score /abs/report.json --output /abs/scores.json
python3 scripts/evals/run-generator-skill-effect-v1.py analyze /abs/scores.json --output /abs/results.json
```

`run` refuses to start when any frozen digest in `protocol.json` has drifted; this protocol is spent, so a rerun is a new version with new cases. The delivered test files of every call are archived under [`reports/claude-sonnet-artifacts/`](reports/claude-sonnet-artifacts/), so `score` can be rerun on them without any model call.
