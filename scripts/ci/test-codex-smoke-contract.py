#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate the manual Codex smoke contract without invoking Codex or network."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "scripts/ci/codex-smoke.sh"
CI_LOCAL = ROOT / "scripts/ci/ci-local.sh"
PYTHON_ISOLATION_INIT = ROOT / "scripts/ci/lib/init-python-isolation.sh"
FIXTURE_ROOT = ROOT / "scripts/ci/fixtures/codex-smoke"
MOCHAWESOME = FIXTURE_ROOT / "mochawesome.json"
CYPRESS_READER = (
    ROOT / "skills/cypress-debugger/scripts/read-cypress-artifact.py"
)
GENERATOR = ROOT / "skills/playwright-test-generator/SKILL.md"


def main() -> None:
    smoke = SMOKE.read_text(encoding="utf-8")
    ci_local = CI_LOCAL.read_text(encoding="utf-8")
    python_isolation_init = PYTHON_ISOLATION_INIT.read_text(encoding="utf-8")
    generator = GENERATOR.read_text(encoding="utf-8")

    current_probe_token = "--framed-stdin"
    assert current_probe_token in generator
    assert f'check "test-generator" "{current_probe_token}"' in smoke
    assert '--target "$TARGET_URL"' not in generator
    assert '--approved-origin "$BASE_URL"' not in generator
    assert "| \"$SKILL_ROOT/scripts/run-preflight-target.sh\" --framed-stdin" in generator
    assert 'write_frame="$SKILL_ROOT/scripts/write-utf8-frame.sh"' in generator
    for framed_value in (
        '"$TARGET_URL"',
        '"$BASE_URL"',
        '"${LOGIN_URL-}"',
        '"${ALLOW_LOOPBACK:-0}"',
    ):
        assert f"printf '%s' {framed_value} | \"$write_frame\"" in generator
    assert (
        "printf '%s' \"$TARGET_URL\" |\n"
        '  "$SKILL_ROOT/scripts/write-utf8-frame.sh" |\n'
        '  "$SKILL_ROOT/scripts/run-raw-aria-snapshot.sh" --framed-stdin'
    ) in generator
    assert "four bounded length-prefixed UTF-8 frames on stdin" in smoke
    assert "never raw URL-valued arguments" in smoke
    assert "complete fenced shell command" in smoke
    assert "curl -fsS -o /dev/null -w" not in smoke

    reader_path = (
        "$SKILLS_ROOT/cypress-debugger/scripts/read-cypress-artifact.py"
    )
    assert reader_path in smoke
    assert (
        f"python3 {reader_path} mochawesome "
        "--artifact-root $FIXTURES $FIXTURES/mochawesome.json"
    ) in smoke
    assert "Do not read the raw JSON directly" in smoke

    result = subprocess.run(
        [
            sys.executable,
            str(CYPRESS_READER),
            "mochawesome",
            "--artifact-root",
            str(FIXTURE_ROOT),
            str(MOCHAWESOME),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    failures = payload["failures"]
    assert len(failures) == 1
    failure = failures[0]
    assert failure["state"] == "failed"
    assert "Expected to find element" in failure["error"]
    assert "[data-testid=\"submit-order\"]" in failure["error"]

    assert "run_python scripts/ci/test-codex-smoke-contract.py" in ci_local
    assert 'source "$REPO_ROOT/scripts/ci/lib/init-python-isolation.sh"' in ci_local
    assert (
        'PYTHON_RUNNER="$REPO_ROOT/scripts/ci/lib/run-python-isolated.sh"'
        in python_isolation_init
    )
    assert '"$PYTHON_RUNNER" "$@"' in python_isolation_init
    assert "bash scripts/ci/codex-smoke.sh" not in ci_local
    print(
        "codex smoke contract: pass "
        "(current generator probe, bounded Cypress reader, valid fixture, "
        "no live Codex/network in ordinary CI)"
    )


if __name__ == "__main__":
    main()
