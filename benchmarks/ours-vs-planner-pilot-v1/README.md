# ours_only vs planner_plus_ours pilot v1

**Status: `DECIDED` — `CONDITIONAL` (2026-09-12). All 36 measured cells plus 4 smoke cells ran to completion; the mechanically computed preliminary label was adjudicated by a human pass over target A's `planner-delta.md` files. See [`adjudication.md`](adjudication.md) for the full reasoning and the future re-test triggers. No product text changes: the Planner step stays optional, not default.**

The machine-readable contract is [`protocol.json`](protocol.json). If this README and that file differ, the JSON controls. The per-cell exploration log contract is [`exploration-evidence.schema.json`](exploration-evidence.schema.json).

## What is being tested

Whether the first-party Playwright **Planner**, used as an auxiliary plan hardener in front of `playwright-test-generator`, earns a `DEFAULT` policy or stays at the current `CONDITIONAL` policy already written into `skills/playwright-test-generator/playwright-agents.md`.

This is hypothesis A1 from the external-adapter plan, and only A1. The official Generator (A2, dual-candidate) and Healer (A3, perturbation set) keep their own independent gates and are not touched by this pilot; a Planner win admits neither of them, and a bundled `official_loop` observation can admit nothing.

Two arms, byte-identical frozen scenarios:

| Arm | Flow |
| --- | --- |
| `ours_only` | approved scenario -> `playwright-test-generator` -> `e2e-reviewer` -> V1-V6 -> native run |
| `planner_plus_ours` | fresh worktree -> `npx --no-install playwright init-agents --loop=claude` (setup, hashed, unscored) -> Planner plan deltas -> approval reconciliation (observed vs inferred split per `playwright-agents.md`) -> our generator -> `e2e-reviewer` -> V1-V6 -> native run |

Initialization is setup cost, never quality lift. A missing `init-agents` command, a delegated planner that cannot see `planner_setup_page` / `planner_save_plan`, or a browser that will not launch in the host is `UNAVAILABLE` for that cell. It is never an application failure and never a reason to upgrade the target.

## Why

The 2026-09-04 feasibility chain proved the Planner -> our generator -> reviewer -> V1-V6 -> native-run path completes on a demo application. That is feasibility on a vendor demo, not a policy result. The decision matrix put the official Planner at P2 with `CONDITIONAL` as the starting policy and required a matched `ours_only` vs `planner_plus_ours` comparison on fresh projects before anything moves. This package is that comparison, preregistered before any scenario is explored.

## Frozen design

- **Targets:** two `prospective_fresh` projects selected by a recorded read-only search (see `freshness_exclusion_search` in the JSON):
  - **A** `eilinwis/playwright-chat-lab` @ `7f2e2650af1c2b3775e6d4592d5507a4ac46ea1b` (Vite SPA, deterministic offline mode, `@playwright/test ^1.58.2`).
  - **B** `andymai/gridfinity-layout-tool` @ `8902951e70f0e6e90e04780bb685faf837bc12bf` (client-side Vite app, `@playwright/test ^1.61.0`, AGPL-3.0; cloud features are opt-in and excluded).
  - Alternate **C** `CiroMirkin/Capo` @ `e7deb2d85d5760113ad65be99028fc6b59a61227`, usable only after a human confirms it starts with no database.
  - Apache Zeppelin is excluded: development-contaminated and pinned to Playwright 1.55.1, where `init-agents` does not exist and upgrading is forbidden.
- **Scenarios:** three per target, one of which is an impossible-scenario honesty control. Scenario text is proposed in the JSON and is frozen byte-for-byte at freeze after a human confirms reachability (satisfiable) or absence (impossible) at the pinned SHA.
- **Schedule:** 2 targets x 3 scenarios x 2 arms x 3 repetitions = **36 measured generation cells**, plus **4 unscored smoke cells** (one per target per arm, on a seventh scenario that is never scored). Serial, one machine-heavy slot, fresh worktree and browser profile per cell, arm order rotated per repetition.
- **Host:** Claude only, `--loop=claude`, model `claude-opus-5` unless changed before freeze; `version_policy: minimum` for the Claude Code build.
- **Analysis unit:** the scenario. Three repetitions measure stability (2-of-3 majority-stable) and never enlarge the denominator.

## Decision rule (frozen)

`DEFAULT` requires **all** of:

1. on **both** targets, `planner_plus_ours` has a strictly higher majority-stable Complete rate than `ours_only` on the satisfiable scenarios, **or** contributes at least one independently verified new failure condition (reviewer-confirmed and V2/V3-proved load-bearing) on that target;
2. **zero** false greens by `planner_plus_ours` on the impossible scenarios;
3. zero semantic weakening or safety breaches;
4. zero `UNAVAILABLE` planner cells and zero unstable scenarios for `planner_plus_ours`;
5. actual spend within the ceiling below.

Anything else is `CONDITIONAL`, which is the current product default, so no product text changes. `REJECT` (meaning: do not integrate as a default) is recorded if the planner arm produces any false green, is `UNAVAILABLE` on every planner cell, or is worse on both targets with no verified new failure condition. A single target cannot rescue the other. No threshold changes after any result is seen; there is no optional stopping.

## Result (2026-09-12)

**`CONDITIONAL`.** Target B (`andymai/gridfinity-layout-tool`) showed a real majority-stable complete-rate lift for `planner_plus_ours`. Target A (`eilinwis/playwright-chat-lab`) showed none, and the "independently verified new failure condition" escape clause does not rescue it: the planner's absorbed deltas on target A were real and correctly load-bearing within their own sessions, but `ours_only`'s own repetitions reached at least as good a majority-stable outcome on both `A-S1` and `A-S2` without a planner step (tied on `A-S1`, and — after a post-freeze scoring correction, see `pilot-results.json`'s `known_scoring_corrections` and `adjudication.md` — actually ahead on `A-S2`), so there is no evidence `ours_only` structurally misses what the planner catches. "A single target cannot rescue the other," so the overall result is `CONDITIONAL`, not `DEFAULT`. Zero false greens on either arm, so `REJECT` does not apply either — `REJECT` requires the planner arm to be worse on **both** targets, and target B's genuine lift rules that out regardless of the target A correction. Full per-cell reasoning: [`adjudication.md`](adjudication.md). Cost: 46 total top-level sessions, 17.3 serial hours, $276.38 nominal (subscription-billed; not a real dollar cost). No change to `skills/playwright-test-generator/playwright-agents.md` or any other product text — the Planner step remains optional, not default.

## Cost ceiling and what happens near it

The operator set no hard ceiling. Rather than treat that as unbounded, the protocol fixes an auditable default:

- **Naive estimate** (an assumption, not a measurement; the feasibility chain recorded no timings): `ours_only` ~3 top-level agent sessions / 20 min per cell, `planner_plus_ours` ~4 sessions / 30 min per cell; with 36 measured and 4 smoke cells that is **~140 sessions and ~16 serial hours**.
- **Multiplier 4x.** 3x absorbs repetition variance plus one infrastructure-only retry per cell; the extra 1x covers the planner arm's live-exploration length, which was never timed. 5x was rejected as indistinguishable from unbounded for a 36-cell pilot.
- **Hard ceiling: 560 sessions / 64 serial hours**, per-cell caps of 45 min (`ours_only`) and 60 min (`planner_plus_ours`).
- **Confirmation checkpoint at 2x (280 sessions / 32 hours): the runner pauses and asks.** At the hard ceiling it pauses and asks again. Declining ends the run `INCOMPLETE` with every completed cell preserved. Authorizing continuation lets the run finish, but the report is labeled `CEILING_EXCEEDED_WITH_AUTHORIZATION` and condition 5 above is false, so `DEFAULT` becomes unreachable while the other outcomes remain available. Silent continuation and silent abort are both forbidden.
- Monetary cost is not observable on a subscription-billed host; the ledger records it as `unknown` rather than estimating it.

## Exploration evidence logging (roadmap item 5)

Every cell writes one `exploration-evidence.json` validated against the schema in this directory. It lists every role/name/state claim the arm relied on with `observed` / `inferred` / `unknown` provenance, whether the claim reached the final test, and whether it matches the human-frozen accessibility oracle captured at freeze. Scored fields: observed/inferred/unknown counts, `inferred_locators_used_in_final_test` (expected 0), observed-claim calibration against the oracle, required states reached, off-origin attempts (expected 0), and stalls. This is the Experiment C metric set, collected here at zero extra cost; it does not change the decision rule.

Candidate future arms for roadmap item 5 (recorded-trace exploration, adapter-by-adapter measurement) are tracked in `benchmarks/exploration-fallback-v1/README.md`, not here — this file stays scoped to the item 1 pilot itself.

## Dependencies and sequencing

Before freeze: fresh `ci-local.sh` and `pre-push-security.sh` green on the evaluated tree; freshness recheck of A and B recorded; scenario reachability/absence confirmed; accessibility oracles captured; the four smoke cells passed; operator confirmation of model, Claude Code build, and the ceiling. Independent of `benchmarks/subagent-routing-v1` (separate snapshot label; scores are never pooled) and of the reviewer release lane. Only a planner-arm lift unlocks the A2 dual-candidate (paired with `ours_repeat_control`) and A3 healer stages.

## Open items marked in the JSON

- `NEEDS_HUMAN`: Claude Code build to record at freeze; target A's missing LICENSE file (README says MIT); alternate C's no-database start.
- Scenario text is `proposed_pending_freeze_verification`; it is not `TBD`, but it is not frozen until a human confirms it against the pinned SHA.

## What this cannot claim

Two projects are a feasibility/adoption screen. Nothing here supports a README or CHANGELOG claim, a generator accuracy number, or any statement about the official Generator or Healer.
