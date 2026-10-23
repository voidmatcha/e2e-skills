# e2e-skills scanner

Static Playwright and Cypress test review with configuration context and explicitly approved probes. The scanner finds candidates; an LLM reviews context, selects checks and interprets the evidence. Scanning never starts a probe.

The commands below pin version `3.1.1`.

Requires Node.js 22+. Neither CLI requires Python. Probe execution additionally requires a trusted, prepared project.

## Run with npx

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.1.1 e2e-skills-scan --scan /absolute/project/tests --format text
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.1.1 e2e-skills-check discover --explain assertion /absolute/project tests/example.spec.ts
```

Or install locally:

```bash
npm install --save-dev @voidmatcha/e2e-skills-scanner@3.1.1
npx e2e-skills-scan --scan ./tests --format json
npx e2e-skills-check --help
```

To validate the prepared stable package locally, run `npm pack --pack-destination /absolute/external/output` from `packages/scanner`, then install the resulting `voidmatcha-e2e-skills-scanner-3.1.1.tgz` in a separate consumer project. This creates a local artifact without publishing it.

Scanning does not run tests or probes. The LLM selects a candidate, supplies source-backed inputs and interprets evidence; the CLI validates inputs and preserves reproducible execution evidence. Missing inputs are reported rather than guessed.

The four Agent Skills are installed separately. The reviewer uses a bundled copy of the scanner, so installing the skill does not require this npm package. The following source-checkout commands document that separate entry point.

## Installed scanner

The `scan.sh` entry point launches the bundled Node scanner and verifies its runtime manifest before loading it. The bundle includes the pinned TypeScript parser and licenses. It requires Node.js 22 or newer at `/opt/homebrew/bin/node`, `/usr/local/bin/node`, `/usr/bin/node` or `/bin/node`. It does not select a project executable from `PATH`, download tools, execute project configuration by default or start a probe. Missing or damaged runtime files and an unavailable supported Node executable fail with exit 2.

From the repository root, or using the corresponding installed skill path:

```bash
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh /absolute/project/tests
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh /absolute/project/tests --format json
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh /absolute/project/tests --fail-on p0-candidate
```

The launcher defaults to the current directory and text output. `--format json` selects the canonical report; `--report-file /absolute/new-file` writes a private text report without overwriting an existing path. Confirmed findings and candidates remain separate. Candidates require contextual review and do not become confirmed defects through formatting or policy selection. Exit 0 means the selected policy found no violation within completed analysis, exit 1 means that policy found a violation, and exit 2 means required analysis or execution evidence remains incomplete. None of these outcomes establishes full JavaScript coverage or general test quality.

Limits are fixed: each parsed source file is limited to 16 MiB; relative-import expansion adds at most 128 helper files, 16 MiB of helper bytes and 32 import levels. These helper budgets do not cap already inventoried test files. Symlinks, excluded trees, ambiguous resolution and imports outside the pinned project boundary are not followed. Unsupported imports, syntax, provenance and drift remain explicit uncertainty. Retired backend, executable and limit environment overrides are rejected; `E2E_SMELL_FAIL_ON` remains supported.

## LLM and CLI responsibilities

The LLM reads the project instructions and intended behavior, selects a candidate, prepares a source-backed plan, and interprets the evidence. The CLI discovers supported source shapes, checks candidate identity and plan inputs, and runs only an explicitly approved probe. Static scanning never starts a probe.

| Stage | CLI contract | LLM responsibility |
| --- | --- | --- |
| `discover` | Structured source candidates with locations and hashes; no execution | Decide whether a candidate tests the intended behavior |
| `bind` | Recheck the selected candidate and assemble a plan from supplied inputs | Supply the test command, expected failure, behavior promise and, for POST omission, independent observer |
| `probe` | Validate the full plan, preview approval, then run normal/changed/restored copies and collect evidence | Review the plan and approval, interpret the verdict and remaining uncertainty |

Assertion mutation measures assertion sensitivity (V2); POST omission probes one promised behavior (V3). Neither operation establishes general test quality. Assertion discovery requires the direct named `expect` import from `@playwright/test` and a unique standalone `await expect(page.getByTestId('literal')).toHaveText('literal')`. Aliases, helper imports, other locators, `.not`, `.soft` and extra arguments are unsupported. POST discovery supports standalone awaited `fetch('/literal-path', {method: 'POST', body: data})`, or a separate operator for a standalone direct `fetch(...).then(...)` chain with one to three callbacks. Both require explicit properties and reject spreads or custom fetch bindings. The chain operator removes the request and all chained callbacks together; it is not an isolated network-only fault. Assigned or returned responses and other chain methods are unsupported. The CLI does not invent commands, observers, faults or missing project setup. Source preservation is checked; execution still has host access.

Explicit POST discovery also accepts a `.svelte` file containing one plain `<script>` block at the beginning, with optional leading whitespace and an exact `</script>` closing tag. Only the existing `omit-awaited-post-statement-v1` operator applies. Attributes, module/lang scripts, multiple blocks and ambiguous script delimiter spellings (including in strings or comments) are rejected. Non-script text is blanked for parsing while preserving UTF-16 positions and newlines; candidate hashes, bytes and edits refer to the complete original file. This container adapter does not expand assertion discovery or directory inventory, and does not establish general Svelte support or runtime behavior.

## Discover, bind and preview

```bash
node src/cli.mjs --experimental-focused /absolute/project
node src/cli.mjs --experimental-static /absolute/project
node src/cli.mjs --bounded-static /absolute/project
node src/cli.mjs --scan /absolute/project/tests --format text
node src/check-cli.mjs discover assertion /absolute/project tests/status.spec.ts
node src/check-cli.mjs discover --explain assertion /absolute/project tests/status.spec.ts
node src/check-cli.mjs discover post /absolute/project src/client.js
node src/check-cli.mjs bind /absolute/selected-candidate.json /absolute/binding.json
```

Default discovery returns the existing candidate array. An empty array does not mean the tests are sound. Add `--explain` for a structured `e2e-skills-check-discovery-v1` report: `CANDIDATES_FOUND` (exit 0) or `NO_SUPPORTED_CANDIDATE` (exit 2), with the same candidates and static diagnostic codes. `expect-import-unsupported`, `expect-use-unsupported` and `fetch-use-unsupported` identify file-wide binding guards; `no-supported-assertion-shape` and `no-supported-post-shape` mean no statement met the narrow syntax and uniqueness checks. They do not establish that a fault exists or that the execution environment is ready. Syntax, path and source errors remain errors.

The focused preview covers `#7`; static preview adds bounded detector slices and records JUSTIFIED suppressions. `implementedPatterns` lists partial detector slices, not full coverage of each pattern. Both preview contracts emit JSON and always exit 2, even with no findings. Neither executes project configuration or downloads tools. Invalid source, source above the 16 MiB parser limit, unavailable files and drift remain incomplete. File guards detect persistent changes; they are not an OS sandbox or an atomic project snapshot.

The policy defaults to `E2E_SMELL_FAIL_ON` when set, otherwise `p0`; an explicit `--fail-on` overrides it. Invalid policies exit 2.

The separate `--bounded-static` mode reports `status: "PARTIAL"` even when execution succeeds. Its new JSON contract separates `execution.complete` from `coverage.complete: false` and lists partial rule slices and limitations. Exit 0 means no violation of the selected policy was found within these checks; exit 1 means a policy violation was found; exit 2 means execution or required analysis evidence is incomplete. Parser, provenance, file access and drift diagnostics still take precedence over every policy. No exit code establishes full taxonomy coverage or test quality. The existing preview modes keep their original JSON and always exit 2. No scan starts a probe. Project ESLint configuration runs only with the paired opt-in flags below.

### Static-review contract

`--scan` is the static-review contract used by the installed launcher. It runs the Node detectors directly, without invoking the legacy analyzer. JSON uses `e2e-skills-node-scan-v1`. `status: COMPLETE` and `execution.complete: true` mean mechanical discovery finished within the declared scope. `coverage.complete` remains false, and `review.required` is true whenever retained triage candidates need contextual review. Neither a complete discovery nor exit 0 means the tests are correct.

Uncertainty can become a review obligation only when its exact detector reason and AST location match a retained candidate with the required evidence. Other parser, read, provenance, drift and required ESLint failures remain incomplete and exit 2. Candidate-only P0 findings continue to require the explicit `p0-candidate` policy; they do not become confirmed P0 findings. Import discovery reads bounded local helpers without executing them or treating them as additional test targets.

`--format text` renders a source-linked report. `--report-file /absolute/new-file` also selects text and creates a private file without replacing an existing path. Complete discovery permits a `Summary:` line; incomplete discovery is explicitly partial. JSON consumers should read canonical pattern, severity, disposition and source-location fields instead of inferring them from historical shell headings.

Release validation requires source-candidate and negative controls, policy exits, suppressions, inventory, project ESLint, text/JSON consumers, and installed execution on macOS and Linux with the old analyzer unavailable. The 69 authored legacy call variants are regression inputs, not independent defects or a detection-rate benchmark. Real-project location comparisons are separate evidence. This contract does not claim that the final release gates have passed.

### Existing configuration and rule overlap

`--scan` and `--bounded-static` include `configurationAnalysis`. The bundled parser reads pinned root and already discovered ancestor-scope Playwright, Cypress and ESLint configuration (including `eslint.config.ts`, `.mts` and `.cts`) without executing it. Literal declarations include test selection, retries, timeouts and the six mapped ESLint rules below, with source locations and declared override scopes. Single-use top-level `const` references are followed only when initialized before use and not otherwise referenced, passed, captured or modified. Nested declarations retain their own `baseDirectory` and `NESTED_DECLARATION_ONLY` scope; they are not selected or merged into root settings. Discovery follows only the requested source scope’s ancestor markers, not every nested directory. Dynamic expressions, imported presets, spreads, nested project arrays and unsupported configuration produce structured unknowns. Configuration files are limited to 1 MiB each. These are static observations, not effective runtime settings: scanning still covers the requested source files, including runner-ignored files.

| Existing ESLint rule | Overlapping scanner slice |
| --- | --- |
| `playwright/no-focused-test`, `mocha/no-exclusive-tests` | `#7` |
| `playwright/no-unnecessary-assertions` | `#4f` |
| `playwright/missing-playwright-await` | `#15` |
| `playwright/no-wait-for-timeout` | `#9` |
| `cypress/no-unnecessary-waiting` | `#9b` |

The comparison lists known overlapping slices and scanner slices without a mapping in this table; it does not establish equivalent coverage or the absence of other ESLint rules. A declared rule is not assumed active for every file. With the approved project ESLint run below, `projectEslint.effectiveConfiguration.files` reports each mapped rule as `ENABLED`, `DISABLED`, `NOT_CONFIGURED` or `UNKNOWN` for each linted file, after ESLint resolves configuration and overrides. Missing effective configuration makes that approved run incomplete. Only rule states are retained, not plugin options, configuration logs or arbitrary messages. Independent scanner rules remain enabled; equivalent reported findings are deduplicated as before. No configuration observation starts a test or probe.

### Optional local project ESLint

```bash
node src/cli.mjs --bounded-static /absolute/project/tests \
  --project-eslint --trust-project
# The installed scan.sh entry point accepts the same paired opt-in flags.
```

Use this only for a trusted project. Both flags are required; preview modes reject them. The CLI resolves the project's already installed `node_modules/eslint`, runs its pinned root configuration against inventoried E2E source files, resolves effective rule states per file, and never downloads dependencies or enables fixes. Supported engines are ESLint 8.21–8.x with a root legacy config and ESLint 9–10 with a root flat config. Legacy nested configs, ignored files, missing dependencies/configs, unmapped rule messages and failed analysis remain incomplete (exit 2). Six mapped Playwright/Cypress/Mocha rules contribute findings; project-disabled ESLint rules stay disabled in that tier. Independent static detectors still run. JUSTIFIED handling and ESLint-before-AST deduplication apply.

`projectEslint` records execution and engine version. Config/plugin code has host and network access; the watchdog bounds runtime/output but is not a sandbox. The root config and project markers are hash-pinned and rechecked, but their imported dependencies are not an atomic frozen graph.

Bounded reports also include `execution.diagnostics`: an array of `{code, detector, file, start?}` objects. Codes distinguish parser, import, binding and unsupported-analysis gaps without exposing source-controlled reason text; unknown reasons retain an unknown code and exit 2. `start` is an optional source offset. These codes guide follow-up work, not findings or coverage claims.

Review and select one candidate object from the discovery array, then prepare an explicit binding using the complete [assertion and POST templates](examples/README.md). The templates include every required nested field and intentionally invalid placeholders; fill them from reviewed project evidence before binding. All operators require `source`, `test_selector`, a source-backed `promise`, a pinned `test` command, native `report`, and linked `expected_failure`. POST omission also requires `test_paths` and a pinned independent `observer`. `dependency_dirs` is optional. The binding produces manifest v1 for the bundled probe; command, wrapper and observer discovery are not automatic. Missing inputs are errors. Binding alone does not validate the full execution manifest; probe preview performs that validation. Missing top-level binding inputs return `{"schema":"e2e-skills-check-requirements-v1","status":"NEEDS_INPUT","operator":"omit-awaited-post-statement-v1","requirements":[{"field":"observer","reason":"Explicit manual binding required; no value is inferred."}]}` with exit 2. The LLM can supply those fields and retry. Invalid supplied inputs and source drift remain errors; missing `source` means freshness has not yet been checked.

```bash
node src/check-cli.mjs probe \
  --plan /absolute/plan.json --output-dir /absolute/new-preview --preview
node src/check-cli.mjs probe \
  --plan /absolute/plan.json --output-dir /absolute/new-execution \
  --execute --trust-checkout --approve-sha256 REVIEWED_PREVIEW_DIGEST
```

Probe execution requires a trusted, prepared project. The bundled Node runner is byte-identical to the skill's `run-probe.mjs`; a parity test guards that copy. It freezes commands and source hashes, then runs normal, changed and restored copies. Commands retain host and network access. No dependencies, browser, project, observer or test command are installed or inferred. Output directories must be fresh and outside the source project. `SURVIVED` is an observed result, not a passing quality gate; inspect the verdict, not just exit status.

## Historical validation

The [3.1.0 pre-release verification record](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/547146b579f9105a72ed2b90837bab5d89340b08/releases/v3.1.0/pre-release-20261023/README.md) preserves the evaluated source hashes, local CI logs, installed-package and skill receipts, Linux checks and a prepared live reviewer probe. That record covers its pinned 3.1.0 source, not the later Node probe runner.

Package and installed-skill checks cover separate distribution paths. Linux used a cached image and an extracted package rather than a fresh npm installation. The live probe used a prepared SvelteKit project and supplied execution inputs: normal passed, the selected fault failed, and the restored copy passed. These are bounded workflow checks, not general detection accuracy. Historical studies and the earlier 5.9.3 parser evidence remain frozen in the [external evidence manifest](https://github.com/voidmatcha/e2e-skills/blob/main/benchmarks/external-evidence.json).

### Independent project execution

On 2026-10-21, the packed, locally installed CLI ran React Router's existing `Supports React Server Functions side-effect redirects` test at upstream commit `7aea711dd1ae2bc5a076d13ff17291829690fa74`. The original test passed, changing its literal `toHaveText` expectation failed at the selected assertion on line 2150, and a fresh restored copy passed. Each native report contained one Chromium test with one worker, no retries and no skips. The runner returned `ASSERTION_SENSITIVE` and verified unchanged source hashes. The plan, native reports and independent report audit are retained under `$HOME/.cache/e2e-skills-bench/independent-react-router-probe-20261021-v1/`.

Two additional existing OSS tests also returned `ASSERTION_SENSITIVE`: TanStack Router (`ed5577593a749b8c7193cc7b5d945fd084bfac2f`, `match-params.spec.ts:42`) and SvelteKit (`c7476484fa0bb7be0447f9b8c985e17db24f7072`, embed `test.js:13`). Each ran normal PASS, mutation FAIL at the selected assertion, and restored PASS, with one test, no retries or skips and unchanged original app/test bytes. Their existing fixtures used pinned published dependencies rather than full upstream workspace builds. Six native reports and their hashes were independently reread; initial setup failures remain retained under `$HOME/.cache/e2e-skills-bench/independent-native-v2-20261021-v1/`.

These are three selected existing OSS tests and V2 evidence only. Project preparation required a locked dependency install, two upstream core builds, a wrapper and explicit dependency mounts. Those external dependencies are neither frozen by the approval digest nor forced read-only. These V2 results do not establish automatic setup or generic mutation coverage; the earlier V3 detection/survival pair uses authored controls.

A separate packed v13 run exercised the existing MSW Remix test `receives mocked responses on browser runtime` at commit `6da9367a877ba550b95b74343d1349c487d744d8`. Omitting its direct POST and full `.then()` chain produced normal PASS, a linked `locator.waitFor` failure at the original test's line 18, and restored PASS (`DETECTED`). An external observer recorded the real button click, POST, service-worker response and DOM; the changed copy retained the click but lost the request and effect. Original app/test bytes remained unchanged. The first attempt exhausted the whole test timeout and remains `CANNOT_VERIFY`; a separate attempt set a 5-second action timeout in external configuration so the existing wait failed before the test deadline. Native reports and observer hashes were independently reread under `$HOME/.cache/e2e-skills-bench/independent-msw-remix-probe-20261021-1792584912/`. This is one mocked-backend workflow, not real-server persistence proof. The injected fault removes response/UI callbacks too, and the click demonstrates trigger reach, not line coverage.

On 2026-10-22, SvelteKit's existing `non-GET requests evict cached responses with hashed keys` test at commit `c7476484fa0bb7be0447f9b8c985e17db24f7072` returned `DETECTED`: normal PASS, POST omission FAIL at `client.test.js:350`, restored PASS. The upstream route, server handler and test bytes were preserved in extracted scaffolding with pinned published dependencies. A separate browser observer confirmed `update` execution through CDP coverage, one POST and server cookie count 1 in normal/restored phases, and no POST/count 0 in the changed phase. Independent audit checked all three native reports and upstream Git blobs. A separately authored visibility-only control returned `SURVIVED`; it is a control on the same case, not an additional upstream defect. Evidence: `$HOME/.cache/e2e-skills-bench/real-server-post-20261022-v1/`. This covers one real HTTP/cookie-state case. The observer uses a separate context; full-app execution, durable database writes and automatic setup remain unverified.

A separate targeted inspection of eight app-source files in two local OSS checkouts found one supported POST omission candidate and seven unsupported files. The candidate, Cal.com's Basecamp project selector at commit `e91bb0c38251b0ee6f87eec70ce4940822fb0cf3`, has no matching existing E2E test in the inspected Playwright directory; its API also needs authentication, integration credentials and an external Basecamp request. It was not executed. Discovery evidence is retained under `$HOME/.cache/e2e-skills-bench/post-app-candidate-survey-20261021-1792579907/`. These selected files are a feasibility inspection, not a representative coverage or detection-rate benchmark.

<details>
<summary>Developer detail: implemented detector slices and known limits</summary>

Implemented modules:

- `inventory`: candidate discovery, file identity and drift checks, with legacy differential fixtures. Project markers are pinned without execution. Self-checkout fixture exclusions apply only to the canonical fingerprint and respect project boundaries when a nested project is explicitly requested, as well as explicitly requested fixture paths. Whole-checkout scans retain the legacy global fixture exclusions.
- Internal `dedupe`: legacy file/line/class accounting with ESLint, AST and heuristic precedence; unclassified variants remain distinct. The CLI retains a duplicate ledger and counts retained findings only. Opted-in local ESLint and AST findings are integrated; the legacy ast-grep backend is not ported.
- Internal `project-context`: nearest Git or package/framework marker discovery, with scan and project roots kept distinct. Configuration discovery pins file hashes; a separate bounded AST pass reports root and already discovered nested declarations and unknowns without execution. Symlinked markers are incomplete. The explicit local ESLint opt-in loads a pinned root config; nested legacy cascade is unsupported.
- `report`: counts and exit policies for already-deduplicated findings. Candidate-only results do not fail the confirmed-only `any` policy; incomplete execution always exits 2.
- Internal `focused-tests`: a bounded raw detector for proven Playwright imports, fixtures, Cypress globals and immutable focused aliases, with lexical shadowing guards. Complete import-graph and pattern coverage are pending. `#7` is never exempted by JUSTIFIED. A legacy same-line shadow false positive and a mixed CommonJS/ESM alias false negative are recorded separately from parity results.
- Internal `scope`: hash-pinned relative fixture, ESM re-export and bounded literal CommonJS provenance; unresolved, mutable or ambiguous imports remain incomplete. Conditional, mixed and property-style CommonJS exports are unsupported. CLI integration uses the same pinned bytes for scope and detectors.
- Internal `receivers`: shared proof for fixture Page, immutable Locator chains and imported Playwright expect. POMs, arbitrary factories and mutable receivers remain unproven.
- Internal `waits`: bounded raw Page-fixture and Cypress numeric waits, with variable waits kept as candidates. Static preview applies the JUSTIFIED policy; broader Page lineage is pending.
- Internal `justified`: the legacy immediate-line, 8-line fluent-chain and 24-line browser-callback windows. P1/P2 findings move to a suppression ledger, P0 remains a review candidate, and `#7` is never suppressed.
- Internal `assertions`: direct ambient `expect(Cypress.$(...))` truthiness and bounded `*Page` member-handle truthiness can produce source-linked candidates; they are not confirmed findings. Only precisely matched uncertainty can be handed off for review in `--scan`. Ordinary objects and known scalar fields are excluded; complete POM lineage remains unsupported. Discarded locator/boolean-result candidates (`#8a`/`#8b`), uncalled matchers (`#8c`), proven direct Locator truthiness (`#4f`), optional and statically computed truthiness matcher candidates, numeric-shape candidates (`#4a`) and positive attachment candidates (`#4b`). Direct Page/Locator type annotations are candidates only, not runtime proof. Numeric candidates do not establish that a subject is nonnegative or that its assertion always passes.
- Internal `suite-data`, `control-flow`, `networkidle`, `actions`: bounded serial configuration (`#10b`), initialized module state (`#19`), exception/skip candidates (`#3b`/`#11c`), Page network-idle calls (`#9c`), and literal forced actions (`#5b`). These are partial ports; dynamic options and unproven receiver graphs are not complete coverage.
- Internal `promises`: bounded missing-await checks (`#15`/`#16`) for imported expect and proven Page/Locator operations. Directly discarded expect and direct `page` operations are confirmed; Locator aliases, typed, deferred, void, optional and computed calls remain candidates, preserving the legacy migration boundary. Await, return and directly observed Promise aggregates are excluded. POM fields, complete saved-promise lifetimes, namespace expect and dynamic methods remain unsupported; supported discarded retry assertions produce missing-await candidates; unsupported retry shapes remain diagnostic.
- Internal `page-reads`: one-shot Page URL assertions (`#4h`) outside proven retry callbacks and direct Page selector APIs (`#17`). Proven immutable Page aliases and identifier selectors remain P1 candidates; selector values and types are not inferred. Identifier selectors on bounded `*Page` instances or unresolved `*Page` names in proven test callbacks can produce candidates with explicit review requirements; they are not confirmed Page calls. Complete POM lineage, type-only Page proof and complex selectors remain unsupported.
- Internal `cypress-assignment`: same-line simple `const`/`let`/`var` assignment of a proven global Cypress chain (`#10e`), excluding spy/stub calls. Split, destructured and subsequent declarations are diagnostic; alias-mediated assignments are outside this slice.
- Internal `dom-queries`: raw document queries (`#6`) and positional-selector candidates (`#10a`) in bounded framework contexts, retaining P1 triage. Selected immutable POM query chains and custom Cypress query chains produce candidates with unresolved-subject evidence. Arbitrary receiver provenance remains unsupported.
- Internal `catch-handlers`: inline promise catch callbacks (`#3`), retaining P0 triage for empty, fallback and single-identifier parameterized bodies. Parameterized callbacks that throw on all bounded paths are excluded; conditional propagation remains a candidate. Direct awaited hard `toBeVisible()` assertions inside a proven async test callback also produce candidates for an empty catch or an arrow callback’s bare finally return. These two forms require a single assertion statement, proven Locator/expect bindings and no matcher arguments. Rethrows and cleanup are excluded. Direct discarded allSettled assertions and bounded finally returns have additional candidate slices. Promise.reject, complex parameters and broader try/catch remain diagnostic gaps; direct filesystem cleanup is excluded.
- Internal `timeout-zero`: literal zero timeout (`#4g`) on bounded proven Playwright action, navigation and assertion signatures. This is a retry/deadline hazard, not an immediate-check or always-pass claim. Cypress timeout semantics remain a separate semantic review; dynamic options and retry wrappers are unsupported.
- Internal `soft-assertions`: direct, unawaited physical-line-start `expect.soft` calls (`#18`), preserving P1 triage. Awaited, returned, inline and multiline calls remain diagnostic gaps. A soft assertion alone does not establish an unsafe prerequisite.
- Internal `cypress-callbacks`: async Cypress test/hook callbacks that directly queue commands (`#10d`) and continued action chains (`#10f`), both P1 candidates. Hook identity comes from shared scope; aliases, optional/computed chains and arbitrary helper execution remain unsupported.
- Internal `state-reads`: directly awaited Playwright state/content reads in assertions (`#4c-4e`), as P1 candidates. Proven retry callbacks are excluded. Wrapped reads, POM and type-only receiver proof remain diagnostic gaps.
- Internal `collections`: absence assertions (`#4i`), awaited Locator iteration and Cypress `each` (`#4k`), as P1 candidates. These shapes include legitimate empty-state assertions and setup loops. Positive-match proof, collection size and the purpose of a loop require semantic review. Aliased Cypress chains and optional/computed calls are outside this slice.
- Internal `accessible-names`: bounded same-line Page name options and Cypress unanchored role-name regexes (`#10c`), as P1 candidates. Preserve the legacy explicit-exact exclusion and direct receiver spelling. Dynamic or spread options remain diagnostic; collisions and container scope require semantic review.
- Internal `conditional-assertions`: bounded inline `if`, logical and ternary assertion paths and proven Page/Locator boolean conditions (`#5a`), as P0 candidates. This does not decide whether a required assertion is bypassed. Generic assert helpers, transitive calls, awaited-variable dataflow, expect wrappers and separate else bodies remain diagnostic gaps.
- Internal `credentials`: a bounded literal/name-based `#14` P1 candidate sweep for forms, login helpers and authentication payloads. This does not validate secrets or prove authentication intent. Findings contain locations, not source values; public JSON also omits JUSTIFIED reason text. Dynamic strings, literal aliases and multiline payloads remain outside this slice. This is not a general redactor for arbitrary project metadata or paths.
- `check`: three narrow operators: change one awaited literal `toHaveText` expectation, omit one standalone awaited literal POST, or omit one standalone POST with its one-to-three `.then()` callbacks. Bundled TypeScript 6.0.3 replaces the historical spike's explicit 5.9.3 parser. Candidate discovery is not runtime proof.

Run `npm ci --ignore-scripts` and `npm test` here. Tests use the exact bundled TypeScript version. Static checks do not load a target compiler or configuration; dedicated ESLint tests explicitly execute authored trusted configs in subprocesses. The legacy policy comparisons additionally need this source checkout's existing scanner prerequisites.

</details>
