# Official framework skills: exploratory local pilot (2026-10-03)

This is a **one-run development pilot**, not a release benchmark or a claim that one bundle beats another. The official skills were installed only in a temporary directory, not globally: Microsoft [`playwright-cli`](https://github.com/microsoft/playwright-cli/tree/b85c7a736bb473bf55b584e54a09ffa698d6d871/skills/playwright-cli) and [`playwright-trace`](https://github.com/microsoft/playwright/tree/c2a031e77ff65a2b230c09500346bce2ee64e02f/packages/playwright-core/src/tools/skills/playwright-trace), and Cypress [`cypress-explain`, `cypress-author`, and `cypress-tap`](https://github.com/cypress-io/ai-toolkit/tree/da6ea17dfa674a2b68908d823e37f5797d5be238/skills). The last two Cypress skills were installed but not scored: this bundle has no Cypress authoring skill, and the pilot had no compatible running `cypress open` session for `cypress-tap`.

For this three-task pilot, all counted calls used Codex CLI 0.159.3, `gpt-6-sol`, one fresh session per arm and case, identical task text except the skill path, host skill discovery disabled, and no test-repository edits. Input-token counts include cached context and are **not** billable-token or end-to-end cost estimates. There was no preregistration, blinded human adjudication, replication, or sealed corpus. Raw model responses and full event logs were not committed; the excerpts below and the cited source files support only a local exploratory reading.

| Comparable task | Official skill | This bundle | Counted input tokens (official / ours) | Result |
| --- | --- | --- | ---: | --- |
| Review the optimistic-edit Cypress test in the [refine #22 pair](../semantic-mutants-v1/batches/s3/corpus.json), defect and original | `cypress-explain` | `e2e-reviewer` | 447,751 / 1,094,487 | Both found the removed PATCH-proof gap in the defect. Both raised a *different* optimistic-UI-coverage concern in the original; that concern was not adjudicated as an error or a clean-control false positive. Our finding used the causal submit line; the official finding cited the later redirect line. |
| Diagnose one locally produced Playwright failure (`#submit-btn` absent from a `data:` fixture; trace on) | `playwright-trace` | `playwright-debugger` | 158,715 / 129,952 | Both identified the selector mismatch as a test defect and noted that fixing it alone leaves the fixture without a submit handler or success message. One synthetic failure cannot establish diagnostic superiority. |
| Explore the local [todo app](../../scripts/evals/generator-live/writescope-demo/README.md) and **propose only** add, complete, and empty-title scenarios | `playwright-cli` | `playwright-test-generator` | 260,462 / 931,446 | Both explored the browser and proposed all three scenarios. Our proposal additionally required a reload before claiming persistence or absence of a stored todo; the official proposal stayed with immediate UI and count checks. Neither wrote or ran tests, so generated-test correctness was not measured. |

The Playwright fixture used for the diagnosis was:

```js
await page.goto('data:text/html,<main><button data-testid="submit-order">Submit order</button><p>Ready</p></main>')
await page.locator('#submit-btn').click({ timeout: 1500 })
await expect(page.getByText('Order placed')).toBeVisible()
```

The test failed at the click with `TimeoutError`; the trace and report were generated with the repository's Playwright 1.62.0 fixture installation. The first todo-app attempt was **excluded**: a restricted Codex sandbox blocked the local server and Chromium, yielding a source-only proposal. A browser-access probe was also excluded. The two counted todo calls were rerun on the same disposable local app with browser access, resetting its in-memory state between arms. One generator tool-start error occurred but the agent recovered and completed browser exploration. The temporary browser sessions were closed and the local server stopped. This setup difference and the single-run schedule rule out latency or reliability conclusions.

**Decision for the three-task pilot:** The official tools are credible complements, not interchangeable competitors. These single calls did not establish an accuracy advantage in Cypress review or Playwright failure diagnosis. The generator produced stronger persistence-oriented scenario proposals at about 3.6 times the recorded input tokens. A decision about broad adoption or replacement needs task-matched, source-complete cases, adjudicated controls, repeated runs, and actual generated-test execution.

## Cypress fix-pair expansion (2026-10-03)

The [fixpair-v1 corpus](../fixpair-v1/corpus.json) has 33 labeled defects in 19 BEFORE/AFTER pairs, but only **six pairs and six labels** are Cypress reviews directly comparable with `cypress-explain`. We ran those six pairs twice with Codex CLI 0.159.3, `gpt-6-sol` at low reasoning effort, and a fresh session for each skill and each side: **48 completed calls**. The two repetitions reversed skill order. Each call saw an opaque, separately copied checkout with no Git history or visible BEFORE/AFTER name; both arms received the same read-only quality-review task except for the explicit skill path. The official arm read its test-review rules in all 24 calls; our arm ran its scanner to a `Summary:` in all 24. Every call returned a final response and its staged checkout and skill digests remained unchanged. The [local runner](../../scripts/evals/run-official-cypress-fixpair.py) records per-call JSON events, usage, and pre/post digests. After repetition 1, the runner gained only `--start-repetition` so repetition 2 could reverse order without rerunning repetition 1; the model command and review prompt were unchanged.

Target scoring here is **semantic and narrowly anchored**: a BEFORE hit must identify the labeled defect at the labeled source line and explain its impact. An AFTER alarm is the *same defect* near its mapped fixed location, not any other concern in the file. The case labels were model-adjudicated in fixpair-v1, not independently human-adjudicated. Other findings were not exhaustively verified, so the table is not whole-report precision.

| BEFORE target | Pairs | `e2e-reviewer` | `cypress-explain` |
| --- | ---: | ---: | ---: |
| Unexplained committed skip (`#11c`, Appsmith) | 1 | 2/2 | 0/2 |
| Established Page Object workflow bypass (`#13`, Appsmith) | 1 | 0/2 | 0/2 |
| Numeric `cy.wait(10)` (`#9b`, Cypress Real World App) | 1 | 2/2 | 0/2 |
| Committed `it.only` (`#7`, three react-admin commits) | 3 | 6/6 | 6/6 |
| **BEFORE total per repetition** | **6** | **5/6 in each** | **3/6 in each** |
| **Mapped AFTER alarms per repetition** | **6** | **0/6 in each** | **0/6 in each** |

The repeated observations are 10/12 versus 6/12 BEFORE hits, **not twelve independent defects**. The three `it.only` labels repeat one simple mechanism. Both skills missed the Page Object target twice. `cypress-explain` also reported other potentially useful problems, including empty-collection assertions and test-order dependencies; those are not scored as target hits or dismissed as false positives. The two skills' full-report accuracy remains unmeasured.

| Arm | Repetition 1 input tokens / summed call time | Repetition 2 input tokens / summed call time | Two-repetition total |
| --- | ---: | ---: | ---: |
| `e2e-reviewer` | 5,618,249 / 1,206.1 s | 5,227,251 / 1,091.0 s | 10,845,500 / 2,297.1 s |
| `cypress-explain` | 1,891,537 / 583.6 s | 1,813,923 / 573.5 s | 3,705,460 / 1,157.1 s |

Our arm used **2.93 times the recorded input tokens** and **1.99 times the summed model-call time**. Input includes cached context, so this is not a billed-token ratio; summed call time is not end-to-end wall time. Both repetitions used the same manifest, checkout digests, and skill digests (`e2e-reviewer`: `71d8be87d8930dcc4fe798a54069cb5c71c23435db0ccd9d0d4ce0eb99a3ad29`; `cypress-explain`: `6c8352871a47001eacbbeb6b459cac378cca865abea29d7e4505e4e5b4653de4`). Raw logs remain in local temporary storage, not the public archive, so the calls and semantic scoring are not independently replayable from this commit. The corpus is public, the checkouts are sparse, there was no blind human adjudication or preregistered scoring protocol, and global skill-discovery isolation was not independently proven. This is development evidence for these six mapped targets, not a general efficiency or superiority claim.

The other 27 fixpair labels are Playwright *static-review* targets. Microsoft's `playwright-cli` is browser automation and `playwright-trace` needs a failing trace, so neither is a valid direct comparator for those labels. The existing [debugger holdout](../../scripts/evals/debugger-holdout-v1.json) has sanitized synthetic report excerpts but no traces, while [generator faultkill](../../scripts/evals/generator-faultkill-v1.json) scores a declarative scenario language rather than authored and executed tests. A Playwright expansion therefore needs separate source-complete trace-diagnosis and test-authoring corpora; these 27 labels were **not** relabeled or scored against unrelated official skills.

## #13 ownership-discovery follow-up (2026-10-03)

The Appsmith miss above led to a read-only exact-selector lead collector. It does **not** make #13 findings. The mandatory scanner now emits its leads for named Cypress specs under `cypress/e2e/`; Phase 2 confirms any plausible match under the unchanged source-ownership contract. Other layouts and computed selectors still need semantic review. On Appsmith BEFORE, the scanner surfaced raw actions at `S3_Spec.js:132,136`, matching `DataSources.ts:88,89` selector fields and their method uses; AFTER surfaced zero leads. The collector covers only direct literal `cy.get`, `page.locator`, and `page.getByTestId` actions, so zero leads cannot clear #13.

The failed attempts matter. Three instruction-only BEFORE reviews all missed #13. A separate, optional collector produced 2/2 BEFORE hits and 0/2 AFTER alarms when the model ran it, but a clean-snapshot repeat yielded only **1/2 BEFORE**: the miss did not invoke the optional tool. These are development diagnostics, not a score to combine with the original six-pair comparison. After moving the same leads into the required scanner output, two fresh BEFORE/AFTER repetitions on the same public Appsmith pair, `gpt-6-sol` at low effort, unchanged task prompt and manifest, yielded **2/2 BEFORE #13 hits and 0/2 mapped AFTER alarms**. Both BEFORE reports cited the first raw action and `TestSaveDatasource()`; every call exited zero with unchanged staged source and skill digests. The final two-repetition skill digest was `23237f5966dddf8f847bbcca02c0534d511dfdca243da9f1e4e2c68d72c52747`.

The final four calls used **2,184,409 input tokens and 516.2 summed call-seconds**, versus **1,755,061 and 389.6** for the earlier four ours-arm calls on this pair. That is about 24% more recorded input and 32% more summed time, but the small stochastic runs and intervening skill edits do not isolate the collector's cost. Input includes cached context, not billed tokens. Other report findings were not exhaustively adjudicated. One known defect repeated twice cannot establish a general #13 recall gain or whole-report precision. Raw final logs remain local at `/tmp/e2e-pom-discovery-20261003-r7`, not in this archive.

The next comparison is defined in the [Page Object ownership validation protocol](../pom-ownership-v1/README.md). It is in preparation only; no new model score is available.
