# Targeted assertion mutation spike

This contributor-only spike discovers narrow assertion and POST omission shapes
with TypeScript's AST, previews exact source edits, and binds manually reviewed
execution plans for the existing `run-probe.py`. It is not an installed skill,
an npm package, a general mutation engine, or automatic project setup.

## Assertion operator

```js
import { expect } from '@playwright/test';
await expect(page.getByTestId('status')).toHaveText('Ready');
```

The single string expectation becomes a deterministic marker derived from the
source SHA-256. Candidates retain the exact before/after bytes, source hash,
UTF-16 and UTF-8 ranges, line and column, and parser artifact hash. Discovery
reads source; it does not load the target project's configuration or imports.
The explicitly supplied parser is executable trusted tooling. This experiment
requires TypeScript 5.9.3 and records its bytes; it has no implicit installation
or dependency resolution from the target project.

Strings, comments, syntax errors, dynamic arguments, regex/templates, `.not`,
`expect.soft`, alternate locator methods, shadowed `expect`, and duplicated exact
assertion text are excluded. This is syntactic candidate selection, not control
flow or type analysis: a candidate can be unreachable, a `page` binding can be
custom, and a project may modify Playwright's behavior. Only execution can
establish the bounded assertion sensitivity result.

## Discover and bind

All output paths must be fresh. Run from the repository root, using an explicitly
reviewed TypeScript artifact at an absolute canonical path:

```bash
node scripts/evals/targeted-check/candidate.mjs discover \
  /absolute/typescript/lib/typescript.js /absolute/project \
  tests/status.spec.ts /absolute/new-candidates.json
```

The output is an array. Review it and save exactly one candidate object to a
separate file. Prepare a binding JSON with these explicit fields:

- `source`: canonical absolute trusted project directory.
- `test_selector`: exactly one native test title.
- `promise`: `{ "path", "quote", "sha256" }` of the source-backed requirement.
- `test`: `{ "argv", "timeout_seconds", "source": { "path", "sha256" } }`.
  The command must invoke the pinned project wrapper; no command is inferred.
- `report`: `{ "format": "playwright-json", "path": "native-report.json" }`.
- `expected_failure`: `{ "contains", "location" }` that must occur together in
  one native error, e.g. matcher name and exact spec line.
- Optional `dependency_dirs`: explicit external dependency mounts accepted by
  the existing runner.

```bash
node scripts/evals/targeted-check/candidate.mjs bind \
  /absolute/typescript/lib/typescript.js \
  /absolute/candidate.json /absolute/binding.json /absolute/new-plan.json
python3.12 skills/e2e-reviewer/scripts/run-probe.py \
  --plan /absolute/new-plan.json --output-dir /absolute/new-preview --preview
```

Binding rediscovers the candidate from current source and rejects drift. The
runner validates the entire manifest, wrapper hash, source hashes and unique
edit, then returns an approval digest without executing the project. Review that
preview before using `--execute --trust-checkout --approve-sha256 <digest>` with
a different fresh output directory. Copies are not an OS sandbox; commands have
host access and dependency mounts are read-only only by convention.

The runner's `ASSERTION_SENSITIVE` is **V2 only**: baseline and restored runs pass,
and the altered expectation produces the linked assertion error. It does not
establish that an application fault would be detected. An unreachable mutation
that leaves all runs green remains `CANNOT_VERIFY`, not a successful detection.

## Checks and observed canaries

```bash
TARGETED_CHECK_TYPESCRIPT=/absolute/typescript/lib/typescript.js \
  node --test scripts/evals/targeted-check/test-candidate.mjs
```

The assertion tests cover syntax selection, byte accuracy, false-positive guards, exact
source uniqueness, binding preservation and source/candidate drift. Tiny test
temporary directories are retained outside Git; no target originals are edited.

The 2026-10-21 local canary used TypeScript 5.9.3, Playwright 1.63.0, an existing
Chromium headless shell revision 1234 selected explicitly, and Python 3.12. It
uses a tiny authored `page.setContent` fixture, not an OSS sample or model run.
Native report hashes and linked error evidence are retained outside Git under
`$HOME/.cache/e2e-skills-bench/targeted-check-canary-20261021-v2/`.
Normal/mutation/restored outcomes were pass/fail/pass, with unchanged originals
and `ASSERTION_SENSITIVE`. The preceding v1 attempt selected no test because its
wrapper anchored the complete Playwright grep title incorrectly; it is preserved
as `CANNOT_VERIFY` and is not counted as valid mutation evidence.

An unreachable-assertion negative control is stored separately under
`targeted-check-unreached-control-20261021-v1/`. See its native reports and result
rather than treating source discovery as execution evidence.

Remaining work includes package installation, broader operators, Cypress,
portable dependency setup, cross-platform checks and project-specific observers.
No product workflow, performance superiority or generic automation claim is
established by this spike.

## POST omission operator and V3 pair

`post-candidate.mjs` adds one behavior-fault operator:

```js
await fetch('/api/like', {method: 'POST'});
// Candidate replacement:
await Promise.resolve(undefined);
```

Only a standalone awaited call with a literal root-relative endpoint, literal
`POST`, and explicit object properties is supported. Consumed response values,
dynamic endpoints/methods, GET, object spreads, computed properties, duplicate
methods, optional calls, shadowed fetch and repeated exact statements are
excluded. This deliberately does not support the current React demo's
`const response = await fetch(...)` shape: supplying a fabricated response could
introduce another failure mechanism. The original demo remains unchanged.

Discovery and binding use the assertion CLI argument order above, substituting
`post-candidate.mjs`. Discovery may return multiple endpoints; review and select
one exact candidate. Behavior bindings additionally require `test_paths` and a
pinned `observer`. The source edit must be outside `test_paths`. Nothing infers
which endpoint is important or what outcome proves a defect.

The authored fixture can be created into a fresh external directory:

```bash
python3.12 scripts/evals/targeted-check/make-post-fixture.py \
  --output /absolute/new-fixture \
  --dependency-dir /absolute/reviewed-node_modules \
  --browser /absolute/reviewed-chromium-headless-shell \
  --node /absolute/node
```

The fixture records real loopback HTTP events and server state. The browser sends
separate `handler-entered` and `handler-settled` requests around the selected POST.
The independent observer uses session IDs, event sequence, the actual write log
and server state, not the runner phase name. It requires one entry and settlement
with no write and false persisted state to establish the omitted-write fault.
Baseline and restored phases must each contain the real write and true state.
These marker requests are fixture instrumentation, not generic instrumentation
injected into an arbitrary project.

On 2026-10-21, the same source and exact `/api/like` edit were run through two
separate one-test plans:

| Test | Normal | Omitted POST | Restored | Runner verdict |
| --- | --- | --- | --- | --- |
| Server-state-aware | pass | linked assertion failure | pass | `DETECTED` |
| UI-only | pass | pass | pass | `SURVIVED` |

Both fault phases reached the handler and settled without a write, and the
server remained unliked while the UI showed success. All six native report
hashes and twelve observation artifact hashes were reread and verified, and both
original-source digests were unchanged. Evidence is external under
`$HOME/.cache/e2e-skills-bench/targeted-post-pair-20261021-v1/`.
The strong assertion fails on `state.liked`, not startup, syntax or test timeout.
This is one authored counterexample, not an estimated real-project detection
rate, generator improvement, or a comparison against other mutation tools.

Run both source-only suites together:

```bash
TARGETED_CHECK_TYPESCRIPT=/absolute/typescript/lib/typescript.js \
  node --test scripts/evals/targeted-check/test-candidate.mjs \
  scripts/evals/targeted-check/test-post-candidate.mjs
```

The current total is ten tests, including behavior-binding observer requirements,
source-vs-test separation and candidate/source drift guards.
