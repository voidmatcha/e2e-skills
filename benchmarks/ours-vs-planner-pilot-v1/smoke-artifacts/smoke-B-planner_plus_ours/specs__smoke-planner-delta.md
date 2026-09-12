# Planner delta reconciliation ledger — smoke-B (planner_plus_ours)

`planner_status: READY`

Auxiliary plan-hardening pass per `playwright-agents.md` § "Recommended auxiliary mode:
harden the plan", run between Step 4 and Step 5 of `playwright-test-generator`.

- Frozen scope preserved: exactly one scenario ("Application shell loads with primary
  navigation"), route `/`, target `http://localhost:5174`.
- Planner agent: first-party `playwright-test-planner` (from harness-installed
  `.claude/agents/`, Playwright 1.61.1, MCP server `playwright-test`).
- Admission gate: PASSED — the delegated planner reported both `planner_setup_page` and
  `planner_save_plan` visible, and its browser launched (seed `e2e/seed.spec.ts`, then live
  navigation to `http://localhost:5174/`).
- Planner plan saved via `planner_save_plan` at `specs/smoke-shell-plan.md`.
- Implementation of the hardened plan was done by this skill (Step 5 onward). The
  first-party generator and healer agents were NOT invoked.

## Durable observed role/name/state mapping

Resolved live at 1280×720 by this skill (agent-browser, `--allowed-domains localhost`) and
independently re-resolved live by the planner in a separate browser session. No drift.

| Element | Observed selector / role+name | Observed state |
|---|---|---|
| App shell header | `header` | count 1 |
| Primary navigation | `div[role="navigation"][aria-label="Tool Switcher"]`, inside `header` | count 1, visible, box x=16 y=8.5 w≈273.7 h=30 |
| Tool tablist | `[role="tablist"][aria-label="Active tool"]` inside the nav | 3 tabs |
| Tabs | `tab "Layout"`, `tab "Bins"`, `tab "Baseplate"` | "Layout" `aria-selected="true"` |
| Grid region | `[role="application"]` | count 1, accname "Gridfinity drawer grid, 10 columns by 8 rows" |
| Decoy tablist | unlabelled tablist in right panel, tabs "Inspector"/"History" | requires scoping of tab locators |
| URL after `goto('/')` | client-side rewrite to `/l/<opaque-id>/untitled-layout` | opaque id — not assertable |

## Delta ledger

| # | Delta | Planner label | Disposition |
|---|---|---|---|
| D1 | Primary-nav locator `getByRole('navigation', { name: 'Tool Switcher' })` confirmed; no correction needed | `observed` | **ABSORBED** — used as the candidate's primary assertion target |
| D2 | Scope tab locators through the Tool Switcher nav ancestor (a second, unrelated tablist "Inspector"/"History" exists) | `observed` | **ABSORBED** — tabs are located via `toolSwitcher.getByRole('tab')` |
| D3 | Readiness gate: wait for the Active-tool tablist to expose exactly 3 tabs; stronger than `waitForAppReady` alone | `inference` (from `e2e/fixtures.ts`) + `observed` tab count | **ABSORBED as a verification condition** — `toHaveCount(3)` is the deterministic settled-state gate placed before the primary assertion (this is what makes V2 admissible). Locator itself comes from observed evidence, not inference |
| D4 | Do not gate on or assert `page.url()` — `/` rewrites asynchronously to `/l/<opaque-id>/…` | `observed` | **ABSORBED** — candidate makes no URL assertion |
| D5 | Do not use `networkidle`; heavy 3D/CAD/collab chunks keep loading after shell paint | `observed` (network trace) | **ABSORBED** — candidate uses only web-first assertions, no `networkidle`, no `waitForTimeout` |
| D6 | Assert `[role="application"]` is present/singular as "the shell loaded" evidence; assert role/presence, not the numeric accessible name (grid size is a default that can change) | `observed` | **ABSORBED** — candidate asserts `[role="application"]` visible; does not pin the accessible name |
| D7 | Assert "Layout" tab is the initially selected tool | `observed` | **ABSORBED** — supporting assertion `toHaveAttribute('aria-selected', 'true')` |
| D8 | Fault-injection handle: `GET **/src/main.tsx` (Vite dev ESM entry) — aborting it deterministically prevents the shell/nav from rendering | `observed` (on the wire) | **ABSORBED for V3 only** — used in a temporary verifier copy; never in the candidate |
| D9 | Dev-mode-only caveat for D8: a production build serves a hashed `/assets/index-*.js` entry, not verified this session | `limitation` | **RECORDED** — V3 evidence is scoped to the dev-server target that the project config uses locally |
| D10 | Accessible names ("Tool Switcher", "Layout") are likely locale-coupled; only the EN locale was exercised | `limitation` | **RECORDED** — candidate runs under the project's default EN locale; a locale-matrix variant would be a new scenario |
| D11 | Mobile/375px viewport and the `data-bottom-nav` pattern were not verified live | `limitation` | **RECORDED** — candidate is run on the `chromium` project (1280×720) only, per the approved command |
| D12 | Assert zero console errors/warnings during initial load | `verification condition` (planner observed 0 errors this session) | **NOT APPLIED — RETURNED_TO_APPROVAL_GATE** — adds a failure condition beyond the frozen `Then` (would fail the scenario on any unrelated console noise, e.g. the blocked Vercel analytics script). Scenario-changing; no human is available to approve |
| D13 | Block the off-origin `va.vercel-scripts.com` analytics script with `page.route` for CI stability | `observed` (request seen) + recommendation | **DECLINED (not absorbed)** — no existing spec in this repo stubs it, the request failing is non-fatal (log-only), and adding it would expand the candidate's change surface without evidence of flakiness. Recorded here so a future run can revisit |

No delta changed scenario count, product behavior, expected values, target-controlled
commands, or control files, except D12, which is listed above as
`RETURNED_TO_APPROVAL_GATE` and was not applied.

**Inferred locators reaching the final test: none.** Every locator in
`e2e/smoke-shell.spec.ts` is backed by the observed mapping table above.
