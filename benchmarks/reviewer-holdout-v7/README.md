# Reviewer holdout v7 — complete, failed

Reviewer holdout v7 is a Codex-only rerun protocol for the unchanged v5 public-development corpus. It was designed after the v5/v6 Claude Fable plan-mode failures showed that the runner's injected instruction could break the strict single-JSON output contract. V7 changes execution tooling and host scope, not cases, labels, scoring, stability, schedule seed, repetitions, or thresholds.

Status: **FAIL**. The full arm passed every preregistered absolute threshold, but the comparator failed the full-vs.-catalog-only `stable_f1_delta_ci95_lower_min` threshold. `skill_lift_claim_eligible` is `false`; no skill-lift claim is allowed.

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

Attempt 5 is the counted run. It executed all three arms sequentially from an ordinary host shell against release revision `2ba34237cb0b67e9918cd28c177774c8e5ed0fc9`, measuring the skills as shipped: the trimmed bodies, the pattern `#3` swallowed-assertion fix, the conditional-rethrow triage rule, and the lexer fix were all present. Every arm recorded `git_dirty: false`, 60/60 scoreable calls, and zero infrastructure errors. The 180 calls ran from 2026-09-20 16:56:47 to 17:37:13 KST with `codex / gpt-5.6-sol` and `codex-cli 0.154.0`. The comparator returned `FAIL` and `skill_lift_claim_eligible: false`.

The protocol's primary unit is unique majority-stable labels and predictions. Repeated precision is the repeated-run safeguard; P0 recall and clean specificity are also preregistered absolute metrics.

| Arm | Status | Stable precision | Stable recall | Stable F1 | Repeated precision | P0 stable-label recall | Clean-case specificity |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| full | PASS | 1.000000 | 0.958333 | 0.978723 | 0.943662 | 1.000000 | 1.000000 |
| catalog-only | FAIL | 0.884615 | 0.958333 | 0.920000 | 0.781609 | 1.000000 | 1.000000 |
| no-skill | FAIL | 0.351351 | 0.541667 | 0.426230 | 0.308943 | 0.375000 | 0.125000 |

The full arm's P0 stable-label recall was `1.000000`, but the pattern `#3` fix was designed after attempt 4 missed `pw-a06` in this same public corpus. `pw-a06` is therefore contaminated in this run, and its recovery is not evidence of generalization. A control arm's `FAIL` is not by itself a defect; the protocol applies the same absolute thresholds to every arm. The lift decision is separate:

| Lift check | Required | Full minus catalog-only | Pass | Full minus no-skill | Pass |
| --- | ---: | ---: | :---: | ---: | :---: |
| Stable F1 delta | >= 0.050000 | 0.058723 | yes | 0.552494 | yes |
| Stable F1 delta, paired-bootstrap 95% CI lower bound | >= 0.010000 | -0.003205 | no | 0.389899 | yes |
| Stable precision delta | >= -0.020000 | 0.115385 | yes | 0.648649 | yes |
| Stable recall delta | >= -0.020000 | 0.000000 | yes | 0.416667 | yes |
| Clean-case specificity delta | >= 0.000000 | 0.000000 | yes | 0.875000 | yes |
| Repeated precision delta | >= 0.000000 | 0.162053 | yes | 0.634719 | yes |

All six lift checks passed against `no-skill`. Against `catalog-only`, the stable F1 delta point estimate was `+0.058723` and cleared its `+0.050000` bar for the first time, but the paired-bootstrap 95% CI lower bound was `-0.003205` against the required `>= +0.010000`. That is the comparator's only failing reason. The result is `FAIL`, and the protocol refuses a skill-lift claim.

### Run history

| Run | Date (KST) | Measured revision | What was measured | Outcome | Why it is not the counted run |
| --- | --- | --- | --- | --- | --- |
| 1 | 2026-09-20 | `110f2ea` | Full arm only, run inside a Codex sandbox | `INCONCLUSIVE`; nested calls hung and 35/60 timed out; stopped | Incomplete sandbox execution |
| 2 | 2026-09-20 | `110f2ea` | Full arm only, run inside a Codex sandbox | Stopped after 9 of the first 11 calls timed out | Incomplete sandbox execution |
| 3 | 2026-09-20 | `110f2ea` | All three arms from the host; zero infrastructure errors; reports written inside the checkout | `INCONCLUSIVE` (`arm_provenance_mismatch`); each arm recorded a different `git_dirty_sha256` | Invalid cross-arm provenance |
| 4 | 2026-09-20 | `110f2ea` | All three arms with clean provenance; pre-trim reviewer before the release's `#3` fix | Counted at the time; full arm `FAIL` on P0 stable-label recall (`0.875`), whose `pw-a06` miss exposed the `#3` defect | Replaced by the clean run of the release commit and shipped skills |
| 5 | 2026-09-20 | `2ba34237cb0b` | All three arms with clean provenance; shipped skills | Full arm `PASS`; comparator `FAIL` on the single catalog-only CI-lower-bound threshold | Counted run |

The release history was squashed before attempt 5. Revisions recorded by the earlier reports, including `110f2ea`, `cb9aca2`, and other pre-squash IDs, are no longer reachable on this branch; their artifacts remain archived under `attempts/`, but their measured trees cannot be checked out from this history. The separate exploratory trim rerun at `cb9aca2` is archived under `attempts/trim-cb9aca2/`; it is not a numbered or counted attempt and contributes no metric to attempt 5.

### Claim limits

This is a single-host, single-model run on an inspectable public development corpus. It is not sealed, release-grade, cross-provider, cryptographically attested, or evidence of population-level generalization. The result supports only the recorded `FAIL` decision and descriptive arm metrics for this frozen corpus and execution.

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
