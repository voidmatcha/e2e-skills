#!/usr/bin/env python3
"""Offline full-pool, drift and exact-matrix guards. Apache-2.0."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("v8", ROOT / "scripts/evals/run-generator-skill-effect-v8.py")
v8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v8)


class Contract(unittest.TestCase):
    def test_full_pool_keeps_floor_and_ceiling(self):
        rows = v8.schedule()
        self.assertEqual(len(rows), 216)
        self.assertEqual(len({v8.identity(row) for row in rows}), 216)
        self.assertEqual(rows, v8.schedule())
        historical = v8.read(v8.SOURCE / "protocol.json")["screening"]["mean_no_skill_refactor_score"]
        self.assertEqual(sum(value == 0 for value in historical.values()), 18)
        self.assertEqual({row["case"] for row in rows}, set(historical))
        self.assertEqual({row["arm"] for row in rows}, set(v8.ARMS))

    def test_source_drift_and_partial_validation_refused(self):
        current = v8.engine.input_digests()
        with patch.object(v8.engine, "input_digests", return_value={**current, "tools": "changed"}):
            with self.assertRaisesRegex(ValueError, "source inputs"):
                v8.validate_source()

    def test_duplicate_missing_foreign_and_ordinal_cells_refused(self):
        rows = v8.schedule()
        mutations = [rows[:-1], rows[:-1] + [rows[0]],
                     [dict(rows[0], case="foreign")] + rows[1:],
                     [dict(rows[0], ordinal=999)] + rows[1:]]
        for changed in mutations:
            with self.subTest(changed=changed[0]):
                with self.assertRaises(ValueError):
                    v8.check_rows(changed, rows)

    def test_protocol_and_runner_binding_drift_refused(self):
        lock = {"bindings": v8.bindings(), "schedule": v8.schedule()}
        with patch.object(v8, "read", return_value=lock):
            with patch.object(v8, "bindings", return_value={"changed": True}):
                with self.assertRaisesRegex(ValueError, "drift"):
                    v8.frozen()

    def test_live_run_requires_explicit_flag_before_model(self):
        with patch.object(v8.engine, "one_call") as call:
            with self.assertRaisesRegex(ValueError, "allow-live"):
                v8.run(type("Args", (), {"allow_live": False})())
            call.assert_not_called()

    def test_outputs_cannot_overwrite_checkout(self):
        for target in (v8.PROTOCOL, ROOT / "new-report.json"):
            with self.assertRaisesRegex(ValueError, "outside"):
                v8.output_guard(target)

    def test_duplicate_json_keys_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"a": 1, "a": 2}')
            with self.assertRaisesRegex(ValueError, "duplicate"):
                v8.read(path)

    def test_large_lift_and_null_comparison_are_distinct(self):
        rows = v8.schedule()
        per = {}
        for row in rows:
            per.setdefault(row["case"], {}).setdefault(row["arm"], []).append(
                {"refactor_score": int(row["arm"] == "full-fixed")})
        comparison = v8.engine.paired(per, "refactor_score", *v8.ARMS,
                                      v8.protocol()["decision_rule"], 123)
        self.assertEqual(comparison["paired_cases"], 36)
        self.assertTrue(all(comparison["checks"].values()))
        for arms in per.values():
            for score in arms["full-fixed"]:
                score["refactor_score"] = 0
        null = v8.engine.paired(per, "refactor_score", *v8.ARMS,
                               v8.protocol()["decision_rule"], 123)
        self.assertFalse(null["checks"]["ci_lower_above_zero"])


if __name__ == "__main__":
    unittest.main()
