#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Strictly normalize one reviewer-release-v1 model response.

This is development infrastructure. Its output cannot make a run eligible for
release evidence; custody, execution, adjudication, scoring, and attestation
remain separate protocol requirements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "scripts" / "evals" / "reviewer-release-v1-protocol.json"
CI_LIB = ROOT / "scripts" / "ci" / "lib"
if str(CI_LIB) not in sys.path:
    sys.path.insert(0, str(CI_LIB))

from reviewer_taxonomy_contract import REVIEWER_TAXONOMY  # noqa: E402


EXPECTED_TOP_LEVEL_KEYS = ("findings",)
EXPECTED_FINDING_KEYS = (
    "pattern_id",
    "severity",
    "file",
    "line",
    "causal_explanation",
    "repair",
    "validation",
)
EXPECTED_IDENTITY_KEYS = ("pattern_id", "severity", "file", "line")
EXPECTED_MAX_FINDINGS = 24
EXPECTED_MAX_OUTPUT_BYTES = 65_536
TAXONOMY = {pattern_id: severity for pattern_id, _title, severity in REVIEWER_TAXONOMY}
TAXONOMY_RANK = {
    pattern_id: index for index, (pattern_id, _title, _severity) in enumerate(REVIEWER_TAXONOMY)
}


class NormalizationError(ValueError):
    """The protocol or response is unsafe, malformed, or out of contract."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise NormalizationError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def loads_strict(raw: bytes, *, context: str, maximum_bytes: int | None = None) -> Any:
    if maximum_bytes is not None and len(raw) > maximum_bytes:
        raise NormalizationError(
            f"{context} exceeds maximum UTF-8 byte count: {len(raw)} > {maximum_bytes}"
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NormalizationError(f"{context} is not valid UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                NormalizationError(f"non-standard JSON constant: {value}")
            ),
        )
    except NormalizationError:
        raise
    except json.JSONDecodeError as exc:
        raise NormalizationError(f"{context} is not one strict JSON value: {exc.msg}") from exc


def load_protocol() -> dict[str, Any]:
    protocol = loads_strict(PROTOCOL_PATH.read_bytes(), context="release protocol")
    if not isinstance(protocol, dict):
        raise NormalizationError("release protocol must be an object")

    contract = protocol.get("response_contract")
    if not isinstance(contract, dict):
        raise NormalizationError("release protocol response_contract must be an object")
    expected = {
        "model_output_format": "one_strict_json_object",
        "top_level_keys": list(EXPECTED_TOP_LEVEL_KEYS),
        "finding_keys": list(EXPECTED_FINDING_KEYS),
        "finding_identity_keys": list(EXPECTED_IDENTITY_KEYS),
        "maximum_findings_per_response": EXPECTED_MAX_FINDINGS,
        "maximum_output_bytes": EXPECTED_MAX_OUTPUT_BYTES,
        "normalization": "sort_unique_finding_identities_without_prose",
        "duplicate_finding_handling": "one_normalized_finding",
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            raise NormalizationError(f"unsupported response_contract.{key}")

    coverage = protocol.get("corpus", {}).get("coverage", {})
    if coverage.get("stable_pattern_count") != len(TAXONOMY) or len(TAXONOMY) != 24:
        raise NormalizationError("release protocol taxonomy count does not match the stable taxonomy")
    amendment = protocol.get("preexecution_amendment")
    if (
        not isinstance(amendment, dict)
        or amendment.get("model_calls_before_amendment") != 0
        or amendment.get("outcome_thresholds_changed") is not True
    ):
        raise NormalizationError("unsupported or post-execution release protocol amendment")
    evidence = protocol.get("current_evidence")
    if not isinstance(evidence, dict) or evidence.get("permitted_work") != "infrastructure_only":
        raise NormalizationError("normalizer is restricted to infrastructure-only protocol state")
    return protocol


def _validate_unicode(value: str, field: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise NormalizationError(f"finding {field} contains an invalid Unicode scalar") from exc


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise NormalizationError("finding file must be a non-empty string")
    _validate_unicode(value, "file")
    if value != value.strip():
        raise NormalizationError("finding file must not have surrounding whitespace")
    if "\\" in value or any(ord(character) < 32 for character in value):
        raise NormalizationError("finding file must be a safe POSIX relative path")
    if value.startswith("/") or value.endswith("/") or "//" in value:
        raise NormalizationError("finding file must be a safe POSIX relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise NormalizationError("finding file must not contain empty or traversal segments")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or ":" in parts[0]:
        raise NormalizationError("finding file must be a canonical POSIX relative path")
    return value


def _assert_no_symlink_components(path: Path, *, boundary: Path | None = None) -> None:
    if boundary is None:
        paths = (path,)
    else:
        try:
            relative = path.relative_to(boundary)
        except ValueError as exc:
            raise NormalizationError(f"path escapes its source root: {path}") from exc
        current = boundary
        descendants: list[Path] = []
        for part in relative.parts:
            current = current / part
            descendants.append(current)
        paths = tuple(descendants)
    for current in paths:
        try:
            metadata = current.lstat()
        except FileNotFoundError as exc:
            raise NormalizationError(f"path does not exist: {path}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise NormalizationError(f"path contains a symlink component: {path}")


def _validate_source_path(source_root: Path, relative: str) -> None:
    if any(part == ".." for part in source_root.parts):
        raise NormalizationError("source root must not contain traversal segments")
    _assert_no_symlink_components(source_root)
    root_metadata = source_root.stat()
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise NormalizationError("source root must be a regular directory")
    candidate = source_root / PurePosixPath(relative)
    _assert_no_symlink_components(candidate, boundary=source_root)
    metadata = candidate.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise NormalizationError(f"finding file is not a regular source file: {relative}")


def _validate_prose(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NormalizationError(f"finding {field} must be non-empty prose")
    _validate_unicode(value, field)
    return value


def normalize_response(raw: bytes, *, source_root: Path | None = None) -> dict[str, Any]:
    protocol = load_protocol()
    contract = protocol["response_contract"]
    response = loads_strict(
        raw,
        context="model response",
        maximum_bytes=contract["maximum_output_bytes"],
    )
    if not isinstance(response, dict) or set(response) != set(EXPECTED_TOP_LEVEL_KEYS):
        raise NormalizationError("model response must be exactly an object with the findings key")
    findings = response["findings"]
    if not isinstance(findings, list):
        raise NormalizationError("model response findings must be an array")
    if len(findings) > contract["maximum_findings_per_response"]:
        raise NormalizationError("model response contains too many findings")

    identities: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict) or set(finding) != set(EXPECTED_FINDING_KEYS):
            raise NormalizationError(
                f"finding {index} must contain exactly the preregistered finding keys"
            )
        pattern_id = finding["pattern_id"]
        severity = finding["severity"]
        if not isinstance(pattern_id, str) or pattern_id not in TAXONOMY:
            raise NormalizationError(f"finding {index} has an unknown pattern_id")
        if not isinstance(severity, str) or severity != TAXONOMY[pattern_id]:
            raise NormalizationError(f"finding {index} severity does not match its pattern_id")
        file_name = _safe_relative_path(finding["file"])
        if source_root is not None:
            _validate_source_path(source_root, file_name)
        line = finding["line"]
        if isinstance(line, bool) or not isinstance(line, int) or line <= 0:
            raise NormalizationError(f"finding {index} line must be a positive integer")
        for field in ("causal_explanation", "repair", "validation"):
            _validate_prose(finding[field], field)
        identity = (pattern_id, severity, file_name, line)
        identities.setdefault(
            identity,
            {"pattern_id": pattern_id, "severity": severity, "file": file_name, "line": line},
        )

    normalized = sorted(
        identities.values(),
        key=lambda item: (
            TAXONOMY_RANK[item["pattern_id"]],
            item["file"].encode("utf-8"),
            item["line"],
            item["severity"],
        ),
    )
    return {
        "schema_version": 1,
        "protocol_id": protocol.get("protocol_id"),
        "evidence_class": "development_only",
        "release_evidence_eligible": False,
        "raw_output_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_output_utf8_bytes": len(raw),
        "raw_findings": findings,
        "normalized_finding_identities": normalized,
    }


def read_regular_file(path: Path, maximum_bytes: int) -> bytes:
    if any(part == ".." for part in path.parts):
        raise NormalizationError("input path must not contain traversal segments")
    _assert_no_symlink_components(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        named = path.stat()
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            named.st_dev,
            named.st_ino,
        ):
            raise NormalizationError("input must be one stable regular file")
        if opened.st_size > maximum_bytes:
            raise NormalizationError("model response exceeds maximum UTF-8 byte count")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(maximum_bytes + 1)
    finally:
        os.close(descriptor)
    if len(raw) > maximum_bytes:
        raise NormalizationError("model response exceeds maximum UTF-8 byte count")
    return raw


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="one raw model response file")
    parser.add_argument(
        "--source-root",
        type=Path,
        help="optional staged case root for regular-file and symlink validation",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        protocol = load_protocol()
        raw = read_regular_file(args.input, protocol["response_contract"]["maximum_output_bytes"])
        result = normalize_response(raw, source_root=args.source_root)
        sys.stdout.buffer.write(canonical_bytes(result))
        return 0
    except (NormalizationError, OSError) as exc:
        print(f"reviewer release response rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
