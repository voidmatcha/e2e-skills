#!/usr/bin/env bash
# PR preflight for upstream E2E-fix PRs prepared in testbed/ clones.
#
# Runs six stages against the uncommitted working-tree edits of a testbed repo:
#   1. smell delta    — scan.sh baseline (HEAD) vs working tree; counts must drop
#   2. ast-artifacts  — verify-fixes.sh postfix rules on changed files only
#   3. tsc            — nearest-tsconfig targeted typecheck (errors in changed files only)
#   4. lint           — the repo's OWN eslint/biome config on changed files
#   5. spec run       — headless run of the changed specs (env failures = SKIP, not FAIL)
#   6. diff hygiene   — only intended files touched, no whitespace-only churn
#
# Every stage emits PASS / FAIL / SKIP <reason>. SKIP never fails the run but is
# listed in the final report so the PR body can disclose what was NOT verified
# locally (lesson from n8n#27035: an unverifiable spec run was quoted back as the
# close reason 68 days later — disclose it, or solve it, never hide it).
#
# Usage: bash scripts/pr-preflight.sh <testbed-repo-path> <changed-spec-file>...
#   changed files are paths relative to the testbed repo root
# Env:
#   PREFLIGHT_RUN_SPECS=0       disable stage 5 (default: attempt with SKIP detection)
#   PREFLIGHT_ALLOW_INSTALL=1   allow dependency install for stage 3/5 (default: off -> SKIP)
#   PREFLIGHT_SPEC_TIMEOUT=600  stage-5 watchdog seconds
#   PREFLIGHT_ALLOW_SLOP=1      allow stage-7 punctuation hits inside intended string literals (default: off -> FAIL)
# Exit codes: 0 = all PASS/SKIP, 1 = >=1 FAIL, 2 = usage error.
#
# bash 3.2 compatible; macOS BSD userland (no timeout(1), no associative arrays).

set -uo pipefail

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
REPO="$(cd "$REPO" && pwd)"  # absolute — stages 3/4 invoke repo-local bins by path

for f in "${FILES[@]}"; do
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

REPORT=()
fails=0
verdict() { # stage, PASS|FAIL|SKIP, message
  REPORT+=("$1|$2|$3")
  [[ "$2" == "FAIL" ]] && fails=$((fails + 1))
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

# parse scan.sh output: "Summary: N total hit(s), N P0," (Tier 3) + "ast-grep total: N hit(s)" (Tier 2)
scan_counts() { # $1 = path (file ok — scan.sh accepts non-dirs); echoes "total p0 ast"
  local out t p a
  out=$(E2E_SMELL_FAIL_ON=none E2E_SMELL_NO_ESLINT_DOWNLOAD=1 bash "$SCAN" "$1" 2>/dev/null)
  t=$(printf '%s\n' "$out" | sed -n 's/^Summary: \([0-9]*\) total.*/\1/p' | head -1); t=${t:-0}
  p=$(printf '%s\n' "$out" | sed -n 's/^Summary: [0-9]* total hit(s), \([0-9]*\) P0.*/\1/p' | head -1); p=${p:-0}
  a=$(printf '%s\n' "$out" | sed -n 's/^[[:space:]]*ast-grep total: \([0-9]*\) hit.*/\1/p' | head -1); a=${a:-0}
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
read -r bt bp ba <<< "$(scan_counts "$TMP/baseline")"
read -r at ap aa <<< "$(scan_counts "$TMP/after")"
# The fix may surface in Tier 3 (total/p0) or Tier 2 (ast) — judge the combined
# delta, but any individual increase is a regression regardless of the others.
if   [[ $at -gt $bt || $ap -gt $bp || $aa -gt $ba ]]; then
  verdict smell-delta FAIL "smell count increased (total $bt->$at p0 $bp->$ap ast $ba->$aa)"
elif [[ $((at + aa)) -lt $((bt + ba)) ]]; then
  verdict smell-delta PASS "total $bt->$at, p0 $bp->$ap, ast $ba->$aa"
else
  verdict smell-delta FAIL "no measurable drop (total $bt->$at p0 $bp->$ap ast $ba->$aa) — fix not scanner-visible (fix the right line, or // JUSTIFIED: a legitimate keep)"
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
elif [[ ! -d "$REPO/node_modules" && "${PREFLIGHT_ALLOW_INSTALL:-0}" != "1" ]]; then
  verdict tsc SKIP "node_modules absent (set PREFLIGHT_ALLOW_INSTALL=1 to install from lockfile)"
else
  if [[ ! -d "$REPO/node_modules" && "${PREFLIGHT_ALLOW_INSTALL:-0}" == "1" ]]; then
    if   [[ -f "$REPO/pnpm-lock.yaml" ]];      then (cd "$REPO" && pnpm install --frozen-lockfile) >/dev/null 2>&1
    elif [[ -f "$REPO/yarn.lock" ]];           then (cd "$REPO" && yarn install --frozen-lockfile) >/dev/null 2>&1
    elif [[ -f "$REPO/package-lock.json" ]];   then (cd "$REPO" && npm ci) >/dev/null 2>&1
    fi
  fi
  tsc_fail=""; tsc_skip=""
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
    tsc_out=$(cd "$REPO/$d" && "$tsc_bin" --noEmit -p . 2>&1)
    tsc_exit=$?
    if [[ $tsc_exit -ne 0 ]]; then
      if printf '%s\n' "$tsc_out" | grep -qE 'TS6059|TS5074'; then
        tsc_skip="composite tsconfig in $d — run the repo's own typecheck script"
        continue
      fi
      for f in "${FILES[@]}"; do
        base="$(basename "$f")"
        if printf '%s\n' "$tsc_out" | grep -F "$base" | grep -qE '\): error TS'; then
          tsc_fail="error in changed file $f (project $d)"
          printf '%s\n' "$tsc_out" | grep -F "$base" | head -5 | sed 's/^/    /'
        fi
      done
    fi
  done <<< "$TSC_DIRS"
  if   [[ -n "$tsc_fail" ]]; then verdict tsc FAIL "$tsc_fail"
  elif [[ -n "$tsc_skip" ]]; then verdict tsc SKIP "$tsc_skip"
  else                            verdict tsc PASS "no errors in changed files"
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
      (cd "$REPO" && node_modules/.bin/eslint --no-error-on-unmatched-pattern "${FILES[@]}") > "$TMP/lint.out" 2>&1
      lint_exit=$?
    else
      verdict lint SKIP "eslint not installed in the repo (node_modules/.bin/eslint absent)"; lint_exit=-1
    fi
  else
    if [[ -x "$REPO/node_modules/.bin/biome" ]]; then
      (cd "$REPO" && node_modules/.bin/biome check "${FILES[@]}") > "$TMP/lint.out" 2>&1
      lint_exit=$?
    else
      verdict lint SKIP "biome not installed in the repo (node_modules/.bin/biome absent)"; lint_exit=-1
    fi
  fi
  if [[ $lint_exit -eq 0 ]]; then
    verdict lint PASS "$lint_config clean on changed files"
  elif [[ $lint_exit -eq 1 ]]; then
    verdict lint FAIL "$lint_config findings on changed files:"
    tail -15 "$TMP/lint.out" | sed 's/^/    /'
  elif [[ $lint_exit -gt 1 ]]; then
    verdict lint SKIP "$lint_config config unusable locally (exit $lint_exit — upstream's plugin set not resolvable)"
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

if [[ "${PREFLIGHT_RUN_SPECS:-1}" == "0" ]]; then
  verdict spec-run SKIP "disabled via PREFLIGHT_RUN_SPECS=0"
else
  first="${FILES[0]}"
  runner=""; cfg_dir=""; cfg_flag=""
  case "$first" in
    *.cy.ts|*.cy.js|*.cy.tsx|*.cy.jsx) runner_kind="cypress";;
    *)                                 runner_kind="playwright";;
  esac
  if cfg_dir=$(find_config_above "$first" "$runner_kind".config.ts "$runner_kind".config.js "$runner_kind".config.mjs); then
    runner="$runner_kind"
  else
    # Fallback: config in a non-ancestor dir (e.g. uptime-kuma's config/playwright.config.js)
    # -> run from repo root with an explicit --config flag.
    found_cfg=$(find "$REPO" -maxdepth 4 \( -name node_modules -o -name dist -o -name build \) -prune -o \
      -type f \( -name "$runner_kind.config.ts" -o -name "$runner_kind.config.js" -o -name "$runner_kind.config.mjs" \) -print 2>/dev/null | head -1)
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
  else
    rel_specs=()
    for f in "${FILES[@]}"; do
      case "$f" in
        "$cfg_dir"/*) rel_specs+=("${f#"$cfg_dir"/}") ;;
        *)            rel_specs+=("$f") ;;
      esac
    done
    if [[ "$runner" == "playwright" ]]; then
      pw_cfg=""
      [[ -n "$cfg_flag" ]] && pw_cfg="--config '$cfg_flag'"
      run_with_timeout "${PREFLIGHT_SPEC_TIMEOUT:-600}" \
        sh -c "cd '$REPO/$cfg_dir' && npx --no-install playwright test $pw_cfg $(printf "'%s' " "${rel_specs[@]}") --reporter=line --workers=1"
      run_exit=$?
    else
      cy_cfg=""
      [[ -n "$cfg_flag" ]] && cy_cfg="--config-file '$cfg_flag'"
      spec_list=$(printf '%s,' "${rel_specs[@]}"); spec_list="${spec_list%,}"
      run_with_timeout "${PREFLIGHT_SPEC_TIMEOUT:-600}" \
        sh -c "cd '$REPO/$cfg_dir' && npx --no-install cypress run $cy_cfg --spec '$spec_list'"
      run_exit=$?
    fi
    if [[ $run_exit -eq 124 ]]; then
      verdict spec-run SKIP "watchdog timeout after ${PREFLIGHT_SPEC_TIMEOUT:-600}s (likely hung webServer) — disclose as not-verified-locally"
    elif [[ $run_exit -eq 0 ]]; then
      verdict spec-run PASS "changed spec(s) green locally"
    elif grep -qE "Executable doesn't exist|browserType\.launch|Process from config\.webServer|webServer.*(timed out|exited)|ECONNREFUSED|Cannot find module|MODULE_NOT_FOUND" "$TMP/run.out"; then
      verdict spec-run SKIP "environment cannot run the app/browser locally ($(grep -oEm1 "Executable doesn't exist|browserType\.launch|Process from config\.webServer|ECONNREFUSED|Cannot find module|MODULE_NOT_FOUND" "$TMP/run.out")) — disclose as not-verified-locally"
    else
      verdict spec-run FAIL "spec(s) failed after the fix (exit $run_exit) — the fix may have broken a load-bearing band-aid"
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
echo "PREFLIGHT ${fails} fail(s)"
[[ $fails -eq 0 ]]
