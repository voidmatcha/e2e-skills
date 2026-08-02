# Run independent product reviews

This protocol was written before the final Claude Opus 5.0 and Claude Fable
product reviews were requested from the local Claude Code CLI. Earlier Codex
product reviews were used as remediation feedback; they are not independent
benchmark evidence.

## Allowed evidence

Reviewers may read:

- `README.md`, `CONTRIBUTING.md`, and `CHANGELOG.md`
- `skills/e2e-reviewer/**`
- `scripts/ci/**`
- `scripts/evals/run-reviewer-holdout.py`
- `scripts/evals/compare-reviewer-holdouts.py`
- `scripts/evals/run-fixture-faults.py`
- `scripts/evals/fixtures/**`
- public benchmark methodology documents

Reviewers must not read:

- `scripts/evals/reviewer-holdout-v3.json`
- `scripts/evals/files/holdout-v3/**`
- `benchmarks/reviewer-holdout-v3/reports/**`
- another model's review

This separation prevents the product critique from merely echoing gold labels,
scores, or another reviewer's conclusions. It is a source review, not a blind
performance measurement.

## Fixed prompt

> Review this repository's `e2e-reviewer` skill and its validation system as a
> skeptical independent product reviewer. Do not read any v3 labeled corpus,
> fixture source under `scripts/evals/files/holdout-v3`, scored v3 report, or
> another model review. Assess: taxonomy correctness and coverage; Playwright
> and Cypress semantic accuracy; false-positive controls; executable
> mutation/behavior evidence; model-runner integrity and reproducibility;
> documentation honesty and user persuasiveness; missing high-value coverage;
> and whether the evidence justifies a score out of 100. Separate confirmed
> defects from limitations and optional improvements. Cite exact file and line
> evidence. Give a 0-100 score with a transparent rubric, the five highest-value
> improvements, and a final PASS, PASS WITH CAVEATS, or REQUEST CHANGES verdict.

## Execution controls

- Models: `claude-opus-5` and `claude-fable-5`
- Read-only tools: `Read`, `Glob`, and `Grep`
- Claude Code flags: safe mode, empty setting sources, no session persistence,
  and plan permission mode
- One fresh non-persistent call per model
- Raw responses are preserved without editing; a separate Codex-native reviewer
  audits the same product after both Claude reviews are frozen

The final reviews run only after the evaluated skill/corpus snapshot is frozen.
They may identify future work, but do not change that final snapshot or
retrospectively alter its model score. Earlier pre-fix/remediation reviews did
inform development and are labeled accordingly.

Licensed under Apache-2.0 with the repository.
