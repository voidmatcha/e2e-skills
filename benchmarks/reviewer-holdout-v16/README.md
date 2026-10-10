# Reviewer holdout v16

Reviewer holdout v16 asks one question: do the three reviewer contract fixes of commit `9e73a6c` help on a corpus they were not derived from? The fixes are the #20 row of `semantic-review.md` aligned to the `pattern-reference.md` evidence rule, a #23 primary line in `pattern-reference.md`, and P1 severity for a #2 partial verification. They were derived from [v10](../reviewer-holdout-v10/README.md) outcomes, so v16 reuses the frozen [v9](../reviewer-holdout-v9/README.md) corpus unchanged, by path and digest (30 cases: 16 Playwright, 14 Cypress). It runs on the single Codex host `gpt-6-sol` and compares two pinned revisions of the skill, not skill against no skill.

Status: **run at `972a119` on Codex `gpt-6-sol`; `NOT_SUPPORTED`, so no claim that the fixes help**. One diagnostic call (one case, one repetition, full arm, after revision) was made before freezing to confirm that `codex exec --output-schema` works with `gpt-6-sol`; it scored, and it is not part of any result.

## Result

The four reports and `revision-comparison.json` are in `reports/`. All 600 scheduled calls scored on the first attempt, with no infrastructure error.

| Arm | Before stable F1 | After stable F1 | After minus before (paired 95% interval) | Stable guard-hit rate |
|---|---|---|---|---|
| full | 0.892 | 0.881 | −0.011 (−0.076 to +0.049) | 0.031 → 0.031 |
| catalog-only | 0.914 | 0.881 | −0.033 (−0.100 to +0.028) | 0.031 → 0.031 |

The full-arm point estimate and lower bound are below 0, so the decision is `NOT_SUPPORTED`; the guard-hit condition held. The one stable change shared by both arms is in `v9-cy-01`: a partly verified title labelled `#1` P1 at line 12 became `#2` P1 at line 13 once the `#2` partial-verification severity sentence was added. In the full arm the after revision also found the labelled `#20` finding in `v9-pw-13`, which offset that lost true positive, so stable true positives stayed at 37 and false positives rose from 6 to 7. In catalog-only, false positives rose from 4 to 7.

**Follow-up.** Commit `25cf449` removed the `#2` partial-verification sentence. The `#20` and `#23` changes stay; v16 showed no harm from them, but they have not been measured on their own.

## Design

| | Before | After |
|---|---|---|
| Source commit | `769f1f61c5d280ff54d1f86610fe86ab84d2dbeb` | `9e73a6c252a135bc94568e9efd30d691a25f0086` |
| `skills/e2e-reviewer` git tree | `14b4563d03cfbb5e9310e6e14cdfdb4f73c795d1` | `899017afbb79a1d7e4e28f81927dccae3e76f493` |
| Skill SHA-256 (runner `skill_sha256`) | `c3b545315f185c1631b213b73f2466a24bad4beaa1d00bc24e4f6c675cb764d9` | `72a2582f043fd7dedbe0bbbc3e62b695d512248be34e0791ac890a20627cbdda` |

- **Before** is the skill at `769f1f6`, byte-identical to the skill at `c21d4f0` (the next/1.20.0 base).
- **After** is the skill at `9e73a6c`, which also carries `92f5bdf`. `92f5bdf` moves the scanner command lines from `SKILL.md` into `references/scanner-workflow.md`. Both files are in the full-arm prompt, so the full-arm prompt bytes differ by that move as well as by the three fixes. A tool-less holdout call cannot run the scanner, but the move is part of the before/after difference and cannot be separated from it.
- **Arms.** Full and catalog-only, once per revision. The catalog-only prompt embeds only `pattern-reference.md`, so it differs between revisions only by the #2 severity paragraph and the #23 primary line; the #20 fix is not in it. No no-skill arm is run: its prompt embeds no skill file and is byte-identical under both revisions.
- **Revision pinning.** The protocol's `revision_comparison.revisions` block pins each revision's commit, git tree, and skill digest. The runner refuses to start a v16 run unless the evaluated skill directory's digest is one of the two pinned digests, and each report records that digest. `--skill-dir` may point anywhere, but its path must be spelled without symlinks. The analysis binds each report to the revision its digest names and recomputes the report's prompt digest from that revision's files.
- **Everything else.** v11's infrastructure-retry policy byte for byte, v13's usage capture (Codex `--json` events), and v15's enforced output schema, which Codex receives through `--output-schema <file>` in the runner-private home. The schema's `pattern_id` enum covers every v9 label and accepted alternative, and both revisions' output legends equal it. v12's per-report thresholds, seed `20260801`, strict-majority stability rule, numbered sources, scoring contract, and five repetitions are unchanged. Codex floor: `codex-cli 0.155.1`, `minimum` version policy.

## Decision rule

Fixed before any counted call, in `revision_comparison.decision`:

- **Primary metric:** stable F1 per arm, from the comparator's per-case stable rows.
- **Uncertainty:** a paired stratified case bootstrap (finding cases and clean cases resampled separately, 10,000 iterations, seed `20260801`, nearest-rank 95% interval) of after minus before, with the same case sample applied to both revisions.
- **SUPPORTED** when, in the full arm, the after-minus-before stable F1 point estimate is at least 0, its bootstrap 95% lower bound is at least 0, and the after revision's stable guard-hit rate is not higher than the before revision's.
- **NOT_SUPPORTED** when all four reports are valid and complete and any of those conditions fails.
- **INCONCLUSIVE** when any report is missing, invalid, not execution complete, or has an unscored run, when the four reports do not share one runner identity, executable, reasoning effort, and clean Git revision, or when they break the execution order below or the 12-hour limit from first start to last completion.
- **Catalog-only** after-minus-before deltas and intervals are reported descriptively and do not enter the decision.

A zero lower bound is a non-inferiority reading: SUPPORTED says the fixes did not lower full-arm stable F1 or raise guard hits on this corpus. Only a positive lower bound shows an improvement.

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v9.json
cases SHA-256: 723740ea9eb6defe4951f72f30927570d9f0e259885d1503d25b20ea6e4c3d14
corpus SHA-256: 5465a355d2126ecbda3e24822ed4e7ced43676df283a77bbf01ca377591debaf
protocol: scripts/evals/reviewer-validation-protocol-v16.json
protocol SHA-256: afbb99cff4c8d91124e3c90cd436bdcecf2ec167e913d9fffe56e37561e23915
analysis: scripts/evals/compare-reviewer-revisions.py
```

The runner and comparator allow reuse of the v9 corpus for v16 only, at v9's frozen digests. The v2–v15 protocols are unchanged. `compare-reviewer-holdouts.py` refuses v16 and points to the revision analysis.

## Exact run commands

Run the four cells sequentially, in this order, from the repository root in an ordinary host shell, not inside a Codex sandbox. Start from a clean tree at the v16 commit so every cell records the same Git provenance. Set `CODEX_RUNNER` once to the explicit executable that reports `codex-cli 0.155.1` or later. Both skill revisions are extracted from Git, so later edits under `skills/` do not affect the run; keep `$OUT` on a path without symlinks.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v16"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v16 requires a clean tree" >&2; exit 1; }
rm -rf "$OUT/before-skill" "$OUT/after-skill"
mkdir -p "$OUT/before-skill" "$OUT/after-skill"
git archive 769f1f61c5d280ff54d1f86610fe86ab84d2dbeb skills/e2e-reviewer | tar -x -C "$OUT/before-skill"
git archive 9e73a6c252a135bc94568e9efd30d691a25f0086 skills/e2e-reviewer | tar -x -C "$OUT/after-skill"
BEFORE_SKILL="$OUT/before-skill/skills/e2e-reviewer"
AFTER_SKILL="$OUT/after-skill/skills/e2e-reviewer"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v9.json \
  --protocol scripts/evals/reviewer-validation-protocol-v16.json \
  --skill-dir "$BEFORE_SKILL" \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-before.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v9.json \
  --protocol scripts/evals/reviewer-validation-protocol-v16.json \
  --skill-dir "$AFTER_SKILL" \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-after.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v9.json \
  --protocol scripts/evals/reviewer-validation-protocol-v16.json \
  --skill-dir "$AFTER_SKILL" \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm catalog-only --repetitions 5 --allow-live --report-only \
  --output "$OUT/catalog-only-after.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v9.json \
  --protocol scripts/evals/reviewer-validation-protocol-v16.json \
  --skill-dir "$BEFORE_SKILL" \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm catalog-only --repetitions 5 --allow-live --report-only \
  --output "$OUT/catalog-only-before.json"

python3 scripts/evals/compare-reviewer-revisions.py \
  --cases scripts/evals/reviewer-holdout-v9.json \
  --protocol scripts/evals/reviewer-validation-protocol-v16.json \
  --before-skill-dir "$BEFORE_SKILL" --after-skill-dir "$AFTER_SKILL" \
  --before-full "$OUT/full-before.json" \
  --after-full "$OUT/full-after.json" \
  --before-catalog-only "$OUT/catalog-only-before.json" \
  --after-catalog-only "$OUT/catalog-only-after.json" \
  --output "$OUT/revision-comparison.json"

mkdir -p benchmarks/reviewer-holdout-v16/reports
cp "$OUT/full-before.json" "$OUT/full-after.json" \
  "$OUT/catalog-only-after.json" "$OUT/catalog-only-before.json" \
  "$OUT/revision-comparison.json" \
  benchmarks/reviewer-holdout-v16/reports/
```

The run is exactly **600 scheduled model calls**: 30 cases x 5 repetitions x 2 arms x 2 revisions. Retries can add at most one extra invocation per scheduled call, so the matrix makes 600 to 1,200 invocations. The v12 arms on this host took about 30 to 45 minutes each, so the matrix should take about 2 to 3 hours against the 12-hour limit. The analysis exits 0 for SUPPORTED, 1 for NOT_SUPPORTED, and 2 for INCONCLUSIVE.

## Claim limits

- **Same author.** The v9 corpus was built by the same author who wrote the fixes and the references under test.
- **Derivation.** The fixes were derived from v10 outcomes, not from v9. v9 already ran on Codex `gpt-5.6-sol` with public reports, and the skill was revised after those results, so both revisions may already fit this corpus; only the difference between them is tested.
- **Bundled change.** The after revision also carries `92f5bdf`'s scanner-command move, which changes the full-arm prompt; the full-arm difference is the fixes plus that move.
- **One host.** Codex `gpt-6-sol` only; no cross-provider claim.
- **Public corpus.** Public development evidence, not sealed or release-grade, and not population-level generalization. Bootstrap intervals describe case-resampling sensitivity on this fixed case set, not model-run stochasticity.
- **Verdicts.** SUPPORTED allows only the non-inferiority statement above. NOT_SUPPORTED allows no claim that the fixes help on a corpus they were not derived from. INCONCLUSIVE allows no before/after claim.
