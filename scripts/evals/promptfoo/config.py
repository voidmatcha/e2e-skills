#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare a model-free Promptfoo evaluation of a recorded holdout cell."""

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys

from provider import project


def write_config(report, case, output):
    request = {"report": str(report.resolve()),
               "sha256": hashlib.sha256(report.read_bytes()).hexdigest(), "case": case}
    projection = project(request)
    config = {
        "description": "CLI holdout transport canary; assertion PASS is not a benchmark PASS",
        "sharing": False,
        "prompts": ["{{request}}"],
        "providers": [{"id": "exec:" + shlex.join([sys.executable, str(Path(__file__).with_name("provider.py"))]), "label": "Existing CLI report (no new model calls)"}],
        "tests": [{"description": case, "vars": {"request": json.dumps(request)}, "assert": [
            {"type": "javascript", "value": "const r=JSON.parse(output);\nreturn r.model_calls_by_provider===0 && r.mode==='recorded-report' && r.cell_count===1;"},
            {"type": "javascript", "value": "const r=JSON.parse(output);\nreturn r.source_status===" + json.dumps(projection["source_status"]) + " && r.report_sha256===" + json.dumps(request["sha256"]) + ";"},
            {"type": "javascript", "value": "const r=JSON.parse(output);\nreturn JSON.stringify(r.cell)===JSON.stringify(JSON.parse(" + json.dumps(json.dumps(projection["cell"], separators=(",", ":"))) + "));"},
        ]}],
        "evaluateOptions": {"maxConcurrency": 1, "cache": False},
    }
    with output.open("x") as file:
        file.write(json.dumps(config, indent=2) + "\n")
    return projection


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_config(args.report, args.case, args.output)
