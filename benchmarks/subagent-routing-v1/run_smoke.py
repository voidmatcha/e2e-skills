#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Smoke-stage entrypoint for the shared subagent-routing-v1 harness.

This wrapper adds ``--stage smoke`` and delegates everything else to
``run_routing.py``.  A smoke invocation still requires ``--execute`` before it
can make a model call; ``--self-test`` remains offline.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def load_runner():
    path = Path(__file__).with_name("run_routing.py")
    spec = importlib.util.spec_from_file_location("subagent_routing_runner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import shared routing runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    runner = load_runner()
    arguments = sys.argv[1:]
    if "--stage" not in arguments:
        arguments = ["--stage", "smoke", *arguments]
    try:
        sys.exit(runner.main(arguments))
    except runner.ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
