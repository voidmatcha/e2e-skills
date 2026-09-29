#!/usr/bin/env python3
"""Adversarial tests for the development-only release-v1 matrix scorer."""

from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCORER_PATH = ROOT / "scripts/evals/score-reviewer-release-matrix-v1.py"
NORMALIZER_PATH = ROOT / "scripts/evals/normalize-reviewer-release-v1.py"
POSTRUN_PATH = ROOT / "scripts/evals/validate-reviewer-release-postrun-v1.py"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCORER = load_module("release_matrix_v1", SCORER_PATH)
NORMALIZER = load_module("release_normalizer_v1_for_matrix", NORMALIZER_PATH)
POSTRUN = load_module("release_postrun_v1_for_matrix", POSTRUN_PATH)
PROTOCOL = SCORER.load_json(PROTOCOL_PATH)
PATTERNS = list(SCORER.TAXONOMY)


def finding(pattern: str, severity: str, file_name: str, line: int) -> dict:
    return {"pattern_id": pattern, "severity": severity, "file": file_name, "line": line}


def fixture() -> tuple[dict, dict, dict, dict]:
    severity_patterns = {
        severity: [pattern for pattern in PATTERNS if SCORER.TAXONOMY[pattern] == severity]
        for severity in SCORER.SEVERITIES
    }
    positive_schedule = [*PATTERNS, *PATTERNS]
    positive_schedule.extend(severity_patterns["P2"] * 2)
    positive_schedule.extend(severity_patterns["P0"][:6])
    positive_index = 0
    cases, label_rows, responses, utilities, resolved = [], [], [], [], []
    for index in range(120):
        framework = "playwright" if index < 60 else "cypress"
        within = index % 60
        kind = "positive" if within < 30 else "clean"
        pattern = positive_schedule[positive_index] if kind == "positive" else None
        positive_index += int(kind == "positive")
        severity = SCORER.TAXONOMY[pattern] if pattern else None
        source_root = f"cases/case-{index:03d}"
        source_path = f"{source_root}/e2e/example.spec.ts"
        guards = [] if kind == "positive" else [PATTERNS[index % 24], PATTERNS[(index + 1) % 24]]
        cases.append({
            "case_id": f"case-{index:03d}", "repo_id": f"repo-{index // 2:02d}",
            "framework": framework, "kind": kind,
            "source_root": source_root,
            "source_files": [
                {"path": source_path, "sha256": hashlib.sha256(source_path.encode()).hexdigest()},
                *([{"path": f"{source_root}/support/helper.ts", "sha256": hashlib.sha256(f"{source_root}/support/helper.ts".encode()).hexdigest()}] if index == 0 else []),
            ],
            "taxonomy_id": pattern, "severity": severity, "guard_taxonomy_ids": guards,
        })
        accepted = [{"file": source_path, "line": 1}] if kind == "positive" else []
        label_rows.append({
            "case_id": f"case-{index:03d}", "kind": kind, "taxonomy_id": pattern,
            "severity": severity, "accepted_locations": accepted,
        })
        identities = [finding(pattern, severity, source_path, 1)] if kind == "positive" else []
        for arm_index, arm in enumerate(SCORER.ARMS):
            for repetition in (1, 2, 3):
                digest = f"{index * 9 + arm_index * 3 + repetition:064x}"
                responses.append({
                    "case_id": f"case-{index:03d}", "arm": arm, "repetition": repetition,
                    "valid": True, "raw_output_sha256": digest,
                    "normalized_finding_identities": copy.deepcopy(identities),
                    "completed_at": "2026-09-23T09:00:00Z",
                })
            key = {"case_id": f"case-{index:03d}", "arm": arm}
            utilities.append({
                **key, "normalized_prediction": json.dumps(identities, sort_keys=True, separators=(",", ":")),
                "helpful": True, "harmful": False,
                "fabricated_destructive_or_security_sensitive_action": False,
            })
            resolved.append({
                **key, "selected_repetition": 1,
                "raw_output_sha256": f"{index * 9 + arm_index * 3 + 1:064x}",
                "correct_decision": True, "location_and_cause": True,
                "safe_actionable_repair": True, "discriminating_validation": True,
                "harmful": False, "fabricated_destructive_or_security_sensitive_action": False,
                "helpful": True, "judge_count": 2,
            })
    corpus = {
        "schema_version": 1, "protocol_id": "reviewer-release-v1", "corpus_id": "external-fixture",
        "frozen_at": "2026-09-23T08:00:00Z", "cases": cases,
    }
    labels = {"schema_version": 1, "corpus_id": "external-fixture", "model_visible": False, "labels": label_rows}
    manifest = {
        "schema_version": 1, "protocol_id": "reviewer-release-v1", "evidence_class": "development_only",
        "model_run_completed_at": "2026-09-23T10:00:00Z", "responses": responses,
    }
    utility_report = {
        "schema_version": 1, "protocol_id": "reviewer-release-v1", "status": "INCONCLUSIVE",
        "evidence_scope": "development-only", "release_claim_eligible": False,
        "status_reasons": ["fixture"], "rubric_resolution_rule": "per_field_two_of_three_majority",
        "utility_adjudications": utilities, "resolved_utility_rows": resolved,
    }
    return corpus, labels, manifest, utility_report


def expect_error(parts: tuple[dict, dict, dict, dict], fragment: str) -> None:
    try:
        SCORER.score(*parts, PROTOCOL)
    except SCORER.MatrixScoreError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected MatrixScoreError containing {fragment!r}")


def make_unstable_full_cell(parts: tuple[dict, dict, dict, dict], case_index: int, *, harmful: bool = False) -> None:
    corpus, _labels, manifest, report = parts
    first = case_index * 9
    responses = manifest["responses"][first:first + 3]
    source_path = corpus["cases"][case_index]["source_files"][0]["path"]
    responses[1]["normalized_finding_identities"] = [
        finding("2", SCORER.TAXONOMY["2"], source_path, 2)
    ]
    responses[2]["valid"] = False
    responses[2]["normalized_finding_identities"] = None
    hashes = [row["raw_output_sha256"] for row in responses]
    summary = report["utility_adjudications"][case_index * 3]
    summary["normalized_prediction"] = None
    summary["helpful"] = False
    summary["harmful"] = harmful
    report["resolved_utility_rows"][case_index * 3] = {
        "case_id": f"case-{case_index:03d}", "arm": "full", "state": "unstable",
        "repetition_raw_hashes": hashes,
        "correct_decision": False, "location_and_cause": False,
        "safe_actionable_repair": False, "discriminating_validation": False,
        "harmful": harmful, "fabricated_destructive_or_security_sensitive_action": False,
        "helpful": False, "judge_count": 2,
    }


def test_complete_matrix_scores_findings_but_never_release_evidence() -> None:
    result = SCORER.score(*fixture(), PROTOCOL)
    full = result["arm_metrics"]["full"]
    assert (full["tp"], full["fp"], full["fn"]) == (60, 0, 0)
    assert (full["precision"], full["recall"], full["f1"]) == (1.0, 1.0, 1.0)
    assert result["status"] == "INCONCLUSIVE"
    assert result["release_claim_eligible"] is False
    assert result["frozen_release_decision"] == "NOT_EVALUATED"
    assert "requires_every_gate" in result["release_gates_not_evaluated"]


def test_oracle_location_can_name_a_second_hashed_file() -> None:
    corpus, labels, _manifest, _utilities = fixture()
    helper_path = corpus["cases"][0]["source_files"][1]["path"]
    labels["labels"][0]["accepted_locations"] = [{"file": helper_path, "line": 1}]
    cases = SCORER.validate_oracle(corpus, labels)
    assert cases["case-000"]["accepted_locations"] == {(helper_path, 1)}
    labels["labels"][0]["accepted_locations"] = [{"file": "cases/case-000/not-staged.ts", "line": 1}]
    try:
        SCORER.validate_oracle(corpus, labels)
    except SCORER.MatrixScoreError as exc:
        assert "invalid accepted location" in str(exc), str(exc)
    else:
        raise AssertionError("matrix scorer accepted a location outside the hashed case files")


def test_extra_finding_on_positive_is_not_hidden() -> None:
    corpus, labels, manifest, utilities = fixture()
    extra = finding("2", SCORER.TAXONOMY["2"], corpus["cases"][0]["source_files"][0]["path"], 2)
    for response in manifest["responses"][:3]:
        response["normalized_finding_identities"].append(copy.deepcopy(extra))
    # The majority-selected response is no longer exactly correct. Human utility
    # must agree with the machine decision before the scorer will calculate.
    utilities["resolved_utility_rows"][0]["correct_decision"] = False
    utilities["resolved_utility_rows"][0]["helpful"] = False
    utilities["utility_adjudications"][0]["normalized_prediction"] = json.dumps(
        manifest["responses"][0]["normalized_finding_identities"], sort_keys=True, separators=(",", ":")
    )
    utilities["utility_adjudications"][0]["helpful"] = False
    result = SCORER.score(corpus, labels, manifest, utilities, PROTOCOL)
    full = result["arm_metrics"]["full"]
    assert (full["tp"], full["fp"], full["fn"]) == (60, 1, 0)
    assert full["case_correctness_rate"] == 119 / 120
    assert full["precision"] == 60 / 61


def test_schedule_incompleteness_fails_closed() -> None:
    parts = list(fixture())
    parts[2]["responses"].pop()
    expect_error(tuple(parts), "exactly 1080")


def test_utility_decision_mismatch_fails_closed() -> None:
    parts = list(fixture())
    parts[3]["resolved_utility_rows"][0]["correct_decision"] = False
    parts[3]["resolved_utility_rows"][0]["helpful"] = False
    parts[3]["utility_adjudications"][0]["helpful"] = False
    expect_error(tuple(parts), "correct_decision disagrees")


def test_utility_hash_and_selected_repetition_must_bind() -> None:
    parts = list(fixture())
    parts[3]["resolved_utility_rows"][0]["raw_output_sha256"] = "f" * 64
    expect_error(tuple(parts), "does not bind")
    parts = list(fixture())
    parts[3]["resolved_utility_rows"][0]["selected_repetition"] = 3
    expect_error(tuple(parts), "does not bind")


def test_raw_normalizer_identity_flows_into_manifest_scoring() -> None:
    corpus, labels, manifest, utilities = fixture()
    case = corpus["cases"][0]
    raw = json.dumps({"findings": [{
        "pattern_id": case["taxonomy_id"], "severity": case["severity"],
        "file": case["source_files"][0]["path"], "line": 1,
        "causal_explanation": "The assertion can silently pass.",
        "repair": "Assert the required state directly.",
        "validation": "The original defect must fail and the repair must pass.",
    }]}, separators=(",", ":")).encode()
    normalized = NORMALIZER.normalize_response(raw)
    assert normalized["normalized_finding_identities"] == manifest["responses"][0]["normalized_finding_identities"]
    for response in manifest["responses"][:3]:
        response["normalized_finding_identities"] = copy.deepcopy(normalized["normalized_finding_identities"])
    manifest["responses"][0]["raw_output_sha256"] = normalized["raw_output_sha256"]
    manifest["responses"][2]["raw_output_sha256"] = normalized["raw_output_sha256"]
    utilities["resolved_utility_rows"][0]["raw_output_sha256"] = normalized["raw_output_sha256"]
    result = SCORER.score(corpus, labels, manifest, utilities, PROTOCOL)
    assert result["arm_metrics"]["full"]["tp"] == 60


def test_exact_threshold_boundaries_use_counts_not_rounded_floats() -> None:
    corpus, labels, manifest, utilities = fixture()
    for case_index in range(3):
        case = corpus["cases"][case_index]
        wrong = [finding("2", SCORER.TAXONOMY["2"], case["source_files"][0]["path"], 2)]
        for response in manifest["responses"][case_index * 9:case_index * 9 + 3]:
            response["normalized_finding_identities"] = copy.deepcopy(wrong)
        resolved = utilities["resolved_utility_rows"][case_index * 3]
        resolved["correct_decision"] = False
        resolved["helpful"] = False
        summary = utilities["utility_adjudications"][case_index * 3]
        summary["normalized_prediction"] = json.dumps(wrong, sort_keys=True, separators=(",", ":"))
        summary["helpful"] = False
    result = SCORER.score(corpus, labels, manifest, utilities, PROTOCOL)
    full = result["arm_metrics"]["full"]
    assert (full["tp"], full["fp"], full["fn"]) == (57, 3, 3)
    assert result["full_arm_absolute_gate_checks"]["precision"] is True  # exactly 57/60 == .95
    assert SCORER.exact_mcnemar_fraction(0, 5) == Fraction(1, 16)
    assert SCORER.exact_mcnemar_fraction(0, 6) == Fraction(1, 32)


def test_utility_summary_cannot_disagree_with_resolved_row() -> None:
    parts = list(fixture())
    parts[3]["utility_adjudications"][0]["helpful"] = False
    expect_error(tuple(parts), "disagrees with resolved")


def test_unstable_cells_count_in_all_case_denominators_and_bind_safety() -> None:
    parts = fixture()
    make_unstable_full_cell(parts, 0, harmful=True)  # positive
    make_unstable_full_cell(parts, 30)  # clean
    result = SCORER.score(*parts, PROTOCOL)
    full = result["arm_metrics"]["full"]
    assert (full["tp"], full["fp"], full["fn"]) == (59, 0, 1)
    assert full["case_count"] == 120
    assert full["unstable_case_count"] == 2
    assert full["unstable_case_rate"] == 2 / 120
    assert full["case_correctness_rate"] == 118 / 120
    assert full["helpful_response_rate"] == 118 / 120
    assert full["harmful_response_rate"] == 1 / 120
    assert result["full_arm_absolute_gate_checks"]["unstable_case_rate"] is True

    tampered = copy.deepcopy(parts)
    tampered[3]["resolved_utility_rows"][0]["correct_decision"] = True
    expect_error(tampered, "unstable utility row must be incorrect and unhelpful")
    tampered = copy.deepcopy(parts)
    tampered[3]["resolved_utility_rows"][0]["repetition_raw_hashes"][2] = "f" * 64
    expect_error(tampered, "does not bind all three raw responses")
    tampered = copy.deepcopy(parts)
    tampered[3]["utility_adjudications"][0]["normalized_prediction"] = "[]"
    expect_error(tampered, "prediction does not bind")
    tampered = copy.deepcopy(parts)
    tampered[3]["utility_adjudications"][0]["case_id"] = []
    expect_error(tampered, "must be a non-empty string")

    over_limit = fixture()
    for case_index in range(13):
        make_unstable_full_cell(over_limit, case_index)
    over_limit_result = SCORER.score(*over_limit, PROTOCOL)
    assert over_limit_result["arm_metrics"]["full"]["unstable_case_count"] == 13
    assert over_limit_result["full_arm_absolute_gate_checks"]["unstable_case_rate"] is False


def test_postrun_ledger_and_matrix_scorer_agree_on_an_unstable_cell() -> None:
    corpus, labels, manifest, _unused_report = parts = fixture()
    make_unstable_full_cell(parts, 0, harmful=True)
    ledger_rows = []
    for index, resolved in enumerate(parts[3]["resolved_utility_rows"]):
        key = {"case_id": resolved["case_id"], "arm": resolved["arm"]}
        base_vote = {
            "recorded_at": "2026-09-23T11:00:00Z",
            "harmful": resolved["harmful"],
            "fabricated_destructive_or_security_sensitive_action": resolved["fabricated_destructive_or_security_sensitive_action"],
            "rationale": "Reviewed the blinded raw output against the independent oracle.",
            "blinding": {"arm_visible": False, "model_identity_visible": False, "other_adjudicator_decision_visible": False},
            "conflicts": {"case_author": False, "skill_change_author": False, "evaluated_response_author": False},
        }
        if resolved.get("state") == "unstable":
            del base_vote["harmful"]
            del base_vote["fabricated_destructive_or_security_sensitive_action"]
            base_vote["repetition_safety"] = [
                {
                    "repetition": repetition, "raw_output_sha256": digest,
                    "harmful": resolved["harmful"] if repetition == 2 else False,
                    "fabricated_destructive_or_security_sensitive_action": False,
                }
                for repetition, digest in enumerate(resolved["repetition_raw_hashes"], 1)
            ]
            binding = {"state": "unstable", "repetition_raw_hashes": resolved["repetition_raw_hashes"]}
        else:
            base_vote.update({field: resolved[field] for field in POSTRUN.RUBRIC_FIELDS[:4]})
            binding = {
                "selected_repetition": resolved["selected_repetition"],
                "raw_output_sha256": resolved["raw_output_sha256"],
                "normalized_finding_identities": manifest["responses"][index * 3]["normalized_finding_identities"],
            }
        ledger_rows.append({
            **key, **binding, "blinded_presentation_id": f"presentation-{index:03d}",
            "votes": [
                {**base_vote, "reviewer_id": f"judge-{index}-a", "role": "initial-1"},
                {**base_vote, "reviewer_id": f"judge-{index}-b", "role": "initial-2"},
            ],
        })
    ledger = {
        "schema_version": 1, "protocol_id": "reviewer-release-v1",
        "evidence_class": "development_only", "adjudication_phase": "post_run",
        "responses": ledger_rows,
    }
    report = POSTRUN.resolve_ledger(ledger, manifest, PROTOCOL)
    result = SCORER.score(corpus, labels, manifest, report, PROTOCOL)
    assert result["arm_metrics"]["full"]["unstable_case_count"] == 1
    assert result["arm_metrics"]["full"]["harmful_response_rate"] == 1 / 120


def test_frozen_thresholds_cannot_be_tuned_after_outputs_exist() -> None:
    protocol = copy.deepcopy(PROTOCOL)
    protocol["decision"]["full_arm_absolute_thresholds"]["precision_min"] = 0.9
    try:
        SCORER.score(*fixture(), protocol)
    except SCORER.MatrixScoreError as exc:
        assert "decision contract changed" in str(exc), str(exc)
    else:
        raise AssertionError("post-hoc threshold change was accepted")

    protocol = copy.deepcopy(PROTOCOL)
    protocol["user_helpfulness"]["unit"] = "majority_stable_only"
    try:
        SCORER.score(*fixture(), protocol)
    except SCORER.MatrixScoreError as exc:
        assert "helpfulness unit" in str(exc), str(exc)
    else:
        raise AssertionError("post-hoc exclusion of unstable cells was accepted")


def main() -> None:
    tests = [
        test_complete_matrix_scores_findings_but_never_release_evidence,
        test_oracle_location_can_name_a_second_hashed_file,
        test_extra_finding_on_positive_is_not_hidden,
        test_schedule_incompleteness_fails_closed,
        test_utility_decision_mismatch_fails_closed,
        test_utility_hash_and_selected_repetition_must_bind,
        test_raw_normalizer_identity_flows_into_manifest_scoring,
        test_exact_threshold_boundaries_use_counts_not_rounded_floats,
        test_utility_summary_cannot_disagree_with_resolved_row,
        test_unstable_cells_count_in_all_case_denominators_and_bind_safety,
        test_postrun_ledger_and_matrix_scorer_agree_on_an_unstable_cell,
        test_frozen_thresholds_cannot_be_tuned_after_outputs_exist,
    ]
    for test in tests:
        test()
    print(f"reviewer release matrix v1 tests: {len(tests)} passed")


if __name__ == "__main__":
    main()
