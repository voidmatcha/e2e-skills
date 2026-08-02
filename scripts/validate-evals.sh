#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)"

python3 - "$REPO_ROOT/scripts/ci/lib" <<'PY'
import pathlib
import sys

sys.path.insert(0, sys.argv[1])
from strict_json import load_strict, require_exact_keys

files = sorted(pathlib.Path('.').glob('skills/*/evals/evals.json'))
if not files:
    sys.exit('no eval files found')

total = 0
for path in files:
    data = require_exact_keys(
        load_strict(path),
        {'skill_name', 'evals'},
        context=str(path),
    )
    skill = data['skill_name']
    evals = data['evals']
    if not isinstance(skill, str) or not skill:
        sys.exit(f"{path}: skill_name must be a non-empty string")
    if not isinstance(evals, list):
        sys.exit(f"{path}: evals must be a list")

    ids = set()
    for index, entry in enumerate(evals):
        total += 1
        if not isinstance(entry, dict):
            sys.exit(f"{path}: evals[{index}] must be an object")
        required = {'id', 'prompt', 'expected_output', 'assertions', 'files'}
        allowed = required | {'title'}
        missing = sorted(required - set(entry))
        unknown = sorted(set(entry) - allowed)
        if missing or unknown:
            sys.exit(
                f"{path}: evals[{index}] schema keys differ; "
                f"missing={missing!r}, unknown={unknown!r}"
            )
        eval_id = entry['id']
        if (
            not isinstance(eval_id, int)
            or isinstance(eval_id, bool)
            or eval_id < 1
        ):
            sys.exit(f"{path}: evals[{index}].id must be a positive integer")
        if eval_id in ids:
            sys.exit(f"{path}: duplicate eval id {eval_id!r}")
        ids.add(eval_id)
        for key in ('prompt', 'expected_output'):
            if not isinstance(entry[key], str) or not entry[key]:
                sys.exit(f"{path}: {eval_id}.{key} must be a non-empty string")
        if 'title' in entry and (
            not isinstance(entry['title'], str) or not entry['title']
        ):
            sys.exit(f"{path}: {eval_id}.title must be a non-empty string")
        if (
            not isinstance(entry['assertions'], list)
            or not entry['assertions']
            or any(
                not isinstance(assertion, str) or not assertion
                for assertion in entry['assertions']
            )
        ):
            sys.exit(f"{path}: {entry['id']} assertions must be a non-empty list")
        if not isinstance(entry['files'], list) or any(
            not isinstance(item, str) or not item for item in entry['files']
        ):
            sys.exit(f"{path}: {entry['id']} files must be a list of strings")
        # Reproducibility contract: every referenced fixture must exist in-repo.
        # Assertions cite exact file:line — a missing fixture makes the eval unrunnable
        # from a fresh clone (and nothing else in CI would notice).
        for rel in entry['files']:
            fixture = path.parent.parent / rel
            if not fixture.is_file():
                sys.exit(f"{path}: eval {entry['id']} references missing fixture {rel}")

    print(f"{skill}: {len(evals)} eval(s)")

print(f"total: {total} eval(s)")
PY
