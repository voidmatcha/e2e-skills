## Prerequisites: Get the Report

Determine the report source in this order:

Use the repository's existing Playwright script when it already preserves the required reporter and flags. Otherwise use the project-local `node_modules/.bin/playwright` commands below. If package-manager resolution is required, replace that prefix with `npx --no-install playwright`; never use a plain `npx` invocation, which may install a different version.

**Repository execution gate:** Project-local binaries, package scripts, Playwright configuration, reporters, fixtures, and plugins can execute code controlled by the checkout. Do not execute any of them until the user has both explicitly trusted this repository and approved the exact command line, including environment assignments, reporter options, paths, and flags. General approval to diagnose, reproduce, or use a test environment is not exact command approval. Until both approvals exist, inspect validated artifacts and present the exact command as `recommended`; do not run it.

**Repository command environment gate:** Run every repository-controlled command below with an explicit empty environment, as shown by `/usr/bin/env -i PATH="$PATH"`. The approval must cover the exact command and the name and current value of every variable passed into that environment, including `PATH`. Add another explicit `NAME="$NAME"` only when the command requires it and that exact name/value was approved. Do not forward ambient credentials or interpreter/package-manager injection variables such as `AWS_*`, `NODE_OPTIONS`, `NPM_CONFIG_*`, `BASH_ENV`, or `PYTHONPATH` merely because they exist. The report publisher independently defaults its child to a fixed system `PATH`; repeat `--pass-env NAME` before the output path for each approved variable the child actually needs. Project-local Node launchers usually need the approved current `PATH`, hence `--pass-env PATH` below.

**Execution safety gate (before any Playwright test command):** Generate or reproduce a report only when the whole target stack, including its APIs and data stores, is `local/disposable` or an explicitly approved non-production test environment. A localhost frontend backed by shared or production services does not pass this gate. When the environment is production, shared, or unknown, do not run tests; analyze existing validated artifacts or request a disposable target. Warn that a rerun can replay non-idempotent writes such as submit, payment, delete, registration, message send, or toggle actions. Reset to a known disposable state first and run the narrowest spec once; never use retries to replay those writes unless system-boundary idempotence is proven.

Playwright applies `--grep` to the full title path, not only the test title. Resolve the filter before every targeted run:

```bash
/usr/bin/env -i PATH="$PATH" node_modules/.bin/playwright test path/to/spec.spec.ts \
  --list --grep 'escaped unique title fragment'
```

Continue only if the list contains exactly one test; otherwise refine and escape the regex fragment, then reuse that same fragment below.

**1. A report already exists locally → detect which reporter produced it.** The reporter decides whether a machine-readable `results.json` even exists:

```bash
ls playwright-report/index.html 2>/dev/null   # HTML reporter (the default)
ls playwright-report/results.json 2>/dev/null # JSON reporter (only if explicitly configured)
ls blob-report/*.zip 2>/dev/null              # blob reporter (sharded CI runs)
```

- **`results.json` present** → skip to Phase 1.
- **HTML report only** (`index.html` + `data/*.zip`, the common case) → there is **no** `results.json`. The HTML report embeds traces under `playwright-report/data/*.zip`. Either regenerate a JSON report (below) or jump to Phase 3 and read those trace zips directly.
- **`blob-report/` present** (sharded run) → merge shards first with the bundled
  JSON publisher shown below.

**2. No report (or HTML only and you want structured data)** → run tests locally and write JSON to a file (do NOT read stdout directly — output may be truncated):

```bash
PROJECT_ROOT=$(/bin/pwd -P)
<skill-dir>/scripts/run-artifact-reader.sh \
  --project-root "$PROJECT_ROOT" \
  --reader publish-json-report.py --pass-env PATH -- \
  --pass-env PATH \
  playwright-report/results.json -- \
  node_modules/.bin/playwright test \
  path/to/spec.spec.ts --grep 'escaped unique title fragment' --retries=0 \
  --reporter=json
```

The first `--pass-env PATH` lets the launcher forward the approved `PATH` into the publisher; the second is the publisher's own option, forwarding that same `PATH` to the project-local Node launcher it starts.

For a sharded blob report, use the same publisher:

```bash
PROJECT_ROOT=$(/bin/pwd -P)
<skill-dir>/scripts/run-artifact-reader.sh \
  --project-root "$PROJECT_ROOT" \
  --reader publish-json-report.py --pass-env PATH -- \
  --pass-env PATH \
  playwright-report/results.json -- \
  node_modules/.bin/playwright merge-reports --reporter=json ./blob-report
```

The helper rejects absolute/traversing output paths, symlinked report-directory components, symlink/non-file destinations, non-zero commands, and reports that fail the bounded reader's strict JSON, schema, outcome, or stats validation. The one accepted non-zero exit is status 1, which `playwright test` returns when tests fail, and only when the captured report then passes that same validation, so a still-failing test's report can be published. Its child environment contains only a fixed system `PATH` plus variables named by repeated `--pass-env NAME` options; names must be valid environment-variable identifiers, set, and non-duplicate. A bare child executable is resolved only through that child `PATH`, while an explicit relative/absolute executable is resolved to an executable regular file before launch. It writes through an opened directory descriptor and atomically publishes only a complete validated report, so do not replace it with `mkdir` plus shell redirection.

**3. Report exists but is from CI and you need to reproduce locally for Phase 3 trace inspection** → read `<skill-dir>/references/ci-artifact-download.md` for the full procedure: confirming the repository slug and numeric run ID with the user (never inferred from ambient state), routing `--reader download-playwright-report.py` through the bundled launcher with only the documented `--pass-env HOME`/token allowlist, what it validates and enforces, and reproducing the specific failing test locally afterward. Never download from forked-PR runs or arbitrary URLs.

If the test passes locally but failed in CI → likely **F7 (test isolation)** or **F8 (environment mismatch)**; jump to Phase 2 with that hypothesis instead of trying to repro further.
