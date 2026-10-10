#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline MCP dispatch checks; no model, credentials, or external calls."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import hashlib
import os
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/evals/reviewer-release-codex-mcp-v1.py"
SPEC = importlib.util.spec_from_file_location("reviewer_release_codex_mcp_v1", MODULE)
assert SPEC and SPEC.loader
MCP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MCP)


class FakeBroker:
    def __init__(self, arm: str) -> None:
        self.arm = arm
        self.calls: list[tuple[str, str | None]] = []

    def read_staged_case_file(self, path: str) -> bytes:
        self.calls.append(("case", path))
        if path != "sources/case-001/example.spec.ts":
            raise MCP.BROKER.ToolSurfaceError("private path and source detail")
        return b"test.only('example', () => {});\n"

    def read_staged_skill_file(self, path: str) -> bytes:
        self.calls.append(("skill", path))
        return b"# review\n"

    def run_staged_bundled_scanner(self) -> bytes:
        self.calls.append(("scan", None))
        return b"Summary: 1 total hit(s)\n"


def request(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    result = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        result["params"] = params
    return result


def exchange(bridge: MCP.Bridge, rows: list[dict]) -> list[dict]:
    source = io.BytesIO(b"".join(json.dumps(row).encode() + b"\n" for row in rows))
    sink = io.BytesIO()
    MCP.serve(bridge, source, sink)
    return [json.loads(line) for line in sink.getvalue().splitlines()]


def main() -> None:
    for arm, expected in (
        ("full", ["read_staged_case_file", "read_staged_skill_file", "run_staged_bundled_scanner"]),
        ("catalog-only", ["read_staged_case_file"]),
        ("no-skill", ["read_staged_case_file"]),
    ):
        broker = FakeBroker(arm)
        bridge = MCP.Bridge(broker)
        init = request("initialize", {"protocolVersion": MCP.PROTOCOL_VERSION})
        before = exchange(bridge, [request("tools/list")])[0]
        assert before["error"]["code"] == -32000
        early_notification = exchange(bridge, [{"jsonrpc": "2.0", "method": "notifications/initialized"}])[0]
        assert early_notification["error"]["code"] == -32000
        response = exchange(bridge, [init, request("tools/list"), request("ping")])
        assert response[0]["result"]["capabilities"] == {"tools": {}}
        assert [tool["name"] for tool in response[1]["result"]["tools"]] == expected
        assert response[2]["result"] == {}
        read = request("tools/call", {"name": "read_staged_case_file", "arguments": {"path": "sources/case-001/example.spec.ts"}})
        denied = request("tools/call", {"name": "read_staged_case_file", "arguments": {"path": "../../auth.json"}})
        hidden = request("tools/call", {"name": "read_staged_skill_file", "arguments": {"path": "skills/e2e-reviewer/SKILL.md"}})
        unknown = request("tools/call", {"name": "exec_command", "arguments": {}})
        malformed_name = request("tools/call", {"name": [], "arguments": {}})
        rows = exchange(bridge, [read, denied, unknown, malformed_name, request("resources/list"), hidden])
        assert "test.only" in rows[0]["result"]["content"][0]["text"]
        assert rows[1]["result"]["isError"] is True
        assert "private path" not in json.dumps(rows[1])
        assert rows[2]["error"]["code"] == -32602
        assert rows[3]["error"]["code"] == -32602
        assert rows[4]["error"]["code"] == -32601
        if arm == "full":
            assert rows[5]["result"]["content"][0]["text"] == "# review\n"
        else:
            assert rows[5]["error"]["code"] == -32602
            assert not any(call[0] == "skill" for call in broker.calls)
        with_meta = request("tools/call", {"_meta": {"progressToken": 7}, "name": "read_staged_case_file",
                                          "arguments": {"path": "sources/case-001/example.spec.ts"}})
        invalid_meta = request("tools/call", {"_meta": "not-an-object", "name": "read_staged_case_file",
                                             "arguments": {"path": "sources/case-001/example.spec.ts"}})
        unexpected = request("tools/call", {"_meta": {}, "name": "read_staged_case_file",
                                           "arguments": {"path": "sources/case-001/example.spec.ts"}, "extra": True})
        assert "test.only" in exchange(bridge, [with_meta])[0]["result"]["content"][0]["text"]
        assert exchange(bridge, [invalid_meta])[0]["error"]["code"] == -32602
        assert exchange(bridge, [unexpected])[0]["error"]["code"] == -32602
        scanner = request("tools/call", {"name": "run_staged_bundled_scanner", "arguments": {}})
        scanned = exchange(bridge, [scanner])[0]
        assert ("result" in scanned) == (arm == "full")

    bridge = MCP.Bridge(FakeBroker("full"))
    malformed = io.BytesIO(b'{"jsonrpc":"2.0","id":1,"id":2,"method":"initialize"}\n')
    sink = io.BytesIO()
    MCP.serve(bridge, malformed, sink)
    assert json.loads(sink.getvalue())["error"]["code"] == -32700
    sink = io.BytesIO()
    MCP.serve(bridge, io.BytesIO(b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":NaN}}\n'), sink)
    assert json.loads(sink.getvalue().splitlines()[0])["error"]["code"] == -32700
    try:
        MCP.serve(bridge, io.BytesIO(b"x" * (MCP.MAX_REQUEST_BYTES + 1)), io.BytesIO())
    except ValueError as exc:
        assert "byte limit" in str(exc)
    else:
        raise AssertionError("oversized MCP request was accepted")

    protocol = json.loads((ROOT / "scripts/evals/reviewer-release-v1-protocol.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="reviewer-release-mcp-v1-") as raw:
        root = Path(raw)
        source = root / "bundle/sources/case-001/example.spec.ts"
        source.parent.mkdir(parents=True)
        source.write_text("import { test } from '@playwright/test';\ntest.only('focused', () => {});\n", encoding="utf-8")
        case = {
            "source_root": "sources/case-001",
            "source_files": [{
                "path": "sources/case-001/example.spec.ts",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }],
        }
        real = MCP.BROKER.ReleaseToolSurface(
            root / "bundle", case, ROOT, protocol["evaluation_surface"], root / "workspace", arm="full"
        )
        bridge = MCP.Bridge(real)
        journal_path = real.workspace / "mcp-transcript.jsonl"
        journal = MCP.AuditJournal(journal_path)
        try:
            MCP.AuditJournal(journal_path)
        except FileExistsError:
            pass
        else:
            raise AssertionError("journal overwrote an existing trace")
        recorded = [request("initialize", {"protocolVersion": MCP.PROTOCOL_VERSION}),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            request("tools/call", {"name": "read_staged_case_file", "arguments": {"path": case["source_files"][0]["path"]}}),
            request("tools/call", {"name": "read_staged_skill_file", "arguments": {"path": "references/review-scope.md"}}),
            request("tools/call", {"name": "run_staged_bundled_scanner", "arguments": {}}),
        ]
        wire_in = io.BytesIO(b"".join(json.dumps(row).encode() + b"\n" for row in recorded))
        wire_out = io.BytesIO()
        try:
            MCP.serve(bridge, wire_in, wire_out, journal)
        finally:
            journal.close()
        output = [json.loads(line) for line in wire_out.getvalue().splitlines()]
        assert "test.only" in output[1]["result"]["content"][0]["text"]
        assert "Phase 0" in output[2]["result"]["content"][0]["text"]
        assert "#7" in output[3]["result"]["content"][0]["text"]
        assert [entry["tool"] for entry in real.transcript] == [
            "read_staged_case_file", "read_staged_skill_file", "run_staged_bundled_scanner"
        ]
        rows = [json.loads(line) for line in journal_path.read_bytes().splitlines()]
        assert MCP.verify_journal(journal_path) == len(rows)
        assert rows[0]["event"]["kind"] == "session_start"
        assert rows[0]["event"]["case_files"] == real.allowed_case
        assert rows[-1]["event"] == {"kind": "server_eof"}
        assert any(row["event"]["kind"] == "mcp_notification_handled" for row in rows)
        scanner_entry = next(row["event"]["entry"] for row in rows if row["event"]["kind"] == "broker_tool" and row["event"]["entry"]["tool"] == "run_staged_bundled_scanner")
        assert {"stdout_base64", "stderr_base64", "exit_code", "arguments", "environment"} <= set(scanner_entry)
        assert os.stat(journal_path).st_mode & 0o777 == 0o600
        journal_path.write_bytes(journal_path.read_bytes()[:-1])
        try:
            MCP.verify_journal(journal_path)
        except ValueError as exc:
            assert "incomplete" in str(exc)
        else:
            raise AssertionError("truncated journal was accepted")
        journal_path.write_bytes(b"".join(MCP.canonical_bytes(row) + b"\n" for row in rows))
        altered = [dict(row) for row in rows]
        altered[2]["event"] = {"kind": "mcp_response_delivered", "extra": "tampered"}
        journal_path.write_bytes(b"".join(MCP.canonical_bytes(row) + b"\n" for row in altered))
        try:
            MCP.verify_journal(journal_path)
        except ValueError as exc:
            assert "digest differs" in str(exc)
        else:
            raise AssertionError("tampered journal was accepted")
        failed_path = real.workspace / "failed-tool-transcript.jsonl"
        failed = MCP.AuditJournal(failed_path)
        failed_bridge = MCP.Bridge(real)
        failure_rows = [
            request("initialize", {"protocolVersion": MCP.PROTOCOL_VERSION}),
            request("tools/call", {"name": "read_staged_case_file", "arguments": {"path": "sources/case-001/.env"}}),
        ]
        try:
            MCP.serve(
                failed_bridge,
                io.BytesIO(b"".join(json.dumps(row).encode() + b"\n" for row in failure_rows)),
                io.BytesIO(),
                failed,
            )
        finally:
            failed.close()
        try:
            MCP.verify_journal(failed_path)
        except ValueError as exc:
            assert "failed model-visible" in str(exc)
        else:
            raise AssertionError("denied tool call was accepted as a valid trace")
        bad_json_path = real.workspace / "nan-transcript.jsonl"
        malformed_header = {
            "sequence": 0,
            "previous_sha256": "0" * 64,
            "event": {"kind": "session_start", "arm": float("nan"), "source_root": "sources/case-001",
                      "case_files": {}, "skill_files": {}, "scanner_files": {}},
        }
        malformed_header["sha256"] = hashlib.sha256(json.dumps(malformed_header, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        bad_json_path.write_text(json.dumps(malformed_header) + "\n", encoding="utf-8")
        try:
            MCP.verify_journal(bad_json_path)
        except ValueError as exc:
            assert "non-standard JSON constant" in str(exc)
        else:
            raise AssertionError("non-standard JSON journal was accepted")
    print("reviewer release Codex MCP v1: pass (offline arm tools, dispatch guards, and local journal)")


if __name__ == "__main__":
    main()
