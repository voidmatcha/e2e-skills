#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Isolated Claude-only confirmation runner for subagent-routing-v1.

This entrypoint deliberately reuses the frozen pilot harness implementation
while rebinding every benchmark path to this confirmation directory.  The
confirmation retains the pilot's strict parser, normalizer, route attestation,
workspace isolation, request accounting, rerun semantics, and stop rules.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
PARENT_RUNNER = HERE.parent / "run_routing.py"


def load_parent():
    spec = importlib.util.spec_from_file_location(
        "subagent_routing_confirmation_parent", PARENT_RUNNER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import parent routing runner: {PARENT_RUNNER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_parent()
runner.BENCHMARK_DIR = HERE
runner.PROTOCOL_PATH = HERE / "protocol.json"
runner.FREEZE_PATH = HERE / "freeze-record.json"
runner.CASE_MANIFEST_PATH = HERE / "cases" / "manifest.json"
runner.SMOKE_MANIFEST_PATH = HERE / "smoke" / "manifest.json"
runner.ACTIVATION_PATH = HERE / "codex-arm-activation.json"
runner.__file__ = str(Path(__file__).resolve())
runner.CONTRACT_FOR_TASK = {
    "finding_verification": (
        "benchmarks/subagent-routing-v1/confirmation-v1/evaluated-snapshot/"
        "skills/e2e-reviewer/references/pattern-reference.md"
    ),
    "failure_classification.playwright": (
        "benchmarks/subagent-routing-v1/confirmation-v1/evaluated-snapshot/"
        "skills/playwright-debugger/SKILL.md"
    ),
    "failure_classification.cypress": (
        "benchmarks/subagent-routing-v1/confirmation-v1/evaluated-snapshot/"
        "skills/cypress-debugger/SKILL.md"
    ),
}
runner.AGENT_SOURCE = {
    "e2e-finding-verifier": (
        "benchmarks/subagent-routing-v1/confirmation-v1/evaluated-snapshot/"
        "agents/e2e-finding-verifier.md"
    ),
    "e2e-failure-classifier": (
        "benchmarks/subagent-routing-v1/confirmation-v1/evaluated-snapshot/"
        "agents/e2e-failure-classifier.md"
    ),
}


def guard_concurrency() -> list[str]:
    """Reject real peer workloads without treating polling shells as workloads."""
    pattern = r"run_(routing|smoke|pilot)\.py|run-reviewer-holdout|run-fixture-faults|ci-local\.sh"
    completed = subprocess.run(
        ["/usr/bin/pgrep", "-fl", pattern], capture_output=True, text=True, check=False
    )
    others = []
    for line in completed.stdout.splitlines():
        fields = line.split(maxsplit=1)
        if not fields or not fields[0].isdigit() or int(fields[0]) == os.getpid():
            continue
        command = fields[1] if len(fields) == 2 else ""
        if re.search(r"\bwhile\s+pgrep\b", command):
            continue
        others.append(line[:200])
    if others:
        raise runner.ContractError(f"another model/browser/CI harness is active: {others[:3]}")
    return others


runner.guard_concurrency = guard_concurrency


ContractError = runner.ContractError


def main(argv: list[str] | None = None) -> int:
    return runner.main(argv)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
