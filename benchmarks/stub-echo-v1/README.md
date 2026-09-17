# Stub-echo v1 — does a `#4l` rule earn its place?

**This protocol is frozen before any candidate is collected.** It decides in
advance what would make the proposed reviewer sub-pattern worth shipping, what
would make it P0, and what result sends it to documentation instead. The
machine-readable copy is [`protocol.json`](protocol.json); if this page and that
file disagree, the JSON controls.

## The proposed pattern

`#4l` would flag an assertion whose subject is a response the same test stubbed:

```typescript
// CANDIDATE — the assertion reads back the fixture the test just installed
await page.route('**/api/cart', route =>
  route.fulfill({ status: 200, body: JSON.stringify({ items: 2 }) }));
const response = await page.waitForResponse('**/api/cart');
expect((await response.json()).items).toBe(2);   // true for any product build
```

```typescript
// NOT THIS PATTERN — the app fetched, parsed, and rendered the stub
await page.route('**/api/cart', route => route.fulfill({ ... }));
await expect(page.getByTestId('cart-count')).toHaveText('2');
```

The second shape is this repository's own documented fix for `#20`
(`skills/e2e-reviewer/references/pattern-reference.md`). A rule that cannot tell
the two apart would flag the guidance the bundle already gives, so the
separation is the whole question.

## Hypotheses

- **H1 (prevalence):** the stub-echo shape occurs in real public Playwright and
  Cypress suites often enough to justify a scanner rule.
- **H2 (severity):** a stub-echo assertion is an always-pass with respect to the
  product: it stays green under a product fault that a user-visible assertion on
  the same behavior catches.
- **H3 (separability):** a mechanical detector can separate stub-echo
  assertions from assertions on rendered output and from assertions on the
  request the application itself sent.

## Corpus (frozen)

The twelve repositories of [`field-scan-v1`](../field-scan-v1/README.md), at the
same pinned commits recorded in its `repos.json`. That pool was selected by a
frozen popularity rule that excludes every repository this project has ever
opened a pull request against, so this measurement inherits its contamination
exclusion. No repository is added, dropped, or swapped after collection starts.

## Candidate collection (frozen)

`collect_candidates.py` in this directory is the only collector. It is
deterministic, runs no model, and publishes every candidate it finds — file,
line, and the matched snippet — with no filtering for how the hit looks.

A candidate is a spec-file line where a test observes a response object
(`page.waitForResponse`, `page.waitForEvent('response')`, `cy.wait('@alias')`)
inside a file that also installs a stub (`page.route(`, `cy.intercept(`).
The collector is deliberately broader than the proposed rule: it collects the
decision surface, and adjudication measures how much of that surface is real.

## Adjudication (frozen)

Every candidate is judged once, by hand, against this rubric, before any
threshold is computed:

| Verdict | Meaning |
| --- | --- |
| `STUB_ECHO` | The asserted value comes from a stub installed in the same test or its fixtures, and no application code had to transform or render it for the assertion to hold |
| `APP_MEDIATED` | The assertion observes something the application produced: rendered output, a request the app sent, a value the app computed from the response |
| `REAL_BACKEND` | The observed response was not stubbed (`route.continue()`, `cy.request`, `page.request`, or no matching stub), so the assertion tests a real server |
| `UNDECIDABLE` | The file does not contain enough context to decide without running the suite |

`UNDECIDABLE` counts against precision; it is not discarded.

## Thresholds (frozen, decided before collection)

| Gate | Test | Pass condition |
| --- | --- | --- |
| G1 prevalence | Adjudicated `STUB_ECHO` instances | at least 5, in at least 2 distinct repositories |
| G2 separability | Wilson 95% lower bound of `STUB_ECHO / adjudicated candidates` | at least 0.50 for the collector, and at least 0.80 for the drafted scanner rule re-run over the same corpus |
| G3 severity | Executable proof in `fixture/` | the stub-echo spec stays green under an injected product fault that turns the rendered-output spec red, and both specs are green without the fault |
| G4 guard | The drafted rule over `fixture/guards/` | zero hits on `route.continue()` pass-through, `page.request`/`cy.request`, `request.postDataJSON()`, and rendered-output assertions |

Outcomes:

- **G1 and G2 and G3 and G4 pass** → implement `#4l` as a P0 sub-pattern of `#4`
  across the seven taxonomy surfaces, with the true-positive and
  false-positive-guard evals AGENTS.md requires.
- **G3 fails** → the shape is not an always-pass; do not add a P0 rule.
- **G1 fails, others pass** → document the shape in the `#4` Phase 2 procedure
  as a form to check by hand; do not add a scanner rule for a shape this corpus
  does not contain.
- **G2 or G4 fails** → keep the Phase 2 documentation and record why a
  mechanical rule was refused.

A result that misses a gate is published here unchanged. No threshold moves
after collection.

## Status

`NOT_RUN`. Collection has not started; this page exists to fix the rules first.
