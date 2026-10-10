# Generator skill-effect v4: full-pool comparison

Status: **INCOMPLETE (account usage limit)**. Live execution was attempted, but the first 16 scheduled cells (32 attempts including retries) all returned Claude Code's weekly-limit error. Recorded usage was $0 and no test deliverable was produced. Execution was interrupted rather than continuing known-failing calls; its partial report is retained outside the checkout. No scores or effect estimate exist. The CLI error says the limit resets at 9am (Asia/Seoul), without identifying the reset date. After access is restored, use a new output path and rerun all 216 cells: resuming this partial report would retain failed cells, not retry them.

This successor addresses [v3's thin-pool stop](../generator-skill-effect-v3/README.md) by admitting all 36 validated tasks, including 18 prior floor tasks. It compares the exact frozen v3 `full-fixed` snapshot with `no-skill`, three fresh repetitions each: 216 calls. Existing v3 tests and scores are never counted as fresh comparison data.

[protocol.json](protocol.json) fixes the schedule, model, decision thresholds and limitations. The primary is the paired mean improvement in markup-refactor survival over all 36 tasks, with clean-pass and effective fault-kill guards. Prior floor/middle/ceiling strata are descriptive only. This is a public development experiment after inspecting v3, not a sealed release evaluation. It measures the frozen candidate rather than automatically tracking the current product.

The runner reuses v3's validated fixtures, snapshots and deterministic scorer through an explicit module adapter. `plan` verifies their exact frozen digests and complete validation coverage. `freeze` creates a separate create-once lock binding protocol bytes, both runners, fixture and snapshot bytes, validation provenance and every shuffled schedule cell. `run`, `score` and `analyze` refuse drift; final analysis also requires every expected cell exactly once and binds scores to the report digest. Execution outputs must be outside the checkout.

Estimated model cost is **$50.76**: 108 skilled calls at an assumed $0.40 and 108 baseline calls at $0.07. The skilled estimate has not been measured by v3 and may be inaccurate. Each attempt has a $4 budget; up to one infrastructure retry is inherited, giving a nominal maximum of 432 attempts and $1,728 in CLI budgets, not a billing guarantee. There is no overall spend cap. No live run is authorized by preparing this protocol; launching requires an explicit `run --allow-live` action after the cost review. Model calls use one worker; deterministic scoring runs separately and sequentially.

```bash
python3 scripts/evals/run-generator-skill-effect-v4.py plan
python3 scripts/evals/run-generator-skill-effect-v4.py freeze
# After approval of the live execution and cost:
python3 scripts/evals/run-generator-skill-effect-v4.py run --allow-live --output /absolute/cache/v4/final.json
python3 scripts/evals/run-generator-skill-effect-v4.py score /absolute/cache/v4/final.json --output /absolute/cache/v4/scores.json
python3 scripts/evals/run-generator-skill-effect-v4.py analyze /absolute/cache/v4/scores.json --output /absolute/cache/v4/results.json
```

Reviewer reads, Agent tool calls and scanner commands are process indicators. They do not prove independent review quality or successful V4 failure injection. A separate audit must locate the introduced defect, expected failing test, restoration, successful rerun and reviewer verdict before claiming those workflow steps succeeded. Until that evidence exists, those claims remain UNVERIFIED. No generator behavior change or simplification is justified by this incomplete experiment.
