# Debugger skill-effect v4: tool-enabled pilot on raw Playwright reports (2026-10-05)

Status: **`INCONCLUSIVE` under the frozen rule, and no lift is shown.** Two of 72 calls were unscored (the preflight rerun of the staged project did not reproduce the frozen failing-test set, twice, for the same call), and the no-skill baseline scored 0.917, above the preregistered 0.90 ceiling. Descriptively, on the 70 scored calls the full-match rate was **0.882 with the `playwright-debugger` skill versus 0.917 without it** (paired lift -0.042, 95% CI -0.194 to +0.097; better on 1 case, worse on 2, tied on 9), at 2.6 times the cost ($2.48 versus $0.94 over 34 and 36 calls). Nothing here supports a skill benefit; nothing supports a skill harm either.

## Why this experiment exists

v1-v3 measured zero-tool prompts over curated artifacts. v2 and v3 found the taxonomy-free baseline near a ceiling, and the artifacts carried author-written notes (`dom_note`, `probe_note`, ...) that in several cases state the maintainers' mechanism almost outright (for example v3 `pw-03`, `pw-08`, `pw-10`, `cy-10`). v4 changes three things: the model works with tools (Read, Grep, Glob, Bash) in a real project, the artifacts are what Playwright actually emits (`playwright-report/results.json`, traces, screenshots from a real `playwright test` run), and scoring is deterministic against faults seeded at build time, with no model judge.

## Design

12 author-written Playwright cases ([`cases/`](cases/)), each a tiny app, a spec, and sometimes a helper, README, or CHANGELOG. They include a setup hook that cascades into four failures (`pw-01`), a product bug behind a seeded hook (`pw-10`), two product bugs plus a stale locator in a shared helper plus a stale title in one report (`pw-09`, `pw-11`), and lookalikes such as a slow-but-successful response versus a transition read. Truth ([`truth/`](truth/)) is the defect file and line, a mechanism from a neutral nine-value enum that both arms receive, the product-or-test diagnosis, and the number of distinct root causes. A call scores `full` only when every seeded root cause is matched within 3 lines with the right mechanism and diagnosis and the number of findings equals the number of root causes.

Arms: `skill` (same prompt, tools, legend and schema, plus an instruction to read and follow the working-tree `playwright-debugger` skill, staged outside the project because its trusted launcher rejects an in-project copy) and `no-skill`. Claude `claude-sonnet-5-5` (Claude Code 2.1.289), three repetitions, seeded shuffle, 72 calls, per-call cap $1.50, run cap $25. The prompt tells both arms the checkout is trusted and disposable and that narrow `playwright test` commands are approved. [`protocol.json`](protocol.json) was frozen, with digests of every case file, truth file, skill file, prompt frame, schema and the runner, before the first scored call; the run recorded `input_drift: false`. Two discarded smoke calls on `pw-07` ($0.09 and $0.02, both correct) measured cost before the protocol was frozen. One type annotation was added to the runner after the run to satisfy Pyright (recorded in `protocol.json`); it changes no runtime behavior.

Decision rule (frozen): `PASS` needs lift >= +0.15, bootstrap 95% CI lower bound > 0, skill diagnosis not more than 0.05 below no-skill, and a no-skill baseline below 0.90; `INCONCLUSIVE` on any unscored call, drift, spend-cap stop, or a baseline at or above the ceiling.

## Results

| Measure | `skill` | `no-skill` |
| --- | ---: | ---: |
| Scored calls | 34 of 36 | 36 of 36 |
| Full match (primary) | 0.882 | 0.917 |
| Right root-cause count | 1.000 | 1.000 |
| Cost, turns, summed call time | $2.48, 219, 475.7 s | $0.94, 180, 394.0 s |

Paired lift -0.042 (CI -0.194 to +0.097). The two unscored calls were `pw-04` rep 2 and `pw-05` rep 3 of the skill arm; in both, an extra test (`shows the report heading`, `adding a book puts one item in the cart`) failed during the harness's own staging run (cause not investigated; three-way parallel load is the likely one), so the frozen preflight rejected the call twice. They are not imputed. Per-case results are in [`reports/claude-sonnet-results.json`](reports/claude-sonnet-results.json); raw calls are in [`reports/claude-sonnet.json`](reports/claude-sonnet.json).

## Limits

- **Ceiling.** The baseline model found nearly every seeded fault. These cases are too easy to separate the arms; harder faults, noisier multi-failure reports, or smaller models are needed before a rerun can say anything.
- **Scoring ambiguity.** Two cases have defensible locations the truth did not accept. In `pw-02` the skill arm named `app.mjs:9` (where the broken store is declared) in two calls while the truth is the call site at line 17; in `pw-05` the baseline named the server's unreset state at `app.mjs:9` while the truth names the spec. Those misses are in the scores as frozen and affect both arms; they were not re-scored after the fact. `pw-05` is 0/3 for the baseline and 1/2 for the skill.
- **Author-written faults.** Seeded faults are independent of the F-code taxonomy but not of the author, so this is not accuracy on real-world failures; v2 and v3 remain the real-failure evidence.
- **Mechanism translation.** The skill's native vocabulary is F1-F15; the shared mechanism enum forces a translation that may cost the skill arm accuracy it would not lose in its own format.
- **One host, Playwright only, three repetitions, twelve cases.** A second model family was not run: the protocol names it as unrun, because a ceiling-limited first arm leaves nothing for a second host to resolve.
- **Cost.** The skill arm used 2.6 times the cost for the same coverage here; no cost-efficiency claim is made beyond the measured totals.

## Reproduce

```bash
npm ci --prefix scripts/evals/fixtures
python3 scripts/evals/run-debugger-skill-effect-v4.py run --output /abs/report.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v4.py analyze /abs/report.json --output /abs/results.json
```

A rerun starts a new protocol (v5): this one is spent. Reduce harness load (one worker) so the preflight cannot flake, and fix the two ambiguous truth locations before the first scored call.
