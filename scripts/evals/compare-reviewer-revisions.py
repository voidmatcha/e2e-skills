#!/usr/bin/env python3
"""Decide a preregistered before/after skill-revision reviewer holdout (v16).

A revision-comparison protocol runs the same corpus, host, prompts, and
schedule under two pinned revisions of the evaluated skill. This script takes
the frozen reports for the protocol's revision/arm cells, re-derives
every report with the holdout comparator's recompute_report against the
revision its skill digest names, and applies the protocol's paired stratified
case bootstrap to the after-minus-before differences. The decision rule and
every constant come from the protocol's revision_comparison block.

Exit status: 0 SUPPORTED, 1 NOT_SUPPORTED, 2 INCONCLUSIVE.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys


ROOT = Path(__file__).resolve().parents[2]
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
REVISIONS = ("before", "after")


def load_comparator_module():
    spec = importlib.util.spec_from_file_location(
        "reviewer_revision_comparator", COMPARATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load comparator module from {COMPARATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMPARATOR = load_comparator_module()
RUNNER = COMPARATOR.RUNNER


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision_contract(protocol: dict) -> dict:
    if protocol.get("protocol_id") not in RUNNER.REVISION_COMPARISON_PROTOCOL_IDS:
        raise ValueError("selected protocol has no frozen revision-comparison contract")
    return protocol["revision_comparison"]


def cells(protocol: dict) -> list[tuple[str, str]]:
    """The (revision, prompt_profile) cells in preregistered execution order."""
    order = sorted(
        revision_contract(protocol)["execution_order"], key=lambda step: step["ordinal"]
    )
    return [(step["revision"], step["prompt_profile"]) for step in order]


def validate_skill_dirs(protocol: dict, skill_dirs: dict[str, Path]) -> None:
    """Each revision's skill directory must hash to its pinned digest."""
    pinned = RUNNER.revision_skill_digests(protocol)
    for revision in REVISIONS:
        actual = RUNNER.skill_digest(skill_dirs[revision])
        if actual != pinned[revision]:
            raise ValueError(
                f"{revision} skill directory digest {actual} does not match the "
                f"pinned {pinned[revision]}"
            )


def validate_cell_report(
    report: dict,
    revision: str,
    prompt_profile: str,
    protocol: dict,
) -> None:
    """Bind one report to its preregistered cell before it is recomputed."""
    pinned = RUNNER.revision_skill_digests(protocol)
    host = protocol["host_matrix"][0]
    if report.get("protocol_id") != protocol["protocol_id"]:
        raise ValueError("report protocol_id does not match the protocol")
    if report.get("skill_sha256") != pinned[revision]:
        raise ValueError(
            f"report skill_sha256 is not the pinned {revision} revision digest"
        )
    if report.get("prompt_profile") != prompt_profile:
        raise ValueError(f"report prompt_profile is not {prompt_profile}")
    if (report.get("runner"), report.get("model")) != (host["runner"], host["model"]):
        raise ValueError("report runner/model is not the preregistered host")


def check_matrix(reports: dict[tuple[str, str], dict], protocol: dict) -> list[dict]:
    """Shared execution identity, order, non-overlap, and elapsed-time limit."""
    contract = revision_contract(protocol)
    reasons: list[dict] = []
    ordered = [reports[cell] for cell in cells(protocol)]
    for field in ("runner_identity", "runner_executable", "reasoning_effort", "git_revision"):
        values = {json.dumps(report.get(field)) for report in ordered}
        if len(values) != 1:
            reasons.append(
                {
                    "code": "revision_matrix_identity_mismatch",
                    "message": f"the reports do not share one {field}",
                }
            )
    if any(report.get("git_dirty") is not False for report in ordered):
        reasons.append(
            {
                "code": "revision_matrix_dirty_checkout",
                "message": "every report must come from a clean runner checkout",
            }
        )
    try:
        starts = [COMPARATOR.report_timestamp(report, "started_at") for report in ordered]
        ends = [COMPARATOR.report_timestamp(report, "created_at") for report in ordered]
    except ValueError as exc:
        return [*reasons, {"code": "revision_matrix_timestamp_invalid", "message": str(exc)}]
    for index, (start, end) in enumerate(zip(starts, ends)):
        if end < start:
            reasons.append(
                {
                    "code": "revision_matrix_timestamp_invalid",
                    "message": f"cell {index + 1} completes before it starts",
                }
            )
        if (
            contract["requires_sequential_non_overlapping_execution"]
            and index
            and start < ends[index - 1]
        ):
            reasons.append(
                {
                    "code": "revision_matrix_order_violation",
                    "message": (
                        f"cell {index + 1} started before cell {index} completed"
                    ),
                }
            )
    elapsed = (ends[-1] - starts[0]).total_seconds()
    if elapsed > contract["maximum_matrix_elapsed_seconds"]:
        reasons.append(
            {
                "code": "revision_matrix_elapsed_exceeded",
                "message": (
                    f"first start to last completion took {elapsed:.0f} s, over "
                    f"{contract['maximum_matrix_elapsed_seconds']} s"
                ),
            }
        )
    return reasons


def arm_metrics(
    report: dict, rows: dict[str, dict], case_ids: list[str]
) -> dict[str, float]:
    return COMPARATOR.provider_weighted_sample_metrics(
        [report],
        {COMPARATOR.report_configuration_key(report): rows},
        case_ids,
        require_both_families=False,
    )


def paired_revision_bootstrap(
    reports: dict[tuple[str, str], dict],
    cases: list[dict],
    protocol: dict,
) -> dict:
    """After-minus-before point deltas and paired case-bootstrap intervals per arm."""
    contract = revision_contract(protocol)
    uncertainty = contract["uncertainty"]
    metrics = uncertainty["metrics"]
    finding_case_ids = [
        case["id"]
        for case in cases
        if any(label["kind"] == "finding" for label in case["labels"])
    ]
    clean_case_ids = [
        case["id"]
        for case in cases
        if {label["kind"] for label in case["labels"]} == {"fp_guard"}
    ]
    if not finding_case_ids or not clean_case_ids:
        raise ValueError("revision bootstrap requires finding and clean case strata")
    all_case_ids = [*finding_case_ids, *clean_case_ids]
    arms = sorted({arm for _, arm in cells(protocol)}, key=["full", "catalog-only"].index)
    rows = {
        cell: COMPARATOR.report_case_metric_rows(report, cases)
        for cell, report in reports.items()
    }
    point = {
        arm: {
            revision: arm_metrics(reports[(revision, arm)], rows[(revision, arm)], all_case_ids)
            for revision in REVISIONS
        }
        for arm in arms
    }
    samples = {arm: {metric: [] for metric in metrics} for arm in arms}
    generator = random.Random(uncertainty["seed"])
    for _ in range(uncertainty["iterations"]):
        sampled = [
            *generator.choices(finding_case_ids, k=len(finding_case_ids)),
            *generator.choices(clean_case_ids, k=len(clean_case_ids)),
        ]
        for arm in arms:
            before = arm_metrics(reports[("before", arm)], rows[("before", arm)], sampled)
            after = arm_metrics(reports[("after", arm)], rows[("after", arm)], sampled)
            for metric in metrics:
                samples[arm][metric].append(after[metric] - before[metric])
    lower_probability = round((1 - uncertainty["confidence"]) / 2, 12)
    upper_probability = round(1 - lower_probability, 12)
    result = {}
    for arm in arms:
        before_guard = reports[("before", arm)]["primary_metrics"]["unique"][
            "stable_guard_hit_rate"
        ]
        after_guard = reports[("after", arm)]["primary_metrics"]["unique"][
            "stable_guard_hit_rate"
        ]
        result[arm] = {
            "before": point[arm]["before"],
            "after": point[arm]["after"],
            "delta": {
                metric: point[arm]["after"][metric] - point[arm]["before"][metric]
                for metric in COMPARATOR.ARM_POINT_METRICS
            },
            "stable_guard_hit_rate": {
                "before": before_guard,
                "after": after_guard,
                "delta": after_guard - before_guard,
            },
            "intervals": {
                metric: {
                    "method": uncertainty["method"],
                    "confidence": uncertainty["confidence"],
                    "iterations": uncertainty["iterations"],
                    "seed": uncertainty["seed"],
                    "strata": uncertainty["strata"],
                    "percentile_method": uncertainty["percentile_method"],
                    "lower": COMPARATOR.nearest_rank(values, lower_probability),
                    "upper": COMPARATOR.nearest_rank(values, upper_probability),
                }
                for metric, values in samples[arm].items()
            },
        }
    return {"arms": result, "interpretation_limit": uncertainty["interpretation_limit"]}


def decide(comparison: dict, protocol: dict) -> tuple[str, list[dict]]:
    """Apply the preregistered SUPPORTED / NOT_SUPPORTED rule to the full arm."""
    decision = revision_contract(protocol)["decision"]
    thresholds = decision["thresholds"]
    primary = comparison["arms"][decision["primary_arm"]]
    metric = decision["primary_metric"]
    exclusive_lower = "stable_f1_delta_ci95_lower_min_exclusive" in thresholds
    lower_key = (
        "stable_f1_delta_ci95_lower_min_exclusive"
        if exclusive_lower else "stable_f1_delta_ci95_lower_min"
    )
    checks = [
        (
            "stable_f1_delta_min",
            primary["delta"][metric],
            thresholds["stable_f1_delta_min"],
            ">=",
        ),
        (
            lower_key,
            primary["intervals"][metric]["lower"],
            thresholds[lower_key],
            ">" if exclusive_lower else ">=",
        ),
        (
            "stable_guard_hit_rate_delta_max",
            primary["stable_guard_hit_rate"]["delta"],
            thresholds["stable_guard_hit_rate_delta_max"],
            "<=",
        ),
    ]
    if "trap_pattern_1_to_2_misclassifications_delta_max" in thresholds:
        checks.append((
            "trap_pattern_1_to_2_misclassifications_delta_max",
            comparison["trap_cases"]["delta"]["pattern_1_to_2_misclassifications"],
            thresholds["trap_pattern_1_to_2_misclassifications_delta_max"],
            "<=",
        ))
    reasons = []
    for name, actual, required, comparator in checks:
        if comparator == ">=":
            passed = actual >= required
        elif comparator == ">":
            passed = actual > required
        else:
            passed = actual <= required
        if not passed:
            reasons.append(
                {
                    "code": f"revision_{name}",
                    "message": (
                        f"{decision['primary_arm']} arm {name}: {actual:.6f} is not "
                        f"{comparator} {required}"
                    ),
                }
            )
    return ("NOT_SUPPORTED" if reasons else "SUPPORTED"), reasons

def descriptive_severity_metrics(report: dict, cases: list[dict]) -> dict:
    """Strict-majority #2 severity and #1/#2 ownership counts, separate from the gate."""
    by_case = {}
    for run in report["runs"]:
        if run["score"] is not None:
            by_case.setdefault(run["case"], []).append(run)
    result = {"pattern_2_labels": 0, "correct_pattern_2_severity": 0,
              "wrong_pattern_2_severity": 0, "pattern_1_to_2_misclassifications": 0,
              "pattern_2_to_1_misclassifications": 0}
    for case in cases:
        runs = by_case.get(case["id"], [])
        if not runs:
            continue
        counts = {}
        for run in runs:
            for finding in run["findings"]:
                key = (finding["pattern_id"], finding["severity"],
                       finding["file"], finding["line"])
                counts[key] = counts.get(key, 0) + 1
        stable = {key for key, count in counts.items() if count > len(runs) // 2}
        for label in case["labels"]:
            if label["kind"] != "finding" or label["pattern_id"] not in {"#1", "#2"}:
                continue
            pattern = label["pattern_id"]
            exact = (pattern, label["severity"], label["file"], label["line"])
            if pattern == "#2":
                result["pattern_2_labels"] += 1
                result["correct_pattern_2_severity"] += exact in stable
                result["wrong_pattern_2_severity"] += any(
                    item[0] == "#2" and item[1] != label["severity"]
                    and item[2:] == exact[2:] for item in stable)
            if exact not in stable and any(
                item[0] == ("#2" if pattern == "#1" else "#1")
                and item[2] == label["file"] for item in stable):
                key = (
                    "pattern_1_to_2_misclassifications" if pattern == "#1"
                    else "pattern_2_to_1_misclassifications"
                )
                result[key] += 1
    result["pattern_2_severity_accuracy"] = (
        result["correct_pattern_2_severity"] / result["pattern_2_labels"]
        if result["pattern_2_labels"] else None)
    return result


def trap_case_metrics(report: dict, trap_cases: list[dict]) -> dict:
    """Count strict-majority #1 title matches and #1→#2 errors on fixed traps."""
    by_case = {}
    for run in report["runs"]:
        if run["score"] is not None:
            by_case.setdefault(run["case"], []).append(run)
    correct = errors = 0
    for case in trap_cases:
        labels = [label for label in case["labels"] if label["kind"] == "finding"]
        if len(labels) != 1 or labels[0]["pattern_id"] != "#1":
            raise ValueError(f"{case['id']}: trap must have exactly one #1 finding")
        runs = by_case.get(case["id"], [])
        counts = {}
        for run in runs:
            for finding in run["findings"]:
                key = (finding["pattern_id"], finding["severity"],
                       finding["file"], finding["line"])
                counts[key] = counts.get(key, 0) + 1
        stable = {key for key, count in counts.items() if count > len(runs) // 2}
        label = labels[0]
        exact = ("#1", label["severity"], label["file"], label["line"])
        if exact in stable:
            correct += 1
        elif any(item[0] == "#2" and item[2] == label["file"] for item in stable):
            errors += 1
    return {
        "cases": len(trap_cases),
        "correct": correct,
        "accuracy": correct / len(trap_cases) if trap_cases else None,
        "pattern_1_to_2_misclassifications": errors,
    }


def compare_revisions(
    report_paths: dict[tuple[str, str], Path],
    cases_path: Path,
    protocol_path: Path,
    skill_dirs: dict[str, Path],
) -> dict:
    protocol_sha256 = sha256_file(protocol_path)
    protocol = RUNNER.load_protocol(protocol_path)
    contract = revision_contract(protocol)
    metadata, all_cases = RUNNER.load_cases(cases_path)
    corpus_sha256 = RUNNER.corpus_digest(cases_path, all_cases)
    RUNNER.validate_corpus_protocol_pairing(metadata, protocol, corpus_sha256)
    validate_skill_dirs(protocol, skill_dirs)
    evaluator_sha256 = RUNNER.evaluator_digest()
    expected_cells = cells(protocol)
    if set(report_paths) != set(expected_cells):
        raise ValueError("exactly one report per preregistered revision and arm is required")
    reasons: list[dict] = []
    recomputed: dict[tuple[str, str], dict] = {}
    report_inputs = []
    for revision, arm in expected_cells:
        path = report_paths[(revision, arm)]
        entry = {
            "revision": revision,
            "prompt_profile": arm,
            "path": RUNNER.portable_host_path(path),
        }
        report_inputs.append(entry)
        try:
            entry["sha256"] = sha256_file(path)
            report = COMPARATOR.load_report(path)
            validate_cell_report(report, revision, arm, protocol)
            report = COMPARATOR.recompute_report(
                report,
                all_cases,
                corpus_sha256,
                protocol,
                protocol_sha256,
                metadata.get("corpus_visibility", "unspecified"),
                "development",
                evaluator_sha256,
                skill_dir=skill_dirs[revision],
            )
            if (
                contract["requires_all_reports_execution_complete"]
                and report["execution_complete"] is not True
            ):
                raise ValueError("report is not execution complete")
            if any(run["score"] is None for run in report["runs"]):
                raise ValueError("report has an unscored run")
            if sha256_file(path) != entry["sha256"]:
                raise ValueError("report changed during comparison")
        except (OSError, KeyError, TypeError, ValueError) as exc:
            reasons.append(
                {
                    "code": "revision_report_invalid",
                    "message": f"{revision} {arm}: {exc}",
                }
            )
            continue
        entry["status"] = report["status"]
        recomputed[(revision, arm)] = report
    comparison = None
    if not reasons:
        reasons.extend(check_matrix(recomputed, protocol))
    if not reasons:
        comparison = paired_revision_bootstrap(recomputed, all_cases, protocol)
        if protocol["protocol_id"] in {"reviewer-holdout-v20", "reviewer-holdout-v21"}:
            comparison["descriptive_severity"] = {
                revision: descriptive_severity_metrics(
                    recomputed[(revision, "full")], all_cases
                )
                for revision in REVISIONS
            }
        if protocol["protocol_id"] == "reviewer-holdout-v21":
            trap_ids = contract["trap_cases"]
            trap_cases = [case for case in all_cases if case["id"] in trap_ids]
            if len(trap_cases) != len(trap_ids):
                raise ValueError("v21 protocol trap case is absent from corpus")
            before = trap_case_metrics(recomputed[("before", "full")], trap_cases)
            after = trap_case_metrics(recomputed[("after", "full")], trap_cases)
            comparison["trap_cases"] = {
                "before": before, "after": after,
                "delta": {"accuracy": after["accuracy"] - before["accuracy"],
                          "pattern_1_to_2_misclassifications":
                          after["pattern_1_to_2_misclassifications"]
                          - before["pattern_1_to_2_misclassifications"]},
            }
        status, reasons = decide(comparison, protocol)
    else:
        status = "INCONCLUSIVE"
    claim_key = {
        "SUPPORTED": "supported",
        "NOT_SUPPORTED": "not_supported",
        "INCONCLUSIVE": "inconclusive",
    }[status]
    return {
        "schema_version": 1,
        "comparison_mode": "skill-revision",
        "status": status,
        "status_reasons": reasons,
        "claim": contract["claim_policy"][claim_key],
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha256,
        "corpus_sha256": corpus_sha256,
        "evaluator_sha256": evaluator_sha256,
        "revision_analysis_sha256": sha256_file(Path(__file__).resolve()),
        "comparator_sha256": sha256_file(COMPARATOR_PATH),
        "revisions": contract["revisions"],
        "report_inputs": report_inputs,
        "decision_rule": contract["decision"],
        "comparison": comparison,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--before-skill-dir", type=Path, required=True)
    parser.add_argument("--after-skill-dir", type=Path, default=RUNNER.DEFAULT_SKILL_DIR)
    parser.add_argument("--before-full", type=Path, required=True)
    parser.add_argument("--after-full", type=Path, required=True)
    parser.add_argument("--before-catalog-only", type=Path)
    parser.add_argument("--after-catalog-only", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report_paths = {
        ("before", "full"): args.before_full,
        ("after", "full"): args.after_full,
    }
    if args.before_catalog_only is not None or args.after_catalog_only is not None:
        if args.before_catalog_only is None or args.after_catalog_only is None:
            parser.error("both catalog-only reports are required together")
        report_paths.update({
            ("before", "catalog-only"): args.before_catalog_only,
            ("after", "catalog-only"): args.after_catalog_only,
        })
    resolved = {cell: path.expanduser().resolve() for cell, path in report_paths.items()}
    output = args.output.expanduser().resolve() if args.output else None
    if output is not None and output in set(resolved.values()):
        parser.error("comparison output must not overwrite an input report")
    try:
        result = compare_revisions(
            resolved,
            args.cases.expanduser().resolve(),
            args.protocol.expanduser().resolve(),
            {
                "before": args.before_skill_dir.expanduser().resolve(),
                "after": args.after_skill_dir.expanduser().resolve(),
            },
        )
    except ValueError as exc:
        parser.error(str(exc))
    if output is not None:
        COMPARATOR.write_json_atomic(output, result)
    print(json.dumps(result, sort_keys=True))
    return {"SUPPORTED": 0, "NOT_SUPPORTED": 1}.get(result["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
