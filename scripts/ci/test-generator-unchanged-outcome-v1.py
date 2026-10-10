#!/usr/bin/env python3
"""Offline targeted remeasurement guards. Apache-2.0."""
import importlib.util
import shutil
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("remeasure", ROOT / "scripts/evals/run-generator-unchanged-outcome-v1.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def matrix():
    runs, scores = [], []
    for item in m.schedule():
        row = dict(item, call_id=f"v3-02-{item['arm']}-r{item['repetition']}", spec_files=["tests/a.spec.mjs"], tests_files=["tests/a.spec.mjs"], deliverable=True, timeout=False, compliance=None, out_of_scope_writes=[])
        killed = item["arm"] == "after"
        runs.append(dict(row, attempts=[dict(elapsed_ms=10)], structured_output=dict(status="partial")))
        faults = {f["id"]: dict(killed=True, failed=1, errors=[]) for f in m.engine.load_truth("v3-02")["faults"]}
        faults["f3-servings-below-one"] = dict(killed=killed, failed=int(killed), errors=[])
        rate = round(sum(f["killed"] for f in faults.values()) / 5, 4)
        scores.append(dict(row, clean=True, clean_runs=[dict(ok=True)] * 3, refactor_pass=True, refactor_score=1, primary=rate, kill_rate=rate, faults=faults, scan=dict(p0=0)))
    return dict(runs=runs), scores


class Tests(unittest.TestCase):
    def test_six_paired_calls_deterministic(self):
        rows = m.schedule()
        self.assertEqual(rows, m.schedule())
        self.assertEqual(len(rows), 6)
        self.assertEqual([r["ordinal"] for r in rows], list(range(1, 7)))
        for a, b in zip(rows[::2], rows[1::2]):
            self.assertEqual(a["repetition"], b["repetition"])
            self.assertNotEqual(a["arm"], b["arm"])

    def test_after_is_only_two_insertions(self):
        # Historical evidence tests use the frozen candidate, not today's skill.
        contents = m.snapshot_bytes()
        m.validate_snapshots(contents)
        contents["SKILL.md"] = b"unrelated"
        with self.assertRaises(ValueError):
            m.validate_snapshots(contents)

    def test_targeted_count_and_no_general_claim(self):
        report, scores = matrix()
        result = m.decision(report, scores)
        self.assertEqual(result["status"], "TARGETED_SIGNAL")
        self.assertEqual(result["f3_killed_calls"], dict(before=0, after=3))
        self.assertFalse(result["release_equivalence"])
        self.assertIsNone(result["billed_usd"])
        self.assertIn("UNVERIFIED", result["process_audit"])
        # Honest partial reports do not suppress measurable fault detection.
        self.assertTrue(all(r["structured_output"]["status"] == "partial" for r in report["runs"]))

    def test_no_signal_on_tie_or_guard_regression(self):
        report, scores = matrix()
        for row in scores:
            row["faults"]["f3-servings-below-one"] = dict(killed=True, failed=1, errors=[])
            row["kill_rate"] = row["primary"] = 1.
        self.assertEqual(m.decision(report, scores)["status"], "NO_TARGETED_SIGNAL")
        report, scores = matrix()
        scores[0]["scan"]["p0"] = 1
        self.assertEqual(m.decision(report, scores)["status"], "NO_TARGETED_SIGNAL")

    def test_missing_or_inconsistent_scores_refused(self):
        report, scores = matrix()
        with self.assertRaises(ValueError):
            m.decision(report, scores[:-1])
        scores[0]["faults"]["f3-servings-below-one"]["killed"] = not scores[0]["faults"]["f3-servings-below-one"]["killed"]
        with self.assertRaises(ValueError):
            m.decision(report, scores)

    def test_adapter_same_prompt_different_snapshot_restores(self):
        observed = []
        def callback(*args):
            observed.append((m.engine.FRAME, m.engine.tree_digest(m.engine.ARM_SKILL["full-fixed"])))
            raise ValueError("mock")
        original = m.engine.FRAME
        with patch("generator_codex_container_adapter.configure", return_value=callback), patch.object(m, "snapshot_bytes", return_value={"SKILL.md": b"after"}):
            m.install_adapter()
            for arm in m.ARMS:
                with self.assertRaises(ValueError):
                    m.engine.call_model(None, None, arm, "task", None, None, None)
        self.assertEqual(observed[0][0], observed[1][0])
        self.assertEqual(observed[0][1], m.engine.tree_digest(m.BEFORE))
        self.assertEqual(observed[1][1], {"SKILL.md": m.engine.sha(b"after")})
        self.assertEqual(m.engine.FRAME, original)
        self.assertEqual(m.engine.ARM_SKILL["full-fixed"], m.BEFORE)

    def test_after_staging_preserves_executable_modes(self):
        name = "scripts/run-preflight-target.sh"
        original = (m.BEFORE / name).stat().st_mode & 0o777
        seen = []
        def callback(*args):
            seen.append((m.engine.ARM_SKILL["full-fixed"] / name).stat().st_mode & 0o777)
            return {}
        with patch("generator_codex_container_adapter.configure", return_value=callback), patch.object(m, "snapshot_bytes", return_value={name: (m.BEFORE / name).read_bytes()}):
            m.install_adapter()
            m.engine.call_model(None, None, "after", "task", None, None, None)
        self.assertEqual(seen, [original])
        self.assertNotEqual(original & 0o111, 0)

    def test_infrastructure_gets_no_second_model_attempt(self):
        args = SimpleNamespace(model="mock", timeout=1, call_budget=None)
        result = dict(infrastructure_error=True, elapsed_ms=1)
        with tempfile.TemporaryDirectory() as directory, patch.object(m.engine, "wait_for_load"), patch.object(m.engine, "stage", return_value=Path(directory)), patch.object(m.engine, "call_model", return_value=result) as call, patch.object(m.engine, "collect_deliverable", return_value=dict(spec_files=[], tests_files=[])):
            row = m.one_call(m.schedule()[0], args, SimpleNamespace(take=lambda: 1), Path(directory))
        self.assertEqual(call.call_count, 1)
        self.assertEqual(len(row["attempts"]), 1)
        self.assertTrue(row["infrastructure_error"])

    def test_attempt_ledger_prevents_unreported_retry(self):
        args = SimpleNamespace(model="mock", timeout=1, call_budget=None)
        with tempfile.TemporaryDirectory() as directory:
            args.attempt_dir = Path(directory)
            lock = args.attempt_dir / "freeze.json"
            lock.write_text("{}")
            item = m.schedule()[0]
            ledger = args.attempt_dir / f"v3-02-{item['arm']}-r{item['repetition']}.json"
            with patch.object(m, "LOCK", lock), patch.object(m.engine, "wait_for_load"), patch.object(m.engine, "call_model") as call, patch.object(m.engine, "stage", side_effect=RuntimeError("interruption before call")):
                with self.assertRaises(RuntimeError):
                    m.one_call(item, args, SimpleNamespace(take=lambda: 1), args.attempt_dir)
                self.assertTrue(ledger.is_file())
                with self.assertRaises(FileExistsError):
                    m.one_call(item, args, SimpleNamespace(take=lambda: 1), args.attempt_dir)
                call.assert_not_called()

    def test_live_requires_explicit_flag(self):
        with self.assertRaises(ValueError):
            m.run(SimpleNamespace(allow_live=False))

    def test_score_retains_raw_report_without_changing_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            report = base / "final.json"
            report.write_text("{}")
            lock = base / "freeze.json"
            lock.write_text("{}")
            args = SimpleNamespace(report=report, output=base / "scores.json", resume=False)
            observed = []
            def scorer(arguments):
                result = m.engine.run_playwright(base, ["tests/a.spec.mjs"])
                observed.append(result)
                m.engine.write_json(arguments.output, dict(result=result))
            raw = json.dumps(dict(stats=dict(expected=1, unexpected=0, flaky=0, skipped=0), errors=[]))
            with patch.object(m, "LOCK", lock), patch.object(m, "frozen", return_value={}), patch.object(m, "check_report"), patch.object(m.engine, "cmd_score", side_effect=scorer), patch.object(m.subprocess, "run", return_value=SimpleNamespace(stdout=raw, stderr="diagnostic", returncode=0)), patch.object(m.shutil, "disk_usage", return_value=SimpleNamespace(free=10**12)):
                m.score(args)
            self.assertTrue(observed[0]["ok"])
            self.assertEqual(observed[0]["passed"], 1)
            evidence = observed[0]["raw_playwright"]
            path = base / evidence["path"]
            self.assertEqual(m.digest(path), evidence["sha256"])
            self.assertEqual(m.read(path)["stdout"], raw)
            self.assertEqual(m.read(path)["stderr"], "diagnostic")

    def test_scoring_floor_blocks_browser_call(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            report, lock = base / "final.json", base / "freeze.json"
            report.write_text("{}")
            lock.write_text("{}")
            args = SimpleNamespace(report=report, output=base / "scores.json", resume=False)
            def scorer(arguments):
                m.engine.run_playwright(base, ["tests/a.spec.mjs"])
            with patch.object(m, "LOCK", lock), patch.object(m, "frozen", return_value={}), patch.object(m, "check_report"), patch.object(m.engine, "cmd_score", side_effect=scorer), patch.object(m.subprocess, "run") as process, patch.object(m.shutil, "disk_usage", return_value=SimpleNamespace(free=1)):
                with self.assertRaises(ValueError):
                    m.score(args)
            process.assert_not_called()

    def test_analyzer_binds_original_report_and_all_raws(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            report, rows = matrix()
            report_path, score_path, lock = base / "final.json", base / "scores.json", base / "freeze.json"
            report_path.write_text(json.dumps(report))
            lock.write_text("{}")
            manifest = {}
            counter = 0
            for row in rows:
                row["refactor"] = dict(ok=True)
                for run in [*row["clean_runs"], *row["faults"].values(), row["refactor"]]:
                    counter += 1
                    name = f"raw-{counter:04d}.json"
                    (base / name).write_text(json.dumps(dict(ordinal=counter)))
                    manifest[name] = m.digest(base / name)
                    run["raw_playwright"] = dict(path=name, sha256=manifest[name])
            # clean_runs fixtures intentionally reuse dictionaries, yet every raw
            # payload still stays bound in the complete manifest.
            p = m.protocol()
            data = dict(protocol_id=p["protocol_id"], stage="final", report="final.json", report_sha256=m.digest(report_path), freeze_sha256=m.digest(lock), scores=rows, raw_playwright_manifest=manifest)
            score_path.write_text(json.dumps(data))
            args = SimpleNamespace(scores=score_path, output=base / "results.json")
            with patch.object(m, "LOCK", lock), patch.object(m, "frozen", return_value=dict(schedule=m.schedule())), patch.object(m, "check_report"):
                m.analyze(args)
                self.assertEqual(m.read(args.output)["report_sha256"], m.digest(report_path))
                self.assertEqual(m.read(args.output)["freeze_sha256"], m.digest(lock))
                (base / "raw-0001.json").write_text("tampered")
                args.output = base / "tampered-result.json"
                with self.assertRaises(ValueError):
                    m.analyze(args)


if __name__ == "__main__":
    unittest.main()
