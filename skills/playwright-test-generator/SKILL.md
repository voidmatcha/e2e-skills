---
name: playwright-test-generator
description: Use when generating new Playwright E2E tests from scratch. Triggers on "generate playwright tests", "write e2e tests for X", "add playwright coverage for X", "create test for X page", "generate tests for the login page". Autonomous mode starts from coverage gap analysis when no target is specified; argument mode targets a specific page or feature directly. Explores the live app via agent-browser tools (with `npx playwright codegen` as a manual fallback), designs scenarios with an explicit user approval gate, auto-detects project structure (POM vs flat spec), runs YAGNI audit and e2e-reviewer after generation, and hands off to playwright-debugger after 3 failed fix attempts.
license: Apache-2.0
metadata:
  author: voidmatcha
  version: "1.2.2"
---

# playwright-test-generator

General-purpose Playwright E2E test generation pipeline. From zero to reviewed, passing tests.

## Pipeline Overview

```
Step 1: Environment Detection
Step 2: Coverage Gap Analysis  (skipped if $ARGUMENT provided)
Step 3: Browser Exploration    (agent-browser; playwright codegen as fallback)
Step 4: Scenario Design        (plan → user approval)
Step 5: Code Generation        (see code-rules.md)
Step 6: YAGNI Audit + e2e-reviewer
Step 7: TS Compile + Test Run  (playwright-debugger on failure)
```

---

## Step 1: Environment Detection

Read project files to build a project profile before doing anything else.

| What | Where to look |
|------|--------------|
| Playwright config | `playwright.config.ts`, `playwright.config.js` |
| Base URL | `baseURL` in playwright config → fallback: `PLAYWRIGHT_BASE_URL` env var → if neither exists, ask user |
| Test directory | config `testDir` → fallback scan: `e2e/`, `tests/`, `playwright/` |
| POM pattern | Check for `models/`, `pages/`, `page-objects/` directories |
| Existing specs | All `*.spec.ts` / `*.test.ts` files in test dir |

**Output (project profile):**
```
baseURL: <detected or user-provided>
testDir: <detected path>
hasPOM: true | false
existingSpecs: [list of file paths]
```

**If `baseURL` cannot be determined:** stop and ask the user to provide the target URL before proceeding.

---

## Step 2: Coverage Gap Analysis

**Skipped if `$ARGUMENT` is provided** — jump to Step 3 with that target.

When no argument is given:

1. Scan for routing files in priority order:
   - Angular: `app-routing.module.ts`, `*-routing.module.ts`
   - Next.js: `app/` directory (App Router), `pages/` directory (Pages Router)
   - React Router: `router.ts`, `routes.ts`, `routes.tsx`
   - Fallback: grep source files for `path:`, `route(`, `<Route ` patterns
   - If no routes found at all: ask user to list the pages they want covered

2. Map existing spec files to routes:
   - Match by file name (e.g. `login.spec.ts` → `/login`)
   - Match by `page.goto()` calls inside spec files

3. Output uncovered routes. Flag as **high priority**:
   - Auth-related paths (`/login`, `/register`, `/forgot-password`)
   - Form-heavy pages (any page with `<form>` or multiple inputs)

4. Ask the user which target to start with before continuing.

---

## Step 3: Browser Exploration

**Do not guess selectors from source code alone.** Use live browser exploration to discover real element roles, labels, and testids.

**Navigation target:** `<baseURL>/<target-path>` from the project profile (Step 1) + selected route (Step 2). If the page requires authentication, open the login page first, authenticate, then navigate to the target.

Use **agent-browser tools** as the primary exploration method:

```
1. browser_navigate <target-URL>
2. browser_snapshot → identify interactive elements (do NOT paste raw content into responses)
3. For each key interaction (button click, form fill, modal open, nav link):
   a. browser_click / browser_type / browser_fill_form / browser_select_option
   b. browser_snapshot → capture resulting state
4. browser_close
```

**Reference only — do not use as primary:** `npx playwright codegen <URL>` launches an interactive browser recorder. It is useful for manually discovering selectors during development but cannot be automated in an agent pipeline.

If agent-browser tools are unavailable, use `npx playwright codegen <URL>` manually and paste discovered selectors into the Locator Mapping Table in Step 4.

**Snapshot handling:** Extract element roles, labels, testids, and visible text from snapshot output. Summarize findings — do NOT paste raw YAML into responses.

**Collect before moving to Step 4:**
- Interactive elements: buttons, links, inputs, selects, modals, dropdowns
- Locator candidates: role+name pairs, label text, data-testid values, attribute selectors
- Key state transitions: loading states, error messages, empty states, open/close toggles

---

## Step 4: Scenario Design + User Approval

Present a scenario plan in the conversation and wait for explicit user approval before writing files. In hosts with a dedicated planning mode, enter that mode before presenting the plan and exit it only after the user approves. In Codex/OpenCode, stop after presenting the plan until the user approves it. Do not write any code until the user approves.

Write a plan containing:

### Scenarios

```
## Scenario 1: [descriptive title]
- Given: [precondition — what state the app is in]
- When: [user action]
- Then: [expected result — what the user sees]
```

Cover at minimum: one happy path + one error/edge case per feature.

### Locator Mapping Table

```
| Locator name   | File              | Selector                                 | Used in | New/Existing |
|----------------|-------------------|------------------------------------------|---------|--------------|
| submitButton   | login-page.ts     | getByRole('button', { name: 'Sign in' }) | 1, 2    | New          |
| emailInput     | login-page.ts     | getByLabel('Email')                      | 1, 2    | New          |
| errorMessage   | login-page.ts     | getByText('Invalid credentials')         | 2       | New          |
```

**Rules:**
- Do not create any locator not listed in this table
- No getter methods — locators are exposed directly as `readonly` properties
- `.nth()`, `.first()`, `.last()` require `// JUSTIFIED: <reason>` on the line immediately above

**Approval gate:** Do not proceed to Step 5 until the user explicitly approves the plan. In hosts with a dedicated planning mode, exit that mode only after approval.

---

## Step 5: Code Generation

Follow `code-rules.md` in this directory for:
- Structure detection (POM vs flat spec)
- Selector priority
- POM rules and composition pattern
- Spec rules and forbidden patterns

Key principle: detect project structure first, match existing patterns when extending.

---

## Step 6: YAGNI Audit + e2e-reviewer

### YAGNI audit (run immediately after writing code)

1. List every locator defined in the generated/modified POM file(s)
2. Grep each locator name across all spec files
3. Delete any locator with zero usages
4. Output the audit table:

```
| Locator        | File           | Used in          | Status  |
|----------------|----------------|------------------|---------|
| submitButton   | login-page.ts  | login.spec.ts:18 | IN USE  |
| unusedLocator  | login-page.ts  | (none)           | DELETED |
```

### e2e-reviewer (automatic quality gate)

Invoke the `e2e-reviewer` skill using the `Skill` tool, targeting the generated spec and POM files.

- **P0 issues found:** fix immediately, re-invoke `e2e-reviewer`. **Max 3 attempts** — if any P0 remains after 3 fix passes (e.g. intentional `test.only` left for development, an unavoidable bypass with no `// JUSTIFIED:` rationale), list the remaining P0s in the final report and proceed to Step 7 with a warning. Do not loop indefinitely.
- **P1/P2 issues found:** output in the final report, do not block Step 7

---

## Step 7: Verification + Failure Handling

```bash
# 1. Type check — must pass with 0 errors
# Use e2e-specific tsconfig if present (e.g. e2e/tsconfig.json), otherwise root tsconfig
npx tsc --noEmit -p <e2e/tsconfig.json or tsconfig.json>

# 2. Run generated tests
npx playwright test <generated-spec-file> --project=chromium
```

### Failure handling (max 3 auto-fix attempts)

Per attempt, diagnose the actual failure and apply the matching fix below (the order is heuristic — the real failure dictates which category to try first):

| Likely cause | Fix |
|--------------|-----|
| Selector mismatches | Re-snapshot the page if needed, update locators to match actual DOM |
| Assertion failures | Fix expected values, add `{ timeout }` for slow elements |
| Structural issues | Fix missing `await`, wrong test setup, incorrect `beforeEach` |

After 3 failed attempts: **invoke `playwright-debugger` skill** using the `Skill` tool. Do not attempt a 4th fix.

### Completion report (on full pass)

```
## playwright-test-generator — Complete

Generated:
- <path to POM file> (new | modified)
- <path to spec file> (new, N scenarios)

Coverage added: <route path>

e2e-reviewer: N P0 (fixed), N P1 (listed below)
Tests: N passed
```

---

## Reference

- Playwright best practices: see `best-practices.md` in this directory
- Code generation rules: see `code-rules.md` in this directory
