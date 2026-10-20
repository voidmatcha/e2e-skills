#!/usr/bin/env python3
"""Validate archived Playwright floating-Promise semantic evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-playwright-semantic-probes.py"
HELPER_PATH = ROOT / "scripts/evals/run-fixture-faults.py"
CAPTURE_HELPER_PATH = ROOT / "scripts/evals/bounded_process.py"

SPEC = importlib.util.spec_from_file_location("playwright_semantic_probes", RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {RUNNER_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ambient = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/ambient/home",
        "TMPDIR": "/ambient/tmp",
        "BASH_ENV": "/ambient/bash-env",
        "ENV": "/ambient/shell-env",
        "NODE_OPTIONS": "--require=/ambient/injected.js",
        "HTTPS_PROXY": "http://proxy.invalid",
        "AWS_SECRET_ACCESS_KEY": "ambient-cloud-secret",
        "GENERIC_TOKEN": "ambient-generic-secret",
    }
    with mock.patch.dict(os.environ, ambient, clear=True):
        environment = MODULE.semantic_environment(
            "behavior",
            "http://127.0.0.1:1234",
        )
    assert environment["FIXTURE_FAULT_MODE"] == "behavior"
    assert environment["FIXTURE_BASE_URL"] == "http://127.0.0.1:1234"
    for blocked in (
        "BASH_ENV", "ENV", "NODE_OPTIONS", "HTTPS_PROXY",
        "AWS_SECRET_ACCESS_KEY", "GENERIC_TOKEN",
    ):
        assert blocked not in environment

    assert MODULE.validate_contracts() == []
    source = MODULE.SEMANTIC_SPEC.read_text(encoding="utf-8")
    assert "catch" not in source
    assert "setTimeout" not in source
    assert "waitForTimeout" not in source
    assert source.count("timeout: 1000") == 2
    assert [probe.pattern_id for probe in MODULE.PROBES] == ["#15", "#16"]
    for probe in MODULE.PROBES:
        assert source.count(probe.marker) == 1
        assert probe.marker.startswith("  await ")
        assert probe.replacement == probe.marker.replace("  await ", "  ", 1)
        assert "catch" not in probe.replacement
        for _, _, _, expected_code in MODULE.MATRIX:
            expected_marker = (
                probe.pass_marker if expected_code == 0 else probe.failure_marker
            )
            matched, evidence = MODULE.classify_result(
                probe,
                expected_code,
                f"\x1b[31m{expected_marker}\x1b[0m",
                expected_code,
            )
            assert matched is True
            assert evidence == [expected_marker]
            matched, evidence = MODULE.classify_result(
                probe,
                expected_code,
                "runner exited without the operation-specific marker",
                expected_code,
            )
            assert matched is False
            assert evidence == [f"missing:{expected_marker}"]
            matched, evidence = MODULE.classify_result(
                probe,
                2,
                expected_marker,
                expected_code,
            )
            assert matched is False
            assert evidence == [expected_marker]

    with tempfile.TemporaryDirectory(prefix="semantic-version-bound-") as temp:
        marker = Path(temp) / "escaped-after-overflow"
        emitter = Path(temp) / "emit-version"
        emitter.write_text(
            "#!/usr/bin/python3\n"
            "import pathlib, sys, time\n"
            "sys.stdout.write('x' * 70000)\n"
            "sys.stdout.flush()\n"
            "time.sleep(30)\n"
            f"pathlib.Path({str(marker)!r}).write_text('escaped')\n",
            encoding="utf-8",
        )
        emitter.chmod(0o755)
        started = time.monotonic()
        assert MODULE.version_output([str(emitter)], Path(temp)) is None
        assert time.monotonic() - started < 10
        assert not marker.exists()

    print("playwright-semantic-probes: current runtime, safety and classification contracts pass")


if __name__ == "__main__":
    main()
