#!/usr/bin/env python3
"""Validate the preregistered v16 before/after skill-revision holdout on the v9 corpus."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
V9_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v9.json"
V10_CASES_PATH = ROOT / "scripts/evals/reviewer-holdout-v10.json"
PROTOCOL_PATHS = {
    version: ROOT / f"scripts/evals/reviewer-validation-protocol-v{version}.json"
    for version in range(8, 17)
}
V16_PROTOCOL_PATH = PROTOCOL_PATHS[16]
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
REVISIONS_PATH = ROOT / "scripts/evals/compare-reviewer-revisions.py"
README_PATH = ROOT / "benchmarks/reviewer-holdout-v16/README.md"
BENCHMARK_DOC_PATH = ROOT / "docs/ai-reviewer-benchmark.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
CONTRIBUTING_PATH = ROOT / "CONTRIBUTING.md"
CI_LOCAL_PATH = ROOT / "scripts/ci/ci-local.sh"

PROTOCOL_ID = "reviewer-holdout-v16"
V9_ID = "reviewer-holdout-v9"
EXPECTED_PROTOCOL_SHA256 = "afbb99cff4c8d91124e3c90cd436bdcecf2ec167e913d9fffe56e37561e23915"
# v16 reuses the frozen v9 corpus: these are v9's digests, unchanged.
EXPECTED_CASES_FILE_SHA256 = "723740ea9eb6defe4951f72f30927570d9f0e259885d1503d25b20ea6e4c3d14"
EXPECTED_CORPUS_SHA256 = "5465a355d2126ecbda3e24822ed4e7ced43676df283a77bbf01ca377591debaf"
# Earlier protocols this change must leave byte for byte.
FROZEN_PROTOCOL_SHA256 = {
    9: "133e7450f0bfecc866ad9e33111012df478f19fd60e05b9d7e88427c2cbb100d",
    10: "186680ad624f9ae40ff0b652ee4949322fb6ccfac5e5426a4b7c182278f33c39",
    12: "ec42df85e7161ca96a807cbd0079eb9c406b926ae0c40bb4214f2b88280a5d20",
    15: "0e79b040aab2b47865ca13a6a484fb3bcad617ef16bcc38b4de7a49b12498d93",
}
BEFORE = {
    "source_commit": "769f1f61c5d280ff54d1f86610fe86ab84d2dbeb",
    "skill_tree": "14b4563d03cfbb5e9310e6e14cdfdb4f73c795d1",
    "skill_sha256": "c3b545315f185c1631b213b73f2466a24bad4beaa1d00bc24e4f6c675cb764d9",
}
AFTER = {
    "source_commit": "9e73a6c252a135bc94568e9efd30d691a25f0086",
    "skill_tree": "899017afbb79a1d7e4e28f81927dccae3e76f493",
    "skill_sha256": "72a2582f043fd7dedbe0bbbc3e62b695d512248be34e0791ac890a20627cbdda",
}
HOST = {"runner": "codex", "model": "gpt-6-sol"}
IDENTITY = {"codex": "codex-cli 0.155.1"}
STUB_CASE = "v9-pw-01"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_object_available(name: str) -> bool:
    git = shutil.which("git")
    if git is None:
        return False
    result = subprocess.run(
        [git, "-C", str(ROOT), "cat-file", "-e", f"{name}^{{tree}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def materialize_tree(tree: str, destination: Path) -> Path:
    """Extract a git tree (skills/e2e-reviewer at a pinned commit) into destination."""
    archive = subprocess.run(
        [shutil.which("git"), "-C", str(ROOT), "archive", "--format=tar", tree],
        stdout=subprocess.PIPE,
        check=True,
    ).stdout
    destination.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as handle:
        try:
            handle.extractall(destination, filter="data")
        except TypeError:  # Python without extraction filters; the archive is our own tree.
            handle.extractall(destination)
    return destination


class ReviewerHoldoutV16Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("reviewer_holdout_v16_runner", RUNNER_PATH)
        cls.comparator = load_module("reviewer_holdout_v16_comparator", COMPARATOR_PATH)
        cls.revisions = load_module("reviewer_holdout_v16_revisions", REVISIONS_PATH)
        cls.protocols = {version: read_json(path) for version, path in PROTOCOL_PATHS.items()}
        cls.v16 = cls.protocols[16]
        cls.v9_metadata, cls.v9_cases = cls.runner.load_cases(V9_CASES_PATH)
        cls.v10_metadata, _ = cls.runner.load_cases(V10_CASES_PATH)
        cls.temp = tempfile.TemporaryDirectory(prefix="reviewer-holdout-v16-test-")
        cls.skill_dirs: dict[str, Path] = {}
        for name, pinned in (("before", BEFORE), ("after", AFTER)):
            if git_object_available(pinned["skill_tree"]):
                cls.skill_dirs[name] = materialize_tree(
                    pinned["skill_tree"], Path(cls.temp.name) / name
                )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def load_mutated(self, temp: str, data: dict, name: str = "protocol.json") -> dict:
        path = Path(temp) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return self.runner.load_protocol(path)

    def require_revision_dirs(self) -> dict[str, Path]:
        if set(self.skill_dirs) != {"before", "after"}:
            self.skipTest("pinned revision trees are not in this clone's git objects")
        return self.skill_dirs

    # Frozen inputs -------------------------------------------------------

    def test_frozen_inputs_and_runner_registration(self) -> None:
        self.assertEqual(
            EXPECTED_CASES_FILE_SHA256, hashlib.sha256(V9_CASES_PATH.read_bytes()).hexdigest()
        )
        self.assertEqual(
            EXPECTED_CORPUS_SHA256, self.runner.corpus_digest(V9_CASES_PATH, self.v9_cases)
        )
        self.assertEqual(
            EXPECTED_PROTOCOL_SHA256, hashlib.sha256(V16_PROTOCOL_PATH.read_bytes()).hexdigest()
        )
        self.assertEqual(self.v16, self.runner.load_protocol(V16_PROTOCOL_PATH))
        self.assertEqual(V16_PROTOCOL_PATH, self.runner.V16_PROTOCOL)
        self.assertEqual(
            {
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
                "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            },
            self.runner.PINNED_LIVE_INPUTS[(V9_CASES_PATH, V16_PROTOCOL_PATH)],
        )
        self.assertEqual(
            [(V9_CASES_PATH, V16_PROTOCOL_PATH)],
            [key for key in self.runner.PINNED_LIVE_INPUTS if key[1] == V16_PROTOCOL_PATH],
        )
        for id_set in (
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
        ):
            self.assertIn(PROTOCOL_ID, getattr(self.runner, id_set), id_set)
        for id_set in (
            "ARM_COMPARISON_PROTOCOL_IDS",
            "OUTPUT_NORMALIZATION_PROTOCOL_IDS",
            "PROVIDER_BALANCED_PROTOCOL_IDS",
            "FULL_ONLY_PROTOCOL_IDS",
            "SUPERSEDED_PROTOCOL_IDS",
            "HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS",
            "SPECIFICITY_PROTOCOL_IDS",
        ):
            self.assertNotIn(PROTOCOL_ID, getattr(self.runner, id_set), id_set)
        self.assertEqual({PROTOCOL_ID, "reviewer-holdout-v20", "reviewer-holdout-v21"}, self.runner.REVISION_COMPARISON_PROTOCOL_IDS)
        self.assertEqual(V9_CASES_PATH, self.runner.REVISED_LABEL_CORPORA[PROTOCOL_ID])
        self.assertEqual(V9_ID, self.runner.SHARED_CORPUS_PROTOCOLS[PROTOCOL_ID])
        self.assertEqual(
            {
                V9_ID: PROTOCOL_PATHS[9],
                "reviewer-holdout-v10": PROTOCOL_PATHS[10],
                "reviewer-holdout-v17": ROOT / "scripts/evals/reviewer-validation-protocol-v17.json",
            },
            self.runner.SHARED_CORPUS_OWNER_PROTOCOLS,
        )
        self.assertEqual("minimum", self.runner.FROZEN_EXECUTION_IDENTITY_POLICIES[PROTOCOL_ID])
        self.assertEqual(IDENTITY, self.runner.FROZEN_EXECUTION_IDENTITIES[PROTOCOL_ID])
        self.assertEqual(HOST, self.runner.REVISED_LABEL_HOSTS[PROTOCOL_ID])
        self.assertNotIn(PROTOCOL_ID, self.runner.REQUIRED_CLAUDE_PERMISSION_MODES)

    def test_earlier_protocols_are_unchanged_and_still_load(self) -> None:
        for version, expected in FROZEN_PROTOCOL_SHA256.items():
            self.assertEqual(
                expected,
                hashlib.sha256(PROTOCOL_PATHS[version].read_bytes()).hexdigest(),
                version,
            )
        for version in range(8, 16):
            path = PROTOCOL_PATHS[version]
            self.assertEqual(self.protocols[version], self.runner.load_protocol(path), version)
            pinned = [
                digests["protocol_sha256"]
                for (_, protocol_path), digests in self.runner.PINNED_LIVE_INPUTS.items()
                if protocol_path == path
            ]
            self.assertEqual(
                [hashlib.sha256(path.read_bytes()).hexdigest()], pinned, version
            )
            self.assertIsNone(self.runner.revision_skill_digests(self.protocols[version]))

    def test_protocol_composition_is_disclosed(self) -> None:
        v12, v15, v9 = self.protocols[12], self.protocols[15], self.protocols[9]
        self.assertEqual(
            [
                "schema_version", "protocol_id", "corpus", "scoring", "schedule",
                "stability", "execution_identity", "infrastructure_retry",
                "usage_capture", "output_schema", "prompt_arms",
                "revision_comparison", "host_matrix", "confidence_intervals",
                "decision", "cross_host_decision",
            ],
            list(self.v16),
        )
        self.assertEqual(v9["corpus"], self.v16["corpus"])
        for key in (
            "scoring", "stability", "execution_identity", "infrastructure_retry",
            "host_matrix", "confidence_intervals", "decision", "cross_host_decision",
        ):
            self.assertEqual(v12[key], self.v16[key], key)
        for key in ("usage_capture", "output_schema"):
            self.assertEqual(v15[key], self.v16[key], key)
        schedule = copy.deepcopy(self.v16["schedule"])
        disclosure = schedule.pop("design_disclosure")
        expected_schedule = copy.deepcopy(v12["schedule"])
        expected_schedule.pop("design_disclosure")
        self.assertEqual(expected_schedule, schedule)
        for phrase in (
            "commit 9e73a6c",
            "not derived from",
            "derived from v10 outcomes",
            "reuses the frozen v9 corpus unchanged by path and digest",
            "gpt-6-sol at the codex-cli 0.155.1 floor",
            "before is the skill at 769f1f6, byte-identical to the skill at c21d4f0",
            "after is the skill at 9e73a6c, which also carries 92f5bdf",
            "full-arm prompt bytes differ by that move",
            "catalog-only prompt differs only by the two pattern-reference.md additions",
            "No no-skill arm is run",
            "--output-schema",
            "same author who wrote the fixes",
            "both revisions may already fit it",
            "one host supports no cross-provider claim",
            "public development evidence",
        ):
            self.assertIn(phrase, disclosure)
        self.assertEqual(self.runner.EXPECTED_V16_PROMPT_ARMS, self.v16["prompt_arms"])
        self.assertEqual(
            self.runner.EXPECTED_V16_REVISION_COMPARISON, self.v16["revision_comparison"]
        )
        contract = self.v16["revision_comparison"]
        self.assertEqual({"before": BEFORE, "after": AFTER}, contract["revisions"])
        self.assertEqual(
            {"before": BEFORE["skill_sha256"], "after": AFTER["skill_sha256"]},
            self.runner.revision_skill_digests(self.v16),
        )
        self.assertEqual(
            [("before", "full"), ("after", "full"), ("after", "catalog-only"),
             ("before", "catalog-only")],
            self.revisions.cells(self.v16),
        )
        self.assertEqual(
            {"stable_f1_delta_min": 0, "stable_f1_delta_ci95_lower_min": 0,
             "stable_guard_hit_rate_delta_max": 0},
            contract["decision"]["thresholds"],
        )
        self.assertEqual(
            self.protocols[12]["arm_comparison"]["uncertainty"], contract["uncertainty"]
        )

    def test_protocol_validation_pins_v16_fields(self) -> None:
        def set_path(data: dict, keys: tuple, value) -> None:
            target = data
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value

        mutations = {
            "no-skill control": lambda d: d["prompt_arms"]["controls"].append("no-skill"),
            "v12 prompt arms": lambda d: d.update(
                {"prompt_arms": copy.deepcopy(self.protocols[12]["prompt_arms"])}
            ),
            "arm comparison added": lambda d: d.update(
                {"arm_comparison": copy.deepcopy(self.protocols[12]["arm_comparison"])}
            ),
            "missing revision comparison": lambda d: d.pop("revision_comparison"),
            "before digest": lambda d: set_path(
                d, ("revision_comparison", "revisions", "before", "skill_sha256"), "0" * 64
            ),
            "after digest": lambda d: set_path(
                d, ("revision_comparison", "revisions", "after", "skill_sha256"),
                BEFORE["skill_sha256"],
            ),
            "before commit": lambda d: set_path(
                d, ("revision_comparison", "revisions", "before", "source_commit"), "0" * 40
            ),
            "third revision": lambda d: d["revision_comparison"]["revisions"].update(
                {"middle": dict(BEFORE)}
            ),
            "order": lambda d: d["revision_comparison"]["execution_order"].reverse(),
            "lower bound threshold": lambda d: set_path(
                d, ("revision_comparison", "decision", "thresholds",
                    "stable_f1_delta_ci95_lower_min"), -0.05,
            ),
            "guard threshold": lambda d: set_path(
                d, ("revision_comparison", "decision", "thresholds",
                    "stable_guard_hit_rate_delta_max"), 0.05,
            ),
            "primary arm": lambda d: set_path(
                d, ("revision_comparison", "decision", "primary_arm"), "catalog-only"
            ),
            "bootstrap seed": lambda d: set_path(
                d, ("revision_comparison", "uncertainty", "seed"), 1
            ),
            "elapsed limit": lambda d: set_path(
                d, ("revision_comparison", "maximum_matrix_elapsed_seconds"), 86_400
            ),
            "claude host": lambda d: d.update(
                {"host_matrix": [{"runner": "claude", "model": "claude-sonnet-5"}]}
            ),
            "retired codex model": lambda d: d.update(
                {"host_matrix": [{"runner": "codex", "model": "gpt-5.6-sol"}]}
            ),
            "older codex floor": lambda d: d["execution_identity"].update(
                {"expected_cli_versions": {"codex": "codex-cli 0.154.0"}}
            ),
            "exact policy": lambda d: d["execution_identity"].update(
                {"version_policy": "exact"}
            ),
            "missing identity": lambda d: d.pop("execution_identity"),
            "v10 corpus": lambda d: d.update(
                {"corpus": copy.deepcopy(self.protocols[10]["corpus"])}
            ),
            "corpus digest": lambda d: d["corpus"].update({"corpus_sha256": "0" * 64}),
            "missing output schema": lambda d: d.pop("output_schema"),
            "schema digest": lambda d: d["output_schema"].update({"schema_sha256": "0" * 64}),
            "missing usage capture": lambda d: d.pop("usage_capture"),
            "three attempts": lambda d: d["infrastructure_retry"].update(
                {"max_attempts_per_call": 3}
            ),
            "three repetitions": lambda d: d["schedule"].update(
                {"default_repetitions": 3, "release_repetitions": 3}
            ),
            "missing disclosure": lambda d: d["schedule"].update({"design_disclosure": " "}),
            "fence normalization": lambda d: d.update(
                {"output_normalization": copy.deepcopy(
                    self.protocols[14]["output_normalization"]
                )}
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, mutate in mutations.items():
                data = copy.deepcopy(self.v16)
                mutate(data)
                with self.subTest(name), self.assertRaises(ValueError):
                    self.load_mutated(temp, data)
            # A revision-comparison block is refused on every other protocol.
            for version in (9, 12, 15):
                data = copy.deepcopy(self.protocols[version])
                data["revision_comparison"] = copy.deepcopy(self.v16["revision_comparison"])
                with self.subTest(version), self.assertRaisesRegex(ValueError, "unknown="):
                    self.load_mutated(temp, data, f"v{version}.json")

    # Corpus binding --------------------------------------------------------

    def test_corpus_reuse_is_limited_to_v16(self) -> None:
        self.runner.validate_corpus_protocol_pairing(
            self.v9_metadata, self.v16, EXPECTED_CORPUS_SHA256
        )
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            self.runner.validate_corpus_protocol_pairing(
                self.v10_metadata, self.v16,
                "672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d",
            )
        with tempfile.TemporaryDirectory() as temp:
            reusers = dict(self.runner.SHARED_CORPUS_PROTOCOLS)
            reusers.pop(PROTOCOL_ID)
            with mock.patch.object(self.runner, "SHARED_CORPUS_PROTOCOLS", reusers):
                with self.assertRaisesRegex(ValueError, "may not share its corpus"):
                    self.runner.load_protocol(V16_PROTOCOL_PATH)
            data = copy.deepcopy(self.protocols[8])
            data["corpus"]["path"] = "scripts/evals/reviewer-holdout-v9.json"
            with self.assertRaisesRegex(ValueError, "must be the v8 corpus"):
                self.load_mutated(temp, data, "v8.json")
        self.assertEqual(self.protocols[9], self.runner.load_protocol(PROTOCOL_PATHS[9]))

    # Revision pinning --------------------------------------------------------

    def test_pinned_trees_reproduce_the_pinned_digests(self) -> None:
        dirs = self.require_revision_dirs()
        git = shutil.which("git")
        for name, pinned in (("before", BEFORE), ("after", AFTER)):
            with self.subTest(name):
                self.assertEqual(
                    pinned["skill_sha256"],
                    self.runner.skill_digest(dirs[name]),
                )
                tree = subprocess.run(
                    [git, "-C", str(ROOT), "rev-parse",
                     f"{pinned['source_commit']}:skills/e2e-reviewer"],
                    stdout=subprocess.PIPE, text=True, check=True,
                ).stdout.strip()
                self.assertEqual(pinned["skill_tree"], tree)
        # 769f1f6 and c21d4f0 carry the same skill, as the disclosure says.
        if git_object_available("c21d4f027808a9e415b9aa48db06830bd353dce7"):
            tree = subprocess.run(
                [git, "-C", str(ROOT), "rev-parse",
                 "c21d4f027808a9e415b9aa48db06830bd353dce7:skills/e2e-reviewer"],
                stdout=subprocess.PIPE, text=True, check=True,
            ).stdout.strip()
            self.assertEqual(BEFORE["skill_tree"], tree)

    def test_revision_prompts_differ_only_where_disclosed(self) -> None:
        dirs = self.require_revision_dirs()
        skills = {name: path for name, path in dirs.items()}
        digests = {
            (name, profile): self.runner.prompt_set_digest(
                self.v9_cases, EXPECTED_CORPUS_SHA256, skill, profile,
                numbered_source_lines=True,
            )
            for name, skill in skills.items()
            for profile in ("full", "catalog-only", "no-skill")
        }
        self.assertEqual(digests[("before", "no-skill")], digests[("after", "no-skill")])
        self.assertNotEqual(digests[("before", "full")], digests[("after", "full")])
        self.assertNotEqual(
            digests[("before", "catalog-only")], digests[("after", "catalog-only")]
        )
        for name, skill in skills.items():
            legend = [
                row.split(" | ", 1)[0]
                for row in self.runner.pattern_output_legend(skill).splitlines()
            ]
            self.assertEqual(list(self.runner.OUTPUT_SCHEMA_PATTERN_IDS), legend, name)
            self.runner.require_output_schema_vocabulary(self.v16["output_schema"], skill)
        # Catalog-only embeds only pattern-reference.md; its change is the two additions.
        before = (skills["before"] / "references/pattern-reference.md").read_text()
        after = (skills["after"] / "references/pattern-reference.md").read_text()
        self.assertEqual(
            [], [line for line in before.splitlines() if line not in after.splitlines()]
        )
        added = [
            line for line in after.splitlines()
            if line.strip() and line not in before.splitlines()
        ]
        self.assertEqual(2, len(added), added)
        self.assertTrue(added[0].startswith("**Severity:** P0 when nothing the action promised"))
        self.assertTrue(added[1].startswith("**Primary line:** Anchor #23 to the fixture field"))

    def test_schema_enum_covers_every_v9_label(self) -> None:
        enum = set(self.v16["output_schema"]["schema"]["properties"]["findings"]["items"][
            "properties"]["pattern_id"]["enum"])
        for case in self.v9_cases:
            for label in case["labels"]:
                self.assertIn(label["pattern_id"], enum, label["finding_id"])
                for alternative in label.get("accepted_alternatives", []):
                    self.assertIn(alternative["pattern_id"], enum, label["finding_id"])

    def test_no_wrapper_live_gate_accepts_only_pinned_revisions(self) -> None:
        pinned = set(self.runner.revision_skill_digests(self.v16).values())
        common = (
            V9_CASES_PATH, V16_PROTOCOL_PATH,
        )
        with tempfile.TemporaryDirectory() as temp:
            elsewhere = Path(temp).resolve() / "skill"
            elsewhere.mkdir()

            def gate(requested_skill: Path, skill: Path, **kwargs) -> bool:
                return self.runner.is_pinned_no_wrapper_live_run(
                    V9_CASES_PATH, V16_PROTOCOL_PATH, requested_skill, *common, skill,
                    EXPECTED_CASES_FILE_SHA256, EXPECTED_CORPUS_SHA256,
                    EXPECTED_PROTOCOL_SHA256, **kwargs,
                )

            self.assertTrue(gate(
                elsewhere, elsewhere,
                revision_skill_sha256s=pinned, skill_sha256=BEFORE["skill_sha256"],
            ))
            self.assertFalse(gate(
                elsewhere, elsewhere,
                revision_skill_sha256s=pinned, skill_sha256="0" * 64,
            ))
            # Without a revision pin, only the checkout's own skill passes.
            self.assertFalse(gate(elsewhere, elsewhere))
            self.assertTrue(gate(self.runner.DEFAULT_SKILL_DIR, self.runner.DEFAULT_SKILL_DIR))
            link = Path(temp).resolve() / "link"
            link.symlink_to(elsewhere)
            self.assertFalse(gate(
                link, elsewhere,
                revision_skill_sha256s=pinned, skill_sha256=BEFORE["skill_sha256"],
            ))

    def run_stub(self, temp: Path, skill_dir: Path) -> subprocess.CompletedProcess:
        stub = temp / "stub-runner"
        stub.write_text(
            "#!/bin/sh\n/bin/cat >/dev/null\nprintf '%s' '{\"findings\":[]}'\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        wrapper = temp / "isolation-wrapper"
        wrapper.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
        return subprocess.run(
            [
                "python3", str(RUNNER_PATH),
                "--cases", str(V9_CASES_PATH),
                "--protocol", str(V16_PROTOCOL_PATH),
                "--skill-dir", str(skill_dir),
                "--case", STUB_CASE,
                "--arm", "catalog-only",
                "--runner", str(stub),
                "--isolation-wrapper", str(wrapper),
                "--repetitions", "1",
                "--timeout", "30",
                "--output", str(temp / "report.json"),
            ],
            cwd=ROOT,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

    def test_runner_refuses_an_unpinned_skill_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skill = Path(temp).resolve() / "e2e-reviewer"
            shutil.copytree(self.runner.DEFAULT_SKILL_DIR, skill)
            with (skill / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write("\nunpinned edit\n")
            result = self.run_stub(Path(temp).resolve(), skill)
            self.assertEqual(2, result.returncode, result.stdout)
            self.assertIn("is not one of the skill revisions", result.stdout)
            self.assertFalse((Path(temp) / "report.json").exists())

    def test_runner_evaluates_the_pinned_before_revision(self) -> None:
        dirs = self.require_revision_dirs()
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_stub(
                Path(temp).resolve(), dirs["before"].resolve()
            )
            report = read_json(Path(temp) / "report.json")
            self.assertEqual(BEFORE["skill_sha256"], report["skill_sha256"], result.stdout)
            self.assertEqual(BEFORE["skill_sha256"], report["skill_sha256_after"])
            self.assertEqual(PROTOCOL_ID, report["protocol_id"])
            self.assertEqual(self.v16["output_schema"], report["output_schema"])
            self.assertEqual(self.v16["usage_capture"], report["usage_capture"])
            self.assertEqual(1, len(report["runs"]))
            self.assertIsNotNone(report["runs"][0]["score"])
            self.comparator.load_report(Path(temp) / "report.json")

    def test_holdout_comparator_refuses_v16(self) -> None:
        result = subprocess.run(
            [
                "python3", str(COMPARATOR_PATH), str(V9_CASES_PATH),
                "--cases", str(V9_CASES_PATH), "--protocol", str(V16_PROTOCOL_PATH),
            ],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("compare-reviewer-revisions.py", result.stdout)

    # Before/after analysis ---------------------------------------------------

    def synthetic_report(
        self, revision: str, profile: str, missed: int, guard_hits: int, ordinal: int
    ) -> dict:
        """A recomputed-shape report: the first `missed` finding cases miss every
        finding, and the first `guard_hits` fp_guard labels are reported."""
        finding_cases = [
            case["id"] for case in self.v9_cases
            if any(label["kind"] == "finding" for label in case["labels"])
        ]
        missed_cases = set(finding_cases[:missed])
        guards = [
            (case["id"], label)
            for case in self.v9_cases
            for label in case["labels"]
            if label["kind"] == "fp_guard"
        ][:guard_hits]
        runs = []
        for case in self.v9_cases:
            findings = [] if case["id"] in missed_cases else [
                {key: label[key] for key in ("pattern_id", "severity", "file", "line")}
                for label in case["labels"]
                if label["kind"] == "finding"
            ]
            findings += [
                {key: label[key] for key in ("pattern_id", "severity", "file", "line")}
                for case_id, label in guards
                if case_id == case["id"]
            ]
            for repetition in range(1, 6):
                runs.append({
                    "case": case["id"],
                    "repetition": repetition,
                    "findings": findings,
                    "score": self.runner.score(case, findings, revised_labels=True),
                })
        start = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc) + dt.timedelta(hours=ordinal)
        return {
            "protocol_id": PROTOCOL_ID,
            "skill_sha256": {"before": BEFORE, "after": AFTER}[revision]["skill_sha256"],
            "prompt_profile": profile,
            "runner": HOST["runner"],
            "model": HOST["model"],
            "runner_identity": "codex-cli 0.155.1",
            "runner_executable": "/opt/codex/bin/codex",
            "reasoning_effort": None,
            "git_revision": "a" * 40,
            "git_dirty": False,
            "started_at": start.isoformat(),
            "created_at": (start + dt.timedelta(minutes=40)).isoformat(),
            "execution_complete": True,
            "status": "PASS",
            "runs": runs,
            "primary_metrics": self.runner.primary_metrics(
                self.v9_cases, runs, 5, "strict-majority", revised_labels=True
            ),
        }

    def run_analysis(self, reports: dict[tuple[str, str], dict]) -> dict:
        paths = {cell: Path(f"/reports/{cell[0]}-{cell[1]}.json") for cell in reports}
        by_path = {str(path): reports[cell] for cell, path in paths.items()}
        with (
            mock.patch.object(self.revisions, "validate_skill_dirs"),
            mock.patch.object(self.revisions, "sha256_file", return_value="c" * 64),
            mock.patch.object(
                self.revisions.COMPARATOR, "load_report",
                side_effect=lambda path: copy.deepcopy(by_path[str(path)]),
            ),
            mock.patch.object(
                self.revisions.COMPARATOR, "recompute_report",
                side_effect=lambda report, *_args, **_kwargs: report,
            ),
        ):
            return self.revisions.compare_revisions(
                paths, V9_CASES_PATH, V16_PROTOCOL_PATH,
                {"before": Path("/before"), "after": Path("/after")},
            )

    def matrix(self, **quality) -> dict[tuple[str, str], dict]:
        """Four cells; quality keys are <revision>_<arm> with '-' as '_'."""
        order = self.revisions.cells(self.v16)
        return {
            cell: self.synthetic_report(
                cell[0],
                cell[1],
                *quality.get(f"{cell[0]}_{cell[1]}".replace("-", "_"), (0, 0)),
                ordinal,
            )
            for ordinal, cell in enumerate(order)
        }

    def test_analysis_supports_an_improvement_and_reports_catalog_only(self) -> None:
        result = self.run_analysis(self.matrix(before_full=(4, 0), before_catalog_only=(2, 0)))
        self.assertEqual("SUPPORTED", result["status"], result["status_reasons"])
        full = result["comparison"]["arms"]["full"]
        self.assertGreater(full["delta"]["stable_f1"], 0)
        self.assertGreaterEqual(full["intervals"]["stable_f1"]["lower"], 0)
        self.assertEqual(0, full["stable_guard_hit_rate"]["delta"])
        catalog = result["comparison"]["arms"]["catalog-only"]
        self.assertGreater(catalog["delta"]["stable_f1"], 0)
        self.assertEqual(
            self.v16["revision_comparison"]["claim_policy"]["supported"], result["claim"]
        )
        self.assertEqual(10_000, full["intervals"]["stable_f1"]["iterations"])

    def test_analysis_treats_no_difference_as_non_inferior(self) -> None:
        result = self.run_analysis(self.matrix())
        self.assertEqual("SUPPORTED", result["status"])
        self.assertEqual(0, result["comparison"]["arms"]["full"]["delta"]["stable_f1"])

    def test_analysis_rejects_a_drop_or_a_new_guard_hit(self) -> None:
        dropped = self.run_analysis(self.matrix(after_full=(3, 0)))
        self.assertEqual("NOT_SUPPORTED", dropped["status"])
        self.assertIn(
            "revision_stable_f1_delta_min",
            {reason["code"] for reason in dropped["status_reasons"]},
        )
        guarded = self.run_analysis(self.matrix(before_full=(4, 0), after_full=(0, 1)))
        self.assertEqual("NOT_SUPPORTED", guarded["status"])
        self.assertEqual(
            {"revision_stable_guard_hit_rate_delta_max"},
            {reason["code"] for reason in guarded["status_reasons"]},
        )
        # A catalog-only drop is descriptive and does not decide.
        catalog = self.run_analysis(self.matrix(after_catalog_only=(5, 2)))
        self.assertEqual("SUPPORTED", catalog["status"])
        self.assertLess(catalog["comparison"]["arms"]["catalog-only"]["delta"]["stable_f1"], 0)

    def test_analysis_is_inconclusive_on_binding_or_matrix_faults(self) -> None:
        faults = {
            "swapped revision": lambda m: m[("before", "full")].update(
                {"skill_sha256": AFTER["skill_sha256"]}
            ),
            "wrong arm": lambda m: m[("after", "catalog-only")].update(
                {"prompt_profile": "full"}
            ),
            "other host": lambda m: m[("after", "full")].update({"model": "gpt-5.6-sol"}),
            "incomplete": lambda m: m[("after", "full")].update({"execution_complete": False}),
            "unscored run": lambda m: m[("before", "catalog-only")]["runs"][0].update(
                {"score": None}
            ),
            "identity mismatch": lambda m: m[("after", "full")].update(
                {"runner_identity": "codex-cli 0.156.0"}
            ),
            "dirty checkout": lambda m: m[("before", "full")].update({"git_dirty": True}),
            "overlap": lambda m: m[("after", "full")].update(
                {"started_at": m[("before", "full")]["started_at"]}
            ),
            "elapsed": lambda m: m[("before", "catalog-only")].update(
                {"created_at": "2026-10-02T12:00:00+00:00"}
            ),
        }
        for name, fault in faults.items():
            with self.subTest(name):
                reports = self.matrix(before_full=(4, 0))
                fault(reports)
                result = self.run_analysis(reports)
                self.assertEqual("INCONCLUSIVE", result["status"])
                self.assertIsNone(result["comparison"])
                self.assertTrue(result["status_reasons"])
        with self.assertRaisesRegex(ValueError, "exactly one report"):
            reports = self.matrix()
            reports.pop(("before", "catalog-only"))
            self.run_analysis(reports)

    def test_analysis_binds_skill_dirs_and_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            edited = Path(temp) / "e2e-reviewer"
            shutil.copytree(self.runner.DEFAULT_SKILL_DIR, edited)
            with (edited / "SKILL.md").open("a", encoding="utf-8") as handle:
                handle.write("\nunpinned edit\n")
            with self.assertRaisesRegex(ValueError, "does not match the pinned"):
                self.revisions.validate_skill_dirs(
                    self.v16, {"before": edited, "after": edited}
                )
        with self.assertRaisesRegex(ValueError, "revision-comparison contract"):
            self.revisions.revision_contract(self.protocols[12])
        dirs = self.require_revision_dirs()
        self.revisions.validate_skill_dirs(
            self.v16, {name: path for name, path in dirs.items()}
        )

    # Documentation ---------------------------------------------------------

    def test_readme_documents_preregistration_and_exact_commands(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("# Reviewer holdout v16", readme.splitlines()[0])
        self.assertIn("`NOT_SUPPORTED`, so no claim that the fixes help", readme)
        calls = len(self.v9_cases) * 5 * 4
        self.assertEqual(600, calls)
        for contract in (
            f"{calls} scheduled model calls",
            "scripts/evals/reviewer-holdout-v9.json",
            "scripts/evals/reviewer-validation-protocol-v16.json",
            "scripts/evals/compare-reviewer-revisions.py",
            EXPECTED_CASES_FILE_SHA256,
            EXPECTED_CORPUS_SHA256,
            EXPECTED_PROTOCOL_SHA256,
            BEFORE["skill_sha256"],
            AFTER["skill_sha256"],
            BEFORE["source_commit"],
            AFTER["source_commit"],
            "codex-cli 0.155.1",
            "gpt-6-sol",
            "--output-schema",
            'test -z "$(git status --porcelain)"',
            "## Decision rule",
            "## Claim limits",
            "non-inferiority",
            "92f5bdf",
        ):
            self.assertIn(contract, readme)
        self.assertEqual(4, readme.count("--repetitions 5"))
        self.assertEqual(4, readme.count("--allow-live"))
        self.assertEqual(4, readme.count("--model gpt-6-sol"))
        self.assertEqual(2, len(re.findall(r"--arm full ", readme)))
        self.assertEqual(2, len(re.findall(r"--arm catalog-only ", readme)))
        self.assertEqual(0, len(re.findall(r"--arm no-skill", readme)))
        self.assertEqual(
            5, readme.count("--protocol scripts/evals/reviewer-validation-protocol-v16.json")
        )
        self.assertEqual(5, readme.count("--cases scripts/evals/reviewer-holdout-v9.json"))
        self.assertEqual(2, readme.count('--skill-dir "$BEFORE_SKILL"'))
        self.assertEqual(2, readme.count('--skill-dir "$AFTER_SKILL"'))
        for revision in (BEFORE, AFTER):
            self.assertIn(
                f"git archive {revision['source_commit']} skills/e2e-reviewer", readme
            )
        self.assertIn(
            "benchmarks/reviewer-holdout-v16/README.md",
            BENCHMARK_DOC_PATH.read_text(encoding="utf-8"),
        )
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
        release_section = changelog.split("## [2.0.0]", 1)[1].split("\n## [", 1)[0]
        self.assertIn(PROTOCOL_ID, release_section)
        self.assertIn("scripts/ci/test-reviewer-holdout-v16.py", release_section)
        for path in (CI_LOCAL_PATH, CONTRIBUTING_PATH):
            self.assertIn(
                "scripts/ci/test-reviewer-holdout-v16.py", path.read_text(encoding="utf-8")
            )


    def test_run_reports(self) -> None:
        reports = README_PATH.parent / "reports"
        comparison = read_json(reports / "revision-comparison.json")
        self.assertEqual("NOT_SUPPORTED", comparison["status"])
        self.assertEqual(EXPECTED_PROTOCOL_SHA256, comparison["protocol_sha256"])
        readme = README_PATH.read_text(encoding="utf-8")
        for revision, pinned in (("before", BEFORE), ("after", AFTER)):
            for arm in ("full", "catalog-only"):
                report = read_json(reports / f"{arm}-{revision}.json")
                self.assertEqual(EXPECTED_PROTOCOL_SHA256, report["protocol_sha256"])
                self.assertEqual(pinned["skill_sha256"], report["skill_sha256"])
                self.assertEqual(0, report["summary"]["infrastructure_errors"])
                self.assertEqual(0, report["infrastructure_retry_summary"]["retries"])
        def signed(value: float) -> str:
            return f"{value:+.3f}".replace("-", "\u2212")

        for arm in ("full", "catalog-only"):
            row = comparison["comparison"]["arms"][arm]
            interval = row["intervals"]["stable_f1"]
            self.assertIn(
                f"| {arm} | {row['before']['stable_f1']:.3f} | {row['after']['stable_f1']:.3f} "
                f"| {signed(row['delta']['stable_f1'])} "
                f"({signed(interval['lower'])} to {signed(interval['upper'])}) |",
                readme,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
