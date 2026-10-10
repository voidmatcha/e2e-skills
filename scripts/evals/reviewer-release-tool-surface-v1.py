#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Development-only read/scan surface for the release-v1 agent workflow.

The model adapter must call this broker rather than exposing a shell. This
module does not provide model isolation, signed transcripts, or a release run.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from typing import Any


SCANNER_ENV = {
    "E2E_SMELL_ALLOW_PROJECT_ESLINT": "0",
    "E2E_SMELL_DISABLE_AST_GREP": "1",
    "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
    "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
    "E2E_SMELL_FAIL_ON": "none",
}
SKILL_PREFIX = "skills/e2e-reviewer/"
RESERVED = {".git", ".codex", ".claude", ".agents", ".omx", ".skill"}
SCANNER_FILES = (
    "scan.sh",
    "scope-source.sh",
    "scope-worker.py",
    "scope-graph.py",
    "scope-lexer.py",
    "scope-watch.py",
    "conditional-discovery.py",
)
INITIAL_FILES = {
    "full": ["skills/e2e-reviewer/SKILL.md"],
    "catalog-only": ["skills/e2e-reviewer/references/pattern-reference.md"],
    "no-skill": [],
}
FULL_REFERENCES = [
    "skills/e2e-reviewer/references/review-scope.md",
    "skills/e2e-reviewer/references/scanner-workflow.md",
    "skills/e2e-reviewer/references/semantic-review.md",
    "skills/e2e-reviewer/references/reporting.md",
    "skills/e2e-reviewer/references/pattern-reference.md",
    "skills/e2e-reviewer/references/verification-rules.md",
    "skills/e2e-reviewer/references/grep-patterns.md",
    "skills/e2e-reviewer/references/upstream-rule-sources.md",
    "skills/e2e-reviewer/references/applying-fixes.md",
]
ON_DEMAND_FILES = {"full": FULL_REFERENCES, "catalog-only": [], "no-skill": []}
TIER3_HEADER = "--- Tier 3: Bundled regex checks (universal fallback for grep-detectable patterns and gaps eslint/ast-grep miss) ---"
SUMMARY = re.compile(
    r"Summary: \d+ total hit\(s\), \d+ P0, \d+ P1/P2 heuristic, "
    r"\d+ LLM-triage, \d+ P0 candidate; 0 AST-origin hit\(s\), "
    r"exact cross-tier dedupe applied\."
)
ADVICE_HEADERS = {
    "Enforceable by a lint rule (fix once in your ESLint config, caught on every commit):",
    "No ESLint rule expresses these — they need this review (or a human) every time:",
}


class ToolSurfaceError(ValueError):
    """The requested read/scan is outside the declared treatment surface."""


def relative_path(raw: Any, *, source: bool = False) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise ToolSurfaceError("expected a non-empty normalized POSIX path")
    if raw.startswith("/") or any(part in {"", ".", ".."} for part in raw.split("/")):
        raise ToolSurfaceError("path is not normalized or is absolute")
    path = PurePosixPath(raw)
    if source and (
        any(part in RESERVED for part in path.parts)
        or path.name in {"AGENTS.md", "CLAUDE.md", "auth.json", ".npmrc"}
        or path.name.startswith(".env")
    ):
        raise ToolSurfaceError("runner-controlled or credential-bearing source path")
    return path


def safe_source_bytes(root: Path, relative: PurePosixPath, max_bytes: int) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ToolSurfaceError("host lacks no-follow file opens")
    nofollow = os.O_NOFOLLOW
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | nofollow
    try:
        parent_fd = os.open(root, directory_flags)
        try:
            for part in relative.parts[:-1]:
                child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = child_fd
            fd = os.open(relative.parts[-1], os.O_RDONLY | nofollow, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        raise ToolSurfaceError(f"source path is unavailable or contains a symlink: {exc.strerror}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise ToolSurfaceError("source must be a bounded regular file")
        data = os.read(fd, max_bytes + 1)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (
        not stat.S_ISREG(before.st_mode)
        or len(data) > max_bytes
        or len(data) != before.st_size
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise ToolSurfaceError("source changed or exceeded its declared bound")
    return data


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scanner_report_complete(stdout: bytes) -> bool:
    try:
        lines = stdout.decode("utf-8").splitlines()
    except UnicodeError:
        return False
    if lines.count(TIER3_HEADER) != 1 or any(
        line.startswith(("--- Tier 1:", "--- Tier 2:")) for line in lines
    ):
        return False
    summaries = [index for index, line in enumerate(lines) if SUMMARY.fullmatch(line)]
    if len(summaries) != 1 or not any(line.startswith("Scope filter: ") for line in lines[:summaries[0]]):
        return False
    if lines.index(TIER3_HEADER) > summaries[0]:
        return False
    tail = [line for line in lines[summaries[0] + 1:] if line]
    while tail:
        if tail.pop(0) not in ADVICE_HEADERS or not tail or not re.fullmatch(r"  #[^\r\n]+", tail.pop(0)):
            return False
    return True


class ReleaseToolSurface:
    """Snapshot one case and expose only three allowlisted read-only tools."""

    def __init__(
        self,
        bundle: Path,
        case: dict[str, Any],
        skill_root: Path,
        surface: dict[str, Any],
        workspace: Path,
        arm: str = "full",
    ) -> None:
        if not workspace.is_absolute():
            raise ToolSurfaceError("workspace must be an absolute path")
        workspace = workspace.resolve(strict=False)
        bundle = bundle.resolve(strict=True)
        skill_root = skill_root.resolve(strict=True)
        if workspace == bundle or workspace.is_relative_to(bundle) or workspace == skill_root or workspace.is_relative_to(skill_root):
            raise ToolSurfaceError("workspace must be outside the source bundle and evaluated skill")
        if workspace.exists():
            raise ToolSurfaceError("workspace must not exist before snapshot creation")
        root = relative_path(case.get("source_root"), source=True)
        files = case.get("source_files")
        limits = {"files_max": 64, "file_bytes_max": 1048576, "total_bytes_max": 4194304}
        if surface.get("status") != "DESIGNED_NOT_IMPLEMENTED":
            raise ToolSurfaceError("tool surface has an unexpected protocol status")
        if surface.get("scanner_environment") != SCANNER_ENV:
            raise ToolSurfaceError("scanner environment differs from the protocol")
        if surface.get("initial_model_visible_files") != INITIAL_FILES or surface.get("on_demand_skill_files") != ON_DEMAND_FILES:
            raise ToolSurfaceError("skill file allowlist differs from the protocol")
        if arm not in {"full", "catalog-only", "no-skill"}:
            raise ToolSurfaceError("unknown treatment arm")
        if not isinstance(files, list) or not 1 <= len(files) <= limits["files_max"]:
            raise ToolSurfaceError("source file count is outside the protocol bound")
        case_dir = bundle.joinpath(*root.parts)
        if not case_dir.is_dir() or case_dir.is_symlink():
            raise ToolSurfaceError("case root must be a real directory")
        self.workspace = workspace
        self.arm = arm
        self.case_root = workspace / "case"
        self.skill_root = workspace / "skill"
        self.source_root = root.as_posix()
        self.allowed_case: dict[str, str] = {}
        self.allowed_skill: dict[str, str] = {}
        self.transcript: list[dict[str, Any]] = []
        snapshot: dict[str, bytes] = {}
        total = 0
        for item in files:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                raise ToolSurfaceError("source reference needs path and sha256")
            name = relative_path(item["path"], source=True)
            if name.parts[:len(root.parts)] != root.parts or len(name.parts) <= len(root.parts):
                raise ToolSurfaceError("source is outside its case root")
            key = name.as_posix()
            if key in snapshot:
                raise ToolSurfaceError("duplicate source path")
            data = safe_source_bytes(bundle, name, limits["file_bytes_max"])
            if digest(data) != item["sha256"]:
                raise ToolSurfaceError("source digest mismatch")
            total += len(data)
            if total > limits["total_bytes_max"]:
                raise ToolSurfaceError("case source byte limit exceeded")
            snapshot[key] = data
        observed: set[str] = set()
        def walk_error(error: OSError) -> None:
            raise ToolSurfaceError(f"cannot enumerate the full case root: {error.strerror}") from error

        for current, directories, filenames in os.walk(case_dir, onerror=walk_error):
            for dirname in directories:
                if (Path(current) / dirname).is_symlink():
                    raise ToolSurfaceError("case contains a symlinked directory")
            for filename in filenames:
                path = Path(current) / filename
                if path.is_symlink() or not path.is_file():
                    raise ToolSurfaceError("case contains a non-regular file")
                observed.add(path.relative_to(bundle).as_posix())
        if observed != set(snapshot):
            raise ToolSurfaceError("declared files do not exactly cover the case")

        skill_names = list(dict.fromkeys([*INITIAL_FILES[arm], *ON_DEMAND_FILES[arm]]))
        skill_snapshot: dict[str, bytes] = {}
        for name in skill_names:
            path = relative_path(name)
            if not name.startswith(SKILL_PREFIX) or path.suffix != ".md":
                raise ToolSurfaceError("unexpected skill file in treatment surface")
            skill_snapshot[name] = safe_source_bytes(skill_root, path, 1048576)
        scanner_snapshot = {
            name: safe_source_bytes(skill_root, relative_path(f"skills/e2e-reviewer/scripts/{name}"), 1048576)
            for name in SCANNER_FILES
        } if arm == "full" else {}

        workspace.mkdir(mode=0o700)
        self.case_root.mkdir(mode=0o700)
        self.skill_root.mkdir(mode=0o700)
        for name, data in snapshot.items():
            dest = self.case_root.joinpath(*relative_path(name).parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            self.allowed_case[name] = digest(data)
        for name, data in skill_snapshot.items():
            dest = self.skill_root.joinpath(*relative_path(name).parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            self.allowed_skill[name] = digest(data)
        self.scanner_digests = {}
        for name, data in scanner_snapshot.items():
            dest = self.skill_root / "skills" / "e2e-reviewer" / "scripts" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            self.scanner_digests[name] = digest(data)
        self.scanner = self.skill_root / "skills" / "e2e-reviewer" / "scripts" / "scan.sh"

    def _read(self, root: Path, allowed: dict[str, str], name: str, tool: str, *, declared_name: str | None = None) -> bytes:
        declared = declared_name if declared_name is not None else name
        path = relative_path(declared)
        if declared not in allowed:
            raise ToolSurfaceError(f"{tool}: undeclared file")
        data = safe_source_bytes(root, path, 1048576)
        if digest(data) != allowed[declared]:
            raise ToolSurfaceError(f"{tool}: staged file changed")
        self.transcript.append({
            "tool": tool,
            "arguments": {"path": name},
            "result_sha256": digest(data),
            "result_base64": base64.b64encode(data).decode("ascii"),
        })
        return data

    def read_staged_case_file(self, name: str) -> bytes:
        return self._read(self.case_root, self.allowed_case, name, "read_staged_case_file")

    def read_staged_skill_file(self, name: str) -> bytes:
        if self.arm != "full":
            raise ToolSurfaceError("skill file reads are full-arm only")
        declared = SKILL_PREFIX + name if name.startswith("references/") else name
        return self._read(self.skill_root, self.allowed_skill, name, "read_staged_skill_file", declared_name=declared)

    def initial_model_material(self) -> dict[str, bytes]:
        return {
            name: self._read(self.skill_root, self.allowed_skill, name, "initial_model_material")
            for name in INITIAL_FILES[self.arm]
        }

    def run_staged_bundled_scanner(self, *, timeout: int = 180) -> bytes:
        if self.arm != "full":
            raise ToolSurfaceError("bundled scanner is full-arm only")
        if timeout != 180:
            raise ToolSurfaceError("scanner timeout is fixed by the broker")
        self._verify_staged_material()
        home = self.workspace / "home"
        temporary = self.workspace / "tmp"
        home.mkdir(exist_ok=True, mode=0o700)
        temporary.mkdir(exist_ok=True, mode=0o700)
        env = {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(home),
            "TMPDIR": str(temporary),
            "LANG": "C",
            "LC_ALL": "C",
            **SCANNER_ENV,
        }
        command = ["/bin/bash", "-p", str(self.scanner), str(self.case_root.joinpath(*relative_path(self.source_root).parts))]
        try:
            completed = subprocess.run(command, cwd=self.workspace, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ToolSurfaceError("scanner timed out; call is invalid") from exc
        if len(completed.stdout) > 1048576 or len(completed.stderr) > 1048576:
            raise ToolSurfaceError("scanner output exceeded the broker bound")
        self.transcript.append({
            "tool": "run_staged_bundled_scanner",
            "arguments": {"source_root": self.source_root},
            "command": command,
            "environment": env,
            "exit_code": completed.returncode,
            "stdout_sha256": digest(completed.stdout),
            "stdout_base64": base64.b64encode(completed.stdout).decode("ascii"),
            "stderr_sha256": digest(completed.stderr),
            "stderr_base64": base64.b64encode(completed.stderr).decode("ascii"),
        })
        self._verify_staged_material()
        if completed.returncode != 0 or not scanner_report_complete(completed.stdout) or b"INCOMPLETE" in completed.stdout:
            raise ToolSurfaceError(f"scanner did not complete a valid Tier 3 result: {completed.stderr[:300]!r}")
        return completed.stdout

    def _verify_staged_material(self) -> None:
        for name, expected in self.scanner_digests.items():
            source = relative_path(f"skills/e2e-reviewer/scripts/{name}")
            if digest(safe_source_bytes(self.skill_root, source, 1048576)) != expected:
                raise ToolSurfaceError("staged scanner changed")
        for name, expected in self.allowed_skill.items():
            if digest(safe_source_bytes(self.skill_root, relative_path(name), 1048576)) != expected:
                raise ToolSurfaceError("staged skill changed")
        for name, expected in self.allowed_case.items():
            if digest(safe_source_bytes(self.case_root, relative_path(name), 1048576)) != expected:
                raise ToolSurfaceError("staged case changed")
