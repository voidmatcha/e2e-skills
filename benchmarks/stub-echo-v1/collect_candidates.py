#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect stub-echo candidates from the frozen field-scan-v1 corpus.

Deterministic and model-free: it reports every line where a test observes a
response object inside a file that also installs a stub, with the surrounding
window an adjudicator needs. Judging the candidates is a separate, manual step;
this file exists so that the decision surface is collected by a rule frozen
before anyone looks at the results.

Usage:
    collect_candidates.py --checkouts <dir> [--output candidates.json]

`--checkouts` holds one directory per repository, named `<owner>__<name>`,
checked out at the sha pinned in benchmarks/field-scan-v1/repos.json. The
collector verifies each sha before reading the tree.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "benchmarks/field-scan-v1/repos.json"

SPEC_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
SPEC_MARKERS = (".spec.", ".test.", ".cy.")
SPEC_DIRECTORIES = ("cypress/e2e", "cypress/integration")
SKIPPED_DIRECTORIES = {"node_modules", ".git", "dist", "build", "coverage"}

STUB_MARKERS = ("page.route(", "cy.intercept(")
RESPONSE_OBSERVERS = (
    re.compile(r"page\s*\.\s*waitForResponse\s*\("),
    re.compile(r"page\s*\.\s*waitForEvent\s*\(\s*['\"]response['\"]"),
    re.compile(r"cy\s*\.\s*wait\s*\(\s*['\"]@"),
)
WINDOW = 8
MAX_BYTES = 2 * 1024 * 1024


def pinned_repositories() -> list[dict]:
    data = json.loads(CORPUS.read_text(encoding="utf-8"))
    return data["repositories"]


def is_spec(path: Path) -> bool:
    if path.suffix not in SPEC_SUFFIXES:
        return False
    posix = path.as_posix()
    if any(part in SKIPPED_DIRECTORIES for part in path.parts):
        return False
    return any(marker in path.name for marker in SPEC_MARKERS) or any(
        directory in posix for directory in SPEC_DIRECTORIES
    )


def verify_checkout(directory: Path, sha: str) -> None:
    head = subprocess.run(
        ["/usr/bin/git", "-C", str(directory), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode != 0:
        raise SystemExit(f"{directory}: not a git checkout")
    if head.stdout.strip() != sha:
        raise SystemExit(
            f"{directory}: HEAD {head.stdout.strip()[:12]} is not the pinned {sha[:12]}"
        )


def collect(directory: Path, repository: str, sha: str) -> list[dict]:
    candidates: list[dict] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.is_symlink() or not is_spec(path):
            continue
        if path.stat().st_size > MAX_BYTES:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        source = "\n".join(lines)
        if not any(marker in source for marker in STUB_MARKERS):
            continue
        for index, line in enumerate(lines, start=1):
            if not any(pattern.search(line) for pattern in RESPONSE_OBSERVERS):
                continue
            start = max(1, index - WINDOW)
            end = min(len(lines), index + WINDOW)
            candidates.append(
                {
                    "repository": repository,
                    "sha": sha,
                    "file": path.relative_to(directory).as_posix(),
                    "line": index,
                    "snippet": line.strip(),
                    "window": lines[start - 1 : end],
                    "window_start": start,
                    "verdict": None,
                    "reason": None,
                }
            )
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkouts", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("candidates.json"))
    args = parser.parse_args()

    repositories = pinned_repositories()
    results: list[dict] = []
    coverage: list[dict] = []
    for entry in repositories:
        repository = entry["repository"]
        sha = entry["sha"]
        directory = args.checkouts / repository.replace("/", "__")
        if not directory.is_dir():
            coverage.append({"repository": repository, "status": "missing_checkout"})
            continue
        verify_checkout(directory, sha)
        found = collect(directory, repository, sha)
        coverage.append(
            {"repository": repository, "status": "collected", "candidates": len(found)}
        )
        results.extend(found)

    report = {
        "schema_version": 1,
        "protocol": "stub-echo-v1",
        "corpus": str(CORPUS.relative_to(ROOT)),
        "coverage": coverage,
        "candidate_count": len(results),
        "candidates": results,
    }
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"candidates: {len(results)} from {len(repositories)} pinned repositories")
    for row in coverage:
        print(f"  {row['repository']}: {row['status']} {row.get('candidates', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
