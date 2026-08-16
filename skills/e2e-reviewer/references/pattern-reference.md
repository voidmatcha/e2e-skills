# Pattern Reference

Read on demand from SKILL.md Phase 2: the exact contract for each of the 24 patterns —
detection semantics, severity rationale, false-positive exclusions, JUSTIFIED handling.
The Quick Reference table in SKILL.md is the at-a-glance ID/severity index; this file is the
authority for per-pattern behavior. CI parity (scripts/ci/review.sh Checks 3b/3c) validates the
`### P0/P1/P2 —` section placement and `#### <id>.` headers in THIS file against that table.

Detailed specification for the 24 anti-patterns that Phase 1, Phase 2, and Phase 2.5 execute. Do **not** re-run these checks as a separate pass — the phases above already cover them. When emitting a finding, consult the matching section here for the canonical Symptom / Rule / Fix wording. Grouped by severity: P0 items are silent always-pass bugs, P1 items waste CI time or mislead developers, P2 items are maintenance concerns.

**Important:** `test.skip()` with a reason comment or reason string is intentional — do NOT flag or remove these. Only flag assertions gated behind a runtime `if` check that cause the test to pass silently (see #5a).

---

<!-- Manual index: keep in sync with the SKILL.md Quick Reference table. CI 3b/3c does not validate this block. -->
## Pattern index

Navigation aid only — the SKILL.md Quick Reference table and the per-pattern sections below are authoritative for severity; if this table ever disagrees, they win. Find a pattern here, then read its section below. Sub-IDs are documented inside their base block: `#4a–#4j` in `#### 4.`, `#5a`/`#5b` in `#### 5.`, `#8a`/`#8b` in `#### 8.`, `#9b`/`#9c` in `#### 9.`, `#10a`–`#10f` in `#### 10.` (`#4`, `#5`, and `#10` span two severities — the base section carries both).

| Severity | Pattern IDs |
|----------|-------------|
| **P0 — Must Fix** (silent always-pass) | #1 name-assertion mismatch, #2 missing Then, #3 error swallowing, #3b Cypress uncaught:exception, #4 invariant/vacuous-object assertions (#4a/#4f), #5a conditional bypass (in #5), #7 focused-test leak, #8 missing assertion (#8a/#8b), #12 missing auth |
| **P1 — Should Fix** (poor diagnostics or retry robustness) | #4 non-retrying/weak assertions (#4b–#4e/#4g–#4j), #5b force:true (in #5), #6 raw DOM query, #9 hard-coded sleep (#9b/#9c), #10 flaky patterns (#10a/#10b/#10c), #13 inconsistent POM, #14 hardcoded creds, #15 missing await on expect, #16 missing await on action, #17 discouraged direct Page selector API, #18 expect.soft overuse, #19 module-level state, #20 unmocked writes, #22 optimistic UI |
| **P2 — Nice to Fix** (maintenance) | #11 YAGNI + zombie specs, #21 manual session file, #23 fixture render guards |

### P0 — Must Fix (silent always-pass)

Tests pass when the feature is broken. No real verification is happening. Always check these.

#### 1. Name-Assertion Alignment `[LLM-only]`

**Symptom:** Test name promises something the assertions don't verify.

```typescript
// BAD — name says "status" but only checks visibility
test('should display user status', async ({ page }) => {
  await expect(status).toBeVisible();  // no status content check
});
```

**Rule:** Every explicit promised outcome, state transition, or acceptance
clause in the test name must have corresponding evidence. Add it or narrow the
title.

Interpret nouns by the user-visible contract, not as isolated implementation
tokens. A success confirmation can substantiate that a submit action completed;
do not also report #1 merely because the test does not inspect the request
directly. Missing route isolation or request proof belongs to #20/#22 unless the
title explicitly promises a specific payload, status, or request shape.

**Procedure:**
1. Parse the title into user-visible promises.
2. Trace each promise to an assertion, request proof, redirect, or equivalent
   observable evidence.
3. A promise with no evidence is a finding; implementation nouns and helper
   steps that are not promised outcomes are not.

**Primary line:** Anchor #1 to the test/setup declaration whose title contains
the unverified promise. A constant or unrelated assertion that fails to prove
the noun is supporting evidence, not a second #1 finding.

**Common patterns:** "should display X" with only `toBeVisible()` (no content check), "should update X and Y" with assertion for X but not Y, "should validate form" with only happy-path assertion.

#### 2. Missing Then `[LLM-only]`

**Symptom:** Test acts but doesn't verify the final expected state.

```typescript
// BAD — toggles but doesn't verify the dismissed state
test('should cancel edit on Escape', async ({ page }) => {
  await input.click();
  await page.keyboard.press('Escape');
  await expect(text).toBeVisible();
  // input still hidden?
});
```

**Rule:** For toggle/cancel/close actions that the title or acceptance contract
promises, verify both the restored state AND the dismissed state. Helper actions
used only to reach another asserted outcome do not each create a separate Then
obligation.

**Procedure:**
1. Identify the action verb (toggle, cancel, close, delete, submit, undo)
2. List the expected state changes (element appears/disappears, text changes, count changes)
3. Check that BOTH sides of the state change are asserted

**Common patterns:** Cancel/Escape without verifying input is hidden, delete without verifying count decreased, submit without verifying form resets, tab switch without verifying previous tab content is hidden.

**Do NOT flag (Phase 2 accept-criteria) — the verification is often non-obvious; confirm it is *truly* absent before flagging.** A delete/remove test is fine when any of these is present:

- **API / request test:** a `request('DELETE')` / `request.delete()` followed by a GET asserting `status()` is `404` — the 404 *is* the removal assertion (not a missing-then).
- **Cleanup / teardown:** the delete sits in `afterEach`/`afterAll`/`after()` or a test titled `Cleanup:`/`teardown` — its job is teardown, not user-facing verification (the create test owns that assertion).
- **Success-confirmation:** a post-delete success toast/snackbar matching `/deleted|removed/i`, or a redirect (`toHaveURL` back to the list/index) — both count as verifying the delete happened.
- **Helper-embedded assertion:** the delete runs through a shared helper (e.g. `deleteElement(name)`, `deleteRancherResource(...)`) that asserts removal internally — read the helper before flagging.
- **Non-standard negative assertion:** `toHaveCount(0)`, `toBeEmpty()`, `toBeNull()`, or `isVisible()` captured into a variable then `toBe(false)` are all valid absence checks — **provided the locator was proven able to match** (it was asserted present or acted on earlier in the test). An absence assertion on a locator that never matched anything satisfies #2 while proving nothing; that is #4i, not an accept-criterion.
- **Non-entity "remove":** editor text/image, a CSS class/style, diacritics, or whitespace being "removed" is not entity deletion — judge by the noun in the title, not the verb.
- **Different promised outcome:** a helper closes, toggles, or navigates while
  the title promises another final state that is asserted. Do not invent a
  second acceptance criterion for the helper action.
- **Write-contract overlap:** the user-visible result is asserted, but the
  source, helper, or fixture confirms a real backend write or optimistic UI
  without request proof. Report #20/#22, not an additional #1/#2. An action
  name alone is not evidence that a backend call or optimistic update exists.

Only flag a delete/remove candidate when the test performs a real entity-delete
action (a click/dispatch on a delete/trash/remove control) and **none** of the
above verifications follow.
Anchor the finding to the action line whose promised result lacks proof.
If the same missing effect also makes the title incomplete, classify it once as
#2 at this causal action. Reserve #1 for title-promised outcomes that do not
reduce to a more specific state-changing action with a missing postcondition.

#### 3. Error Swallowing `[grep-detectable + LLM]`

**Symptom (POM — grep):** empty/fallback Promise catch callbacks such as `.catch(() => {})`, optional-call `.catch?.(() => {})`, `.catch(function () {})`, or `.catch(() => false)` on awaited operations — caller never sees the failure. Async, named, and parameterized function-expression callbacks carry the same semantics and must not bypass review.

**Symptom (spec — LLM):** `try/catch` wrapping assertions — test passes on error instead of failing.

```typescript
// BAD POM — caller thinks execution succeeded
await loadingSpinner.waitFor({ state: 'detached' }).catch(() => {});

// BAD spec — silent pass on assertion failure
try { await expect(header).toBeVisible(); }
catch { console.log('skipped'); }
```

**Rule (POM):** Remove `.catch(() => {})` / `.catch(() => false)` from wait/assertion methods. If the operation can legitimately fail, the caller should decide how to handle it. Only keep catch for UI stabilization like `input.click({ force: true }).catch(() => textarea.focus())`.

**Rule (spec):** Never wrap assertions in `try/catch`. Use `test.skip()` in `beforeEach` if the test can't run. `try/catch` in non-assertion code (setup, teardown, optional cleanup) is fine — LLM must read context before flagging.

#### 3b. Cypress `uncaught:exception` Suppression `[grep-detectable, Cypress only]`

**Symptom:** `cy.on('uncaught:exception', () => false)` globally suppresses all unhandled app errors, hiding real bugs.

```javascript
// BAD — blanket suppression
Cypress.on('uncaught:exception', () => false);

// BETTER — scoped to a specific known error
Cypress.on('uncaught:exception', (err) => {
  if (err.message.includes('ResizeObserver loop')) return false;
  throw err;
});
```

**Rule:** Blanket `() => false` is P0 — equivalent to `.catch(() => {})`.
Safe handlers conditionally allowlist one named, documented regression and
rethrow every other error. Mere `expect(err).to.exist` or another generic
assertion does not excuse a later unconditional `return false`: it still
suppresses every application error. A negative-regression handler is exempt
only when its assertion is regression-specific and non-matching errors are
explicitly rethrown.

#### 4. Vacuous and Non-Retrying Assertions `[grep-detectable + LLM confirmation]` `[P0/P1]`

**Symptom:** An assertion is logically unable to fail, samples asynchronous
state once instead of retrying until the expected state settles, or uses a
partial match that omits a user-visible contract the scenario promises.

```typescript
// BAD — count >= 0 is always true
expect(count).toBeGreaterThanOrEqual(0);

// BAD — helper implementation increments from zero before every return
expect(nextTicket()).toBeGreaterThan(0);

// P1 — weak existence proof after an action, no user-visible outcome
await expect(page.locator('header')).toBeAttached();

// P1 — one-shot values, no auto-retry
expect(await el.isVisible()).toBe(true);
expect(await el.textContent()).toBe('expected text');
expect(await el.getAttribute('attr')).toBe('value');
expect(await el.allTextContents()).toContain('expected item');

// BAD — Locator is always a truthy JS object regardless of element existence
expect(page.locator('.selector')).toBeTruthy();

// BAD — a Locator is never null/undefined, so these never fail either (same #4f family)
expect(page.getByText('1/31/2025')).not.toBeNull();
expect(page.getByText('1/31/2025')).not.toBeUndefined();
expect(page.getByText('1/31/2025')).not.to.equal(null);
expect(page.getByText('1/31/2025')).not.to.be.null;
expect(page.locator('.selector')).toBeDefined();
```

**Sub-IDs:** `#4a` numeric invariant candidate (LLM-TRIAGE), `#4b` vacuous `toBeAttached()` (LLM-TRIAGE — see below), `#4c-4e` one-shot state/content reads (one combined scanner check), `#4f` Locator truthiness/nullness, `#4g` `timeout: 0` (dedicated block below), `#4h` one-shot `page.url()`, `#4i` absence assertion on a locator never proven able to match (LLM-TRIAGE), and `#4j` under-specified ARIA snapshot accessible names (LLM-only). The scanner does not emit `#4j`.

**#4a helper-invariant semantics:** Syntax alone is not enough: `value > 0` can
be a meaningful assertion. When the asserted value comes from a helper supplied
in scope, read that implementation. Flag #4a only if the implementation itself
proves the predicate for every call independently of product behavior (for
example, module state starts at zero, increments before returning, and the test
asserts only that the result is positive). Anchor the assertion line. If the
helper can return a value that violates the predicate, keep the assertion.
Imports of `test` from unresolved package/workspace fixtures retain the raw
candidate as LLM triage rather than proving Playwright scope; known unit-test
framework imports do not establish E2E scope.

**Severity rule:** #4a and #4f are P0 because their predicates are true
independently of product behavior. #4b–#4e and #4g–#4j are P1: they can fail,
but provide weak, non-retrying, or under-specified evidence and therefore create
timing, diagnostic, selector-rot, or accessibility-contract risk. Do not call a
one-shot or partial-match assertion "always-passing."

**Rule:** `toBeAttached()` is meaningful when the promised contract is DOM
attachment itself: for example, a conditionally rendered node, a dynamically
injected resource, or a CSS-hidden element that must remain in the DOM. It is
weak after an action when attachment adds no evidence for the promised
user-visible or removed state → P1. Judge the test title, action, and expected
outcome; do not treat every positive attachment assertion as vacuous.

**#4b scanner semantics (LLM-TRIAGE):** grep alone cannot confirm the context that makes a `toBeAttached()` hit real. The scanner matches the positive form only (`.not.toBeAttached()` is never flagged) and tags each hit `[P1?][LLM-TRIAGE]`. Phase 2 confirms destructive-action context (the element should have been removed) before reporting P1 — on client-rendered apps a positive `toBeAttached()` is usually a legitimate render-gate (field data: ~90% FP).

**Fix:**
- `toBeGreaterThanOrEqual(0)` → `toBeGreaterThan(0)`
- weak `toBeAttached()` → `toBeVisible()` when visibility is promised, or remove
  it when another assertion already proves the outcome; keep it when DOM
  attachment is the actual contract
- `expect(await el.isVisible()).toBe(true)` → `await expect(el).toBeVisible()`
- `expect(await el.textContent()).toBe(x)` → `await expect(el).toHaveText(x)`
- `expect(await el.getAttribute('x')).toBe(y)` → `await expect(el).toHaveAttribute('x', y)`
- `expect(await el.allTextContents()).toContain(x)` → `await expect(el).toContainText(x)`
- `expect(locator).toBeTruthy()` → `await expect(locator).toBeVisible()`
- Computed matcher access is a candidate only when the key is a literal or an
  immutable `const` bound directly to `toBeTruthy`/`toBeDefined`; arbitrary or
  mutable computed keys remain unresolved and are not mechanically reported.
- A direct Locator subject can be final #4f. A Locator nested inside an
  arbitrary wrapper call, such as `expect(wrapper(page.locator(...)))`, remains
  LLM-triage because the wrapper may transform the value.
- `expect(locator).not.toBeNull()` / `.not.toBeUndefined()` / `.not.to.equal(null)` / `.not.to.be.null` / `.toBeDefined()` → `await expect(locator).toBeVisible()` (a Locator is never null/undefined; assert the user-visible state instead)
- `{ timeout: 0 }` on assertions → see the 4g block below
- `expect(page.url()).toContain(x)` → `await expect.poll(() => page.url()).toContain(x)` (one-shot URL read with no retry). Keep the substring matcher instead of converting `x` into a regex-backed `toHaveURL`; `x` may contain regex metacharacters. The scanner follows provenance-backed aliases of Playwright `expect` and renamed receivers whose type/fixture provenance proves `Page`.
- **Multiple `expect(page.url()).toContain(...)` in sequence** → replace each call with its **own** `await expect.poll(() => page.url()).toContain(...)`. Do NOT combine them into a single regex with `.*` — that adds an ordering constraint not present in the original substring checks.
- **Compound boolean expression** like `expect(visible1 || visible2).toBe(true)` is the same one-shot anti-pattern as `expect(await el.isVisible()).toBe(true)`. Prefer a locator-level web-first assertion such as `await expect(page.locator('.a, .b')).toBeVisible()`. If both branches require independent assertions (e.g., different post-actions per branch), gate the test with `test.skip()` on the unsupported branch rather than collapsing into a single boolean check.

**Boundary with #15 (one-shot reads vs floating promises):** in #4c-4e the `await` sits INSIDE `expect()` and resolves a real value against a sync matcher — `expect(await el.textContent()).toBe(x)`, including wrapped forms `expect((await …).trim())`, `expect(Number(await …))`, `expect(!(await …))` — nothing floats; the bug is a one-shot read with no auto-retry. The scanner reroutes these shapes here even when they superficially resemble #15. An unawaited web-first matcher (`expect(locator).toBeVisible()` with no leading `await`) is #15, not #4.

**Retry-wrapper skip (false-positive exclusion — applies to #4c-4e and #4h):** when a hit's enclosing function is the callback of `await expect(async () => { … }).toPass({…})` or `await expect.poll(async () => { … }).toX(…)`, Playwright re-runs the callback until it passes or times out. SKIP the P1 finding for those hits. In practice a large share of raw #4h hits sit inside `.toPass(…)` callbacks — always check the enclosing wrapper before counting.

<!-- 4g stays a bold sub-block, NOT a "#### 4g." header: CI Check 3c (scripts/ci/review.sh) requires the set of "#### <id>." headers in this file to exactly equal the 24 Quick Reference base IDs. Sub-IDs (4g — like 5a/5b, 8a/8b, 10a/10b) live inside their parent's block. -->
**4g. Zero timeout weakens retry/deadline control** `[grep-detectable]` — in
Playwright 1.62, `{ timeout: 0 }` on a web-first assertion does **not** make it
one-shot. It removes the assertion-local deadline, so the matcher keeps
retrying until an enclosing test or hook deadline aborts it. In Cypress, a
zero command timeout removes the normal retry window and behaves like an
immediate current-state check. Both forms discard the framework's useful local
bound and degrade failure timing or diagnostics.

```typescript
// BAD in Playwright — can consume the enclosing test timeout
await expect(el).toHaveCount(0, { timeout: 0 });

// BETTER — preserves retry with a finite assertion-local deadline
await expect(el).toHaveCount(0, { timeout: 5_000 });
```

**Rule:** flag `timeout: 0` (including quoted keys and whitespace before `:`)
only when bounded call context ties it to a Playwright
assertion/action or Cypress command/configuration API (P1). A standalone options
object or an unrelated `apiClient.request({ timeout: 0 })` is not this pattern. In Playwright, replace it
with an explicit finite matcher timeout unless the assertion deliberately
shares a documented, bounded enclosing deadline. In Cypress, remove it unless
an immediate current-state check is the explicit intent. Put a concrete
`// JUSTIFIED:` on the line above for either exceptional case; the scanner
suppresses justified hits.

<!-- 4i is a bold sub-block, NOT a "#### 4i." header — see the 4g note above (CI Check 3c). -->
**4i. Absence assertion never proven able to match** `[grep-detectable + LLM-TRIAGE]` `[P1]` — an absence assertion is satisfied by a locator that matches *nothing*, so a selector that rotted keeps the test green forever while proving nothing.

This is framework semantics, not a codebase quirk. Playwright defines `toBeHidden` as "either **does not resolve to any DOM node**, or resolves to a non-visible one", and `not.toBeVisible()` is the inverse of `toBeVisible` ("attached **and** visible"). Both are satisfied by zero matches. `toHaveCount(0)` and Cypress `.should('not.exist')` behave the same way.

```typescript
// BAD — .spinner is a class the app stopped rendering three refactors ago.
// The selector matches nothing, so this passes without observing the cancel at all.
await cancelButton.click();
await expect(page.locator('.job-controls .spinner')).not.toBeVisible();

// GOOD — the same locator is proven able to match before absence is asserted
const spinner = page.locator('[data-testid="run-spinner"]');
await expect(spinner).toBeVisible();
await cancelButton.click();
await expect(spinner).toBeHidden();
```

**Why it matters:** this is the failure mode that survives longest. A rotted *positive* assertion fails on the next run and gets fixed; a rotted *negative* assertion is indistinguishable from a passing test. It accumulates silently across framework migrations (AngularJS→Angular, class renames, design-system swaps), and the suite reports coverage it does not have. A generated spec can arrive in this state on day one: an invented `data-testid` that never matched anything is indistinguishable from a selector that rotted, and an absence assertion keeps both green forever. Cause does not change the resolution — do not narrow this to authorship.

**Rule:** an absence assertion is only meaningful if the same locator is proven capable of matching somewhere in that test's execution path — asserted present, or used as the target of an action.

**Detection (grep + LLM):** the scanner flags every `.not.toBeVisible()` / `.not.toBeAttached()` / `.toBeHidden()` / `.toHaveCount(0)` / `.should('not.exist'|'not.be.visible')` as `[P1?][LLM-TRIAGE]` — outside the exit gate, because grep cannot see the rest of the test. Phase 2 resolves each hit:

- **SKIP** — the same locator (or an alias of it) is asserted present, or is clicked/filled/hovered, earlier in the test or its `beforeEach`.
- **SKIP** — the test is an empty-state / no-results case that also asserts a positive counterpart (empty-state message visible, "0 results" text). This is the dominant legitimate shape; expect it to account for most raw hits. It does not cover the `#23` case: when a render guard suppresses seeded items, the empty-state message renders for the wrong reason and the positive counterpart proves nothing. Check that the fixture can actually satisfy the component's guards before skipping on this ground.
- **SKIP** — `// JUSTIFIED:` on the preceding line.
- **FLAG P1** — the locator appears nowhere else and nothing positive is asserted alongside. Report it as an assertion that can pass without proving the locator ever matched, and propose either proving the locator first or deleting the assertion.

**Fix:** assert the positive state before the action that removes it, then assert absence on the *same* locator object — binding it to a variable makes the pairing checkable at a glance.

<!-- 4j is a bold sub-block, NOT a "#### 4j." header — see the 4g note above. -->
**4j. Under-specified ARIA snapshot accessible name** `[LLM-only, Playwright only]` `[P1]` — a `toMatchAriaSnapshot()` template contains a role-only node such as `- button` even though the test title, action, or acceptance contract promises a specific control label or identity.

Playwright's [partial-matching contract](https://playwright.dev/docs/aria-snapshots#partial-matching) says that omitting an accessible name matches the role regardless of its label. A role-only `- button` snapshot therefore stays green if "Submit order" regresses to "Delete order" or an empty accessible name.

```typescript
// BAD — the title promises the label, but this snapshot accepts any button name
test('submit control has an accessible name', async ({ page }) => {
  await expect(page.getByRole('main')).toMatchAriaSnapshot(`
    - button
  `);
});

// GOOD — make the promised accessible name load-bearing
await expect(page.getByRole('main')).toMatchAriaSnapshot(`
  - button "Submit order"
`);

// GOOD — snapshot is deliberately structural; the name is proved separately
const submit = page.getByRole('button', { name: 'Submit order', exact: true });
await expect(submit).toHaveAccessibleName('Submit order');
await expect(page.getByRole('main')).toMatchAriaSnapshot(`
  - button
`);
```

**Rule:** Flag P1 when an omitted accessible name lets the ARIA snapshot pass with a wrong or empty label that the scenario promises to verify. Anchor the finding at the role-only snapshot node. This is not a blanket requirement to name every node in an ARIA snapshot.

**False-positive exclusions:**
- **SKIP** an intentionally structure-only snapshot when the same test separately asserts the relevant accessible name or a complete user-visible outcome that fulfills the title/action contract.
- **SKIP** a role whose accessible name is genuinely dynamic or irrelevant to the scenario when a concrete `// JUSTIFIED:` immediately above the `toMatchAriaSnapshot()` call documents that intent.
- **SKIP** named nodes (`- button "Submit order"` or a deliberate regular-expression name) because the snapshot already constrains the accessible name.

**Fix:** include the stable accessible name in the ARIA snapshot, or add a separate web-first `toHaveAccessibleName()` assertion when keeping the snapshot structure-only is clearer. Use `// JUSTIFIED:` only when label independence is part of the test's explicit intent.

#### 5. Bypass Patterns `[grep-detectable]` (5a P0, 5b P1)

Two sub-patterns that suppress what the framework would normally catch — making tests pass when they should fail. Listed under P0 because 5a is a silent-pass bug; 5b is a P1 actionability issue documented in the same section for proximity.

**5a. Conditional assertion bypass** — a load-bearing assertion for the
scenario's promised outcome is gated behind a runtime condition. If the branch
is false, that outcome is never verified and no independent unconditional
meaningful postcondition or failure-producing action can fail the test.

```typescript
// BAD — if spinner never appears, assertion never runs
if (await spinner.isVisible()) {
  await expect(spinner).toBeHidden({ timeout: 5000 });
}
```

**Rule:** Flag P0 only when the conditional assertion is load-bearing for the
title/action's promised outcome and the false branch has no independent
unconditional meaningful postcondition or failure-producing action. Do not flag
a conditional diagnostic or optional-state assertion when the scenario still
has an unconditional assertion or action that meaningfully proves or enforces
the promised outcome. Move environment- or feature-flag gates for a required
outcome to `beforeEach` / declaration-level `test.skip()` so unsupported runs
are skipped explicitly rather than passing silently.

**5b. Force true bypass** — `{ force: true }` skips actionability checks (visibility, enabled state, pointer-events), hiding real UX problems that real users would encounter.

**Rule:** Each `{ force: true }` (including quoted keys and whitespace before
the colon) on a Playwright/Cypress action must have `// JUSTIFIED:` on the line
above explaining why the element is not normally actionable. Unrelated APIs such as `fs.rm(..., { force: true })` or `apiClient.request({ force: true })` are not findings. Without a comment, flag P1 and anchor the finding at the line containing the action option.

#### 7. Focused Test Leak (`test.only` / `it.only`) `[grep-detectable]`

**Symptom:** A `.only` modifier left in committed code. Test focus applies to
the invoked project/run, so tests in other files can be silently excluded even
when the focused file contains only one test.

```typescript
// CRITICAL SILENT-SKIP — file has multiple tests; the others never run
test.only('should show user profile', async ({ page }) => { ... });
test('should show settings', ...);   // ← never runs in CI

// STILL CRITICAL — other files in the invoked project can be excluded
test.only('the only test in this file', ...);
```

**Rule** (Playwright & Cypress best practices): `.only` is a development-time
focus tool. It must never be committed. Search `.spec.*/.test.*/.cy.*` for
direct and optional-call focus modifiers, then trace immutable one-hop aliases:
`const focused = test.only`, `const focused = test.only.bind(test)`, and
`const { only } = test` / `const { only: focused } = test`. Report the alias
call (for example, `focused(...)`) as P0. Accept Playwright-proven receivers and
Cypress `it` / `test` / `describe` globals only in Cypress-proven spec context.
For Playwright, follow the exact named, default, CommonJS, or namespace `test`
binding through relative re-exports. A barrel that exports Playwright `test`
beside an unrelated `scenario` does not make `scenario.only()` a finding.
Reject aliases that are reassigned, shadowed, imported from a foreign test
framework, bound to a different receiver, or derived from an unrelated
application method named `only`.

**Fix:** Delete the `.only` modifier. If the test is intentionally isolated,
use `test.skip()` with a reason on the others, or run a single file via the CLI
(`--grep` / `--spec`). Audit CI history for skipped runs.

No `// JUSTIFIED:` exemption exists for either tier — there are no legitimate committed uses.

#### 8. Missing Assertion `[grep + LLM confirmation]`

Two candidate sub-patterns where a discarded expression may be standing in for
the scenario's only verification. The standalone expression is always dead
code, but it is P0 #8 only when the test otherwise has no independent
meaningful postcondition or failure-producing action for the promised behavior.

**8a. Dangling locator** `[Playwright only, grep-detectable]` — a Playwright locator created as a standalone statement, not assigned to a variable, not passed to `expect()`, and not chained with an action. The statement is a complete no-op.

```typescript
// BAD — locator created and immediately discarded
await page.locator('.selector');
page.getByRole('button'); // also bad — not even awaited
```

**8b. Boolean result discarded** — `isVisible()` / `isEnabled()` / `isChecked()` / `isDisabled()` / `isEditable()` awaited as a standalone statement. The boolean resolves and is thrown away.

```typescript
// BAD — boolean computed but never checked; asserts nothing
await el.isVisible();
await el.isEnabled();
await page.isVisible('[data-testid="foo"]'); // page-level shorthand with a selector arg — same discard
```

**Rule:** Every Playwright locator expression and every Playwright boolean
state call must either feed into `expect()`, be assigned and used later, or be
chained with an action. Standalone Playwright expressions are dead code, but
report P0 #8 only when the discarded expression is the scenario's intended
verification and removing it leaves no independent meaningful verification or
failure evidence. Skip a leftover read in a test that already has real
assertions. Also skip a discarded pre-check immediately followed by an action
on the same locator: the action can fail on absence/actionability, while a
missing outcome assertion is #2 anchored at the action. Do not generalize this
rule to Cypress: `cy.get(...)` is a retrying query that requires the element to
exist even without a `.should(...)` chain.

**Fix:** Replace with web-first assertion — `await expect(locator).toBeVisible()` / `toBeEnabled()` etc. These also auto-retry. Or delete the line if it's leftover debug code.

**Detection note:** the scanner sends both the empty-parens form and the
page-level selector-argument shorthand (`await page.isVisible('sel')`), with or
without a trailing semicolon, to `[P0?][LLM-TRIAGE]`; grep alone never enters
these hits into the P0 exit gate. The end-of-statement anchor means
handled/chained forms are not candidates:
`await el.isVisible().catch(() => false)` (covered by `#3` error-swallow),
`&& ...`, ternaries, and assigned reads
(`const v = await el.isVisible()`) all pass.

#### 12. Missing Auth Setup `[LLM-only]`

**Symptom:** A spec navigates to a protected route without auth, and the resulting login or other wrong surface still satisfies the test's actual assertions.

**Why it matters:** The test passes against the wrong page and silently reports feature coverage it never exercised.

**Rule:** First prove the route is protected. Then determine whether the login/wrong surface can satisfy the test's actual assertions. Flag P0 only when both conditions hold and no auth mechanism is supplied by the spec, config, support hooks, or fixtures. Anchor the finding at the causal navigation line. If the wrong surface makes the assertion fail, missing auth is a setup problem rather than a silent always-pass defect: do not report #12 as P0.

**Config read is mandatory, not optional (severity-stability rule).** Path (b) is invisible from the spec file: a `setup` / `global.setup` project plus a project-level `storageState` in `playwright.config.*` authenticates every spec in that project with nothing in the spec itself. Cypress equivalents are `cy.session()` in a support file and `cypress.config.*` `setupNodeEvents` login tasks. **Open the config and read the `projects` array before deciding severity.** Reviewers who skip this step flag every protected-route spec P0 while reviewers who read it flag none — the same suite then scores 0, 1, or 2 Real P0s across runs, which breaks the counting contract. If the config cannot be located, say so in the finding rather than assuming either way.

---

### P1 — Should Fix (poor diagnostics / wastes CI time)

Tests work but mislead developers, waste CI time, or set up future regressions. Check on every review.

#### 15. Missing `await` on `expect()` `[grep-detectable]`

**Symptom:** An async Playwright Locator/Page web-first matcher or retry
assertion (`expect.poll(...).toX()`, `expect(fn).toPass()`) is called without
observing its Promise.

```typescript
// BAD — matcher starts, but later work is not sequenced after it
expect(page.locator('.toast')).toBeVisible();

// BAD — await is on the Locator (a no-op), not on the async matcher
expect(await page.getByTestId('toast')).toBeVisible();

// GOOD
await expect(page.locator('.toast')).toBeVisible();
```

**Why it matters:** The matcher runs outside the test's intended sequence. Under Playwright 1.62, a rejection normally fails the current test or worker through `unhandledRejection`, often after teardown has started and with degraded attribution. A matcher that resolves can still race later work.

**Rule:** Report P1 when an async Locator/Page web-first matcher,
`expect.poll(...).toX()`, or `expect(fn).toPass()` is not `await`ed or returned.
Awaited/returned retry assertions are explicit guards. Prove the called
`expect` binding through its own local declaration/import/re-export lineage;
the presence of a Playwright `test` export elsewhere in a mixed fixture/barrel
does not make a custom `expect` Playwright-owned.

**Boundary with #4c-4e (the #15/#4 split):** Sync value matchers are excluded. `expect(await x.isVisible()).toBe(true)`, `expect(Number(await getRowCount(page))).toBe(4)`, and other value-resolving reads (including wrapped forms) resolve a real value and are #4c-4e, not #15. Matcher-on-next-line splits are covered by Tier 2 (`sg-15`).

**Escalation/dedupe:** If code catches or otherwise swallows the floating matcher's rejection, report #3 P0 for error swallowing. If the scenario also lacks an independent postcondition, #2 P0 may apply. Keep #15 as the P1 sequencing defect; do not inflate it to P0.

**Retry-wrapper boundary:** `toPass()` / `expect.poll()` can retry only the Promise returned by their callback. An unawaited matcher Promise that the callback neither awaits nor returns floats independently, so report #15 inside retry callbacks exactly as elsewhere.

#### 16. Missing `await` on Playwright Actions `[grep-detectable]`

**Symptom:** A Playwright Locator action starts without the test observing its Promise.

```typescript
// BAD — actionability, ordering, or navigation can race the next line
page.locator('#submit').click();

// GOOD
await page.locator('#submit').click();
```

**Why it matters:** Actionability checks, the action itself, and any resulting navigation are no longer sequenced with later test work. Under Playwright 1.62, rejection normally fails the current test or worker through `unhandledRejection`, often with degraded teardown attribution.

**Rule:** Report P1 when an action in the supported Playwright Locator subset (`.click()`, `.dblclick()`, `.tap()`, `.fill()`, `.clear()`, `.type()`, `.press()`, `.pressSequentially()`, `.check()`, `.uncheck()`, `.setChecked()`, `.selectOption()`, `.setInputFiles()`, `.hover()`, `.focus()`, `.blur()`, `.dragTo()`, `.drop()` in Playwright 1.62, `.dispatchEvent()`, `.scrollIntoViewIfNeeded()`, `.selectText()`, `.screenshot()`) is not `await`ed or returned. This is an explicit action subset, not a claim that every asynchronous Locator method is mechanically covered.

**False-positive exclusions (Phase 2):**
- **Observed Promise combinator arrays:** SKIP a hit when the action is an array element passed to `Promise.all`, `Promise.race`, `Promise.allSettled`, or `Promise.any` and that aggregate is itself syntactically led by `await` or `return` — including when the closing `]` is on the action line. Do not suppress a bare or merely assigned aggregate: although the combinator receives the element, its aggregate Promise still floats.

**Locator/POM receiver sweep:** Direct `page.locator(...).click()` is only one shape. Scan Playwright-proven specs, POMs, and support TS/JS, then inspect action statements on local Locator variables and POM properties, such as `saveButton.click()` and `this.submitButton.click()`. Walk bounded multiline chains back to their receiver and report the physical action line. Trace non-`page` receivers to a Playwright `Locator`; do not classify arbitrary application objects by method name alone. A logical chain led by `await` or `return` is already consumed and must not be reported.

Unawaited `page.goto(...)`, `page.reload(...)`, `page.waitForURL(...)`,
`page.waitForNavigation(...)`, `page.goBack(...)`, `page.goForward(...)`, and
`locator.waitFor(...)` follow the same #16
Promise-observation contract; their awaited/returned forms are excluded.

**Escalation/dedupe:** If code catches or otherwise swallows the action rejection, report #3 P0. If the flow lacks an independent postcondition after the action, #2 P0 may also apply. Keep #16 as the P1 action-ordering defect.

**Retry-wrapper boundary:** A retry wrapper does not exempt #16. If its callback neither awaits nor returns an action Promise, the wrapper has nothing to observe or retry.

#### 6. Raw DOM Queries (Bypassing Framework API) `[grep-detectable]`

**Symptom:** Test or POM uses `document.querySelector*` / `document.getElementById` inside `evaluate()` or `waitForFunction()` when the framework's element API could do the same job. Check both spec files and POM files — raw DOM in a POM helper is equally harmful since it bypasses the same auto-wait guarantees.

**Why it matters:** No auto-waiting, no retry, boolean trap, framework error messages lost.

```typescript
// BAD
await page.waitForFunction(() => document.querySelectorAll('.item').length > 0);
const has = await page.evaluate(() => !!document.querySelector('.result'));

// GOOD
await page.locator('.item').waitFor({ state: 'attached' });
await expect(page.locator('.result')).toBeVisible();
```

**Rule:** Use the framework's element API instead of raw DOM:
- **Playwright:** `locator.waitFor({ state: 'attached' })` replaces `waitForFunction(() => querySelector(...) !== null)`; `page.locator()` + web-first assertions replaces `evaluate(() => querySelector(...))`
- **Cypress:** `cy.get()` / `cy.find()` — avoid `cy.window().then(win => win.document.querySelector(...))`

Only use `evaluate`/`waitForFunction` when the framework API genuinely can't express the condition: multi-condition AND/OR logic, `getComputedStyle`, `children.length`, cross-element DOM relationships, or `body.textContent` checks. Add `// JUSTIFIED:` explaining why.

#### 9. Hard-coded Sleeps `[grep-detectable]`

**Symptom:** Explicit sleep calls pause execution for a fixed duration instead of waiting for a condition.

Sub-variants share this entry: `#9` Playwright `waitForTimeout`, `#9b` Cypress `cy.wait(ms)` (identifier arguments remain LLM-triage until the value is resolved), `#9c` Playwright `waitForLoadState('networkidle')` — networkidle is explicitly discouraged by Playwright docs as unreliable on modern SPAs; replace with a web-first assertion on the element the test actually needs.

```typescript
// BAD — arbitrary delay; still races if render takes longer
await page.waitForTimeout(2000);
cy.wait(1000);

// GOOD — wait for condition
await expect(modal).toBeVisible();
cy.get('[data-testid="modal"]').should('be.visible');
```

**Rule:** Never use explicit framework sleep (`Page.waitForTimeout` / `cy.wait(ms)`) — rely on framework auto-wait or condition-based waits. The scanner requires Page fixture/type provenance before making `waitForTimeout` gate-ready, so an unrelated `fakeClock.waitForTimeout()` is not a finding.

Note: `timeout` option values in `waitFor({ timeout: N })` or `toBeVisible({ timeout: N })` are NOT flagged — these are bounds, not sleeps.

#### 10. Flaky Test Patterns `[LLM-only + grep]`

Two sub-patterns that cause tests to fail intermittently in CI or parallel runs.

**10a. Positional selectors** — locator `nth()`, `first()`, and `last()` without a comment break when DOM order changes. The scanner deliberately emits broad method-name candidates as `[P1?][LLM-TRIAGE]`; Phase 2 must first prove the receiver is a Playwright/Cypress locator. Unrelated methods such as a database query builder's `.first()` are not findings.

Scan Playwright/Cypress-proven POM/support files as well as specs for positional locators. POM encapsulation is not an exemption: moving a positional locator into a semantically named Page Object method does not make it stable. Only a method name that explicitly promises positional access may use the method-name exemption. When a positional locator targets a collection that is conditionally rendered or reordered by viewport, feature flags, permissions, or state, inspect those render conditions before resolving the candidate.

```typescript
// BAD — breaks if DOM order changes
await expect(items.nth(2)).toContainText('expected text');
```

**Rule:** Prefer `data-testid`, role-based, or attribute selectors. If `nth()` is unavoidable, add `// JUSTIFIED:` explaining why.

**Exemptions (no `// JUSTIFIED:` needed):**
- **Method-name self-documents intent** — when the enclosing method's name explicitly conveys positional access (e.g., `getParagraphByIndex(index) { return this.paragraphs.nth(index); }`, `nthRowOf(...)`, `firstResult()`). The name documents the intent.
- **Fallback selector loops** — `.first()` inside `for (const selector of fallbackSelectors) { … this.page.locator(selector).first() … }`. Here `.first()` means "any match for this candidate selector", not "the first of multiple known elements".
- **Single-result `toHaveCount(1)` adjacent** — `await expect(items).toHaveCount(1); const only = items.first();` (the count assertion documents that exactly one element exists).

**Selector priority** (best → worst, per [Playwright docs](https://playwright.dev/docs/best-practices#use-locators)): `getByRole` → `getByLabel` → `getByTestId`/`data-cy` → `getByText` → attribute (`[name]`, `[id]`) → class → generic. Class and generic selectors are "Never" — coupled to CSS and DOM structure.

**10b. Serial test ordering** `[Playwright only]` — `test.describe.serial()` and `test.describe.configure({ mode: 'serial' })`, including multiline configuration objects, make tests order-dependent: a single failure cascades to all subsequent tests, and the suite can't be sharded.

**Rule:** Replace serial suites with self-contained tests using `beforeEach` for shared setup. If sequential flow is genuinely required, use a single test with `test.step()` blocks. If serial is unavoidable, add `// JUSTIFIED:` on the line above `test.describe.serial(`.

**10c. Unscoped accessible-name substring match** `[grep + LLM]` — a page-scoped Playwright `getByRole` / `getByLabel` / `getByPlaceholder`, or Cypress Testing Library `cy.findByRole` / `cy.findByLabelText` / `cy.findByPlaceholderText`, with a `name` and **no `exact: true`**. Per [Playwright docs](https://playwright.dev/docs/locators#locate-by-role), the `name` option matches the accessible name as a **case-insensitive substring** by default. When the page also renders user- or data-controlled text (note names, search results, list rows, folder titles), that text can contain the same word, so the locator resolves to 2+ elements and Playwright throws a **strict-mode violation** — thrown immediately, no timeout, so it reads as a hard failure or (when the dynamic content only sometimes collides) an intermittent flake.

```typescript
// BAD — 'Job' is a substring of a note named "Nightly Job Report", so this
//       resolves to the header link AND the note-list link → strict-mode violation
await page.getByRole('link', { name: 'Job' }).click();

// GOOD — exact accessible name, scoped to the container it lives in
await page.getByRole('navigation').getByRole('link', { name: 'Job', exact: true }).click();
```

**Rule:** A `getByRole`/`getByLabel`/`getByPlaceholder` with a `name` should either be **scoped to a container locator** (`page.locator('.header').getByRole(...)`) or use **`exact: true`** — ideally both — whenever the surrounding page can render dynamic text that might contain the name as a substring. This is the official disambiguation guidance for strict-mode collisions.

**Fix:** Add `exact: true` to the `name` option, and/or chain the accessor off a stable container locator that bounds the search subtree.

**Exemptions (skip in Phase 2 — no `// JUSTIFIED:` needed):**
- **Already scoped:** the accessor is chained off a non-`page` locator (`someContainer.getByRole(...)`) — the subtree already bounds the match.
- **Already exact:** the call includes `exact: true`.
- **Regex name:** `name: /^Job$/` — an anchored regex is as precise as `exact`.
- **Static-only surface:** the suite under test renders no user- or data-controlled text that could contain the name (e.g. a fixed marketing page). Judge by whether the app paints dynamic list/entity text, not by the word alone — a distinctive multi-word name like `"Switch to Classic UI"` is low-risk; a short common word (`"Job"`, `"Run"`, `"Save"`, `"New"`) on a page with dynamic content is the real hit.

**Cypress equivalent:** `cy.findByRole('link', { name: 'Job' })` (cypress-testing-library) has the same substring default — prefer `{ name: 'Job', exact: true }` or scope with `.within()`.

**10d. Cypress async callback** `[Cypress only]` `[grep + LLM-TRIAGE]` — an `async` test or hook callback that also queues `cy` commands mixes a returned Promise with Cypress's command queue. The bundled scanner recognizes common arrow/function callback starts and confirms `cy.*` in a bounded body window; Phase 2 confirms nested/multi-line callback boundaries. Remove `async`/`await` and keep Cypress work in the command chain; use `cy.then()` for a real Promise boundary. Do not flag a native-Promise-only async callback as this command-queue smell.

**10e. Assigned Cypress command return** `[Cypress only]` — `const value = cy.get(...)` stores a Chainable, not the yielded DOM/application value. The bundled scanner covers same-line declarations, including TypeScript annotations; Phase 2 checks split declarations. Keep dependent assertions in `.then()`/`.should()` or use an alias. Do not flag ordinary application-value assignment or Cypress's synchronous Sinon utilities `cy.spy()`/`cy.stub()`, which intentionally return the created test double.

**10f. Unsafe continued Cypress action chain** `[Cypress only]` `[grep + LLM-TRIAGE]` — an action such as `.click()` or `.type()` is followed by another assertion/action in the same chain. The bundled scanner reconstructs bounded same-line and multiline chains; Phase 2 confirms the subject-stability risk. Cypress retries queries and assertions but not the action, so the continued chain can retain a detached/stale subject. End the chain and re-query the intended post-action state. Skip when project evidence proves the subject remains stable and the chain is intentionally atomic.

#### 13. Inconsistent POM Usage `[LLM-only]`

**Symptom:** A POM class is imported and used for some actions, but the spec also uses raw `page.fill()` / `page.click()` for operations the POM should encapsulate.

**Why it matters:** Defeats the purpose of the POM pattern — when the UI changes, you must update both the POM and the spec. DRY principle violated.

**Rule:** If a POM exists for a page, all interactions with that page should go through the POM. Flag P1 if spec bypasses POM with raw `page.*` calls for actions the POM should own. Suggest adding missing methods to the POM.

#### 14. Hardcoded Credentials `[grep-detectable]`

**Symptom:** String literals used as usernames, passwords, or API keys directly in test code.

```typescript
// BAD — credentials as string literals
await loginPage.login('demo-admin', '<literal-password>');
await page.fill('#password', '<literal-secret>');
```

**Why it matters:** Security risk if repo is public, couples tests to specific credentials, prevents running tests against different environments.

**Rule:** Use environment variables (`process.env.TEST_USER`), Playwright config secrets, or test data fixtures. Flag P1.

**Scope — only flag actual credentials, not input test data:**
- **Flag** literals passed to authentication operations: `loginPage.login('demo-admin', '<literal-password>')`, `page.locator('#password').fill('<literal-password>')` followed by submit, API calls posting credentials, fixtures named `validUser` / `testAdmin`.
- **Do NOT flag** literals used only to verify form input behavior (no auth attempt follows): `passwordInput.fill('anyText'); await expect(passwordInput).toHaveValue('anyText');` — this is input-acceptance testing, not credential storage. Intentional invalid-creds fixtures with dummy username/password values are also fine because they document a negative-path scenario.

When grep flags a literal, read 2–3 lines below to confirm a login/auth call follows. If none, skip.

The bundled scanner emits these as `[P1?][LLM-TRIAGE]` candidates. Its lexical
filter requires a credential-shaped field/auth call plus a literal-shaped
value and drops `process.env`, `import.meta.env`, `Cypress.env()`, `Deno.env`,
and `Bun.env` values. This reduces obvious false positives but does not replace
the authentication-context check above.

API auth payloads and reusable positive fixtures such as `validUser` and
`testAdmin` are included in this candidate sweep. They remain triage because
negative-path dummy credentials and form-input test data are legitimate.

#### 17. Discouraged Direct Page Selector API `[grep-detectable, Playwright only]`

**Symptom:** Using selector-based Page actions such as `page.click('#button')` or `page.fill('#input', 'text')` instead of the locator-based API. These APIs are discouraged in favor of Locators; do not describe them as deprecated.

Scan Playwright-proven POM/support TS/JS as well as specs. A direct `page.*` call is final only when lexical fixture/type provenance proves that receiver is a Playwright `Page`; a locally shadowed application object named `page` remains LLM triage. Literal `this.page.*`, renamed parameters, and other receivers are also triage until their declaration/import proves a Playwright `Page` (including aliased `Page` types), at which point the scanner can promote the hit. Do not classify arbitrary object methods from the action name alone.

```typescript
// BAD — direct page action
await page.click('#submit');
await page.fill('#email', 'user@test.com');

// GOOD — locator composition, strictness, and clearer failures
await page.locator('#submit').click();
await page.locator('#email').fill('user@test.com');
```

**Why it matters:** `page.click(selector)` skips the Locator layer, losing locator composition and producing worse review/error context. Playwright docs recommend locator-based actions.

**Rule:** Flag P1 for selector-based `page.click`, `page.dblclick`, `page.tap`, `page.fill`, `page.type`, `page.press`, `page.check`, `page.uncheck`, `page.setChecked`, `page.selectOption`, `page.setInputFiles`, `page.hover`, `page.focus`, `page.dispatchEvent`, and `page.dragAndDrop`. Literal selectors on fixture/type-proven Page receivers can be final. Variable selector arguments, Page-shaped POM receivers, and unresolved package fixtures remain LLM-triage until receiver provenance is confirmed. Suggest migrating to Locator actions. Do not map this finding to `playwright/no-element-handle`; that rule checks a different API shape.

#### 18. `expect.soft()` Overuse `[grep-detectable + LLM]`

**Symptom:** A scenario-critical `expect.soft()` (including a provenance-backed alias of Playwright `expect`) is a prerequisite for a later
action or check, so the test continues into that dependent work when the
prerequisite is broken.
Playwright still records each soft assertion error and fails the test at the
end; this is a diagnostic/control-flow problem, not error swallowing.

```typescript
// BAD — edit depends on the profile form that was only soft-checked
test('should edit profile', async ({ page }) => {
  const form = page.getByTestId('profile-form');
  await expect.soft(form).toBeVisible();
  await form.getByLabel('Display name').fill('Alice');
  await form.getByRole('button', { name: 'Save' }).click();
});

// GOOD — hard gate, then an all-soft terminal set of independent details
test('should display profile', async ({ page }) => {
  await expect(page.locator('.profile')).toBeVisible();          // hard gate
  await expect.soft(page.locator('.name')).toHaveText('Alice');  // independent detail
  await expect.soft(page.locator('.email')).toHaveText('a@b.c'); // independent detail
  await expect.soft(page.locator('.locale')).toHaveText('en-US');// independent detail
});
```

**Rule:** Flag P1 only when a scenario-critical soft assertion is a prerequisite
for a later action or check and that dependent work runs without an intervening
hard assertion proving the prerequisite. Independent terminal details are
legitimate even when every detail assertion is soft. Do not use a numeric
soft-assertion count or ratio as the verdict. Anchor the finding at the soft
prerequisite line.

#### 19. Module-Level Mutable State In Test Utilities `[grep-detectable + LLM]`

**Symptom:** Top-level (column-0) mutable state in a test utility, helper, or POM file — state that persists across test invocations within the same worker. The binding keyword does not decide it: an initialised `let`, a `var`, and a `const` holding a container that is mutated later (`const seen = new Set()`, `const cache = new Map()`) all survive a worker unchanged. The scanner emits only the initialised `let`; the other two reach Phase 2 through the mandatory sweep.

```typescript
// BAD — module-level counter; survives across tests in the worker
let testNotebookSequence = 0;

export async function createTestNotebook(page: Page) {
  testNotebookSequence += 1;
  const name = `notebook_${testNotebookSequence}_${Date.now()}`;
  // ...
}

// GOOD — derive uniqueness from data that's already unique
export async function createTestNotebook(page: Page) {
  const name = `notebook_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  // ...
}
```

**Why it matters:** Playwright/Cypress run specs across multiple worker processes in parallel. Module-level mutable state survives across tests within a long-lived worker but is independent across workers — so the same counter value can appear in two specs running concurrently in different workers, breaking the "unique" contract the variable was supposed to provide. Playwright discards a failed test's worker before retrying in a fresh worker; this rule is about cross-test persistence and cross-worker collisions, not retry survival. These bugs surface as intermittent name collisions or flake.

**Rule:** Flag P1 when a `let` at column 0 has an initializer. The scanner excludes declaration-only bindings such as `let page: Page;` mechanically; they are not final findings awaiting an LLM skip. Suppress initialized state with `// JUSTIFIED: [reason]` when it is intentionally shared (e.g., a worker-scoped cache the framework's parallelism guarantees won't collide).

**Phase 2 confirmation:** the scanner has already removed pure type declarations such as `let page: Page;` and `let context: BrowserContext;`. For emitted initialized lets such as `let counter = 0;`, `let cache = new Map();`, or `let lastResult: Result | null = null;`, confirm the binding is test-shared mutable state rather than a justified worker-scoped cache.

**Fix pattern:** Replace counter-based uniqueness with `Date.now()` + `Math.random().toString(36).slice(2, 8)`, or use Playwright's `testInfo.workerIndex` for worker-scoped uniqueness, or move the state into a `test.beforeEach` so it's per-test rather than per-worker.

---

#### 20. Unmocked Real-Backend Writes `[LLM-only]`

**Symptom:** A spec drives a write or credential path — signup, login, checkout, any data mutation — and no route stub (`page.route()` / `cy.intercept()`) in the spec or its fixtures covers the endpoint, so every run reaches a real backend.

**Why it matters:** Each CI run creates real accounts, real orders, or real charges: shared-environment data pollution, rate-limit and quota flakiness, and PII/credential exposure in backend or third-party logs. The test is also non-deterministic — backend state, not the code under test, decides whether it passes.

```typescript
// BAD — every run registers a real account on the shared backend
await signUpPage.fillForm(`test+${Date.now()}@corp.com`, 'hunter22!');
await signUpPage.submitButton.click();

// GOOD — the write is stubbed; the test asserts the app's handling of the response
await page.route('**/api/auth/join**', r =>
  r.fulfill({ status: 200, contentType: 'application/json', body: '{"result":"SUCCESS"}' }));
await signUpPage.fillForm('user@example.com', 'hunter22!');
await signUpPage.submitButton.click();
```

**Rule:** A write test must prove that its backend boundary is controlled. A
route stub is one valid strategy, but documented disposable containers,
transaction rollback fixtures, isolated test tenants/databases, and dedicated
ephemeral backends are also valid. Flag only when repository evidence shows the
write can reach shared, persistent, chargeable, rate-limited, or otherwise
uncontrolled state. Mark intentional full-stack strategies with a concrete
`// JUSTIFIED:` rationale or repository-level test-environment documentation.

**Detection (LLM):** In each spec, list actions that submit forms or trigger
mutation-shaped requests (signup/login/checkout/save/delete). Confirm from the
component, handler, helper, request assertion, or fixture contract that the
action really fires a backend write; an action name alone is insufficient. Then
trace the isolation strategy across route helpers, fixtures, configs, container
setup, tenant/database lifecycle, and cleanup/rollback hooks. Flag only when the
available repository evidence establishes an uncontrolled boundary.

**Primary line:** Anchor #20 to the submit/click/action that triggers the
unstubbed write. The missing route is repository context, not a source line to
invent.

#### 22. Optimistic UI Without Call Proof `[LLM-only]`

**Symptom:** An interaction test clicks a write control (like toggle, delete, save) and asserts only the resulting UI state — but the app updates that UI *optimistically*, before (and regardless of) the network call. The assertion passes even if the wiring to the API is deleted.

**Why it matters:** This is a false positive specific to write interactions: the visible behavior under test is produced client-side, so the test proves the click handler ran, not that the write reached the backend contract. A regression that drops the API call (refactor, early return, swallowed promise) ships green.

```typescript
// BAD — aria-pressed flips optimistically; passes with the POST deleted
await likeToggle.click();
await expect(likeToggle).toHaveAttribute('aria-pressed', 'true');

// GOOD — request proof + UI state
const call = page.waitForRequest(r =>
  r.method() === 'POST' && r.url().includes('/user/sentence/like'));
await likeToggle.click();
await call;
await expect(likeToggle).toHaveAttribute('aria-pressed', 'true');
```

**Rule:** Every write-interaction test pairs its UI assertion with proof the request fired: `page.waitForRequest()`, a route-handler hit flag, or an assertion on mocked-request capture. Set up `waitForRequest` *before* the click to avoid racing fast responses.

**Detection (LLM):** For each test that clicks a control whose handler issues a mutation, confirm from the component, handler, helper, or fixture contract that the UI updates optimistically before or regardless of the request. If the only assertions are on that optimistic DOM/UI state and the spec awaits no request evidence, flag. Do not infer optimistic behavior from a write-shaped action name when the supplied scope lacks implementation evidence. Tests of pure client-side state (no request in the handler) are not hits.

**Primary line:** Anchor #22 to the write-control action. The following UI-only
assertion explains why the test is insufficient but is not the causal line.

---

### P2 — Nice to Fix (maintenance / robustness)

Weak but not wrong. Address when refactoring or before adopting wider conventions.

#### 11. YAGNI + Zombie Specs `[LLM-only]`

Two sub-patterns: unused code in Page Objects, and zombie spec files.

**11a. YAGNI in Page Objects and Utility Modules** — POM or utility/helper file
has locators, methods, or exported functions never referenced by any spec or
other module. A single-use member is only a review candidate: report it when
inlining clearly removes indirection without duplicating meaningful setup,
erasing stable domain vocabulary, or violating an established repository
boundary. Or a POM class extends a parent with zero additional members and no
documented convention justifies the type boundary.

**Procedure:**
1. List all public members of each changed POM file AND all exported symbols of each changed utility module (`utils.ts`, `helpers.ts`, `fixtures.ts`, etc.)
2. Grep each member/export across all test files, POMs, and other utility modules
3. Classify: USED / INTERNAL-ONLY (`private` for POMs, non-`export` for utility modules) / UNUSED (delete) / SINGLE-USE (inline at the call site)
4. For a single-use symbol, inspect complexity, domain meaning, and repository
   conventions before deciding whether inlining is an improvement.
5. Check if any POM class has zero members beyond what it inherits — empty
   wrappers add no value unless the convention is intentional.

**Common patterns:** Convenience wrappers (`clickEdit()` when specs use `editButton.click()`), getter methods (`getCount()` when specs use `toHaveCount()`), state checkers (`isVisible()` when specs assert on locators directly), pre-built "just in case" locators, empty subclass created for future expansion. In utility modules: single-use auth helpers (`isLoginPageVisible()` called by exactly one other utility), single-use REST helpers (`getDefaultInterpreterGroup()` called by exactly one create function), single-use waits (`waitForNotebookParagraphVisible()` invoked from one navigation helper).

**Single-use Util wrappers** — a separate `*Util` / `*Helper` class OR a
standalone exported function called from only one place warrants inspection,
not automatic deletion. Inline only when the wrapper adds no stable domain
vocabulary, reusable validation, non-trivial setup boundary, or documented
architectural role.

**Rule:** Delete unused members and exports. Make internal-only POM members
`private`; drop the `export` keyword from utility functions used only inside
their own module. Treat usage count as evidence, not the verdict: recommend
inlining a single-use helper only when the resulting code is simpler and the
boundary carries no independent meaning. Flag empty wrapper classes for review
when no documented convention explains them.

**11b. Zombie spec files** — An entire spec file whose tests are all subsets of tests in another spec file covering the same feature. The file adds no coverage that isn't already verified elsewhere.

**Procedure:** After reviewing all files in scope, cross-check spec files with similar names or feature coverage. If every test in file A is a subset of a test in file B, flag file A for deletion.

**Common patterns:** `feature-basic.spec.ts` where every case also appears in `feature-full.spec.ts`; a 1–2 test file created as a "quick smoke" that was never expanded while a comprehensive suite grew alongside it.

**Rule:** Delete the zombie file. If any test in it is not covered elsewhere, migrate it to the comprehensive suite first.

**Output:**
```
| File | Member | Used In | Status |
|------|--------|---------|--------|
| modal-page.ts | openModal() | (none) | DELETE |
| modal-page.ts | closeButton | internal only | PRIVATE |
| search-page.ts | (class body empty) | — | REVIEW |
| basic.spec.ts | (entire file) | covered by full.spec.ts | DELETE |
```

#### 21. Manually-Captured Session-File Dependency `[LLM-only]`

**Symptom:** A spec, fixture, or project config loads a `storageState` JSON (e.g. `auth/member.json`) that only a manual capture script or a developer's one-off login produces — nothing in the automated test setup can regenerate it.

**Why it matters:** The file is absent on fresh clones and CI, and silently expires. The suite then fails — or worse, soft-skips — for reasons unrelated to the code under test, and nobody trusts the signal. A committed `storageState` file is also a credential leak, not just an unreproducible fixture: it holds live session cookies — and any bearer tokens the app keeps in origin storage — for whatever account captured it. #14 does not reach this — its scope is string literals in test code.

**Rule:** Session state must be reproducible from code: an API-login helper or a `setup` project that writes `storageState` before dependent specs run. A committed or manually captured file may serve only as a cache with a programmatic fallback.

**Detection (LLM):** For each `storageState:` reference (spec, fixture, or `playwright.config` project), trace what writes that path. If only a manual script — or nothing in-repo — produces it, flag. `storageState:` is Playwright-only, so sweep the Cypress equivalents too: a session JSON loaded through `cy.fixture(` and replayed with `cy.setCookie`/`cy.setAllCookies`/`localStorage` restore, or a `cy.session()` setup whose callback reads a committed file instead of logging in. The defect is the same — the file is absent on a fresh clone and expires silently — and the rule is not framework-scoped.

#### 23. Fixture Ignores Conditional Render Guards `[LLM-only]`

**Symptom:** A seeded list/item fixture satisfies the API type but not the *render guards* of the component that displays it — e.g. a "Liked" tab whose item component does `if (tabIsLiked && !item.liked) return null;`, while the fixture seeds `liked: false`. The UI renders an empty container; the test fails with "element not found" that looks like infra flake, or—worse—a negative assertion (`toHaveCount(0)`, empty-state check) passes for the wrong reason.

**Why it matters:** Type-correct fixtures aren't render-correct fixtures. Components self-hide on field+view-state combinations (`liked` in a liked view, `enabled`, `membershipOnly`, date windows, `items.slice(1)` init drops), and these guards live in the component, not the API contract. Hours go to debugging "flaky" tests whose mock data was simply unrenderable.

**Severity:** P2 for the usual case, where the guard leaves the container empty and the test fails with a confusing "element not found". Report the variant this pattern calls worse — a negative assertion or empty-state check that passes because the guard suppressed the seeded items — at P0: nothing the test promised is verified, and it stays green while the feature is broken.

**Rule:** Before seeding a list fixture, read the item component's early returns and filters; seed fields so the item passes every guard for the view under test. Document each discovered guard next to the fixture (e.g. "Like-tab items must seed `liked: true`") so the next generated test doesn't rediscover it.

**Detection (LLM):** For each fixture consumed by a conditionally-rendered component, open the component and collect conditions that suppress rendering (early `return null`, `.filter()`, `.slice()`, a template guard such as `@if`/`v-if`/`{cond && …}` around the whole subtree). Cross-check the seeded values against them. Flag mismatches, and flag negative assertions whose truth could come from a guard-suppressed render rather than the intended state.

**Scope note:** the guard need not sit on a list/card item — the same failure appears whenever a *container* is gated on a value the test controls indirectly. A results panel wrapped in `@if (result.type === TABLE)` suppresses every control inside it when the fixture produces a different result type, so a test targeting a toolbar button inside that panel fails with "element not found" and looks like infra flake. When a control the test needs is missing, walk up the template to the nearest guard before suspecting the selector.

---
