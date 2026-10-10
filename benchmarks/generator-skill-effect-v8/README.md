# Generator skill-effect v8: browser-capable Codex container

Status: **PASS under the frozen development rule**. All 216 scheduled calls were delivered and scored, and the digest-bound comparison passed. On 36 paired public tasks, markup-refactor survival was **0.9537 with full-fixed versus 0.4352 without the skill**: paired lift **+0.5185**, case-cluster bootstrap 95% CI **+0.3981 to +0.6296**. The skill arm improved 28 tasks, tied 8, and worsened none on this primary metric. This is not an independent release benchmark, a fault-detection lift, or proof that every completion procedure was followed correctly.

The separate Codex-driven setup preflight ran the existing smoke test three times; its command event recorded exit 0 and `3 passed`. Setup evidence is not primary task data. The model run finished on 2026-10-08 and sequential host scoring finished at 06:46 UTC. [The archived results](reports/results.json), [model report](reports/final.json), [scores](reports/scores.json), and delivered files under `reports/final-artifacts/` preserve the measured inputs and outcomes. Re-running `analyze` on the archived files reproduces `PASS` without model or browser calls.

[v7](../generator-skill-effect-v7/README.md) generated one spec but could not launch Chromium inside the macOS tool sandbox. Its partial results and all earlier setup failures are preserved, not counted as v8 data. This successor runs Codex CLI 0.159.3 with `gpt-5.5`, medium reasoning, inside an immutable Linux Docker image. A non-root, read-only-root container browser probe returned `Browser ready` with exit 0; this is a setup check, not primary evidence.

[protocol.json](protocol.json) keeps all 36 validated v3 tasks, exact full-fixed generator/shared reviewer snapshots, the task prompt, shuffled 216-cell schedule and decision thresholds. Two arms receive three fresh repetitions, one worker, 1,500-second timeout and separate sequential host scoring. Markup-refactor survival is primary, guarded by clean pass and effective fault kill. The inferential unit is 36 paired tasks; repeated calls are not independent defects.

Each attempt gets a disposable non-root Docker container with all capabilities dropped, a read-only root filesystem, a private temporary home and default seccomp. Only disposable task work and a read-only private auth/schema staging directory are mounted. No privileged mode, Docker socket, host network, published ports or host home/repository mount is used. Browser and app share the container-local loopback network. Codex's tool sandbox is `danger-full-access` **inside this external container boundary**, not on the host. This follows [official guidance for isolated runners](https://learn.chatgpt.com/docs/developer-commands#codex-exec).

The exact image ID is fixed before calls and used for both version probing and execution; the Docker client, context and image are recorded. Freeze binds Dockerfile, adapter, shared event/parser/auth helpers, fixture package/lock, validated source inputs and schedule. Dependency packages use the frozen fixture lock and Codex package 0.159.3; the image freezes their installed bytes. The default macOS scorer still evaluates generated artifacts with the validated v3 engine. A Linux-vs-macOS or host causal comparison is not claimed.

Codex token usage is recorded; billed USD, price estimate and dollar cost multiple remain null. Claude's $50.76 estimate and $4 budget do not apply. Account limits can still stop execution. Infrastructure failures stop after the inherited one retry. A 4 GiB disk safety floor is checked before each call; a breach preserves the partial report without deleting evidence. Incomplete, drifted, duplicated, unexpected or unscored matrices cannot pass. Full transcripts are retained outside the checkout; tool counters do not prove independent review or V4/V6 correctness without a separate audit.

```bash
python3 scripts/evals/run-generator-skill-effect-v8.py plan
python3 scripts/evals/run-generator-skill-effect-v8.py freeze
python3 scripts/evals/run-generator-skill-effect-v8.py run --allow-live --output /absolute/cache/v8/final.json
python3 scripts/evals/run-generator-skill-effect-v8.py score /absolute/cache/v8/final.json --output /absolute/cache/v8/scores.json
python3 scripts/evals/run-generator-skill-effect-v8.py analyze /absolute/cache/v8/scores.json --output /absolute/cache/v8/results.json
```

## Results and interpretation

| Measure | full-fixed | no-skill |
| --- | ---: | ---: |
| Calls delivered and scored | 108/108 | 108/108 |
| Clean app, all three scoring runs pass | 1.0000 | 0.9722 |
| Markup-refactor survival, primary | 0.9537 | 0.4352 |
| Effective fault kill, guard | 0.9389 | 0.9222 |
| Scanner P0 / P1-P2 findings | 0 / 0 | 0 / 5 |
| Flaky scoring calls | 0 | 2 |
| Summed recorded generation time | 30,717.5 s | 4,556.2 s |
| Recorded input tokens, including cached input | 240,102,951 | 7,976,866 |
| Recorded cached input tokens | 228,268,544 | 6,808,576 |
| Recorded output tokens | 1,159,106 | 247,797 |

The clean-pass and effective-fault-kill guards passed. The effective-fault-kill difference was +0.0167, 95% CI -0.0167 to +0.0519: this does not establish an improvement in fault detection. The primary gain is survival of the prescribed markup refactor while keeping clean runs and fault detection within the frozen guards. The historical floor/middle/ceiling summaries in the result are descriptive only.

Recorded generation time was 6.74 times the baseline. Approximately 95.1% of skilled input tokens were cached; input counts include repeated context, and neither raw tokens nor elapsed time establish a billed-dollar multiple. Child usage completeness and actual subscription billing are not independently established. One skilled call had an incomplete-transcript infrastructure attempt and succeeded on the single permitted retry: 217 attempts for 216 completed cells. Final records have zero unresolved infrastructure errors and zero timeouts. The elapsed-time and usage aggregates above are the frozen analyzer's per-call records, not an independently reconciled accounting of every failed attempt and child.

## Post-hoc execution audit

[The parent-event audit](reports/transcript-audit.json) is separate from the frozen primary analysis. It includes all 217 attempts, hashes each sanitized transcript, and counts only completed nonzero commands whose output matches a stated error. Full sanitized transcripts remain outside the public archive; the hashes support local verification, not independently replayable public transcript evidence.

| Observed skilled-arm events | Events | Calls affected |
| --- | ---: | ---: |
| Preflight connection failure, curl exit 7 | 108 | 107/108 |
| Default Chrome distribution not installed | 110 | 95/108 |
| Port already in use | 57 | 50/108 |
| Native agent spawn completion | 152 | 108/108 |

The no-skill arm recorded none of these events. Repeated preflight, browser-selection and server-ownership failures are candidates for reducing execution friction in a new protocol; their causal time savings have not been measured. Two sanitized JSONL lines were invalid and were counted and skipped, not repaired. Native spawn events do not prove an independent review was correct or that V4/V6 completion criteria were satisfied. The frozen result's zero read/spawn aggregates are unsupported/null indicator aggregation, not evidence that files were unread or no child ran. The original report, scorer, adapter and aggregates remain unchanged.

Reproduce the post-hoc audit against retained transcripts with:

```bash
python3 scripts/evals/audit-generator-codex-transcripts.py \
  benchmarks/generator-skill-effect-v8/reports/final.json \
  /absolute/cache/v8/final-transcripts --output /absolute/cache/new-audit.json
```

This is an environment-driven successor on a spent public development pool, not an independent sealed release evaluation. It does not isolate the earlier generator fixes, identify which workflow step caused the quality gain, or justify skill simplification. Repairs to the environment, process-event accounting, or loading policy require a new version and unchanged quality guards; do not modify this protocol or retrofit the archived evidence.
