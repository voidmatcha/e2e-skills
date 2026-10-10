#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Development-only MCP bridge to the release-v1 read/scan broker.

This is not an isolated model runner or release evidence. In particular, MCP
tool filtering does not establish that a Codex process has no other tools.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from typing import Any, BinaryIO


MAX_REQUEST_BYTES = 65536
MAX_JOURNAL_LINE_BYTES = 4194304
PROTOCOL_VERSION = "2025-03-26"
HERE = Path(__file__).resolve().parent
BROKER_PATH = HERE / "reviewer-release-tool-surface-v1.py"
BROKER_SPEC = importlib.util.spec_from_file_location("reviewer_release_tool_surface_v1", BROKER_PATH)
assert BROKER_SPEC and BROKER_SPEC.loader
BROKER = importlib.util.module_from_spec(BROKER_SPEC)
BROKER_SPEC.loader.exec_module(BROKER)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def loads_strict(raw: str | bytes) -> Any:
    return json.loads(raw, object_pairs_hook=strict_object, parse_constant=reject_constant)


class AuditJournal:
    """Crash-detectable development trace, not a signed custody record."""

    def __init__(self, path: Path) -> None:
        if not path.is_absolute() or not path.parent.is_dir():
            raise ValueError("journal needs an existing absolute parent")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        self.fd = os.open(path, flags, 0o600)
        self.sequence = 0
        self.previous_sha256 = "0" * 64

    def append(self, event: dict[str, Any]) -> None:
        row = {
            "sequence": self.sequence,
            "previous_sha256": self.previous_sha256,
            "event": event,
        }
        row["sha256"] = hashlib.sha256(canonical_bytes(row)).hexdigest()
        line = canonical_bytes(row) + b"\n"
        if len(line) > MAX_JOURNAL_LINE_BYTES:
            raise ValueError("journal event exceeds byte limit")
        with os.fdopen(os.dup(self.fd), "wb", closefd=True) as duplicate:
            duplicate.write(line)
            duplicate.flush()
        os.fsync(self.fd)
        self.sequence += 1
        self.previous_sha256 = row["sha256"]

    def close(self) -> None:
        os.close(self.fd)


def verify_journal(path: Path | bytes, *, allow_codex_shutdown: bool = False) -> int:
    """Check local trace completeness and accidental mutation, not authenticity."""
    previous = "0" * 64
    count = 0
    pending_request = False
    response_intended = False
    finished = False
    started = False
    pending_id: str | int | None = None
    expects_response = False
    last_kind = ""
    source_input = io.BytesIO(path) if isinstance(path, bytes) else path.open("rb")
    with source_input as source:
        while line := source.readline(MAX_JOURNAL_LINE_BYTES + 1):
            if len(line) > MAX_JOURNAL_LINE_BYTES or not line.endswith(b"\n"):
                raise ValueError("journal line is oversized or incomplete")
            row = loads_strict(line)
            if not isinstance(row, dict) or set(row) != {"sequence", "previous_sha256", "event", "sha256"}:
                raise ValueError("journal row shape is invalid")
            if type(row["sequence"]) is not int or row["sequence"] != count or row["previous_sha256"] != previous:
                raise ValueError("journal chain order is invalid")
            actual = hashlib.sha256(canonical_bytes({key: row[key] for key in ("sequence", "previous_sha256", "event")})).hexdigest()
            if row["sha256"] != actual:
                raise ValueError("journal row digest differs")
            previous = actual
            count += 1
            event = row["event"]
            if not isinstance(event, dict) or finished:
                raise ValueError("journal event order is invalid")
            kind = event.get("kind")
            last_kind = kind
            if kind == "session_start":
                if set(event) != {"kind", "arm", "source_root", "case_files", "skill_files", "scanner_files"}:
                    raise ValueError("journal session header shape is invalid")
                if count != 1 or started:
                    raise ValueError("journal session header is out of order")
                started = True
                continue
            if not started:
                raise ValueError("journal is missing its session header")
            if kind in {"mcp_request", "mcp_response_intent"}:
                if set(event) != {"kind", "raw_base64"} or not isinstance(event["raw_base64"], str):
                    raise ValueError("journal wire event shape is invalid")
                try:
                    wire = base64.b64decode(event["raw_base64"], validate=True)
                except ValueError as exc:
                    raise ValueError("journal wire bytes are invalid") from exc
                try:
                    payload = loads_strict(wire)
                except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                    raise ValueError("journal wire payload is not strict JSON") from exc
                if kind == "mcp_request":
                    if not isinstance(payload, dict):
                        raise ValueError("journal request shape is invalid")
                    pending_id = payload.get("id")
                    expects_response = "id" in payload
                else:
                    if not isinstance(payload, dict) or "error" in payload or (
                        isinstance(payload.get("result"), dict) and payload["result"].get("isError") is True
                    ):
                        raise ValueError("journal contains a failed model-visible tool response")
                    if not expects_response or payload.get("id") != pending_id:
                        raise ValueError("journal response id does not match its request")
            elif kind == "broker_tool":
                if set(event) != {"kind", "entry"} or not isinstance(event["entry"], dict):
                    raise ValueError("journal broker event shape is invalid")
            elif kind in {"mcp_response_delivered", "mcp_notification_handled", "server_eof"}:
                if set(event) != {"kind"}:
                    raise ValueError("journal marker shape is invalid")
            else:
                raise ValueError("journal event kind is invalid")
            if kind == "mcp_request":
                if pending_request or response_intended:
                    raise ValueError("journal has an unanswered request")
                pending_request = True
            elif kind == "broker_tool":
                if not pending_request or response_intended:
                    raise ValueError("journal broker event is out of order")
            elif kind == "mcp_response_intent":
                if not pending_request or response_intended or not expects_response:
                    raise ValueError("journal response intent is out of order")
                response_intended = True
            elif kind == "mcp_response_delivered":
                if not pending_request or not response_intended:
                    raise ValueError("journal response delivery is out of order")
                pending_request = response_intended = False
                expects_response = False
                pending_id = None
            elif kind == "mcp_notification_handled":
                if not pending_request or response_intended or expects_response:
                    raise ValueError("journal notification is out of order")
                pending_request = False
            elif kind == "server_eof":
                if pending_request or response_intended:
                    raise ValueError("journal ends with an unanswered request")
                finished = True
    if count == 0 or (not finished and not (
        allow_codex_shutdown and last_kind == "mcp_response_delivered"
        and not pending_request and not response_intended
    )):
        raise ValueError("journal is missing its normal-end marker")
    return count


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def tool_definition(name: str) -> dict[str, Any]:
    if name == "run_staged_bundled_scanner":
        return {
            "name": name,
            "description": "Run only the frozen bundled Tier 3 scanner on the staged case root.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        }
    return {
        "name": name,
        "description": "Read one declared staged source file." if name == "read_staged_case_file"
        else "Read one allowlisted reviewer reference file. Use the relative references/name.md path from SKILL.md or the full skills/e2e-reviewer/references/name.md path.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
    }


class Bridge:
    def __init__(self, broker: Any) -> None:
        self.broker = broker
        self.initialized = False
        names = ["read_staged_case_file"]
        if broker.arm == "full":
            names.extend(["read_staged_skill_file", "run_staged_bundled_scanner"])
        self.tools = {name: tool_definition(name) for name in names}

    def handle(self, request: Any) -> dict[str, Any] | None:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return self.error(None, -32600, "invalid JSON-RPC request")
        request_id = request.get("id")
        method = request.get("method")
        if method == "notifications/initialized" and "id" not in request:
            if not self.initialized:
                return self.error(None, -32000, "server is not initialized")
            return None
        if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
            return self.error(None, -32600, "request id must be a string or integer")
        if method == "initialize":
            params = request.get("params")
            if not isinstance(params, dict) or not isinstance(params.get("protocolVersion"), str):
                return self.error(request_id, -32602, "invalid initialize parameters")
            self.initialized = True
            return self.result(request_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "reviewer-release-development", "version": "0.1.0"},
            })
        if not self.initialized:
            return self.error(request_id, -32000, "server is not initialized")
        if method == "ping":
            return self.result(request_id, {})
        if method == "tools/list":
            return self.result(request_id, {"tools": list(self.tools.values())})
        if method != "tools/call":
            return self.error(request_id, -32601, "method is not exposed")
        params = request.get("params")
        if not isinstance(params, dict) or set(params) not in ({"name", "arguments"}, {"_meta", "name", "arguments"}) or (
            "_meta" in params and not isinstance(params["_meta"], dict)
        ):
            return self.error(request_id, -32602, "invalid tool-call parameters")
        name, arguments = params["name"], params["arguments"]
        if not isinstance(name, str) or name not in self.tools or not isinstance(arguments, dict):
            return self.error(request_id, -32602, "tool is not exposed")
        try:
            if name == "run_staged_bundled_scanner":
                if arguments:
                    raise ValueError("scanner takes no arguments")
                data = self.broker.run_staged_bundled_scanner()
            else:
                if set(arguments) != {"path"} or not isinstance(arguments["path"], str):
                    raise ValueError("read requires exactly one path")
                data = getattr(self.broker, name)(arguments["path"])
            output = data.decode("utf-8", errors="strict")
        except (BROKER.ToolSurfaceError, UnicodeError, ValueError) as exc:
            return self.result(request_id, {
                "content": [{"type": "text", "text": f"DENIED: {type(exc).__name__}"}],
                "isError": True,
            })
        return self.result(request_id, {"content": [{"type": "text", "text": output}]})

    @staticmethod
    def result(request_id: str | int, value: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": value}

    @staticmethod
    def error(request_id: str | int | None, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def serve(bridge: Bridge, source: BinaryIO, sink: BinaryIO, journal: AuditJournal | None = None) -> None:
    if journal is not None:
        journal.append({
            "kind": "session_start",
            "arm": bridge.broker.arm,
            "source_root": bridge.broker.source_root,
            "case_files": bridge.broker.allowed_case,
            "skill_files": bridge.broker.allowed_skill,
            "scanner_files": bridge.broker.scanner_digests,
        })
    while line := source.readline(MAX_REQUEST_BYTES + 1):
        if len(line) > MAX_REQUEST_BYTES:
            raise ValueError("MCP request exceeds byte limit")
        if journal is not None:
            journal.append({"kind": "mcp_request", "raw_base64": base64.b64encode(line).decode("ascii")})
        prior_tools = len(bridge.broker.transcript) if journal is not None else 0
        try:
            request = loads_strict(line)
            response = bridge.handle(request)
        except (UnicodeError, json.JSONDecodeError, ValueError):
            response = Bridge.error(None, -32700, "invalid JSON request")
        if journal is not None:
            for entry in bridge.broker.transcript[prior_tools:]:
                journal.append({"kind": "broker_tool", "entry": entry})
        if response is not None:
            wire = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            if journal is not None:
                journal.append({"kind": "mcp_response_intent", "raw_base64": base64.b64encode(wire).decode("ascii")})
            sink.write(wire)
            sink.flush()
            if journal is not None:
                journal.append({"kind": "mcp_response_delivered"})
        elif journal is not None:
            journal.append({"kind": "mcp_notification_handled"})
    if journal is not None:
        journal.append({"kind": "server_eof"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--case-json", type=Path, required=True)
    parser.add_argument("--skill-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--arm", choices=("full", "catalog-only", "no-skill"), required=True)
    args = parser.parse_args()
    case = loads_strict(args.case_json.read_text(encoding="utf-8"))
    if not isinstance(case, dict) or set(case) != {"source_root", "source_files"}:
        parser.error("case JSON must contain source_root and source_files only")
    protocol = loads_strict(args.protocol.read_text(encoding="utf-8"))
    broker = BROKER.ReleaseToolSurface(args.bundle, case, args.skill_root, protocol["evaluation_surface"], args.workspace, arm=args.arm)
    journal = AuditJournal(broker.workspace / "mcp-transcript.jsonl")
    try:
        serve(Bridge(broker), sys.stdin.buffer, sys.stdout.buffer, journal)
    finally:
        journal.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
