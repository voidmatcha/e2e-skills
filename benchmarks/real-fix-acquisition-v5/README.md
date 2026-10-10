# Real-fix acquisition v5 (PR-enriched public development search)

This round changes the **discovery method**, not the gold admission standard, after the low-yield [v4 fixed-history search](../real-fix-acquisition-v4/README.md). It is deliberately enriched for PRs that discuss Playwright/Cypress test flakiness or assertions, so neither its yield nor its findings estimate prevalence. The query, order, row cap, tiers, and stop rule below were frozen before querying results or inspecting any PR diff. Public GitHub is read through the adapted `agent-reach` `gh` fallback; no upstream repository is mutated.

## Frozen search and review window

Use GitHub's `search/issues` API for each exact query below, `sort=created&order=desc&per_page=20`, and inspect every returned PR position in the order listed. The search date applies to PR creation, not merge. A row with fewer than 20 stays short. Do not skip a low-yield PR or extend a query after seeing its result. PRs that appear in multiple rows are inspected at their first occurrence and recorded as duplicates in later rows. Exclude this project's own PRs from admission, but retain them in the search ledger if returned. Require public Playwright/Cypress E2E spec, POM, support, or configuration source; names, titles, labels, and self-reported fixes are only leads.

| Row | Exact GitHub search query |
| --- | --- |
| PW-flaky | `is:pr is:merged playwright flaky in:title,body created:2025-01-01..2026-09-30` |
| CY-flaky | `is:pr is:merged cypress flaky in:title,body created:2025-01-01..2026-09-30` |
| PW-assertion | `is:pr is:merged playwright assertion in:title,body created:2025-01-01..2026-09-30` |
| CY-assertion | `is:pr is:merged cypress assertion in:title,body created:2025-01-01..2026-09-30` |

## Three separate disposition tiers

1. **A — strict natural repair pair:** source-backed catalog BEFORE defect and causally mapped AFTER repair that preserves the promised outcome. Use the relevant PR commit's immediate parent/fix revision, or the merge commit's first parent/fix when the PR was squash-merged; pin blob IDs and exact lines. App/config/fixture/POM context must exclude a merely renamed product contract, broken setup, or weakened assertion. This is the *only* tier that increments the 11 public development fix clusters from v1–v4. It is still not sealed validation or reproduced failure.
2. **B — diagnostic lead:** source-backed changed E2E test where a plausible catalog issue remains unresolved, the AFTER changes or drops some verification, or the actual repair is outside the current 24-pattern catalog. Preserve concrete evidence and the reason A failed; do **not** silently convert B to benchmark gold or tune product rules to it.
3. **C — ineligible/control:** new tests only, no in-scope test diff, product/UI wording adaptation, opaque external-suite replacement, duplicate PR, or source disproves the presumed defect. Retain strong lookalikes as negative controls, not clean-file labels.

Group same-cause edits in a PR into one cluster. Retain at most two A clusters per repository and at most three per pattern across this round, in search/API order; record eligible-but-not-retained rows. Existing v1–v4 cases are not new cases. Independently challenge all proposed A admissions and disputed A/B boundaries without scanner/model outputs. Unresolved cases stay B. Stop after the four fixed windows regardless of yield. A later paired benchmark must predeclare a separate source scope, normal skill workflow and equal no-skill tools/budgets, union-of-claims adjudication, and its selected-case/public-corpus limits before model calls.

## Outcome

The [frozen search ledger](search-ledger.json) contains all 80 returned positions from four 20-PR windows, representing 78 unique PRs. The [per-position adjudication](adjudication.json) classifies two strict A repair clusters, 15 B diagnostic leads, 61 C ineligible/control positions, and two duplicate positions. The two A cases are pinned with immediate parent/fix revisions, blob IDs, and causal limits in [cases.json](cases.json). Both were challenged against the exact pattern contract and source context; the DataHub case had an independent source challenge. The public development collection therefore grows from 11 to **13 correlated clusters**, not 13 independent failures or a release validation set.

| Strict case | Narrow conclusion | Important limit |
| --- | --- | --- |
| [Iliaduda market clock](https://github.com/dudailia/iliaduda-site/pull/3) | Playwright #4c–#4e: a one-shot attribute/threshold comparison becomes a bounded `expect.poll` with the same threshold. | The enclosing test still has a GPU-availability skip and an unrelated setup sleep; this is not a whole-spec fix. |
| [DataHub lineage replacement](https://github.com/datahub-project/datahub/pull/20099) | #1: a test promising historical replacement gains complementary absence assertions on the time-filtered main list, after same-response presence proves readiness. | One correlated PR cluster, not separate credit for four removed sleeps or adjacent lineage edits. The four-commit PR is compared as its completed squash-merge first-parent/fix pair. |

The changed discovery method also surfaced useful **non-gold** examples. [Invoicerr](https://github.com/invoicerr-app/invoicerr/pull/573) repaired a genuine Cypress flake caused by a clamped paragraph, but its original visibility assertion was already retrying and the repair adds a different status check; it is not #4. [Metabase](https://github.com/metabase/metabase/pull/83346) changed a one-shot Cypress geometry check to a retrying `.should()` callback, but the explicit #4c–#4e subcontract is Playwright-specific. [DPL Web](https://github.com/danskernesdigitalebibliotek/dpl-web/pull/1811) replaced Cypress `.eq(1)` with labels, while the current #10a contract covers `nth`/`first`/`last`, not `.eq`. These are leads for a separately justified rule-boundary decision, not permission to relabel the current catalog after observing the result. Other B examples and their reasons are in the adjudication file.

This search intentionally selected recent PRs whose title/body contains both a framework name and a flake/assertion term. It therefore says nothing about real-world prevalence or how often a model would detect or repair these cases. No target test, scanner arm, model arm, or natural failure replay ran in this acquisition; PR-authored test claims were not independently reproduced. The public cases remain development evidence, not a sealed holdout. Stop here rather than extend a low-yield window after seeing its results.
