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
| `fail-on` | `p0` | `p0`: fail on confirmed P0 findings. `p0-candidate`: also fail on P0 candidates, including justified-review findings. `none`: report findings without failing on them. P1/P2 failure policies are not exposed. `p0-candidate` is not recommended as a blocking gate: in a read-only adjudication of 64 P0 candidates from five open-source suites (2026-11-23), 8 were real P0 problems (12.5%; `#3b` 6/8, `#5a` 2/25, `#3` 0/31). If you use it, combine it with `fail-scope: changed`. |
| `fail-scope` | `all` | `all`: apply `fail-on` to the full scan. `changed`: apply it only to findings in files changed between the PR base and head commits. Requires a `pull_request` event and both commits locally; otherwise exit 2. A finding in a changed file may predate the PR. |
| `compare-base` | `false` | On a PR, also scan the base commit's target from a temporary, data-only Git blob snapshot. Apply `fail-on` to new findings in comparable files and all findings in non-comparable files. `fail-scope: changed` restricts both sets to changed files. Partial analysis can still support per-file comparison; see below for exit 2 conditions. |
| `allow-incomplete` | `true` | Permit unresolved analysis while reporting the unchecked code. Set `false` to fail when analysis is incomplete. Inventory, source-integrity and other scanner execution errors still fail either way. |
| `format` | `text` | `text` or `json` for the saved `report` output. A readable summary and full JSON are always produced. The job summary lists at most 50 unique diagnostics and 50 findings, changed-file and P0 findings first; the `report` output keeps the full list. |

Outputs `report` and `json-report` are absolute file paths on the runner, available to later steps for an optional artifact upload. `exit-code` is the Action's selected policy result: `0` clear, `1` selected finding policy failed, or `2` incomplete analysis or an execution error. The scanner JSON retains its own full-scan `execution.exitCode` and `failOn`; for scoped or base policies, the Action's exit can differ from that scanner field. Setup, validation and base-comparison failures can occur before outputs are written. Use `if: always()` on a following upload step if you need reports from failed scans. Full report files remain on the runner; this Action does not publish them externally. Large job summaries are truncated with an explicit notice, while the report files retain the full output.

Confirmed P0 findings in changed files emit `::error` annotations; P0 candidates emit `::warning`. The Action emits at most 10 of each type per step, prioritizes confirmed errors and then ordinary candidates before justified-review warnings, and states how many were omitted. Workflow-command properties and messages escape `%`, carriage returns, newlines, colons and commas, so repository text cannot start a second command. Paths are workspace-relative. When `compare-base` is enabled, annotations include only new findings in comparable files, labeled `[new in this PR]`, and all findings in non-comparable changed files, labeled `[not comparable: incomplete analysis]`. Existing findings in comparable files are not annotated. No API or additional permission is used.

Base comparison copies regular Git blobs into a temporary directory outside the checkout. It does not run hooks, filters, submodules or repository code. It skips symlinks, submodules and secret-style names; the snapshot is capped at 512 MiB. Findings are matched **within each head file and its base counterpart**, using pattern ID, severity, disposition and the whitespace-normalized source range (or finding line when no range exists), with multiset counts. Git rename detection supplies counterparts for renames/moves; line shifts retain matches. Added files have an empty base. Findings in unrelated files cannot cancel one another. Extra identical occurrences are new. Git may not recognize heavily edited renames, and identical snippets within a file may represent distinct findings; this is a static comparison, not semantic proof. The same target path must exist at base; a target renamed as a whole fails closed.

### Partial base comparison

A changed source file is comparable only if both its head path and base counterpart have no unresolved diagnostic, both are regular source files inside the scan target, and neither report has a global trust failure. Added files need only the head source plus a trustworthy base report. Deleted, excluded, outside-target and out-of-scope files are counted as non-comparable. These are comparison eligibility counts, not a claim of full rule coverage.

Inventory, source-integrity, pinned-scope and requested-ESLint failures invalidate every file. Unlocated diagnostics, unknown incomplete reasons and missing/inconsistent diagnostic accounting also block the entire comparison. The wrapper recognizes located analysis reasons and relative import snapshot reasons; it does not dismiss other failures just because a diagnostic has a path.

The scanner JSON does not expose the import graph. When a report has located import snapshot failures, the wrapper additionally scans each otherwise eligible file on that side individually, using the same isolated scanner and policy `none`. The single-file scan must inventory exactly one file and complete its analysis, including transitive imported helpers, without diagnostics or out-of-scope results. This prevents a diagnostic in an imported helper from being ignored merely because its path differs from the test path. A failed dependency check makes that file non-comparable; an execution error still produces exit 2. These extra reports are retained beside `scan.json` as `dependency-check-N.json`. The summary counts them and includes their time in the additional base-comparison wall time.

The summary starts with `New findings: N in K comparable changed files; M changed files not comparable`. Comparable findings absent from their base counterpart receive `[new in this PR]`; existing findings have no new label. Every finding in a non-comparable file receives `[not comparable: incomplete analysis]`, and the summary lists exclusion reasons. Raw head and base scanner reports retain their original `INCOMPLETE` states.

With comparison enabled, failure policy uses **new findings in comparable files plus all findings in non-comparable files**. With `fail-scope: changed`, both sets are restricted to changed files. This conservative fallback means an old P0 in a non-comparable changed file can fail the job; it is never described as introduced by the PR. `p0` fails on confirmed P0, `p0-candidate` also fails on candidates, and `none` reports both sets without a finding-policy failure.

Scanner execution failures (including scanner exit 2), unavailable commits, absent base target and invalid reports remain exit 2. If at least one file changed but **zero changed files are comparable**, a non-`none` policy returns exit 2 even if fallback findings would return 0 or 1: the requested comparison provides no usable changed-file evidence. `fail-on: none` can report that state without failing, unless a scanner/execution error occurred. An empty PR diff has no changed comparison obligation. `allow-incomplete: false` retains the scanner's strict exit 2 behavior.


The coverage line reports scanner inventory files, file paths with unresolved diagnostics, unresolved locations, and out-of-scope files. The scanner does not expose a per-file completed count: diagnostic paths can be outside the inventoried test set, so subtracting those counts would be misleading. `Execution complete: false` remains visible even when `allow-incomplete: 'true'` permits exit 0.

## Execution boundary

The Action invokes `npx --yes --ignore-scripts --package=@voidmatcha/e2e-skills-scanner@3.7.0` from a fresh directory outside the checkout. This candidate pins the 3.7.0 release package. Publish that package before making this Action version available; the Action does not build or run scanner sources from the checkout.

The scanner receives a clean environment, empty user/global npm configuration and a fresh npm cache. Package retrieval uses `https://registry.npmjs.org`; the Action does not contact model services or call GitHub APIs. npm lifecycle scripts are disabled. The checkout's `.npmrc`, local binaries, ESLint configuration and test configuration are not executed. Configuration files may be read statically. The Action never passes the scanner's `--project-eslint` or `--trust-project` execution flags. This is not an OS network sandbox; ordinary runner and npm trust still apply.

A green job means the configured static policy did not fail on the code it could analyse. With the default `allow-incomplete: 'true'`, it can be green even when some code remains unchecked. It does not mean every test was analysed, every candidate was dismissed, or tests will detect a real fault. Use the [reviewer](../skills/e2e-reviewer/SKILL.md) for contextual review. Its [experimental runtime proof](../skills/e2e-reviewer/references/runtime-probes.md) requires an explicit request and execution approval.

## Local verification

`node --test scripts/ci/test-github-action.mjs` validates the composite metadata schema and runs offline smoke cases for confirmed P0, candidates, incomplete analysis, invalid output, unsafe input and report rendering. The metadata is written as JSON, a YAML subset, so this check needs no YAML dependency. The full local CI runs this check too. A hosted GitHub execution is a separate release check; local tests do not claim that a `v3` tag already exists or that GitHub has run the Action.
