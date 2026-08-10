# Why the Codex host misses on line anchors, not on detection

## Question

The public development holdout scored `claude:claude-opus-5` at 0.986 precision
and `codex:gpt-5.6-sol` at 0.792, a gap wide enough to read as a skill quality
problem on that host. This audit asks what the Codex misses actually are.

## Finding

They are not detection misses. Across the failing runs, every miss lands in a
file the model did report, with the correct pattern ID, one line above the
labeled line. The scorer keys a finding on `(pattern_id, severity, file, line)`,
so one line of disagreement produces a false positive and a false negative from
the same finding. That is why `fp` equals `fn` in almost every failing case.

Breakdown of the 16 misses in the third measured run:

| miss shape | count |
| --- | --- |
| same file, line off by one | 14 |
| same line, different pattern ID | 0 |
| file not reported at all | 0 |

All 14 were exactly `-1`, and all 14 carried the correct pattern ID.

## The disagreement is a convention, not an offset

The labels are correct: for every audited miss, `source_line` matches the file
at the labeled line number. The line the model picks instead is not a blank, a
comment, or a counting artifact. It is the start of the enclosing expression, or
the line where the subject is declared:

| pattern | labeled line | line the model reported |
| --- | --- | --- |
| `#5b` | `force: true,` | `.click({` — where the call starts |
| `#6` | `document.querySelector(...)` | `const ready = await page.evaluate(` |
| `#15` | `expect(saved).toBeVisible();` | `const saved = page.getByRole(...)` |
| `#16` | `reload.click();` | `const reload = page.getByRole(...)` |
| `#18` | `await expect.soft(form)...` | `const profileForm = ...` |
| `#3` | the swallowed `await` | `async waitUntilReady() {` |

The corpus is written compactly, so the enclosing construct is always one line
above. That is what makes the deltas look like an off-by-one.

Two of these are arguable in the model's favour. For `#5b` the labeled line is a
property inside a multi-line call, and for `#6` it is a line inside an arrow body;
naming the line where the call begins is a defensible reading of "the causal
line". Part of this gap is the specificity of the corpus convention, not model
error.

## Interventions that did not work

Two prompt-level changes to the reviewer's primary-line anchor contract were
measured, each with a full 24-call run against the same corpus and protocol.

| skill state | precision | miss shape |
| --- | --- | --- |
| baseline | 0.792 | `-1` and `+1` mixed, one ID mismatch |
| plus an explicit anchor rule for unnamed patterns | 0.778 | `+1` gone, `-1` remains |
| plus a re-read-the-line verification step | 0.784 | `-1` only, nothing else |

Both changes moved the failure shape and neither moved the metric. The rules
were reverted; the skill is unchanged. Recording them here so the next person
does not spend another 48 live calls rediscovering that a prompt sentence does
not resolve a convention disagreement.

## What this does and does not license

It does not license calling the Codex arm a pass. The preregistered thresholds
are what they are, and the run is recorded `FAIL` with `repeated_precision_min`
at 0.784 against a required 0.900.

It also does not support "the skill detects poorly on Codex". Recall of the smell
itself is high and pattern identification was exact on every audited miss.

The actionable item, if this is pursued, is the anchor contract for multi-line
constructs — which line is causal when a call spans lines, and whether a finding
anchors the action or the declaration of its subject. That has to be settled
across the skill and the corpus labels together, not by adding prose to one of
them.

## Reproduction

Per-run findings and scores are in `reports/full-codex.json` under `runs[].findings`
and `runs[].score`. Labels are in `scripts/evals/reviewer-holdout-v3.json`. A miss
is classified by comparing each `missed_finding_ids` entry against the findings
reported for the same file in that run.
