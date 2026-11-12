# GitHub Action

Run the static Playwright/Cypress scanner on a pull request without a model, a browser, project dependencies or test execution. Confirmed P0 findings fail the default policy. Candidates appear in the job summary for review; they do not fail the job.

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
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - uses: voidmatcha/e2e-skills@v3
        id: scan
        with:
          path: tests/
          fail-on: p0
          allow-incomplete: 'true'
          format: text
```

The composite Action requires Node.js 22+ with npm/npx on a Linux or macOS runner. It does not install Node itself. `contents: read` is sufficient for checkout; the Action makes no GitHub API calls and requests no PR write permission. Candidates go to the job summary, not a bot comment.

## Inputs and outputs

| Input | Default | Meaning |
| --- | --- | --- |
| `path` | `.` | Existing file or directory inside `GITHUB_WORKSPACE`; paths escaping the checkout are rejected. |
| `fail-on` | `p0` | `p0`: fail on confirmed P0 findings. `none`: report findings without failing on them. Candidate-failure and P1/P2 policies are deliberately not exposed. |
| `allow-incomplete` | `true` | Permit unresolved analysis while reporting the unchecked code. Set `false` to fail when analysis is incomplete. Inventory, source-integrity and other scanner execution errors still fail either way. |
| `format` | `text` | `text` or `json` for the saved `report` output. A readable summary and full JSON are always produced. |

Outputs `report` and `json-report` are absolute file paths on the runner, available to later steps for an optional artifact upload. `exit-code` is `0` when the chosen policy is clear, `1` for a confirmed P0 policy failure, or `2` for incomplete analysis or an execution error. Setup failures can occur before outputs are written. Use `if: always()` on a following upload step if you need reports from failed scans. Full report files remain on the runner; this Action does not publish them externally. Large job summaries are truncated with an explicit notice, while the report files retain the full output.

## Execution boundary

The Action invokes `npx --yes --ignore-scripts --package=@voidmatcha/e2e-skills-scanner@3.5.1` from a fresh directory outside the checkout. The Action pins the 3.5.1 release package. Publish that package before making this Action version available; the Action does not build or run scanner sources from the checkout.

The scanner receives a clean environment, empty user/global npm configuration and a fresh npm cache. Package retrieval uses `https://registry.npmjs.org`; the Action does not contact model services or call GitHub APIs. npm lifecycle scripts are disabled. The checkout's `.npmrc`, local binaries, ESLint configuration and test configuration are not executed. Configuration files may be read statically. The Action never passes the scanner's `--project-eslint` or `--trust-project` execution flags. This is not an OS network sandbox; ordinary runner and npm trust still apply.

A green job means the configured static policy did not fail on the code it could analyse. With the default `allow-incomplete: 'true'`, it can be green even when some code remains unchecked. It does not mean every test was analysed, every candidate was dismissed, or tests will detect a real fault. Use the [reviewer](../skills/e2e-reviewer/SKILL.md) for contextual review and explicitly prepared probes.

## Local verification

`node --test scripts/ci/test-github-action.mjs` validates the composite metadata schema and runs offline smoke cases for confirmed P0, candidates, incomplete analysis, invalid output, unsafe input and report rendering. The metadata is written as JSON, a YAML subset, so this check needs no YAML dependency. The full local CI runs this check too. A hosted GitHub execution is a separate release check; local tests do not claim that a `v3` tag already exists or that GitHub has run the Action.
