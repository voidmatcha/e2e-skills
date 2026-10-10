#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline Codex JSONL / MCP journal reconciliation tests."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import base64


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/evals/reviewer-release-codex-transcript-v1.py"
SPEC = importlib.util.spec_from_file_location("reviewer_release_codex_transcript_v1", MODULE)
assert SPEC and SPEC.loader
TRACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRACE)
CALL_SPEC = importlib.util.spec_from_file_location(
    "reviewer_release_call_evidence_v1", ROOT / "scripts/evals/verify-reviewer-release-calls-v1.py"
)
assert CALL_SPEC and CALL_SPEC.loader
CALL = importlib.util.module_from_spec(CALL_SPEC)
CALL_SPEC.loader.exec_module(CALL)
ASSEMBLER_SPEC = importlib.util.spec_from_file_location(
    "reviewer_release_call_assembler_v1", ROOT / "scripts/evals/assemble-reviewer-release-call-v1.py"
)
assert ASSEMBLER_SPEC and ASSEMBLER_SPEC.loader
ASSEMBLER = importlib.util.module_from_spec(ASSEMBLER_SPEC)
ASSEMBLER_SPEC.loader.exec_module(ASSEMBLER)
MCP = TRACE.MCP
SERVER = "reviewer_release"
FILE = "sources/case-001/example.spec.ts"


class Broker:
    arm = "no-skill"
    source_root = "sources/case-001"
    allowed_case = {FILE: TRACE.digest(b"test('example', () => {});\n")}
    allowed_skill: dict[str, str] = {}
    scanner_digests: dict[str, str] = {}

    def __init__(self) -> None:
        self.transcript: list[dict] = []

    def read_staged_case_file(self, name: str) -> bytes:
        assert name == FILE
        data = b"test('example', () => {});\n"
        self.transcript.append({"tool": "read_staged_case_file", "arguments": {"path": name},
                                "result_sha256": TRACE.digest(data), "result_base64": base64.b64encode(data).decode()})
        return data


def denied(action, expected: str) -> None:
    try:
        action()
    except TRACE.TranscriptError as exc:
        assert expected in str(exc), (expected, str(exc))
    else:
        raise AssertionError(f"expected transcript rejection: {expected}")


def _denied_call(action) -> None:
    try:
        action()
    except CALL.CallEvidenceError:
        return
    raise AssertionError("expected call-evidence rejection")


def event_bytes(events: list[dict]) -> bytes:
    return b"".join(json.dumps(event, separators=(",", ":")).encode() + b"\n" for event in events)


def main() -> None:
    protocol = json.loads((ROOT / "scripts/evals/reviewer-release-v1-protocol.json").read_text(encoding="utf-8"))
    surface = protocol["evaluation_surface"]
    primary = protocol["execution_identity"]["primary"]
    runner_config = {
        "schema_version": 1, "protocol_id": "reviewer-release-v1",
        "host_id": primary["host_id"], "runner_family": primary["runner_family"],
        "model": primary["model"], "runner_version": primary["minimum_version"],
        "decoding_settings": surface["runner_decoding_settings"],
    }
    assert CALL.verified_runner_config(json.dumps(runner_config).encode(), surface, primary) == primary["minimum_version"]
    _denied_call(lambda: CALL.verified_runner_config(json.dumps({**runner_config, "model": "different"}).encode(), surface, primary))
    _denied_call(lambda: CALL.verified_runner_config(json.dumps({**runner_config, "runner_version": "0.151.9"}).encode(), surface, primary))
    _denied_call(lambda: CALL.verified_runner_config(json.dumps({**runner_config, "decoding_settings": "custom"}).encode(), surface, primary))
    two_paths = {FILE, "sources/case-001/second.pom.ts"}
    one_read = [{"name": "read_staged_case_file", "arguments": {"path": FILE}}]
    _denied_call(lambda: CALL.verify_required_case_reads(one_read, two_paths, "no-skill"))
    _denied_call(lambda: CALL.verify_required_case_reads(one_read, {FILE}, "full"))
    both_reads = [*one_read, {"name": "read_staged_case_file", "arguments": {"path": "sources/case-001/second.pom.ts"}}]
    CALL.verify_required_case_reads(both_reads, two_paths, "catalog-only")
    CALL.verify_required_case_reads([*both_reads, {"name": "run_staged_bundled_scanner", "arguments": {}}], two_paths, "full")
    expected_cases = {f"case-{index:03d}" for index in range(120)}
    signed_cases = {
        case_id: {"source_root": f"sources/{case_id}", "source_files": [
            {"path": f"sources/{case_id}/example.spec.ts", "sha256": TRACE.digest(b"test('example', () => {});\n")},
        ]}
        for case_id in expected_cases
    }
    frozen_skill_paths = set(surface["initial_model_visible_files"]["full"]) | set(surface["on_demand_skill_files"]["full"])
    frozen_skill_paths |= set(surface["initial_model_visible_files"]["catalog-only"])
    initial_skill_paths = set(surface["initial_model_visible_files"]["full"]) | set(surface["initial_model_visible_files"]["catalog-only"])
    frozen_snapshot = {
        "schema_version": 1, "protocol_id": "reviewer-release-v1",
        "skill_files": {path: TRACE.digest(f"reference for {path}".encode() if path in initial_skill_paths else path.encode()) for path in frozen_skill_paths},
        "scanner_files": {name: TRACE.digest(name.encode()) for name in MCP.BROKER.SCANNER_FILES},
    }
    evaluated = CALL.evaluated_skill_snapshot(json.dumps(frozen_snapshot).encode(), surface)
    _denied_call(lambda: CALL.evaluated_skill_snapshot(
        json.dumps({**frozen_snapshot, "skill_files": {}}).encode(), surface,
    ))
    matrix_rows = [
        {"case_id": case_id, "arm": arm, "repetition": repetition, "artifacts": {}}
        for case_id in sorted(expected_cases) for arm in CALL.ARMS for repetition in (1, 2, 3)
    ]
    assert len(CALL.indexed_rows(matrix_rows, expected_cases, "test", {"case_id", "arm", "repetition", "artifacts"})) == 1080
    _denied_call(lambda: CALL.indexed_rows(matrix_rows[:-1], expected_cases, "test", {"case_id", "arm", "repetition", "artifacts"}))
    _denied_call(lambda: CALL.indexed_rows([*matrix_rows[:-1], matrix_rows[0]], expected_cases, "test", {"case_id", "arm", "repetition", "artifacts"}))
    ordered_rows = [
        {"case_id": case_id, "arm": arm, "repetition": repetition, "artifacts": {}}
        for case_id, arm, repetition in CALL.PLAN.ordered_call_keys(list(expected_cases))
    ]
    CALL.verify_declared_schedule(ordered_rows, list(expected_cases), "test")
    _denied_call(lambda: CALL.verify_declared_schedule(matrix_rows, list(expected_cases), "test"))
    _denied_call(lambda: CALL.verify_declared_schedule([ordered_rows[1], ordered_rows[0], *ordered_rows[2:]], list(expected_cases), "test"))
    for arm in CALL.ARMS:
        initial_paths = surface["initial_model_visible_files"][arm]
        skill_paths = set(initial_paths) | set(surface["on_demand_skill_files"][arm])
        initial_bytes = {path: f"reference for {path}".encode() for path in initial_paths}
        skill_hashes = {path: evaluated["skill_files"][path] for path in skill_paths}
        scanner_hashes = {name: TRACE.digest(name.encode()) for name in MCP.BROKER.SCANNER_FILES} if arm == "full" else {}
        staged = {
            "schema_version": 1, "skill_files": skill_hashes, "scanner_files": scanner_hashes,
            "initial_content_base64": {path: base64.b64encode(data).decode() for path, data in initial_bytes.items()},
        }
        header = {"skill_files": skill_hashes, "scanner_files": scanner_hashes}
        assert CALL.verified_initial_material(json.dumps(staged).encode(), header, arm, surface, evaluated) == initial_bytes
        _denied_call(lambda: CALL.verified_initial_material(
            json.dumps({**staged, "schema_version": True}).encode(), header, arm, surface, evaluated,
        ))
        if initial_paths:
            _denied_call(lambda: CALL.verified_initial_material(
                json.dumps({**staged, "initial_content_base64": {path: base64.b64encode(b"changed").decode() for path in initial_paths}}).encode(),
                header, arm, surface, evaluated,
            ))
        if skill_paths:
            _denied_call(lambda: CALL.verified_initial_material(
                json.dumps(staged).encode(), {**header, "skill_files": {}}, arm, surface, evaluated,
            ))
        if skill_paths:
            _denied_call(lambda: CALL.verified_initial_material(
                json.dumps(staged).encode(), header, arm, surface,
                {**evaluated, "skill_files": {**evaluated["skill_files"], next(iter(skill_paths)): "0" * 64}},
            ))
    with tempfile.TemporaryDirectory(prefix="reviewer-release-codex-trace-v1-") as raw:
        journal_path = Path(raw) / "mcp-transcript.jsonl"
        journal = MCP.AuditJournal(journal_path)
        broker = Broker()
        bridge = MCP.Bridge(broker)
        requests = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": MCP.PROTOCOL_VERSION}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"_meta": {"progressToken": 7}, "name": "read_staged_case_file", "arguments": {"path": FILE}}},
        ]
        wire_out = io.BytesIO()
        try:
            MCP.serve(bridge, io.BytesIO(event_bytes(requests)), wire_out, journal)
        finally:
            journal.close()
        tool_output = json.loads(wire_out.getvalue().splitlines()[-1])["result"]
        final = '{"findings":[]}'
        started = {"id": "item_1", "type": "mcp_tool_call", "server": SERVER, "tool": "read_staged_case_file",
                   "arguments": {"path": FILE}, "result": None, "error": None, "status": "in_progress"}
        completed = {**started, "result": {"content": tool_output["content"], "structured_content": None}, "status": "completed"}
        events = [
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "turn.started"},
            {"type": "item.started", "item": started},
            {"type": "item.completed", "item": completed},
            {"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": final}},
            {"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 10}},
        ]
        signed_case = signed_cases["case-001"]
        prompt = CALL.PROMPT.common_prompt(surface, signed_case)
        stdout = event_bytes(events)
        kwargs = dict(prompt=prompt, stdout=stdout, stderr=b"", final_file=final.encode(),
                      journal=journal_path, expected_server=SERVER, expected_arm="no-skill", exit_code=0)
        result = TRACE.verify_capture(**kwargs)
        assert result["status"] == "complete_development_trace_only"
        assert result["mcp_tool_calls"] == 1
        assert result["prompt_sha256"] == TRACE.digest(prompt)
        assert TRACE.verify_capture(**{**kwargs, "journal": journal_path.read_bytes()}) == result
        call_files = {
            "prompt": prompt,
            "staged_case_manifest": json.dumps(signed_case).encode(),
            "staged_skill_manifest": json.dumps({
                "schema_version": 1, "skill_files": {}, "scanner_files": {},
                "initial_content_base64": {},
            }).encode(),
            "runner_config": json.dumps(runner_config).encode(),
            "codex_jsonl": stdout,
            "stderr": b"",
            "final_response": final.encode(),
            "mcp_journal": journal_path.read_bytes(),
            "transcript_report": json.dumps({
                "schema_version": 1, "protocol_id": "reviewer-release-v1",
                "case_id": "case-001", "arm": "no-skill", "repetition": 1,
                "exit_code": 0, "capture": result,
            }).encode(),
        }
        assembled = ASSEMBLER.assemble_call(
            case_id="case-001", arm="no-skill", repetition=1,
            case=signed_case, surface=surface, primary=primary,
            runner_version=primary["minimum_version"],
            staged_skill_files={}, staged_scanner_files={},
            prompt=prompt, codex_jsonl=stdout, stderr=b"",
            final_response=final.encode(), mcp_journal=journal_path.read_bytes(),
            completed_at="2026-09-23T09:00:00Z",
        )
        frozen_inputs = ASSEMBLER.assemble_inputs(
            arm="no-skill", case=signed_case, surface=surface, primary=primary,
            runner_version=primary["minimum_version"],
            staged_skill_files={}, staged_scanner_files={}, prompt=prompt,
        )
        assert frozen_inputs == assembled["inputs"]
        assert set(frozen_inputs) == CALL.INPUT_ROLES
        try:
            ASSEMBLER.assemble_inputs(
                arm="no-skill", case=signed_case, surface=surface, primary=primary,
                runner_version=primary["minimum_version"],
                staged_skill_files={}, staged_scanner_files={}, prompt=prompt + b"changed",
            )
        except ASSEMBLER.EVIDENCE.CallEvidenceError:
            pass
        else:
            raise AssertionError("pre-call input assembly accepted a changed prompt")
        for role in CALL.INPUT_ROLES:
            call_files[role] = assembled["inputs"][role]
        for role in CALL.OUTPUT_ROLES:
            call_files[role] = assembled["outputs"][role]
        assert assembled["response"]["normalized_finding_identities"] == []
        for invalid_header_event in (None, [], "not an object"):
            malformed_header = {"sequence": 0, "previous_sha256": None,
                                "event": invalid_header_event, "sha256": "0" * 64}
            try:
                ASSEMBLER.assemble_call(
                    case_id="case-001", arm="no-skill", repetition=1,
                    case=signed_case, surface=surface, primary=primary,
                    runner_version=primary["minimum_version"],
                    staged_skill_files={}, staged_scanner_files={},
                    prompt=prompt, codex_jsonl=stdout, stderr=b"",
                    final_response=final.encode(),
                    mcp_journal=json.dumps(malformed_header).encode() + b"\n",
                    completed_at="2026-09-23T09:00:00Z",
                )
            except ASSEMBLER.EVIDENCE.CallEvidenceError:
                pass
            else:
                raise AssertionError("assembler accepted a non-object MCP header event")
        try:
            ASSEMBLER.assemble_call(
                case_id="case-001", arm="no-skill", repetition=1,
                case=signed_case, surface=surface, primary=primary,
                runner_version=primary["minimum_version"],
                staged_skill_files={}, staged_scanner_files={},
                prompt=prompt + b"changed", codex_jsonl=stdout, stderr=b"",
                final_response=final.encode(), mcp_journal=journal_path.read_bytes(),
                completed_at="2026-09-23T09:00:00Z",
            )
        except ASSEMBLER.EVIDENCE.CallEvidenceError:
            pass
        else:
            raise AssertionError("assembler accepted a changed prompt")
        try:
            ASSEMBLER.assemble_call(
                case_id="case-001", arm="no-skill", repetition=1,
                case=signed_case, surface=surface, primary=primary,
                runner_version=primary["minimum_version"],
                staged_skill_files={}, staged_scanner_files={},
                prompt=prompt, codex_jsonl=stdout, stderr=b"",
                final_response=final.encode(), mcp_journal=b"",
                completed_at="2026-09-23T09:00:00Z",
            )
        except ASSEMBLER.EVIDENCE.CallEvidenceError:
            pass
        else:
            raise AssertionError("assembler accepted an empty MCP journal")
        refs = {}
        for role, data in call_files.items():
            (Path(raw) / f"{role}.bin").write_bytes(data)
            refs[role] = {"path": f"{role}.bin", "sha256": TRACE.digest(data)}
        identity = {"case_id": "case-001", "arm": "no-skill", "repetition": 1}
        input_row = {**identity, "artifacts": {role: refs[role] for role in CALL.INPUT_ROLES}}
        output_row = {**identity, "artifacts": {role: refs[role] for role in CALL.OUTPUT_ROLES}}
        response_row = assembled["response"]
        assert CALL.verify_call(Path(raw), input_row, output_row, response_row, signed_case, surface, evaluated, primary)["raw_output_sha256"] == TRACE.digest(final.encode())
        malformed_final = b"not JSON"
        malformed_events = json.loads(json.dumps(events))
        malformed_events[-2]["item"]["text"] = malformed_final.decode()
        invalid_packet = ASSEMBLER.assemble_call(
            case_id="case-001", arm="no-skill", repetition=1,
            case=signed_case, surface=surface, primary=primary,
            runner_version=primary["minimum_version"],
            staged_skill_files={}, staged_scanner_files={},
            prompt=prompt, codex_jsonl=event_bytes(malformed_events), stderr=b"",
            final_response=malformed_final, mcp_journal=journal_path.read_bytes(),
            completed_at="2026-09-23T09:00:00Z",
        )
        assert invalid_packet["response"]["valid"] is False
        assert invalid_packet["response"]["normalized_finding_identities"] is None
        invalid_refs = {}
        for role, data in {**invalid_packet["inputs"], **invalid_packet["outputs"]}.items():
            path = f"invalid-{role}.bin"
            (Path(raw) / path).write_bytes(data)
            invalid_refs[role] = {"path": path, "sha256": TRACE.digest(data)}
        invalid_inputs = {**identity, "artifacts": {role: invalid_refs[role] for role in CALL.INPUT_ROLES}}
        invalid_outputs = {**identity, "artifacts": {role: invalid_refs[role] for role in CALL.OUTPUT_ROLES}}
        checked_invalid = CALL.verify_call(
            Path(raw), invalid_inputs, invalid_outputs, invalid_packet["response"],
            signed_case, surface, evaluated, primary,
        )
        assert checked_invalid["valid"] is False
        _denied_call(lambda: CALL.verify_call(
            Path(raw), invalid_inputs, invalid_outputs,
            {**invalid_packet["response"], "valid": True},
            signed_case, surface, evaluated, primary,
        ))
        _denied_call(lambda: CALL.verify_call(
            Path(raw), invalid_inputs, invalid_outputs,
            {**invalid_packet["response"], "normalized_finding_identities": []},
            signed_case, surface, evaluated, primary,
        ))
        oversized_final = b'{"findings":[]}' + b" " * 65536
        oversized_events = json.loads(json.dumps(events))
        oversized_events[-2]["item"]["text"] = oversized_final.decode()
        oversized_packet = ASSEMBLER.assemble_call(
            case_id="case-001", arm="no-skill", repetition=1,
            case=signed_case, surface=surface, primary=primary,
            runner_version=primary["minimum_version"],
            staged_skill_files={}, staged_scanner_files={},
            prompt=prompt, codex_jsonl=event_bytes(oversized_events), stderr=b"",
            final_response=oversized_final, mcp_journal=journal_path.read_bytes(),
            completed_at="2026-09-23T09:00:00Z",
        )
        assert oversized_packet["response"]["valid"] is False
        oversized_refs = {}
        for role, data in {**oversized_packet["inputs"], **oversized_packet["outputs"]}.items():
            path = f"oversized-{role}.bin"
            (Path(raw) / path).write_bytes(data)
            oversized_refs[role] = {"path": path, "sha256": TRACE.digest(data)}
        assert CALL.verify_call(
            Path(raw),
            {**identity, "artifacts": {role: oversized_refs[role] for role in CALL.INPUT_ROLES}},
            {**identity, "artifacts": {role: oversized_refs[role] for role in CALL.OUTPUT_ROLES}},
            oversized_packet["response"], signed_case, surface, evaluated, primary,
        )["valid"] is False
        different_signed_case = {**signed_case, "source_files": [
            {**signed_case["source_files"][0], "sha256": "0" * 64},
        ]}
        _denied_call(lambda: CALL.verify_call(Path(raw), input_row, output_row, response_row, different_signed_case, surface, evaluated, primary))
        different_staged_bytes = json.dumps(different_signed_case).encode()
        (Path(raw) / "different-staged-case.json").write_bytes(different_staged_bytes)
        different_inputs = {**input_row, "artifacts": {**input_row["artifacts"],
            "staged_case_manifest": {"path": "different-staged-case.json", "sha256": TRACE.digest(different_staged_bytes)},
        }}
        _denied_call(lambda: CALL.verify_call(Path(raw), different_inputs, output_row, response_row, signed_case, surface, evaluated, primary))
        wrong_root_journal = Path(raw) / "wrong-root-journal.jsonl"
        forged = MCP.AuditJournal(wrong_root_journal)
        try:
            for row in [json.loads(line) for line in journal_path.read_bytes().splitlines()]:
                event = row["event"]
                if event["kind"] == "session_start":
                    event = {**event, "source_root": "sources/other"}
                forged.append(event)
        finally:
            forged.close()
        wrong_capture = TRACE.verify_capture(**{**kwargs, "journal": wrong_root_journal})
        wrong_report = json.dumps({
            "schema_version": 1, "protocol_id": "reviewer-release-v1",
            **identity, "exit_code": 0, "capture": wrong_capture,
        }).encode()
        (Path(raw) / "wrong-root-report.json").write_bytes(wrong_report)
        wrong_outputs = {**output_row, "artifacts": {**output_row["artifacts"],
            "mcp_journal": {"path": "wrong-root-journal.jsonl", "sha256": TRACE.digest(wrong_root_journal.read_bytes())},
            "transcript_report": {"path": "wrong-root-report.json", "sha256": TRACE.digest(wrong_report)},
        }}
        _denied_call(lambda: CALL.verify_call(Path(raw), input_row, wrong_outputs, response_row, signed_case, surface, evaluated, primary))
        second_path = "sources/case-001/second.pom.ts"
        second_digest = TRACE.digest(b"export const second = true;\n")
        two_file_case = {**signed_case, "source_files": [*signed_case["source_files"], {"path": second_path, "sha256": second_digest}]}
        two_file_journal = Path(raw) / "two-file-journal.jsonl"
        forged = MCP.AuditJournal(two_file_journal)
        try:
            for row in [json.loads(line) for line in journal_path.read_bytes().splitlines()]:
                event = row["event"]
                if event["kind"] == "session_start":
                    event = {**event, "case_files": {**event["case_files"], second_path: second_digest}}
                forged.append(event)
        finally:
            forged.close()
        two_file_prompt = CALL.PROMPT.common_prompt(surface, two_file_case)
        two_file_capture = TRACE.verify_capture(**{**kwargs, "prompt": two_file_prompt, "journal": two_file_journal})
        two_file_report = json.dumps({
            "schema_version": 1, "protocol_id": "reviewer-release-v1", **identity,
            "exit_code": 0, "capture": two_file_capture,
        }).encode()
        two_file_inputs = {**input_row, "artifacts": dict(input_row["artifacts"])}
        two_file_outputs = {**output_row, "artifacts": dict(output_row["artifacts"])}
        for role, name, data, refs_for_call in (
            ("prompt", "two-file-prompt.bin", two_file_prompt, two_file_inputs["artifacts"]),
            ("staged_case_manifest", "two-file-case.json", json.dumps(two_file_case).encode(), two_file_inputs["artifacts"]),
            ("mcp_journal", "two-file-journal.jsonl", two_file_journal.read_bytes(), two_file_outputs["artifacts"]),
            ("transcript_report", "two-file-report.json", two_file_report, two_file_outputs["artifacts"]),
        ):
            (Path(raw) / name).write_bytes(data)
            refs_for_call[role] = {"path": name, "sha256": TRACE.digest(data)}
        try:
            CALL.verify_call(Path(raw), two_file_inputs, two_file_outputs, response_row, two_file_case, surface, evaluated, primary)
        except CALL.CallEvidenceError as exc:
            assert "every signed case source file" in str(exc), str(exc)
        else:
            raise AssertionError("a model call that read only one of two signed source files was accepted")
        wrong_prompt = prompt + b"\nExtra instruction not in the common task."
        (Path(raw) / "wrong-prompt.bin").write_bytes(wrong_prompt)
        wrong_prompt_capture = TRACE.verify_capture(**{**kwargs, "prompt": wrong_prompt})
        wrong_prompt_report = json.dumps({
            "schema_version": 1, "protocol_id": "reviewer-release-v1",
            **identity, "exit_code": 0, "capture": wrong_prompt_capture,
        }).encode()
        (Path(raw) / "wrong-prompt-report.json").write_bytes(wrong_prompt_report)
        wrong_prompt_inputs = {**input_row, "artifacts": {**input_row["artifacts"],
            "prompt": {"path": "wrong-prompt.bin", "sha256": TRACE.digest(wrong_prompt)},
        }}
        wrong_prompt_outputs = {**output_row, "artifacts": {**output_row["artifacts"],
            "transcript_report": {"path": "wrong-prompt-report.json", "sha256": TRACE.digest(wrong_prompt_report)},
        }}
        _denied_call(lambda: CALL.verify_call(Path(raw), wrong_prompt_inputs, wrong_prompt_outputs, response_row, signed_case, surface, evaluated, primary))
        _denied_call(lambda: CALL.verify_call(Path(raw), input_row, output_row, {**response_row, "raw_output_sha256": "0" * 64}, signed_case, surface, evaluated, primary))
        (Path(raw) / "final_response.bin").write_bytes(b'{"findings":[{}]}')
        _denied_call(lambda: CALL.verify_call(Path(raw), input_row, output_row, response_row, signed_case, surface, evaluated, primary))
        incomplete_inventory = {
            "schema_version": 1, "protocol_id": "reviewer-release-v1", "corpus_id": "external-corpus-001", "calls": [],
        }
        inventory_bytes = json.dumps(incomplete_inventory).encode()
        (Path(raw) / "all_inputs.json").write_bytes(inventory_bytes)
        inventory_ref = {"path": "all_inputs.json", "sha256": TRACE.digest(inventory_bytes)}
        snapshot_bytes = json.dumps(frozen_snapshot).encode()
        (Path(raw) / "evaluated-skill.json").write_bytes(snapshot_bytes)
        snapshot_ref = {"path": "evaluated-skill.json", "sha256": TRACE.digest(snapshot_bytes)}
        _denied_call(lambda: CALL.verify_matrix(Path(raw), snapshot_ref, inventory_ref, inventory_ref, inventory_ref, signed_cases, "external-corpus-001", surface, primary))
        _denied_call(lambda: CALL.verify_matrix(Path(raw), snapshot_ref, inventory_ref, inventory_ref, inventory_ref, signed_cases, "different-corpus", surface, primary))
        assert MCP.verify_journal(journal_path.read_bytes()) == MCP.verify_journal(journal_path)
        codex_shutdown_journal = Path(raw) / "codex-shutdown-transcript.jsonl"
        incomplete = MCP.AuditJournal(codex_shutdown_journal)
        try:
            for row in [json.loads(line) for line in journal_path.read_bytes().splitlines()][:-1]:
                incomplete.append(row["event"])
        finally:
            incomplete.close()
        try:
            MCP.verify_journal(codex_shutdown_journal)
        except ValueError as exc:
            assert "normal-end" in str(exc)
        else:
            raise AssertionError("an open journal passed strict verification")
        assert TRACE.verify_capture(**{**kwargs, "journal": codex_shutdown_journal})["mcp_tool_calls"] == 1
        partial_journal = Path(raw) / "partial-transcript.jsonl"
        partial = MCP.AuditJournal(partial_journal)
        try:
            for row in [json.loads(line) for line in journal_path.read_bytes().splitlines()][:-2]:
                partial.append(row["event"])
        finally:
            partial.close()
        denied(lambda: TRACE.verify_capture(**{**kwargs, "journal": partial_journal}), "journal is incomplete or invalid")
        linked_journal = Path(raw) / "linked-transcript.jsonl"
        linked_journal.symlink_to(journal_path)
        denied(lambda: TRACE.verify_capture(**{**kwargs, "journal": linked_journal}), "journal is incomplete or invalid")
        forged_journal = Path(raw) / "forged-broker-transcript.jsonl"
        forged = MCP.AuditJournal(forged_journal)
        try:
            for row in [json.loads(line) for line in journal_path.read_bytes().splitlines()]:
                event = row["event"]
                if event["kind"] == "broker_tool":
                    event = {"kind": "broker_tool", "entry": {**event["entry"],
                        "result_base64": base64.b64encode(b"forged broker output").decode(),
                        "result_sha256": TRACE.digest(b"forged broker output")}}
                forged.append(event)
        finally:
            forged.close()
        assert MCP.verify_journal(forged_journal) > 0
        denied(lambda: TRACE.verify_capture(**{**kwargs, "journal": forged_journal}), "declared bytes")
        forged_response = Path(raw) / "forged-response-transcript.jsonl"
        forged = MCP.AuditJournal(forged_response)
        fake_content = [{"type": "text", "text": "forged model-visible content"}]
        try:
            for row in [json.loads(line) for line in journal_path.read_bytes().splitlines()]:
                event = row["event"]
                if event["kind"] == "mcp_response_intent":
                    response = json.loads(base64.b64decode(event["raw_base64"]))
                    if response.get("id") == 2:
                        response["result"]["content"] = fake_content
                        event = {"kind": "mcp_response_intent", "raw_base64":
                            base64.b64encode(event_bytes([response])).decode()}
                forged.append(event)
        finally:
            forged.close()
        fake_events = [dict(event) for event in events]
        fake_events[3] = {"type": "item.completed", "item": {**completed,
            "result": {"content": fake_content, "structured_content": None}}}
        assert MCP.verify_journal(forged_response) > 0
        denied(lambda: TRACE.verify_capture(**{**kwargs, "journal": forged_response,
            "stdout": event_bytes(fake_events)}), "response content differs from the broker result")
        forged_arm = Path(raw) / "forged-arm-transcript.jsonl"
        forged = MCP.AuditJournal(forged_arm)
        try:
            for row in [json.loads(line) for line in journal_path.read_bytes().splitlines()]:
                event = row["event"]
                if event["kind"] == "session_start":
                    event = {**event, "skill_files": {FILE: TRACE.digest(b"test('example', () => {});\n")}}
                elif event["kind"] == "mcp_request":
                    request = json.loads(base64.b64decode(event["raw_base64"]))
                    if request.get("method") == "tools/call":
                        request["params"]["name"] = "read_staged_skill_file"
                        event = {"kind": "mcp_request", "raw_base64": base64.b64encode(event_bytes([request])).decode()}
                elif event["kind"] == "broker_tool":
                    event = {"kind": "broker_tool", "entry": {**event["entry"], "tool": "read_staged_skill_file"}}
                forged.append(event)
        finally:
            forged.close()
        skill_events = [dict(event) for event in events]
        skill_events[2] = {"type": "item.started", "item": {**started, "tool": "read_staged_skill_file"}}
        skill_events[3] = {"type": "item.completed", "item": {**completed, "tool": "read_staged_skill_file"}}
        assert MCP.verify_journal(forged_arm) > 0
        denied(lambda: TRACE.verify_capture(**{**kwargs, "journal": forged_arm,
            "stdout": event_bytes(skill_events)}), "files are incompatible with the arm")
        forged_tool = Path(raw) / "forged-tool-transcript.jsonl"
        forged = MCP.AuditJournal(forged_tool)
        try:
            for row in [json.loads(line) for line in forged_arm.read_bytes().splitlines()]:
                event = row["event"]
                if event["kind"] == "session_start":
                    event = {**event, "skill_files": {}}
                forged.append(event)
        finally:
            forged.close()
        denied(lambda: TRACE.verify_capture(**{**kwargs, "journal": forged_tool,
            "stdout": event_bytes(skill_events)}), "tool is not allowed for the recorded arm")
        denied(lambda: TRACE.verify_capture(**{**kwargs, "expected_arm": "full"}), "arm differs")
        denied(lambda: TRACE.verify_capture(**{**kwargs, "exit_code": 1}), "invocation failed")
        denied(lambda: TRACE.verify_capture(**{**kwargs, "final_file": b'{"findings":[1]}'}), "final-message file differs")
        denied(lambda: TRACE.verify_capture(**{**kwargs, "stdout": stdout[:-1]}), "incomplete")
        denied(lambda: TRACE.verify_capture(**{**kwargs, "stdout": event_bytes(events[:-1])}), "terminal success")
        bad_command = [*events[:2], {"type": "item.completed", "item": {"id": "item_0", "type": "command_execution", "command": "cat auth.json"}}, *events[2:]]
        denied(lambda: TRACE.verify_capture(**{**kwargs, "stdout": event_bytes(bad_command)}), "unapproved item")
        bad_tool = [dict(event) for event in events]
        bad_tool[3] = {"type": "item.completed", "item": {**completed, "arguments": {"path": "sources/case-001/other.ts"}}}
        denied(lambda: TRACE.verify_capture(**{**kwargs, "stdout": event_bytes(bad_tool)}), "start/completion mismatch")
        missing_tool = [*events[:2], *events[4:]]
        denied(lambda: TRACE.verify_capture(**{**kwargs, "stdout": event_bytes(missing_tool)}), "differ from the broker journal")
        bad_result = [dict(event) for event in events]
        bad_result[3] = {"type": "item.completed", "item": {**completed, "result": {"content": [{"type": "text", "text": "forged"}]}}}
        denied(lambda: TRACE.verify_capture(**{**kwargs, "stdout": event_bytes(bad_result)}), "differ from the broker journal")
        bad_server = [dict(event) for event in events]
        bad_server[2] = {"type": "item.started", "item": {**started, "server": "other"}}
        denied(lambda: TRACE.verify_capture(**{**kwargs, "stdout": event_bytes(bad_server)}), "unexpected MCP server")
    print("reviewer release Codex transcript v1: pass (offline complete trace and fail-closed mismatches)")


if __name__ == "__main__":
    main()
