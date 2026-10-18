#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Internal fixed Notepad pilot with strict native admission before verdict export.

The legacy runner/verifiers and their frozen inputs remain unchanged. This
revision adds reporter consistency admission, not arbitrary-test authentication.
"""
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
LEGACY_PATH = HERE.parent / "check-docker-matrix/notepad_adapter_v1.py"
STRICT_PATH = HERE / "verify_notepad_v2.py"


def load_fixed(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("fixed admission dependency unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LEGACY = load_fixed("notepad_check_legacy_v1", LEGACY_PATH)
STRICT = load_fixed("notepad_check_strict_v2", STRICT_PATH)
ADAPTER_ID = "notepad-playwright-v2"
PROMISE_ID = LEGACY.PROMISE_ID
PROMISE_TEXT = LEGACY.PROMISE_TEXT
TEST_SELECTORS = LEGACY.TEST_SELECTORS


def descriptor():
    definition = LEGACY.descriptor()
    definition["adapter"] = ADAPTER_ID
    definition["files_sha256"].update({
        LEGACY_PATH.name: LEGACY.digest(LEGACY_PATH),
        STRICT_PATH.name: LEGACY.digest(STRICT_PATH),
    })
    definition["native_admission"] = "strict v2 summaries, counters, expected status, attempt and error consistency on all four cells before verdict export"
    definition["scope"] = "internal fixed-input trusted-checkout pilot; public arbitrary-test execution remains NO-GO"
    return definition


def admit_selected(output_dir, test_selector):
    """Read-only re-admission of a completed selected runner's retained outputs."""
    if test_selector not in TEST_SELECTORS:
        raise ValueError("test selector is not registered")
    root = Path(output_dir)
    proof = json.loads((root / "results.json").read_text())
    manifest = json.loads((root / "artifacts-sha256.json").read_text())
    observed = {str(path.relative_to(root)): LEGACY.digest(path) for path in root.rglob("*")
                if path.is_file() and path.name != "artifacts-sha256.json"}
    if manifest != observed:
        raise ValueError("selected matrix artifact digest mismatch")
    names = ["weak-normal-canary"] + [f"{test_selector}-{phase}" for phase in ("normal", "fault", "recovery")]
    # Apply strict native checks before reading the summary's status as a verdict.
    cells = [STRICT.validate_cell(root, name) for name in names]
    expected = "DETECTED" if test_selector == "strong" else "SURVIVED"
    if (proof.get("selected_test") != test_selector or proof.get("canary") != 1
            or proof.get("unique_faults") != 1 or proof.get("cells") != cells
            or proof.get("status") != expected):
        raise ValueError("strict selected matrix proof mismatch")
    return {"status": expected, "adapter": ADAPTER_ID, "test": test_selector,
            "native_assertion": "note-content-persisted-after-reload" if test_selector == "strong" else "editor-echo",
            "fault_hit": 1, "proof": proof, "artifacts": str(root),
            "native_consistency": {"version": 2, "validated_cells": len(cells),
                                   "verifier_sha256": LEGACY.digest(STRICT_PATH)}}


def run(output_dir, test_selector):
    try:
        legacy = LEGACY.run(output_dir, test_selector)
        if legacy.get("status") == "CANNOT_VERIFY":
            return {**legacy, "adapter": ADAPTER_ID}
        return admit_selected(output_dir, test_selector)
    except (OSError, ValueError, RuntimeError, AssertionError, KeyError, IndexError, TypeError,
            subprocess.SubprocessError) as error:
        return {"status": "CANNOT_VERIFY", "adapter": ADAPTER_ID,
                "reason": str(error), "artifacts": str(output_dir)}
