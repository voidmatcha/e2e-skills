#!/usr/bin/env bash
# Validate optional named Codex-agent packaging without touching the real home.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP=$(mktemp -d /tmp/e2e-codex-agents.XXXXXX)
trap 'rm -rf "$TMP"' EXIT INT TERM

CODEX_HOME="$TMP" bash "$ROOT/scripts/dev/install-codex-agents.sh" >/dev/null

for name in e2e-finding-verifier e2e-failure-classifier; do
  cmp "$ROOT/.codex/agents/$name.toml" "$TMP/agents/$name.toml"
done

# Never overwrite a same-name user file that is not owned by e2e-skills.
# A copy carrying this installer's OWN historical marker must upgrade without
# forcing. The marker was renamed Codex -> Codex/OMX, and treating the older one
# as foreign blocked every existing install behind E2E_SKILLS_FORCE_CODEX_AGENTS.
printf '%s\n' '# e2e-skills Codex native agent: e2e-finding-verifier' \
  > "$TMP/agents/e2e-finding-verifier.toml"
CODEX_HOME="$TMP" bash "$ROOT/scripts/dev/install-codex-agents.sh" >/dev/null
cmp "$ROOT/.codex/agents/e2e-finding-verifier.toml" \
  "$TMP/agents/e2e-finding-verifier.toml"

printf '%s\n' '# user-owned custom agent' > "$TMP/agents/e2e-finding-verifier.toml"
if CODEX_HOME="$TMP" bash "$ROOT/scripts/dev/install-codex-agents.sh" >"$TMP/conflict.log" 2>&1; then
  echo "codex agent packaging: conflict guard did not fail" >&2
  exit 1
fi
grep -q 'refusing to overwrite non-e2e-skills file' "$TMP/conflict.log"

echo "codex agent packaging: install, parity, and conflict guard passed"
