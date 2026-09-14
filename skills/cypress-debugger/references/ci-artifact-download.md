# Downloading a CI-run report (Prerequisites detail)

Read this only when the report is from CI and you need local artifacts
(screenshots/videos for Phase 3).

Download the CI artifact into a fresh local directory using a
user-confirmed repository slug and numeric run ID. Do **not** download
artifacts from forked-PR runs or from arbitrary URLs.

```bash
REPO=<confirmed-owner/repository>
RUN_ID=<numeric-github-actions-run-id>
PROJECT_ROOT=$(/bin/pwd -P)
<skill-dir>/scripts/run-artifact-reader.sh \
  --project-root "$PROJECT_ROOT" \
  --reader download-cypress-reports.py \
  --pass-env HOME --pass-env GH_TOKEN -- \
  --repo "$REPO" "$RUN_ID"
```

Pass `--pass-env GITHUB_TOKEN` instead of `--pass-env GH_TOKEN` when that is
the name holding the token, and drop the token option entirely when `gh` reads
an already-authenticated host config under `HOME`. `--pass-env HOME` is always
required. Do not add any other variable: the launcher rejects a name outside
this helper's allowlist, and that rejection is the intended behavior, not an
obstacle to route around.

The helper requires the user-confirmed strict `owner/repository` slug, resolves
that repository's numeric identity from `github.com`, and binds the Actions
run's repository, head-repository, and pull-request head metadata to that
identity. It uses explicit repository API endpoints on the fixed host and
ignores ambient checkout and `GH_REPO` context. It rejects forked runs, then
requires exactly one unexpired artifact named `cypress-reports`, streams its
bounded ZIP into a private staging directory, and never gives `gh` an extraction
path. It walks the physical repository directory through descriptor-relative
no-follow opens,
requires `cypress/reports/` to be absent, and rejects traversal, duplicate,
encrypted, symlink, and special ZIP members. Extraction uses held directory
descriptors; staging identity is rechecked and the completed tree is published
with an atomic no-replace rename. The helper resolves an absolute `gh`
executable outside the repository, invokes it with a minimal allowlisted
environment, canonicalizes `HOME`, rejects a repository-contained `HOME`, and
leaves no published report after a failed or non-zero download. This prevents
normal path-component and destination-swap races; it is not a sandbox against a
same-user or privileged local process that can discover and move the private
staging directory while the download is active. Stop such concurrent untrusted
processes before downloading.

Then reproduce the specific failing spec locally with the same environment:

```bash
# Default: the exact failing spec, one attempt. Use the repository's existing
# exact-title filter too when one is already installed and trusted.
/usr/bin/env -i PATH="$PATH" node_modules/.bin/cypress run \
  --spec path/to/spec.cy.ts --browser chrome \
  --config retries=0,video=true

# If CI uses a non-default baseUrl or env, mirror it
/usr/bin/env -i PATH="$PATH" CYPRESS_BASE_URL=<ci-base-url> \
  node_modules/.bin/cypress run \
  --spec path/to/spec.cy.ts --config retries=0
```

Only add a retry probe after repository evidence proves every action and its
system-boundary effects are idempotent. Then, and only then, use the same exact
spec (and existing exact-title filter when available) with bounded
`--config retries=2`.
