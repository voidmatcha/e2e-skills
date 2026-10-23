# Contributing to e2e-skills

Thanks for your interest in improving `e2e-skills`. This project is a bundle of four Agent Skills plus a deterministic scanner for silent-pass Playwright and Cypress tests. Contributions of all sizes are welcome — a new false-positive guard, a clearer skill instruction, a translation fix, or a whole new anti-pattern.

For the deep, cross-agent canonical reference (directory layout, parity surfaces, severity rationale), read [`AGENTS.md`](./AGENTS.md). This file is the shorter, human-facing entry point.

## Code of conduct

Be respectful and constructive. We follow the spirit of the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/): no harassment, assume good faith, critique the work and not the person. Report concerns via a private message to the maintainer or a GitHub issue.

## Ways to contribute

- **Report a bug or false positive.** Open an issue with the exact spec snippet, the pattern ID or failure code involved, and what the scanner or skill did versus what you expected. A minimal reproducing fixture is the fastest path to a fix.
- **Improve a skill.** Sharpen a detection instruction, add a missing false-positive guard, or fix a report-parsing mismatch.
- **Propose an anti-pattern or failure category.** New silent-pass smells are welcome, but IDs and severities are a stable contract — see below.
- **Improve docs or translations.** English is canonical; translated READMEs are a sanctioned exception (see [Translations](#translations)).

The project is **Playwright and Cypress only**. It does not accept code or advice for Puppeteer, Selenium, WebdriverIO, TestCafe, or Nightwatch. See [`docs/framework-scope.md`](./docs/framework-scope.md) for the rationale; CI fails on accidental support claims for out-of-scope frameworks.

## Contribution tiers

Not every change needs the same amount of process. Which tier a change falls into decides what you need before opening a PR.

| Tier | What it covers | What you need |
| --- | --- | --- |
| **0 — Docs & typos** | Wording, comments, and typo fixes that do not change installed skill behavior, regardless of file location | A passing changed-file CI run; shared security, syntax and document checks still apply |
| **1 — Skill behavior wording** | Any behavior-affecting instruction edit that does not change a pattern ID, F-code, or verdict term, including `skills/*/SKILL.md` and point-of-use procedure files such as `classification-procedure.md`, `safety-procedures.md`, and `semantic-review.md`. A mechanical sub-ID under an existing pattern (for example `#8c` under `#8`) is also Tier 1 when it changes no existing ID, title, or severity and its scanner shape is syntactically certain and contract-tested with a true positive and a false-positive guard; it claims no detection rate | A RED/GREEN contract test proving the old wording violated your intent and the new wording satisfies it (see `scripts/ci/test-routing-contract.py` for a worked example), then changed-file CI green; `scripts/dev/tier1-check.sh` remains the full-gate alternative |
| **2 — Taxonomy / decision-surface change** | New or renumbered top-level pattern IDs, F-codes, verdict vocabulary, severity changes, or a delegation-routing decision not yet backed by measured evidence | A new preregistered study preserved on Hugging Face, with its protocol and evidence linked from `benchmarks/STATUS.md`; use the archived routing and stub-echo studies as examples. Required for a new correctness claim about the skills themselves |

Most contributions are Tier 0 or Tier 1. Issues labeled `good first issue` do not require changing frozen studies. The four directories under `skills/` are the product. Current CI and eval harnesses remain in Git with small regression fixtures; historical reports, protocols and frozen inputs live in the pinned Hugging Face snapshot indexed by [benchmark status](benchmarks/STATUS.md).

## Development setup

Bundled debugger helpers must remain compatible with Python 3.9, the oldest system interpreter their trusted launcher may select. Keep newer Python APIs out of those helpers; the launcher's fixed interpreter policy is not a dependency-upgrade mechanism.

The default local CI mirror targets macOS and Linux with `/bin/bash`, a PCRE2-capable `rg`, and Python 3.10 or newer. The separate historical evidence replay may also require CPython 3.12 and hash-locked packages from a local cache or PyPI. Trusted interpreter discovery uses standard system and Homebrew prefixes; a Nix-, Conda-, or pyenv-only layout is not currently auto-discovered. GitHub CI runs the default mirror on Ubuntu and a smaller portability contract on Ubuntu and macOS.

Write each ordinary prose paragraph as one physical line, not hard-wrapped at a fixed column: this repo cites exact `file:line` locations from eval assertions and CI parity checks, and a hard-wrapped paragraph cascades every following line number on any edit inside it, while a single-line paragraph only shifts line numbers when whole paragraphs are added or removed. Do not mechanically reflow Markdown table rows, shell commands, URLs, hashes, or frozen JSON/log evidence: their physical line boundaries are structural or evidence-bearing. Keep each table row on one physical line, and split a command only with an explicit shell continuation.

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

## Verification gate

`ci-local.sh` owns every check command. During development and before a pull request, select checks from the merge-base comparison plus staged, unstaged and nonignored untracked changes:

```bash
/bin/bash -p scripts/ci/ci-local.sh --changed origin/main --plan
/bin/bash -p scripts/ci/ci-local.sh --changed origin/main
/bin/bash -p scripts/ci/pre-push-security.sh
```

`--plan` prints the selected groups and reasons without executing the suites. Shared security, syntax, documentation and contract checks always run during a scoped execution. The selector includes deleted paths and both sides of renames. Shared infrastructure changes, unknown paths or an unavailable comparison select the full suite. Scoped success lists what was omitted and does not claim full validation.

Pull-request CI uses the same selector against the PR base. Main pushes and manual workflow runs execute the full suite. Before a release, run the full suite on the final stable snapshot:

```bash
/bin/bash -p scripts/ci/ci-local.sh --full
/bin/bash -p scripts/ci/pre-push-security.sh
```

No arguments still run the full suite; `--quiet` changes output only. A scoped run does not replace the release gate, the Linux shipped-script checks or the generator host smoke tests required for relevant behavior changes.

`ci-local.sh` runs one Node.js stage and resolves Node from `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`, or `/bin`. If your Node comes from a version manager (nvm, fnm, asdf), point the gate at it explicitly:

```bash
E2E_SKILLS_NODE_BIN="$(command -v node)" /bin/bash -p scripts/ci/ci-local.sh
```

The override clears the same checks as the defaults: it must be an absolute path to a regular executable file that is not group- or world-writable and does not live inside the repository. A Node the gate cannot trust fails the stage rather than being used.

Selected focused checks are listed below. The default gate validates the current product and common harness regressions using local fixtures; historical result replay is a separate opt-in command described under [Benchmark evidence](#benchmark-evidence).

```bash
bash scripts/ci/review.sh
bash scripts/ci/test-parity.sh
bash scripts/ci/check-verification-parity.sh
bash scripts/ci/test-local-eslint-path.sh
python3 scripts/ci/test-eslint-import-resolution.py
bash scripts/validate-evals.sh
bash scripts/ci/test-reviewer-holdout.sh
python3 scripts/ci/test-reviewer-scanner.py
python3 scripts/ci/test-debugger-contracts.py
python3 scripts/ci/test-generator-router.py
python3 scripts/ci/test-external-evidence.py
python3 scripts/dev/reviewer-contract.py
```

### Reviewer accuracy and behavior validation

Reviewer development results are model-specific: [v22](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/reviewer-holdout-v22/README.md) passed on Codex `gpt-6-sol`, while [v23](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/blob/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254/benchmarks/reviewer-holdout-v23/README.md) failed on `gpt-6-luna`. Each scored all 540 calls on the same 36 reused public cases and frozen reviewer snapshot; neither measures the later scanner/configuration changes. These tool-free comparisons do not measure scanner execution or sealed release accuracy.

Reviewer results apply to their recorded model, corpus and evaluated skill snapshot. See [benchmark status](benchmarks/STATUS.md) for outcomes and limits; study READMEs, reports and exact reproduction commands are preserved in the external snapshot. Historical measurements do not validate later product changes. Public cases and repeated runs do not establish sealed release accuracy or general cross-model superiority.

`evals/evals.json` defines expected behavior. Ordinary CI verifies product contracts, local fixtures and common harness regressions. New live studies require a preregistered protocol, immutable inputs, recorded model/CLI/environment identity and a complete schedule; preserve failures and incomplete attempts. Do not rewrite old reports or their digests after a product edit or adjudication: add a new study or explicit revision.

For TP/FP/FN counts, precision/recall and presentation tables, use the offline [classification report](scripts/evals/classification-report/README.md). It rescores existing finding holdouts through the canonical comparator, or measures a new fixed binary-unit study with an explicitly defined TN denominator. Missing decisions and execution errors remain separate; Promptfoo can display the results without a model grader. For a prospective same-model comparison with actual coordinator-run CLI evidence, use the opt-in [finite-unit study](scripts/evals/classification-study/README.md); its authored units and tool-disabled model calls do not establish interactive workflow quality.

Follow [AGENTS.md's runner contract](AGENTS.md#local-development-commands) for built-in public versus external corpora, isolated workspaces, credential routing and pre/post input digests. For `scripts/evals/run-reviewer-holdout.py`, external `--cases` bundles always require `--isolation-wrapper`, even when labeled public. The wrapper does not establish isolation by itself, and the bundled harness keeps wrapped evidence `INCONCLUSIVE`. Local runner/model strings are provenance, not signed identity. Comparators must reparse raw outputs, rederive scores and enforce the protocol's declared model matrix and thresholds before accepting any result.

To prove the smell has a real behavioral consequence, install the fixture-only dependencies and run the fault matrix:

```bash
npm ci --prefix scripts/evals/fixtures
python3 scripts/evals/run-fixture-faults.py
```

Across twelve fault operators and 36 browser cells, the strong test must pass on the correct app and fail after behavior fault injection; the assertion-mutated or call-proof-mutated weak test must remain green against the same fault.

For reviewer replacement changes, run `node scripts/evals/run-assertion-contract-probes.cjs` with the same fixture dependencies and an available Chromium binary. It executes the documented replacements against raw-text, exact-membership, and compound-visibility counterexamples; it does not update frozen benchmark reports. The dependency-free `scripts/ci/test-assertion-contracts.py` guards the corresponding guidance in ordinary CI.

The older paired behavioral harness still measures whether loading a skill improves a bounded answer:

```bash
python3 scripts/evals/run-behavioral-evals.py --runner codex --allow-live
# or: --runner claude --allow-live
# bounded pilot: add --case reviewer-always-true-locator --repetitions 1
```

Each case runs three times both with and without the skill. Reports are written under the gitignored `results/behavioral-evals/` directory and include pass rates, absolute lift, per-case results, timing, and saturated cases where the baseline already scores 100%. The hosted `main` workflow automatically reruns the pinned 36-cell browser fault matrix on a disposable runner. The scanner CI group uses Node 22 or newer and installs the Node package's exact locked dependencies in an external temporary source copy with lifecycle scripts disabled. The source checkout stays unchanged. Live model runs and the other browser probes stay opt-in because they are variable or consume tokens and downloads. A positive result on either small public set is evidence for those cases only, not a general cross-model superiority claim.

## Benchmark evidence

The authoritative historical research archive is the Hugging Face dataset [`voidmatcha/e2e-skills-benchmarks`](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks). The [source snapshot](https://huggingface.co/datasets/voidmatcha/e2e-skills-benchmarks/tree/2992d57564bb5b0d7eae0650a64f392481211d41/snapshots/git-93afd3b105b869b15589634c88676230c7d92254) is pinned to its publication revision. Git keeps [benchmark status](benchmarks/STATUS.md), the [snapshot manifest](benchmarks/external-evidence.json), current harness code and small regression fixtures under `scripts/`. Historical reports, protocols, frozen inputs, source snapshots, adjudications and raw artifacts belong in the external archive.

The manifest pins a full 40-character dataset revision, source Git commit, archive and metadata paths, SHA-256 hashes, file count and byte count. The public restore tool needs only Python's standard library; it checks archive and metadata hashes, rejects unsafe tar entries, and verifies every original file's SHA-256, Git blob identity and mode. It creates a new external directory and refuses to overwrite an existing path.

```bash
/bin/bash -p scripts/dev/fetch-benchmark-evidence.sh --dry-run
/bin/bash -p scripts/dev/fetch-benchmark-evidence.sh --output /absolute/new-evidence-root
/bin/bash -p scripts/dev/fetch-benchmark-evidence.sh --verify-only --output /absolute/new-evidence-root
/bin/bash -p scripts/ci/ci-evidence.sh /absolute/new-evidence-root
```

`ci-evidence.sh` verifies the restored snapshot, downloads and verifies the separately pinned source archive, and runs the original CI with the restored `benchmarks/` in a temporary workspace. The source commit need not exist locally. A synthetic Git HEAD supplies the tracked-file context; it is reported separately from the original `source_commit`. Its historical dependencies, including the pinned tokenizer environment, may be required. This reproduces historical checks; run `ci-local.sh` separately to verify the current product. Neither restoration nor replay authorizes live model or browser experiments.

For a new study, preregister its protocol and retain the evaluated skill snapshot, corpus and protocol digests, execution environment, validity checks, licenses and redistribution rights. Distinguish unique cases from repetitions. Preserve negative, failed, incomplete and invalid outcomes with their limits; never amend frozen evidence to match a changed product.

Build uploads from a strict file allowlist. Exclude credentials, auth files, environment files, cookies, browser profiles and home directories. Review transcripts and artifacts for sensitive content before upload. Preserve original evidence; record every redaction or normalization and both source and derived SHA-256 hashes.

Upload only with explicit user authorization. Pin the resulting dataset commit, download it afresh and verify all hashes before removing tracked evidence. Audit CI dependencies and retain needed product regression fixtures locally. Preserve local originals and Git history; removal from the tip does not remove historical blobs from ordinary full clones. Keep default offline CI independent of network downloads. New publication batches get their own identifiers and receipts rather than replacing existing frozen paths.

## Conventions

These are enforced by CI. Breaking one fails the build.

- **Pattern IDs are frozen.** 24 anti-pattern entries (`#1`–`#23` plus `#3b`), each with a P0/P1/P2 severity. Do not renumber, remove, or change the severity of an existing ID — downstream evals and external adopters depend on them. Severity meaning: **P0** = silently always passes, **P1** = poor diagnostics, **P2** = maintenance.
- **Failure codes are frozen.** 15 debugger failure categories (`F1`–`F15`), shared by both debuggers. Do not renumber.
- **English-only public surface.** `README.md`, `SKILL.md`, and `docs/` are English; CI enforces this. The sanctioned exception is root-level `README.<lang>.md` translations and the language-switcher line that links to them.
- **Severity-first ordering.** Tables in `SKILL.md`, `README.md`, and `docs/e2e-test-smells.md` group by P0/P1/P2 in the same order.
- **`// JUSTIFIED: <reason>` comments** document an intentional exception at the matching expression or supported callback/chain boundary, not an entire test or `describe` block. P0 candidates remain visible until the rationale is verified; `#7` (focused tests) has no exemption. Follow the exact [suppression rules](skills/e2e-reviewer/references/scanner-workflow.md#phase-1-mechanical-scan), never use a marker to hide a real finding.
- **Keep security exemptions exact.** If a new tracked regression fixture copies a shipped scanner, record any justified HOL scanner false-positive exemption in both `.plugin-scanner.toml` and `scripts/ci/test-security-gates.py`. Historical copies stay in the external archive and do not need tracked-path exemptions.

## Changing an anti-pattern or skill behavior

Pattern and failure-code semantics live in several files that must move together. CI fails fast if any one drifts. When you add or rename a pattern, update all of:

- the relevant `skills/<name>/SKILL.md` (Quick Reference),
- `skills/e2e-reviewer/references/pattern-reference.md` (the per-pattern contract),
- `docs/e2e-test-smells.md`,
- the `README.md` pattern table,
- `skills/e2e-reviewer/references/grep-patterns.md`,
- `skills/e2e-reviewer/scripts/scan.sh`,
- `scripts/ci/lib/reviewer_taxonomy_contract.py` (the stable reviewer ID/title/severity order).

Then:

1. **Re-run the drift smoke test** (`scripts/ci/test-parity.sh`) and keep it green.
2. **Add or update evals.** Each behavior change needs at least two assertions in the skill's `evals/evals.json`: one true positive that must be flagged, and one false-positive guard that names the exact line and why it must not be flagged.
3. **Respect the severity contract.** P0 entries are silent-always-pass smells; do not downgrade them or promote P1/P2 into P0 just because they are easier to grep.
4. **Preserve evaluated snapshot digests.** Product edits do not refresh old evidence. Run current contract tests; record a new evaluated-skill digest only in a new study or explicit evidence revision, keeping earlier results unchanged.
5. **Run the shipped scripts on Linux.** `ci-local.sh` runs on macOS. After changes to shipped skills or their Linux suites are in a local commit, run `/bin/bash -p scripts/dev/linux-script-check.sh` from a worktree with no relevant dirty or untracked inputs. The default command archives `HEAD` and refuses worktree changes in `skills/**`, `README*.md`, `.github/workflows/e2e-smell-scan.yml`, `scripts/ci/ci-local.sh`, `scripts/ci/test-reviewer-scanner.py`, `scripts/ci/test-debugger-contracts.py`, `scripts/ci/test-*-debugger-*.py`, or `scripts/dev/linux-script-check.sh` rather than silently testing the previous commit. These paths are the product, documentation, workflow contract, and suites that the pinned Linux run actually reads. Passing an explicit `<revision>` intentionally validates only that immutable commit, which is how the pre-push hook checks the pushed revision. `--validate-inputs-only` checks this snapshot contract without Docker or network but does not run the Linux suites.
6. **Run the generator host smoke tests** after changing `playwright-test-generator`'s `SKILL.md` or `thin-rules.md`: use the loopback app in [`scripts/evals/generator-live/writescope-demo/`](scripts/evals/generator-live/writescope-demo/RUNBOOK.md) and keep the transcripts. Cover the official-agent path when `init-agents` and MCP are already set up (thin rules prepended, scanner fix of a seeded `#id` selector, one run), the agents not set up (guide shown, nothing installed or configured, no spec written), `e2e-reviewer` absent (gate reported as skipped and listed as not done), and a non-loopback `baseURL` (not delegated; a loopback stack is requested). It needs a model and a browser, so it is not part of CI; `scripts/ci/test-generator-router.py` is the offline contract.
7. **Keep historical pins immutable.** Archived thin-eval and other study snapshots describe their original actors and inputs. A changed shipped router needs new evidence; do not update an archived pin or redirect its comparison to make an old result cover new bytes.

## Releases

A push to `main` that changes `skills/` is a release. `skills update` offers an update to existing installs whenever the skill folder's content hash on `main` (or `master`) changes, whatever the version says, while Claude Code plugin installs update only when the plugin `version` changes (see the [plugin version management docs](https://code.claude.com/docs/en/plugins-reference#version-management)). Unbumped changes on `main` therefore reach one install path and not the other. Bump the version in all three manifests and all four `SKILL.md` files in the same push, and keep unfinished work on a branch rather than on `main`. Outside user-visible bug fixes and security fixes, aim for at most about one release a week.

Release gate: `python3 scripts/ci/check-pending-markers.py` fails while any `<!-- PENDING-THIN-EVAL -->` marker remains in `README*.md`, `AGENTS.md`, or `CHANGELOG.md` and the manifest version is a plain release string. It is deliberately not part of `ci-local.sh`; run it and rewrite or remove the marked wording (or tag a prerelease) before tagging. Its self-test, `scripts/ci/test-pending-markers.py`, is in `ci-local.sh`.

## Translations

Translated READMEs (`README.ko.md`, `README.ja.md`, `README.zh-cn.md`) follow the English `README.md`, which is canonical and may be newer. When you touch the English README, either update the translations in the same PR or note in the PR description that they now lag. New-language translations are welcome — mirror the structure of an existing one, keep the language-switcher line, and never translate code blocks, commands, pattern IDs, or failure codes.

## Pull request process

1. Keep the change focused; unrelated cleanup belongs in a separate PR.
2. Run the verification gate above and confirm it is green.
3. Write a descriptive title and a body that explains the *why*, links any related issue, and calls out any parity surface you touched.
4. For a new anti-pattern, include the fixtures and eval assertions in the same PR.

## License

By contributing, you agree that your contributions are licensed under the [Apache-2.0](./LICENSE) license, the same as the project. Match the parent license header in any new file you add.
