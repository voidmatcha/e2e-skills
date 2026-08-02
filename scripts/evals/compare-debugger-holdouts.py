#!/usr/bin/env python3
"""Re-adjudicate and compare the fixed debugger development benchmark matrix."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-debugger-holdout.py"
DEFAULT_CASES = ROOT / "scripts/evals/debugger-holdout-v1.json"
DEFAULT_PROTOCOL = ROOT / "scripts/evals/debugger-validation-protocol-v1.json"
MAX_REPORT_BYTES = 16_777_216
SHA256_RE = re.compile(r"[0-9a-f]{64}")
REPORT_KEYS = {
    "schema_version",
    "corpus_id",
    "corpus_sha256",
    "protocol_sha256",
    "input_snapshot_manifest",
    "input_post_digests",
    "input_integrity_verified",
    "prompt_skill_sha256",
    "prompt_set_sha256",
    "schedule",
    "schedule_sha256",
    "runner",
    "model",
    "runner_cli_identity",
    "repetitions",
    "execution_complete",
    "infrastructure_errors",
    "status",
    "score",
    "records",
    "limitations",
}
RECORD_KEYS = {
    "ordinal",
    "case_id",
    "repetition",
    "valid",
    "infrastructure_error",
    "prediction",
    "raw_output",
    "raw_output_sha256",
    "raw_output_bytes",
    "error",
    "exit_code",
    "elapsed_ms",
    "workspace_integrity",
}
MANIFEST_KEYS = {
    "source_path",
    "snapshot_path",
    "sha256",
    "source_pre_sha256",
    "snapshot_pre_sha256",
}


def load_runner_module():
    spec = importlib.util.spec_from_file_location(
        "debugger_holdout_runner_for_comparison", RUNNER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load debugger evaluator: {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner_module()


def require_exact_keys(value: object, keys: set[str], context: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        actual = set(value) if isinstance(value, dict) else set()
        raise ValueError(
            f"{context} schema differs: "
            f"missing={sorted(keys - actual)!r}, unknown={sorted(actual - keys)!r}"
        )
    return value


def require_sha256(value: object, context: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def equivalent(left: object, right: object) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        return math.isclose(left, right, rel_tol=1e-15, abs_tol=1e-15)
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            equivalent(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            equivalent(a, b) for a, b in zip(left, right)
        )
    return left == right


def load_report(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path}: report must be a regular non-symlink file")
    payload = path.read_bytes()
    if len(payload) > MAX_REPORT_BYTES:
        raise ValueError(f"{path}: report exceeds {MAX_REPORT_BYTES} bytes")
    try:
        report = RUNNER.strict_loads(payload.decode("utf-8"), str(path))
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"{path}: cannot load strict report JSON: {exc}") from exc
    return validate_report_schema(report, str(path))


def validate_report_schema(report: object, context: str) -> dict:
    report = require_exact_keys(report, REPORT_KEYS, context)
    if report["schema_version"] != 2:
        raise ValueError(f"{context}: expected schema_version 2")
    if not isinstance(report["schedule"], list) or not isinstance(report["records"], list):
        raise ValueError(f"{context}: schedule and records must be arrays")
    if not isinstance(report["infrastructure_errors"], list):
        raise ValueError(f"{context}: infrastructure_errors must be an array")
    for index, record in enumerate(report["records"]):
        require_exact_keys(record, RECORD_KEYS, f"{context}.records[{index}]")
    return report


def expected_sources(corpus: dict) -> dict[str, Path]:
    return {
        "corpus": DEFAULT_CASES,
        "protocol": DEFAULT_PROTOCOL,
        **{
            f"skill:{framework}": path
            for framework, path in RUNNER.FRAMEWORK_SKILLS.items()
        },
        **{
            f"artifact:{case['id']}": DEFAULT_CASES.parent / case["artifact"]["source"]
            for case in corpus["cases"]
        },
    }


def validate_input_provenance(report: dict, corpus: dict) -> None:
    if report["input_integrity_verified"] is not True:
        raise ValueError("input integrity was not verified")
    manifest = report["input_snapshot_manifest"]
    post = report["input_post_digests"]
    sources = expected_sources(corpus)
    if not isinstance(manifest, dict) or set(manifest) != set(sources):
        raise ValueError("input snapshot manifest does not cover the fixed inputs")
    if not isinstance(post, dict) or set(post) != set(sources):
        raise ValueError("input post-digests do not cover the fixed inputs")
    for name, expected_path in sources.items():
        entry = require_exact_keys(manifest[name], MANIFEST_KEYS, f"manifest.{name}")
        post_entry = require_exact_keys(
            post[name], {"source_sha256", "snapshot_sha256"}, f"post.{name}"
        )
        current_path = expected_path.resolve(strict=True)
        if not isinstance(entry["source_path"], str):
            raise ValueError(f"input provenance source path is invalid: {name}")
        if Path(entry["source_path"]) != current_path:
            raise ValueError(f"input provenance source path drift: {name}")
        digest = RUNNER.sha256(current_path)
        require_sha256(entry["sha256"], f"manifest.{name}.sha256")
        if not (
            digest
            == entry["sha256"]
            == entry["source_pre_sha256"]
            == entry["snapshot_pre_sha256"]
            == post_entry["source_sha256"]
            == post_entry["snapshot_sha256"]
        ):
            raise ValueError(f"input provenance digest drift: {name}")
        if not isinstance(entry["snapshot_path"], str) or not Path(
            entry["snapshot_path"]
        ).is_absolute():
            raise ValueError(f"input snapshot path is invalid: {name}")


def reconstruct_records(report: dict, corpus: dict, protocol: dict) -> list[dict]:
    expected_schedule = RUNNER.build_schedule(
        corpus["cases"], protocol["default_repetitions"], protocol["seed"]
    )
    if report["schedule"] != expected_schedule:
        raise ValueError("serialized schedule differs from the fixed schedule")
    if report["schedule_sha256"] != RUNNER.canonical_digest(expected_schedule):
        raise ValueError("schedule digest drift")
    if len(report["records"]) != len(expected_schedule):
        raise ValueError("record count does not match the complete schedule")
    cases_by_id = {case["id"]: case for case in corpus["cases"]}
    reconstructed = []
    for index, (scheduled, record) in enumerate(
        zip(expected_schedule, report["records"])
    ):
        for field in ("ordinal", "case_id", "repetition"):
            if record[field] != scheduled[field]:
                raise ValueError(f"record {index} does not follow the fixed schedule")
        if record["infrastructure_error"]:
            raise ValueError(f"record {index} contains an infrastructure error")
        integrity = require_exact_keys(
            record["workspace_integrity"],
            {"before_sha256", "after_sha256", "verified"},
            f"record {index}.workspace_integrity",
        )
        if (
            integrity["verified"] is not True
            or integrity["before_sha256"] != integrity["after_sha256"]
        ):
            raise ValueError(f"record {index} workspace integrity drift")
        raw_output = record["raw_output"]
        if not isinstance(raw_output, str):
            raise ValueError(f"record {index} raw output must be text")
        raw_bytes = raw_output.encode("utf-8")
        if (
            record["raw_output_bytes"] != len(raw_bytes)
            or record["raw_output_sha256"] != sha256_bytes(raw_bytes)
        ):
            raise ValueError(f"record {index} raw output digest drift")
        try:
            prediction = RUNNER.parse_prediction(raw_output)
            valid = True
        except ValueError:
            prediction = None
            valid = False
        if record["valid"] is not valid:
            raise ValueError(f"record {index} serialized validity drift")
        if valid and not equivalent(record["prediction"], prediction):
            raise ValueError(f"record {index} serialized prediction drift")
        if not valid and record["prediction"] is not None:
            raise ValueError(f"record {index} invalid output carries a prediction")
        rebuilt = {
            **record,
            "valid": valid,
            "prediction": prediction,
            "case": cases_by_id[record["case_id"]],
        }
        reconstructed.append(rebuilt)
    return reconstructed


def validate_report(report: dict, corpus: dict, protocol: dict) -> tuple[dict, dict]:
    validate_report_schema(report, "report")
    if report["corpus_id"] != corpus["corpus_id"]:
        raise ValueError("corpus id drift")
    if report["corpus_sha256"] != RUNNER.sha256(DEFAULT_CASES):
        raise ValueError("corpus provenance drift")
    if report["protocol_sha256"] != RUNNER.sha256(DEFAULT_PROTOCOL):
        raise ValueError("protocol provenance drift")
    if report["repetitions"] != protocol["default_repetitions"]:
        raise ValueError("report does not contain exactly three repetitions")
    if report["execution_complete"] is not True:
        raise ValueError("partial execution is not comparable")
    if report["infrastructure_errors"]:
        raise ValueError("infrastructure errors make the report inconclusive")
    if report["status"] == "INCONCLUSIVE":
        raise ValueError("inconclusive report is not comparable")
    if report["limitations"] != protocol["limitations"]:
        raise ValueError("benchmark limitation disclosure drift")
    validate_input_provenance(report, corpus)
    expected_skill_digests = {
        framework: RUNNER.sha256(path)
        for framework, path in RUNNER.FRAMEWORK_SKILLS.items()
    }
    if report["prompt_skill_sha256"] != expected_skill_digests:
        raise ValueError("prompt skill provenance drift")
    expected_prompt_digest = RUNNER.prompt_set_digest(
        corpus["cases"], DEFAULT_CASES, RUNNER.FRAMEWORK_SKILLS
    )
    if report["prompt_set_sha256"] != expected_prompt_digest:
        raise ValueError("prompt set provenance drift")
    identity = require_exact_keys(
        report["runner_cli_identity"],
        {"path", "sha256", "size_bytes", "version_output"},
        "runner_cli_identity",
    )
    if (
        not isinstance(identity["path"], str)
        or not Path(identity["path"]).is_absolute()
        or not isinstance(identity["size_bytes"], int)
        or identity["size_bytes"] < 1
        or not isinstance(identity["version_output"], str)
        or not identity["version_output"]
    ):
        raise ValueError("runner CLI identity is incomplete")
    require_sha256(identity["sha256"], "runner_cli_identity.sha256")
    reconstructed = reconstruct_records(report, corpus, protocol)
    score = RUNNER.score_predictions(reconstructed)
    if not equivalent(report["score"], score):
        raise ValueError("serialized score drift")
    expected_status = RUNNER.derive_status(True, True, [], score, protocol["thresholds"])
    if report["status"] != expected_status:
        raise ValueError("serialized status drift")
    return score, {"runner": report["runner"], "model": report["model"]}


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def metric_row(score: dict) -> dict[str, float]:
    return {
        "unique_f_code_accuracy": score["unique_cases"]["f_code_accuracy"],
        "unique_macro_precision": score["unique_cases"]["macro_precision"],
        "unique_stable_case_rate": score["unique_cases"]["stable_case_rate"],
        "repeated_f_code_accuracy": score["repeated"]["f_code_accuracy"],
        "repeated_macro_precision": score["repeated"]["macro_precision"],
        "invalid_output_rate": score["invalid_output_rate"],
    }


def average_rows(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        raise ValueError("cannot average an empty metric group")
    return {
        metric: average([row[metric] for row in rows])
        for metric in sorted(rows[0])
    }


def compare_reports(reports: list[dict], corpus: dict, protocol: dict) -> dict:
    expected_matrix = {
        (row["runner"], row["model"]): row["provider_family"]
        for row in protocol["host_matrix"]
    }
    actual_pairs = [(report.get("runner"), report.get("model")) for report in reports]
    if len(reports) != len(expected_matrix) or set(actual_pairs) != set(expected_matrix):
        raise ValueError("reports must contain the fixed host matrix exactly once")
    if len(actual_pairs) != len(set(actual_pairs)):
        raise ValueError("reports must contain the fixed host matrix exactly once")

    host_rows = []
    family_rows: dict[str, list[dict[str, float]]] = defaultdict(list)
    worst_framework = None
    worst_category = None
    for report in reports:
        score, host = validate_report(report, corpus, protocol)
        pair = (host["runner"], host["model"])
        family = expected_matrix[pair]
        metrics = metric_row(score)
        family_rows[family].append(metrics)
        host_rows.append({**host, "provider_family": family, "metrics": metrics})
        framework = {**score["worst_slices"]["framework"], **host}
        category = {**score["worst_slices"]["category"], **host}
        if worst_framework is None or framework["accuracy"] < worst_framework["accuracy"]:
            worst_framework = framework
        if worst_category is None or category["accuracy"] < worst_category["accuracy"]:
            worst_category = category

    by_family = {
        family: average_rows(rows) for family, rows in sorted(family_rows.items())
    }
    balanced = average_rows(list(by_family.values()))
    return {
        "schema_version": 1,
        "status": "VALID_DEVELOPMENT_COMPARISON",
        "evidence_scope": protocol["evidence_scope"],
        "release_eligible": False,
        "raw_outputs_reparsed": True,
        "schedule_and_scores_rederived": True,
        "matrix": {
            "host_count": len(host_rows),
            "provider_family_count": len(by_family),
            "hosts": sorted(host_rows, key=lambda row: (row["runner"], row["model"])),
        },
        "provider_family_metrics": by_family,
        "provider_family_balanced": balanced,
        "worst_slices": {
            "framework": worst_framework,
            "category": worst_category,
        },
        "limitations": protocol["limitations"],
    }


def write_report(path: Path, report: dict) -> None:
    RUNNER.write_report(path, report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if not RUNNER.exact_canonical_path(args.cases, DEFAULT_CASES):
            raise ValueError("comparator accepts only the pinned built-in corpus")
        if not RUNNER.exact_canonical_path(args.protocol, DEFAULT_PROTOCOL):
            raise ValueError("comparator accepts only the pinned built-in protocol")
        corpus = RUNNER.load_corpus(DEFAULT_CASES)
        protocol = RUNNER.load_protocol(DEFAULT_PROTOCOL)
        comparison = compare_reports(
            [load_report(path) for path in args.reports],
            corpus,
            protocol,
        )
        write_report(args.output, comparison)
        return 0
    except (OSError, ValueError) as exc:
        write_report(
            args.output,
            {
                "schema_version": 1,
                "status": "INCONCLUSIVE",
                "release_eligible": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
            },
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
