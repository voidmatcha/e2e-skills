# Debugger skill-effect v7: does the 3.0.0 lean debugger text keep the 2.0.1 diagnosis quality? (prepared 2026-10-16)

Status: **PREPARED, NOT FROZEN, NOT RUN.** `protocol.json` pins every input by digest; `freeze.json` does not exist yet. No model call has been made.

A zero-tool, non-inferiority development comparison on the 28 real failures of the [v3 corpus](../debugger-skill-effect-v3/README.md). It is named v7 because a separate [v6](https://github.com/voidmatcha/e2e-skills/tree/next/2.1.0-rebased/benchmarks/debugger-skill-effect-v6) (thinned 2.1 text versus pre-thin text, the v2 corpus) already exists on branch `next/2.1.0-rebased`; this protocol reuses its harness design and judges.

## What it tests

| Arm | Prompt material | Playwright / Cypress bytes |
| --- | --- | ---: |
| `new-full` | 3.0.0 `SKILL.md` + all seven references (worst-case load) | 57,099 / 56,230 |
| `new-lean` | 3.0.0 `SKILL.md` + artifact-extraction, classification-procedure, fix-verification (the typical diagnosis path; primary arm) | 29,531 / 33,621 |
| `old` | released 2.0.1 `SKILL.md` + all six references | 55,394 / 52,288 |
| `free` | taxonomy-free "diagnose the root cause" prompt, 3-field schema | small |

Calls: 28 cases x 4 arms x 3 repetitions = 336 (Claude `sonnet`, every tool disabled), then 56 judge calls (Codex `gpt-6-sol`: 28 blind root-cause match, 28 blind unsupported-claim count; twelve shuffled candidates per case, no arm or F-code visible). A canary is 8 calls (`pw-02`, `cy-06`, one repetition, four arms) and is non-data.

## Preregistered rule (new-lean minus old)

PASS only if every check holds: strict-match difference 95% case-cluster bootstrap lower bound >= -0.05 and point estimate >= -0.05; F-code exact (23 labeled cases) lower bound >= -0.10; product/test attribution no more than 0.05 below `old`; unsupported claims per answer at most +0.30 above `old`; `new-lean` input tokens at most 0.80 of `old`. FAIL if all calls are scored and any check fails. INCONCLUSIVE on any unscored call, incomplete judge entry after the registered three-attempt judge retry, digest or prompt-digest mismatch, or a canary report. `new-full` versus `old` and `new-lean` versus `new-full` get the same quality checks and are reported without changing the verdict. [hypothesis.md](hypothesis.md) was written before any call.

A PASS supports one sentence only: on these 28 development cases the lean text was not worse than the 2.0.1 text on zero-tool diagnosis by more than the margins, at about the stated share of the input tokens. It does not support "better", "safer", or any claim about the workflow, the safety gates, or the conditional load of `safety-procedures.md`.

## Guards added before any call

- **Freeze marker.** `freeze` writes `freeze.json` (protocol and script SHA-256) once; `run`, `canary`, `judge` and `analyze` refuse if either file changed.
- **Prompt-digest proof.** `analyze` recomputes every call's prompt digest from the frozen snapshot and excerpt; a mismatch makes the verdict INCONCLUSIVE. This is the proof that each arm saw its declared text (zero-tool calls have no tool log to count).
- **CLI minimum, not an exact pin.** Claude Code >= 2.1.289 and Codex CLI >= 0.146.0 are checked before any model call (AGENTS.md: exact pins strand a protocol).
- **Bounded judge re-ask.** v6 lost 14 of 390 calls to one judge answer that omitted candidate ids and needed a post hoc re-judge. Here an answer that does not parse or omits an id is re-asked with the identical frame and order, up to three attempts, registered in advance.
- **Canary.** `canary` then `validate-canary`: PROCEED only if all 8 calls exist, none has an infrastructure error, a retry, a missing usage record or an invalid prediction, and every prompt digest matches.
- **No lock, browser, Docker or port**, so it can run beside the thin-eval driver (its process probe only matches `run-generator-*.py`).

## Limits to read before any number

- Zero-tool prompts measure interpretation of the text. The lean rewrite moved the safety text into a reference that `new-lean` deliberately omits, so this cannot show that the conditional load works or that any gate is kept.
- **The corpus is a development set, not a holdout.** It was used once, in v3. The F-code labels were agreed by two blind mappers who saw only each fix and the v3 "new" skill tables. The 3.0.0 `classification-procedure.md` differs from that text by six diff lines per framework, so F-code agreement favors the `new` arms and is not a fair test of new versus old; it is a fair test of `new-lean` versus `new-full`.
- Truth is the merged fix, not independent human adjudication. Both judges are models. One host, one judge family, three repetitions.
- The arms differ in how much text they see by design (that is the 3.0.0 change), not only in wording.
- v3 normalized two raw-log artifacts after its run (a generic runner home path); this protocol pins the current files.

## Was the 3.0.0 text tuned on these cases? (audit, 2026-10-16)

Commands, rerunnable from `wt-300` (`impl/3.0.0`):

```
grep the text for the 28 case ids and the 19 source repositories of corpus.json
git log --since=2026-10-05 -- skills/playwright-debugger skills/cypress-debugger
diff skill-snapshots (v3 'new') against the 3.0.0 files
```

Results: no case id and no repository name appears in any 3.0.0 debugger file (the only string hit is `actual`, from `chrisvasz/actual`, which is an ordinary English word in the text). Three changes touched the debuggers after the v3 run: `6ded5e9d` (release 2.0.0), `afbd10c9` (2.0.1; its message says the wording was tuned and scored on the four OpenMetadata reports of `debugger-dev-comparison-v1`, not on this corpus) and `fd16fee2` (2.1 review fixes), plus the uncommitted 3.0.0 lean rewrite. Against the v3 "new" snapshot the 3.0.0 `classification-procedure.md` differs by six diff lines per framework and `SKILL.md` roughly halves. What this cannot rule out: the v3 result and its F1/F14/F11/F7 confusions motivated the tie-break paragraph the 3.0.0 text inherits, and `pw-14` is an OpenMetadata case from the same repository as the dev-comparison reports. Treat the corpus as seen.

## Run order (the owner runs it; nothing here was executed)

```
python3 scripts/evals/run-debugger-skill-effect-v7.py verify
python3 scripts/evals/run-debugger-skill-effect-v7.py freeze
python3 scripts/evals/run-debugger-skill-effect-v7.py canary --runner claude --model sonnet --runner-path /abs/claude --output /abs/canary.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v7.py validate-canary /abs/canary.json
python3 scripts/evals/run-debugger-skill-effect-v7.py run --runner claude --model sonnet --runner-path /abs/claude --workers 4 --output /abs/model.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v7.py judge /abs/model.json --runner codex --model gpt-6-sol --runner-path /abs/codex --workers 3 --output /abs/judged.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v7.py analyze /abs/judged.json --output /abs/results.json
```

Time estimate (from v3's measured summed call times of about 9 s per skill-arm call and 26 s per judge call): canary about 3 minutes, the 336 model calls about 15 to 25 minutes at four workers, the 56 judge calls about 8 to 12 minutes at three workers, analysis seconds. About 30 to 45 minutes of wall time plus the canary check. Claude usage: 336 calls of roughly 13 to 15 thousand input tokens each; Codex usage: 56 judge calls.

Offline tests: `python3 scripts/ci/test-debugger-skill-effect-v7.py` (26 tests, including synthetic end-to-end PASS, FAIL and INCONCLUSIVE analyses).
