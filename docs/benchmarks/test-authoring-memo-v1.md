# Test-authoring memo v1: evidence record

Summary evidence for the optional [test-authoring memo](../test-authoring-memo.md). This record holds summarized counts and hashes only. Transcripts, agent output, app sources and fault definitions are not published.

- Memo: SHA-256 `c7e5d9a2dc69ee8f5366154f165269d8a33eaacc5fbb13266a3ed009ba3ca2bf`, 136 words excluding markup, frozen before every pair below.
- Models: `claude-sonnet-5-5` (Claude Code, medium effort) and `gpt-6-sol` (Codex). One model per host.
- Runs: 2026-10-27, harness versions as listed per pair. Development-stage record, not a sealed benchmark.

## Method

1. An agent receives a small web app with its source visible and a neutral prompt to write one Playwright spec for a named feature. The prompt does not mention failure paths.
2. Two arms per host: **bare** (no instruction file) and **memo** (the memo in `CLAUDE.md` and `AGENTS.md`). Three repetitions per app and arm; each pair uses two apps.
3. Faults are injected one behaviour at a time into a copy of the app. Failure-path faults are the target class: rollback after rejection, request sent after failed validation, success shown before or without server confirmation, optimistic update, duplicate-submit guard. Ordinary-path faults are scored as a non-gap control.
4. A spec is valid only if it passes on the unmodified app. A fault counts as detected only if the valid spec fails on every scoring repetition with that fault. Invalid specs detect nothing.
5. Gates were fixed in a pre-registration before each pair: failure-path gain >= +0.40 raw and by majority; non-gap drop <= 0.10; invalid rate <= 0.10; a delivery canary confirming that the instruction file reached the agent. The pre-registrations name the invalid rate as pooled; the scorer evaluated it per host, and the verdicts below are the scorer's.
6. Each pair ran once. The memo was not edited after any confirmation pair.

## Results by pair

Failure-path detections over scored observations. All delivery canaries passed.

| Pair | Harness | Claude bare | Claude memo | Claude gate | Codex bare | Codex memo | Codex gate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C3 | v3 | 8/18 | 15/18 | not met: gain +0.39 raw, +0.33 majority | 3/18 | 15/18 | met |
| C5 | v3 | 6/18 | 9/12 | not met: invalid 2/6 cells | 6/18 | 18/18 | met |
| C6 | v3 | 7/15 | 18/18 | met | 1/18 | 18/18 | met |
| C7 | v3 | 4/24 | 15/20 | met | 2/20 | 13/20 | not met: invalid 2/12 cells |
| P8 | v4 | 6/18 | 17/18 | met | 0/15 | 16/18 | met |
| **Pooled** | | **31/93** | **74/86** | **3/5** | **12/89** | **80/92** | **4/5** |

Non-gap detection did not drop by more than the gate in any pair. Denominators differ because invalid specs are excluded.

Not counted as confirmation: the pair used to select this memo wording and the selection round that compared it with two alternatives.

## Real-repository check

TanStack Query example `examples/react/nextjs-app-optimistic-updates` at commit `ff8bdaff` (MIT), three failure-path faults, three repetitions, harness v5, run once:

| Host | Bare | Memo | Gate |
| --- | --- | --- | --- |
| Claude | 0/9 | 9/9 | met |
| Codex | 0/9 | 8/9 | met |

An earlier run on harness v4 is kept in the working record: Claude 0/9 to 9/9; Codex 0/9 to 3/3 with two of three memo cells invalid (gate not met), because Codex could not launch a browser in-cell. This check is external validity only and is not pooled. The public example is likely in the models' training data.

## Limits

- Small authored apps with visible source; neutral prompts only; three repetitions per app.
- One model per host. Results may not transfer to other models, efforts or hosts.
- In the authored pairs (harness v3 and v4), Codex cells could not launch a browser in-cell, so every Codex spec there was written without running it. Only the real-repository rerun (harness v5) gave Codex a browser.
- Before harness v4, many invalid Claude cells came from a permission artifact: a shell heredoc write was denied and the agent stopped without running its spec. This depresses Claude's memo-arm counts in C3 to C7.
- The memo was selected after earlier development pairs. Alternative wordings (v4a, v4b, v5) and a self-check script did not beat it, but none of them was a pre-registered superiority test.
- Development-stage evidence: not a sealed benchmark, not proof that the memo improves tests on any particular project.
