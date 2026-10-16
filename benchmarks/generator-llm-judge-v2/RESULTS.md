# generator-llm-judge-v2 — results (written after the run; not bound by freeze.json)

Descriptive, reference only. No human check. Judge: Claude `sonnet` (Claude Code 2.1.300). The v1 reports and the human-eval key were not changed or opened.
Frozen 2026-10-16 (see `freeze.json`); canary 4 units, 0 failed, no identifying word in the reasons; main run 72 calls, 0 failed, 0 pairs excluded
by the preservation check (all 36 pairs normalised; 41 of the 72 artifacts had more than one file before the merge).

## M2 — normalised re-judging (Claude, 36 pairs, both positions)

| | v2 normalised | v1 same pairs |
|---|---|---|
| AF decisive pairs favouring CLI-first (W) | 24 / 24 (95% CI 0.858–1.0) | 24 / 24 |
| AF P1 (not worse), strict | 24 / 24, strict 24 / 24 | 24 / 24 |
| AG decisive pairs favouring CLI-first | 12 / 12 (CI 0.735–1.0) | 12 / 12 |
| position consistency (AF / AG) | 24 / 24, 12 / 12 | |
| share of calls choosing Spec 1 | 0.50 (24 / 48) | |
| AF decisive pairs favouring the longer artifact (normalised lines) | 3 of 24 (CI 0.027–0.324) | 0 of 24 (v1 lines) |

Preregistered reading: **M2: same direction after normalisation (reference only)**, for AF and AG.

## M1 — length-matched subset of the v1 reports (no new calls)

Band counts (from line counts only): AF within 1.25x = 13 of 36, within 1.5x = 26 of 36; AG within 1.25x = 14 of 24, within 1.5x = 22 of 24.

| judge | AF in band-1.25 (W) | AF outside (W) | reading |
|---|---|---|---|
| Claude | 9 / 9 | 15 / 15 | no length dependence seen (small sample) |
| Codex (same family as the makers) | 12 / 12 (+1 unstable) | 23 / 23 | no length dependence seen (small sample) |

AG (Claude): in band 7 / 7 decisive, below the 8-pair minimum, so *insufficient sample*; Codex AG in band 14 / 14, same reading as AF.

## What this does and does not show

- The preference for the CLI-first artifact did not disappear when comments, blank lines and file splits were removed, and it did not weaken inside similar-length pairs.
- **Ceiling.** Every decisive pair favoured CLI-first in every cell, so W = 1.0 everywhere; W cannot register dependence on length, and the M1 readings are weak by construction. The preregistered rule yields "no dependence seen" only because there is no variation to detect.
- **Confounding in this sample (not a preregistered measure).** In all 36 AF pairs the CLI-first artifact has fewer non-blank lines than the official-agent artifact (and 23 of 24 AG pairs). Length and arm are therefore not separable by selection here; M2's normalisation is the only control, and it removes comments, blank lines and file splits, not indentation, naming or test count. After normalisation the judge chose the longer artifact in 3 of 24 AF pairs (post-normalisation line counts differ from the v1 counts), which is some evidence the choice is not only "shorter".
- Reasons in the canary cite repeated setup, vague test names and data-driven loops, i.e. content differences, not size. That is a reading of 4 answers, not a measure.
- Everything here is a model judging a model, one family, no human confirmation. No sentence about quality may rest on it. The allowed sentence (preregistered table, M1 "no dependence seen" + M2 "same direction"): *"A length-controlled re-check pointed the same way as v1 (model judge, no human check, reference only)."*
