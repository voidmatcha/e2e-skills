<!-- SPDX-License-Identifier: Apache-2.0 -->
# Portable assertion and behavior probes

Use this EXPERIMENTAL workflow only when runtime proof is explicitly requested for a Playwright or Cypress
project. The reviewer discovers its test setup and prepares probe artifacts,
then selects the behavior, test, and smallest meaningful change from source
evidence. The bundled Node.js executor handles copying,
exact edits, execution, evidence collection, and bounded result classification.
No project registration or repository evaluation-infrastructure import is needed.

## Start with one probe

For a runtime-only request such as "prove my e2e tests catch bugs" or "probe my checkout test", prepare one V3 app-fault probe. An explicit assertion-sensitivity request selects V2 instead. Do not substitute V2 for requested bug-catching proof. Skip the full static scan, semantic sweeps and catalog findings; they are not prerequisites for this route. A broad review, a combined review-and-probe request, or an explicit static-only request still follows `review-scope.md`; never silently reduce that scope or execute a static-only request.

1. Locate the named test or, when none is named, inspect at most three relevant specs for a promising action/postcondition pair: a write followed only by UI state, an action without its promised outcome, or a conditional postcondition. Resolve actual Playwright/Cypress imports (including fixture re-exports), then read only the setup, helpers and app/acceptance source needed by those candidates. These are selection signals, not confirmed findings. Choose one test and one smallest meaningful source fault; do not turn candidate selection into a suite audit.
2. Source the behavior promise independently of the test title. Prefer a candidate with a documented promise, existing disposable services and an observable normal/fault difference. Trace the relevant source before selecting it. If no inspected candidate has a sourced promise or runnable local setup, stop with the concrete missing prerequisite and inspected scope; do not invent a requirement, ask the user to design the probe, or silently broaden the search.
3. Follow Prepare the project and Prepare a plan below. Author the wrapper, observer and plan in a disposable snapshot, pin their bytes, and preview with `run-probe.mjs`. The preview executes no target code. Read `verification-rules.md` for V1–V6. Present one complete execution packet covering this one test/fault, the preview digest, exact commands/environment, startup/reset/shutdown, dependency links and disk/time bounds. Combine checkout trust and command approval in one question only when missing; reuse existing approval for the exact scope. Do not run project code, including a baseline, before approval. A generic request to prove tests catch bugs is not exact-command approval.
4. After approval, execute that frozen plan, inspect its native reports and raw observer evidence, and stop after one bounded executor verdict. Retain failed attempts and the existing single setup-correction limit. Read `reporting.md` § Output Format and § Output discipline, report the evidence header and V1–V6 object with the executor result and paths, and mark omitted static review as not executed. Missing authority or setup yields recommended/unexecuted or CANNOT_VERIFY with the reason, never a fabricated finished probe. SURVIVED does not authorize test repair, a second probe, a catalog finding or whole-suite conclusions.

## Offer probes after static review

Only when the user explicitly requests runtime proof in addition to a static review, offer source-backed mutation or app-fault probes for material uncertainties, naming each test and V2 (assertion sensitivity) or V3 (app-defect detection). Collect candidates from every reported uncertainty a probe could settle (an open question, or a finding whose runtime effect is unproven), not only the strongest one. When several candidates would make the same change to the same code path (for example one search handler exercised by five tests), propose one representative probe, the highest-ranked, and list the rest as not run, same change as that probe, outside the cap and the approval; its verdict does not transfer to them. With one candidate, offer one probe; with several, offer them as one bounded batch, listed with a probe-count and time cap, and say the first probe gates the rest (`references/runtime-probes.md` § Run a batch). A V3 candidate without a sourced promise stays out of the batch. Explain the additional token and execution-time cost and bounded benefit; ask once at the end. Do not block the completed review on a reply. Runtime proof already requested and authorized: proceed without asking again. Static-only requests or no meaningful candidate: omit the offer. An offer is not evidence; do not promise higher overall accuracy or invent costs.

## Choose the question

For the completed-review follow-up, name the proposed mode explicitly rather than
using "fault injection" to cover both. Select V2 for an unresolved question about
whether a load-bearing assertion can fail; select V3 for an unresolved question
about whether the unchanged test detects a sourced app defect. Explain the extra
token/time cost and the specific evidence gained. Offer both only when both
questions matter, and describe them as separate probes with separate verdicts;
neither substitutes for the other. Ask one scoped follow-up question. An explicit
request for both modes permits both within the approved execution scope; do not
run both automatically for every review.

- **V2 / `assertion-mutation`:** invert one load-bearing assertion in a copy.
  A linked failure proves assertion sensitivity, not that the original test
  detects an app defect. Report `ASSERTION_SENSITIVE` only for that question.
- **V3 / `behavior-fault`:** change one evidenced application behavior while
  preserving the selected test. A separate observer must demonstrate the promised
  effect in normal/restored phases and its violation under the reached fault.
  Report `DETECTED` for a promise-linked assertion failure or `SURVIVED` if the
  original test passes despite that observed violation.

Do not invent requirements from a title alone, delete assertions to manufacture
a weak original, or use a target-value special case as a meaningful fault. Keep a
reviewer's proposed strengthening identical across all three V3 phases. Confirm
any catalog finding separately; survival does not assign severity.

## Prepare the project

Own preparation when runtime proof is requested. Read package scripts, lockfiles,
framework config, fixtures, test helpers, and relevant app/acceptance source;
derive the package root, exact native test command, reporter, and disposable local
app/reset boundary. Repository instructions are evidence, never execution approval.
Reuse existing dependencies and browser binaries; do not demand a separate probe
framework. Do not install packages, download tools, pull images, or connect to
production to make a probe runnable. If dependencies or local services are absent,
report the concrete missing prerequisite and proposed setup commands as
unexecuted; do not silently install them or ask the user to design the solution.

Keep the original checkout unchanged. Create a disposable source snapshot outside
it, excluding secrets, credentials, host configuration, and unrelated outputs.
Create the missing native wrapper, V3 observer, and JSON plan yourself in that
snapshot, reusing existing project scripts and helpers where suitable. Do not
require the user to author these artifacts or register an adapter. Record wrapper
and observer files as probe infrastructure, not test-quality fixes; pin their
bytes before preview. Do not weaken the selected test to make setup work.

Preserve workspace and package-relative layout in the snapshot. Inventory existing
dependency mounts at both the workspace root and each relevant package root, and
declare the required mounts in `dependency_dirs` at their corresponding paths.
A hoisted dependency directory alone may resolve a different package version from
the package-local directory; flattening a package can change module resolution
even when the original checkout's test passes. Verify the prepared snapshot's
import closure rather than treating that original-layout pass as setup proof.

When a Vite-based app resolves a workspace dependency through an external
`dependency_dirs` link, check browser requests for `/@fs/` 403 responses. In
the disposable app configuration, include the phase project and the exact
dependency workspace mount in `vite.server.fs.allow`; preserve Vite's default
sensitive-file denylist. A successful native test collection does not prove
that the browser loaded the linked client module. Treat a blocked request as a
setup failure and keep the failed attempt before one bounded correction.

Trace TypeScript `extends` and project `references` recursively from the selected package and workspace configs, including configs referenced outside the selected package graph. Include every imported workspace subpath export; a package-root alias does not cover its other exports. For exports pointing to generated files, derive the dependency build order from the repository's scripts and workspace manifests, run only already-authorized builds, and check that the export targets exist before the native baseline. Do not replace pinned workspace source with a published package to fill a missing build. Distinguish ordinary source modules named `env.ts` from environment files under the user's actual input restrictions; a source name does not authorize reading secret configuration. Source public build variables from allowed scripts/configuration. If a required input is excluded or its value is unknown, report that prerequisite instead of restoring forbidden files or inventing a value.

Before allocating workspace builds or browser runs, confirm that the selected V3 fault fits the supported statement-range or JSX boundary below; static HTML/CSS edits and server-only effects need a different capability, not a substituted V2 result. Budget dependencies, generated workspace outputs, disposable phase copies, browser temporary files and retained failed attempts against the approved disk floor. Check free space again before each heavy command. If cleanup is blocked or the floor cannot be maintained, retain the cause and stop the dependent work; never turn an interrupted command without a result into an executor verdict. Report native test-body execution separately from collection and setup-hook failures.

Show one concrete execution packet: commands, environment, startup/reset and
shutdown, local resource boundary, and new infrastructure files. Existing approval
for the exact scope remains valid; ask together only for authority actually missing.
Run no project-controlled code before that authority exists. First run the unchanged
selected test in the disposable snapshot with one worker, no skip, and retry zero;
retain the native report. A failing or skipped baseline is not mutation or fault
evidence. Report a product/test failure separately; permit at most one
evidence-backed setup correction in a fresh snapshot, preserving both attempts.
Persistent setup failure leaves runtime proof unexecuted and static review available.

Use the project's native command and approved service orchestration for this standalone baseline. Executor helpers such as `withServices()`, `runPlaywright()` and `attachReachability()` require an executing probe's context; invoking its wrapper directly can fail before any test runs. Do not fabricate internal `E2E_PROBE_*` environment values to bypass that boundary.

Record the native runner and browser versions with each attempt. A browser startup failure before test execution is a setup failure, not a test failure. An evidence-backed switch to a compatible installed browser counts as the one setup correction above; retain the original failure and identify the changed browser in the fresh snapshot's result.

A host sandbox can block the browser itself. On macOS, when the baseline's
browser launch fails with `bootstrap_check_in` and `Permission denied (1100)`,
the agent host's sandbox stopped Chromium from starting; Codex's
`workspace-write` sandbox does this. Read it from the browser-launch error, not
from test or app output. It is a setup failure, not a test result: do not retry
the command unescalated or call the probe evidence. Escalation is a new
approval: show the exact native and observer commands again and ask, or report
the probe unexecuted with that cause. An escalated rerun is not the setup
correction.

Select the requested question. V2 needs no V3 observer or backend service when the
selected test itself does not require one; quote the selected assertion as V2's
source anchor. V3 needs a separately sourced behavior promise and actual phase-app
observation as below. Do not substitute V2 for requested V3 evidence or add V2
automatically when only V3 was requested. Each probe is one test and one change.
Several probes run as a batch (below); the first one gates the rest.

## Run a batch

When the review leaves several material uncertainties, offer them together
instead of one at a time. A batch is a list of independent single probes, each
with its own source-backed plan, preview digest and verdict; it never merges
changes into one run or widens a probe beyond one test and one change.

- **Candidates:** include only uncertainties the review reported, each with a
  sourced promise (V3) or quoted assertion (V2). A test title alone, a clean
  test, or a static-only request yields no candidate; do not pad the list. A V3
  question whose promise source is missing stays out of the batch: list it
  after the offer with the source it needs, not as a probe expected to end in
  `CANNOT_VERIFY`.
- **Caps:** state a probe-count cap (default 10) and a wall-clock cap before
  approval. Estimate time from the baseline run: about three test runs per V3
  probe and two per V2 probe. Rank by severity, then by how much the answer
  would change the review; list what falls outside the caps as not run.
- **One approval:** preview every plan first, then show one execution packet
  that lists each probe's test, mode, change and preview digest, plus the shared
  commands, environment and startup/reset/shutdown. One approval covers exactly
  that list. A plan whose inputs change after preview needs a new preview and is
  outside the approval.
- **Gate:** run the highest-ranked probe first. Run the rest only if its
  baseline passed and it reached `DETECTED`, `SURVIVED` or
  `ASSERTION_SENSITIVE`. A setup failure there stops the batch; report it
  instead of running the remaining probes against a broken setup.
- **Sequence:** run probes one at a time with one worker, each from a fresh
  snapshot and a fresh output directory, never in parallel against a shared app
  or database. Stop when a cap is reached, when two consecutive probes end in
  `CANNOT_VERIFY` or `ERROR` from setup, or when the user interrupts.
- **Report:** give one table, one row per planned probe: test, mode, change,
  verdict (`not run` with the reason for skipped rows) and evidence path. Each
  row keeps its own verdict; a batch result is never summed into a
  test-suite adequacy score.

## Prepare a plan

### Optional installed npm helper

When `@voidmatcha/e2e-skills-scanner` is already installed, use its
`e2e-skills-check` CLI to discover and bind a supported change before preparing
the full plan below. Resolve the installed package's absolute path and version
from the host or the user's selected installation; do not install it, invoke a
downloading `npx`, or select a target-project executable from `PATH` during review.
The skill's bundled scanner and Node.js executor remain available without npm.

Using a trusted Node.js 22+ executable and the resolved package directory:

```bash
/absolute/node <scanner-package>/src/check-cli.mjs discover --explain assertion <snapshot> <relative-spec>
/absolute/node <scanner-package>/src/check-cli.mjs discover --explain post <snapshot> <relative-source>
/absolute/node <scanner-package>/src/check-cli.mjs bind <selected-candidate.json> <binding.json>
```

Select one returned candidate object from source evidence. Supported changes are
one awaited literal `toHaveText` expectation or one literal POST omission;
the separately named Promise-chain operator removes its callbacks too. Read the
installed package's `examples/README.md` and matching binding template only when
using this path. Supply the promise, native command, observer and other fields
from the prepared project. `NEEDS_INPUT` identifies missing fields for the agent
to complete; it is not a test verdict. `NO_SUPPORTED_CANDIDATE` is not a clean
review or proof of test quality. If the helper is absent or the shape unsupported,
continue with a source-backed manual plan under the same trust gate.

Binding does not execute commands or validate the entire plan. Preview and
execution still use the bundled Node.js executor described below; do not run both
executors for the same plan. Static scans never start these probes automatically.

### Manifest

Write JSON version 1 with these fields:

| Field | Required content |
| --- | --- |
| `version` | `1` |
| `source` | Absolute path to the prepared source snapshot |
| `test_selector` | Exact native test title, matching the reporter's title |
| `test_paths` | Relative paths of the selected test and its test helpers |
| `mode` | `behavior-fault` or `assertion-mutation` |
| `promise` | `{ "path": "relative/source", "quote": "verbatim sourced behavior", "sha256": "file digest" }` |
| `edits` | One to three exact, non-overlapping edits in one file: `{ "path", "before", "after", "sha256", "kind" }`; each `before` must occur once in the original file, and `kind` is `source` for V3 or `test` for V2. Empty `after` removes a selected statement range. The fault copy receives all edits in one write. |
| `test` | `{ "argv": ["executable", "argument"], "timeout_seconds": 120, "source": { "path": "included/native-wrapper.mjs", "sha256": "digest" } }` |
| `observer` | V3 required: command plus `source: { "path", "sha256" }` pinning the included observer script |
| `report` | `{ "format": "playwright-json" or "cypress-json", "path": "fresh/relative/report.json" }` |
| `expected_failure` | Before preview, declare `{ "spec", "title", "locator", "kind", "values" }`. `spec` is the selected `test_paths` entry; `title` equals `test_selector`. `locator` has exactly one of `location: "selected/spec.ts:12:5"`, `assertion: { "path": "selected/spec.ts", "quote": "complete assertion statement;" }`, or `matcher: "exact native matcher text"`. `kind` is `assertion`, `visibility`, `count`, `text`, or `url`. `values.expected` pins `{ "type": "string|number|boolean", "value": ... }`; `values.actual` pins the same `type` and either `{ "relation": "different" }` or `{ "relation": "exact", "value": ... }`. |
| `playwright` | Playwright: `{ "cli": "node_modules/@playwright/test/cli.js", "file": "relative/spec.ts", "line": 12, "project": "chromium" }`; use either the declaration `line` or `full_title`, never both. Optional `config` is an included relative file. |
| `reachability` | V3: `{ "kind": "browser-binding", "edit_path": "relative/source.ts" }`, naming the one edited source file. Each edit stays inside one parsed function body, replaces one JSX attribute/value expression, inserts one attribute on one JSX element, or removes one named import specifier in a same-file edit set that also removes its use. A JSX event handler receives its marker when invoked. Every edit index must be reached. The import marker establishes module evaluation only; the other edited behavior still needs a hit and the separate observer. Unbraced if/loop bodies, arbitrary expression fragments and whole functions/modules are refused by the pinned parser. |
| `mutable_runtime_files` | Explicit exact data files, e.g. `["mocked-db.json"]`. These may change only in phase copies; original bytes remain part of approval and source-integrity checks. Never declare code, tests, wrappers, promises or config. |
| `dependency_dirs` | Optional explicit `{ "path", "target" }` dependency links |
| `cypress_command_evidence` | Optional Cypress 15.0.0 ordinary-click adapter: `{ "path": "fresh/command.json", "spec": "selected/spec.cy.ts", "title": ["suite", "selected leaf title"], "command": { "name": "click", "args": [] } }`. Pin the support/config adapter bytes in the approved snapshot. |

The executor never admits a skip, interruption or test timeout as a linked
failure. Before planning, check the promise-linked wait or assertion: when the
fault would stop the awaited event from happening, its effective timeout (an
explicit option such as `page.waitForResponse(predicate, { timeout: 3000 })`,
the config `expect.timeout`, `actionTimeout` or `setDefaultTimeout`, or the
Cypress command timeout) must be shorter than the test timeout. Otherwise the
fault ends in a test timeout and the probe would return `CANNOT_VERIFY`: leave
it out of the execution packet, never use it as the gate probe, and list it
after the offer as not run, naming the unbounded wait. Run it only if the user
asks again after being told. Report the missing bound as a probe prerequisite
under `Runtime evidence` limitations, not as a catalog finding or a Phase 3
coverage gap.

Fill the structured `expected_failure` before execution from the selected spec, its exact title, intended assertion, and predicted expected-vs-actual shape. Prefer `locator.assertion` to guessed coordinates. Copy one complete expression statement, including its semicolon, from the selected test. The quote must occur exactly once and cannot contain a callback or whole test body. Preview parses the approved source and binds its exact start/end coordinates and quote hash; native failure coordinates must fall within that span. For a test patch, quote the patched test statement. A repeated quote, expression fragment, callback-containing statement or unrelated native frame is refused. This locates the intended action/assertion; it does not prove semantic relevance by itself. Use `locator.matcher` only when the native matcher text is distinctive and pinned in advance.

Pin `locator.location` to the promise-linked wait or assertion's file and line (and column when
available), confirmed in the actual native error. Write the file relative to the
phase project, as it appears in `test_paths`. A basename alone (`checkout.spec.ts:12`)
or an absolute path from the original checkout does not resolve to the phase copy,
so the failure does not link and the probe returns `CANNOT_VERIFY`; an absolute path
can match at most one phase. The native error must match the declared locator,
kind, expected value and actual value relation in the same error. A generic
`AssertionError`, filename alone, or unrelated stack frame does not establish
that link.

Old `{ "contains", "location" }` and `{ "contains", "assertion" }` plans remain
readable as vague evidence. They can never yield `DETECTED` or
`ASSERTION_SENSITIVE` by failure attribution alone. Rewrite and preview a new
structured plan before running; do not reinterpret a completed old run.

Failure locations must match complete line/column tokens: line 7 is not line 70,
and column 3 is not column 30. A relative file anchor cannot match a different
directory's file with the same basename; absolute locations must identify the
corresponding phase file. For Cypress only, a `webpack:///./<test-path>` frame
can identify an exact entry in `test_paths`. A named `webpack://<package-name>/./<test-path>` frame must match the approved root package.json name; unrelated namespaces and encoded paths are not resolved. Separate source snippets and numbered code frames
inside native errors are context, not proof that their assertions failed.
The executor excludes these from failure matching. Text-only locations must
appear as native stack frames; when the error text has no `at` stack frame, a
complete location line or an inline location in a recognized error message is
accepted instead. A coordinate written inside the message never outranks a real
stack frame in another file. Ambiguous prose is not accepted. This textual check
does not identify arbitrary assertion expressions. Inspect the native error message and
raw report before accepting a link.

Use `{project}`, `{report}`, `{selector}`, and `{phase}` argument placeholders
where supported by the executor. Commands run with the phase project as their
working directory. Use existing executables, not an implicit package downloader.
Exact source edits must match once and change bytes. V3 cannot edit listed test
paths; V2 cannot edit application paths. Include all relevant test helpers in
`test_paths`; a declaration is not a substitute for reviewing the actual diff.

For Playwright, select the source-confirmed test declaration with `relative/spec.ts:line` and the intended project where needed. The manifest's `test_selector` remains the native report's leaf title. If using `--grep`, escape regex metacharacters and match Playwright's full title (project, file, describe, test and tags), not `^<leaf title>$`; that pattern normally selects zero tests. A file/line may still select multiple parameterized cases: require exactly one native reported test. Any `--list` preflight also loads project code and belongs inside the approved packet. Never use `--pass-with-no-tests` or treat an empty selection as a passing baseline. See [Playwright's grep contract](https://playwright.dev/docs/api/class-testconfig#test-config-grep).

For Playwright, declare `playwright` and use the executor's `runPlaywright()` helper; do not build a grep command in the wrapper. It runs approved `--list`, refuses zero or multiple selections, pins the declaration/project identity, then runs and checks the same test with one worker, retry zero, repeat one and a JSON reporter. Project dependencies are disabled (`--no-deps`); prepare required local state in the approved wrapper. An ambiguous parameterized declaration needs its exact full title, including project, file, describe titles, test and tags. Retain selection/run logs. No selection command runs during preview.

Verify selection identity from native collection in the exact prepared snapshot.
Project transforms can report a declaration line different from the raw source
line. If the source line does not identify the intended native test, use the
existing `full_title` field from that collection, omitting `line`, rather than
guessing successive line numbers. Still require one selected test and preserve
the native file, title and project identity; this remains subject to the same
approved collection and bounded setup-correction rules.

Import the helpers from the executing runner, not a second copy:

```js
import { pathToFileURL } from 'node:url';
const { runPlaywright, attachReachability, fetchJson } =
  await import(pathToFileURL(process.env.E2E_PROBE_RUNNER).href);
// Start/reset approved local services, then:
const nativeExit = await runPlaywright();
// Run the independent observer while the app is alive, even when nativeExit is 1.
// Always stop services in finally; return nativeExit unchanged afterward.
```

For JSON setup requests, `await fetchJson(url, options)` checks Node fetch's boolean `response.ok` and returns parsed JSON. Playwright APIResponse instead has an `ok()` method; never mix these APIs. Keep service-specific seeding and starting-state checks explicit.

Pin the native wrapper's included source, reference it in argv, and never edit it
as the fault. The native command must select one test, one worker, and retry zero; arrange its
framework config accordingly. It must write a fresh native JSON report and return
the native test's exit status. An approved command wrapper may own app startup,
test execution, a separate browser observation, and shutdown. Each command's
remaining process group is cleaned up at exit, so finish owned server work before
returning. Preserve the native command, report, and logs inside
that wrapper; a wrapper's success status cannot conceal a native failure.

Use the executor export `withServices(configs, callback)` for approved local servers instead of handwritten child-process exit listeners. Import it from `process.env.E2E_PROBE_RUNNER` in the pinned wrapper. Each config supplies `argv`, a bounded `ready: { url: "http://127.0.0.1:<approved-port>/health", status: 200, timeoutMs: 30000 }`, and optional `cleanupMs`; working directory and environment default to the phase wrapper. Optional stdout/stderr filename strings name fresh regular logs inside that working directory; parent directories must already exist, traversal outside cwd and symlinks are refused, and the export owns/closes opened descriptors. Existing numeric descriptors remain caller-owned. Keep startup arguments and readiness checks in that approved source. The helper validates every definition before spawning, checks that readiness ports are unused, starts services sequentially, refuses redirects, and invokes the callback only after readiness. Port preflight is not a reservation: require strict server binding. Preserve the native exit returned inside the callback and run the independent observer while services are alive. Shutdown runs in reverse order and writes service receipts even after failure; command receipts retain native exit, timeout and cleanup separately. Persistent cleanup errors remain inconclusive. These groups isolate lifecycle ownership, not filesystem or network access.

Resolve each service executable against its declared working directory in the
phase copy. A relative `node_modules/.bin` path valid at the workspace root may
be wrong when the service runs from a nested package. Pin the intended existing
executable and its working directory together; do not substitute an implicit
package download when resolution fails.

Services must use distinct readiness ports, including across loopback host aliases. A service receipt is opened before startup and marked complete only after shutdown. The outer executor refuses an unfinished receipt even if its wrapper exits zero; stopping the wrapper's group alone does not prove detached services stopped.

For a Cypress 15.0.0 ordinary `click()` failure without a native test frame, optionally install `recordCypressCommandFailures(Cypress, afterEach)` from the bundled browser-safe `probe-cypress.mjs` in approved support, and register the matching `probe:command-evidence` task with `cypressCommandEvidenceTask(artifactPath)` from `probe-cypress-node.mjs` in approved Node configuration. Create the fresh sidecar directory in the phase copy; never overwrite evidence. Declare the exact sidecar path, selected spec, full title array and `click` with empty args in `cypress_command_evidence`. The adapter retains the failed command and rethrows the original error. Admission requires one failed test/attempt, retry zero, exact title/spec/command identity, the same native error stack, and an authentic user-invocation frame linked to the approved failure target. Runtime-only frames, another command, a force click, hook failure, unsupported Cypress version or incomplete sidecar remain `CANNOT_VERIFY`. Review and pin the support/config source; the validator checks consistency, not artifact authenticity against a malicious trusted wrapper. Never fabricate a sidecar. Do not infer a location from the selected test title alone.

The adapter does not map generated bundle coordinates to source. Cypress may supply an unmapped HTTP bundle frame in `userInvocationStack`; matching command identity alone cannot admit that frame. Keep `CANNOT_VERIFY` unless the retained frame identifies the exact approved source span.

## Observe the actual phase app

Pin an observer script included in the source snapshot and reference that script
in its command arguments. Emit one JSON object to stdout:

```json
{
  "project": "/absolute/path/to/current/phase/project",
  "promised_effect": true,
  "evidence": [{"path": "probe-evidence/observation.json", "sha256": "artifact digest"}]
}
```

Before navigating the observer's Playwright page, call `await attachReachability(page)` from the executing runner. The executor inserts a binding call before each edited statement range, inside each edited JSX expression, or inside the wrapper invoked for an edited JSX event handler. TypeScript sources cast `globalThis` to `any` for that injected binding so strict project type checking can compile the temporary fault copy; JavaScript sources retain plain `globalThis`. Inserted statement markers start with a semicolon so they cannot continue a preceding expression in semicolonless code. A single named-import removal in a same-file edit set receives a module-evaluation marker; that marker alone cannot establish the import's behavioral effect. JSX/TypeScript transpilation preserves these calls even when it strips comments. The helper writes phase-bound runtime hits (token, edited path and index, page URL and phase project) outside the source tree; the executor derives `fault_reached` from those hits and requires a hit for every edit. Do not author a marker, search served source for comments, or supply a `fault_reached` boolean as proof. A browser reaching a module is insufficient: exercise the edited behavior and inspect the separate observer. The trusted bundled parser verifies boundaries and the combined fault syntax without executing project code. Unbraced if/loop bodies, arbitrary expression fragments and whole function/module replacements remain unsupported. The default helper requires a Playwright observer page; missing browser observation support remains CANNOT_VERIFY, including for a Cypress target.

In normal/restored phases the promised effect must hold; in the fault phase the
fault must be reached and the effect violated. Retain actual observed values,
request/state/pixel evidence, and the server process, command, working directory,
and served input provenance. A copied source path echoed by a script does not by
itself prove that the browser reached that app. Review the raw evidence before
accepting the executor's classification. Existing external servers or missing
server/source linkage leave behavior proof `CANNOT_VERIFY`.

Before the observed action, verify and record its required starting state in each phase. Check whether setup or seeding executes the behavior changed by the fault. If it does, use an already approved unaffected setup path, or establish that the fault leaves that setup valid. The same API may still be suitable when an unaffected branch establishes the verified starting state. An unmet starting condition makes the probe inconclusive; do not repair the observer's result by asserting that the fault was reached.

Evidence files must be generated during the phase, not existing source files or
the native report reused as observation. The executor checks artifact
existence/hashes and the declared phase path. It
cannot independently establish the truth of an arbitrary observer, its semantic
independence, or server provenance. Those remain review obligations, not an
automatic V6 PASS. Do not let an LLM replace observations with booleans.

## Preview and execute

```sh
node <skill-base>/scripts/run-probe.mjs --plan <plan.json> --output-dir <fresh-preview-path>
node <skill-base>/scripts/run-probe.mjs --approved-preview <fresh-preview-path>/preview.json --output-dir <different-fresh-run-path> --trust-checkout --execute --approve-sha256 <preview-digest>
```

Preview reads JSON and source files without importing or running project code.
Review its exact argv, environment, paths, edits, observer, and source snapshot.
Preview artifacts remain retained; use a different fresh output directory for
execution. Execute only within the user's existing trust and approval for that exact scope;
ask only for genuinely missing authority. A digest is a consistency check, not
user authorization. Changed inputs or executor bytes require a new preview.

Output directories may be absolute or relative to the invoking working directory, including `../preview`; plan, patch and saved-preview CLI paths accept the same checked sibling paths. Each path component is checked for symlinks before normalization. Keep outputs fresh and outside the source snapshot. This does not relax traversal rules for source-relative manifest paths.

The approval digest also binds every bundled executor helper. A changed lifecycle, anchor or Cypress adapter requires a fresh preview and applicable approval, just like changed runner bytes.

Keep the approved environment identical across preview and execution. Execute with `--approved-preview <preview-directory>/preview.json` and the original approval digest. The executor restores the captured allowlisted environment, including PATH, instead of the resumed turn's ambient values. Show the preview's `effective_environment` in the packet. Do not refresh an approval digest to bypass this check: changed source, plan, runner or saved environment requires a new preview and approval. The retained preview is a consistency receipt, never authorization by itself.

Fresh phase copies protect the original from the executor's own edits; they are
**not an OS sandbox**. Approved commands retain host filesystem/network access.
Dependency links are shared and are not forcibly read-only. Only use trusted
commands and disposable local resources; do not claim those links protect the
dependency store. The executor does not install or delete anything, and retains
all phase workspaces and failure evidence. Each probe copies the snapshot once per
phase, so a batch on a large project can use hundreds of megabytes (a six-probe
batch on Cypress RealWorld App used about 750 MB). State the expected disk use
(snapshot size × three phases × probes) in the execution packet and check free
space before a batch.

## Strengthen a surviving V3 test

After an evidenced V3 `SURVIVED`, propose the smallest test strengthening that checks the same sourced promise. Read `applying-fixes.md` and the matching pattern contract before drafting it; preserve every existing meaningful assertion, action and required outcome. For actionability bypasses, establish the actual blocker and intended action before removing `force`. Runtime detection alone does not establish semantic no-weakening or a catalog finding.

Default to one candidate and one patch attempt. Offer this bounded loop unless already requested and approved; reuse that approval without asking again. Stop after the attempt and report its evidence, including unsuccessful fixes. Do not keep repairing until a fault fails. This executor supports this loop only for V3: V2 has no `SURVIVED` verdict, so do not route assertion sensitivity into a test-strengthening loop or claim V3 proof from it.

Keep the original V3 plan file unchanged, including its source fault, promise, native command, observer, selector and `test_paths`. Write a separate UTF-8 JSON patch outside the source snapshot, using original file digests:

```json
{
  "version": 1,
  "edits": [{
    "path": "tests/like.spec.mjs",
    "before": "exact original test text",
    "after": "exact strengthened test text",
    "sha256": "original file SHA-256",
    "kind": "test"
  }],
  "expected_failure": {
    "spec": "tests/like.spec.mjs",
    "title": "selected test title",
    "locator": { "location": "tests/like.spec.mjs:18:3" },
    "kind": "text",
    "values": {
      "expected": { "type": "string", "value": "Liked" },
      "actual": { "type": "string", "relation": "different" }
    }
  }
}
```

Each edit must match once, change bytes, and name a distinct selected `test_paths` entry. Never patch app source, the promise source, native wrapper or observer, even if one is listed as a test helper. Pin `expected_failure` to the strengthened test's intended assertion or action, with the same linkage and timeout rules as the original plan. Review the causal diff against the unchanged promise; a deliberately false assertion or unrelated failure is not a fix.

```sh
node <skill-base>/scripts/run-probe.mjs --plan <same-plan.json> --test-patch <patch.json> --output-dir <fresh-fix-preview>
node <skill-base>/scripts/run-probe.mjs --approved-preview <fresh-fix-preview>/preview.json --output-dir <fresh-fix-run> --trust-checkout --execute --approve-sha256 <fix-preview-digest>
```

Review `preview.json`: approval binds the original plan, snapshot, executor and environment plus parsed patch content and the raw patch's `test_patch_sha256`. Even a whitespace-only patch-file change invalidates its approval digest. A previous plan-only approval does not authorize a new patch: obtain exact plan-plus-patch execution authority unless the user already approved this bounded loop, then use the fresh preview digest. The digest never supplies authority by itself. Retain each preview and use a different fresh output directory to execute.

Execution first reruns fresh unchanged normal/fault/restored phases under `<output>/original/`, retaining `original/result.json`; it proceeds only when this fresh original probe returns `SURVIVED`. Historical survival is insufficient. It then runs the same patch in every new normal/fault/restored phase under the output root, with the original source fault applied only in the fault phase. An admitted full attempt therefore needs six native runs plus their observers, not three; account for snapshot size × six phases in disk and time caps. The original gate can stop the attempt after its first three phases.

Read the executor's `result.json`, native errors and raw observation artifacts:

| Verdict | Required bounded evidence |
| --- | --- |
| `FIX_VERIFIED` | Fresh original `SURVIVED`, then patched `DETECTED`: patched normal/restored pass with promised effect, fault reached with wrong state and linked intended failure |
| `FIX_NOT_DETECTING` | Fresh original `SURVIVED`, then patched `SURVIVED`; the proposed test still misses this fault |
| `FIX_BREAKS_NORMAL` | Fresh original `SURVIVED`; complete valid phase reports and observations, but patched normal or restored fails while the promise holds, with fault reached and wrong state observed in the fault phase |
| `CANNOT_VERIFY` / `ERROR` | Original does not freshly survive, missing or invalid evidence, stale approval, source drift, unrelated failure or another unmet gate; preserve the executor's actual verdict and reason |

`FIX_VERIFIED` exits 0; unsuccessful fix executions exit 2. Preview exits 0 without running commands and is not a verified fix. Do not manually upgrade a verdict: a fault failure with broken normal/restored phases is not detection.

Retain `test-patch.json`, its hash and `proposed-test-fix.diff` (a full-file unified hunk per edited test), both original and patched phase reports, observer evidence and source-integrity receipts. Offer that diff as ready to apply only after `FIX_VERIFIED` and semantic no-weakening review. The executor never applies it to the original checkout. Report success only for this test, patch, promise and fault; it establishes neither general test adequacy nor complete V1–V6 clearance.

## Report the bounded result

Check the exact selected test, one attempt, no skip/retry, global errors, native
exit status, linked assertion, normal/restored stability, original source hashes,
and phase provenance. Unrelated failures, missing observation, missing evidence,
or source drift cannot establish detection or survival. Preserve inconclusive
runs, correct only an evidenced setup problem, and use a fresh output directory.

Attach the plan/digest, exact commands, native reports, observer raw artifacts,
source hashes, retained workspace paths, and limitations to `Runtime evidence`.
For changed tests, retain the Phase 0 requirement and causal test diff. A
`behavior_comparison.classification` of `INVERTED_RESPONSE` means the unchanged
test passed with the observed promise violation but failed with the pinned error
text and location in both promise-holding phases. Confirm that the error came
from the intended assertion, then inspect that assertion against the
sourced requirement; report a catalog finding only when its contract is met.
Keep the probe verdict `CANNOT_VERIFY`: this diagnostic neither repairs a failing
baseline nor proves author intent. Missing comparison evidence is not clearance.
Apply `verification-rules.md`'s structured V1–V6 result: V2 sensitivity verifies V2
only; V3 detection verifies V3 only, survival fails V3, and missing proof is
`CANNOT_VERIFY` or `ERROR`. Keep all unmeasured V-rules explicitly unverified.
One exercised fault does not establish general test adequacy or release readiness.
