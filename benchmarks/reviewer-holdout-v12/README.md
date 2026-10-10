# Reviewer holdout v12

Reviewer holdout v12 is a single-host three-arm protocol on Codex `gpt-6-sol`. It reuses the frozen v10 corpus unchanged, by path and digest. It keeps v10's prompt arms, thresholds, schedule seed, strict-majority stability rule, numbered sources, scoring contract, and five repetitions, and carries v11's infrastructure-retry policy unchanged. It replaces v11 as the Codex run. [Reviewer holdout v13](../reviewer-holdout-v13/README.md) is the same design on Claude `claude-sonnet-5`.

Status: **run at `05962ec` on Codex `gpt-6-sol`; arm comparison `FAIL`, so no skill-lift claim**. The corpus is public development evidence that its author inspected while designing v10; it is not sealed and does not establish generalization.

## Result

The counted run is in `reports/`. It made 450 calls with no infrastructure error, and the preregistered retry policy was never triggered.

| Arm | Status | Stable P / R / F1 | Repeated TP / FP / FN |
|---|---|---|---|
| full | `PASS` | 0.981 / 0.981 / 0.981 | 257 / 10 / 8 |
| catalog-only | `FAIL` | 0.927 / 0.962 / 0.944 | 254 / 20 / 11 |
| no-skill | `FAIL` | 0.407 / 0.415 / 0.411 | 116 / 178 / 149 |

The arm comparison is `FAIL`:

- **Full minus no-skill:** stable F1 is +0.570, paired 95% interval +0.422 to +0.727.
- **Full minus catalog-only:** +0.037, paired 95% interval 0.000 to +0.086. That favors the full workflow but falls short of the preregistered +0.05 lift and its interval floor.
- **Host comparison:** on Claude `claude-opus-5`, v10's counted run on the same corpus gave −0.019 (−0.048 to 0.000). The value of the workflow references beyond the catalog depends on the host.

## Why v12 exists

- **The earlier holdouts used continuity models, not the current defaults.** Codex holdouts used `gpt-5.6-sol` and Claude holdouts used `claude-opus-5`, so results stayed comparable from one version to the next. The models users now run by default are `gpt-6-sol` on Codex and `claude-sonnet-5` on Claude.
- **V11 will not finish.** V11 was preregistered on Codex `gpt-5.6-sol`. Its official run was stopped during the full arm, before completion, when that model was retired. No v11 result is claimed. See [`../reviewer-holdout-v11/README.md`](../reviewer-holdout-v11/README.md).
- **V12 answers the arm questions on the current Codex default.** Is the full workflow better than the catalog alone, and is the skill better than no skill? The v10 cases were designed so that the deciding rule for eleven of them lives only in the full workflow references.
- **A 30-case corpus has enough power.** A power analysis on the current skill used a paired case bootstrap of the comparator's per-case stable rows. For the full-minus-catalog stable-F1 difference, it found a standard error of about 0.009 on Claude opus and about 0.012 on Codex `gpt-5.6-sol`. At 80% power, 30 cases detect a difference of about 0.025–0.033. No figure exists yet for `gpt-6-sol`.
- **The corpus is not fresh for the author.** It already ran on Claude `claude-opus-5` (v10, two `INCONCLUSIVE` attempts) and partly on Codex `gpt-5.6-sol` (the stopped v11 run). No model has seen it except through those runs, which do not train models.

## Infrastructure-retry policy

V12 carries v11's policy byte for byte, and the runner's protocol validator pins its exact form:

```json
"infrastructure_retry": {
  "max_attempts_per_call": 2,
  "retryable": [
    "timeout",
    "runner_nonzero_exit_with_usage_limit_text",
    "malformed_json_output"
  ],
  "contract": "..."
}
```

A scheduled call that times out, exits non-zero with a CLI usage-limit message, or exits zero with output that is not one strict JSON payload gets one more attempt. The retry runs in a freshly prepared, identical workspace at the same schedule position. The final attempt is scored, and every attempt is recorded. A scoreable output is never retried, including well-formed JSON with wrong findings. Integrity failures are never retried either. The full rules, record format, and comparator checks are in the [v11 README](../reviewer-holdout-v11/README.md#infrastructure-retry-policy).

## Corpus binding

V12 names the v10 corpus by its v10 path and digests. The runner and comparator allow this reuse for v11, v12, and v13 only:

- v12 refuses any other corpus path, and refuses the v10 path at any other digest.
- The v10 corpus under any protocol other than v10, v11, v12, or v13 is refused, by path in the protocol validator and by digest in the corpus-protocol pairing.
- The v10 protocol, corpus, sources, and archived attempts are unchanged, and so is the v11 protocol.

The 30 cases, their labels, and the expected-arm notes are documented in the [v10 README](../reviewer-holdout-v10/README.md).

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v10.json
cases SHA-256: 6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e
corpus SHA-256: 672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d
protocol: scripts/evals/reviewer-validation-protocol-v12.json
protocol SHA-256: ec42df85e7161ca96a807cbd0079eb9c406b926ae0c40bb4214f2b88280a5d20
```

The protocol differs from v11 only in these fields:

- `protocol_id` and `schedule.design_disclosure`.
- The model: `gpt-6-sol` in `host_matrix` and in each `arm_comparison.execution_order` step.

Its `execution_identity` (a `codex-cli 0.155.1` floor, no `claude_permission_mode`), `corpus`, and `infrastructure_retry` blocks are v11's, byte for byte.

## Exact rerun command

Run the three cells sequentially from the repository root in an ordinary host shell, not from inside a Codex sandbox. A nested `codex` call from a workspace-write sandbox hangs until timeout. Start from a clean tree so every arm records the same Git provenance. Set `CODEX_RUNNER` once to the explicit executable that reports `codex-cli 0.155.1` or later, and use that same path for every cell. Keep all generated reports outside the checkout until the comparison is complete, then copy the four JSON artifacts into the benchmark directory.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v12"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v12 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v12.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-codex.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v12.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm catalog-only --repetitions 5 --allow-live --report-only \
  --output "$OUT/catalog-only-codex.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v12.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
  --arm no-skill --repetitions 5 --allow-live --report-only \
  --output "$OUT/no-skill-codex.json"

python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v12.json \
  --compare-arms \
  --output "$OUT/arm-comparison.json"

mkdir -p benchmarks/reviewer-holdout-v12/reports
cp "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  "$OUT/arm-comparison.json" \
  benchmarks/reviewer-holdout-v12/reports/
```

The full run is exactly **450 scheduled model calls**: 30 cases x 5 repetitions x 3 prompt arms. Retries can add at most one extra invocation per scheduled call, so the matrix makes 450 to 900 invocations. The frozen hard limit remains 12 hours from the first start to the last completion, and retries count against it.

## Claim limits

- **Scope.** A v12 result is single-host, single-model evidence (Codex `gpt-6-sol`) on an inspectable public development corpus. One author wrote its labels, the same author who wrote the references under test, and two blind model labelers and a model arbiter checked them.
- **What it is not.** It is not sealed, release-grade, cross-provider, or cryptographically attested evidence, and it says nothing about population-level generalization.
- **Verdicts.** A `PASS` supports only the declared development skill-lift claim for this corpus, execution, schedule, and retry policy. `FAIL` or `INCONCLUSIVE` supports no skill-lift claim.
- **Comparability.** Results are not comparable across hosts with v10, the stopped v11 run, or v13. Each protocol answers its questions within its own host.
- **Corpus exposure.** The v10 attempt reports are public, so anyone who tunes the skill after reading them can fit this corpus. Any change under `skills/e2e-reviewer/` before the v12 run must be disclosed with the result.
- **Power.** The power figures are estimates from a case bootstrap of earlier per-case rows on other models, not a property of this run.
- **Retries.** The retry policy guards against infrastructure loss. It does not measure or correct model-run stochasticity.
