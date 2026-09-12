# Reviewer case library

**Static cases only. There is no runner here, and these files support no claim.** They are kept because the cases are reusable and were expensive to write; the pilot apparatus that once consumed them was removed deliberately.

48 cases in four sets of twelve, each set six positives and six clean guards, each in a different application domain so a reviewer cannot pattern-match on subject matter.

| File | Domain | Focus |
| --- | --- | --- |
| `cases-v2.json` | garden plots | mixed catalog: `#2`, `#16`, `#17`, `#14`, `#10`, `#19` |
| `cases-v3.json` | community radio archive | error-swallow probes plus `#18`, `#1`, `#6`, `#11` |
| `cases-v4.json` | museum collections | error-swallow concentrated: `#3`, `#3b` |
| `cases-v5.json` | bikeshare docks | error-swallow across helper modules and callback bodies |

## What these cases are not

- **Not independent.** Every case was written by the same agent that was iterating on the skill, in the same sessions. `source_provenance.class` is `development_contaminated` throughout, and that is accurate.
- **Not real defects.** Every case is `synthetic_fault` or `clean_guard`. No case is anchored to a repository, pull request, or commit. "The author planted it and the author's tool found it" is the correct way to read any result measured on them.
- **Not a fair test for v4 and v5.** Their outputs were read while the `#3` contract was being edited. Measuring a later `#3` change against those two sets would report overfitting, not improvement. `cases-v2.json` and `cases-v3.json` were not used that way.

## Why the runner is gone

Five pilots and roughly 650 model calls produced two findings. One was negative — rewording `#3`'s exemption did not improve detection (0.19 against 0.17, one detection in thirty-six). The other did not come from any aggregate: detection tracked whether the deterministic scanner could see the swallow form, `.catch(() => {})` scoring 6/6 while five `try/catch` cases scored 0/6 or 1/6.

Two of the five pilots also saturated at 12/12 in every arm, which carries no information, and three never produced their declared headline measure because the judge scored helpfulness fields that were never the declared measure.

The integrity machinery was sound. The experiment design around it was not, and keeping a runnable harness invites running the same design again. The measurements it produced are recorded in `CHANGELOG.md`; the raw generation and judgment artifacts are not committed.

## Reasonable uses

- A regression bed for deterministic scanner work, where the oracle is checked mechanically and no model call is involved. This is the use that produced real value: the `try/catch` blind spot was found by scanning these cases and reading which ones failed.
- Seed material for a future corpus with genuine independence — different authorship, real defects with repository and commit anchors, and enough cases to support the claim being made.

Recovering the deleted apparatus is possible (`git log -- scripts/evals/reviewer-cross-model-*`) but is not recommended without first fixing the design faults above.
