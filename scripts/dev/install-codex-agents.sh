#!/usr/bin/env bash
# Install the optional named Codex-native e2e agents from this checkout.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
DEST="$CODEX_HOME_DIR/agents"
AGENTS=(e2e-finding-verifier e2e-failure-classifier)

mkdir -p "$DEST"

for name in "${AGENTS[@]}"; do
  src="$REPO_ROOT/.codex/agents/$name.toml"
  dst="$DEST/$name.toml"
  [ -f "$src" ] || { echo "install-codex-agents: missing $src" >&2; exit 1; }

  if [ -f "$dst" ] && ! cmp -s "$src" "$dst"; then
    if ! grep -q '^# e2e-skills Codex/OMX native agent:' "$dst" && [ "${E2E_SKILLS_FORCE_CODEX_AGENTS:-0}" != "1" ]; then
      echo "install-codex-agents: refusing to overwrite non-e2e-skills file: $dst" >&2
      echo "set E2E_SKILLS_FORCE_CODEX_AGENTS=1 only if replacement is intentional" >&2
      exit 1
    fi
  fi

  cp "$src" "$dst"
  echo "install-codex-agents: installed $dst"
done

for name in "${AGENTS[@]}"; do
  discovered=$(sed -n 's/^name = "\([^"]*\)"[[:space:]]*$/\1/p' "$DEST/$name.toml" | head -1)
  if [ "$discovered" != "$name" ]; then
    echo "install-codex-agents: discovery validation failed for $name" >&2
    exit 1
  fi
done
echo "install-codex-agents: discovery files valid"

echo "Restart Codex sessions opened outside this repository so the named agents are rediscovered."
