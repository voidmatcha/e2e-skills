# Debugger skill-effect v8: does the shipped 3.0.0 lean debugger text keep the 2.0.1 F-code agreement? (prepared 2026-10-16)

Status: **PREPARED, NOT FROZEN, NOT RUN.** `protocol.json` pins every input by digest and `verify` passes; `freeze.json` does not exist. No scoring call has been made. The only model calls so far are five zero-tool blind labeling calls (see "Labels"; one for the first 60 cases and one per extension batch).

A zero-tool, non-inferiority development comparison on a **new corpus of 107 labeled failures** (73 Playwright, 34 Cypress). It follows [v7](../debugger-skill-effect-v7/README.md) (same arms, same two judges, same margins and guards) and answers the question v7 could not: v7 ended FAIL only because its F-code interval was too wide (difference -0.029, 95% interval -0.116 to +0.058, 23 labeled cases); it did not show a loss. v7 is kept as run. v8 also fixes a mismatch in v7: its `new` snapshot was a working tree whose Playwright `SKILL.md` (11,227 B) differs from the committed release candidate (11,388 B, it carries the 2.0.1 spec-source rule). v8 snapshots the committed tree.

## What it tests

| Arm | Prompt material | Playwright / Cypress bytes |
| --- | --- | ---: |
| `new-lean` | the same `SKILL.md` + artifact-extraction, classification-procedure, fix-verification (typical path; primary arm) | 29,692 / 33,621 |
| `old` | released 2.0.1 (`v2.0.1`, 20cc5fc8) `SKILL.md` + all six references; byte-identical to the v7 `old` snapshot | 55,394 / 52,288 |
| `free` | taxonomy-free "diagnose the root cause" prompt, 3-field schema | small |

Calls: 107 cases x 3 arms x 3 repetitions = **963** (Claude `sonnet`, every tool disabled), then **214** judge calls (Codex `gpt-6-sol`: 107 blind root-cause match, 107 blind unsupported-claim count; nine shuffled candidates per case, no arm or F-code visible). A canary is 8 calls (`pw-n03`, `cy-n01`, one repetition, four arms) and is non-data.

## Preregistered rule (new-lean minus old)

Identical to v7 except that check 3 runs on the **primary label set**: PASS only if every check holds: strict-match difference 95% case-cluster bootstrap lower bound >= -0.05 and point estimate >= -0.05; F-code exact (primary set) lower bound >= -0.10; product/test attribution no more than 0.05 below `old`; unsupported claims per answer at most +0.30 above `old`; `new-lean` input tokens at most 0.80 of `old`. FAIL if all calls are scored and any check fails. INCONCLUSIVE on any unscored call, incomplete judge entry after the registered three-attempt judge retry, digest or prompt-digest mismatch, or a canary report. `new-full` versus `old` and `new-lean` versus `new-full` get the same quality checks and are reported without changing the verdict. F-code differences are also printed on four other sets (all 60 labeled, real only, authored only, author-marked clean fit) and are descriptive. [hypothesis.md](hypothesis.md) was written before any scoring call.

A PASS supports one sentence only: on these 107 development cases the shipped lean text was not worse than the 2.0.1 text on zero-tool diagnosis by more than the margins, at about the stated share of the input tokens. A lower bound under -0.10 is FAIL and means "not proven", not "measured loss". Neither outcome says anything about safety gates or the workflow.

## Corpus

| F-code | real | authored | total | in primary set |
|---|---:|---:|---:|---:|
| F1 | 6 | 3 | 9 | 7 |
| F2 | 10 | 0 | 10 | 10 |
| F3 | 5 | 1 | 6 | 5 |
| F4 | 0 | 3 | 3 | 3 |
| F5 | 5 | 2 | 7 | 4 |
| F6 | 0 | 4 | 4 | 4 |
| F7 | 5 | 2 | 7 | 6 |
| F8 | 3 | 2 | 5 | 2 |
| F9 | 1 | 2 | 3 | 3 |
| F10 | 2 | 3 | 5 | 4 |
| F11 | 12 | 3 | 15 | 10 |
| F12 | 12 | 0 | 12 | 4 |
| F13 | 0 | 4 | 4 | 4 |
| F14 | 11 | 0 | 11 | 10 |
| F15 | 3 | 3 | 6 | 6 |
| **all** | **75** | **32** | **107** | **82** |

- **75 real cases** (57 Playwright, 18 Cypress) are restated from public merged fixes in 67 repositories (MIT, Apache-2.0, BSD-3-Clause), merged 2026-07-27 to 2026-10-16, found by read-only GitHub PR searches and filtered to small test-side fixes with a reported failure. None appears in the v1 to v7 corpora (repository and PR URL checked against every earlier debugger and real-fix benchmark). Each artifact holds only observations: test id, the failure text as reported (verbatim where the PR quoted it, otherwise minimally shaped into a Playwright/Cypress error form), the pre-fix test code from the diff, the frequency or attempt pattern, and environment facts a report would show. The cause and the fix are in `truth/`. Several PR descriptions were written with AI assistants. Of these, 28 come from the first preparation and 47 from the extension (see below).
- **32 authored cases** (16 Playwright, 16 Cypress) are failure artifacts written from the F-code definitions to cover codes that real fixes rarely show (F1, F4, F6, F13, F9, F10, F11 and some F15/F7/F8): real fixes gave no F4, F6 or F13 at all and only one F9. They are labeled by construction before any model call. They follow the taxonomy's canonical patterns, so they are probably easier than real failures; they are a separate stratum and are reported as such. Their repository field is `synthetic-authored`.
- Cases are `pw-n*` / `cy-n*` (real) and `pw-s*` / `cy-s*` (authored). `label-ledger.json` holds each label's rationale, second choice and fit (`clean` or `forced`, 75 clean and 32 forced); it is digest-bound and never appears in a prompt (tested).

### Extension (2026-10-16, after the first 60 were prepared)

The first preparation gave 54 primary cases, which the power simulation showed to be too few to make the F-code check informative. The corpus was therefore extended with 47 further real merged fixes (`extension/`: the builder and the case data, `added-ids*.json`), authored the same way: the PR search was repeated with a relaxed size filter (up to 6 files and 160 changed lines, all files test-side), the candidates were fixed by those filters before any label was set, and each case was labeled from the merged fix using only the F1-F15 table. The blind second mapper then ran on each batch (four extension batches of 35, 7, 2 and 3 cases, because cases were added in rounds when the primary set was still below 80). No case was relabeled after the mapper answered, and no case was dropped because of its label; the disagreements stay in the corpus as before. Cases that looked ambiguous before labeling were not selected, and this selection is the author's, so it is not independent of the author's reading.

Notes on the extension to read before any number:
- **The real stratum now leans toward F2, F11, F12 and F14** (the codes real small test-side fixes most often show). The F-code check is a micro-average over cases, so these codes carry more weight than F1, F3, F5 to F10 and F15. Per-code values are not reported as claims.
- **F12 versus F2.** Of the 8 extension cases the author labeled F12 (a page change made an existing locator ambiguous or stale, with the change named), the blind mapper read 6 as F2 (a strict-mode violation or a locator that was never specific enough). They leave the primary set. This repeats the pattern of `pw-n14` and `pw-n16` in the first 60 and shows the author and the mapper apply the F2/F12 boundary differently; the author labels were not changed.
- **One wording change after the mapper.** In `pw-n38` the keyboard key F2 appears in the author's prose and tripped the packet-hygiene test (no F-code token in a packet). The prose was reworded to "the edit key (function key 2)" in `truth/pw-n38.json`, in `cases/pw-n38.json` (prose fields only; the verbatim test code keeps `press('F2')`, which the test now ignores) and in `blind-labels/packet-ext.md`, after the mapper had answered. The mapper saw "F2" and labeled the case F11, the same as the author. The wording carries the same meaning; `extension/ext_c.py` holds the final text.
- `extension/` holds the case data of the added cases (`ext_a.py` to `ext_g.py`), the builder (`build_ext.py`), the mapper script (`run-ext-mapper.py`), the documentation updater (`update-docs.py`), `original-60-ids.json` and `added-ids*.json`, `labels-final-first60.json` (the first label file) and the mapper logs. Nothing in it is read by the runner.

## Labels

1. **Author label**, from the merged fix (real) or the construction design (authored), using only the F1-F15 table that the 2.0.1 and 3.0.0 texts share. The `classification-procedure.md` files, which differ between old and new, were not used, so the labels do not favor either text.
2. **Blind second mapper** (`blind-labels/`): Codex `gpt-6-sol` (CLI 0.159.3), five zero-tool calls on 2026-10-16, each saw only the root-cause statement and the fix of its cases (item ids shuffled with a fixed seed) and the Phase 2 text of the 2.0.1 `SKILL.md`. The first call covered the first 60 cases (items 1-60) and agreed with the author on **54 of 60**; the four extension calls covered items 61-95, 96-102, 103-104 and 105-107 and agreed on **28 of 47**. Overall it agreed on **82 of 107**. The 25 disagreements stay in the corpus with the author label as truth and leave only the primary F-code set. First 60: `cy-s05` (F5 vs F14), `pw-n16` (F12 vs F2), `pw-n14` (F12 vs F2), `cy-n08` (F8 vs F3), `cy-n10` (F3 vs F10), `pw-n09` (F8 vs F1). Extension: `pw-n41` (F5 vs F14), `pw-n25` (F12 vs F2), `pw-n26` (F12 vs F2), `pw-n43` (F7 vs F14), `pw-n32` (F1 vs F14), `pw-n24` (F12 vs F2), `pw-n46` (F10 vs F11), `pw-n39` (F11 vs F14), `pw-n37` (F11 vs F14), `pw-n27` (F12 vs F2), `pw-n23` (F12 vs F2), `pw-n40` (F11 vs F14), `cy-n12` (F11 vs F14), `pw-n29` (F12 vs F2), `pw-n51` (F14 vs F2), `pw-n52` (F1 vs F14), `pw-n48` (F8 vs F14), `cy-n18` (F11 vs F3), `pw-n54` (F5 vs F14). Outputs and run metadata are in `blind-labels/mapper-output*.json` and `mapper-run*.json`; `apply-blind-labels.py` produced `labels-final.json` (status `final`) from all five outputs.
3. Limits: one author and one second mapper, both models; no human adjudication. The mapper family is the same as the judge family (the judges never see F-codes). Some F-code pairs overlap in the taxonomy itself (F1/F14, F2/F12, F3/F10, F11/F14). The four extension batches were labeled in rounds and the mapper was run after each, so the author knew that the primary set was below 80 when adding the last batches; the labels of the later cases were set before the mapper answered, but their selection was not blind to that aim.

## Power (declared before data)

[power-simulation.py](power-simulation.py) resamples the 23 v7 paired F-code differences (4 worse, 16 tied, 3 better). For the primary set of 82 cases the F-code check passes in about 97 of 100 trials if the true difference is 0, 89 at -0.02, 67 at -0.04, 41 at -0.06 and 16 at -0.08; for the 54 primary cases of the first 60 the figures were 89, 75 and 54. 80 percent power needs about 40 cases at 0, 63 at -0.02 and 77 at the v7 point estimate. So this corpus can confirm a small or zero loss and, if the true difference is the v7 point estimate (-0.029), it is large enough to do so; it still cannot prove that a loss of 0.04 to 0.06 is absent. If the interval straddles -0.10 the plan is a second corpus, not a rescue of this one.

## Tuning audit (2026-10-16)

Zero hits for the 107 case ids and the 67 full repository names (174 patterns in all) in `skills/*-debugger` at 293491f8, rerun after the extension. The short repository names `cypress` and `console` match ordinary words (306 and 9 matches) and are not hits. The text was last changed by commit d357338f (2026-10-16) and the real fixes were collected afterwards from PRs merged 2026-07-27 or later; no debugger text was edited after the snapshot. The real fixes existed before the text was written, so the order of events alone does not exclude influence from earlier work; the audit above is the evidence. Any edit to `skills/*-debugger` after the snapshot invalidates this protocol.

## Guards (inherited from v7)

Freeze marker binding `protocol.json` and the runner; prompt-digest proof per call (an arm that did not see its text makes the verdict INCONCLUSIVE); CLI minimum rather than an exact pin; canary before the run; bounded judge re-ask; no lock, browser, Docker or port. New in v8: `labels-final.json` must be `final` before `freeze` (it refuses a provisional file) and is digest-bound; `refresh-digests` rewrites the protocol digests before the freeze only.

## Cost and time (estimates from the v7 run)

| Stage | Calls | Wall time | Notes |
| --- | ---: | --- | --- |
| canary | 6 | about 3 min | non-data |
| model run (4 workers) | 963 | about 35 to 45 min (estimate) | Claude sonnet, all tools off; about 27 M input tokens in total (scaled from the 720-call estimate; v7: 9.3 M for 336 calls), mostly cacheable skill text; `old` prompts are about 40 k tokens each |
| judge (3 workers) | 214 | about 30 to 40 min (estimate) | Codex gpt-6-sol |
| analysis | - | seconds | |

Revision before the freeze (2026-10-16, owner decision in chat, no v8 model call had run): the descriptive arm `new-full` (release candidate `SKILL.md` + all seven references; 57,260 / 56,230 bytes) was dropped to cut the model run from 1284 to 963 calls. The verdict does not depend on it. H2 and H3 are therefore not run; the worst-case text load is described by bytes only. See `revision_drop_new_full` in `protocol.json`.

## Run order (the owner runs it; nothing past `verify` has been executed)

```
python3 scripts/evals/run-debugger-skill-effect-v8.py verify
python3 scripts/evals/run-debugger-skill-effect-v8.py freeze
python3 scripts/evals/run-debugger-skill-effect-v8.py canary --runner claude --model sonnet --runner-path /abs/claude --output /abs/canary.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v8.py validate-canary /abs/canary.json
python3 scripts/evals/run-debugger-skill-effect-v8.py run --runner claude --model sonnet --runner-path /abs/claude --workers 4 --output /abs/model.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v8.py judge /abs/model.json --runner codex --model gpt-6-sol --runner-path /abs/codex --workers 3 --output /abs/judged.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v8.py analyze /abs/judged.json --output /abs/results.json
```

Offline tests: `python3 scripts/ci/test-debugger-skill-effect-v8.py` (39 tests, including corpus invariants, label logic, blind-packet hygiene and synthetic end-to-end PASS, FAIL and INCONCLUSIVE analyses).

## Limits to read before any number

- Zero-tool prompts measure interpretation of the text. `new-lean` deliberately omits `safety-procedures.md`, so this cannot show that the conditional load works or that any gate is kept.
- A development set, not a holdout and not sealed. 32 of 107 cases are authored by the benchmark's author.
- Truth for real cases is the merged fix, not independent human adjudication; both judges and the second mapper are models; one host, one judge family, three repetitions.
- The arms differ in how much text they see by design, not only in wording.

## Results

Written after the run (2026-10-17). This section is not bound by `freeze.json`; nothing above it was edited.

**Status update, 2026-10-17.** The `Status` line at the top of this file ("PREPARED, NOT FROZEN, NOT RUN") is the pre-run text and is left as written. Current status: **RUN, verdict PASS (non-inferiority, development stage).**

**Valid from.** The result is valid for the harness frozen on 2026-10-16T12:55:08Z (`freeze.json`: protocol sha256 `b15d0884eeca11176ccd88b00a5ec5e88dbb14fd4fd82cd7fd4adc543d5ba8bb`, runner script sha256 `55bb7f5eee11e00a4fe6a17de9de24f5e26097eb043b9573a61d7e12198571f2`). The canary (6 calls, verdict PROCEED) started at 2026-10-16T12:55:24Z. Generation: Claude Code 2.1.300 with `sonnet` (`claude-sonnet-5-5`); the protocol sets a minimum CLI version, not an exact pin. Judge: `codex-cli 0.159.3`, `gpt-6-sol`. Only the third attempt below is data.

Source files are in [evidence/](evidence/) (`analyze.out`, `results.json`, `run3.out`, `judge.out`, `canary.out`, the archived attempts, digests in `SHA256SUMS`). Machine-specific home paths were replaced by `/Users/example/` and nothing else changed. The full transcripts (`model.json`, `judged.json`) stay in `~/.cache/e2e-skills-bench/debugger-v8/`. One authoring helper, `extension/build_ext.py`, had a machine-specific scratch path in its output-directory constant; it was replaced by `/path/to/scratchpad/v8ext` for the repository security gate (the script is not bound by `freeze.json` or `protocol.json`).

### Scope of the claim

Development stage, one generation model, 107 development cases (75 real, 32 authored by the benchmark author). Not a holdout and not a release gate. The only sentence this result supports: on these 107 development cases the shipped 3.0.0 lean text was not worse than the 2.0.1 text on zero-tool diagnosis by more than the stated margins, at about the stated share of the input tokens. It does not support "better", "safer", or any statement about the full workflow or the safety gates.

### Run integrity

963 of 963 model calls and 214 of 214 judge calls were scored. Infrastructure errors, invalid predictions, judge failures, unjudged runs, prompt-digest mismatches, and model or judge retries were all 0.

### Verdict: PASS (new-lean minus old)

| # | Check | Bar | Measured | Result |
|---|---|---|---|---|
| 1 | strict match, 95% lower bound | >= -0.05 | -0.016, interval -0.034 to 0.000 | met |
| 2 | strict match, point estimate | >= -0.05 | -0.016 (0.857 against 0.872) | met |
| 3 | F-code exact, primary set of 82, 95% lower bound | >= -0.10 | +0.016, interval -0.033 to +0.065 (0.813 against 0.797) | met |
| 4 | product/test diagnosis accuracy | >= old - 0.05 | 0.963 against 0.960 | met |
| 5 | unsupported claims per answer | new-lean - old <= +0.30 | -0.075 (1.533 against 1.607), interval -0.227 to +0.078 | met |
| 6 | input tokens | <= 0.80 x old | 0.693 (7,690,757 against 11,097,527) | met |

Lenient match was 1.000 for both arms (107 of 107 tied). On strict match the paired comparison was 2 cases better, 7 worse, 98 tied. The README's Power section already states that check 3 cannot prove the absence of a loss of 0.04 to 0.06.

| Arm | Valid calls | Input tokens | Output tokens |
|---|---:|---:|---:|
| new-lean | 321 | 7,690,757 | 216,854 |
| old | 321 | 11,097,527 | 188,860 |
| free | 321 | 1,043,474 | 101,777 |

### F-code difference by subset (new-lean minus old; descriptive, does not affect the verdict)

| Set | n | Difference | 95% interval | better / worse / tied |
|---|---:|---:|---|---|
| primary (verdict set) | 82 | +0.016 | -0.033 to +0.065 | 11 / 7 / 64 |
| all labeled | 107 | 0.000 | -0.047 to +0.050 | 13 / 13 / 81 |
| real only | 75 | +0.018 | -0.040 to +0.080 | 11 / 9 / 55 |
| **synthetic only** | 32 | **-0.042** | **-0.115 to +0.021** | 2 / 4 / 26 |
| author-marked clean fit | 75 | -0.009 | -0.067 to +0.044 | 7 / 8 / 60 |

The synthetic-only subset has a negative point estimate and a lower bound below -0.10. It is a 32-case descriptive subgroup and not part of the rule; the preregistered rule forbids changing the verdict or rescuing it with another set or margin, and this section does neither. It also means a loss on authored cases cannot be ruled out.

Against the taxonomy-free `free` arm (descriptive): strict match was lower for both skill texts (lean -0.040, interval -0.087 to 0.000; old -0.025, interval -0.062 to +0.009), and `free` made more unsupported claims per answer (2.570, against 1.533 for lean and 1.607 for old). `free` gives no F-code, so its F-code score is 0. No accuracy lift over a taxonomy-free prompt is claimed.

### Attempts (three; only the third is data)

| Attempt | Progress | Ended by | Log |
|---|---|---|---|
| run1 | 720 of 963 | stopped by the operator to relieve host load | [evidence/archived-nondata/run1.out](evidence/archived-nondata/run1.out) |
| run2 | 10 of 963 | stopped by the operator after an automatic restart, same reason | [evidence/archived-nondata/run2.out](evidence/archived-nondata/run2.out) |
| run3 | 963 of 963 | completed; the only source of the numbers above | [evidence/run3.out](evidence/run3.out) |

The cause record is [evidence/archived-nondata/debugger-v8-run1-run2-CAUSE.txt](evidence/archived-nondata/debugger-v8-run1-run2-CAUSE.txt): host swap pressure while another benchmark ran, not a runner crash. The runner writes results only at the end and has no resume, so no call from run1 or run2 was used or cited. They are archived, not deleted.

### What this result does not show

- Anything about the tool-using flow, the conditional load of `safety-procedures.md` (the lean arm deliberately omits it) or the post-diagnosis review.
- Generalization: truth for real cases is the merged fix, not independent human adjudication; the labeler, second mapper and judge are models from one host and one judge family; three repetitions.
- Absence of a loss on authored cases (see the synthetic-only row).
