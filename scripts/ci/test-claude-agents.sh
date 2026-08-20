#!/bin/bash
# Contract test for the user-level Claude Code subagent installer.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP=$(mktemp -d /tmp/e2e-claude-agents.XXXXXX)
trap 'rm -rf "$TMP"' EXIT INT TERM

CLAUDE_CONFIG_DIR="$TMP" bash "$ROOT/scripts/dev/install-claude-agents.sh" >/dev/null
for name in e2e-finding-verifier e2e-failure-classifier; do
  cmp "$ROOT/agents/$name.md" "$TMP/agents/$name.md"
  # Claude Code identifies a user-level subagent only by frontmatter `name:`, so
  # a mismatch here means the installed file would be discovered under the wrong
  # identity or not at all.
  grep -qx "name: $name" "$TMP/agents/$name.md"
  grep -qx "<!-- e2e-skills Claude Code native agent: $name -->" "$TMP/agents/$name.md"
done

# Re-running must be idempotent rather than tripping the ownership guard on the
# installer's own output.
CLAUDE_CONFIG_DIR="$TMP" bash "$ROOT/scripts/dev/install-claude-agents.sh" >/dev/null
cmp "$ROOT/agents/e2e-finding-verifier.md" "$TMP/agents/e2e-finding-verifier.md"

# An e2e-skills file that is merely out of date must upgrade without forcing.
printf '%s\n' '<!-- e2e-skills Claude Code native agent: e2e-finding-verifier -->' \
  > "$TMP/agents/e2e-finding-verifier.md"
CLAUDE_CONFIG_DIR="$TMP" bash "$ROOT/scripts/dev/install-claude-agents.sh" >/dev/null
cmp "$ROOT/agents/e2e-finding-verifier.md" "$TMP/agents/e2e-finding-verifier.md"

# A user-authored agent of the same name must never be overwritten silently.
printf '%s\n' '# user-owned custom agent' > "$TMP/agents/e2e-finding-verifier.md"
if CLAUDE_CONFIG_DIR="$TMP" bash "$ROOT/scripts/dev/install-claude-agents.sh" \
    >"$TMP/conflict.log" 2>&1; then
  echo "claude agent packaging: conflict guard did not fail" >&2
  exit 1
fi
grep -q 'refusing to overwrite non-e2e-skills file' "$TMP/conflict.log"

# A dotfiles-managed agents directory symlinks each file; writing through the
# link would mutate the tracked original in the dotfiles repository.
rm -f "$TMP/agents/e2e-finding-verifier.md"
ln -s "$ROOT/agents/e2e-failure-classifier.md" "$TMP/agents/e2e-finding-verifier.md"
if CLAUDE_CONFIG_DIR="$TMP" bash "$ROOT/scripts/dev/install-claude-agents.sh" \
    >"$TMP/symlink.log" 2>&1; then
  echo "claude agent packaging: symlink guard did not fail" >&2
  exit 1
fi
grep -q 'refusing symlinked destination file' "$TMP/symlink.log"

echo "claude agent packaging: install, parity, idempotence, upgrade, and guards passed"
