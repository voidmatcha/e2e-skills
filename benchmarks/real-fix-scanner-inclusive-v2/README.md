# Full skill plus scanner real-fix rerun v2

This is a new, prospectively frozen 30-call attempt after [v1](../real-fix-scanner-inclusive-v1/README.md) stopped at 22/30 when Claude's third call exceeded its 300-second limit. V1 remains `INCOMPLETE`; no v1 model answer is reused. [protocol.json](protocol.json) fixes all five public repair clusters, ten source-side packets, three hosts, prompt and source identities, scanner output hashes, scoring, and stop policy before the first v2 model call. It increases only the model-call ceiling to 900 seconds and requires no concurrent repository CI; neither change is hidden or retroactively applied to v1.

The v2 runner imports the exact hash-pinned v1 runner, so scanner, prompts, JSON schema, source staging, model-tool restrictions, and scoring are unchanged. The 30 fresh calls run Sol, Astra, then Claude in the same case order. Any scanner/prompt/source mismatch or model failure stops the run without retry, replacement, timeout increase, or imputation. Source and prompt snapshots are checked against the historical full and catalog-only controls. Those controls were run earlier, so this remains a descriptive, temporally confounded public development comparison, not a causal or release-grade skill-lift test.

Raw reports, prompts, and scanner outputs stay outside the repository. The [public result](results.json) pins the completed raw report by SHA-256. All 30 calls completed without a retry, timeout, or schema failure; v1 remains independently `INCOMPLETE`.

## Observed outcome

All ten pinned Tier 2+3 scanner packets reproduced (39,578 normalized bytes; 65.147 seconds summed scanner time). At the exact BEFORE target line and pattern, scanner candidates covered only Growi and Kibana, two of five. The other cases still require semantic review independent of scanner output.

| Host | Scanner-inclusive strict BEFORE hits | Historical full | Historical catalog-only | Paired change versus full | Mapped AFTER alarms |
| --- | ---: | ---: | ---: | --- | ---: |
| Codex Sol | 4/5 | 5/5 | 4/5 | Lost OpenSearch | 0 |
| Codex Astra | 4/5 | 4/5 | 4/5 | No case change | 0 |
| Claude Sonnet 5 | 3/5 | 2/5 | 2/5 | Gained Kibana | 0 |

Relative to catalog-only, Sol gained Chronograf but lost OpenSearch (net zero); Astra had no case changes; Claude gained OneArmy and Kibana but lost Chronograf (net +1). This is not a consistent cross-host lift. The [five Sol-only](adjudication-sol-new.json) and [one Astra-only](adjudication-astra-new.json) new unique additional-finding keys were checked against frozen source: two confirmed, two false positives, and two invalid locations. No new Claude keys remained unadjudicated. Repeated additional predictions are correlated, not independent defects.

Within-host costs also vary. Sol used 598,220 input tokens and 475.042 summed model seconds versus historical full 585,783 and 415.2 (+2.12% input, +14.41% time). Astra used 602,711 and 270.710 versus 590,262 and 297.5 (+2.11% input, −9.01% time). Claude reported 799,487 cache-write, 123,867 cache-read, and 147,707 output tokens, with 1,555.588 summed model seconds; historical full reported 839,107, 468,043, 142,707, and 1,490.0 respectively. Claude's `input_tokens` excludes cache reads/writes, so no single comparable cross-host token total exists. Scanner time is additional, and historical timing differences cannot be attributed to the scanner alone.

The narrow conclusion is that this completed rerun does **not** show a robust scanner-induced gain: one host declined versus full, one tied, and one gained one case. It also does not prove the scanner is harmful. V1's Sol 3/5 versus v2's 4/5 under the same packets illustrates single-run variability. The five selected public clusters, one repetition, historical controls, v2's longer timeout and no concurrent CI, and precomputed scanner evidence with model tools disabled preclude a causal, population, or full-product claim. No product rule was changed to chase the result.

## Reproduce the checks

`scripts/evals/run-real-fix-scanner-inclusive-v2.py --check-contracts` verifies the frozen dependencies and protocol. A `--plan-only` run verifies source, prompts, schema, scanner tiers, and all ten packet hashes without model calls. The fresh live run used the same arguments as [v1](../real-fix-scanner-inclusive-v1/README.md), a new output directory, and `--allow-live`; its 30 calls used Codex `0.159.3`, Claude Code `2.1.289`, and ast-grep `0.45.3`. Use `scripts/evals/summarize-real-fix-scanner-inclusive-v2.py` with the three historical reports, this raw v2 report, and all six adjudication ledgers to recompute [results.json](results.json). The protocol and result SHA-256 values identify the exact local artifacts without publishing local paths or prompts.
