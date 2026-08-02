#!/usr/bin/env bash
# Keep independently installable skill copies of the V1-V6 behavior aligned.
# Marker comments are informative only: parity is derived from the actionable
# prose/table and the structured-result contract that agents actually read.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)" || exit 1
REPO_ROOT="$ROOT"
source "$REPO_ROOT/scripts/ci/lib/init-python-isolation.sh" || exit 2
GEN="$ROOT/skills/playwright-test-generator/verification-rules.md"
REV="$ROOT/skills/e2e-reviewer/references/verification-rules.md"

if ! command -v python3 >/dev/null 2>&1; then
  echo "verification parity: python3 unavailable; semantic contract check did not run" >&2
  exit 1
fi

python3 - "$GEN" "$REV" <<'PY'
import json
import pathlib
import re
import sys

generator_path = pathlib.Path(sys.argv[1])
reviewer_path = pathlib.Path(sys.argv[2])
try:
    generator = generator_path.read_text(encoding="utf-8")
    reviewer = reviewer_path.read_text(encoding="utf-8")
except (OSError, UnicodeError) as exc:
    print(f"verification parity: cannot read contract files: {exc}", file=sys.stderr)
    raise SystemExit(1)


def generator_rules(text):
    matches = list(re.finditer(r"^## (V[1-6])\s+—[^\n]*\n", text, re.M))
    rules = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        rules[match.group(1)] = text[match.end():end]
    return rules


def reviewer_rules(text):
    rules = {}
    for line in text.splitlines():
        match = re.match(r"^\|\s*(V[1-6])\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|$", line)
        if match:
            rules[match.group(1)] = " ".join(match.groups()[1:])
    return rules


# Each tuple is a canonical semantic clause. Every alternative in a clause is
# accepted, but every clause must be evidenced in both independently shipped
# documents. This normalizes framework-specific wording without trusting a
# duplicated marker token.
canonical = {
    "V1": (
        (r"primary observable outcome", r"observable product outcome"),
        (r"(?:title|name).*(?:action|actions)", r"(?:action|actions).*(?:title|name)"),
        (r"match", r"same behavior"),
    ),
    "V2": (
        (r"invert", r"inverse", r"mutat(?:e|ion).{0,120}contradict"),
        (r"primary (?:assertion|matcher)",),
        (r"temporary (?:copy|spec)",),
        (r"(?:turn|expect) red", r"must .*red"),
    ),
    "V3": (
        (r"corrupt",),
        (r"evidenced (?:dependency|input)", r"(?:dependency|input).{0,160}proves? is load-bearing"),
        (r"unchanged (?:primary )?assertion",),
        (r"(?:turn|must turn) red",),
    ),
    "V4": (
        (r"(?:write )?method",),
        (r"endpoint",),
        (r"payload",),
        (r"cardinality",),
        (r"failed[- ]write", r"failed write"),
    ),
    "V5": (
        (r"\bsolo\b", r"\balone\b"),
        (r"repeat",),
        (r"suite[- ]context", r"suite context"),
        (r"parallel",),
    ),
    "V6": (
        (r"(?:writer|debugger).*(?:cannot|can not|must not).*approve",),
        (
            r"(?:rerun|run it again).*e2e-reviewer",
            r"e2e-reviewer.*after (?:repair|generation)",
            r"e2e-reviewer.{0,120}after .*repair.{0,80}run it again",
        ),
    ),
}


def normalize(label, rules):
    if set(rules) != set(canonical):
        missing = sorted(set(canonical) - set(rules))
        extra = sorted(set(rules) - set(canonical))
        print(
            f"verification parity: {label} V-rule set differs "
            f"(missing={missing}, extra={extra})",
            file=sys.stderr,
        )
        raise SystemExit(1)
    normalized = {}
    for rule_id, clauses in canonical.items():
        body = re.sub(r"\s+", " ", rules[rule_id]).lower()
        values = tuple(
            any(re.search(pattern, body, re.I) for pattern in alternatives)
            for alternatives in clauses
        )
        if not all(values):
            missing = [index + 1 for index, present in enumerate(values) if not present]
            print(
                f"verification parity: {label} {rule_id} behavior differs "
                f"(missing canonical clauses {missing})",
                file=sys.stderr,
            )
            raise SystemExit(1)
        normalized[rule_id] = values
    return normalized


gen_contract = normalize("generator", generator_rules(generator))
rev_contract = normalize("reviewer", reviewer_rules(reviewer))
if gen_contract != rev_contract:
    print("verification parity: generator/reviewer V-rule contracts differ", file=sys.stderr)
    raise SystemExit(1)

schema_fields = {
    "candidate",
    "runner",
    "verification.V1",
    "verification.V2",
    "verification.V3",
    "verification.V4",
    "verification.V5",
    "verification.V6",
    "sourceUnchanged",
    "temporaryArtifactsRemaining",
}


def flatten(value, prefix=""):
    fields = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else key
            fields.add(path)
            fields.update(flatten(child, path))
    return fields


json_blocks = re.findall(r"```json\s*\n(.*?)\n```", generator, re.S | re.I)
if len(json_blocks) != 1:
    print("verification parity: generator result schema is missing or ambiguous", file=sys.stderr)
    raise SystemExit(1)
try:
    gen_fields = flatten(json.loads(json_blocks[0]))
except (json.JSONDecodeError, TypeError) as exc:
    print(f"verification parity: generator result schema is invalid JSON: {exc}", file=sys.stderr)
    raise SystemExit(1)

reviewer_schema_text = reviewer[reviewer.find("When runtime proof is actually requested"):]
reviewer_fields = {
    field
    for field in schema_fields
    if (
        field in reviewer_schema_text
        or (
            field.startswith("verification.V")
            and re.search(r"explicit V1[–-]V6 verdict objects", reviewer_schema_text)
        )
        or (field == "candidate" and "candidate path" in reviewer_schema_text)
        or (field == "runner" and "repository-native runner" in reviewer_schema_text)
    )
}
if not schema_fields.issubset(gen_fields) or reviewer_fields != schema_fields:
    print("verification parity: generator/reviewer result schemas differ or are missing", file=sys.stderr)
    raise SystemExit(1)

print("verification parity: V1-V6 semantic contract aligned")
PY
