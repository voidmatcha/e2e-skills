#!/usr/bin/env bash
# Post-fix verification: static-check + AST-aware sed-artifact detection.
#
# Run after bulk sed/perl transforms (typically ≥10 files modified).
# Catches the two failure classes:
#   1. Compile errors from regex matching non-Locator subjects
#   2. AST anti-patterns sed accidentally introduced (double await, empty expect, orphan then)
#
# Usage: bash scripts/verify-fixes.sh <repo-path>
# Exits 0 on clean, non-zero on issues found.

set -uo pipefail

REPO="${1:-.}"

if [[ ! -d "$REPO" ]]; then
  echo "error: not a directory: $REPO" >&2
  exit 2
fi

# Resolve ast-grep (same fallback chain as scan.sh's Tier 2 block).
if command -v ast-grep >/dev/null 2>&1; then
  AST_GREP="ast-grep"
elif command -v sg >/dev/null 2>&1; then
  AST_GREP="sg"
elif command -v npx >/dev/null 2>&1; then
  AST_GREP="npx --yes @ast-grep/cli"
else
  echo "error: ast-grep required for postfix verification — install via 'brew install ast-grep' or 'npm i -g @ast-grep/cli'" >&2
  exit 2
fi

# AST rules now live with the skill they support.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RULES_DIR="$SCRIPT_DIR/../skills/e2e-reviewer/scripts/ast-grep-rules"

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
has_tsconfig=false
if (cd "$REPO" && [[ -f tsconfig.json ]] || [[ -f tsconfig.base.json ]]); then
  has_tsconfig=true
fi

if [[ "$has_tsconfig" == "true" ]]; then
  if ! command -v npx >/dev/null 2>&1; then
    echo "(npx not available — skipping tsc check)"
  else
    # First, probe whether tsc is installed (separate from running it).
    # `npx --no-install --quiet tsc --version` exits 0 if installed, non-0 if not.
    if (cd "$REPO" && npx --no-install --quiet tsc --version >/dev/null 2>&1); then
      # tsc IS installed locally — now run the actual check.
      tsc_output=$(cd "$REPO" && npx --no-install tsc --noEmit 2>&1)
      tsc_exit=$?
      if [[ "$tsc_exit" -eq 0 ]]; then
        echo "✓ tsc --noEmit clean"
      else
        echo "✗ tsc --noEmit reported errors (exit $tsc_exit):"
        printf '%s\n' "$tsc_output" | tail -10 | sed 's/^/  /'
        issues=$((issues + 1))
      fi
    else
      echo "(tsc not installed locally in $REPO — skipping; run 'npm install' first to enable)"
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

run_postfix_rule() {
  local rule_file="$1"
  local label="$2"
  local output
  output=$($AST_GREP scan --rule "$RULES_DIR/$rule_file" "$REPO" 2>&1 || true)
  local count
  count=$(printf '%s\n' "$output" | grep -cE '^(error|warning|info)\[' || true)
  count=${count:-0}
  if [[ "$count" -gt 0 ]]; then
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
