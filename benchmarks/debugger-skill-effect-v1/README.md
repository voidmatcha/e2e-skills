# Debugger skill-effect v1 (2026-10-04)

Status: **`PASS` on both hosts under the preregistered rule; public development evidence, not a release benchmark.** Claude `claude-sonnet-5-5`: F-code accuracy 0.944 with the debugger skill text versus 0.756 with the F-code legend alone, paired lift **+0.189** (95% CI +0.078 to +0.311). Codex `gpt-6-sol`: 1.000 versus 0.800, lift **+0.200** (+0.078 to +0.333). All 360 scheduled calls scored with zero infrastructure errors, zero retries, and zero invalid predictions. On each host the skill arm was better on 8 of 30 cases and worse on none.

This is the first live measurement of either debugger skill. A follow-up on real upstream fixes with a taxonomy-free baseline, [debugger skill-effect v2](../debugger-skill-effect-v2/README.md), found no lift and is recorded separately; neither result revises the other. [`debugger-holdout-v1`](../../docs/debugger-benchmark/README.md) has never run: its protocol pins retired CLI builds and a retired model and has no no-skill arm, so it cannot answer whether the skill text helps. This benchmark answers that one question for the model-visible skill text, on fresh cases.

## Question and arms

Does a zero-tool model classify an already-observed Playwright or Cypress failure into F1–F15 more accurately when it receives the debugger skill text than when it receives only the F-code legend?

| Arm | Prompt material |
| --- | --- |
| `skill` | the same model-visible surface `run-debugger-holdout.py` embeds: `SKILL.md`, `references/report-acquisition.md`, `references/artifact-extraction.md`, `references/classification-procedure.md`, `references/fix-verification.md` for the case's framework (about 43 KB for Playwright, 46 KB for Cypress) |
| `no-skill` | a 15-line legend (`F1: Flaky / Timing` … `F15: Hydration Race`) parsed from the same `SKILL.md`, so exact scoring stays possible. This is a legend-only baseline, not a taxonomy-free one. |

Both arms get the same prompt frame, the same excerpt, and the same enforced JSON schema (seven fields; `--json-schema` on Claude, `--output-schema` on Codex). Every call is prompt-complete with every model tool disabled, no user settings, no session persistence, and the shared holdout runner's strict environment allowlist and credential staging.

## Corpus and labels

Thirty fresh author-written cases, one per F-code for Playwright and one for Cypress, in domains not used by `debugger-holdout-v1`. Each is a short sanitized excerpt (error, attempts, network, DOM, spec or fixture lines, timeline) and carries one planted lookalike: the F14 and F15 cases pass on retry like F1; the F7, F9, F10 and F12 errors read like F2 or F4; the F11 Cypress case reads like F3. Labels for `f_code` and `diagnosis` were written by the author, who is a Claude model, and then checked by two blind labelers (Claude Sonnet and Claude Opus in fresh contexts) that saw only the two debugger F-code tables, both `classification-procedure.md` files, and the unlabeled packet under neutral item names. Both matched **30/30** F-codes and **30/30** diagnoses ([`blind-labels/`](blind-labels/)). No human labeled the corpus. The other four output fields use `debugger-holdout-v1`'s conventions and are recorded but not scored.

## Protocol

[`protocol.json`](protocol.json) was frozen before the first scored call. It pins the SHA-256 of `corpus.json`, every artifact, the ten skill files, both legends, the prompt frame, and the output schema; the runner refuses to start on drift and re-digests after the run. Three repetitions per case and arm, one seeded shuffle of all 180 cells per host, timeout 180 s, one retry for infrastructure failure only (non-zero exit, timeout, malformed envelope). Decision rule: `PASS` when the paired per-case lift is at least +0.10, the framework-stratified case-cluster bootstrap 95% CI lower bound is above 0, and skill diagnosis accuracy is no more than 0.05 below no-skill; `FAIL` when all calls scored and that is not met; `INCONCLUSIVE` on any unscoreable call or digest drift. Three unscored pipeline checks (two Sonnet calls on `pw-f7`, one Codex call on `cy-f11`) ran before the freeze and are not counted.

Power was stated before running: with no pilot variance and an assumed paired SD of 0.35, 30 cases detect about 0.18 at alpha 0.05 and power 0.8, so a true +0.10 could have been missed. The observed lifts exceeded that.

## Results

| Host | Calls scored | F-code acc. skill | F-code acc. no-skill | Paired lift (95% CI) | Cases better / worse / tied | Diagnosis acc. skill / no-skill | Stable F-code acc. skill / no-skill | Decision |
| --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |
| Claude `claude-sonnet-5-5`, Claude Code 2.1.289 | 180/180 | 0.944 | 0.756 | +0.189 (+0.078, +0.311) | 8 / 0 / 22 | 0.922 / 0.878 | 0.933 / 0.767 | `PASS` |
| Codex `gpt-6-sol`, codex-cli 0.159.3 | 180/180 | 1.000 | 0.800 | +0.200 (+0.078, +0.333) | 8 / 0 / 22 | 0.911 / 0.900 | 1.000 / 0.800 | `PASS` |

Per framework (F-code accuracy, skill versus no-skill): Sonnet Playwright 0.956 / 0.844, Cypress 0.933 / 0.667; Sol Playwright 1.000 / 0.822, Cypress 1.000 / 0.778.

### Cost

| Host | Total input tokens skill / no-skill (cache reads and writes included) | Ratio | Output tokens skill / no-skill | Summed call time skill / no-skill |
| --- | --- | ---: | --- | --- |
| Sonnet | 2,362,244 / 365,314 | 6.47× | 39,356 / 32,708 | 928.6 s / 839.2 s |
| Sol | 2,761,492 / 1,911,699 | 1.44× | 18,175 / 19,571 | 2,204.5 s / 2,201.9 s |

The skill arm sends about 9,000 (Codex tokenizer) to 15,000 (Claude tokenizer) more prompt tokens per call. On Codex the fixed system prompt dominates both arms, so the ratio is small; on Claude the ratio reflects the prompt itself. Token totals are not billing ratios and were measured with four (Claude) or three (Codex) concurrent calls.

### Where the skill text changed the answer

| Case | Expected | Lookalike | Sonnet skill | Sonnet no-skill | Sol skill | Sol no-skill |
| --- | --- | --- | --- | --- | --- | --- |
| `pw-f1` | F1 | F14 | F3/F1/F3 | F3/F3/F3 | F1/F1/F1 | F3/F3/F1 |
| `pw-f5` | F5 | F4 | F5/F5/F5 | F4/F4/F4 | F5/F5/F5 | F4/F4/F4 |
| `pw-f6` | F6 | F2 | F6/F6/F6 | F9/F6/F6 | F6/F6/F6 | F9/F6/F9 |
| `pw-f8` | F8 | F2 | F8/F8/F8 | F8/F8/F8 | F8/F8/F8 | F8/F6/F8 |
| `cy-f1` | F1 | F14 | F1/F1/F1 | F3/F3/F3 | F1/F1/F1 | F1/F1/F1 |
| `cy-f3` | F3 | F11 | F3/F3/F3 | F8/F8/F8 | F3/F3/F3 | F3/F3/F3 |
| `cy-f4` | F4 | F5 | F4/F4/F4 | F4/F8/F8 | F4/F4/F4 | F4/F4/F4 |
| `cy-f5` | F5 | F4 | F4/F4/F4 | F4/F4/F4 | F5/F5/F5 | F4/F4/F4 |
| `cy-f6` | F6 | F2 | F6/F6/F6 | F9/F6/F6 | F6/F6/F6 | F9/F9/F9 |
| `cy-f7` | F7 | F4 | F7/F7/F7 | F7/F7/F7 | F7/F7/F7 | F10/F7/F7 |
| `cy-f14` | F14 | F1 | F14/F14/F14 | F1/F1/F1 | F14/F14/F14 | F1/F1/F1 |

The other 19 cases were correct in every repetition of every arm on both hosts; the full per-case rows are in the `*-results.json` files. The legend-only arm most often collapsed F5 (action accepted, state never changed) into F4, F6 (unconditional assertion on an optional element) into F9, and the transient-toast F14 into F1. Those are exactly the distinctions the skill's signals column and `classification-procedure.md` spell out.

### Boundary cases and a sensitivity check

The skill arm's only misses were on Sonnet: `pw-f1` twice as F3 and `cy-f5` three times as F4. Both F1 excerpts contain a slow but successful API response, and both F5 excerpts contain a 200 response whose state never persisted, so each sits on an F1/F3 or F4/F5 boundary. The labels follow the contract as written and both blind labelers agreed with them, but the excerpts are not unambiguous. Excluding all four F1 and F5 cases, the lift is +0.128 (95% CI +0.038 to +0.244) on Sonnet and +0.128 (+0.026 to +0.244) on Sol, with skill accuracy 1.000 on both; the conclusion does not depend on those cases. This check was computed after the run and is reported as sensitivity, not as a revised score.

## What this does and does not support

It supports: on fresh public cases, the model-visible debugger skill text raises F-code classification accuracy over a legend-only prompt on both a Claude and a Codex host, with a paired case-bootstrap interval that excludes zero, and without lowering product-versus-test diagnosis accuracy. The F1–F15 table's signals and the classification procedure are doing measurable work.

It does not support: production debugger accuracy or a release claim. The corpus is public and model-authored, the labels are model-checked rather than human-adjudicated, each excerpt is a short sanitized reconstruction with one planted lookalike, and the no-skill arm already knew the fifteen category names. A zero-tool prompt measures interpretation of the skill text, not the end-to-end workflow (artifact reader, isolation probes, config checks, fix verification). Two hosts, three repetitions, and 30 cases do not estimate variance across models, versions, or real reports. Runner and model strings are provenance, not attestation. Nothing in the skills was changed in response to this run.

## Reproduce

```bash
python3 scripts/evals/run-debugger-skill-effect.py run \
  --runner claude --model sonnet --runner-path /absolute/path/to/claude \
  --output /absolute/path/claude.json --allow-live
python3 scripts/evals/run-debugger-skill-effect.py run \
  --runner codex --model gpt-6-sol --runner-path /absolute/path/to/codex \
  --output /absolute/path/codex.json --allow-live
python3 scripts/evals/run-debugger-skill-effect.py analyze /absolute/path/claude.json \
  --output /absolute/path/claude-results.json
```

The runner refuses to overwrite an existing report and refuses to start if any frozen digest differs. Source commit of the measured skills: `ed9489c` (release 2.0.0 skill text for both debuggers). After both runs, three static-typing findings in the runner were fixed (a `None` guard on module loading, an unused parameter, and a retry loop restructured so the result variable is always bound). The protocol's `max_attempts` is 2, every one of the 360 recorded runs has exactly one attempt, and re-deriving both `*-results.json` files with the fixed script reproduces them byte for byte, so no recorded call or score was affected and no rerun was needed. Account names in the archived report paths were replaced with the repository's `/Users/user/` placeholder after the run; the results files re-derive identically from the normalized reports.

## Files

- [`protocol.json`](protocol.json): preregistration, decision rule, frozen digests.
- [`corpus.json`](corpus.json) and [`cases/`](cases/): the 30 excerpts and labels.
- [`blind-labels/`](blind-labels/): labeler instructions, both blind label sets, item-to-case mapping.
- [`reports/claude-sonnet.json`](reports/claude-sonnet.json), [`reports/codex-gpt-6-sol.json`](reports/codex-gpt-6-sol.json): every call with prompt digests, raw output, usage, and timing.
- [`reports/claude-sonnet-results.json`](reports/claude-sonnet-results.json), [`reports/codex-gpt-6-sol-results.json`](reports/codex-gpt-6-sol-results.json): derived metrics, per-case rows, confusion, decision.

## Freeze evidence note (added after review)

The `registered_utc` field in `protocol.json` is not reliable: it was typed by hand and does not match the real first scored call (it is later than that call, and for v2 and v3 later than the actual clock time). `protocol.json` is frozen, so it is left as is. The freeze is established only by the pinned SHA-256 digests (`frozen_digests` equal the `input_digests_before` recorded in every report) and by file modification times; no git commit predates the first call.
