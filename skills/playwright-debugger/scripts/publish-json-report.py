#!/usr/bin/env python3
"""Run a command and atomically publish its validated JSON stdout.

The output path is resolved beneath the current working directory without
following symlinked directory components. The command never runs when the
destination is unsafe.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import secrets
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePath
from typing import NoReturn


# Keep this publication ceiling aligned with read-playwright-artifact.py.
MAX_STDOUT_BYTES = 8 * 1024 * 1024
MAX_COMMAND_SECONDS = 5 * 60
STREAM_CHUNK_BYTES = 64 * 1024
TERMINATION_GRACE_SECONDS = 1
ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def relative_parts(raw_path: str) -> tuple[str, ...]:
    path = PurePath(raw_path)
    if path.is_absolute():
        fail("output path must be relative to the current working directory")
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        fail("output path must not be empty or contain '.' or '..'")
    if len(parts) < 2:
        fail("output path must include a report directory")
    return parts


def open_output_parent(parts: tuple[str, ...]) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    current_fd = os.open(".", flags)
    try:
        for component in parts[:-1]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=current_fd)
            except FileExistsError:
                pass
            next_fd = os.open(component, flags | nofollow, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def reject_unsafe_destination(parent_fd: int, name: str) -> None:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode):
        fail("output destination must not be a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        fail("output destination must be absent or a regular file")


def create_temporary(parent_fd: int, destination: str) -> tuple[int, str]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    for _ in range(32):
        temporary = f".{destination}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        try:
            return os.open(temporary, flags, 0o600, dir_fd=parent_fd), temporary
        except FileExistsError:
            continue
    fail("could not allocate a unique temporary report file")


def load_report_validator() -> object:
    script_directory = Path(__file__).resolve(strict=True).parent
    validator_path = script_directory / "read-playwright-artifact.py"
    metadata = os.lstat(validator_path)
    if not stat.S_ISREG(metadata.st_mode):
        fail("Playwright report validator must be a regular sibling file")
    resolved_validator = validator_path.resolve(strict=True)
    if resolved_validator.parent != script_directory:
        fail("Playwright report validator escaped the trusted script directory")
    spec = importlib.util.spec_from_file_location(
        "playwright_debugger_artifact_reader",
        resolved_validator,
    )
    if spec is None or spec.loader is None:
        fail("could not load the Playwright report validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "validate_report_json", None)):
        fail("Playwright report validator has no validate_report_json entry point")
    return module


def validate_report(file_descriptor: int, validator: object) -> None:
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    with os.fdopen(os.dup(file_descriptor), "rb") as report:
        data = report.read(MAX_STDOUT_BYTES + 1)
    if len(data) > MAX_STDOUT_BYTES:
        fail(f"report exceeds the {MAX_STDOUT_BYTES}-byte limit")
    validator.validate_report_json(data)


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
        with process.stdout, os.fdopen(os.dup(file_descriptor), "wb") as temporary:
            captured_bytes = 0
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            try:
                while True:
                    remaining_seconds = deadline - time.monotonic()
                    if remaining_seconds <= 0:
                        cleaned = True
                        fail_after_cleanup(process, f"command timed out after {MAX_COMMAND_SECONDS} seconds")
                    if not selector.select(timeout=min(remaining_seconds, 0.1)):
                        continue

                    remaining_bytes = MAX_STDOUT_BYTES - captured_bytes
                    chunk = os.read(
                        process.stdout.fileno(),
                        min(STREAM_CHUNK_BYTES, remaining_bytes + 1),
                    )
                    if not chunk:
                        break
                    captured_bytes += len(chunk)
                    if captured_bytes > MAX_STDOUT_BYTES:
                        cleaned = True
                        fail_after_cleanup(process, f"command stdout exceeds the {MAX_STDOUT_BYTES}-byte limit")
                    temporary.write(chunk)
            finally:
                selector.close()

        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            cleaned = True
            fail_after_cleanup(process, f"command timed out after {MAX_COMMAND_SECONDS} seconds")
        try:
            returncode = process.wait(timeout=remaining_seconds)
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


def run_and_publish(output: str, command: list[str], pass_env: list[str]) -> None:
    if not command:
        fail("a command is required after '--'")
    environment = command_environment(pass_env)
    command = resolve_command(command, environment)

    parts = relative_parts(output)
    destination = parts[-1]
    parent_fd = open_output_parent(parts)
    temporary_fd = -1
    temporary_name = ""
    try:
        reject_unsafe_destination(parent_fd, destination)
        temporary_fd, temporary_name = create_temporary(parent_fd, destination)
        validator = load_report_validator()

        capture_stdout(temporary_fd, command, environment)
        validate_report(temporary_fd, validator)
        os.fsync(temporary_fd)

        # Recheck for an unsafe destination created while the command ran.
        # renameat replaces a regular file or symlink entry atomically and never
        # follows it; the directory descriptor also pins the validated parent.
        reject_unsafe_destination(parent_fd, destination)
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
        description="atomically publish validated JSON emitted by a command"
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
    parser.add_argument("output", help="relative output path beneath the current directory")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="command and arguments, preceded by --",
    )
    args = parser.parse_args(argv)
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    return args


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        run_and_publish(args.output, args.command, args.pass_env)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"publish-json-report: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
