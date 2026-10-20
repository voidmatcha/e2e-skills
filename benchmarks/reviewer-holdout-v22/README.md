# Reviewer holdout v22: current 3.0.0 development confirmation

Status: **PASS** (`release_confirmation_passed`), limited to public development evidence. All 540 scheduled calls completed on 2026-10-19, from 16:36:45 to 17:45:24 UTC (68 minutes 39 seconds). `release_eligible` is `false`.

## Result

The [original arm reports and comparison](reports/) were copied byte for byte from the run cache. All **540/540** calls scored, with **0 infrastructure errors, 0 retries and 0 reported stream-guard violations**. Each arm passed immutable-input and staged-skill pre/post checks. All 540 stored final-answer JSON payloads were reparsed and rescored; the comparator validated the complete matrix against the frozen gates.

| Arm | Report status | Scored calls | Stable precision | Stable recall | Stable F1 |
|---|---|---:|---:|---:|---:|
| full | `PASS` | 180/180 | 0.976 | 1.000 | 0.988 |
| catalog-only | `FAIL` | 180/180 | 0.886 | 0.975 | 0.929 |
| no-skill | `FAIL` | 180/180 | 0.356 | 0.400 | 0.376 |

Full minus no-skill stable F1 was **+0.611**, paired stratified bootstrap 95% CI **[+0.464, +0.760]**. Both frozen primary lift gates passed, and full passed its absolute gates. Full minus catalog-only was **+0.059**, 95% CI **[+0.013, +0.102]**; this comparison is descriptive. The complete control reports fail the full skill's absolute thresholds without invalidating their execution. Five repetitions measure label stability; they do not turn 36 public cases into 180 independent defects.

See [outcome.json](outcome.json) for the result receipt, artifact hashes and execution limits. The machine-readable reason retains the inherited name `release_confirmation_passed`; it does not establish sealed release evidence or overall release readiness.

## Preregistration

The [v22 protocol](../../scripts/evals/reviewer-validation-protocol-v22.json) derives from frozen [v19](../reviewer-holdout-v19/README.md). It reuses the unchanged 36-case public AI-authored v17 development corpus, five repetitions and Codex `gpt-6-sol`. The 180-call arms run sequentially: `full`, `catalog-only`, `no-skill`. The registered maximum is 12 hours from the first scored start to the final completion, with 180 seconds per attempt and at most two attempts under the declared infrastructure retry policy. Exhausted authentication or capacity errors stop v22 before the next scheduled cell. No scoreable output is retried; no model or identity switch, cell replacement, or result-dependent threshold change is allowed.

The candidate reviewer SHA-256 is `7ff53a2999b80f2f777679fe8dd80941f6ad84b74d36ada43084573f3eeb3c10`. The CLI is `codex-cli 0.159.3`; the protocol uses a minimum version floor and all arms must report one identical resolved runner identity. The scorer, comparator, protocol, schema, corpus and source snapshot hashes were frozen before scoring in [provenance.json](provenance.json). A private local source snapshot preserves the complete selected tracked tree and reviewer surface; concurrent documentation changes cannot change arm provenance.

The original v19 schema does not include the current `#8c` output ID. The first admission correctly stopped before any model call. V22 registers a separate strict schema with exactly the current output legend, shared by every arm; historical protocols and schemas remain unchanged. The final harness also adds the v22-only exhausted authentication/capacity stop. Both successful three-call admission attempts are retained under [admission/](admission/). These calls are unscored and excluded from the 540-call matrix. Their `INCONCLUSIVE` report status is expected for a one-case, one-repetition diagnostic and is not a cohort verdict.

## Gates and interpretation

All three arms receive the same pattern ID/title/severity output legend and strict schema. The full profile embeds the registered skill and semantic review references, catalog-only embeds the pattern reference, and no-skill embeds no skill instructions.

All v19 per-report and arm-comparison thresholds are retained. The full arm must pass its absolute precision, recall, specificity and related gates. Full minus no-skill stable F1 must be at least 0.30 and its paired bootstrap 95% lower bound must exceed zero. Full minus catalog-only remains descriptive. All calls must be execution complete, with strict JSON/schema parsing, source and staged-skill pre/post hashes, the same frozen inputs, and sequential nonoverlapping arm times. The comparator reparses and rescores raw model answers. Reports preserve each final answer JSON and extracted usage. Original CLI JSON event streams are consumed in memory and are not retained; the stored answers cannot independently establish per-call tool counts. The declared `model_tool_surface: none` is bound to the frozen disabled-tool CLI arguments and a live parser that rejects every `item.*` type other than `agent_message` or `reasoning`, plus the admitted native calls. It is not a separately retained tool-count attestation.

This is previously observed public development evidence on one model. It does not establish a sealed or blind release evaluation, population accuracy, provider backend identity, or scanner causal benefit. The tool-free semantic comparison does not execute the production scanner or runtime probes. Its scientific verdict is separate from release readiness, installer checks and native workflow checks.

## Reproduction

Use an exact source snapshot whose reviewer and protocol bytes match the registered hashes. Bind the trusted Codex executable explicitly; do not change frozen historical protocols to fit a newer candidate.

```bash
for arm in full catalog-only no-skill; do
  python3 scripts/evals/run-reviewer-holdout.py \
    --cases scripts/evals/reviewer-holdout-v17.json \
    --protocol scripts/evals/reviewer-validation-protocol-v22.json \
    --runner codex --runner-path "$CODEX_RUNNER" --model gpt-6-sol \
    --arm "$arm" --repetitions 5 --timeout 180 --allow-live --report-only \
    --output "$OUT/$arm.json"
done
python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full.json" "$OUT/catalog-only.json" "$OUT/no-skill.json" \
  --cases scripts/evals/reviewer-holdout-v17.json \
  --protocol scripts/evals/reviewer-validation-protocol-v22.json \
  --compare-arms --output "$OUT/arm-comparison.json"
```

Runner exit codes are `PASS=0`, `FAIL=1`, `INCONCLUSIVE=2`. A complete control arm may fail the full skill's absolute thresholds; that alone does not invalidate its execution. Stop the matrix on an incomplete arm or a safety/integrity failure and preserve all original reports. The reproduction must enforce the registered 12-hour deadline; the comparator independently rejects a matrix outside it.

## External evidence package

The [revision-pinned Hugging Face package](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/tree/ba80292b2531ddac654134ba4aa319da1e3a2b3a/raw/reviewer-holdout-v22-v24-20261020) includes the unchanged v22–v24 original arm reports and comparisons, all 1,620 recorded final-answer payloads, frozen evaluated inputs, model-specific evaluators and offline replay. It preserves the v22 PASS, v23 FAIL and v24 PASS verdicts. Complete original CLI event streams were not retained.
