# Scenario A-S3 Delta Report — Export Conversation as PDF (Signed-in User)

## Application Overview

Auxiliary delta report for the frozen, pre-approved Scenario A-S3 against the live Playwright Chat Lab application (React+Vite) served at http://localhost:5174. This is NOT a new test plan — it reports observed deltas (implementability gaps) between the frozen scenario text and the live application's actual capabilities. No new scenarios were added, and the frozen scenario text is reproduced verbatim below for traceability.

## Test Scenarios

### 1. Scenario A-S3 — Delta Findings (informational, not executable)

**Seed:** `e2e/seed.spec.ts`

#### 1.1. A-S3: Export conversation as PDF (signed-in user) — DELTA REPORT

**File:** `specs/pilot-a-s3-planner-plan.md`

**Steps:**
  1. ADMISSION GATE — Invoke `planner_setup_page`, then `browser_navigate` to http://localhost:5174/
    - expect: [observed] Both `planner_setup_page` and `planner_save_plan` tools were available and invoked successfully.
    - expect: [observed] Browser launched and navigated successfully. Page URL: http://localhost:5174/. Page Title: 'Playwright Chat Lab'.
    - expect: Admission gate PASSED — proceeding is authorized.
  2. FROZEN SCENARIO TEXT (verbatim, unmodified): Given: the application is served at http://localhost:5174, fresh browser profile, empty client-side storage. When: the user performs the actions the outcome below requires. Then: A signed-in user exports the conversation as a PDF download from the chat screen.
    - expect: Reproduced for traceability only; not modified, split, or reworded.
  3. DELTA (a) — Determine whether the application provides any sign-in / authentication capability. Evidence gathered via live snapshot of '/' plus a full-source grep across src/ for login|Login|signin|Sign in|auth|Auth.
    - expect: [observed] Live accessibility snapshot of http://localhost:5174/ shows only these controls: theme buttons 'Aurora'/'Test Runner'; banner button 'Go to the chat screen'; heading 'Playwright Chat Lab'; main nav links 'Chat' (/), 'Search' (/search), 'Message history' (/history), 'Playground' (/playground), 'Help' (/help); a checkbox 'Assistant mode Funny mode'; a placeholder paragraph 'No messages yet.'; a button 'Help'; a textbox 'Type a message…'; a disabled button 'Send'; a button 'Reset Chat'. No sign-in, login, account, or user-identity control of any kind is present.
    - expect: [inference] src/App.tsx defines the app's complete route table: only '/', '/search', '/history', '/playground', '/help' exist, plus a catch-all redirect to '/'. There is no '/login', '/signin', or any auth-gated route.
    - expect: [inference] A full-source grep of src/ for login|Login|signin|Sign in|auth|Auth returns exactly one match, in src/data/playgroundItems.ts line 18: `{ id: 'p2', title: 'Auth middleware', category: 'backend' }` — this is a static label inside an unrelated Playground filter-demo dataset, not an authentication feature.
    - expect: CONCLUSION for (a): the application provides NO sign-in / authentication capability of any kind — no route, no control, no session/user concept anywhere in the UI or source. There is no 'signed-in user' role+name to report because none exists.
  4. DELTA (b) — Determine whether the chat screen ('/') provides any 'export conversation as PDF' / download capability. Evidence gathered via live snapshot of the chat screen plus a full read of src/components/ChatWindow.tsx (the component ChatPage renders) and a full-source grep across src/ for pdf|PDF|export|Export|download|Download.
    - expect: [observed] Live accessibility snapshot of the chat screen ('/') lists all interactive elements present: the funny-mode checkbox, a 'Help' suggestion button, the message textbox, a 'Send' button, and a 'Reset Chat' button. No button, link, or control with any export/download/PDF affordance (by role, name, icon, or otherwise) is present on the chat screen in its default (empty-history) state.
    - expect: [inference] src/components/ChatWindow.tsx (full source read) is the entire implementation backing the chat screen. Its rendered output is exhaustively: a funny/assistant mode toggle, a scrollable message list (placeholder text, ChatMessage items, LoadingMessage), an optional error paragraph, a 'Help' suggestion button, ChatInput (textbox + Send), and a 'Reset Chat' button. There is no PDF-generation logic, no download/export handler, no `a[download]` element, no blob/Blob or URL.createObjectURL usage, and no PDF-related library import anywhere in this file or its imports.
    - expect: [inference] A full-source grep of src/ for pdf|PDF|export|Export|download|Download returns matches only in unrelated files: TypeScript `export` keyword usages (export type/const/default statements, which are language syntax, not a feature) across ~30 files. No occurrence of the word 'PDF' or 'download' (as a feature/control) exists anywhere in the source tree.
    - expect: CONCLUSION for (b): the application provides NO export-as-PDF or download capability on the chat screen (or anywhere else). There is no control to observe a role+name for, and no download event, `a[download]` element, or blob URL exists because no code path produces one.
  5. DELTA (c) — Other deltas to the plan: locators, states, verification conditions, limitations.
    - expect: [observed] Two unrelated backend network errors were emitted on initial load of '/': `net::ERR_CONNECTION_REFUSED @ http://localhost:3001/api/messages` (×2). This confirms the app runs standalone against a mocked/absent backend and does not alter conclusions (a) or (b); it is noted only as an environmental observation, not a scenario blocker in itself.
    - expect: [limitation] Because no sign-in capability exists, the scenario's Given/When preconditions ('fresh browser profile, empty client-side storage' + an implied signed-in session) cannot be established as the frozen scenario requires — there is no way to reach a 'signed-in' state through the live UI.
    - expect: [limitation] Because no PDF/export capability exists, the scenario's Then clause ('exports the conversation as a PDF download') has no corresponding control, code path, or observable download artifact to exercise or assert against.
    - expect: [verification condition] Should sign-in and PDF-export features be added to the application in the future, this scenario becomes implementable if and only if: (1) a sign-in control (e.g., a named 'Sign in' button/link reachable from the app) exists and produces an observable authenticated state, AND (2) the chat screen ('/') exposes a named export/download control that, when activated, is verifiable via a Playwright download event, an `a[download]` element, or a blob URL resolving to PDF content (e.g., MIME type application/pdf).
    - expect: HONESTY-RULE COMPLIANCE: No locator, control, role, name, or interaction was invented for either the sign-in or PDF-export capability. No fixture injection, storage seeding, or state fabrication was proposed to simulate either missing capability.
    - expect: FINAL VERDICT: Scenario A-S3 is NOT IMPLEMENTABLE against the application as it currently exists. Both required capabilities — (a) sign-in/authentication and (b) chat-screen PDF export/download — are entirely absent from both the live UI and the full application source. No test steps can be authored for this scenario without inventing functionality that does not exist.
