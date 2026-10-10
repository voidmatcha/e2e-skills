#!/usr/bin/env python3
"""Offline guards for the third distinct-case V4 GET screen. Apache-2.0."""

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "v4_get_transfer_v3", ROOT / "scripts/evals/run-generator-v4-get-transfer-v3.py"
)
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)


class V4GetTransferV3Tests(unittest.TestCase):
    def test_distinct_validated_case_and_narrow_skill_contrast(self):
        self.assertEqual(screen.validated_case()["cases"][screen.CASE]["strong_kill_rate"], 1.0)
        digests = screen.snapshot_check()
        self.assertEqual(
            {name for name in digests["before"] if digests["before"][name] != digests["after"][name]},
            {"SKILL.md", "verification-rules.md"},
        )
        self.assertEqual([(row["case"], row["arm"]) for row in screen.schedule()],
                         [(screen.CASE, "before"), (screen.CASE, "after")])

    def test_frozen_scoring_does_not_require_current_product_bytes(self):
        source = screen.ROOT / "skills/playwright-test-generator"
        real = screen.engine.tree_digest

        def changed_current(path, **kwargs):
            if Path(path) == source:
                raise AssertionError("read-only post-run commands touched the mutable product")
            return real(path, **kwargs)

        with mock.patch.object(screen.engine, "tree_digest", side_effect=changed_current):
            screen.protocol()
            screen.bindings()
        with self.assertRaisesRegex(AssertionError, "mutable product"):
            with mock.patch.object(screen.engine, "tree_digest", side_effect=changed_current):
                screen.snapshot_check(require_current=True)

    def test_mutated_case_and_extra_skill_change_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_root = Path(tmp) / "cases"
            shutil.copytree(screen.engine.CASES, case_root)
            with mock.patch.object(screen.engine, "CASES", case_root):
                with (case_root / screen.CASE / "app.mjs").open("a") as handle:
                    handle.write("\nchanged\n")
                with self.assertRaisesRegex(ValueError, "validated case or oracle bytes changed"):
                    screen.validated_case()
            snapshots = {}
            for arm in screen.ARMS:
                snapshots[arm] = Path(tmp) / arm
                shutil.copytree(screen.SNAPSHOTS[arm], snapshots[arm])
            with mock.patch.dict(screen.SNAPSHOTS, snapshots):
                with (snapshots["after"] / "best-practices.md").open("a") as handle:
                    handle.write("\nchanged\n")
                with self.assertRaisesRegex(ValueError, "beyond SKILL.md and verification-rules.md"):
                    screen.snapshot_check()

    def test_manual_verdict_not_inferred_from_model_status(self):
        protocol = screen.pilot.read(screen.PROTOCOL)
        self.assertIn("one request per user click", protocol["decision_rule"]["primary"])
        self.assertIn("unchanged primary assertion", protocol["decision_rule"]["primary"])
        self.assertIn("await the product-recognized failed GET response", protocol["decision_rule"]["primary"])
        self.assertIn("print its complete source", protocol["common_prompt_appendix"])
        self.assertIn("PROCESS_ADJUDICATION_PENDING", screen.triage.decision.__code__.co_consts)


if __name__ == "__main__":
    unittest.main()
