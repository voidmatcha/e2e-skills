## Phase 2: Classification Procedure

Before any execution, browser request, or artifact write in this procedure, read `references/safety-procedures.md` and apply its gates.

Classification steps:

**If delegating**, pass the failing test name, report excerpt (error, stack, attempt outcome), repo root, and the **absolute** path to this skill's `SKILL.md` (resolve the actual loaded skill from the host-provided file path or Base directory, not a conventional installation directory). Every delegated working directory is the project under debug, so a repo-relative `skills/...` path is invalid. Require the F-code with confidence, evidence, and a fix. All available paths use the same F1–F15 contract; resolve disagreements against source evidence and preserve uncertainty when unresolved.

1. Match error message to signals above
2. `duration` near timeout → F1 or F3
3. CI-only failure → F7 or F8
4. Passes on retry — spec `outcome` is `flaky` (a trailing `passed` result; cross-check `stats.flaky`) and no SSR first-interaction signature (see step 5) → F1. A flaky outcome is an F1 candidate, not a hard failure.
5. Action succeeded but the *next* assertion timed out, SSR app, first interaction after `goto` → F15
6. **F1 vs F7 needs an isolation probe plus causal evidence, not the error text alone.** Both can surface as `TimeoutError` and both can "pass sometimes". Run the probe only after the execution safety gate and the repository execution gate's trust checks have passed (see Prerequisites): the whole target stack is `local/disposable` or an approved non-production test environment, the user explicitly trusts this repository, and both exact commands are approved. The probe replays the test, so the safety gate's rule on replaying non-idempotent writes applies to each repetition as it does to retries. Until both gates pass, or while the failing test performs a non-idempotent write whose system-boundary idempotence is not proven, present the commands as `recommended`; in either case, or if the suite cannot be run, say the probe was not performed and report `CANNOT_VERIFY` between F1 and F7 rather than guessing. Once both gates pass and no unproven non-idempotent write would be replayed, run:

   ```bash
   # (a) alone, repeated — is the test non-deterministic by itself?
   /usr/bin/env -i PATH="$PATH" node_modules/.bin/playwright test path/to/spec.spec.ts \
     --grep 'escaped unique title fragment' --retries=0 --repeat-each=10 --workers=1

   # (b) at the suite's real parallelism — does it only break with neighbours?
   /usr/bin/env -i PATH="$PATH" node_modules/.bin/playwright test --retries=0
   ```

   | (a) alone ×10 | (b) full suite | Interpretation |
   | --- | --- | --- |
   | mixed pass/fail | fails | Supports **F1**, but still check network, environment, and product-state evidence before resolving the code. |
   | 10/10 pass | fails | Supports **F7**; resolve F7 only with shared-state, ordering, worker-fixture, serial-chain, or neighbour/subset evidence. Otherwise report `CANNOT_VERIFY` between F1 and F7. |
   | 10/10 fail | fails | Look first for a consistently reproducible F2/F4/F5/F9/F10/F12 cause, but do not claim that ten failures prove the test cannot be flaky. |

   A bounded sample changes confidence; it does not prove that a test is non-flaky or that suite context caused the failure. `--repeat-each` multiplies runtime, so scope it to the single failing test, never the suite.

**Setup-level signals (check before classifying individual tests):**

- **`beforeEach` / fixture failure:** if the error stack points into a hook or a fixture (not the test body) and **every test in the file fails identically**, the bug is in the shared setup — fix the fixture/hook once, not each test. A wall of identical failures across one spec is the tell; don't file N separate findings.
- **Sharding / unmerged blob artifacts:** specs that show as "missing"/never-run
  after a `--shard` CI run usually mean the per-shard `blob-report/`
  directories were never merged. These are phantom failures, not real ones —
  merge first with `publish-json-report.py` and the `merge-reports` command
  from Prerequisites, then re-classify against the merged report.

**Read the matching default config, `playwright.config.{ts,js,mts,mjs,cts,cjs}`, before classifying F1 / F7 / F8.** These are Playwright's six default-discovery filenames. Three config fields decide whether a failure is even a test bug:

- `retries` — if 0 (the safe reproduction default), no `flaky` outcome can ever
  appear in the report (Playwright never retried). Recommend `--retries=2` to
  confirm an F1 only after repository evidence proves the test and every
  system-boundary effect are idempotent; otherwise classify from existing
  evidence without replaying the action.
- `fullyParallel` / `workers` / `test.describe.configure({ mode: 'serial' })` — each test gets a fresh browser context, but **worker-scoped fixtures and serial chains leak state across tests**. A test that passes alone but fails in-suite (F7) usually traces to a worker fixture or a serial chain relying on an earlier test's state; the fix is to seed the state explicitly (storageState, API setup), not to reorder tests or drop to one worker.
- `use.baseURL` / `timeout` / `expect.timeout` / `webServer` — a CI-only failure (F8) often traces to a baseURL, timeout, or `webServer` target (which app build the tests even hit) that differs from local.

**For F2 / F12 fixes — heal by intent, not by patching strings:** only against a target that passes the execution safety gate in `SKILL.md` (a read-only browser action is still an outbound request; otherwise ask the user for a sanitized snapshot), take a fresh snapshot of the live page, locate the element the failing step semantically targets (the role/name/label a user would see), and write a new locator at the highest stable tier (role+name > placeholder > testid). Tweaking the old selector string usually re-breaks on the next DOM change.

**Accessible-name collisions (strict-mode violation on role+name):** when two semantically different controls share a name — e.g. a "Like" *tab* button and a per-card "Like" *toggle* — don't downgrade to `.nth()`. Disambiguate by the semantic attribute that distinguishes the roles: `getByRole('button', { name: 'Like' }).and(page.locator('[aria-pressed]'))` selects the toggle; `.and(page.locator(':not([aria-pressed])'))` selects the tab. The attribute encodes intent (`aria-pressed` = toggle semantics), so the locator survives reordering that breaks positional selection.

**Visible but `getByRole` never matches (click stuck at "waiting for" on an element the screenshot plainly shows):** check the element's ancestors for `aria-hidden="true"`. An aria-hidden ancestor removes the entire subtree from the accessibility tree, so role queries can never match inside it — while `getByText` (DOM text matching) still works. App layer/modal wrappers that put `aria-hidden` on their own root are a common source. The nastier variant: if a control elsewhere on the page shares the accessible name, the role query silently resolves to *that* one and the click is then blocked by the modal overlay — same timeout, misleading target. Fix: locate by text scoped to a stable container inside the hidden subtree (e.g. `page.locator('#modalBox').getByText('Start quiz')`), leave a WHY comment, and report the `aria-hidden` root upstream as an application accessibility defect — screen readers lose the same subtree your locator did.

**Click landed but nothing happened (F15 hydration race):** server-rendered pages paint interactive-looking elements before the framework attaches event listeners. Playwright's actionability checks (visible, stable, enabled) all pass against the inert pre-hydration DOM, so the action is reported successful and the failure surfaces only at the *next* assertion. Signals: SSR/SSG framework (Next.js, Nuxt, SvelteKit, Astro, Remix), the failing assertion follows the first interaction after `page.goto()`, the failure screenshot shows a fully painted page, passes on retry or with `slowMo`. Distinguish from F14: in F14 the element/content is racing render or removal (not yet rendered, or already gone); in F15 it is rendered but inert. Fix, in order of preference: (1) gate the first interaction on an app-provided hydration marker — `await expect(page.locator('html[data-hydrated]')).toBeAttached();` — and if the app exposes none, propose the one-line marker upstream (set an attribute in a root `useEffect`/`onMounted`); it fixes every spec at once. (2) Only when repository evidence proves the action is idempotent, make it self-verifying so a retry can land: `await expect(async () => { await button.click(); await expect(dialog).toBeVisible({ timeout: 1000 }); }).toPass();`. **Never retry a non-idempotent action** such as submit, payment, delete, registration, or toggle; wait for a readiness signal instead, because replay can duplicate or reverse a write. Do NOT paper over it with `waitForTimeout()` after `goto` — that's the #9 band-aid the reviewer flags, and it still races on slow CI.
