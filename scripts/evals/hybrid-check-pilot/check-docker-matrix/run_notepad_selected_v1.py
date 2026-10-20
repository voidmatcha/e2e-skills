#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run one registered Notepad test plus a setup canary with frozen cell machinery."""

import argparse
import json
import os
from pathlib import Path
import re
import time

import run_notepad_split as frozen
import verify_notepad_split as cell_verifier
import verify_notepad_split_matrix as matrix_verifier


def selected(root: Path, strength: str) -> dict:
    if strength not in ("weak", "strong") or root.exists():
        raise ValueError("one registered strength and fresh output required")
    root.mkdir(exist_ok=False)
    try:
        assert json.loads((frozen.BUNDLE / "gate-receipts/result.json").read_text())["status"] == "NODE_DEPENDENCY_GATE_PASS"
        assert frozen.call(["git", "-C", str(frozen.SOURCE), "rev-parse", "HEAD"]) == frozen.PIN
        assert frozen.call(["git", "-C", str(frozen.SOURCE), "rev-parse", "HEAD^{tree}"]) == frozen.TREE
        assert not frozen.call(["git", "-C", str(frozen.SOURCE), "status", "--porcelain"])
        identities = {image: json.loads(frozen.docker("image", "inspect", image))[0]
                      for image in (frozen.APP_IMAGE, frozen.TEST_IMAGE)}
        assert all(row["Id"] == image and row["Os"] == "linux" and row["Architecture"] == "arm64"
                   for image, row in identities.items())
        disk = os.statvfs(root)
        assert disk.f_bavail * disk.f_frsize >= 4 * 1024 ** 3
        load = os.getloadavg()[0]
        swap = frozen.call(["sysctl", "vm.swapusage"])
        match = re.search(r"used = ([\d.]+)M", swap)
        assert load < 8 and match and float(match[1]) < 4096
        daemon_disk = frozen.call(["colima", "ssh", "--", "df", "-Pk", "/"])
        assert int(daemon_disk.splitlines()[-1].split()[3]) >= 4 * 1024 ** 2
        bundle = frozen.admitted_bundle()
        dependencies = frozen.deps_digest()
        inputs = frozen.frozen()
        frozen.save(root / "frozen-inputs.json", {"files": inputs, "verifier": str(frozen.HERE / "verify_notepad_split.py"),
                     "verifier_sha256": frozen.sha(frozen.HERE / "verify_notepad_split.py"),
                     "dependencies": dependencies})
        frozen.save(root / "preflight.json", {"images": identities, "bundle_identity": bundle,
                    "disk_available": disk.f_bavail * disk.f_frsize, "load1": load, "swap": swap,
                    "daemon_disk": daemon_disk, "source": str(frozen.SOURCE), "commit": frozen.PIN,
                    "tree": frozen.TREE, "selected_test": strength})
        previous = frozen.unrelated()
        frozen.save(root / "unrelated-before.json", previous)
        schedule = [("weak-normal-canary", "weak", "normal")] + [
            (f"{strength}-{phase}", strength, phase) for phase in ("normal", "fault", "recovery")]
        start = time.monotonic()
        for name, chosen, phase in schedule:
            assert time.monotonic() - start < 400
            frozen.run_cell(root, name, chosen, phase, frozen.HERE / "verify_notepad_split.py", inputs, dependencies)
            assert frozen.unrelated() == previous
            assert not frozen.call(["git", "-C", str(frozen.SOURCE), "status", "--porcelain"])
        frozen.save(root / "unrelated-after.json", frozen.unrelated())
        observations = [cell_verifier.validate_cell(root, name) for name, _, _ in schedule]
        for name, chosen, phase in schedule:
            matrix_verifier.verify_environments(root / name, chosen, phase,
                identities[frozen.APP_IMAGE]["Config"]["Env"],
                identities[frozen.TEST_IMAGE]["Config"]["Env"])
        native = [item["native"] for item in observations]
        hits = [item["hits"] for item in observations]
        assert native == ["passed", "passed", "failed" if strength == "strong" else "passed", "passed"]
        assert hits == [0, 0, 1, 0]
        ids = [(root / name / f"{kind}.id").read_text().strip() for name, _, _ in schedule
               for kind in ("app", "test")]
        assert len(set(ids)) == 8
        result = {"status": "DETECTED" if strength == "strong" else "SURVIVED", "selected_test": strength,
                  "cells": observations, "canary": 1, "unique_faults": 1, "model_calls": 0}
        frozen.save(root / "results.json", result)
        frozen.save(root / "artifacts-sha256.json", {str(p.relative_to(root)): frozen.sha(p)
                    for p in sorted(root.rglob("*")) if p.is_file()})
        return result
    except BaseException as error:
        frozen.save(root / "failure.json", {"status": "CANNOT_VERIFY", "type": type(error).__name__,
                    "message": str(error)})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strength", choices=("weak", "strong"), required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("explicit --execute required")
    print(json.dumps(selected(args.output, args.strength)))
