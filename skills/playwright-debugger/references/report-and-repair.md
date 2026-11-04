## Report and repair

Read this before verifying a repair or writing a diagnosis report (SKILL.md section Output). Extraction-only responses stop before this reference. The safety, redaction and excerpt rules stay in SKILL.md.

## Verify and review

Run the checklist in every diagnosis or repair case before output:
- Check every identifier, selector, endpoint and line number in Root Cause/Fix against the artifact or source read this session.
- State a cause only when evidenced; otherwise use a hypothesis plus missing evidence.
- Decide the product/test axis first; never weaken, widen, skip or delete a correct assertion to manufacture green. Change only an evidenced wrong assertion.
- Check the F-table's Review Pattern column for P0/P1 smells; add no fixed sleeps/`waitForTimeout`, `networkidle`, force clicks, swallowed `.catch`, conditional assertions or bare `.first()`.

1. Diagnosis or prose-only fix: no reviewer call.
2. Spec/POM edited at the user's request: under the execution-safety and repository-trust/command/environment gates, rerun the narrowest repository-native test with `--retries=0`. Otherwise mark the exact command `recommended`. If sibling `e2e-reviewer/scripts/scan.sh` exists, run the reference's pinned scan once per edited file and require P0=0; otherwise report `scan: not run (<reason>)`. Absent, blocked or incomplete scans are not clean.
3. Generated-candidate or verification-probe repair (explicit user/caller or artifact provenance identifies the failing test as a generated candidate or verification probe): apply the mechanics-only boundary in `references/fix-verification.md`; emit the exact line `V6: required (caller)`. The caller (the user, or whoever generated the candidate) owns any independent V6; pending V6 is not approval/completion. For edited files also apply case 2. An approved plan or `specs/` path alone does not establish this provenance; ordinary handwritten-test repairs follow case 2 and may correct an evidenced wrong assertion without requiring caller V6.

Never load `e2e-reviewer` inline or spawn a reviewer; the debugger cannot approve its own repair. Apply the reference's proof labels.

## Output fields

Report failed/flaky totals, then one finding per failure; keep fields on one line except Fix code:

```text
test name — Fxx Category
F-code / confidence: code or CANNOT_VERIFY / high|medium|low
Diagnosis axis: product regression|test defect|unknown
Product impact: consequence and reach, or unknown
Test-reliability urgency: critical|high|medium|low
Test-quality severity: P0|P1|P2 for confirmed test defects; otherwise N/A
Error excerpt source: bundled reader|safely redacted direct input|unavailable placeholder
Error excerpt: "sanitized excerpt, max 500 characters"
Root Cause: observed failure; evidenced cause or hypothesis plus missing evidence
Verification: V2–V6 recommended | ran: <command> -> <result> | CANNOT_VERIFY: <missing evidence> | N/A
Fix: evidence-backed code if source read; otherwise prose
```

For cases 2–3 only, add `Review: scan P0=<n> P1=<n> P2=<n> | scan: not run (<reason>)`; case 3 also emits `V6: required (caller)` on its own line.

Keep mechanism, product impact, urgency and test-quality severity independent. For an unknown axis use literal `unknown` impact and `N/A` severity. Never infer P2 from F4/F5/F8/F9/F10/F12 alone. Grade confirmed test defects only: P0 silent pass while broken; P1 intermittent/misleading failure; P2 brittleness/maintenance. Prioritize product impact and independent test severity.

## Triage summary

End with this counts-only roll-up; add no diagnosis or review narrative:

| Diagnosis axis | Product impact | Test urgency | Test-quality severity | Count | Files |
|---|---|---|---|---|---|

Dedupe by `file` + `title` across projects in summary totals; aggregate affected `projectName` values into one row.
