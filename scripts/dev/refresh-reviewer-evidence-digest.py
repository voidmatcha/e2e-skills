#!/usr/bin/env python3
"""Record the current e2e-reviewer skill digest in the v3 evidence status.

Any byte change under skills/e2e-reviewer, including a version bump or a
whitespace-only reflow, changes the digest that
scripts/ci/test-reviewer-evidence-v3.py compares against
benchmarks/reviewer-holdout-v3/evidence-status.json. This writes only the
`current_skill_sha256` field, computed by the same function the check uses,
then runs the check. It does not mark any report fresh: reports evaluated
against an older digest stay stale, which is what the check verifies.

Usage:
  scripts/dev/refresh-reviewer-evidence-digest.py          # update, then verify
  scripts/dev/refresh-reviewer-evidence-digest.py --check  # exit 1 if stale
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "benchmarks/reviewer-holdout-v3/evidence-status.json"
RUNNER = ROOT / "scripts/evals/run-reviewer-holdout.py"
SKILL_DIR = ROOT / "skills/e2e-reviewer"
CHECK = ROOT / "scripts/ci/test-reviewer-evidence-v3.py"


def computed_digest() -> str:
    spec = importlib.util.spec_from_file_location("reviewer_holdout_runner", RUNNER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.skill_digest(SKILL_DIR)


def main() -> int:
    check_only = sys.argv[1:] == ["--check"]
    if sys.argv[1:] not in ([], ["--check"]):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    recorded = status["current_skill_sha256"]
    computed = computed_digest()
    if recorded == computed:
        print(f"reviewer evidence digest: current ({computed})")
        return 0
    if check_only:
        print(
            f"reviewer evidence digest: stale; recorded={recorded}, computed={computed}",
            file=sys.stderr,
        )
        return 1
    status["current_skill_sha256"] = computed
    STATUS.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(f"reviewer evidence digest: {recorded} -> {computed}")
    return subprocess.run([sys.executable, str(CHECK)], cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
