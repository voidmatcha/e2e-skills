# Optional test-authoring memo

A short memo you can add to a project so that coding agents writing Playwright tests also cover failure paths. It is optional and separate from the four skills: no e2e-skills skill loads or reads it.

## The memo

Copy the text inside the block exactly (SHA-256 `c7e5d9a2dc69ee8f5366154f165269d8a33eaacc5fbb13266a3ed009ba3ca2bf` for the block content with a trailing newline; 136 words excluding Markdown markup):

```text
# Test authoring notes

- Make the server reject the action (intercept the request, answer with an error). Assert the interface returns to its previous state and shows no success indicator.
- Where the code guards an action, attempt the forbidden one: submit invalid or empty input; trigger the same action twice. Assert nothing was sent, or only one request, and state did not change.
- A success indicator is not proof. Assert it appears only after the server confirmed, and read server-side state directly.
- If the interface updates before the server answers, hold the response, assert the pending state, then release it.
- If the code lacks a guard, do not assert it; a test must pass on the unchanged app.

Finally, ask of each assertion: if this behavior broke, would this line fail? Strengthen any that would still pass.
```

## How to use it

Paste the memo unchanged into the project's always-loaded instruction file: `CLAUDE.md` for Claude Code, `AGENTS.md` for Codex. Then ask for tests as you normally would. The measured effect applies to this exact text; edited wording is untested.

## What it targets

Agent-written E2E tests often stay green when a failure path breaks. The memo targets five such behaviours:

- rollback of the interface after the server rejects an action;
- no request after failed client-side validation;
- success shown only after server confirmation;
- a guard against duplicate submission;
- the pending state of an optimistic update.

## Measured effect and limits

In five pre-registered pairs of small authored apps, specs written with the memo detected more injected failure-path faults than specs written without it: Codex 12/89 to 80/92, Claude 31/93 to 74/86. The fixed per-pair gates were met in 4 of 5 pairs for Codex and 3 of 5 for Claude. On one public example app, detection rose from 0/9 to 9/9 (Claude) and 0/9 to 8/9 (Codex).

These are development-stage results on authored apps with visible source, one model per host and a few repetitions. They are not a sealed benchmark and do not show that the memo works on your project. See the [evidence record](benchmarks/test-authoring-memo-v1.md) for the method, per-pair results and limits.

## Check your own tests

Do not assume the memo worked. Pick one failure-path behaviour, break it in a copy of the app (for example, make the save handler ignore a server error) and confirm the unchanged spec fails. The `e2e-reviewer` skill can propose and run such a probe with your approval; see [runtime probes](../skills/e2e-reviewer/references/runtime-probes.md). When `@voidmatcha/e2e-skills-scanner` is installed, its `e2e-skills-check` CLI can discover and bind a supported change for an approved probe.
