#!/usr/bin/env bash
# Post-fix verification: static-check + AST-aware sed-artifact detection.
#
# Run after bulk sed/perl transforms (typically ≥10 files modified).
# Catches the two failure classes:
#   1. Compile errors from regex matching non-Locator subjects
#   2. AST anti-patterns sed accidentally introduced (double await, empty expect, orphan then)
#
# Usage: bash scripts/verify-fixes.sh <repo-path> [-- <file>...]
#   <file> paths are relative to <repo-path>; when given, the AST rules run
#   only on those files (whole-repo scan remains the no-args default).
# Env: Typechecking is disabled by default because a repository-local tsc is
#   project-controlled code. To opt in, all three values are required:
#     VERIFY_FIXES_RUN_TSC=1
#     VERIFY_FIXES_TRUST_REPO=1
#     VERIFY_FIXES_APPROVE_TSC_COMMAND='node_modules/.bin/tsc --noEmit'
#   The approved command runs with a minimized environment and is NOT sandboxed.
#   VERIFY_FIXES_SKIP_TSC=1 remains a compatibility override for callers that
#   own typechecking (for example scripts/pr-preflight.sh).
#   VERIFY_FIXES_AST_GREP=/absolute/path selects an explicit trusted executable.
# Exits 0 on clean, non-zero on issues found.

set -uo pipefail

REPO="${1:-.}"
[[ $# -gt 0 ]] && shift

EXPLICIT_FILES=()
EXPLICIT_MODE=false
if [[ "${1:-}" == "--" ]]; then
  EXPLICIT_MODE=true
  shift
  EXPLICIT_FILES=("$@")
fi

if [[ ! -d "$REPO" ]]; then
  echo "error: not a directory: $REPO" >&2
  exit 2
fi

# AST rules live with the verifier. Resolve only already-installed executables;
# postfix verification must never download and execute an unpinned package.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RULES_DIR="$SCRIPT_DIR/../skills/e2e-reviewer/scripts/ast-grep-rules"
REPO_CANONICAL="$(cd "$REPO" && pwd -P)"
VALIDATED_EXPLICIT_FILES=()

if [[ "$EXPLICIT_MODE" == "true" && ${#EXPLICIT_FILES[@]} -eq 0 ]]; then
  echo "error: unsafe explicit target list: at least one file is required after --" >&2
  exit 2
fi

validate_explicit_target() {
  local target="$1" part remaining current parent resolved
  case "$target" in
    "") echo "empty target"; return 1 ;;
    /*) echo "absolute target"; return 1 ;;
    -*) echo "option-like target"; return 1 ;;
  esac
  if printf '%s' "$target" | LC_ALL=C grep -q '[[:cntrl:]]'; then
    echo "control character in target"
    return 1
  fi
  case "/$target/" in
    */../*) echo "parent traversal"; return 1 ;;
    */./*) echo "dot path component"; return 1 ;;
    *//*) echo "empty path component"; return 1 ;;
  esac
  current="$REPO_CANONICAL"
  remaining="$target"
  while :; do
    case "$remaining" in
      */*)
        part="${remaining%%/*}"
        remaining="${remaining#*/}"
        ;;
      *)
        part="$remaining"
        remaining=""
        ;;
    esac
    current="$current/$part"
    if [[ -L "$current" ]]; then
      echo "symlink component"
      return 1
    fi
    [[ -n "$remaining" ]] || break
  done
  parent="$(cd -P "$(dirname "$REPO_CANONICAL/$target")" 2>/dev/null && pwd)" || {
    echo "unresolvable target parent"
    return 1
  }
  resolved="$parent/$(basename "$target")"
  case "$resolved" in
    "$REPO_CANONICAL"/*) ;;
    *) echo "target escapes repository"; return 1 ;;
  esac
  if [[ -L "$resolved" ]]; then
    echo "final target is a symlink"
    return 1
  fi
  if [[ ! -f "$resolved" ]]; then
    echo "target is not a regular file"
    return 1
  fi
  printf '%s\n' "$resolved"
}

for _f in "${EXPLICIT_FILES[@]}"; do
  if ! validated_target="$(validate_explicit_target "$_f")"; then
    echo "error: unsafe explicit target ($_f): $validated_target" >&2
    exit 2
  fi
  VALIDATED_EXPLICIT_FILES+=("$validated_target")
done

AST_GREP_CMD=()
EXEC_TMP="$(mktemp -d)"
mkdir -p "$EXEC_TMP/home"
trap 'rm -rf "$EXEC_TMP"' EXIT
SAFE_EXEC_PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"

canonical_executable() {
  local candidate="$1"
  local link_target
  local candidate_dir
  local candidate_base
  local symlink_hops=0

  [[ "$candidate" == /* ]] || return 1
  while [[ -L "$candidate" ]]; do
    symlink_hops=$((symlink_hops + 1))
    [[ "$symlink_hops" -le 40 ]] || return 1
    link_target="$(readlink "$candidate")" || return 1
    if [[ "$link_target" == /* ]]; then
      candidate="$link_target"
    else
      candidate="$(dirname "$candidate")/$link_target"
    fi
  done

  candidate_dir="$(cd -P "$(dirname "$candidate")" 2>/dev/null && pwd)" || return 1
  candidate_base="$(basename "$candidate")"
  printf '%s/%s\n' "$candidate_dir" "$candidate_base"
}

is_target_controlled() {
  if [[ "$REPO_CANONICAL" == "/" ]]; then
    return 0
  fi
  case "$1" in
    "$REPO_CANONICAL"|"$REPO_CANONICAL"/*) return 0 ;;
    *) return 1 ;;
  esac
}

accept_ast_grep() {
  local candidate="$1"
  local resolved

  [[ -x "$candidate" ]] || return 1
  resolved="$(canonical_executable "$candidate")" || return 1
  [[ -x "$resolved" ]] || return 1
  if is_target_controlled "$resolved"; then
    return 2
  fi
  AST_GREP_CMD=("$resolved")
  return 0
}

if [[ -n "${VERIFY_FIXES_AST_GREP:-}" ]]; then
  if [[ "$VERIFY_FIXES_AST_GREP" != /* ]]; then
    echo "error: VERIFY_FIXES_AST_GREP must be an absolute path: $VERIFY_FIXES_AST_GREP" >&2
    exit 2
  fi
  accept_ast_grep "$VERIFY_FIXES_AST_GREP"
  ast_accept_status=$?
  if [[ "$ast_accept_status" -eq 2 ]]; then
    echo "error: VERIFY_FIXES_AST_GREP resolves inside the target repository: $VERIFY_FIXES_AST_GREP" >&2
    exit 2
  elif [[ "$ast_accept_status" -ne 0 ]]; then
    echo "error: VERIFY_FIXES_AST_GREP is not a trusted executable: $VERIFY_FIXES_AST_GREP" >&2
    exit 2
  fi
else
  for ast_candidate in \
    "$SCRIPT_DIR/../node_modules/.bin/ast-grep" \
    "$SCRIPT_DIR/../node_modules/.bin/sg"
  do
    if accept_ast_grep "$ast_candidate"; then
      break
    fi
  done

  if [[ ${#AST_GREP_CMD[@]} -eq 0 ]]; then
    for ast_name in ast-grep sg; do
      ast_candidate="$(command -v "$ast_name" 2>/dev/null || true)"
      [[ "$ast_candidate" == /* ]] || continue
      if accept_ast_grep "$ast_candidate"; then
        break
      fi
    done
  fi
fi

if [[ ${#AST_GREP_CMD[@]} -eq 0 ]]; then
  echo "error: ast-grep required for postfix verification; install it locally or system-wide, or set VERIFY_FIXES_AST_GREP to a trusted executable" >&2
  exit 2
fi

# Collect changed files since HEAD if inside a git repo.
CHANGED_FILES=""
if (cd "$REPO" && git rev-parse --git-dir >/dev/null 2>&1); then
  CHANGED_FILES=$(cd "$REPO" && git diff --name-only HEAD 2>/dev/null | grep -E '\.(ts|tsx|js|jsx|cy\.ts|cy\.js)$' || true)
  if [[ -n "$CHANGED_FILES" ]]; then
    CHANGED_COUNT=$(printf '%s\n' "$CHANGED_FILES" | wc -l | tr -d ' ')
    echo "==> verifying $CHANGED_COUNT changed file(s) since HEAD"
  else
    echo "==> no tracked file changes since HEAD; running full-repo verify"
  fi
else
  echo "==> not a git repo; running full-repo verify"
fi

issues=0

# --- Step 1: TypeScript / JavaScript static check ---
echo
echo "--- Static check ---"
if [[ "${VERIFY_FIXES_SKIP_TSC:-0}" == "1" ]]; then
  echo "(VERIFY_FIXES_SKIP_TSC=1 — caller owns typechecking; skipping tsc)"
elif [[ "${VERIFY_FIXES_RUN_TSC:-0}" != "1" ]]; then
  echo "(AST-only default — repository-local tsc is not executed; set VERIFY_FIXES_RUN_TSC=1 with trust and exact-command approval to opt in)"
fi
has_tsconfig=false
if (cd "$REPO" && [[ -f tsconfig.json ]] || [[ -f tsconfig.base.json ]]); then
  has_tsconfig=true
fi

if [[ "${VERIFY_FIXES_SKIP_TSC:-0}" == "1" ]]; then
  : # skipped above
elif [[ "${VERIFY_FIXES_RUN_TSC:-0}" != "1" ]]; then
  : # safe default reported above
elif [[ "$has_tsconfig" == "true" ]]; then
  tsc_bin="$REPO_CANONICAL/node_modules/.bin/tsc"
  approved_tsc="node_modules/.bin/tsc --noEmit"
  if [[ "${VERIFY_FIXES_TRUST_REPO:-0}" != "1" ]]; then
    echo "(tsc skipped — repository trust not declared; set VERIFY_FIXES_TRUST_REPO=1)"
  elif [[ "${VERIFY_FIXES_APPROVE_TSC_COMMAND:-}" != "$approved_tsc" ]]; then
    echo "(tsc skipped — exact command approval required (VERIFY_FIXES_APPROVE_TSC_COMMAND): $approved_tsc)"
  elif [[ ! -x "$tsc_bin" ]]; then
    echo "(tsc skipped — $tsc_bin is not executable)"
  else
    echo "NOTICE: executing approved repository-local tsc with a minimized environment; this is NOT SANDBOXED"
    tsc_output=$(
      cd "$REPO_CANONICAL" &&
        env -i \
          HOME="$EXEC_TMP/home" \
          TMPDIR="$EXEC_TMP" \
          PATH="$SAFE_EXEC_PATH" \
          LANG=C \
          LC_ALL=C \
          "$tsc_bin" --noEmit 2>&1
    )
    tsc_exit=$?
    if [[ "$tsc_exit" -eq 0 ]]; then
      echo "✓ tsc --noEmit clean"
    else
      echo "✗ tsc --noEmit reported errors (exit $tsc_exit):"
      printf '%s\n' "$tsc_output" | tail -10 | sed 's/^/  /'
      issues=$((issues + 1))
    fi
  fi
elif (cd "$REPO" && [[ -f package.json ]]); then
  echo "(no tsconfig.json found — skipping tsc; consider eslint for JS)"
else
  echo "(no package.json — skipping language static check)"
fi

# --- Step 2: AST-aware sed-artifact detection ---
echo
echo "--- AST-aware sed-artifact detection ---"

# Scan targets: explicit file list (relative to $REPO) when given, else whole repo.
SCAN_TARGETS=("$REPO")
if [[ ${#EXPLICIT_FILES[@]} -gt 0 ]]; then
  SCAN_TARGETS=("${VALIDATED_EXPLICIT_FILES[@]}")
  echo "(scanning ${#SCAN_TARGETS[@]} explicit file(s) only)"
fi

run_postfix_rule() {
  local rule_file="$1"
  local label="$2"
  local output
  local ast_status
  if [[ ! -f "$RULES_DIR/$rule_file" ]]; then
    echo "✗ $label — missing rule: $RULES_DIR/$rule_file"
    issues=$((issues + 1))
    return
  fi
  output=$("${AST_GREP_CMD[@]}" scan --rule "$RULES_DIR/$rule_file" "${SCAN_TARGETS[@]}" 2>&1)
  ast_status=$?
  local count
  count=$(printf '%s\n' "$output" | grep -cE '^(error|warning|info)\[' || true)
  count=${count:-0}
  if [[ "$ast_status" -gt 1 || ( "$ast_status" -ne 0 && "$count" -eq 0 ) ]]; then
    echo "✗ $label — ast-grep failed (exit $ast_status)"
    printf '%s\n' "$output" | head -20 | sed 's/^/  /'
    issues=$((issues + 1))
  elif [[ "$count" -gt 0 ]]; then
    echo "✗ $label ($count hit(s))"
    printf '%s\n' "$output" | head -20 | sed 's/^/  /'
    issues=$((issues + count))
  else
    echo "✓ $label — no hits"
  fi
}

run_postfix_rule 'sg-postfix-double-await.yml'   'Double await (sed artifact)'
run_postfix_rule 'sg-postfix-empty-expect.yml'   'Empty expect() (sed artifact)'
run_postfix_rule 'sg-postfix-orphan-then.yml'    'Orphan .then() after web-first (review)'

# --- Summary ---
echo
if [[ "$issues" -eq 0 ]]; then
  echo "✓ verify-fixes: clean"
  exit 0
else
  echo "✗ verify-fixes: $issues issue(s) found — review above"
  exit 1
fi
