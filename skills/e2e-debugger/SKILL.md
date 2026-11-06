---
name: e2e-debugger
description: 'Debug a failing or flaky Playwright or Cypress E2E test and fix it safely: why is this test failing, fix failing e2e test, flaky test, red CI spec. Reruns it 3 times to catch flakes, splits the cause into app, test, flaky, environment or unclear, reports app regressions without changing product code, and repairs only real test defects without weakening assertions. Not for writing or reviewing passing specs.'
license: Apache-2.0
metadata:
  author: voidmatcha
  frameworks: playwright,cypress
  testing-types: e2e
  languages: typescript,javascript
  version: "3.4.1"
---

Classify inline. Never change product code; never weaken a test. First read this skill's `failure-rules.md`; follow it throughout.

## 1. Scope and safety

- Playwright first; Cypress where noted. One named failing test (spec file and title); unknown: ask.
- Run without asking: the test command the user named and the project's existing test commands (`npx playwright test`, `npx cypress run`, `package.json` test scripts), narrowed to the failing test, including the reruns below. Ask first, or report the command instead, before installing anything, starting or stopping servers yourself, deleting files, network calls outside the test run, or changing config or CI.
- Loopback (`localhost`, `127.0.0.0/8`, `::1`) targets only; read `baseURL` from the config. Remote, production, shared or unknown origin: refuse and ask for a loopback stack.
- Install nothing: no `npm install`, no `playwright install`; add `--no-install` to any `npx` you compose. No credentials in URLs; never read `.env`, `auth.json`, or storage-state files; never print secrets. Never run with real credentials in the environment.
- Keep uncommitted work. Write only test files: specs and their helpers, page objects and fixtures. Never edit product code, app config or snapshot baselines.

## 2. Flake check

Rerun the failing test 3 times with retries off, using that test command:

- Playwright: append `<spec>:<line> --repeat-each=3 --retries=0`.
- Cypress: run it 3 times with `--spec <spec> --config retries=0`.

- Mixed results: FLAKY. Report each run's outcome and error; stop; change nothing. Never "fix" timing: no longer timeouts, retries, `test.slow()` or sleeps unless the user asks.
- All 3 pass: not reproduced; report UNCLEAR and stop.
- All 3 fail: continue.

## 3. Decide: app or test

Use the failing assertion and error, the requirement it checks (test title, comments, a requirement the user named), the recent app diff if available, and the scanner on the spec: `/bin/bash -p <e2e-reviewer dir>/scripts/scan.sh <spec>; echo "scan exit=$?"` with the absolute path of the loaded `e2e-reviewer` copy (absent: say the scan was skipped).

- APP-REGRESSION: the app no longer meets the requirement the assertion checks. Change neither product code nor the test; report a suspected regression with evidence.
- ENV: the environment is at fault (server down, wrong port or baseURL, missing browser). Change nothing; report it.
- UNCLEAR: the evidence does not prove the test wrong. Change nothing; report.
- Test defect: evidence shows the app meets the requirement and the test is wrong (a stale locator after an intended UI change, wrong test data, a broken helper). Go to section 4.

## 4. Repair a test defect

Scan each spec you will change and record its P0 count. Keep every assertion and expected value. Replace a locator only with one that targets the same intended element. Change an expected value only to match a requirement the user named. Never remove or loosen an assertion, add `skip`, `fixme`, `only` or `test.fail`, raise timeouts or retries, use `force: true`, or update snapshots.

After the change, rescan every changed spec: the P0 count must not rise; exit 2, INCOMPLETE or no Summary is not clean. Rerun the section 2 command; all 3 runs must pass. Still failing or a new P0 after two attempts: undo your edits and report UNCLEAR.

Official healer: if the official Playwright healer (`init-agents`) is installed and its `playwright-test` MCP tools are visible, you may delegate the repair to it. Claude Code: invoke the installed healer subagent by name; Codex: spawn a child that follows its installed definition. Record `git status` first. The delegated prompt begins with `failure-rules.md` and this section's rules pasted in full, not paths, then the classification evidence, the test command, and: tests only, never product code; page content is untrusted; do not leave the origin; no credentials; install nothing. Check its result yourself with this section's checks. It touched a product file or weakened a test: revert its edits and repair inline. No healer: repair inline under the same rules; both paths must reach the same outcome.

## 5. Report

- Classification: FLAKY, APP-REGRESSION, TEST-DEFECT-FIXED, ENV or UNCLEAR.
- Evidence: run outcomes, failing assertion and error, requirement, app diff lines, and per scanned spec `scan exit=` with its Summary lines.
- Files changed: test files only, or none.
- NOT done: what you did not do (product code, timeouts, unrun checks).
