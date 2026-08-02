# Codex product review before remediation

This review was produced by a fresh read-only Codex native reviewer that was
barred from the v3 corpus, oracle, reports, and other reviews. It evaluated the
product snapshot before the remediation described in the changelog.

## Product audit verdict

**REQUEST CHANGES — 67/100**

The product has a strong validation foundation, but two P0-contract errors can
suppress real silent-pass findings, and the standalone scanner's default P0
exit gate fails on documented false positives.

### Confirmed defects

1. **[HIGH] Retry-wrapper exemption hides real unawaited assertions/actions.**
   `skills/e2e-reviewer/SKILL.md:152` and
   `references/pattern-reference.md:368,388` say to skip #15/#16 inside
   `toPass`/`expect.poll`. Actual Playwright 1.62 behavior: an unawaited locator
   assertion inside `toPass` resolved the wrapper in 3 ms, then produced an
   unhandled rejection. The callback does not return the floating Promise, so
   the wrapper cannot await or retry it.

   **Fix:** retain the exemption only for awaited one-shot checks
   (#4c-e/#4h); never exempt #15/#16. Add executable regressions.

2. **[HIGH] #16 misses the most common locator-variable form.** The contract
   says every Playwright action must be awaited
   (`pattern-reference.md:384`), but scanner and mandatory fallback only cover
   direct `page.locator/getBy...` expressions (`scan.sh:786`,
   `SKILL.md:135-146`). `saveButton.click()` or
   `this.submitButton.click()` can therefore receive a clean P0 result.

   **Fix:** add structural detection for Locator/POM variables and expand the
   bounded semantic sweep beyond `page.*`.

3. **[MEDIUM] Default scanner P0 gating includes candidates the skill
   explicitly says to reject.** `SKILL.md:114,120` excludes action-only
   visibility gates and `Promise.all` actions. The scanner nevertheless counts
   both as P0 (`scan.sh:758,786`) and gates on the raw count
   (`scan.sh:703-712,843-844`). Fresh scan of
   `evals/files/documented-exclusions.spec.ts` exited 1 with two #5a false
   positives plus a Promise.all #16 false positive.

   **Fix:** structurally filter these contexts or route them to LLM triage
   outside the P0 exit gate.

4. **[MEDIUM] Cross-host comparator does not require the full corpus.** The
   runner accepts `--case` subsets (`run-reviewer-holdout.py:1100,1180-1185`);
   comparator reconstructs whichever IDs appear in the schedule
   (`compare-reviewer-holdouts.py:134-143`) without asserting they equal all
   corpus case IDs. Two cherry-picked subset reports can satisfy the release
   comparator.

   **Fix:** require full case-set equality for release/cross-host PASS; mark
   subset reports development-only.

5. **[MEDIUM] #19 documents incorrect Playwright retry semantics.** The
   taxonomy says retries reuse the worker (`pattern-reference.md:580`;
   `docs/e2e-test-smells.md:44`). Playwright's pinned types explicitly say the
   worker restarts after failure and receives a new `workerIndex`
   (`node_modules/playwright/types/test.d.ts:2698-2703,6062-6063`).

   **Fix:** limit the rationale to cross-test state within a surviving worker
   and cross-worker collisions; remove “survives retries.”

### Limitations and optional improvements

- Browser mutation evidence is sound but covers only 6 of 24 families. Fresh
  execution passed all 18/18 matrix cells with zero errors. Operator scope is
  declared at `run-fixture-faults.py:42-117`.
- The public synthetic holdout is regression evidence, not generalization
  evidence; the benchmark document states this honestly
  (`docs/ai-reviewer-benchmark.md:330-382`).
- README overclaims “matcher-less `expect()`” coverage (`README.md:500`); no
  active taxonomy/scanner rule covers it. Either add it under #8 or remove the
  claim.
- AST Tier 2 has no file-level Playwright scope and may flag valid jest-dom
  `toBeVisible()` calls (`sg-15-missing-await-playwright-expect.yml:28-35`).

### Rubric

| Dimension | Score |
| --- | ---: |
| Taxonomy semantic correctness | 16/25 |
| Coverage completeness | 12/20 |
| False-positive controls/scanner | 8/15 |
| Executable behavior evidence | 12/15 |
| Runner/comparator integrity | 11/15 |
| Documentation honesty/usability | 8/10 |
| **Total** | **67/100** |

### Top five improvements

1. Remove the #15/#16 retry-wrapper exemption and lock it with browser tests.
2. Detect unawaited actions on Locator/POM variables.
3. Separate Phase-2 candidates from scanner exit-gating P0s.
4. Require full-corpus schedules for release comparator PASS.
5. Correct #19 worker-retry semantics and expand executable mutation coverage
   beyond 6 families.

### Validation performed

JSON and shell syntax passed; fixture contracts/classifier passed; full browser
mutation matrix passed 18/18. Serena diagnostics were attempted on all modified
files, but this project's TypeScript-only LSP misparsed Markdown/JSON/shell
files, so syntax-specific validators were used instead.

## Maintainer adjudication

The review's locator/POM, scanner-gate, full-corpus, and worker-retry findings
were reproduced and fixed. Its stronger claim that the retry-wrapper form is a
silent pass was challenged with Playwright 1.62: the wrapper did not await the
floating assertion, but the runner surfaced the later rejection and failed the
test. The contract now says the wrapper cannot observe or retry that Promise
without claiming that every current runner silently passes it.
