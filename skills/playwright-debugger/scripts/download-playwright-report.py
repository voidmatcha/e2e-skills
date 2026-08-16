#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Download one GitHub Actions artifact without giving gh an extraction path.

The archive is streamed from ``gh api`` into a private staging directory, then
validated and extracted with descriptor-relative, no-follow filesystem calls.
The completed directory is published with an atomic no-replace rename.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import io
import json
import os
from pathlib import PurePosixPath
import re
import secrets
import selectors
import signal
import stat
import subprocess
import sys
import time
from typing import NoReturn
import zipfile


ARTIFACT_NAME = "playwright-report"
DESTINATION = "playwright-report"
MAX_API_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBER_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1_000
MIN_FREE_SPACE_BYTES = 256 * 1024 * 1024
MAX_ENTRIES = 20_000
COMMAND_TIMEOUT_SECONDS = 5 * 60
TERMINATION_GRACE_SECONDS = 1
EXTRACTION_TIMEOUT_SECONDS = 5 * 60
CHUNK_BYTES = 64 * 1024
GH_CANDIDATES = (
    "/opt/homebrew/bin/gh",
    "/usr/local/bin/gh",
    "/opt/local/bin/gh",
    "/usr/bin/gh",
)
TRUSTED_GH_PREFIXES = (
    "/opt/homebrew",
    "/usr/local",
    "/opt/local",
    "/usr",
)
GH_ENV_ALLOWLIST = frozenset(
    {
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "HOME",
    }
)
SAFE_COMMAND_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin:/opt/local/bin"
GH_HOSTNAME = "github.com"
PULL_REQUEST_EVENTS = {"pull_request", "pull_request_target"}
REPOSITORY_SLUG = re.compile(
    r"\A"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
    r"/"
    r"[A-Za-z0-9._-]{1,100}"
    r"\Z"
)


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def require_secure_descriptor_support() -> None:
    if not hasattr(os, "O_NOFOLLOW"):
        fail("requires POSIX descriptor-relative no-follow APIs")
    required = {os.open, os.mkdir, os.stat, os.unlink, os.rename, os.rmdir}
    if not required.issubset(os.supports_dir_fd):
        fail("requires POSIX descriptor-relative no-follow APIs")


def path_is_within(path: str, parent: str) -> bool:
    try:
        return os.path.commonpath((path, parent)) == parent
    except ValueError:
        return False


def reject_insecure_path(path: str, *, stop_at: str) -> None:
    current = path
    while True:
        metadata = os.stat(current, follow_symlinks=False)
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            fail(f"refusing gh path with group/world-writable component: {current}")
        if current == stop_at:
            return
        parent = os.path.dirname(current)
        if parent == current:
            fail(f"gh executable escaped its trusted prefix: {path}")
        current = parent


def resolve_gh_executable() -> str:
    """Resolve gh from fixed system/package-manager paths, never caller PATH."""
    workspace = os.path.realpath(os.getcwd())
    for candidate in GH_CANDIDATES:
        if not os.path.isabs(candidate):
            continue
        try:
            if not os.path.exists(candidate):
                continue
            resolved = os.path.realpath(candidate)
            metadata = os.stat(resolved, follow_symlinks=False)
        except (FileNotFoundError, NotADirectoryError, OSError):
            continue
        if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
            continue
        if path_is_within(candidate, workspace) or path_is_within(resolved, workspace):
            fail("refusing a project-controlled gh executable")
        trusted_prefix = next(
            (
                prefix
                for prefix in TRUSTED_GH_PREFIXES
                if path_is_within(candidate, prefix)
                and path_is_within(resolved, prefix)
            ),
            None,
        )
        if trusted_prefix is None:
            fail(f"refusing gh executable outside trusted prefixes: {resolved}")
        # Package-manager entry points are commonly symlinks with mode 0777;
        # validate their containing directory plus the resolved regular file.
        reject_insecure_path(os.path.dirname(candidate), stop_at=trusted_prefix)
        reject_insecure_path(resolved, stop_at=trusted_prefix)
        return resolved
    fail(
        "could not find gh in a trusted system/package-manager path; "
        "install GitHub CLI in /opt/homebrew, /usr/local, /opt/local, or /usr"
    )


def build_gh_environment() -> dict[str, str]:
    home = os.environ.get("HOME")
    if not home or not os.path.isabs(home):
        fail("HOME must be an absolute path for gh credential lookup")
    resolved_home = os.path.realpath(home)
    if path_is_within(resolved_home, os.path.realpath(os.getcwd())):
        fail("refusing a project-controlled HOME for gh credential lookup")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in GH_ENV_ALLOWLIST
    }
    environment["HOME"] = resolved_home
    environment["PATH"] = SAFE_COMMAND_PATH
    environment["GH_PROMPT_DISABLED"] = "1"
    environment["GH_PAGER"] = "cat"
    environment["NO_COLOR"] = "1"
    return environment


def open_workspace() -> int:
    """Open the physical cwd by walking from / without following components."""
    physical = os.getcwd()
    if not physical.startswith("/"):
        fail("current working directory must be absolute")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd = os.open("/", flags)
    try:
        for component in PurePosixPath(physical).parts[1:]:
            next_fd = os.open(component, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def reject_existing_destination(workspace_fd: int) -> None:
    try:
        metadata = os.stat(
            DESTINATION,
            dir_fd=workspace_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    kind = "symlink" if stat.S_ISLNK(metadata.st_mode) else "existing path"
    fail(f"{DESTINATION} must be absent; refusing {kind}")


def create_staging_directory(workspace_fd: int) -> tuple[int, str]:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    for _ in range(32):
        name = f".playwright-report.download.{os.getpid()}.{secrets.token_hex(8)}"
        try:
            os.mkdir(name, 0o700, dir_fd=workspace_fd)
        except FileExistsError:
            continue
        return os.open(name, flags, dir_fd=workspace_fd), name
    fail("could not allocate a private staging directory")


def process_group_exists(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate_process_group(process: subprocess.Popen[bytes]) -> str | None:
    group = process.pid
    errors: list[str] = []
    try:
        for name, sig in (("SIGTERM", signal.SIGTERM), ("SIGKILL", signal.SIGKILL)):
            try:
                os.killpg(group, sig)
            except ProcessLookupError:
                process.poll()
                return
            except OSError as error:
                errors.append(f"{name}: {type(error).__name__}: {error}")
            deadline = time.monotonic() + TERMINATION_GRACE_SECONDS
            while process_group_exists(group):
                process.poll()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(0.01, remaining))
            else:
                process.poll()
                return
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")
        return "; ".join(errors)
    errors.append("process group remained alive after SIGKILL grace period")
    return "; ".join(errors)


cleanup_process_group = terminate_process_group


def fail_after_cleanup(
    process: subprocess.Popen[bytes],
    message: str,
) -> NoReturn:
    try:
        cleanup_error = cleanup_process_group(process)
    except Exception as error:
        cleanup_error = f"{type(error).__name__}: {error}"
    fail(f"{message}; cleanup failed: {cleanup_error}" if cleanup_error else message)


def run_bounded(
    command: list[str],
    *,
    environment: dict[str, str],
    stdout_fd: int | None,
    stdout_limit: int,
) -> bytes:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        start_new_session=True,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    captured_stdout = io.BytesIO()
    captured_stderr = bytearray()
    stdout_bytes = 0
    deadline = time.monotonic() + COMMAND_TIMEOUT_SECONDS
    cleaned = False
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                cleaned = True
                fail_after_cleanup(process, "gh command timed out")
            events = selector.select(timeout=min(remaining, 0.1))
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), CHUNK_BYTES)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stdout":
                    stdout_bytes += len(chunk)
                    if stdout_bytes > stdout_limit:
                        cleaned = True
                        fail_after_cleanup(process, "gh response exceeds the configured byte limit")
                    if stdout_fd is None:
                        captured_stdout.write(chunk)
                    else:
                        view = memoryview(chunk)
                        while view:
                            written = os.write(stdout_fd, view)
                            view = view[written:]
                elif len(captured_stderr) < MAX_API_BYTES:
                    captured_stderr.extend(
                        chunk[: MAX_API_BYTES - len(captured_stderr)]
                    )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            cleaned = True
            fail_after_cleanup(process, "gh command timed out")
        returncode = process.wait(timeout=remaining)
        if returncode != 0:
            detail = captured_stderr.decode("utf-8", "replace").strip()
            fail(f"gh command failed with exit {returncode}: {detail}")
        if process_group_exists(process.pid):
            cleaned = True
            fail_after_cleanup(process, "command left live descendants")
        return captured_stdout.getvalue()
    except subprocess.TimeoutExpired:
        cleaned = True
        fail_after_cleanup(process, "gh command timed out")
    except BaseException as error:
        if not cleaned:
            cleanup_error = cleanup_process_group(process)
            if cleanup_error is not None and isinstance(error, Exception):
                fail(f"{error}; cleanup failed: {cleanup_error}")
        raise
    finally:
        selector.close()


def strict_json(raw: bytes, description: str) -> object:
    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                fail(f"{description} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            raw,
            object_pairs_hook=object_pairs,
            parse_constant=lambda value: fail(
                f"{description} contains non-finite JSON number {value}"
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"{description} is not valid JSON: {error}")


def repository_identity(value: object, description: str) -> tuple[int, str]:
    if not isinstance(value, dict):
        fail(f"{description} is missing")
    repository_id = value.get("id")
    full_name = value.get("full_name")
    if (
        type(repository_id) is not int
        or repository_id <= 0
        or not isinstance(full_name, str)
        or not full_name
    ):
        fail(f"{description} has no validated id/full_name")
    return repository_id, full_name


def validate_repository_slug(repository: str) -> str:
    if (
        not repository.isascii()
        or REPOSITORY_SLUG.fullmatch(repository) is None
        or repository.rsplit("/", 1)[1] in {".", ".."}
    ):
        fail("repository must be an explicit ASCII owner/repo slug")
    return repository


def same_repository(
    candidate: tuple[int, str],
    expected: tuple[int, str],
) -> bool:
    return (
        candidate[0] == expected[0]
        and candidate[1].casefold() == expected[1].casefold()
    )


def resolve_repository_identity(
    repository: str,
    *,
    gh_executable: str,
    environment: dict[str, str],
) -> tuple[int, str]:
    endpoint = f"repos/{repository}"
    raw = run_bounded(
        [
            gh_executable,
            "api",
            "--hostname",
            GH_HOSTNAME,
            "--method",
            "GET",
            endpoint,
        ],
        environment=environment,
        stdout_fd=None,
        stdout_limit=MAX_API_BYTES,
    )
    identity = repository_identity(
        strict_json(raw, "GitHub repository metadata"),
        "requested repository",
    )
    if identity[1].casefold() != repository.casefold():
        fail(
            "requested repository metadata does not match the user-confirmed "
            "owner/repo slug"
        )
    return identity


def find_artifact_id(
    repository: str,
    run_id: str,
    *,
    gh_executable: str,
    environment: dict[str, str],
) -> int:
    endpoint = (
        f"repos/{repository}/actions/runs/"
        f"{run_id}/artifacts?per_page=100"
    )
    raw = run_bounded(
        [
            gh_executable,
            "api",
            "--hostname",
            GH_HOSTNAME,
            "--method",
            "GET",
            endpoint,
        ],
        environment=environment,
        stdout_fd=None,
        stdout_limit=MAX_API_BYTES,
    )
    payload = strict_json(raw, "GitHub artifact listing")
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    total_count = payload.get("total_count") if isinstance(payload, dict) else None
    if not isinstance(artifacts, list) or type(total_count) is not int:
        fail("GitHub artifact listing has no validated artifacts/total_count")
    if total_count != len(artifacts):
        fail("GitHub artifact listing is paginated or inconsistent")
    matches = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, dict)
        and artifact.get("name") == ARTIFACT_NAME
        and artifact.get("expired") is False
        and type(artifact.get("id")) is int
        and artifact["id"] > 0
    ]
    if len(matches) != 1:
        fail(
            f"expected exactly one unexpired {ARTIFACT_NAME!r} artifact; "
            f"found {len(matches)}"
        )
    return matches[0]["id"]


def verify_run_is_not_from_fork(
    repository: str,
    run_id: str,
    expected_repository: tuple[int, str],
    *,
    gh_executable: str,
    environment: dict[str, str],
) -> None:
    endpoint = f"repos/{repository}/actions/runs/{run_id}"
    raw = run_bounded(
        [
            gh_executable,
            "api",
            "--hostname",
            GH_HOSTNAME,
            "--method",
            "GET",
            endpoint,
        ],
        environment=environment,
        stdout_fd=None,
        stdout_limit=MAX_API_BYTES,
    )
    payload = strict_json(raw, "GitHub workflow run metadata")
    if not isinstance(payload, dict):
        fail("GitHub workflow run metadata is not an object")
    run_repository = repository_identity(
        payload.get("repository"),
        "run repository",
    )
    if not same_repository(run_repository, expected_repository):
        fail(
            "workflow run repository does not match the user-confirmed "
            "repository"
        )
    head_repository = repository_identity(
        payload.get("head_repository"),
        "run head_repository",
    )
    if not same_repository(head_repository, expected_repository):
        fail(
            "refusing a workflow run whose head repository differs from "
            "the trusted repository (fork-origin run)"
        )
    event = payload.get("event")
    if not isinstance(event, str) or not event:
        fail("GitHub workflow run metadata has no event")
    if event in PULL_REQUEST_EVENTS:
        pull_requests = payload.get("pull_requests")
        if not isinstance(pull_requests, list) or not pull_requests:
            fail("pull-request run metadata has no pull request identity")
        for pull_request in pull_requests:
            if not isinstance(pull_request, dict):
                fail("pull-request run metadata is malformed")
            head = pull_request.get("head")
            pr_repository = head.get("repo") if isinstance(head, dict) else None
            pr_repository_identity = repository_identity(
                pr_repository,
                "pull-request head repository",
            )
            if not same_repository(
                pr_repository_identity,
                expected_repository,
            ):
                fail("refusing artifact from a forked pull request run")


def zip_parts(name: str) -> tuple[str, ...]:
    if "\\" in name or "\x00" in name:
        fail(f"unsafe ZIP member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute():
        fail(f"absolute ZIP member path: {name!r}")
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        fail(f"traversing or empty ZIP member path: {name!r}")
    return parts


def member_kind(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x1:
        fail(f"encrypted ZIP member is forbidden: {info.filename!r}")
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    mode_kind = stat.S_IFMT(unix_mode)
    named_directory = info.filename.endswith("/")
    if mode_kind == stat.S_IFLNK:
        fail(f"symlink ZIP member is forbidden: {info.filename!r}")
    if mode_kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
        fail(f"special ZIP member is forbidden: {info.filename!r}")
    if mode_kind == stat.S_IFDIR and not named_directory:
        fail(f"ZIP directory mode/name disagreement: {info.filename!r}")
    if mode_kind == stat.S_IFREG and named_directory:
        fail(f"ZIP file mode/name disagreement: {info.filename!r}")
    return "directory" if named_directory or mode_kind == stat.S_IFDIR else "file"


def open_directory(
    root_fd: int,
    parts: tuple[str, ...],
    deadline: float,
) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd = os.dup(root_fd)
    try:
        for component in parts:
            if time.monotonic() >= deadline:
                fail("artifact ZIP extraction timed out")
            try:
                os.mkdir(component, 0o700, dir_fd=current_fd)
            except FileExistsError:
                pass
            next_fd = os.open(component, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def require_disk_headroom(directory_fd: int, required_bytes: int) -> None:
    if required_bytes < 0:
        fail("disk-headroom requirement cannot be negative")
    filesystem = os.fstatvfs(directory_fd)
    available = filesystem.f_bavail * filesystem.f_frsize
    if available < required_bytes + MIN_FREE_SPACE_BYTES:
        fail(
            "insufficient free space for bounded artifact handling: "
            f"need {required_bytes + MIN_FREE_SPACE_BYTES} bytes, "
            f"have {available}"
        )


def extract_archive(archive_fd: int, staging_fd: int) -> None:
    deadline = time.monotonic() + EXTRACTION_TIMEOUT_SECONDS
    with os.fdopen(os.dup(archive_fd), "rb") as archive_file:
        with zipfile.ZipFile(archive_file) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                fail(f"artifact ZIP exceeds {MAX_ENTRIES} entries")
            expanded = 0
            seen: set[tuple[str, ...]] = set()
            validated: list[tuple[zipfile.ZipInfo, tuple[str, ...], str]] = []
            for info in infos:
                if time.monotonic() >= deadline:
                    fail("artifact ZIP extraction timed out")
                parts = zip_parts(info.filename)
                if parts in seen:
                    fail(f"duplicate ZIP member: {info.filename!r}")
                seen.add(parts)
                kind = member_kind(info)
                if info.file_size < 0 or info.compress_size < 0:
                    fail(f"invalid ZIP member size: {info.filename!r}")
                if info.file_size > MAX_MEMBER_EXPANDED_BYTES:
                    fail(
                        "artifact ZIP member exceeds the per-member expanded-byte "
                        f"limit: {info.filename!r}"
                    )
                if info.compress_type not in {
                    zipfile.ZIP_STORED,
                    zipfile.ZIP_DEFLATED,
                }:
                    fail(
                        f"unsupported ZIP compression method: {info.filename!r}"
                    )
                if (
                    kind == "file"
                    and info.file_size > 0
                    and (
                        info.compress_size == 0
                        or info.file_size
                        > info.compress_size * MAX_COMPRESSION_RATIO
                    )
                ):
                    fail(
                        "artifact ZIP member exceeds the compression-ratio "
                        f"limit: {info.filename!r}"
                    )
                expanded += info.file_size
                if expanded > MAX_EXPANDED_BYTES:
                    fail("artifact ZIP exceeds the expanded-byte limit")
                validated.append((info, parts, kind))
            require_disk_headroom(staging_fd, expanded)
            for info, parts, kind in validated:
                if time.monotonic() >= deadline:
                    fail("artifact ZIP extraction timed out")
                if kind == "directory":
                    directory_fd = open_directory(staging_fd, parts, deadline)
                    os.close(directory_fd)
                    continue
                parent_fd = open_directory(staging_fd, parts[:-1], deadline)
                output_fd = -1
                try:
                    output_fd = os.open(
                        parts[-1],
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | os.O_NOFOLLOW,
                        0o600,
                        dir_fd=parent_fd,
                    )
                    remaining = info.file_size
                    with archive.open(info, "r") as source:
                        while remaining:
                            if time.monotonic() >= deadline:
                                fail("artifact ZIP extraction timed out")
                            chunk = source.read(min(CHUNK_BYTES, remaining))
                            if not chunk:
                                fail(f"truncated ZIP member: {info.filename!r}")
                            remaining -= len(chunk)
                            view = memoryview(chunk)
                            while view:
                                written = os.write(output_fd, view)
                                view = view[written:]
                        if source.read(1):
                            fail(f"oversized ZIP member: {info.filename!r}")
                    os.fsync(output_fd)
                finally:
                    if output_fd >= 0:
                        os.close(output_fd)
                    os.close(parent_fd)


def rename_noreplace(
    source_fd: int,
    source: str,
    destination_fd: int,
    destination: str,
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin" and hasattr(libc, "renameatx_np"):
        result = libc.renameatx_np(
            source_fd,
            source_bytes,
            destination_fd,
            destination_bytes,
            0x00000004,  # RENAME_EXCL
        )
    elif hasattr(libc, "renameat2"):
        result = libc.renameat2(
            source_fd,
            source_bytes,
            destination_fd,
            destination_bytes,
            1,  # RENAME_NOREPLACE
        )
    else:
        fail("atomic no-replace directory publication is unavailable")
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            fail(f"{destination} appeared during download; refusing to replace it")
        raise OSError(error, os.strerror(error), destination)


def remove_tree(directory_fd: int) -> None:
    """Remove only entries reached through the held private directory fd."""
    for name in os.listdir(directory_fd):
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            try:
                remove_tree(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            os.unlink(name, dir_fd=directory_fd)


def download(repository: str, run_id: str) -> None:
    require_secure_descriptor_support()
    repository = validate_repository_slug(repository)
    if not run_id.isascii() or not run_id.isdigit() or int(run_id) <= 0:
        fail("run ID must be a positive decimal integer")
    gh_executable = resolve_gh_executable()
    gh_environment = build_gh_environment()
    workspace_fd = open_workspace()
    staging_fd = -1
    staging_name = ""
    staging_identity: tuple[int, int] | None = None
    archive_fd = -1
    published = False
    try:
        reject_existing_destination(workspace_fd)
        expected_repository = resolve_repository_identity(
            repository,
            gh_executable=gh_executable,
            environment=gh_environment,
        )
        verify_run_is_not_from_fork(
            repository,
            run_id,
            expected_repository,
            gh_executable=gh_executable,
            environment=gh_environment,
        )
        artifact_id = find_artifact_id(
            repository,
            run_id,
            gh_executable=gh_executable,
            environment=gh_environment,
        )
        staging_fd, staging_name = create_staging_directory(workspace_fd)
        staged_metadata = os.fstat(staging_fd)
        staging_identity = (staged_metadata.st_dev, staged_metadata.st_ino)
        require_disk_headroom(staging_fd, MAX_ARCHIVE_BYTES)
        archive_fd = os.open(
            ".artifact.zip",
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=staging_fd,
        )
        endpoint = (
            f"repos/{repository}/actions/"
            f"artifacts/{artifact_id}/zip"
        )
        run_bounded(
            [
                gh_executable,
                "api",
                "--hostname",
                GH_HOSTNAME,
                "--method",
                "GET",
                endpoint,
            ],
            environment=gh_environment,
            stdout_fd=archive_fd,
            stdout_limit=MAX_ARCHIVE_BYTES,
        )
        os.fsync(archive_fd)
        os.lseek(archive_fd, 0, os.SEEK_SET)
        extract_archive(archive_fd, staging_fd)
        os.close(archive_fd)
        archive_fd = -1
        os.unlink(".artifact.zip", dir_fd=staging_fd)

        current_metadata = os.stat(
            staging_name,
            dir_fd=workspace_fd,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(current_metadata.st_mode)
            or (current_metadata.st_dev, current_metadata.st_ino)
            != staging_identity
        ):
            fail("private staging directory changed during download")
        reject_existing_destination(workspace_fd)
        require_disk_headroom(staging_fd, 0)
        rename_noreplace(
            workspace_fd,
            staging_name,
            workspace_fd,
            DESTINATION,
        )
        published = True
        os.fsync(workspace_fd)
    finally:
        if archive_fd >= 0:
            os.close(archive_fd)
        if staging_fd >= 0:
            if not published:
                remove_tree(staging_fd)
                try:
                    current_metadata = os.stat(
                        staging_name,
                        dir_fd=workspace_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    current_metadata = None
                if (
                    current_metadata is not None
                    and stat.S_ISDIR(current_metadata.st_mode)
                    and (current_metadata.st_dev, current_metadata.st_ino)
                    == staging_identity
                ):
                    os.rmdir(staging_name, dir_fd=workspace_fd)
            os.close(staging_fd)
        os.close(workspace_fd)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="safely download the playwright-report Actions artifact"
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="user-confirmed GitHub repository slug in owner/repo form",
    )
    parser.add_argument("run_id", help="user-confirmed numeric GitHub Actions run ID")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        download(args.repo, args.run_id)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"download-playwright-report: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
