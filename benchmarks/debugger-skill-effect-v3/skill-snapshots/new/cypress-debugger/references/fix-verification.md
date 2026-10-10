## Phase 4: Fix Verification

### Verification-rule handoff

Preserve the F1–F15 classification and add the smallest relevant proof recommendation; V-rules do not replace F-codes:

- V2 temporary inversion for supported `.should()`/`expect` assertion shapes.
- V3 `cy.intercept()` fault injection for response/data dependency questions.
- V4 intercept alias plus `cy.wait()` request method/URL/body/cardinality proof for writes and optimistic UI.
- V5 repository-native solo/repeat/suite-context runs for timing, isolation, or retry evidence.
- V6 independent re-review after any generated-test repair.

Do not install a verifier or require `npx`. Reuse the repository's existing targeted Cypress command and tooling. Label a proof `recommended` unless an actual command/result shows it ran; use `CANNOT_VERIFY` with the exact missing evidence when no safe probe exists.
