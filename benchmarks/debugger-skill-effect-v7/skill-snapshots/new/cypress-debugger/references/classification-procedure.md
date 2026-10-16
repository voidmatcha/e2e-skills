## Phase 2: Classification Procedure

Before any execution, browser request, or artifact write in this procedure, read `references/safety-procedures.md` and apply its gates.

Classification steps:

**If delegating**, pass the failing test name, only the sanitized and bounded report excerpt permitted by the output contract below (error, stack, attempt/screenshot signal), repo root, and the **absolute** path to this skill's `SKILL.md` (resolve the actual loaded skill from the host-provided file path or Base directory, not a conventional installation directory). Never pass raw artifact text or an unredacted directly supplied error/stack to a subagent. Every delegated working directory is the project under debug, so a repo-relative `skills/...` path is invalid. Require the F-code with confidence, evidence, and a fix. All available paths use the same F1–F15 contract; resolve disagreements against source evidence and preserve uncertainty when unresolved.

1. Match error message to signals above
2. `duration` near `defaultCommandTimeout` (4s) → F1 or F2
3. CI-only failure → F7 or F8
4. Passes on retry (and no SSR first-interaction signature — see step 5) → F1 candidate; confirm with the evidence below rather than treating retry success as causal proof
5. First `.click()` after `cy.visit()` succeeded but the next assertion timed out on an SSR page → F15
6. **F1 vs F7 needs an isolation probe plus causal evidence, not the error text alone.** Both can surface as `Timed out retrying` and both can "pass sometimes". Run the probe only after the execution safety gate and the repository execution gate's trust checks have passed (see Prerequisites): the whole target stack is `local/disposable` or an approved non-production test environment, the user explicitly trusts this repository, and both exact commands are approved. The probe replays the test, so the safety gate's rule on replaying non-idempotent writes applies to each repetition as it does to retries. Until both gates pass, or while the failing test performs a non-idempotent write whose system-boundary idempotence is not proven, present the commands as `recommended`; in either case, or if the suite cannot be run, say the probe was not performed and report `CANNOT_VERIFY` between F1 and F7 rather than guessing. Once both gates pass and no unproven non-idempotent write would be replayed, run the probe; Cypress has no `--repeat-each`, so repeat the spec run:

   ```bash
   # (a) the spec alone, repeated — is it non-deterministic by itself?
   for i in 1 2 3 4 5; do
     /usr/bin/env -i PATH="$PATH" node_modules/.bin/cypress run \
       --spec 'cypress/e2e/path/to.cy.ts' --config retries=0
   done

   # (b) the whole suite in its real order — does it only break with neighbours?
   /usr/bin/env -i PATH="$PATH" node_modules/.bin/cypress run --config retries=0
   ```

   | (a) alone ×5 | (b) full suite | Interpretation |
   | --- | --- | --- |
   | mixed pass/fail | fails | Supports **F1**, but still check network, environment, and product-state evidence before resolving the code. |
   | 5/5 pass | fails | Supports **F7**; resolve F7 only with shared-state, ordering, `cy.session`, seeded-data, or neighbour/subset evidence. Otherwise report `CANNOT_VERIFY` between F1 and F7. |
   | 5/5 fail | fails | Look first for a consistently reproducible F2/F4/F5/F9/F10/F12 cause, but do not claim that five failures prove the spec cannot be flaky. |

   A bounded sample changes confidence; it does not prove that a spec is non-flaky or that suite context caused the failure. With `e2e.testIsolation: true`, Cypress clears the page, cookies, and storage before each test. `cy.session()` caches within the current spec by default; `cacheAcrossSpecs` defaults to `false`, so cross-spec session reuse is evidence only when the project explicitly enables it. Both commands disable retries: a configured `retries` value would report a fail-then-pass spec as passed and hide the per-run result the table reads.

**Setup-level signals (check before classifying individual tests):**

- **Hook failure:** when a `before`/`beforeEach` hook throws, Cypress fails the first test and **skips the remaining tests in the suite** ("Because this error occurred during a `before each` hook we are skipping the remaining tests in the current suite"). The tell: one failure whose error names the hook (`"before each" hook for "..."`) plus a block of skipped tests (mochawesome `stats.skipped` > 0). The bug is in the shared hook — fix it once; don't file a finding per skipped test.
- **Per-spec reports never merged:** specs that appear "missing"/never-run after a multi-spec `cypress run` usually mean the per-spec mochawesome files were never merged — or the default `overwrite=true` let each spec overwrite the last. These are phantom gaps, not real failures. Regenerate with `overwrite=false`; if `node_modules/.bin/mochawesome-merge` already exists, merge into a different output filename, otherwise inspect every per-spec JSON independently. Do not install a merger during diagnosis.

**Click landed but nothing happened (F15 hydration race):** server-rendered pages (Next.js, Nuxt, SvelteKit, Astro, Remix) paint interactive-looking elements before the framework attaches event listeners. The element is visible and actionable, so `.click()` succeeds against the inert pre-hydration DOM and the failure surfaces only at the next assertion — and Cypress retries *assertions*, never the click, so the test stays red for the full timeout once the inert click is consumed. Distinguish from F14: in F14 the element/content is racing render or removal (not yet rendered, or already gone); in F15 it is rendered but inert. Fix, in order of preference: (1) gate the first interaction on an app-provided hydration signal — `cy.get('html[data-hydrated]')` or `cy.window().its('__APP_READY__').should('eq', true)` — and if the app exposes none, propose the one-line marker upstream (set an attribute in a root `useEffect`/`onMounted`); reading a false-valued property with `.its()` proves only that it exists, not that hydration finished. (2) Only when repository evidence proves the action is idempotent, make the first interaction self-verifying with a bounded re-query/effect check. **Never re-click a non-idempotent control** such as submit, payment, delete, registration, or toggle; wait for a readiness signal instead, because replay can duplicate or reverse a write. Do NOT paper over it with a blind `cy.wait(ms)` after `cy.visit()` — that's the #9 band-aid the reviewer flags, and it still races on slow CI.

**For F2 / F12 fixes — heal by intent, not by patching strings:** only against a target that passes the execution safety gate in `SKILL.md` (a read-only browser action is still an outbound request; otherwise ask the user for a sanitized snapshot), re-query the live DOM for the element the failing command semantically targets (the role/label/text a user sees), then write a new selector at the highest stable tier — `data-testid` or `cy.contains('text')` over a brittle CSS chain. Update the selector at its source (a custom command or Page Object), not inline in the spec, so every caller heals at once. Tweaking the old CSS string usually re-breaks on the next DOM change.

**Read the matching default config, `cypress.config.{js,ts,mjs,cjs}`, before classifying F1 / F7 / F8.** These are Cypress's four default-discovery filenames. A project may instead select a `.mts` or `.cts` config explicitly with `--config-file`; inspect that selected file when the run command or CI configuration names it, but do not treat those extensions as additional default-discovery names. Three config fields decide whether a failure is even a test bug:

- `retries: { runMode, openMode }` — if `runMode` is 0, a "passes on retry"
  diagnosis is moot (Cypress never retried). Recommend a bounded run-mode retry
  probe to confirm an F1 only after repository evidence proves the test and
  every system-boundary effect are idempotent; otherwise classify from existing
  evidence without replaying the action.
- `e2e.testIsolation` — Cypress 12+ resets the browser state (cookies, localStorage, the page) between tests **by default**. A test that passes alone but fails in-suite (F7) usually relies on state a prior test left behind; with `testIsolation: true` that leak is gone, so the fix is to seed the state explicitly (`cy.session()`, fixtures), not to disable isolation.
- `defaultCommandTimeout` / `baseUrl` — a CI-only failure (F8) often traces to a `baseUrl` or timeout that differs from local.

**cy.intercept ordering (F3 / F11) — declare the stub before the request fires.** Registering an intercept after `cy.visit()` is a concrete race because the request can leave before the interceptor exists. Omitting `cy.wait('@alias')` does not by itself prove an intercept race: a retrying DOM assertion may already wait for the response-driven UI state. Add `cy.wait('@alias')` when the request/response itself is part of the contract or when evidence shows the following non-retrying step can run before completion; do not classify F3/F11 from wait omission alone.

```javascript
// before — intercept registered after visit; request may already be in flight
cy.visit('/orders');
cy.intercept('GET', '/api/orders').as('orders');
cy.get('[data-testid="order-row"]').should('have.length', 3); // may retry to the UI state, but cannot prove this intercept observed the request

// after — stub first, visit, then gate the assertion on the response
cy.intercept('GET', '/api/orders').as('orders');
cy.visit('/orders');
cy.wait('@orders');
cy.get('[data-testid="order-row"]').should('have.length', 3);
```
