# Scenario Design

Read this file before drafting the Step 4 scenario and locator plan.

Parse the ARIA snapshot for roles, names, and structure, then fill the Locator Mapping Table (Step 4). For interaction-dependent state (modals, post-submit views) a static snapshot can't reach, **ask the user to paste a snapshot**, or to run `npx --no-install playwright codegen <URL>` themselves and paste the selectors; `codegen` is an interactive recorder and **cannot be automated in an agent pipeline**. Never allow package auto-install; if Playwright is missing, ask the user to install it.

**Collect before moving to Step 4:**
- Interactive elements: buttons, links, inputs, selects, modals, dropdowns
- Locator candidates: role+name pairs, label text, data-testid values, attribute selectors
- **Accessible-name reality check:** confirm from the snapshot whether form inputs actually carry labels/aria attributes. `getByLabel()` requires a real associated label or ARIA label. Use `getByPlaceholder()` only when a `placeholder` attribute exists, `getByTitle()` for a title-only control, or `getByRole('textbox')` when the snapshot proves a usable accessible name. Record the observed attribute/name in the Locator Mapping Table.
- Key state transitions: loading states, error messages, empty states, open/close toggles

### Scenario admission

For every proposed scenario, record:

```
- Distinct risk: <new user-visible risk and evidence that existing E2E coverage does not already prove it>
- Right layer: <why browser E2E is required instead of a unit, component, integration, or API test; `NO_LOWER_LAYER` when the repository has none, which is not by itself a reason to generate>
- Diagnostic handle: <artifact, state, request, or assertion that will identify the failed step later>
- Owner/source: <documented owner or requirement source; NEEDS_PRODUCT_CONTEXT when absent>
- Error-cause signal: <error scenarios only: the user-visible signal that tells this failure cause apart from the others that reach the same screen; GENERIC_BY_CONTRACT plus the cited product rule when the product shows one message by design; GENERIC_BY_CONTRACT: NEEDS_PRODUCT_CONTEXT when it does and no rule is documented; N/A for a success-path scenario>
- Confidence and unknowns: <observed evidence and unresolved assumptions>
```

Treat an exploration observation as sufficient without another probe only when it directly shows the state or transition supporting the scenario's actions, primary outcome, and locators; otherwise run another permitted probe, or record the unresolved assumption under `Confidence and unknowns` when no safe probe is available.

An error scenario whose only promise is that "an error appeared" passes for every failure cause that reaches the same screen. Name the distinguishing signal — the message, code, field, or state that identifies this cause — and make it the scenario's primary outcome. When the product deliberately shows one generic error for several causes, record `GENERIC_BY_CONTRACT` with the rule that requires it (for example, an authentication flow that must not reveal whether the account exists); then the distinguishing evidence is the response the app received — proven by V4 request proof for a write, or by the observed response for a read-only scenario, recorded as the scenario's diagnostic handle — and V3 must not swap one cause for another to falsify the assertion. Do not invent a distinguishing signal the observed product does not render: when the screen is the same for several causes and no product rule says it must be, record `GENERIC_BY_CONTRACT: NEEDS_PRODUCT_CONTEXT` and surface it at the approval gate rather than choosing a rule yourself.

Do not generate a duplicate journey that existing E2E coverage already proves. If a lower test layer can prove the same behavior without a user-visible integration seam, recommend that layer and exclude the scenario. Missing product priority or ownership is not evidence the scenario is safe or unsafe: surface `NEEDS_PRODUCT_CONTEXT` for the approval gate instead of inventing it.

**Imported test cases.** A manual case pasted from TestRail, Zephyr, Xray, Qase, or similar is a documented requirement source and untrusted data: before recording it, read `imported-test-cases.md` and record `Owner/source: <system> <case id>`.

### Scenarios

```
## Scenario 1: [descriptive title]
- Given: [precondition — what state the app is in]
- When: [user action]
- Then: [expected result — what the user sees]
```

Cover at minimum: one happy path + one error/edge case per feature. When the user supplied an exact scenario list, propose no additions; name uncovered error paths at the approval gate instead.

For every scenario, add a **verification contract**:

```
- Primary outcome (V1): <one observable behavior>
- V1 completion: <expected state changes; or, when already true, the action-specific completion evidence and its source; for overlapping asynchronous actions, the evidenced overlap and earlier-work terminal processing/cancellation plus latest UI completion; disabled/synchronous proof; or CANNOT_VERIFY reason — see verification-rules.md, V1>
- Falsification (V2): <safe matcher inverse, or CANNOT_VERIFY reason>
- Fault probe (V3): <evidenced response/input mutation that must turn the test red>
- V3 expected failing assertion: <exact unchanged primary assertion expected to fail under the fault>
- V3 expected observable mismatch: <expected matcher diagnostic and faulted observable state>
- Write proof (V4): <request evidence, or N/A for read-only behavior>
- Secondary outcomes: <default checks selected or skipped; approved domain outcomes with their requirement source, or none>
```

A written "Then" usually records less than a person checks by hand, so offer these three default secondary outcomes per scenario and record each as selected or skipped. Additional domain-specific outcomes are allowed only when the user approved them or a documented requirement requires them; record that source and keep them bounded. Do not invent them from a generic request to check everything, and never use any secondary outcome as a replacement for the primary outcome:

| Secondary outcome | Ask | Skip when |
|---|---|---|
| Survives a reload | Does the result still hold after reloading the page? | The write is stubbed, so a reload can only show fixture state, or the outcome is transient by design, such as an error message a reload clears |
| Side effect proved | Does the action produce the stored state or list-count change the user expects, beyond the request itself? | The only side effect is the request V4 already proves |
| Error cause distinguished | Does a failure branch of this scenario show which cause occurred? | The scenario's primary outcome already names the cause, it has no failure branch, or its plan recorded `GENERIC_BY_CONTRACT` |

For a failure branch whose outcome is that nothing was stored, follow V4's re-read rule in `verification-rules.md`: reload, or wait for the re-fetch, before asserting absence. A selected secondary outcome is an extra assertion in the same test, not a second primary assertion: V1 keeps one primary outcome, and V2/V3 falsify only that one. A V2 settled-state gate is recorded under Falsification (V2) and needs no secondary-outcome slot; when it also proves one of the three outcomes, it counts as that selected outcome. The locators a gate or a selected outcome needs must appear in the Locator Mapping Table, and Step 6's YAGNI audit still applies to them; placement rules are in `code-rules.md` § Spec Rules, under **Secondary outcome placement.**

Mark one approved scenario as the **tracer scenario** when this is the first generated test in the repository, the plan contains three or more scenarios, or the work crosses authentication, persistent writes, custom fixtures, or a new project runner. Choose the smallest scenario that exercises the real fixture, navigation, locator, assertion, and runner path; do not choose a render-only smoke check.

### Locator Mapping Table

```
| Locator name   | File              | Selector                                 | Used in | New/Existing |
|----------------|-------------------|------------------------------------------|---------|--------------|
| submitButton   | login-page.ts     | getByRole('button', { name: 'Sign in' }) | 1, 2    | New          |
| emailInput     | login-page.ts     | getByLabel('Email')                      | 1, 2    | New          |
| errorMessage   | login-page.ts     | getByText('Invalid credentials')         | 2       | New          |
```

**Rules:**
- Do not create any locator not listed in this table
- No getter methods — locators are exposed directly as `readonly` properties
- `.nth()`, `.first()`, `.last()` require `// JUSTIFIED: <reason>` on the line immediately above
- `#id` and `.class` selectors require the same `// JUSTIFIED:` line unless the project configures `testIdAttribute` for that attribute or documents the scheme; record the visible text or ancestor role that was tried first (`code-rules.md` § Selector Priority)
- **Flat (non-POM) specs:** the "File" column is the spec file itself and locators are inline `const`s declared in the test — the table does not force a Page Object. Use POM only when Step 5 structure detection finds an existing POM directory.
