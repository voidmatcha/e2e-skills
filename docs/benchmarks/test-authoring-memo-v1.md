# Test-authoring memo v1: evidence record

Summary evidence for the optional [test-authoring memo](../test-authoring-memo.md). This record holds summarized counts and hashes only. Transcripts, agent output, app sources and fault definitions are not published.

- Memo: SHA-256 `c7e5d9a2dc69ee8f5366154f165269d8a33eaacc5fbb13266a3ed009ba3ca2bf`, 136 words excluding markup, frozen before every pair below.
- Models: `claude-sonnet-5-5` (Claude Code, medium effort) and `gpt-6-sol` (Codex). One model per host.
- Runs: 2026-10-27, harness versions as listed per pair. Development-stage record, not a sealed benchmark.

## Method

1. An agent receives a small web app with its source visible and a neutral prompt to write one Playwright spec for a named feature. The prompt does not mention failure paths.
2. Two arms per host: **bare** (no project instruction file) and **memo** (the memo in `CLAUDE.md` and `AGENTS.md`). Three repetitions per app and arm; each pair uses two apps.
3. Faults are injected one behavior at a time into a copy of the app. Failure-path faults are the target class: rollback after rejection, request sent after failed validation, success shown before or without server confirmation, optimistic update, duplicate-submit guard. Ordinary-path faults are scored as a non-gap control.
4. A spec is valid only if it passes on the unmodified app. A fault counts as detected only if the valid spec fails on every scoring repetition with that fault. Invalid specs detect nothing.
5. Gates were fixed in a pre-registration before each pair: failure-path gain >= +0.40 raw and by majority; non-gap drop <= 0.10; invalid rate <= 0.10; a delivery canary confirming that the instruction file reached the agent. The pre-registrations name the invalid rate as pooled over both hosts and arms; the scorer evaluated it per host. The two readings disagree in two pairs, so both are reported below.
6. Each pair ran once. The memo was not edited after any confirmation pair.

## Results by pair

Failure-path detections over scored observations. All delivery canaries passed.

| Pair | Harness | Claude bare | Claude memo | Codex bare | Codex memo |
| --- | --- | --- | --- | --- | --- |
| C3 | v3 | 8/18 | 15/18 | 3/18 | 15/18 |
| C5 | v3 | 6/18 | 9/12 | 6/18 | 18/18 |
| C6 | v3 | 7/15 | 18/18 | 1/18 | 18/18 |
| C7 | v3 | 4/24 | 15/20 | 2/20 | 13/20 |
| P8 | v4 | 6/18 | 17/18 | 0/15 | 16/18 |
| **Pooled** | | **31/93** | **74/86** | **12/89** | **80/92** |
| P8h (Codex rerun, not pooled) | v5 | | | 1/18 | 15/18 |

Gate verdicts under both readings of the invalid-rate gate. "Per host" is how the scorer applied it; "pooled" is the pre-registered text. The other gates are identical in both readings.

| Pair | Pooled invalid | Claude, per host | Claude, pooled | Codex, per host | Codex, pooled |
| --- | --- | --- | --- | --- | --- |
| C3 | 0/24 | not met: gain +0.39 raw, +0.33 majority | not met: same | met | met |
| C5 | 2/24 | not met: host invalid 2/12 | met | met | met |
| C6 | 1/24 | met | met | met | met |
| C7 | 3/24 | met | not met: pooled invalid 3/24 | not met: host invalid 2/12 | not met: pooled invalid 3/24 |
| P8 | 1/24 | met | met | met | met |
| **Met** | | **3/5** | **3/5** | **4/5** | **4/5** |
| P8h (not pooled) | 0/12 | | | met | met |

The met counts are the same under both readings (Claude 3/5, Codex 4/5), but the pairs differ: per host, Claude meets C6, C7 and P8; pooled, Claude meets C5, C6 and P8. Codex meets C3, C5, C6 and P8 under both.

P8h reran the P8 pair for Codex only under harness v5, which gave Codex a browser outside the sandbox. It was pre-registered before any call and reported either way. Two infrastructure amendments are recorded: one in-flight cell was killed when the run paused for another browser job, and one when the disk filled; both were archived unscored and regenerated under the same names. All 12 P8h cells executed their tests in-cell. Failure-path gain was +0.78 raw and +0.83 by majority, with no invalid cells; the delivery canary passed.

Non-gap detection did not drop by more than the gate in any pair, including P8h. Denominators differ because invalid specs are excluded.

Not counted as confirmation: the pair used to select this memo wording and the selection round that compared it with two alternatives.

## Real-repository checks

TanStack Query example `examples/react/nextjs-app-optimistic-updates` at commit `ff8bdaff` (MIT), three failure-path faults, three repetitions, harness v5 (round `round-rr1h`), run once:

| Host | Bare | Memo | Gate |
| --- | --- | --- | --- |
| Claude | 0/9 | 9/9 | met |
| Codex | 0/9 | 8/9 | met |

An earlier run on harness v4 (round `round-rr1`) is kept in the working record: Claude 0/9 to 9/9; Codex 0/9 to 3/3 with two of three memo cells invalid (gate not met), because Codex could not launch a browser in-cell. The public example is likely in the models' training data.

A second pre-registered check (round `round-rr2`, harness v5, run once) used two more repositories: `flaskr`, the Flask tutorial (`pallets/flask` `examples/tutorial` at `d086db8`, BSD-3-Clause, very likely in training data), and `benginN/caltask` at `bd84aca` (MIT, less known). Each app had six faults: four failure-path faults (two in the memo's five classes, two outside them) and two non-gap controls. Bare versus memo, three repetitions, both hosts; 24 cells, 0/24 invalid, every cell ran its spec in-cell, delivery canaries passed.

| App | Claude bare | Claude memo | Codex bare | Codex memo |
| --- | --- | --- | --- | --- |
| flaskr | 0/12 | 9/12 | 0/12 | 7/12 |
| caltask | 3/12 | 9/12 | 3/12 | 11/12 |
| Both | 3/24 | 18/24 | 3/24 | 18/24 |

The pre-registered gate was met on both hosts; non-gap detection was 12/12 in both arms. The two hosts' totals coincide, but their per-cell outcomes differ. Across the three repositories, failure-path detection rose from 3/33 to 27/33 for Claude and from 3/33 to 26/33 for Codex. For the two well-known apps (TanStack example, flaskr) read this as direction only; caltask is the less-known one. These checks are external validity only and are not pooled with the authored pairs.

## Limits

- Scope: the memo targets failure paths of flows that write to a server; it adds nothing where there are none. The measured fault classes were chosen by the memo's author, the out-of-class result is one pair, and no measurement with independently chosen faults exists yet.
- An independent replication by a separate benchmark session (two other apps, 96 valid cells, two models) measured no difference with this exact memo (same SHA-256), but its faults were ordinary-path behaviours, not the failure-path classes the memo targets; it shows the memo did not change ordinary-path detection there (mostly ceiling) and does not test the memo's targeted claim.
- Small authored apps with visible source; neutral prompts only; three repetitions per app.
- One model per host. Results may not transfer to other models, efforts or hosts.
- In the pooled pairs (harness v3 and v4), Codex cells could not launch a browser in-cell, so every Codex spec there was written without running it. Codex had a browser only in the harness v5 runs: the P8 Codex rerun (P8h), where all 12 cells executed their tests in-cell, and the real-repository runs `round-rr1h` and `round-rr2`.
- Under harness v3 (C3 to C7), Claude also ran its spec in a minority of cells: 18 of 84 Claude cells across confirmations 2 to 6. Most Claude invalid cells came from a permission artifact: a shell heredoc write was denied and the agent stopped without running its spec. Claude invalid cells: C5 memo 2/6, C6 bare 1/6, C7 memo 1/6; none in C3 or P8.
- Claude cells also loaded the operator's user-level `CLAUDE.md` in both arms (equal across arms; recorded as a caveat in the working record). Codex cells ran with a per-cell `CODEX_HOME` that held no `AGENTS.md` and with user config ignored, so they did not load the operator's global `AGENTS.md`.
- The memo was selected after earlier development pairs. Alternative wordings (v4a, v4b, v5) and a self-check script did not beat it, but none of them was a pre-registered superiority test.
- Records (local, not published): rounds `confirm3`, `round-conf5`, `round-conf6`, `round-conf7`, `round-p8`, `round-p8h`, `round-rr1`, `round-rr1h` and `round-rr2`, with their pre-registrations.
- Development-stage evidence: not a sealed benchmark, not proof that the memo improves tests on any particular project.
