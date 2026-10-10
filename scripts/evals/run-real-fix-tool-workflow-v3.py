#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Frozen tool-workflow runner with a spec-root scanner completion gate.

V2 stopped after the model completed the named spec scan and also scanned a
context fixture. V3 requires one complete scan of the named E2E spec and
records any additional scans without treating them as a missing scan.
"""

import hashlib
import json
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "scripts/evals/run-real-fix-tool-workflow-v1.py"
PROTOCOL = ROOT / "benchmarks/real-fix-tool-workflow-v3/protocol.json"
source = V1.read_bytes()
protocol = json.loads(PROTOCOL.read_text())
if hashlib.sha256(source).hexdigest() != protocol["v1_runner_sha256"]:
    raise ValueError("v1 runner drift")
if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != protocol["wrapper_sha256"]:
    raise ValueError("v3 wrapper drift")
old = b'"--skip-git-repo-check", "--sandbox", "read-only"'
new = b'"--skip-git-repo-check", "--sandbox", "workspace-write"'
if source.count(old) != 1:
    raise ValueError("sandbox substitution anchor drift")
patched = source.replace(old, new, 1)
old_gate = b'                report["calls"].append({'
new_gate = b'''                spec_scans = [item for item in scans
                              if case["spec"] in item["command"]]
                if cell["arm"] == "workflow" and (
                    len(spec_scans) != 1
                    or not all("Summary:" in item["output"] for item in spec_scans)
                ):
                    report["stop"] = f"cell {index + 1} spec scanner did not complete"
                    save(args.output_dir / "report.json", report)
                    raise ValueError(report["stop"])
                report["calls"].append({'''
if patched.count(old_gate) != 1:
    raise ValueError("scanner completion gate anchor drift")
patched = patched.replace(old_gate, new_gate, 1)
module = types.ModuleType("real_fix_tool_workflow_v3")
module.__file__ = str(V1)
sys.modules[module.__name__] = module
exec(compile(patched, str(V1), "exec"), module.__dict__)
module.PROTOCOL = PROTOCOL
module.main()
