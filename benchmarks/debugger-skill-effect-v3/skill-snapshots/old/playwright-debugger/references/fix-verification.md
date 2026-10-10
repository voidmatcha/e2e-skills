## Phase 4: Fix Verification

### Verification-rule handoff

Preserve the F1–F15 classification and add the smallest relevant proof recommendation; V-rules do not replace F-codes:

- V2 assertion falsification for swallowed, conditional, missing-await, or load-bearing-assertion questions.
- V3 `page.route()` fault injection for response/data dependency questions.
- V4 request method/endpoint/payload/cardinality proof for writes and optimistic UI.
- V5 repository-native solo/repeat/suite-context runs for timing, isolation, or retry evidence.
- V6 independent re-review after any generated-test repair.

Do not install a verifier or require `npx`. Reuse the repository's existing targeted command and tooling. Label a proof `recommended` unless an actual command/result shows it ran; use `CANNOT_VERIFY` with the exact missing evidence when no safe probe exists.
