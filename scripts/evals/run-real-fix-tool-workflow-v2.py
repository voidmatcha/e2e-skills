#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Frozen v1 workflow runner with one sandbox policy correction.

The read-only Codex sandbox prevented the bundled scanner from creating its
trusted temporary directory. V2 changes only that sandbox value; staged source
mutation is still checked after every call and the workspace is disposable.
"""

import hashlib
import json
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "scripts/evals/run-real-fix-tool-workflow-v1.py"
PROTOCOL = ROOT / "benchmarks/real-fix-tool-workflow-v2/protocol.json"
source = V1.read_bytes()
protocol = json.loads(PROTOCOL.read_text())
if hashlib.sha256(source).hexdigest() != protocol["v1_runner_sha256"]:
    raise ValueError("v1 runner drift")
if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != protocol["wrapper_sha256"]:
    raise ValueError("v2 wrapper drift")
old = b'"--skip-git-repo-check", "--sandbox", "read-only"'
new = b'"--skip-git-repo-check", "--sandbox", "workspace-write"'
if source.count(old) != 1:
    raise ValueError("sandbox substitution anchor drift")
patched = source.replace(old, new, 1)
old_gate = b'                report["calls"].append({'
new_gate = b'''                if cell["arm"] == "workflow" and (
                    len(scans) != 1 or not any("Summary:" in item["output"] for item in scans)
                ):
                    report["stop"] = f"cell {index + 1} scanner did not complete"
                    save(args.output_dir / "report.json", report)
                    raise ValueError(report["stop"])
                report["calls"].append({'''
if patched.count(old_gate) != 1:
    raise ValueError("scanner completion gate anchor drift")
patched = patched.replace(old_gate, new_gate, 1)
module = types.ModuleType("real_fix_tool_workflow_v2")
module.__file__ = str(V1)
sys.modules[module.__name__] = module
exec(compile(patched, str(V1), "exec"), module.__dict__)
module.PROTOCOL = PROTOCOL
module.main()
