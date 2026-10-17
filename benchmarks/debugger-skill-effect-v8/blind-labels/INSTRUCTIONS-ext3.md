# Blind F-code mapping task (v8 extension, pass ext3)

You map 2 real, already-diagnosed E2E test failures onto the F1-F15 taxonomy. For each item you see ONLY the
root-cause statement and the fix. Use only the table and the packet below; do not use any tool and do not read any file.

F1-F15 table (released 2.0.1 text, Phase 2):

| # | Category | Signals | Review Pattern |
|---|----------|---------|----------------|
| F1 | **Flaky / Timing** | `TimeoutError`, duration near maxTimeout, passes on retry | #9 |
| F2 | **Selector Broken** | `locator not found`, `strict mode violation`, element count mismatch | #6, #10 |
| F3 | **Network Dependency** | `net::ERR_*`, unexpected API response, `404`/`500` | — |
| F4 | **Assertion Mismatch** | `Expected X to equal Y`, over-broad check | #4 |
| F5 | **Missing Then** | Action completed but wrong state remains | #2 |
| F6 | **Condition Branch Missing** | Element conditionally present, assertion always runs | #5 |
| F7 | **Test Isolation Failure** | Passes alone, fails in suite; leaked state | — |
| F8 | **Environment Mismatch** | CI vs local only; viewport, OS, timezone | — |
| F9 | **Data Dependency** | Missing seed data, hardcoded IDs | — |
| F10 | **Auth / Session** | Session expired, role-based UI not rendered | — |
| F11 | **Async Order Assumption** | `Promise.all` order, parallel race | — |
| F12 | **POM / Locator Drift** | DOM changed, POM locator not updated | #10 |
| F13 | **Error Swallowing** | `.catch(() => {})` hiding failure, test passes silently | #3 |
| F14 | **Animation Race** | Element/content appears or disappears within a window the assertion can miss — content not yet rendered, or a transient element removed before it is observed | #9 |
| F15 | **Hydration Race** | Action reported success but had no effect; first interaction after `goto` on a server-rendered page (Next.js/Nuxt/SvelteKit/Astro/Remix); failure surfaces at the next assertion; passes on retry | #9 |

Use Phase 1 output (error message + duration + file) to classify each failure. **Most failures are identifiable here — only go to Phase 3 if still unclear.**

For each item give: `f_code` (the single F-code whose definition best matches the stated mechanism), `second_choice`
(or null), `fit` ("clean" if one code clearly matches; "forced" if no code fits well and you picked the least bad),
and `reason` (one sentence). Return ONE strict-JSON object: {"item-103": {"f_code": "F?", "second_choice": "F?", "fit": "clean|forced", "reason": "..."}, ... all 2 items ...}.

