#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Focused adversarial tests for the Cypress CI artifact downloader."""

from __future__ import annotations

from contextlib import contextmanager
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import warnings
import zipfile
# Resolve the temp root so mkdtemp never returns a symlinked path.
# macOS /tmp is a symlink to /private/tmp and the bundled launchers reject
# symlinked roots; hardcoding /private/tmp broke every non-macOS runner.
tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "skills/cypress-debugger/scripts/download-cypress-reports.py"


MOCK_GH = """#!/usr/bin/python3
import json
import os
from pathlib import Path
import signal
import sys
import time

endpoint = sys.argv[-1]
log = Path(os.environ["MOCK_GH_LOG"])
with log.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")
mode = os.environ.get("MOCK_GH_MODE", "valid")
repository = {"id": 10, "full_name": "owner/repo"}
head_repository = dict(repository)
event = "push"
pull_requests = []
if mode == "fork":
    head_repository = {"id": 11, "full_name": "contributor/repo"}
if mode in {"pr-fork", "pr-target-fork"}:
    event = "pull_request" if mode == "pr-fork" else "pull_request_target"
    pull_requests = [{"head": {"repo": {"id": 11}}}]
if mode == "pr-same":
    event = "pull_request"
    pull_requests = [{"head": {"repo": {"id": 10}}}]
if mode == "missing-pr":
    event = "pull_request"
if mode == "bool-pr-id":
    event = "pull_request_target"
    pull_requests = [{"head": {"repo": {"id": True}}}]
if mode == "bool-repo-id":
    repository["id"] = True
    head_repository["id"] = True
if mode == "run-other-repo":
    repository = {"id": 12, "full_name": "owner/repo"}
    head_repository = dict(repository)
if mode == "timeout":
    child = os.fork()
    if child == 0:
        time.sleep(0.5)
        Path(os.environ["MOCK_GH_TIMEOUT_MARKER"]).write_text(
            "escaped",
            encoding="utf-8",
        )
        raise SystemExit(0)
    time.sleep(10)
if mode == "leader-exits-descendant-ignores-term":
    child = os.fork()
    if child == 0:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(0.5)
        Path(os.environ["MOCK_GH_TIMEOUT_MARKER"]).write_text(
            "escaped",
            encoding="utf-8",
        )
        os._exit(0)
    raise SystemExit(0)
if endpoint == "repos/owner/repo":
    resolved_repository = {"id": 10, "full_name": "owner/repo"}
    if mode == "resolved-name-mismatch":
        resolved_repository["full_name"] = "attacker/repo"
    print(json.dumps(resolved_repository))
    raise SystemExit(0)
if endpoint.endswith("/runs/123"):
    if mode == "duplicate-json-run":
        print('{"repository":{"id":10,"full_name":"owner/repo"},'
              '"repository":{"id":10,"full_name":"owner/repo"},'
              '"head_repository":{"id":10,"full_name":"owner/repo"},'
              '"event":"push","pull_requests":[]}')
        raise SystemExit(0)
    if mode == "nonfinite-run":
        print('{"repository":{"id":10,"full_name":"owner/repo"},'
              '"head_repository":{"id":10,"full_name":"owner/repo"},'
              '"event":NaN,"pull_requests":[]}')
        raise SystemExit(0)
    print(json.dumps({
        "repository": repository,
        "head_repository": head_repository,
        "event": event,
        "pull_requests": pull_requests,
    }))
    raise SystemExit(0)
if endpoint.endswith("/runs/123/artifacts?per_page=100"):
    artifacts = [
        {"id": 42, "name": "cypress-reports", "expired": False}
    ]
    if mode == "duplicate":
        artifacts.append(
            {"id": 43, "name": "cypress-reports", "expired": False}
        )
    if mode == "duplicate-json-list":
        print('{"total_count":1,"total_count":1,'
              '"artifacts":[{"id":42,"name":"cypress-reports","expired":false}]}')
        raise SystemExit(0)
    if mode == "nonfinite-list":
        print('{"total_count":NaN,'
              '"artifacts":[{"id":42,"name":"cypress-reports","expired":false}]}')
        raise SystemExit(0)
    if mode == "bool-total":
        total_count = True
    elif mode == "pagination-mismatch":
        total_count = len(artifacts) + 1
    else:
        total_count = len(artifacts)
    if mode == "bool-artifact-id":
        artifacts[0]["id"] = True
    print(json.dumps({"total_count": total_count, "artifacts": artifacts}))
    raise SystemExit(0)
if mode == "download-fail":
    print("download failed", file=sys.stderr)
    raise SystemExit(17)
race_target = os.environ.get("MOCK_GH_RACE_TARGET")
if race_target:
    Path("cypress/reports").symlink_to(
        race_target,
        target_is_directory=True,
    )
sys.stdout.buffer.write(Path(os.environ["MOCK_GH_ZIP"]).read_bytes())
"""


@contextmanager
def working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def load_helper():
    spec = importlib.util.spec_from_file_location(
        "download_cypress_reports",
        HELPER,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_zip(path: Path, *, symlink: bool = False) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("mochawesome.json", '{"stats":{"failures":1}}')
        archive.writestr("screenshots/failing.png", b"png")
        if symlink:
            info = zipfile.ZipInfo("screenshots/escape")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "../../outside")


def make_duplicate_zip(path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(
            path,
            "w",
            compression=zipfile.ZIP_STORED,
        ) as archive:
            archive.writestr("mochawesome.json", "{}")
            archive.writestr("mochawesome.json", '{"duplicate":true}')


def make_traversal_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("../outside", "escaped")


def make_encrypted_flag_zip(path: Path) -> None:
    make_zip(path)
    raw = bytearray(path.read_bytes())
    offset = 0
    while True:
        offset = raw.find(b"PK\x03\x04", offset)
        if offset < 0:
            break
        flags = int.from_bytes(raw[offset + 6 : offset + 8], "little") | 0x1
        raw[offset + 6 : offset + 8] = flags.to_bytes(2, "little")
        offset += 4
    offset = 0
    while True:
        offset = raw.find(b"PK\x01\x02", offset)
        if offset < 0:
            break
        flags = int.from_bytes(raw[offset + 8 : offset + 10], "little") | 0x1
        raw[offset + 8 : offset + 10] = flags.to_bytes(2, "little")
        offset += 4
    path.write_bytes(raw)


def make_compressed_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mochawesome.json", "A" * 4096)


def run_case(
    module,
    workspace: Path,
    gh: Path,
    archive: Path,
    log: Path,
    *,
    mode: str = "valid",
    race_target: Path | None = None,
    timeout_marker: Path | None = None,
) -> str | None:
    environment = {
        "MOCK_GH_LOG": str(log),
        "MOCK_GH_MODE": mode,
        "MOCK_GH_ZIP": str(archive),
        "GH_REPO": "attacker/ambient",
    }
    if race_target is not None:
        environment["MOCK_GH_RACE_TARGET"] = str(race_target)
    if timeout_marker is not None:
        environment["MOCK_GH_TIMEOUT_MARKER"] = str(timeout_marker)
    try:
        with working_directory(workspace):
            module.download_with_transport(
                "owner/repo",
                "123",
                str(gh),
                environment,
            )
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        return str(error)
    return None


def assert_no_staging(workspace: Path) -> None:
    cypress = workspace / "cypress"
    if cypress.is_dir():
        assert not list(cypress.glob(".reports.download.*"))


def read_calls(log: Path) -> list[list[str]]:
    import json

    calls = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
    ]
    for call in calls:
        assert call[:5] == [
            "api",
            "--hostname",
            "github.com",
            "--method",
            "GET",
        ], call
    return calls


def assert_final_sigkill_permission_error_accepts_proven_group_exit(module) -> None:
    original_killpg = module.os.killpg
    original_grace = module.TERMINATION_GRACE_SECONDS
    signals: list[int] = []

    state = {"final_attempted": False}

    class Process:
        pid = 12345
        poll_calls = 0

        def poll(self) -> None:
            self.poll_calls += 1
            return None

    process = Process()

    def killpg(_process_group: int, signal_number: int) -> None:
        signals.append(signal_number)
        if signal_number == 0 and state["final_attempted"]:
            raise ProcessLookupError
        if signal_number == module.signal.SIGKILL:
            state["final_attempted"] = True
            raise PermissionError("operation not permitted")

    try:
        module.os.killpg = killpg
        module.TERMINATION_GRACE_SECONDS = 0

        cleanup_error = module.terminate_process_group(process)
    finally:
        module.os.killpg = original_killpg
        module.TERMINATION_GRACE_SECONDS = original_grace

    assert [item for item in signals if item != 0] == [
        module.signal.SIGTERM,
        module.signal.SIGKILL,
    ]
    assert cleanup_error is None
    assert process.poll_calls >= 2


def assert_initial_sigterm_permission_still_attempts_sigkill(module) -> None:
    original_killpg = module.os.killpg
    original_grace = module.TERMINATION_GRACE_SECONDS
    signals: list[int] = []

    state = {"killed": False}

    class Process:
        pid = 12345
        poll_calls = 0

        def poll(self) -> None:
            self.poll_calls += 1
            return None

    process = Process()

    def killpg(_process_group: int, signal_number: int) -> None:
        signals.append(signal_number)
        if signal_number == 0 and state["killed"]:
            raise ProcessLookupError
        if signal_number == module.signal.SIGTERM:
            raise PermissionError("operation not permitted")
        if signal_number == module.signal.SIGKILL:
            state["killed"] = True

    try:
        module.os.killpg = killpg
        module.TERMINATION_GRACE_SECONDS = 0

        cleanup_error = module.terminate_process_group(process)
    finally:
        module.os.killpg = original_killpg
        module.TERMINATION_GRACE_SECONDS = original_grace

    assert [item for item in signals if item != 0] == [
        module.signal.SIGTERM,
        module.signal.SIGKILL,
    ]
    assert cleanup_error is None
    assert process.poll_calls >= 2


def assert_permission_denied_signals_report_a_live_process_group(module) -> None:
    original_killpg = module.os.killpg
    original_grace = module.TERMINATION_GRACE_SECONDS

    class Process:
        pid = 12345
        args = ("fixture",)

        def poll(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> None:
            return None

    def killpg(_process_group: int, signal_number: int) -> None:
        if signal_number in (module.signal.SIGTERM, module.signal.SIGKILL):
            raise PermissionError("operation not permitted")

    try:
        module.os.killpg = killpg
        module.TERMINATION_GRACE_SECONDS = 0
        cleanup_error = module.cleanup_process_group(Process())
    finally:
        module.os.killpg = original_killpg
        module.TERMINATION_GRACE_SECONDS = original_grace

    assert cleanup_error is not None
    assert "SIGTERM" in cleanup_error
    assert "SIGKILL" in cleanup_error
    assert "remained alive" in cleanup_error


def assert_final_sigkill_permission_error_reports_live_process_group(module) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        start_new_session=True,
    )
    original_killpg = module.os.killpg
    original_grace = module.TERMINATION_GRACE_SECONDS

    def deny_only_final_kill(_process_group: int, signal_number: int) -> None:
        if signal_number == module.signal.SIGKILL:
            raise PermissionError("operation not permitted")

    try:
        module.os.killpg = deny_only_final_kill
        module.TERMINATION_GRACE_SECONDS = 0.05

        cleanup_error = module.cleanup_process_group(process)
        assert cleanup_error is not None
        assert "remained alive" in cleanup_error
        assert process.poll() is None
    finally:
        module.os.killpg = original_killpg
        module.TERMINATION_GRACE_SECONDS = original_grace
        try:
            original_killpg(process.pid, module.signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def assert_cleanup_timeout_preserves_original_run_bounded_diagnostic(module) -> None:
    original_cleanup = module.cleanup_process_group
    original_timeout = module.COMMAND_TIMEOUT_SECONDS
    cleanup_calls = 0
    try:
        module.COMMAND_TIMEOUT_SECONDS = 0

        def cleanup_timeout(process) -> None:
            nonlocal cleanup_calls
            cleanup_calls += 1
            if cleanup_calls == 1:
                raise subprocess.TimeoutExpired(process.args, 0)
            try:
                os.killpg(process.pid, module.signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
            return None

        module.cleanup_process_group = cleanup_timeout
        try:
            module.run_bounded(
                sys.executable,
                ["-c", "import time; time.sleep(1)"],
                environment={"PATH": "/usr/bin:/bin"},
                stdout_fd=None,
                stdout_limit=1024,
            )
        except ValueError as error:
            message = str(error)
            assert "gh command timed out" in message
            assert "cleanup failed" in message
            assert message.count("cleanup failed") == 1
            assert cleanup_calls == 1
        else:
            raise AssertionError("timed-out gh command must fail")
    finally:
        module.cleanup_process_group = original_cleanup
        module.COMMAND_TIMEOUT_SECONDS = original_timeout


def assert_nonzero_leader_with_live_group_attempts_cleanup(module) -> None:
    original_cleanup = module.cleanup_process_group
    cleanup_calls = 0
    try:
        def cleanup(process) -> str:
            nonlocal cleanup_calls
            cleanup_calls += 1
            try:
                os.killpg(process.pid, module.signal.SIGKILL)
            except ProcessLookupError:
                pass
            return "process group remained alive after leader exit"

        module.cleanup_process_group = cleanup
        try:
            module.run_bounded(
                sys.executable,
                [
                    "-c",
                    "import os, sys, time\n"
                    "if os.fork() == 0:\n"
                    "    os.close(1)\n"
                    "    os.close(2)\n"
                    "    time.sleep(5)\n"
                    "    sys.exit(0)\n"
                    "sys.stderr.write('leader failed\\n')\n"
                    "sys.exit(7)\n",
                ],
                environment={"PATH": "/usr/bin:/bin"},
                stdout_fd=None,
                stdout_limit=1024,
            )
        except ValueError as error:
            message = str(error)
            assert "gh command failed with exit 7" in message
            assert "leader failed" in message
            assert "cleanup failed" in message
            assert cleanup_calls == 1
        else:
            raise AssertionError("nonzero leader must fail")
    finally:
        module.cleanup_process_group = original_cleanup


def assert_zero_leader_with_live_group_fails_closed(module) -> None:
    original_cleanup = module.cleanup_process_group
    cleanup_calls = 0
    with tempfile.TemporaryDirectory(prefix="e2e-cypress-live-child-") as raw:
        marker = Path(raw) / "ready"
        try:
            def cleanup(process) -> str:
                nonlocal cleanup_calls
                cleanup_calls += 1
                try:
                    os.killpg(process.pid, module.signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return "process group remained alive after leader exit"

            module.cleanup_process_group = cleanup
            try:
                module.run_bounded(
                    sys.executable,
                    [
                        "-c",
                        "import os, sys, time\n"
                        "marker = sys.argv[1]\n"
                        "if os.fork() == 0:\n"
                        "    open(marker, 'w').close()\n"
                        "    os.close(1)\n"
                        "    os.close(2)\n"
                        "    time.sleep(5)\n"
                        "    sys.exit(0)\n"
                        "while not os.path.exists(marker):\n"
                        "    time.sleep(0.01)\n"
                        "print('ok')\n",
                        str(marker),
                    ],
                    environment={"PATH": "/usr/bin:/bin"},
                    stdout_fd=None,
                    stdout_limit=1024,
                )
            except ValueError as error:
                message = str(error)
                assert "command left live descendants" in message
                assert message.count("cleanup failed") == 1
                assert cleanup_calls == 1
            else:
                raise AssertionError("zero leader with live descendants must fail")
        finally:
            module.cleanup_process_group = original_cleanup


def run_case_with_watchdog(
    helper: Path,
    workspace: Path,
    gh: Path,
    archive: Path,
    log: Path,
    *,
    watchdog_seconds: float = 20,
) -> subprocess.CompletedProcess[str]:
    driver = (
        "import importlib.util, os, sys\n"
        "from pathlib import Path\n"
        "helper, workspace, gh, archive, log = sys.argv[1:]\n"
        "spec = importlib.util.spec_from_file_location('download_cypress_reports', helper)\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "assert spec.loader is not None\n"
        "spec.loader.exec_module(module)\n"
        "module.COMMAND_TIMEOUT_SECONDS = 0.05\n"
        "os.chdir(workspace)\n"
        "module.download_with_transport('owner/repo', '123', gh, {\n"
        "    'MOCK_GH_LOG': log,\n"
        "    'MOCK_GH_MODE': 'timeout',\n"
        "    'MOCK_GH_ZIP': archive,\n"
        "    'MOCK_GH_TIMEOUT_MARKER': str(Path(workspace) / 'escaped'),\n"
        "})\n"
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            driver,
            str(helper),
            str(workspace),
            str(gh),
            str(archive),
            str(log),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=watchdog_seconds,
        check=False,
    )


def main() -> None:
    module = load_helper()
    assert module.MAX_ARCHIVE_BYTES == 512 * 1024 * 1024
    assert module.MIN_DISK_HEADROOM_BYTES == 64 * 1024 * 1024
    # Tiny fixtures should exercise the policy without requiring production-
    # sized free-space reserves on a contributor machine.
    module.MAX_ARCHIVE_BYTES = 1024 * 1024
    module.MIN_DISK_HEADROOM_BYTES = 0
    assert_final_sigkill_permission_error_accepts_proven_group_exit(module)
    assert_initial_sigterm_permission_still_attempts_sigkill(module)
    assert_permission_denied_signals_report_a_live_process_group(module)
    assert_final_sigkill_permission_error_reports_live_process_group(module)
    assert_cleanup_timeout_preserves_original_run_bounded_diagnostic(module)
    assert_nonzero_leader_with_live_group_attempts_cleanup(module)
    assert_zero_leader_with_live_group_fails_closed(module)
    parsed = module.parse_args(["--repo", "owner/repo", "123"])
    assert parsed.repo == "owner/repo"
    assert parsed.run_id == "123"
    assert module.validated_repository_slug("owner/repo") == "owner/repo"
    for valid_slug in (
        "owner/.github",
        "owner/A-",
        "owner/repo_",
    ):
        assert module.validated_repository_slug(valid_slug) == valid_slug
    for invalid_slug in (
        "",
        "owner",
        "/repo",
        "owner/",
        "-owner/repo",
        "owner-/repo",
        "owner/repo/name",
        "owner/../repo",
        "owner/.",
        "owner/..",
        "owner/%2e%2e",
        "owner/repo\nname",
        "owner/.git",
        "owner/repo.git",
        "owner/repo.GIT",
        "ownér/repo",
    ):
        try:
            module.validated_repository_slug(invalid_slug)
        except ValueError as error:
            assert "strict owner/repo slug" in str(error)
        else:
            raise AssertionError(f"unsafe repository slug accepted: {invalid_slug!r}")

    original_supports_dir_fd = module.os.supports_dir_fd
    module.os.supports_dir_fd = set()
    try:
        try:
            module.require_secure_descriptor_support()
        except ValueError as error:
            assert "descriptor-relative no-follow" in str(error)
        else:
            raise AssertionError("missing descriptor APIs must fail closed")
    finally:
        module.os.supports_dir_fd = original_supports_dir_fd

    with tempfile.TemporaryDirectory(
        prefix="e2e-cypress-download-contract-",
    ) as temp_dir:
        temp = Path(temp_dir)
        gh = temp / "mock-gh"
        gh.write_text(MOCK_GH, encoding="utf-8")
        gh.chmod(0o755)
        valid_zip = temp / "valid.zip"
        make_zip(valid_zip)

        valid_workspace = temp / "valid-workspace"
        valid_workspace.mkdir()
        log = temp / "valid.log"
        error = run_case(module, valid_workspace, gh, valid_zip, log)
        assert error is None, error
        assert (
            valid_workspace / "cypress/reports/mochawesome.json"
        ).read_text(encoding="utf-8") == '{"stats":{"failures":1}}'
        assert [call[-1] for call in read_calls(log)] == [
            "repos/owner/repo",
            "repos/owner/repo/actions/runs/123",
            "repos/owner/repo/actions/runs/123/artifacts?per_page=100",
            "repos/owner/repo/actions/artifacts/42/zip",
        ]
        assert_no_staging(valid_workspace)

        watchdog_workspace = temp / "watchdog-timeout-workspace"
        watchdog_workspace.mkdir()
        watchdog_result = run_case_with_watchdog(
            HELPER,
            watchdog_workspace,
            gh,
            valid_zip,
            temp / "watchdog-timeout.log",
        )
        assert watchdog_result.returncode != 0
        assert "gh command timed out" in watchdog_result.stderr
        assert not (watchdog_workspace / "escaped").exists()
        assert_no_staging(watchdog_workspace)

        for mode, expected in (
            ("resolved-name-mismatch", "confirmed repository slug"),
            ("run-other-repo", "confirmed repository"),
            ("duplicate-json-run", "duplicate JSON key"),
            ("nonfinite-run", "non-finite JSON number"),
            ("bool-repo-id", "validated id/full_name"),
            ("duplicate-json-list", "duplicate JSON key"),
            ("nonfinite-list", "non-finite JSON number"),
            ("bool-total", "validated artifacts/total_count"),
            ("pagination-mismatch", "paginated or inconsistent"),
            ("bool-artifact-id", "exactly one unexpired"),
        ):
            workspace = temp / f"{mode}-workspace"
            workspace.mkdir()
            error = run_case(
                module,
                workspace,
                gh,
                valid_zip,
                temp / f"{mode}.log",
                mode=mode,
            )
            assert error is not None and expected in error, (mode, error)
            assert not (workspace / "cypress/reports").exists()
            assert_no_staging(workspace)

        outside = temp / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("unchanged", encoding="utf-8")
        linked_workspace = temp / "linked-workspace"
        (linked_workspace / "cypress").mkdir(parents=True)
        (linked_workspace / "cypress/reports").symlink_to(
            outside,
            target_is_directory=True,
        )
        linked_log = temp / "linked.log"
        error = run_case(
            module,
            linked_workspace,
            gh,
            valid_zip,
            linked_log,
        )
        assert error is not None and "refusing symlink" in error
        assert not linked_log.exists(), "unsafe destination must fail before gh"
        assert sentinel.read_text(encoding="utf-8") == "unchanged"

        parent_link_workspace = temp / "parent-link-workspace"
        parent_link_workspace.mkdir()
        (parent_link_workspace / "cypress").symlink_to(
            outside,
            target_is_directory=True,
        )
        parent_log = temp / "parent-link.log"
        error = run_case(
            module,
            parent_link_workspace,
            gh,
            valid_zip,
            parent_log,
        )
        assert error is not None
        assert not parent_log.exists(), "symlinked parent must fail before gh"

        for mode, expected in (
            ("fork", "forked repository run"),
            ("pr-fork", "forked pull request run"),
            ("pr-target-fork", "forked pull request run"),
            ("missing-pr", "no pull request identity"),
            ("bool-pr-id", "forked pull request run"),
        ):
            workspace = temp / f"{mode}-workspace"
            workspace.mkdir()
            case_log = temp / f"{mode}.log"
            error = run_case(
                module,
                workspace,
                gh,
                valid_zip,
                case_log,
                mode=mode,
            )
            assert error is not None and expected in error
            assert [call[-1] for call in read_calls(case_log)] == [
                "repos/owner/repo",
                "repos/owner/repo/actions/runs/123",
            ]
            assert not (workspace / "cypress/reports").exists()
            assert_no_staging(workspace)

        pr_same_workspace = temp / "pr-same-workspace"
        pr_same_workspace.mkdir()
        error = run_case(
            module,
            pr_same_workspace,
            gh,
            valid_zip,
            temp / "pr-same.log",
            mode="pr-same",
        )
        assert error is None, error
        assert (pr_same_workspace / "cypress/reports/mochawesome.json").is_file()
        assert_no_staging(pr_same_workspace)

        timeout_workspace = temp / "timeout-workspace"
        timeout_workspace.mkdir()
        timeout_marker = temp / "timeout-child-escaped"
        original_timeout = module.COMMAND_TIMEOUT_SECONDS
        module.COMMAND_TIMEOUT_SECONDS = 0.1
        try:
            error = run_case(
                module,
                timeout_workspace,
                gh,
                valid_zip,
                temp / "timeout.log",
                mode="timeout",
                timeout_marker=timeout_marker,
            )
        finally:
            module.COMMAND_TIMEOUT_SECONDS = original_timeout
        assert error is not None and "timed out" in error, error
        assert "cleanup failed" not in error
        assert not (timeout_workspace / "cypress/reports").exists()
        assert_no_staging(timeout_workspace)

        descendant_workspace = temp / "leader-exit-descendant-workspace"
        descendant_workspace.mkdir()
        descendant_marker = temp / "leader-exit-descendant-escaped"
        original_timeout = module.COMMAND_TIMEOUT_SECONDS
        original_grace = module.TERMINATION_GRACE_SECONDS
        module.COMMAND_TIMEOUT_SECONDS = 0.1
        module.TERMINATION_GRACE_SECONDS = 0.05
        try:
            error = run_case(
                module,
                descendant_workspace,
                gh,
                valid_zip,
                temp / "leader-exit-descendant.log",
                mode="leader-exits-descendant-ignores-term",
                timeout_marker=descendant_marker,
            )
        finally:
            module.COMMAND_TIMEOUT_SECONDS = original_timeout
            module.TERMINATION_GRACE_SECONDS = original_grace
        assert error is not None and "timed out" in error
        assert "cleanup failed" not in error
        assert not (descendant_workspace / "cypress/reports").exists()
        assert_no_staging(descendant_workspace)

        duplicate_workspace = temp / "duplicate-workspace"
        duplicate_workspace.mkdir()
        error = run_case(
            module,
            duplicate_workspace,
            gh,
            valid_zip,
            temp / "duplicate.log",
            mode="duplicate",
        )
        assert error is not None and "exactly one unexpired" in error
        assert not (duplicate_workspace / "cypress/reports").exists()
        assert_no_staging(duplicate_workspace)

        failed_workspace = temp / "failed-workspace"
        failed_workspace.mkdir()
        error = run_case(
            module,
            failed_workspace,
            gh,
            valid_zip,
            temp / "failed.log",
            mode="download-fail",
        )
        assert error is not None and "exit 17" in error
        assert not (failed_workspace / "cypress/reports").exists()
        assert_no_staging(failed_workspace)

        malicious_zip = temp / "symlink.zip"
        make_zip(malicious_zip, symlink=True)
        malicious_workspace = temp / "malicious-workspace"
        malicious_workspace.mkdir()
        error = run_case(
            module,
            malicious_workspace,
            gh,
            malicious_zip,
            temp / "malicious.log",
        )
        assert error is not None and "symlink ZIP member is forbidden" in error
        assert not (malicious_workspace / "cypress/reports").exists()
        assert sentinel.read_text(encoding="utf-8") == "unchanged"
        assert_no_staging(malicious_workspace)

        for label, factory, expected in (
            ("duplicate-member", make_duplicate_zip, "duplicate ZIP member"),
            ("traversal", make_traversal_zip, "traversing or empty"),
            ("encrypted", make_encrypted_flag_zip, "encrypted ZIP member"),
        ):
            archive = temp / f"{label}.zip"
            factory(archive)
            workspace = temp / f"{label}-workspace"
            workspace.mkdir()
            error = run_case(
                module,
                workspace,
                gh,
                archive,
                temp / f"{label}.log",
            )
            assert error is not None and expected in error, (label, error)
            assert not (workspace / "cypress/reports").exists()
            assert_no_staging(workspace)

        race_workspace = temp / "race-workspace"
        race_workspace.mkdir()
        error = run_case(
            module,
            race_workspace,
            gh,
            valid_zip,
            temp / "race.log",
            race_target=outside,
        )
        assert error is not None and "refusing symlink" in error
        assert (race_workspace / "cypress/reports").is_symlink()
        assert sentinel.read_text(encoding="utf-8") == "unchanged"
        assert_no_staging(race_workspace)

        bounded_workspace = temp / "bounded-workspace"
        bounded_workspace.mkdir()
        original_limit = module.MAX_ARCHIVE_BYTES
        module.MAX_ARCHIVE_BYTES = 8
        try:
            error = run_case(
                module,
                bounded_workspace,
                gh,
                valid_zip,
                temp / "bounded.log",
            )
        finally:
            module.MAX_ARCHIVE_BYTES = original_limit
        assert error is not None and "byte limit" in error
        assert not (bounded_workspace / "cypress/reports").exists()
        assert_no_staging(bounded_workspace)

        for attribute, limit, expected in (
            ("MAX_ENTRIES", 1, "entries"),
            ("MAX_EXPANDED_BYTES", 8, "expanded-byte limit"),
            ("MAX_MEMBER_BYTES", 8, "per-entry byte limit"),
        ):
            workspace = temp / f"{attribute.lower()}-workspace"
            workspace.mkdir()
            original = getattr(module, attribute)
            setattr(module, attribute, limit)
            try:
                error = run_case(
                    module,
                    workspace,
                    gh,
                    valid_zip,
                    temp / f"{attribute.lower()}.log",
                )
            finally:
                setattr(module, attribute, original)
            assert error is not None and expected in error, (attribute, error)
            assert not (workspace / "cypress/reports").exists()
            assert_no_staging(workspace)

        compressed_zip = temp / "compressed.zip"
        make_compressed_zip(compressed_zip)
        ratio_workspace = temp / "ratio-workspace"
        ratio_workspace.mkdir()
        original_ratio = module.MAX_COMPRESSION_RATIO
        module.MAX_COMPRESSION_RATIO = 2
        try:
            error = run_case(
                module,
                ratio_workspace,
                gh,
                compressed_zip,
                temp / "ratio.log",
            )
        finally:
            module.MAX_COMPRESSION_RATIO = original_ratio
        assert error is not None and "compression-ratio limit" in error
        assert not (ratio_workspace / "cypress/reports").exists()
        assert_no_staging(ratio_workspace)

        extraction_timeout_workspace = temp / "extraction-timeout-workspace"
        extraction_timeout_workspace.mkdir()
        original_extraction_timeout = module.EXTRACTION_TIMEOUT_SECONDS
        module.EXTRACTION_TIMEOUT_SECONDS = 0
        try:
            error = run_case(
                module,
                extraction_timeout_workspace,
                gh,
                valid_zip,
                temp / "extraction-timeout.log",
            )
        finally:
            module.EXTRACTION_TIMEOUT_SECONDS = original_extraction_timeout
        assert error is not None and "extraction timed out" in error
        assert not (extraction_timeout_workspace / "cypress/reports").exists()
        assert_no_staging(extraction_timeout_workspace)

        download_headroom_workspace = temp / "download-headroom-workspace"
        download_headroom_workspace.mkdir()
        original_headroom = module.require_disk_headroom
        module.require_disk_headroom = (
            lambda *_args, **_kwargs: module.fail("insufficient disk headroom")
        )
        try:
            error = run_case(
                module,
                download_headroom_workspace,
                gh,
                valid_zip,
                temp / "download-headroom.log",
            )
        finally:
            module.require_disk_headroom = original_headroom
        assert error is not None and "insufficient disk headroom" in error
        assert not (download_headroom_workspace / "cypress/reports").exists()
        assert_no_staging(download_headroom_workspace)

        publication_headroom_workspace = temp / "publication-headroom-workspace"
        publication_headroom_workspace.mkdir()
        headroom_calls = 0

        def fail_publication_headroom(*args, **kwargs):
            nonlocal headroom_calls
            headroom_calls += 1
            if headroom_calls == 3:
                module.fail("insufficient disk headroom before artifact publication")

        module.require_disk_headroom = fail_publication_headroom
        try:
            error = run_case(
                module,
                publication_headroom_workspace,
                gh,
                valid_zip,
                temp / "publication-headroom.log",
            )
        finally:
            module.require_disk_headroom = original_headroom
        assert headroom_calls == 3
        assert error is not None and "artifact publication" in error
        assert not (publication_headroom_workspace / "cypress/reports").exists()
        assert_no_staging(publication_headroom_workspace)

        trusted_workspace = temp / "trusted-workspace"
        trusted_workspace.mkdir()
        local_gh = trusted_workspace / "gh"
        local_gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        local_gh.chmod(0o755)
        original_candidates = module.GH_CANDIDATES
        original_prefixes = module.TRUSTED_GH_PREFIXES
        module.GH_CANDIDATES = (str(local_gh),)
        module.TRUSTED_GH_PREFIXES = (str(trusted_workspace),)
        previous_path = os.environ.get("PATH")
        os.environ["PATH"] = str(trusted_workspace)
        try:
            with working_directory(trusted_workspace):
                try:
                    module.resolve_gh()
                except ValueError as error:
                    assert "repository-controlled" in str(error)
                else:
                    raise AssertionError("repository-controlled gh must be rejected")
        finally:
            module.GH_CANDIDATES = original_candidates
            module.TRUSTED_GH_PREFIXES = original_prefixes
            if previous_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = previous_path

        ambient_root = temp / "ambient"
        ambient_root.mkdir()
        ambient_gh = ambient_root / "gh"
        ambient_marker = temp / "ambient-executed"
        ambient_gh.write_text(
            f"#!/bin/sh\n: > {ambient_marker}\nexit 0\n",
            encoding="utf-8",
        )
        ambient_gh.chmod(0o755)
        fixed_root = temp / "fixed"
        fixed_root.mkdir(mode=0o700)
        fixed_gh = fixed_root / "gh"
        fixed_gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fixed_gh.chmod(0o755)
        original_candidates = module.GH_CANDIDATES
        original_prefixes = module.TRUSTED_GH_PREFIXES
        module.GH_CANDIDATES = (str(fixed_gh),)
        module.TRUSTED_GH_PREFIXES = (str(fixed_root),)
        previous_path = os.environ.get("PATH")
        os.environ["PATH"] = str(ambient_root)
        try:
            assert module.resolve_gh() == str(fixed_gh)
        finally:
            module.GH_CANDIDATES = original_candidates
            module.TRUSTED_GH_PREFIXES = original_prefixes
            if previous_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = previous_path
        assert not ambient_marker.exists(), "ambient PATH gh must never execute"

        os.environ["PROJECT_ATTACKER_ENV"] = "must-not-pass"
        os.environ["GH_REPO"] = "attacker/ambient"
        os.environ["GH_HOST"] = "attacker.invalid"
        os.environ["HTTPS_PROXY"] = "https://attacker.invalid"
        os.environ["SSL_CERT_FILE"] = str(temp / "attacker-ca.pem")
        try:
            environment = module.gh_environment()
        finally:
            os.environ.pop("PROJECT_ATTACKER_ENV")
            os.environ.pop("GH_REPO")
            os.environ.pop("GH_HOST")
            os.environ.pop("HTTPS_PROXY")
            os.environ.pop("SSL_CERT_FILE")
        assert "PROJECT_ATTACKER_ENV" not in environment
        assert "GH_REPO" not in environment
        assert "GH_HOST" not in environment
        assert "HTTPS_PROXY" not in environment
        assert "SSL_CERT_FILE" not in environment

        home_workspace = temp / "home-workspace"
        home_workspace.mkdir()
        previous_home = os.environ.get("HOME")
        os.environ["HOME"] = str(home_workspace)
        try:
            with working_directory(home_workspace):
                try:
                    module.gh_environment()
                except ValueError as error:
                    assert "repository-controlled HOME" in str(error)
                else:
                    raise AssertionError("workspace-contained HOME must fail closed")
        finally:
            if previous_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = previous_home

        canonical_home_link = temp / "home-link"
        canonical_home_target = temp / "home-target"
        canonical_cwd = temp / "canonical-cwd"
        canonical_home_target.mkdir()
        canonical_cwd.mkdir()
        canonical_home_link.symlink_to(canonical_home_target, target_is_directory=True)
        os.environ["HOME"] = str(canonical_home_link)
        try:
            with working_directory(canonical_cwd):
                environment = module.gh_environment()
        finally:
            if previous_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = previous_home
        assert environment["HOME"] == str(canonical_home_target)

        lexical_workspace = temp / "lexical-home-workspace"
        lexical_workspace.mkdir()
        lexical_home_link = lexical_workspace / "home"
        lexical_home_link.symlink_to(
            canonical_home_target,
            target_is_directory=True,
        )
        os.environ["HOME"] = str(lexical_home_link)
        try:
            with working_directory(lexical_workspace):
                try:
                    module.gh_environment()
                except ValueError as error:
                    assert "repository-controlled HOME" in str(error)
                else:
                    raise AssertionError(
                        "workspace-contained HOME symlink must fail closed"
                    )
        finally:
            if previous_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = previous_home

    skill = (ROOT / "skills/cypress-debugger/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "download-cypress-reports.py" in skill
    assert "--repo" in skill
    assert "gh run download" not in skill
    assert "cypress-reports" in skill
    assert "forked" in skill
    print("Cypress artifact download safety: pass")


if __name__ == "__main__":
    main()
