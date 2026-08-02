#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read Cypress JSON and media artifacts through bounded trust gates."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redact_artifact import (
    bounded_redacted,
    redact_diagnostic,
    redact_for_output,
)


MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_PNG_BYTES = 64 * 1024 * 1024
MAX_MP4_BYTES = 512 * 1024 * 1024
MAX_JSON_DEPTH = 100
MAX_JSON_NODES = 200_000
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_OUTPUT_RECORDS = 10_000
MAX_ATTEMPTS_PER_TEST = 100
MAX_STRING_CHARS = 4_000
REQUIRED_MOCHAWESOME_STATS = (
    "suites",
    "tests",
    "passes",
    "pending",
    "failures",
    "skipped",
    "duration",
)
OPTIONAL_MOCHAWESOME_INTEGER_STATS = ("testsRegistered", "other")
OPTIONAL_MOCHAWESOME_BOOLEAN_STATS = ("hasOther", "hasSkipped")
OPTIONAL_MOCHAWESOME_PERCENT_STATS = ("passPercent", "pendingPercent")
CYPRESS_RUN_RESULT_STATES = {"passed", "failed", "pending", "skipped"}


def require_secure_descriptor_support() -> tuple[int, int]:
    directory_flag = getattr(os, "O_DIRECTORY", None)
    no_follow_flag = getattr(os, "O_NOFOLLOW", None)
    if (
        os.name != "posix"
        or not isinstance(directory_flag, int)
        or not isinstance(no_follow_flag, int)
        or os.open not in getattr(os, "supports_dir_fd", set())
    ):
        raise ValueError(
            "secure artifact reading requires POSIX descriptor-relative "
            "no-follow support (macOS, Linux, or Windows via WSL); "
            "native Windows is unsupported"
        )
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    return (
        os.O_RDONLY | directory_flag | no_follow_flag | close_on_exec,
        os.O_RDONLY
        | no_follow_flag
        | getattr(os, "O_NONBLOCK", 0)
        | close_on_exec,
    )


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for position, (key, item) in enumerate(pairs):
        if key in value:
            # The key itself is artifact-controlled and this error travels to
            # stderr through `parser.error`, which never reaches the emission
            # gate. Report the position instead of echoing the bytes.
            raise ValueError(f"duplicate JSON key at object entry {position}")
        value[key] = item
    return value


def reject_nonfinite_number(token: str) -> object:
    raise ValueError(f"non-finite JSON number is forbidden: {token}")


def strict_json_loads(data: bytes | str) -> object:
    if isinstance(data, bytes):
        if data.startswith(b"\xef\xbb\xbf"):
            raise ValueError("JSON BOM is forbidden")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"invalid JSON UTF-8: {exc}") from exc
    else:
        text = data
    if text.startswith("\ufeff"):
        raise ValueError("JSON BOM is forbidden")
    start = len(text) - len(text.lstrip())
    if start == len(text):
        raise ValueError("invalid JSON: input is empty")
    decoder = json.JSONDecoder(
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_nonfinite_number,
    )
    try:
        value, end = decoder.raw_decode(text, start)
    except (RecursionError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if text[end:].strip():
        raise ValueError("invalid JSON: trailing data is forbidden")
    return value


def open_trusted_directory(path: Path, description: str) -> int:
    """Open an absolute directory from the filesystem root without following links."""
    directory_flags, _ = require_secure_descriptor_support()
    absolute = Path(os.path.abspath(path))
    current_fd: int | None = None
    try:
        current_fd = os.open(absolute.anchor, directory_flags)
        for component in absolute.parts[1:]:
            next_fd = os.open(component, directory_flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except OSError as exc:
        if current_fd is not None:
            os.close(current_fd)
        raise ValueError(
            f"{description} contains a symlink or is unavailable: {path}: {exc}"
        ) from exc


def descriptor_fingerprint(metadata: os.stat_result) -> tuple[int, ...]:
    fingerprint = (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
    )
    ctime_ns = getattr(metadata, "st_ctime_ns", None)
    if ctime_ns is not None:
        return fingerprint + (ctime_ns,)
    return fingerprint


def require_unchanged_descriptor(
    artifact_fd: int,
    original_metadata: os.stat_result,
    artifact: Path,
) -> os.stat_result:
    current_metadata = os.fstat(artifact_fd)
    if descriptor_fingerprint(current_metadata) != descriptor_fingerprint(
        original_metadata
    ):
        raise ValueError(f"artifact changed while being read: {artifact}")
    return current_metadata


def require_path_still_matches_descriptor(
    directory_fd: int,
    name: str,
    original_metadata: os.stat_result,
    artifact: Path,
) -> None:
    try:
        path_metadata = os.stat(
            name,
            dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ValueError(
            f"artifact changed while being read: {artifact}"
        ) from exc
    if descriptor_fingerprint(path_metadata) != descriptor_fingerprint(
        original_metadata
    ):
        raise ValueError(f"artifact changed while being read: {artifact}")


@contextmanager
def open_artifact_descriptor(
    artifact_root: Path,
    artifact: Path,
    max_bytes: int,
) -> Iterator[tuple[int, os.stat_result]]:
    directory_flags, file_flags = require_secure_descriptor_support()
    absolute_root = Path(os.path.abspath(artifact_root))
    absolute_artifact = Path(os.path.abspath(artifact))
    try:
        lexical_relative = absolute_artifact.relative_to(absolute_root)
    except ValueError as exc:
        raise ValueError(f"artifact is outside the artifact root: {artifact}") from exc
    if not lexical_relative.parts:
        raise ValueError(f"artifact is not a regular file: {artifact}")

    root_fd = open_trusted_directory(absolute_root, "artifact root")
    current_fd = root_fd
    opened_directory_fds: list[int] = []
    artifact_fd: int | None = None
    try:
        for component in lexical_relative.parts[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=current_fd)
            opened_directory_fds.append(next_fd)
            current_fd = next_fd
        artifact_fd = os.open(
            lexical_relative.parts[-1],
            file_flags,
            dir_fd=current_fd,
        )
        metadata = os.fstat(artifact_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"artifact is not a regular file: {artifact}")
        if metadata.st_size > max_bytes:
            raise ValueError(
                f"artifact exceeds the {max_bytes}-byte limit: {artifact}"
            )
        yield artifact_fd, metadata
        require_path_still_matches_descriptor(
            current_fd,
            lexical_relative.parts[-1],
            metadata,
            artifact,
        )
    except OSError as exc:
        raise ValueError(
            f"unsafe, symlinked, or unreadable artifact path: {artifact}: {exc}"
        ) from exc
    finally:
        if artifact_fd is not None:
            os.close(artifact_fd)
        for directory_fd in reversed(opened_directory_fds):
            os.close(directory_fd)
        os.close(root_fd)


def read_artifact(
    artifact_root: Path,
    artifact: Path,
    max_bytes: int,
) -> tuple[int, bytes]:
    with open_artifact_descriptor(
        artifact_root,
        artifact,
        max_bytes,
    ) as (artifact_fd, metadata):
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(artifact_fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > max_bytes:
            raise ValueError(
                f"artifact exceeds the {max_bytes}-byte limit: {artifact}"
            )
        require_unchanged_descriptor(artifact_fd, metadata, artifact)
        if len(data) != metadata.st_size:
            raise ValueError(f"artifact changed while being read: {artifact}")
        return metadata.st_size, data


def write_all(file_descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(file_descriptor, view)
        if written <= 0:
            raise OSError("snapshot write made no progress")
        view = view[written:]


def remove_failed_snapshot(
    snapshot_path: Path | None,
    snapshot_directory: Path | None,
) -> None:
    if snapshot_path is not None:
        try:
            snapshot_path.unlink()
        except FileNotFoundError:
            pass
    if snapshot_directory is not None:
        try:
            snapshot_directory.rmdir()
        except FileNotFoundError:
            pass


def validate_json_shape(value: object) -> None:
    stack = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ValueError(f"JSON exceeds the {MAX_JSON_NODES}-node limit")
        if depth > MAX_JSON_DEPTH:
            raise ValueError(f"JSON exceeds the {MAX_JSON_DEPTH}-level depth limit")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)


def load_json(data: bytes) -> object:
    try:
        value = strict_json_loads(data)
    except ValueError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    validate_json_shape(value)
    return value


def bounded_string(value: object) -> str | None:
    return bounded_redacted(value, MAX_STRING_CHARS)


def bounded_scalar(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return bounded_string(value)
    return None


def nonnegative_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"mochawesome stats.{field} must be a nonnegative integer"
        )
    return value


def validate_mochawesome_stats(stats: dict[str, object]) -> dict[str, int]:
    counters = {
        key: nonnegative_integer(stats.get(key), key)
        for key in REQUIRED_MOCHAWESOME_STATS
    }
    for key in OPTIONAL_MOCHAWESOME_INTEGER_STATS:
        if key in stats:
            nonnegative_integer(stats[key], key)
    for key in OPTIONAL_MOCHAWESOME_BOOLEAN_STATS:
        if key in stats and not isinstance(stats[key], bool):
            raise ValueError(f"mochawesome stats.{key} must be a boolean")
    for key in OPTIONAL_MOCHAWESOME_PERCENT_STATS:
        value = stats.get(key)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value < 0
            or value > 100
        ):
            raise ValueError(
                f"mochawesome stats.{key} must be a percentage from 0 to 100"
            )
    for key in ("start", "end"):
        if key in stats and not isinstance(stats[key], str):
            raise ValueError(f"mochawesome stats.{key} must be a string")
    return counters


def error_text(value: object) -> str | None:
    if isinstance(value, dict):
        return bounded_string(value.get("message"))
    return bounded_string(value)


def screenshot_paths(context: object) -> list[str]:
    if not isinstance(context, str) or not context:
        return []
    try:
        parsed = strict_json_loads(context)
    except ValueError:
        return []
    validate_json_shape(parsed)
    paths: list[str] = []
    stack = [parsed]
    while stack:
        current = stack.pop()
        if isinstance(current, str) and current.lower().endswith(".png"):
            path = bounded_string(current)
            assert path is not None
            paths.append(path)
        elif isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
        if len(paths) > MAX_OUTPUT_RECORDS:
            raise ValueError("context exceeds the screenshot-path limit")
    return paths


def mochawesome_test_classification(
    test: object,
    *,
    is_hook: bool = False,
) -> str:
    if (
        not isinstance(test, dict)
        or not isinstance(test.get("pass"), bool)
        or not isinstance(test.get("fail"), bool)
        or not isinstance(test.get("pending"), bool)
    ):
        raise ValueError(
            "mochawesome schema requires test pass/fail/pending booleans"
        )
    skipped = test.get("skipped", False)
    if not isinstance(skipped, bool):
        raise ValueError(
            "mochawesome schema requires optional test skipped boolean"
        )
    classifications = {
        "passed": test["pass"],
        "failed": test["fail"],
        "pending": test["pending"],
        "skipped": skipped,
    }
    active = [name for name, enabled in classifications.items() if enabled]
    if not active and is_hook:
        classification = "other"
    elif len(active) == 1:
        classification = active[0]
    else:
        raise ValueError(
            "mochawesome schema has contradictory test state flags"
        )
    state = test.get("state")
    if state is not None and not isinstance(state, str):
        raise ValueError(
            "mochawesome schema requires test state to be a string or null"
        )
    expected_states: dict[str, set[object]] = {
        "passed": {"passed"},
        "failed": {"failed"},
        "pending": {None, "pending"},
        "skipped": {None, "skipped"},
        "other": {None},
    }
    if state not in expected_states[classification]:
        raise ValueError(
            "mochawesome test flags contradict test state"
        )
    if is_hook and classification in {"pending", "skipped"}:
        raise ValueError("mochawesome hook cannot be pending or skipped")

    error = test.get("err")
    if not isinstance(error, dict):
        raise ValueError("mochawesome schema requires test err object")
    has_error = any(
        isinstance(error.get(field), str) and bool(error[field].strip())
        for field in ("message", "estack")
    )
    if classification == "failed" and not has_error:
        raise ValueError(
            "mochawesome failed test requires a nonempty error message or stack"
        )
    if classification != "failed" and has_error:
        raise ValueError(
            "mochawesome nonfailed test cannot contain a failure error"
        )
    return classification


def validate_mochawesome_percentage(
    stats: dict[str, object],
    field: str,
    expected: float | None,
) -> None:
    if field not in stats:
        return
    actual = stats[field]
    if expected is None:
        if actual is not None:
            raise ValueError(
                f"mochawesome stats.{field} contradicts parsed counters"
            )
        return
    if not isinstance(actual, (int, float)) or isinstance(actual, bool):
        raise ValueError(
            f"mochawesome stats.{field} must be a percentage from 0 to 100"
        )
    if abs(float(actual) - expected) > 0.011:
        raise ValueError(
            # Explanation before the numbers: see the counter check below.
            f"mochawesome stats.{field} contradicts parsed percentage "
            f"(reported {actual}, parsed {expected})"
        )


def mochawesome_output(report: object) -> dict[str, object]:
    if (
        not isinstance(report, dict)
        or not isinstance(report.get("stats"), dict)
        or not isinstance(report.get("results"), list)
    ):
        raise ValueError(
            "mochawesome schema requires root stats object and results array"
        )
    stats = report["stats"]
    counters = validate_mochawesome_stats(stats)
    records: list[dict[str, object]] = []
    parsed_counts = {
        "suites": 0,
        "tests": 0,
        "passes": 0,
        "pending": 0,
        "failures": 0,
        "skipped": 0,
        "failed_hooks": 0,
    }
    containers: list[tuple[object, str | None]] = [
        (result, None) for result in reversed(report["results"])
    ]
    while containers:
        container, inherited_file = containers.pop()
        if (
            not isinstance(container, dict)
            or not isinstance(container.get("tests"), list)
            or not isinstance(container.get("suites"), list)
        ):
            raise ValueError(
                "mochawesome schema requires tests/suites arrays on every "
                "result and suite"
            )
        file_name = bounded_string(container.get("file")) or inherited_file
        parsed_counts["suites"] += len(container["suites"])
        containers.extend(
            (suite, file_name) for suite in reversed(container["suites"])
        )
        expected_ids = {
            "passes": [],
            "failures": [],
            "pending": [],
            "skipped": [],
        }
        for test in container["tests"]:
            if not isinstance(test, dict):
                raise ValueError(
                    "mochawesome schema requires test objects"
                )
            if test.get("isHook", False) is not False:
                raise ValueError(
                    "mochawesome suite tests cannot be hook records"
                )
            classification = mochawesome_test_classification(test)
            test_uuid = test.get("uuid")
            if not isinstance(test_uuid, str) or not test_uuid:
                raise ValueError(
                    "mochawesome schema requires nonempty test uuid strings"
                )
            list_name = {
                "passed": "passes",
                "failed": "failures",
                "pending": "pending",
                "skipped": "skipped",
            }[classification]
            expected_ids[list_name].append(test_uuid)
            parsed_counts["tests"] += 1
            if classification == "passed":
                parsed_counts["passes"] += 1
            elif classification == "failed":
                parsed_counts["failures"] += 1
            elif classification == "pending":
                parsed_counts["pending"] += 1
            else:
                parsed_counts["skipped"] += 1
            if classification != "failed":
                continue
            error = test["err"]
            assert isinstance(error, dict)
            records.append(
                {
                    "file": file_name,
                    "title": bounded_string(test.get("title")),
                    "fullTitle": bounded_string(test.get("fullTitle")),
                    "duration": bounded_scalar(test.get("duration")),
                    "state": bounded_string(test.get("state")),
                    "error": bounded_string(error.get("message")),
                    "stack": bounded_string(error.get("estack")),
                    "screenshots": screenshot_paths(test.get("context")),
                }
            )
            if len(records) > MAX_OUTPUT_RECORDS:
                raise ValueError(
                    f"mochawesome report exceeds the "
                    f"{MAX_OUTPUT_RECORDS}-record limit"
                )
        for list_name, expected in expected_ids.items():
            actual = container.get(list_name)
            if (
                not isinstance(actual, list)
                or not all(isinstance(item, str) for item in actual)
                or actual != expected
            ):
                raise ValueError(
                    f"mochawesome suite {list_name} contradicts test flags"
                )
        for hook_field in ("beforeHooks", "afterHooks"):
            hooks = container.get(hook_field, [])
            if not isinstance(hooks, list):
                raise ValueError(
                    f"mochawesome schema requires optional {hook_field} array"
                )
            for hook in hooks:
                if (
                    not isinstance(hook, dict)
                    or hook.get("isHook") is not True
                ):
                    raise ValueError(
                        f"mochawesome {hook_field} entries must be hook records"
                    )
                classification = mochawesome_test_classification(
                    hook, is_hook=True
                )
                if classification == "failed":
                    parsed_counts["failed_hooks"] += 1
                    error = hook["err"]
                    assert isinstance(error, dict)
                    records.append(
                        {
                            "file": file_name,
                            "title": bounded_string(hook.get("title")),
                            "fullTitle": bounded_string(
                                hook.get("fullTitle")
                            ),
                            "duration": bounded_scalar(
                                hook.get("duration")
                            ),
                            "state": bounded_string(hook.get("state")),
                            "error": bounded_string(error.get("message")),
                            "stack": bounded_string(error.get("estack")),
                            "screenshots": screenshot_paths(
                                hook.get("context")
                            ),
                            "hook": hook_field,
                        }
                    )
                    if len(records) > MAX_OUTPUT_RECORDS:
                        raise ValueError(
                            f"mochawesome report exceeds the "
                            f"{MAX_OUTPUT_RECORDS}-record limit"
                        )

    runnable_tests = parsed_counts["tests"] - parsed_counts["skipped"]
    expected_stats = {
        "suites": parsed_counts["suites"],
        "tests": runnable_tests,
        "passes": parsed_counts["passes"],
        "pending": parsed_counts["pending"],
        "failures": parsed_counts["failures"],
        "skipped": parsed_counts["skipped"],
    }
    for key, expected_value in expected_stats.items():
        if counters[key] != expected_value:
            raise ValueError(
                # Explanation before the numbers, deliberately: the shared
                # redactor treats `passes=2` as a credential assignment and
                # its value extent runs to the end of the line, so a reason
                # written after a `key=value` would be redacted away with
                # the counter and the operator would be told only that
                # something was wrong.
                f"mochawesome stats.{key} contradicts parsed counters "
                f"(reported {counters[key]}, parsed {expected_value})"
            )
    for key in ("testsRegistered",):
        if key in stats and stats[key] != parsed_counts["tests"]:
            raise ValueError(
                f"mochawesome stats.{key} contradicts parsed tests "
                f"(reported {stats[key]}, parsed {parsed_counts['tests']})"
            )
    if "other" in stats and stats["other"] != parsed_counts["failed_hooks"]:
        raise ValueError(
            f"mochawesome stats.other contradicts parsed failed hooks "
            f"(reported {stats['other']}, "
            f"parsed {parsed_counts['failed_hooks']})"
        )
    if "hasOther" in stats and stats["hasOther"] != (
        parsed_counts["failed_hooks"] > 0
    ):
        raise ValueError(
            "mochawesome stats.hasOther contradicts parsed failed hooks"
        )
    if "hasSkipped" in stats and stats["hasSkipped"] != (
        parsed_counts["skipped"] > 0
    ):
        raise ValueError(
            "mochawesome stats.hasSkipped contradicts parsed skipped"
        )
    registered = parsed_counts["tests"]
    pass_denominator = registered - parsed_counts["pending"]
    validate_mochawesome_percentage(
        stats,
        "passPercent",
        (
            parsed_counts["passes"] / pass_denominator * 100
            if pass_denominator
            else None
        ),
    )
    validate_mochawesome_percentage(
        stats,
        "pendingPercent",
        (
            parsed_counts["pending"] / registered * 100
            if registered
            else None
        ),
    )

    return {
        "stats": {
            key: counters[key] for key in REQUIRED_MOCHAWESOME_STATS
        },
        "failures": records,
    }


def run_result_records(report: object) -> list[dict[str, object]]:
    if not isinstance(report, dict) or not isinstance(report.get("runs"), list):
        raise ValueError("run-results schema requires a root runs array")
    records: list[dict[str, object]] = []
    for run in report["runs"]:
        if not isinstance(run, dict):
            raise ValueError("run-results schema requires run objects")
        spec = run.get("spec")
        tests = run.get("tests")
        if not isinstance(spec, dict) or not isinstance(
            spec.get("relative"), str
        ) or not isinstance(tests, list):
            raise ValueError(
                "run-results schema requires spec.relative and tests array"
            )
        for test in tests:
            if (
                not isinstance(test, dict)
                or not isinstance(test.get("title"), list)
                or not all(isinstance(part, str) for part in test["title"])
                or not isinstance(test.get("state"), str)
                or not isinstance(test.get("attempts"), list)
            ):
                raise ValueError(
                    "run-results schema requires title/state/attempts"
                )
            test_state = test["state"]
            raw_attempts = test["attempts"]
            assert isinstance(test_state, str)
            assert isinstance(raw_attempts, list)
            if test_state not in CYPRESS_RUN_RESULT_STATES:
                raise ValueError(
                    f"run-results test state is unsupported: {test_state}"
                )
            if not raw_attempts:
                raise ValueError(
                    "run-results tests require at least one attempt"
                )
            attempts: list[dict[str, object]] = []
            attempt_states: list[str] = []
            for index, attempt in enumerate(raw_attempts):
                if index >= MAX_ATTEMPTS_PER_TEST:
                    raise ValueError(
                        f"test exceeds the {MAX_ATTEMPTS_PER_TEST}-attempt limit"
                    )
                if not isinstance(attempt, dict) or not isinstance(
                    attempt.get("state"), str
                ):
                    raise ValueError(
                        "run-results schema requires attempt state strings"
                    )
                attempt_state = attempt["state"]
                assert isinstance(attempt_state, str)
                if attempt_state not in CYPRESS_RUN_RESULT_STATES:
                    raise ValueError(
                        "run-results attempt state is unsupported: "
                        f"{attempt_state}"
                    )
                attempt_states.append(attempt_state)
                attempts.append(
                    {
                        "attempt": index,
                        "state": bounded_string(attempt_state),
                        "error": error_text(
                            attempt.get("error")
                            or attempt.get("displayError")
                        ),
                    }
                )
            if attempt_states[-1] != test_state:
                raise ValueError(
                    f"run-results final test state={test_state} contradicts "
                    f"last attempt state={attempt_states[-1]}"
                )
            records.append(
                {
                    "file": bounded_string(spec["relative"]),
                    "title": bounded_string(" ".join(test["title"])),
                    "state": bounded_string(test_state),
                    "duration": bounded_scalar(test.get("duration")),
                    "attempts": attempts,
                }
            )
            if len(records) > MAX_OUTPUT_RECORDS:
                raise ValueError(
                    f"run-results exceeds the {MAX_OUTPUT_RECORDS}-record limit"
                )
    return records


def media_metadata(
    artifact_root: Path,
    artifact: Path,
) -> dict[str, object]:
    suffix = artifact.suffix.lower()
    if suffix == ".png":
        kind = "png"
        max_bytes = MAX_PNG_BYTES
        expected_magic = b"\x89PNG\r\n\x1a\n"
    elif suffix == ".mp4":
        kind = "mp4"
        max_bytes = MAX_MP4_BYTES
        expected_magic = None
    else:
        raise ValueError("media mode accepts only .png and .mp4 files")

    snapshot_directory: Path | None = None
    snapshot_path: Path | None = None
    try:
        with open_artifact_descriptor(
            artifact_root,
            artifact,
            max_bytes,
        ) as (artifact_fd, metadata):
            header = os.read(artifact_fd, 16)
            if expected_magic is not None and not header.startswith(
                expected_magic
            ):
                raise ValueError("PNG artifact has an invalid signature")
            if kind == "mp4" and (
                len(header) < 12 or header[4:8] != b"ftyp"
            ):
                raise ValueError("MP4 artifact has an invalid ftyp signature")
            os.lseek(artifact_fd, 0, os.SEEK_SET)

            snapshot_directory = Path(
                tempfile.mkdtemp(prefix="e2e-cypress-media-")
            )
            os.chmod(snapshot_directory, stat.S_IRWXU)
            snapshot_path = snapshot_directory / f"artifact.{kind}"
            snapshot_flags = (
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            snapshot_fd = os.open(
                snapshot_path,
                snapshot_flags,
                stat.S_IRUSR,
            )
            digest = hashlib.sha256()
            copied = 0
            try:
                while True:
                    chunk = os.read(artifact_fd, 64 * 1024)
                    if not chunk:
                        break
                    copied += len(chunk)
                    if copied > max_bytes:
                        raise ValueError(
                            f"artifact exceeds the {max_bytes}-byte limit: "
                            f"{artifact}"
                        )
                    digest.update(chunk)
                    write_all(snapshot_fd, chunk)
                require_unchanged_descriptor(
                    artifact_fd,
                    metadata,
                    artifact,
                )
                if copied != metadata.st_size:
                    raise ValueError(
                        f"artifact changed while being read: {artifact}"
                    )
                os.fsync(snapshot_fd)
                os.fchmod(snapshot_fd, stat.S_IRUSR)
                snapshot_metadata = os.fstat(snapshot_fd)
                if (
                    not stat.S_ISREG(snapshot_metadata.st_mode)
                    or snapshot_metadata.st_size != copied
                    or stat.S_IMODE(snapshot_metadata.st_mode)
                    != stat.S_IRUSR
                ):
                    raise ValueError("media snapshot validation failed")
            finally:
                os.close(snapshot_fd)

        return {
            "path": str(snapshot_path),
            "snapshot_directory": str(snapshot_directory),
            "kind": kind,
            "size": copied,
            "sha256": digest.hexdigest(),
            "lifecycle": (
                "temporary owner-only snapshot; delete snapshot_directory "
                "after the viewer closes"
            ),
        }
    except BaseException:
        remove_failed_snapshot(snapshot_path, snapshot_directory)
        raise


def emit_json(value: object) -> None:
    value = redact_for_output(value)
    validate_json_shape(value)
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(payload) > MAX_OUTPUT_BYTES:
        raise ValueError(f"output exceeds the {MAX_OUTPUT_BYTES}-byte limit")
    print(payload.decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("mochawesome", "run-results", "media"),
    )
    parser.add_argument(
        "--artifact-root",
        required=True,
        type=Path,
        help="trusted non-symlink directory containing the artifact",
    )
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()

    try:
        require_secure_descriptor_support()
        if args.mode == "media":
            emit_json(media_metadata(args.artifact_root, args.artifact))
        else:
            _, data = read_artifact(
                args.artifact_root,
                args.artifact,
                MAX_JSON_BYTES,
            )
            report = load_json(data)
            records = (
                mochawesome_output(report)
                if args.mode == "mochawesome"
                else run_result_records(report)
            )
            emit_json(records)
    except (OSError, ValueError) as exc:
        parser.error(redact_diagnostic(exc))


if __name__ == "__main__":
    main()
