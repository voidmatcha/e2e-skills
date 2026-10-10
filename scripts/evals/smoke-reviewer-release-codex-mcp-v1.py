#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Opt-in, development-only Codex -> MCP -> broker transcript smoke.

This uses the caller's Codex login. It does not prove isolation, custody,
review accuracy, or any release-v1 gate.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
MCP_SCRIPT = ROOT / "scripts/evals/reviewer-release-codex-mcp-v1.py"
RECONCILER = ROOT / "scripts/evals/reviewer-release-codex-transcript-v1.py"
CALL_EVIDENCE = ROOT / "scripts/evals/verify-reviewer-release-calls-v1.py"
PROTOCOL = ROOT / "scripts/evals/reviewer-release-v1-protocol.json"
SOURCE_PATH = "sources/case-001/example.spec.ts"
SOURCE = b"import { test } from '@playwright/test';\ntest.only('focused', () => {});\n"
SECOND_SOURCE_PATH = "sources/case-001/support.ts"
SECOND_SOURCE = b"export const marker = 'development-only';\n"
ARMS = ("full", "catalog-only", "no-skill")
ARTIFACT_ROOT = ROOT / "testbed"


def smoke_prompt(arm: str) -> bytes:
    task = (
        "This is a development plumbing smoke, not a quality review. "
        "Use only the reviewer_release MCP tools. Call read_staged_case_file "
        f"with path {SOURCE_PATH!r}. "
    )
    if arm == "full":
        task += "Then call run_staged_bundled_scanner with {}. "
    task += (
        'After the requested tool calls complete, return exactly {"findings":[]} with no Markdown. '
        "Do not use shell commands, web search, or any other tool."
    )
    return task.encode("utf-8")


def load_reconciler():
    spec = importlib.util.spec_from_file_location("reviewer_release_codex_transcript_v1", RECONCILER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_call_evidence():
    spec = importlib.util.spec_from_file_location("reviewer_release_call_evidence_v1", CALL_EVIDENCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exact_task_prompt(call_evidence, surface: dict, case: dict, arm: str) -> bytes:
    initial = {
        path: (ROOT / path).read_bytes()
        for path in surface["initial_model_visible_files"][arm]
    }
    return call_evidence.PROMPT.build_prompt(surface, case, arm, initial)


def failed_tool_summaries(journal: Path) -> list[str]:
    summaries: list[str] = []
    last_name = "unknown"
    last_path = ""
    for line in journal.read_bytes().splitlines():
        event = json.loads(line)["event"]
        if event["kind"] == "mcp_request":
            request = json.loads(base64.b64decode(event["raw_base64"]))
            if request.get("method") == "tools/call":
                last_name = str(request.get("params", {}).get("name", "unknown"))[:80]
                path = request.get("params", {}).get("arguments", {}).get("path")
                last_path = path if isinstance(path, str) and len(path) <= 120 and re.fullmatch(r"[A-Za-z0-9_./-]+", path) else "<redacted>"
        elif event["kind"] == "mcp_response_intent":
            response = json.loads(base64.b64decode(event["raw_base64"]))
            result = response.get("result")
            if isinstance(result, dict) and result.get("isError") is True:
                content = result.get("content", [])
                kind = content[0].get("text", "unknown") if content and isinstance(content[0], dict) else "unknown"
                summaries.append(f"{last_name}({last_path}): {str(kind)[:80]}")
    return summaries


def toml_value(value: str | list[str]) -> str:
    return json.dumps(value, ensure_ascii=False)


def validate_artifact_target(target: Path, allowed_root: Path = ARTIFACT_ROOT) -> None:
    """Keep development traces in an existing, ignored, owner-controlled tree."""
    if not target.is_absolute() or ".." in target.parts or target.exists() or target.is_symlink():
        raise ValueError("artifact destination must be a new absolute directory")
    root = allowed_root.absolute()
    if not root.is_dir() or root.is_symlink() or not target.is_relative_to(root):
        raise ValueError("artifact destination must be beneath a real testbed directory")
    if not target.parent.is_dir():
        raise ValueError("artifact parent must already exist")
    current = target.parent
    while current != root:
        if current.is_symlink() or not current.is_dir():
            raise ValueError("artifact parent contains a symlink or non-directory")
        current = current.parent
    if target.parent == root and root.is_symlink():
        raise ValueError("artifact root is a symlink")


def persist_artifacts(target: Path, files: dict[str, bytes], allowed_root: Path = ARTIFACT_ROOT) -> dict[str, str]:
    validate_artifact_target(target, allowed_root)
    for name in files:
        path = Path(name)
        if name == "manifest.json" or path.is_absolute() or not path.parts or any(part in (".", "..") for part in path.parts):
            raise ValueError("unsafe artifact name")
    target.mkdir(mode=0o700)
    hashes: dict[str, str] = {}
    for name, data in sorted(files.items()):
        path = Path(name)
        destination = target / path
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            os.chmod(destination, 0o600)
            stream.write(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    manifest = json.dumps({"status": "DEVELOPMENT_ONLY", "sha256": hashes}, sort_keys=True, indent=2).encode() + b"\n"
    with (target / "manifest.json").open("xb") as stream:
        os.chmod(target / "manifest.json", 0o600)
        stream.write(manifest)
    return hashes


def staged_snapshot(workspace: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for section in ("case", "skill"):
        base = workspace / section
        if not base.is_dir() or base.is_symlink():
            raise RuntimeError("staged snapshot root is missing or unsafe")
        for path in sorted(base.rglob("*")):
            if path.is_symlink() or (not path.is_dir() and not path.is_file()):
                raise RuntimeError("staged snapshot contains an unsafe entry")
            if path.is_file():
                files[f"staged/{section}/{path.relative_to(base).as_posix()}"] = path.read_bytes()
    return files


def replay_artifacts(directory: Path) -> dict:
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("development artifact directory is missing or unsafe")
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("development artifact manifest is missing or unsafe")
    manifest = json.loads(manifest_path.read_bytes())
    if set(manifest) != {"status", "sha256"} or manifest["status"] != "DEVELOPMENT_ONLY" or not isinstance(manifest["sha256"], dict):
        raise ValueError("development artifact manifest has an unexpected shape")
    expected = manifest["sha256"]
    required = {"prompt.txt", "codex.jsonl", "codex.stderr", "final.txt", "mcp-transcript.jsonl", "case.json", "protocol.json", SOURCE_PATH, "transcript-report.json"}
    if not required <= set(expected):
        raise ValueError("development artifact is missing required files")
    observed: set[str] = set()
    for path in directory.rglob("*"):
        if path.is_symlink() or (not path.is_dir() and not path.is_file()):
            raise ValueError("development artifact contains an unsafe entry")
        if path.is_file():
            observed.add(path.relative_to(directory).as_posix())
    if observed != set(expected) | {"manifest.json"}:
        raise ValueError("development artifact inventory differs from files")
    for name, declared in expected.items():
        if not isinstance(name, str) or not isinstance(declared, str) or not re.fullmatch(r"[0-9a-f]{64}", declared):
            raise ValueError("development artifact has an invalid digest entry")
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != declared:
            raise ValueError(f"development artifact digest mismatch: {name}")
    report = json.loads((directory / "transcript-report.json").read_bytes())
    arm = report.get("arm")
    if arm not in ARMS:
        raise ValueError("development report has an invalid arm")
    case = json.loads((directory / "case.json").read_bytes())
    journal_rows = [json.loads(line) for line in (directory / "mcp-transcript.jsonl").read_bytes().splitlines()]
    header = journal_rows[0]["event"]
    staged_case = {name.removeprefix("staged/case/"): digest for name, digest in expected.items() if name.startswith("staged/case/")}
    staged_skill = {name.removeprefix("staged/skill/"): digest for name, digest in expected.items() if name.startswith("staged/skill/")}
    scanner_prefix = "skills/e2e-reviewer/scripts/"
    staged_scanner = {name.removeprefix(scanner_prefix): digest for name, digest in staged_skill.items() if name.startswith(scanner_prefix)}
    staged_skill = {name: digest for name, digest in staged_skill.items() if not name.startswith(scanner_prefix)}
    if header["case_files"] != staged_case or header["skill_files"] != staged_skill or header["scanner_files"] != staged_scanner:
        raise ValueError("saved staged files differ from the MCP session header")
    if case["source_root"] != header["source_root"] or {item["path"]: item["sha256"] for item in case["source_files"]} != staged_case:
        raise ValueError("saved case manifest differs from staged source")
    reconciler = load_reconciler()
    result = reconciler.verify_capture(
        prompt=(directory / "prompt.txt").read_bytes(),
        stdout=(directory / "codex.jsonl").read_bytes(),
        stderr=(directory / "codex.stderr").read_bytes(),
        final_file=(directory / "final.txt").read_bytes(),
        journal=directory / "mcp-transcript.jsonl",
        expected_server="reviewer_release",
        expected_arm=arm,
        exit_code=0,
    )
    if report.get("task_prompt") == "exact_common_v1_development_only":
        call_evidence = load_call_evidence()
        calls, _ = reconciler.journal_tool_calls(directory / "mcp-transcript.jsonl", arm)
        call_evidence.verify_required_case_reads(calls, {item["path"] for item in case["source_files"]}, arm)
        protocol = json.loads((directory / "protocol.json").read_bytes())
        initial = {
            name: (directory / "staged/skill" / name).read_bytes()
            for name in protocol["evaluation_surface"]["initial_model_visible_files"][arm]
        }
        rebuilt_prompt = call_evidence.PROMPT.build_prompt(protocol["evaluation_surface"], case, arm, initial)
        if rebuilt_prompt != (directory / "prompt.txt").read_bytes():
            raise ValueError("saved prompt differs from saved protocol and staged material")
        normalized = call_evidence.NORMALIZE.normalize_response((directory / "final.txt").read_bytes())
        result["normalized_finding_identities"] = normalized["normalized_finding_identities"]
    result["task_prompt"] = report.get("task_prompt")
    result["arm"] = arm
    if result != report:
        raise ValueError("development artifact report differs from replayed capture")
    return {"status": "replayed_development_trace_only", "arm": arm, "artifact_dir": str(directory), "mcp_tool_calls": result["mcp_tool_calls"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=ARMS, default="full")
    parser.add_argument("--exact-task", action="store_true", help="development-only exact common release-v1 task prompt")
    parser.add_argument("--two-file", action="store_true", help="add a second synthetic source file; requires --exact-task")
    parser.add_argument("--artifact-dir", type=Path, help="new absolute directory below ignored testbed/ for private development traces")
    parser.add_argument("--replay-artifact-dir", type=Path, help="offline-verify a saved development trace without a model call")
    args = parser.parse_args()
    if args.replay_artifact_dir is not None:
        if args.artifact_dir is not None or args.exact_task or args.two_file:
            parser.error("replay cannot be combined with a model-call mode")
        print(json.dumps(replay_artifacts(args.replay_artifact_dir), sort_keys=True))
        return 0
    if args.two_file and not args.exact_task:
        parser.error("--two-file requires --exact-task")
    if args.artifact_dir is not None:
        validate_artifact_target(args.artifact_dir)
    arm = args.arm
    codex = shutil.which("codex")
    if codex is None:
        raise RuntimeError("codex CLI is not installed")
    codex = str(Path(codex).resolve())
    python = str(Path(sys.executable).resolve())
    with tempfile.TemporaryDirectory(prefix="reviewer-release-codex-mcp-smoke-") as raw:
        root = Path(raw)
        bundle = root / "bundle"
        source = bundle / SOURCE_PATH
        source.parent.mkdir(parents=True)
        source.write_bytes(SOURCE)
        if args.two_file:
            (bundle / SECOND_SOURCE_PATH).write_bytes(SECOND_SOURCE)
        case = {
            "source_root": "sources/case-001",
            "source_files": [
                {"path": SOURCE_PATH, "sha256": hashlib.sha256(SOURCE).hexdigest()},
                *([{"path": SECOND_SOURCE_PATH, "sha256": hashlib.sha256(SECOND_SOURCE).hexdigest()}] if args.two_file else []),
            ],
        }
        protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
        call_evidence = load_call_evidence() if args.exact_task else None
        prompt = exact_task_prompt(call_evidence, protocol["evaluation_surface"], case, arm) if call_evidence else smoke_prompt(arm)
        case_json = root / "case.json"
        case_json.write_text(json.dumps(case), encoding="utf-8")
        workspace = root / "workspace"
        final_path = root / "final.txt"
        server_args = [
            str(MCP_SCRIPT), "--bundle", str(bundle), "--case-json", str(case_json),
            "--skill-root", str(ROOT), "--protocol", str(PROTOCOL),
            "--workspace", str(workspace), "--arm", arm,
        ]
        command = [
            codex, "exec", "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
            "--strict-config", "--skip-git-repo-check", "--sandbox", "read-only",
            "--model", "gpt-5.6-sol", "-C", str(root), "-o", str(final_path),
            "-c", f"mcp_servers.reviewer_release.command={toml_value(python)}",
            "-c", f"mcp_servers.reviewer_release.args={toml_value(server_args)}",
            "-c", "mcp_servers.reviewer_release.required=true",
            "-c", "mcp_servers.reviewer_release.default_tools_approval_mode=\"approve\"",
            "-c", "features.shell_tool=false",
            "-c", "features.apps=false",
            "-c", "features.multi_agent=false",
            "-c", "web_search=\"disabled\"",
            "-",
        ]
        try:
            call = subprocess.run(command, input=prompt, cwd=root, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Codex MCP smoke timed out; no release claim") from exc
        if call.returncode != 0:
            # Avoid printing stderr: it can include user-specific CLI diagnostics.
            raise RuntimeError(f"Codex MCP smoke exited {call.returncode}; no release claim")
        if not final_path.is_file():
            raise RuntimeError("Codex did not write its final-message file")
        reconciler = load_reconciler()
        journal = workspace / "mcp-transcript.jsonl"
        try:
            result = reconciler.verify_capture(
                prompt=prompt,
                stdout=call.stdout,
                stderr=call.stderr,
                final_file=final_path.read_bytes(),
                journal=journal,
                expected_server="reviewer_release",
                expected_arm=arm,
                exit_code=call.returncode,
            )
        except reconciler.TranscriptError as exc:
            raise RuntimeError(f"development trace failed: {exc}; denied_tools={failed_tool_summaries(journal)}") from exc
        if call_evidence:
            calls, _ = reconciler.journal_tool_calls(journal, arm)
            call_evidence.verify_required_case_reads(calls, {item["path"] for item in case["source_files"]}, arm)
            try:
                normalized = call_evidence.NORMALIZE.normalize_response(final_path.read_bytes())
            except call_evidence.NORMALIZE.NormalizationError as exc:
                raw_findings = json.loads(final_path.read_bytes())["findings"]
                ids = [str(item.get("pattern_id", "<missing>"))[:40] for item in raw_findings[:5] if isinstance(item, dict)]
                raise RuntimeError(f"exact-task development response violates the frozen adapter: {exc}; pattern_ids={ids}") from exc
            result["normalized_finding_identities"] = normalized["normalized_finding_identities"]
            result["task_prompt"] = "exact_common_v1_development_only"
        elif result["mcp_tool_calls"] != (2 if arm == "full" else 1):
            raise RuntimeError("Codex did not complete the expected arm-specific MCP calls")
        else:
            result["task_prompt"] = "plumbing_only"
        result["arm"] = arm
        if args.artifact_dir is not None:
            files = {
                "prompt.txt": prompt,
                "codex.jsonl": call.stdout,
                "codex.stderr": call.stderr,
                "final.txt": final_path.read_bytes(),
                "mcp-transcript.jsonl": journal.read_bytes(),
                "case.json": case_json.read_bytes(),
                "protocol.json": PROTOCOL.read_bytes(),
                SOURCE_PATH: SOURCE,
                "transcript-report.json": json.dumps(result, sort_keys=True, indent=2).encode() + b"\n",
            }
            if args.two_file:
                files[SECOND_SOURCE_PATH] = SECOND_SOURCE
            files.update(staged_snapshot(workspace))
            persist_artifacts(args.artifact_dir, files)
            result["artifact_dir"] = str(args.artifact_dir)
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
