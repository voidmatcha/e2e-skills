#!/usr/bin/env python3
"""Validate the frozen Codex-only v7 reviewer protocol."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v5.json"
V5_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v5.json"
V7_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v7.json"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
V5_TEST_PATH = ROOT / "scripts/ci/test-reviewer-holdout-v5.py"
README_PATH = ROOT / "benchmarks/reviewer-holdout-v7/README.md"
STATUS_PATH = ROOT / "benchmarks/STATUS.md"

EXPECTED_CASES_FILE_SHA256 = "50c828c5e267a683ced73a161a645af0b73f305f6391b6fe0e8ee150ec419849"
EXPECTED_CORPUS_SHA256 = "745bc765fb6f424abe90d6d3fc9a3b85e921472a4cc1291054879af8002e965f"
EXPECTED_PROTOCOL_SHA256 = "e379edfc7ad04e4ff92134f3f5952bda7f146e0f80667726283a2a60de08daf2"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewerHoldoutV7Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("reviewer_holdout_v7_runner", RUNNER_PATH)
        cls.comparator = load_module("reviewer_holdout_v7_comparator", COMPARATOR_PATH)
        cls.v5_helpers = load_module("reviewer_holdout_v5_helpers", V5_TEST_PATH)
        cls.v5 = json.loads(V5_PROTOCOL_PATH.read_text(encoding="utf-8"))
        cls.v7 = json.loads(V7_PROTOCOL_PATH.read_text(encoding="utf-8"))

    def test_frozen_inputs_and_runner_registration(self) -> None:
        self.assertEqual(
            EXPECTED_CASES_FILE_SHA256,
            hashlib.sha256(CASES_PATH.read_bytes()).hexdigest(),
        )
        _, cases = self.runner.load_cases(CASES_PATH)
        self.assertEqual(EXPECTED_CORPUS_SHA256, self.runner.corpus_digest(CASES_PATH, cases))
        self.assertEqual(
            EXPECTED_PROTOCOL_SHA256,
            hashlib.sha256(V7_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(self.v7, self.runner.load_protocol(V7_PROTOCOL_PATH))
        self.assertEqual(V7_PROTOCOL_PATH, self.runner.V7_PROTOCOL)
        self.assertEqual(
            {
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
                "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            },
            self.runner.PINNED_LIVE_INPUTS[(CASES_PATH, V7_PROTOCOL_PATH)],
        )

    def test_v7_changes_only_disclosed_execution_and_host_scope(self) -> None:
        v5_schedule = copy.deepcopy(self.v5["schedule"])
        v7_schedule = copy.deepcopy(self.v7["schedule"])
        disclosure = v7_schedule.pop("design_disclosure")
        self.assertEqual(v5_schedule, v7_schedule)
        self.assertIn("v5 and v6 Claude Fable plan-mode failures", disclosure)
        self.assertIn("does not change the v5 cases", disclosure)

        for key in ("stability", "confidence_intervals"):
            self.assertEqual(self.v5[key], self.v7[key], key)
        self.assertEqual(
            self.v5["decision"]["thresholds"],
            self.v7["decision"]["thresholds"],
        )
        for key in ("treatment", "controls", "stability_basis", "uncertainty", "decision"):
            self.assertEqual(
                self.v5["arm_comparison"][key],
                self.v7["arm_comparison"][key],
                key,
            )
        self.assertEqual(
            [{"runner": "codex", "model": "gpt-5.6-sol"}],
            self.v7["host_matrix"],
        )
        self.assertEqual("minimum", self.v7["execution_identity"]["version_policy"])
        self.assertEqual(
            {"codex": "codex-cli 0.154.0"},
            self.v7["execution_identity"]["expected_cli_versions"],
        )
        self.assertEqual(
            ["full", "catalog-only", "no-skill"],
            [step["prompt_profile"] for step in self.v7["arm_comparison"]["execution_order"]],
        )

    def test_existing_protocols_retain_plan_mode_and_off_is_opt_in(self) -> None:
        for version in (5, 6):
            protocol = json.loads(
                (ROOT / f"scripts/evals/reviewer-validation-protocol-v{version}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertNotIn("claude_permission_mode", protocol["execution_identity"])
        plan, _ = self.runner.runner_invocation("claude", "claude", "p", "m")
        off, _ = self.runner.runner_invocation(
            "claude", "claude", "p", "m", claude_permission_mode="off"
        )
        self.assertEqual(plan[:], [*off[:-2], "--permission-mode", "plan", *off[-2:]])

    def test_benchmark_docs_are_frozen_not_run_and_disclose_design_timing(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        status = STATUS_PATH.read_text(encoding="utf-8")
        for text in (readme, status):
            self.assertIn("frozen", text.lower())
            self.assertIn("not yet run", text.lower())
            self.assertIn("v5/v6 Claude Fable plan-mode failures", text)
            self.assertIn("No Reviewer holdout v7 result is claimed", text)
        for contract in (
            "180 model calls",
            "reviewer-validation-protocol-v7.json",
            EXPECTED_CASES_FILE_SHA256,
            EXPECTED_CORPUS_SHA256,
            EXPECTED_PROTOCOL_SHA256,
        ):
            self.assertIn(contract, readme)

    def test_single_host_comparator_is_decisive(self) -> None:
        cases = self.v5_helpers.synthetic_arm_cases()
        reports = [
            self.v5_helpers.synthetic_arm_report(
                self.comparator,
                profile,
                "codex",
                "gpt-5.6-sol",
                "strong" if profile == "full" else "weak",
                cases,
            )
            for profile in ("full", "catalog-only", "no-skill")
        ]
        for report in reports:
            report["runner_identity"] = "codex-cli 0.154.0"
        by_profile = {report["prompt_profile"]: report for report in reports}
        for step in self.v7["arm_comparison"]["execution_order"]:
            report = by_profile[step["prompt_profile"]]
            report["started_at"] = f"2026-09-19T00:00:0{step['ordinal'] - 1}+00:00"
            report["created_at"] = f"2026-09-19T00:00:0{step['ordinal']}+00:00"

        with (
            mock.patch.object(
                self.comparator,
                "recompute_report",
                side_effect=lambda report, *_args, **_kwargs: report,
            ),
            mock.patch.object(
                self.comparator,
                "compare_reports",
                return_value={"status": "PASS", "status_reasons": [], "metrics": {}},
            ),
        ):
            result = self.comparator.compare_arm_reports(
                reports,
                cases,
                "a" * 64,
                self.v7,
                "b" * 64,
                "public-development",
                "development",
            )
        self.assertEqual("PASS", result["status"])
        self.assertEqual(
            "exact-three-profiles-by-one-host",
            result["metrics"]["comparison_unit"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
