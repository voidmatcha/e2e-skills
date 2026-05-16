#!/usr/bin/env bash
# Local security gate for e2e-skills. Mirrors the lightweight checks used in CI.

set -uo pipefail

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)" || {
  echo "pre-push-security: cannot resolve repo root" >&2
  exit 2
}
cd "$REPO_ROOT" || {
  echo "pre-push-security: cannot cd to $REPO_ROOT" >&2
  exit 2
}

ERRORS=0
WARNINGS=0
PASSED=0

err() { echo "  [FAIL] $*" >&2; ERRORS=$((ERRORS + 1)); }
warn() { echo "  [WARN] $*" >&2; WARNINGS=$((WARNINGS + 1)); }
ok() { [ "$QUIET" = "1" ] || echo "  [OK] $*"; PASSED=$((PASSED + 1)); }
section() { [ "$QUIET" = "1" ] || { echo ""; echo "-- $* --"; }; }

SELF="pre-push-security.sh"

section "Secrets"
secret_patterns=(
  'AKIA[0-9A-Z]{16}'
  'sk-[a-zA-Z0-9]{20,}'
  'ghp_[a-zA-Z0-9]{36}'
  'xox[baprs]-[0-9A-Za-z-]{10,}'
  'AIza[0-9A-Za-z_-]{35}'
  '-----BEGIN [A-Z ]*PRIVATE KEY-----'
)

secret_hits=0
for pattern in "${secret_patterns[@]}"; do
  hits=$(grep -rEn \
    --include='*.sh' --include='*.md' --include='*.json' --include='*.yaml' --include='*.yml' \
    --exclude="$SELF" --exclude='e2e-smell-report.txt' \
    --exclude-dir=.git --exclude-dir='*-workspace' --exclude-dir=node_modules --exclude-dir=testbed \
    "$pattern" . 2>/dev/null || true)
  if [ -n "$hits" ]; then
    err "potential secret matching /$pattern/"
    printf '%s\n' "$hits" | head -3 | sed 's/^/      /' >&2
    secret_hits=$((secret_hits + 1))
  fi
done
[ "$secret_hits" -eq 0 ] && ok "no high-confidence API keys, tokens, or private keys"

section "Code injection"
eval_hits=$(grep -rEn \
  --include='*.sh' --exclude="$SELF" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=testbed \
  "(^|[;&|])[[:space:]]*eval([[:space:]\"']|$)" . 2>/dev/null | \
  grep -vE "^[^:]+:[0-9]+:[[:space:]]*#" || true)
if [ -z "$eval_hits" ]; then
  ok "no bash eval() in shell scripts"
else
  err "bash eval() found"
  printf '%s\n' "$eval_hits" | head -5 | sed 's/^/      /' >&2
fi

fixed_tmp_hits=$(grep -rEn \
  --include='*.sh' --exclude="$SELF" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=testbed \
  '/tmp(/|/[A-Za-z0-9_.-]+)' . 2>/dev/null | \
  grep -vE 'mktemp|TMPDIR|TEMP_FILE|RESULT_FILE' || true)
if [ -z "$fixed_tmp_hits" ]; then
  ok "no fixed /tmp file paths in shell scripts"
else
  err "fixed /tmp paths found"
  printf '%s\n' "$fixed_tmp_hits" | head -5 | sed 's/^/      /' >&2
fi

backdoor_hits=$(grep -rEn \
  --include='*.sh' --exclude="$SELF" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=testbed \
  'nc -[el]|/dev/tcp/|bash -i.*&|reverse shell|exec [0-9]<>/dev/' . 2>/dev/null || true)
if [ -z "$backdoor_hits" ]; then
  ok "no reverse-shell or backdoor shell patterns"
else
  err "reverse-shell or backdoor pattern found"
  printf '%s\n' "$backdoor_hits" | head -5 | sed 's/^/      /' >&2
fi

section "Manifest validity"
if command -v python3 >/dev/null 2>&1; then
  python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))" 2>/dev/null && \
    ok ".claude-plugin/plugin.json valid JSON" || err ".claude-plugin/plugin.json invalid JSON"
  python3 -c "import json; json.load(open('.claude-plugin/marketplace.json'))" 2>/dev/null && \
    ok ".claude-plugin/marketplace.json valid JSON" || err ".claude-plugin/marketplace.json invalid JSON"

  if python3 - <<'PY'
import json
import pathlib
import re
import sys

errors = []
plugin = json.loads(pathlib.Path('.claude-plugin/plugin.json').read_text())
marketplace = json.loads(pathlib.Path('.claude-plugin/marketplace.json').read_text())
codex_plugin = json.loads(pathlib.Path('.codex-plugin/plugin.json').read_text())

plugin_version = plugin.get('version')
market_versions = [entry.get('version') for entry in marketplace.get('plugins', [])]
codex_version = codex_plugin.get('version')
if not plugin_version or market_versions != [plugin_version] or codex_version != plugin_version:
    errors.append(
        f"version mismatch: plugin={plugin_version!r}, marketplace={market_versions!r}, codex={codex_version!r}"
    )

skill_dirs = sorted(path for path in pathlib.Path('skills').iterdir() if path.is_dir())
expected = {path.name for path in skill_dirs}
expected_paths = {f'./skills/{skill}' for skill in expected}
plugin_paths = plugin.get('skills')
if (
    not isinstance(plugin_paths, list)
    or not all(isinstance(path, str) for path in plugin_paths)
    or set(plugin_paths) != expected_paths
    or len(plugin_paths) != len(expected_paths)
):
    errors.append(f"plugin skills must be exactly these paths: {sorted(expected_paths)!r}")

for skill_dir in skill_dirs:
    manifest = skill_dir / 'agents' / 'openai.yaml'
    if not manifest.exists():
        errors.append(f"{manifest}: missing OpenAI agent manifest")
        continue
    text = manifest.read_text(encoding='utf-8')
    if '\t' in text:
        errors.append(f"{manifest}: tabs are not allowed")

    top = {}
    metadata = {}
    current = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if not line.startswith(' '):
            key, _, value = line.partition(':')
            current = key.strip()
            top[current] = value.strip()
            continue
        if current == 'metadata':
            match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
            if match:
                metadata[match.group(1)] = match.group(2).strip()

    if top.get('name') != skill_dir.name:
        errors.append(f"{manifest}: name must match directory {skill_dir.name}")
    for key in ('description', 'metadata', 'allow_implicit_invocation'):
        if key not in top:
            errors.append(f"{manifest}: missing {key}")
    if not metadata.get('short-description'):
        errors.append(f"{manifest}: missing metadata.short-description")
    if top.get('allow_implicit_invocation') not in {'true', 'false'}:
        errors.append(f"{manifest}: allow_implicit_invocation must be true or false")

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)
PY
  then
    ok "plugin versions, skill list, and OpenAI manifests match repo conventions"
  else
    err "plugin/OpenAI manifest convention check failed"
  fi
else
  warn "python3 not available; skipped manifest checks"
fi

section "Shell syntax"
syntax_fail=0
while IFS= read -r file; do
  [ -z "$file" ] && continue
  if ! bash -n "$file" 2>/dev/null; then
    err "syntax error: $file"
    syntax_fail=$((syntax_fail + 1))
  fi
done < <(find scripts -name '*.sh' -type f 2>/dev/null)
[ "$syntax_fail" -eq 0 ] && ok "all shell scripts parse"

section "Hardcoded paths"
hardcoded_paths=$(grep -rEn \
  --include='*.sh' --include='*.md' --include='*.json' --include='*.yaml' --include='*.yml' \
  --exclude="$SELF" --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=testbed --exclude-dir='*-workspace' \
  '/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/' . 2>/dev/null | \
  grep -vE 'CHANGELOG\.md|example|placeholder|~/' || true)
if [ -z "$hardcoded_paths" ]; then
  ok "no hardcoded absolute user-home paths"
else
  err "hardcoded absolute user-home paths found"
  printf '%s\n' "$hardcoded_paths" | head -5 | sed 's/^/      /' >&2
fi

echo ""
echo "========================================"
echo "  Pre-push security: $PASSED passed, $WARNINGS warnings, $ERRORS blockers"
echo "========================================"

if [ "$ERRORS" -gt 0 ]; then
  echo "  BLOCKERS found - fix before push" >&2
  exit 1
fi

[ "$QUIET" = "1" ] && echo "  clean"
exit 0
