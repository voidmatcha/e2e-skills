#!/usr/bin/env python3
"""Offline guards for the frozen V4 counted-proof triage. Apache-2.0."""

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "v4_get_pilot_v3", ROOT / "scripts/evals/run-generator-v4-get-pilot-v3.py"
)
triage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(triage)


class V4GetTriageTests(unittest.TestCase):
    def archived_source_digest(self):
        original = triage.pilot.engine.tree_digest
        source = ROOT / "skills/playwright-test-generator"

        def digest(path, **kwargs):
            if Path(path) == source:
                return original(triage.SNAPSHOTS["after"])
            return original(path, **kwargs)

        return mock.patch.object(triage.pilot.engine, "tree_digest", side_effect=digest)

    def test_exact_snapshot_scope_and_one_pair(self):
        with self.archived_source_digest():
            digests = triage.snapshot_check()
            self.assertEqual(
                {name for name in digests["before"] if digests["before"][name] != digests["after"][name]},
                {"SKILL.md", "verification-rules.md"},
            )
            self.assertEqual(
                [(row["arm"], row["repetition"]) for row in triage.schedule()],
                [("before", 1), ("after", 1)],
            )

    def test_extra_change_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = {}
            for arm in triage.ARMS:
                staged[arm] = Path(tmp) / arm
                shutil.copytree(triage.SNAPSHOTS[arm], staged[arm])
            with mock.patch.dict(triage.SNAPSHOTS, staged):
                with (staged["after"] / "best-practices.md").open("a") as handle:
                    handle.write("\nchanged\n")
                with self.assertRaisesRegex(ValueError, "beyond SKILL.md and verification-rules.md"):
                    triage.snapshot_check()

    def test_conditional_probe_and_pending_verdict(self):
        value = triage.pilot.read(triage.PROTOCOL)
        self.assertIn("If a V4 temporary verifier is created", value["common_prompt_appendix"])
        self.assertIn("counted request cardinality", value["decision_rule"]["primary"])
        self.assertIn("stop the iteration", value["decision_rule"]["primary"])
        self.assertIn("PROCESS_ADJUDICATION_PENDING", triage.decision.__code__.co_consts)
        self.assertIn("scheduled_calls=2", Path(triage.__file__).read_text())


if __name__ == "__main__":
    unittest.main()
