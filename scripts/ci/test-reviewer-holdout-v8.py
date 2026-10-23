#!/usr/bin/env python3
"""Validate the frozen Codex-only v8 protocol, its revised corpus, and scoring."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
V5_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v5.json"
V8_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v8.json"
V7_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v7.json"
V8_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v8.json"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
V5_TEST_PATH = ROOT / "scripts/ci/test-reviewer-holdout-v5.py"
V7_REPORTS_PATH = ROOT / "benchmarks/reviewer-holdout-v7/reports"
README_PATH = ROOT / "benchmarks/reviewer-holdout-v8/README.md"
BENCHMARK_DOC_PATH = ROOT / "docs/ai-reviewer-benchmark.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
CI_LOCAL_PATH = ROOT / "scripts/ci/ci-local.sh"

EXPECTED_CASES_FILE_SHA256 = "85f072589d5d3f3cb32aa478f8872682f3cff29014d1b06e6d8b4f01d7a8fe97"
EXPECTED_CORPUS_SHA256 = "15a53df7366b229bf76bf1b5f22a7a4e6a8580ee18623397678a5f2022665c86"
EXPECTED_PROTOCOL_SHA256 = "87a9e0b7c6a0b891862d370fb6e260cda0bf7de03e803d14b1ce797f1ddcb1ab"
REVISED_IDS = {"V5-007", "V5-008", "V5-026"}

# Digests of the unnumbered (v2-v7) prompt for a fixed synthetic skill and
# source, recorded before v8 existed. They change only if the pre-v8 prompt
# bytes change, which v8 must never do.
FIXTURE_SKILL = {
    "SKILL.md": "| 1 | Name mismatch | P0 |\n| 3b | Uncaught exception | P0 |\n",
    "scripts/scan.sh": "#!/bin/bash\n",
    "references/pattern-reference.md": "#### 1. Name mismatch\nContract text.\n",
    "references/grep-patterns.md": "Pattern ID lookup contract\n",
}
FIXTURE_SOURCE = (
    "import { test } from '@playwright/test';\n\n"
    "test('a', async () => {\n  await go();\n});\n"
)
FIXTURE_CASE = {
    "id": "fixture",
    "framework": "playwright",
    "source_files": [{"source": "unused", "path": "tests/a.spec.ts"}],
    "labels": [],
}
PRE_V8_PROMPT_SHA256 = {
    "workspace-catalog-only": "d6fddc1731eabf5428f6978afa3b2e2e46355dccce4ea0dfabd0a7258acf10db",
    "template-catalog-only": "8550777bdd8213ab027085cd57866924a9a27e830ce603d949e940f81246301a",
    "workspace-no-skill": "2f2f0ca585a041a5dc1a38fd33aa18df54452016463e2971abd37b3c71adb833",
    "template-no-skill": "436edf7836e6b5ac1238d72f86603818778a7fa03664caecd2527cccceac0a5e",
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


def build_fixture_workspace(root: Path) -> Path:
    skill = root / ".skill/e2e-reviewer"
    for relative, content in FIXTURE_SKILL.items():
        path = skill / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    source = root / "tests/a.spec.ts"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(FIXTURE_SOURCE, encoding="utf-8")
    return skill


def finding(pattern_id: str, severity: str, file: str, line: int) -> dict:
    return {"pattern_id": pattern_id, "severity": severity, "file": file, "line": line}


class ReviewerHoldoutV8Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("reviewer_holdout_v8_runner", RUNNER_PATH)
        cls.comparator = load_module("reviewer_holdout_v8_comparator", COMPARATOR_PATH)
        cls.v5_helpers = load_module("reviewer_holdout_v8_v5_helpers", V5_TEST_PATH)
        cls.v7 = read_json(V7_PROTOCOL_PATH)
        cls.v8 = read_json(V8_PROTOCOL_PATH)
        cls.v5_metadata, cls.v5_cases = cls.runner.load_cases(V5_CASES_PATH)
        cls.v8_metadata, cls.v8_cases = cls.runner.load_cases(V8_CASES_PATH)
        cls.v5_by_id = {case["id"]: case for case in cls.v5_cases}
        cls.v8_by_id = {case["id"]: case for case in cls.v8_cases}

    # Frozen inputs -------------------------------------------------------

    def test_frozen_inputs_and_runner_registration(self) -> None:
        self.assertEqual(
            EXPECTED_CASES_FILE_SHA256,
            hashlib.sha256(V8_CASES_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            EXPECTED_CORPUS_SHA256,
            self.runner.corpus_digest(V8_CASES_PATH, self.v8_cases),
        )
        self.assertEqual(
            EXPECTED_PROTOCOL_SHA256,
            hashlib.sha256(V8_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(self.v8, self.runner.load_protocol(V8_PROTOCOL_PATH))
        self.assertEqual(V8_PROTOCOL_PATH, self.runner.V8_PROTOCOL)
        self.assertEqual(V8_CASES_PATH, self.runner.V8_CASES)
        self.assertEqual(
            {
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
                "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            },
            self.runner.PINNED_LIVE_INPUTS[(V8_CASES_PATH, V8_PROTOCOL_PATH)],
        )
        self.assertEqual(
            {
                "path": "scripts/evals/reviewer-holdout-v8.json",
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
            },
            self.v8["corpus"],
        )
        for id_set in (
            "SUPPORTED_PROTOCOL_IDS",
            "STRICT_MAJORITY_PROTOCOL_IDS",
            "PROMPT_ARM_PROTOCOL_IDS",
            "ARM_COMPARISON_PROTOCOL_IDS",
            "CODEX_ONLY_PROTOCOL_IDS",
        ):
            self.assertIn("reviewer-holdout-v8", getattr(self.runner, id_set), id_set)
        self.assertNotIn("reviewer-holdout-v8", self.runner.PROVIDER_BALANCED_PROTOCOL_IDS)
        # v9-v19 are the only later protocols that share these behaviors;
        # no v2-v7 protocol may join either set.
        self.assertEqual(
            {"reviewer-holdout-v8", "reviewer-holdout-v9", "reviewer-holdout-v10",
             "reviewer-holdout-v11", "reviewer-holdout-v12", "reviewer-holdout-v13",
             "reviewer-holdout-v14", "reviewer-holdout-v15", "reviewer-holdout-v16", "reviewer-holdout-v17", "reviewer-holdout-v18", "reviewer-holdout-v19", "reviewer-holdout-v20", "reviewer-holdout-v21", "reviewer-holdout-v22", "reviewer-holdout-v23", "reviewer-holdout-v24"},
            self.runner.NUMBERED_SOURCE_PROTOCOL_IDS,
        )
        self.assertEqual(
            {"reviewer-holdout-v8", "reviewer-holdout-v9", "reviewer-holdout-v10",
             "reviewer-holdout-v11", "reviewer-holdout-v12", "reviewer-holdout-v13",
             "reviewer-holdout-v14", "reviewer-holdout-v15", "reviewer-holdout-v16", "reviewer-holdout-v17", "reviewer-holdout-v18", "reviewer-holdout-v19", "reviewer-holdout-v20", "reviewer-holdout-v21", "reviewer-holdout-v22", "reviewer-holdout-v23", "reviewer-holdout-v24"},
            self.runner.REVISED_LABEL_PROTOCOL_IDS,
        )
        # v8 runs every scheduled call once; v11-v21 declare a retry policy.
        self.assertIsNone(self.runner.infrastructure_retry_policy(self.v8))
        self.assertEqual(
            {"reviewer-holdout-v11", "reviewer-holdout-v12", "reviewer-holdout-v13",
             "reviewer-holdout-v14", "reviewer-holdout-v15", "reviewer-holdout-v16", "reviewer-holdout-v17", "reviewer-holdout-v18", "reviewer-holdout-v19", "reviewer-holdout-v20", "reviewer-holdout-v21", "reviewer-holdout-v22", "reviewer-holdout-v23", "reviewer-holdout-v24"},
            self.runner.INFRASTRUCTURE_RETRY_PROTOCOL_IDS,
        )

    def test_protocol_changes_only_disclosed_fields_from_v7(self) -> None:
        v7 = copy.deepcopy(self.v7)
        v8 = copy.deepcopy(self.v8)
        self.assertEqual("reviewer-holdout-v8", v8.pop("protocol_id"))
        v7.pop("protocol_id")
        self.assertEqual(self.runner.EXPECTED_V8_SCORING, v8.pop("scoring"))
        v8.pop("corpus")
        schedule = v8["schedule"]
        self.assertEqual((5, 5), (
            schedule.pop("default_repetitions"), schedule.pop("release_repetitions")
        ))
        disclosure = schedule.pop("design_disclosure")
        for key in ("default_repetitions", "release_repetitions", "design_disclosure"):
            v7["schedule"].pop(key)
        for phrase in (
            "v7 full arm",
            "without line numbers",
            "V5-008",
            "V5-007",
            "V5-026",
            "five repetitions",
            "public development evidence",
        ):
            self.assertIn(phrase, disclosure)
        identity = v8["execution_identity"]
        self.assertEqual({"codex": "codex-cli 0.155.1"}, identity.pop("expected_cli_versions"))
        self.assertEqual("minimum", identity["version_policy"])
        v7["execution_identity"].pop("expected_cli_versions")
        # Host matrix, arms, thresholds, seed, and stability are unchanged.
        self.assertEqual(v7, v8)
        self.assertEqual(
            [{"runner": "codex", "model": "gpt-5.6-sol"}], self.v8["host_matrix"]
        )

    def test_protocol_validation_pins_v8_only_fields(self) -> None:
        mutations = {
            "three repetitions": lambda data: data["schedule"].update(
                {"default_repetitions": 3, "release_repetitions": 3}
            ),
            "scoring drift": lambda data: data["scoring"].update(
                {"label_semantics": "exact"}
            ),
            "other corpus": lambda data: data["corpus"].update(
                {"path": "scripts/evals/reviewer-holdout-v5.json"}
            ),
            "extra host": lambda data: data["host_matrix"].append(
                {"runner": "claude", "model": "claude-opus-5"}
            ),
            "exact policy": lambda data: data["execution_identity"].update(
                {"version_policy": "exact"}
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, mutate in mutations.items():
                data = copy.deepcopy(self.v8)
                mutate(data)
                path = Path(temp) / "protocol.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(name), self.assertRaises(ValueError):
                    self.runner.load_protocol(path)
            v7_with_scoring = copy.deepcopy(self.v7)
            v7_with_scoring["scoring"] = self.runner.EXPECTED_V8_SCORING
            path = Path(temp) / "v7.json"
            path.write_text(json.dumps(v7_with_scoring), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.runner.load_protocol(path)

    # Corpus ----------------------------------------------------------------

    def test_corpus_copies_v5_except_three_recorded_label_revisions(self) -> None:
        v5 = read_json(V5_CASES_PATH)
        v8 = read_json(V8_CASES_PATH)
        revisions = v8.pop("label_revisions")
        v5_cases = v5.pop("cases")
        v8_cases = v8.pop("cases")
        self.assertEqual(v5, v8)
        self.assertEqual(REVISED_IDS, {item["finding_id"] for item in revisions})
        for v5_case, v8_case in zip(v5_cases, v8_cases, strict=True):
            self.assertEqual(
                {key: value for key, value in v5_case.items() if key != "labels"},
                {key: value for key, value in v8_case.items() if key != "labels"},
            )
            for v5_label, v8_label in zip(v5_case["labels"], v8_case["labels"], strict=True):
                if v5_label["finding_id"] not in REVISED_IDS:
                    self.assertEqual(v5_label, v8_label)
                    continue
                self.assertEqual(
                    {key: value for key, value in v5_label.items() if key != "kind"},
                    {
                        key: value
                        for key, value in v8_label.items()
                        if key not in {"kind", "reason", "accepted_alternatives"}
                    },
                )
        labels = {
            label["finding_id"]: label
            for case in self.v8_cases
            for label in case["labels"]
        }
        self.assertEqual("fp_guard", labels["V5-008"]["kind"])
        self.assertIn("#13 v2 ownership contract", labels["V5-008"]["reason"])
        self.assertIn("navigation-only POM", labels["V5-008"]["reason"])
        self.assertEqual("finding", labels["V5-007"]["kind"])
        self.assertEqual(("#12", "P0", 14), (
            labels["V5-007"]["pattern_id"],
            labels["V5-007"]["severity"],
            labels["V5-007"]["line"],
        ))
        self.assertEqual(
            [{
                "pattern_id": "#1",
                "severity": "P0",
                "file": "tests/billing.spec.ts",
                "line": 13,
                "source_line": "test('opens the team invoices route', async ({ page }) => {",
            }],
            labels["V5-007"]["accepted_alternatives"],
        )
        self.assertEqual("optional", labels["V5-026"]["kind"])
        by_id = {item["finding_id"]: item for item in revisions}
        self.assertEqual("finding-to-fp-guard", by_id["V5-008"]["change"])
        self.assertEqual("accepted-alternatives-added", by_id["V5-007"]["change"])
        self.assertEqual("finding-to-optional", by_id["V5-026"]["change"])
        for finding_id, revision in by_id.items():
            self.assertEqual(labels[finding_id]["reason"], revision["reason"])

    def test_revised_label_fields_require_a_revised_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(
                ROOT / "scripts/evals/files/holdout-v5",
                root / "files/holdout-v5",
            )
            data = read_json(V5_CASES_PATH)
            data["cases"][0]["labels"][0]["kind"] = "optional"
            path = root / "corpus.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid kind"):
                self.runner.load_cases(path)

            data = read_json(V8_CASES_PATH)
            data["label_revisions"] = [
                item for item in data["label_revisions"]
                if item["finding_id"] != "V5-026"
            ]
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing from label_revisions"):
                self.runner.load_cases(path)

            data = read_json(V8_CASES_PATH)
            alternative = data["cases"][2]["labels"][1]["accepted_alternatives"][0]
            alternative["line"] = 14
            alternative["source_line"] = "await page.goto('/team/invoices');"
            alternative["pattern_id"] = "#12"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicates label location"):
                self.runner.load_cases(path)

    def test_corpus_and_protocol_pair_only_with_each_other(self) -> None:
        self.runner.validate_corpus_protocol_pairing(
            self.v8_metadata, self.v8, EXPECTED_CORPUS_SHA256
        )
        self.runner.validate_corpus_protocol_pairing(self.v5_metadata, self.v7)
        with self.assertRaisesRegex(ValueError, "does not support revised-label"):
            self.runner.validate_corpus_protocol_pairing(self.v8_metadata, self.v7)
        with self.assertRaisesRegex(ValueError, "requires a corpus"):
            self.runner.validate_corpus_protocol_pairing(self.v5_metadata, self.v8)
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            self.runner.validate_corpus_protocol_pairing(
                self.v8_metadata, self.v8, "0" * 64
            )

    # Prompt rendering --------------------------------------------------------

    def test_unnumbered_prompt_bytes_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            skill = build_fixture_workspace(workspace)
            actual = {}
            for profile in ("catalog-only", "no-skill"):
                actual[f"workspace-{profile}"] = hashlib.sha256(
                    self.runner.render_prompt(FIXTURE_CASE, workspace, profile).encode()
                ).hexdigest()
                actual[f"template-{profile}"] = hashlib.sha256(
                    self.runner.render_prompt(
                        FIXTURE_CASE, prompt_profile=profile, legend_skill_dir=skill
                    ).encode()
                ).hexdigest()
                self.assertEqual(
                    self.runner.render_prompt(FIXTURE_CASE, workspace, profile),
                    self.runner.render_prompt(
                        FIXTURE_CASE, workspace, profile, numbered_source_lines=False
                    ),
                )
        self.assertEqual(PRE_V8_PROMPT_SHA256, actual)

    def test_v7_prompt_set_digest_is_unchanged_and_v8_differs(self) -> None:
        corpus = self.runner.corpus_digest(V5_CASES_PATH, self.v5_cases)
        for profile in ("full", "catalog-only", "no-skill"):
            default = self.runner.prompt_set_digest(
                self.v5_cases, corpus, self.runner.DEFAULT_SKILL_DIR, profile
            )
            explicit = self.runner.prompt_set_digest(
                self.v5_cases, corpus, self.runner.DEFAULT_SKILL_DIR, profile,
                numbered_source_lines=False,
            )
            numbered = self.runner.prompt_set_digest(
                self.v5_cases, corpus, self.runner.DEFAULT_SKILL_DIR, profile,
                numbered_source_lines=True,
            )
            self.assertEqual(default, explicit)
            self.assertNotEqual(default, numbered)

    def test_numbered_rendering_matches_nl_ba_for_v8_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            build_fixture_workspace(workspace)
            numbered = self.runner.render_prompt(
                FIXTURE_CASE, workspace, "no-skill", numbered_source_lines=True
            )
            plain = self.runner.render_prompt(FIXTURE_CASE, workspace, "no-skill")
            source = workspace / "tests/a.spec.ts"
            expected_block = self.runner.number_source_lines(FIXTURE_SOURCE)
            if shutil.which("nl"):
                nl_output = subprocess.run(
                    ["nl", "-ba", str(source)],
                    check=True, capture_output=True, text=True,
                ).stdout
                self.assertEqual(nl_output, expected_block)
        self.assertEqual(
            "     1\timport { test } from '@playwright/test';\n"
            "     2\t\n"
            "     3\ttest('a', async () => {\n"
            "     4\t  await go();\n"
            "     5\t});\n",
            expected_block,
        )
        self.assertIn(
            "BEGIN_UNTRUSTED_SOURCE tests/a.spec.ts\n"
            f"{expected_block}END_UNTRUSTED_SOURCE tests/a.spec.ts",
            numbered,
        )
        self.assertIn("The numbers are display-only", numbered)
        self.assertIn("Cite that displayed number as the line", numbered)
        self.assertNotIn("display-only", plain)
        self.assertNotIn("     1\t", plain)

    def test_displayed_numbers_match_every_v8_label_line(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            for case in self.v8_cases:
                workspace = Path(temp) / case["id"]
                workspace.mkdir()
                for source in case["source_files"]:
                    target = workspace / source["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(V8_CASES_PATH.parent / source["source"], target)
                blocks = {
                    source["path"]: self.runner.number_source_lines(
                        (workspace / source["path"]).read_text(encoding="utf-8")
                    )
                    for source in case["source_files"]
                }
                for label in case["labels"]:
                    tuples = [label, *label.get("accepted_alternatives", ())]
                    for item in tuples:
                        line = blocks[item["file"]].splitlines()[item["line"] - 1]
                        number, text = line.split("\t", 1)
                        self.assertEqual(item["line"], int(number))
                        self.assertEqual(item["source_line"], text.strip())

    # Scoring -------------------------------------------------------------

    def test_accepted_alternative_counts_as_one_true_positive(self) -> None:
        case = self.v8_by_id["pw-a03"]
        primary = finding("#12", "P0", "tests/billing.spec.ts", 14)
        alternative = finding("#1", "P0", "tests/billing.spec.ts", 13)
        other = finding("#8a", "P0", "tests/billing.spec.ts", 9)
        for findings in ([primary, other], [alternative, other], [primary, alternative, other]):
            result = self.runner.score(case, findings, revised_labels=True)
            self.assertEqual((2, 0, 0), (result["tp"], result["fp"], result["fn"]))
            self.assertEqual(["V5-006", "V5-007"], result["matched_finding_ids"])
        missed = self.runner.score(case, [other], revised_labels=True)
        self.assertEqual((1, 0, 1), (missed["tp"], missed["fp"], missed["fn"]))
        self.assertEqual(["V5-007"], missed["missed_finding_ids"])

    def test_optional_label_is_never_a_false_positive_or_negative(self) -> None:
        case = self.v8_by_id["cy-a06"]
        optional = finding("#22", "P1", "cypress/e2e/board.cy.ts", 6)
        required = finding("#23", "P2", "cypress/fixtures/summary.json", 3)
        reported = self.runner.score(case, [optional, required], revised_labels=True)
        self.assertEqual((1, 0, 0), (reported["tp"], reported["fp"], reported["fn"]))
        self.assertEqual(["V5-026"], reported["optional_matched_ids"])
        silent = self.runner.score(case, [required], revised_labels=True)
        self.assertEqual((1, 0, 0), (silent["tp"], silent["fp"], silent["fn"]))
        self.assertEqual([], silent["optional_matched_ids"])
        only_optional = self.runner.score(case, [optional], revised_labels=True)
        self.assertEqual((0, 0, 1), (
            only_optional["tp"], only_optional["fp"], only_optional["fn"]
        ))
        self.assertEqual(["V5-027"], only_optional["missed_finding_ids"])

    def test_v5_008_report_is_a_guard_hit(self) -> None:
        case = self.v8_by_id["pw-a04"]
        pom = finding("#13", "P1", "tests/profile.spec.ts", 7)
        banner = finding("#15", "P1", "tests/profile.spec.ts", 9)
        reload = finding("#16", "P1", "tests/profile.spec.ts", 10)
        result = self.runner.score(case, [pom, banner, reload], revised_labels=True)
        self.assertEqual((2, 1, 0), (result["tp"], result["fp"], result["fn"]))
        self.assertEqual(["V5-008"], result["hit_fp_guard_ids"])
        clean = self.runner.score(case, [banner, reload], revised_labels=True)
        self.assertEqual((2, 0, 0), (clean["tp"], clean["fp"], clean["fn"]))
        self.assertEqual([], clean["hit_fp_guard_ids"])

    def synthetic_v8_runs(self, repetitions: int) -> list[dict]:
        """Perfect answers except the three revised labels, which vary per run."""
        runs = []
        for case in self.v8_cases:
            for repetition in range(1, repetitions + 1):
                findings = []
                for label in case["labels"]:
                    if label["kind"] != "finding" or label["finding_id"] == "V5-007":
                        continue
                    findings.append(finding(
                        label["pattern_id"], label["severity"], label["file"], label["line"]
                    ))
                if case["id"] == "pw-a03":
                    # Alternate: primary, primary, alternative, alternative, none.
                    if repetition <= 2:
                        findings.append(finding("#12", "P0", "tests/billing.spec.ts", 14))
                    elif repetition <= 4:
                        findings.append(finding("#1", "P0", "tests/billing.spec.ts", 13))
                if case["id"] == "pw-a04" and repetition <= 3:
                    findings.append(finding("#13", "P1", "tests/profile.spec.ts", 7))
                if case["id"] == "cy-a06" and repetition <= 3:
                    findings.append(finding("#22", "P1", "cypress/e2e/board.cy.ts", 6))
                runs.append({
                    "case": case["id"],
                    "repetition": repetition,
                    "findings": findings,
                    "score": self.runner.score(case, findings, revised_labels=True),
                })
        return runs

    def test_repetitions_and_strict_majority_use_the_revised_label_set(self) -> None:
        self.assertEqual(5, self.v8["schedule"]["default_repetitions"])
        self.assertEqual(5, self.v8["schedule"]["release_repetitions"])
        schedule = self.runner.build_schedule(
            self.v8_cases, 5, self.v8["schedule"]["seed"]
        )
        self.assertEqual(100, len(schedule))
        runs = self.synthetic_v8_runs(5)
        primary = self.runner.primary_metrics(
            self.v8_cases, runs, 5, "strict-majority", revised_labels=True
        )
        self.assertEqual(3, primary["stability"]["required_hits"])
        unique = primary["unique"]
        # 24 v5 finding labels minus V5-008 (guard) and V5-026 (optional).
        self.assertEqual((22, 1, 0), (unique["tp"], unique["fp"], unique["fn"]))
        self.assertEqual(1, unique["stable_guard_hits"])
        self.assertEqual(25, unique["guard_labels"])
        self.assertEqual(1, unique["optional_labels"])
        self.assertEqual(1, unique["stable_optional_matches"])
        self.assertEqual(["V5-026"], unique["stable_optional_matched_ids"])
        p0 = {
            row["finding_id"]: row
            for row in primary["p0_per_label_stability"]["labels"]
        }
        self.assertNotIn("V5-008", p0)
        self.assertNotIn("V5-026", p0)
        self.assertEqual((4, True), (p0["V5-007"]["hits"], p0["V5-007"]["stable"]))
        self.assertEqual(1.0, primary["p0_per_label_stability"]["stable_label_recall"])
        self.assertEqual(1.0, primary["clean_case_specificity"]["value"])
        self.assertEqual(
            "accepted-alternatives-and-optional-v1", primary["label_semantics"]
        )

    def test_comparator_case_rows_use_revised_semantics(self) -> None:
        runs = self.synthetic_v8_runs(5)
        report = {
            "protocol_id": "reviewer-holdout-v8",
            "prompt_profile": "full",
            "runner": "codex",
            "model": "gpt-5.6-sol",
            "primary_metrics": {"stability": {"required_hits": 3}},
            "runs": runs,
        }
        rows = self.comparator.report_case_metric_rows(report, self.v8_cases)
        self.assertEqual({"tp": 2, "fp": 0, "fn": 0}, rows["pw-a03"]["stable"])
        self.assertEqual({"tp": 2, "fp": 1, "fn": 0}, rows["pw-a04"]["stable"])
        self.assertEqual({"tp": 1, "fp": 0, "fn": 0}, rows["cy-a06"]["stable"])
        self.assertEqual(
            (22, 1, 0),
            tuple(sum(row["stable"][name] for row in rows.values()) for name in ("tp", "fp", "fn")),
        )

    def test_v7_scoring_is_unchanged(self) -> None:
        # Synthetic report on the unrevised corpus: the old exact semantics.
        pw_a03 = self.v5_by_id["pw-a03"]
        alternative = self.runner.score(
            pw_a03, [finding("#1", "P0", "tests/billing.spec.ts", 13)]
        )
        self.assertEqual(
            {
                "tp": 0,
                "fp": 1,
                "fn": 2,
                "matched_finding_ids": [],
                "missed_finding_ids": ["V5-006", "V5-007"],
                "hit_fp_guard_ids": [],
            },
            alternative,
        )
        pw_a04 = self.v5_by_id["pw-a04"]
        pom = self.runner.score(pw_a04, [finding("#13", "P1", "tests/profile.spec.ts", 7)])
        self.assertEqual((1, 0, 2), (pom["tp"], pom["fp"], pom["fn"]))
        cy_a06 = self.v5_by_id["cy-a06"]
        silent = self.runner.score(
            cy_a06, [finding("#23", "P2", "cypress/fixtures/summary.json", 3)]
        )
        self.assertEqual(["V5-026"], silent["missed_finding_ids"])
        self.assertNotIn("optional_matched_ids", silent)
        # Committed v7 reports still recompute to their stored scores and metrics.
        for name in ("full-codex.json", "catalog-only-codex.json", "no-skill-codex.json"):
            report = read_json(V7_REPORTS_PATH / name)
            for run in report["runs"]:
                self.assertEqual(
                    run["score"],
                    self.runner.score(self.v5_by_id[run["case"]], run["findings"]),
                )
            self.assertEqual(
                report["primary_metrics"],
                self.runner.primary_metrics(
                    self.v5_cases, report["runs"], report["repetitions"], "strict-majority"
                ),
            )

    def test_single_host_comparator_is_decisive_for_v8(self) -> None:
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
            report["runner_identity"] = "codex-cli 0.155.1"
        by_profile = {report["prompt_profile"]: report for report in reports}
        for step in self.v8["arm_comparison"]["execution_order"]:
            report = by_profile[step["prompt_profile"]]
            report["started_at"] = f"2026-09-26T00:00:0{step['ordinal'] - 1}+00:00"
            report["created_at"] = f"2026-09-26T00:00:0{step['ordinal']}+00:00"
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
                self.v8,
                "b" * 64,
                "public-development",
                "development",
            )
        self.assertEqual("PASS", result["status"])
        self.assertEqual(
            "exact-three-profiles-by-one-host",
            result["metrics"]["comparison_unit"],
        )

    # Documentation ---------------------------------------------------------

    def test_readme_documents_design_and_exact_rerun(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("# Reviewer holdout v8", readme.splitlines()[0])
        for contract in (
            "300 model calls",
            "scripts/evals/reviewer-holdout-v8.json",
            "scripts/evals/reviewer-validation-protocol-v8.json",
            EXPECTED_CASES_FILE_SHA256,
            EXPECTED_CORPUS_SHA256,
            EXPECTED_PROTOCOL_SHA256,
            "codex-cli 0.155.1",
            "V5-007",
            "V5-008",
            "V5-026",
            "--compare-arms",
            'test -z "$(git status --porcelain)"',
            "arm comparison `FAIL`, so no skill-lift claim",
        ):
            self.assertIn(contract, readme)
        self.assertEqual(3, readme.count("--repetitions 5"))
        self.assertEqual(0, readme.count("--repetitions 3"))
        self.assertEqual(4, readme.count('--output "$OUT/'))
        self.assertIn(
            "benchmarks/reviewer-holdout-v8/README.md",
            BENCHMARK_DOC_PATH.read_text(encoding="utf-8"),
        )
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
        unreleased = changelog.split("## [2.0.0]", 1)[1].split("\n## [", 1)[0]
        self.assertIn("### Added", unreleased)
        self.assertIn("reviewer-holdout-v8", unreleased)
        self.assertIn(
            "scripts/ci/test-reviewer-holdout-v8.py",
            CI_LOCAL_PATH.read_text(encoding="utf-8"),
        )

    def test_committed_reports_match_documented_result(self) -> None:
        reports = README_PATH.parent / "reports"
        expected = {
            "full-codex.json": "PASS",
            "catalog-only-codex.json": "PASS",
            "no-skill-codex.json": "FAIL",
            "arm-comparison.json": "FAIL",
        }
        for name, status in expected.items():
            report = read_json(reports / name)
            self.assertEqual(status, report["status"], name)
            self.assertEqual(EXPECTED_PROTOCOL_SHA256, report["protocol_sha256"], name)
        self.assertFalse(read_json(reports / "arm-comparison.json")["skill_lift_claim_eligible"])
        attempt = read_json(README_PATH.parent / "attempts/1/full-codex.json")
        self.assertEqual("INCONCLUSIVE", attempt["status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
