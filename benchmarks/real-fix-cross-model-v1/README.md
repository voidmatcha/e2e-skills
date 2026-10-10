# Cross-model public real-fix probe v1

This is a read-only, zero-tool, single-repetition development comparison against [the Sol probe](../real-fix-probe-v1/README.md), not a sealed holdout. [protocol.json](protocol.json) freezes two additional model/host cells: Codex `gpt-6-astra` and Claude Code `claude-sonnet-5`. Each receives the exact same five scoreable case-side-arm prompts used for Sol, with prompt/source/skill/schema digests checked before every call. The original Sol call schedule is filtered only to exclude DataGrok, because its base `#4` answer was impossible under that frozen JSON schema. The excluded case is not relabeled or quietly scored as a miss.

Each host runs 5 repair clusters × BEFORE/AFTER × three arms = 30 fresh, independent calls. The `no-skill` arm still receives a shared output legend, so it is a legend-only baseline. The `full` arm embeds skill text but runs no scanner, browser, or subagents. Compare strict target detection and mapped AFTER alarms within each model first; cross-host token counts are descriptive because Codex and Claude account for cached input differently. Summed call time excludes source staging and analysis. Additional predictions were subsequently source-adjudicated; see below.

The runner writes a local-only report after each call and stops without retry or imputation on a bad cell. Invoke `python3 scripts/evals/run-real-fix-cross-model-probe.py --runner codex --model gpt-6-astra --runner-path /absolute/path/to/codex --sol-report /path/to/Sol/report.json --output /path/to/Astra/report.json` and similarly with `--runner claude --model claude-sonnet-5`. `--plan-only` checks source and prompt identity without model calls.

## Outcome

All 60 new model calls completed: 30 Codex `gpt-6-astra` and 30 Claude Code `claude-sonnet-5`. The historical Sol report contributes the exact same 30 scoreable prompts. [results.json](results.json) records the raw-report hashes, per-arm counts, usage, elapsed time, and unadjudicated findings.

| Model | Full target hits | Catalog-only | Legend-only | Mapped AFTER alarms |
| --- | ---: | ---: | ---: | ---: |
| Codex Sol | 5/5 | 4/5 | 1/5 | 0 across all arms |
| Codex Astra | 4/5 | 4/5 | 2/5 | 0 across all arms |
| Claude Sonnet 5 | 2/5 | 2/5 | 1/5 | 0 across all arms |

The full text adds one strict hit over the catalog on Sol (Chronograf), none on Astra, and none on Claude. Claude's catalog hit on Chronograf and full hit on OneArmy are *different cases*, so its tied 2/5 totals do not mean identical behavior. Astra misses Chronograf in all arms. Claude misses OpenSearch and Kibana in all arms. All counts require the exact source-adjudicated pattern and causal line on BEFORE, with each repair cluster counted once; the AFTER metric checks only a mapped same-pattern alarm, not every possible false positive.

Full versus legend-only reported input tokens and summed call time were Sol 585,783 versus 169,840 and 415.2 versus 290.5 seconds; Astra 590,262 versus 174,317 and 297.5 versus 200.9 seconds. Claude's `input_tokens` alone is misleading because it reports cache reads and writes separately: `input_tokens + cached_input_tokens + cache_write_tokens` was 1,307,180 versus 241,223, and summed call time was 1,490.0 versus 939.1 seconds. These are descriptive within-host overheads, not cross-host cost ratios. Claude's reported output tokens were also far larger than Codex's, and the hosts do not expose identical reasoning-token categories.

## Additional-finding adjudication

The 90 calls made 883 additional predictions beyond strict target findings and mapped AFTER alarms. These collapse to 326 unique `(case, side, file, line, pattern ID)` keys. Three source ledgers — [Growi/Kibana](adjudication-growi-kibana.json), [Chronograf](adjudication-chronograf.json), and [OpenSearch](adjudication-opensearch.json) — classify every key against pinned source and the applicable pattern contract. A deterministic 40-key adversarial cross-audit led to two Chronograf row corrections; all other sampled verdicts stood. [adjudication-results.json](adjudication-results.json) records the exact report and ledger hashes and per-model/arm counts; `scripts/evals/summarize-real-fix-adjudication.py` checks coverage and recomputes them.

Of the 326 unique keys, 139 are confirmed pattern findings, 94 are false positives, 80 cite a location that does not support the proposed pattern, and 13 still need context. Repeated predictions are correlated and must not be treated as 883 independent defects. The classification is for *additional* findings only; the strict target metric above is separate. It shows both useful non-target findings and substantial unsupported output, especially in the legend-only arm. It is not a population precision estimate: cases are public and selected, each model ran once, and the judgments remain source-level rather than runtime reproductions.

The narrow conclusion remains: instruction material helped strict target recall over the shared-legend baseline in this selected zero-tool set, but a longer full skill was not consistently better than its catalog across models. This probe does not establish scanner-inclusive product value, stable model effects, or a release-grade skill-lift claim. The one-repetition, public-case, host/effort differences and DataGrok schema exclusion are material limits.
