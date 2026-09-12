# Pilot A-S3 Planner Hardening — Capability Verification Deltas

## Application Overview

Hardening check for Scenario A-S3 against the live app at http://localhost:5174. This is NOT a full test plan — it documents evidence-classified deltas verifying whether the app supports (a) sign-in/authenticated-user concept and (b) an export-conversation-as-PDF download control on the chat screen, as required by the frozen scenario outcome: "A signed-in user exports the conversation as a PDF download from the chat screen."

## Test Scenarios

### 1. A-S3 Capability Verification Deltas

**Seed:** `e2e/seed.spec.ts`

#### 1.1. DELTA 1 (observed) — No sign-in / authenticated-user concept exists on entry route

**File:** `specs/pilot-a-s3-planner-plan.md`

**Steps:**
  1. Navigate to http://localhost:5174/ with a fresh browser profile and empty storage.
    - expect: Evidence class: observed.
    - expect: Full accessibility snapshot of the chat screen (empty state) shows only: theme toggle group (buttons 'Aurora'/'Test Runner'), banner with heading 'Playwright Chat Lab', main navigation with links Chat/Search/Message history/Playground/Help, an 'Assistant mode / Funny mode' checkbox, a 'No messages yet.' paragraph, a 'Help' button, a chat textbox, a disabled 'Send' button, and a 'Reset Chat' button.
    - expect: No login form, sign-in button, username/password fields, account menu, avatar, session indicator, or any accessible element with a name containing 'sign in', 'log in', 'account', or 'user' was present.
    - expect: Conclusion: the app has no authenticated-user concept reachable from the entry route. There is no way to represent 'a signed-in user' as a precondition.

#### 1.2. DELTA 2 (observed) — No sign-in concept on any in-app navigation route (Search, Message history, Playground, Help)

**File:** `specs/pilot-a-s3-planner-plan.md`

**Steps:**
  1. From the chat screen, click each main-nav link in turn: 'Search' (/search), 'Message history' (/history), 'Playground' (/playground), 'Help' (/help), and take an accessibility snapshot of each resulting page.
    - expect: Evidence class: observed.
    - expect: /search shows a heading 'Search', a description 'Find past questions and answers stored in this browser.', a searchbox, and an empty list — no auth control.
    - expect: /history shows heading 'Message history', description 'Conversations are saved in this browser...', a 'Delete history' button, and a grouped list of saved exchanges (by day) — no auth control, no export/download control of any kind.
    - expect: /playground shows only unrelated practice widgets: Image gallery, Video player, Calendar, Filter, Slider, Modal window, Drag and drop — no auth control, no export control. Note the Filter widget contains a static demo list item literally titled 'Auth middleware' (category tag 'backend'); this is inert sample data, not a functional authentication feature.
    - expect: /help shows an FAQ accordion with 5 items: '"Error: failed to get AI response"', 'Blank chat or missing past messages', 'Message history or search looks empty', 'Cannot send a message', 'Reset Chat does not clear history'. Expanding the first item confirms it only discusses backend/API connectivity (/api/chat, VITE_API_URL), not authentication.
    - expect: Conclusion: no route reachable from in-app navigation introduces a sign-in/auth concept.

#### 1.3. DELTA 3 (observed) — No PDF export / download control on chat screen in empty or populated state

**File:** `specs/pilot-a-s3-planner-plan.md`

**Steps:**
  1. On the empty chat screen (/), record full snapshot. Then type 'Hello, testing export' into the chat textbox and press Enter to populate the conversation with a user message and an assistant reply, and take a full snapshot again.
    - expect: Evidence class: observed.
    - expect: Empty-state chat screen controls: theme toggle, nav links, 'Assistant mode / Funny mode' checkbox, 'No messages yet.' text, 'Help' button, chat textbox, disabled 'Send' button, 'Reset Chat' button. No export, download, PDF, save, or share control present.
    - expect: Populated-state chat screen (after sending 'Hello, testing export') shows the user message and an assistant reply text ("Historians agree: the first bug was a literal beetle with opinions."), plus the same control set as the empty state: theme toggle, nav, mode checkbox, 'Help' button, chat textbox, 'Send' button, 'Reset Chat' button. No new control appeared for exporting/downloading/printing the conversation.
    - expect: Console during this flow showed 'Failed to load resource: net::ERR_CONNECTION_REFUSED @ http://localhost:3001/api/messages', indicating the backend API is not running and the app fell back to a local/offline reply — this does not introduce or reveal any export control either.
    - expect: Conclusion: there is no export-conversation-as-PDF (or any export/download) affordance on the chat screen in either state.

#### 1.4. DELTA 4 (inference) — Source code confirms no export/PDF/auth implementation exists anywhere in the app

**File:** `specs/pilot-a-s3-planner-plan.md`

**Steps:**
  1. Searched the full src/ tree (30 files: pages, components, hooks, lib, api, context, types, data) for case-insensitive matches of pdf|export|sign.?in|login|auth.
    - expect: Evidence class: inference (from source, not resolved live beyond what DELTA 1-3 already observed live).
    - expect: All 'export' matches are JavaScript/TypeScript 'export' keyword usages (module exports of functions/consts/types) — not a conversation-export feature.
    - expect: The only 'auth' match is the static string 'Auth middleware' in src/data/playgroundItems.ts, a hardcoded sample list item for the unrelated Playground 'Filter' demo widget — not a functional authentication system.
    - expect: Zero matches for 'pdf', 'sign in', or 'login' anywhere in src/.
    - expect: Conclusion: there is no PDF-generation library, no download/export handler, and no authentication module anywhere in this codebase to build such a feature on top of.

#### 1.5. VERIFICATION CONDITION — concrete red conditions for any test attempting Scenario A-S3

**File:** `specs/pilot-a-s3-planner-plan.md`

**Steps:**
  1. Document the concrete, falsifiable conditions a test author would need in order to mark Scenario A-S3 as failing/blocked rather than fabricate a pass.
    - expect: Evidence class: verification condition.
    - expect: Condition 1: A test that attempts to locate any sign-in/login control (by role 'button'/'link' with accessible name matching /sign.?in|log.?in/i, or a form with username/password fields) on http://localhost:5174/ must fail with 'element not found', since no such element exists in the current DOM/accessibility tree.
    - expect: Condition 2: A test that attempts to locate a control to export/download the conversation as PDF (e.g., role 'button' or 'link' with accessible name matching /export|download|pdf/i, or a download-triggering href/blob) on the chat screen (populated or empty) must fail with 'element not found', since no such element exists.
    - expect: Condition 3: A test that waits for a browser download event (Playwright 'download') after any interaction on the chat screen must time out, since no interaction on this screen currently triggers a file download.
    - expect: Any test plan step asserting these controls exist and function would be asserting against a false premise and must not be authored as a passing/green scenario.

#### 1.6. LIMITATION — scope of exploration and unverified areas

**File:** `specs/pilot-a-s3-planner-plan.md`

**Steps:**
  1. Note constraints on this verification pass.
    - expect: Evidence class: limitation.
    - expect: Only routes reachable via the visible in-app navigation (/, /search, /history, /playground, /help) were explored live; no other routes were probed by direct URL guessing since the task restricted exploration to in-app navigation and the chat screen.
    - expect: The backend API (expected at http://localhost:3001) was not running during this session (ERR_CONNECTION_REFUSED observed), so any hypothetical server-side-only auth or export functionality that requires a live backend (and is not represented in the frontend source or UI at all) could not be ruled out by network inspection of that backend — however, no client-side route, component, or control referencing such functionality exists in src/, so this limitation does not change the conclusion.
    - expect: Did not test keyboard-only or screen-reader-only affordances beyond what the accessibility snapshot exposes; if a hidden/undiscoverable control existed it would still fail standard Playwright role/name-based locators used in the verification conditions above.
