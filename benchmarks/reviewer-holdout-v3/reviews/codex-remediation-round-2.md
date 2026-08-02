## Code Review Summary

**Verdict:** REQUEST CHANGES  
**Score:** 73/100  
**Confidence:** High — 0.92  
**Confirmed issues:** 7

### Score Rubric

| Area | Score |
|---|---:|
| Taxonomy/framework semantics | 18/20 |
| Scanner accuracy and exit integrity | 11/25 |
| Behavioral evidence | 13/15 |
| Evaluator/comparator integrity | 18/20 |
| Documentation honesty | 8/10 |
| CI and regression coverage | 5/10 |
| **Total** | **73/100** |

### Confirmed Defects

[HIGH] Project ESLint disables can silently suppress the scanner’s P0 gate  
File: `skills/e2e-reviewer/scripts/scan.sh:90`

`should_skip_pattern()` removes Tier 2/3 checks whenever Tier 1 ran
successfully. Because the project flat config is appended after the baseline,
disabling `no-focused-test` produces no Tier 1 finding and also suppresses Tier
3 `#7`. This directly contradicts the documented claim that Tier 2/3 remain
independent.

Reproduction: adapted the existing local-ESLint fixture to contain `it.only()`.
ESLint exited cleanly, the scanner returned success, and `#7` was absent.

Fix: always run the bundled Tier 3 baseline, then deduplicate equivalent Tier 1
results. Add a regression with local ESLint, a disabled rule, and `.only`.

[HIGH] AST-only P0 findings do not affect default `FAIL_ON=p0`  
File: `skills/e2e-reviewer/scripts/scan.sh:429`,
`skills/e2e-reviewer/scripts/scan.sh:862`

AST findings are accumulated only in `ast_total`. The default `p0` branch
checks only `p0_hits`; therefore an AST-only `#15` or `#4f` finding exits
successfully. Multi-line missing-await assertions are explicitly delegated to
AST detection, making this a real silent-pass path.

Fix: track AST counts by mapped severity and include `ast_p0_hits` in the P0
exit gate. Add a multiline `expect(locator)…matcher()` regression with Tier 1
unavailable.

[MEDIUM] Valid `Promise.all` formatting triggers a false P0 and fails CI  
File: `skills/e2e-reviewer/scripts/scan.sh:662`

The exclusion recognizes `Promise.all([` only when the opening line ends
immediately after `[`. Putting the first promise on the same line leaves
subsequent action elements classified as missing-await.

Reproduced with:

```ts
await Promise.all([page.waitForResponse(...),
  page.locator('#send').click(),
]);
```

The scanner reported `#16`, counted one P0, and exited 1.

Fix: use structural ancestor detection or balanced-token parsing. Cover inline
first elements, comments, nested arrays, and `Promise.race`.

[MEDIUM] Cypress JUnit fallback can associate a failure with the wrong
classname  
File: `skills/cypress-debugger/SKILL.md:137`

Failures and classnames are extracted into separate arrays and joined by
index. A passing testcase before a failure shifts the indexes, producing
incorrect file/class evidence.

Fix: parse each `<testcase>` and its nested `<failure>` together with an XML
parser. Add mixed pass/fail and multiple-suite fixtures.

[MEDIUM] Playwright cross-project deduplication key contradicts its stated
behavior  
File: `skills/playwright-debugger/SKILL.md:234`

It says to deduplicate by `file + title + projectName`, but including
`projectName` preserves one finding per browser project—the inflation it says
to prevent.

Fix: group by `file + title`, then aggregate affected project names.

[MEDIUM] Cypress debugger can auto-install an unpinned package  
File: `skills/cypress-debugger/SKILL.md:44`

`npx mochawesome-merge` may download the latest package, conflicting with the
bundle’s dependency-free/no-implicit-install posture.

Fix: reuse a repository script or local binary, or use `npx --no-install` after
verifying availability. Otherwise report the missing tool.

[LOW] Benchmark documentation describes two reports while the protocol
requires three  
File: `docs/ai-reviewer-benchmark.md:153`

The current protocol registers three runner/model entries, but the text says
the comparator requires “both host reports.”

Fix: say “all preregistered host reports.”

### Top Five Improvements

1. Make Tier 3 unconditional and independent of project ESLint policy.
2. Make AST findings severity-aware and fail the default P0 gate.
3. Replace formatting-sensitive `Promise.all` detection with structural
   handling.
4. Add scanner regressions for local-rule disables, AST-only P0s, and Promise
   variants.
5. Correct debugger result grouping and replace regex-based JUnit correlation.

### Validation Performed

- Fresh full fixture matrix: **21/21 browser cells matched**, zero runtime
  errors, across seven operators and both frameworks.
- `test-reviewer-scanner.py`: passed.
- V1–V6 parity check: passed.
- Fixture contract validation and classifier checks: passed.
- Local ESLint path test: passed, but its missing detection assertion enabled
  the reproduced `.only` escape.
- Bash syntax, Python syntax compilation, eval JSON parsing, and
  `git diff --check`: passed.
- LSP diagnostics were invoked on all modified allowed surfaces. The configured
  server treated non-TypeScript files as TypeScript and reported the expected
  unresolved fixture-only `@playwright/test` import, so syntax and runtime
  checks supplied the actionable validation.
- No repository files were edited; final Git status matched the initial state.

The forbidden v3 corpus, reports, reviews, oracle audit, scorecard, and other
reviewer outputs were not inspected. Consequently, this audit validates the
harness contracts and documentation structure, but does not independently
endorse the blinded benchmark results.
