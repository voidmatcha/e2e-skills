# Subagent routing v1

**Status: `COMPLETE` / protocol revision 4 Codex inline measured run finished. Revision 3 completed the 96-cell Claude run. Codex feasibility evidence passed `codex.inline` but showed zero real delegation events for `codex.named` and `codex.native-role`. Those two arms remain in the report as 96 zero-cost `UNAVAILABLE` cells; all 48 `codex.inline` cells ran once. The missing arms make the Codex host result `INCONCLUSIVE`. Production routing is unchanged.**

The machine-readable contract is [`protocol.json`](protocol.json). If this README and that file differ, the JSON controls.

## What is being tested

Whether `e2e-reviewer`, `playwright-debugger`, and `cypress-debugger` should delegate one finding verification or one failure classification to the repository's read-only subagents (`e2e-finding-verifier`, `e2e-failure-classifier`), or answer inline through the fallback procedure every host already carries. Two independent production questions, decided separately per host and per task:

1. Does `e2e-finding-verifier` improve refute-first adjudication of one `e2e-reviewer` candidate finding (`CONFIRMED` / `FALSE-POSITIVE` / `NEEDS-CONTEXT`)?
2. Does `e2e-failure-classifier` improve classification of one Playwright or Cypress failure into the frozen F1-F15 taxonomy (including `CANNOT_VERIFY` between two named codes)?

The inline fallback is **not a candidate for removal** under any outcome. Per `AGENTS.md`, the named agents are discovered only on a Claude Code plugin install or a Codex `~/.codex/agents/` registration, so the inline path is load-bearing on every host. This benchmark can only change *when* delegation is preferred, expressed as wording in the three delegation blocks.

Generator V6 fresh-context review is out of scope: it is an independence requirement, not a cost optimization.

## Arms

| Arm | Host | Status | Definition |
| --- | --- | --- | --- |
| `claude.inline` | Claude Code | active | parent runs the frozen procedure itself |
| `claude.named` | Claude Code | active | parent delegates one case to the installed named agent |
| `codex.inline` | Codex | active; smoke `PASS` | parent runs the frozen procedure itself |
| `codex.named` | Codex | `UNAVAILABLE` by smoke evidence | retained as a zero-cost schedule cell; no model process is launched |
| `codex.native-role` | Codex | `UNAVAILABLE` by smoke evidence | retained as a zero-cost schedule cell; no model process is launched |

All arms receive byte-identical case material, the same absolute path to the frozen source-of-truth contract, and must return the same compact output schema. The deterministic scanner is not an arm.

### The activated Codex arm

The Codex arms were activated on 2026-09-13 by the separate `codex-arm-activation.json` record. Revision 4 adds an explicit `delegation_unavailable_arms` reduction to that record after the live smoke proved this Codex CLI environment has no functioning mid-session delegation event analogous to Claude Code's Agent tool. The harness keeps all 144 Codex cells visible, materializes 96 delegation cells as `UNAVAILABLE` with zero requests/cost, and launches only the 48 inline cells. This is a disclosed missing-arm result, not a silent skip.

## Stage 4 amendments, incorporated

- **(a) Request accounting.** "240" is the full-matrix count of *strategy executions*, not model calls. Every cell logs actual requests, tokens, elapsed time, and visible cost separately for the parent and each child; unobservable child telemetry is `null`, never estimated.
- **(b) Native-role attestation.** A `codex.native-role` cell whose harness cannot prove which role ran records `UNAVAILABLE`; silent substitution voids the arm.
- **(c) Smoke gate.** Every executable arm must pass. An activation-declared structurally unavailable delegation arm remains visible as a zero-cost `UNAVAILABLE` cell and launches no process. Any runner change after smoke requires a new protocol version and a fresh smoke of the executable arms.
- **(d) Freshness search recorded.** See below and `freshness_exclusion_search` in the JSON; it is rerun at freeze.

## Frozen case set (16 slots)

Eight finding-verification and eight failure-classification cases in disposable, self-contained repositories with no secrets, network, model instructions, or mutable third-party state:

| Slot | Task | Stratum | Framework | Expected |
| --- | --- | --- | --- | --- |
| FV-01 / FV-02 | finding verification | clear | PW `#8` / CY `#9` | `CONFIRMED` |
| FV-03 / FV-04 | finding verification | clear, documented exclusion | PW `#4` / CY `#14` | `FALSE-POSITIVE` |
| FV-05 / FV-06 | finding verification | cross-file / config-dependent | PW `#12` / CY `#20` | `CONFIRMED` |
| FV-07 / FV-08 | finding verification | cross-file / config-dependent | PW `#12` / CY `#3b` | `FALSE-POSITIVE` |
| FC-01 / FC-02 | failure classification | clear single code | PW / CY | `F2` / `F3` |
| FC-03 / FC-04 | failure classification | shared setup / config-dependent | PW / CY | `F9` / `F8` |
| FC-05 / FC-06 | failure classification | two codes plausible until evidence | PW / CY | `F6` / `F13` |
| FC-07 / FC-08 | failure classification | F1 vs F7 | PW (probe supplied) / CY (no probe) | `F7` / `CANNOT_VERIFY` |

Each slot predeclares the accepted verdict, decisive evidence, allowed confidence, required limitation, forbidden weakened fix, and whether a concrete fix is legal. The case bytes were authored only after the harness design was approved and remain unexecuted and unfrozen pending case review and the feasibility smoke gate.

### Freshness-exclusion search

Pattern IDs and F-codes are closed vocabularies (24 and 15 entries) and cannot be the freshness unit; every pattern already appears somewhere in the public corpora. Freshness here means no source-byte duplicate and no scenario or defect-lineage duplicate. The inventories dumped and compared on 2026-09-11, with the domain search rerun against the current tree on 2026-09-12: `reviewer-holdout-v3.json` (8 cases: receipts, admin billing, settings, invoices, search, profile/board, catalog), `reviewer-holdout-v5.json` (20), `reviewer-fault-causal-v3.json` (24), `debugger-holdout-v1.json` (30), the four skills' `evals/evals.json` and fixture files (auth, dashboard, checkout, products, notebook, session state, optimistic UI, and others), the output-discipline v1 pilot (jobs-and-reports domain) and v2 pilot (garden plots / compost / harvest domain), and the worked examples in `pattern-reference.md`, the SKILL.md files, `docs/`, and `CHANGELOG.md`.

The chosen application domain, a **public library branch** (patron holds, reading-room bookings, overdue fines, staff hold queue), returned zero hits for `patron|reading room|book hold|library branch|overdue fine` across `skills/`, `scripts/`, `docs/`, `README.md`, `CHANGELOG.md`, and `benchmarks/` after excluding this protocol directory, whose preregistration and authored cases necessarily name the chosen domain. The search was rerun after case authoring on 2026-09-13. The only `.handover/` hits are three unrelated Spanish i18n substrings inside a vendored `open-mercato` fixture; there are zero case-material hits. The 42 authored repository files also had zero exact-byte collisions against 5,386 files on the checked public repository surfaces and zero within-set duplicate groups. If freshness cannot be re-established at freeze, the run is labeled `development_known_cases` and is not used to choose routing.

## Schedule and budget

- 16 cases x 3 repetitions in fresh sessions and workspaces.
- Claude phase: 96 measured strategy executions + 2 smoke + at most 32 judge calls = **130 strategy executions maximum**.
- Full declared matrix: 240 measured report slots + 5 smoke slots + at most 80 judge calls = the existing **325** cap. Under the revision-4 Codex scope reduction, 96 Codex measured slots and two Codex smoke slots are zero-cost `UNAVAILABLE`; only 48 Codex measured cells and one Codex smoke cell launch a model.
- Claude actual-request ceiling: naive estimate ~1,200 requests (inline ~10 per execution; named ~5 parent + ~10 child), **pause-and-ask at 2x (2,400)**, **hard ceiling at 4x (4,800)**, per-execution turn cap 40 parent / 40 child, 15 minutes per execution, 52 serial hours hard ceiling. Declining at a ceiling ends the run `INCOMPLETE` with raw evidence preserved and unscored; authorizing continuation labels the report `CEILING_EXCEEDED_WITH_AUTHORIZATION`, which makes `ALWAYS_DELEGATE` unreachable for that host. Silent continuation and silent abort are both forbidden.
- Analysis unit: the unique majority-stable case (2-of-3). Repetitions test stability and create no additional defects.

### Claude feasibility smoke

The sacrificial `SMOKE-FV-01` Playwright case is outside the 16 measured slots. The revision 3 runner passed `claude.inline` and `claude.named`: exact oracle match, strict JSON parsing, expected route attestation, unchanged workspaces, clean process-group teardown, no credential material, and every safety field accepted. The named transcript recorded exactly one delegation, while the inline transcript recorded none. This gate used two strategy executions and five observable parent requests over 396.233 seconds. Claude Code reported 8 parent input tokens, 34,510 parent output tokens, and USD 2.47119475 in provider-visible session cost. The named session's USD 2.02922775 is an aggregate that includes its child; unseparable parent and child costs remain `null` rather than being estimated.

Revision 1's three earlier smoke attempts are retained under `smoke-incidents/` rather than hidden: lowercase `confirmed` exposed an under-specified case-sensitive verdict prompt; denied `Read`/`Grep`/`Glob` calls exposed missing read-only tools for the named agent; and the first two-arm pass exposed delegated session cost being recorded as parent-only cost. Its previously accepted final smoke and the later measured heartbeat incident are preserved together under `revision-history/revision-1/`. Each runner defect now has an offline self-test. Child telemetry unavailable from the CLI remains `null`. All USD values are the CLI's nominal observations on a subscription-billed host, not a separate charge claim.

### Codex feasibility smoke

The first activated Codex smoke completed all three arm slots on Codex CLI 0.154.0 with `gpt-5.6-sol`, but the original all-arms gate failed. `codex.inline` passed. `codex.named` had one preserved diagnostic retry: the first attempt's JSONL stream reconnected after an idle timeout and contained no delegation event; the retry logged two `collab spawn failed: no thread with id` errors, returned `delegated: false`, and remained `INCOMPLETE`. `codex.native-role` logged the same spawn failure twice and was recorded `UNAVAILABLE` because no `spawn_agent` event with `agent_type: verifier` could be attested. Across the four executions including the superseded named attempt, Codex reported four parent requests, 312,213 input tokens, 5,082 output tokens, and 742.803 seconds wall time; cost was not exposed. Revision 4 preserves that evidence in `revision-history/revision-3/` and records both delegation arms unavailable.

The final revision-4 smoke report contains all three arm slots but launched only `codex.inline`. It passed with one observable parent request, 30,008 input tokens, 163 output tokens, and 6.91 seconds wall time; cost was not exposed. The named and native-role slots each record zero parent requests, zero child requests, zero cost, and `UNAVAILABLE`. One earlier revision-4 inline pass is preserved under `smoke-incidents/revision-4-pre-activation-freeze-binding/`; it was invalidated when the freeze validator was tightened to bind the activation digest, then rerun under the final runner bytes.

### Codex measured result

The revision-4 report completed all 144 declared slots: `codex.inline` produced 20 `PASS` and 28 `FAIL` cells, while `codex.named` and `codex.native-role` each contributed 48 zero-cost `UNAVAILABLE` cells. Exactly 48 model processes were launched, with 48 observable parent requests, 1,237,610 input tokens, 18,929 output tokens, and 620.705 seconds aggregate cell wall time. Codex exposed no cost. There were no retries, stop events, parse failures, setup failures, or nonterminal cells. The report is intentionally not scoreable and records `INCONCLUSIVE` because two arms are missing; the inline observations remain real per-cell evidence.

**Root cause of the delegation-arm unavailability, independently verified rather than assumed.** The `collab spawn failed: no thread with id: <the session's own thread_id>` error is not this harness's runner invocation and not network flakiness: it reproduces deterministically (2/2 direct reproductions outside the harness) on both Codex CLI 0.153.4 and 0.154.0 (the current latest per `npm view`) using the exact `codex exec --ephemeral ... --enable multi_agent` invocation shape this runner uses. It matches two currently open upstream issues on `openai/codex`: [#41474](https://github.com/openai/codex/issues/41474) and [#33672](https://github.com/openai/codex/issues/33672), plus a related open issue, [#35781](https://github.com/openai/codex/issues/35781), on Collab/MultiAgentV2 thread ownership. #41474's most detailed comment traces the cause to source: an ephemeral session has no persisted `ThreadStore` row by design (`--ephemeral`'s whole contract), but the spawn path unconditionally tries to reconstruct the parent's history from that persisted store rather than from the live in-memory context, so the lookup fails even though the parent thread is genuinely alive. The bug has reproduced from Codex CLI 0.144.5 through current `origin/main`; the 0.153.0 and 0.154.0 release notes contain no related fix, so this is a longstanding upstream limitation, not a regression introduced by the pinned version here. #33672 independently corroborates this benchmark's own finding that the failure is silent to the calling model: the parent turn still completes and the process exits non-error, so a caller that only checks the exit code (or, as observed here, the model's own self-reported `route.delegated` field) will not see the degradation — this is exactly why this protocol's `route_attestation()` checks the raw transcript for an actual delegation event instead of trusting the model's self-report, and exactly the failure mode it was designed to catch. No maintainer-confirmed fix or workaround exists as of this check (2026-09-13); the only partial mitigation on record (moving custom agent definitions from project-scoped to global `~/.codex/agents/`) fixes non-ephemeral mode only and does not apply to `--ephemeral`, which this harness requires for isolation. Re-checking this is a reasonable trigger for re-authorizing the Codex arms in a future protocol revision once upstream resolves it.

## Decision rule (frozen)

One outcome per host per task:

- `ALWAYS_DELEGATE`: the named route is majority-stable on both clear and context-dependent strata, adds no harmful fix, and its correctness benefit over inline is stable and not confined to one case (at least two independent decisive cases per stratum).
- `SELECTIVE_DELEGATE`: the named route improves the context-dependent, two-codes, or F1-vs-F7 cases without a stable advantage on clear cases; route only those documented ambiguity classes.
- `INLINE_DEFAULT`: no stable correctness/calibration benefit, any regressed case, or material latency/usage without compensating quality.
- `INCONCLUSIVE`: missing arm, unstable repetitions, integrity failure, ceiling exceeded without authorization, or too few decisive cases.

No percentage threshold is invented after results; a one-case directional difference is diagnostic only.

## Result (2026-09-13)

One outcome per host per task, computed directly from `routing-results-claude.json`'s per-cell `normalized_outcome`, majority-stable (2-of-3) per case:

- **Claude / finding_verification: `SELECTIVE_DELEGATE`.** The `clear` stratum (`FV-01`–`FV-04`) is tied at a stable 3-of-3 `PASS` for both arms — already at ceiling, so delegation shows no incremental benefit there. The `context-dependent` stratum shows a real, stable named-arm advantage with zero regressions: `FV-05` is stable `FAIL` inline (`1/3` `PASS`) vs. stable `PASS` named (`3/3`); `FV-08` is stable `FAIL` inline (`1/3`) vs. stable `PASS` named (`2/3`). No case is stable-better for inline. This matches `SELECTIVE_DELEGATE`'s own text exactly: improve the context-dependent cases, no advantage claimed on clear cases.
- **Claude / failure_classification: `INLINE_DEFAULT`.** Named delegation produced zero stable wins over inline across all 8 cases (`FC-01`–`FC-08`; most are tied `PASS` or tied `FAIL`) and one stable regression: `FC-07` (F1-vs-F7 stratum) is stable `PASS` inline (`3/3`) vs. stable `FAIL` named (`1/3`) — in every named execution the model reached the correct `F7` verdict but twice failed `decisive_evidence_complete` (an evidentiary-completeness failure, not a wrong-verdict failure). Per the decision rule's own text, any regressed case is disqualifying for anything above `INLINE_DEFAULT`.
- **Codex / both tasks: `INCONCLUSIVE`.** `codex.named` and `codex.native-role` are missing arms (see the Codex measured result above and its root-cause note); the decision rule's `INCONCLUSIVE` criterion ("missing arm") applies directly. `codex.inline`'s own 48 real cells remain valid raw evidence for a future revision that re-authorizes the delegation arms once the upstream Codex bug is fixed.
- **Safety**: zero `safety_*` check failures across all 96 Claude cells and all 48 real Codex cells — delegation did not produce an unsafe action on either host in this sample.

No SKILL.md changes follow from this result yet. Per the change boundary below, a wording change to `skills/e2e-reviewer/SKILL.md`'s and the two debugger skills' delegation blocks requires RED routing-contract tests first, then the smallest change, then a separately frozen confirmation case set — not this pilot's own case set reused.

## Change boundary

The measured run edits nothing. If a result supports a change and the user asks: RED routing-contract tests first, then the smallest wording change to the delegation blocks in `skills/e2e-reviewer/SKILL.md`, `skills/playwright-debugger/SKILL.md`, and `skills/cypress-debugger/SKILL.md`, then full CI and pre-push security, then confirmation on a separately frozen case set. Never touched: the inline fallback, the verdict vocabulary, F1-F15, pattern IDs and severities, the SP1-SP5 parity checks, generator V6, framework scope, or installation behavior.

## Dependencies and sequencing

Preconditions: output-discipline v2 terminal result reconfirmed; fresh `ci-local.sh` and `pre-push-security.sh` green; one immutable digest over the evaluated surfaces, fixtures, oracle, prompts, runner, rubric, and schedule; provider limits available; the two Claude smoke cases passed. Independent of `benchmarks/ours-vs-planner-pilot-v1` (separate snapshot label, never pooled) and of the reviewer release lane. Serial per provider; one model-benchmark lane at a time.

## Open items marked in the JSON

- RESOLVED 2026-09-11: Claude Code build recorded as `2.1.268`; the completed Claude report keeps judged fields unjudged rather than retroactively adding judge calls.
- RESOLVED 2026-09-13: live smoke established that delegation was not feasible on Codex CLI 0.154.0. Revision 4 records `codex.named` and `codex.native-role` as zero-cost `UNAVAILABLE` arms while authorizing only the 48 real `codex.inline` measured executions after a clean inline smoke and refreeze.
