#!/usr/bin/env python3
"""Validate archived Playwright 1.62 timeout-zero semantic evidence."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Dict, List
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-playwright-timeout-zero-probe.py"
REPORT_PATH = (
    ROOT
    / "benchmarks/fixture-faults/2026-07-30-playwright-1.62-timeout-zero.json"
)

SPEC = importlib.util.spec_from_file_location(
    "playwright_timeout_zero_probe",
    RUNNER_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load {}".format(RUNNER_PATH))
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_OUTPUT_RE = MODULE.RESIDUAL_SECRET_RE
ABSOLUTE_PATH_RE = MODULE.ABSOLUTE_LOCAL_PATH_RE


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_report(report: Dict[str, object]) -> List[str]:
    errors: List[str] = []
    if report.get("schema_version") != 1:
        errors.append("wrong schema version")
    if report.get("report_kind") != "playwright-timeout-zero-semantic-probe":
        errors.append("wrong report kind")
    if report.get("pattern_id") != "#4g":
        errors.append("wrong pattern ID")
    if report.get("mode") != "run":
        errors.append("archive must contain a live run")
    if report.get("complete") is not True:
        errors.append("archive is incomplete")
    if report.get("contracts_valid") is not True:
        errors.append("probe contracts were not valid")
    if report.get("runtime_complete") is not True:
        errors.append("runtime matrix is incomplete")
    if report.get("errors") != []:
        errors.append("archive contains runtime errors")
    if report.get("output_limit_bytes") != MODULE.OUTPUT_LIMIT_BYTES:
        errors.append("wrong output bound")
    if (
        report.get("process_output_limit_bytes")
        != MODULE.PROCESS_OUTPUT_LIMIT_BYTES
    ):
        errors.append("wrong process output bound")
    if (
        report.get("subprocess_timeout_seconds")
        != MODULE.SUBPROCESS_TIMEOUT_SECONDS
    ):
        errors.append("wrong infrastructure timeout")

    versions = report.get("versions")
    if not isinstance(versions, dict):
        errors.append("missing versions")
        versions = {}
    if versions.get("playwright_cli") != "Version 1.62.0":
        errors.append("wrong Playwright CLI version")
    if versions.get("playwright_package") != "1.62.0":
        errors.append("wrong Playwright package version")

    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("missing provenance")
        provenance = {}
    expected_current_provenance = {
        "probe_source_sha256": sha256_file(MODULE.SPEC_PATH),
        "evaluator_runner_sha256": sha256_file(RUNNER_PATH),
        "capture_helper_sha256": sha256_file(
            MODULE.EVALS_DIR / "bounded_process.py"
        ),
        "package_lock_sha256": sha256_file(MODULE.LOCK_PATH),
        "playwright_version_record_sha256": MODULE.canonical_sha256(
            MODULE.package_lock_version_record()
        ),
        "versions_sha256": MODULE.canonical_sha256(versions),
        "case_contract_sha256": MODULE.canonical_sha256(MODULE.CASES),
        "generated_config_sha256": MODULE.sha256_bytes(
            MODULE.CONFIG_SOURCE.encode("utf-8")
        ),
        "selected_package_lock_sha256": sha256_file(MODULE.LOCK_PATH),
        "selected_version_record_sha256": MODULE.canonical_sha256(
            MODULE.package_lock_version_record()
        ),
    }
    archived_dependency_keys = {
        "selected_executable_sha256",
        "selected_package_json_sha256",
    }
    if set(provenance) != (
        set(expected_current_provenance) | archived_dependency_keys
    ):
        errors.append("incomplete or stale provenance")
    for key, expected in expected_current_provenance.items():
        if provenance.get(key) != expected:
            errors.append("incomplete or stale provenance")
            break
    # These two digests describe the platform-dependent dependency tree used
    # for the historical live run. The evidence manifest authenticates the
    # archive; ordinary CI must not require the ignored local node_modules tree.
    for key, value in provenance.items():
        if key.endswith("_sha256") and not SHA256_RE.fullmatch(str(value)):
            errors.append("invalid provenance hash: {}".format(key))

    results = report.get("results")
    if not isinstance(results, list):
        errors.append("missing results")
        results = []
    if len(results) != len(MODULE.CASES):
        errors.append("wrong result count")
    result_by_case = {
        result.get("case"): result
        for result in results
        if isinstance(result, dict)
    }
    for case in MODULE.CASES:
        result = result_by_case.get(case["id"])
        if not isinstance(result, dict):
            errors.append("missing case: {}".format(case["id"]))
            continue
        if result.get("expected_exit_code") != case["expected_exit_code"]:
            errors.append("{}: wrong expected exit".format(case["id"]))
        if result.get("exit_code") != case["expected_exit_code"]:
            errors.append("{}: wrong actual exit".format(case["id"]))
        if result.get("required_markers") != list(case["required_markers"]):
            errors.append("{}: wrong required markers".format(case["id"]))
        if result.get("forbidden_markers") != list(case["forbidden_markers"]):
            errors.append("{}: wrong forbidden markers".format(case["id"]))
        if result.get("missing_markers") != []:
            errors.append("{}: required output marker missing".format(case["id"]))
        if result.get("present_forbidden_markers") != []:
            errors.append("{}: forbidden output marker present".format(case["id"]))
        if result.get("infrastructure_timeout") is not False:
            errors.append("{}: infrastructure timeout".format(case["id"]))
        if result.get("infrastructure_output_overflow") is not False:
            errors.append(
                "{}: infrastructure output overflow".format(case["id"])
            )
        if result.get("matched") is not True:
            errors.append("{}: case did not match".format(case["id"]))

        output = result.get("output")
        if not isinstance(output, str):
            errors.append("{}: missing output".format(case["id"]))
            continue
        for marker in case["required_markers"]:
            if marker not in output:
                errors.append("{}: output missing {!r}".format(case["id"], marker))
        for marker in case["forbidden_markers"]:
            if marker in output:
                errors.append(
                    "{}: output contains forbidden {!r}".format(case["id"], marker)
                )
        if result.get("output_sha256") != MODULE.sha256_bytes(
            output.encode("utf-8")
        ):
            errors.append("{}: output hash mismatch".format(case["id"]))
        if result.get("output_truncated") is not False:
            errors.append("{}: archived output was truncated".format(case["id"]))
        if not isinstance(result.get("output_original_bytes"), int):
            errors.append("{}: missing original output size".format(case["id"]))
        elif result["output_original_bytes"] != len(output.encode("utf-8")):
            errors.append("{}: output size mismatch".format(case["id"]))
        if len(output.encode("utf-8")) > MODULE.OUTPUT_LIMIT_BYTES:
            errors.append("{}: output exceeds bound".format(case["id"]))
        if "\x1b" in output:
            errors.append("{}: ANSI escape remains".format(case["id"]))
        if ABSOLUTE_PATH_RE.search(MODULE.HTTP_URL_RE.sub("", output)):
            errors.append("{}: absolute local path remains".format(case["id"]))
        if SENSITIVE_OUTPUT_RE.search(output):
            errors.append("{}: sensitive assignment remains".format(case["id"]))
        if not isinstance(result.get("duration_ms"), int):
            errors.append("{}: missing duration".format(case["id"]))
        elif result["duration_ms"] <= 0:
            errors.append("{}: non-positive duration".format(case["id"]))

    summary = report.get("summary")
    expected_summary = {
        "expected_cases": 3,
        "cases": 3,
        "matched": 3,
        "expected_exit_codes": [1, 0, 1],
        "actual_exit_codes": [1, 0, 1],
        "total_duration_ms": sum(
            int(result.get("duration_ms", 0))
            for result in results
            if isinstance(result, dict)
        ),
        "errors": 0,
    }
    if summary != expected_summary:
        errors.append("summary mismatch")
    return errors


def assert_fail_closed(report: Dict[str, object]) -> None:
    mutations = []

    wrong_exit = copy.deepcopy(report)
    wrong_exit["results"][0]["exit_code"] = 0
    mutations.append(("wrong exit", wrong_exit))

    missing_marker = copy.deepcopy(report)
    marker = missing_marker["results"][1]["required_markers"][1]
    missing_marker["results"][1]["output"] = missing_marker["results"][1][
        "output"
    ].replace(marker, "REMOVED_REQUIRED_MARKER")
    mutations.append(("missing marker", missing_marker))

    incomplete = copy.deepcopy(report)
    incomplete["complete"] = False
    mutations.append(("incomplete report", incomplete))

    missing_provenance = copy.deepcopy(report)
    del missing_provenance["provenance"]["package_lock_sha256"]
    mutations.append(("missing provenance", missing_provenance))

    stale_capture_helper = copy.deepcopy(report)
    stale_capture_helper["provenance"]["capture_helper_sha256"] = "0" * 64
    mutations.append(("stale capture helper", stale_capture_helper))

    invalid_archived_dependency = copy.deepcopy(report)
    invalid_archived_dependency["provenance"][
        "selected_executable_sha256"
    ] = "not-a-sha256"
    mutations.append(
        ("invalid archived dependency digest", invalid_archived_dependency)
    )

    wrong_process_bound = copy.deepcopy(report)
    wrong_process_bound["process_output_limit_bytes"] = 1
    mutations.append(("wrong process output bound", wrong_process_bound))

    path_leak = copy.deepcopy(report)
    path_leak["results"][0]["output"] += "\n/var/folders/unrelated/T/probe.log"
    path_leak["results"][0]["output_sha256"] = MODULE.sha256_bytes(
        path_leak["results"][0]["output"].encode("utf-8")
    )
    path_leak["results"][0]["output_original_bytes"] = len(
        path_leak["results"][0]["output"].encode("utf-8")
    )
    mutations.append(("unrelated absolute path", path_leak))

    secret_leak = copy.deepcopy(report)
    secret_leak["results"][0]["output"] += (
        '\n{"api_key":"unrelated-secret-value"}'
    )
    secret_leak["results"][0]["output_sha256"] = MODULE.sha256_bytes(
        secret_leak["results"][0]["output"].encode("utf-8")
    )
    secret_leak["results"][0]["output_original_bytes"] = len(
        secret_leak["results"][0]["output"].encode("utf-8")
    )
    mutations.append(("unrelated secret", secret_leak))

    for label, mutation in mutations:
        if not validate_report(mutation):
            raise AssertionError("validator accepted {}".format(label))


def test_archive_validation_does_not_read_local_dependencies(
    report: Dict[str, object],
) -> None:
    with mock.patch.object(
        MODULE,
        "dependency_artifacts",
        side_effect=AssertionError("archive validation read node_modules"),
    ):
        assert validate_report(report) == []


def test_output_sanitizer_fail_closed() -> None:
    workspace = Path("/private/tmp/probe-workspace")
    dependency_root = Path("/private/tmp/probe-dependencies")
    users_path = "/" + "Users/other-user/project/trace.zip"
    public_url = "https://example.test/" + "Users/public"
    provider_token = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz1234567890"
    for leaked_path in (
        users_path,
        "/private/tmp/unrelated/probe.log",
        "/var/folders/aa/bb/T/unrelated.log",
        "/private/var/folders/aa/bb/T/unrelated.log",
    ):
        try:
            MODULE.sanitize_output(
                "unrelated path: {}".format(leaked_path),
                workspace,
                dependency_root,
            )
        except ValueError as exc:
            assert "absolute local path" in str(exc)
        else:
            raise AssertionError(
                "sanitizer accepted unrelated absolute path: {}".format(
                    leaked_path
                )
            )

    output, truncated, original_bytes = MODULE.sanitize_output(
        (
            public_url
            + ' {"api_key":"json-secret-value"} '
            "--password cli-secret "
            "Authorization: Basic dXNlcjpwYXNz "
            "Cookie: session=browser-secret\n"
            + provider_token
        ),
        workspace,
        dependency_root,
    )
    assert public_url in output
    assert "json-secret-value" not in output
    assert "cli-secret" not in output
    assert "dXNlcjpwYXNz" not in output
    assert "browser-secret" not in output
    assert provider_token not in output
    assert output.count("$REDACTED") == 5
    assert truncated is False
    assert original_bytes == len(output.encode("utf-8"))

    never_matches = re.compile(r"(?!x)x")
    with mock.patch.object(MODULE, "SENSITIVE_RE", never_matches):
        try:
            MODULE.sanitize_output(
                "api_key: unsanitized-secret",
                workspace,
                dependency_root,
            )
        except ValueError as exc:
            assert "residual secret" in str(exc)
        else:
            raise AssertionError("residual secret bypassed fail-closed check")


def test_sanitizer_failure_becomes_runtime_error() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-pw-sanitize-error-") as raw:
        dependency_root = Path(raw)
        (dependency_root / "node_modules").mkdir()
        with mock.patch.object(
            MODULE,
            "run_case",
            side_effect=ValueError(
                "sanitized probe output contains an absolute local path"
            ),
        ):
            results, errors = MODULE.run_matrix(dependency_root)
    assert results == []
    assert len(errors) == len(MODULE.CASES)
    assert all("absolute local path" in error for error in errors)


def test_selected_dependency_provenance() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-pw-provenance-") as raw:
        root = Path(raw)
        executable = root / "node_modules/.bin/playwright"
        package = root / "node_modules/@playwright/test/package.json"
        executable.parent.mkdir(parents=True)
        package.parent.mkdir(parents=True)
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
        package.write_text(
            json.dumps({"version": MODULE.EXPECTED_PLAYWRIGHT_VERSION}),
            encoding="utf-8",
        )
        (root / "package-lock.json").write_text(
            json.dumps(
                {
                    "packages": {
                        "node_modules/@playwright/test": {
                            "version": MODULE.EXPECTED_PLAYWRIGHT_VERSION,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        artifacts, errors = MODULE.dependency_artifacts(root)
        assert errors == []
        assert set(artifacts) == {"executable", "package_json", "package_lock"}

        outside = root.parent / f"{root.name}-outside"
        outside.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        outside.chmod(0o755)
        executable.unlink()
        executable.symlink_to(outside)
        _, errors = MODULE.dependency_artifacts(root)
        assert any("resolves outside dependency root" in error for error in errors)
        outside.unlink()


def test_version_environment_and_timeout_group() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-pw-process-") as raw:
        root = Path(raw)
        script = root / "version"
        script.write_text(
            "#!/bin/sh\n"
            'test -z "$OPENAI_API_KEY" || exit 9\n'
            'case "$HOME" in /ambient/*) exit 8;; esac\n'
            'printf "Version 1.2.3\\n"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)
        with mock.patch.dict(
            os.environ,
            {"PATH": "/usr/bin:/bin", "OPENAI_API_KEY": "must-not-leak"},
            clear=True,
        ):
            assert MODULE.version_output(
                [str(script)],
                cwd=root,
                expected=re.compile(r"Version \d+\.\d+\.\d+"),
            ) == "Version 1.2.3"

        marker = root / "orphan-marker"
        return_code, _, timed_out, overflowed = MODULE.run_captured(
            [
                "/bin/sh",
                "-c",
                f"(sleep 2; touch '{marker}') & wait",
            ],
            cwd=root,
            environment={"PATH": "/usr/bin:/bin"},
            timeout=1,
        )
        assert return_code == 124 and timed_out is True
        assert overflowed is False
        time.sleep(2)
        assert not marker.exists()

        return_code, output, timed_out, overflowed = MODULE.run_captured(
            [
                sys.executable,
                "-c",
                "import os; os.write(1, b'x' * 1000000)",
            ],
            cwd=root,
            environment={"PATH": "/usr/bin:/bin"},
            timeout=5,
            output_limit_bytes=3072,
        )
        assert return_code == 125
        assert timed_out is False
        assert overflowed is True
        assert output.startswith("x" * 3072)
        assert "output exceeded 3072 bytes" in output
        assert len(output.encode("utf-8")) < 3300


def test_timeout_cleanup_permission_error_is_reported() -> None:
    class Process:
        pid = 12345
        returncode = None

    process = Process()
    with mock.patch.object(
        MODULE.subprocess, "Popen", return_value=process
    ), mock.patch.object(
        MODULE,
        "capture_process",
        return_value=MODULE.CaptureResult(
            return_code=125,
            output="partial output",
            timed_out=True,
            overflowed=False,
            cleanup_failures=(
                "SIGTERM: PermissionError: operation not permitted",
            ),
        ),
    ):
        return_code, output, timed_out, overflowed = MODULE.run_captured(
            ["runner"],
            cwd=Path.cwd(),
            environment={},
            timeout=1,
        )
    assert return_code == 124 and timed_out is True
    assert overflowed is False
    assert "cleanup failure: SIGTERM: PermissionError:" in output


def main() -> None:
    ambient = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/ambient/home",
        "TMPDIR": "/ambient/tmp",
        "BASH_ENV": "/ambient/bash-env",
        "ENV": "/ambient/shell-env",
        "NODE_OPTIONS": "--require=/ambient/injected.js",
        "ALL_PROXY": "socks5://proxy.invalid",
        "GITHUB_TOKEN": "ambient-generic-secret",
    }
    with mock.patch.dict(os.environ, ambient, clear=True):
        environment = MODULE.safe_environment(home="/isolated/home")
    assert environment["HOME"] == "/isolated/home"
    assert environment["CI"] == "1"
    assert environment["NO_COLOR"] == "1"
    for blocked in (
        "BASH_ENV", "ENV", "NODE_OPTIONS", "ALL_PROXY", "GITHUB_TOKEN",
    ):
        assert blocked not in environment

    test_selected_dependency_provenance()
    test_version_environment_and_timeout_group()
    test_timeout_cleanup_permission_error_is_reported()
    test_output_sanitizer_fail_closed()
    test_sanitizer_failure_becomes_runtime_error()
    contract_errors = MODULE.validate_contracts()
    if contract_errors:
        raise AssertionError("probe contract errors: {}".format(contract_errors))
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    test_archive_validation_does_not_read_local_dependencies(report)
    errors = validate_report(report)
    if errors:
        raise AssertionError("\n".join(errors))
    assert_fail_closed(report)
    print(
        "Playwright timeout-zero probe: pass "
        "(#4g; exits 1/0/1; 9 fail-closed mutations rejected)"
    )


if __name__ == "__main__":
    main()
