<!-- SPDX-License-Identifier: Apache-2.0 -->
# Generated output validation

Read before handling delegated output: origin checks, scanner, native execution, any repair and final reporting. These gates apply to every new or changed spec.

Additional evidence copies and reports must stay within authorized write paths; temporary directories are not an exception. Approval for native test outputs does not permit manually added reports or copies in their output directories. Without an authorized path, retain evidence in the conversation and report unavailable files instead of creating another directory.

## 5. Origin, scanner gate, then run

Stay within the requested phase. For an execution-eligibility decision only, inspect the necessary evidence, report eligibility and stop without scanning or running. A failed or unresolved destination gate stops downstream scanning, execution and repair. An independently authorized static check may still run without contacting blocked destinations; report the origin block and never treat a clean scan as execution approval. Mandatory later gates do not authorize additional work.

Inspect executable navigation/request destinations in specs, called helpers/hooks/config and generator output/redirects. Resolve relative URLs; compare scheme, hostname and effective port to the approved origin; API requests may also use separately approved loopback stack destinations. Other origins, including loopback aliases/ports: BLOCKED. Unknown/dynamic: unresolved, BLOCKED until proven. Inactive comments and href-only assertions do not block solely for URL strings. With `e2e-reviewer`, always scan each changed spec file separately: `/bin/bash -p <its skill dir>/scripts/scan.sh --fail-on p0 <one spec file>; echo "scan exit=$?"` (use its loaded skill copy; no project ESLint opt-in; never pipe or truncate it). Exit 0 means no confirmed P0; exit 1 with a Summary means confirmed P0; exit 2, INCOMPLETE, or no Summary means not clean. Resolve retained P0/P1 candidates before proceeding; completed execution or P0=0 does not clear them. Fix printed P0/P1, at most 3 passes; P0 or P1 left or scan not clean: report BLOCKED, never claim completion.

Confirm the effective `baseURL` (config plus env) is the approved origin; if not, do not run. Recheck section 1 whole-stack safety for drift. Reuse unchanged scoped evidence and approvals. Run the approved test command on new specs only against a disposable stack. Before the first native run after exploration and every retry of a write scenario, establish its starting state using approved fixtures, reset or cleanup; unavailable or unapproved: BLOCKED. Never reset unrelated data or require reset for read-only scenarios.

Or official `test_run` with approved exact `locations` (new specs; never omit `locations`) and approved `projects`, or confirm the sole project. Origin approval is not project approval. Prove its loaded config, environment, project and origin match the approved command. Unknown/broader scope: BLOCKED. Use one execution method; never disable the sandbox. Record the execution owner and native pass/fail/skip counts; MCP transport success alone is not test success. Match every planned scenario to an actual native attempt with status `passed` in its approved applicable projects; an expected failure, zero tests or a missing, skipped, interrupted or failed required scenario: BLOCKED, not complete. Skips outside those applicable targets do not block completion. Evaluator runs do not count as agent execution.

Absent: report skipped gate; suggest `e2e-reviewer`. Skipped gate/run: not complete.

Compare failures to native evidence, scenario, app. For locator repairs, verify the intended target and unique match in the failing UI state before rerunning; never guess from timeout alone. Product defects or uncertain causes: report BLOCKED; use `playwright-debugger` (NOFIX). For proven generation errors, the parent may make at most two repairs. Preserve required outcomes and expected values; replace an incorrect added assertion only with evidence-backed coverage of its intended check. Never skip tests, drop required checks or change the app. Repeat the origin/scanner gates on changed specs and use the same approved execution method. Still failing: BLOCKED.

## 6. Report

Files; planner use/skip; repairs; per changed spec: `scan exit=` and Summary lines verbatim; tests run/skipped; NOT done: all unrun checks. Installed scanner not run, exit 2, INCOMPLETE: BLOCKED. Offer opt-in fault checks; never claim they ran.
