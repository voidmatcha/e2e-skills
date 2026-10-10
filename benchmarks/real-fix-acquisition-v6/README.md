# Real-fix acquisition v6 (older title-only PR window)

This round tests a different discovery surface after [v5](../real-fix-acquisition-v5/README.md): older merged PRs with *flaky* and the framework name in the **title**, rather than recent PRs whose body mentions those words. Freeze the two queries, order, cap, and admission policy below before reading search results. The result is a selected discovery sample, not a prevalence estimate. Public GitHub is read through the `agent-reach` `gh` fallback; never mutate an upstream repository.

| Row | Exact query |
| --- | --- |
| PW-title | `is:pr is:merged playwright flaky in:title created:2023-01-01..2025-12-31` |
| CY-title | `is:pr is:merged cypress flaky in:title created:2023-01-01..2025-12-31` |

Use `search/issues`, `sort=created&order=desc&per_page=20`. Inspect every returned position, including no-E2E, new-test-only, and misleading title cases; do not extend a row after seeing its yield. A repeated PR is owned by its first position. Source-file presence, not the PR title, establishes Playwright/Cypress E2E scope. Exclude this project and previously admitted v1–v5 repair clusters from *new* A counts, retaining them as duplicates/controls if returned.

The v5 three-tier decision applies unchanged: **A** is a natural, source-backed catalog BEFORE/AFTER repair preserving the promised outcome, pinned to the relevant commit's immediate parent/fix or a squash merge's first parent/fix; **B** is a concrete diagnostic lead that misses a catalog, causal, or outcome-preservation requirement; **C** is ineligible or a negative control. Retain at most two A clusters per repository and three per pattern in API order. Group same-cause PR edits as one cluster. Challenge every proposed A against the actual preimage, app/POM/config/fixture context, and unchanged pattern contract; unresolved A/B boundaries stay B. Do not run the scanner or a model to select source labels. Stop after both frozen rows, regardless of yield; no target tests or natural failure reproduction are implied.

## Outcome

The [frozen search ledger](search-ledger.json) contains 40 positions from 40 distinct merged PRs. The [per-position adjudication](adjudication.json) assigns two strict A clusters, 21 B diagnostic leads, and 17 C ineligible/negative-control positions. The two [pinned cases](cases.json) both come from TypeScript Playwright tests and survived an independent source challenge. The public development collection grows from 13 v1–v5 clusters to **15 correlated clusters**; no model/scanner outcome is inferred.

| Admitted cluster | Narrow source-backed repair |
| --- | --- |
| [ComfyUI background-image upload](https://github.com/Comfy-Org/ComfyUI_frontend/pull/7389) | #4: one-shot `inputValue()`/regex assertion becomes awaited `toHaveValue()` on the same input with the identical regex. |
| [CARE prescription creation](https://github.com/ohcnetwork/care_fe/pull/14587) | #9c: `waitForLoadState('networkidle')` after opening the form becomes a web-first visibility assertion on the exact Add Medication control used next. |

The independent challenge prevented two plausible Playwright admissions: [Digicatapult](https://github.com/digicatapult/dtdl-visualisation-tool/pull/451) awaits a previously floating matcher but also weakens computed-color proof to class membership, while [HyperDX](https://github.com/hyperdxio/hyperdx/pull/1398) adds a retrying value guard but retains the one-shot comparison. On Cypress, [DataHub](https://github.com/datahub-project/datahub/pull/15331) splits an action chain into fresh queries, but inspected editor code does not establish the subject-instability risk required by #10f; it remains a disputed B lead. [Playnite Web](https://github.com/andrew-codes/playnite-web/pull/885) improves intercept timing, but existing reload-based persistence proof and a non-optimistic mutation path refute a #22 label. These boundaries are recorded in the adjudication file rather than inflated into A cases.

The title-only search was richer in relevant code than the v5 body-inclusive search, but its 2/40 strict yield is a *selected-source yield*, not a real-world defect rate. Python/.NET Playwright repairs, backports, dropped suites, and longer fixed sleeps were retained as controls, not silently counted. No target tests, natural failure replay, scanner arm, or model arm ran. The new public cases are development evidence only, not a sealed holdout or a measured skill lift. Stop at the frozen two windows.
