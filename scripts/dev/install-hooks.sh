#!/usr/bin/env bash
# One-time setup: point git at the tracked hooks directory.
# After this, a `git push` that sends the checked-out HEAD to main, with no
# uncommitted skills/ edits, refreshes the local skills install.

set -euo pipefail

current=$(git config --get core.hooksPath || true)
if [ -n "$current" ] && [ "$current" != "scripts/hooks" ]; then
  echo "install-hooks: core.hooksPath is already set to '$current'; not replacing it." >&2
  echo "install-hooks: the hooks there would stop running. To switch anyway, run:" >&2
  echo "install-hooks:   git config core.hooksPath scripts/hooks" >&2
  exit 1
fi

git config core.hooksPath scripts/hooks
chmod +x scripts/hooks/* 2>/dev/null || true

echo "install-hooks: git core.hooksPath = scripts/hooks"
echo "install-hooks: pre-push will refresh the local e2e-skills install when a push sends HEAD to main"
echo "install-hooks: to disable, run: git config --unset core.hooksPath"
