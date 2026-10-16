# generator-llm-judge-v2 — length-controlled re-check of generator-llm-judge-v1

Status: **PREREGISTERED_NOT_FROZEN. Descriptive, reference only (no human check). Not a statistical test.**
Written 2026-10-16 (KST evening), before any v2 judge call and before any v2 prompt was built.

## Why this exists

[v1](../generator-llm-judge-v1/protocol.md) found both judges preferring the CLI-first artifact in nearly every AF pair (Claude: every
decisive pair; about nine in ten decisive calls favoured the shorter file). That pattern is what a length or form cue would produce, and it is
also what a real economy and readability difference would produce. v1 cannot tell the two apart. v2 tries to separate them with two controls.
v1 is frozen and is neither edited nor re-run; v2 reuses its sample and, for M1, its judge reports.

**Disclosure of what the author knew.** When this file was written the author knew the *aggregate* v1 outcome (Claude: all decisive AF pairs
favoured CLI-first, 33 of 36 decisive pairs favoured the shorter artifact; Codex similar) and the thin-eval r3 cell metadata. The author had not
seen per-pair v1 predictions, any artifact text, or the per-pair line counts. The band limits below (1.25 and 1.5) come from the owner's
instruction, not from the data, and are fixed here.

## M1 — length-matched subset (no new calls)

Uses the finished v1 judge reports (Claude `reduced`, Codex `full`) and the v1 arm key. Line count = non-blank lines of the anonymised
shown code (`facts.nonblank` in the v1 key), summed over the files of an artifact.

- Length ratio of a pair = longer artifact / shorter artifact (non-blank lines). **Band-1.25** = pairs with ratio ≤ 1.25 (primary).
  **Band-1.5** = ratio ≤ 1.5 (sensitivity only). No other band is computed.
- The bands are decided from line counts alone, before any v1 prediction is joined to a pair.
- For each judge and comparison (AF primary, AG secondary), inside the band and outside it:
  - **W** = O / (A + O) over decisive pairs (O = CLI-first arm preferred in both positions, A = official preferred in both).
  - **P1** = (O + tie + unstable) / (pairs not `cannot`), Clopper–Pearson 95% interval; strict P1 beside it. Same definitions as v1.
- **Insufficient sample rule.** A cell of the table with fewer than 8 decisive pairs is labelled *insufficient sample* and gets no reading.
- **Reading (per judge, AF).** With ≥ 8 decisive pairs in the band:
  - `W_out − W_in ≥ 0.25` → **length plausibly drove v1** (preference falls when the files are similar in length).
  - otherwise, if `W_in ≥ 0.5` → **no length dependence seen (small sample)**: the preference holds among similar-length pairs.
  - `W_in < 0.5` → **reversed among similar-length pairs**.
  Band-1.5 is reported next to Band-1.25 and cannot change the reading.

## M2 — normalised re-judging (new calls)

**Normalisation (`normalize.js`, meaning-preserving).** For each artifact, after the v1 anonymisation: remove comments, blank lines and
trailing whitespace (blank lines inside template literals are kept); merge all files of the artifact into **one file** labelled `File 1`; merge
and de-duplicate the import declarations (kept bindings unchanged), sort them (packages before relative paths), single quotes.
Not normalised: indentation, quote style inside the body, identifier names, statement order, the number of tests. These remain possible form cues
and are listed as a limit.

**Why merge into one file (decided here, before looking at the merged results).** v1's judge reasons mention files being split into several files; a
different number of files is a visible form cue and the rubric does not value it. The merge does not change what the tests verify.

**Preservation check (per pair, mandatory).** The comment-free, location-free AST of the original bodies (imports excluded, files
concatenated in file order) must equal the AST of the merged body, and the set of imported bindings must be unchanged. Also refused: a duplicate
top-level name after merging, a local name imported from two sources, a file that does not parse. A pair that fails is **excluded from M2 and
listed**. If more than 6 of the 36 pairs are excluded, M2 is *inconclusive* and is not read.

**Judge and sample.** Claude `sonnet` only, same runner path as v1, `reduced` tier (the same 36 pairs, 24 AF + 12 AG, both positions: 72 calls
minus excluded pairs). The Codex judge is **not** run in this freeze (it would use Codex quota that the thin-eval stage needs; if run later it
needs its own protocol). Nothing from v1's answers is shown to the judge. Calls are fresh, prompt-complete, tools disabled.

**Prompt.** The v1 prompt with the sentence about length replaced by:
"Length, number of files, amount of code, comments and blank lines are not criteria: comments and blank lines were removed, all files were merged
into one, and imports were merged and sorted before you saw the code. Economy means duplicated or dead code, not shortness." The rubric, the
task sentence and the scenario list are unchanged. Everything else (answer schema, retries, anonymisation, leak scan) is as in v1.

**Metrics (Claude, AF primary).** W and P1 as above, on the normalised prompts; position consistency; position share; the length measures
recomputed on the *normalised* line counts (Spearman of score difference against relative length, and the share of decisive pairs favouring the
longer artifact).

**Reading of M2 against v1 (same Claude judge, same pairs that survived the preservation check).**
- `W_v2 < 0.5` → **reversed after normalisation**: the v1 preference did not survive.
- `W_v1 − W_v2 ≥ 0.25` (and `W_v2 ≥ 0.5`) → **weakened**: the v1 preference was partly a length or form effect.
- otherwise, `W_v2 ≥ 0.5` and `P1_v2 ≥ 0.5` → **same direction after normalisation (reference only)**.
- If the judge's position consistency is < 0.60, M2 is *reference only, unstable* regardless of the above.
- If fewer than 8 decisive AF pairs remain, *insufficient sample*.

## Combined sentence (fixed in advance)

| M1 (Claude, AF) | M2 (Claude, AF) | Sentence allowed |
|---|---|---|
| no length dependence seen | same direction | "A length-controlled re-check pointed the same way as v1 (model judge, no human check, reference only)." |
| length plausibly drove v1, or reversed | weakened or reversed | "The v1 judge preference is plausibly a length/form effect and is not evidence of quality." |
| any other mix, insufficient sample, or inconclusive | | "The length control did not settle whether v1's preference reflects quality; no judge-based quality statement is made." |

Whatever the outcome, there is no human confirmation, so no sentence about quality may rely on model judging; the allowed sentences only
describe the judge's behaviour. v1 results are not changed by v2. A result that moves in neither direction is reported as such.

## Exclusions, canary, invalid runs

- Canary before any data call: 2 pairs (4 units) into a file whose name contains `canary`; non-data. It checks that answers are schema-valid and
  that no identifying token appears in the reason, and that the normalised prompts contain no comment text. A failing canary is archived (never
  deleted) and fixed in a new protocol id before any data call.
- Failed units follow v1: up to 3 attempts, then the pair is `missing`; more than 10% failed units makes M2 inconclusive.
- `freeze.json` binds this protocol, the scripts, `normalize.js`, the Playwright Babel bundle digest, the v1 sample key, the v1 reports used by M1
  and the v2 prompt set. Drift stops the run; a change needs a new protocol id. The human-eval key is never opened.

## Limits

- Model judging, no human check; nothing here supports a quality statement.
- Normalising removes comments, which are part of readability; a judge may lose a real signal. Residual form cues (indentation, naming, test count)
  remain.
- Pairs are not independent (cells reappear); 36 pairs give wide intervals.
- M1 reuses v1 calls, so it is not an independent replication; M2 is one judge, one model family different from the makers.
- Both judges in v1 favoured the shorter file strongly; if the normalised prompts still carry a size cue, M2 cannot see it.

## Files

`normalize.js`, `common.py`, `build_inputs.py`, `run_judge.py` (`plan`, `verify`, `freeze`, `run`), `m1_band.py`, `analyze.py`, `selftest.py`,
`protocol.json`. Runtime data: `~/.cache/e2e-skills-bench/llm-judge-v2/` (v1's `llm-judge-v1/` is read, never written).
