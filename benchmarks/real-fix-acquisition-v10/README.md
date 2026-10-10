# Real-fix acquisition v10 (older assertion/await and flaky PRs)

This is selected public-source discovery for underrepresented Playwright/Cypress reviewer rules, not prevalence sampling or a sealed evaluation. Freeze the four queries, API sort, 15-position cap, and admission policy below before querying. Use read-only `gh api` as the local fallback because `agent-reach` is unavailable. Do not mutate upstream repositories.

| Row | Exact query |
| --- | --- |
| PW-await-old | `is:pr is:merged playwright await in:title created:2020-01-01..2022-12-31` |
| PW-assert-old | `is:pr is:merged playwright assertion in:title created:2020-01-01..2022-12-31` |
| CY-assert-old | `is:pr is:merged cypress assertion in:title created:2020-01-01..2022-12-31` |
| CY-flaky-recent | `is:pr is:merged cypress flaky in:title created:2023-01-01..2026-09-30` |

Query `search/issues`, sort `created` descending, `per_page=15`, one page per row. Inspect every returned position in API order; no extensions or replacement queries after seeing the yield. A repeated PR URL is D. Exclude v1–v9 admitted repair clusters from new counts. Classify framework from actual in-scope E2E source, not title or description.

Use A/B/C/D source adjudication: A requires a natural catalog BEFORE defect, immediate parent/fix pair, and preserved promised outcome, with preimage and app/POM/config context challenged independently. B is a concrete but not closed lead; C is ineligible/control; D is a repeated PR URL. Group same-cause edits into one cluster; retain at most two A clusters per repo and two per numbered pattern in frozen API order. Do not admit #9 in this rule-diversity round. Do not use scanner/model outcomes for labels or run target-project code. Stop at the four frozen windows regardless of yield.

## Outcome

The frozen windows returned **38 distinct merged PRs**: 5 + 3 older Playwright, 15 older Cypress assertion, and 15 recent Cypress flaky-test positions. Source adjudication assigned **A 3 / B 13 / C 21 / D 1**. The read-only query snapshot is [search-ledger.json](search-ledger.json); [adjudication.json](adjudication.json) accounts for every returned position; [cases.json](cases.json) pins the admitted parent/fix sources.

| Position | Narrow source-backed repair | Catalog label |
| --- | --- | --- |
| CY-assert-old:10 | A user-edit test clicks the SuperAdmin toggle but does not check the resulting state; the fix asserts active before and not active after the same click. | #2, P1 instance |
| CY-flaky-recent:2 | A global Cypress `after(async () => ...)` hook queues `cy.task`; the fix removes `async` without changing the cleanup task. | #10d, P1 |
| CY-flaky-recent:5 | An absence-only global-spinner check after rule disablement does not establish the rule state; the fix asserts the actual switch's disabled state. | #4i, P1 |

The #4i admission is limited to the `beforeEach` check. A second spinner-absence check in that spec already has a positive alert-count counterpart and is not a second #4i instance. A Cypress one-shot `.then(expect)` to retrying `.should` repair is a real improvement but remains B: the current #4c–e contract is expressly Playwright Locator/Page shaped, consistent with v9's Eyewall boundary. One PR repeats a v8 source-adjudicated #9 case and is D; #9 remains excluded here.

The prior public development collection of 22 correlated clusters is now **25**. This selected 3/38 discovery yield does not estimate defect prevalence, scanner/model accuracy, token cost, or skill benefit. No target tests, natural failure replay, or scanner/model arm ran in v10.
