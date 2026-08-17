# Verification Rules (V1–V6)

<!-- V-RULE-CONTRACT: V1=primary-outcome;V2=assertion-falsification;V3=behavior-fault-injection;V4=write-contract-proof;V5=repeat-and-isolation;V6=independent-re-review;verdicts=PASS,FAIL,CANNOT_VERIFY,ERROR;source=immutable;install=forbidden -->
<!-- V-RESULT-SCHEMA: candidate,runner,verification.V1,verification.V2,verification.V3,verification.V4,verification.V5,verification.V6,sourceUnchanged,temporaryArtifactsRemaining -->

These rules verify generated Playwright tests without installing packages or requiring `npx`. Treat a generated spec as a candidate until every applicable rule passes. Mutations run only against a temporary or project-approved scratch copy; the source candidate must remain byte-identical.

## Capability discovery and command selection

Before verification, read `package.json`, lockfiles, Playwright config, testing docs, CI workflows, fixtures, and existing scripts. Prefer the narrowest repository-native command that already runs the target spec. Examples include `pnpm test:e2e -- <spec>`, `npm run test:e2e -- <spec>`, `yarn playwright test <spec>`, or `bun run test:e2e -- <spec>`. Do not install a package, add a script, rewrite lint config, or invent a generic `npx` command when the repository already defines its runner.

If the project already has mutation, coverage, lint, accessibility, visual, or fault-injection tooling, reuse it. Otherwise use Playwright-native temporary probes. Existing tooling is an implementation of a V-rule, not a prerequisite.

Do not begin browser-backed verification from a target URL unless exploration
recorded an approved DNS snapshot, pinned peer probes, and a no-drift result.
For an untrusted remote target, verification also requires the same enforceable
browser egress policy used during exploration; a Playwright route callback is
not a transport boundary. If those controls are unavailable, do not navigate
and record the affected browser-backed rule as `CANNOT_VERIFY`.

When auth depends on named environment variables, credential values remain
local to the user's environment. The agent may inspect only each variable's
presence and non-empty status; it never requests, reads, prints, echoes, logs,
or asks the user to paste a value.

## Verdicts

- `PASS` — the expected evidence was observed.
- `FAIL` — the test stayed green under a mutation that should have made it red, was flaky, or lost its required proof.
- `CANNOT_VERIFY` — the mutation cannot be performed safely or the required environment/evidence is unavailable. State the exact reason; do not guess.
- `ERROR` — the verifier itself failed. Do not misreport this as a test defect.

## V1 — Primary Outcome

Name one observable product outcome per scenario before generation. The test title, actions, and primary assertion must describe the same behavior. Record the outcome in the approved scenario plan; a package-specific marker such as `@primary-assert` is optional and must not be added unless the project already uses it.

## V2 — Assertion Falsification

Use V2 only when the candidate reaches an evidenced deterministic settled-state gate
before its primary assertion (for example, a proven terminal response,
completed navigation plus an application-specific ready state, or a terminal UI
state). In a temporary copy, mutate one single-line, framework-native primary
matcher only when the mutation is guaranteed contradictory after that same gate,
then run the repository-native targeted command. The mutated run must turn
red **because the changed primary assertion reports the expected contradictory
mismatch**. Capture the failure location and matcher diagnostics and require
them to identify that exact mutated assertion. A nonzero exit caused only by
setup, navigation, fixture, browser, timeout, worker, reporter, or other
unrelated infrastructure failure does not kill the mutant: record `ERROR` when
the verifier/run infrastructure failed, or `CANNOT_VERIFY` when causal
attribution cannot be established.

| Original | Conditionally safe temporary inverse |
|---|---|
| `toBeVisible()` | `not.toBeVisible()` after the same settled-state gate |
| `not.toBeVisible()` | `toBeVisible()` after the same settled-state gate |
| `toHaveText(x)` | `not.toHaveText(x)` after the same settled-state gate |
| `toHaveURL(x)` | `not.toHaveURL(x)` after the same settled-state gate |
| `toHaveCount(n)` | `not.toHaveCount(n)` after the same settled-state gate |

Return `CANNOT_VERIFY` when the assertion observes transitional or eventually changing state,
no deterministic settled-state gate is evidenced, the inverse
is not guaranteed contradictory after that gate, or the test depends on
uncontrolled timing between separate runs. Also return it for custom matchers,
multiple assertions on one line, dynamic matcher construction, multi-line
chains that cannot be rewritten safely, or a candidate the project runner
cannot execute from scratch. Never mutate the source candidate. `FAIL` if a
valid contradictory mutation survives. Return `ERROR` or `CANNOT_VERIFY`, never
`PASS`, when the mutant run is red but its output does not prove failure at the
changed primary assertion.

## V3 — Behavior Fault Injection

Use `page.route()` or an existing project fixture to corrupt a product input that repository source, a trace, or observed network evidence proves is load-bearing: success to error, expected text to a different value, non-empty to empty, response to abort, or a bounded delay.

Before applying the fault, record both (1) the exact unchanged primary assertion
expected to fail and (2) the observable mismatch that its matcher is expected
to report under that fault. First require the unfaulted candidate to pass. The
unchanged primary assertion must turn red. The fault kills the test only when
the faulted run turns red at that exact primary
assertion and its diagnostics match the declared observable difference. A red
run with a different failure location or mismatch is `ERROR` when the verifier
or run infrastructure failed, or `CANNOT_VERIFY` when causal attribution cannot
be established; it is never `PASS`.

Do not invent endpoints or mutate third-party/production traffic. Return
`CANNOT_VERIFY` when no safe, local, interceptable dependency is evidenced.
This per-scenario runtime declaration is not the `generator-faultkill-v1`
planning DSL and does not change that benchmark's frozen plan language.

## V4 — Write Contract Proof

For signup, checkout, save, delete, toggle, and similar writes, establish request observation before the action and prove method, endpoint, relevant payload, and expected cardinality. Pair request proof with the user-visible outcome. Also inject a failed write and prove success UI does not remain accepted. Optimistic DOM state alone is not write success.

## V5 — Repeat and Isolation

Use repository-native commands to run the candidate alone, repeatedly with the project's supported repeat mechanism, and in its normal suite context. Exercise normal CI parallelism when the project supports it. A pass after retry is flaky evidence, not a clean pass. Keep repetitions bounded and report any mode the repository cannot express as `CANNOT_VERIFY`.

Before repeating a write-producing scenario, prove at least one replay-safe
boundary:

1. the write carries an idempotency key whose enforcement is proven at the
   persistent system boundary;
2. every attempt uses disposable state that is reset or rolled back before and
   after that attempt; or
3. every write is fully stubbed or intercepted, with evidence that no
   persistent boundary is reached.

A disabled button, double-click guard, unique UI value, or loopback frontend
alone does not prove replay safety. If none of the three boundaries is proven,
do not replay the persistent write. Record V5 as `CANNOT_VERIFY` and return
`PARTIAL/BLOCKED` under the completion matrix. A single normal run may still
provide V1/V4 evidence, but it cannot substitute for V5 repetition.

## V6 — Independent Re-review

The writer or debugger cannot approve its own output. Run `e2e-reviewer` through
a distinct fresh-context, read-only reviewer actor or process that did not write
or repair the candidate. Give it the candidate paths and the reviewer contract,
not the writer's conclusions; require a recorded verdict and evidence.
Inline self-review by the writer or debugger cannot produce `PASS`.
Return `CANNOT_VERIFY` when the host cannot provide a separate reviewer context or
cannot keep that reviewer read-only.

Run this independent review after generation and again after any debugger
repair. During repair, expected values, primary outcome, assertion target,
scenario count, and request proof are immutable. The debugger may fix only
evidenced mechanics such as locator, wait strategy, navigation, fixture, setup
order, or test data. It must not delete/skip a test or weaken an assertion to
manufacture green; return `NOFIX` when behavior and approved intent disagree.

## Temporary-copy safety

Prefer an existing gitignored scratch directory accepted by the project config. Otherwise use a uniquely named temporary spec in the configured test directory and remove it in `finally`/`trap`. Before and after mutation, hash the candidate and inspect `git status`; completion requires an unchanged candidate and no verifier artifacts in the repository.

## Structured result contract

Record the result in this shape so an omitted or unavailable proof is visible rather than silently treated as a pass:

```json
{
  "candidate": "tests/example.spec.ts",
  "runner": "repository-native targeted command",
  "verification": {
    "V1": {"status": "PASS", "evidence": "observable primary outcome"},
    "V2": {"status": "PASS", "evidence": "settled-state contradictory mutation failed"},
    "V3": {"status": "CANNOT_VERIFY", "reason": "no evidenced interceptable dependency"},
    "V4": {"status": "PASS", "evidence": "one expected write request"},
    "V5": {"status": "PASS", "evidence": "bounded solo/repeat/suite runs"},
    "V6": {"status": "PASS", "evidence": "fresh-context read-only reviewer verdict"}
  },
  "sourceUnchanged": true,
  "temporaryArtifactsRemaining": []
}
```

Every applicable V-rule needs one of the four verdicts. Use `reason`, not invented evidence, for `CANNOT_VERIFY` or `ERROR`. A completion report is invalid when `sourceUnchanged` is false, temporary artifacts remain, or an applicable V-rule is omitted.

### Completion status matrix

| Condition | Allowed final status |
|---|---|
| Applicable V4 is `PASS` (or explicitly `N/A` only for a read-only scenario), applicable V5 is `PASS`, and the other completion gates pass | `Complete` |
| Applicable V4 or V5 is `CANNOT_VERIFY` | `PARTIAL/BLOCKED` with the exact missing capability or evidence |
| Applicable V4 or V5 is `ERROR` | `PARTIAL/BLOCKED` with the verifier error; never reinterpret it as product evidence |
| Applicable V4 or V5 is `FAIL` | `BLOCKED` until the candidate is repaired and reverified |

`CANNOT_VERIFY` and `ERROR` are honest outcomes, but they are not successful
completion evidence for write proof or repeat/isolation. Never emit a
`Complete` heading when an applicable V4 or V5 has either status.
