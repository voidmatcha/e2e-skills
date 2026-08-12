# Contributing to e2e-skills

Thanks for your interest in improving `e2e-skills`. This project is a bundle of
four Agent Skills plus a deterministic scanner for silent-pass Playwright and
Cypress tests. Contributions of all sizes are welcome — a new false-positive
guard, a clearer skill instruction, a translation fix, or a whole new anti-pattern.

For the deep, cross-agent canonical reference (directory layout, parity surfaces,
severity rationale), read [`AGENTS.md`](./AGENTS.md). This file is the shorter,
human-facing entry point.

## Code of conduct

Be respectful and constructive. We follow the spirit of the
[Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/):
no harassment, assume good faith, critique the work and not the person. Report
concerns via a private message to the maintainer or a GitHub issue.

## Ways to contribute

- **Report a bug or false positive.** Open an issue with the exact spec snippet,
  the pattern ID or failure code involved, and what the scanner or skill did
  versus what you expected. A minimal reproducing fixture is the fastest path to
  a fix.
- **Improve a skill.** Sharpen a detection instruction, add a missing
  false-positive guard, or fix a report-parsing mismatch.
- **Propose an anti-pattern or failure category.** New silent-pass smells are
  welcome, but IDs and severities are a stable contract — see below.
- **Improve docs or translations.** English is canonical; translated READMEs are
  a sanctioned exception (see [Translations](#translations)).

The project is **Playwright and Cypress only**. It does not accept code or advice
for Puppeteer, Selenium, WebdriverIO, TestCafe, or Nightwatch. See
[`docs/framework-scope.md`](./docs/framework-scope.md) for the rationale; CI
fails on accidental support claims for out-of-scope frameworks.

## Development setup

The full local CI mirror targets macOS and Linux with `/bin/bash`, a
PCRE2-capable `rg`, and Python 3.10 or newer. Its frozen prompt-size replay also
requires CPython 3.12 and access to the hash-locked Python packages (from a
local cache or PyPI). For its trust boundary, the gate
discovers interpreters only at standard system and Homebrew prefixes; a
Nix-, Conda-, or pyenv-only layout is not currently auto-discovered. GitHub CI
runs the full mirror on Ubuntu and a smaller portability contract on both
Ubuntu and macOS.

Hard-wrap ordinary prose when it makes reviews easier. Do not mechanically
reflow Markdown table rows, shell commands, URLs, hashes, or frozen JSON/log
evidence: their physical line boundaries are structural or evidence-bearing.
Keep each table row on one physical line, and split a command only with an
explicit shell continuation.

```bash
# Clone the repo
git clone https://github.com/voidmatcha/e2e-skills.git
cd e2e-skills

# Exercise the scanner against any real Playwright/Cypress repo (testbed/ is gitignored)
git clone --depth 1 https://github.com/calcom/cal.diy testbed/cal.diy
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh testbed/cal.diy

# Install the four skills as real copies for local agent testing (one-time)
bash scripts/dev/reinstall-skills.sh
```

## Verification gate (must pass before every PR)

`ci-local.sh` is the single source of truth for what CI runs. Run both of these
and confirm they are green before opening a pull request:

```bash
/bin/bash -p scripts/ci/ci-local.sh          # review checks + drift smoke + 0 P0 smell hits
/bin/bash -p scripts/ci/pre-push-security.sh # secrets and credential-leak guard
```

Useful individual stages while iterating:

```bash
bash scripts/ci/review.sh            # parity, language, links, framework scope, orphans
bash scripts/ci/test-parity.sh       # drift smoke test (mutate-and-detect) + scanner detection smoke
bash scripts/ci/check-verification-parity.sh # V1-V6 contract parity
bash scripts/ci/test-codex-agents.sh # optional Codex agent packaging contract
bash scripts/ci/test-local-eslint-path.sh # local lint + disabled-rule fail-closed path
bash scripts/validate-evals.sh       # eval JSON schema
bash scripts/ci/test-reviewer-holdout.sh # labeled TP/FP/FN scorer + isolation
python3 scripts/ci/test-reviewer-holdout-v3.py # all-family corpus + N-configuration contracts
/bin/bash -p scripts/ci/run-reference-tokenizer-suites.sh \
  scripts/ci/test-independent-review-v7.py \
  scripts/ci/test-independent-review-v10.py # v7/v10 preregistration + runner fail-closed contracts
                                     # (needs the pinned tokenizer venv; the suites fail closed without it)
/bin/bash -p scripts/ci/run-independent-review-v10-evidence.sh # v10 archive state + prompt-size replay
python3 scripts/ci/test-reviewer-scanner.py # P0 gate + missing-await context regression
python3 scripts/ci/test-debugger-contracts.py # debugger extraction + dedupe contracts
python3 scripts/ci/test-residual-redos-budget.py # credential-regex linearity budget
python3 scripts/ci/test-reviewer-evidence-v3.py # reparse and rescore v3 raw reports
python3 scripts/ci/test-reviewer-evidence.py # immutable reports + aggregate replay
python3 scripts/ci/test-fixture-faults.py # browser-free 36-cell classifier regression
python3 scripts/evals/run-fixture-faults.py --validate-only # browser-free fixture contract
bash scripts/ci/codex-smoke.sh       # manual Codex cross-host smoke (skips if codex absent)
```

### Reviewer accuracy and behavior validation

`evals/evals.json` defines expected behavior, while the ordinary CI gate checks
that those contracts and fixtures remain structurally valid. The labeled
development holdout adds exact TP/FP/FN scoring over isolated multi-file
Playwright/Cypress cases:

```bash
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v3.json \
  --protocol scripts/evals/reviewer-validation-protocol-v3.json \
  --runner codex --model gpt-5.6-sol --repetitions 3 --allow-live
# Repeat with:
#   --runner claude --model claude-opus-5
#   --runner claude --model claude-fable-5
```

The current v3 corpus has eight multi-file cases, 24 findings covering all 24
base pattern families, and 24 explicit false-positive guards. It is public, so
it is a reproducible development holdout, not a secret release oracle. The
historical v2/r3 corpus has 30 findings and 31 guards, but its performance
estimate was oracle-invalidated after post-run adjudication. Pass an external
corpus with `--cases` for a sealed run, inside an independently isolated
environment supplied through `--isolation-wrapper <executable>`.
Reports under `benchmarks/reviewer-holdout-v3/reports/` include corpus/model/CLI/Git provenance,
the evaluated-skill and protocol digests, seeded schedule, raw outputs, per-case
TP/FP/FN, unique majority-stable precision/recall, repeated-run metrics, and
Wilson intervals. Public runs use one immutable skill/corpus input snapshot,
fresh temporary workspaces, Codex/Claude read-only controls, and pre/post
digests of every staged path and original input. A changed digest is an
infrastructure error and is not scored. The release gate also enforces repeated
precision so rotating one-off false positives cannot disappear under majority
aggregation. The runner does not provide a built-in sealed sandbox; non-public
corpora fail closed without the external wrapper.

After all three live reports complete, enforce the declared
cross-configuration gate:

```bash
python3 scripts/evals/compare-reviewer-holdouts.py \
  <codex-report.json> <opus-report.json> <fable-report.json> \
  --cases scripts/evals/reviewer-holdout-v3.json \
  --protocol scripts/evals/reviewer-validation-protocol-v3.json
```

The comparator requires the exact declared runner/model configuration matrix and identical
skill, corpus, protocol, schedule, and repetition provenance. It re-parses raw
outputs and re-derives every run score, metric, and status before checking that
all three declared model configurations pass individually, the maximum
pairwise stable-recall gap is at
most 10 percentage points, and the minimum pairwise stable-prediction Jaccard
agreement is at least 0.80. Runner/model/CLI fields are declared local
provenance, not signed or remotely attested identity; a release claim needs an
externally controlled runner if host authenticity matters.

Historical v2 public-development reports and oracle corrections are frozen
under `benchmarks/reviewer-holdout-v2/`. The v3 source-only oracle audit,
completed Codex report, and preserved incomplete Claude attempts live under
`benchmarks/reviewer-holdout-v3/`. CI accepts the v3 evidence manifest only
after all three declared reports exist and re-derives the documented
aggregates from raw model output. Never rewrite an old report after post-run
adjudication; add an explicit revision or adjudication record instead.

To prove the smell has a real behavioral consequence, install the fixture-only
dependencies and run the fault matrix:

```bash
npm ci --prefix scripts/evals/fixtures
python3 scripts/evals/run-fixture-faults.py
```

Across twelve fault operators and 36 browser cells, the strong test must pass on
the correct app and fail after behavior fault injection; the assertion-mutated
or call-proof-mutated weak test must remain green against the same fault.

The older paired behavioral harness still measures whether loading a skill
improves a bounded answer:

```bash
python3 scripts/evals/run-behavioral-evals.py --runner codex --allow-live
# or: --runner claude --allow-live
# bounded pilot: add --case reviewer-always-true-locator --repetitions 1
```

Each case runs three times both with and without the skill. Reports are written
under the gitignored `results/behavioral-evals/` directory and include pass
rates, absolute lift, per-case results, timing, and saturated cases where the
baseline already scores 100%. Live execution is deliberately opt-in: normal CI
only tests deterministic harnesses because model and browser runs are variable
and consume time, tokens, or downloads. A positive result on either small public
set is evidence for those cases only, not a general cross-model superiority
claim.

## Conventions

These are enforced by CI. Breaking one fails the build.

- **Pattern IDs are frozen.** 24 anti-pattern entries (`#1`–`#23` plus `#3b`),
  each with a P0/P1/P2 severity. Do not renumber, remove, or change the severity
  of an existing ID — downstream evals and external adopters depend on them.
  Severity meaning: **P0** = silently always passes, **P1** = poor diagnostics,
  **P2** = maintenance.
- **Failure codes are frozen.** 15 debugger failure categories (`F1`–`F15`),
  shared by both debuggers. Do not renumber.
- **English-only public surface.** `README.md`, `SKILL.md`, and `docs/` are
  English; CI enforces this. The sanctioned exception is root-level
  `README.<lang>.md` translations and the language-switcher line that links to
  them.
- **Severity-first ordering.** Tables in `SKILL.md`, `README.md`, and
  `docs/e2e-test-smells.md` group by P0/P1/P2 in the same order.
- **`// JUSTIFIED: <reason>` comments** suppress a scanner finding on the line
  (or block) below. Use them for documented intent, never to hide a real
  finding. `#7` (focused tests) has no exemption.

## Changing an anti-pattern or skill behavior

Pattern and failure-code semantics live in several files that must move together.
CI fails fast if any one drifts. When you add or rename a pattern, update all of:

- the relevant `skills/<name>/SKILL.md` (Quick Reference),
- `skills/e2e-reviewer/references/pattern-reference.md` (the per-pattern contract),
- `docs/e2e-test-smells.md`,
- the `README.md` pattern table,
- `skills/e2e-reviewer/references/grep-patterns.md`,
- `skills/e2e-reviewer/scripts/scan.sh`,
- the three plugin manifest descriptions (`.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json`, `.codex-plugin/plugin.json`).

Then:

1. **Re-run the drift smoke test** (`scripts/ci/test-parity.sh`) and keep it green.
2. **Add or update evals.** Each behavior change needs at least two assertions in
   the skill's `evals/evals.json`: one true positive that must be flagged, and one
   false-positive guard that names the exact line and why it must not be flagged.
3. **Respect the severity contract.** P0 entries are silent-always-pass smells;
   do not downgrade them or promote P1/P2 into P0 just because they are easier to
   grep.

## Translations

Translated READMEs (`README.ko.md`, `README.ja.md`, `README.zh-cn.md`) follow the
English `README.md`, which is canonical and may be newer. When you touch the
English README, either update the translations in the same PR or note in the PR
description that they now lag. New-language translations are welcome — mirror the
structure of an existing one, keep the language-switcher line, and never
translate code blocks, commands, pattern IDs, or failure codes.

## Pull request process

1. Keep the change focused; unrelated cleanup belongs in a separate PR.
2. Run the verification gate above and confirm it is green.
3. Write a descriptive title and a body that explains the *why*, links any
   related issue, and calls out any parity surface you touched.
4. For a new anti-pattern, include the fixtures and eval assertions in the same PR.

## License

By contributing, you agree that your contributions are licensed under the
[Apache-2.0](./LICENSE) license, the same as the project. Match the parent
license header in any new file you add.
