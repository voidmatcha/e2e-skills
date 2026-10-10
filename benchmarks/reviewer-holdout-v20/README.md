# Reviewer holdout v20: #2 partial-verification severity

Status: **run on Codex `gpt-6-sol`; `NOT_SUPPORTED`**. This public development holdout asks whether adding the explicit #2 P1 instance rule improves reviewer accuracy over release 2.0.0. The only skill difference is the #2 severity paragraph in `references/pattern-reference.md`, its generated `references/patterns/2.md`, and the Quick Reference #2 clause in `SKILL.md`. The BEFORE skill is commit `976c3fae4400a2683bab2c2a015af0bd842e4dd5` (tree `40cbbfeab3f46a96533b1dae3760a8ae96cf0aea`, runner digest `aa88145dda8b95fcd7c59cbf64de28ae4beeafe3451b739a46ae202b3cb0d57f`). The AFTER skill is commit `23267980c7afb74acf128eefee55ee326b5f428a` (tree `072e4dbbe75fbdb005bfccbf2d852d36615e31f8`, digest `818794b3f2e20eec20a716950d25a1273609523b750d1227687fbb01feb15d83`).

The 24 synthetic cases contain 21 finding labels and 29 false-positive guards, including #2 P0 at partly verified actions and #1 P1 at titles. Codex `gpt-6-sol` authored the sources and initial labels. Blind labels from `gpt-6-astra` and `gpt-6-luna` each matched 19/21 author findings; their two disputes and resolution are in [labeling/adjudication.md](labeling/adjudication.md), alongside both blind label files. The severity ground truth was fixed before labeling from `references/reporting.md`: one real promised effect verified while another is unchecked is P1. These public AI-authored cases are development evidence, not a sealed release sample.

## Result

The byte-for-byte reports and revision comparison are in [reports/](reports/). All 240 scheduled calls scored with 0 retries. The full-arm stable F1 rose from 0.857 BEFORE to 1.000 AFTER: +0.143, paired 95% case-bootstrap interval [0.000, 0.286]. Stable guard-hit rate fell from 0.069 to 0.000; #2 severity accuracy rose from 10/13 to 13/13 and #2→#1 misclassifications fell from 3 to 0. The point estimate and guard condition pass, but the interval's lower bound is exactly 0 and the preregistered rule requires **strictly greater than 0**. The result is therefore `NOT_SUPPORTED`, and the 2.0.0 wording is kept for now.

The v20 corpus defines partial verification as P1 by construction, matching the AFTER wording. On the earlier v9 corpus, v16 found the same wording harmful: a labelled #1 P1 title finding moved to #2 P1. V20 cannot rule out that transfer on other cases. A larger v21 replication with explicit #1 ownership traps was preregistered next. The v20 fallback is the doc-only clarification, “#2 keeps its catalog severity; reporting.md's boundary governs only where a pattern states an instance rule”; its disposition follows v21.

## Frozen inputs and decision

- Cases: `scripts/evals/reviewer-holdout-v20.json`, SHA-256 `4c71dc456ec657e6de8affe999c3f6ca27bd246d52d08f084676d4df612bf1fb`; source-inclusive corpus digest `9a73b4b12fa860ace1ba7b2af825c1d3927f135296eca14b3da95a523bcd306b`.
- Protocol: `scripts/evals/reviewer-validation-protocol-v20.json`, SHA-256 `d61537729e94d115e1aeaacaf278ba396eeceb9f13840ba1e59b01497122f036`.
- Host: Codex `gpt-6-sol`, CLI floor `codex-cli 0.155.1`; full arm only, before then after, five repetitions each, 240 scheduled calls. Native output schema, usage capture, strict-majority stability, and one fresh retry for timeout, malformed JSON, usage-limit exit, authentication error, or unexpected Codex stream item.
- Adopt AFTER only if full-arm after-minus-before stable F1 is at least +0.05, its paired case-bootstrap 95% lower bound is strictly above zero, and stable guard-hit rate does not increase. A complete matrix that misses any gate retains 2.0.0 wording and calls for the doc-only clarification: “#2 keeps its catalog severity; reporting.md's boundary governs only where a pattern states an instance rule.” Incomplete or invalid reports are inconclusive. Report #2 severity accuracy and #1/#2 misclassifications descriptively.

## Exact run commands

Run sequentially from a clean checkout containing the v20 preregistration commit, in a host shell with an explicit Codex executable. Keep `OUT` on a path without symlinks. The commands do not change the checkout or publish reports.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v20"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v20 requires a clean tree" >&2; exit 1; }
test ! -e "$OUT/before-skill" && test ! -e "$OUT/after-skill" || { echo "v20 skill extraction directories already exist" >&2; exit 1; }
mkdir -p "$OUT/before-skill" "$OUT/after-skill"
git archive 976c3fae4400a2683bab2c2a015af0bd842e4dd5 skills/e2e-reviewer | tar -x -C "$OUT/before-skill"
git archive 23267980c7afb74acf128eefee55ee326b5f428a skills/e2e-reviewer | tar -x -C "$OUT/after-skill"
BEFORE_SKILL="$OUT/before-skill/skills/e2e-reviewer"
AFTER_SKILL="$OUT/after-skill/skills/e2e-reviewer"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v20.json \
  --protocol scripts/evals/reviewer-validation-protocol-v20.json \
  --skill-dir "$BEFORE_SKILL" \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-before.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v20.json \
  --protocol scripts/evals/reviewer-validation-protocol-v20.json \
  --skill-dir "$AFTER_SKILL" \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-after.json"

python3 scripts/evals/compare-reviewer-revisions.py \
  --cases scripts/evals/reviewer-holdout-v20.json \
  --protocol scripts/evals/reviewer-validation-protocol-v20.json \
  --before-skill-dir "$BEFORE_SKILL" --after-skill-dir "$AFTER_SKILL" \
  --before-full "$OUT/full-before.json" --after-full "$OUT/full-after.json" \
  --output "$OUT/revision-comparison.json"
```

The comparator returns 0 for `SUPPORTED`, 1 for `NOT_SUPPORTED`, and 2 for `INCONCLUSIVE`. The archived result and frozen preregistration remain separate: the protocol and corpus were not edited after the run.
