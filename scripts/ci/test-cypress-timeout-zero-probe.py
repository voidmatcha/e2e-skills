#!/usr/bin/env python3
"""Validate archived Cypress 15.19 timeout-zero semantic evidence."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Dict, List
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-cypress-timeout-zero-probe.py"
REPORT_PATH = (
    ROOT
    / "benchmarks/fixture-faults/2026-07-30-cypress-15.19-timeout-zero.json"
)
SPEC = importlib.util.spec_from_file_location(
    "cypress_timeout_zero_probe",
    RUNNER_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load {}".format(RUNNER_PATH))
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_OUTPUT_RE = re.compile(
    r"(?i)\b(token|password|secret|api[_-]?key)=[^$\s&]"
)
ABSOLUTE_PATH_RE = re.compile(r"(?:/private/|/Users/)")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_report(report: Dict[str, object]) -> List[str]:
    errors: List[str] = []
    if report.get("schema_version") != 1:
        errors.append("wrong schema version")
    if report.get("report_kind") != "cypress-timeout-zero-semantic-probe":
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
        errors.append("wrong runner timeout")

    versions = report.get("versions")
    if not isinstance(versions, dict):
        errors.append("missing versions")
        versions = {}
    if versions.get("cypress_package") != "15.19.0":
        errors.append("wrong Cypress package version")
    cli_version = versions.get("cypress_cli")
    if not isinstance(cli_version, str):
        errors.append("missing Cypress CLI version")
    else:
        for marker in (
            "Cypress package version: 15.19.0",
            "Cypress binary version: 15.19.0",
        ):
            if marker not in cli_version:
                errors.append("wrong Cypress CLI provenance")

    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        errors.append("missing provenance")
        provenance = {}
    expected_current_provenance = {
        "probe_spec_sha256": sha256_file(MODULE.SPEC_PATH),
        "probe_app_sha256": sha256_file(MODULE.APP_ROOT / "index.html"),
        "evaluator_runner_sha256": sha256_file(RUNNER_PATH),
        "capture_helper_sha256": sha256_file(
            MODULE.EVALS_DIR / "bounded_process.py"
        ),
        "server_source_sha256": sha256_file(MODULE.SERVER_PATH),
        "package_lock_sha256": sha256_file(MODULE.LOCK_PATH),
        "cypress_version_record_sha256": MODULE.canonical_sha256(
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
        case_id = str(case["id"])
        result = result_by_case.get(case_id)
        if not isinstance(result, dict):
            errors.append("missing case: {}".format(case_id))
            continue
        if result.get("title") != case["title"]:
            errors.append("{}: wrong title".format(case_id))
        if result.get("expected_exit_code") != case["expected_exit_code"]:
            errors.append("{}: wrong expected exit".format(case_id))
        if result.get("exit_code") != case["expected_exit_code"]:
            errors.append("{}: wrong actual exit".format(case_id))
        if result.get("required_markers") != list(case["required_markers"]):
            errors.append("{}: wrong required markers".format(case_id))
        if result.get("forbidden_markers") != list(case["forbidden_markers"]):
            errors.append("{}: wrong forbidden markers".format(case_id))
        if result.get("missing_markers") != []:
            errors.append("{}: required output marker missing".format(case_id))
        if result.get("present_forbidden_markers") != []:
            errors.append("{}: forbidden output marker present".format(case_id))
        if result.get("infrastructure_timeout") is not False:
            errors.append("{}: infrastructure timeout".format(case_id))
        if result.get("infrastructure_output_overflow") is not False:
            errors.append(
                "{}: infrastructure output overflow".format(case_id)
            )

        output = result.get("output")
        if not isinstance(output, str):
            errors.append("{}: missing output".format(case_id))
            continue
        recomputed, missing, forbidden = MODULE.classify_case(
            case,
            int(result.get("exit_code", -999)),
            output,
            bool(result.get("infrastructure_timeout")),
        )
        if not recomputed or result.get("matched") is not True:
            errors.append("{}: semantic classification failed".format(case_id))
        if missing != result.get("missing_markers"):
            errors.append("{}: stored missing markers drifted".format(case_id))
        if forbidden != result.get("present_forbidden_markers"):
            errors.append("{}: stored forbidden markers drifted".format(case_id))
        if result.get("output_sha256") != MODULE.sha256_bytes(
            output.encode("utf-8")
        ):
            errors.append("{}: output hash mismatch".format(case_id))
        if result.get("output_truncated") is not False:
            errors.append("{}: archived output was truncated".format(case_id))
        if result.get("output_original_bytes") != len(output.encode("utf-8")):
            errors.append("{}: output size mismatch".format(case_id))
        if len(output.encode("utf-8")) > MODULE.OUTPUT_LIMIT_BYTES:
            errors.append("{}: output exceeds bound".format(case_id))
        if "\x1b" in output:
            errors.append("{}: ANSI escape remains".format(case_id))
        if ABSOLUTE_PATH_RE.search(output) or "/private$" in output:
            errors.append("{}: absolute local path remains".format(case_id))
        if MODULE.RESIDUAL_PATH_TOKEN_RE.search(output):
            errors.append("{}: path-prefixed replacement token".format(case_id))
        if SENSITIVE_OUTPUT_RE.search(output):
            errors.append("{}: sensitive assignment remains".format(case_id))
        command = result.get("command")
        if not isinstance(command, list) or not command:
            errors.append("{}: missing command".format(case_id))
        elif any(
            "/private/" in str(argument) or "/Users/" in str(argument)
            for argument in command
        ):
            errors.append("{}: command contains a local path".format(case_id))
        if not isinstance(result.get("duration_ms"), int):
            errors.append("{}: missing duration".format(case_id))
        elif result["duration_ms"] <= 0:
            errors.append("{}: non-positive duration".format(case_id))

    expected_summary = {
        "expected_cases": 3,
        "cases": 3,
        "matched": 3,
        "expected_exit_codes": [0, 1, 1],
        "actual_exit_codes": [0, 1, 1],
        "total_duration_ms": sum(
            int(result.get("duration_ms", 0))
            for result in results
            if isinstance(result, dict)
        ),
        "errors": 0,
    }
    if report.get("summary") != expected_summary:
        errors.append("summary mismatch")
    return errors


def assert_fail_closed(report: Dict[str, object]) -> None:
    mutations = []

    def refresh_output(result: Dict[str, object]) -> None:
        output = str(result["output"])
        result["output_sha256"] = MODULE.sha256_bytes(output.encode("utf-8"))
        result["output_original_bytes"] = len(output.encode("utf-8"))

    wrong_exit = copy.deepcopy(report)
    wrong_exit["results"][1]["exit_code"] = 0
    mutations.append(("wrong exit", wrong_exit))

    missing_marker = copy.deepcopy(report)
    missing_marker["results"][1]["output"] = missing_marker["results"][1][
        "output"
    ].replace("Timed out retrying after 0ms", "REMOVED_FAILURE_MARKER")
    refresh_output(missing_marker["results"][1])
    mutations.append(("missing failure marker", missing_marker))

    stale_runner = copy.deepcopy(report)
    stale_runner["provenance"]["evaluator_runner_sha256"] = "0" * 64
    mutations.append(("stale runner provenance", stale_runner))

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

    wrong_version = copy.deepcopy(report)
    wrong_version["versions"]["cypress_package"] = "0.0.0"
    wrong_version["provenance"]["versions_sha256"] = MODULE.canonical_sha256(
        wrong_version["versions"]
    )
    mutations.append(("wrong Cypress version", wrong_version))

    path_leak = copy.deepcopy(report)
    path_leak["results"][0]["output"] += "\n/private/tmp/probe"
    refresh_output(path_leak["results"][0])
    mutations.append(("local path leak", path_leak))

    delayed_zero = copy.deepcopy(report)
    delayed_zero["results"][1]["output"] = re.sub(
        r"PROBE_ZERO_OBSERVED elapsed_ms=\d+",
        "PROBE_ZERO_OBSERVED elapsed_ms=700",
        delayed_zero["results"][1]["output"],
    )
    refresh_output(delayed_zero["results"][1])
    mutations.append(("zero timeout delayed past app change", delayed_zero))

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


def test_selected_dependency_provenance() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-cy-provenance-") as raw:
        root = Path(raw)
        executable = root / "node_modules/.bin/cypress"
        package = root / "node_modules/cypress/package.json"
        executable.parent.mkdir(parents=True)
        package.parent.mkdir(parents=True)
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
        package.write_text(
            json.dumps({"version": MODULE.EXPECTED_CYPRESS_VERSION}),
            encoding="utf-8",
        )
        (root / "package-lock.json").write_text(
            json.dumps(
                {
                    "packages": {
                        "node_modules/cypress": {
                            "version": MODULE.EXPECTED_CYPRESS_VERSION,
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


def test_version_environment_and_bounds() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-cy-version-") as raw:
        root = Path(raw)
        script = root / "version"
        script.write_text(
            "#!/bin/sh\n"
            'test -z "$ANTHROPIC_API_KEY" || exit 9\n'
            'case "$HOME" in /ambient/*) exit 8;; esac\n'
            'printf "Cypress package version: 1.2.3\\n'
            'Cypress binary version: 1.2.3\\n'
            'Electron version: 1\\nBundled Node version: 2\\n"\n',
            encoding="utf-8",
        )
        script.chmod(0o755)
        pattern = re.compile(
            r"Cypress package version: \d+\.\d+\.\d+\n"
            r"Cypress binary version: \d+\.\d+\.\d+\n"
            r"Electron version: [^\n]+\nBundled Node version: [^\n]+"
        )
        with mock.patch.dict(
            os.environ,
            {"PATH": "/usr/bin:/bin", "ANTHROPIC_API_KEY": "must-not-leak"},
            clear=True,
        ):
            assert MODULE.version_output(
                [str(script)],
                cwd=root,
                expected=pattern,
            ) is not None
        script.write_text(
            "#!/bin/sh\nprintf 'unexpected\\n'\n",
            encoding="utf-8",
        )
        assert MODULE.version_output(
            [str(script)],
            cwd=root,
            expected=pattern,
        ) is None


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


def test_high_rate_output_is_an_infrastructure_error() -> None:
    return_code, output, timed_out, overflowed = MODULE.run_captured(
        [
            sys.executable,
            "-c",
            (
                "import os\n"
                "chunk = b'z' * 65536\n"
                "for _ in range(128): os.write(1, chunk)\n"
            ),
        ],
        cwd=Path.cwd(),
        environment={"PATH": "/usr/bin:/bin"},
        timeout=5,
        output_limit_bytes=4096,
    )
    assert return_code == 125
    assert timed_out is False
    assert overflowed is True
    assert output.startswith("z" * 4096)
    assert "output exceeded 4096 bytes" in output
    assert len(output.encode("utf-8")) < 4300


def test_probe_server_cleanup_failure_is_fail_closed() -> None:
    class Process:
        pid = 12345
        stdout = io.StringIO('{"port": 43123}\n')
        stderr = io.StringIO("")

        def poll(self):
            return None

    class Selector:
        def register(self, *_args) -> None:
            pass

        def select(self, timeout=None):
            return [object()]

        def close(self) -> None:
            pass

    process = Process()
    cleanup_calls = []

    def failed_cleanup(candidate):
        cleanup_calls.append(candidate)
        return ["SIGTERM: PermissionError: operation not permitted"]

    with mock.patch.object(
        MODULE.subprocess, "Popen", return_value=process
    ), mock.patch.object(
        MODULE.selectors, "DefaultSelector", return_value=Selector()
    ), mock.patch.object(
        MODULE, "stop_process", side_effect=failed_cleanup
    ):
        try:
            with MODULE.probe_server("node", Path("probe-home")):
                pass
        except RuntimeError as exc:
            assert "probe server cleanup failed" in str(exc)
            assert "SIGTERM: PermissionError:" in str(exc)
        else:
            raise AssertionError("probe server cleanup failure was ignored")
    assert cleanup_calls == [process]

    original = ValueError("active probe failure")
    cleanup_calls.clear()
    process.stdout.seek(0)
    with mock.patch.object(
        MODULE.subprocess, "Popen", return_value=process
    ), mock.patch.object(
        MODULE.selectors, "DefaultSelector", return_value=Selector()
    ), mock.patch.object(
        MODULE, "stop_process", side_effect=failed_cleanup
    ):
        try:
            with MODULE.probe_server("node", Path("probe-home")):
                raise original
        except ValueError as exc:
            assert exc is original
            assert any(
                "probe server cleanup failed" in note
                and "SIGTERM: PermissionError:" in note
                for note in getattr(exc, "__notes__", [])
            )
            assert "probe server cleanup failed" in MODULE.exception_message(exc)
        else:
            raise AssertionError("active probe failure was not preserved")
    assert cleanup_calls == [process]


def test_node_executable_path_is_sanitized() -> None:
    node = "/Users/example/.nvm/versions/node/v24/bin/node"
    with mock.patch.object(
        MODULE.shutil, "which", return_value=node
    ), mock.patch.object(
        MODULE, "cypress_cache_path", return_value=Path("/cache/cypress")
    ):
        output, truncated, original_bytes = MODULE.sanitize_output(
            "Node Version: v24 ({})".format(node),
            Path("/probe/workspace"),
            Path("/probe/dependencies"),
            "http://127.0.0.1:4321",
        )
    assert output == "Node Version: v24 ($NODE_EXECUTABLE)"
    assert truncated is False
    assert original_bytes == len(output.encode("utf-8"))


def test_output_sanitizer_matches_shared_secret_and_path_contract() -> None:
    provider_token = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz1234567890"
    public_url = "https://example.test/" + "Users/public"
    output, truncated, original_bytes = MODULE.sanitize_output(
        (
            public_url
            + ' {"api_key":"json-secret-value"} '
            "--password cli-secret "
            "Authorization: Basic dXNlcjpwYXNz "
            "Cookie: session=browser-secret\n"
            + provider_token
        ),
        Path("/private/tmp/probe"),
        Path("/private/tmp/dependencies"),
        "http://127.0.0.1:4321",
    )
    assert public_url in output
    for secret in (
        "json-secret-value",
        "cli-secret",
        "dXNlcjpwYXNz",
        "browser-secret",
        provider_token,
    ):
        assert secret not in output
    assert output.count("$REDACTED") == 5
    assert truncated is False
    assert original_bytes == len(output.encode("utf-8"))

    for leaked_path in (
        "/private/tmp/unrelated/probe.log",
        "/var/folders/aa/bb/T/unrelated.log",
        "/private/var/folders/aa/bb/T/unrelated.log",
        "/" + "Users/other-user/project/trace.zip",
    ):
        try:
            MODULE.sanitize_output(
                "unrelated path: {}".format(leaked_path),
                Path("/private/tmp/probe"),
                Path("/private/tmp/dependencies"),
                "http://127.0.0.1:4321",
            )
        except ValueError as exc:
            assert "absolute local path" in str(exc)
        else:
            raise AssertionError(
                "sanitizer accepted unrelated absolute path: {}".format(
                    leaked_path
                )
            )

    never_matches = re.compile(r"(?!x)x")
    with mock.patch.object(MODULE, "SENSITIVE_RE", never_matches):
        try:
            MODULE.sanitize_output(
                "api_key: unsanitized-secret",
                Path("/private/tmp/probe"),
                Path("/private/tmp/dependencies"),
                "http://127.0.0.1:4321",
            )
        except ValueError as exc:
            assert "residual secret" in str(exc)
        else:
            raise AssertionError("residual secret bypassed fail-closed check")


def main() -> None:
    ambient = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/ambient/home",
        "TMPDIR": "/ambient/tmp",
        "CYPRESS_CACHE_FOLDER": "/ambient/cypress-cache",
        "BASH_ENV": "/ambient/bash-env",
        "ENV": "/ambient/shell-env",
        "NODE_OPTIONS": "--require=/ambient/injected.js",
        "NO_PROXY": "*",
        "NPM_TOKEN": "ambient-generic-secret",
    }
    with mock.patch.dict(os.environ, ambient, clear=True):
        environment = MODULE.safe_environment(
            "default-retries",
            "http://127.0.0.1:1234",
            home="/isolated/home",
        )
    assert environment["HOME"] == "/isolated/home"
    assert environment["CYPRESS_CACHE_FOLDER"] == ambient["CYPRESS_CACHE_FOLDER"]
    assert environment["PROBE_BASE_URL"] == "http://127.0.0.1:1234"
    assert environment["CYPRESS_probeCase"] == "default-retries"
    for blocked in (
        "BASH_ENV", "ENV", "NODE_OPTIONS", "NO_PROXY", "NPM_TOKEN",
    ):
        assert blocked not in environment

    test_selected_dependency_provenance()
    test_version_environment_and_bounds()
    test_timeout_cleanup_permission_error_is_reported()
    test_high_rate_output_is_an_infrastructure_error()
    test_probe_server_cleanup_failure_is_fail_closed()
    test_node_executable_path_is_sanitized()
    test_output_sanitizer_matches_shared_secret_and_path_contract()
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
        "Cypress timeout-zero probe: pass "
        "(#4g; exits 0/1/1; 9 fail-closed mutations rejected)"
    )


if __name__ == "__main__":
    main()
