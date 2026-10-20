#!/usr/bin/env python3
"""Replay archived v8 analysis with its exact historical helper. Apache-2.0."""
import argparse
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HELPER_SHA256 = "de2317a0fd133fa721e031ca48c4f336750aba596d1f6e64fb97dca0a5acf1e8"
ARCHIVE = ROOT / "benchmarks/historical-sources/sha256" / (HELPER_SHA256 + ".py")
HELPER_PATH = Path("scripts/evals/run-reviewer-holdout.py")
FILES = (
    "scripts/evals/run-generator-skill-effect-v8.py",
    "scripts/evals/run-generator-skill-effect-v3.py",
    "scripts/evals/generator_codex_container_adapter.py",
    "scripts/evals/generator_codex_adapter_v2.py",
    "scripts/evals/generator-codex-container/Dockerfile",
    "scripts/evals/fixtures/package.json",
    "scripts/evals/fixtures/package-lock.json",
    "benchmarks/generator-skill-effect-v8/protocol.json",
    "benchmarks/generator-skill-effect-v8/freeze.json",
    "benchmarks/generator-skill-effect-v3/protocol.json",
    "benchmarks/generator-skill-effect-v3/reports/validation.json",
)
TREES = tuple("benchmarks/generator-skill-effect-v3/" + name for name in ("cases", "truth", "arms"))


def historical_helper():
    data = ARCHIVE.read_bytes()
    if hashlib.sha256(data).hexdigest() != HELPER_SHA256:
        raise ValueError("historical auth helper digest mismatch")
    return data


def stage(root, extra_files=(), extra_trees=(), tree_aliases=()):
    """Copy the finite analysis dependency set; never replace checkout files."""
    helper = historical_helper()
    for relative in (*FILES, *extra_files):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for relative in (*TREES, *extra_trees):
        shutil.copytree(ROOT / relative, root / relative,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (root / HELPER_PATH).write_bytes(helper)
    for source, destination in tree_aliases:
        shutil.copytree(ROOT / source, root / destination,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


@contextmanager
def historical_project(extra_files=(), extra_trees=(), tree_aliases=()):
    """Provide physical historical inputs to offline callers, preserving guards."""
    before = (ROOT / HELPER_PATH).read_bytes()
    with tempfile.TemporaryDirectory(prefix="generator-historical-root-") as directory:
        root = Path(directory)
        stage(root, extra_files, extra_trees, tree_aliases)
        try:
            yield root
        finally:
            if (ROOT / HELPER_PATH).read_bytes() != before:
                raise ValueError("current auth helper changed during historical replay")


def replay(scores, output):
    scores, output = scores.resolve(), output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("replay output must be outside the checkout")
    if output.exists():
        raise ValueError("replay output already exists")
    with historical_project() as root:
        # The original runner only receives the analyze verb. No model, browser,
        # dependency installation, auth staging, or live execution is requested.
        command = [sys.executable, str(root / FILES[0]), "analyze", str(scores),
                   "--output", str(output)]
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("GSE3_")}
        result = subprocess.run(command, cwd=root, env=env, check=False)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scores", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    return replay(args.scores, args.output)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError) as error:
        print(f"refused: {error}", file=sys.stderr)
        raise SystemExit(3)
