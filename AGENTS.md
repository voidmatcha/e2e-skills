› **Reading this in Claude Code?** See also `CLAUDE.md` if present. This file is read by Codex and other agents that follow the `AGENTS.md` convention.

# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, and other AGENTS.md-compatible hosts) working in this repository.

## Repository Overview

`e2e-skills` is a bundle of four Agent Skills for end-to-end test work on Playwright and Cypress projects:

- `playwright-test-generator` — generates Playwright E2E tests from scratch (coverage-gap analysis → live-browser exploration → approval gate → review).
- `e2e-reviewer` — static review of existing Playwright/Cypress specs against 24 anti-patterns grouped P0/P1/P2.
- `playwright-debugger` — root-cause diagnosis from `playwright-report/`.
- `cypress-debugger` — root-cause diagnosis from `cypress/reports/` (mochawesome / JUnit).

The repo doubles as a Claude Code plugin (`.claude-plugin/`), a Codex plugin (`.codex-plugin/`), a cross-agent skill source via the `skills` CLI, and a standalone scanner (`skills/e2e-reviewer/scripts/scan.sh`).

## Verification gate (must pass before commit)

```
[ ] /bin/bash -p scripts/ci/ci-local.sh          # review checks + drift smoke checks + 0 P0 smell hits
[ ] /bin/bash -p scripts/ci/pre-push-security.sh # secrets and credential leak guard
```

`ci-local.sh` is the single source of truth for the repository CI mirror
(shell syntax, security, parity, evals, public skill surface, framework scope,
link integrity, docs orphan check, language, and the E2E smell scan).
`ci-local.sh` reaches the security gate through `review.sh`; the explicit
`pre-push-security.sh` command above reruns that mandatory gate at the
pre-push boundary. If you change a CI check, update `ci-local.sh` first.

## Directory Layout

```
.
├── .claude-plugin/         # Claude Code plugin + marketplace manifests
│   ├── plugin.json
│   └── marketplace.json
├── .codex-plugin/          # Codex plugin manifest (interface display surface)
│   └── plugin.json
├── AGENTS.md               # This file (cross-agent canonical guide)
├── agents/                 # Claude Code subagents (plugin-install only): read-only
│   ├── e2e-finding-verifier.md    # adversarially verify ONE reviewer finding
│   └── e2e-failure-classifier.md  # classify ONE failure into F1–F15
├── .codex/agents/          # Codex-native TOML ports of the two subagents (optional)
│   ├── e2e-finding-verifier.toml   # behavior-synced with agents/*.md; guarded by SP5
│   └── e2e-failure-classifier.toml
├── benchmarks/             # immutable public benchmark evidence + adjudication ledgers
├── skills/                 # Four Agent Skills (the public surface)
│   ├── playwright-test-generator/
│   │   ├── SKILL.md        # Required: skill frontmatter + body
│   │   ├── best-practices.md
│   │   ├── code-rules.md
│   │   ├── evals/evals.json
│   │   └── agents/openai.yaml
│   ├── e2e-reviewer/
│   ├── playwright-debugger/
│   └── cypress-debugger/
├── scripts/
│   ├── ci/                 # CI parity, security, eval-metadata checks
│   ├── dev/                # contributor reinstall + git hook setup
│   ├── evals/              # labeled reviewer holdout, live runners, executable fixtures
│   ├── hooks/              # local git hooks
│   ├── pr-preflight.sh     # seven-stage preflight for upstream E2E-fix PRs
│   ├── verify-fixes.sh     # post-bulk-fix verification (sed-artifact AST detection)
│   └── validate-evals.sh
├── docs/                   # Open-source assets (taxonomy, case studies, scope)
├── README.md
└── CHANGELOG.md
```

Each `skills/<name>/SKILL.md` is the contract. Everything in the skill body should be **task-actionable instructions for the agent**, not narrative documentation; supporting reference material (long tables, framework references) goes in sibling `.md` files and is read on demand.

## Conventions

- **Skill names**: kebab-case, must match the directory name and the `name:` in SKILL.md frontmatter.
- **SKILL.md frontmatter**: `name`, `description`, `license`, `metadata: { author, version }`. The description is the trigger surface — pack synonyms and the user's likely phrasing.
- **Pattern IDs**: 24 stable anti-pattern entries (`#1`–`#23` plus `#3b`) with P0/P1/P2 severity. IDs are stable; do not renumber. Severity rationale: P0 = silent always-pass, P1 = poor diagnostics, P2 = maintenance.
- **Failure category IDs**: 15 codes (`F1`–`F15`) used by both debuggers. Codes are stable.
- **JUSTIFIED comments**: `// JUSTIFIED: <reason>` on the line above (or above the enclosing block / multi-line chain) suppresses scanner findings. Suppress for documented intent, never to hide a real finding.
- **Severity-first organization**: tables in SKILL.md, README, and `docs/e2e-test-smells.md` group by P0/P1/P2 in the same order.
- **English-only public surface**: SKILL.md, README, and `docs/` are English. CI enforces this (`Language` check). Sanctioned exception: root-level `README.<lang>.md` translations (`README.ko.md`, `README.ja.md`, `README.zh-cn.md`) and the language-switcher line in `README.md` that links to them. `README.md` (English) is canonical; translations follow it.

## Frameworks in Scope

Playwright and Cypress only. The skill does not produce code or advice for Puppeteer, Selenium, WebdriverIO, TestCafe, or Nightwatch. See `docs/framework-scope.md` for the rationale. CI fails on accidental support claims for out-of-scope frameworks.

## Local Development Commands

```bash
# Full CI mirror — run before every commit
/bin/bash -p scripts/ci/ci-local.sh

# Individual stages
bash scripts/ci/review.sh           # parity, language, links, framework scope, orphans
bash scripts/ci/test-parity.sh      # drift smoke test (mutate-and-detect)
bash scripts/ci/check-verification-parity.sh
bash scripts/ci/test-codex-agents.sh
bash scripts/ci/test-local-eslint-path.sh
bash scripts/validate-evals.sh      # eval JSON schema
bash scripts/ci/test-reviewer-holdout.sh
python3 scripts/ci/test-reviewer-holdout-v3.py
/bin/bash -p scripts/ci/run-reference-tokenizer-suites.sh \
  scripts/ci/test-independent-review-v7.py \
  scripts/ci/test-independent-review-v10.py
/bin/bash -p scripts/ci/run-independent-review-v10-evidence.sh
python3 scripts/ci/test-reviewer-evidence-v3.py
python3 scripts/ci/test-reviewer-evidence.py
python3 scripts/ci/test-reviewer-scanner.py
python3 scripts/ci/test-debugger-contracts.py
python3 scripts/ci/test-residual-redos-budget.py
python3 scripts/ci/test-fixture-faults.py
python3 scripts/evals/run-fixture-faults.py --validate-only
python3 scripts/ci/test-playwright-semantic-probes.py
python3 scripts/ci/test-playwright-timeout-zero-probe.py
python3 scripts/ci/test-cypress-timeout-zero-probe.py
/bin/bash -p scripts/ci/pre-push-security.sh
bash scripts/ci/codex-smoke.sh      # manual Codex cross-host smoke (skips if codex absent)
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh path/to/tests   # standalone scanner

# Plugin manifest sanity
python3 -m json.tool .claude-plugin/plugin.json
python3 -m json.tool .claude-plugin/marketplace.json
```

`ci-local.sh` runs the repository CI mirror, including the security gate
through `review.sh`, and must be green before opening a PR. The direct
pre-push security rerun, manual Codex smoke, standalone scanner example, and
manifest JSON sanity commands above remain separate invocations.

Live browser/model evidence is opt-in and stays outside ordinary CI:

```bash
npm ci --prefix scripts/evals/fixtures
python3 scripts/evals/run-fixture-faults.py
python3 scripts/evals/run-playwright-semantic-probes.py
python3 scripts/evals/run-playwright-timeout-zero-probe.py
python3 scripts/evals/run-cypress-timeout-zero-probe.py
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v3.json \
  --protocol scripts/evals/reviewer-validation-protocol-v3.json \
  --runner codex --model gpt-5.6-sol --repetitions 3 --allow-live \
  --report-only --output benchmarks/reviewer-holdout-v3/reports/full-codex.json
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v3.json \
  --protocol scripts/evals/reviewer-validation-protocol-v3.json \
  --runner claude --model claude-opus-5 --repetitions 3 --timeout 300 --allow-live \
  --report-only --output benchmarks/reviewer-holdout-v3/reports/full-opus.json
python3 scripts/evals/run-reviewer-holdout.py \
  --cases scripts/evals/reviewer-holdout-v3.json \
  --protocol scripts/evals/reviewer-validation-protocol-v3.json \
  --runner claude --model claude-fable-5 --repetitions 3 --timeout 300 --allow-live \
  --report-only --output benchmarks/reviewer-holdout-v3/reports/full-fable.json
python3 scripts/evals/compare-reviewer-holdouts.py \
  benchmarks/reviewer-holdout-v3/reports/full-codex.json \
  benchmarks/reviewer-holdout-v3/reports/full-opus.json \
  benchmarks/reviewer-holdout-v3/reports/full-fable.json \
  --cases scripts/evals/reviewer-holdout-v3.json \
  --protocol scripts/evals/reviewer-validation-protocol-v3.json \
  --output benchmarks/reviewer-holdout-v3/reports/cross-host.json
```

The committed labeled corpus is a public development holdout. Use an external
`--cases` bundle for a sealed release run; do not describe a public corpus as hidden.
Wrapper-free live runs are limited to the exact built-in corpus/protocol paths and
pinned digests. Every external `--cases` bundle requires `--isolation-wrapper`,
regardless of its self-declared visibility. Built-in public live runs use one
start-of-run skill/corpus snapshot, fresh temporary
workspaces, prompt-complete Codex/Claude calls with every model tool disabled,
and pre/post digests of every staged
path and original input; any mutation makes the report incomplete.
Corpus workspace paths must not enter runner-controlled surfaces (`.skill/`,
`.git/`, `.codex/`, `.claude/`, `.agents/`, `.omx/`, `AGENTS.md`, or
`CLAUDE.md`). The staged `.skill/e2e-reviewer` digest is checked against the
frozen evaluated skill before and after every call.
The runner passes a strict environment allowlist. Codex receives only a private
staged copy of the parent `auth.json`; Claude receives one validated
`CLAUDE_CODE_OAUTH_TOKEN` snapshot but no ambient config directory or API key;
custom executables receive no Codex/Claude credentials. Generic tokens, cloud
credentials, proxy variables, and shell/runtime injection variables are removed.
There is no built-in sealed sandbox. A non-public corpus requires
`--isolation-wrapper <executable>` and an independently isolated release environment;
the wrapper receives the runner command as its argument vector.
The bundled harness records wrapper isolation as not proven and keeps the
report `INCONCLUSIVE`; it never promotes a wrapped run to `PASS` merely
because the wrapper is executable.
The release protocol declares the host/model matrix and fixes the schedule and
thresholds before execution. Local runner/model strings are provenance, not
cryptographic attestation. Primary accuracy is computed on unique
majority-stable labels and predictions; repeated totals also enforce a precision
floor against rotating one-off false positives, but are not additional
independent defects.

### Local dev workflow (testbed + auto-reinstall)

```bash
# Clone any real Playwright/Cypress repo into testbed/ (gitignored) to exercise the skills
git clone --depth 1 https://github.com/calcom/cal.diy testbed/cal.diy
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh testbed/cal.diy
# Invoke e2e-reviewer / playwright-debugger via the agent runtime as usual.

# Install the four skills from this repo as real copies (one-time setup; also cleans up any prior symlink install)
bash scripts/dev/reinstall-skills.sh

# Optional: register the two named Codex-native e2e agents globally
bash scripts/dev/install-codex-agents.sh

# Wire `git push` to refresh the installed copies via `skills update` (one-time, opt-in)
bash scripts/dev/install-hooks.sh
```

The reinstall script executes a verified `skills@1.5.21` artifact from an exact
dependency lock, then replaces only the four e2e-skills as real copies. It
verifies the canonical store, the requested Claude Code projection, and any
Codex shadow before accepting the install; other installed skills are
untouched. `--copy` mode snapshots the current working tree at invocation time,
including uncommitted edits, so later source edits do not leak into the runtime
until the next reinstall. The pre-push hook refreshes that snapshot from the
working tree present at push time. `E2E_SKILLS_AGENTS` is restricted to the
receiving surfaces this installer verifies (`claude-code` and `codex`; default:
both). Named Codex-agent installation remains a separate global opt-in: run
`scripts/dev/install-codex-agents.sh` directly, or set
`E2E_SKILLS_INSTALL_CODEX_AGENTS=1` for an explicit combined reinstall; the
default is `0`.

## When You Edit Skills

1. **Update parity surfaces in lock-step.** Adding or renaming a pattern means touching: the relevant `SKILL.md` (Quick Reference), `skills/e2e-reviewer/references/pattern-reference.md` (per-pattern contract — CI Checks 3b/3c validate this file), `docs/e2e-test-smells.md`, `README.md` 24 Patterns table, `skills/e2e-reviewer/references/grep-patterns.md`, `skills/e2e-reviewer/scripts/scan.sh`, `.claude-plugin/plugin.json` description, `.claude-plugin/marketplace.json` description, and `.codex-plugin/plugin.json` description. CI fails fast if any one is out of step.
2. **Re-run the drift smoke test.** `scripts/ci/test-parity.sh` mutates known-bad versions of the files and asserts the parity check catches each one — keep it green when you add new parity rules.
3. **Add or update evals when behavior changes.** Each skill has an `evals/evals.json`. Eval IDs must follow the skill's naming convention (CI validates). Each new smell or behavior change should add at least two assertions: one true positive that must be flagged, and one false-positive guard that names the exact line and why it must not be flagged.
4. **Respect severity contracts.** P0 entries should be silent-always-pass smells; don't downgrade. P1/P2 should not creep into P0 just because they're easier to grep.
5. **Keep subagent wiring delegation-aware.** The `agents/` subagents (`e2e-finding-verifier`, `e2e-failure-classifier`) are discovered only on a Claude Code plugin install — the `skills` CLI copy and Codex never see them. So any skill that delegates to a subagent MUST also carry an inline fallback that reaches an **identical** verdict from the same source of truth (`skills/e2e-reviewer/references/pattern-reference.md` for reviewer findings; the debugger `SKILL.md` F1–F15 tables for failures). Never make a subagent the only path to a verdict. The Codex-native `.codex/agents/*.toml` ports are an optional **third** copy of the same contract — kept from drifting by the `Subagent parity` **SP5** check in `scripts/ci/review.sh` (A1 absolute-path contract, verdict vocabulary, frozen F1–F15) — but Codex only registers them when the TOMLs sit in `~/.codex/agents/` (or a Codex checkout of this repo), never via `codex plugin add` or the `skills` CLI, so the inline fallback stays load-bearing on every host.

## Cross-host parity rules

Both the Claude Code plugin and the Codex plugin expose the same four public skills from the shared `skills/` directory. The two manifests differ only in schema shape and host-specific display fields — never in skill behavior. CI enforces:

- **Version parity**: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (the `e2e-skills` entry), and `.codex-plugin/plugin.json` must share the same `version` string. Bump all three together.
- **Description parity**: all 24 P0/P1/P2 pattern phrases must appear in order in every manifest description. `scripts/ci/lib/manifest_phrase_contract.py` owns the stable ID/title/phrase mapping and `review.sh` checks each mapped ID/title/severity against the `e2e-reviewer/SKILL.md` Quick Reference before checking all three manifests. No manifest can redefine the canonical phrase list. The `e2e-reviewer/SKILL.md` frontmatter keeps a lean trigger description.
- **Public skill surface**: `skills/<name>/SKILL.md` `name` field must match the directory name, and the four directory names must match `.claude-plugin/plugin.json` `skills` paths and the four `agents/openai.yaml` `name` fields.
- **Framework scope**: the word "Puppeteer" must not appear outside `docs/framework-scope.md`, including in any plugin manifest.

When you bump the bundle version, touch all three manifests in one commit. The drift smoke test (`scripts/ci/test-parity.sh`) mutates each manifest in turn to verify the parity checks actually catch drift.

## What Not to Do

- Do **not** add new file types under `docs/` without linking them from `README.md` or referencing them from a CI script — the docs orphan check will fail.
- Do **not** silently change a pattern ID, severity, or failure category code. Downstream evals and OSS adopters depend on them.
- Do **not** introduce out-of-scope framework code paths. Skills must say "out of scope" rather than emit half-working examples for Selenium/WebdriverIO/etc.
- Do **not** push commits without running `/bin/bash -p scripts/ci/ci-local.sh`.
- Do **not** edit `skills/e2e-reviewer/references/grep-patterns.md` without checking that the matching pattern IDs in `skills/e2e-reviewer/scripts/scan.sh` still line up — `scan.sh` is now the runtime source of truth, `grep-patterns.md` is an ID-meaning reference for Phase 2 / debugger lookup.
- Do **not** create side effects on third-party repos when validating the skill. Cloning into `testbed/` and running `scan.sh` locally is allowed; pushing to forks, opening PRs/issues, posting comments, or any state-changing `gh` command is not.

## Installation Paths Documented for Users

`README.md` organizes the Install section as per-host subsections (superpowers-style anchor list at the top, one short subsection per host). Keep this list and those subsections in lock-step:

- **Claude Code**: plugin marketplace — `/plugin marketplace add voidmatcha/e2e-skills` → `/plugin install e2e-skills@voidmatcha` (reads `.claude-plugin/plugin.json` + `marketplace.json`) — or the `skills` CLI with `-a claude-code`.
- **Codex**: the recommended Codex-only path is `npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a codex`; Claude Code has its own `-a claude-code` command above. The skill copies land in `~/.agents/skills/`, where Codex/omx auto-discovers their `SKILL.md` files. This path does not install the root `.codex-plugin/plugin.json`; that interface manifest belongs to the alternative Codex plugin marketplace path: `codex plugin marketplace add voidmatcha/e2e-skills` → `codex plugin add e2e-skills@voidmatcha`.
- **All other agents (Cursor, OpenCode, Gemini CLI, and more)**: one generalized section — the global install `npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all` is the primary command, with `-a <agent>` mentioned as the single-agent variant (agent names must be verified in the `vercel-labs/skills` supported-agents list; do not document names that are not in it).
- **Manual clone for Claude Code**: clone the repository to `~/.claude/e2e-skills`, then symlink each of the four `skills/<name>` directories directly into `~/.claude/skills/<name>`; Claude Code documents direct per-skill roots and supports those symlinks. The README commands must fail rather than overwrite an existing same-named skill and must tell users to verify all four through `/skills`.

The install paths above cover every supported host. Use the `skills` CLI route as the default cross-agent path (Claude Code, Codex, and the broader `vercel-labs/skills` ecosystem); the Codex plugin marketplace remains a supported alternative for Codex plugin installs.

## License

Apache-2.0. Match the parent license in any new file you add.
