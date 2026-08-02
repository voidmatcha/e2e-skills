#!/usr/bin/env python3
"""Validate the public reviewer/fixture-fault causal benchmark contract."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "scripts/evals/reviewer-fault-causal-v1.json"
PROTOCOL_PATH = (
    ROOT / "scripts/evals/reviewer-validation-protocol-fault-causal-v1.json"
)
OPERATORS_PATH = ROOT / "scripts/evals/run-fixture-faults.py"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"

RUNNER_SPEC = importlib.util.spec_from_file_location(
    "reviewer_fault_causal_runner",
    RUNNER_PATH,
)
if RUNNER_SPEC is None or RUNNER_SPEC.loader is None:
    raise RuntimeError(f"cannot load {RUNNER_PATH}")
RUNNER = importlib.util.module_from_spec(RUNNER_SPEC)
sys.modules[RUNNER_SPEC.name] = RUNNER
RUNNER_SPEC.loader.exec_module(RUNNER)

ROOT_KEYS = {
    "schema_version",
    "corpus_visibility",
    "intended_use",
    "contamination_risk",
    "cases",
}
CASE_KEYS = {"id", "split", "framework", "source_files", "labels"}
SOURCE_KEYS = {"source", "path"}
LABEL_KEYS = {
    "finding_id",
    "kind",
    "pattern_id",
    "severity",
    "file",
    "line",
    "source_line",
}
PROTOCOL_KEYS = {
    "schema_version",
    "protocol_id",
    "schedule",
    "stability",
    "host_matrix",
    "confidence_intervals",
    "decision",
    "cross_host_decision",
}
THRESHOLD_KEYS = {
    "stable_precision_min",
    "stable_recall_min",
    "repeated_precision_min",
    "pattern_macro_recall_min",
    "case_macro_recall_min",
    "framework_macro_recall_min",
    "p0_stable_label_recall_min",
    "stable_guard_hit_rate_max",
}
EXPECTED_OPERATORS = {
    "playwright-error-swallow": ("#3", "playwright"),
    "playwright-locator-truthiness": ("#4f", "playwright"),
    "playwright-conditional-assertion": ("#5a", "playwright"),
    "playwright-discarded-boolean": ("#8b", "playwright"),
    "playwright-aria-snapshot-name": ("#4j", "playwright"),
    "playwright-missing-auth": ("#12", "playwright"),
    "playwright-optimistic-call-proof": ("#22", "playwright"),
    "cypress-missing-then": ("#2", "cypress"),
    "cypress-assigned-chainable": ("#10e", "cypress"),
    "cypress-uncaught-exception": ("#3b", "cypress"),
    "cypress-focused-test-leak": ("#7", "cypress"),
    "cypress-fixture-render-guard": ("#23", "cypress"),
}


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_strict(path: Path) -> dict:
    data = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be an object")
    return data


def require_exact_keys(value: object, expected: set[str], context: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise AssertionError(f"{context}: expected {sorted(expected)}, got {actual}")


def fixture_operators() -> dict[str, tuple[str, str]]:
    tree = ast.parse(OPERATORS_PATH.read_text(encoding="utf-8"))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "OPERATORS"
            for target in node.targets
        )
    )
    assert isinstance(assignment.value, ast.Tuple)
    operators = {}
    for entry in assignment.value.elts:
        assert isinstance(entry, ast.Call)
        assert isinstance(entry.func, ast.Name) and entry.func.id == "Operator"
        fields = {
            keyword.arg: ast.literal_eval(keyword.value)
            for keyword in entry.keywords
            if keyword.arg is not None
        }
        operators[fields["id"]] = (fields["pattern_id"], fields["framework"])
    return operators


def deterministic_schedule(cases: list[dict], repetitions: int, seed: int) -> list:
    unordered = [
        (case["id"], repetition)
        for case in cases
        for repetition in range(1, repetitions + 1)
    ]
    return sorted(
        unordered,
        key=lambda item: (
            hashlib.sha256(f"{seed}\0{item[0]}\0{item[1]}".encode()).hexdigest(),
            item,
        ),
    )


def validate_corpus() -> list[dict]:
    corpus = load_strict(CASES_PATH)
    require_exact_keys(corpus, ROOT_KEYS, "corpus")
    assert corpus["schema_version"] == 1
    assert corpus["corpus_visibility"] == "public"
    intended_use = corpus["intended_use"].casefold()
    contamination_risk = corpus["contamination_risk"].casefold()
    assert "causal reviewer benchmark" in intended_use
    assert "one-to-one" in intended_use and "run-fixture-faults.py" in intended_use
    assert "not sealed" in intended_use
    assert "public" in contamination_risk
    assert "sealed or hidden" in contamination_risk

    cases = corpus["cases"]
    assert isinstance(cases, list) and len(cases) == 12
    assert len({case["id"] for case in cases}) == 12
    assert {case["id"] for case in cases} == set(EXPECTED_OPERATORS)
    assert {case["framework"] for case in cases} == {"playwright", "cypress"}

    for case in cases:
        require_exact_keys(case, CASE_KEYS, f"case {case.get('id')}")
        case_id = case["id"]
        pattern_id, framework = EXPECTED_OPERATORS[case_id]
        assert case["split"] == "public-fault-causal-v1"
        assert case["framework"] == framework
        assert isinstance(case["source_files"], list) and case["source_files"]

        workspace_files = set()
        for source in case["source_files"]:
            require_exact_keys(source, SOURCE_KEYS, f"{case_id} source")
            assert not PurePosixPath(source["source"]).is_absolute()
            assert ".." not in PurePosixPath(source["source"]).parts
            assert f"/{case_id}/" in f"/{source['source']}"
            source_path = CASES_PATH.parent / source["source"]
            assert source_path.is_file(), source_path
            assert source["path"] not in workspace_files
            workspace_files.add(source["path"])

        findings = []
        guards = []
        for label in case["labels"]:
            require_exact_keys(label, LABEL_KEYS, f"{case_id} label")
            assert label["pattern_id"] == pattern_id
            assert label["file"] in workspace_files
            source = next(
                item for item in case["source_files"] if item["path"] == label["file"]
            )
            source_path = CASES_PATH.parent / source["source"]
            source_lines = source_path.read_text(encoding="utf-8").splitlines()
            assert 1 <= label["line"] <= len(source_lines)
            assert label["source_line"] == source_lines[label["line"] - 1].strip()
            if label["kind"] == "finding":
                findings.append(label)
            elif label["kind"] == "fp_guard":
                guards.append(label)
            else:
                raise AssertionError(f"{case_id}: invalid label kind {label['kind']}")

        assert len(findings) == 1, f"{case_id}: expected exactly one finding"
        assert guards, f"{case_id}: expected at least one exact guard"

    return cases


def validate_protocol(cases: list[dict]) -> None:
    protocol = load_strict(PROTOCOL_PATH)
    require_exact_keys(protocol, PROTOCOL_KEYS, "protocol")
    assert protocol["schema_version"] == 1
    assert protocol["protocol_id"] == "reviewer-fault-causal-v1"

    schedule = protocol["schedule"]
    require_exact_keys(
        schedule,
        {"algorithm", "seed", "default_repetitions", "release_repetitions"},
        "protocol schedule",
    )
    assert schedule["algorithm"] == "sha256-seeded-sort-v1"
    assert schedule["default_repetitions"] == 3
    assert schedule["release_repetitions"] == 3
    first = deterministic_schedule(cases, 3, schedule["seed"])
    second = deterministic_schedule(cases, 3, schedule["seed"])
    assert first == second and len(first) == 36 and len(set(first)) == 36

    assert protocol["stability"] == {"rule": "strict-majority"}
    assert protocol["confidence_intervals"] == {
        "method": "wilson",
        "confidence": 0.95,
        "unit": "unique-label-or-prediction",
    }
    assert len(protocol["host_matrix"]) == 3
    for host in protocol["host_matrix"]:
        require_exact_keys(host, {"runner", "model"}, "host matrix entry")

    decision = protocol["decision"]
    require_exact_keys(decision, {"threshold_basis", "thresholds"}, "decision")
    assert decision["threshold_basis"] == "point-estimate"
    require_exact_keys(decision["thresholds"], THRESHOLD_KEYS, "thresholds")
    assert decision["thresholds"]["repeated_precision_min"] >= 0.9
    assert decision["thresholds"]["p0_stable_label_recall_min"] >= 0.9
    assert decision["thresholds"]["framework_macro_recall_min"] >= 0.8

    loaded_protocol = RUNNER.load_protocol(PROTOCOL_PATH)
    assert loaded_protocol["protocol_id"] == "reviewer-fault-causal-v1"
    metadata, loaded_cases = RUNNER.load_cases(CASES_PATH, RUNNER.DEFAULT_SKILL_DIR)
    assert metadata["corpus_visibility"] == "public"
    assert [case["id"] for case in loaded_cases] == [case["id"] for case in cases]
    assert RUNNER.canonical_severities()["#4j"] == "P1"

    pinned = RUNNER.PINNED_LIVE_INPUTS[(CASES_PATH, PROTOCOL_PATH)]
    assert pinned["cases_file_sha256"] == RUNNER.sha256_file(CASES_PATH)
    assert pinned["corpus_sha256"] == RUNNER.corpus_digest(CASES_PATH, loaded_cases)
    assert pinned["protocol_sha256"] == RUNNER.sha256_file(PROTOCOL_PATH)


def main() -> None:
    operators = fixture_operators()
    assert operators == EXPECTED_OPERATORS
    assert operators["playwright-aria-snapshot-name"][0] == "#4j"
    cases = validate_corpus()
    validate_protocol(cases)
    print(
        "reviewer fault-causal benchmark: "
        "12 cases, 12 findings, exact guards, 12 fixture operators, protocol PASS"
    )


if __name__ == "__main__":
    main()
