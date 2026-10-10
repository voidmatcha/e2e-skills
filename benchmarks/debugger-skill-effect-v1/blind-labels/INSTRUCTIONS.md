# Blind labeling task

You are an independent labeler for 30 sanitized E2E test-failure excerpts. You must work only from the
materials named below. Do NOT read any other file under `benchmarks/`, `scripts/evals/`, or the scratchpad
directory, and do not search the repository for answer keys. Do not run any model calls or shell commands
other than reading the files listed here.

Materials (read all three first):
1. `/Users/user/Documents/e2e-skills/skills/playwright-debugger/SKILL.md` — section "Phase 2: Classify Root Cause" (the F1–F15 table) and `/Users/user/Documents/e2e-skills/skills/playwright-debugger/references/classification-procedure.md`
2. `/Users/user/Documents/e2e-skills/skills/cypress-debugger/SKILL.md` — the same section — and `/Users/user/Documents/e2e-skills/skills/cypress-debugger/references/classification-procedure.md`
3. The packet: `/private/tmp/claude-501/-Users-user-Documents-e2e-skills/16672ab7-1ff3-4057-b912-24edbbc68259/scratchpad/blind/packet.md` (30 items, `item-01` … `item-30`; each is one JSON excerpt whose `framework` field says playwright or cypress)

For every item decide, from the excerpt evidence alone:
- `f_code`: exactly one of F1 … F15 (the single best-supported failure mechanism)
- `diagnosis`: `product_regression`, `test_defect`, or `unknown`
- `second_choice`: the F-code you would pick if your first were wrong (or null)
- `ambiguous`: true only if you think two codes are equally well supported by the excerpt
- `reason`: one sentence of evidence

Write ONE file, strict JSON, no prose, to the output path given in your prompt:
{"item-01": {"f_code": "F?", "diagnosis": "...", "second_choice": "F?", "ambiguous": false, "reason": "..."}, ... all 30 items ...}

Then reply with just: "done: <output path>" and the count of items you marked ambiguous.
