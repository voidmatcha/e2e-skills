#!/usr/bin/env bash
# Reinstall the 4 e2e-skills from this repo via the official `skills` CLI.
# Removes any prior install (including older symlink installs) of these
# specific skills, then re-adds them as real copies (--copy). Copy mode
# means uncommitted local edits do NOT leak into the agent runtime — only
# committed/pushed state does. The pre-push hook calls this script to
# refresh installs on every push, so first push acts as initial install.
#
# Overrides:
#   E2E_SKILLS_AGENTS  default: "-a claude-code -a codex"
#                      (set to "-a claude-code -a codex -a opencode" or other -a flags to install elsewhere)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILLS=(cypress-debugger e2e-reviewer playwright-debugger playwright-test-generator)

if [ -n "${E2E_SKILLS_AGENTS:-}" ]; then
  # shellcheck disable=SC2206
  AGENTS_FLAGS=($E2E_SKILLS_AGENTS)
else
  AGENTS_FLAGS=(-a claude-code -a codex)
fi

echo "reinstall-skills: removing prior install (${SKILLS[*]})"
npx -y skills remove "${SKILLS[@]}" -g "${AGENTS_FLAGS[@]}" -y || true

echo "reinstall-skills: adding from $REPO_ROOT as real copies (--copy)"
npx -y skills add "$REPO_ROOT" "${SKILLS[@]}" -g "${AGENTS_FLAGS[@]}" --copy -y
