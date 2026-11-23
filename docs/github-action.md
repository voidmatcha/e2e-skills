# GitHub Action

Run the static Playwright/Cypress scanner on a pull request without a model, a browser, project dependencies or test execution. Confirmed P0 findings fail the default policy. Candidates appear in the job summary for review. Set `fail-on: p0-candidate` to make P0 candidates fail the job too.

## Usage

The `v3` example below is the intended release interface. It works only after an Action-bearing commit is published under that ref; this change does not create or move a tag. To try a reviewed checkout before publication, replace the last `uses` with `uses: ./` in that checkout. For production, prefer the full commit SHA of a released Action.

```yaml
name: E2E static review
on: [pull_request]
permissions:
  contents: read
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
          fetch-depth: 0 # Needed to show findings in files changed by the PR.
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - uses: voidmatcha/e2e-skills@v3
        id: scan
        with:
          path: tests/
          fail-on: p0
          fail-scope: all
          compare-base: 'false'
          allow-incomplete: 'true'
          format: text
```

The composite Action requires Node.js 22+ with npm/npx on a Linux or macOS runner. It does not install Node itself. `contents: read` is sufficient for checkout; the Action makes no GitHub API calls and requests no PR write permission. Candidates go to the job summary and P0 findings in changed files receive workflow annotations, not bot comments. For `pull_request`, it compares the payload's base and head commits locally and highlights findings in changed files. File membership alone does not prove a finding was introduced by the PR. If either commit is missing locally, the default `fail-scope: all` shows the full report; `fail-scope: changed` and `compare-base: 'true'` fail closed with exit 2.

## Inputs and outputs

| Input | Default | Meaning |
| --- | --- | --- |
| `path` | `.` | Existing file or directory inside `GITHUB_WORKSPACE`; paths escaping the checkout are rejected. |
| `fail-on` | `p0` | `p0`: fail on confirmed P0 findings. `p0-candidate`: also fail on P0 candidates, including justified-review findings. `none`: report findings without failing on them. P1/P2 failure policies are not exposed. |
| `fail-scope` | `all` | `all`: apply `fail-on` to the full scan. `changed`: apply it only to findings in files changed between the PR base and head commits. Requires a `pull_request` event and both commits locally; otherwise exit 2. A finding in a changed file may predate the PR. |
| `compare-base` | `false` | On a PR, also scan the base commit's target from a temporary, data-only Git blob snapshot. Apply `fail-on` only to findings absent from the base scan. With `fail-scope: changed`, apply it only to new findings in changed files. Missing commits, an absent base target, incomplete base or head analysis, or a failed comparison produce exit 2. |
| `allow-incomplete` | `true` | Permit unresolved analysis while reporting the unchecked code. Set `false` to fail when analysis is incomplete. Inventory, source-integrity and other scanner execution errors still fail either way. |
| `format` | `text` | `text` or `json` for the saved `report` output. A readable summary and full JSON are always produced. The job summary lists at most 50 unique diagnostics and 50 findings, changed-file and P0 findings first; the `report` output keeps the full list. |

Outputs `report` and `json-report` are absolute file paths on the runner, available to later steps for an optional artifact upload. `exit-code` is the Action's selected policy result: `0` clear, `1` selected finding policy failed, or `2` incomplete analysis or an execution error. The scanner JSON retains its own full-scan `execution.exitCode` and `failOn`; for scoped or base policies, the Action's exit can differ from that scanner field. Setup, validation and base-comparison failures can occur before outputs are written. Use `if: always()` on a following upload step if you need reports from failed scans. Full report files remain on the runner; this Action does not publish them externally. Large job summaries are truncated with an explicit notice, while the report files retain the full output.

Confirmed P0 findings in changed files emit `::error` annotations; P0 candidates emit `::warning`. The Action emits at most 10 of each type per step, prioritizes confirmed errors and then ordinary candidates before justified-review warnings, and states how many were omitted. Workflow-command properties and messages escape `%`, carriage returns, newlines, colons and commas, so repository text cannot start a second command. Paths are workspace-relative. When `compare-base` is enabled, only new findings are annotated. No API or additional permission is used.

Base comparison copies regular Git blobs into a temporary directory outside the checkout. It does not run hooks, filters, submodules or repository code. It skips symlinks, submodules and secret-style names; the snapshot is capped at 512 MiB. The matching key is pattern ID, severity, disposition and the whitespace-normalized source range (or finding line when no range exists), with multiset counts. This tolerates line shifts, renames and moves while still counting extra identical occurrences as new. Two distinct findings with the same normalized snippet may be matched as the same occurrence; this is a static comparison, not semantic proof. The summary reports the extra base-comparison wall time and says “new in this PR” only after both complete scans. This option requires the same target path at base; a target renamed as a whole fails closed.

The coverage line reports scanner inventory files, file paths with unresolved diagnostics, unresolved locations, and out-of-scope files. The scanner does not expose a per-file completed count: diagnostic paths can be outside the inventoried test set, so subtracting those counts would be misleading. `Execution complete: false` remains visible even when `allow-incomplete: 'true'` permits exit 0.

## Execution boundary

The Action invokes `npx --yes --ignore-scripts --package=@voidmatcha/e2e-skills-scanner@3.7.0` from a fresh directory outside the checkout. This candidate pins the 3.7.0 release package. Publish that package before making this Action version available; the Action does not build or run scanner sources from the checkout.

The scanner receives a clean environment, empty user/global npm configuration and a fresh npm cache. Package retrieval uses `https://registry.npmjs.org`; the Action does not contact model services or call GitHub APIs. npm lifecycle scripts are disabled. The checkout's `.npmrc`, local binaries, ESLint configuration and test configuration are not executed. Configuration files may be read statically. The Action never passes the scanner's `--project-eslint` or `--trust-project` execution flags. This is not an OS network sandbox; ordinary runner and npm trust still apply.

A green job means the configured static policy did not fail on the code it could analyse. With the default `allow-incomplete: 'true'`, it can be green even when some code remains unchecked. It does not mean every test was analysed, every candidate was dismissed, or tests will detect a real fault. Use the [reviewer](../skills/e2e-reviewer/SKILL.md) for contextual review. Its [experimental runtime proof](../skills/e2e-reviewer/references/runtime-probes.md) requires an explicit request and execution approval.

## Local verification

`node --test scripts/ci/test-github-action.mjs` validates the composite metadata schema and runs offline smoke cases for confirmed P0, candidates, incomplete analysis, invalid output, unsafe input and report rendering. The metadata is written as JSON, a YAML subset, so this check needs no YAML dependency. The full local CI runs this check too. A hosted GitHub execution is a separate release check; local tests do not claim that a `v3` tag already exists or that GitHub has run the Action.
