#!/usr/bin/env python3
"""Keep benchmarks/external-evidence.json honest.

2.0.1 moved the raw run artifacts out of the tree into a pinned revision of a
Hugging Face dataset. This test needs no network. It fails if the manifest is
malformed, if a listed directory is tracked again or is not gitignored, or if
the fetch script stops reading the same manifest.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "benchmarks" / "external-evidence.json"
FETCH = ROOT / "scripts" / "dev" / "fetch-benchmark-evidence.sh"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=False, capture_output=True, text=True
    ).stdout


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key in ("dataset", "repo_type", "revision", "path_prefix_in_dataset", "file_count", "directories"):
        assert key in manifest, f"manifest is missing {key}"
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["revision"]), "revision must be a full commit id"
    assert re.fullmatch(r"[\w.-]+/[\w.-]+", manifest["dataset"]), "dataset must be owner/name"
    assert manifest["repo_type"] == "dataset"

    directories = manifest["directories"]
    assert directories and len(directories) == len(set(directories)), "directories must be unique"
    assert directories == sorted(directories), "keep directories sorted"
    for directory in directories:
        assert not directory.startswith("/") and ".." not in directory.split("/"), directory
        assert (ROOT / "benchmarks" / directory).parent.is_dir(), f"no parent benchmark for {directory}"
        assert not git("ls-files", f"benchmarks/{directory}").strip(), f"{directory} is tracked again"
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", f"benchmarks/{directory}/x"], cwd=ROOT, check=False
        )
        assert ignored.returncode == 0, f"{directory} is not gitignored"

    result = subprocess.run(
        ["/bin/bash", "-p", str(FETCH), "--dry-run"], cwd=ROOT, check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert manifest["revision"] in result.stdout
    for directory in directories:
        assert directory in result.stdout, f"fetch script does not list {directory}"

    print(
        f"external evidence manifest: pass ({len(directories)} directories, "
        f"{manifest['file_count']} files pinned to {manifest['revision'][:8]})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
