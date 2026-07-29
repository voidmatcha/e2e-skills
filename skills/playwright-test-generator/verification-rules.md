# Verification Rules (V1–V6)

<!-- V-RULE-CONTRACT: V1=primary-outcome;V2=assertion-falsification;V3=behavior-fault-injection;V4=write-contract-proof;V5=repeat-and-isolation;V6=independent-re-review;verdicts=PASS,FAIL,CANNOT_VERIFY,ERROR;source=immutable;install=forbidden -->
<!-- V-RESULT-SCHEMA: candidate,runner,verification.V1,verification.V2,verification.V3,verification.V4,verification.V5,verification.V6,sourceUnchanged,temporaryArtifactsRemaining -->

These rules verify generated Playwright tests without installing packages or requiring `npx`. Treat a generated spec as a candidate until every applicable rule passes. Mutations run only against a temporary or project-approved scratch copy; the source candidate must remain byte-identical.

## Capability discovery and command selection

Before verification, read `package.json`, lockfiles, Playwright config, testing docs, CI workflows, fixtures, and existing scripts. Prefer the narrowest repository-native command that already runs the target spec. Examples include `pnpm test:e2e -- <spec>`, `npm run test:e2e -- <spec>`, `yarn playwright test <spec>`, or `bun run test:e2e -- <spec>`. Do not install a package, add a script, rewrite lint config, or invent a generic `npx` command when the repository already defines its runner.

If the project already has mutation, coverage, lint, accessibility, visual, or fault-injection tooling, reuse it. Otherwise use Playwright-native temporary probes. Existing tooling is an implementation of a V-rule, not a prerequisite.

## Verdicts

- `PASS` — the expected evidence was observed.
- `FAIL` — the test stayed green under a mutation that should have made it red, was flaky, or lost its required proof.
- `CANNOT_VERIFY` — the mutation cannot be performed safely or the required environment/evidence is unavailable. State the exact reason; do not guess.
- `ERROR` — the verifier itself failed. Do not misreport this as a test defect.

## V1 — Primary Outcome

Name one observable product outcome per scenario before generation. The test title, actions, and primary assertion must describe the same behavior. Record the outcome in the approved scenario plan; a package-specific marker such as `@primary-assert` is optional and must not be added unless the project already uses it.

## V2 — Assertion Falsification

In a temporary copy, invert only a single-line, framework-native primary matcher whose inverse is unambiguous, then run the repository-native targeted command. The mutated run must turn red.

| Original | Safe temporary inverse |
|---|---|
| `toBeVisible()` | `not.toBeVisible()` |
| `not.toBeVisible()` | `toBeVisible()` |
| `toHaveText(x)` | `not.toHaveText(x)` |
| `toHaveURL(x)` | `not.toHaveURL(x)` |
| `toHaveCount(n)` | `not.toHaveCount(n)` |

Return `CANNOT_VERIFY` for custom matchers, multiple assertions on one line, dynamic matcher construction, multi-line chains that cannot be rewritten safely, or a candidate the project runner cannot execute from scratch. Never mutate the source candidate. `FAIL` if the inverted assertion survives.

## V3 — Behavior Fault Injection

Use `page.route()` or an existing project fixture to corrupt a product input that repository source, a trace, or observed network evidence proves is load-bearing: success to error, expected text to a different value, non-empty to empty, response to abort, or a bounded delay. The unchanged primary assertion must turn red. Do not invent endpoints or mutate third-party/production traffic. Return `CANNOT_VERIFY` when no safe, local, interceptable dependency is evidenced.

## V4 — Write Contract Proof

For signup, checkout, save, delete, toggle, and similar writes, establish request observation before the action and prove method, endpoint, relevant payload, and expected cardinality. Pair request proof with the user-visible outcome. Also inject a failed write and prove success UI does not remain accepted. Optimistic DOM state alone is not write success.

## V5 — Repeat and Isolation

Use repository-native commands to run the candidate alone, repeatedly with the project's supported repeat mechanism, and in its normal suite context. Exercise normal CI parallelism when the project supports it. A pass after retry is flaky evidence, not a clean pass. Keep repetitions bounded and report any mode the repository cannot express as `CANNOT_VERIFY`.

## V6 — Independent Re-review

The writer or debugger cannot approve its own output. After generation, use `e2e-reviewer`; after any debugger repair, run it again. During repair, expected values, primary outcome, assertion target, scenario count, and request proof are immutable. The debugger may fix only evidenced mechanics such as locator, wait strategy, navigation, fixture, setup order, or test data. It must not delete/skip a test or weaken an assertion to manufacture green; return `NOFIX` when behavior and approved intent disagree.

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
    "V2": {"status": "PASS", "evidence": "inverse mutation failed"},
    "V3": {"status": "CANNOT_VERIFY", "reason": "no evidenced interceptable dependency"},
    "V4": {"status": "PASS", "evidence": "one expected write request"},
    "V5": {"status": "PASS", "evidence": "bounded solo/repeat/suite runs"},
    "V6": {"status": "PASS", "evidence": "independent reviewer verdict"}
  },
  "sourceUnchanged": true,
  "temporaryArtifactsRemaining": []
}
```

Every applicable V-rule needs one of the four verdicts. Use `reason`, not invented evidence, for `CANNOT_VERIFY` or `ERROR`. A completion report is invalid when `sourceUnchanged` is false, temporary artifacts remain, or an applicable V-rule is omitted.
