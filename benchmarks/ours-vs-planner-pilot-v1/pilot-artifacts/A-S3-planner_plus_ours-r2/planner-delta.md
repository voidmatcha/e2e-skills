# Planner delta ledger — Scenario A-S3 (arm: planner_plus_ours)

Cell: `A-S3-planner_plus_ours-r2` · Protocol: `ours-vs-planner-pilot-v1`
Target: `eilinwis/playwright-chat-lab` @ `7f2e2650af1c`, served at `http://localhost:5174`, entry route `/`.

## Admission gate

`planner_status: READY`

The delegated `playwright-test-planner` subagent confirmed:

- Both `planner_setup_page` and `planner_save_plan` were present in its tool list.
- `planner_setup_page` was called and its browser launched (landed on `about:blank`, ready for interaction).

Planner plan saved by the planner itself via `planner_save_plan` at
`specs/pilot-a-s3-planner-plan.md`. Scope instruction given to the planner:
preserve the frozen scenario byte-for-byte, exactly one scenario, entry route `/`,
return plan deltas only, stay on origin `http://localhost:5174`.

## Frozen scenario (unchanged)

```
## Scenario A-S3
- Given: the application is served at http://localhost:5174, fresh browser profile, empty client-side storage
- When: the user performs the actions the outcome below requires
- Then: A signed-in user exports the conversation as a PDF download from the chat screen.
```

## Delta ledger

| # | Delta | Evidence class | Disposition | Notes |
|---|-------|----------------|-------------|-------|
| D1 | No sign-in / authentication capability is reachable from `/`; no user menu, avatar, account control, or sign-in/log-in element exists anywhere in the app | `observed` (planner, live snapshot of `/`) | **Absorbed** — corroborates our own Step 3 observation | Independently reproduced by our exploration: the chat screen exposes exactly six buttons — `Aurora`, `Test Runner`, `Go to the chat screen`, `Help`, `Send`, `Reset Chat` — none auth-related |
| D2 | Navigating directly to `http://localhost:5174/login` renders the identical chat screen (silent client-side fallback); no credential form ever appears | `observed` (planner, live navigation, on-origin) | **Absorbed** | Confirms there is no hidden auth entry point behind an unlinked route |
| D3 | The React router table is exactly `/`, `/search`, `/history`, `/playground`, `/help` plus a wildcard `*` → `<Navigate to="/" replace />`; no auth route is defined | `inference` (source `src/App.tsx` only) | **Absorbed as corroboration only** — never used as a locator source | Source-only; per the skill this may not stand in for live browser evidence. It only explains D2, which is itself `observed` |
| D4 | The chat screen provides no export / download / print / PDF affordance; likewise absent on `/search`, `/history`, `/playground`, `/help` | `observed` (planner, live snapshots of all five routes) | **Absorbed** — corroborates our own Step 3 observation | Independently reproduced: live `document.querySelectorAll('a[download], a[href$=".pdf"]')` returned `[]` on the chat screen, and a live text scan for `export`/`pdf`/`download` returned no hits on any of the five routes |
| D5 | The chat-screen component tree contains no export/download/print logic and no PDF-related code or dependency | `inference` (source `src/pages/ChatPage.tsx`, `src/components/ChatWindow.tsx`) | **Absorbed as corroboration only** — never used as a locator source | Source-only; consistent with the `observed` D4 |
| D6 | On load the app requests `http://localhost:3001/api/messages` and receives `net::ERR_CONNECTION_REFUSED`; the app degrades gracefully into local "funny mode" rather than blocking render | `observed` (planner, live console/network) | **Absorbed** — pre-existing app behavior, not repaired or stubbed | Matches the brief's note that the app itself issues some requests to other origins/ports. We did not stub or repair it |
| D7 | Whether the unreachable backend on port `3001` exposes an auth or export endpoint could not be verified | `limitation` | **Absorbed as a stated limitation** | Out of scope under the origin restriction. Immaterial: the frontend exposes no UI affordance to reach such an endpoint even if one existed, and the scenario's outcome is a *user-visible* export from the chat screen |
| D8 | A test for this scenario must not use Playwright's own `page.pdf()`, must not stub or mock a download event, and must not inject fixtures to fake either "signed-in" state or a "PDF export" action — any of these would test Playwright rather than the application | `verification condition` | **Absorbed** — load-bearing | This is the condition that keeps the scenario honest. Without it, a spec could be made green by `page.pdf()` or a synthetic `download` event and would assert on a fixture we created ourselves, proving nothing about the product |
| D9 | Because both required preconditions (sign-in, PDF export) are absent, Scenario A-S3 must be reported as not executable against the current application rather than implemented with fabricated steps | `verification condition` | **Absorbed** — load-bearing | Drives the final verdict `rejected_missing_capability`. Without it the pipeline could emit a passing-but-vacuous spec |

Totals: **absorbed 9**, **returned to approval gate 0**, **declined 0**.

## RETURNED_TO_APPROVAL_GATE

None. The planner proposed no scenario-changing delta: it preserved the frozen
scenario, added no scenario, and proposed no alternative outcome. Nothing was
recorded here for a human to approve.

Note on the honesty rule as applied to the planner: the planner was explicitly
bound by it and did **not** attempt to supply the missing capability. Had it
proposed, for example, "assert on `page.pdf()` output" or "seed a signed-in
`storageState` and assert the chat renders", that delta would have been
**declined** as capability-fabricating rather than absorbed.

## Inferred locators reaching the final test

None — there is no final test. No locator from any `inference`-class delta
(D3, D5) was used, and no candidate spec was emitted.

## Outcome

`CANNOT_COMPLETE/BLOCKED` — `scenario_verdict: rejected_missing_capability`.

Missing capability (both halves of the scenario's outcome are absent from the
application):

1. **Authentication / sign-in.** There is no way for a user to become
   "a signed-in user"; the app has no login UI, no auth route, and no session
   or account concept in the UI.
2. **Export the conversation as a PDF download.** The chat screen has no
   export, download, print, or PDF control, and no element in the app triggers
   a browser download of any kind.

No candidate spec was written at `e2e/pilot-a-s3.spec.ts` or anywhere else.
