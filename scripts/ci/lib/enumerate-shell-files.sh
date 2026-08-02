#!/usr/bin/env bash
# Enumerate repository shell scripts with a trusted, fail-closed find binary.

set -uo pipefail

FIND_BIN="/usr/bin/find"
if [[ "${1:-}" == "--test-find" ]]; then
  FIND_BIN="${2:-}"
  shift 2
fi

REPO_ROOT="${1:-}"
if [[ -z "$REPO_ROOT" || ! -d "$REPO_ROOT/scripts" ]]; then
  echo "shell-enumerator: expected repository root with scripts/: $REPO_ROOT" >&2
  exit 2
fi

case "$FIND_BIN" in
  /*) ;;
  *)
    echo "shell-enumerator: find executable path must be absolute" >&2
    exit 2
    ;;
esac
if [[ ! -x "$FIND_BIN" ]]; then
  echo "shell-enumerator: find executable unavailable: $FIND_BIN" >&2
  exit 2
fi

ENUM_TMP="$(mktemp -d)"
trap 'rm -rf "$ENUM_TMP"' EXIT
"$FIND_BIN" "$REPO_ROOT/scripts" \( -type f -o -type l \) -print0 \
  >"$ENUM_TMP/files" 2>"$ENUM_TMP/find.err"
FIND_STATUS=$?
if [[ "$FIND_STATUS" -ne 0 ]]; then
  echo "shell-enumerator: find failed (exit $FIND_STATUS)" >&2
  [[ -s "$ENUM_TMP/find.err" ]] && cat "$ENUM_TMP/find.err" >&2
  exit 2
fi

SHELL_FILES=()
while IFS= read -r -d '' file; do
  case "$file" in
    ""|*$'\n'*|*$'\r'*)
      echo "shell-enumerator: unsafe control character in discovered file name" >&2
      exit 4
      ;;
  esac
  if printf '%s' "$file" | LC_ALL=C grep -q '[[:cntrl:]]'; then
    echo "shell-enumerator: unsafe control character in discovered file name" >&2
    exit 4
  fi
  if [[ -L "$file" ]]; then
    case "$file" in
      "$REPO_ROOT/scripts/hooks/"*)
        echo "shell-enumerator: discovered hook path is a symlink: $file" >&2
        exit 4
        ;;
      *)
        continue
        ;;
    esac
  fi
  if [[ "$file" == *.sh ]]; then
    SHELL_FILES+=("$file")
    continue
  fi

  IFS= read -r first_line < "$file" || true
  if [[ "$first_line" =~ ^\#\![[:space:]]*/([^[:space:]/]+/)*(ba|da|k|z)?sh([[:space:]]|$) ]] ||
     [[ "$first_line" =~ ^\#\![[:space:]]*/(usr/)?bin/env[[:space:]]+(-S[[:space:]]+)?(ba|da|k|z)?sh([[:space:]]|$) ]]; then
    SHELL_FILES+=("$file")
  fi
done < "$ENUM_TMP/files"

if [[ ${#SHELL_FILES[@]} -eq 0 ]]; then
  echo "shell-enumerator: zero shell files found under $REPO_ROOT/scripts" >&2
  exit 3
fi

printf '%s\n' "${SHELL_FILES[@]}"
