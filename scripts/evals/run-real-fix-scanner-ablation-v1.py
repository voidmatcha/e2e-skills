#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Same-skill scanner ablation on the frozen real-fix tool workflow."""

import hashlib
import json
import shutil
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "scripts/evals/run-real-fix-tool-workflow-v1.py"
PROTOCOL = ROOT / "benchmarks/real-fix-scanner-ablation-v1/protocol.json"
ARMS = ("scanner", "no-scanner")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ablation_prompt(original_prompt, arm, case, legend):
    full = original_prompt("workflow", case, legend)
    if arm == "scanner":
        return full
    if arm != "no-scanner":
        raise ValueError(f"unknown arm: {arm}")
    original = (
        "Read and follow its complete review workflow, including its mandatory "
        "scanner and semantic references."
    )
    override = (
        "Read and follow its complete review workflow except this explicit "
        "experimental override: read the scanner reference but do not execute "
        "scan.sh or another mechanical scanner. Perform all semantic sweeps and "
        "source confirmation manually."
    )
    if full.count(original) != 1:
        raise ValueError("prompt ablation anchor drift")
    return full.replace(original, override, 1)


def main():
    protocol = json.loads(PROTOCOL.read_text())
    source = V1.read_bytes()
    if digest(source) != protocol["v1_runner_sha256"]:
        raise ValueError("v1 runner drift")
    if digest(Path(__file__).read_bytes()) != protocol["wrapper_sha256"]:
        raise ValueError("ablation wrapper drift")
    old = b'"--skip-git-repo-check", "--sandbox", "read-only"'
    if source.count(old) != 1:
        raise ValueError("sandbox substitution anchor drift")
    patched = source.replace(old, b'"--skip-git-repo-check", "--sandbox", "workspace-write"', 1)
    anchor = b'                report["calls"].append({'
    gate = b'''                spec_scans = [item for item in scans
                              if case["spec"] in item["command"]]
                if cell["arm"] == "scanner" and (
                    len(spec_scans) != 1
                    or not all("Summary:" in item["output"] for item in spec_scans)
                ):
                    report["stop"] = f"cell {index + 1} spec scanner did not complete"
                    save(args.output_dir / "report.json", report)
                    raise ValueError(report["stop"])
                if cell["arm"] == "no-scanner" and scans:
                    report["stop"] = f"cell {index + 1} unexpectedly used scanner"
                    save(args.output_dir / "report.json", report)
                    raise ValueError(report["stop"])
                report["calls"].append({'''
    if patched.count(anchor) != 1:
        raise ValueError("scanner gate anchor drift")
    patched = patched.replace(anchor, gate, 1)
    module = types.ModuleType("real_fix_scanner_ablation_v1")
    module.__file__ = str(V1)
    sys.modules[module.__name__] = module
    exec(compile(patched, str(V1), "exec"), module.__dict__)
    module.PROTOCOL = PROTOCOL
    module.ARMS = ARMS
    original_stage = module.staged_cases
    original_prompt = module.prompt

    def stage_with_skill(root, selected):
        workspaces, sources = original_stage(root, selected)
        for workspace in workspaces.values():
            shutil.copytree(module.SKILL, workspace / ".skill/e2e-reviewer")
        return workspaces, sources

    module.staged_cases = stage_with_skill
    module.prompt = lambda arm, case, legend: ablation_prompt(original_prompt, arm, case, legend)
    module.main()


if __name__ == "__main__":
    main()
