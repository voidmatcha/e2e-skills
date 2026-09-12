# Roadmap item 5: exploration fallback

Status: `NOT_RUN` / no protocol frozen. This directory exists only to hold candidate future arms for the existing exploration chain (`playwright cli` → `agent-browser` → MCP → ARIA fallback, `skills/playwright-test-generator/SKILL.md`) in one place, instead of scattered across unrelated documents. Nothing here is authorized to build. The rule this item has carried since it was first scoped: no new adapter for feature parity alone — establish one concrete exploration capability gap first.

## Candidate arm 1: recorded-trace exploration

Source: a Korean fintech (Toss) FE platform team talk, cited in [`docs/llm-generated-e2e-test-evidence.md`](../../docs/llm-generated-e2e-test-evidence.md#transferable-workflow-patterns). Proposed converting a developer's recorded manual walkthrough into test coverage. Evaluated 2026-09-11 and deferred, not rejected outright:

- **Trigger**: only reconsider if `benchmarks/ours-vs-planner-pilot-v1`'s real 36-cell pilot (not its smoke stage, which is unscored and excluded from every denominator) produces `exploration-evidence.json` logs showing at least one `unknown`-provenance or unreached required state across both targets — i.e. a concrete gap the existing chain actually cannot resolve. A feature-parity argument alone does not authorize a new arm.
- **Checked 2026-09-12, after the pilot completed: trigger did not fire, arm stays deferred.** All 36 `exploration-evidence.json` files were read. Literally, 17 `unknown`-provenance claims and 12 unreached-required-state cells exist — but every one of them is on the `S3` impossible/honesty-control scenario, where the app genuinely lacks the feature being searched for (e.g. `Export as PDF`, `Sign in / Log in`) and the exploration chain correctly reports it absent; that is the intended honesty-control behavior, not a capability gap. Restricted to the satisfiable scenarios (`S1`/`S2`) only, there is exactly one `unknown`-provenance claim (`A-S1-planner_plus_ours-r2`, claim `L11`, the `Loading…` paragraph) — and it originated from the *planner* arm's own delta (`source_arm_stage: "official_planner_delta"`), was never used in the final test, and mismatches the frozen oracle; it is not evidence that this repo's own exploration chain (`playwright cli` → `agent-browser` → MCP → ARIA fallback) failed to resolve anything on a satisfiable scenario. No concrete gap materialized.
- **Even if the gap materializes**, general-skill fit is a separate question from technical feasibility and must be re-evaluated at that time, not assumed: this project is a portable, install-anywhere public skill, not an internal platform team's tool built for one company's known workflows and infrastructure (device farm, logging pipeline). Recording a trace today requires `npx playwright codegen --save-trace=trace.zip <url>` — an undiscoverable flag most users won't know, and it puts the manual-exploration burden back on the human, in tension with this project's automation value proposition. This convenience problem is explicitly parked, not solved, and blocks nothing else.
- **If ever built, the mechanism is diff-based, not raw conversion**: a naive trace-to-test conversion would duplicate whatever the generator's existing Step 1 coverage-gap analysis already covers. The corrected design feeds the human trace into that same coverage-gap step as one more evidence source, and only extracts the delta — states/actions the trace reaches that neither the existing test suite nor the arm's own exploration already cover — rather than converting the trace wholesale.

## Candidate arm 2: adapter-by-adapter measurement

Source: Slack Engineering's agentic-testing post, cited in the same evidence table. The current exploration chain's ordering (CLI-first, then `agent-browser`, then MCP, then ARIA fallback) is a portability default, explicitly not a measured efficiency claim (`skills/playwright-test-generator/SKILL.md:179-181`: "Do not claim that this ordering is universally faster, more reliable, or more token-efficient"). No benchmark currently records which adapter a run actually used, or its time/turn/cost, per cell.

- **Trigger**: none required to *log* this — it is a logging addition, not a new adapter.
- **Checked 2026-09-12: the opportunity to add this to `ours-vs-planner-pilot-v1` at zero marginal cost is gone.** That pilot finished (`status: COMPLETE`, 2026-09-12) without an adapter-identity field in `exploration-evidence.json`; its 36 archived files are frozen evidence now and are not retrofitted. `subagent-routing-v1` was considered as the next opportunity, but on inspection it is not actually a fit: its cells delegate finding-verification and failure-classification to named subagents and never drive a browser, so no exploration-chain adapter (`playwright cli` / `agent-browser` / MCP / ARIA) is ever selected inside it. There is currently no live, running protocol that exercises `playwright-test-generator`'s Step 3 exploration to attach this logging to.
- **Proposed schema addition, ready for the next protocol that does run Step 3** (e.g. a future item 2 dual-candidate pilot, or a re-run of item 1): add one required object to `exploration-evidence.schema.json`'s per-cell record —

  ```json
  "adapter_used": {
    "source": "playwright_cli | agent_browser | mcp | aria_fallback | none_reached",
    "reason_for_tier": "cli_available | cli_absent_agent_browser_used | cli_and_agent_browser_absent_mcp_used | no_browser_source_available",
    "fallback_occurred": false,
    "wall_seconds_this_stage": 0.0,
    "browser_actions_this_stage": 0
  }
  ```

  `source` records which tier of the chain actually ran the exploration for that cell; `fallback_occurred` is `true` only when a higher-priority source was attempted and failed closed (not merely "wasn't installed" — see `SKILL.md`'s existing absent-vs-failed distinction); the two `wall_seconds`/`browser_actions` fields let a future comparison separate adapter overhead from generation-stage cost, which the existing `usage` block conflates today.
- **Trigger for acting on the data**: only after enough cells accumulate real adapter-usage records does a claim like "CLI-first is faster on average" become falsifiable. Until then this is instrumentation, not a benchmark result, and must not be reported as one.

## What this is not

Not a preregistered protocol. No `protocol.json`, no runner, no cost ceiling, no target selection. If either candidate arm above is ever authorized to move forward, it gets that full treatment (matching `benchmarks/ours-vs-planner-pilot-v1/` and `benchmarks/subagent-routing-v1/`) at that time, not now.
