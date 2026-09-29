#!/usr/bin/env python3
"""Validate the Codex-only v9 protocol, its designed corpus, scoring, and recorded run."""

from __future__ import annotations

from collections import Counter
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
V5_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v5.json"
V8_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v8.json"
V9_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v9.json"
V7_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v7.json"
V8_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v8.json"
V9_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v9.json"
V9_FILES_PATH = ROOT / "scripts/evals/files/holdout-v9"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
V5_TEST_PATH = ROOT / "scripts/ci/test-reviewer-holdout-v5.py"
README_PATH = ROOT / "benchmarks/reviewer-holdout-v9/README.md"
BENCHMARK_DOC_PATH = ROOT / "docs/ai-reviewer-benchmark.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
CI_LOCAL_PATH = ROOT / "scripts/ci/ci-local.sh"

EXPECTED_CASES_FILE_SHA256 = "723740ea9eb6defe4951f72f30927570d9f0e259885d1503d25b20ea6e4c3d14"
EXPECTED_CORPUS_SHA256 = "5465a355d2126ecbda3e24822ed4e7ced43676df283a77bbf01ca377591debaf"
EXPECTED_PROTOCOL_SHA256 = "133e7450f0bfecc866ad9e33111012df478f19fd60e05b9d7e88427c2cbb100d"
PROTOCOL_ID = "reviewer-holdout-v9"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finding(pattern_id: str, severity: str, file: str, line: int) -> dict:
    return {"pattern_id": pattern_id, "severity": severity, "file": file, "line": line}


def as_finding(item: dict) -> dict:
    return finding(item["pattern_id"], item["severity"], item["file"], item["line"])


class ReviewerHoldoutV9Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("reviewer_holdout_v9_runner", RUNNER_PATH)
        cls.comparator = load_module("reviewer_holdout_v9_comparator", COMPARATOR_PATH)
        cls.v5_helpers = load_module("reviewer_holdout_v9_v5_helpers", V5_TEST_PATH)
        cls.v7 = read_json(V7_PROTOCOL_PATH)
        cls.v8 = read_json(V8_PROTOCOL_PATH)
        cls.v9 = read_json(V9_PROTOCOL_PATH)
        cls.v5_metadata, cls.v5_cases = cls.runner.load_cases(V5_CASES_PATH)
        cls.v8_metadata, cls.v8_cases = cls.runner.load_cases(V8_CASES_PATH)
        cls.v9_metadata, cls.v9_cases = cls.runner.load_cases(V9_CASES_PATH)
        cls.v9_by_id = {case["id"]: case for case in cls.v9_cases}
        cls.labels = [label for case in cls.v9_cases for label in case["labels"]]
        cls.labels_by_id = {label["finding_id"]: label for label in cls.labels}

    # Frozen inputs -------------------------------------------------------

    def test_frozen_inputs_and_runner_registration(self) -> None:
        self.assertEqual(
            EXPECTED_CASES_FILE_SHA256,
            hashlib.sha256(V9_CASES_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            EXPECTED_CORPUS_SHA256,
            self.runner.corpus_digest(V9_CASES_PATH, self.v9_cases),
        )
        self.assertEqual(
            EXPECTED_PROTOCOL_SHA256,
            hashlib.sha256(V9_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(self.v9, self.runner.load_protocol(V9_PROTOCOL_PATH))
        self.assertEqual(V9_PROTOCOL_PATH, self.runner.V9_PROTOCOL)
        self.assertEqual(V9_CASES_PATH, self.runner.V9_CASES)
        self.assertEqual(
            {
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
                "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            },
            self.runner.PINNED_LIVE_INPUTS[(V9_CASES_PATH, V9_PROTOCOL_PATH)],
        )
        self.assertEqual(
            {
                "path": "scripts/evals/reviewer-holdout-v9.json",
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
            },
            self.v9["corpus"],
        )
        for id_set in (
            "SUPPORTED_PROTOCOL_IDS",
            "STRICT_MAJORITY_PROTOCOL_IDS",
            "PROMPT_ARM_PROTOCOL_IDS",
            "ARM_COMPARISON_PROTOCOL_IDS",
            "CODEX_ONLY_PROTOCOL_IDS",
            "NUMBERED_SOURCE_PROTOCOL_IDS",
            "REVISED_LABEL_PROTOCOL_IDS",
        ):
            self.assertIn(PROTOCOL_ID, getattr(self.runner, id_set), id_set)
        for id_set in (
            "PROVIDER_BALANCED_PROTOCOL_IDS",
            "FULL_ONLY_PROTOCOL_IDS",
            "SUPERSEDED_PROTOCOL_IDS",
            "HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS",
            "SPECIFICITY_PROTOCOL_IDS",
        ):
            self.assertNotIn(PROTOCOL_ID, getattr(self.runner, id_set), id_set)
        # v10, v11-v15 (which reuse the v10 corpus), v16 (which reuses
        # this v9 corpus), and v17 are the only later designed-label protocols.
        self.assertEqual(
            {PROTOCOL_ID, "reviewer-holdout-v10", "reviewer-holdout-v11",
             "reviewer-holdout-v12", "reviewer-holdout-v13", "reviewer-holdout-v14",
             "reviewer-holdout-v15", "reviewer-holdout-v16", "reviewer-holdout-v17", "reviewer-holdout-v18", "reviewer-holdout-v19", "reviewer-holdout-v20", "reviewer-holdout-v21"},
            self.runner.DESIGNED_LABEL_PROTOCOL_IDS,
        )
        self.assertEqual(
            {
                "reviewer-holdout-v8": V8_CASES_PATH,
                PROTOCOL_ID: V9_CASES_PATH,
                "reviewer-holdout-v10": ROOT / "scripts/evals/reviewer-holdout-v10.json",
                "reviewer-holdout-v11": ROOT / "scripts/evals/reviewer-holdout-v10.json",
                "reviewer-holdout-v12": ROOT / "scripts/evals/reviewer-holdout-v10.json",
                "reviewer-holdout-v13": ROOT / "scripts/evals/reviewer-holdout-v10.json",
                "reviewer-holdout-v14": ROOT / "scripts/evals/reviewer-holdout-v10.json",
                "reviewer-holdout-v15": ROOT / "scripts/evals/reviewer-holdout-v10.json",
                "reviewer-holdout-v16": V9_CASES_PATH,
                "reviewer-holdout-v17": ROOT / "scripts/evals/reviewer-holdout-v17.json",
                "reviewer-holdout-v18": ROOT / "scripts/evals/reviewer-holdout-v17.json",
                "reviewer-holdout-v19": ROOT / "scripts/evals/reviewer-holdout-v17.json",
                "reviewer-holdout-v20": ROOT / "scripts/evals/reviewer-holdout-v20.json",
                "reviewer-holdout-v21": ROOT / "scripts/evals/reviewer-holdout-v21.json",
            },
            self.runner.REVISED_LABEL_CORPORA,
        )
        # v9 runs every scheduled call once; only v11-v17 declare a retry policy.
        self.assertIsNone(self.runner.infrastructure_retry_policy(self.v9))
        self.assertEqual("minimum", self.runner.FROZEN_EXECUTION_IDENTITY_POLICIES[PROTOCOL_ID])
        self.assertEqual(
            {"codex": "codex-cli 0.155.1"},
            self.runner.FROZEN_EXECUTION_IDENTITIES[PROTOCOL_ID],
        )

    def test_protocol_changes_only_disclosed_fields_from_v8(self) -> None:
        v8 = copy.deepcopy(self.v8)
        v9 = copy.deepcopy(self.v9)
        self.assertEqual(PROTOCOL_ID, v9.pop("protocol_id"))
        v8.pop("protocol_id")
        v8.pop("corpus")
        v9.pop("corpus")
        disclosure = v9["schedule"].pop("design_disclosure")
        v8["schedule"].pop("design_disclosure")
        for phrase in (
            "ceiling",
            "stable F1 1.000",
            "30 new synthetic cases",
            "semantic-review.md",
            "review-scope.md",
            "reporting.md",
            "no blind double labeling",
            "five repetitions",
            "public development evidence",
        ):
            self.assertIn(phrase, disclosure)
        # Host, arms, scoring, thresholds, seed, stability, and identity are v8's.
        self.assertEqual(v8, v9)
        self.assertEqual(self.runner.EXPECTED_V8_SCORING, self.v9["scoring"])
        self.assertEqual("minimum", self.v9["execution_identity"]["version_policy"])
        self.assertEqual(
            {"codex": "codex-cli 0.155.1"},
            self.v9["execution_identity"]["expected_cli_versions"],
        )
        self.assertEqual(
            [{"runner": "codex", "model": "gpt-5.6-sol"}], self.v9["host_matrix"]
        )

    def test_protocol_validation_pins_v9_fields(self) -> None:
        mutations = {
            "three repetitions": lambda data: data["schedule"].update(
                {"default_repetitions": 3, "release_repetitions": 3}
            ),
            "scoring drift": lambda data: data["scoring"].update(
                {"label_semantics": "exact"}
            ),
            "v8 corpus": lambda data: data["corpus"].update(
                {"path": "scripts/evals/reviewer-holdout-v8.json"}
            ),
            "extra host": lambda data: data["host_matrix"].append(
                {"runner": "claude", "model": "claude-opus-5"}
            ),
            "exact policy": lambda data: data["execution_identity"].update(
                {"version_policy": "exact"}
            ),
            "missing disclosure": lambda data: data["schedule"].update(
                {"design_disclosure": " "}
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, mutate in mutations.items():
                data = copy.deepcopy(self.v9)
                mutate(data)
                path = Path(temp) / "protocol.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(name), self.assertRaises(ValueError):
                    self.runner.load_protocol(path)
            # The v8 protocol still refuses the v9 corpus path.
            v8_on_v9 = copy.deepcopy(self.v8)
            v8_on_v9["corpus"]["path"] = "scripts/evals/reviewer-holdout-v9.json"
            path = Path(temp) / "v8.json"
            path.write_text(json.dumps(v8_on_v9), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be the v8 corpus"):
                self.runner.load_protocol(path)

    # Corpus ----------------------------------------------------------------

    def test_corpus_shape_and_balance(self) -> None:
        self.assertTrue(24 <= len(self.v9_cases) <= 30)
        frameworks = Counter(case["framework"] for case in self.v9_cases)
        self.assertEqual({"playwright", "cypress"}, set(frameworks))
        self.assertLessEqual(abs(frameworks["playwright"] - frameworks["cypress"]), 4)
        self.assertEqual("public-development", self.v9_metadata["corpus_visibility"])
        self.assertNotIn("label_revisions", self.v9_metadata)
        self.assertEqual(
            self.runner.DESIGNED_LABELING_KEYS, set(self.v9_metadata["labeling"])
        )
        self.assertIn("checked by two blind labelers and an arbiter", self.v9_metadata["labeling"]["limitations"])
        kinds = Counter(label["kind"] for label in self.labels)
        self.assertEqual({"finding", "fp_guard", "optional"}, set(kinds))
        guard_share = kinds["fp_guard"] / len(self.labels)
        self.assertTrue(0.35 <= guard_share <= 0.5, guard_share)
        finding_severities = Counter(
            label["severity"] for label in self.labels if label["kind"] == "finding"
        )
        self.assertEqual({"P0", "P1", "P2"}, set(finding_severities))
        clean = [
            case["id"] for case in self.v9_cases
            if {label["kind"] for label in case["labels"]} == {"fp_guard"}
        ]
        self.assertGreaterEqual(len(clean), 2)
        self.assertEqual({"playwright", "cypress"}, {
            self.v9_by_id[case_id]["framework"] for case_id in clean
        })

    def test_every_case_and_label_carries_its_rationale(self) -> None:
        arm_phrases = ("Both arms", "Full arm", "Clean case", "Contract boundary")
        for case in self.v9_cases:
            with self.subTest(case["id"]):
                self.assertRegex(case["id"], r"^v9-(pw|cy)-[0-9]{2}$")
                self.assertEqual(
                    "pw" if case["framework"] == "playwright" else "cy",
                    case["id"].split("-")[1],
                )
                self.assertEqual("public-development-v9", case["split"])
                self.assertTrue(
                    any(phrase in case["design_note"] for phrase in arm_phrases),
                    case["design_note"],
                )
                for source in case["source_files"]:
                    self.assertTrue(
                        source["source"].startswith(f"files/holdout-v9/{case['id']}/")
                    )
        ids = [label["finding_id"] for label in self.labels]
        self.assertEqual([f"V9-{index:03d}" for index in range(1, len(ids) + 1)], sorted(ids))
        for label in self.labels:
            self.assertGreater(len(label["reason"]), 40, label["finding_id"])

    def test_corpus_is_independent_from_v5(self) -> None:
        v5_case_ids = {case["id"] for case in self.v5_cases}
        v5_label_ids = {
            label["finding_id"] for case in self.v5_cases for label in case["labels"]
        }
        v5_sources = {
            (V5_CASES_PATH.parent / source["source"]).read_bytes()
            for case in self.v5_cases
            for source in case["source_files"]
        }
        self.assertFalse(v5_case_ids & set(self.v9_by_id))
        self.assertFalse(v5_label_ids & set(self.labels_by_id))
        for case in self.v9_cases:
            for source in case["source_files"]:
                self.assertNotIn(
                    (V9_CASES_PATH.parent / source["source"]).read_bytes(), v5_sources
                )
        on_disk = sorted(
            path.relative_to(V9_CASES_PATH.parent).as_posix()
            for path in V9_FILES_PATH.rglob("*")
            if path.is_file()
        )
        declared = sorted(
            source["source"] for case in self.v9_cases for source in case["source_files"]
        )
        self.assertEqual(declared, on_disk)

    def test_instance_severities_are_limited_to_documented_rules(self) -> None:
        canonical = self.runner.canonical_severities(self.runner.DEFAULT_SKILL_DIR)
        off_catalog = sorted(
            (label["pattern_id"], label["severity"], label["kind"])
            for label in self.labels
            if label["severity"] != canonical[label["pattern_id"]]
        )
        self.assertEqual(
            [
                ("#1", "P1", "finding"),
                ("#1", "P1", "finding"),
                ("#2", "P1", "finding"),
                ("#23", "P0", "finding"),
                ("#4i", "P0", "optional"),
                ("#4i", "P0", "optional"),
            ],
            off_catalog,
        )
        # v10 added #4k P0 (optional labels only); the v9 corpus does not use it.
        self.assertEqual(
            {"#1": {"P1"}, "#23": {"P0"}, "#2": {"P1"}, "#4i": {"P0"}, "#4k": {"P0"}},
            self.runner.INSTANCE_SEVERITIES,
        )
        reference = (
            self.runner.DEFAULT_SKILL_DIR / "references/pattern-reference.md"
        ).read_text(encoding="utf-8")
        self.assertIn("report #1 at P1", reference)
        self.assertRegex(reference, r"Report the variant this pattern calls worse[^\n]*at P0")
        # Each partial-verification #1 P1 finding has a #1 P0 guard on the same line.
        for label in self.labels:
            if (label["pattern_id"], label["severity"]) == ("#1", "P1"):
                self.assertIn(
                    ("#1", "P0", label["file"], label["line"], "fp_guard"),
                    {
                        (item["pattern_id"], item["severity"], item["file"], item["line"], item["kind"])
                        for item in self.labels
                    },
                )

    def test_designed_corpus_validation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(V9_FILES_PATH, root / "files/holdout-v9")
            shutil.copytree(
                ROOT / "scripts/evals/files/holdout-v5", root / "files/holdout-v5"
            )
            path = root / "corpus.json"
            mutations = {
                "missing design_note": (
                    lambda data: data["cases"][0].pop("design_note"),
                    "missing",
                ),
                "blank design_note": (
                    lambda data: data["cases"][0].update({"design_note": " "}),
                    "design_note",
                ),
                "missing reason": (
                    lambda data: data["cases"][0]["labels"][0].pop("reason"),
                    "missing",
                ),
                "undocumented instance severity": (
                    lambda data: next(
                        label for case in data["cases"] for label in case["labels"]
                        if label["finding_id"] == "V9-011"
                    ).update({"severity": "P0"}),
                    "severity must be P1",
                ),
                "labeling key": (
                    lambda data: data["labeling"].pop("limitations"),
                    "labeling",
                ),
                "label_revisions beside labeling": (
                    lambda data: data.update({"label_revisions": []}),
                    "unknown=",
                ),
                "provenance on a designed case": (
                    lambda data: data["cases"][0].update({"provenance": {}}),
                    "unknown=",
                ),
            }
            for name, (mutate, message) in mutations.items():
                data = read_json(V9_CASES_PATH)
                mutate(data)
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(name), self.assertRaisesRegex(ValueError, message):
                    self.runner.load_cases(path)
            # An instance severity is refused on an exact-label corpus.
            data = read_json(V5_CASES_PATH)
            first = data["cases"][0]["labels"][0]
            self.assertEqual(("#1", "P0"), (first["pattern_id"], first["severity"]))
            first["severity"] = "P1"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "severity must be P0"):
                self.runner.load_cases(path)
            # A design note is refused on an exact-label corpus.
            data = read_json(V5_CASES_PATH)
            data["cases"][0]["design_note"] = "Both arms."
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown="):
                self.runner.load_cases(path)

    def test_corpus_and_protocol_pair_only_with_each_other(self) -> None:
        pairing = self.runner.validate_corpus_protocol_pairing
        pairing(self.v9_metadata, self.v9, EXPECTED_CORPUS_SHA256)
        pairing(self.v8_metadata, self.v8, self.v8["corpus"]["corpus_sha256"])
        pairing(self.v5_metadata, self.v7)
        with self.assertRaisesRegex(ValueError, "requires a corpus that declares labeling"):
            pairing(self.v8_metadata, self.v9)
        with self.assertRaisesRegex(ValueError, "requires a corpus that declares labeling"):
            pairing(self.v5_metadata, self.v9)
        with self.assertRaisesRegex(ValueError, "declares label_revisions"):
            pairing(self.v9_metadata, self.v8)
        with self.assertRaisesRegex(ValueError, "does not support designed-label"):
            pairing(self.v9_metadata, self.v7)
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            pairing(self.v9_metadata, self.v9, "0" * 64)
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            pairing(
                self.v9_metadata,
                self.v9,
                self.runner.corpus_digest(V8_CASES_PATH, self.v8_cases),
            )

    # Prompt rendering --------------------------------------------------------

    def test_displayed_numbers_match_every_v9_label_line(self) -> None:
        for case in self.v9_cases:
            blocks = {
                source["path"]: self.runner.number_source_lines(
                    (V9_CASES_PATH.parent / source["source"]).read_text(encoding="utf-8")
                )
                for source in case["source_files"]
            }
            for label in case["labels"]:
                for item in [label, *label.get("accepted_alternatives", ())]:
                    line = blocks[item["file"]].splitlines()[item["line"] - 1]
                    number, text = line.split("\t", 1)
                    self.assertEqual(item["line"], int(number))
                    self.assertEqual(item["source_line"], text.strip())

    def test_prompts_are_numbered_and_never_leak_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            for case in self.v9_cases:
                workspace = Path(temp) / case["id"]
                skill = workspace / ".skill/e2e-reviewer"
                shutil.copytree(self.runner.DEFAULT_SKILL_DIR, skill)
                for source in case["source_files"]:
                    target = workspace / source["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(V9_CASES_PATH.parent / source["source"], target)
                for profile in ("full", "catalog-only", "no-skill"):
                    prompt = self.runner.render_prompt(
                        case, workspace, profile, numbered_source_lines=True
                    )
                    self.assertIn("Cite that displayed number as the line", prompt)
                    self.assertNotIn(case["design_note"], prompt)
                    self.assertNotIn("V9-", prompt)
                    for label in case["labels"]:
                        self.assertNotIn(label["reason"], prompt)
                full = self.runner.render_prompt(case, workspace, "full", numbered_source_lines=True)
                catalog = self.runner.render_prompt(
                    case, workspace, "catalog-only", numbered_source_lines=True
                )
                self.assertIn("BEGIN_REVIEWER_SKILL references/semantic-review.md", full)
                self.assertNotIn("BEGIN_REVIEWER_SKILL references/semantic-review.md", catalog)
                self.assertIn("BEGIN_REVIEWER_SKILL references/pattern-reference.md", catalog)

    def test_prompt_set_digest_is_numbered_for_v9(self) -> None:
        for profile in ("full", "catalog-only", "no-skill"):
            numbered = self.runner.prompt_set_digest(
                self.v9_cases, EXPECTED_CORPUS_SHA256, self.runner.DEFAULT_SKILL_DIR,
                profile, numbered_source_lines=True,
            )
            plain = self.runner.prompt_set_digest(
                self.v9_cases, EXPECTED_CORPUS_SHA256, self.runner.DEFAULT_SKILL_DIR,
                profile,
            )
            self.assertNotEqual(plain, numbered)

    # Scoring -------------------------------------------------------------

    def label(self, case_id: str, pattern_id: str, severity: str, kind: str) -> dict:
        matches = [
            label for label in self.v9_by_id[case_id]["labels"]
            if (label["pattern_id"], label["severity"], label["kind"])
            == (pattern_id, severity, kind)
        ]
        self.assertEqual(1, len(matches), (case_id, pattern_id, severity, kind))
        return matches[0]

    def test_partial_verification_scores_at_p1_only(self) -> None:
        case = self.v9_by_id["v9-pw-01"]
        partial = self.label("v9-pw-01", "#1", "P1", "finding")
        unverified = self.label("v9-pw-01", "#1", "P0", "finding")
        right = self.runner.score(
            case, [as_finding(partial), as_finding(unverified)], revised_labels=True
        )
        self.assertEqual((2, 0, 0), (right["tp"], right["fp"], right["fn"]))
        wrong = self.runner.score(
            case,
            [
                finding("#1", "P0", partial["file"], partial["line"]),
                as_finding(unverified),
            ],
            revised_labels=True,
        )
        self.assertEqual((1, 1, 1), (wrong["tp"], wrong["fp"], wrong["fn"]))
        self.assertEqual(
            [self.label("v9-pw-01", "#1", "P0", "fp_guard")["finding_id"]],
            wrong["hit_fp_guard_ids"],
        )

    def test_accepted_alternative_and_optional_labels(self) -> None:
        case = self.v9_by_id["v9-pw-05"]
        primary = self.label("v9-pw-05", "#4a", "P0", "finding")
        alternative = primary["accepted_alternatives"][0]
        for findings in ([as_finding(primary)], [as_finding(alternative)],
                         [as_finding(primary), as_finding(alternative)]):
            result = self.runner.score(case, findings, revised_labels=True)
            self.assertEqual((1, 0, 0), (result["tp"], result["fp"], result["fn"]))
        case = self.v9_by_id["v9-cy-13"]
        root = self.label("v9-cy-13", "#23", "P0", "finding")
        optional = next(label for label in case["labels"] if label["kind"] == "optional")
        both = self.runner.score(
            case, [as_finding(root), as_finding(optional)], revised_labels=True
        )
        self.assertEqual((1, 0, 0), (both["tp"], both["fp"], both["fn"]))
        self.assertEqual([optional["finding_id"]], both["optional_matched_ids"])
        usual = self.runner.score(
            case, [finding("#23", "P2", root["file"], root["line"])], revised_labels=True
        )
        self.assertEqual((0, 1, 1), (usual["tp"], usual["fp"], usual["fn"]))

    def test_anchor_guards_penalise_the_wrong_line(self) -> None:
        case = self.v9_by_id["v9-pw-12"]
        field = self.label("v9-pw-12", "#23", "P2", "finding")
        guard = self.label("v9-pw-12", "#23", "P2", "fp_guard")
        wrong = self.runner.score(case, [as_finding(guard)], revised_labels=True)
        self.assertEqual((0, 1, 1), (wrong["tp"], wrong["fp"], wrong["fn"]))
        self.assertEqual([guard["finding_id"]], wrong["hit_fp_guard_ids"])
        self.assertTrue(field["file"].endswith(".json"))

    def synthetic_v9_runs(self, repetitions: int) -> list[dict]:
        """Every finding label in every run; optional labels in a strict majority."""
        runs = []
        for case in self.v9_cases:
            for repetition in range(1, repetitions + 1):
                findings = [
                    as_finding(label) for label in case["labels"]
                    if label["kind"] == "finding"
                    or (label["kind"] == "optional" and repetition <= 3)
                ]
                runs.append({
                    "case": case["id"],
                    "repetition": repetition,
                    "findings": findings,
                    "score": self.runner.score(case, findings, revised_labels=True),
                })
        return runs

    def test_schedule_and_perfect_run_metrics(self) -> None:
        schedule = self.runner.build_schedule(
            self.v9_cases, 5, self.v9["schedule"]["seed"]
        )
        self.assertEqual(len(self.v9_cases) * 5, len(schedule))
        primary = self.runner.primary_metrics(
            self.v9_cases, self.synthetic_v9_runs(5), 5, "strict-majority",
            revised_labels=True,
        )
        kinds = Counter(label["kind"] for label in self.labels)
        unique = primary["unique"]
        self.assertEqual((kinds["finding"], 0, 0), (unique["tp"], unique["fp"], unique["fn"]))
        self.assertEqual(kinds["fp_guard"], unique["guard_labels"])
        self.assertEqual(0, unique["stable_guard_hits"])
        self.assertEqual(kinds["optional"], unique["optional_labels"])
        self.assertEqual(kinds["optional"], unique["stable_optional_matches"])
        p0 = {row["finding_id"] for row in primary["p0_per_label_stability"]["labels"]}
        self.assertEqual(
            {
                label["finding_id"] for label in self.labels
                if label["kind"] == "finding" and label["severity"] == "P0"
            },
            p0,
        )
        self.assertIn(self.label("v9-cy-13", "#23", "P0", "finding")["finding_id"], p0)
        self.assertNotIn(self.label("v9-pw-01", "#1", "P1", "finding")["finding_id"], p0)
        self.assertEqual(1.0, primary["p0_per_label_stability"]["stable_label_recall"])
        self.assertEqual(1.0, primary["clean_case_specificity"]["value"])
        self.assertEqual(
            "accepted-alternatives-and-optional-v1", primary["label_semantics"]
        )

    def test_comparator_case_rows_use_revised_semantics(self) -> None:
        report = {
            "protocol_id": PROTOCOL_ID,
            "prompt_profile": "full",
            "runner": "codex",
            "model": "gpt-5.6-sol",
            "primary_metrics": {"stability": {"required_hits": 3}},
            "runs": self.synthetic_v9_runs(5),
        }
        rows = self.comparator.report_case_metric_rows(report, self.v9_cases)
        self.assertEqual(set(self.v9_by_id), set(rows))
        kinds = Counter(label["kind"] for label in self.labels)
        self.assertEqual(
            (kinds["finding"], 0, 0),
            tuple(
                sum(row["stable"][name] for row in rows.values())
                for name in ("tp", "fp", "fn")
            ),
        )

    def test_single_host_comparator_is_decisive_for_v9(self) -> None:
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
        for step in self.v9["arm_comparison"]["execution_order"]:
            report = by_profile[step["prompt_profile"]]
            report["started_at"] = f"2026-09-27T00:00:0{step['ordinal'] - 1}+00:00"
            report["created_at"] = f"2026-09-27T00:00:0{step['ordinal']}+00:00"
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
                self.v9,
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

    def test_readme_documents_preregistration_and_exact_rerun(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("# Reviewer holdout v9", readme.splitlines()[0])
        calls = len(self.v9_cases) * 5 * 3
        self.assertEqual(450, calls)
        for contract in (
            "arm comparison `FAIL`, so no skill-lift claim",
            f"{calls} model calls",
            "scripts/evals/reviewer-holdout-v9.json",
            "scripts/evals/reviewer-validation-protocol-v9.json",
            EXPECTED_CASES_FILE_SHA256,
            EXPECTED_CORPUS_SHA256,
            EXPECTED_PROTOCOL_SHA256,
            "codex-cli 0.155.1",
            "--compare-arms",
            'test -z "$(git status --porcelain)"',
            "stable F1 1.000",
        ):
            self.assertIn(contract, readme)
        for case in self.v9_cases:
            self.assertIn(f"`{case['id']}`", readme)
        self.assertEqual(3, readme.count("--repetitions 5"))
        self.assertEqual(0, readme.count("--repetitions 3"))
        self.assertEqual(4, readme.count('--output "$OUT/'))
        self.assertEqual(3, len(re.findall(r"--arm (full|catalog-only|no-skill) ", readme)))
        self.assertIn(
            "benchmarks/reviewer-holdout-v9/README.md",
            BENCHMARK_DOC_PATH.read_text(encoding="utf-8"),
        )
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
        unreleased = changelog.split("## [2.0.0]", 1)[1].split("\n## [", 1)[0]
        self.assertIn("### Added", unreleased)
        self.assertIn(PROTOCOL_ID, unreleased)
        self.assertIn(
            "scripts/ci/test-reviewer-holdout-v9.py",
            CI_LOCAL_PATH.read_text(encoding="utf-8"),
        )

    def test_committed_reports_match_documented_result(self) -> None:
        reports = README_PATH.parent / "reports"
        for name in ("full-codex.json", "catalog-only-codex.json", "no-skill-codex.json", "arm-comparison.json"):
            report = read_json(reports / name)
            self.assertEqual("FAIL", report["status"], name)
            self.assertEqual(EXPECTED_PROTOCOL_SHA256, report["protocol_sha256"], name)
        comparison = read_json(reports / "arm-comparison.json")
        self.assertFalse(comparison["skill_lift_claim_eligible"])
        readme = README_PATH.read_text(encoding="utf-8")
        for arm in ("full", "catalog-only", "no-skill"):
            unique = read_json(reports / f"{arm}-codex.json")["primary_metrics"]["unique"]
            self.assertIn(
                f"{unique['precision']:.3f} / {unique['recall']:.3f} / {unique['f1']:.3f}", readme
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
