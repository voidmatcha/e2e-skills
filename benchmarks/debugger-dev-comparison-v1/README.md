# Debugger development comparison v1 (2.0.1)

A local development comparison of the Playwright debugger on four real OpenMetadata CI reports. It tuned the 2.0.1 wording; it is **not** a held-out or preregistered result and freezes no protocol.

## Setup

- Cases: the four reports in [debugger-ci-artifacts-v1](../debugger-ci-artifacts-v1/README.md) that still held unexpired blob shards (PR #34725, #34811, #35016, #34929), merged with `playwright-report/results.json`. Reader-excerpt hashes are in `results.json`; the reports themselves are not committed.
- Arms, three repetitions each, `claude -p --model sonnet`, one fresh working directory per run, tools limited to `Read`/`Grep`/`Glob` (plus the bundled reader for the skill arm):
  - `noskill`: no skill, `--disable-slash-commands`, prompt without the skill name.
  - `skill`: the skill loaded with `--plugin-dir` **outside** the project, user settings excluded with `--setting-sources project`.
- Judge: `codex exec` with `gpt-6-sol`, one answer at a time, arm unlabelled (the finding template still reveals the skill arm). It scores cause match against a maintainer-known background (`scripts/judge.py`), counts claims the reader excerpt does not support, and records whether the answer says the cause is not in the report. For three of four cases that background states that the real cause is not in the report, so the "not in the report" rate is the metric the tuning targeted.
- Cost, turns, and time come from the `claude` result record.

## Invalid first attempts

Two earlier 24-run batches were discarded. The first loaded the skill from the user's settings, where `skillOverrides` disabled it. The second installed the skill inside the project, so the bundled launcher correctly refused to run ("launcher resolves inside the target project"); that is the safety rule working, not a defect.

## Rounds

Each row is 12 runs. `base` is the 2.0.0 skill; each later round builds on the stated parent (`rounds/mk_r*.py`; r5 is r3 plus the Phase 2 spec-source sentence; r4 inlined the command into SKILL.md Phase 1 and was dropped).

| Arm / round | Cost | Time | Turns | Unsupported claims | Says cause not in report | Strict cause match |
|---|---|---|---|---|---|---|
| noskill | $0.092 | 31 s | 6.7 | 9.25 | 8% | 25% |
| base (2.0.0) | $0.111 | 33 s | 7.2 | 5.42 | 58% | 25% |
| r1 evidence wording | $0.114 | 31 s | 7.3 | 4.17 | 92% | 25% |
| r2 + one line per field | $0.113 | 33 s | 7.3 | 3.75 | 92% | 25% |
| r3 + literal one-line reader command | $0.105 | 29 s | 6.6 | 3.25 | 83% | 25% |
| r4 (dropped) | $0.111 | 28 s | 6.8 | 3.33 | 100% | 25% |
| **r5 (shipped in 2.0.1)** | **$0.103** | **26 s** | **6.2** | **2.92** | **100%** | 25% |

## What it supports

- The reader command with `PROJECT_ROOT=$(...)` and a quoted variable was rejected by the host's exact-command approval in most base runs and cost one or two extra turns; the literal one-line form was not rejected in r5. This is the clearest effect and the likely source of the cost drop.
- Fewer unsupported claims and more explicit "not in the report" answers followed the evidence-first wording. The judge saw maintainer background that prescribes hedging, so this measures the targeted behavior.

## What it does not support

- Better diagnosis. Strict cause match is 3 of 12 in every round, consistent with one scoreable case.
- Any held-out claim. The wording was tuned on these same four reports over five rounds, one judge model scored them, and 12 runs per row leave the cost difference ($0.111 to $0.103) within about three within-arm standard deviations.

## Files

`results.json` (per-run scores and aggregates for every round), `scripts/` (harness; set `SCRATCH` to a directory holding `om-*/playwright-report/results.json`), `rounds/` (the edit applied in each round and the final diff against 2.0.0).
