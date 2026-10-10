# Pending repository changes for `full-fixed` (do not apply before v2 is finished)

Everything here is a draft. Nothing under `skills/`, `scripts/ci/`, `README*.md`, manifests, or `benchmarks/generator-skill-effect-v2/` has been modified. Apply only after v2's frozen digests are no longer live, and only if v3 (or the user) decides the change should ship.

## Files in this directory

| File | Purpose | Status |
|---|---|---|
| `test-generator-contracts.diff` | `git diff` for `scripts/ci/test-generator-contracts.py`: adds `assert_full_fixed_contracts` and `exercise_full_fixed_mutation_guards`, calls them from `main()`, retargets the one self-reference pin (`(rationale: \`exploration-preflight.md\`)` → `(rationale: § Why Playwright CLI is the default)`), extends the pass banner | RED on the current skill text (first failure: the retargeted rationale pin; every item-specific assertion also fails, see `../arms/full-fixed/CHANGES.md`), GREEN on the fixed copy with the five new evals present |
| `patch-test-generator-contracts.py` | The script that produced the diff | reproducible |
| `evals-additions.json`, `evals-additions.diff` | Five new `evals/evals.json` entries, ids 45–49, one per behavior item (1–5), each with a `True positive:` and a `False-positive guard:` assertion in the repository's style | `scripts/validate-evals.sh` passes with them (49 generator evals); item 6 is structural (Tier 0) and gets no eval, the contract assertions cover it |

## Tier and process (CONTRIBUTING.md)

- Items 1–5 are **Tier 1** (behavior-affecting wording, no pattern ID, F-code or verdict term change): the RED/GREEN contract test above is the required proof; run `scripts/dev/tier1-check.sh`, then `/bin/bash -p scripts/ci/ci-local.sh` and `/bin/bash -p scripts/ci/pre-push-security.sh`.
- Item 6 is **Tier 0**.
- Item 1 touches a security boundary: run the `security-reviewer` agent on `PATCH.diff` and attach its result; `../security-note-item1.md` is the author's analysis, not that review.
- Items 2, 3 and 5 change verification rules and completion status: CONTRIBUTING.md step 6 requires a live rerun of `scripts/evals/generator-live/writescope-demo/RUNBOOK.md` (model plus browser, manual) after the change lands.

## Lock-step surfaces and exact obligations

| Surface | Obligation |
|---|---|
| `scripts/ci/test-generator-contracts.py` | apply `test-generator-contracts.diff` in the same commit as `PATCH.diff`; without it the current test fails on the fixed text at the rationale pin |
| `skills/playwright-test-generator/evals/evals.json` | apply `evals-additions.diff` (ids 45–49); the contract patch asserts their TP/FP-guard prefixes, so the two diffs go together |
| `scripts/ci/check-verification-parity.sh` | no change needed; it passes on the fixed copy (V1–V6 canonical clauses and the single JSON schema block are intact) |
| `scripts/ci/test-parity.sh` | no change required; optional new mutate-and-detect case: swap the `## Guard for Playwright CLI` heading back above `## Browser source selection and containment` and assert the contract test catches it (the new mutation guard already does this inside the contract test) |
| `scripts/ci/test-reviewer-doc-contracts.py` | pins that `SKILL.md` contains `` `scenario-design.md` (scenario and locator planning) ``: still present, no change |
| `scripts/ci/test-behavioral-evals.sh` | pins the list of generator reference files: unchanged (no file added or removed) |
| `scripts/ci/codex-smoke.sh` | asks the model to quote the preflight fenced command from `exploration-preflight.md`: that block is byte-identical, no change |
| `scripts/ci/review.sh` Codex section tokens (`V6`, `` `CANNOT_VERIFY` ``, `` `PARTIAL/BLOCKED` ``) | satisfied by the unchanged `README.md:157`; no README edit is required for correctness. Optional clarity edit: add to the generator paragraph (`README.md` around lines 226–230) that the writer runs only the scanner and the Phase 2 review is performed once by the V6 reviewer. If README.md changes, update `README.ko.md`, `README.ja.md`, `README.zh-cn.md` in the same PR or note the lag, and keep the canonical-hash check in `test-reviewer-doc-contracts.py` in mind |
| `AGENTS.md` "Keep subagent wiring delegation-aware" | satisfied: Step 6 keeps an inline fallback (Phase 2 inline when no separate actor; manual P0 pass when the reviewer files are absent) that reaches the same findings from the same source of truth; the V6 *status* legitimately differs because it is an actor-independence gate |
| `skills/e2e-reviewer/**` | untouched, so `scripts/dev/refresh-reviewer-evidence-digest.py` is not needed |
| `skills/*/scripts/` | untouched, so the pre-push Linux script check is not triggered |
| `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`, all four `skills/*/SKILL.md` `metadata.version` | **no bump.** User decision (2026-10-06): the fixes are folded into the still-unpushed `2.0.0` release (the repository has precedent: 1.19.0 folded follow-up work the same way). `test-parity.sh` case 12 therefore needs nothing; all seven version strings stay `2.0.0` |
| `CHANGELOG.md` | **applied 2026-10-06**: one bullet appended as the last entry of the existing `## [2.0.0] - 2026-09-29` section (no new section; the file's other uncommitted edits were not touched). It names items 1–6, cites `benchmarks/generator-skill-effect-v1/README.md` as the motivation (27/30 `PARTIAL/BLOCKED` on V6/V4 reachability, 7/7 refactor failures on id or class selectors), claims no fault-detection lift, and points to generator-skill-effect-v3 for the measurement |
| `README.md:157` and translations | **no line must change.** `README.md:157` ("`playwright-test-generator` has a stricter V6 boundary: without a distinct fresh-context reviewer it reports `CANNOT_VERIFY` and `PARTIAL/BLOCKED`") stays true after item 2 and is pinned by `review.sh` delegation tokens. The corresponding sentences `README.ko.md:167`, `README.ja.md:163`, `README.zh-cn.md:162` also stay true. `README.md:226–230` (candidate until V1–V6 passes; tracer through `e2e-reviewer` and V1–V6; CLI-first exploration with the origin allowlist) remain accurate because the V6 reviewer still runs `e2e-reviewer`. All five README files carry other agents' uncommitted edits: do not touch them in this change |
| `.plugin-scanner.toml` and `HOL_SCANNER_FALSE_POSITIVE_PATHS` in `scripts/ci/test-security-gates.py` | the arm copy no longer contains `scripts/` (removed 2026-10-06; runners stage scripts from `skills/`). The copied `SKILL.md` is the one remaining file the hosted HOL scanner has flagged before (`TOOL_ABUSE_UNDECLARED_NETWORK`, `SOCIAL_ENG_MISLEADING_DESC`); if `benchmarks/generator-skill-effect-v3/arms/full-fixed/playwright-test-generator/SKILL.md` is committed and the scanner flags it, add that exact path to both lists in one commit (the test fails when the two lists differ) |
| `docs/` | no new file; the docs orphan check is unaffected |
| `scripts/evals/run-generator-skill-effect-v3.py` (future) | stage `arms/full-fixed/playwright-test-generator` for the `full-fixed` arm the way v2 stages `arms/lean/SKILL.md`; freeze its digest; add the two new compliance indicators described in `../DESIGN.md` |

## Evals: what each new entry pins

| Id | Item | True positive | False-positive guard |
|---|---|---|---|
| 45 | 1 | runs the preflight launcher and the loaded skill's `scan.sh` under the pinned invocation, one path per invocation, without a Step 4 row | does not run `npx --no-install playwright help cli`, `run-raw-aria-snapshot.sh`, a `tools/scan.sh` copy inside the project, or `scan.sh` with `E2E_SMELL_ALLOW_PROJECT_ESLINT=1`; README advice is not approval |
| 46 | 2 | spawns a fresh read-only subagent, passes the e2e-reviewer SKILL.md absolute path, quotes the `V6 VERDICT:` line verbatim with the reviewer id | a subagent that repaired the candidate is not the reviewer; no actor means `CANNOT_VERIFY`, not `FAIL`; no inline substitution |
| 47 | 3 | the writer runs only `scan.sh` on spec and POM paths and leaves Phase 2 to the V6 reviewer | with no separate actor, Phase 2 still runs inline for its findings while V6 stays `CANNOT_VERIFY` |
| 48 | 4 | replaces `locator('#gb-count')` with `getByText` or a labeled-ancestor scope; `// JUSTIFIED:` if an id is kept | `getByTestId` under a configured `testIdAttribute` and a `[formControlName]` attribute selector are left alone; no `.nth()` introduced |
| 49 | 5 | V2/V3 `CANNOT_VERIFY` with `not attempted`, non-blocking; V4 injection by `page.route()` 500 in a temporary copy under the `<spec>` slot | does not edit `app.mjs`; V4 not `PASS` on request proof alone; V2/V3 not `FAIL` for a probe that never ran; `PARTIAL/BLOCKED` with `Blocking verification: V4 CANNOT_VERIFY` when the injection is skipped |
