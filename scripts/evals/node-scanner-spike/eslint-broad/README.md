# Optional broad missing-await mode

Apache-2.0. Development experiment only; no product detector or promotion change.
Reuses the exact external dependency pins documented in `../eslint-owned/README.md`:
ESLint 10.8.0, TypeScript parser 8.65.0, TypeScript 6.0.3 and Playwright plugin 2.11.0.

```sh
node scripts/evals/node-scanner-spike/eslint-broad/run.mjs \
  /absolute/external/deps /absolute/new/external/output
```

The exact supported option is `{ includePageLocatorMethods: true }`. The harness
checks the installed option schema and versions, then compares explicit false
and true settings against the same 17 authored snippets. `Linter.verify` receives
only scanner-owned configuration; TypeScript project services, inline config and
fixes are disabled. Throwing target config/import files remain unexecuted.
Raw messages, source/config/dependency/harness hashes and immutable fixtures stay
external. No target configuration discovery, runtime tests or models are used.

## Result, 2026-10-21

Evidence: `~/.cache/e2e-skills-bench/eslint-broad-20261021-v1/result.json`.
All default-mode counts were zero in this focused action-method fixture set.
Broad mode produced these raw candidates:

| Controls | Broad result |
| --- | --- |
| Unawaited page click, locator chain, locator alias, aliased fixture click | One each |
| Awaited equivalents, returned click, saved Promise later awaited | Zero |
| Synchronous foreign object's click | One: false candidate for Playwright missing await |
| Local function parameter named page with synchronous click | One: false candidate from shadowed binding |
| Foreign async object's click | One: foreign API, no Playwright ownership proof |
| Aliased fixture `browser.goto()` without await | Zero: missed Playwright action |
| Awaited Promise.all | Zero |
| Unawaited Promise.all | One, reported on outer `all`, not its inner actions |
| Explicit void click | One: intent requires review |
| Saved Promise never consumed | One |

This mode can supply action candidates beyond the default rule. It cannot safely
replace manual pattern #16 review or a binding-aware detector. In the pinned
implementation, locator method names are accepted without proving receiver
ownership; page-only methods use page/frame name heuristics. Consequently, the
same option both flags unrelated synchronous calls and misses a real aliased
page API. Promise.all detection here also relies on `all` being in the locator
method set, so it is not evidence of general Promise ownership analysis.

Keep outputs as raw lint candidates. Scanner routing, binding/receiver checks
and independent semantic review remain necessary before confirmation. These 17
snippets establish concrete boundaries, not corpus precision or recall. No
candidate was promoted, no fixer ran and no scanner rule was changed.

## Pinned source

The prior scanner-owned experiment retrieved the upstream document through
`agent-reach`; this followup reused that exact cached version and inspected the
installed compiled implementation and option schema:

- [2.11.0 rule documentation](https://github.com/mskelton/eslint-plugin-playwright/blob/v2.11.0/docs/rules/missing-playwright-await.md)
- [2.11.0 rule source](https://github.com/mskelton/eslint-plugin-playwright/blob/v2.11.0/src/rules/missing-playwright-await.ts)

The compiled receiver/name checks and rule implementation hashes are recorded
in the external `source-receipt.json`.
