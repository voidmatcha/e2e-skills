#!/usr/bin/env python3
"""Fail-closed repository scans for non-secret security policies."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


SELF = Path("scripts/ci/lib/scan-security-policy.py")
SECURITY_GATE = Path("scripts/ci/pre-push-security.sh")
SHELL_SUFFIXES = {".sh"}
HARDCODED_SUFFIXES = {".sh", ".md", ".json", ".yaml", ".yml", ".py"}
RULES = ("eval", "fixed-tmp", "backdoor", "hardcoded-home")
SHELL_SHEBANG = re.compile(
    br"^#![ \t]*(?:"
    br"/(?:[^ \t\r\n/]+/)*(?:ba|da|k|z)?sh(?:[ \t\r\n]|$)"
    br"|/(?:usr/)?bin/env[ \t]+(?:-S[ \t]+)?"
    br"(?:ba|da|k|z)?sh(?:[ \t\r\n]|$)"
    br")"
)


def git_executable(test_override: Path | None = None) -> str:
    executable = str(test_override) if test_override is not None else "/usr/bin/git"
    if not os.path.isabs(executable):
        raise RuntimeError("git enumerator path must be absolute")
    if not os.path.isfile(executable) or not os.access(executable, os.X_OK):
        raise RuntimeError("git enumerator unavailable: {}".format(executable))
    return executable


def enumerate_files(root: Path, test_git: Path | None = None) -> list[Path]:
    completed = subprocess.run(
        [
            git_executable(test_git),
            "ls-files",
            "-co",
            "--exclude-standard",
            "-z",
            "--",
        ],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            "git file enumeration failed (exit {}): {}".format(
                completed.returncode,
                detail or "no diagnostic",
            )
        )
    raw_paths = [item for item in completed.stdout.split(b"\0") if item]
    if not raw_paths:
        raise RuntimeError("git file enumeration returned zero files")
    files = []
    for raw in raw_paths:
        try:
            relative = Path(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise RuntimeError("non-UTF-8 repository path: {}".format(exc))
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("unsafe repository path from git: {}".format(relative))
        files.append(relative)
    return sorted(set(files))


def is_shell_program(root: Path, relative: Path) -> bool:
    if relative.suffix.lower() in SHELL_SUFFIXES:
        return True
    path = root / relative
    if path.is_symlink() or not path.is_file():
        return False
    try:
        with path.open("rb") as stream:
            first_line = stream.readline(512)
    except OSError as exc:
        raise RuntimeError("cannot inspect {}: {}".format(relative, exc))
    return SHELL_SHEBANG.match(first_line) is not None


def selected(rule: str, root: Path, relative: Path) -> bool:
    if relative == SELF:
        return False
    if rule in {"eval", "fixed-tmp", "backdoor"}:
        return is_shell_program(root, relative)
    return (
        relative.suffix.lower() in HARDCODED_SUFFIXES
        and relative.parts[:1]
        in {
            ("scripts",),
            ("skills",),
            (".claude-plugin",),
            (".codex-plugin",),
        }
    )


def line_matches(rule: str, line: str) -> bool:
    if rule == "eval":
        eval_command = re.compile(
            r"""(?:^|[;&|]|\bthen\b|\bdo\b)\s*
            (?:
                (?:builtin|command)
                (?:\s+(?:--|-[A-Za-z]+))*\s+
            )?
            (?:
                ["']eval["']
                |
                e\\?v\\?a\\?l
            )
            (?=\s|$)
            """,
            re.VERBOSE,
        )
        return (
            not line.lstrip().startswith("#")
            and eval_command.search(line) is not None
        )
    if rule == "fixed-tmp":
        remaining = re.sub(
            r"\$\{(?:TMPDIR|TMP|TEMP)(?::?-)/tmp\}",
            "",
            line,
        )
        if re.search(r"/tmp(?:/|$)", remaining) is None:
            return False
        if (
            re.search(r"\bmktemp\b", remaining) is not None
            and re.search(r"/tmp/[^\s\"']*X{6,}", remaining) is not None
        ):
            return False
        return True
    if rule == "backdoor":
        return (
            re.search(
                r"nc -[el]|/dev/tcp/|bash -i.*&|reverse shell|exec [0-9]<>/dev/",
                line,
            )
            is not None
        )
    homes = re.findall(r"/(?:Users|home)/([A-Za-z0-9._-]+)/", line)
    return any(user not in {"example", "placeholder"} for user in homes)


def scan(root: Path, rule: str, test_git: Path | None = None) -> list[str]:
    findings = []
    selected_count = 0
    for relative in enumerate_files(root, test_git):
        path = root / relative
        if relative.parts[:2] == ("scripts", "hooks") and path.is_symlink():
            raise RuntimeError(
                "security-sensitive hook path is a symlink: {}".format(relative)
            )
        if not selected(rule, root, relative):
            continue
        selected_count += 1
        if path.is_symlink():
            raise RuntimeError("selected path is a symlink: {}".format(relative))
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError("cannot read {}: {}".format(relative, exc))
        for line_number, line in enumerate(text.splitlines(), 1):
            if line_matches(rule, line):
                findings.append("{}:{}: {}".format(relative, line_number, rule))
    if selected_count == 0:
        raise RuntimeError("{} scan selected zero files".format(rule))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--rule", required=True, choices=RULES)
    parser.add_argument("--test-git", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        findings = scan(args.repo.resolve(), args.rule, args.test_git)
    except RuntimeError as exc:
        print(
            "security-policy-scanner: infrastructure error: {}".format(exc),
            file=sys.stderr,
        )
        return 2
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print("security-policy-scanner: {} clean".format(args.rule))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
