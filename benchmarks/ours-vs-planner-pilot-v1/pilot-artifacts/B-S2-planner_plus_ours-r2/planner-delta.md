# Pilot B-S2 — planner delta reconciliation ledger

- Cell: `B-S2-planner_plus_ours-r2`, arm `planner_plus_ours`, protocol `ours-vs-planner-pilot-v1`
- Planner: first-party `playwright-test-planner` subagent (`.claude/agents/playwright-test-planner.md`), MCP server `playwright-test`
- Planner admission gate: **PASSED** — the delegated planner confirmed it could see both
  `planner_setup_page` and `planner_save_plan`, and its browser launched and loaded
  `http://localhost:5174/` (self-navigated to `/l/7QCnfrdAoWUW/untitled-layout`).
- Planner plan artifact: `specs/pilot-b-s2-planner-plan.md` (saved by the planner via `planner_save_plan`)
- Scope instruction given to the planner: PRESERVE the frozen scenario (exactly one scenario,
  entry route `/`), return plan deltas only. No scenario was added, split, or reworded.
- Implementation is mine (this skill). The planner wrote no test code.

## Classification key

- `observed` — resolved against the live page (by the planner, by me, or both)
- `inference` — source or static snapshot only
- `verification condition` — a failure condition the test must encode
- `limitation` — something the application does not do

Rule applied: an `inference`-only locator may not reach the final test. Every locator that
reached `e2e/pilot-b-s2.spec.ts` was **re-resolved by me on the live page this session**, not
taken on the planner's word.

## Ledger

| # | Delta | Label | Disposition | Notes |
|---|-------|-------|-------------|-------|
| D1 | Stash header toggle is a `button` whose accessible name is `Stash {N} bins` (e.g. `Stash 1 bins`) — a role+name locator, better than parsing the `1 bins` text node I had found | `observed` (planner) | **ABSORBED** | Re-verified by me: `getByRole('button', { name: /^Stash \d+ bins?$/ })` resolved to exactly 1 element in the post-resize state. Used in the final test. Upgrades my own L10 from tier-6 `getByText` to tier-1 role+name. |
| D2 | Stash bin card is a `button` with accessible name `1×1` inside `#staging-stash-panel` | `observed` (planner; also observed by me independently) | **DECLINED** | Superseded. `1×1` is a size label shared by every 1×1 bin and proves nothing about *which* bin moved. The final test uses `[data-staging-bin-id="<captured id>"]`, which proves identity continuity. |
| D3 | `[role="application"]` aria-label format is `Gridfinity drawer grid, {N} columns by {M} rows` and updates with the resize | `observed` (planner, confirming mine) | **ABSORBED** | Confirmatory. Used as the settled-state gate before the primary assertion. |
| D4 | `[data-stash]` carries `role="status"` **only while empty**; once populated the header is a plain `div`/`button` with no live-region role | `observed` (planner) | **ABSORBED** | Re-verified by me: `[data-stash]` had no `role` attribute in the populated state. Prevents asserting on a live region that is removed exactly when the event fires. |
| D5 | After a displacing resize there is **no** `[role="status"]`, `[role="alert"]`, or `[aria-live]` element anywhere on the page — no toast, no ARIA announcement | `observed` + `limitation` | **ABSORBED** | Re-verified by me: the query returned `[]` in the settled post-resize state. Load-bearing honesty constraint — the "reported" half of the outcome must be asserted structurally (bin leaves `[data-bin-id]`, same id appears under `[data-staging-bin-id]`, stash count changes). No toast assertion was invented. |
| D6 | The resize is not debounced; grid aria-label, `[data-bin-id]` set and stash contents settle synchronously once the click resolves | `observed` | **ABSORBED** | No `waitForTimeout` in the final test; web-first assertions carry the wait. |
| D7 | The header autosave "Saving…"/"Saved" status is transient and disappears on its own — must not be used as a synchronisation signal | `observed` | **ABSORBED** | Not used. (I had transiently seen `["Saved"]` from a `[role="status"]` query right after the click; D7 explains it and correctly rules it out as a gate.) |
| D8 | Background `POST /api/ml-telemetry` returns 404 and logs console errors, unrelated to this flow | `observed` | **ABSORBED** | No console-error assertion in the final test; it would be flaky and wrong. Also recorded as V4 evidence that this flow has no server write of its own. |
| D9 | Control condition: a bin at the anchored edge (column 1 for a width shrink) must **not** be displaced and must keep its `[data-bin-id]` presence | `observed` + `verification condition` | **ABSORBED** | New failure condition encoded in the test (`keptBinId` stays on the grid). |
| D10 | Same-id continuity: the displaced bin's `[data-staging-bin-id]` equals its pre-resize `[data-bin-id]` | `observed` + `verification condition` | **ABSORBED** | Confirmed independently by me in two trials. The primary assertion is keyed on the captured id. |
| D11 | Width truncates from the **high-index (right)** edge, but depth truncates from the **low-index (top, CSS row 1)** edge — the opposite convention; a depth case must probe row 1, not the last row | `observed` + `verification condition` | **RETURNED_TO_APPROVAL_GATE** | Adding a depth-axis case would change the frozen scenario's `When`. Recorded, **not applied**. There is no human in this session to approve the expansion. |
| D12 | Depth decreases mostly renumber bins in place rather than displacing them; "near the resized edge" ≠ "displaced" | `observed` + `limitation` | **RETURNED_TO_APPROVAL_GATE** (with D11) | Same reason as D11 — only relevant to a depth case that is outside the frozen scope. Recorded, not applied. |

## Tallies

- Absorbed: **9** (D1, D3, D4, D5, D6, D7, D8, D9, D10)
- Returned to approval gate (recorded, never applied): **2** (D11, D12)
- Declined: **1** (D2)

## New verification conditions absorbed

1. **A still-fitting bin must remain on the grid after the resize (D9).** Without it the test stays
   green against a regression that stashes every bin (or clears the layer) on any dimension change —
   the assertion "something is in the stash" alone is nearly vacuous.
2. **The stashed bin must be the *same* bin, keyed on the id captured before the resize (D10).**
   Without it, an app that deletes the non-fitting bin and leaves an unrelated or stale entry in the
   stash would still pass; identity continuity is what makes "reported rather than silently kept"
   checkable.
3. **No toast or ARIA live region exists for this event, so the report must be proven structurally (D5).**
   This is load-bearing in the negative direction: it is the condition that forbids an invented
   `getByText(/moved to stash/i)` assertion, which would have been a fabricated locator that never
   resolves.

## Honesty note

The planner supplied no capability the application does not have. Its single most valuable
contribution (D5) was a *negative* finding that removed a tempting fabrication, and its second
(D9/D10) tightened the failure conditions the test encodes. D11/D12 are real and correct but
scenario-changing, so they are recorded here and left unapplied.
