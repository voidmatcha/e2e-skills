#!/usr/bin/env python3
"""Offline contracts for the focused overlap V1 pilot. Apache-2.0."""
import importlib.util
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "overlap_pilot", ROOT / "scripts/evals/run-generator-overlap-v1-pilot.py"
)
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
replay_spec = importlib.util.spec_from_file_location(
    "historical_generator_root", ROOT / "scripts/evals/replay-generator-skill-effect-v8.py"
)
historical = importlib.util.module_from_spec(replay_spec)
replay_spec.loader.exec_module(historical)


@contextmanager
def historical_overlap():
    files = (
        "scripts/evals/run-generator-overlap-v1-pilot.py",
        "scripts/evals/run-generator-environment-pilot-v1.py",
        "scripts/evals/generator-environment-probe.py",
        "scripts/evals/generator-environment-successor-probe.py",
        "benchmarks/generator-overlap-v1-pilot/protocol.json",
        "benchmarks/generator-overlap-v1-pilot/freeze.json",
        "benchmarks/generator-environment-pilot-v1/reports/environment-successor-probe.json",
    )
    snapshot = "benchmarks/generator-overlap-v1-pilot/arms"
    with historical.historical_project(
        extra_files=files, extra_trees=(snapshot,),
        tree_aliases=((snapshot + "/after/playwright-test-generator",
                       "skills/playwright-test-generator"),),
    ) as root:
        spec = importlib.util.spec_from_file_location(
            "historical_overlap_pilot", root / "scripts/evals/run-generator-overlap-v1-pilot.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module


@contextmanager
def archived_product():
    engine = pilot.pilot.engine
    original = engine.tree_digest
    frozen = original(pilot.SNAPSHOTS["after"])

    def tree_digest(path, *args, **kwargs):
        if path == ROOT / "skills/playwright-test-generator":
            return frozen
        return original(path, *args, **kwargs)

    with patch.object(engine, "tree_digest", side_effect=tree_digest):
        yield


class OverlapPilotTests(unittest.TestCase):
    def test_one_factor_snapshots(self):
        with archived_product():
            trees = pilot.snapshot_check()
        before, after = (trees[arm] for arm in pilot.ARMS)
        self.assertEqual(
            {name for name in before if before[name] != after[name]},
            {"scenario-design.md", "verification-rules.md"},
        )

    def test_three_fresh_balanced_pairs(self):
        with archived_product():
            rows = pilot.schedule()
        self.assertEqual(len(rows), 6)
        self.assertEqual([row["repetition"] for row in rows], [1, 1, 2, 2, 3, 3])
        self.assertEqual([row["arm"] for row in rows], ["before", "after", "after", "before", "before", "after"])
        self.assertTrue(all(row["case"] == "v3-13" for row in rows))

    def test_live_usage_needs_explicit_flag(self):
        with self.assertRaisesRegex(ValueError, "--allow-live"):
            pilot.run(SimpleNamespace(allow_live=False))

    def test_frozen_inputs_and_schedule(self):
        if pilot.LOCK.exists():
            with historical_overlap() as archived:
                self.assertEqual(archived.pilot.frozen()["schedule"], archived.schedule())

    def test_historical_frozen_guard_rejects_helper_drift(self):
        with historical_overlap() as archived:
            helper = archived.ROOT / historical.HELPER_PATH
            helper.write_bytes(helper.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "frozen pilot inputs or schedule drift"):
                archived.pilot.frozen()

    def test_frozen_runner_refuses_current_product_drift(self):
        current = pilot.pilot.engine.tree_digest(ROOT / "skills/playwright-test-generator", skip=("evals",))
        frozen = pilot.pilot.engine.tree_digest(pilot.SNAPSHOTS["after"])
        if current != frozen:
            with self.assertRaisesRegex(ValueError, "after snapshot differs from current product skill"):
                pilot.snapshot_check()

    def test_decision_requires_incremental_race_kills_and_quality(self):
        target = "f2-stale-response-wins"
        other = "f1-search-noop"
        runs, scores = [], []
        with archived_product():
            schedule = pilot.schedule()
        for item in schedule:
            arm, repetition = item["arm"], item["repetition"]
            call_id = f"v3-13-{arm}-r{repetition}"
            runs.append(dict(item, call_id=call_id, tests_files=["tests/search.spec.mjs"],
                             attempts=[dict(elapsed_ms=1000, usage={"input_tokens": 10})],
                             structured_output={"status": "complete"}))
            scores.append(dict(item, call_id=call_id, tests_files=["tests/search.spec.mjs"],
                               clean=True, clean_runs=[{"ok": True}] * 3, refactor_score=1,
                               primary=1.0, scan={"p0": 0}, timeout=False, out_of_scope_writes=[],
                               faults={target: {"killed": arm == "after" and repetition < 3},
                                       other: {"killed": True}}))
        report = {"runs": runs}
        result = pilot.decision(report, scores)
        self.assertEqual(result["status"], "DIRECTIONAL_SIGNAL")
        self.assertEqual(result["target_fault_kills"], {"before": 0, "after": 2})
        scores[0]["faults"][target]["killed"] = True
        scores[3]["faults"][target]["killed"] = True
        self.assertEqual(pilot.decision(report, scores)["status"], "PILOT_NOT_PROMISING")


if __name__ == "__main__":
    unittest.main()
