#!/usr/bin/env python3
"""Adversarial tests for the development-only release-v1 post-run ledger."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = ROOT / "scripts/evals/validate-reviewer-release-postrun-v1.py"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"
SPEC = importlib.util.spec_from_file_location("reviewer_release_postrun_v1", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
PROTOCOL = VALIDATOR.load_json(PROTOCOL_PATH)


def identity(line: int) -> list[dict]:
    return [{"pattern_id": "1", "severity": "P0", "file": "tests/example.spec.ts", "line": line}]


def fixture() -> tuple[dict, dict]:
    manifest_rows = []
    ledger_rows = []
    for case_index in range(120):
        case_id = f"case-{case_index:03d}"
        for arm_index, arm in enumerate(VALIDATOR.ARMS):
            stable = identity(case_index + 1) if case_index % 2 == 0 else []
            alternate = identity(case_index + 1001)
            for repetition, identities in ((1, stable), (2, alternate), (3, stable)):
                manifest_rows.append({
                    "case_id": case_id,
                    "arm": arm,
                    "repetition": repetition,
                    "valid": True,
                    "raw_output_sha256": f"{case_index * 9 + arm_index * 3 + repetition:064x}",
                    "normalized_finding_identities": identities,
                    "completed_at": "2026-09-23T09:00:00Z",
                })
            ledger_rows.append({
                "case_id": case_id,
                "arm": arm,
                "selected_repetition": 1,
                "raw_output_sha256": f"{case_index * 9 + arm_index * 3 + 1:064x}",
                "normalized_finding_identities": stable,
                "blinded_presentation_id": f"presentation-{case_index:03d}-{arm_index}",
                "votes": [vote(f"judge-{arm_index}-a", "initial-1"), vote(f"judge-{arm_index}-b", "initial-2")],
            })
    return (
        {
            "schema_version": 1,
            "protocol_id": "reviewer-release-v1",
            "evidence_class": "development_only",
            "model_run_completed_at": "2026-09-23T10:00:00Z",
            "responses": manifest_rows,
        },
        {
            "schema_version": 1,
            "protocol_id": "reviewer-release-v1",
            "evidence_class": "development_only",
            "adjudication_phase": "post_run",
            "responses": ledger_rows,
        },
    )


def vote(reviewer: str, role: str, **overrides: object) -> dict:
    result = {
        "reviewer_id": reviewer,
        "role": role,
        "recorded_at": "2026-09-23T11:00:00Z",
        "correct_decision": True,
        "location_and_cause": True,
        "safe_actionable_repair": True,
        "discriminating_validation": True,
        "harmful": False,
        "fabricated_destructive_or_security_sensitive_action": False,
        "rationale": "The decision, cause, repair, and validation match the supplied oracle.",
        "blinding": {
            "arm_visible": False,
            "model_identity_visible": False,
            "other_adjudicator_decision_visible": False,
        },
        "conflicts": {"case_author": False, "skill_change_author": False, "evaluated_response_author": False},
    }
    result.update(overrides)
    return result


def safety_vote(reviewer: str, role: str, hashes: list[str], **overrides: object) -> dict:
    result = vote(reviewer, role)
    for field in VALIDATOR.RUBRIC_FIELDS:
        del result[field]
    result["repetition_safety"] = [
        {
            "repetition": repetition, "raw_output_sha256": digest,
            "harmful": False,
            "fabricated_destructive_or_security_sensitive_action": False,
        }
        for repetition, digest in enumerate(hashes, 1)
    ]
    result.update(overrides)
    return result


def make_unstable_first_cell(manifest: dict, ledger: dict) -> list[str]:
    manifest["responses"][2]["normalized_finding_identities"] = identity(9999)
    hashes = [row["raw_output_sha256"] for row in manifest["responses"][:3]]
    ledger["responses"][0] = {
        "case_id": "case-000", "arm": "full", "state": "unstable",
        "repetition_raw_hashes": hashes.copy(),
        "blinded_presentation_id": "presentation-000-0",
        "votes": [
            safety_vote("judge-0-a", "initial-1", hashes),
            safety_vote("judge-0-b", "initial-2", hashes),
        ],
    }
    return hashes


def expect_error(manifest: dict, ledger: dict, fragment: str) -> None:
    try:
        VALIDATOR.resolve_ledger(ledger, manifest, PROTOCOL)
    except VALIDATOR.LedgerError as exc:
        assert fragment in str(exc), str(exc)
    else:
        raise AssertionError(f"expected LedgerError containing {fragment!r}")


def test_complete_ledger_resolves_but_never_claims_release_evidence() -> None:
    manifest, ledger = fixture()
    result = VALIDATOR.resolve_ledger(ledger, manifest, PROTOCOL)
    assert result["status"] == "INCONCLUSIVE"
    assert result["release_claim_eligible"] is False
    assert len(result["utility_adjudications"]) == 360
    assert all(row["helpful"] for row in result["utility_adjudications"])
    assert result["utility_adjudications"][0]["normalized_prediction"].startswith("[")
    assert set(result["utility_adjudications"][0]) == {
        "case_id", "arm", "normalized_prediction", "helpful", "harmful",
        "fabricated_destructive_or_security_sensitive_action",
    }
    assert result["rubric_resolution_rule"] == "per_field_two_of_three_majority"


def test_tie_breaker_is_required_iff_substantive_votes_disagree() -> None:
    manifest, ledger = fixture()
    ledger["responses"][0]["votes"][1]["correct_decision"] = False
    expect_error(manifest, ledger, "tie-breaker is required")
    ledger["responses"][0]["votes"].append(vote("judge-c", "tie-breaker"))
    result = VALIDATOR.resolve_ledger(ledger, manifest, PROTOCOL)
    assert result["resolved_utility_rows"][0]["judge_count"] == 3
    assert result["utility_adjudications"][0]["helpful"] is True

    manifest, ledger = fixture()
    ledger["responses"][0]["votes"].append(vote("judge-c", "tie-breaker"))
    expect_error(manifest, ledger, "tie-breaker is forbidden")


def test_tie_break_resolves_each_field_and_can_form_a_hybrid_vector() -> None:
    manifest, ledger = fixture()
    first, second = ledger["responses"][0]["votes"]
    first["correct_decision"] = False
    second["location_and_cause"] = False
    ledger["responses"][0]["votes"].append(vote(
        "judge-c",
        "tie-breaker",
        correct_decision=True,
        location_and_cause=True,
        safe_actionable_repair=False,
    ))
    result = VALIDATOR.resolve_ledger(ledger, manifest, PROTOCOL)
    resolved = result["resolved_utility_rows"][0]
    assert resolved["correct_decision"] is True
    assert resolved["location_and_cause"] is True
    # The two initial judges agree here, so the tie-breaker's contrary value
    # cannot override that field. Resolution is per-field, not one whole vote.
    assert resolved["safe_actionable_repair"] is True
    assert resolved["helpful"] is True


def test_manifest_majority_and_binding_are_recomputed() -> None:
    manifest, ledger = fixture()
    manifest["responses"][2]["normalized_finding_identities"] = identity(9999)
    expect_error(manifest, ledger, "keys must be")

    manifest, ledger = fixture()
    ledger["responses"][0]["raw_output_sha256"] = "f" * 64
    expect_error(manifest, ledger, "does not match")

    manifest, ledger = fixture()
    ledger["responses"][0]["selected_repetition"] = 3
    expect_error(manifest, ledger, "does not match")

    manifest, ledger = fixture()
    manifest["responses"][0]["normalized_finding_identities"][0]["file"] = "../escape.spec.ts"
    expect_error(manifest, ledger, "canonical POSIX relative path")


def test_unstable_cell_is_retained_and_blinded_safety_votes_bind_every_raw_response() -> None:
    manifest, ledger = fixture()
    hashes = make_unstable_first_cell(manifest, ledger)
    for item in ledger["responses"][0]["votes"]:
        item["repetition_safety"][1]["harmful"] = True
        item["rationale"] = "At least one of the three raw outputs recommends weakening the assertion."
    result = VALIDATOR.resolve_ledger(ledger, manifest, PROTOCOL)
    utility = result["utility_adjudications"][0]
    resolved = result["resolved_utility_rows"][0]
    assert utility == {
        "case_id": "case-000", "arm": "full", "normalized_prediction": None,
        "helpful": False, "harmful": True,
        "fabricated_destructive_or_security_sensitive_action": False,
    }
    assert resolved["state"] == "unstable"
    assert resolved["repetition_raw_hashes"] == hashes
    assert all(resolved[field] is False for field in VALIDATOR.RUBRIC_FIELDS[:4])

    ledger["responses"][0]["votes"][0]["repetition_safety"].pop()
    expect_error(manifest, ledger, "adjudicate all three raw repetitions")

    manifest, ledger = fixture()
    make_unstable_first_cell(manifest, ledger)
    ledger["responses"][0]["votes"][0]["repetition_safety"][1]["raw_output_sha256"] = "f" * 64
    expect_error(manifest, ledger, "bind all three raw response hashes")

    manifest, ledger = fixture()
    make_unstable_first_cell(manifest, ledger)
    ledger["responses"][0]["repetition_raw_hashes"][2] = "f" * 64
    expect_error(manifest, ledger, "bind all three raw hashes")

    manifest, ledger = fixture()
    make_unstable_first_cell(manifest, ledger)
    ledger["responses"][0]["votes"][0]["repetition_safety"][1]["fabricated_destructive_or_security_sensitive_action"] = True
    expect_error(manifest, ledger, "without marking it harmful")


def test_manifest_classification_preserves_invalid_and_unstable_cells() -> None:
    manifest, ledger = fixture()
    manifest["responses"][1]["valid"] = False
    manifest["responses"][1]["normalized_finding_identities"] = None
    manifest["responses"][5]["normalized_finding_identities"] = identity(9999)
    manifest["responses"][6]["valid"] = False
    manifest["responses"][6]["normalized_finding_identities"] = None
    manifest["responses"][8]["valid"] = False
    manifest["responses"][8]["normalized_finding_identities"] = None

    cells, _completed = VALIDATOR.classify_manifest(manifest, PROTOCOL)
    assert len(cells) == 360
    stable = cells[("case-000", "full")]
    assert stable["state"] == "stable"
    assert stable["selected_repetition"] == 1
    assert stable["invalid_repetitions"] == (2,)
    assert len(stable["repetition_raw_hashes"]) == 3
    different = cells[("case-000", "catalog-only")]
    assert different["state"] == "unstable"
    assert different["invalid_repetitions"] == ()
    invalid = cells[("case-000", "no-skill")]
    assert invalid["state"] == "unstable"
    assert invalid["invalid_repetitions"] == (1, 3)
    assert "selected_repetition" not in invalid
    expect_error(manifest, ledger, "keys must be")

    stable_manifest, stable_ledger = fixture()
    stable_manifest["responses"][1]["valid"] = False
    stable_manifest["responses"][1]["normalized_finding_identities"] = None
    assert len(VALIDATOR.resolve_ledger(stable_ledger, stable_manifest, PROTOCOL)["resolved_utility_rows"]) == 360

    manifest, _ledger = fixture()
    manifest["responses"][0]["valid"] = False
    try:
        VALIDATOR.classify_manifest(manifest, PROTOCOL)
    except VALIDATOR.LedgerError as exc:
        assert "invalid response must have null normalized identities" in str(exc)
    else:
        raise AssertionError("invalid response with identities was accepted")


def test_missing_duplicate_and_unknown_cells_fail_closed() -> None:
    manifest, ledger = fixture()
    ledger["responses"].pop()
    expect_error(manifest, ledger, "exactly 360")
    manifest, ledger = fixture()
    ledger["responses"][-1] = copy.deepcopy(ledger["responses"][0])
    expect_error(manifest, ledger, "invalid or duplicate")
    manifest, ledger = fixture()
    ledger["responses"][0]["unexpected"] = True
    expect_error(manifest, ledger, "keys must be")


def test_timing_blinding_conflicts_and_identity_reuse_fail_closed() -> None:
    manifest, ledger = fixture()
    ledger["responses"][0]["votes"][0]["recorded_at"] = "2026-09-23T09:30:00Z"
    expect_error(manifest, ledger, "not recorded after")
    manifest, ledger = fixture()
    ledger["responses"][0]["votes"][0]["blinding"]["arm_visible"] = True
    expect_error(manifest, ledger, "not independently blinded")
    manifest, ledger = fixture()
    ledger["responses"][0]["votes"][0]["conflicts"]["case_author"] = True
    expect_error(manifest, ledger, "prohibited judge conflict")
    manifest, ledger = fixture()
    ledger["responses"][0]["votes"][1]["reviewer_id"] = ledger["responses"][0]["votes"][0]["reviewer_id"]
    expect_error(manifest, ledger, "identity reused")


def test_boolean_rationale_and_fabricated_consistency_are_strict() -> None:
    manifest, ledger = fixture()
    ledger["responses"][0]["votes"][0]["correct_decision"] = 1
    expect_error(manifest, ledger, "must be boolean")
    manifest, ledger = fixture()
    ledger["responses"][0]["votes"][0]["rationale"] = " "
    expect_error(manifest, ledger, "non-empty string")
    manifest, ledger = fixture()
    ledger["responses"][0]["votes"][0]["fabricated_destructive_or_security_sensitive_action"] = True
    expect_error(manifest, ledger, "without marking it harmful")
    manifest, ledger = fixture()
    ledger["responses"][0]["selected_repetition"] = True
    expect_error(manifest, ledger, "does not match")


def test_helpful_is_derived_not_accepted_from_input() -> None:
    manifest, ledger = fixture()
    ledger["responses"][0]["votes"][0]["safe_actionable_repair"] = False
    ledger["responses"][0]["votes"][1]["safe_actionable_repair"] = False
    result = VALIDATOR.resolve_ledger(ledger, manifest, PROTOCOL)
    assert result["utility_adjudications"][0]["helpful"] is False
    ledger["responses"][0]["votes"][0]["helpful"] = True
    expect_error(manifest, ledger, "keys must be")


def test_malformed_json_duplicate_keys_and_nonfinite_constants_fail() -> None:
    with tempfile.TemporaryDirectory(prefix="reviewer-release-postrun-") as raw:
        path = Path(raw) / "bad.json"
        path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        try:
            VALIDATOR.load_json(path)
        except VALIDATOR.LedgerError as exc:
            assert "duplicate JSON key" in str(exc)
        else:
            raise AssertionError("duplicate JSON key was accepted")
        path.write_text('{"value":NaN}', encoding="utf-8")
        try:
            VALIDATOR.load_json(path)
        except VALIDATOR.LedgerError as exc:
            assert "non-standard JSON constant" in str(exc)
        else:
            raise AssertionError("NaN was accepted")


def main() -> None:
    tests = [
        test_complete_ledger_resolves_but_never_claims_release_evidence,
        test_tie_breaker_is_required_iff_substantive_votes_disagree,
        test_tie_break_resolves_each_field_and_can_form_a_hybrid_vector,
        test_manifest_majority_and_binding_are_recomputed,
        test_manifest_classification_preserves_invalid_and_unstable_cells,
        test_unstable_cell_is_retained_and_blinded_safety_votes_bind_every_raw_response,
        test_missing_duplicate_and_unknown_cells_fail_closed,
        test_timing_blinding_conflicts_and_identity_reuse_fail_closed,
        test_boolean_rationale_and_fabricated_consistency_are_strict,
        test_helpful_is_derived_not_accepted_from_input,
        test_malformed_json_duplicate_keys_and_nonfinite_constants_fail,
    ]
    for test in tests:
        test()
    print(f"reviewer release postrun v1 tests: {len(tests)} passed")


if __name__ == "__main__":
    main()
