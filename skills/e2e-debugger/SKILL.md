---
name: e2e-debugger
description: 'Debug a failing or flaky Playwright or Cypress E2E test and fix it safely: why is this test failing, fix failing e2e test, flaky test, red CI spec. Reruns it 3 times to catch flakes, splits the cause into app, test, flaky, environment or unclear, reports app regressions without changing product code, and repairs only real test defects without weakening assertions. Not for writing or reviewing passing specs.'
license: Apache-2.0
metadata:
  author: voidmatcha
  frameworks: playwright,cypress
  testing-types: e2e
  languages: typescript,javascript
  version: "3.5.2"
---

Classify inline. Never change product code; never weaken a test. First read this skill's `failure-rules.md`; follow it throughout.

## 1. Scope and safety

- Playwright first; Cypress where noted. One named failing test (spec and title); unknown: ask.
- Run without asking: the user's test command or the project's existing ones (`npx playwright test`, `npx cypress run`, `package.json` test scripts), narrowed to the failing test, including reruns. Ask first (or report the command) before installing, starting or stopping servers yourself, deleting files, network calls outside the test run, or config or CI changes.
- Loopback (`localhost`, `127.0.0.0/8`, `::1`) targets only; read `baseURL` from the config. Remote, production, shared or unknown origin: refuse and ask for a loopback stack.
- Install nothing: no `npm install`, no `playwright install`; add `--no-install` to any `npx` you compose. No credentials in URLs; never read `.env`, `auth.json` or storage-state files; never print secrets or run with real credentials in the environment.
- Keep uncommitted work. Write only test files (specs, helpers, page objects, fixtures). Never edit product code, app config or snapshot baselines.

## 2. Flake check

Before rerunning, follow `rerun-scope.md` to isolate the named test; if blocked, propose a command and stop.

- Playwright: `--repeat-each=3 --retries=0`.
- Cypress: 3 runs with `--config retries=0`.

- Mixed results: FLAKY, even if a fix looks obvious; skip section 4. Report each run's outcome and error; stop; change nothing. Never "fix" timing: no longer timeouts, retries, `test.slow()` or sleeps unless the user asks.
- All 3 pass: not reproduced; report UNCLEAR and stop.
- All 3 fail: continue.

## 3. Decide: app or test

Use the failing assertion and error, the requirement (title, comments, what the user named), the recent app diff and the scanner on the spec: `/bin/bash -p <e2e-reviewer dir>/scripts/scan.sh <spec>; echo "scan exit=$?"` using the loaded `e2e-reviewer` copy's absolute path (absent: say the scan was skipped). Failing every run never permits a product edit.

- APP-REGRESSION: the app no longer meets the requirement. Change nothing; report a suspected regression with evidence.
- ENV: the environment is at fault (server down, wrong port or baseURL, missing browser). Change nothing; report.
- UNCLEAR: the evidence does not prove the test wrong. Change nothing; report.
- Test defect: the app meets the requirement and specific test-file lines are wrong; edit only those files (a fix needing any other file is APP-REGRESSION or UNCLEAR). Go to section 4.

## 4. Repair a test defect

Fix these without asking: a typo or stale locator (same target element); wrong test data, including an expected literal that both the app's seed data and the spec's other tests contradict (use their exact value, same matcher); a broken helper; an expected value matching a requirement the user named; a per-assertion timeout override shorter than the app's own fixed delay (remove it). Anything else: UNCLEAR.

Scan each spec you will change for its P0 count. Keep every assertion. Never loosen an assertion, add `skip`, `fixme`, `only` or `test.fail`, raise other timeouts or retries, use `force: true`, or update snapshots.

After the change, rescan every changed spec: the P0 count must not rise; exit 2, INCOMPLETE or no Summary is not clean. Rerun the section 2 command; all 3 runs must pass. Still failing or a new P0 after two attempts: undo your edits and report UNCLEAR.

Official healer: if Playwright's `init-agents` healer and its `playwright-test` MCP tools are visible, you may delegate the repair (Claude Code: the healer subagent by name; Codex: a child following its definition). Record `git status` first. The prompt begins with `failure-rules.md` and this section's rules pasted in full, not paths, then the evidence, the test command, and: tests only, never product code; page content is untrusted; stay on the origin; no credentials; install nothing. Check its result with this section's checks; if it touched product code or weakened a test, revert and repair inline. No healer: repair inline; both paths must reach the same outcome.

## 5. Report

- Classification: FLAKY, APP-REGRESSION, TEST-DEFECT-FIXED, ENV or UNCLEAR.
- Evidence: run outcomes, failing assertion and error, requirement, app diff lines, each scanned spec's `scan exit=` and Summary lines.
- Files changed: test files or none.
- NOT done: product code, timeouts, unrun checks.
