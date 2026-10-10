# Real-fix acquisition v9 (non-sleep rule search)

This is selected public-source discovery for underrepresented reviewer rules, not prevalence sampling or a sealed evaluation. [v8](../real-fix-acquisition-v8/README.md) found additional #9 repairs but no rule diversity. Freeze the four title-only searches, API order, 15-position cap, and admission policy below before querying. GitHub is read through the read-only `gh` fallback because `agent-reach` is unavailable locally; do not mutate upstream repositories.

| Row | Exact query |
| --- | --- |
| PW-await-title | `is:pr is:merged playwright await in:title created:2023-01-01..2026-09-30` |
| PW-assert-title | `is:pr is:merged playwright assertion in:title created:2023-01-01..2026-09-30` |
| CY-selector-title | `is:pr is:merged cypress selector in:title created:2023-01-01..2026-09-30` |
| CY-assert-title | `is:pr is:merged cypress assertion in:title created:2023-01-01..2026-09-30` |

Call `search/issues`, sorted by `created` descending, `per_page=15`, exactly one page per row. Inspect every returned position in API order, even if the title is misleading; do not extend a row or add searches after seeing the yield. A repeated PR URL is D. Unique backports and sister-repository copies are contextual B or C, not D. Exclude v1–v8 admitted repair clusters from new counts. Determine Playwright/Cypress from actual TypeScript/JavaScript E2E spec, POM, support, fixture, or config imports/calls, not titles or PR descriptions.

Use the same A/B/C/D source standard as v8, but **do not admit numbered pattern #9** in this round. A requires a natural catalog BEFORE defect and immediate parent/fix repair preserving the same promised outcome. B is a concrete but not closed lead; C is ineligible/control; D repeats a PR URL. Group same-cause edits into one cluster; retain at most two A clusters per repo and two per numbered non-#9 pattern in frozen API order. Read the exact per-pattern contract and independently challenge every proposed A with preimage and app/POM/config context. Unresolved stays B. Do not use scanner/model outcomes to select labels or run tests in upstream checkouts. Stop after four windows regardless of yield.

## Outcome

The frozen windows returned **60 distinct merged PRs**. Source adjudication assigned **A 3 / B 10 / C 47 / D 0**; all positions and boundary reasons are in [adjudication.json](adjudication.json), with the read-only query snapshot in [search-ledger.json](search-ledger.json). The three admitted, independently challenged source pairs in [cases.json](cases.json) span three repositories and two numbered patterns:

| Position | Natural BEFORE defect and preserving repair | Catalog label |
| --- | --- | --- |
| PW-await-title:2 | A promised `lastError` was stringified, making its no-error predicate invariant; the fix awaits the real value before the same assertion. | base #4, P0 |
| PW-await-title:4 | A Playwright settings-menu `click()` floated without `await`; the fix awaits that same action before the unchanged destination assertion. | #16, P1 |
| CY-assert-title:8 | A Cypress sort check omitted its column index, extracting all-zero arrays that always matched their sorted copies; the fix passes the index and preserves the ascending/descending checks. | #4a, P0 |

The independent challenge kept plausible lookalikes out: the DataGrok custom canvas poll and a Cypress `.then()`-to-`.should()` repair do not match the current explicit Playwright Locator/Page one-shot subrule; a Cypress `.first()` repair retained its positional selector and changed an asserted dependency target. These are diagnostic leads, not extra admitted patterns. #9 repairs were intentionally excluded by this round's frozen scope.

The prior public development collection of 19 correlated clusters is now **22**. This selected 3/60 source-discovery yield does not estimate defect prevalence, scanner/model accuracy, or skill benefit. No upstream test execution, natural failure replay, or scanner/model arm ran in this round; runtime effectiveness remains unmeasured.
