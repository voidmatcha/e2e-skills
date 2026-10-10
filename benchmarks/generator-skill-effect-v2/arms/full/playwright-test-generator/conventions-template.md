# E2E Conventions Template (AGENTS.md section)

Before writing first-run convention and seed artifacts, apply this procedure:

1. Re-read the approved Step 4 control-file table. Mutate only an approved exact
   target, using its approved `create` or `append` action. Generate the
   project-adapted E2E conventions section from `conventions-template.md` for
   the approved root `AGENTS.md`; add the one-line `CLAUDE.md` pointer only when
   that exact row was disclosed and approved. Never mutate an undisclosed,
   skipped, or otherwise unapproved control surface.
2. Designate the best generated spec as the seed by path in the conventions doc ("copy the shape of `<path>`") so future agents copy real auth, locator, and mocking patterns.
3. Fill template project-reality fields from Step 3 observations, not generic best practices.
4. Apply `recommended-lint.md`: reuse documented lint commands and dedupe equivalent findings, but do not install/scaffold ESLint or rewrite config; the bundled scanner/reviewer remains the cross-host gate.

Used by Step 5b when a project has no testing-conventions doc. Fill every `<angle-bracket>` field from what Step 3 exploration **actually observed** — a conventions doc that parrots generic best practices instead of project reality is worse than none, because future agents will trust it.

Append the section below to the project's root `AGENTS.md` (create the file if absent). When the approved control-file table has a `CLAUDE.md` row (a root `CLAUDE.md` or `.claude/` directory exists), add a single pointer there, creating the file only if that row says `create`: `See AGENTS.md.`

---

## E2E Testing

### Layout
- Specs: `<testDir>/<area>/<feature>.spec.ts`
- Page objects: `<pom-dir, or "none — flat specs">`
- Shared fixtures: `<fixtures file, or "none">`
- Never touch: `<protected areas — e.g. visual-regression suites, snapshot baselines, capture scripts>`

### Locator strategy (this app's reality)
- Buttons / links: `getByRole('button' | 'link', { name })`
- Form inputs: `<"getByLabel — labels exist" | "inputs have NO labels — use getByPlaceholder('<string>') or getByRole('textbox'); getByLabel matches nothing here">`
- Last resort: `data-testid`. Raw CSS chains / XPath: forbidden.

### Assertions
Auto-waiting web-first assertions only (`toBeVisible`, `toHaveURL`, `toHaveText`, `toHaveCount`). No `waitForTimeout`, no one-shot boolean checks (`expect(await el.isVisible())`).

### Network
- API shape: `<e.g. "all calls proxied through /api/request?cmd=<path> — mock by decoded cmd">`
- Writes/credentials (signup, login, payment, mutations): `<"stubbed via <mock helper path> — list every write endpoint explicitly; unlisted calls fall through to the real backend" | "real, against a disposable server that the approved test run starts and stops and that <reset seam> resets before each test; never a shared or pre-existing backend">`
- Real backend allowed: `<which read endpoints / the one designated smoke spec>`

### Auth
- Session setup: `<programmatic helper / setup project + storageState path>`
- Do NOT depend on: `<manually captured session files — name them>`
- Logged-out scenarios: fresh context (project `<name>`)

### Routing facts (verified)
- `<e.g. "logged-out + protected route → 307 redirect to /">`
- `<e.g. "logged-in non-guest + / → redirect to /home; guest sessions excluded">`

### Run
- All E2E: `<command>`
- Single spec: `<command> <path>`
- Dev server: `<"auto-started via playwright webServer (reuses a running one)" | "must be running at <url> first">`

### Adding tests (AI agents start here)
To add E2E coverage for feature X: copy the shape of `<seed spec path>`, add locators only via the Locator Mapping Table workflow, control every write at the seam named under Network, then run `<verify command>`. Deferred areas — do not auto-generate without sign-off: `<e.g. payment (external PG redirect), member-session deep flows>`.
