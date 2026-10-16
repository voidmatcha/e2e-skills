# Generator component ablation v2 (repaired): Codex preregistration

Status: **BUILT OFFLINE, NOT FROZEN, NOT RUN.** No model call, container, server, dependency installation, network operation or freeze was performed by this repair. The study is meant to run after the Codex weekly window resets (2026-10-20 22:00 KST), starting with the small first stage in [Budget](#budget-and-recommended-first-stage).

This repair answers two questions that the first build could not: **which components of the generator skill carry the benefit**, and **where the tokens (and, with owner-supplied rates, dollars) go**. The second is now a named deliverable that does not depend on the quality gate.

## What changed in the repair

| Finding | Change |
|---|---|
| AB-1 cost not per component | New ungated **core tier** (`0`, `0b`) holds `full`, `minus-R`, `minus-V6`, `minus-V` and `thin`. Per-cell tokens are split by rollout role (root, V6 reviewer child, other children); paired per-task cost contrasts use the same exact sign-flip machinery; incomplete-token cells are counted and bound the label both ways instead of being dropped. |
| AB-2 lock misses live drivers | Every live command holds the machine-wide `CampaignLock` (shared lock file plus a probe for any `run-generator-*.py` driver) and the v4 multimodel lock. |
| AB-3 model rule | The model follows the stated rule (`gpt-6-sol`) unless the owner records an explicit override before freeze; the claim is worded quality-blind and process-fidelity-informed; the v3 admission of the chosen model is a precondition of every model-calling command. |
| AB-4 wrong harness, no exposure check | Ablation-specific harness check and a preflight that asserts expected exposure per condition. The runner now imports the v4 evidence module, which rejects a contradicting root thread. |
| AB-5 blind primary, V bundle | Effective fault kill and clean 3/3 are co-primary endpoints for C4, C8, C9 and C10; a `minus-V6` arm separates the cheap half of V (execution) from the expensive half (the reviewer child). |
| AB-6 gate can silently never open | Per-component exposure with a disclosed partial label; tasks with no clean cell are dropped from both sides (at least 10 tasks stay); the tier 2 gate is a reported status with reasons and a recorded owner override; the none-arm prompt no longer mentions a skill. |
| AB-7 exit codes, stale flag | A scanner run that exits 1 on P0 hits and a failing first Playwright run now count; the stale `validated_against_transcripts` flag is gone and a revalidation is a freeze precondition. |
| AB-8 power | Read against the .25 threshold below. |
| AB-9 thin layer | New `thin` condition: the 11-line THIN-RULES checklist staged as the only skill. |

## Selection before outcomes

**Claim: quality-blind and process-fidelity-informed. It is NOT outcome-blind**: the rule reads delivery and process-fidelity counts of the first Codex v2 attempt (arm C only), which are outcomes of an earlier campaign. No survivor, fault or score value is used.

The stated rule: among models with a completed 24-call arm-C panel in `multimodel-v2-codex-attempt1-armA-invalid`, choose the highest count of cells with complete-process fidelity (executed tests plus a returned independent V6 verdict line), break ties by delivered cells, then by model ID. The stored replay is Sol 22/24 versus Luna 16/24 for that count and 24/24 versus 23/24 delivered, so `rule_outcome` is **`gpt-6-sol`**, and the runner recomputes it from the stored replay (a tampered `rule_outcome` is refused). The earlier supplied rationale (Luna delivered 23/24 with all key steps) is not verified and is contradicted by that replay; the earlier fixed Luna target is recorded as superseded, with the reason.

**Owner decision, 2026-10-15.** The owner delegated the model choice to the stated rule: the default stays `gpt-6-sol`, there is no `gpt-6-luna` override, and `owner_choice` stays null. The v3 admission of the model remains a precondition (below). The dollar rates stay unfilled (never guessed) and the 16 extra preflight cells are kept.

To run another model the owner sets `model` and fills `model_selection.owner_choice` (model, UTC time, statement) in the same edit before freeze; a model other than the rule outcome without a complete record makes the protocol invalid. **Commit the protocol and this README before freeze** so the choice has a timestamp before any data exists.

**Precondition:** before `harness-check`, `preflight` or `drive`, the chosen model must have an admitted entry in the Codex v3 campaign (`_entry/<model>.json` under the v3 campaign directory, bound to the current v3 freeze, with working-child shell and mutating-MCP criteria). The runner reads only that one file, fails closed, and records its digest in the harness check, the preflight decision and every report. Scoring does not call the model and does not require it.

The twelve tasks are copied from the old design: `v2-06`, `v2-12`, `v2-13`, `v2-20`, `v2-22`, `v3-03`, `v3-04`, `v3-06`, `v3-07`, `v3-08`, `v3-09`, `v3-10`. Their old floor/middle/ceiling labels came from a gpt-5.5 screen that cannot be repeated; they govern neither eligibility, weights nor inference. This is a historically selected development panel, not a random sample of applications.

## Conditions, tiers and views

Components: L explicit locator rules; E live exploration; P design reference; R author-side scanner gate (Step 6); V execution verification **and** the independent review (Step 7); **VR** the independent V6 reviewer child alone (new, inside V).

| Condition | Meaning |
|---|---|
| `full` | shipped skill, byte-identical to the base tree |
| `minus-L`, `minus-E`, `minus-P`, `minus-R`, `minus-V` | historical leave-one-out variants (byte-identical overlays) |
| `minus-EPRV`, `minus-LEPRV` | process removed, with and without the locator rules |
| `none` | no skill; frame and plan line only |
| `minus-V6` (new) | Step 7 keeps the baseline run, tracer and V1-V5; the V6 reviewer, its packet, verdict line and the V4 independent audit are removed (34 text operations, each with an expected-change record that the tests check against an independent line diff); the Step 6 scanner stays and its Phase 2 sentence is replaced by a scanner-only statement |
| `thin` (new) | the THIN-RULES checklist staged at `skill/playwright-thin-rules/SKILL.md`, no process text, no reviewer. Not the thin-eval arm D (official MCP generator plus rules); it bounds what the rules carry alone |

| Tier | Conditions | Repetitions | Calls | Role |
|---|---|---|---:|---|
| `0` | full, minus-R, minus-V6, minus-V, thin | 1 | 60 | **first stage**: component cost and exposure, ungated |
| `0b` | same | 2 to 4 | 180 | extension of the same schedule to four repetitions, ungated |
| `1` | full, minus-L, minus-EPRV, minus-LEPRV, none | 1 to 4 | 240 | historical quality tier (C1-C5) |
| `2` | full, minus-E, minus-P | 1 to 4 | 144 | exploration and design leave-outs; gate reported, owner override recorded |

Tiers `0` and `0b` split one seeded schedule, so tier `0` is an exact prefix of the four-repetition core matrix. Views group tiers for analysis: `0` (descriptive, one repetition), `0+0b` (four repetitions), `1`, `2`. R and V are no longer gated behind C1: the new design measures their cost in tier `0` whatever the quality tier shows. E and P cost is read in tier `2`.

The overlays, deleted-file lists, tree hashes and twelve plans for the historical conditions are byte-for-byte copies of the repaired historical design (reference generator tree SHA-256 `acc407688513f973ea647260effc996e038108b877c18aeb5a6f24960b10cb22`); the helpers are preserved in [reference](reference/protocol.json) and pinned in [protocol.json](protocol.json). Prompt clauses of the historical conditions are reused exactly. The skill-specific scratch approval is appended only where a skill tree is staged; `none` and `thin` carry a scratch-only sentence that names no skill and no exploration or guard config, because there is no skill text for it to refer to. The minus-V6 prompt names the reviewer skill only for its bundled scanner.

## Manipulation, exposure and detectors

Signals: L and P need their characteristic text in a successful read output; E an executed exploration command; R an executed author-side scanner (a scanner inside a V6 child is not R); X an executed Playwright test command; **V6** a literal `V6 VERDICT:` line in a linked child rollout's final message or the parent collaboration state; V is X **and** V6. Evidence comes from full, untruncated commands and outputs in the parent and the linked rollouts read by the v4 evidence module. A rollout whose lineage is contradicted by the transcript root identity, or that is not linked to the identified root, is not evidence: the cell has no signals and counts against coverage.

**Exit-code rule.** A command counts when it ran to completion with an accepted exit code: L, E, P need 0; R and X accept 0 or 1 (the scanner exits 1 on P0 hits, which is the useful run for R; a first failing Playwright run is still an executed test). Exit 2 or more, a missing exit code and unobserved commands never count.

**Per-component exposure.** For every named component a contrast reports reference and ablated shares and a status: EXERCISED (reference share at least 50%, ablated at most 15%, transcript coverage at least 90%), NOT_EXERCISED, NO_EVIDENCE or DETECTOR_FAILS_BOUNDS. A `kept` component (C10 keeps X) must stay in the ablated arm. Exposure is *complete*, *partial* or *none*. **None** gives NOT_EXERCISED. **Partial** keeps CARRIES and ABLATION_BETTER, attributed to the exercised subset, and turns NO_LARGE_EFFECT and GUARD_WORSE into INCONCLUSIVE, because a null cannot be attributed when part of the manipulation did not happen.

**Detector validation.** Historical validation (precision and recall at least .90 on at least ten positives, Codex cells, tuned in-sample) covers the L, E, P and R command and read rules only. The V rule, the V6 rule, X and the exit-code rule are **not validated**; results list them as `unvalidated_detectors`. The stale `validated_against_transcripts` flag is removed. **Freeze is refused** until `revalidate --cells-dir <finished cells> --out <external file>` has been run offline on allowed finished Codex rollouts, the output reviewed and committed as `manipulation-revalidation.json` with `reviewed: true`, and the protocol's `revalidation.status` set to `RECORDED`.

Build-time dry run (read-only, process facts only, no score or survivor value read, nothing recorded): the detectors and role split were run over the 25 finished gpt-6-sol cells of the live Codex v3 campaign at that time. In its 15 arm-C cells L, E, P and R appeared in 15 and a V6 verdict in a linked child rollout in 13 (never only in the parent state); X appeared in all 25; the role split reconciled with the pipeline token total in 25 of 25; the V6 reviewer children held 27 to 60 percent of processed tokens in the 13 cells that had one. This checks the parser on the real rollout format; it is not the revalidation and does not enter any decision.

## Metrics and decision rule

Unit: **twelve paired task means**, with the scheduled repetitions inside each task. Endpoints (all reference minus ablated):

| Endpoint | Task value |
|---|---|
| survival | mean refactor score over clean cells (clean-conditional) |
| effective fault kill | mean over all cells, 0 when not clean (ITT) |
| clean 3/3 | mean over all cells of the indicator (ITT) |

C4, C8, C9 and C10 are **co-primary on all three endpoints**; C12 (thin rules versus the full skill) reports the three endpoints descriptively, and every other contrast reports survival only. Alpha is `.05/3` two-sided for survival of C1, C2 and C4 and for every endpoint of the co-primary contrasts; everything else is descriptive at `.05`. The effect threshold is .25. A contrast with several endpoints is CARRIES when any listed endpoint is, otherwise ABLATION_BETTER, otherwise NO_LARGE_EFFECT only if every endpoint is and the guards hold (clean drop at most .05, effective fault-kill drop at most .10, no extra scanner P0), otherwise INCONCLUSIVE. Per-endpoint labels are always reported. NO_LARGE_EFFECT does not prove equivalence, and exact p-values assume joint coordinate-wise sign invariance, which correlated task shocks can break.

A task with no value on either side is dropped from **both** sides and listed; a contrast stands with at least ten usable tasks and shows ITT survival beside it, instead of failing on one task. A view with fewer than four repetitions per cell (view `0`) is graded *descriptive*: labels are computed by the same rule but are not powered.

**Tier 2 gate (reported, never silent).** Tier 1 analysis stores `OPEN` when tier 1 is complete and C1, C2 or C4 is CARRIES with at least one exercised component; otherwise `CLOSED_INCOMPLETE`, `CLOSED_NOT_EXERCISED` (with per-component statuses) or `CLOSED_NO_CARRIES`, each with reasons. `drive --tier 2` recomputes it from digest-bound reports and stops on a closed gate unless `--owner-ungated "<reason>"` is given; the reason is recorded in the report and the analysis. The cost reading never depends on it.

## Cost deliverable: where the tokens go

Computed in every view, independent of any quality label:

- **Tokens by role** per arm: root, V6 reviewer child (a linked child whose persisted final message carries a literal verdict line), other children, each split into uncached input, cached input, output, processed (uncached plus output) and total; shares of processed tokens; cells with a V6 child; cells with incomplete records. Roles reconcile with the cell's pipeline token total or the cell is flagged.
- **Paired per-task cost contrasts** for every contrast of the family, for processed tokens, total tokens and pipeline seconds: `ln(mean reference / mean ablated)` over the task's complete cells. Labels: COMPONENT_COSTS (geometric mean ratio at least 1.2 and exact sign-flip p at most .05), COMPONENT_SAVES (mirror), NO_LARGE_COST_EFFECT (one-sided 95% upper bound below ln 1.2 and mean above -ln 1.2), INCONCLUSIVE. Descriptive alpha, no multiplicity claim.
- **Incomplete cells are bounded, not dropped.** The primary uses complete cells; the label is recomputed with incomplete cells at their partial known value (lower) and at the arm's largest complete cell (upper, a stated assumption). `label_bounded` says whether the three agree, and incomplete counts are shown per arm and metric.
- **Dollars.** Subscription billing has no dollar figure. If the owner fills `cost_deliverable.dollars.rates_per_million_tokens` (uncached input, cached input, output) before freeze, the analysis adds an API-equivalent estimate per role; otherwise only token shares appear. Rates are never guessed.
- Per-arm survivors per 100k processed tokens and seconds per survivor remain as secondary views.

## Offline power

Seed `20261017`, 4,000 datasets per scenario, twelve tasks, four independent Bernoulli repetitions per side, full-arm baseline .90, all cells delivered and clean, the same .25 threshold and `.05/3` two-sided test; heterogeneous sensitivity draws each task baseline uniformly from .75 to .95. No campaign outcome informs these assumptions.

| True drop | Homogeneous power | Heterogeneous power |
|---:|---:|---:|
| .15 | .087 | .088 |
| .25 | .422 | .384 |
| .30 | .620 | .579 |
| .35 | .782 | .750 |
| .40 | .888 | .864 |

The 80% minimum detectable effect on the .05 grid is **.40**. The CARRIES bar is .25, which is detected only about 42% of the time, so **true effects between .25 and .40 are expected to come back INCONCLUSIVE, not NO_LARGE_EFFECT**. The table covers survival at four repetitions; fault kill, clean 3/3 and the cost contrasts are not separately powered. Cost differences are better powered only if between-cell variance is small, which the first stage measures; a true full-versus-none drop is also bounded by the none arm's own level. `power` reproduces the simulation offline.

## Budget and recommended first stage

Estimated Codex weekly-limit points at **about 0.37 points per cell** (owner-supplied rate, measured on other cells and models; re-measure after the first stage). The window resets 2026-10-20 22:00 KST at 100 points. `budget` prints this table from the protocol.

| Unit | Calls | Estimated points | Cumulative calls | Cumulative points |
|---|---:|---:|---:|---:|
| harness-check | 1 | 0.4 | 1 | 0.4 |
| preflight (non-data: 6 full, 10 other conditions) | 16 | 5.9 | 17 | 6.3 |
| tier 0 (5 arms x 12 tasks x 1 repetition) | 60 | 22.2 | 77 | 28.5 |
| tier 0b (repetitions 2 to 4) | 180 | 66.6 | 257 | 95.1 |
| tier 1 (5 arms x 12 tasks x 4) | 240 | 88.8 | 497 | 183.9 |
| tier 2 (3 arms x 12 tasks x 4) | 144 | 53.3 | 641 | 237.2 |

**Recommended minimal first stage.** (0) harness-check plus preflight only, 17 calls, about 6 points: validates exposure, lineage, token additivity and role accounting before any data call. (1) Add tier `0`, 60 calls, about 22 points (about 28.5 in total): the first where-do-the-tokens-go reading, with cost and exposure for R, V, V6 and the thin rules. Extend with tier `0b` only if the stage-1 role shares and paired ratios are stable enough to justify four repetitions; run tiers `1` and `2` in later windows. The whole program is about 2.4 windows.

## Commands and operational gate

```bash
python3 -B scripts/evals/run-generator-ablation-v2.py plan
python3 -B scripts/evals/run-generator-ablation-v2.py check
python3 -B scripts/evals/run-generator-ablation-v2.py power
python3 -B scripts/evals/run-generator-ablation-v2.py budget
python3 -B scripts/ci/test-generator-ablation-v2.py
```

These are offline. **Do not freeze as part of this build.** After the model choice, revalidation and imported-source repairs are reviewed and committed, the owner may invoke `freeze`; it writes once and binds the imported machinery (v4 runner, adapter, evidence and pooled modules, machine-wide lock module), the stats helper, historical assets, prompts, the harness line, the model choice and the revalidation artifact. There is no smoke bypass.

Future live order: `freeze`, `harness-check --allow-live`, `preflight --allow-live`, `drive --tier 0 --allow-live`, `score --tier 0 --allow-live`, offline `analyze --view 0`, then the later tiers. Every command accepts `--output <external-campaign-directory>`; never point it at the first attempt or another study. Model-calling commands accept `--v3-dir`. `summary` reads and recomputes digest-bound analyses. Scoring writes a STARTED/COMPLETE/FAILED state; analysis requires the latest complete state bound to the exact score bytes. `score` starts browser scoring and therefore also needs explicit live authorization and a freeze.

**Harness check (ablation-specific).** One call under the ablation sandbox (`danger-full-access`, no MCP): the parent spawns one child that runs a shell command and replies with a literal `V6 VERDICT: PASS` line. It passes only if the call succeeded, sessions and the root rollout persisted, the census is clean, a child rollout exists, spawns resolve to rollouts, the child's shell output and verdict line are in its persisted rollout, child usage is present, and the root rollout is a separate account from the child rollouts (the parent stream total equals the root total, or root plus child). It replaces the inherited official-arm check, which tested a configuration no ablation condition uses.

**Preflight (non-data, task `v2-01`).** The full condition six times and every other condition once (16 calls). Hard assertions: every cell deliverable with complete evidence and reconciling role tokens; L, P, E, R, V6 and X each appear in at least 4 of the 6 full cells; L and P never appear in a condition whose text for them is gone. The rest of the per-condition expected-exposure table is reported, not enforced (E may appear in `none` through the shared frame). The decision is bound to the freeze, the harness check and the v3 admission digest, and `drive` refuses without it.

**One campaign at a time.** Every live command holds the machine-wide `CampaignLock` (a shared lock file plus a probe for any `run-generator-*.py` drive, run, preflight, score, smoke, harness-check, final-eval or calibrate process, so a running v3, v4, thin-eval, oss, loop or claude driver blocks the ablation) and the v4 multimodel lock. The reverse holds only for drivers that use the same machine-wide lock (thin-eval, oss): the v3 and v4 drivers do not, so **no other driver may be started while an ablation command runs**. The ablation uses ports 6300 (generation), 6700 (harness and preflight) and 5300 (scoring) without the +3000 offset of the v3 and v4 drivers; exclusivity makes that safe. A stale lock file after a crash is refused, not stolen: remove it by hand after checking that no driver runs. Resume preserves completed rows and every attempt; CLI or image drift, or a recorded infrastructure failure, refuses resume instead of silently replacing evidence.

## Limits and remaining live checks

The components overlap: P removal also deletes three locator rules, leaving thirty in minus-EPRV; R can be enforced by V; the thin condition is not the thin-eval arm. Removal also changes skill length and attention. One model, twelve historical tasks and one fixture family cannot establish broad application performance, and the ablation does not say whether the thin layer retains the benefit on the official MCP generator (use the thin-eval arms for that).

Unverified: that the chosen model is admitted by the v3 campaign (a precondition, not yet true or false here); the detector revalidation (pending); accepted current container and CLI identity; actual exposure and manipulation in the ablated conditions, particularly E in `none`; child persistence, lineage and additive tokens under the ablation sandbox (the dry run saw them in v3 arm-C rollouts only); guard-file approvals; successful generation server reuse; clean host-side scoring and end-to-end score, analyze and summary recovery on real data. Synthetic tests and the read-only dry run do not settle these. No live call, browser scoring, freeze or empirical ablation result exists for v2.
