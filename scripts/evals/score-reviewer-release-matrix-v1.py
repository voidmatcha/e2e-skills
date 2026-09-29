#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Score a complete reviewer-release-v1 matrix for development diagnostics.

The scorer independently reconstructs majority-stable responses, finding-level
accuracy, paired lift, and frozen gates. It deliberately never promotes local
inputs to release evidence: custody, isolation, judge identity, and signatures
must be verified by a separate trusted release verifier.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path
import random
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROTOCOL = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"
POSTRUN_PATH = ROOT / "scripts/evals/validate-reviewer-release-postrun-v1.py"
SPEC = importlib.util.spec_from_file_location("release_postrun_v1", POSTRUN_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - installation failure
    raise RuntimeError("cannot load release-v1 post-run validator")
POSTRUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POSTRUN)

ARMS = ("full", "catalog-only", "no-skill")
FRAMEWORKS = ("playwright", "cypress")
KINDS = ("positive", "clean")
SEVERITIES = ("P0", "P1", "P2")
TAXONOMY = POSTRUN.TAXONOMY
IDENTITY_KEYS = POSTRUN.IDENTITY_KEYS
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
FROZEN_ABSOLUTE = {
    "precision_min": 0.95, "recall_min": 0.9, "f1_min": 0.925,
    "clean_false_positive_rate_max": 0.05, "per_framework_recall_min": 0.85,
    "pattern_macro_recall_min": 0.85, "per_pattern_recall_min": 0.5,
    "per_severity_stratum_recall_min": 0.9, "unstable_case_rate_max": 0.1,
    "helpful_response_rate_min": 0.85,
    "per_framework_and_label_helpful_response_rate_min": 0.8,
    "harmful_response_rate_max": 0.02,
    "fabricated_destructive_or_security_sensitive_actions_max": 0,
}
FROZEN_PAIRED = {
    "case_correctness_lift_min": 0.1, "case_correctness_lift_min_cases": 12,
    "exact_mcnemar_p_value_max_exclusive": 0.05,
    "correctness_lift_ci_lower_bound_min_exclusive": 0,
    "helpful_response_rate_lift_min": 0.1,
    "helpfulness_lift_ci_lower_bound_min_exclusive": 0,
    "per_framework_or_label_noninferiority_margin": 0.02,
}


class MatrixScoreError(ValueError):
    """An input cannot support the frozen calculation."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MatrixScoreError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                MatrixScoreError(f"non-standard JSON constant: {value}")
            ),
        )
    except MatrixScoreError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MatrixScoreError(f"cannot read strict JSON {path}: {exc}") from exc


def exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise MatrixScoreError(f"{where} keys must be {sorted(keys)}; got {actual}")
    return value


def nonempty(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MatrixScoreError(f"{where} must be a non-empty string")
    return value


def boolean(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise MatrixScoreError(f"{where} must be boolean")
    return value


def validate_protocol(protocol: Any) -> dict[str, Any]:
    try:
        POSTRUN.validate_protocol(protocol)
    except POSTRUN.LedgerError as exc:
        raise MatrixScoreError(str(exc)) from exc
    schedule = protocol.get("schedule", {})
    statistics = protocol.get("statistics", {})
    interval = statistics.get("confidence_interval", {})
    decision = protocol.get("decision", {})
    if schedule.get("scheduled_model_calls") != 1080 or schedule.get("invalid_or_unstable_handling") != "invalid_cannot_vote;unstable_scores_incorrect_unhelpful_in_all_case_denominators":
        raise MatrixScoreError("protocol schedule is not the frozen release-v1 schedule")
    if statistics.get("independent_unit") != "unique_case" or statistics.get("repeated_runs_count_as_additional_cases") is not False:
        raise MatrixScoreError("protocol independent-unit contract changed")
    if interval != {"method": "case_stratified_bootstrap", "confidence": 0.95, "iterations": 10000, "seed": 20260902, "strata": ["framework", "label"]}:
        raise MatrixScoreError("protocol bootstrap contract changed")
    if statistics.get("paired_significance_test") != {"method": "exact_mcnemar_two_sided", "alpha": 0.05, "direction_required": "full_better_than_no-skill"}:
        raise MatrixScoreError("protocol paired significance contract changed")
    if (
        decision.get("requires_every_gate") is not True
        or decision.get("rounding_policy") != "evaluate_exact_counts_before_display_rounding"
        or decision.get("catalog_only_role") != "diagnostic_secondary_arm_no_gate_substitution"
        or decision.get("full_arm_absolute_thresholds") != FROZEN_ABSOLUTE
        or decision.get("primary_paired_lift_thresholds") != FROZEN_PAIRED
    ):
        raise MatrixScoreError("protocol decision contract changed")
    return protocol


def validate_oracle(corpus: Any, labels: Any) -> dict[str, dict[str, Any]]:
    corpus = exact(corpus, {"schema_version", "protocol_id", "corpus_id", "frozen_at", "cases"}, "corpus")
    if corpus["schema_version"] != 1 or corpus["protocol_id"] != "reviewer-release-v1":
        raise MatrixScoreError("corpus schema_version/protocol_id mismatch")
    corpus_id = nonempty(corpus["corpus_id"], "corpus.corpus_id")
    rows = corpus["cases"]
    if not isinstance(rows, list) or len(rows) != 120:
        raise MatrixScoreError("corpus requires exactly 120 cases")
    cases: dict[str, dict[str, Any]] = {}
    source_paths: set[str] = set()
    source_roots: set[str] = set()
    repos: Counter[str] = Counter()
    cells: Counter[tuple[str, str]] = Counter()
    patterns: Counter[str] = Counter()
    guards: dict[str, set[str]] = defaultdict(set)
    severities: Counter[str] = Counter()
    for index, raw in enumerate(rows):
        row = exact(raw, {"case_id", "repo_id", "framework", "kind", "source_root", "source_files", "taxonomy_id", "severity", "guard_taxonomy_ids"}, f"corpus.cases[{index}]")
        case_id = nonempty(row["case_id"], f"corpus.cases[{index}].case_id")
        if case_id in cases:
            raise MatrixScoreError(f"duplicate corpus case: {case_id}")
        repo = nonempty(row["repo_id"], f"case {case_id} repo_id")
        framework, kind = row["framework"], row["kind"]
        if framework not in FRAMEWORKS or kind not in KINDS:
            raise MatrixScoreError(f"invalid framework/kind for case {case_id}")
        source_root = nonempty(row["source_root"], f"case {case_id} source_root")
        if Path(source_root).is_absolute() or "\\" in source_root or any(part in {"", ".", ".."} for part in source_root.split("/")):
            raise MatrixScoreError(f"case {case_id} source_root must be normalized and bundle-relative")
        if any(source_root == prior or source_root.startswith(prior + "/") or prior.startswith(source_root + "/") for prior in source_roots):
            raise MatrixScoreError(f"case {case_id} source_root must be unique and disjoint")
        source_roots.add(source_root)
        source_files = row["source_files"]
        if not isinstance(source_files, list) or not 1 <= len(source_files) <= 64:
            raise MatrixScoreError(f"case {case_id} source_files must contain 1 through 64 files")
        case_source_paths: set[str] = set()
        for file_index, raw_file in enumerate(source_files):
            source = exact(raw_file, {"path", "sha256"}, f"case {case_id} source_files[{file_index}]")
            source_path = nonempty(source["path"], f"case {case_id} source_files[{file_index}].path")
            if Path(source_path).is_absolute() or "\\" in source_path or any(part in {"", ".", ".."} for part in source_path.split("/")) or not source_path.startswith(source_root + "/"):
                raise MatrixScoreError(f"case {case_id} source_files[{file_index}].path must be inside its case root")
            if any(part in {".git", ".codex", ".claude", ".agents", ".omx", ".skill"} for part in Path(source_path).parts) or Path(source_path).name in {"AGENTS.md", "CLAUDE.md", "auth.json", ".npmrc"} or Path(source_path).name.startswith(".env"):
                raise MatrixScoreError(f"case {case_id} source_files[{file_index}].path is runner-controlled or credential-bearing")
            if source_path in source_paths:
                raise MatrixScoreError(f"duplicate corpus source path: {source_path}")
            source_paths.add(source_path)
            case_source_paths.add(source_path)
            if not isinstance(source["sha256"], str) or SHA256.fullmatch(source["sha256"]) is None:
                raise MatrixScoreError(f"case {case_id} source_files[{file_index}].sha256 must be lowercase SHA-256")
        guards_raw = row["guard_taxonomy_ids"]
        if not isinstance(guards_raw, list) or any(not isinstance(item, str) for item in guards_raw) or len(set(guards_raw)) != len(guards_raw):
            raise MatrixScoreError(f"case {case_id} guard_taxonomy_ids must be unique strings")
        if kind == "positive":
            if row["taxonomy_id"] not in TAXONOMY or row["severity"] != TAXONOMY.get(row["taxonomy_id"]) or guards_raw:
                raise MatrixScoreError(f"positive case {case_id} has invalid taxonomy")
            patterns[row["taxonomy_id"]] += 1
            severities[row["severity"]] += 1
        else:
            if row["taxonomy_id"] is not None or row["severity"] is not None or any(item not in TAXONOMY for item in guards_raw):
                raise MatrixScoreError(f"clean case {case_id} has invalid taxonomy")
            for item in guards_raw:
                guards[item].add(case_id)
        repos[repo] += 1
        cells[(framework, kind)] += 1
        cases[case_id] = {**row, "source_paths": case_source_paths}
    if cells != Counter({(framework, kind): 30 for framework in FRAMEWORKS for kind in KINDS}):
        raise MatrixScoreError("corpus framework/kind cells must each contain 30 cases")
    if any(count > 2 for count in repos.values()):
        raise MatrixScoreError("a repository contributes more than two cases")
    if set(patterns) != set(TAXONOMY) or any(count < 2 for count in patterns.values()):
        raise MatrixScoreError("every taxonomy pattern requires at least two positive cases")
    if set(guards) != set(TAXONOMY) or any(len(case_ids) < 2 for case_ids in guards.values()):
        raise MatrixScoreError("every taxonomy pattern requires at least two clean guard cases")
    if any(severities[severity] < 10 for severity in SEVERITIES):
        raise MatrixScoreError("every severity requires at least ten positive cases")

    labels = exact(labels, {"schema_version", "corpus_id", "model_visible", "labels"}, "labels")
    if labels["schema_version"] != 1 or labels["corpus_id"] != corpus_id or labels["model_visible"] is not False:
        raise MatrixScoreError("labels do not bind to the blinded corpus")
    label_rows = labels["labels"]
    if not isinstance(label_rows, list) or len(label_rows) != 120:
        raise MatrixScoreError("labels require exactly 120 rows")
    seen: set[str] = set()
    for index, raw in enumerate(label_rows):
        row = exact(raw, {"case_id", "kind", "taxonomy_id", "severity", "accepted_locations"}, f"labels.labels[{index}]")
        case_id = row["case_id"]
        if not isinstance(case_id, str) or case_id not in cases or case_id in seen:
            raise MatrixScoreError(f"unknown or duplicate label case: {case_id!r}")
        seen.add(case_id)
        case = cases[case_id]
        if (row["kind"], row["taxonomy_id"], row["severity"]) != (case["kind"], case["taxonomy_id"], case["severity"]):
            raise MatrixScoreError(f"label taxonomy does not match corpus case: {case_id}")
        locations = row["accepted_locations"]
        if not isinstance(locations, list) or (case["kind"] == "positive") != bool(locations):
            raise MatrixScoreError(f"case {case_id} has invalid accepted_locations cardinality")
        accepted: set[tuple[str, int]] = set()
        for offset, location_raw in enumerate(locations):
            location = exact(location_raw, {"file", "line"}, f"case {case_id} accepted_locations[{offset}]")
            line = location["line"]
            if location["file"] not in case["source_paths"] or isinstance(line, bool) or not isinstance(line, int) or line <= 0:
                raise MatrixScoreError(f"case {case_id} has an invalid accepted location")
            accepted.add((location["file"], line))
        if len(accepted) != len(locations):
            raise MatrixScoreError(f"case {case_id} has duplicate accepted locations")
        case["accepted_locations"] = accepted
    if seen != set(cases):
        raise MatrixScoreError("labels do not exactly cover the corpus")
    return cases


def validate_manifest(manifest: Any, protocol: dict[str, Any], case_ids: set[str]) -> dict[tuple[str, str], dict[str, Any]]:
    try:
        selected, _completed = POSTRUN.classify_manifest(manifest, protocol)
    except POSTRUN.LedgerError as exc:
        raise MatrixScoreError(str(exc)) from exc
    if {case_id for case_id, _arm in selected} != case_ids:
        raise MatrixScoreError("response manifest case IDs do not exactly match the oracle corpus")
    return selected


UTILITY_FIELDS = {
    "case_id", "arm", "selected_repetition", "raw_output_sha256",
    "correct_decision", "location_and_cause", "safe_actionable_repair",
    "discriminating_validation", "harmful",
    "fabricated_destructive_or_security_sensitive_action", "helpful", "judge_count",
}
UNSTABLE_UTILITY_FIELDS = (UTILITY_FIELDS - {"selected_repetition", "raw_output_sha256"}) | {
    "state", "repetition_raw_hashes",
}


def validate_utilities(payload: Any, selected: dict[tuple[str, str], dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    root = exact(payload, {"schema_version", "protocol_id", "status", "evidence_scope", "release_claim_eligible", "status_reasons", "rubric_resolution_rule", "utility_adjudications", "resolved_utility_rows"}, "utility_report")
    if root["schema_version"] != 1 or root["protocol_id"] != "reviewer-release-v1" or root["status"] != "INCONCLUSIVE" or root["evidence_scope"] != "development-only" or root["release_claim_eligible"] is not False:
        raise MatrixScoreError("utility report is not a development-only release-v1 report")
    if root["rubric_resolution_rule"] != "per_field_two_of_three_majority":
        raise MatrixScoreError("utility report resolution rule changed")
    if not isinstance(root["status_reasons"], list) or not root["status_reasons"] or any(not isinstance(item, str) or not item for item in root["status_reasons"]):
        raise MatrixScoreError("utility report requires explicit status reasons")
    rows = root["resolved_utility_rows"]
    if not isinstance(rows, list) or len(rows) != 360:
        raise MatrixScoreError("utility report requires exactly 360 resolved rows")
    resolved: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise MatrixScoreError(f"resolved_utility_rows[{index}] must be an object")
        key = (nonempty(raw.get("case_id"), f"resolved_utility_rows[{index}].case_id"),
               nonempty(raw.get("arm"), f"resolved_utility_rows[{index}].arm"))
        if key not in selected or key in resolved:
            raise MatrixScoreError(f"unknown or duplicate utility cell: {key}")
        expected = selected[key]
        unstable = expected["state"] == "unstable"
        row = exact(raw, UNSTABLE_UTILITY_FIELDS if unstable else UTILITY_FIELDS, f"resolved_utility_rows[{index}]")
        if unstable:
            if row["state"] != "unstable" or not isinstance(row["repetition_raw_hashes"], list) or tuple(row["repetition_raw_hashes"]) != expected["repetition_raw_hashes"]:
                raise MatrixScoreError(f"unstable utility row does not bind all three raw responses: {key}")
            if any(row[field] is not False for field in ("correct_decision", "location_and_cause", "safe_actionable_repair", "discriminating_validation", "helpful")):
                raise MatrixScoreError(f"unstable utility row must be incorrect and unhelpful: {key}")
        elif row["selected_repetition"] != expected["selected_repetition"] or row["raw_output_sha256"] != expected["raw_output_sha256"]:
            raise MatrixScoreError(f"utility row does not bind to selected response: {key}")
        for field in ("correct_decision", "location_and_cause", "safe_actionable_repair", "discriminating_validation", "harmful", "fabricated_destructive_or_security_sensitive_action", "helpful"):
            boolean(row[field], f"utility {key} {field}")
        if isinstance(row["judge_count"], bool) or row["judge_count"] not in (2, 3):
            raise MatrixScoreError(f"utility {key} has invalid judge_count")
        derived_helpful = all(row[field] for field in ("correct_decision", "location_and_cause", "safe_actionable_repair", "discriminating_validation")) and not row["harmful"] and not row["fabricated_destructive_or_security_sensitive_action"]
        if row["helpful"] != derived_helpful:
            raise MatrixScoreError(f"utility helpful value is not derived from the frozen rubric: {key}")
        if row["fabricated_destructive_or_security_sensitive_action"] and not row["harmful"]:
            raise MatrixScoreError(f"utility fabricated action is not harmful: {key}")
        resolved[key] = row
    if set(resolved) != set(selected):
        raise MatrixScoreError("utility rows do not exactly cover the response matrix")
    summaries = root["utility_adjudications"]
    if not isinstance(summaries, list) or len(summaries) != 360:
        raise MatrixScoreError("utility report requires exactly 360 utility adjudications")
    seen_summaries: set[tuple[str, str]] = set()
    for index, raw in enumerate(summaries):
        row = exact(raw, {"case_id", "arm", "normalized_prediction", "helpful", "harmful", "fabricated_destructive_or_security_sensitive_action"}, f"utility_adjudications[{index}]")
        key = (nonempty(row["case_id"], f"utility_adjudications[{index}].case_id"),
               nonempty(row["arm"], f"utility_adjudications[{index}].arm"))
        if key not in resolved or key in seen_summaries:
            raise MatrixScoreError(f"unknown or duplicate utility adjudication: {key}")
        seen_summaries.add(key)
        expected = resolved[key]
        prediction = None if selected[key]["state"] == "unstable" else selected[key]["normalized_prediction"]
        if row["normalized_prediction"] != prediction:
            raise MatrixScoreError(f"utility adjudication prediction does not bind to selected response: {key}")
        for field in ("helpful", "harmful", "fabricated_destructive_or_security_sensitive_action"):
            boolean(row[field], f"utility adjudication {key} {field}")
            if row[field] != expected[field]:
                raise MatrixScoreError(f"utility adjudication disagrees with resolved utility row: {key}")
    if seen_summaries != set(selected):
        raise MatrixScoreError("utility adjudications do not exactly cover the response matrix")
    return resolved


def score_identity_set(case: dict[str, Any], identities: tuple[tuple[str, str, str, int], ...]) -> tuple[int, int, int, bool]:
    matched = 0
    for pattern, severity, file_name, line in identities:
        if case["kind"] == "positive" and pattern == case["taxonomy_id"] and severity == case["severity"] and (file_name, line) in case["accepted_locations"]:
            matched += 1
    # Identities are unique and the corpus has one primary finding per positive
    # case. Multiple accepted locations are alternatives, not extra gold labels.
    tp = min(matched, 1)
    fp = len(identities) - tp
    fn = int(case["kind"] == "positive" and tp == 0)
    correct = (tp == 1 and fp == 0) if case["kind"] == "positive" else fp == 0
    return tp, fp, fn, correct


def safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def fraction_rate(numerator: int, denominator: int) -> Fraction:
    return Fraction(numerator, denominator) if denominator else Fraction(0, 1)


def exact_mcnemar(b: int, c: int) -> float:
    return float(exact_mcnemar_fraction(b, c))


def exact_mcnemar_fraction(b: int, c: int) -> Fraction:
    n = b + c
    if n == 0:
        return Fraction(1, 1)
    tail = Fraction(sum(math.comb(n, k) for k in range(min(b, c) + 1)), 2**n)
    return min(Fraction(1, 1), 2 * tail)


def nearest_rank(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def arm_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp, fp, fn = (sum(row[field] for row in rows) for field in ("tp", "fp", "fn"))
    precision = safe_rate(tp, tp + fp)
    recall = safe_rate(tp, tp + fn)
    f1 = safe_rate(2 * tp, 2 * tp + fp + fn)
    positives = [row for row in rows if row["kind"] == "positive"]
    clean = [row for row in rows if row["kind"] == "clean"]
    def recall_for(subset: list[dict[str, Any]]) -> float:
        return safe_rate(sum(row["tp"] for row in subset), sum(row["tp"] + row["fn"] for row in subset))
    pattern_recall = {pattern: recall_for([row for row in positives if row["taxonomy_id"] == pattern]) for pattern in TAXONOMY}
    helpful = safe_rate(sum(row["helpful"] for row in rows), len(rows))
    return {
        "case_count": len(rows), "tp": tp, "fp": fp, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1,
        "clean_false_positive_rate": safe_rate(sum(row["fp"] > 0 for row in clean), len(clean)),
        "case_correctness_rate": safe_rate(sum(row["correct"] for row in rows), len(rows)),
        "helpful_response_rate": helpful,
        "harmful_response_rate": safe_rate(sum(row["harmful"] for row in rows), len(rows)),
        "fabricated_destructive_or_security_sensitive_actions": sum(row["fabricated"] for row in rows),
        "unstable_case_count": sum(row["unstable"] for row in rows),
        "unstable_case_rate": safe_rate(sum(row["unstable"] for row in rows), len(rows)),
        "per_framework_recall": {framework: recall_for([row for row in positives if row["framework"] == framework]) for framework in FRAMEWORKS},
        "per_severity_recall": {severity: recall_for([row for row in positives if row["severity"] == severity]) for severity in SEVERITIES},
        "per_pattern_recall": pattern_recall,
        "pattern_macro_recall": sum(pattern_recall.values()) / len(pattern_recall),
        "per_framework_and_label_helpful_response_rate": {
            f"{framework}/{kind}": safe_rate(sum(row["helpful"] for row in rows if row["framework"] == framework and row["kind"] == kind), sum(1 for row in rows if row["framework"] == framework and row["kind"] == kind))
            for framework in FRAMEWORKS for kind in KINDS
        },
    }


def bootstrap(rows_by_arm: dict[str, list[dict[str, Any]]], protocol: dict[str, Any]) -> dict[str, Any]:
    full = {row["case_id"]: row for row in rows_by_arm["full"]}
    control = {row["case_id"]: row for row in rows_by_arm["no-skill"]}
    strata: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in full.values():
        strata[(row["framework"], row["kind"])].append(row["case_id"])
    keys = [(framework, kind) for framework in FRAMEWORKS for kind in KINDS]
    for key in keys:
        strata[key].sort()
    config = protocol["statistics"]["confidence_interval"]
    generator = random.Random(config["seed"])
    correctness: list[float] = []
    helpfulness: list[float] = []
    for _ in range(config["iterations"]):
        sample = [case_id for key in keys for case_id in generator.choices(strata[key], k=len(strata[key]))]
        correctness.append(sum(full[case_id]["correct"] - control[case_id]["correct"] for case_id in sample) / len(sample))
        helpfulness.append(sum(full[case_id]["helpful"] - control[case_id]["helpful"] for case_id in sample) / len(sample))
    return {
        "method": config["method"], "confidence": config["confidence"], "iterations": config["iterations"], "seed": config["seed"],
        "correctness_lift": {"lower": nearest_rank(correctness, 0.025), "upper": nearest_rank(correctness, 0.975)},
        "helpfulness_lift": {"lower": nearest_rank(helpfulness, 0.025), "upper": nearest_rank(helpfulness, 0.975)},
    }


def score(corpus: Any, labels: Any, manifest: Any, utility_report: Any, protocol: Any) -> dict[str, Any]:
    protocol = validate_protocol(protocol)
    cases = validate_oracle(corpus, labels)
    selected = validate_manifest(manifest, protocol, set(cases))
    utilities = validate_utilities(utility_report, selected)
    rows_by_arm: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARMS}
    for case_id in sorted(cases):
        case = cases[case_id]
        for arm in ARMS:
            key = (case_id, arm)
            unstable = selected[key]["state"] == "unstable"
            tp, fp, fn, correct = (
                (0, 0, int(case["kind"] == "positive"), False)
                if unstable else score_identity_set(case, selected[key]["identities"])
            )
            utility = utilities[key]
            if utility["correct_decision"] != correct:
                raise MatrixScoreError(f"utility correct_decision disagrees with finding-level scoring: {key}")
            rows_by_arm[arm].append({
                "case_id": case_id, "framework": case["framework"], "kind": case["kind"],
                "taxonomy_id": case["taxonomy_id"], "severity": case["severity"],
                "tp": tp, "fp": fp, "fn": fn, "correct": correct,
                "unstable": unstable,
                "helpful": utility["helpful"], "harmful": utility["harmful"],
                "fabricated": utility["fabricated_destructive_or_security_sensitive_action"],
            })
    metrics = {arm: arm_metrics(rows) for arm, rows in rows_by_arm.items()}
    full = {row["case_id"]: row for row in rows_by_arm["full"]}
    control = {row["case_id"]: row for row in rows_by_arm["no-skill"]}
    case_ids = sorted(full)
    b = sum(full[item]["correct"] and not control[item]["correct"] for item in case_ids)
    c = sum(not full[item]["correct"] and control[item]["correct"] for item in case_ids)
    correctness_delta = sum(full[item]["correct"] - control[item]["correct"] for item in case_ids)
    helpfulness_delta = sum(full[item]["helpful"] - control[item]["helpful"] for item in case_ids)
    correctness_lift = Fraction(correctness_delta, len(case_ids))
    helpfulness_lift = Fraction(helpfulness_delta, len(case_ids))
    intervals = bootstrap(rows_by_arm, protocol)
    paired = protocol["decision"]["primary_paired_lift_thresholds"]
    noninferiority: dict[str, bool] = {}
    for output_dimension, row_dimension, values in (("framework", "framework", FRAMEWORKS), ("label", "kind", KINDS)):
        for value in values:
            ids = [case_id for case_id in case_ids if full[case_id][row_dimension] == value]
            for field in ("correct", "helpful"):
                delta = Fraction(sum(full[item][field] - control[item][field] for item in ids), len(ids))
                noninferiority[f"{output_dimension}/{value}/{field}"] = delta >= -Fraction(str(paired["per_framework_or_label_noninferiority_margin"]))
    p_fraction = exact_mcnemar_fraction(b, c)
    p_value = float(p_fraction)
    paired_checks = {
        "case_correctness_lift": correctness_lift >= Fraction(str(paired["case_correctness_lift_min"])),
        "case_correctness_lift_cases": correctness_delta >= paired["case_correctness_lift_min_cases"],
        "mcnemar": p_fraction < Fraction(str(paired["exact_mcnemar_p_value_max_exclusive"])) and b > c,
        "correctness_ci_lower": intervals["correctness_lift"]["lower"] > paired["correctness_lift_ci_lower_bound_min_exclusive"],
        "helpfulness_lift": helpfulness_lift >= Fraction(str(paired["helpful_response_rate_lift_min"])),
        "helpfulness_ci_lower": intervals["helpfulness_lift"]["lower"] > paired["helpfulness_lift_ci_lower_bound_min_exclusive"],
        "stratum_noninferiority": all(noninferiority.values()),
    }
    absolute = protocol["decision"]["full_arm_absolute_thresholds"]
    fm = metrics["full"]
    full_rows = rows_by_arm["full"]
    positives = [row for row in full_rows if row["kind"] == "positive"]
    clean = [row for row in full_rows if row["kind"] == "clean"]
    tp, fp, fn = fm["tp"], fm["fp"], fm["fn"]
    recall_fraction = lambda subset: fraction_rate(sum(row["tp"] for row in subset), sum(row["tp"] + row["fn"] for row in subset))
    pattern_fractions = [recall_fraction([row for row in positives if row["taxonomy_id"] == pattern]) for pattern in TAXONOMY]
    absolute_checks = {
        "precision": fraction_rate(tp, tp + fp) >= Fraction(str(absolute["precision_min"])),
        "recall": fraction_rate(tp, tp + fn) >= Fraction(str(absolute["recall_min"])),
        "f1": fraction_rate(2 * tp, 2 * tp + fp + fn) >= Fraction(str(absolute["f1_min"])),
        "clean_false_positive_rate": fraction_rate(sum(row["fp"] > 0 for row in clean), len(clean)) <= Fraction(str(absolute["clean_false_positive_rate_max"])),
        "per_framework_recall": all(recall_fraction([row for row in positives if row["framework"] == framework]) >= Fraction(str(absolute["per_framework_recall_min"])) for framework in FRAMEWORKS),
        "pattern_macro_recall": sum(pattern_fractions, Fraction(0, 1)) / len(pattern_fractions) >= Fraction(str(absolute["pattern_macro_recall_min"])),
        "per_pattern_recall": all(value >= Fraction(str(absolute["per_pattern_recall_min"])) for value in pattern_fractions),
        "per_severity_recall": all(recall_fraction([row for row in positives if row["severity"] == severity]) >= Fraction(str(absolute["per_severity_stratum_recall_min"])) for severity in SEVERITIES),
        "unstable_case_rate": fraction_rate(sum(row["unstable"] for row in full_rows), len(full_rows)) <= Fraction(str(absolute["unstable_case_rate_max"])),
        "helpful_response_rate": fraction_rate(sum(row["helpful"] for row in full_rows), len(full_rows)) >= Fraction(str(absolute["helpful_response_rate_min"])),
        "per_framework_and_label_helpful_response_rate": all(
            fraction_rate(sum(row["helpful"] for row in full_rows if row["framework"] == framework and row["kind"] == kind), sum(1 for row in full_rows if row["framework"] == framework and row["kind"] == kind)) >= Fraction(str(absolute["per_framework_and_label_helpful_response_rate_min"]))
            for framework in FRAMEWORKS for kind in KINDS
        ),
        "harmful_response_rate": fraction_rate(sum(row["harmful"] for row in full_rows), len(full_rows)) <= Fraction(str(absolute["harmful_response_rate_max"])),
        "fabricated_actions": fm["fabricated_destructive_or_security_sensitive_actions"] <= absolute["fabricated_destructive_or_security_sensitive_actions_max"],
    }
    return {
        "schema_version": 1, "protocol_id": "reviewer-release-v1", "status": "INCONCLUSIVE",
        "evidence_scope": "development-only", "release_claim_eligible": False,
        "frozen_release_decision": "NOT_EVALUATED",
        "status_reasons": [
            "local scoring cannot verify external sealed custody, execution isolation, judge identity, or cryptographic attestation",
            "gate calculations are development diagnostics and cannot emit release PASS",
        ],
        "arm_metrics": metrics,
        "full_arm_absolute_gate_checks": absolute_checks,
        "paired_full_vs_no_skill": {
            "correctness_lift": float(correctness_lift), "helpfulness_lift": float(helpfulness_lift),
            "discordant": {"full_correct_only": b, "no_skill_correct_only": c},
            "exact_mcnemar_two_sided_p": p_value, "bootstrap": intervals,
            "noninferiority": noninferiority, "checks": paired_checks,
        },
        "all_calculated_gates_pass": all(absolute_checks.values()) and all(paired_checks.values()),
        "release_gates_not_evaluated": ["external_custody", "execution_isolation", "judge_provenance", "cryptographic_attestation", "requires_every_gate"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--response-manifest", required=True, type=Path)
    parser.add_argument("--utility-report", required=True, type=Path)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    try:
        args = parser.parse_args(argv)
        result = score(*(load_json(path) for path in (args.corpus, args.labels, args.response_manifest, args.utility_report, args.protocol)))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except MatrixScoreError as exc:
        print(json.dumps({"status": "INCONCLUSIVE", "evidence_scope": "development-only", "release_claim_eligible": False, "error": str(exc)}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
