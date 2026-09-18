#!/usr/bin/env bash
# Drift smoke test for the repository parity checks in review.sh.
# Each case applies a known-bad mutation, runs review.sh, asserts the expected
# error substring appears, then restores the file from a backup.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd -P)" || {
  echo "test-parity.sh: cannot resolve repo root" >&2
  exit 1
}
cd "$REPO_ROOT" || {
  echo "test-parity.sh: cannot cd to $REPO_ROOT" >&2
  exit 1
}
source "$REPO_ROOT/scripts/ci/lib/init-python-isolation.sh" || exit 2

if [ -z "${E2E_PARITY_DISPOSABLE_ROOT:-}" ]; then
  # Fan the case list out over several disposable copies. Each worker walks every case and asserts
  # only its own shard, so the union is the unsharded suite; the runner still proves the source
  # digest once around the whole fan-out. Default 4; E2E_PARITY_WORKERS=1 restores the
  # historical single-copy run, and 0 derives the count from the core count. A worker
  # costs more than a core here — it runs review.sh over its own full-tree copy — so a
  # host with fewer than ~4 cores should set this down rather than take the default.
  parity_workers="${E2E_PARITY_WORKERS:-4}"
  case "$parity_workers" in ''|*[!0-9]*) parity_workers=1 ;; esac
  if [ "$parity_workers" -eq 0 ]; then
    parity_workers=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)
    [ "$parity_workers" -gt 4 ] && parity_workers=4
  fi
  exec python3 \
    "$REPO_ROOT/scripts/ci/lib/run_disposable_parity.py" \
    "$REPO_ROOT" \
    "$parity_workers"
fi

if [ "$REPO_ROOT" != "$E2E_PARITY_DISPOSABLE_ROOT" ] ||
   [ ! -f "$REPO_ROOT/.e2e-parity-disposable-root" ]; then
  echo "test-parity.sh: refusing mutations outside the marked disposable copy" >&2
  exit 2
fi

PLUGIN_VERSION=$(python3 - <<'PY'
import json
import pathlib

print(json.loads(pathlib.Path('.claude-plugin/plugin.json').read_text(encoding='utf-8'))['version'])
PY
)
PASS=0
FAIL=0
BACKUPS=()
PARITY_SECURITY_BACKUP=""

cleanup() {
  local parity_security_backup="${PARITY_SECURITY_BACKUP:-}"
  PARITY_SECURITY_BACKUP=""
  if [ -n "$parity_security_backup" ] && [ -f "$parity_security_backup" ]; then
    /bin/mv -f -- "$parity_security_backup" scripts/ci/pre-push-security.sh || true
  fi
  # Best-effort restore: under `set -e` an early `mv` failure would otherwise
  # leave the remaining .parity-backup files on disk.
  for b in "${BACKUPS[@]:-}"; do
    if [ -n "$b" ] && [ -f "$b" ]; then
      local f="${b%.parity-backup}"
      mv "$b" "$f" || true
    fi
  done
  [ -n "${SCAN_FIXDIR:-}" ] && rm -rf "$SCAN_FIXDIR" || true
  [ -n "${LANGUAGE_BAD_FILE:-}" ] && rm -f "$LANGUAGE_BAD_FILE" || true
  [ -n "${ORPHAN_BAD_FILE:-}" ] && rm -f "$ORPHAN_BAD_FILE" || true
  [ "${TRIGGER_FIXTURE_CREATED:-0}" = "1" ] &&
    rm -f "${TRIGGER_FIXTURE_FILE:-}" || true
}

handle_signal() {
  local signal="$1"
  local status=143
  [ "$signal" = "INT" ] && status=130
  trap - "$signal"
  cleanup
  /bin/kill -s "$signal" "$$" 2>/dev/null || exit "$status"
}

trap cleanup EXIT
trap 'handle_signal INT' INT
trap 'handle_signal TERM' TERM

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

# Shard selector. run_disposable_parity.py may fan the suite out across several disposable
# copies; each worker runs every case but only asserts the ones whose index is its own. The
# counter increments for every case on every worker, so an index is stable no matter how the
# fan-out is sized, and running unsharded (the default) executes all of them.
CASE_INDEX=0
PARITY_SHARD_INDEX="${E2E_PARITY_SHARD_INDEX:-0}"
PARITY_SHARD_COUNT="${E2E_PARITY_SHARD_COUNT:-1}"
case "$PARITY_SHARD_COUNT" in ''|*[!0-9]*|0) echo "test-parity: E2E_PARITY_SHARD_COUNT must be a positive integer" >&2; exit 2 ;; esac
case "$PARITY_SHARD_INDEX" in ''|*[!0-9]*) echo "test-parity: E2E_PARITY_SHARD_INDEX must be a non-negative integer" >&2; exit 2 ;; esac
if [ "$PARITY_SHARD_INDEX" -ge "$PARITY_SHARD_COUNT" ]; then
  echo "test-parity: shard index $PARITY_SHARD_INDEX is out of range for count $PARITY_SHARD_COUNT" >&2
  exit 2
fi

# Returns 0 when the case that is about to run belongs to this shard.
claim_case() {
  CASE_INDEX=$((CASE_INDEX + 1))
  [ $(( (CASE_INDEX - 1) % PARITY_SHARD_COUNT )) -eq "$PARITY_SHARD_INDEX" ]
}

run_review_without_duplicate_security() {
  # ci-local runs the real security gate before entering this disposable-copy
  # mutation suite, and assert_security_fails below executes it again for every
  # security-specific mutation. Ordinary review mutations only need to prove
  # that review.sh detects their expected contract drift. Replacing the nested
  # security invocation inside this marked disposable copy avoids repeating the
  # same unchanged gate for every case without creating a skip path in either
  # canonical script.
  local output_name="$1"
  local security="scripts/ci/pre-push-security.sh"
  local review_output=""
  [ "$output_name" = "output" ] || return 2
  PARITY_SECURITY_BACKUP="${security}.parity-real"
  [ ! -e "$PARITY_SECURITY_BACKUP" ] || {
    echo "test-parity: stale security backup in disposable copy" >&2
    return 2
  }
  /bin/mv -- "$security" "$PARITY_SECURITY_BACKUP" || return 2
  if ! printf '%s\n' '#!/bin/bash -p' 'exit 0' >"$security"; then
    /bin/mv -f -- "$PARITY_SECURITY_BACKUP" "$security" || true
    PARITY_SECURITY_BACKUP=""
    return 2
  fi
  /bin/chmod 700 "$security" || {
    /bin/mv -f -- "$PARITY_SECURITY_BACKUP" "$security" || true
    PARITY_SECURITY_BACKUP=""
    return 2
  }

  local status=0
  review_output=$(/bin/bash scripts/ci/review.sh --quiet 2>&1) || status=$?
  /bin/rm -f -- "$security"
  /bin/mv -- "$PARITY_SECURITY_BACKUP" "$security" || return 2
  PARITY_SECURITY_BACKUP=""
  printf -v "$output_name" '%s' "$review_output"
  return "$status"
}

assert_fails() {
  local name="$1"
  local expected="$2"
  local output=""
  local status=0
  claim_case || return 0
  run_review_without_duplicate_security output || status=$?
  if [ "$status" -eq 0 ]; then
    echo "  [FAIL] $name — review.sh exited 0 on the mutation (a warning is not a gate failure)" >&2
    echo "$output" | sed 's/^/         /' >&2
    FAIL=$((FAIL + 1))
  elif grep -qF "$expected" <<<"$output"; then
    echo "  [PASS] $name"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $name — expected substring not found: '$expected'" >&2
    echo "$output" | sed 's/^/         /' >&2
    FAIL=$((FAIL + 1))
  fi
}

assert_passes() {
  local name="$1"
  local output=""
  local status=0
  claim_case || return 0
  run_review_without_duplicate_security output || status=$?
  if [ "$status" -eq 0 ]; then
    echo "  [PASS] $name"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $name — review unexpectedly failed" >&2
    echo "$output" | sed 's/^/         /' >&2
    FAIL=$((FAIL + 1))
  fi
}

assert_security_fails() {
  local name="$1"
  local expected="$2"
  local output
  claim_case || return 0
  output=$(/bin/bash -p scripts/ci/pre-push-security.sh --quiet 2>&1 || true)
  if grep -qF "$expected" <<<"$output"; then
    echo "  [PASS] $name"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] $name — expected substring not found: '$expected'" >&2
    echo "$output" | sed 's/^/         /' >&2
    FAIL=$((FAIL + 1))
  fi
}

assert_verification_parity_fails() {
  local name="$1"
  local expected="$2"
  local output
  claim_case || return 0
  output=$(bash scripts/ci/check-verification-parity.sh 2>&1 || true)
  if grep -qF "$expected" <<<"$output"; then
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

# Case 2b: malformed docs taxonomy row — ID/severity parity can pass while
# the public Markdown row drops its rationale/action columns.
file="docs/e2e-test-smells.md"
backup "$file"
mutate \
  "$file" \
  "| #19 | Module-level mutable state in test code | Top-level (column-0) mutable state in a test utility or POM — an initialised \`let\`, a \`var\`, or a mutated \`const\` container — persists across tests within a long-lived worker. Independent worker copies can generate the same supposedly unique value during parallel execution. | Move mutable state behind per-test setup (\`beforeEach\`, fixtures, or factories), or use runtime-unique values such as \`Date.now()\` plus random data or \`testInfo\`-scoped identifiers. |" \
  "| #19 | Module-level mutable state in test code | Top-level (column-0) mutable state persists across tests within a worker. |"
assert_fails \
  "Check 1c — docs taxonomy row must keep four columns" \
  "taxonomy row must have 4 non-empty columns"
restore "$file"

# Case 2c: four populated cells are still malformed without the closing table
# delimiter; this is the shape produced by hard-wrapping inside the last cell.
file="docs/e2e-test-smells.md"
backup "$file"
mutate \
  "$file" \
  "random data or \`testInfo\`-scoped identifiers. |" \
  "random data or \`testInfo\`-scoped identifiers."
assert_fails \
  "Check 1c — docs taxonomy row must retain its closing delimiter" \
  "taxonomy row must start and end with |"
restore "$file"

# Case 2d: an escaped pipe belongs to a cell and must not become a separator.
file="docs/e2e-test-smells.md"
backup "$file"
mutate \
  "$file" \
  "during parallel execution." \
  'during parallel \| concurrent execution.'
assert_passes "Check 1c — escaped pipe remains table-cell content"
restore "$file"

# Case 2e: changelog scanner-budget prose must match the measured audit note.
file="CHANGELOG.md"
backup "$file"
mutate "$file" 'with eighteen tokens of headroom' 'with nineteen tokens of headroom'
assert_fails \
  "Check 1d — changelog scanner headroom matches rule self-audit" \
  "scanner headroom must match docs/rule-self-audit.md"
restore "$file"

# Case 2f: the roadmap summary must count only rows in the false-green Merged
# table. Reviewer-informed maintenance is deliberately tracked separately.
file="docs/roadmap.md"
backup "$file"
mutate "$file" "**Merged:** 15 upstream PRs" "**Merged:** 16 upstream PRs"
assert_fails \
  "Check 1e — roadmap merged summary matches table rows" \
  "Merged summary count 16 does not match 15 table rows"
restore "$file"

# Case 2g: an open maintenance cleanup must not inflate the false-green
# campaign's In-review count.
file="docs/roadmap.md"
backup "$file"
mutate "$file" "**In review:** 6 active/open upstream PRs" "**In review:** 7 active/open upstream PRs"
assert_fails \
  "Check 1e — roadmap maintenance stays outside in-review count" \
  "In review summary count 7 does not match 6 table rows"
restore "$file"

# Case 2h: the canonical README merged-fixes table must name the same merged PRs as
# the roadmap, not merely carry the same row count.
file="README.md"
backup "$file"
mutate \
  "$file" \
  "https://github.com/storybookjs/storybook/pull/34141" \
  "https://github.com/storybookjs/storybook/pull/34142"
assert_fails \
  "Check 1e — README merged PR URLs match roadmap" \
  "README.md: merged PR URL set differs from docs/roadmap.md"
restore "$file"

# Case 2i: the badge is a public count claim and must follow the roadmap table.
file="README.md"
backup "$file"
mutate "$file" "merged_PRs-15-" "merged_PRs-16-"
assert_fails \
  "Check 1e — README merged badge matches roadmap" \
  "README.md merged badge 16 does not match roadmap 15"
restore "$file"

# Case 2j: the benchmark status repeats the merged-fix count and must not drift.
file="benchmarks/STATUS.md"
backup "$file"
mutate \
  "$file" \
  "Findings have contributed to **15 merged upstream PRs**" \
  "Findings have contributed to **16 merged upstream PRs**"
assert_fails \
  "Check 1e — benchmark status merged count matches roadmap" \
  "benchmarks/STATUS.md merged count 16 does not match roadmap 15"
restore "$file"

# Case 2k: even a coordinated 6 -> 7 count change cannot classify the ToolJet
# maintenance cleanup as a false-green test fix.
file="docs/roadmap.md"
backup "$file"
python3 - "$file" <<'PY_MOVE_TOOLJET'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
row = next(line for line in lines if "ToolJet/ToolJet#17492" in line)
lines.remove(row)
in_review = lines.index("## In review")
end = next(
    index
    for index in range(in_review + 1, len(lines))
    if lines[index].startswith("## ")
)
lines.insert(end - 1, row)
text = "\n".join(lines) + "\n"
text = text.replace(
    "**In review:** 6 active/open upstream PRs",
    "**In review:** 7 active/open upstream PRs",
    1,
)
path.write_text(text, encoding="utf-8")
PY_MOVE_TOOLJET
assert_fails \
  "Check 1e — ToolJet maintenance cannot enter false-green counts" \
  "ToolJet #17492 must remain Reviewer-informed maintenance"
restore "$file"

# Case 2l: the in-review summary counts distinct PRs, not merely table rows.
# The two PRs this case originally used have since closed without merging and
# moved out of the In review table, so it now uses two rows that are still open.
file="docs/roadmap.md"
backup "$file"
mutate \
  "$file" \
  "https://github.com/hcengineering/platform/pull/10922" \
  "https://github.com/TanStack/router/pull/7616"
assert_fails \
  "Check 1e — in-review rows require distinct PR URLs" \
  "In review table must contain one distinct PR URL per row"
restore "$file"

# Case 2l-2: a PR that closed without merging must not also be claimed as
# merged. Without this check the Closed section becomes a place to park a
# contribution while still counting it in the headline merged number.
file="docs/roadmap.md"
backup "$file"
mutate \
  "$file" \
  "| module-federation/core | ★2.6k |" \
  "| Supabase | ★104.8k | [supabase/supabase#47053](https://github.com/supabase/supabase/pull/47053) | Double-counted | Double-counted. |
| module-federation/core | ★2.6k |"
assert_fails \
  "Check 1e — a closed PR cannot also be counted as merged" \
  "Merged and Closed without merge share PR URLs"
restore "$file"

# Case 2l-3: the closed summary is a public count and must follow its table.
file="docs/roadmap.md"
backup "$file"
mutate \
  "$file" \
  "- **Closed without merge:** 5." \
  "- **Closed without merge:** 6."
assert_fails \
  "Check 1e — closed summary count must match its table rows" \
  "Closed without merge summary count 6 does not match 5 table rows"
restore "$file"

# Case 2m: translated badges repeat the public merged count and must remain
# bound to the roadmap just like the canonical README badge.
file="README.ko.md"
backup "$file"
mutate "$file" "merged_PRs-15-" "merged_PRs-16-"
assert_fails \
  "Check 1e — localized merged badge matches roadmap" \
  "README.ko.md merged badge 16 does not match roadmap 15"
restore "$file"

# Case 2n: translated visible prose must not drift while its badge stays
# correct. Both localized merged-fix claims are part of the public count surface.
file="README.ko.md"
backup "$file"
mutate "$file" "PR 15건이" "PR 16건이"
assert_fails \
  "Check 1e — localized merged prose matches roadmap" \
  "README.ko.md merged prose counts"
restore "$file"

# Case 2o: a second summary must not be hidden by selecting only the first
# matching line, even when that first line still agrees with the table.
file="docs/roadmap.md"
backup "$file"
mutate \
  "$file" \
  "- **Merged:** 15 upstream PRs accepted in real projects." \
  $'- **Merged:** 15 upstream PRs accepted in real projects.\n- **Merged:** 16 upstream PRs accepted in real projects.'
assert_fails \
  "Check 1e — roadmap summary must be unique" \
  "expected exactly one Merged summary count, found 2"
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

# Case 6: the canonical reviewer taxonomy must agree with SKILL.md even
# after manifest descriptions stop storing the full 24-pattern phrase list.
file="scripts/ci/lib/reviewer_taxonomy_contract.py"
backup "$file"
mutate "$file" '"Name-Assertion"' '"Renamed-Assertion"'
assert_fails \
  "Check 5 — reviewer taxonomy title drift" \
  "reviewer taxonomy contract #1 title 'Renamed-Assertion' does not match Quick Reference 'Name-Assertion'"
restore "$file"

# Case 6b: the Quick Reference is a stable numerical lookup surface, so row
# movement must fail even when every ID, title, and severity remains present.
file="skills/e2e-reviewer/SKILL.md"
backup "$file"
python3 - "$file" <<'PY_QR_ORDER'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
heading = lines.index("## Quick Reference")
first = next(
    i
    for i, line in enumerate(lines[heading:], heading)
    if line.startswith("| 1 | Name-Assertion |")
)
second = next(
    i
    for i, line in enumerate(lines[heading:], heading)
    if line.startswith("| 2 | Missing Then |")
)
lines[first], lines[second] = lines[second], lines[first]
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY_QR_ORDER
assert_fails \
  "Check 5 — Quick Reference row order drift" \
  "Quick Reference rows must list numeric IDs in order followed by suffixed IDs"
restore "$file"

# Case 7: docs orphan — add a publishable docs file with no incoming reference.
# Mutating README.md would also trip the canonical translation acknowledgement,
# while selecting an existing doc becomes brittle when CI starts referencing it.
ORPHAN_BAD_FILE="docs/parity-orphan.md"
printf '%s\n' '# Deliberately orphaned parity fixture' > "$ORPHAN_BAD_FILE"
assert_fails "Check 7 — docs orphan detection" "$ORPHAN_BAD_FILE: orphan"
rm -f "$ORPHAN_BAD_FILE"
unset ORPHAN_BAD_FILE

# Case 8: manifest version drift — bump .codex-plugin/plugin.json out of sync with the others
file=".codex-plugin/plugin.json"
backup "$file"
mutate "$file" "\"version\": \"$PLUGIN_VERSION\"" "\"version\": \"9.9.9\""
assert_fails "Check 6 — manifest version drift" "manifest version mismatch"
restore "$file"

# Case 10: Codex plugin interface prompt limit — Codex displays at most 3 prompts
file=".codex-plugin/plugin.json"
backup "$file"
mutate "$file" "\"Diagnose failed Playwright/Cypress tests with root-cause classification.\"" "\"Diagnose failed Playwright/Cypress tests with root-cause classification.\", \"Extra prompt that should fail\""
assert_fails "Codex plugin guard — too many default prompts" "interface.defaultPrompt must contain 1-3 prompts"
restore "$file"

# Case 10b: Codex plugin package descriptions are capped at 1,024 characters.
file=".codex-plugin/plugin.json"
backup "$file"
python3 - "$file" <<'PY_CODEX_DESCRIPTION'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
manifest = json.loads(path.read_text(encoding="utf-8"))
manifest["description"] = "x" * 1025
path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY_CODEX_DESCRIPTION
assert_fails \
  "Codex plugin guard — package description length" \
  ".codex-plugin/plugin.json: description must be 1-1024 characters"
restore "$file"

# Case 10c: directory submissions cap the short listing subtitle at 30 chars.
file=".codex-plugin/plugin.json"
backup "$file"
python3 - "$file" <<'PY_CODEX_SHORT_DESCRIPTION'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
manifest = json.loads(path.read_text(encoding="utf-8"))
manifest["interface"]["shortDescription"] = (
    "A directory subtitle longer than thirty characters"
)
path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY_CODEX_SHORT_DESCRIPTION
assert_fails \
  "Codex plugin guard — directory short description length" \
  ".codex-plugin/plugin.json: interface.shortDescription must be 1-30 characters for directory submission"
restore "$file"

# Case 10d: directory categories use the fixed public taxonomy.
file=".codex-plugin/plugin.json"
backup "$file"
python3 - "$file" <<'PY_CODEX_CATEGORY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
manifest = json.loads(path.read_text(encoding="utf-8"))
manifest["interface"]["category"] = "Testing"
path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY_CODEX_CATEGORY
assert_fails \
  "Codex plugin guard — unsupported directory category" \
  ".codex-plugin/plugin.json: interface.category must be one of"
restore "$file"

# Case 11: SKILL.md frontmatter description unquoted with colon-space — YAML parse regression of v0.7.3
file="skills/e2e-reviewer/SKILL.md"
backup "$file"
# Inject the whole bad shape instead of anchoring on the real description's wording. The
# previous anchor ("description: 'Static review") hard-coded the opening words, so the 1.9.0
# description rewrite silently broke this case; anchoring on the opening quote alone is not
# enough either, because the guard only fires when the unquoted value also contains ": ",
# which the current text no longer has. Replacing the line outright keeps the case testing
# the guard (unquoted plain scalar + colon-space) rather than the prose that happens to be there.
mutate "$file" "description: '" "description: Static review: unquoted with colon-space '"
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

# Case 13b: OpenAI YAML must be structurally parsed. A duplicate key with the
# same value defeats token/regex checks but is invalid under the supported
# fail-closed manifest subset. The duplicate now sits inside `interface`,
# because the schema no longer has top-level scalars.
file="skills/e2e-reviewer/agents/openai.yaml"
backup "$file"
mutate \
  "$file" \
  "  short_description: Audit E2E tests and diffs" \
  $'  short_description: Audit E2E tests and diffs\n  short_description: duplicate'
assert_fails "OpenAI YAML parser — duplicate interface key rejected" "invalid OpenAI agent YAML"
assert_security_fails "Pre-push OpenAI YAML parser — duplicate interface key rejected" "invalid OpenAI agent YAML"
restore "$file"

# Case 13b-2: the runtime drops an unknown key silently, so an invented field
# must fail here or it ships inert the way `name`/`description` once did.
backup "$file"
mutate \
  "$file" \
  "policy:" \
  $'description: an invented top-level key\npolicy:'
assert_fails "OpenAI YAML parser — unknown top-level key rejected" "invalid OpenAI agent YAML"
assert_security_fails "Pre-push OpenAI YAML parser — unknown top-level key rejected" "invalid OpenAI agent YAML"
restore "$file"

# Case 13b-3: `interface` carries the only required values; losing it strips the
# skill's display name in the Codex UI without any runtime error.
backup "$file"
mutate "$file" "interface:" "dependencies:"
assert_fails "OpenAI YAML parser — missing interface rejected" "invalid OpenAI agent YAML"
assert_security_fails "Pre-push OpenAI YAML parser — missing interface rejected" "invalid OpenAI agent YAML"
restore "$file"

# Case 13b-4: policy.allow_implicit_invocation is the one field whose value
# changes behavior, so a non-boolean must not pass as truthy.
backup "$file"
mutate "$file" "  allow_implicit_invocation: true" "  allow_implicit_invocation: yes"
assert_fails "OpenAI YAML parser — non-boolean policy value rejected" "invalid OpenAI agent YAML"
assert_security_fails "Pre-push OpenAI YAML parser — non-boolean policy value rejected" "invalid OpenAI agent YAML"
restore "$file"

# Case 13b-5: the schema has no `name`, so the directory binding rides on the
# documented $<skill> invocation instead.
backup "$file"
mutate "$file" "Use \$e2e-reviewer to review" "Use the reviewer to review"
assert_fails "OpenAI YAML default_prompt — skill invocation required" "must invoke \$e2e-reviewer"
assert_security_fails "Pre-push OpenAI YAML default_prompt — skill invocation required" "must invoke \$e2e-reviewer"
restore "$file"

# Case 13b-6: trigger fixtures must remain balanced, unique, typed, exact,
# and realistic enough to exercise the skill-creator trigger workflow.
TRIGGER_FIXTURE_FILE="skills/e2e-reviewer/evals/trigger-evals.json"
TRIGGER_FIXTURE_CREATED=0
if [ -f "$TRIGGER_FIXTURE_FILE" ]; then
  backup "$TRIGGER_FIXTURE_FILE"
else
  TRIGGER_FIXTURE_CREATED=1
fi

reset_trigger_fixture() {
  if [ "$TRIGGER_FIXTURE_CREATED" = "0" ]; then
    cp "$TRIGGER_FIXTURE_FILE.parity-backup" "$TRIGGER_FIXTURE_FILE"
    return
  fi
  python3 - "$TRIGGER_FIXTURE_FILE" <<'PY_TRIGGER_BASE'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
cases = []
for label in (True, False):
    kind = "positive" if label else "negative"
    for index in range(1, 9):
        cases.append(
            {
                "id": f"synthetic-{kind}-{index}",
                "query": f"Synthetic {kind} trigger query number {index}",
                "should_trigger": label,
            }
        )
path.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
PY_TRIGGER_BASE
}

mutate_trigger_fixture() {
  python3 - "$TRIGGER_FIXTURE_FILE" "$1" <<'PY_TRIGGER_MUTATION'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
mutation = sys.argv[2]

if mutation == "duplicate-key":
    text = path.read_text(encoding="utf-8")
    needle = '"should_trigger": true'
    replacement = '"should_trigger": true,\n    "should_trigger": false'
    if needle not in text:
        raise SystemExit("trigger fixture has no positive case to duplicate")
    path.write_text(text.replace(needle, replacement, 1), encoding="utf-8")
    raise SystemExit(0)

cases = json.loads(path.read_text(encoding="utf-8"))

if mutation == "fewer-true":
    index = next(i for i, case in enumerate(cases) if case["should_trigger"] is True)
    cases.pop(index)
elif mutation == "fewer-false":
    index = next(i for i, case in enumerate(cases) if case["should_trigger"] is False)
    cases.pop(index)
elif mutation == "duplicate-id":
    cases[1]["id"] = cases[0]["id"]
elif mutation == "non-boolean":
    cases[0]["should_trigger"] = "true"
elif mutation == "unexpected-key":
    cases[0]["notes"] = "not part of the skill-creator trigger schema"
elif mutation == "one-word-query":
    cases[0]["query"] = "Review"
else:
    raise SystemExit(f"unknown trigger fixture mutation: {mutation}")

path.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")
PY_TRIGGER_MUTATION
}

reset_trigger_fixture
mutate_trigger_fixture "fewer-true"
assert_fails \
  "Trigger fixtures — at least eight positive cases required" \
  "must contain at least 8 should_trigger=true cases"

reset_trigger_fixture
mutate_trigger_fixture "fewer-false"
assert_fails \
  "Trigger fixtures — at least eight negative cases required" \
  "must contain at least 8 should_trigger=false cases"

reset_trigger_fixture
mutate_trigger_fixture "duplicate-id"
assert_fails \
  "Trigger fixtures — duplicate IDs rejected" \
  "duplicate trigger fixture id"

reset_trigger_fixture
mutate_trigger_fixture "duplicate-key"
assert_fails \
  "Trigger fixtures — duplicate JSON object keys rejected" \
  "duplicate JSON object key"

reset_trigger_fixture
mutate_trigger_fixture "non-boolean"
assert_fails \
  "Trigger fixtures — should_trigger must be boolean" \
  "should_trigger must be a boolean"

reset_trigger_fixture
mutate_trigger_fixture "unexpected-key"
assert_fails \
  "Trigger fixtures — unexpected entry keys rejected" \
  "entry keys must be exactly ['id', 'query', 'should_trigger']"

reset_trigger_fixture
mutate_trigger_fixture "one-word-query"
assert_fails \
  "Trigger fixtures — one-word queries rejected" \
  "query must contain at least 2 words"

if [ "$TRIGGER_FIXTURE_CREATED" = "0" ]; then
  restore "$TRIGGER_FIXTURE_FILE"
else
  rm -f "$TRIGGER_FIXTURE_FILE"
fi
TRIGGER_FIXTURE_CREATED=0

# Case 13c: machine-specific absolute home paths must fail anywhere in the
# shipped text/code artifact set; placeholders like /Users/example remain ok.
file="README.md"
backup "$file"
bad_home="/""Users/machine-owner/e2e-skills"
mutate \
  "$file" \
  "four focused workflows for Playwright and Cypress E2E work" \
  "four focused workflows for Playwright and Cypress E2E work from $bad_home"
assert_security_fails \
  "Pre-push hardcoded-home guard — public docs reject real user paths" \
  "machine-specific absolute user-home paths found in public artifacts"
restore "$file"

# Case 14: Language guard — Hangul on a non-switcher README.md line must still fail.
# The switcher exemption only covers lines linking to README.<lang>.md translations.
file="README.md"
backup "$file"
mutate \
  "$file" \
  "four focused workflows for Playwright and Cypress E2E work" \
  "four focused workflows for Playwright and Cypress E2E 한국어 work"
assert_fails "Language guard — Hangul outside switcher line in README.md" "Korean text found in public docs: README.md"
restore "$file"

# A checker exception must fail closed. This guards against command
# substitutions that append `|| true` and accidentally convert crashes or read
# failures into an empty, successful result.
file="scripts/ci/review.sh"
backup "$file"
mutate \
  "$file" \
  "hangul = re.compile(r'[\\uAC00-\\uD7AF]')" \
  $'raise RuntimeError(\"language checker sentinel crash\")\nhangul = re.compile(r\\'[\\\\uAC00-\\\\uD7AF]\\')'
assert_fails \
  "Language guard — checker crash fails closed" \
  "Language checker failed closed"
restore "$file"

LANGUAGE_BAD_FILE="docs/.language-read-failure.md"
printf '\377' >"$LANGUAGE_BAD_FILE"
assert_fails \
  "Language guard — UTF-8 read failure fails closed" \
  "Language checker failed closed"
rm -f "$LANGUAGE_BAD_FILE"
unset LANGUAGE_BAD_FILE

# Case 15: README i18n structural parity — a translation losing a section must fail.
file="README.ko.md"
backup "$file"
mutate "$file" "## 설치" "###설치-변조"
assert_fails "README i18n parity — section drift in README.ko.md" "README i18n parity: README.ko.md has"
restore "$file"

# The four shortened scanner transcripts preserve the same actionable fixture lines.
file="README.ko.md"
backup "$file"
mutate \
  "$file" \
  "Summary: 2 total hit(s), 2 P0" \
  "Summary: 2 total hit(s), 1 P0"
assert_fails \
  "README i18n parity — scanner transcript stays reproducible" \
  "README.ko.md scanner transcript must preserve the current P0 finding and summary output"
restore "$file"

file="README.ja.md"
backup "$file"
mutate \
  "$file" \
  ".../tests/login.spec.ts:6:  expect(page.locator('.user-badge')).not.toBeNull();" \
  ".../tests/login.spec.ts:7:  expect(page.locator('.user-badge')).not.toBeNull();"
assert_fails \
  "README i18n parity — localized scanner transcript matches canonical bytes" \
  "README.ja.md scanner transcript differs from README.md"
restore "$file"

# The bundled scripts are POSIX-oriented; native Windows support must not be
# implied when the documented execution boundary is WSL.
file="README.md"
backup "$file"
mutate \
  "$file" \
  "Windows users should run them through WSL" \
  "Windows users should run them through a compatible shell"
assert_fails \
  "README i18n parity — Windows limitation keeps the WSL boundary" \
  "README.md Scope and limits section missing platform-limit tokens ['WSL execution/filesystem boundary']"
restore "$file"

# Case 15a: every README accepts the centered display title while repository,
# package, and install identifiers remain the lowercase e2e-skills slug.
centered_title='<h1 align="center">E2E Skills</h1>'
centered_title_files=(README.md README.ko.md README.ja.md README.zh-cn.md)
for file in "${centered_title_files[@]}"; do
  backup "$file"
  if grep -qxF '# e2e-skills' "$file"; then
    mutate "$file" $'# e2e-skills\n' "$centered_title"$'\n'
  fi
done
assert_passes "README i18n parity — centered display title is accepted"
for file in "${centered_title_files[@]}"; do
  restore "$file"
done

# The display title must remain centered.
file="README.md"
backup "$file"
mutate "$file" \
  '<h1 align="center">E2E Skills</h1>' \
  '<h1 align="left">E2E Skills</h1>'
assert_fails \
  "README i18n parity — canonical display title stays centered" \
  "README i18n parity: README.md title must be exactly '<h1 align=\"center\">E2E Skills</h1>'"
restore "$file"

# A reviewer-specific subtitle would narrow the four-skill bundle again.
file="README.ko.md"
backup "$file"
mutate "$file" \
  '<h1 align="center">E2E Skills</h1>' \
  '<h1 align="center">E2E Skills: 리뷰 전용 부제</h1>'
assert_fails \
  "README i18n parity — localized title stays product-only" \
  "README i18n parity: README.ko.md title must be exactly '<h1 align=\"center\">E2E Skills</h1>'"
restore "$file"

# Case 15b: verified merged fixes are a top-level trust signal and must remain
# before the first reviewer-specific false-green walkthrough in every language.
file="README.md"
backup "$file"
python3 - "$file" <<'PY_MOVE_MERGED_FIXES'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
match = re.search(
    r'^<a id="merged-upstream-fixes"></a>\n\n'
    r'## Merged upstream fixes\n.*?(?=^## )',
    text,
    re.M | re.S,
)
if match is None:
    raise SystemExit("merged-fixes section not found")
block = match.group(0)
text = text[:match.start()] + text[match.end():]
marker = "## E2E review catalog\n"
if marker not in text:
    raise SystemExit("review catalog marker not found")
path.write_text(text.replace(marker, block + marker, 1), encoding="utf-8")
PY_MOVE_MERGED_FIXES
assert_fails \
  "README i18n parity — merged fixes stay above first reviewer example" \
  "README i18n parity: README.md Merged upstream fixes must appear before See a false-green test"
restore "$file"

file="README.ko.md"
backup "$file"
python3 - "$file" <<'PY_MOVE_MERGED_FIXES_KO'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
match = re.search(
    r'^<a id="merged-upstream-fixes"></a>\n\n'
    r'## upstream에 merge된 수정 사례\n.*?(?=^## )',
    text,
    re.M | re.S,
)
if match is None:
    raise SystemExit("localized merged-fixes section not found")
block = match.group(0)
text = text[:match.start()] + text[match.end():]
marker = "## E2E 리뷰 목록\n"
if marker not in text:
    raise SystemExit("localized review catalog marker not found")
path.write_text(text.replace(marker, block + marker, 1), encoding="utf-8")
PY_MOVE_MERGED_FIXES_KO
assert_fails \
  "README i18n parity — localized merged fixes stay above first reviewer example" \
  "README i18n parity: README.ko.md upstream에 merge된 수정 사례 must appear before false-green 테스트 살펴보기"
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

# Case 21: subagent parity SP5 — the optional Codex-native TOML port is a third
# copy of the frozen contract; a new F16+ code in it must fail just like the .md.
# (Skips cleanly when the port is absent; guards it only when shipped.)
file=".codex/agents/e2e-failure-classifier.toml"
if [ -f "$file" ]; then
  backup "$file"
  mutate "$file" "F1-F15 root-cause taxonomy" "F1-F17 root-cause taxonomy"
  assert_fails "Subagent parity SP5 — Codex TOML port new F16+ code caught" "found a new F16+ code"
  restore "$file"
else
  echo "  [SKIP] Case 21 — .codex/agents/e2e-failure-classifier.toml not present"
fi

# Case 21b: subagent parity SP3b — F1-vs-F7 is decided by an isolation probe the
# read-only classifier can never run, so the no-probe verdict term has to exist on
# every path that can return one. Drop it from a path and the delegated classifier
# silently guesses F1 from the error text instead.
file="agents/e2e-failure-classifier.md"
backup "$file"
mutate "$file" "CANNOT_VERIFY" "CANNOTVERIFY"
assert_fails "Subagent parity SP3b — classifier missing CANNOT_VERIFY caught" "in both the procedure and"
restore "$file"

# The debugger leg has to fail on the rule, not the token: both skills use
# CANNOT_VERIFY elsewhere, so a token-only check would stay green here.
file="skills/playwright-debugger/SKILL.md"
backup "$file"
mutate "$file" "between F1 and F7" "between F1 and F2"
assert_fails "Subagent parity SP3b — debugger losing the F1/F7 rule caught" "CANNOT_VERIFY rule for F1 versus F7"
restore "$file"

file=".codex/agents/e2e-failure-classifier.toml"
if [ -f "$file" ]; then
  backup "$file"
  mutate "$file" "CANNOT_VERIFY" "CANNOTVERIFY"
  assert_fails "Subagent parity SP3b — Codex TOML port missing CANNOT_VERIFY caught" "in both the procedure and"
  restore "$file"
else
  echo "  [SKIP] Case 21b — .codex/agents/e2e-failure-classifier.toml not present"
fi

# Case 22: independently installable V-rule copies must not drift. Mutate the
# actionable behavior while leaving marker comments untouched; marker-only
# parity would miss every one of these regressions.
file="skills/e2e-reviewer/references/verification-rules.md"
v_rule_anchors=(
  "One primary observable outcome"
  "Safely invert the primary assertion"
  "Corrupt an evidenced dependency"
  "Prove write method/endpoint/payload/cardinality and failed-write behavior"
  "Pass bounded solo, repeat, suite-context, and supported parallel checks"
  "A writer/debugger cannot approve its own output"
)
v_rule_mutations=(
  "One implementation detail"
  "Leave the primary assertion unchanged"
  "Observe a dependency"
  "Prove visible confirmation"
  "Pass one normal run"
  "A writer/debugger may approve its own output"
)
for index in "${!v_rule_anchors[@]}"; do
  rule_id="V$((index + 1))"
  backup "$file"
  mutate "$file" "${v_rule_anchors[$index]}" "${v_rule_mutations[$index]}"
  assert_verification_parity_fails \
    "Verification parity — reviewer $rule_id behavior drift" \
    "reviewer $rule_id behavior differs"
  restore "$file"
done

file="skills/e2e-reviewer/references/verification-rules.md"
backup "$file"
mutate "$file" "after a failed write, assert absence only after a reload or re-fetch" "after a failed write, assert absence"
assert_verification_parity_fails \
  "Verification parity — reviewer V4 failed-write re-read drift" \
  "reviewer V4 behavior differs"
restore "$file"

file="skills/e2e-reviewer/references/verification-rules.md"
backup "$file"
mutate "$file" '`sourceUnchanged`' '`sourceMayChange`'
assert_verification_parity_fails "Verification parity — reviewer result schema drift" "result schemas differ or are missing"
restore "$file"

# Case 23: named custom agents are optional; standard Codex native roles must
# remain the delegation bridge before the inline fallback.
file="skills/e2e-reviewer/SKILL.md"
backup "$file"
mutate "$file" 'native `verifier` role' 'native review role'
assert_fails "Subagent parity SP6 — reviewer drops standard native verifier fallback" "must fall back from the named agent"
restore "$file"

file="skills/playwright-debugger/SKILL.md"
backup "$file"
mutate "$file" 'native `debugger` role' 'native diagnosis role'
assert_fails "Subagent parity SP6 — Playwright debugger drops standard native fallback" "must fall back from the named classifier"
restore "$file"

file="skills/cypress-debugger/SKILL.md"
backup "$file"
mutate "$file" 'native `debugger` role' 'native diagnosis role'
assert_fails "Subagent parity SP6 — Cypress debugger drops standard native fallback" "must fall back from the named classifier"
restore "$file"

# Case 24: every framework rejected by the contributor scope contract must be
# detected independently. Mutate the same positive README support sentence for
# each name so a missing alternation cannot hide behind another framework hit.
for framework in Puppeteer Selenium WebdriverIO TestCafe Nightwatch; do
  file="README.md"
  backup "$file"
  mutate \
    "$file" \
    "Playwright and Cypress E2E work" \
    "Playwright, Cypress, and $framework E2E work"
  assert_fails \
    "Framework scope — $framework support claim rejected" \
    "unsupported framework reference: $framework"
  restore "$file"
done

# A negative framework sentence must not exempt a positive sentence elsewhere
# in the same paragraph.
file="AGENTS.md"
backup "$file"
mutate \
  "$file" \
  "or Nightwatch. See \`docs/framework-scope.md\`" \
  "or Nightwatch. Puppeteer is fully supported. See \`docs/framework-scope.md\`"
assert_fails \
  "Framework scope — paragraph-level negative wording cannot launder support" \
  "unsupported framework reference: Puppeteer"
restore "$file"

# The attributed evidence document may discuss out-of-scope frameworks, but it
# must not become a blanket escape hatch for an e2e-skills capability claim.
file="docs/llm-generated-e2e-test-evidence.md"
backup "$file"
mutate \
  "$file" \
  "The implementation is Selenium-based; feature coverage is not semantic fault detection." \
  "The implementation is Selenium-based; feature coverage is not semantic fault detection. e2e-skills fully supports Selenium test generation."
assert_fails \
  "Framework scope — evidence document cannot claim e2e-skills Selenium support" \
  "unsupported framework reference: Selenium"
restore "$file"

# Translation parity protects the exact canonical installation commands and
# repository URLs in every language, not just section/fence counts.
for file in README.ko.md README.ja.md README.zh-cn.md; do
  backup "$file"
  mutate \
    "$file" \
    "npx --yes skills@1.5.21 add voidmatcha/e2e-skills -g --all" \
    "npx --yes skills@1.5.21 add voidmatcha/e2e-skillz -g --all"
  assert_fails \
    "README i18n parity — $file install command drift" \
    "$file canonical install commands differ from README.md"
  restore "$file"

  backup "$file"
  mutate \
    "$file" \
    "https://github.com/voidmatcha/e2e-skills.git" \
    "https://github.com/voidmatcha/e2e-skillz.git"
  assert_fails \
    "README i18n parity — $file repository URL drift" \
    "$file canonical repository URLs differ from README.md"
  restore "$file"
done

# A manual Claude Code source install must expose each skill directly under
# ~/.claude/skills; Claude Code does not document recursive personal-skill
# discovery through a bundle directory.
file="README.md"
backup "$file"
mutate \
  "$file" \
  'git clone https://github.com/voidmatcha/e2e-skills.git "$HOME/.claude/e2e-skills"' \
  'git clone https://github.com/voidmatcha/e2e-skills.git ~/.claude/skills/e2e-skills'
assert_fails \
  "README manual clone — nested bundle path rejected" \
  "README.md manual Claude Code clone must expose four direct per-skill roots"
restore "$file"

# Codex installation is host-specific, and generator V6 needs independent
# context rather than the equivalent inline-fallback contract used elsewhere.
file="README.md"
backup "$file"
mutate \
  "$file" \
  "--skill '*' -g -a codex" \
  "--skill '*' -g -a claude-code -a codex"
assert_fails \
  "README Codex install — host-specific command rejects hidden Claude install" \
  "README.md Codex install must target only -a codex"
restore "$file"

file="README.md"
backup "$file"
mutate "$file" '`CANNOT_VERIFY` and' '`UNVERIFIED` and'
assert_fails \
  "README Codex delegation — generator independent-context limit is required" \
  "README.md Codex delegation limits missing tokens"
restore "$file"

# The translated taxonomy tables must retain the canonical pattern IDs,
# severities, and two complete F1-F15 debugger tables.
for file in README.ko.md README.ja.md README.zh-cn.md; do
  backup "$file"
  mutate "$file" "| 12 |" "| 12x |"
  assert_fails \
    "README i18n taxonomy — $file pattern ID drift" \
    "$file pattern ID/severity contract differs from README.md"
  restore "$file"
done

file="README.ko.md"
backup "$file"
mutate "$file" "#### P1:" "#### P0:"
assert_fails \
  "README i18n taxonomy — severity drift" \
  "README.ko.md pattern ID/severity contract differs from README.md"
restore "$file"

file="README.ja.md"
backup "$file"
mutate "$file" "| F15 |" "| F16 |"
assert_fails \
  "README i18n taxonomy — F1-F15 drift" \
  "README.ja.md F1-F15 taxonomy contract differs from README.md"
restore "$file"

# Translation contract snapshots protect a small set of safety and scope claims.
# They do not assess translation quality. Changing the visible protected prose
# requires an explicit review.sh snapshot update.
for file in README.ko.md README.ja.md README.zh-cn.md; do
  backup "$file"
  mutate \
    "$file" \
    "\`--isolation-wrapper\`" \
    "\`--isolation-hook\`"
  assert_fails \
    "README i18n semantic contract — $file isolation claim drift" \
    "$file protected semantic contract"
  restore "$file"
done

file="README.ko.md"
backup "$file"
mutate \
  "$file" \
  "<!-- README-I18N-CONTRACT:CORE-SAFETY:START -->" \
  "<!-- README-I18N-CONTRACT:CORE-SAFETY:REMOVED -->"
assert_fails \
  "README i18n semantic contract — missing protected block fails" \
  "README.ko.md missing or duplicated protected semantic contract"
restore "$file"

# The scanner trust disclosure must preserve the narrow read-scope exception:
# findings stay under the requested path, while provenance resolution may read
# relative fixture/support imports elsewhere in the same containing project.
for file in README.ko.md README.ja.md README.zh-cn.md; do
  backup "$file"
  mutate "$file" "fixture/support" "fixture/helper"
  assert_fails \
    "README i18n scanner read scope — $file provenance exception drift" \
    "$file protected scanner read-scope contract"
  restore "$file"
done

file="README.zh-cn.md"
backup "$file"
mutate \
  "$file" \
  "<!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:START -->" \
  "<!-- README-I18N-CONTRACT:SCANNER-READ-SCOPE:REMOVED -->"
assert_fails \
  "README i18n scanner read scope — missing protected block fails" \
  "README.zh-cn.md missing or duplicated protected scanner read-scope contract"
restore "$file"

# Each translation acknowledges the exact byte revision of canonical README.md.
# This is a review checkpoint, not a translation-quality attestation.
readme_digest=$(env LC_ALL=C LC_CTYPE=C LANG=C python3 - <<'PY'
import hashlib
import pathlib

print(hashlib.sha256(pathlib.Path("README.md").read_bytes()).hexdigest())
PY
)
file="README.ko.md"
backup "$file"
mutate "$file" "$readme_digest" "$(printf '0%.0s' {1..64})"
assert_fails \
  "README i18n canonical revision — translated acknowledgement drift" \
  "README.ko.md canonical revision acknowledgement is stale"
restore "$file"

file="README.md"
backup "$file"
mutate \
  "$file" \
  "False-green detection is one important part of the review workflow" \
  "False-green detection is an important part of the review workflow"
assert_fails \
  "README i18n canonical revision — canonical byte change requires review" \
  "canonical revision acknowledgement is stale"
restore "$file"

# Scanner smoke is invariant across drift shards and uses CPU-heavy concurrent
# checks internally. Run it once on shard zero instead of duplicating it across
# every disposable copy.
if [ "$PARITY_SHARD_INDEX" -ne 0 ]; then
  echo ""
  echo "========================================"
  echo "  Drift smoke: $PASS passed, $FAIL failed"
  echo "========================================"
  [ "$FAIL" -gt 0 ] && exit 1
  exit 0
fi

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
  # Native match, not `printf | grep -q`: `pipefail` plus grep's early exit
  # returns 141 on scanner output larger than the pipe buffer, which reads as
  # "not found" and would make assert_scan_absent pass without checking.
  if [[ "$SCAN_OUT" == *"$expected"* ]]; then
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
  if [[ "$SCAN_OUT" == *"$unexpected"* ]]; then
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

# Case S3: sync-matcher one-shot read is #4c-4e (non-retrying read, P1), never #15
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

# Case S6: local Cypress command-model rules run without eslint/plugin downloads and keep
# ordinary values plus assert-before-action chains out of the raw hit set.
mkdir -p "$SCAN_FIXDIR/s6"
cat > "$SCAN_FIXDIR/s6/commands.cy.ts" <<'EOF'
it('bad command model', async () => {
  const button = cy.get('[data-cy=save]');
  await button.type('Ada').should('have.value', 'Ada');
});

it('safe command model', () => {
  const expected = 'Saved';
  cy.get('[data-cy=save]').should('be.enabled').click();
  cy.get('[role=status]').should('have.text', expected);
});
EOF
run_scan s6 none
assert_scan_contains "Scanner S6 — Cypress async callback flagged as #10d" "#10d"
assert_scan_contains "Scanner S6 — assigned Cypress command flagged as #10e" "#10e"
assert_scan_contains "Scanner S6 — unsafe continued action chain triaged as #10f" "#10f"
assert_scan_absent "Scanner S6 — ordinary expected value is not a second #10e hit" "#10e Cypress return value assigned outside the command chain (2 hits)"

# Case S7: Playwright requires async test callbacks; the Cypress-only #10d rule must
# filter by framework evidence rather than classify every async test callback.
mkdir -p "$SCAN_FIXDIR/s7"
cat > "$SCAN_FIXDIR/s7/normal.spec.ts" <<'EOF'
import { test, expect } from '@playwright/test';

test('normal Playwright callback', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL('/');
});
EOF
run_scan s7 none
assert_scan_absent "Scanner S7 — normal Playwright async callback not flagged as Cypress #10d" "#10d"

# Case S8: Cypress command-model syntax boundaries. Confirm function/hook callback
# variants and typed assignments while excluding native-Promise-only async callbacks.
mkdir -p "$SCAN_FIXDIR/s8"
cat > "$SCAN_FIXDIR/s8/boundaries.cy.ts" <<'EOF'
it('native promise only', async () => {
  await Promise.resolve('ready');
});

it('one-line native promise only', async () => await Promise.resolve('ready'));

it('async function with Cypress queue', async function () {
  await cy.visit('/settings');
});

afterEach(async () => {
  await cy.clearCookies();
});

it('typed Chainable assignment', () => {
  const button: Cypress.Chainable<JQuery<HTMLElement>> = cy.get('[data-cy=save]');
  button.click();
});

it('uses synchronous Cypress Sinon utilities', () => {
  const spy = cy.spy(console, 'log');
  const stub = cy.stub(window, 'open');
  expect(spy).to.exist;
  expect(stub).to.exist;
});
EOF
run_scan s8 none
assert_scan_contains "Scanner S8 — async function callback with cy queue flagged as #10d" "boundaries.cy.ts:7"
assert_scan_contains "Scanner S8 — async afterEach callback with cy queue flagged as #10d" "boundaries.cy.ts:11"
assert_scan_absent "Scanner S8 — native-Promise-only async callback excluded from #10d" "boundaries.cy.ts:1:"
assert_scan_absent "Scanner S8 — one-line native-Promise callback excluded from #10d" "boundaries.cy.ts:5:"
assert_scan_contains "Scanner S8 — typed Cypress Chainable assignment flagged as #10e" "boundaries.cy.ts:16"
assert_scan_absent "Scanner S8 — synchronous cy.spy assignment excluded from #10e" "boundaries.cy.ts:21:"
assert_scan_absent "Scanner S8 — synchronous cy.stub assignment excluded from #10e" "boundaries.cy.ts:22:"

rm -rf "$SCAN_FIXDIR"

echo ""
echo "========================================"
echo "  Drift smoke: $PASS passed, $FAIL failed"
echo "========================================"

[ "$FAIL" -gt 0 ] && exit 1
exit 0
