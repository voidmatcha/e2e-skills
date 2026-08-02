#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Focused adversarial tests for the Playwright CI artifact downloader."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import warnings
import zipfile
# Resolve the temp root so mkdtemp never returns a symlinked path.
# macOS /tmp is a symlink to /private/tmp and the bundled launchers reject
# symlinked roots; hardcoding /private/tmp broke every non-macOS runner.
tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())


ROOT = Path(__file__).resolve().parents[2]
HELPER = (
    ROOT
    / "skills/playwright-debugger/scripts/download-playwright-report.py"
)
PYTHON = "/usr/bin/python3"


MOCK_GH = """#!/usr/bin/python3
import json
import os
from pathlib import Path
import signal
import sys
import time

env_dump = os.environ.get("MOCK_GH_ENV_DUMP")
if env_dump:
    Path(env_dump).write_text(
        json.dumps(dict(os.environ), sort_keys=True),
        encoding="utf-8",
    )
marker = os.environ.get("MOCK_GH_MARKER")
if marker:
    Path(marker).write_text("called", encoding="utf-8")
try:
    hostname = sys.argv[sys.argv.index("--hostname") + 1]
except (ValueError, IndexError):
    print("missing explicit hostname", file=sys.stderr)
    raise SystemExit(91)
if hostname != "github.com":
    print("unexpected hostname", file=sys.stderr)
    raise SystemExit(92)
endpoint = sys.argv[-1]
endpoint_log = os.environ.get("MOCK_GH_ENDPOINT_LOG")
if endpoint_log:
    with Path(endpoint_log).open("a", encoding="utf-8") as stream:
        stream.write(endpoint + "\\n")
sleep_seconds = os.environ.get("MOCK_GH_SLEEP")
if sleep_seconds:
    time.sleep(float(sleep_seconds))
descendant_marker = os.environ.get("MOCK_GH_DESCENDANT_MARKER")
if descendant_marker:
    child = os.fork()
    if child == 0:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(0.5)
        Path(descendant_marker).write_text("escaped", encoding="utf-8")
        os._exit(0)
    raise SystemExit(0)
if endpoint == "repos/owner/repo":
    raw_path = os.environ.get("MOCK_GH_REPOSITORY_JSON")
    if raw_path:
        sys.stdout.buffer.write(Path(raw_path).read_bytes())
    else:
        print(json.dumps({"id": 10, "full_name": "owner/repo"}))
    raise SystemExit(0)
if "/runs/" in endpoint and endpoint.endswith("artifacts?per_page=100"):
    raw_path = os.environ.get("MOCK_GH_ARTIFACT_JSON")
    if raw_path:
        sys.stdout.buffer.write(Path(raw_path).read_bytes())
    else:
        print(json.dumps({
            "total_count": 1,
            "artifacts": [
                {"id": 42, "name": "playwright-report", "expired": False}
            ],
        }))
    raise SystemExit(0)
if "/actions/runs/" in endpoint:
    raw_path = os.environ.get("MOCK_GH_RUN_JSON")
    if raw_path:
        sys.stdout.buffer.write(Path(raw_path).read_bytes())
    else:
        forked = os.environ.get("MOCK_GH_FORK") == "1"
        pr_target_fork = os.environ.get("MOCK_GH_PR_TARGET_FORK") == "1"
        print(json.dumps({
            "repository": {"id": 10, "full_name": "owner/repo"},
            "head_repository": {
                "id": 11 if forked else 10,
                "full_name": "outsider/fork" if forked else "owner/repo",
            },
            "event": "pull_request_target" if pr_target_fork else "push",
            "pull_requests": ([{
                "head": {"repo": {
                    "id": 11 if pr_target_fork else 10,
                    "full_name": (
                        "outsider/fork" if pr_target_fork else "owner/repo"
                    ),
                }},
            }] if pr_target_fork else []),
        }))
    raise SystemExit(0)
if os.environ.get("MOCK_GH_FAIL") == "1":
    print("download failed", file=sys.stderr)
    raise SystemExit(17)
race_target = os.environ.get("MOCK_GH_RACE_TARGET")
if race_target:
    Path("playwright-report").symlink_to(
        race_target,
        target_is_directory=True,
    )
sys.stdout.buffer.write(Path(os.environ["MOCK_GH_ZIP"]).read_bytes())
"""

DRIVER = """
import importlib.util
from pathlib import Path
import sys

helper_path, gh_path, trusted_prefix, repository, run_id = sys.argv[1:]
spec = importlib.util.spec_from_file_location("playwright_artifact_helper", helper_path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
module.GH_CANDIDATES = (gh_path,)
module.TRUSTED_GH_PREFIXES = (trusted_prefix,)
module.GH_ENV_ALLOWLIST = module.GH_ENV_ALLOWLIST | frozenset({
    "MOCK_COMMAND_TIMEOUT",
    "MOCK_EXTRACTION_TIMEOUT",
    "MOCK_GH_ARTIFACT_JSON",
    "MOCK_GH_DESCENDANT_MARKER",
    "MOCK_GH_ENV_DUMP",
    "MOCK_GH_ENDPOINT_LOG",
    "MOCK_GH_FAIL",
    "MOCK_GH_FORK",
    "MOCK_GH_MARKER",
    "MOCK_GH_PR_TARGET_FORK",
    "MOCK_GH_RACE_TARGET",
    "MOCK_GH_REPOSITORY_JSON",
    "MOCK_GH_RUN_JSON",
    "MOCK_GH_SLEEP",
    "MOCK_GH_ZIP",
    "MOCK_MAX_ENTRIES",
    "MOCK_MAX_COMPRESSION_RATIO",
    "MOCK_MAX_EXPANDED_BYTES",
    "MOCK_MAX_MEMBER_EXPANDED_BYTES",
    "MOCK_MIN_FREE_SPACE_BYTES",
    "MOCK_TERMINATION_GRACE",
})
if "MOCK_COMMAND_TIMEOUT" in __import__("os").environ:
    module.COMMAND_TIMEOUT_SECONDS = float(
        __import__("os").environ["MOCK_COMMAND_TIMEOUT"]
    )
if "MOCK_EXTRACTION_TIMEOUT" in __import__("os").environ:
    module.EXTRACTION_TIMEOUT_SECONDS = float(
        __import__("os").environ["MOCK_EXTRACTION_TIMEOUT"]
    )
if "MOCK_TERMINATION_GRACE" in __import__("os").environ:
    module.TERMINATION_GRACE_SECONDS = float(
        __import__("os").environ["MOCK_TERMINATION_GRACE"]
    )
if "MOCK_MAX_ENTRIES" in __import__("os").environ:
    module.MAX_ENTRIES = int(__import__("os").environ["MOCK_MAX_ENTRIES"])
if "MOCK_MAX_COMPRESSION_RATIO" in __import__("os").environ:
    module.MAX_COMPRESSION_RATIO = int(
        __import__("os").environ["MOCK_MAX_COMPRESSION_RATIO"]
    )
if "MOCK_MAX_EXPANDED_BYTES" in __import__("os").environ:
    module.MAX_EXPANDED_BYTES = int(
        __import__("os").environ["MOCK_MAX_EXPANDED_BYTES"]
    )
if "MOCK_MAX_MEMBER_EXPANDED_BYTES" in __import__("os").environ:
    module.MAX_MEMBER_EXPANDED_BYTES = int(
        __import__("os").environ["MOCK_MAX_MEMBER_EXPANDED_BYTES"]
    )
if "MOCK_MIN_FREE_SPACE_BYTES" in __import__("os").environ:
    module.MIN_FREE_SPACE_BYTES = int(
        __import__("os").environ["MOCK_MIN_FREE_SPACE_BYTES"]
    )
raise SystemExit(module.main([f"--repo={repository}", run_id]))
"""


def make_zip(
    path: Path,
    *,
    symlink: bool = False,
    duplicate: bool = False,
    traversal: bool = False,
    compression: int = zipfile.ZIP_STORED,
    index_payload: str = "<title>Playwright report</title>",
) -> None:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        archive.writestr("index.html", index_payload)
        archive.writestr("data/trace.zip", b"trace")
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                archive.writestr("index.html", "duplicate")
        if traversal:
            archive.writestr("../escape", "outside")
        if symlink:
            info = zipfile.ZipInfo("data/escape")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "../../outside")


def make_encrypted_flag_zip(source: Path, destination: Path) -> None:
    payload = bytearray(source.read_bytes())
    local = payload.find(b"PK\x03\x04")
    central = payload.find(b"PK\x01\x02")
    assert local >= 0 and central >= 0
    local_flags = int.from_bytes(payload[local + 6 : local + 8], "little") | 0x1
    central_flags = int.from_bytes(
        payload[central + 8 : central + 10],
        "little",
    ) | 0x1
    payload[local + 6 : local + 8] = local_flags.to_bytes(2, "little")
    payload[central + 8 : central + 10] = central_flags.to_bytes(2, "little")
    destination.write_bytes(payload)


def run_helper(
    workspace: Path,
    gh: Path,
    trusted_prefix: Path,
    archive: Path,
    *,
    ambient_path: str | None = None,
    repository: str = "owner/repo",
    **extra_env: str,
) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "PATH": ambient_path or "/usr/bin:/bin",
        "MOCK_GH_ZIP": str(archive),
        **extra_env,
    }
    return subprocess.run(
        [
            PYTHON,
            "-c",
            DRIVER,
            str(HELPER),
            str(gh),
            str(trusted_prefix),
            repository,
            "123456",
        ],
        cwd=workspace,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        check=False,
    )


def assert_no_staging(workspace: Path) -> None:
    assert not list(workspace.glob(".playwright-report.download.*"))


def assert_descriptor_guard_is_live() -> None:
    spec = importlib.util.spec_from_file_location(
        "playwright_artifact_descriptor_guard",
        HELPER,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    original = module.os.supports_dir_fd
    try:
        module.os.supports_dir_fd = frozenset()
        try:
            module.require_secure_descriptor_support()
        except ValueError as error:
            assert "descriptor-relative no-follow APIs" in str(error)
        else:
            raise AssertionError("descriptor capability guard must fail closed")
    finally:
        module.os.supports_dir_fd = original


def main() -> None:
    assert_descriptor_guard_is_live()
    with tempfile.TemporaryDirectory(
        prefix="e2e-playwright-download-contract-",
    ) as temp_dir:
        temp = Path(temp_dir)
        mock_bin = temp / "bin"
        mock_bin.mkdir()
        gh = mock_bin / "gh"
        gh.write_text(MOCK_GH, encoding="utf-8")
        gh.chmod(0o755)
        valid_zip = temp / "valid.zip"
        make_zip(valid_zip)

        valid_workspace = temp / "valid-workspace"
        valid_workspace.mkdir()
        environment_dump = temp / "gh-environment.json"
        valid_endpoint_log = temp / "valid-endpoints.log"
        result = run_helper(
            valid_workspace,
            gh,
            temp,
            valid_zip,
            MOCK_GH_ENV_DUMP=str(environment_dump),
            MOCK_GH_ENDPOINT_LOG=str(valid_endpoint_log),
            GH_TOKEN="preserved-token",
            GH_HOST="attacker.invalid",
            GH_ENTERPRISE_TOKEN="must-not-reach-gh",
            GH_CONFIG_DIR=str(valid_workspace / ".gh"),
            HTTPS_PROXY="https://attacker.invalid",
            SSL_CERT_FILE=str(temp / "attacker-ca.pem"),
            XDG_CONFIG_HOME=str(valid_workspace / ".config"),
            LEAK_ME="must-not-reach-gh",
        )
        assert result.returncode == 0, result.stderr
        assert (
            valid_workspace / "playwright-report/index.html"
        ).read_text(encoding="utf-8") == "<title>Playwright report</title>"
        child_environment = __import__("json").loads(
            environment_dump.read_text(encoding="utf-8")
        )
        assert child_environment["GH_TOKEN"] == "preserved-token"
        assert "LEAK_ME" not in child_environment
        for forbidden in (
            "GH_HOST",
            "GH_ENTERPRISE_TOKEN",
            "GH_CONFIG_DIR",
            "HTTPS_PROXY",
            "SSL_CERT_FILE",
            "XDG_CONFIG_HOME",
        ):
            assert forbidden not in child_environment
        assert child_environment["PATH"].startswith("/usr/bin:/bin:")
        assert child_environment["GH_PROMPT_DISABLED"] == "1"
        assert valid_endpoint_log.read_text(encoding="utf-8").splitlines() == [
            "repos/owner/repo",
            "repos/owner/repo/actions/runs/123456",
            (
                "repos/owner/repo/actions/runs/123456/"
                "artifacts?per_page=100"
            ),
            "repos/owner/repo/actions/artifacts/42/zip",
        ]
        assert_no_staging(valid_workspace)

        ambient_workspace = temp / "ambient-repository-workspace"
        (ambient_workspace / ".git").mkdir(parents=True)
        (ambient_workspace / ".git/config").write_text(
            "\n".join(
                [
                    '[remote "origin"]',
                    "url = https://github.com/attacker/ambient.git",
                ]
            ),
            encoding="utf-8",
        )
        ambient_endpoint_log = temp / "ambient-repository-endpoints.log"
        result = run_helper(
            ambient_workspace,
            gh,
            temp,
            valid_zip,
            GH_REPO="attacker/environment",
            MOCK_GH_ENDPOINT_LOG=str(ambient_endpoint_log),
        )
        assert result.returncode == 0, result.stderr
        assert all(
            endpoint.startswith("repos/owner/repo")
            for endpoint in ambient_endpoint_log.read_text(
                encoding="utf-8"
            ).splitlines()
        ), "ambient checkout and GH_REPO must not select the repository"

        hostile_bin = temp / "hostile-bin"
        hostile_bin.mkdir()
        hostile_marker = temp / "ambient-gh-called"
        hostile_gh = hostile_bin / "gh"
        hostile_gh.write_text(
            "#!/bin/sh\nprintf called > \"$HOSTILE_MARKER\"\nexit 99\n",
            encoding="utf-8",
        )
        hostile_gh.chmod(0o755)
        fixed_path_workspace = temp / "fixed-path-workspace"
        fixed_path_workspace.mkdir()
        result = run_helper(
            fixed_path_workspace,
            gh,
            temp,
            valid_zip,
            ambient_path=f"{hostile_bin}:/usr/bin:/bin",
            HOSTILE_MARKER=str(hostile_marker),
        )
        assert result.returncode == 0, result.stderr
        assert not hostile_marker.exists(), "ambient PATH gh must never execute"

        outside = temp / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel"
        sentinel.write_text("unchanged", encoding="utf-8")
        linked_workspace = temp / "linked-workspace"
        linked_workspace.mkdir()
        (linked_workspace / "playwright-report").symlink_to(
            outside,
            target_is_directory=True,
        )
        marker = temp / "gh-called"
        result = run_helper(
            linked_workspace,
            gh,
            temp,
            valid_zip,
            MOCK_GH_MARKER=str(marker),
        )
        assert result.returncode != 0
        assert "refusing symlink" in result.stderr
        assert not marker.exists(), "unsafe destination must be rejected before gh"
        assert sentinel.read_text(encoding="utf-8") == "unchanged"

        race_workspace = temp / "race-workspace"
        race_workspace.mkdir()
        result = run_helper(
            race_workspace,
            gh,
            temp,
            valid_zip,
            MOCK_GH_RACE_TARGET=str(outside),
        )
        assert result.returncode != 0
        assert "refusing symlink" in result.stderr
        assert (race_workspace / "playwright-report").is_symlink()
        assert sentinel.read_text(encoding="utf-8") == "unchanged"
        assert_no_staging(race_workspace)

        failed_workspace = temp / "failed-workspace"
        failed_workspace.mkdir()
        result = run_helper(
            failed_workspace,
            gh,
            temp,
            valid_zip,
            MOCK_GH_FAIL="1",
        )
        assert result.returncode != 0
        assert "exit 17" in result.stderr
        assert not (failed_workspace / "playwright-report").exists()
        assert_no_staging(failed_workspace)

        malicious_zip = temp / "symlink.zip"
        make_zip(malicious_zip, symlink=True)
        malicious_workspace = temp / "malicious-workspace"
        malicious_workspace.mkdir()
        result = run_helper(
            malicious_workspace,
            gh,
            temp,
            malicious_zip,
        )
        assert result.returncode != 0
        assert "symlink ZIP member is forbidden" in result.stderr
        assert not (malicious_workspace / "playwright-report").exists()
        assert sentinel.read_text(encoding="utf-8") == "unchanged"
        assert_no_staging(malicious_workspace)

        project_gh = malicious_workspace / "gh"
        project_gh.write_text(MOCK_GH, encoding="utf-8")
        project_gh.chmod(0o755)
        result = run_helper(
            malicious_workspace,
            project_gh,
            malicious_workspace,
            valid_zip,
        )
        assert result.returncode != 0
        assert "project-controlled gh executable" in result.stderr

        insecure_prefix = temp / "insecure-prefix"
        insecure_prefix.mkdir(mode=0o777)
        insecure_prefix.chmod(0o777)
        insecure_gh = insecure_prefix / "gh"
        insecure_gh.write_text(MOCK_GH, encoding="utf-8")
        insecure_gh.chmod(0o755)
        insecure_workspace = temp / "insecure-workspace"
        insecure_workspace.mkdir()
        result = run_helper(
            insecure_workspace,
            insecure_gh,
            insecure_prefix,
            valid_zip,
        )
        assert result.returncode != 0
        assert "group/world-writable component" in result.stderr
        assert not (insecure_workspace / "playwright-report").exists()

        fork_workspace = temp / "fork-workspace"
        fork_workspace.mkdir()
        fork_endpoint_log = temp / "fork-endpoints.log"
        result = run_helper(
            fork_workspace,
            gh,
            temp,
            valid_zip,
            MOCK_GH_FORK="1",
            MOCK_GH_ENDPOINT_LOG=str(fork_endpoint_log),
        )
        assert result.returncode != 0
        assert "fork-origin run" in result.stderr
        assert fork_endpoint_log.read_text(encoding="utf-8").splitlines() == [
            "repos/owner/repo",
            "repos/owner/repo/actions/runs/123456",
        ], "fork origin must be rejected before artifact lookup/download"
        assert not (fork_workspace / "playwright-report").exists()
        assert_no_staging(fork_workspace)

        pr_fork_workspace = temp / "pr-fork-workspace"
        pr_fork_workspace.mkdir()
        result = run_helper(
            pr_fork_workspace,
            gh,
            temp,
            valid_zip,
            MOCK_GH_PR_TARGET_FORK="1",
        )
        assert result.returncode != 0
        assert "forked pull request run" in result.stderr
        assert not (pr_fork_workspace / "playwright-report").exists()
        assert_no_staging(pr_fork_workspace)

        wrong_repository_payload = temp / "wrong-consistent-repository.json"
        wrong_repository_payload.write_bytes(
            b'{"repository":{"id":20,"full_name":"attacker/repo"},'
            b'"head_repository":{"id":20,"full_name":"attacker/repo"},'
            b'"event":"push","pull_requests":[]}'
        )
        wrong_repository_workspace = temp / "wrong-consistent-repository-workspace"
        wrong_repository_workspace.mkdir()
        result = run_helper(
            wrong_repository_workspace,
            gh,
            temp,
            valid_zip,
            MOCK_GH_RUN_JSON=str(wrong_repository_payload),
        )
        assert result.returncode != 0
        assert "does not match the user-confirmed repository" in result.stderr
        assert not (wrong_repository_workspace / "playwright-report").exists()
        assert_no_staging(wrong_repository_workspace)

        for malformed_slug in (
            "owner",
            "owner/repo/extra",
            "../owner/repo",
            "owner/repo?ref=main",
            "owner/repo name",
            "-owner/repo",
            "owner/..",
        ):
            workspace = temp / (
                "malformed-slug-" + str(abs(hash(malformed_slug)))
            )
            workspace.mkdir()
            marker = workspace / "gh-called"
            result = run_helper(
                workspace,
                gh,
                temp,
                valid_zip,
                repository=malformed_slug,
                MOCK_GH_MARKER=str(marker),
            )
            assert result.returncode != 0, malformed_slug
            assert "explicit ASCII owner/repo slug" in result.stderr, (
                malformed_slug,
                result.stderr,
            )
            assert not marker.exists(), malformed_slug
            assert not (workspace / "playwright-report").exists()

        strict_payloads = {
            "duplicate-run": (
                b'{"repository":{"id":10,"full_name":"owner/repo"},'
                b'"repository":{"id":10,"full_name":"owner/repo"},'
                b'"head_repository":{"id":10,"full_name":"owner/repo"},'
                b'"event":"push","pull_requests":[]}',
                "duplicate JSON key",
                "run",
            ),
            "boolean-run-id": (
                b'{"repository":{"id":true,"full_name":"owner/repo"},'
                b'"head_repository":{"id":true,"full_name":"owner/repo"},'
                b'"event":"push","pull_requests":[]}',
                "validated id/full_name",
                "run",
            ),
            "duplicate-artifacts": (
                b'{"total_count":1,"artifacts":[],'
                b'"artifacts":[{"id":42,"name":"playwright-report",'
                b'"expired":false}]}',
                "duplicate JSON key",
                "artifact",
            ),
            "nonfinite-artifact": (
                b'{"total_count":1,"artifacts":[{"id":NaN,'
                b'"name":"playwright-report","expired":false}]}',
                "non-finite JSON number",
                "artifact",
            ),
            "boolean-artifact-id": (
                b'{"total_count":1,"artifacts":[{"id":true,'
                b'"name":"playwright-report","expired":false}]}',
                "found 0",
                "artifact",
            ),
            "boolean-total-count": (
                b'{"total_count":true,"artifacts":[{"id":42,'
                b'"name":"playwright-report","expired":false}]}',
                "validated artifacts/total_count",
                "artifact",
            ),
            "pagination": (
                b'{"total_count":101,"artifacts":[{"id":42,'
                b'"name":"playwright-report","expired":false}]}',
                "paginated or inconsistent",
                "artifact",
            ),
        }
        for name, (payload, expected, payload_kind) in strict_payloads.items():
            payload_path = temp / f"{name}.json"
            payload_path.write_bytes(payload)
            workspace = temp / f"{name}-workspace"
            workspace.mkdir()
            extra = {
                (
                    "MOCK_GH_RUN_JSON"
                    if payload_kind == "run"
                    else "MOCK_GH_ARTIFACT_JSON"
                ): str(payload_path)
            }
            result = run_helper(workspace, gh, temp, valid_zip, **extra)
            assert result.returncode != 0, name
            assert expected in result.stderr, (name, result.stderr)
            assert not (workspace / "playwright-report").exists()
            assert_no_staging(workspace)

        duplicate_zip = temp / "duplicate.zip"
        make_zip(duplicate_zip, duplicate=True)
        traversal_zip = temp / "traversal.zip"
        make_zip(traversal_zip, traversal=True)
        encrypted_zip = temp / "encrypted.zip"
        make_encrypted_flag_zip(valid_zip, encrypted_zip)
        unsupported_zip = temp / "unsupported-compression.zip"
        make_zip(unsupported_zip, compression=zipfile.ZIP_BZIP2)
        compressed_zip = temp / "compressed.zip"
        make_zip(
            compressed_zip,
            compression=zipfile.ZIP_DEFLATED,
            index_payload="A" * 4096,
        )
        for name, archive, expected in (
            ("duplicate-zip", duplicate_zip, "duplicate ZIP member"),
            ("traversal-zip", traversal_zip, "traversing or empty ZIP member"),
            ("encrypted-zip", encrypted_zip, "encrypted ZIP member"),
            (
                "unsupported-compression",
                unsupported_zip,
                "unsupported ZIP compression method",
            ),
        ):
            workspace = temp / f"{name}-workspace"
            workspace.mkdir()
            result = run_helper(workspace, gh, temp, archive)
            assert result.returncode != 0, name
            assert expected in result.stderr, (name, result.stderr)
            assert not (workspace / "playwright-report").exists()
            assert_no_staging(workspace)

        bounded_cases = (
            ("entry-limit", {"MOCK_MAX_ENTRIES": "1"}, "entries"),
            (
                "expanded-limit",
                {"MOCK_MAX_EXPANDED_BYTES": "4"},
                "expanded-byte limit",
            ),
            (
                "member-limit",
                {"MOCK_MAX_MEMBER_EXPANDED_BYTES": "4"},
                "per-member expanded-byte limit",
            ),
            (
                "extraction-timeout",
                {"MOCK_EXTRACTION_TIMEOUT": "0"},
                "extraction timed out",
            ),
            (
                "disk-headroom",
                {"MOCK_MIN_FREE_SPACE_BYTES": str(10**30)},
                "insufficient free space",
            ),
        )
        for name, extra, expected in bounded_cases:
            workspace = temp / f"{name}-workspace"
            workspace.mkdir()
            result = run_helper(workspace, gh, temp, valid_zip, **extra)
            assert result.returncode != 0, name
            assert expected in result.stderr, (name, result.stderr)
            assert not (workspace / "playwright-report").exists()
            assert_no_staging(workspace)

        ratio_workspace = temp / "compression-ratio-workspace"
        ratio_workspace.mkdir()
        result = run_helper(
            ratio_workspace,
            gh,
            temp,
            compressed_zip,
            MOCK_MAX_COMPRESSION_RATIO="1",
        )
        assert result.returncode != 0
        assert "compression-ratio limit" in result.stderr
        assert not (ratio_workspace / "playwright-report").exists()
        assert_no_staging(ratio_workspace)

        timeout_workspace = temp / "command-timeout-workspace"
        timeout_workspace.mkdir()
        result = run_helper(
            timeout_workspace,
            gh,
            temp,
            valid_zip,
            MOCK_GH_SLEEP="2",
            MOCK_COMMAND_TIMEOUT="0.05",
        )
        assert result.returncode != 0
        assert "gh command timed out" in result.stderr
        assert not (timeout_workspace / "playwright-report").exists()
        assert_no_staging(timeout_workspace)

        descendant_workspace = temp / "leader-exit-descendant-workspace"
        descendant_workspace.mkdir()
        descendant_marker = temp / "leader-exit-descendant-escaped"
        result = run_helper(
            descendant_workspace,
            gh,
            temp,
            valid_zip,
            MOCK_GH_DESCENDANT_MARKER=str(descendant_marker),
            MOCK_COMMAND_TIMEOUT="0.05",
            MOCK_TERMINATION_GRACE="0.05",
        )
        assert result.returncode != 0
        assert "gh command timed out" in result.stderr
        time.sleep(0.6)
        assert not descendant_marker.exists(), (
            "SIGTERM-ignoring descendant escaped after its leader exited"
        )
        assert not (descendant_workspace / "playwright-report").exists()
        assert_no_staging(descendant_workspace)

        project_home_workspace = temp / "project-home-workspace"
        project_home_workspace.mkdir()
        result = run_helper(
            project_home_workspace,
            gh,
            temp,
            valid_zip,
            HOME=str(project_home_workspace),
        )
        assert result.returncode != 0
        assert "project-controlled HOME" in result.stderr
        assert not (project_home_workspace / "playwright-report").exists()

    skill = (ROOT / "skills/playwright-debugger/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "download-playwright-report.py" in skill
    assert '--repo "$REPO" "$RUN_ID"' in skill
    assert "do not infer the repository" in skill
    assert "gh run download" not in skill
    assert "same-user or privileged local process" in skill
    for readme_name in (
        "README.md",
        "README.ko.md",
        "README.ja.md",
        "README.zh-cn.md",
    ):
        readme = (ROOT / readme_name).read_text(encoding="utf-8")
        assert "gh run download" not in readme, (
            f"{readme_name} must describe the bounded gh api helper"
        )
    print("Playwright artifact download safety: pass")


if __name__ == "__main__":
    main()
