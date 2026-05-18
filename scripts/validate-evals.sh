#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
import pathlib
import sys

files = sorted(pathlib.Path('.').glob('skills/*/evals/evals.json'))
if not files:
    sys.exit('no eval files found')

total = 0
for path in files:
    data = json.loads(path.read_text(encoding='utf-8'))
    try:
        skill = data['skill_name']
        evals = data['evals']
    except KeyError as exc:
        sys.exit(f"{path}: missing required key {exc.args[0]!r}")
    if not isinstance(evals, list):
        sys.exit(f"{path}: evals must be a list")

    for entry in evals:
        total += 1
        for key in ('id', 'prompt', 'expected_output', 'assertions'):
            if key not in entry:
                sys.exit(f"{path}: eval {entry!r} missing {key}")
        if not isinstance(entry['assertions'], list) or not entry['assertions']:
            sys.exit(f"{path}: {entry['id']} assertions must be a non-empty list")

    print(f"{skill}: {len(evals)} eval(s)")

print(f"total: {total} eval(s)")
PY
