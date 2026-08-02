#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Extract Cypress JUnit failures without losing testcase/classname association."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from redact_artifact import (
    bounded_redacted,
    redact_diagnostic,
    redact_for_output,
)


MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_REPORTS = 128
MAX_AGGREGATE_INPUT_BYTES = 16 * 1024 * 1024
MAX_XML_NODES = 100_000
MAX_XML_DEPTH = 100
MAX_FAILURE_ROWS = 10_000
MAX_AGGREGATE_FAILURE_ROWS = 10_000
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_FIELD_CHARS = 1_000
MAX_MESSAGE_CHARS = 500
XML_FEED_CHUNK_BYTES = 4 * 1024
UNSAFE_XML_DECLARATION = re.compile(br"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
XML_ENCODING_DECLARATION = re.compile(
    r"<\?xml\s+[^?]*\bencoding\s*=\s*(['\"])([^'\"]+)\1",
    re.IGNORECASE,
)
XML_BOMS = (
    b"\xef\xbb\xbf",
    b"\xff\xfe\x00\x00",
    b"\x00\x00\xfe\xff",
    b"\xff\xfe",
    b"\xfe\xff",
)


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


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def bounded(value: str, limit: int = MAX_FIELD_CHARS) -> str:
    redacted = bounded_redacted(value, limit)
    assert redacted is not None
    return redacted


def optional_nonnegative_counter(
    node: ET.Element,
    field: str,
) -> int | None:
    raw_value = node.attrib.get(field)
    if raw_value is None:
        return None
    if not raw_value.isascii() or not raw_value.isdecimal():
        raise ValueError(
            f"JUnit {local_name(node.tag)} {field} counter must be a "
            "nonnegative integer"
        )
    return int(raw_value)


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
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def read_bounded_report(report_root: Path, report: Path) -> tuple[Path, bytes]:
    directory_flags, file_flags = require_secure_descriptor_support()
    absolute_root = Path(os.path.abspath(report_root))
    absolute_report = Path(os.path.abspath(report))

    try:
        lexical_relative_report = absolute_report.relative_to(absolute_root)
    except ValueError as exc:
        raise ValueError(
            f"report is outside the report root: {report}"
        ) from exc
    if not lexical_relative_report.parts:
        raise ValueError(f"report is not a regular file: {report}")

    root_fd = open_trusted_directory(absolute_root, "report root")
    current_fd = root_fd
    opened_directory_fds: list[int] = []
    report_fd: int | None = None
    try:
        for component in lexical_relative_report.parts[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=current_fd)
            opened_directory_fds.append(next_fd)
            current_fd = next_fd
        report_fd = os.open(
            lexical_relative_report.parts[-1],
            file_flags,
            dir_fd=current_fd,
        )
        metadata = os.fstat(report_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"report is not a regular file: {report}")
        if metadata.st_size > MAX_INPUT_BYTES:
            raise ValueError(
                f"report exceeds the {MAX_INPUT_BYTES}-byte limit: {report}"
            )

        chunks: list[bytes] = []
        remaining = MAX_INPUT_BYTES + 1
        while remaining:
            chunk = os.read(report_fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_INPUT_BYTES:
            raise ValueError(
                f"report exceeds the {MAX_INPUT_BYTES}-byte limit: {report}"
            )
        current_metadata = os.fstat(report_fd)
        if (
            descriptor_fingerprint(current_metadata)
            != descriptor_fingerprint(metadata)
            or len(data) != current_metadata.st_size
        ):
            raise ValueError(f"report changed while being read: {report}")
    except OSError as exc:
        raise ValueError(
            f"unsafe, symlinked, or unreadable report path: {report}: {exc}"
        ) from exc
    finally:
        if report_fd is not None:
            os.close(report_fd)
        for directory_fd in reversed(opened_directory_fds):
            os.close(directory_fd)
        os.close(root_fd)

    if any(data.startswith(bom) for bom in XML_BOMS):
        raise ValueError(f"report must be BOM-free UTF-8 XML: {report}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"report must be UTF-8 XML: {report}: {exc}") from exc
    encoding = XML_ENCODING_DECLARATION.search(text[:1024])
    if encoding is not None and encoding.group(2).lower() not in {
        "utf-8",
        "utf8",
    }:
        raise ValueError(
            f"report XML encoding must be UTF-8: {report}"
        )
    if UNSAFE_XML_DECLARATION.search(data):
        raise ValueError(f"report contains a forbidden DOCTYPE/ENTITY declaration: {report}")
    return absolute_report, data


def parse_junit(data: bytes, path: Path) -> list[dict[str, str]]:
    parser = ET.XMLPullParser(events=("start", "end"))
    element_stack: list[ET.Element] = []
    counter_stack: list[dict[str, object]] = []
    suite_stack: list[tuple[int, str]] = []
    testcase_stack: list[dict[str, object]] = []
    rows_by_suite: dict[int, list[dict[str, str]]] = {}
    node_count = 0
    failure_count = 0
    suite_sequence = 0
    saw_root = False

    def handle_event(event: str, element: ET.Element) -> None:
        nonlocal failure_count, node_count, saw_root, suite_sequence
        tag = local_name(element.tag)
        if event == "start":
            node_count += 1
            if node_count > MAX_XML_NODES:
                raise ValueError(
                    f"report exceeds the {MAX_XML_NODES}-node limit: {path}"
                )
            depth = len(element_stack) + 1
            if depth > MAX_XML_DEPTH:
                raise ValueError(
                    f"report exceeds the {MAX_XML_DEPTH}-level depth limit: "
                    f"{path}"
                )
            parent_tag = (
                local_name(element_stack[-1].tag)
                if element_stack
                else None
            )
            if not saw_root:
                saw_root = True
                if tag not in {"testsuite", "testsuites"}:
                    raise ValueError(
                        "JUnit report root must be testsuite or testsuites: "
                        f"{path}"
                    )
            element_stack.append(element)
            if tag in {"testsuite", "testsuites"}:
                counter_stack.append(
                    {
                        "element": element,
                        "kind": tag,
                        "declared": {
                            field: optional_nonnegative_counter(element, field)
                            for field in (
                                "tests",
                                "failures",
                                "errors",
                                "skipped",
                            )
                        },
                        "actual": {
                            "tests": 0,
                            "failures": 0,
                            "errors": 0,
                            "skipped": 0,
                        },
                    }
                )
            if tag == "testsuite":
                suite_stack.append(
                    (
                        suite_sequence,
                        bounded(element.attrib.get("file", "")),
                    )
                )
                suite_sequence += 1
            if tag == "testcase":
                if parent_tag != "testsuite":
                    raise ValueError(
                        "JUnit testcase must be a direct child of testsuite"
                    )
                testcase_stack.append(
                    {
                        "element": element,
                        "counter": counter_stack[-1],
                        "suite": (
                            suite_stack[-1]
                            if parent_tag == "testsuite" and suite_stack
                            else None
                        ),
                        "file": bounded(element.attrib.get("file", "")),
                        "classname": bounded(
                            element.attrib.get("classname", "")
                        ),
                        "name": bounded(element.attrib.get("name", "")),
                        "classifications": [],
                        "rows": [],
                    }
                )
            if (
                tag in {"failure", "error", "skipped"}
                and parent_tag != "testcase"
            ):
                raise ValueError(
                    f"JUnit {tag} must be a direct child of testcase"
                )
            return

        parent = element_stack[-2] if len(element_stack) > 1 else None
        parent_tag = local_name(parent.tag) if parent is not None else None
        if (
            tag in {"failure", "error", "skipped"}
            and parent_tag == "testcase"
            and testcase_stack
        ):
            testcase = testcase_stack[-1]
            classifications = testcase["classifications"]
            assert isinstance(classifications, list)
            classifications.append(tag)
            if tag in {"failure", "error"} and testcase["suite"] is not None:
                if failure_count >= MAX_FAILURE_ROWS:
                    raise ValueError(
                        f"report exceeds the "
                        f"{MAX_FAILURE_ROWS}-failure limit: {path}"
                    )
                suite = testcase["suite"]
                assert isinstance(suite, tuple)
                message = (
                    element.attrib.get("message")
                    or (element.text or "").strip()
                )
                case_file = testcase["file"]
                assert isinstance(case_file, str)
                rows = testcase["rows"]
                assert isinstance(rows, list)
                rows.append(
                    {
                        "report": bounded(str(path)),
                        "file": case_file or suite[1],
                        "classname": str(testcase["classname"]),
                        "name": str(testcase["name"]),
                        "kind": tag,
                        "message": bounded(message, MAX_MESSAGE_CHARS),
                    }
                )
                failure_count += 1
        if tag == "testcase":
            testcase = testcase_stack.pop()
            if testcase["element"] is not element:
                raise ValueError("JUnit testcase nesting is malformed")
            classifications = testcase["classifications"]
            assert isinstance(classifications, list)
            if len(classifications) > 1:
                raise ValueError(
                    "JUnit testcase has contradictory "
                    "failure/error/skipped children"
                )
            classification = classifications[0] if classifications else None
            counter = testcase["counter"]
            assert isinstance(counter, dict)
            actual = counter["actual"]
            assert isinstance(actual, dict)
            actual["tests"] += 1
            if classification is not None:
                counter_field = {
                    "failure": "failures",
                    "error": "errors",
                    "skipped": "skipped",
                }[classification]
                actual[counter_field] += 1
            suite = testcase["suite"]
            rows = testcase["rows"]
            assert isinstance(rows, list)
            if suite is not None and rows:
                assert isinstance(suite, tuple)
                rows_by_suite.setdefault(suite[0], []).extend(rows)
        if tag in {"testsuite", "testsuites"}:
            counter = counter_stack.pop()
            if counter["element"] is not element:
                raise ValueError("JUnit suite nesting is malformed")
            actual = counter["actual"]
            declared = counter["declared"]
            assert isinstance(actual, dict)
            assert isinstance(declared, dict)
            for field, actual_value in actual.items():
                declared_value = declared[field]
                if (
                    declared_value is not None
                    and declared_value != actual_value
                ):
                    raise ValueError(
                        f"JUnit {tag} {field}={declared_value} contradicts "
                        f"actual testcase children={actual_value}: {path}"
                    )
            if counter_stack:
                parent_actual = counter_stack[-1]["actual"]
                assert isinstance(parent_actual, dict)
                for field, actual_value in actual.items():
                    parent_actual[field] += actual_value
        if tag == "testsuite":
            suite_stack.pop()

        popped = element_stack.pop()
        if popped is not element:
            raise ValueError("JUnit XML nesting is malformed")
        element.clear()
        if parent is not None:
            parent.remove(element)

    for offset in range(0, len(data), XML_FEED_CHUNK_BYTES):
        parser.feed(data[offset:offset + XML_FEED_CHUNK_BYTES])
        for event, element in parser.read_events():
            handle_event(event, element)
    parser.close()
    for event, element in parser.read_events():
        handle_event(event, element)
    if not saw_root or element_stack or counter_stack or testcase_stack:
        raise ValueError(f"JUnit XML document is incomplete: {path}")

    rows: list[dict[str, str]] = []
    for suite_index in sorted(rows_by_suite):
        rows.extend(rows_by_suite[suite_index])
    return rows


def failures(report_root: Path, path: Path) -> list[dict[str, str]]:
    _, data = read_bounded_report(report_root, path)
    return parse_junit(data, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report-root",
        required=True,
        type=Path,
        help="trusted non-symlink directory containing every JUnit report",
    )
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        if len(args.reports) > MAX_REPORTS:
            raise ValueError(
                f"report count exceeds the {MAX_REPORTS}-report limit"
            )
        require_secure_descriptor_support()

        buffered_reports: list[tuple[Path, bytes]] = []
        aggregate_input_bytes = 0
        for report in args.reports:
            _, data = read_bounded_report(
                args.report_root,
                report,
            )
            aggregate_input_bytes += len(data)
            if aggregate_input_bytes > MAX_AGGREGATE_INPUT_BYTES:
                raise ValueError(
                    "reports exceed the "
                    f"{MAX_AGGREGATE_INPUT_BYTES}-byte aggregate input limit"
                )
            buffered_reports.append((report, data))

        all_rows: list[dict[str, str]] = []
        for report, data in buffered_reports:
            rows = parse_junit(data, report)
            if len(all_rows) + len(rows) > MAX_AGGREGATE_FAILURE_ROWS:
                raise ValueError(
                    "reports exceed the "
                    f"{MAX_AGGREGATE_FAILURE_ROWS}-failure aggregate limit"
                )
            all_rows.extend(rows)

        output_chunks: list[bytes] = []
        output_bytes = 0
        for row in all_rows:
            row = redact_for_output(row)
            chunk = (
                json.dumps(row, ensure_ascii=False, sort_keys=True)
                .encode("utf-8")
                + b"\n"
            )
            output_bytes += len(chunk)
            if output_bytes > MAX_OUTPUT_BYTES:
                raise ValueError(
                    f"output exceeds the {MAX_OUTPUT_BYTES}-byte limit"
                )
            output_chunks.append(chunk)
    except (ET.ParseError, OSError, ValueError) as exc:
        parser.error(redact_diagnostic(exc))

    sys.stdout.buffer.write(b"".join(output_chunks))


if __name__ == "__main__":
    main()
