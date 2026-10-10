# Debugger skill-effect v3: does the F1/F14/F11/F7 tie-break help? (2026-10-05)

Status: **`FAIL` on the preregistered primary rule; the secondary F-code result moves in the hypothesised direction.** On 28 fresh real Playwright and Cypress failures whose merged upstream fix is the ground truth, Claude `claude-sonnet-5-5` named the maintainers' root-cause mechanism in **81.0%** of calls with the Stage 2 skill text, **79.8%** with the release 2.0.0 skill text, and **86.9%** with a taxonomy-free prompt. The primary paired lift, new minus old strict match, is **+0.012** (95% CI 0.000 to +0.036): no measurable lift in root-cause identification. On the 23 cases with a blind-agreed F-code label, F-code exact match rose from **0.638 to 0.812** (+0.174, paired 95% CI 0.000 to +0.362; better on 9 cases, worse on 2, tied on 12), and two blind mappers using the new tables agreed on **23/28** real fixes against **15/26** in v2 with the 2.0.0 tables. All 252 model calls and 28 judge calls completed with no infrastructure error, retry, or invalid output. The staged plan behind this run is in [`stage1-findings.md`](stage1-findings.md) (why v2 found no lift) and [`hypothesis.md`](hypothesis.md) (written before the skill edits).

## What was tested

Stage 2 made the smallest edits to both debugger skills that address the v2 findings: sharper F1, F5, F11 and F14 signal cells; one `F1 / F14 / F11 / F7 tie-break` paragraph in `SKILL.md` and `references/classification-procedure.md`; and a Root Cause line rule (trigger, mechanism, effect, not a timeline or a category restatement). F-code numbers, titles and order are unchanged. During the run a contract test (`assert_f1_f14_f11_f7_tiebreak_contract`) pinned the new text; it failed on the 2.0.0 text and passed on the new one. The prompt surface grew from 43.3 KB to 46.6 KB (+7.6%). **The tested text is not shipped in 2.0.0**: after the primary `FAIL`, both debugger skills keep the `ed9489c` text and that contract test is not in CI; the wording survives only in the snapshot below. The two texts are frozen in [`skill-snapshots/old`](skill-snapshots/old/) (git `ed9489c`) and [`skill-snapshots/new`](skill-snapshots/new/), and their digests are in [`protocol.json`](protocol.json).

| Arm | Prompt material |
| --- | --- |
| `new` | frame + Stage 2 skill text (five files per framework, from `skill-snapshots/new`) + excerpt; 7-field F-code schema |
| `old` | frame + release 2.0.0 skill text (from `skill-snapshots/old`) + excerpt; same schema |
| `free` | taxonomy-free "diagnose the root cause and propose the fix"; 3-field schema |

A tool-enabled workflow arm was not run: it needs each of the 19 source repositories (counted from `corpus.json`; the "17 merged fixes / 15 repositories" figures elsewhere in this file and in `protocol.json` do not match the corpus's 19 repositories and 21 pull-request URLs) checked out at the failing commit with its artifacts plus tool-enabled calls per case, which is neither cheap nor reproducible from this checkout. The zero-tool arms measure interpretation of the skill text only.

## Corpus: 28 fresh real failures from 17 merged fixes

Read-only GitHub search (`gh search`, `gh pr view/diff`, `gh issue view`, `gh run view --log-failed`) over merged flaky-test fixes and closed failure issues in MIT or Apache-2.0 repositories, screened from 811 hits to 122 permissive-license candidates and then by hand. None of the 28 cases is in v1 or v2; three come from PRs whose other sub-cases v2 used (OpenMetadata #31063, a different ChurchCRM PR, Altinn). 14 Playwright, 14 Cypress; the maintainers attributed 5 to the product. Two artifacts carry a verbatim raw excerpt of the failed GitHub Actions job log (`pw-13` cloudlands-fe Playwright failure block, `cy-01` ChurchCRM Cypress results table); the other runs had expired or logged only summaries. Sources, licenses, merge dates and the construction rule are in [`corpus.json`](corpus.json); artifacts hold observations only ([`cases/`](cases/)), the maintainers' explanation and fix are held back ([`truth/`](truth/)).

**F-code labels.** Two blind mappers (Claude Opus, Claude Sonnet; fresh contexts) saw only each case's explanation and fix plus the **new** skill tables and procedure. They agreed on 23 of 28 (8 of 56 judgments marked "forced"); the 5 disputes were F1/F14 (`pw-13`), F14/F11 (`pw-10`), F15/F14 (`cy-02`), F10/F11 (`cy-03`), F15/F11 (`cy-09`). Ledger in [`blind-labels/`](blind-labels/). In v2, with the 2.0.0 tables, the same two mapper roles agreed on 15 of 26 and 14 of 52 judgments were forced. Different corpora, so this is a descriptive comparison, not a controlled one.

## Protocol

[`protocol.json`](protocol.json) was frozen after the labels were filled and before the first scored call: arms, judge, decision rule, and SHA-256 digests of the corpus, every artifact and truth file, all ten snapshot files per arm, the prompt frames and the schemas. Three repetitions per case and arm in one seeded shuffle (252 calls), timeout 240 s, one infrastructure retry. Judge: Codex `gpt-6-sol` (codex-cli 0.159.3), per case all nine root-cause statements in shuffled order under letter ids, blind to arm, 2/1/0 rubric, schema-enforced. Decision rule: primary new minus old strict match, `PASS` when lift ≥ +0.10, framework-stratified case-cluster bootstrap 95% CI lower bound > 0, and new diagnosis accuracy no more than 0.05 below old. Power stated before running: with v2's observed per-case SD of about 0.20 the MDE is about 0.11; with the prior assumption of 0.35 about 0.19; `FAIL` was named as the likely outcome even if the wording helps a little, because the coded arms already sat near 0.8–0.9.

## Results

| Metric | `new` | `old` | `free` |
| --- | ---: | ---: | ---: |
| Strict match with the maintainers' mechanism (score 2) | 0.810 | 0.798 | 0.869 |
| Lenient match (score 1 or 2) | 1.000 | 1.000 | 1.000 |
| Product-versus-test diagnosis matches the maintainers | 0.857 | 0.821 | 0.798 |
| F-code exact match, 23 blind-agreed labels | **0.812** | 0.638 | n/a |
| Total input tokens (cache included), 84 calls | 2,893,220 | 2,755,586 | 301,467 |
| Output tokens | 55,595 | 57,305 | 32,616 |
| Summed call time | 762.2 s | 815.4 s | 581.7 s |

| Paired comparison | Lift | 95% CI | Cases better / worse / tied |
| --- | ---: | --- | --- |
| new − old, strict match (primary) | +0.012 | 0.000 to +0.036 | 1 / 0 / 27 |
| new − old, F-code exact (23 labeled) | +0.174 | 0.000 to +0.362 | 9 / 2 / 12 |
| new − free, strict match | −0.060 | −0.131 to 0.000 | 0 / 3 / 25 |
| old − free, strict match | −0.071 | −0.143 to 0.000 | 0 / 3 / 25 |

Decision: **`FAIL`** (`lift_at_least_min` false, `ci_lower_above_zero` false, `diagnosis_not_worse` true). The judge used 350,533 input tokens over 729.3 s.

### Per case

Judge scores are the three repetitions in schedule order; F-codes are the three `new` and `old` answers; the last column is diagnosis accuracy new/old/free.

| Case | Repository | F-code label | new | old | free | new F-codes | old F-codes | diag n/o/f |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pw-01` | GeoLibre | F7 | 1,1,1 | 1,1,1 | 1,1,1 | F7/F7/F7 | F7/F7/F1 | 0.67/0.00/1.00 |
| `pw-02` | stylebot | F7 | 2,2,2 | 2,2,2 | 2,2,2 | F7/F7/F7 | F7/F7/F7 | 1/1/1 |
| `pw-03` | jot | F14 | 1,1,1 | 1,1,1 | 1,1,1 | F14/F14/F14 | F14/F14/F14 | 0/0/0 |
| `pw-04` | staging-studio | F2 | 1,1,1 | 1,1,1 | 1,1,1 | F2/F2/F2 | F2/F2/F2 | 1.00/1.00/0.33 |
| `pw-05` | ludus | F2 | 2,2,2 | 2,2,2 | 2,2,2 | F2/F14/F14 | F2/F2/F2 | 1.00/1.00/0.00 |
| `pw-06` | ludus | F15 | 2,2,2 | 2,2,2 | 2,2,2 | F15/F15/F15 | F15/F15/F15 | 1/1/1 |
| `pw-07` | Shohoj | F3 | 1,1,1 | 1,1,1 | 1,2,2 | F3/F3/F3 | F3/F3/F3 | 1/1/1 |
| `pw-08` | arcadePlatform | F11 | 2,2,2 | 2,2,2 | 2,2,2 | F11/F1/F11 | F1/F1/F1 | 1/1/1 |
| `pw-09` | arcadePlatform | F1 | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F1/F1/F14 | 1/1/1 |
| `pw-10` | actual | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F5/F5/F5 | 1/1/1 |
| `pw-11` | Raid-Ledger | F14 | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F15/F15/F15 | 0/0/0 |
| `pw-12` | datahub | F14 | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F1/F1/F1 | 1/1/1 |
| `pw-13` | cloudlands-fe | disputed | 1,2,2 | 1,2,1 | 2,2,2 | F1/F1/F1 | F1/F1/F1 | 1/1/1 |
| `pw-14` | OpenMetadata | F14 | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F14/F14/F14 | 1/1/1 |
| `cy-01` | ChurchCRM | F14 | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F14/F14/F14 | 1/1/1 |
| `cy-02` | ChurchCRM | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F15 | F15/F15/F15 | 1/1/1 |
| `cy-03` | recetas-ia | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F10/F10/F10 | F10/F10/F10 | 0.33/0.67/0.67 |
| `cy-04` | gbstem/portal | F15 | 2,2,2 | 2,2,2 | 2,2,2 | F15/F15/F15 | F15/F15/F15 | 1/1/1 |
| `cy-05` | frappe/release_tests | F2 | 2,2,2 | 2,2,2 | 2,2,2 | F2/F2/F2 | F12/F8/F14 | 1/1/1 |
| `cy-06` | frappe/release_tests | F11 | 2,2,2 | 2,2,2 | 2,2,2 | F11/F11/F11 | F3/F11/F11 | 1/1/1 |
| `cy-07` | frappe/release_tests | F2 | 2,2,2 | 2,2,2 | 2,2,2 | F12/F12/F2 | F12/F12/F12 | 1/1/1 |
| `cy-08` | frappe/release_tests | F2 | 1,1,1 | 1,1,1 | 1,2,2 | F2/F2/F2 | F2/F2/F2 | 1/1/1 |
| `cy-09` | ReactiveTraderCloudClone | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F15/F15/F15 | F15/F15/F15 | 1/1/1 |
| `cy-10` | ReactiveTraderCloudClone | F11 | 2,2,2 | 2,2,2 | 2,2,2 | F11/F11/F11 | F11/F11/F11 | 1/1/1 |
| `cy-11` | odh-dashboard | F4 | 2,2,2 | 2,2,2 | 2,2,2 | F7/F7/F7 | F9/F9/F9 | 1/1/1 |
| `cy-12` | altinn-studio | F11 | 2,2,2 | 2,2,2 | 2,2,2 | F11/F14/F14 | F1/F1/F1 | 0/0/0 |
| `cy-13` | altinn-studio | F11 | 2,2,2 | 2,2,2 | 2,2,2 | F11/F11/F11 | F11/F11/F11 | 1/1/1 |
| `cy-14` | altinn-studio | F1 | 2,2,2 | 2,2,2 | 2,2,2 | F1/F1/F1 | F1/F1/F3 | 1.00/0.33/0.33 |

Twenty-five cases had identical strict judge scores across all three arms. `pw-07` (http.server backlog) and `cy-08` (grid-add-row appends a second row) were scored 1 for both coded arms and 2 twice for the free arm; `pw-13` (reduced-motion `scrollbar-color` transitions) was a mixed 1/2 in all arms. Four cases scored 1 in every arm (`pw-01` wedged renderer, `pw-03` Headless UI menu left mounted, `pw-04` two file inputs plus hidden-input race, and `pw-07`), because no arm named the specific mechanism the maintainers found (the SwiftShader renderer left alive by the disposed context, the interrupted-transition path that never unmounts, the production-build `setInputFiles` on a hidden input, the HTTP/1.0 listen backlog of 5). Diagnosis attribution failed in every arm for the three product-side cases where the test code also changed (`pw-03`, `pw-11`, `cy-12`): the models called them test defects.

Where the new text changed the F-code: `pw-08` (old F1 → new F11, label F11), `pw-12` (F1 → F14, label F14), `pw-11` (F15 → F14, label F14), `cy-05` (F12/F8/F14 → F2, label F2), `cy-06` (F3 → F11, label F11), `cy-12` (F1 → F11/F14, label F11), `cy-14` (one F3 → F1, label F1), `pw-01` (one F1 → F7, label F7), `cy-07` (one F12 → F2). It also moved `pw-09` the wrong way (label F1; old F1/F1/F14, new F14/F14/F14: a fixed 300 ms sleep before sampling a fullscreenchange-driven state, which the new F14 row's "value change between two reads" wording now attracts) and `pw-05` partly (label F2; two of three new answers F14 for the offscreen duplicate main that appears during route preloading). `cy-11` stayed wrong in both arms (label F4; old F9, new F7).

## What this does and does not support

It supports: the Stage 2 tie-break made the model's F-code choices agree more often with blind mappers reading the same contract (0.638 → 0.812 exact match on agreed labels; 9 cases better, 2 worse) and made the contract itself less ambiguous for independent readers (23/28 agreement against 15/26), without lowering diagnosis attribution (0.821 → 0.857) or lenient match (1.000 in all arms). It does not support the primary hypothesis: on these real cases the new wording did not change how often the model named the maintainers' mechanism (+0.012), and the taxonomy-free arm remained descriptively best at that task while using about a tenth of the input tokens, as in v2. The Root Cause shape rule therefore shows no measurable effect at this sample size, and the F-code gain is a classification-consistency gain, not evidence of better diagnosis.

Limits: one host, three repetitions, 28 search-selected public cases that over-represent timing and isolation causes; the author selected and redacted the artifacts (auditable through the source URLs) and most non-raw-log artifacts carry the observations the maintainers needed, so the coded arms had little room to add anything; several source PR descriptions were AI-assisted and the truth is the merged fix, not an independent human adjudication; the judge is a model; the F-code secondary CI touches zero and the mapper-agreement comparison is across different corpora. Stage 2 also added about 3 KB to each `SKILL.md`, a cost without a measured diagnosis benefit. The v1 and v2 `protocol.json` files pin the 2.0.0 skill digests, so their runners now refuse a rerun on the edited tree by design; the measured text is recoverable at `ed9489c` and in `skill-snapshots/old`. No further skill text was changed after this run.

## Reproduce

```bash
python3 scripts/evals/run-debugger-skill-effect-v3.py run --runner claude --model sonnet \
  --runner-path /absolute/path/to/claude --output /absolute/path/model.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v3.py judge /absolute/path/model.json --runner codex \
  --model gpt-6-sol --runner-path /absolute/path/to/codex --output /absolute/path/judged.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v3.py analyze /absolute/path/judged.json \
  --output /absolute/path/results.json
```

Both live stages refuse to overwrite an existing report and refuse to start on any frozen-digest drift. The two raw-log artifacts (`pw-13`, `cy-01`) had the GitHub Actions runner account's home path (`/home/<gha-runner>/`, where the account is GitHub's default runner user) replaced with `/home/user/` after the run because the repository's security gate treats it like an account path; [`post-run-normalization.json`](post-run-normalization.json) records both digests, `protocol.json` keeps the pre-normalization digests the model saw, and the one-line restore command there makes the frozen digests match again for a rerun. After the run, account-name path components in provenance fields were replaced with `/Users/user/` and the judge report's model-report digest recomputed (the pre-normalization digest is kept alongside); the results file re-derives identically.

## Files

- [`stage1-findings.md`](stage1-findings.md), [`hypothesis.md`](hypothesis.md): the read-only v2 analysis and the pre-edit hypotheses.
- [`protocol.json`](protocol.json), [`corpus.json`](corpus.json), [`cases/`](cases/), [`truth/`](truth/), [`blind-labels/`](blind-labels/), [`skill-snapshots/`](skill-snapshots/).
- [`reports/claude-sonnet.json`](reports/claude-sonnet.json), [`reports/claude-sonnet-judged-by-codex-sol.json`](reports/claude-sonnet-judged-by-codex-sol.json), [`reports/claude-sonnet-results.json`](reports/claude-sonnet-results.json).

## Freeze evidence note (added after review)

The `registered_utc` field in `protocol.json` is not reliable: it was typed by hand and does not match the real first scored call (it is later than that call, and for v2 and v3 later than the actual clock time). `protocol.json` is frozen, so it is left as is. The freeze is established only by the pinned SHA-256 digests (`frozen_digests` equal the `input_digests_before` recorded in every report) and by file modification times; no git commit predates the first call.
