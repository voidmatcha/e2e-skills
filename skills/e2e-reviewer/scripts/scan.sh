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
try_eslint() {
  local plugin="$1"; local config="$2"; local label="$3"
  command -v npx >/dev/null 2>&1 || return 1

  local plugin_path="$ROOT/node_modules/eslint-plugin-$plugin"
  local mode npx_args
  if [[ -d "$plugin_path" ]]; then
    mode="locally installed"
    npx_args=(--no-install eslint)
  elif [[ "${E2E_SMELL_NO_ESLINT_DOWNLOAD:-}" == "1" ]]; then
    printf '\n[ESLint] %s — eslint-plugin-%s not installed and E2E_SMELL_NO_ESLINT_DOWNLOAD=1 — skipping\n' "$label" "$plugin"
    return 1
  else
    mode="auto-downloaded via npx (set E2E_SMELL_NO_ESLINT_DOWNLOAD=1 to skip)"
    npx_args=(--yes -p eslint -p "eslint-plugin-$plugin" $([[ "$plugin" == "cypress" ]] && printf -- '-p\neslint-plugin-mocha\n') eslint)
  fi

  printf '\n[ESLint] %s — running eslint-plugin-%s (%s)\n' "$label" "$plugin" "$mode"
  local out
  out=$(cd "$ROOT" && npx "${npx_args[@]}" --no-eslintrc -c "$config" \
        --ext .ts,.js,.tsx,.jsx,.cy.ts,.cy.js . 2>&1) || true
  if printf '%s' "$out" | grep -qE '(error|warning)' ; then
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
  try_eslint playwright '{"plugins":["playwright"],"extends":["plugin:playwright/recommended"]}' Playwright
fi
if rg -lq "from\s+['\"]cypress['\"]|cy\." "$ROOT" --glob '!node_modules/**' --glob '*.{cy.ts,cy.js,ts,js}' 2>/dev/null; then
  try_eslint cypress '{"plugins":["cypress","mocha"],"extends":["plugin:cypress/recommended"]}' Cypress
fi

if [[ "$eslint_ran" -eq 0 ]]; then
  printf '\n[ESLint] Tier 1 not run (no Playwright/Cypress imports detected, or npx unavailable, or download disabled).\n'
fi

# Tier 2: ast-grep — Tree-sitter AST patterns. Lower FP rate than regex on the patterns it covers
# (#15, #4ce-state-bool/text/count, #4f). Skipped silently if ast-grep isn't on PATH and npx isn't either.
ASTGREP_RULES_DIR="$(cd "$(dirname "$0")" && pwd)/ast-grep-rules"
if command -v ast-grep >/dev/null 2>&1; then AST_GREP="ast-grep"
elif command -v sg >/dev/null 2>&1; then AST_GREP="sg"
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

printf '\n--- Tier 3: Bundled regex checks (universal fallback — covers all 19 patterns including gaps eslint/ast-grep miss) ---\n'

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
  raw_output=$(rg -nP --color never --hidden \
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
    --glob "$glob" \
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

run_check P0 '#3' 'Error swallowing via empty catch (test scope)' '\.catch\(\s*(async\s*)?\(\)\s*=>' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P0 '#7' 'Focused test committed' '\.(only)\(' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P1 '#9' 'Playwright hard-coded sleep' 'waitForTimeout' '*.{ts,js,tsx,jsx}'
run_check P1 '#9b' 'Cypress hard-coded sleep' 'cy\.wait\(\d' '*.{cy.ts,cy.js}'
run_check P1 '#6' 'Raw DOM query inside test code' 'document\.querySelector' '*.{ts,js,tsx,jsx,cy.ts,cy.js}'

run_check P0 '#4a' 'Always-true numeric assertion' 'toBeGreaterThanOrEqual\(0\)' '*.{ts,js,tsx,jsx,cy.ts,cy.js}'
run_check P0 '#4b' 'Vacuous toBeAttached assertion (positive form only)' '(?<!not\.)toBeAttached\(\)' '*.{ts,js,tsx,jsx,cy.ts,cy.js}'
run_check P0 '#4c-4e' 'One-shot Playwright state/content assertion' 'expect\(await.*\.(isVisible|isDisabled|isEnabled|isChecked|isHidden|textContent|innerText|getAttribute|inputValue)\(\)\)' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P0 '#4f' 'Locator-as-truthy assertion' 'expect\(.*(locator|getBy[A-Za-z]+).*\.toBeTruthy\(\)' '*.{ts,js,tsx,jsx}'
run_check P0 '#4g' 'Retry disabled with timeout zero' 'timeout:\s*0' '*.{ts,js,tsx,jsx,cy.ts,cy.js}'
run_check P0 '#4h' 'One-shot page.url assertion' 'expect\(page\.url\(\)\)' '*.{spec.ts,spec.js,test.ts,test.js}'

run_check P0 '#5a' 'Conditional assertion bypass' 'if.*(isVisible|is\(.*:visible.*\))' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P1 '#5b' 'Forced actionability bypass' 'force:\s*true' '*.{ts,js,tsx,jsx,cy.ts,cy.js}'
run_check P0 '#8a' 'Dangling Playwright locator statement' '^\s*(await\s+)?page\.(locator|getBy[A-Za-z]+)\([^)]*\)\s*;?\s*$' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P0 '#8b' 'Boolean state result discarded' '^\s*await .*\.(isVisible|isEnabled|isChecked|isDisabled|isEditable|isHidden)\(\)\s*;' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P1 '#10a' 'Positional selector' '\.(nth\(|first\(\)|last\(\))' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P1 '#10b' 'Serial Playwright suite' '\.describe\.serial\(' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P1 '#14' 'Hardcoded credentials' '(login|fill|type).*(["'"'"'].*password|["'"'"'].*secret|["'"'"']admin["'"'"'])' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P0 '#15' 'Missing await on Playwright expect' '^\s*expect\(.*(locator|getBy[A-Za-z]+|page\))' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P0 '#16' 'Missing await on Playwright action' '^\s*page\.(locator|getBy\w+)\(.*\)\.(click|fill|type|press|check|uncheck|selectOption|setInputFiles|hover|focus|blur)\(' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P1 '#17' 'Direct page action API' 'page\.(click|fill|type|check|uncheck|selectOption)\(["'"'"'`]' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P1 '#9c' 'Network-idle readiness check' 'networkidle' '*.{ts,js,tsx,jsx}'
run_check P1 '#18' 'Soft assertion usage' 'expect\.soft\(' '*.{spec.ts,spec.js,test.ts,test.js}'
run_check P0 '#3b' 'Cypress uncaught exception suppression' "on\('uncaught:exception'.*false" '*.{cy.ts,cy.js,ts,js}'

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
