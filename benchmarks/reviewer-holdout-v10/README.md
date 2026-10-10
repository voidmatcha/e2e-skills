# Reviewer holdout v10

Reviewer holdout v10 is a single-host three-arm protocol on Claude `claude-opus-5` with a new corpus. It keeps v9's prompt arms, thresholds, schedule seed, strict-majority stability rule, numbered sources, scoring contract, and five repetitions. It replaces the v9 cases with 30 new synthetic cases.

Status: **counted run is attempt 3 at `e7a9f81`; arm comparison `FAIL`, so no skill-lift claim**. The corpus is public development evidence that its author inspected while designing it; it is not sealed and does not establish generalization.

## Result

The counted run is attempt 3, in `reports/`. It made 450 calls at `e7a9f81` on Claude `claude-opus-5` with no infrastructure error. Attempts 1 and 2, in `attempts/`, were `INCONCLUSIVE` and are not counted:

- **Attempt 1:** after call 72 of the catalog-only arm, the Claude subscription's weekly usage limit refused every remaining call, and the full arm had one timeout.
- **Attempt 2:** after the limit was reset, one no-skill call (`v10-cy-11`, repetition 2) returned malformed JSON.

The skill files are identical across the three attempts. Only the benchmark tooling and documentation changed between `7e76d32` and `e7a9f81`.

| Arm | Status | Stable P / R / F1 | Repeated TP / FP / FN |
|---|---|---|---|
| full | `FAIL` (stable precision below 0.95) | 0.927 / 0.962 / 0.944 | 257 / 18 / 8 |
| catalog-only | `FAIL` (stable precision below 0.95) | 0.945 / 0.981 / 0.963 | 259 / 20 / 6 |
| no-skill | `FAIL` | 0.400 / 0.415 / 0.407 | 112 / 201 / 153 |

The arm comparison is `FAIL`:

- **Full minus no-skill** stable F1 is +0.537, with a paired 95% interval of +0.391 to +0.697. The skill's value over no skill is established on this host and corpus.
- **Full minus catalog-only** is −0.019, with an interval of −0.048 to 0.000. The full workflow references add no accuracy over the pattern catalog alone here, and the interval rules out the preregistered +0.05 lift.

The attempt-2 descriptive metrics agreed: full 0.963 and catalog-only 0.954, differing on one case.

Power depends on the host. On Claude opus the paired standard error of the full-minus-catalog stable-F1 difference was about 0.009 (attempt 2), so 30 cases detect about 0.025 at 80% power, which makes this comparison decisive. On Codex, the pre-fix v9 run gave 0.045, a detectable difference near 0.125. A pilot with the current skill gave 0.012.

## Host

V10 was preregistered for Codex `gpt-5.6-sol`, like v7–v9. Before any run, the single host was moved to Claude `claude-opus-5`. The Codex subscription quota was nearly exhausted, and the Fable model was usage-limited. Claude runs with every tool disabled and no permission mode (`claude_permission_mode: off`), so the plan-file failure that ended the v5 and v6 Claude runs cannot occur. The full versus catalog-only question is answered within this one host. The numbers are not comparable with the Codex results of v8 or v9.

## Why v10 exists

V9 ran and found no difference between the full workflow and the catalog alone. After that, the reviewer skill changed. The `SKILL.md` Quick Reference now says each listed severity is the usual case and names the documented exceptions, and `pattern-reference.md` `#1` now states a P0/P1 severity rule. Those changes were designed after v9 was seen, so v9 can no longer test them: any v9 improvement could come from fitting its cases.

V10 asks the same question on unseen cases: does the full workflow beat the catalog alone? It also asks whether severity-exception handling generalizes to cases nobody has run. The cases were designed from the reference contracts under `skills/e2e-reviewer/` alone, without reading any v9 run report or per-case v9 result, and no v5 or v9 source file, spec name, domain, or distinctive source line is reused.

The two skill arms see different reference text. The runner's `PROMPT_SKILL_PROFILES` gives the full arm `SKILL.md`, `review-scope.md`, `scanner-workflow.md`, `semantic-review.md`, `reporting.md`, `pattern-reference.md`, and `verification-rules.md`; the catalog-only arm gets `pattern-reference.md` alone; no-skill gets none. The corpus has four kinds of case:

- **Severity exceptions and boundaries (11 cases).** The `#1` P0/P1 rule, the `#23` P0 variant, the `#4` sub-ID split (`#4f` P0 against `#4c-4e` P1 on the same `toBeTruthy()` matcher, a `#4a` helper invariant), `#4k` against its contested P0 reading, `#5a` P0 against `#5b` P1, the `#8b` P0 condition, the `#12` P0 condition, the `#3`/`#15` escalation boundary, `#18` against `#3`, and the `reporting.md` P0 boundary for `#2`. Where the contract forces one severity, the other severity sits on the same line as a false-positive guard. Where it supports two readings, the second is an optional label.
- **Workflow-only rules (11 cases, one shared with the severity group).** The deciding rule is only in the full arm's extra references: `review-scope.md` framework detection by imports (a Vitest `.spec.ts` is out of scope) and project conventions (a documented quarantine list, a documented order guarantee, the nearest README for selector stability); `semantic-review.md` sweep rows (sleeps on a Frame receiver and a `setTimeout` helper, a formatter-wrapped `.only` destructure, `.clear()`/`.blur()` chains, `force: true` passed by variable or on `.trigger`) and the custom-service exclusion for `#4c-4e`; `scanner-workflow.md` and `SKILL.md` `// JUSTIFIED:` handling; and the `reporting.md` P0 boundary that makes a partly verified `#2` P1.
- **Ordinary true positives (5 cases)** that `pattern-reference.md` decides for both skill arms.
- **Clean cases (4 cases)** with only guards.

## Corpus

30 cases: 15 Playwright and 15 Cypress, each a small repository slice (spec plus any page object, fixture, support file, config, README, or application component it needs) under `scripts/evals/files/holdout-v10/<case-id>/`. Every case has a `design_note` naming the arm expected to get it right and why, and every label has a `reason` that quotes or cites the reference rule that decides it. Case and label IDs (`v10-pw-01`, `V10-001`) are independent of v5 and v9.

| Kind | P0 | P1 | P2 | Total |
|---|---|---|---|---|
| finding | 12 | 36 | 5 | 53 |
| fp_guard | 17 | 29 | 4 | 50 |
| optional | 7 | 3 | 1 | 11 |

False-positive guards are 45% of labels. Four cases are clean (only guards): `v10-pw-14`, `v10-pw-15`, `v10-cy-14`, `v10-cy-15`. Five finding labels carry `accepted_alternatives` where two tuples describe the same single defect: a gated assertion's `if` and the assertion inside it, a sleep helper's call and definition, a formatter-wrapped `.only` alias call and its destructure, a `force: true` option and the constant that holds it, and `#14` beside `#17` on one hard-coded login line.

Labels use instance severities that the references define but the Quick Reference does not list, and the corpus validator accepts them only in a designed-label corpus: `#1` at P1 when one promised outcome is verified and another is not (`v10-cy-01`), `#2` at P1 when one promised effect is verified and another is not (`v10-cy-05`), and `#23` at P0 when a guard-suppressed render lets an empty-state check pass (`v10-cy-02`). Each such finding has a guard at the catalog severity on the same line, so reporting the wrong severity costs a false positive and a miss. V10 adds one instance severity to the validator: `#4k` at P0, used only on an optional label beside the required `#4k` P1 (`v10-pw-04`). Its basis is `pattern-reference.md` placing `#4k` "with the silent-always-pass family" and `reporting.md` allowing an instance to be "reported higher when it meets the P0 definition outright". The runner keeps one severity per label, so the P0 reading is an optional label, not an accepted alternative.

| Case | Framework | Theme | Expected to succeed |
|---|---|---|---|
| `v10-pw-01` | Playwright | `toBeTruthy()` on a Locator (`#4f` P0) vs on an awaited read (`#4c-4e` P1) | both skill arms |
| `v10-pw-02` | Playwright | clamped helper makes `>= 0` vacuous (`#4a` P0); polled bound guard | both skill arms |
| `v10-pw-03` | Playwright | discarded `isVisible()` as the only check (`#8b` P0) vs a pre-check before a click | both skill arms |
| `v10-pw-04` | Playwright | `#4k` loop over an unproven collection (P1; optional P0); counted loop guard | both skill arms (P1); contract boundary (P0) |
| `v10-pw-05` | Playwright | awaited matcher swallowed by `.catch` (`#3` P0) vs unawaited matcher (`#15` P1) | both skill arms |
| `v10-pw-06` | Playwright | soft prerequisite (`#18` P1, not `#3`); terminal soft details guard | both skill arms |
| `v10-pw-07` | Playwright | Vitest `.spec.ts` out of scope; re-exported Playwright fixture in scope (`#9`) | full |
| `v10-pw-08` | Playwright | `setTimeout` sleep helper and `Frame.waitForTimeout` (`#9`); fake clock guard | full |
| `v10-pw-09` | Playwright | custom service read is not `#4c-4e`; Locator read is; optimistic favourite (`#22`) | full (guard) |
| `v10-pw-10` | Playwright | JUSTIFIED above `evaluate` covers its callback; sibling `#6`; vague JUSTIFIED on `#4f` | full |
| `v10-pw-11` | Playwright | nearest README decides `#10c` (fixed tab names vs free-text link names); `#4j` | full |
| `v10-pw-12` | Playwright | `#17`, `#14`, `#16`, `#4h`, bypassed POM method (`#13`) | both skill arms |
| `v10-pw-13` | Playwright | `#10b`, `#19` in a support helper, `#9c`, bare `test.skip` | both skill arms |
| `v10-pw-14` | Playwright | clean: proven absence, counted `.first()`, polled read, reasoned skip | both skill arms |
| `v10-pw-15` | Playwright | clean: awaited `Promise.all`, read inside `toPass`, injected preload link | both skill arms |
| `v10-cy-01` | Cypress | `#1` partial title (P1) vs value title with visibility only (P0) | both skill arms |
| `v10-cy-02` | Cypress | `#23` P0 (date guard empties an empty-state check) vs `#23` P2 (skipped item) | both skill arms (severity); full (anchor) |
| `v10-cy-03` | Cypress | conditional forced dismissal (`#5b` P1, not `#5a`) vs gated assertion (`#5a` P0) | both skill arms |
| `v10-cy-04` | Cypress | sign-in URL satisfies `include 'rota'` (`#12` P0) vs a check it cannot satisfy | both skill arms |
| `v10-cy-05` | Cypress | request proof but unchecked list removal (`#2` P1) vs nothing verified (`#2` P0) | full |
| `v10-cy-06` | Cypress | documented quarantine list decides `#11c`; `#9b` | full |
| `v10-cy-07` | Cypress | documented order guarantee suppresses one `#10a`, not the other | full |
| `v10-cy-08` | Cypress | formatter-wrapped `const { only: ... } = it` (`#7`); unrelated `only` helper guard | full |
| `v10-cy-09` | Cypress | `.clear().should()` and `.blur().should()` chains (`#10f`) | full |
| `v10-cy-10` | Cypress | `force: true` by variable on `.trigger` and on `.dblclick` (`#5b`); JUSTIFIED `.select` guard | full |
| `v10-cy-11` | Cypress | parameterised blanket `uncaught:exception` (`#3b`), `#9b`, Cypress `timeout: 0` (`#4g`) | both skill arms |
| `v10-cy-12` | Cypress | `#14` login request, async `it` (`#10d`), assigned command (`#10e`); `#16` guard | both skill arms |
| `v10-cy-13` | Cypress | unstubbed RSVP to shared staging (`#20`), replayed session cookie (`#21`), unused command (`#11`) | both skill arms |
| `v10-cy-14` | Cypress | clean: scoped exception allowlist, counted `.each`, stubbed write with request proof | both skill arms |
| `v10-cy-15` | Cypress | clean: Playwright-only `#8a`/`#15` do not apply to Cypress; proven absence; API session | full (guards) |

## Labeling

One author wrote the labels from the reviewer references at the frozen skill commit, before any model call on this corpus and without reading any earlier run report. Each label's `reason` quotes or cites the rule that decides it, and each case's `design_note` records the arm expected to get it right.

Then, as for v9, a Claude subagent and Codex `gpt-5.6-sol` each labeled all 30 cases blind, from copies of the case sources and the skill only, without the corpus file. 100 of the 103 finding and guard labels matched both labelers. An arbiter subagent resolved 4 disputes from quoted contract text, and the user approved the result on 2026-09-26. Each change is recorded in the label's `reason`:

- `V10-043` (`#17` on a hard-coded login line) accepts `#14` on the same line as the same finding, under `semantic-review.md`'s consolidation rule.
- `V10-046`, formerly the optional `#14` on that line, is now the optional `#13` at `v10-pw-12` line 14, because the `#13` rule reads both ways there.
- New optional labels: `V10-113` (`#20` on an unstubbed waitlist write with no environment evidence) and `V10-114` (`#11` on a single-use helper, which `semantic-review.md` calls a review candidate, not an automatic finding).

Eleven labels are `optional` because the references support two readings. Every labeler and the arbiter are models, not human experts, and the author also wrote the references the cases exercise, so the corpus can still favour one reading of them.

## Frozen inputs

```text
cases file:  scripts/evals/reviewer-holdout-v10.json
cases SHA-256: 6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e
corpus SHA-256: 672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d
protocol: scripts/evals/reviewer-validation-protocol-v10.json
protocol SHA-256: 186680ad624f9ae40ff0b652ee4949322fb6ccfac5e5426a4b7c182278f33c39
```

The protocol binds its corpus by path and digest in a `corpus` block. The runner and comparator refuse the v10 protocol with any other corpus and refuse the v10 corpus under any other protocol. The protocol differs from v9 only in `protocol_id`, `corpus`, `schedule.design_disclosure`, and the disclosed host move: `host_matrix`, `execution_identity` (a `Claude Code 2.1.281` floor and `claude_permission_mode: off`), the host named in each `arm_comparison.execution_order` step, and the single-host wording of `cross_host_decision`. Protocols v2–v9 keep their prompts, corpora, and scoring unchanged; the one shared change is that the designed-corpus validator now also accepts `#4k` at P0, which no v9 label uses.

## Exact rerun command

Run the three cells sequentially from the repository root in an ordinary host shell. Start from a clean tree so every arm records the same Git provenance. Set `CLAUDE_RUNNER` once to the explicit executable that reports `Claude Code 2.1.281` or later; do not use a changing command name between cells. Keep all generated reports outside the checkout until the comparison is complete, then copy the four JSON artifacts into the benchmark directory.

```bash
CLAUDE_RUNNER=/absolute/path/to/claude
OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v10"
test -z "$(git status --porcelain)" || { echo "reviewer holdout v10 requires a clean tree" >&2; exit 1; }
mkdir -p "$OUT"

python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v10.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-opus-5 \
  --arm full --repetitions 5 --allow-live --report-only \
  --output "$OUT/full-claude.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v10.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-opus-5 \
  --arm catalog-only --repetitions 5 --allow-live --report-only \
  --output "$OUT/catalog-only-claude.json"
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v10.json \
  --runner claude --runner-path "$CLAUDE_RUNNER" --model claude-opus-5 \
  --arm no-skill --repetitions 5 --allow-live --report-only \
  --output "$OUT/no-skill-claude.json"

python3 scripts/evals/compare-reviewer-holdouts.py \
  "$OUT/full-claude.json" \
  "$OUT/catalog-only-claude.json" \
  "$OUT/no-skill-claude.json" \
  --cases scripts/evals/reviewer-holdout-v10.json \
  --protocol scripts/evals/reviewer-validation-protocol-v10.json \
  --compare-arms \
  --output "$OUT/arm-comparison.json"

mkdir -p benchmarks/reviewer-holdout-v10/reports
cp "$OUT/full-claude.json" \
  "$OUT/catalog-only-claude.json" \
  "$OUT/no-skill-claude.json" \
  "$OUT/arm-comparison.json" \
  benchmarks/reviewer-holdout-v10/reports/
```

The full run is exactly **450 model calls**: 30 cases x 5 repetitions x 3 prompt arms. The frozen hard limit remains 12 hours from the first start to the last completion.

## Claim limits

A v10 result is single-host, single-model evidence (Claude `claude-opus-5`) on an inspectable public development corpus whose labels were written by the author of the references under test and then checked by two blind model labelers and a model arbiter. It is not sealed, release-grade, cross-provider, cryptographically attested, or evidence of population-level generalization. A `PASS` supports only the declared development skill-lift claim for this corpus, execution, and schedule; `FAIL` or `INCONCLUSIVE` supports no skill-lift claim. A severity-exception case that the full arm gets right shows that the documented exception was applied to an unseen case of this design, not that the exception wording is correct in general. The per-case expected-arm notes are the designer's predictions, not results, and a run that confirms them does not show that the cases are representative of real suites.
