#!/usr/bin/env bash
# Drift smoke test for the pattern-and-description parity checks in review.sh.
# Each case applies a known-bad mutation, runs review.sh, asserts the expected
# error substring appears, then restores the file from a backup.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)" || {
  echo "test-parity.sh: cannot resolve repo root" >&2
  exit 1
}
cd "$REPO_ROOT" || {
  echo "test-parity.sh: cannot cd to $REPO_ROOT" >&2
  exit 1
}

PASS=0
FAIL=0
BACKUPS=()

cleanup() {
  for b in "${BACKUPS[@]:-}"; do
    if [ -n "$b" ] && [ -f "$b" ]; then
      local f="${b%.parity-backup}"
      mv "$b" "$f"
    fi
  done
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
    for x in "${BACKUPS[@]}"; do
      [ "$x" != "$b" ] && new+=("$x")
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

# Case 4: SKILL.md severity placement — relabel a P2 id under P0 section (Check 3b)
file="skills/e2e-reviewer/SKILL.md"
backup "$file"
mutate "$file" "#### 1. Name-Assertion Alignment" "#### 11. Name-Assertion Alignment"
assert_fails "Check 3b — SKILL.md P0 section with P2 id" "Quick Reference severity is P2"
restore "$file"

# Case 5: Quick Reference row count drift (Check 3c)
file="skills/e2e-reviewer/SKILL.md"
backup "$file"
mutate "$file" "| 1 | Name-Assertion | P0 | LLM | Noun in name with no matching \`expect()\` |
" ""
assert_fails "Check 3c — QR row count drift" "expected 19 rows"
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
mutate "$file" "See [Open Source Case Studies](docs/case-studies.md) for short before/after lessons from these PRs." ""
assert_fails "Check 7 — docs orphan detection" "docs/case-studies.md: orphan"
restore "$file"

# Case 8: manifest version drift — bump .codex-plugin/plugin.json out of sync with the others
file=".codex-plugin/plugin.json"
backup "$file"
mutate "$file" "\"version\": \"1.2.2\"" "\"version\": \"9.9.9\""
assert_fails "Check 6 — manifest version drift" "manifest version mismatch"
restore "$file"

# Case 9: codex-plugin description out of order — same parity contract as plugin.json
file=".codex-plugin/plugin.json"
backup "$file"
mutate "$file" "name-assertion mismatch, missing Then" "missing Then, name-assertion mismatch"
assert_fails "Check 5 — codex-plugin out-of-order pattern phrase" "missing or out-of-order pattern"
restore "$file"

# Case 10: SKILL.md frontmatter description unquoted with colon-space — YAML parse regression of v0.7.3
file="skills/e2e-reviewer/SKILL.md"
backup "$file"
mutate "$file" "description: 'Use when reviewing" "description: Use when reviewing"
mutate "$file" "specs.'" "specs."
assert_fails "Frontmatter YAML guard — unquoted description with ': '" "colon-space"
restore "$file"

echo ""
echo "========================================"
echo "  Drift smoke: $PASS passed, $FAIL failed"
echo "========================================"

[ "$FAIL" -gt 0 ] && exit 1
exit 0
