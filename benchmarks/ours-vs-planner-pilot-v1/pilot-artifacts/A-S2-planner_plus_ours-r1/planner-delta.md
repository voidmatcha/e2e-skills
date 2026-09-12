# A-S2 — planner delta reconciliation ledger

- Cell: `A-S2-planner_plus_ours-r1` (arm `planner_plus_ours`)
- Planner status: **READY** — the delegated `playwright-test-planner` confirmed both
  `planner_setup_page` and `planner_save_plan` were visible in its tool list and that its
  browser launched (paused at `about:blank`) before exploring.
- Planner output: `specs/pilot-a-s2-planner-plan.md` (saved by the planner via `planner_save_plan`).
- Frozen scope preserved: exactly one scenario (A-S2), entry route `/`, target `http://localhost:5174`.
- Implementer: this skill (`playwright-test-generator` pipeline). The first-party generator and
  healer agents were NOT invoked.

## Delta classification and disposition

| # | Delta (planner) | Evidence label | Disposition | Notes |
|---|---|---|---|---|
| 1 | `Send` (button, "Send") is disabled while the composer is empty and enables once the textbox has content; gate on enabled before clicking | observed (planner) — also independently observed by this skill (`isEnabled()` → `true` after `fill`) | **Absorbed** | Spec asserts `await expect(chat.sendButton).toBeEnabled()` before the click |
| 2 | Clicking Send renders the user text and an assistant reply; Send returns to disabled | observed | **Absorbed** | Used as the pre-reload settled-state gate |
| 3 | The exchange is written synchronously to `localStorage['ai-assistant-chat-history-v1']` with fields `id, userContent, assistantContent, userTimestamp, assistantTimestamp` | observed | **Absorbed** | Becomes the V4 write-contract proof (the write boundary is localStorage, not a request) |
| 4 | On `/history` the exchange renders as `list` → `listitem` (time, "You" + text, "Assistant" + reply); locate the entry by the user message text, never by the run-dependent date/time | observed + verification condition | **Absorbed** | Spec uses `getByRole('listitem').filter({ hasText: MESSAGE })`; verified live to resolve to exactly 1 node |
| 5 | A full reload on `/history` still shows the same listitem | observed | **Absorbed** | Same outcome reached in this skill's exploration via reload on `/` then navigating to History |
| 6 | Reloading the **Chat** screen does NOT restore the conversation into the chat panel ("No messages yet."), even though localStorage and `/history` still hold it — the post-reload assertion must be scoped to the Message History screen | observed + limitation | **Absorbed — load-bearing** | This is the delta with the highest value: it rules out the naive "reload `/` and assert the chat thread" implementation, which would fail against correct app behavior |
| 7 | "Delete history" opens a native `confirm()` dialog with text "Delete all message history stored in this browser? This cannot be undone."; an unhandled click leaves the flow blocked | observed | **Absorbed — load-bearing** | Independently observed by this skill too. Spec registers `page.once('dialog', …accept())` before the click; without it Playwright auto-dismisses and the clear silently never happens |
| 8 | Cancel/dismiss path of the confirm dialog not exercised | limitation | **RETURNED_TO_APPROVAL_GATE (not applied)** | Testing the cancel path would be a second scenario; the frozen brief admits exactly one. Recorded, not implemented. No human is available to approve it in this session |
| 9 | After accepting: listitem removed, empty-state paragraph "No history yet. Send a message in Chat to build your archive." visible, "Delete history" becomes disabled, storage key returns `null` | observed + verification condition | **Absorbed** | All four asserted in the spec |
| 10 | Pre-existing failing `GET http://localhost:3001/api/messages` on every navigation is app noise; do not stub, repair, or wait on it | observed | **Absorbed as a constraint** | The spec adds no route stub. Network log across the whole exploration session showed only GETs — no POST left the page, which is part of the V5 replay-safety evidence |
| 11 | Assistant reply text may be randomized (checkbox "Assistant mode Funny mode" checked); key assertions off the user text, not a hardcoded reply | **inference** (planner labelled the variability itself as inference; only one sample observed) | **Declined, after live re-verification** | Falsified live: `Hello there!` → `GENERAL KENOBI!!` observed on two independent sends in this session, and `e2e/tests/chat.spec.ts` already asserts the same pair. `src/lib/funnyReply.ts` is a pure letter/exact-match lookup with no randomness. The spec locates the entry by the user text (the planner's safe core, absorbed) **and** asserts the reply text, because asserting only the user text would let a broken reply-persistence path pass |
| 12 | "Reset Chat" (Chat screen) is a distinct control from "Delete history" (History screen); its effect on persisted history was not verified | observed + limitation | **RETURNED_TO_APPROVAL_GATE (not applied)** | Ambiguity note absorbed (the spec never touches "Reset Chat"); verifying its effect on `/history` would be a new scenario |

Totals: **absorbed 9**, **returned to approval gate 2**, **declined 1**.

## New verification conditions absorbed (each is a failure condition the candidate would otherwise miss)

1. **Post-reload assertion must be scoped to the Message History screen** — reloading `/` clears the
   chat thread by design, so a chat-panel assertion would fail against a correct app and mask what
   persistence actually promises (delta 6).
2. **The confirm() dialog must be explicitly accepted** — Playwright auto-dismisses dialogs, so
   `clearAllHistory()` never runs without a handler; the "clearing removes it" half of the scenario
   would then assert against an unchanged page (delta 7).
3. **Locate the history entry by message text, not by date/time** — the day heading and timestamp are
   run-dependent, so a date-anchored locator is a latent time-of-day/timezone flake (delta 4).
4. **Send must be enabled before the click** — the composer's Send is disabled while the app is still
   loading history and while the input is empty; clicking too early is a silent no-op (delta 1).
5. **Assert the cleared state three ways** — entry gone, empty-state paragraph visible, Delete button
   disabled — so an in-memory-only clear that leaves storage populated cannot pass (delta 9).

## Honesty notes

- No delta supplied a capability the application lacks. Every capability the scenario needs
  (send, client-side persistence across reload, history listing, clear-with-confirmation) was
  resolved on the live page by this skill independently of the planner.
- No inferred locator reached the final test. Every locator in the candidate was resolved against
  the running app at `http://localhost:5174` in this session.
