# `full-fixed` arm: what changed and why (design material, not frozen)

`playwright-test-generator/` in this directory is a copy of `skills/playwright-test-generator/` at commit `0c37f08` (the working tree was clean for that directory) with six bounded edits applied, minus `scripts/`: any runner stages the scripts from `skills/playwright-test-generator/scripts/`, which the patch does not touch (user decision, 2026-10-06). Nothing under `skills/`, `scripts/ci/`, or `benchmarks/generator-skill-effect-v2/` was touched; v2 stages the real skill and must finish first.

- `PATCH.diff`: `git diff` of the skill directory, applicable later with `git apply benchmarks/generator-skill-effect-v3/arms/full-fixed/PATCH.diff` from the repository root. It excludes `evals/evals.json`; the five new evals live in `../../pending-repo-changes/`.
- `apply-full-fixed.py`: the exact string replacements that produced the copy (27 edits, each required to match once). Rerun it on a fresh copy of the skill to regenerate the arm. Content digest of this copy (`find . -type f | sort | xargs shasum -a 256 | shasum -a 256` inside `playwright-test-generator/`): `95acd4857baf9b4bed961cf559396dbff02fe01b3f22cb28e63f9cfbadc72bb5` (without `scripts/`; item 1 revised after the security review, scanner invocation given as one inline code span because the contract test forbids fenced bash in `SKILL.md`). `git apply --check PATCH.diff` succeeds against the repository skill at `0c37f08` (re-checked 2026-10-06 after the user's decisions). The fixes ship inside the unpushed `2.0.0` release; `version` stays `2.0.0`.
- Verification (run in a disposable clone under `~/.cache`, never in the repository): `scripts/ci/check-verification-parity.sh` passes on the fixed copy; the current `scripts/ci/test-generator-contracts.py` passes on the fixed copy except for one pin that encoded a self-reference (`(rationale: \`exploration-preflight.md\`)`), which the pending contract patch retargets; with that patch the contracts pass on the fixed copy (GREEN) and fail on the current text (RED); `scripts/validate-evals.sh` accepts the five new evals (49 total).

## Hunk map

The edit ids are the names in `apply-full-fixed.py`; each maps to one hunk group in `PATCH.diff`.

| Item | Edit id(s) | File | Change |
|---|---|---|---|
| 1 | `item1-scope`, `item1-step3`, `item1-step4-table`, `item1-launcher-owned`, and the scanner part of `item3-step6` | `SKILL.md` (safety preamble, Step 3, Step 4 command table, Step 6), `exploration-preflight.md` § Preflight launcher | Closed list of exactly three skill-owned scripts (preflight launcher, frame writer, `scan.sh`), exempt only when their real paths lie outside the target repository and, for `scan.sh`, only under the pinned invocation (`E2E_SMELL_ALLOW_PROJECT_ESLINT=0 ... E2E_SMELL_DISABLE_AST_GREP=1 /usr/bin/env -u E2E_SMELL_*_BIN ... /bin/bash -p scan.sh <one path>`, one path per invocation); Step 3's safety gate still governs the probe; `run-raw-aria-snapshot.sh`, project binaries, the debuggers' `download-*`/`publish-*` scripts, `pom-ownership-candidates.py`, and any other `E2E_SMELL_*` setting stay approval-gated; an environment variable alone is never approval. Revised after the security review (`../../security-note-item1.md`) |
| 2 | `item2-v6` | `verification-rules.md` § V6 | "Obtaining the reviewer": Claude Code `Agent` tool (read-only subagent), Codex named agent or `spawn_agent`, or any fresh process; what to pass; the single line `V6 VERDICT: <PASS\|FAIL> P0=<n> P1=<n> P2=<n> reviewer=<id>` to quote verbatim; a reduced-Phase-1 reviewer still yields a verdict; no host isolation proof beyond a fresh context is required; no actor means `CANNOT_VERIFY`, never inline |
| 3 | `item3-step6`, `item3-step6-bullet` | `SKILL.md` Step 6 | The writer runs the scanner (Phase 1) and fixes P0s; the Phase 2 LLM review runs once, by the V6 reviewer; the writer does not invoke `e2e-reviewer` through the `Skill` tool; inline Phase 2 only when no separate actor exists (findings still reported, V6 unchanged); manual P0 pass only when the reviewer files are absent |
| 4 | `item4-tier8`, `item4-text-only`, `item4-suppression`, `item4-table`, `item4-mapping-rule`, `item4-template` | `code-rules.md`, `best-practices.md`, `scenario-design.md`, `conventions-template.md` | Text-bearing elements without a role, label or test id are located by `getByText` or a labeled ancestor; `#id`/`.class` are last resort and need `// JUSTIFIED:` unless `testIdAttribute` or a documented convention says otherwise; mirrored in the suppression list, the locators table, the Locator Mapping Table rules and the conventions template |
| 5 | `item5-v2`, `item5-v3`, `item5-v4`, `item5-step7` | `verification-rules.md` §§ V2, V3, V4; `SKILL.md` Step 7 | A probe that was not run is `CANNOT_VERIFY` with reason `not attempted: <why>` (V2/V3 non-blocking, stated in Step 7); V4 gets a concrete failed-write procedure (`page.route()` fulfill 500 in a temporary copy under the approved `<spec>` slot, red at the unchanged primary or declared gate, two evidence lines; request proof alone is `CANNOT_VERIFY` and blocks) |
| 6 | `item6-heading-remove`, `item6-heading-insert`, `item6-skillmd-typo`, `item6-selfref-frame`, `item6-dup-recap`, `item6-empty-guard-heading`, `item6-guard-heading-insert`, `item6-selfref-rationale`, `item6-selfref-guard-summary`, `item6-guard-pointer` | `verification-rules.md`, `exploration-preflight.md`, `SKILL.md` Step 3 | The empty `## Structured result contract` heading moves above the JSON block; the empty `## Guard for Playwright CLI` heading moves above the guard recipe; four self-references in `exploration-preflight.md` become in-file pointers; the "this SKILL.md" slip and the duplicated launcher paragraph are reduced to a recap; the pinned pointer sentence "read `exploration-preflight.md` § Guard for Playwright CLI and follow it exactly" moves to `SKILL.md` Step 3 where it belongs |

Unchanged on purpose: `name`, `version` (stays `2.0.0`: the fixes are folded into the unpushed 2.0.0 release), the completion templates, the completion status matrix rows and count, the V-rule canonical clauses that `check-verification-parity.sh` compares with the reviewer, every pinned phrase in `test-generator-contracts.py` other than the one self-reference pin, the scripts under `scripts/`, and `evals/`.

## Hypothesis and metric per item

Metrics named `compliance.*` are the deterministic stream-json indicators the v2 runner records (`compliance_from_events` in `scripts/evals/run-generator-skill-effect-v2.py`); v3 adds two (see `../../DESIGN.md`).

| Item | Hypothesis (v1 evidence) | Metric that tests it |
|---|---|---|
| 1 | Models classified the skill's own scripts as unapproved target-controlled commands and skipped exploration (29/30) and the scanner (5 self-reports say "not an approved command"). Clarifying ownership raises both rates without widening what project code may run. | `compliance.exploration_commands > 0` rate, `compliance.scanner_runs > 0` rate, full-fixed vs full |
| 2 | 14/30 calls never created a reviewer and 9/30 created one but demoted its verdict (relayed, reduced, "separation unprovable"); the skill never said how. Naming the host mechanism and the verdict line turns V6 into a reachable gate. | `compliance.agent_spawns > 0` rate; v3 "V6 verbatim verdict rate" (regex on the summary); self-reported `complete` rate |
| 3 | Step 6 (writer Phase 1–2) and V6 (reviewer Phase 1–2) ran the same review twice; the writer-side Phase 2 cost tokens and counted for nothing. | cost and wall-time multiple vs `full`; `compliance.read_reviewer_skill` rate (should fall in the writer); scanner P0 unchanged |
| 4 | All 7 skill-arm refactor failures used `#id`/`.class` on elements without a role or label; the selector priority had no rule for them. | refactor survival score, full-fixed vs full and vs no-skill (preregistered secondary) |
| 5 | V4 failed-write injection was skipped in every writing task (16 self-reports name it; the matrix blocks without it), V2/V3 were cited as blockers although non-blocking, and one call believed probes required editing the app. | v3 "legitimate Complete rate"; self-report `complete` vs compliance cross-check; primary metric unchanged or better |
| 6 | Structural defects cost reading time and mislead section pointers; no behavior claim. | none (Tier 0); guarded by the pending contract assertions only |

## RED/GREEN per pinned phrase

Computed against `HEAD` text and the fixed copy; the pending contract patch asserts each of these.

| Item | File | Pinned phrase | Expected | Current (HEAD) | Fixed copy |
|---|---|---|---|---|---|
| 1 | `SKILL.md` | `Exactly three scripts are skill-owned` | present | RED | GREEN |
| 1 | `SKILL.md` | `They are skill-owned only when their real paths lie outside the target repository` | present | RED | GREEN |
| 1 | `SKILL.md` | `No other script is skill-owned` | present | RED | GREEN |
| 1 | `SKILL.md` | `The three skill-owned scripts (the preflight launcher, the frame writer, and \`scan.sh\` under its pinned Step 6 invocation) are not rows in this table` | present | RED | GREEN |
| 1 | `SKILL.md` Step 6 | `E2E_SMELL_ALLOW_PROJECT_ESLINT=0 E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 E2E_SMELL_DISABLE_AST_GREP=1` and `/usr/bin/env -u E2E_SMELL_RG_BIN ...` | present | RED | GREEN |
| 1 | `SKILL.md` Step 6 | `one path per invocation`, `an environment variable alone is never approval` | present | RED | GREEN |
| 1 | `exploration-preflight.md` | `they need no Step 4 row` | present | RED | GREEN |
| 2 | `verification-rules.md` | `**Obtaining the reviewer.**` | present | RED | GREEN |
| 2 | `verification-rules.md` | `` `V6 VERDICT: <PASS|FAIL> P0=<n> P1=<n> P2=<n> reviewer=<id>` `` | present | RED | GREEN |
| 3 | `SKILL.md` | `The Phase 2 LLM review runs once, by the V6 reviewer in Step 7` | present | RED | GREEN |
| 3 | `SKILL.md` | `run its full Phase 1–2 procedure inline` | absent | RED | GREEN |
| 4 | `code-rules.md` | `**Text-bearing elements without a role, label, or test id.**` | present | RED | GREEN |
| 4 | `code-rules.md` | `CSS class — **POM files only**` | absent | RED | GREEN |
| 4 | `best-practices.md` | `\| Text-only elements \|` | present | RED | GREEN |
| 4 | `scenario-design.md` | `` `#id` and `.class` selectors require the same `// JUSTIFIED:` line `` | present | RED | GREEN |
| 4 | `conventions-template.md` | `` Raw CSS `#id`/`.class`: `// JUSTIFIED:` only `` | present | RED | GREEN |
| 5 | `verification-rules.md` | `not attempted: <why>` | present | RED | GREEN |
| 5 | `verification-rules.md` | `**Failed-write procedure.**` | present | RED | GREEN |
| 5 | `SKILL.md` | `` never block `Complete`, while applicable V4, V5, and V6 must be `PASS` `` | present | RED | GREEN |
| 6 | `exploration-preflight.md` | `## Guard for Playwright CLI` directly above `**Guard for Playwright CLI.** Its \`route\` command` | present | RED | GREEN |
| 6 | `exploration-preflight.md` | `` `exploration-preflight.md` § `` (self-reference) | absent | RED | GREEN |
| 6 | `exploration-preflight.md` | `this SKILL.md` | absent | RED | GREEN |
| 6 | `verification-rules.md` | `## Structured result contract` directly above `Record the result in this shape` | present | RED | GREEN |
| 6 | `exploration-preflight.md` | `(rationale: § Why Playwright CLI is the default)` | present | RED | GREEN |

## What this arm does not do

- It does not remove any layer (exploration, approval tables, tracer, V1–V6, Step 5b). That is the `lean` arm's question, answered by v2.
- It does not change the Step 4 approval semantics for any project-controlled command; item 1 only names the skill's own scripts as outside that table. See `../../security-note-item1.md`.
- It does not make V6 passable without a separate actor; a host with no subagent facility still returns `CANNOT_VERIFY` (eval 10 still holds).
- It adds no new verdict vocabulary: `not attempted: <why>` is a `CANNOT_VERIFY` reason, so the parity markers and the SP5 verdict vocabulary are unchanged.
