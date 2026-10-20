#!/usr/bin/env python3
"""Validate the preregistered Codex gpt-6-sol v12 protocol on the reused v10 corpus."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
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
V11_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v11.json"
V12_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v12.json"
V13_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v13.json"
V10_FILES_PATH = ROOT / "scripts/evals/files/holdout-v10"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
V5_TEST_PATH = ROOT / "scripts/ci/test-reviewer-holdout-v5.py"
README_PATH = ROOT / "benchmarks/reviewer-holdout-v12/README.md"
V11_README_PATH = ROOT / "benchmarks/reviewer-holdout-v11/README.md"
BENCHMARK_DOC_PATH = ROOT / "docs/ai-reviewer-benchmark.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
CONTRIBUTING_PATH = ROOT / "CONTRIBUTING.md"
CI_LOCAL_PATH = ROOT / "scripts/ci/ci-local.sh"

# v12 reuses the frozen v10 corpus: these are v10's digests, unchanged.
EXPECTED_CASES_FILE_SHA256 = "6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e"
EXPECTED_CORPUS_SHA256 = "672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d"
EXPECTED_V10_PROTOCOL_SHA256 = "186680ad624f9ae40ff0b652ee4949322fb6ccfac5e5426a4b7c182278f33c39"
EXPECTED_V11_PROTOCOL_SHA256 = "5676b452de7d6fce7ae7292bf21248b2dbeef3eeb493175cf85024299dee1bf1"
EXPECTED_PROTOCOL_SHA256 = "ec42df85e7161ca96a807cbd0079eb9c406b926ae0c40bb4214f2b88280a5d20"
PROTOCOL_ID = "reviewer-holdout-v12"
V10_ID = "reviewer-holdout-v10"
V11_ID = "reviewer-holdout-v11"
V13_ID = "reviewer-holdout-v13"
V14_ID = "reviewer-holdout-v14"
V15_ID = "reviewer-holdout-v15"
HOST = {"runner": "codex", "model": "gpt-6-sol"}
IDENTITY = {"codex": "codex-cli 0.155.1"}
REUSERS = {V11_ID, PROTOCOL_ID, V13_ID, V14_ID, V15_ID}

# v16 carries the same retry policy on the reused v9 corpus.
V16_ID = "reviewer-holdout-v16"
V17_ID = "reviewer-holdout-v17"
V18_ID = "reviewer-holdout-v18"
V19_ID = "reviewer-holdout-v19"
V20_ID = "reviewer-holdout-v20"
V21_ID = "reviewer-holdout-v21"
V9_OWNER_ID = "reviewer-holdout-v9"
V9_OWNER_PROTOCOL_PATH = ROOT / "scripts/evals/reviewer-validation-protocol-v9.json"
STUB_CASE = "v10-pw-01"
STUB_TIMEOUT_SECONDS = 10  # headroom for a loaded machine; the timeout stub sleeps 30 s

# The same stub runner as the v11 suite: it reads the next action from PLAN,
# counts itself in COUNT, and never calls a model.
STUB_TEMPLATE = """#!/bin/sh
/bin/cat >/dev/null
n=$(/bin/cat '{count}' 2>/dev/null || echo 0)
n=$((n + 1))
echo "$n" > '{count}'
action=$(/usr/bin/sed -n "${{n}}p" '{plan}')
case "$action" in
  timeout) /bin/sleep 30 ;;
  ok) printf '%s' '{{"findings":[]}}' ;;
  wrong) printf '%s' '{{"findings":[{{"pattern_id":"#9","severity":"P1","file":"tests/unrelated.spec.ts","line":1}}]}}' ;;
  malformed) printf '%s' '{{"findings":[' ;;
  usage_stderr) echo "Error: You've hit your usage limit. Try again later." >&2; exit 1 ;;
  crash) echo "internal failure" >&2; exit 3 ;;
  *) echo "unplanned invocation $n" >&2; exit 9 ;;
esac
"""


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewerHoldoutV12Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("reviewer_holdout_v12_runner", RUNNER_PATH)
        cls.comparator = load_module("reviewer_holdout_v12_comparator", COMPARATOR_PATH)
        cls.v5_helpers = load_module("reviewer_holdout_v12_v5_helpers", V5_TEST_PATH)
        cls.v7 = read_json(V7_PROTOCOL_PATH)
        cls.v8 = read_json(V8_PROTOCOL_PATH)
        cls.v9 = read_json(V9_PROTOCOL_PATH)
        cls.v10 = read_json(V10_PROTOCOL_PATH)
        cls.v11 = read_json(V11_PROTOCOL_PATH)
        cls.v12 = read_json(V12_PROTOCOL_PATH)
        cls.v13 = read_json(V13_PROTOCOL_PATH)
        cls.v5_metadata, _ = cls.runner.load_cases(V5_CASES_PATH)
        cls.v8_metadata, _ = cls.runner.load_cases(V8_CASES_PATH)
        cls.v9_metadata, cls.v9_cases = cls.runner.load_cases(V9_CASES_PATH)
        cls.v10_metadata, cls.v10_cases = cls.runner.load_cases(V10_CASES_PATH)

    def load_mutated(self, temp: str, data: dict, name: str = "protocol.json") -> dict:
        path = Path(temp) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return self.runner.load_protocol(path)

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
            hashlib.sha256(V12_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        # The reused v10 protocol and the stopped v11 protocol are untouched.
        self.assertEqual(
            EXPECTED_V10_PROTOCOL_SHA256,
            hashlib.sha256(V10_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            EXPECTED_V11_PROTOCOL_SHA256,
            hashlib.sha256(V11_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(self.v12, self.runner.load_protocol(V12_PROTOCOL_PATH))
        self.assertEqual(V12_PROTOCOL_PATH, self.runner.V12_PROTOCOL)
        self.assertEqual(
            {
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
                "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            },
            self.runner.PINNED_LIVE_INPUTS[(V10_CASES_PATH, V12_PROTOCOL_PATH)],
        )
        # Only the v10 corpus is pinned for v12.
        self.assertEqual(
            [(V10_CASES_PATH, V12_PROTOCOL_PATH)],
            [key for key in self.runner.PINNED_LIVE_INPUTS if key[1] == V12_PROTOCOL_PATH],
        )
        self.assertEqual(self.v10["corpus"], self.v12["corpus"])
        for id_set in (
            "SUPPORTED_PROTOCOL_IDS",
            "STRICT_MAJORITY_PROTOCOL_IDS",
            "PROMPT_ARM_PROTOCOL_IDS",
            "ARM_COMPARISON_PROTOCOL_IDS",
            "CODEX_ONLY_PROTOCOL_IDS",
            "NUMBERED_SOURCE_PROTOCOL_IDS",
            "REVISED_LABEL_PROTOCOL_IDS",
            "DESIGNED_LABEL_PROTOCOL_IDS",
            "INFRASTRUCTURE_RETRY_PROTOCOL_IDS",
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
        self.assertEqual(REUSERS | {V16_ID, V17_ID, V18_ID, V19_ID, V20_ID, V21_ID, "reviewer-holdout-v22", "reviewer-holdout-v23", "reviewer-holdout-v24"}, self.runner.INFRASTRUCTURE_RETRY_PROTOCOL_IDS)
        self.assertEqual(V10_CASES_PATH, self.runner.REVISED_LABEL_CORPORA[PROTOCOL_ID])
        self.assertEqual(
            {**{reuser: V10_ID for reuser in REUSERS}, V16_ID: V9_OWNER_ID, V18_ID: V17_ID, V19_ID: V17_ID, "reviewer-holdout-v22": V17_ID, "reviewer-holdout-v23": V17_ID, "reviewer-holdout-v24": V17_ID},
            self.runner.SHARED_CORPUS_PROTOCOLS,
        )
        self.assertEqual(
            {V9_OWNER_ID: V9_OWNER_PROTOCOL_PATH, V10_ID: V10_PROTOCOL_PATH,
             V17_ID: ROOT / "scripts/evals/reviewer-validation-protocol-v17.json"},
            self.runner.SHARED_CORPUS_OWNER_PROTOCOLS,
        )
        self.assertEqual("minimum", self.runner.FROZEN_EXECUTION_IDENTITY_POLICIES[PROTOCOL_ID])
        self.assertEqual(IDENTITY, self.runner.FROZEN_EXECUTION_IDENTITIES[PROTOCOL_ID])
        self.assertEqual(HOST, self.runner.REVISED_LABEL_HOSTS[PROTOCOL_ID])
        self.assertNotIn(PROTOCOL_ID, self.runner.REQUIRED_CLAUDE_PERMISSION_MODES)

    def test_protocol_changes_only_the_model_from_v11(self) -> None:
        v11 = copy.deepcopy(self.v11)
        v12 = copy.deepcopy(self.v12)
        self.assertEqual(PROTOCOL_ID, v12.pop("protocol_id"))
        v11.pop("protocol_id")
        disclosure = v12["schedule"].pop("design_disclosure")
        v11["schedule"].pop("design_disclosure")
        for phrase in (
            "preregistered on Codex gpt-5.6-sol",
            "stopped during the full arm, before completion, when that model was retired",
            "no v11 result is claimed",
            "gpt-5.6-sol and Claude holdouts used claude-opus-5 for continuity",
            "the models users now run by default are gpt-6-sol on Codex and "
            "claude-sonnet-5 on Claude",
            "V12 replaces v11 as the Codex run",
            "reuses the frozen v10 corpus unchanged by path and digest",
            "codex-cli 0.155.1 floor",
            "full versus catalog-only and skill versus no-skill questions",
            "not a fresh-corpus test for the author",
            "no model has seen the corpus except through those runs, which do not train models",
            "about 0.009 on Claude opus and 0.012 on Codex gpt-5.6-sol",
            "about 0.025 to 0.033 at 80% power",
            "infrastructure-retry policy unchanged",
            "a scoreable output is never retried",
            "five repetitions",
            "public development evidence",
        ):
            self.assertIn(phrase, disclosure)
        self.assertNotIn("is being run", disclosure)
        # Only the model changes; the identity, retry policy, corpus, and every
        # v10 field carried by v11 are v11's byte for byte.
        v11["host_matrix"] = [HOST]
        for step in v11["arm_comparison"]["execution_order"]:
            step["model"] = HOST["model"]
        self.assertEqual(v11, v12)
        self.assertEqual(list(self.v11), list(self.v12))
        self.assertEqual(self.v11["infrastructure_retry"], self.v12["infrastructure_retry"])
        self.assertEqual(
            self.runner.EXPECTED_INFRASTRUCTURE_RETRY, self.v12["infrastructure_retry"]
        )
        self.assertEqual(self.v11["execution_identity"], self.v12["execution_identity"])
        self.assertNotIn("claude_permission_mode", self.v12["execution_identity"])
        self.assertEqual(
            [
                {"ordinal": 1, "prompt_profile": "full", **HOST},
                {"ordinal": 2, "prompt_profile": "catalog-only", **HOST},
                {"ordinal": 3, "prompt_profile": "no-skill", **HOST},
            ],
            self.v12["arm_comparison"]["execution_order"],
        )
        self.assertEqual(5, self.v12["schedule"]["default_repetitions"])
        self.assertEqual(20260801, self.v12["schedule"]["seed"])

    def test_protocol_validation_pins_v12_fields(self) -> None:
        other_order = [
            {**step, "model": "gpt-5.6-sol"}
            for step in self.v12["arm_comparison"]["execution_order"]
        ]
        mutations = {
            "three repetitions": lambda data: data["schedule"].update(
                {"default_repetitions": 3, "release_repetitions": 3}
            ),
            "scoring drift": lambda data: data["scoring"].update(
                {"label_semantics": "exact"}
            ),
            "retired codex model": lambda data: data.update(
                {"host_matrix": [{"runner": "codex", "model": "gpt-5.6-sol"}]}
            ),
            "claude host": lambda data: data.update(
                {"host_matrix": [{"runner": "claude", "model": "claude-sonnet-5"}]}
            ),
            "second host": lambda data: data["host_matrix"].append(
                {"runner": "claude", "model": "claude-sonnet-5"}
            ),
            "execution order model": lambda data: data["arm_comparison"].update(
                {"execution_order": other_order}
            ),
            "older codex floor": lambda data: data["execution_identity"].update(
                {"expected_cli_versions": {"codex": "codex-cli 0.154.0"}}
            ),
            "claude identity": lambda data: data["execution_identity"].update(
                {"expected_cli_versions": {"claude": "Claude Code 2.1.281"}}
            ),
            "exact policy": lambda data: data["execution_identity"].update(
                {"version_policy": "exact"}
            ),
            "missing disclosure": lambda data: data["schedule"].update(
                {"design_disclosure": " "}
            ),
            "missing retry policy": lambda data: data.pop("infrastructure_retry"),
            "three attempts": lambda data: data["infrastructure_retry"].update(
                {"max_attempts_per_call": 3}
            ),
            "one attempt": lambda data: data["infrastructure_retry"].update(
                {"max_attempts_per_call": 1}
            ),
            "extra reason": lambda data: data["infrastructure_retry"]["retryable"].append(
                "runner_nonzero_exit"
            ),
            "dropped reason": lambda data: data["infrastructure_retry"]["retryable"].pop(),
            "contract drift": lambda data: data["infrastructure_retry"].update(
                {"contract": "Retry anything."}
            ),
            "stricter thresholds": lambda data: data["arm_comparison"]["decision"][
                "thresholds"
            ].update({"stable_f1_delta_min": 0.02}),
            "other seed": lambda data: data["arm_comparison"]["uncertainty"].update(
                {"seed": 1}
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, mutate in mutations.items():
                data = copy.deepcopy(self.v12)
                mutate(data)
                with self.subTest(name), self.assertRaises(ValueError):
                    self.load_mutated(temp, data)

    def test_retry_policy_is_limited_to_v11_v12_v13(self) -> None:
        self.assertEqual(
            self.v12["infrastructure_retry"],
            self.runner.infrastructure_retry_policy(self.v12),
        )
        for protocol_id in sorted(self.runner.SUPPORTED_PROTOCOL_IDS - REUSERS - {V16_ID, V17_ID, V18_ID, V19_ID, V20_ID, V21_ID, "reviewer-holdout-v22", "reviewer-holdout-v23", "reviewer-holdout-v24"}):
            self.assertIsNone(
                self.runner.infrastructure_retry_policy({"protocol_id": protocol_id}),
                protocol_id,
            )
        with tempfile.TemporaryDirectory() as temp:
            for name, protocol in (("v10", self.v10), ("v9", self.v9), ("v8", self.v8)):
                data = copy.deepcopy(protocol)
                data["infrastructure_retry"] = copy.deepcopy(
                    self.runner.EXPECTED_INFRASTRUCTURE_RETRY
                )
                with self.subTest(name), self.assertRaisesRegex(ValueError, "unknown="):
                    self.load_mutated(temp, data, f"{name}.json")

    # Corpus binding --------------------------------------------------------

    def test_corpus_reuse_is_limited_to_the_v10_reusers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            for corpus in (
                "scripts/evals/reviewer-holdout-v9.json",
                "scripts/evals/reviewer-holdout-v8.json",
                "scripts/evals/reviewer-holdout-v5.json",
            ):
                data = copy.deepcopy(self.v12)
                data["corpus"]["path"] = corpus
                with self.subTest(corpus), self.assertRaisesRegex(
                    ValueError, "must be the v10 corpus"
                ):
                    self.load_mutated(temp, data)
            for key in ("cases_file_sha256", "corpus_sha256"):
                data = copy.deepcopy(self.v12)
                data["corpus"][key] = "0" * 64
                with self.subTest(key), self.assertRaisesRegex(ValueError, "frozen digests"):
                    self.load_mutated(temp, data)
            for protocol, name in ((self.v9, "v9"), (self.v8, "v8")):
                data = copy.deepcopy(protocol)
                data["corpus"]["path"] = "scripts/evals/reviewer-holdout-v10.json"
                with self.subTest(name), self.assertRaisesRegex(
                    ValueError, f"must be the {name} corpus"
                ):
                    self.load_mutated(temp, data, f"{name}.json")
            # A protocol that is not a declared reuser cannot share the corpus,
            # even if the corpus table were extended to let it.
            with mock.patch.dict(
                self.runner.REVISED_LABEL_CORPORA, {"reviewer-holdout-v9": V10_CASES_PATH}
            ):
                data = copy.deepcopy(self.v9)
                data["corpus"] = copy.deepcopy(self.v10["corpus"])
                with self.assertRaisesRegex(ValueError, "may not share its corpus"):
                    self.load_mutated(temp, data, "v9-shared.json")
                with self.assertRaisesRegex(ValueError, "may not share its corpus"):
                    self.runner.load_protocol(V12_PROTOCOL_PATH)
            # Dropping v12 from the reuser table makes the shared corpus illegal.
            reusers = dict(self.runner.SHARED_CORPUS_PROTOCOLS)
            reusers.pop(PROTOCOL_ID)
            with mock.patch.object(self.runner, "SHARED_CORPUS_PROTOCOLS", reusers):
                with self.assertRaisesRegex(ValueError, "may not share its corpus"):
                    self.runner.load_protocol(V12_PROTOCOL_PATH)
        # Every sanctioned protocol still loads with the v10 corpus.
        for path in (V10_PROTOCOL_PATH, V11_PROTOCOL_PATH, V13_PROTOCOL_PATH):
            self.assertEqual(read_json(path), self.runner.load_protocol(path))

    def test_corpus_and_protocol_pairing(self) -> None:
        for pairing in (
            self.runner.validate_corpus_protocol_pairing,
            self.comparator.RUNNER.validate_corpus_protocol_pairing,
        ):
            pairing(self.v10_metadata, self.v12, EXPECTED_CORPUS_SHA256)
            v9_digest = self.runner.corpus_digest(V9_CASES_PATH, self.v9_cases)
            with self.assertRaisesRegex(ValueError, "corpus digest"):
                pairing(self.v9_metadata, self.v12, v9_digest)
            with self.assertRaisesRegex(ValueError, "corpus digest"):
                pairing(self.v10_metadata, self.v12, "0" * 64)
            with self.assertRaisesRegex(ValueError, "requires a corpus that declares labeling"):
                pairing(self.v8_metadata, self.v12)
            with self.assertRaisesRegex(ValueError, "requires a corpus that declares labeling"):
                pairing(self.v5_metadata, self.v12)

    # Prompt rendering --------------------------------------------------------

    def test_prompts_are_numbered_and_never_leak_labels(self) -> None:
        numbered = PROTOCOL_ID in self.runner.NUMBERED_SOURCE_PROTOCOL_IDS
        self.assertTrue(numbered)
        with tempfile.TemporaryDirectory() as temp:
            for case in self.v10_cases:
                workspace = Path(temp) / case["id"]
                shutil.copytree(self.runner.DEFAULT_SKILL_DIR, workspace / ".skill/e2e-reviewer")
                for source in case["source_files"]:
                    target = workspace / source["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(V10_CASES_PATH.parent / source["source"], target)
                for profile in ("full", "catalog-only", "no-skill"):
                    prompt = self.runner.render_prompt(
                        case, workspace, profile, numbered_source_lines=numbered
                    )
                    self.assertIn("Cite that displayed number as the line", prompt)
                    self.assertNotIn(case["design_note"], prompt)
                    self.assertNotIn(case["id"], prompt)
                    for marker in (
                        "V10-", "holdout-v10", "holdout-v11", "holdout-v12",
                        "holdout-v13", "infrastructure_retry", "gpt-6-sol",
                        "claude-sonnet-5",
                    ):
                        self.assertNotIn(marker, prompt)
                    for label in case["labels"]:
                        self.assertNotIn(label["reason"], prompt)
        for path in V10_FILES_PATH.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for marker in ("V10-", "fp_guard", "design_note", "holdout"):
                    self.assertNotIn(marker, text, path)

    def test_prompts_and_schedule_match_v10(self) -> None:
        for profile in ("full", "catalog-only", "no-skill"):
            self.assertEqual(
                self.runner.prompt_set_digest(
                    self.v10_cases, EXPECTED_CORPUS_SHA256,
                    self.runner.DEFAULT_SKILL_DIR, profile,
                    numbered_source_lines=V10_ID in self.runner.NUMBERED_SOURCE_PROTOCOL_IDS,
                ),
                self.runner.prompt_set_digest(
                    self.v10_cases, EXPECTED_CORPUS_SHA256,
                    self.runner.DEFAULT_SKILL_DIR, profile,
                    numbered_source_lines=PROTOCOL_ID
                    in self.runner.NUMBERED_SOURCE_PROTOCOL_IDS,
                ),
            )
        v10_schedule = self.runner.build_schedule(
            self.v10_cases, 5, self.v10["schedule"]["seed"]
        )
        v12_schedule = self.runner.build_schedule(
            self.v10_cases, 5, self.v12["schedule"]["seed"]
        )
        self.assertEqual(v10_schedule, v12_schedule)
        self.assertEqual(150, len(v12_schedule))

    # Stub-runner retries -----------------------------------------------------

    def run_stub(self, temp: Path, plan: list[str]):
        count = temp / "count"
        plan_path = temp / "plan"
        plan_path.write_text("\n".join(plan) + "\n", encoding="utf-8")
        stub = temp / "stub-runner"
        stub.write_text(STUB_TEMPLATE.format(count=count, plan=plan_path), encoding="utf-8")
        stub.chmod(0o755)
        wrapper = temp / "isolation-wrapper"
        wrapper.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
        output = temp / "report.json"
        result = subprocess.run(
            [
                "python3", str(RUNNER_PATH),
                "--cases", str(V10_CASES_PATH),
                "--protocol", str(V12_PROTOCOL_PATH),
                "--case", STUB_CASE,
                "--runner", str(stub),
                "--isolation-wrapper", str(wrapper),
                "--repetitions", "1",
                "--timeout", str(STUB_TIMEOUT_SECONDS),
                "--output", str(output),
            ],
            cwd=ROOT,
            env={**os.environ, "LC_ALL": "C", "LANG": "C"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertTrue(output.is_file(), result.stdout)
        report = read_json(output)
        invocations = int(count.read_text(encoding="utf-8").strip())
        self.assertEqual(1, len(report["runs"]), result.stdout)
        self.comparator.load_report(output)
        self.assertEqual(PROTOCOL_ID, report["protocol_id"])
        self.assertEqual(self.v12["infrastructure_retry"], report["infrastructure_retry"])
        self.assertEqual(
            self.runner.infrastructure_retry_summary(report["runs"]),
            report["infrastructure_retry_summary"],
        )
        self.comparator.validate_retry_records(report, self.v12["infrastructure_retry"])
        return report, report["runs"][0], invocations

    def test_retryable_failures_are_retried_once(self) -> None:
        for first, reason in (
            ("timeout", "timeout"),
            ("malformed", "malformed_json_output"),
            ("usage_stderr", "runner_nonzero_exit_with_usage_limit_text"),
        ):
            with self.subTest(first), tempfile.TemporaryDirectory() as temp:
                report, run, invocations = self.run_stub(Path(temp), [first, "ok"])
                self.assertEqual(2, invocations)
                self.assertEqual(
                    [reason, None], [attempt["reason"] for attempt in run["attempts"]]
                )
                self.assertIsNone(run["error"])
                self.assertIsNotNone(run["score"])
                self.assertEqual(
                    1, report["infrastructure_retry_summary"]["retries_by_reason"][reason]
                )

    def test_scoreable_or_unrecognized_output_is_never_retried(self) -> None:
        for first in ("wrong", "crash"):
            with self.subTest(first), tempfile.TemporaryDirectory() as temp:
                report, run, invocations = self.run_stub(Path(temp), [first, "ok"])
                self.assertEqual(1, invocations)
                self.assertEqual([None], [attempt["reason"] for attempt in run["attempts"]])
                self.assertEqual(0, report["infrastructure_retry_summary"]["retries"])

    # Comparator ------------------------------------------------------------

    def test_single_host_comparator_is_decisive_for_v12(self) -> None:
        cases = self.v5_helpers.synthetic_arm_cases()
        reports = [
            self.v5_helpers.synthetic_arm_report(
                self.comparator,
                profile,
                HOST["runner"],
                HOST["model"],
                "strong" if profile == "full" else "weak",
                cases,
            )
            for profile in ("full", "catalog-only", "no-skill")
        ]
        for report in reports:
            report["runner_identity"] = "codex-cli 0.155.1"
        by_profile = {report["prompt_profile"]: report for report in reports}
        for step in self.v12["arm_comparison"]["execution_order"]:
            report = by_profile[step["prompt_profile"]]
            report["started_at"] = f"2026-10-01T00:00:0{step['ordinal'] - 1}+00:00"
            report["created_at"] = f"2026-10-01T00:00:0{step['ordinal']}+00:00"
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
                reports, cases, "a" * 64, self.v12, "b" * 64,
                "public-development", "development",
            )
        self.assertEqual("PASS", result["status"])
        self.assertEqual(
            "exact-three-profiles-by-one-host", result["metrics"]["comparison_unit"]
        )

    # Documentation ---------------------------------------------------------

    def test_readme_documents_preregistration_and_exact_rerun(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("# Reviewer holdout v12", readme.splitlines()[0])
        self.assertIn("arm comparison `FAIL`, so no skill-lift claim", readme)
        calls = len(self.v10_cases) * 5 * 3
        self.assertEqual(450, calls)
        for contract in (
            f"{calls} scheduled model calls",
            "scripts/evals/reviewer-holdout-v10.json",
            "scripts/evals/reviewer-validation-protocol-v12.json",
            EXPECTED_CASES_FILE_SHA256,
            EXPECTED_CORPUS_SHA256,
            EXPECTED_PROTOCOL_SHA256,
            "codex-cli 0.155.1",
            "gpt-6-sol",
            "claude-sonnet-5",
            "--compare-arms",
            'test -z "$(git status --porcelain)"',
            "## Why v12 exists",
            "## Infrastructure-retry policy",
            "## Claim limits",
            "about 0.009 on Claude opus",
            "about 0.012 on Codex `gpt-5.6-sol`",
            "0.025–0.033",
            "stopped during the full arm",
            "No v11 result is claimed",
            "which do not train models",
            '"max_attempts_per_call": 2',
            "never retried",
        ):
            self.assertIn(contract, readme)
        self.assertNotIn("is being run", readme)
        self.assertEqual(3, readme.count("--repetitions 5"))
        self.assertEqual(0, readme.count("--repetitions 3"))
        self.assertEqual(4, readme.count('--output "$OUT/'))
        self.assertEqual(3, len(re.findall(r"--arm (full|catalog-only|no-skill) ", readme)))
        self.assertEqual(3, readme.count("--allow-live"))
        self.assertEqual(3, readme.count("--model gpt-6-sol"))
        self.assertEqual(4, readme.count("--protocol scripts/evals/reviewer-validation-protocol-v12.json"))
        self.assertEqual(4, readme.count("--cases scripts/evals/reviewer-holdout-v10.json"))
        self.assertFalse((README_PATH.parent / "attempts").exists())
        self.assertIn(
            "benchmarks/reviewer-holdout-v12/README.md",
            BENCHMARK_DOC_PATH.read_text(encoding="utf-8"),
        )
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
        release_section = changelog.split("## [2.0.0]", 1)[1].split("\n## [", 1)[0]
        added = release_section.split("### Added", 1)[1].split("\n### ", 1)[0]
        self.assertIn(PROTOCOL_ID, added)
        self.assertIn("scripts/ci/test-reviewer-holdout-v12.py", added)
        for path in (CI_LOCAL_PATH, CONTRIBUTING_PATH):
            self.assertIn(
                "scripts/ci/test-reviewer-holdout-v12.py", path.read_text(encoding="utf-8")
            )
        # The v11 record says its run was stopped and v12 replaces it.
        self.assertIn(
            "Status: preregistered; the official run was stopped during the full arm "
            "when gpt-5.6-sol was retired, and v12 (gpt-6-sol) replaces it. "
            "No v11 result is claimed.",
            V11_README_PATH.read_text(encoding="utf-8"),
        )

    def test_counted_reports(self) -> None:
        reports = README_PATH.parent / "reports"
        comparison = read_json(reports / "arm-comparison.json")
        self.assertEqual("FAIL", comparison["status"])
        self.assertFalse(comparison["skill_lift_claim_eligible"])
        readme = README_PATH.read_text(encoding="utf-8")
        for arm, status in (("full", "PASS"), ("catalog-only", "FAIL"), ("no-skill", "FAIL")):
            report = read_json(reports / f"{arm}-codex.json")
            self.assertEqual(status, report["status"], arm)
            self.assertEqual(0, report["summary"]["infrastructure_errors"], arm)
            unique = report["primary_metrics"]["unique"]
            self.assertIn(f"{unique['precision']:.3f} / {unique['recall']:.3f} / {unique['f1']:.3f}", readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
