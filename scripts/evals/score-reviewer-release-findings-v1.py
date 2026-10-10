#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Score one normalized reviewer-release-v1 response at finding level.

This is bounded development infrastructure. It proves only the arithmetic for
one case/arm cell; it does not verify custody, independence, completeness, or
release eligibility.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTOCOL = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"
sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
from reviewer_taxonomy_contract import REVIEWER_TAXONOMY  # noqa: E402


TAXONOMY = {pattern_id: severity for pattern_id, _title, severity in REVIEWER_TAXONOMY}
ARMS = {"full", "catalog-only", "no-skill"}
IDENTITY_KEYS = {"pattern_id", "severity", "file", "line"}


class FindingScoreError(ValueError):
    """The input cannot support the frozen finding-level calculation."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FindingScoreError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                FindingScoreError(f"non-standard JSON constant: {value}")
            ),
        )
    except FindingScoreError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FindingScoreError(f"cannot read strict JSON {path}: {exc}") from exc


def _exact_object(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise FindingScoreError(f"{where} keys must be {sorted(keys)}; got {actual}")
    return value


def _nonempty_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise FindingScoreError(f"{where} must be a non-empty trimmed string")
    return value


def _safe_file(value: Any, where: str) -> str:
    text = _nonempty_string(value, where)
    if (
        "\\" in text
        or text.startswith("/")
        or text.endswith("/")
        or "//" in text
        or any(ord(character) < 32 for character in text)
    ):
        raise FindingScoreError(f"{where} must be a canonical POSIX relative path")
    parts = text.split("/")
    path = PurePosixPath(text)
    if any(part in {"", ".", ".."} for part in parts) or path.is_absolute() or path.as_posix() != text:
        raise FindingScoreError(f"{where} must be a canonical POSIX relative path")
    return text


def _positive_line(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise FindingScoreError(f"{where} must be a positive integer")
    return value


def _validate_protocol(protocol: Any) -> None:
    if not isinstance(protocol, dict) or protocol.get("protocol_id") != "reviewer-release-v1":
        raise FindingScoreError("protocol_id must be reviewer-release-v1")
    contract = protocol.get("response_contract")
    if not isinstance(contract, dict):
        raise FindingScoreError("protocol response_contract is missing")
    expected = {
        "finding_identity_keys": ["pattern_id", "severity", "file", "line"],
        "normalization": "sort_unique_finding_identities_without_prose",
        "duplicate_finding_handling": "one_normalized_finding",
        "unmatched_finding_handling": "false_positive_even_on_positive_cases",
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            raise FindingScoreError(f"unsupported response_contract.{key}")
    evidence = protocol.get("current_evidence")
    if not isinstance(evidence, dict) or evidence.get("permitted_work") != "infrastructure_only":
        raise FindingScoreError("finding scorer is restricted to infrastructure-only protocol state")


def _identity(value: Any, where: str) -> tuple[str, str, str, int]:
    row = _exact_object(value, IDENTITY_KEYS, where)
    pattern_id = row["pattern_id"]
    if not isinstance(pattern_id, str) or pattern_id not in TAXONOMY:
        raise FindingScoreError(f"{where}.pattern_id is not in the frozen taxonomy")
    severity = row["severity"]
    if severity != TAXONOMY[pattern_id]:
        raise FindingScoreError(f"{where}.severity does not match its pattern_id")
    return (
        pattern_id,
        severity,
        _safe_file(row["file"], f"{where}.file"),
        _positive_line(row["line"], f"{where}.line"),
    )


def _identity_object(value: tuple[str, str, str, int]) -> dict[str, Any]:
    return dict(zip(("pattern_id", "severity", "file", "line"), value, strict=True))


def score_case(payload: Any, protocol: Any) -> dict[str, Any]:
    """Validate and score one representative case/arm response."""

    _validate_protocol(protocol)
    root = _exact_object(
        payload,
        {"schema_version", "protocol_id", "development_only", "case", "representative"},
        "input",
    )
    if root["schema_version"] != 1 or root["protocol_id"] != "reviewer-release-v1":
        raise FindingScoreError("input schema_version/protocol_id mismatch")
    if root["development_only"] is not True:
        raise FindingScoreError("development_only must be true")

    case = _exact_object(
        root["case"],
        {"case_id", "label", "pattern_id", "severity", "accepted_locations"},
        "case",
    )
    case_id = _nonempty_string(case["case_id"], "case.case_id")
    label = case["label"]
    if label not in {"positive", "clean"}:
        raise FindingScoreError("case.label must be positive or clean")
    locations = case["accepted_locations"]
    if not isinstance(locations, list):
        raise FindingScoreError("case.accepted_locations must be an array")
    accepted: set[tuple[str, int]] = set()
    for index, value in enumerate(locations):
        row = _exact_object(value, {"file", "line"}, f"case.accepted_locations[{index}]")
        location = (
            _safe_file(row["file"], f"case.accepted_locations[{index}].file"),
            _positive_line(row["line"], f"case.accepted_locations[{index}].line"),
        )
        if location in accepted:
            raise FindingScoreError("case.accepted_locations contains a duplicate")
        accepted.add(location)
    if label == "positive":
        pattern_id = case["pattern_id"]
        if not isinstance(pattern_id, str) or pattern_id not in TAXONOMY:
            raise FindingScoreError("positive case pattern_id is not in the frozen taxonomy")
        if case["severity"] != TAXONOMY[pattern_id] or not accepted:
            raise FindingScoreError("positive case requires matching severity and accepted locations")
    else:
        pattern_id = None
        if case["pattern_id"] is not None or case["severity"] is not None or accepted:
            raise FindingScoreError("clean case must have null taxonomy and no accepted locations")

    representative = _exact_object(
        root["representative"],
        {"arm", "selected_repetition", "raw_output_sha256", "normalized_finding_identities"},
        "representative",
    )
    arm = representative["arm"]
    if arm not in ARMS:
        raise FindingScoreError("representative.arm is invalid")
    repetition = representative["selected_repetition"]
    if isinstance(repetition, bool) or not isinstance(repetition, int) or repetition not in (1, 2, 3):
        raise FindingScoreError("representative.selected_repetition must be 1, 2, or 3")
    raw_hash = representative["raw_output_sha256"]
    if (
        not isinstance(raw_hash, str)
        or len(raw_hash) != 64
        or any(character not in "0123456789abcdef" for character in raw_hash)
    ):
        raise FindingScoreError("representative.raw_output_sha256 must be lowercase SHA-256")
    findings = representative["normalized_finding_identities"]
    if not isinstance(findings, list) or len(findings) > 24:
        raise FindingScoreError("representative.normalized_finding_identities must contain at most 24 findings")

    # Duplicate identities collapse to one finding, exactly as preregistered.
    predictions = sorted({_identity(value, f"finding[{index}]") for index, value in enumerate(findings)})
    matching = []
    if label == "positive":
        matching = [
            identity
            for identity in predictions
            if identity[0] == pattern_id
            and identity[1] == case["severity"]
            and (identity[2], identity[3]) in accepted
        ]
    matched = matching[0] if matching else None
    unmatched = list(predictions)
    if matched is not None:
        unmatched.remove(matched)

    true_positives = int(matched is not None)
    false_positives = len(unmatched)
    false_negatives = int(label == "positive" and matched is None)
    correct = (
        true_positives == 1 and false_positives == 0
        if label == "positive"
        else false_positives == 0
    )
    return {
        "schema_version": 1,
        "protocol_id": "reviewer-release-v1",
        "status": "INCONCLUSIVE",
        "evidence_class": "development_only",
        "release_claim_eligible": False,
        "frozen_release_decision": "NOT_EVALUATED",
        "case_id": case_id,
        "arm": arm,
        "selected_repetition": repetition,
        "raw_output_sha256": raw_hash,
        "normalized_distinct_finding_count": len(predictions),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "case_correct": correct,
        "matched_finding": _identity_object(matched) if matched else None,
        "false_positive_findings": [_identity_object(value) for value in unmatched],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="one strict case/representative JSON object")
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = score_case(load_json(args.input), load_json(args.protocol))
    except FindingScoreError as exc:
        print(f"finding scorer error: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
