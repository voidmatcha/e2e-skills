# Full skill plus scanner real-fix probe v1 — incomplete

This preregistered development probe adds bundled scanner evidence to the exact full-skill prompts already measured in [the five-case cross-model probe](../real-fix-cross-model-v1/README.md), comparing against historical catalog-only and full zero-tool calls. It asks whether scanner candidates change strict target detection for Codex `gpt-6-sol`, Codex `gpt-6-astra`, and Claude Code `claude-sonnet-5`. [protocol.json](protocol.json) fixed the cases, control-report hashes, source/prompt/schema identity checks, scanner tree and ast-grep hashes, model/CLI identities, schedule, and stop policy before calls. The attempted 30-call matrix stopped at 22 calls; [results.json](results.json) is explicitly `INCOMPLETE`.

The experiment has 5 repair clusters × BEFORE/AFTER × 3 models = 30 new calls. Existing full zero-tool and catalog-only calls are historical matched controls: their source packets, numbered lines, prompts, enforced JSON schema, and score function must match exactly. The only addition to the full-skill prompt is a fixed evidence-boundary paragraph plus complete scanner output. Historical controls leave a temporal/provider-state confound; this design cannot isolate a stable causal model effect. DataGrok stays excluded because its base `#4` answer is unavailable in the unchanged output schema. No scanner-plus-catalog secondary arm is scheduled.

The runner executes the pinned bundled scanner once on each of the ten named spec roots before any model call. Tier 1 and downloads are disabled. Tier 2 uses the explicitly supplied, digest-pinned external ast-grep binary; Tier 3 uses the bundled checks. No target-controlled package scripts, binaries, plugins, or configs execute. An incomplete scan, missing tier, source mutation, or identity mismatch stops preparation without narrowing scope or raising limits. All ten normalized packet hashes were fixed after scanner-only preparation and before any model call; live execution must reproduce every hash before its first call. Scanner signals remain candidates: an added instruction requires semantic confirmation and independent catalog review even when the scan has zero hits.

Exact stdout/stderr, augmented prompts, raw answers, source identities, usage, and timing remain in a user-chosen local cache outside the repository. The model-visible packet replaces only the random temporary workspace prefix with `.`; both exact and normalized hashes are recorded. Scanner time is recorded once per source packet, separately from model call time. Model tools remain disabled through the existing holdout runner. No raw local home paths or transcripts belong in the public result summary.

## Prepare without model calls

Use the three original local reports identified by SHA-256 in the protocol. The exact ast-grep build is platform-specific; an unavailable or different binary fails closed rather than silently changing tiers.

```bash
python3 scripts/evals/run-real-fix-scanner-inclusive-v1.py \
  --sol-report /path/to/cache/real-fix-probe-v1/report.json \
  --astra-report /path/to/cache/real-fix-cross-model-v1/astra.json \
  --claude-report /path/to/cache/real-fix-cross-model-v1/claude.json \
  --ast-grep /absolute/path/to/ast-grep \
  --output-dir /path/to/cache/real-fix-scanner-inclusive-v1/plan \
  --plan-only
```

`--plan-only` fetches the same pinned public source snapshots and runs ten scanners, verifies all 30 full and 30 catalog prompt identities, writes local evidence, and makes no model calls. `--check-contracts` performs dependency, schema, and scanner-tree checks without source fetches or scanner/model execution. Every output directory must be new. Preparation and live execution both require the protocol to match its digest frozen at process startup.

The live attempt used a new output directory, omitted `--plan-only`, and supplied `--allow-live --codex /absolute/path/to/codex --claude /absolute/path/to/claude`. Exact CLI versions matched the historical controls. Hosts ran sequentially in the protocol's order; the first timeout stopped the matrix without retry or imputation. The local raw report and scanner packets are SHA-pinned in `results.json` but are not checked into this repository.

## Observed outcome

All ten pinned scanner packets reproduced with Tier 2+3, 39,578 normalized bytes, and 71.603 seconds summed scanner time. At the exact BEFORE target line and pattern, the scanner proposed Growi `#16` and Kibana `#4i`, but not OpenSearch `#4a`, Chronograf `#2`, or OneArmy `#10d`. The Chronograf target line was a `#10f` candidate instead; candidate presence is not semantic correctness. This 2/5 candidate coverage explains why the independent catalog review remains necessary even with the scanner.

The complete Sol and Astra host cohorts each have ten scored calls. Strict BEFORE target hits are Sol **3/5** with scanner versus historical full **5/5** and catalog-only **4/5**; scanner loses Chronograf and Kibana relative to full, with no gain. Astra is **4/5** in all three arms, with identical hit cases. Mapped same-pattern AFTER alarms remain zero in both complete cohorts. Sol used 598,240 input tokens and 519.516 summed model-call seconds versus historical full 585,783 and 415.2; Astra used 602,730 and 313.347 versus 590,262 and 297.5. Scanner time is additional. These are descriptions, not scanner-caused slowdowns: historical controls ran at another time, and repository CI ran concurrently with this attempt.

Claude completed Growi BEFORE/AFTER, then its OpenSearch BEFORE call exceeded the predeclared 300-second limit. The runner stopped at 22/30 calls. The two Claude calls are not a comparable host cohort, and missing calls were not rerun or filled in. The full three-model matrix therefore has **no PASS result**. Raising the timeout or reusing this partial run as a complete comparison would violate the frozen protocol.

The completed Sol/Astra cohorts produced five additional unique keys absent from the earlier [source adjudication](../real-fix-cross-model-v1/adjudication-results.json). [A supplemental ledger](adjudication-opensearch-new.json) finds three valid patterns, one false positive, and one invalid location; `scripts/evals/summarize-real-fix-scanner-inclusive-v1.py --allow-incomplete` recomputes complete-host-only counts and refuses to score Claude's partial cohort. Repeated predictions are correlated, not independent defects. The source judgments are not runtime reproduction or a population precision estimate.

The narrow reading is unfavorable to any claim that scanner inclusion improved strict target detection here: Sol declined and Astra tied, while input increased modestly. It does **not** establish that the scanner generally hurts review. The five selected public cases, single repetition, historical-control drift, concurrent CI, incomplete Claude cohort, and tool-disabled precomputed scanner packet prevent a general causal or full-product conclusion. No product rule was changed to chase this benchmark.
