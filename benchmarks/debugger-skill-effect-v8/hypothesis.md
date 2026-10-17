# Hypotheses (written before any scoring call of v8)

Context: v7 compared the 3.0.0 lean debugger text with the 2.0.1 text on the 28 v3 cases and ended FAIL on one check only: the F-code interval was too wide (difference -0.029, 95% interval -0.116 to +0.058 on 23 labeled cases, 16 of them tied). It did not show a loss; it showed the check was underpowered. The v7 `new` snapshot also came from a working tree whose Playwright `SKILL.md` (11,227 B) differs from the text now committed for release (11,388 B). v8 measures the committed text on a larger, new corpus.

H1 (primary, non-inferiority): on zero-tool diagnosis of the 107 v8 cases, the typical-path text (`new-lean`, release candidate 293491f8) is not worse than the 2.0.1 text (`old`) by more than 0.05 on strict root-cause match (95% case-cluster lower bound and point estimate), by more than 0.10 on F-code exact match on the primary label set (the cases a blind second mapper labeled the same as the author), by more than 0.05 on product/test attribution, or by more than 0.30 unsupported claims per answer, while using at most 0.80 of its input tokens.

H2 (secondary): dropped before the freeze (2026-10-16, owner decision; the `new-full` arm is not run).

H3 (secondary): dropped before the freeze for the same reason.

H4 (descriptive, no gate): the F-code difference has the same sign on the real cases and on the authored cases. A difference that appears only on the authored stratum is read as a property of the authored cases.

Not hypothesised: superiority of any arm; that the conditional load of `safety-procedures.md` works; anything about tool use, redaction, the launcher or the acquisition workflow.

Expected, stated so a surprise is visible: F-code agreement of both skill arms clearly above chance and within a few points of each other (the F1-F15 table is identical in both texts; v7 measured 0.61 for `new-lean` and 0.64 for `old`); the authored stratum easier than the real stratum for every arm; `free` close to the skill arms on strict match and behind them on unsupported claims, as in v2, v3, v5, v6 and v7.

Stated in advance: with the primary set of 82 cases the F-code check passes in roughly 97 of 100 trials if the true difference is 0, 89 at -0.02 and 67 at -0.04 (power-simulation.json; with the first 54 primary cases it was 89, 75 and 54). A lower bound under -0.10 is reported as FAIL on the preregistered rule and read as "not proven", never rescued by choosing another set or margin afterwards.
