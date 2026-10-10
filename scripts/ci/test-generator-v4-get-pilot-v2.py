#!/usr/bin/env python3
"""Offline guards for the frozen V4 GET successor. Apache-2.0."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "v4_get_pilot_v2", ROOT / "scripts/evals/run-generator-v4-get-pilot-v2.py"
)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


class V4GetSuccessorTests(unittest.TestCase):
    def frozen_snapshot_check(self):
        original = pilot.pilot.engine.tree_digest
        source = ROOT / "skills/playwright-test-generator"

        def archival_digest(path, **kwargs):
            if Path(path) == source:
                return original(pilot.SNAPSHOTS["after"])
            return original(path, **kwargs)

        return mock.patch.object(pilot.pilot.engine, "tree_digest", side_effect=archival_digest)

    def test_exact_skill_contrast_and_schedule(self):
        with self.frozen_snapshot_check():
            digests = pilot.snapshot_check()
        self.assertEqual(set(digests), {"before", "after"})
        self.assertEqual(
            {name for name in digests["before"] if digests["before"][name] != digests["after"][name]},
            {"SKILL.md", "scenario-design.md"},
        )
        with mock.patch.object(pilot.overlap, "protocol", return_value=pilot.pilot.read(pilot.PROTOCOL)):
            self.assertEqual(
                [(row["arm"], row["repetition"]) for row in pilot.overlap.schedule()],
                [("before", 1), ("after", 1), ("after", 2),
                 ("before", 2), ("before", 3), ("after", 3)],
            )

    def test_extra_change_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = {}
            for arm in pilot.ARMS:
                staged[arm] = Path(tmp) / arm
                shutil.copytree(pilot.SNAPSHOTS[arm], staged[arm])
            with mock.patch.dict(pilot.SNAPSHOTS, staged):
                with (staged["before"] / "best-practices.md").open("a") as handle:
                    handle.write("\nchanged\n")
                with self.assertRaisesRegex(ValueError, "beyond SKILL.md and scenario-design.md"):
                    pilot.snapshot_check()

    def test_conditional_evidence_and_pending_decision(self):
        value = pilot.pilot.read(pilot.PROTOCOL)
        self.assertIn("If a V4 temporary verifier is created", value["common_prompt_appendix"])
        self.assertIn("print its complete source with a read-only command", value["common_prompt_appendix"])
        self.assertIn("not a probe", value["decision_rule"]["primary"])
        self.assertIn("PROCESS_ADJUDICATION_PENDING", pilot.PARENT.read_text())


if __name__ == "__main__":
    unittest.main()
