# Scrubbed finished harness-check fixture

This pair is a trimmed copy of the finished 2026-10-14 Codex gpt-6-sol harness check. The root rollout ends in `0004-7850-ad51-cf590beb1b25`; the child ends in `1736-7832-95e8-ad217ed80a42`. The root contains one `response_item` function call named `spawn_agent` in namespace `collaboration`, its matching output containing only `task_name`, and a separate `wait_agent` call/output. The child preserves its parent relationship, the inherited second session metadata record, communication metadata, a completed `playwright-test.test_list` call, and numeric usage records. The stream preserves only thread/turn lifecycle and usage: it contains zero spawns.

The fixture removes prompts, messages, reasoning, encrypted payloads, configuration, working directories and all home paths. Spawn arguments retain only `task_name`; wait arguments retain only `timeout_ms`. Wait output narration and MCP result text are removed; the latter retains a structured success envelope. Timestamps, ordinals, call IDs, thread IDs, parent relationships and numeric usage are retained. There is no model invocation or freeze in this fixture.

The pending [repair patch](../../repairs/root-rollout-spawns.patch) adds regression tests for this pair, a blind stream, a second completed root call with only one child rollout, a request without output, a child without any root spawn, stale stream identities, and stream fallback when the root is absent. The [offline verification script](../../repairs/check-root-rollout-spawns.py) loads the candidate patch in memory, so the existing frozen runtime files stay unchanged:

```bash
python3 -B benchmarks/generator-multimodel-v2-codex/repairs/check-root-rollout-spawns.py
python3 -B benchmarks/generator-multimodel-v2-codex/repairs/check-root-rollout-spawns.py --tests
python3 -B benchmarks/generator-multimodel-v2-codex/repairs/check-root-rollout-spawns.py --stored
```

The last command reads the finished persisted harness directory and prints the recalculated check, fidelity completeness and cost completeness. It never rewrites the stored result. A successful candidate replay does not mean that the frozen runtime was repaired or that the recorded frozen campaign result has changed. Applying the patch requires resolution of the owner's prohibition on changing freeze-bound files.

License: Apache-2.0, matching the repository.
