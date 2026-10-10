# Blind F-code mapping task (v3)

You map 28 real, already-diagnosed E2E test failures onto the F1-F15 taxonomy. For each item you see ONLY the
maintainers' root-cause statement and the merged fix. Read only these files; do not read anything else under
benchmarks/, scripts/, skills/ or the scratchpad, and do not search the repository for answer keys.

1. `/Users/user/Documents/e2e-skills/benchmarks/debugger-skill-effect-v3/skill-snapshots/new/playwright-debugger/SKILL.md` section "Phase 2: Classify Root Cause" (the F1-F15 table and the tie-break paragraph under it) and `/Users/user/Documents/e2e-skills/benchmarks/debugger-skill-effect-v3/skill-snapshots/new/playwright-debugger/references/classification-procedure.md`
2. `/Users/user/Documents/e2e-skills/benchmarks/debugger-skill-effect-v3/skill-snapshots/new/cypress-debugger/SKILL.md` same section and `/Users/user/Documents/e2e-skills/benchmarks/debugger-skill-effect-v3/skill-snapshots/new/cypress-debugger/references/classification-procedure.md`
3. The packet: `/private/tmp/claude-501/-Users-user-Documents-e2e-skills/16672ab7-1ff3-4057-b912-24edbbc68259/scratchpad/blind3/packet.md`

For each item give: `f_code` (the single F-code whose definition best matches the stated mechanism), `second_choice`
(or null), `fit` ("clean" if one code clearly matches; "forced" if no code fits well and you picked the least bad),
and `reason` (one sentence). Write ONE strict-JSON file to the output path in your prompt:
{"item-01": {"f_code": "F?", "second_choice": "F?", "fit": "clean|forced", "reason": "..."}, ... all 28 ...}
Then reply with just "done: <path>" and the count of items you marked forced.
