#!/usr/bin/env bash
# Scanner portability notes for contributors:
# - BSD sed (macOS default) silently fails on `\b` word boundaries — pattern `\bit\.only\(`
#   matches the literal substring `bit.only(` and returns zero hits while reporting success.
#   Avoid `\b` in any sed used by/around this scanner. Use `[^a-zA-Z_]` anchors instead.
# - In-place edit flag differs: BSD sed needs `sed -i ''`, GNU sed needs `sed -i`. The
#   most-portable form for repo-wide bulk fixes is `perl -i -0pe '...'` (handles multi-line too).
# - This scanner itself uses `rg` (PCRE2) — verify with `rg --version | grep pcre2`.
set -uo pipefail

ROOT="${1:-.}"
FAIL_ON="${E2E_SMELL_FAIL_ON:-p0}"

# Eval fixtures contain intentional anti-patterns and are excluded from normal scans,
# EXCEPT when the scan root itself is inside an evals/files tree (self-testing the fixtures).
# bash 3.2 + set -u: expand with ${arr[@]+...} guard — empty-array expansion errors otherwise.
EVAL_FIXTURE_EXCLUDES=(--glob '!**/evals/files/**')
case "$(cd "$ROOT" 2>/dev/null && pwd || true)" in
  *"/evals/files"*) EVAL_FIXTURE_EXCLUDES=() ;;
esac

# Shared `// JUSTIFIED:` suppression check, honored by ALL THREE tiers so the documented
# convention is consistent (previously only the Tier-3 regex net applied it; Tier-1 eslint
# and Tier-2 ast-grep flagged JUSTIFIED lines regardless). Returns 0 when the hit at
# <file>:<line> is covered by a JUSTIFIED marker on the line itself or the contiguous
# //-comment block immediately above it (max 5 lines). The #7 no-exemption contract is the
# caller's responsibility — callers must NOT consult this for focused-test rules.
_line_is_justified() {
  local _hf="$1" _hl="$2" _linetext _just
  [[ -f "$_hf" && "$_hl" =~ ^[0-9]+$ ]] || return 1
  _linetext=$(sed -n "${_hl}p" "$_hf" 2>/dev/null)
  case "$_linetext" in (*"JUSTIFIED:"*) return 0 ;; esac
  if [[ "$_hl" -gt 1 ]]; then
    _just=$(sed -n "$((_hl > 5 ? _hl - 5 : 1)),$((_hl - 1))p" "$_hf" 2>/dev/null | awk '
      { lines[NR] = $0 }
      END {
        for (i = NR; i >= 1; i--) {
          t = lines[i]; sub(/^[[:space:]]+/, "", t)
          if (t ~ /^\/\//) { if (t ~ /JUSTIFIED:/) { print "Y"; exit } } else exit
        }
      }')
    [[ "$_just" == "Y" ]] && return 0
  fi
  return 1
}

if [[ ! -e "$ROOT" ]]; then
  echo "error: path does not exist: $ROOT" >&2
  exit 2
fi

if ! command -v rg >/dev/null 2>&1; then
  echo "error: rg is required (https://github.com/BurntSushi/ripgrep)" >&2
  exit 2
fi

total_hits=0
p0_hits=0
p1_hits=0
llm_triage_hits=0
eslint_ran=0
playwright_lint_done=0
cypress_lint_done=0

# Coverage map — patterns the eslint plugin's `recommended` config catches reliably.
# When the plugin runs successfully, Tier 2 (ast-grep) and Tier 3 (regex) skip the LINT_COVERS patterns to avoid duplicate reports.
# Patterns OUTSIDE those lists (e.g. #4c-4e, #4f) are intentionally reported by every tier that matches; Tier-1 findings for the covered rules are mapped onto the same total/p0/p1 counters as Tier 3 (see the rule map in try_eslint) so skipping Tier 2/3 can never zero the exit gate. ast_total stays a separate count, but FAIL_ON=any gates on it too.
# The ast-grep rules are language:TypeScript (.ts/.mts/.cts) by design; .js/.jsx/.tsx coverage is delegated to the always-on Tier-3 regex net.
# Conservative: only includes patterns where the eslint rule covers the same surface as our regex
# (binary patterns or full overlap). Partial-overlap patterns like #4 sub-variants stay in Tier 3 as safety net.
PLAYWRIGHT_LINT_COVERS='#7 #9 #15 #16'   # no-focused-test, no-wait-for-timeout, missing-playwright-await (covers expect+action)
CYPRESS_LINT_COVERS='#7 #9b'             # mocha/no-exclusive-tests (it.only), cypress/no-unnecessary-waiting

# AST-grep rule → our pattern ID (bash 3.2 compatible — no associative arrays)
get_pattern_for_ast_rule() {
  case "$1" in
    sg-15-missing-await-playwright-expect) echo '#15' ;;
    sg-4ce-count|sg-4ce-state-bool|sg-4ce-text) echo '#4c-4e' ;;
    sg-4f-locator-as-truthy) echo '#4f' ;;
  esac
}

# Returns 0 (skip) if the pattern is covered by an eslint plugin that ran successfully.
should_skip_pattern() {
  local id="$1"
  if [[ "$playwright_lint_done" == 1 && " $PLAYWRIGHT_LINT_COVERS " == *" $id "* ]]; then return 0; fi
  if [[ "$cypress_lint_done" == 1 && " $CYPRESS_LINT_COVERS " == *" $id "* ]]; then return 0; fi
  return 1
}

# Try the framework's official ESLint plugin (better than our regex for mechanical patterns).
# Prefers locally installed; falls back to `npx --yes` auto-download when missing (mirrors ast-grep tier).
# Skip entirely if no Playwright/Cypress import exists in $ROOT or npx isn't on PATH.
# Uses a generated FLAT config file (eslint.config.mjs): ESLint v9+ removed --no-eslintrc/--ext and
# inline-JSON -c. ESLINT_USE_FLAT_CONFIG=true opts v8.21+ local installs into the same path; anything
# older fails with rc>=2 and we fall through WITHOUT claiming coverage (see exit-code gate below).
try_eslint() {
  local plugin="$1"; local label="$2"
  command -v npx >/dev/null 2>&1 || return 1

  local plugin_path="$ROOT/node_modules/eslint-plugin-$plugin"
  local mode
  local -a npx_args
  if [[ -d "$plugin_path" ]]; then
    mode="locally installed"
    npx_args=(--no-install eslint)
  elif [[ "${E2E_SMELL_NO_ESLINT_DOWNLOAD:-}" == "1" ]]; then
    printf '\n[ESLint] %s — eslint-plugin-%s not installed and E2E_SMELL_NO_ESLINT_DOWNLOAD=1 — skipping\n' "$label" "$plugin"
    return 1
  else
    mode="auto-downloaded via npx (set E2E_SMELL_NO_ESLINT_DOWNLOAD=1 to skip)"
    # `typescript` MUST be a direct -p dep. It is only a PEER dep of @typescript-eslint/parser,
    # and npx (re)materializes its shared cache env using the npmrc of the cwd it runs from:
    # `cd "$ROOT"` into a repo whose .npmrc sets `legacy-peer-deps=true` (xyflow, many monorepos)
    # installs the env WITHOUT peer deps, so the parser dies with "Cannot find module 'typescript'"
    # (eslint rc=2) and Tier 1 silently never fires — for that repo AND for every later scan that
    # reuses the poisoned cache env. A direct dep is installed under every peer-deps policy.
    npx_args=(--yes -p 'eslint@^9' -p "eslint-plugin-$plugin" -p '@typescript-eslint/parser' -p 'typescript@^5' -p "eslint-plugin-$plugin-silent-pass")
    if [[ "$plugin" == "cypress" ]]; then
      npx_args+=(-p eslint-plugin-mocha)
    fi
    npx_args+=(eslint)
  fi

  # Generate the flat config. ESLint v9 loads eslint.config.mjs via ESM import whose module
  # resolution is anchored at the CONFIG FILE's directory — a /tmp config cannot see the
  # npx-cache-installed plugins by bare name. Resolve their ABSOLUTE entry paths inside the
  # same npx environment (CJS require.resolve honors npx's NODE_PATH) and embed those.
  local _paths _plugin_abs _parser_abs _mocha_abs=""
  local _cfgd
  _cfgd=$(mktemp -d)
  # npm >=9 npx exposes packages only via PATH (no NODE_PATH); derive the npx env's
  # node_modules root from PATH[0] and resolve with explicit paths. Falls back to
  # <cwd>/node_modules for the locally-installed mode.
  cat > "$_cfgd/resolve.cjs" <<'EOFRES'
const cands = [
  process.env.PATH.split(':')[0].replace(/\/\.bin$/, ''),
  process.cwd() + '/node_modules',
];
const r = (n) => {
  for (const c of cands) { try { return require.resolve(n, { paths: [c] }); } catch (e) {} }
  throw new Error('unresolvable: ' + n);
};
console.log(JSON.stringify(process.argv.slice(2).map(r)));
EOFRES
  local -a _want=("eslint-plugin-$plugin" "@typescript-eslint/parser")
  [[ "$plugin" == "cypress" ]] && _want+=("eslint-plugin-mocha")
  local -a _resolve_args
  if [[ "$mode" == "locally installed" ]]; then
    _resolve_args=(--no-install node)
  else
    _resolve_args=("${npx_args[@]:0:${#npx_args[@]}-1}" node)   # same -p set, run node instead of eslint
  fi
  _paths=$( (cd "$ROOT" && npx "${_resolve_args[@]}" "$_cfgd/resolve.cjs" "${_want[@]}") 2>/dev/null | tail -1 )
  if [[ -z "$_paths" || "$_paths" != "["* ]]; then
    printf '\n[ESLint] %s — could not resolve eslint-plugin-%s (or @typescript-eslint/parser) — skipping Tier 1; Tier 2/3 cover\n' "$label" "$plugin"
    rm -rf "$_cfgd"
    return 1
  fi
  _plugin_abs=$(printf '%s' "$_paths" | sed 's/^\["//; s/",".*$//; s/"\]$//')
  _parser_abs=$(printf '%s' "$_paths" | awk -F'","' '{print $2}' | sed 's/"\]$//')
  if [[ "$plugin" == "cypress" ]]; then
    _mocha_abs=$(printf '%s' "$_paths" | awk -F'","' '{print $3}' | sed 's/"\]$//')
  fi

  # Companion silent-pass plugin (dogfood the #4f always-pass rule). Best-effort:
  # resolved separately so a missing/offline package NEVER breaks Tier 1 — the
  # official plugin still runs, and Tier 2/3 still cover #4f.
  # NOTE: #4f was upstreamed to eslint-plugin-playwright as `no-unnecessary-assertions`
  # (mskelton/eslint-plugin-playwright#470, merged). Once released and in its recommended
  # config, the Playwright `flat/recommended` spread below covers #4f natively and this
  # companion dogfood becomes redundant for Playwright (Cypress silent-pass still applies).
  # Not hardcoding the rule name here — an unreleased rule id would error "rule not found".
  local _sp_abs="" _sp_paths _sp_imp="" _sp_plg="" _sp_rul=""
  _sp_paths=$( (cd "$ROOT" && npx "${_resolve_args[@]}" "$_cfgd/resolve.cjs" "eslint-plugin-$plugin-silent-pass") 2>/dev/null | tail -1 )
  if [[ "$_sp_paths" == "["* ]]; then
    _sp_abs=$(printf '%s' "$_sp_paths" | sed 's/^\["//; s/"\]$//')
    _sp_imp="import spp from '$_sp_abs';"
    _sp_plg=", '$plugin-silent-pass': spp"
    _sp_rul=", '$plugin-silent-pass/no-silent-pass': 'error'"
  fi

  # Conditional evals/files ignore mirrors Tier 3's EVAL_FIXTURE_EXCLUDES.
  local _cfg _evalign=""
  _cfg="$_cfgd/eslint.config.mjs"
  # bash 3.2 + set -u treats an empty array as unset; ${arr[*]+x} is the safe presence test.
  if [[ -n "${EVAL_FIXTURE_EXCLUDES[*]+x}" ]]; then _evalign="'**/evals/files/**',"; fi
  if [[ "$plugin" == "playwright" ]]; then
    cat > "$_cfg" <<EOFCFG
import playwright from '$_plugin_abs';
import tsParser from '$_parser_abs';
$_sp_imp
export default [
  { ignores: ['**/node_modules/**','**/dist/**','**/build/**','**/.next/**','**/out/**','**/coverage/**','**/public/**','**/*.min.js',$_evalign] },
  {
    files: ['**/*.ts','**/*.js','**/*.tsx','**/*.jsx'],
    plugins: { playwright$_sp_plg },
    languageOptions: { parser: tsParser, ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } },
    rules: { ...(playwright.configs['flat/recommended'] ?? playwright.configs.recommended).rules$_sp_rul },
  },
];
EOFCFG
  else
    cat > "$_cfg" <<EOFCFG
import cypress from '$_plugin_abs';
import mocha from '$_mocha_abs';
import tsParser from '$_parser_abs';
$_sp_imp
const cypressRules = (cypress.configs['flat/recommended'] ?? cypress.configs.recommended).rules;
export default [
  { ignores: ['**/node_modules/**','**/dist/**','**/build/**','**/coverage/**','**/*.min.js',$_evalign] },
  {
    files: ['**/*.ts','**/*.js','**/*.tsx','**/*.jsx'],
    plugins: { cypress, mocha$_sp_plg },
    languageOptions: { parser: tsParser, ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } },
    rules: { ...cypressRules, 'mocha/no-exclusive-tests': 'error'$_sp_rul },
  },
];
EOFCFG
  fi

  printf '\n[ESLint] %s — running eslint-plugin-%s (%s)\n' "$label" "$plugin" "$mode"
  local out
  # Watchdog: npx auto-download or eslint itself can hang on large/offline environments.
  # Run in background and kill after ESLINT_TIMEOUT_SECS (default 300) — macOS has no timeout(1).
  local _outf _pid _waited=0 _cap="${E2E_SMELL_ESLINT_TIMEOUT_SECS:-300}"
  _outf=$(mktemp)
  ( cd "$ROOT" && ESLINT_USE_FLAT_CONFIG=true npx "${npx_args[@]}" --no-error-on-unmatched-pattern \
        -c "$_cfg" . ) > "$_outf" 2>&1 &
  _pid=$!
  while kill -0 "$_pid" 2>/dev/null; do
    sleep 5; _waited=$((_waited + 5))
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
      printf '  [watchdog] eslint exceeded %ss — killed; Tier 2/3 still cover these patterns\n' "$_cap"
      rm -f "$_outf"; rm -rf "$_cfgd"
      return 1
    fi
  done
  wait "$_pid" 2>/dev/null
  local _rc=$?
  out=$(cat "$_outf"); rm -f "$_outf"; rm -rf "$_cfgd"

  # EXIT-CODE GATE (the silent-always-pass bug class this skill exists to catch):
  # eslint exits 0 = clean, 1 = findings; anything else (2 = config/usage error, 127 = not
  # found, npx/network crash...) means Tier 1 did NOT cover the patterns — never claim it did,
  # or Tier 2/3 would silently skip #7/#9/#15/#16 (#7/#9b for Cypress).
  if [[ "$_rc" -ge 2 ]]; then
    printf '  [ESLint] crashed or unusable (exit %s) — Tier 2/3 keep covering these patterns\n' "$_rc"
    printf '%s\n' "$out" | head -5 | sed 's/^/    /'
    return 1
  fi
  if [[ "$_rc" -eq 1 ]] || printf '%s' "$out" | grep -qE '(error|warning)'; then
    printf '%s\n' "$out" | sed 's/^/  /' | head -100
  else
    printf '  no findings\n'
  fi
  # Tier-1 findings must reach the exit gate: Tier 2/3 skip the LINT_COVERS patterns when
  # Tier 1 ran, so without these counters a repo whose only P0 is `test.only` exits 0 under
  # FAIL_ON=p0 whenever Tier 1 runs. Map the covered eslint rule IDs onto the same counters
  # Tier 3 uses (parsed from the full "$out", not the head-truncated display):
  #   P0: no-focused-test (#7), missing-playwright-await (#15/#16),
  #       mocha no-exclusive-tests (#7 Cypress), no-silent-pass (#4f companion plugin)
  #   P1: no-wait-for-timeout (#9), no-unnecessary-waiting (#9b)
  # Count Tier-1 P0/P1 hits, honoring `// JUSTIFIED:` (parity with Tier 2/3). Walk the eslint
  # stylish output tracking the current file header; #7 rules (no-focused-test / mocha
  # no-exclusive-tests) are NEVER exempt, per the no-JUSTIFIED-for-#7 contract.
  local _t1_p0=0 _t1_p1=0 _curf="" _eln _elno _efp _etrim
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
            _efp="$_curf"; [[ -f "$_efp" ]] || _efp="$ROOT/$_curf"
            case "$_etrim" in
              */no-focused-test|*/no-exclusive-tests)
                _t1_p0=$((_t1_p0 + 1)) ;;                            # #7 — never JUSTIFIED-exempt
              */no-silent-pass|*/missing-playwright-await)
                _line_is_justified "$_efp" "$_elno" || _t1_p0=$((_t1_p0 + 1)) ;;
              */no-wait-for-timeout|*/no-unnecessary-waiting)
                _line_is_justified "$_efp" "$_elno" || _t1_p1=$((_t1_p1 + 1)) ;;
            esac ;;
        esac ;;
    esac
  done <<< "$out"
  if [[ "$_t1_p0" -gt 0 ]]; then p0_hits=$((p0_hits + _t1_p0)); total_hits=$((total_hits + _t1_p0)); fi
  if [[ "$_t1_p1" -gt 0 ]]; then p1_hits=$((p1_hits + _t1_p1)); total_hits=$((total_hits + _t1_p1)); fi
  eslint_ran=1
  [[ "$plugin" == "playwright" ]] && playwright_lint_done=1
  [[ "$plugin" == "cypress" ]] && cypress_lint_done=1
}

# If the project already has its own eslint config, warn that our scanner uses
# `recommended` (not the user's custom rules) — they may want to opt out and rely
# on their own pipeline instead.
if [[ -f "$ROOT/.eslintrc" || -f "$ROOT/.eslintrc.json" || -f "$ROOT/.eslintrc.js" || -f "$ROOT/.eslintrc.cjs" || -f "$ROOT/.eslintrc.yml" || -f "$ROOT/.eslintrc.yaml" || -f "$ROOT/eslint.config.js" || -f "$ROOT/eslint.config.mjs" || -f "$ROOT/eslint.config.ts" ]]; then
  printf '\n[note] Project has its own ESLint config — our Tier 1 uses `recommended` preset (not your config) for predictable output. If you already lint with eslint-plugin-{playwright,cypress} in CI/IDE, set E2E_SMELL_NO_ESLINT_DOWNLOAD=1 to skip Tier 1 here and let your pipeline own it (Tier 2 ast-grep + Tier 3 regex still run for the gaps your lint may not cover).\n'
fi

# Detect each framework via actual imports, then opt into eslint-plugin-* if installed.
pw_imports_found=0
cy_imports_found=0
if rg -lq '@playwright/test' "$ROOT" --glob '!node_modules/**' 2>/dev/null; then
  pw_imports_found=1
  try_eslint playwright Playwright
fi
if rg -lq "from\s+['\"]cypress['\"]|[^A-Za-z0-9_]cy\.(visit|get|contains|request|intercept|session|origin|task|wait|fixture)\(" "$ROOT" --glob '!node_modules/**' --glob '*.{cy.ts,cy.js,ts,js}' 2>/dev/null; then
  cy_imports_found=1
  try_eslint cypress Cypress
fi

if [[ "$eslint_ran" -eq 0 ]]; then
  # Single-cause skip report. The old message OR'ed three causes in one line, which made
  # field failures undiagnosable (the real field cause was an eslint crash: missing
  # `typescript` peer dep in the npx env — see the npx_args comment in try_eslint).
  if [[ "$pw_imports_found" -eq 0 && "$cy_imports_found" -eq 0 ]]; then
    printf '\n[ESLint] Tier 1 not run — no Playwright/Cypress imports detected under %s.\n' "$ROOT"
  elif ! command -v npx >/dev/null 2>&1; then
    printf '\n[ESLint] Tier 1 not run — npx is not on PATH.\n'
  elif [[ "${E2E_SMELL_NO_ESLINT_DOWNLOAD:-}" == "1" ]]; then
    printf '\n[ESLint] Tier 1 not run — E2E_SMELL_NO_ESLINT_DOWNLOAD=1 is set and no locally installed plugin was found.\n'
  else
    printf '\n[ESLint] Tier 1 not run — imports were detected but the eslint run failed; the [ESLint] line above names the exact failure (resolve error, crash exit code, or watchdog timeout).\n'
  fi
fi

# Tier 2: ast-grep — Tree-sitter AST patterns. Lower FP rate than regex on the patterns it covers
# (#15, #4ce-state-bool/text/count, #4f). Skipped silently if ast-grep isn't on PATH and npx isn't either.
# Set E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 to disable the npx fallback (matches eslint tier's escape hatch).
ASTGREP_RULES_DIR="$(cd "$(dirname "$0")" && pwd)/ast-grep-rules"
if command -v ast-grep >/dev/null 2>&1; then AST_GREP="ast-grep"
elif command -v sg >/dev/null 2>&1; then AST_GREP="sg"
elif [[ "${E2E_SMELL_NO_AST_GREP_DOWNLOAD:-}" == "1" ]]; then AST_GREP=""
elif command -v npx >/dev/null 2>&1; then AST_GREP="npx --yes @ast-grep/cli"
else AST_GREP=""; fi

if [[ -n "$AST_GREP" && -d "$ASTGREP_RULES_DIR" ]]; then
  printf '\n--- Tier 2: AST-grep checks (Tree-sitter; covers FP-prone patterns more accurately) ---\n'
  ast_total=0
  ast_skipped=0
  for rule in "$ASTGREP_RULES_DIR"/sg-*.yml; do
    [[ "$(basename "$rule")" == sg-postfix-* ]] && continue  # postfix rules are for verify-fixes.sh
    rule_name=$(basename "$rule" .yml)
    # Dedupe: skip ast-grep rule if covered by an eslint plugin that ran (Tier 1 wins)
    pattern_id=$(get_pattern_for_ast_rule "$rule_name")
    if [[ -n "$pattern_id" ]] && should_skip_pattern "$pattern_id"; then
      ast_skipped=$((ast_skipped + 1))
      continue
    fi
    ast_out=$($AST_GREP scan --rule "$rule" "$ROOT" 2>&1 || true)
    # Honor `// JUSTIFIED:` — count only hits whose source line is NOT suppressed (parity with
    # Tier 1/3). ast-grep prints each hit's location as "  ┌─ <file>:<line>:<col>".
    ast_count=0
    while IFS= read -r _aloc; do
      [[ -z "$_aloc" ]] && continue
      _acol=${_aloc##*:}; _arest=${_aloc%:*}; _aln=${_arest##*:}; _afile=${_arest%:*}
      _line_is_justified "$_afile" "$_aln" && continue
      [[ ! -f "$_afile" ]] && _line_is_justified "$ROOT/$_afile" "$_aln" && continue
      ast_count=$((ast_count + 1))
    done < <(printf '%s\n' "$ast_out" | grep -oE '[^[:space:]]+:[0-9]+:[0-9]+')
    if [[ "$ast_count" -gt 0 ]]; then
      printf '\n[AST] %s (%s hit%s)\n' "$rule_name" "$ast_count" "$([[ "$ast_count" == "1" ]] && printf '' || printf 's')"
      printf '%s\n' "$ast_out" | head -30 | sed 's/^/  /'
      ast_total=$((ast_total + ast_count))
    fi
  done
  printf '\n  ast-grep total: %s hit(s)' "$ast_total"
  [[ "$ast_skipped" -gt 0 ]] && printf ' (%s rule%s skipped — covered by Tier 1 eslint)' "$ast_skipped" "$([[ "$ast_skipped" == "1" ]] && printf '' || printf 's')"
  printf '\n'
fi

printf '\n--- Tier 3: Bundled regex checks (universal fallback for grep-detectable patterns and gaps eslint/ast-grep miss) ---\n'

# Phase-0 file scope filter (Tier 3): pattern checks only apply to files that are actually
# E2E surface — basename contains `.cy.`, path has a `cypress/` component, the file imports
# @playwright/test, or it references cypress (import/require or `cy.<cmd>(` usage). Kills
# backend/unit-suite FPs that share the *.test.* suffix (observed in the field: Knex
# `.first()` flagged as #10a and an `import type ... secret` line flagged as #14 in backend
# Vitest files). Skipped files are counted and reported before the Summary — never silently.
SCOPE_STATE_DIR=$(mktemp -d)
: > "$SCOPE_STATE_DIR/in"
: > "$SCOPE_STATE_DIR/out"

file_in_e2e_scope() {
  local f="$1"
  case "$(basename "$f")" in
    *.cy.*) return 0 ;;
  esac
  case "/$f/" in
    */cypress/*) return 0 ;;
  esac
  rg -q "@playwright/test|from\s+['\"]cypress['\"]|require\(\s*['\"]cypress['\"]|(^|[^A-Za-z0-9_])cy\.[a-z]+\(" "$f" 2>/dev/null
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

run_check() {
  local severity="$1"
  local check_id="$2"
  local title="$3"
  local pattern="$4"
  local glob="$5"
  local output=""

  # Dedupe: if covered by an eslint plugin that ran in Tier 1, skip this regex check
  if should_skip_pattern "$check_id"; then
    return 0
  fi

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
  raw_output=$(rg -nP -H --color never --hidden \
    "${include_globs[@]}" \
    --glob '!node_modules/**' \
    --glob '!.git/**' \
    --glob '!playwright-report/**' \
    --glob '!cypress/reports/**' \
    --glob '!test-results/**' \
    --glob '!dist/**' \
    --glob '!build/**' \
    --glob '!.next/**' \
    --glob '!out/**' \
    --glob '!coverage/**' \
    --glob '!public/**' \
    --glob '!*.min.js' \
    --glob '!*.min.ts' \
    ${EVAL_FIXTURE_EXCLUDES[@]+"${EVAL_FIXTURE_EXCLUDES[@]}"} \
    "$pattern" -- "$ROOT" 2>/dev/null || true)

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
    _scopekeep=$(mktemp)
    while IFS= read -r _sf; do
      [[ -z "$_sf" ]] && continue
      if [[ "$(scope_status "$_sf")" == "IN" ]]; then printf '%s\n' "$_sf" >> "$_scopekeep"; fi
    done <<< "$(printf '%s\n' "$output" | awk -F: '{print $1}' | sort -u)"
    output=$(printf '%s\n' "$output" | awk -F: 'NR==FNR { if ($0 != "") k[$0] = 1; next } k[$1] { print }' "$_scopekeep" -)
    rm -f "$_scopekeep"
  fi

  # `// JUSTIFIED: <reason>` suppression (mechanical part): drop a hit when the marker is on
  # the hit line itself or the immediately preceding line. Block-level/multi-line-chain
  # placements remain Phase 2 LLM responsibility, per the SKILL.md suppression contract.
  # No-exemption contract for #7: a committed focused test is never justifiable
  # (grep-patterns.md / pattern-reference.md), so JUSTIFIED must not silence it.
  if [[ -n "$output" && "$check_id" != '#7' ]]; then
    output=$(printf '%s\n' "$output" | while IFS= read -r _hit; do
      _hf=${_hit%%:*}
      _rest=${_hit#*:}
      _hl=${_rest%%:*}
      case "$_rest" in (*"JUSTIFIED:"*) continue ;; esac
      # Walk upward through the contiguous //-comment block above the hit (max 5 lines):
      # JUSTIFIED rationales legitimately wrap onto multiple comment lines.
      if [[ "$_hl" -gt 1 ]]; then
        _just=$(sed -n "$((_hl > 5 ? _hl - 5 : 1)),$((_hl - 1))p" "$_hf" 2>/dev/null | awk '
          { lines[NR] = $0 }
          END {
            for (i = NR; i >= 1; i--) {
              t = lines[i]; sub(/^[[:space:]]+/, "", t)
              if (t ~ /^\/\//) { if (t ~ /JUSTIFIED:/) { print "Y"; exit } } else exit
            }
          }')
        [[ "$_just" == "Y" ]] && continue
      fi
      printf '%s\n' "$_hit"
    done)
  fi

  # Optional e2e content scoping (6th arg == "e2e"): keep hits only in files that carry a real
  # Playwright/Cypress marker. The marker set deliberately ERRS TOWARD INCLUSION (fail-open):
  # a unit file mentioning e.g. `router.page.url()` is admitted and its hits flow to Phase 2,
  # which owns residual unit-test elimination. Tightening here risks silently dropping real specs. Kills Vitest/Jest/RTL unit-test bleed-through — the #1 FP root
  # cause observed across the 77-repo OSS validation corpus. Markers: @playwright/test import,
  # Playwright fixture destructure `async ({ page`, direct `page.<api>` usage, or `cy.<cmd>(`.
  local flags=",${6:-},"
  if [[ "$flags" == *",e2e,"* && -n "$output" ]]; then
    local _f _keepf
    _keepf=$(mktemp)
    while IFS= read -r _f; do
      [[ -z "$_f" ]] && continue
      if rg -q "@playwright/test|async \(\{ ?page|(^|[^A-Za-z_])page\.(goto|locator|getBy|url|waitFor|click|fill)|test\.(describe|use|step|beforeEach|afterEach|fixme|slow|skip)\s*\(|from\s+['\"][^'\"]*fixtures|cy\.[a-z]+\(" "$_f" 2>/dev/null; then
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

  if [[ -n "$output" ]]; then
    local count sev_label
    count=$(printf '%s\n' "$output" | wc -l | tr -d ' ')
    total_hits=$((total_hits + count))
    sev_label="[$severity]"
    if [[ "$flags" == *",triage,"* ]]; then
      # Documented severity is unchanged, but grep alone cannot confirm the context that
      # makes these hits real (e.g. #4b needs destructive-action context — ~90% FP rate on
      # client-rendered apps where positive toBeAttached is a legitimate render-gate).
      # Route to a separate Phase-2 LLM-triage count instead of the p0 exit gate.
      llm_triage_hits=$((llm_triage_hits + count))
      sev_label="[$severity?][LLM-TRIAGE]"
    elif [[ "$severity" == "P0" ]]; then
      p0_hits=$((p0_hits + count))
    else
      p1_hits=$((p1_hits + count))
    fi

    printf '\n%s %s %s (%s hit%s)\n' "$sev_label" "$check_id" "$title" "$count" "$([[ "$count" == "1" ]] && printf '' || printf 's')"
    printf '%s\n' "$output" | sed 's/^/  /'
  fi
}

# Suffix-less Cypress layouts: files under cypress/integration/ (classic, pre-v10) and
# cypress/e2e/ (Cypress 10+) commonly have no .cy./.spec./.test. basename suffix — e.g.
# foo_spec.js or plain foo.js — so suffix-only globs miss them. This path-based include is
# appended (via the `;` multi-glob support) to Cypress-intended checks below so committed
# .only, error swallowing, hard-coded cy.wait(ms), etc. are caught in those layouts too.
CYI='**/cypress/{integration,e2e}/**/*.{js,ts}'

run_check P0 '#3' 'Error swallowing via empty catch (test scope)' '\.catch\(\s*(async\s*)?\(\)\s*=>' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'";$CYI" e2e
run_check P0 '#7' 'Focused test committed' '\.(only)\(' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'";$CYI"
run_check P1 '#9' 'Playwright hard-coded sleep' 'waitForTimeout' '*.{ts,js,tsx,jsx}' e2e
run_check P1 '#9b' 'Cypress hard-coded sleep' 'cy\.wait\(\d' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'";$CYI"
run_check P1 '#6' 'Raw DOM query inside test code' 'document\.querySelector' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e

run_check P0 '#4a' 'Always-true numeric assertion' 'toBeGreaterThanOrEqual\(0\)' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e
# #4b is grep-undecidable: positive toBeAttached is only vacuous when a destructive action
# should have removed the element; on client-rendered apps it is usually a legitimate
# render-gate (field data: ~90% FP). The `triage` flag reports it as [P0?][LLM-TRIAGE] and
# keeps it out of the p0 exit count — Phase 2 confirms destructive-action context.
run_check P0 '#4b' 'Vacuous toBeAttached assertion (positive form only; Phase 2 confirms destructive-action context)' '(?<!not\.)toBeAttached\(\)' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e,triage
# #4c-4e: one-shot reads (`expect(await <locator>.textContent()/count()/inputValue()...)`
# + sync matcher) are P0 one-shot assertions, NOT #15 — the await resolves a value, nothing
# floats. The leading `(?:...)*` group admits wrapped forms (`expect((await ...).trim())`,
# `expect(Number(await ...))`, `expect(!(await ...))`) that field runs showed being
# misfiled under #15 by the old locator-substring heuristic.
run_check P0 '#4c-4e' 'One-shot Playwright state/content assertion' 'expect\((?:[!(\s+-]|[A-Za-z_$][\w$.]*\()*await\b.*\.(isVisible|isDisabled|isEnabled|isChecked|isHidden|isEditable|textContent|innerText|getAttribute|inputValue|allTextContents|allInnerTexts|count)\([^)]*\)\)' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P0 '#4f' 'Locator always-true assertion (truthy/defined/not-null)' 'expect\(.*(locator|getBy[A-Za-z]+).*(\.toBeTruthy\(\)|\.toBeDefined\(\)|\.not\.toBeNull\(\)|\.not\.toBeUndefined\(\)|\.not\.to\.equal\(null\)|\.not\.to\.be\.null)' '*.{ts,js,tsx,jsx}' e2e
run_check P0 '#4g' 'Retry disabled with timeout zero' 'timeout:\s*0' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e
run_check P0 '#4h' 'One-shot page.url assertion' 'expect\(page\.url\(\)\)' '*.{spec.ts,spec.js,test.ts,test.js}'

run_check P0 '#5a' 'Conditional assertion bypass' 'if.*(isVisible\(|is\(.*:visible.*\))' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'";$CYI"
run_check P1 '#5b' 'Forced actionability bypass' 'force:\s*true' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e
run_check P0 '#8a' 'Dangling Playwright locator statement' '^\s*(await\s+)?page\.(locator|getBy[A-Za-z]+)\(([^()]|\([^()]*\))*\)\s*;?\s*(//.*)?$' '*.{spec.ts,spec.js,test.ts,test.js}' cont
run_check P0 '#8b' 'Boolean state result discarded' '^\s*await .*\.(isVisible|isEnabled|isChecked|isDisabled|isEditable|isHidden)\([^)]*\)\s*;?\s*(//.*)?$' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'";$CYI"
run_check P1 '#10a' 'Positional selector' '\.(nth\(|first\(\)|last\(\))' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'";$CYI"
run_check P1 '#10b' 'Serial Playwright suite' '\.describe\.serial\(' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P1 '#14' 'Hardcoded credentials' '(login|fill|type).*(["'"'"'].*password|["'"'"'].*secret|["'"'"']admin["'"'"'])' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'";$CYI"
# #15 keeps ONLY unawaited web-first matchers: the trailing matcher whitelist stops the old
# conflation where sync-matcher one-shot reads (e.g. `expect(Number(await getRowCount(page)))
# .toBe(4)` — the `page)` substring) were misfiled as #15 (ag-grid field run: 25 of 33 #15
# hits were really #4c-4e). Matcher-on-next-line splits are covered by Tier 2 (sg-15).
run_check P0 '#15' 'Missing await on Playwright expect' '^\s*expect\(\s*+(?!await\b).*(locator|getBy[A-Z][A-Za-z]*|(?<![.\w])page\)).*\.(toBeVisible|toBeHidden|toHaveText|toContainText|toHaveValue|toHaveValues|toHaveClass|toHaveAttribute|toBeChecked|toBeEnabled|toBeDisabled|toBeEditable|toBeFocused|toBeEmpty|toHaveCount|toHaveCSS|toHaveId|toHaveJSProperty|toHaveScreenshot|toHaveURL|toHaveTitle)\(' '*.{spec.ts,spec.js,test.ts,test.js}' e2e
# #15 variant: the await is misplaced INSIDE expect() onto the locator (a no-op, since a Locator
# is not thenable) instead of on expect itself, so the web-first matcher promise still floats and
# the assertion never settles. The base #15 above skips `expect(await ...` by design, so this
# catches the awaited-locator form. Bounded to web-first matchers so value-resolving reads like
# `expect(await x.isVisible()).toBe(true)` (that is #4c-4e) are not double-flagged.
run_check P0 '#15' 'Missing await on Playwright expect (awaited locator)' '^\s*expect\(\s*await\b.*\)\.(toBeVisible|toBeHidden|toHaveText|toContainText|toHaveValue|toHaveValues|toHaveClass|toHaveAttribute|toBeChecked|toBeEnabled|toBeDisabled|toBeEditable|toBeFocused|toBeEmpty|toHaveCount|toHaveCSS|toHaveId|toHaveJSProperty|toHaveScreenshot|toHaveURL|toHaveTitle)\(' '*.{spec.ts,spec.js,test.ts,test.js}' e2e
run_check P0 '#16' 'Missing await on Playwright action' '^\s*page\.(locator|getBy\w+)\(.*\)\.(click|fill|type|press|check|uncheck|selectOption|setInputFiles|hover|focus|blur)\(' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P1 '#17' 'Direct page action API' 'page\.(click|fill|type|check|uncheck|selectOption)\(["'"'"'`]' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P1 '#9c' 'Network-idle readiness check' '(waitForLoadState\(\s*[\x27\"]networkidle[\x27\"]|waitUntil:\s*[\x27\"]networkidle[\x27\"])' '*.{ts,js,tsx,jsx}' e2e
run_check P1 '#18' 'Soft assertion usage' 'expect\.soft\(' '*.{spec.ts,spec.js,test.ts,test.js}'
# #3b matches every uncaught:exception handler OPENING (single- or multi-line body): the
# old `.*false` suffix only caught the one-line `() => false` form and missed 51 multi-line
# `(err, runnable) => { return false; }` blanket suppressors in one OSS Cypress suite.
# Blanket-vs-scoped is Phase 2's documented call (handler containing expect() is exempt).
run_check P0 '#3b' 'Cypress uncaught exception suppression (Phase 2 confirms blanket vs scoped)' "on\(\s*['\"]uncaught:exception['\"]" '*.{cy.ts,cy.js,ts,js}'
run_check P1 '#19' 'Module-level mutable state in test code' '^let\s+' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e

# Out-of-scope report: one explicit line so Phase-0 skips are never a silent truncation.
scope_skipped=$(wc -l < "$SCOPE_STATE_DIR/out" | tr -d ' ')
printf '\nScope filter: %s out-of-scope file(s) skipped (pattern hits in files without Playwright/Cypress markers).\n' "$scope_skipped"
rm -rf "$SCOPE_STATE_DIR"

printf '\nSummary: %s total hit(s), %s P0, %s P1/P2 heuristic, %s LLM-triage; %s AST hit(s).\n' "$total_hits" "$p0_hits" "$p1_hits" "$llm_triage_hits" "${ast_total:-0}"

case "$FAIL_ON" in
  none)
    exit 0
    ;;
  any)
    # `any` means anything found by any tier — Tier-2 AST hits gate here too.
    [[ "$((total_hits + ${ast_total:-0}))" -eq 0 ]]
    ;;
  p0)
    [[ "$p0_hits" -eq 0 ]]
    ;;
  *)
    echo "error: E2E_SMELL_FAIL_ON must be one of: p0, any, none" >&2
    exit 2
    ;;
esac
