## Phase 1: Extract Failures

```bash
# Find report if path not specified
find . -name "mochawesome*.json" -path "*/cypress/*" | head -10
find . -name "*.xml" -path "*/cypress/*" | head -5

# Multiple mochawesome files (mochawesome.json + mochawesome_NNN.json) = a per-spec
# run. Merge them FIRST (see Prerequisites), then point the queries below at the
# merged file. A lone mochawesome.json after a multi-spec run with overwrite=true
# holds only the LAST spec — regenerate with overwrite=false rather than trusting it.

# Resolve <skill-dir> as the directory containing this SKILL.md. Read a
# mochawesome or merged JSON report through the bundled standard-library parser.
# It carries the containing result/suite file into each failed test record and
# emits a bounded stats summary plus failure title, fullTitle, duration, state,
# error, stack, and screenshot paths.
PROJECT_ROOT=$(/bin/pwd -P)
<skill-dir>/scripts/run-artifact-reader.sh \
  --project-root "$PROJECT_ROOT" -- mochawesome \
  --artifact-root cypress/reports \
  cypress/reports/mochawesome.json

# Flag retried tests — stock mochawesome has NO per-attempt data. Cypress replays
# only the FINAL attempt to the mocha reporter, so a test that failed twice and
# passed on attempt 3 appears as a plain `"state": "passed"`; there is no
# attempts[] or currentRetry field in mochawesome JSON (same for JUnit XML).
# Recover the retry signal from these real sources instead:

# (a) Failure screenshots on disk — every failed ATTEMPT writes one. Attempt 1 →
#     "<test> (failed).png"; attempt N → "<test> (failed) (attempt N).png".
#     Report says PASSED but "(failed)" screenshots exist → passed on retry →
#     F1/F15 flaky signal. Report says FAILED with "(attempt N)" screenshots →
#     failed every attempt → consistent failure, NOT flaky.
find cypress/screenshots -name "*(failed)*.png"            # all failed attempts
find cypress/screenshots -name "*(attempt *"               # retries happened at all

# (b) Cypress's own run results, if the project saves them — the Module API and
#     the after:run / after:spec node events DO expose per-attempt data as
#     runs[].tests[].attempts[] (since Cypress 13, after:run/module-API attempts
#     carry only {state}; after:spec attempts keep per-attempt error details).
#     When the trusted project already saves this artifact:
#     attempts [{state:"failed"},{state:"passed"}] + final "passed" → flaky (F1).
<skill-dir>/scripts/run-artifact-reader.sh \
  --project-root "$PROJECT_ROOT" -- run-results \
  --artifact-root cypress/reports \
  cypress/reports/run-results.json

# If neither source exists and flakiness is suspected: check `retries` in
# cypress.config first (runMode 0 → Cypress never retried, so passes-on-retry
# cannot be diagnosed from this run), then recommend wiring the after:run dump.

# Both JSON modes require --artifact-root, reject symlinks and special files,
# open every artifact-root component from the filesystem root with
# descriptor-relative no-follow operations, traverse only from that held root
# descriptor, verify descriptor identity/size/mtime/ctime after the read, and
# enforce 8 MiB input, 100-level/200,000-node JSON, 10,000-record,
# 100-attempt-per-test, bounded-string, and 1 MiB output ceilings. Their schemas
# are explicit; malformed or empty artifacts fail closed instead of producing a
# misleading empty result. The smaller input ceiling bounds the JSON decoder's
# unavoidable parse-time allocation before the post-parse depth/node checks.
# run-results accepts only passed/failed/pending/skipped test and attempt states,
# requires at least one attempt per test, and rejects a final test state that
# contradicts the last attempt. Earlier attempts may contain any valid state
# because Cypress retry strategies can require multiple passing attempts.
# JSON parsing also rejects duplicate keys, NaN/positive or negative Infinity
# (including an overflowing literal such as 1e999), a UTF-8 BOM, and trailing
# non-whitespace data; output disables non-finite numbers.

Every artifact-derived string from mochawesome, run-results, or JUnit is
recursively sanitized before any per-field or output truncation. The sanitizer
removes Bearer/Basic credentials, authorization/cookie/API-key headers,
password/secret/token/API-key assignments, URL userinfo, and URL query values;
a non-idempotent residual credential shape fails closed instead of being
emitted. That gate covers a value on the same line as its
key and one continuation line; the second and later lines of a multi-line
value are not classified, so a secret spread over several lines can still be
emitted.

For mochawesome and merged reports, root `stats` and `results` are required.
Every result and nested suite requires `tests` and `suites` arrays; direct tests
on a result and tests in nested suites are both supported. Required stats
`suites`, `tests`, `passes`, `pending`, `failures`, `skipped`, and `duration`
must be nonnegative integers (booleans and numeric strings are invalid).
Optional `testsRegistered`/`other` must also be nonnegative integers,
`hasOther`/`hasSkipped` must be booleans, percentages must be numeric from
0–100, and `start`/`end` must be strings. Parsed suite/test/pass/failure/
pending/skipped counts must match stats; contradictory merged reports fail
closed. Failed `beforeHooks` and `afterHooks` are emitted as failure rows with
their hook phase, title, error, stack, duration, and containing file; a
hook-only failure can never appear as an empty successful extraction.

# Extract failed tests from JUnit XML with the bundled standard-library parser.
# Resolve <skill-dir> as the directory containing this SKILL.md. Each testcase
# stays paired with its own classname, suite file, failure, and source report,
# including mixed pass/fail and multi-suite XML.
# --report-root is required: the parser rejects a symlink root, symlink path
# component, non-regular input, or any input outside that canonical root. It
# reads at most 8 MiB per report, accepts only BOM-free UTF-8 XML (an encoding
# declaration, when present, must also say UTF-8), rejects DOCTYPE and ENTITY
# declarations, requires testcase elements to be direct testsuite children and
# failure/error/skipped elements to be direct testcase children, and enforces
# 100,000-node and 100-level depth ceilings while streaming the parse.
# Suite/root counters are reconciled in one postorder pass; the parser does not
# retain or repeatedly rescan complete nested XML subtrees. One invocation
# accepts at most 128 reports and 16 MiB total input. It buffers and validates
# every report before emitting atomic JSONL, so a malformed later report
# produces no partial stdout. Aggregate output is limited to 10,000 rows and
# 8 MiB of serialized UTF-8; per-field and message sizes are also bounded.
PROJECT_ROOT=$(/bin/pwd -P)
<skill-dir>/scripts/run-artifact-reader.sh \
  --project-root "$PROJECT_ROOT" --reader extract-junit-failures.py -- \
  --report-root cypress/reports \
  cypress/reports/results-*.xml
```
