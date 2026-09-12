# Planner delta ledger — Scenario A-S2

`planner_status: READY`

Admission gate (per `playwright-agents.md`, "Admission gate"): the delegated
`playwright-test-planner` subagent confirmed it could see **both**
`planner_setup_page` and `planner_save_plan`, and `planner_setup_page`
(seedFile `e2e/seed.spec.ts`) launched a real browser which it then navigated to
`http://localhost:5174/`. Gate PASSED. Planner plan saved by the planner itself
via `planner_save_plan` at `specs/pilot-a-s2-planner-plan.md`.

Frozen scope was preserved: exactly one scenario (A-S2), entry route `/`, no
scenario added, split, or reworded.

**Scenario-changing deltas: 0.** Nothing the planner returned changed the
scenario count, product behavior, expected values, target-controlled commands,
or control files, so nothing was RETURNED_TO_APPROVAL_GATE.

## Ledger

| # | Delta | Class | Disposition |
|---|-------|-------|-------------|
| D1 | Composer textarea (`data-testid=chat-input`) is already enabled immediately after `page.goto()` resolves; the boot-disabled window had already passed. | observed | **Absorbed** (as a gate, not as an assumption) |
| D2 | Composer `disabled={loading \|\| !historyReady}`; `historyReady` flips only after the `fetchMessages()` call to the down `localhost:3001` settles in a `finally`. | inference | **Absorbed as rationale only** — no inferred locator reaches the test |
| D3 | Planner could not capture the transient `Loading…` / all-controls-disabled boot state; connection-refused resolves faster than its observation point. | limitation | **Superseded by our own exploration** — we *did* observe it (first post-`goto` snapshot: `paragraph: Loading…`, checkbox/textbox/Send/Reset all `[disabled]`). Recorded as observed in our mapping. |
| D4 | Tests must wait for the textarea to be **enabled**, not assume instant readiness. | verification condition | **Absorbed** → `await expect(messageInput).toBeEnabled({ timeout: 15_000 })` |
| D5 | Send (`data-testid=send-button`) carries `disabled` while input is empty; the attribute is removed once non-empty text is typed. | observed | **Absorbed** |
| D6 | `ChatInput.tsx`: `disabled={disabled \|\| !value.trim()}` — whitespace-only input keeps Send disabled. | inference | **Not absorbed** — whitespace-only input is outside the frozen scenario |
| D7 | Assert Send is **enabled** before clicking, not merely present. | verification condition | **Absorbed** → `await expect(sendButton).toBeEnabled()` before the click |
| D8 | The instant the assistant reply renders, `localStorage['ai-assistant-chat-history-v1']` already contains the new exchange (checked with no artificial delay). | observed | **Absorbed — independently reproduced by us** (`storageBeforeSend: null` → `storageWrittenByTheTimeBubbleVisible: true`) |
| D9 | `recordSuccessfulExchange` runs its synchronous `localStorage.setItem` before `finally { setLoading(false) }`, so no test-reachable window shows the reply without storage. | inference | **Absorbed as rationale only** |
| D10 | The test must wait for the assistant reply before reloading; reloading while `loading` is still true is a real race. | verification condition | **Absorbed — load-bearing** → reply-visible gate precedes `page.reload()` |
| D11 | Funny-mode's 120 ms path was timed; Assistant-mode's real-network fallback timing was not separately measured. | limitation | **Recorded** — the scenario runs in the default Funny mode, so not applicable |
| D12 | `/history`: `heading` level 2 "Message history"; day sections are level-3 headings; exchanges render as `list` / `listitem`; the inner cells (timestamp, "You", user text, "Assistant", assistant text) are unnamed `generic` divs with no distinguishing ARIA roles/names. | observed | **Absorbed** |
| D13 | With 2+ exchanges, "You"/"Assistant" text and timestamps repeat verbatim across listitems; **no** `data-testid` exists on `.history-day__item`, `.history-exchange__role`, or `.history-exchange__text` (confirmed via `outerHTML`). | observed | **Absorbed** |
| D14 | `getByText('You')`-style locators break Playwright strict mode at 2+ exchanges; scope by unique message content or `.filter({ hasText })`. | verification condition | **Absorbed — load-bearing** → history row is `getByRole('listitem').filter({ hasText: MESSAGE })` |
| D15 | Day-heading grouping uses local-time `Intl.DateTimeFormat` off `userTimestamp`; midnight-boundary behavior unexercised (needs clock manipulation). | inference / limitation | **Declined** — asserting it would require a second scenario; out of frozen scope |
| D16 | Clicking "Delete history" fires a native `confirm()` with the exact text "Delete all message history stored in this browser? This cannot be undone." | observed | **Absorbed — independently reproduced by us** (CLI reported the same modal text) |
| D17 | Accept → history clears, empty-state paragraph "No history yet. Send a message in Chat to build your archive." appears, button becomes disabled. | observed | **Absorbed — independently reproduced** (`listItems: 0`, `deleteDisabled: true`, storage `null`) |
| D18 | Dismiss → history unchanged. | observed | **Absorbed as evidence, not asserted** — dismissing is a second branch, outside the frozen scenario; it is what proves the accept is causal rather than incidental |
| D19 | The button already carries `disabled` when `exchanges.length === 0`, so no dialog fires at all in the fresh/post-delete state. | observed | **Absorbed** → used as the post-clear assertion, and as the reason the test must not click delete in the empty precondition |
| D20 | The dialog handler must be registered before/synchronously with the click or Playwright hangs; verify both the DOM state and the button-disabled state after accept, not just one signal. | verification condition | **Absorbed — load-bearing** → `page.once('dialog', …)` registered before `.click()`, plus both post-state assertions |

## Counts

- absorbed: **15** (D1, D2, D3→superseded-and-recorded, D4, D5, D7, D8, D9, D10, D12, D13, D14, D16, D17, D19, D20 — D3 counted under limitations below, so 15 absorbed)
- returned_to_approval_gate: **0**
- declined: **3** (D6, D11, D15)
- limitations recorded: **3** (D3, D11, D15)

## New verification conditions absorbed (failure condition → why load-bearing)

1. **D4/D7 — composer/Send readiness.** Failure condition added: the test can act on an inert, still-booting composer. Load-bearing because `historyReady` gates the whole composer behind a network call to a host that is *down*; without an enabled-gate the fill/click can be issued against a disabled control and the send silently never happens.
2. **D10 — reply-before-reload gate.** Failure condition added: reloading before the exchange is recorded destroys the very state the scenario asserts. Load-bearing because it is the only thing separating "persistence works" from "we reloaded too early", and it would surface as a flaky, not deterministic, failure.
3. **D14 — strict-mode-safe history row locator.** Failure condition added: a locator that resolves today with one exchange but throws strict-mode violations as soon as a second exchange exists. Load-bearing because the repeated "You"/"Assistant" cells carry no test hooks, so only content-scoped filtering stays correct.
4. **D20 — dialog handler registered before the click.** Failure condition added: an unhandled native `confirm()` auto-dismisses/hangs, so "clearing history removes it" would be tested against a clear that never ran. Load-bearing because the clear is gated entirely behind that dialog.
5. **D19/D20 — dual post-clear signal.** Failure condition added: the row disappearing for a rendering reason other than the history actually being cleared. Load-bearing because pairing row-removal with the button returning to `disabled` (driven by `exchanges.length === 0`) plus the storage key going `null` makes a cosmetic-only pass impossible.

## Note on evidence durability

The observed role/name/state mapping is recorded here and in the final report
rather than left only in `test-results/` or the HTML report, which a later run
would overwrite.
