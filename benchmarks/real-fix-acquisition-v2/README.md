# Real-fix acquisition v2 (development search)

This is a source-first search for additional natural Playwright/Cypress E2E repairs. It is **not** a sealed holdout, a skill/no-skill score, or evidence of generalized product lift. The search boundary and disposition rules below were written before reviewing the listed commits' diffs or running either benchmark arm. The four repositories were already present as shallow local checkouts from earlier POM exploration, so they are convenient development sources rather than a random sample. The public GitHub commits API is read through the project's `agent-reach` GitHub fallback (`gh`); no upstream repository is mutated.

## Frozen acquisition boundary

For each row, query GitHub's commits API with `sha=<cutoff>`, `path=<path>`, and `per_page=25`. Inspect the resulting **first 25 commits in API order**, including non-spec changes and unusable commits; do not skip past them to fill a quota. Inspect changed-file metadata and source only after this boundary is fixed. The path, not a fix keyword or a previously missed pattern, selects commits. If an API response is unavailable, record the gap rather than replacing the repository. Existing `fixpair-v1` commits and the three `real-fix-feasibility-v1` clusters are ineligible as new cases.

| Repository | Framework | Local HEAD cutoff | API path |
| --- | --- | --- | --- |
| [OHIF/Viewers](https://github.com/OHIF/Viewers) | Playwright | `f06cf8b309551325038a80d38c2ec94af81d79ae` | `tests` |
| [ever-co/ever-gauzy](https://github.com/ever-co/ever-gauzy) | Playwright | `54b537baf8755924eb11f0505b99c304e6b44c8a` | `apps/gauzy-e2e/tests` |
| [harvester/tests](https://github.com/harvester/tests) | Cypress | `fe06844ce0f38a4b3a438085c436dad3c51e464c` | `cypress/testcases` |
| [omegaup/omegaup](https://github.com/omegaup/omegaup) | Cypress | `26730787a588243308602da544f5be2fc009ceff` | `cypress/e2e` |

Record all 100 commit SHAs and dispositions, including no-spec-change, new-test-only, out-of-catalog, ambiguous, and eligible. A spec change is eligible only when its immediate parent and fix commit, relevant app/fixture/config context, and the exact reviewer pattern contract establish a BEFORE defect mechanism and a mapped AFTER repair. Commit subjects and scanner/model answers are not labels. Mixed product/test commits, independently broken parent tests, and unreproduced race claims require explicit qualification; they cannot silently become clean behavioral fix pairs. Group correlated rule instances into one causal cluster. Retain at most two source-adjudicated clusters per repository in API order, but inspect all 25 commits regardless of early yield. The mapped AFTER slice is a control only for the changed mechanism, not a whole-file clean label.

Before any model run, an independent reviewer should receive source, config, and pattern contracts without scanner or model outputs. Preserve disagreement as unresolved. For report precision, independently adjudicate the union of both arms' findings, including unanticipated claims. A later full-workflow comparison must freeze skill bytes, corpus, prompts, tools, model/effort, schedule, scoring, and usage fields in advance and give both arms identical source scope. The skill arm must execute its normal read-only scanner and semantic workflow; this search alone is not that validation.

## Search ledger and outcome

The [raw commit ledger](commit-ledger.json) contains all 100 API positions, their SHAs, parents, changed-spec paths, and initial path classification. Join its repository name and one-based ordinal to the [source-adjudicated dispositions](adjudication.json); the raw collector's `pending-source` values are deliberately not rewritten after source review. The [admitted case manifest](cases.json) pins the four narrow BEFORE/AFTER slices and their representative spec blobs. All 25 commits in each repository were inspected. A separate read-only Astra challenge checked the four admissions against upstream source, config, and current rule contracts without seeing scanner or model outputs; it confirmed their *narrow* labels, not historical runtime failure or whole-suite repair.

| Disposition | Commits |
| --- | ---: |
| Admitted source-backed repair clusters | 4 |
| Eligible but not retained (duplicate focus-leak mechanism) | 2 |
| Ambiguous or mixed repair, not a clean pair | 4 |
| New-test-only | 27 |
| No changed spec | 27 |
| Out of current catalog | 27 |
| Out of current contract | 1 |
| No eligible repair | 8 |
| **Total** | **100** |

The admitted four are **three mechanism families across three repositories**, not four independent rule types. OHIF's five modified specs count as one hydration/count cluster. Harvester and omegaUp each contribute an `it.only` leak, but those are correlated `#7` examples. ever-gauzy yielded no changed `*.spec.ts` in this fixed window; its BDD steps and page objects were not silently treated as specs.

| Source fix | BEFORE → mapped AFTER | Adjudication boundary |
| --- | --- | --- |
| [OHIF `95200ec6`](https://github.com/OHIF/Viewers/commit/95200ec6e896a7e94f0884b9872c4fe1aa36ad7d) | `tests/ContourSegmentDelete.spec.ts:23-24` reads a segment count once and synchronously asserts `4`; AFTER line 23 uses retrying `toHaveCount(4)` on rows (`#4c-4e/P1`). | Parent POM explicitly deprecates the count helper as racing render; the hydration code schedules work after the confirmation click. Five same-mechanism specs are one cluster. No flake was reproduced. |
| [Harvester `789c3624`](https://github.com/harvester/tests/commit/789c36248713263a4a849c37da227b942818c5fb) | `cypress/testcases/settings/settings.spec.ts:65` changes `it.only` to `it` (`#7/P0`); four sibling tests existed before. | Only the focus removal is admitted from a mixed commit. Historical CI impact is unproven. |
| [omegaUp `ec389179`](https://github.com/omegaup/omegaup/commit/ec38917953a9587f19a7424873e84dca40200258) | `cypress/e2e/ide.cy.ts:37` uses `cy.wait(1000)`; AFTER lines 40-42 retry until the generated zip link has a nonempty `href` (`#9b/P1`). | App source asynchronously generates the zip before setting that `href`. Other WebSocket changes in the commit are excluded; no timing failure was reproduced. |
| [omegaUp `a17f45c9`](https://github.com/omegaup/omegaup/commit/a17f45c9c0ca5cd2301d9d3c526822b85a7149d9) | `cypress/e2e/basic_commands.cy.ts:85` changes `it.only` to `it` (`#7/P0`), restoring sibling-test eligibility. | Separate helper changes are excluded; mechanism overlaps the Harvester case. Historical suite impact is unproven. |

The `context.only` removal at Harvester API position 7 is a useful rejected boundary: Cypress can focus a suite that way, and the scanner appears to recognize it, but the current `#7` pattern contract explicitly names `it`, `test`, and `describe` globals, not `context`. We record it as **out-of-contract**, not a conveniently added gold label. That contract/scanner discrepancy deserves its own general product review with negative guards; this public search must not silently expand the rule.

## Decision and next validation

This search supplies additional source-backed *development* examples, including a retrying count repair and a condition-based Cypress wait. It does not establish a skill advantage, a recall percentage, or a release-grade score. No scanner/model benchmark arm ran in this round, and no skill or scanner bytes were changed to fit the discoveries.

The next useful validation is a predeclared **full-workflow paired diagnostic** on a more diverse source set: equal source scope and host/model budget, normal scanner-plus-semantic workflow in the skill arm, independently adjudicated union of both arms' findings, mapped AFTER controls, and separate reporting for the three mechanism families and correlated focus cases. The four public cases here can be development checks, not sealed evidence. Before claiming generalization, acquire cases from new repositories under another fixed window, including clean guards and mechanisms beyond focus, fixed sleeps, and one-shot reads; record zero-yield windows as faithfully as this one. Do not tune the product or expand the source window in response to a model miss.
