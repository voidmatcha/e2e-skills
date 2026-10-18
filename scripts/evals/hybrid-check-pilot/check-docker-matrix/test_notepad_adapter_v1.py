#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""No-browser contract checks for the registered Notepad adapter."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


FILE = Path(__file__).with_name("notepad_adapter_v1.py")
SPEC = importlib.util.spec_from_file_location("notepad_adapter", FILE)
assert SPEC and SPEC.loader
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


class AdapterTest(unittest.TestCase):
    def test_descriptor_is_fixed(self):
        data = ADAPTER.descriptor()
        self.assertEqual(data["allowed_tests"], ["weak", "strong"])
        self.assertEqual(data["schedule"], ["weak-normal-canary", "<selected>-normal",
                                            "<selected>-fault", "<selected>-recovery"])
        self.assertIn("--pull=never", data["execution"])

    def test_invalid_test_and_existing_output_do_not_run(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = str(Path(temp).resolve())
            with patch.object(ADAPTER.subprocess, "run") as run:
                self.assertEqual(ADAPTER.run(Path(temp) / "new", "other")["status"], "CANNOT_VERIFY")
                self.assertEqual(ADAPTER.run(Path(temp), "strong")["status"], "CANNOT_VERIFY")
                run.assert_not_called()

    def test_runner_failure_cannot_verify(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = str(Path(temp).resolve())
            bad = subprocess.CompletedProcess([], 1, "", "mismatch")
            with patch.object(ADAPTER.subprocess, "run", return_value=bad) as run:
                self.assertEqual(ADAPTER.run(Path(temp) / "new2", "weak")["status"], "CANNOT_VERIFY")
                self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
