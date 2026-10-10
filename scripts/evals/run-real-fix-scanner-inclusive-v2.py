#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the frozen v1 scanner workflow against the separately frozen v2 protocol."""

import hashlib
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/evals/run-real-fix-scanner-inclusive-v1.py"
EXPECTED_RUNNER_SHA256 = "aabec9dbe71fe75c812568a3e54585d55d1e939a8ddcce08df0d4cdf6f977851"
if hashlib.sha256(RUNNER.read_bytes()).hexdigest() != EXPECTED_RUNNER_SHA256:
    raise SystemExit("pinned v1 scanner runner drift")

spec = importlib.util.spec_from_file_location("scanner_inclusive_v1_runner", RUNNER)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.PROTOCOL = ROOT / "benchmarks/real-fix-scanner-inclusive-v2/protocol.json"

if __name__ == "__main__":
    module.main()
