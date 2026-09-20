#!/usr/bin/env python3
"""Validate the frozen Codex-only v7 protocol and committed result."""

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
EVIDENCE_PATH = ROOT / "benchmarks/reviewer-holdout-v7"
REPORTS_PATH = EVIDENCE_PATH / "reports"
ADDENDUM_PATH = EVIDENCE_PATH / "addenda/trim-cb9aca2"

EXPECTED_CASES_FILE_SHA256 = "50c828c5e267a683ced73a161a645af0b73f305f6391b6fe0e8ee150ec419849"
EXPECTED_CORPUS_SHA256 = "745bc765fb6f424abe90d6d3fc9a3b85e921472a4cc1291054879af8002e965f"
EXPECTED_PROTOCOL_SHA256 = "e379edfc7ad04e4ff92134f3f5952bda7f146e0f80667726283a2a60de08daf2"
EXPECTED_ARTIFACT_SHA256 = {
    "reports/arm-comparison.json": "41b31d9f57ff052a37077902c9ec7719d838fda9aae3bb4cd91f790736a08ab3",
    "reports/catalog-only-codex.json": "94ee295973d81eca5d2dffb7fcd7e93788e40790049a01715930ae0a75466ca4",
    "reports/full-codex.json": "cb79b2622076bc72397baed97f9fd8710231b363d6a7526425bbdcea9ca38e2c",
    "reports/no-skill-codex.json": "72af18536f24b475d2bcc11404e5956fb0a34e98ae08a1a21659f779fe264541",
    "attempts/1/full-codex.json": "715bf63664d6cb45c875c0a7fe46ecbc64fcc384a74fab6f93d064dc96060e32",
    "attempts/2/full-codex.json": "2d02b9ebb60a67cd53658b6873481ca6cd85d2909fead1016a475ebac48d4b26",
    "attempts/3/arm-comparison.json": "14dedcd6b0bf56afee40e049729c0069a74fcbc922f4f8257f616f3c7a8e99ff",
    "attempts/3/catalog-only-codex.json": "805c6053170e2c2dfc62b632762aa80d7adb8fe3540e86d0c802d84843fd74bc",
    "attempts/3/full-codex.json": "07c15c87f620737bafb3ca20b1ed88e760d845b387b01d8179a33c0f6fd70468",
    "attempts/3/no-skill-codex.json": "a62634be45edbdcd27a6cf2c78d6827a83caf378fe3af8633f45369ead70c83c",
    "addenda/trim-cb9aca2/arm-comparison.json": "df618823f467dd4ead9208b83e5197ef60284def40c02f3ee7056861647d1baf",
    "addenda/trim-cb9aca2/catalog-only-codex.json": "bdacd3396b5a42480d0e42d29b4a402c19d36107aa2c1a98eae6b3ad82215a61",
    "addenda/trim-cb9aca2/full-codex.json": "8cfb41433fc57f31120abe4f49812471f21b0ab5f1e37c60e831262a42ebba42",
    "addenda/trim-cb9aca2/no-skill-codex.json": "d59b400cca70e3f69a8ac17b41f35f5a95044fc8586c7dfa26daf23c7384425c",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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

    def test_benchmark_docs_match_committed_fail_result(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        status = STATUS_PATH.read_text(encoding="utf-8")
        comparison = read_json(REPORTS_PATH / "arm-comparison.json")
        for text in (readme, status):
            self.assertIn("Reviewer holdout v7", text)
            self.assertIn("skill_lift_claim_eligible", text)
            self.assertNotIn("No Reviewer holdout v7 result is claimed", text)
        self.assertIn(f"Status: **{comparison['status']}**.", readme)
        self.assertIn("complete, failed", readme.splitlines()[0].lower())
        self.assertIn("v5/v6 Claude Fable plan-mode failures", readme)
        self.assertIn("Complete; `FAIL`; no skill-lift claim", status)
        self.assertFalse(comparison["skill_lift_claim_eligible"])
        mutated = readme.replace("Status: **FAIL**.", "Status: **PASS**.", 1)
        self.assertNotIn(f"Status: **{comparison['status']}**.", mutated)
        for contract in (
            "180 model calls",
            "reviewer-validation-protocol-v7.json",
            EXPECTED_CASES_FILE_SHA256,
            EXPECTED_CORPUS_SHA256,
            EXPECTED_PROTOCOL_SHA256,
        ):
            self.assertIn(contract, readme)

    def test_committed_artifact_bytes_and_provenance(self) -> None:
        for relative, expected in EXPECTED_ARTIFACT_SHA256.items():
            self.assertEqual(
                expected,
                hashlib.sha256((EVIDENCE_PATH / relative).read_bytes()).hexdigest(),
                relative,
            )

        comparison = read_json(REPORTS_PATH / "arm-comparison.json")
        self.assertEqual("FAIL", comparison["status"])
        self.assertFalse(comparison["skill_lift_claim_eligible"])
        self.assertFalse(comparison["release_eligible"])
        self.assertEqual("development", comparison["evidence_scope"])
        self.assertEqual(EXPECTED_CORPUS_SHA256, comparison["corpus_sha256"])
        self.assertEqual(EXPECTED_PROTOCOL_SHA256, comparison["protocol_sha256"])

    def test_addendum_artifacts_and_docs_match_exploratory_result(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        status = STATUS_PATH.read_text(encoding="utf-8")
        comparison = read_json(ADDENDUM_PATH / "arm-comparison.json")
        self.assertIn("Addendum: exploratory rerun", readme)
        self.assertIn(
            "uncounted addendum on the trimmed reviewer plus the pattern `#3` fix "
            "within the same release",
            status,
        )
        self.assertIn(
            "the trimmed reviewer plus the pattern `#3` swallowed-assertion wording "
            "fix within the same release",
            readme,
        )
        self.assertNotIn("next/1.20.0", readme)
        self.assertEqual("FAIL", comparison["status"])
        self.assertFalse(comparison["skill_lift_claim_eligible"])
        self.assertFalse(comparison["release_eligible"])
        self.assertEqual("development", comparison["evidence_scope"])
        self.assertEqual(EXPECTED_CORPUS_SHA256, comparison["corpus_sha256"])
        self.assertEqual(EXPECTED_PROTOCOL_SHA256, comparison["protocol_sha256"])
        stated = "The exploratory comparator returned `FAIL`"
        self.assertIn(stated, readme)
        self.assertNotIn(
            stated,
            readme.replace(stated, "The exploratory comparator returned `PASS`", 1),
        )

    def test_counted_arm_provenance_is_complete_and_clean(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "the pre-trim reviewer as it stood before the trim and the pattern `#3` "
            "fix in the same release",
            readme,
        )
        self.assertNotIn("(`v1.19.0`)", readme)
        comparison = read_json(REPORTS_PATH / "arm-comparison.json")
        input_digests = {
            Path(item["path"]).name: item["sha256"]
            for item in comparison["report_inputs"]
        }
        revision = "110f2ea6a6e4876f601fa3b2cb6bd2ead40e48ab"
        for profile in ("full", "catalog-only", "no-skill"):
            name = f"{profile}-codex.json"
            report = read_json(REPORTS_PATH / name)
            self.assertEqual(EXPECTED_ARTIFACT_SHA256[f"reports/{name}"], input_digests[name])
            self.assertEqual(profile, report["prompt_profile"])
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(report["complete"])
            self.assertTrue(report["execution_complete"])
            self.assertEqual((60, 60, 0), (
                report["summary"]["runs"],
                report["summary"]["successful_runs"],
                report["summary"]["infrastructure_errors"],
            ))
            self.assertEqual(revision, report["git_revision"])
            self.assertFalse(report["git_dirty"])
            self.assertEqual(("codex", "gpt-5.6-sol", "codex-cli 0.154.0"), (
                report["runner"], report["model"], report["runner_identity"],
            ))

    def test_addendum_arm_provenance_is_complete_and_clean(self) -> None:
        expected_names = {
            "arm-comparison.json",
            "catalog-only-codex.json",
            "full-codex.json",
            "no-skill-codex.json",
        }
        self.assertEqual(expected_names, {path.name for path in ADDENDUM_PATH.iterdir()})
        comparison = read_json(ADDENDUM_PATH / "arm-comparison.json")
        input_digests = {
            Path(item["path"]).name: item["sha256"]
            for item in comparison["report_inputs"]
        }
        expected_status = {
            "full": "PASS",
            "catalog-only": "FAIL",
            "no-skill": "FAIL",
        }
        revision = "cb9aca231fc413876d5169c1617978c8a9a3ced2"
        for profile, status in expected_status.items():
            name = f"{profile}-codex.json"
            report = read_json(ADDENDUM_PATH / name)
            digest_key = f"addenda/trim-cb9aca2/{name}"
            self.assertEqual(EXPECTED_ARTIFACT_SHA256[digest_key], input_digests[name])
            self.assertEqual(
                (profile, status),
                (report["prompt_profile"], report["status"]),
            )
            self.assertTrue(report["complete"])
            self.assertTrue(report["execution_complete"])
            self.assertEqual((60, 60, 0), (
                report["summary"]["runs"],
                report["summary"]["successful_runs"],
                report["summary"]["infrastructure_errors"],
            ))
            self.assertEqual(revision, report["git_revision"])
            self.assertFalse(report["git_dirty"])

    def test_committed_decision_matches_absolute_failure(self) -> None:
        full = read_json(REPORTS_PATH / "full-codex.json")
        self.assertEqual(1, len(full["status_reasons"]))
        reason = full["status_reasons"][0]
        self.assertEqual("p0_stable_label_recall_min", reason["metric"])
        self.assertEqual((0.875, 0.9), (reason["actual"], reason["required"]))

    def test_committed_lift_decision(self) -> None:
        comparison = read_json(REPORTS_PATH / "arm-comparison.json")
        lifts = comparison["metrics"]["lift"]
        self.assertTrue(lifts["no-skill"]["passed"])
        self.assertTrue(all(row["passed"] for row in lifts["no-skill"]["decision_checks"]))
        failed = {
            row["metric"]
            for row in lifts["catalog-only"]["decision_checks"]
            if not row["passed"]
        }
        self.assertEqual({
            "stable_f1_delta_min",
            "stable_f1_delta_ci95_lower_min",
            "stable_recall_delta_min",
        }, failed)

    def test_systematic_pw_a06_miss(self) -> None:
        for relative in (
            "reports/full-codex.json",
            "reports/catalog-only-codex.json",
            "attempts/3/full-codex.json",
        ):
            report = read_json(EVIDENCE_PATH / relative)
            runs = [run for run in report["runs"] if run["case"] == "pw-a06"]
            self.assertEqual(3, len(runs), relative)
            self.assertTrue(all(run["output"] == '{"findings":[]}\n' for run in runs))
            self.assertTrue(all(
                run["score"]["missed_finding_ids"] == ["V5-014"]
                for run in runs
            ))

        no_skill = read_json(REPORTS_PATH / "no-skill-codex.json")
        runs = [run for run in no_skill["runs"] if run["case"] == "pw-a06"]
        self.assertEqual(3, len(runs))
        self.assertTrue(all(
            run["score"]["missed_finding_ids"] == ["V5-014"]
            for run in runs
        ))

    def test_full_run_keeps_outputs_outside_clean_checkout_until_arm_comparison(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("ordinary host shell", readme)
        self.assertIn("not from inside a Codex sandbox", readme)
        self.assertIn('OUT="${XDG_CACHE_HOME:-$HOME/.cache}/', readme)
        self.assertIn('test -z "$(git status --porcelain)"', readme)
        self.assertEqual(4, readme.count('--output "$OUT/'))
        self.assertIn("--compare-arms", readme)
        self.assertNotIn(
            "--output benchmarks/reviewer-holdout-v7/reports/",
            readme,
        )
        comparator_index = readme.index("python3 scripts/evals/compare-reviewer-holdouts.py")
        compare_arms_index = readme.index("--compare-arms", comparator_index)
        copy_index = readme.index('cp "$OUT/full-codex.json"', compare_arms_index)
        self.assertLess(comparator_index, compare_arms_index)
        self.assertLess(compare_arms_index, copy_index)
        for artifact in (
            "full-codex.json",
            "catalog-only-codex.json",
            "no-skill-codex.json",
            "arm-comparison.json",
        ):
            self.assertIn(f'"$OUT/{artifact}"', readme[copy_index:])

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
