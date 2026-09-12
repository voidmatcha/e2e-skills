# Planner delta ledger — Scenario A-S1

Arm: `planner_plus_ours`. Cell: `A-S1-planner_plus_ours-r1`.

- **planner_status: READY** — the delegated `playwright-test-planner` confirmed it could see
  both `planner_setup_page` and `planner_save_plan`, and its browser launched and rendered
  the live app at `http://localhost:5174`.
- Planner plan saved by the planner at `specs/pilot-a-s1-planner-plan.md`.
- Scope instruction given to the planner: preserve the frozen scenario byte-for-byte,
  exactly one scenario, entry route `/`, deltas only.
- Final implementer: this skill (the planner did not write the test).

## Classification of every delta

### observed (planner resolved it on the live page)

| # | Delta | Reconciliation |
|---|---|---|
| O1 | `funny-mode-toggle` checkbox, accessible name "Assistant mode Funny mode", checked on fresh load | Matches my own Step 3 observation exactly. Independent corroboration. |
| O2 | `chat-input` textarea, accessible name / placeholder "Type a message…" | Matches mine. |
| O3 | `send-button`, disabled when composer empty, enabled once text typed | Matches mine (I saw the same disabled→enabled transition). |
| O4 | `message-user` / `message-assistant` transcript containers | Matches mine. Planner verified with **different letters** than I used: `"Zebra crossing please"` → the Z entry, `"Bananas are cool"` → the B entry. My probes used K (twice, different wording) and D. Four letters across two independent browser sessions all matched `FUNNY_REPLIES_BY_LETTER`. |
| O5 | `loading-indicator` ("Thinking...") appears immediately after Send, then disappears when the reply lands — deterministic settle gate | Matches my own observation (I caught it with a pre-armed `waitFor`, then saw `count() === 0` after the reply). **Absorbed as A1.** |

### inference (source/seed only — NOT live-resolved by the planner)

| # | Delta | Reconciliation |
|---|---|---|
| I1 | "offline mode" is not a literal UI label; it maps to the "Funny mode" toggle | **Absorbed, and upgraded to observed on my side.** `README.md:27` calls it "Deterministic offline mode (\"Funny mode\")", and I observed live that the send issues **zero** HTTP requests (blocked-request count unchanged across the send; no `POST /api/chat` in the console log). So the mapping is not left as an inference in the final test. |
| I2 | `getAppAssistantReply` runs *before* the letter table, so a message containing `?` bypasses letter keying | **Absorbed as a test-data constraint (A5).** Does not introduce a locator. My chosen message contains no `?`. |
| I3 | `"Hello there!"` is special-cased and bypasses the letter table | **Absorbed as A5.** This is exactly why the existing `e2e/tests/chat.spec.ts` does not cover the keyed path. |
| I4 | First letter is the first `/[a-zA-Z]/` match, not `message[0]` | **Absorbed as A5.** My message starts with a plain letter, so both readings agree. |
| I5 | `historyReady` / disabled-on-load timing not separately measured | Not needed; I gate on observed enabled-state instead. |

### verification condition

| # | Condition | Decision |
|---|---|---|
| A1 | Assert the `loading-indicator` is hidden after the reply, not merely that an assistant bubble exists | **ABSORBED** |
| A2 | Assert the Funny-mode (offline) toggle is checked immediately before sending | **ABSORBED** |
| A3 | Exact-text equality against the letter-table entry, not loose "an assistant message appeared" | **ABSORBED** (already my V1; confirms it) |
| A4 | Assert exact transcript cardinality rather than presence, to catch duplicate/echoed renders | **ABSORBED** |
| A5 | Constrain the test message: no `?`, not `"Hello there!"`, starts with a plain letter | **ABSORBED** |
| D1 | Assert the `error-message` element is absent, to catch a mode leak into the backend error path | **DECLINED.** The planner never resolved `error-message` on the live page — it is source-only (`inference`). The skill forbids an inferred locator reaching the final test, and I chose not to drive the app into the error state because that is outside the frozen scenario. The underlying concern is already covered: the error path renders **no** assistant bubble at all, so the exact-text assertion on `message-assistant` turns red under it. |
| D2 | Scope assertions to the *last* `message-user` / `message-assistant` pair | **DECLINED as a mechanism.** In a fresh context sending exactly one message, asserting an exact count of 1 is strictly stronger than `.last()` and avoids an unjustified `.last()` (which `code-rules.md` would require a `// JUSTIFIED:` comment for). The concern itself is absorbed via A4. |

### limitation (could not be observed live)

- Real-backend (non-funny) success reply — no backend ships in this repo.
- Exact `historyReady` timing.
- No-letter / emoji fallback reply text.
- Message-history (localStorage) persistence across screens.

All four are **outside the frozen scenario** and are recorded here rather than tested.

## RETURNED_TO_APPROVAL_GATE

**None (0).** The planner proposed no additional scenario, no scope change, no new
target-controlled command, and no control-file mutation. Nothing required human approval,
and nothing scenario-changing was applied.

## Tally

- absorbed: **5** (A1–A5)
- returned_to_approval_gate: **0**
- declined: **2** (D1, D2)

## Honesty note

No planner delta supplied a capability the application lacks. Every delta that reached the
final test was independently resolved on the live page by me in this session as well.
