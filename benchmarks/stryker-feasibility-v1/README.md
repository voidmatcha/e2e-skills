# Roadmap item 4: Stryker vs V2/V3

Status: `NOT_RUN` / preregistered, not yet frozen (2026-09-12). Lowest priority of the six roadmap items — skip if machine time is scarce. The machine-readable contract is [`protocol.json`](protocol.json); if this README and that file differ, the JSON controls. Nothing here is authorized to run: `design_only: true`, `execution_authorized_by_this_file: false`.

## Decision (already made, not open)

Default result: `REFERENCE_ONLY` (interop documentation for projects that already use Stryker), not a replacement for this repo's own V2/V3 targeted-fault verification. `skills/e2e-reviewer/references/upstream-rule-sources.md` already states the project's position: StrykerJS is "not a dependency," and building a general AST mutation engine inside `e2e-skills` would duplicate it and is out of scope. The only open question is narrower: does a general-purpose mutation tool (Stryker) catch any causally valid, behaviorally distinct fault that this repo's own targeted V2/V3 fault injection misses, at reasonable cost — not whether raw mutation score is a quality metric (it isn't; `Raw mutation score is not product quality` per the decision matrix this item was scoped from).

## If ever run: scope (feasibility only, one arm)

- Only the `stryker_serial` arm from the original external-adapter plan. The `external_gate` (`playwright-mutation-gate`) and `native_kernel` arms are excluded from this decision entirely, not deferred — they would need their own separate preregistration if ever proposed.
- Target: one repo fixture app whose 12 fault operators already serve as a frozen oracle of "behaviorally relevant fault" (`benchmarks/fixture-faults/`), optionally a second fresh small app.
- No model calls. Local CPU only, disposable Stryker install (never added to any target's own dependencies).
- Unfaulted native run must be stable across 3 repetitions before any mutation run starts (abort if not). The V3 fault manifest is frozen and hashed *before* looking at any Stryker output, never after. Dry-run first, then `concurrency: 1`, no incremental mode. No-op-copy, positive-control, and irrelevant-fault-control cells all required. Source fingerprint identical before/after. Process exit alone is never counted as a kill — the failure must reach the primary assertion.
- Verdict: `optional adapter` only if, on both apps, within a preregistered budget, Stryker finds at least one causally valid, behaviorally distinct survivor/kill not already in the frozen V3 manifest. Otherwise `REFERENCE_ONLY`. An invalid/infra-failure rate over a preregistered threshold is an automatic `REJECT`, not a smaller sample.

## What this is not

Preregistered, but not frozen: no runner, no cost ceiling committed (the wall-time/CPU ceiling is `TBD` at freeze — unlike item 1/3/6, Stryker's real per-mutant runtime on this fixture app has never been measured), no target selection finalized, no freeze record. This protocol pins zero `skills/*/SKILL.md`, `playwright-agents.md`, `pattern-reference.md`, `agents/*.md`, or `.codex/agents/*.toml` files — it makes no model call and invokes no generator/reviewer/debugger/healer/planner arm anywhere in its design, so it does not compete with `healer-perturbation-v1` or `subagent-routing-v1` for the same pinned surface. If this item is ever authorized to move past `design_only`, it gets the same freeze treatment as `benchmarks/ours-vs-planner-pilot-v1/`, `benchmarks/subagent-routing-v1/`, and `benchmarks/healer-perturbation-v1/` at that time, not now. Given the low expected value already established, that authorization should not be assumed to come soon.
