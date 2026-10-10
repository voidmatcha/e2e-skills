#!/usr/bin/env python3
"""Offline guards for the V4 GET development pilot. Apache-2.0."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "v4_get_pilot", ROOT / "scripts/evals/run-generator-v4-get-pilot-v1.py"
)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class V4GetPilotTests(unittest.TestCase):
    def test_exact_snapshot_contrast_and_schedule(self):
        digests = {
            arm: pilot.pilot.engine.tree_digest(path)
            for arm, path in pilot.SNAPSHOTS.items()
        }
        self.assertEqual(set(digests), {"before", "after"})
        self.assertEqual(set(digests["before"]), set(digests["after"]))
        self.assertEqual(
            {name for name in digests["before"] if digests["before"][name] != digests["after"][name]},
            {"SKILL.md"},
        )
        self.assertEqual(
            (pilot.SNAPSHOTS["after"] / "SKILL.md").read_text().replace(pilot.V4_LINE, ""),
            (pilot.SNAPSHOTS["before"] / "SKILL.md").read_text(),
        )
        with mock.patch.object(pilot.overlap, "protocol", return_value=pilot.pilot.read(pilot.PROTOCOL)):
            self.assertEqual(
                [(row["arm"], row["repetition"]) for row in pilot.overlap.schedule()],
                [("before", 1), ("after", 1), ("after", 2),
                 ("before", 2), ("before", 3), ("after", 3)],
            )

    def test_extra_before_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = {}
            for arm in pilot.ARMS:
                staged[arm] = Path(tmp) / arm
                shutil.copytree(pilot.SNAPSHOTS[arm], staged[arm])
            with mock.patch.dict(pilot.SNAPSHOTS, staged):
                with (staged["before"] / "best-practices.md").open("a") as handle:
                    handle.write("\nchanged\n")
                with self.assertRaisesRegex(ValueError, "beyond SKILL.md"):
                    pilot.snapshot_check()

    def test_positive_verdict_requires_manual_process_audit(self):
        protocol = pilot.pilot.read(pilot.PROTOCOL)
        self.assertIn("Independently adjudicated V4 evidence", protocol["decision_rule"]["primary"])
        self.assertIn("not award PASS", protocol["process_audit"])
        self.assertIn('status="PROCESS_ADJUDICATION_PENDING"',
                      (ROOT / "scripts/evals/run-generator-v4-get-pilot-v1.py").read_text())


if __name__ == "__main__":
    unittest.main()
