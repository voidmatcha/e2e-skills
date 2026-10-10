#!/usr/bin/env python3
"""Model-free pilot safety and decision tests. Apache-2.0."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pilot", ROOT / "scripts/evals/run-generator-environment-pilot-v1.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
P = dict(cases=[f"c{i}" for i in range(6)], seed=42, environment_guidance="GUIDANCE {literal}", common_prompt_appendix="COMMON", decision_rule=dict(minimum_paired_median_time_reduction=.25))


def matrix():
    runs, scores = [], []
    for case in P["cases"]:
        for arm in pilot.ARMS:
            row = dict(case=case, arm=arm, repetition=1, call_id=f"{case}-{arm}-r1", spec_files=["tests/new.spec.js"], tests_files=["tests/new.spec.js"], deliverable=True, timeout=False, compliance=None)
            duration = 100 if arm == "current" else 70
            runs.append(dict(row, attempts=[dict(elapsed_ms=duration, usage=dict(input_tokens=12))], structured_output=dict(status="complete")))
            scores.append(dict(row, clean=True, clean_runs=[dict(ok=True)] * 3, refactor_pass=True, refactor_score=1, primary=1., scan=dict(p0=0)))
    return dict(runs=runs), scores


class PilotTests(unittest.TestCase):
    def test_schedule_paired_balanced_and_deterministic(self):
        with patch.object(pilot, "protocol", return_value=P):
            rows = pilot.schedule()
            self.assertEqual(rows, pilot.schedule())
        self.assertEqual(len(rows), 12)
        self.assertEqual([r["ordinal"] for r in rows], list(range(1, 13)))
        self.assertEqual(sum(r["arm"] == "current" for r in rows[::2]), 3)
        for a, b in zip(rows[::2], rows[1::2]):
            self.assertEqual(a["case"], b["case"])
            self.assertNotEqual(a["arm"], b["arm"])

    def test_adapter_maps_both_arms_and_restores_frame_on_failure(self):
        frames = []
        def callback(*args):
            frames.append((args[2], pilot.engine.FRAME.format(task="task")))
            raise ValueError("intentional")
        original = pilot.engine.FRAME
        with patch.object(pilot, "protocol", return_value=P), patch("generator_codex_container_adapter.configure", return_value=callback):
            pilot.install_adapter()
            for arm in pilot.ARMS:
                with self.assertRaises(ValueError):
                    pilot.engine.call_model(None, None, arm, "task", None, None, None)
                self.assertEqual(pilot.engine.FRAME, original)
        self.assertTrue(all(a == "full-fixed" and "COMMON" in frame for a, frame in frames))
        self.assertNotIn("GUIDANCE", frames[0][1])
        self.assertIn("GUIDANCE {literal}", frames[1][1])

    def test_decision_quality_guards_and_unknown_usd(self):
        report, scores = matrix()
        with patch.object(pilot, "protocol", return_value=P):
            result = pilot.decision(report, scores)
            self.assertEqual(result["status"], "PILOT_PROMISING")
            self.assertIsNone(result["billed_usd"])
            self.assertFalse(result["release_equivalence"])
            self.assertIn("UNVERIFIED", result["process_audit"])
            scores[1]["primary"] = .5
            self.assertEqual(pilot.decision(report, scores)["status"], "PILOT_NOT_PROMISING")
            scores[1]["primary"] = 1
            scores[1]["scan"]["p0"] = 1
            self.assertEqual(pilot.decision(report, scores)["status"], "PILOT_NOT_PROMISING")

    def test_all_attempt_durations_not_final_only(self):
        row = dict(attempts=[dict(elapsed_ms=100), dict(elapsed_ms=30)])
        self.assertEqual(pilot.elapsed(row), 130)
        row["attempts"][0]["elapsed_ms"] = float("nan")
        with self.assertRaises(ValueError):
            pilot.elapsed(row)

    def test_invalid_scores_are_refused(self):
        for field, value in (("primary", float("nan")), ("clean", 1), ("scan", None), ("refactor_score", .5), ("call_id", "changed")):
            report, scores = matrix()
            scores[0][field] = value
            with patch.object(pilot, "protocol", return_value=P), self.assertRaises(ValueError):
                pilot.decision(report, scores)

    def test_artifact_paths_and_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "final.json"
            base = path.parent / "final-artifacts/call/tests"
            base.mkdir(parents=True)
            artifact = base / "new.spec.js"
            artifact.write_text("test")
            row = dict(call_id="call", tests_files=["tests/new.spec.js"])
            before = pilot.artifact_hashes(path, row)
            artifact.write_text("changed")
            self.assertNotEqual(before, pilot.artifact_hashes(path, row))
            row["tests_files"] = ["tests/../../escape"]
            with self.assertRaises(ValueError):
                pilot.artifact_hashes(path, row)

    def test_live_requires_explicit_authority(self):
        with self.assertRaises(ValueError):
            pilot.run(SimpleNamespace(allow_live=False))

    def test_matrix_missing_duplicate_and_ordinal_refused(self):
        with patch.object(pilot, "protocol", return_value=P):
            rows = pilot.schedule()
        for actual in (rows[:-1], rows + [rows[0]], [dict(r, ordinal=99) for r in rows]):
            with self.assertRaises(ValueError):
                pilot.check_rows(actual, rows)

    def test_report_binding_attempts_artifacts_and_identity(self):
        with patch.object(pilot, "protocol", return_value=P):
            rows = pilot.schedule()
        p = dict(P, protocol_id="generator-environment-pilot-v1", model="pinned", container_image="image", docker_context="context", reasoning_effort="medium", workers=1)
        report = dict(protocol_id=p["protocol_id"], freeze_sha256="frozen", stage="final", arms=list(pilot.ARMS), model=p["model"], container_image=p["container_image"], docker_context=p["docker_context"], reasoning_effort=p["reasoning_effort"], workers=1, scheduled_calls=12, completed_calls=12, runs=[])
        for row in rows:
            report["runs"].append(dict(row, call_id=f"{row['case']}-{row['arm']}-r1", attempts=[dict(elapsed_ms=100, infrastructure_error=False)], total_attempt_elapsed_ms=100, artifact_sha256={}, tests_files=[], infrastructure_error=False))
        with patch.object(pilot, "protocol", return_value=p), patch.object(pilot, "digest", return_value="frozen"), patch.object(pilot, "artifact_hashes", return_value={}):
            pilot.check_report(report, dict(schedule=rows), Path("unused"))
            report["runs"][0]["total_attempt_elapsed_ms"] = 1
            with self.assertRaises(ValueError):
                pilot.check_report(report, dict(schedule=rows), Path("unused"))
            report["runs"][0]["total_attempt_elapsed_ms"] = 100
            report["runs"][0]["attempts"][0]["infrastructure_error"] = True
            with self.assertRaises(ValueError):
                pilot.check_report(report, dict(schedule=rows), Path("unused"))
            report["runs"][0]["attempts"][0]["infrastructure_error"] = False
            report["model"] = "changed"
            with self.assertRaises(ValueError):
                pilot.check_report(report, dict(schedule=rows), Path("unused"))

    def test_prerequisite_strict_status_image_and_boolean_checks(self):
        probe = pilot.read(pilot.PROBE)
        p = dict(container_image=probe["image"])
        pilot.validate_probe(p)
        for key, value in (("status", "INCONCLUSIVE"), ("image", "other"), ("safe_setup", {})):
            changed = dict(probe, **{key: value})
            with patch.object(pilot, "read", return_value=changed), self.assertRaises(ValueError):
                pilot.validate_probe(p)
        changed = dict(probe, safe_setup=dict(probe["safe_setup"], cli_closed=1))
        with patch.object(pilot, "read", return_value=changed), self.assertRaises(ValueError):
            pilot.validate_probe(p)

    def test_all_failing_or_incomplete_work_is_not_promising(self):
        for guard in ("clean", "timeout", "writes", "completion"):
            report, scores = matrix()
            if guard == "clean":
                for row in scores:
                    row.update(clean=False, clean_runs=[dict(ok=False)] * 3, refactor_pass=False, refactor_score=0)
            elif guard == "timeout":
                report["runs"][1]["timeout"] = scores[1]["timeout"] = True
            elif guard == "writes":
                report["runs"][1]["out_of_scope_writes"] = scores[1]["out_of_scope_writes"] = ["app.mjs"]
            else:
                report["runs"][1]["structured_output"]["status"] = "incomplete"
            with patch.object(pilot, "protocol", return_value=P):
                self.assertEqual(pilot.decision(report, scores)["status"], "PILOT_NOT_PROMISING")


if __name__ == "__main__":
    unittest.main()
