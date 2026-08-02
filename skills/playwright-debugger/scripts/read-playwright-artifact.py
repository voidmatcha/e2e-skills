#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read Playwright JSON reports and trace entries through bounded trust gates."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit
import zipfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from residual_credentials import (  # noqa: E402
    AUTH_SCHEME_NAMES,
    build_assignment_redactor,
    build_header_pattern,
    has_residual_credential,
    header_substitution,
    redact_credential_shapes,
    sanitize_diagnostic,
)


MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_VIDEO_BYTES = 512 * 1024 * 1024
MAX_JSON_DEPTH = 100
MAX_JSON_NODES = 200_000
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_OUTPUT_RECORDS = 10_000
MAX_ATTEMPTS_PER_TEST = 100
MAX_STRING_CHARS = 4_000
MAX_ZIP_ENTRIES = 10_000
MAX_ZIP_ENTRY_BYTES = 64 * 1024 * 1024
MAX_SELECTED_ENTRY_BYTES = 32 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_NDJSON_LINE_BYTES = 1024 * 1024
EXPECTED_TRACE_ENTRY = re.compile(r"(?:[0-9]+-)?trace\.(?:trace|network)\Z")
REDACTED = "[REDACTED]"
SENSITIVE_KEY_FRAGMENTS = (
    "apikey",
    "authorization",
    "body",
    "clientsecret",
    "cookie",
    "credential",
    "formdata",
    "passwd",
    "password",
    "payload",
    "postdata",
    "query",
    "secret",
    "token",
)
REDACT_TEXT_ASSIGNMENTS = build_assignment_redactor(
    "body|post[_-]?data|payload"
)
SENSITIVE_HEADER = build_header_pattern()
URL = re.compile(r"https?://[^\s\"'<>]+")
QUERY_ASSIGNMENT = re.compile(r"([?&][^=\s&#]+)=([^&#\s]*)")
# Scheme list owned by residual_credentials so this redactor and the gate
# that checks its output can never disagree about which schemes exist.
AUTH_SCHEME = re.compile(
    r"(?i)\b(?:" + AUTH_SCHEME_NAMES + r")\s+[A-Za-z0-9._~+/=-]+"
)
ALLOWED_ZIP_METHODS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
PLAYWRIGHT_OUTCOMES = {"expected", "unexpected", "flaky", "skipped"}
PLAYWRIGHT_RESULT_STATUSES = {
    "passed",
    "failed",
    "timedOut",
    "skipped",
    "interrupted",
}
PLAYWRIGHT_STAT_COUNTERS = ("expected", "skipped", "unexpected", "flaky")
SECURE_OPEN_PLATFORM_ERROR = (
    "secure artifact reading requires POSIX descriptor-relative no-follow "
    "filesystem APIs (macOS/Linux); on Windows run this reader inside WSL "
    "against artifacts stored under a trusted WSL filesystem root"
)


def require_secure_descriptor_support() -> None:
    if (
        not isinstance(getattr(os, "O_DIRECTORY", None), int)
        or not isinstance(getattr(os, "O_NOFOLLOW", None), int)
        or os.open not in getattr(os, "supports_dir_fd", set())
    ):
        raise ValueError(SECURE_OPEN_PLATFORM_ERROR)


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


def parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"non-finite JSON number is forbidden: {token}")
    return value


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
        parse_float=parse_finite_float,
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
    require_secure_descriptor_support()
    absolute = Path(os.path.abspath(path))
    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | close_on_exec
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
    report_root: Path,
    artifact: Path,
    max_bytes: int,
) -> Iterator[tuple[int, os.stat_result]]:
    require_secure_descriptor_support()
    absolute_root = Path(os.path.abspath(report_root))
    absolute_artifact = Path(os.path.abspath(artifact))
    try:
        lexical_relative = absolute_artifact.relative_to(absolute_root)
    except ValueError as exc:
        raise ValueError(f"artifact is outside the report root: {artifact}") from exc
    if not lexical_relative.parts:
        raise ValueError(f"artifact is not a regular file: {artifact}")

    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | close_on_exec
    file_flags = (
        os.O_RDONLY
        | os.O_NOFOLLOW
        | getattr(os, "O_NONBLOCK", 0)
        | close_on_exec
    )
    root_fd = open_trusted_directory(absolute_root, "report root")
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


def read_bounded_file(
    report_root: Path,
    artifact: Path,
    max_bytes: int,
) -> bytes:
    with open_artifact_descriptor(
        report_root,
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
        current_metadata = require_unchanged_descriptor(
            artifact_fd,
            metadata,
            artifact,
        )
        if len(data) != current_metadata.st_size:
            raise ValueError(f"artifact changed while being read: {artifact}")
        return data


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


def media_kind_and_limit(artifact: Path) -> tuple[str, int]:
    suffix = artifact.suffix.lower()
    if suffix == ".png":
        return "png", MAX_IMAGE_BYTES
    if suffix in {".jpg", ".jpeg"}:
        return "jpeg", MAX_IMAGE_BYTES
    if suffix == ".webm":
        return "webm", MAX_VIDEO_BYTES
    raise ValueError(
        "media mode accepts only Playwright .png, .jpg/.jpeg, and .webm files"
    )


def validate_media_header(kind: str, header: bytes) -> None:
    if kind == "png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("PNG artifact has an invalid signature")
    if kind == "jpeg" and not header.startswith(b"\xff\xd8\xff"):
        raise ValueError("JPEG artifact has an invalid signature")
    if kind == "webm" and (
        not header.startswith(b"\x1aE\xdf\xa3") or b"webm" not in header
    ):
        raise ValueError("WebM artifact has an invalid EBML/WebM signature")


def snapshot_metadata(
    report_root: Path,
    artifact: Path,
    *,
    kind: str,
    max_bytes: int,
    validate_header: bool,
) -> dict[str, object]:
    snapshot_directory: Path | None = None
    snapshot_path: Path | None = None
    try:
        with open_artifact_descriptor(
            report_root,
            artifact,
            max_bytes,
        ) as (artifact_fd, metadata):
            header = os.read(artifact_fd, 4096)
            if validate_header:
                validate_media_header(kind, header)
            os.lseek(artifact_fd, 0, os.SEEK_SET)

            snapshot_directory = Path(
                tempfile.mkdtemp(prefix="e2e-playwright-artifact-")
            )
            os.chmod(snapshot_directory, stat.S_IRWXU)
            snapshot_path = snapshot_directory / f"artifact.{kind}"
            snapshot_fd = os.open(
                snapshot_path,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
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
                current_metadata = require_unchanged_descriptor(
                    artifact_fd,
                    metadata,
                    artifact,
                )
                if copied != current_metadata.st_size:
                    raise ValueError(f"artifact changed while being read: {artifact}")
                os.fsync(snapshot_fd)
                os.fchmod(snapshot_fd, stat.S_IRUSR)
                snapshot_stat = os.fstat(snapshot_fd)
                if (
                    not stat.S_ISREG(snapshot_stat.st_mode)
                    or snapshot_stat.st_size != copied
                    or stat.S_IMODE(snapshot_stat.st_mode) != stat.S_IRUSR
                ):
                    raise ValueError("artifact snapshot validation failed")
            finally:
                os.close(snapshot_fd)

        return {
            "path": str(snapshot_path),
            "snapshot_directory": str(snapshot_directory),
            "kind": kind,
            "size": copied,
            "sha256": digest.hexdigest(),
            "lifecycle": (
                "temporary owner-only read-only snapshot; delete "
                "snapshot_directory after the viewer closes"
            ),
        }
    except BaseException:
        remove_failed_snapshot(snapshot_path, snapshot_directory)
        raise


def media_metadata(report_root: Path, artifact: Path) -> dict[str, object]:
    kind, max_bytes = media_kind_and_limit(artifact)
    return snapshot_metadata(
        report_root,
        artifact,
        kind=kind,
        max_bytes=max_bytes,
        validate_header=True,
    )


def snapshot_validated_bytes(
    data: bytes,
    *,
    kind: str,
) -> dict[str, object]:
    snapshot_directory: Path | None = None
    snapshot_path: Path | None = None
    try:
        snapshot_directory = Path(
            tempfile.mkdtemp(prefix="e2e-playwright-artifact-")
        )
        os.chmod(snapshot_directory, stat.S_IRWXU)
        snapshot_path = snapshot_directory / f"artifact.{kind}"
        snapshot_fd = os.open(
            snapshot_path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            stat.S_IRUSR,
        )
        try:
            write_all(snapshot_fd, data)
            os.fsync(snapshot_fd)
            os.fchmod(snapshot_fd, stat.S_IRUSR)
            snapshot_stat = os.fstat(snapshot_fd)
            if (
                not stat.S_ISREG(snapshot_stat.st_mode)
                or snapshot_stat.st_size != len(data)
                or stat.S_IMODE(snapshot_stat.st_mode) != stat.S_IRUSR
            ):
                raise ValueError("artifact snapshot validation failed")
        finally:
            os.close(snapshot_fd)
        return {
            "path": str(snapshot_path),
            "snapshot_directory": str(snapshot_directory),
            "kind": kind,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "lifecycle": (
                "temporary owner-only read-only snapshot; delete "
                "snapshot_directory after the viewer closes"
            ),
        }
    except BaseException:
        remove_failed_snapshot(snapshot_path, snapshot_directory)
        raise


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


def bounded_string(value: object) -> str | None:
    if value is None:
        return None
    return redact_string(str(value))[:MAX_STRING_CHARS]


def bounded_scalar(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return bounded_string(value)
    return None


def bounded_location(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {
        "file": bounded_string(value.get("file")),
        "line": bounded_scalar(value.get("line")),
        "column": bounded_scalar(value.get("column")),
    }


def is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact_url(match: re.Match[str]) -> str:
    raw_url = match.group(0)
    trailing = ""
    while raw_url and raw_url[-1] in ".,;:)]}":
        trailing = raw_url[-1] + trailing
        raw_url = raw_url[:-1]
    try:
        parts = urlsplit(raw_url)
        hostname = parts.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        if parts.port is not None:
            hostname = f"{hostname}:{parts.port}"
        query = QUERY_ASSIGNMENT.sub(
            rf"\1={REDACTED}",
            f"?{parts.query}",
        )[1:]
        sanitized = urlunsplit(
            (parts.scheme, hostname, parts.path, query, parts.fragment)
        )
    except ValueError:
        sanitized = QUERY_ASSIGNMENT.sub(
            rf"\1={REDACTED}",
            raw_url,
        )
        sanitized = re.sub(r"(?<=://)[^/@\s]+@", "", sanitized)
    return sanitized + trailing


def redact_string(value: str) -> str:
    redacted = URL.sub(redact_url, value)
    redacted = AUTH_SCHEME.sub(REDACTED, redacted)
    redacted = redact_credential_shapes(redacted)
    redacted = SENSITIVE_HEADER.sub(header_substitution, redacted)
    redacted = REDACT_TEXT_ASSIGNMENTS(redacted)
    return QUERY_ASSIGNMENT.sub(rf"\1={REDACTED}", redacted)


def redact_sensitive(value: object, parent_key: object = None) -> object:
    if is_sensitive_key(parent_key):
        return REDACTED
    if isinstance(value, dict):
        header_name = value.get("name")
        sensitive_named_value = is_sensitive_key(header_name)
        return {
            key: (
                REDACTED
                if sensitive_named_value and key == "value"
                else redact_sensitive(item, key)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value



def error_message(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    return bounded_string(value.get("message"))


def synthetic_error_records(report: object) -> list[dict[str, object]]:
    assert isinstance(report, dict)
    sources: list[tuple[str | None, object]] = [
        (None, report.get("errors", []))
    ]
    for container_name in ("projects",):
        projects = report.get(container_name, [])
        if not isinstance(projects, list):
            raise ValueError(
                f"report JSON schema requires {container_name} to be an array"
            )
        for project in projects:
            if not isinstance(project, dict):
                raise ValueError("report JSON schema requires project objects")
            sources.append(
                (bounded_string(project.get("name")), project.get("errors", []))
            )
    config = report.get("config")
    if config is not None:
        if not isinstance(config, dict):
            raise ValueError("report JSON schema requires config to be an object")
        config_projects = config.get("projects", [])
        if not isinstance(config_projects, list):
            raise ValueError(
                "report JSON schema requires config.projects to be an array"
            )
        for project in config_projects:
            if not isinstance(project, dict):
                raise ValueError(
                    "report JSON schema requires config project objects"
                )
            sources.append(
                (bounded_string(project.get("name")), project.get("errors", []))
            )

    records: list[dict[str, object]] = []
    for project_name, errors in sources:
        if not isinstance(errors, list):
            raise ValueError("report JSON schema requires errors arrays")
        for error in errors:
            if not isinstance(error, dict):
                raise ValueError("report JSON schema requires error objects")
            message = error.get("message")
            stack = error.get("stack")
            if not isinstance(message, str) and not isinstance(stack, str):
                raise ValueError(
                    "report JSON schema requires error message or stack"
                )
            location = bounded_location(error.get("location"))
            records.append(
                {
                    "title": (
                        "[project error]"
                        if project_name is not None
                        else "[global error]"
                    ),
                    "file": location["file"] if location else None,
                    "line": location["line"] if location else None,
                    "projectName": project_name,
                    "outcome": "unexpected",
                    "retries": 0,
                    "attempts": [
                        {
                            "attempt": 0,
                            "status": "failed",
                            "duration": None,
                            "error": bounded_string(
                                message if isinstance(message, str) else stack
                            ),
                            "errorLocation": location,
                        }
                    ],
                }
            )
            if len(records) > MAX_OUTPUT_RECORDS:
                raise ValueError(
                    f"report exceeds the {MAX_OUTPUT_RECORDS}-error limit"
                )
    return records


def computed_test_outcome(test: dict[str, object]) -> str:
    expected_status = test.get("expectedStatus", "passed")
    if (
        not isinstance(expected_status, str)
        or expected_status not in PLAYWRIGHT_RESULT_STATUSES
    ):
        raise ValueError(
            "report JSON schema requires a valid test expectedStatus"
        )
    results = test.get("results")
    assert isinstance(results, list)
    skipped = 0
    expected = 0
    unexpected = 0
    for result in results:
        assert isinstance(result, dict)
        status = result.get("status")
        if (
            not isinstance(status, str)
            or status not in PLAYWRIGHT_RESULT_STATUSES
        ):
            raise ValueError(
                "report result status contradicts the Playwright JSON schema"
            )
        if status == "interrupted":
            unexpected += 1
            continue
        if status == "skipped" and expected_status == "skipped":
            skipped += 1
        elif status == "skipped":
            continue
        elif status == expected_status:
            expected += 1
        else:
            unexpected += 1
    if expected == 0 and unexpected == 0:
        return "skipped"
    if unexpected == 0:
        return "expected"
    if expected == 0 and skipped == 0:
        return "unexpected"
    return "flaky"


def report_specs(report: object) -> list[dict[str, object]]:
    if not isinstance(report, dict) or not isinstance(report.get("suites"), list):
        raise ValueError("report JSON schema requires a root suites array")

    specs: list[dict[str, object]] = []
    canonical_spec_ids: set[int] = set()
    suites = report["suites"]
    suite_stack = list(reversed(suites))
    while suite_stack:
        suite = suite_stack.pop()
        if not isinstance(suite, dict):
            raise ValueError("report JSON schema requires suite objects")
        child_suites = suite.get("suites", [])
        suite_specs = suite.get("specs")
        if not isinstance(child_suites, list) or not isinstance(suite_specs, list):
            raise ValueError(
                "report JSON schema requires suites/specs arrays on every suite"
            )
        suite_stack.extend(reversed(child_suites))
        for spec in suite_specs:
            if (
                not isinstance(spec, dict)
                or not isinstance(spec.get("ok"), bool)
                or not isinstance(spec.get("tests"), list)
            ):
                raise ValueError(
                    "report JSON schema requires each spec to have bool ok "
                    "and tests array"
                )
            canonical_spec_ids.add(id(spec))
            specs.append(spec)
            if len(specs) > MAX_OUTPUT_RECORDS:
                raise ValueError(
                    f"report exceeds the {MAX_OUTPUT_RECORDS}-spec limit"
                )
            for test in spec["tests"]:
                if (
                    not isinstance(test, dict)
                    or not isinstance(test.get("status"), str)
                    or not isinstance(test.get("results"), list)
                ):
                    raise ValueError(
                        "report JSON schema requires test status and results array"
                    )
                outcome = test["status"]
                if outcome not in PLAYWRIGHT_OUTCOMES:
                    raise ValueError(
                        "report JSON schema requires a valid test status"
                    )
                if len(test["results"]) > MAX_ATTEMPTS_PER_TEST:
                    raise ValueError(
                        f"test exceeds the "
                        f"{MAX_ATTEMPTS_PER_TEST}-attempt limit"
                    )
                for result in test["results"]:
                    if not isinstance(result, dict):
                        raise ValueError(
                            "report JSON schema requires result objects"
                        )
                computed_outcome = computed_test_outcome(test)
                if outcome != computed_outcome:
                    raise ValueError(
                        f"report test status={outcome} contradicts results "
                        f"outcome={computed_outcome}"
                    )
            expected_ok = all(
                test["status"] in {"expected", "flaky", "skipped"}
                for test in spec["tests"]
            )
            if spec["ok"] != expected_ok:
                raise ValueError(
                    f"report spec.ok={spec['ok']} contradicts test statuses"
                )

    # A spec-shaped object outside suites/specs is ambiguous. Reject it rather
    # than silently returning an empty/partial failure set.
    stack = [report]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if (
                "ok" in current
                and "tests" in current
                and id(current) not in canonical_spec_ids
            ):
                raise ValueError(
                    "report JSON schema contains a spec-shaped object outside "
                    "suites/specs"
                )
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return specs


def validate_report_stats(
    report: object,
    specs: list[dict[str, object]],
) -> None:
    assert isinstance(report, dict)
    stats = report.get("stats")
    if not isinstance(stats, dict):
        raise ValueError("report JSON schema requires a root stats object")
    counters: dict[str, int] = {}
    for field in PLAYWRIGHT_STAT_COUNTERS:
        value = stats.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"report stats.{field} must be a nonnegative integer"
            )
        counters[field] = value
    duration = stats.get("duration")
    if duration is not None and (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or duration < 0
    ):
        raise ValueError("report stats.duration must be a nonnegative number")
    start_time = stats.get("startTime")
    if start_time is not None and not isinstance(start_time, str):
        raise ValueError("report stats.startTime must be a string")

    parsed = {field: 0 for field in PLAYWRIGHT_STAT_COUNTERS}
    for spec in specs:
        tests = spec["tests"]
        assert isinstance(tests, list)
        for test in tests:
            assert isinstance(test, dict)
            outcome = test["status"]
            assert isinstance(outcome, str)
            parsed[outcome] += 1
    for field in PLAYWRIGHT_STAT_COUNTERS:
        if counters[field] != parsed[field]:
            raise ValueError(
                # Explanation before the numbers, deliberately: the shared
                # redactor treats `passes=2` as a credential assignment and
                # its value extent runs to the end of the line, so a reason
                # written after a `key=value` would be redacted away with
                # the counter and the operator would be told only that
                # something was wrong.
                f"report stats.{field} contradicts parsed counters "
                f"(reported {counters[field]}, parsed {parsed[field]})"
            )


def validate_report_json(data: bytes | str) -> list[dict[str, object]]:
    """Parse a Playwright JSON report and return its validated reader records."""
    try:
        report = strict_json_loads(data)
    except ValueError as exc:
        raise ValueError(f"invalid report JSON: {exc}") from exc
    validate_json_shape(report)
    records = report_records(report)
    encode_json(records)
    return records


def report_records(report: object) -> list[dict[str, object]]:
    records = synthetic_error_records(report)
    specs = report_specs(report)
    validate_report_stats(report, specs)
    for spec in specs:
        tests = spec.get("tests")
        assert isinstance(tests, list)
        for test in tests:
            if not isinstance(test, dict):
                continue
            outcome = test.get("status")
            if outcome in {"expected", "skipped"}:
                continue
            raw_attempts = test.get("results")
            attempts: list[dict[str, object]] = []
            if isinstance(raw_attempts, list):
                for index, result in enumerate(raw_attempts):
                    if index >= MAX_ATTEMPTS_PER_TEST:
                        raise ValueError(
                            f"test exceeds the "
                            f"{MAX_ATTEMPTS_PER_TEST}-attempt limit"
                        )
                    if not isinstance(result, dict):
                        continue
                    retry = result.get("retry")
                    error = result.get("error")
                    nested_error_location = (
                        error.get("location")
                        if isinstance(error, dict)
                        else None
                    )
                    attempts.append(
                        {
                            "attempt": retry if isinstance(retry, int) else index,
                            "status": bounded_string(result.get("status")),
                            "duration": bounded_scalar(result.get("duration")),
                            "error": error_message(error),
                            "errorLocation": bounded_location(
                                nested_error_location
                                if isinstance(nested_error_location, dict)
                                else result.get("errorLocation")
                            ),
                        }
                    )
            records.append(
                {
                    "title": bounded_string(spec.get("title")),
                    "file": bounded_string(spec.get("file")),
                    "line": bounded_scalar(spec.get("line")),
                    "projectName": bounded_string(test.get("projectName")),
                    "outcome": bounded_string(outcome),
                    "retries": max(len(attempts) - 1, 0),
                    "attempts": attempts,
                }
            )
            if len(records) > MAX_OUTPUT_RECORDS:
                raise ValueError(
                    f"report exceeds the {MAX_OUTPUT_RECORDS}-record limit"
                )
    return records


def safe_zip_infos(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise ValueError(f"ZIP exceeds the {MAX_ZIP_ENTRIES}-entry limit")
    by_name: dict[str, zipfile.ZipInfo] = {}
    total_size = 0
    for index, info in enumerate(infos):
        if info.filename in by_name:
            raise ValueError(f"duplicate ZIP entry at entry index {index}")
        by_name[info.filename] = info
        path = PurePosixPath(info.filename)
        if (
            not info.filename
            or info.filename.startswith("/")
            or "\\" in info.filename
            or ".." in path.parts
        ):
            raise ValueError(f"unsafe ZIP entry name at entry index {index}")
        mode = info.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        name_is_directory = info.filename.endswith("/")
        mode_is_directory = bool(file_type) and stat.S_ISDIR(mode)
        if file_type and name_is_directory != mode_is_directory:
            raise ValueError(
                "ZIP directory mode/name disagreement at entry index "
                f"{index}"
            )
        if stat.S_ISLNK(mode):
            raise ValueError(
                f"symlink ZIP entry is forbidden at entry index {index}"
            )
        if file_type and not (
            stat.S_ISREG(mode) or stat.S_ISDIR(mode)
        ):
            raise ValueError(
                "special-file ZIP entry is forbidden "
                f"at entry index {index}"
            )
        if info.flag_bits & 0x1:
            raise ValueError(
                f"encrypted ZIP entry is forbidden at entry index {index}"
            )
        if info.compress_type not in ALLOWED_ZIP_METHODS:
            raise ValueError(
                f"unsupported ZIP compression method at entry index {index}"
            )
        if info.file_size > MAX_ZIP_ENTRY_BYTES:
            raise ValueError(
                f"ZIP entry exceeds the {MAX_ZIP_ENTRY_BYTES}-byte limit "
                f"at entry index {index}"
            )
        total_size += info.file_size
        if total_size > MAX_ZIP_TOTAL_BYTES:
            raise ValueError(
                f"ZIP exceeds the {MAX_ZIP_TOTAL_BYTES}-byte expanded limit"
            )
        if info.file_size:
            if not info.compress_size:
                raise ValueError(
                    "ZIP entry has an invalid compression ratio "
                    f"at entry index {index}"
                )
            ratio = info.file_size / info.compress_size
            if ratio > MAX_COMPRESSION_RATIO:
                raise ValueError(
                    f"ZIP entry exceeds the {MAX_COMPRESSION_RATIO}:1 "
                    f"compression ratio at entry index {index}"
                )
    return by_name


def open_trace_archive(
    data: bytes,
) -> tuple[zipfile.ZipFile, dict[str, zipfile.ZipInfo]]:
    archive: zipfile.ZipFile | None = None
    try:
        archive = zipfile.ZipFile(BytesIO(data))
        return archive, safe_zip_infos(archive)
    except ValueError:
        if archive is not None:
            archive.close()
        raise
    except (zipfile.BadZipFile, RuntimeError) as exc:
        if archive is not None:
            archive.close()
        raise ValueError(f"invalid or unsupported ZIP: {exc}") from exc


def validate_trace_archive_payloads(data: bytes) -> None:
    """Read every member fully so CRC and decompression failures fail closed."""
    archive, infos = open_trace_archive(data)
    try:
        with archive:
            for index, info in enumerate(infos.values()):
                if info.is_dir():
                    continue
                expanded = 0
                with archive.open(info, "r") as source:
                    while True:
                        chunk = source.read(64 * 1024)
                        if not chunk:
                            break
                        expanded += len(chunk)
                        if expanded > info.file_size:
                            raise ValueError(
                                "ZIP entry expanded beyond its declared size "
                                f"at entry index {index}"
                            )
                if expanded != info.file_size:
                    raise ValueError(
                        "ZIP entry size contradicts its payload "
                        f"at entry index {index}"
                    )
    except (zipfile.BadZipFile, RuntimeError, EOFError, zlib.error) as exc:
        raise ValueError(f"invalid or corrupt ZIP entry payload: {exc}") from exc


def projected_error(value: object) -> dict[str, object] | None:
    if isinstance(value, str):
        return {"message": trace_string(value)}
    if not isinstance(value, dict):
        return None
    return {
        "name": trace_string(value.get("name")),
        "message": trace_string(value.get("message")),
        "stack": trace_string(value.get("stack")),
    }


def trace_string(value: object) -> str | None:
    return (
        redact_string(value)[:MAX_STRING_CHARS]
        if isinstance(value, str)
        else None
    )


def projected_trace_location(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {
        "file": trace_string(value.get("file")),
        "line": (
            value.get("line")
            if isinstance(value.get("line"), int)
            and not isinstance(value.get("line"), bool)
            else None
        ),
        "column": (
            value.get("column")
            if isinstance(value.get("column"), int)
            and not isinstance(value.get("column"), bool)
            else None
        ),
    }


def project_trace_record(record: object, entry: str) -> dict[str, object] | None:
    if not isinstance(record, dict):
        return None
    if entry.endswith("trace.network"):
        if record.get("type") != "resource-snapshot":
            return None
        snapshot = record.get("snapshot")
        if not isinstance(snapshot, dict):
            return None
        request = snapshot.get("request")
        response = snapshot.get("response")
        request = request if isinstance(request, dict) else {}
        response = response if isinstance(response, dict) else {}
        status = response.get("status")
        failure = (
            snapshot.get("_failureText")
            or response.get("errorText")
            or request.get("failure")
        )
        if isinstance(failure, dict):
            failure = failure.get("errorText") or failure.get("message")
        failure_text = trace_string(failure)
        if not (
            isinstance(status, (int, float))
            and not isinstance(status, bool)
            and status >= 400
        ) and not failure_text:
            return None
        return redact_sensitive(
            {
                "kind": "network-error",
                "method": trace_string(request.get("method")),
                "url": trace_string(request.get("url") or snapshot.get("url")),
                "status": (
                    status
                    if isinstance(status, (int, float))
                    and not isinstance(status, bool)
                    else None
                ),
                "statusText": trace_string(response.get("statusText")),
                "failure": failure_text,
            }
        )

    record_type = record.get("type")
    if record_type == "after" and record.get("error") is not None:
        return redact_sensitive(
            {
                "kind": "failed-action",
                "apiName": trace_string(record.get("apiName")),
                "callId": trace_string(record.get("callId")),
                "error": projected_error(record.get("error")),
            }
        )
    if (
        record_type == "console"
        and str(record.get("messageType", "")).lower() == "error"
    ):
        return redact_sensitive(
            {
                "kind": "console-error",
                "text": trace_string(record.get("text")),
                "location": projected_trace_location(record.get("location")),
            }
        )
    method = str(record.get("method", "")).lower().replace("-", "")
    normalized_type = str(record_type or "").lower().replace("-", "")
    if method == "pageerror" or normalized_type == "pageerror":
        params = record.get("params")
        params = params if isinstance(params, dict) else {}
        error = (
            params.get("error")
            or record.get("error")
            or params.get("message")
            or record.get("message")
        )
        return redact_sensitive(
            {
                "kind": "page-error",
                "error": projected_error(error),
            }
        )
    return None


def read_trace_entry(data: bytes, entry: str) -> list[object]:
    if not EXPECTED_TRACE_ENTRY.fullmatch(entry):
        raise ValueError(
            "entry is not an expected trace entry "
            "(trace.trace, trace.network, or a numeric-prefixed equivalent)"
        )
    archive, infos = open_trace_archive(data)
    try:
        with archive:
            info = infos.get(entry)
            if info is None:
                raise ValueError(f"expected trace entry is absent: {entry}")
            mode = info.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if (
                info.is_dir()
                or stat.S_ISDIR(mode)
                or (file_type and not stat.S_ISREG(mode))
            ):
                raise ValueError(
                    f"selected trace entry is not a regular file: {entry}"
                )
            if info.file_size > MAX_SELECTED_ENTRY_BYTES:
                raise ValueError(
                    f"selected entry exceeds the "
                    f"{MAX_SELECTED_ENTRY_BYTES}-byte limit: {entry}"
                )
            records: list[object] = []
            projected_bytes = 2
            selected_bytes = 0
            with archive.open(info, "r") as source:
                line_number = 0
                while True:
                    line = source.readline(MAX_NDJSON_LINE_BYTES + 2)
                    if not line:
                        break
                    line_number += 1
                    selected_bytes += len(line)
                    if selected_bytes > MAX_SELECTED_ENTRY_BYTES:
                        raise ValueError(
                            f"selected entry exceeds the "
                            f"{MAX_SELECTED_ENTRY_BYTES}-byte limit: {entry}"
                        )
                    if len(line.rstrip(b"\r\n")) > MAX_NDJSON_LINE_BYTES:
                        raise ValueError(
                            f"trace line {line_number} exceeds the "
                            f"{MAX_NDJSON_LINE_BYTES}-byte limit"
                        )
                    if not line.strip():
                        continue
                    try:
                        record = strict_json_loads(line)
                    except ValueError as exc:
                        raise ValueError(
                            f"invalid trace JSON on line {line_number}: {exc}"
                        ) from exc
                    validate_json_shape(record)
                    projected = project_trace_record(record, entry)
                    if projected is None:
                        continue
                    encoded = json.dumps(
                        projected,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                    projected_bytes += len(encoded) + (1 if records else 0)
                    if projected_bytes > MAX_OUTPUT_BYTES:
                        raise ValueError(
                            f"trace projection exceeds the "
                            f"{MAX_OUTPUT_BYTES}-byte output limit"
                        )
                    records.append(projected)
                    if len(records) > MAX_OUTPUT_RECORDS:
                        raise ValueError(
                            f"trace exceeds the "
                            f"{MAX_OUTPUT_RECORDS}-diagnostic output limit"
                        )
            return records
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError(f"invalid or corrupt ZIP entry: {exc}") from exc


def encode_json(value: object) -> bytes:
    value = redact_sensitive(value)
    if redact_sensitive(value) != value:
        raise ValueError("credential redaction left residual sensitive output")
    validate_json_shape(value)
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if has_residual_credential(payload.decode("utf-8")):
        raise ValueError("credential redaction left residual sensitive output")
    if len(payload) > MAX_OUTPUT_BYTES:
        raise ValueError(f"output exceeds the {MAX_OUTPUT_BYTES}-byte limit")
    return payload


def emit_json(value: object) -> None:
    print(encode_json(value).decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    for mode in ("report", "trace", "media", "trace-snapshot"):
        command = subparsers.add_parser(mode)
        command.add_argument(
            "--report-root",
            required=True,
            type=Path,
            help="trusted non-symlink directory containing the artifact",
        )
        command.add_argument("artifact", type=Path)
        if mode == "trace":
            selection = command.add_mutually_exclusive_group(required=True)
            selection.add_argument("--entry")
            selection.add_argument(
                "--list",
                action="store_true",
                help="list only expected trace JSON entries",
            )
    args = parser.parse_args()

    try:
        if args.mode == "report":
            data = read_bounded_file(
                args.report_root,
                args.artifact,
                MAX_REPORT_BYTES,
            )
            emit_json(validate_report_json(data))
        elif args.mode == "trace":
            data = read_bounded_file(
                args.report_root,
                args.artifact,
                MAX_ARCHIVE_BYTES,
            )
            if args.list:
                archive, infos = open_trace_archive(data)
                with archive:
                    emit_json(
                        sorted(
                            name
                            for name, info in infos.items()
                            if not info.is_dir()
                            and EXPECTED_TRACE_ENTRY.fullmatch(name)
                        )
                    )
            else:
                emit_json(read_trace_entry(data, args.entry))
        elif args.mode == "media":
            emit_json(media_metadata(args.report_root, args.artifact))
        else:
            if args.artifact.suffix.lower() != ".zip":
                raise ValueError("trace-snapshot mode accepts only .zip files")
            data = read_bounded_file(
                args.report_root,
                args.artifact,
                MAX_ARCHIVE_BYTES,
            )
            validate_trace_archive_payloads(data)
            emit_json(snapshot_validated_bytes(data, kind="zip"))
    except (OSError, ValueError) as exc:
        parser.error(sanitize_diagnostic(exc, redact_string))


if __name__ == "__main__":
    main()
