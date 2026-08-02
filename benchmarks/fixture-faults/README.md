# Executable fixture-fault evidence

`2026-07-31-current.json` is the current full 36-cell Playwright/Cypress
execution report produced by `scripts/evals/run-fixture-faults.py`.
`evidence-manifest.json` classifies and hashes every JSON report in this
directory. Ordinary CI validates those immutable archives without requiring a
machine-local `node_modules` tree. Reproducing browser execution remains an
explicit live step after `npm ci --prefix scripts/evals/fixtures`.

For each of twelve fault operators:

1. the strong test passes on the correct app,
2. the same strong test fails after behavior fault injection, and
3. an assertion- or call-proof-mutated weak test stays green against that fault.

The report records fixture, operator, lockfile, selected launch-shim/package
metadata, and evaluator-runner source digests; normalized commands; sanitized
raw per-cell merged stdout/stderr and its hash; mutation hashes;
framework/runtime versions; platform identity; and durations. The current
schema-v4 report additionally hashes every regular file, directory, and
internal symlink in the selected `node_modules` tree, rejects escaping symlinks
or special files, and rechecks the complete dependency provenance after the
matrix finishes. That digest identifies the exact installed code and detects
runtime changes; it is not registry attestation.
The current archive was reproduced on 2026-07-31 and matched all 36 expected
cells with zero infrastructure errors. Output sanitization removes ANSI
escapes, replaces fixture/dependency paths and
the ephemeral fixture URL with stable tokens, and redacts common secret
assignments and bearer credentials. Each output is capped at 64 KiB and records
its original byte count plus a truncation flag; the current 36-cell run did not
require truncation. It is evidence for these pinned minimal fixtures, not a
claim that twelve operators cover the full 24-pattern taxonomy or production
app topology. It proves that the selected weak tests stay green against their
paired faults; it does not measure the fault-detection rate of model-generated
Playwright/Cypress suites.

The twelfth operator is `playwright-aria-snapshot-name` (`#4j`). A strong
`toMatchAriaSnapshot('- button "Increment"')` assertion fails when the app's
accessible label changes to `Delete`, while the mutated `- button` template
stays green. This is the exact partial-matching behavior documented by
[Playwright](https://playwright.dev/docs/aria-snapshots#partial-matching).

`2026-07-31-playwright-1.62-floating-promises.json` is the current separate
negative semantic probe for Playwright 1.62.0. It refreshes the original
`2026-07-30-playwright-1.62-floating-promises.json` result against the hardened
fixture evaluator while preserving the same 6/6 exit matrix. For both a
floating assertion Promise
(#15) and a floating Locator action Promise (#16), the awaited clean call exits
0, the awaited fault exits 1, and deleting only the leading `await` from that
same faulting call still exits 1. The probe uses the existing `behavior-fault`
and `account-view&auth-fault` app paths with 1000ms operation timeouts; it adds
no catch, sleep, app change, or dependency change. This 6/6 result shows that
these two exact unawaited rejections are not weak-green mutants under the pinned
runtime. It is intentionally outside the canonical 12-operator/36-cell
weak-green matrix and does not generalize to every floating Promise shape or
Playwright version.

`2026-07-30-playwright-1.62-timeout-zero.json` is a separate #4g semantic
probe. A finite 100ms assertion fails before a delayed 500ms DOM update;
`{ timeout: 0 }` retries and passes after that update; and a missing-target
control fails at the enclosing 1200ms Playwright test timeout rather than the
runner's 15-second infrastructure cap. The exact exit matrix is `1/0/1`.
This proves that Playwright 1.62 zero timeout removes the matcher-local
deadline instead of creating a one-shot read. The probe uses `page.setContent`
and does not modify the canonical fixture app or its 12/36 archive.

`2026-07-30-cypress-15.19-timeout-zero.json` is the corresponding bounded
Cypress 15.19.0 #4g probe, but it does not claim identical Playwright
semantics. With the default 1200ms command timeout, the assertion retries and
passes after the same kind of 500ms DOM update. Adding `{ timeout: 0 }` makes
both an initially wrong value and a missing selector fail with Cypress's exact
`Timed out retrying after 0ms` marker while the page still reports
`status=waiting`. The exact exit matrix is `0/1/1`; the archived observation
times were 518ms for the default retry and 9ms/7ms for the two zero-timeout
checks. This substantiates only the shared loss of a useful local retry window:
Playwright zero timeout delegates to an outer deadline, whereas Cypress zero
timeout performs an immediate current-state check.

`2026-07-30-operator-design-incomplete.json` preserves the first expansion
attempt. It matched 20/21 cells because the initial #22 mutant removed only the
`await` while leaving a rejecting `waitForRequest` Promise alive. The corrected
operator removes the complete request-proof block; the complete current report
then matches 21/21. `2026-07-30-current.json` preserves that seven-operator
checkpoint; `2026-07-30-expanded.json` adds behavioral proof for #8b, #10e,
#12, and #23 and matches 33/33. The current ARIA-expanded report adds #4j and
matches 36/36.
