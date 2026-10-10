#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Adversarial checks for the release-v1 development finding scorer."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCORER_PATH = ROOT / "scripts/evals/score-reviewer-release-findings-v1.py"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"
SPEC = importlib.util.spec_from_file_location("release_finding_scorer_v1", SCORER_PATH)
assert SPEC and SPEC.loader
SCORER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCORER)
PROTOCOL = SCORER.load_json(PROTOCOL_PATH)
HASH = "a" * 64


def finding(pattern_id: str = "1", file: str = "tests/example.spec.ts", line: int = 7) -> dict:
    return {
        "pattern_id": pattern_id,
        "severity": SCORER.TAXONOMY[pattern_id],
        "file": file,
        "line": line,
    }


def fixture(*, label: str = "positive", findings: list[dict] | None = None) -> dict:
    positive = label == "positive"
    return {
        "schema_version": 1,
        "protocol_id": "reviewer-release-v1",
        "development_only": True,
        "case": {
            "case_id": "case-001",
            "label": label,
            "pattern_id": "1" if positive else None,
            "severity": SCORER.TAXONOMY["1"] if positive else None,
            "accepted_locations": [{"file": "tests/example.spec.ts", "line": 7}] if positive else [],
        },
        "representative": {
            "arm": "full",
            "selected_repetition": 2,
            "raw_output_sha256": HASH,
            "normalized_finding_identities": findings if findings is not None else [finding()],
        },
    }


def expect_error(payload: dict, fragment: str) -> None:
    try:
        SCORER.score_case(payload, PROTOCOL)
    except SCORER.FindingScoreError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected FindingScoreError containing {fragment!r}")


def test_exact_positive_match_is_one_tp_and_never_release_evidence() -> None:
    result = SCORER.score_case(fixture(), PROTOCOL)
    assert (result["true_positives"], result["false_positives"], result["false_negatives"]) == (1, 0, 0)
    assert result["case_correct"] is True
    assert result["status"] == "INCONCLUSIVE"
    assert result["release_claim_eligible"] is False
    assert result["frozen_release_decision"] == "NOT_EVALUATED"


def test_correct_finding_plus_invented_finding_counts_false_positive() -> None:
    payload = fixture(findings=[finding(), finding("2", line=20)])
    result = SCORER.score_case(payload, PROTOCOL)
    assert (result["true_positives"], result["false_positives"], result["false_negatives"]) == (1, 1, 0)
    assert result["case_correct"] is False
    assert result["false_positive_findings"] == [finding("2", line=20)]


def test_wrong_location_is_fp_and_missing_oracle_is_fn() -> None:
    result = SCORER.score_case(fixture(findings=[finding(line=8)]), PROTOCOL)
    assert (result["true_positives"], result["false_positives"], result["false_negatives"]) == (0, 1, 1)
    assert result["case_correct"] is False


def test_duplicate_identity_normalizes_to_one_prediction() -> None:
    duplicate = finding()
    result = SCORER.score_case(fixture(findings=[duplicate, copy.deepcopy(duplicate)]), PROTOCOL)
    assert result["normalized_distinct_finding_count"] == 1
    assert (result["true_positives"], result["false_positives"], result["false_negatives"]) == (1, 0, 0)
    assert result["case_correct"] is True


def test_clean_case_any_finding_is_false_positive() -> None:
    result = SCORER.score_case(fixture(label="clean", findings=[finding()]), PROTOCOL)
    assert (result["true_positives"], result["false_positives"], result["false_negatives"]) == (0, 1, 0)
    assert result["case_correct"] is False
    clean = SCORER.score_case(fixture(label="clean", findings=[]), PROTOCOL)
    assert clean["case_correct"] is True
    assert clean["false_positives"] == 0


def test_multiple_accepted_alternatives_still_allow_only_one_tp() -> None:
    payload = fixture(findings=[finding(line=7), finding(line=9)])
    payload["case"]["accepted_locations"].append({"file": "tests/example.spec.ts", "line": 9})
    result = SCORER.score_case(payload, PROTOCOL)
    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert result["case_correct"] is False


def test_schema_and_taxonomy_mismatches_fail_closed() -> None:
    extra_key = fixture()
    extra_key["representative"]["unexpected"] = True
    expect_error(extra_key, "representative keys")
    bad_severity = fixture()
    bad_severity["representative"]["normalized_finding_identities"][0]["severity"] = "P2"
    expect_error(bad_severity, "severity does not match")
    bad_hash = fixture()
    bad_hash["representative"]["raw_output_sha256"] = "not-a-hash"
    expect_error(bad_hash, "lowercase SHA-256")
    traversal = fixture()
    traversal["representative"]["normalized_finding_identities"][0]["file"] = "../secret"
    expect_error(traversal, "canonical POSIX relative path")


def test_malformed_oracle_fails_closed() -> None:
    empty_locations = fixture()
    empty_locations["case"]["accepted_locations"] = []
    expect_error(empty_locations, "accepted locations")
    dirty_clean = fixture(label="clean", findings=[])
    dirty_clean["case"]["accepted_locations"] = [{"file": "tests/example.spec.ts", "line": 7}]
    expect_error(dirty_clean, "clean case must")
    duplicate_location = fixture()
    duplicate_location["case"]["accepted_locations"].append(copy.deepcopy(duplicate_location["case"]["accepted_locations"][0]))
    expect_error(duplicate_location, "contains a duplicate")


def main() -> None:
    tests = [
        test_exact_positive_match_is_one_tp_and_never_release_evidence,
        test_correct_finding_plus_invented_finding_counts_false_positive,
        test_wrong_location_is_fp_and_missing_oracle_is_fn,
        test_duplicate_identity_normalizes_to_one_prediction,
        test_clean_case_any_finding_is_false_positive,
        test_multiple_accepted_alternatives_still_allow_only_one_tp,
        test_schema_and_taxonomy_mismatches_fail_closed,
        test_malformed_oracle_fails_closed,
    ]
    for test in tests:
        test()
    print(f"reviewer release finding scorer v1 tests: {len(tests)} passed")


if __name__ == "__main__":
    main()
