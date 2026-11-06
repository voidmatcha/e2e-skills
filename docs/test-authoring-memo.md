# Optional test-authoring memo

A short memo you can add to a project so that coding agents writing Playwright tests also cover failure paths, and do not make a failing test green by changing the app or weakening the test. Adding it to your project is optional. The `playwright-test-generator` skill also passes a byte-identical copy to the official Playwright planner and generator it delegates to; `e2e-debugger` loads only the failure-handling lines (see [Failure handling](#failure-handling)).

## The memo

Copy the text inside the block exactly (SHA-256 `10b500f843c0daa3c0f3383b0891c16c604401c754f0427708bdd89fc9213999` for the block content with a trailing newline; 201 words excluding Markdown markup):

```text
# Test authoring notes

- Make the server reject the action (intercept the request, answer with an error). Assert the interface returns to its previous state and shows no success indicator.
- Where the code guards an action, attempt the forbidden one: submit invalid or empty input; trigger the same action twice. Assert nothing was sent, or only one request, and state did not change.
- A success indicator is not proof. Assert it appears only after the server confirmed, and read server-side state directly.
- If the interface updates before the server answers, hold the response, assert the pending state, then release it.
- If the code lacks a guard, do not assert it; a test must pass on the unchanged app.

Finally, ask of each assertion: if this behavior broke, would this line fail? Strengthen any that would still pass.

When a test fails:
- First decide whether the app or the test is wrong.
- Never change product code to make a test pass unless the user asked for that change.
- Change an assertion only to match a requirement the user named; otherwise do not weaken, skip or delete it.
- If the failure is a regression you did not cause, report it instead of fixing it.
```

## How to use it

Paste the memo unchanged into the project's always-loaded instruction file: `CLAUDE.md` for Claude Code, `AGENTS.md` for Codex. That is its supported place: an instruction file is loaded in every session, whichever skill or prompt is used, while a skill file is loaded only when its skill runs. On some hosts, sub-agents do not inherit the project instruction file; for that reason the generator skill also passes the memo in the prompt of the official agents it delegates to. When the generator skill finds the memo missing from the instruction file, it shows the `guidance` command below and writes nothing there without your yes. Then ask for tests as you normally would. The measured effect applies to the earlier 136-word text, which is everything above the `When a test fails:` section (SHA-256 `c7e5d9a2dc69ee8f5366154f165269d8a33eaacc5fbb13266a3ed009ba3ca2bf`), in the instruction file; edited wording is untested, and the copy in the delegated prompt has not been measured separately. The `When a test fails:` section was added in 3.5; its failure-path detection effect has not been measured as part of this memo, and its effect on healer repairs is described under [Failure handling](#failure-handling).

Instead of pasting, you can run `e2e-skills guidance --host claude --project /path/to/project --memo` (use `--host codex` for `AGENTS.md`, and add `--dry-run` to preview). It inserts the same text unchanged between two HTML comment markers; see [installation](installation.md#optional-memo-and-failure-policy). Writing the file does not show that the memo works for you; still check your own tests as described below.

## What it targets

In our authored-app runs, agent-written E2E tests often stayed green when a failure path broke. The memo targets five such behaviors:

- rollback of the interface after the server rejects an action;
- no request after failed client-side validation;
- success shown only after server confirmation;
- a guard against duplicate submission;
- the pending state of an optimistic update.

## Failure handling

The `When a test fails:` lines ask the agent to decide first whether the app or the test is wrong, never to change product code to make a test pass unless the user asked for that change, to change an assertion only to match a requirement the user named and otherwise not to weaken, skip or delete it, and to report a regression it did not cause instead of fixing it. They replace the removed `playwright-debugger` and `cypress-debugger` skills for ordinary failure diagnosis. The `e2e-debugger` skill ships these lines unchanged as `failure-rules.md` and delivers them with a request to fix a failing test, so no instruction-file setup is needed for that request; it adds a three-run flake check. Use `e2e-reviewer` for a test made green by weakening it.

Why: in a development replication on two app sets (n=16 app regressions per model), the official Playwright healer asked to fix a test changed product code in 16/16 runs on Claude and 16/16 on Codex; with the failure-handling note in the instruction file this dropped to 0/16 (Claude) and 1/16 (Codex). The effect required the memo file in the instruction file; delivery through the `e2e-debugger` skill instead of that file has not been measured yet. An earlier pilot, before the replication, measured 13/16 (Claude) and 16/16 (Codex) without the note and 0/16 and 2/16 with it. The separate [test-failure policy](test-failure-policy.md) is a longer, measured rule for edits to failing assertions.

## Measured effect and limits

In five pre-registered pairs of small authored apps, specs written with the memo detected more injected failure-path faults than specs written without it: Codex 12/89 to 80/92, Claude 31/93 to 74/86. The fixed per-pair gates were met in 4 of 5 pairs for Codex and 3 of 5 for Claude; the count is the same whether the invalid-rate gate is read per host or pooled, although the Claude pairs that meet it differ. In those pairs Codex could not run its specs; in a pre-registered rerun of one pair where it could, Codex rose from 1/18 to 15/18. On three real repositories (two of them well known, so direction only), detection rose from 3/33 to 27/33 (Claude) and 3/33 to 26/33 (Codex).

Replication 1, by a separate benchmark session (two other apps, 96 valid cells, two models), measured no difference with this exact memo (same SHA-256), but its faults were ordinary-path behaviours, not the failure-path classes the memo targets; it shows the memo did not change ordinary-path detection there (mostly ceiling).

Replication 2, by the same separate session with failure-path faults: "An independent replication on two public example apps with failure-path faults and neutral prompts (48 cells, two models) found that without the memo the agent-written tests caught none of the failure-path faults (0/120) and with the memo they caught 98/120 (80-83% per model)." The apps were the redux-toolkit optimistic-update and SWR optimistic-ui examples, each changed to fail deterministically, with workspaces outside the home directory. Limits: two apps, one feature each, five faults per app authored by the replicating session, four candidate faults dropped before freezing because they were not visible to a user, apps likely in training data, one prompt shape. The replicating session chose its faults within the memo's five target classes, learned from the public CHANGELOG; it did not read the memo text. The two replications are not pooled.

Scope: the memo targets failure paths of flows that write to a server; it adds nothing where there are none. In the author's pairs and in replication 2 the failure-path faults fall in the memo's own classes, and the author's out-of-class result is one pair; no measurement yet uses faults chosen without reference to the memo.

These are development-stage results on authored apps with visible source, one model per host and a few repetitions. Claude cells also loaded the operator's user-level `CLAUDE.md` in both arms. They are not a sealed benchmark and do not show that the memo works on your project. See the [evidence record](benchmarks/test-authoring-memo-v1.md) for the method, per-pair results and limits.

## Check your own tests

Do not assume the memo worked. Pick one failure-path behavior, break it in a copy of the app (for example, make the save handler ignore a server error) and confirm the unchanged spec fails. The `e2e-reviewer` skill can propose and run such a probe with your approval; see [runtime probes](../skills/e2e-reviewer/references/runtime-probes.md). When `@voidmatcha/e2e-skills-scanner` is installed, its `e2e-skills-check` CLI can find a supported change and prepare a probe plan for it, for you to approve.
