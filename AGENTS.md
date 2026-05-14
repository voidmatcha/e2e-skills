› **Reading this in Claude Code?** See also `CLAUDE.md` if present. This file is read by Codex, Cursor, Copilot, Gemini CLI, OpenCode, and other agents that follow the `AGENTS.md` convention.

# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, OpenCode, Cursor, Gemini CLI, Copilot, and others) working in this repository.

## Repository Overview

`e2e-skills` is a bundle of four Agent Skills for end-to-end test work on Playwright and Cypress projects:

- `playwright-test-generator` — generates Playwright E2E tests from scratch (coverage-gap analysis → live-browser exploration → approval gate → review).
- `e2e-reviewer` — static review of existing Playwright/Cypress specs against 19 anti-patterns grouped P0/P1/P2.
- `playwright-debugger` — root-cause diagnosis from `playwright-report/`.
- `cypress-debugger` — root-cause diagnosis from `cypress/reports/` (mochawesome / JUnit).

The repo doubles as a Claude Code plugin (`.claude-plugin/`), a Codex plugin (`.codex-plugin/`), a cross-agent skill source via the `skills` CLI, and a standalone scanner (`scripts/e2e-smell-scan.sh`).

## Verification gate (must pass before commit)

```
[ ] bash scripts/ci/ci-local.sh          # 10 review checks + 10 drift smoke checks + 0 P0 smell hits
[ ] bash scripts/ci/pre-push-security.sh # secrets and credential leak guard
```

`ci-local.sh` is the single source of truth for what CI runs (shell syntax, parity, security, evals, public skill surface, framework scope, link integrity, docs orphan check, language, e2e smell scan). If you change any check, update this script first.

## Directory Layout

```
.
├── .claude-plugin/         # Claude Code plugin + marketplace manifests
│   ├── plugin.json
│   └── marketplace.json
├── .codex-plugin/          # Codex plugin manifest (interface display surface)
│   └── plugin.json
├── AGENTS.md               # This file (cross-agent canonical guide)
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
│   ├── e2e-smell-scan.sh   # Standalone P0/P1 grep scanner
│   └── ci/                 # CI parity, security, eval-metadata checks
├── docs/                   # Open-source assets (taxonomy, case studies, evals, scope, compat)
├── README.md
└── CHANGELOG.md
```

Each `skills/<name>/SKILL.md` is the contract. Everything in the skill body should be **task-actionable instructions for the agent**, not narrative documentation; supporting reference material (long tables, framework references) goes in sibling `.md` files and is read on demand.

## Conventions

- **Skill names**: kebab-case, must match the directory name and the `name:` in SKILL.md frontmatter.
- **SKILL.md frontmatter**: `name`, `description`, `license`, `metadata: { author, version }`. The description is the trigger surface — pack synonyms and the user's likely phrasing.
- **Pattern IDs**: 19 numbered anti-patterns (`#1`–`#18` plus `#3b`) with P0/P1/P2 severity. IDs are stable; do not renumber. Severity rationale: P0 = silent always-pass, P1 = poor diagnostics, P2 = maintenance.
- **Failure category IDs**: 14 codes (`F1`–`F14`) used by both debuggers. Codes are stable.
- **JUSTIFIED comments**: `// JUSTIFIED: <reason>` on the line above (or above the enclosing block / multi-line chain) suppresses scanner findings. Suppress for documented intent, never to hide a real finding.
- **Severity-first organization**: tables in SKILL.md, README, and `docs/e2e-test-smells.md` group by P0/P1/P2 in the same order.
- **English-only public surface**: SKILL.md, README, and `docs/` are English. CI enforces this (`Language` check).

## Frameworks in Scope

Playwright and Cypress only. The skill does not produce code or advice for Puppeteer, Selenium, WebdriverIO, TestCafe, or Nightwatch. See `docs/framework-scope.md` for the rationale. CI fails on accidental support claims for out-of-scope frameworks.

## Local Development Commands

```bash
# Full CI mirror — run before every commit
bash scripts/ci/ci-local.sh

# Individual stages
bash scripts/ci/review.sh           # parity, language, links, framework scope, orphans
bash scripts/ci/test-parity.sh      # drift smoke test (mutate-and-detect)
bash scripts/ci/validate-evals.sh   # eval JSON schema
bash scripts/ci/pre-push-security.sh
bash scripts/e2e-smell-scan.sh path/to/tests   # standalone scanner

# Plugin manifest sanity
python3 -m json.tool .claude-plugin/plugin.json
python3 -m json.tool .claude-plugin/marketplace.json
```

`ci-local.sh` runs all of the above and must be green before opening a PR.

### Local dev workflow (testbed + auto-reinstall)

```bash
# Clone any real Playwright/Cypress repo into testbed/ (gitignored) to exercise the skills
git clone --depth 1 https://github.com/calcom/cal.com testbed/cal.com
bash scripts/e2e-smell-scan.sh testbed/cal.com
# Invoke e2e-reviewer / playwright-debugger via the agent runtime as usual.

# Install the four skills from this repo as real copies (one-time setup; also cleans up any prior symlink install)
bash scripts/dev/reinstall-skills.sh

# Wire `git push` to refresh the installed copies via `skills update` (one-time, opt-in)
bash scripts/dev/install-hooks.sh
```

The reinstall script runs `npx skills remove` then `npx skills add <repo-root> --copy`, scoped to the four e2e-skills (other installed skills are untouched). `--copy` mode means the install is a real copy, not a symlink — uncommitted local edits in this repo do **not** leak into the Claude Code / Codex runtime. The pre-push hook (after `install-hooks.sh`) runs `npx skills update` on every `git push`, refreshing the installed copies so they match the HEAD being pushed. Override the agent list via `E2E_SKILLS_AGENTS` (default: `-a claude-code -a codex -a opencode`).

## When You Edit Skills

1. **Update parity surfaces in lock-step.** Adding or renaming a pattern means touching: the relevant `SKILL.md`, `docs/e2e-test-smells.md`, `README.md` Quick Reference table, `skills/e2e-reviewer/references/grep-patterns.md`, `.claude-plugin/plugin.json` description, `.claude-plugin/marketplace.json` description, and `.codex-plugin/plugin.json` description. CI fails fast if any one is out of step.
2. **Re-run the drift smoke test.** `scripts/ci/test-parity.sh` mutates known-bad versions of the files and asserts the parity check catches each one — keep it green when you add new parity rules.
3. **Add or update evals when behavior changes.** Each skill has an `evals/evals.json`. Eval IDs must follow the skill's naming convention (CI validates).
4. **Respect severity contracts.** P0 entries should be silent-always-pass smells; don't downgrade. P1/P2 should not creep into P0 just because they're easier to grep.

## Cross-host parity rules

Both the Claude Code plugin and the Codex plugin expose the same four public skills from the shared `skills/` directory. The two manifests differ only in schema shape and host-specific display fields — never in skill behavior. CI enforces:

- **Version parity**: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (the `e2e-skills` entry), and `.codex-plugin/plugin.json` must share the same `version` string. Bump all three together.
- **Description parity**: the 19 P0/P1/P2 pattern phrases must appear in order in every manifest description. The phrase order is owned by the `e2e-reviewer/SKILL.md` frontmatter; downstream manifests follow it.
- **Public skill surface**: `skills/<name>/SKILL.md` `name` field must match the directory name, and the four directory names must match `.claude-plugin/plugin.json` `skills` paths and the four `agents/openai.yaml` `name` fields.
- **Framework scope**: the word "Puppeteer" must not appear outside `docs/framework-scope.md`, including in any plugin manifest.

When you bump the bundle version, touch all three manifests in one commit. The drift smoke test (`scripts/ci/test-parity.sh`) mutates each manifest in turn to verify the parity checks actually catch drift.

## What Not to Do

- Do **not** add new file types under `docs/` without linking them from `README.md` or referencing them from a CI script — the docs orphan check will fail.
- Do **not** silently change a pattern ID, severity, or failure category code. Downstream evals and OSS adopters depend on them.
- Do **not** introduce out-of-scope framework code paths. Skills must say "out of scope" rather than emit half-working examples for Selenium/WebdriverIO/etc.
- Do **not** push commits without running `bash scripts/ci/ci-local.sh`.
- Do **not** edit `skills/e2e-reviewer/references/grep-patterns.md` without checking that the matching `Phase 1` block in `SKILL.md` still lines up — they are intentionally paired.

## Installation Paths Documented for Users

- **Claude Code marketplace**: `/plugin marketplace add voidmatcha/e2e-skills` → `/plugin install e2e-skills@voidmatcha` (reads `.claude-plugin/plugin.json` + `marketplace.json`).
- **Codex plugin**: registered via the Codex marketplace UI; reads `.codex-plugin/plugin.json` for `interface.displayName`, `defaultPrompt[]`, `brandColor`, and capabilities. Shared `skills/` is the source of truth for both hosts.
- **Cross-agent (Codex, OpenCode, Cursor, Gemini CLI, and 50+ others)**: `npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code -a codex -a opencode` (uses the `vercel-labs/skills` npm CLI).
- **Manual clone for Claude Code**: `git clone https://github.com/voidmatcha/e2e-skills.git ~/.claude/skills/e2e-skills`.

See `docs/agent-compatibility.md` for the full matrix.

## License

Apache-2.0. Match the parent license in any new file you add.
