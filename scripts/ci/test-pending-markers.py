#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prove the PENDING-THIN-EVAL release gate fails and passes where it should."""

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("gate", ROOT / "scripts/ci/check-pending-markers.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def tree(version: str, readme: str) -> Path:
    base = Path(tempfile.mkdtemp(prefix="pending-markers-"))
    (base / ".claude-plugin").mkdir()
    (base / ".claude-plugin/plugin.json").write_text(json.dumps({"version": version}))
    (base / "README.md").write_text(readme)
    return base


marked = "CLI is the default <!-- PENDING-THIN-EVAL -->\n"
assert gate.check(tree("3.0.0", marked)), "release version with a marker must fail"
assert not gate.check(tree("3.0.0", "CLI is the default\n")), "release version without a marker passes"
assert not gate.check(tree("3.0.0-rc.1", marked)), "prerelease versions may carry markers"
assert gate.check(tree("3.0.0", marked))[0].endswith("README.md:1")
print("pending-marker gate tests: pass (release+marker fails; clean and prerelease pass)")
