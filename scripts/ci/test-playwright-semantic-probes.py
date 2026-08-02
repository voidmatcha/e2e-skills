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
EVIDENCE_PATH = (
    ROOT
    / "benchmarks/fixture-faults/2026-07-31-playwright-1.62-floating-promises.json"
)
CANONICAL_PATH = ROOT / "benchmarks/fixture-faults/2026-07-31-current.json"

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

    report = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert report["schema_version"] == 2
    assert report["report_kind"] == "playwright-floating-promise-semantic-probe"
    assert report["mode"] == "run"
    assert report["complete"] is True
    assert report["contracts_valid"] is True
    assert report["runtime_complete"] is True
    assert report["errors"] == []
    assert (
        report["process_output_limit_bytes"]
        == MODULE.HELPER.PROCESS_OUTPUT_LIMIT_BYTES
    )
    assert report["subprocess_timeout_seconds"] == 120
    assert report["versions"]["playwright"] == "Version 1.62.0"
    assert report["summary"] == {
        "probes": 2,
        "expected_cases": 6,
        "cases": 6,
        "matched": 6,
        "fault_unawaited_nonzero": 2,
        "errors": 0,
    }

    provenance = report["provenance"]
    assert provenance == {
        "semantic_input_sha256": sha256(MODULE.SEMANTIC_SPEC),
        "operators_sha256": MODULE.probes_sha256(),
        "evaluator_runner_sha256": sha256(RUNNER_PATH),
        "imported_fixture_helper_sha256": sha256(HELPER_PATH),
        "capture_helper_sha256": sha256(CAPTURE_HELPER_PATH),
        "package_lock_sha256": sha256(MODULE.FIXTURES / "package-lock.json"),
    }

    expected = {
        (probe.id, case): expected_code
        for probe in MODULE.PROBES
        for case, _, _, expected_code in MODULE.MATRIX
    }
    assert {
        (result["probe"], result["case"]): result["exit_code"]
        for result in report["results"]
    } == expected
    baseline_hash = sha256(MODULE.SEMANTIC_SPEC)
    probe_by_id = {probe.id: probe for probe in MODULE.PROBES}
    for result in report["results"]:
        probe = probe_by_id[result["probe"]]
        mutated = result["case"] == "fault-unawaited"
        expected_marker = (
            probe.pass_marker
            if result["expected_exit_code"] == 0
            else probe.failure_marker
        )
        assert result["matched"] is True
        assert result["evidence"] == [expected_marker]
        assert expected_marker in result["output"]
        assert result["mutation_applied"] is mutated
        assert result["baseline_source_sha256"] == baseline_hash
        assert result["mutation_sha256"] == (
            MODULE.mutation_sha256(probe) if mutated else None
        )
        executed = source.replace(probe.marker, probe.replacement) if mutated else source
        assert result["executed_source_sha256"] == hashlib.sha256(
            executed.encode()
        ).hexdigest()
        assert "catch" not in executed
        assert len(result["output_sha256"]) == 64
        assert result["output_sha256"] == hashlib.sha256(
            result["output"].encode()
        ).hexdigest()
        assert result["output_truncated"] is False
        assert result["output_original_bytes"] == len(result["output"].encode())
        assert len(result["output"].encode()) <= MODULE.HELPER.OUTPUT_LIMIT_BYTES
        assert "\x1b" not in result["output"]
        assert "/private/" not in result["output"]
        assert "/private$" not in result["output"]
        assert "/Users/" not in result["output"]
        assert MODULE.HELPER.RESIDUAL_PATH_TOKEN_RE.search(result["output"]) is None
        assert not re.search(
            r"(?i)\b(token|password|secret|api[_-]?key)=[^$\s&]",
            result["output"],
        )
        assert not re.search(
            r"(?i)\bBearer\s+(?!\$REDACTED)",
            result["output"],
        )
        assert all("/private/" not in argument for argument in result["command"])

    canonical = json.loads(CANONICAL_PATH.read_text(encoding="utf-8"))
    assert canonical["schema_version"] == 4
    assert canonical["summary"]["operators"] == len(MODULE.HELPER.OPERATORS) == 12
    assert canonical["summary"]["matrix_cases"] == 36
    assert canonical["summary"]["matched"] == 36
    assert len(canonical["results"]) == 36
    assert (
        canonical["provenance"]["fixture_tree_sha256"]
        == MODULE.HELPER.fixture_tree_sha256()
    )

    print("Playwright semantic probes: pass (2 probes, 6/6 exits; canonical 12/36)")


if __name__ == "__main__":
    main()
