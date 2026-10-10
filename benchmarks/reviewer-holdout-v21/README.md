# Reviewer holdout v21: decisive #2 severity replication

Status: **run on Codex `gpt-6-sol`; `NOT_SUPPORTED`**. This public development holdout repeats v20's full-arm before/after comparison on a larger, newly authored corpus with explicit guards against moving #1 title findings to #2. The BEFORE skill is the pre-release 2.0.0 candidate commit `976c3fae4400a2683bab2c2a015af0bd842e4dd5` (the shipped 2.0.0 reviewer was changed afterwards and is not measured here) (tree `40cbbfeab3f46a96533b1dae3760a8ae96cf0aea`, runner digest `aa88145dda8b95fcd7c59cbf64de28ae4beeafe3451b739a46ae202b3cb0d57f`). The AFTER skill is isolated #2 partial-P1 wording commit `23267980c7afb74acf128eefee55ee326b5f428a` (tree `072e4dbbe75fbdb005bfccbf2d852d36615e31f8`, digest `818794b3f2e20eec20a716950d25a1273609523b750d1227687fbb01feb15d83`).

## Corpus and labeling

The 48 synthetic cases comprise 24 Playwright and 24 Cypress suites. Codex `gpt-6-sol` authored them and their labels without access to v16/v20 corpora or results, following [BRIEF.txt](labeling/BRIEF.txt), which fixed the ground-truth rules before labeling. Blind `gpt-6-astra` and `gpt-6-luna` labels each matched all 48/48 author findings and added no findings; their byte-for-byte outputs are in [labeling/](labeling/). The 12 partial-verification title cases (`v21-pw-10`–`15`, `v21-cy-10`–`15`) are ownership traps: #1 must remain at the title, not move to #2 at an action. This is AI-authored public development evidence, not a human-adjudicated or sealed release sample. The imported corpus's `source_line` strings were stripped of indentation to satisfy the runner's canonical line format; the source files and blind-label outputs were copied unchanged.

- Cases: `scripts/evals/reviewer-holdout-v21.json`, SHA-256 `1e3e5e2ac948056812ea7966d81f2df2b646cd6d486e758b72b49f8d78ced09e`; source-inclusive corpus digest `e792f200fdf1ba5b5bedd956fb5f3b27bec15fba519c3f59ec2204ef9edb2113`.
- Protocol: `scripts/evals/reviewer-validation-protocol-v21.json`, SHA-256 `050867ce7eaa44d70f9070d59860ffdb0aad75b92531dce1d8cf702d2106154b`.
- BEFORE: release 2.0.0 skill commit `976c3fae4400a2683bab2c2a015af0bd842e4dd5`; AFTER: isolated #2 partial-P1 wording commit `23267980c7afb74acf128eefee55ee326b5f428a`. These are the same pinned skill revisions as v20.
- Codex `gpt-6-sol`, `codex-cli 0.155.1` minimum; full arm only, BEFORE then AFTER, five repetitions each: **480 scheduled calls**. The v20 output schema, usage capture, and one fresh retry for timeout, malformed JSON, usage-limit exit, authentication error, or unexpected Codex stream item apply unchanged.

## Result

The byte-for-byte reports and revision comparison are in [reports/](reports/). All 480 scheduled calls scored with 0 retries. Full-arm stable F1 fell from 1.000 BEFORE to 0.980 AFTER: -0.020, with a paired 95% case-bootstrap interval of [-0.043, 0.000]. Stable guard-hit rate rose from 0.000 to 0.019. #2 severity accuracy was 24/24 in both revisions, #1→#2 and #2→#1 misclassifications were 0 in both, and all 12 title-ownership traps were correct in both. AFTER therefore misses the F1 point-estimate and interval gates and the no-guard-regression gate; the result is `NOT_SUPPORTED`.

The decision is to keep the 2.0.0 wording with no clarification. The frozen protocol carried the v20 doc-only clarification only as a post-run proposal, not as evaluated skill text or an automatic consequence independent of the evidence. V21 shows that the existing 2.0.0 wording already grades partially verified #2 instances as P1 in agreement with `references/reporting.md`: BEFORE achieved 24/24 #2 severity accuracy. Adding “#2 keeps its catalog severity” would instead steer grading away from that observed behavior. V20's lower BEFORE result, 10/13 (77%), is therefore best treated as a likely corpus-construction effect in that smaller corpus rather than evidence that the existing wording needs the proposed clarification.

## Frozen decision

Adopt AFTER wording as release 2.0.1 only if all four gates pass on the complete, valid matrix:

1. AFTER minus BEFORE full-arm stable F1 is at least +0.05.
2. Its paired stratified case-bootstrap 95% lower bound is strictly greater than 0.
3. Stable guard-hit rate does not rise.
4. #1→#2 strict-majority misclassifications on the 12 trap cases do not rise.

Otherwise keep the 2.0.0 wording and add the v20 doc-only clarification: “#2 keeps its catalog severity; reporting.md's boundary governs only where a pattern states an instance rule.” An incomplete or invalid matrix is `INCONCLUSIVE` and authorizes neither wording decision. Report #2 severity accuracy, #1↔#2 misclassifications, and trap-case accuracy descriptively. The paired interval measures resampling sensitivity of this fixed case set, not model-run randomness or a population effect. The completed result keeps the wording and rejects that proposed clarification for the evidence-based reason above; this records the proposal's disposition without rewriting the frozen rule.

## Exact run commands

Run sequentially from a clean checkout containing this preregistration, with an explicit Codex executable. Use an output path without symlinks. The run does not publish reports or mutate the checkout.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v21"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v21 requires a clean tree" >&2; exit 1; }
test ! -e "$OUT/before-skill" && test ! -e "$OUT/after-skill" || { echo "v21 skill extraction directories already exist" >&2; exit 1; }
mkdir -p "$OUT/before-skill" "$OUT/after-skill"
git archive 976c3fae4400a2683bab2c2a015af0bd842e4dd5 skills/e2e-reviewer | tar -x -C "$OUT/before-skill"
git archive 23267980c7afb74acf128eefee55ee326b5f428a skills/e2e-reviewer | tar -x -C "$OUT/after-skill"
BEFORE_SKILL="$OUT/before-skill/skills/e2e-reviewer"
AFTER_SKILL="$OUT/after-skill/skills/e2e-reviewer"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v21.json \
  --protocol scripts/evals/reviewer-validation-protocol-v21.json \
  --skill-dir "$BEFORE_SKILL" \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-before.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v21.json \
  --protocol scripts/evals/reviewer-validation-protocol-v21.json \
  --skill-dir "$AFTER_SKILL" \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-after.json"

python3 scripts/evals/compare-reviewer-revisions.py \
  --cases scripts/evals/reviewer-holdout-v21.json \
  --protocol scripts/evals/reviewer-validation-protocol-v21.json \
  --before-skill-dir "$BEFORE_SKILL" --after-skill-dir "$AFTER_SKILL" \
  --before-full "$OUT/full-before.json" --after-full "$OUT/full-after.json" \
  --output "$OUT/revision-comparison.json"
```

The comparator exits 0 for `SUPPORTED`, 1 for `NOT_SUPPORTED`, and 2 for `INCONCLUSIVE`. Archive the three output files byte-for-byte if this run is reported; do not edit the frozen v21 corpus or protocol after the first measured call.
