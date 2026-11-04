## Prerequisites: Get the Report

Before any execution, browser request, or artifact write in this procedure, read `references/safety-procedures.md` and apply its gates.

Determine the report source in this order:

Use the repository's existing Playwright script when it already preserves the required reporter and flags. Otherwise use the project-local `node_modules/.bin/playwright` commands below. If package-manager resolution is required, replace that prefix with `npx --no-install playwright`; never use a plain `npx` invocation, which may install a different version.

Apply the repository execution, approved environment, target and replay-safety gates in `references/safety-procedures.md` to every command below; report acquisition grants no additional execution authority.

Playwright applies `--grep` to the full title path, not only the test title. Resolve the filter before every targeted run:

Command form: write `<absolute-project-root>` literally, as the physical (symlink-resolved) absolute project root (run `/bin/pwd -P` once as its own command to learn it). Use no shell variables, `$()`, or `cd`, so an exact-command approval can match each command.

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
<skill-dir>/scripts/run-artifact-reader.sh \
  --project-root <absolute-project-root> \
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
<skill-dir>/scripts/run-artifact-reader.sh \
  --project-root <absolute-project-root> \
  --reader publish-json-report.py --pass-env PATH -- \
  --pass-env PATH \
  playwright-report/results.json -- \
  node_modules/.bin/playwright merge-reports --reporter=json ./blob-report
```

The helper rejects absolute/traversing output paths, symlinked report-directory components, symlink/non-file destinations, non-zero commands, and reports that fail the bounded reader's strict JSON, schema, outcome, or stats validation. The one accepted non-zero exit is status 1, which `playwright test` returns when tests fail, and only when the captured report then passes that same validation, so a still-failing test's report can be published. Its child environment contains only a fixed system `PATH` plus variables named by repeated `--pass-env NAME` options; names must be valid environment-variable identifiers, set, and non-duplicate. A bare child executable is resolved only through that child `PATH`, while an explicit relative/absolute executable is resolved to an executable regular file before launch. It writes through an opened directory descriptor and atomically publishes only a complete validated report, so do not replace it with `mkdir` plus shell redirection.

**3. Report exists but is from CI and you need to reproduce locally for Phase 3 trace inspection** → read `<skill-dir>/references/ci-artifact-download.md` for the full procedure: confirming the repository slug and numeric run ID with the user (never inferred from ambient state), routing `--reader download-playwright-report.py` through the bundled launcher with only the documented `--pass-env HOME`/token allowlist, what it validates and enforces, and reproducing the specific failing test locally afterward. Never download from forked-PR runs or arbitrary URLs.

If the test passes locally but failed in CI → likely **F7 (test isolation)** or **F8 (environment mismatch)**; jump to Phase 2 with that hypothesis instead of trying to repro further.
