# Reviewer holdout v7 — complete, failed

Reviewer holdout v7 is a Codex-only rerun protocol for the unchanged v5 public-development corpus. It was designed after the v5/v6 Claude Fable plan-mode failures showed that the runner's injected instruction could break the strict single-JSON output contract. V7 changes execution tooling and host scope, not cases, labels, scoring, stability, schedule seed, repetitions, or thresholds.

Status: **FAIL**. The full arm missed the preregistered P0 stable-label recall threshold, and the full-vs.-catalog-only contrast missed three lift thresholds. `skill_lift_claim_eligible` is `false`; no skill-lift claim is allowed.

## Why this model and runner floor

The sole host remains `codex / gpt-5.6-sol`, the same Codex cell used by v5. That keeps the model identifier stable while removing the failed Claude execution path. The protocol was cut against installed `codex-cli 0.154.0`, which supports that model, and declares it as a `minimum` version floor. Every report still records the actual CLI identity, and the comparator requires one identical resolved Codex executable, identity, and reasoning-effort setting across all three arms.

## Differences from v5

- Protocol ID changes from v5 to v7 because frozen protocols are never rewritten.
- The host matrix narrows from Codex plus Claude Opus and Fable to Codex `gpt-5.6-sol` only. This removes the known Claude plan-mode failure path and means v7 supports no cross-provider claim.
- The execution identity changes from exact Codex `0.146.0` and Claude `2.1.220` pins to a Codex-only `0.154.0` minimum floor. This follows the post-v5/v6 rule that new protocols must survive ordinary CLI rotation while recording the actual version.
- The required matrix shrinks from three prompt profiles by three hosts (nine reports, 540 calls) to the same three prompt profiles by one host (three reports, 180 calls). The Codex arm order remains `full`, `catalog-only`, `no-skill`, run sequentially.
- Provider-family aggregation becomes a direct single-host aggregation. Singleton agreement values are neutral (`recall gap = 0`, `Jaccard = 1`); the full-arm absolute PASS gate, both control lift gates, paired bootstrap intervals, and every v5 scoring threshold remain load-bearing.
- The schedule disclosure records that v7 was designed after observing the v5/v6 Fable failures. The cases file and case digest are byte-identical to v5.
- Runner tooling now accepts exactly one recognized version line after leading diagnostics, and Claude permission mode is protocol-declarable for future protocols. Existing protocols still emit `--permission-mode plan` byte-for-byte; v7 invokes no Claude cell.

Everything else is unchanged from v5: the 20 cases, 24 findings, 24 guards, schedule algorithm and seed, three repetitions, strict-majority stability rule, Wilson intervals, per-report thresholds, paired-stratified bootstrap, lift thresholds, 12-hour matrix window, failure semantics, and public-development claim limits.

## Results

Attempt 4 is the counted run. It executed all three arms sequentially from an ordinary host shell against Git revision `110f2ea6a6e4876f601fa3b2cb6bd2ead40e48ab` (`v1.19.0`). Every arm recorded `git_dirty: false`, 60/60 scoreable calls, and zero infrastructure errors. The 180 calls ran from 2026-09-20 03:38:34 to 04:16:43 KST with `codex / gpt-5.6-sol` and `codex-cli 0.154.0`. The comparator returned `FAIL` and `skill_lift_claim_eligible: false`.

The protocol's primary unit is unique majority-stable labels and predictions. Repeated precision is the repeated-run safeguard; P0 recall and clean specificity are also preregistered absolute metrics.

| Arm | Status | Stable precision | Stable recall | Stable F1 | Repeated precision | P0 stable-label recall | Clean-case specificity |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| full | FAIL | 0.956522 | 0.916667 | 0.936170 | 0.902778 | 0.875000 | 1.000000 |
| catalog-only | FAIL | 0.884615 | 0.958333 | 0.920000 | 0.839506 | 0.875000 | 0.750000 |
| no-skill | FAIL | 0.350000 | 0.583333 | 0.437500 | 0.338710 | 0.375000 | 0.250000 |

The full arm passed every absolute threshold except `p0_stable_label_recall_min`: 7 of 8 P0 labels were stable, for `0.875000` against the required `>= 0.900000`. A control arm's `FAIL` is not by itself a defect; the protocol applies the same absolute thresholds to all arms. The lift decision is separate:

| Lift check | Required | Full minus catalog-only | Pass | Full minus no-skill | Pass |
| --- | ---: | ---: | :---: | ---: | :---: |
| Stable F1 delta | >= 0.050000 | 0.016170 | no | 0.498670 | yes |
| Stable F1 delta, paired-bootstrap 95% CI lower bound | >= 0.010000 | -0.068687 | no | 0.334149 | yes |
| Stable precision delta | >= -0.020000 | 0.071906 | yes | 0.606522 | yes |
| Stable recall delta | >= -0.020000 | -0.041667 | no | 0.333333 | yes |
| Clean-case specificity delta | >= 0.000000 | 0.250000 | yes | 0.750000 | yes |
| Repeated precision delta | >= 0.000000 | 0.063272 | yes | 0.564068 | yes |

All six lift checks passed against `no-skill`. Against `catalog-only`, stable F1 delta, its paired-bootstrap 95% CI lower bound, and stable recall delta failed. Because the full arm also failed an absolute threshold, the comparator does not permit a skill-lift claim.

### Systematic `pw-a06` miss

The unstable P0 label was `pw-a06` / `V5-014`, pattern `#3`: a `try`/`catch` wraps `await expect(...).toHaveCount(2)`, and the catch only logs. The counted full arm missed it in all three repetitions and returned `{"findings":[]}` each time. The counted catalog-only arm did the same. The no-skill arm named pattern `#3` on unrelated lines in all three repetitions, so none matched `V5-014`; it also scored 0/3. Attempt 3's full arm independently returned `{"findings":[]}` in all three repetitions. This is a repeated miss on this fixed case, not an estimate of the pattern's prevalence or population-level recall.

### Attempts and counting rule

- **Attempt 1:** ran only the full arm from inside a Codex workspace-write sandbox. Nested Codex calls hung: 35 of 60 timed out, leaving 25 scoreable calls. The arm was `INCONCLUSIVE`, and the run stopped. `attempts/1/RUN-REPORT.md` records the details.
- **Attempt 2:** again ran the full arm inside the sandbox. Nine of the first 11 calls timed out; the run was stopped early with only two scoreable calls.
- **Attempt 3:** ran all three arms from the host with zero infrastructure errors, but wrote reports inside the checkout. Each arm therefore recorded a different `git_dirty_sha256`; the comparator returned `INCONCLUSIVE` with `arm_provenance_mismatch`.
- **Attempt 4:** ran all three arms from the host, wrote reports outside the checkout, and completed with matching clean-tree provenance and zero infrastructure errors. This is the only counted result.

Attempts 1–3 are disclosed as execution history and are not combined with attempt 4. No metric, prediction, or arm was cherry-picked across attempts.

### Claim limits

This is a single-host, single-model run on an inspectable public development corpus. It is not sealed, release-grade, cross-provider, cryptographically attested, or evidence of population-level generalization. The result supports only the recorded `FAIL` decision and descriptive arm metrics for this frozen corpus and execution.

## Addendum: exploratory rerun after the SKILL.md trim and #3 fix (not counted)

An uncounted exploratory rerun used the same frozen v7 protocol and attempt 4 procedure at Git revision `cb9aca231fc413876d5169c1617978c8a9a3ced2` on `next/1.20.0`: the reviewer `SKILL.md` trim (`0021313`) plus the pattern `#3` swallowed-assertion wording fix (`cb9aca2`). All three arms ran sequentially from the host shell with a clean tree and reports outside the checkout; all 180 calls were scoreable with zero infrastructure errors, from 2026-09-20 05:48 to 06:25 KST. This rerun is a non-regression check, does not replace attempt 4, and is not included in the counted v7 verdict.

| Run | Arm | Status | Stable precision | Stable recall | Stable F1 | P0 recall | Clean specificity |
| --- | --- | :---: | ---: | ---: | ---: | ---: | ---: |
| Attempt 4 (counted) | full | FAIL | 0.956522 | 0.916667 | 0.936170 | 0.875000 | 1.000000 |
| Attempt 4 (counted) | catalog-only | FAIL | 0.884615 | 0.958333 | 0.920000 | 0.875000 | 0.750000 |
| Attempt 4 (counted) | no-skill | FAIL | 0.350000 | 0.583333 | 0.437500 | 0.375000 | 0.250000 |
| Exploratory rerun | full | PASS | 0.958333 | 0.958333 | 0.958333 | 1.000000 | 1.000000 |
| Exploratory rerun | catalog-only | FAIL | 0.888889 | 1.000000 | 0.941176 | 1.000000 | 0.750000 |
| Exploratory rerun | no-skill | FAIL | 0.351351 | 0.541667 | 0.426230 | 0.375000 | 0.125000 |

The exploratory comparator returned `FAIL` and `skill_lift_claim_eligible: false`. Full-versus-no-skill passed all six lift checks. Full-versus-catalog-only failed the same three checks as attempt 4: stable F1 delta (`0.017157 < 0.050000`), its paired-bootstrap 95% CI lower bound (`-0.041667 < 0.010000`), and stable recall delta (`-0.041667 < -0.020000`).

Relative to attempt 4's full arm, the rerun gained stable true positives `cy-a05` / `V5-024` / `#19` and `pw-a06` / `V5-014` / `#3`, and lost stable true positive `pw-a04` / `V5-008` / `#13`. It gained no stable false positives and lost none; the single stable false positive remained `cy-a06` / `#1` at `cypress/e2e/board.cy.ts:10`.

The `#3` wording fix was designed after observing the `pw-a06` miss in this same public corpus, so `pw-a06` is contaminated in this rerun and its recovery is not evidence of generalization.

The catalog-only profile also embeds the edited `SKILL.md` `#3` row, so its recovery of the same label is contaminated too. Excluding `pw-a06` would be the uncontaminated comparison, but the repository comparator has no case-exclusion mode; the per-case changes above are reported instead of introducing a new post-hoc scoring method.

Within this fixed tool-less public holdout, the trim did not regress the full arm; the failed lift-versus-catalog-only outcome is unchanged.

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v5.json
cases SHA-256: 50c828c5e267a683ced73a161a645af0b73f305f6391b6fe0e8ee150ec419849
corpus SHA-256: 745bc765fb6f424abe90d6d3fc9a3b85e921472a4cc1291054879af8002e965f
protocol: scripts/evals/reviewer-validation-protocol-v7.json
protocol SHA-256: e379edfc7ad04e4ff92134f3f5952bda7f146e0f80667726283a2a60de08daf2
```

## Full run

Run the three cells sequentially from the repository root in an ordinary host shell, not from inside a Codex sandbox. A nested `codex` call from a workspace-write sandbox hangs until timeout. Start from a clean tree so every arm records the same Git provenance. Set `CODEX_RUNNER` once to the explicit executable that reports `codex-cli 0.154.0` or later; do not use a changing command name between cells. Keep all generated reports outside the checkout until the comparison is complete, then copy the four JSON artifacts into the benchmark directory.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v7"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v7 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm full --repetitions 3 --allow-live --report-only \
  --output "$OUT/full-codex.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm catalog-only --repetitions 3 --allow-live --report-only \
  --output "$OUT/catalog-only-codex.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm no-skill --repetitions 3 --allow-live --report-only \
  --output "$OUT/no-skill-codex.json"

python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --compare-arms \
  --output "$OUT/arm-comparison.json"

mkdir -p benchmarks/reviewer-holdout-v7/reports
cp "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  "$OUT/arm-comparison.json" \
  benchmarks/reviewer-holdout-v7/reports/
```

The full run is exactly **180 model calls**: 20 cases x 3 repetitions x 3 prompt arms. The completed v5 Codex full arm took about 12 minutes 41 seconds for 60 calls on 2026-09-19, so three sequential Codex arms are expected to take roughly 38–45 minutes under similar service conditions. The frozen hard limit remains 12 hours because provider latency can vary.

This remains public-development evidence. It is not sealed, release-grade, cryptographically attested, cross-provider, or evidence of population-level generalization.
