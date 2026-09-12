# Scenario A-S1 — planner reconciliation ledger

Arm: `planner_plus_ours`. Cell: `A-S1-planner_plus_ours-r3`.
Planner status: **READY** (admission gate passed — the delegated
`playwright-test-planner` confirmed both `planner_setup_page` and
`planner_save_plan` were visible and its browser launched).
Planner plan artifact: `specs/pilot-a-s1-plan.md` (written by `planner_save_plan`).

The frozen scenario text was not altered. The planner was asked for plan deltas
only. This ledger classifies each delta and records what was absorbed.

Independent exploration by this skill (Step 3) used the standalone
`playwright-cli` (session `pilot`) with a `context.route('**/*')` guard
installed *before* navigation that aborted every request whose URL was not
under `http://localhost:5174/`. The planner explored the same origin through
its own MCP browser without that guard. Where both saw the same thing, the
delta is marked `observed (corroborated)`.

## Ledger

| # | Delta | Planner label | My label after reconciliation | Disposition |
|---|---|---|---|---|
| D1 | Initial disabled/`Loading…` state; all controls (`funny-mode-toggle`, `chat-input`, `send-button`, `help-suggestion`, `reset-button`) start disabled | observed | observed (corroborated — my first snapshot showed `checkbox … [checked] [disabled]`, `textbox … [disabled]`, `paragraph: Loading…`) | **ABSORBED** — spec gates on the toggle being enabled before any interaction |
| D2 | Gate clears from the `finally` of the bootstrap `fetchMessages()` effect regardless of fetch outcome | inference (source) | inference — I did not prove the code path, only the *effect* (ready state reached while `localhost:3001/api/messages` failed) | **ABSORBED as behaviour, not as claim** — the spec waits on the observed enabled/`No messages yet.` state, never on the source-level flag |
| D3 | Two `GET http://localhost:3001/api/messages` fail and the app still becomes ready | observed | observed (corroborated — my run shows the same two requests failing, blocked by my origin guard rather than refused; same net effect) | **ABSORBED** — explains why no backend stub is needed |
| D4 | `loading-indicator` / "Thinking..." transient (~120 ms) may make a naive read flaky | inference + limitation (planner could not capture it live) | **observed by me** — `getByTestId('loading-indicator')` reached `visible` state during a live send in session `pilot`; also confirmed it is a *separate* testid from `message-assistant`, so the reply locator can never match the placeholder | **ABSORBED, and the planner's limitation is closed by my observation** |
| D5 | All assertions on the reply must be auto-waiting/polling, never a one-shot `textContent` read | verification condition | verification condition | **ABSORBED** — spec uses `toHaveText` only |
| D6 | Assert `funny-mode-toggle` is *checked* before sending rather than assuming the default; an unchecked toggle would silently exercise the real `POST /api/chat` path | verification condition | verification condition — **load-bearing**, this was not in my pre-planner contract | **ABSORBED** (new verification condition) |
| D7 | No `POST /api/chat` may occur after Send while the toggle is checked | verification condition | verification condition — corroborated by my own network capture (no `/api/chat` request after send) | **ABSORBED** — spec records browser requests and asserts zero `/api/chat` |
| D8 | The reply key is the **first `[a-zA-Z]` match anywhere** in the trimmed string, upper-cased — *not* `charAt(0)` | inference (source: `src/lib/funnyReply.ts`) | inference | **ABSORBED as a message-choice constraint only.** The spec's message begins with a letter, so the two rules coincide and the test does not depend on the inferred detail. The inferred rule is *not* encoded as a computed expectation. |
| D9 | The test message must avoid `?`, exact `Help`, and exact `Hello there!` — each routes to a different reply mechanism | inference (source) + verification condition | verification condition — I independently observed the `Hello there!` special case is what the *existing* `e2e/tests/chat.spec.ts` covers | **ABSORBED** — `"Zebra crossing at dawn"` satisfies all three constraints |
| D10 | Locators `funny-mode-toggle`, `chat-input`, `send-button`, `message-user`, `message-assistant`, `reset-button` | observed | observed (corroborated — every one of these was emitted by `playwright-cli generate-locator` against a live element ref in my own session) | **ABSORBED** |
| D11 | `loading-indicator` locator | inference only (planner) | **observed by me** | Not used in the final test (unnecessary — `message-assistant` is a distinct testid), but recorded as observed |
| D12 | `reset-button` fires a best-effort failing `POST /api/reset` | observed (planner) | observed (corroborated — I used Reset three times during exploration and the transcript cleared each time) | **DECLINED for the spec** — out of the frozen outcome; each test gets a fresh context instead |
| D13 | Planner's suggested file `specs/a-s1-offline-canned-reply.spec.ts` | (plan artifact field) | n/a | **DECLINED** — the output contract fixes the path at `e2e/pilot-a-s1.spec.ts` |
| D14 | Planner's example message `"Hello there"` (letter H) | observed | observed | **DECLINED in favour of `"Zebra crossing at dawn"`** — `"Hello there"` is one character away from the `Hello there!` special case, an avoidable footgun; and I had already proven the letter-keying live with a Q/Z contrast pair sharing the suffix `at dawn` |

## RETURNED_TO_APPROVAL_GATE (recorded, never applied)

Every item the planner listed under its own `SCOPE-CHANGING (not applied)`
heading is scenario-changing. None was applied; there is no human in this
session to approve any of them.

1. Toggling funny mode off to exercise the real `POST /api/chat` path.
2. Sending exactly `Hello there!` for the `GENERAL KENOBI!!` + GIF special case.
3. Sending `Help` or any `?` message for the app-assistant topic replies.
4. Sending a letter-free message for `FUNNY_NO_LETTER_FALLBACK`.
5. Asserting Reset Chat's `/api/reset` network semantics as its own outcome.
6. Asserting the initial readiness gate as an independent test outcome.

## Inferred locators reaching the final test

None. Every locator in `e2e/pilot-a-s1.spec.ts` was emitted by
`playwright-cli generate-locator` against a live element reference in this
session.

## Counts

- absorbed: 10 (D1–D11 minus D12/D13/D14; D2 absorbed as behaviour only)
- returned_to_approval_gate: 6
- declined: 3 (D12, D13, D14)
