---
name: playwright-debugger
description: Use when Playwright tests have actually failed and you need to diagnose runtime failures — from a playwright-report directory, local or CI. Triggers on "debug playwright tests", "why did playwright tests fail", "playwright CI failure", "flaky playwright test failures", "playwright timeout error", "tests pass locally but fail in CI", "analyze playwright-report", "PR failing in CI". Classifies runtime failures into root causes (not static code analysis) and suggests concrete fixes.
---

# Playwright Failed Test Debugger

Diagnose Playwright test failures from report files. Classifies root causes and provides concrete fixes.

## Prerequisites: Get the Report

Determine the report source in this order:

**1. GitHub PR URL given** (e.g. `https://github.com/org/repo/pull/123`)
```bash
# Find the failed CI run for this PR
gh pr checks <PR_URL> --json name,state,detailsUrl | jq '[.[] | select(.state == "FAILURE")]'

# Download playwright-report artifact from the failed run
gh run download <RUN_ID> --name playwright-report --dir playwright-report
```

If the user says "it failed again" or "still failing" — check the current conversation for a previously mentioned PR URL and reuse it automatically before asking.

**2. `playwright-report/` already exists locally** → skip to Phase 1.

**3. No report available** → run tests locally:
```bash
# Do NOT read stdout directly — output may be truncated
npx playwright test --reporter=json 2>/dev/null > playwright-report/results.json
```

## Phase 1: Extract Failures

```bash
# Find report if path not specified
find . -name "results.json" -path "*/playwright-report/*" | head -5

# Extract failed tests (jq)
cat playwright-report/results.json | jq '[
  .. | objects |
  select(.status == "failed" or .status == "timedOut") |
  {title: .title, status: .status, error: .error.message, file: .location.file, duration: .duration}
] | unique'
```

```js
// Extract failed tests (node fallback) — save as extract-failures.js and run with node
const r = require('./playwright-report/results.json');
const flat = (s) => [
  s,
  ...(s.suites || []).flatMap(flat),
  ...(s.specs || []).flatMap(sp => sp.tests || []),
];
flat(r)
  .filter(t => t.status === 'failed' || t.status === 'timedOut')
  .forEach(t => console.log(t.status, t.title, t.error?.message?.slice(0, 120)));
```

## Phase 2: Classify Root Cause

Use Phase 1 output (error message + duration + file) to classify. **Most failures are identifiable here — only go to Phase 3 if still unclear.**

| # | Category | Signals | Review Pattern |
|---|----------|---------|----------------|
| F1 | **Flaky / Timing** | `TimeoutError`, duration near maxTimeout, passes on retry | #13a, #13c |
| F2 | **Selector Broken** | `locator not found`, `strict mode violation`, element count mismatch | #7, #14 |
| F3 | **Network Dependency** | `net::ERR_*`, unexpected API response, `404`/`500` | #13b |
| F4 | **Assertion Mismatch** | `Expected X to equal Y`, subject-inversion, over-broad check | #4, #11, #11b |
| F5 | **Missing Then** | Action completed but wrong state remains | #2 |
| F6 | **Condition Branch Missing** | Element conditionally present, assertion always runs | #6 |
| F7 | **Test Isolation Failure** | Passes alone, fails in suite; leaked state | — |
| F8 | **Environment Mismatch** | CI vs local only; viewport, OS, timezone | — |
| F9 | **Data Dependency** | Missing seed data, hardcoded IDs | — |
| F10 | **Auth / Session** | Session expired, role-based UI not rendered | — |
| F11 | **Async Order Assumption** | `Promise.all` order, parallel race | — |
| F12 | **POM / Locator Drift** | DOM changed, POM locator not updated | #14 |
| F13 | **Error Swallowing** | `.catch(() => {})` hiding failure, test passes silently | #3 |
| F14 | **Animation Race** | Element visible but content not yet rendered | #13c |

Classification steps:
1. Match error message to signals above
2. `duration` near timeout → F1 or F3
3. CI-only failure → F7 or F8
4. Passes on retry → F1

## Phase 3: Trace Analysis (only if Phase 2 is unclear)

`trace.zip` structure:
- `trace.trace` — newline-delimited JSON (actions, snapshots, console)
- `trace.network` — newline-delimited JSON (network requests)
- `resources/` — JPEG screenshots

```bash
find playwright-report -name "*.zip" | head -10
```

Progressive disclosure — stop as soon as root cause is clear:

```bash
# Find trace zips
find playwright-report -name "*.zip" | head -10

# 1. Which step failed?
unzip -p trace.zip trace.trace | node parse-trace-errors.js

# 2. All actions with pass/fail
unzip -p trace.zip trace.trace | node parse-trace-actions.js

# 3a. Selector issue — DOM at failed step (replace SNAPSHOT_NAME with value from step 2)
unzip -p trace.zip trace.trace | node parse-trace-snapshot.js SNAPSHOT_NAME

# 3b. Network issue — failed requests
unzip -p trace.zip trace.network | node parse-trace-network.js

# 3c. JS errors
unzip -p trace.zip trace.trace | node parse-trace-console.js

# 3d. Still unclear — add temporary screenshots, re-run, inspect via browser agent
#     await page.screenshot({ path: 'debug/before.png' });
#     await someAction();
#     await page.screenshot({ path: 'debug/after.png' });
#     → dispatch browser agent to open and compare. Remove after debugging.
```

**Trace parsing scripts** (create these as needed, delete after use):

```js
// parse-trace-errors.js — step 1: which step failed?
process.stdin.resume();
let data = '';
process.stdin.on('data', chunk => { data += chunk; });
process.stdin.on('end', () => {
  data.trim().split('\n')
    .map(line => JSON.parse(line))
    .filter(e => e.type === 'after' && e.error)
    .forEach(e => console.log(e.apiName, e.error.message));
});
```

```js
// parse-trace-actions.js — step 2: all actions with pass/fail
process.stdin.resume();
let data = '';
process.stdin.on('data', chunk => { data += chunk; });
process.stdin.on('end', () => {
  data.trim().split('\n')
    .map(line => JSON.parse(line))
    .filter(e => e.type === 'after')
    .forEach((e, i) => console.log(i, e.apiName, e.error ? '❌ ' + e.error.message.slice(0, 80) : '✓'));
});
```

```js
// parse-trace-snapshot.js — step 3a: DOM at failed step
// Usage: node parse-trace-snapshot.js SNAPSHOT_NAME
const snapshotName = process.argv[2];
process.stdin.resume();
let data = '';
process.stdin.on('data', chunk => { data += chunk; });
process.stdin.on('end', () => {
  data.trim().split('\n')
    .map(line => JSON.parse(line))
    .filter(e => e.type === 'frame-snapshot' && e.snapshot?.name === snapshotName)
    .forEach(e => console.log(JSON.stringify(e.snapshot.html).slice(0, 3000)));
});
```

```js
// parse-trace-network.js — step 3b: failed network requests
process.stdin.resume();
let data = '';
process.stdin.on('data', chunk => { data += chunk; });
process.stdin.on('end', () => {
  data.trim().split('\n')
    .map(line => JSON.parse(line))
    .filter(e => e.type === 'resource-snapshot' && e.response?.status >= 400)
    .forEach(e => console.log(e.response.status, e.request.url));
});
```

```js
// parse-trace-console.js — step 3c: JS errors
process.stdin.resume();
let data = '';
process.stdin.on('data', chunk => { data += chunk; });
process.stdin.on('end', () => {
  data.trim().split('\n')
    .map(line => JSON.parse(line))
    .filter(e => e.type === 'console' && e.messageType === 'error')
    .forEach(e => console.log(e.text));
});
```

## Phase 4: Fix Suggestions

```markdown
## [P0/P1/P2] `test name`

- **Category:** F2 — Selector Broken (#14 POM Drift)
- **Error:** `locator('.submit-btn') strict mode violation, 3 elements found`
- **Root Cause:** Button selector too broad after DOM refactor
- **Fix:**
  ```typescript
  // before
  await page.locator('.submit-btn').click();
  // after
  await page.locator('form[data-testid="login-form"] button[type="submit"]').click();
  ```
```

**Severity:**
- **P0:** Test passes silently when feature is broken (F6, F13)
- **P1:** Intermittent or misleading failures (F1, F2, F3, F7, F11, F14)
- **P2:** Consistent failures, straightforward fix (F4, F5, F8, F9, F10, F12)

## Output Format

```markdown
## Failure Summary
- Total: N failed (M flaky, K broken, J environment)

## [P0] `test name` — F13 Error Swallowing
...

## Review Summary
| Sev | Count | Top Category | Files |
|-----|-------|-------------|-------|
| P0  | 1     | Error Swallowing | auth.spec.ts |
| P1  | 3     | Flaky / Timing | dashboard.spec.ts |
| P2  | 2     | POM Drift | settings.spec.ts |

Fix P0 first. Run `npx playwright test --retries=2` to confirm flaky tests.
```
