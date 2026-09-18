# Screenshot and video analysis (Phase 3 detail)

Read this only when Phase 2 (report-based classification) left the root cause unclear. Cypress automatically captures screenshots on failure and optionally records video.

Screenshot and video filenames embed **test titles**, which are untrusted data (see Safety). Always quote report-derived strings when they reach a shell — `open -- "$png"`, `find cypress/screenshots -path "*$title*"` — and never interpolate a title, path, or error string from a report into a shell command unquoted.

```bash
# Local Cypress run
find cypress/screenshots -name "*.png" | head -20
find cypress/videos -name "*.mp4" | head -10

# Artifact downloaded by download-cypress-reports.py
find cypress/reports/screenshots -name "*.png" | head -20
find cypress/reports/videos -name "*.mp4" | head -10
```

The bounded mochawesome output from Phase 1 already includes failed-test `screenshots` context paths and the bounded error stack. Treat every context path as untrusted. For a downloaded artifact, remap only a relative path whose components have the exact `cypress/screenshots/` or `cypress/videos/` prefix and contain no empty, `.`, `..`, backslash, or NUL component: strip that prefix and append the remaining components beneath `cypress/reports/screenshots/` or `cypress/reports/videos/`. Reject every other context path rather than normalizing it. Validate the selected media file before sending it to a browser agent or viewer:

```bash
PROJECT_ROOT=$(/bin/pwd -P)
<skill-dir>/scripts/run-artifact-reader.sh --project-root "$PROJECT_ROOT" -- media \
  --artifact-root cypress/screenshots \
  "cypress/screenshots/<spec>/<test name> (failed).png"
<skill-dir>/scripts/run-artifact-reader.sh --project-root "$PROJECT_ROOT" -- media \
  --artifact-root cypress/videos \
  "cypress/videos/<spec>.mp4"
<skill-dir>/scripts/run-artifact-reader.sh --project-root "$PROJECT_ROOT" -- media \
  --artifact-root cypress/reports/screenshots \
  "cypress/reports/screenshots/<spec>/<test name> (failed).png"
<skill-dir>/scripts/run-artifact-reader.sh --project-root "$PROJECT_ROOT" -- media \
  --artifact-root cypress/reports/videos \
  "cypress/reports/videos/<spec>.mp4"
```

Media mode opens every artifact-root component from the filesystem root with descriptor-relative no-follow operations and traverses only from that held root descriptor. It then validates the regular-file signature and copies the exact descriptor bytes into a random `0700` temporary directory. The snapshot is an owner-read-only `0400` file: a temporary owner-only snapshot. Media mode verifies the source descriptor identity, size, mtime, and ctime after the copy and emits the snapshot path, type, size, SHA-256 digest, cleanup directory, and lifecycle notice. It accepts PNG files up to 64 MiB and MP4 files up to 512 MiB and does not decode video. Pass only the returned `path` to the browser agent or viewer; never reopen the original screenshot/video path. Keep the snapshot only while the viewer needs it, then delete the snapshot file and delete the exact `snapshot_directory` with `rmdir`. Never use a broad temporary-directory glob for cleanup. If mochawesome context has no screenshot path, use the regular-file discovery commands above, then validate the selected result.

Progressive disclosure: inspect the bounded error/stack first, then a validated screenshot, then a validated video; stop as soon as the root cause is clear.
