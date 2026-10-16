#!/usr/bin/env python3
"""Offline guards for the official+reviewer pilot: schedule, staging prompt, freeze binding, drift refusal. Apache-2.0."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("revpilot", ROOT / "scripts/evals/run-generator-official-reviewer-pilot-v1.py")
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)
HAVE_SOURCE = (rp.SOURCE_DIR / "final.json").is_file() and (rp.SOURCE_DIR / "final-artifacts").is_dir()


class Contract(unittest.TestCase):
    def test_protocol_matches_original_pilot_environment(self):
        p, base = rp.protocol(), rp.orig.protocol()
        for key in ("tasks", "model", "reasoning_effort", "timeout_s", "container_image", "docker_context", "load"):
            self.assertEqual(p[key], base[key])
        self.assertEqual(p["status"], "NOT_RUN")
        self.assertEqual(p["arms"], ["official+reviewer"])
        self.assertEqual(p["compared_arms"], ["official-generator", "official+reviewer", "ours-2.0.1"])

    def test_schedule_is_12_unique_b_cells_two_per_task(self):
        rows = rp.schedule()
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({rp.identity(r) for r in rows}), 12)
        self.assertEqual({r["arm"] for r in rows}, {"official+reviewer"})
        for task in rp.protocol()["tasks"]:
            self.assertEqual(sorted(r["repetition"] for r in rows if r["case"] == task), [1, 2])
        self.assertEqual(rows, rp.schedule())

    def test_prompt_is_review_and_fix_without_weakening_and_scoped_to_tests(self):
        line = rp.REVIEW_LINE
        for needle in ("e2e-reviewer", "/work/skill/e2e-reviewer/SKILL.md", "scan.sh", "FIX every finding", "P0",
                       "do not weaken assertions", "add no scenarios", "app.mjs", "outside `tests/`"):
            self.assertIn(needle, line)
        self.assertNotIn("playwright-test-generator", line + rp.TASK_LINE)
        self.assertIn("review-and-fix", rp.TASK_LINE)

    def test_arm_b_is_staged_from_saved_official_specs_only(self):
        self.assertTrue(rp.ARM_A != rp.ARM and rp.ARM_C != rp.ARM)
        item = rp.schedule()[0]
        self.assertEqual(rp.source_call_id(item), f"{item['case']}-official-generator-r{item['repetition']}")
        self.assertTrue(str(rp.source_artifacts(item)).startswith(str(rp.SOURCE_DIR)))

    def test_reviewer_skill_is_the_pinned_2_0_1_tree(self):
        original = rp.read(rp.orig.LOCK)["bindings"]["ours_skills_tree"]
        import hashlib, json
        tree = json.dumps(rp.orig.skills_digest(), sort_keys=True)
        self.assertEqual(hashlib.sha256(tree.encode()).hexdigest(), original)

    @unittest.skipUnless(HAVE_SOURCE, "saved offgen-pilot-v1 outputs not present")
    def test_saved_official_deliverables_exist_for_every_cell(self):
        for item in rp.schedule():
            files = list((rp.source_artifacts(item) / "tests").rglob("*.ts")) + list((rp.source_artifacts(item) / "tests").rglob("*.mjs"))
            self.assertTrue(files, rp.source_call_id(item))

    @unittest.skipUnless(HAVE_SOURCE, "saved offgen-pilot-v1 outputs not present")
    def test_freeze_binds_current_files_and_saved_evidence(self):
        lock = rp.read(rp.LOCK)
        self.assertEqual(lock["bindings"], rp.bindings())
        self.assertEqual(lock["schedule"], rp.schedule())
        self.assertEqual(len(lock["bindings"]["source_evidence"]["artifacts"]), 12)

    def test_foreign_duplicate_and_missing_cells_refused(self):
        rows = rp.schedule()
        for changed in (rows[:-1] + [rows[0]], [dict(rows[0], case="foreign")] + rows[1:], rows[:-1]):
            with self.assertRaises(ValueError):
                rp.orig.check_rows(changed, rows)

    def test_drift_and_live_flag_refused(self):
        with patch.object(rp, "bindings", return_value={"changed": True}), patch.object(rp.orig, "frozen", return_value={}):
            with self.assertRaisesRegex(ValueError, "drift"):
                rp.frozen()
        with self.assertRaisesRegex(ValueError, "allow-live"):
            rp.run(type("A", (), {"allow_live": False})())

    def test_outputs_must_leave_checkout(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            rp.orig.output_guard(ROOT / "x.json")

    def test_suggestive_rule_needs_five_of_six_and_guards(self):
        arms = (rp.ARM_A, rp.ARM, rp.ARM_C)
        def entry(rs):
            return {"refactor_survival": rs, "clean_cells": 2, "effective_fault_kill": 1.0, "scan_p0": 0, "scan_p1p2": 0}
        def summary(**over):
            base = {"clean_all_three": 1.0, "effective_fault_kill": 1.0, "scan_p0_total": 0, "scan_p1p2_total": 0}
            return {a: dict(base, **over.get(a, {})) for a in arms}
        tasks = [f"t{i}" for i in range(6)]
        win = {t: {rp.ARM: entry(1.0), rp.ARM_A: entry(0.5 if i < 5 else 1.0), rp.ARM_C: entry(1.0)} for i, t in enumerate(tasks)}
        self.assertTrue(rp.suggestive(win, summary(), rp.ARM, rp.ARM_A)["label"].startswith("suggestive"))
        self.assertTrue(rp.suggestive(win, summary(**{rp.ARM: {"scan_p1p2_total": 3}}), rp.ARM, rp.ARM_A)["label"].startswith("nothing"))
        split = {t: {rp.ARM: entry(1.0 if i < 3 else 0.0), rp.ARM_A: entry(0.5), rp.ARM_C: entry(0.5)} for i, t in enumerate(tasks)}
        self.assertTrue(rp.suggestive(split, summary(), rp.ARM, rp.ARM_A)["label"].startswith("nothing"))


if __name__ == "__main__":
    unittest.main()
