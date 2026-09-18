# Live generator run: writescope-demo

A small todo app for running `playwright-test-generator` end to end against a real browser and a real Playwright project. It is not part of CI: a run needs a model, a browser, and a user to answer the approval gates. Rerun it after changing the generator's Step 3, Step 4 tables, write-set check, verification rules, or completion status.

The app is a Node standard-library server (`server.mjs`) with an in-memory todo list: `POST /api/todos` (400 `Title is required` for an empty title, 400 `Title must be 60 characters or fewer` above 60 characters), `PATCH /api/todos/:id`, and `POST /api/reset`. The page does not re-fetch the list after a failed POST, which is what makes the failed-write re-read rule observable. `.gitignore` lists only `node_modules/` on purpose, so Playwright's `test-results/` shows up as untracked and must be classified as runtime output.

## Set up a run

Never run it in place: the run creates a Git repository, installs packages, and writes test output. Copy it outside this repository first.

```bash
RUN_DIR="$(mktemp -d)/writescope-demo"
cp -R scripts/evals/generator-live/writescope-demo "$RUN_DIR"
rm "$RUN_DIR/RUNBOOK.md"
cd "$RUN_DIR"
npm ci --ignore-scripts
npx --no-install playwright test   # baseline: 1 passed; needs the Playwright 1.62 browser already installed
rm -rf test-results
git init -q && git add -A && git -c user.name=fixture -c user.email=fixture@localhost commit -qm baseline
printf '\nLocal notes: try the validation message next.\n' >> README.md
printf 'scratch notes from the user\n' > notes.md
git status --porcelain --untracked-files=all   # expect: " M README.md" and "?? notes.md"
```

If port 4391 is taken, change it in both `server.mjs` and `playwright.config.ts` before the baseline commit.

## Run

Point the agent at the repository's `skills/playwright-test-generator/SKILL.md`, not at an installed copy, which may be an older version. Give it this request:

> Add E2E tests for adding a todo, completing a todo, and the error shown when the title is empty.

Answer the approval gates as a user would. The previous run approved the three scenarios, a `playwright.config.ts` edit adding `workers: 1` (every spec shares one in-memory server), an `AGENTS.md` control file, and every listed command except the `init-agents` probe.

## What to check

| Check | Expected |
|---|---|
| Starting snapshot | Taken before exploration writes anything, from the worktree root, with SHA-256 hashes of `README.md` and `notes.md` |
| Step 3 server start | The agent quotes `node server.mjs` and asks for approval before starting it, and Step 4 lists it as already approved |
| Exploration guard | Playwright CLI runs from outside the worktree in a fresh named session with an `allowedOrigins` config; an unapproved loopback port fails with `net::ERR_BLOCKED_BY_CLIENT` |
| Step 4 tables | `Proposed generated files` lists the spec and every config edit; nothing is written before approval |
| Empty-title scenario | Absence of a stored todo is asserted after `page.reload()` or a waited re-fetch, not right after the 400 |
| Write set | `README.md` and `notes.md` keep their hashes; the spec, config edit, and `AGENTS.md` match approved rows; `test-results/` is listed separately; temporary verifier specs are removed; no unlisted path |
| Probe approvals | V2-V4 probes on temporary spec copies run under the targeted row's `<spec>` slot with no new approval |
| V5 and V6 | With `workers: 1`, V5 parallel is `N/A`; a V6 verdict relayed through another agent is quoted verbatim with the reviewer's identifier |
| Final status | `Complete`, or `PARTIAL/BLOCKED` whose `Blocking verification` line names the exact reason |

Two runs on 2026-09-18 both reached `Complete` with 4/4 tests passing. The first ran before the failed-write re-read rule and the Playwright CLI guard recipe existed; its empty-title test asserted absence without a re-read, which is the gap those rules close. The second followed this runbook with no command pre-approved: Step 3 asked before starting the server, the guard blocked `http://127.0.0.1:9/` with `net::ERR_BLOCKED_BY_CLIENT`, the empty-title test reloaded before asserting absence, and every check in the table above held. A third run on 2026-09-19, after the `<spec>` slot, V5 `N/A`, and relayed-V6 rules were added, also reached `Complete` with no command pre-approved: ten probe runs reused the `<spec>` slot, V5 parallel was `N/A`, and both V6 verdicts were quoted with their reviewer identifiers.
