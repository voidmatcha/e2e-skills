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
RULES = ("eval", "fixed-tmp", "backdoor", "hardcoded-home")
# Cheap byte-level pre-filter for the hardcoded-home rule, checked before the
# more expensive decode + regex pass. Must cover every leak shape line_matches()
# can detect: the classic slash form, the dash/underscore-encoded scratchpad-path
# form, and a machine-local `ls -l`/`ls -la` owner column.
HARDCODED_HOME_TRIGGERS = (
    b"/Users/",
    b"/home/",
    b"-Users-",
    b"_Users_",
    b" staff ",
    b" wheel ",
    b" admin ",
)
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


def git_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = "/dev/null"
    return environment


def enumerate_files(root: Path, test_git: Path | None = None) -> list[Path]:
    completed = subprocess.run(
        [
            git_executable(test_git),
            # Repo-local config can point core.excludesFile at an attacker-chosen
            # list; neutralise it here because GIT_CONFIG_* scrubbing cannot.
            "-c",
            "core.excludesFile=/dev/null",
            "ls-files",
            "-co",
            "--exclude-standard",
            "-z",
            "--",
        ],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=git_environment(),
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


def read_index_blob(root: Path, relative: Path) -> bytes:
    completed = subprocess.run(
        [git_executable(), "cat-file", "blob", ":{}".format(relative.as_posix())],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=git_environment(),
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            "cannot read indexed {}: {}".format(relative, detail or "no diagnostic")
        )
    return completed.stdout


def is_shell_program(root: Path, relative: Path, data: bytes | None = None) -> bool:
    if relative.suffix.lower() in SHELL_SUFFIXES:
        return True
    if data is not None:
        return SHELL_SHEBANG.match(data.splitlines(keepends=True)[0][:512] if data else b"") is not None
    path = root / relative
    if path.is_symlink() or not path.is_file():
        return False
    try:
        with path.open("rb") as stream:
            first_line = stream.readline(512)
    except OSError as exc:
        raise RuntimeError("cannot inspect {}: {}".format(relative, exc))
    return SHELL_SHEBANG.match(first_line) is not None


def selected(rule: str, root: Path, relative: Path, data: bytes | None = None) -> bool:
    if relative == SELF and rule != "hardcoded-home":
        return False
    if rule in {"eval", "fixed-tmp", "backdoor"}:
        return is_shell_program(root, relative, data)
    return True


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
    homes = re.findall(
        r"/(?:Users|home)/([A-Za-z0-9._-]+)(?=/|[^A-Za-z0-9._-]|$)",
        line,
    )
    # Dash/underscore-encoded home paths (e.g. a session scratchpad directory
    # name shaped "-Users-<name>-Documents-...") don't contain a literal
    # "/Users/" substring, so they need their own pattern. Capitalized "Users"
    # only -- a lowercase "home" here is far too common in ordinary compound
    # identifiers (e.g. "pilot-home-A-S1-...") to use as a signal on its own.
    homes += re.findall(
        r"[-_]Users[-_]([A-Za-z0-9.]+)(?=[-_]|$)",
        line,
    )
    # A machine-local `ls -l`/`ls -la` owner column (e.g.
    # "drwxr-xr-x@  18 <name>  staff  576 ...") leaks the real account name
    # without any home-path substring at all.
    homes += re.findall(
        r"[-dlpsc][-rwxXsS]{9}[.@+]?\s+\d+\s+([A-Za-z][A-Za-z0-9._-]*)\s+"
        r"(?:staff|wheel|admin|root|daemon)\s+\d+",
        line,
    )
    return any(
        user not in {"...", "example", "placeholder", "user"}
        for user in homes
    )


def scan(root: Path, rule: str, test_git: Path | None = None) -> list[str]:
    findings = []
    selected_count = 0
    for relative in enumerate_files(root, test_git):
        path = root / relative
        if relative.parts[:2] == ("scripts", "hooks") and path.is_symlink():
            raise RuntimeError(
                "security-sensitive hook path is a symlink: {}".format(relative)
            )
        indexed_data = None
        if not os.path.lexists(path) and test_git is None:
            indexed_data = read_index_blob(root, relative)
        if not selected(rule, root, relative, indexed_data):
            continue
        selected_count += 1
        if path.is_symlink():
            raise RuntimeError("selected path is a symlink: {}".format(relative))
        try:
            if rule == "hardcoded-home":
                raw_lines = (
                    indexed_data.splitlines(keepends=True)
                    if indexed_data is not None
                    else path.read_bytes().splitlines(keepends=True)
                )
                for line_number, raw_line in enumerate(raw_lines, 1):
                    if not any(
                        trigger in raw_line
                        for trigger in HARDCODED_HOME_TRIGGERS
                    ):
                        continue
                    line = raw_line.decode("utf-8", errors="replace")
                    if line_matches(rule, line):
                        findings.append(
                            "{}:{}: {}".format(relative, line_number, rule)
                        )
                continue
            text = (
                indexed_data.decode("utf-8")
                if indexed_data is not None
                else path.read_text(encoding="utf-8")
            )
            for line_number, line in enumerate(text.splitlines(keepends=True), 1):
                if line_matches(rule, line):
                    findings.append(
                        "{}:{}: {}".format(relative, line_number, rule)
                    )
        except (OSError, UnicodeError) as exc:
            raise RuntimeError("cannot read {}: {}".format(relative, exc))
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
