#!/usr/bin/env bash
# Keep independently installable skill copies of the V1-V6 core contract aligned.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)" || exit 1
GEN="$ROOT/skills/playwright-test-generator/verification-rules.md"
REV="$ROOT/skills/e2e-reviewer/references/verification-rules.md"
PREFIX='<!-- V-RULE-CONTRACT:'
SCHEMA_PREFIX='<!-- V-RESULT-SCHEMA:'

extract_contract() {
  grep -F "$PREFIX" "$1" 2>/dev/null | head -1
}

gen_contract=$(extract_contract "$GEN")
rev_contract=$(extract_contract "$REV")

if [ -z "$gen_contract" ] || [ -z "$rev_contract" ]; then
  echo "verification parity: missing V-RULE-CONTRACT marker" >&2
  exit 1
fi

if [ "$gen_contract" != "$rev_contract" ]; then
  echo "verification parity: generator/reviewer V-rule contracts differ" >&2
  diff -u <(printf '%s\n' "$gen_contract") <(printf '%s\n' "$rev_contract") >&2 || true
  exit 1
fi

gen_schema=$(grep -F "$SCHEMA_PREFIX" "$GEN" 2>/dev/null | head -1)
rev_schema=$(grep -F "$SCHEMA_PREFIX" "$REV" 2>/dev/null | head -1)
if [ -z "$gen_schema" ] || [ -z "$rev_schema" ] || [ "$gen_schema" != "$rev_schema" ]; then
  echo "verification parity: generator/reviewer result schemas differ or are missing" >&2
  exit 1
fi

for id in V1 V2 V3 V4 V5 V6; do
  grep -q "$id" "$GEN" || { echo "verification parity: $id missing from generator" >&2; exit 1; }
  grep -q "$id" "$REV" || { echo "verification parity: $id missing from reviewer" >&2; exit 1; }
done

echo "verification parity: V1-V6 core contract aligned"
