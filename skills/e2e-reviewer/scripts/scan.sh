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
eslint_ran=0
playwright_lint_done=0
cypress_lint_done=0

# Coverage map — patterns the eslint plugin's `recommended` config catches reliably.
# When the plugin runs successfully, Tier 2 (ast-grep) and Tier 3 (regex) skip these to avoid duplicate reports.
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
    npx_args=(--yes -p 'eslint@^9' -p "eslint-plugin-$plugin" -p '@typescript-eslint/parser')
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

  # Conditional evals/files ignore mirrors Tier 3's EVAL_FIXTURE_EXCLUDES.
  local _cfg _evalign=""
  _cfg="$_cfgd/eslint.config.mjs"
  # bash 3.2 + set -u treats an empty array as unset; ${arr[*]+x} is the safe presence test.
  if [[ -n "${EVAL_FIXTURE_EXCLUDES[*]+x}" ]]; then _evalign="'**/evals/files/**',"; fi
  if [[ "$plugin" == "playwright" ]]; then
    cat > "$_cfg" <<EOFCFG
import playwright from '$_plugin_abs';
import tsParser from '$_parser_abs';
export default [
  { ignores: ['**/node_modules/**','**/dist/**','**/build/**','**/.next/**','**/out/**','**/coverage/**','**/public/**','**/*.min.js',$_evalign] },
  {
    files: ['**/*.ts','**/*.js','**/*.tsx','**/*.jsx'],
    plugins: { playwright },
    languageOptions: { parser: tsParser, ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } },
    rules: (playwright.configs['flat/recommended'] ?? playwright.configs.recommended).rules,
  },
];
EOFCFG
  else
    cat > "$_cfg" <<EOFCFG
import cypress from '$_plugin_abs';
import mocha from '$_mocha_abs';
import tsParser from '$_parser_abs';
const cypressRules = (cypress.configs['flat/recommended'] ?? cypress.configs.recommended).rules;
export default [
  { ignores: ['**/node_modules/**','**/dist/**','**/build/**','**/coverage/**','**/*.min.js',$_evalign] },
  {
    files: ['**/*.ts','**/*.js','**/*.tsx','**/*.jsx'],
    plugins: { cypress, mocha },
    languageOptions: { parser: tsParser, ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } },
    rules: { ...cypressRules, 'mocha/no-exclusive-tests': 'error' },
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
if rg -lq '@playwright/test' "$ROOT" --glob '!node_modules/**' 2>/dev/null; then
  try_eslint playwright Playwright
fi
if rg -lq "from\s+['\"]cypress['\"]|[^A-Za-z0-9_]cy\.(visit|get|contains|request|intercept|session|origin|task|wait|fixture)\(" "$ROOT" --glob '!node_modules/**' --glob '*.{cy.ts,cy.js,ts,js}' 2>/dev/null; then
  try_eslint cypress Cypress
fi

if [[ "$eslint_ran" -eq 0 ]]; then
  printf '\n[ESLint] Tier 1 not run (no Playwright/Cypress imports detected, or npx unavailable, or download disabled).\n'
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
    ast_count=$(printf '%s\n' "$ast_out" | grep -cE '^(error|warning|info)\[' || true)
    ast_count=${ast_count:-0}
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
  # NOTE: ripgrep gives precedence to later globs — the include glob MUST come first
  # so the negations below always win (a basename include declared last would re-include
  # files inside excluded dirs; this previously let vendored dist/ hits through on repos
  # that don't gitignore their build output).
  raw_output=$(rg -nP --color never --hidden \
    --glob "$glob" \
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

  # `// JUSTIFIED: <reason>` suppression (mechanical part): drop a hit when the marker is on
  # the hit line itself or the immediately preceding line. Block-level/multi-line-chain
  # placements remain Phase 2 LLM responsibility, per the SKILL.md suppression contract.
  if [[ -n "$output" ]]; then
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
    local count
    count=$(printf '%s\n' "$output" | wc -l | tr -d ' ')
    total_hits=$((total_hits + count))
    if [[ "$severity" == "P0" ]]; then
      p0_hits=$((p0_hits + count))
    else
      p1_hits=$((p1_hits + count))
    fi

    printf '\n[%s] %s %s (%s hit%s)\n' "$severity" "$check_id" "$title" "$count" "$([[ "$count" == "1" ]] && printf '' || printf 's')"
    printf '%s\n' "$output" | sed 's/^/  /'
  fi
}

run_check P0 '#3' 'Error swallowing via empty catch (test scope)' '\.catch\(\s*(async\s*)?\(\)\s*=>' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}' e2e
run_check P0 '#7' 'Focused test committed' '\.(only)\(' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P1 '#9' 'Playwright hard-coded sleep' 'waitForTimeout' '*.{ts,js,tsx,jsx}' e2e
run_check P1 '#9b' 'Cypress hard-coded sleep' 'cy\.wait\(\d' '*.{cy.ts,cy.js}'
run_check P1 '#6' 'Raw DOM query inside test code' 'document\.querySelector' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e

run_check P0 '#4a' 'Always-true numeric assertion' 'toBeGreaterThanOrEqual\(0\)' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e
run_check P0 '#4b' 'Vacuous toBeAttached assertion (positive form only)' '(?<!not\.)toBeAttached\(\)' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e
run_check P0 '#4c-4e' 'One-shot Playwright state/content assertion' 'expect\(await.*\.(isVisible|isDisabled|isEnabled|isChecked|isHidden|textContent|innerText|getAttribute|inputValue|allTextContents)\([^)]*\)\)' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P0 '#4f' 'Locator-as-truthy assertion' 'expect\(.*(locator|getBy[A-Za-z]+).*\.toBeTruthy\(\)' '*.{ts,js,tsx,jsx}' e2e
run_check P0 '#4g' 'Retry disabled with timeout zero' 'timeout:\s*0' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e
run_check P0 '#4h' 'One-shot page.url assertion' 'expect\(page\.url\(\)\)' '*.{spec.ts,spec.js,test.ts,test.js}'

run_check P0 '#5a' 'Conditional assertion bypass' 'if.*(isVisible\(|is\(.*:visible.*\))' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P1 '#5b' 'Forced actionability bypass' 'force:\s*true' '*.{ts,js,tsx,jsx,cy.ts,cy.js}' e2e
run_check P0 '#8a' 'Dangling Playwright locator statement' '^\s*(await\s+)?page\.(locator|getBy[A-Za-z]+)\(([^()]|\([^()]*\))*\)\s*;?\s*(//.*)?$' '*.{spec.ts,spec.js,test.ts,test.js}' cont
run_check P0 '#8b' 'Boolean state result discarded' '^\s*await .*\.(isVisible|isEnabled|isChecked|isDisabled|isEditable|isHidden)\([^)]*\)\s*;?\s*(//.*)?$' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P1 '#10a' 'Positional selector' '\.(nth\(|first\(\)|last\(\))' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P1 '#10b' 'Serial Playwright suite' '\.describe\.serial\(' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P1 '#14' 'Hardcoded credentials' '(login|fill|type).*(["'"'"'].*password|["'"'"'].*secret|["'"'"']admin["'"'"'])' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P0 '#15' 'Missing await on Playwright expect' '^\s*expect\(\s*+(?!await\b).*(locator|getBy[A-Z][A-Za-z]*|(?<![.\w])page\))' '*.{spec.ts,spec.js,test.ts,test.js}' e2e
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

printf '\nSummary: %s total hit(s), %s P0, %s P1/P2 heuristic.\n' "$total_hits" "$p0_hits" "$p1_hits"

case "$FAIL_ON" in
  none)
    exit 0
    ;;
  any)
    [[ "$total_hits" -eq 0 ]]
    ;;
  p0)
    [[ "$p0_hits" -eq 0 ]]
    ;;
  *)
    echo "error: E2E_SMELL_FAIL_ON must be one of: p0, any, none" >&2
    exit 2
    ;;
esac
