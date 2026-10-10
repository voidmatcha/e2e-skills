# Generator skill-effect v7: executable-bound Codex comparison

Status: **INCOMPLETE (browser sandbox)**. One full-fixed call returned a test deliverable and `partial_or_blocked`, without an infrastructure error or timeout, but Chromium could not launch under the macOS workspace-write sandbox (`MachPortRendezvousServer` permission denied). The next call was interrupted and the partial report/transcripts are retained outside the checkout. No scores or effect estimate exist. Continuing would confound skill behavior with a blocked browser, so this run was stopped. The route smoke checked model access, not browser execution.

An adapter-level routing smoke using the resolved CLI returned valid schema output with exit 0 (7.467 seconds); it is not task evidence. [v6](../generator-skill-effect-v6/README.md) was interrupted before any completed task because its recorded CLI and actual call executable differed. This successor uses the same resolved absolute executable for every call and its version record, records the launcher SHA256, and refuses resume on a changed launcher or version. No v6 tasks or scores enter this comparison.

[v5](../generator-skill-effect-v5/README.md) stopped because the account rejected its pinned model. A separate read-only `gpt-5.5` routing smoke returned `OK` (exit 0, 13.661 seconds); its tokens and answer are not task evidence. This successor preserves [v4](../generator-skill-effect-v4/README.md), whose Claude execution hit an account limit without producing tests. It reuses all 36 validated v3 tasks, the exact frozen full-fixed generator and shared reviewer snapshots, the same task prompt, two arms and three fresh repetitions (216 calls). The shuffled schedule and decision thresholds are unchanged; no Claude calls or prior scores enter this comparison.

[protocol.json](protocol.json) pins `codex`, `gpt-5.5`, medium reasoning, one worker, 1,500-second call timeout and separate sequential scoring. The primary is markup-refactor survival with clean-pass and effective fault-kill guards, using 36 paired task clusters rather than treating repeated calls as independent cases. This is a spent public development pool, not a sealed release holdout.

Codex runs with a private auth-only home, no ambient user configuration or installed skills, an ephemeral session, a workspace-write sandbox and the same flags in both arms. Only full-fixed receives the frozen skills. The adapter retains sanitized JSONL transcripts outside the checkout. Local-server access is needed for Playwright; sandbox behavior differs from Claude and is a disclosed host change. No sandbox bypass is used.

The Claude $50.76 estimate and $4 per-attempt budget do not apply to Codex. Codex CLI records token usage but not billed USD and has no equivalent dollar cap. USD metrics remain null rather than misleadingly reporting zero. Account usage limits may still stop execution. Infrastructure errors stop the run after the inherited single retry; interrupted or failed calls never become passing evidence.

```bash
python3 scripts/evals/run-generator-skill-effect-v7.py plan
python3 scripts/evals/run-generator-skill-effect-v7.py freeze
python3 scripts/evals/run-generator-skill-effect-v7.py run --allow-live --output /absolute/cache/v7/final.json
python3 scripts/evals/run-generator-skill-effect-v7.py score /absolute/cache/v7/final.json --output /absolute/cache/v7/scores.json
python3 scripts/evals/run-generator-skill-effect-v7.py analyze /absolute/cache/v7/scores.json --output /absolute/cache/v7/results.json
```

Freeze is create-only and binds protocol, runner, Codex adapter, auth helper, validated inputs and the exact schedule. Execution outputs must be outside the checkout. Final analysis refuses incomplete, duplicate, unexpected, drifted or unscored cells. Transcripts and tool counts are process indicators only: independent review, failure injection, restoration and V4/V6 completion remain UNVERIFIED without a separate audit. No skill simplification, fix attribution or causal host comparison follows from this two-arm experiment.

Codex flags follow [official CLI guidance](https://learn.chatgpt.com/docs/developer-commands#codex-exec); the installed CLI's help is checked before execution.
