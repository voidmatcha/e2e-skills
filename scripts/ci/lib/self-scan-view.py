#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""CI self-scan with one byte-pinned historical experimental control.

The product scanner and frozen evidence stay unchanged. Copy the entire source
(including untracked files), except root Git internals, into an owned temporary
view. Only the exact frozen control is absent there. Its original direct scan
must still report the two known candidates. No cache or source directories are
silently pruned; unsupported filesystem entries make this gate incomplete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

FROZEN_PATH = "scripts/evals/hybrid-check-pilot/check-docker-matrix/notepad.spec.cjs"
FROZEN_SHA256 = "12b916469ae234cc70e3f2ad523fd28691176e4ef3f70e6a634fb4ebdf166018"
FROZEN_MODE = 0o644
SCANNER = "skills/e2e-reviewer/scripts/scan.sh"
REQUIRED = ("AGENTS.md", "skills/e2e-reviewer/SKILL.md", SCANNER,
            "scripts/ci/test-reviewer-scanner.py")


class ViewError(ValueError):
    """The view cannot prove its source identity or frozen exception."""


def describe_file(path: Path) -> dict:
    # Do not follow even a last-component link substituted after enumeration.
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ViewError(f"not a regular file: {path}")
        digest = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(handle.fileno())
    stable = lambda info: (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                           info.st_mtime_ns, info.st_ctime_ns)
    if stable(before) != stable(after) or stable(path.lstat()) != stable(after):
        raise ViewError(f"source changed while fingerprinting: {path}")
    return {"kind": "file", "mode": stat.S_IMODE(after.st_mode),
            "bytes": after.st_size, "sha256": digest.hexdigest()}


def inventory(root: Path) -> dict[str, dict]:
    """Inventory all entries; root Git metadata alone is not scan input."""
    result = {}

    def visit(directory: Path) -> None:
        for path in sorted(directory.iterdir()):
            name = path.relative_to(root).as_posix()
            info = path.lstat()
            if name == ".git":
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                    raise ViewError("unsafe root Git boundary")
                continue
            if stat.S_ISREG(info.st_mode):
                result[name] = describe_file(path)
            elif stat.S_ISDIR(info.st_mode):
                result[name] = {"kind": "directory", "mode": stat.S_IMODE(info.st_mode)}
                visit(path)
            else:
                raise ViewError(f"unsupported symlink or special entry: {name}")
    visit(root)
    return result


def validate_frozen(entries: dict[str, dict]) -> None:
    frozen = entries.get(FROZEN_PATH, {})
    if (frozen.get("kind") != "file" or frozen.get("sha256") != FROZEN_SHA256
            or frozen.get("mode") != FROZEN_MODE):
        raise ViewError(f"missing or drifted frozen control: {FROZEN_PATH}")
    for name in REQUIRED:
        if entries.get(name, {}).get("kind") != "file":
            raise ViewError(f"missing regular identity/scanner file: {name}")


def verify_view(source: Path, view: Path, original: dict[str, dict]) -> None:
    if inventory(source) != original:
        raise ViewError("source entries/content/modes changed during self-scan")
    expected = {name: entry for name, entry in original.items() if name != FROZEN_PATH}
    if inventory(view) != expected:
        raise ViewError("view entries/content/modes differ from complete source inventory")
    boundary = view / ".git"
    if boundary.is_symlink() or not boundary.is_dir() or any(boundary.iterdir()):
        raise ViewError("view Git boundary is not an empty owned directory")


def create_view(source: Path, view: Path) -> dict[str, dict]:
    source = source.resolve(strict=True)
    view = view.parent.resolve(strict=True) / view.name
    if view == source or view.is_relative_to(source) or source.is_relative_to(view):
        raise ViewError("temporary view must be outside the source")
    if view.exists() or view.is_symlink():
        raise ViewError("temporary view must be fresh")
    original = inventory(source)
    validate_frozen(original)
    view.mkdir()
    (view / ".git").mkdir()
    for name, entry in original.items():
        if name == FROZEN_PATH:
            continue
        target = view / name
        if entry["kind"] == "directory":
            target.mkdir()
        else:
            with os.fdopen(os.open(source / name, os.O_RDONLY | os.O_NOFOLLOW), "rb") as incoming:
                if not stat.S_ISREG(os.fstat(incoming.fileno()).st_mode):
                    raise ViewError(f"source stopped being regular: {name}")
                with target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
            target.chmod(entry["mode"])
    # Apply directory permissions after children have been created.
    for name, entry in reversed(list(original.items())):
        if entry["kind"] == "directory":
            (view / name).chmod(entry["mode"])
    verify_view(source, view, original)
    return original


def scan(source: Path, target: str, *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", "-p", str(source / SCANNER), target], cwd=source,
        env={**os.environ, "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
             "E2E_SMELL_FAIL_ON": "p0-candidate"},
        text=True, stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def verify_original_candidates(result: subprocess.CompletedProcess) -> None:
    output = result.stdout or ""
    summaries = re.findall(r"^Summary: .*?, (\d+) P0, .*?, (\d+) P0 candidate;", output, re.M)
    candidates = re.findall(r"^\[P0\?\]\[LLM-TRIAGE\] (#\S+) .*? \((\d+) hit\)", output, re.M)
    if (result.returncode != 1 or summaries != [("0", "2")]
            or sorted(candidates) != [("#3", "1"), ("#5a", "1")]
            or "INCOMPLETE" in output):
        raise ViewError("original frozen-control scan did not retain exactly #3/#5a candidates")


def run(source: Path) -> int:
    source = source.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="e2e-self-scan-view-") as raw:
        view = Path(raw) / "project"
        original = create_view(source, view)
        print(f"self-scan-view: exact historical-control exception {FROZEN_PATH} "
              f"sha256={FROZEN_SHA256} mode=0644", flush=True)
        print("self-scan-view: original fixture direct scan follows; expected exit 1, "
              "0 P0 and 2 P0 candidates (#3/#5a), retained for review", flush=True)
        direct = scan(source, FROZEN_PATH, capture=True)
        print(direct.stdout, end="", flush=True)
        print(f"self-scan-view: original fixture scanner exit={direct.returncode}", flush=True)
        verify_original_candidates(direct)
        verify_view(source, view, original)
        digest = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
        print(f"self-scan-view: complete source identity verified; "
              f"entries={len(original)} sha256={digest}; only root Git internals replaced", flush=True)
        for target in ("skills", "scripts"):
            print(f"self-scan-view: unchanged scanner p0-candidate gate for {target}", flush=True)
            result = scan(view, target)
            verify_view(source, view, original)
            if result.returncode:
                return result.returncode if result.returncode > 0 else 128 - result.returncode
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    try:
        return run(args.source)
    except (OSError, ViewError) as error:
        print(f"self-scan-view: INCOMPLETE: {error}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
