# Subagent routing v1

**Status: `NOT_RUN` / preregistered, not yet frozen. No model call, agent installation, or case authoring has happened under this protocol. No routing result is claimed and production routing is unchanged.**

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
| `codex.inline` | Codex | `pending_authorization` | parent runs the frozen procedure itself |
| `codex.named` | Codex | `pending_authorization` | parent delegates to the isolated named TOML agent |
| `codex.native-role` | Codex | `pending_authorization` | parent delegates to Codex's native `verifier` / `debugger` role; `UNAVAILABLE` unless the harness can attest which role ran |

All arms receive byte-identical case material, the same absolute path to the frozen source-of-truth contract, and must return the same compact output schema. The deterministic scanner is not an arm.

### The dormant Codex arm

The operator excluded Codex for now (budget and host availability unresolved) but asked that it stay designed in. The three Codex arms are therefore real entries in `protocol.json` with `status: "pending_authorization"`, their strategy-execution counts fixed (144 measured, 3 smoke, at most 48 judge calls), and their request/wall-time/monetary ceilings left `null` with a `TBD` note. Activation is a separate file, `codex-arm-activation.json`, whose required fields the protocol enumerates (authorization, Codex build floor, model, request ceilings, turn caps, wall time, monetary ceiling or `unknown`, the native-role attestation method, and the path to the three passed Codex smoke cases). Because activation lives in that record and not in `protocol.json`, the preregistration digest does not change, and the Codex phase runs against the same frozen 16-case digest, oracle, scoring, and judge selector as the Claude phase. Codex results are reported per host and never pooled with Claude.

## Stage 4 amendments, incorporated

- **(a) Request accounting.** "240" is the full-matrix count of *strategy executions*, not model calls. Every cell logs actual requests, tokens, elapsed time, and visible cost separately for the parent and each child; unobservable child telemetry is `null`, never estimated.
- **(b) Native-role attestation.** A `codex.native-role` cell whose harness cannot prove which role ran records `UNAVAILABLE`; silent substitution voids the arm.
- **(c) Smoke gate.** The five feasibility smoke cases (one per host arm) must pass before the runner is frozen; in the Claude-only phase the two Claude smokes gate freeze, the three Codex smokes gate activation. Any runner change after the smoke requires a new protocol version.
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

Each slot predeclares the accepted verdict, decisive evidence, allowed confidence, required limitation, forbidden weakened fix, and whether a concrete fix is legal. The case bytes are authored at freeze, not now, so that the authored material cannot leak into any session before the case digest exists.

### Freshness-exclusion search

Pattern IDs and F-codes are closed vocabularies (24 and 15 entries) and cannot be the freshness unit; every pattern already appears somewhere in the public corpora. Freshness here means no source-byte duplicate and no scenario or defect-lineage duplicate. The inventories dumped and compared on 2026-09-11: `reviewer-holdout-v3.json` (8 cases: receipts, admin billing, settings, invoices, search, profile/board, catalog), `reviewer-holdout-v5.json` (20), `reviewer-fault-causal-v3.json` (24), `debugger-holdout-v1.json` (30), the four skills' `evals/evals.json` and fixture files (auth, dashboard, checkout, products, notebook, session state, optimistic UI, and others), the output-discipline v1 pilot (jobs-and-reports domain) and v2 pilot (garden plots / compost / harvest domain), and the worked examples in `pattern-reference.md`, the SKILL.md files, `docs/`, and `CHANGELOG.md`.

The chosen application domain, a **public library branch** (patron holds, reading-room bookings, overdue fines, staff hold queue), returned zero hits for `patron|reading room|book hold|library branch|overdue fine` across `skills/`, `scripts/`, `docs/`, `README.md`, `CHANGELOG.md`, and `benchmarks/`; the only `.handover/` hits are unrelated Spanish i18n strings inside a vendored `open-mercato` fixture. If freshness cannot be re-established at freeze, the run is labeled `development_known_cases` and is not used to choose routing.

## Schedule and budget

- 16 cases x 3 repetitions in fresh sessions and workspaces.
- Claude phase: 96 measured strategy executions + 2 smoke + at most 32 judge calls = **130 strategy executions maximum**.
- Full matrix when Codex is activated: 240 measured + 5 smoke + at most 80 judge calls = the existing **325** cap, now stated in the corrected vocabulary; actual model requests are capped separately per host.
- Claude actual-request ceiling: naive estimate ~1,200 requests (inline ~10 per execution; named ~5 parent + ~10 child), **pause-and-ask at 2x (2,400)**, **hard ceiling at 4x (4,800)**, per-execution turn cap 40 parent / 40 child, 15 minutes per execution, 52 serial hours hard ceiling. Declining at a ceiling ends the run `INCOMPLETE` with raw evidence preserved and unscored; authorizing continuation labels the report `CEILING_EXCEEDED_WITH_AUTHORIZATION`, which makes `ALWAYS_DELEGATE` unreachable for that host. Silent continuation and silent abort are both forbidden.
- Analysis unit: the unique majority-stable case (2-of-3). Repetitions test stability and create no additional defects.

## Decision rule (frozen)

One outcome per host per task:

- `ALWAYS_DELEGATE`: the named route is majority-stable on both clear and context-dependent strata, adds no harmful fix, and its correctness benefit over inline is stable and not confined to one case (at least two independent decisive cases per stratum).
- `SELECTIVE_DELEGATE`: the named route improves the context-dependent, two-codes, or F1-vs-F7 cases without a stable advantage on clear cases; route only those documented ambiguity classes.
- `INLINE_DEFAULT`: no stable correctness/calibration benefit, any regressed case, or material latency/usage without compensating quality.
- `INCONCLUSIVE`: missing arm, unstable repetitions, integrity failure, ceiling exceeded without authorization, or too few decisive cases.

No percentage threshold is invented after results; a one-case directional difference is diagnostic only.

## Change boundary

The measured run edits nothing. If a result supports a change and the user asks: RED routing-contract tests first, then the smallest wording change to the delegation blocks in `skills/e2e-reviewer/SKILL.md`, `skills/playwright-debugger/SKILL.md`, and `skills/cypress-debugger/SKILL.md`, then full CI and pre-push security, then confirmation on a separately frozen case set. Never touched: the inline fallback, the verdict vocabulary, F1-F15, pattern IDs and severities, the SP1-SP5 parity checks, generator V6, framework scope, or installation behavior.

## Dependencies and sequencing

Preconditions: output-discipline v2 terminal result reconfirmed; fresh `ci-local.sh` and `pre-push-security.sh` green; one immutable digest over the evaluated surfaces, fixtures, oracle, prompts, runner, rubric, and schedule; provider limits available; the two Claude smoke cases passed. Independent of `benchmarks/ours-vs-planner-pilot-v1` (separate snapshot label, never pooled) and of the reviewer release lane. Serial per provider; one model-benchmark lane at a time.

## Open items marked in the JSON

- RESOLVED 2026-09-11: Claude Code build recorded as `2.1.268`. No Codex judge budget is authorized for the Claude-only phase, so judged fields are reported as unjudged, never self-judged, until a Codex arm is separately authorized.
- `TBD` (Codex activation record only, still genuinely open): Codex build floor, request ceilings, turn caps, wall time, monetary ceiling, native-role attestation method. These stay `TBD` by design until the dormant Codex arm is activated.
