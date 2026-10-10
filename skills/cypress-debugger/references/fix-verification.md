## Phase 4: Fix Verification

### Verification-rule handoff

Preserve the F1–F15 classification and add the smallest relevant proof recommendation; V-rules do not replace F-codes:

- V2 temporary inversion for supported `.should()`/`expect` assertion shapes.
- V3 `cy.intercept()` fault injection for response/data dependency questions.
- V4 intercept alias plus `cy.wait()` request method/URL/body/cardinality proof for writes and optimistic UI.
- V5 repository-native solo/repeat/suite-context runs for timing, isolation, or retry evidence.
- V6 independent re-review after any generated-test repair.

For a generated candidate, obtain the approved scenario plan before changing it. Keep each scenario's title, action, primary outcome, V1 completion evidence or `CANNOT_VERIFY` reason, assertion target, and expected value available during repair. When dispatching V6 after a repair, copy those approved fields and the applicable generator V1 primary-outcome subsection **verbatim into the outgoing message** to the separate read-only reviewer, along with the repaired spec path. For `playwright-test-generator`, copy the single block from `## V1 — Primary Outcome` through the line immediately before `## V2 — Assertion Falsification`, preserving its heading, text, list, punctuation, and `Unchanged outcomes` wording. Ask the reviewer to trace the action-specific completion observation to the unchanged primary assertion. Inspect the message actually sent before dispatch and retain it or its transcript. A path, link, attachment reference, or instruction to read the V1 source is not the copied block; nor is a paraphrase. A reviewer `PASS` does not establish V6 when the literal approved fields or applicable V1 block are missing. Correct the packet with a fresh reviewer, or report `CANNOT_VERIFY`. Do not let this handoff substitute for browser-backed V1 evidence.

Do not install a verifier or require `npx`. Reuse the repository's existing targeted Cypress command and tooling. Label a proof `recommended` unless an actual command/result shows it ran; use `CANNOT_VERIFY` with the exact missing evidence when no safe probe exists.
