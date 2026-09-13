#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Smoke-stage entrypoint for the isolated confirmation harness."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


path = Path(__file__).with_name("run_routing.py")
spec = importlib.util.spec_from_file_location("confirmation_routing_runner", path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot import confirmation runner: {path}")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if "--stage" not in arguments:
        arguments = ["--stage", "smoke", *arguments]
    try:
        sys.exit(runner.main(arguments))
    except runner.ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
