# Real-fix acquisition v8 (repair-language PR search)

This is a source-first development-corpus search, not prevalence sampling or a sealed evaluation. The v6–v7 title-only `flaky` windows found few strict catalog repairs. Before querying, fix the four repair-language searches below, their API order and 15-position cap. Unlike those rounds, these searches deliberately target likely fixes; compare only source-backed admission counts, not yields as if the sampling frames matched. Public GitHub is read through the read-only `gh` fallback because `agent-reach` is unavailable locally. Never mutate upstream repositories.

| Row | Exact query |
| --- | --- |
| PW-await | `is:pr is:merged playwright "missing await" created:2023-01-01..2026-09-30` |
| PW-retry | `is:pr is:merged playwright "waitForTimeout" flaky created:2023-01-01..2026-09-30` |
| CY-order | `is:pr is:merged cypress "first()" flaky created:2023-01-01..2026-09-30` |
| CY-sleep | `is:pr is:merged cypress "cy.wait" flaky created:2023-01-01..2026-09-30` |

Use `search/issues` sorted by `created` descending, `per_page=15`, one page per row; inspect every returned position in API order. Do not add searches after seeing the yield. Deduplicate against all v1–v7 admitted clusters and across rows; a repeated PR URL is D, a unique backport or correlated sister-repository patch is a C control or contextual B, not D. Require actual TypeScript/JavaScript Playwright/Cypress E2E spec, POM, support, fixture, or config code by imports/calls, not title or PR prose.

Use the same A/B/C/D decision as v7. **A** requires a natural catalog BEFORE defect, immediate parent/fix repair, and preserved promised outcome, all established from source and exact per-pattern contract. **B** is a concrete lead missing catalog, causal, or preservation proof; **C** is ineligible/control; **D** repeats a PR URL. Group same-cause edits into one cluster, allow at most two A clusters per repo and three per pattern in API order, and independently challenge every proposed A against preimage, app/POM/config context, and unchanged test assertions. Unresolved remains B. Neither scanner/model output nor target test execution selects labels. Stop after these four windows regardless of yield.

## Outcome

The [frozen search ledger](search-ledger.json) returned 60 positions from 60 distinct merged PR URLs, with no overlap against previously admitted v1–v7 PRs. [Per-position adjudication](adjudication.json) assigns **3 admitted A clusters, 10 B diagnostic leads, and 47 C controls**, with no repeated-URL D positions. The three [pinned cases](cases.json) increase the selected public development collection from 16 to **19 correlated clusters**. This is not a prevalence estimate or measured reviewer lift.

All three admissions are narrow Playwright **#9 fixed-sleep** repairs, independently challenged against the exact immediate parent/fix source:

| Admitted cluster | Preserved outcome |
| --- | --- |
| [Versicle reader readiness](https://github.com/vrwarp/versicle/pull/1694) | A two-second sleep becomes awaited reader-engine readiness and current-location checks; annotation round-trip assertions remain. |
| [Melosys institution options](https://github.com/navikt/melosys-e2e-tests/pull/354) | A tolerated response wait plus 500 ms sleep becomes a hard assertion that the requested or fallback option is attached; selection and missing-option failure remain. |
| [Cellar kernel probes](https://github.com/fbereilh/cellar/pull/130) | A one-second setup sleep becomes observed request settlement before probe counters reset; the batch and probe-count assertions remain. |

The predeclared **three-per-numbered-pattern** cap fills at the third Playwright case in API order. Two later Cypress #9b repairs were independently source-confirmed but are recorded as *eligible over cap*, not extra admissions: [Group Income](https://github.com/okTurtles/group-income/pull/3172) waits for saved draft state instead of one-second sleeps, and [Motion](https://github.com/motiondivision/motion/pull/3836) retries the same unit-conversion outcomes instead of post-click fixed sleeps. These are useful leads for a future balanced corpus, but adding them here would break the frozen cap. A third [Frappe](https://github.com/frappe/release_tests/pull/3) wait replacement remains B: its first replacement makes a popup-location assumption revised by a later commit, and the source does not prove exact selected-value preservation.

The search was **not especially precise**: GitHub's issue search matched many PRs without an existing in-scope E2E repair, despite the repair-language queries. The 3/60 admitted yield and five source-confirmed #9 repairs are properties of this deliberately selected window, not a random sample. The extra cases strengthen #9 development examples but **do not diversify the 24-pattern evidence** or establish whether the reviewer detects them. No target tests, natural failure replay, scanner arm, or model arm ran. Stop at these four frozen windows.
