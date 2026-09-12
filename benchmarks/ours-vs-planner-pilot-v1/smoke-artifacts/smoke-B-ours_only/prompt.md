You are running one unscored SMOKE cell (smoke-B-ours_only) of a preregistered
benchmark harness. There is NO human in this session: every question the
`playwright-test-generator` skill would normally ask the user is answered by this
brief. If a decision genuinely outside this brief is needed, stop and report
BLOCKED with the exact question instead of guessing.

Invoke the `playwright-test-generator` skill with the Skill tool and follow it end
to end (Step 1 -> Step 3 -> Step 4 -> Step 5 -> Step 6 -> Step 7). It is installed at
$HOME/.claude/skills/playwright-test-generator (that directory is SKILL_ROOT). The
`e2e-reviewer` skill is installed alongside it for Step 6. Step 2 (coverage-gap
analysis) is skipped because the target is given below ($ARGUMENT).

TARGET (already approved as a trusted, local/disposable stack; loopback fixture,
ALLOW_LOOPBACK=1): this repository checkout, andymai/gridfinity-layout-tool at
8902951e70f0, served at http://localhost:5174. Dependencies are installed and
Chromium is installed (PLAYWRIGHT_BROWSERS_PATH is set). Route under test: `/`.
Do not follow off-origin links; no network beyond http://localhost:5174 is permitted.

APPROVED SCENARIO (frozen; exactly one; do not add, split, or reword it):
## Scenario 1: Application shell loads with primary navigation
- Given: the application is served at http://localhost:5174
- When: a user opens `/`
- Then: the application shell loads and the primary navigation is visible
Fill in the scenario admission block and the V1-V6 verification contract from
your own live-browser observations (V4: N/A, read-only). Choose the primary
navigation locator from what you OBSERVE in the browser, not from source alone.

APPROVED TARGET-CONTROLLED COMMANDS (exact strings; nothing else may run from
the target's package scripts):
| Exact command | Purpose |
| `pnpm run dev` | serve the app for Step 3 exploration (run in background; stop it before Step 7 unless the config reuses it) |
| `pnpm exec playwright test e2e/smoke-shell.spec.ts --project=chromium --retries=0 --reporter=list` | Step 7 native run of the candidate |
Host tools that are NOT target-controlled and may be used freely: the standalone
`playwright-cli` on PATH (preferred Step 3 source), `agent-browser` on PATH,
`pnpm` for the approved scripts only. Never install packages, never let npx
download anything, never edit package.json, playwright.config.*, or lockfiles.

CONTROL-FILE MUTATIONS: skip all (no AGENTS.md / CLAUDE.md changes; Step 5b is skipped).

OUTPUT CONTRACT:
- Write the candidate spec at exactly `e2e/smoke-shell.spec.ts` (testDir is ./e2e).
  Match the repository's existing spec style; if the project already has a POM
  directory you may add one page object there, otherwise keep the spec flat.
  Create no other files outside e2e/, specs/, test-results/, playwright-report/.
- The e2e-reviewer gate (zero P0) and V1-V6 apply as written in the skill; report
  CANNOT_VERIFY honestly where a rule cannot be satisfied in this session.
- Stop every background process you started before finishing.
- End your final message with the skill's completion (or PARTIAL/BLOCKED) report
  followed by exactly one fenced ```json block:
  {"cell": "smoke-B-ours_only", "arm": "ours_only", "outcome": "<Complete|PARTIAL/BLOCKED|CANNOT_COMPLETE/BLOCKED|UNAVAILABLE>",
   "candidate_files": ["<paths you created>"], "browser_source": "<playwright-cli|agent-browser|mcp|aria-fallback|none>",
   "planner_status": "<N/A|READY|UNAVAILABLE>", "native_run_command": "<exact command>",
   "native_run_passed": <true|false>, "verification": {"V1": "..", "V2": "..", "V3": "..", "V4": "..", "V5": "..", "V6": ".."}}
