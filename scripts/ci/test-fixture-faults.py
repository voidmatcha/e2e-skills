#!/usr/bin/env python3
"""Deterministic classification tests for the executable fault matrix."""

from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CI_LIB = ROOT / "scripts/ci/lib"
if str(CI_LIB) not in sys.path:
    sys.path.insert(0, str(CI_LIB))

from strict_json import StrictJsonError, load_strict

MODULE_PATH = ROOT / "scripts/evals/run-fixture-faults.py"
EVIDENCE_PATH = ROOT / "benchmarks/fixture-faults/2026-07-31-current.json"
EVIDENCE_ROOT = ROOT / "benchmarks/fixture-faults"
EVIDENCE_MANIFEST_PATH = EVIDENCE_ROOT / "evidence-manifest.json"
CANONICAL_EVIDENCE = {
    "2026-07-31-current.json",
    "2026-07-30-cypress-15.19-timeout-zero.json",
    "2026-07-31-playwright-1.62-floating-promises.json",
    "2026-07-30-playwright-1.62-timeout-zero.json",
}
EVIDENCE_CLASSIFICATIONS = {
    "canonical",
    "historical-complete",
    "historical-incomplete",
}
SPEC = importlib.util.spec_from_file_location("fixture_faults", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def validate_evidence_manifest(
    evidence_root: Path = EVIDENCE_ROOT,
    manifest_path: Path = EVIDENCE_MANIFEST_PATH,
) -> None:
    manifest = load_strict(manifest_path)
    assert set(manifest) == {"schema_version", "artifacts"}
    assert manifest["schema_version"] == 1
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list) and artifacts

    actual_reports = {
        path.name
        for path in evidence_root.glob("*.json")
        if path.name != manifest_path.name
    }
    listed_reports = []
    canonical_reports = set()
    for artifact in artifacts:
        assert set(artifact) == {
            "path",
            "classification",
            "sha256",
            "expected_complete",
            "expected_runtime_complete",
        }
        relative = Path(artifact["path"])
        assert relative.name == artifact["path"]
        assert relative.suffix == ".json"
        assert artifact["classification"] in EVIDENCE_CLASSIFICATIONS
        assert isinstance(artifact["expected_complete"], bool)
        assert isinstance(artifact["expected_runtime_complete"], bool)
        digest = artifact["sha256"]
        assert isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)

        report_path = evidence_root / relative
        assert report_path.is_file()
        assert hashlib.sha256(report_path.read_bytes()).hexdigest() == digest
        report = load_strict(report_path)
        assert report.get("complete") is artifact["expected_complete"]
        assert (
            report.get("runtime_complete")
            is artifact["expected_runtime_complete"]
        )
        if artifact["classification"] == "historical-incomplete":
            assert artifact["expected_complete"] is False
            assert artifact["expected_runtime_complete"] is False
        else:
            assert artifact["expected_complete"] is True
            assert artifact["expected_runtime_complete"] is True
        if artifact["classification"] == "canonical":
            canonical_reports.add(artifact["path"])
        listed_reports.append(artifact["path"])

    assert len(listed_reports) == len(set(listed_reports))
    assert set(listed_reports) == actual_reports
    assert canonical_reports == CANONICAL_EVIDENCE


def test_evidence_manifest_rejects_tampering() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-fixture-manifest-") as raw:
        evidence_root = Path(raw)
        for source in EVIDENCE_ROOT.glob("*.json"):
            (evidence_root / source.name).write_bytes(source.read_bytes())
        manifest_path = evidence_root / EVIDENCE_MANIFEST_PATH.name

        manifest = load_strict(manifest_path)
        manifest["artifacts"][0]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            validate_evidence_manifest(evidence_root, manifest_path)
        except AssertionError:
            pass
        else:
            raise AssertionError("fixture evidence digest tampering was accepted")

        manifest = load_strict(EVIDENCE_MANIFEST_PATH)
        manifest["artifacts"].pop()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        try:
            validate_evidence_manifest(evidence_root, manifest_path)
        except AssertionError:
            pass
        else:
            raise AssertionError("unlisted fixture evidence was accepted")


def test_evidence_manifest_requires_strict_json() -> None:
    invalid_documents = {
        "duplicate key": '{"schema_version":1,"schema_version":1,"artifacts":[]}',
        "NaN": '{"schema_version":NaN,"artifacts":[]}',
        "Infinity": '{"schema_version":Infinity,"artifacts":[]}',
        "BOM": '\ufeff{"schema_version":1,"artifacts":[]}',
        "trailing data": '{"schema_version":1,"artifacts":[]} trailing',
    }
    with tempfile.TemporaryDirectory(prefix="e2e-fixture-strict-json-") as raw:
        root = Path(raw)
        manifest_path = root / "evidence-manifest.json"
        for label, document in invalid_documents.items():
            manifest_path.write_text(document, encoding="utf-8")
            try:
                validate_evidence_manifest(root, manifest_path)
            except StrictJsonError:
                continue
            raise AssertionError(f"fixture manifest accepted {label}")


def expected_marker(operator, cell: str) -> str:
    if cell == "fault-strong":
        return operator.failure_marker
    if cell == "fault-mutant" and operator.mutant_pass_marker:
        return operator.mutant_pass_marker
    return operator.pass_marker


def test_fixture_environment() -> None:
    ambient = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/" + "Users/fixture-runner",
        "TMPDIR": "/var/folders/fixture/T/",
        "TMP": "/tmp",
        "TEMP": "/tmp",
        "LANG": "en_US.UTF-8",
        "XDG_RUNTIME_DIR": "/tmp/runtime-fixture",
        "AWS_SECRET_ACCESS_KEY": "cloud-secret",
        "OPENAI_API_KEY": "model-secret",
        "HTTPS_PROXY": "http://proxy.invalid:8080",
        "ALL_PROXY": "socks5://proxy.invalid:1080",
        "BASH_ENV": "/tmp/injected-bash-env",
        "ENV": "/tmp/injected-shell-env",
        "NODE_OPTIONS": "--require=/tmp/injected-node.cjs",
        "DYLD_INSERT_LIBRARIES": "/tmp/injected.dylib",
        "OTEL_EXPORTER_OTLP_HEADERS": "authorization=telemetry-secret",
    }
    fixture_variables = {
        "FIXTURE_FAULT_MODE": "behavior",
        "FIXTURE_BASE_URL": "http://127.0.0.1:43123",
        "CYPRESS_faultMode": "behavior",
    }
    environment = MODULE.fixture_environment(
        fixture_variables,
        ambient=ambient,
    )
    assert environment == {
        "PATH": ambient["PATH"],
        "HOME": ambient["HOME"],
        "TMPDIR": ambient["TMPDIR"],
        "TMP": ambient["TMP"],
        "TEMP": ambient["TEMP"],
        "LANG": ambient["LANG"],
        "XDG_RUNTIME_DIR": ambient["XDG_RUNTIME_DIR"],
        **fixture_variables,
    }
    assert not {
        "AWS_SECRET_ACCESS_KEY",
        "OPENAI_API_KEY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "BASH_ENV",
        "ENV",
        "NODE_OPTIONS",
        "DYLD_INSERT_LIBRARIES",
        "OTEL_EXPORTER_OTLP_HEADERS",
    } & environment.keys()
    try:
        MODULE.fixture_environment(
            {"NODE_OPTIONS": "--require=/tmp/injected-node.cjs"},
            ambient=ambient,
        )
    except ValueError as exc:
        assert "unsupported fixture environment variable(s): NODE_OPTIONS" == str(exc)
    else:
        raise AssertionError("unsupported explicit fixture variable was accepted")


def test_selected_dependency_provenance() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-fixture-provenance-") as raw:
        root = Path(raw)
        lock_packages = {}
        for framework, package_name in (
            ("playwright", "@playwright/test"),
            ("cypress", "cypress"),
        ):
            binary = root / "node_modules/.bin" / framework
            package = root / "node_modules" / package_name / "package.json"
            binary.parent.mkdir(parents=True, exist_ok=True)
            package.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o755)
            package.write_text(
                json.dumps({"name": package_name, "version": "1.2.3"}),
                encoding="utf-8",
            )
            (package.parent / "runtime.js").write_text(
                f"module.exports = {framework!r};\n",
                encoding="utf-8",
            )
            lock_packages[f"node_modules/{package_name}"] = {
                "version": "1.2.3",
                "integrity": f"sha512-{framework}",
            }
        (root / "package-lock.json").write_text(
            json.dumps({"packages": lock_packages}),
            encoding="utf-8",
        )

        provenance, errors = MODULE.dependency_provenance(
            root,
            ["playwright", "cypress"],
        )
        assert errors == []
        assert len(provenance) == 10
        assert provenance["selected_playwright_package_version"] == "1.2.3"
        assert provenance["selected_cypress_package_version"] == "1.2.3"
        assert all(
            len(value) == 64
            for key, value in provenance.items()
            if key.endswith("_sha256")
        )
        original_tree = provenance["selected_node_modules_tree_sha256"]

        runtime = root / "node_modules/@playwright/test/runtime.js"
        runtime.write_text("module.exports = 'tampered';\n", encoding="utf-8")
        tampered, errors = MODULE.dependency_provenance(root, ["playwright"])
        assert errors == []
        assert tampered["selected_node_modules_tree_sha256"] != original_tree

        runtime.write_text("module.exports = 'playwright';\n", encoding="utf-8")
        restored, errors = MODULE.dependency_provenance(root, ["playwright"])
        assert errors == []
        assert restored["selected_node_modules_tree_sha256"] == original_tree

        outside = root.parent / f"{root.name}-outside"
        outside.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        outside.chmod(0o755)
        binary = root / "node_modules/.bin/playwright"
        binary.unlink()
        binary.symlink_to(outside)
        _, errors = MODULE.dependency_provenance(root, ["playwright"])
        assert any("resolves outside dependency root" in error for error in errors)
        assert any(
            "invalid entry in selected node_modules tree" in error
            for error in errors
        )
        outside.unlink()


def test_cypress_runtime_provenance() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-cypress-runtime-") as raw:
        root = Path(raw)
        package = root / "deps/node_modules/cypress/package.json"
        package.parent.mkdir(parents=True)
        package.write_text(
            json.dumps({"name": "cypress", "version": "15.19.0"}),
            encoding="utf-8",
        )
        home = root / "home"
        if sys.platform == "darwin":
            relative = Path(
                "15.19.0/Cypress.app/Contents/MacOS/Cypress"
            )
            binary = home / "Library/Caches/Cypress" / relative
        elif os.name == "nt":
            relative = Path("15.19.0/Cypress/Cypress.exe")
            binary = root / "local-app-data/Cypress/Cache" / relative
        else:
            relative = Path("15.19.0/Cypress/Cypress")
            binary = home / ".cache/Cypress" / relative
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"selected Cypress runtime")

        environment = {"HOME": str(home)}
        if os.name == "nt":
            environment["LOCALAPPDATA"] = str(root / "local-app-data")
        with mock.patch.dict(os.environ, environment, clear=False):
            provenance, errors = MODULE.cypress_runtime_provenance(
                root / "deps"
            )
        assert errors == []
        assert provenance["selected_cypress_runtime_cache_key"] == (
            relative.as_posix()
        )
        assert provenance["selected_cypress_runtime_sha256"] == hashlib.sha256(
            b"selected Cypress runtime"
        ).hexdigest()


def test_version_probe_environment_and_bounds() -> None:
    with tempfile.TemporaryDirectory(prefix="e2e-fixture-version-test-") as raw:
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
        previous = os.environ.get("OPENAI_API_KEY")
        os.environ["OPENAI_API_KEY"] = "must-not-leak"
        try:
            assert MODULE.version_output(
                [str(script)],
                root,
                re.compile(r"Version \d+\.\d+\.\d+"),
            ) == "Version 1.2.3"
        finally:
            if previous is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous

        script.write_text(
            "#!/bin/sh\nprintf 'unexpected\\n'\n",
            encoding="utf-8",
        )
        assert MODULE.version_output(
            [str(script)],
            root,
            re.compile(r"Version \d+\.\d+\.\d+"),
        ) is None
        script.write_text(
            "#!/bin/sh\nprintf 'Version 2.3.4\\n'\n",
            encoding="utf-8",
        )
        with mock.patch.dict(os.environ, {"HOME": str(root)}, clear=False):
            assert MODULE.version_output(
                [str(script)],
                root,
                re.compile(r"Version \d+\.\d+\.\d+"),
                isolated_home=False,
            ) == "Version 2.3.4"


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
        return_code, output, _ = MODULE.run_command(
            ["runner"],
            Path.cwd(),
            {},
            timeout=1,
        )
    assert return_code == 124
    assert "fixture runner timed out after 1s" in output
    assert "cleanup failure: SIGTERM: PermissionError:" in output


def test_bounded_capture_overflow_and_timeout_cleanup() -> None:
    environment = MODULE.fixture_environment()
    high_rate = (
        "import os\n"
        "chunk = b'x' * 65536\n"
        "for _ in range(128): os.write(1, chunk)\n"
    )
    result = MODULE.run_command(
        [sys.executable, "-c", high_rate],
        Path.cwd(),
        environment,
        timeout=5,
        output_limit_bytes=4096,
    )
    return_code, output, _ = result
    assert return_code == 125
    assert output.startswith("x" * 4096)
    assert "output exceeded 4096 bytes" in output
    assert len(output.encode("utf-8")) < 4300

    long_line = "import os; os.write(1, b'y' * 1000000)"
    result = MODULE.run_command(
        [sys.executable, "-c", long_line],
        Path.cwd(),
        environment,
        timeout=5,
        output_limit_bytes=2048,
    )
    return_code, output, _ = result
    assert return_code == 125
    assert output.startswith("y" * 2048)
    assert len(output.encode("utf-8")) < 2300

    with tempfile.TemporaryDirectory(
        prefix="e2e-fixture-timeout-cleanup-"
    ) as raw:
        sentinel = Path(raw) / "child-survived"
        child = (
            "import pathlib,time; "
            "time.sleep(1.0); "
            "pathlib.Path({!r}).write_text('leak')".format(str(sentinel))
        )
        parent = (
            "import subprocess,sys,time; "
            "subprocess.Popen([sys.executable,'-c',{!r}]); "
            "print('started', flush=True); "
            "time.sleep(60)".format(child)
        )
        result = MODULE.run_command(
            [sys.executable, "-c", parent],
            Path.cwd(),
            environment,
            timeout=0.3,
            output_limit_bytes=4096,
        )
        return_code, output, _ = result
        assert return_code == 124
        assert output.startswith("started\n")
        time.sleep(1.2)
        assert not sentinel.exists(), "timeout left a process-group child running"

        inherited_pipe_sentinel = Path(raw) / "inherited-pipe-child-survived"
        child = (
            "import pathlib,time; "
            "time.sleep(0.8); "
            "pathlib.Path({!r}).write_text('leak')".format(
                str(inherited_pipe_sentinel)
            )
        )
        parent_exits = (
            "import subprocess,sys; "
            "subprocess.Popen([sys.executable,'-c',{!r}]); "
            "print('parent-exited', flush=True)".format(child)
        )
        result = MODULE.run_command(
            [sys.executable, "-c", parent_exits],
            Path.cwd(),
            environment,
            timeout=0.3,
            output_limit_bytes=4096,
        )
        return_code, output, _ = result
        assert return_code == 124
        assert output.startswith("parent-exited\n")
        time.sleep(1.0)
        assert not inherited_pipe_sentinel.exists(), (
            "exited parent left an inherited-pipe child running"
        )


def test_fixture_server_cleanup_failure_is_fail_closed() -> None:
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
            with MODULE.fixture_server("node", Path("fixtures/playwright/app")):
                pass
        except RuntimeError as exc:
            assert "fixture server cleanup failed" in str(exc)
            assert "SIGTERM: PermissionError:" in str(exc)
        else:
            raise AssertionError("fixture server cleanup failure was ignored")
    assert cleanup_calls == [process]

    original = ValueError("active fixture failure")
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
            with MODULE.fixture_server("node", Path("fixtures/playwright/app")):
                raise original
        except ValueError as exc:
            assert exc is original
            assert any(
                "fixture server cleanup failed" in note
                and "SIGTERM: PermissionError:" in note
                for note in getattr(exc, "__notes__", [])
            )
            assert "fixture server cleanup failed" in MODULE.exception_message(exc)
        else:
            raise AssertionError("active fixture failure was not preserved")
    assert cleanup_calls == [process]


def test_sanitizer_failure_becomes_runtime_error() -> None:
    @MODULE.contextmanager
    def fake_server(*_args, **_kwargs):
        yield "http://127.0.0.1:4321"

    with tempfile.TemporaryDirectory(prefix="e2e-fixture-sanitize-error-") as raw:
        dependency_root = Path(raw)
        (dependency_root / "node_modules").mkdir()
        operator = MODULE.OPERATORS[0]
        with mock.patch.object(MODULE, "OPERATORS", (operator,)), mock.patch.object(
            MODULE,
            "MATRIX",
            (("clean-strong", "none", False, 0),),
        ), mock.patch.object(
            MODULE.shutil,
            "which",
            return_value="/usr/bin/node",
        ), mock.patch.object(
            MODULE,
            "fixture_server",
            fake_server,
        ), mock.patch.object(
            MODULE,
            "framework_command",
            return_value=["runner"],
        ), mock.patch.object(
            MODULE,
            "run_command",
            return_value=(0, operator.pass_marker, 1),
        ), mock.patch.object(
            MODULE,
            "sanitize_output",
            side_effect=ValueError("sanitized output contains a residual secret"),
        ):
            results, errors = MODULE.run_matrix(
                ["playwright"],
                dependency_root,
                1,
            )
    assert results == []
    assert errors == [
        "{}/clean-strong: sanitized output contains a residual secret".format(
            operator.id
        )
    ]


def main() -> None:
    validate_evidence_manifest()
    test_evidence_manifest_rejects_tampering()
    test_evidence_manifest_requires_strict_json()
    assert MODULE.validate_fixtures() == []
    test_fixture_environment()
    test_selected_dependency_provenance()
    test_cypress_runtime_provenance()
    test_version_probe_environment_and_bounds()
    test_timeout_cleanup_permission_error_is_reported()
    test_bounded_capture_overflow_and_timeout_cleanup()
    test_fixture_server_cleanup_failure_is_fail_closed()
    test_sanitizer_failure_becomes_runtime_error()
    observed = 0

    for operator in MODULE.OPERATORS:
        for cell, _, _, expected_code in MODULE.MATRIX:
            marker = expected_marker(operator, cell)
            actual, matched, evidence = MODULE.classify_result(
                operator,
                cell,
                expected_code,
                f"\x1b[31m{marker}\x1b[0m",
                expected_code,
            )
            assert matched is True
            assert evidence == [marker]
            assert actual == ("pass" if expected_code == 0 else "fail")
            observed += 1

            _, matched, evidence = MODULE.classify_result(
                operator,
                cell,
                expected_code,
                "runner completed without the contract marker",
                expected_code,
            )
            assert matched is False
            assert evidence == [f"missing:{marker}"]

            actual, matched, evidence = MODULE.classify_result(
                operator,
                cell,
                2,
                marker,
                expected_code,
            )
            assert actual == "error"
            assert matched is False
            assert evidence == ["unexpected exit code 2"]

    assert observed == len(MODULE.OPERATORS) * len(MODULE.MATRIX) == 36
    assert len({operator.pattern_id for operator in MODULE.OPERATORS}) == 12
    assert any(
        operator.id == "playwright-aria-snapshot-name"
        and operator.pattern_id == "#4j"
        for operator in MODULE.OPERATORS
    )
    assert len(MODULE.fixture_tree_sha256()) == 64
    assert len(MODULE.operators_sha256()) == 64
    assert len(MODULE.runner_source_sha256()) == 64

    sanitized, truncated, original_bytes = MODULE.sanitize_output(
        (
            "\x1b[31m/private/tmp/copy/test.spec.mjs\x1b[0m "
            "/private/tmp/deps/node_modules "
            "http://127.0.0.1:43123 "
            "token=fixture-secret Authorization: Bearer abc.def\n"
        ),
        Path("/private/tmp/copy"),
        Path("/private/tmp/deps"),
        "http://127.0.0.1:43123",
    )
    assert sanitized == (
        "$FIXTURE_COPY/test.spec.mjs "
        "$DEPENDENCY_ROOT/node_modules "
        "$FIXTURE_BASE_URL "
        "token=$REDACTED Authorization: Bearer $REDACTED\n"
    )
    assert truncated is False
    assert original_bytes == len(sanitized.encode())

    node = "/" + "Users/example/.nvm/versions/node/v24/bin/node"
    with mock.patch.object(MODULE.shutil, "which", return_value=node):
        sanitized, truncated, original_bytes = MODULE.sanitize_output(
            "Node Version: v24 ({})".format(node),
            Path("/probe/copy"),
            Path("/probe/dependencies"),
            "http://127.0.0.1:1",
        )
    assert sanitized == "Node Version: v24 ($NODE_EXECUTABLE)"
    assert truncated is False
    assert original_bytes == len(sanitized.encode())

    fixture_home = "/" + "Users/fixture-runner"
    with mock.patch.dict(
        MODULE.os.environ,
        {"HOME": fixture_home},
        clear=False,
    ):
        sanitized, truncated, original_bytes = MODULE.sanitize_output(
            (
                "Cypress executable: "
                f"{fixture_home}/Library/Caches/Cypress/15.19.0/Cypress.app\n"
            ),
            Path("/probe/copy"),
            Path("/probe/dependencies"),
            "http://127.0.0.1:1",
        )
    assert sanitized == (
        "Cypress executable: $HOME/Library/Caches/Cypress/15.19.0/Cypress.app\n"
    )
    assert truncated is False
    assert original_bytes == len(sanitized.encode())

    sanitized, truncated, _ = MODULE.sanitize_output(
        (
            "/var/folders/demo/copy/test.spec.mjs "
            "/private/var/folders/demo/copy/trace.zip "
            "file:///private/var/folders/demo/copy/source.mjs "
            "../../../../../../private/var/folders/demo/copy/context.md "
            "/var/folders/demo/deps/node_modules/tool\n"
        ),
        Path("/var/folders/demo/copy"),
        Path("/var/folders/demo/deps"),
        "http://127.0.0.1:1",
    )
    assert sanitized == (
        "$FIXTURE_COPY/test.spec.mjs "
        "$FIXTURE_COPY/trace.zip "
        "$FIXTURE_COPY/source.mjs "
        "$FIXTURE_COPY/context.md "
        "$DEPENDENCY_ROOT/node_modules/tool\n"
    )
    assert truncated is False
    assert "/private$" not in sanitized
    assert MODULE.RESIDUAL_PATH_TOKEN_RE.search(sanitized) is None

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
                Path("/private/tmp/copy"),
                Path("/private/tmp/deps"),
                "http://127.0.0.1:1",
            )
        except ValueError as exc:
            assert "absolute local path" in str(exc)
        else:
            raise AssertionError(
                "sanitizer accepted unrelated absolute path: {}".format(
                    leaked_path
                )
            )

    sanitized, truncated, original_bytes = MODULE.sanitize_output(
        (
            public_url
            + ' {"api_key":"json-secret-value"} '
            "--password cli-secret "
            "Authorization: Basic dXNlcjpwYXNz "
            "Cookie: session=browser-secret\n"
            + provider_token
        ),
        Path("/private/tmp/copy"),
        Path("/private/tmp/deps"),
        "http://127.0.0.1:1",
    )
    assert public_url in sanitized
    assert "json-secret-value" not in sanitized
    assert "cli-secret" not in sanitized
    assert "dXNlcjpwYXNz" not in sanitized
    assert "browser-secret" not in sanitized
    assert provider_token not in sanitized
    assert sanitized.count("$REDACTED") == 5
    assert truncated is False
    assert original_bytes == len(sanitized.encode("utf-8"))

    never_matches = re.compile(r"(?!x)x")
    with mock.patch.object(MODULE, "SENSITIVE_ASSIGNMENT_RE", never_matches):
        try:
            MODULE.sanitize_output(
                "api_key: unsanitized-secret",
                Path("/private/tmp/copy"),
                Path("/private/tmp/deps"),
                "http://127.0.0.1:1",
            )
        except ValueError as exc:
            assert "residual secret" in str(exc)
        else:
            raise AssertionError("residual secret bypassed fail-closed check")

    oversized = "x" * (MODULE.OUTPUT_LIMIT_BYTES + 1)
    sanitized, truncated, original_bytes = MODULE.sanitize_output(
        oversized,
        Path("/tmp/copy"),
        Path("/tmp/deps"),
        "http://127.0.0.1:1",
    )
    assert truncated is True
    assert original_bytes == MODULE.OUTPUT_LIMIT_BYTES + 1
    assert sanitized.endswith(
        f"[output truncated at {MODULE.OUTPUT_LIMIT_BYTES} UTF-8 bytes]\n"
    )
    assert len(sanitized.encode()) <= MODULE.OUTPUT_LIMIT_BYTES

    report = load_strict(EVIDENCE_PATH)
    assert report["schema_version"] == 4
    assert report["mode"] == "run"
    assert report["complete"] is True
    assert report["contracts_valid"] is True
    assert report["runtime_complete"] is True
    assert report["errors"] == []
    assert report["output_limit_bytes"] == MODULE.OUTPUT_LIMIT_BYTES
    assert (
        report["process_output_limit_bytes"]
        == MODULE.PROCESS_OUTPUT_LIMIT_BYTES
    )
    assert report["subprocess_timeout_seconds"] == 120
    assert report["summary"] == {
        "operators": 12,
        "unique_pattern_ids": 12,
        "expected_matrix_cases": 36,
        "matrix_cases": 36,
        "matched": 36,
        "errors": 0,
    }
    assert len(report["results"]) == 36
    assert all(result["matched"] for result in report["results"])
    assert {
        (result["operator"], result["case"])
        for result in report["results"]
    } == {
        (operator.id, cell)
        for operator in MODULE.OPERATORS
        for cell, _, _, _ in MODULE.MATRIX
    }
    operators_by_id = {operator.id: operator for operator in MODULE.OPERATORS}
    expected_codes_by_cell = {
        cell: expected_code for cell, _, _, expected_code in MODULE.MATRIX
    }
    reclassified_matches = 0
    for result in report["results"]:
        actual, matched, evidence = MODULE.classify_result(
            operators_by_id[result["operator"]],
            result["case"],
            result["exit_code"],
            result["output"],
            expected_codes_by_cell[result["case"]],
        )
        assert result["actual"] == actual
        assert result["matched"] is matched
        assert result["evidence"] == evidence
        reclassified_matches += int(matched)
    assert reclassified_matches == report["summary"]["matched"] == 36
    assert report["provenance"]["fixture_tree_sha256"] == MODULE.fixture_tree_sha256()
    assert report["provenance"]["operators_sha256"] == MODULE.operators_sha256()
    # Historical reports are immutable snapshots. The runner is allowed to
    # evolve; the evidence manifest authenticates the archived report itself.
    assert re.fullmatch(
        r"[0-9a-f]{64}",
        report["provenance"]["evaluator_runner_sha256"],
    )
    assert report["provenance"]["capture_helper_sha256"] == hashlib.sha256(
        (MODULE.EVALS_DIR / "bounded_process.py").read_bytes()
    ).hexdigest()
    assert report["provenance"]["package_lock_sha256"] == hashlib.sha256(
        (MODULE.FIXTURES / "package-lock.json").read_bytes()
    ).hexdigest()
    # This digest describes the exact platform-dependent dependency tree that
    # produced the archive. Ordinary CI verifies the archive manifest and the
    # lockfile, but does not compare against an ignored local node_modules tree.
    # An opt-in live run performs the complete dependency recheck.
    for key in (
        "selected_node_modules_tree_sha256",
        "selected_playwright_executable_sha256",
        "selected_playwright_package_json_sha256",
        "selected_playwright_lock_record_sha256",
        "selected_cypress_executable_sha256",
        "selected_cypress_package_json_sha256",
        "selected_cypress_lock_record_sha256",
    ):
        assert re.fullmatch(r"[0-9a-f]{64}", report["provenance"][key])
    for result in report["results"]:
        assert len(result["output_sha256"]) == 64
        assert result["infrastructure_timeout"] is False
        assert result["infrastructure_output_overflow"] is False
        assert isinstance(result["output"], str) and result["output"]
        assert result["output_sha256"] == hashlib.sha256(
            result["output"].encode()
        ).hexdigest()
        assert result["output_truncated"] is False
        assert result["output_original_bytes"] == len(result["output"].encode())
        assert len(result["output"].encode()) <= MODULE.OUTPUT_LIMIT_BYTES
        assert "\x1b" not in result["output"]
        assert MODULE.ABSOLUTE_LOCAL_PATH_RE.search(
            MODULE.HTTP_URL_RE.sub("", result["output"])
        ) is None
        assert "/private$" not in result["output"]
        assert "/" + "Users/" not in result["output"]
        assert MODULE.RESIDUAL_PATH_TOKEN_RE.search(result["output"]) is None
        assert MODULE.RESIDUAL_SECRET_RE.search(result["output"]) is None
        assert all("/private/" not in part for part in result["command"])
        assert result["mutation_applied"] == (result["case"] == "fault-mutant")
        assert (result["mutation_sha256"] is not None) == result["mutation_applied"]

    print("fixture fault classifier: pass (36 synthetic + 36 browser cells)")


if __name__ == "__main__":
    main()
