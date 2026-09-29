#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture one reviewer-release-v1 Codex call without claiming release provenance.

Run only inside an independently controlled environment. This program does not
verify isolation, custody, an online witness, or release eligibility. A timed
out or interrupted call is never retried by this program.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, NamedTuple


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MCP = HERE / "reviewer-release-codex-mcp-v1.py"
MAX_STDOUT = 8 << 20
MAX_STDERR = 1 << 20
MAX_PROMPT = 1 << 20
TIMEOUT = 600


def load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CALL = load("release_capture_call_evidence", "verify-reviewer-release-calls-v1.py")
ASSEMBLE = load("release_capture_assembler", "assemble-reviewer-release-call-v1.py")
BROKER = load("release_capture_broker", "reviewer-release-tool-surface-v1.py")
HOLDOUT = load("release_capture_runner_helpers", "run-reviewer-holdout.py")


class CaptureError(ValueError):
    pass


class PreparedCall(NamedTuple):
    root: Path
    command: tuple[str, ...]
    environment: dict[str, str]
    prompt: bytes
    case_bytes: bytes
    protocol_bytes: bytes
    frozen_inputs: dict[str, bytes]
    case_id: str
    arm: str
    repetition: int
    protocol: dict[str, Any]
    case: dict[str, Any]
    skill: dict[str, bytes]
    scanner: dict[str, bytes]
    runner_version: str
    witness_artifact_gid: int | None


def regular_bytes(path: Path, limit: int) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise CaptureError("input must be an absolute, non-symlink file")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise CaptureError("input file is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise CaptureError("input must be a bounded regular file")
        data = os.read(descriptor, limit + 1)
        after = os.fstat(descriptor)
        if len(data) != before.st_size or len(data) > limit or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise CaptureError("input changed while read")
        return data
    finally:
        os.close(descriptor)


def checked_executable(path: Path) -> str:
    if not path.is_absolute() or path.is_symlink():
        raise CaptureError("runner must be an absolute non-symlink executable")
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise CaptureError("runner is not executable")
    return str(resolved)


def checked_artifact_dir(path: Path, bundle: Path, skill_root: Path, *, evidence_output_root: Path | None = None) -> None:
    if not path.is_absolute() or ".." in path.parts or path.exists() or path.is_symlink():
        raise CaptureError("artifact directory must be a new absolute path")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir() or parent.resolve(strict=True) != parent:
        raise CaptureError("artifact parent must be an existing real directory")
    bundle_root = bundle.resolve(strict=True)
    if evidence_output_root is not None:
        if evidence_output_root != bundle_root / "calls" or parent != evidence_output_root:
            raise CaptureError("release artifact directory must be a direct child of bundle/calls")
        if evidence_output_root.is_symlink() or evidence_output_root.resolve(strict=True) != evidence_output_root:
            raise CaptureError("release artifact parent must be a real directory")
    protected_roots = (skill_root.resolve(strict=True), ROOT) if evidence_output_root is not None else (bundle_root, skill_root.resolve(strict=True), ROOT)
    for protected in protected_roots:
        if path == protected or path.is_relative_to(protected):
            raise CaptureError("artifact directory overlaps an input or the repository")


def private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(data)


def checked_witness_artifact_gid(group_id: int) -> int:
    if isinstance(group_id, bool) or not isinstance(group_id, int) or group_id < 0:
        raise CaptureError("witness artifact group ID is invalid")
    if os.geteuid() == 0:
        raise CaptureError("release runner must be a non-root user")
    if group_id not in {*os.getgroups(), os.getegid()}:
        raise CaptureError("release runner is not a member of the witness artifact group")
    return group_id


def witness_directory(path: Path, group_id: int) -> None:
    """Create one runner-owned directory readable, but not writable, by the witness."""
    group_id = checked_witness_artifact_gid(group_id)
    try:
        path.mkdir(mode=0o700)
        os.chown(path, -1, group_id)
        os.chmod(path, 0o750)
        info = path.lstat()
    except OSError as exc:
        raise CaptureError("witness artifact directory could not be created safely") from exc
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or info.st_gid != group_id or stat.S_IMODE(info.st_mode) != 0o750):
        raise CaptureError("witness artifact directory ownership or mode differs")


def witness_write(path: Path, data: bytes, group_id: int) -> None:
    """Publish one complete create-only artifact to the witness read group."""
    group_id = checked_witness_artifact_gid(group_id)
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise CaptureError("witness artifact parent is unavailable")
    descriptor = -1
    try:
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600,
        )
        pending = memoryview(data)
        while pending:
            written = os.write(descriptor, pending)
            if written <= 0:
                raise CaptureError("witness artifact accepted no bytes")
            pending = pending[written:]
        os.fchown(descriptor, -1, group_id)
        os.fchmod(descriptor, 0o640)
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_gid != group_id or stat.S_IMODE(info.st_mode) != 0o640
                or info.st_size != len(data)):
            raise CaptureError("witness artifact ownership, mode, or size differs")
    except OSError as exc:
        raise CaptureError("witness artifact could not be written safely") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def staged_files(root: Path, names: set[str], *, scanner: bool = False) -> dict[str, bytes]:
    result = {}
    for name in sorted(names):
        source = f"skills/e2e-reviewer/scripts/{name}" if scanner else name
        result[name] = BROKER.safe_source_bytes(root, BROKER.relative_path(source), 1 << 20)
    return result


def prepare_input_bytes(
    bundle: Path, case_bytes: bytes, skill_root: Path, protocol_bytes: bytes, arm: str, *,
    frozen_protocol_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes], dict[str, bytes], bytes, bytes, bytes]:
    protocol = CALL.strict_json(protocol_bytes, "capture protocol")
    if protocol.get("protocol_id") != "reviewer-release-v1":
        raise CaptureError("capture protocol identity differs")
    surface_status = protocol.get("evaluation_surface", {}).get("status")
    if frozen_protocol_sha256 is None:
        if protocol.get("status") != "NOT_RUN" or surface_status != "DESIGNED_NOT_IMPLEMENTED":
            raise CaptureError("capture protocol is not the current development contract")
    elif (
        not isinstance(frozen_protocol_sha256, str)
        or CALL.SHA256.fullmatch(frozen_protocol_sha256) is None
        or hashlib.sha256(protocol_bytes).hexdigest() != frozen_protocol_sha256
        or protocol.get("status") != "FROZEN"
        or surface_status != "IMPLEMENTED"
    ):
        raise CaptureError("release call protocol differs from the admitted frozen snapshot")
    case = CALL.strict_json(case_bytes, "capture case")
    _, source_hashes = CALL.case_files(case, "capture case")
    for name, digest in source_hashes.items():
        actual = BROKER.safe_source_bytes(bundle, BROKER.relative_path(name, source=True), 1 << 20)
        if hashlib.sha256(actual).hexdigest() != digest:
            raise CaptureError("case source hash differs before model call")
    surface = protocol["evaluation_surface"]
    skill_names = set(surface["initial_model_visible_files"][arm]) | set(surface["on_demand_skill_files"][arm])
    skill = staged_files(skill_root, skill_names)
    scanner = staged_files(skill_root, set(BROKER.SCANNER_FILES), scanner=True) if arm == "full" else {}
    initial = {name: skill[name] for name in surface["initial_model_visible_files"][arm]}
    prompt = CALL.PROMPT.build_prompt(surface, case, arm, initial)
    if len(prompt) > MAX_PROMPT:
        raise CaptureError("prompt exceeds the frozen capture bound")
    return protocol, case, skill, scanner, prompt, case_bytes, protocol_bytes


def prepare_inputs(bundle: Path, case_path: Path, skill_root: Path, protocol_path: Path, arm: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes], dict[str, bytes], bytes, bytes, bytes]:
    return prepare_input_bytes(
        bundle, regular_bytes(case_path, 4 << 20), skill_root,
        regular_bytes(protocol_path, 1 << 20), arm,
    )


def command_for(runner: str, python: str, root: Path, bundle: Path, case_path: Path, skill_root: Path, protocol_path: Path, arm: str) -> list[str]:
    server_args = [
        str(MCP), "--bundle", str(bundle), "--case-json", str(case_path),
        "--skill-root", str(skill_root), "--protocol", str(protocol_path),
        "--workspace", str(root / "workspace"), "--arm", arm,
    ]
    encode = lambda value: json.dumps(value, ensure_ascii=False)
    return [
        runner, "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
        "--strict-config", "--skip-git-repo-check", "--sandbox", "read-only",
        "--model", "gpt-5.6-sol", "-C", str(root), "-o", str(root / "final.txt"),
        "-c", f"mcp_servers.reviewer_release.command={encode(python)}",
        "-c", f"mcp_servers.reviewer_release.args={encode(server_args)}",
        "-c", "mcp_servers.reviewer_release.required=true",
        "-c", 'mcp_servers.reviewer_release.default_tools_approval_mode="approve"',
        "-c", "features.shell_tool=false", "-c", "features.apps=false",
        "-c", "features.multi_agent=false", "-c", 'web_search="disabled"',
        "-c", 'shell_environment_policy.inherit="none"', "-",
    ]


def kill_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def communicate_bounded(process: subprocess.Popen[bytes], command: list[str], prompt: bytes, stdout_path: Path, stderr_path: Path) -> tuple[bytes, bytes]:
    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise CaptureError("runner pipes are unavailable")
    selector = selectors.DefaultSelector()
    sizes = {"stdout": 0, "stderr": 0}
    pending = memoryview(prompt)
    offset = 0
    if pending:
        os.set_blocking(process.stdin.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE, "stdin")
    else:
        process.stdin.close()
    for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    deadline = time.monotonic() + TIMEOUT
    try:
        with stdout_path.open("xb") as stdout_file, stderr_path.open("xb") as stderr_file:
            os.chmod(stdout_path, 0o600)
            os.chmod(stderr_path, 0o600)
            targets = {"stdout": stdout_file, "stderr": stderr_file}
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, TIMEOUT)
                for key, _ in selector.select(min(0.1, remaining)):
                    if key.data == "stdin":
                        written = os.write(key.fileobj.fileno(), pending[offset:offset + 65536])
                        if written == 0:
                            raise CaptureError("runner accepted no prompt bytes")
                        offset += written
                        if offset == len(pending):
                            selector.unregister(key.fileobj)
                            process.stdin.close()
                        continue
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    name = key.data
                    sizes[name] += len(chunk)
                    if sizes[name] > (MAX_STDOUT if name == "stdout" else MAX_STDERR):
                        raise CaptureError(f"{name} exceeds the capture bound")
                    targets[name].write(chunk)
                    targets[name].flush()
            process.wait(timeout=max(0, deadline - time.monotonic()))
    finally:
        selector.close()
        if not process.stdin.closed:
            process.stdin.close()
    return regular_bytes(stdout_path, MAX_STDOUT), regular_bytes(stderr_path, MAX_STDERR)


def prepare_call(
    *, root: Path, runner: str, bundle: Path, skill_root: Path,
    protocol: dict[str, Any], case: dict[str, Any], skill: dict[str, bytes],
    scanner: dict[str, bytes], prompt: bytes, case_bytes: bytes,
    protocol_bytes: bytes, environment: dict[str, str], runner_version: str,
    case_id: str, arm: str, repetition: int,
    evidence_output_root: Path | None = None,
    witness_artifact_gid: int | None = None,
) -> PreparedCall:
    """Create and retain the four input artifacts before the launch boundary."""
    checked_artifact_dir(root, bundle, skill_root, evidence_output_root=evidence_output_root)
    if evidence_output_root is not None:
        if witness_artifact_gid is None:
            raise CaptureError("release capture requires a witness artifact group")
        witness_directory(root, witness_artifact_gid)
    else:
        root.mkdir(mode=0o700)
    private_write(root / "prompt.txt", prompt)
    private_write(root / "case.json", case_bytes)
    private_write(root / "protocol.json", protocol_bytes)
    frozen_inputs = ASSEMBLE.assemble_inputs(
        arm=arm, case=case, surface=protocol["evaluation_surface"],
        primary=protocol["execution_identity"]["primary"],
        runner_version=runner_version, staged_skill_files=skill,
        staged_scanner_files=scanner, prompt=prompt,
    )
    if witness_artifact_gid is not None:
        witness_directory(root / "inputs", witness_artifact_gid)
    for role, data in frozen_inputs.items():
        if witness_artifact_gid is None:
            private_write(root / "inputs" / role, data)
        else:
            witness_write(root / "inputs" / role, data, witness_artifact_gid)
    command = command_for(runner, str(Path(sys.executable).resolve()), root, bundle, root / "case.json", skill_root, root / "protocol.json", arm)
    return PreparedCall(root, tuple(command), environment, prompt, case_bytes, protocol_bytes, frozen_inputs, case_id, arm, repetition, protocol, case, skill, scanner, runner_version, witness_artifact_gid)


def verify_frozen_inputs(prepared: PreparedCall) -> None:
    if any(regular_bytes(prepared.root / "inputs" / role, 4 << 20) != data for role, data in prepared.frozen_inputs.items()):
        raise CaptureError("pre-call input artifacts changed after freezing")
    for name, expected in (("prompt.txt", prepared.prompt), ("case.json", prepared.case_bytes), ("protocol.json", prepared.protocol_bytes)):
        if regular_bytes(prepared.root / name, 4 << 20) != expected:
            raise CaptureError("runner input source changed after freezing")


def verify_attempt_marker(prepared: PreparedCall) -> None:
    marker = CALL.exact(CALL.strict_json(regular_bytes(prepared.root / "attempt.json", 1 << 20), "attempt marker"), {
        "case_id", "arm", "repetition", "prompt_sha256", "status",
    }, "attempt marker")
    expected = {
        "case_id": prepared.case_id, "arm": prepared.arm,
        "repetition": prepared.repetition,
        "prompt_sha256": hashlib.sha256(prepared.prompt).hexdigest(),
        "status": "LAUNCH_BOUNDARY_CROSSED",
    }
    if marker != expected:
        raise CaptureError("attempt marker differs from the prepared call")


def execute_prepared_call(
    prepared: PreparedCall, *,
    acknowledge_begin: Callable[[dict[str, Path]], None] | None = None,
    on_attempt: Callable[[], None] | None = None,
) -> tuple[int, bytes, bytes]:
    """Cross the one-attempt boundary only after an optional begin acknowledgement.

    A release coordinator must supply an independently verified, durable witness
    acknowledgement. With no callback this remains a development-only call.
    """
    verify_frozen_inputs(prepared)
    if acknowledge_begin is not None:
        acknowledge_begin({role: prepared.root / "inputs" / role for role in prepared.frozen_inputs})
        verify_frozen_inputs(prepared)
    private_write(prepared.root / "attempt.json", ASSEMBLE.json_bytes({
        "case_id": prepared.case_id, "arm": prepared.arm,
        "repetition": prepared.repetition,
        "prompt_sha256": hashlib.sha256(prepared.prompt).hexdigest(),
        "status": "LAUNCH_BOUNDARY_CROSSED",
    }))
    if on_attempt is not None:
        on_attempt()
    process = subprocess.Popen(
        list(prepared.command), cwd=prepared.root, env=prepared.environment,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = communicate_bounded(
            process, list(prepared.command), prepared.prompt,
            prepared.root / "codex.jsonl", prepared.root / "codex.stderr",
        )
    except BaseException:
        kill_group(process)
        raise
    return process.returncode, stdout, stderr


def finalize_call(
    prepared: PreparedCall, returncode: int, stdout: bytes, stderr: bytes, *,
    acknowledge_end: Callable[[dict[str, Path]], None] | None = None,
) -> None:
    """Verify the call and freeze all five outputs before an optional end acknowledgement."""
    verify_attempt_marker(prepared)
    if returncode != 0:
        raise CaptureError(f"runner exited {returncode}; no replacement call")
    root = prepared.root
    final = regular_bytes(root / "final.txt", 8 << 20)
    journal = regular_bytes(root / "workspace" / "mcp-transcript.jsonl", 128 << 20)
    staged = root / "workspace" / "skill"
    for name, original in prepared.skill.items():
        if BROKER.safe_source_bytes(staged, BROKER.relative_path(name), 1 << 20) != original:
            raise CaptureError("staged skill differs after model call")
    for name, original in prepared.scanner.items():
        if BROKER.safe_source_bytes(staged, BROKER.relative_path(f"skills/e2e-reviewer/scripts/{name}"), 1 << 20) != original:
            raise CaptureError("staged scanner differs after model call")
    assembled = ASSEMBLE.assemble_call(
        case_id=prepared.case_id, arm=prepared.arm, repetition=prepared.repetition,
        case=prepared.case, surface=prepared.protocol["evaluation_surface"],
        primary=prepared.protocol["execution_identity"]["primary"],
        runner_version=prepared.runner_version, staged_skill_files=prepared.skill,
        staged_scanner_files=prepared.scanner, prompt=prepared.prompt,
        codex_jsonl=stdout, stderr=stderr, final_response=final,
        mcp_journal=journal, completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    if assembled["inputs"] != prepared.frozen_inputs:
        raise CaptureError("assembled inputs differ from the frozen call")
    verify_frozen_inputs(prepared)
    output_paths = {}
    if prepared.witness_artifact_gid is not None:
        witness_directory(root / "outputs", prepared.witness_artifact_gid)
    for role, data in assembled["outputs"].items():
        path = root / "outputs" / role
        if prepared.witness_artifact_gid is None:
            private_write(path, data)
        else:
            witness_write(path, data, prepared.witness_artifact_gid)
        output_paths[role] = path
    if acknowledge_end is not None:
        acknowledge_end(output_paths)
        if any(regular_bytes(path, 128 << 20) != assembled["outputs"][role] for role, path in output_paths.items()):
            raise CaptureError("output artifacts changed after end acknowledgement")
        verify_frozen_inputs(prepared)
    private_write(root / "response.json", ASSEMBLE.json_bytes(assembled["response"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--case-json", type=Path, required=True)
    parser.add_argument("--skill-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--repetition", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--arm", choices=("full", "catalog-only", "no-skill"), required=True)
    parser.add_argument("--execute", action="store_true", help="make exactly one credentialed model call")
    args = parser.parse_args()
    model_attempted = False
    try:
        runner = checked_executable(args.runner_path)
        checked_artifact_dir(args.artifact_dir, args.bundle, args.skill_root)
        protocol, case, skill, scanner, prompt, case_bytes, protocol_bytes = prepare_inputs(args.bundle, args.case_json, args.skill_root, args.protocol, args.arm)
        if not args.execute:
            print(json.dumps({"status": "PREFLIGHT_ONLY", "model_execution_attempted": False, "prompt_sha256": hashlib.sha256(prompt).hexdigest()}, sort_keys=True))
            return 0
        root = args.artifact_dir
        with tempfile.TemporaryDirectory(prefix="reviewer-release-runner-home-") as runner_home:
            environment = HOLDOUT.clean_env("codex", runner_home)
            environment["CODEX_HOME"] = str(HOLDOUT.stage_codex_auth(Path(runner_home)))
            version = subprocess.run([runner, "--version"], env=environment, capture_output=True, timeout=10, check=False)
            match = re.fullmatch(rb"codex-cli (\d+\.\d+\.\d+)\s*", version.stdout)
            if version.returncode != 0 or match is None:
                raise CaptureError("runner version could not be independently read")
            prepared = prepare_call(
                root=root, runner=runner, bundle=args.bundle, skill_root=args.skill_root,
                protocol=protocol, case=case, skill=skill, scanner=scanner,
                prompt=prompt, case_bytes=case_bytes, protocol_bytes=protocol_bytes,
                environment=environment, runner_version=match.group(1).decode(),
                case_id=args.case_id, arm=args.arm, repetition=args.repetition,
            )
            def mark_attempt() -> None:
                nonlocal model_attempted
                model_attempted = True

            returncode, stdout, stderr = execute_prepared_call(prepared, on_attempt=mark_attempt)
        finalize_call(prepared, returncode, stdout, stderr)
        print(json.dumps({"status": "CAPTURED_UNATTESTED", "model_execution_attempted": True, "artifact_dir": str(root)}, sort_keys=True))
        return 0
    except (CaptureError, CALL.CallEvidenceError, ASSEMBLE.EVIDENCE.CallEvidenceError, BROKER.ToolSurfaceError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "INCOMPLETE", "model_execution_attempted": model_attempted, "error": type(exc).__name__, "no_replacement_call": True}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
