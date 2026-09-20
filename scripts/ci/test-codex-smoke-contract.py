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
PLAYWRIGHT_LAUNCHER = (
    ROOT / "skills/playwright-debugger/scripts/run-artifact-reader.sh"
)
PLAYWRIGHT_FIXTURE_ROOT = ROOT / "skills/playwright-debugger/evals/files"
PLAYWRIGHT_FIXTURE = PLAYWRIGHT_FIXTURE_ROOT / "results-selector-timeout.json"
CYPRESS_READER = (
    ROOT / "skills/cypress-debugger/scripts/read-cypress-artifact.py"
)
GENERATOR = ROOT / "skills/playwright-test-generator/SKILL.md"
GENERATOR_PREFLIGHT = (
    ROOT / "skills/playwright-test-generator/exploration-preflight.md"
)


def main() -> None:
    smoke = SMOKE.read_text(encoding="utf-8")
    ci_local = CI_LOCAL.read_text(encoding="utf-8")
    python_isolation_init = PYTHON_ISOLATION_INIT.read_text(encoding="utf-8")
    generator = GENERATOR.read_text(encoding="utf-8")
    generator_preflight = GENERATOR_PREFLIGHT.read_text(encoding="utf-8")

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
    ) in generator_preflight
    assert '--target "$TARGET_URL"' not in generator_preflight
    assert "four bounded length-prefixed UTF-8 frames on stdin" in smoke
    assert "never raw URL-valued arguments" in smoke
    assert "complete fenced shell command" in smoke
    assert "curl -fsS -o /dev/null -w" not in smoke
    assert "CODEX_ISOLATION=(--ephemeral --ignore-user-config)" in smoke
    assert "CODEX_ISOLATION=(-c 'mcp_servers={}')" not in smoke
    assert 'contains "$out" "rmcp::transport"' in smoke
    assert 'contains "$out" "AuthRequired"' in smoke
    assert "operator MCP startup leaked into isolated Codex output" in smoke

    playwright_launcher_path = (
        "$SKILLS_ROOT/playwright-debugger/scripts/run-artifact-reader.sh"
    )
    assert 'check "playwright-debugger" "F2"' in smoke
    assert playwright_launcher_path in smoke
    assert (
        f"{playwright_launcher_path} --project-root $PLAYWRIGHT_FIXTURE_ROOT "
        "-- report --report-root $PLAYWRIGHT_FIXTURE_ROOT $PLAYWRIGHT_FIXTURE"
    ) in smoke
    assert "classify only the first failure" in smoke

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

    playwright_result = subprocess.run(
        [
            str(PLAYWRIGHT_LAUNCHER),
            "--project-root",
            str(PLAYWRIGHT_FIXTURE_ROOT),
            "--",
            "report",
            "--report-root",
            str(PLAYWRIGHT_FIXTURE_ROOT),
            str(PLAYWRIGHT_FIXTURE),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert playwright_result.returncode == 0, playwright_result.stderr
    playwright_failures = json.loads(playwright_result.stdout)
    assert len(playwright_failures) == 2
    first_playwright_failure = playwright_failures[0]
    assert first_playwright_failure["outcome"] == "unexpected"
    first_attempt = first_playwright_failure["attempts"][0]
    assert first_attempt["status"] == "failed"
    assert "locator('#submit-btn')" in first_attempt["error"]

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
        "(current generator probe, bounded Playwright/Cypress readers, valid fixtures, "
        "no live Codex/network in ordinary CI)"
    )


if __name__ == "__main__":
    main()
