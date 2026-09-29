#!/usr/bin/env python3
"""Compare a preregistered reviewer holdout report matrix across agent hosts."""

from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
sys.path.insert(0, str(ROOT / "scripts/evals"))
from eval_security import descriptor_sha256, replace_atomic_and_sync_parent
from strict_json import StrictJsonError, loads_strict

DEFAULT_CASES = ROOT / "scripts/evals/reviewer-holdout.json"
DEFAULT_PROTOCOL = ROOT / "scripts/evals/reviewer-validation-protocol.json"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("reviewer_holdout_runner", RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load evaluator module from {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_runner_module()
EVALUATOR_SHA256_AT_IMPORT = RUNNER.evaluator_digest()
SHA256_RE = re.compile(r"[0-9a-f]{64}")
MAX_REPORT_BYTES = 8_388_608
MAX_CORPUS_SOURCE_BYTES = 8_388_608
MAX_CORPUS_TOTAL_BYTES = 134_217_728
MAX_CORPUS_FILES = 10_000
MAX_REPORT_DEPTH = 64
MAX_REPORT_NODES = 500_000
MAX_REPORT_STRING_BYTES = 1_048_576
MAX_REPORT_RUNS = 10_000
REPORT_KEYS = {
    "schema_version", "complete", "execution_complete", "status",
    "status_reasons", "evidence_limitations", "runner",
    "runner_identity", "model", "git_revision", "git_dirty", "git_dirty_sha256",
    "evaluator_sha256", "prompt_set_sha256", "prompt_profile", "skill_sha256",
    "snapshot_skill_sha256", "skill_sha256_after",
    "snapshot_skill_sha256_after", "skill_source_path", "corpus_sha256",
    "snapshot_corpus_sha256", "corpus_sha256_after",
    "snapshot_corpus_sha256_after", "corpus_visibility",
    "corpus_intended_use", "corpus_contamination_risk", "protocol_id",
    "protocol_path", "protocol_sha256", "protocol_sha256_after", "protocol",
    "schedule_seed", "schedule_algorithm", "release_repetitions",
    "schedule_sha256", "schedule", "source_read_isolation",
    "external_wrapper", "credential_environment", "model_tool_surface",
    "evidence_scope", "release_eligible", "release_isolation_attestation",
    "input_snapshot", "workspace_integrity", "repetitions",
    "case_scope", "decision_scope", "created_at", "summary",
    "primary_metrics", "secondary_metrics", "by_case", "runs",
}
REPORT_OPTIONAL_KEYS = {
    "runner_executable",
    "reasoning_effort",
    "started_at",
    "execution_identity_policy",
    "execution_identity_match",
    "adjudication_ledger_path",
    "adjudication_ledger_sha256",
    "repository_walk_path",
    "repository_walk_sha256",
    # Only reports under a protocol with a preregistered infrastructure-retry
    # policy carry these; recompute_report refuses them everywhere else.
    "infrastructure_retry",
    "infrastructure_retry_summary",
    # Only reports under a protocol that opted into usage capture carry these;
    # recompute_report refuses them everywhere else.
    "usage_capture",
    "usage_summary",
    # Only reports under a protocol that preregistered output normalization
    # carry these; recompute_report refuses them everywhere else.
    "output_normalization",
    "output_normalization_summary",
    # Only reports under a protocol that preregistered an enforced output
    # schema carry this (the frozen schema and its sha256); recompute_report
    # refuses it everywhere else.
    "output_schema",
}
RUN_KEYS = {
    "schedule_ordinal", "case", "framework", "split", "repetition",
    "exit_code", "duration_ms", "workspace_sha256_before",
    "workspace_sha256_after", "staged_skill_sha256_before",
    "staged_skill_sha256_after", "findings", "score", "output", "error",
    "cleanup_failures",
}
# A retry-policy run additionally records every attempt.
RETRY_RUN_KEYS = RUN_KEYS | {"attempts"}
ATTEMPT_KEYS = {"attempt", "reason", "exit_code", "error"}
# A usage-capture run, and each of its attempts, additionally records usage.
USAGE_KEY = "usage"
# An output-normalization run additionally records whether its answer was
# judged after one whole-answer JSON fence was removed.
NORMALIZED_KEY = "output_normalized"
FINDING_KEYS = {"pattern_id", "severity", "file", "line"}
SCHEDULE_KEYS = {"ordinal", "case", "repetition"}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(json.dumps(payload, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        replace_atomic_and_sync_parent(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_snapshot_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError(f"short write while snapshotting {path}")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def verify_input_digests(captured: dict[Path, str]) -> None:
    for path, expected in captured.items():
        limit = (
            MAX_REPORT_BYTES
            if path.suffix == ".json"
            else MAX_CORPUS_SOURCE_BYTES
        )
        actual, _ = descriptor_sha256(path, limit)
        if actual != expected:
            raise ValueError(f"{path}: input changed during comparison")


def verify_evaluator_digest(expected: str) -> None:
    if RUNNER.evaluator_digest() != expected:
        raise ValueError("the evaluator changed while comparison was running")


def snapshot_corpus_inputs(
    cases_path: Path,
    snapshot_root: Path,
) -> tuple[Path, dict[Path, str]]:
    cases_digest, cases_payload = descriptor_sha256(
        cases_path,
        MAX_REPORT_BYTES,
    )
    validate_raw_json_depth(cases_payload, cases_path)
    try:
        corpus = loads_strict(
            cases_payload.decode("utf-8"),
            context=str(cases_path),
        )
    except (UnicodeError, StrictJsonError) as exc:
        raise ValueError(f"{cases_path}: cannot parse corpus snapshot: {exc}") from exc
    validate_tree_limits(corpus, cases_path)
    if not isinstance(corpus, dict) or not isinstance(corpus.get("cases"), list):
        raise ValueError(f"{cases_path}: corpus must contain a cases array")

    source_names: set[str] = set()
    for case_index, case in enumerate(corpus["cases"]):
        if not isinstance(case, dict) or not isinstance(
            case.get("source_files"),
            list,
        ):
            raise ValueError(
                f"{cases_path}: case {case_index} must contain source_files"
            )
        for source_index, source in enumerate(case["source_files"]):
            if not isinstance(source, dict):
                raise ValueError(
                    f"{cases_path}: case {case_index} source {source_index} "
                    "must be an object"
                )
            source_names.add(
                RUNNER.safe_relative(
                    source.get("source"),
                    f"case {case_index} source {source_index}",
                )
            )
    if len(source_names) > MAX_CORPUS_FILES:
        raise ValueError(
            f"{cases_path}: corpus exceeds {MAX_CORPUS_FILES} source files"
        )

    captured = {cases_path: cases_digest}
    snapshot_cases_path = snapshot_root / cases_path.name
    write_snapshot_file(snapshot_cases_path, cases_payload)
    total_bytes = len(cases_payload)
    for source_name in sorted(source_names):
        source_path = cases_path.parent / source_name
        source_digest, source_payload = descriptor_sha256(
            source_path,
            MAX_CORPUS_SOURCE_BYTES,
        )
        total_bytes += len(source_payload)
        if total_bytes > MAX_CORPUS_TOTAL_BYTES:
            raise ValueError(
                f"{cases_path}: corpus snapshot exceeds "
                f"{MAX_CORPUS_TOTAL_BYTES} bytes"
            )
        captured[source_path] = source_digest
        write_snapshot_file(snapshot_root / source_name, source_payload)
    verify_input_digests(captured)
    return snapshot_cases_path, captured


def finding_key(run: dict, finding: dict) -> tuple[str, str, str, str, int]:
    return (
        run["case"],
        finding["pattern_id"],
        finding["severity"],
        finding["file"],
        finding["line"],
    )


def stable_predictions(report: dict) -> set[tuple[str, str, str, str, int]]:
    required_hits = report["primary_metrics"]["stability"]["required_hits"]
    counts: Counter = Counter()
    for run in report["runs"]:
        if run.get("score") is None:
            continue
        counts.update({finding_key(run, finding) for finding in run["findings"]})
    return {key for key, hits in counts.items() if hits >= required_hits}


def validate_raw_json_depth(payload: bytes, path: Path) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in payload:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x7B, 0x5B):
            depth += 1
            if depth > MAX_REPORT_DEPTH:
                raise ValueError(
                    f"{path}: JSON nesting exceeds {MAX_REPORT_DEPTH}"
                )
        elif byte in (0x7D, 0x5D):
            depth -= 1
            if depth < 0:
                raise ValueError(f"{path}: invalid JSON nesting")


def validate_tree_limits(value: object, path: Path) -> None:
    stack = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_REPORT_NODES:
            raise ValueError(f"{path}: JSON exceeds {MAX_REPORT_NODES} nodes")
        if depth > MAX_REPORT_DEPTH:
            raise ValueError(f"{path}: JSON nesting exceeds {MAX_REPORT_DEPTH}")
        if isinstance(current, str):
            if len(current.encode("utf-8")) > MAX_REPORT_STRING_BYTES:
                raise ValueError(
                    f"{path}: JSON string exceeds {MAX_REPORT_STRING_BYTES} bytes"
                )
        elif isinstance(current, float) and not math.isfinite(current):
            raise ValueError(f"{path}: non-finite JSON number is not allowed")
        elif isinstance(current, dict):
            stack.extend((key, depth + 1) for key in current)
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)


def require_exact_object_keys(
    value: object, expected: set[str], context: str
) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        actual = set(value) if isinstance(value, dict) else set()
        raise ValueError(
            f"{context}: schema keys differ; "
            f"missing={sorted(expected - actual)!r}, "
            f"unknown={sorted(actual - expected)!r}"
        )
    return value


def load_report(path: Path) -> dict:
    try:
        _, payload = descriptor_sha256(path, MAX_REPORT_BYTES)
        validate_raw_json_depth(payload, path)
        text = payload.decode("utf-8")
        report = loads_strict(text, context=str(path))
    except (OSError, UnicodeError, StrictJsonError) as exc:
        raise ValueError(f"{path}: cannot load strict report JSON: {exc}") from exc
    validate_tree_limits(report, path)
    if not isinstance(report, dict):
        raise ValueError(f"{path}: report must be an object")
    actual_report_keys = set(report)
    missing_report_keys = REPORT_KEYS - actual_report_keys
    unknown_report_keys = actual_report_keys - REPORT_KEYS - REPORT_OPTIONAL_KEYS
    if missing_report_keys or unknown_report_keys:
        raise ValueError(
            f"{path}: schema keys differ; "
            f"missing={sorted(missing_report_keys)!r}, "
            f"unknown={sorted(unknown_report_keys)!r}"
        )
    if report["schema_version"] != 2:
        raise ValueError(f"{path}: expected schema_version 2")
    schedule = report["schedule"]
    runs = report["runs"]
    if not isinstance(schedule, list):
        raise ValueError(f"{path}: schedule must be an array")
    if not isinstance(runs, list) or len(runs) > MAX_REPORT_RUNS:
        raise ValueError(
            f"{path}: runs must be an array with at most {MAX_REPORT_RUNS} entries"
        )
    for index, item in enumerate(schedule):
        require_exact_object_keys(item, SCHEDULE_KEYS, f"{path}.schedule[{index}]")
    for index, run in enumerate(runs):
        expected_run_keys = (
            RETRY_RUN_KEYS if isinstance(run, dict) and "attempts" in run else RUN_KEYS
        )
        if isinstance(run, dict) and USAGE_KEY in run:
            expected_run_keys = expected_run_keys | {USAGE_KEY}
        if isinstance(run, dict) and NORMALIZED_KEY in run:
            expected_run_keys = expected_run_keys | {NORMALIZED_KEY}
        if isinstance(run, dict) and "unexpected_stream_item" in run:
            if (report.get("protocol_id") not in {"reviewer-holdout-v19", "reviewer-holdout-v20", "reviewer-holdout-v21"}
                    or run.get("error") != RUNNER.CODEX_STREAM_ERROR
                    or run.get("score") is not None):
                raise ValueError("unexpected stream diagnostic is limited to failed v19/v20/v21 runs")
            names = run["unexpected_stream_item"]
            require_exact_object_keys(
                names, {"event_type", "item_type", "item_kind"},
                f"{path}.runs[{index}].unexpected_stream_item",
            )
            if any(
                value is not None and value != "[invalid type name]"
                and (not isinstance(value, str)
                     or re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) is None)
                for value in names.values()
            ):
                raise ValueError("unexpected stream diagnostic must contain only type names")
            expected_run_keys = expected_run_keys | {"unexpected_stream_item"}
        require_exact_object_keys(
            run,
            expected_run_keys,
            f"{path}.runs[{index}]",
        )
        findings = run["findings"]
        if not isinstance(findings, list):
            raise ValueError(f"{path}.runs[{index}].findings must be an array")
        for finding_index, finding in enumerate(findings):
            require_exact_object_keys(
                finding,
                FINDING_KEYS,
                f"{path}.runs[{index}].findings[{finding_index}]",
            )
    return report


def require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def equivalent(actual: object, expected: object) -> bool:
    """Compare serialized metrics across Python float-summation implementations."""
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


def validate_provenance(
    report: dict,
    comparison_scope: str = "development",
) -> None:
    digest_fields = (
        "skill_sha256",
        "snapshot_skill_sha256",
        "skill_sha256_after",
        "snapshot_skill_sha256_after",
        "corpus_sha256",
        "snapshot_corpus_sha256",
        "corpus_sha256_after",
        "snapshot_corpus_sha256_after",
        "evaluator_sha256",
        "prompt_set_sha256",
        "protocol_sha256",
        "protocol_sha256_after",
        "schedule_sha256",
    )
    for field in digest_fields:
        require_sha256(report.get(field), field)
    if report.get("protocol_id") in RUNNER.ADJUDICATED_SPECIFICITY_PROTOCOL_IDS:
        require_sha256(
            report.get("adjudication_ledger_sha256"),
            "adjudication_ledger_sha256",
        )
        if not isinstance(report.get("adjudication_ledger_path"), str):
            raise ValueError("specificity report is missing its adjudication ledger path")
    if report.get("protocol_id") in {"reviewer-specificity-v3", "reviewer-specificity-v4"}:
        require_sha256(report.get("repository_walk_sha256"), "repository_walk_sha256")
        if not isinstance(report.get("repository_walk_path"), str):
            raise ValueError("specificity-v3 report is missing its repository walk path")
    if report.get("prompt_profile") not in RUNNER.PROMPT_SKILL_PROFILES:
        raise ValueError("prompt_profile is not a declared evaluator arm")
    if "runner_executable" in report:
        executable = report["runner_executable"]
        if (
            not isinstance(executable, str)
            or not executable
            or not Path(executable).is_absolute()
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in executable
            )
        ):
            raise ValueError("runner_executable must be an absolute path string")
    reasoning_effort = report.get("reasoning_effort")
    if reasoning_effort is not None:
        RUNNER.validate_reasoning_effort(report["runner"], reasoning_effort)

    if report["snapshot_skill_sha256"] != report["skill_sha256"]:
        raise ValueError("snapshot_skill_sha256 does not match skill_sha256")
    if report["snapshot_skill_sha256_after"] != report["snapshot_skill_sha256"]:
        raise ValueError("snapshot skill digest changed during execution")
    if report["skill_sha256_after"] != report["skill_sha256"]:
        raise ValueError("source skill digest changed during execution")
    if report["snapshot_corpus_sha256"] != report["corpus_sha256"]:
        raise ValueError("snapshot_corpus_sha256 does not match corpus_sha256")
    if report["snapshot_corpus_sha256_after"] != report["snapshot_corpus_sha256"]:
        raise ValueError("snapshot corpus digest changed during execution")
    if report["corpus_sha256_after"] != report["corpus_sha256"]:
        raise ValueError("source corpus digest changed during execution")

    if report["input_snapshot"] != "copy-once-temp":
        raise ValueError("input_snapshot must be copy-once-temp")
    if report["workspace_integrity"] != "pre-post-sha256":
        raise ValueError("workspace_integrity must be pre-post-sha256")
    visibility = report["corpus_visibility"]
    isolation = report["source_read_isolation"]
    wrapper = report["external_wrapper"]
    valid_wrapper = (
        isinstance(wrapper, dict)
        and isinstance(wrapper.get("path"), str)
        and bool(wrapper["path"])
        and wrapper.get("claim") == "execution-wrapper-only"
        and wrapper.get("isolation_proof") is False
    )
    # The runner permits no-wrapper live runs for its pinned built-in inputs
    # whatever visibility label the corpus carries (v4 "public-pre-publication",
    # v5/v6 "public-development"), so accept exactly those digest pairs rather
    # than only the literal "public" label. External bundles still need a wrapper.
    pinned_built_in_input = any(
        pinned["corpus_sha256"] == report["corpus_sha256"]
        and pinned["protocol_sha256"] == report["protocol_sha256"]
        for pinned in RUNNER.PINNED_LIVE_INPUTS.values()
    )
    if visibility == "public" or pinned_built_in_input:
        if not (
            (isolation == "prompt-complete-zero-tools" and wrapper is None)
            or (isolation == "not-proven" and valid_wrapper)
        ):
            raise ValueError("public corpus has invalid isolation provenance")
    else:
        if isolation != "not-proven":
            raise ValueError("non-public corpus must declare source isolation not-proven")
        if not valid_wrapper:
            raise ValueError("non-public corpus has invalid external-wrapper provenance")
    if report["credential_environment"] not in {
        "not-inherited-by-model-tools",
        "parent-auth-staged-model-tools-disabled",
    }:
        raise ValueError("report does not prove a credential-free model tool environment")
    if report["model_tool_surface"] != "none":
        raise ValueError("release comparison requires a zero-tool model surface")
    if comparison_scope == "development":
        if (
            report["evidence_scope"] != "development"
            or report["release_eligible"] is not False
            or report["release_isolation_attestation"] is not None
        ):
            raise ValueError(
                "development comparison requires development evidence with "
                "release_eligible=false and no release attestation"
            )
        return
    if comparison_scope != "release":
        raise ValueError(f"unsupported comparison scope: {comparison_scope}")
    if (
        report["evidence_scope"] != "release"
        or report["release_eligible"] is not True
        or not isinstance(report["release_isolation_attestation"], dict)
    ):
        raise ValueError(
            "release comparison requires release_eligible=true and a "
            "machine-verifiable isolation attestation"
        )
    raise ValueError(
        "signed isolation attestation verification is not implemented; "
        "release comparison fails closed"
    )


def repeated_summary(runs: list[dict]) -> dict:
    successful = [run for run in runs if run["score"] is not None]
    totals = {
        name: sum(run["score"][name] for run in successful)
        for name in ("tp", "fp", "fn")
    }
    return {
        **RUNNER.rates(**totals),
        "runs": len(runs),
        "successful_runs": len(successful),
        "infrastructure_errors": len(runs) - len(successful),
    }


def provider_family_aggregation(
    reports: list[dict], *, require_both_families: bool = True
) -> dict:
    families: dict[str, list[dict]] = {"openai": [], "anthropic": []}
    for report in reports:
        if report["runner"] == "codex":
            family = "openai"
        elif report["runner"] == "claude":
            family = "anthropic"
        else:
            raise ValueError("unknown runner in provider-family aggregation")
        families[family].append(report)
    if require_both_families and any(not members for members in families.values()):
        raise ValueError("provider-family aggregation requires OpenAI and Anthropic")
    families = {family: members for family, members in families.items() if members}

    family_rows = {}
    for family, members in families.items():
        values = {
            "stable_precision": [
                report["primary_metrics"]["unique"]["precision"]
                for report in members
            ],
            "stable_recall": [
                report["primary_metrics"]["unique"]["recall"]
                for report in members
            ],
            "stable_f1": [
                report["primary_metrics"]["unique"]["f1"]
                for report in members
            ],
            "repeated_precision": [
                report["secondary_metrics"]["precision"]
                for report in members
            ],
            "p0_stable_label_recall": [
                report["primary_metrics"]["p0_per_label_stability"][
                    "stable_label_recall"
                ]
                for report in members
            ],
            "clean_case_specificity": [
                report["primary_metrics"]["clean_case_specificity"]["value"]
                for report in members
            ],
        }
        family_rows[family] = {
            "configuration_count": len(members),
            "configurations": [
                {"runner": report["runner"], "model": report["model"]}
                for report in members
            ],
            "metrics": {
                name: {
                    "value": sum(samples) / len(samples),
                    "configuration_denominator": len(samples),
                }
                for name, samples in values.items()
            },
        }

    metric_names = tuple(next(iter(family_rows.values()))["metrics"])
    return {
        "method": (
            "mean-within-provider-family-then-equal-weight-families"
            if require_both_families
            else "single-host-direct"
        ),
        "provider_family_denominator": len(family_rows),
        "families": family_rows,
        "equal_weighted_metrics": {
            name: {
                "value": sum(
                    family_rows[family]["metrics"][name]["value"]
                    for family in family_rows
                )
                / len(family_rows),
                "provider_family_denominator": len(family_rows),
            }
            for name in metric_names
        },
    }


ARM_POINT_METRICS = (
    "stable_precision",
    "stable_recall",
    "stable_f1",
    "repeated_precision",
    "clean_case_specificity",
)
ARM_BOOTSTRAP_METRICS = (
    "stable_precision",
    "stable_recall",
    "stable_f1",
    "clean_case_specificity",
)


def report_configuration_key(report: dict) -> tuple[str, str, str]:
    return (
        report["prompt_profile"],
        report["runner"],
        report["model"],
    )


def report_timestamp(report: dict, field: str) -> dt.datetime:
    value = report.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty ISO-8601 timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return parsed.astimezone(dt.timezone.utc)


def report_case_metric_rows(report: dict, cases: list[dict]) -> dict[str, dict]:
    if report.get("protocol_id") in RUNNER.REVISED_LABEL_PROTOCOL_IDS:
        return revised_report_case_metric_rows(report, cases)
    predictions = stable_predictions(report)
    rows: dict[str, dict] = {}
    for case in cases:
        case_id = case["id"]
        expected = {
            (
                case_id,
                label["pattern_id"],
                label["severity"],
                label["file"],
                label["line"],
            )
            for label in case["labels"]
            if label["kind"] == "finding"
        }
        predicted = {
            prediction for prediction in predictions if prediction[0] == case_id
        }
        repeated_runs = [
            run for run in report["runs"] if run["case"] == case_id
        ]
        if not repeated_runs or any(run["score"] is None for run in repeated_runs):
            raise ValueError(
                f"{report_configuration_key(report)!r}: incomplete case {case_id}"
            )
        clean = {label["kind"] for label in case["labels"]} == {"fp_guard"}
        rows[case_id] = {
            "stable": {
                "tp": len(predicted & expected),
                "fp": len(predicted - expected),
                "fn": len(expected - predicted),
            },
            "repeated": {
                name: sum(run["score"][name] for run in repeated_runs)
                for name in ("tp", "fp", "fn")
            },
            "clean": clean,
            "clean_without_prediction": clean and not predicted,
        }
    return rows


def revised_report_case_metric_rows(
    report: dict, cases: list[dict]
) -> dict[str, dict]:
    """Per-case bootstrap rows under revised (v8) label semantics."""
    required_hits = report["primary_metrics"]["stability"]["required_hits"]
    outcomes = RUNNER.revised_stable_case_outcomes(
        cases, report["runs"], required_hits
    )
    rows: dict[str, dict] = {}
    for case in cases:
        case_id = case["id"]
        repeated_runs = [
            run for run in report["runs"] if run["case"] == case_id
        ]
        if not repeated_runs or any(run["score"] is None for run in repeated_runs):
            raise ValueError(
                f"{report_configuration_key(report)!r}: incomplete case {case_id}"
            )
        outcome = outcomes[case_id]
        clean = {label["kind"] for label in case["labels"]} == {"fp_guard"}
        rows[case_id] = {
            "stable": {
                "tp": len(outcome["stable_tp"]),
                "fp": len(outcome["stable_fp"]),
                "fn": len(outcome["stable_fn"]),
            },
            "repeated": {
                name: sum(run["score"][name] for run in repeated_runs)
                for name in ("tp", "fp", "fn")
            },
            "clean": clean,
            "clean_without_prediction": (
                clean and not outcome["stable_predictions"]
            ),
        }
    return rows


def provider_weighted_sample_metrics(
    reports: list[dict],
    rows_by_configuration: dict[tuple[str, str, str], dict[str, dict]],
    sampled_case_ids: list[str],
    *,
    require_both_families: bool = True,
) -> dict[str, float]:
    families: dict[str, list[dict[str, float]]] = {
        "openai": [],
        "anthropic": [],
    }
    for report in reports:
        family = (
            "openai"
            if report["runner"] == "codex"
            else "anthropic"
            if report["runner"] == "claude"
            else None
        )
        if family is None:
            raise ValueError("unknown runner in provider-weighted arm metrics")
        rows = rows_by_configuration[report_configuration_key(report)]
        stable_totals = {
            name: sum(rows[case_id]["stable"][name] for case_id in sampled_case_ids)
            for name in ("tp", "fp", "fn")
        }
        repeated_totals = {
            name: sum(
                rows[case_id]["repeated"][name] for case_id in sampled_case_ids
            )
            for name in ("tp", "fp", "fn")
        }
        stable_rates = RUNNER.rates(**stable_totals)
        repeated_rates = RUNNER.rates(**repeated_totals)
        clean_rows = [
            rows[case_id]
            for case_id in sampled_case_ids
            if rows[case_id]["clean"]
        ]
        if not clean_rows:
            raise ValueError("arm bootstrap sample contains no clean cases")
        families[family].append(
            {
                "stable_precision": stable_rates["precision"],
                "stable_recall": stable_rates["recall"],
                "stable_f1": stable_rates["f1"],
                "repeated_precision": repeated_rates["precision"],
                "clean_case_specificity": (
                    sum(row["clean_without_prediction"] for row in clean_rows)
                    / len(clean_rows)
                ),
            }
        )
    if require_both_families and any(
        not configurations for configurations in families.values()
    ):
        raise ValueError("arm metrics require OpenAI and Anthropic reports")
    families = {
        family: configurations
        for family, configurations in families.items()
        if configurations
    }
    family_values = {
        family: {
            metric: (
                sum(configuration[metric] for configuration in configurations)
                / len(configurations)
            )
            for metric in ARM_POINT_METRICS
        }
        for family, configurations in families.items()
    }
    return {
        metric: (
            sum(values[metric] for values in family_values.values())
            / len(family_values)
        )
        for metric in ARM_POINT_METRICS
    }


def nearest_rank(values: list[float], probability: float) -> float:
    if not values or not 0 <= probability <= 1:
        raise ValueError("nearest-rank requires samples and a probability")
    ordered = sorted(values)
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def paired_stratified_arm_bootstrap(
    reports_by_profile: dict[str, list[dict]],
    cases: list[dict],
    protocol: dict,
) -> dict:
    arm_contract = protocol["arm_comparison"]
    uncertainty = arm_contract["uncertainty"]
    treatment = arm_contract["treatment"]
    controls = arm_contract["controls"]
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
        raise ValueError("arm bootstrap requires finding and clean case strata")
    rows_by_configuration = {
        report_configuration_key(report): report_case_metric_rows(report, cases)
        for reports in reports_by_profile.values()
        for report in reports
    }
    all_case_ids = [*finding_case_ids, *clean_case_ids]
    require_both_families = (
        arm_contract["provider_aggregation"]
        == "mean-within-provider-family-then-equal-weight-families"
    )
    point_metrics = {
        profile: provider_weighted_sample_metrics(
            reports,
            rows_by_configuration,
            all_case_ids,
            require_both_families=require_both_families,
        )
        for profile, reports in reports_by_profile.items()
    }
    samples = {
        control: {
            metric: []
            for metric in ARM_BOOTSTRAP_METRICS
        }
        for control in controls
    }
    generator = random.Random(uncertainty["seed"])
    for _ in range(uncertainty["iterations"]):
        sampled_case_ids = [
            *generator.choices(finding_case_ids, k=len(finding_case_ids)),
            *generator.choices(clean_case_ids, k=len(clean_case_ids)),
        ]
        sampled_metrics = {
            profile: provider_weighted_sample_metrics(
                reports,
                rows_by_configuration,
                sampled_case_ids,
                require_both_families=require_both_families,
            )
            for profile, reports in reports_by_profile.items()
        }
        for control in controls:
            for metric in ARM_BOOTSTRAP_METRICS:
                samples[control][metric].append(
                    sampled_metrics[treatment][metric]
                    - sampled_metrics[control][metric]
                )
    lower_probability = round(
        (1 - uncertainty["confidence"]) / 2,
        12,
    )
    upper_probability = round(1 - lower_probability, 12)
    intervals = {
        control: {
            metric: {
                "method": uncertainty["method"],
                "confidence": uncertainty["confidence"],
                "iterations": uncertainty["iterations"],
                "seed": uncertainty["seed"],
                "strata": uncertainty["strata"],
                "percentile_method": uncertainty["percentile_method"],
                "lower": nearest_rank(values, lower_probability),
                "upper": nearest_rank(values, upper_probability),
            }
            for metric, values in metrics.items()
        }
        for control, metrics in samples.items()
    }
    return {
        "point_metrics": point_metrics,
        "intervals": intervals,
        "interpretation_limit": uncertainty["interpretation_limit"],
    }


def specificity_case_rows(report: dict, cases: list[dict]) -> dict[str, dict]:
    rows = {}
    for case in cases:
        selected = [run for run in report["runs"] if run["case"] == case["id"]]
        if not selected or any(run["score"] is None for run in selected):
            raise ValueError(f"incomplete specificity case {case['id']}")
        clean = sum(not run["findings"] for run in selected)
        rows[case["id"]] = {
            "framework": case["framework"],
            "specificity": float(clean >= (len(selected) // 2 + 1)),
            "false_positive_count": sum(
                len({RUNNER.finding_key(item) for item in run["findings"]})
                for run in selected
            ),
        }
    return rows


def specificity_sample_metrics(rows: dict[str, dict], sampled: list[str]) -> dict:
    return {
        "per_case_specificity": sum(rows[key]["specificity"] for key in sampled) / len(sampled),
        "repeated_run_false_positive_count_per_case":
            sum(rows[key]["false_positive_count"] for key in sampled) / len(sampled),
    }


def paired_specificity_bootstrap(reports_by_profile: dict, cases: list[dict], protocol: dict) -> dict:
    contract = protocol["arm_comparison"]
    treatment, controls = contract["treatment"], contract["controls"]
    rows = {profile: specificity_case_rows(items[0], cases)
            for profile, items in reports_by_profile.items()}
    case_ids = [case["id"] for case in cases]
    point = {profile: specificity_sample_metrics(profile_rows, case_ids)
             for profile, profile_rows in rows.items()}
    samples = {control: {"per_case_specificity": [],
        "repeated_run_false_positive_count_per_case": []} for control in controls}
    case_stratum = [case["id"] for case in cases]
    generator = random.Random(contract["uncertainty"]["seed"])
    for _ in range(contract["uncertainty"]["iterations"]):
        sampled = generator.choices(case_stratum, k=len(case_stratum))
        metrics = {profile: specificity_sample_metrics(profile_rows, sampled)
                   for profile, profile_rows in rows.items()}
        for control in controls:
            samples[control]["per_case_specificity"].append(
                metrics[treatment]["per_case_specificity"]
                - metrics[control]["per_case_specificity"])
            samples[control]["repeated_run_false_positive_count_per_case"].append(
                metrics[control]["repeated_run_false_positive_count_per_case"]
                - metrics[treatment]["repeated_run_false_positive_count_per_case"])
    probability = round((1 - contract["uncertainty"]["confidence"]) / 2, 12)
    intervals = {control: {metric: {
        "lower": nearest_rank(values, probability),
        "upper": nearest_rank(values, 1 - probability),
        **{key: contract["uncertainty"][key] for key in
           ("method", "confidence", "iterations", "seed", "strata", "percentile_method")},
    } for metric, values in metrics.items()} for control, metrics in samples.items()}
    return {"point_metrics": point, "intervals": intervals,
            "interpretation_limit": contract["uncertainty"]["interpretation_limit"]}


def threshold_check(metric, actual, required, comparator):
    passed = (actual > required if comparator == ">" else
              actual >= required if comparator == ">=" else actual <= required)
    return {"metric": metric, "actual": actual, "required": required,
            "comparator": comparator, "passed": passed}


def _specificity_lift_checks(point, intervals, treatment, control, thresholds):
    return [
        threshold_check("per_case_specificity_delta_min",
            point[treatment]["per_case_specificity"] - point[control]["per_case_specificity"],
            thresholds["per_case_specificity_delta_min"], ">="),
        threshold_check("per_case_specificity_delta_ci95_lower_min_exclusive",
            intervals["per_case_specificity"]["lower"],
            thresholds["per_case_specificity_delta_ci95_lower_min_exclusive"], ">"),
        threshold_check("repeated_run_false_positive_count_per_case_advantage_min",
            point[control]["repeated_run_false_positive_count_per_case"]
            - point[treatment]["repeated_run_false_positive_count_per_case"],
            thresholds["repeated_run_false_positive_count_per_case_advantage_min"], ">="),
        threshold_check(
            "repeated_run_false_positive_count_per_case_advantage_ci95_lower_min_exclusive",
            intervals["repeated_run_false_positive_count_per_case"]["lower"],
            thresholds[
                "repeated_run_false_positive_count_per_case_advantage_ci95_lower_min_exclusive"
            ], ">"),
    ]


def decide_specificity_matrix(reports_by_profile, cases, protocol):
    treatment = protocol["arm_comparison"]["treatment"]
    controls = protocol["arm_comparison"]["controls"]
    minimum = protocol["corpus"]["case_count_minimum"]
    framework_counts = Counter(case["framework"] for case in cases)
    if len(cases) < minimum:
        return {"status": "INCONCLUSIVE", "specificity_claim_eligible": False,
                "skill_lift_claim_eligible": False,
                "status_reasons": [{"code": "specificity_corpus_minimum_not_met",
                    "case_count": len(cases), "framework_counts": dict(framework_counts)}],
                "metrics": None, "claim_policy": protocol["claim_policy"]}
    bootstrap = paired_specificity_bootstrap(reports_by_profile, cases, protocol)
    point = bootstrap["point_metrics"]
    absolute = protocol["decision"]["full_arm_absolute_thresholds"]
    comparative = protocol["decision"]["full_vs_each_control_thresholds"]
    checks = [
        threshold_check("per_case_specificity_min",
            point[treatment]["per_case_specificity"],
            absolute["per_case_specificity_min"], ">="),
        threshold_check("repeated_run_false_positive_count_per_case_max",
            point[treatment]["repeated_run_false_positive_count_per_case"],
            absolute["repeated_run_false_positive_count_per_case_max"], "<="),
    ]
    lift = {}
    for control in controls:
        intervals = bootstrap["intervals"][control]
        control_checks = _specificity_lift_checks(
            point, intervals, treatment, control, comparative,
        )
        checks.extend(control_checks)
        lift[control] = {"decision_checks": control_checks,
                         "paired_bootstrap_ci95": intervals}
    full_pass = reports_by_profile[treatment][0]["status"] == "PASS"
    if not full_pass:
        checks.append({"metric": "full_arm_status", "actual":
            reports_by_profile[treatment][0]["status"], "required": "PASS",
            "comparator": "==", "passed": False})
    status = "PASS" if full_pass and all(row["passed"] for row in checks) else "FAIL"
    return {"status": status, "specificity_claim_eligible": status == "PASS",
            "skill_lift_claim_eligible": False,
            "status_reasons": [{"code": "all_specificity_gates_met" if status == "PASS"
                else "specificity_gate_not_met",
                "failed_checks": [row for row in checks if not row["passed"]]}],
            "metrics": {"arm_point_metrics": point, "absolute_checks": checks[:2],
                        "lift": lift, "uncertainty": bootstrap},
            "claim_policy": protocol["claim_policy"]}


def parse_report_findings(output: str, schema_policy: dict | None) -> list[dict]:
    """Reparse stored output under the protocol's finding schema, when opted in."""
    return RUNNER.parse_findings(
        output, schema_policy["schema"] if schema_policy is not None else None
    )


def recompute_report(
    report: dict,
    all_cases: list[dict],
    corpus_sha256: str,
    protocol: dict,
    protocol_sha256: str,
    corpus_visibility: str | None = None,
    comparison_scope: str = "development",
    evaluator_sha256: str | None = None,
    skill_dir: Path | None = None,
) -> dict:
    """Re-derive one report from its raw outputs and the selected inputs.

    skill_dir is the evaluated skill whose files the prompt digest is
    recomputed from; it defaults to the checkout's skill. Only a
    revision-comparison protocol passes another directory, the pinned
    revision the report recorded.
    """
    protocol_id = protocol.get("protocol_id")
    validate_provenance(report, comparison_scope)
    if (
        corpus_visibility is not None
        and report["corpus_visibility"] != corpus_visibility
    ):
        raise ValueError("report corpus_visibility does not match selected corpus")
    release_repetitions = protocol["schedule"]["release_repetitions"]
    if (
        isinstance(report["repetitions"], bool)
        or not isinstance(report["repetitions"], int)
        or report["repetitions"] <= 0
        or report["repetitions"] != release_repetitions
        or report["release_repetitions"] != release_repetitions
    ):
        raise ValueError(
            "report repetitions do not match protocol release_repetitions"
        )

    selected_ids = {item["case"] for item in report["schedule"]}
    all_case_ids = {case["id"] for case in all_cases}
    if selected_ids != all_case_ids:
        missing = sorted(all_case_ids - selected_ids)
        extra = sorted(selected_ids - all_case_ids)
        raise ValueError(
            "cross-host comparison requires the full selected corpus; "
            f"missing={missing}, extra={extra}"
        )
    cases = [case for case in all_cases if case["id"] in selected_ids]
    if selected_ids != {case["id"] for case in cases}:
        raise ValueError("schedule references unknown corpus cases")
    expected_case_scope = {
        "selection": "full",
        "selected_case_ids": [case["id"] for case in all_cases],
        "selected_case_count": len(all_cases),
        "total_case_count": len(all_cases),
    }
    if not equivalent(report["case_scope"], expected_case_scope):
        raise ValueError("case_scope does not match the full selected corpus")
    expected_decision_scope = {
        "mode": "release",
        "repetitions": release_repetitions,
        "release_repetitions": release_repetitions,
    }
    if not equivalent(report["decision_scope"], expected_decision_scope):
        raise ValueError("decision_scope does not match the release protocol")
    expected_schedule = RUNNER.build_schedule(
        cases,
        report["repetitions"],
        protocol["schedule"]["seed"],
    )
    if report["schedule"] != expected_schedule:
        raise ValueError("serialized schedule does not match corpus/protocol")
    if report["schedule_sha256"] != RUNNER.canonical_json_sha256(expected_schedule):
        raise ValueError("schedule_sha256 does not match recomputed schedule")
    if report["corpus_sha256"] != corpus_sha256:
        raise ValueError("corpus_sha256 does not match selected corpus")
    expected_evaluator_sha256 = (
        evaluator_sha256
        if evaluator_sha256 is not None
        else RUNNER.evaluator_digest()
    )
    if report["evaluator_sha256"] != expected_evaluator_sha256:
        raise ValueError("evaluator_sha256 does not match selected evaluator")
    if (
        protocol_id in RUNNER.FULL_ONLY_PROTOCOL_IDS
        and report["prompt_profile"] != "full"
    ):
        raise ValueError("report prompt_profile is not preregistered by protocol")
    if protocol_id in RUNNER.PROMPT_ARM_PROTOCOL_IDS:
        prompt_arms = protocol["prompt_arms"]
        declared_arms = {
            prompt_arms["treatment"],
            *prompt_arms["controls"],
        }
        if report["prompt_profile"] not in declared_arms:
            raise ValueError(
                "report prompt_profile is not preregistered by protocol"
            )
    expected_prompt_set_sha256 = RUNNER.prompt_set_digest(
        cases,
        corpus_sha256,
        skill_dir if skill_dir is not None else RUNNER.DEFAULT_SKILL_DIR,
        report["prompt_profile"],
        numbered_source_lines=(
            protocol_id in RUNNER.NUMBERED_SOURCE_PROTOCOL_IDS
        ),
    )
    if report["prompt_set_sha256"] != expected_prompt_set_sha256:
        raise ValueError("prompt_set_sha256 does not match selected cases")
    if (
        report["protocol_sha256"] != protocol_sha256
        or report["protocol_sha256_after"] != protocol_sha256
        or report.get("protocol") != protocol
    ):
        raise ValueError("report protocol does not match selected protocol")
    execution_identity = protocol.get("execution_identity")
    if isinstance(execution_identity, dict):
        if not isinstance(report.get("runner_executable"), str):
            raise ValueError(
                "protocol requires a captured explicit runner_executable path"
            )
        expected_identity = execution_identity["expected_cli_versions"].get(
            report["runner"]
        )
        identity_policy = execution_identity.get("version_policy", "exact")
        if expected_identity is None or not RUNNER.runner_identity_matches(
            report["runner"],
            report["runner_identity"],
            expected_identity,
            identity_policy,
        ):
            raise ValueError(
                "runner_identity does not match the preregistered CLI version"
            )

    case_by_id = {case["id"]: case for case in cases}
    revised_labels = protocol_id in RUNNER.REVISED_LABEL_PROTOCOL_IDS
    if len(report["runs"]) != len(expected_schedule):
        raise ValueError("run count does not match recomputed schedule")
    retry_policy = RUNNER.infrastructure_retry_policy(protocol)
    validate_retry_records(report, retry_policy)
    usage_policy = RUNNER.usage_capture_policy(protocol)
    validate_usage_records(report, usage_policy)
    normalization_policy = RUNNER.output_normalization_policy(protocol)
    validate_output_normalization_records(report, normalization_policy)
    validate_output_schema_records(report, RUNNER.output_schema_policy(protocol))
    normalized_runs: list[dict] = []
    for scheduled, stored in zip(expected_schedule, report["runs"]):
        identity = (
            stored.get("schedule_ordinal"),
            stored.get("case"),
            stored.get("repetition"),
        )
        expected_identity = (
            scheduled["ordinal"],
            scheduled["case"],
            scheduled["repetition"],
        )
        if identity != expected_identity:
            raise ValueError("run order or schedule identity was tampered")
        workspace_before = stored.get("workspace_sha256_before")
        workspace_after = stored.get("workspace_sha256_after")
        require_sha256(
            workspace_before,
            f"run {scheduled['ordinal']} workspace_sha256_before",
        )
        require_sha256(
            workspace_after,
            f"run {scheduled['ordinal']} workspace_sha256_after",
        )
        scoreable = (
            stored.get("exit_code") == 0
            and stored.get("error") is None
            and workspace_before == workspace_after
        )
        if normalization_policy is not None and stored[NORMALIZED_KEY] != (
            RUNNER.output_normalization_applied(stored)
        ):
            raise ValueError("stored output_normalized does not match raw model output")
        if scoreable and normalization_policy is not None:
            findings = RUNNER.parse_normalized_findings(stored.get("output", ""))
            if findings != stored.get("findings"):
                raise ValueError("stored findings do not match raw model output")
            computed_score = RUNNER.score(
                case_by_id[stored["case"]],
                findings,
                revised_labels=revised_labels,
            )
        elif scoreable:
            findings = parse_report_findings(
                stored.get("output", ""), RUNNER.output_schema_policy(protocol)
            )
            if findings != stored.get("findings"):
                raise ValueError("stored findings do not match raw model output")
            computed_score = RUNNER.score(
                case_by_id[stored["case"]],
                findings,
                revised_labels=revised_labels,
            )
        else:
            findings = []
            computed_score = None
        if stored.get("score") != computed_score:
            raise ValueError("stored run score does not match corpus oracle")
        normalized_runs.append(
            {
                **stored,
                "findings": findings,
                "score": computed_score,
            }
        )
    summary = repeated_summary(normalized_runs)
    if protocol_id in RUNNER.SPECIFICITY_PROTOCOL_IDS:
        primary, secondary = RUNNER.specificity_metrics(
            cases, normalized_runs, protocol,
        )
    else:
        secondary = {"aggregation_unit": "repeated-run", **summary}
        primary = RUNNER.primary_metrics(
            cases, normalized_runs, report["repetitions"],
            protocol["stability"]["rule"],
            revised_labels=revised_labels,
        )
    by_case = {}
    for case in cases:
        selected = [run for run in normalized_runs if run["case"] == case["id"]]
        by_case[case["id"]] = RUNNER.rates(
            **{
                name: sum(
                    run["score"][name]
                    for run in selected
                    if run["score"] is not None
                )
                for name in ("tp", "fp", "fn")
            }
        )
        by_case[case["id"]].update(
            {
                "runs": len(selected),
                "successful_runs": sum(run["score"] is not None for run in selected),
                "infrastructure_errors": sum(
                    run["score"] is None for run in selected
                ),
            }
        )

    integrity_args = (
        expected_schedule, normalized_runs, protocol_sha256,
        report["protocol_sha256_after"], report["skill_sha256"],
        report["skill_sha256_after"], corpus_sha256,
        report["corpus_sha256_after"],
    )
    integrity_kwargs = {
        "source_read_isolation": report["source_read_isolation"],
        "case_scope": expected_case_scope,
        "decision_scope": expected_decision_scope,
    }
    if protocol_id in RUNNER.SPECIFICITY_PROTOCOL_IDS:
        status, reasons = RUNNER.classify_specificity_status(
            primary, secondary, protocol, integrity_args, integrity_kwargs,
        )
    else:
        status, reasons = RUNNER.classify_status(
            primary, secondary, *integrity_args,
            thresholds=protocol["decision"]["thresholds"], **integrity_kwargs,
        )
    expected_execution_complete = RUNNER.execution_complete(
        expected_schedule,
        normalized_runs,
        protocol_sha256,
        report["protocol_sha256_after"],
        report["skill_sha256"],
        report["skill_sha256_after"],
        corpus_sha256,
        report["corpus_sha256_after"],
    )
    expected_complete = status != "INCONCLUSIVE"
    checks = {
        "summary": summary,
        "primary_metrics": primary,
        "secondary_metrics": secondary,
        "by_case": by_case,
        "status": status,
        "status_reasons": reasons,
        "complete": expected_complete,
        "execution_complete": expected_execution_complete,
        "evidence_limitations": RUNNER.evidence_limitations(
            report["source_read_isolation"],
            report["prompt_profile"],
        ),
    }
    if retry_policy is not None:
        checks["infrastructure_retry_summary"] = (
            RUNNER.infrastructure_retry_summary(
                normalized_runs, tuple(retry_policy["retryable"])
            )
        )
    if usage_policy is not None:
        checks["usage_summary"] = RUNNER.usage_summary(normalized_runs)
    if normalization_policy is not None:
        checks["output_normalization_summary"] = (
            RUNNER.output_normalization_summary(normalized_runs)
        )
    for field, expected in checks.items():
        if not equivalent(report.get(field), expected):
            raise ValueError(f"serialized {field} does not match recomputed value")
    return {
        **report,
        "runs": normalized_runs,
        **checks,
    }


def validate_retry_records(report: dict, retry_policy: dict | None) -> None:
    """Check per-run attempt records against the protocol's retry policy.

    A protocol without a policy must carry no retry fields at all. Under a
    policy, every run records 1..max attempts; each non-final attempt names a
    preregistered retryable reason, the final attempt matches the scored run,
    and a scoreable final attempt carries no reason.
    """
    runs = report["runs"]
    if retry_policy is None:
        if (
            "infrastructure_retry" in report
            or "infrastructure_retry_summary" in report
            or any("attempts" in run for run in runs)
        ):
            raise ValueError(
                "report carries retry records but the protocol has no retry policy"
            )
        return
    if report.get("infrastructure_retry") != retry_policy:
        raise ValueError("report infrastructure_retry does not match the protocol")
    if "infrastructure_retry_summary" not in report:
        raise ValueError("report is missing its infrastructure_retry_summary")
    retryable = set(retry_policy["retryable"])
    maximum = retry_policy["max_attempts_per_call"]
    attempt_keys = (
        ATTEMPT_KEYS | {USAGE_KEY} if "usage_capture" in report else ATTEMPT_KEYS
    )
    for index, run in enumerate(runs):
        attempts = run.get("attempts")
        if not isinstance(attempts, list) or not 1 <= len(attempts) <= maximum:
            raise ValueError(f"run {index + 1} attempts exceed the retry policy")
        for number, attempt in enumerate(attempts, start=1):
            require_exact_object_keys(
                attempt, attempt_keys, f"run {index + 1} attempt {number}"
            )
            if attempt["attempt"] != number:
                raise ValueError(f"run {index + 1} attempts are not numbered in order")
            reason = attempt["reason"]
            if reason is not None and reason not in retryable:
                raise ValueError(f"run {index + 1} attempt reason is not retryable")
            if number < len(attempts) and reason is None:
                raise ValueError(
                    f"run {index + 1} retried an attempt with no retryable reason"
                )
        final = attempts[-1]
        if final["exit_code"] != run["exit_code"] or final["error"] != run["error"]:
            raise ValueError(f"run {index + 1} final attempt does not match the run")
        if run["error"] is None and final["reason"] is not None:
            raise ValueError(f"run {index + 1} scoreable attempt carries a retry reason")
        if len(attempts) < maximum and final["reason"] is not None:
            raise ValueError(
                f"run {index + 1} stopped before exhausting a retryable failure"
            )


def validate_usage_records(report: dict, usage_policy: dict | None) -> None:
    """Check usage records against the protocol's usage-capture opt-in.

    A protocol without the opt-in must carry no usage fields at all, so its
    report schema is exactly the pre-usage one. Under the opt-in, every run
    and every attempt records usage (null or a valid record), and a run's
    usage is its final attempt's usage.
    """
    runs = report["runs"]
    if usage_policy is None:
        if (
            "usage_capture" in report
            or "usage_summary" in report
            or any(USAGE_KEY in run for run in runs)
            or any(
                USAGE_KEY in attempt
                for run in runs
                for attempt in run.get("attempts", [])
                if isinstance(attempt, dict)
            )
        ):
            raise ValueError(
                "report carries usage records but the protocol has no usage capture"
            )
        return
    if report.get("usage_capture") != usage_policy:
        raise ValueError("report usage_capture does not match the protocol")
    if "usage_summary" not in report:
        raise ValueError("report is missing its usage_summary")
    for index, run in enumerate(runs):
        if USAGE_KEY not in run:
            raise ValueError(f"run {index + 1} is missing its usage record")
        RUNNER.validate_usage_record(run[USAGE_KEY], f"run {index + 1}")
        attempts = run.get("attempts")
        if attempts is None:
            continue
        for number, attempt in enumerate(attempts, start=1):
            if not isinstance(attempt, dict) or USAGE_KEY not in attempt:
                raise ValueError(
                    f"run {index + 1} attempt {number} is missing its usage record"
                )
            RUNNER.validate_usage_record(
                attempt[USAGE_KEY], f"run {index + 1} attempt {number}"
            )
        if attempts and attempts[-1][USAGE_KEY] != run[USAGE_KEY]:
            raise ValueError(f"run {index + 1} usage does not match its final attempt")


def validate_output_normalization_records(
    report: dict, normalization_policy: dict | None
) -> None:
    """Check output-normalization records against the protocol's opt-in.

    A protocol without the opt-in must carry no normalization fields, so its
    report schema is exactly the earlier one. Under the opt-in, every run
    records a boolean output_normalized and the report carries its summary.
    """
    runs = report["runs"]
    if normalization_policy is None:
        if (
            "output_normalization" in report
            or "output_normalization_summary" in report
            or any(NORMALIZED_KEY in run for run in runs)
        ):
            raise ValueError(
                "report carries output-normalization records but the protocol "
                "has no output normalization"
            )
        return
    if report.get("output_normalization") != normalization_policy:
        raise ValueError("report output_normalization does not match the protocol")
    if "output_normalization_summary" not in report:
        raise ValueError("report is missing its output_normalization_summary")
    for index, run in enumerate(runs):
        if not isinstance(run.get(NORMALIZED_KEY), bool):
            raise ValueError(f"run {index + 1} is missing its output_normalized flag")


def validate_output_schema_records(report: dict, schema_policy: dict | None) -> None:
    """Check the enforced-output-schema provenance against the protocol's opt-in.

    A protocol without the opt-in must carry no output_schema field. Under it,
    the report must carry the protocol's exact block, whose schema_sha256 is
    recomputed from the embedded schema. Run records are unchanged: the
    stored output is the answer the strict parser judged.
    """
    if schema_policy is None:
        if "output_schema" in report:
            raise ValueError(
                "report carries an output_schema but the protocol has no "
                "enforced output schema"
            )
        return
    recorded = report.get("output_schema")
    if recorded != schema_policy:
        raise ValueError("report output_schema does not match the protocol")
    if RUNNER.output_schema_sha256(recorded["schema"]) != recorded["schema_sha256"]:
        raise ValueError("report output_schema digest does not match its schema")


def output_normalization_rows(reports: list[dict]) -> list[dict]:
    """Surface each report's (arm's) normalized-run counts, recomputed from its runs."""
    rows = []
    for report in reports:
        try:
            summary = RUNNER.output_normalization_summary(report["runs"])
        except (KeyError, TypeError):
            summary = None
        rows.append(
            {
                "prompt_profile": report.get("prompt_profile"),
                "runner": report.get("runner"),
                "model": report.get("model"),
                "output_normalization_summary": summary,
            }
        )
    return rows


def usage_rows(reports: list[dict]) -> list[dict]:
    """Surface each report's (arm's) usage summary, recomputed from its runs."""
    rows = []
    for report in reports:
        try:
            summary = RUNNER.usage_summary(report["runs"])
        except (KeyError, TypeError):
            summary = None
        rows.append(
            {
                "prompt_profile": report.get("prompt_profile"),
                "runner": report.get("runner"),
                "model": report.get("model"),
                "usage_summary": summary,
            }
        )
    return rows


def per_report_sections(protocol: dict, reports: list[dict]) -> dict:
    """Output sections that list per-report (per-arm) counts for opted-in protocols."""
    sections: dict = {}
    retry_policy = RUNNER.infrastructure_retry_policy(protocol)
    if retry_policy is not None:
        # Retried-then-scored runs are ordinary scored runs above; the counts
        # are surfaced here so a reader sees how many calls needed a retry.
        sections["infrastructure_retry"] = {
            "policy": retry_policy,
            "reports": retry_count_rows(reports),
        }
    usage_policy = RUNNER.usage_capture_policy(protocol)
    if usage_policy is not None:
        # Descriptive cost evidence only: usage enters no threshold or decision.
        sections["usage_capture"] = {
            "policy": usage_policy,
            "reports": usage_rows(reports),
        }
    normalization_policy = RUNNER.output_normalization_policy(protocol)
    if normalization_policy is not None:
        # Counts of runs judged on a fence-stripped answer, per arm. The rule
        # is preregistered and identical across arms; the counts let a reader
        # see how much each arm relied on it.
        sections["output_normalization"] = {
            "policy": normalization_policy,
            "reports": output_normalization_rows(reports),
        }
    return sections


def retry_count_rows(reports: list[dict]) -> list[dict]:
    """Surface each report's retry counts, recomputed from its attempt records."""
    rows = []
    for report in reports:
        try:
            policy = report.get("infrastructure_retry", RUNNER.EXPECTED_INFRASTRUCTURE_RETRY)
            summary = RUNNER.infrastructure_retry_summary(
                report["runs"], tuple(policy["retryable"])
            )
        except (KeyError, TypeError):
            summary = None
        rows.append(
            {
                "prompt_profile": report.get("prompt_profile"),
                "runner": report.get("runner"),
                "model": report.get("model"),
                "infrastructure_retry_summary": summary,
            }
        )
    return rows


def compare_reports(
    reports: list[dict],
    all_cases: list[dict],
    corpus_sha256: str,
    protocol: dict,
    protocol_sha256: str,
    corpus_visibility: str | None = None,
    comparison_scope: str = "development",
    evaluator_sha256: str | None = None,
) -> dict:
    protocol_id = protocol.get("protocol_id")
    reasons: list[dict] = []
    expected_report_count = len(protocol["host_matrix"])
    if len(reports) != expected_report_count:
        raise ValueError(
            f"expected {expected_report_count} reports from the preregistered "
            "host matrix"
        )

    recomputed = []
    for report in reports:
        try:
            recomputed.append(
                recompute_report(
                    report,
                    all_cases,
                    corpus_sha256,
                    protocol,
                    protocol_sha256,
                    corpus_visibility,
                    comparison_scope,
                    evaluator_sha256,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            reasons.append(
                {
                    "code": "report_integrity_error",
                    "runner": report.get("runner"),
                    "message": str(exc),
                }
            )
    if reasons:
        return {
            "status": "INCONCLUSIVE",
            "status_reasons": reasons,
            "metrics": None,
        }
    reports = recomputed

    required_hosts = {
        (entry["runner"], entry["model"])
        for entry in protocol["host_matrix"]
    }
    actual_hosts = {(report["runner"], report["model"]) for report in reports}
    if actual_hosts != required_hosts:
        reasons.append(
            {
                "code": "host_matrix_mismatch",
                "actual": sorted([list(item) for item in actual_hosts]),
                "required": sorted([list(item) for item in required_hosts]),
                "message": "reports do not match the preregistered runner/model matrix",
            }
        )

    shared_fields = (
        "skill_sha256",
        "corpus_sha256",
        "schedule_sha256",
        "repetitions",
        "evaluator_sha256",
        "prompt_set_sha256",
        "prompt_profile",
        "source_read_isolation",
        "workspace_integrity",
        "input_snapshot",
    )
    if protocol_id in RUNNER.ADJUDICATED_SPECIFICITY_PROTOCOL_IDS:
        shared_fields += ("adjudication_ledger_sha256",)
    if protocol_id in {"reviewer-specificity-v3", "reviewer-specificity-v4"}:
        shared_fields += ("repository_walk_sha256",)
    for field in shared_fields:
        values = {report[field] for report in reports}
        if len(values) != 1:
            reasons.append(
                {
                    "code": "provenance_mismatch",
                    "field": field,
                    "message": f"reports disagree on {field}",
                }
            )

    for report in reports:
        runner = report["runner"]
        host = f"{runner}:{report['model']}"
        if (
            not report["complete"]
            or not report["execution_complete"]
            or report["status"] == "INCONCLUSIVE"
        ):
            reasons.append(
                {
                    "code": "input_inconclusive",
                    "runner": runner,
                    "model": report["model"],
                    "message": f"{host} report is incomplete or inconclusive",
                }
            )
        if (
            report["protocol_sha256"] != protocol_sha256
            or report["protocol_sha256_after"] != protocol_sha256
        ):
            reasons.append(
                {
                    "code": "protocol_mismatch",
                    "runner": runner,
                    "model": report["model"],
                    "message": f"{host} report does not use the selected protocol",
                }
            )

    if reasons:
        return {
            "status": "INCONCLUSIVE",
            "status_reasons": reasons,
            "metrics": None,
        }

    prediction_sets = [stable_predictions(report) for report in reports]
    union = set().union(*prediction_sets)
    intersection = set.intersection(*prediction_sets)
    recalls = [
        report["primary_metrics"]["unique"]["recall"] for report in reports
    ]
    pairwise = []
    for left_index in range(len(reports)):
        for right_index in range(left_index + 1, len(reports)):
            left = reports[left_index]
            right = reports[right_index]
            pair_union = prediction_sets[left_index] | prediction_sets[right_index]
            pair_intersection = (
                prediction_sets[left_index] & prediction_sets[right_index]
            )
            pairwise.append(
                {
                    "left": {
                        "runner": left["runner"],
                        "model": left["model"],
                    },
                    "right": {
                        "runner": right["runner"],
                        "model": right["model"],
                    },
                    "stable_recall_gap": abs(
                        recalls[left_index] - recalls[right_index]
                    ),
                    "stable_prediction_jaccard": (
                        len(pair_intersection) / len(pair_union)
                        if pair_union
                        else 1.0
                    ),
                    "stable_prediction_intersection": len(pair_intersection),
                    "stable_prediction_union": len(pair_union),
                }
            )
    # A Codex-only protocol has no pairwise host comparison. Its agreement
    # values are the neutral singleton identities; the absolute report-status
    # gate remains load-bearing.
    recall_gap = max(
        (item["stable_recall_gap"] for item in pairwise), default=0.0
    )
    jaccard = min(
        (item["stable_prediction_jaccard"] for item in pairwise), default=1.0
    )
    metrics = {
        "stable_recall_gap": recall_gap,
        "stable_prediction_jaccard": jaccard,
        "stable_prediction_intersection": len(intersection),
        "stable_prediction_union": len(union),
        "agreement_aggregation": {
            "stable_recall_gap": "maximum pairwise gap",
            "stable_prediction_jaccard": "minimum pairwise Jaccard",
            "global_intersection_and_union": "all hosts",
        },
        "pairwise": pairwise,
        "hosts": [
            {
                "runner": report["runner"],
                "model": report["model"],
                "status": report["status"],
                "stable_precision": report["primary_metrics"]["unique"]["precision"],
                "stable_recall": report["primary_metrics"]["unique"]["recall"],
                "stable_predictions": len(predictions),
            }
            for report, predictions in zip(reports, prediction_sets)
        ],
    }
    if protocol_id in RUNNER.PROVIDER_BALANCED_PROTOCOL_IDS:
        metrics["provider_family_aggregation"] = provider_family_aggregation(
            reports
        )

    decision = protocol["cross_host_decision"]
    required_status = decision["requires_each_report_status"]
    for report in reports:
        if report["status"] != required_status:
            host = f"{report['runner']}:{report['model']}"
            reasons.append(
                {
                    "code": "input_status_not_met",
                    "runner": report["runner"],
                    "model": report["model"],
                    "actual": report["status"],
                    "required": required_status,
                    "message": (
                        f"{host} status was {report['status']}; "
                        f"required {required_status}"
                    ),
                }
            )

    thresholds = decision["thresholds"]
    checks = {
        "stable_recall_gap_max": recall_gap,
        "stable_prediction_jaccard_min": jaccard,
    }
    for name, actual in checks.items():
        threshold = thresholds[name]
        passed = actual <= threshold if name.endswith("_max") else actual >= threshold
        if not passed:
            comparator = "<=" if name.endswith("_max") else ">="
            reasons.append(
                {
                    "code": "cross_host_threshold_not_met",
                    "metric": name,
                    "actual": actual,
                    "required": threshold,
                    "comparator": comparator,
                    "message": (
                        f"{name} was {actual:.6f}; "
                        f"required {comparator} {threshold:.6f}"
                    ),
                }
            )

    if reasons:
        return {"status": "FAIL", "status_reasons": reasons, "metrics": metrics}
    return {
        "status": "PASS",
        "status_reasons": [
            {
                "code": "all_cross_host_thresholds_met",
                "message": (
                    "all preregistered cross-host thresholds passed for "
                    f"{comparison_scope} evidence"
                ),
            }
        ],
        "metrics": metrics,
    }


def compare_arm_reports(
    reports: list[dict],
    all_cases: list[dict],
    corpus_sha256: str,
    protocol: dict,
    protocol_sha256: str,
    corpus_visibility: str | None = None,
    comparison_scope: str = "development",
    evaluator_sha256: str | None = None,
) -> dict:
    protocol_id = protocol.get("protocol_id")
    arm_contract = protocol.get("arm_comparison")
    if (
        protocol_id not in RUNNER.ARM_COMPARISON_PROTOCOL_IDS
        or not isinstance(arm_contract, dict)
    ):
        raise ValueError("selected protocol has no frozen arm-comparison contract")
    treatment = arm_contract["treatment"]
    controls = arm_contract["controls"]
    if protocol_id in RUNNER.SPECIFICITY_PROTOCOL_IDS:
        claim_policy = protocol["claim_policy"]
    else:
        claim_policy = arm_contract["claim_policy"]
    profiles = [treatment, *controls]
    required_hosts = {
        (entry["runner"], entry["model"])
        for entry in protocol["host_matrix"]
    }
    required_configurations = {
        (profile, runner, model)
        for profile in profiles
        for runner, model in required_hosts
    }
    actual_configurations = [
        report_configuration_key(report)
        for report in reports
    ]
    if (
        len(reports) != len(required_configurations)
        or len(set(actual_configurations)) != len(actual_configurations)
        or set(actual_configurations) != required_configurations
    ):
        return {
            "status": "INCONCLUSIVE",
            "skill_lift_claim_eligible": False,
            "status_reasons": [
                {
                    "code": "arm_matrix_mismatch",
                    "actual": sorted([list(item) for item in actual_configurations]),
                    "required": sorted([list(item) for item in required_configurations]),
                    "message": (
                        "arm comparison requires one complete report for every "
                        "preregistered profile and host"
                    ),
                }
            ],
            "metrics": None,
            "claim_policy": claim_policy,
        }

    normalized: list[dict] = []
    integrity_reasons: list[dict] = []
    for report in reports:
        try:
            normalized.append(
                recompute_report(
                    report,
                    all_cases,
                    corpus_sha256,
                    protocol,
                    protocol_sha256,
                    corpus_visibility,
                    comparison_scope,
                    evaluator_sha256,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            integrity_reasons.append(
                {
                    "code": "report_integrity_error",
                    "profile": report.get("prompt_profile"),
                    "runner": report.get("runner"),
                    "model": report.get("model"),
                    "message": str(exc),
                }
            )
    if integrity_reasons:
        return {
            "status": "INCONCLUSIVE",
            "skill_lift_claim_eligible": False,
            "status_reasons": integrity_reasons,
            "metrics": None,
            "claim_policy": claim_policy,
        }

    completeness_reasons = []
    for report in normalized:
        if (
            not report["complete"]
            or not report["execution_complete"]
            or report["status"] == "INCONCLUSIVE"
        ):
            completeness_reasons.append(
                {
                    "code": "arm_input_incomplete",
                    "profile": report["prompt_profile"],
                    "runner": report["runner"],
                    "model": report["model"],
                    "message": (
                        "every arm report must finish the exact schedule without "
                        "infrastructure or integrity errors"
                    ),
                }
            )
    shared_fields = (
        "skill_sha256",
        "corpus_sha256",
        "protocol_sha256",
        "schedule_sha256",
        "repetitions",
        "evaluator_sha256",
        "git_revision",
        "git_dirty",
        "git_dirty_sha256",
        "source_read_isolation",
        "workspace_integrity",
        "input_snapshot",
        "model_tool_surface",
        "evidence_scope",
    )
    for field in shared_fields:
        values = {report[field] for report in normalized}
        if len(values) != 1:
            completeness_reasons.append(
                {
                    "code": "arm_provenance_mismatch",
                    "field": field,
                    "message": f"arm reports disagree on {field}",
                }
            )
    for runner, model in required_hosts:
        host_reports = [
            report
            for report in normalized
            if (report["runner"], report["model"]) == (runner, model)
        ]
        identities = {
            (
                report["runner_identity"],
                report.get("runner_executable"),
                report.get("reasoning_effort"),
            )
            for report in host_reports
        }
        if len(identities) != 1:
            completeness_reasons.append(
                {
                    "code": "arm_runner_identity_mismatch",
                    "runner": runner,
                    "model": model,
                    "message": (
                        "the same host/model must use one CLI identity and resolved "
                        "runner path across every arm"
                    ),
                }
            )
    for runner in {runner for runner, _ in required_hosts}:
        runner_bindings = {
            (
                report["runner_identity"],
                report.get("runner_executable"),
                report.get("reasoning_effort"),
            )
            for report in normalized
            if report["runner"] == runner
        }
        if len(runner_bindings) != 1:
            completeness_reasons.append(
                {
                    "code": "arm_runner_binding_mismatch",
                    "runner": runner,
                    "message": (
                        "one runner family must use one CLI identity and resolved "
                        "executable across every model and arm"
                    ),
                }
            )
    timestamped_reports = []
    actual_order: list[dict] = []
    elapsed_seconds: float | None = None
    for report in normalized:
        try:
            started_at = report_timestamp(report, "started_at")
            completed_at = report_timestamp(report, "created_at")
            if completed_at < started_at:
                raise ValueError("created_at precedes started_at")
            timestamped_reports.append((started_at, completed_at, report))
        except ValueError as exc:
            completeness_reasons.append(
                {
                    "code": "arm_execution_time_invalid",
                    "profile": report["prompt_profile"],
                    "runner": report["runner"],
                    "model": report["model"],
                    "message": str(exc),
                }
            )
    if len(timestamped_reports) == len(normalized):
        start_timestamps = [started for started, _, _ in timestamped_reports]
        if len(set(start_timestamps)) != len(start_timestamps):
            completeness_reasons.append(
                {
                    "code": "arm_execution_time_collision",
                    "message": (
                        "every arm report must have a distinct start timestamp"
                    ),
                }
            )
        ordered_intervals = sorted(
            timestamped_reports,
            key=lambda item: item[0],
        )
        actual_order = [
            {
                "ordinal": ordinal,
                "prompt_profile": report["prompt_profile"],
                "runner": report["runner"],
                "model": report["model"],
            }
            for ordinal, (_, _, report) in enumerate(
                ordered_intervals,
                start=1,
            )
        ]
        if actual_order != arm_contract["execution_order"]:
            completeness_reasons.append(
                {
                    "code": "arm_execution_order_mismatch",
                    "actual": actual_order,
                    "required": arm_contract["execution_order"],
                    "message": (
                        "report start timestamps do not match the frozen "
                        "execution order"
                    ),
                }
            )
        for (_, previous_completed, previous_report), (
            next_started,
            _,
            next_report,
        ) in zip(ordered_intervals, ordered_intervals[1:]):
            if next_started < previous_completed:
                completeness_reasons.append(
                    {
                        "code": "arm_execution_overlap",
                        "previous": list(
                            report_configuration_key(previous_report)
                        ),
                        "next": list(report_configuration_key(next_report)),
                        "message": (
                            "arm cells must execute sequentially without overlap"
                        ),
                    }
                )
        elapsed_seconds = (
            ordered_intervals[-1][1] - ordered_intervals[0][0]
        ).total_seconds()
        if elapsed_seconds > arm_contract["maximum_matrix_elapsed_seconds"]:
            completeness_reasons.append(
                {
                    "code": "arm_matrix_elapsed_limit_exceeded",
                    "actual": elapsed_seconds,
                    "required": arm_contract["maximum_matrix_elapsed_seconds"],
                    "comparator": "<=",
                    "message": (
                        "the arm matrix exceeded the preregistered completion-time "
                        "window"
                    ),
                }
            )
    arm_prompt_digests = {
        profile: {
            report["prompt_set_sha256"]
            for report in normalized
            if report["prompt_profile"] == profile
        }
        for profile in profiles
    }
    if any(len(values) != 1 for values in arm_prompt_digests.values()) or (
        len({next(iter(values)) for values in arm_prompt_digests.values()}) != len(profiles)
    ):
        completeness_reasons.append(
            {
                "code": "arm_prompt_provenance_mismatch",
                "message": (
                    "each arm must have one shared prompt digest and the three "
                    "profile digests must be distinct"
                ),
            }
        )
    if completeness_reasons:
        return {
            "status": "INCONCLUSIVE",
            "skill_lift_claim_eligible": False,
            "status_reasons": completeness_reasons,
            "metrics": None,
            "claim_policy": claim_policy,
        }

    raw_by_profile = {
        profile: [
            report
            for report in reports
            if report["prompt_profile"] == profile
        ]
        for profile in profiles
    }
    normalized_by_profile = {
        profile: [
            report
            for report in normalized
            if report["prompt_profile"] == profile
        ]
        for profile in profiles
    }
    if protocol_id in RUNNER.SPECIFICITY_PROTOCOL_IDS:
        return decide_specificity_matrix(
            normalized_by_profile, all_cases, protocol,
        )
    treatment_cross_host = compare_reports(
        raw_by_profile[treatment],
        all_cases,
        corpus_sha256,
        protocol,
        protocol_sha256,
        corpus_visibility,
        comparison_scope,
        evaluator_sha256,
    )
    arm_aggregations = {
        profile: provider_family_aggregation(
            profile_reports,
            require_both_families=(
                arm_contract["provider_aggregation"]
                == "mean-within-provider-family-then-equal-weight-families"
            ),
        )
        for profile, profile_reports in normalized_by_profile.items()
    }
    bootstrap = paired_stratified_arm_bootstrap(
        normalized_by_profile,
        all_cases,
        protocol,
    )
    point_metrics = bootstrap["point_metrics"]
    for profile, aggregation in arm_aggregations.items():
        aggregated_values = {
            metric: aggregation["equal_weighted_metrics"][metric]["value"]
            for metric in ARM_POINT_METRICS
        }
        if not equivalent(point_metrics[profile], aggregated_values):
            return {
                "status": "INCONCLUSIVE",
                "skill_lift_claim_eligible": False,
                "status_reasons": [
                    {
                        "code": "arm_metric_recompute_mismatch",
                        "profile": profile,
                        "message": (
                            "case-level and serialized provider-balanced arm "
                            "metrics disagree"
                        ),
                    }
                ],
                "metrics": None,
                "claim_policy": claim_policy,
            }

    if protocol_id in {"reviewer-holdout-v18", "reviewer-holdout-v19"}:
        thresholds = arm_contract["decision"]["thresholds"]
        control = "no-skill"
        delta = point_metrics[treatment]["stable_f1"] - point_metrics[control]["stable_f1"]
        interval = bootstrap["intervals"][control]["stable_f1"]
        checks = [
            threshold_check("stable_f1_delta_min", delta, thresholds["stable_f1_delta_min"], ">="),
            threshold_check("stable_f1_delta_ci95_lower_min_exclusive", interval["lower"],
                            thresholds["stable_f1_delta_ci95_lower_min_exclusive"], ">"),
        ]
        if treatment_cross_host["status"] != "PASS":
            checks.append({"metric": "full_report_status", "actual": treatment_cross_host["status"],
                           "required": "PASS", "comparator": "==", "passed": False})
        passed = all(check["passed"] for check in checks)
        return {
            "status": "PASS" if passed else "FAIL",
            "skill_lift_claim_eligible": passed,
            "status_reasons": [{"code": "release_confirmation_passed" if passed else "release_confirmation_gate_not_met",
                                "failed_checks": [check for check in checks if not check["passed"]]}],
            "metrics": {
                "arm_point_metrics": point_metrics,
                "primary": {"delta": delta, "paired_bootstrap_ci95": interval, "decision_checks": checks},
                "descriptive_full_minus_catalog_only_stable_f1":
                    point_metrics[treatment]["stable_f1"] - point_metrics["catalog-only"]["stable_f1"],
                "descriptive_full_minus_catalog_only": {
                    "point_deltas": {
                        metric: point_metrics[treatment][metric] - point_metrics["catalog-only"][metric]
                        for metric in ARM_POINT_METRICS
                    },
                    "paired_bootstrap_ci95": bootstrap["intervals"]["catalog-only"],
                },
                "historical_v17_full_stable_f1": 0.964,
            },
            "claim_policy": claim_policy,
        }

    if protocol_id == "reviewer-holdout-v17":
        control = "catalog-only"
        formal = "catalog-formal"
        subset_ids = set(protocol["formal_comparison"]["secondary_case_ids"])
        subset = [case for case in all_cases if case["id"] in subset_ids]
        secondary = paired_stratified_arm_bootstrap(
            normalized_by_profile,
            subset,
            protocol,
        )
        delta = point_metrics[formal]["stable_f1"] - point_metrics[control]["stable_f1"]
        lower = bootstrap["intervals"][control]["stable_f1"]["lower"]
        formal_guard = normalized_by_profile[formal][0]["primary_metrics"]["unique"]["stable_guard_hit_rate"]
        control_guard = normalized_by_profile[control][0]["primary_metrics"]["unique"]["stable_guard_hit_rate"]
        checks = [
            threshold_check("stable_f1_delta_min", delta, 0.03, ">="),
            threshold_check("stable_f1_delta_ci95_lower_min_exclusive", lower, 0, ">"),
            threshold_check("stable_guard_hit_rate_delta_max", formal_guard - control_guard, 0, "<="),
        ]
        if treatment_cross_host["status"] != "PASS":
            checks.append({"metric": "formal_report_status", "actual": treatment_cross_host["status"],
                           "required": "PASS", "comparator": "==", "passed": False})
        passed = all(check["passed"] for check in checks)
        return {
            "status": "PASS" if passed else "FAIL",
            "skill_lift_claim_eligible": passed,
            "status_reasons": [{"code": "formal_comparison_passed" if passed else "formal_comparison_gate_not_met",
                                "failed_checks": [check for check in checks if not check["passed"]]}],
            "metrics": {
                "arm_point_metrics": point_metrics,
                "primary": {"delta": delta, "paired_bootstrap_ci95": bootstrap["intervals"][control]["stable_f1"],
                            "formal_guard_hit_rate": formal_guard, "catalog_guard_hit_rate": control_guard,
                            "decision_checks": checks},
                "secondary": {"case_ids": protocol["formal_comparison"]["secondary_case_ids"],
                              "delta": secondary["point_metrics"][formal]["stable_f1"]
                              - secondary["point_metrics"][control]["stable_f1"],
                              "paired_bootstrap_ci95": secondary["intervals"][control]["stable_f1"]},
                "descriptive_full_minus_catalog_only_stable_f1": point_metrics["full"]["stable_f1"]
                    - point_metrics[control]["stable_f1"],
            },
            "claim_policy": claim_policy,
        }

    thresholds = arm_contract["decision"]["thresholds"]
    decision_reasons: list[dict] = []
    if treatment_cross_host["status"] != "PASS":
        decision_reasons.append(
            {
                "code": "treatment_cross_host_not_pass",
                "actual": treatment_cross_host["status"],
                "required": arm_contract["requires_treatment_report_status"],
                "message": (
                    "the full treatment must pass all per-report and cross-host "
                    "development thresholds before a skill-lift claim"
                ),
            }
        )
    lift_rows = {}
    for control in controls:
        deltas = {
            metric: point_metrics[treatment][metric] - point_metrics[control][metric]
            for metric in ARM_POINT_METRICS
        }
        intervals = bootstrap["intervals"][control]
        checks = {
            "stable_f1_delta_min": {
                "actual": deltas["stable_f1"],
                "required": thresholds["stable_f1_delta_min"],
            },
            "stable_f1_delta_ci95_lower_min": {
                "actual": intervals["stable_f1"]["lower"],
                "required": thresholds["stable_f1_delta_ci95_lower_min"],
            },
            "stable_precision_delta_min": {
                "actual": deltas["stable_precision"],
                "required": thresholds["stable_precision_delta_min"],
            },
            "stable_recall_delta_min": {
                "actual": deltas["stable_recall"],
                "required": thresholds["stable_recall_delta_min"],
            },
            "clean_case_specificity_delta_min": {
                "actual": deltas["clean_case_specificity"],
                "required": thresholds["clean_case_specificity_delta_min"],
            },
            "repeated_precision_delta_min": {
                "actual": deltas["repeated_precision"],
                "required": thresholds["repeated_precision_delta_min"],
            },
        }
        decision_checks = []
        for metric, check in checks.items():
            passed = check["actual"] >= check["required"]
            decision_checks.append(
                {
                    "metric": metric,
                    **check,
                    "comparator": ">=",
                    "passed": passed,
                }
            )
            if not passed:
                decision_reasons.append(
                    {
                        "code": "arm_lift_threshold_not_met",
                        "control": control,
                        "metric": metric,
                        **check,
                        "comparator": ">=",
                        "message": (
                            f"full minus {control} {metric} was "
                            f"{check['actual']:.6f}; required >= "
                            f"{check['required']:.6f}"
                        ),
                    }
                )
        lift_rows[control] = {
            "point_deltas": deltas,
            "paired_bootstrap_ci95": intervals,
            "decision_checks": decision_checks,
            "passed": all(check["passed"] for check in decision_checks),
        }

    metrics = {
        "comparison_unit": arm_contract["required_matrix"],
        "provider_aggregation": arm_contract["provider_aggregation"],
        "stability_basis": arm_contract["stability_basis"],
        "execution_order": {
            "design": arm_contract["execution_order_design"],
            "required": arm_contract["execution_order"],
            "observed": actual_order,
            "sequential_non_overlapping_required": arm_contract[
                "requires_sequential_non_overlapping_execution"
            ],
            "elapsed_basis": arm_contract["matrix_elapsed_basis"],
            "elapsed_seconds": elapsed_seconds,
            "maximum_elapsed_seconds": arm_contract[
                "maximum_matrix_elapsed_seconds"
            ],
            "interpretation_limit": arm_contract["temporal_validity_limit"],
        },
        "arms": arm_aggregations,
        "treatment_cross_host": treatment_cross_host,
        "lift": lift_rows,
        "uncertainty": {
            **arm_contract["uncertainty"],
            "intervals": bootstrap["intervals"],
        },
    }
    if decision_reasons:
        return {
            "status": "FAIL",
            "skill_lift_claim_eligible": False,
            "status_reasons": decision_reasons,
            "metrics": metrics,
            "claim_policy": claim_policy,
        }
    return {
        "status": "PASS",
        "skill_lift_claim_eligible": True,
        "status_reasons": [
            {
                "code": "all_arm_lift_thresholds_met",
                "message": (
                    "the complete treatment matrix passed absolute, cross-host, "
                    "paired-lift, and uncertainty gates against every control"
                ),
            }
        ],
        "metrics": metrics,
        "claim_policy": claim_policy,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--compare-arms",
        action="store_true",
        help=(
            "compare the frozen full/catalog-only/no-skill matrix; requires one "
            "report for every preregistered profile and host"
        ),
    )
    parser.add_argument(
        "--evidence-scope",
        choices=("development", "release"),
        default="development",
        help=(
            "development re-derives metrics but cannot produce release evidence; "
            "release requires signed isolation-attestation verification"
        ),
    )
    args = parser.parse_args()

    comparator_path = Path(__file__).resolve()
    comparator_sha256 = sha256_file(comparator_path)
    evaluator_sha256 = RUNNER.evaluator_digest()
    if evaluator_sha256 != EVALUATOR_SHA256_AT_IMPORT:
        parser.error("the evaluator changed while the comparator was starting")
    cases_path = args.cases.expanduser().resolve()
    protocol_path = args.protocol.expanduser().resolve()
    snapshot_handle = tempfile.TemporaryDirectory(
        prefix="e2e-reviewer-comparison-inputs-"
    )
    snapshot_root = Path(snapshot_handle.name)
    protocol_sha256, protocol_payload = descriptor_sha256(
        protocol_path,
        MAX_REPORT_BYTES,
    )
    snapshot_protocol_path = snapshot_root / protocol_path.name
    write_snapshot_file(snapshot_protocol_path, protocol_payload)
    protocol = RUNNER.load_protocol(snapshot_protocol_path)
    protocol_id = protocol.get("protocol_id")
    adjudication_ledger_path = (
        RUNNER.specificity_ledger_path(protocol)
        if protocol_id in RUNNER.ADJUDICATED_SPECIFICITY_PROTOCOL_IDS else None
    )
    repository_walk_path = (
        RUNNER.specificity_repository_walk_path(protocol)
        if protocol_id in {"reviewer-specificity-v3", "reviewer-specificity-v4"} else None
    )
    snapshot_cases_path, corpus_input_digests = snapshot_corpus_inputs(
        cases_path,
        snapshot_root,
    )
    if protocol_id in RUNNER.SUPERSEDED_PROTOCOL_IDS:
        parser.error(
            f"{protocol_id} was superseded before run and cannot produce "
            "benchmark comparisons; use reviewer-specificity-v3"
        )
    if protocol_id == "reviewer-specificity-v4":
        parser.error("specificity-v4 has an infeasible selection contract; no benchmark comparison is permitted")
    if protocol_id in RUNNER.HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS:
        parser.error(
            f"{protocol_id} is frozen historical diagnostic evidence "
            "with a known-invalid oracle and cannot produce a benchmark comparison"
        )
    if protocol_id in RUNNER.REVISION_COMPARISON_PROTOCOL_IDS:
        parser.error(
            f"{protocol_id} decides on a before/after skill-revision comparison; "
            "use scripts/evals/compare-reviewer-revisions.py"
        )
    if args.compare_arms and not isinstance(protocol.get("arm_comparison"), dict):
        parser.error("selected protocol has no frozen arm-comparison contract")
    decision = protocol.get("cross_host_decision")
    expected_thresholds = {
        "stable_recall_gap_max",
        "stable_prediction_jaccard_min",
    }
    if protocol_id not in RUNNER.SPECIFICITY_PROTOCOL_IDS and (
        not isinstance(decision, dict)
        or decision.get("threshold_basis") != "point-estimate"
        or decision.get("requires_each_report_status") != "PASS"
        or set(decision.get("thresholds", {})) != expected_thresholds
    ):
        parser.error("protocol has no valid preregistered cross-host decision")

    report_paths = [
        Path(os.path.abspath(os.fspath(path.expanduser())))
        for path in args.reports
    ]
    output_path = args.output.expanduser().resolve() if args.output else None
    protected_output_paths = {
        comparator_path,
        RUNNER_PATH.resolve(),
        cases_path,
        protocol_path,
        *report_paths,
        *corpus_input_digests,
        *(path.resolve() for path in RUNNER.skill_files(RUNNER.DEFAULT_SKILL_DIR)),
        (ROOT / "scripts/ci/lib/strict_json.py").resolve(),
        (ROOT / "scripts/evals/eval_security.py").resolve(),
        *([adjudication_ledger_path.resolve()] if adjudication_ledger_path else []),
        *([repository_walk_path.resolve()] if repository_walk_path else []),
    }
    if output_path in protected_output_paths:
        parser.error("comparison output must not overwrite a benchmark input")
    report_sha256s = [
        descriptor_sha256(path, MAX_REPORT_BYTES)[0]
        for path in report_paths
    ]
    reports = [load_report(path) for path in report_paths]
    report_sha256s_after = [
        descriptor_sha256(path, MAX_REPORT_BYTES)[0]
        for path in report_paths
    ]
    if report_sha256s_after != report_sha256s:
        parser.error("an input report changed while the comparison was running")
    metadata, all_cases = RUNNER.load_cases(snapshot_cases_path)
    try:
        RUNNER.validate_corpus_protocol_pairing(
            metadata,
            protocol,
            RUNNER.corpus_digest(snapshot_cases_path, all_cases),
        )
    except ValueError as exc:
        parser.error(str(exc))
    if protocol_id in RUNNER.SPECIFICITY_PROTOCOL_IDS:
        RUNNER.validate_specificity_cases(
            all_cases, str(snapshot_cases_path), protocol, snapshot_cases_path,
        )
    if protocol_id in RUNNER.ADJUDICATED_SPECIFICITY_PROTOCOL_IDS:
        RUNNER.validate_specificity_adjudication_ledger(
            all_cases, snapshot_cases_path, protocol, adjudication_ledger_path,
        )
        ledger_sha256 = sha256_file(adjudication_ledger_path)
        if any(report.get("adjudication_ledger_sha256") != ledger_sha256
               for report in reports):
            parser.error("report adjudication ledger digest does not match current ledger")
    if protocol_id in {"reviewer-specificity-v3", "reviewer-specificity-v4"}:
        RUNNER.validate_specificity_repository_walk(protocol, repository_walk_path)
        walk_sha256 = sha256_file(repository_walk_path)
        if any(report.get("repository_walk_sha256") != walk_sha256 for report in reports):
            parser.error("report repository walk digest does not match current walk")
    selected_corpus_sha256 = RUNNER.corpus_digest(
        snapshot_cases_path,
        all_cases,
    )
    comparison = compare_arm_reports if args.compare_arms else compare_reports
    result = comparison(
        reports,
        all_cases,
        selected_corpus_sha256,
        protocol,
        protocol_sha256,
        metadata.get("corpus_visibility", "unspecified"),
        args.evidence_scope,
        evaluator_sha256,
    )
    report_sha256s_final = [
        descriptor_sha256(path, MAX_REPORT_BYTES)[0]
        for path in report_paths
    ]
    if report_sha256s_final != report_sha256s:
        parser.error("an input report changed while the comparison was running")
    try:
        final_protocol_sha256, _ = descriptor_sha256(
            protocol_path,
            MAX_REPORT_BYTES,
        )
        verify_input_digests(corpus_input_digests)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.error(f"benchmark inputs became unreadable during comparison: {exc}")
    if final_protocol_sha256 != protocol_sha256:
        parser.error("the protocol or corpus changed while comparison was running")
    if sha256_file(comparator_path) != comparator_sha256:
        parser.error("the comparator changed while the comparison was running")
    try:
        verify_evaluator_digest(evaluator_sha256)
    except ValueError as exc:
        parser.error(str(exc))
    snapshot_handle.cleanup()
    output = {
        "schema_version": 1,
        "comparator_sha256": comparator_sha256,
        "evaluator_sha256": evaluator_sha256,
        "comparison_mode": "arm-matrix" if args.compare_arms else "cross-host",
        "skill_lift_claim_eligible": result.get(
            "skill_lift_claim_eligible",
            False,
        ),
        "evidence_scope": args.evidence_scope,
        "release_eligible": False,
        "protocol_id": protocol_id,
        "protocol_sha256": protocol_sha256,
        "corpus_sha256": selected_corpus_sha256,
        "reports": [RUNNER.portable_host_path(path) for path in report_paths],
        "report_inputs": [
            {"path": RUNNER.portable_host_path(path), "sha256": digest}
            for path, digest in zip(report_paths, report_sha256s)
        ],
        "prompt_profiles": sorted(
            {report["prompt_profile"] for report in reports}
        ),
        **result,
    }
    output.update(per_report_sections(protocol, reports))
    if output_path is not None:
        write_json_atomic(output_path, output)
    print(json.dumps(output, sort_keys=True))
    if result["status"] == "PASS":
        return 0
    if args.compare_arms and result["status"] == "INCONCLUSIVE":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
