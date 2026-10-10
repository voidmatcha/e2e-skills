# Generator skill-effect v6: account-supported Codex comparison

Status: **INCOMPLETE (runner identity mismatch)**. Execution was interrupted during the first call, before any task completed: version capture selected Codex CLI 0.159.3 but the sanitized subprocess PATH selected CLI 0.149.0. The partial report and interrupted transcript are preserved outside the checkout. No scores or task data are reused. [v7](../generator-skill-effect-v7/README.md) uses one resolved executable for both version capture and every model call.

[v5](../generator-skill-effect-v5/README.md) stopped because the account rejected its pinned model. A separate read-only `gpt-5.5` routing smoke returned `OK` (exit 0, 13.661 seconds); its tokens and answer are not task evidence. This successor preserves [v4](../generator-skill-effect-v4/README.md), whose Claude execution hit an account limit without producing tests. It reuses all 36 validated v3 tasks, the exact frozen full-fixed generator and shared reviewer snapshots, the same task prompt, two arms and three fresh repetitions (216 calls). The shuffled schedule and decision thresholds are unchanged; no Claude calls or prior scores enter this comparison.

[protocol.json](protocol.json) pins `codex`, `gpt-5.5`, medium reasoning, one worker, 1,500-second call timeout and separate sequential scoring. The primary is markup-refactor survival with clean-pass and effective fault-kill guards, using 36 paired task clusters rather than treating repeated calls as independent cases. This is a spent public development pool, not a sealed release holdout.

Codex runs with a private auth-only home, no ambient user configuration or installed skills, an ephemeral session, a workspace-write sandbox and the same flags in both arms. Only full-fixed receives the frozen skills. The adapter retains sanitized JSONL transcripts outside the checkout. Local-server access is needed for Playwright; sandbox behavior differs from Claude and is a disclosed host change. No sandbox bypass is used.

The Claude $50.76 estimate and $4 per-attempt budget do not apply to Codex. Codex CLI records token usage but not billed USD and has no equivalent dollar cap. USD metrics remain null rather than misleadingly reporting zero. Account usage limits may still stop execution. Infrastructure errors stop the run after the inherited single retry; interrupted or failed calls never become passing evidence.

```bash
python3 scripts/evals/run-generator-skill-effect-v6.py plan
python3 scripts/evals/run-generator-skill-effect-v6.py freeze
python3 scripts/evals/run-generator-skill-effect-v6.py run --allow-live --output /absolute/cache/v6/final.json
python3 scripts/evals/run-generator-skill-effect-v6.py score /absolute/cache/v6/final.json --output /absolute/cache/v6/scores.json
python3 scripts/evals/run-generator-skill-effect-v6.py analyze /absolute/cache/v6/scores.json --output /absolute/cache/v6/results.json
```

Freeze is create-only and binds protocol, runner, Codex adapter, auth helper, validated inputs and the exact schedule. Execution outputs must be outside the checkout. Final analysis refuses incomplete, duplicate, unexpected, drifted or unscored cells. Transcripts and tool counts are process indicators only: independent review, failure injection, restoration and V4/V6 completion remain UNVERIFIED without a separate audit. No skill simplification, fix attribution or causal host comparison follows from this two-arm experiment.

Codex flags follow [official CLI guidance](https://learn.chatgpt.com/docs/developer-commands#codex-exec); the installed CLI's help is checked before execution.
