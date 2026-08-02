## Code Review Summary

**Score: 78/100**  
**Verdict: REQUEST CHANGES**

The product is substantially stronger post-fix: the scanner regression suite passes, local ESLint/no-download behavior passes, archive hashes match current sources, and a fresh full browser matrix completed 33/33. However, one P0 false-positive path and several product-contract inaccuracies remain.

### Rubric

| Area | Score |
|---|---:|
| Taxonomy correctness and coverage | 17/20 |
| Playwright/Cypress semantic accuracy | 14/20 |
| False-positive controls | 11/15 |
| Executable mutation/behavior evidence | 14/15 |
| Runner integrity and reproducibility | 10/15 |
| Documentation honesty and persuasion | 12/15 |
| **Total** | **78/100** |

### Confirmed Defects

[HIGH] #16 misclassifies an awaited Promise-array action as a P0 when `]` closes on the action line  
File: [scan.sh](/private/tmp/e2e-product-review-postfix.rzzsdt/skills/e2e-reviewer/scripts/scan.sh:980)

The Promise-array filter counts opening and closing brackets before testing `depth > 0`. Therefore this valid shape remains a P0 finding:

```ts
await Promise.all([
  page.locator('#save').click()]);
```

The existing regression uses a later closing-bracket line, so it misses the boundary: [missing-await-contexts.spec.ts](/private/tmp/e2e-product-review-postfix.rzzsdt/skills/e2e-reviewer/evals/files/missing-await-contexts.spec.ts:41), [test-reviewer-scanner.py](/private/tmp/e2e-product-review-postfix.rzzsdt/scripts/ci/test-reviewer-scanner.py:173).

Fix: determine membership before consuming the target line’s closing bracket, or use a token/AST-balanced ancestor check. Add same-line-close cases for `Promise.all` and `Promise.race`, plus `allSettled`/`any` if they are accepted Promise consumers.

[MEDIUM] The advertised “full Locator action surface” omits `locator.screenshot()`  
Files: [SKILL.md](/private/tmp/e2e-product-review-postfix.rzzsdt/skills/e2e-reviewer/SKILL.md:120), [scan.sh](/private/tmp/e2e-product-review-postfix.rzzsdt/skills/e2e-reviewer/scripts/scan.sh:1123), [test-reviewer-scanner.py](/private/tmp/e2e-product-review-postfix.rzzsdt/scripts/ci/test-reviewer-scanner.py:190)

All three canonical lists omit `screenshot`. The pinned Playwright declaration confirms it is an async Locator method that waits for actionability and returns a Promise: [types.d.ts](/private/tmp/e2e-product-review-postfix.rzzsdt/scripts/evals/fixtures/node_modules/playwright-core/types/types.d.ts:16123).

Fix: either add `screenshot` to detection, references, and tests, or narrow the claim from “full Locator action surface” to the exact mutation/action subset intentionally covered.

[MEDIUM] #18’s evaluation contradicts its correct soft-assertion semantics  
Files: [pattern-reference.md](/private/tmp/e2e-product-review-postfix.rzzsdt/skills/e2e-reviewer/references/pattern-reference.md:542), [evals.json](/private/tmp/e2e-product-review-postfix.rzzsdt/skills/e2e-reviewer/evals/evals.json:306), [soft-and-zero-timeout.spec.ts](/private/tmp/e2e-product-review-postfix.rzzsdt/skills/e2e-reviewer/evals/files/soft-and-zero-timeout.spec.ts:24)

The contract correctly says soft assertions still fail the test and should be flagged only when dependent work continues after a broken prerequisite. The evaluation nevertheless requires a finding for three terminal soft assertions with no dependent work. Even the documented “BAD” example has no dependent continuation.

Additionally, the scanner emits all `expect.soft()` uses as ordinary `[P1]`, not `[LLM-TRIAGE]`: [scan.sh](/private/tmp/e2e-product-review-postfix.rzzsdt/skills/e2e-reviewer/scripts/scan.sh:1130).

Fix: change the positive fixture to perform dependent work after the soft prerequisite, add a legitimate all-soft independent-detail guard, and route raw #18 hits to LLM triage.

[MEDIUM] Archived-output path sanitization is incomplete on macOS  
Files: [run-fixture-faults.py](/private/tmp/e2e-product-review-postfix.rzzsdt/scripts/evals/run-fixture-faults.py:557), [2026-07-30-expanded.json](/private/tmp/e2e-product-review-postfix.rzzsdt/benchmarks/fixture-faults/2026-07-30-expanded.json:82), [test-fixture-faults.py](/private/tmp/e2e-product-review-postfix.rzzsdt/scripts/ci/test-fixture-faults.py:157)

The archive contains malformed residual paths such as `/private$FIXTURE_COPY/...`. This occurs when a `/var/...` temporary path is rendered canonically as `/private/var/...`, but sanitization replaces only the noncanonical substring. The validation misses it because it rejects `/private/`, not `/private$FIXTURE_COPY`.

Fix: sanitize both lexical and realpath forms, longest path first. Assert that no replacement token is immediately preceded by a path component and test macOS `/var` ↔ `/private/var` aliases.

[MEDIUM] #17’s lint mapping and “deprecated” wording are inaccurate  
Files: [scan.sh](/private/tmp/e2e-product-review-postfix.rzzsdt/skills/e2e-reviewer/scripts/scan.sh:1167), [SKILL.md](/private/tmp/e2e-product-review-postfix.rzzsdt/skills/e2e-reviewer/SKILL.md:329)

The scanner tells users #17 maps to `playwright/no-element-handle`, which does not describe direct selector-based Page actions. The quick reference calls these APIs “Deprecated,” while the pinned Playwright types only recommend Locator alternatives and retain `page.click`: [types.d.ts](/private/tmp/e2e-product-review-postfix.rzzsdt/scripts/evals/fixtures/node_modules/playwright-core/types/types.d.ts:2216).

Fix: label them “discouraged direct Page selector APIs,” map to the actual compatible lint rule or advertise no mapping, and decide whether #17 covers the broader Page action family rather than only six methods.

### Confirmed Strengths

- Fresh full mutation matrix: 11 operators, both frameworks, 33/33 matched, zero errors.
- Archive runner, fixture, operator, and lockfile digests match current source.
- Archived outputs are nonempty, hashed, untruncated, and contain concrete framework failure evidence.
- #16 now covers multiline receivers, direct versus POM/Locator provenance, return/await guards, comments, strings, and the documented 20-method list.
- #18 documentation correctly acknowledges that soft failures still fail the test.
- README honestly limits behavioral evidence to 11 of 24 families: [fixture-fault README](/private/tmp/e2e-product-review-postfix.rzzsdt/benchmarks/fixture-faults/README.md:18).

### Limitations, Not Defects

- Executable fault evidence covers 11/24 pattern families, not the whole taxonomy.
- Archive hashes establish consistency with current files, not cryptographic attestation that the archive could not have been rewritten.
- LSP diagnostics could not resolve root-level `@playwright/test` types in this standalone export; targeted scanner, syntax, ESLint-path, archive, and browser-matrix validations passed.
- The supplied directory is not a Git repository, so no diff-based “modified files” scope was available.

### Five Highest-Value Next Improvements

1. Repair #16 Promise-consumer ancestry and add bracket-closing boundary regressions.
2. Align #18 fixtures, scanner triage, and the dependent-work semantic contract.
3. Canonicalize/redact all temporary-path aliases and harden archive privacy assertions.
4. Correct #17 terminology/lint provenance and finish the intended Page/Locator action inventory.
5. Expand executable behavior plus false-positive evidence to #15, #16, #18 and additional Cypress-specific families.

### Validation Run

- `test-reviewer-scanner.py`: passed.
- `test-fixture-faults.py`: passed.
- `test-local-eslint-path.sh`: passed.
- Shell/Python syntax checks: passed.
- Fresh `run-fixture-faults.py`: 33/33 matched, zero errors.

I did not read the parent directory, `/private/tmp/e2e-test-reviewer`, any labeled v3 corpus or v3 holdout/evidence source, reviewer/model scorecards or reports, previous reviews, or chat conclusions. The only archived result inspected was the explicitly requested fixture-fault raw-output/provenance report.
