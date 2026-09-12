# Pilot B-S3 Hardening — Plan Deltas

## Application Overview

Auxiliary "harden the plan" pass for Scenario B-S3 (unauthenticated cross-browser-profile Cloud Sync) against the Gridfinity Planner & Layout Tool running at http://localhost:5174. This document reports whether the app supports the exact outcome described, with every claim labelled observed / inference / verification condition / limitation. No test files were created; this is a findings-only delta document as instructed.

## Test Scenarios

### 1. B-S3 Findings

**Seed:** `e2e/seed.spec.ts`

#### 1.1. B-S3 verdict and evidence

**File:** `specs/pilot-b-s3-planner-plan.md`

**Steps:**
  1. ADMISSION GATE
    - expect: observed: Both planner_setup_page and planner_save_plan tools were available and callable in this session.
    - expect: observed: planner_setup_page returned a live Playwright page (about:blank) confirming the browser launched successfully.
    - expect: observed: Navigating to http://localhost:5174 loaded the app (Page Title: 'Gridfinity Planner & Layout Tool — Free Online Drawer Organizer', URL redirected to /l/Yz8qY8cgMjWt/untitled-layout).
  2. Explore fresh-state entry route and toolbar for any sharing/sync affordance
    - expect: observed: On fresh load with empty storage, the toolbar exposes a status region that briefly reads 'Saved' (role=status), a button with accessible name 'Share layout', and a button with accessible name 'Open settings'. No sign-in control is present anywhere in the header.
  3. Click the button with accessible name 'Share layout' to inspect the sharing mechanism
    - expect: observed: A dialog opens with accessible name 'Share Layout' (role=dialog). It contains a combobox with accessible name 'Anyone with link can' (options 'Anyone with link can view' [selected] and 'Anyone with link can edit') and a button with accessible name 'Create share link'. This is a manual link-based sharing feature: a URL must be generated and then deliberately opened by a second party. No automatic, linkless cross-profile propagation is offered here.
    - expect: inference: Reading src/shell/Collab/CollabProvider/CollabProvider.tsx confirms this is the only cross-device sync path: real-time sync (Liveblocks RoomProvider) is keyed by shareId and only activates for a layout that has been explicitly shared via this dialog; there is no ambient/background sync of a layout to other browser profiles absent a share action.
  4. Click 'Open settings', then the 'Account' tab inside the resulting Settings dialog
    - expect: observed: Settings dialog (role=dialog, name='Settings') has a tab group including a tab named 'Account' under a group heading 'Account & Data'. Selecting it renders a tabpanel (id=settings-tabpanel-account) with two sections: an 'Account' heading whose content area has aria-busy="true" and never resolves (observed after an explicit 2-second wait), and a 'Cloud sync' heading whose content simultaneously displays two static text nodes, 'All changes synced' and 'Not synced yet', rendered side by side in the same row — not a single state-driven status.
    - expect: observed: No 'Sign in' button, link, or any account-identifying UI ever appears in the Account tab in this environment; the Account block is permanently stuck loading.
  5. Inspect the network call backing the Account panel
    - expect: observed: The only account-related network request was GET /api/auth/me → HTTP 200, but its response Content-Type header is 'text/javascript' and the response body is the raw TypeScript source code of the serverless handler (import statements, JSDoc, function body, and a base64 sourcemap comment) — not the JSON {authenticated, user} payload the handler is written to return.
    - expect: limitation: This proves the /api/* serverless function layer is NOT executing in this dev environment; Vite is instead serving the handler's source file verbatim. Consequently /api/auth/me can never report authenticated: true, the Settings > Account panel can never resolve out of its aria-busy loading state, and no client code path that depends on a real authenticated session (sign-in state, account-scoped cloud sync) is exercisable end-to-end here, regardless of whether sign-in itself is in scope.
  6. Check for any background room/collab connection on a fresh, unshared layout
    - expect: observed: Filtering all captured network requests (including static) for 'liveblocks' shows only local module loads (src/liveblocks.config.ts, @liveblocks_client.js, @liveblocks_react.js bundled deps) — zero requests to any Liveblocks realtime backend/room endpoint were made on the fresh /l/<id>/untitled-layout route, confirming no realtime sync session was established without an explicit share action.
  7. CRITICAL HONESTY / missing-capability finding
    - expect: verification condition: For Scenario B-S3 to be automatable as literally written, the app would need to, without any sign-in step and without the tester manually transporting a link/URL/code between two browser profiles, cause a layout edited in profile A to appear in profile B. A conforming test would need to open two independent browser contexts (fresh storage each), make an edit in context A, and then assert — via a locator resolvable purely from context B's own UI state (e.g. the grid's bin count, a layer/bin list item's accessible name, or a persisted-layout list entry) — that the edit is visible in context B, without the test itself navigating context B to a URL derived from context A or otherwise injecting the shared state.
    - expect: inference: No such mechanism exists in this codebase. The only two cross-context data paths observed/inferred are (1) the 'Share layout' dialog's generated link, which requires deliberate manual transport/opening in the second profile (explicitly disallowed as a substitute by the task), and (2) an account-based 'Cloud sync' surface in Settings > Account, which is gated on being signed in (out of scope per the task) and which, in this environment, cannot even be exercised because /api/auth/me is not executing as a real backend endpoint (limitation above) — it returns raw source text rather than an authentication JSON payload.
    - expect: verification condition: Do NOT write a test that (a) manually copies the share URL from context A into context B and calls that 'automatic sync', (b) asserts on the 'Saved' local-storage status text as a stand-in for cross-profile sync, or (c) asserts on the static 'All changes synced' / 'Not synced yet' pair in the Account tab, since that text is unconditionally present in the DOM in this environment and asserting on it would be a tautological check unconnected to any real second-profile state.
    - expect: verdict: Scenario B-S3 as written is NOT implementable in this environment. The capability it requires — unauthenticated, linkless, automatic propagation of a layout to a second browser profile — does not exist in the product (only an opt-in manual share-link exists) and, orthogonally, the one authenticated 'Cloud sync' surface that does exist cannot be verified here because the backend auth API does not execute (it serves raw source instead of JSON). Recommend removing or fundamentally rewriting B-S3 (e.g. to test the manual share-link flow explicitly, or to test account-based cloud sync against an environment where /api/* actually runs and OAuth is stubbed) rather than attempting to automate it as currently scoped.
