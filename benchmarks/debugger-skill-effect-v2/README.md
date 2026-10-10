# Debugger skill-effect v2: real fixes, taxonomy-free baseline (2026-10-05)

Status: **`FAIL` under the preregistered rule; public development evidence.** On 26 real public Playwright and Cypress failures whose merged upstream fix is the ground truth, Claude `claude-sonnet-5-5` identified the maintainers' root-cause mechanism in **87.2%** of calls with the debugger skill text, **83.3%** with the F-code legend only, and **89.7%** with a taxonomy-free "diagnose the root cause" prompt. The primary paired lift, skill minus taxonomy-free, is **−0.026** (95% CI −0.090 to +0.026): no lift. Skill minus legend is +0.038 (0.000 to +0.077). All 234 model calls and all 26 blind judge calls completed with no infrastructure error, retry, or invalid output.

[v1](../debugger-skill-effect-v1/README.md) had two weaknesses: a model-authored corpus with model-authored labels, and a legend-only baseline. V2 replaces both. The cases are real, the truth is the fix the maintainers merged, the primary baseline receives no taxonomy at all, and the grader is a model from the other family that never sees which arm produced a statement. V1 stays as recorded; v2 asks a different question on a different corpus. The follow-up [v3](../debugger-skill-effect-v3/README.md) tested a tie-break wording motivated by this run on 28 further real fixes.

## Question and arms

Does the debugger skill text help a zero-tool model name the mechanism that the maintainers found and fixed, compared with the same model given no taxonomy, and compared with the legend only?

| Arm | Prompt material | Output |
| --- | --- | --- |
| `skill` | frame + full debugger skill text (`SKILL.md` and four references, about 43 KB) + excerpt | 7-field JSON with F-code and `root_cause` |
| `legend` | frame + 15-line F-code legend parsed from `SKILL.md` + excerpt | same 7-field JSON |
| `free` | "Decide whether the product or the test is at fault, state the root cause, and propose the fix" + excerpt; no taxonomy | 3-field JSON: `diagnosis`, `root_cause`, `fix` |

Every call is prompt-complete with every model tool disabled, no user settings, no session persistence, schema-enforced output, and the shared holdout runner's environment allowlist and credential staging.

## Corpus: 26 real failures from 12 merged fixes

Sources were found with read-only GitHub search for merged flaky-test fixes and closed failure issues with a linked fix, in MIT or Apache-2.0 repositories only: OpenMetadata (13 cases from four PRs), parisek/styleguide, ExaDev/agent-comms, Agent-Clubhouse/Goobers, anonhym/latelier, datahub, ChurchCRM (2), bloom-housing, trento-project/web, concord-consortium/davai-plugin, LuxTronic/cvat (2), and opensearch-project/dashboards-observability. 18 cases are Playwright and 8 Cypress; the maintainers attributed 2 to the product and 24 to the test. Every case records its source URLs, license, and merge date in [`corpus.json`](corpus.json).

Each [`cases/*.json`](cases/) artifact holds only observations: the test identifier, the failure text as reported, the pre-fix test code from the merged diff's removed lines, the attempt or frequency pattern, and environment, DOM, or network facts. The maintainers' causal explanation and the fix are held back in [`truth/*.json`](truth/). The construction rule is recorded in `corpus.json`; where a report-style detail is not verbatim from the source, it restates a fact the maintainers reported, and the source URLs allow an audit of every case.

**F-code labels.** Two blind mappers (Claude Opus and Claude Sonnet in fresh contexts) saw only each case's explanation and fix plus the two F-code tables and mapped each to an F-code. They agreed on **15 of 26**; 11 cases are disputed and carry no F-code label. Eight of the eleven disputes are F1 against F14 or F11 (timing against animation or ordering), and 14 of the 52 mapping judgments were marked "forced", meaning no code fit well. The ledger is in [`blind-labels/`](blind-labels/). The F-code metric uses the 15 agreed cases only; the primary metric does not depend on F-codes.

## Protocol

[`protocol.json`](protocol.json) was frozen before the first scored call: hypothesis, arms, judge, decision rule, and SHA-256 digests of the corpus, every artifact and truth file, the ten skill files, both legends, all prompt frames, and all schemas. Three repetitions per case and arm in one seeded shuffle (234 calls), timeout 240 s, one retry for infrastructure failure only.

**Judge.** Codex `gpt-6-sol` (codex-cli 0.159.3) received, per case, the maintainers' explanation, fix, and side, plus all nine root-cause statements in shuffled order under letter ids, and scored each: 2 = same mechanism, 1 = right family but not the mechanism, 0 = different or vague. It never saw the arm, the model, or any F-code. Output was schema-enforced.

**Decision rule.** Primary metric: strict match (score 2) per call, mean per case, paired per-case difference skill minus free. `PASS` when the lift is at least +0.10, the framework-stratified case-cluster bootstrap 95% CI lower bound is above 0, and skill diagnosis accuracy is no more than 0.05 below free. Power was stated before running: with 26 cases and an assumed paired SD of 0.35, the minimum detectable effect is about 0.20, so a true +0.10 can be missed.

## Results

| Metric | `skill` | `legend` | `free` |
| --- | ---: | ---: | ---: |
| Strict match with the maintainers' mechanism (score 2) | 0.872 | 0.833 | 0.897 |
| Lenient match (score 1 or 2) | 1.000 | 1.000 | 1.000 |
| Product-versus-test diagnosis matches the maintainers | 1.000 | 1.000 | 1.000 |
| F-code exact match, 15 blind-agreed labels | 0.733 | 0.778 | n/a |
| Total input tokens (cache included), 78 calls | 2,581,964 | 357,265 | 248,558 |
| Output tokens | 55,175 | 32,627 | 26,641 |
| Summed call time | 757.5 s | 596.7 s | 526.3 s |

| Paired comparison (strict match) | Lift | 95% CI | Cases better / worse / tied |
| --- | ---: | --- | --- |
| skill − free (primary) | −0.026 | −0.090 to +0.026 | 1 / 2 / 23 |
| skill − legend | +0.038 | 0.000 to +0.077 | 3 / 0 / 23 |
| legend − free | −0.064 | −0.141 to 0.000 | 0 / 3 / 23 |

Decision: **`FAIL`** (`lift_at_least_min` false, `ci_lower_above_zero` false, `diagnosis_not_worse` true). The judge used 324,118 input tokens over 782.7 s.

### Per case

Judge scores are the three repetitions in schedule order; F-codes are the three skill and legend answers.

| Case | Repository | F-code label | skill | legend | free | skill F-codes | legend F-codes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `pw-01` | OpenMetadata | F14 | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F14/F14/F14 |
| `pw-02` | OpenMetadata | disputed | 1,1,2 | 1,1,1 | 1,2,2 | F14/F14/F14 | F14/F14/F14 |
| `pw-03` | OpenMetadata | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F1/F14/F1 | F1/F1/F11 |
| `pw-04` | OpenMetadata | F11 | 2,1,1 | 1,1,1 | 1,1,1 | F11/F11/F11 | F11/F11/F11 |
| `pw-05` | OpenMetadata | F3 | 2,2,2 | 2,2,2 | 2,2,2 | F7/F7/F7 | F7/F11/F7 |
| `pw-06` | OpenMetadata | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F11/F11/F7 | F7/F7/F7 |
| `pw-07` | OpenMetadata | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F11/F11/F11 |
| `pw-08` | OpenMetadata | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F11/F5/F5 | F11/F11/F11 |
| `pw-09` | OpenMetadata | F14 | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F14/F14/F14 |
| `pw-10` | OpenMetadata | F3 | 2,2,2 | 2,2,2 | 2,2,2 | F7/F7/F7 | F7/F7/F7 |
| `pw-11` | OpenMetadata | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F1/F1/F6 | F10/F10/F10 |
| `pw-12` | OpenMetadata | F7 | 2,2,2 | 2,2,2 | 2,2,2 | F7/F7/F7 | F9/F7/F7 |
| `pw-13` | OpenMetadata | F1 | 2,2,2 | 1,2,2 | 2,2,2 | F14/F14/F14 | F6/F1/F1 |
| `pw-14` | parisek/styleguide | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F1/F14/F5 | F1/F1/F1 |
| `pw-15` | ExaDev/agent-comms | F7 | 1,1,1 | 1,1,1 | 1,1,1 | F7/F7/F7 | F7/F7/F7 |
| `pw-16` | Agent-Clubhouse/Goobers | F2 | 2,2,2 | 2,2,2 | 2,2,2 | F2/F2/F2 | F2/F1/F2 |
| `pw-17` | anonhym/latelier | F2 | 2,2,2 | 2,2,2 | 2,2,2 | F2/F2/F2 | F2/F2/F2 |
| `pw-18` | datahub | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F1/F1/F14 | F11/F11/F11 |
| `cy-01` | ChurchCRM | F14 | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F14/F14/F14 |
| `cy-02` | ChurchCRM | F14 | 2,2,2 | 2,2,2 | 2,2,2 | F14/F14/F14 | F14/F14/F14 |
| `cy-03` | bloom-housing | F1 | 2,2,2 | 2,2,2 | 2,2,2 | F1/F1/F1 | F1/F1/F1 |
| `cy-04` | trento-project/web | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F14/F11/F11 | F11/F11/F11 |
| `cy-05` | davai-plugin | F13 | 2,2,2 | 2,2,2 | 2,2,2 | F8/F8/F8 | F8/F13/F13 |
| `cy-06` | LuxTronic/cvat | disputed | 1,1,1 | 1,1,1 | 1,2,2 | F5/F5/F5 | F12/F2/F2 |
| `cy-07` | LuxTronic/cvat | F4 | 2,2,2 | 2,2,2 | 2,2,2 | F4/F4/F4 | F4/F4/F4 |
| `cy-08` | dashboards-observability | disputed | 2,2,2 | 2,2,2 | 2,2,2 | F1/F1/F1 | F11/F11/F11 |

Twenty-one cases were judged a full match in every call of every arm. The three cases where arms differed: `pw-02` (Observability listbox closed by auto-scroll; the judge wanted the scroll-closes-popover mechanism named, which each arm did in some repetitions), `pw-13` (virtualised filter list; one legend call blamed the wrong thing), and `cy-06` (cvat click outside a bowtie polygon; the free arm named the click-outside-the-shape mechanism twice while the coded arms described the selection being lost without the geometric cause). `pw-04` (product fetch race) and `pw-15` (parallel dashboards discovering each other) were scored 1 in nearly every call of every arm: the models named the race or the cross-worker leak but not the exact overwrite or the shared first-contact port.

## What this does and does not support

It supports: on these real cases, the model-visible debugger skill text did **not** improve root-cause identification over a taxonomy-free prompt for `claude-sonnet-5-5`; the taxonomy-free arm was descriptively best and used about a tenth of the input tokens. The skill text did not lower product-versus-test attribution, which was perfect in all arms. Relative to the legend-only arm the skill text was descriptively better by one call in each of three cases, with a CI touching zero. Separately, the blind mapping shows the F1–F15 taxonomy fits real flaky-test fixes loosely: two careful mappers disagreed on 11 of 26, and the forced-pick F-code exact match was 0.73 to 0.78 even on agreed labels, with the F1/F14/F11 boundary the main source of both.

It does not support a claim that the skill text is useless: a ceiling effect is likely. The free arm already reached 0.90 strict match, so the comparison had little room to show a lift, and the artifacts, although built from observations only, carry the report-style facts (a DOM state at the moment of failure, a request timing, an instrumented log line) that the maintainers themselves needed in order to find the cause. A corpus of raw CI logs without those facts could separate the arms differently. It also does not measure the end-to-end debugger workflow, in which the skill's value is meant to lie in acquiring and reading artifacts, running isolation probes, and verifying fixes, none of which a zero-tool prompt exercises. One host, one judge model, 26 selected cases that over-represent timing causes, author-performed redaction, and a model judge rather than human adjudication all limit generalisation. V1's positive result on synthetic lookalike cases and this negative result on real cases are both recorded; neither revises the other.

No skill text was changed in response to this run.

## Reproduce

```bash
python3 scripts/evals/run-debugger-skill-effect-v2.py run --runner claude --model sonnet \
  --runner-path /absolute/path/to/claude --output /absolute/path/model.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v2.py judge /absolute/path/model.json --runner codex \
  --model gpt-6-sol --runner-path /absolute/path/to/codex --output /absolute/path/judged.json --allow-live
python3 scripts/evals/run-debugger-skill-effect-v2.py analyze /absolute/path/judged.json \
  --output /absolute/path/results.json
```

Both live stages refuse to overwrite an existing report and refuse to start on any frozen-digest drift. Measured skill text: release 2.0.0 debuggers at `ed9489c`.

## Files

- [`protocol.json`](protocol.json): preregistration, decision rule, frozen digests.
- [`corpus.json`](corpus.json), [`cases/`](cases/), [`truth/`](truth/): the 26 artifacts, hidden truth, sources, licenses, labels.
- [`blind-labels/`](blind-labels/): mapper instructions, the two blind F-code mappings, item-to-case key.
- [`reports/claude-sonnet.json`](reports/claude-sonnet.json): all 234 model calls with prompt digests, raw output, usage, timing.
- [`reports/claude-sonnet-judged-by-codex-sol.json`](reports/claude-sonnet-judged-by-codex-sol.json): the 26 blind judge calls.
- [`reports/claude-sonnet-results.json`](reports/claude-sonnet-results.json): derived metrics, lifts, per-case rows, decision.

## Freeze evidence note (added after review)

The `registered_utc` field in `protocol.json` is not reliable: it was typed by hand and does not match the real first scored call (it is later than that call, and for v2 and v3 later than the actual clock time). `protocol.json` is frozen, so it is left as is. The freeze is established only by the pinned SHA-256 digests (`frozen_digests` equal the `input_digests_before` recorded in every report) and by file modification times; no git commit predates the first call.
