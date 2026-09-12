# A-S2 Plan-Hardening Deltas (Message send -> reload -> history persistence -> delete)

## Application Overview

Auxiliary plan-hardening pass for a single frozen scenario (A-S2) of the Playwright Chat Lab app at http://localhost:5174. This file contains ONLY delta findings (gates, locators, dialog handling, verification conditions, limitations) gathered by exploring the live app, not a new/expanded test plan. Every delta below is labeled observed / inference / verification condition / limitation per the task's evidence rules.

## Test Scenarios

### 1. A-S2 Plan Hardening Deltas

**Seed:** `e2e/seed.spec.ts`

#### 1.1. Scenario A-S2 - Send message, reload, verify history persistence, clear history (hardened deltas)

**File:** `specs/pilot-a-s2-planner-plan.md`

**Steps:**
  1. [observed] Navigate to http://localhost:5174/ on a fresh profile.
    - expect: Chat screen loads with textbox role=textbox name="Type a message…" (empty) and button role=button name="Send" in a [disabled] state; paragraph "No messages yet." is shown.
    - expect: [observed] Pre-existing background failures to http://localhost:3001/api/messages (ERR_CONNECTION_REFUSED) fire on every full navigation/reload; these are unrelated noise per task instructions and must not be stubbed, repaired, or waited on.
  2. [observed] Fill the textbox role=textbox name="Type a message…" with a deterministic, test-controlled string (e.g. "Hello test message A-S2").
    - expect: [observed] The Send button (role=button name="Send") transitions from disabled to enabled only once the textbox has non-empty content. GATE: implementation must assert/wait for Send to be enabled before clicking rather than clicking immediately after fill.
  3. [observed] Click the Send button (role=button name="Send").
    - expect: [observed] Immediately (no visible loading state was observed) two new elements appear in the chat panel: the user's exact submitted text, and an assistant reply (sample observed: "Historians agree: the first bug was a literal beetle with opinions."). The Send button returns to a [disabled] state (input cleared).
    - expect: [verification condition] Assert on the exact user-submitted text (deterministic). Do NOT assert a specific hardcoded assistant reply string as a hard requirement — [inference] the checked checkbox role=checkbox name="Assistant mode Funny mode" suggests replies may be randomized/varied across runs; only a single sample was observed live so treat assistant-reply text as informational, not a strict equality check, unless a second run is used to confirm determinism.
    - expect: [observed] The exchange is written to localStorage key `ai-assistant-chat-history-v1` as a JSON array entry (fields observed: id, userContent, assistantContent, userTimestamp, assistantTimestamp) immediately after send — this is the persistence mechanism under test and can optionally be asserted directly for a stronger check.
  4. [observed] Click the "Message history" nav link (role=link name="Message history", href=/history).
    - expect: [observed] URL becomes http://localhost:5174/history. Page shows heading role=heading name="Message history", a date-grouped heading (role=heading level=3, e.g. "Friday, September 11, 2026") followed by a list (role=list) containing a listitem with the time, "You" label + the exact submitted user text, and "Assistant" label + reply text.
    - expect: [verification condition] Locator should target the listitem by its exact user message text content, NOT by the date/time heading text, since date and time are run-dependent and not stable across test executions.
  5. [observed] Reload the page while on http://localhost:5174/history (full navigation reload, not client-side route change).
    - expect: [observed] After reload, the same listitem (time, You/user text, Assistant/reply text) is still present under the same date heading — confirms client-side (localStorage-backed) persistence survives a full reload specifically on the /history route.
    - expect: [observed][limitation] Reloading the CHAT screen (/) instead does NOT restore the prior conversation into the chat panel itself — it resets to paragraph "No messages yet." even though localStorage still holds the record and /history still lists it. GATE: the scenario's post-reload assertion must be scoped to the Message History screen (navigate to or reload while on /history); asserting persistence by reloading and inspecting the Chat screen would incorrectly fail.
  6. [observed] Click the "Delete history" button (role=button name="Delete history").
    - expect: [observed] A native browser confirm() dialog appears with the exact message "Delete all message history stored in this browser? This cannot be undone." GATE: this requires explicit dialog handling (e.g. registering a dialog handler before the click, or Playwright's browser_handle_dialog equivalent); a plain click() with no dialog handler will hang/timeout — this dialog is not implied by the frozen scenario wording and must be added as an explicit step.
    - expect: [limitation] The dismiss/cancel path of this dialog was not exercised live in this session (only accept was tested); cancel-path behavior (history presumably remains) is unverified and out of scope for the frozen scenario, which only requires the accept-and-clear path.
  7. [observed] Accept the confirm dialog.
    - expect: [observed] The listitem/date-group content is removed and replaced with paragraph text "No history yet. Send a message in Chat to build your archive."; the "Delete history" button itself becomes [disabled] since there is nothing left to delete.
    - expect: [verification condition] Assert all three: (a) the specific message text/listitem is no longer present, (b) the empty-state paragraph "No history yet. Send a message in Chat to build your archive." is visible, and (c) optionally, localStorage.getItem('ai-assistant-chat-history-v1') is null — [observed] this was confirmed to be null via page.evaluate immediately after accepting the dialog.
  8. [observed][limitation] Note on a similarly-named but distinct control: the Chat screen (not History screen) has its own button role=button name="Reset Chat". This is a different control on a different screen from "Delete history" and must not be confused with it in locators; its exact effect on persisted /history data was not verified live in this session.
    - expect: No action required for scenario A-S2 — flagged only to prevent locator ambiguity between "Reset Chat" (Chat screen) and "Delete history" (History screen).
