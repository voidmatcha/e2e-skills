# Reviewer holdout v13

Reviewer holdout v13 is a single-host three-arm protocol on Claude `claude-sonnet-5`. It reuses the frozen v10 corpus unchanged, by path and digest. It keeps v10's prompt arms, thresholds, schedule seed, strict-majority stability rule, numbered sources, scoring contract, and five repetitions, and carries v11's infrastructure-retry policy unchanged. It is the Claude counterpart of [reviewer holdout v12](../reviewer-holdout-v12/README.md), which runs the same design on Codex `gpt-6-sol`.

Status: **run at `79d6d8f` on Claude `claude-sonnet-5`; arm comparison `INCONCLUSIVE`, so no skill-lift claim**. The corpus is public development evidence that its author inspected while designing v10; it is not sealed and does not establish generalization.

## Result

The reports are in `reports/`. Every arm ended with unscoreable calls, so every arm report is `INCONCLUSIVE` and the arm comparison is `INCONCLUSIVE` (`arm_input_incomplete` for all three arms) with no metrics.

- **Cause.** `claude-sonnet-5` wrapped its JSON answer in one Markdown code fence. The strict parser rejects that as `malformed_json_output`, the retry policy re-invoked the call once, and the model fenced again. Every unscoreable call's stored answer is one fenced block.
- **Unscoreable calls per 150:** full 6, catalog-only 21, no-skill 4. Retries: 26, 47, and 16 (no-skill: 13 malformed, 3 timeouts), of which 20, 26, and 12 scored.
- **Skill.** The evaluated skill (`skill_sha256` `c3b545315f18…`) includes `78053e6`, committed after preregistration, which requires the pattern ID in every finding heading. It changes the full-arm prompt (`SKILL.md`, `references/reporting.md`), not the catalog-only or no-skill prompt or the JSON answer format. V14 and v15 ran the same skill.

Descriptive metrics over scored calls only, which support no claim:

| Arm | Scored calls | Stable P / R / F1 | Repeated TP / FP / FN |
|---|---|---|---|
| full | 144 | 0.909 / 0.943 / 0.926 | 232 / 25 / 16 |
| catalog-only | 129 | 0.905 / 0.717 / 0.800 | 182 / 27 / 22 |
| no-skill | 146 | 0.377 / 0.377 / 0.377 | 103 / 188 / 152 |

[V14](../reviewer-holdout-v14/README.md) (fence normalization) and [v15](../reviewer-holdout-v15/README.md) (enforced output schema) rerun this design.

## Why v13 exists

- **The earlier holdouts used continuity models, not the current defaults.** Codex holdouts used `gpt-5.6-sol` and Claude holdouts used `claude-opus-5`, so results stayed comparable from one version to the next. The models users now run by default are `gpt-6-sol` on Codex and `claude-sonnet-5` on Claude.
- **V13 answers the arm questions on the current Claude default.** Is the full workflow better than the catalog alone, and is the skill better than no skill? The v10 cases were designed so that the deciding rule for eleven of them lives only in the full workflow references.
- **V10 lost both attempts to infrastructure.** V10 ran twice on Claude `claude-opus-5` and ended `INCONCLUSIVE` both times: a weekly usage limit, then one malformed-JSON output. V13 carries the retry policy that v11 introduced for exactly those failures. See [`../reviewer-holdout-v10/README.md`](../reviewer-holdout-v10/README.md).
- **A 30-case corpus has enough power.** A power analysis on the current skill used a paired case bootstrap of the comparator's per-case stable rows. For the full-minus-catalog stable-F1 difference, it found a standard error of about 0.009 on Claude opus and about 0.012 on Codex `gpt-5.6-sol`. At 80% power, 30 cases detect a difference of about 0.025–0.033. No figure exists yet for `claude-sonnet-5`.
- **The corpus is not fresh for the author.** It already ran on Claude `claude-opus-5` (v10, two `INCONCLUSIVE` attempts) and partly on Codex `gpt-5.6-sol`. V11 was preregistered on that model, and its official run was stopped during the full arm, before completion, when the model was retired; no v11 result is claimed. No model has seen the corpus except through those runs, which do not train models.

## Execution

Claude runs with every tool disabled and no permission mode (`claude_permission_mode: "off"`), as in v10, so the plan-file failure that ended the v5 and v6 Claude runs cannot occur. The runner's protocol validator refuses a v13 protocol that declares any other permission mode or omits it.

## Infrastructure-retry policy

V13 carries v11's policy byte for byte, and the runner's protocol validator pins its exact form:

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

A weekly usage limit lasts longer than one retry. A retry only recovers a call that the limit refused near its reset. If the limit holds, the call stays an infrastructure error and the matrix ends `INCONCLUSIVE`, as v10's first attempt did.

## Usage capture

Token-usage capture was added to v13 before any v13 run. The protocol opts in with a top-level `"usage_capture": {"enabled": true}` block, and the runner's protocol validator pins that exact form. No earlier protocol declares it, so v2–v12 keep their text-output commands, run records, and report schemas.

- **Invocation.** Claude runs with `--output-format json` in place of the default text output. Every other flag is unchanged: all tools disabled, no permission mode, no session persistence.
- **Scoring.** The model's answer is the envelope's `result` string. The same strict single-JSON-payload parser and scorer judge it as they judge text output, so a malformed answer is still `malformed_json_output` and is retried under the policy above.
- **Malformed envelope.** An envelope that is not one strict JSON object reporting a successful, non-error result is an unscoreable call. It is not one of the preregistered retryable reasons, so it is not retried.
- **Records.** Each run, and each attempt, records `usage`: `input_tokens`, `cached_input_tokens` (Claude's cache reads), `cache_write_tokens` (cache creation), and `output_tokens`. Each report adds a `usage_summary` with totals and means for the scored attempts and for all attempts, and the comparator surfaces every arm's summary under `usage_capture`.
- **Claim scope.** Usage is descriptive cost evidence. It enters no threshold, status, or decision.

## Corpus binding

V13 names the v10 corpus by its v10 path and digests. The runner and comparator allow this reuse for v11, v12, and v13 only:

- v13 refuses any other corpus path, and refuses the v10 path at any other digest.
- The v10 corpus under any protocol other than v10, v11, v12, or v13 is refused, by path in the protocol validator and by digest in the corpus-protocol pairing.
- The v10 protocol, corpus, sources, and archived attempts are unchanged, and so is the v11 protocol.

The 30 cases, their labels, and the expected-arm notes are documented in the v10 README.

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v10.json
cases SHA-256: 6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e
corpus SHA-256: 672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d
protocol: scripts/evals/reviewer-validation-protocol-v13.json
protocol SHA-256: 6803125914bd03ff07e724614636b2e8a040e6a13932f2af6b187a87ed78ff7b
```

The protocol differs from v11 only in these fields:

- `protocol_id` and `schedule.design_disclosure`.
- The host: `host_matrix`, the host named in each `arm_comparison.execution_order` step, and the single-host Claude wording of `cross_host_decision`, all as in v10 with the model set to `claude-sonnet-5`.
- `execution_identity`, which is v10's: a `Claude Code 2.1.281` floor and `claude_permission_mode: "off"`.
- `usage_capture`, which v11 does not have. See [Usage capture](#usage-capture).

Its `corpus` and `infrastructure_retry` blocks are v11's, byte for byte.

## Exact rerun command

Run the three cells sequentially from the repository root in an ordinary host shell. Start from a clean tree so every arm records the same Git provenance. Set `CLAUDE_RUNNER` once to the explicit executable that reports `Claude Code 2.1.281` or later; do not use a changing command name between cells. Keep all generated reports outside the checkout until the comparison is complete, then copy the four JSON artifacts into the benchmark directory.

```bash
CLAUDE_RUNNER=/absolute/path/to/claude
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v13"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v13 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v13.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-sonnet-5 \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-claude.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v13.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-sonnet-5 \
  --arm catalog-only --repetitions 5 --allow-live --report-only \
  --output "$OUT/catalog-only-claude.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v13.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-sonnet-5 \
  --arm no-skill --repetitions 5 --allow-live --report-only \
  --output "$OUT/no-skill-claude.json"

python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full-claude.json" \
  "$OUT/catalog-only-claude.json" \
  "$OUT/no-skill-claude.json" \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v13.json \
  --compare-arms \
  --output "$OUT/arm-comparison.json"

mkdir -p benchmarks/reviewer-holdout-v13/reports
cp "$OUT/full-claude.json" \
  "$OUT/catalog-only-claude.json" \
  "$OUT/no-skill-claude.json" \
  "$OUT/arm-comparison.json" \
  benchmarks/reviewer-holdout-v13/reports/
```

The full run is exactly **450 scheduled model calls**: 30 cases x 5 repetitions x 3 prompt arms. Retries can add at most one extra invocation per scheduled call, so the matrix makes 450 to 900 invocations. The frozen hard limit remains 12 hours from the first start to the last completion, and retries count against it.

## Claim limits

- **Scope.** A v13 result is single-host, single-model evidence (Claude `claude-sonnet-5`) on an inspectable public development corpus. One author wrote its labels, the same author who wrote the references under test, and two blind model labelers and a model arbiter checked them.
- **What it is not.** It is not sealed, release-grade, cross-provider, or cryptographically attested evidence, and it says nothing about population-level generalization.
- **Verdicts.** A `PASS` supports only the declared development skill-lift claim for this corpus, execution, schedule, and retry policy. `FAIL` or `INCONCLUSIVE` supports no skill-lift claim.
- **Comparability.** Results are not comparable across hosts with v10, the stopped v11 run, or v12. Each protocol answers its questions within its own host.
- **Corpus exposure.** The v10 attempt reports are public, so anyone who tunes the skill after reading them can fit this corpus. Any change under `skills/e2e-reviewer/` before the v13 run must be disclosed with the result.
- **Power.** The power figures are estimates from a case bootstrap of earlier per-case rows on other models, not a property of this run.
- **Retries.** The retry policy guards against infrastructure loss. It does not measure or correct model-run stochasticity.
