#!/bin/bash -p
# Portability: BSD sed lacks `\b` and uses a different `-i`; use explicit
# character anchors and `perl -i -0pe` for multiline edits. The scanner needs
# PCRE2-capable `rg`. Privileged Bash plus this builtin scrub blocks startup
# files/functions before the inherited PATH trust check. Do not reset PATH here:
# it is inspected below, while still untrusted, before the trusted system path
# replaces it.
builtin unset CDPATH ENV BASH_ENV GLOBIGNORE
while IFS= builtin read -r imported_function; do
  builtin unset -f "$imported_function"
done < <(builtin compgen -A function)
builtin shopt -u expand_aliases
builtin unalias -a 2>/dev/null || true

builtin set -uo pipefail

if (( $# > 1 )); then
  printf 'error: multiple scan roots are not supported; invoke scan.sh once per root\n' >&2
  exit 2
fi

ROOT="${1:-.}"
REQUESTED_ROOT="$ROOT"
FAIL_ON="${E2E_SMELL_FAIL_ON:-p0}"
case "$ROOT" in
  -*) printf "error: scan root must not begin with '-': %s\n" "$ROOT" >&2; exit 2 ;;
esac
if [[ -L "$ROOT" ]]; then
  printf 'error: symbolic-link scan roots are not supported: %s\n' "$ROOT" >&2
  exit 2
fi
REQUESTED_ROOT_KIND=""
REQUESTED_ROOT_REAL=""
if [[ -d "$ROOT" ]]; then
  REQUESTED_ROOT_KIND="directory"
  REQUESTED_ROOT_REAL=$(cd "$ROOT" 2>/dev/null && pwd -P)
  SCAN_ROOT_REAL="$REQUESTED_ROOT_REAL"
elif [[ -f "$ROOT" ]]; then
  REQUESTED_ROOT_KIND="file"
  _root_parent=${ROOT%/*}
  _root_name=${ROOT##*/}
  [[ "$_root_parent" == "$ROOT" ]] && _root_parent="."
  [[ -z "$_root_parent" ]] && _root_parent="/"
  SCAN_ROOT_REAL=$(cd "$_root_parent" 2>/dev/null && pwd -P)
  REQUESTED_ROOT_REAL="$SCAN_ROOT_REAL/$_root_name"
else
  SCAN_ROOT_REAL=""
fi
if [[ -n "$REQUESTED_ROOT_REAL" ]]; then
  # All scanner traversal uses the initially resolved path. Keep the lexical
  # argument only as an identity witness so a swapped parent-component symlink
  # cannot redirect later preflight/discovery/tier operations.
  ROOT="$REQUESTED_ROOT_REAL"
fi

reject_path_entries_under() {
  local _trust_root="$1" _path_ifs _path_entry _path_real
  [[ -n "$_trust_root" ]] || return 0
  _path_ifs="$IFS"
  IFS=':'
  for _path_entry in ${PATH:-}; do
    [[ -n "$_path_entry" ]] || _path_entry="."
    if [[ -d "$_path_entry" ]]; then
      _path_real=$(cd "$_path_entry" 2>/dev/null && pwd -P)
    else
      case "$_path_entry" in
        /*) _path_real="$_path_entry" ;;
        *) _path_real="$PWD/$_path_entry" ;;
      esac
    fi
    case "$_path_real" in
      "$_trust_root"|"$_trust_root"/*)
        IFS="$_path_ifs"
        printf 'error: refusing PATH entry inside the requested scan root: %s\n' "$_path_real" >&2
        exit 2
        ;;
    esac
  done
  IFS="$_path_ifs"
}

# No project-controlled PATH entry may run before tool trust is established.
# Resolve PATH directories with shell builtins only; this gate therefore runs
# before dirname, basename, realpath, mktemp, awk, sed, grep, or rg.
reject_path_entries_under "$SCAN_ROOT_REAL"

# Keep every JavaScript/TypeScript include surface on the same extension set.
# The comma-only value is also a machine-readable contract for regression tests;
# ripgrep expands the derived brace globs itself.
CODE_EXTENSIONS='ts,js,tsx,jsx,mts,mjs,cts,cjs'
ALL_CODE_GLOB="*.{$CODE_EXTENSIONS}"
PLAYWRIGHT_ASYNC_MATCHERS='toBeAttached|toBeChecked|toBeDisabled|toBeEditable|toBeEmpty|toBeEnabled|toBeFocused|toBeHidden|toBeInViewport|toBeOK|toBeVisible|toContainClass|toContainText|toHaveAccessibleDescription|toHaveAccessibleErrorMessage|toHaveAccessibleName|toHaveAttribute|toHaveCSS|toHaveClass|toHaveCount|toHaveId|toHaveJSProperty|toHaveRole|toHaveScreenshot|toHaveText|toHaveTitle|toHaveURL|toHaveValue|toHaveValues|toMatchAriaSnapshot'
ESLINT_FILE_GLOBS=""
_extension_ifs="$IFS"
IFS=','
for _code_extension in $CODE_EXTENSIONS; do
  [[ -n "$ESLINT_FILE_GLOBS" ]] && ESLINT_FILE_GLOBS="$ESLINT_FILE_GLOBS,"
  ESLINT_FILE_GLOBS="$ESLINT_FILE_GLOBS'**/*.$_code_extension'"
done
IFS="$_extension_ifs"

has_project_marker() {
  local directory="$1"
  [[ -f "$directory/package.json" ||
     -f "$directory/playwright.config.ts" ||
     -f "$directory/playwright.config.js" ||
     -f "$directory/playwright.config.mts" ||
     -f "$directory/playwright.config.mjs" ||
     -f "$directory/playwright.config.cts" ||
     -f "$directory/playwright.config.cjs" ||
     -f "$directory/cypress.config.ts" ||
     -f "$directory/cypress.config.js" ||
     -f "$directory/cypress.config.mts" ||
     -f "$directory/cypress.config.mjs" ||
     -f "$directory/cypress.config.cts" ||
     -f "$directory/cypress.config.cjs" ]]
}

# Tool trust follows the containing project, not only the requested subdirectory.
# Prefer the nearest Git worktree boundary. When Git metadata is absent, use the
# nearest package/framework-config ancestor; otherwise fall back to the scan root.
PROJECT_ROOT_REAL="$SCAN_ROOT_REAL"
if [[ -n "$SCAN_ROOT_REAL" ]]; then
  _project_cursor="$SCAN_ROOT_REAL"
  while :; do
    if [[ -e "$_project_cursor/.git" ]]; then
      PROJECT_ROOT_REAL="$_project_cursor"
      break
    fi
    [[ "$_project_cursor" == "/" ]] && break
    _project_parent=${_project_cursor%/*}
    [[ -z "$_project_parent" ]] && _project_parent="/"
    [[ "$_project_parent" == "$_project_cursor" ]] && break
    _project_cursor="$_project_parent"
  done
  if [[ "$PROJECT_ROOT_REAL" == "$SCAN_ROOT_REAL" && ! -e "$SCAN_ROOT_REAL/.git" ]]; then
    _project_cursor="$SCAN_ROOT_REAL"
    while :; do
      if has_project_marker "$_project_cursor"; then
        PROJECT_ROOT_REAL="$_project_cursor"
        break
      fi
      [[ "$_project_cursor" == "/" ]] && break
      _project_parent=${_project_cursor%/*}
      [[ -z "$_project_parent" ]] && _project_parent="/"
      [[ "$_project_parent" == "$_project_cursor" ]] && break
      _project_cursor="$_project_parent"
    done
  fi
fi
reject_path_entries_under "$PROJECT_ROOT_REAL"

# Do not let an inherited PATH select scanner dependencies. The scanner's shell
# utilities come only from the operating-system path. Tools commonly installed
# outside that path (rg, node/npx, ast-grep) are bound below from deterministic
# locations or an explicit absolute-path override.
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
unset RIPGREP_CONFIG_PATH

validate_explicit_tool() {
  local variable_name="$1" candidate="$2" resolved="$2" link_target="" hops=0
  [[ -n "$candidate" ]] || return 1
  case "$candidate" in
    /*) ;;
    *)
      printf 'error: %s must be an absolute executable path\n' "$variable_name" >&2
      exit 2
      ;;
  esac
  if [[ ! -f "$candidate" || ! -x "$candidate" ]]; then
    printf 'error: %s does not name an executable file: %s\n' \
      "$variable_name" "$candidate" >&2
    exit 2
  fi
  while [[ -L "$resolved" ]]; do
    hops=$((hops + 1))
    if [[ "$hops" -gt 40 ]]; then
      printf 'error: %s has an excessive symbolic-link chain: %s\n' \
        "$variable_name" "$candidate" >&2
      exit 2
    fi
    link_target=$(readlink "$resolved") || {
      printf 'error: unable to resolve %s executable: %s\n' \
        "$variable_name" "$candidate" >&2
      exit 2
    }
    case "$link_target" in
      /*) resolved="$link_target" ;;
      *) resolved="${resolved%/*}/$link_target" ;;
    esac
  done
  resolved=$(cd "${resolved%/*}" 2>/dev/null &&
    printf '%s/%s\n' "$(pwd -P)" "${resolved##*/}") || {
    printf 'error: unable to canonicalize %s executable: %s\n' \
      "$variable_name" "$candidate" >&2
    exit 2
  }
  if [[ -n "$PROJECT_ROOT_REAL" ]]; then
    case "$candidate|$resolved" in
      "$PROJECT_ROOT_REAL"|"$PROJECT_ROOT_REAL"/*|\
      *'|'"$PROJECT_ROOT_REAL"|*'|'"$PROJECT_ROOT_REAL"/*)
        printf 'error: refusing %s executable inside the target project root: %s\n' \
          "$variable_name" "$candidate" >&2
        exit 2
        ;;
    esac
  fi
  # Execute the canonical file that was validated, not the lexical symlink.
  # Otherwise a same-user retarget between validation and execution can switch
  # the selected tool without another trust-boundary check.
  printf '%s\n' "$resolved"
}

bind_deterministic_tool() {
  local variable_name="$1" explicit_value="$2"
  shift 2
  local candidate=""
  if [[ -n "$explicit_value" ]]; then
    validate_explicit_tool "$variable_name" "$explicit_value"
    return
  fi
  for candidate in "$@"; do
    if [[ -f "$candidate" && -x "$candidate" ]]; then
      validate_explicit_tool "$variable_name" "$candidate"
      return
    fi
  done
  return 1
}

bind_optional_tool() {
  local variable_name="$1" explicit_value="$2"
  shift 2
  if [[ -n "$explicit_value" ]]; then
    validate_explicit_tool "$variable_name" "$explicit_value"
    return
  fi
  bind_deterministic_tool "$variable_name" "" "$@" || true
}

[[ -n "${E2E_SMELL_RG_BIN:-}" ]] &&
  validate_explicit_tool E2E_SMELL_RG_BIN "$E2E_SMELL_RG_BIN" >/dev/null
[[ -n "${E2E_SMELL_NODE_BIN:-}" ]] &&
  validate_explicit_tool E2E_SMELL_NODE_BIN "$E2E_SMELL_NODE_BIN" >/dev/null
[[ -n "${E2E_SMELL_NPX_BIN:-}" ]] &&
  validate_explicit_tool E2E_SMELL_NPX_BIN "$E2E_SMELL_NPX_BIN" >/dev/null
[[ -n "${E2E_SMELL_AST_GREP_BIN:-}" ]] &&
  validate_explicit_tool E2E_SMELL_AST_GREP_BIN "$E2E_SMELL_AST_GREP_BIN" >/dev/null

RG_BIN=$(bind_deterministic_tool E2E_SMELL_RG_BIN "${E2E_SMELL_RG_BIN:-}" \
  /opt/homebrew/bin/rg /usr/local/bin/rg /usr/bin/rg /bin/rg) || {
  printf 'error: rg is required; install it in /opt/homebrew/bin, /usr/local/bin, or /usr/bin, or set E2E_SMELL_RG_BIN to an explicit absolute path\n' >&2
  exit 2
}

NODE_BIN=$(bind_optional_tool E2E_SMELL_NODE_BIN "${E2E_SMELL_NODE_BIN:-}" \
  /opt/homebrew/bin/node /usr/local/bin/node /usr/bin/node /bin/node)
NPX_BIN=$(bind_optional_tool E2E_SMELL_NPX_BIN "${E2E_SMELL_NPX_BIN:-}" \
  /opt/homebrew/bin/npx /usr/local/bin/npx /usr/bin/npx /bin/npx)
PYTHON3_BIN=$(bind_deterministic_tool E2E_SMELL_PYTHON_BIN \
  "${E2E_SMELL_PYTHON_BIN:-}" \
  /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3 /bin/python3) || {
  printf 'error: Python 3 is required; install it in /opt/homebrew/bin, /usr/local/bin, or /usr/bin, or set E2E_SMELL_PYTHON_BIN to an explicit absolute path\n' >&2
  exit 2
}
_python3_probe=$("$PYTHON3_BIN" -I -B -c \
  'import sys; print("e2e-reviewer-python3") if sys.version_info.major == 3 else sys.exit(1)' \
  </dev/null 2>/dev/null)
if [[ "$_python3_probe" != "e2e-reviewer-python3" ]]; then
  printf 'error: E2E_SMELL_PYTHON_BIN must execute a working Python 3 interpreter\n' >&2
  exit 2
fi
FIND_BIN=$(bind_deterministic_tool E2E_SMELL_FIND_BIN "" \
  /usr/bin/find /bin/find) || {
  printf 'error: a trusted find executable is required for scanner tree validation\n' >&2
  exit 2
}

# The bundled scanner is the load-bearing path. Never download project tooling by
# default; callers may explicitly opt into the legacy download path by setting either
# variable to 0. Locally installed tools remain optional precision tiers.
E2E_SMELL_NO_ESLINT_DOWNLOAD="${E2E_SMELL_NO_ESLINT_DOWNLOAD:-1}"
E2E_SMELL_NO_AST_GREP_DOWNLOAD="${E2E_SMELL_NO_AST_GREP_DOWNLOAD:-1}"
E2E_SMELL_DISABLE_AST_GREP="${E2E_SMELL_DISABLE_AST_GREP:-0}"
E2E_SMELL_IGNORE_HOST_AST_GREP="${E2E_SMELL_IGNORE_HOST_AST_GREP:-0}"
export E2E_SMELL_NO_ESLINT_DOWNLOAD E2E_SMELL_NO_AST_GREP_DOWNLOAD E2E_SMELL_DISABLE_AST_GREP
export E2E_SMELL_IGNORE_HOST_AST_GREP
E2E_SMELL_ALLOW_PROJECT_ESLINT="${E2E_SMELL_ALLOW_PROJECT_ESLINT:-0}"
E2E_SMELL_ESLINT_TIMEOUT_SECS="${E2E_SMELL_ESLINT_TIMEOUT_SECS:-300}"
E2E_SMELL_MAX_RULE_HITS="${E2E_SMELL_MAX_RULE_HITS:-1000}"
E2E_SMELL_MAX_RULE_HITS_HARD=10000
E2E_SMELL_MAX_RULE_BYTES="${E2E_SMELL_MAX_RULE_BYTES:-1048576}"
E2E_SMELL_MAX_RULE_BYTES_HARD=16777216
validate_boolean_flag() {
  case "$2" in
    0|1) ;;
    *)
      printf 'error: %s must be exactly 0 or 1\n' "$1" >&2
      exit 2
      ;;
  esac
}
validate_boolean_flag E2E_SMELL_NO_ESLINT_DOWNLOAD "$E2E_SMELL_NO_ESLINT_DOWNLOAD"
validate_boolean_flag E2E_SMELL_NO_AST_GREP_DOWNLOAD "$E2E_SMELL_NO_AST_GREP_DOWNLOAD"
validate_boolean_flag E2E_SMELL_DISABLE_AST_GREP "$E2E_SMELL_DISABLE_AST_GREP"
validate_boolean_flag E2E_SMELL_IGNORE_HOST_AST_GREP "$E2E_SMELL_IGNORE_HOST_AST_GREP"
validate_boolean_flag E2E_SMELL_ALLOW_PROJECT_ESLINT "$E2E_SMELL_ALLOW_PROJECT_ESLINT"
case "$E2E_SMELL_ESLINT_TIMEOUT_SECS" in
  ''|*[!0-9]*|0)
    printf 'error: E2E_SMELL_ESLINT_TIMEOUT_SECS must be a positive integer\n' >&2
    exit 2
    ;;
esac
if [[ "$E2E_SMELL_ESLINT_TIMEOUT_SECS" -gt 3600 ]]; then
  printf 'error: E2E_SMELL_ESLINT_TIMEOUT_SECS must not exceed 3600\n' >&2
  exit 2
fi
case "$E2E_SMELL_MAX_RULE_HITS" in
  ''|*[!0-9]*|0)
    printf 'error: E2E_SMELL_MAX_RULE_HITS must be an integer from 1 through %s\n' \
      "$E2E_SMELL_MAX_RULE_HITS_HARD" >&2
    exit 2
    ;;
esac
if [[ "$E2E_SMELL_MAX_RULE_HITS" -gt "$E2E_SMELL_MAX_RULE_HITS_HARD" ]]; then
  printf 'error: E2E_SMELL_MAX_RULE_HITS must not exceed %s\n' \
    "$E2E_SMELL_MAX_RULE_HITS_HARD" >&2
  exit 2
fi
case "$E2E_SMELL_MAX_RULE_BYTES" in
  ''|*[!0-9]*|0)
    printf 'error: E2E_SMELL_MAX_RULE_BYTES must be an integer from 1 through %s\n' \
      "$E2E_SMELL_MAX_RULE_BYTES_HARD" >&2
    exit 2
    ;;
esac
if [[ "$E2E_SMELL_MAX_RULE_BYTES" -gt "$E2E_SMELL_MAX_RULE_BYTES_HARD" ]]; then
  printf 'error: E2E_SMELL_MAX_RULE_BYTES must not exceed %s\n' \
    "$E2E_SMELL_MAX_RULE_BYTES_HARD" >&2
  exit 2
fi

TRUSTED_TEMP_PARENT=""
for _trusted_temp_parent_candidate in /var/tmp /private/tmp /tmp; do
  if [[ -d "$_trusted_temp_parent_candidate" &&
        -w "$_trusted_temp_parent_candidate" ]]; then
    _trusted_temp_parent_real=$(cd "$_trusted_temp_parent_candidate" 2>/dev/null &&
      pwd -P) || _trusted_temp_parent_real=""
    [[ -n "$_trusted_temp_parent_real" ]] || continue
    "$PYTHON3_BIN" -I -B -c '
import os
import stat
import sys

path = sys.argv[1]
info = os.lstat(path)
if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
    raise SystemExit(1)
if info.st_uid not in (0, os.geteuid()):
    raise SystemExit(1)
shared_writable = bool(info.st_mode & (stat.S_IWGRP | stat.S_IWOTH))
if shared_writable and not bool(info.st_mode & stat.S_ISVTX):
    raise SystemExit(1)
' "$_trusted_temp_parent_real" </dev/null >/dev/null 2>&1 || continue
    if [[ -n "$PROJECT_ROOT_REAL" ]]; then
      case "$_trusted_temp_parent_real" in
        "$PROJECT_ROOT_REAL"|"$PROJECT_ROOT_REAL"/*) continue ;;
      esac
    fi
    TRUSTED_TEMP_PARENT="$_trusted_temp_parent_real"
    break
  fi
done
if [[ -z "$TRUSTED_TEMP_PARENT" ]]; then
  printf 'error: unable to locate a trusted writable system temporary directory outside the target project root\n' >&2
  exit 2
fi
SCANNER_TEMP_ROOT=$(mktemp -d "$TRUSTED_TEMP_PARENT/e2e-reviewer.XXXXXXXX") || {
  printf 'error: unable to allocate private scanner temporary storage\n' >&2
  exit 2
}
chmod 700 "$SCANNER_TEMP_ROOT" || {
  printf 'error: unable to secure private scanner temporary storage\n' >&2
  exit 2
}
_scanner_temp_root_real=$(cd "$SCANNER_TEMP_ROOT" 2>/dev/null && pwd -P) || {
  printf 'error: unable to validate private scanner temporary storage\n' >&2
  exit 2
}
if [[ "$_scanner_temp_root_real" != "$SCANNER_TEMP_ROOT" ||
      "$SCANNER_TEMP_ROOT" == "$TRUSTED_TEMP_PARENT" ]]; then
  printf 'error: private scanner temporary storage failed validation\n' >&2
  exit 2
fi

cleanup_scanner_temp_root() {
  case "${SCANNER_TEMP_ROOT:-}" in
    "$TRUSTED_TEMP_PARENT"/e2e-reviewer.*)
      [[ -d "$SCANNER_TEMP_ROOT" && ! -L "$SCANNER_TEMP_ROOT" ]] &&
        rm -rf -- "$SCANNER_TEMP_ROOT"
      ;;
  esac
}
trap cleanup_scanner_temp_root EXIT

allocate_temp() {
  local variable_name="$1" allocated_path="" template=""
  shift
  template="$SCANNER_TEMP_ROOT/item.XXXXXXXX"
  allocated_path=$(mktemp "$@" "$template")
  if [[ "$?" -ne 0 || -z "$allocated_path" ]]; then
    printf 'error: unable to allocate scanner temporary storage via mktemp\n' >&2
    exit 2
  fi
  case "$allocated_path" in
    "$SCANNER_TEMP_ROOT"/item.*) ;;
    *)
      printf 'error: scanner temporary storage escaped its private root\n' >&2
      exit 2
      ;;
  esac
  printf -v "$variable_name" '%s' "$allocated_path"
}

# Stream external-tool output through byte and line limiters before any output
# can be materialized in a shell variable. `head` bounds even one hostile
# unterminated line; awk then stops after limit+1 records. The producer/head may
# receive SIGPIPE (141) only after a confirmed limiter trip. Any other producer
# failure remains an infrastructure error owned by the caller.
capture_bounded_command() {
  # $4 is the stderr sink. Empty keeps the historical 2>&1 merge for callers that read the
  # combined text as human diagnostics; a path keeps stderr out of a strictly parsed stream.
  # Passed positionally rather than through the environment: a `VAR=x func` prefix persists
  # after the call under an inherited POSIXLY_CORRECT, which would silently divert a later
  # caller's stderr.
  local output_file="$1" error_file="$2" marker_file="$3" stderr_file="$4"
  shift 4
  local byte_window=$((E2E_SMELL_MAX_RULE_BYTES + 1))
  local -a _capture_status=()
  : > "$output_file"
  : > "$error_file"
  : > "$marker_file"
  # Callers that parse the capture as a strict machine format pass a stderr sink, so the
  # tool's diagnostics cannot land mid-stream. ast-grep >= 0.40 prints "Error: N error(s)
  # found in code." to stderr on a findings run; merged in, that became a non-JSON record and
  # collapsed Tier 2 into INCOMPLETE on any host carrying such a build. Callers that read the
  # merged text for human diagnostics (the ESLint tier) leave it unset and keep 2>&1.
  if [[ -n "$stderr_file" ]]; then
    : > "$stderr_file"
    "$@" 2>"$stderr_file" |
      head -c "$byte_window" |
      awk -v max_lines="$E2E_SMELL_MAX_RULE_HITS" -v marker="$marker_file" '
        NR > max_lines {
          print "lines" > marker
          exit 42
        }
        { print }
      ' > "$output_file"
    _capture_status=("${PIPESTATUS[@]}")
  else
  "$@" 2>&1 |
    head -c "$byte_window" |
    awk -v max_lines="$E2E_SMELL_MAX_RULE_HITS" -v marker="$marker_file" '
      NR > max_lines {
        print "lines" > marker
        exit 42
      }
      { print }
    ' > "$output_file"
  _capture_status=("${PIPESTATUS[@]}")
  fi
  BOUNDED_COMMAND_RC="${_capture_status[0]:-2}"
  BOUNDED_HEAD_RC="${_capture_status[1]:-2}"
  BOUNDED_FILTER_RC="${_capture_status[2]:-2}"
  printf '%s %s %s\n' \
    "$BOUNDED_COMMAND_RC" "$BOUNDED_HEAD_RC" "$BOUNDED_FILTER_RC" > "$error_file"
  BOUNDED_LIMIT_KIND=""
  if [[ -s "$marker_file" ]]; then
    BOUNDED_LIMIT_KIND="hits"
  elif [[ "$(wc -c < "$output_file" | tr -d '[:space:]')" -gt "$E2E_SMELL_MAX_RULE_BYTES" ]]; then
    BOUNDED_LIMIT_KIND="bytes"
    printf '%s\n' bytes > "$marker_file"
  fi
}

sanitize_evidence() {
  # Preserve tabs/newlines for readable file:line evidence, but neutralize every
  # other C0 control plus DEL so source text cannot move the cursor, rewrite
  # prior output, or emit terminal escape sequences.
  if [[ -x /usr/bin/perl ]]; then
    LC_ALL=C LC_CTYPE=C LANG=C /usr/bin/perl -CSD -pe \
      's/[\x{0080}-\x{009F}\x{202A}-\x{202E}\x{2066}-\x{2069}]/?/g' |
      LC_ALL=C tr '\000-\010\013\014\016-\037\177' '?'
  else
    LC_ALL=C tr '\000-\010\013\014\016-\037\177' '?'
  fi
}

redact_credential_evidence() {
  # Credential candidates keep their source location while withholding the
  # entire source payload. Partial quote substitution is unsafe for template
  # expressions, concatenation, and multiline helper calls.
  awk -F: '
    NF >= 3 {
      print $1 ":" $2 ":[REDACTED credential candidate]"
    }
  '
}

# Resolve $0 through symlinks to locate the scanner's own sibling files.
# `cd "$(dirname "$0")" && pwd` reports a symlink's own directory, and bash's
# logical `cd` makes any `..` walk from there worse, so `pwd -P` afterwards
# cannot recover the real location. Reuse `SCANNER_DIR_REAL` for every
# scanner-relative path. This locates files only — it must never decide what
# gets scanned, or the answer would depend on how the scanner was installed.
SCANNER_DIR_REAL=""
_scanner_self="$0"
_scanner_link_hops=0
while [[ -n "$_scanner_self" && -L "$_scanner_self" ]]; do
  _scanner_link_hops=$((_scanner_link_hops + 1))
  if (( _scanner_link_hops > 40 )); then
    _scanner_self=""
    break
  fi
  if ! _scanner_link_target=$(readlink "$_scanner_self" 2>/dev/null); then
    _scanner_self=""
    break
  fi
  _scanner_link_parent=${_scanner_self%/*}
  [[ "$_scanner_link_parent" == "$_scanner_self" ]] && _scanner_link_parent="."
  case "$_scanner_link_target" in
    /*) _scanner_self="$_scanner_link_target" ;;
    *) _scanner_self="$_scanner_link_parent/$_scanner_link_target" ;;
  esac
done
if [[ -n "$_scanner_self" ]]; then
  _scanner_dir=${_scanner_self%/*}
  [[ "$_scanner_dir" == "$_scanner_self" ]] && _scanner_dir="."
  SCANNER_DIR_REAL=$(cd -P "$_scanner_dir" 2>/dev/null && pwd -P) || SCANNER_DIR_REAL=""
fi
unset _scanner_self _scanner_link_hops _scanner_link_target
unset _scanner_link_parent _scanner_dir

# Exclude intentional fixtures only when the SCANNED PROJECT is an e2e-skills
# checkout. Fingerprint the scanned project, never the scanner's own location:
# `reinstall-skills.sh` installs real copies and users symlink the skill, so a
# location-derived answer makes identical input produce different findings
# depending on how the tool was installed. A third-party project that merely
# has an `evals/files/` directory does not match this fingerprint and stays in
# scope, which is the point — silently skipping a target's real tests is the
# failure this scanner exists to prevent.
SELF_REPO_SCAN=0
_self_boundary_cursor="$SCAN_ROOT_REAL"
if [[ -n "$PROJECT_ROOT_REAL" &&
      -f "$PROJECT_ROOT_REAL/AGENTS.md" &&
      -f "$PROJECT_ROOT_REAL/skills/e2e-reviewer/SKILL.md" &&
      -f "$PROJECT_ROOT_REAL/scripts/ci/test-reviewer-scanner.py" ]]; then
  while [[ "$_self_boundary_cursor" == "$PROJECT_ROOT_REAL"/* ]]; do
    # Nested package/config roots are separate targets even without Git metadata.
    if [[ -e "$_self_boundary_cursor/.git" ]] ||
       has_project_marker "$_self_boundary_cursor"; then
      break
    fi
    _self_boundary_cursor=${_self_boundary_cursor%/*}
  done
  [[ "$_self_boundary_cursor" == "$PROJECT_ROOT_REAL" ]] && SELF_REPO_SCAN=1
fi
unset _self_boundary_cursor

# bash 3.2 (macOS) plus `set -u` treats an empty array as unset, so the five
# call sites below expand these with the ${arr[@]+"${arr[@]}"} presence guard.
# Removing that guard makes every scan abort when the arrays are empty.
EVAL_FIXTURE_EXCLUDES=()
EVAL_FIXTURE_AST_GREP_EXCLUDES=()
if [[ "$SELF_REPO_SCAN" == "1" ]]; then
  EVAL_FIXTURE_EXCLUDES=(
    --glob '!**/evals/files/**'
    --glob '!**/scripts/ci/fixtures/**'
  )
  EVAL_FIXTURE_AST_GREP_EXCLUDES=(
    --globs '!**/evals/files/**'
    --globs '!**/scripts/ci/fixtures/**'
  )
fi
case "$ROOT/" in
  *"/evals/files/"*|*"/scripts/ci/fixtures/"*)
    EVAL_FIXTURE_EXCLUDES=()
    EVAL_FIXTURE_AST_GREP_EXCLUDES=()
    ;;
esac

# Remove JavaScript/TypeScript line and block comments before checking a module
# reference. Package names mentioned only in contributor comments are not
# executable imports. This shares source_executable_code's lexer on purpose: a
# second copy of the string rules could disagree with it about the evaluated
# value of an escaped specifier, and a disagreement is a silent scope drop.
source_has_playwright_module_reference() {
  source_executable_code "$1" @playwright/test |
    tr '\n' ' ' |
    scanner_rg -q "(import|export)[^;]*from[[:space:]]*['\"\`]@playwright/test['\"\`]|require[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)|import[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)"
}

# Emit executable JavaScript/TypeScript while removing comments and quoted
# values. An optional package name is the only string value retained, allowing
# import/require provenance checks without letting documentation strings create
# framework scope.
source_executable_code() {
  local f="$1" retained_string="${2:-}"
  awk -v retained="$retained_string" '
    # A JavaScript string literal is not its own source text: `\u0040pkg` and
    # `@pkg` are the same module specifier. Decode escapes so an obfuscated
    # import cannot make a real framework reference invisible (or an unrelated
    # package look like one). Sequences whose value cannot occur inside a
    # package specifier (control characters, non-ASCII code points) decode to a
    # sentinel word so they compare unequal to every package name instead of
    # accidentally matching one.
    function js_hex_value(digits,   k, value, digit) {
      value = 0
      for (k = 1; k <= length(digits); k++) {
        digit = index("0123456789abcdef", tolower(substr(digits, k, 1))) - 1
        if (digit < 0) return -1
        value = value * 16 + digit
      }
      return value
    }
    function js_code_point_text(code) {
      if (code >= 32 && code <= 126) return sprintf("%c", code)
      return "__E2E_UNREPRESENTABLE__"
    }
    # Decodes the escape sequence starting at s[i] (which is a backslash) and
    # records how many source characters it spans in js_escape_span so the
    # caller can advance its cursor past the whole sequence.
    function js_escape_text(s, i,   next_char, digits, brace_end) {
      next_char = substr(s, i + 1, 1)
      if (next_char == "") {
        # Trailing backslash: a line continuation contributes no characters.
        js_escape_span = 1
        return ""
      }
      if (next_char == "u") {
        if (substr(s, i + 2, 1) == "{") {
          brace_end = index(substr(s, i + 3), "}")
          if (brace_end > 0) {
            digits = substr(s, i + 3, brace_end - 1)
            if (digits ~ /^[0-9A-Fa-f]+$/) {
              js_escape_span = brace_end + 3
              return js_code_point_text(js_hex_value(digits))
            }
          }
        } else {
          digits = substr(s, i + 2, 4)
          if (digits ~ /^[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]$/) {
            js_escape_span = 6
            return js_code_point_text(js_hex_value(digits))
          }
        }
        js_escape_span = 2
        return "u"
      }
      if (next_char == "x") {
        digits = substr(s, i + 2, 2)
        if (digits ~ /^[0-9A-Fa-f][0-9A-Fa-f]$/) {
          js_escape_span = 4
          return js_code_point_text(js_hex_value(digits))
        }
        js_escape_span = 2
        return "x"
      }
      js_escape_span = 2
      if (next_char ~ /^[0-7]$/) return "__E2E_UNREPRESENTABLE__"
      if (index("ntrbfv", next_char) > 0) return "__E2E_UNREPRESENTABLE__"
      return next_char
    }
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_regex) {
          if (lex_escape) {
            lex_escape = 0
          } else if (c == "\\") {
            lex_escape = 1
          } else if (c == "[") {
            regex_class = 1
          } else if (c == "]") {
            regex_class = 0
          } else if (c == "/" && !regex_class) {
            lex_regex = 0
            out = out "__REGEX__"
            prev_sig = "/"
          }
          continue
        }
        if (lex_quote != "") {
          if (c == "\\") {
            lex_value = lex_value js_escape_text(s, i)
            i += js_escape_span - 1
          } else if (lex_quote == "`" && c == "$" && nchar == "{") {
            lex_quote = ""
            template_depth = 1
            lex_value = ""
            i++
          } else if (c == lex_quote) {
            if (retained != "" && lex_value == retained)
              out = out lex_quote lex_value lex_quote
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (template_depth > 0 && c == "{") {
          template_depth++
          out = out c
          continue
        }
        if (template_depth > 0 && c == "}") {
          template_depth--
          if (template_depth == 0) {
            lex_quote = "`"
            lex_value = ""
          } else {
            out = out c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        if (c == "/" && (prev_sig == "" ||
            prev_sig ~ /[=(:,!{\[;?&|]/ ||
            out ~ /(^|[^A-Za-z0-9_$])(return|throw|case|yield)[[:space:]]*$/ ||
            out ~ /=>[[:space:]]*$/ ||
            out ~ /(^|[^A-Za-z0-9_$])(if|while|for|with)[[:space:]]*\([^)]*\)[[:space:]]*$/)) {
          lex_regex = 1
          regex_class = 0
          continue
        }
        out = out c
        if (c !~ /[[:space:]]/) prev_sig = c
      }
      return out
    }
    { print executable_source($0) }
  ' "$f" 2>/dev/null
}

source_has_cypress_module_reference() {
  source_executable_code "$1" cypress |
    tr '\n' ' ' |
    scanner_rg -q "(import|export)[^;]*from[[:space:]]*['\"]cypress['\"]|require[[:space:]]*\\([[:space:]]*['\"]cypress['\"][[:space:]]*\\)|import[[:space:]]*\\([[:space:]]*['\"]cypress['\"][[:space:]]*\\)"
}

# Report whether executable code on standard input imports $1 at *runtime*.
# TypeScript type-only forms (`import type ... from`, `export type ... from`,
# a brace list whose specifiers are all `type`-prefixed, and `import()` in a
# type position) are erased before the file ever executes, so they say nothing
# about which runner owns the file and must not remove it from scope. Anything
# whose shape is not recognised counts as a runtime import, which keeps the
# existing exclusions at full strength.
code_imports_module_at_runtime() {
  awk -v package="$1" '
    function rtrim(s) { sub(/[[:space:]]+$/, "", s); return s }
    function ltrim(s) { sub(/^[[:space:]]+/, "", s); return s }
    function trim(s) { return ltrim(rtrim(s)) }
    function brace_has_value_specifier(inner,   n, parts, k, part) {
      n = split(inner, parts, ",")
      for (k = 1; k <= n; k++) {
        part = trim(parts[k])
        if (part == "") continue
        # `type X` / `type X as Y` are erased; a binding literally named `type`
        # (`{ type }`, `{ type as t }`) is a value and must still count.
        if (part ~ /^type[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*/ &&
            part !~ /^type[[:space:]]+as([^A-Za-z0-9_$]|$)/) continue
        return 1
      }
      return 0
    }
    function last_word_pos(head, word,   at, offset, found, before, after) {
      found = 0
      offset = 0
      while ((at = index(substr(head, offset + 1), word)) > 0) {
        offset = offset + at
        before = (offset == 1) ? "" : substr(head, offset - 1, 1)
        after = substr(head, offset + length(word), 1)
        if ((before == "" || before !~ /[A-Za-z0-9_$.]/) &&
            (after == "" || after !~ /[A-Za-z0-9_$]/)) found = offset
      }
      return found
    }
    function from_clause_is_runtime(head,   keyword_pos, export_pos, clause, open_brace, close_brace, inner) {
      head = rtrim(substr(head, 1, length(head) - 4))
      keyword_pos = last_word_pos(head, "import")
      export_pos = last_word_pos(head, "export")
      if (export_pos > keyword_pos) keyword_pos = export_pos
      if (keyword_pos == 0) return 1
      clause = ltrim(substr(head, keyword_pos + 6))
      if (clause ~ /^type[[:space:]]*[{]/) return 0
      if (clause ~ /^type[[:space:]]*[*]/) return 0
      if (clause ~ /^type[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*$/ &&
          clause !~ /^type[[:space:]]+as[[:space:]]*$/) return 0
      open_brace = index(clause, "{")
      if (open_brace > 0) {
        close_brace = index(clause, "}")
        if (close_brace > open_brace) {
          # A default or namespace binding outside the braces is a value.
          if (trim(substr(clause, 1, open_brace - 1)) != "") return 1
          inner = substr(clause, open_brace + 1, close_brace - open_brace - 1)
          return brace_has_value_specifier(inner)
        }
      }
      return 1
    }
    function dynamic_import_is_runtime(head) {
      head = rtrim(head)
      if (head ~ /:$/) return 0
      if (head ~ /[<|&]$/) return 0
      if (head ~ /(^|[^A-Za-z0-9_$])(extends|keyof|implements|readonly)$/) return 0
      if (head ~ /(^|[^A-Za-z0-9_$])type[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*(<[^=]*>[[:space:]]*)?=$/) return 0
      return 1
    }
    function is_runtime_import(head) {
      head = rtrim(head)
      if (head ~ /(^|[^A-Za-z0-9_$])from$/) return from_clause_is_runtime(head)
      if (head ~ /[(]$/) {
        head = rtrim(substr(head, 1, length(head) - 1))
        if (head ~ /(^|[^A-Za-z0-9_$])require$/) return 1
        if (head ~ /(^|[^A-Za-z0-9_$])import$/) {
          return dynamic_import_is_runtime(substr(head, 1, length(head) - 6))
        }
      }
      return 0
    }
    { buffer = buffer $0 " " }
    END {
      quotes = "\"" "\047" "`"
      for (q = 1; q <= 3; q++) {
        needle = substr(quotes, q, 1) package substr(quotes, q, 1)
        cursor = 1
        while ((at = index(substr(buffer, cursor), needle)) > 0) {
          pos = cursor + at - 1
          window_start = pos - 512
          if (window_start < 1) window_start = 1
          if (is_runtime_import(substr(buffer, window_start, pos - window_start))) exit 0
          cursor = pos + length(needle)
        }
      }
      exit 1
    }
  '
}

source_has_foreign_test_module_reference() {
  local f="$1" package
  for package in vitest jest @jest/globals node:test bun:test mocha @wdio/globals; do
    source_executable_code "$f" "$package" |
      code_imports_module_at_runtime "$package" &&
      return 0
  done
  return 1
}

source_imports_foreign_test_binding() {
  local f="$1" binding="$2" package source_name code
  local _foreign_import_binding _foreign_require_binding
  for package in vitest jest @jest/globals node:test bun:test mocha @wdio/globals; do
    code=$(source_executable_code "$f" "$package" | tr '\n' ' ')
    for source_name in test it describe context specify; do
      if [[ "$binding" == "$source_name" ]]; then
        _foreign_import_binding="$source_name([[:space:]]+as[[:space:]]+$binding)?"
        _foreign_require_binding="$source_name([[:space:]]*:[[:space:]]*$binding)?"
      else
        _foreign_import_binding="$source_name[[:space:]]+as[[:space:]]+$binding"
        _foreign_require_binding="$source_name[[:space:]]*:[[:space:]]*$binding"
      fi
      printf '%s\n' "$code" |
        scanner_rg -qP "(?:(?:import|export)[[:space:]]*\\{[^}]*\\b$_foreign_import_binding\\b[^}]*\\}[[:space:]]*from[[:space:]]*['\"\`]$package['\"\`]|(?:const|let|var)[[:space:]]*\\{[^}]*\\b$_foreign_require_binding\\b[^}]*\\}[[:space:]]*=[[:space:]]*(?:require|(?:await[[:space:]]+)?import)[[:space:]]*\\([[:space:]]*['\"\`]$package['\"\`][[:space:]]*\\))" &&
        return 0
    done
    printf '%s\n' "$code" |
      scanner_rg -qP "import[[:space:]]+$binding[[:space:]]+from[[:space:]]*['\"\`]$package['\"\`]" &&
      return 0
  done
  return 1
}

source_has_playwright_runtime_reference() {
  source_executable_code "$1" |
    scanner_rg -q "async[[:space:]]*\\([[:space:]]*\\{[[:space:]]*page\\b"
}

# `cy` chains are routinely reformatted so that the dot starts the next line,
# so the lexer output is joined before matching. A line-anchored search misses
# the whole chain and silently drops the file out of scope. Any `cy.*()` or
# `Cypress.*()` member call counts, not just the two originally spelled out.
source_has_cypress_runtime_reference() {
  source_executable_code "$1" |
    tr '\n' ' ' |
    scanner_rg -q '(^|[^A-Za-z0-9_])(cy|Cypress)[[:space:]]*[.][[:space:]]*([A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*[.][[:space:]]*)*[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*[(]'
}

# Emit relative module specifiers only from executable import/export/require
# syntax. Quoted comments and standalone strings remain inert.
source_relative_module_references() {
  awk '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_value = lex_value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_value = lex_value c
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__E2E_STR__" lex_value "__E2E_END__"
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    { print executable_source($0) }
  ' "$1" 2>/dev/null |
    tr '\n' ' ' |
    scanner_rg -o "(?:(?:import|export)[^;]*?from[[:space:]]*|require[[:space:]]*\\([[:space:]]*|import[[:space:]]*\\([[:space:]]*|import[[:space:]]+)__E2E_STR__\\.\\.?/.*?__E2E_END__" 2>/dev/null |
    sed -E 's/^.*__E2E_STR__(.*)__E2E_END__.*$/\1/'
}

resolve_relative_module_candidates() {
  local f="$1" import_path="$2" module_path module_base candidate candidate_dir candidate_real
  module_path="$(dirname "$f")/$import_path"
  module_base="$module_path"
  case "$module_path" in
    *.js|*.jsx|*.mjs|*.cjs) module_base="${module_path%.*}" ;;
  esac
  for candidate in \
    "$module_path" \
    "$module_base.ts" "$module_base.tsx" "$module_base.js" "$module_base.jsx" \
    "$module_base.mts" "$module_base.mjs" "$module_base.cts" "$module_base.cjs" \
    "$module_path/index.ts" "$module_path/index.tsx" \
    "$module_path/index.js" "$module_path/index.jsx" \
    "$module_path/index.mts" "$module_path/index.mjs" \
    "$module_path/index.cts" "$module_path/index.cjs"; do
    [[ -f "$candidate" && ! -L "$candidate" ]] || continue
    candidate_dir=$(cd "$(dirname "$candidate")" 2>/dev/null && pwd -P) || continue
    candidate_real="$candidate_dir/$(basename "$candidate")"
    case "$candidate_real" in
      "$PROJECT_ROOT_REAL"/*) printf '%s\n' "$candidate_real" ;;
    esac
  done
}

module_reaches_playwright_reference() {
  local f="$1" visited="$2" depth="$3" import_path candidate
  [[ "$depth" -le 32 ]] || return 1
  grep -qFx -e "$f" "$visited" 2>/dev/null && return 1
  printf '%s\n' "$f" >> "$visited"
  source_has_playwright_module_reference "$f" && return 0
  while IFS= read -r import_path; do
    while IFS= read -r candidate; do
      module_reaches_playwright_reference "$candidate" "$visited" "$((depth + 1))" &&
        return 0
    done < <(resolve_relative_module_candidates "$f" "$import_path")
  done < <(source_relative_module_references "$f")
  return 1
}

# Resolve generic relative fixture/support/barrel chains within the containing
# project while keeping reported findings limited to the requested scan root.
file_uses_playwright_fixture_module() {
  local f="$1" visited rc
  allocate_temp visited
  module_reaches_playwright_reference "$f" "$visited" 0
  rc=$?
  rm -f "$visited"
  return "$rc"
}

# An unresolved workspace/path-alias import cannot prove full E2E provenance,
# but importing a `test` API is enough to conservatively scan an unsuppressible
# focused-test call. Known unit-test frameworks remain out of scope.
source_has_unresolved_test_import() {
  awk '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_value = lex_value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_value = lex_value c
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__E2E_STR__" lex_value "__E2E_END__"
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    { print executable_source($0) }
  ' "$1" 2>/dev/null |
    tr '\n' ' ' |
    scanner_rg -o "(?:(?:import|export)[^;]*\\btest\\b[^;]*from[[:space:]]*|import[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]+from[[:space:]]*|(?:const|let|var)[[:space:]]*\\{[^}]*\\btest\\b[^}]*\\}[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*)__E2E_STR__.*?__E2E_END__" 2>/dev/null |
    scanner_rg -qv '__E2E_STR__(\.{1,2}/|@playwright/test|vitest|jest|@jest/globals|node:test|bun:test|@wdio/globals)'
}

source_imports_playwright_test_binding() {
  local f="$1" binding="$2" import_binding require_binding code
  if [[ "$binding" == "test" ]]; then
    import_binding='test([[:space:]]+as[[:space:]]+test)?'
    require_binding='test([[:space:]]*:[[:space:]]*test)?'
  else
    import_binding="test[[:space:]]+as[[:space:]]+$binding"
    require_binding="test[[:space:]]*:[[:space:]]*$binding"
  fi
  code=$(source_executable_code "$f" @playwright/test | tr '\n' ' ')
  printf '%s\n' "$code" |
    scanner_rg -qP "(?:(?:import|export)[[:space:]]*\\{[^}]*\\b$import_binding\\b[^}]*\\}[[:space:]]*from[[:space:]]*['\"\`]@playwright/test['\"\`]|(?:const|let|var)[[:space:]]*\\{[^}]*\\b$require_binding\\b[^}]*\\}[[:space:]]*=[[:space:]]*(?:require|(?:await[[:space:]]+)?import)[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)|(?:const|let|var)[[:space:]]+$binding[[:space:]]*=[[:space:]]*(?:require|(?:await[[:space:]]+)?import)[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)[[:space:]]*[.][[:space:]]*test\\b|(?:const|let|var)[[:space:]]+(?<pw_test_ns>[A-Za-z_$][A-Za-z0-9_$]*)[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)[[:space:]]*;[[:space:]]*(?:const|let|var)[[:space:]]+$binding[[:space:]]*=[[:space:]]*\\k<pw_test_ns>[[:space:]]*[.][[:space:]]*test\\b)" &&
    return 0
  awk '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_value = lex_value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_value = lex_value c
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__E2E_STR__" lex_value "__E2E_END__"
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    { print executable_source($0) }
  ' "$f" 2>/dev/null |
    tr '\n' ' ' |
    scanner_rg -qP "(?:import[[:space:]]*\\{[^}]*\\b$import_binding\\b[^}]*\\}[[:space:]]*from[[:space:]]*__E2E_STR__@playwright/test__E2E_END__|(?:const|let|var)[[:space:]]*\\{[^}]*\\b$require_binding\\b[^}]*\\}[[:space:]]*=[[:space:]]*(?:require|(?:await[[:space:]]+)?import)[[:space:]]*\\([[:space:]]*__E2E_STR__@playwright/test__E2E_END__)"
}

source_imports_playwright_namespace_binding() {
  local f="$1" binding="$2" code
  case "$binding" in
    *[!A-Za-z0-9_$]*|'') return 1 ;;
  esac
  code=$(source_executable_code "$f" @playwright/test | tr '\n' ' ')
  printf '%s\n' "$code" |
    scanner_rg -qP "(?:import[[:space:]]*\\*[[:space:]]+as[[:space:]]+$binding\\b[[:space:]]*from[[:space:]]*['\"\`]@playwright/test['\"\`]|import[[:space:]]+$binding\\b[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)|(?:const|let|var)[[:space:]]+$binding\\b[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\))" &&
    return 0
  awk '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_value = lex_value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_value = lex_value c
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__E2E_STR__" lex_value "__E2E_END__"
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    { print executable_source($0) }
  ' "$f" 2>/dev/null |
    tr '\n' ' ' |
    scanner_rg -qP "(?:import[[:space:]]*\\*[[:space:]]+as[[:space:]]+$binding\\b[[:space:]]*from[[:space:]]*__E2E_STR__@playwright/test__E2E_END__|import[[:space:]]+$binding\\b[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*__E2E_STR__@playwright/test__E2E_END__|(?:const|let|var)[[:space:]]+$binding\\b[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*__E2E_STR__@playwright/test__E2E_END__)"
}

source_imports_playwright_expect_binding() {
  local f="$1" binding="$2" import_binding require_binding code
  if [[ "$binding" == "expect" ]]; then
    import_binding='expect'
    require_binding='expect'
  else
    import_binding="expect[[:space:]]+as[[:space:]]+$binding"
    require_binding="expect[[:space:]]*:[[:space:]]*$binding"
  fi
  code=$(source_executable_code "$f" @playwright/test | tr '\n' ' ')
  printf '%s\n' "$code" |
    scanner_rg -qP "(?:(?:import|export)[[:space:]]*\\{[^}]*\\b$import_binding\\b[^}]*\\}[[:space:]]*from[[:space:]]*['\"\`]@playwright/test['\"\`]|(?:const|let|var)[[:space:]]*\\{[^}]*\\b$require_binding\\b[^}]*\\}[[:space:]]*=[[:space:]]*(?:require|(?:await[[:space:]]+)?import)[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)|(?:const|let|var)[[:space:]]+$binding[[:space:]]*=[[:space:]]*(?:require|(?:await[[:space:]]+)?import)[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)[[:space:]]*[.][[:space:]]*expect\\b|(?:const|let|var)[[:space:]]+(?<pw_expect_ns>[A-Za-z_$][A-Za-z0-9_$]*)[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)[[:space:]]*;[[:space:]]*(?:const|let|var)[[:space:]]+$binding[[:space:]]*=[[:space:]]*\\k<pw_expect_ns>[[:space:]]*[.][[:space:]]*expect\\b)" &&
    return 0
  printf '%s\n' "$code" |
    scanner_rg -qP "(?:const|let|var)[[:space:]]+(?<pw_expect_dynamic_ns>[A-Za-z_$][A-Za-z0-9_$]*)[[:space:]]*=[[:space:]]*(?:require|(?:await[[:space:]]+)?import)[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)[[:space:]]*;?[[:space:]]*(?:export[[:space:]]+)?(?:const|let|var)[[:space:]]*\\{[^}]*\\b$require_binding\\b[^}]*\\}[[:space:]]*=[[:space:]]*\\k<pw_expect_dynamic_ns>\\b" &&
    return 0
  printf '%s\n' "$code" |
    scanner_rg -qP "import[[:space:]]*\\*[[:space:]]+as[[:space:]]+(?<pw_expect_import_ns>[A-Za-z_$][A-Za-z0-9_$]*)[[:space:]]*from[[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*;?[[:space:]]*(?:export[[:space:]]+)?(?:const|let|var)[[:space:]]*\\{[^}]*\\b$require_binding\\b[^}]*\\}[[:space:]]*=[[:space:]]*\\k<pw_expect_import_ns>\\b" &&
    return 0
  awk '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_value = lex_value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_value = lex_value c
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__E2E_STR__" lex_value "__E2E_END__"
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    { print executable_source($0) }
  ' "$f" 2>/dev/null |
    tr '\n' ' ' |
    scanner_rg -qP "(?:(?:import|export)[[:space:]]*\\{[^}]*\\b$import_binding\\b[^}]*\\}[[:space:]]*from[[:space:]]*__E2E_STR__@playwright/test__E2E_END__|(?:const|let|var)[[:space:]]*\\{[^}]*\\b$require_binding\\b[^}]*\\}[[:space:]]*=[[:space:]]*(?:require|(?:await[[:space:]]+)?import)[[:space:]]*\\([[:space:]]*__E2E_STR__@playwright/test__E2E_END__)"
}

source_imports_relative_binding() {
  local f="$1" binding="$2"
  awk '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_value = lex_value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_value = lex_value c
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__E2E_STR__" lex_value "__E2E_END__"
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    { print executable_source($0) }
  ' "$f" 2>/dev/null |
    tr '\n' ' ' |
    scanner_rg -qP "(?:(?:import[[:space:]]*\\{[^}]*\\b(?:[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]+as[[:space:]]+)?$binding\\b[^}]*\\}|import[[:space:]]+$binding\\b)[[:space:]]*from[[:space:]]*__E2E_STR__\\.\\.?/|(?:const|let|var)[[:space:]]*\\{[^}]*\\b(?:[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*:[[:space:]]*)?$binding\\b[^}]*\\}[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*__E2E_STR__\\.\\.?/)"
}

source_relative_module_references_for_binding() {
  local f="$1" binding="$2"
  awk '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_value = lex_value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_value = lex_value c
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__E2E_STR__" lex_value "__E2E_END__"
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    { print executable_source($0) }
  ' "$f" 2>/dev/null |
    tr '\n' ' ' |
    scanner_rg -oP "(?:(?:import[[:space:]]*(?:\\{[^}]*\\b(?:[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]+as[[:space:]]+)?$binding\\b[^}]*\\}|$binding\\b)[[:space:]]*from[[:space:]]*)|(?:(?:const|let|var)[[:space:]]*\\{[^}]*\\b(?:[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*:[[:space:]]*)?$binding\\b[^}]*\\}[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*))__E2E_STR__\\K\\.\\.?/.*?(?=__E2E_END__)" 2>/dev/null
}

source_relative_module_references_for_named_binding() {
  local f="$1" binding="$2" source_name="$3" import_member require_member
  if [[ "$binding" == "$source_name" ]]; then
    import_member="$source_name(?:[[:space:]]+as[[:space:]]+$binding)?"
    require_member="$source_name(?:[[:space:]]*:[[:space:]]*$binding)?"
  else
    import_member="$source_name[[:space:]]+as[[:space:]]+$binding"
    require_member="$source_name[[:space:]]*:[[:space:]]*$binding"
  fi
  awk '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_value = lex_value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_value = lex_value c
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__E2E_STR__" lex_value "__E2E_END__"
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    { print executable_source($0) }
  ' "$f" 2>/dev/null |
    tr '\n' ' ' |
    scanner_rg -oP "(?:(?:import[[:space:]]*\\{[^}]*\\b$import_member\\b[^}]*\\}[[:space:]]*from[[:space:]]*)|(?:(?:const|let|var)[[:space:]]*\\{[^}]*\\b$require_member\\b[^}]*\\}[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*))__E2E_STR__\\K\\.\\.?/.*?(?=__E2E_END__)" 2>/dev/null
}

source_relative_binding_lineage_edges() {
  local f="$1" binding="$2" mode="${3:-binding}"
  case "$binding" in
    *[!A-Za-z0-9_$]*|'') return 1 ;;
  esac
  awk -v target="$binding" -v mode="$mode" '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_value = lex_value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_value = lex_value c
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__E2E_STR__" lex_value "__E2E_END__"
            lex_quote = ""
            lex_value = ""
          } else {
            lex_value = lex_value c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          lex_value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    function trim(s) {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", s)
      return s
    }
    function emit_statement(statement,    path, compact, body, start, stop, count, members, member, pair, source, local, i) {
      if (statement !~ /__E2E_STR__[.][.]?\//) return
      path = statement
      sub(/^.*__E2E_STR__/, "", path)
      sub(/__E2E_END__.*/, "", path)
      compact = statement
      gsub(/[[:space:]]+/, "", compact)
      if (mode == "namespace" || mode == "namespace-expect") {
        if (compact ~ ("import[*]as" target "from__E2E_STR__") ||
            compact ~ ("import" target "=require[(]__E2E_STR__") ||
            compact ~ ("(const|let|var)" target "=require[(]__E2E_STR__"))
          print (mode == "namespace-expect" ? "expect" : "test") "\t" path
        return
      }
      if (compact ~ ("import" target "from__E2E_STR__")) {
        print "default\t" path
        return
      }
      if (compact ~ /^export[*]from__E2E_STR__/ ||
          compact ~ /^module[.]exports=require[(]__E2E_STR__/) {
        print target "\t" path
        return
      }
      start = index(statement, "{")
      stop = index(statement, "}")
      if (!start || stop <= start) return
      body = substr(statement, start + 1, stop - start - 1)
      count = split(body, members, ",")
      for (i = 1; i <= count; i++) {
        member = trim(members[i])
        if (member ~ /^[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]+as[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*$/) {
          split(member, pair, /[[:space:]]+as[[:space:]]+/)
          source = trim(pair[1])
          local = trim(pair[2])
        } else if (member ~ /^[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*:[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*$/) {
          split(member, pair, /[[:space:]]*:[[:space:]]*/)
          source = trim(pair[1])
          local = trim(pair[2])
        } else if (member ~ /^[A-Za-z_$][A-Za-z0-9_$]*$/) {
          source = member
          local = member
        } else {
          continue
        }
        if (local == target) print source "\t" path
      }
    }
    function starts_declaration(s,    t) {
      t = trim(s)
      return t ~ /^(import|export|module[[:space:]]*[.]|const[[:space:]]|let[[:space:]]|var[[:space:]])/
    }
    function consume_fragment(fragment, boundary,    clean) {
      clean = trim(fragment)
      if (clean == "") {
        if (boundary) pending = ""
        return
      }
      # A declaration beginning on a new physical line terminates a
      # semicolonless predecessor. Multiline continuations do not begin with a
      # declaration keyword and stay attached until the module string arrives.
      if (line_start && pending != "" && starts_declaration(clean))
        pending = ""
      pending = pending " " clean
      if (pending ~ /__E2E_END__/) {
        emit_statement(pending)
        pending = ""
      } else if (boundary) {
        pending = ""
      }
      line_start = 0
    }
    {
      source = executable_source($0)
      fragment_count = split(source, fragments, ";")
      line_start = 1
      for (fragment_index = 1; fragment_index <= fragment_count; fragment_index++)
        consume_fragment(fragments[fragment_index], fragment_index < fragment_count)
      if (pending ~ /__E2E_END__/) {
        emit_statement(pending)
        pending = ""
      }
    }
  ' "$f" 2>/dev/null
}

binding_reaches_playwright_expect() {
  local f="$1" binding="$2" visited="$3" depth="$4"
  local key source_binding import_path candidate
  [[ "$depth" -le 32 ]] || return 1
  key="$f|$binding"
  grep -qFx -e "$key" "$visited" 2>/dev/null && return 1
  printf '%s\n' "$key" >> "$visited"
  source_imports_playwright_expect_binding "$f" "$binding" && return 0
  if [[ "$binding" == "expect" ]]; then
    source_executable_code "$f" @playwright/test |
      tr '\n' ' ' |
      scanner_rg -qP "(?:module[[:space:]]*[.][[:space:]]*exports[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)|export[[:space:]]*\\*[[:space:]]*from[[:space:]]*['\"\`]@playwright/test['\"\`])" &&
      return 0
  fi
  while IFS=$'\t' read -r source_binding import_path; do
    [[ -n "$source_binding" && -n "$import_path" ]] || continue
    while IFS= read -r candidate; do
      binding_reaches_playwright_expect \
        "$candidate" "$source_binding" "$visited" "$((depth + 1))" &&
        return 0
    done < <(resolve_relative_module_candidates "$f" "$import_path")
  done < <(source_relative_binding_lineage_edges "$f" "$binding")
  return 1
}

binding_reaches_playwright_test() {
  local f="$1" binding="$2" visited="$3" depth="$4"
  local key source_binding import_path candidate
  [[ "$depth" -le 32 ]] || return 1
  key="$f|$binding"
  grep -qFx -e "$key" "$visited" 2>/dev/null && return 1
  printf '%s\n' "$key" >> "$visited"
  source_imports_playwright_test_binding "$f" "$binding" && return 0
  if [[ "$binding" == "test" ]]; then
    source_executable_code "$f" @playwright/test |
      tr '\n' ' ' |
      scanner_rg -qP "(?:module[[:space:]]*[.][[:space:]]*exports[[:space:]]*=[[:space:]]*require[[:space:]]*\\([[:space:]]*['\"\`]@playwright/test['\"\`][[:space:]]*\\)|export[[:space:]]*\\*[[:space:]]*from[[:space:]]*['\"\`]@playwright/test['\"\`])" &&
      return 0
  fi
  while IFS=$'\t' read -r source_binding import_path; do
    [[ -n "$source_binding" && -n "$import_path" ]] || continue
    while IFS= read -r candidate; do
      binding_reaches_playwright_test \
        "$candidate" "$source_binding" "$visited" "$((depth + 1))" &&
        return 0
    done < <(resolve_relative_module_candidates "$f" "$import_path")
  done < <(source_relative_binding_lineage_edges "$f" "$binding")
  return 1
}

relative_binding_reaches_playwright() {
  local f="$1" binding="$2" visited rc
  allocate_temp visited
  binding_reaches_playwright_test "$f" "$binding" "$visited" 0
  rc=$?
  rm -f "$visited"
  return "$rc"
}

relative_namespace_binding_reaches_playwright_test() {
  local f="$1" binding="$2" source_binding import_path candidate visited rc
  while IFS=$'\t' read -r source_binding import_path; do
    [[ -n "$source_binding" && -n "$import_path" ]] || continue
    while IFS= read -r candidate; do
      allocate_temp visited
      binding_reaches_playwright_test "$candidate" "$source_binding" "$visited" 0
      rc=$?
      rm -f "$visited"
      [[ "$rc" -eq 0 ]] && return 0
    done < <(resolve_relative_module_candidates "$f" "$import_path")
  done < <(source_relative_binding_lineage_edges "$f" "$binding" namespace)
  return 1
}

relative_namespace_binding_reaches_playwright_expect() {
  local f="$1" binding="$2" source_binding import_path candidate visited rc
  while IFS=$'\t' read -r source_binding import_path; do
    [[ -n "$source_binding" && -n "$import_path" ]] || continue
    while IFS= read -r candidate; do
      allocate_temp visited
      binding_reaches_playwright_expect "$candidate" "$source_binding" "$visited" 0
      rc=$?
      rm -f "$visited"
      [[ "$rc" -eq 0 ]] && return 0
    done < <(resolve_relative_module_candidates "$f" "$import_path")
  done < <(source_relative_binding_lineage_edges "$f" "$binding" namespace-expect)
  return 1
}

relative_named_binding_reaches_playwright() {
  local f="$1" binding="$2" source_name="$3" import_path candidate visited rc
  if [[ "$source_name" == "expect" ]]; then
    allocate_temp visited
    binding_reaches_playwright_expect "$f" "$binding" "$visited" 0
    rc=$?
    rm -f "$visited"
    return "$rc"
  fi
  while IFS= read -r import_path; do
    [[ -n "$import_path" ]] || continue
    while IFS= read -r candidate; do
      allocate_temp visited
      module_reaches_playwright_reference "$candidate" "$visited" 0
      rc=$?
      rm -f "$visited"
      [[ "$rc" -eq 0 ]] && return 0
    done < <(resolve_relative_module_candidates "$f" "$import_path")
  done < <(source_relative_module_references_for_named_binding "$f" "$binding" "$source_name")
  return 1
}

source_imports_unresolved_binding() {
  local f="$1" binding="$2"
  source_has_unresolved_test_import "$f" || return 1
  scanner_rg -qP "import[[:space:]]+(?:\\{[^}]*\\b(?:[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]+as[[:space:]]+)?$binding\\b[^}]*\\}|$binding\\b)[[:space:]]*from[[:space:]]*['\"](?!\\.{1,2}/)(?!vitest['\"]|jest['\"]|@jest/globals['\"]|node:test['\"]|bun:test['\"])" "$f"
}

source_imports_unresolved_expect_binding() {
  local f="$1" binding="$2" named
  source_has_unresolved_test_import "$f" || return 1
  if [[ "$binding" == "expect" ]]; then
    named='expect([[:space:]]+as[[:space:]]+expect)?'
  else
    named="expect[[:space:]]+as[[:space:]]+$binding"
  fi
  scanner_rg -qP "import[[:space:]]+\\{[^}]*\\b$named\\b[^}]*\\}[[:space:]]*from[[:space:]]*['\"](?!\\.{1,2}/)(?!vitest['\"]|jest['\"]|@jest/globals['\"]|node:test['\"]|bun:test['\"])" "$f"
}

# Reject #4f when the assertion subject is an awaited Locator value read. Those
# calls resolve primitives and remain #4c-4e triage candidates.
awaited_locator_value_read_at() {
  local file="$1" line="$2"
  awk -v target="$line" '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) lex_escape = 0
          else if (c == "\\") lex_escape = 1
          else if (c == lex_quote) { out = out "__STR__"; lex_quote = "" }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") { lex_quote = c; continue }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    NR < target { executable_source($0); next }
    NR > target + 12 { exit }
    {
      code = code " " executable_source($0)
      if (code ~ /[.](toBeTruthy|toBeDefined|toBeNull|toBeUndefined)[[:space:]]*[(]/ ||
          code ~ /[.]not[.]to([.]be)?[.](equal|undefined|null)/ ||
          code ~ /;[[:space:]]*$/) {
        print code
        exit
      }
    }
  ' "$file" 2>/dev/null |
    tr '\n' ' ' |
    scanner_rg -q 'expect[[:space:]]*\([[:space:]]*await\b.*\.(isVisible|isDisabled|isEnabled|isChecked|isHidden|isEditable|textContent|innerText|getAttribute|inputValue|allTextContents|allInnerTexts|count)[[:space:]]*\('
}

expect_promise_nonfloating_at() {
  local file="$1" line="$2"
  sed -n "${line}p" "$file" 2>/dev/null |
    scanner_rg -q '^[[:space:]]*(return[[:space:]]+|(?:export[[:space:]]+)?(?:const|let|var)[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*=|void[[:space:]]+)expect[[:space:]]*\('
}

# Tier 2 precedes the shared semantic helpers, so this self-contained #4f check
# proves both a locator/query argument and a Playwright `expect` binding. Proven
# local redeclarations are dropped; ambiguous receivers remain triage.
# KEEP THIS DEFINITION ABOVE ITS TIER 2 CALL SITE. When the equivalent check
# lived ~1400 lines below the call, bash reported `command not found`, the
# trailing `|| continue` swallowed rc 127, and every AST #4f hit was dropped
# silently — the exact silent-coverage class this scanner exists to catch.
ast_locator_truthiness_confirmed_at() {
  local file="$1" line="$2" code
  code=$(source_executable_code "$file" | sed -n "${line}p")
  [[ -n "$code" ]] || return 1
  # `expect(await locator.textContent())` asserts on a resolved value, not on the Locator: that is
  # a one-shot read (#4c-4e), not an always-true locator assertion.
  printf '%s\n' "$code" | scanner_rg -q 'expect[[:space:]]*\([[:space:]]*await\b' && return 1
  # Only a literal `page.` receiver is confirmable here. `app.getByRole(...)`, `screen.getBy*`, or a
  # bare `getBy*` may be a Testing-Library wrapper rather than a Playwright Locator, and deciding
  # that needs the binding dataflow Tier 2 cannot reach — those stay triage rather than firm P0.
  printf '%s\n' "$code" |
    scanner_rg -q '\([[:space:]]*page[[:space:]]*\.[[:space:]]*(locator|getBy[A-Z][A-Za-z]*)[[:space:]]*\(' ||
    return 1
  ast_playwright_expect_proven_at "$file" "$line"
}

ast_expect_binding_shadowed_at() {
  local file="$1" line="$2" target_code binding prefix
  target_code=$(source_executable_code "$file" | sed -n "${line}p")
  binding=$(printf '%s\n' "$target_code" |
    scanner_rg -oP '^[[:space:]]*\(?[[:space:]]*\K[A-Za-z_$][A-Za-z0-9_$]*(?=[[:space:]]*[(])' |
    head -1 |
    sed -E 's/[[:space:]]//g')
  [[ -n "$binding" ]] || return 1
  case "$binding" in *[!A-Za-z0-9_$]*) return 1 ;; esac
  # Only a name the file actually imports from Playwright can be *shadowed*. Without this, a purely
  # custom `const expect = makeCustomExpect()` would be dropped, but the contract for an unknown
  # expect is triage, not silence — only a provably-not-the-imported binding is dropped.
  source_imports_playwright_expect_binding "$file" "$binding" || return 1
  # Retain the specifier string, then drop every line mentioning it: importing a name is not
  # shadowing it, and neither is `const expect = require('@playwright/test').expect`. Without the
  # retained argument the specifier is blanked out and that CJS binding reads as a shadow.
  prefix=$(source_executable_code "$file" @playwright/test |
    sed -n "1,${line}p" |
    grep -v '@playwright/test')
  printf '%s\n' "$prefix" |
    scanner_rg -qP "(?:const|let|var)[[:space:]]*\\{[^}]*\\b$binding\\b[^}]*\\}[[:space:]]*=" && return 0
  printf '%s\n' "$prefix" |
    scanner_rg -qP "(?:^|[;{}[:space:]])(?:const|let|var|class|function)[[:space:]]+$binding\\b" && return 0
  printf '%s\n' "$prefix" |
    scanner_rg -qP "catch[[:space:]]*\\([^)]*\\b$binding\\b" && return 0
  printf '%s\n' "$prefix" |
    scanner_rg -qP "(?:function[[:space:]]*[A-Za-z_$]*[[:space:]]*\\([^)]*\\b$binding\\b|\\([^)]*\\b$binding\\b[^)]*\\)[[:space:]]*=>)" && return 0
  return 1
}

# Tier 2 runs before the later semantic helpers are declared. Keep this
# provenance check self-contained so AST #15 is final only for a proven
# Playwright expect binding; ambiguous custom expect calls remain triage.
ast_playwright_expect_proven_at() {
  local file="$1" line="$2" target_code binding prefix namespace
  target_code=$(source_executable_code "$file" | sed -n "${line}p")
  binding=$(printf '%s\n' "$target_code" |
    scanner_rg -oP '^[[:space:]]*\(?[[:space:]]*\K[A-Za-z_$][A-Za-z0-9_$]*(?:[[:space:]]*[.][[:space:]]*expect)?(?=[[:space:]]*[(])' |
    head -1 |
    sed -E 's/[[:space:]]//g')
  [[ -n "$binding" ]] || return 1
  prefix=$(source_executable_code "$file" @playwright/test |
    sed -n "1,${line}p" |
    grep -v '@playwright/test')
  case "$binding" in
    *'.expect')
      namespace=${binding%.expect}
      source_imports_playwright_namespace_binding "$file" "$namespace"
      return
      ;;
    *[!A-Za-z0-9_$]*) return 1 ;;
  esac
  printf '%s\n' "$prefix" |
    scanner_rg -qP "(?:^|[;{}[:space:]])(?:const|let|var|class|function)[[:space:]]+$binding\\b|(?:function[[:space:]]*[A-Za-z_$]*|catch)[[:space:]]*\\([^)]*\\b$binding\\b|\\([^)]*\\b$binding\\b[^)]*\\)[[:space:]]*=>" &&
    return 1
  source_imports_playwright_expect_binding "$file" "$binding" && return 0
  relative_named_binding_reaches_playwright "$file" "$binding" expect
}

# Prove framework scope independently of the generic `.e2e.*` filename
# convention. The filename remains useful for conservative review triage, but
# cannot by itself justify a gating P0 result.
file_has_framework_provenance() {
  local f="$1"
  if source_has_foreign_test_module_reference "$f"; then
    source_has_playwright_module_reference "$f" && return 0
    source_has_cypress_module_reference "$f" && return 0
    source_has_cypress_runtime_reference "$f" && return 0
    file_uses_playwright_fixture_module "$f" && return 0
    return 1
  fi
  case "$(basename "$f")" in
    *.cy.*) return 0 ;;
  esac
  case "/$f/" in
    */cypress/*) return 0 ;;
  esac
  source_has_playwright_module_reference "$f" && return 0
  source_has_cypress_module_reference "$f" && return 0
  source_has_cypress_runtime_reference "$f" && return 0
  file_uses_playwright_fixture_module "$f"
}

file_has_resolved_framework_reference() {
  local f="$1"
  source_has_playwright_module_reference "$f" && return 0
  source_has_cypress_module_reference "$f" && return 0
  source_has_cypress_runtime_reference "$f" && return 0
  file_uses_playwright_fixture_module "$f"
}

file_has_playwright_provenance() {
  local f="$1"
  source_has_playwright_module_reference "$f" && return 0
  file_uses_playwright_fixture_module "$f"
}

# Shared candidate scope for AST and regex tiers. A generic `.e2e.*` basename
# admits review candidates, while file_has_framework_provenance controls
# whether P0 evidence is allowed to enter the exit gate.
file_in_e2e_scope() {
  local f="$1"
  file_has_framework_provenance "$f" && return 0
  source_has_foreign_test_module_reference "$f" && return 1
  # A generic callback can destructure a property named `page` without using
  # Playwright. Keep that shape visible to the non-gating triage path, but do
  # not let it prove framework provenance for a final P0 verdict.
  source_has_playwright_runtime_reference "$f" && return 0
  case "$(basename "$f")" in
    *.e2e.*) return 0 ;;
  esac
  return 1
}

file_is_scanner_excluded() {
  local f="$1"
  case "/$f/" in
    */node_modules/*|*/.git/*|*/playwright-report/*|*/cypress/reports/*|\
    */test-results/*|*/dist/*|*/build/*|*/.next/*|*/out/*|*/coverage/*)
      return 0
      ;;
  esac
  case "$f" in
    *.min.js|*.min.ts) return 0 ;;
  esac
  if [[ "${#EVAL_FIXTURE_EXCLUDES[@]}" -gt 0 ]]; then
    case "/$f/" in
      */evals/files/*|*/scripts/ci/fixtures/*) return 0 ;;
    esac
  fi
  return 1
}

# A non-regular entry can only make the E2E scan incomplete when it could stand
# in for source the scanner is expected to inspect. Ignore ordinary asset-file
# symlinks (for example public/logo-current.png -> logo.png), but retain
# fail-closed behavior for every supported JS/TS extension and for directory
# links, including broken links whose names are conventional source roots.
special_entry_can_hide_scanner_source() {
  local f="$1" name="${1##*/}" extension=""
  extension="${name##*.}"
  if [[ "$extension" != "$name" ]]; then
    case ",$CODE_EXTENSIONS," in
      *",$extension,"*) return 0 ;;
    esac
  fi
  if [[ -L "$f" && -d "$f" ]]; then
    return 0
  fi
  if [[ -L "$f" ]]; then
    case "$name" in
      src|test|tests|e2e|spec|specs|playwright|cypress|support|fixtures)
        return 0
        ;;
    esac
  fi
  return 1
}

# Apply Playwright-only mechanical rules where Playwright lineage is visible or
# the callback shape is relevant enough for non-gating triage. Cypress-only path
# scope is deliberately insufficient: a Cypress helper named `page` must not
# resolve as the Playwright Page API. The final P0 gate independently requires
# file_has_framework_provenance, so a bare `async ({ page })` callback cannot
# become authoritative without import/fixture/type lineage.
file_in_playwright_scope() {
  local f="$1"
  case "/$f/" in
    */playwright/*) return 0 ;;
  esac
  source_has_playwright_module_reference "$f" && return 0
  source_executable_code "$f" |
    scanner_rg -q "async[[:space:]]*\\([[:space:]]*\\{[[:space:]]*page\\b" &&
    return 0
  file_uses_playwright_fixture_module "$f"
}

# Shared `// JUSTIFIED:` marker check, honored by ALL THREE tiers so the documented
# convention is consistent. P1/P2 hits are suppressed; P0 hits move to the
# externally-verifiable candidate ledger instead of disappearing. Returns 0 when the hit at
# <file>:<line> is covered by a JUSTIFIED marker on the immediately preceding pure
# //-comment line or the start of the same fluent chain. The #7 no-exemption contract is the
# caller's responsibility — callers must NOT consult this for focused-test rules.
_line_is_justified() {
  local _hf="$1" _hl="$2"
  [[ -f "$_hf" && "$_hl" =~ ^[0-9]+$ ]] || return 1
  awk -v target="$_hl" '
    function classify(s,    code, comment, i, c, nchar, trimmed) {
      code = ""
      comment = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") {
            lex_block = 0
            i++
          }
          continue
        }
        if (lex_quote != "") {
          code = code c
          if (lex_escape) {
            lex_escape = 0
          } else if (c == "\\") {
            lex_escape = 1
          } else if (c == lex_quote) {
            lex_quote = ""
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          code = code c
          continue
        }
        if (c == "/" && nchar == "*") {
          lex_block = 1
          i++
          continue
        }
        if (c == "/" && nchar == "/") {
          comment = substr(s, i + 2)
          break
        }
        code = code c
      }
      trimmed = code
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", trimmed)
      code_line[NR] = trimmed
      pure_comment[NR] = (comment != "" && trimmed == "")
      marker[NR] = (comment ~ /^[[:space:]]*JUSTIFIED:[[:space:]]*[^[:space:]]/)
    }
    NR <= target { classify($0) }
    NR == target { exit }
    END {
      if (target > 1 && pure_comment[target - 1] && marker[target - 1]) exit 0
      # A marker immediately above an evaluate/waitForFunction callback covers
      # executable hits inside that callback. Require the target to remain
      # inside the same brace-delimited callback so a later sibling expression
      # cannot inherit the rationale.
      lower = target > 24 ? target - 24 : 1
      for (i = target - 1; i >= lower; i--) {
        if (!pure_comment[i] || !marker[i]) continue
        start = i + 1
        while (start < target && code_line[start] == "") start++
        header = ""
        depth = 0
        opened = 0
        valid = 1
        for (j = start; j <= target; j++) {
          if (opened == 0) header = header " " code_line[j]
          opens = gsub(/\{/, "{", code_line[j])
          closes = gsub(/\}/, "}", code_line[j])
          depth += opens - closes
          if (opens > 0) opened = 1
          if (opened && j < target && depth <= 0) valid = 0
          if (j == target) break
        }
        if (valid && opened && depth > 0 &&
            header ~ /[.](evaluate|waitForFunction)[[:space:]]*[(]/) exit 0
      }
      # A marker above the start of one fluent expression also covers a later
      # physical-line hit in that same chain. Keep this narrow: the reported
      # line must start with a member continuation, and no intervening line may
      # terminate a statement or open/close a block.
      lower = target > 8 ? target - 8 : 1
      if (code_line[target] ~ /^[.]/) {
        for (i = target - 1; i >= lower; i--) {
          if (pure_comment[i] && marker[i]) {
            valid = 1
            saw_code = 0
            roots = 0
            if (code_line[i + 1] == "") valid = 0
            for (j = i + 1; j <= target; j++) {
              if (code_line[j] == "") continue
              saw_code = 1
              if (code_line[j] !~ /^[.]/) roots++
              if (roots > 1) valid = 0
              if (j < target && code_line[j] ~ /[;{}]/) valid = 0
            }
            if (valid && saw_code) exit 0
          }
          if (code_line[i] ~ /[;{}]/) break
        }
      }
      exit 1
    }
  ' "$_hf" >/dev/null 2>&1
}

if [[ ! -e "$ROOT" ]]; then
  echo "error: path does not exist: $REQUESTED_ROOT" >&2
  exit 2
fi

# Re-resolve both the caller's lexical path and the pinned canonical path at
# security boundaries. A changed parent-component symlink, replaced root, or
# changed root kind makes the scan incomplete rather than allowing a zero-hit
# Summary from a different tree.
validate_scan_root_identity() {
  local _requested_parent _requested_name _requested_parent_real
  local _requested_real="" _pinned_parent _pinned_name _pinned_parent_real
  local _pinned_real=""

  if [[ -L "$REQUESTED_ROOT" ]]; then
    printf 'INCOMPLETE: requested scan root identity changed after validation: %q [symbolic link]; no final Summary was emitted.\n' \
      "$REQUESTED_ROOT" >&2
    exit 2
  fi

  case "$REQUESTED_ROOT_KIND" in
    directory)
      if [[ -d "$REQUESTED_ROOT" ]]; then
        _requested_real=$(cd "$REQUESTED_ROOT" 2>/dev/null && pwd -P)
      fi
      if [[ -d "$ROOT" && ! -L "$ROOT" ]]; then
        _pinned_real=$(cd "$ROOT" 2>/dev/null && pwd -P)
      fi
      ;;
    file)
      _requested_parent=${REQUESTED_ROOT%/*}
      _requested_name=${REQUESTED_ROOT##*/}
      [[ "$_requested_parent" == "$REQUESTED_ROOT" ]] && _requested_parent="."
      [[ -z "$_requested_parent" ]] && _requested_parent="/"
      if [[ -f "$REQUESTED_ROOT" && ! -L "$REQUESTED_ROOT" ]]; then
        _requested_parent_real=$(cd "$_requested_parent" 2>/dev/null && pwd -P)
        [[ -n "$_requested_parent_real" ]] &&
          _requested_real="$_requested_parent_real/$_requested_name"
      fi
      _pinned_parent=${ROOT%/*}
      _pinned_name=${ROOT##*/}
      [[ -z "$_pinned_parent" ]] && _pinned_parent="/"
      if [[ -f "$ROOT" && ! -L "$ROOT" ]]; then
        _pinned_parent_real=$(cd "$_pinned_parent" 2>/dev/null && pwd -P)
        [[ -n "$_pinned_parent_real" ]] &&
          _pinned_real="$_pinned_parent_real/$_pinned_name"
      fi
      ;;
  esac

  if [[ "$_requested_real" != "$REQUESTED_ROOT_REAL" ||
        "$_pinned_real" != "$REQUESTED_ROOT_REAL" ]]; then
    printf 'INCOMPLETE: requested scan root identity changed after validation: %q; no final Summary was emitted.\n' \
      "$REQUESTED_ROOT" >&2
    exit 2
  fi
}

# Ripgrep deliberately skips symbolic links and non-regular filesystem entries.
# Validate the requested tree with lstat/no-follow semantics before discovery so
# an in-scope symlink, FIFO, socket, device, or other special entry cannot make
# the scan look complete while silently hiding source. Excluded artifact/vendor
# trees retain the same scope boundary as the scanner itself.
preflight_scanner_tree() {
  local _entries _errors _diagnostics _find_rc _entry _relative _kind
  local _count=0 _shown=0 _omitted=0 _rendered=""
  allocate_temp _entries
  allocate_temp _errors
  allocate_temp _diagnostics
  : > "$_diagnostics"
  validate_scan_root_identity

  if [[ "${#EVAL_FIXTURE_EXCLUDES[@]}" -gt 0 ]]; then
    "$FIND_BIN" -P "$ROOT" \
      \( -type d \( \
        -name node_modules -o -name .git -o -name playwright-report -o \
        -path '*/cypress/reports' -o -name test-results -o -name dist -o \
        -name build -o -name .next -o -name out -o -name coverage -o \
        -path '*/evals/files' -o -path '*/scripts/ci/fixtures' \
      \) -prune \) -o \
      \( -type l -o \( ! -type f ! -type d \) \) -print0 \
      >"$_entries" 2>"$_errors"
  else
    "$FIND_BIN" -P "$ROOT" \
      \( -type d \( \
        -name node_modules -o -name .git -o -name playwright-report -o \
        -path '*/cypress/reports' -o -name test-results -o -name dist -o \
        -name build -o -name .next -o -name out -o -name coverage \
      \) -prune \) -o \
      \( -type l -o \( ! -type f ! -type d \) \) -print0 \
      >"$_entries" 2>"$_errors"
  fi
  _find_rc=$?
  if [[ "$_find_rc" -ne 0 ]]; then
    printf 'INCOMPLETE: scanner tree preflight could not inspect the complete requested tree (find exit %s).\n' \
      "$_find_rc" >&2
    sed -n '1,20p' "$_errors" | sanitize_evidence >&2
    rm -f "$_entries" "$_errors" "$_diagnostics"
    exit 2
  fi

  while IFS= read -r -d '' _entry; do
    file_is_scanner_excluded "$_entry" && continue
    special_entry_can_hide_scanner_source "$_entry" || continue
    _count=$((_count + 1))
    if [[ "$_shown" -ge 20 ]]; then
      continue
    fi
    if [[ -L "$_entry" ]]; then
      _kind="symbolic link"
    elif [[ -p "$_entry" ]]; then
      _kind="FIFO"
    elif [[ -S "$_entry" ]]; then
      _kind="socket"
    elif [[ -b "$_entry" ]]; then
      _kind="block device"
    elif [[ -c "$_entry" ]]; then
      _kind="character device"
    else
      _kind="non-regular entry"
    fi
    case "$_entry" in
      "$ROOT") _relative="${_entry##*/}" ;;
      "$ROOT"/*) _relative="${_entry#"$ROOT"/}" ;;
      *) _relative="$_entry" ;;
    esac
    printf -v _rendered '%q' "$_relative"
    printf '  %s [%s]\n' "$_rendered" "$_kind" >> "$_diagnostics"
    _shown=$((_shown + 1))
  done < "$_entries"
  rm -f "$_entries" "$_errors"

  if [[ "$_count" -gt 0 ]]; then
    printf 'INCOMPLETE: scanner tree preflight found %s unsupported filesystem entries (showing at most 20); no scan was run.\n' \
      "$_count" >&2
    sed -n '1,20p' "$_diagnostics" >&2
    _omitted=$((_count - _shown))
    if [[ "$_omitted" -gt 0 ]]; then
      printf '  %s additional unsupported entries omitted\n' "$_omitted" >&2
    fi
    rm -f "$_diagnostics"
    exit 2
  fi
  rm -f "$_diagnostics"
}

preflight_scanner_tree
validate_scan_root_identity

if ! printf 'pcre2\n' | "$RG_BIN" -P '^pcre2$' - >/dev/null 2>&1; then
  echo "error: rg with PCRE2 support is required for Tier 3 (-P unavailable)" >&2
  exit 2
fi
discover_candidate_files() {
  local _destination="$1" _filename_rg_rc
  "$RG_BIN" --files -0 --hidden --no-ignore \
    --glob "$ALL_CODE_GLOB" \
    --glob '!**/node_modules/**' \
    --glob '!**/.git/**' \
    --glob '!**/playwright-report/**' \
    --glob '!**/cypress/reports/**' \
    --glob '!**/test-results/**' \
    --glob '!**/dist/**' \
    --glob '!**/build/**' \
    --glob '!**/.next/**' \
    --glob '!**/out/**' \
    --glob '!**/coverage/**' \
    --glob '!*.min.js' \
    --glob '!*.min.ts' \
    ${EVAL_FIXTURE_EXCLUDES[@]+"${EVAL_FIXTURE_EXCLUDES[@]}"} \
    -- "$ROOT" > "$_destination" 2>/dev/null
  _filename_rg_rc=$?
  if [[ "$_filename_rg_rc" -gt 1 ]]; then
    printf 'error: unable to validate scanner filenames before scanning\n' >&2
    exit 2
  fi
}

validate_candidate_filenames() {
  local _source="$1" _candidate_file _unsupported_file=""
  while IFS= read -r -d '' _candidate_file; do
    case "/$_candidate_file/" in
      */node_modules/*|*/.git/*|*/playwright-report/*|*/cypress/reports/*|*/test-results/*|*/dist/*|*/build/*|*/.next/*|*/out/*|*/coverage/*)
        continue
        ;;
    esac
    case "$_candidate_file" in
      *.min.js|*.min.ts) continue ;;
    esac
    case "$_candidate_file" in
      *:*|*$'\n'*) _unsupported_file="$_candidate_file"; break ;;
    esac
  done < "$_source"
  if [[ -n "$_unsupported_file" ]]; then
    printf 'error: colon/newline-containing filenames are unsupported by the scanner hit transport: %q\n' \
      "$_unsupported_file" >&2
    exit 2
  fi
}

allocate_temp _filename_list
discover_candidate_files "$_filename_list"
validate_scan_root_identity
validate_candidate_filenames "$_filename_list"

# Retain the no-ignore discovery result as an immutable candidate-identity
# manifest. Each identity is collected through O_NOFOLLOW and includes the
# opened file's device/inode/mode/size/timestamps plus a SHA-256 content digest.
# Recompute it immediately before each tier and the final Summary so same-path
# regular-file rewrites/replacements fail closed alongside type changes.
allocate_temp CANDIDATE_IDENTITY_FILE

candidate_identity() {
  local _candidate="$1"
  [[ -n "$PYTHON3_BIN" ]] || return 1
  "$PYTHON3_BIN" -I -B -c '
import hashlib
import os
import stat
import sys

path = sys.argv[1]
flags = os.O_RDONLY
flags |= getattr(os, "O_CLOEXEC", 0)
no_follow = getattr(os, "O_NOFOLLOW", None)
if no_follow is None:
    raise OSError("O_NOFOLLOW is unavailable")
flags |= no_follow
fd = os.open(path, flags)
try:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise OSError("candidate is not a regular file")
    digest = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    after = os.fstat(fd)
finally:
    os.close(fd)

fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
if any(getattr(before, field) != getattr(after, field) for field in fields):
    raise OSError("candidate changed while fingerprinting")
current = os.lstat(path)
if any(getattr(after, field) != getattr(current, field) for field in fields):
    raise OSError("candidate path changed while fingerprinting")
print(
    ":".join(str(getattr(after, field)) for field in fields)
    + ":"
    + digest.hexdigest()
)
' "$_candidate" 2>/dev/null
}

record_candidate_manifest() {
  local _source="$1" _destination="$2"
  local _candidate _identity _invalid_kind
  : > "$_destination"
  while IFS= read -r -d '' _candidate; do
    file_is_scanner_excluded "$_candidate" && continue
    _identity=$(candidate_identity "$_candidate") || {
      if [[ -L "$_candidate" ]]; then
        _invalid_kind="symbolic link"
      elif [[ -p "$_candidate" ]]; then
        _invalid_kind="FIFO"
      elif [[ -S "$_candidate" ]]; then
        _invalid_kind="socket"
      elif [[ -e "$_candidate" && ! -f "$_candidate" ]]; then
        _invalid_kind="non-regular entry"
      elif [[ ! -e "$_candidate" ]]; then
        _invalid_kind="missing path"
      else
        _invalid_kind="identity unavailable"
      fi
      printf 'INCOMPLETE: scanner candidate changed after discovery: %q [%s]; no final Summary was emitted.\n' \
        "$_candidate" "$_invalid_kind" >&2
      exit 2
    }
    printf '%s\0%s\0' "$_candidate" "$_identity" >> "$_destination"
  done < "$_source"
}

validate_candidate_manifest() {
  local _current_files _current_manifest _comparison
  validate_scan_root_identity
  allocate_temp _current_files
  allocate_temp _current_manifest
  discover_candidate_files "$_current_files"
  validate_scan_root_identity
  validate_candidate_filenames "$_current_files"
  record_candidate_manifest "$_current_files" "$_current_manifest"
  _comparison=$("$PYTHON3_BIN" -I -B -c '
import sys

def read_manifest(path):
    fields = open(path, "rb").read().split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) % 2:
        raise SystemExit("malformed manifest")
    return dict(zip(fields[0::2], fields[1::2]))

expected = read_manifest(sys.argv[1])
actual = read_manifest(sys.argv[2])
for path in sorted(expected.keys() - actual.keys()):
    print("removed from candidate set")
    print(path.decode("utf-8", "backslashreplace"))
    raise SystemExit(1)
for path in sorted(actual.keys() - expected.keys()):
    print("added to candidate set")
    print(path.decode("utf-8", "backslashreplace"))
    raise SystemExit(1)
for path in sorted(expected.keys() & actual.keys()):
    if expected[path] != actual[path]:
        print("regular-file identity/content drift")
        print(path.decode("utf-8", "backslashreplace"))
        raise SystemExit(1)
' "$CANDIDATE_IDENTITY_FILE" "$_current_manifest" 2>/dev/null)
  _comparison_rc=$?
  rm -f "$_current_files" "$_current_manifest"
  if [[ "$_comparison_rc" -ne 0 ]]; then
    _invalid_kind=${_comparison%%$'\n'*}
    _invalid=${_comparison#*$'\n'}
    [[ -n "$_invalid_kind" && "$_invalid" != "$_comparison" ]] || {
      _invalid_kind="manifest comparison unavailable"
      _invalid="$ROOT"
    }
    printf 'INCOMPLETE: scanner candidate changed after discovery: %q [%s]; no final Summary was emitted.\n' \
      "$_invalid" "$_invalid_kind" >&2
    exit 2
  fi
}

record_candidate_manifest "$_filename_list" "$CANDIDATE_IDENTITY_FILE"

total_hits=0
p0_hits=0
p1_hits=0
llm_triage_hits=0
p0_candidate_hits=0
ast_p0_hits=0
ast_p1_hits=0
hit_pattern_ids=""
eslint_ran=0
allocate_temp STRUCTURAL_HITS_FILE
allocate_temp RG_RUNTIME_ERROR_FILE
allocate_temp SUPPRESSED_HITS_FILE
allocate_temp SUPPRESSED_P0_CANDIDATES_FILE
: > "$RG_RUNTIME_ERROR_FILE"
: > "$SUPPRESSED_HITS_FILE"
: > "$SUPPRESSED_P0_CANDIDATES_FILE"

record_justified_suppression() {
  local severity="$1" pattern_id="$2" file="$3" line="$4" canonical_file=""
  canonical_file=$(absolute_hit_file "$file" 2>/dev/null || true)
  [[ -n "$canonical_file" ]] && file="$canonical_file"
  printf '%s:%s\n' "$file" "$line" >> "$SUPPRESSED_HITS_FILE"
  if [[ "$severity" == "P0" ]]; then
    printf '%s\t%s:%s\n' "$pattern_id" "$file" "$line" \
      >> "$SUPPRESSED_P0_CANDIDATES_FILE"
  fi
}

scanner_rg() {
  "$RG_BIN" "$@"
  local rc=$?
  if [[ "$rc" -gt 1 ]]; then
    printf '%s\n' "$rc" > "$RG_RUNTIME_ERROR_FILE"
  fi
  return "$rc"
}

abort_on_rg_error() {
  if [[ -s "$RG_RUNTIME_ERROR_FILE" ]]; then
    printf 'error: ripgrep helper invocation failed (exit %s)\n' "$(tail -1 "$RG_RUNTIME_ERROR_FILE")" >&2
    exit 2
  fi
}

# Tier 1 records exact file/line fingerprints. Tier 2/3 always run
# independently and suppress only exact duplicates, so a project config that
# disables a lint rule cannot suppress the bundled scanner's P0 gate.
# The ast-grep rules are language:TypeScript (.ts/.mts/.cts) by design; .js/.jsx/.tsx coverage is delegated to the always-on Tier-3 regex net.

# AST-grep rule → our pattern ID (bash 3.2 compatible — no associative arrays)
get_pattern_for_ast_rule() {
  case "$1" in
    sg-15-missing-await-playwright-expect) echo '#15' ;;
    sg-4ce-count|sg-4ce-state-bool|sg-4ce-text) echo '#4c-4e' ;;
    sg-4f-locator-as-truthy) echo '#4f' ;;
  esac
}

dedupe_class_for_pattern() {
  case "$1" in
    '#7') echo 'focused-test' ;;
    '#9') echo 'playwright-wait' ;;
    '#9b') echo 'cypress-wait' ;;
    '#15'|'#16') echo 'missing-playwright-await' ;;
    '#4f') echo 'silent-pass' ;;
    '#4c-4e') echo 'one-shot-read' ;;
  esac
}

absolute_hit_file() {
  local file="$1" resolved
  [[ -f "$file" ]] || file="$ROOT/$file"
  [[ -f "$file" && ! -L "$file" ]] || return 1
  resolved=$(cd "$(dirname "$file")" 2>/dev/null &&
    printf '%s/%s\n' "$(pwd -P)" "$(basename "$file")") || return 1
  case "$REQUESTED_ROOT_KIND" in
    directory)
      case "$resolved" in
        "$REQUESTED_ROOT_REAL"/*) ;;
        *) return 1 ;;
      esac
      ;;
    file) [[ "$resolved" == "$REQUESTED_ROOT_REAL" ]] || return 1 ;;
    *) return 1 ;;
  esac
  printf '%s\n' "$resolved"
}

# --- Private, pinned npm environment for the optional Tier 1 download path ----
# Two properties are load-bearing here and neither one alone is sufficient.
#   1. A private working directory. npm resolves its project config from the
#      directory it runs in, so running from the audited repository lets that
#      repository's `.npmrc` choose the registry, the cache, and the script
#      policy for the packages we are about to execute. A SCOPED line
#      (`@typescript-eslint:registry=...`) has no `npm_config_*` counterpart and
#      therefore survives any registry pin — verified with `npm config get`. The
#      private cwd is what removes that whole surface: the repository's `.npmrc`
#      is never consulted.
#   2. `env -i` plus explicit `npm_config_*` pins. The download step is where
#      third-party code is first fetched and executed, so it must not inherit
#      the operator's real HOME (and `~/.npmrc` auth tokens), npm cache,
#      NODE_OPTIONS, proxy variables, or cloud credentials.
# `npm_config_userconfig` and `npm_config_globalconfig` must name DISTINCT
# files: npm >= 9 aborts with "double-loading config" when both are /dev/null.
PINNED_NPM_ROOT=""

# Single source of truth for the npm configuration pins. Both the download step
# and the ESLint run step build their environment from this one generator, so a
# pin can never be added to one and forgotten on the other.
pinned_npm_config_env() {
  local base="$1"
  printf '%s\n' \
    "npm_config_cache=$base/npm-cache" \
    "npm_config_prefix=$base/npm-prefix" \
    "npm_config_userconfig=$base/npmrc/user" \
    "npm_config_globalconfig=$base/npmrc/global" \
    "npm_config_registry=https://registry.npmjs.org/" \
    "npm_config_ignore_scripts=true"
}

prepare_pinned_npm_dirs() {
  local base="$1"
  mkdir -p -m 700 "$base/npm-cache" "$base/npm-prefix" "$base/npmrc" || return 1
  : > "$base/npmrc/user" || return 1
  : > "$base/npmrc/global" || return 1
  chmod 600 "$base/npmrc/user" "$base/npmrc/global" || return 1
  return 0
}

setup_pinned_npm_env() {
  [[ -n "$PINNED_NPM_ROOT" ]] && return 0
  [[ -n "$NODE_BIN" && -n "$NPX_BIN" ]] || return 1
  local _root
  allocate_temp _root -d
  chmod 700 "$_root" || return 1
  mkdir -m 700 "$_root/bin" "$_root/home" "$_root/tmp" "$_root/config" \
    "$_root/xdg-cache" "$_root/work" || return 1
  prepare_pinned_npm_dirs "$_root" || return 1
  # Anchor npm's project-config and local-prefix discovery inside scanner-owned
  # storage. Without these two files npm walks UP from the working directory and
  # can adopt an unrelated ancestor package.json/.npmrc as "the project".
  printf '{"name":"e2e-reviewer-tier1","version":"0.0.0","private":true}\n' \
    > "$_root/work/package.json" || return 1
  : > "$_root/work/.npmrc" || return 1
  /bin/ln -s "$NODE_BIN" "$_root/bin/node" || return 1
  PINNED_NPM_ROOT="$_root"
  return 0
}

# The ONLY path from try_eslint to npx. The hardening travels with the call
# instead of sitting at a fixed position in the function, so a future edit
# cannot reintroduce a download step that runs before its own environment
# exists: calling this before setup_pinned_npm_env fails closed (127) and Tier 1
# then reports the failure and falls through to Tier 2/3.
run_pinned_npx() {
  if [[ -z "$PINNED_NPM_ROOT" || ! -d "$PINNED_NPM_ROOT/work" ]]; then
    printf 'error: refusing to run npx before the private pinned npm environment exists\n' >&2
    return 127
  fi
  local -a _pins=()
  local _pin
  while IFS= read -r _pin; do _pins+=("$_pin"); done < <(pinned_npm_config_env "$PINNED_NPM_ROOT")
  if [[ "${#_pins[@]}" -eq 0 ]]; then
    printf 'error: refusing to run npx without the pinned npm configuration\n' >&2
    return 127
  fi
  (
    cd "$PINNED_NPM_ROOT/work" || exit 127
    exec /usr/bin/env -i \
      "PATH=$PINNED_NPM_ROOT/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
      "HOME=$PINNED_NPM_ROOT/home" \
      "TMPDIR=$PINNED_NPM_ROOT/tmp" \
      "TMP=$PINNED_NPM_ROOT/tmp" \
      "TEMP=$PINNED_NPM_ROOT/tmp" \
      "XDG_CONFIG_HOME=$PINNED_NPM_ROOT/config" \
      "XDG_CACHE_HOME=$PINNED_NPM_ROOT/xdg-cache" \
      "${_pins[@]}" \
      "CI=1" \
      "NO_COLOR=1" \
      "LANG=C" \
      "LC_ALL=C" \
      "LC_CTYPE=C" \
      "$NPX_BIN" "$@"
  )
}

# Optional Tier 1 uses an approved local ESLint or the explicit pinned-download
# path; bundled checks remain sufficient when it is absent. A generated flat
# config supports ESLint v8.21+ and v9+ without claiming coverage on failure.
try_eslint() {
  local plugin="$1"; local label="$2"

  if [[ "$E2E_SMELL_ALLOW_PROJECT_ESLINT" != "1" ]]; then
    return 1
  fi

  local plugin_path="$PROJECT_ROOT_REAL/node_modules/eslint-plugin-$plugin"
  local local_eslint="$PROJECT_ROOT_REAL/node_modules/.bin/eslint"
  local mode
  local eslint_bin
  local -a npx_args
  if [[ -d "$plugin_path" && -x "$local_eslint" ]]; then
    mode="locally installed"
    eslint_bin="$local_eslint"
    npx_args=()
  elif [[ "${E2E_SMELL_NO_ESLINT_DOWNLOAD:-}" == "1" ]]; then
    printf '\n[ESLint] %s — eslint-plugin-%s not installed and E2E_SMELL_NO_ESLINT_DOWNLOAD=1 — skipping\n' "$label" "$plugin"
    return 1
  elif ! setup_pinned_npm_env; then
    printf '\n[ESLint] %s — local eslint/plugin unavailable and no trusted npx executable was found (or the private pinned npm environment could not be created) — skipping Tier 1; Tier 3 still runs, and Tier 2 runs only when available/enabled\n' "$label"
    return 1
  else
    mode="auto-downloaded via npx (set E2E_SMELL_NO_ESLINT_DOWNLOAD=1 to skip)"
    # Keep TypeScript direct so legacy-peer-deps cannot omit the parser peer.
    # Do not replace these pins with tags, ranges, or a dynamically assembled
    # unversioned package name; updating any pin requires reviewing the whole
    # set because their peer ranges are coupled.
    # Top-level packages are exact and jointly reviewed; transitives still float
    # because there is no lockfile. Both --ignore-scripts and the pinned npm
    # environment block lifecycle scripts and project .npmrc overrides.
    npx_args=(
      --yes
      --ignore-scripts
      -p 'eslint@10.8.0'
      -p '@typescript-eslint/parser@8.65.0'
      -p 'typescript@6.0.3'
    )
    # The companion silent-pass plugin is Cypress-only now. Its Playwright counterpart was
    # upstreamed as `no-unnecessary-assertions`, shipped in eslint-plugin-playwright v2.11.0 and
    # enabled by that plugin's `recommended` config — so #4f is covered by Tier 1 with no extra
    # package, and eslint-plugin-playwright-silent-pass is deprecated on npm. Downloading it here
    # would pull a deprecated package and double-report the same finding.
    if [[ "$plugin" == "cypress" ]]; then
      npx_args+=(
        -p 'eslint-plugin-cypress@6.4.3'
        -p 'eslint-plugin-cypress-silent-pass@0.2.2'
        -p 'eslint-plugin-mocha@12.0.1'
      )
    else
      npx_args+=(-p 'eslint-plugin-playwright@2.11.0')
    fi
    # End of the reviewed pin set. `--` closes npm's own option list; each call
    # site appends the command word itself. ESLint is NOT run through npx: it is
    # materialized once here and then invoked directly from the resolved entry
    # point, so no second npm/npx process ever runs from the audited repository.
    npx_args+=(--)
    eslint_bin=""
  fi

  # Generate the flat config. ESLint v9 loads eslint.config.mjs via ESM import whose module
  # resolution is anchored at the CONFIG FILE's directory — a /tmp config cannot see the
  # npx-cache-installed plugins by bare name. Resolve their ABSOLUTE entry paths inside the
  # same npx environment (CJS require.resolve honors npx's NODE_PATH) and embed those.
  local _paths _plugin_abs _parser_abs _mocha_abs=""
  local _cfgd
  allocate_temp _cfgd -d
  # npm >=9 npx exposes packages only via PATH (no NODE_PATH); derive the npx env's
  # node_modules root from PATH[0] and resolve with explicit paths. Falls back to
  # <cwd>/node_modules for the locally-installed mode.
  cat > "$_cfgd/resolve.cjs" <<'EOFRES'
const fs = require('fs');
const path = require('path');
const cands = [
  process.env.PATH.split(':')[0].replace(/\/\.bin$/, ''),
  process.cwd() + '/node_modules',
];
// 'eslint#bin' asks for the CLI entry point of the ESLint that was just
// materialized, so the caller can execute it directly with node instead of
// invoking npx a second time from the audited repository. `eslint/bin/*` is not
// in the package's `exports` map, so resolve package.json (which is exported)
// and read its `bin` field.
const bin = () => {
  for (const c of cands) {
    try {
      const pj = require.resolve('eslint/package.json', { paths: [c] });
      const declared = JSON.parse(fs.readFileSync(pj, 'utf8')).bin;
      const rel = typeof declared === 'string' ? declared : declared && declared.eslint;
      if (rel) {
        const abs = path.resolve(path.dirname(pj), rel);
        if (fs.existsSync(abs)) return abs;
      }
    } catch (e) {}
    const fallback = path.join(c, 'eslint', 'bin', 'eslint.js');
    if (fs.existsSync(fallback)) return fallback;
  }
  throw new Error('unresolvable: eslint#bin');
};
const r = (n) => {
  if (n === 'eslint#bin') return bin();
  for (const c of cands) { try { return require.resolve(n, { paths: [c] }); } catch (e) {} }
  throw new Error('unresolvable: ' + n);
};
console.log(JSON.stringify(process.argv.slice(2).map(r)));
EOFRES
  local -a _want=("eslint-plugin-$plugin" "@typescript-eslint/parser")
  [[ "$plugin" == "cypress" ]] && _want+=("eslint-plugin-mocha")
  if [[ "$mode" == "locally installed" ]]; then
    # No registry traffic and no third-party execution: this only runs our own
    # resolver with the canonical Node against the project's existing tree.
    [[ -n "$NODE_BIN" ]] ||
      _paths=""
    [[ -n "$NODE_BIN" ]] &&
      _paths=$( (cd "$PROJECT_ROOT_REAL" && "$NODE_BIN" "$_cfgd/resolve.cjs" "${_want[@]}") 2>/dev/null | tail -1 )
  else
    # This single call is the download-and-execute step. It materializes the
    # whole pinned set, so it runs from the private working directory under the
    # pinned npm configuration (see run_pinned_npx) and additionally resolves
    # the ESLint CLI entry point for the run step below.
    _want+=("eslint#bin")
    _paths=$(run_pinned_npx "${npx_args[@]}" "$NODE_BIN" "$_cfgd/resolve.cjs" "${_want[@]}" 2>/dev/null | tail -1)
  fi
  if [[ -z "$_paths" || "$_paths" != "["* ]]; then
    printf '\n[ESLint] %s — could not resolve eslint-plugin-%s (or @typescript-eslint/parser) — skipping Tier 1; Tier 3 still runs, and Tier 2 runs only when available/enabled\n' "$label" "$plugin"
    rm -rf "$_cfgd"
    return 1
  fi
  _plugin_abs=$(printf '%s' "$_paths" | sed 's/^\["//; s/",".*$//; s/"\]$//')
  _parser_abs=$(printf '%s' "$_paths" | awk -F'","' '{print $2}' | sed 's/"\]$//')
  if [[ "$plugin" == "cypress" ]]; then
    _mocha_abs=$(printf '%s' "$_paths" | awk -F'","' '{print $3}' | sed 's/"\]$//')
  fi

  # Download path only: the ESLint CLI entry point inside the private npx
  # environment, requested as the LAST element of "${_want[@]}".
  local _eslint_js="" _binfield=3
  if [[ "$mode" != "locally installed" ]]; then
    [[ "$plugin" == "cypress" ]] && _binfield=4
    _eslint_js=$(printf '%s' "$_paths" | awk -F'","' -v n="$_binfield" '{print $n}' | sed 's/"\]$//')
    if [[ -z "$_eslint_js" || ! -f "$_eslint_js" ]]; then
      printf '\n[ESLint] %s — could not resolve the pinned ESLint entry point inside the private npm environment — skipping Tier 1; Tier 3 still runs, and Tier 2 runs only when available/enabled\n' "$label"
      rm -rf "$_cfgd"
      return 1
    fi
  fi

  # Companion silent-pass plugin — Cypress only. Best-effort: resolved separately so a
  # missing/offline package NEVER breaks Tier 1, and Tier 2/3 still cover #4f regardless.
  # Playwright is deliberately excluded: #4f was upstreamed as `no-unnecessary-assertions`
  # (mskelton/eslint-plugin-playwright#470), shipped in v2.11.0, and enabled by that plugin's
  # `recommended` config — which the flat/recommended spread below already pulls in. Resolving
  # the companion here too would load a package now deprecated on npm and double-report #4f.
  # The rule id still is not hardcoded: it arrives through recommended, so an older
  # eslint-plugin-playwright simply does not enable it instead of erroring "rule not found".
  local _sp_abs="" _sp_paths="" _sp_imp="" _sp_plg="" _sp_rul=""
  if [[ "$plugin" == "cypress" ]]; then
    if [[ "$mode" == "locally installed" ]]; then
      _sp_paths=$( (cd "$PROJECT_ROOT_REAL" && "$NODE_BIN" "$_cfgd/resolve.cjs" "eslint-plugin-$plugin-silent-pass") 2>/dev/null | tail -1 )
    else
      _sp_paths=$(run_pinned_npx "${npx_args[@]}" "$NODE_BIN" "$_cfgd/resolve.cjs" "eslint-plugin-$plugin-silent-pass" 2>/dev/null | tail -1)
    fi
  fi
  if [[ "$_sp_paths" == "["* ]]; then
    _sp_abs=$(printf '%s' "$_sp_paths" | sed 's/^\["//; s/"\]$//')
    _sp_imp="import spp from '$_sp_abs';"
    _sp_plg=", '$plugin-silent-pass': spp"
    _sp_rul=", '$plugin-silent-pass/no-silent-pass': 'error'"
  fi

  # Respect the project's own flat config when it has one. ESLint flat config is an array
  # and later entries win, so appending the project's config after ours lets a deliberate
  # `'playwright/no-force': 'off'` actually take effect instead of being overridden by our
  # `recommended` spread. Severity edits (error<->warn) are ignored on purpose: severity here
  # is ours to assign (P0/P1), not the project's.
  # Only flat configs are honored — legacy .eslintrc cannot be imported from an ESM config,
  # and those projects fall through to the recommended-only behavior with the note below.
  local _localcfg="" _localimport="" _localspread=""
  for _c in eslint.config.mjs eslint.config.js eslint.config.cjs; do
    if [[ -f "$PROJECT_ROOT_REAL/$_c" ]]; then
      _localcfg="$PROJECT_ROOT_REAL/$_c"
      break
    fi
  done
  if [[ -n "$_localcfg" ]]; then
    _localimport="import projectConfig from '$_localcfg';"
    # The project's default export may be a single object or an array; normalize before spreading.
    _localspread='  ...(Array.isArray(projectConfig) ? projectConfig : [projectConfig]),'
  fi

  # Conditional evals/files ignore mirrors Tier 3's EVAL_FIXTURE_EXCLUDES.
  local _cfg _evalign=""
  _cfg="$_cfgd/eslint.config.mjs"
  if [[ "${#EVAL_FIXTURE_EXCLUDES[@]}" -gt 0 ]]; then
    _evalign="'**/evals/files/**','**/scripts/ci/fixtures/**',"
  fi
  if [[ "$plugin" == "playwright" ]]; then
    {
      printf "import playwright from '%s';\n" "$_plugin_abs"
      printf "import tsParser from '%s';\n" "$_parser_abs"
      printf '%s%s\n' "$_sp_imp" "$_localimport"
      printf "export default [\n  { ignores: ['**/node_modules/**','**/dist/**','**/build/**','**/.next/**','**/out/**','**/coverage/**','**/*.min.js',%s] },\n" "$_evalign"
      printf '  {\n    files: [%s],\n' "$ESLINT_FILE_GLOBS"
      printf '    plugins: { playwright%s },\n' "$_sp_plg"
      cat <<'EOFCFG'
    languageOptions: { parser: tsParser, ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } },
EOFCFG
      printf "    rules: { ...(playwright.configs['flat/recommended'] ?? playwright.configs.recommended).rules%s },\n" "$_sp_rul"
      printf '  },\n%s\n];\n' "$_localspread"
    } > "$_cfg"
  else
    {
      printf "import cypress from '%s';\n" "$_plugin_abs"
      printf "import mocha from '%s';\n" "$_mocha_abs"
      printf "import tsParser from '%s';\n" "$_parser_abs"
      printf '%s%s\n' "$_sp_imp" "$_localimport"
      cat <<'EOFCFG'
const cypressRules = (cypress.configs['flat/recommended'] ?? cypress.configs.recommended).rules;
EOFCFG
      printf "export default [\n  { ignores: ['**/node_modules/**','**/dist/**','**/build/**','**/coverage/**','**/*.min.js',%s] },\n" "$_evalign"
      printf '  {\n    files: [%s],\n' "$ESLINT_FILE_GLOBS"
      printf '    plugins: { cypress, mocha%s },\n' "$_sp_plg"
      cat <<'EOFCFG'
    languageOptions: { parser: tsParser, ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } },
EOFCFG
      printf "    rules: { ...cypressRules, 'mocha/no-exclusive-tests': 'error'%s },\n" "$_sp_rul"
      printf '  },\n%s\n];\n' "$_localspread"
    } > "$_cfg"
  fi

  # ESLint loads the target project's config and plugins as executable code.
  # The explicit trust opt-in above authorizes that execution, but not wholesale
  # inheritance of the scanner's environment. Use a temporary home/config/cache
  # and a minimal command path. This reduces ambient credential discovery but
  # does not stop explicitly trusted project code from reading other accessible
  # filesystem paths or opening sockets.
  local _tool_path
  _tool_path="/usr/bin:/bin:/usr/sbin:/sbin"
  [[ -n "$NODE_BIN" ]] && _tool_path="${NODE_BIN%/*}:$_tool_path"
  mkdir -p "$_cfgd/home" "$_cfgd/tmp" "$_cfgd/xdg-config" "$_cfgd/xdg-cache"
  # The run step legitimately runs from the audited repository (ESLint resolves
  # its target files and the project's own flat config there), so it carries the
  # same npm pins as the download step. Nothing here installs anything, but a
  # trusted project config that shells out to npm must not reach the operator's
  # credentials, cache, or a repository-chosen registry either.
  prepare_pinned_npm_dirs "$_cfgd" || {
    printf '\n[ESLint] %s — could not create the private npm configuration for the ESLint run — skipping Tier 1; Tier 3 still runs, and Tier 2 runs only when available/enabled\n' "$label"
    rm -rf "$_cfgd"
    return 1
  }
  local -a _npm_pins=()
  local _npm_pin
  while IFS= read -r _npm_pin; do _npm_pins+=("$_npm_pin"); done < <(pinned_npm_config_env "$_cfgd")
  if [[ "${#_npm_pins[@]}" -eq 0 ]]; then
    printf '\n[ESLint] %s — pinned npm configuration unavailable for the ESLint run — skipping Tier 1; Tier 3 still runs, and Tier 2 runs only when available/enabled\n' "$label"
    rm -rf "$_cfgd"
    return 1
  fi
  local -a _eslint_env=(env -i
    "PATH=$_tool_path"
    "HOME=$_cfgd/home"
    "TMPDIR=$_cfgd/tmp"
    "TMP=$_cfgd/tmp"
    "TEMP=$_cfgd/tmp"
    "XDG_CONFIG_HOME=$_cfgd/xdg-config"
    "XDG_CACHE_HOME=$_cfgd/xdg-cache"
    "${_npm_pins[@]}"
    "CI=1"
    "NO_COLOR=1"
    "LANG=C"
    "LC_ALL=C"
  )
  [[ -n "${XDG_RUNTIME_DIR:-}" ]] && _eslint_env+=("XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR")

  # Tier 1 receives the same framework-proven source boundary as Tier 3. A
  # neighboring Vitest/Jest file is not admitted merely because ESLint can parse it.
  local -a _eslint_targets=()
  local _candidate
  while IFS= read -r _candidate; do
    file_in_e2e_scope "$_candidate" && _eslint_targets+=("$_candidate")
  done < <(
    scanner_rg --files --no-ignore "$ROOT" \
      --glob "$ALL_CODE_GLOB" \
      --glob '!**/node_modules/**' --glob '!**/.git/**' \
      --glob '!**/playwright-report/**' --glob '!**/cypress/reports/**' \
      --glob '!**/test-results/**' --glob '!**/dist/**' --glob '!**/build/**' \
      --glob '!**/.next/**' --glob '!**/out/**' --glob '!**/coverage/**' \
      --glob '!*.min.js' --glob '!*.min.ts' \
      ${EVAL_FIXTURE_EXCLUDES[@]+"${EVAL_FIXTURE_EXCLUDES[@]}"} 2>/dev/null
  )
  if [[ "${#_eslint_targets[@]}" -eq 0 ]]; then
    printf '\n[ESLint] %s — no framework-proven E2E files found — skipping Tier 1; Tier 3 still runs, and Tier 2 runs only when available/enabled\n' "$label"
    rm -rf "$_cfgd"
    return 1
  fi

  printf '\n[ESLint] %s — running eslint-plugin-%s (%s)\n' "$label" "$plugin" "$mode"
  local out
  # Watchdog: npx auto-download or eslint itself can hang on large/offline environments.
  # Run in background and kill after ESLINT_TIMEOUT_SECS (default 300) — macOS has no timeout(1).
  local _outf _statusf _limitf _pid _waited=0 _cap="$E2E_SMELL_ESLINT_TIMEOUT_SECS"
  allocate_temp _outf
  allocate_temp _statusf
  allocate_temp _limitf
  # Either the project's own ESLint binary or the pinned entry point already
  # materialized above — never a fresh npx invocation from the audited
  # repository, which would re-consult that repository's `.npmrc`.
  local -a _eslint_cmd
  if [[ "$mode" == "locally installed" ]]; then
    _eslint_cmd=("$eslint_bin")
  else
    _eslint_cmd=("$NODE_BIN" "$_eslint_js")
  fi
  ( cd "$PROJECT_ROOT_REAL" &&
    capture_bounded_command "$_outf" "$_statusf" "$_limitf" "" \
      "${_eslint_env[@]}" ESLINT_USE_FLAT_CONFIG=true \
      "${_eslint_cmd[@]}" --no-error-on-unmatched-pattern -c "$_cfg" \
      "${_eslint_targets[@]}" ) &
  _pid=$!
  while kill -0 "$_pid" 2>/dev/null; do
    # On macOS/Bash 3.2 an exited background child may remain visible to
    # `kill -0` as a zombie until `wait` reaps it. Break so a fast ESLint does
    # not sit in the watchdog loop until the timeout.
    _child_state=$(ps -p "$_pid" -o stat= 2>/dev/null || true)
    case "$_child_state" in (*Z*) break ;; esac
    sleep 1; _waited=$((_waited + 1))
    if [[ "$_waited" -ge "$_cap" ]]; then
      # Kill the descendant tree, not just the subshell: npx -> node children survive a
      # bare kill on the subshell PID (no process-group cascade on macOS). Two-level
      # pgrep walk covers subshell -> npx -> eslint/node; deeper orphans are unlikely
      # and exit on their own once stdout/stderr targets vanish.
      local _kid _gkid
      for _kid in $(pgrep -P "$_pid" 2>/dev/null); do
        for _gkid in $(pgrep -P "$_kid" 2>/dev/null); do kill -9 "$_gkid" 2>/dev/null; done
        kill -9 "$_kid" 2>/dev/null
      done
      kill -9 "$_pid" 2>/dev/null
      printf '  [watchdog] eslint exceeded %ss — killed; Tier 3 still runs, and Tier 2 runs only when available/enabled\n' "$_cap"
      rm -f "$_outf" "$_statusf" "$_limitf"; rm -rf "$_cfgd"
      return 1
    fi
  done
  wait "$_pid" 2>/dev/null
  local _capture_rc=$? _rc=2 _head_rc=2 _filter_rc=2 _limit_kind=""
  if [[ -s "$_statusf" ]]; then
    read -r _rc _head_rc _filter_rc < "$_statusf"
  fi
  [[ -s "$_limitf" ]] && _limit_kind=$(tail -1 "$_limitf")
  if [[ -n "$_limit_kind" ]]; then
    printf 'INCOMPLETE: Tier 1 %s exceeded E2E_SMELL_MAX_RULE_%s=%s while streaming ESLint output; Tier 1 emitted no findings and no final Summary was emitted.\n' \
      "$label" \
      "$([[ "$_limit_kind" == lines ]] && printf HITS || printf BYTES)" \
      "$([[ "$_limit_kind" == lines ]] && printf '%s' "$E2E_SMELL_MAX_RULE_HITS" || printf '%s' "$E2E_SMELL_MAX_RULE_BYTES")" >&2
    rm -f "$_outf" "$_statusf" "$_limitf"; rm -rf "$_cfgd"
    exit 2
  fi
  if [[ "$_capture_rc" -ne 0 || "$_head_rc" -ne 0 || "$_filter_rc" -ne 0 ]]; then
    printf 'error: Tier 1 output limiter failed for %s (capture %s, head %s, filter %s)\n' \
      "$label" "$_capture_rc" "$_head_rc" "$_filter_rc" >&2
    rm -f "$_outf" "$_statusf" "$_limitf"; rm -rf "$_cfgd"
    exit 2
  fi
  out=$(cat "$_outf")
  rm -f "$_outf" "$_statusf" "$_limitf"; rm -rf "$_cfgd"

  # EXIT-CODE GATE (the silent-always-pass bug class this skill exists to catch):
  # eslint exits 0 = clean, 1 = findings; anything else (2 = config/usage error, 127 = not
  # found, npx/network crash...) means Tier 1 did NOT cover the patterns — never claim it did,
  # or Tier 2/3 would silently skip #7/#9/#15/#16 (#7/#9b for Cypress).
  if [[ "$_rc" -ge 2 ]]; then
    printf '  [ESLint] crashed or unusable (exit %s) — Tier 3 still runs, and Tier 2 runs only when available/enabled\n' "$_rc"
    printf '%s\n' "$out" | sanitize_evidence | head -5 | sed 's/^/    /'
    return 1
  fi
  # Native match, not `printf | grep -q`: under `pipefail` grep exits on its
  # first hit, printf takes SIGPIPE on output larger than the pipe buffer, and
  # the pipeline returns 141. That reads as "no match", so a long eslint run
  # that exits 0 with warnings would print "no findings" and drop every Tier 1
  # hit — the silent-always-pass class this gate exists to prevent.
  if [[ "$_rc" -eq 1 || "$out" == *error* || "$out" == *warning* ]]; then
    printf '%s\n' "$out" | sanitize_evidence | sed 's/^/  /' | head -100
  else
    printf '  no findings\n'
  fi
  # Tier-1 findings must reach the exit gate. Tier 2/3 still run independently
  # and deduplicate only the same file/line/rule-class fingerprint.
  # Map covered eslint rule IDs onto the same counters Tier 3 uses:
  #   P0: no-focused-test (#7), mocha no-exclusive-tests (#7 Cypress),
  #       no-silent-pass (#4f companion plugin)
  #   P1: missing-playwright-await (#15/#16), no-wait-for-timeout (#9),
  #       no-unnecessary-waiting (#9b)
  # Count Tier-1 hits, routing JUSTIFIED P0 to external-review candidates while
  # suppressing JUSTIFIED P1 (parity with Tier 2/3). Walk the eslint
  # stylish output tracking the current file header; #7 rules (no-focused-test / mocha
  # no-exclusive-tests) are NEVER exempt, per the no-JUSTIFIED-for-#7 contract.
  local _t1_p0=0 _t1_p1=0 _curf="" _eln _elno _efp _etrim _dclass=""
  while IFS= read -r _eln; do
    # File header line: a path on its own (absolute, or relative with a dot), not a hit/summary.
    if [[ "$_eln" == /* || ( -n "$_eln" && "$_eln" != " "* && "$_eln" == *.* && "$_eln" != *"problem"* && "$_eln" != *"✖"* && "$_eln" != *"potentially fixable"* ) ]]; then
      _curf="$_eln"; continue
    fi
    # Hit line: "  <line>:<col>  <severity> ... <rule>". Extract the line number with parameter
    # expansion — bash 3.2 (macOS default) does NOT populate BASH_REMATCH capture groups, so a
    # `=~ (…)` capture silently yields an empty line number and suppression never fires.
    _body="${_eln#"${_eln%%[![:space:]]*}"}"        # strip leading whitespace
    case "$_body" in
      *:*)
        _elno="${_body%%:*}"                        # field before the first ':' — the line number
        case "$_elno" in
          ''|*[!0-9]*) ;;                           # not a pure number -> not an eslint hit line
          *)
            _etrim="${_eln%"${_eln##*[![:space:]]}"}"   # strip trailing whitespace; rule is the suffix
            _efp="$_curf"; [[ -f "$_efp" ]] || _efp="$PROJECT_ROOT_REAL/$_curf"
            case "$_etrim" in
              */no-focused-test|*/no-exclusive-tests)
                _t1_p0=$((_t1_p0 + 1)); _dclass='focused-test' ;;    # #7 — never JUSTIFIED-exempt
              */no-silent-pass|*/no-unnecessary-assertions)
                if _line_is_justified "$_efp" "$_elno"; then
                  record_justified_suppression P0 '#4f' "$_efp" "$_elno"
                else
                  _t1_p0=$((_t1_p0 + 1))
                  case "$_etrim" in
                    */no-silent-pass|*/no-unnecessary-assertions) _dclass='silent-pass' ;;
                  esac
                fi ;;
              */missing-playwright-await|*/no-wait-for-timeout|*/no-unnecessary-waiting)
                if _line_is_justified "$_efp" "$_elno"; then
                  record_justified_suppression P1 '#lint-p1' "$_efp" "$_elno"
                else
                  _t1_p1=$((_t1_p1 + 1))
                  case "$_etrim" in
                    */missing-playwright-await) _dclass='missing-playwright-await' ;;
                    */no-wait-for-timeout) _dclass='playwright-wait' ;;
                    *) _dclass='cypress-wait' ;;
                  esac
                fi ;;
            esac
            if [[ -n "$_dclass" ]]; then
              _efp=$(absolute_hit_file "$_efp" 2>/dev/null || true)
              [[ -n "$_efp" ]] && printf '%s|%s|%s\n' "$_efp" "$_elno" "$_dclass" >> "$STRUCTURAL_HITS_FILE"
              _dclass=""
            fi ;;
        esac ;;
    esac
  done <<< "$out"
  if [[ "$_t1_p0" -gt 0 ]]; then p0_hits=$((p0_hits + _t1_p0)); total_hits=$((total_hits + _t1_p0)); fi
  if [[ "$_t1_p1" -gt 0 ]]; then p1_hits=$((p1_hits + _t1_p1)); total_hits=$((total_hits + _t1_p1)); fi
  eslint_ran=1
}

# Tell the user which tier obeys their config and which does not. The tiers answer different
# questions, so they take different orders from the project's ESLint setup:
#   Tier 1 is THEIR linter. A flat config is layered on top of our baseline, so a deliberate
#          `'playwright/no-focused-test': 'off'` genuinely silences that rule here.
#   Tier 2/3 are OUR reviewer. They ask "can this test fail?", not "does your lint policy
#          allow it?", so they keep reporting regardless — that is what makes the finding
#          count reproducible across hosts and independent of local policy.
# Legacy .eslintrc cannot be imported from an ESM flat config, so those projects keep the old
# recommended-only behavior and are told so explicitly rather than left to assume otherwise.
_flatcfg=""
for _c in eslint.config.mjs eslint.config.js eslint.config.cjs; do
  [[ -f "$PROJECT_ROOT_REAL/$_c" ]] && { _flatcfg="$_c"; break; }
done
if [[ "$E2E_SMELL_ALLOW_PROJECT_ESLINT" == "1" && -n "$_flatcfg" ]]; then
  printf '\n[note] Layering your %s over our Tier 1 baseline — rules you set to `off` there are not reported by Tier 1. Tier 2 (ast-grep) and Tier 3 (regex) still evaluate independently: they ask whether a test can fail, not whether your lint policy allows it, so a pattern you disabled can still surface there. Set E2E_SMELL_ALLOW_PROJECT_ESLINT=0 to disable Tier 1.\n' "$_flatcfg"
elif [[ "$E2E_SMELL_ALLOW_PROJECT_ESLINT" == "1" && ( -f "$PROJECT_ROOT_REAL/.eslintrc" || -f "$PROJECT_ROOT_REAL/.eslintrc.json" || -f "$PROJECT_ROOT_REAL/.eslintrc.js" || -f "$PROJECT_ROOT_REAL/.eslintrc.cjs" || -f "$PROJECT_ROOT_REAL/.eslintrc.yml" || -f "$PROJECT_ROOT_REAL/.eslintrc.yaml" ) ]]; then
  printf '\n[note] Project uses a legacy .eslintrc, which an ESM flat config cannot import — Tier 1 runs the `recommended` preset instead, so rules you disabled there are NOT honored here. If you already lint with eslint-plugin-{playwright,cypress} in CI/IDE, set E2E_SMELL_ALLOW_PROJECT_ESLINT=0 to skip Tier 1 and let your pipeline own it (Tier 2 + Tier 3 still run).\n'
fi

# Detect each framework via actual imports, then opt into eslint-plugin-* if installed.
validate_candidate_manifest
pw_imports_found=0
cy_imports_found=0
if scanner_rg -lq --no-ignore '@playwright/test' "$ROOT" --glob '!**/node_modules/**' 2>/dev/null; then
  pw_imports_found=1
  try_eslint playwright Playwright
fi
if scanner_rg -lq --no-ignore "from\s+['\"]cypress['\"]|[^A-Za-z0-9_]cy\.(visit|get|contains|request|intercept|session|origin|task|wait|fixture)\(" "$ROOT" --glob '!**/node_modules/**' --glob "$ALL_CODE_GLOB" 2>/dev/null; then
  cy_imports_found=1
  try_eslint cypress Cypress
fi
abort_on_rg_error

if [[ "$eslint_ran" -eq 0 ]]; then
  # Single-cause skip report. The old message OR'ed three causes in one line, which made
  # field failures undiagnosable (the real field cause was an eslint crash: missing
  # `typescript` peer dep in the npx env — see the npx_args comment in try_eslint).
  if [[ "$E2E_SMELL_ALLOW_PROJECT_ESLINT" != "1" ]]; then
    printf '\n[ESLint] Tier 1 disabled by default because local ESLint config/plugins execute project code. Set E2E_SMELL_ALLOW_PROJECT_ESLINT=1 to opt in; this is not a sandbox. Tier 3 still runs; Tier 2 runs only when available/enabled.\n'
  elif [[ "$pw_imports_found" -eq 0 && "$cy_imports_found" -eq 0 ]]; then
    printf '\n[ESLint] Tier 1 not run — no Playwright/Cypress imports detected under %s.\n' "$ROOT"
  elif [[ -z "$NPX_BIN" ]]; then
    printf '\n[ESLint] Tier 1 not run — no trusted npx executable was found.\n'
  elif [[ "${E2E_SMELL_NO_ESLINT_DOWNLOAD:-}" == "1" ]]; then
    printf '\n[ESLint] Tier 1 not run — E2E_SMELL_NO_ESLINT_DOWNLOAD=1 is set and no locally installed plugin was found.\n'
  else
    printf '\n[ESLint] Tier 1 not run — imports were detected but the eslint run failed; the [ESLint] line above names the exact failure (resolve error, crash exit code, or watchdog timeout).\n'
  fi
fi

# Tier 2: ast-grep — Tree-sitter AST patterns. Lower FP rate than regex on the patterns it covers
# (#15, #4ce-state-bool/text/count, #4f). An inherited PATH is never used to
# select it: use a deterministic install location, E2E_SMELL_AST_GREP_BIN, or
# the explicitly enabled trusted npx fallback.
# Set E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 to disable the npx fallback (matches eslint tier's escape hatch).
# Set E2E_SMELL_DISABLE_AST_GREP=1 to disable Tier 2 entirely, including any
# deterministic binary already present on the host. This is for portability
# contracts that deliberately must not depend on ambient ast-grep installs.
# Use the symlink-resolved directory: both the Tier 2 branch and its "not run"
# notice gate on `-d "$ASTGREP_RULES_DIR"`, so a wrong path deleted the tier
# without printing anything.
ASTGREP_RULES_DIR="${SCANNER_DIR_REAL:-$(cd "$(dirname "$0")" && pwd)}/ast-grep-rules"
ASTGREP_JSON_PARSER="${SCANNER_DIR_REAL:-$(cd "$(dirname "$0")" && pwd)}/parse-ast-grep-json.py"
AST_GREP=""
AST_GREP_CMD=()
TIER2_INFRA_FAILURE=0
TIER2_INFRA_DETAIL=""
validate_candidate_manifest
_ast_candidate=""
if [[ "$E2E_SMELL_DISABLE_AST_GREP" != "1" ]]; then
# E2E_SMELL_IGNORE_HOST_AST_GREP=1 skips the deterministic host lookup while leaving the pinned
# npx fallback available. Harness-internal on purpose and deliberately absent from the README
# knobs: its only job is to let the test suite exercise the npx tier on a machine that happens
# to have ast-grep installed. Users wanting no ambient binary want E2E_SMELL_DISABLE_AST_GREP. E2E_SMELL_DISABLE_AST_GREP=1 kills the whole tier and cannot express
# this, which left the npx tier exercised only on machines that happen to lack ast-grep.
if [[ "$E2E_SMELL_IGNORE_HOST_AST_GREP" == "1" ]]; then
  if [[ -n "${E2E_SMELL_AST_GREP_BIN:-}" ]]; then
    printf 'error: E2E_SMELL_IGNORE_HOST_AST_GREP=1 conflicts with E2E_SMELL_AST_GREP_BIN; unset one\n' >&2
    exit 2
  fi
  _ast_candidate=""
else
_ast_candidate=$(bind_optional_tool E2E_SMELL_AST_GREP_BIN "${E2E_SMELL_AST_GREP_BIN:-}" \
  /opt/homebrew/bin/ast-grep /usr/local/bin/ast-grep /usr/bin/ast-grep \
  /opt/homebrew/bin/sg /usr/local/bin/sg /usr/bin/sg)
fi
if [[ -n "$_ast_candidate" ]]; then
  AST_GREP="$_ast_candidate"
  AST_GREP_CMD=("$_ast_candidate")
elif [[ "${E2E_SMELL_NO_AST_GREP_DOWNLOAD:-}" == "1" ]]; then AST_GREP=""
elif [[ -n "$NPX_BIN" && -n "$NODE_BIN" ]]; then
  AST_GREP="npx --yes --ignore-scripts --package @ast-grep/cli@0.39.7 ast-grep"
  # Tier 2 downloads through the SAME private pinned npm environment as Tier 1
  # (see setup_pinned_npm_env / run_pinned_npx). It used to build a second,
  # hand-rolled environment here, and that copy drifted: it pointed BOTH
  # npm_config_userconfig and npm_config_globalconfig at /dev/null, which npm >= 9
  # rejects with "double-loading config /dev/null as global, previously loaded as
  # user" before it resolves any config at all. One generator for both tiers is
  # what makes that class of drift impossible to reintroduce.
  if ! setup_pinned_npm_env; then
    printf 'error: unable to create the private pinned npm environment for ast-grep\n' >&2
    exit 2
  fi
  AST_GREP_CMD=(run_ast_grep_npx)
else AST_GREP=""; fi
fi

run_ast_grep_npx() {
  # Match the ESLint download boundary: exact pin, no lifecycle scripts, and a
  # private pinned npm environment that ignores the audited repository's .npmrc.
  run_pinned_npx --yes --ignore-scripts \
    --package '@ast-grep/cli@0.39.7' ast-grep "$@"
}

record_tier2_infrastructure_failure() {
  TIER2_INFRA_FAILURE=1
  TIER2_INFRA_DETAIL="$1"
}

if [[ "${#AST_GREP_CMD[@]}" -gt 0 && -d "$ASTGREP_RULES_DIR" &&
      -n "$PYTHON3_BIN" && -f "$ASTGREP_JSON_PARSER" ]]; then
  printf '\n--- Tier 2: AST-grep checks (Tree-sitter; covers FP-prone patterns more accurately) ---\n'
  ast_total=0
  _ast_glob_args=(
    --globs '!**/node_modules/**'
    --globs '!**/.git/**'
    --globs '!**/playwright-report/**'
    --globs '!**/cypress/reports/**'
    --globs '!**/test-results/**'
    --globs '!**/dist/**'
    --globs '!**/build/**'
    --globs '!**/.next/**'
    --globs '!**/out/**'
    --globs '!**/coverage/**'
    --globs '!**/*.min.js'
    --globs '!**/*.min.ts'
  )
  if [[ "${#EVAL_FIXTURE_AST_GREP_EXCLUDES[@]}" -gt 0 ]]; then
    _ast_glob_args+=("${EVAL_FIXTURE_AST_GREP_EXCLUDES[@]}")
  fi
  for rule in "$ASTGREP_RULES_DIR"/sg-*.yml; do
    [[ "$(basename "$rule")" == sg-postfix-* ]] && continue  # postfix rules are for verify-fixes.sh
    rule_name=$(basename "$rule" .yml)
    pattern_id=$(get_pattern_for_ast_rule "$rule_name")
    allocate_temp _ast_capture
    allocate_temp _ast_error
    allocate_temp _ast_limit
    allocate_temp _ast_stream_err
    capture_bounded_command "$_ast_capture" "$_ast_error" "$_ast_limit" "$_ast_stream_err" \
      "${AST_GREP_CMD[@]}" scan \
      --rule "$rule" \
      --json=stream \
      --no-ignore hidden \
      --no-ignore dot \
      --no-ignore exclude \
      --no-ignore global \
      --no-ignore parent \
      --no-ignore vcs \
      "${_ast_glob_args[@]}" \
      "$ROOT"
    _ast_rc="$BOUNDED_COMMAND_RC"
    # A nonzero exit with an EMPTY capture is never ast-grep reporting: every
    # bundled sg-*.yml scan rule is `severity: error`, and ast-grep only exits 1
    # once it has printed those error-severity findings, so a genuine exit 1
    # always leaves JSON records on the stream. Nothing captured means the tool
    # never started — npm config abort, missing binary, sandbox denial. Without
    # this check that case parses as zero locations and Tier 2 prints a clean
    # "0 hit(s)" for a tier that never ran, which is a silent always-pass.
    # Checked before the empty-capture guard: a crash reports on stderr, and stderr is no longer
    # merged into the capture, so an empty capture no longer distinguishes "never started" from
    # "started and crashed loudly". The exit code does.
    if [[ "$_ast_rc" -gt 1 && "$_ast_rc" -ne 141 ]]; then
      printf 'error: Tier 2 ast-grep failed for %s (exit %s)\n' "$rule_name" "$_ast_rc" >&2
      sed -n '1,80p' "$_ast_stream_err" | sanitize_evidence >&2
      sed -n '1,80p' "$_ast_capture" | sanitize_evidence >&2
      rm -f "$_ast_capture" "$_ast_error" "$_ast_limit" "$_ast_stream_err"
      record_tier2_infrastructure_failure \
        "ast-grep failed for $rule_name (exit $_ast_rc)"
      break
    fi
    if [[ "$_ast_rc" -ne 0 && ! -s "$_ast_capture" ]]; then
      printf 'error: Tier 2 ast-grep produced no output for %s and exited %s; the tier did not run\n' \
        "$rule_name" "$_ast_rc" >&2
      sed -n '1,20p' "$_ast_stream_err" | sanitize_evidence >&2
      rm -f "$_ast_capture" "$_ast_error" "$_ast_limit" "$_ast_stream_err"
      record_tier2_infrastructure_failure \
        "ast-grep produced no output for $rule_name (exit $_ast_rc)"
      break
    fi
    if [[ -n "$BOUNDED_LIMIT_KIND" ]]; then
      printf 'INCOMPLETE: Tier 2 %s exceeded E2E_SMELL_MAX_RULE_%s=%s; this rule emitted no findings and no final Summary was emitted. Narrow the scan root or raise the bounded limit.\n' \
        "$rule_name" \
        "$([[ "$BOUNDED_LIMIT_KIND" == hits ]] && printf HITS || printf BYTES)" \
        "$([[ "$BOUNDED_LIMIT_KIND" == hits ]] && printf '%s' "$E2E_SMELL_MAX_RULE_HITS" || printf '%s' "$E2E_SMELL_MAX_RULE_BYTES")" >&2
      rm -f "$_ast_capture" "$_ast_error" "$_ast_limit" "$_ast_stream_err"
      record_tier2_infrastructure_failure \
        "$rule_name exceeded the configured $BOUNDED_LIMIT_KIND limit"
      break
    fi
    if [[ "$_ast_rc" -eq 141 || "$BOUNDED_HEAD_RC" -ne 0 || "$BOUNDED_FILTER_RC" -ne 0 ]]; then
      printf 'error: Tier 2 output limiter failed for %s (ast-grep %s, head %s, filter %s)\n' \
        "$rule_name" "$_ast_rc" "$BOUNDED_HEAD_RC" "$BOUNDED_FILTER_RC" >&2
      rm -f "$_ast_capture" "$_ast_error" "$_ast_limit" "$_ast_stream_err"
      record_tier2_infrastructure_failure \
        "output limiter failed for $rule_name"
      break
    fi
    allocate_temp _ast_locations
    allocate_temp _ast_parse_error
    if ! "$PYTHON3_BIN" -I "$ASTGREP_JSON_PARSER" \
      <"$_ast_capture" >"$_ast_locations" 2>"$_ast_parse_error"; then
      printf 'error: Tier 2 ast-grep emitted an invalid JSON stream for %s\n' \
        "$rule_name" >&2
      sed -n '1,20p' "$_ast_parse_error" | sanitize_evidence >&2
      sed -n '1,20p' "$_ast_stream_err" | sanitize_evidence >&2
      rm -f "$_ast_capture" "$_ast_error" "$_ast_limit" "$_ast_stream_err" \
        "$_ast_locations" "$_ast_parse_error"
      record_tier2_infrastructure_failure \
        "invalid JSON stream for $rule_name"
      break
    fi
    # Exit 0 with diagnostics still means reduced coverage (an unreadable file, a partially
    # ignored rule). Merged stderr used to collapse the tier loudly; now that it is separated,
    # report it rather than counting hits over a silently narrowed scan.
    if [[ -s "$_ast_stream_err" ]]; then
      printf 'note: Tier 2 ast-grep wrote diagnostics for %s while exiting %s\n' \
        "$rule_name" "$_ast_rc" >&2
      sed -n '1,20p' "$_ast_stream_err" | sanitize_evidence >&2
    fi
    rm -f "$_ast_capture" "$_ast_error" "$_ast_limit" "$_ast_stream_err" "$_ast_parse_error"
    # Honor `// JUSTIFIED:` — suppress P1/P2 hits and retain P0 as external-review
    # candidates (parity with Tier 1/3). The bundled parser validates ast-grep's JSON-stream
    # schema and emits tab-separated file, one-based line, and one-based column.
    ast_count=0
    ast_triage_count=0
    allocate_temp _ast_keep
    allocate_temp _ast_triage_keep
    while IFS=$'\t' read -r _afile _aln _acol; do
      [[ -n "$_afile" && -n "$_aln" && -n "$_acol" ]] || {
        printf 'error: Tier 2 parser emitted an invalid location row for %s\n' \
          "$rule_name" >&2
        rm -f "$_ast_locations" "$_ast_keep" "$_ast_triage_keep"
        record_tier2_infrastructure_failure \
          "invalid parsed location for $rule_name"
        break
      }
      _resolved=$(absolute_hit_file "$_afile" 2>/dev/null || true)
      [[ -n "$_resolved" ]] || continue
      file_is_scanner_excluded "$_resolved" && continue
      file_in_e2e_scope "$_resolved" || continue
      if [[ "$pattern_id" == '#4f' ]]; then
        if ast_expect_binding_shadowed_at "$_resolved" "$_aln"; then
          continue
        fi
        if ! ast_locator_truthiness_confirmed_at "$_resolved" "$_aln"; then
          ast_triage_count=$((ast_triage_count + 1))
          printf '%s:%s:%s\n' "$_resolved" "$_aln" "$_acol" >> "$_ast_triage_keep"
          continue
        fi
      fi
      if [[ "$pattern_id" == '#15' ]] &&
        expect_promise_nonfloating_at "$_resolved" "$_aln"; then
        continue
      fi
      if [[ "$pattern_id" == '#15' ]] &&
        ast_expect_binding_shadowed_at "$_resolved" "$_aln"; then
        continue
      fi
      if [[ "$pattern_id" == '#15' ]] &&
        ! ast_playwright_expect_proven_at "$_resolved" "$_aln"; then
        ast_triage_count=$((ast_triage_count + 1))
        printf '%s:%s:%s\n' "$_resolved" "$_aln" "$_acol" >> "$_ast_triage_keep"
        continue
      fi
      if _line_is_justified "$_resolved" "$_aln"; then
        case "$pattern_id" in
          '#4f') record_justified_suppression P0 "$pattern_id" "$_resolved" "$_aln" ;;
          *) record_justified_suppression P1 "$pattern_id" "$_resolved" "$_aln" ;;
        esac
        continue
      fi
      _dclass=$(dedupe_class_for_pattern "$pattern_id")
      if [[ -n "$_dclass" ]] &&
        grep -qFx -e "$_resolved|$_aln|$_dclass" "$STRUCTURAL_HITS_FILE" 2>/dev/null; then
        continue
      fi
      ast_count=$((ast_count + 1))
      printf '%s:%s:%s\n' "$_resolved" "$_aln" "$_acol" >> "$_ast_keep"
      [[ -n "$_dclass" ]] &&
        printf '%s|%s|%s\n' "$_resolved" "$_aln" "$_dclass" >> "$STRUCTURAL_HITS_FILE"
    done < "$_ast_locations"
    rm -f "$_ast_locations"
    if [[ "$TIER2_INFRA_FAILURE" -eq 1 ]]; then
      rm -f "$_ast_keep" "$_ast_triage_keep"
      break
    fi
    abort_on_rg_error
    if [[ "$ast_count" -gt 0 ]]; then
      _ast_label='[AST]'
      [[ "$pattern_id" == '#4c-4e' ]] && _ast_label='[AST][LLM-TRIAGE]'
      printf '\n%s %s (%s hit%s)\n' "$_ast_label" "$rule_name" "$ast_count" "$([[ "$ast_count" == "1" ]] && printf '' || printf 's')"
      sed 's/^/  /' "$_ast_keep"
      ast_total=$((ast_total + ast_count))
      case "$pattern_id" in
        '#4f') ast_p0_hits=$((ast_p0_hits + ast_count)) ;;
        '#4c-4e')
          llm_triage_hits=$((llm_triage_hits + ast_count))
          ;;
        *) ast_p1_hits=$((ast_p1_hits + ast_count)) ;;
      esac
      hit_pattern_ids="$hit_pattern_ids $pattern_id"
    fi
    if [[ "$ast_triage_count" -gt 0 ]]; then
      printf '\n[AST][LLM-TRIAGE] %s (%s hit%s; Playwright expect provenance unproven)\n' \
        "$rule_name" "$ast_triage_count" "$([[ "$ast_triage_count" == "1" ]] && printf '' || printf 's')"
      sed 's/^/  /' "$_ast_triage_keep"
      ast_total=$((ast_total + ast_triage_count))
      llm_triage_hits=$((llm_triage_hits + ast_triage_count))
      hit_pattern_ids="$hit_pattern_ids $pattern_id"
    fi
    rm -f "$_ast_keep"
    rm -f "$_ast_triage_keep"
  done
  printf '\n  ast-grep total: %s hit(s)\n' "$ast_total"
elif [[ "${#AST_GREP_CMD[@]}" -gt 0 && -d "$ASTGREP_RULES_DIR" ]]; then
  printf '\n[ast-grep] Tier 2 not run — deterministic Python 3 JSON validation is unavailable.\n'
fi

validate_candidate_manifest
printf '\n--- Tier 3: Bundled regex checks (universal fallback for grep-detectable patterns and gaps eslint/ast-grep miss) ---\n'

# Phase-0 file scope filter (Tier 3): pattern checks only apply to files that are actually
# E2E surface — basename contains `.cy.`, path has a `cypress/` component, the file imports
# @playwright/test, or it references cypress (import/require or `cy.<cmd>(` usage). Kills
# backend/unit-suite FPs that share the *.test.* suffix (observed in the field: Knex
# `.first()` flagged as #10a and an `import type ... secret` line flagged as #14 in backend
# Vitest files). Skipped files are counted and reported before the Summary — never silently.
allocate_temp SCOPE_STATE_DIR -d
: > "$SCOPE_STATE_DIR/in"
: > "$SCOPE_STATE_DIR/out"

file_in_cypress_scope() {
  local f="$1"
  # A conventional .cy.* basename is not stronger than executable provenance:
  # generators and migrations sometimes leave Vitest/Jest/Mocha modules under
  # that name. A known foreign runner therefore wins unless the same file also
  # imports Cypress or executes a Cypress command. Apply this override before
  # basename/path admission so all Cypress-only rules share the same boundary.
  if source_has_foreign_test_module_reference "$f"; then
    source_has_cypress_module_reference "$f" && return 0
    source_has_cypress_runtime_reference "$f" && return 0
    return 1
  fi
  case "$(basename "$f")" in
    *.cy.*) return 0 ;;
  esac
  case "/$f/" in
    */cypress/*) return 0 ;;
  esac
  source_has_cypress_module_reference "$f" && return 0
  source_has_cypress_runtime_reference "$f"
}

# Cached IN/OUT lookup (exact-line grep — space-safe filenames; file appends survive the
# command-substitution subshells run_check calls this from).
scope_status() {
  local f="$1"
  if grep -qFx -e "$f" "$SCOPE_STATE_DIR/in" 2>/dev/null; then printf 'IN'; return 0; fi
  if grep -qFx -e "$f" "$SCOPE_STATE_DIR/out" 2>/dev/null; then printf 'OUT'; return 0; fi
  if file_in_e2e_scope "$f"; then
    printf '%s\n' "$f" >> "$SCOPE_STATE_DIR/in"; printf 'IN'
  else
    printf '%s\n' "$f" >> "$SCOPE_STATE_DIR/out"; printf 'OUT'
  fi
}

# #16 action calls are frequently formatted across several lines, so a regex
# anchored to the receiver line misses the action entirely. Start from the
# action line (the line users need in the report), then walk back through at
# most 12 physical lines to find the logical receiver. This is deliberately a
# bounded lexical sweep rather than a JavaScript parser: direct page.locator /
# page.getBy* chains enter the deterministic P1 output, while variable/POM chains
# remain LLM-triage candidates that Phase 2 traces to a Locator declaration.
missing_await_action_hit_matches() {
  local hit="$1" mode="$2" file rest line
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  awk -v target="$line" -v mode="$mode" '
    function trim(s) {
      sub(/^[[:space:]]+/, "", s)
      sub(/[[:space:]]+$/, "", s)
      return s
    }
    function executable_source(s,    out, i, c, nextc) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nextc = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nextc == "/") {
            lex_block = 0
            i++
          }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_escape = 0
          } else if (c == "\\") {
            lex_escape = 1
          } else if (c == lex_quote) {
            lex_quote = ""
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          continue
        }
        if (c == "/" && nextc == "*") {
          lex_block = 1
          i++
          continue
        }
        if (c == "/" && nextc == "/") break
        out = out c
      }
      return out
    }
    function is_awaited_or_returned(s) {
      s = trim(s)
      return s ~ /^(await|return)([[:space:]]|$)/
    }
    {
      # Scan from the start of the file so a block comment or quoted/template
      # string opened before the bounded receiver window still has correct
      # lexical state. Only the final 12-line receiver walk is retained.
      source[NR] = executable_source($0)
    }
    END {
      first = target - 12
      if (first < 1) first = 1
      action = "(click|dblclick|tap|fill|clear|type|press|pressSequentially|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|blur|dragTo|drop|dispatchEvent|scrollIntoViewIfNeeded|selectText|screenshot|waitFor)"
      for (start = target; start >= first; start--) {
        origin = trim(source[start])
        if (origin == "" || origin ~ /^\/\// || origin ~ /^\*/) continue
        if (start < target && origin ~ /;[[:space:]]*$/) exit 1
        # Same-line Promise aggregates otherwise hide the receiver behind
        # `await/return/assignment Promise.*([`. Classification must retain
        # the action and let the later aggregate-observation filter decide
        # whether it is genuinely consumed.
        sub(/^.*Promise\.(all|race|allSettled|any)[[:space:]]*\([[:space:]]*\[/, "", origin)

        deferred_origin = origin ~ /^(void[[:space:]]+|((export[[:space:]]+)?(const|let|var)[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*([[:space:]]*:[^=]+)?[[:space:]]*=[[:space:]]*))/
        if (deferred_origin) {
          sub(/^void[[:space:]]+/, "", origin)
          sub(/^(export[[:space:]]+)?(const|let|var)[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*([[:space:]]*:[^=]+)?[[:space:]]*=[[:space:]]*/, "", origin)
        }
        direct_origin = origin ~ /^(await[[:space:]]+|return[[:space:]]+)?page([[:space:]]*$|[[:space:]]*\.[[:space:]]*(locator|getBy[A-Za-z]+)[[:space:]]*\()/
        variable_origin = origin ~ /^(await[[:space:]]+|return[[:space:]]+)?(this[[:space:]]*\.[[:space:]]*)?[A-Za-z_$][A-Za-z0-9_$]*([[:space:]]*\.[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*)*[[:space:]]*(\.|$)/
        if (!direct_origin && !variable_origin) continue

        chain = origin
        for (i = start + 1; i <= target; i++) chain = chain " " trim(source[i])
        gsub(/[[:space:]]+/, " ", chain)
        chain = trim(chain)
        if (is_awaited_or_returned(chain)) exit 1

        direct_chain = (chain ~ ("^page[[:space:]]*\\.[[:space:]]*(locator|getBy[A-Za-z]+)[[:space:]]*\\(.*\\)[[:space:]]*\\.[[:space:]]*" action "[[:space:]]*\\(") ||
                        chain ~ "^page[[:space:]]*\\.[[:space:]]*(goto|reload|waitForURL|waitForNavigation|goBack|goForward)[[:space:]]*\\(")
        if (mode == "deferred" && deferred_origin &&
            (direct_chain || chain ~ ("^(this[[:space:]]*\\.[[:space:]]*)?[A-Za-z_$][A-Za-z0-9_$]*([[:space:]]*\\.[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*)*[[:space:]]*\\.[[:space:]]*" action "[[:space:]]*\\("))) exit 0
        if (deferred_origin) exit 1
        if (mode == "direct" && direct_chain) exit 0
        if (mode == "variable" && !direct_chain &&
            chain ~ ("^(this[[:space:]]*\\.[[:space:]]*)?[A-Za-z_$][A-Za-z0-9_$]*([[:space:]]*\\.[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*)*[[:space:]]*\\.[[:space:]]*" action "[[:space:]]*\\(")) exit 0
        exit 1
      }
      exit 1
    }
  ' "$file" >/dev/null 2>&1
}

# Classify a boolean-state line using only the bounded source prefix that can
# consume it. This keeps multiline control-flow/argument/assignment uses out of
# #8b without hiding unrelated discarded statements later in the same block.
# mode=consumed accepts if/while/return/assignment/ternary/argument contexts;
# mode=if accepts only an open multiline `if (` condition for #5a triage.
boolean_state_hit_context() {
  local hit="$1" mode="$2" file rest line
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  awk -v target="$line" -v mode="$mode" '
    function trim(s) {
      sub(/^[[:space:]]+/, "", s)
      sub(/[[:space:]]+$/, "", s)
      return s
    }
    NR >= target - 8 && NR < target { source[NR] = $0 }
    END {
      prefix = ""
      first = target - 8
      if (first < 1) first = 1
      for (i = target - 1; i >= first; i--) {
        line = source[i]
        sub(/\/\/.*/, "", line)
        line = trim(line)
        if (line == "") continue
        if (line ~ /[;{}][[:space:]]*$/) break
        prefix = line " " prefix
        if (line ~ /[=?:,(][[:space:]]*$/ ||
            line ~ /(^|[^A-Za-z0-9_$])(if|while|return)[[:space:]]*(\(|$)/) break
      }
      prefix = trim(prefix)
      if (mode == "if") {
        if (prefix ~ /(^|[^A-Za-z0-9_$])if[[:space:]]*\([^)]*$/) exit 0
        exit 1
      }
      if (prefix ~ /(^|[^A-Za-z0-9_$])(if|while)[[:space:]]*\([^)]*$/ ||
          prefix ~ /(^|[^A-Za-z0-9_$])return([[:space:]]|\()/ ||
          prefix ~ /[=?:,(][[:space:]]*$/) exit 0
      exit 1
    }
  ' "$file" >/dev/null 2>&1
}

# Return only executable source for one hit line. Strings are replaced with
# inert tokens that preserve credential words but not punctuation, so source
# text such as "test.only(...)" cannot masquerade as a call. Block-comment and
# quote state is carried from line 1 to the target.
lexical_target_line() {
  local hit="$1" file rest line
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  awk -v target="$line" '
    function inert_string(value,    token) {
      token = value
      gsub(/[^A-Za-z0-9_$]+/, "_", token)
      return "__STR_" token "__"
    }
    function executable_source(s,    out, value, i, c, nchar) {
      out = ""
      value = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") {
            lex_block = 0
            i++
          }
          continue
        }
        if (lex_regex) {
          if (lex_escape) {
            lex_escape = 0
          } else if (c == "\\") {
            lex_escape = 1
          } else if (c == "[") {
            regex_class = 1
          } else if (c == "]") {
            regex_class = 0
          } else if (c == "/" && !regex_class) {
            lex_regex = 0
            out = out "__REGEX__"
            prev_sig = "/"
          }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            value = value c
            lex_escape = 0
          } else if (c == "\\") {
            lex_escape = 1
          } else if (lex_quote == "`" && c == "$" && nchar == "{") {
            lex_quote = ""
            template_depth = 1
            value = ""
            i++
          } else if (c == lex_quote) {
            out = out inert_string(value)
            lex_quote = ""
            value = ""
          } else {
            value = value c
          }
          continue
        }
        if (template_depth > 0 && c == "{") {
          template_depth++
          out = out c
          continue
        }
        if (template_depth > 0 && c == "}") {
          template_depth--
          if (template_depth == 0) {
            lex_quote = "`"
            value = ""
          } else {
            out = out c
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          value = ""
          continue
        }
        if (c == "/" && nchar == "*") {
          lex_block = 1
          i++
          continue
        }
        if (c == "/" && nchar == "/") break
        if (c == "/" && (prev_sig == "" ||
            prev_sig ~ /[=(:,!{\[;?&|]/ ||
            out ~ /(^|[^A-Za-z0-9_$])(return|throw|case|yield)[[:space:]]*$/ ||
            out ~ /=>[[:space:]]*$/ ||
            out ~ /(^|[^A-Za-z0-9_$])(if|while|for|with)[[:space:]]*\([^)]*\)[[:space:]]*$/)) {
          lex_regex = 1
          regex_class = 0
          continue
        }
        out = out c
        if (c !~ /[[:space:]]/) prev_sig = c
      }
      if (NR == target) print out
    }
    NR <= target { executable_source($0) }
    NR >= target { exit }
  ' "$file" 2>/dev/null
}

focused_test_hit_matches() {
  local hit="$1" file rest line raw_line code receiver namespace target_code
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  raw_line=${rest#*:}
  target_code=$(lexical_target_line "$hit")
  namespace=$(printf '%s\n' "$target_code" |
    scanner_rg -oP '(?<![A-Za-z0-9_$.])\K[A-Za-z_$][A-Za-z0-9_$]*(?=[[:space:]]*\.[[:space:]]*test(?:[[:space:]]*\.[[:space:]]*describe)?[[:space:]]*(?:\.[[:space:]]*only|\[[[:space:]]*(?:__STR_only__|__ONLY__)[[:space:]]*\]))' |
    head -1)
  if [[ -n "$namespace" ]] &&
    { source_imports_playwright_namespace_binding "$file" "$namespace" ||
      relative_namespace_binding_reaches_playwright_test "$file" "$namespace"; }; then
      return 0
  fi
  receiver=$(printf '%s\n' "$target_code" |
    scanner_rg -oP '(?<![A-Za-z0-9_$.])\K[A-Za-z_$][A-Za-z0-9_$]*(?:[[:space:]]*\.[[:space:]]*describe)?[[:space:]]*(?:\?[[:space:]]*)?(?:\.[[:space:]]*only|\[[[:space:]]*(?:__STR_only__|__STR_on__[[:space:]]*\+[[:space:]]*__STR_ly__)[[:space:]]*\])[[:space:]]*(?:\?[[:space:]]*\.)?[[:space:]]*(?:\)[[:space:]]*)?\(' |
    head -1 |
    sed -E 's/([[:space:]]*\.[[:space:]]*describe)?[[:space:]]*(\?[[:space:]]*)?(\.[[:space:]]*only|\[[^]]+\])[[:space:]]*(\?[[:space:]]*\.)?[[:space:]]*(\)[[:space:]]*)?\($//; s/[[:space:]]//g')
  printf '%s\n' "$target_code" |
    scanner_rg -q '\.[[:space:]]*test([[:space:]]*\.[[:space:]]*describe)?[[:space:]]*(\.[[:space:]]*only|\[)' &&
    return 1
  if [[ -z "$receiver" ]] &&
    ! printf '%s\n' "$target_code" |
      scanner_rg -qP '(?:[.][[:space:]]*only|\[[[:space:]]*(?:__STR_only__|__STR_on__[[:space:]]*\+[[:space:]]*__STR_ly__)[[:space:]]*\])' &&
    ! printf '%s\n' "$raw_line" |
      scanner_rg -qP '\[[[:space:]]*`on\$\{[[:space:]]*['"'"'\"]ly['"'"'\"][[:space:]]*\}`[[:space:]]*\]'; then
      return 1
  fi
  code=$(awk -v first="$((line > 5 ? line - 5 : 1))" -v last="$line" '
    function executable_source(s,    out, value, i, c, nchar) {
      out = ""
      value = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_regex) {
          if (lex_escape) {
            lex_escape = 0
          } else if (c == "\\") {
            lex_escape = 1
          } else if (c == "[") {
            regex_class = 1
          } else if (c == "]") {
            regex_class = 0
          } else if (c == "/" && !regex_class) {
            lex_regex = 0
            out = out "__REGEX__"
            prev_sig = "/"
          }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) lex_escape = 0
          else if (c == "\\") lex_escape = 1
          else if (c == lex_quote) {
            if (value == "only" ||
                value == "on${\047ly\047}" ||
                value == "on${\"ly\"}")
              out = out "__ONLY__"
            else
              out = out "__STR__"
            lex_quote = ""
          } else value = value c
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          value = ""
          continue
        }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    NR <= last {
      source = executable_source($0)
      if (NR >= first) print source
    }
  ' "$file" 2>/dev/null | tr '\n' ' ')
  if [[ -z "$receiver" ]]; then
    receiver=$(printf '%s\n' "$code" |
      scanner_rg -oP '(?<![A-Za-z0-9_$.])\K[A-Za-z_$][A-Za-z0-9_$]*(?:[[:space:]]*\.[[:space:]]*describe)?[[:space:]]*(?:\.[[:space:]]*only|\[[[:space:]]*__ONLY__[[:space:]]*\])[[:space:]]*(?:\?[[:space:]]*\.)?[[:space:]]*(?:\)[[:space:]]*)?\(' |
      tail -1 |
      sed -E 's/([[:space:]]*\.[[:space:]]*describe)?[[:space:]]*(\.[[:space:]]*only|\[[[:space:]]*__ONLY__[[:space:]]*\])[[:space:]]*(\?[[:space:]]*\.)?[[:space:]]*(\)[[:space:]]*)?\($//; s/[[:space:]]//g')
  fi
  [[ -n "$receiver" ]] || return 1
  source_binding_shadowed_at "$file" "$receiver" "$line" && return 1
  source_imports_playwright_test_binding "$file" "$receiver" && return 0
  relative_binding_reaches_playwright "$file" "$receiver" &&
    return 0
  source_imports_relative_binding "$file" "$receiver" && return 1
  if source_imports_foreign_test_binding "$file" "$receiver" &&
    file_has_framework_provenance "$file"; then
    return 1
  fi
  source_imports_unresolved_binding "$file" "$receiver" && return 0
  case "$receiver" in
    test|it|describe|context|specify)
      source_declares_shadowing_test_binding_before "$file" "$receiver" "$line" &&
        return 1
      return 0
      ;;
  esac
  return 1
}

focused_test_alias_hit_matches() {
  local hit="$1" file rest line code alias prefix declaration receiver declaration_line between
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(lexical_target_line "$hit")
  alias=$(printf '%s\n' "$code" |
    scanner_rg -oP '^[[:space:]]*\K[A-Za-z_$][A-Za-z0-9_$]*(?=[[:space:]]*\()' |
    head -1)
  [[ -n "$alias" ]] || return 1
  prefix=$(source_executable_code "$file" only | sed -n "1,${line}p")
  declaration=$(printf '%s\n' "$prefix" |
    awk -v name="$alias" '
      {
        compact = $0
        gsub(/[[:space:]]+/, "", compact)
        if (compact ~ /^const\{/ &&
            (index(compact, "only:" name) > 0 ||
             (name == "only" && compact ~ /^const\{only\}/)) &&
            compact ~ /\}=[A-Za-z_$][A-Za-z0-9_$]*;?$/) {
          receiver = compact
          sub(/^.*\}=/, "", receiver)
          sub(/;$/, "", receiver)
          print NR ":" receiver
        }
      }
    ' |
    tail -1)
  if [[ -n "$declaration" ]]; then
    declaration_line=${declaration%%:*}
    receiver=${declaration#*:}
  else
    declaration=$(printf '%s\n' "$prefix" |
      scanner_rg -nP "(?:^|[;{}[:space:]])const[[:space:]]+$alias[[:space:]]*=[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*(?:[.][[:space:]]*only\\b|\\[[[:space:]]*['\"]only['\"][[:space:]]*\\])" |
      tail -1)
    [[ -n "$declaration" ]] || return 1
    declaration_line=${declaration%%:*}
    receiver=$(printf '%s\n' "${declaration#*:}" |
      scanner_rg -oP "const[[:space:]]+$alias[[:space:]]*=[[:space:]]*\\K[A-Za-z_$][A-Za-z0-9_$]*(?=[[:space:]]*(?:[.][[:space:]]*only\\b|\\[[[:space:]]*['\"]only['\"][[:space:]]*\\]))" |
      head -1)
    printf '%s\n' "${declaration#*:}" |
      scanner_rg -qP "const[[:space:]]+$alias[[:space:]]*=[[:space:]]*$receiver[[:space:]]*(?:[.][[:space:]]*only\\b|\\[[[:space:]]*['\"]only['\"][[:space:]]*\\])(?:[[:space:]]*[.][[:space:]]*bind[[:space:]]*\\([[:space:]]*$receiver[[:space:]]*\\))?[[:space:]]*;?[[:space:]]*$" ||
      return 1
  fi
  [[ -n "$receiver" ]] || return 1
  source_binding_shadowed_at "$file" "$receiver" "$declaration_line" && return 1
  source_imports_playwright_test_binding "$file" "$receiver" ||
    relative_binding_reaches_playwright "$file" "$receiver" ||
    {
      case "$receiver" in
        test|it|describe|context|specify) ;;
        *) return 1 ;;
      esac
      file_in_cypress_scope "$file" || return 1
      if source_has_foreign_test_module_reference "$file"; then
        source_has_cypress_module_reference "$file" ||
          source_has_cypress_runtime_reference "$file" ||
          return 1
      fi
      source_declares_shadowing_test_binding_before \
        "$file" "$receiver" "$declaration_line" &&
        return 1
    }
  between=$(source_executable_code "$file" |
    awk -v first="$((declaration_line + 1))" -v last="$line" '
      NR >= first && NR <= last { print }
      NR > last { exit }
    ')
  printf '%s\n' "$between" |
    scanner_rg -qP "(?:^|[;{}[:space:]])(?:let|var|const)?[[:space:]]*$alias[[:space:]]*=|(?:function[[:space:]]*[A-Za-z_$]*|catch)[[:space:]]*\\([^)]*\\b$alias\\b|\\([^)]*\\b$alias\\b[^)]*\\)[[:space:]]*=>" &&
    return 1
  return 0
}

focused_alias_call_pattern() {
  local declarations aliases
  declarations=$(
    "$RG_BIN" --no-filename -P --color never --hidden --no-ignore \
      --glob "$ALL_CODE_GLOB" \
      --glob '!**/node_modules/**' --glob '!**/.git/**' \
      --glob '!**/playwright-report/**' --glob '!**/cypress/reports/**' \
      --glob '!**/test-results/**' --glob '!**/dist/**' \
      --glob '!**/build/**' --glob '!**/.next/**' --glob '!**/out/**' \
      --glob '!**/coverage/**' \
      ${EVAL_FIXTURE_EXCLUDES[@]+"${EVAL_FIXTURE_EXCLUDES[@]}"} \
      'const[[:space:]]+(?:[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*=[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*(?:[.][[:space:]]*only\b|\[[[:space:]]*['"'"'"]only['"'"'"][[:space:]]*\])|\{[^}\n]*\bonly\b[^}\n]*\}[[:space:]]*=[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*)' \
      -- "$ROOT" 2>/dev/null || true
  )
  aliases=$(
    printf '%s\n' "$declarations" |
      while IFS= read -r declaration; do
        printf '%s\n' "$declaration" |
          scanner_rg -oP 'const[[:space:]]+\K[A-Za-z_$][A-Za-z0-9_$]*(?=[[:space:]]*=)' || true
        printf '%s\n' "$declaration" |
          scanner_rg -oP '\bonly[[:space:]]*:[[:space:]]*\K[A-Za-z_$][A-Za-z0-9_$]*' || true
        printf '%s\n' "$declaration" |
          scanner_rg -qP 'const[[:space:]]*\{[[:space:]]*only[[:space:]]*\}' &&
          printf '%s\n' only
      done |
      LC_ALL=C sort -u |
      paste -sd'|' -
  )
  if [[ -n "$aliases" ]]; then
    printf '^[[:space:]]*(?:%s)[[:space:]]*\\(' "$aliases"
  else
    printf '(?!)'
  fi
}

expect_call_pattern() {
  local aliases
  aliases=$(
    "$RG_BIN" --no-filename -P --color never --hidden --no-ignore \
      --glob "$ALL_CODE_GLOB" \
      --glob '!**/node_modules/**' --glob '!**/.git/**' \
      --glob '!**/playwright-report/**' --glob '!**/cypress/reports/**' \
      --glob '!**/test-results/**' --glob '!**/dist/**' \
      --glob '!**/build/**' --glob '!**/.next/**' --glob '!**/out/**' \
      --glob '!**/coverage/**' \
      ${EVAL_FIXTURE_EXCLUDES[@]+"${EVAL_FIXTURE_EXCLUDES[@]}"} \
      '(?:import[[:space:]]*\{[^}\n]*\bexpect[[:space:]]+as[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*|\{[^}\n]*\bexpect[[:space:]]*:[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*[^}\n]*\}[[:space:]]*=[[:space:]]*require[[:space:]]*\()' \
      -- "$ROOT" 2>/dev/null |
      while IFS= read -r declaration; do
        printf '%s\n' "$declaration" |
          scanner_rg -oP '\bexpect[[:space:]]+as[[:space:]]+\K[A-Za-z_$][A-Za-z0-9_$]*' || true
        printf '%s\n' "$declaration" |
          scanner_rg -oP '\bexpect[[:space:]]*:[[:space:]]*\K[A-Za-z_$][A-Za-z0-9_$]*' || true
      done |
      LC_ALL=C sort -u |
      paste -sd'|' - || true
  )
  if [[ -n "$aliases" ]]; then
    aliases="|$aliases"
  fi
  printf '^[[:space:]]*(?:(?:expect|assertion%s)|[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*[.][[:space:]]*expect)(?:[[:space:]]|/\\*.*?\\*/)*\\(' \
    "$aliases"
}

source_binding_shadowed_at() {
  local file="$1" binding="$2" line="$3"
  case "$binding" in
    *[!A-Za-z0-9_$]*|'') return 1 ;;
  esac
  source_executable_code "$file" |
    awk -v name="$binding" -v last="$line" '
      NR > last { exit }
      {
        normalized = $0
        gsub(/[^A-Za-z0-9_$]+/, " ", normalized)
        if ($0 ~ /catch[[:space:]]*\([^)]*\)/ &&
            (" " normalized " ") ~ (" catch " name " "))
          catch_open = 1
        else if (catch_open && $0 ~ /^[[:space:]]*}/)
          catch_open = 0
      }
      END { exit(catch_open ? 0 : 1) }
    ' >/dev/null 2>&1 &&
    return 0
  source_executable_code "$file" |
    awk -v name="$binding" -v last="$line" '
      function has_name(list,    normalized) {
        normalized = list
        gsub(/[^A-Za-z0-9_$]+/, " ", normalized)
        return (" " normalized " ") ~ (" " name " ")
      }
      NR > last { exit }
      {
        source = $0
        expression_param_shadow = 0
        if (match(source, /function[[:space:]]*[A-Za-z_$]*[[:space:]]*\([^)]*\)/)) {
          params = substr(source, RSTART, RLENGTH)
          if (has_name(params)) pending_param_shadow = 1
        } else if (match(source, /\([^)]*\)[[:space:]]*=>/)) {
          params = substr(source, RSTART, RLENGTH)
          if (has_name(params)) {
            arrow_tail = substr(source, RSTART + RLENGTH)
            if (arrow_tail !~ /^[[:space:]]*\{/) expression_param_shadow = 1
            else pending_param_shadow = 1
          }
        } else if (source ~ ("(^|[^A-Za-z0-9_$])" name "[[:space:]]*=>")) {
          if (source ~ ("(^|[^A-Za-z0-9_$])" name "[[:space:]]*=>[[:space:]]*\\{"))
            pending_param_shadow = 1
          else
            expression_param_shadow = 1
        } else if (match(source, /catch[[:space:]]*\([^)]*\)/)) {
          params = substr(source, RSTART, RLENGTH)
          if (has_name(params)) pending_param_shadow = 1
        }
        if (source ~ ("(^|[;{}[:space:]])(const|let|var|class|function)[[:space:]]+" name "([^A-Za-z0-9_$]|$)"))
          local_depth[depth] = 1
        if (source ~ ("(^|[;{}[:space:]])(const|let|var)[[:space:]]*(\\{|\\[)[^]}]*(^|[^A-Za-z0-9_$])" name "([^A-Za-z0-9_$]|$)"))
          local_depth[depth] = 1
        for (i = 1; i <= length(source); i++) {
          c = substr(source, i, 1)
          if (c == "{") {
            depth++
            if (pending_param_shadow) {
              param_depth[depth] = 1
              pending_param_shadow = 0
            }
          } else if (c == "}") {
            delete local_depth[depth]
            delete param_depth[depth]
            depth--
            if (depth < 0) depth = 0
          }
        }
        if (NR == last) {
          if (expression_param_shadow) found = 1
          for (d = depth; d >= 0; d--)
            if (local_depth[d] || param_depth[d]) found = 1
          exit
        }
      }
      END { exit(found ? 0 : 1) }
    ' >/dev/null 2>&1
}

source_declares_shadowing_test_binding_before() {
  local file="$1" binding="$2" line="$3"
  awk -v last="$line" '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) lex_escape = 0
          else if (c == "\\") lex_escape = 1
          else if (c == lex_quote) lex_quote = ""
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") { lex_quote = c; continue }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    NR <= last { print executable_source($0) }
  ' "$file" 2>/dev/null |
    scanner_rg -qP "(^|[;{}[:space:]])(?:const|let|var|function|class)[[:space:]]+$binding\\b"
}

executable_hit_matches() {
  local hit="$1" pattern="$2" file rest line
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  if [[ "$pattern" == *networkidle* ]]; then
    source_executable_code "$file" networkidle |
      sed -n "${line}p" |
      scanner_rg -qP "$pattern"
    return
  fi
  lexical_target_line "$hit" |
    sed -E 's/__STR_[A-Za-z0-9_$]*__//g' |
    scanner_rg -qP "$pattern"
}

filter_positive_to_be_attached_hits() {
  # `rg` reports the line containing the matcher name. Reconstruct lexical
  # state from the start of the file so quoted/comment-only names stay inert,
  # then admit only executable `toBeAttached` calls whose opening `(` occurs
  # within 24 physical lines and 500 lexical characters. The same bounded
  # window recognizes whitespace and block comments between the name and `(`,
  # plus `.not` chains split across whitespace/comments/lines. Keep candidates
  # on read/parse uncertainty (fail open for detection). One Python process
  # handles the rule stream, so a noisy file cannot create one interpreter
  # launch per candidate. A line containing both positive and negative calls
  # stays visible when at least one occurrence is positive.
  "$PYTHON3_BIN" -I -B -c '
import re
import sys
from collections import defaultdict

records = []
targets = defaultdict(set)
for raw in sys.stdin:
    raw = raw.rstrip("\n")
    try:
        path, remainder = raw.split(":", 1)
        raw_line = remainder.split(":", 1)[0]
        line = int(raw_line)
        if line < 1:
            raise ValueError("invalid line")
        records.append((raw, path, line))
        targets[path].add(line)
    except Exception:
        records.append((raw, None, None))

def executable_source(source):
    out = []
    stack = [{"kind": "code", "brace": None, "prev": ""}]
    index = 0
    while index < len(source):
        context = stack[-1]
        kind = context["kind"]
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        inert = "\n" if char == "\n" else " "
        if kind == "line-comment":
            out.append(inert)
            index += 1
            if char == "\n":
                stack.pop()
            continue
        if kind == "block-comment":
            if char == "*" and following == "/":
                out.extend((" ", " "))
                index += 2
                stack.pop()
            else:
                out.append(inert)
                index += 1
            continue
        if kind == "quote":
            out.append(inert)
            index += 1
            if context.get("escaped"):
                context["escaped"] = False
            elif char == "\\":
                context["escaped"] = True
            elif char == context["quote"]:
                stack.pop()
            continue
        if kind == "regex":
            out.append(inert)
            index += 1
            if context.get("escaped"):
                context["escaped"] = False
            elif char == "\\":
                context["escaped"] = True
            elif char == "[":
                context["class"] = True
            elif char == "]":
                context["class"] = False
            elif char == "/" and not context.get("class"):
                stack.pop()
            continue
        if kind == "template":
            if context.get("escaped"):
                context["escaped"] = False
                out.append(inert)
                index += 1
            elif char == "\\":
                context["escaped"] = True
                out.append(" ")
                index += 1
            elif char == "`":
                out.append(" ")
                index += 1
                stack.pop()
            elif char == "$" and following == "{":
                out.extend((" ", " "))
                index += 2
                stack.append({"kind": "code", "brace": 1, "prev": ""})
            else:
                out.append(inert)
                index += 1
            continue

        # Executable code, either the root source or a `${...}` substitution.
        if context["brace"] is not None and char == "{":
            context["brace"] += 1
            out.append(char)
            context["prev"] = char
            index += 1
        elif context["brace"] is not None and char == "}":
            context["brace"] -= 1
            index += 1
            if context["brace"] == 0:
                out.append(" ")
                stack.pop()
            else:
                out.append(char)
                context["prev"] = char
        elif char in ("\"", chr(39)):
            out.append(" ")
            index += 1
            stack.append({"kind": "quote", "quote": char, "escaped": False})
        elif char == "`":
            out.append(" ")
            index += 1
            stack.append({"kind": "template", "escaped": False})
        elif char == "/" and following == "*":
            out.extend((" ", " "))
            index += 2
            stack.append({"kind": "block-comment"})
        elif char == "/" and following == "/":
            out.extend((" ", " "))
            index += 2
            stack.append({"kind": "line-comment"})
        elif char == "/" and (
            not context["prev"]
            or context["prev"] in "=(:,!{[;?&|"
            or re.search(
                r"(?:^|[^A-Za-z0-9_$])(return|throw|case|yield)\s*$",
                "".join(out[-512:]),
            )
            or re.search(r"=>\s*$", "".join(out[-512:]))
            or re.search(
                r"(?:^|[^A-Za-z0-9_$])(if|while|for|with)\s*\([^)]*\)\s*$",
                "".join(out[-512:]),
            )
        ):
            out.append(" ")
            index += 1
            stack.append({"kind": "regex", "escaped": False, "class": False})
        else:
            out.append(char)
            index += 1
            if not char.isspace():
                context["prev"] = char
    return "".join(out)

positive = {}
for path, wanted in targets.items():
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        if any(len(text) > 65536 for text in lines):
            raise ValueError("oversized source line")
        lexical = executable_source("".join(lines))
        lexical_lines = lexical.splitlines(keepends=True)
        offsets = [0]
        for value in lexical_lines:
            offsets.append(offsets[-1] + len(value))
        for line in wanted:
            if line > len(lexical_lines):
                positive[(path, line)] = True
                continue
            start = offsets[line - 1]
            current = lexical_lines[line - 1]
            end = start + len(current)
            found = False
            for match in re.finditer(r"\btoBeAttached\b", lexical[start:end]):
                absolute = start + match.start()
                suffix_lines = lexical_lines[line - 1:line + 23]
                suffix = "".join(suffix_lines)[match.end():]
                opening = re.match(r"\s{0,500}\(", suffix)
                if opening is None:
                    continue
                prefix = lexical[offsets[max(0, line - 25)]:absolute]
                compact = re.sub(r"\s+", "", prefix)
                if not compact.endswith(".not."):
                    found = True
                    break
            positive[(path, line)] = found
    except Exception:
        for line in wanted:
            positive[(path, line)] = True

for raw, path, line in records:
    if path is None or positive.get((path, line), True):
        print(raw)
'
}

immutable_computed_truthy_hit_matches() {
  local hit="$1" file rest line code property binding prefix matcher
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(lexical_target_line "$hit")
  property=$(printf '%s\n' "$code" |
    scanner_rg -oP '\[[[:space:]]*\K[A-Za-z_$][A-Za-z0-9_$]*(?=[[:space:]]*\][[:space:]]*\()' |
    head -1)
  [[ -n "$property" ]] || return 1
  binding=$(expect_call_binding_at "$hit")
  [[ -n "$binding" ]] || return 1
  source_imports_playwright_expect_binding "$file" "$binding" ||
    relative_named_binding_reaches_playwright "$file" "$binding" expect ||
    return 1
  for matcher in toBeTruthy toBeDefined; do
    prefix=$(source_executable_code "$file" "$matcher" | sed -n "1,${line}p")
    printf '%s\n' "$prefix" |
      scanner_rg -qP "(?:^|[;{}[:space:]])const[[:space:]]+$property[[:space:]]*=[[:space:]]*['\"]$matcher['\"]" &&
      return 0
  done
  return 1
}

initialized_module_state_hit_matches() {
  lexical_target_line "$1" |
    scanner_rg -qP '^[[:space:]]*(?:export[[:space:]]+)?let[[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*(?:[[:space:]]*:[^=;]+)?[[:space:]]*='
}

playwright_page_receiver_proven_at() {
  local file="$1" line="$2" receiver="$3" member code type_binding
  member="$receiver"
  case "$receiver" in
    this.*) member=${receiver#this.} ;;
  esac
  case "$member" in
    *[!A-Za-z0-9_$]*|'') return 1 ;;
  esac
  code=$(source_executable_code "$file" | awk -v last="$line" 'NR <= last { print }')

  # A local value assignment shadows the conventional fixture name. Without a
  # Page annotation its method surface is only an application object candidate.
  if [[ "$member" == "page" ]] &&
    printf '%s\n' "$code" |
      scanner_rg -qP "(^|[;{}[:space:]])(?:const|let|var)[[:space:]]+page[[:space:]]*="; then
    return 1
  fi
  if [[ "$member" == "page" ]] &&
    printf '%s\n' "$code" |
      scanner_rg -qP 'async[[:space:]]*\([[:space:]]*\{[^}]*\bpage\b'; then
    return 0
  fi
  printf '%s\n' "$code" |
    scanner_rg -qP "(?:\\b(?:readonly|private|protected|public|declare)[[:space:]]+)*\\b$member[[:space:]]*:[[:space:]]*import[[:space:]]*\\([[:space:]]*['\"]@playwright/test['\"][[:space:]]*\\)[.]Page\\b" &&
    return 0
  type_binding=$(printf '%s\n' "$code" |
    scanner_rg -oP "(?:\\b(?:readonly|private|protected|public|declare)[[:space:]]+)*\\b$member[[:space:]]*:[[:space:]]*\\K[A-Za-z_$][A-Za-z0-9_$]*" |
    tail -1)
  [[ -n "$type_binding" ]] || return 1
  if [[ "$type_binding" == "Page" ]]; then
    scanner_rg -qP "import[[:space:]]*(?:type[[:space:]]*)?\\{[^}]*\\b(?:type[[:space:]]+)?Page\\b[^}]*\\}[[:space:]]*from[[:space:]]*['\"]@playwright/test['\"]" "$file"
  else
    scanner_rg -qP "import[[:space:]]*(?:type[[:space:]]*)?\\{[^}]*\\b(?:type[[:space:]]+)?Page[[:space:]]+as[[:space:]]+$type_binding\\b[^}]*\\}[[:space:]]*from[[:space:]]*['\"]@playwright/test['\"]" "$file"
  fi
}

one_shot_page_url_hit_matches() {
  local hit="$1" file rest line binding code receiver
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  binding=$(expect_call_binding_at "$hit")
  [[ -n "$binding" ]] && playwright_expect_binding "$file" "$binding" "$line" || return 1
  code=$(locator_assertion_source "$file" "$line")
  receiver=$(printf '%s\n' "$code" |
    scanner_rg -oP '\([[:space:]]*\K(?:this[.])?[A-Za-z_$][A-Za-z0-9_$]*(?=[[:space:]]*[.][[:space:]]*url[[:space:]]*[(])' |
    head -1)
  [[ -n "$receiver" ]] || return 1
  playwright_page_receiver_proven_at "$file" "$line" "$receiver"
}

soft_expect_hit_matches() {
  local hit="$1" file code binding
  file=${hit%%:*}
  code=$(lexical_target_line "$hit")
  binding=$(printf '%s\n' "$code" |
    scanner_rg -oP '^[[:space:]]*\K[A-Za-z_$][A-Za-z0-9_$]*(?:[[:space:]]*[.][[:space:]]*expect)?(?=[[:space:]]*[.][[:space:]]*soft[[:space:]]*[(])' |
    head -1 |
    sed -E 's/[[:space:]]//g')
  [[ -n "$binding" ]] || return 1
  local rest line
  rest=${hit#*:}
  line=${rest%%:*}
  playwright_expect_binding "$file" "$binding" "$line"
}

page_api_receiver_at() {
  lexical_target_line "$1" |
    scanner_rg -oP '(?<![A-Za-z0-9_$.])\K(?:this[.])?[A-Za-z_$][A-Za-z0-9_$]*(?=[[:space:]]*[.][[:space:]]*(?:click|dblclick|tap|fill|type|press|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|dispatchEvent|dragAndDrop)[[:space:]]*[(])' |
    head -1
}

direct_page_api_hit_matches() {
  local hit="$1" file rest line receiver
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  receiver=$(page_api_receiver_at "$hit")
  [[ "$receiver" == "page" ]] || return 1
  playwright_page_receiver_proven_at "$file" "$line" "$receiver"
}

triage_page_api_hit_matches() {
  local hit="$1" file rest line receiver member
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  receiver=$(page_api_receiver_at "$hit")
  [[ -n "$receiver" ]] || return 1
  if [[ "$receiver" == "page" ]] &&
    playwright_page_receiver_proven_at "$file" "$line" "$receiver"; then
    return 1
  fi
  playwright_page_receiver_proven_at "$file" "$line" "$receiver" && return 0
  member=${receiver#this.}
  case "$member" in
    *[Pp]age) return 0 ;;
    page) return 0 ;;
  esac
  return 1
}

# `cy.wait()` accepts whitespace and line breaks before its first argument.
# Reconstruct a bounded, lexically stripped prefix so numeric sleeps are found
# without treating alias waits (`cy.wait('@request')`) or strings/comments as
# delays. The finding remains anchored at the `cy.wait(` line.
cypress_numeric_wait_hit_matches() {
  local hit="$1" file rest line
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  bounded_executable_source "$file" "$line" "$((line + 4))" |
    scanner_rg -q 'cy\.wait\([[:space:]]*[0-9]'
}

bounded_executable_source() {
  local file="$1" first="$2" last="$3" retained="${4:-}"
  source_executable_code "$file" "$retained" |
    awk -v first="$first" -v last="$last" 'NR >= first && NR <= last { print } NR > last { exit }' |
    tr '\n' ' '
}

playwright_wait_timeout_hit_matches() {
  local hit="$1" file rest line receiver
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  receiver=$(lexical_target_line "$hit" |
    scanner_rg -oP '(?<![A-Za-z0-9_$.])\K(?:this[.])?[A-Za-z_$][A-Za-z0-9_$]*(?=[[:space:]]*[.][[:space:]]*waitForTimeout[[:space:]]*[(])' |
    head -1)
  [[ -n "$receiver" ]] || return 1
  playwright_page_receiver_proven_at "$file" "$line" "$receiver"
}

zero_timeout_hit_matches() {
  local hit="$1" file rest line first code
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  first=$((line > 8 ? line - 8 : 1))
  code=$(bounded_executable_source "$file" "$first" "$line" timeout)
  printf '%s\n' "$code" |
    scanner_rg -qP "(?:\\bexpect[[:space:]]*[(]|[.](${PLAYWRIGHT_ASYNC_MATCHERS})[[:space:]]*[(]|[.]should[[:space:]]*[(]|[.](?:goto|waitFor|click|fill|press|check|selectOption)[A-Za-z_$]*[[:space:]]*[(])(?:(?!;).)*['\"]?timeout['\"]?[[:space:]]*:[[:space:]]*0"
}

force_action_hit_matches() {
  local hit="$1" file rest line first code
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  first=$((line > 8 ? line - 8 : 1))
  code=$(bounded_executable_source "$file" "$first" "$line" force)
  printf '%s\n' "$code" |
    scanner_rg -qP "[.](?:click|dblclick|tap|fill|clear|type|press|pressSequentially|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|dragTo|drop|dispatchEvent|scrollIntoViewIfNeeded|selectText)[[:space:]]*[(](?:(?!;).)*['\"]?force['\"]?[[:space:]]*:[[:space:]]*true"
}

serial_configure_hit_matches() {
  local hit="$1" file rest line code
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(bounded_executable_source "$file" "$line" "$((line + 12))" serial)
  printf '%s\n' "$code" |
    scanner_rg -qP "[.]describe[[:space:]]*[.][[:space:]]*configure[[:space:]]*[(][^;]{0,1000}mode[[:space:]]*:[[:space:]]*['\"\`]serial['\"\`]"
}

cypress_action_chain_hit_matches() {
  local hit="$1" file rest line code
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(bounded_executable_source "$file" "$line" "$((line + 12))")
  printf '%s\n' "$code" |
    scanner_rg -qP "[.](?:click|type|check|uncheck|select|selectFile|trigger|scrollIntoView)[[:space:]]*[(][^;]{0,1200}[)][[:space:]]*[.][[:space:]]*(?:should|and|click|type|check|uncheck|select|trigger)[[:space:]]*[(]"
}

# Reconstruct a bounded assertion starting at the matched expect( line. The
# lexer removes strings/comments while preserving call punctuation, and the
# matcher requires a Locator-shaped subject before an always-true matcher.
locator_assertion_source() {
  local file="$1" line="$2"
  awk -v target="$line" '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") {
            lex_block = 0
            i++
          }
          continue
        }
        if (lex_regex) {
          if (lex_escape) {
            lex_escape = 0
          } else if (c == "\\") {
            lex_escape = 1
          } else if (c == "[") {
            regex_class = 1
          } else if (c == "]") {
            regex_class = 0
          } else if (c == "/" && !regex_class) {
            lex_regex = 0
            out = out "__REGEX__"
            prev_sig = "/"
          }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) {
            lex_escape = 0
          } else if (c == "\\") {
            lex_escape = 1
          } else if (c == lex_quote) {
            out = out "__STR__"
            lex_quote = ""
          }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") {
          lex_quote = c
          continue
        }
        if (c == "/" && nchar == "*") {
          lex_block = 1
          i++
          continue
        }
        if (c == "/" && nchar == "/") break
        if (c == "/" && (prev_sig == "" ||
            prev_sig ~ /[=(:,!{\[;?&|]/ ||
            out ~ /(^|[^A-Za-z0-9_$])(return|throw|case|yield)[[:space:]]*$/ ||
            out ~ /=>[[:space:]]*$/ ||
            out ~ /(^|[^A-Za-z0-9_$])(if|while|for|with)[[:space:]]*\([^)]*\)[[:space:]]*$/)) {
          lex_regex = 1
          regex_class = 0
          continue
        }
        out = out c
        if (c !~ /[[:space:]]/) prev_sig = c
      }
      return out
    }
    NR < target { executable_source($0); next }
    NR > target + 12 { exit }
    {
      code = code " " executable_source($0)
      if (code ~ /[.](toBeTruthy|toBeDefined|toBeNull|toBeUndefined)[[:space:]]*[(]/ ||
          code ~ /[.]not[.]to([.]be)?[.](equal|undefined|null)/ ||
          code ~ /;[[:space:]]*$/) {
        gsub(/[[:space:]]+/, " ", code)
        print code
        exit
      }
    }
  ' "$file" 2>/dev/null
}

playwright_expect_binding() {
  local file="$1" binding="$2" line="${3:-0}"
  if [[ "$line" -gt 0 ]]; then
    case "$binding" in
      *'.expect') ;;
      *) source_binding_shadowed_at "$file" "$binding" "$line" && return 1 ;;
    esac
  fi
  case "$binding" in
    *'.expect')
      local namespace=${binding%.expect}
      source_imports_playwright_namespace_binding "$file" "$namespace" ||
        relative_namespace_binding_reaches_playwright_expect "$file" "$namespace"
      return
      ;;
  esac
  case "$binding" in
    *[!A-Za-z0-9_$]*|'') return 1 ;;
  esac
  source_imports_playwright_expect_binding "$file" "$binding" && return 0
  relative_named_binding_reaches_playwright "$file" "$binding" expect
}

expect_call_binding_at() {
  local hit="$1" code
  code=$(lexical_target_line "$hit")
  printf '%s\n' "$code" |
    scanner_rg -oP '^[[:space:]]*\(?[[:space:]]*(?:[^,;()]+,[[:space:]]*)?\K[A-Za-z_$][A-Za-z0-9_$]*(?:[[:space:]]*\.[[:space:]]*expect)?[[:space:]]*(?=\()' |
    head -1 |
    sed -E 's/[[:space:]]//g'
}

expect_in_observed_promise_aggregate_at() {
  local file="$1" line="$2"
  awk -v target="$line" '
    function trim(s) {
      sub(/^[[:space:]]+/, "", s)
      sub(/[[:space:]]+$/, "", s)
      return s
    }
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) lex_escape = 0
          else if (c == "\\") lex_escape = 1
          else if (c == lex_quote) lex_quote = ""
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") { lex_quote = c; continue }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    NR > target { exit }
    {
      source = executable_source($0)
      if (!inside && match(source, /Promise[.](all|race|allSettled|any)[[:space:]]*[(][[:space:]]*\[/)) {
        prefix = trim(substr(source, 1, RSTART - 1))
        observed = (prefix == "await" || prefix == "return")
        inside = 1
        source = substr(source, RSTART + RLENGTH - 1)
        depth = 0
      }
      if (inside) {
        opens = gsub(/\[/, "[", source)
        closes = gsub(/\]/, "]", source)
        depth += opens - closes
        if (NR == target && observed) found = 1
        if (depth <= 0) {
          inside = 0
          observed = 0
          depth = 0
        }
      }
    }
    END { exit(found ? 0 : 1) }
  ' "$file" >/dev/null 2>&1
}

missing_await_expect_hit_matches() {
  local hit="$1" file rest line binding code
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  binding=$(expect_call_binding_at "$hit")
  [[ -n "$binding" ]] || return 1
  playwright_expect_binding "$file" "$binding" "$line" || return 1
  expect_in_observed_promise_aggregate_at "$file" "$line" && return 1
  code=$(locator_assertion_source "$file" "$line")
  printf '%s\n' "$code" |
    scanner_rg -q '^[[:space:]]*(await|return)([^A-Za-z0-9_$]|$)' &&
    return 1
  printf '%s\n' "$code" |
    scanner_rg -q "[.](${PLAYWRIGHT_ASYNC_MATCHERS})[[:space:]]*[(]"
}

retry_expect_hit_matches() {
  local hit="$1" file rest line code binding
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(locator_assertion_source "$file" "$line")
  [[ -n "$code" ]] || code=$(lexical_target_line "$hit")
  binding=$(printf '%s\n' "$code" |
    scanner_rg -oP '^[[:space:]]*\K[A-Za-z_$][A-Za-z0-9_$]*(?=[[:space:]]*(?:[.][[:space:]]*poll[[:space:]]*[(]|[(]))' |
    head -1)
  [[ -n "$binding" ]] || return 1
  playwright_expect_binding "$file" "$binding" "$line" || return 1
  printf '%s\n' "$code" |
    scanner_rg -q '^[[:space:]]*(await|return)([^A-Za-z0-9_$]|$)' &&
    return 1
  printf '%s\n' "$code" |
    scanner_rg -qP "(?:^[[:space:]]*$binding[[:space:]]*[.][[:space:]]*poll[[:space:]]*[(].*[.][A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*[(]|^[[:space:]]*$binding[[:space:]]*[(].*[.]toPass[[:space:]]*[(])"
}

proven_locator_binding() {
  local file="$1" line="$2" binding="$3"
  case "$binding" in
    *[!A-Za-z0-9_$]*|'') return 1 ;;
  esac
  awk -v last="$line" '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) lex_escape = 0
          else if (c == "\\") lex_escape = 1
          else if (c == lex_quote) { out = out "__STR__"; lex_quote = "" }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") { lex_quote = c; continue }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    NR <= last { print executable_source($0) }
  ' "$file" 2>/dev/null |
    scanner_rg -qP "(?:\\b(?:const|let|var|readonly)[[:space:]]+$binding[[:space:]]*:[[:space:]]*(?:import[[:space:]]*\\([^)]*\\)[.]?)?Locator\\b|\\bconst[[:space:]]+$binding[[:space:]]*=[[:space:]]*page[.](?:locator|getBy[A-Z][A-Za-z]*)[[:space:]]*\\()"
}

locator_assertion_hit_matches() {
  local hit="$1" file rest line code binding expect_binding
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  expect_binding=$(expect_call_binding_at "$hit")
  [[ -n "$expect_binding" ]] || return 1
  playwright_expect_binding "$file" "$expect_binding" "$line" || return 1
  awaited_locator_value_read_at "$file" "$line" && return 1
  code=$(locator_assertion_source "$file" "$line")
  printf '%s\n' "$code" |
    scanner_rg -q '^[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*(\s*\.\s*expect)?\s*\(\s*page\.(locator|getBy[A-Z][A-Za-z]*)\s*\(.*\)\s*(\.toBeTruthy\s*\(\s*\)|\.toBeDefined\s*\(\s*\)|\.not\.toBeNull\s*\(\s*\)|\.not\.toBeUndefined\s*\(\s*\)|\.not\.to\.equal\s*\(\s*null\s*\)|\.not\.to\.be\.null)' &&
    return 0
  binding=$(printf '%s\n' "$code" |
    scanner_rg -o '[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*\([[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*' |
    head -1 |
    sed -E 's/^[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*\([[:space:]]*//')
  [[ -n "$binding" ]] || return 1
  printf '%s\n' "$code" |
    scanner_rg -q '\)\s*(\.toBeTruthy\s*\(\s*\)|\.toBeDefined\s*\(\s*\)|\.not\.toBeNull\s*\(\s*\)|\.not\.toBeUndefined\s*\(\s*\)|\.not\.to\.equal\s*\(\s*null\s*\)|\.not\.to\.be\.null)' ||
    return 1
  proven_locator_binding "$file" "$line" "$binding"
}

unresolved_locator_assertion_hit_matches() {
  local hit="$1" file rest line code expect_binding
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  expect_binding=$(expect_call_binding_at "$hit")
  [[ -n "$expect_binding" ]] || return 1
  source_imports_unresolved_expect_binding "$file" "$expect_binding" || return 1
  code=$(locator_assertion_source "$file" "$line")
  printf '%s\n' "$code" |
    scanner_rg -q '^[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*\([[:space:]]*page[.](locator|getBy[A-Z][A-Za-z]*)[[:space:]]*\(.*\)[[:space:]]*\)[[:space:]]*(\.[[:space:]]*toBeTruthy[[:space:]]*\([[:space:]]*\)|\.[[:space:]]*toBeDefined[[:space:]]*\([[:space:]]*\)|\.[[:space:]]*not[[:space:]]*\.[[:space:]]*toBeNull[[:space:]]*\([[:space:]]*\)|\.[[:space:]]*not[[:space:]]*\.[[:space:]]*toBeUndefined[[:space:]]*\([[:space:]]*\))'
}

wrapped_locator_assertion_hit_matches() {
  local hit="$1" file rest line code expect_binding
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  expect_binding=$(expect_call_binding_at "$hit")
  [[ -n "$expect_binding" ]] || return 1
  playwright_expect_binding "$file" "$expect_binding" "$line" || return 1
  code=$(locator_assertion_source "$file" "$line")
  printf '%s\n' "$code" |
    scanner_rg -q '^[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*(\s*\.\s*expect)?\s*\(\s*[A-Za-z_$][A-Za-z0-9_$]*\s*\(\s*page\.(locator|getBy[A-Z][A-Za-z]*)\s*\(.*\)\s*\)\s*\)\s*(\.toBeTruthy\s*\(\s*\)|\.toBeDefined\s*\(\s*\)|\.not\.toBeNull\s*\(\s*\)|\.not\.toBeUndefined\s*\(\s*\))'
}

identifier_locator_assertion_hit_matches() {
  local hit="$1" file rest line code
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(locator_assertion_source "$file" "$line")
  printf '%s\n' "$code" |
    scanner_rg -q '[A-Za-z_$][A-Za-z0-9_$]*\s*\(\s*[A-Za-z_$][A-Za-z0-9_$]*[Ll]ocator\s*\)\s*(\.toBeTruthy\s*\(\s*\)|\.toBeDefined\s*\(\s*\)|\.not\.toBeNull\s*\(\s*\)|\.not\.toBeUndefined\s*\(\s*\)|\.not\.to\.equal\s*\(\s*null\s*\)|\.not\.to\.be\.null)' ||
    return 1
  locator_assertion_hit_matches "$hit" && return 1
  return 0
}

member_locator_assertion_hit_matches() {
  local hit="$1" file rest line code
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(locator_assertion_source "$file" "$line")
  printf '%s\n' "$code" |
    scanner_rg -q '[A-Za-z_$][A-Za-z0-9_$]*\s*\(\s*(this|[A-Za-z_$][A-Za-z0-9_$]*[Pp]age)\.[A-Za-z_$][A-Za-z0-9_$]*(Button|Link|Input|Field|Checkbox|Radio|Select|Dialog|Modal|Toast|Banner|Heading|Label|Tab|Menu|Item|Row|Cell|Locator|Element)\s*\)\s*(\.toBeTruthy\s*\(\s*\)|\.toBeDefined\s*\(\s*\)|\.not\.toBeNull\s*\(\s*\)|\.not\.toBeUndefined\s*\(\s*\)|\.not\.to\.equal\s*\(\s*null\s*\)|\.not\.to\.be\.null)'
}

generic_getby_assertion_hit_matches() {
  local hit="$1" file rest line code
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(locator_assertion_source "$file" "$line")
  printf '%s\n' "$code" |
    scanner_rg -q '[A-Za-z_$][A-Za-z0-9_$]*\s*\(.*(\.getBy[A-Z][A-Za-z]*|\bgetBy[A-Z][A-Za-z]*)\s*\(.*\)\s*(\.toBeTruthy\s*\(\s*\)|\.toBeDefined\s*\(\s*\)|\.not\.toBeNull\s*\(\s*\)|\.not\.to\.equal\s*\(\s*null\s*\)|\.not\.to\.be\.null)' ||
    return 1
  locator_assertion_hit_matches "$hit" && return 1
  return 0
}

conditional_assertion_hit_matches() {
  local hit="$1" file rest line code alias
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(awk -v target="$line" -v last="$((line + 40))" '
    function executable_source(s,    out, i, c, nchar) {
      out = ""
      for (i = 1; i <= length(s); i++) {
        c = substr(s, i, 1)
        nchar = substr(s, i + 1, 1)
        if (lex_block) {
          if (c == "*" && nchar == "/") { lex_block = 0; i++ }
          continue
        }
        if (lex_quote != "") {
          if (lex_escape) lex_escape = 0
          else if (c == "\\") lex_escape = 1
          else if (c == lex_quote) { out = out "__STR__"; lex_quote = "" }
          continue
        }
        if (c == "\"" || c == "\047" || c == "`") { lex_quote = c; continue }
        if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
        if (c == "/" && nchar == "/") break
        out = out c
      }
      return out
    }
    NR < target { executable_source($0); next }
    NR > last { exit }
    {
      line = executable_source($0)
      code = code " " line
      if (!condition_done) {
        opens = gsub(/\(/, "(", line)
        closes = gsub(/\)/, ")", line)
        condition_depth += opens - closes
        if (opens > 0) saw_condition = 1
        if (saw_condition && condition_depth <= 0) condition_done = 1
      }
      brace_opens = gsub(/\{/, "{", line)
      brace_closes = gsub(/\}/, "}", line)
      if (brace_opens > 0) saw_brace = 1
      brace_depth += brace_opens - brace_closes
      if (condition_done && saw_brace && brace_depth <= 0) {
        print code
        printed = 1
        exit
      }
      if (condition_done && !saw_brace && line ~ /;/) {
        print code
        printed = 1
        exit
      }
    }
    END { if (!printed && code != "") print code }
  ' "$file" 2>/dev/null)
  printf '%s\n' "$code" |
    scanner_rg -q '(^|[^A-Za-z0-9_$])(expect|assertion)[[:space:]]*\(|(^|[^A-Za-z0-9_$])assert([.][A-Za-z_$][A-Za-z0-9_$]*)?[[:space:]]*\(|[.]should[[:space:]]*\(' &&
    return 0
  source_has_unresolved_test_import "$file" || return 1
  while IFS= read -r alias; do
    [[ -n "$alias" ]] || continue
    source_binding_shadowed_at "$file" "$alias" "$line" && continue
    printf '%s\n' "$code" |
      scanner_rg -qP "(^|[^A-Za-z0-9_$])$alias[[:space:]]*\\(" &&
      return 0
  done < <(
    scanner_rg -oP 'import[[:space:]]*\{[^}]*\bexpect[[:space:]]+as[[:space:]]+\K[A-Za-z_$][A-Za-z0-9_$]*' "$file" 2>/dev/null
  )
  return 1
}

hardcoded_credential_hit_matches() {
  local hit="$1" file rest line code target_line
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  target_line=$(lexical_target_line "$hit")
  printf '%s\n' "$target_line" |
    scanner_rg -qi '(function[[:space:]]+(login|signIn)[[:space:]]*\(|^[[:space:]]*(public|private|protected|static|async|readonly|override|abstract|declare|[[:space:]])*(login|signIn)[[:space:]]*\([^)]*\)[[:space:]]*(:[^={]+)?[[:space:]]*\{)' &&
    return 1
  code=$(locator_assertion_source "$file" "$line")
  [[ -n "$code" ]] || code=$(lexical_target_line "$hit")
  [[ -n "$code" ]] || return 1
  printf '%s\n' "$code" |
    scanner_rg -qi '(process\.env|import\.meta\.env|Cypress\.env\s*\(|Deno\.env|Bun\.env)' &&
    return 1
  printf '%s\n' "$code" |
    scanner_rg -q '(__STR__|__STR_[A-Za-z0-9_$]+__)' || return 1
  if printf '%s\n' "$code" |
    scanner_rg -qi '\.(fill|type)\s*\('; then
    return 0
  fi
  if printf '%s\n' "$code" |
    scanner_rg -qi '(^|[^A-Za-z0-9_$])(login|signIn)\s*\('; then
    [[ "$(printf '%s\n' "$code" | scanner_rg -o '__STR(?:_[A-Za-z0-9_$]+)?__' | wc -l | tr -d '[:space:]')" -ge 2 ]] &&
      return 0
    return 1
  fi
  printf '%s\n' "$code" |
    scanner_rg -qi '(\b(validUser|testAdmin|adminUser)\b[[:space:]]*[:=]|\.(post|put|patch|request)\s*\(|\bfetch\s*\()' &&
    printf '%s\n' "$code" |
      scanner_rg -qi '(password|passwd|secret|credential|token|username|email|validUser|testAdmin|adminUser|auth|login|signIn)'
}

empty_catch_hit_matches() {
  catch_callback_hit_matches "$1" empty || return 1
  empty_catch_best_effort_hit_matches "$1" && return 1
  empty_catch_load_bearing_hit_matches "$1"
}

fluent_chain_source_at() {
  local file="$1" line="$2"
  source_executable_code "$file" |
    awk -v target="$line" '
      NR <= target { source[NR] = $0 }
      NR == target { exit }
      END {
        if (source[target] !~ /^[[:space:]]*[.]/)
          exit
        lower = target > 8 ? target - 8 : 1
        start = target
        for (i = target - 1; i >= lower; i--) {
          if (source[i] ~ /^[[:space:]]*$/)
            continue
          if (source[i] ~ /[;{}]/)
            break
          start = i
          if (source[i] !~ /^[[:space:]]*[.]/)
            break
        }
        for (i = start; i <= target; i++)
          print source[i]
      }
    '
}

empty_catch_load_bearing_hit_matches() {
  local hit="$1" file rest line code chain
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(locator_assertion_source "$file" "$line")
  chain=$(fluent_chain_source_at "$file" "$line")
  [[ -n "$chain" ]] && code="$chain
$code"
  [[ -n "$code" ]] || return 1
  printf '%s\n' "$code" |
    scanner_rg -qP '(?:Promise[[:space:]]*[.][[:space:]]*(?:all|allSettled|any|race)|[.](?:goto|reload|goBack|goForward|waitForURL|waitForNavigation|waitForLoadState|waitForResponse|waitForRequest|click|dblclick|tap|fill|clear|type|press|pressSequentially|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|blur|dragTo|drop|dispatchEvent|scrollIntoViewIfNeeded|selectText|screenshot|waitFor|route|unroute|evaluate|evaluateAll|title|content|textContent|innerText|innerHTML|inputValue|count|isVisible|isHidden|isEnabled|isDisabled|isEditable|isChecked|get|post|put|patch|delete|fetch|step|to[A-Z][A-Za-z0-9_$]*))[[:space:]]*[(]'
}

empty_catch_unresolved_outcome_hit_matches() {
  catch_callback_hit_matches "$1" empty || return 1
  empty_catch_best_effort_hit_matches "$1" && return 1
  empty_catch_load_bearing_hit_matches "$1" && return 1
  return 0
}

catch_in_lifecycle_hook_at() {
  local file="$1" line="$2"
  source_executable_code "$file" |
    awk -v target="$line" '
      NR > target { exit }
      {
        source = $0
        if (source ~ /(^|[^A-Za-z0-9_$])(test[[:space:]]*[.][[:space:]]*)?(beforeAll|beforeEach|afterAll|afterEach|before|after)[[:space:]]*[(]/)
          pending_hook = 1

        opens = gsub(/\{/, "{", source)
        closes = gsub(/\}/, "}", source)
        next_depth = depth + opens - closes

        if (pending_hook &&
            source ~ /(=>[[:space:]]*\{|function([[:space:]]+[A-Za-z_$][A-Za-z0-9_$]*)?[[:space:]]*[(][^)]*[)][[:space:]]*\{)/) {
          if (NR == target)
            found = 1
          if (next_depth > depth)
            hook_depth = next_depth
          pending_hook = 0
        } else if (NR == target && hook_depth > 0 && depth >= hook_depth) {
          found = 1
        }

        depth = next_depth
        if (hook_depth > 0 && depth < hook_depth)
          hook_depth = 0
      }
      END { exit(found ? 0 : 1) }
    ' >/dev/null 2>&1
}

empty_catch_best_effort_hit_matches() {
  local hit="$1" file rest line code chain
  catch_callback_hit_matches "$hit" empty || return 1
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(locator_assertion_source "$file" "$line")
  chain=$(fluent_chain_source_at "$file" "$line")
  [[ -n "$chain" ]] && code="$chain
$code"
  printf '%s\n' "$code" |
    scanner_rg -qi '(^|[^A-Za-z0-9_$])(cleanup|teardown|tearDown|dispose|disconnect|shutdown|terminate|release|close|stop|kill)[A-Za-z0-9_$]*[[:space:]]*\([^;]*\)[[:space:]]*[.]catch' &&
    return 0
  catch_in_lifecycle_hook_at "$file" "$line"
}

catch_callback_hit_matches() {
  local hit="$1" mode="$2" file rest line code
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  code=$(locator_assertion_source "$file" "$line")
  [[ -n "$code" ]] || return 1
  printf '%s\n' "$code" |
    scanner_rg -q '(^|[^A-Za-z0-9_$])(fs[.](rm|unlink)|rm|unlink)[[:space:]]*\(' &&
    return 1
  case "$mode" in
    empty)
      printf '%s\n' "$code" |
        scanner_rg -qP '\.catch\s*(?:\?\.\s*)?\(\s*(?:(?:async\s*)?\(\)\s*=>\s*\{\s*\}|(?:async\s+)?function(?:\s+[A-Za-z_$][A-Za-z0-9_$]*)?\s*\(\s*\)\s*\{\s*\})\s*,?\s*\)'
      ;;
    parameterized)
      printf '%s\n' "$code" |
        scanner_rg -qP '\.catch\s*(?:\?\.\s*)?\(\s*(?:(?:async\s*)?(?:\([^)]*[A-Za-z_$][^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>|(?:async\s+)?function(?:\s+[A-Za-z_$][A-Za-z0-9_$]*)?\s*\([^)]*[A-Za-z_$][^)]*\))'
      ;;
    fallback)
      printf '%s\n' "$code" |
        scanner_rg -qP '\.catch\s*(?:\?\.\s*)?\(\s*(?:(?:async\s*)?\(\)\s*=>(?!\s*\{\s*\}\s*,?\s*\))|(?:async\s+)?function(?:\s+[A-Za-z_$][A-Za-z0-9_$]*)?\s*\(\s*\)\s*\{(?!\s*\}))'
      ;;
    *) return 1 ;;
  esac
}

swallowed_assertion_hit_matches() {
  local hit="$1" mode="$2" file rest line code binding
  file=${hit%%:*}
  rest=${hit#*:}
  line=${rest%%:*}
  if [[ "$mode" == "all-settled" ]]; then
    code=$(locator_assertion_source "$file" "$line")
    printf '%s\n' "$code" |
      scanner_rg -q "Promise[.]allSettled[[:space:]]*[(].*[.](${PLAYWRIGHT_ASYNC_MATCHERS})[[:space:]]*[(]" ||
      return 1
  else
    code=$(locator_assertion_source "$file" "$line")
    printf '%s\n' "$code" |
      scanner_rg -q 'finally[[:space:]]*\{[^}]*\breturn\b' ||
      return 1
    code="$code $(awk -v first="$((line > 40 ? line - 40 : 1))" -v last="$((line - 1))" '
      function executable_source(s,    out, i, c, nchar) {
        out = ""
        for (i = 1; i <= length(s); i++) {
          c = substr(s, i, 1)
          nchar = substr(s, i + 1, 1)
          if (lex_block) {
            if (c == "*" && nchar == "/") { lex_block = 0; i++ }
            continue
          }
          if (lex_quote != "") {
            if (lex_escape) lex_escape = 0
            else if (c == "\\") lex_escape = 1
            else if (c == lex_quote) lex_quote = ""
            continue
          }
          if (c == "\"" || c == "\047" || c == "`") { lex_quote = c; continue }
          if (c == "/" && nchar == "*") { lex_block = 1; i++; continue }
          if (c == "/" && nchar == "/") break
          out = out c
        }
        return out
      }
      NR <= last {
        source = executable_source($0)
        if (NR >= first) print source
      }
      NR >= last { exit }
    ' "$file" 2>/dev/null | tr '\n' ' ')"
    printf '%s\n' "$code" |
      scanner_rg -q "[.](${PLAYWRIGHT_ASYNC_MATCHERS})[[:space:]]*[(]" ||
      return 1
  fi
  while IFS= read -r binding; do
    [[ -n "$binding" ]] || continue
    playwright_expect_binding "$file" "$binding" "$line" && return 0
  done < <(printf '%s\n' "$code" |
    scanner_rg -o '[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*\(' |
    sed -E 's/[[:space:]]*\($//' |
    sort -u)
  return 1
}

run_check() {
  local severity="$1"
  local check_id="$2"
  local title="$3"
  local pattern="$4"
  local glob="$5"
  local output="" p0_unproven_output="" p1_unproven_output=""

  local raw_output
  # Include globs: a `;`-separated list in $glob becomes multiple --glob includes (rg unions
  # them). This lets one check cover both a basename suffix (e.g. *.cy.js) and a path-based
  # location (e.g. cypress/integration/**/*.js — the legacy Cypress layout that has no
  # .cy./.spec./.test. suffix and was previously invisible to the scanner).
  local -a include_globs=()
  local _g _ifs_save="$IFS"
  IFS=';'
  for _g in $glob; do include_globs+=(--glob "$_g"); done
  IFS="$_ifs_save"
  # NOTE: ripgrep gives precedence to later globs — the include glob(s) MUST come first
  # so the negations below always win (a basename include declared last would re-include
  # files inside excluded dirs; this previously let vendored dist/ hits through on repos
  # that don't gitignore their build output).
  allocate_temp _rg_capture
  allocate_temp _rg_error
  allocate_temp _rg_limit
  capture_bounded_command "$_rg_capture" "$_rg_error" "$_rg_limit" "" \
    "$RG_BIN" -nP -H --color never --hidden --no-ignore \
    "${include_globs[@]}" \
    --glob '!**/node_modules/**' \
    --glob '!**/.git/**' \
    --glob '!**/playwright-report/**' \
    --glob '!**/cypress/reports/**' \
    --glob '!**/test-results/**' \
    --glob '!**/dist/**' \
    --glob '!**/build/**' \
    --glob '!**/.next/**' \
    --glob '!**/out/**' \
    --glob '!**/coverage/**' \
    --glob '!*.min.js' \
    --glob '!*.min.ts' \
    ${EVAL_FIXTURE_EXCLUDES[@]+"${EVAL_FIXTURE_EXCLUDES[@]}"} \
    "$pattern" -- "$ROOT"
  local _rg_rc="$BOUNDED_COMMAND_RC"
  if [[ "$_rg_rc" -gt 1 && "$_rg_rc" -ne 141 ]]; then
    printf 'error: Tier 3 ripgrep failed for %s %s (exit %s)\n' "$check_id" "$title" "$_rg_rc" >&2
    sed -n '1,80p' "$_rg_capture" | sanitize_evidence >&2
    rm -f "$_rg_capture" "$_rg_error" "$_rg_limit"
    exit 2
  fi
  if [[ -n "$BOUNDED_LIMIT_KIND" ]]; then
    printf 'INCOMPLETE: Tier 3 %s %s exceeded E2E_SMELL_MAX_RULE_%s=%s while streaming raw candidates; this rule emitted no findings and no final Summary was emitted. Narrow the scan root or raise the bounded limit.\n' \
      "$check_id" "$title" \
      "$([[ "$BOUNDED_LIMIT_KIND" == hits ]] && printf HITS || printf BYTES)" \
      "$([[ "$BOUNDED_LIMIT_KIND" == hits ]] && printf '%s' "$E2E_SMELL_MAX_RULE_HITS" || printf '%s' "$E2E_SMELL_MAX_RULE_BYTES")" >&2
    rm -f "$_rg_capture" "$_rg_error" "$_rg_limit"
    exit 2
  fi
  if [[ "$_rg_rc" -eq 141 || "$BOUNDED_HEAD_RC" -ne 0 || "$BOUNDED_FILTER_RC" -ne 0 ]]; then
    printf 'error: Tier 3 output limiter failed for %s %s (rg %s, head %s, filter %s)\n' \
      "$check_id" "$title" "$_rg_rc" "$BOUNDED_HEAD_RC" "$BOUNDED_FILTER_RC" >&2
    rm -f "$_rg_capture" "$_rg_error" "$_rg_limit"
    exit 2
  fi
  raw_output=$(cat "$_rg_capture")
  rm -f "$_rg_capture" "$_rg_error" "$_rg_limit"
  if [[ -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _bounded_hit; do
      _bounded_file=${_bounded_hit%%:*}
      absolute_hit_file "$_bounded_file" >/dev/null 2>&1 &&
        printf '%s\n' "$_bounded_hit"
    done)
  fi

  # The #16 sweep starts at the action line, then classifies its bounded
  # receiver chain. Keeping classification here preserves all shared filters:
  # E2E scope, JUSTIFIED, lint dedupe, Promise.all/race, and severity accounting.
  local flags=",${6:-},"
  if [[ "$flags" == *",action-direct,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _action_hit; do
      _action_file=${_action_hit%%:*}
      _action_rest=${_action_hit#*:}
      _action_line=${_action_rest%%:*}
      if missing_await_action_hit_matches "$_action_hit" direct &&
        playwright_page_receiver_proven_at "$_action_file" "$_action_line" page; then
        printf '%s\n' "$_action_hit"
      fi
    done)
  elif [[ "$flags" == *",action-variable,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _action_hit; do
      _action_file=${_action_hit%%:*}
      _action_rest=${_action_hit#*:}
      _action_line=${_action_rest%%:*}
      if missing_await_action_hit_matches "$_action_hit" variable; then
        printf '%s\n' "$_action_hit"
      elif missing_await_action_hit_matches "$_action_hit" direct &&
        ! playwright_page_receiver_proven_at "$_action_file" "$_action_line" page; then
        printf '%s\n' "$_action_hit"
      fi
    done)
  elif [[ "$flags" == *",action-deferred,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _action_hit; do
      missing_await_action_hit_matches "$_action_hit" deferred &&
        printf '%s\n' "$_action_hit"
    done)
  elif [[ "$flags" == *",focused-call,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _focused_hit; do
      focused_test_hit_matches "$_focused_hit" &&
        printf '%s\n' "$_focused_hit"
    done)
  elif [[ "$flags" == *",focused-alias-call,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _focused_hit; do
      focused_test_alias_hit_matches "$_focused_hit" &&
        printf '%s\n' "$_focused_hit"
    done)
  elif [[ "$flags" == *",missing-expect,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _expect_hit; do
      missing_await_expect_hit_matches "$_expect_hit" &&
        printf '%s\n' "$_expect_hit"
    done)
  elif [[ "$flags" == *",retry-expect,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _expect_hit; do
      retry_expect_hit_matches "$_expect_hit" &&
        printf '%s\n' "$_expect_hit"
    done)
  elif [[ "$flags" == *",empty-catch,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _catch_hit; do
      empty_catch_hit_matches "$_catch_hit" &&
        printf '%s\n' "$_catch_hit"
    done)
  elif [[ "$flags" == *",empty-catch-best-effort,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _catch_hit; do
      empty_catch_best_effort_hit_matches "$_catch_hit" &&
        printf '%s\n' "$_catch_hit"
    done)
  elif [[ "$flags" == *",empty-catch-unresolved-outcome,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _catch_hit; do
      empty_catch_unresolved_outcome_hit_matches "$_catch_hit" &&
        printf '%s\n' "$_catch_hit"
    done)
  elif [[ "$flags" == *",empty-catch-any,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _catch_hit; do
      catch_callback_hit_matches "$_catch_hit" empty &&
        printf '%s\n' "$_catch_hit"
    done)
  elif [[ "$flags" == *",catch-fallback,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _catch_hit; do
      catch_callback_hit_matches "$_catch_hit" fallback &&
        printf '%s\n' "$_catch_hit"
    done)
  elif [[ "$flags" == *",catch-parameterized,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _catch_hit; do
      catch_callback_hit_matches "$_catch_hit" parameterized &&
        printf '%s\n' "$_catch_hit"
    done)
  elif [[ "$flags" == *",swallowed-all-settled,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _swallowed_hit; do
      swallowed_assertion_hit_matches "$_swallowed_hit" all-settled &&
        printf '%s\n' "$_swallowed_hit"
    done)
  elif [[ "$flags" == *",swallowed-finally-return,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _swallowed_hit; do
      swallowed_assertion_hit_matches "$_swallowed_hit" finally-return &&
        printf '%s\n' "$_swallowed_hit"
    done)
  elif [[ "$flags" == *",playwright-wait-timeout,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _wait_hit; do
      playwright_wait_timeout_hit_matches "$_wait_hit" &&
        printf '%s\n' "$_wait_hit"
    done)
  elif [[ "$flags" == *",zero-timeout,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _timeout_hit; do
      zero_timeout_hit_matches "$_timeout_hit" &&
        printf '%s\n' "$_timeout_hit"
    done)
  elif [[ "$flags" == *",force-action,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _force_hit; do
      force_action_hit_matches "$_force_hit" &&
        printf '%s\n' "$_force_hit"
    done)
  elif [[ "$flags" == *",serial-configure,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _serial_hit; do
      serial_configure_hit_matches "$_serial_hit" &&
        printf '%s\n' "$_serial_hit"
    done)
  elif [[ "$flags" == *",cypress-action-chain,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _chain_hit; do
      cypress_action_chain_hit_matches "$_chain_hit" &&
        printf '%s\n' "$_chain_hit"
    done)
  elif [[ "$flags" == *",positive-attached,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | filter_positive_to_be_attached_hits)
  elif [[ "$flags" == *",executable-line,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _executable_hit; do
      executable_hit_matches "$_executable_hit" "$pattern" &&
        printf '%s\n' "$_executable_hit"
    done)
  elif [[ "$flags" == *",immutable-computed-truthy,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _computed_hit; do
      immutable_computed_truthy_hit_matches "$_computed_hit" &&
        printf '%s\n' "$_computed_hit"
    done)
  elif [[ "$flags" == *",cypress-numeric-wait,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _wait_hit; do
      cypress_numeric_wait_hit_matches "$_wait_hit" &&
        printf '%s\n' "$_wait_hit"
    done)
  elif [[ "$flags" == *",unresolved-locator-assertion,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _locator_hit; do
      unresolved_locator_assertion_hit_matches "$_locator_hit" &&
        printf '%s\n' "$_locator_hit"
    done)
  elif [[ "$flags" == *",locator-assertion,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _locator_hit; do
      locator_assertion_hit_matches "$_locator_hit" &&
        printf '%s\n' "$_locator_hit"
    done)
  elif [[ "$flags" == *",wrapped-locator-assertion,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _locator_hit; do
      wrapped_locator_assertion_hit_matches "$_locator_hit" &&
        printf '%s\n' "$_locator_hit"
    done)
  elif [[ "$flags" == *",generic-getby-assertion,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _locator_hit; do
      generic_getby_assertion_hit_matches "$_locator_hit" &&
        printf '%s\n' "$_locator_hit"
    done)
  elif [[ "$flags" == *",identifier-locator-assertion,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _locator_hit; do
      identifier_locator_assertion_hit_matches "$_locator_hit" &&
        printf '%s\n' "$_locator_hit"
    done)
  elif [[ "$flags" == *",member-locator-assertion,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _locator_hit; do
      member_locator_assertion_hit_matches "$_locator_hit" &&
        printf '%s\n' "$_locator_hit"
    done)
  elif [[ "$flags" == *",conditional-assertion,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _conditional_hit; do
      conditional_assertion_hit_matches "$_conditional_hit" &&
        printf '%s\n' "$_conditional_hit"
    done)
  elif [[ "$flags" == *",credential-candidate,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _credential_hit; do
      hardcoded_credential_hit_matches "$_credential_hit" &&
        printf '%s\n' "$_credential_hit"
    done)
  elif [[ "$flags" == *",initialized-module-state,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _state_hit; do
      initialized_module_state_hit_matches "$_state_hit" &&
        printf '%s\n' "$_state_hit"
    done)
  elif [[ "$flags" == *",one-shot-page-url,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _url_hit; do
      one_shot_page_url_hit_matches "$_url_hit" &&
        printf '%s\n' "$_url_hit"
    done)
  elif [[ "$flags" == *",soft-expect,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _soft_hit; do
      soft_expect_hit_matches "$_soft_hit" &&
        printf '%s\n' "$_soft_hit"
    done)
  elif [[ "$flags" == *",direct-page-api,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _page_hit; do
      direct_page_api_hit_matches "$_page_hit" &&
        printf '%s\n' "$_page_hit"
    done)
  elif [[ "$flags" == *",triage-page-api,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _page_hit; do
      triage_page_api_hit_matches "$_page_hit" &&
        printf '%s\n' "$_page_hit"
    done)
  fi
  if [[ "$flags" == *",unresolved-test-source,"* && -n "$raw_output" ]]; then
    raw_output=$(printf '%s\n' "$raw_output" | while IFS= read -r _unresolved_hit; do
      _unresolved_file=${_unresolved_hit%%:*}
      if source_has_unresolved_test_import "$_unresolved_file" &&
        ! file_has_resolved_framework_reference "$_unresolved_file"; then
        printf '%s\n' "$_unresolved_hit"
      fi
    done)
  fi

  # Filter out matches inside single-line `//` comments — Phase 1 limitation, see SKILL.md.
  # Format from rg -n: <path>:<line>:<content>. Strip first two fields, check if content (after
  # leading whitespace) starts with //. Doesn't catch trailing comments or block comments — those
  # remain Phase 2 LLM responsibility.
  output=$(printf '%s\n' "$raw_output" | awk -F: '
    NF < 3 { next }
    {
      content = $3
      for (i = 4; i <= NF; i++) content = content ":" $i
      stripped = content
      sub(/^[[:space:]]+/, "", stripped)
      if (substr(stripped, 1, 2) == "//") next
      print
    }')

  # Phase-0 scope filter: drop hits in files that carry no Playwright/Cypress marker at all
  # (see file_in_e2e_scope above). Runs before the JUSTIFIED walk so out-of-scope files never
  # cost per-hit sed/awk work.
  if [[ -n "$output" ]]; then
    local _sf _scopekeep
    allocate_temp _scopekeep
    while IFS= read -r _sf; do
      [[ -z "$_sf" ]] && continue
      if [[ "$(scope_status "$_sf")" == "IN" ]]; then
        printf '%s\n' "$_sf" >> "$_scopekeep"
      elif [[ "$check_id" == '#7' ]] && source_has_unresolved_test_import "$_sf"; then
        printf '%s\n' "$_sf" >> "$_scopekeep"
      elif [[ "$flags" == *",unresolved-test-source,"* ]] &&
        source_has_unresolved_test_import "$_sf"; then
        printf '%s\n' "$_sf" >> "$_scopekeep"
      elif [[ "$severity" == "P0" &&
              "$flags" == *",triage,"* ]] &&
        source_has_unresolved_test_import "$_sf"; then
        printf '%s\n' "$_sf" >> "$_scopekeep"
      elif [[ "$flags" == *",playwright-only,"* &&
              "$flags" == *",triage,"* ]] &&
        source_has_unresolved_test_import "$_sf"; then
        printf '%s\n' "$_sf" >> "$_scopekeep"
      fi
    done <<< "$(printf '%s\n' "$output" | awk -F: '{print $1}' | sort -u)"
    output=$(printf '%s\n' "$output" | awk -F: 'NR==FNR { if ($0 != "") k[$0] = 1; next } k[$1] { print }' "$_scopekeep" -)
    rm -f "$_scopekeep"
  fi

  # Framework applicability is narrower than general E2E scope. A Cypress path
  # keeps a file in the review, but does not make Playwright-only API matches
  # authoritative. Mixed files pass when Playwright provenance is also present.
  if [[ "$flags" == *",playwright-only,"* && -n "$output" ]]; then
    local _pf _playwrightkeep
    allocate_temp _playwrightkeep
    while IFS= read -r _pf; do
      [[ -z "$_pf" ]] && continue
      if file_in_playwright_scope "$_pf" ||
        { [[ "$flags" == *",triage,"* ]] &&
          source_has_unresolved_test_import "$_pf"; }; then
        printf '%s\n' "$_pf" >> "$_playwrightkeep"
      fi
    done <<< "$(printf '%s\n' "$output" | awk -F: '{print $1}' | sort -u)"
    output=$(printf '%s\n' "$output" | awk -F: 'NR==FNR { if ($0 != "") k[$0] = 1; next } k[$1] { print }' "$_playwrightkeep" -)
    rm -f "$_playwrightkeep"
  fi

  if [[ "$flags" == *",cypress-only,"* && -n "$output" ]]; then
    local _cf _cypressonlykeep
    allocate_temp _cypressonlykeep
    while IFS= read -r _cf; do
      [[ -z "$_cf" ]] && continue
      file_in_cypress_scope "$_cf" &&
        printf '%s\n' "$_cf" >> "$_cypressonlykeep"
    done <<< "$(printf '%s\n' "$output" | awk -F: '{print $1}' | sort -u)"
    output=$(printf '%s\n' "$output" | awk -F: 'NR==FNR { if ($0 != "") k[$0] = 1; next } k[$1] { print }' "$_cypressonlykeep" -)
    rm -f "$_cypressonlykeep"
  fi

  # Cypress command-model sub-rules must never classify Playwright's normal async
  # test callbacks. #10e/#10f include `cy` on the hit line, but keep one shared
  # file-level guard for all three sub-rules and mixed naming conventions.
  case "$check_id" in
    '#10d'|'#10e'|'#10f')
      if [[ -n "$output" ]]; then
        local _cf _cypresskeep
        allocate_temp _cypresskeep
        while IFS= read -r _cf; do
          [[ -z "$_cf" ]] && continue
          if file_in_cypress_scope "$_cf"; then printf '%s\n' "$_cf" >> "$_cypresskeep"; fi
        done <<< "$(printf '%s\n' "$output" | awk -F: '{print $1}' | sort -u)"
        output=$(printf '%s\n' "$output" | awk -F: 'NR==FNR { if ($0 != "") k[$0] = 1; next } k[$1] { print }' "$_cypresskeep" -)
        rm -f "$_cypresskeep"
      fi
      ;;
  esac

  # #10d is only a real command-model candidate when the async callback also
  # queues Cypress commands. The signature grep supplies the callback start;
  # inspect a bounded body window to drop native-Promise-only async tests.
  # Phase 2 still confirms callback boundaries for deeply nested bodies.
  if [[ "$check_id" == '#10d' && -n "$output" ]]; then
    output=$(printf '%s\n' "$output" | while IFS= read -r _hit; do
      _hf=${_hit%%:*}
      _rest=${_hit#*:}
      _hl=${_rest%%:*}
      _end=$((_hl + 20))
      _start=$(sed -n "${_hl}p" "$_hf" 2>/dev/null)
      # Expression-bodied or fully one-line callbacks end on the hit line. Do
      # not let a later sibling test's cy.* command leak into this candidate.
      if ! printf '%s\n' "$_start" | scanner_rg -q '(^|[^A-Za-z0-9_])cy\.[A-Za-z_$][A-Za-z0-9_$]*\(' &&
        printf '%s\n' "$_start" | scanner_rg -q '(}\)|=>[^{}]*\))[[:space:]]*;?[[:space:]]*$'; then
        continue
      fi
      if sed -n "${_hl},${_end}p" "$_hf" 2>/dev/null |
        awk 'NR > 1 && /^[[:space:]]*}\);?[[:space:]]*$/ { print; exit } { print }' |
        scanner_rg -q '(^|[^A-Za-z0-9_])cy\.[A-Za-z_$][A-Za-z0-9_$]*\('; then
        printf '%s\n' "$_hit"
      fi
    done)
  fi

  # `// JUSTIFIED: <reason>` handling (mechanical part): accept only a lexical
  # line comment with a non-empty rationale on the hit line or in the contiguous
  # comment block above it. String/template text, empty markers, `NOT JUSTIFIED`,
  # and block comments never suppress a finding.
  # P1/P2 findings are suppressed; P0 findings move to the candidate gate until
  # externally verified. No-exemption contract for #7: a committed focused test is never justifiable
  # (grep-patterns.md / pattern-reference.md), so JUSTIFIED must not silence it.
  if [[ -n "$output" && "$check_id" != '#7' ]]; then
    output=$(printf '%s\n' "$output" | while IFS= read -r _hit; do
      _hf=${_hit%%:*}
      _rest=${_hit#*:}
      _hl=${_rest%%:*}
      if _line_is_justified "$_hf" "$_hl"; then
        record_justified_suppression "$severity" "$check_id" "$_hf" "$_hl"
        continue
      fi
      printf '%s\n' "$_hit"
    done)
  fi

  if [[ "$flags" == *",boolean-consumed,"* && -n "$output" ]]; then
    output=$(printf '%s\n' "$output" | while IFS= read -r _hit; do
      boolean_state_hit_context "$_hit" consumed || printf '%s\n' "$_hit"
    done)
  elif [[ "$flags" == *",boolean-if,"* && -n "$output" ]]; then
    output=$(printf '%s\n' "$output" | while IFS= read -r _hit; do
      boolean_state_hit_context "$_hit" if && printf '%s\n' "$_hit"
    done)
  fi

  # Tier 1 and Tier 2 remain independent of project lint policy, then exact
  # file/line/rule-class duplicates are removed here from the bundled regex tier.
  if [[ -n "$output" ]]; then
    local _dclass _df _drest _dl _dabs
    _dclass=$(dedupe_class_for_pattern "$check_id")
    if [[ -n "$_dclass" ]]; then
      output=$(printf '%s\n' "$output" | while IFS= read -r _hit; do
        _df=${_hit%%:*}
        _drest=${_hit#*:}
        _dl=${_drest%%:*}
        _dabs=$(absolute_hit_file "$_df" 2>/dev/null || true)
        if [[ -n "$_dabs" ]] &&
          grep -qFx -e "$_dabs|$_dl|$_dclass" "$STRUCTURAL_HITS_FILE" 2>/dev/null; then
          continue
        fi
        printf '%s\n' "$_hit"
      done)
    fi
  fi

  # Optional e2e content scoping (6th arg == "e2e"): keep hits only in files that carry a real
  # Playwright/Cypress marker. The marker set deliberately ERRS TOWARD INCLUSION (fail-open):
  # a unit file mentioning e.g. `router.page.url()` is admitted and its hits flow to Phase 2,
  # which owns residual unit-test elimination. Tightening here risks silently dropping real specs. Kills Vitest/Jest/RTL unit-test bleed-through — the #1 FP root
  # cause observed across the 77-repo OSS validation corpus. Markers: @playwright/test import,
  # Playwright fixture destructure `async ({ page`, direct `page.<api>` usage, or `cy.<cmd>(`.
  # Promise combinator filter (flag "promise-array"): a Playwright action used as an
  # array element of Promise.all/race/allSettled/any is consumed only when the aggregate
  # itself is syntactically led by `await` or `return`. A bare or assigned aggregate still
  # floats, so its action elements remain visible to the #16 gate/triage path.
  if [[ "$flags" == *",promise-array,"* && -n "$output" ]]; then
    output=$(printf '%s\n' "$output" | while IFS= read -r _hit; do
      _hf=${_hit%%:*}
      _rest=${_hit#*:}
      _hl=${_rest%%:*}
      _inside_promise_array=$(awk -v target="$_hl" '
        function trim(s) {
          sub(/^[[:space:]]+/, "", s)
          sub(/[[:space:]]+$/, "", s)
          return s
        }
        function executable_source(s,    out, i, c, nchar) {
          out = ""
          for (i = 1; i <= length(s); i++) {
            c = substr(s, i, 1)
            nchar = substr(s, i + 1, 1)
            if (promise_block) {
              if (c == "*" && nchar == "/") {
                promise_block = 0
                i++
              }
              continue
            }
            if (promise_quote != "") {
              if (promise_escape) {
                promise_escape = 0
              } else if (c == "\\") {
                promise_escape = 1
              } else if (c == promise_quote) {
                out = out promise_quote promise_quote
                promise_quote = ""
              }
              continue
            }
            if (c == "\"" || c == "\047" || c == "`") {
              promise_quote = c
              continue
            }
            if (c == "/" && nchar == "*") {
              promise_block = 1
              i++
              continue
            }
            if (c == "/" && nchar == "/") break
            out = out c
          }
          return out
        }
        NR > target { exit }
        {
          line = executable_source($0)
          if (!inside && !pending) {
            if (!match(line, /Promise\.(all|race|allSettled|any)[[:space:]]*\(/)) next
            prefix = trim(substr(line, 1, RSTART - 1))
            aggregate_observed = (prefix == "await" || prefix == "return")
            pending = 1
            line = substr(line, RSTART + RLENGTH)
          }
          if (pending && !inside) {
            sub(/^[[:space:]]+/, "", line)
            if (line == "") next
            if (substr(line, 1, 1) != "[") {
              pending = 0
              next
            }
            inside = 1
            pending = 0
            depth = 0
          }
          opens = gsub(/\[/, "[", line)
          closes = gsub(/\]/, "]", line)
          depth += opens - closes
          # The action is consumed even when the array closes later on the
          # same physical line (`Promise.all([locator.click()])`).
          if (NR == target && inside && aggregate_observed) found = 1
          if (inside && depth <= 0) {
            inside = 0
            depth = 0
          }
        }
        END { if (found) print "Y" }
      ' "$_hf" 2>/dev/null)
      [[ "$_inside_promise_array" == "Y" ]] && continue
      printf '%s\n' "$_hit"
    done)
  fi

  if [[ "$flags" == *",e2e,"* && -n "$output" ]]; then
    local _f _keepf
    allocate_temp _keepf
    while IFS= read -r _f; do
      [[ -z "$_f" ]] && continue
      if file_in_e2e_scope "$_f"; then
        printf '%s\n' "$_f" >> "$_keepf"
      elif [[ "$check_id" == '#7' ]] && source_has_unresolved_test_import "$_f"; then
        printf '%s\n' "$_f" >> "$_keepf"
      elif [[ "$severity" == "P0" &&
              "$flags" == *",triage,"* ]] &&
        source_has_unresolved_test_import "$_f"; then
        printf '%s\n' "$_f" >> "$_keepf"
      elif [[ "$flags" == *",playwright-only,"* &&
              "$flags" == *",triage,"* ]] &&
        source_has_unresolved_test_import "$_f"; then
        printf '%s\n' "$_f" >> "$_keepf"
      fi
    done <<< "$(printf '%s\n' "$output" | awk -F: '{print $1}' | sort -u)"
    # BSD awk rejects multiline strings via -v — pass the keep-list as a file instead.
    output=$(printf '%s\n' "$output" | awk -F: 'NR==FNR { if ($0 != "") k[$0] = 1; next } k[$1] { print }' "$_keepf" -)
    rm -f "$_keepf"
  fi

  # Continuation filter (flag "cont"): drop a hit when the previous non-blank line ends
  # with '(' or ',' — the matched line is an argument inside a multi-line expect(...) call,
  # not a dangling statement. Restores detection of semicolonless dangling locators without
  # re-admitting the multi-line continuation false positives.
  if [[ "$flags" == *",cont,"* && -n "$output" ]]; then
    output=$(printf '%s\n' "$output" | while IFS= read -r _hit; do
      _hf=${_hit%%:*}
      _rest=${_hit#*:}
      _hl=${_rest%%:*}
      _prev=""
      if [[ "$_hl" -gt 1 ]]; then
        _prev=$(sed -n "$((_hl - 1))p" "$_hf" 2>/dev/null | sed 's/[[:space:]]*$//')
      fi
      case "$_prev" in
        (*\(|*,) : ;;  # continuation — drop  (leading paren: bash-3.2 case-in-$() parser quirk)
        (*) printf '%s\n' "$_hit" ;;
      esac
    done)
  fi

  abort_on_rg_error
  if [[ "$severity" == "P1" &&
        "$flags" == *",playwright-only,"* &&
        "$flags" != *",triage,"* &&
        -n "$output" ]]; then
    local _p1_proven_output="" _p1_scope_hit _p1_scope_file
    while IFS= read -r _p1_scope_hit; do
      [[ -n "$_p1_scope_hit" ]] || continue
      _p1_scope_file=${_p1_scope_hit%%:*}
      if file_has_playwright_provenance "$_p1_scope_file"; then
        _p1_proven_output="${_p1_proven_output}${_p1_proven_output:+$'\n'}${_p1_scope_hit}"
      else
        p1_unproven_output="${p1_unproven_output}${p1_unproven_output:+$'\n'}${_p1_scope_hit}"
      fi
    done <<< "$output"
    output="$_p1_proven_output"
  fi

  if [[ "$severity" == "P0" &&
        "$flags" != *",triage,"* &&
        -n "$output" ]]; then
    local _proven_output="" _scope_hit _scope_file
    while IFS= read -r _scope_hit; do
      [[ -n "$_scope_hit" ]] || continue
      _scope_file=${_scope_hit%%:*}
      if source_has_unresolved_test_import "$_scope_file" &&
        ! file_has_resolved_framework_reference "$_scope_file"; then
        p0_unproven_output="${p0_unproven_output}${p0_unproven_output:+$'\n'}${_scope_hit}"
      elif file_has_framework_provenance "$_scope_file"; then
        _proven_output="${_proven_output}${_proven_output:+$'\n'}${_scope_hit}"
      else
        p0_unproven_output="${p0_unproven_output}${p0_unproven_output:+$'\n'}${_scope_hit}"
      fi
    done <<< "$output"
    output="$_proven_output"
  fi

  if [[ -n "$p1_unproven_output" ]]; then
    local p1_candidate_count
    p1_candidate_count=$(printf '%s\n' "$p1_unproven_output" | wc -l | tr -d ' ')
    total_hits=$((total_hits + p1_candidate_count))
    llm_triage_hits=$((llm_triage_hits + p1_candidate_count))
    hit_pattern_ids="$hit_pattern_ids $check_id"
    printf '\n[P1?][LLM-TRIAGE] %s Possible %s (framework provenance unproven) (%s hit%s)\n' \
      "$check_id" "$title" "$p1_candidate_count" \
      "$([[ "$p1_candidate_count" == "1" ]] && printf '' || printf 's')"
    printf '%s\n' "$p1_unproven_output" | sanitize_evidence | sed 's/^/  /'
  fi

  if [[ -n "$p0_unproven_output" ]]; then
    local candidate_count
    candidate_count=$(printf '%s\n' "$p0_unproven_output" | wc -l | tr -d ' ')
    total_hits=$((total_hits + candidate_count))
    llm_triage_hits=$((llm_triage_hits + candidate_count))
    p0_candidate_hits=$((p0_candidate_hits + candidate_count))
    hit_pattern_ids="$hit_pattern_ids $check_id"
    printf '\n[P0?][LLM-TRIAGE] %s Possible %s (framework provenance unproven) (%s hit%s)\n' \
      "$check_id" "$title" "$candidate_count" \
      "$([[ "$candidate_count" == "1" ]] && printf '' || printf 's')"
    printf '%s\n' "$p0_unproven_output" | sanitize_evidence | sed 's/^/  /'
  fi

  if [[ -n "$output" ]]; then
    local count sev_label
    count=$(printf '%s\n' "$output" | wc -l | tr -d ' ')
    total_hits=$((total_hits + count))
    # Remember which pattern IDs actually fired, so the closing summary can separate the
    # findings a lint rule could enforce on every commit from the ones only a reviewer catches.
    hit_pattern_ids="$hit_pattern_ids $check_id"
    sev_label="[$severity]"
    if [[ "$flags" == *",triage,"* ]]; then
      # Documented severity is unchanged, but grep alone cannot confirm the context that
      # makes these hits real (e.g. #4b needs destructive-action context — ~90% FP rate on
      # client-rendered apps where positive toBeAttached is a legitimate render-gate).
      # Route to a separate Phase-2 LLM-triage count instead of the p0 exit gate.
      llm_triage_hits=$((llm_triage_hits + count))
      if [[ "$severity" == "P0" ]]; then
        p0_candidate_hits=$((p0_candidate_hits + count))
      fi
      sev_label="[$severity?][LLM-TRIAGE]"
    elif [[ "$severity" == "P0" ]]; then
      p0_hits=$((p0_hits + count))
    else
      p1_hits=$((p1_hits + count))
    fi

    printf '\n%s %s %s (%s hit%s)\n' "$sev_label" "$check_id" "$title" "$count" "$([[ "$count" == "1" ]] && printf '' || printf 's')"
    if [[ "$flags" == *",credential-candidate,"* ]]; then
      printf '%s\n' "$output" | redact_credential_evidence | sanitize_evidence | sed 's/^/  /'
    else
      printf '%s\n' "$output" | sanitize_evidence | sed 's/^/  /'
    fi
  fi
}

# Evaluate every supported JS/TS extension first, then apply the shared
# framework-content scope. This covers custom Playwright testMatch names and
# suffix-less Cypress layouts without admitting unrelated unit/backend files.
FOCUSED_ALIAS_CALL_PATTERN=$(focused_alias_call_pattern)
EXPECT_CALL_PATTERN=$(expect_call_pattern)
run_check P0 '#3' 'Error swallowing via empty catch (E2E scope)' '\.catch([^A-Za-z0-9_$]|$)' "$ALL_CODE_GLOB" 'e2e,empty-catch'
run_check P0 '#3' 'Possible best-effort setup, teardown, or cleanup empty catch' '\.catch([^A-Za-z0-9_$]|$)' "$ALL_CODE_GLOB" 'e2e,triage,empty-catch-best-effort'
run_check P0 '#3' 'Possible empty catch with unresolved test-outcome impact' '\.catch([^A-Za-z0-9_$]|$)' "$ALL_CODE_GLOB" 'e2e,triage,empty-catch-unresolved-outcome'
run_check P0 '#3' 'Possible error swallowing in unresolved test-fixture source' '\.catch([^A-Za-z0-9_$]|$)' "$ALL_CODE_GLOB" 'triage,empty-catch-any,unresolved-test-source'
# Non-empty catch callbacks can be swallowing, cleanup, or an intentional fallback.
# Keep framework-proven support/POM files visible, but leave that semantic call to Phase 2.
run_check P0 '#3' 'Possible error swallowing via catch fallback' '\.catch([^A-Za-z0-9_$]|$)' "$ALL_CODE_GLOB" 'e2e,triage,catch-fallback'
run_check P0 '#3' 'Possible parameterized catch swallowing' '\.catch([^A-Za-z0-9_$]|$)' "$ALL_CODE_GLOB" 'e2e,triage,catch-parameterized'
run_check P0 '#3' 'Possible assertion failure swallowed by Promise.allSettled' 'Promise[.]allSettled[[:space:]]*\(' "$ALL_CODE_GLOB" 'e2e,triage,swallowed-all-settled'
run_check P0 '#3' 'Possible assertion failure masked by finally return' '\bfinally\b' "$ALL_CODE_GLOB" 'e2e,triage,swallowed-finally-return'
run_check P0 '#7' 'Focused test committed' '(\.[^;\n]{0,80}\bonly|\[[^]\n]{0,80}\])' "$ALL_CODE_GLOB" 'e2e,focused-call'
run_check P0 '#7' 'Focused test alias committed' "$FOCUSED_ALIAS_CALL_PATTERN" "$ALL_CODE_GLOB" 'e2e,focused-alias-call'
run_check P1 '#9' 'Playwright hard-coded sleep' 'waitForTimeout' "$ALL_CODE_GLOB" 'e2e,playwright-wait-timeout,playwright-only'
run_check P1 '#9b' 'Cypress hard-coded sleep' 'cy\.wait\(' "$ALL_CODE_GLOB" 'cypress-numeric-wait'
run_check P1 '#9b' 'Possible variable Cypress wait' 'cy\.wait\([[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*\)' "$ALL_CODE_GLOB" 'e2e,triage,cypress-only,executable-line'
run_check P1 '#6' 'Raw DOM query inside test code' 'document\.(querySelector(?:All)?|getElementById)' "$ALL_CODE_GLOB" 'e2e,triage,executable-line'

run_check P0 '#4a' 'Always-true numeric assertion' 'toBeGreaterThanOrEqual\(0\)' "$ALL_CODE_GLOB" 'e2e,triage'
# #4b is grep-undecidable: positive toBeAttached is only vacuous when a destructive action
# should have removed the element; on client-rendered apps it is usually a legitimate
# render-gate (field data: ~90% FP). Phase 2 confirms destructive-action context.
run_check P1 '#4b' 'Vacuous toBeAttached assertion (positive form only; Phase 2 confirms destructive-action context)' '\btoBeAttached\b' "$ALL_CODE_GLOB" 'e2e,triage,positive-attached'
# #4c-4e: one-shot reads (`expect(await <locator>.textContent()/count()/inputValue()...)`
# + sync matcher) are P1 one-shot assertions, NOT #15 — the await resolves a value, nothing
# floats. The leading `(?:...)*` group admits wrapped forms (`expect((await ...).trim())`,
# `expect(Number(await ...))`, `expect(!(await ...))`) that field runs showed being
# misfiled under #15 by the old locator-substring heuristic.
run_check P1 '#4c-4e' 'One-shot Playwright state/content assertion' 'expect\((?:[!(\s+-]|[A-Za-z_$][\w$.]*\()*await\b.*\.(isVisible|isDisabled|isEnabled|isChecked|isHidden|isEditable|textContent|innerText|getAttribute|inputValue|allTextContents|allInnerTexts|count)\([^)]*\)\)' "$ALL_CODE_GLOB" 'triage,playwright-only'
run_check P0 '#4f' 'Locator always-true assertion (truthy/defined/not-null)' "$EXPECT_CALL_PATTERN" "$ALL_CODE_GLOB" 'e2e,locator-assertion'
run_check P0 '#4f' 'Possible wrapped Locator truthiness assertion' "$EXPECT_CALL_PATTERN" "$ALL_CODE_GLOB" 'e2e,triage,wrapped-locator-assertion'
run_check P0 '#4f' 'Possible Locator truthiness in unresolved test-fixture source' "$EXPECT_CALL_PATTERN" "$ALL_CODE_GLOB" 'triage,unresolved-locator-assertion,unresolved-test-source'
run_check P0 '#4f' 'Possible generic getBy/query truthiness assertion' "$EXPECT_CALL_PATTERN" "$ALL_CODE_GLOB" 'e2e,triage,generic-getby-assertion'
run_check P0 '#4f' 'Possible Locator/POM identifier truthiness assertion' "$EXPECT_CALL_PATTERN" "$ALL_CODE_GLOB" 'e2e,triage,identifier-locator-assertion'
run_check P0 '#4f' 'Possible Locator/POM member truthiness assertion' "$EXPECT_CALL_PATTERN" "$ALL_CODE_GLOB" 'e2e,triage,member-locator-assertion'
run_check P0 '#4f' 'Possible optional/computed Locator truthiness assertion' '(?:expect[[:space:]]*(?:\?\.[[:space:]]*\(|\[[[:space:]]*['"'"'\"](?:call|expect)['"'"'\"][[:space:]]*\][[:space:]]*\())[^;\n]*(?:toBeTruthy|toBeDefined|toBeNull|toBeUndefined)' "$ALL_CODE_GLOB" 'e2e,triage,playwright-only'
run_check P0 '#4f' 'Possible constant-computed truthiness matcher' 'expect[[:space:]]*\([^;\n]*\)[[:space:]]*\[[[:space:]]*['"'"'\"](?:toBeTruthy|toBeDefined)['"'"'\"][[:space:]]*\]' "$ALL_CODE_GLOB" 'e2e,triage'
run_check P0 '#4f' 'Possible immutable computed truthiness matcher' 'expect[[:space:]]*\([^;\n]*\)[[:space:]]*\[[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*\][[:space:]]*\(' "$ALL_CODE_GLOB" 'e2e,triage,immutable-computed-truthy'
run_check P0 '#4f' 'Cypress jQuery object always-exists assertion' 'expect[[:space:]]*\([[:space:]]*Cypress[.]\$[[:space:]]*\([^;\n]*\)[[:space:]]*\)[[:space:]]*[.](?:to[.]exist|to[.]be[.]ok|toBeTruthy[[:space:]]*\()' "$ALL_CODE_GLOB" 'e2e,executable-line'
run_check P1 '#4g' 'Zero-timeout retry/deadline hazard' '(?:timeout|["'"'"']timeout["'"'"'])\s*:\s*0' "$ALL_CODE_GLOB" 'e2e,zero-timeout'
run_check P1 '#4h' 'One-shot page.url assertion' '^[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*(?:[[:space:]]*\.[[:space:]]*expect)?[[:space:]]*\([^;\n]*[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*\.[[:space:]]*url[[:space:]]*\(' "$ALL_CODE_GLOB" 'playwright-only,one-shot-page-url'
# #4i: an absence assertion is satisfied by a locator that matches NOTHING. Playwright defines
# toBeHidden as "either does not resolve to any DOM node, or resolves to a non-visible one",
# and not.toBeVisible() is the inverse of "attached AND visible" — so a selector that rotted
# (renamed class, framework migration, component rewrite) keeps passing forever while proving
# nothing. Grep finds the assertion but cannot tell whether the same locator is ever proven
# able to match, so this is LLM-TRIAGE: Phase 2 looks for a positive assertion or an action on
# that locator earlier in the test (or its beforeEach) before reporting. Empty-state tests are
# the main legitimate shape and are expected to dominate raw hits.
run_check P1 '#4i' 'Absence assertion never proven able to match' '\.not\.toBeVisible\(|\.not\.toBeAttached\(|(?<!\.not)\.toBeHidden\(|(?<!\.not)\.toHaveCount\(\s*0\s*\)|\.should\(.[^)]*not\.(exist|be\.visible)' "$ALL_CODE_GLOB" 'triage'

# Grep cannot see whether the branch body contains an assertion or only a setup/navigation
# action. Keep every candidate visible, but outside the mechanical P0 exit gate.
run_check P0 '#5a' 'Conditional assertion bypass' 'if.*(isVisible\(|is\(.*:visible.*\))' "$ALL_CODE_GLOB" 'triage'
run_check P0 '#5a' 'Conditional assertion bypass' '^\s*await .*\.(isVisible|isEnabled|isChecked|isDisabled|isEditable|isHidden)\([^)]*\)\s*;?\s*(//.*)?$' "$ALL_CODE_GLOB" 'e2e,triage,boolean-if'
run_check P0 '#5a' 'Conditional branch contains assertion' '^[[:space:]]*if\b' "$ALL_CODE_GLOB" 'e2e,triage,conditional-assertion'
run_check P0 '#5a' 'Logical/ternary conditional assertion candidate' '(&&|\?)[^;\n]*(expect|assert|\.should)\s*[\.(]' "$ALL_CODE_GLOB" 'e2e,triage,executable-line'
run_check P1 '#5b' 'Forced actionability bypass' '(?:force|["'"'"']force["'"'"'])\s*:\s*true' "$ALL_CODE_GLOB" 'e2e,force-action'
# A standalone locator/boolean is dead code, but grep cannot prove the P0
# condition: that this discarded expression was the scenario's only intended
# verification. Keep candidates visible for Phase 2 without entering the
# mechanical P0 gate; real assertions or a following action on the same locator
# are explicit skip guards in the #8 contract.
run_check P0 '#8a' 'Dangling Playwright locator statement' '^\s*(await\s+)?page\.(locator|getBy[A-Za-z]+)\(([^()]|\([^()]*\))*\)\s*;?\s*(//.*)?$' "$ALL_CODE_GLOB" 'triage,cont,playwright-only'
run_check P0 '#8b' 'Boolean state result discarded' '^\s*await .*\.(isVisible|isEnabled|isChecked|isDisabled|isEditable|isHidden)\([^)]*\)\s*;?\s*(//.*)?$' "$ALL_CODE_GLOB" 'e2e,triage,boolean-consumed,playwright-only'
run_check P1 '#10a' 'Positional selector' '\.(nth\(|first\(\)|last\(\))' "$ALL_CODE_GLOB" 'triage'
run_check P1 '#10b' 'Serial Playwright suite' '\.describe\.serial\(' "$ALL_CODE_GLOB" 'playwright-only,executable-line'
run_check P1 '#10b' 'Serial Playwright suite' '\.describe[[:space:]]*\.configure[[:space:]]*\(' "$ALL_CODE_GLOB" 'playwright-only,serial-configure'
# #10c matches ONLY page-scoped getByRole/getByLabel/getByPlaceholder calls that carry a name:
# and no exact: — the negative lookahead skips exact-qualified calls, and requiring `page.`
# directly excludes container-scoped forms (`x.getByRole(...)`, `page.locator(...).getByRole(...)`).
# Phase 2 LLM confirms the suite renders dynamic text that could substring-collide before flagging.
run_check P1 '#10c' 'Unscoped accessible-name substring match' '(?<![.\w])page\.(getByRole|getByLabel|getByPlaceholder)\((?:(?!exact:)[^)])*name:(?:(?!exact:)[^)])*\)' "$ALL_CODE_GLOB" 'e2e,triage,playwright-only'
run_check P1 '#10c' 'Cypress accessible-name substring match' '\bcy\.(?:findByRole|findByLabelText|findByPlaceholderText)\((?:(?!exact\s*:)[^)])*\bname\s*:(?:(?!exact\s*:)[^)])*\)' "$ALL_CODE_GLOB" 'e2e,triage,cypress-only,executable-line'
run_check P1 '#10d' 'Cypress async callback mixes promises with queued commands' '(?:(?:it|test|specify)\s*\([^;\n]*,\s*async\s*(?:function\b\s*(?:[A-Za-z_$][\w$]*)?\s*\([^)]*\)|(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>)|(?:before|beforeEach|after|afterEach)\s*\(\s*(?:[^,;\n]+,\s*)?async\s*(?:function\b\s*(?:[A-Za-z_$][\w$]*)?\s*\([^)]*\)|(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>))' "$ALL_CODE_GLOB" 'triage'
run_check P1 '#10e' 'Cypress return value assigned outside the command chain' '\b(const|let|var)\s+[A-Za-z_$][\w$]*(?:\s*:[^=;\n]+)?\s*=\s*cy\.(?!spy\(|stub\()' "$ALL_CODE_GLOB"
# Actions are one-shot; assertions chained after them do not retry the action. Phase 2 confirms
# whether the chain can observe stale/detached state before reporting.
run_check P1 '#10f' 'Cypress action followed by an unsafe continued chain' '\.(click|type|check|uncheck|select|selectFile|trigger|scrollIntoView)[[:space:]]*\(' "$ALL_CODE_GLOB" 'triage,cypress-action-chain'
run_check P1 '#14' 'Hardcoded credential candidate' '(?i)(?:(?:password|passwd|secret|credential|token|username|email|auth|validUser|testAdmin|adminUser)[A-Za-z0-9_$-]*[[:space:]]*[:=][[:space:]]*['"'"'"`]|[.](?:fill|type)[[:space:]]*\([^;\n]*['"'"'"`]|(?:^|[^A-Za-z0-9_$])(?:login|signIn)[[:space:]]*\()' "$ALL_CODE_GLOB" 'triage,credential-candidate'
# #15 keeps ONLY unawaited web-first matchers: the trailing matcher whitelist stops the old
# conflation where sync-matcher one-shot reads (e.g. `expect(Number(await getRowCount(page)))
# .toBe(4)` — the `page)` substring) were misfiled as #15 (ag-grid field run: 25 of 33 #15
# hits were really #4c-4e). Matcher-on-next-line splits are covered by Tier 2 (sg-15).
run_check P1 '#15' 'Missing await on Playwright expect' '^[[:space:]]*\(?[[:space:]]*(?:[0-9]+[[:space:]]*,[[:space:]]*)?[A-Za-z_$][A-Za-z0-9_$]*(?:[[:space:]]*\.[[:space:]]*expect)?(?:[[:space:]]|/\*.*?\*/)*\(' "$ALL_CODE_GLOB" 'e2e,missing-expect,playwright-only'
run_check P1 '#15' 'Possible missing await on expect from unresolved test-fixture source' "^[[:space:]]*expect[[:space:]]*\\([^;\\n]*\\)[[:space:]]*[.][[:space:]]*(${PLAYWRIGHT_ASYNC_MATCHERS})[[:space:]]*\\(" "$ALL_CODE_GLOB" 'triage,playwright-only,unresolved-test-source'
run_check P1 '#15' 'Missing await on Playwright retry assertion' '^[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*[[:space:]]*(?:[.][[:space:]]*poll[[:space:]]*[(]|[(])' "$ALL_CODE_GLOB" 'e2e,retry-expect,playwright-only'
# #15 variant: the await is misplaced INSIDE expect() onto the locator (a no-op, since a Locator
# is not thenable) instead of on expect itself, so the web-first matcher Promise is not observed
# or sequenced. The base #15 above skips `expect(await ...` by design, so this
# catches the awaited-locator form. Bounded to web-first matchers so value-resolving reads like
# `expect(await x.isVisible()).toBe(true)` (that is #4c-4e) are not double-flagged.
run_check P1 '#15' 'Missing await on Playwright expect (awaited locator)' "^\\s*(?:[A-Za-z_$][A-Za-z0-9_$]*\\s*\\.\\s*)?expect\\(\\s*await\\b.*\\)\\.(${PLAYWRIGHT_ASYNC_MATCHERS})\\(" "$ALL_CODE_GLOB" 'e2e,playwright-only'
run_check P1 '#15' 'Possible deferred/discarded Playwright expect promise' "^\\s*(?:(?:const|let|var)\\s+[A-Za-z_$][\\w$]*\\s*=\\s*|void\\s+)(?:[A-Za-z_$][A-Za-z0-9_$]*\\s*\\.\\s*)?expect\\(.*\\)\\.(${PLAYWRIGHT_ASYNC_MATCHERS})\\(" "$ALL_CODE_GLOB" 'e2e,triage,playwright-only'
run_check P1 '#15' 'Possible optional/computed Playwright expect promise' "(?:expect[[:space:]]*\\?[[:space:]]*\\.[[:space:]]*\\(|expect[[:space:]]*\\[[[:space:]]*['\"]call['\"][[:space:]]*\\][[:space:]]*\\()[^;\\n]*[.](${PLAYWRIGHT_ASYNC_MATCHERS})[[:space:]]*[(]" "$ALL_CODE_GLOB" 'e2e,triage,playwright-only'
run_check P1 '#16' 'Possible deferred/discarded Playwright action promise' '\.(click|dblclick|tap|fill|clear|type|press|pressSequentially|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|blur|dragTo|drop|dispatchEvent|scrollIntoViewIfNeeded|selectText|screenshot|waitFor|goto|reload|waitForURL|waitForNavigation|goBack|goForward)(?:[[:space:]]|/\*.*?\*/)*\(' "$ALL_CODE_GLOB" 'e2e,triage,promise-array,action-deferred,playwright-only'
run_check P1 '#16' 'Possible optional Playwright action promise' '\.(click|dblclick|tap|fill|clear|type|press|pressSequentially|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|blur|dragTo|drop|dispatchEvent|scrollIntoViewIfNeeded|selectText|screenshot)[[:space:]]*\?\.[[:space:]]*\(' "$ALL_CODE_GLOB" 'e2e,triage,playwright-only'
run_check P1 '#16' 'Possible constant-computed Playwright action promise' '\[[[:space:]]*['"'"'\"](?:click|fill|press|check|waitFor)['"'"'\"][[:space:]]*\][[:space:]]*\(' "$ALL_CODE_GLOB" 'e2e,triage,playwright-only'
run_check P1 '#16' 'Missing await on Playwright action' '\.(click|dblclick|tap|fill|clear|type|press|pressSequentially|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|blur|dragTo|drop|dispatchEvent|scrollIntoViewIfNeeded|selectText|screenshot|waitFor|goto|reload|waitForURL|waitForNavigation|goBack|goForward)(?:[[:space:]]|/\*.*?\*/)*\(' "$ALL_CODE_GLOB" 'e2e,promise-array,action-direct,playwright-only'
# Locator variables and POM properties are the common real-world form that a page.*-only
# regex misses. The broad token is intentionally LLM-TRIAGE: Phase 2 traces the receiver
# to a Playwright Locator before reporting, which avoids gating on arbitrary object methods.
run_check P1 '#16' 'Possible missing await on Locator/POM action' '\.(click|dblclick|tap|fill|clear|type|press|pressSequentially|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|blur|dragTo|drop|dispatchEvent|scrollIntoViewIfNeeded|selectText|screenshot|waitFor|goto|reload|waitForURL|waitForNavigation|goBack|goForward)(?:[[:space:]]|/\*.*?\*/)*\(' "$ALL_CODE_GLOB" 'e2e,triage,promise-array,action-variable,playwright-only'
run_check P1 '#17' 'Discouraged direct Page selector API' '(?<![\w$])page\.(click|dblclick|tap|fill|type|press|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|dispatchEvent|dragAndDrop)\(\s*["'"'"'`]' "$ALL_CODE_GLOB" 'e2e,playwright-only,direct-page-api'
# POMs commonly retain the Page under `this.page` or an aliased/renamed Page-typed
# property. Literal selector actions on those receivers are Playwright-proven by file scope,
# but receiver typing still needs Phase 2 confirmation before a #17 verdict.
run_check P1 '#17' 'Possible discouraged selector-based Page API on POM/aliased receiver' '(?<![\w$.])(?:this\.)?[A-Za-z_$][\w$]*\.(click|dblclick|tap|fill|type|press|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|dispatchEvent|dragAndDrop)\(\s*["'"'"'`]' "$ALL_CODE_GLOB" 'e2e,triage,playwright-only,triage-page-api'
run_check P1 '#17' 'Possible variable selector passed to Page API' '(?<![\w$.])(?:this\.)?[A-Za-z_$][\w$]*\.(click|dblclick|tap|fill|type|press|check|uncheck|setChecked|selectOption|setInputFiles|hover|focus|dispatchEvent|dragAndDrop)\(\s*[A-Za-z_$][\w$]*' "$ALL_CODE_GLOB" 'e2e,triage,playwright-only,triage-page-api'
run_check P1 '#9c' 'Network-idle readiness check' '(waitForLoadState\(\s*[\x27\"]networkidle[\x27\"]|waitUntil:\s*[\x27\"]networkidle[\x27\"])' "$ALL_CODE_GLOB" 'e2e,playwright-only,executable-line'
run_check P1 '#18' 'Soft assertion dependency candidate' '^[[:space:]]*[A-Za-z_$][A-Za-z0-9_$]*(?:[[:space:]]*\.[[:space:]]*expect)?[[:space:]]*\.[[:space:]]*soft[[:space:]]*\(' "$ALL_CODE_GLOB" 'triage,playwright-only,soft-expect'
# #3b matches every uncaught:exception handler OPENING (single- or multi-line body): the
# old `.*false` suffix only caught the one-line `() => false` form and missed 51 multi-line
# `(err, runnable) => { return false; }` blanket suppressors in one OSS Cypress suite.
# Blanket-vs-scoped is Phase 2's documented call (handler containing expect() is exempt).
run_check P0 '#3b' 'Cypress uncaught exception suppression (Phase 2 confirms blanket vs scoped)' '(cy|Cypress)\.on\(' "$ALL_CODE_GLOB" triage
run_check P1 '#19' 'Module-level mutable state in test code' '^(?:export\s+)?let\s+' "$ALL_CODE_GLOB" 'e2e,initialized-module-state'

validate_candidate_manifest

# Out-of-scope report: one explicit line so Phase-0 skips are never a silent truncation.
scope_skipped=$(wc -l < "$SCOPE_STATE_DIR/out" | tr -d ' ')
printf '\nScope filter: %s out-of-scope file(s) skipped (pattern hits in files without Playwright/Cypress markers).\n' "$scope_skipped"
rm -rf "$SCOPE_STATE_DIR"

allocate_temp _suppressed_p0_unique
sort -u "$SUPPRESSED_P0_CANDIDATES_FILE" > "$_suppressed_p0_unique"
suppressed_p0_count=$(wc -l < "$_suppressed_p0_unique" | tr -d ' ')
if [[ "$suppressed_p0_count" -gt 0 ]]; then
  total_hits=$((total_hits + suppressed_p0_count))
  llm_triage_hits=$((llm_triage_hits + suppressed_p0_count))
  p0_candidate_hits=$((p0_candidate_hits + suppressed_p0_count))
  _suppressed_p0_ids=$(cut -f1 "$_suppressed_p0_unique" | sort -u | tr '\n' ' ')
  hit_pattern_ids="$hit_pattern_ids $_suppressed_p0_ids"
  printf '\n[P0?][JUSTIFIED-REVIEW] Suppressed P0 candidates require external verification (%s candidate%s)\n' \
    "$suppressed_p0_count" \
    "$([[ "$suppressed_p0_count" == "1" ]] && printf '' || printf 's')"
  awk -F '\t' '{ print "  " $1 " " $2 }' "$_suppressed_p0_unique"
fi
rm -f "$_suppressed_p0_unique"

suppressed_count=$(sort -u "$SUPPRESSED_HITS_FILE" | wc -l | tr -d ' ')
if [[ "$suppressed_count" -gt 0 ]]; then
  printf '\nSuppressed by JUSTIFIED: %s unique candidate location(s) (showing at most 20):\n' "$suppressed_count"
  sort -u "$SUPPRESSED_HITS_FILE" | head -20 | sed 's/^/  /'
fi

validate_candidate_manifest
if [[ "$TIER2_INFRA_FAILURE" -eq 1 ]]; then
  printf '\nINCOMPLETE: Tier 2 infrastructure failed (%s); Tier 3 completed, but no final Summary was emitted.\n' \
    "$TIER2_INFRA_DETAIL" >&2
  exit 2
fi
unique_mechanical_hits=$((total_hits + ${ast_total:-0}))
unique_p0_hits=$((p0_hits + ast_p0_hits))
unique_p1_hits=$((p1_hits + ast_p1_hits))
confirmed_mechanical_hits=$((unique_mechanical_hits - llm_triage_hits))
printf '\nSummary: %s total hit(s), %s P0, %s P1/P2 heuristic, %s LLM-triage, %s P0 candidate; %s AST-origin hit(s), exact cross-tier dedupe applied.\n' "$unique_mechanical_hits" "$unique_p0_hits" "$unique_p1_hits" "$llm_triage_hits" "$p0_candidate_hits" "${ast_total:-0}"

# Separate what a lint rule could enforce from what only a review can catch. Roughly half of the
# mechanical catalog IS already covered by eslint-plugin-playwright's recommended preset — saying
# so turns the report into a decision: enable the rule once for that slice, keep reviewing for the
# cross-file and intent-versus-assertion patterns no rule can reach. Claiming lint covers less
# than it does would be a credibility problem, so this map is checked against the published preset.
if [[ -n "$hit_pattern_ids" ]]; then
  _lintable="" _reviewonly=""
  for _id in $(printf '%s\n' $hit_pattern_ids | sort -u); do
    case "$_id" in
      '#7')  _lintable="$_lintable $_id(playwright/no-focused-test, mocha/no-exclusive-tests)" ;;
      '#9')  _lintable="$_lintable $_id(playwright/no-wait-for-timeout)" ;;
      '#9b') _lintable="$_lintable $_id(cypress/no-unnecessary-waiting)" ;;
      '#9c') _lintable="$_lintable $_id(playwright/no-networkidle)" ;;
      '#15') _lintable="$_lintable $_id(playwright/missing-playwright-await)" ;;
      # missing-playwright-await is scoped to matchers, expect.poll, test.step and waitFor* — it
      # does NOT see a floating locator action. Type-aware no-floating-promises is what catches #16.
      '#16') _lintable="$_lintable $_id(@typescript-eslint/no-floating-promises, type-aware)" ;;
      '#8a') _lintable="$_lintable $_id(playwright/no-unused-locators)" ;;
      '#4f') _lintable="$_lintable $_id(playwright/no-unnecessary-assertions, partial)" ;;
      '#4c'|'#4d'|'#4e'|'#4c-4e') _lintable="$_lintable $_id(playwright/prefer-web-first-assertions)" ;;
      '#17') _lintable="$_lintable $_id(playwright/prefer-locator)" ;;
      # Verified against eslint-plugin-playwright@2.11.0 flat/recommended: these are ON by
      # default (warn), not opt-in. Overstating what lint misses is worse than understating it.
      '#5a') _lintable="$_lintable $_id(playwright/no-conditional-expect, playwright/no-conditional-in-test)" ;;
      '#5b') _lintable="$_lintable $_id(playwright/no-force-option; cypress/no-force is opt-in)" ;;
      '#6')  _lintable="$_lintable $_id(playwright/no-eval, partial — misses evaluate()+querySelector)" ;;
      # Genuinely opt-in upstream: naming it is the actionable part.
      '#10a') _lintable="$_lintable $_id(playwright/no-nth-methods, opt-in)" ;;
      *) _reviewonly="$_reviewonly $_id" ;;
    esac
  done
  if [[ -n "$_lintable" ]]; then
    printf '\nEnforceable by a lint rule (fix once in your ESLint config, caught on every commit):\n %s\n' "$_lintable"
  fi
  if [[ -n "$_reviewonly" ]]; then
    printf '\nNo ESLint rule expresses these — they need this review (or a human) every time:\n %s\n' "$_reviewonly"
  fi
fi

case "$FAIL_ON" in
  none)
    exit 0
    ;;
  any)
    [[ "$confirmed_mechanical_hits" -eq 0 ]]
    ;;
  p0)
    [[ "$unique_p0_hits" -eq 0 ]]
    ;;
  p0-candidate)
    [[ "$((unique_p0_hits + p0_candidate_hits))" -eq 0 ]]
    ;;
  *)
    echo "error: E2E_SMELL_FAIL_ON must be one of: p0, p0-candidate, any, none" >&2
    exit 2
    ;;
esac
