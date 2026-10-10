# Reviewer boundary wording pilot (2026-10-04)

Status: **no lift on the synthetic ceiling cases; a targeted Sonnet `#20` false-positive reduction on one previously failing case**. This is public development evidence for four 2.0.0 reviewer wording clarifications (`#10a`, `#11c`, `#19`, `#20`), not a release holdout or a general skill-quality estimate.

## Design

Codex `gpt-6-sol` (`codex-cli 0.159.3`, medium effort) reviewed the same four source cases under BEFORE and AFTER wording, three times per case and arm (24 completed model calls in each experiment). Each case contains an exact positive and a false-positive guard; `#19` has two positives, so each arm has five unique positive labels and four guard lines. Cases, expected lines, protocol, and order were fixed in the runner before the first call. Alternating arm order reduces simple order bias. Model tools were disabled, JSON output was schema-enforced, and the existing holdout runner supplied isolated Codex credentials and a strict environment allowlist.

The primary experiment embedded the repository's complete seven-file `full` prompt profile and numbered source, as the existing holdout runner does. Its BEFORE snapshot copied the current skill, then reverted only the four relevant `pattern-reference.md` sections and the `#11c` semantic-review row to `HEAD`; all other prompt material was identical. The separate excerpt experiment embedded only each affected pattern section. Neither experiment executed the scanner, browser, or subagents.

| Experiment | Arm | Correct positive decisions | Guard hits | Input tokens (cache reads included) | Sum model-call time |
| --- | --- | ---: | ---: | ---: | ---: |
| Full prompt | BEFORE | 15/15 | 0/12 | 649,553 | 108.274 s |
| Full prompt | AFTER | 15/15 | 0/12 | 649,306 | 112.415 s |
| Rule excerpt | BEFORE | 15/15 | 0/12 | 147,286 | 89.063 s |
| Rule excerpt | AFTER | 15/15 | 0/12 | 147,173 | 86.071 s |

Each of the four target patterns had identical BEFORE and AFTER judgments in every repetition. The full-prompt input-token difference is −247/649,553 (−0.038%); the excerpt difference is −113/147,286 (−0.077%). Cached-input totals differ between arms, and summed call time moves in opposite directions across the two experiments. These small differences are not evidence of a token, cost, or latency improvement. The wording changes remain justified as contract consistency and false-positive-boundary clarification, not as a measured detection lift.

The `#20` fixture shows the backend routes and tenant lifetime but does not show the UI button-to-POST wiring. Its positive label is therefore conditional on that unshown connection, not independently source-confirmed. Excluding the three repeated `#20` positive decisions leaves both arms at 12/12 positives and 0/9 guard hits in each experiment; the no-lift conclusion does not depend on that label.

The cases are deliberately compact, public, and authored with knowledge of the intended rules. Codex also helped author the rule text, and no independent human or sealed labels were used. All BEFORE arms already reached the ceiling on these cases, so the experiment cannot estimate gains on harder real repositories. A complete skill workflow with scanner and source exploration was not measured. A zero-tool full-prompt run measures model interpretation of the skill text, not end-to-end reviewer effectiveness. No new release-performance claim follows from this pilot.

## Replay of an observed false positive

The ceiling cases could not test whether the changed `#20` wording prevents an error. In the frozen v15 Claude Sonnet full-arm report, `v10-cy-15` was reported as `#20` at `cypress/e2e/plots.cy.ts:20` in **3/5** repetitions; v10 Claude Opus did so in **1/5**. The source shows a release-plot click and an API-login helper, but no application or fixture evidence that either writes to shared or persistent backend state. Under the current `#20` source-evidence boundary, neither is a final finding. This was an observed error rather than a newly invented clean example.

We replayed that exact two-file v10 source case with the full seven-file prompt profile and v15's enforced output schema. The BEFORE snapshot reverted only the `#20` section to `HEAD`; the AFTER snapshot kept the clarified `#20` wording. All other prompt files, source bytes, model settings, and five-repetition schedule were the same within each model. Tools, scanner, browser, and subagents remained disabled.

| Model | Historical full-arm `#20` at line 20 | New BEFORE | New AFTER |
| --- | ---: | ---: | ---: |
| `claude-sonnet-5` | 3/5 | 2/5 | 0/5 |
| `claude-opus-5` | 1/5 | 0/5 | 0/5 |

Every new call completed. Sonnet's BEFORE arm also made one additional `#20` report on the API-login request at `cypress/support/commands.ts:3`; AFTER returned no findings in all five calls. This is a **case-specific reduction observed on Sonnet**, not a general improvement estimate: it is one known public failure selected after inspecting prior results, has only five paired repetitions, and Opus showed no difference in the new run. Historical CLI/skill versions are context, not a paired control. No token or latency conclusion follows from these calls.

### Three-case `#20` safety check

To check whether suppressing that false positive also suppresses a real finding, a second Sonnet run used three frozen v10 cases: a stubbed subscription (`v10-cy-11`, guard), an RSVP button wired in source to a POST against a documented shared staging backend (`v10-cy-13`, positive), and the previously observed release-plot false positive (`v10-cy-15`, guard). The case order, exact target lines, five-repetition schedule, and scoring were fixed in the runner before calls began. BEFORE and AFTER differed only in the `#20` section as above. All 30 full-prompt, zero-tool calls completed on `claude-sonnet-5` with Claude Code 2.1.286.

| Case | BEFORE correct | AFTER correct |
| --- | ---: | ---: |
| Stubbed subscription guard | 5/5 | 5/5 |
| Source-confirmed shared-backend write | 5/5 | 5/5 |
| Previously observed false-positive guard | 4/5 | 5/5 |

The sole new BEFORE error flagged both the plot click at `cypress/e2e/plots.cy.ts:20` and API-login helper at `cypress/support/commands.ts:3` as `#20`; AFTER made no `#20` reports on that case. The positive remained detectable in every repetition. This supports a narrow safety observation, not a population-level accuracy gain: these are three public, synthetic, already-known cases; repeated answers are not independent defects; no blind human adjudication or complete skill workflow was used. It also does not establish an effect for the other three wording clarifications.

Summed input tokens, including cache reads and writes, were 1,921,859 BEFORE and 1,917,562 AFTER (−0.22%); summed model-call time was 749.735 s and 744.505 s (−0.70%). Output tokens were 65,564 and 62,335. These small differences in stochastic calls are **not** evidence of token, cost, or latency improvement; input-token totals are not billing ratios. The full [30-call report](sonnet-20-safety-matrix.json) contains source/prompt digests, responses, usage, and elapsed times.

## Reproduce and audit

Run from this checkout with an authenticated Codex CLI. Both runners refuse to overwrite an existing report; choose new output paths for a rerun.

```bash
python3 scripts/evals/run-reviewer-boundary-pilot.py \
  --runner-path /absolute/path/to/codex \
  --output /absolute/path/to/excerpt-results.json
python3 scripts/evals/run-reviewer-boundary-full-pilot.py \
  --runner-path /absolute/path/to/codex \
  --output /absolute/path/to/full-results.json
python3 scripts/evals/run-reviewer-observed-fp.py \
  --runner-path /absolute/path/to/claude \
  --model claude-sonnet-5 \
  --output /absolute/path/to/sonnet-observed-fp.json
python3 scripts/evals/run-reviewer-observed-fp.py \
  --runner-path /absolute/path/to/claude \
  --model claude-opus-5 \
  --output /absolute/path/to/opus-observed-fp.json
python3 scripts/evals/run-reviewer-20-safety-matrix.py \
  --runner-path /absolute/path/to/claude \
  --model claude-sonnet-5 \
  --output /absolute/path/to/sonnet-20-safety-matrix.json
```

The captured reports are [excerpt results](results.json), [full-prompt results](full-results.json), [Sonnet false-positive replay](sonnet-observed-fp.json), and [Opus false-positive replay](opus-observed-fp.json). They retain every parsed answer, exact score or target-hit flag, usage record, elapsed time, and raw-answer digest, but not the full raw event stream or credentials. The case-definition digest shared by the ceiling reports is `ab269c1c461a8720fdd98e4009a260e22b514d4f8a0bae5a926c2ada8ccb38ff`. Full-prompt skill digests are `69b8ac92a8d16580d7e65f04eaa195e288f275ca7a8d95a39715b16e405bb44c` (BEFORE) and `6acaf64ad9f03c4e644192eb409a7a9b8999861e8a1ce49c2c5c5ea7bf8a4c7f` (AFTER). The observed-FP replay shares the same AFTER digest; its `#20`-only BEFORE digest is `13613ff87cd115e2dd8e55a48b80a15e7be7562cca37788ac73910568bbb43ff`. A rerun may differ because provider backend versions are not pinned by CLI versions.
