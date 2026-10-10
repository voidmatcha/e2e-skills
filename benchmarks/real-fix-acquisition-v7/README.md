# Real-fix acquisition v7 (2023–2024 title-only PR window)

Continue the [v6 title-only discovery](../real-fix-acquisition-v6/README.md) with an older date slice. Its interval is contained within v6's broad query interval, so exclude any previously admitted cluster and check returned PRs for overlap. Freeze the exact queries and review cap below before reading their results. This is selected public-source discovery, not prevalence sampling. Use read-only public GitHub through the `agent-reach` `gh` fallback; do not mutate upstream repositories.

| Row | Exact query |
| --- | --- |
| PW-old-title | `is:pr is:merged playwright flaky in:title created:2023-01-01..2024-12-31` |
| CY-old-title | `is:pr is:merged cypress flaky in:title created:2023-01-01..2024-12-31` |

Call `search/issues` with `sort=created&order=desc&per_page=20`. Inspect every returned position in API order, without extending a window after seeing its yield. Retain duplicate, no-E2E, and misleading-title positions in the ledger. Exclude this project and existing v1–v6 admitted clusters from new counts. Require TypeScript/JavaScript Playwright/Cypress E2E spec, POM, support, fixture, or config source, established by imports/calls rather than filenames or PR prose.

Keep the same tiers as v5–v6: **A** = natural, source-backed catalog BEFORE defect and immediate parent/fix repair that preserves the promised outcome; **B** = concrete diagnostic lead lacking exact catalog, causal, or preservation proof; **C** = ineligible/control; **D** = duplicate position. A squash merge's first-parent/fix may be used when the completed PR is the repair unit. Group correlated same-cause changes, and retain at most two A clusters per repo and three per pattern in API order. Independently challenge proposed A and disputed A/B boundaries with source/app/POM/config context; unresolved stays B. Do not use scanner/model output to choose labels. Stop after these two rows, regardless of yield. No target test execution or natural failure replay is implied.

## Outcome

The [frozen search ledger](search-ledger.json) returned 40 positions from 40 distinct merged PR URLs, with no URL overlap with v6's returned positions. [Per-position adjudication](adjudication.json) assigns **one strict A cluster, 27 B diagnostic leads, and 12 C controls**; there are no repeated-position D rows. The one [pinned case](cases.json) increases the selected public development collection from 15 to **16 correlated clusters**. This is not a prevalence estimate or measured reviewer lift.

The admitted [Bichard trigger-resolution repair](https://github.com/ministryofjustice/bichard7-next-core/pull/1153) replaces an uncommented Cypress `.first()` checkbox action with a PR01-specific trigger-code selection, then selects PR02 explicitly. The unchanged assertions still require PR01 and PR02 resolution notes. Source shows trigger ordering is not guaranteed to put PR01 first. An independent challenge confirmed this narrow #10a repair against the immediate parent/fix pair and the app changes that supply the new row selector. Another `.first()` in a sibling test remains; the after-file is not labeled clean.

Several plausible repairs correctly remain B. [OpenMetadata](https://github.com/open-metadata/OpenMetadata/pull/18984) moves a response listener before the action, but missed-response ordering is outside the current 24-pattern catalog. [Immersion Facilitée](https://github.com/Immersion-Facilitee/immersion-facile/pull/2506) waits for a dynamic option before selection, also outside that catalog. [Emojicoin](https://github.com/econia-labs/emojicoin-dot-fun/pull/322) still contains the same unawaited Playwright matcher defect (#15) after its flake work. [CARE](https://github.com/ohcnetwork/care_fe/pull/9148) removes a fixed wait but also deletes the unlink/relink behavior the test promised, so it is not an outcome-preserving #9 repair. Related backports, cherry-picks, and sister-repository patches are controls or contextual leads rather than extra independent cases.

The 1/40 strict yield is a property of these title-selected PR windows only. No upstream tests, natural failure replay, scanner arm, or model arm ran. The pinned case is public development evidence, not a sealed holdout. Stop at the frozen two windows.
