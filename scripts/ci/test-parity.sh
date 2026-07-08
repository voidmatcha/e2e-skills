#!/usr/bin/env bash
# Drift smoke test for the pattern-and-description parity checks in review.sh.
# Each case applies a known-bad mutation, runs review.sh, asserts the expected
# error substring appears, then restores the file from a backup.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)" || {
  echo "test-parity.sh: cannot resolve repo root" >&2
  exit 1
}
cd "$REPO_ROOT" || {
  echo "test-parity.sh: cannot cd to $REPO_ROOT" >&2
  exit 1
}

PLUGIN_VERSION=$(python3 - <<'PY'
import json
import pathlib

print(json.loads(pathlib.Path('.claude-plugin/plugin.json').read_text(encoding='utf-8'))['version'])
PY
)
PASS=0
FAIL=0
BACKUPS=()

cleanup() {
  # Best-effort restore: under `set -e` an early `mv` failure would otherwise
  # leave the remaining .parity-backup files on disk.
  for b in "${BACKUPS[@]:-}"; do
    if [ -n "$b" ] && [ -f "$b" ]; then
      local f="${b%.parity-backup}"
      mv "$b" "$f" || true
    fi
  done
  [ -n "${SCAN_FIXDIR:-}" ] && rm -rf "$SCAN_FIXDIR" || true
}
trap cleanup EXIT INT TERM

backup() {
  cp "$1" "$1.parity-backup"
  BACKUPS+=("$1.parity-backup")
}

restore() {
  local f="$1"
  local b="$1.parity-backup"
  if [ -f "$b" ]; then
    mv "$b" "$f"
    local new=()
    for x in "${BACKUPS[@]:-}"; do
      [ -n "$x" ] && [ "$x" != "$b" ] && new+=("$x")
    done
    BACKUPS=("${new[@]:-}")
  fi
}

assert_fails() {
  local name="$1"
  local expected="$2"
  local output
  output=$(bash scripts/ci/review.sh --quiet 2>&1 || true)
  if echo "$output" | grep -qF "$expected"; then
    echo "  [PASS] $name"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $name — expected substring not found: '$expected'" >&2
    echo "$output" | sed 's/^/         /' >&2
    FAIL=$((FAIL + 1))
  fi
}

assert_security_fails() {
  local name="$1"
  local expected="$2"
  local output
  output=$(bash scripts/ci/pre-push-security.sh --quiet 2>&1 || true)
  if echo "$output" | grep -qF "$expected"; then
    echo "  [PASS] $name"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $name — expected substring not found: '$expected'" >&2
    echo "$output" | sed 's/^/         /' >&2
    FAIL=$((FAIL + 1))
  fi
}

mutate() {
  python3 - "$1" "$2" "$3" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
old = sys.argv[2]
new = sys.argv[3]
text = path.read_text()
if old not in text:
    sys.exit(f"mutate: substring not found in {path}: {old!r}")
path.write_text(text.replace(old, new, 1))
PY
}

echo "-- Drift smoke test --"

# Case 1: bogus pattern id in grep-patterns.md (Check 1)
file="skills/e2e-reviewer/references/grep-patterns.md"
backup "$file"
mutate "$file" "| #3 Error Swallowing |" "| #99 Error Swallowing |"
assert_fails "Check 1 — bogus grep pattern id #99" "pattern #99 has no matching base id"
restore "$file"

# Case 2: missing docs row (Check 1b)
file="docs/e2e-test-smells.md"
backup "$file"
mutate "$file" "| #1 |" "| #99 |"
assert_fails "Check 1b — docs missing QR id" "missing rows for Quick Reference ids"
restore "$file"

# Case 3: README severity placement — relabel a P2 item under P0 table (Check 3)
file="README.md"
backup "$file"
mutate "$file" "| 1 | **Name-assertion mismatch**" "| 11 | **Name-assertion mismatch**"
assert_fails "Check 3 — README P0 row with P2 id" "Quick Reference severity is P2"
restore "$file"

# Case 4: pattern-reference.md severity placement — relabel a P2 id under P0 section (Check 3b)
file="skills/e2e-reviewer/references/pattern-reference.md"
backup "$file"
mutate "$file" "#### 1. Name-Assertion Alignment" "#### 11. Name-Assertion Alignment"
assert_fails "Check 3b — pattern-reference.md P0 section with P2 id" "Quick Reference severity is P2"
restore "$file"

# Case 5: Quick Reference row count drift (Check 3c)
file="skills/e2e-reviewer/SKILL.md"
backup "$file"
mutate "$file" "| 1 | Name-Assertion | P0 | LLM | Noun in name with no matching \`expect()\` |
" ""
assert_fails "Check 3c — QR row count drift" "expected 24 rows"
restore "$file"

# Case 6: out-of-order plugin.json description (Check 5)
file=".claude-plugin/plugin.json"
backup "$file"
mutate "$file" "name-assertion mismatch, missing Then" "missing Then, name-assertion mismatch"
assert_fails "Check 5 — plugin.json out-of-order pattern phrase" "missing or out-of-order pattern"
restore "$file"

# Case 7: docs orphan — strip README reference so a docs file is no longer linked
file="README.md"
backup "$file"
mutate "$file" "](docs/roadmap.md)" ""
mutate "$file" "](docs/roadmap.md)" ""
assert_fails "Check 7 — docs orphan detection" "docs/roadmap.md: orphan"
restore "$file"

# Case 8: manifest version drift — bump .codex-plugin/plugin.json out of sync with the others
file=".codex-plugin/plugin.json"
backup "$file"
mutate "$file" "\"version\": \"$PLUGIN_VERSION\"" "\"version\": \"9.9.9\""
assert_fails "Check 6 — manifest version drift" "manifest version mismatch"
restore "$file"

# Case 9: codex-plugin description out of order — same parity contract as plugin.json
file=".codex-plugin/plugin.json"
backup "$file"
mutate "$file" "name-assertion mismatch, missing Then" "missing Then, name-assertion mismatch"
assert_fails "Check 5 — codex-plugin out-of-order pattern phrase" "missing or out-of-order pattern"
restore "$file"

# Case 10: Codex plugin interface prompt limit — Codex displays at most 3 prompts
file=".codex-plugin/plugin.json"
backup "$file"
mutate "$file" "\"Diagnose failed Playwright/Cypress tests with root-cause classification.\"" "\"Diagnose failed Playwright/Cypress tests with root-cause classification.\", \"Extra prompt that should fail\""
assert_fails "Codex plugin guard — too many default prompts" "interface.defaultPrompt must contain 1-3 prompts"
restore "$file"

# Case 11: SKILL.md frontmatter description unquoted with colon-space — YAML parse regression of v0.7.3
file="skills/e2e-reviewer/SKILL.md"
backup "$file"
mutate "$file" "description: 'Static review" "description: Static review"
assert_fails "Frontmatter YAML guard — unquoted description with ': '" "colon-space"
restore "$file"

# Case 12: SKILL.md metadata.version drift vs plugin manifest version — guards against
# the v1.3.1 hole where one of four SKILL.md files got left behind during a lock-step bump
file="skills/playwright-test-generator/SKILL.md"
backup "$file"
mutate "$file" "version: \"$PLUGIN_VERSION\"" "version: \"9.9.9\""
assert_fails "SKILL.md version drift vs manifest" "does not match plugin version"
restore "$file"

# Case 13: SKILL.md description length — skills hosts reject descriptions over 1024 characters
file="skills/e2e-reviewer/SKILL.md"
backup "$file"
python3 - "$file" <<'PY_LONG_DESC'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text()
text = re.sub(
    r"^description: .+$",
    "description: '" + ("Use when reviewing Playwright/Cypress tests. " * 40).strip() + "'",
    text,
    count=1,
    flags=re.M,
)
path.write_text(text)
PY_LONG_DESC
assert_fails "SKILL.md description length guard" "frontmatter description exceeds 1024 characters"
assert_security_fails "Pre-push SKILL.md description length guard" "frontmatter description exceeds 1024 characters"
restore "$file"

# Case 14: Language guard — Hangul on a non-switcher README.md line must still fail.
# The switcher exemption only covers lines linking to README.<lang>.md translations.
file="README.md"
backup "$file"
mutate "$file" "Find Playwright/Cypress E2E tests that pass CI" "Find Playwright/Cypress E2E tests 한국어 that pass CI"
assert_fails "Language guard — Hangul outside switcher line in README.md" "Korean text found in public docs: README.md"
restore "$file"

# Case 15: README i18n structural parity — a translation losing a section must fail.
file="README.ko.md"
backup "$file"
mutate "$file" "## 설치" "###설치-변조"
assert_fails "README i18n parity — section drift in README.ko.md" "README i18n parity: README.ko.md has"
restore "$file"

# Case 16: subagent parity SP1 — dropping the absolute-path contract from an
# agent file (the A1 regression) must fail. CWD is the target project, so a
# repo-relative read target silently resolves nowhere.
file="agents/e2e-finding-verifier.md"
backup "$file"
mutate "$file" "absolute path" "path"
assert_fails "Subagent parity SP1 — agent drops absolute-path contract" "must state the caller passes the absolute"
restore "$file"

# Case 17: subagent parity SP3 — the inline fallback losing a verifier verdict
# term breaks the "identical verdict either way" contract (AGENTS.md rule 5).
file="skills/e2e-reviewer/SKILL.md"
backup "$file"
mutate "$file" "CONFIRMED / FALSE-POSITIVE / NEEDS-CONTEXT" "CONFIRMED / FALSE-POSITIVE"
assert_fails "Subagent parity SP3 — inline fallback drops a verdict term" "inline fallback missing verdict term NEEDS-CONTEXT"
restore "$file"

# Case 18: subagent parity SP4 — a new F16+ code beyond the frozen F1–F15 range
# must fail. Anchor on the bare `| F15 |` cell, NOT its display title: AGENTS.md
# freezes the CODES, and F-code titles are framework-adapted, so a title rename
# must not break this smoke test.
file="skills/playwright-debugger/SKILL.md"
backup "$file"
mutate "$file" "| F15 |" "| F16 |"
assert_fails "Subagent parity SP4 — new F16 code beyond frozen range" "found a new F16+ code"
restore "$file"

# Case 19: subagent parity SP4 — an added F17 code must ALSO fail. This guards the
# strengthening over a bare "F16" substring check: the table-set comparison catches
# any code outside F1–F15, not just the literal F16.
file="skills/playwright-debugger/SKILL.md"
backup "$file"
mutate "$file" "| F15 |" "| F17 |"
assert_fails "Subagent parity SP4 — added F17 caught by table-set check" "F-code table must be exactly F1"
restore "$file"

# Case 20: subagent parity SP2 — dropping the absolute-path requirement from the
# DELEGATION LINE (the line naming the subagent) must fail, even if the word
# 'absolute' survives elsewhere in the file. Guards the A1 regression on the
# caller side.
file="skills/playwright-debugger/SKILL.md"
backup "$file"
mutate "$file" "the **absolute** path to this skill" "the path to this skill"
assert_fails "Subagent parity SP2 — delegation line drops absolute-path contract" "delegation line must pass the subagent an absolute"
restore "$file"

# ---------------------------------------------------------------------------
# Scanner detection smoke — fixture-based and offline: eslint auto-download is
# disabled via E2E_SMELL_NO_ESLINT_DOWNLOAD=1 (so counts come from the Tier-3
# regex path) and ast-grep download via E2E_SMELL_NO_AST_GREP_DOWNLOAD=1. A
# locally installed ast-grep may still run Tier 2 offline, so assertions only
# key on Tier-3 output shapes ('[P0] #id' headers and the Summary line).
# ---------------------------------------------------------------------------
echo ""
echo "-- Scanner detection smoke --"

SCAN_SH="skills/e2e-reviewer/scripts/scan.sh"
SCAN_FIXDIR=$(mktemp -d /tmp/e2e-scan-smoke.XXXXXX)

run_scan() { # $1 = fixture subdir, $2 = FAIL_ON mode; sets SCAN_OUT and SCAN_RC
  SCAN_RC=0
  SCAN_OUT=$(E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 \
    E2E_SMELL_FAIL_ON="$2" bash "$SCAN_SH" "$SCAN_FIXDIR/$1" 2>&1) || SCAN_RC=$?
}

assert_scan_contains() {
  local name="$1"
  local expected="$2"
  if printf '%s\n' "$SCAN_OUT" | grep -qF "$expected"; then
    echo "  [PASS] $name"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $name — expected substring not found: '$expected'" >&2
    printf '%s\n' "$SCAN_OUT" | sed 's/^/         /' >&2
    FAIL=$((FAIL + 1))
  fi
}

assert_scan_absent() {
  local name="$1"
  local unexpected="$2"
  if printf '%s\n' "$SCAN_OUT" | grep -qF "$unexpected"; then
    echo "  [FAIL] $name — unexpected substring found: '$unexpected'" >&2
    printf '%s\n' "$SCAN_OUT" | sed 's/^/         /' >&2
    FAIL=$((FAIL + 1))
  else
    echo "  [PASS] $name"
    PASS=$((PASS + 1))
  fi
}

assert_scan_rc() {
  local name="$1"
  local expected_rc="$2"
  if [ "$SCAN_RC" -eq "$expected_rc" ]; then
    echo "  [PASS] $name"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $name — expected exit $expected_rc, got $SCAN_RC" >&2
    printf '%s\n' "$SCAN_OUT" | sed 's/^/         /' >&2
    FAIL=$((FAIL + 1))
  fi
}

# Case S1: JUSTIFIED above test.only must NOT suppress #7 (no-exemption contract)
mkdir -p "$SCAN_FIXDIR/s1"
cat > "$SCAN_FIXDIR/s1/focused.spec.ts" <<'EOF'
import { test, expect } from '@playwright/test';

// JUSTIFIED: debugging leftover — the no-exemption contract must still flag this
test.only('focused test', async ({ page }) => {
  await page.goto('/');
});
EOF
run_scan s1 none
assert_scan_contains "Scanner S1 — JUSTIFIED does not silence #7" "[P0] #7"
assert_scan_contains "Scanner S1 — #7 hit names the fixture line" "focused.spec.ts:4"

# Case S2: fixture whose only P0 is test.only must exit 1 under FAIL_ON=p0 (Tier-3 path)
run_scan s1 p0
assert_scan_rc "Scanner S2 — test.only fixture exits 1 under FAIL_ON=p0" 1

# Case S3: sync-matcher one-shot read is #4c-4e (one-shot read, P0), never #15
mkdir -p "$SCAN_FIXDIR/s3"
cat > "$SCAN_FIXDIR/s3/oneshot.spec.ts" <<'EOF'
import { test, expect } from '@playwright/test';

test('one-shot read with sync matcher', async ({ page }) => {
  expect(await page.locator('.cell').textContent()).toBe('Name');
});
EOF
run_scan s3 none
assert_scan_contains "Scanner S3 — sync-matcher read reported as #4c-4e" "#4c-4e"
assert_scan_absent "Scanner S3 — sync-matcher read not reported as #15" "#15"

# Case S4: Knex-style .first() in a non-E2E (backend Vitest) file produces no hit
mkdir -p "$SCAN_FIXDIR/s4"
cat > "$SCAN_FIXDIR/s4/user-dal.test.ts" <<'EOF'
import { describe, it, expect } from 'vitest';
import { db } from './db';

describe('user dal', () => {
  it('returns the first user', async () => {
    const user = await db('users').where({ id: 1 }).first();
    expect(user).toBeDefined();
  });
});
EOF
run_scan s4 none
assert_scan_absent "Scanner S4 — backend Knex .first() not flagged as #10a" "#10a"
assert_scan_contains "Scanner S4 — out-of-scope file skip is reported" "1 out-of-scope file(s) skipped"
assert_scan_contains "Scanner S4 — zero total hits" "Summary: 0 total hit(s)"

# Case S5: Cypress 10+ layout — cypress/e2e/<name>_spec.js with a suffix-less basename
# (no .cy./.spec./.test. dot-suffix) must still be scanned. Guards the $CYI path-include
# covering cypress/e2e/ (not just the legacy cypress/integration/); a suffix-only glob
# would miss cy.wait(ms) here.
mkdir -p "$SCAN_FIXDIR/s5/cypress/e2e"
cat > "$SCAN_FIXDIR/s5/cypress/e2e/widget_link_spec.js" <<'EOF'
describe('widget link', () => {
  it('waits then asserts', () => {
    cy.visit('/');
    cy.wait(300);
    cy.get('[data-cy=link]').click();
  });
});
EOF
run_scan s5 none
assert_scan_contains "Scanner S5 — cypress/e2e _spec.js hard-coded sleep flagged as #9b" "#9b"
assert_scan_contains "Scanner S5 — #9b hit names the cypress/e2e fixture line" "widget_link_spec.js:4"

rm -rf "$SCAN_FIXDIR"

echo ""
echo "========================================"
echo "  Drift smoke: $PASS passed, $FAIL failed"
echo "========================================"

[ "$FAIL" -gt 0 ] && exit 1
exit 0
