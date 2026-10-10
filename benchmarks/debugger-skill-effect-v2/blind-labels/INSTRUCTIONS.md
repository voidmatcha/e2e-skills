# Blind F-code mapping task

You map 26 real, already-diagnosed E2E test failures onto the F1-F15 taxonomy. For each item you see ONLY the
maintainers' root-cause statement and the merged fix (not the failure artifact, not any other label).
Read only these files; do not read anything else under benchmarks/, scripts/evals/, or the scratchpad, and do
not search the repository for answer keys.

1. `/Users/user/Documents/e2e-skills/skills/playwright-debugger/SKILL.md` section "Phase 2: Classify Root Cause" (F1-F15 table) and `/Users/user/Documents/e2e-skills/skills/playwright-debugger/references/classification-procedure.md`
2. `/Users/user/Documents/e2e-skills/skills/cypress-debugger/SKILL.md` same section and `/Users/user/Documents/e2e-skills/skills/cypress-debugger/references/classification-procedure.md`
3. The packet: `/private/tmp/claude-501/-Users-user-Documents-e2e-skills/16672ab7-1ff3-4057-b912-24edbbc68259/scratchpad/blind2/packet.md`

For each item give: `f_code` (the single F-code whose definition best matches the stated mechanism), `second_choice`
(or null), `fit` ("clean" if one code clearly matches; "forced" if no code fits well and you picked the least bad),
and `reason` (one sentence). Write ONE strict-JSON file to the output path in your prompt:
{"item-01": {"f_code": "F?", "second_choice": "F?", "fit": "clean|forced", "reason": "..."}, ... all 26 ...}
Then reply with just "done: <path>" and the count of items you marked forced.
