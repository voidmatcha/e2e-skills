#!/usr/bin/env python3
"""Verify the immutable reviewer evidence and re-derive documented aggregates."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "benchmarks/reviewer-holdout-v2"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
SPEC = importlib.util.spec_from_file_location("reviewer_holdout", RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {RUNNER_PATH}")
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)

HISTORICAL_PRIMARY_KEYS = {
    "aggregation_unit",
    "stability",
    "unique",
    "macro_recall",
    "p0_per_label_stability",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def label_counts(corpus: dict) -> tuple[int, int]:
    labels = [label for case in corpus["cases"] for label in case["labels"]]
    return (
        sum(label["kind"] == "finding" for label in labels),
        sum(label["kind"] == "fp_guard" for label in labels),
    )


def equivalent(actual: object, expected: object) -> bool:
    """Compare historical metrics across Python float-summation implementations."""
    if isinstance(actual, float) and isinstance(expected, float):
        return math.isclose(actual, expected, rel_tol=1e-15, abs_tol=1e-15)
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            equivalent(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            equivalent(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def corpus_digest(corpus_path: Path, cases: list[dict], source_root: Path) -> str:
    digest = hashlib.sha256()
    digest.update(corpus_path.read_bytes())
    for case in cases:
        for source in sorted(case["source_files"], key=lambda item: item["source"]):
            digest.update(source["source"].encode())
            digest.update(b"\0")
            digest.update((source_root / source["source"]).read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def r2_cases(current_oracle: dict) -> list[dict]:
    corpus = copy.deepcopy(current_oracle)
    r3_only = {"PW-CONTRACT-005", "PW-CONTRACT-FP-006", "PW-SESSION-003"}
    for case in corpus["cases"]:
        case["labels"] = [
            label
            for label in case["labels"]
            if label["finding_id"] not in r3_only
        ]
    return corpus["cases"]


def recompute_report(report: dict, oracle_cases: list[dict]) -> dict:
    selected_ids = {item["case"] for item in report["schedule"]}
    cases = [case for case in oracle_cases if case["id"] in selected_ids]
    assert selected_ids == {case["id"] for case in cases}
    schedule = RUNNER.build_schedule(
        cases,
        report["repetitions"],
        report["protocol"]["schedule"]["seed"],
    )
    assert report["schedule"] == schedule
    assert report["schedule_sha256"] == RUNNER.canonical_json_sha256(schedule)

    by_id = {case["id"]: case for case in cases}
    assert len(report["runs"]) == len(schedule)
    normalized_runs = []
    for expected, stored in zip(schedule, report["runs"]):
        assert (
            stored["schedule_ordinal"],
            stored["case"],
            stored["repetition"],
        ) == (expected["ordinal"], expected["case"], expected["repetition"])
        assert stored["exit_code"] == 0
        assert stored["error"] is None
        assert (
            stored["workspace_sha256_before"]
            == stored["workspace_sha256_after"]
        )
        findings = RUNNER.parse_findings(stored["output"])
        assert stored["findings"] == findings
        score = RUNNER.score(by_id[stored["case"]], findings)
        assert stored["score"] == score
        normalized_runs.append({**stored, "findings": findings, "score": score})
    totals = {
        name: sum(run["score"][name] for run in normalized_runs)
        for name in ("tp", "fp", "fn")
    }
    summary = {
        **RUNNER.rates(**totals),
        "runs": len(normalized_runs),
        "successful_runs": len(normalized_runs),
        "infrastructure_errors": 0,
    }
    secondary = {"aggregation_unit": "repeated-run", **summary}
    primary = RUNNER.primary_metrics(cases, normalized_runs, report["repetitions"])
    assert equivalent(report["summary"], summary)
    assert equivalent(report["secondary_metrics"], secondary)
    # These v2 reports predate clean-case specificity. Re-derive every metric
    # in their frozen schema without pretending that a newly added runner field
    # was present in the historical evidence.
    assert set(report["primary_metrics"]) == HISTORICAL_PRIMARY_KEYS
    historical_primary = {
        key: primary[key] for key in report["primary_metrics"]
    }
    assert equivalent(report["primary_metrics"], historical_primary)

    status, _ = RUNNER.classify_status(
        primary,
        secondary,
        schedule,
        normalized_runs,
        report["protocol_sha256"],
        report.get("protocol_sha256_after", report["protocol_sha256"]),
        report["skill_sha256"],
        report.get("skill_sha256_after", report["skill_sha256"]),
        report["corpus_sha256"],
        report.get("corpus_sha256_after", report["corpus_sha256"]),
        report["protocol"]["decision"]["thresholds"],
    )
    assert report["status"] == status

    counts: Counter = Counter()
    for run in normalized_runs:
        counts.update(
            {
                (
                    run["case"],
                    finding["pattern_id"],
                    finding["severity"],
                    finding["file"],
                    finding["line"],
                )
                for finding in run["findings"]
            }
        )
    required_hits = math.ceil(report["repetitions"] / 2)
    stable_predictions = {key for key, hits in counts.items() if hits >= required_hits}
    unique = primary["unique"]
    return {
        "status": status,
        "stable": (unique["tp"], unique["fp"], unique["fn"]),
        "repeated": (secondary["tp"], secondary["fp"], secondary["fn"]),
        "stable_f1": unique["f1"],
        "stable_precision": unique["precision"],
        "stable_recall": unique["recall"],
        "stable_predictions": stable_predictions,
    }


def main() -> None:
    manifest = read_json(EVIDENCE / "evidence-manifest.json")
    assert manifest["schema_version"] == 1
    seen: set[str] = set()
    for artifact in manifest["artifacts"]:
        relative = Path(artifact["path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        root_name = artifact.get("root", "evidence")
        assert root_name in {"evidence", "repo"}
        identity = f"{root_name}:{relative.as_posix()}"
        assert identity not in seen
        seen.add(identity)
        path = (ROOT if root_name == "repo" else EVIDENCE) / relative
        assert path.is_file(), path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"], path

    initial_path = EVIDENCE / "oracles/initial-oracle-25.json"
    current_path = EVIDENCE / "oracles/current-oracle-r4-30.json"
    initial_oracle = read_json(initial_path)
    current_oracle = read_json(current_path)
    assert label_counts(initial_oracle) == (25, 28)
    assert label_counts(current_oracle) == (30, 31)

    ledger = read_json(EVIDENCE / "oracle-revisions.json")
    assert ledger["current_revision"] == "r4"
    assert [
        (revision["positive_labels"], revision["false_positive_guards"])
        for revision in ledger["revisions"]
    ] == [(25, 28), (28, 30), (30, 31), (30, 31)]
    assert [revision["output_conditioned"] for revision in ledger["revisions"]] == [
        False,
        True,
        True,
        True,
    ]
    assert ledger["revisions"][0]["aggregate_corpus_sha256"] == corpus_digest(
        initial_path,
        initial_oracle["cases"],
        ROOT / "scripts/evals",
    )
    current_cases = current_oracle["cases"]
    assert ledger["revisions"][3]["aggregate_corpus_sha256"] == corpus_digest(
        current_path,
        current_cases,
        ROOT / "scripts/evals",
    )
    adjudications = read_json(EVIDENCE / "post-run-adjudications.json")
    assert adjudications["performance_claim_status"] == "oracle-invalidated"
    assert adjudications["score_rewritten"] is False
    assert len(adjudications["findings"]) == 4
    assert {
        (item["pattern_id"], item["severity"], item["file"], item["line"])
        for item in adjudications["findings"]
        if item["verdict"] == "CONFIRMED"
    } == {
        ("#4a", "P0", "tests/profile.spec.ts", 19),
        ("#4a", "P0", "tests/account.spec.ts", 24),
        ("#4a", "P0", "tests/account.spec.ts", 35),
        ("#4a", "P0", "tests/account.spec.ts", 36),
    }
    assert adjudications["source_report_sha256"] == hashlib.sha256(
        (EVIDENCE / adjudications["source_report"]).read_bytes()
    ).hexdigest()

    expected = {
        "initial-full-codex.json": (
            initial_oracle["cases"],
            "PASS",
            (25, 0, 0),
            (75, 8, 0),
        ),
        "initial-full-claude.json": (
            initial_oracle["cases"],
            "FAIL",
            (24, 2, 1),
            (73, 5, 2),
        ),
        "catalog-control-codex.json": (
            initial_oracle["cases"],
            "FAIL",
            (24, 13, 1),
            (73, 44, 2),
        ),
        "catalog-control-claude.json": (
            initial_oracle["cases"],
            "FAIL",
            (24, 4, 1),
            (71, 23, 4),
        ),
        "current-public-codex.json": (
            current_oracle["cases"],
            "FAIL",
            (30, 4, 0),
            (86, 14, 4),
        ),
        "output-conditioned-postfix-codex.json": (
            initial_oracle["cases"],
            "PASS",
            (7, 0, 0),
            (21, 0, 0),
        ),
        "output-conditioned-postfix-claude.json": (
            initial_oracle["cases"],
            "PASS",
            (7, 0, 0),
            (21, 0, 0),
        ),
        "output-conditioned-targeted-codex.json": (
            r2_cases(current_oracle),
            "PASS",
            (14, 0, 0),
            (42, 1, 0),
        ),
    }
    recomputed = {}
    for name, (cases, status, stable, repeated) in expected.items():
        report = read_json(EVIDENCE / "reports" / name)
        assert report["complete"] is True
        recomputed[name] = recompute_report(report, cases)
        assert recomputed[name]["status"] == status
        assert recomputed[name]["stable"] == stable
        assert recomputed[name]["repeated"] == repeated

    for host in ("codex", "claude"):
        full = recomputed[f"initial-full-{host}.json"]
        control = recomputed[f"catalog-control-{host}.json"]
        ablation = read_json(EVIDENCE / "reports" / f"ablation-{host}.json")
        assert math.isclose(
            ablation["deltas"]["stable_f1_lift"],
            full["stable_f1"] - control["stable_f1"],
        )
        assert math.isclose(
            ablation["deltas"]["stable_precision_delta"],
            full["stable_precision"] - control["stable_precision"],
        )
        assert math.isclose(
            ablation["deltas"]["stable_recall_delta"],
            full["stable_recall"] - control["stable_recall"],
        )
        expected_status = (
            "PASS"
            if all(
                ablation["deltas"][metric.removesuffix("_min")]
                >= threshold
                for metric, threshold in ablation["thresholds"].items()
            )
            else "FAIL"
        )
        assert ablation["status"] == expected_status

    codex = recomputed["initial-full-codex.json"]
    claude = recomputed["initial-full-claude.json"]
    cross_host = read_json(EVIDENCE / "reports/initial-cross-host.json")
    intersection = codex["stable_predictions"] & claude["stable_predictions"]
    union = codex["stable_predictions"] | claude["stable_predictions"]
    assert math.isclose(
        cross_host["metrics"]["stable_recall_gap"],
        abs(codex["stable_recall"] - claude["stable_recall"]),
    )
    assert cross_host["metrics"]["stable_prediction_intersection"] == len(intersection)
    assert cross_host["metrics"]["stable_prediction_union"] == len(union)
    assert math.isclose(
        cross_host["metrics"]["stable_prediction_jaccard"],
        len(intersection) / len(union),
    )
    assert cross_host["status"] == "FAIL"

    print("reviewer evidence: pass (17 artifacts, 8 raw-output reports)")


if __name__ == "__main__":
    main()
