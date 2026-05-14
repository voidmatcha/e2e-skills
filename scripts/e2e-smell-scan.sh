#!/usr/bin/env bash
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

run_check() {
  local severity="$1"
  local check_id="$2"
  local title="$3"
  local pattern="$4"
  local glob="$5"
  local output=""

  output=$(rg -n --color never --hidden \
    --glob '!node_modules/**' \
    --glob '!.git/**' \
    --glob '!playwright-report/**' \
    --glob '!cypress/reports/**' \
    --glob '!test-results/**' \
    --glob "$glob" \
    "$pattern" -- "$ROOT" 2>/dev/null || true)

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

run_check P0 '#3' 'Error swallowing via empty catch' '\.catch\(\s*(async\s*)?\(\)\s*=>' '*.{ts,js,tsx,jsx,cy.ts,cy.js}'
run_check P0 '#7' 'Focused test committed' '\.(only)\(' '*.{spec.ts,spec.js,test.ts,test.js,cy.ts,cy.js}'
run_check P1 '#9' 'Playwright hard-coded sleep' 'waitForTimeout' '*.{ts,js,tsx,jsx}'
run_check P1 '#9b' 'Cypress hard-coded sleep' 'cy\.wait\(\d' '*.{cy.ts,cy.js}'
run_check P1 '#6' 'Raw DOM query inside test code' 'document\.querySelector' '*.{ts,js,tsx,jsx,cy.ts,cy.js}'

run_check P0 '#4a' 'Always-true numeric assertion' 'toBeGreaterThanOrEqual\(0\)' '*.{ts,js,tsx,jsx,cy.ts,cy.js}'
run_check P0 '#4b' 'Vacuous toBeAttached assertion' 'toBeAttached\(\)' '*.{ts,js,tsx,jsx,cy.ts,cy.js}'
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
