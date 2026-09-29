#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Development-only cross-check of Codex JSONL and the MCP tool journal.

This verifies a complete local event trace, not runner isolation, custody, or
the provenance of the supplied bytes. It cannot certify a release result.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
from typing import Any


HERE = Path(__file__).resolve().parent
MCP_PATH = HERE / "reviewer-release-codex-mcp-v1.py"
MCP_SPEC = importlib.util.spec_from_file_location("reviewer_release_codex_mcp_v1", MCP_PATH)
assert MCP_SPEC and MCP_SPEC.loader
MCP = importlib.util.module_from_spec(MCP_SPEC)
MCP_SPEC.loader.exec_module(MCP)
MAX_CODEX_STDOUT_BYTES = 8 * 1024 * 1024
MAX_CODEX_STDERR_BYTES = 1024 * 1024
MAX_MCP_JOURNAL_BYTES = 128 * 1024 * 1024
ALLOWED_ITEMS = {"agent_message", "reasoning", "mcp_tool_call"}
CATALOG_FILE = "skills/e2e-reviewer/references/pattern-reference.md"
ARM_TOOLS = {
    "full": {"read_staged_case_file", "read_staged_skill_file", "run_staged_bundled_scanner"},
    "catalog-only": {"read_staged_case_file"},
    "no-skill": {"read_staged_case_file"},
}


class TranscriptError(ValueError):
    """Missing, malformed, or unexpected model-visible evidence."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(raw: bytes, name: str) -> Any:
    try:
        return MCP.loads_strict(raw)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise TranscriptError(f"{name} is not strict JSON") from exc


def broker_content(entry: dict[str, Any], request: dict[str, Any], header: dict[str, Any]) -> list[dict[str, str]]:
    params = request["params"]
    name, arguments = params["name"], params["arguments"]
    if not isinstance(name, str) or name not in ARM_TOOLS[header["arm"]]:
        raise TranscriptError("MCP tool is not allowed for the recorded arm")
    if entry.get("tool") != name or not isinstance(arguments, dict):
        raise TranscriptError("MCP broker tool differs from the request")
    if name in {"read_staged_case_file", "read_staged_skill_file"}:
        if set(arguments) != {"path"} or not isinstance(arguments["path"], str) or entry.get("arguments") != arguments:
            raise TranscriptError("MCP broker read path differs from the request")
        allowed = header["case_files" if name == "read_staged_case_file" else "skill_files"]
        declared_path = arguments["path"]
        if name == "read_staged_skill_file" and declared_path.startswith("references/"):
            declared_path = "skills/e2e-reviewer/" + declared_path
        if not isinstance(allowed, dict) or declared_path not in allowed:
            raise TranscriptError("MCP broker read path is not in the session header")
        encoded, recorded_hash = entry.get("result_base64"), entry.get("result_sha256")
        expected_hash = allowed[declared_path]
    elif name == "run_staged_bundled_scanner":
        if arguments or entry.get("arguments") != {"source_root": header["source_root"]} or entry.get("exit_code") != 0:
            raise TranscriptError("MCP broker scanner result differs from the request")
        encoded, recorded_hash = entry.get("stdout_base64"), entry.get("stdout_sha256")
        expected_hash = recorded_hash
    else:
        raise TranscriptError("MCP broker tool is not allowlisted")
    if not isinstance(encoded, str) or not isinstance(recorded_hash, str) or not isinstance(expected_hash, str):
        raise TranscriptError("MCP broker result is malformed")
    try:
        data = base64.b64decode(encoded, validate=True)
        output = data.decode("utf-8", errors="strict")
    except (ValueError, UnicodeError) as exc:
        raise TranscriptError("MCP broker result is not valid UTF-8 base64") from exc
    if digest(data) != recorded_hash or recorded_hash != expected_hash:
        raise TranscriptError("MCP broker result differs from the declared bytes")
    return [{"type": "text", "text": output}]


def journal_tool_calls(path: Path | bytes, expected_arm: str) -> tuple[list[dict[str, Any]], str]:
    try:
        if isinstance(path, bytes):
            data = path
        else:
            if not hasattr(os, "O_NOFOLLOW"):
                raise ValueError("no-follow journal opening is unavailable")
            flags = os.O_RDONLY | os.O_NOFOLLOW
            with os.fdopen(os.open(path, flags), "rb") as source:
                metadata = os.fstat(source.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_MCP_JOURNAL_BYTES:
                    raise ValueError("MCP journal is not a bounded regular file")
                data = source.read(MAX_MCP_JOURNAL_BYTES + 1)
        if len(data) > MAX_MCP_JOURNAL_BYTES:
            raise ValueError("MCP journal exceeds capture bounds")
        # Codex may end the STDIO server without first closing its stdin. The
        # successful Codex turn and exact MCP call comparison below provide
        # the external boundary for a journal ending after a delivered reply.
        MCP.verify_journal(data, allow_codex_shutdown=True)
    except (OSError, ValueError) as exc:
        raise TranscriptError("MCP journal is incomplete or invalid") from exc
    rows = [strict_json(line, "MCP journal row") for line in data.splitlines()]
    calls: list[dict[str, Any]] = []
    header = rows[0]["event"]
    if header["arm"] != expected_arm or expected_arm not in ARM_TOOLS:
        raise TranscriptError("MCP journal arm differs from the expected arm")
    if not all(isinstance(header[key], dict) for key in ("case_files", "skill_files", "scanner_files")):
        raise TranscriptError("MCP journal file maps are malformed")
    if (expected_arm == "no-skill" and header["skill_files"]) or (
        expected_arm == "catalog-only" and set(header["skill_files"]) != {CATALOG_FILE}
    ) or (expected_arm != "full" and header["scanner_files"]):
        raise TranscriptError("MCP journal files are incompatible with the arm")
    pending: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    broker_entries: list[dict[str, Any]] = []
    for row in rows:
        event = row["event"]
        if event["kind"] == "mcp_request":
            request = strict_json(base64.b64decode(event["raw_base64"]), "MCP request")
            if request.get("method") == "tools/call":
                params = request.get("params")
                if not isinstance(params, dict) or set(params) not in ({"name", "arguments"}, {"_meta", "name", "arguments"}) or (
                    "_meta" in params and not isinstance(params["_meta"], dict)
                ):
                    raise TranscriptError("MCP tool request has unexpected arguments")
                pending = {"name": params["name"], "arguments": params["arguments"]}
        elif event["kind"] == "broker_tool":
            broker_entries.append(event["entry"])
        elif event["kind"] == "mcp_response_intent":
            response = strict_json(base64.b64decode(event["raw_base64"]), "MCP response")
            if pending is not None:
                result = response.get("result")
                if not isinstance(result, dict) or set(result) != {"content"} or len(broker_entries) != 1 or request is None:
                    raise TranscriptError("MCP tool response has no unique broker result")
                expected_content = broker_content(broker_entries[0], request, header)
                if result["content"] != expected_content:
                    raise TranscriptError("MCP response content differs from the broker result")
                pending["content"] = result["content"]
                calls.append(pending)
                pending = None
            elif broker_entries:
                raise TranscriptError("MCP broker result has no matching tool request")
            broker_entries = []
            request = None
        elif event["kind"] == "mcp_notification_handled":
            if broker_entries:
                raise TranscriptError("MCP broker result has no matching tool request")
            request = None
    if pending is not None or broker_entries:
        raise TranscriptError("MCP tool request has no response")
    return calls, digest(data)


def codex_events(raw: bytes, expected_server: str) -> tuple[str, str, list[dict[str, Any]]]:
    if not raw or len(raw) > MAX_CODEX_STDOUT_BYTES or not raw.endswith(b"\n"):
        raise TranscriptError("Codex JSONL is empty, oversized, or incomplete")
    events = [strict_json(line, "Codex event") for line in raw.splitlines()]
    if any(not isinstance(event, dict) for event in events):
        raise TranscriptError("Codex event must be an object")
    if len(events) < 4 or events[0].get("type") != "thread.started" or events[1].get("type") != "turn.started":
        raise TranscriptError("Codex event stream lacks its start boundary")
    thread_id = events[0].get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        raise TranscriptError("Codex thread id is missing")
    if events[-1].get("type") != "turn.completed" or sum(row.get("type") == "turn.completed" for row in events) != 1:
        raise TranscriptError("Codex turn has no unique terminal success event")
    messages: list[str] = []
    started: dict[str, dict[str, Any]] = {}
    calls: list[dict[str, Any]] = []
    for event in events[2:-1]:
        kind = event.get("type")
        if kind not in {"item.started", "item.updated", "item.completed"}:
            raise TranscriptError("Codex emitted an unexpected event type")
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") not in ALLOWED_ITEMS:
            raise TranscriptError("Codex used an unapproved item or tool")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise TranscriptError("Codex item id is missing")
        if item["type"] == "mcp_tool_call":
            if item.get("server") != expected_server or not isinstance(item.get("tool"), str) or not isinstance(item.get("arguments"), dict):
                raise TranscriptError("Codex called an unexpected MCP server or tool")
            if kind == "item.started":
                if item_id in started:
                    raise TranscriptError("Codex MCP item started twice")
                started[item_id] = item
            elif kind == "item.completed":
                first = started.pop(item_id, None)
                if first is None or (first["server"], first["tool"], first["arguments"]) != (
                    item["server"], item["tool"], item["arguments"]
                ):
                    raise TranscriptError("Codex MCP start/completion mismatch")
                result = item.get("result")
                if item.get("status") != "completed" or item.get("error") is not None or not isinstance(result, dict):
                    raise TranscriptError("Codex MCP call did not succeed")
                calls.append({"name": item["tool"], "arguments": item["arguments"], "content": result.get("content")})
        elif item["type"] == "agent_message" and kind == "item.completed":
            if not isinstance(item.get("text"), str):
                raise TranscriptError("Codex agent message is malformed")
            messages.append(item["text"])
    if started or not messages:
        raise TranscriptError("Codex stream has an unfinished MCP call or no final message")
    return thread_id, messages[-1], calls


def verify_capture(
    *, prompt: bytes, stdout: bytes, stderr: bytes, final_file: bytes,
    journal: Path | bytes, expected_server: str, expected_arm: str, exit_code: int,
) -> dict[str, Any]:
    if exit_code != 0 or not prompt or len(stderr) > MAX_CODEX_STDERR_BYTES:
        raise TranscriptError("Codex invocation failed or exceeded capture bounds")
    if not isinstance(expected_server, str) or not expected_server:
        raise TranscriptError("expected MCP server name is required")
    tool_calls, journal_sha256 = journal_tool_calls(journal, expected_arm)
    thread_id, final, event_calls = codex_events(stdout, expected_server)
    if event_calls != tool_calls:
        raise TranscriptError("Codex MCP events differ from the broker journal")
    final_bytes = final.encode("utf-8")
    if final_bytes != final_file:
        raise TranscriptError("Codex final-message file differs from the event stream")
    # Capture completeness and response validity are separate. A completed
    # Codex turn can return malformed JSON; the normalizer/response manifest
    # records that as an invalid model outcome without discarding raw evidence.
    return {
        "status": "complete_development_trace_only",
        "thread_id": thread_id,
        "prompt_sha256": digest(prompt),
        "codex_stdout_sha256": digest(stdout),
        "codex_stderr_sha256": digest(stderr),
        "mcp_journal_sha256": journal_sha256,
        "final_response_sha256": digest(final_bytes),
        "mcp_tool_calls": len(tool_calls),
    }
