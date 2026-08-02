## Independent Product Review

**Score: 83/100**  
**Verdict: PASS WITH CAVEATS**

The product is unusually rigorous for an agent skill: the taxonomy is broad, false-positive triage is explicit, the scanner is fail-closed for its mechanical P0 gate, and the model runner preserves raw outputs plus strong input/workspace digests. It is not yet justified as a near-perfect or generally validated reviewer because several semantic claims are inaccurate and executable evidence covers only 11 of 24 pattern families.

### Rubric

| Area | Score | Assessment |
|---|---:|---|
| Taxonomy correctness and coverage | 20/25 | Strong silent-pass core and cross-file checks; important async/missing-await surfaces remain uncovered. |
| Playwright/Cypress semantic accuracy | 15/20 | Mostly precise, especially auth, retry wrappers, Cypress queue semantics, and absence assertions; two confirmed Playwright inaccuracies. |
| False-positive controls | 18/20 | Excellent triage boundaries, scope filtering, suppression, config tracing, and Promise combinator exclusions. |
| Executable mutation/behavior evidence | 10/15 | Real browser matrix is valuable, but covers 11/24 families and archives hashes/markers rather than successful raw logs. |
| Model-runner integrity/reproducibility | 13/15 | Strong snapshots, exact scoring, drift detection, and read-only controls; runtime identity and sealed isolation remain externally asserted. |
| Documentation honesty/persuasion | 7/10 | Persuasive and candid about public-corpus limitations, but contains contradictory or overstated framework/lint claims. |

## Confirmed defects

### [MEDIUM] `expect.soft()` is described as masking failures, but Playwright marks the test failed

The taxonomy says soft assertions can “mask cascading failures” and are “functionally equivalent to error swallowing” when over 50% of assertions are soft:

- `skills/e2e-reviewer/references/pattern-reference.md:540-560`
- `skills/e2e-reviewer/SKILL.md:121`
- `README.md:355`

The vendored Playwright runtime explicitly propagates a soft assertion error into test failure:

- `scripts/evals/fixtures/node_modules/playwright/lib/worker/workerProcessEntry.js:1029-1032`

Soft assertions defer interruption and may worsen diagnostics, but they do not swallow the failure. Keep a P1/P2 maintainability rule if desired, but remove the silent-mask rationale and replace the arbitrary `>50%` threshold with evidence about dependent/cascading assertions.

### [MEDIUM] Pattern #16 misses valid Playwright actions and formatted multiline chains

The scanner and mandatory bounded sweep recognize only:

`click|fill|type|press|check|uncheck|selectOption|setInputFiles|hover|focus|blur`

Evidence:

- `skills/e2e-reviewer/SKILL.md:120,135-146`
- `skills/e2e-reviewer/scripts/scan.sh:1015-1019`

The bundled Playwright API also exposes Promise-returning actions such as `clear`, `dblclick`, `dispatchEvent`, `dragTo`, `pressSequentially`, `scrollIntoViewIfNeeded`, and `tap`:

- `scripts/evals/fixtures/node_modules/playwright-core/types/types.d.ts:14358,14581,14742,14788,16091,16160,16528`

Because both scanner regexes and the “exactly this list—no more, no less” sweep assume receiver and action are on one line, a formatter-produced chain such as `page` → `.getByRole(...)` → `.dblclick()` can evade the entire #16 contract. Expand the API set and use AST/structural ancestry for multiline receiver chains.

### [LOW] Documentation contradicts the implementation about lintability and auto-wait

README says the listed mechanical rules are “already covered” by standard plugins and then places #4f under “What a linter structurally cannot catch”:

- `README.md:370-380`

The skill itself correctly says local lint/AST tiers are optional and #4f coverage is only partial:

- `skills/e2e-reviewer/SKILL.md:49,60-62,66-74`

README also implies `page.locator(...).click()` adds auto-wait absent from `page.click()`:

- `README.md:354`

But the bundled Playwright API documents attachment waiting, actionability checks, detach retries, scrolling, and navigation waiting for `page.click()` itself:

- `scripts/evals/fixtures/node_modules/playwright-core/types/types.d.ts:2219-2236`

The locator migration remains good advice, but the benefit should be locator composition, strictness, reuse, and diagnostics—not invented auto-wait semantics.

## Confirmed strengths

- P0 is tightly defined around tests or suites that can remain green against broken behavior, with nuanced auth classification rather than treating every missing login as P0 (`SKILL.md:117,148`; `pattern-reference.md:342-344`).
- Cypress semantics are substantially accurate: standalone `cy.get()` is not mislabeled as a missing assertion, and async callback, assigned Chainable, and unsafe post-action chain cases are separated (`SKILL.md:110,322`; `pattern-reference.md:488-492`).
- False-positive handling is excellent for `toBeAttached`, absence assertions, conditional setup actions, retry wrappers, `Promise.all`/`race`, module-level type-only declarations, and dynamic accessible names (`SKILL.md:108-122,152`; `pattern-reference.md:203-260,465-492`).
- Scanner scope filtering resolves Playwright custom fixtures and excludes non-E2E files rather than trusting filenames alone (`scan.sh:28-129,693-723`).
- Scanner regression and fixture-classifier checks passed freshly:
  - `reviewer scanner: pass`
  - `fixture fault classifier: pass (33 synthetic + 33 browser cells)`
  - Shell and Python syntax checks passed.
- The model runner prevents answer leakage from the staged skill, snapshots inputs once, creates fresh workspaces, hashes every staged path, preserves raw model output, and treats drift or infrastructure failures as inconclusive:
  - `run-reviewer-holdout.py:321-420,485-547,573-656,730-752,966-1064,1150-1178,1266-1305`
- Documentation is candid that the corpus is public development evidence, not a sealed oracle, and that runner/model identity is local provenance rather than attestation:
  - `README.md:74-77`
  - `CONTRIBUTING.md:99-115,126-142,168-171`

## Limitations, not confirmed defects

- Executable browser evidence covers **11 unique pattern IDs**, not all 24: `benchmarks/fixture-faults/2026-07-30-expanded.json:22-28`. Important P0s such as #15 and #16 currently lack mutation-backed behavior proof.
- Successful browser-cell raw output is not archived; only evidence markers and `output_sha256` are stored. Raw output is included only for mismatches (`run-fixture-faults.py:646-672`). This supports rerunning but prevents independent reclassification of the archived successful cells.
- The fault report hashes fixtures, operators, and the package lock, but not the evaluator source itself (`run-fixture-faults.py:729-756`).
- Model execution remains nondeterministic and locally identified. Repetition and schedule hashing improve measurement but cannot pin a remotely changing model behind the same name.
- An executable `--isolation-wrapper` is required for non-public corpora, but the runner explicitly records that isolation is not proven (`run-reviewer-holdout.py:1167-1178,1232-1244`). That is honest, but sealed claims still need external audit.

## Optional coverage improvements

- Add a P0 sub-pattern for async work escaping the test lifecycle: `forEach(async ...)`, unconsumed `map(async ...)`, and unawaited `test.step(...)`.
- Cover floating Playwright navigation/wait Promises such as `page.goto`, `reload`, `waitForResponse`, and `waitForEvent`.
- Add explicit cross-test data-isolation checks for shared accounts, tenant leakage, and cleanup failures beyond uncontrolled writes.
- Add multiline Cypress command-chain fixtures; current scanner evidence concentrates on same-line forms.
- Add negative mutation controls proving that legitimate soft assertions, controlled full-stack writes, and authenticated setup projects are not downgraded incorrectly.

## Five highest-value improvements

1. Expand #16 to the full Locator action API and AST-backed multiline chains.
2. Correct #18’s soft-assertion semantics and replace the arbitrary 50% rule.
3. Add lifecycle-escaped async callbacks/Promises as a new silent-pass family.
4. Extend executable browser mutations to every P0 and the highest-risk P1 families, especially #15/#16.
5. Archive sanitized raw browser output and evaluator digests so evidence can be independently replayed and reclassified.

## Scope statement

I read only `/private/tmp/e2e-product-review-final.bgR67q`. I did **not** open or inspect:

- `/private/tmp/e2e-test-reviewer` or the snapshot’s parent directory
- any v3 labeled corpus
- any holdout-v3 source
- the v3 scorecard or any scored v3 report contents
- any previous-review artifact
- any chat-derived benchmark result

No files were edited.
