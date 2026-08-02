#!/usr/bin/env python3
"""Run the public F1-F15 debugger holdout with a prompt-complete zero-tool model call."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "scripts/evals/debugger-holdout-v1.json"
DEFAULT_PROTOCOL = ROOT / "scripts/evals/debugger-validation-protocol-v1.json"
STRICT_JSON_PATH = ROOT / "scripts/ci/lib/strict_json.py"
SHARED_RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
FRAMEWORK_SKILLS = {
    "playwright": ROOT / "skills/playwright-debugger/SKILL.md",
    "cypress": ROOT / "skills/cypress-debugger/SKILL.md",
}
CORPUS_KEYS = {"schema_version", "corpus_id", "status", "description", "cases"}
CASE_KEYS = {"id", "framework", "artifact", "expected"}
ARTIFACT_KEYS = {"source", "sha256"}
EXPECTED_KEYS = {
    "f_code",
    "confidence",
    "diagnosis",
    "product_impact",
    "test_reliability_urgency",
    "test_quality_severity",
}
PREDICTION_KEYS = {*EXPECTED_KEYS, "root_cause"}
F_CODES = {f"F{number}" for number in range(1, 16)}
CONFIDENCES = {"high", "medium", "low"}
DIAGNOSES = {"product_regression", "test_defect", "unknown"}
PRODUCT_IMPACTS = {"none", "low", "medium", "high", "critical", "unknown"}
URGENCIES = {"critical", "high", "medium", "low"}
SEVERITIES = {"P0", "P1", "P2", "N/A"}
PINNED_CASES_SHA256 = "17a3efeb8fc812ce250a4b25254cafb95f5d7dc51e96c10481fed3d39bb59f5c"
PINNED_PROTOCOL_SHA256 = "53635f244ca17223ba159afcd507e94420c381a78b479b6f4074b68070f7200c"
STATUS_EXIT_CODES = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}
sys.path.insert(0, str(STRICT_JSON_PATH.parent))
import strict_json as STRICT_JSON


def load_python_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strict_load(path: Path, context: str) -> Any:
    try:
        return STRICT_JSON.load_strict(path)
    except STRICT_JSON.StrictJsonError as exc:
        raise ValueError(str(exc)) from exc


def strict_loads(text: str, context: str) -> Any:
    try:
        return STRICT_JSON.loads_strict(text, context=context)
    except STRICT_JSON.StrictJsonError as exc:
        raise ValueError(str(exc)) from exc


def require_exact_keys(value: object, keys: set[str], context: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{context} must contain exactly: {', '.join(sorted(keys))}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact_canonical_path(requested: Path, expected: Path) -> bool:
    lexical = Path(os.path.abspath(os.fspath(requested.expanduser())))
    try:
        resolved = requested.expanduser().resolve(strict=True)
    except OSError:
        return False
    return lexical == expected and resolved == expected


def is_pinned_builtin_input(cases_path: Path, protocol_path: Path) -> bool:
    return bool(
        exact_canonical_path(cases_path, DEFAULT_CASES)
        and exact_canonical_path(protocol_path, DEFAULT_PROTOCOL)
        and sha256(cases_path) == PINNED_CASES_SHA256
        and sha256(protocol_path) == PINNED_PROTOCOL_SHA256
    )


def safe_source_path(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{context} must stay inside scripts/evals")
    if not value.startswith("files/debugger-holdout-v1/"):
        raise ValueError(f"{context} must use the debugger holdout source root")
    return path.as_posix()


def validate_expected(value: object, context: str) -> dict:
    expected = require_exact_keys(value, EXPECTED_KEYS, context)
    checks = (
        ("f_code", F_CODES),
        ("confidence", CONFIDENCES),
        ("diagnosis", DIAGNOSES),
        ("product_impact", PRODUCT_IMPACTS),
        ("test_reliability_urgency", URGENCIES),
        ("test_quality_severity", SEVERITIES),
    )
    for field, allowed in checks:
        if expected[field] not in allowed:
            raise ValueError(f"{context}.{field} is invalid")
    if expected["diagnosis"] != "test_defect" and expected["test_quality_severity"] != "N/A":
        raise ValueError(f"{context}: non-test diagnoses require N/A test severity")
    return dict(expected)


def load_corpus(path: Path = DEFAULT_CASES) -> dict:
    corpus = require_exact_keys(strict_load(path, "debugger corpus"), CORPUS_KEYS, "debugger corpus")
    if corpus["schema_version"] != 1 or corpus["corpus_id"] != "debugger-holdout-v1":
        raise ValueError("unsupported debugger corpus")
    if not isinstance(corpus["cases"], list) or not corpus["cases"]:
        raise ValueError("debugger corpus cases must be a non-empty list")
    case_ids: set[str] = set()
    sources: set[str] = set()
    validated_cases = []
    for index, value in enumerate(corpus["cases"]):
        case = require_exact_keys(value, CASE_KEYS, f"case {index}")
        case_id = case["id"]
        if (
            not isinstance(case_id, str)
            or len(case_id) != 8
            or not case_id.startswith("case-")
            or not case_id[5:].isdigit()
            or case_id in case_ids
        ):
            raise ValueError(f"case {index} has an invalid or duplicate id")
        case_ids.add(case_id)
        if case["framework"] not in FRAMEWORK_SKILLS:
            raise ValueError(f"{case_id} has an unsupported framework")
        artifact = require_exact_keys(case["artifact"], ARTIFACT_KEYS, f"{case_id}.artifact")
        source = safe_source_path(artifact["source"], f"{case_id}.artifact.source")
        if source in sources:
            raise ValueError(f"{case_id} reuses an artifact")
        sources.add(source)
        digest = artifact["sha256"]
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"{case_id} has an invalid artifact digest")
        source_root = path.parent.resolve(strict=True)
        source_path = source_root / source
        resolved_source = source_path.resolve(strict=True)
        try:
            resolved_source.relative_to(source_root)
        except ValueError as exc:
            raise ValueError(f"{case_id} artifact escapes the corpus root") from exc
        cursor = source_root
        has_symlink_component = False
        for component in PurePosixPath(source).parts:
            cursor = cursor / component
            if cursor.is_symlink():
                has_symlink_component = True
                break
        if (
            resolved_source != source_path
            or has_symlink_component
            or not source_path.is_file()
        ):
            raise ValueError(f"{case_id} artifact is not a regular file")
        if sha256(source_path) != digest:
            raise ValueError(f"{case_id} artifact digest mismatch")
        artifact_payload = strict_load(source_path, f"{case_id} artifact")
        if (
            not isinstance(artifact_payload, dict)
            or artifact_payload.get("framework") != case["framework"]
        ):
            raise ValueError(f"{case_id} artifact framework mismatch")
        validated_cases.append(
            {
                "id": case_id,
                "framework": case["framework"],
                "artifact": {"source": source, "sha256": digest},
                "expected": validate_expected(case["expected"], f"{case_id}.expected"),
            }
        )
    return {**corpus, "cases": validated_cases}


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict:
    protocol = require_exact_keys(
        strict_load(path, "debugger protocol"),
        {
            "schema_version",
            "protocol_id",
            "evidence_scope",
            "default_repetitions",
            "seed",
            "host_matrix",
            "stability",
            "confidence_intervals",
            "cross_host_comparison",
            "execution_identity",
            "thresholds",
            "limitations",
        },
        "debugger protocol",
    )
    if (
        protocol["schema_version"] != 1
        or protocol["protocol_id"] != "debugger-holdout-v1"
    ):
        raise ValueError("unsupported debugger protocol")
    if protocol["evidence_scope"] != "public-pre-publication-development":
        raise ValueError("debugger protocol must remain development-only")
    if (
        isinstance(protocol["seed"], bool)
        or not isinstance(protocol["seed"], int)
        or protocol["seed"] < 0
    ):
        raise ValueError("debugger protocol seed must be a non-negative integer")
    repetitions = protocol.get("default_repetitions")
    if repetitions != 3:
        raise ValueError("debugger protocol requires exactly three repetitions")
    stability = require_exact_keys(
        protocol["stability"],
        {"rule", "repetitions", "classification_fields"},
        "debugger protocol.stability",
    )
    if (
        stability["rule"] != "strict-majority"
        or stability["repetitions"] != repetitions
        or stability["classification_fields"] != sorted(EXPECTED_KEYS)
    ):
        raise ValueError("debugger protocol stability contract is invalid")
    confidence = require_exact_keys(
        protocol["confidence_intervals"],
        {"method", "confidence", "unit"},
        "debugger protocol.confidence_intervals",
    )
    if confidence != {"method": "wilson", "confidence": 0.95, "unit": "unique_case"}:
        raise ValueError("debugger protocol confidence interval contract is invalid")
    cross_host = require_exact_keys(
        protocol["cross_host_comparison"],
        {"matrix_required", "provider_family_balance_required", "aggregation"},
        "debugger protocol.cross_host_comparison",
    )
    if cross_host != {
        "matrix_required": True,
        "provider_family_balance_required": True,
        "aggregation": "equal-provider-family-weight",
    }:
        raise ValueError("debugger protocol cross-host contract is invalid")
    execution_identity = require_exact_keys(
        protocol["execution_identity"],
        {"require_explicit_runner_path", "expected_cli_versions", "attestation_limit"},
        "debugger protocol.execution_identity",
    )
    if execution_identity != {
        "require_explicit_runner_path": True,
        "expected_cli_versions": {
            "codex": "codex-cli 0.146.0",
            "claude": "Claude Code 2.1.220",
        },
        "attestation_limit": (
            "The explicit canonical path, binary digest, and version output are "
            "provenance evidence, not cryptographic attestation."
        ),
    }:
        raise ValueError("debugger protocol execution identity contract is invalid")
    expected_hosts = {
        ("codex", "gpt-5.6-sol", "openai"),
        ("claude", "claude-opus-5", "anthropic"),
        ("claude", "claude-fable-5", "anthropic"),
    }
    hosts = set()
    if not isinstance(protocol["host_matrix"], list):
        raise ValueError("debugger protocol.host_matrix must be an array")
    for index, entry in enumerate(protocol["host_matrix"]):
        host = require_exact_keys(
            entry,
            {"runner", "model", "provider_family"},
            f"debugger protocol.host_matrix[{index}]",
        )
        hosts.add((host["runner"], host["model"], host["provider_family"]))
    if hosts != expected_hosts or len(protocol["host_matrix"]) != len(expected_hosts):
        raise ValueError("debugger protocol host_matrix must be the fixed balanced matrix")
    threshold_keys = {
        "unique_f_code_accuracy_min",
        "unique_f_code_wilson_lower_min",
        "unique_stable_case_rate_min",
        "unique_diagnosis_accuracy_min",
        "unique_axis_exact_match_min",
        "repeated_f_code_accuracy_min",
        "repeated_macro_precision_min",
        "worst_framework_unique_accuracy_min",
        "worst_category_unique_accuracy_min",
        "invalid_output_rate_max",
    }
    thresholds = require_exact_keys(
        protocol["thresholds"], threshold_keys, "debugger protocol.thresholds"
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0.0 <= value <= 1.0
        for value in thresholds.values()
    ):
        raise ValueError("debugger protocol thresholds must be numbers from zero to one")
    if not isinstance(protocol["limitations"], list) or not all(
        isinstance(item, str) and item for item in protocol["limitations"]
    ):
        raise ValueError("debugger protocol limitations must be non-empty strings")
    return protocol


def validate_host_pair(protocol: dict, runner: str, model: str | None) -> None:
    allowed = {
        (entry.get("runner"), entry.get("model"))
        for entry in protocol.get("host_matrix", [])
        if isinstance(entry, dict)
    }
    if (runner, model) not in allowed:
        rendered = ", ".join(f"{host}/{name}" for host, name in sorted(allowed))
        raise ValueError(
            f"runner/model must exactly match the protocol host_matrix: {rendered}"
        )


def select_repetitions(requested: int | None, default: int) -> int:
    repetitions = default if requested is None else requested
    if isinstance(repetitions, bool) or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    return repetitions


def copy_snapshot_file(source: Path, destination: Path) -> dict:
    lexical_source = Path(os.path.abspath(os.fspath(source)))
    source = source.resolve(strict=True)
    if lexical_source != source:
        raise ValueError(f"snapshot source path is not canonical: {lexical_source}")
    before = source.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"snapshot source is not a regular file: {source}")
    before_digest = sha256(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    after = source.stat()
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        or sha256(source) != before_digest
    ):
        destination.unlink(missing_ok=True)
        raise ValueError(f"snapshot source changed while copying: {source}")
    if destination.is_symlink() or not destination.is_file() or sha256(destination) != before_digest:
        destination.unlink(missing_ok=True)
        raise ValueError(f"snapshot copy verification failed: {destination}")
    return {
        "source_path": str(source),
        "snapshot_path": str(destination.resolve(strict=True)),
        "sha256": before_digest,
        "source_pre_sha256": before_digest,
        "snapshot_pre_sha256": before_digest,
    }


def snapshot_inputs(
    cases_path: Path,
    protocol_path: Path,
    skill_paths: dict[str, Path],
    snapshot_root: Path,
) -> dict:
    """Copy every prompt/evaluator input once and return a verified manifest."""
    original_corpus = load_corpus(cases_path)
    load_protocol(protocol_path)
    manifest: dict[str, dict] = {}
    snapshot_cases = snapshot_root / cases_path.name
    snapshot_protocol = snapshot_root / protocol_path.name
    manifest["corpus"] = copy_snapshot_file(cases_path, snapshot_cases)
    manifest["protocol"] = copy_snapshot_file(protocol_path, snapshot_protocol)
    snapshot_skills: dict[str, Path] = {}
    for framework, source in sorted(skill_paths.items()):
        destination = snapshot_root / "skills" / framework / "SKILL.md"
        manifest[f"skill:{framework}"] = copy_snapshot_file(source, destination)
        snapshot_skills[framework] = destination
    for case in original_corpus["cases"]:
        relative = case["artifact"]["source"]
        source = cases_path.parent / relative
        destination = snapshot_root / relative
        manifest[f"artifact:{case['id']}"] = copy_snapshot_file(source, destination)

    snapshot = {
        "root": snapshot_root,
        "cases_path": snapshot_cases,
        "protocol_path": snapshot_protocol,
        "skill_paths": snapshot_skills,
        "manifest": manifest,
    }
    load_corpus(snapshot_cases)
    load_protocol(snapshot_protocol)
    verify_snapshot(snapshot)
    return snapshot


def verify_snapshot(snapshot: dict) -> None:
    for name, entry in snapshot["manifest"].items():
        source = Path(entry["source_path"])
        staged = Path(entry["snapshot_path"])
        if (
            not source.is_file()
            or source.is_symlink()
            or sha256(source) != entry["sha256"]
        ):
            raise ValueError(f"original input drifted after snapshot: {name}")
        if (
            not staged.is_file()
            or staged.is_symlink()
            or sha256(staged) != entry["sha256"]
        ):
            raise ValueError(f"snapshot input drifted during run: {name}")


def snapshot_post_digests(snapshot: dict) -> dict[str, dict[str, str]]:
    return {
        name: {
            "source_sha256": sha256(Path(entry["source_path"])),
            "snapshot_sha256": sha256(Path(entry["snapshot_path"])),
        }
        for name, entry in sorted(snapshot["manifest"].items())
    }


def validate_isolation_wrapper(path: Path) -> Path:
    lexical = Path(os.path.abspath(os.fspath(path.expanduser())))
    resolved = path.expanduser().resolve(strict=True)
    metadata = resolved.stat()
    if (
        lexical != resolved
        or path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or not os.access(resolved, os.X_OK)
    ):
        raise ValueError("isolation wrapper must be an exact executable regular file")
    return resolved


def isolation_prefix_for_inputs(
    cases_path: Path,
    protocol_path: Path,
    wrapper: Path | None,
) -> list[str] | None:
    if wrapper is None:
        if not is_pinned_builtin_input(cases_path, protocol_path):
            raise ValueError(
                "custom or drifted inputs require --isolation-wrapper; "
                "wrapper-free calls are pinned to the built-in corpus and protocol"
            )
        return None
    return [str(validate_isolation_wrapper(wrapper))]


def render_prompt(framework: str, artifact_text: str, skill_text: str) -> str:
    if framework not in FRAMEWORK_SKILLS:
        raise ValueError("unsupported framework")
    return f"""You are classifying one already-observed {framework} E2E failure.

Use only the skill contract and sanitized report excerpt embedded below. You have
no tools. Do not infer hidden files or claim that you ran a command. Classify the
observed failure mechanism independently from whether the product or test is at
fault.

Return exactly one JSON object and no markdown or surrounding prose:
{{
  "f_code": "F1 through F15",
  "confidence": "high|medium|low",
  "diagnosis": "product_regression|test_defect|unknown",
  "product_impact": "none|low|medium|high|critical|unknown",
  "test_reliability_urgency": "critical|high|medium|low",
  "test_quality_severity": "P0|P1|P2|N/A",
  "root_cause": "one concise evidence-grounded sentence"
}}

Use test-quality severity only for a confirmed test_defect. Otherwise use N/A.

<skill_contract>
{skill_text}
</skill_contract>

<sanitized_report_excerpt>
{artifact_text}
</sanitized_report_excerpt>
"""


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_schedule(cases: list[dict], repetitions: int, seed: int) -> list[dict]:
    schedule = [
        {"case_id": case["id"], "repetition": repetition + 1}
        for repetition in range(repetitions)
        for case in cases
    ]
    random.Random(seed).shuffle(schedule)
    return [
        {"ordinal": ordinal, **entry}
        for ordinal, entry in enumerate(schedule, start=1)
    ]


def prompt_set_digest(
    cases: list[dict],
    cases_path: Path,
    skill_paths: dict[str, Path],
) -> str:
    prompts = {}
    skill_texts = {
        framework: path.read_text(encoding="utf-8")
        for framework, path in skill_paths.items()
    }
    for case in cases:
        artifact = cases_path.parent / case["artifact"]["source"]
        prompts[case["id"]] = render_prompt(
            case["framework"],
            artifact.read_text(encoding="utf-8"),
            skill_texts[case["framework"]],
        )
    return canonical_digest(prompts)


def parse_prediction(output: str) -> dict:
    if not isinstance(output, str) or not output.strip():
        raise ValueError("model output is empty")
    payload = require_exact_keys(strict_loads(output.strip(), "model output"), PREDICTION_KEYS, "model output")
    prediction = validate_expected(
        {field: payload[field] for field in EXPECTED_KEYS},
        "model output",
    )
    root_cause = payload["root_cause"]
    if not isinstance(root_cause, str) or not root_cause.strip() or len(root_cause) > 1000:
        raise ValueError("model output.root_cause must be a concise non-empty string")
    return {**prediction, "root_cause": root_cause.strip()}


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def macro_precision(rows: list[tuple[str | None, str]]) -> float:
    """Return macro precision over expected classes, counting invalids as no prediction."""
    expected_codes = sorted({expected for _, expected in rows})
    if not expected_codes:
        return 0.0
    precisions = []
    for code in expected_codes:
        true_positive = sum(
            predicted == code and expected == code for predicted, expected in rows
        )
        predicted_positive = sum(predicted == code for predicted, _ in rows)
        precisions.append(
            true_positive / predicted_positive if predicted_positive else 0.0
        )
    return mean(precisions)


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> dict:
    """Return a two-sided Wilson 95% interval for independent unique cases."""
    if (
        isinstance(successes, bool)
        or isinstance(total, bool)
        or not isinstance(successes, int)
        or not isinstance(total, int)
        or total < 1
        or successes < 0
        or successes > total
    ):
        raise ValueError("Wilson interval requires 0 <= successes <= total")
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return {"lower": max(0.0, center - margin), "upper": min(1.0, center + margin)}


def classification_signature(prediction: dict) -> tuple:
    return tuple(prediction[field] for field in sorted(EXPECTED_KEYS))


def strict_majority_prediction(records: list[dict]) -> dict | None:
    valid = [record["prediction"] for record in records if record.get("valid")]
    counts = Counter(classification_signature(prediction) for prediction in valid)
    if not counts:
        return None
    signature, hits = counts.most_common(1)[0]
    if hits <= len(records) / 2:
        return None
    fields = sorted(EXPECTED_KEYS)
    return dict(zip(fields, signature))


def _worst_slice(
    hits: dict[str, list[float]], label: str
) -> dict[str, object]:
    rows = [
        {
            label: key,
            "accuracy": mean(values),
            "cases": len(values),
        }
        for key, values in sorted(hits.items())
    ]
    if not rows:
        return {label: None, "accuracy": 0.0, "cases": 0}
    return min(rows, key=lambda row: (row["accuracy"], str(row[label])))


def score_predictions(records: list[dict]) -> dict:
    total = len(records)
    valid = sum(bool(record.get("valid")) for record in records)
    code_hits = 0
    diagnosis_hits = 0
    axis_hits = 0
    framework_hits: dict[str, list[float]] = defaultdict(list)
    category_hits: dict[str, list[float]] = defaultdict(list)
    repeated_precision_rows: list[tuple[str | None, str]] = []
    records_by_case: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        expected = record["case"]["expected"]
        prediction = record.get("prediction", {})
        code_hit = bool(record.get("valid")) and prediction.get("f_code") == expected["f_code"]
        diagnosis_hit = bool(record.get("valid")) and prediction.get("diagnosis") == expected["diagnosis"]
        axis_hit = bool(record.get("valid")) and all(
            prediction.get(field) == expected[field] for field in EXPECTED_KEYS
        )
        code_hits += int(code_hit)
        diagnosis_hits += int(diagnosis_hit)
        axis_hits += int(axis_hit)
        framework_hits[record["case"]["framework"]].append(float(code_hit))
        category_hits[expected["f_code"]].append(float(code_hit))
        repeated_precision_rows.append(
            (prediction.get("f_code") if record.get("valid") else None, expected["f_code"])
        )
        records_by_case[record["case"]["id"]].append(record)

    unique_code_hits = 0
    unique_diagnosis_hits = 0
    unique_axis_hits = 0
    stable_cases = 0
    unique_framework_hits: dict[str, list[float]] = defaultdict(list)
    unique_category_hits: dict[str, list[float]] = defaultdict(list)
    unique_precision_rows: list[tuple[str | None, str]] = []
    for case_id in sorted(records_by_case):
        case_records = records_by_case[case_id]
        case = case_records[0]["case"]
        expected = case["expected"]
        majority = strict_majority_prediction(case_records)
        stable = majority is not None
        stable_cases += int(stable)
        code_hit = stable and majority["f_code"] == expected["f_code"]
        diagnosis_hit = stable and majority["diagnosis"] == expected["diagnosis"]
        axis_hit = stable and all(
            majority[field] == expected[field] for field in EXPECTED_KEYS
        )
        unique_code_hits += int(code_hit)
        unique_diagnosis_hits += int(diagnosis_hit)
        unique_axis_hits += int(axis_hit)
        unique_framework_hits[case["framework"]].append(float(code_hit))
        unique_category_hits[expected["f_code"]].append(float(code_hit))
        unique_precision_rows.append(
            (majority["f_code"] if stable else None, expected["f_code"])
        )

    total_cases = len(records_by_case)
    unique_accuracy = unique_code_hits / total_cases if total_cases else 0.0
    stable_rate = stable_cases / total_cases if total_cases else 0.0
    repeated = {
        "f_code_accuracy": code_hits / total if total else 0.0,
        "macro_precision": macro_precision(repeated_precision_rows),
        "diagnosis_accuracy": diagnosis_hits / total if total else 0.0,
        "axis_exact_match": axis_hits / total if total else 0.0,
        "framework_accuracy": {
            framework: mean(hits) for framework, hits in sorted(framework_hits.items())
        },
        "category_macro_recall": mean(
            [mean(category_hits[code]) for code in sorted(category_hits)]
        ),
    }
    unique = {
        "total_cases": total_cases,
        "stable_cases": stable_cases,
        "stable_case_rate": stable_rate,
        "stable_case_rate_wilson_95": (
            wilson_interval(stable_cases, total_cases) if total_cases else None
        ),
        "f_code_accuracy": unique_accuracy,
        "f_code_accuracy_wilson_95": (
            wilson_interval(unique_code_hits, total_cases) if total_cases else None
        ),
        "macro_precision": macro_precision(unique_precision_rows),
        "diagnosis_accuracy": (
            unique_diagnosis_hits / total_cases if total_cases else 0.0
        ),
        "axis_exact_match": unique_axis_hits / total_cases if total_cases else 0.0,
        "framework_accuracy": {
            framework: mean(hits)
            for framework, hits in sorted(unique_framework_hits.items())
        },
        "category_recall": {
            code: mean(hits) for code, hits in sorted(unique_category_hits.items())
        },
        "category_macro_recall": mean(
            [mean(unique_category_hits[code]) for code in sorted(unique_category_hits)]
        ),
    }
    return {
        "total_calls": total,
        "valid_calls": valid,
        "invalid_output_rate": (total - valid) / total if total else 1.0,
        "repeated": repeated,
        "unique_cases": unique,
        "worst_slices": {
            "framework": _worst_slice(unique_framework_hits, "framework"),
            "category": _worst_slice(unique_category_hits, "category"),
        },
    }


def thresholds_pass(score: dict, thresholds: dict) -> bool:
    repeated = score["repeated"]
    unique = score["unique_cases"]
    framework_floor = score["worst_slices"]["framework"]["accuracy"]
    category_floor = score["worst_slices"]["category"]["accuracy"]
    wilson_lower = unique["f_code_accuracy_wilson_95"]["lower"]
    return bool(
        unique["f_code_accuracy"] >= thresholds["unique_f_code_accuracy_min"]
        and wilson_lower >= thresholds["unique_f_code_wilson_lower_min"]
        and unique["stable_case_rate"] >= thresholds["unique_stable_case_rate_min"]
        and unique["diagnosis_accuracy"]
        >= thresholds["unique_diagnosis_accuracy_min"]
        and unique["axis_exact_match"] >= thresholds["unique_axis_exact_match_min"]
        and repeated["f_code_accuracy"]
        >= thresholds["repeated_f_code_accuracy_min"]
        and repeated["macro_precision"]
        >= thresholds["repeated_macro_precision_min"]
        and framework_floor
        >= thresholds["worst_framework_unique_accuracy_min"]
        and category_floor >= thresholds["worst_category_unique_accuracy_min"]
        and score["invalid_output_rate"] <= thresholds["invalid_output_rate_max"]
    )


def derive_status(
    execution_complete: bool,
    input_integrity_verified: bool,
    infrastructure_errors: list[str],
    score: dict,
    thresholds: dict,
) -> str:
    if (
        not execution_complete
        or not input_integrity_verified
        or infrastructure_errors
    ):
        return "INCONCLUSIVE"
    return "PASS" if thresholds_pass(score, thresholds) else "FAIL"


def workspace_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for candidate in sorted(path.rglob("*")):
        metadata = candidate.lstat()
        digest.update(candidate.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(stat.S_IMODE(metadata.st_mode)).encode("ascii"))
        digest.update(b"\0")
        if stat.S_ISDIR(metadata.st_mode):
            digest.update(b"directory")
        elif stat.S_ISREG(metadata.st_mode):
            digest.update(b"file\0")
            digest.update(candidate.read_bytes())
        else:
            raise ValueError("workspace contains a non-regular file")
        digest.update(b"\0")
    return digest.hexdigest()


def load_shared_runner():
    return load_python_module("debugger_holdout_shared_runner", SHARED_RUNNER_PATH)


def validate_runner_path(path: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise ValueError("runner path must be an explicit absolute canonical path")
    if ".." in expanded.parts:
        raise ValueError(
            "runner path must be canonical and must not contain symlinks or traversal"
        )
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"runner path cannot be resolved: {expanded}") from exc
    if expanded != resolved:
        raise ValueError(
            "runner path must be canonical and must not contain symlinks or traversal"
        )
    metadata = resolved.stat()
    if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
        raise ValueError("runner executable is not an executable regular file")
    return resolved


def runner_identity_matches(runner: str, actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    if runner == "claude":
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+){2}) \(Claude Code\)", actual)
        return bool(match and expected == f"Claude Code {match.group(1)}")
    return False


def runner_cli_identity(
    runner: str,
    runner_path: Path,
    expected_version: str,
) -> tuple[str, dict]:
    executable = validate_runner_path(runner_path)
    metadata = executable.stat()
    completed = subprocess.run(
        [str(executable), "--version"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=15,
        check=False,
        env={
            "PATH": f"{executable.parent}:/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
        },
    )
    version_output = completed.stdout.strip()
    if completed.returncode != 0 or not version_output:
        raise ValueError("runner --version identity probe failed")
    if not runner_identity_matches(runner, version_output, expected_version):
        raise ValueError(
            f"runner identity {version_output!r} does not match "
            f"the protocol identity {expected_version!r}"
        )
    return str(executable), {
        "path": str(executable),
        "sha256": sha256(executable),
        "size_bytes": metadata.st_size,
        "version_output": version_output[:500],
    }


def run_case(
    shared_runner,
    runner: str,
    model: str | None,
    case: dict,
    cases_path: Path,
    timeout: int,
    skill_paths: dict[str, Path],
    isolation_prefix: list[str] | None,
    runner_executable: str,
) -> dict:
    artifact_path = cases_path.parent / case["artifact"]["source"]
    skill_path = skill_paths[case["framework"]]
    artifact_text = artifact_path.read_text(encoding="utf-8")
    prompt = render_prompt(
        case["framework"],
        artifact_text,
        skill_path.read_text(encoding="utf-8"),
    )
    with tempfile.TemporaryDirectory(prefix="e2e-debugger-holdout-") as temporary:
        workspace = Path(temporary)
        staged_artifact = workspace / "report.json"
        shutil.copy2(artifact_path, staged_artifact)
        before = workspace_digest(workspace)
        credential_loader = getattr(
            shared_runner,
            "runner_credentials",
            getattr(shared_runner, "inherited_runner_credentials", None),
        )
        try:
            runner_credentials = (
                credential_loader(runner) if credential_loader is not None else {}
            )
        except Exception:
            return {
                "case_id": case["id"],
                "case": case,
                "valid": False,
                "infrastructure_error": True,
                "prediction": None,
                "error": "runner credential lookup failed",
                "exit_code": None,
                "elapsed_ms": None,
                "raw_output_sha256": None,
                "raw_output_bytes": None,
                "workspace_integrity": {
                    "before_sha256": before,
                    "after_sha256": before,
                    "verified": True,
                },
            }
        output_sanitizer = shared_runner.sanitize_model_output
        try:
            exit_code, output, elapsed_ms = shared_runner.run_once(
                runner,
                prompt,
                timeout,
                workspace,
                model,
                isolation_prefix=isolation_prefix,
                runner_executable=runner_executable,
                runner_credentials=runner_credentials,
            )
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            try:
                error_text, credential_detected = output_sanitizer(
                    error_text,
                    runner_credentials,
                )
            except Exception:
                error_text = "runner failed and credential-safe error redaction failed"
            else:
                if credential_detected:
                    error_text = "runner failed and credential-shaped data was redacted"
            try:
                after = workspace_digest(workspace)
                integrity_error = None
            except ValueError as digest_exc:
                after = None
                integrity_error = str(digest_exc)
            return {
                "case_id": case["id"],
                "case": case,
                "valid": False,
                "infrastructure_error": True,
                "prediction": None,
                "error": (
                    error_text
                    if integrity_error is None
                    else f"{error_text}; {integrity_error}"
                ),
                "exit_code": None,
                "elapsed_ms": None,
                "raw_output_sha256": None,
                "raw_output_bytes": None,
                "workspace_integrity": {
                    "before_sha256": before,
                    "after_sha256": after,
                    "verified": after is not None and before == after,
                },
            }
        try:
            output, credential_detected = output_sanitizer(
                output,
                runner_credentials,
            )
        except Exception:
            output = ""
            credential_detected = False
            output_security_error = "runner output credential redaction failed"
        else:
            output_security_error = (
                "runner output contained credential-shaped data and was redacted"
                if credential_detected
                else None
            )
        try:
            after = workspace_digest(workspace)
        except ValueError as exc:
            output_bytes = output.encode("utf-8")
            return {
                "case_id": case["id"],
                "case": case,
                "valid": False,
                "infrastructure_error": True,
                "prediction": None,
                "error": str(exc),
                "exit_code": exit_code,
                "elapsed_ms": elapsed_ms,
                "raw_output_sha256": hashlib.sha256(output_bytes).hexdigest(),
                "raw_output_bytes": len(output_bytes),
                "raw_output": output,
                "workspace_integrity": {
                    "before_sha256": before,
                    "after_sha256": None,
                    "verified": False,
                },
            }
    output_bytes = output.encode("utf-8")
    integrity = {
        "before_sha256": before,
        "after_sha256": after,
        "verified": before == after,
    }
    if output_security_error is not None:
        return {
            "case_id": case["id"],
            "case": case,
            "valid": False,
            "infrastructure_error": True,
            "prediction": None,
            "error": output_security_error,
            "exit_code": exit_code,
            "elapsed_ms": elapsed_ms,
            "raw_output_sha256": hashlib.sha256(output_bytes).hexdigest(),
            "raw_output_bytes": len(output_bytes),
            "raw_output": output,
            "workspace_integrity": integrity,
        }
    if before != after:
        return {
            "case_id": case["id"],
            "case": case,
            "valid": False,
            "infrastructure_error": True,
            "prediction": None,
            "error": "isolated workspace mutated during model call",
            "exit_code": exit_code,
            "elapsed_ms": elapsed_ms,
            "raw_output_sha256": hashlib.sha256(output_bytes).hexdigest(),
            "raw_output_bytes": len(output_bytes),
            "raw_output": output,
            "workspace_integrity": integrity,
        }
    if exit_code != 0:
        return {
            "case_id": case["id"],
            "case": case,
            "valid": False,
            "infrastructure_error": True,
            "prediction": None,
            "error": f"runner exited {exit_code}",
            "exit_code": exit_code,
            "elapsed_ms": elapsed_ms,
            "raw_output_sha256": hashlib.sha256(output_bytes).hexdigest(),
            "raw_output_bytes": len(output_bytes),
            "raw_output": output,
            "workspace_integrity": integrity,
        }
    try:
        prediction = parse_prediction(output)
    except ValueError as exc:
        return {
            "case_id": case["id"],
            "case": case,
            "valid": False,
            "infrastructure_error": False,
            "prediction": None,
            "error": str(exc),
            "exit_code": exit_code,
            "elapsed_ms": elapsed_ms,
            "raw_output_sha256": hashlib.sha256(output_bytes).hexdigest(),
            "raw_output_bytes": len(output_bytes),
            "raw_output": output,
            "workspace_integrity": integrity,
        }
    return {
        "case_id": case["id"],
        "case": case,
        "valid": True,
        "infrastructure_error": False,
        "prediction": prediction,
        "raw_output": output,
        "raw_output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "raw_output_bytes": len(output_bytes),
        "error": None,
        "exit_code": exit_code,
        "elapsed_ms": elapsed_ms,
        "workspace_integrity": integrity,
    }


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", choices=("codex", "claude"), required=True)
    parser.add_argument(
        "--runner-path",
        type=Path,
        help="explicit absolute canonical path to the trusted runner executable",
    )
    parser.add_argument("--model")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--isolation-wrapper", type=Path)
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()

    if not args.allow_live:
        parser.error("live model calls require --allow-live")
    if args.runner_path is None:
        parser.error("the selected protocol requires an explicit --runner-path")
    requested_cases_path = Path(os.path.abspath(os.fspath(args.cases.expanduser())))
    requested_protocol_path = Path(os.path.abspath(os.fspath(args.protocol.expanduser())))
    try:
        cases_path = requested_cases_path.resolve(strict=True)
        protocol_path = requested_protocol_path.resolve(strict=True)
        isolation_prefix = isolation_prefix_for_inputs(
            requested_cases_path,
            requested_protocol_path,
            args.isolation_wrapper,
        )

        with tempfile.TemporaryDirectory(prefix="e2e-debugger-input-snapshot-") as temporary:
            snapshot = snapshot_inputs(
                cases_path,
                protocol_path,
                FRAMEWORK_SKILLS,
                Path(temporary),
            )
            snapshot_cases_path = snapshot["cases_path"]
            snapshot_protocol_path = snapshot["protocol_path"]
            corpus = load_corpus(snapshot_cases_path)
            protocol = load_protocol(snapshot_protocol_path)
            validate_host_pair(protocol, args.runner, args.model)
            repetitions = select_repetitions(
                args.repetitions,
                protocol["default_repetitions"],
            )
            selected = corpus["cases"]
            if args.case_ids:
                requested = set(args.case_ids)
                selected = [case for case in selected if case["id"] in requested]
                missing = requested - {case["id"] for case in selected}
                if missing:
                    parser.error(f"unknown case ids: {', '.join(sorted(missing))}")

            schedule = build_schedule(selected, repetitions, protocol["seed"])
            schedule_sha256 = canonical_digest(schedule)
            prompt_sha256 = prompt_set_digest(
                selected,
                snapshot_cases_path,
                snapshot["skill_paths"],
            )
            shared_runner = load_shared_runner()
            runner_executable, cli_identity = runner_cli_identity(
                args.runner,
                args.runner_path,
                protocol["execution_identity"]["expected_cli_versions"][args.runner],
            )
            cases_by_id = {case["id"]: case for case in selected}
            records = []
            for schedule_entry in schedule:
                record = run_case(
                    shared_runner,
                    args.runner,
                    args.model,
                    cases_by_id[schedule_entry["case_id"]],
                    snapshot_cases_path,
                    args.timeout,
                    snapshot["skill_paths"],
                    isolation_prefix,
                    runner_executable,
                )
                records.append({**schedule_entry, **record})

            input_integrity_verified = True
            input_integrity_error = None
            try:
                verify_snapshot(snapshot)
            except ValueError as exc:
                input_integrity_verified = False
                input_integrity_error = str(exc)
            try:
                input_post_digests = snapshot_post_digests(snapshot)
            except OSError as exc:
                input_post_digests = {}
                input_integrity_verified = False
                input_integrity_error = f"cannot compute post-run input digests: {exc}"
            score = score_predictions(records)
            complete = (
                len(selected) == len(corpus["cases"])
                and repetitions == protocol["default_repetitions"]
                and len(records) == len(schedule)
            )
            infrastructure_errors = [
                f"{record['case_id']} repetition {record['repetition']}: {record['error']}"
                for record in records
                if record.get("infrastructure_error")
            ]
            if input_integrity_error:
                infrastructure_errors.append(input_integrity_error)
            status = derive_status(
                complete,
                input_integrity_verified,
                infrastructure_errors,
                score,
                protocol["thresholds"],
            )
            report = {
                "schema_version": 2,
                "corpus_id": corpus["corpus_id"],
                "corpus_sha256": sha256(snapshot_cases_path),
                "protocol_sha256": sha256(snapshot_protocol_path),
                "input_snapshot_manifest": snapshot["manifest"],
                "input_post_digests": input_post_digests,
                "input_integrity_verified": input_integrity_verified,
                "prompt_skill_sha256": {
                    framework: snapshot["manifest"][f"skill:{framework}"]["sha256"]
                    for framework in sorted(snapshot["skill_paths"])
                },
                "prompt_set_sha256": prompt_sha256,
                "schedule": schedule,
                "schedule_sha256": schedule_sha256,
                "runner": args.runner,
                "model": args.model,
                "runner_cli_identity": cli_identity,
                "repetitions": repetitions,
                "execution_complete": complete,
                "infrastructure_errors": infrastructure_errors,
                "status": status,
                "score": score,
                "records": [
                    {
                        key: value
                        for key, value in record.items()
                        if key != "case"
                    }
                    for record in records
                ],
                "limitations": protocol["limitations"],
            }
            write_report(args.output, report)
            return STATUS_EXIT_CODES[status]
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report = {
            "schema_version": 1,
            "corpus_id": "debugger-holdout-v1",
            "runner": args.runner,
            "model": args.model,
            "execution_complete": False,
            "status": "INCONCLUSIVE",
            "infrastructure_errors": [f"{type(exc).__name__}: {exc}"],
        }
        write_report(args.output, report)
        return STATUS_EXIT_CODES["INCONCLUSIVE"]


if __name__ == "__main__":
    raise SystemExit(main())
