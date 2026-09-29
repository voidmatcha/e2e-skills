# Semantic mutants v1

This benchmark now contains 25 model-authored defects injected into real Payload, Storybook, and refine E2E specs. The original S1 corpus remains under `cases/`, `corpus.json`, and `scores/`. The linked S2 and S3 records are under `batches/s2/` and `batches/s3/`; each publishes its own mutant/original pairs, corpus ledger, per-sample scores, and aggregate summary. Every corpus ledger records the edit, pattern, severity, target line, quoted reviewer rule, and independent `codex-gpt-6-astra` verifier verdict.

The accepted cases cover #1, #2, #20, #22, and #23. S1 contains ten #1/#2 cases. S2 adds four Payload #23 fixture cases and five refine #20 uncontrolled-write cases. The #20 mutations were reworked to call `req.continue()` after the verifier rejected handler-less observer intercepts, which did not bypass the existing stubs. S3 adds six refine #22 cases whose remaining redirect assertions can pass before the optimistic write completes. All 15 S2/S3 labels were independently confirmed. Upstream MIT license copies are in `licenses/`; the Payload copy matches the copy used by `fixpair-v1`, and the refine copy comes from the evaluated checkout.

## Result

These recorded model-review results used the reviewer skill before the 2.0.0 scanner fixes (`976c3fa`); they were not recomputed after the standalone scanner changed.

| Arm | Strict recall | Lenient recall (±2 lines) | AFTER false alarms | Mean input tokens per sample |
|---|---:|---:|---:|---:|
| skill | **7/10** | **7/10** | **1/10** | 558,224 |
| no-skill | **5/10** | **7/10** | **1/10** | 138,078 |

The strict advantage is **+20 percentage points**; the lenient advantage is **0**. This is small compared with the mechanical fixpair batches. Each arm ran once per sample on one Codex `gpt-6-sol` host: ten mutant BEFORE samples and ten original AFTER controls. `scores/samples.json` records each local Inspect score; `scores/summary.json` records the aggregate. Input-token means come from the Inspect logs. The mutant labels are ground truth by construction in real code, which is weaker evidence than naturally occurring upstream fixes. There is no human adjudication or cross-host replication. These results describe this narrow corpus, not broad reviewer accuracy.

The original candidate manifest and independent verification came from the local `fixpair-pilot/semantic-v1` run. Scores were extracted offline from `runs-live-s-skill` and `runs-live-s-no-skill` Inspect logs, filtered to batch `S`. The verifier's quoted rules and explanations are preserved in `corpus.json`; raw model transcripts are not included in this benchmark. Run `python3 scripts/ci/test-semantic-mutants-v1.py` to check the published files and score arithmetic without Inspect or model access.

## S2: fixture guards and uncontrolled writes

| Model | Arm | Strict recall | Lenient recall (±2 lines) | AFTER false alarms | Mean input tokens per sample |
|---|---|---:|---:|---:|---:|
| `gpt-6-sol` | skill | **8/9** | **8/9** | **0/9** | 520,121 |
| `gpt-6-sol` | no-skill | **2/9** | **7/9** | **0/9** | 134,502 |
| `claude-sonnet-5-5` | skill | **3/9** | **4/9** | **0/9** | 379,907 |
| `claude-sonnet-5-5` | no-skill | **4/9** | **7/9** | **2/9** | 41,120 |

The skill found all five #20 cases and three of four #23 cases at the exact line. The no-skill arm found two of four #23 cases exactly and none of the five #20 cases exactly; all five #20 findings landed one or two lines from the write action, so its lenient score rises to 7/9. Both arms had zero false alarms on the nine original controls. Each arm ran once per sample on one Codex `gpt-6-sol` host.

On the same S2 cases, `claude-sonnet-5-5` scored **3/9 versus 4/9** strict, **4/9 versus 7/9** lenient, and **0/9 versus 2/9** original-control alarms (skill versus no skill). Input tokens were **6,838,330 versus 740,151** across 18 side samples per arm (means **379,907 versus 41,120**). See the [per-sample Inspect score ledger](batches/s2/scores/sonnet-5-5-samples.json).

## S3: optimistic write verification

| Model | Arm | Strict recall | Lenient recall (±2 lines) | AFTER false alarms | Mean input tokens per sample |
|---|---|---:|---:|---:|---:|
| `gpt-6-sol` | skill | **5/6** | **5/6** | **0/6** | 680,516 |
| `gpt-6-sol` | no-skill | **2/6** | **3/6** | **2/6** | 136,169 |
| `claude-sonnet-5-5` | skill | **5/6** | **5/6** | **0/6** | 424,916 |
| `claude-sonnet-5-5` | no-skill | **3/6** | **4/6** | **2/6** | 48,928 |

The skill found five of six #22 cases exactly and produced no false alarms. The no-skill arm found two exactly, one more within two lines, and flagged two of six original controls. Each arm ran once per sample on one Codex `gpt-6-sol` host.

On the same S3 cases, `claude-sonnet-5-5` scored **5/6 versus 3/6** strict, **5/6 versus 4/6** lenient, and **0/6 versus 2/6** original-control alarms. Input tokens were **5,098,989 versus 587,133** across 12 side samples per arm (means **424,916 versus 48,928**). See the [per-sample Inspect score ledger](batches/s3/scores/sonnet-5-5-samples.json).

Across S2 and S3, strict recall was 13/15 with the skill and 4/15 without it; lenient recall was 13/15 and 10/15, and false alarms were 0/15 and 2/15. For Sonnet 5.5 across S2+S3, strict recall was **8/15 versus 7/15**, lenient recall **9/15 versus 11/15**, and original-control alarms **0/15 versus 4/15**. Each model/arm ran once per sample; the Sonnet skill arm used the 2.0.0 skill, while the earlier Sol runs used an earlier revision. These batches remain model-injected defects in real code rather than naturally occurring fixes. Every #20 case comes from one repository, refine, and #12 is not covered. There is no human adjudication or cross-host replication, so the results describe these narrow batches rather than broad reviewer accuracy.

S2 scores were extracted offline from `runs-live-s2-skill` and `runs-live-s2-no-skill`; S3 scores came from `runs-live-s3-skill` and `runs-live-s3-no-skill`. The published ledgers preserve the exact Inspect scores and input-token counts, while the corpus records preserve the verifier's quoted rules and explanations. Raw model transcripts are not included.
