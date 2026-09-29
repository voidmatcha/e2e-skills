# Billing E2E conventions

- Quarantine: a flaky test is skipped with a bare `test.skip(...)` and listed by its exact
  title on the QA quarantine board, which owns the reason and the revisit date. Do not add
  inline skip reasons; the board is the single record.
- Feature flags: assertions for flagged features may be wrapped in `if (flags.<name>)`.
- `force: true` is accepted in this repository.
