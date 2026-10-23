#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run one existing CLI holdout cell, then prepare a model-free Promptfoo view."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from provider import project
from config import write_config


ROOT = Path(__file__).resolve().parents[3]


def fresh_external_output(path):
    output = path.expanduser().absolute()
    if any(part.is_symlink() for part in (output, *output.parents)):
        raise ValueError("output must not use symlinks")
    output = output.resolve()
    if output.is_relative_to(ROOT) or output.exists() or not output.parent.is_dir():
        raise ValueError("output must be a fresh directory outside the checkout")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runner-path", type=Path, required=True)
    parser.add_argument("--case", default="playwright-split-context")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    if not args.allow_live:
        parser.error("one live Codex call requires --allow-live")
    try:
        output = fresh_external_output(args.output)
    except ValueError as error:
        parser.error(str(error))
    runner = args.runner_path.expanduser().resolve(strict=True)
    if not runner.is_file() or not os.access(runner, os.X_OK):
        parser.error("runner must be an executable file")
    output.mkdir()
    report = output / "holdout.json"
    command = [sys.executable, str(ROOT / "scripts/evals/run-reviewer-holdout.py"),
               "--runner", "codex", "--runner-path", str(runner),
               "--case", args.case, "--repetitions", "1", "--arm", "full",
               "--model", args.model, "--reasoning-effort", "medium",
               "--timeout", "180", "--allow-live", "--report-only",
               "--output", str(report)]
    (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (output / "harness.stdout.txt").open("w") as stdout, (output / "harness.stderr.txt").open("w") as stderr:
        result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    if not report.is_file():
        raise RuntimeError(f"harness produced no report (exit {result.returncode}); see {output}")
    request = {"report": str(report), "sha256": hashlib.sha256(report.read_bytes()).hexdigest(), "case": args.case}
    projection = project(request)
    expected_exit = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[projection["source_status"]]
    if result.returncode != expected_exit:
        raise RuntimeError("harness exit does not match its report")
    (output / "projection.json").write_text(json.dumps(projection, indent=2) + "\n")
    write_config(report, args.case, output / "promptfooconfig.json")
    print(json.dumps({"output": str(output), "source_status": projection["source_status"],
                      "recorded_cells": 1, "provider_model_calls": 0}))


if __name__ == "__main__":
    main()
