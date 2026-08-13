#!/usr/bin/env python3
"""Contract tests for the safe generator planning/oracle benchmark."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/evals/generator-faultkill-v1.py"
CORPUS_PATH = ROOT / "scripts/evals/generator-faultkill-v1.json"
SCHEMA_PATH = ROOT / "scripts/evals/generator-faultkill-v1.schema.json"
MANIFEST_PATH = (
    ROOT / "scripts/evals/files/generator-faultkill-v1/manifest.json"
)
PREDICTIONS_PATH = (
    ROOT / "scripts/evals/files/generator-faultkill-v1/reference-predictions.json"
)

SPEC = importlib.util.spec_from_file_location("generator_faultkill_v1", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_strict_json_rejects(text: str) -> None:
    with tempfile.TemporaryDirectory(prefix="generator-faultkill-json-") as raw:
        path = Path(raw) / "invalid.json"
        path.write_text(text, encoding="utf-8")
        try:
            MODULE.load_strict_json(path)
        except ValueError:
            return
        raise AssertionError(f"strict JSON accepted invalid input: {text!r}")


def test_strict_json_rejects_duplicate_keys() -> None:
    assert_strict_json_rejects('{"schema_version":1,"schema_version":2}')


def test_strict_json_rejects_nan() -> None:
    assert_strict_json_rejects('{"value":NaN}')


def test_strict_json_rejects_infinity() -> None:
    assert_strict_json_rejects('{"value":Infinity}')


def test_strict_json_rejects_utf8_bom() -> None:
    assert_strict_json_rejects('\ufeff{"value":1}')


def test_strict_json_rejects_trailing_data() -> None:
    assert_strict_json_rejects('{"value":1} trailing')


def test_corpus_is_neutral_and_playwright_scoring_is_unique_by_fault() -> None:
    corpus = MODULE.load_strict_json(CORPUS_PATH)
    MODULE.validate_corpus(corpus)
    scored = [case for case in corpus["cases"] if case["scored"]]
    controls = [case for case in corpus["cases"] if not case["scored"]]

    assert [case["framework"] for case in scored] == ["playwright"] * 4
    assert {case["fault_mode"] for case in scored} == {
        "behavior",
        "label",
        "auth",
        "write",
    }
    assert len({case["fault_mode"] for case in scored}) == len(scored)
    assert controls and {case["framework"] for case in controls} == {"cypress"}
    assert all(
        case["expected_disposition"] == "out_of_scope"
        for case in controls
    )

    serialized = CORPUS_PATH.read_text(encoding="utf-8").lower()
    forbidden_hints = (
        "error swallow",
        "locator truthiness",
        "conditional assertion",
        "discarded boolean",
        "missing auth",
        "optimistic call proof",
        "pattern #",
        "mutant",
    )
    assert not any(hint in serialized for hint in forbidden_hints)


def test_schema_rejects_code_and_unknown_dsl_tokens() -> None:
    schema = MODULE.load_strict_json(SCHEMA_PATH)
    MODULE.validate_schema(schema)
    valid = MODULE.load_strict_json(PREDICTIONS_PATH)["predictions"][0]
    MODULE.validate_prediction(valid)

    for bad in (
        {**valid, "javascript": "process.exit(0)"},
        {**valid, "actions": [*valid["actions"], "evaluate-javascript"]},
        {**valid, "oracles": [*valid["oracles"], "run-shell-command"]},
    ):
        try:
            MODULE.validate_prediction(bad)
        except (AssertionError, ValueError):
            pass
        else:
            raise AssertionError(f"unsafe DSL prediction was accepted: {bad}")


def test_reference_predictions_score_all_scored_cases_and_controls() -> None:
    report = MODULE.score_predictions(
        MODULE.load_strict_json(CORPUS_PATH),
        MODULE.load_strict_json(PREDICTIONS_PATH),
    )
    assert report["complete"] is True
    assert report["summary"] == {
        "scored_cases": 4,
        "scored_passed": 4,
        "planning_accuracy": 1.0,
        "fault_mode_accuracy": {
            "auth": 1.0,
            "behavior": 1.0,
            "label": 1.0,
            "write": 1.0,
        },
        "fault_mode_macro_accuracy": 1.0,
        "worst_case_fault_mode_accuracy": 1.0,
        "linked_playwright_operators": 7,
        "runtime_triads_proven": 7,
        "cypress_controls": 5,
        "cypress_controls_passed": 5,
    }
    assert report["measurement_claim"].endswith(
        "not autonomous oracle discovery."
    )
    for result in report["results"]:
        if result["scored"]:
            assert result["case_score"] == 1
            assert result["fault_mode"] in {"behavior", "label", "auth", "write"}
            assert result["plan_matches_label"] is True
            assert result["runtime_evidence"] == {
                "clean_strong": "pass",
                "fault_strong": "fail",
                "fault_weakened_oracle": "pass",
            }
            assert result["compiled_templates"]
            assert all(
                template.startswith("scripts/evals/fixtures/playwright/tests/")
                for template in result["compiled_templates"]
            )
        else:
            assert result["control_passed"] is True


def test_weakened_or_missing_oracle_cannot_receive_credit() -> None:
    corpus = MODULE.load_strict_json(CORPUS_PATH)
    predictions = MODULE.load_strict_json(PREDICTIONS_PATH)
    weakened = json.loads(json.dumps(predictions))
    behavior = next(
        prediction
        for prediction in weakened["predictions"]
        if prediction["case_id"] == "pw-counter-transition"
    )
    behavior["oracles"] = ["status-count-zero"]

    report = MODULE.score_predictions(corpus, weakened)
    result = next(
        result
        for result in report["results"]
        if result["case_id"] == "pw-counter-transition"
    )
    assert result["plan_matches_label"] is False
    assert result["missing_oracles"] == ["status-count-one"]
    assert report["summary"]["scored_passed"] == 3
    assert report["summary"]["fault_mode_macro_accuracy"] == 0.75
    assert report["summary"]["worst_case_fault_mode_accuracy"] == 0.0
    assert report["complete"] is False


def test_runtime_rows_are_reclassified_from_exit_and_output() -> None:
    evidence = MODULE.load_strict_json(MODULE.RUNTIME_EVIDENCE_PATH)
    operators = MODULE.parse_operators()
    scored_operator_ids = {
        operator_id
        for case in MODULE.load_strict_json(CORPUS_PATH)["cases"]
        if case["scored"]
        for operator_id in case["linked_operators"]
    }
    MODULE.load_runtime_triads(evidence, operators, scored_operator_ids)

    for label, mutate in (
        (
            "marker",
            lambda row: (
                row.__setitem__(
                    "output", "completed without the required contract marker"
                ),
                row.__setitem__(
                    "output_sha256",
                    hashlib.sha256(row["output"].encode()).hexdigest(),
                ),
                row.__setitem__(
                    "output_original_bytes", len(row["output"].encode())
                ),
            ),
        ),
        ("exit", lambda row: row.__setitem__("exit_code", 1)),
        ("hash", lambda row: row.__setitem__("output_sha256", "0" * 64)),
    ):
        tampered = json.loads(json.dumps(evidence))
        row = next(
            item
            for item in tampered["results"]
            if item["operator"] in scored_operator_ids
            and item["case"] == "clean-strong"
        )
        mutate(row)
        try:
            MODULE.load_runtime_triads(tampered, operators, scored_operator_ids)
        except ValueError:
            pass
        else:
            raise AssertionError(
                f"stored matched=true bypassed {label} reclassification"
            )


def test_archived_runtime_provenance_does_not_require_live_dependencies() -> None:
    MODULE.expected_runtime_provenance.cache_clear()
    expected = MODULE.expected_runtime_provenance()
    assert set(expected) == {
        "fixture_tree_sha256",
        "operators_sha256",
        "evaluator_runner_sha256",
        "capture_helper_sha256",
        "package_lock_sha256",
        "selected_package_lock_sha256",
    }
    assert expected["selected_package_lock_sha256"] == expected[
        "package_lock_sha256"
    ]


def test_runtime_archive_rejects_schema_state_command_and_provenance_tampering() -> None:
    evidence = MODULE.load_strict_json(MODULE.RUNTIME_EVIDENCE_PATH)
    operators = MODULE.parse_operators()
    mutations = {
        "extra row key": lambda value, row: row.__setitem__("unexpected", True),
        "timeout": lambda value, row: row.__setitem__(
            "infrastructure_timeout", True
        ),
        "overflow": lambda value, row: row.__setitem__(
            "infrastructure_output_overflow", True
        ),
        "truncation": lambda value, row: row.__setitem__(
            "output_truncated", True
        ),
        "non-text output": lambda value, row: row.__setitem__("output", None),
        "runtime timeout contract": lambda value, row: value.__setitem__(
            "subprocess_timeout_seconds", 121
        ),
        "wrong original bytes": lambda value, row: row.__setitem__(
            "output_original_bytes", row["output_original_bytes"] + 1
        ),
        "wrong command": lambda value, row: row.__setitem__(
            "command", ["playwright", "test", "wrong.spec.mjs"]
        ),
        "clean fault mode": lambda value, row: row.__setitem__(
            "fault_mode", "behavior"
        ),
        "clean mutation state": lambda value, row: row.__setitem__(
            "mutation_applied", True
        ),
        "fixture provenance": lambda value, row: value["provenance"].__setitem__(
            "fixture_tree_sha256", "0" * 64
        ),
        "operator provenance": lambda value, row: value["provenance"].__setitem__(
            "operators_sha256", "0" * 64
        ),
        "dependency provenance": lambda value, row: value["provenance"].__setitem__(
            "selected_package_lock_sha256", "0" * 64
        ),
        "archived dependency digest": lambda value, row: value[
            "provenance"
        ].__setitem__("selected_node_modules_tree_sha256", "not-a-digest"),
        "archived dependency version": lambda value, row: value[
            "provenance"
        ].__setitem__("selected_playwright_package_version", ""),
        "archived runtime cache path": lambda value, row: value[
            "provenance"
        ].__setitem__("selected_cypress_runtime_cache_key", "/outside/Cypress"),
    }
    for label, mutate in mutations.items():
        tampered = json.loads(json.dumps(evidence))
        row = next(
            item for item in tampered["results"] if item["case"] == "clean-strong"
        )
        mutate(tampered, row)
        try:
            MODULE.validate_runtime_archive(tampered, operators)
        except ValueError:
            pass
        else:
            raise AssertionError(f"runtime archive accepted {label} tampering")

    mutant = json.loads(json.dumps(evidence))
    row = next(
        item for item in mutant["results"] if item["case"] == "fault-mutant"
    )
    row["mutation_sha256"] = None
    try:
        MODULE.validate_runtime_archive(mutant, operators)
    except ValueError:
        pass
    else:
        raise AssertionError("mutant row accepted a missing mutation digest")


def test_manifest_is_explicitly_scorer_input_scoped_and_detects_tampering() -> None:
    manifest = MODULE.load_strict_json(MANIFEST_PATH)
    MODULE.validate_manifest(manifest)
    assert manifest["scope"] == "deterministic-scorer-inputs-only"
    listed = {entry["path"] for entry in manifest["artifacts"]}
    assert listed == {
        "scripts/evals/generator-faultkill-v1.json",
        "scripts/evals/generator-faultkill-v1.schema.json",
        "scripts/evals/generator-faultkill-v1.py",
        "scripts/evals/files/generator-faultkill-v1/reference-predictions.json",
        "scripts/ci/lib/strict_json.py",
        "scripts/evals/run-fixture-faults.py",
        "benchmarks/fixture-faults/2026-07-31-current.json",
    }
    for entry in manifest["artifacts"]:
        path = ROOT / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]

    with tempfile.TemporaryDirectory(prefix="generator-faultkill-manifest-") as raw:
        copied = Path(raw) / "manifest.json"
        value = json.loads(json.dumps(manifest))
        value["artifacts"][0]["sha256"] = "0" * 64
        copied.write_text(json.dumps(value), encoding="utf-8")
        try:
            MODULE.validate_manifest(MODULE.load_strict_json(copied))
        except AssertionError:
            pass
        else:
            raise AssertionError("tampered manifest digest was accepted")


def test_cli_validate_only_and_reference_scoring() -> None:
    validate = subprocess.run(
        [sys.executable, str(MODULE_PATH), "--validate-only"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert validate.returncode == 0, validate.stderr
    assert "generator-faultkill-v1 validation: PASS" in validate.stdout

    score = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--predictions",
            str(PREDICTIONS_PATH),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert score.returncode == 0, score.stderr
    report = json.loads(score.stdout)
    assert report["summary"]["planning_accuracy"] == 1.0


def main() -> int:
    tests = [
        test_strict_json_rejects_duplicate_keys,
        test_strict_json_rejects_nan,
        test_strict_json_rejects_infinity,
        test_strict_json_rejects_utf8_bom,
        test_strict_json_rejects_trailing_data,
        test_corpus_is_neutral_and_playwright_scoring_is_unique_by_fault,
        test_schema_rejects_code_and_unknown_dsl_tokens,
        test_reference_predictions_score_all_scored_cases_and_controls,
        test_weakened_or_missing_oracle_cannot_receive_credit,
        test_runtime_rows_are_reclassified_from_exit_and_output,
        test_archived_runtime_provenance_does_not_require_live_dependencies,
        test_runtime_archive_rejects_schema_state_command_and_provenance_tampering,
        test_manifest_is_explicitly_scorer_input_scoped_and_detects_tampering,
        test_cli_validate_only_and_reference_scoring,
    ]
    for test in tests:
        test()
    print(f"generator fault-kill v1 tests: PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
