# Reviewer holdout v9

Reviewer holdout v9 is a Codex-only three-arm protocol with a new corpus. It keeps the v8 host, prompt arms, thresholds, schedule seed, strict-majority stability rule, numbered sources, scoring contract, and five repetitions. It replaces the 20 v5 cases with 30 new synthetic cases built to separate the full reviewer workflow from the pattern catalog alone.

Status: **run at `cea2ae5`; arm comparison `FAIL`, so no skill-lift claim**. The corpus is public development evidence that its author inspected while designing it; it is not sealed and does not establish generalization.

## Result

One attempt, in `reports/`: 450 calls, no infrastructure errors, 84 minutes from first start to last completion.

| Arm | Status | Stable P / R / F1 | Repeated TP / FP / FN |
|---|---|---|---|
| full | `FAIL` | 0.902 / 0.925 / 0.914 | 186 / 24 / 14 |
| catalog-only | `FAIL` | 0.905 / 0.950 / 0.927 | 189 / 24 / 11 |
| no-skill | `FAIL` | 0.380 / 0.475 / 0.422 | 94 / 190 / 106 |

Unlike v8, v9 is not at the ceiling. Both skill arms miss the stable-precision (0.95), repeated-precision, and guard-hit-rate thresholds. Full minus catalog-only stable F1 is −0.013, with a 95% interval of −0.105 to +0.067, so the full workflow shows no accuracy gain over the pattern catalog alone. Full minus no-skill is +0.491, with a lower bound of +0.390.

By case, the full arm made fewer false positives where the deciding rule lives only in the workflow references (`v9-pw-07`, `v9-pw-10`, `v9-pw-15`). It did worse on severity boundaries: `#1` partial verification (`v9-pw-01`, `v9-cy-01`) and `#23` at P0 (`v9-cy-13`). Both arms missed `v9-cy-06` (`#2` at P1, a label the arbiter changed) in every run. These per-case readings are descriptive and support no causal claim.

## Why v9 exists

Reviewer holdout v8 hit a ceiling. The full and catalog-only arms both scored stable F1 1.000, so the lift of the full workflow over the catalog was 0 and the arm comparison was `FAIL` (see [`../reviewer-holdout-v8/README.md`](../reviewer-holdout-v8/README.md)). The v5 cases are small specs whose defects `pattern-reference.md` resolves on its own, so they cannot show whether the rest of the workflow adds anything.

The two skill arms see different reference text. The runner's `PROMPT_SKILL_PROFILES` gives the full arm `SKILL.md`, `review-scope.md`, `scanner-workflow.md`, `semantic-review.md`, `reporting.md`, `pattern-reference.md`, and `verification-rules.md`; the catalog-only arm gets `pattern-reference.md` alone; no-skill gets none. Many v9 cases are built so that the deciding rule lives only in the full arm's extra references:

- `semantic-review.md`: the bounded opening-token sweep rows (a bare `return` branch is the same `#5a` finding, `Cypress['on'](` bracket access, a non-literal `cy.wait`, a `describe.configure` policy passed by variable, a formatter-wrapped async `it(`), and the primary-line contract that anchors `#21` at the reference and `#23` at the violating fixture field.
- `review-scope.md` and `verification-rules.md`: application source is context only, and a documented project convention decides P2 findings but can never downgrade a P0 or suppress a P1 without a concrete local rationale.
- `reporting.md`: the P0 boundary, which also backs the `#1` severity rule that `pattern-reference.md` now states.

Other cases are decided by `pattern-reference.md` for both skill arms; they keep the corpus from rewarding the full arm on every case. Case themes come from a 2026-09-26 adjudication of 45 real reviewer findings on cal.com, kibana, cypress-rwa, and ever-gauzy. All code is synthetic and original: the field cases were reduced to their structure, and no text was copied from those repositories.

## Corpus

30 cases: 16 Playwright and 14 Cypress, each a small repository slice (spec plus any page object, fixture, support file, config, or application component it needs) under `scripts/evals/files/holdout-v9/<case-id>/`. Every case has a `design_note` naming the arm expected to get it right and why, and every label has a `reason` naming the reference rule that decides it. Case and label IDs (`v9-pw-01`, `V9-001`) are independent of v5.

| Kind | P0 | P1 | P2 | Total |
|---|---|---|---|---|
| finding | 11 | 22 | 7 | 40 |
| fp_guard | 14 | 13 | 5 | 32 |
| optional | 4 | 3 | 0 | 7 |

False-positive guards are 41% of labels. Clean cases (only guards): `v9-pw-11`, `v9-cy-10`, `v9-cy-12`. Seven labels carry `accepted_alternatives` where two tuples describe the same single defect.

Some labels use an instance severity that the Quick Reference does not list, and the corpus validator accepts only these, only in a designed-label corpus: `#1` at P1 when one promised outcome is verified and another is not (`v9-pw-01`, `v9-cy-01`); `#2` at P1 when request proof exists and only the promised UI state is unchecked (`v9-cy-06`); `#23` at P0 when a guard-suppressed render lets a negative assertion pass (`v9-cy-13`); and optional `#4i` at P0 where an absence check is the only verification and cannot fail (`v9-pw-02`, `v9-cy-02`). The last two rest on the `reporting.md` P0 boundary. Each has a guard on the catalog severity at the same line, so reporting the wrong severity costs a false positive and a miss.

| Case | Framework | Theme | Expected to succeed |
|---|---|---|---|
| `v9-pw-01` | Playwright | `#1` partial (P1) vs fully unverified (P0) titles | both skill arms |
| `v9-pw-02` | Playwright | `#4i` loading gate vs absence check on a test-only selector | both skill arms |
| `v9-pw-03` | Playwright | `#5a` bare-`return` branch; reasoned `test.skip` guard | full |
| `v9-pw-04` | Playwright | `#10a` scoped `.first()` guard vs sorted-list `.nth()` | both skill arms |
| `v9-pw-05` | Playwright | screenshot tolerance larger than the 16x16 icon (`#4a` P0) | both skill arms |
| `v9-pw-06` | Playwright | swallowed assertion in a helper looks like `#1`/`#2` (`#3`) | both skill arms |
| `v9-pw-07` | Playwright | `#19` `var` and mutated `const`; app-source state guard | full (guard) |
| `v9-pw-08` | Playwright | `#9c` via constant, retry-wrapper skip, `> -1` bound | both skill arms |
| `v9-pw-09` | Playwright | `#22` optimistic save vs `#1`/UI-only toggle guards | both skill arms |
| `v9-pw-10` | Playwright | project conventions: P0 and P1 kept, P2 skip follows convention | full |
| `v9-pw-11` | Playwright | clean: proven absence, named-error rethrow | both skill arms |
| `v9-pw-12` | Playwright | `#23` anchored at the fixture field | full |
| `v9-pw-13` | Playwright | `#20` disposable backend guard vs shared staging write | both skill arms |
| `v9-pw-14` | Playwright | `#13` consolidation at the first raw action; unused POM member | both skill arms |
| `v9-pw-15` | Playwright | `#21` anchored at the `storageState` reference; `#11`; `#18` | full (`#21` anchor) |
| `v9-pw-16` | Playwright | `#10b` policy by variable; `#7` alias; `#17` renamed fixture | full (`#10b`) |
| `v9-cy-01` | Cypress | `#1` status-only (P0) vs partial ownership check (P1) | both skill arms |
| `v9-cy-02` | Cypress | `#4i` loading indicator on a test-only selector | both skill arms |
| `v9-cy-03` | Cypress | spec-level env gating (optional `#5a`); opt-in external auth (`#20` guard) | contract boundary |
| `v9-cy-04` | Cypress | `describe.skip` with a reason comment vs bare `it.skip` | both skill arms |
| `v9-cy-05` | Cypress | `#3b` bracket access; scoped allowlist guard; `#9b` non-literal wait | full |
| `v9-cy-06` | Cypress | redirect proves delete; rename lacks Then (`#2`, not `#1`) | both skill arms |
| `v9-cy-07` | Cypress | `#21` `cy.session` replaying a manually captured file | full (anchor) |
| `v9-cy-08` | Cypress | `#10f` chain, `#4g` zero timeout, JUSTIFIED guards | both skill arms |
| `v9-cy-09` | Cypress | `#10d` formatter-wrapped async callback | full |
| `v9-cy-10` | Cypress | clean: smells only in application source | full |
| `v9-cy-11` | Cypress | `#5a` bare `return` in a `.then` callback | full |
| `v9-cy-12` | Cypress | clean: counted `.each`, proven absence | both skill arms |
| `v9-cy-13` | Cypress | `#23` P0 at the archived fixture field; optional `#4i` | full (anchor) |
| `v9-cy-14` | Cypress | `#19`, `#10e`, bare `xit` | both skill arms |

## Labeling limits

Labels were first written by one author from the reviewer references at the frozen skill commit, before any model call on this corpus. Then a Claude subagent and Codex `gpt-5.6-sol` each labeled all 30 cases blind, from copies of the case sources and the skill only, without the corpus file. 66 of the 74 author labels matched both labelers. An arbiter subagent resolved the 8 disputed labels and 2 extra findings from quoted contract text, and the user approved the result on 2026-09-26. Each change is recorded in the label's `reason`:

- `V9-004` (`#4i` loading gate beside a positive assertion) and `V9-016` (`#19` on a never-mutated `var`) became `optional`.
- `V9-010` (`#10a` `.first()` in a page object) became a finding.
- `V9-057` (`#2` with request proof) moved from P0 to P1.
- `V9-044` accepts `#2` P0 at the status-only request as an alternative.
- New optional labels: `V9-077` (`#1` P0 on the reminder test in `v9-pw-06`), and `V9-078`/`V9-079` (`#4i` P0 beside the required `#4i` P1 in `v9-pw-02` and `v9-cy-02`, because one label keeps one severity).

Every labeler and the arbiter are models, not human experts, and the author also wrote the references the cases exercise, so the corpus can still favour one reading of them.

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v9.json
cases SHA-256: 723740ea9eb6defe4951f72f30927570d9f0e259885d1503d25b20ea6e4c3d14
corpus SHA-256: 5465a355d2126ecbda3e24822ed4e7ced43676df283a77bbf01ca377591debaf
protocol: scripts/evals/reviewer-validation-protocol-v9.json
protocol SHA-256: 133e7450f0bfecc866ad9e33111012df478f19fd60e05b9d7e88427c2cbb100d
```

The protocol binds its corpus by path and digest in a `corpus` block. The runner and comparator refuse the v9 protocol with any other corpus and refuse the v9 corpus under any other protocol. The corpus is a designed-label corpus: it declares a `labeling` block and per-case design notes instead of v8's `label_revisions`, and scoring uses the same accepted-alternatives-and-optional semantics as v8. Protocols v2–v8 keep their prompts, corpora, and scoring unchanged.

## Exact rerun command

Run the three cells sequentially from the repository root in an ordinary host shell, not from inside a Codex sandbox. A nested `codex` call from a workspace-write sandbox hangs until timeout. Start from a clean tree so every arm records the same Git provenance. Set `CODEX_RUNNER` once to the explicit executable that reports `codex-cli 0.155.1` or later; do not use a changing command name between cells. Keep all generated reports outside the checkout until the comparison is complete, then copy the four JSON artifacts into the benchmark directory.

```bash
CODEX_RUNNER=/absolute/path/to/codex
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v9"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v9 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v9.json \
  --protocol scripts/evals/reviewer-validation-protocol-v9.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-codex.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v9.json \
  --protocol scripts/evals/reviewer-validation-protocol-v9.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm catalog-only --repetitions 5 --allow-live --report-only \
  --output "$OUT/catalog-only-codex.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v9.json \
  --protocol scripts/evals/reviewer-validation-protocol-v9.json \
  --runner codex --runner-path "$CODEX_RUNNER" --model gpt-5.6-sol \
  --arm no-skill --repetitions 5 --allow-live --report-only \
  --output "$OUT/no-skill-codex.json"

python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  --cases scripts/evals/reviewer-holdout-v9.json \
  --protocol scripts/evals/reviewer-validation-protocol-v9.json \
  --compare-arms \
  --output "$OUT/arm-comparison.json"

mkdir -p benchmarks/reviewer-holdout-v9/reports
cp "$OUT/full-codex.json" \
  "$OUT/catalog-only-codex.json" \
  "$OUT/no-skill-codex.json" \
  "$OUT/arm-comparison.json" \
  benchmarks/reviewer-holdout-v9/reports/
```

The full run is exactly **450 model calls**: 30 cases x 5 repetitions x 3 prompt arms. The v8 arms of 100 calls took 17–20 minutes each, so three sequential 150-call arms are expected to take roughly 80–95 minutes under similar service conditions. The frozen hard limit remains 12 hours from the first start to the last completion.

## Claim limits

A v9 result is single-host, single-model evidence on an inspectable public development corpus whose labels were written by the author of the references under test and then checked by two blind model labelers and a model arbiter. It is not sealed, release-grade, cross-provider, cryptographically attested, or evidence of population-level generalization. A `PASS` supports only the declared development skill-lift claim for this corpus, execution, and schedule; `FAIL` or `INCONCLUSIVE` supports no skill-lift claim. The per-case expected-arm notes are the designer's predictions, not results, and a run that confirms them does not show that the cases are representative of real suites.
