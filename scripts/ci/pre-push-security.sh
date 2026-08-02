#!/bin/bash -p
# Local security gate for e2e-skills. Mirrors the lightweight checks used in CI.

builtin set -uo pipefail

# Establish the command trust boundary before resolving the repository or
# running external tools. The privileged shebang prevents direct invocations
# from processing BASH_ENV or imported functions before this file starts; the
# cleanup below also protects callers that explicitly run `/bin/bash script`.
PATH="/usr/bin:/bin:/usr/sbin:/sbin"
builtin export PATH
builtin unset CDPATH ENV BASH_ENV GLOBIGNORE
while IFS= builtin read -r imported_function; do
  builtin unset -f "$imported_function"
done < <(builtin compgen -A function)
builtin shopt -u expand_aliases
builtin unalias -a 2>/dev/null || true
builtin unset E2E_SECRET_GIT E2E_SECURITY_GIT E2E_SHELL_FIND

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR="."
REPO_ROOT="$(builtin cd -- "$SCRIPT_DIR/../.." && builtin pwd -P)" || {
  echo "pre-push-security: cannot resolve repo root" >&2
  exit 2
}
builtin cd -- "$REPO_ROOT" || {
  echo "pre-push-security: cannot cd to $REPO_ROOT" >&2
  exit 2
}

PYTHON_RUNNER="$REPO_ROOT/scripts/ci/lib/run-python-isolated.sh"
if [[ ! -f "$PYTHON_RUNNER" || ! -x "$PYTHON_RUNNER" ]]; then
  echo "pre-push-security: trusted isolated Python runner unavailable" >&2
  exit 2
fi
if ! "$PYTHON_RUNNER" -c 'import sys; assert __debug__ and sys.flags.isolated == 1' \
  >/dev/null; then
  echo "pre-push-security: trusted isolated Python runner unusable" >&2
  exit 2
fi

ERRORS=0
WARNINGS=0
PASSED=0

err() { echo "  [FAIL] $*" >&2; ERRORS=$((ERRORS + 1)); }
warn() { echo "  [WARN] $*" >&2; WARNINGS=$((WARNINGS + 1)); }
ok() { [ "$QUIET" = "1" ] || echo "  [OK] $*"; PASSED=$((PASSED + 1)); }
section() { [ "$QUIET" = "1" ] || { echo ""; echo "-- $* --"; }; }

section "Secrets"
secret_output=$("$PYTHON_RUNNER" scripts/ci/lib/scan-secrets.py --repo "$REPO_ROOT" 2>&1)
secret_status=$?
if [ "$secret_status" -eq 0 ]; then
  ok "no high-confidence secrets in source/config files"
elif [ "$secret_status" -eq 1 ]; then
  err "potential secrets found in source/config files"
  printf '%s\n' "$secret_output" | head -10 | sed 's/^/      /' >&2
else
  err "secret scanner infrastructure error (exit $secret_status)"
  printf '%s\n' "$secret_output" | head -10 | sed 's/^/      /' >&2
fi

section "Code injection"
run_policy_scan() {
  local rule="$1"
  local clean_message="$2"
  local finding_message="$3"
  local output
  local status
  output=$("$PYTHON_RUNNER" scripts/ci/lib/scan-security-policy.py --repo "$REPO_ROOT" --rule "$rule" 2>&1)
  status=$?
  if [ "$status" -eq 0 ]; then
    ok "$clean_message"
  elif [ "$status" -eq 1 ]; then
    err "$finding_message"
    printf '%s\n' "$output" | head -10 | sed 's/^/      /' >&2
  else
    err "$rule scanner infrastructure error (exit $status)"
    printf '%s\n' "$output" | head -10 | sed 's/^/      /' >&2
  fi
}

run_policy_scan "eval" "no bash eval() in shell scripts" "bash eval() found"
run_policy_scan "fixed-tmp" "no fixed temporary-directory paths in shell scripts" "fixed temporary-directory paths found"
run_policy_scan "backdoor" "no reverse-shell or backdoor shell patterns" "reverse-shell or backdoor pattern found"

section "Manifest validity"
"$PYTHON_RUNNER" -c \
  "import sys; sys.path.insert(0,'scripts/ci/lib'); import strict_json; strict_json._self_test()" \
  >/dev/null 2>&1 || \
  err "strict JSON regression self-test failed"
"$PYTHON_RUNNER" -c "import pathlib,sys; sys.path.insert(0,'scripts/ci/lib'); from strict_json import load_manifest_json; load_manifest_json(pathlib.Path('.claude-plugin/plugin.json'))" 2>/dev/null && \
  ok ".claude-plugin/plugin.json valid JSON" || err ".claude-plugin/plugin.json invalid JSON"
"$PYTHON_RUNNER" -c "import pathlib,sys; sys.path.insert(0,'scripts/ci/lib'); from strict_json import load_manifest_json; load_manifest_json(pathlib.Path('.claude-plugin/marketplace.json'))" 2>/dev/null && \
  ok ".claude-plugin/marketplace.json valid JSON" || err ".claude-plugin/marketplace.json invalid JSON"
"$PYTHON_RUNNER" -c "import pathlib,sys; sys.path.insert(0,'scripts/ci/lib'); from strict_json import load_manifest_json; load_manifest_json(pathlib.Path('.codex-plugin/plugin.json'))" 2>/dev/null && \
  ok ".codex-plugin/plugin.json valid JSON" || err ".codex-plugin/plugin.json invalid JSON"

if "$PYTHON_RUNNER" - <<'PY'
import json
import pathlib
import re
import sys

sys.path.insert(0, 'scripts/ci/lib')
from strict_json import load_manifest_json
from validate_codex import collect_codex_errors
from version_contract import canonical_semver_error

errors = []

def parse_openai_manifest(path):
    """Parse the deliberately small agents/openai.yaml schema, fail closed."""
    text = path.read_text(encoding='utf-8')
    if text.startswith('\ufeff'):
        raise ValueError("UTF-8 BOM is not supported")
    if '\t' in text:
        raise ValueError("tabs are not allowed")
    top = {}
    metadata = {}
    current = None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if line.startswith(' '):
            match = re.fullmatch(r"  ([A-Za-z_][A-Za-z0-9_-]*):[ ]+(.+)", line)
            if current != 'metadata' or not match:
                raise ValueError(f"line {number}: unsupported indentation or nested value")
            key, value = match.groups()
            if key in metadata:
                raise ValueError(f"line {number}: duplicate metadata key {key!r}")
            metadata[key] = value
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_-]*):(?:[ ]+(.*))?", line)
        if not match:
            raise ValueError(f"line {number}: unsupported YAML syntax")
        key, value = match.groups()
        if key in top:
            raise ValueError(f"line {number}: duplicate top-level key {key!r}")
        if key == 'metadata':
            if value is not None:
                raise ValueError(f"line {number}: metadata must be a mapping")
            top[key] = metadata
        else:
            if value is None or not value.strip():
                raise ValueError(f"line {number}: {key} must have a scalar value")
            if re.search(r":\s|(?:^|\s)#", value):
                raise ValueError(f"line {number}: unsupported ambiguous plain scalar")
            top[key] = value
        current = key
    expected_top = {'name', 'description', 'metadata', 'allow_implicit_invocation'}
    if set(top) != expected_top:
        raise ValueError(
            f"top-level keys must be exactly {sorted(expected_top)!r}, got {sorted(top)!r}"
        )
    if set(metadata) != {'short-description'}:
        raise ValueError("metadata must contain exactly short-description")
    if top['allow_implicit_invocation'] not in {'true', 'false'}:
        raise ValueError("allow_implicit_invocation must be true or false")
    return top

plugin = load_manifest_json(pathlib.Path('.claude-plugin/plugin.json'))
marketplace = load_manifest_json(pathlib.Path('.claude-plugin/marketplace.json'))
codex_plugin = load_manifest_json(pathlib.Path('.codex-plugin/plugin.json'))

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

errors.extend(collect_codex_errors(codex_plugin, expected, pathlib.Path('.')))

for skill_dir in skill_dirs:
    skill_file = skill_dir / 'SKILL.md'
    skill_text = skill_file.read_text(encoding='utf-8')
    frontmatter = re.search(r"^---\n(.*?)\n---", skill_text, re.S)
    if not frontmatter:
        errors.append(f"{skill_file}: missing YAML frontmatter")
    else:
        desc = re.search(r"^description:\s*(.+?)\s*$", frontmatter.group(1), re.M)
        if not desc:
            errors.append(f"{skill_file}: missing frontmatter description")
        else:
            val = desc.group(1).strip()
            quoted = (val.startswith("'") and val.endswith("'")) or (
                val.startswith('"') and val.endswith('"')
            )
            desc_value = val[1:-1] if quoted else val
            if len(desc_value) > 1024:
                errors.append(
                    f"{skill_file}: frontmatter description exceeds 1024 characters "
                    f"({len(desc_value)})"
                )
        version = re.search(
            r"^  version:\s*['\"]?([^'\"\n]+)['\"]?\s*$",
            frontmatter.group(1),
            re.M,
        )
        if not version:
            errors.append(f"{skill_file}: missing metadata.version in frontmatter")
        else:
            skill_version = version.group(1).strip()
            version_error = canonical_semver_error(
                skill_version, f"{skill_file}: metadata.version"
            )
            if version_error:
                errors.append(version_error)
            elif skill_version != plugin_version:
                errors.append(
                    f"{skill_file}: metadata.version {skill_version!r} "
                    f"does not match plugin version {plugin_version!r}"
                )

    manifest = skill_dir / 'agents' / 'openai.yaml'
    if not manifest.exists():
        errors.append(f"{manifest}: missing OpenAI agent manifest")
        continue
    try:
        top = parse_openai_manifest(manifest)
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"{manifest}: invalid OpenAI agent YAML: {exc}")
        continue
    if top['name'] != skill_dir.name:
        errors.append(f"{manifest}: name must match directory {skill_dir.name}")

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)
PY
then
  ok "plugin versions, skill list, SKILL.md descriptions, and OpenAI manifests match repo conventions"
else
  err "plugin/OpenAI manifest convention check failed"
fi

section "Shell syntax"
syntax_fail=0
shell_file_count=0
shell_enumerator="$REPO_ROOT/scripts/ci/lib/enumerate-shell-files.sh"
if [ ! -x "$shell_enumerator" ]; then
  err "trusted shell enumerator unavailable"
elif ! shell_files=$("$shell_enumerator" "$REPO_ROOT"); then
  err "shell enumeration failed"
else
  while IFS= read -r file; do
    [ -z "$file" ] && continue
    shell_file_count=$((shell_file_count + 1))
    if ! /bin/bash -n "$file" 2>/dev/null; then
      err "syntax error: $file"
      syntax_fail=$((syntax_fail + 1))
    fi
  done <<< "$shell_files"
  if [ "$shell_file_count" -eq 0 ]; then
    err "shell enumeration returned zero files"
  elif [ "$syntax_fail" -eq 0 ]; then
    ok "all $shell_file_count shell scripts parse"
  fi
fi

section "Hardcoded paths"
# Scope: scripts/, skills/, and the plugin manifests. README/CHANGELOG/docs are
# allowed to use example paths freely (the previous `grep -vE '…|example|~/'`
# exclusion was too loose to catch a real leak in those files anyway), but the
# manifest JSON files MUST be scanned — a leaked `/Users/...` path there would
# ship directly to every plugin user.
run_policy_scan \
  "hardcoded-home" \
  "no hardcoded absolute user-home paths in scripts/, skills/, or plugin manifests" \
  "hardcoded absolute user-home paths found in scripts/, skills/, or plugin manifests"

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
