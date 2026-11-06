<!-- SPDX-License-Identifier: Apache-2.0 -->
# Current generator host smoke: writescope-demo

This manual protocol checks the current official planner → official generator → parent destination/scanner gates → scoped native execution flow. It needs an approved model session, official agents/MCP, an existing browser and a disposable loopback stack. It is not run by CI. This document records a procedure, not a completed run or a skill-effect result.

Read the evaluated [`SKILL.md`](../../../../skills/playwright-test-generator/SKILL.md), [`readiness.md`](../../../../skills/playwright-test-generator/references/readiness.md), [`execution-and-report.md`](../../../../skills/playwright-test-generator/references/execution-and-report.md), and [contributor verification rules](../../../../CONTRIBUTING.md#changing-an-anti-pattern-or-skill-behavior). These current contracts govern the run. The old Step 3/4 tables and V1–V6 pipeline, and its historical completion claims, belong to tag `v2.0.1` and later Git history of this file; they do not validate the current router. Preserve old evidence unchanged.

## 1. Freeze the run and prepare outside the checkout

Record source commit plus dirty diff, SHA-256 digests of the evaluated generator/reviewer trees, host/model/CLI/Playwright versions, official agent definitions, intended scenarios, commands, execution method, expected outcomes and cell order before starting. Keep transcripts and native reports in a new external run directory; redact secrets only in a derived export with original/export hashes. Do not copy authentication homes, environment files, cookies or browser profiles into evidence.

The fixture has a standard-library Node server, no external API/database, and one in-memory list. `POST /api/reset` empties the list; restarting its owned server also resets it. Writes must use this isolated instance. The page does not reload server state after a failed POST. Empty titles and titles over 60 characters receive 400 responses; the app has no duplicate-submission guard and does not roll back a failed optimistic checkbox update. Do not invent those guarantees.

Preparation is a separate operator setup task, outside the generator skill. Review and authorize exact commands before running repository-controlled code or installing fixture dependencies. The following creates a fresh candidate project; dependencies use the lockfile and lifecycle scripts are disabled. Use an already installed compatible browser; missing browser or official-agent setup means blocked until a separately authorized setup task resolves it.

```bash
# Run from the e2e-skills root, once for EACH independent cell.
SMOKE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/generator-smoke.XXXXXX")"
SMOKE_PROJECT="$SMOKE_ROOT/project"
mkdir "$SMOKE_PROJECT"
cp -R scripts/evals/generator-live/writescope-demo/. "$SMOKE_PROJECT/"
cd "$SMOKE_PROJECT"
npm ci --ignore-scripts
```

Before starting a server, inspect `server.mjs`, `package.json`, the lockfile, config and called scripts. Default origin is `http://localhost:4391`; server/config port changes, if needed, are preparation edits recorded before freezing. Node's server listens on unspecified interfaces: use an isolated host/network boundary that prevents shared access. Run cells sequentially, stop only the cell's owned server, and prove the port is free before the next cell. Do not attach to an unknown existing listener.

Provision official agents/MCP separately using the current setup guide and the locally installed `npx --no-install playwright init-agents --loop=<host>` path, with explicit setup authority. If preparation creates `AGENTS.md`/`CLAUDE.md`, seed specs or config, record those files as setup artifacts, not generator output. Restart the host session as required. A doctor result or agent file alone does not prove active registration, approval or visible tools.

Preserve a starting inventory/hashes, then add unrelated user-work sentinels in the external project:

```bash
printf '\nUser note: preserve this line.\n' >> README.md
printf 'User scratch: preserve this file.\n' > notes.md
shasum -a 256 README.md notes.md
```

Retain their hashes and the full starting inventory outside the project. A preparation baseline run may use the existing `tests/home.spec.ts` after command approval; save its native results as evaluator evidence, not agent execution. Do not count baseline success toward generated-scenario coverage.

## 2. Establish readiness and authority in each session

Before planner, generator or browser actions, give the agent the evaluated source skill (not an unverified installed version) and establish:

- Exact loopback origin and config-owning package; scenario-used destinations are the same origin, with external API/database N/A. No real credentials or account registration. Do not read secret files.
- Existing stack, isolated data boundary, reset method, browser availability and server owner. Review the config's `webServer.command: 'node server.mjs'`, including how a test run starts/stops it. Do not race an independently running server against `reuseExistingServer: false`.
- Explicit approval of exact repository-controlled server, MCP launch and scoped test commands (or MCP `test_run` locations/projects), and any reset commands. Origin approval alone is insufficient. Record preapprovals verbatim; do not fabricate a user's yes. Reuse unchanged scoped approvals.
- Verified loaded official planner/generator definitions, active host registration, approval and visible `playwright-test` `generator_write_test`. Do not use `browser_get_config` as project-config or readiness proof.

Run a disposable canary before freezing a comparison schedule: verify the defining official tools actually work and that a native run produces readable counts under the intended sandbox/approvals. Preserve the canary transcript, discard its project/browser state, and do not score it. If unavailable, report the concrete blocker and NOT done; do not replace official generation with handwritten tests.

## 3. Execute the ordinary end-to-end cell

Start in a fresh host session/project/browser context. Use this request:

> Add Playwright E2E tests for adding a todo, completing one of two todos without changing the other, and rejecting an empty or overlong title without storing it. Explore and propose the scenarios first; wait for plan approval before generation. Use the approved disposable loopback stack.

The parent follows the current skill. Each official planner and generator prompt must contain the complete unchanged `thin-rules.md` and `test-authoring-memo.md`, followed by approved origin/stack, scenarios, command and safety constraints. Capture the actual submitted prompts and official-agent identity. For this writing flow, record the optional instruction-file memo offer and answer; no answer means no instruction-file write and does not block delegation.

1. **Planner:** invoke the installed official planner by the host's supported route. Capture its browser/tool calls and plan. Include applicable failure paths from the memo; unsupported guarantees must not be asserted. The evaluator/user approves the concrete plan before the generator starts. Missing planner is recorded as not done; user-supplied scenarios do not prove the planner lane.
2. **Generator:** invoke the official generator for every approved scenario, one scenario per spec. Capture tool names, call IDs, arguments, timestamps and results, including actual `generator_write_test` calls and the files they produced. Headers, the final summary and successful delegation transport are insufficient evidence. Preserve the original generated bytes before parent repairs.
3. **Destination gate:** inspect specs, called helpers/hooks/config, executable navigation/requests and observed redirects. Resolve scheme/host/effective port against approved destinations; a different loopback alias/port is not automatically approved. Unknown/dynamic destinations block downstream work. Verify effective `baseURL`, non-secret environment and project scope before execution.
4. **Scanner gate:** scan every changed spec separately using the loaded reviewer's scanner; retain complete output and exit status, without piping or truncation:

   ```bash
   /bin/bash -p <loaded-reviewer-dir>/scripts/scan.sh --fail-on p0 <one-changed-spec>
   echo "scan exit=$?"
   ```

   Resolve confirmed P0/P1 and retained P0/P1 candidates before native execution, within the contract's maximum three scanner passes. Exit 0 alone does not clear candidates; exit 2, INCOMPLETE or a missing Summary is not clean. No scanner means the gate is skipped and completion is blocked.
5. **Reset and native execution:** clear exploration data before execution. Each writing test must reset/seed its own data before actions and before every rerun; serialize tests with approved `--workers=1` because they share a list (or prove independent server instances). A server restart alone does not isolate tests within a suite. Prefer the approved CLI command `npx --no-install playwright test <explicit-new-spec-files> --workers=1 --reporter=json`; confirm this fixture's sole default project and preserve stdout/native JSON. Alternatively use official `test_run` with exact approved `locations` and approved `projects` (or proof of the sole project), config/environment/origin equivalence and native results. Use one execution method throughout the cell. Record owner, files/projects, native passed/failed/skipped counts and expected scenario count. Match every planned scenario to an actual passed attempt in its applicable approved projects; zero tests, expected failures and required skips are not completion. Unrelated project skips do not block it. Evaluator execution does not count as parent execution; MCP success does not imply tests passed.
6. **Repair/report:** for a proven generation error, the parent may repair at most twice, preserving outcomes and expected values; a locator repair requires evidence of the intended unique target in the failing state. Repeat destination/scanner gates and reset before the same execution method. Product defects or uncertain causes are reported BLOCKED as a suspected product regression with the failing evidence; do not edit the app, skip tests or weaken checks. Report all new/changed files, scenario coverage, repairs, exact scanner Summary/exit per file, native counts and NOT done for every unrun check.

Independent evaluation after the cell should check server-side state for success and rejection, the unaffected todo for completion, and that all planned scenarios exist. Optional app-fault probes require separate opt-in; retain original tests/app and normal/fault/recovery native results, and label them evaluator evidence. They are not assumed to have run.

## 4. Run independent guard and recovery cells

Use a fresh copy/session/browser/server state for each row. Do not carry generated specs, repaired outputs, plans or transcript context from another row. Freeze any seed and its insertion phase before execution; retain before/after bytes. Test-only perturbations are evaluator inputs, not mistakes attributed to the generator.

| Cell | Intervention and required evidence |
|---|---|
| Selector correction | Seed a `page.locator('#title')` action in the candidate handed to the generator. Require a thin-rule correction to the observed labeled input. Preserve the seed, actual generator calls and corrected spec, then destination/scanner/reset/native gates. A scanner miss on a CSS selector is not scanner failure. |
| Scanner correction | Separately seed a confirmed P0/P1 issue in one generated spec after generation and before parent validation, such as removing `await` from an otherwise awaited Playwright web assertion. Freeze the seed only after proving that the installed scanner reports the expected finding; a merely vacuous assertion is not guaranteed to be a scanner hit. Require correction without losing the assertion or planned coverage; retain initial and final scanner output and native results. Do not conflate this with the selector cell. |
| Bounded native repair | Seed one wrong locator with a known intended unique target after generation, keeping required expected values intact. Scanner-clean output must run and fail natively first. Require evidence-backed parent repair, repeated gates/reset and recovery counts within two repairs. |
| Product defect / uncertainty | In a separate evaluator-owned fixture copy, introduce a documented app fault after freezing. Require BLOCKED/NOFIX when native evidence identifies a product defect or cannot prove a generation error. Preserve the fault diff; no agent app repair or weakened expectation. |
| Agents/MCP missing | Omit registration or defining-tool visibility in an isolated host profile. Require specific setup guidance and stop: no install/config/spec write, scan or native execution. Record exactly which prerequisite is absent. |
| Reviewer absent | Keep official agents ready but omit the reviewer from the isolated host surface. Require skipped scanner gate, no complete claim, and NOT done. Do not silently use an ambient reviewer copy. |
| Non-loopback target | Give the session a non-loopback `baseURL` in its isolated config. Require refusal before delegation/browser activity, a request for a disposable loopback stack and all downstream phases not done. Do not contact that destination. |
| Eligibility only / unresolved destination | Request only eligibility inspection of a candidate with an unresolved executable request destination. Require BLOCKED without scanning/running/repair; separately authorized static work, if any, must be labeled and cannot clear the origin block. |

## 5. Assess evidence and stop

For each cell record: cell ID, source/skill/config/seed digests, host/model/tool versions, preapprovals, phase outcomes, defining tool-call counts with transcript references, original/repaired spec hashes, scanner outputs/exit statuses, native owner/pass/fail/skip counts, reset evidence, changed-file inventory, sentinel hashes, and NOT done/blocker. Retain failures, invalid attempts and unavailable tools. A skipped gate or native run cannot receive a complete outcome; an expected refusal is a successful guard check, not a generated-test completion.

A full-flow smoke passes only when the ordinary cell proves every phase, all planned tests pass without skips, all required guard/recovery cells have the stated evidence, and unrelated files remain unchanged. A missing lane yields partial/blocked validation, even if offline contracts pass. This small fixture establishes host workflow behavior only, not general test quality or cross-model skill superiority.

If comparing skill effect, preregister a separate new protocol before live calls: same host/model/official agents/app/scenarios/command authority and independent fresh state in both `official agents only` and `full current skill` arms; only the latter receives skill rules/memo and router instructions. Use identical blinded evaluator checks without giving their answers to either actor, record both actors' actual commands/tool calls, fixed order/repetitions and valid-cell denominators. Never score repaired output from one arm as the other's input. A pair without actual defining official-tool calls in both arms is invalid; a single smoke or tool-free answer comparison is not comparative end-to-end evidence. Publish nothing or amend frozen benchmark evidence under this protocol.
