#!/usr/bin/env python3
"""Adversarial tests for the development-only release-v1 scorer."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SCORER_PATH = ROOT / "scripts/evals/score-reviewer-release-v1.py"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"
SPEC = importlib.util.spec_from_file_location("reviewer_release_v1_scorer", SCORER_PATH)
assert SPEC and SPEC.loader
SCORER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCORER)
PROTOCOL = SCORER.load_json(PROTOCOL_PATH)
PATTERNS = list(SCORER.TAXONOMY)


def fixture(full_wrong: set[int] | None = None, control_wrong: set[int] | None = None) -> dict:
    full_wrong = full_wrong or set()
    control_wrong = control_wrong if control_wrong is not None else set(range(24))
    severity_patterns = {
        severity: [pattern for pattern in PATTERNS if SCORER.TAXONOMY[pattern] == severity]
        for severity in SCORER.SEVERITIES
    }
    positive_pattern_schedule = [*PATTERNS, *PATTERNS]
    positive_pattern_schedule.extend(severity_patterns["P2"] * 2)
    positive_pattern_schedule.extend(severity_patterns["P0"][:6])
    positive_index = 0
    cases = []
    for index in range(120):
        framework = "playwright" if index < 60 else "cypress"
        within = index % 60
        label = "positive" if within < 30 else "clean"
        pattern = positive_pattern_schedule[positive_index] if label == "positive" else None
        positive_index += int(label == "positive")
        cases.append({
            "id": f"case-{index:03d}",
            "framework": framework,
            "label": label,
            "oracle_token": f"finding-{index:03d}" if label == "positive" else "clean",
            "pattern_id": pattern,
            "severity": SCORER.TAXONOMY[pattern] if pattern else None,
            "guard_pattern_ids": (
                [] if label == "positive" else [PATTERNS[index % 24], PATTERNS[(index + 1) % 24]]
            ),
            "source_repository": f"repo-{index // 2:02d}",
            "lineage_cluster": f"lineage-{index:03d}",
        })
    calls = []
    utilities = []
    for index, case in enumerate(cases):
        for arm in SCORER.ARMS:
            wrong = index in (full_wrong if arm == "full" else control_wrong if arm == "no-skill" else set())
            prediction = f"wrong-{index:03d}" if wrong else case["oracle_token"]
            for repetition in (1, 2, 3):
                calls.append({"case_id": case["id"], "arm": arm, "repetition": repetition, "valid": True, "normalized_prediction": prediction})
            utilities.append({
                "case_id": case["id"], "arm": arm, "normalized_prediction": prediction,
                "helpful": not wrong, "harmful": False,
                "fabricated_destructive_or_security_sensitive_action": False,
            })
    return {
        "schema_version": 1,
        "protocol_id": "reviewer-release-v1",
        "provenance": {
            "development_only": True,
            "contamination_detected": False,
            "independent_human_utility_adjudication_complete": True,
        },
        "cases": cases,
        "calls": calls,
        "utility_adjudications": utilities,
    }


def expect_error(payload: dict, fragment: str) -> None:
    try:
        SCORER.score(payload, PROTOCOL)
    except SCORER.ScoreError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected ScoreError containing {fragment!r}")


def test_complete_inputs_never_make_release_claim() -> None:
    result = SCORER.score(fixture(), PROTOCOL)
    assert result["status"] == "INCONCLUSIVE"
    assert result["release_claim_eligible"] is False
    assert result["frozen_release_decision"] == "NOT_EVALUATED"
    assert "precision" not in result["development_case_diagnostics"]["full"]
    assert result["paired_full_vs_no_skill"]["checks"]["case_correctness_lift"] is True


def test_missing_and_duplicate_calls_fail_closed() -> None:
    missing = fixture()
    missing["calls"].pop()
    expect_error(missing, "exactly 1080 calls")
    duplicate = fixture()
    duplicate["calls"][-1] = copy.deepcopy(duplicate["calls"][0])
    expect_error(duplicate, "duplicate call")


def test_invalid_and_unstable_calls_fail_closed() -> None:
    invalid = fixture()
    invalid["calls"][0]["valid"] = False
    expect_error(invalid, "invalid model call")
    unstable = fixture()
    for offset, token in enumerate(("one", "two", "three")):
        unstable["calls"][offset]["normalized_prediction"] = token
    expect_error(unstable, "unstable normalized predictions")
    bool_repetition = fixture()
    bool_repetition["calls"][0]["repetition"] = True
    expect_error(bool_repetition, "invalid call key")
    impossible_utility = fixture()
    impossible_utility["utility_adjudications"][2]["helpful"] = True
    expect_error(impossible_utility, "incorrect response cannot be adjudicated helpful")


def test_threshold_boundary_is_exact_but_still_development_only() -> None:
    # Twelve one-sided discordances are exactly 0.10 and 12 cases.
    result = SCORER.score(fixture(control_wrong=set(range(12))), PROTOCOL)
    paired = result["paired_full_vs_no_skill"]
    assert paired["correctness_lift"] == 0.1
    assert paired["checks"]["case_correctness_lift"] is True
    assert paired["checks"]["case_correctness_lift_cases"] is True
    assert result["frozen_release_decision"] == "NOT_EVALUATED"


def test_noninferiority_failure_is_not_hidden_by_overall_lift() -> None:
    # Full loses two Playwright-positive cases while control loses those two and
    # another 24 cases elsewhere: overall full wins, but this stratum regresses.
    full_wrong = {0, 1}
    result = SCORER.score(fixture(full_wrong=full_wrong, control_wrong=full_wrong | set(range(30, 54))), PROTOCOL)
    paired = result["paired_full_vs_no_skill"]
    assert paired["correctness_lift"] > 0.1
    assert paired["noninferiority"]["framework/playwright/correct"] is True
    assert paired["noninferiority"]["label/positive/correct"] is True  # control shares the two losses
    # Create a real local regression: control gets the two positive cases right.
    payload = fixture(full_wrong=full_wrong, control_wrong=set(range(30, 54)))
    result = SCORER.score(payload, PROTOCOL)
    assert result["paired_full_vs_no_skill"]["noninferiority"]["label/positive/correct"] is False
    assert result["paired_full_vs_no_skill"]["checks"]["stratum_noninferiority"] is False


def test_contamination_and_duplicate_json_keys_fail_closed() -> None:
    contaminated = fixture()
    contaminated["provenance"]["contamination_detected"] = True
    expect_error(contaminated, "contamination_detected")
    with tempfile.TemporaryDirectory(prefix="reviewer-release-scorer-") as raw:
        path = Path(raw) / "duplicate.json"
        path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        try:
            SCORER.load_json(path)
        except SCORER.ScoreError as exc:
            assert "duplicate JSON key" in str(exc)
        else:
            raise AssertionError("duplicate JSON key was accepted")


def test_unhashable_json_values_fail_closed_with_structured_error() -> None:
    malformed_guard = fixture()
    malformed_guard["cases"][30]["guard_pattern_ids"] = [{}]
    expect_error(malformed_guard, "guard_pattern_ids must be unique strings")

    malformed_pattern = fixture()
    malformed_pattern["cases"][0]["pattern_id"] = {}
    expect_error(malformed_pattern, "invalid oracle taxonomy")

    malformed_call = fixture()
    malformed_call["calls"][0]["case_id"] = {}
    expect_error(malformed_call, "invalid call key")

    malformed_utility = fixture()
    malformed_utility["utility_adjudications"][0]["arm"] = {}
    expect_error(malformed_utility, "invalid or duplicate utility key")


def main() -> None:
    tests = [
        test_complete_inputs_never_make_release_claim,
        test_missing_and_duplicate_calls_fail_closed,
        test_invalid_and_unstable_calls_fail_closed,
        test_threshold_boundary_is_exact_but_still_development_only,
        test_noninferiority_failure_is_not_hidden_by_overall_lift,
        test_contamination_and_duplicate_json_keys_fail_closed,
        test_unhashable_json_values_fail_closed_with_structured_error,
    ]
    for test in tests:
        test()
    print(f"reviewer release scorer v1 tests: {len(tests)} passed")


if __name__ == "__main__":
    main()
