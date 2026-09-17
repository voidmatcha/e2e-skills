#!/usr/bin/env bash
# One-time setup: point git at the tracked hooks directory.
# After this, `git push` will reinstall the local skills install from HEAD.

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
echo "install-hooks: pre-push will now reinstall e2e-skills locally on each push"
echo "install-hooks: to disable, run: git config --unset core.hooksPath"
