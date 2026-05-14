#!/usr/bin/env bash
# Reinstall the 4 e2e-skills from this repo via the official `skills` CLI.
# Removes any prior install (including symlink installs) of these specific skills,
# then re-adds them as real copies (--copy). Copy mode means uncommitted local
# edits do NOT leak into the agent runtime — only pushed/synced state does.
# The pre-push hook (scripts/hooks/pre-push) runs `skills update` on each push
# to keep the installed copies in lock-step with HEAD.
#
# Overrides:
#   E2E_SKILLS_AGENTS  default: "-a claude-code -a codex -a opencode"

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILLS_CSV="cypress-debugger,e2e-reviewer,playwright-debugger,playwright-test-generator"

if [ -n "${E2E_SKILLS_AGENTS:-}" ]; then
  # shellcheck disable=SC2206
  AGENTS_FLAGS=($E2E_SKILLS_AGENTS)
else
  AGENTS_FLAGS=(-a claude-code -a codex -a opencode)
fi

echo "reinstall-skills: removing prior install (skills=$SKILLS_CSV)"
npx -y skills remove -g "${AGENTS_FLAGS[@]}" --skill "$SKILLS_CSV" -y || true

echo "reinstall-skills: adding from $REPO_ROOT as real copies (--copy)"
npx -y skills add "$REPO_ROOT" -g "${AGENTS_FLAGS[@]}" --skill "$SKILLS_CSV" --copy -y
