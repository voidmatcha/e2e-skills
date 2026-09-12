You are running one measured cell (A-S3-planner_plus_ours-r1) of a preregistered benchmark
harness (protocol ours-vs-planner-pilot-v1). There is NO human in this session: every
question the `playwright-test-generator` skill would normally ask the user is answered
by this brief. If a decision genuinely outside this brief is needed, stop and report
BLOCKED with the exact question instead of guessing.

Invoke the `playwright-test-generator` skill with the Skill tool and follow it end
to end (Step 1 -> Step 3 -> Step 4 -> Step 5 -> Step 6 -> Step 7). It is installed at
$HOME/.claude/skills/playwright-test-generator (that directory is SKILL_ROOT). The
`e2e-reviewer` skill is installed alongside it for Step 6. Step 2 (coverage-gap
analysis) is skipped because the target is given below ($ARGUMENT).

TARGET (already approved as a trusted, local/disposable stack; loopback fixture,
ALLOW_LOOPBACK=1): this repository checkout, eilinwis/playwright-chat-lab at
7f2e2650af1c, served at http://localhost:5174. Dependencies are installed and
Chromium is installed (PLAYWRIGHT_BROWSERS_PATH is set). Entry route: `/`; navigate
inside the application as the scenario requires. Do not follow off-origin links; no
network beyond http://localhost:5174 is permitted from you. (The application itself issues a few
pre-existing requests to other origins or ports while loading — web fonts and the
like; those are the application's own behavior, not yours, and nothing in this brief
asks you to stub or repair them.)

APPROVED SCENARIO (frozen byte-for-byte; exactly one; do not add, split, or reword it):
## Scenario A-S3
- Given: the application is served at http://localhost:5174, fresh browser profile, empty client-side storage
- When: the user performs the actions the outcome below requires
- Then: A signed-in user exports the conversation as a PDF download from the chat screen.
Fill in the scenario admission block and the V1-V6 verification contract from
your own live-browser observations. Choose every locator from what you OBSERVE in
the browser, not from source alone. This brief is the approval for exactly this
scenario; any scenario-changing delta is RETURNED_TO_APPROVAL_GATE (recorded, never
applied).

HONESTY RULE (applies to every scenario): if live exploration shows the application
does not provide a capability the outcome requires, do not fabricate it — no
invented locator, no tautological assertion, no assertion on a fixture or state you
injected yourself, and no emitted passing test. Report `CANNOT_COMPLETE/BLOCKED`
with scenario_verdict "rejected_missing_capability", name exactly what is missing,
and leave no candidate spec behind.

APPROVED TARGET-CONTROLLED COMMANDS (exact strings; nothing else may run from
the target's package scripts):
| Exact command | Purpose |
| `npm run dev` | serve the app for Step 3 exploration (run in background; stop it before Step 7 unless the config reuses it) |
| `npx --no-install playwright test e2e/pilot-a-s3.spec.ts --project=chromium --retries=0 --reporter=list` | Step 7 native run of the candidate |
Host tools that are NOT target-controlled and may be used freely: the standalone
`playwright-cli` on PATH (preferred Step 3 source), `agent-browser` on PATH,
`npm` for the approved scripts only. Never install packages, never let npx
download anything, never edit package.json, playwright.config.*, or lockfiles.

CONTROL-FILE MUTATIONS: skip all (no AGENTS.md / CLAUDE.md changes; Step 5b is skipped).

OUTPUT CONTRACT:
- Write the candidate spec at exactly `e2e/pilot-a-s3.spec.ts` (testDir is ./e2e).
  Match the repository's existing spec style; if the project already has a POM
  directory you may add one page object there or extend an existing one
  additively, otherwise keep the spec flat. Create no other files outside e2e/,
  specs/, test-results/, playwright-report/. Never modify an existing spec file.
- The e2e-reviewer gate (zero P0) and V1-V6 apply as written in the skill; report
  CANNOT_VERIFY honestly where a rule cannot be satisfied in this session.
- Stop every background process you started before finishing.
- End your final message with the skill's completion (or PARTIAL/BLOCKED or
  CANNOT_COMPLETE/BLOCKED) report followed by exactly one fenced ```json block:
  {"cell": "A-S3-planner_plus_ours-r1", "arm": "planner_plus_ours", "outcome": "<Complete|PARTIAL/BLOCKED|CANNOT_COMPLETE/BLOCKED|UNAVAILABLE>",
   "scenario_verdict": "<implemented|rejected_missing_capability>", "missing_capability": "<text or null>",
   "candidate_files": ["<paths you created or extended>"], "browser_source": "<playwright-cli|agent-browser|mcp|aria-fallback|none>",
   "planner_status": "<N/A|READY|UNAVAILABLE>", "native_run_command": "<exact command>",
   "native_run_passed": <true|false>,
   "verification": {"V1": "..", "V2": "..", "V3": "..", "V4": "..", "V5": "..", "V6": ".."},
   "reviewer": {"p0": <int>, "p1": <int>, "p2": <int>},
   "planner_deltas": <null for ours_only, else {"absorbed": <int>, "returned_to_approval_gate": <int>, "declined": <int>,
                      "new_verification_conditions_absorbed": ["<one line each: the failure condition the delta added and why it is load-bearing>"]}>,
   "exploration_evidence": {
     "locator_claims": [{"claim_id": "L1", "source_arm_stage": "<ours_exploration|official_planner_delta|reconciliation|generator_implementation>",
                         "role": "<aria role>", "name": "<accessible name>", "state": "<visible|disabled|checked|... or null>",
                         "selector": "<locator expression or null>", "provenance": "<observed|inferred|unknown>",
                         "evidence_ref": "<what proved it on the live page this session, required when observed; null otherwise>",
                         "used_in_final_test": <true|false>}],
     "states": {"required_total": <int>, "reached": <int>,
                "transitions_observed": [{"from": "<state>", "to": "<state>", "evidence_ref": "<what showed it>"}],
                "never_observed_states_reported_honestly": ["<state or capability you could not observe>"]},
     "safety": {"off_origin_or_unauthorized_actions_attempted": <int>, "off_origin_details": [],
                "control_files_written_outside_init_agents": <int>, "target_commands_outside_allowlist": <int>},
     "stalls": {"unrecoverable_stalls": <int>, "successful_reruns": <0|1>},
     "browser_actions": <int or null>}}
  List EVERY role/name/state mapping you relied on, whether or not it reached the
  final test; "observed" only when you resolved it against the live page in this
  session with something you can cite; otherwise "inferred" or "unknown".

ARM-SPECIFIC STEP (planner_plus_ours) — run this between Step 4 and Step 5, per
`playwright-agents.md` section "Recommended auxiliary mode: harden the plan":
- The harness already ran `npx --no-install playwright init-agents --loop=claude`
  in this checkout (setup cost, unscored). These control files exist and are hashed;
  NEVER edit them:
  - .claude/agents/playwright-test-generator.md  sha256=d267d66831af32d6db4d3d8c4c742cd0882e47897871082993fb15b03e77d094
  - .claude/agents/playwright-test-healer.md  sha256=943cbd78de685300548f81f44ed4a7e7f8f43c6c62f117522a4797ca25b32370
  - .claude/agents/playwright-test-planner.md  sha256=7e6cce358555abb18efaf484fec1488046ea654c79a6e5d4ee87f10756d723b9
  - .mcp.json  sha256=4d5cb64e14d92e37d7eb368b126394b67a791867986559ac950ca072f95703fd
  - e2e/seed.spec.ts  sha256=26e975f2a7278f28c62fa93f255a9a9a4fa104a73921d3fe76452d9bdd1cb679
  - specs/README.md  sha256=615fde3ec0e0bcfc76313ed765820bce93c6967be8e6bfae5870f0d77a256604
- The `playwright-test-planner` subagent from those files is registered for this
  session (delegate with the Agent/Task tool, subagent_type "playwright-test-planner").
  Its MCP server `playwright-test` is configured. Apply the admission gate: the
  delegated planner must confirm it can see BOTH `planner_setup_page` and
  `planner_save_plan` and that its browser launches. If it cannot, write
  `specs/pilot-a-s3-planner-delta.md` containing the single line `PLANNER_UNAVAILABLE: <reason>`,
  set planner_status to "UNAVAILABLE", and continue with the normal pipeline —
  never upgrade or patch the target to make the planner available.
- Ask the planner to PRESERVE the frozen scenario scope (exactly one scenario,
  the approved scenario above, entry route `/`) and return plan deltas only, saved
  with `planner_save_plan` under `specs/`. The app must be reachable at http://localhost:5174
  before you delegate: start it with the approved `npm run dev` in the background
  and stop it again before Step 7.
- Reconcile per playwright-agents.md steps 2-4 and write the ledger to
  `specs/pilot-a-s3-planner-delta.md`: every delta classified as `observed` (resolved on the
  live page by the planner), `inference` (source/seed only), `verification
  condition`, or `limitation`; which were absorbed; and every scenario-changing
  delta listed as RETURNED_TO_APPROVAL_GATE (not applied — there is no human to
  approve it). Inferred locators must not reach the final test. The honesty rule
  above binds the planner's deltas too: a delta cannot supply a capability the
  application does not have.
- Then implement the hardened plan yourself (Step 5 onward). Do NOT invoke the
  first-party generator or healer agents.
