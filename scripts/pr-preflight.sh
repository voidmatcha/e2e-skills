#!/usr/bin/env bash
# PR preflight for upstream E2E-fix PRs prepared in testbed/ clones.
#
# Runs seven stages against the uncommitted working-tree edits of a testbed repo:
#   1. smell delta    — scan.sh baseline (HEAD) vs working tree; counts must drop
#   2. ast-artifacts  — verify-fixes.sh postfix rules on changed files only
#   3. tsc            — nearest-tsconfig typecheck (every nonzero exit is FAIL)
#   4. lint           — the repo's OWN eslint/biome config on changed files
#   5. spec run       — approved headless run; any started nonzero/timeout is FAIL
#   6. diff hygiene   — only intended files touched, no whitespace-only churn
#   7. authoring       — added-line punctuation/comment/title hygiene
#
# Every stage emits PASS / FAIL / SKIP <reason>. A required spec-run SKIP makes
# the result incomplete and nonzero. Other SKIPs remain disclosure-only.
#
# Usage: bash scripts/pr-preflight.sh <testbed-repo-path> <changed-spec-file>...
#   changed files are paths relative to the testbed repo root
# Env:
#   PREFLIGHT_RUN_SPECS=0       disable stage 5; incomplete unless the task is
#                               explicitly declared semantic-only
#   PREFLIGHT_SEMANTIC_ONLY=1   accept PREFLIGHT_RUN_SPECS=0 only for a change
#                               whose correctness cannot be exercised by a spec
#   PREFLIGHT_SPEC_TIMEOUT=600  stage-5 watchdog seconds
#   PREFLIGHT_TRUST_REPO=1      declare that project-controlled tools may run
#   PREFLIGHT_APPROVE_TSC_COMMAND=<exact command shown by a blocked run>
#   PREFLIGHT_APPROVE_LINT_COMMAND=<exact command shown by a blocked run>
#   PREFLIGHT_APPROVE_SPEC_COMMAND=<exact command shown by a blocked run>
#                               exact approval for each repository-local command;
#                               newline-separated commands are accepted for multiple
#                               tsconfig projects. Approved commands use a minimized
#                               environment and are explicitly NOT SANDBOXED.
#   PREFLIGHT_SPEC_BACKEND=local|disposable|non-production
#                               required before stage 5 can execute a spec
#   PREFLIGHT_APPROVE_NON_PRODUCTION=1
#                               additionally required for non-production backends
#   PREFLIGHT_ALLOW_SLOP=1      allow stage-7 punctuation hits inside intended string literals (default: off -> FAIL)
# Exit codes: 0 = complete with no FAIL, 1 = >=1 FAIL, 2 = usage error,
#   3 = incomplete because the required spec stage was skipped.
#
# bash 3.2 compatible; macOS BSD userland (no timeout(1), no associative arrays).

set -uo pipefail

# Resolve every pre-trust utility from fixed system package roots. The caller's
# PATH may begin inside the untrusted target repository.
TRUSTED_TOOL_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PATH="$TRUSTED_TOOL_PATH"
export PATH

REPO="${1:-}"
if [[ -z "$REPO" || ! -d "$REPO" ]]; then
  echo "usage: pr-preflight.sh <testbed-repo> <changed-spec-file>..." >&2
  exit 2
fi
shift
if [[ $# -lt 1 ]]; then
  echo "usage: pr-preflight.sh <testbed-repo> <changed-spec-file>..." >&2
  exit 2
fi
FILES=("$@")
REPO="$(cd "$REPO" && pwd -P)"  # physical absolute path — stages invoke repo-local bins by path
if [[ "${PREFLIGHT_SEMANTIC_ONLY:-0}" == "1" &&
      "${PREFLIGHT_RUN_SPECS:-1}" != "0" ]]; then
  echo "error: PREFLIGHT_SEMANTIC_ONLY=1 requires PREFLIGHT_RUN_SPECS=0" >&2
  exit 2
fi

unsafe_path_reason() { # $1 = repo-relative changed file; prints reason, rc 0 when unsafe
  local f="$1" part current parent resolved
  case "$f" in
    "") echo "empty path"; return 0 ;;
    /*) echo "absolute path"; return 0 ;;
    -*) echo "option-like leading dash"; return 0 ;;
    *:*) echo "colon"; return 0 ;;
    *$'\n'*|*$'\r'*) echo "line break"; return 0 ;;
    *\\*) echo "backslash"; return 0 ;;
    *,*|*\**|*\?*|*\[*|*\]*) echo "glob/list metacharacter"; return 0 ;;
    *"|"*) echo "report delimiter"; return 0 ;;
  esac
  if printf '%s' "$f" | LC_ALL=C grep -q '[[:cntrl:]]'; then
    echo "control character"
    return 0
  fi
  case "/$f/" in
    */../*) echo "parent traversal"; return 0 ;;
    */./*) echo "dot path component"; return 0 ;;
    *//*) echo "empty path component"; return 0 ;;
  esac

  current="$REPO"
  local old_ifs="$IFS"
  IFS='/'
  for part in $f; do
    current="$current/$part"
    if [[ -L "$current" ]]; then
      IFS="$old_ifs"
      echo "symlink component"
      return 0
    fi
  done
  IFS="$old_ifs"

  parent="$(cd "$(dirname "$REPO/$f")" 2>/dev/null && pwd -P)" || {
    echo "unresolvable parent"
    return 0
  }
  resolved="$parent/$(basename "$f")"
  case "$resolved" in
    "$REPO"/*) return 1 ;;
    *) echo "path escapes repository"; return 0 ;;
  esac
}

for f in "${FILES[@]}"; do
  if reason=$(unsafe_path_reason "$f"); then
    echo "error: unsafe changed-file path ($reason): $f" >&2
    exit 2
  fi
  if [[ ! -f "$REPO/$f" ]]; then
    echo "error: no such file in repo: $f" >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCAN="$SCRIPT_DIR/../skills/e2e-reviewer/scripts/scan.sh"
VERIFY="$SCRIPT_DIR/verify-fixes.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/execution-home"
SAFE_EXEC_PATH="$TRUSTED_TOOL_PATH"

REPORT=()
fails=0
incomplete=0
verdict() { # stage, PASS|FAIL|SKIP, message
  REPORT+=("$1|$2|$3")
  [[ "$2" == "FAIL" ]] && fails=$((fails + 1))
  if [[ "$1" == "spec-run" && "$2" == "SKIP" ]]; then
    if [[ "${PREFLIGHT_RUN_SPECS:-1}" != "0" ||
          "${PREFLIGHT_SEMANTIC_ONLY:-0}" != "1" ]]; then
      incomplete=$((incomplete + 1))
    fi
  fi
  return 0
}

kill_tree() {
  local p="$1" c
  for c in $(pgrep -P "$p" 2>/dev/null); do kill_tree "$c"; done
  kill -9 "$p" 2>/dev/null
  return 0
}

run_with_timeout() { # $1=seconds, rest=cmd...; stdout+stderr -> $TMP/run.out; 124 on timeout
  local secs="$1"; shift
  ( "$@" ) > "$TMP/run.out" 2>&1 &
  local pid=$! waited=0
  while kill -0 "$pid" 2>/dev/null; do
    if [[ $waited -ge $secs ]]; then
      kill_tree "$pid"
      wait "$pid" 2>/dev/null
      return 124
    fi
    sleep 5; waited=$((waited + 5))
  done
  wait "$pid"
}

format_command() { # $1=working directory, rest=argv; stable exact approval string
  local dir="$1" arg
  shift
  printf 'cd '
  printf '%q' "$dir"
  printf ' &&'
  for arg in "$@"; do
    printf ' '
    printf '%q' "$arg"
  done
  printf '\n'
}

command_is_approved() { # $1=env var name, $2=exact command
  local variable="$1" expected="$2" approvals line
  if [[ "${PREFLIGHT_TRUST_REPO:-0}" != "1" ]]; then
    echo "repository trust not declared (set PREFLIGHT_TRUST_REPO=1)"
    return 1
  fi
  case "$variable" in
    PREFLIGHT_APPROVE_TSC_COMMAND) approvals="${PREFLIGHT_APPROVE_TSC_COMMAND:-}" ;;
    PREFLIGHT_APPROVE_LINT_COMMAND) approvals="${PREFLIGHT_APPROVE_LINT_COMMAND:-}" ;;
    PREFLIGHT_APPROVE_SPEC_COMMAND) approvals="${PREFLIGHT_APPROVE_SPEC_COMMAND:-}" ;;
    *) echo "internal error: unsupported approval variable: $variable"; return 1 ;;
  esac
  while IFS= read -r line; do
    [[ "$line" == "$expected" ]] && return 0
  done <<< "$approvals"
  echo "exact command approval required ($variable): $expected"
  return 1
}

announce_project_execution() { # $1=stage, $2=exact command
  echo "NOTICE: $1 executes approved project-controlled code with a minimized environment; this is NOT SANDBOXED"
  echo "  approved command: $2"
}

run_sanitized() { # $1=working directory, rest=argv-safe command
  local dir="$1"
  shift
  local safe_env=(
    env -i
    "HOME=$TMP/execution-home"
    "TMPDIR=$TMP"
    "PATH=$SAFE_EXEC_PATH"
    "LANG=C"
    "LC_ALL=C"
    "CI=1"
    "NO_COLOR=1"
  )
  # Preserve only declared backend selectors; credentials and arbitrary ambient
  # variables are intentionally excluded.
  [[ -n "${BASE_URL:-}" ]] && safe_env+=("BASE_URL=$BASE_URL")
  [[ -n "${PLAYWRIGHT_BASE_URL:-}" ]] && safe_env+=("PLAYWRIGHT_BASE_URL=$PLAYWRIGHT_BASE_URL")
  [[ -n "${CYPRESS_BASE_URL:-}" ]] && safe_env+=("CYPRESS_BASE_URL=$CYPRESS_BASE_URL")
  [[ -n "${CYPRESS_baseUrl:-}" ]] && safe_env+=("CYPRESS_baseUrl=$CYPRESS_baseUrl")
  cd "$dir" && "${safe_env[@]}" "$@"
}

# parse scan.sh output: "Summary: N total hit(s), N P0," already includes
# severity-aware AST-origin hits after exact cross-tier deduplication.
scan_counts() { # $1 = path (file ok — scan.sh accepts non-dirs); echoes "total p0 ast"
  local out rc t p a
  out=$(E2E_SMELL_FAIL_ON=none E2E_SMELL_NO_ESLINT_DOWNLOAD=1 bash "$SCAN" "$1" 2>&1)
  rc=$?
  if [[ $rc -ne 0 ]]; then
    printf '%s\n' "$out" >&2
    return "$rc"
  fi
  t=$(printf '%s\n' "$out" | sed -n 's/^Summary: \([0-9]*\) total.*/\1/p' | head -1)
  p=$(printf '%s\n' "$out" | sed -n 's/^Summary: [0-9]* total hit(s), \([0-9]*\) P0.*/\1/p' | head -1)
  a=$(printf '%s\n' "$out" | sed -n 's/^[[:space:]]*ast-grep total: \([0-9]*\) hit.*/\1/p' | head -1)
  if [[ -z "$t" || -z "$p" || -z "$a" ]]; then
    echo "scanner output missing required Summary/ast-grep counts" >&2
    return 65
  fi
  echo "$t $p $a"
}

# ---- Stage 1: smell delta ---------------------------------------------------
# scan.sh's Tier-3 globs only match in directory mode, so both sides are staged
# as temp TREES with relative paths preserved (basenames like *.spec.ts must
# survive for the globs; the dir layout also keeps e2e content scoping intact).
for f in "${FILES[@]}"; do
  mkdir -p "$TMP/baseline/$(dirname "$f")" "$TMP/after/$(dirname "$f")"
  git -C "$REPO" show "HEAD:$f" > "$TMP/baseline/$f" 2>/dev/null || rm -f "$TMP/baseline/$f" # new file -> absent from baseline (intentional)
  cp "$REPO/$f" "$TMP/after/$f"
done
scan_failed=0
if scan_counts "$TMP/baseline" > "$TMP/baseline.counts" 2> "$TMP/baseline.scan.err"; then
  read -r bt bp ba < "$TMP/baseline.counts"
else
  scan_failed=1
fi
if scan_counts "$TMP/after" > "$TMP/after.counts" 2> "$TMP/after.scan.err"; then
  read -r at ap aa < "$TMP/after.counts"
else
  scan_failed=1
fi
if [[ $scan_failed -ne 0 ]]; then
  verdict smell-delta FAIL "scanner infrastructure/output failed; smell delta is not trustworthy"
  { sed 's/^/    baseline: /' "$TMP/baseline.scan.err"; sed 's/^/    after: /' "$TMP/after.scan.err"; } | tail -20
else
  # Summary total already includes deduplicated AST-origin findings. Compare
  # that unique total directly; adding ast again would double-count Tier 2.
  if   [[ $at -gt $bt || $ap -gt $bp || $aa -gt $ba ]]; then
    verdict smell-delta FAIL "smell count increased (total $bt->$at p0 $bp->$ap ast $ba->$aa)"
  elif [[ $at -lt $bt ]]; then
    verdict smell-delta PASS "total $bt->$at, p0 $bp->$ap, ast $ba->$aa"
  elif [[ $bt -eq 0 && $bp -eq 0 && $ba -eq 0 && $at -eq 0 && $ap -eq 0 && $aa -eq 0 ]]; then
    verdict smell-delta SKIP "0->0 scanner result; semantic-only fix is not mechanically verifiable by this stage"
  else
    verdict smell-delta FAIL "no measurable drop (total $bt->$at p0 $bp->$ap ast $ba->$aa) — fix not scanner-visible (fix the right line, or // JUSTIFIED: a legitimate keep)"
  fi
fi

# ---- Stage 2: sed-artifact AST check (changed files only) --------------------
if VERIFY_FIXES_SKIP_TSC=1 bash "$VERIFY" "$REPO" -- "${FILES[@]}" > "$TMP/verify.out" 2>&1; then
  verdict ast-artifacts PASS "postfix rules clean on ${#FILES[@]} file(s)"
else
  verdict ast-artifacts FAIL "double-await / empty-expect / orphan-then in changed files (rerun: bash $VERIFY $REPO -- ${FILES[*]})"
  sed 's/^/    /' "$TMP/verify.out" | tail -15
fi

# ---- Stage 3: targeted tsc ----------------------------------------------------
nearest_tsconfig_dir() { # $1 = file rel path; echoes dir rel path, rc 1 if none
  local d
  d="$(dirname "$1")"
  while :; do
    [[ -f "$REPO/$d/tsconfig.json" ]] && { echo "$d"; return 0; }
    [[ "$d" == "." ]] && break
    d="$(dirname "$d")"
  done
  return 1
}

TSC_DIRS=""
ts_files=0
for f in "${FILES[@]}"; do
  case "$f" in *.ts|*.tsx|*.mts|*.cts) ts_files=$((ts_files + 1));; *) continue;; esac
  d=$(nearest_tsconfig_dir "$f") || continue
  case "
$TSC_DIRS
" in *"
$d
"*) ;; *) TSC_DIRS="$TSC_DIRS$d
";; esac
done

if [[ $ts_files -eq 0 ]]; then
  verdict tsc SKIP "no TypeScript files among changed files"
elif [[ -z "$TSC_DIRS" ]]; then
  verdict tsc SKIP "no tsconfig.json found above changed files"
elif [[ ! -d "$REPO/node_modules" ]]; then
  verdict tsc SKIP "node_modules absent; automatic dependency installation is disabled"
else
  tsc_fail=""; tsc_skip=""; tsc_ran=0
  while IFS= read -r d; do
    [[ -z "$d" ]] && continue
    tsc_bin=""
    if   [[ -x "$REPO/$d/node_modules/.bin/tsc" ]]; then tsc_bin="$REPO/$d/node_modules/.bin/tsc"
    elif [[ -x "$REPO/node_modules/.bin/tsc" ]];    then tsc_bin="$REPO/node_modules/.bin/tsc"
    fi
    if [[ -z "$tsc_bin" ]]; then
      # explicit local-bin check — `npx --no-install` also resolves global/npx-cache copies
      tsc_skip="tsc not installed in the repo for $d (node_modules/.bin/tsc absent)"
      continue
    fi
    tsc_command=$(format_command "$REPO/$d" "$tsc_bin" --noEmit -p .)
    if ! tsc_gate_reason=$(command_is_approved PREFLIGHT_APPROVE_TSC_COMMAND "$tsc_command"); then
      tsc_skip="$tsc_gate_reason"
      continue
    fi
    announce_project_execution tsc "$tsc_command"
    tsc_ran=$((tsc_ran + 1))
    tsc_out=$(run_sanitized "$REPO/$d" "$tsc_bin" --noEmit -p . 2>&1)
    tsc_exit=$?
    if [[ $tsc_exit -ne 0 ]]; then
      tsc_fail="project $d failed (exit $tsc_exit)"
      printf '%s\n' "$tsc_out" | tail -10 | sed 's/^/    /'
    fi
  done <<< "$TSC_DIRS"
  if   [[ -n "$tsc_fail" ]]; then verdict tsc FAIL "$tsc_fail"
  elif [[ -n "$tsc_skip" ]]; then verdict tsc SKIP "$tsc_skip"
  elif [[ "$tsc_ran" -gt 0 ]]; then verdict tsc PASS "approved project typecheck completed cleanly"
  else verdict tsc SKIP "no eligible TypeScript project command"
  fi
fi

# ---- Stage 4: repo's own lint, changed files only ------------------------------
lint_config=""
for c in .eslintrc .eslintrc.js .eslintrc.cjs .eslintrc.json .eslintrc.yml .eslintrc.yaml eslint.config.js eslint.config.mjs eslint.config.ts; do
  [[ -f "$REPO/$c" ]] && { lint_config="eslint"; break; }
done
[[ -z "$lint_config" && -f "$REPO/biome.json" ]] && lint_config="biome"

if [[ -z "$lint_config" ]]; then
  verdict lint SKIP "no eslint/biome config at repo root"
else
  lint_exit=0
  # explicit local-bin checks — `npx --no-install` also resolves global/npx-cache copies
  if [[ "$lint_config" == "eslint" ]]; then
    if [[ -x "$REPO/node_modules/.bin/eslint" ]]; then
      lint_cmd=("$REPO/node_modules/.bin/eslint" --no-error-on-unmatched-pattern "${FILES[@]}")
    else
      verdict lint SKIP "eslint not installed in the repo (node_modules/.bin/eslint absent)"; lint_exit=-1
    fi
  else
    if [[ -x "$REPO/node_modules/.bin/biome" ]]; then
      lint_cmd=("$REPO/node_modules/.bin/biome" check "${FILES[@]}")
    else
      verdict lint SKIP "biome not installed in the repo (node_modules/.bin/biome absent)"; lint_exit=-1
    fi
  fi
  if [[ $lint_exit -eq 0 ]]; then
    lint_command=$(format_command "$REPO" "${lint_cmd[@]}")
    if ! lint_gate_reason=$(command_is_approved PREFLIGHT_APPROVE_LINT_COMMAND "$lint_command"); then
      verdict lint SKIP "$lint_gate_reason"
      lint_exit=-1
    else
      announce_project_execution lint "$lint_command"
      run_sanitized "$REPO" "${lint_cmd[@]}" > "$TMP/lint.out" 2>&1
      lint_exit=$?
    fi
  fi
  if [[ $lint_exit -eq 0 ]]; then
    verdict lint PASS "$lint_config clean on changed files"
  elif [[ $lint_exit -gt 1 ]]; then
    verdict lint FAIL "$lint_config exited $lint_exit after explicit approval"
    tail -15 "$TMP/lint.out" | sed 's/^/    /'
  elif [[ $lint_exit -eq 1 ]]; then
    verdict lint FAIL "$lint_config findings on changed files:"
    tail -15 "$TMP/lint.out" | sed 's/^/    /'
  fi
fi

# ---- Stage 5: headless run of changed specs (best-effort) ----------------------
find_config_above() { # $1 = file rel path, $2... = config names; echoes dir
  local f="$1"; shift
  local d n
  d="$(dirname "$f")"
  while :; do
    for n in "$@"; do
      [[ -f "$REPO/$d/$n" ]] && { echo "$d"; return 0; }
    done
    [[ "$d" == "." ]] && break
    d="$(dirname "$d")"
  done
  return 1
}

spec_backend_gate() { # prints a safe verdict reason; rc 0 only when execution is allowed
  local backend="${PREFLIGHT_SPEC_BACKEND:-}" value configured=0
  case "$backend" in
    local)
      for value in \
        "${BASE_URL:-}" \
        "${PLAYWRIGHT_BASE_URL:-}" \
        "${CYPRESS_BASE_URL:-}" \
        "${CYPRESS_baseUrl:-}"
      do
        [[ -z "$value" ]] && continue
        configured=1
        if ! python3 - "$value" <<'PY'
import sys
from urllib.parse import urlsplit

try:
    parsed = urlsplit(sys.argv[1])
    valid = (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    )
    if valid:
        parsed.port
except ValueError:
    valid = False
raise SystemExit(0 if valid else 1)
PY
        then
          echo "configured base URL is not a userinfo-free loopback URL for PREFLIGHT_SPEC_BACKEND=local"
          return 1
        fi
      done
      if [[ $configured -eq 0 ]]; then
        echo "local backend requires an actual configured base URL"
        return 1
      fi
      echo "explicit local backend declaration"
      return 0
      ;;
    disposable)
      echo "explicit disposable backend declaration"
      return 0
      ;;
    non-production)
      if [[ "${PREFLIGHT_APPROVE_NON_PRODUCTION:-0}" != "1" ]]; then
        echo "non-production backend requires PREFLIGHT_APPROVE_NON_PRODUCTION=1"
        return 1
      fi
      echo "explicitly approved non-production backend"
      return 0
      ;;
    "")
      echo "backend undeclared (set PREFLIGHT_SPEC_BACKEND=local, disposable, or approved non-production)"
      return 1
      ;;
    *)
      echo "invalid PREFLIGHT_SPEC_BACKEND=$backend"
      return 1
      ;;
  esac
}

if [[ "${PREFLIGHT_RUN_SPECS:-1}" == "0" ]]; then
  if [[ "${PREFLIGHT_SEMANTIC_ONLY:-0}" == "1" ]]; then
    verdict spec-run SKIP "explicit semantic-only opt-out via PREFLIGHT_RUN_SPECS=0 and PREFLIGHT_SEMANTIC_ONLY=1"
  else
    verdict spec-run SKIP "disabled via PREFLIGHT_RUN_SPECS=0 without the semantic-only opt-out"
  fi
else
  first="${FILES[0]}"
  runner=""; cfg_dir=""; cfg_flag=""
  case "$first" in
    *.cy.ts|*.cy.js|*.cy.tsx|*.cy.jsx) runner_kind="cypress";;
    *)                                 runner_kind="playwright";;
  esac
  config_names=()
  for config_ext in js cjs mjs jsx ts cts mts tsx; do
    config_names+=("$runner_kind.config.$config_ext")
  done
  if cfg_dir=$(find_config_above "$first" "${config_names[@]}"); then
    runner="$runner_kind"
  else
    # Fallback: config in a non-ancestor dir (e.g. uptime-kuma's config/playwright.config.js)
    # -> run from repo root with an explicit --config flag.
    found_cfg=""
    for config_ext in js cjs mjs jsx ts cts mts tsx; do
      found_cfg=$(find "$REPO" -maxdepth 4 \
        \( -name node_modules -o -name dist -o -name build \) -prune -o \
        -type f -name "$runner_kind.config.$config_ext" -print 2>/dev/null |
        head -1)
      [[ -n "$found_cfg" ]] && break
    done
    if [[ -n "$found_cfg" ]]; then
      runner="$runner_kind"; cfg_dir="."; cfg_flag="${found_cfg#"$REPO"/}"
    fi
  fi
  if [[ -z "$runner" ]]; then
    verdict spec-run SKIP "no $runner_kind config found above ${first} or in the repo (depth 4)"
  elif [[ ! -x "$REPO/node_modules/.bin/$runner" && ! -x "$REPO/$cfg_dir/node_modules/.bin/$runner" ]]; then
    # explicit local-bin check — `npx --no-install` still resolves a GLOBAL npx-cache
    # copy, which then can't load the repo's config (MODULE_NOT_FOUND on repo deps)
    verdict spec-run SKIP "$runner not installed in the repo (node_modules/.bin/$runner absent — install repo deps to enable)"
  elif ! backend_reason=$(spec_backend_gate); then
    verdict spec-run SKIP "safety gate blocked execution: $backend_reason"
  else
    runner_bin="$REPO/node_modules/.bin/$runner"
    [[ -x "$REPO/$cfg_dir/node_modules/.bin/$runner" ]] && runner_bin="$REPO/$cfg_dir/node_modules/.bin/$runner"
    rel_specs=()
    for f in "${FILES[@]}"; do
      case "$f" in
        "$cfg_dir"/*) rel_specs+=("${f#"$cfg_dir"/}") ;;
        *)            rel_specs+=("$f") ;;
      esac
    done
    if [[ "$runner" == "playwright" ]]; then
      spec_cmd=("$runner_bin" test)
      [[ -n "$cfg_flag" ]] && spec_cmd+=(--config "$cfg_flag")
      spec_cmd+=("${rel_specs[@]}" --reporter=line --workers=1)
    else
      spec_list=$(printf '%s,' "${rel_specs[@]}"); spec_list="${spec_list%,}"
      spec_cmd=("$runner_bin" run)
      [[ -n "$cfg_flag" ]] && spec_cmd+=(--config-file "$cfg_flag")
      spec_cmd+=(--spec "$spec_list")
    fi
    spec_command=$(format_command "$REPO/$cfg_dir" "${spec_cmd[@]}")
    if ! spec_gate_reason=$(command_is_approved PREFLIGHT_APPROVE_SPEC_COMMAND "$spec_command"); then
      verdict spec-run SKIP "$spec_gate_reason"
      run_exit=-1
    else
      announce_project_execution spec-run "$spec_command"
      run_with_timeout "${PREFLIGHT_SPEC_TIMEOUT:-600}" \
        run_sanitized "$REPO/$cfg_dir" "${spec_cmd[@]}"
      run_exit=$?
    fi
    if [[ $run_exit -eq -1 ]]; then
      :
    elif [[ $run_exit -eq 124 ]]; then
      verdict spec-run FAIL "approved spec command watchdog timeout after ${PREFLIGHT_SPEC_TIMEOUT:-600}s"
    elif [[ $run_exit -eq 0 ]]; then
      verdict spec-run PASS "changed spec(s) green locally"
    else
      verdict spec-run FAIL "approved spec command failed (exit $run_exit)"
      tail -20 "$TMP/run.out" | sed 's/^/    /'
    fi
  fi
fi

# ---- Stage 6: diff hygiene (runs LAST, after stage-5 side effects) -------------
hygiene_fail=0
stray=$(git -C "$REPO" diff --name-only HEAD | grep -vxF -f <(printf '%s\n' "${FILES[@]}") || true)
if [[ -n "$stray" ]]; then
  verdict diff-hygiene FAIL "unintended tracked files modified: $(echo "$stray" | tr '\n' ' ')"
  hygiene_fail=1
fi
if ! git -C "$REPO" diff --check HEAD -- "${FILES[@]}" >/dev/null 2>&1; then
  verdict diff-hygiene FAIL "trailing whitespace or conflict markers in changed files"
  hygiene_fail=1
fi
for f in "${FILES[@]}"; do
  if [[ -z "$(git -C "$REPO" diff -w HEAD -- "$f")" && -n "$(git -C "$REPO" diff HEAD -- "$f")" ]]; then
    verdict diff-hygiene FAIL "$f is a whitespace-only change — drop it; upstream reviewers reject formatting noise"
    hygiene_fail=1
  fi
done
[[ $hygiene_fail -eq 0 ]] && verdict diff-hygiene PASS "only intended files, no formatting churn"

# ---- Stage 7: authoring hygiene (added lines must not read as generated) --------
added=$(git -C "$REPO" diff HEAD -- "${FILES[@]}" | grep '^+' | grep -v '^+++' || true)
style_fail=0
slop=$(printf '%s\n' "$added" | LC_ALL=C grep -nE $'\xe2\x80\x94|\xe2\x80\x93|\xe2\x86\x92|\xe2\x80\xa6' || true)
if [[ -n "$slop" && "${PREFLIGHT_ALLOW_SLOP:-0}" != "1" ]]; then
  verdict authoring FAIL "AI-tell punctuation (em/en dash, arrow, ellipsis) in added lines (PREFLIGHT_ALLOW_SLOP=1 to override for intentional string-literal content): $(printf '%s\n' "$slop" | head -3 | tr '\n' ' ')"
  style_fail=1
fi
added_comments=$(printf '%s\n' "$added" | grep -cE '^\+[[:space:]]*//' || true)
if [[ "${added_comments:-0}" -gt "${PREFLIGHT_MAX_COMMENTS:-3}" ]]; then
  verdict authoring FAIL "$added_comments comment lines added (max ${PREFLIGHT_MAX_COMMENTS:-3}) - only non-obvious WHY comments belong in an upstream fix"
  style_fail=1
fi
# BSD sed BRE has no alternation - filter with grep -E, then extract the quoted title
removed_titles=$(git -C "$REPO" diff HEAD -- "${FILES[@]}" | grep -E '^-[[:space:]]*(test|it|describe)(\.only)?\("' | sed 's/^[^"]*\("[^"]*"\).*/\1/' || true)
if [[ -n "$removed_titles" && "${PREFLIGHT_ALLOW_RENAME:-0}" != "1" ]]; then
  rename_hit=""
  while IFS= read -r rt; do
    [[ -z "$rt" ]] && continue
    printf '%s\n' "$added" | grep -qF "$rt" || rename_hit="$rt"
  done <<< "$removed_titles"
  if [[ -n "$rename_hit" ]]; then
    verdict authoring FAIL "test title changed ($rename_hit) - keep original names unless factually wrong (PREFLIGHT_ALLOW_RENAME=1 to override)"
    style_fail=1
  fi
fi
[[ $style_fail -eq 0 ]] && verdict authoring PASS "no slop punctuation, ${added_comments:-0} comment line(s), no test renames"

# ---- Report ---------------------------------------------------------------------
echo
echo "== pr-preflight: $REPO =="
for r in "${REPORT[@]}"; do
  IFS='|' read -r s v m <<< "$r"
  printf '  %-14s %-5s %s\n' "$s" "$v" "$m"
done
echo "PREFLIGHT ${fails} fail(s), ${incomplete} incomplete required stage(s)"
if [[ $fails -gt 0 ]]; then
  exit 1
fi
if [[ $incomplete -gt 0 ]]; then
  echo "PREFLIGHT INCOMPLETE: $incomplete required stage(s) skipped"
  exit 3
fi
exit 0
