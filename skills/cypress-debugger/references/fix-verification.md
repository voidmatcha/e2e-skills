## Phase 4: Fix Verification

Before any execution, browser request, or artifact write in this procedure, read `references/safety-procedures.md` and apply its gates.

### Verification-rule handoff

Preserve F1–F15; recommend the smallest applicable proof for every fix, including ordinary fixes:
- V2 assertion falsification by temporary inversion of a supported `.should()`/`expect` primary matcher: F4/F5/F6/F13 or other load-bearing assertion questions; unchanged normal candidate passes, inverted primary turns red.
- V3 `cy.intercept()` fault injection at an evidenced response/data dependency: F3/F9; unchanged primary assertion turns red.
- V4 intercept alias plus `cy.wait()` request method/URL/body/cardinality proof plus an injected failed write: when the approved scenario promises request delivery/persistence or the diagnosis depends on write success/failure, regardless of F-code; never accept optimistic state alone as proof of that contract.
- V5 repository-native solo/repeat/suite-context runs at normal supported parallelism: F1/F7/F8/F11/F14/F15; reuse classification's bounded isolation probes and replay gates.
- V6 independent re-review after any generated-test repair: all F-codes; the caller owns the single pass. Emit `V6: required (caller)`; never PASS inline.

Do not add a backend-proof requirement to a UI-only repair solely because the application sends a request. Preserve every existing approved request or persistence check; this scope rule does not exempt an evidenced write defect.

Do not install a verifier or require `npx`; reuse the repository's targeted command. Label proof `recommended` unless an actual command/result shows it ran; use `CANNOT_VERIFY` with the exact missing evidence when no safe probe exists.

### Generated-test repair boundary

First establish explicit user/caller or artifact provenance that the failure came from a generated candidate or verification probe. An approved plan or `specs/` path alone does not establish this provenance. Ordinary handwritten-test repairs may correct an evidenced wrong assertion under case 2 without requiring caller V6. Only after establishing generated/probe provenance, obtain the approved plan (the user's request, a `specs/` plan, or an archived plan path) before changing a candidate; keep each scenario's title, action, primary outcome, V1 completion evidence or `CANNOT_VERIFY` reason, assertion target and expected value available.

**Generated-test repair boundary:** when the failure came from a generated candidate or a verification probe, expected values, the approved primary outcome, assertion target, scenario count, request proof, and test enablement are immutable. Repair only evidence-backed mechanics (selector, retryable command/query strategy, navigation, fixture, setup order, or test data). Never delete/skip the test, remove intercept/alias proof, or accept an optimistic toast in place of a write contract. Return `NOFIX: <evidence>` when the approved contract and observed product behavior disagree. Independent V6 remains required before completion; the debugger never approves its own repair.

For generated-candidate repairs the debugger emits `V6: required (caller)` plus the approved-fields packet (the user's request, the `specs/` plan or archived plan path, the repaired spec path, and each scenario's title, action, primary outcome, assertion target and expected value). It never dispatches a reviewer and never quotes or invents a verdict; the caller (the user, or whoever generated the candidate) owns any independent re-review and a missing verdict leaves V6 pending, not passed.

### Deterministic scan for edited files

Resolve the reviewer only next to the actual loaded debugger skill; do not install or search for another copy. Under case 2's gates, run once per edited spec/POM, with one path per invocation:

`E2E_SMELL_ALLOW_PROJECT_ESLINT=0 E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 E2E_SMELL_DISABLE_AST_GREP=1 /usr/bin/env -u E2E_SMELL_RG_BIN -u E2E_SMELL_NODE_BIN -u E2E_SMELL_NPX_BIN -u E2E_SMELL_AST_GREP_BIN -u E2E_SMELL_PYTHON_BIN /bin/bash -p <e2e-reviewer skill-base>/scripts/scan.sh <one spec or POM path>`

Read the scanner result by exit code: exit 0 means P0=0; exit 1 with a printed Summary means P0>0, so report the counts and do not call the edit clean; reserve `CANNOT_VERIFY` for exit 2, an INCOMPLETE result or a missing Summary. If absent or gated off, report `scan: not run (<reason>)`; the inline checklist still applies. P1/P2 counts remain visible. Changing the pinned settings requires repository trust and exact command/environment approval; never load the reviewer skill inline.
