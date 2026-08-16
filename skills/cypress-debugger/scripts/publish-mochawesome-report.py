#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run a merger and atomically publish its strictly validated Mochawesome JSON."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePath
import re
import secrets
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
from types import ModuleType
from typing import NoReturn


MAX_STDOUT_BYTES = 8 * 1024 * 1024
MAX_COMMAND_SECONDS = 5 * 60
STREAM_CHUNK_BYTES = 64 * 1024
TERMINATION_GRACE_SECONDS = 1
REPORT_PREFIX = ("cypress", "reports")
ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def require_secure_descriptor_support() -> None:
    if not hasattr(os, "O_NOFOLLOW"):
        fail("requires POSIX descriptor-relative no-follow APIs")
    required = {os.open, os.mkdir, os.stat, os.unlink, os.rename}
    if not required.issubset(os.supports_dir_fd):
        fail("requires POSIX descriptor-relative no-follow APIs")


def output_parts(raw_path: str) -> tuple[str, ...]:
    path = PurePath(raw_path)
    parts = path.parts
    if (
        path.is_absolute()
        or len(parts) != 3
        or parts[:2] != REPORT_PREFIX
        or any(part in {"", ".", ".."} for part in parts)
    ):
        fail("output must be a direct child of cypress/reports")
    return parts


def open_output_parent(parts: tuple[str, ...]) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current_fd = os.open(".", flags)
    try:
        for component in parts[:-1]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=current_fd)
            except FileExistsError:
                pass
            next_fd = os.open(component, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def destination_identity(parent_fd: int, name: str) -> tuple[int, ...] | None:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(metadata.st_mode):
        fail("output destination must not be a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        fail("output destination must be absent or a regular file")
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def create_temporary(parent_fd: int, destination: str) -> tuple[int, str]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    for _ in range(32):
        name = f".{destination}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        try:
            return os.open(name, flags, 0o600, dir_fd=parent_fd), name
        except FileExistsError:
            continue
    fail("could not allocate a unique temporary report file")


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


def command_environment(pass_env: list[str]) -> dict[str, str]:
    environment = {"PATH": os.defpath}
    seen: set[str] = set()
    for name in pass_env:
        if not ENVIRONMENT_NAME.fullmatch(name):
            fail(f"invalid environment variable name: {name!r}")
        if name in seen:
            fail(f"environment variable requested more than once: {name}")
        if name not in os.environ:
            fail(f"requested environment variable is not set: {name}")
        seen.add(name)
        environment[name] = os.environ[name]
    return environment


def resolve_command(command: list[str], environment: dict[str, str]) -> list[str]:
    executable = command[0]
    if os.sep in executable or (os.altsep and os.altsep in executable):
        candidate = Path(executable)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve(strict=True)
        metadata = os.stat(resolved)
        if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
            fail("command executable must resolve to an executable regular file")
    else:
        located = shutil.which(executable, path=environment["PATH"])
        if located is None:
            fail(
                f"command executable {executable!r} was not found in the child PATH"
            )
        resolved = Path(located).resolve(strict=True)
    return [str(resolved), *command[1:]]


def capture_stdout(
    file_descriptor: int,
    command: list[str],
    environment: dict[str, str],
) -> None:
    process = subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.PIPE,
        start_new_session=True,
    )
    deadline = time.monotonic() + MAX_COMMAND_SECONDS
    cleaned = False
    try:
        if process.stdout is None:
            fail("could not capture command stdout")
        captured_bytes = 0
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    cleaned = True
                    fail_after_cleanup(process, f"command timed out after {MAX_COMMAND_SECONDS} seconds")
                if not selector.select(timeout=min(remaining, 0.1)):
                    continue
                chunk = os.read(
                    process.stdout.fileno(),
                    min(
                        STREAM_CHUNK_BYTES,
                        MAX_STDOUT_BYTES - captured_bytes + 1,
                    ),
                )
                if not chunk:
                    break
                captured_bytes += len(chunk)
                if captured_bytes > MAX_STDOUT_BYTES:
                    cleaned = True
                    fail_after_cleanup(process, f"command stdout exceeds the {MAX_STDOUT_BYTES}-byte limit")
                view = memoryview(chunk)
                while view:
                    written = os.write(file_descriptor, view)
                    if written <= 0:
                        raise OSError("temporary report write made no progress")
                    view = view[written:]
        finally:
            selector.close()
            process.stdout.close()

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            cleaned = True
            fail_after_cleanup(process, f"command timed out after {MAX_COMMAND_SECONDS} seconds")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            cleaned = True
            fail_after_cleanup(process, f"command timed out after {MAX_COMMAND_SECONDS} seconds")
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command)
        if process_group_exists(process.pid):
            cleaned = True
            fail_after_cleanup(process, "command left live descendants")
    except BaseException as error:
        if not cleaned:
            cleanup_error = cleanup_process_group(process)
            if cleanup_error is not None and isinstance(error, Exception):
                fail(f"{error}; cleanup failed: {cleanup_error}")
        raise


def load_reader() -> tuple[ModuleType, bytes]:
    script_directory = Path(__file__).resolve(strict=True).parent
    reader_path = script_directory / "read-cypress-artifact.py"
    path_metadata = os.lstat(reader_path)
    if not stat.S_ISREG(path_metadata.st_mode):
        fail("Cypress artifact reader must be a regular sibling file")
    resolved_reader = reader_path.resolve(strict=True)
    if resolved_reader.parent != script_directory:
        fail("Cypress artifact reader escaped the trusted script directory")

    descriptor = os.open(resolved_reader, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        descriptor_metadata = os.fstat(descriptor)
        if (
            descriptor_metadata.st_dev,
            descriptor_metadata.st_ino,
        ) != (
            path_metadata.st_dev,
            path_metadata.st_ino,
        ):
            fail("Cypress artifact reader changed while it was being opened")
        source = b""
        while True:
            chunk = os.read(descriptor, STREAM_CHUNK_BYTES)
            if not chunk:
                break
            source += chunk
        final_metadata = os.fstat(descriptor)
        if (
            final_metadata.st_size,
            final_metadata.st_mtime_ns,
            final_metadata.st_ctime_ns,
        ) != (
            descriptor_metadata.st_size,
            descriptor_metadata.st_mtime_ns,
            descriptor_metadata.st_ctime_ns,
        ):
            fail("Cypress artifact reader changed while it was being loaded")
    finally:
        os.close(descriptor)

    module = ModuleType("cypress_debugger_artifact_reader")
    module.__file__ = str(resolved_reader)
    exec(
        compile(source, str(resolved_reader), "exec"),
        module.__dict__,
    )
    if not callable(getattr(module, "load_json", None)) or not callable(
        getattr(module, "mochawesome_output", None)
    ):
        fail("Cypress artifact reader is missing required validator entry points")
    return module, source


def validate_mochawesome(
    file_descriptor: int,
    trusted_reader: tuple[ModuleType, bytes],
) -> None:
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(file_descriptor, STREAM_CHUNK_BYTES)
        if not chunk:
            break
        chunks.append(chunk)
    reader, _source = trusted_reader
    report = reader.load_json(b"".join(chunks))
    reader.mochawesome_output(report)


def run_and_publish(output: str, command: list[str], pass_env: list[str]) -> None:
    require_secure_descriptor_support()
    if not command:
        fail("a command is required after '--'")
    environment = command_environment(pass_env)
    command = resolve_command(command, environment)
    trusted_reader = load_reader()
    parts = output_parts(output)
    destination = parts[-1]
    parent_fd = open_output_parent(parts)
    temporary_fd = -1
    temporary_name = ""
    try:
        original_identity = destination_identity(parent_fd, destination)
        temporary_fd, temporary_name = create_temporary(parent_fd, destination)
        capture_stdout(temporary_fd, command, environment)
        validate_mochawesome(temporary_fd, trusted_reader)
        os.fsync(temporary_fd)
        if destination_identity(parent_fd, destination) != original_identity:
            fail("output destination changed while the merger was running")
        os.rename(
            temporary_name,
            destination,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary_name = ""
        os.fsync(parent_fd)
    finally:
        if temporary_fd >= 0:
            os.close(temporary_fd)
        if temporary_name:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "atomically publish strict Mochawesome JSON emitted by a command"
        )
    )
    parser.add_argument(
        "--pass-env",
        action="append",
        default=[],
        metavar="NAME",
        help=(
            "pass one explicitly approved environment variable to the command; "
            "repeat for additional variables"
        ),
    )
    parser.add_argument(
        "output",
        help="direct child path beneath cypress/reports",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    return args


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        run_and_publish(args.output, args.command, args.pass_env)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"publish-mochawesome-report: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
