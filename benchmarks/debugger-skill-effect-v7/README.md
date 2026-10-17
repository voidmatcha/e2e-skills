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

## Results

Written after the run (2026-10-17). This section is not bound by `freeze.json`; nothing above it was edited.

**Status update, 2026-10-17.** The `Status` line at the top of this file ("PREPARED, NOT FROZEN, NOT RUN") is the pre-run text and is left as written. The protocol was frozen on 2026-10-16T00:25:24Z (`freeze.json`: protocol sha256 `b4b6ed93...f3336c`, runner script sha256 `de77447b...bde5`), the canary was run, and the full run completed. Current status: **RUN, verdict FAIL by its rule.**

Source files are in [evidence/](evidence/) (`analyze.out`, `results.json`, run and judge logs, digests in `SHA256SUMS`). Machine-specific home paths in `results.json` and the logs were replaced by `/Users/example/` and nothing else changed. The full model and judge transcripts (`model.json`, `judged.json`) stay in `~/.cache/e2e-skills-bench/debugger-v7/`.

### Run

Generation: Claude `sonnet` (`claude-sonnet-5-5`, Claude Code 2.1.300), every tool disabled. Judge: Codex `gpt-6-sol` (codex-cli 0.159.3). 336 of 336 model calls and 56 of 56 judge calls were scored; infrastructure errors, invalid predictions, judge failures, unjudged runs, prompt-digest mismatches and retries were all 0. 28 development cases (14 Playwright, 14 Cypress), 3 repetitions, 4 arms.

### Verdict: FAIL (new-lean minus old)

| # | Check | Bar | Measured | Result |
|---|---|---|---|---|
| 1 | strict match, 95% lower bound | >= -0.05 | +0.024, interval 0.000 to +0.060 (0.821 against 0.798) | met |
| 2 | strict match, point estimate | >= -0.05 | +0.024 | met |
| 3 | F-code exact, 23 labeled cases, 95% lower bound | >= -0.10 | -0.029, interval -0.116 to +0.058 (0.609 against 0.638) | **not met** |
| 4 | product/test diagnosis accuracy | >= old - 0.05 | 0.798 against 0.786 | met |
| 5 | unsupported claims per answer | new-lean - old <= +0.30 | -0.036 (1.381 against 1.417) | met |
| 6 | input tokens | <= 0.80 x old | 0.740 | met |

Only check 3 failed. Its interval reaches below -0.10 because only 23 cases carry F-code labels (3 better, 4 worse, 16 tied); the result is "not proven", not a measured loss, and it does not show equivalence either. `new-full` against `old` and `new-lean` against `new-full` fail the same check (lower bounds -0.116 for both) and never change the verdict. The 3.0.0 `classification-procedure.md` differs from the text the labels were agreed on, so F-code agreement favors the new arms; that is why this check is a development-only reading, and why v8 was prepared on a larger corpus.

Descriptive: against the taxonomy-free `free` arm, strict match was 0.821 for the lean text and for `free` (difference 0.000, interval -0.083 to +0.095), and the skill texts made fewer unsupported claims (lean 1.38, old 1.42, `free` 2.01). No accuracy lift over a taxonomy-free prompt is claimed. Input tokens: lean 2,301,175, old 3,108,830, `new-full` 3,574,170 (1.15 of old), `free` 306,850.

### Limits

Development set, not a holdout; one generator model, one judge family, three repetitions; truth is the merged fix, not independent human adjudication; zero-tool prompts do not test the tool-using flow, the conditional load of `safety-procedures.md` or the post-diagnosis review. This result is kept as run; [v8](../debugger-skill-effect-v8/README.md) is the larger follow-up and does not replace it.
