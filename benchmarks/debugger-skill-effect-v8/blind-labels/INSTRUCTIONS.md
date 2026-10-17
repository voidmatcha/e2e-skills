# Blind F-code mapping task (v8)

You map 60 real or authored, already-diagnosed E2E test failures onto the F1-F15 taxonomy. For each item you see ONLY the
root-cause statement and the fix. Read only the two files named below. Do not read anything else under benchmarks/, scripts/,
skills/ or the scratchpad, and do not search the repository for answer keys or for the item-to-case map.

1. The F1-F15 table and the paragraph under it ("Classify inline in this order"): section "Phase 2: Classify Root Cause" of the
   released 2.0.1 text, `benchmarks/debugger-skill-effect-v8/skill-snapshots/old/playwright-debugger/SKILL.md` (the F1-F15 table is
   the same in both frameworks). Do not read the references/ files.
2. The packet: `benchmarks/debugger-skill-effect-v8/blind-labels/packet.md`

For each item give: `f_code` (the single F-code whose definition best matches the stated mechanism), `second_choice`
(or null), `fit` ("clean" if one code clearly matches; "forced" if no code fits well and you picked the least bad),
and `reason` (one sentence). Write ONE strict-JSON file to the output path in your prompt:
{"item-01": {"f_code": "F?", "second_choice": "F?", "fit": "clean|forced", "reason": "..."}, ... all 60 ...}
Then reply with just "done: <path>" and the count of items you marked forced.
