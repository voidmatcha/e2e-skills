#!/usr/bin/env python3
"""Fail-closed, development-only scorer for reviewer-release-v1.

This scorer consumes already-normalized predictions and already-resolved human
utility adjudications.  It does not normalize model prose, adjudicate responses,
verify custody, or emit release-grade evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import json
import math
from pathlib import Path
import random
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTOCOL = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"
ARMS = ("full", "catalog-only", "no-skill")
FRAMEWORKS = ("playwright", "cypress")
LABELS = ("positive", "clean")
SEVERITIES = ("P0", "P1", "P2")
sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
from reviewer_taxonomy_contract import REVIEWER_TAXONOMY  # noqa: E402

TAXONOMY = {pattern_id: severity for pattern_id, _title, severity in REVIEWER_TAXONOMY}


class ScoreError(ValueError):
    """Input cannot support the frozen calculation."""


def load_json(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ScoreError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, json.JSONDecodeError) as exc:
        raise ScoreError(f"cannot read JSON {path}: {exc}") from exc


def exact_keys(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ScoreError(f"{where} keys must be {sorted(keys)}; got {actual}")
    return value


def nonempty(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScoreError(f"{where} must be a non-empty string")
    return value


def boolean(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise ScoreError(f"{where} must be boolean")
    return value


def validate_protocol(protocol: dict[str, Any]) -> None:
    if protocol.get("protocol_id") != "reviewer-release-v1":
        raise ScoreError("protocol_id must be reviewer-release-v1")
    if protocol.get("schedule") != {
        "unique_cases": 120,
        "arm_count": 3,
        "repetitions_per_case_arm": 3,
        "scheduled_model_calls": 1080,
        "per_call_wall_timeout_seconds": 600,
        "attempts_per_call": 1,
        "timeout_or_interruption_handling": "inconclusive_no_replacement_call",
        "fresh_workspace_per_repetition": True,
        "repetitions_are_independent_samples": False,
        "repetition_purpose": "stability_only",
        "stable_prediction_rule": "at_least_2_of_3_identical_normalized_predictions",
        "invalid_or_unstable_handling": "invalid_cannot_vote;unstable_scores_incorrect_unhelpful_in_all_case_denominators",
    }:
        raise ScoreError("protocol schedule is not the frozen release-v1 schedule")
    stats = protocol.get("statistics", {})
    ci = stats.get("confidence_interval", {})
    if (
        stats.get("independent_unit") != "unique_case"
        or stats.get("repeated_runs_count_as_additional_cases") is not False
        or ci.get("method") != "case_stratified_bootstrap"
        or ci.get("iterations") != 10000
        or ci.get("seed") != 20260902
        or ci.get("strata") != ["framework", "label"]
    ):
        raise ScoreError("protocol statistics are not the frozen release-v1 contract")


def validate_input(payload: Any, protocol: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
    root = exact_keys(
        payload,
        {"schema_version", "protocol_id", "provenance", "cases", "calls", "utility_adjudications"},
        "input",
    )
    if root["schema_version"] != 1 or root["protocol_id"] != protocol["protocol_id"]:
        raise ScoreError("input schema_version/protocol_id mismatch")
    provenance = exact_keys(
        root["provenance"],
        {"development_only", "contamination_detected", "independent_human_utility_adjudication_complete"},
        "input.provenance",
    )
    if boolean(provenance["development_only"], "provenance.development_only") is not True:
        raise ScoreError("this scorer accepts development_only inputs only")
    if boolean(provenance["contamination_detected"], "provenance.contamination_detected"):
        raise ScoreError("contamination_detected prevents scoring")
    if not boolean(
        provenance["independent_human_utility_adjudication_complete"],
        "provenance.independent_human_utility_adjudication_complete",
    ):
        raise ScoreError("resolved independent human utility adjudication is required")

    cases = root["cases"]
    calls = root["calls"]
    utilities = root["utility_adjudications"]
    if not isinstance(cases, list) or not isinstance(calls, list) or not isinstance(utilities, list):
        raise ScoreError("cases, calls, and utility_adjudications must be arrays")
    if len(cases) != 120:
        raise ScoreError(f"exactly 120 cases required; got {len(cases)}")

    case_ids: set[str] = set()
    lineages: set[str] = set()
    repo_counts: Counter[str] = Counter()
    cell_counts: Counter[tuple[str, str]] = Counter()
    positive_patterns: Counter[str] = Counter()
    guard_patterns: dict[str, set[str]] = defaultdict(set)
    severity_counts: Counter[str] = Counter()
    for index, raw in enumerate(cases):
        case = exact_keys(
            raw,
            {"id", "framework", "label", "oracle_token", "pattern_id", "severity", "guard_pattern_ids", "source_repository", "lineage_cluster"},
            f"cases[{index}]",
        )
        case_id = nonempty(case["id"], f"cases[{index}].id")
        if case_id in case_ids:
            raise ScoreError(f"duplicate case id: {case_id}")
        case_ids.add(case_id)
        framework = case["framework"]
        label = case["label"]
        if framework not in FRAMEWORKS or label not in LABELS:
            raise ScoreError(f"invalid framework/label for {case_id}")
        oracle = nonempty(case["oracle_token"], f"case {case_id} oracle_token")
        repo = nonempty(case["source_repository"], f"case {case_id} source_repository")
        lineage = nonempty(case["lineage_cluster"], f"case {case_id} lineage_cluster")
        if lineage in lineages:
            raise ScoreError(f"duplicate lineage_cluster: {lineage}")
        lineages.add(lineage)
        repo_counts[repo] += 1
        cell_counts[(framework, label)] += 1
        guards = case["guard_pattern_ids"]
        if not isinstance(guards, list) or any(not isinstance(v, str) for v in guards) or len(set(guards)) != len(guards):
            raise ScoreError(f"case {case_id} guard_pattern_ids must be unique strings")
        if label == "positive":
            if oracle == "clean" or not isinstance(case["pattern_id"], str) or case["pattern_id"] not in TAXONOMY or case["severity"] != TAXONOMY[case["pattern_id"]] or guards:
                raise ScoreError(f"positive case {case_id} has invalid oracle taxonomy")
            positive_patterns[case["pattern_id"]] += 1
            severity_counts[case["severity"]] += 1
        else:
            if oracle != "clean" or case["pattern_id"] is not None or case["severity"] is not None:
                raise ScoreError(f"clean case {case_id} has invalid oracle taxonomy")
            for pattern in guards:
                if pattern not in TAXONOMY:
                    raise ScoreError(f"clean case {case_id} has unknown guard pattern {pattern}")
                guard_patterns[pattern].add(case_id)
    if cell_counts != Counter({(f, l): 30 for f in FRAMEWORKS for l in LABELS}):
        raise ScoreError(f"framework/label cells must each contain 30 cases; got {dict(cell_counts)}")
    if any(count > 2 for count in repo_counts.values()):
        raise ScoreError("a source_repository contributes more than two cases")
    expected_patterns = set(TAXONOMY)
    if set(positive_patterns) != expected_patterns or any(value < 2 for value in positive_patterns.values()):
        raise ScoreError("every stable pattern requires at least two positive cases")
    if set(guard_patterns) != expected_patterns or any(len(value) < 2 for value in guard_patterns.values()):
        raise ScoreError("every stable pattern requires at least two distinct clean guard cases")
    if any(severity_counts[value] < 10 for value in SEVERITIES):
        raise ScoreError("every severity stratum requires at least ten positive cases")

    expected_calls = len(cases) * len(ARMS) * 3
    if len(calls) != expected_calls:
        raise ScoreError(f"exactly {expected_calls} calls required; got {len(calls)}")
    seen_calls: set[tuple[str, str, int]] = set()
    predictions: dict[tuple[str, str], list[str]] = defaultdict(list)
    for index, raw in enumerate(calls):
        call = exact_keys(raw, {"case_id", "arm", "repetition", "valid", "normalized_prediction"}, f"calls[{index}]")
        key = (call["case_id"], call["arm"], call["repetition"])
        if not isinstance(call["case_id"], str) or call["case_id"] not in case_ids or call["arm"] not in ARMS or type(call["repetition"]) is not int or call["repetition"] not in (1, 2, 3):
            raise ScoreError(f"invalid call key: {key}")
        if key in seen_calls:
            raise ScoreError(f"duplicate call: {key}")
        seen_calls.add(key)
        if not boolean(call["valid"], f"call {key} valid"):
            raise ScoreError(f"invalid model call: {key}")
        prediction = nonempty(call["normalized_prediction"], f"call {key} normalized_prediction")
        predictions[(call["case_id"], call["arm"])].append(prediction)
    stable: dict[tuple[str, str], str] = {}
    for key, values in predictions.items():
        common = Counter(values).most_common()
        if not common or common[0][1] < 2:
            raise ScoreError(f"unstable normalized predictions: {key}")
        stable[key] = common[0][0]
    if len(stable) != len(cases) * len(ARMS):
        raise ScoreError("missing case/arm prediction cell")

    if len(utilities) != len(cases) * len(ARMS):
        raise ScoreError(f"exactly {len(cases) * len(ARMS)} utility adjudications required; got {len(utilities)}")
    oracle_by_id = {case["id"]: case["oracle_token"] for case in cases}
    seen_utilities: set[tuple[str, str]] = set()
    for index, raw in enumerate(utilities):
        row = exact_keys(
            raw,
            {"case_id", "arm", "normalized_prediction", "helpful", "harmful", "fabricated_destructive_or_security_sensitive_action"},
            f"utility_adjudications[{index}]",
        )
        key = (row["case_id"], row["arm"])
        if not isinstance(row["case_id"], str) or not isinstance(row["arm"], str) or key not in stable or key in seen_utilities:
            raise ScoreError(f"invalid or duplicate utility key: {key}")
        seen_utilities.add(key)
        if row["normalized_prediction"] != stable[key]:
            raise ScoreError(f"utility prediction does not match stable response: {key}")
        for field in ("helpful", "harmful", "fabricated_destructive_or_security_sensitive_action"):
            boolean(row[field], f"utility {key} {field}")
        if row["helpful"] and row["harmful"]:
            raise ScoreError(f"utility cannot be both helpful and harmful: {key}")
        if row["helpful"] and stable[key] != oracle_by_id[row["case_id"]]:
            raise ScoreError(f"an incorrect response cannot be adjudicated helpful: {key}")
        if row["fabricated_destructive_or_security_sensitive_action"] and not row["harmful"]:
            raise ScoreError(f"a fabricated destructive or sensitive action must be harmful: {key}")
    return cases, calls, utilities


def nearest_rank(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def exact_mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / (2**n)
    return min(1.0, 2 * tail)


def rate(rows: list[dict], field: str) -> float:
    return sum(bool(row[field]) for row in rows) / len(rows)


def case_metrics(rows: list[dict]) -> dict[str, Any]:
    return {
        "case_count": len(rows),
        "case_correctness_rate": rate(rows, "correct"),
        "helpful_response_rate": rate(rows, "helpful"),
        "harmful_response_rate": rate(rows, "harmful"),
        "fabricated_destructive_or_security_sensitive_actions": sum(row["fabricated"] for row in rows),
        "strata": {
            f"{f}/{label}": {
                "case_correctness_rate": rate([row for row in rows if row["framework"] == f and row["label"] == label], "correct"),
                "helpful_response_rate": rate([row for row in rows if row["framework"] == f and row["label"] == label], "helpful"),
            }
            for f in FRAMEWORKS for label in LABELS
        },
    }


def bootstrap(rows_by_arm: dict[str, list[dict]], protocol: dict[str, Any]) -> dict[str, Any]:
    full = {row["case_id"]: row for row in rows_by_arm["full"]}
    control = {row["case_id"]: row for row in rows_by_arm["no-skill"]}
    strata: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in full.values():
        strata[(row["framework"], row["label"])].append(row["case_id"])
    stratum_keys = [(framework, label) for framework in FRAMEWORKS for label in LABELS]
    for key in stratum_keys:
        strata[key].sort()
    ci = protocol["statistics"]["confidence_interval"]
    generator = random.Random(ci["seed"])
    correctness: list[float] = []
    helpfulness: list[float] = []
    for _ in range(ci["iterations"]):
        sample = [
            case_id
            for key in stratum_keys
            for case_id in generator.choices(strata[key], k=len(strata[key]))
        ]
        correctness.append(sum(full[i]["correct"] - control[i]["correct"] for i in sample) / len(sample))
        helpfulness.append(sum(full[i]["helpful"] - control[i]["helpful"] for i in sample) / len(sample))
    return {
        "method": ci["method"],
        "confidence": ci["confidence"],
        "iterations": ci["iterations"],
        "seed": ci["seed"],
        "correctness_lift": {"lower": nearest_rank(correctness, 0.025), "upper": nearest_rank(correctness, 0.975)},
        "helpfulness_lift": {"lower": nearest_rank(helpfulness, 0.025), "upper": nearest_rank(helpfulness, 0.975)},
    }


def score(payload: Any, protocol: dict[str, Any]) -> dict[str, Any]:
    validate_protocol(protocol)
    cases, calls, utilities = validate_input(payload, protocol)
    utility_by_key = {(row["case_id"], row["arm"]): row for row in utilities}
    predictions: dict[tuple[str, str], list[str]] = defaultdict(list)
    for call in calls:
        predictions[(call["case_id"], call["arm"])].append(call["normalized_prediction"])
    rows_by_arm: dict[str, list[dict]] = {arm: [] for arm in ARMS}
    for case in cases:
        for arm in ARMS:
            prediction = Counter(predictions[(case["id"], arm)]).most_common(1)[0][0]
            utility = utility_by_key[(case["id"], arm)]
            rows_by_arm[arm].append({
                "case_id": case["id"], "framework": case["framework"], "label": case["label"],
                "pattern_id": case["pattern_id"], "severity": case["severity"],
                "correct": prediction == case["oracle_token"], "helpful": utility["helpful"],
                "harmful": utility["harmful"], "fabricated": utility["fabricated_destructive_or_security_sensitive_action"],
            })
    metrics = {arm: case_metrics(rows) for arm, rows in rows_by_arm.items()}
    full = rows_by_arm["full"]
    control = rows_by_arm["no-skill"]
    b = sum(f["correct"] and not c["correct"] for f, c in zip(full, control))
    c = sum(not f["correct"] and c["correct"] for f, c in zip(full, control))
    correctness_delta_count = sum(row["correct"] for row in full) - sum(row["correct"] for row in control)
    helpfulness_delta_count = sum(row["helpful"] for row in full) - sum(row["helpful"] for row in control)
    correctness_lift_fraction = Fraction(correctness_delta_count, len(full))
    helpfulness_lift_fraction = Fraction(helpfulness_delta_count, len(full))
    correctness_lift = float(correctness_lift_fraction)
    helpfulness_lift = float(helpfulness_lift_fraction)
    intervals = bootstrap(rows_by_arm, protocol)
    paired = protocol["decision"]["primary_paired_lift_thresholds"]
    noninferiority: dict[str, bool] = {}
    for dimension in ("framework", "label"):
        values = FRAMEWORKS if dimension == "framework" else LABELS
        for value in values:
            frows = [row for row in full if row[dimension] == value]
            crows = [row for row in control if row[dimension] == value]
            for field in ("correct", "helpful"):
                delta = Fraction(sum(row[field] for row in frows) - sum(row[field] for row in crows), len(frows))
                noninferiority[f"{dimension}/{value}/{field}"] = delta >= -Fraction(str(paired["per_framework_or_label_noninferiority_margin"]))
    p_value = exact_mcnemar(b, c)
    paired_checks = {
        "case_correctness_lift": correctness_lift_fraction >= Fraction(str(paired["case_correctness_lift_min"])),
        "case_correctness_lift_cases": b - c >= paired["case_correctness_lift_min_cases"],
        "mcnemar": p_value < paired["exact_mcnemar_p_value_max_exclusive"] and b > c,
        "correctness_ci_lower": intervals["correctness_lift"]["lower"] > paired["correctness_lift_ci_lower_bound_min_exclusive"],
        "helpfulness_lift": helpfulness_lift_fraction >= Fraction(str(paired["helpful_response_rate_lift_min"])),
        "helpfulness_ci_lower": intervals["helpfulness_lift"]["lower"] > paired["helpfulness_lift_ci_lower_bound_min_exclusive"],
        "stratum_noninferiority": all(noninferiority.values()),
    }
    return {
        "schema_version": 1,
        "protocol_id": protocol["protocol_id"],
        "status": "INCONCLUSIVE",
        "evidence_scope": "development-only",
        "release_claim_eligible": False,
        "frozen_release_decision": "NOT_EVALUATED",
        "status_reasons": [
            "offline scorer does not verify custody, isolation, attestation, normalization, or human-judge provenance",
            "opaque normalized tokens cannot compute finding-level precision, recall, or F1; frozen absolute gates are not evaluated",
        ],
        "development_case_diagnostics": metrics,
        "paired_full_vs_no_skill": {
            "correctness_lift": correctness_lift, "helpfulness_lift": helpfulness_lift,
            "discordant": {"full_correct_only": b, "no_skill_correct_only": c},
            "exact_mcnemar_two_sided_p": p_value, "bootstrap": intervals,
            "noninferiority": noninferiority, "checks": paired_checks,
        },
        "release_gates_not_evaluated": ["full_arm_absolute_thresholds", "requires_every_gate"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    try:
        args = parser.parse_args(argv)
        result = score(load_json(args.input), load_json(args.protocol))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except ScoreError as exc:
        print(json.dumps({"status": "INCONCLUSIVE", "release_claim_eligible": False, "error": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    sys.exit(main())
