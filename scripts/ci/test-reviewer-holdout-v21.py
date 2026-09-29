#!/usr/bin/env python3
"""Offline v21 corpus, revision binding, and decisive gate checks."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "scripts/evals/reviewer-holdout-v21.json"
PROTOCOL = ROOT / "scripts/evals/reviewer-validation-protocol-v21.json"
LABELING = ROOT / "benchmarks/reviewer-holdout-v21/labeling"
README = ROOT / "benchmarks/reviewer-holdout-v21/README.md"
REPORTS = ROOT / "benchmarks/reviewer-holdout-v21/reports"
PROTOCOL_ID = "reviewer-holdout-v21"
EXPECTED_PROTOCOL_SHA256 = "050867ce7eaa44d70f9070d59860ffdb0aad75b92531dce1d8cf702d2106154b"
EXPECTED_CASES_FILE_SHA256 = "1e3e5e2ac948056812ea7966d81f2df2b646cd6d486e758b72b49f8d78ced09e"
EXPECTED_CORPUS_SHA256 = "e792f200fdf1ba5b5bedd956fb5f3b27bec15fba519c3f59ec2204ef9edb2113"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finding_tuples(cases: list[dict]) -> set[tuple[str, str, str, int]]:
    return {
        (label["pattern_id"], label["severity"], label["file"], label["line"])
        for case in cases
        for label in case["labels"]
        if label["kind"] == "finding"
    }


class ReviewerHoldoutV21Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load("v21_runner", ROOT / "scripts/evals/run-reviewer-holdout.py")
        cls.revisions = load(
            "v21_revisions", ROOT / "scripts/evals/compare-reviewer-revisions.py"
        )
        cls.protocol = cls.runner.load_protocol(PROTOCOL)
        cls.metadata, cls.cases = cls.runner.load_cases(CASES)

    def test_frozen_inputs_and_runner_registration(self) -> None:
        self.assertEqual(EXPECTED_PROTOCOL_SHA256, self.runner.V21_PROTOCOL_SHA256)
        self.assertEqual(EXPECTED_PROTOCOL_SHA256, hashlib.sha256(PROTOCOL.read_bytes()).hexdigest())
        self.assertEqual(
            EXPECTED_CASES_FILE_SHA256,
            hashlib.sha256(CASES.read_bytes()).hexdigest(),
        )
        digest = self.runner.corpus_digest(CASES, self.cases)
        self.assertEqual(EXPECTED_CASES_FILE_SHA256, self.protocol["corpus"]["cases_file_sha256"])
        self.assertEqual(EXPECTED_CORPUS_SHA256, self.protocol["corpus"]["corpus_sha256"])
        self.assertEqual(EXPECTED_CORPUS_SHA256, digest)
        self.runner.validate_corpus_protocol_pairing(self.metadata, self.protocol, digest)
        self.assertEqual(CASES, self.runner.REVISED_LABEL_CORPORA[PROTOCOL_ID])
        self.assertEqual(
            {"runner": "codex", "model": "gpt-6-sol"},
            self.runner.REVISED_LABEL_HOSTS[PROTOCOL_ID],
        )
        self.assertEqual(
            "minimum", self.runner.FROZEN_EXECUTION_IDENTITY_POLICIES[PROTOCOL_ID]
        )
        for name in (
            "SUPPORTED_PROTOCOL_IDS",
            "STRICT_MAJORITY_PROTOCOL_IDS",
            "PROMPT_ARM_PROTOCOL_IDS",
            "CODEX_ONLY_PROTOCOL_IDS",
            "NUMBERED_SOURCE_PROTOCOL_IDS",
            "REVISED_LABEL_PROTOCOL_IDS",
            "DESIGNED_LABEL_PROTOCOL_IDS",
            "INFRASTRUCTURE_RETRY_PROTOCOL_IDS",
            "USAGE_CAPTURE_PROTOCOL_IDS",
            "OUTPUT_SCHEMA_PROTOCOL_IDS",
            "REVISION_COMPARISON_PROTOCOL_IDS",
        ):
            self.assertIn(PROTOCOL_ID, getattr(self.runner, name), name)
        for name in (
            "ARM_COMPARISON_PROTOCOL_IDS",
            "FULL_ONLY_PROTOCOL_IDS",
            "OUTPUT_NORMALIZATION_PROTOCOL_IDS",
            "PROVIDER_BALANCED_PROTOCOL_IDS",
            "SUPERSEDED_PROTOCOL_IDS",
            "HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS",
            "SPECIFICITY_PROTOCOL_IDS",
        ):
            self.assertNotIn(PROTOCOL_ID, getattr(self.runner, name), name)
        self.assertEqual(
            {
                "cases_file_sha256": self.protocol["corpus"]["cases_file_sha256"],
                "corpus_sha256": self.protocol["corpus"]["corpus_sha256"],
                "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            },
            self.runner.PINNED_LIVE_INPUTS[(CASES, PROTOCOL)],
        )

    def test_corpus_mix_and_source_lines(self) -> None:
        self.assertEqual(48, len(self.cases))
        self.assertEqual(
            {"playwright": 24, "cypress": 24},
            {
                framework: sum(case["framework"] == framework for case in self.cases)
                for framework in ("playwright", "cypress")
            },
        )
        self.assertEqual(
            {"finding": 48, "fp_guard": 108},
            {
                kind: sum(
                    label["kind"] == kind
                    for case in self.cases
                    for label in case["labels"]
                )
                for kind in ("finding", "fp_guard")
            },
        )
        traps = [case for case in self.cases if "partial trap" in case["design_note"]]
        self.assertEqual(12, len(traps))
        for case in traps:
            findings = [label for label in case["labels"] if label["kind"] == "finding"]
            self.assertEqual([("#1", "P1")], [(x["pattern_id"], x["severity"]) for x in findings])
            self.assertEqual(
                {("#2", "P0"), ("#2", "P1"), ("#1", "P0")},
                {
                    (label["pattern_id"], label["severity"])
                    for label in case["labels"]
                    if label["kind"] == "fp_guard"
                },
            )
        for case in self.cases:
            self.assertEqual("public-development-v21", case["split"])
            source_by_path = {}
            for source in case["source_files"]:
                lines = (ROOT / "scripts/evals" / source["source"]).read_text().splitlines()
                source_by_path[source["path"]] = lines
            for label in case["labels"]:
                self.assertEqual(
                    label["source_line"],
                    source_by_path[label["file"]][label["line"] - 1].strip(),
                    label["finding_id"],
                )

    def test_blind_labels_and_fixed_brief(self) -> None:
        author = finding_tuples(self.cases)
        self.assertEqual(48, len(author))
        for name, model in (
            ("labels-gpt-6-astra.json", "gpt-6-astra"),
            ("labels-gpt-6-luna.json", "gpt-6-luna"),
        ):
            data = json.loads((LABELING / name).read_text())
            self.assertEqual(model, data["labeler"])
            blind = {
                (finding["pattern_id"], finding["severity"], finding["file"], finding["line"])
                for findings in data["cases"].values()
                for finding in findings
            }
            self.assertEqual(author, blind)
        brief = (LABELING / "BRIEF.txt").read_text()
        for contract in (
            "12: #2 partial",
            "12: TRAPS for over-applying #2",
            "title-level promises with partial verification that must stay #1 P1",
            "Ground-truth rules, fixed now",
        ):
            self.assertIn(contract, brief)
        procedure = self.metadata["labeling"]["procedure"]
        self.assertIn("Codex gpt-6-sol", procedure)
        self.assertIn("48/48", procedure)
        self.assertIn("gpt-6-astra", procedure)
        self.assertIn("gpt-6-luna", procedure)

    def test_revision_skill_archives_match_v20_pins(self) -> None:
        expected_commits = {
            "before": "976c3fae4400a2683bab2c2a015af0bd842e4dd5",
            "after": "23267980c7afb74acf128eefee55ee326b5f428a",
        }
        for revision, pin in self.protocol["revision_comparison"]["revisions"].items():
            self.assertEqual(expected_commits[revision], pin["source_commit"])
            with self.subTest(revision=revision), tempfile.TemporaryDirectory() as temp:
                tree = subprocess.check_output(
                    [
                        "/usr/bin/git",
                        "rev-parse",
                        f"{pin['source_commit']}:skills/e2e-reviewer",
                    ],
                    cwd=ROOT,
                    text=True,
                ).strip()
                self.assertEqual(pin["skill_tree"], tree)
                archive = subprocess.check_output(
                    [
                        "/usr/bin/git",
                        "archive",
                        pin["source_commit"],
                        "skills/e2e-reviewer",
                    ],
                    cwd=ROOT,
                )
                with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
                    handle.extractall(temp, filter="data")
                self.assertEqual(
                    pin["skill_sha256"],
                    self.runner.skill_digest(Path(temp) / "skills/e2e-reviewer"),
                )

    def test_protocol_and_decision_boundary(self) -> None:
        self.assertEqual([("before", "full"), ("after", "full")], self.revisions.cells(self.protocol))
        self.assertEqual(5, self.protocol["schedule"]["release_repetitions"])
        self.assertEqual([{"runner": "codex", "model": "gpt-6-sol"}], self.protocol["host_matrix"])
        self.assertEqual({"enabled": True}, self.protocol["usage_capture"])
        self.assertEqual(
            {
                "timeout",
                "malformed_json_output",
                "runner_nonzero_exit_with_usage_limit_text",
                "runner_auth_error",
                "codex_unexpected_stream_item",
            },
            set(self.protocol["infrastructure_retry"]["retryable"]),
        )
        self.assertEqual(
            {
                "stable_f1_delta_min": 0.05,
                "stable_f1_delta_ci95_lower_min_exclusive": 0,
                "stable_guard_hit_rate_delta_max": 0,
                "trap_pattern_1_to_2_misclassifications_delta_max": 0,
            },
            self.protocol["revision_comparison"]["decision"]["thresholds"],
        )

        def comparison(delta: float, lower: float, guard: float, traps: int) -> dict:
            return {
                "arms": {
                    "full": {
                        "delta": {"stable_f1": delta},
                        "intervals": {"stable_f1": {"lower": lower}},
                        "stable_guard_hit_rate": {"delta": guard},
                    }
                },
                "trap_cases": {
                    "delta": {"pattern_1_to_2_misclassifications": traps}
                },
            }

        self.assertEqual(
            "SUPPORTED", self.revisions.decide(comparison(0.05, 0.001, 0, 0), self.protocol)[0]
        )
        for values in (
            (0.049, 0.001, 0, 0),
            (0.05, 0, 0, 0),
            (0.05, 0.001, 0.001, 0),
            (0.05, 0.001, 0, 1),
        ):
            with self.subTest(values=values):
                self.assertEqual(
                    "NOT_SUPPORTED",
                    self.revisions.decide(comparison(*values), self.protocol)[0],
                )

    def test_trap_metrics_use_only_the_fixed_trap_cases(self) -> None:
        trap = next(case for case in self.cases if "partial trap" in case["design_note"])
        label = next(item for item in trap["labels"] if item["kind"] == "finding")
        wrong = next(
            item
            for item in trap["labels"]
            if item["kind"] == "fp_guard" and item["pattern_id"] == "#2"
            and item["severity"] == "P1"
        )

        def finding(item: dict) -> dict:
            return {key: item[key] for key in ("pattern_id", "severity", "file", "line")}

        correct_report = {
            "runs": [
                {
                    "case": trap["id"],
                    "score": {},
                    "findings": [finding(label)] if repetition < 3 else [],
                }
                for repetition in range(5)
            ]
        }
        self.assertEqual(
            {
                "cases": 1,
                "correct": 1,
                "accuracy": 1.0,
                "pattern_1_to_2_misclassifications": 0,
            },
            self.revisions.trap_case_metrics(correct_report, [trap]),
        )

        wrong_report = {
            "runs": [
                {
                    "case": trap["id"],
                    "score": {},
                    "findings": [finding(wrong)] if repetition < 3 else [],
                }
                for repetition in range(5)
            ]
        }
        self.assertEqual(
            {
                "cases": 1,
                "correct": 0,
                "accuracy": 0.0,
                "pattern_1_to_2_misclassifications": 1,
            },
            self.revisions.trap_case_metrics(wrong_report, [trap]),
        )

        # Favorable results outside the fixed trap list do not enter this metric
        # and therefore cannot offset a new trap misclassification in the gate.
        wrong_report["runs"].extend(
            {"case": "v21-pw-01", "score": {}, "findings": []} for _ in range(5)
        )
        self.assertEqual(
            1,
            self.revisions.trap_case_metrics(wrong_report, [trap])[
                "pattern_1_to_2_misclassifications"
            ],
        )
        comparison = {
            "arms": {
                "full": {
                    "delta": {"stable_f1": 0.05},
                    "intervals": {"stable_f1": {"lower": 0.001}},
                    "stable_guard_hit_rate": {"delta": 0},
                }
            },
            "trap_cases": {
                "delta": {"pattern_1_to_2_misclassifications": 1}
            },
            "descriptive_severity": {
                "before": {"pattern_1_to_2_misclassifications": 100},
                "after": {"pattern_1_to_2_misclassifications": 0},
            },
        }
        self.assertEqual("NOT_SUPPORTED", self.revisions.decide(comparison, self.protocol)[0])

    def test_documented_run_and_wiring(self) -> None:
        readme = README.read_text()
        self.assertEqual(
            3,
            readme.count("--protocol scripts/evals/reviewer-validation-protocol-v21.json"),
        )
        self.assertIn("480 scheduled calls", readme)
        self.assertIn("git archive 976c3fa", readme)
        self.assertIn("git archive 2326798", readme)
        self.assertIn(
            'OUT="${XDG_CACHE_HOME:-$HOME/.cache}/e2e-skills-bench/reviewer-holdout-v21"',
            readme,
        )
        self.assertIn(
            "test-reviewer-holdout-v21.py",
            (ROOT / "scripts/ci/ci-local.sh").read_text(),
        )
        self.assertIn(
            "test-reviewer-holdout-v21.py", (ROOT / "CONTRIBUTING.md").read_text()
        )
        self.assertIn(
            "reviewer-holdout-v21/README.md",
            (ROOT / "docs/ai-reviewer-benchmark.md").read_text(),
        )

    def test_recorded_result(self) -> None:
        comparison = json.loads((REPORTS / "revision-comparison.json").read_text())
        self.assertEqual("NOT_SUPPORTED", comparison["status"])
        self.assertEqual(
            [
                "revision_stable_f1_delta_min",
                "revision_stable_f1_delta_ci95_lower_min_exclusive",
                "revision_stable_guard_hit_rate_delta_max",
            ],
            [reason["code"] for reason in comparison["status_reasons"]],
        )
        full = comparison["comparison"]["arms"]["full"]
        self.assertEqual(1.0, full["before"]["stable_f1"])
        self.assertAlmostEqual(0.9795918367346939, full["after"]["stable_f1"])
        self.assertAlmostEqual(-0.020408163265306145, full["delta"]["stable_f1"])
        self.assertAlmostEqual(
            -0.04255319148936165, full["intervals"]["stable_f1"]["lower"]
        )
        self.assertEqual(0, full["intervals"]["stable_f1"]["upper"])
        self.assertEqual(0, full["stable_guard_hit_rate"]["before"])
        self.assertAlmostEqual(
            2 / 108, full["stable_guard_hit_rate"]["after"]
        )

        severity = comparison["comparison"]["descriptive_severity"]
        for revision in ("before", "after"):
            self.assertEqual(24, severity[revision]["correct_pattern_2_severity"])
            self.assertEqual(24, severity[revision]["pattern_2_labels"])
            self.assertEqual(0, severity[revision]["pattern_1_to_2_misclassifications"])
            self.assertEqual(0, severity[revision]["pattern_2_to_1_misclassifications"])
        traps = comparison["comparison"]["trap_cases"]
        for revision in ("before", "after"):
            self.assertEqual((12, 12, 1.0, 0), (
                traps[revision]["cases"], traps[revision]["correct"],
                traps[revision]["accuracy"],
                traps[revision]["pattern_1_to_2_misclassifications"],
            ))

        self.assertEqual(
            480,
            sum(
                len(json.loads((REPORTS / f"full-{revision}.json").read_text())["runs"])
                for revision in ("before", "after")
            ),
        )
        self.assertEqual(
            0,
            sum(
                json.loads((REPORTS / f"full-{revision}.json").read_text())[
                    "infrastructure_retry_summary"
                ]["retries"]
                for revision in ("before", "after")
            ),
        )
        for item in comparison["report_inputs"]:
            report = REPORTS / f"full-{item['revision']}.json"
            self.assertEqual(item["sha256"], hashlib.sha256(report.read_bytes()).hexdigest())

        readme = README.read_text()
        for statement in (
            "`NOT_SUPPORTED`",
            "1.000 BEFORE to 0.980 AFTER",
            "[-0.043, 0.000]",
            "0.000 to 0.019",
            "24/24 in both revisions",
            "All 480 scheduled calls scored with 0 retries",
            "keep the 2.0.0 wording with no clarification",
            "likely corpus-construction effect",
        ):
            self.assertIn(statement, readme)


if __name__ == "__main__":
    unittest.main()
