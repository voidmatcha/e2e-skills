#!/usr/bin/env bash
# Drift smoke test for the pattern-and-description parity checks in review.sh.
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
  # digest once around the whole fan-out. Default 6; E2E_PARITY_WORKERS=1 restores the
  # historical single-copy run, and 0 derives the count from the core count. A worker
  # costs more than a core here — it runs review.sh over its own full-tree copy — so a
  # host with fewer than ~6 cores should set this down rather than take the default.
  parity_workers="${E2E_PARITY_WORKERS:-6}"
  case "$parity_workers" in ''|*[!0-9]*) parity_workers=1 ;; esac
  if [ "$parity_workers" -eq 0 ]; then
    parity_workers=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)
    [ "$parity_workers" -gt 6 ] && parity_workers=6
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
  [ -n "${LANGUAGE_BAD_FILE:-}" ] && rm -f "$LANGUAGE_BAD_FILE" || true
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

assert_fails() {
  local name="$1"
  local expected="$2"
  local output
  claim_case || return 0
  output=$(bash scripts/ci/review.sh --quiet 2>&1 || true)
  if grep -qF "$expected" <<<"$output"; then
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

# Case 9b: coordinated drift in all manifests must still fail. The phrase
# source is the checked ID/title contract, not whichever manifest is treated as
# the leader, so changing all three copies together cannot redefine truth.
coordinated_manifests=(
  ".claude-plugin/plugin.json"
  ".claude-plugin/marketplace.json"
  ".codex-plugin/plugin.json"
)
for file in "${coordinated_manifests[@]}"; do
  backup "$file"
  mutate "$file" "name-assertion mismatch" "renamed coordinated pattern"
done
assert_fails \
  "Check 5 — coordinated manifest phrase drift rejected" \
  "missing or out-of-order pattern 'name assertion mismatch'"
for file in "${coordinated_manifests[@]}"; do
  restore "$file"
done

# Case 10: Codex plugin interface prompt limit — Codex displays at most 3 prompts
file=".codex-plugin/plugin.json"
backup "$file"
mutate "$file" "\"Diagnose failed Playwright/Cypress tests with root-cause classification.\"" "\"Diagnose failed Playwright/Cypress tests with root-cause classification.\", \"Extra prompt that should fail\""
assert_fails "Codex plugin guard — too many default prompts" "interface.defaultPrompt must contain 1-3 prompts"
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
# fail-closed manifest subset.
file="skills/e2e-reviewer/agents/openai.yaml"
backup "$file"
mutate \
  "$file" \
  "allow_implicit_invocation: true" \
  $'allow_implicit_invocation: true\nname: e2e-reviewer'
assert_fails "OpenAI YAML parser — duplicate top-level key rejected" "invalid OpenAI agent YAML"
assert_security_fails "Pre-push OpenAI YAML parser — duplicate top-level key rejected" "invalid OpenAI agent YAML"
restore "$file"

# Case 14: Language guard — Hangul on a non-switcher README.md line must still fail.
# The switcher exemption only covers lines linking to README.<lang>.md translations.
file="README.md"
backup "$file"
mutate "$file" "Find Playwright and Cypress E2E tests that pass CI" "Find Playwright and Cypress E2E tests 한국어 that pass CI"
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
    "Find Playwright and Cypress E2E tests that pass CI" \
    "Find Playwright, Cypress, and $framework E2E tests that pass CI"
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
mutate "$file" "#### P1 " "#### P0 "
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
  "Find Playwright and Cypress E2E tests that pass CI but fail to verify user-visible behavior." \
  "Find Playwright and Cypress E2E tests that pass CI but verify too little."
assert_fails \
  "README i18n canonical revision — canonical byte change requires review" \
  "canonical revision acknowledgement is stale"
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
