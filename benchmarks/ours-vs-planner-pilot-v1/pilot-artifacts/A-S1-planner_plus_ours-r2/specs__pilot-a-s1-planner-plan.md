# Scenario A-S1 Plan Hardening (Auxiliary)

## Application Overview

SCOPE: This document hardens exactly ONE pre-approved, frozen scenario. No scenarios were added, split, reworded, or invented. No test spec was written or modified.

## Frozen Scenario (verbatim, unmodified)

## Scenario A-S1
- Given: the application is served at http://localhost:5174, fresh browser profile, empty client-side storage
- When: the user performs the actions the outcome below requires
- Then: In offline mode, sending a message shows the user's message and the deterministic canned reply keyed by its first letter in the chat transcript.

## Admission Gate Result
Both `planner_setup_page` and `planner_save_plan` were available; the browser launched successfully (verified at about:blank, then navigated live to http://localhost:5174/). All findings below were gathered by interacting with the LIVE running app at http://localhost:5174/ unless explicitly labeled `inference` (source-code-derived only).

## Observed Locator Mapping (role / accessible name / observed state)

| Element | Role | Accessible name | data-testid | Observed state(s) | Label |
|---|---|---|---|---|---|
| Message input | textbox | "Type a message…" | chat-input | empty+enabled (initial) -> active with typed text -> cleared+enabled after send; disabled while history is loading (historyReady=false) | observed |
| Send button | button | "Send" | send-button | disabled (empty input, and while pending) -> enabled (non-whitespace input present) -> disabled again after send clears input | observed |
| Funny-mode toggle | checkbox | "Assistant mode Funny mode" (composite; visual sub-labels "Assistant mode" / "Funny mode", toggle literally controls "Funny mode") | funny-mode-toggle | checked by default on fresh load (offline/funny-mode ON) = the Given precondition; transiently disabled while historyReady=false | observed |
| Reset Chat button | button | "Reset Chat" | reset-button | enabled at rest; disabled while loading/history not ready | observed |
| Help suggestion chip | button | "Help" | help-suggestion | enabled at rest | observed |
| Initial placeholder | paragraph (text) | n/a | none (class chat-window__placeholder) | shown briefly on load/reload: literal text "Loading…" while historyReady=false | observed |
| Empty-transcript placeholder | paragraph (text) | n/a | none (class chat-window__placeholder) | literal text "No messages yet." once historyReady=true and messages.length===0 | observed |
| Pending/loading reply bubble | generic (div) | n/a | loading-indicator | transient; class "chat-message chat-message--assistant chat-message--loading"; literal text "Thinking..."; confirmed present immediately post-click via a race-condition probe (loadingCount:1) | observed |
| User message bubble | generic (div) | n/a | message-user | class "chat-message chat-message--user"; textContent = exact sent text | observed |
| Assistant reply bubble | generic (div) | n/a | message-assistant | class "chat-message chat-message--assistant" (never has --loading; loading uses a separate testid) once settled; textContent = deterministic canned reply | observed |

Note: getByTestId('message-assistant') is inherently immune to matching the transient loading placeholder because LoadingMessage.tsx uses a distinct data-testid ("loading-indicator"), unlike the repo's existing class-based `.chat-message--assistant` locator (e2e/pages/chat/chatPage.ts), which must add `:not(.chat-message--loading)` to be safe. (observed DOM + inference from reading src/components/LoadingMessage.tsx and e2e/pages/chat/chatPage.ts)

## State Transitions Observed
1. Empty -> Typed: filled "Testing scenario" into chat-input; snapshot showed Send button's `[disabled]` attribute removed. Proved by direct before/after accessibility snapshot diff. (observed)
2. Typed -> Pending: clicked Send; a script run immediately after `.click()` (racing the app's internal reply delay) found `.chat-message--loading` count=1 with text "Thinking...". Proved by live DOM query timed to run before settlement. (observed)
3. Pending -> Settled: ~120ms later (source constant FUNNY_REPLY_DELAY_MS in src/components/ChatWindow.tsx, not independently timed via trace/video — inference for the exact ms figure, but the transition itself, i.e. loading indicator gone and reply text present, was observed live across three separate sends: "Testing scenario"->T reply, "Banana test"->B reply, "Zebra check"->Z reply, each exactly matching src/data/funnyReplies.ts table entries). (observed for the transition; inference for the precise 120ms duration)
4. Reload does NOT restore the on-screen transcript (chat state is in-memory/session-scoped: after reload with 2 prior exchanges present, screen reverted to "No messages yet."), even though the same exchanges remain in localStorage. (observed)
5. Reset Chat clears the on-screen transcript and best-effort POSTs to /api/reset (fails offline, non-blocking) but does NOT clear the localStorage key ai-assistant-chat-history-v1. (observed)

## Hazards / Guards Observed or Inferred
- **Transient-placeholder collision hazard (observed + inference):** `.chat-message--assistant` is shared by both the "Thinking..." placeholder and the real reply while pending; a naive `.first()`/class-only locator can transiently bind to the placeholder. Use `getByTestId('message-assistant')` (safe, distinct testid) or `.chat-message--assistant:not(.chat-message--loading)`.
- **Client-side persistence hazard (observed):** Successful exchanges are mirrored into localStorage key `ai-assistant-chat-history-v1` (confirmed via direct localStorage read after sending), which survives both page reload and the Reset Chat button. The Given precondition "empty client-side storage" can only be reliably satisfied by starting from a genuinely fresh browser context/storageState — not by reloading or clicking Reset Chat inside an already-used context — and the scenario's own send will itself write to this key, which could leak into later/parallel tests unless each test uses an isolated context.
- **Off-origin background-request hazard (observed):** On every load, the app fires GET http://localhost:3001/api/messages (and on Reset Chat, POST http://localhost:3001/api/reset); both fail with net::ERR_CONNECTION_REFUSED in the console since no backend runs on port 3001. This is the app's own expected offline behavior (confirmed via browser_network_requests and console events) and must not be treated as a test failure signal (e.g., do not assert "zero console errors"); per instructions this was observed, not stubbed or repaired, and no navigation to the off-origin URL was performed.
- **Exact-match Easter-egg hazard (inference, source-read only, not exercised live):** `getFunnyReplyContent` in src/lib/funnyReply.ts special-cases the exact trimmed string "Hello there!" to return a fixed "GENERAL KENOBI!!" reply plus an image, bypassing the first-letter table entirely. The scenario's chosen message must avoid this exact phrase.
- **Question / Help-keyword interception hazard (inference, source-read only, not exercised live):** src/components/ChatWindow.tsx calls `getAppAssistantReply(text) ?? getFunnyReplyContent(text)` — any message containing "?" that matches a topic keyword (or the exact word "Help") returns a fixed topical reply instead of the first-letter-keyed funny reply. The scenario's message must not contain "?" and must not be the exact word "Help".
- **Leading-non-letter/no-letter hazard (inference, source-read only, not exercised live):** the letter-picking regex `/[a-zA-Z]/` skips leading non-letter characters, and a message with no letters at all falls back to a fixed FUNNY_NO_LETTER_FALLBACK string rather than a letter-specific one.
- **Ordering/multiplicity hazard (inference from repo POM comments, consistent with observed structure):** if a test sends more than one message, `.first()`-based locators always bind to the earliest bubble; assertions about "the reply to the just-sent message" must target the correct index/last() explicitly.

## Verification Conditions (to make the assertion load-bearing, not tautological)
1. Assert the reply text with full string equality against the specific FUNNY_REPLIES_BY_LETTER[firstLetter] entry (src/data/funnyReplies.ts) for the sent message's first letter — not merely "assistant bubble is non-empty" — so a regression that returns the wrong letter's line, or a generic placeholder, fails the test. (verification condition)
2. Send two messages with different first letters in the same test and assert each yields its own distinct, correct reply — a single-message test cannot distinguish "keyed by first letter" from "always returns one hardcoded reply." (verification condition)
3. Assert the user bubble (`getByTestId('message-user')`) contains the exact literal sent text and appears immediately before the assistant bubble in DOM/list order, so the "shows the user's message" half of the Then-clause is independently pinned, not just the reply half. (verification condition)
4. Assert no POST request to /api/chat (or /api/messages) fires for the funny-mode send (e.g., via request interception/count), positively proving "no network call," which is what makes this "offline mode" behavior rather than an accidental successful network call. (verification condition)
5. Wait for `data-testid="loading-indicator"` to detach before reading final content, rather than only waiting for `message-assistant` to exist or using a fixed sleep, to avoid a race that reads stale/placeholder DOM as a false pass. (verification condition)
6. Assert Send returns to its disabled idle state (empty input) as an explicit settle-signal instead of an arbitrary wait. (verification condition)
7. Required failure conditions (must turn the test RED): (a) reply text does not exactly match the expected table entry for the sent message's first letter; (b) two different-first-letter messages produce the same reply text; (c) any network POST fires for a funny-mode send; (d) the user's own message bubble is missing/altered/mis-ordered; (e) the assertion reads "Thinking..." instead of the settled reply due to a timing race. (verification condition)

## Limitations (could NOT observe this session)
- Did not exhaustively verify all 26 letters' canned replies live; only B, T, Z were exercised live (each matched src/data/funnyReplies.ts exactly). The full table's content beyond those three is source-derived only. (limitation)
- Did not exercise the "Hello there!" exact-match Easter egg, the "?"/topic-keyword interceptor, the exact "Help" menu path, or the no-letter/leading-non-letter fallback live; these hazards are source-derived only. (limitation)
- Did not spin up a second, separate fresh Playwright browser context/storageState to independently re-verify the "empty client-side storage" starting condition; this session's own origin now has non-empty localStorage as a side effect of the exploration performed here (ai-assistant-chat-history-v1 and chat-lab:theme keys). A real test run needs its own fresh context, which was not separately instantiated in this planning session. (limitation)
- Did not independently trace/measure the ~120ms reply delay via network/video trace; relied on the FUNNY_REPLY_DELAY_MS source constant plus one successful race-condition probe. (limitation)
- Did not test keyboard-only (Enter-to-send) submission, mobile/responsive viewport, or deep screen-reader semantics beyond the automatically computed accessibility snapshot roles/names. (limitation)
- Did not navigate to the Message History / Search screens to confirm live whether the persisted localStorage exchanges surface there (plausible from key naming and in-app help text, not observed). (limitation)

## Test Scenarios

### 1. Scenario A-S1

**Seed:** `e2e/seed.spec.ts`

#### 1.1. Offline mode: sending a message shows the user's message and the deterministic first-letter-keyed canned reply

**File:** `e2e/chat-offline-funny-reply.spec.ts`

**Steps:**
  1. Given: Start the app at http://localhost:5174/ using a fresh browser context with empty storageState (no ai-assistant-chat-history-v1 / chat-lab:theme localStorage keys), so client-side storage is genuinely empty rather than merely reloaded or Reset.
    - expect: Page loads with title 'Playwright Chat Lab' (observed)
    - expect: A brief initial placeholder with literal text 'Loading…' appears while historyReady is false and all controls (funny-mode-toggle, chat-input, send-button, reset-button, help-suggestion) are disabled, during which a background GET to http://localhost:3001/api/messages is attempted off-origin and fails with net::ERR_CONNECTION_REFUSED (observed) -- this failure is the app's own expected offline behavior and must not be stubbed, repaired, or treated as a test failure signal
    - expect: Once settled, the placeholder text reads exactly 'No messages yet.' (observed)
    - expect: The funny-mode checkbox (data-testid=funny-mode-toggle, accessible name 'Assistant mode Funny mode') is checked by default, confirming offline/funny-mode canned-reply behavior is already active with no toggle interaction required (observed)
    - expect: The Send button (data-testid=send-button, role button, name 'Send') is disabled because chat-input (role textbox, placeholder 'Type a message…') is empty (observed)
  2. When (part 1 - type): Fill chat-input with a plain-text message that (a) starts with a plain letter, no leading digit/punctuation, (b) contains no '?' character, (c) is not the exact string 'Hello there!', and (d) is not the exact word 'Help' -- e.g. 'Banana test' -- so the send unambiguously exercises the first-letter-keyed funny-reply path and not the question/topic interceptor, the Hello-there Easter egg, or the Help menu (all three are documented hazards in src/lib/appAssistantReply.ts and src/lib/funnyReply.ts that would otherwise silently swap out the reply the scenario is meant to test -- inference, not exercised live in this session).
    - expect: send-button becomes enabled as soon as the field holds non-whitespace text (observed via before/after snapshot diff)
  3. When (part 2 - send): Click send-button.
    - expect: chat-input is immediately cleared and send-button becomes disabled again (observed)
    - expect: A transient element data-testid='loading-indicator' (class chat-message--assistant chat-message--loading, text 'Thinking...') appears; confirmed live via a script that read the DOM immediately after .click(), racing the app's internal reply delay, and found loadingCount:1 with text 'Thinking...' (observed) -- this element must never be the one asserted against as the final reply, since it shares the chat-message--assistant class with the real reply (hazard)
    - expect: No POST request fires to /api/chat or /api/messages for this exchange (funny mode performs no network call at all per src/lib/funnyReply.ts and was corroborated by the absence of such requests in browser_network_requests during this session) -- assert this via request interception/count, not merely via the absence of a visible error message (verification condition)
  4. Then: Wait explicitly for data-testid='loading-indicator' to detach from the DOM (do not just wait for message-assistant to exist, and do not use a fixed sleep) before making final assertions.
    - expect: A new data-testid='message-user' element (class chat-message chat-message--user) is appended containing the exact literal text that was sent, unmodified (observed live for 3 distinct messages)
    - expect: A new data-testid='message-assistant' element (class chat-message chat-message--assistant, without --loading) is appended immediately after it, containing the EXACT deterministic canned reply for the message's first letter per src/data/funnyReplies.ts -- assert full string equality, not substring/contains, and not merely 'non-empty' (observed live: 'Banana test'->'Bananas are just shy yellow kayaks that never learned to swim.', 'Testing scenario'->'Tabs versus spaces? The real war is humans versus reasonable bedtimes.', 'Zebra check'->'ZIP files are introverted folders wearing compression hoodies.', each matching the source table exactly)
    - expect: send-button returns to its disabled idle state (input now empty) as an explicit settle-signal (observed)
    - expect: To make the assertion load-bearing rather than tautological, repeat the type+send+assert cycle once more in the same test with a message whose first letter differs from the first (e.g. one 'B...' message and one 'Z...' message) and assert each produced its OWN distinct correct reply -- a single-message test cannot distinguish 'keyed by first letter' from 'always returns one hardcoded string' (verification condition; observed live across B/T/Z in this session)
    - expect: Required failure conditions that must turn this test RED: reply text not matching the exact table entry for the sent message's first letter; the same reply text appearing for two different-first-letter messages; any network POST firing for a funny-mode send; the user's own message bubble missing, altered, or not immediately preceding the reply bubble; or the assertion capturing 'Thinking...' instead of the settled reply due to a timing race (verification condition)
