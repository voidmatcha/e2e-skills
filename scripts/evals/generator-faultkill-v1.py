#!/usr/bin/env python3
"""Score safe Playwright generator plans against fixture-owned fault evidence.

The model surface is a closed declarative DSL. Model output is never interpreted
as JavaScript, Python, a shell command, a path, or an executable template.
"""

from __future__ import annotations

import argparse
import ast
import functools
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CI_LIB = ROOT / "scripts/ci/lib"
if str(CI_LIB) not in sys.path:
    sys.path.insert(0, str(CI_LIB))

from strict_json import load_strict


CORPUS_PATH = ROOT / "scripts/evals/generator-faultkill-v1.json"
SCHEMA_PATH = ROOT / "scripts/evals/generator-faultkill-v1.schema.json"
MANIFEST_PATH = (
    ROOT / "scripts/evals/files/generator-faultkill-v1/manifest.json"
)
OPERATORS_PATH = ROOT / "scripts/evals/run-fixture-faults.py"
RUNTIME_EVIDENCE_PATH = (
    ROOT / "benchmarks/fixture-faults/2026-07-31-current.json"
)

GENERATE_KEYS = {
    "schema_version",
    "case_id",
    "disposition",
    "framework",
    "actions",
    "oracles",
}
CONTROL_KEYS = {
    "schema_version",
    "case_id",
    "disposition",
    "framework",
    "reason_code",
}
ACTION_TOKENS = {
    "navigate-counter",
    "click-increment",
    "set-auth-valid",
    "navigate-account",
    "arm-increment-post-request",
}
ORACLE_TOKENS = {
    "status-count-zero",
    "status-count-one",
    "button-name-increment",
    "account-name-ada-lovelace",
    "increment-post-request-observed",
}
CASE_KEYS = {
    "id",
    "framework",
    "scored",
    "fault_mode",
    "task",
    "expected_disposition",
    "required_actions",
    "required_oracles",
    "linked_operators",
    "compiled_templates",
}
CORPUS_KEYS = {
    "schema_version",
    "corpus_visibility",
    "evaluation_scope",
    "claims_excluded",
    "cases",
}
PREDICTION_BUNDLE_KEYS = {"schema_version", "predictions"}
MANIFEST_KEYS = {"schema_version", "benchmark_id", "scope", "artifacts"}
MANIFEST_ARTIFACT_KEYS = {"path", "role", "sha256"}
RUNTIME_ARCHIVE_KEYS = {
    "schema_version",
    "mode",
    "complete",
    "contracts_valid",
    "runtime_complete",
    "frameworks",
    "output_limit_bytes",
    "process_output_limit_bytes",
    "subprocess_timeout_seconds",
    "provenance",
    "summary",
    "results",
    "errors",
}
RUNTIME_ROW_KEYS = {
    "operator",
    "pattern_id",
    "framework",
    "case",
    "fault_mode",
    "mutation_applied",
    "mutation_sha256",
    "expected",
    "actual",
    "matched",
    "exit_code",
    "infrastructure_timeout",
    "infrastructure_output_overflow",
    "evidence",
    "command",
    "output",
    "output_sha256",
    "output_truncated",
    "output_original_bytes",
    "duration_ms",
}
RUNTIME_PROVENANCE_KEYS = {
    "fixture_tree_sha256",
    "operators_sha256",
    "evaluator_runner_sha256",
    "capture_helper_sha256",
    "package_lock_sha256",
    "python",
    "node",
    "playwright",
    "cypress",
    "platform",
    "machine",
    "selected_package_lock_sha256",
    "selected_node_modules_tree_sha256",
    "selected_playwright_executable_sha256",
    "selected_playwright_package_json_sha256",
    "selected_playwright_lock_record_sha256",
    "selected_playwright_package_version",
    "selected_cypress_executable_sha256",
    "selected_cypress_package_json_sha256",
    "selected_cypress_lock_record_sha256",
    "selected_cypress_package_version",
    "selected_cypress_runtime_cache_key",
    "selected_cypress_runtime_sha256",
}
EXPECTED_RUNTIME_TRIAD = {
    "clean-strong": ("pass", "pass"),
    "fault-strong": ("fail", "fail"),
    "fault-mutant": ("pass", "pass"),
}
FORBIDDEN_TASK_HINTS = {
    "error swallow",
    "locator truthiness",
    "conditional assertion",
    "discarded boolean",
    "missing auth",
    "optimistic call proof",
    "pattern #",
    "mutant",
}


def load_strict_json(path: Path) -> dict[str, Any]:
    value = load_strict(path)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def require_exact_keys(
    value: object,
    expected: set[str],
    context: str,
) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ValueError(
            f"{context}: expected keys {sorted(expected)}, got {actual}"
        )


def require_unique_tokens(
    value: object,
    allowed: set[str],
    context: str,
) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{context}: expected a non-empty array")
    if any(not isinstance(token, str) or token not in allowed for token in value):
        raise ValueError(f"{context}: contains a non-allowlisted token")
    if len(value) != len(set(value)):
        raise ValueError(f"{context}: duplicate tokens are not allowed")
    return value


def validate_schema(schema: dict[str, Any]) -> None:
    require_exact_keys(
        schema,
        {"$schema", "$id", "title", "description", "oneOf"},
        "DSL schema",
    )
    if schema["$schema"] != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("DSL schema must use JSON Schema 2020-12")
    if "never evaluates or executes model-provided source code" not in schema[
        "description"
    ]:
        raise ValueError("DSL schema must state its non-execution boundary")
    branches = schema["oneOf"]
    if not isinstance(branches, list) or len(branches) != 2:
        raise ValueError("DSL schema must define exactly two prediction branches")

    generate, control = branches
    if generate["additionalProperties"] is not False:
        raise ValueError("generate predictions must reject extra properties")
    if control["additionalProperties"] is not False:
        raise ValueError("control predictions must reject extra properties")
    if set(generate["required"]) != GENERATE_KEYS:
        raise ValueError("generate schema keys drifted")
    if set(control["required"]) != CONTROL_KEYS:
        raise ValueError("control schema keys drifted")
    if set(generate["properties"]["actions"]["items"]["enum"]) != ACTION_TOKENS:
        raise ValueError("action token schema drifted")
    if set(generate["properties"]["oracles"]["items"]["enum"]) != ORACLE_TOKENS:
        raise ValueError("oracle token schema drifted")
    if control["properties"]["reason_code"]["const"] != (
        "generator-playwright-only"
    ):
        raise ValueError("Cypress control reason drifted")


def validate_prediction(prediction: dict[str, Any]) -> None:
    if not isinstance(prediction, dict):
        raise ValueError("prediction must be an object")
    disposition = prediction.get("disposition")
    if disposition == "generate":
        require_exact_keys(prediction, GENERATE_KEYS, "generate prediction")
        if prediction["schema_version"] != 1:
            raise ValueError("prediction schema_version must be 1")
        if prediction["framework"] != "playwright":
            raise ValueError("generate disposition is Playwright-only")
        if not re.fullmatch(r"pw-[a-z0-9-]+", prediction["case_id"]):
            raise ValueError("invalid Playwright case_id")
        require_unique_tokens(
            prediction["actions"], ACTION_TOKENS, "prediction actions"
        )
        require_unique_tokens(
            prediction["oracles"], ORACLE_TOKENS, "prediction oracles"
        )
        return
    if disposition == "out_of_scope":
        require_exact_keys(prediction, CONTROL_KEYS, "control prediction")
        if prediction["schema_version"] != 1:
            raise ValueError("prediction schema_version must be 1")
        if prediction["framework"] != "cypress":
            raise ValueError("out_of_scope control must be Cypress")
        if prediction["reason_code"] != "generator-playwright-only":
            raise ValueError("invalid out_of_scope reason")
        if not re.fullmatch(r"cy-[a-z0-9-]+", prediction["case_id"]):
            raise ValueError("invalid Cypress case_id")
        return
    raise ValueError("prediction disposition must be generate or out_of_scope")


def parse_operators() -> dict[str, dict[str, Any]]:
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
    if not isinstance(assignment.value, ast.Tuple):
        raise ValueError("OPERATORS must be a tuple")
    operators: dict[str, dict[str, Any]] = {}
    for entry in assignment.value.elts:
        if not isinstance(entry, ast.Call):
            raise ValueError("operator entry must be a constructor call")
        fields = {
            keyword.arg: ast.literal_eval(keyword.value)
            for keyword in entry.keywords
            if keyword.arg is not None
        }
        operator_id = fields.get("id")
        if not isinstance(operator_id, str) or operator_id in operators:
            raise ValueError("operator ids must be unique strings")
        operators[operator_id] = fields
    return operators


def validate_corpus(corpus: dict[str, Any]) -> None:
    require_exact_keys(corpus, CORPUS_KEYS, "corpus")
    if corpus["schema_version"] != 1:
        raise ValueError("corpus schema_version must be 1")
    if corpus["corpus_visibility"] != "public-development":
        raise ValueError("corpus visibility must remain explicit")
    if "faithful encoding" not in corpus["evaluation_scope"]:
        raise ValueError("evaluation scope must state the measured behavior")
    if "acceptance criteria already stated" not in corpus["evaluation_scope"]:
        raise ValueError("evaluation scope must disclose acceptance-criteria source")
    if (
        "strict declarative" not in corpus["evaluation_scope"]
        or "scenario/oracle DSL" not in corpus["evaluation_scope"]
    ):
        raise ValueError("evaluation scope must identify the DSL boundary")
    if "unrestricted source generation" not in corpus["evaluation_scope"]:
        raise ValueError("evaluation scope must exclude source-generation claims")
    if set(corpus["claims_excluded"]) != {
        "unrestricted model-generated JavaScript execution",
        "sealed or hidden holdout performance",
        "Cypress test generation quality",
        "production application correctness",
    }:
        raise ValueError("excluded claims drifted")

    operators = parse_operators()
    cases = corpus["cases"]
    if not isinstance(cases, list) or len(cases) != 9:
        raise ValueError("corpus must contain four scored and five control cases")
    case_ids: set[str] = set()
    scored_fault_modes: set[str] = set()
    linked_ids: set[str] = set()
    for case in cases:
        require_exact_keys(case, CASE_KEYS, f"case {case.get('id')}")
        case_id = case["id"]
        if not isinstance(case_id, str) or case_id in case_ids:
            raise ValueError("case ids must be unique strings")
        case_ids.add(case_id)
        task = case["task"]
        if not isinstance(task, str) or not task.strip():
            raise ValueError(f"{case_id}: task must be non-empty")
        lowered_task = task.lower()
        leaked = sorted(hint for hint in FORBIDDEN_TASK_HINTS if hint in lowered_task)
        if leaked:
            raise ValueError(f"{case_id}: answer-leading hint(s): {leaked}")
        links = case["linked_operators"]
        if not isinstance(links, list) or not links or len(links) != len(set(links)):
            raise ValueError(f"{case_id}: linked operators must be unique")
        for operator_id in links:
            if operator_id not in operators:
                raise ValueError(f"{case_id}: unknown operator {operator_id}")
            if operator_id in linked_ids:
                raise ValueError(f"{case_id}: duplicate operator linkage {operator_id}")
            linked_ids.add(operator_id)

        if case["scored"] is True:
            if case["framework"] != "playwright":
                raise ValueError(f"{case_id}: only Playwright cases are scored")
            if case["expected_disposition"] != "generate":
                raise ValueError(f"{case_id}: scored case must be generated")
            if case["fault_mode"] in scored_fault_modes:
                raise ValueError(
                    f"{case_id}: primary score duplicates a product fault mode"
                )
            scored_fault_modes.add(case["fault_mode"])
            require_unique_tokens(
                case["required_actions"], ACTION_TOKENS, f"{case_id} actions"
            )
            require_unique_tokens(
                case["required_oracles"], ORACLE_TOKENS, f"{case_id} oracles"
            )
            templates = case["compiled_templates"]
            if not isinstance(templates, list) or len(templates) != len(links):
                raise ValueError(f"{case_id}: template/operator count mismatch")
            for operator_id, relative in zip(links, templates, strict=True):
                path = PurePosixPath(relative)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError(f"{case_id}: unsafe template path")
                expected = (
                    Path("scripts/evals/fixtures")
                    / operators[operator_id]["spec"]
                ).as_posix()
                if relative != expected or not (ROOT / relative).is_file():
                    raise ValueError(f"{case_id}: template linkage drifted")
                if operators[operator_id]["framework"] != "playwright":
                    raise ValueError(f"{case_id}: non-Playwright scored operator")
                if operators[operator_id]["fault_mode"] != case["fault_mode"]:
                    raise ValueError(f"{case_id}: operator fault mode drifted")
        elif case["scored"] is False:
            if case["framework"] != "cypress":
                raise ValueError(f"{case_id}: controls must be Cypress")
            if case["expected_disposition"] != "out_of_scope":
                raise ValueError(f"{case_id}: Cypress control must be out_of_scope")
            if case["fault_mode"] != "control":
                raise ValueError(f"{case_id}: invalid control fault mode")
            if case["required_actions"] or case["required_oracles"]:
                raise ValueError(f"{case_id}: control cannot carry a plan label")
            if case["compiled_templates"]:
                raise ValueError(f"{case_id}: control cannot compile a template")
            if len(links) != 1 or operators[links[0]]["framework"] != "cypress":
                raise ValueError(f"{case_id}: invalid Cypress control linkage")
        else:
            raise ValueError(f"{case_id}: scored must be boolean")

    if scored_fault_modes != {"behavior", "label", "auth", "write"}:
        raise ValueError("scored product fault coverage drifted")
    expected_operators = set(operators)
    if linked_ids != expected_operators:
        raise ValueError(
            "corpus must classify every existing fixture operator exactly once"
        )


def validate_manifest(manifest: dict[str, Any]) -> None:
    require_exact_keys(manifest, MANIFEST_KEYS, "manifest")
    if manifest["schema_version"] != 1:
        raise ValueError("manifest schema_version must be 1")
    if manifest["benchmark_id"] != "generator-faultkill-v1":
        raise ValueError("manifest benchmark_id drifted")
    if manifest["scope"] != "deterministic-scorer-inputs-only":
        raise ValueError("manifest scope drifted")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("manifest artifacts must be non-empty")
    paths: set[str] = set()
    for entry in artifacts:
        require_exact_keys(entry, MANIFEST_ARTIFACT_KEYS, "manifest artifact")
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("manifest artifact path must stay below repository root")
        if entry["path"] in paths:
            raise ValueError("manifest artifact paths must be unique")
        paths.add(entry["path"])
        digest = entry["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("manifest digest must be lowercase sha256")
        path = ROOT / relative
        if not path.is_file():
            raise AssertionError(f"manifest artifact missing: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            raise AssertionError(f"manifest digest mismatch: {relative}")


@functools.lru_cache(maxsize=1)
def expected_runtime_provenance() -> dict[str, str]:
    module_name = "generator_faultkill_fixture_contract"
    spec = importlib.util.spec_from_file_location(module_name, OPERATORS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import fixture runner: {OPERATORS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    dependency, errors = module.full_dependency_provenance(
        module.FIXTURES, ["playwright", "cypress"]
    )
    if errors:
        raise ValueError(f"fixture dependency provenance is invalid: {errors}")
    return {
        "fixture_tree_sha256": module.fixture_tree_sha256(),
        "operators_sha256": module.operators_sha256(),
        "evaluator_runner_sha256": hashlib.sha256(
            OPERATORS_PATH.read_bytes()
        ).hexdigest(),
        "capture_helper_sha256": hashlib.sha256(
            (ROOT / "scripts/evals/bounded_process.py").read_bytes()
        ).hexdigest(),
        "package_lock_sha256": hashlib.sha256(
            (module.FIXTURES / "package-lock.json").read_bytes()
        ).hexdigest(),
        **dependency,
    }


def canonical_runtime_command(
    operator: dict[str, Any],
) -> list[str]:
    spec = f"$FIXTURE_COPY/{operator['spec']}"
    if operator["framework"] == "playwright":
        return [
            "$DEPENDENCY_ROOT/node_modules/.bin/playwright",
            "test",
            spec,
            "--config",
            "$FIXTURE_COPY/playwright/playwright.config.mjs",
        ]
    return [
        "$DEPENDENCY_ROOT/node_modules/.bin/cypress",
        "run",
        "--project",
        "$FIXTURE_COPY/cypress",
        "--spec",
        spec,
        "--browser",
        "electron",
    ]


def validate_runtime_archive(
    evidence: dict[str, Any],
    operators: dict[str, dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    require_exact_keys(evidence, RUNTIME_ARCHIVE_KEYS, "runtime evidence")
    if (
        evidence["schema_version"] != 4
        or evidence["mode"] != "run"
        or evidence["complete"] is not True
        or evidence["contracts_valid"] is not True
        or evidence["runtime_complete"] is not True
        or evidence["frameworks"] != ["playwright", "cypress"]
        or evidence["output_limit_bytes"] != 65_536
        or evidence["process_output_limit_bytes"] != 1_048_576
        or evidence["subprocess_timeout_seconds"] != 120
        or evidence["errors"] != []
    ):
        raise ValueError("runtime evidence is not a complete canonical schema v4 run")
    provenance = evidence["provenance"]
    require_exact_keys(
        provenance, RUNTIME_PROVENANCE_KEYS, "runtime evidence provenance"
    )
    expected_provenance = expected_runtime_provenance()
    for key, expected_value in expected_provenance.items():
        if provenance[key] != expected_value:
            raise ValueError(f"runtime evidence provenance drifted: {key}")
    for key in ("python", "node", "playwright", "cypress", "platform", "machine"):
        if not isinstance(provenance[key], str) or not provenance[key].strip():
            raise ValueError(f"runtime evidence provenance is missing {key}")

    rows = evidence["results"]
    expected_keys = {
        (operator_id, cell)
        for operator_id in operators
        for cell in EXPECTED_RUNTIME_TRIAD
    }
    if not isinstance(rows, list) or len(rows) != len(expected_keys):
        raise ValueError("runtime evidence result cardinality drifted")
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        require_exact_keys(row, RUNTIME_ROW_KEYS, "runtime evidence row")
        key = (row["operator"], row["case"])
        if key in by_key:
            raise ValueError(f"duplicate runtime evidence cell: {key}")
        by_key[key] = row
    if set(by_key) != expected_keys:
        raise ValueError("runtime evidence matrix coverage drifted")

    for (operator_id, cell), row in by_key.items():
        operator = operators[operator_id]
        expected, actual = EXPECTED_RUNTIME_TRIAD[cell]
        if (
            isinstance(row["exit_code"], bool)
            or not isinstance(row["exit_code"], int)
            or not isinstance(row["mutation_applied"], bool)
            or not isinstance(row["infrastructure_timeout"], bool)
            or not isinstance(row["infrastructure_output_overflow"], bool)
            or not isinstance(row["output_truncated"], bool)
            or not isinstance(row["output"], str)
            or not isinstance(row["evidence"], list)
            or any(not isinstance(item, str) for item in row["evidence"])
            or not isinstance(row["command"], list)
            or any(not isinstance(item, str) for item in row["command"])
            or isinstance(row["output_original_bytes"], bool)
            or not isinstance(row["output_original_bytes"], int)
        ):
            raise ValueError(f"invalid runtime row types: {operator_id}/{cell}")
        fault_mode = "none" if cell == "clean-strong" else operator["fault_mode"]
        mutation_applied = cell == "fault-mutant"
        mutation_sha256 = (
            hashlib.sha256(
                f"{operator['marker']}\0{operator['replacement']}".encode()
            ).hexdigest()
            if mutation_applied
            else None
        )
        expected_exit = 0 if expected == "pass" else 1
        output = row["output"]
        marker = (
            operator.get("mutant_pass_marker")
            if mutation_applied and operator.get("mutant_pass_marker")
            else operator["pass_marker"]
        )
        if expected_exit == 1:
            marker = operator["failure_marker"]
        rederived_actual = "pass" if row["exit_code"] == 0 else (
            "fail" if row["exit_code"] == 1 else "error"
        )
        rederived_evidence = (
            [marker]
            if row["exit_code"] in (0, 1) and marker in output
            else [f"missing:{marker}"]
        )
        rederived_matched = (
            row["exit_code"] == expected_exit
            and rederived_evidence == [marker]
        )
        if (
            row["pattern_id"] != operator["pattern_id"]
            or row["framework"] != operator["framework"]
            or row["fault_mode"] != fault_mode
            or row["mutation_applied"] is not mutation_applied
            or row["mutation_sha256"] != mutation_sha256
            or row["expected"] != expected
            or row["actual"] != actual
            or row["actual"] != rederived_actual
            or row["matched"] is not True
            or row["matched"] is not rederived_matched
            or row["infrastructure_timeout"] is not False
            or row["infrastructure_output_overflow"] is not False
            or row["evidence"] != rederived_evidence
            or row["command"] != canonical_runtime_command(operator)
            or not isinstance(output, str)
            or row["output_sha256"]
            != hashlib.sha256(output.encode("utf-8")).hexdigest()
            or row["output_truncated"] is not False
            or row["output_original_bytes"] != len(output.encode("utf-8"))
            or isinstance(row["duration_ms"], bool)
            or not isinstance(row["duration_ms"], int)
            or row["duration_ms"] < 0
        ):
            raise ValueError(f"invalid runtime evidence: {operator_id}/{cell}")

    summary = evidence["summary"]
    require_exact_keys(
        summary,
        {
            "operators",
            "unique_pattern_ids",
            "expected_matrix_cases",
            "matrix_cases",
            "matched",
            "errors",
        },
        "runtime evidence summary",
    )
    if summary != {
        "operators": len(operators),
        "unique_pattern_ids": len(
            {operator["pattern_id"] for operator in operators.values()}
        ),
        "expected_matrix_cases": len(expected_keys),
        "matrix_cases": len(expected_keys),
        "matched": len(expected_keys),
        "errors": 0,
    }:
        raise ValueError("runtime evidence summary drifted")
    return by_key


def load_runtime_triads(
    evidence: dict[str, Any],
    operators: dict[str, dict[str, Any]],
    operator_ids: set[str],
) -> dict[str, dict[str, str]]:
    by_key = validate_runtime_archive(evidence, operators)
    result: dict[str, dict[str, str]] = {}
    for operator_id in operator_ids:
        triad: dict[str, str] = {}
        for cell, (expected, actual) in EXPECTED_RUNTIME_TRIAD.items():
            row = by_key.get((operator_id, cell))
            if not row:
                raise ValueError(f"missing runtime evidence: {operator_id}/{cell}")
            operator = operators[operator_id]
            if row["framework"] != "playwright" or row["actual"] != actual:
                raise ValueError(f"invalid scored runtime evidence: {operator_id}/{cell}")
            triad[cell] = actual
        result[operator_id] = triad
    return result


def compile_plan(
    case: dict[str, Any],
    prediction: dict[str, Any],
) -> list[str]:
    """Map an exact allowlisted plan to existing fixture templates."""
    if prediction["disposition"] != "generate":
        return []
    if prediction["actions"] != case["required_actions"]:
        return []
    if set(prediction["oracles"]) != set(case["required_oracles"]):
        return []
    if len(prediction["oracles"]) != len(case["required_oracles"]):
        return []
    return list(case["compiled_templates"])


def score_predictions(
    corpus: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    validate_schema(load_strict_json(SCHEMA_PATH))
    validate_corpus(corpus)
    validate_manifest(load_strict_json(MANIFEST_PATH))
    require_exact_keys(bundle, PREDICTION_BUNDLE_KEYS, "prediction bundle")
    if bundle["schema_version"] != 1:
        raise ValueError("prediction bundle schema_version must be 1")
    predictions = bundle["predictions"]
    if not isinstance(predictions, list):
        raise ValueError("predictions must be an array")
    prediction_by_id: dict[str, dict[str, Any]] = {}
    for prediction in predictions:
        validate_prediction(prediction)
        case_id = prediction["case_id"]
        if case_id in prediction_by_id:
            raise ValueError(f"duplicate prediction: {case_id}")
        prediction_by_id[case_id] = prediction
    cases = corpus["cases"]
    expected_ids = {case["id"] for case in cases}
    if set(prediction_by_id) != expected_ids:
        missing = sorted(expected_ids - set(prediction_by_id))
        extra = sorted(set(prediction_by_id) - expected_ids)
        raise ValueError(f"prediction coverage mismatch: missing={missing}, extra={extra}")

    scored_operator_ids = {
        operator_id
        for case in cases
        if case["scored"]
        for operator_id in case["linked_operators"]
    }
    evidence = load_strict_json(RUNTIME_EVIDENCE_PATH)
    runtime = load_runtime_triads(evidence, parse_operators(), scored_operator_ids)

    results: list[dict[str, Any]] = []
    scored_passed = 0
    controls_passed = 0
    runtime_triads_proven = 0
    fault_mode_scores: dict[str, list[int]] = {}
    for case in cases:
        prediction = prediction_by_id[case["id"]]
        if case["scored"]:
            compiled = compile_plan(case, prediction)
            missing_actions = [
                action
                for action in case["required_actions"]
                if action not in prediction.get("actions", [])
            ]
            missing_oracles = [
                oracle
                for oracle in case["required_oracles"]
                if oracle not in prediction.get("oracles", [])
            ]
            plan_matches = bool(compiled)
            if plan_matches:
                scored_passed += 1
            fault_mode_scores.setdefault(case["fault_mode"], []).append(
                int(plan_matches)
            )
            linked_runtime = [runtime[operator] for operator in case["linked_operators"]]
            runtime_triads_proven += len(linked_runtime)
            results.append(
                {
                    "case_id": case["id"],
                    "framework": "playwright",
                    "fault_mode": case["fault_mode"],
                    "scored": True,
                    "case_score": int(plan_matches),
                    "plan_matches_label": plan_matches,
                    "missing_actions": missing_actions,
                    "missing_oracles": missing_oracles,
                    "compiled_templates": compiled,
                    "linked_operators": case["linked_operators"],
                    "runtime_evidence": {
                        "clean_strong": "pass",
                        "fault_strong": "fail",
                        "fault_weakened_oracle": "pass",
                    },
                }
            )
        else:
            passed = (
                prediction["disposition"] == "out_of_scope"
                and prediction["framework"] == "cypress"
                and prediction["reason_code"] == "generator-playwright-only"
            )
            controls_passed += int(passed)
            results.append(
                {
                    "case_id": case["id"],
                    "framework": "cypress",
                    "scored": False,
                    "control_passed": passed,
                    "linked_operators": case["linked_operators"],
                }
            )

    scored_cases = sum(1 for case in cases if case["scored"])
    controls = len(cases) - scored_cases
    per_fault_mode = {
        fault_mode: sum(scores) / len(scores)
        for fault_mode, scores in sorted(fault_mode_scores.items())
    }
    fault_mode_macro_accuracy = (
        sum(per_fault_mode.values()) / len(per_fault_mode)
    )
    summary = {
        "scored_cases": scored_cases,
        "scored_passed": scored_passed,
        "planning_accuracy": scored_passed / scored_cases,
        "fault_mode_accuracy": per_fault_mode,
        "fault_mode_macro_accuracy": fault_mode_macro_accuracy,
        "worst_case_fault_mode_accuracy": min(per_fault_mode.values()),
        "linked_playwright_operators": len(scored_operator_ids),
        "runtime_triads_proven": runtime_triads_proven,
        "cypress_controls": controls,
        "cypress_controls_passed": controls_passed,
    }
    return {
        "schema_version": 1,
        "benchmark_id": "generator-faultkill-v1",
        "evaluation_scope": corpus["evaluation_scope"],
        "measurement_claim": (
            "Faithful encoding of user-story acceptance criteria into a "
            "closed scenario/oracle DSL; not autonomous oracle discovery."
        ),
        "complete": scored_passed == scored_cases and controls_passed == controls,
        "summary": summary,
        "results": results,
        "limitations": corpus["claims_excluded"],
    }


def build_prompt_bundle(corpus: dict[str, Any]) -> dict[str, Any]:
    """Emit label-free prompts for an external zero-tool model harness."""
    return {
        "schema_version": 1,
        "benchmark_id": "generator-faultkill-v1",
        "instruction": (
            "Return one JSON prediction per case. Use only the allowlisted "
            "declarative tokens in generator-faultkill-v1.schema.json. Do not "
            "return source code, paths, commands, prose, or markdown."
        ),
        "cases": [
            {
                "case_id": case["id"],
                "framework": case["framework"],
                "task": case["task"],
            }
            for case in corpus["cases"]
        ],
    }


def validate_all() -> None:
    schema = load_strict_json(SCHEMA_PATH)
    validate_schema(schema)
    corpus = load_strict_json(CORPUS_PATH)
    validate_corpus(corpus)
    manifest = load_strict_json(MANIFEST_PATH)
    validate_manifest(manifest)
    scored_operator_ids = {
        operator_id
        for case in corpus["cases"]
        if case["scored"]
        for operator_id in case["linked_operators"]
    }
    load_runtime_triads(
        load_strict_json(RUNTIME_EVIDENCE_PATH),
        parse_operators(),
        scored_operator_ids,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate corpus, DSL, provenance, and runtime evidence",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        help="strict JSON prediction bundle to score",
    )
    parser.add_argument(
        "--emit-prompts",
        action="store_true",
        help="emit label-free cases for a separate zero-tool model runner",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if sum(bool(value) for value in (
        args.validate_only,
        args.predictions,
        args.emit_prompts,
    )) != 1:
        raise SystemExit(
            "choose exactly one of --validate-only, --predictions, or --emit-prompts"
        )
    validate_all()
    corpus = load_strict_json(CORPUS_PATH)
    if args.validate_only:
        print("generator-faultkill-v1 validation: PASS")
        return 0
    if args.emit_prompts:
        print(json.dumps(build_prompt_bundle(corpus), indent=2, sort_keys=True))
        return 0
    report = score_predictions(corpus, load_strict_json(args.predictions))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
