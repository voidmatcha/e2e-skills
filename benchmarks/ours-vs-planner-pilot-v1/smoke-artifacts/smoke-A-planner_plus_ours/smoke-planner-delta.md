# Planner delta reconciliation — Scenario 1 (application shell + primary navigation)

Arm: `planner_plus_ours`. Auxiliary mode per `playwright-agents.md` §"Recommended
auxiliary mode: harden the plan", steps 2–4.

- **Planner status:** READY. Admission gate passed — the delegated
  `playwright-test-planner` confirmed it could see both `planner_setup_page` and
  `planner_save_plan`, and its browser launched against `http://localhost:5174/`
  (page title `Playwright Chat Lab`).
- **Raw planner output:** `specs/smoke-planner-plan.md` (saved by the planner via
  `planner_save_plan`).
- **Scope:** frozen — exactly one scenario, route `/`. The planner proposed **no**
  `SCOPE_CHANGE` deltas.
- **Implementer:** this skill (`playwright-test-generator`). The first-party
  generator and healer agents were not invoked.

## Durable observed role/name mapping

Persisted here so it does not live only in a transient `test-results/` context.
Source of truth is my own Step 3 exploration (Playwright CLI, session `smoke`),
corroborated by the planner's independent live session.

| Element | Role + accessible name | `data-testid` | Notes |
|---|---|---|---|
| Shell title | `heading` "Playwright Chat Lab", level 1 | — | inside `banner` |
| Primary nav | `navigation` "Main" (`<nav aria-label="Main">`) | — | exactly one `<nav>` on `/` |
| Nav link 1 | `link` "Chat" → `/` | `nav-tab-chat` | carries `aria-current="page"` on `/` |
| Nav link 2 | `link` "Search" → `/search` | `nav-tab-search` | |
| Nav link 3 | `link` "Message history" → `/history` | `nav-tab-history` | |
| Nav link 4 | `link` "Playground" → `/playground` | `nav-tab-playground` | not covered by the existing suite |
| Nav link 5 | `link` "Help" → `/help` | `nav-tab-help` | a separate `button` "Help" also exists on `/` |

## Delta ledger

`#` refers to the numbered step in `specs/smoke-planner-plan.md`.

| # | Class (planner) | Class (reconciled) | Delta | Disposition |
|---|---|---|---|---|
| 1 | observed | **observed** | Nav landmark "Main" and h1 "Playwright Chat Lab" both present in the first snapshot after `goto` resolves; no flash/reorder observable | **ABSORBED** — corroborates my own snapshot; justifies a same-paint settled gate |
| 2 | inference | **inference** | React SPA renders header + nav from one top-level component tree; only the chat list depends on the failing `localhost:3001` fetch | **ABSORBED AS RATIONALE ONLY** — no locator derived from it |
| 3 | verification condition | **verification condition** | Use *both* `navigation` "Main" visible **and** `heading` level-1 "Playwright Chat Lab" visible as the settled-state gate | **ABSORBED** — hardens my draft, which gated on the h1 alone. Implemented as `AppLayoutPage.expectAppShellLoaded()` |
| 4 | limitation | **limitation** | Could not empirically prove there is zero frame where the nav is absent/empty pre-hydration | **RECORDED** — residual, unverified. Mitigated by web-first retrying matchers; no `waitForTimeout` used |
| 5 | observed | **observed** | `document.querySelectorAll('nav').length === 1` on `/` | **ABSORBED** — `getByRole('navigation', { name: 'Main' })` is unambiguous |
| 6 | observed | **observed** | Link `textContent` values are exactly `Chat`, `Search`, `Message history`, `Playground`, `Help` — no whitespace/icon pollution | **ABSORBED** — ordered-text array assertion is safe |
| 7 | observed | **observed** | `aria-current="page"` is set only on the Chat link on `/` | **RETURNED_TO_APPROVAL_GATE** — the planner offered it as a "bonus check". Asserting active-route indication is a *different* user-visible outcome than the frozen `Then` clause ("primary navigation is visible"), so it would change scenario content. Not applied; no human available to approve |
| 8 | observed | **observed** | role+name locators resolve cleanly here; `data-testid` present but no live evidence favours it | **ABSORBED** — primary assertion uses role+name scoped to the landmark. Consequence: I dropped the new `getByTestId('nav-tab-playground')` locator from my Step 4 table (YAGNI). Pre-existing testid locators in `AppLayoutPage` are left untouched |
| 9 | observed | **observed** | A second "Help" element exists on `/` — `button` "Help" in the chat panel, distinct from the nav `link` "Help" | **ABSORBED** — all link assertions are scoped to the `Main` landmark; an unscoped `getByText('Help')` would be a strict-mode hazard. Recorded as a comment in the spec |
| 10 | verification condition | **verification condition** | Falsification probe: nav link count === 5 | **ABSORBED (SUBSUMED)** — `toHaveText([...5 names])` already enforces cardinality; a separate `toHaveCount(5)` would be redundant |
| 11 | verification condition | **verification condition** | Falsification probe: nav link texts equal the exact array, in order — fails on reorder, rename, or icon/text prefix | **ABSORBED** — this is the V1 primary assertion |
| 12 | observed | **observed** | Two `ERR_CONNECTION_REFUSED` console errors for `http://localhost:3001/api/messages` on every load; they do not block header/nav render | **ABSORBED AS A GUARD** — the candidate must not assert console cleanliness. It does not |
| 13 | limitation | **limitation** | Theme switcher (Aurora / Test Runner) interaction not probed; cannot confirm the nav is unaffected by theme changes | **RECORDED / OUT OF SCOPE** — probing it would add an interaction to a frozen read-only scenario |
| 14 | limitation (planner called the fonts dependency *inferred*) | **observed (by me, not by the planner)** | `index.html` pulls a stylesheet from `https://fonts.googleapis.com` | **RECLASSIFIED + ABSORBED** — I observed this live via `performance.getEntriesByType('resource')` in my own session, so it is observed evidence, not inference. Absorbed recommendation: never gate on `networkidle`. The candidate does not |

## Summary

- Absorbed: 1, 2 (rationale only), 3, 5, 6, 8, 9, 10, 11, 12, 14.
- Returned to the approval gate (not applied): **7** — `aria-current` active-route
  assertion, because it introduces a new user-visible outcome beyond the frozen
  `Then` clause. There is no human in this session to approve it.
- Recorded limitations, not applied: 4, 13.
- **Inferred locators that reached the final test: none.** Every locator in
  `e2e/smoke-shell.spec.ts` and every locator newly added to
  `e2e/pages/layout/appLayoutPage.ts` was resolved on the live page.
- Net change from the planner: the settled-state gate was widened from the h1
  alone to h1 + nav landmark (#3), a planned new testid locator was dropped in
  favour of role+name (#8), and landmark scoping was documented as a
  strict-mode requirement (#9).

## Session limitations affecting this ledger

- **Preflight verdict unavailable.** `scripts/run-preflight-target.sh` could not
  return `reachable` for this fixture: `localhost` resolves to both loopback
  peers, Vite binds only `::1`, so the `127.0.0.1` peer probe fails (curl 7) and
  peer agreement is impossible; the IPv6-literal form fails the helper's own
  `--resolve` construction (curl 49). Direct pinned probes: `127.0.0.1` refused,
  `[::1]` → `200`. Both peers are loopback and `ALLOW_LOOPBACK=1` was authorised,
  so the gate's intent holds, but the scripted verdict was not obtained.
- **No pre-dispatch request guard during exploration.** Playwright CLI exposes no
  `context.route()` hook, so off-origin requests could not be aborted before
  dispatch. Post-hoc, the application itself requested
  `https://fonts.googleapis.com` (off-origin, succeeded) and
  `http://localhost:3001/api/messages` (refused). No off-origin navigation was
  performed; the browser was closed immediately after the snapshot.
