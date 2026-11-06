#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate the manual Codex smoke contract without invoking Codex or network."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "scripts/ci/codex-smoke.sh"
CI_LOCAL = ROOT / "scripts/ci/ci-local.sh"
PYTHON_ISOLATION_INIT = ROOT / "scripts/ci/lib/init-python-isolation.sh"
FIXTURE_ROOT = ROOT / "scripts/ci/fixtures/codex-smoke"
GENERATOR = ROOT / "skills/playwright-test-generator/SKILL.md"
GENERATOR_THIN_RULES = ROOT / "skills/playwright-test-generator/thin-rules.md"


def main() -> None:
    smoke = SMOKE.read_text(encoding="utf-8")
    ci_local = CI_LOCAL.read_text(encoding="utf-8")
    python_isolation_init = PYTHON_ISOLATION_INIT.read_text(encoding="utf-8")
    generator = GENERATOR.read_text(encoding="utf-8")
    thin_rules = GENERATOR_THIN_RULES.read_text(encoding="utf-8")

    # Check 5 recalls the MCP tool name from the router SKILL.md, which the
    # 3.0.0 official-first router checks before delegating.
    current_probe_token = "generator_write_test"
    assert current_probe_token in generator
    assert "Playwright thin rules" in thin_rules
    assert f'check "test-generator" "{current_probe_token}"' in smoke
    assert "playwright-test-generator/thin-rules.md" in smoke
    assert "exploration-preflight" not in smoke
    assert "--framed-stdin" not in smoke
    assert "run-preflight-target" not in smoke
    assert "curl -fsS -o /dev/null -w" not in smoke
    assert "CODEX_ISOLATION=(--ephemeral --ignore-user-config)" in smoke
    assert "CODEX_ISOLATION=(-c 'mcp_servers={}')" not in smoke
    assert 'contains "$out" "rmcp::transport"' in smoke
    assert 'contains "$out" "AuthRequired"' in smoke
    assert "operator MCP startup leaked into isolated Codex output" in smoke

    # The debugger skills were removed; their checks must not come back.
    for removed in ("playwright-debugger", "cypress-debugger", "F1-F15"):
        assert removed not in smoke.replace("The debugger checks were dropped", ""), removed
    assert 'check "e2e-reviewer" "#4f"' in smoke
    assert (FIXTURE_ROOT / "silent.spec.ts").is_file()
    assert "all 3 checks passed" in smoke

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
        "(current generator and reviewer probes, valid fixtures, "
        "no live Codex/network in ordinary CI)"
    )


if __name__ == "__main__":
    main()
