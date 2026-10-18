#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Adapter boundary tests; no Docker, model, or browser execution."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ADAPTER_PATH = Path(__file__).with_name("passport_adapter_v1.py")
SPEC = importlib.util.spec_from_file_location("passport_adapter_v1", ADAPTER_PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


class PassportAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name).resolve() / "fresh"
        self.calls = []

    def fake_launch(self, output, selector, phase, verify_only=False):
        self.calls.append((phase, verify_only))
        if verify_only:
            return
        root = output / adapter._cell_name(selector, phase)
        root.mkdir()
        index = adapter.PHASES.index(phase) * 4
        for number, name in enumerate(("seed", "app", "network-probe", "browser")):
            (root / f"{name}.id").write_text(f"{index + number:064x}")
        (root / "native-report.json").write_text('{"test":"fixed"}')

    def run_mocked(self, selector):
        with patch.object(adapter, "_check_pins"), patch.object(adapter, "_launch", self.fake_launch):
            return adapter.run(self.output, selector)

    def test_weak_three_phases_and_fresh_replay(self):
        result = self.run_mocked("weak")
        self.assertEqual(result["verdict"], "SURVIVED")
        self.assertEqual(self.calls, [(phase, False) for phase in adapter.PHASES]
                         + [(phase, True) for phase in adapter.PHASES])
        self.assertEqual(len(result["cells"]), 3)
        self.assertEqual(json.loads((self.output / "adapter-result.json").read_text()), result)
        self.assertIn("passport-weak-split-fault-v1-home/native-report.json", result["evidence"]["sha256"])

    def test_strong_three_phases_detected(self):
        self.assertEqual(self.run_mocked("strong")["verdict"], "DETECTED")

    def test_setup_failure_never_becomes_survived(self):
        with patch.object(adapter, "_check_pins"), patch.object(adapter, "_launch", side_effect=RuntimeError("startup")), patch.object(adapter, "_stop_owned") as stop:
            result = adapter.run(self.output, "weak")
        self.assertEqual(result["verdict"], "CANNOT_VERIFY")
        self.assertEqual(result["cells"], [])
        stop.assert_called_once_with(self.output, "weak")

    def test_late_replay_failure_invalidates_earlier_admission(self):
        def launch(output, selector, phase, verify_only=False):
            if verify_only:
                raise RuntimeError("earlier evidence changed")
            self.fake_launch(output, selector, phase)
        with patch.object(adapter, "_check_pins"), patch.object(adapter, "_launch", launch), patch.object(adapter, "_stop_owned"):
            result = adapter.run(self.output, "strong")
        self.assertEqual(result["verdict"], "CANNOT_VERIFY")

    def test_container_reuse_is_not_a_valid_matrix(self):
        def launch(output, selector, phase, verify_only=False):
            self.fake_launch(output, selector, phase, verify_only)
            if not verify_only:
                (output / adapter._cell_name(selector, phase) / "seed.id").write_text("0" * 64)
        with patch.object(adapter, "_check_pins"), patch.object(adapter, "_launch", launch), patch.object(adapter, "_stop_owned"):
            result = adapter.run(self.output, "weak")
        self.assertEqual(result["verdict"], "CANNOT_VERIFY")
        self.assertIn("reuse", result["reason"])

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "keep"
        sentinel.write_text("existing")
        with patch.object(adapter, "_launch") as launch, self.assertRaises(FileExistsError):
            adapter.run(self.output, "weak")
        launch.assert_not_called()
        self.assertEqual(sentinel.read_text(), "existing")

    def test_unknown_selector_never_launches(self):
        with patch.object(adapter, "_launch") as launch, self.assertRaises(ValueError):
            adapter.run(self.output, "weak; arbitrary command")
        launch.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_repository_output_is_rejected(self):
        with patch.object(adapter, "_launch") as launch, self.assertRaises(ValueError):
            adapter.run(adapter.HERE / "new-adapter-test-must-not-exist", "weak")
        launch.assert_not_called()

    def test_current_input_drift_stops_before_runner(self):
        source = Path(self.temp.name).resolve()
        baseline = source / adapter._cell_name("weak", "normal")
        baseline.mkdir()
        (baseline / "input-hashes.json").write_text('{}')
        runner = SimpleNamespace(SOURCE_CELL=source, DEPENDENCIES=source,
                                 CACHE=source, ADAPTER=source,
                                 digest_tree=lambda path: {"sha256": "changed"})
        with patch.object(adapter, "HERE", source), patch.object(adapter, "_check_pins"), patch.object(adapter, "_modules", return_value=(runner, None)), self.assertRaisesRegex(RuntimeError, "input drift"):
            adapter._worker(self.output, "weak", "normal", False)

    def test_descriptor_cannot_change_registry(self):
        first = adapter.descriptor()
        first["runner_verifier_sha256"].clear()
        first["source_sha256"].clear()
        first["test_selectors"].append("extra")
        self.assertEqual(len(adapter.descriptor()["runner_verifier_sha256"]), 6)
        self.assertEqual(len(adapter.descriptor()["source_sha256"]), 3)
        self.assertEqual(adapter.TEST_SELECTORS, ("weak", "strong"))

    def test_pin_failure_stops_before_launch(self):
        with patch.object(adapter, "_check_pins", side_effect=RuntimeError("pin drift")), patch.object(adapter, "_launch") as launch, patch.object(adapter, "_stop_owned"):
            result = adapter.run(self.output, "strong")
        launch.assert_not_called()
        self.assertEqual(result["verdict"], "CANNOT_VERIFY")


if __name__ == "__main__":
    unittest.main()
