<!-- SPDX-License-Identifier: Apache-2.0 -->
# Portable assertion and behavior probes

Use this workflow when runtime proof is requested for a Playwright or Cypress
project. The reviewer discovers its test setup and prepares probe artifacts,
then selects the behavior, test, and smallest meaningful change from source
evidence. The bundled Node.js executor handles copying,
exact edits, execution, evidence collection, and bounded result classification.
No project registration or repository evaluation-infrastructure import is needed.

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

Show one concrete execution packet: commands, environment, startup/reset and
shutdown, local resource boundary, and new infrastructure files. Existing approval
for the exact scope remains valid; ask together only for authority actually missing.
Run no project-controlled code before that authority exists. First run the unchanged
selected test in the disposable snapshot with one worker, no skip, and retry zero;
retain the native report. A failing or skipped baseline is not mutation or fault
evidence. Report a product/test failure separately; permit at most one
evidence-backed setup correction in a fresh snapshot, preserving both attempts.
Persistent setup failure leaves runtime proof unexecuted and static review available.

Select the requested question. V2 needs no V3 observer or backend service when the
selected test itself does not require one; quote the selected assertion as V2's
source anchor. V3 needs a separately sourced behavior promise and actual phase-app
observation as below. Do not substitute V2 for requested V3 evidence or add V2
automatically when only V3 was requested. Start with one test and one change;
expand only when the user requested broader coverage and the first result is valid.

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
| `edits` | Exact edits: `{ "path", "before", "after", "sha256", "kind" }`; `kind` is `source` for V3 or `test` for V2 |
| `test` | `{ "argv": ["executable", "argument"], "timeout_seconds": 120, "source": { "path": "included/native-wrapper.mjs", "sha256": "digest" } }` |
| `observer` | V3 required: command plus `source: { "path", "sha256" }` pinning the included observer script |
| `report` | `{ "format": "playwright-json" or "cypress-json", "path": "fresh/relative/report.json" }` |
| `expected_failure` | Nonempty `contains` and `location` strings identifying the intended assertion failure |
| `dependency_dirs` | Optional explicit `{ "path", "target" }` dependency links |

Pin `location` to the promise-linked assertion's file and line (and column when
available), confirmed in the actual native error. Pin `contains` to that
assertion's specific matcher or expected-value message. A generic
`AssertionError`, filename alone, or unrelated stack frame does not establish
that link.

Failure locations must match complete line/column tokens: line 7 is not line 70,
and column 3 is not column 30. A relative file anchor cannot match a different
directory's file with the same basename; absolute locations must identify the
corresponding phase file. For Cypress only, a `webpack:///./<test-path>` frame
can identify an exact entry in `test_paths`; other webpack namespaces and encoded
paths are not resolved. Separate source snippets and numbered code frames
inside native errors are context, not proof that their assertions failed.
The executor excludes these from failure matching. Text-only locations must
appear as complete location lines, native stack frames, or inline locations in
recognized error messages; ambiguous prose is not accepted. This textual check
does not identify arbitrary assertion expressions. Inspect the native error message and
raw report before accepting a link.

Use `{project}`, `{report}`, `{selector}`, and `{phase}` argument placeholders
where supported by the executor. Commands run with the phase project as their
working directory. Use existing executables, not an implicit package downloader.
Exact source edits must match once and change bytes. V3 cannot edit listed test
paths; V2 cannot edit application paths. Include all relevant test helpers in
`test_paths`; a declaration is not a substitute for reviewing the actual diff.

Pin the native wrapper's included source, reference it in argv, and never edit it
as the fault. The native command must select one test, one worker, and retry zero; arrange its
framework config accordingly. It must write a fresh native JSON report and return
the native test's exit status. An approved command wrapper may own app startup,
test execution, a separate browser observation, and shutdown. Each command's
remaining process group is cleaned up at exit, so finish owned server work before
returning. Preserve the native command, report, and logs inside
that wrapper; a wrapper's success status cannot conceal a native failure.

## Observe the actual phase app

Pin an observer script included in the source snapshot and reference that script
in its command arguments. Emit one JSON object to stdout:

```json
{
  "project": "/absolute/path/to/current/phase/project",
  "promised_effect": true,
  "fault_reached": false,
  "evidence": [{"path": "probe-evidence/observation.json", "sha256": "artifact digest"}]
}
```

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
node <skill-base>/scripts/run-probe.mjs --plan <plan.json> --output-dir <different-fresh-run-path> --trust-checkout --execute --approve-sha256 <preview-digest>
```

Preview reads JSON and source files without importing or running project code.
Review its exact argv, environment, paths, edits, observer, and source snapshot.
Preview artifacts remain retained; use a different fresh output directory for
execution. Execute only within the user's existing trust and approval for that exact scope;
ask only for genuinely missing authority. A digest is a consistency check, not
user authorization. Changed inputs or executor bytes require a new preview.

Fresh phase copies protect the original from the executor's own edits; they are
**not an OS sandbox**. Approved commands retain host filesystem/network access.
Dependency links are shared and are not forcibly read-only. Only use trusted
commands and disposable local resources; do not claim those links protect the
dependency store. The executor does not install or delete anything, and retains
all phase workspaces and failure evidence.

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
