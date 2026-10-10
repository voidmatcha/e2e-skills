# Real-fix acquisition v3 (public development search)

This source-first acquisition extends the [v2 search](../real-fix-acquisition-v2/README.md) without changing its ledger or scores. It is not a sealed holdout, a model/scanner evaluation, or a release claim. This boundary was written before querying the six rows' commit histories or inspecting their diffs. The repositories are convenience sources: four were already present in local E2E exploration and two came from a public GitHub Playwright-config code search. Selection was based on visible framework/spec evidence, not the presence of a promising repair. No upstream repository will be mutated.

An independent `claude-fable-5` no-tool methodology pass advised freezing the repository/query window, inspecting all positions including zero-yield rows, capping correlated instances, and preserving clean controls. Its suggested numeric thresholds for accuracy claims are not accepted as statistical power calculations. This round uses six repositories as a bounded batch rather than its suggested 8–12; it will not extend this batch after seeing yield.

## Frozen search window

For each row, query GitHub's commits API with `sha=<cutoff>`, `path=<test root>`, and `per_page=25`; inspect every returned position in API order, even if it changes no spec. A row with fewer than 25 commits stays short. Do not replace, skip, or extend a low-yield repository. Commit subjects may provide context but cannot establish a defect. Do not run the product scanner or a model arm to select candidates. Existing `fixpair-v1`, `real-fix-feasibility-v1`, and `real-fix-acquisition-v2` pairs are ineligible as new cases.

| Repository | Framework | Cutoff SHA | Test-root API path | Spec extension |
| --- | --- | --- | --- | --- |
| [calcom/cal.com](https://github.com/calcom/cal.com) | Playwright | `e91bb0c38251b0ee6f87eec70ce4940822fb0cf3` | `apps/web/playwright` | `.e2e.ts` |
| [element-hq/hydrogen-web](https://github.com/element-hq/hydrogen-web) | Playwright | `ea5976e40b8d4974890e67bba3c139012044612c` | `playwright/tests` | `.spec.ts` |
| [officecli/officedex](https://github.com/officecli/officedex) | Playwright | `60d199dad7951e9ba688ec9bac2ebaf10323c752` | `e2e` | `.spec.ts` |
| [RedHatInsights/uhc-portal](https://github.com/RedHatInsights/uhc-portal) | Cypress | `5ccaadbf025ae035bf2d95a8f4716102f6e63303` | `cypress/e2e` | `.js` Cypress specs |
| [tomosterlund/qalendar](https://github.com/tomosterlund/qalendar) | Cypress | `1e81b86d45a4e34be7b7c8bc59fa17aea713d890` | `cypress/e2e` | `.cy.ts` |
| [xchem/fragalysis-frontend](https://github.com/xchem/fragalysis-frontend) | Cypress | `c5a0cd68d30fcbb34dd66dfccedd9f41fb571648` | `cypress/e2e` | `.cy.js` |

For RedHat, `.js` alone is not enough: a changed file must be shown by source/context to contain Cypress tests. If a source tree or GitHub API result is unavailable, record an incomplete row rather than replacing it. The collector must preserve all returned SHA/parent/path metadata and explicit no-spec positions.

## Admission and controls

For each changed E2E spec, compare the immediate parent and fix revision, current pattern contract, configuration, and relevant app/fixture/POM context. Admit only a narrow BEFORE defect and causally mapped AFTER repair; distinguish structural quality repairs from reproduced runtime failures. Mixed commits are not automatically excluded, but independent product/helper changes cannot be credited to the test repair without support. A merely removed code smell, commit title, green CI, or cleaner-looking AFTER is not sufficient by itself. Record rejected lookalikes and reasons, including out-of-catalog, out-of-contract, new-test-only, refactor-only, ambiguous mixed change, and independently broken BEFORE tests. The mapped AFTER slice is a control for its mechanism only, not a whole-file clean label.

Group same-cause instances in one commit into one cluster. Retain at most two clusters per repository and at most three per pattern ID across this round, in API order; record eligible-but-not-retained candidates rather than hiding them. In particular, at most one focused-test-leak cluster per repository may be retained. Independently challenge every proposed admission and disputed exclusion without scanner/model findings. Unresolved disagreements stay unresolved. Record source-backed negative controls from rejected lookalikes separately; they are not automatically fully clean specs.

Stop after these six fixed windows regardless of yield. If the round still lacks enough diverse cases, design another disclosed acquisition window *before* inspecting its commits. A later full-workflow paired comparison needs an independently held-out corpus or, for development diagnostics only, a frozen shared source scope, normal scanner-plus-semantic skill workflow, equal no-skill tools/budget, predeclared scoring, and blinded adjudication of the union of both arms' claims. Repetitions are stability checks, not more independent defects. Do not tune product rules on this public development corpus and then call it independent validation.

## Outcome

The [raw ledger](commit-ledger.json) records all **102** returned commits across the six frozen windows (25 + 5 + 20 + 25 + 24 + 3). Join repository and one-based API ordinal to the [source dispositions](adjudication.json). Every returned position was inspected, including the four zero-yield repositories. Cal.com ordinal 7 reached GitHub's 300-file response limit; its complete local parent-to-fix tree was inspected separately (4,080 changed files, including 60 under the Playwright root) before classifying it. The raw ledger retains the API truncation marker rather than pretending the API response was complete.

| Disposition | Commits |
| --- | ---: |
| Admitted narrow repair clusters | 3 |
| Eligible but not retained under the two-per-repository cap | 1 |
| Ambiguous or mixed repair, not a clean pair | 6 |
| New-test-only | 36 |
| No changed spec | 5 |
| Out of current catalog | 35 |
| Refactor-only | 8 |
| No eligible repair | 4 |
| Negative/reverse or lookalike control | 4 |
| **Total** | **102** |

The [case manifest](cases.json) pins **three** narrow BEFORE/AFTER slices across **two** repositories and **three** pattern families. A read-only independent source challenge inspected the proposed admissions and disputed exclusions without scanner/model results. It rejected two tempting initial labels and narrowed a third; it confirmed the final three as source-backed *structural* repairs, not reproduced historical failures or whole-file clean labels.

| Source fix | Admitted BEFORE → mapped AFTER | Limit |
| --- | --- | --- |
| [Cal.com `0d164da8`](https://github.com/calcom/cal.com/commit/0d164da8ddc68474300dc85677856950ef81ee7e) | `change-password.e2e.ts:21` floats `Locator.fill()` immediately before submission; AFTER line 22 awaits it (`#16/P1`). | Password-policy and fixture changes in the same commit are excluded. No race was reproduced. |
| [Cal.com `ecc5e66f`](https://github.com/calcom/cal.com/commit/ecc5e66fd4ae7034bb9eaf2fd9f99debb25ddd61) | `payment-apps.e2e.ts:316` discards `isDisabled()` as the sole intended postcondition; AFTER lines 317–318 assert PayPal checked and Stripe unchecked (`#8b/P0`). | Proves the title's mutual-exclusion outcome, not the discarded call's narrower disabled-state property. |
| [OfficeDex `361802bd`](https://github.com/officecli/officedex/commit/361802bdad7a68dacd337b7b84ab0b01e8281ac8) | `artifacts-preview-real.spec.ts:41` samples the revoked preview-token counter once after Close Preview; AFTER lines 43–46 poll it with a five-second bound (`#4c-4e/P1`). | The issued counter was already gated by visible PreviewPanel/Close Preview and is **not** a second admitted finding. No flake was reproduced. |

The source challenge also rejected RedHatInsights ordinal 14 as a clean `#10a` pair: its Page Object already targets a numeric input, while the parent test's `.get('option').first()/last()` queries cannot validate that input; the fix drops old upper-bound checks rather than preserving them. Cal.com ordinal 15 changes `count() === 0` to `toBeHidden()`, which retries but accepts an attached hidden node and thus weakens the DOM-removal condition. Cal.com ordinal 20 is a source-backed positional-selector repair, but is recorded as eligible-not-retained because ordinals 1 and 16 fill the per-repository cap. Qalendar ordinal 5 creates a Page Object during a migration; it is not an existing-ownership `#13` repair. Qalendar ordinal 1 removes sleeps but also deletes a visual snapshot, so it is not a clean `#9b` pair. RedHatInsights ordinals 18 and 20 introduce or preserve forced Cypress actions instead of repairing `#5b`; ordinal 9 changes product fixtures and expected GCP wording together rather than fixing a pre-existing `#5a` bypass. These are source-backed negative controls, not fully clean-file labels.

Together with the three [feasibility](../real-fix-feasibility-v1/README.md) and four [v2](../real-fix-acquisition-v2/README.md) clusters, this leaves **10** public development clusters, with mechanism and repository correlation. The next *development* diversity target is roughly **24–30** separately sourced clusters (14–20 more), not a statistically sufficient sample size or a requirement to keep searching until a skill lift appears. Claude Fable's no-tool methodology consultation supported fixed windows, zero-yield retention, causal source review, and caps; its suggested numeric accuracy threshold was not used as a power calculation. The stronger next test is a predeclared full-workflow paired diagnostic on the existing frozen cases with matched tools and budgets, blinded union-of-claims adjudication, and separate false-positive/negative-control reporting. A public acquisition corpus remains unsuitable as sealed release evidence. No scanner/model arm or live browser reproduction ran in this v3 round, and no product rule or scanner was changed to fit these cases.
