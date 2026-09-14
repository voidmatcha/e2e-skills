# Downloading a CI-run report (Prerequisites detail)

Read this only when the report is from CI and you need to reproduce it
locally for Phase 3 trace inspection.

Download the CI artifact into a fresh local directory using a
user-confirmed repository slug and numeric run ID. Confirm both values
explicitly with the user; do not infer the repository from the checkout, a
Git remote, `GH_REPO`, or other ambient state. Do **not** download
artifacts from forked-PR runs or from arbitrary URLs.

```bash
REPO=<user-confirmed-owner/repo>
RUN_ID=<numeric-github-actions-run-id>
PROJECT_ROOT=$(/bin/pwd -P)
<skill-dir>/scripts/run-artifact-reader.sh \
  --project-root "$PROJECT_ROOT" \
  --reader download-playwright-report.py \
  --pass-env HOME --pass-env GH_TOKEN -- \
  --repo "$REPO" "$RUN_ID"
```

Pass `--pass-env GITHUB_TOKEN` instead of `--pass-env GH_TOKEN` when that is
the name holding the token, and drop the token option entirely when `gh` reads
an already-authenticated host config under `HOME`. `--pass-env HOME` is always
required. Do not add any other variable: the launcher rejects a name outside
this helper's allowlist, and that rejection is the intended behavior, not an
obstacle to route around.

The helper binds `gh` from a fixed system/package-manager path, pins API calls
to `github.com` with explicit `repos/<owner>/<repo>/...` API paths,
forwards only `HOME` plus `GH_TOKEN`/`GITHUB_TOKEN`, resolves the confirmed
repository's numeric identity, binds the run, head repository, and pull-request
head to that identity, resolves the artifact ID through `gh api`, streams the
ZIP into a private staging directory, and never lets `gh` choose an extraction
path. It
walks the physical repository directory with descriptor-relative no-follow
opens, requires `playwright-report/` to be absent, rejects traversal, duplicate,
encrypted, symlink, and special ZIP members, applies entry, byte, per-member,
disk-headroom, command-time, and extraction-time limits, extracts only through
held directory descriptors, rechecks staging identity, and publishes with an
atomic no-replace rename. A failed or non-zero download leaves no published
report. This prevents
path-component and destination-swap races from redirecting the helper's normal
writes; it is not a sandbox against a same-user or privileged local process
that can discover and move the private staging directory while the download is
active. Stop such concurrent untrusted processes before downloading.

Then reproduce the specific failing test locally with the same environment:

```bash
# Default: one verified test filter, one attempt.
/usr/bin/env -i PATH="$PATH" node_modules/.bin/playwright test path/to/spec.spec.ts \
  --grep 'escaped unique title fragment' --project=chromium --retries=0 \
  --trace=retain-on-failure --video=retain-on-failure

# If CI uses a non-default baseURL or env, mirror it
/usr/bin/env -i PATH="$PATH" PLAYWRIGHT_BASE_URL=<ci-base-url> \
  node_modules/.bin/playwright test \
  path/to/spec.spec.ts --grep 'escaped unique title fragment' --retries=0
```

Only add a retry probe after repository evidence proves every action and its
system-boundary effects are idempotent. Then, and only then, use the same exact
test with a bounded `--retries=2` diagnostic run.
