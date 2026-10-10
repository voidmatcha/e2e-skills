# Real-fix acquisition v4 (public development search)

This is a second source-first search after [v3](../real-fix-acquisition-v3/README.md), not a model/scanner evaluation or sealed release holdout. The eight repositories below were selected from public GitHub configuration-code search before querying their test-root commit histories or inspecting any repair diffs. Selection required current Playwright/Cypress configuration and an existing E2E spec root with actual specs. The repository mix intentionally includes different products and both supported frameworks; it is a convenience sample, not random sampling. No upstream repository is mutated.

## Frozen window

Query the GitHub commits API for each row with `sha=<cutoff>`, `path=<root>`, and `per_page=25`. Inspect every returned position in API order, even if the root changed only helpers or yielded no eligible spec edit. Never extend a row to fill a candidate quota. If an API file list is truncated, resolve it from the same parent/fix tree or mark that row incomplete. Do not replace an inaccessible or zero-yield repository after observing its history.

| Repository | Framework | HEAD cutoff | Test-root API path | Spec boundary |
| --- | --- | --- | --- | --- |
| [mtlynch/whatgotdone](https://github.com/mtlynch/whatgotdone) | Playwright | `ef10be2a9f8a57c35f67d299a4c0ef374e768e04` | `e2e` | `*.spec.ts` under configured `testDir` |
| [RedHatInsights/patchman-ui](https://github.com/RedHatInsights/patchman-ui) | Playwright | `9b6bac02e02373d6a8ad99a1920b19ab1fd23979` | `playwright` | `*.spec.ts` under `Integration/` or `UI/` projects |
| [xmlui-org/xmlui](https://github.com/xmlui-org/xmlui) | Playwright | `e4e2bc10dadb630105fc4d33f4f8b59cf3a30ea3` | `xmlui/tests-e2e` | `*.spec.ts` in package-configured E2E project |
| [godotlauncher/launcher](https://github.com/godotlauncher/launcher) | Playwright | `e26cdb8daf289aada48b9e57e58bdbe02f681c3a` | `e2e` | `*.spec.ts` under configured `testDir` |
| [verdaccio/verdaccio](https://github.com/verdaccio/verdaccio) | Cypress | `8f877d52abb8f37f3b4eacd7917dad8299544034` | `cypress/e2e` | `*.cy.ts` per `specPattern` |
| [victronenergy/venus-html5-app](https://github.com/victronenergy/venus-html5-app) | Cypress | `61f4dd8c6f339a4ec025d3af4d39a90cb81c4ea7` | `cypress/e2e` | `*.spec.ts` within `specPattern: **/*.{js,jsx,ts,tsx}`; prove `cy` usage |
| [wikimedia/wikidata-query-builder](https://github.com/wikimedia/wikidata-query-builder) | Cypress | `d2b960af9b6417ce2c9c32d224671d5988d5ad37` | `cypress/e2e` | `*.cy.js` using Cypress commands |
| [ministryofjustice/hmpps-contacts-ui](https://github.com/ministryofjustice/hmpps-contacts-ui) | Cypress | `aee67b0a2d258ba03d508cea0f4f8372772388eb` | `integration_tests/e2e` | `*.cy.{js,jsx,ts,tsx}` per `specPattern` |

## Source admission

Use the immediate parent and fix source, the exact current `e2e-reviewer` pattern contract, and relevant app/config/fixture/POM context. A changed test must have a source-backed BEFORE defect and a mapped AFTER repair that preserves the promised verification; structural risk is not a reproduced runtime failure. Commit subject, scanner hit, model judgment, and attractive AFTER syntax are not labels. Group same-cause edits within a commit as one cluster. Retain at most two clusters per repository and at most three per pattern across this v4 round, in API order; record later eligible examples rather than replacing earlier ones. Existing v1–v3 cases are not new cases. Preserve meaningful rejected lookalikes as negative controls without assuming whole-file cleanliness. Independently challenge admissions and disputed exclusions from source before freezing cases. No product rule or scanner change will be fitted to this public search.

The round stops after these eight fixed windows. Further expansion requires a new disclosed boundary before seeing its commit histories. The goal is diversity for a development diagnostic, not a magic case count or a release-grade precision estimate. A proper later paired evaluation must freeze inputs, tools, budgets, model/host identities, scoring, and union-of-claims adjudication before model calls.

## Outcome

The [raw ledger](commit-ledger.json) is `COMPLETE`: **147** returned commits (25 + 25 + 25 + 25 + 3 + 1 + 18 + 25). All positions were source-reviewed; the [disposition ledger](adjudication.json) joins by repository and one-based API ordinal. The sole GitHub changed-file list that reached the 300-file limit was Godot ordinal 12. A separate [paginated resolution](file-list-resolution.json) found all 426 changed files across five nonempty pages and all seven in-scope specs on page 1; its sixth page was empty. The raw ledger deliberately retains the original API truncation marker.

| Disposition | Commits |
| --- | ---: |
| Admitted narrow source-backed repair | 1 |
| New-test-only | 39 |
| No changed in-scope spec | 15 |
| Out of current catalog | 70 |
| Refactor-only | 8 |
| Ambiguous or mixed repair | 7 |
| Negative lookalike or reverse direction | 7 |
| **Total** | **147** |

The sole admitted [case](cases.json) is [XMLUI `2807bff4`](https://github.com/xmlui-org/xmlui/commit/2807bff4afafe5696257b7c53ed848a6808ab29c), parent `f5c47a05`: `xmlui/tests-e2e/how-to-examples/preserve-tree-state-across-data-refreshes.spec.ts:54` uses `page.waitForTimeout(50)` after setting the Tree scroller to the bottom. AFTER lines 15–21/62 poll the *same scroll surface* until its `scrollTop` becomes nonzero (`#9/P1`). The original delete, disappearance, success-message, and <=1-pixel scroll-delta checks remain. Source review and a separate read-only challenge confirmed the narrow fixed-delay replacement. The poll does **not** prove exact bottom position or full scroll-event settlement; the large feature commit also changes app behavior, and no historical flaky failure was reproduced.

Several superficially appealing repairs were rejected on source context:

- Godot ordinal 22 deletes two sleeps **and** the intervening delayed-open/cancelled-open assertions. Its unchanged tooltip implementation has a 500ms open timer and cancels on pointer leave. Later visibility checks do not preserve those temporal promises, so this is not a clean `#9` pair.
- Venus ordinal 1 comments out the numeric-value and screenshot tests when migrating Cypress files. The sleeps disappear only because their verification stops running; this is not a `#9b` repair.
- whatgotdone ordinal 12 changes `toHaveCount(0)` to `not.toBeVisible()`: it does not prove a locator can match for `#4i` and weakens exact DOM absence.
- patchman-ui ordinal 1 adds nonempty waits before intentionally capturing table-cell baselines. That is useful readiness hardening but not the current `#4c-4e` one-shot-assertion shape. Its positional locator is only moved to a scoped `.first()`, not removed as `#10a`.
- Wikimedia ordinal 10 separates `cy.type().wait('@alias')`. The wait observes an intercepted request and the next action begins with a fresh query, so the current `#10f` stale-subject continuation contract is not established by the lint-rule title.
- Ministry of Justice ordinal 24 adds a missing stub for an unconditional page-load **read**. It is not an unmocked persistent write (`#20`) or fixture violating a render guard (`#23`).
- Verdaccio ordinal 3 replaces local Cypress suites with wrappers around an external suite package. Old sleeps and async hooks vanish from the repository, but the new package's equivalent workflows are not source-closed here, so deletion alone is not a fix pair.

The eight-repository v4 window yielded only **one** admission; seven zero-yield rows remain in the denominator. Together with the three feasibility, four v2, and three v3 clusters, there are now **11** correlated public development clusters. This does not measure prevalence, reviewer recall/precision, skill lift, or release readiness. No scanner or model arm ran in this round; no product rules were changed to fit the discovered case. The observed low yield suggests a future *separately disclosed* search over issue/PR-linked test-quality fixes may be more efficient than another convenience-repository recent-history window, but any such search must freeze its query/window before reading fixes and must report its selection bias.
