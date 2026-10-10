#!/usr/bin/env python3
"""Validate the preregistered Codex-only v10 protocol, its designed corpus, and scoring."""

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
V10_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v10.json"
V7_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v7.json"
V8_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v8.json"
V9_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v9.json"
V10_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v10.json"
V5_FILES_PATH = ROOT / "scripts/evals/files/holdout-v5"
V9_FILES_PATH = ROOT / "scripts/evals/files/holdout-v9"
V10_FILES_PATH = ROOT / "scripts/evals/files/holdout-v10"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
V5_TEST_PATH = ROOT / "scripts/ci/test-reviewer-holdout-v5.py"
README_PATH = ROOT / "benchmarks/reviewer-holdout-v10/README.md"
BENCHMARK_DOC_PATH = ROOT / "docs/ai-reviewer-benchmark.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
CI_LOCAL_PATH = ROOT / "scripts/ci/ci-local.sh"

EXPECTED_CASES_FILE_SHA256 = "6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e"
EXPECTED_CORPUS_SHA256 = "672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d"
EXPECTED_PROTOCOL_SHA256 = "186680ad624f9ae40ff0b652ee4949322fb6ccfac5e5426a4b7c182278f33c39"
PROTOCOL_ID = "reviewer-holdout-v10"

# Cases whose verdict hinges on a documented severity exception or boundary.
SEVERITY_CASES = {
    "v10-pw-01", "v10-pw-02", "v10-pw-03", "v10-pw-04", "v10-pw-05", "v10-pw-06",
    "v10-cy-01", "v10-cy-02", "v10-cy-03", "v10-cy-04", "v10-cy-05",
}
# Cases whose deciding rule lives only in the full arm's workflow references.
WORKFLOW_CASES = {
    "v10-pw-07", "v10-pw-08", "v10-pw-09", "v10-pw-10", "v10-pw-11",
    "v10-cy-05", "v10-cy-06", "v10-cy-07", "v10-cy-08", "v10-cy-09", "v10-cy-10",
}
REFERENCE_CITATION = re.compile(
    r"(?:pattern-reference|semantic-review|review-scope|reporting|scanner-workflow|"
    r"verification-rules)\.md|SKILL\.md"
)


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


class ReviewerHoldoutV10Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("reviewer_holdout_v10_runner", RUNNER_PATH)
        cls.comparator = load_module("reviewer_holdout_v10_comparator", COMPARATOR_PATH)
        cls.v5_helpers = load_module("reviewer_holdout_v10_v5_helpers", V5_TEST_PATH)
        cls.v7 = read_json(V7_PROTOCOL_PATH)
        cls.v8 = read_json(V8_PROTOCOL_PATH)
        cls.v9 = read_json(V9_PROTOCOL_PATH)
        cls.v10 = read_json(V10_PROTOCOL_PATH)
        cls.v5_metadata, cls.v5_cases = cls.runner.load_cases(V5_CASES_PATH)
        cls.v8_metadata, cls.v8_cases = cls.runner.load_cases(V8_CASES_PATH)
        cls.v9_metadata, cls.v9_cases = cls.runner.load_cases(V9_CASES_PATH)
        cls.v10_metadata, cls.v10_cases = cls.runner.load_cases(V10_CASES_PATH)
        cls.v10_by_id = {case["id"]: case for case in cls.v10_cases}
        cls.labels = [label for case in cls.v10_cases for label in case["labels"]]
        cls.labels_by_id = {label["finding_id"]: label for label in cls.labels}

    # Frozen inputs -------------------------------------------------------

    def test_frozen_inputs_and_runner_registration(self) -> None:
        self.assertEqual(
            EXPECTED_CASES_FILE_SHA256,
            hashlib.sha256(V10_CASES_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            EXPECTED_CORPUS_SHA256,
            self.runner.corpus_digest(V10_CASES_PATH, self.v10_cases),
        )
        self.assertEqual(
            EXPECTED_PROTOCOL_SHA256,
            hashlib.sha256(V10_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(self.v10, self.runner.load_protocol(V10_PROTOCOL_PATH))
        self.assertEqual(V10_PROTOCOL_PATH, self.runner.V10_PROTOCOL)
        self.assertEqual(V10_CASES_PATH, self.runner.V10_CASES)
        self.assertEqual(
            {
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
                "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            },
            self.runner.PINNED_LIVE_INPUTS[(V10_CASES_PATH, V10_PROTOCOL_PATH)],
        )
        self.assertEqual(
            {
                "path": "scripts/evals/reviewer-holdout-v10.json",
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
            },
            self.v10["corpus"],
        )
        for id_set in (
            "SUPPORTED_PROTOCOL_IDS",
            "STRICT_MAJORITY_PROTOCOL_IDS",
            "PROMPT_ARM_PROTOCOL_IDS",
            "ARM_COMPARISON_PROTOCOL_IDS",
            "CODEX_ONLY_PROTOCOL_IDS",
            "NUMBERED_SOURCE_PROTOCOL_IDS",
            "REVISED_LABEL_PROTOCOL_IDS",
            "DESIGNED_LABEL_PROTOCOL_IDS",
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
        # v11 through v15 reuse this corpus; v16 reuses v9's, and v17 has its own.
        self.assertEqual(
            {"reviewer-holdout-v9", PROTOCOL_ID, "reviewer-holdout-v11",
             "reviewer-holdout-v12", "reviewer-holdout-v13", "reviewer-holdout-v14",
             "reviewer-holdout-v15", "reviewer-holdout-v16", "reviewer-holdout-v17", "reviewer-holdout-v18", "reviewer-holdout-v19", "reviewer-holdout-v20", "reviewer-holdout-v21"},
            self.runner.DESIGNED_LABEL_PROTOCOL_IDS,
        )
        self.assertEqual(
            {
                "reviewer-holdout-v8": V8_CASES_PATH,
                "reviewer-holdout-v9": V9_CASES_PATH,
                PROTOCOL_ID: V10_CASES_PATH,
                "reviewer-holdout-v11": V10_CASES_PATH,
                "reviewer-holdout-v12": V10_CASES_PATH,
                "reviewer-holdout-v13": V10_CASES_PATH,
                "reviewer-holdout-v14": V10_CASES_PATH,
                "reviewer-holdout-v15": V10_CASES_PATH,
                "reviewer-holdout-v16": V9_CASES_PATH,
                "reviewer-holdout-v17": ROOT / "scripts/evals/reviewer-holdout-v17.json",
                "reviewer-holdout-v18": ROOT / "scripts/evals/reviewer-holdout-v17.json",
                "reviewer-holdout-v19": ROOT / "scripts/evals/reviewer-holdout-v17.json",
                "reviewer-holdout-v20": ROOT / "scripts/evals/reviewer-holdout-v20.json",
                "reviewer-holdout-v21": ROOT / "scripts/evals/reviewer-holdout-v21.json",
            },
            self.runner.REVISED_LABEL_CORPORA,
        )
        self.assertEqual(
            {
                "reviewer-holdout-v11": PROTOCOL_ID,
                "reviewer-holdout-v12": PROTOCOL_ID,
                "reviewer-holdout-v13": PROTOCOL_ID,
                "reviewer-holdout-v14": PROTOCOL_ID,
                "reviewer-holdout-v15": PROTOCOL_ID,
                "reviewer-holdout-v16": "reviewer-holdout-v9",
                "reviewer-holdout-v18": "reviewer-holdout-v17",
                "reviewer-holdout-v19": "reviewer-holdout-v17",
            },
            self.runner.SHARED_CORPUS_PROTOCOLS,
        )
        # v10 runs every scheduled call once; only v11-v16 declare a retry policy.
        self.assertIsNone(self.runner.infrastructure_retry_policy(self.v10))
        self.assertNotIn(PROTOCOL_ID, self.runner.INFRASTRUCTURE_RETRY_PROTOCOL_IDS)
        self.assertEqual("minimum", self.runner.FROZEN_EXECUTION_IDENTITY_POLICIES[PROTOCOL_ID])
        self.assertEqual(
            {"claude": "Claude Code 2.1.281"},
            self.runner.FROZEN_EXECUTION_IDENTITIES[PROTOCOL_ID],
        )
        self.assertEqual(
            {"runner": "claude", "model": "claude-opus-5"},
            self.runner.REVISED_LABEL_HOSTS[PROTOCOL_ID],
        )

    def test_protocol_changes_only_disclosed_fields_from_v9(self) -> None:
        v9 = copy.deepcopy(self.v9)
        v10 = copy.deepcopy(self.v10)
        self.assertEqual(PROTOCOL_ID, v10.pop("protocol_id"))
        v9.pop("protocol_id")
        v9.pop("corpus")
        v10.pop("corpus")
        disclosure = v10["schedule"].pop("design_disclosure")
        v9["schedule"].pop("design_disclosure")
        for phrase in (
            "after reviewer holdout v9 ran",
            "30 new synthetic cases",
            "15 Playwright, 15 Cypress",
            "severity exception",
            "semantic-review.md",
            "review-scope.md",
            "reporting.md",
            "without reading any v9 run report",
            "checked by two blind model labelers",
            "five repetitions",
            "public development evidence",
            "moved from Codex gpt-5.6-sol to Claude claude-opus-5",
            "claude_permission_mode off",
        ):
            self.assertIn(phrase, disclosure)
        # Arms, scoring, thresholds, seed, and stability are v9's. Only the
        # disclosed host move changes the host, the identity, and the fields
        # that name the host.
        def host_neutral(protocol: dict) -> dict:
            protocol = copy.deepcopy(protocol)
            protocol.pop("host_matrix")
            protocol.pop("execution_identity")
            for step in protocol["arm_comparison"]["execution_order"]:
                step.pop("runner")
                step.pop("model")
            protocol["cross_host_decision"].pop("aggregation_intent", None)
            return protocol
        self.assertEqual(host_neutral(v9), host_neutral(v10))
        v9_identity = dict(self.v9["execution_identity"])
        v10_identity = dict(self.v10["execution_identity"])
        self.assertEqual("off", v10_identity.pop("claude_permission_mode"))
        v9_identity.pop("expected_cli_versions")
        v10_identity.pop("expected_cli_versions")
        self.assertEqual(v9_identity, v10_identity)
        self.assertEqual(list(self.v9), list(self.v10))
        self.assertEqual(self.runner.EXPECTED_V8_SCORING, self.v10["scoring"])
        self.assertEqual("minimum", self.v10["execution_identity"]["version_policy"])
        self.assertEqual(
            {"claude": "Claude Code 2.1.281"},
            self.v10["execution_identity"]["expected_cli_versions"],
        )
        self.assertEqual(
            [{"runner": "claude", "model": "claude-opus-5"}], self.v10["host_matrix"]
        )
        self.assertEqual(5, self.v10["schedule"]["default_repetitions"])
        self.assertEqual(20260801, self.v10["schedule"]["seed"])

    def test_protocol_validation_pins_v10_fields(self) -> None:
        mutations = {
            "three repetitions": lambda data: data["schedule"].update(
                {"default_repetitions": 3, "release_repetitions": 3}
            ),
            "scoring drift": lambda data: data["scoring"].update(
                {"label_semantics": "exact"}
            ),
            "v9 corpus": lambda data: data["corpus"].update(
                {"path": "scripts/evals/reviewer-holdout-v9.json"}
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
                data = copy.deepcopy(self.v10)
                mutate(data)
                path = Path(temp) / "protocol.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(name), self.assertRaises(ValueError):
                    self.runner.load_protocol(path)
            # The v9 protocol still refuses the v10 corpus path.
            v9_on_v10 = copy.deepcopy(self.v9)
            v9_on_v10["corpus"]["path"] = "scripts/evals/reviewer-holdout-v10.json"
            path = Path(temp) / "v9.json"
            path.write_text(json.dumps(v9_on_v10), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be the v9 corpus"):
                self.runner.load_protocol(path)
            v10_on_v9 = copy.deepcopy(self.v10)
            v10_on_v9["corpus"]["path"] = "scripts/evals/reviewer-holdout-v9.json"
            path = Path(temp) / "v10.json"
            path.write_text(json.dumps(v10_on_v9), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be the v10 corpus"):
                self.runner.load_protocol(path)

    def test_earlier_protocols_are_unchanged(self) -> None:
        # The v10 registration must not move any frozen v8/v9 input.
        for (cases, protocol), expected in (
            (
                (V8_CASES_PATH, V8_PROTOCOL_PATH),
                self.runner.PINNED_LIVE_INPUTS[(V8_CASES_PATH, V8_PROTOCOL_PATH)],
            ),
            (
                (V9_CASES_PATH, V9_PROTOCOL_PATH),
                self.runner.PINNED_LIVE_INPUTS[(V9_CASES_PATH, V9_PROTOCOL_PATH)],
            ),
        ):
            self.assertEqual(
                expected["cases_file_sha256"], hashlib.sha256(cases.read_bytes()).hexdigest()
            )
            self.assertEqual(
                expected["protocol_sha256"], hashlib.sha256(protocol.read_bytes()).hexdigest()
            )
        # Numbered prompts stay limited to v8-v16; earlier protocols keep plain sources.
        self.assertEqual(
            {"reviewer-holdout-v8", "reviewer-holdout-v9", PROTOCOL_ID,
             "reviewer-holdout-v11", "reviewer-holdout-v12", "reviewer-holdout-v13",
             "reviewer-holdout-v14", "reviewer-holdout-v15", "reviewer-holdout-v16", "reviewer-holdout-v17", "reviewer-holdout-v18", "reviewer-holdout-v19", "reviewer-holdout-v20", "reviewer-holdout-v21"},
            self.runner.NUMBERED_SOURCE_PROTOCOL_IDS,
        )

    # Corpus ----------------------------------------------------------------

    def test_corpus_shape_and_balance(self) -> None:
        self.assertEqual(30, len(self.v10_cases))
        frameworks = Counter(case["framework"] for case in self.v10_cases)
        self.assertEqual({"playwright": 15, "cypress": 15}, dict(frameworks))
        self.assertEqual("public-development", self.v10_metadata["corpus_visibility"])
        self.assertNotIn("label_revisions", self.v10_metadata)
        self.assertEqual(
            self.runner.DESIGNED_LABELING_KEYS, set(self.v10_metadata["labeling"])
        )
        labeling = self.v10_metadata["labeling"]
        self.assertIn("Single-author", labeling["procedure"])
        self.assertIn("Blind double labeling is pending", labeling["procedure"])
        self.assertIn("checked by two blind labelers and an arbiter", labeling["limitations"])
        kinds = Counter(label["kind"] for label in self.labels)
        self.assertEqual({"finding", "fp_guard", "optional"}, set(kinds))
        guard_share = kinds["fp_guard"] / len(self.labels)
        self.assertTrue(0.35 <= guard_share <= 0.47, guard_share)
        finding_severities = Counter(
            label["severity"] for label in self.labels if label["kind"] == "finding"
        )
        self.assertEqual({"P0", "P1", "P2"}, set(finding_severities))
        clean = [
            case["id"] for case in self.v10_cases
            if {label["kind"] for label in case["labels"]} == {"fp_guard"}
        ]
        self.assertGreaterEqual(len(clean), 3)
        self.assertEqual({"playwright", "cypress"}, {
            self.v10_by_id[case_id]["framework"] for case_id in clean
        })
        self.assertTrue(SEVERITY_CASES <= set(self.v10_by_id))
        self.assertTrue(WORKFLOW_CASES <= set(self.v10_by_id))
        self.assertGreaterEqual(len(SEVERITY_CASES), 10)
        self.assertGreaterEqual(len(WORKFLOW_CASES), 10)

    def test_every_case_and_label_carries_its_rationale(self) -> None:
        arm_phrases = ("Both arms", "Full arm", "Clean case", "Contract boundary")
        for case in self.v10_cases:
            with self.subTest(case["id"]):
                self.assertRegex(case["id"], r"^v10-(pw|cy)-[0-9]{2}$")
                self.assertEqual(
                    "pw" if case["framework"] == "playwright" else "cy",
                    case["id"].split("-")[1],
                )
                self.assertEqual("public-development-v10", case["split"])
                self.assertTrue(
                    any(phrase in case["design_note"] for phrase in arm_phrases),
                    case["design_note"],
                )
                for source in case["source_files"]:
                    self.assertTrue(
                        source["source"].startswith(f"files/holdout-v10/{case['id']}/")
                    )
        ids = [label["finding_id"] for label in self.labels]
        self.assertEqual([f"V10-{index:03d}" for index in range(1, len(ids) + 1)], sorted(ids))
        for label in self.labels:
            with self.subTest(label["finding_id"]):
                self.assertGreater(len(label["reason"]), 40)
                # Every reason cites the reference file whose rule decides it.
                self.assertRegex(label["reason"], REFERENCE_CITATION)
        for case_id in WORKFLOW_CASES:
            self.assertRegex(
                self.v10_by_id[case_id]["design_note"],
                r"semantic-review\.md|review-scope\.md|reporting\.md|scanner-workflow\.md|SKILL\.md",
                case_id,
            )

    def test_corpus_is_independent_from_v5_and_v9(self) -> None:
        earlier = [(V5_CASES_PATH, self.v5_cases), (V9_CASES_PATH, self.v9_cases)]
        earlier_ids = {case["id"] for _, cases in earlier for case in cases}
        earlier_label_ids = {
            label["finding_id"] for _, cases in earlier for case in cases
            for label in case["labels"]
        }
        self.assertFalse(earlier_ids & set(self.v10_by_id))
        self.assertFalse(earlier_label_ids & set(self.labels_by_id))
        earlier_sources = {
            (path.parent / source["source"]).read_bytes()
            for path, cases in earlier
            for case in cases
            for source in case["source_files"]
        }
        for case in self.v10_cases:
            for source in case["source_files"]:
                self.assertNotIn(
                    (V10_CASES_PATH.parent / source["source"]).read_bytes(), earlier_sources
                )

        def spec_names(root: Path) -> set[str]:
            return {
                path.name for path in root.rglob("*")
                if path.is_file() and re.search(r"\.(spec|cy)\.[jt]sx?$", path.name)
            }

        self.assertFalse(
            spec_names(V10_FILES_PATH) & (spec_names(V5_FILES_PATH) | spec_names(V9_FILES_PATH))
        )

        # No distinctive source line is copied from v5 or v9; imports and
        # framework boilerplate are the only shared lines.
        def distinctive(text: str) -> set[str]:
            return {
                line.strip() for line in text.splitlines()
                if len(line.strip()) >= 30
                and not line.strip().startswith(("import ", "export default ", "constructor("))
            }

        earlier_lines: set[str] = set()
        for root in (V5_FILES_PATH, V9_FILES_PATH):
            for path in root.rglob("*"):
                if path.is_file():
                    earlier_lines |= distinctive(path.read_text(encoding="utf-8"))
        for path in V10_FILES_PATH.rglob("*"):
            if path.is_file():
                shared = distinctive(path.read_text(encoding="utf-8")) & earlier_lines
                self.assertFalse(shared, (path, shared))

        on_disk = sorted(
            path.relative_to(V10_CASES_PATH.parent).as_posix()
            for path in V10_FILES_PATH.rglob("*")
            if path.is_file()
        )
        declared = sorted(
            source["source"] for case in self.v10_cases for source in case["source_files"]
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
                ("#1", "P1", "fp_guard"),
                ("#1", "P1", "fp_guard"),
                ("#2", "P1", "finding"),
                ("#2", "P1", "fp_guard"),
                ("#23", "P0", "finding"),
                ("#23", "P0", "fp_guard"),
                ("#4k", "P0", "optional"),
            ],
            off_catalog,
        )
        self.assertEqual(
            {"#1": {"P1"}, "#23": {"P0"}, "#2": {"P1"}, "#4i": {"P0"}, "#4k": {"P0"}},
            self.runner.INSTANCE_SEVERITIES,
        )
        skill = self.runner.DEFAULT_SKILL_DIR
        reference = (skill / "references/pattern-reference.md").read_text(encoding="utf-8")
        reporting = (skill / "references/reporting.md").read_text(encoding="utf-8")
        self.assertIn("report #1 at P1", reference)
        self.assertRegex(reference, r"Report the variant this pattern calls worse[^\n]*at P0")
        # #4k P0 basis: the catalog's own framing plus the reporting.md raise rule.
        self.assertIn("with the silent-always-pass family", reference)
        self.assertIn(
            "an instance can be reported higher when it meets the P0 definition outright",
            reporting,
        )
        self.assertIn("only a second promised effect goes unchecked, that is P1", reporting)
        tuples = {
            (item["pattern_id"], item["severity"], item["file"], item["line"], item["kind"])
            for item in self.labels
        }
        # Each off-catalog finding has a guard at the catalog severity on its line.
        for label in self.labels:
            if label["kind"] != "finding":
                continue
            if label["severity"] == canonical[label["pattern_id"]]:
                continue
            self.assertIn(
                (label["pattern_id"], canonical[label["pattern_id"]], label["file"],
                 label["line"], "fp_guard"),
                tuples,
                label["finding_id"],
            )
        # One label keeps one severity: no alternative changes it.
        for label in self.labels:
            for alternative in label.get("accepted_alternatives", ()):
                self.assertEqual(label["severity"], alternative["severity"])

    def test_severity_cases_pair_each_boundary_on_one_line(self) -> None:
        for case_id in sorted(SEVERITY_CASES - {"v10-cy-04"}):
            with self.subTest(case_id):
                by_line: dict[tuple[str, int], set[tuple[str, str]]] = {}
                for label in self.v10_by_id[case_id]["labels"]:
                    by_line.setdefault((label["file"], label["line"]), set()).add(
                        (label["kind"], label["severity"])
                    )
                self.assertTrue(
                    any(
                        any(kind == "finding" for kind, _ in entries)
                        and len({severity for _, severity in entries}) > 1
                        for entries in by_line.values()
                    ),
                    by_line,
                )
        # #12 has no documented non-P0 severity: its boundary is the same
        # pattern at P0 on the navigation the sign-in page cannot satisfy.
        rota = self.v10_by_id["v10-cy-04"]["labels"]
        self.assertEqual(
            {("finding", "#12", "P0"), ("fp_guard", "#12", "P0")},
            {(label["kind"], label["pattern_id"], label["severity"]) for label in rota},
        )

    def test_designed_corpus_validation_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(V10_FILES_PATH, root / "files/holdout-v10")
            shutil.copytree(V5_FILES_PATH, root / "files/holdout-v5")
            path = root / "corpus.json"
            first_10a = next(
                label["finding_id"] for label in self.labels if label["pattern_id"] == "#10a"
            )
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
                        if label["finding_id"] == first_10a
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
                "source line drift": (
                    lambda data: data["cases"][0]["labels"][0].update({"line": 1}),
                    "source_line does not match",
                ),
            }
            for name, (mutate, message) in mutations.items():
                data = read_json(V10_CASES_PATH)
                mutate(data)
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(name), self.assertRaisesRegex(ValueError, message):
                    self.runner.load_cases(path)
            # The #4k P0 instance severity is refused on an exact-label corpus.
            data = read_json(V5_CASES_PATH)
            data["cases"][0]["labels"][0].update({"pattern_id": "#4k", "severity": "P0"})
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "severity must be P1"):
                self.runner.load_cases(path)

    def test_corpus_and_protocol_pair_only_with_each_other(self) -> None:
        pairing = self.runner.validate_corpus_protocol_pairing
        pairing(self.v10_metadata, self.v10, EXPECTED_CORPUS_SHA256)
        pairing(self.v9_metadata, self.v9, self.v9["corpus"]["corpus_sha256"])
        with self.assertRaisesRegex(ValueError, "requires a corpus that declares labeling"):
            pairing(self.v8_metadata, self.v10)
        with self.assertRaisesRegex(ValueError, "requires a corpus that declares labeling"):
            pairing(self.v5_metadata, self.v10)
        with self.assertRaisesRegex(ValueError, "declares label_revisions"):
            pairing(self.v10_metadata, self.v8)
        with self.assertRaisesRegex(ValueError, "does not support designed-label"):
            pairing(self.v10_metadata, self.v7)
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            pairing(self.v10_metadata, self.v10, "0" * 64)
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            pairing(
                self.v9_metadata,
                self.v10,
                self.runner.corpus_digest(V9_CASES_PATH, self.v9_cases),
            )
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            pairing(self.v10_metadata, self.v9, EXPECTED_CORPUS_SHA256)

    # Prompt rendering --------------------------------------------------------

    def test_displayed_numbers_match_every_v10_label_line(self) -> None:
        for case in self.v10_cases:
            blocks = {
                source["path"]: self.runner.number_source_lines(
                    (V10_CASES_PATH.parent / source["source"]).read_text(encoding="utf-8")
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
            for case in self.v10_cases:
                workspace = Path(temp) / case["id"]
                skill = workspace / ".skill/e2e-reviewer"
                shutil.copytree(self.runner.DEFAULT_SKILL_DIR, skill)
                for source in case["source_files"]:
                    target = workspace / source["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(V10_CASES_PATH.parent / source["source"], target)
                for profile in ("full", "catalog-only", "no-skill"):
                    prompt = self.runner.render_prompt(
                        case, workspace, profile, numbered_source_lines=True
                    )
                    self.assertIn("Cite that displayed number as the line", prompt)
                    self.assertNotIn(case["design_note"], prompt)
                    self.assertNotIn("V10-", prompt)
                    self.assertNotIn("holdout-v10", prompt)
                    self.assertNotIn(case["id"], prompt)
                    for label in case["labels"]:
                        self.assertNotIn(label["reason"], prompt)
                full = self.runner.render_prompt(case, workspace, "full", numbered_source_lines=True)
                catalog = self.runner.render_prompt(
                    case, workspace, "catalog-only", numbered_source_lines=True
                )
                no_skill = self.runner.render_prompt(
                    case, workspace, "no-skill", numbered_source_lines=True
                )
                for reference in (
                    "semantic-review.md", "review-scope.md", "reporting.md",
                    "scanner-workflow.md", "verification-rules.md",
                ):
                    self.assertIn(f"BEGIN_REVIEWER_SKILL references/{reference}", full)
                    self.assertNotIn(f"BEGIN_REVIEWER_SKILL references/{reference}", catalog)
                self.assertIn("BEGIN_REVIEWER_SKILL references/pattern-reference.md", catalog)
                self.assertNotIn("BEGIN_REVIEWER_SKILL", no_skill)
        # The corpus sources themselves carry no label vocabulary.
        for path in V10_FILES_PATH.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for marker in ("V10-", "fp_guard", "design_note", "holdout"):
                    self.assertNotIn(marker, text, path)

    def test_prompt_set_digest_is_numbered_for_v10(self) -> None:
        for profile in ("full", "catalog-only", "no-skill"):
            numbered = self.runner.prompt_set_digest(
                self.v10_cases, EXPECTED_CORPUS_SHA256, self.runner.DEFAULT_SKILL_DIR,
                profile, numbered_source_lines=True,
            )
            plain = self.runner.prompt_set_digest(
                self.v10_cases, EXPECTED_CORPUS_SHA256, self.runner.DEFAULT_SKILL_DIR,
                profile,
            )
            self.assertNotEqual(plain, numbered)

    # Scoring -------------------------------------------------------------

    def label(self, case_id: str, pattern_id: str, severity: str, kind: str) -> dict:
        matches = [
            label for label in self.v10_by_id[case_id]["labels"]
            if (label["pattern_id"], label["severity"], label["kind"])
            == (pattern_id, severity, kind)
        ]
        self.assertEqual(1, len(matches), (case_id, pattern_id, severity, kind))
        return matches[0]

    def test_wrong_severity_costs_a_false_positive_and_a_miss(self) -> None:
        case = self.v10_by_id["v10-cy-05"]
        partial = self.label("v10-cy-05", "#2", "P1", "finding")
        unverified = self.label("v10-cy-05", "#2", "P0", "finding")
        right = self.runner.score(
            case, [as_finding(partial), as_finding(unverified)], revised_labels=True
        )
        self.assertEqual((2, 0, 0), (right["tp"], right["fp"], right["fn"]))
        wrong = self.runner.score(
            case,
            [finding("#2", "P0", partial["file"], partial["line"]), as_finding(unverified)],
            revised_labels=True,
        )
        self.assertEqual((1, 1, 1), (wrong["tp"], wrong["fp"], wrong["fn"]))
        self.assertEqual(
            [self.label("v10-cy-05", "#2", "P0", "fp_guard")["finding_id"]],
            wrong["hit_fp_guard_ids"],
        )
        # The same boundary on a #4 sub-ID: the Locator truthiness line is #4f P0.
        case = self.v10_by_id["v10-pw-01"]
        locator = self.label("v10-pw-01", "#4f", "P0", "finding")
        wrong = self.runner.score(
            case,
            [finding("#4c-4e", "P1", locator["file"], locator["line"])],
            revised_labels=True,
        )
        self.assertEqual((0, 1, 2), (wrong["tp"], wrong["fp"], wrong["fn"]))

    def test_optional_severity_is_neither_rewarded_nor_penalised(self) -> None:
        case = self.v10_by_id["v10-pw-04"]
        required = self.label("v10-pw-04", "#4k", "P1", "finding")
        raised = self.label("v10-pw-04", "#4k", "P0", "optional")
        both = self.runner.score(
            case, [as_finding(required), as_finding(raised)], revised_labels=True
        )
        self.assertEqual((1, 0, 0), (both["tp"], both["fp"], both["fn"]))
        self.assertEqual([raised["finding_id"]], both["optional_matched_ids"])
        only_raised = self.runner.score(case, [as_finding(raised)], revised_labels=True)
        self.assertEqual((0, 0, 1), (only_raised["tp"], only_raised["fp"], only_raised["fn"]))

    def test_accepted_alternatives_count_once(self) -> None:
        for case_id, pattern_id, severity in (
            ("v10-pw-08", "#9", "P1"),
            ("v10-cy-08", "#7", "P0"),
            ("v10-cy-10", "#5b", "P1"),
        ):
            case = self.v10_by_id[case_id]
            primary = next(
                label for label in case["labels"]
                if "accepted_alternatives" in label
                and (label["pattern_id"], label["severity"]) == (pattern_id, severity)
            )
            alternative = primary["accepted_alternatives"][0]
            others = [
                as_finding(label) for label in case["labels"]
                if label["kind"] == "finding" and label is not primary
            ]
            for findings in ([as_finding(primary)], [as_finding(alternative)],
                             [as_finding(primary), as_finding(alternative)]):
                result = self.runner.score(case, findings + others, revised_labels=True)
                self.assertEqual(
                    (len(others) + 1, 0, 0),
                    (result["tp"], result["fp"], result["fn"]),
                    case_id,
                )

    def test_out_of_scope_and_convention_guards_penalise_reports(self) -> None:
        case = self.v10_by_id["v10-pw-07"]
        vitest = self.label("v10-pw-07", "#19", "P1", "fp_guard")
        result = self.runner.score(case, [as_finding(vitest)], revised_labels=True)
        self.assertEqual((0, 1, 1), (result["tp"], result["fp"], result["fn"]))
        self.assertEqual([vitest["finding_id"]], result["hit_fp_guard_ids"])
        case = self.v10_by_id["v10-cy-06"]
        listed = self.label("v10-cy-06", "#11c", "P2", "fp_guard")
        result = self.runner.score(case, [as_finding(listed)], revised_labels=True)
        self.assertEqual([listed["finding_id"]], result["hit_fp_guard_ids"])

    def synthetic_v10_runs(self, repetitions: int) -> list[dict]:
        """Every finding label in every run; optional labels in a strict majority."""
        runs = []
        for case in self.v10_cases:
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
            self.v10_cases, 5, self.v10["schedule"]["seed"]
        )
        self.assertEqual(len(self.v10_cases) * 5, len(schedule))
        primary = self.runner.primary_metrics(
            self.v10_cases, self.synthetic_v10_runs(5), 5, "strict-majority",
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
        self.assertIn(self.label("v10-cy-02", "#23", "P0", "finding")["finding_id"], p0)
        self.assertNotIn(self.label("v10-cy-05", "#2", "P1", "finding")["finding_id"], p0)
        self.assertNotIn(self.label("v10-pw-04", "#4k", "P0", "optional")["finding_id"], p0)
        self.assertEqual(1.0, primary["p0_per_label_stability"]["stable_label_recall"])
        self.assertEqual(1.0, primary["clean_case_specificity"]["value"])
        self.assertEqual(
            "accepted-alternatives-and-optional-v1", primary["label_semantics"]
        )

    def test_comparator_case_rows_use_revised_semantics(self) -> None:
        report = {
            "protocol_id": PROTOCOL_ID,
            "prompt_profile": "full",
            "runner": "claude",
            "model": "claude-opus-5",
            "primary_metrics": {"stability": {"required_hits": 3}},
            "runs": self.synthetic_v10_runs(5),
        }
        rows = self.comparator.report_case_metric_rows(report, self.v10_cases)
        self.assertEqual(set(self.v10_by_id), set(rows))
        kinds = Counter(label["kind"] for label in self.labels)
        self.assertEqual(
            (kinds["finding"], 0, 0),
            tuple(
                sum(row["stable"][name] for row in rows.values())
                for name in ("tp", "fp", "fn")
            ),
        )

    def test_single_host_comparator_is_decisive_for_v10(self) -> None:
        cases = self.v5_helpers.synthetic_arm_cases()
        reports = [
            self.v5_helpers.synthetic_arm_report(
                self.comparator,
                profile,
                "claude",
                "claude-opus-5",
                "strong" if profile == "full" else "weak",
                cases,
            )
            for profile in ("full", "catalog-only", "no-skill")
        ]
        for report in reports:
            report["runner_identity"] = "Claude Code 2.1.281"
        by_profile = {report["prompt_profile"]: report for report in reports}
        for step in self.v10["arm_comparison"]["execution_order"]:
            report = by_profile[step["prompt_profile"]]
            report["started_at"] = f"2026-09-28T00:00:0{step['ordinal'] - 1}+00:00"
            report["created_at"] = f"2026-09-28T00:00:0{step['ordinal']}+00:00"
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
                self.v10,
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
        self.assertIn("# Reviewer holdout v10", readme.splitlines()[0])
        self.assertIn("counted run is attempt 3", readme)
        self.assertIn("arm comparison `FAIL`, so no skill-lift claim", readme)
        calls = len(self.v10_cases) * 5 * 3
        self.assertEqual(450, calls)
        for contract in (
            f"{calls} model calls",
            "scripts/evals/reviewer-holdout-v10.json",
            "scripts/evals/reviewer-validation-protocol-v10.json",
            EXPECTED_CASES_FILE_SHA256,
            EXPECTED_CORPUS_SHA256,
            EXPECTED_PROTOCOL_SHA256,
            "Claude Code 2.1.281",
            "--compare-arms",
            'test -z "$(git status --porcelain)"',
            "100 of the 103 finding and guard labels matched both labelers",
            "## Why v10 exists",
            "## Claim limits",
        ):
            self.assertIn(contract, readme)
        for case in self.v10_cases:
            self.assertIn(f"`{case['id']}`", readme)
        self.assertEqual(3, readme.count("--repetitions 5"))
        self.assertEqual(0, readme.count("--repetitions 3"))
        self.assertEqual(4, readme.count('--output "$OUT/'))
        self.assertEqual(3, len(re.findall(r"--arm (full|catalog-only|no-skill) ", readme)))
        self.assertEqual(3, readme.count("--allow-live"))
        kinds = Counter((label["kind"], label["severity"]) for label in self.labels)
        for kind in ("finding", "fp_guard", "optional"):
            row = " | ".join(
                str(kinds[(kind, severity)]) for severity in ("P0", "P1", "P2")
            )
            total = sum(kinds[(kind, severity)] for severity in ("P0", "P1", "P2"))
            self.assertIn(f"| {kind} | {row} | {total} |", readme)
        self.assertIn(
            "benchmarks/reviewer-holdout-v10/README.md",
            BENCHMARK_DOC_PATH.read_text(encoding="utf-8"),
        )
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
        unreleased = changelog.split("## [2.0.0]", 1)[1].split("\n## [", 1)[0]
        added = unreleased.split("### Added", 1)[1].split("\n### ", 1)[0]
        self.assertIn(PROTOCOL_ID, added)
        self.assertIn(
            "scripts/ci/test-reviewer-holdout-v10.py",
            CI_LOCAL_PATH.read_text(encoding="utf-8"),
        )

    def test_archived_attempts_match_documented_status(self) -> None:
        attempts = README_PATH.parent / "attempts"
        for number in ("1", "2"):
            comparison = read_json(attempts / number / "arm-comparison.json")
            self.assertEqual("INCONCLUSIVE", comparison["status"], number)
            self.assertFalse(comparison["skill_lift_claim_eligible"])
            for arm in ("full", "catalog-only", "no-skill"):
                report = read_json(attempts / number / f"{arm}-claude.json")
                self.assertEqual(EXPECTED_PROTOCOL_SHA256, report["protocol_sha256"], (number, arm))
        second = read_json(attempts / "2" / "no-skill-claude.json")
        self.assertEqual(1, second["summary"]["infrastructure_errors"])

    def test_counted_attempt_3_reports(self) -> None:
        reports = README_PATH.parent / "reports"
        comparison = read_json(reports / "arm-comparison.json")
        self.assertEqual("FAIL", comparison["status"])
        self.assertFalse(comparison["skill_lift_claim_eligible"])
        readme = README_PATH.read_text(encoding="utf-8")
        for arm in ("full", "catalog-only", "no-skill"):
            report = read_json(reports / f"{arm}-claude.json")
            self.assertEqual(EXPECTED_PROTOCOL_SHA256, report["protocol_sha256"], arm)
            self.assertEqual(0, report["summary"]["infrastructure_errors"], arm)
            unique = report["primary_metrics"]["unique"]
            self.assertIn(f"{unique['precision']:.3f} / {unique['recall']:.3f} / {unique['f1']:.3f}", readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
