#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarize v2 with the unchanged v1 paired-control calculation."""

import hashlib
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evals/summarize-real-fix-scanner-inclusive-v1.py"
EXPECTED_SCRIPT_SHA256 = "57b162a2b63884fc0ecefe0274a173538628837c81e45790298cddf9287d3577"
if hashlib.sha256(SCRIPT.read_bytes()).hexdigest() != EXPECTED_SCRIPT_SHA256:
    raise SystemExit("pinned v1 scanner summary drift")
spec = importlib.util.spec_from_file_location("scanner_inclusive_v1_summary", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.PROTOCOL = ROOT / "benchmarks/real-fix-scanner-inclusive-v2/protocol.json"

if __name__ == "__main__":
    module.main()
