# Reviewer holdout v7 — frozen, not yet run

Reviewer holdout v7 is a Codex-only rerun protocol for the unchanged v5 public-development corpus. It was designed after the v5/v6 Claude Fable plan-mode failures showed that the runner's injected instruction could break the strict single-JSON output contract. V7 changes execution tooling and host scope, not cases, labels, scoring, stability, schedule seed, repetitions, or thresholds.

Status: **FROZEN / NOT_RUN**. No Reviewer holdout v7 result is claimed; no accuracy or skill-lift result is claimed.

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

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v5.json
cases SHA-256: 50c828c5e267a683ced73a161a645af0b73f305f6391b6fe0e8ee150ec419849
corpus SHA-256: 745bc765fb6f424abe90d6d3fc9a3b85e921472a4cc1291054879af8002e965f
protocol: scripts/evals/reviewer-validation-protocol-v7.json
protocol SHA-256: e379edfc7ad04e4ff92134f3f5952bda7f146e0f80667726283a2a60de08daf2
```

## Full run

Run the three cells sequentially from the repository root. Set `CODEX_RUNNER` once to the explicit executable that reports `codex-cli 0.154.0` or later; do not use a changing command name between cells.

```bash
CODEX_RUNNER=/absolute/path/to/codex
mkdir -p benchmarks/reviewer-holdout-v7/reports

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm full --repetitions 3 --allow-live --report-only \
  --output benchmarks/reviewer-holdout-v7/reports/full-codex.json
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm catalog-only --repetitions 3 --allow-live --report-only \
  --output benchmarks/reviewer-holdout-v7/reports/catalog-only-codex.json
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm no-skill --repetitions 3 --allow-live --report-only \
  --output benchmarks/reviewer-holdout-v7/reports/no-skill-codex.json

python3 scripts/evals/compare-reviewer-holdouts.py \
  benchmarks/reviewer-holdout-v7/reports/full-codex.json \
  benchmarks/reviewer-holdout-v7/reports/catalog-only-codex.json \
  benchmarks/reviewer-holdout-v7/reports/no-skill-codex.json \
  --cases scripts/evals/reviewer-holdout-v5.json \
  --protocol scripts/evals/reviewer-validation-protocol-v7.json \
  --output benchmarks/reviewer-holdout-v7/reports/arm-comparison.json
```

The full run is exactly **180 model calls**: 20 cases x 3 repetitions x 3 prompt arms. The completed v5 Codex full arm took about 12 minutes 41 seconds for 60 calls on 2026-09-19, so three sequential Codex arms are expected to take roughly 38–45 minutes under similar service conditions. The frozen hard limit remains 12 hours because provider latency can vary.

This remains public-development evidence. It is not sealed, release-grade, cryptographically attested, cross-provider, or evidence of population-level generalization.
