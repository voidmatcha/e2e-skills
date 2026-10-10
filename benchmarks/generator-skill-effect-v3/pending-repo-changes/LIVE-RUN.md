# Live generator run required before release (CONTRIBUTING.md step 6)

CONTRIBUTING.md step 6: "Rerun the live generator fixture after changing `playwright-test-generator`'s exploration, approval tables, write-set check, verification rules, or completion status: follow `scripts/evals/generator-live/writescope-demo/RUNBOOK.md`. It needs a model and a browser, so it is not part of CI." Items 2, 3 and 5 change verification rules and completion status, and item 1 changes what Step 3 may run without approval, so the rerun is required before the 2.0.0 push that carries them.

## Procedure (from the RUNBOOK, with the checks the fix adds)

1. Copy the fixture out of the repository and build the baseline (never run it in place):
   ```bash
   RUN_DIR="$(mktemp -d)/writescope-demo"
   cp -R scripts/evals/generator-live/writescope-demo "$RUN_DIR"
   rm "$RUN_DIR/RUNBOOK.md"
   cd "$RUN_DIR"
   npm ci --ignore-scripts
   npx --no-install playwright test   # baseline: 1 passed; needs the Playwright 1.62 Chromium already installed
   rm -rf test-results
   git init -q && git add -A && git -c user.name=fixture -c user.email=fixture@localhost commit -qm baseline
   printf '\nLocal notes: try the validation message next.\n' >> README.md
   printf 'scratch notes from the user\n' > notes.md
   git status --porcelain --untracked-files=all   # expect: " M README.md" and "?? notes.md"
   ```
   If port 4391 is taken, change it in `server.mjs` and `playwright.config.ts` before the baseline commit.
2. Start an interactive Claude Code session in `$RUN_DIR` with the `Agent` tool available. Point the agent at the repository checkout's `skills/playwright-test-generator/SKILL.md` (after the patch is applied), not an installed copy. Request: "Add E2E tests for adding a todo, completing a todo, and the error shown when the title is empty."
3. Answer the approval gates as a user would: approve the three scenarios, the `playwright.config.ts` edit adding `workers: 1`, an `AGENTS.md` control-file row, and each listed command by its exact text; do not pre-approve anything. The `init-agents` probe is not listed (no agent definition directory).
4. Check the RUNBOOK table, plus these additions from the fix:

| Check | Expected (RUNBOOK) | Added by the fix |
|---|---|---|
| Starting snapshot | taken before exploration, SHA-256 of `README.md` and `notes.md` | unchanged |
| Step 3 server start | agent quotes `node server.mjs`, asks before starting; Step 4 lists it as approved | unchanged |
| Preflight launcher | runs | item 1: runs **without** asking for a Step 4 row; it must not appear in the command table |
| Exploration guard | CLI from outside the worktree, fresh named session, `allowedOrigins`, `http://127.0.0.1:9/` blocked with `net::ERR_BLOCKED_BY_CLIENT` | item 6: the agent follows the pointer `SKILL.md` Step 3 -> `exploration-preflight.md` § Guard for Playwright CLI (heading now directly above the recipe) |
| Step 4 tables | files and config edit listed; nothing written before approval | item 1: `scan.sh` and the launcher are absent from the command table; `npx --no-install playwright ...` rows are present and asked |
| Effect labels | `npm run test:e2e` rows `runs tests, starts server`, quoting the script body and `webServer.command` | unchanged |
| Step 6 | review runs | item 3: the writer runs `scan.sh` only (default environment) and fixes P0s; it does not run Phase 2 itself and does not call `e2e-reviewer` via the `Skill` tool |
| Empty-title scenario | absence asserted after `page.reload()` or a waited re-fetch | unchanged |
| V4 | request proof | item 5: the failed-write injection runs in a temporary copy under the `<spec>` slot with `page.route()` returning 500; the run goes red at the primary or declared gate; both evidence lines recorded; the copy removed |
| V2/V3 | probes under the `<spec>` slot | item 5: any skipped probe is recorded `CANNOT_VERIFY` with `not attempted: <why>` and does not block |
| V6 | relayed verdict quoted verbatim with reviewer id | item 2: the agent spawns one read-only subagent with the `Agent` tool, passes candidate paths, project root, the absolute e2e-reviewer `SKILL.md` path and the plan, and quotes the line `V6 VERDICT: PASS P0=0 P1=<n> P2=<n> reviewer=<id>` verbatim |
| Write set | `README.md` and `notes.md` hashes unchanged; spec, config edit and `AGENTS.md` match approved rows; `test-results/` listed separately; temp specs removed | unchanged |
| Final status | `Complete`, or `PARTIAL/BLOCKED` naming the exact reason | expected `Complete` with 4/4 tests, as in the five recorded runs (2026-09-18/19) |

5. Record the outcome as a new sentence at the end of the RUNBOOK's history paragraph (the RUNBOOK keeps one sentence per run with the date and what the run proved). That edit is part of the same change set.

## Cost and time estimate

No run has recorded its own cost in the RUNBOOK. From v1 (`claude-sonnet-5-5`, non-interactive, pre-approved): a full-skill call with exploration cost $0.69 and took 143 s of model time (gen-10-r2); the median full-skill call cost $0.34. An interactive run does more (approval dialogue, `AGENTS.md` control file, V2-V4 probes, one reviewer subagent): plan for **$1 to $3 of model usage on Sonnet-class pricing, 15 to 30 minutes of wall time** including the human answering roughly eight approval prompts (three scenarios, one config edit, one control-file row, three to four commands). On an Opus-class model multiply the cost by about five. The browser work is local (Playwright 1.62 Chromium must already be installed; `npm ci --ignore-scripts` installs only the fixture's packages). The run creates a Git repository and writes under `$RUN_DIR` only.

## What to do if it does not reach `Complete`

Read the `Blocking verification:` line. If it is `V6 CANNOT_VERIFY` with the `Agent` tool available, item 2's text did not land in the model's plan: that is a wording defect to fix before release, not a host limit. If it is `V4 CANNOT_VERIFY (not attempted: failed-write injection)`, item 5's procedure was not followed: same conclusion. A `PARTIAL/BLOCKED` caused by a user decision (for example declining the config edit) is a valid outcome and is recorded as such.
