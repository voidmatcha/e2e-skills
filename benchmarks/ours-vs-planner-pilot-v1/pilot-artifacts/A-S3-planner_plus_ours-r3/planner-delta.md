# Scenario A-S3 — planner delta reconciliation ledger

- Cell: `A-S3-planner_plus_ours-r3` (arm `planner_plus_ours`, protocol `ours-vs-planner-pilot-v1`)
- Target: `eilinwis/playwright-chat-lab` @ `7f2e2650af1c`, served at `http://localhost:5174`, entry route `/`
- Planner status: **READY** (admission gate passed — planner reported both `planner_setup_page`
  and `planner_save_plan` visible, and its browser launched successfully)
- Planner plan artifact: `specs/pilot-a-s3-planner-plan.md` (saved by the planner via `planner_save_plan`)
- Frozen scope preserved: exactly one scenario (A-S3), entry route `/`, no additions/splits/rewording

## Frozen scenario under review

> ## Scenario A-S3
> - Given: the application is served at http://localhost:5174, fresh browser profile, empty client-side storage
> - When: the user performs the actions the outcome below requires
> - Then: A signed-in user exports the conversation as a PDF download from the chat screen.

## Delta ledger

| # | Planner delta (summarised) | Evidence class | Disposition |
|---|---------------------------|----------------|-------------|
| D1 | Empty chat screen `/` exposes only: theme buttons "Aurora"/"Test Runner", banner "Go to the chat screen" + heading "Playwright Chat Lab", nav links Chat/Search/Message history/Playground/Help, checkbox "Assistant mode Funny mode", text "No messages yet.", button "Help", textbox "Type a message…", disabled button "Send", button "Reset Chat". No sign-in/login/account/session element of any kind. | `observed` (live, planner) | **Absorbed** — independently corroborates my own live snapshot of `/` this session (identical control set). |
| D2 | Every in-app nav route (`/search`, `/history`, `/playground`, `/help`) explored live; none contains a sign-in control. The Playground filter item literally titled "Auth middleware" is inert demo data, not an auth feature. | `observed` (live, planner) | **Absorbed** — matches my own live snapshots of the same four routes. |
| D3 | After sending a message on `/`, the populated chat screen has an identical control set to the empty state; no export / download / PDF / save / share / print control appears in either state. Console shows `ERR_CONNECTION_REFUSED @ http://localhost:3001/api/messages` (no backend), unrelated to export. | `observed` (live, planner) | **Absorbed** — matches my own live populated-state observation (message "Hello there!" → reply "GENERAL KENOBI!!"; buttons unchanged: Aurora, Test Runner, Go to the chat screen, Chat, Search, Message history, Playground, Help, Help, Send, Reset Chat). |
| D4 | Source grep across `src/`: every "export" hit is the JS/TS `export` keyword; the only "auth" hit is the string `'Auth middleware'` in `src/data/playgroundItems.ts`; zero hits for "pdf", "sign in", "login". | `inference` (source only) | **Absorbed as corroboration only.** Source inference cannot substitute for live evidence and supplies no locator; nothing from this delta may reach a test. Consistent with D1–D3. |
| D5 | Verification condition: a locator for a sign-in control on `/` must fail; a locator for an export/download/PDF control on the chat screen (empty or populated) must fail; a Playwright `download` event awaited after any chat-screen interaction must time out. | `verification condition` | **Not absorbed into a test.** These are red conditions describing the *absence* of the capability. Turning them into a passing spec would be a tautological assertion on a capability the app does not have — barred by the honesty rule. Recorded here as the evidence basis for the missing-capability verdict. |
| D6 | Only routes reachable from visible in-app navigation were explored; the `localhost:3001` backend was down, so server-only functionality could not be probed over the network; non-role/name-based hidden affordances were not specifically probed. | `limitation` | **Recorded, not absorbed.** I independently reduced this limitation: a live DOM sweep on the populated chat screen enumerated every `button`/`a` element and word-matched the full `document.body.innerHTML` for `pdf, export, download, signin, signout, login, logout, account, print` → `NO_MATCHES`. No hidden non-ARIA affordance was found either. |

### Scenario-changing deltas — RETURNED_TO_APPROVAL_GATE

None. The planner preserved the frozen scope and proposed no scenario addition, split, reword, or
substitution. Nothing was returned to the approval gate, and nothing was declined.

Counts: absorbed = 4 (D1–D4, all as corroborating evidence; no locator absorbed because none exists);
returned_to_approval_gate = 0; declined = 0.

### Inferred locators reaching the final test

None — there is no final test. No locator from any delta (observed or inferred) was written into a spec.

## Reconciled outcome

Both the planner (independent MCP browser session) and this session's own live exploration
(`agent-browser`, `--allowed-domains localhost`, final URL verified `http://localhost:5174/`) agree:

1. The application has **no sign-in / authenticated-user concept** anywhere.
2. The chat screen has **no export-conversation control**, and nothing in the app produces a
   **PDF download**.

Scenario A-S3 requires both. Per the honesty rule, no candidate spec was emitted and no locator was
invented. Verdict: `rejected_missing_capability`.
