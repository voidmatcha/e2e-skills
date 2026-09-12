# Pilot A-S3 — Planner Findings (Sign-in + PDF Export capability check)

## Application Overview

This is a delta report for a single frozen, pre-approved test scenario (A-S3) against the live application at http://localhost:5174 (playwright-chat-lab, entry route `/`). Per task instructions, this document does NOT define a runnable test plan — it reports live-observed findings about whether the two capabilities the scenario depends on (sign-in / authentication, and PDF export of a conversation) actually exist in the application. No scope expansion, no additional scenarios, no fixtures or stubs were introduced. Where a capability was found to be missing, no workaround was invented.

## Test Scenarios

### 1. Scenario A-S3 — Delta Findings (No runnable steps: blocking capability gaps found)

**Seed:** `e2e/seed.spec.ts`

#### 1.1. A-S3: Signed-in user exports conversation as PDF from chat screen — CAPABILITY GAP REPORT

**File:** `specs/pilot-a-s3-planner-plan.md`

**Steps:**
  1. [observed] Navigated to http://localhost:5174/ (fresh context). Page loaded with title 'Playwright Chat Lab'.
    - expect: observed: Page snapshot shows a banner (button 'Go to the chat screen', heading 'Playwright Chat Lab'), a Main navigation with exactly 5 links — 'Chat' (/), 'Search' (/search), 'Message history' (/history), 'Playground' (/playground), 'Help' (/help) — and the chat panel itself (checkbox 'Assistant mode Funny mode', placeholder text 'No messages yet.', button 'Help', textbox 'Type a message…', button 'Send' [disabled], button 'Reset Chat'). No user menu, avatar, account control, or sign-in/log-in link/button is present anywhere in this snapshot.
  2. [observed] Attempted direct navigation to http://localhost:5174/login to check for a dedicated sign-in route reachable from the app.
    - expect: observed: The app rendered the identical chat-screen snapshot as '/' (same banner, nav, chat panel) — i.e. '/login' does not exist as a distinct page and the app silently falls back to the chat screen. No sign-in form, credential fields, or auth-related control appeared.
  3. [inference] Read src/App.tsx (React Router route table) to corroborate the live observation.
    - expect: inference: Route table is exactly: '/' -> ChatPage, '/search' -> SearchChatsPage, '/history' -> HistoryPage, '/playground' -> PlaygroundPage, '/help' -> HelpPage, and a wildcard '*' -> <Navigate to="/" replace />. There is no '/login', '/signin', '/account', or any authentication route defined anywhere in the router, confirming the observed redirect behavior and confirming no client-side auth route exists to add later without a code change.
  4. [observed] Inspected the Help page (http://localhost:5174/help) for any mention of sign-in or export/PDF, since it lists 'Common issues and quick fixes'.
    - expect: observed: Help page lists exactly 5 collapsible topics: '"Error: failed to get AI response"', 'Blank chat or missing past messages', 'Message history or search looks empty', 'Cannot send a message', 'Reset Chat does not clear history'. None of the topic titles reference sign-in, authentication, export, download, or PDF.
  5. [inference] Read src/pages/ChatPage.tsx and src/components/ChatWindow.tsx (the full chat-screen implementation) to check for any export/PDF/print/download affordance, since none was visible in the rendered snapshot.
    - expect: inference: ChatWindow.tsx renders only: a funny/assistant mode toggle (checkbox, data-testid='funny-mode-toggle'), the scrollable message list (or a 'Loading…' / 'No messages yet.' placeholder), an optional inline error message, a 'Help' suggestion button (data-testid='help-suggestion'), the ChatInput component (textbox + Send button), and a 'Reset Chat' button (data-testid='reset-button'). There is no export button, no download link, no print trigger, no menu, and no PDF-related code anywhere in this component or its imports.
  6. [verification condition] (a) Sign-in / authentication capability reachable from `/`: NOT PRESENT. Exact missing control: there is no button, link, or menu item anywhere in the app shell (banner or nav) with an accessible name resembling 'Sign in', 'Log in', 'Account', or similar, and no dedicated route serves a credential form. A test asserting 'the user signs in' has no real control to interact with and must fail this precondition rather than proceed.
    - expect: verification condition: If a future implementation adds sign-in, the test must locate and assert on the specific real control (e.g. button role with accessible name 'Sign in') rather than assuming one; until then, any step claiming to 'sign in' is unimplementable against this app and must be reported as a failed precondition, not silently skipped or faked.
  7. [verification condition] (b) PDF export of the conversation from the chat screen: NOT PRESENT. Exact missing control: no button/menu/link exists anywhere in the chat screen (or in Search, History, Playground, or Help) with an accessible name resembling 'Export', 'Download', 'Export as PDF', 'Print', or similar, and no code path in ChatWindow.tsx, ChatInput, or ChatMessage triggers a browser download or print dialog.
    - expect: verification condition: A test must NOT substitute Playwright's own `page.pdf()` API, a stubbed/mocked download event, or any fixture-injected file as a stand-in for this missing feature — doing so would validate Playwright itself, not an application capability. The correct outcome for Scenario A-S3 as currently written is a reported capability gap / blocked precondition, not a passing (faked) test.
  8. [limitation] Backend dependency observed but not explorable further: the app attempted to call http://localhost:3001/api/messages on load and received net::ERR_CONNECTION_REFUSED (no backend server running). This did not block rendering (the app falls back to local/'funny mode' behavior) but means any server-persisted history, auth session, or export feature that might hypothetically live only on that backend could not be observed or ruled out from the frontend alone.
    - expect: limitation: Could not verify whether the (currently unreachable) backend at localhost:3001 exposes any auth or PDF-export endpoint. This assessment is scoped strictly to what is reachable and observable from the live frontend at http://localhost:5174/ per the task's origin restriction; the frontend itself exposes no UI to reach or exercise any such endpoint even if one existed.
  9. [verification condition] Overall conclusion for Scenario A-S3 as frozen.
    - expect: verification condition: Both preconditions required by the scenario's 'When'/'Then' (a signed-in user; a PDF export action) are unimplementable against the live application in its current state. Recommended handling: mark Scenario A-S3 as BLOCKED / not executable, citing this report, rather than writing Playwright steps that assert on non-existent controls or that fabricate the missing capability.
