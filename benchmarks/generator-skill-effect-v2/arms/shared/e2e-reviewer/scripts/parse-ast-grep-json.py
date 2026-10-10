#!/usr/bin/env python3
"""Validate ast-grep JSON-stream records and emit stable file:line:column rows."""

from __future__ import annotations

import json
import sys
from typing import Any


MAX_RECORD_BYTES = 1_048_576
MAX_RECORDS = 10_000


class AstGrepOutputError(ValueError):
    pass


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AstGrepOutputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise AstGrepOutputError(f"non-finite JSON number: {value}")


def require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AstGrepOutputError(f"{label} must be an object")
    return value


def require_coordinate(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AstGrepOutputError(f"{label} must be a non-negative integer")
    return value


def parse_record(raw: bytes, record_number: int) -> tuple[str, int, int]:
    if len(raw) > MAX_RECORD_BYTES:
        raise AstGrepOutputError(
            f"record {record_number} exceeds {MAX_RECORD_BYTES} bytes"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AstGrepOutputError(
            f"record {record_number} is not valid UTF-8"
        ) from error
    try:
        record = json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, AstGrepOutputError) as error:
        raise AstGrepOutputError(
            f"record {record_number} is not strict JSON: {error}"
        ) from error

    record = require_mapping(record, f"record {record_number}")
    file_name = record.get("file")
    if not isinstance(file_name, str) or not file_name:
        raise AstGrepOutputError(
            f"record {record_number}.file must be a non-empty string"
        )
    if "\x00" in file_name or "\n" in file_name or "\r" in file_name or "\t" in file_name:
        raise AstGrepOutputError(
            f"record {record_number}.file contains an unsafe control character"
        )

    match_range = require_mapping(record.get("range"), f"record {record_number}.range")
    start = require_mapping(
        match_range.get("start"), f"record {record_number}.range.start"
    )
    line = require_coordinate(
        start.get("line"), f"record {record_number}.range.start.line"
    )
    column = require_coordinate(
        start.get("column"), f"record {record_number}.range.start.column"
    )
    return file_name, line + 1, column + 1


def main() -> int:
    count = 0
    try:
        for raw in sys.stdin.buffer:
            if not raw.strip():
                raise AstGrepOutputError(
                    f"record {count + 1} is unexpectedly blank"
                )
            count += 1
            if count > MAX_RECORDS:
                raise AstGrepOutputError(
                    f"ast-grep emitted more than {MAX_RECORDS} records"
                )
            file_name, line, column = parse_record(raw, count)
            print(f"{file_name}\t{line}\t{column}")
    except AstGrepOutputError as error:
        print(f"invalid ast-grep JSON stream: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
