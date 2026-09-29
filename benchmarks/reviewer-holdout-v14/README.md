# Reviewer holdout v14

Reviewer holdout v14 is [reviewer holdout v13](../reviewer-holdout-v13/README.md) plus one preregistered output-normalization rule. It is a single-host three-arm protocol on Claude `claude-sonnet-5` that reuses the frozen v10 corpus unchanged, by path and digest. The rule applies identically to every arm. Everything else is v13's: host, CLI floor, permission mode, usage capture, retry policy, corpus, prompt arms, thresholds, schedule seed, strict-majority stability rule, numbered sources, scoring contract, and five repetitions.

Status: **run at `3bc1dd5` on Claude `claude-sonnet-5`; arm comparison `FAIL`, so no skill-lift claim**. The corpus is public development evidence that its author inspected while designing v10; it is not sealed and does not establish generalization.

## Result

The reports are in `reports/`. All 450 scheduled calls scored with no infrastructure error; one catalog-only call was retried once for malformed JSON and then scored. The evaluated skill is v13's (see the [v13 result](../reviewer-holdout-v13/README.md#result)).

| Arm | Status | Stable P / R / F1 | Repeated TP / FP / FN | Normalized runs |
|---|---|---|---|---|
| full | `FAIL` | 0.926 / 0.943 / 0.935 | 250 / 20 / 15 | 31 / 150 |
| catalog-only | `FAIL` | 0.889 / 0.906 / 0.897 | 237 / 40 / 28 | 62 / 150 |
| no-skill | `FAIL` | 0.407 / 0.453 / 0.429 | 119 / 211 / 146 | 17 / 150 |

Every normalized run scored. Full misses the per-report stable-precision floor (0.926 against 0.95). The arm comparison is `FAIL`:

- **Full minus no-skill:** stable F1 +0.506, paired 95% interval +0.390 to +0.638.
- **Full minus catalog-only:** +0.037, paired 95% interval −0.032 to +0.136, short of the preregistered +0.05 lift and its +0.01 interval floor.

## Why v14 exists

- **`claude-sonnet-5` fences its answers.** V13 judges every answer with the strict single-JSON-payload parser. The model often wrapped its answer in one Markdown code fence, even though the prompt asks for no fences:

  ````text
  ```json
  {"findings":[...]}
  ```
  ````

- **The retry policy could not recover it.** The strict parser rejects a fenced answer as `malformed_json_output`, so the retry policy re-invoked the call once. The model fenced its answer again. In v13, 6 of 150 full-arm calls and 21 of 150 catalog-only calls ended unscoreable this way.
- **V13 has no counted result.** No arm may have unscoreable runs, so v13 was stopped or finished without a counted result: its outcome is `INCONCLUSIVE`, and no v13 skill-lift result is claimed. V13's results are described separately in its own record, and v13's reports are not rescored under the v14 rule.
- **The rule was fixed before any v14 call.** It is part of the frozen protocol below. It was written from v13's failure mode, not from any v14 output, and it applies to every arm (full, catalog-only, and no-skill), so it cannot favor one arm's format.

## Output-normalization rule

The protocol declares the rule in a top-level block, and the runner's protocol validator pins its exact form, contract text included:

```json
"output_normalization": {
  "strip_single_json_fence": true,
  "contract": "..."
}
```

The rule fires only when the whole model answer, after trimming leading and trailing whitespace, is exactly one fenced block:

- the first line is exactly three backticks, optionally followed by `json` (lowercase, nothing else on the line);
- the last line is exactly three backticks, at the very end of the answer;
- lines are separated by LF;
- the text between the fences contains no other run of three backticks.

The runner then passes the text between the fences to the existing strict single-JSON-payload parser, unchanged. The parser, the findings validator, and the scorer are the same code v13 uses.

Every other answer goes to the strict parser as it does today. In particular, these are never recovered:

- prose before or after the fence;
- two fenced blocks;
- a fence without a closing line, or with the closing backticks on the last JSON line;
- a fence around non-JSON, or around JSON that is not one findings payload;
- any other info string (`javascript`, `JSON`), a four-backtick or tilde fence, or CRLF line endings.

An answer that is unrecoverable under the rule is still `malformed_json_output`, so the retry policy below re-invokes it once. A fence around well-formed JSON with wrong findings is scored like any other scoreable answer and is never retried.

### Records and counts

- **Runs.** Each run records `output_normalized`: `true` when the answer the strict parser judged was the text inside a single fence, whether it then scored or was refused. It is derived from the stored answer, so the comparator recomputes it and refuses a report whose flag disagrees.
- **Reports.** Each report records the `output_normalization` block and an `output_normalization_summary` for its arm: scheduled calls, normalized runs, and how many of those scored or ended unscoreable.
- **Comparison.** The comparator re-parses every fenced answer under the rule, re-derives each summary, and lists each arm's counts under `output_normalization`. It refuses normalization fields under every other protocol.
- **Earlier protocols.** V2–v13 keep their parsing, run records, and report schemas byte for byte. V13 still rejects the fenced answers that v14 accepts, and the v14 suite checks both.

## Execution

Claude runs with every tool disabled and no permission mode (`claude_permission_mode: "off"`), as in v10 and v13. Token-usage capture is enabled as in v13: Claude runs with `--output-format json`, the model's answer is the envelope's `result` string, and each run records its usage. The output-normalization rule applies to that answer string. Usage is descriptive cost evidence and enters no threshold or decision. The prompts are v13's byte for byte and still tell the model not to use Markdown fences; the rule is never announced to the model.

## Infrastructure-retry policy

V14 carries v11's policy byte for byte, and the runner's protocol validator pins its exact form:

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

A scheduled call that times out, exits non-zero with a CLI usage-limit message, or exits zero with an answer that is not one strict JSON payload after normalization gets one more attempt. The retry runs in a freshly prepared, identical workspace at the same schedule position. The final attempt is scored, and every attempt is recorded. A scoreable output is never retried, including well-formed JSON with wrong findings. The full rules are in the [v11 README](../reviewer-holdout-v11/README.md#infrastructure-retry-policy).

## Corpus binding

V14 names the v10 corpus by its v10 path and digests. The runner and comparator allow this reuse for v11, v12, v13, and v14 only. V14 refuses any other corpus path and refuses the v10 path at any other digest. The v10–v13 protocols are unchanged. The 30 cases, their labels, and the expected-arm notes are documented in the [v10 README](../reviewer-holdout-v10/README.md).

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v10.json
cases SHA-256: 6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e
corpus SHA-256: 672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d
protocol: scripts/evals/reviewer-validation-protocol-v14.json
protocol SHA-256: c668d7308c4ec841998c26c052a8900a1da99d2057955e79b39d76848a20c679
```

The protocol differs from v13 only in `protocol_id`, `schedule.design_disclosure`, and the added `output_normalization` block, which follows `usage_capture`.

## Exact rerun command

Run the three cells sequentially from the repository root in an ordinary host shell. Start from a clean tree so every arm records the same Git provenance. Set `CLAUDE_RUNNER` once to the explicit executable that reports `Claude Code 2.1.281` or later; do not use a changing command name between cells. Keep all generated reports outside the checkout until the comparison is complete, then copy the four JSON artifacts into the benchmark directory.

```bash
CLAUDE_RUNNER=/absolute/path/to/claude
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v14"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v14 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v14.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-sonnet-5 \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-claude.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v14.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-sonnet-5 \
  --arm catalog-only --repetitions 5 --allow-live --report-only \
  --output "$OUT/catalog-only-claude.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v14.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-sonnet-5 \
  --arm no-skill --repetitions 5 --allow-live --report-only \
  --output "$OUT/no-skill-claude.json"

python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full-claude.json" \
  "$OUT/catalog-only-claude.json" \
  "$OUT/no-skill-claude.json" \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v14.json \
  --compare-arms \
  --output "$OUT/arm-comparison.json"

mkdir -p benchmarks/reviewer-holdout-v14/reports
cp "$OUT/full-claude.json" \
  "$OUT/catalog-only-claude.json" \
  "$OUT/no-skill-claude.json" \
  "$OUT/arm-comparison.json" \
  benchmarks/reviewer-holdout-v14/reports/
```

The full run is exactly **450 scheduled model calls**: 30 cases x 5 repetitions x 3 prompt arms. Retries can add at most one extra invocation per scheduled call, so the matrix makes 450 to 900 invocations. The frozen hard limit remains 12 hours from the first start to the last completion, and retries count against it.

## Claim limits

- **Scope.** A v14 result is single-host, single-model evidence (Claude `claude-sonnet-5`) on an inspectable public development corpus. One author wrote its labels, the same author who wrote the references under test, and two blind model labelers and a model arbiter checked them.
- **What it is not.** It is not sealed, release-grade, cross-provider, or cryptographically attested evidence, and it says nothing about population-level generalization.
- **Verdicts.** A `PASS` supports only the declared development skill-lift claim for this corpus, execution, schedule, retry policy, and normalization rule. `FAIL` or `INCONCLUSIVE` supports no skill-lift claim.
- **Normalization.** The rule measures review accuracy through a model's formatting habit; it does not measure format compliance. Normalized-run counts per arm are reported so a reader can see how much each arm relied on it.
- **Corpus exposure.** The corpus already ran on Claude `claude-opus-5` (v10), partly on Codex `gpt-5.6-sol` (the stopped v11 run), on Codex `gpt-6-sol` (v12), and on `claude-sonnet-5` itself under v13. Those runs do not train models, but their reports are public, so anyone who tunes the skill after reading them can fit this corpus. Any change under `skills/e2e-reviewer/` before the v14 run must be disclosed with the result.
- **Comparability.** Results are not comparable across hosts with v10, v11, or v12, and v14 is not a rescoring of v13.
