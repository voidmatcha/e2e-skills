# Pilot B-S3 — planner delta reconciliation ledger

Arm: `planner_plus_ours` · Cell: `B-S3-planner_plus_ours-r2` · Protocol: `ours-vs-planner-pilot-v1`

Planner status: **READY** (admission gate passed — the delegated `playwright-test-planner`
confirmed it could see both `planner_setup_page` and `planner_save_plan`, and its browser
launched and loaded `http://localhost:5174/`, redirecting to
`http://localhost:5174/l/TiQxAc6thjBm/untitled-layout`).

Planner plan artifact: `specs/pilot-b-s3-planner-plan.md` (saved via `planner_save_plan`).

## Frozen scenario (preserved verbatim, not reworded)

> ## Scenario B-S3
> - Given: the application is served at http://localhost:5174, fresh browser profile, empty client-side storage
> - When: the user performs the actions the outcome below requires
> - Then: Without signing in, the layout is synced to a second browser profile through Cloud Sync and appears there automatically.

## Outcome

The scenario is **rejected_missing_capability**. Both exploration sources — this skill's own
`playwright-cli` exploration and the independently-run planner — resolved on the live page that
the application provides no sign-in-free automatic cross-profile Cloud Sync. No candidate spec
was emitted. No assertion was fabricated.

## Delta ledger

| # | Delta from planner | Class | Disposition |
|---|--------------------|-------|-------------|
| D1 | Anonymous Settings → Account tab renders an empty `aria-busy="true"` skeleton where the sign-in / local-mode block belongs; no sign-in affordance is reachable under `pnpm run dev`. | `observed` (planner opened Settings → Account tab live; independently reproduced here — panel HTML dumped live is `<div ... aria-busy="true"></div>`) | **Absorbed** into the missing-capability finding. |
| D2 | `/api/auth/me` returns HTTP 200 with `content-type: text/javascript` (the Vite-transformed module, not session JSON), so session status never resolves past `'unknown'`. | `observed` (planner: network request; independently reproduced here — request #1147, `content-type: text/javascript`, `content-length: 8442`) | **Absorbed**. Establishes that even the sign-in path is unreachable on this fixture, so the "without signing in" premise cannot be rescued by signing in. |
| D3 | Creating and renaming a layout while anonymous produces **zero** `/api/sync/*` requests; only `/api/auth/me` and `/api/ml-telemetry` (404) appear. | `observed` (planner: `browser_network_requests` after rename + bin placement; independently reproduced here — profile A request list after rename contained no `/api/sync/*` entry) | **Absorbed**. This is the load-bearing negative evidence: the sync engine never starts anonymously. |
| D4 | `SyncSessionMount.tsx` gates `engine.start()` behind `if (status !== 'authenticated') return;`; `engine.ts` documents itself as started on sign-in. | `inference` (source only — planner read the files; no live proof of the branch) | **Absorbed as corroboration only.** Explicitly *not* treated as live evidence and not used as a locator source. |
| D5 | "All changes synced" (`dock.syncStatusIdle`) and "Not synced yet" (`account.sync.lastSyncedNever`) are the sync-status store's untouched defaults and render identically whether or not any sync engine ran — asserting on them would be tautological. | `verification condition` (planner flagged; independently confirmed here — both strings present in the anonymous Account panel while zero sync traffic occurred) | **Absorbed as a prohibition.** Any test asserting Cloud Sync success via these labels would pass with the feature entirely absent, so no such assertion may be written. |
| D6 | The only anonymous cross-browser propagation path is the manual "Share layout" → "Create share link" dialog, which requires copying a URL out of band. | `observed` (planner opened the dialog; independently reproduced here — `dialog "Share Layout"` with `button "Create share link"`) | **Absorbed** as the boundary of what exists. Does **not** satisfy "through Cloud Sync" or "appears there automatically". |
| D7 | The genuine anonymous local-mode UI ("Working locally", "Sign in with Google/Github") could not be confirmed live because session status is stuck at `'unknown'` on this fixture. | `limitation` | **Recorded, not absorbed.** Reported honestly as a never-observed state. |
| D8 | Planner recommendation: replace the scenario with a **negative** test (layout created anonymously in profile A does not appear in profile B; no `/api/sync/*` traffic). | scenario-changing | **RETURNED_TO_APPROVAL_GATE — not applied.** This inverts the approved Then-clause from a sync-succeeds outcome to a sync-absent outcome. The scenario is frozen byte-for-byte and there is no human in this session to approve the change, so it is recorded here and left unimplemented. |

Summary: absorbed **6** (D1–D6), returned to approval gate **1** (D8), declined **0**.
D7 is a limitation record, not a delta disposition.

### New verification conditions absorbed

- D5 — A test could assert on the Account panel's "All changes synced" / "Not synced yet" labels
  and go green while no sync engine has ever started; that failure condition (feature absent,
  test passes) is exactly the silent pass this contract must detect, so the labels are barred
  from serving as evidence of sync.
- D3 — Absence of `/api/sync/*` traffic in the anonymous session is the observable that
  distinguishes "sync ran and succeeded" from "sync never started"; without it, any
  cross-profile assertion cannot tell the two apart.

## Inferred locators that reached the final test

None — no test was emitted. D4 (the only source-only delta) supplied no locator.

## Honesty-rule application to planner deltas

No planner delta supplied a capability the application lacks. The planner's own verdict was
`CAPABILITY_ABSENT`, concordant with this skill's independent exploration.
