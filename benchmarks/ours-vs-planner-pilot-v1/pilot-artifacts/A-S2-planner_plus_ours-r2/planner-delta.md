# Planner delta ledger — Scenario A-S2 (cell A-S2-planner_plus_ours-r2)

Planner: first-party `playwright-test-planner` subagent (`.claude/agents/playwright-test-planner.md`),
MCP server `playwright-test`.

**Admission gate: PASSED.** The delegated planner confirmed it could see both `planner_setup_page`
and `planner_save_plan`, and its browser launched and loaded `http://localhost:5174/`
(page title "Playwright Chat Lab"). `planner_status: READY`.

Planner plan file: `specs/pilot-a-s2-planner-plan.md` (saved by the planner via `planner_save_plan`).

Frozen scope preserved: exactly one scenario (A-S2), entry route `/`, no new scenarios proposed.

## Classification and disposition

| # | Delta (abridged) | Planner label | Verified label | Disposition |
|---|---|---|---|---|
| 1 | Fresh `/` shows "No messages yet."; Send disabled with empty input | observed | observed (independently observed in our Step 3 exploration) | ABSORBED — used as the Given-state guard |
| 2 | Send transitions disabled→enabled once the textbox has content | observed | observed (corroborates our exploration) | ABSORBED — corroboration; not asserted (outside the frozen Then) |
| 3 | Sending issues no network request; only the pre-existing failing `localhost:3001/api/messages` GETs at load | observed | observed (corroborates: Funny mode is fully client-side) | ABSORBED — evidence for the V4 rationale (write seam is `localStorage`, not the network) |
| 4 | "Assistant reply text is randomized — do not hardcode it; assert only non-empty content" | verification condition | **inference (refuted)** | DECLINED — the planner compared replies to two *different* messages. Live counter-evidence this session: the same input `Persistence check one` in two fresh page loads produced the identical reply `Programmers don’t panic; we just \`console.log\` our feelings.` (`identical: true`). Funny mode maps the first letter of the message to a canned reply. Accepting this delta would have weakened the primary assertion to a non-empty check. |
| 5 | Stored `id` is a fresh UUID composite — must not be asserted verbatim | observed | observed | ABSORBED — the candidate asserts no storage internals at all |
| 6 | `/history`: h2 "Message history", button "Delete history" (enabled when entries exist), level-3 day heading, `list`/`listitem` with time + "You"/message + "Assistant"/reply | observed | observed (independently resolved: `getByRole('button', { name: 'Delete history' })` count 1, `getByRole('listitem')` count 1 populated / 0 empty) | ABSORBED — locator evidence agrees with our Locator Mapping Table |
| 7 | Do not assert the exact clock time or the date heading as a fixed literal | verification condition | verification condition | ABSORBED — candidate asserts neither |
| 8 | A real `page.reload()` on `/history` preserves storage and re-renders the identical listitem | observed | observed | ABSORBED — this is the V1 primary outcome |
| 9 | Must wait for the listitem to be visible after navigation/reload (client-rendered SPA); no fixed sleeps | verification condition | verification condition | ABSORBED — web-first retrying assertions only, no `waitForTimeout` |
| 10 | Reloading/revisiting Chat `/` resets its live transcript to "No messages yet." — the persistence assertion must be made on `/history`, not on Chat | observed / limitation | observed (independently observed: navigating back to `/` clears the thread while storage still holds the exchange) | **ABSORBED — load-bearing.** Without it, the reload assertion would be made on a screen that never restores its thread and the test would falsely fail. |
| 11 | "Delete history" opens a native `confirm()` with exact text "Delete all message history stored in this browser? This cannot be undone." | observed | observed (same string captured in our session) | ABSORBED — the dialog message is asserted in the handler |
| 12 | A dialog handler must be registered before/at the click or the test hangs | verification condition | verification condition | **ABSORBED — load-bearing.** Registered via `page.once('dialog', …)` before the click. |
| 13 | Dismissing the confirm dialog leaves storage and the listitem unchanged — add as a negative-path guard | observed | observed, but **scenario-changing** | **RETURNED_TO_APPROVAL_GATE — not applied.** The frozen Then covers only "clearing history removes it"; asserting the cancel path adds product behaviour the approved scenario does not name. Recorded for a human approval gate. |
| 14 | Accepting the dialog: storage key becomes `null`, list/day heading disappear, "No history yet. …" appears, Delete button becomes disabled | observed | observed | ABSORBED — the clearing half of the Then |
| 15 | Assert both the positive empty-state message AND the absence of the previously asserted user message text, not merely absence of the day heading | verification condition | verification condition | **ABSORBED — load-bearing.** Adds a failure condition the plan lacked: a regression that hides the day heading while leaving the exchange rendered would otherwise pass. Implemented as `toHaveCount(0)` on the entries + `not.toBeVisible()` on the sent text + empty-state visible + Delete button disabled. |
| 16 | Delete clears only `ai-assistant-chat-history-v1`; `chat-lab:theme` is unaffected — guard against clear-all-storage regressions | observed | observed, but out of frozen scope | DECLINED — asserts a `localStorage` implementation detail with no user-visible seam in the approved Then. Not applied. |
| 17 | Use a unique/run-specific token in the message text to avoid cross-retry collisions | inference / verification condition | inference | DECLINED — each Playwright test gets a fresh browser context with empty storage (verified: the candidate asserts `toHaveCount(0)` on entries in the Given state and it holds on repeat runs). A run-specific token would also make the asserted user text non-deterministic for no gain. |
| 18 | Pre-existing failing `http://localhost:3001/api/messages` requests occur on every load; do not assert "no console errors"/"no failed requests" globally | limitation | limitation | ABSORBED — candidate makes no console/network-cleanliness assertion |

## Totals

- 18 deltas returned by the planner.
- absorbed: 14 (#1, #2, #3, #5, #6, #7, #8, #9, #10, #11, #12, #14, #15, #18)
- returned_to_approval_gate: 1 (#13)
- declined: 3 (#4, #16, #17)

## New verification conditions absorbed (failure conditions the deltas added)

- **#10** — "the reload-persistence check must be performed on `/history`, not on the Chat screen":
  load-bearing because the Chat route discards its in-memory transcript on remount, so the same
  assertion placed on `/` would fail against a correct application.
- **#12** — "a `dialog` handler must be registered before the Delete click": load-bearing because
  without it the click never settles and the clearing half of the scenario can never be observed.
- **#15** — "after clearing, assert the empty state AND the absence of the previously asserted
  message text": load-bearing because it adds a failure condition the original plan lacked — a
  regression that removed only the day-group heading while still rendering the exchange would have
  passed an empty-state-only assertion.

## Honesty notes

- No planner delta supplied a capability the application does not have; every absorbed delta was
  independently re-observed on the live page in this session before use.
- No inferred locator reached the final test. Every locator in the candidate was resolved against
  the live page (role/name/state probes recorded in the Step 4 Locator Mapping Table).
- The planner's browser ran under the same approved loopback fixture. Its MCP tool surface exposes
  no `context.route()`-level hook, so its navigation had no before-dispatch origin guard; it was
  constrained by instruction to `http://localhost:5174` only, and its own report lists no off-origin
  navigation. Our own exploration ran with an installed before-dispatch guard.
