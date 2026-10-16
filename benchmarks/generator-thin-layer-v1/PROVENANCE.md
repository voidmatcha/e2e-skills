# Thin rules provenance

This is a deliberately small supplement to the official Playwright generator, not a replacement generator workflow. Install the bytes of [THIN-RULES.md](THIN-RULES.md) as a directory's `SKILL.md`; the synthetic successor stages them read-only at `/work/skill/thin-rules/SKILL.md`. The supplement includes only general generation rules, without task-specific selectors or scoring instructions.

The source references below were read locally on 2026-10-15. Line numbers describe that checkout; the campaign freeze must bind both source and supplement digests. Source links: [code-rules.md](../../skills/playwright-test-generator/code-rules.md), [best-practices.md](../../skills/playwright-test-generator/best-practices.md), and [scenario-design.md](../../skills/playwright-test-generator/scenario-design.md).

The evidence labels refer to the owner's 2026-10-15 development-stage audited report supplied in the build brief. This build did not independently recount finished outputs, and the numbers are not a sealed or confirmatory result:

- E1: Working official generator tools already produce robust specs on strong models; the owner reports all Opus arms at 1.00, with the full skill costing about five times as much.
- E2: The owner identifies avoiding CSS id/class coupling as the main measured benefit of the full skill.
- E3: Generic numbered titles occur in 38-47 of 54 official specs, compared with 0 of 57 full-skill specs. The reported range is retained; this build does not infer its arm/model denominator.
- E4: The owner reports positional locators, one-test-per-file layout, and `toHaveClass` state assertions in official outputs that full-skill outputs avoid; counts were not supplied.
- E5: No comparative frequency for missing awaits, hard waits, vacuous assertions, or unexecuted tests was supplied. Their inclusion is preventive and source- or owner-policy-based, not an observed treatment effect.
- E6: Supplied independent finished-run analysis attributes about 56% of an example reviewer pass to reviewer skill/reference loading, with roughly 25–28k newly loaded text tokens per pass; reviewer calls account for about 58–59% of generation-plus-review dollars in the analyzed Claude arms. Attribution uses transcript-derived text estimates and cost decomposition rather than a randomized ablation. The deterministic scanner uses no model tokens and negligible direct dollars; model context for the command/result and repair work still costs tokens. The accompanying debugger attribution concerns a different workflow and does not establish generator effects. These observations motivate arm E, not a prediction of its benefit or cost.

Rules are numbered here by checklist order only. Every rule occupies one checklist line in the installed file.

| Rule | Source lines and derivation | Observational basis |
|---|---|---|
| 1. Semantic locators | `code-rules.md` 31-41; `best-practices.md` 38-41; `scenario-design.md` 5-10: roles, actual labels, configured test ids and visible text. | E2; E1 motivates retaining a small supplement. |
| 2. No CSS id/styling class selectors | `code-rules.md` 38, 43, 45; `best-practices.md` 41-42; `scenario-design.md` 86. The blanket CSS id prohibition is an explicit owner-required tightening: the source permits documented/JUSTIFIED id exceptions. Attribute equivalents preserve the prohibition's meaning. | E2. No claim that this exact stricter rule has already been evaluated. |
| 3. Scope repeated text semantically | `code-rules.md` 43; `best-practices.md` 40-41: scope by ancestor or filter rather than position. | E2, E4. |
| 4. Justify positional locators | `code-rules.md` 39, 267-270; `scenario-design.md` 85: immediate `JUSTIFIED` comment. | E4. |
| 5. Await actions and assertions | `code-rules.md` 9-10, 128, 149; `best-practices.md` 48-50, 90. | E5; no measured incremental benefit asserted. |
| 6. Observable/ARIA state, not classes | `scenario-design.md` 38-40, 48; `code-rules.md` 128, 209; `best-practices.md` 48, 52. Banning styling-class state and `toHaveClass` is an explicit owner-required policy extension of observable-contract assertions, not an existing verbatim source rule. | E4. |
| 7. Conditions, not hard waits | `code-rules.md` 14, 137; `best-practices.md` 87. | E5; preventive only. |
| 8. No vacuous assertions | `code-rules.md` 141 explicitly rejects locator truthiness; `scenario-design.md` 48-53 requires an observable outcome with a falsification/fault contract. Rejecting constant assertions is the owner-required generalization, not a quoted source prohibition. | E5; preventive only. |
| 9. Behaviour-describing titles | `scenario-design.md` 37-40 calls for a descriptive title; `code-rules.md` 97, 109 supplies behaviour-describing test titles. Rejecting generic numbered placeholders makes the owner's requirement explicit. | E3. |
| 10. Group a screen in one file | `code-rules.md` 89-120 demonstrates two related independent behaviours in one describe/spec; 124-125 requires test independence. Screen-level file grouping is an owner-required policy synthesis, not an explicit rule in the three source documents. | E4. |
| 11. Execute and repair before completion | `code-rules.md` 3 makes verification a completion condition and preserves the outcome during repairs; `best-practices.md` 18 requires the existing command. Running generated tests at least once and fixing failures is the owner's explicit minimal delivery requirement; the three sources do not prescribe this exact reduced workflow. | E5; preventive only. |

## Size and accounting

Sizes count complete UTF-8 file bytes, including frontmatter and final newline. Token counts below are planning estimates using `ceil(bytes / 4)`, not model-tokenizer measurements. No tokenizer dependency was installed. The three-source total is a comparison of reference text only, not the full skill's runtime context or billed usage.

| Surface | UTF-8 bytes | Estimated tokens |
|---|---:|---:|
| Installed thin `SKILL.md` bytes | 1,883 | 471 |
| One added prompt line, without newline | 95 | 24 |
| Thin bytes plus prompt line | 1,978 | 495 |
| Full generator `SKILL.md` only | 28,847 | 7,212 |
| Source `code-rules.md` | 25,133 | 6,284 |
| Source `best-practices.md` | 9,988 | 2,497 |
| Source `scenario-design.md` | 9,864 | 2,466 |
| Three source files combined | 44,985 | 11,247 |

The one added prompt line is exactly `Read and follow /work/skill/thin-rules/SKILL.md; pass this instruction to the generating child.` A line terminator adds one byte; its serialized framing is not included in this estimate. The supplement has 617 bytes of headroom under the 2,500-byte hard limit.

Pre-declare 471 estimated content tokens and 24 estimated prompt-line tokens per initial read for planning and expose that overhead separately. Do not add these estimates to measured billing totals: parent/child rollout input already includes reads, repeat exposure and prompt text. Actual token and cost endpoints must use the inherited v3 accounting, show cached versus uncached input and child usage, and report incomplete evidence. The estimate cannot certify that a model read the file, that a child inherited it, or that the change costs exactly 495 tokens.

## Scanner-gate amendment

The synthetic design (arms A, D and E scheduled by default; B optional; C a labeled v3 reference unless re-run, see the budget amendment below) retains the exact thin rules bytes for D and E. E adds only the pinned scanner runtime scripts mounted read-only at `/work/skill/scanner` and one scanner-gate prompt line, defined exactly in the [protocol](../generator-thin-eval-v1/protocol.json) and runner. The exact command is `/bin/bash -p /work/skill/scanner/scan.sh tests/`. Its 13-file runtime manifest is distinct from the inherited v8 scoring scanner; E uses the current scanner bytes also staged for B. It does not stage reviewer `SKILL.md`, references, agent definitions or the full reviewer directory. B retains the predecessor full reviewer pass over matched A output; C retains the full generator 2.0.1 reference. This tests D−A, E−D, E−B (when B is scheduled) and C−E (cross-campaign descriptive by default) separately. E6 motivates separating deterministic scanner feedback from the full reviewer text and reasoning, but the combined E treatment cannot attribute gains separately to individual scanner findings or repairs.

Scanner source bytes and the extra line are treatment inputs, not an estimate of runtime billed tokens. The scanner executable consumes no model tokens; its prompt, returned findings, repeated context, child copies and repairs enter observed parent/descendant usage. Preserve all attempts and report B’s generation-plus-review pipeline, each other arm’s own pipeline, cached versus uncached tokens, missing usage, and quality per 100k processed tokens. Do not add the thin-file size estimate or scanner source size to measured usage a second time.

## Codex budget and v3 mid-run amendment

The following are development observations from a Claude audit of the running Codex v3 campaign on 2026-10-15 (finding ids F1 to F5 of that audit) and from supplied cost analysis. They were read from the audit report in the build brief; this build did not recount the finished outputs, and none is a confirmatory result. They motivate the arm set, the budget, the roster size and the generation-harness repairs; they do not predict effects for the thin arms.

- F1 (limit burn): the account-wide weekly Codex limit went from 27% to 34% over 65 minutes and 19 cells (9 arm A, 10 arm C), about 7 points per hour or 0.37 per cell, with integer-rounded percentages; the window resets 2026-10-20 22:00 KST. The percentage includes any other Codex use on the account. The thin budget derives per-arm points from this by splitting in proportion to rollout tokens; the D, E and B figures are assumptions.
- F2 (cost accounting): the per-attempt usage in `final.json` is the parent rollout only. For arm A the child carries most of the work (roughly 874k input and 4.7k output against the parent’s 195k and 2.3k), so reading `final.json` alone understates arm A by about 5x. With children included the per-cell means were about 58k uncached-plus-output and 1.08M total tokens for arm A and about 133k and 2.35M for arm C. Every thin cost and budget number is rollout-derived for this reason.
- F3 (shared-server state): with `reuseExistingServer` true in the generation phase, the child’s browser exploration mutated the running app and the parent’s single test run then failed on stateful tasks (4 of 9 arm-A cells: all three v2-23 and one v2-06). The specs were left unchanged by design, so those cells count as delivered although the model never saw them pass. Arm C is not affected because it does not use the MCP session’s server. The thin runner gives arms A, D and E separate exploration and test-run ports.
- F4 (fidelity depth): the official-tool class is satisfied by minimal generator use; one arm-A cell made 7 setup and 7 write calls with no click, type, navigate or snapshot. Eight of nine cells had 9 to 16 mutating browser calls. The thin runner reports browser interaction counts beside the class.
- F5 (scoped writes): `.playwright-mcp/page-*.yml` snapshots were recorded as out-of-scope writes in 6 of 9 arm-A cells, and a node_modules link swapped inside the container appeared as a tracked change that cost the agent investigation commands. The thin runner git-excludes both paths and lists the snapshots separately.
- E6 remains the motivation for the scanner-only gate: reviewer passes dominate generation-plus-review cost because each pass cold-starts 25 to 28 thousand reviewer-skill tokens, which is why B is optional in the budget-constrained first stage.

Limits: one model, one account, a partly complete campaign, and an audit that read rollouts rather than rerunning anything. The harness repairs are unproven live; the per-arm budget multipliers for D, E and B are assumptions to be replaced by the first measured cells.

## CLI-first workflow amendment (arm F and optional arm G)

The CLI guide staged for arms F and G ([CLI-GUIDE.md](../generator-thin-eval-v1/CLI-GUIDE.md), at most 1,000 bytes, THIN-RULES.md unchanged) is derived from two checked sources and one development observation; it is not a result and predicts no effect.

- Checked source instructions: `skills/playwright-test-generator/exploration-preflight.md`, sections Browser source selection and containment and Guard for Playwright CLI, read in this build. The guard requires a deny-by-default origin allowlist written outside the worktree, a fresh uniquely named session opened with that config, a blocked-origin fetch proven to fail with `net::ERR_BLOCKED_BY_CLIENT` before navigating, and the session closed afterward. The guide keeps those four steps and drops the approval, project-local and browser-discovery prose.
- Development observation (not recounted as a confirmatory result): the commands of the 24 successful arm-C cells in the finished gpt-6-sol v3 transcripts were read offline. Their sequence was `npx --no-install playwright cli -s=<name> --config <outside config> open --browser chromium`, a fetch probe through `eval`, `requests`, `goto`, `snapshot`, then `click`, `fill`, `select`, `press`, `reload` and `close`. Failures in those cells shaped the text: `open` without `--browser chromium` failed in three cells in the pinned image; `select-option` and `press eN Enter` are not commands; `eval` takes a function and an `await page.evaluate(...)` expression raised a syntax error while still exiting 0.
- Token accounting: the guide’s estimate is `ceil(bytes / 4)` like the rules; it is part of observed context and is never added to rollout usage. Arm F has no child agent, so its role split in reports is parent only; any child found is recorded and blocks the F decision.
- Limits: one model, one account, a CLI sequence the model chose while following a different skill. Whether a model follows this shorter guide, and whether the CLI surface matches the MCP surface in quality and tokens, is the experiment’s question and is unmeasured. The thin rules still say “alongside the official generator”; F has none, which is disclosed in the README rather than edited into the frozen text.
