#!/usr/bin/env python3
"""Validate the neutral, public pre-publication v4 reviewer corpus."""

from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v4.json"
PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v4.json"
SOURCE_ROOT = ROOT / "scripts/evals/files/holdout-v4"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"

EXPECTED_CORPUS_SHA256 = "da1a77c0be808b2e35a662a937227ec0e69bc0b4900cdb9f15f9860295305952"
EXPECTED_PROTOCOL_SHA256 = "3cf0fc53f62b4822f61b2fd30cf653d3241fd1510a7814cde22c05b6e25ca831"
EXPECTED_SOURCE_TREE_SHA256 = "a650dcf2b3e83daf1c9f30ef41cb9d5de77d1d3ad6ac33f4ff2ee6f5d711fdde"
EXPECTED_FAMILIES = {f"#{number}" for number in range(1, 24)} | {"#3b"}
ANSWER_LEADING_TERMS = re.compile(
    r"\b(?:"
    r"anti[- ]?pattern|bad|broken|bug|bypass|false positive|finding|flaky|"
    r"hardcoded|manual|missing|oracle|pattern|smell|swallow|unsafe|"
    r"unprotected|unused|vacuous|weak|zombie"
    r")\b",
    re.IGNORECASE,
)


def family(pattern_id: str) -> str:
    if pattern_id == "#3b":
        return pattern_id
    for prefix in ("#4", "#5", "#8", "#9", "#10"):
        if pattern_id.startswith(prefix):
            return prefix
    return pattern_id


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewerHoldoutV4Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = json.loads(CASES_PATH.read_text(encoding="utf-8"))
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        cls.cases = cls.corpus["cases"]

    def test_covers_each_stable_family_once_for_findings_and_guards(self) -> None:
        by_kind = {
            kind: [
                label
                for case in self.cases
                for label in case["labels"]
                if label["kind"] == kind
            ]
            for kind in ("finding", "fp_guard")
        }
        for kind, labels in by_kind.items():
            families = [family(label["pattern_id"]) for label in labels]
            self.assertEqual(EXPECTED_FAMILIES, set(families), kind)
            self.assertEqual(len(EXPECTED_FAMILIES), len(families), kind)

    def test_runner_accepts_corpus_schema_and_canonical_severities(self) -> None:
        runner = load_module("reviewer_holdout_v4_runner", RUNNER_PATH)
        _, loaded_cases = runner.load_cases(CASES_PATH)
        self.assertEqual(PROTOCOL_PATH, runner.V4_PROTOCOL)
        self.assertEqual(CASES_PATH, runner.V4_CASES)
        self.assertEqual(self.protocol, runner.load_protocol(PROTOCOL_PATH))
        self.assertIn(
            self.protocol["protocol_id"],
            runner.HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS,
        )
        self.assertEqual(
            {
                self.protocol["prompt_arms"]["treatment"],
                *self.protocol["prompt_arms"]["controls"],
            },
            set(runner.PROMPT_SKILL_PROFILES),
        )
        pinned = runner.PINNED_LIVE_INPUTS[(CASES_PATH, PROTOCOL_PATH)]
        self.assertEqual(EXPECTED_CORPUS_SHA256, pinned["cases_file_sha256"])
        self.assertEqual(EXPECTED_PROTOCOL_SHA256, pinned["protocol_sha256"])
        self.assertEqual(
            runner.corpus_digest(CASES_PATH, loaded_cases),
            pinned["corpus_sha256"],
        )
        self.assertEqual(self.cases, loaded_cases)
        canonical = runner.canonical_severities(ROOT / "skills/e2e-reviewer")
        for case in loaded_cases:
            for label in case["labels"]:
                self.assertEqual(
                    canonical[label["pattern_id"]],
                    label["severity"],
                    label["finding_id"],
                )

    def test_clean_case_specificity_uses_stable_case_level_predictions(self) -> None:
        runner = load_module("reviewer_holdout_v4_specificity", RUNNER_PATH)
        clean_cases = [
            case
            for case in self.cases
            if {label["kind"] for label in case["labels"]} == {"fp_guard"}
        ]
        target = clean_cases[0]
        guard = target["labels"][0]
        stable_guard_prediction = {
            "pattern_id": guard["pattern_id"],
            "severity": guard["severity"],
            "file": guard["file"],
            "line": guard["line"],
        }
        runs = []
        for case in self.cases:
            for repetition in range(1, 4):
                findings = (
                    [stable_guard_prediction]
                    if case["id"] == target["id"] and repetition <= 2
                    else []
                )
                runs.append(
                    {
                        "case": case["id"],
                        "repetition": repetition,
                        "findings": findings,
                        "score": {},
                    }
                )
        specificity = runner.primary_metrics(
            self.cases,
            runs,
            3,
            "strict-majority",
        )["clean_case_specificity"]
        self.assertEqual(8, specificity["clean_cases"])
        self.assertEqual(7, specificity["cases_without_stable_predictions"])
        self.assertEqual(0.875, specificity["value"])
        self.assertTrue(
            specificity["by_case"][target["id"]]["has_stable_prediction"]
        )

    def test_provider_families_are_equal_weighted_after_within_family_mean(
        self,
    ) -> None:
        comparator = load_module(
            "reviewer_holdout_v4_comparator",
            COMPARATOR_PATH,
        )

        def report(runner: str, model: str, precision: float) -> dict:
            return {
                "runner": runner,
                "model": model,
                "primary_metrics": {
                    "unique": {
                        "precision": precision,
                        "recall": precision,
                        "f1": precision,
                    },
                    "p0_per_label_stability": {
                        "stable_label_recall": precision,
                    },
                    "clean_case_specificity": {"value": precision},
                },
                "secondary_metrics": {"precision": precision},
            }

        aggregation = comparator.provider_family_aggregation(
            [
                report("codex", "gpt-5.6-sol", 1.0),
                report("claude", "claude-opus-5", 1.0),
                report("claude", "claude-fable-5", 0.0),
            ]
        )
        self.assertEqual(
            "mean-within-provider-family-then-equal-weight-families",
            aggregation["method"],
        )
        self.assertEqual(2, aggregation["provider_family_denominator"])
        self.assertEqual(
            1,
            aggregation["families"]["openai"]["configuration_count"],
        )
        self.assertEqual(
            2,
            aggregation["families"]["anthropic"]["configuration_count"],
        )
        self.assertEqual(
            0.5,
            aggregation["families"]["anthropic"]["metrics"][
                "stable_precision"
            ]["value"],
        )
        self.assertEqual(
            0.75,
            aggregation["equal_weighted_metrics"]["stable_precision"]["value"],
        )
        self.assertNotEqual(
            (1.0 + 1.0 + 0.0) / 3,
            aggregation["equal_weighted_metrics"]["stable_precision"]["value"],
        )

    def test_exact_source_lines_and_manifest_coverage_match(self) -> None:
        manifested_sources: set[Path] = set()
        finding_sources: set[Path] = set()
        guard_sources: set[Path] = set()
        for case in self.cases:
            sources = {
                entry["path"]: ROOT / "scripts/evals" / entry["source"]
                for entry in case["source_files"]
            }
            self.assertGreaterEqual(len(sources), 2, case["id"])
            self.assertTrue(
                any(
                    path.endswith((".spec.ts", ".cy.ts"))
                    for path in sources
                ),
                case["id"],
            )
            self.assertTrue(
                any(
                    not path.endswith((".spec.ts", ".cy.ts"))
                    for path in sources
                ),
                case["id"],
            )
            manifested_sources.update(sources.values())
            for label in case["labels"]:
                source = sources[label["file"]]
                lines = source.read_text(encoding="utf-8").splitlines()
                self.assertGreaterEqual(label["line"], 1, label["finding_id"])
                self.assertLessEqual(label["line"], len(lines), label["finding_id"])
                self.assertEqual(
                    label["source_line"],
                    lines[label["line"] - 1].strip(),
                    label["finding_id"],
                )
                target = finding_sources if label["kind"] == "finding" else guard_sources
                target.add(source)

        actual_sources = {
            candidate for candidate in SOURCE_ROOT.rglob("*") if candidate.is_file()
        }
        self.assertEqual(actual_sources, manifested_sources)
        self.assertTrue(finding_sources.isdisjoint(guard_sources))

    def test_clean_cases_are_separate_and_comprise_forty_percent(self) -> None:
        kinds_by_case = [
            {label["kind"] for label in case["labels"]}
            for case in self.cases
        ]
        self.assertTrue(all(len(kinds) == 1 for kinds in kinds_by_case))
        clean = [
            case
            for case, kinds in zip(self.cases, kinds_by_case)
            if kinds == {"fp_guard"}
        ]
        ratio = len(clean) / len(self.cases)
        self.assertGreaterEqual(ratio, 0.30)
        self.assertLessEqual(ratio, 0.50)
        self.assertEqual(0.40, ratio)

    def test_finding_and_clean_cases_are_framework_balanced(self) -> None:
        counts = Counter(
            (
                case["labels"][0]["kind"],
                case["framework"],
            )
            for case in self.cases
        )
        self.assertEqual(counts[("finding", "playwright")], 6)
        self.assertEqual(counts[("finding", "cypress")], 6)
        self.assertEqual(counts[("fp_guard", "playwright")], 4)
        self.assertEqual(counts[("fp_guard", "cypress")], 4)

    def test_source_surface_contains_no_answer_leading_vocabulary(self) -> None:
        for path in sorted(candidate for candidate in SOURCE_ROOT.rglob("*") if candidate.is_file()):
            relative = path.relative_to(SOURCE_ROOT).as_posix()
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(ANSWER_LEADING_TERMS.search(relative), relative)
            self.assertIsNone(ANSWER_LEADING_TERMS.search(text), relative)
            self.assertNotRegex(text, r"(?m)^\s*(?://|/\*|\*)")
            self.assertNotRegex(text, r"#[0-9]+b?\b")

    def test_case_identifiers_and_paths_are_neutral(self) -> None:
        for case in self.cases:
            self.assertRegex(case["id"], r"^(?:pw|cy)-[ac][0-9]{2}$")
            self.assertIsNone(ANSWER_LEADING_TERMS.search(case["id"]))
            for source in case["source_files"]:
                self.assertTrue(source["source"].startswith("files/holdout-v4/"))
                self.assertIsNone(ANSWER_LEADING_TERMS.search(source["source"]))

    def test_protocol_declares_scope_balance_repetitions_and_limits(self) -> None:
        protocol = self.protocol
        self.assertEqual(protocol["protocol_id"], "reviewer-holdout-v4")
        self.assertEqual(
            protocol["schedule"]["evidence_scope"],
            "public-pre-publication-development",
        )
        self.assertEqual(protocol["schedule"]["default_repetitions"], 3)
        self.assertEqual(protocol["schedule"]["release_repetitions"], 3)
        self.assertEqual(protocol["stability"]["minimum_repetitions"], 3)
        self.assertEqual(
            protocol["prompt_arms"],
            {
                "treatment": "full",
                "controls": ["catalog-only", "no-skill"],
                "shared_output_legend": True,
                "no_skill_is_taxonomy_free": False,
                "comparison_unit": "separate-complete-host-matrix",
            },
        )
        self.assertEqual(
            {
                (entry["runner"], entry["model"])
                for entry in protocol["host_matrix"]
            },
            {
                ("codex", "gpt-5.6-sol"),
                ("claude", "claude-opus-5"),
                ("claude", "claude-fable-5"),
            },
        )
        self.assertEqual(
            protocol["decision"]["thresholds"]["clean_case_specificity_min"],
            0.95,
        )
        self.assertIn(
            "equal top-level weight",
            protocol["cross_host_decision"]["aggregation_intent"],
        )
        limits = protocol["decision"]["point_estimate_limits"].lower()
        for required in (
            "descriptive",
            "confidence intervals",
            "human oracle",
            "generalization",
            "not established",
        ):
            self.assertIn(required, limits)

    def test_frozen_artifact_digests_are_deterministic(self) -> None:
        self.assertEqual(sha256(CASES_PATH), sha256(CASES_PATH))
        self.assertEqual(sha256(PROTOCOL_PATH), sha256(PROTOCOL_PATH))
        self.assertEqual(source_tree_sha256(SOURCE_ROOT), source_tree_sha256(SOURCE_ROOT))
        self.assertEqual(EXPECTED_CORPUS_SHA256, sha256(CASES_PATH))
        self.assertEqual(EXPECTED_PROTOCOL_SHA256, sha256(PROTOCOL_PATH))
        self.assertEqual(EXPECTED_SOURCE_TREE_SHA256, source_tree_sha256(SOURCE_ROOT))


if __name__ == "__main__":
    unittest.main(verbosity=2)
