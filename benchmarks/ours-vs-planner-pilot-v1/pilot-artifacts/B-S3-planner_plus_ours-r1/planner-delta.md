# Planner delta reconciliation — Scenario B-S3 (cell B-S3-planner_plus_ours-r1)

Arm: `planner_plus_ours`. Auxiliary mode per `playwright-agents.md` §"harden the plan".
The delegated `playwright-test-planner` proposes evidence-labelled plan deltas; this
skill remains the implementer. Planner plan saved by the planner itself at
`specs/pilot-b-s3-planner-plan.md` via `planner_save_plan`.

## Admission gate

`planner_status: READY`.

- Planner confirmed both `planner_setup_page` and `planner_save_plan` were visible in its toolset.
- Planner confirmed its browser launched: `planner_setup_page` returned a live `about:blank`
  page, and navigation to `http://localhost:5174` loaded the app (title
  "Gridfinity Planner & Layout Tool — Free Online Drawer Organizer", redirected to
  `/l/Yz8qY8cgMjWt/untitled-layout`).
- Scope preserved: exactly one scenario (frozen B-S3), entry route `/`, origin
  `http://localhost:5174` only. The planner proposed no additional, split, or reworded scenario.

## Delta ledger

| ID | Delta | Evidence class | Disposition |
|----|-------|----------------|-------------|
| D1 | The only cross-profile mechanism reachable without signing in is the "Share layout" dialog: `combobox "Anyone with link can"` (view / edit) plus `button "Create share link"` — a manual, link-carried mechanism. | observed (planner live page) | **Absorbed** — corroborates my own Step 3 observation of the same dialog (`Anyone with link can view` / `Anyone with link can edit` / `Create share link`). Does not supply the scenario's capability. |
| D2 | Liveblocks realtime sync (`RoomProvider`) is keyed by `shareId` and only activates after an explicit share action; there is no ambient background sync to other profiles. | inference (source `src/shell/Collab/CollabProvider/CollabProvider.tsx`) | **Recorded, not load-bearing.** Source-only; must not reach a test as a locator or assertion. Independently corroborated at runtime by D6. |
| D3 | Settings → Account renders an identity block with `aria-busy="true"` that never resolves, and no "Sign in" control ever appears. | observed (planner) | **Absorbed** — matches my observation: Account tabpanel text `Account \| Cloud sync \| All changes synced \| Not synced yet`, with 0 sign-in buttons and 0 sign-in links in a fresh profile. |
| D4 | `GET /api/auth/me` returns HTTP 200 with `content-type: text/javascript` and the raw TypeScript source of the handler, not the JSON `{authenticated, user}` payload. | observed (planner) | **Absorbed** — independently reproduced by me in-page: `{status: 200, ct: "text/javascript", head: "import { requireMethod } from \"/api/lib/method.ts\"…"}`. |
| D5 | The `/api/*` serverless layer does not execute under the dev server, so the session store can never leave `unknown` and no authenticated path is exercisable end-to-end here. | limitation | **Absorbed** as an environment limitation. It is *secondary*: it blocks exercising the signed-in Cloud Sync path, but the scenario's "without signing in" requirement is already unavailable by product design (see Primary finding). |
| D6 | On a fresh, unshared route, zero network requests to any Liveblocks realtime/room endpoint occur — only local bundled module loads. | observed (planner) | **Absorbed** — runtime confirmation that no sync session exists absent an explicit share. |
| D7 | Verification condition: a conforming test needs two independent fresh browser contexts, an edit made only in context A, and an assertion resolvable purely from context B's own UI, without the test transporting a URL or injected state from A to B. | verification condition | **Absorbed.** This is exactly the shape I executed live in Step 3 (profiles `p1` / `p2`) and it is what falsified the scenario. |
| D8 | Verification condition: must NOT treat copying a share link into context B as "automatic sync"; must NOT assert on the local "Saved" status as a proxy for cross-profile sync; must NOT assert on the "All changes synced" / "Not synced yet" pair, which reads identically in every anonymous profile regardless of any second-profile state. | verification condition | **Absorbed.** These are the three tautologies that a fabricated "passing" B-S3 test would have relied on. Partial decline: the planner characterised those two strings as unconditionally present / "not state-driven"; source (`AccountTab.tsx`) shows they are derived from `useSyncStatusStore`. The load-bearing half is kept (constant for an anonymous session ⇒ tautological here); the "not state-driven" characterisation is **declined** as unverified. |

Counts: absorbed 6 (D1, D3, D4, D6, D7, D8) + 1 recorded-but-not-load-bearing (D2)
+ 1 absorbed-as-limitation (D5); declined 1 (the "not state-driven" half of D8);
**RETURNED_TO_APPROVAL_GATE: 0** — the planner proposed no scenario-changing delta and
explicitly refused to substitute the share-link feature for the frozen outcome.

## Primary finding (planner and this skill agree)

Scenario B-S3 is **not implementable**: the product has no unauthenticated, linkless,
automatic propagation of a layout to a second browser profile.

Evidence, live and in source:

1. Live, two fresh profiles, same origin: profile `p1` created a bin and a layout named
   "Pilot B-S3 Sync Probe" (its own library menu lists it). A fresh profile `p2` at `/`
   was redirected to its own new layout; after a reload and a further 12 s wait its layout
   menu read `["Untitled layout", "New layout", "Manage layouts"]` — `probeCount: 0`,
   `bins: 0`. The layout never appeared.
2. Live, both profiles: Account → "Cloud sync" reads "Not synced yet"; no sign-in
   affordance is rendered at all in this environment.
3. Source gate: `src/shell/sync/SyncSessionMount.tsx` starts the sync engine only under
   `if (status !== 'authenticated') return;` — the engine is never started for an
   anonymous visitor.
4. Server gate: every `/api/sync/*` handler calls `requireSession`
   (`api/lib/session.ts:182`), which answers `401 UNAUTHORIZED "Not signed in"` when no
   session cookie is present. Anonymous sync is refused at the persistence boundary.
5. Product definition: the Labs entry is literally `cloud_sync` / **"Cloud Sync (sign in)"** —
   "Sign in with Google or GitHub to sync your layouts and bin designs across devices."
   `docs/self-hosting.md` lists the capability as the single line
   "Sign in, cloud sync across devices". UI copy: "Working locally · Sign in to sync",
   "Your layouts are saved on this device."

No candidate spec was emitted for B-S3. Writing one would have required a tautological
assertion (D8) or a self-injected fixture, both forbidden by the honesty rule.
