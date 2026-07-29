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

```bash
# Clone the repo
git clone https://github.com/voidmatcha/e2e-skills.git
cd e2e-skills

# Exercise the scanner against any real Playwright/Cypress repo (testbed/ is gitignored)
git clone --depth 1 https://github.com/calcom/cal.diy testbed/cal.diy
bash skills/e2e-reviewer/scripts/scan.sh testbed/cal.diy

# Install the four skills as real copies for local agent testing (one-time)
bash scripts/dev/reinstall-skills.sh
```

## Verification gate (must pass before every PR)

`ci-local.sh` is the single source of truth for what CI runs. Run both of these
and confirm they are green before opening a pull request:

```bash
bash scripts/ci/ci-local.sh          # review checks + drift smoke + 0 P0 smell hits
bash scripts/ci/pre-push-security.sh # secrets and credential-leak guard
```

Useful individual stages while iterating:

```bash
bash scripts/ci/review.sh            # parity, language, links, framework scope, orphans
bash scripts/ci/test-parity.sh       # drift smoke test (mutate-and-detect) + scanner detection smoke
bash scripts/validate-evals.sh       # eval JSON schema
bash scripts/ci/codex-smoke.sh       # manual Codex cross-host smoke (skips if codex absent)
```

### Behavioral skill evaluation

`evals/evals.json` defines expected behavior, while the ordinary CI gate checks
that those contracts and fixtures remain structurally valid. To measure whether
the skill itself improves an agent's answer, run the paired behavioral harness:

```bash
python3 scripts/evals/run-behavioral-evals.py --runner codex --allow-live
# or: --runner claude --allow-live
# bounded pilot: add --case reviewer-always-true-locator --repetitions 1
```

Each case runs three times both with and without the skill. Reports are written
under the gitignored `results/behavioral-evals/` directory and include pass
rates, absolute lift, per-case results, timing, and saturated cases where the
baseline already scores 100%. Live execution is deliberately opt-in: normal CI
only tests the deterministic harness because model runs are variable and consume
time or tokens. A positive result on this small smoke set is evidence for those
cases only, not a general precision/recall or cross-model claim.

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
