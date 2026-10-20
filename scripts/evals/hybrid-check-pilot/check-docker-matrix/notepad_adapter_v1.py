#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fixed Anonymous Notepad Playwright transfer, using frozen split-container runner."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
ADAPTER_ID = "notepad-playwright-v1"
PROMISE_ID = "note-content-persists-after-save"
PROMISE_TEXT = "View/Edit the note without any sign-in or sign-up"
TEST_SELECTORS = ("weak", "strong")
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
RUNNER = HERE / "run_notepad_selected_v1.py"
FROZEN_RUNNER = HERE / "run_notepad_split.py"
CELL_VERIFIER = HERE / "verify_notepad_split.py"
MATRIX_VERIFIER = HERE / "verify_notepad_split_matrix.py"
PROTOCOL = HERE / "NOTEPAD-SPLIT-PROTOCOL.md"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def descriptor() -> dict:
    return {
        "adapter": ADAPTER_ID,
        "promise_id": PROMISE_ID,
        "framework": "Playwright",
        "source_commit": "135e18dde6ac1acae195bb74dfaee49a0fbf33f6",
        "app_image": "sha256:a10a311fdac6a850603a4092842198356702ce77117569670dffe9f04ec8fd12",
        "test_image": "sha256:687b18c424d01c3af69efa921eaa824b48eb737d46492da334405e348da73881",
        "allowed_tests": list(TEST_SELECTORS),
        "schedule": ["weak-normal-canary", "<selected>-normal", "<selected>-fault", "<selected>-recovery"],
        "argv": [sys.executable, str(RUNNER), "--output", "<fresh-output>", "--strength", "<exact-selector>", "--execute"],
        "host_environment": {"HOME": str(Path.home()), "PATH": PATH, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
        "files_sha256": {p.name: digest(p) for p in (RUNNER, FROZEN_RUNNER, CELL_VERIFIER, MATRIX_VERIFIER, PROTOCOL,
            HERE / "notepad.spec.cjs", HERE / "notepad.config.cjs", HERE / "notepad-serve.cjs")},
        "execution": "fresh disposable app/test containers; pinned images; --pull=never; no install; retries=0; no model",
    }


def run(output_dir: Path, test_selector: str) -> dict:
    output_dir = Path(output_dir).absolute()
    if (test_selector not in TEST_SELECTORS or output_dir.exists() or output_dir.is_relative_to(REPO)
            or not output_dir.parent.is_dir() or output_dir.parent.resolve() != output_dir.parent):
        return {"status": "CANNOT_VERIFY", "reason": "invalid selector or nonfresh external output"}
    command = [sys.executable, str(RUNNER), "--output", str(output_dir),
               "--strength", test_selector, "--execute"]
    environment = descriptor()["host_environment"]
    try:
        executed = subprocess.run(command, capture_output=True, text=True, timeout=900, cwd=HERE, env=environment)
        if executed.returncode:
            return {"status": "CANNOT_VERIFY", "reason": "frozen runner failed", "exit": executed.returncode,
                    "stderr_tail": executed.stderr[-1500:], "artifacts": str(output_dir)}
        proof = json.loads((output_dir / "results.json").read_text())
        verdict = proof["status"]
        manifest = json.loads((output_dir / "artifacts-sha256.json").read_text())
        observed = {str(path.relative_to(output_dir)): digest(path) for path in output_dir.rglob("*")
                    if path.is_file() and path.name != "artifacts-sha256.json"}
        if (manifest != observed or proof.get("selected_test") != test_selector
                or proof.get("canary") != 1 or proof.get("unique_faults") != 1
                or len(proof.get("cells", [])) != 4
                or verdict != ("DETECTED" if test_selector == "strong" else "SURVIVED")):
            raise ValueError("selected matrix proof invalid")
        return {"status": verdict, "adapter": ADAPTER_ID, "test": test_selector,
                "native_assertion": "note-content-persisted-after-reload" if test_selector == "strong" else "editor-echo",
                "fault_hit": 1, "proof": proof, "artifacts": str(output_dir)}
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, json.JSONDecodeError) as error:
        return {"status": "CANNOT_VERIFY", "reason": str(error), "artifacts": str(output_dir)}
