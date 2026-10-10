# Reviewer holdout v11

Reviewer holdout v11 is a single-host three-arm protocol on Codex `gpt-5.6-sol`. It reuses the frozen v10 corpus unchanged, by path and digest. It keeps v10's prompt arms, thresholds, schedule seed, strict-majority stability rule, numbered sources, scoring contract, and five repetitions. It was the first reviewer holdout to preregister an infrastructure-retry policy; v12 and v13 carry the same policy.

Status: preregistered; the official run was stopped during the full arm when gpt-5.6-sol was retired, and v12 (gpt-6-sol) replaces it. No v11 result is claimed. The partial full-arm report is kept outside the repository. See [`../reviewer-holdout-v12/README.md`](../reviewer-holdout-v12/README.md). The corpus is public development evidence that its author inspected while designing v10; it is not sealed and does not establish generalization.

## Why v11 exists

- **V10 ended `INCONCLUSIVE` twice for infrastructure reasons.** V10 ran twice on Claude `claude-opus-5`. In attempt 1, the Claude subscription's weekly usage limit refused every call after call 72 of the catalog-only arm. In attempt 2, one no-skill call returned malformed JSON. The comparator requires every arm to finish its schedule without an unscoreable run, so neither attempt can be counted, although neither failure was a reviewer error. See [`../reviewer-holdout-v10/README.md`](../reviewer-holdout-v10/README.md).
- **The v10 corpus has not been run on Codex.** V7–v9 ran on Codex, and v10 moved to Claude before its first run.
- **A 30-case corpus has enough power on Codex.** A power analysis on the current skill used a paired case bootstrap of the comparator's per-case stable rows. It found a Codex standard error of about 0.012 for the full-minus-catalog stable-F1 difference, so 30 cases detect a difference of about 0.033 at 80% power. The v10 README's figure of about 0.125 came from v9's per-case rows (standard error 0.045) and does not apply to this host and skill.
- **V11 answers the full-versus-catalog question on Codex.** It uses the v10 cases, which were designed so the deciding rule for eleven of them lives only in the full workflow references. A preregistered infrastructure-retry policy stops one transient failure from voiding a 450-call matrix.

## Infrastructure-retry policy

The protocol declares the policy, and the runner's protocol validator pins its exact form:

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

- **Retried failures.** A scheduled call is re-invoked when its attempt ends unscoreable for one of three reasons:
  - `timeout`: the call hit the runner timeout.
  - `runner_nonzero_exit_with_usage_limit_text`: the CLI exited non-zero, and its stdout or stderr matched a usage-limit message (`You've hit your`, `usage limit`, `weekly limit`, or `rate limit`). The match is never applied on a zero exit.
  - `malformed_json_output`: the CLI exited zero, but its output was not one strict JSON payload.
- **Re-invocation.** The retry runs in a freshly prepared, identical workspace at the same schedule position, with the same prompt, up to two attempts per call.
- **Scoring.** The final attempt is the one scored. If it is still unscoreable, the call stays an infrastructure error, exactly as it would under v10.
- **What is never retried.** A scoreable output is never retried, including well-formed JSON with wrong findings. Integrity failures are never retried either: a mutated workspace, a changed staged skill, credential-shaped output, a schema-invalid findings payload, or any other non-zero exit.
- **Records.** Each run record carries an `attempts` list with every attempt's number, reason, exit code, and error. The report adds the policy (`infrastructure_retry`) and a count summary (`infrastructure_retry_summary`): scheduled calls, total attempts, retried calls, retries by reason, calls scored after a retry, and calls whose last attempt still had a retryable failure. Stderr is used only for the usage-limit match. The report keeps only its digest marker, as before.
- **Comparison.** The comparator recomputes and checks the attempt records and the summary. It treats a call that was retried and then scored as an ordinary scored run, and its output lists each arm's retry counts under `infrastructure_retry`.
- **Other protocols.** Only protocols that list the policy retry. Protocols v2–v10 run each call exactly once, write the same run records as before, and refuse a report that carries retry fields.

A retry changes which output is scored for an affected call. A model that is more likely to time out or emit malformed JSON on a given case gets a second draw on exactly those calls. The retry counts are published so that effect stays visible. A large or arm-skewed retry count is a caveat on the result, not something the threshold decision absorbs.

## Corpus binding

V11 names the v10 corpus by its v10 path and digests. The runner and comparator allow this reuse for v11, v12, and v13 only:

- v11 refuses any other corpus path, and refuses the v10 path at any other digest.
- The v10 corpus under any protocol other than v10, v11, v12, or v13 is refused, by path in the protocol validator and by digest in the corpus-protocol pairing.
- The v10 protocol, corpus, sources, and archived attempts are unchanged.

The 30 cases, their labels, and the expected-arm notes are documented in the v10 README.

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v10.json
cases SHA-256: 6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e
corpus SHA-256: 672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d
protocol: scripts/evals/reviewer-validation-protocol-v11.json
protocol SHA-256: 5676b452de7d6fce7ae7292bf21248b2dbeef3eeb493175cf85024299dee1bf1
```

The protocol differs from v10 only in these fields:

- `protocol_id` and `schedule.design_disclosure`.
- The host: `host_matrix`, `execution_identity` (a `codex-cli 0.155.1` floor, no `claude_permission_mode`), the host named in each `arm_comparison.execution_order` step, and the Codex-only wording of `cross_host_decision`.
- The new `infrastructure_retry` block.

The `corpus` block is v10's, byte for byte.

## Exact rerun command

Run the three cells sequentially from the repository root in an ordinary host shell, not from inside a Codex sandbox. A nested `codex` call from a workspace-write sandbox hangs until timeout. Start from a clean tree so every arm records the same Git provenance. Set `CODEX_RUNNER` once to the explicit executable that reports `codex-cli 0.155.1` or later, and use that same path for every cell. Keep all generated reports outside the checkout until the comparison is complete, then copy the four JSON artifacts into the benchmark directory.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v11"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v11 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v11.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-codex.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v11.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm catalog-only --repetitions 5 --allow-live --report-only \
  --output "$OUT/catalog-only-codex.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v11.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm no-skill --repetitions 5 --allow-live --report-only \
  --output "$OUT/no-skill-codex.json"

python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v11.json \
  --compare-arms \
  --output "$OUT/arm-comparison.json"

mkdir -p benchmarks/reviewer-holdout-v11/reports
cp "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  "$OUT/arm-comparison.json" \
  benchmarks/reviewer-holdout-v11/reports/
```

The full run is exactly **450 scheduled model calls**: 30 cases x 5 repetitions x 3 prompt arms. Retries can add at most one extra invocation per scheduled call, so the matrix makes 450 to 900 invocations. The frozen hard limit remains 12 hours from the first start to the last completion, and retries count against it.

## Claim limits

- **Scope.** A v11 result is single-host, single-model evidence (Codex `gpt-5.6-sol`) on an inspectable public development corpus. One author wrote its labels, the same author who wrote the references under test, and two blind model labelers and a model arbiter checked them.
- **What it is not.** It is not sealed, release-grade, cross-provider, or cryptographically attested evidence, and it says nothing about population-level generalization.
- **Verdicts.** A `PASS` supports only the declared development skill-lift claim for this corpus, execution, schedule, and retry policy. `FAIL` or `INCONCLUSIVE` supports no skill-lift claim.
- **Comparability.** Results are not comparable across hosts with the v10 Claude attempts.
- **Corpus exposure.** The v10 attempt reports are public, so anyone who tunes the skill after reading them can fit this corpus. Any change under `skills/e2e-reviewer/` before the v11 run must be disclosed with the result.
- **Power.** The power figure is an estimate from a case bootstrap of earlier per-case rows, not a property of this run.
- **Retries.** The retry policy guards against infrastructure loss. It does not measure or correct model-run stochasticity.
