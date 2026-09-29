#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reconcile signed-inventory call bytes with Codex traces and response rows.

This is an offline byte-consistency check, not runner isolation or provenance.
The caller must first verify the Ed25519 chain and every inventory file hash.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "scripts/evals"
LIB = ROOT / "scripts/ci/lib"
sys.path.insert(0, str(LIB))

from reviewer_release_case_id import is_valid_case_id  # noqa: E402
INPUT_ROLES = {"prompt", "staged_case_manifest", "staged_skill_manifest", "runner_config"}
OUTPUT_ROLES = {"codex_jsonl", "stderr", "final_response", "mcp_journal", "transcript_report"}
LIMITS = {
    "corpus_commitment": 1 << 20,
    "corpus": 16 << 20,
    "labels": 4 << 20,
    "adjudications": 16 << 20,
    "custody": 4 << 20,
    "adjudication_ledger": 16 << 20,
    "scorer_output": 4 << 20,
    "all_inputs": 32 << 20,
    "raw_outputs": 32 << 20,
    "response_manifest": 32 << 20,
    "evaluated_skill": 4 << 20,
    "prompt": 1 << 20,
    "staged_case_manifest": 4 << 20,
    "staged_skill_manifest": 4 << 20,
    "runner_config": 1 << 20,
    "codex_jsonl": 8 << 20,
    "stderr": 1 << 20,
    # Preserve overlong model answers as invalid outcomes; 65,536 bytes is the
    # validity boundary in the normalizer, not a raw-evidence retention limit.
    "final_response": 8 << 20,
    "mcp_journal": 128 << 20,
    "transcript_report": 1 << 20,
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ARMS = ("full", "catalog-only", "no-skill")
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


class CallEvidenceError(ValueError):
    """A call's supplied bytes are incomplete, mismatched, or ambiguous."""


def import_fixed(name: str, file_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, EVALS / file_name)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fixed evaluator {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TRACE = import_fixed("reviewer_release_call_trace_v1", "reviewer-release-codex-transcript-v1.py")
NORMALIZE = import_fixed("reviewer_release_call_normalize_v1", "normalize-reviewer-release-v1.py")
PROMPT = import_fixed("reviewer_release_call_prompt_v1", "reviewer-release-prompt-v1.py")
PLAN = import_fixed("reviewer_release_call_plan_v1", "run-reviewer-release-v1.py")


def strict_json(raw: bytes, where: str) -> Any:
    try:
        return NORMALIZE.loads_strict(raw, context=where)
    except NORMALIZE.NormalizationError as exc:
        raise CallEvidenceError(str(exc)) from exc


def exact(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise CallEvidenceError(f"{where} has missing or extra fields")
    return value


def call_key(value: dict[str, Any], where: str) -> tuple[str, str, int]:
    case_id, arm, repetition = value.get("case_id"), value.get("arm"), value.get("repetition")
    if not is_valid_case_id(case_id) or arm not in ARMS or type(repetition) is not int or repetition not in (1, 2, 3):
        raise CallEvidenceError(f"{where} has an invalid call identity")
    return case_id, arm, repetition


def verify_declared_schedule(rows: Any, case_ids: list[str], where: str) -> None:
    """Check a signed row sequence, not the actual order of model execution."""
    if not isinstance(rows, list):
        raise CallEvidenceError(f"{where} calls must be an array")
    try:
        expected = PLAN.ordered_call_keys(case_ids)
    except PLAN.ReleasePlanError as exc:
        raise CallEvidenceError(f"{where} cannot derive the frozen schedule") from exc
    if len(rows) != len(expected):
        raise CallEvidenceError(f"{where} call count differs from the frozen schedule")
    for index, (row, key) in enumerate(zip(rows, expected)):
        if not isinstance(row, dict) or call_key(row, f"{where}[{index}]") != key:
            raise CallEvidenceError(f"{where}[{index}] differs from the frozen call order")


def case_files(value: Any, where: str) -> tuple[str, dict[str, str]]:
    case = exact(value, {"source_root", "source_files"}, where)
    root = case["source_root"]
    if not isinstance(root, str) or not root or root.startswith("/") or "\\" in root or any(ord(char) < 32 for char in root) or any(part in {"", ".", ".."} for part in root.split("/")):
        raise CallEvidenceError(f"{where}.source_root is invalid")
    rows = case["source_files"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        raise CallEvidenceError(f"{where}.source_files is invalid")
    files: dict[str, str] = {}
    for index, raw in enumerate(rows):
        item = exact(raw, {"path", "sha256"}, f"{where}.source_files[{index}]")
        path, digest = item["path"], item["sha256"]
        if not isinstance(path, str) or not path.startswith(root + "/") or "\\" in path or any(ord(char) < 32 for char in path) or any(part in {"", ".", ".."} for part in path.split("/")) or path in files:
            raise CallEvidenceError(f"{where}.source_files[{index}].path is invalid or duplicated")
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            raise CallEvidenceError(f"{where}.source_files[{index}].sha256 is invalid")
        files[path] = digest
    return root, files


def evaluated_skill_snapshot(raw: bytes, surface: dict[str, Any]) -> dict[str, dict[str, str]]:
    snapshot = exact(strict_json(raw, "evaluated skill snapshot"), {
        "schema_version", "protocol_id", "skill_files", "scanner_files",
    }, "evaluated skill snapshot")
    if type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1 or snapshot["protocol_id"] != "reviewer-release-v1":
        raise CallEvidenceError("evaluated skill snapshot identity differs")
    try:
        all_skill_paths = set(surface["initial_model_visible_files"]["full"]) | set(surface["on_demand_skill_files"]["full"])
        all_skill_paths |= set(surface["initial_model_visible_files"]["catalog-only"])
    except (KeyError, TypeError) as exc:
        raise CallEvidenceError("signed skill treatment surface is invalid") from exc
    skill_files = exact(snapshot["skill_files"], all_skill_paths, "evaluated skill files")
    scanner_files = exact(snapshot["scanner_files"], set(TRACE.MCP.BROKER.SCANNER_FILES), "evaluated scanner files")
    for role, files in (("skill", skill_files), ("scanner", scanner_files)):
        if any(not isinstance(value, str) or SHA256.fullmatch(value) is None for value in files.values()):
            raise CallEvidenceError(f"evaluated {role} file SHA-256 is invalid")
    return {"skill_files": skill_files, "scanner_files": scanner_files}


def verified_runner_config(raw: bytes, surface: dict[str, Any], primary: dict[str, Any]) -> str:
    config = exact(strict_json(raw, "runner config"), {
        "schema_version", "protocol_id", "host_id", "runner_family", "model",
        "runner_version", "decoding_settings",
    }, "runner config")
    if type(config["schema_version"]) is not int or config["schema_version"] != 1 or config["protocol_id"] != "reviewer-release-v1":
        raise CallEvidenceError("runner config identity differs")
    if not isinstance(primary, dict) or set(primary) != {"host_id", "runner_family", "model", "minimum_version"}:
        raise CallEvidenceError("signed primary execution identity is invalid")
    for field in ("host_id", "runner_family", "model"):
        if config[field] != primary[field]:
            raise CallEvidenceError(f"runner config {field} differs from the signed primary cell")
    if config["decoding_settings"] != surface.get("runner_decoding_settings"):
        raise CallEvidenceError("runner decoding settings differ from the signed treatment surface")
    version, minimum = config["runner_version"], primary["minimum_version"]
    if not isinstance(version, str) or not isinstance(minimum, str):
        raise CallEvidenceError("runner version is invalid")
    match, floor = VERSION.fullmatch(version), VERSION.fullmatch(minimum)
    if match is None or floor is None or tuple(map(int, match.groups())) < tuple(map(int, floor.groups())):
        raise CallEvidenceError("runner version is below the frozen minimum or malformed")
    return version


def verified_initial_material(
    raw: bytes, header: dict[str, Any], arm: str, surface: dict[str, Any],
    evaluated_skill: dict[str, dict[str, str]],
) -> dict[str, bytes]:
    manifest = exact(strict_json(raw, "staged skill manifest"), {
        "schema_version", "skill_files", "scanner_files", "initial_content_base64",
    }, "staged skill manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise CallEvidenceError("staged skill manifest version differs")
    try:
        initial_paths = surface["initial_model_visible_files"][arm]
        on_demand_paths = surface["on_demand_skill_files"][arm]
    except (KeyError, TypeError) as exc:
        raise CallEvidenceError("signed skill treatment surface is invalid") from exc
    if not isinstance(initial_paths, list) or not isinstance(on_demand_paths, list):
        raise CallEvidenceError("signed skill treatment path lists are invalid")
    expected_skill = set(initial_paths) | set(on_demand_paths)
    skill_files = exact(manifest["skill_files"], expected_skill, "staged skill files")
    scanner_files = exact(manifest["scanner_files"],
        set(TRACE.MCP.BROKER.SCANNER_FILES) if arm == "full" else set(), "staged scanner files")
    for role, files in (("skill", skill_files), ("scanner", scanner_files)):
        if any(not isinstance(value, str) or SHA256.fullmatch(value) is None for value in files.values()):
            raise CallEvidenceError(f"staged {role} file SHA-256 is invalid")
        frozen = evaluated_skill[f"{role}_files"]
        if any(frozen.get(path) != digest for path, digest in files.items()):
            raise CallEvidenceError(f"staged {role} files differ from the signed evaluated skill")
    if header.get("skill_files") != skill_files or header.get("scanner_files") != scanner_files:
        raise CallEvidenceError("MCP journal skill files differ from the staged skill manifest")
    encoded = exact(manifest["initial_content_base64"], set(initial_paths), "initial skill content")
    initial: dict[str, bytes] = {}
    for path, value in encoded.items():
        if not isinstance(value, str):
            raise CallEvidenceError("initial skill content is not base64")
        try:
            data = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise CallEvidenceError("initial skill content is not base64") from exc
        if len(data) > 1048576 or hashlib.sha256(data).hexdigest() != skill_files[path]:
            raise CallEvidenceError("initial skill bytes differ from the staged skill manifest")
        initial[path] = data
    return initial


def verify_required_case_reads(calls: list[dict[str, Any]], case_paths: set[str], arm: str) -> None:
    observed: set[str] = set()
    scanner_seen = False
    for call in calls:
        if call["name"] == "read_staged_case_file":
            arguments = call["arguments"]
            if set(arguments) != {"path"} or arguments["path"] not in case_paths:
                raise CallEvidenceError("case read is outside the signed source set")
            observed.add(arguments["path"])
        elif call["name"] == "run_staged_bundled_scanner":
            scanner_seen = True
    if observed != case_paths:
        raise CallEvidenceError("model did not read every signed case source file")
    if arm == "full" and not scanner_seen:
        raise CallEvidenceError("full treatment omitted the bundled scanner")


def read_bound(bundle: Path, reference: Any, role: str) -> bytes:
    item = exact(reference, {"path", "sha256"}, f"{role} reference")
    raw_path, expected = item["path"], item["sha256"]
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path or any(ord(c) < 32 for c in raw_path):
        raise CallEvidenceError(f"{role} path is invalid")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or path.as_posix() != raw_path or any(part in {"", ".", ".."} for part in raw_path.split("/")):
        raise CallEvidenceError(f"{role} path escapes or is not canonical")
    if not isinstance(expected, str) or SHA256.fullmatch(expected) is None:
        raise CallEvidenceError(f"{role} SHA-256 is invalid")
    candidate = bundle
    for part in path.parts:
        candidate = candidate / part
        try:
            mode = candidate.lstat().st_mode
        except OSError as exc:
            raise CallEvidenceError(f"{role} path is unavailable") from exc
        if stat.S_ISLNK(mode):
            raise CallEvidenceError(f"{role} path contains a symlink")
    if not stat.S_ISREG(mode):
        raise CallEvidenceError(f"{role} is not a regular file")
    maximum = LIMITS[role]
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        with os.fdopen(os.open(candidate, flags), "rb") as source:
            opened = os.fstat(source.fileno())
            if not stat.S_ISREG(opened.st_mode) or opened.st_size > maximum:
                raise CallEvidenceError(f"{role} is not a bounded regular file")
            data = source.read(maximum + 1)
    except OSError as exc:
        raise CallEvidenceError(f"{role} cannot be read") from exc
    if len(data) > maximum or hashlib.sha256(data).hexdigest() != expected:
        raise CallEvidenceError(f"{role} bytes differ from the signed inventory")
    return data


def verify_call(
    bundle: Path, input_row: Any, output_row: Any, response_row: Any,
    expected_case: dict[str, Any], surface: dict[str, Any],
    evaluated_skill: dict[str, dict[str, str]], primary: dict[str, Any],
) -> dict[str, Any]:
    inputs = exact(input_row, {"case_id", "arm", "repetition", "artifacts"}, "input call")
    outputs = exact(output_row, {"case_id", "arm", "repetition", "artifacts"}, "output call")
    response = exact(response_row, {
        "case_id", "arm", "repetition", "valid", "raw_output_sha256",
        "normalized_finding_identities", "completed_at",
    }, "response manifest row")
    key = call_key(inputs, "input call")
    if call_key(outputs, "output call") != key or call_key(response, "response manifest row") != key:
        raise CallEvidenceError("input, output, and response call identities differ")
    input_refs = exact(inputs["artifacts"], INPUT_ROLES, "input artifacts")
    output_refs = exact(outputs["artifacts"], OUTPUT_ROLES, "output artifacts")
    in_bytes = {role: read_bound(bundle, input_refs[role], role) for role in INPUT_ROLES}
    out_bytes = {role: read_bound(bundle, output_refs[role], role) for role in OUTPUT_ROLES}
    runner_version = verified_runner_config(in_bytes["runner_config"], surface, primary)
    staged_root, staged_files = case_files(strict_json(in_bytes["staged_case_manifest"], "staged case manifest"), "staged case manifest")
    committed_root, committed_files = case_files(expected_case, "signed corpus case")
    if (staged_root, staged_files) != (committed_root, committed_files):
        raise CallEvidenceError("staged case differs from the signed corpus case")
    try:
        common_prompt = PROMPT.common_prompt(surface, expected_case)
    except PROMPT.PromptError as exc:
        raise CallEvidenceError("signed common prompt contract is invalid") from exc
    if not in_bytes["prompt"].startswith(common_prompt) or (key[1] == "no-skill" and in_bytes["prompt"] != common_prompt):
        raise CallEvidenceError("call prompt differs from the signed common task")
    if key[1] != "no-skill" and len(in_bytes["prompt"]) == len(common_prompt):
        raise CallEvidenceError("treatment arm lacks its initial reference material")
    report = exact(strict_json(out_bytes["transcript_report"], "transcript report"), {
        "schema_version", "protocol_id", "case_id", "arm", "repetition", "exit_code", "capture",
    }, "transcript report")
    if report["schema_version"] != 1 or report["protocol_id"] != "reviewer-release-v1" or call_key(report, "transcript report") != key or report["exit_code"] != 0:
        raise CallEvidenceError("transcript report identity or exit status differs")
    try:
        capture = TRACE.verify_capture(
            prompt=in_bytes["prompt"], stdout=out_bytes["codex_jsonl"],
            stderr=out_bytes["stderr"], final_file=out_bytes["final_response"],
            journal=out_bytes["mcp_journal"], expected_server="reviewer_release",
            expected_arm=key[1], exit_code=report["exit_code"],
        )
        calls, _ = TRACE.journal_tool_calls(out_bytes["mcp_journal"], key[1])
    except TRACE.TranscriptError as exc:
        raise CallEvidenceError("Codex JSONL, MCP journal, and final response do not reconcile") from exc
    header = exact(strict_json(out_bytes["mcp_journal"].splitlines()[0], "MCP journal header"), {"sequence", "previous_sha256", "event", "sha256"}, "MCP journal header")["event"]
    if header.get("source_root") != staged_root or header.get("case_files") != staged_files:
        raise CallEvidenceError("MCP journal case files differ from the signed staged case")
    initial_material = verified_initial_material(in_bytes["staged_skill_manifest"], header, key[1], surface, evaluated_skill)
    try:
        expected_prompt = PROMPT.build_prompt(surface, expected_case, key[1], initial_material)
    except PROMPT.PromptError as exc:
        raise CallEvidenceError("signed treatment prompt contract is invalid") from exc
    if in_bytes["prompt"] != expected_prompt:
        raise CallEvidenceError("call prompt differs from the signed treatment material")
    if report["capture"] != capture:
        raise CallEvidenceError("signed transcript report differs from recomputed capture")
    verify_required_case_reads(calls, set(staged_files), key[1])
    try:
        normalized = NORMALIZE.normalize_response(out_bytes["final_response"])
    except NORMALIZE.NormalizationError:
        normalized = None
    raw_hash = hashlib.sha256(out_bytes["final_response"]).hexdigest()
    if response["raw_output_sha256"] != raw_hash:
        raise CallEvidenceError("response manifest hash differs from raw final response")
    if normalized is None:
        if response["valid"] is not False or response["normalized_finding_identities"] is not None:
            raise CallEvidenceError("invalid raw response must be declared invalid without identities")
    elif response["valid"] is not True or response["normalized_finding_identities"] != normalized["normalized_finding_identities"]:
        raise CallEvidenceError("response manifest row differs from normalized final response")
    return {
        "case_id": key[0], "arm": key[1], "repetition": key[2],
        "raw_output_sha256": raw_hash, "valid": normalized is not None,
        "thread_id": capture["thread_id"],
        "runner_version": runner_version,
    }


def indexed_rows(rows: Any, expected_cases: set[str], where: str, row_keys: set[str]) -> dict[tuple[str, str, int], dict[str, Any]]:
    if not isinstance(rows, list) or len(rows) != 1080:
        raise CallEvidenceError(f"{where} must contain exactly 1080 calls")
    indexed: dict[tuple[str, str, int], dict[str, Any]] = {}
    for index, raw in enumerate(rows):
        row = exact(raw, row_keys, f"{where}[{index}]")
        key = call_key(row, f"{where}[{index}]")
        if key[0] not in expected_cases or key in indexed:
            raise CallEvidenceError(f"{where} has an uncommitted or duplicate call")
        indexed[key] = row
    expected = {(case_id, arm, repetition) for case_id in expected_cases for arm in ARMS for repetition in (1, 2, 3)}
    if set(indexed) != expected:
        raise CallEvidenceError(f"{where} does not cover every committed case, arm, and repetition")
    return indexed


def verify_matrix(
    bundle: Path, evaluated_skill_ref: Any, input_ref: Any, output_ref: Any, response_ref: Any,
    expected_cases: dict[str, dict[str, Any]], expected_corpus_id: str,
    surface: dict[str, Any], primary: dict[str, Any],
) -> dict[str, Any]:
    """Verify all call bytes after an independent signed-chain/corpus check."""
    if not isinstance(expected_cases, dict) or len(expected_cases) != 120 or any(not is_valid_case_id(case_id) for case_id in expected_cases):
        raise CallEvidenceError("expected cases must be the 120 signed corpus cases")
    for case_id, case in expected_cases.items():
        case_files(case, f"signed corpus case {case_id}")
    if not isinstance(expected_corpus_id, str) or not expected_corpus_id:
        raise CallEvidenceError("expected corpus ID must come from the signed corpus commitment")
    evaluated_skill = evaluated_skill_snapshot(read_bound(bundle, evaluated_skill_ref, "evaluated_skill"), surface)
    inventories: dict[str, dict[tuple[str, str, int], dict[str, Any]]] = {}
    for name, reference, roles in (
        ("all_inputs", input_ref, INPUT_ROLES),
        ("raw_outputs", output_ref, OUTPUT_ROLES),
    ):
        root = exact(strict_json(read_bound(bundle, reference, name), name), {
            "schema_version", "protocol_id", "corpus_id", "calls",
        }, name)
        if root["schema_version"] != 1 or root["protocol_id"] != "reviewer-release-v1" or root["corpus_id"] != expected_corpus_id:
            raise CallEvidenceError(f"{name} identity is invalid")
        verify_declared_schedule(root["calls"], list(expected_cases), name)
        rows = indexed_rows(root["calls"], expected_cases, name, {"case_id", "arm", "repetition", "artifacts"})
        for key, row in rows.items():
            exact(row["artifacts"], roles, f"{name} artifacts {key}")
        inventories[name] = rows
    manifest = exact(strict_json(read_bound(bundle, response_ref, "response_manifest"), "response manifest"), {
        "schema_version", "protocol_id", "evidence_class", "model_run_completed_at", "responses",
    }, "response manifest")
    if manifest["schema_version"] != 1 or manifest["protocol_id"] != "reviewer-release-v1" or manifest["evidence_class"] != "development_only":
        raise CallEvidenceError("response manifest identity or evidence class differs")
    verify_declared_schedule(manifest["responses"], list(expected_cases), "response manifest")
    responses = indexed_rows(manifest["responses"], expected_cases, "response manifest", {
        "case_id", "arm", "repetition", "valid", "raw_output_sha256",
        "normalized_finding_identities", "completed_at",
    })
    thread_ids: set[str] = set()
    runner_versions: set[str] = set()
    for key in sorted(responses):
        checked = verify_call(bundle, inventories["all_inputs"][key], inventories["raw_outputs"][key], responses[key], expected_cases[key[0]], surface, evaluated_skill, primary)
        if checked["thread_id"] in thread_ids:
            raise CallEvidenceError("Codex thread ID was reused across supposedly fresh calls")
        thread_ids.add(checked["thread_id"])
        runner_versions.add(checked["runner_version"])
    if len(runner_versions) != 1:
        raise CallEvidenceError("runner version changed across paired calls")
    return {"status": "byte_consistency_only", "verified_calls": 1080, "release_eligible": False}
