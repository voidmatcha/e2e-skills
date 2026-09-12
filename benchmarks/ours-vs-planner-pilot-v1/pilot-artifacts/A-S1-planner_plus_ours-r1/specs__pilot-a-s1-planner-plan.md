# A-S1 Plan Deltas — Offline/Funny Mode Canned Reply

## Application Overview

Plan deltas (not a full plan) for Scenario A-S1 only: at http://localhost:5174, in offline mode, sending a message shows the user's message and the deterministic canned reply keyed by its first letter in the chat transcript. All locators below were resolved against the live app in this session unless explicitly marked `inference`. Key finding: the app has no control literally labelled "offline mode" — the scenario's "offline mode" corresponds to the "Funny mode" toggle, which is ON by default and, per the app's own in-app help text, "picks a canned, deterministic reply based on the first letter of your message — no network call, no real AI." This was corroborated live: on initial page load the app attempted GET http://localhost:3001/api/messages and got net::ERR_CONNECTION_REFUSED (no backend running), i.e. the environment is genuinely offline, and Funny mode is the code path that never depends on that backend.

## Test Scenarios

### 1. A-S1 Plan Deltas

**Seed:** `e2e/seed.spec.ts`

#### 1.1. Locators (role + accessible name + data-testid, each labelled observed/inference)

**File:** `specs/pilot-a-s1-planner-plan.md`

**Steps:**
  1. Offline/Funny mode control
    - expect: observed: role=checkbox, accessible name 'Assistant mode Funny mode' (single checkbox with a compound two-option label; the active side is styled via CSS class, not exposed as a separate a11y name), data-testid='funny-mode-toggle'. Confirmed via live accessibility snapshot (checkbox rendered checked=true on fresh load) and via a live DOM query for [data-testid] that returned 'funny-mode-toggle' with empty text content (it's the input element, not the label text).
    - expect: observed: default state on a fresh load is checked (funny/offline mode ON) — confirmed from the initial snapshot immediately after navigation, before any interaction.
    - expect: inference: there is no separate control literally named 'offline mode'; treating 'funny-mode-toggle' checked=true as the scenario's offline mode is an interpretation based on reading src/lib/appAssistantReply.ts's own canned copy ('no network call, no real AI') and src/components/ChatWindow.tsx's handleSend branching on funnyMode — not an explicit product label. Testers should not assume a literal 'Offline' label exists anywhere in the UI.
  2. Message composer
    - expect: observed: role=textbox, accessible name 'Type a message…', data-testid='chat-input' (a <textarea>). Confirmed live: filled it via getByTestId('chat-input').fill(...) and it accepted text; also present in the live [data-testid] enumeration.
  3. Send control
    - expect: observed: role=button, accessible name 'Send', data-testid='send-button'. Confirmed live: disabled when the composer is empty (initial snapshot shows button 'Send' [disabled]), becomes enabled once text is typed, clicked successfully via getByTestId('send-button').click().
  4. User message in the transcript
    - expect: observed: container div, data-testid='message-user', no explicit ARIA role beyond generic — confirmed live via DOM enumeration after sending two separate messages ('Zebra crossing please' then 'Bananas are cool'); text content matched exactly what was typed in both cases.
  5. Assistant reply in the transcript
    - expect: observed: container div, data-testid='message-assistant' — confirmed live twice: sending 'Zebra crossing please' produced message-assistant text 'ZIP files are introverted folders wearing compression hoodies.' (Z-keyed reply) and sending 'Bananas are cool' produced 'Bananas are just shy yellow kayaks that never learned to swim.' (B-keyed reply), both matching src/data/funnyReplies.ts FUNNY_REPLIES_BY_LETTER exactly for the first alphabetic character of each message.

#### 1.2. Readiness / settle gates

**File:** `specs/pilot-a-s1-planner-plan.md`

**Steps:**
  1. Condition proving the app is ready to accept a send
    - expect: observed: send-button is disabled while the composer textarea is empty and becomes enabled the instant non-whitespace text is present — confirmed live by filling the textarea and re-snapshotting (button changed from 'Send' [disabled] to plain 'Send'). Additionally, both the toggle and the send/input controls are disabled while historyReady is false or while a send is in flight (source-level: ChatInput disabled={loading || !historyReady}); on this fixture historyReady flips true almost immediately after the failed GET (inference from src/components/ChatWindow.tsx, not separately timed live, but the initial snapshot already showed an enabled, non-loading composer with 'No messages yet.' placeholder, which only renders once historyReady is true — so this was observed indirectly).
  2. Condition proving the reply has fully arrived (vs. a transient loading placeholder)
    - expect: observed: immediately after clicking Send, a data-testid='loading-indicator' element (text 'Thinking...') is present and the send-button is disabled — confirmed live by clicking send and, in the same synchronous script before any extra await, querying getByTestId('loading-indicator').count() === 1 and sendBtn.isDisabled() === true.
    - expect: observed: after the exchange settles, the loading-indicator is gone, the send-button returns to its empty-composer disabled state, and exactly one new message-assistant node exists with the expected text — confirmed live in the final snapshot after each of the two sends in this session.
    - expect: verification condition: a test must assert BOTH that data-testid='loading-indicator' has count 0 AND that the specific data-testid='message-assistant' node (e.g. the last one, or matched by exact expected text) is visible with the exact expected string. Asserting only 'some assistant message text is visible' would also pass while the transcript is still showing the 'Thinking...' loading bubble layered underneath, or while showing a stale reply from a prior turn.

#### 1.3. Verification conditions a test must catch (ways it could pass while the feature is broken)

**File:** `specs/pilot-a-s1-planner-plan.md`

**Steps:**
  1. Weak content assertion
    - expect: verification condition: asserting only that a message-assistant element exists (without checking its exact text) would pass even if the reply text were wrong, empty, or the generic FALLBACK_REPLY. The assertion must compare the message-assistant text to the exact string for the first alphabetic character of the sent message, per src/data/funnyReplies.ts FUNNY_REPLIES_BY_LETTER — confirmed live for letters Z and B.
  2. Message text containing '?' silently switches code path
    - expect: verification condition (source-level, inference — src/lib/appAssistantReply.ts and src/components/ChatWindow.tsx line 'getAppAssistantReply(text) ?? getFunnyReplyContent(text)'): if the test's chosen message contains a '?' and matches one of the app-assistant keyword topics (e.g. 'reset', 'funny', 'history', 'search', 'help', 'playground', 'backend'...), the reply comes from getAppAssistantReply, NOT the first-letter table, even though funnyMode is on. A test that sends such a message and only loosely checks 'a deterministic reply appeared' would falsely pass while never exercising the first-letter-keyed behavior this scenario is actually about. The test MUST use a plain statement (no '?') that is not the exact string 'Hello there!' (which triggers a special GENERAL KENOBI + image reply, also bypassing the letter table).
  3. Naive 'first letter' computation mismatch
    - expect: verification condition (inference from src/lib/funnyReply.ts regex /[a-zA-Z]/): the app picks the first character matching [a-zA-Z] anywhere in the trimmed string, not literally message[0]. If the test message begins with a digit, punctuation, or whitespace (e.g. '123 apples'), a test that computes its expected reply from message.charAt(0) would compute the wrong expected letter and could falsely fail a correct implementation, or, worse, a hard-coded wrong expectation could falsely pass a broken implementation. Test messages should start with a plain letter to keep expected-value computation unambiguous, or the expected-value logic must replicate the same regex.
  4. False pass via mode confusion
    - expect: verification condition: if the test does not first assert the funny-mode-toggle is checked before sending, a prior test/state leak (or an accidental uncheck) could route the send through the real POST /api/chat path instead. Since no backend is running (observed: ERR_CONNECTION_REFUSED for /api/messages and, by the same code path, would occur for /api/chat), that would either surface data-testid='error-message' ("Error: failed to get AI response") or, if the text happens to match an app-assistant keyword, still produce a plausible-looking reply that is NOT letter-keyed — a loose assertion could pass on the latter for the wrong reason. The test must explicitly assert the toggle is checked (offline/funny mode) immediately before sending, and must assert data-testid='error-message' is absent after sending.
  5. Transcript ordering / stale-node false pass
    - expect: verification condition: in a transcript with more than one exchange, asserting via a generic locator like page.getByTestId('message-assistant') without scoping to the last element (or without asserting the exact new count) could match an earlier message and pass even if the newest reply is missing or wrong. The test should assert the message-user/message-assistant count increased by exactly one pair, and check the content of the LAST message-assistant node — confirmed live this app appends new turns to the end of the same list without removing prior ones.

#### 1.4. Limitations

**File:** `specs/pilot-a-s1-planner-plan.md`

**Steps:**
  1. Non-funny (real backend) mode reply content
    - expect: limitation: could not observe a successful real-backend reply live, since no backend process is running on this fixture (only the connection-refused failure path was observed). Not required for this scenario, which is scoped to offline/funny mode, but noted so it isn't confused with an 'observed' claim.
  2. historyReady timing precision
    - expect: limitation: the exact moment historyReady flips to true (and thus exactly how long the composer/toggle are disabled on initial load) was not separately measured live; this was inferred from source (src/components/ChatWindow.tsx) plus the indirect observation that the composer was already enabled with the 'No messages yet.' placeholder by the time the first snapshot was taken.
  3. Non-Latin / emoji / whitespace-only edge inputs
    - expect: limitation: behavior for messages with no a-zA-Z character (e.g. purely emoji or numeric), which per src/data/funnyReplies.ts should fall back to FUNNY_NO_LETTER_FALLACK text, was not exercised live in this session — this is inference from source only, not observed.
  4. Persistence to Message history / localStorage
    - expect: limitation: recordSuccessfulExchange (localStorage persistence) is called on every successful send per source, but was not verified live against the Message history screen in this session, since that is outside this scenario's scope (transcript display only).
