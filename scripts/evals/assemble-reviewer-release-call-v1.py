#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build one release-v1 call's byte inventory from an already captured run.

This is a local artifact assembler, not an executor or provenance attestation.
The independent operator must still establish the origin of every supplied byte.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


HERE = Path(__file__).resolve().parent


def load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVIDENCE = load("release_call_evidence", "verify-reviewer-release-calls-v1.py")
TRACE = EVIDENCE.TRACE


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"


def execution_event_payload(
    *, corpus_id: str, event_index: int, previous_sha256: str,
    stage: str, case_id: str, arm: str, repetition: int,
    artifacts: dict[str, dict[str, str]],
) -> bytes:
    """Build the exact bytes an independent witness must sign at one boundary.

    This does not sign, timestamp, or establish that the event happened online.
    """
    EVIDENCE.call_key({"case_id": case_id, "arm": arm, "repetition": repetition}, "execution event")
    if not isinstance(corpus_id, str) or not corpus_id:
        raise EVIDENCE.CallEvidenceError("execution event needs a committed corpus ID")
    if type(event_index) is not int or event_index < 0 or stage not in {"begin", "end"} or event_index % 2 != (stage == "end"):
        raise EVIDENCE.CallEvidenceError("execution event index and stage differ")
    if not isinstance(previous_sha256, str) or EVIDENCE.SHA256.fullmatch(previous_sha256) is None:
        raise EVIDENCE.CallEvidenceError("execution event predecessor hash is invalid")
    if event_index == 0 and previous_sha256 != "0" * 64:
        raise EVIDENCE.CallEvidenceError("first execution event needs the zero predecessor")
    roles = EVIDENCE.INPUT_ROLES if stage == "begin" else EVIDENCE.OUTPUT_ROLES
    references = EVIDENCE.exact(artifacts, roles, "execution event artifacts")
    paths: set[str] = set()
    for role, raw in references.items():
        item = EVIDENCE.exact(raw, {"path", "sha256"}, f"execution event {role}")
        path, digest = item["path"], item["sha256"]
        if not isinstance(path, str) or not path or PurePosixPath(path).is_absolute() or PurePosixPath(path).as_posix() != path or any(part in {"", ".", ".."} for part in path.split("/")) or any(ord(char) < 32 for char in path) or "\\" in path or path in paths:
            raise EVIDENCE.CallEvidenceError("execution event artifact path is unsafe or reused")
        if not isinstance(digest, str) or EVIDENCE.SHA256.fullmatch(digest) is None:
            raise EVIDENCE.CallEvidenceError("execution event artifact hash is invalid")
        paths.add(path)
    event = {
        "schema_version": 1, "protocol_id": "reviewer-release-v1", "corpus_id": corpus_id,
        "event_index": event_index, "previous_sha256": previous_sha256,
        "stage": stage, "case_id": case_id, "arm": arm,
        "repetition": repetition, "artifacts": references,
    }
    return json_bytes(event).rstrip(b"\n")


def assemble_inputs(
    *, arm: str, case: dict[str, Any], surface: dict[str, Any],
    primary: dict[str, Any], runner_version: str,
    staged_skill_files: dict[str, bytes], staged_scanner_files: dict[str, bytes],
    prompt: bytes,
) -> dict[str, bytes]:
    """Freeze the four model-call input artifacts before execution begins."""
    EVIDENCE.case_files(case, "assembled case")
    try:
        initial_paths = set(surface["initial_model_visible_files"][arm])
        skill_paths = initial_paths | set(surface["on_demand_skill_files"][arm])
    except (KeyError, TypeError) as exc:
        raise EVIDENCE.CallEvidenceError("treatment file lists are invalid") from exc
    if set(staged_skill_files) != skill_paths:
        raise EVIDENCE.CallEvidenceError("staged skill file set differs from the treatment")
    expected_scanner = set(TRACE.MCP.BROKER.SCANNER_FILES) if arm == "full" else set()
    if set(staged_scanner_files) != expected_scanner:
        raise EVIDENCE.CallEvidenceError("staged scanner file set differs from the treatment")
    skill_hashes = {path: hashlib.sha256(data).hexdigest() for path, data in staged_skill_files.items()}
    scanner_hashes = {path: hashlib.sha256(data).hexdigest() for path, data in staged_scanner_files.items()}
    initial = {path: staged_skill_files[path] for path in initial_paths}
    try:
        expected_prompt = EVIDENCE.PROMPT.build_prompt(surface, case, arm, initial)
    except EVIDENCE.PROMPT.PromptError as exc:
        raise EVIDENCE.CallEvidenceError("cannot build the frozen call prompt") from exc
    if prompt != expected_prompt:
        raise EVIDENCE.CallEvidenceError("captured prompt differs from the frozen treatment")
    runner_config = {
        "schema_version": 1, "protocol_id": "reviewer-release-v1",
        "host_id": primary["host_id"], "runner_family": primary["runner_family"],
        "model": primary["model"], "runner_version": runner_version,
        "decoding_settings": surface["runner_decoding_settings"],
    }
    EVIDENCE.verified_runner_config(json_bytes(runner_config), surface, primary)
    staged_skill_manifest = {
        "schema_version": 1, "skill_files": skill_hashes,
        "scanner_files": scanner_hashes,
        "initial_content_base64": {
            path: base64.b64encode(initial[path]).decode("ascii") for path in sorted(initial)
        },
    }
    return {
        "prompt": prompt,
        "staged_case_manifest": json_bytes(case),
        "staged_skill_manifest": json_bytes(staged_skill_manifest),
        "runner_config": json_bytes(runner_config),
    }


def assemble_call(
    *, case_id: str, arm: str, repetition: int, case: dict[str, Any],
    surface: dict[str, Any], primary: dict[str, Any], runner_version: str,
    staged_skill_files: dict[str, bytes], staged_scanner_files: dict[str, bytes],
    prompt: bytes, codex_jsonl: bytes, stderr: bytes, final_response: bytes,
    mcp_journal: bytes, completed_at: str,
) -> dict[str, Any]:
    """Validate and return the exact four inputs, five outputs, and response row."""
    key = {"case_id": case_id, "arm": arm, "repetition": repetition}
    EVIDENCE.call_key(key, "assembled call")
    root, source_hashes = EVIDENCE.case_files(case, "assembled case")
    if not mcp_journal or not mcp_journal.endswith(b"\n"):
        raise EVIDENCE.CallEvidenceError("MCP journal is empty or incomplete")
    header = EVIDENCE.exact(
        EVIDENCE.strict_json(mcp_journal.splitlines()[0], "MCP journal header"),
        {"sequence", "previous_sha256", "event", "sha256"}, "MCP journal header",
    )["event"]
    if not isinstance(header, dict):
        raise EVIDENCE.CallEvidenceError("MCP journal header event must be an object")
    if header.get("source_root") != root or header.get("case_files") != source_hashes or header.get("arm") != arm:
        raise EVIDENCE.CallEvidenceError("captured case or arm differs from the declared call")
    inputs = assemble_inputs(
        arm=arm, case=case, surface=surface, primary=primary,
        runner_version=runner_version, staged_skill_files=staged_skill_files,
        staged_scanner_files=staged_scanner_files, prompt=prompt,
    )
    skill_hashes = {path: hashlib.sha256(data).hexdigest() for path, data in staged_skill_files.items()}
    scanner_hashes = {path: hashlib.sha256(data).hexdigest() for path, data in staged_scanner_files.items()}
    if header.get("skill_files") != skill_hashes or header.get("scanner_files") != scanner_hashes:
        raise EVIDENCE.CallEvidenceError("captured treatment hashes differ from staged files")
    try:
        capture = TRACE.verify_capture(
            prompt=prompt, stdout=codex_jsonl, stderr=stderr,
            final_file=final_response, journal=mcp_journal,
            expected_server="reviewer_release", expected_arm=arm, exit_code=0,
        )
        calls, _ = TRACE.journal_tool_calls(mcp_journal, arm)
        EVIDENCE.verify_required_case_reads(calls, set(source_hashes), arm)
    except TRACE.TranscriptError as exc:
        raise EVIDENCE.CallEvidenceError("captured call is incomplete") from exc
    try:
        normalized = EVIDENCE.NORMALIZE.normalize_response(final_response)
    except EVIDENCE.NORMALIZE.NormalizationError:
        # A completed call with a malformed answer is a measured model outcome,
        # not missing execution evidence. Keep its raw bytes for the signed
        # inventory and mark only the response as invalid.
        normalized = None
    outputs = {
        "codex_jsonl": codex_jsonl, "stderr": stderr,
        "final_response": final_response, "mcp_journal": mcp_journal,
        "transcript_report": json_bytes({
            "schema_version": 1, "protocol_id": "reviewer-release-v1",
            **key, "exit_code": 0, "capture": capture,
        }),
    }
    return {
        "inputs": inputs,
        "outputs": outputs,
        "response": {
            **key, "valid": normalized is not None,
            "raw_output_sha256": hashlib.sha256(final_response).hexdigest(),
            "normalized_finding_identities": (
                normalized["normalized_finding_identities"] if normalized is not None else None
            ),
            "completed_at": completed_at,
        },
    }
