## Prerequisites: Get the Report

Determine the report source in this order:

Use the repository's existing Cypress script when it already preserves the required reporter and flags. Otherwise use the project-local `node_modules/.bin/cypress` commands below. If package-manager resolution is required, replace that prefix with `npx --no-install cypress`; never use a plain `npx` invocation, which may install a different version.

**Repository execution gate:** Project-local binaries, package scripts, Cypress configuration, reporters, support files, fixtures, and plugins can execute code controlled by the checkout. Do not execute any of them until the user has both explicitly trusted this repository and approved the exact command line, including environment assignments, reporter options, paths, and flags. General approval to diagnose, reproduce, or use a test environment is not exact command approval. Until both approvals exist, inspect validated artifacts and present the exact command as `recommended`; do not run it.

**Repository command environment gate:** Run every repository-controlled command below with an explicit empty environment, as shown by `/usr/bin/env -i PATH="$PATH"`. The approval must cover the exact command and the name and current value of every variable passed into that environment, including `PATH`. Add another explicit `NAME="$NAME"` only when the command requires it and that exact name/value was approved. Do not forward ambient credentials or interpreter/package-manager injection variables such as `AWS_*`, `NODE_OPTIONS`, `NPM_CONFIG_*`, `BASH_ENV`, or `PYTHONPATH` merely because they exist. The report publisher independently defaults its child to a fixed system `PATH`; repeat `--pass-env NAME` before the output path for each approved variable the child actually needs. Project-local Node launchers usually need the approved current `PATH`, hence `--pass-env PATH` below.

**Execution safety gate (before any Cypress test command):** Generate or reproduce a report only when the whole target stack, including its APIs and data stores, is `local/disposable` or an explicitly approved non-production test environment. A localhost frontend backed by shared or production services does not pass this gate. When the environment is production, shared, or unknown, do not run tests; analyze existing validated artifacts or request a disposable target. Warn that a rerun can replay non-idempotent writes such as submit, payment, delete, registration, message send, or toggle actions. Reset to a known disposable state first and run the narrowest spec once; never use retries to replay those writes unless system-boundary idempotence is proven.

**1. A report already exists locally** → find it (see Phase 1) and check for the multi-spec trap below before trusting it.

**2. No report → run with a structured reporter** (do NOT rely on Cypress stdout):

```bash
# mochawesome (recommended). overwrite=false is REQUIRED on multi-spec runs:
# Cypress runs every spec as a separate mocha run, and mochawesome's default
# overwrite=true makes each spec OVERWRITE cypress/reports/mochawesome.json —
# a multi-spec run silently keeps only the LAST spec's results.
/usr/bin/env -i PATH="$PATH" node_modules/.bin/cypress run \
  --spec path/to/spec.cy.ts --config retries=0 \
  --reporter mochawesome \
  --reporter-options "reportDir=cypress/reports,overwrite=false,html=false,json=true"

# Merge only when the project already has mochawesome-merge installed. Never
# auto-install a changing latest package during diagnosis. If the local binary
# is absent, inspect the per-spec JSON files independently instead.
test -x node_modules/.bin/mochawesome-merge &&
  PROJECT_ROOT=$(/bin/pwd -P) &&
  <skill-dir>/scripts/run-artifact-reader.sh \
    --project-root "$PROJECT_ROOT" \
    --reader publish-mochawesome-report.py --pass-env PATH -- \
    --pass-env PATH \
    cypress/reports/merged.json -- \
    node_modules/.bin/mochawesome-merge "cypress/reports/mochawesome*.json"

# JUnit (CI-friendly) — the [hash] token is required for the same reason:
# without it each spec overwrites results.xml and only the last spec survives.
/usr/bin/env -i PATH="$PATH" node_modules/.bin/cypress run \
  --spec path/to/spec.cy.ts --config retries=0 \
  --reporter junit --reporter-options "mochaFile=cypress/reports/results-[hash].xml"
```

The Mochawesome publisher opens `cypress/reports/` descriptor-relatively without following symlinks, captures bounded merger stdout into a private temporary file, requires a successful merger exit, and validates the strict Mochawesome schema through `read-cypress-artifact.py`. It rechecks the destination and atomically replaces a prior regular report only after validation. Do not replace the helper with shell redirection. Its child environment contains only a fixed system `PATH` plus variables named by repeated `--pass-env NAME` options; names must be valid environment-variable identifiers, set, and non-duplicate. A bare child executable is resolved only through that child `PATH`, while an explicit relative/absolute executable is resolved to an executable regular file before launch.

**3. Report exists but is from CI and you need local artifacts (screenshots/videos for Phase 3)** → read `<skill-dir>/references/ci-artifact-download.md` for the full procedure: confirming the repository slug and numeric run ID with the user, routing `--reader download-cypress-reports.py` through the bundled launcher with only the documented `--pass-env HOME`/token allowlist, what it validates and enforces, and reproducing the specific failing spec locally afterward. Never download from forked-PR runs or arbitrary URLs.

If the test passes locally but failed in CI → likely **F7 (test isolation)** or **F8 (environment mismatch)**; jump to Phase 2 with that hypothesis instead of trying to repro further.
