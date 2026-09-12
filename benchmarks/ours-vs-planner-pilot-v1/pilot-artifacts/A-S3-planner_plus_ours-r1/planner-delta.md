# Scenario A-S3 — planner delta reconciliation ledger

Cell: `A-S3-planner_plus_ours-r1` · arm `planner_plus_ours` · protocol `ours-vs-planner-pilot-v1`
Target: `http://localhost:5174` (eilinwis/playwright-chat-lab @ 7f2e2650af1c), entry route `/`.

## Planner admission gate

`planner_status: READY`

- Delegated subagent: `playwright-test-planner` (from the harness-installed `.claude/agents/playwright-test-planner.md`).
- Planner confirmed it can see BOTH `planner_setup_page` and `planner_save_plan`, and invoked both successfully.
- Planner's browser launched and navigated to `http://localhost:5174/`; reported page title **"Playwright Chat Lab"**.
- Planner plan saved via `planner_save_plan` at `specs/pilot-a-s3-planner-plan.md`.

Scope instruction given to the planner: preserve the frozen scenario byte-for-byte, exactly one
scenario, entry route `/`, return plan deltas only. No scope widening was requested or accepted.

## Frozen scenario (unchanged)

```
## Scenario A-S3
- Given: the application is served at http://localhost:5174, fresh browser profile, empty client-side storage
- When: the user performs the actions the outcome below requires
- Then: A signed-in user exports the conversation as a PDF download from the chat screen.
```

## Delta ledger

| # | Delta | Planner label | My classification | Disposition |
|---|-------|---------------|-------------------|-------------|
| D1 | No sign-in / authentication control exists anywhere in the live UI; chat screen `/` exposes only theme buttons "Aurora"/"Test Runner", banner button "Go to the chat screen", nav links Chat/Search/Message history/Playground/Help, checkbox "Assistant mode Funny mode", button "Help", textbox "Type a message…", button "Send", button "Reset Chat". | `observed` | `observed` — independently corroborated by my own live snapshot of `/` and by `document.querySelectorAll('button')` on the live page returning exactly `["Aurora","Test Runner","","Help","Send","Reset Chat"]`. | **Absorbed** (as a capability finding, not a test step) |
| D2 | `src/App.tsx` route table contains only `/`, `/search`, `/history`, `/playground`, `/help` + catch-all redirect; no `/login`. | `inference` | `inference` (source only) — corroborated by my own read of `src/App.tsx`, and by live navigation to all four non-root routes, none of which presented an auth surface. | **Absorbed** as corroboration only; never used as a locator source |
| D3 | Source grep for `login\|signin\|auth` yields one unrelated hit: Playground demo datum `{ id: 'p2', title: 'Auth middleware', category: 'backend' }`. | `inference` | `inference` — corroborated by my own grep. Not a feature. | **Absorbed** as corroboration only |
| D4 | No export / PDF / download control on the chat screen: no such button, link, `a[download]`, blob URL, or download event. | `observed` | `observed` — independently corroborated live: snapshot of the chat screen in both the empty state and the populated state (after sending "Hello there!" → assistant reply "GENERAL KENOBI!!"), plus `document.querySelectorAll('a[download]').length === 0`, plus in-page `find` for `export` / `PDF` / `download` returning "No matches found". | **Absorbed** (capability finding) |
| D5 | `src/components/ChatWindow.tsx` contains no PDF-generation logic, no download handler, no `Blob`/`URL.createObjectURL`, no PDF library import; no PDF dependency in `package.json`. | `inference` | `inference` (source only) — corroborated by my own grep of `src/` and `package.json` (`no pdf deps`). | **Absorbed** as corroboration only |
| D6 | Two `net::ERR_CONNECTION_REFUSED` for `http://localhost:3001/api/messages` on initial load. | `observed` | `observed` — pre-existing application behaviour (the brief anticipates such requests). Not caused by, and does not affect, D1/D4. | **Absorbed** as environmental context; nothing stubbed or repaired |
| D7 | The Given (signed-in session) and the Then (PDF download) cannot be established or exercised through the live UI. | `limitation` | `limitation` | **Absorbed** — this is the blocking finding |
| D8 | The scenario becomes implementable only if a future build adds (1) a named sign-in control producing an observable authenticated state and (2) a named chat-screen export control verifiable via a Playwright download event, `a[download]`, or an `application/pdf` blob. | `verification condition` | `verification condition` | **Absorbed** as a forward-looking condition; **not** implemented, because implementing it would require the capability the app does not have |

### Absorbed / returned / declined counts

- Absorbed: 8 (D1–D8) — all as evidence about capability, none as a test step.
- RETURNED_TO_APPROVAL_GATE: 0. The planner proposed no scenario-changing delta: it did not
  add, split, reword, or substitute the scenario, and it did not propose a weaker
  surrogate outcome (e.g. "print the page", "download chat history as JSON",
  "assert `page.pdf()` output"). Had it proposed such a surrogate, that would have been
  recorded here as RETURNED_TO_APPROVAL_GATE and not applied — there is no human in this
  session to approve a scenario change.
- Declined: 0.

### New verification conditions absorbed

- D8: a chat-screen export control whose activation yields an observable
  `application/pdf` download artifact (download event / `a[download]` / blob). Load-bearing
  because without such an artifact the Then clause has no falsifiable observable — any test
  written today could only assert on state the test itself injected, which the honesty rule forbids.

## Inferred locators reaching the final test

None. No candidate spec was emitted (see verdict), so no locator — observed or inferred —
reached a test file.

## Verdict

Both the planner's independent live exploration and my own agree:

**Scenario A-S3 is NOT IMPLEMENTABLE.** Two required capabilities are absent from the
application:

1. **Authentication** — there is no sign-in flow, no user/session concept, no auth route, no
   auth cookie and no auth key in `localStorage`/`sessionStorage`. A "signed-in user" state
   cannot be reached.
2. **Export conversation as PDF download** — the chat screen exposes no export/download/print
   control, produces no download event, no `a[download]`, and no blob; there is no PDF
   dependency or PDF code path in the application.

`scenario_verdict: rejected_missing_capability`. No candidate spec was written; no locator was
invented; no fixture or storage state was injected to manufacture either capability.
