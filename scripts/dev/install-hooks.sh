#!/usr/bin/env bash
# One-time setup: point git at the tracked hooks directory.
# After this, `git push` will reinstall the local skills install from HEAD.

set -euo pipefail

git config core.hooksPath scripts/hooks
chmod +x scripts/hooks/* 2>/dev/null || true

echo "install-hooks: git core.hooksPath = scripts/hooks"
echo "install-hooks: pre-push will now reinstall e2e-skills locally on each push"
echo "install-hooks: to disable, run: git config --unset core.hooksPath"
