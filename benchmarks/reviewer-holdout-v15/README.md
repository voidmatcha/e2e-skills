# Reviewer holdout v15

Reviewer holdout v15 is [reviewer holdout v13](../reviewer-holdout-v13/README.md) plus one preregistered enforced output schema. The runner hands the schema to the host CLI's native structured-output option, so the model cannot return a fenced or prose-wrapped answer. It is a single-host three-arm protocol on Claude `claude-sonnet-5` that reuses the frozen v10 corpus unchanged, by path and digest. The schema applies identically to every arm. It carries no output normalization: [v14](../reviewer-holdout-v14/README.md)'s fence rule is not part of v15. Everything else is v13's except the Claude Code floor: host, permission mode, usage capture, retry policy, corpus, prompt arms, prompts, thresholds, schedule seed, strict-majority stability rule, numbered sources, scoring contract, and five repetitions.

Status: **run at `769f1f6` on Claude `claude-sonnet-5`; arm comparison `INCONCLUSIVE`, so no skill-lift claim**. The corpus is public development evidence that its author inspected while designing v10; it is not sealed and does not establish generalization.

## Result

The reports are in `reports/`. The arm comparison is `INCONCLUSIVE` (`arm_input_incomplete` for catalog-only) with no metrics: one catalog-only call, `v10-cy-07` repetition 1, ended with `runner exited 1`, which is not a retryable reason, so the call is unscoreable and the catalog-only report is `INCONCLUSIVE`. Every other call scored. Five calls timed out once (full 1, catalog-only 2, no-skill 2) and scored on retry. The evaluated skill is v13's (see the [v13 result](../reviewer-holdout-v13/README.md#result)).

The schema did what it was for: no call in any arm produced malformed JSON, against 31 unscoreable fenced answers in v13. Accuracy stayed close to v14's. Descriptive metrics, which support no claim:

| Arm | Status | Scored calls | Stable P / R / F1 | Repeated TP / FP / FN |
|---|---|---|---|---|
| full | `FAIL` | 150 | 0.943 / 0.943 / 0.943 | 246 / 21 / 19 |
| catalog-only | `INCONCLUSIVE` | 149 | 0.925 / 0.925 / 0.925 | 241 / 31 / 23 |
| no-skill | `FAIL` | 150 | 0.400 / 0.453 / 0.425 | 118 / 224 / 147 |

Full misses the per-report stable-precision floor (0.943 against 0.95) and the clean-case specificity floor (0.75 against 0.95).

## Why v15 exists

- **V13 lost runs to formatting.** V13 judges every answer with the strict single-JSON-payload parser, and `claude-sonnet-5` often wrapped its answer in one Markdown code fence. The retry policy re-invoked each such call once, and the model fenced its answer again. In v13, 6 of 150 full-arm calls, 21 of 150 catalog-only calls, and 4 of 150 no-skill calls ended unscoreable. No arm may have unscoreable runs, so v13 ended `INCONCLUSIVE` and no v13 skill-lift result is claimed.
- **V14 repairs the answer; v15 prevents the failure.** V14 unwraps one whole-answer fence after the answer arrives. V15 asks the host to constrain the answer to a JSON schema at generation time, so the failure class cannot occur, and the answer is judged by the strict parser with no repair.
- **The schema was fixed before any v15 call.** It is part of the frozen protocol below and applies to every arm (full, catalog-only, and no-skill). V13's and v14's reports are not rescored under it.

## Enforced output schema

The protocol declares a top-level `output_schema` block with `mode: "enforced"`, the schema itself, its `schema_sha256`, and a contract. The runner's protocol validator pins the exact block, and each report records it, so the schema and its digest are part of the run provenance. The digest is the SHA-256 of the schema serialized as compact, sorted-key JSON, the exact bytes the runner passes to the CLI:

```text
schema SHA-256: 9bfd806c73c083a2b8af13a2199523651567d4fe4442c392c09174a122139aa3
```

The schema admits an object with exactly one property, `findings`, an array of objects with exactly `pattern_id`, `severity`, `file`, and `line`. Every object is closed (`additionalProperties: false`) and requires all of its properties, as OpenAI strict schemas demand:

- `pattern_id` is one of the 44 IDs in the output legend every arm's prompt already shows: `#1`, `#10`, `#10a`–`#10f`, `#11`, `#11c`, `#12`–`#23`, `#2`, `#3`, `#3b`, `#4a`, `#4b`, `#4c-4e`, `#4f`–`#4k`, `#5a`, `#5b`, `#6`, `#7`, `#8`, `#8a`, `#8b`, `#9`, `#9b`, and `#9c`. The list is derived from the same source as the legend and the corpus validator (the `SKILL.md` Quick Reference, `scan.sh` checks, and the `pattern-reference.md` sub-IDs). Every label and accepted alternative of the v10 corpus uses one of these IDs, so the schema never forbids a correct answer. A run refuses to start if the evaluated skill's legend names a different set.
- `severity` is `P0`, `P1`, or `P2`.
- `file` is any string. The findings validator still checks it as a safe workspace-relative path.
- `line` is an integer of at least 1.

The schema constrains the shape of an answer, not which findings the model reports.

### How the answer is read

- **Claude.** The runner adds `--output-format json --json-schema <schema>`. The answer is the envelope's `structured_output` object, serialized as compact JSON. A result whose `structured_output` is missing or not an object is malformed output, `malformed_json_output` under the retry policy. The free-text `result` is kept as the recorded output and is never scored instead. Claude Code implements structured output with an internal tool call; the model-callable tool surface is still empty.
- **Codex.** The runner writes the schema to a file in the runner-private home and adds `--output-schema <file>`; the answer is the final agent message, as before. V15's host is Claude, so this path matters only to a later Codex protocol.
- **Validation.** Either answer goes through the unchanged strict single-JSON-payload parser, findings validator, and scorer. No fence or other normalization is applied, and a fenced answer stays `malformed_json_output`.
- **Custom runners.** A stub or other custom runner receives no schema flag and prints plain text, as it does under every protocol.

The stored `output` of a scored Claude run is the serialized `structured_output`, so the comparator re-parses and re-scores it exactly as it does for earlier protocols. Run records keep v13's schema; each report adds only the `output_schema` block, which the comparator checks against the protocol and refuses under every other protocol.

## Execution

Claude runs with every tool disabled and no permission mode (`claude_permission_mode: "off"`), as in v10 and v13. Usage capture is enabled as in v13, and usage is descriptive cost evidence that enters no threshold or decision. The prompts are v13's byte for byte; they still ask for bare JSON and never mention the schema. The Claude Code floor is `Claude Code 2.1.283`, the build whose `--json-schema` behavior was probed before the protocol was frozen; v13 and v14 keep `2.1.281`.

## Infrastructure-retry policy

V15 carries v11's policy byte for byte, and the runner's protocol validator pins its exact form:

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

A scheduled call that times out, exits non-zero with a CLI usage-limit message, or exits zero with an answer that is not one strict JSON payload (including a missing `structured_output`) gets one more attempt in a freshly prepared, identical workspace at the same schedule position. The final attempt is scored, and every attempt is recorded. A scoreable output is never retried, including well-formed JSON with wrong findings. The full rules are in the [v11 README](../reviewer-holdout-v11/README.md#infrastructure-retry-policy).

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v10.json
cases SHA-256: 6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e
corpus SHA-256: 672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d
protocol: scripts/evals/reviewer-validation-protocol-v15.json
protocol SHA-256: 0e79b040aab2b47865ca13a6a484fb3bcad617ef16bcc38b4de7a49b12498d93
```

The protocol differs from v13 only in `protocol_id`, `schedule.design_disclosure`, the Claude Code floor, and the added `output_schema` block, which follows `usage_capture`. The runner and comparator allow reuse of the v10 corpus for v11 through v15 only; the v10–v14 protocols are unchanged.

## Exact rerun command

Run the three cells sequentially from the repository root in an ordinary host shell. Start from a clean tree so every arm records the same Git provenance. Set `CLAUDE_RUNNER` once to the explicit executable that reports `Claude Code 2.1.283` or later. Keep all generated reports outside the checkout until the comparison is complete, then copy the four JSON artifacts into the benchmark directory.

```bash
CLAUDE_RUNNER=/absolute/path/to/claude
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v15"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v15 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v15.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-sonnet-5 \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-claude.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v15.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-sonnet-5 \
  --arm catalog-only --repetitions 5 --allow-live --report-only \
  --output "$OUT/catalog-only-claude.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v15.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-sonnet-5 \
  --arm no-skill --repetitions 5 --allow-live --report-only \
  --output "$OUT/no-skill-claude.json"

python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full-claude.json" \
  "$OUT/catalog-only-claude.json" \
  "$OUT/no-skill-claude.json" \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v15.json \
  --compare-arms \
  --output "$OUT/arm-comparison.json"

mkdir -p benchmarks/reviewer-holdout-v15/reports
cp "$OUT/full-claude.json" \
  "$OUT/catalog-only-claude.json" \
  "$OUT/no-skill-claude.json" \
  "$OUT/arm-comparison.json" \
  benchmarks/reviewer-holdout-v15/reports/
```

The full run is exactly **450 scheduled model calls**: 30 cases x 5 repetitions x 3 prompt arms. Retries can add at most one extra invocation per scheduled call, so the matrix makes 450 to 900 invocations. The frozen hard limit remains 12 hours from the first start to the last completion, and retries count against it.

## Claim limits

- **Scope.** A v15 result is single-host, single-model evidence (Claude `claude-sonnet-5`) on an inspectable public development corpus. One author wrote its labels, the same author who wrote the references under test, and two blind model labelers and a model arbiter checked them.
- **What it is not.** It is not sealed, release-grade, cross-provider, or cryptographically attested evidence, and it says nothing about population-level generalization.
- **Verdicts.** A `PASS` supports only the declared development skill-lift claim for this corpus, execution, schedule, retry policy, and output schema. `FAIL` or `INCONCLUSIVE` supports no skill-lift claim.
- **Schema.** The schema measures review accuracy with the answer format enforced by the host; it does not measure format compliance. Constrained decoding may differ from free-text generation in ways this protocol does not isolate, and it applies equally to every arm.
- **Corpus exposure.** The corpus already ran on Claude `claude-opus-5` (v10), partly on Codex `gpt-5.6-sol` (the stopped v11 run), on Codex `gpt-6-sol` (v12), and on `claude-sonnet-5` itself under v13. Those runs do not train models, but their reports are public, so anyone who tunes the skill after reading them can fit this corpus. Any change under `skills/e2e-reviewer/` before the v15 run must be disclosed with the result.
- **Comparability.** Results are not comparable across hosts with v10, v11, or v12, and v15 is not a rescoring of v13 or v14.
