# Multi-model replication of the official-generator / official+reviewer / ours-2.0.1 pilots (preregistration)

Status: **PREREGISTERED, NOT RUN** when this file was committed to the working tree. Results, if any, are appended below the line marked `Results` after the run and never change anything above it.

The two earlier pilots ([generator-official-pilot-v1](../generator-official-pilot-v1/README.md), [generator-official-reviewer-pilot-v1](../generator-official-reviewer-pilot-v1/README.md)) used one host and one model: Codex CLI 0.159.3, `gpt-5.5`, medium effort. Their descriptive result was refactor survival 0.500 for the first-party Playwright generator (A), 0.917 for this repository's `playwright-test-generator` 2.0.1 (C), and one `e2e-reviewer` pass over A's own output (B) as a third condition. The question here is narrow: **does that pattern show up with other models, or was it a property of `gpt-5.5`?** A negative, mixed or not-evaluable outcome is an acceptable result. There is **no PASS/FAIL rule and no confidence interval**.

## Design

- **Same cells, many models.** For every model in the matrix: the same 6 synthetic tasks x 3 arms x 2 repetitions = 36 cells, same container image, plan files, seed, scanner, scoring engine, timeout (1500 s) and medium effort as the pilots. Models run **one after another and one call at a time**; the schedule is fixed by seed 20261016 (phase 1: the 24 A and C cells, phase 2: the 12 B cells).
- **Arms.** A = official generator (`init-agents`, native subagent plus the `playwright-test` MCP server; Playwright CLI exploration is allowed in every arm through the shared approvals). B = one `e2e-reviewer` review-and-fix pass over **the same model's own A deliverable** of the same task and repetition (so B is unavailable where A produced nothing). C = this repository's `playwright-test-generator` 2.0.1 skill. Skill and reviewer snapshots are the pilots' (tree-digested in `freeze.json`).
- **Transports.** Codex models: the pilots' Docker transport, unchanged. Claude models: `scripts/evals/generator_claude_multimodel_adapter.py`, Claude Code 2.1.299 on the host. Isolation is verified from the `system/init` event of **every** Claude call (installed skills list empty in every arm; `playwright-test-*` subagents and the MCP server visible only in arm A; no web tools; arm A's parent has no Write/Edit tools; B and C have them). A call that violates the contract is an infrastructure error, not data. Details and the full tool scope are in `protocol.json` (`transports.claude`).
- **Official arm for Claude.** `npx --no-install playwright init-agents --loop=claude` (four files digest-checked), then exactly one line of the shipped subagent definition changes (`model: sonnet` to `model: inherit`) because the shipped pin overrides `CLAUDE_CODE_SUBAGENT_MODEL` (observed in a pre-freeze preflight: a haiku parent got a sonnet subagent). Every Claude cell records `modelUsage`; cells naming another model are counted.

## Model matrix (confirmed locally on 2026-10-14)

Claude Code (`claude -p --model`): `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-fable-5-1`, `claude-haiku-5-5`, all answered. Codex CLI 0.159.3 (`codex exec --model`): `gpt-6-sol`, `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, all answered. Run order interleaves the families (see `protocol.json`).

Excluded, with reasons recorded in `protocol.json`: `gpt-5.5` (already measured in both pilots; shown as a reference row, never counted), `gpt-daybreak-blue-latest` (moving `-latest` alias, not reproducible), `gpt-reserve` and `codex-auto-review` (hidden in the local model cache, not general generation models).

## Engagement preflight (before the freeze, not data)

One arm A call per Codex model on task `v2-01`, which is outside the preregistered set: `gpt-5.5` (control) engaged and delivered; `gpt-5.6-sol` and `gpt-5.6-luna` delivered; `gpt-6-sol`, `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6-luna` and `gpt-5.6-terra` returned in 12 to 38 s with no spec file (the native subagent could not be driven with its browser and generator tools). The harness is unchanged from the pilots, so this is a model-by-loop compatibility result. The models stay in the matrix and the evaluability rule below keeps those cells from being read as a quality difference. Claude: haiku delivered in all three arms with the isolation check passing.

## Metrics (all per model and arm, from the unchanged v3 engine and v8 scanner)

Primary: markup-refactor survival (1 only if clean 3/3 and the refactor passes), mean over the 2 repetitions per task. Also reported: valid-defect detection (effective fault kill and raw kill rate), clean 3/3 rate, scanner P0 and P1/P2 totals, delivered/unavailable/timeout cells, wall-clock seconds, tokens (and `total_cost_usd` for Claude), flaky clean runs, weakening text-probe hits, out-of-scope writes, for B the files the reviewer changed, for A the official-signature proxy (and the count of `generator_write_test` MCP calls for Claude), and an after-the-fact audit of home-directory paths touched outside the work directory. Tokens and seconds are not comparable across the two families.

## Decision rule (fixed before any scheduled call)

1. **Per model and contrast** (C vs A, B vs A, C vs B): evaluable only if both arms delivered a spec in at least 6 of their 12 cells. If evaluable, the label is `suggestive: X better` when X has the same refactor-survival sign in at least 5 of the 6 tasks and its clean 3/3 rate, effective fault kill, scanner P0 total and scanner P1/P2 total are not worse (the pilots' rule); otherwise `nothing`. Ties and 3-3 splits are `nothing`.
2. **Across models**, per contrast, with N = complete models for which it is evaluable: `replicated` only if N >= 4, at least ceil(2N/3) of them carry the same suggestive label, none carries the opposite one, and the agreeing models include a Claude-family and a Codex-family model. Otherwise `not replicated` (N >= 4) or `not evaluable` (N < 4). No "partly" verdict exists.
3. A model that stops before 36 cells are scored is incomplete: shown descriptively, excluded from N. `gpt-5.5` from the pilots is a reference row.
4. Descriptive only: no p-values. The pooled view never replaces the rule.

## Stop rules

One call at a time; load pause above 40; stop below 4 GiB free disk (resume with `drive --allow-live`, which resumes every model from its saved `final.json`); stop on usage limits or digest drift; an infrastructure-error cell is retried at most twice by later resumes, then stays recorded and scores 0, and three consecutive such cells stop the campaign. The protocol, runners, adapters and `freeze.json` are not edited after the first scheduled call.

## Commands

```bash
python3 scripts/evals/run-generator-multimodel-v1.py plan
python3 scripts/evals/run-generator-multimodel-v1.py freeze                # done before the first scheduled call
python3 scripts/evals/run-generator-multimodel-v1.py drive --allow-live    # all models in order: run, score, analyze each; resumable
python3 scripts/evals/run-generator-multimodel-v1.py status                # writes ~/.cache/e2e-skills-bench/multimodel-v1/STATUS.md
python3 scripts/evals/run-generator-multimodel-v1.py summary               # cross-model tables and the rule
python3 scripts/ci/test-generator-multimodel-v1.py                         # offline guards, no model call
```

Per-model evidence lives outside the checkout in `~/.cache/e2e-skills-bench/multimodel-v1/<model>/` (`final.json`, `scores.json`, `results.json`, artifacts, transcripts).

## Limitations

Six task clusters and two repetitions per arm and model: tiny and descriptive. The same synthetic fixtures and author-written faults as the pilots. Arm A's loop differs between the families (Claude subagent plus MCP with a parent that cannot write files, versus Codex native subagent with a parent that is only told not to write specs), and Claude runs on the host while Codex runs in a container: the family comparison is confounded and only within-family and rule-level readings are intended. B starts from the same model's A output, so B and A are not independent. Claude Bash is not path-sandboxed (read denies plus an audit only). Models ran on different days and hosts load was not controlled. Token usage excludes Codex child agents. Nothing here is a release or accuracy claim.

## Results
