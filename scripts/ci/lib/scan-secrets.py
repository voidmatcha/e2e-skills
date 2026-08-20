#!/usr/bin/env python3
"""Fail-closed high-confidence secret scan over shipped textual files."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


PATTERNS = (
    (
        "AWS access key",
        re.compile(r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z2-7]{16}(?![A-Z0-9])"),
    ),
    (
        "OpenAI project secret",
        re.compile(
            r"(?<![A-Za-z0-9_-])sk-proj-"
            r"(?:"
            r"[A-Za-z0-9_-]{58}T3BlbkFJ[A-Za-z0-9_-]{58}"
            r"|"
            r"[A-Za-z0-9_-]{74}T3BlbkFJ[A-Za-z0-9_-]{74}"
            r")"
            r"(?![A-Za-z0-9_-])"
        ),
    ),
    (
        "OpenAI-style secret",
        re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}(?![A-Za-z0-9])"),
    ),
    (
        "GitHub personal access token",
        re.compile(
            r"(?<![A-Za-z0-9_])"
            r"(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82})"
            r"(?![A-Za-z0-9_])"
        ),
    ),
    ("Slack token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    (
        "private key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
)
SOURCE_SUFFIXES = {
    ".bash",
    ".cfg",
    ".cjs",
    ".conf",
    ".cts",
    ".env",
    ".gradle",
    ".ini",
    ".js",
    ".json",
    ".jsonc",
    ".jsx",
    ".key",
    ".lock",
    ".md",
    ".mjs",
    ".mts",
    ".pem",
    ".plist",
    ".properties",
    ".py",
    ".pyi",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}
SOURCE_NAMES = {
    ".npmrc",
    ".pypirc",
    "Dockerfile",
    "Makefile",
}
TEXT_ASSET_SUFFIXES = {
    ".css",
    ".csv",
    ".gql",
    ".graphql",
    ".htm",
    ".html",
    ".rst",
    ".sql",
    ".svg",
    ".txt",
    ".webmanifest",
}
EXCLUDED_PATH = Path("scripts/ci/lib/scan-secrets.py")
MAX_TEXT_BYTES = 8 * 1024 * 1024


def is_source_or_config(path: Path) -> bool:
    return (
        path.suffix.lower() in SOURCE_SUFFIXES
        or path.name in SOURCE_NAMES
        or path.name == ".env"
        or path.name.startswith(".env.")
    )


def is_declared_text(path: Path) -> bool:
    return is_source_or_config(path) or path.suffix.lower() in TEXT_ASSET_SUFFIXES


def is_text_candidate(path: Path) -> bool:
    return is_declared_text(path) or not path.suffix


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
        if relative == EXCLUDED_PATH:
            continue
        if not is_text_candidate(relative):
            continue
        files.append(relative)
    if not files:
        raise RuntimeError("secret scan selected zero shipped text files")
    return sorted(set(files))


def scan(root: Path, test_git: Path | None = None) -> list[str]:
    findings = []
    for relative in enumerate_files(root, test_git):
        path = root / relative
        if path.is_symlink():
            raise RuntimeError("selected path is a symlink: {}".format(relative))
        try:
            if path.stat().st_size > MAX_TEXT_BYTES:
                raise RuntimeError(
                    "selected text file exceeds the {}-byte limit: {}".format(
                        MAX_TEXT_BYTES,
                        relative,
                    )
                )
            with path.open("rb") as handle:
                data = handle.read(MAX_TEXT_BYTES + 1)
            if len(data) > MAX_TEXT_BYTES:
                raise RuntimeError(
                    "selected text file exceeds the {}-byte limit: {}".format(
                        MAX_TEXT_BYTES,
                        relative,
                    )
                )
            if b"\0" in data:
                raise RuntimeError(
                    "selected text file contains a NUL byte: {}".format(relative)
                )
            text = data.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError("cannot read {}: {}".format(relative, exc))
        for line_number, line in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append(
                        "{}:{}: {}".format(relative, line_number, label)
                    )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--test-git", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.repo.resolve()
    try:
        findings = scan(root, args.test_git)
    except RuntimeError as exc:
        print("secret-scanner: infrastructure error: {}".format(exc), file=sys.stderr)
        return 2
    if findings:
        for finding in findings:
            print(finding)
        return 1
    print(
        "secret-scanner: clean "
        "({} declared text suffixes plus extensionless UTF-8 files checked)".format(
            len(SOURCE_SUFFIXES | TEXT_ASSET_SUFFIXES)
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
