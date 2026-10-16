# generator-human-eval-v1 — blinded human review of generated Playwright specs

Status: **PREREGISTERED_BEFORE_ANY_ARTIFACT_WAS_READ. Descriptive human check, not a statistical test.**

Written 2026-10-16. **Revision r2 (2026-10-16, same day):** tool requirements were added by the coordinator after r1 was frozen and r1 sampling had been run, but before any pack was built, any artifact content was read, or any rating existed. Changes: three practice pairs (excluded from analysis), a scenario checklist and neutral count facts shown to the reviewer, rubric anchors, a required one-line reason for "cannot tell", and an explicit no-hints rule for the tool. The r1 hashes and r1 sample hash are kept in `freeze.json` under `revisions`; the 24 analysed pairs are byte-identical to the r1 sample. **Revision r5 (same day, before any rating existed; UI language only):** the reviewer tool shows every guidance text, the five rubric definitions and 1/3/5 anchors, and the per-pair task description and scenario checklist in Korean by default, with a toggle to the English original. The English texts (task sentences from `generator-skill-effect-v3/truth/<id>.json`, scenario lines from the approved plans, rubric table above) are the source of record; the Korean text is a translation produced once per task (six tasks), never from reading any generated artifact, and is identical for both sides of every pair. Backticked identifiers, selectors, UI labels and test names are not translated, and the build refuses a translation whose backticked spans or numbers differ from the source. The translation was checked against the English with `gyojeong check` and the source hash is bound (`translations_ko.json`, `translation_check.json`). No scoring rule, rubric meaning, sample or pair order changed. **Revision r4 (same day, before any rating existed):** reviewer burden was judged too high, so the review is split into two stages, a quick input mode was added, and the reading rules were rewritten so that stage 1 alone supports the primary verdict. Pair composition, pair ids, presentation order, positions and seed are unchanged (the sample and its hash are untouched; only the pack digest changes because each pair now carries its stage). Details are in the sections *Stages*, *Quick mode* and *Statistics*. **Revision r3 (same day):** the pack leak scan (aggregate counts only) found one remaining `plan.md` token in the shown code that the header rule did not remove. The anonymiser rule was extended to also drop whole-line `//` comments that name `plan.md` or `seed.spec`; the line itself was not read, and the rescan reports zero identifying tokens. No rating existed. The 24+3 sampled pairs are unchanged; only the pack digest changed. Nothing below was chosen after looking at the content of a generated spec or a human rating. The only data read before this file was frozen are cell *metadata* from the finished thin-eval r3 campaign (cell counts, arm names, `deliverable`, `as_treated`, `fidelity_class`, `spec_files` lengths).

## Question

The thin-eval r3 screen compared the generator arms with five automated quality metrics (`selector_hygiene`, `clean_conditional_survival`, `refactor_score`, `clean`, `effective_fault_kill`). Those metrics are proxies: scanner and mutant based, never read by a person. This check asks one narrower thing: **when a developer reads a generated spec from the CLI-first arm next to one from the official-agent arm, do they judge it worse?** It does not replace the automated screen and cannot make it a statistical equivalence claim.

## Source and arms

- Source: finished thin-eval r3 results, models `gpt-6-sol` and `gpt-6-astra`, six tasks (`v2-06 v2-22 v2-23 v3-04 v3-06 v3-09`), four repetitions per arm. Results directory `~/.cache/e2e-skills-bench/thin-eval-v1-r3`, bound by `generator-thin-eval-v1/freeze.json`.
- Arm A = `official-generator` (official Playwright generator agent via MCP).
- Arm F = `cli-first+thin-rules`. Arm G = `cli-first+thin-rules+scanner`.
- Pairs: **AF** (A vs F) is primary; **AG** (A vs G) is secondary. D and E are not sampled.

## Sample

- Strata: model (2) × task (6) = 12.
- Eligible cell (all must hold, read from `results.json`): `deliverable` true, `as_treated` true, `infra_failed` false, `aborted` false, `spec_files` non-empty, `fidelity_class` equals `official-tool` for A and `cli-observed` for F and G.
- Per stratum, with `random.Random(f"{seed}|{model}|{task}|{arm}")` (seed `20261016`) over the eligible repetitions sorted by name: draw **two distinct A cells** (first for the AF pair, second for the AG pair), **one F cell**, **one G cell**. If a stratum has fewer than two eligible A cells, the AG pair reuses the AF cell and the report states it. If a stratum has no eligible F or G cell, that pair is omitted and counted.
- Total analysed: **24 pairs (12 AF + 12 AG), 48 artifacts**, 12 per stratum×comparison.
- **Practice (r2):** three extra AF pairs `X1–X3`, shown first, drawn with `random.Random(f"{seed}|practice")` from distinct tasks, using only A and F cells that are not in any of the 24 analysed pairs. Purpose: let the reviewer calibrate the 1–5 anchors. Practice ratings are exported but **never analysed**, and no feedback is given on them. Each A artifact is used in at most one pair.
- Left/right position of the two artifacts in each pair is drawn from `random.Random(f"{seed}|position|{pair_id}")`; presentation order of all 24 pairs from `random.Random(f"{seed}|order")`.
- The sampling scripts and the sampling output hash are bound in `freeze.json` before any rating.

## What the reviewer sees

- The task sentence of the case (one of the six `task` texts, identical for both artifacts) and, identically for both sides, the **scenario checklist**: the "Expected Results" lines of the approved plan every arm received (`generator-official-pilot-v1/plans/<task>/plan.md`).
- The generated spec files (the `spec_files` list), concatenated under neutral headings `File 1..n`, original file names hidden, `// spec:` and `// seed:` header comment lines removed, and any whole-line `//` comment that names `plan.md` or `seed.spec` removed (r3). Nothing else: no scanner output, no test results, no metrics, no model or arm name.
- Per side, the same four **neutral counts**, computed by one rule for every artifact: lines of the shown code, non-blank lines, `test(`/`it(` calls (not `describe`, `step`, `use`), and `expect(` calls (including `.soft` and `.poll`). They are labelled as not a quality indicator.
- A collapsible rubric table with a one-line definition and generic 1/3/5 anchors per criterion (examples of the criterion, not of any artifact). Open by default on practice pairs.
- Side-by-side code with line numbers and per-file fold/unfold. **Not included:** diff or similarity highlighting, recommendations, default selections, colouring or ordering that favours a side. Every choice is made by the reviewer.
- **Hidden until all ratings are exported:** arm, model, scanner result, mutant kill, pass/fail, refactor score, and every other automated metric. They are not in the tool file at all; they exist only in the key and in `results.json`.
- The reviewer judges **the code as written**. Whether it ran and whether it kills mutants is already covered by the automated metrics and is not rated here.

## Rubric

Each artifact, 1–5 (5 best), with "cannot tell" allowed per criterion:

| Criterion | Definition | 1 | 3 | 5 |
|---|---|---|---|---|
| Scenario coverage | each listed behaviour tested at least once | most listed behaviours untested | about half tested; some behaviour (e.g. persistence across reload) missing | every behaviour verified at least once |
| Assertion meaning | assertions check the promised outcome or state | only checks that elements are visible; promised values, states or texts not asserted | some steps assert the outcome, some only existence | each key step asserts the promised value, state or text |
| Locator robustness | roles, labels, accessible names over position or structure | mostly position, order or CSS-structure selectors | role/label selectors mixed with structural ones | almost all located by role, label or accessible name |
| Readability and style | naming, structure, length | unclear names; long tests that are hard to follow | readable, but repetition or vague names stand out | names state intent; consistent structure; reads in one pass |
| Economy | no redundant, duplicated or dead code (5 = nothing to remove) | much duplication, dead code or needless waits/helpers | a few places could be shortened | almost nothing to remove |

The anchors are generic descriptions written before any artifact was read. Each criterion also allows "?" (cannot tell).

Per pair: **overall preference** = left / right / tie / cannot tell. Choosing "cannot tell" requires a one-line reason (stored as `cannot_reason`). An optional free-text note is also stored. After rating a pair the reviewer also guesses **which side is the official-agent artifact** (left / right / no idea), recorded as a blinding diagnostic.

## Stages (r4)

- **Stage 1** = the three practice pairs + the 12 AF pairs. It supports the primary verdict (P1) by itself.
- **Stage 2** = the 12 AG pairs. Optional. The owner may skip it; it may be handed to another reviewer. Nothing in stage 1 changes if stage 2 is never done.
- Pair ids, relative order and left/right positions are the ones drawn in r1; a stage only filters them. The stage label of a pair is stored in the pack. It tells a reviewer which pairs belong to the secondary comparison but not which side is which arm.
- A reviewer who rates only stage 1 has a complete primary result. Reports state which stages each reviewer completed.

## Quick mode (r4)

- Default input mode for analysed pairs is **quick**; **full** (all five criteria and the "which is official" guess required, as in r1–r3) is available per pair. Practice pairs default to full so the reviewer calibrates the anchors on all five criteria. The mode used is recorded per pair.
- In quick mode the required inputs are: overall preference (left / right / tie / cannot tell, with the one-line reason for cannot tell) and the 1–5 (or "?") scores on **three criteria: scenario coverage (c1), assertion meaning (c2), readability and style (c4)**, for both sides. Locator robustness (c3), economy (c5) and the "which is official" guess are optional.
- **Why these three, decided before any artifact was read, from the metric definitions only:** c1 and c2 ask whether the spec tests what the task promised, which is the claim under check, and no scanner or mutant metric rates the match to the scenario list directly. c4 is the dimension none of the automated metrics touches. c3 overlaps the automated `selector_hygiene` and c5 overlaps scanner findings and `clean`, so they are the ones that can be optional at the least cost to what a human adds.
- Optional criteria that were left empty are simply missing for that pair; they are not counted as "?" or as a score.
- The tool shows remaining pairs, an estimate of remaining minutes (an assumed 2.5 min per quick pair and 4 min per full pair until the reviewer has three timed pairs, then that reviewer's own average), and a break suggestion after every 8 completed analysed pairs. Progress is autosaved.

## Statistics (all descriptive)

Let a "decisive" pair be one whose preference is left or right.

- **P1 (primary, AF):** share of AF pairs in which F is *not worse than* A, i.e. (F preferred + tie) / (all AF pairs with a recorded preference, "cannot tell" excluded). Report with a Clopper–Pearson 95% interval. Also report F-preferred, tie, A-preferred counts.
- **P2 (secondary, AG):** the same for G vs A, **only if stage 2 was completed**. If stage 2 was rated by a different reviewer than stage 1, P2 is reported under that reviewer's id and is not pooled with P1; no statement about G is made from stage 1 alone.
- **Rubric differences:** for each criterion (n varies, because c3 and c5 can be missing in quick mode), mean of (F − A) and (G − A) over pairs, with the number of pairs; per-model and per-task tables as listings, not tests. A criterion with fewer than 6 scored pairs is listed as thin and is not used for the concern flag below.
- **Concordance with automated metrics:** for each decisive pair, the automated direction is the sign of the mean of the pair's `effective_fault_kill` difference and `refactor_score` difference (cell-level values from `results.json`); pairs with zero or missing automated difference are skipped. Report agreements / compared pairs with a Clopper–Pearson interval.
- **Inter-rater agreement** (only on pairs both reviewers completed; for AF this needs a second reviewer who also did stage 1): quadratic-weighted kappa per rubric criterion, Cohen's kappa on the preference (left/right/tie), percent agreement. If any kappa is below 0.40 the human results are read as reviewer-specific.
- **Blinding check** (guess answers exist for full-mode pairs and any quick-mode pair where the reviewer chose to answer; report the number answered): share of "which is official" guesses that are correct among non-"no idea" answers, with an interval, plus the median line-count ratio of the two sides. A correct share above 0.70 means blinding largely failed and the preference is read with that caveat.

## Reading rules (set before any data)

- Say "no human-judged quality loss seen" only if P1's interval lower bound is at least 0.5 **and** no rubric criterion with at least 6 scored pairs has a mean (F−A) of −0.5 or lower. These rules need only stage 1 (P1 is defined on the AF pairs). Otherwise say the check did not show F is as good as A and name what was seen.
- If P1's lower bound is below 0.5 but the point estimate is at least 0.5, that is "no loss detected, undersized"; this is the expected outcome of 12 pairs and is not a pass.
- A mean (F−A) of −0.5 or lower on any criterion with at least 6 scored pairs, or F preferred in at most a third of the decisive AF pairs, is a *concern flag*, reported as such even if P1 passes.
- Disagreement with the automated metrics (concordance interval entirely below 0.5) is reported as disagreement; neither source is declared right.
- No result from this check moves the automated thresholds, the ship decision rule, or any frozen file.

## Exclusions and invalid runs

- Cells failing eligibility are not sampled. Eligibility is fixed above and read from metadata.
- A reviewer who sees an arm name, model name, scanner output, or an `// spec:` header in the pack must record it; the pair is excluded from analysis and the leak is listed. Pack building runs a leak scan (arm, model, tool, scanner and plan vocabulary) and reports the aggregate counts to the owner; the pack is rebuilt and the sample hash recomputed only if the scan finds identifying tokens that the header-stripping rule did not remove, and the rebuild is recorded as a protocol revision before any rating exists.
- The tool records time per pair automatically (visible-tab milliseconds) and autosaves to the reviewer's browser; the exported JSON is the record.
- Ratings are collected once. A reviewer who has seen a pair's key cannot rate it again.

## Limits (stated up front)

- **Reviewer = developer of the skill (or close to it).** Expectation and familiarity bias cannot be removed by blinding; the guess-which-is-official diagnostic measures part of it. A reviewer who did not build the skill is better and the tooling supports a second reviewer.
- **12 pairs per comparison** is too few for any equivalence claim. Intervals will be wide.
- **Blinding is imperfect:** official-agent outputs tend to split a flow into more files and more lines than CLI-first outputs, and scanner-gated outputs may carry `// JUSTIFIED:` markers. Line counts and file counts are recorded and reported.
- **Code only:** execution, mutation kill and scanner results are not shown, so a spec that reads well but fails would score well here; the automated metrics are the guard for that.
- **Two Codex models, six synthetic tasks:** the same scope limit as thin-eval r3. This check does not generalise beyond it.
- A human preference for one artifact is not evidence that its generator is better; it is only a check that the cheaper path was not judged worse on this sample.

## Files

`translations_ko.json` (English sources and Korean translations of tasks, scenarios and rubric), `translation_check.json` (gyojeong results), `select_sample.py` (sampling), `build_pack.py` (anonymising and tool build), `tool_template.html` (single-file reviewer tool), `analyze.py` (analysis), `selftest.py` (synthetic end-to-end test; no real key). `freeze.json` binds the SHA-256 of all of these, of the thin-eval r3 `results.json` for both models, and (after sampling) of the sample key. The mapping key lives outside the repository in `~/.cache/e2e-skills-bench/human-eval-v1/key/` and is not opened until all ratings are exported.
