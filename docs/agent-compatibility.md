# Agent Compatibility

This repository uses the Agent Skills `SKILL.md` format and is meant to work across Claude Code, Codex, and OpenCode-style environments.

## Claude Code

The `skills` CLI install below also targets Claude Code. As an alternative, use the plugin marketplace flow:

```text
/plugin marketplace add voidmatcha/e2e-skills
/plugin install e2e-skills@voidmatcha
```

## Skills CLI User Install

Quick install all four skills globally for Claude Code, Codex, and OpenCode:

```bash
npx skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code -a codex -a opencode
```

If the `skills` CLI is already installed, use the same command without `npx`:

```bash
skills add voidmatcha/e2e-skills --skill '*' -g -a claude-code -a codex -a opencode
```

To install to every supported agent instead:

```bash
npx skills add voidmatcha/e2e-skills --skill '*' -g --agent '*'
```

## Codex

The repo ships a Codex plugin manifest at `.codex-plugin/plugin.json` that points to the same shared `skills/` directory used by Claude Code. Its `interface` block carries Codex-specific display fields (`displayName`, `shortDescription`, `longDescription`, `developerName`, `category`, `capabilities`, `websiteURL`, `defaultPrompt[]`, `brandColor`). Versions are kept in lock-step with the Claude Code manifests by CI (`scripts/ci/review.sh` Check 6).

Each skill also includes an `agents/openai.yaml` per-skill manifest, which the `vercel-labs/skills` CLI reads to register the skill against the codex agent target during `npx skills add ... -a codex`.

## Compatibility Rule

Skill instructions should avoid assuming one host unless the step is explicitly host-specific. For example, an approval gate should say “present a plan and wait for user approval,” then describe host-specific planning-mode commands only as optional implementation details.
