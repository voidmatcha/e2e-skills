You are running one unscored SMOKE cell (smoke-B-planner_plus_ours) of a preregistered
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
  {"cell": "smoke-B-planner_plus_ours", "arm": "planner_plus_ours", "outcome": "<Complete|PARTIAL/BLOCKED|CANNOT_COMPLETE/BLOCKED|UNAVAILABLE>",
   "candidate_files": ["<paths you created>"], "browser_source": "<playwright-cli|agent-browser|mcp|aria-fallback|none>",
   "planner_status": "<N/A|READY|UNAVAILABLE>", "native_run_command": "<exact command>",
   "native_run_passed": <true|false>, "verification": {"V1": "..", "V2": "..", "V3": "..", "V4": "..", "V5": "..", "V6": ".."}}

ARM-SPECIFIC STEP (planner_plus_ours) — run this between Step 4 and Step 5, per
`playwright-agents.md` section "Recommended auxiliary mode: harden the plan":
- The harness already ran `pnpm exec playwright init-agents --loop=claude`
  in this checkout (setup cost, unscored). These control files exist and are hashed;
  NEVER edit them:
  - .claude/agents/playwright-test-generator.md  sha256=d267d66831af32d6db4d3d8c4c742cd0882e47897871082993fb15b03e77d094
  - .claude/agents/playwright-test-healer.md  sha256=7ace70bce4716641633a46a6c5f41773277812a046cba517be616e677e7ccdf8
  - .claude/agents/playwright-test-planner.md  sha256=4566f7ea58d11ceb8e65b7992c658d959cb610df4b9949e370cfbfb1f3ea310b
  - .mcp.json  sha256=4d5cb64e14d92e37d7eb368b126394b67a791867986559ac950ca072f95703fd
  - e2e/seed.spec.ts  sha256=26e975f2a7278f28c62fa93f255a9a9a4fa104a73921d3fe76452d9bdd1cb679
  - specs/README.md  sha256=615fde3ec0e0bcfc76313ed765820bce93c6967be8e6bfae5870f0d77a256604
- The `playwright-test-planner` subagent from those files is registered for this
  session (delegate with the Agent/Task tool, subagent_type "playwright-test-planner").
  Its MCP server `playwright-test` is configured. Apply the admission gate: the
  delegated planner must confirm it can see BOTH `planner_setup_page` and
  `planner_save_plan` and that its browser launches. If it cannot, write
  `specs/smoke-planner-delta.md` containing the single line `PLANNER_UNAVAILABLE: <reason>`,
  set planner_status to "UNAVAILABLE", and continue with the normal pipeline —
  never upgrade or patch the target to make the planner available.
- Ask the planner to PRESERVE the frozen scenario scope (exactly one scenario,
  the smoke scenario below, route `/`) and return plan deltas only, saved with
  `planner_save_plan` under `specs/`. The app must be reachable at http://localhost:5174
  before you delegate: start it with the approved `pnpm run dev` in the background
  and stop it again before Step 7.
- Reconcile per playwright-agents.md steps 2-4 and write the ledger to
  `specs/smoke-planner-delta.md`: every delta classified as `observed` (resolved on the
  live page by the planner), `inference` (source/seed only), `verification
  condition`, or `limitation`; which were absorbed; and every scenario-changing
  delta listed as RETURNED_TO_APPROVAL_GATE (not applied — there is no human to
  approve it). Inferred locators must not reach the final test.
- Then implement the hardened plan yourself (Step 5 onward). Do NOT invoke the
  first-party generator or healer agents.
