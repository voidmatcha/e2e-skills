#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline safety checks for the one-call development capture adapter."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evals/capture-reviewer-release-call-v1.py"
PROTOCOL = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"
SPEC = importlib.util.spec_from_file_location("reviewer_release_capture_v1", SCRIPT)
assert SPEC and SPEC.loader
CAPTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPTURE)


def rejects(fn, error: type[Exception]) -> None:
    try:
        fn()
    except error:
        return
    raise AssertionError(f"expected {error.__name__}")


def test_preflight(root: Path) -> None:
    bundle = root / "bundle"
    source = bundle / "sources/case-001/example.spec.ts"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"test('example', () => {});\n")
    case = {
        "source_root": "sources/case-001",
        "source_files": [{"path": "sources/case-001/example.spec.ts", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
    }
    case_path = bundle / "case.json"
    case_path.write_text(json.dumps(case), encoding="utf-8")
    for arm in ("full", "catalog-only", "no-skill"):
        protocol, parsed, skill, scanner, prompt, case_bytes, protocol_bytes = CAPTURE.prepare_inputs(bundle, case_path, ROOT, PROTOCOL, arm)
        assert parsed == case
        assert case_bytes == case_path.read_bytes()
        assert protocol_bytes == PROTOCOL.read_bytes()
        assert prompt and protocol["evaluation_surface"]["status"] == "DESIGNED_NOT_IMPLEMENTED"
        rejects(lambda: CAPTURE.prepare_input_bytes(bundle, case_bytes, ROOT, protocol_bytes, arm,
                                                    frozen_protocol_sha256=hashlib.sha256(protocol_bytes).hexdigest()), CAPTURE.CaptureError)
        assert ("skills/e2e-reviewer/SKILL.md" in skill) == (arm == "full")
        assert bool(scanner) == (arm == "full")
        frozen = CAPTURE.ASSEMBLE.assemble_inputs(
            arm=arm, case=case, surface=protocol["evaluation_surface"],
            primary=protocol["execution_identity"]["primary"],
            runner_version="0.155.1", staged_skill_files=skill,
            staged_scanner_files=scanner, prompt=prompt,
        )
        assert set(frozen) == CAPTURE.CALL.INPUT_ROLES and frozen["prompt"] == prompt
        command = CAPTURE.command_for(sys.executable, sys.executable, root, bundle, case_path, ROOT, PROTOCOL, arm)
        assert command[:3] == [sys.executable, "exec", "--json"]
        assert command.count("--sandbox") == 1 and command[command.index("--sandbox") + 1] == "read-only"
        assert "-c" in command and "features.shell_tool=false" in command
        assert "features.apps=false" in command and "features.multi_agent=false" in command
        assert 'web_search="disabled"' in command
        assert command[-1] == "-"
    output = root / "new-artifact"
    CAPTURE.checked_artifact_dir(output, bundle, ROOT)
    rejects(lambda: CAPTURE.checked_artifact_dir(bundle / "output", bundle, ROOT), CAPTURE.CaptureError)
    rejects(lambda: CAPTURE.checked_artifact_dir(ROOT / "output", bundle, ROOT), CAPTURE.CaptureError)
    evidence_outputs = bundle / "calls"
    evidence_outputs.mkdir()
    CAPTURE.checked_artifact_dir(evidence_outputs / "0000", bundle, ROOT, evidence_output_root=evidence_outputs)
    rejects(lambda: CAPTURE.checked_artifact_dir(bundle / "output", bundle, ROOT, evidence_output_root=evidence_outputs), CAPTURE.CaptureError)
    rejects(lambda: CAPTURE.checked_artifact_dir(evidence_outputs / "nested" / "0000", bundle, ROOT, evidence_output_root=evidence_outputs), CAPTURE.CaptureError)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--bundle", str(bundle), "--case-json", str(case_path),
         "--skill-root", str(ROOT), "--protocol", str(PROTOCOL), "--runner-path", str(Path(sys.executable).resolve()),
         "--artifact-dir", str(output), "--case-id", "case-001", "--repetition", "1", "--arm", "no-skill"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout)["status"] == "PREFLIGHT_ONLY"
    assert not output.exists()
    test_pre_call_input_freeze(root, bundle, case_path)
    test_begin_boundary(root, bundle, case_path)
    test_end_boundary(root, bundle, case_path)
    source.write_bytes(b"changed\n")
    rejects(lambda: CAPTURE.prepare_inputs(bundle, case_path, ROOT, PROTOCOL, "no-skill"), CAPTURE.CaptureError)


def test_pre_call_input_freeze(root: Path, bundle: Path, case_path: Path) -> None:
    artifact = root / "pre-call"
    original_argv = sys.argv
    original_run = CAPTURE.subprocess.run
    original_popen = CAPTURE.subprocess.Popen
    original_clean_env = CAPTURE.HOLDOUT.clean_env
    original_stage_auth = CAPTURE.HOLDOUT.stage_codex_auth
    original_assemble_inputs = CAPTURE.ASSEMBLE.assemble_inputs
    observed = []

    def fake_popen(command, **kwargs):
        assert kwargs["stdin"] == subprocess.PIPE
        assert json.loads((artifact / "attempt.json").read_bytes())["status"] == "LAUNCH_BOUNDARY_CROSSED"
        frozen = artifact / "inputs"
        assert {path.name for path in frozen.iterdir()} == CAPTURE.CALL.INPUT_ROLES
        assert (frozen / "prompt").read_bytes() == (artifact / "prompt.txt").read_bytes()
        assert json.loads((frozen / "staged_case_manifest").read_bytes())["source_root"] == "sources/case-001"
        observed.append(command)
        raise OSError("stop before model launch")

    try:
        sys.argv = [str(SCRIPT), "--bundle", str(bundle), "--case-json", str(case_path),
                    "--skill-root", str(ROOT), "--protocol", str(PROTOCOL),
                    "--runner-path", str(Path(sys.executable).resolve()),
                    "--artifact-dir", str(artifact), "--case-id", "case-001",
                    "--repetition", "1", "--arm", "no-skill", "--execute"]
        CAPTURE.subprocess.run = lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, b"codex-cli 0.155.1\n", b"")
        CAPTURE.subprocess.Popen = fake_popen
        CAPTURE.HOLDOUT.clean_env = lambda *args: {}
        CAPTURE.HOLDOUT.stage_codex_auth = lambda path: path
        output = io.StringIO()
        with redirect_stdout(output):
            result = CAPTURE.main()
        assert result == 2 and len(observed) == 1
        assert json.loads(output.getvalue())["status"] == "INCOMPLETE"
        assert json.loads(output.getvalue())["model_execution_attempted"] is True

        sys.argv[sys.argv.index("--artifact-dir") + 1] = str(root / "assembly-failure")

        def fail_assembly(**_kwargs):
            raise CAPTURE.ASSEMBLE.EVIDENCE.CallEvidenceError("frozen inputs rejected")

        CAPTURE.ASSEMBLE.assemble_inputs = fail_assembly
        output = io.StringIO()
        with redirect_stdout(output):
            result = CAPTURE.main()
        assert result == 2 and len(observed) == 1
        assert json.loads(output.getvalue())["status"] == "INCOMPLETE"
        assert json.loads(output.getvalue())["model_execution_attempted"] is False
    finally:
        sys.argv = original_argv
        CAPTURE.subprocess.run = original_run
        CAPTURE.subprocess.Popen = original_popen
        CAPTURE.HOLDOUT.clean_env = original_clean_env
        CAPTURE.HOLDOUT.stage_codex_auth = original_stage_auth
        CAPTURE.ASSEMBLE.assemble_inputs = original_assemble_inputs


def test_begin_boundary(root: Path, bundle: Path, case_path: Path) -> None:
    protocol, case, skill, scanner, prompt, case_bytes, protocol_bytes = CAPTURE.prepare_inputs(bundle, case_path, ROOT, PROTOCOL, "no-skill")

    def prepared(name: str):
        return CAPTURE.prepare_call(
            root=root / name, runner=sys.executable, bundle=bundle, skill_root=ROOT,
            protocol=protocol, case=case, skill=skill, scanner=scanner,
            prompt=prompt, case_bytes=case_bytes, protocol_bytes=protocol_bytes,
            environment={}, runner_version="0.155.1", case_id="case-001",
            arm="no-skill", repetition=1,
        )

    original_popen = CAPTURE.subprocess.Popen
    launches = []

    def fake_popen(*_args, **_kwargs):
        launches.append("popen")
        raise OSError("fake runner stopped")

    try:
        CAPTURE.subprocess.Popen = fake_popen
        refused = prepared("begin-refused")

        def refuse(paths):
            assert set(paths) == CAPTURE.CALL.INPUT_ROLES
            raise CAPTURE.CaptureError("witness refused begin")

        rejects(lambda: CAPTURE.execute_prepared_call(refused, acknowledge_begin=refuse), CAPTURE.CaptureError)
        assert not launches and not (refused.root / "attempt.json").exists()

        tampered = prepared("begin-tampered")

        def mutate(paths):
            paths["prompt"].write_bytes(b"changed after begin")

        rejects(lambda: CAPTURE.execute_prepared_call(tampered, acknowledge_begin=mutate), CAPTURE.CaptureError)
        assert not launches and not (tampered.root / "attempt.json").exists()

        for name in ("prompt.txt", "case.json", "protocol.json"):
            changed = prepared(f"begin-changed-{name}")

            def change_runner_source(_paths, target=changed.root / name):
                target.write_bytes(b"changed after begin")

            rejects(lambda: CAPTURE.execute_prepared_call(changed, acknowledge_begin=change_runner_source), CAPTURE.CaptureError)
            assert not launches and not (changed.root / "attempt.json").exists()

        admitted = prepared("begin-admitted")
        events = []

        def acknowledge(paths):
            assert all(paths[role].read_bytes() == admitted.frozen_inputs[role] for role in paths)
            events.append("begin")

        def mark_attempt():
            events.append("attempt")

        rejects(lambda: CAPTURE.execute_prepared_call(admitted, acknowledge_begin=acknowledge, on_attempt=mark_attempt), OSError)
        assert events == ["begin", "attempt"] and launches == ["popen"]
        assert (admitted.root / "attempt.json").exists()
        rejects(lambda: CAPTURE.execute_prepared_call(admitted, acknowledge_begin=acknowledge, on_attempt=mark_attempt), FileExistsError)
        assert launches == ["popen"]
    finally:
        CAPTURE.subprocess.Popen = original_popen


def test_end_boundary(root: Path, bundle: Path, case_path: Path) -> None:
    protocol, case, skill, scanner, prompt, case_bytes, protocol_bytes = CAPTURE.prepare_inputs(bundle, case_path, ROOT, PROTOCOL, "no-skill")

    def prepared(name: str):
        call = CAPTURE.prepare_call(
            root=root / name, runner=sys.executable, bundle=bundle, skill_root=ROOT,
            protocol=protocol, case=case, skill=skill, scanner=scanner,
            prompt=prompt, case_bytes=case_bytes, protocol_bytes=protocol_bytes,
            environment={}, runner_version="0.155.1", case_id="case-001",
            arm="no-skill", repetition=1,
        )
        (call.root / "workspace").mkdir()
        (call.root / "final.txt").write_bytes(b"final")
        (call.root / "workspace" / "mcp-transcript.jsonl").write_bytes(b"journal\n")
        return call

    original_assemble = CAPTURE.ASSEMBLE.assemble_call

    def fake_assemble(**_kwargs):
        return {
            "inputs": expected_inputs,
            "outputs": {role: role.encode() for role in CAPTURE.CALL.OUTPUT_ROLES},
            "response": {"case_id": "case-001", "arm": "no-skill", "repetition": 1},
        }

    def mark(call):
        CAPTURE.private_write(call.root / "attempt.json", CAPTURE.ASSEMBLE.json_bytes({
            "case_id": "case-001", "arm": "no-skill", "repetition": 1,
            "prompt_sha256": hashlib.sha256(prompt).hexdigest(),
            "status": "LAUNCH_BOUNDARY_CROSSED",
        }))

    try:
        CAPTURE.ASSEMBLE.assemble_call = fake_assemble
        missing = prepared("end-no-attempt")
        rejects(lambda: CAPTURE.finalize_call(missing, 0, b"stdout", b"stderr"), CAPTURE.CaptureError)
        assert not (missing.root / "outputs").exists()

        admitted = prepared("end-admitted")
        expected_inputs = admitted.frozen_inputs
        mark(admitted)
        seen = []

        def acknowledge(paths):
            assert set(paths) == CAPTURE.CALL.OUTPUT_ROLES
            assert all(paths[role].read_bytes() == role.encode() for role in paths)
            seen.append("end")

        CAPTURE.finalize_call(admitted, 0, b"stdout", b"stderr", acknowledge_end=acknowledge)
        assert seen == ["end"] and (admitted.root / "response.json").exists()

        refused = prepared("end-refused")
        expected_inputs = refused.frozen_inputs
        mark(refused)

        def refuse(_paths):
            raise CAPTURE.CaptureError("witness refused end")

        rejects(lambda: CAPTURE.finalize_call(refused, 0, b"stdout", b"stderr", acknowledge_end=refuse), CAPTURE.CaptureError)
        assert {path.name for path in (refused.root / "outputs").iterdir()} == CAPTURE.CALL.OUTPUT_ROLES
        assert not (refused.root / "response.json").exists()

        tampered = prepared("end-tampered")
        expected_inputs = tampered.frozen_inputs
        mark(tampered)

        def mutate(paths):
            paths["final_response"].write_bytes(b"changed after end")

        rejects(lambda: CAPTURE.finalize_call(tampered, 0, b"stdout", b"stderr", acknowledge_end=mutate), CAPTURE.CaptureError)
        assert not (tampered.root / "response.json").exists()

        changed_input = prepared("end-changed-input")
        expected_inputs = changed_input.frozen_inputs
        mark(changed_input)

        def change_input(_paths):
            (changed_input.root / "case.json").write_bytes(b"changed after end")

        rejects(lambda: CAPTURE.finalize_call(changed_input, 0, b"stdout", b"stderr", acknowledge_end=change_input), CAPTURE.CaptureError)
        assert not (changed_input.root / "response.json").exists()
    finally:
        CAPTURE.ASSEMBLE.assemble_call = original_assemble


def test_capture_limits(root: Path) -> None:
    success = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'out'); sys.stderr.buffer.write(b'err')"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    stdout, stderr = CAPTURE.communicate_bounded(success, [sys.executable], b"", root / "ok.jsonl", root / "ok.stderr")
    assert success.returncode == 0 and stdout == b"out" and stderr == b"err"
    assert (root / "ok.jsonl").read_bytes() == stdout
    assert (root / "ok.stderr").read_bytes() == stderr

    prompt = bytes(range(256)) * 1024
    digest = hashlib.sha256(prompt).hexdigest().encode()
    receiving = subprocess.Popen(
        [sys.executable, "-c", "import hashlib,sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(hashlib.sha256(data).hexdigest().encode())"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    stdout, stderr = CAPTURE.communicate_bounded(receiving, [sys.executable], prompt, root / "prompt.jsonl", root / "prompt.stderr")
    assert receiving.returncode == 0 and stdout == digest and stderr == b""

    bidirectional = subprocess.Popen(
        [sys.executable, "-c", "import hashlib,sys; sys.stdout.buffer.write(b'x' * 131072); sys.stdout.flush(); data=sys.stdin.buffer.read(); sys.stderr.buffer.write(hashlib.sha256(data).hexdigest().encode())"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    stdout, stderr = CAPTURE.communicate_bounded(bidirectional, [sys.executable], prompt, root / "bidirectional.jsonl", root / "bidirectional.stderr")
    assert bidirectional.returncode == 0 and stdout == b"x" * 131072 and stderr == digest

    closed = subprocess.Popen(
        [sys.executable, "-c", "import os,sys,time; os.close(0); sys.stdout.buffer.write(b'partial'); sys.stdout.flush(); time.sleep(0.1)"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    try:
        rejects(lambda: CAPTURE.communicate_bounded(closed, [sys.executable], prompt, root / "closed.jsonl", root / "closed.stderr"), BrokenPipeError)
    finally:
        CAPTURE.kill_group(closed)
    assert (root / "closed.jsonl").exists()

    old_timeout = CAPTURE.TIMEOUT
    CAPTURE.TIMEOUT = 0.2
    timed = subprocess.Popen(
        [sys.executable, "-c", "import sys,time; sys.stdout.buffer.write(b'partial'); sys.stdout.flush(); time.sleep(10)"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    try:
        rejects(lambda: CAPTURE.communicate_bounded(timed, [sys.executable], b"prompt", root / "timed.jsonl", root / "timed.stderr"), subprocess.TimeoutExpired)
    finally:
        CAPTURE.kill_group(timed)
        CAPTURE.TIMEOUT = old_timeout
    assert (root / "timed.jsonl").read_bytes() == b"partial"
    assert timed.poll() is not None

    old_limit = CAPTURE.MAX_STDOUT
    CAPTURE.MAX_STDOUT = 3
    oversized = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'too long'); sys.stdout.flush()"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    )
    try:
        rejects(lambda: CAPTURE.communicate_bounded(oversized, [sys.executable], b"prompt", root / "large.jsonl", root / "large.stderr"), CAPTURE.CaptureError)
    finally:
        CAPTURE.kill_group(oversized)
        CAPTURE.MAX_STDOUT = old_limit


def test_execution_event_payload() -> None:
    assemble = CAPTURE.ASSEMBLE
    inputs = {role: {"path": f"calls/001/inputs/{role}", "sha256": hashlib.sha256(role.encode()).hexdigest()} for role in CAPTURE.CALL.INPUT_ROLES}
    outputs = {role: {"path": f"calls/001/outputs/{role}", "sha256": hashlib.sha256(role.encode()).hexdigest()} for role in CAPTURE.CALL.OUTPUT_ROLES}
    common = {"corpus_id": "sealed-corpus", "case_id": "case-001", "arm": "no-skill", "repetition": 1}
    begin = assemble.execution_event_payload(**common, event_index=0, previous_sha256="0" * 64, stage="begin", artifacts=inputs)
    assert not begin.endswith(b"\n")
    assert json.loads(begin) == {
        "schema_version": 1, "protocol_id": "reviewer-release-v1", **common,
        "event_index": 0, "previous_sha256": "0" * 64, "stage": "begin", "artifacts": inputs,
    }
    end = assemble.execution_event_payload(**common, event_index=1, previous_sha256=hashlib.sha256(begin).hexdigest(), stage="end", artifacts=outputs)
    assert json.loads(end)["previous_sha256"] == hashlib.sha256(begin).hexdigest()
    invalid = assemble.EVIDENCE.CallEvidenceError
    rejects(lambda: assemble.execution_event_payload(**common, event_index=0, previous_sha256="0" * 64, stage="end", artifacts=outputs), invalid)
    rejects(lambda: assemble.execution_event_payload(**common, event_index=0, previous_sha256="f" * 64, stage="begin", artifacts=inputs), invalid)
    rejects(lambda: assemble.execution_event_payload(**common, event_index=0, previous_sha256="0" * 64, stage="begin", artifacts=outputs), invalid)
    reused = {role: {"path": "same", "sha256": "a" * 64} for role in inputs}
    rejects(lambda: assemble.execution_event_payload(**common, event_index=0, previous_sha256="0" * 64, stage="begin", artifacts=reused), invalid)


def test_witness_artifact_access(root: Path) -> None:
    group_id = CAPTURE.os.getegid()
    call = root / "shared-call"
    CAPTURE.witness_directory(call, group_id)
    assert call.stat().st_uid == CAPTURE.os.geteuid()
    assert call.stat().st_gid == group_id
    assert call.stat().st_mode & 0o7777 == 0o750
    for directory, roles in (("inputs", CAPTURE.CALL.INPUT_ROLES), ("outputs", CAPTURE.CALL.OUTPUT_ROLES)):
        shared = call / directory
        CAPTURE.witness_directory(shared, group_id)
        for role in roles:
            CAPTURE.witness_write(shared / role, role.encode(), group_id)
        assert set(path.name for path in shared.iterdir()) == roles
        assert all(path.stat().st_uid == CAPTURE.os.geteuid() for path in shared.iterdir())
        assert all(path.stat().st_gid == group_id for path in shared.iterdir())
        assert all(path.stat().st_mode & 0o7777 == 0o640 for path in shared.iterdir())
    assert len(list((call / "inputs").iterdir())) == 4
    assert len(list((call / "outputs").iterdir())) == 5
    rejects(lambda: CAPTURE.witness_write(call / "bad", b"bad", 1 << 30), CAPTURE.CaptureError)

    for name in ("prompt.txt", "case.json", "protocol.json", "attempt.json", "response.json"):
        CAPTURE.private_write(call / name, b"private")
        assert (call / name).stat().st_mode & 0o777 == 0o600


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="reviewer-release-capture-test-") as temporary:
        root = Path(temporary).resolve()
        test_preflight(root)
        test_capture_limits(root)
        test_execution_event_payload()
        test_witness_artifact_access(root)
    print("reviewer release capture v1: PASS")


if __name__ == "__main__":
    main()
