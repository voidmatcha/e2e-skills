› **Reading this in Claude Code?** See also `CLAUDE.md` if present. This file is read by Codex and other agents that follow the `AGENTS.md` convention.

# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, and other AGENTS.md-compatible hosts) working in this repository.

## Repository Overview

`e2e-skills` is a bundle of four Agent Skills for end-to-end test work on Playwright and Cypress projects:

- `playwright-test-generator` — routes new-test generation to the official Playwright planner and generator when they are installed and their MCP tools are visible, with the 12 thin rules and safety instructions prepended, then the `e2e-reviewer` scanner gate and scoped test execution, with at most two parent-owned repairs for proven generation errors while preserving required behavior; when the agents are not set up it shows the setup guide and stops. A router, not a pipeline; the 2.x pipeline is archived at tag `v2.0.1`.
- `e2e-reviewer` — static review of existing Playwright/Cypress specs against 24 anti-patterns grouped P0/P1/P2.
- `playwright-debugger` — root-cause diagnosis from `playwright-report/`.
- `cypress-debugger` — root-cause diagnosis from `cypress/reports/` (mochawesome / JUnit).

The repo doubles as a Claude Code plugin (`.claude-plugin/`), a Codex plugin (`.codex-plugin/`), a cross-agent skill source via the `skills` CLI, and the standalone npm scanner (`packages/scanner/`). Installed skills launch the bundled Node scanner through `skills/e2e-reviewer/scripts/scan.sh`; that file is a generated integrity-checking launcher, not a separate analyzer.

**Product vs. infrastructure.** The four `skills/` directories above are the product — what a user installs and runs. `scripts/ci/` and the eval harnesses verify the product. Historical research evidence lives in a pinned Hugging Face snapshot; `benchmarks/` keeps its status index and restoration manifest. A typo fix or a small skill-wording change barely touches any of it — see `CONTRIBUTING.md`'s tier table before assuming a change needs the full process below.

## Verification gate

```
[ ] /bin/bash -p scripts/ci/ci-local.sh          # review checks + drift smoke checks + 0 P0 smell hits
[ ] /bin/bash -p scripts/ci/pre-push-security.sh # secrets and credential leak guard
```

For development and pre-commit checks, `ci-local.sh --changed origin/main` selects suites using committed, staged, unstaged and nonignored untracked changes; add `--plan` to preview the selection. Security, syntax and common contracts remain mandatory. Unknown paths, shared infrastructure or an unavailable comparison select the full suite. Scoped success is not full release validation. No arguments or `--full` run the complete suite, which remains required before release.

`ci-local.sh` is the single source of truth for the repository CI mirror (shell syntax, security, parity, evals, public skill surface, framework scope, link integrity, docs orphan check, language, and the E2E smell scan). `ci-local.sh` reaches the security gate through `review.sh`; the explicit `pre-push-security.sh` command above reruns that mandatory gate at the pre-push boundary. If you change a CI check, update `ci-local.sh` first.

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
├── benchmarks/             # STATUS.md + external-evidence.json; historical study files live on Hugging Face
├── skills/                 # Four Agent Skills (the public surface)
│   ├── playwright-test-generator/
│   │   ├── SKILL.md        # Required: skill frontmatter + body (at most 7,168 bytes)
│   │   ├── thin-rules.md   # the current 12-rule checklist; test-generator-router.py pins its product digest
│   │   ├── evals/evals.json
│   │   └── agents/openai.yaml
│   ├── e2e-reviewer/
│   │   └── references/      # e.g. scanner-workflow.md, semantic-review.md, verification-rules.md
│   ├── playwright-debugger/
│   │   └── references/      # e.g. artifact-extraction.md, classification-procedure.md, safety-procedures.md
│   └── cypress-debugger/
│       └── references/      # e.g. artifact-extraction.md, classification-procedure.md, safety-procedures.md
├── packages/scanner/        # Canonical Node scanner implementation and npm package
├── scripts/
│   ├── ast-grep-rules/     # Developer-only postfix verification rules
│   ├── ci/                 # CI parity, security, eval-metadata checks
│   │   └── fixtures/legacy-scanner/ # Immutable shell oracle for regression comparisons
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
- **SKILL.md frontmatter**: `name`, `description`, `license`, `metadata: { author, version, frameworks, testing-types, languages }`. The description is the trigger surface — pack synonyms and the user's likely phrasing. The Agent Skills spec fixes the set of top-level keys and any other one is a validation error, so classification fields live under `metadata`, which the spec defines as a string-to-string map — comma-joined values, never YAML lists. `frameworks` must match the skill's real scope (`docs/framework-scope.md`); a skill that names a framework it does not support is a scope claim, not a hint.
- **Pattern IDs**: 24 stable anti-pattern entries (`#1`–`#23` plus `#3b`) with P0/P1/P2 severity. IDs are stable; do not renumber. Severity rationale: P0 = silent always-pass, P1 = poor diagnostics, P2 = maintenance.
- **Failure category IDs**: 15 codes (`F1`–`F15`) used by both debuggers. Codes are stable.
- **JUSTIFIED comments**: `// JUSTIFIED: <reason>` on the line above the hit, above the start of a multi-line chain, or directly above a `page.evaluate()` / `page.waitForFunction()` callback whose body contains the hit. It does not reach past that: a marker above a `describe` or `test` does not cover the block, so use it where the finding is. Suppress for documented intent, never to hide a real finding.
- **Severity-first organization**: tables in SKILL.md, README, and `docs/e2e-test-smells.md` group by P0/P1/P2 in the same order.
- **English-only public surface**: SKILL.md, README, and `docs/` are English. CI enforces this (`Language` check). Sanctioned exception: root-level `README.<lang>.md` translations (`README.ko.md`, `README.ja.md`, `README.zh-cn.md`) and the language-switcher line in `README.md` that links to them. `README.md` (English) is canonical; translations follow it.

## Benchmark validity (before trusting any arm)

An arm that never used its defining tools makes the comparison meaningless; the official-generator arm was invalid until 2026-10-15 for exactly this reason.

- Count the defining tool calls per cell from rollout or transcript logs. `// spec:` / `// seed:` headers, final summaries, and "delivered" are not evidence.
- Prove the environment exposes those tools (sandbox, approvals, MCP declared per cell, free ports) with a canary cell before freezing.
- Gate on content, not a grep for a flag another arm also contains.
- Report valid-cell counts per arm and the harness version/date a result is valid from; never cite results from invalid attempts, and archive them instead of deleting.

## Frameworks in Scope

Playwright and Cypress only. The skill does not produce code or advice for Puppeteer, Selenium, WebdriverIO, TestCafe, or Nightwatch. See `docs/framework-scope.md` for the rationale. CI fails on accidental support claims for out-of-scope frameworks.

## Benchmark evidence storage

- Keep only [STATUS.md](benchmarks/STATUS.md) and [external-evidence.json](benchmarks/external-evidence.json) under `benchmarks/` in Git. Store historical reports, protocols, frozen inputs, adjudications and raw artifacts in the authoritative `voidmatcha/e2e-skills-benchmarks` Hugging Face dataset. Keep current harness code and small regression fixtures under `scripts/`.
- Default `ci-local.sh` verifies the current product, common harness contracts and local regression fixtures without downloading historical evidence. `/bin/bash -p scripts/ci/ci-evidence.sh /absolute/restored-root` is a separate opt-in replay of the original CI at the manifest's `source_commit`; it does not validate the current product.
- The manifest pins a full dataset revision, archive and metadata SHA-256 hashes, the source Git commit, file count and byte count. Restore to a new external directory with `scripts/dev/fetch-benchmark-evidence.sh`; never restore into this checkout or overwrite local originals.
- Preserve frozen attempts, negative results, original provenance and licenses. Do not refresh an old evidence digest to match a product edit. New results require a new study or explicit revision. Label derived or sanitized exports and record both source and exported hashes. Never export credentials, authentication homes, cookies, environment secrets, or browser profiles.
- Upload only with user authorization. Verify a fresh download before removing tracked evidence, audit CI dependencies, and preserve Git history. Follow [CONTRIBUTING.md: Benchmark evidence](CONTRIBUTING.md#benchmark-evidence) for publication and restoration commands.

## Local Development Commands

```bash
# Required current-product gates
/bin/bash -p scripts/ci/ci-local.sh
/bin/bash -p scripts/ci/pre-push-security.sh

# Selected focused checks
bash scripts/ci/review.sh
bash scripts/ci/test-parity.sh
bash scripts/ci/check-verification-parity.sh
bash scripts/ci/test-local-eslint-path.sh
bash scripts/validate-evals.sh
python3 scripts/ci/test-reviewer-scanner.py
python3 scripts/ci/test-debugger-contracts.py
python3 scripts/ci/test-generator-router.py
python3 scripts/ci/test-external-evidence.py
python3 scripts/dev/reviewer-contract.py --write --lean # taxonomy changes; requires Lean 4

# Historical evidence: explicit restoration and source-commit replay
/bin/bash -p scripts/dev/fetch-benchmark-evidence.sh --dry-run
/bin/bash -p scripts/dev/fetch-benchmark-evidence.sh --output /absolute/new-evidence-root
/bin/bash -p scripts/dev/fetch-benchmark-evidence.sh --verify-only --output /absolute/new-evidence-root
/bin/bash -p scripts/ci/ci-evidence.sh /absolute/new-evidence-root

# Optional platform and host verification
/bin/bash -p scripts/dev/linux-script-check.sh # needs Docker; see CONTRIBUTING.md
bash scripts/ci/codex-smoke.sh
/bin/bash -p skills/e2e-reviewer/scripts/scan.sh path/to/tests
python3 scripts/ci/check-pending-markers.py # separate release gate
```

`ci-local.sh` owns current-product CI and includes the security gate through `review.sh`; run the direct security gate again before pushing. Pull-request CI uses changed-file selection; main pushes and manual workflows use the full suite. Historical study READMEs in the restored snapshot own their frozen reproduction instructions. Evidence replay downloads the separately pinned source archive, verifies it and builds a temporary Git context; the original commit need not exist locally. Historical CI may require its pinned tokenizer environment. It does not run live models or authorize new benchmark calls.

The hosted `main` workflow reruns the pinned 36-cell browser fault matrix on a disposable runner. The scanner CI group installs the Node package's exact locked dependencies with lifecycle scripts disabled in an external temporary source copy, then runs its tests with Node 22 or newer. It does not install dependencies into the source checkout or load a reviewed project's configuration. Live model runs and other browser probes are opt-in. For generator behavior changes, use the host smoke procedure in [CONTRIBUTING.md](CONTRIBUTING.md#changing-an-anti-pattern-or-skill-behavior). Run reviewer study arms sequentially under a new preregistered protocol; do not modify a frozen study to test new product bytes.

For `scripts/evals/run-reviewer-holdout.py`, the committed labeled corpus is a public development holdout. Use an external `--cases` bundle for a sealed release run; do not describe a public corpus as hidden. Wrapper-free live runs are limited to the exact built-in corpus/protocol paths and pinned digests. Every external `--cases` bundle requires `--isolation-wrapper`, regardless of its self-declared visibility. Built-in public live runs use one start-of-run skill/corpus snapshot, fresh temporary workspaces, prompt-complete Codex/Claude calls with every model tool disabled, and pre/post digests of every staged path and original input; any mutation makes the report incomplete.

Corpus workspace paths must not enter runner-controlled surfaces (`.skill/`, `.git/`, `.codex/`, `.claude/`, `.agents/`, `.omx/`, `AGENTS.md`, or `CLAUDE.md`). The staged `.skill/e2e-reviewer` digest is checked against the frozen evaluated skill before and after every call.

The runner passes a strict environment allowlist. Codex receives only a private staged copy of the parent `auth.json`; Claude receives one validated `CLAUDE_CODE_OAUTH_TOKEN` snapshot but no ambient config directory or API key; custom executables receive no Codex/Claude credentials. Generic tokens, cloud credentials, proxy variables, and shell/runtime injection variables are removed.

There is no built-in sealed sandbox. A non-public corpus requires `--isolation-wrapper <executable>` and an independently isolated release environment; the wrapper receives the runner command as its argument vector. The bundled harness records wrapper isolation as not proven and keeps the report `INCONCLUSIVE`; it never promotes a wrapped run to `PASS` merely because the wrapper is executable.

The release protocol declares the host/model matrix and fixes the schedule and thresholds before execution. Local runner/model strings are provenance, not cryptographic attestation. Primary accuracy is computed on unique majority-stable labels and predictions; repeated totals also enforce a precision floor against rotating one-off false positives, but are not additional independent defects. For a new protocol, use `execution_identity.version_policy: "minimum"` with a pinned version floor. The comparator enforces one identity per runner family across a matrix. Never change the policy of an already frozen protocol.

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

# Optional: register the same two subagents for Claude Code at user level.
# Prefer this over installing the plugin when the four skills are already
# present through the skills CLI: plugin skills are namespaced rather than
# deduplicated, so the plugin would load a second copy of every skill
# description into each session just to deliver these two agents.
bash scripts/dev/install-claude-agents.sh

# Wire pushes of HEAD to main to refresh the installed copies (one-time, opt-in)
bash scripts/dev/install-hooks.sh
```

The reinstall script executes a verified `skills@1.5.21` artifact from an exact dependency lock, then replaces only the four e2e-skills as real copies. It verifies the canonical store, the requested Claude Code projection, and any Codex shadow before accepting the install; other installed skills are untouched. `--copy` mode snapshots the current working tree at invocation time, including uncommitted edits, so later source edits do not leak into the runtime until the next reinstall. The pre-push hook refreshes that snapshot only when the push sends the checked-out HEAD to `main` and `skills/` has no uncommitted edits, so the installed copy matches what was pushed; other pushes skip the refresh. When a pushed range touches `skills/*/scripts/` or their test suites, the hook also runs `scripts/dev/linux-script-check.sh` on the pushed commit, because `ci-local.sh` runs on macOS and the scripts also ship to Linux: a suite failure blocks the push, and a missing Docker daemon only warns. `E2E_SKILLS_SKIP_LINUX_CHECK=1` bypasses it; hosted CI still runs on Linux. `E2E_SKILLS_AGENTS` is restricted to the receiving surfaces this installer verifies (`claude-code` and `codex`; default: both). Named Codex-agent installation remains a separate global opt-in: run `scripts/dev/install-codex-agents.sh` directly, or set `E2E_SKILLS_INSTALL_CODEX_AGENTS=1` for an explicit combined reinstall; the default is `0`.

## When You Edit Skills

1. **Update taxonomy surfaces in lock-step.** Adding or renaming a pattern means touching: the relevant `SKILL.md` (Quick Reference), `skills/e2e-reviewer/references/pattern-reference.md` (per-pattern contract — CI Checks 3b/3c validate this file), `docs/e2e-test-smells.md`, `README.md` 24 Patterns table, `skills/e2e-reviewer/references/grep-patterns.md`, `packages/scanner/src/` detector and report mappings, and `scripts/ci/lib/reviewer_taxonomy_contract.py`. Rebuild the installed scanner with `scripts/dev/build-scanner-runtime.py` when runtime sources change; edit `scripts/dev/scanner-launcher.sh` for launcher changes and keep the public `scan.sh` copy byte-identical. Do not hand-edit generated bundled files. `scripts/ci/review.sh` derives the expected Quick Reference row order from the IDs themselves, so it needs no edit for a new pattern. CI fails fast if IDs, titles, order, or severities drift. Regenerate the Lean severity model with `python3 scripts/dev/reviewer-contract.py --write`; CI checks it against the skill without Lean, and a new instance-severity exception must be added to its hand-written rules and the Quick Reference row together. After any `pattern-reference.md` edit, run `python3 scripts/dev/split-pattern-reference.py` to regenerate the per-pattern copies in `references/patterns/`, which the reviewer reads instead of the 90 KB source; CI fails when they drift. Plugin descriptions remain concise host-specific package metadata and do not store the reviewer taxonomy.
2. **Re-run the drift smoke test.** `scripts/ci/test-parity.sh` mutates known-bad versions of the files and asserts the parity check catches each one — keep it green when you add new parity rules.
3. **Add or update evals when behavior changes.** Each skill has an `evals/evals.json`. Eval IDs must follow the skill's naming convention (CI validates). Each new smell or behavior change should add at least two assertions: one true positive that must be flagged, and one false-positive guard that names the exact line and why it must not be flagged.
4. **Respect severity contracts.** P0 entries should be silent-always-pass smells; don't downgrade. P1/P2 should not creep into P0 just because they're easier to grep.
5. **Keep subagent wiring delegation-aware.** The `agents/` subagents (`e2e-finding-verifier`, `e2e-failure-classifier`) are discovered only on a Claude Code plugin install — the `skills` CLI copy and Codex never see them. So any skill that delegates to a subagent MUST also carry an inline fallback that reaches an **identical** verdict from the same source of truth (`skills/e2e-reviewer/references/pattern-reference.md` for reviewer findings; the debugger `SKILL.md` F1–F15 tables for failures). Never make a subagent the only path to a verdict. The Codex-native `.codex/agents/*.toml` ports are an optional **third** copy of the same contract — kept from drifting by the `Subagent parity` **SP5** check in `scripts/ci/review.sh` (A1 absolute-path contract, verdict vocabulary, frozen F1–F15) — but Codex only registers them when the TOMLs sit in `~/.codex/agents/` (or a Codex checkout of this repo), never via `codex plugin add` or the `skills` CLI, so the inline fallback stays load-bearing on every host.

## Cross-host parity rules

Both the Claude Code plugin and the Codex plugin expose the same four public skills from the shared `skills/` directory. The two manifests differ only in schema shape and host-specific display fields — never in skill behavior. CI enforces:

- **Version parity**: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (the `e2e-skills` entry), and `.codex-plugin/plugin.json` must share the same `version` string. Bump all three together.
- **Taxonomy parity**: `scripts/ci/lib/reviewer_taxonomy_contract.py` owns the stable 24-entry reviewer ID/title/severity order, and `review.sh` checks it against the `e2e-reviewer/SKILL.md` Quick Reference. Manifest descriptions are concise host-specific package metadata; they identify the four generate, review, and debug skills without duplicating the full reviewer taxonomy. The `e2e-reviewer/SKILL.md` frontmatter remains the lean trigger description.
- **Public skill surface**: `skills/<name>/SKILL.md` `name` field must match the directory name, and the four directory names must match `.claude-plugin/plugin.json` `skills` paths and the `$<skill>` invocation in each `agents/openai.yaml` `interface.default_prompt`. That file follows the schema codex-cli actually reads — `interface` plus optional `policy` and `dependencies` — so it carries no `name` field of its own.
- **Framework scope**: the word "Puppeteer" must not appear outside `docs/framework-scope.md`, including in any plugin manifest.

When you bump the bundle version, touch all three manifests in one commit. The drift smoke test (`scripts/ci/test-parity.sh`) mutates each manifest in turn to verify the parity checks actually catch drift.

## What Not to Do

- Do **not** add new file types under `docs/` without linking them from `README.md` or referencing them from a CI script — the docs orphan check will fail.
- Do **not** silently change a pattern ID, severity, or failure category code. Downstream evals and OSS adopters depend on them.
- Do **not** introduce out-of-scope framework code paths. Skills must say "out of scope" rather than emit half-working examples for Selenium/WebdriverIO/etc.
- Do **not** push commits without running `/bin/bash -p scripts/ci/ci-local.sh`.
- Do **not** edit `skills/e2e-reviewer/references/grep-patterns.md` without checking the matching pattern IDs against `packages/scanner/src/` and the reviewer taxonomy contract. The Node sources implement detection; `scan.sh` only verifies and launches the generated bundle. `grep-patterns.md` is an ID-meaning reference for Phase 2 / debugger lookup.
- Do **not** create side effects on third-party repos when validating the skill. Cloning into `testbed/` and running `scan.sh` locally is allowed; pushing to forks, opening PRs/issues, posting comments, or any state-changing `gh` command is not.

## Installation Paths Documented for Users

`README.md` starts its Install section with the all-in-one installer and one cross-agent skills CLI command, followed by Claude Code and Codex plugin alternatives. Keep these paths synchronized:

- **All-in-one**: from a reviewed checkout, `bash install.sh --host <claude|codex> [--project /path/to/project] [--dry-run]`. Reuses the verified skill/agent installers. Claude setup also prepares the shared canonical skill store through the Codex projection; dedicated agents target only the selected host. Project setup uses the installed Playwright CLI in a temporary workspace, copies official agent definitions without seed/spec files, and merges project MCP configuration after collision checks. It requires Node.js 22.20+ with npm/npx at standard system or Homebrew locations. Restart, approval, live tool discovery, fixtures and browser readiness remain separate.
- **Claude Code**: plugin marketplace — `/plugin marketplace add voidmatcha/e2e-skills` → `/plugin install e2e-skills@voidmatcha` (reads `.claude-plugin/plugin.json` + `marketplace.json`).
- **Codex**: the skills-only Codex CLI variant is `npx --yes skills@1.5.21 add voidmatcha/e2e-skills --skill '*' -g -a codex`; Use `-a claude-code` for the Claude Code skills-only variant. The skill copies land in `~/.agents/skills/`, where Codex/omx auto-discovers their `SKILL.md` files. This path does not install the root `.codex-plugin/plugin.json`; that interface manifest belongs to the alternative Codex plugin marketplace path: `codex plugin marketplace add voidmatcha/e2e-skills` → `codex plugin add e2e-skills@voidmatcha`.
- **skills.sh / other agents (Cursor, OpenCode, Gemini CLI, and more)**: one generalized section — the global install `npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all` is the primary command, with `-a <agent>` mentioned as the single-agent variant (agent names must be verified in the `vercel-labs/skills` supported-agents list; do not document names that are not in it).
- **Manual clone for Claude Code**: clone the repository to `~/.claude/e2e-skills`, then symlink each of the four `skills/<name>` directories directly into `~/.claude/skills/<name>`; Claude Code documents direct per-skill roots and supports those symlinks. The README commands must fail rather than overwrite an existing same-named skill and must tell users to verify all four through `/skills`.

The install paths above cover every supported host. Use the all-in-one route for guided Claude Code/Codex setup and the single `skills` CLI command for skills-only cross-agent installation; the host plugin marketplaces remain supported alternatives.

## License

Apache-2.0. Match the parent license in any new file you add.
