# generator-llm-judge-v1 — cross-family model judging of generated Playwright specs

Status: **PREREGISTERED_NOT_FROZEN. Descriptive supplement to a human check, not a statistical test.**
**r2 (2026-10-16, owner decision, before freeze and before any judge call):** the owner decided NOT to run the human check. The human gate below therefore cannot be met: model judging is **reference only (no human confirmation)** in every reading, and no sentence about quality may rely on it. Chosen tiers: Claude `sonnet` = `reduced` (72 calls), Codex `gpt-6-sol` = `full` (120 calls). Nothing else in this protocol changes.
Written 2026-10-16, before any judge was called and before any generated spec was read by the author of this file.
The only data read are cell *metadata* of the finished thin-eval r3 campaign (arm, case, `deliverable`, `as_treated`,
`fidelity_class`, `spec_files` lengths) and aggregate size statistics of the anonymised prompts.

## Question

[generator-human-eval-v1](../generator-human-eval-v1/protocol.md) asks a developer to read CLI-first and official-agent specs
side by side. One reviewer and 12 pairs per comparison is a small, expensive check. This protocol asks the same narrow question of
**models from a different family than the one that wrote the specs**, on more pairs, with every pair judged in both positions:

> When a model that did not write either file reads a CLI-first spec next to an official-agent spec, does it judge the CLI-first spec worse?

It does not replace the automated metrics of [thin-eval r3](../generator-thin-eval-v1/README.md), does not replace the human check,
and cannot turn either into an equivalence claim. Model judges have known biases (position, length, self-preference); this protocol
measures those biases and states in advance how the results are read when they appear.

## Source and arms

- Source: finished thin-eval r3 results (`~/.cache/e2e-skills-bench/thin-eval-v1-r3`), models `gpt-6-sol` and `gpt-6-astra`, six tasks
  (`v2-06 v2-22 v2-23 v3-04 v3-06 v3-09`), bound by the digests in `freeze.json`.
- Arm A = `official-generator`. Arm F = `cli-first+thin-rules`. Arm G = `cli-first+thin-rules+scanner`. Pairs: **AF** (primary) and **AG** (secondary). D and E are not sampled.
- Eligible cell: `deliverable` and `as_treated` true, `infra_failed` and `aborted` false, `spec_files` non-empty, `fidelity_class` equals `official-tool` (A) or `cli-observed` (F, G). Same rule as the human check. `call_id` is only unique within a model; every pair key includes the model.

## Sample (fixed by `select_sample.py`, seed `20261016-llm-judge`)

Strata: model (2) × task (6) = 12. Per stratum, five pairs in three nested tiers:

| tier | per stratum | pairs | meaning |
|---|---|---|---|
| core | 1 AF + 1 AG | 24 | the pairs the human-eval protocol rates (see below) |
| reduced | core + 1 AF | 36 (24 AF + 12 AG) | smaller option for the judge with scarce quota |
| full | reduced + 1 AF + 1 AG | 60 (36 AF + 24 AG) | all pairs |

- **Shared with the human check:** the 24 `core` pairs are *derived* by replaying the human-eval sampling rule (its public code and seed `20261016`) on cell metadata. The human key was not opened, so `human_rated` is a derived flag. It is checked against the real human key only after all human ratings exist (`analyze.py --human-key`; the check is by model plus cell ids). If the derivation turns out to differ, the concordance section reports fewer matched pairs and says so; the judge results themselves are unaffected.
- Extra pairs are drawn per stratum from the remaining cell combinations with a seeded shuffle, preferring combinations that reuse the fewest cells. Cells can appear in more than one pair; pairs are therefore not independent samples, and intervals are computed on pairs and cross-checked with a task-clustered bootstrap.
- Each pair is **judged in both positions** (official-generator artifact as Spec 1, then as Spec 2): 2 calls per pair, 120 calls for the full tier.

## Judges and independence

| role | runner and model | family relation to the makers (`gpt-6-sol`, `gpt-6-astra`) |
|---|---|---|
| primary | Claude Code, alias `sonnet` (canonical id recorded in the report) | **different family** — preferred judge for this question |
| secondary | Codex, `gpt-6-sol` | **same family as both makers, and the same model as the maker for the `gpt-6-sol` cells** — self-preference toward Codex-style code is possible; results carry that label |

- Judges never see each other's output. Each writes its own report; `analyze.py` is the only place they meet.
- Each call is a fresh, prompt-complete invocation with every model tool disabled (`run_once` with `claude_permission_mode="off"` and an output schema), in an empty temporary directory. No repository, skill, memory or earlier answer is available to the judge.
- Reasoning effort and sampling settings are the runner defaults; they are not controllable per call and are not part of the claim.
- **Reverse direction (documented, not in this freeze).** A Codex-primary judgement of Claude-written specs needs enough valid Claude-made artifacts. Valid Claude official-arm data exists only from 2026-10-15 and in small amounts; a separate protocol and freeze would be needed.

## What the judge sees

One prompt per call, built by `common.render_prompt`: the task sentence, the scenario checklist (the "Expected Results" lines of the approved plan every arm received), the five-criterion rubric with 1/3/5 anchors (the same wording as the human check), and the two specs under neutral headings. Spec files are anonymised exactly like the human pack: original names hidden, `// spec:` and `// seed:` headers dropped, whole-line `//` comments naming `plan.md` or `seed.spec` dropped.

- **Not shown, in any form:** arm, model name, runner name, scanner output, test results, mutant kill, refactor score, line counts, or any automated metric. `build_inputs.py` runs a leak scan (arm, model, tool, scanner, plan, runner vocabulary) over the shown code and `verify` refuses to proceed if any identifying token remains in a prompt.
- The prompt tells the judge to judge the code as written, not to guess authorship, and not to reward or penalise length or file count.
- **Answer schema** (enforced by the runner and re-validated): per spec, five integer scores 1–5 or null; `preference` ∈ {spec1, spec2, tie, cannot_tell}; a reason of at most 300 characters. A failed call is retried up to 3 times (infrastructure error or invalid output); a unit still without a valid answer is reported as failed and the pair is `missing` for that judge.

## Options and cost (planning estimates, not measurements)

Per judge; tokens use 3.5 characters per token on the anonymised prompts plus an assumed 4,000-token runner overhead per call (mostly cache reads), plus 350 answer tokens.

| option | pairs | calls | prompt input tokens | with runner overhead | output tokens |
|---|---|---|---|---|---|
| core | 24 | 48 | ≈ 169 k | ≈ 361 k | ≈ 17 k |
| reduced | 36 | 72 | ≈ 251 k | ≈ 539 k | ≈ 25 k |
| full | 60 | 120 | ≈ 420 k | ≈ 900 k | ≈ 42 k |

Wall-clock is unmeasured: at 45–90 s per call and 2 workers a judge takes roughly 0.5–1.5 h for `reduced` and 1–2.5 h for `full`. Judges use no Docker, browser or machine lock, so they can run while a Codex campaign uses the host, but the Codex judge then competes for the same Codex quota.

The owner chooses the tiers at freeze (recorded in the freeze note, not changeable afterwards). Proposed default: **Claude `reduced` (72 calls) + Codex `full` (120 calls)**, which keeps the scarce Claude weekly quota low and gives a 36-pair overlap for judge agreement. A Claude `core` run (48 calls) is the minimum that still overlaps all 24 human-rated pairs.

## Statistics (all descriptive)

Per judge and comparison, each pair is consolidated from its two positions into one class: **A** (official preferred in both positions), **O** (the other arm preferred in both), **tie**, **cannot**, or **unstable** (preference flipped with position or only one position decisive).

- **P1 (primary, AF):** share of pairs where the CLI-first output is *not worse*: (O + tie + unstable) / (pairs not `cannot`), Clopper–Pearson 95% interval. `unstable` is counted as a tie here because the judge could not separate the files; the **strict P1** (unstable counted against F) is always printed beside it. P2 is the same for AG.
- **Rubric differences:** mean of (other − A) per criterion over pairs, with a task-clustered bootstrap 95% interval (seed fixed in the code).
- **Position bias:** share of calls preferring Spec 1 with an interval; **position-consistency** = share of decisive pairs whose two positions agree.
- **Length bias:** Spearman correlation between the pair's mean score difference and the relative line-count difference, and the share of decisive pairs preferring the longer file.
- **Maker/judge family table:** printed with every report (above), plus per-maker-model class counts; the Codex judge's results are labelled self-family.
- **Judge agreement:** percent agreement and Cohen's κ on the 3-way class (A / O / no preference) over the pairs both judges completed; **disagreements are listed separately**, opposite-direction pairs (A vs O) first.
- **Human concordance** (only after all human ratings exist, on the `human_rated` pairs): agreement among pairs where both the human and the judge are decisive, with an interval.

## Reading rules (set before any data)

- **Per judge.** "No judge-measured quality loss seen" requires all of: the AF P1 interval's lower bound ≥ 0.5; no criterion with mean (F − A) ≤ −0.5; position-consistency ≥ 0.60. If consistency < 0.60 the judge's results are *reference only* regardless of the other numbers.
- If the P1 lower bound is < 0.5 but the point estimate is ≥ 0.5 and no criterion is ≤ −0.5, say "no loss detected, undersized"; that is not a pass.
- A criterion mean ≤ −0.5, or F preferred in at most a third of decisive AF pairs, is a *concern flag*, reported even if P1 passes.
- **Two judges.** If the judges point in opposite directions (primary: no loss, secondary: F worse, or the reverse), the sentence is "the judges disagree" and both are reported with their disagreement list. A statement that uses model judging at all must name the judge family and mention the self-family caveat for the Codex judge.
- **Human gate (r2: no human check will be run, so this gate is unmet by construction; model judging is reference only, with no human confirmation).** Model judging counts as *supporting* evidence only if, on the `human_rated` pairs where both are decisive, it agrees with the human reviewer on ≥ 0.70 of at least 8 pairs. Otherwise it is *reference only* and no sentence about quality may rely on it. If the human reviewer and a judge disagree, both are reported and neither is declared right.
- Bias findings are reported whatever they say: a judge with position-share > 0.65 or length preference > 0.70 among decisive pairs is flagged.
- No result moves the automated thresholds, the ship decision rule, or any frozen file. Nothing here is "equivalent" or "better".

## Exclusions, invalid runs and canary

- Canary: before the first real call, `run --canary` makes two pairs' calls (4 units) into a file whose name contains `canary`; it is non-data, excluded from analysis, and checks that the runner returns schema-valid answers and that no identifying token appears in the model's reason. A failing canary is archived (never deleted) and the cause fixed as a new protocol revision before any data call.
- A report with failed units is still analysed; failed units make their pair `missing` for that judge and are listed. If more than 10% of units fail for a judge, that judge is `inconclusive`.
- Mock and canary reports are refused by `analyze.py`. Judge reports are written once; an existing report is never overwritten (`--resume` continues a partial file).
- `freeze.json` binds the digests of this protocol, the scripts, the thin-eval r3 `results.json` of both models, the sample key and the prompt set. A drift in any of them stops `run`. A change after the freeze needs a new protocol id.

## Limits (stated up front)

- **Models judging models is not a human check.** It is cheaper and more repeatable, and it has its own biases; this protocol measures three of them and cannot rule out others (for example a preference for a style the judge itself tends to write).
- **Self-family judge.** The Codex judge reads Codex-written files; its preference for or against them is not independent of the makers.
- **Pairs are not independent.** Cells reappear in several pairs and positions double the calls per pair; intervals are indicative.
- **Code only.** Execution, mutation kill and scanner results are not shown, so a spec that reads well but fails would score well here; the automated metrics are the guard for that.
- **Two Codex-made model sets, six synthetic tasks:** same scope limit as thin-eval r3.
- A judge's preference is not evidence that a generator is better; it is only a check that the cheaper path was not judged worse by a reader from another family on this sample.

## Files

`common.py` (rubric, prompt, anonymiser, statistics), `select_sample.py`, `build_inputs.py`, `run_judge.py` (`plan`, `verify`, `freeze`, `run`), `analyze.py`, `selftest.py` (offline, mock judges), `protocol.json` (machine-readable sizes). Runtime data (sample key, prompts, reports) live outside the repository in `~/.cache/e2e-skills-bench/llm-judge-v1/`; the arm key (`key/`) is not opened until the judge reports exist.
