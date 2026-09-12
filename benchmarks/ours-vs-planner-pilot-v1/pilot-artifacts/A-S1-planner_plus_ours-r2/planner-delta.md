# Scenario A-S1 — planner delta reconciliation ledger

Arm: `planner_plus_ours`. Auxiliary path per `playwright-agents.md` §"Recommended
auxiliary mode: harden the plan", steps 2–4.

- Planner status: **READY**. Admission gate passed — the delegated
  `playwright-test-planner` confirmed it could see both `planner_setup_page` and
  `planner_save_plan`, and its browser launched (about:blank → live navigation to
  `http://localhost:5174/`, title "Playwright Chat Lab").
- Planner plan saved by the planner itself with `planner_save_plan` at
  `specs/pilot-a-s1-planner-plan.md`.
- Scope preserved: the planner returned deltas for exactly one scenario and
  reproduced the frozen A-S1 text byte-for-byte. It wrote no spec.
- Final implementer: `playwright-test-generator` (this skill). Candidate:
  `e2e/pilot-a-s1.spec.ts` + additive locators in `e2e/pages/chat/chatPage.ts`.

## Classification of every delta

| # | Delta | Class | Disposition |
|---|---|---|---|
| D1 | Locator mapping: `chat-input` / `send-button` / `funny-mode-toggle` / `reset-button` / `help-suggestion` / `message-user` / `message-assistant` / `loading-indicator`, plus roles and accessible names | `observed` (planner, live) | **Absorbed** — independently corroborated by this skill's own Step 3 live session, so nothing inferred reached the test |
| D2 | Funny-mode toggle is `checked` on a fresh load, so offline mode needs no toggle interaction | `observed` | **Absorbed** — asserted as an explicit precondition rather than assumed |
| D3 | Transition empty → typed → pending (`loading-indicator`, text "Thinking...") → settled | `observed` | **Absorbed** as the settled-state gate |
| D4 | Exact 120 ms reply delay | `inference` (source constant `FUNNY_REPLY_DELAY_MS`) | **Not used** — no timing value appears in the test; web-first assertions only |
| D5 | Hazard: the pending placeholder shares `.chat-message--assistant` with the real reply, but carries the distinct `data-testid="loading-indicator"` | `observed` + `inference` | **Absorbed** — the candidate uses `getByTestId('message-assistant')`, which cannot bind to the placeholder, instead of the repo's existing class-based `.first()` locator |
| D6 | Hazard: exchanges persist to `localStorage['ai-assistant-chat-history-v1']`, which survives both reload and Reset Chat; only a fresh context gives the "empty client-side storage" precondition | `observed` | **Absorbed** — the candidate relies on Playwright's per-test fresh context and never uses reload or Reset Chat for isolation; recorded as a comment in the spec |
| D7 | Hazard: the app fires off-origin `GET http://localhost:3001/api/messages` (and `POST /api/reset`) that fail with `ERR_CONNECTION_REFUSED`; this is the app's own offline behaviour and must not be stubbed or treated as failure (e.g. no "zero console errors" assertion) | `observed` | **Absorbed** — nothing is stubbed or repaired, and the candidate asserts nothing about console output |
| D8 | Hazard: the message must avoid `?`+topic keywords, the exact `Hello there!` Easter egg, the exact word `Help`, and leading non-letters, or a different reply path is taken | `inference` (source-read; planner did not exercise these live) | **Absorbed as a constraint on test data only.** `Wookiee cookies` satisfies all four. No inferred locator or inferred product behaviour entered the test |
| D9 | VC: assert the reply with full string equality against the specific `FUNNY_REPLIES_BY_LETTER` entry, not "non-empty" | `verification condition` | **Absorbed** — `toHaveText` with the literal `W` string, hardcoded rather than imported from `src/`, so a regression to the app's own constant cannot make the assertion agree with itself |
| D10 | VC: pin the "shows the user's message" half too — exact literal user text, and the user bubble immediately preceding the reply bubble in list order | `verification condition` | **Absorbed** — one ordered `toHaveText([MESSAGE, EXPECTED_REPLY])` over the transcript's direct test-id children asserts content, order, and cardinality together |
| D11 | VC: prove "no network call" positively — assert no `POST /api/chat` fires for a funny-mode send, via request observation rather than the absence of an error banner | `verification condition` | **Absorbed** — request observer installed *before* `goto`; the test asserts zero `POST .../api/chat` **and** that the observer did see the app's own `/api/messages` bootstrap call, so the zero-count cannot pass vacuously |
| D12 | VC: wait for `loading-indicator` to detach before reading final content; no fixed sleep | `verification condition` | **Absorbed** — `not.toBeAttached()` is part of the settled gate that precedes the primary assertion |
| D13 | VC: use Send returning to its disabled idle state as an explicit settle signal | `verification condition` | **Absorbed** — `toBeDisabled()` in the settled gate |
| D14 | VC (failure conditions a, c, d, e): wrong letter's reply; any POST for a funny-mode send; user bubble missing/altered/mis-ordered; assertion capturing "Thinking..." | `verification condition` | **Absorbed** — each is made red by D9/D10/D11/D12 above |
| D15 | VC: send **two** messages with different first letters in the same test, asserting each yields its own distinct reply (and failure condition (b): same reply for two different first letters) | `verification condition` | **RETURNED_TO_APPROVAL_GATE — recorded, not applied.** It is genuinely load-bearing, but it adds a second send and a second expected value to a scenario whose approved `Then` is "sending **a** message". The brief freezes the scenario byte-for-byte and there is no human in this session to approve the change. The same risk ("the reply is a hardcoded constant") is instead covered at the verification layer by V3, which faults the served `funnyReplies` module and requires the unchanged primary assertion to go red |
| D16 | Candidate file path `e2e/chat-offline-funny-reply.spec.ts` | `inference` | **Declined** — the output contract fixes the path at `e2e/pilot-a-s1.spec.ts` |
| D17 | Assert the boot-time `Loading…` placeholder and the disabled state of all five controls while `historyReady` is false | `observed` (planner saw it) | **Declined** — it is a transient pre-settle state with no deterministic gate; asserting it would race and is outside the frozen `Then`. Recorded, not applied |
| D18 | Limitation: only 3 of 26 letters (B, T, Z) exercised live by the planner; the rest of the table is source-derived | `limitation` | Acknowledged. This skill's own Step 3 session independently observed `W` (twice) and `B` live, and the candidate asserts only the `W` entry it observed |
| D19 | Limitation: the planner did not instantiate a second fresh context to re-verify "empty client-side storage"; its own origin ended the session with non-empty localStorage | `limitation` | Acknowledged and handled by D6 — the candidate gets a fresh context per test from the runner, not from the planner's session |
| D20 | Limitations: Easter-egg / topic-interceptor / no-letter paths, Enter-to-send, mobile viewport, History & Search persistence surfacing not observed | `limitation` | Acknowledged; all are out of the frozen scenario's scope and none is relied on |

## Tally

- Absorbed: **13** (D1, D2, D3, D5, D6, D7, D8, D9, D10, D11, D12, D13, D14)
- Returned to approval gate: **1** (D15)
- Declined: **2** (D16, D17)
- Not used / acknowledged only: D4, D18, D19, D20

No inferred locator reached the final test. Every locator in the candidate was
resolved against the live page by this skill in its own Step 3 session and
independently corroborated by the planner.
