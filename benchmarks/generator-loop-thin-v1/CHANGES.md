# Changes: thin-layer autoresearch loop v1

## 2026-10-15: owner decisions (pre-freeze, nothing frozen)

- Guard profile STRICT. A low false-adopt rate is preferred to missing a real improvement, because a false adoption stacked on a tiny rules file is the main risk. `prepare` now defaults to `strict` (previously an explicit `--guard-profile` was required); `noise-tolerant` stays registered but is not chosen.
- Dev tasks: the synthetic dev split only at first (`v2-11`, `v3-08`, `v2-18`). The Zeppelin dev tasks are removed from the default list and kept as an opt-in list (`prepare --include-zeppelin`, recorded in the campaign config and bound at freeze), with the shared-proxy F3 hazard disclosed.
- Consequences recorded in `protocol.json` and the README: six cells per batch (ten with the opt-in); generation budget 162 cells (168 with `aa3`; 270 and 280 with the opt-in); layer-read threshold 0.9 means 6 of 6 by default; the decision simulation was regenerated for three tasks and the five-task table is kept as `results_with_zeppelin_opt_in`; packet labels T1 to T3.
- Runner: `use_zeppelin()`, `batch_cells()` and `DEFAULT_GUARD_PROFILE` added; hard-coded batch sizes of 10 now follow the active task list. The staged Zeppelin pool, shared runtime and reference calibration stay prerequisites of the shared machinery and are unchanged.
- Tests: the suite runs the full five-task machinery in opt-in mode and adds default-mode tests.

## 2026-10-15: second independent review repairs (pre-freeze, nothing frozen)

- F1 official-tool fidelity is now an adoption requirement (decide, failing, entry gate LOW_FIDELITY).
- F2 calibration covers the active mode's tasks; offline synthetic calibration added; Zeppelin calibration only with the opt-in.
- F3 void cells count toward the budget; bounded recorded `retry-void` for infrastructure voids; no result peeking.
- F4 no per-task regression on both paths; pooled confirmation gate (disjoint cells, 3-cell pooled threshold). Simulation tables regenerated.
- F5 offline static inner stage before any live cell; F7 evasion-resistant wording screen and risky-action screen.
- F6, F8 low power and skeleton redaction limits documented; F9 alignment with thin-eval arm D documented, entry check fixed; F10 one saturation rule for bytes and line count.
- Tests: 233 existing plus the new classes; the existing helpers gained `fidelity_class` on cells, a synthetic-aware calibration record, and distinct filler rules.
