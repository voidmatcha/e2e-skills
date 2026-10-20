#!/usr/bin/env python3
"""Validate the preregistered Codex v11 protocol, its reused v10 corpus, and retries."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
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
V10_FILES_PATH = ROOT / "scripts/evals/files/holdout-v10"
RUNNER_PATH = ROOT / "scripts/evals/run-reviewer-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
V5_TEST_PATH = ROOT / "scripts/ci/test-reviewer-holdout-v5.py"
README_PATH = ROOT / "benchmarks/reviewer-holdout-v11/README.md"
V10_README_PATH = ROOT / "benchmarks/reviewer-holdout-v10/README.md"
BENCHMARK_DOC_PATH = ROOT / "docs/ai-reviewer-benchmark.md"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
CONTRIBUTING_PATH = ROOT / "CONTRIBUTING.md"
CI_LOCAL_PATH = ROOT / "scripts/ci/ci-local.sh"

# v11 reuses the frozen v10 corpus: these are v10's digests, unchanged.
EXPECTED_CASES_FILE_SHA256 = "6db718fe63001f987901a68ee230809c56fda2df5e97d3f0b83ab382b953cc5e"
EXPECTED_CORPUS_SHA256 = "672f99fc323cf72cb9946483b01f7df314ee12000bcc40b5aa3eb1efb2f8cb8d"
EXPECTED_V10_PROTOCOL_SHA256 = "186680ad624f9ae40ff0b652ee4949322fb6ccfac5e5426a4b7c182278f33c39"
EXPECTED_PROTOCOL_SHA256 = "5676b452de7d6fce7ae7292bf21248b2dbeef3eeb493175cf85024299dee1bf1"
PROTOCOL_ID = "reviewer-holdout-v11"
V10_ID = "reviewer-holdout-v10"
EXPECTED_RETRY_REASONS = [
    "timeout",
    "runner_nonzero_exit_with_usage_limit_text",
    "malformed_json_output",
]
STUB_CASE = "v10-pw-01"
STUB_TIMEOUT_SECONDS = 10  # headroom for a loaded machine; the timeout stub sleeps 30 s


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def as_finding(item: dict) -> dict:
    return {key: item[key] for key in ("pattern_id", "severity", "file", "line")}


# A stub runner: each invocation reads the next action from PLAN and counts
# itself in COUNT. It never calls a model.
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
  usage_stdout) echo "You've hit your weekly limit - resets Oct 1"; exit 1 ;;
  crash) echo "internal failure" >&2; exit 3 ;;
  *) echo "unplanned invocation $n" >&2; exit 9 ;;
esac
"""


class ReviewerHoldoutV11Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("reviewer_holdout_v11_runner", RUNNER_PATH)
        cls.comparator = load_module("reviewer_holdout_v11_comparator", COMPARATOR_PATH)
        cls.v5_helpers = load_module("reviewer_holdout_v11_v5_helpers", V5_TEST_PATH)
        cls.v7 = read_json(V7_PROTOCOL_PATH)
        cls.v8 = read_json(V8_PROTOCOL_PATH)
        cls.v9 = read_json(V9_PROTOCOL_PATH)
        cls.v10 = read_json(V10_PROTOCOL_PATH)
        cls.v11 = read_json(V11_PROTOCOL_PATH)
        cls.v5_metadata, _ = cls.runner.load_cases(V5_CASES_PATH)
        cls.v8_metadata, _ = cls.runner.load_cases(V8_CASES_PATH)
        cls.v9_metadata, cls.v9_cases = cls.runner.load_cases(V9_CASES_PATH)
        cls.v10_metadata, cls.v10_cases = cls.runner.load_cases(V10_CASES_PATH)
        cls.v10_by_id = {case["id"]: case for case in cls.v10_cases}

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
            hashlib.sha256(V11_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        # The reused v10 protocol is untouched.
        self.assertEqual(
            EXPECTED_V10_PROTOCOL_SHA256,
            hashlib.sha256(V10_PROTOCOL_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(self.v11, self.runner.load_protocol(V11_PROTOCOL_PATH))
        self.assertEqual(V11_PROTOCOL_PATH, self.runner.V11_PROTOCOL)
        self.assertEqual(
            {
                "cases_file_sha256": EXPECTED_CASES_FILE_SHA256,
                "corpus_sha256": EXPECTED_CORPUS_SHA256,
                "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
            },
            self.runner.PINNED_LIVE_INPUTS[(V10_CASES_PATH, V11_PROTOCOL_PATH)],
        )
        self.assertEqual(
            self.runner.PINNED_LIVE_INPUTS[(V10_CASES_PATH, V10_PROTOCOL_PATH)][
                "protocol_sha256"
            ],
            EXPECTED_V10_PROTOCOL_SHA256,
        )
        self.assertEqual(self.v10["corpus"], self.v11["corpus"])
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
        # v12 through v15 carry the same policy on the same reused corpus, v16
        # carries it on the reused v9 corpus; later preregistrations keep the policy.
        self.assertEqual(
            {PROTOCOL_ID, "reviewer-holdout-v12", "reviewer-holdout-v13", "reviewer-holdout-v14",
             "reviewer-holdout-v15", "reviewer-holdout-v16", "reviewer-holdout-v17", "reviewer-holdout-v18", "reviewer-holdout-v19", "reviewer-holdout-v20", "reviewer-holdout-v21", "reviewer-holdout-v22", "reviewer-holdout-v23", "reviewer-holdout-v24"},
            self.runner.INFRASTRUCTURE_RETRY_PROTOCOL_IDS,
        )
        self.assertEqual(V10_CASES_PATH, self.runner.REVISED_LABEL_CORPORA[PROTOCOL_ID])
        self.assertEqual(
            {
                PROTOCOL_ID: V10_ID,
                "reviewer-holdout-v12": V10_ID,
                "reviewer-holdout-v13": V10_ID,
                "reviewer-holdout-v14": V10_ID,
                "reviewer-holdout-v15": V10_ID,
                "reviewer-holdout-v16": "reviewer-holdout-v9",
                "reviewer-holdout-v18": "reviewer-holdout-v17",
                "reviewer-holdout-v19": "reviewer-holdout-v17", "reviewer-holdout-v22": "reviewer-holdout-v17", "reviewer-holdout-v23": "reviewer-holdout-v17", "reviewer-holdout-v24": "reviewer-holdout-v17",
            },
            self.runner.SHARED_CORPUS_PROTOCOLS,
        )
        self.assertEqual("minimum", self.runner.FROZEN_EXECUTION_IDENTITY_POLICIES[PROTOCOL_ID])
        self.assertEqual(
            {"codex": "codex-cli 0.155.1"},
            self.runner.FROZEN_EXECUTION_IDENTITIES[PROTOCOL_ID],
        )
        self.assertEqual(
            {"runner": "codex", "model": "gpt-5.6-sol"},
            self.runner.REVISED_LABEL_HOSTS[PROTOCOL_ID],
        )

    def test_protocol_changes_only_disclosed_fields_from_v10(self) -> None:
        v10 = copy.deepcopy(self.v10)
        v11 = copy.deepcopy(self.v11)
        self.assertEqual(PROTOCOL_ID, v11.pop("protocol_id"))
        v10.pop("protocol_id")
        disclosure = v11["schedule"].pop("design_disclosure")
        v10["schedule"].pop("design_disclosure")
        for phrase in (
            "both attempts ended INCONCLUSIVE for infrastructure reasons",
            "weekly usage limit",
            "malformed-JSON output",
            "has not been run on Codex",
            "reuses the frozen v10 corpus unchanged by path and digest",
            "standard error of about 0.012",
            "about 0.033 at 80% power",
            "preregistered infrastructure-retry policy",
            "a scoreable output is never retried",
            "five repetitions",
            "public development evidence",
        ):
            self.assertIn(phrase, disclosure)
        self.assertEqual(
            self.runner.EXPECTED_INFRASTRUCTURE_RETRY, v11.pop("infrastructure_retry")
        )

        # Corpus, arms, scoring, thresholds, seed, and stability are v10's; only
        # the host, its identity, and the fields that name the host change.
        def host_neutral(protocol: dict) -> dict:
            protocol = copy.deepcopy(protocol)
            protocol.pop("host_matrix")
            protocol.pop("execution_identity")
            for step in protocol["arm_comparison"]["execution_order"]:
                step.pop("runner")
                step.pop("model")
            protocol["cross_host_decision"].pop("aggregation_intent", None)
            return protocol

        self.assertEqual(host_neutral(v10), host_neutral(v11))
        # The identity is v9's Codex identity.
        self.assertEqual(self.v9["execution_identity"], self.v11["execution_identity"])
        self.assertEqual(self.v9["host_matrix"], self.v11["host_matrix"])
        self.assertEqual(
            self.v9["arm_comparison"]["execution_order"],
            self.v11["arm_comparison"]["execution_order"],
        )
        self.assertEqual(
            self.v9["cross_host_decision"], self.v11["cross_host_decision"]
        )
        self.assertEqual(
            [key for key in self.v10 if key != "execution_identity"] ,
            [
                key for key in self.v11
                if key not in {"execution_identity", "infrastructure_retry"}
            ],
        )
        self.assertEqual(5, self.v11["schedule"]["default_repetitions"])
        self.assertEqual(20260801, self.v11["schedule"]["seed"])
        self.assertEqual(
            {
                "max_attempts_per_call": 2,
                "retryable": EXPECTED_RETRY_REASONS,
                "contract": self.runner.EXPECTED_INFRASTRUCTURE_RETRY["contract"],
            },
            self.v11["infrastructure_retry"],
        )

    def test_protocol_validation_pins_v11_fields(self) -> None:
        mutations = {
            "three repetitions": lambda data: data["schedule"].update(
                {"default_repetitions": 3, "release_repetitions": 3}
            ),
            "scoring drift": lambda data: data["scoring"].update(
                {"label_semantics": "exact"}
            ),
            "claude host": lambda data: data.update(
                {"host_matrix": [{"runner": "claude", "model": "claude-opus-5"}]}
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
            "reordered reasons": lambda data: data["infrastructure_retry"][
                "retryable"
            ].reverse(),
            "contract drift": lambda data: data["infrastructure_retry"].update(
                {"contract": "Retry anything."}
            ),
            "extra policy key": lambda data: data["infrastructure_retry"].update(
                {"backoff_seconds": 60}
            ),
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, mutate in mutations.items():
                data = copy.deepcopy(self.v11)
                mutate(data)
                path = Path(temp) / "protocol.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(name), self.assertRaises(ValueError):
                    self.runner.load_protocol(path)

    def test_no_other_protocol_may_declare_a_retry_policy(self) -> None:
        for protocol_id in sorted(
            self.runner.SUPPORTED_PROTOCOL_IDS - self.runner.INFRASTRUCTURE_RETRY_PROTOCOL_IDS
        ):
            self.assertIsNone(
                self.runner.infrastructure_retry_policy({"protocol_id": protocol_id}),
                protocol_id,
            )
        with tempfile.TemporaryDirectory() as temp:
            for name, protocol in (("v9", self.v9), ("v10", self.v10), ("v8", self.v8)):
                data = copy.deepcopy(protocol)
                data["infrastructure_retry"] = copy.deepcopy(
                    self.runner.EXPECTED_INFRASTRUCTURE_RETRY
                )
                path = Path(temp) / f"{name}.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(name), self.assertRaisesRegex(ValueError, "unknown="):
                    self.runner.load_protocol(path)

    # Corpus binding --------------------------------------------------------

    def test_corpus_reuse_is_allowed_for_v11_v12_v13_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            def load(data: dict, name: str) -> None:
                path = Path(temp) / name
                path.write_text(json.dumps(data), encoding="utf-8")
                self.runner.load_protocol(path)

            # v11 refuses any other corpus path.
            for corpus, owner in (
                ("scripts/evals/reviewer-holdout-v9.json", "v10"),
                ("scripts/evals/reviewer-holdout-v8.json", "v10"),
            ):
                data = copy.deepcopy(self.v11)
                data["corpus"]["path"] = corpus
                with self.subTest(corpus), self.assertRaisesRegex(
                    ValueError, f"must be the {owner} corpus"
                ):
                    load(data, "v11.json")
            # v11 refuses the v10 path at any digest other than v10's.
            for key in ("cases_file_sha256", "corpus_sha256"):
                data = copy.deepcopy(self.v11)
                data["corpus"][key] = "0" * 64
                with self.subTest(key), self.assertRaisesRegex(
                    ValueError, "frozen digests"
                ):
                    load(data, "v11.json")
            # Earlier protocols still refuse the v10 corpus path.
            for protocol, name in ((self.v9, "v9"), (self.v8, "v8")):
                data = copy.deepcopy(protocol)
                data["corpus"]["path"] = "scripts/evals/reviewer-holdout-v10.json"
                with self.subTest(name), self.assertRaisesRegex(
                    ValueError, f"must be the {name} corpus"
                ):
                    load(data, f"{name}.json")
            # A protocol that is not the declared reuser cannot share a corpus,
            # even if the corpus table were extended to let it.
            with mock.patch.dict(
                self.runner.REVISED_LABEL_CORPORA,
                {"reviewer-holdout-v9": V10_CASES_PATH},
            ):
                data = copy.deepcopy(self.v9)
                data["corpus"] = copy.deepcopy(self.v10["corpus"])
                with self.assertRaisesRegex(ValueError, "may not share its corpus"):
                    load(data, "v9-shared.json")
            # The v10 protocol still loads with its own corpus.
            self.assertEqual(self.v10, self.runner.load_protocol(V10_PROTOCOL_PATH))

    def test_corpus_and_protocol_pairing(self) -> None:
        pairing = self.runner.validate_corpus_protocol_pairing
        pairing(self.v10_metadata, self.v11, EXPECTED_CORPUS_SHA256)
        pairing(self.v10_metadata, self.v10, EXPECTED_CORPUS_SHA256)
        v9_digest = self.runner.corpus_digest(V9_CASES_PATH, self.v9_cases)
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            pairing(self.v9_metadata, self.v11, v9_digest)
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            pairing(self.v10_metadata, self.v11, "0" * 64)
        with self.assertRaisesRegex(ValueError, "corpus digest"):
            pairing(self.v10_metadata, self.v9, EXPECTED_CORPUS_SHA256)
        with self.assertRaisesRegex(ValueError, "requires a corpus that declares labeling"):
            pairing(self.v8_metadata, self.v11)
        with self.assertRaisesRegex(ValueError, "requires a corpus that declares labeling"):
            pairing(self.v5_metadata, self.v11)
        with self.assertRaisesRegex(ValueError, "declares label_revisions"):
            pairing(self.v10_metadata, self.v8)
        with self.assertRaisesRegex(ValueError, "does not support designed-label"):
            pairing(self.v10_metadata, self.v7)

    def test_comparator_uses_the_same_corpus_binding(self) -> None:
        # The comparator loads the protocol and pairs it with the corpus through
        # the runner module, so it refuses the same combinations.
        main_source = inspect.getsource(self.comparator.main)
        self.assertIn("RUNNER.load_protocol(snapshot_protocol_path)", main_source)
        self.assertIn("RUNNER.validate_corpus_protocol_pairing(", main_source)
        pairing = self.comparator.RUNNER.validate_corpus_protocol_pairing
        pairing(self.v10_metadata, self.v11, EXPECTED_CORPUS_SHA256)
        v9_digest = self.runner.corpus_digest(V9_CASES_PATH, self.v9_cases)
        for metadata, protocol, digest in (
            (self.v10_metadata, self.v9, EXPECTED_CORPUS_SHA256),
            (self.v9_metadata, self.v11, v9_digest),
        ):
            with self.subTest(protocol["protocol_id"]), self.assertRaisesRegex(
                ValueError, "corpus digest"
            ):
                pairing(metadata, protocol, digest)
        with tempfile.TemporaryDirectory() as temp:
            data = copy.deepcopy(self.v11)
            data["corpus"]["path"] = "scripts/evals/reviewer-holdout-v9.json"
            path = Path(temp) / "v11.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must be the v10 corpus"):
                self.comparator.RUNNER.load_protocol(path)

    # Prompt rendering --------------------------------------------------------

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
                numbered = PROTOCOL_ID in self.runner.NUMBERED_SOURCE_PROTOCOL_IDS
                self.assertTrue(numbered)
                for profile in ("full", "catalog-only", "no-skill"):
                    prompt = self.runner.render_prompt(
                        case, workspace, profile, numbered_source_lines=numbered
                    )
                    self.assertIn("Cite that displayed number as the line", prompt)
                    self.assertNotIn(case["design_note"], prompt)
                    self.assertNotIn("V10-", prompt)
                    self.assertNotIn("holdout-v10", prompt)
                    self.assertNotIn("holdout-v11", prompt)
                    self.assertNotIn(case["id"], prompt)
                    self.assertNotIn("infrastructure_retry", prompt)
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
        for path in V10_FILES_PATH.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                for marker in ("V10-", "fp_guard", "design_note", "holdout"):
                    self.assertNotIn(marker, text, path)

    def test_prompts_and_schedule_match_v10(self) -> None:
        # Same corpus, same seed, same numbered rendering: v11 sends v10's prompts
        # in v10's order.
        for profile in ("full", "catalog-only", "no-skill"):
            self.assertEqual(
                self.runner.prompt_set_digest(
                    self.v10_cases, EXPECTED_CORPUS_SHA256,
                    self.runner.DEFAULT_SKILL_DIR, profile,
                    numbered_source_lines=True,
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
        v11_schedule = self.runner.build_schedule(
            self.v10_cases, 5, self.v11["schedule"]["seed"]
        )
        self.assertEqual(v10_schedule, v11_schedule)
        self.assertEqual(150, len(v11_schedule))

    # Retry classification ---------------------------------------------------

    def test_retryable_failure_reason_is_conservative(self) -> None:
        reason = self.runner.retryable_failure_reason
        strict = "model output must be exactly one strict JSON payload: model output: x"
        self.assertEqual("timeout", reason(None, 124, "timeout", "", ""))
        self.assertEqual(
            "runner_nonzero_exit_with_usage_limit_text",
            reason(1, 1, "runner exited 1", "You've hit your weekly limit", ""),
        )
        self.assertEqual(
            "runner_nonzero_exit_with_usage_limit_text",
            reason(1, 1, "runner exited 1", "[stderr omitted]", "ERROR: usage limit reached"),
        )
        self.assertEqual(
            "runner_nonzero_exit_with_usage_limit_text",
            reason(2, 2, "runner exited 2", "", "429 Rate limit exceeded"),
        )
        self.assertEqual(
            "runner_nonzero_exit_with_usage_limit_text",
            reason(1, 1, "runner exited 1", "You’ve hit your limit", ""),
        )
        self.assertEqual("malformed_json_output", reason(0, 1, strict, '{"findings":[', ""))
        # Usage text on a zero exit is never the usage reason.
        self.assertEqual(
            "malformed_json_output",
            reason(0, 1, strict, "You've hit your usage limit", ""),
        )
        not_retryable = (
            (0, 0, None, '{"findings":[]}', ""),  # scoreable
            (0, 0, None, '{"findings":[]}', "usage limit"),  # scoreable, noisy stderr
            (3, 3, "runner exited 3", "internal failure", ""),  # other crash
            (1, 1, "runner exited 1", "", ""),  # silent non-zero exit
            (
                0, 1,
                "findings payload must contain exactly the findings field",
                '{"results":[]}', "",
            ),  # well-formed JSON, wrong schema
            (0, 1, "runner output exceeded 1 byte capture limit", "", ""),
            (1, 126, "runner output contained credential-shaped data and was redacted",
             "usage limit", ""),
            (1, 1, "staged workspace mutated during runner execution", "usage limit", ""),
            (0, 1, "staged workspace mutated during runner execution", "", ""),
            (None, 124, "staged workspace mutated during runner execution", "", ""),
            (None, 1, strict, "", ""),  # parse error without a completed runner
        )
        for args in not_retryable:
            with self.subTest(args=args):
                self.assertIsNone(reason(*args))

    # Stub-runner end-to-end retries -------------------------------------------

    def run_stub(self, temp: Path, plan: list[str], protocol: Path = V11_PROTOCOL_PATH):
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
                "--protocol", str(protocol),
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
        # The report loads under the comparator's schema checks either way.
        self.comparator.load_report(output)
        return report, report["runs"][0], invocations, result.stdout

    def assert_retry_report(self, report: dict, run: dict) -> None:
        protocol = self.runner.load_protocol(V11_PROTOCOL_PATH)
        self.assertEqual(protocol["infrastructure_retry"], report["infrastructure_retry"])
        self.assertEqual(
            self.runner.infrastructure_retry_summary(report["runs"]),
            report["infrastructure_retry_summary"],
        )
        self.comparator.validate_retry_records(report, protocol["infrastructure_retry"])
        self.assertEqual(set(self.comparator.RETRY_RUN_KEYS), set(run))

    def test_timeout_then_success_is_scored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report, run, invocations, _ = self.run_stub(Path(temp), ["timeout", "ok"])
        self.assertEqual(2, invocations)
        self.assertEqual(
            [
                {"attempt": 1, "reason": "timeout", "exit_code": 124, "error": "timeout"},
                {"attempt": 2, "reason": None, "exit_code": 0, "error": None},
            ],
            run["attempts"],
        )
        self.assertIsNone(run["error"])
        self.assertIsNotNone(run["score"])
        summary = report["infrastructure_retry_summary"]
        self.assertEqual(1, summary["retried_calls"])
        self.assertEqual(1, summary["retries_by_reason"]["timeout"])
        self.assertEqual(1, summary["scored_after_retry"])
        self.assertEqual(0, report["summary"]["infrastructure_errors"])
        self.assert_retry_report(report, run)

    def test_malformed_json_then_valid_is_scored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report, run, invocations, _ = self.run_stub(Path(temp), ["malformed", "ok"])
        self.assertEqual(2, invocations)
        first, second = run["attempts"]
        self.assertEqual(("malformed_json_output", 1), (first["reason"], first["exit_code"]))
        self.assertTrue(first["error"].startswith(self.runner.STRICT_JSON_FAILURE_PREFIX))
        self.assertEqual((None, 0, None), (second["reason"], second["exit_code"], second["error"]))
        self.assertEqual('{"findings":[]}', run["output"])
        self.assertIsNotNone(run["score"])
        self.assertEqual(
            1, report["infrastructure_retry_summary"]["retries_by_reason"]["malformed_json_output"]
        )
        self.assert_retry_report(report, run)

    def test_usage_limit_exit_then_success_is_scored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report, run, invocations, _ = self.run_stub(Path(temp), ["usage_stderr", "ok"])
        self.assertEqual(2, invocations)
        first = run["attempts"][0]
        self.assertEqual(
            ("runner_nonzero_exit_with_usage_limit_text", 1, "runner exited 1"),
            (first["reason"], first["exit_code"], first["error"]),
        )
        self.assertIsNotNone(run["score"])
        self.assertEqual(
            1,
            report["infrastructure_retry_summary"]["retries_by_reason"][
                "runner_nonzero_exit_with_usage_limit_text"
            ],
        )
        self.assert_retry_report(report, run)

    def test_exhausted_retries_stay_an_infrastructure_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report, run, invocations, _ = self.run_stub(
                Path(temp), ["usage_stdout", "usage_stderr", "ok"]
            )
        # Two attempts is the preregistered maximum; the third plan line is unused.
        self.assertEqual(2, invocations)
        self.assertEqual(
            ["runner_nonzero_exit_with_usage_limit_text"] * 2,
            [attempt["reason"] for attempt in run["attempts"]],
        )
        self.assertEqual((1, "runner exited 1"), (run["exit_code"], run["error"]))
        self.assertIsNone(run["score"])
        # Stderr is used for classification only; the report keeps its digest marker.
        self.assertIn("[stderr omitted sha256=", run["output"])
        self.assertNotIn("Try again later", run["output"])
        self.assertEqual(1, report["summary"]["infrastructure_errors"])
        summary = report["infrastructure_retry_summary"]
        self.assertEqual(
            (1, 2, 1, 0, 1),
            (
                summary["retried_calls"], summary["total_attempts"], summary["retries"],
                summary["scored_after_retry"], summary["unscoreable_with_retryable_reason"],
            ),
        )
        self.assertEqual("INCONCLUSIVE", report["status"])
        self.assert_retry_report(report, run)

    def test_scoreable_wrong_output_is_never_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report, run, invocations, _ = self.run_stub(Path(temp), ["wrong", "ok"])
        self.assertEqual(1, invocations)
        self.assertEqual(
            [{"attempt": 1, "reason": None, "exit_code": 0, "error": None}],
            run["attempts"],
        )
        self.assertEqual(1, run["score"]["fp"])
        self.assertEqual(0, run["score"]["tp"])
        self.assertEqual(0, report["infrastructure_retry_summary"]["retries"])
        self.assert_retry_report(report, run)

    def test_unrecognized_failure_is_never_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            report, run, invocations, _ = self.run_stub(Path(temp), ["crash", "ok"])
        self.assertEqual(1, invocations)
        self.assertEqual(
            [{"attempt": 1, "reason": None, "exit_code": 3, "error": "runner exited 3"}],
            run["attempts"],
        )
        self.assertIsNone(run["score"])
        self.assertEqual(0, report["infrastructure_retry_summary"]["retries"])
        self.assert_retry_report(report, run)

    def test_protocol_without_policy_is_never_retried(self) -> None:
        # The v10 protocol has no policy: every failure keeps its single attempt
        # and the run record and report keep their pre-policy shape.
        for plan in (["usage_stderr", "ok"], ["malformed", "ok"], ["timeout", "ok"]):
            with self.subTest(plan[0]), tempfile.TemporaryDirectory() as temp:
                report, run, invocations, _ = self.run_stub(
                    Path(temp), plan, protocol=V10_PROTOCOL_PATH
                )
                self.assertEqual(1, invocations)
                self.assertEqual(set(self.comparator.RUN_KEYS), set(run))
                self.assertIsNone(run["score"])
                self.assertNotIn("infrastructure_retry", report)
                self.assertNotIn("infrastructure_retry_summary", report)
                self.assertEqual(1, report["summary"]["infrastructure_errors"])
                self.comparator.validate_retry_records(report, None)

    # Comparator ------------------------------------------------------------

    def synthetic_retry_runs(self) -> list[dict]:
        runs = []
        for index, case in enumerate(self.v10_cases):
            findings = [
                as_finding(label) for label in case["labels"] if label["kind"] == "finding"
            ]
            attempts = [{"attempt": 1, "reason": None, "exit_code": 0, "error": None}]
            if index == 0:
                attempts.insert(
                    0, {"attempt": 1, "reason": "timeout", "exit_code": 124, "error": "timeout"}
                )
                attempts[1]["attempt"] = 2
            runs.append({
                "case": case["id"],
                "repetition": 1,
                "exit_code": 0,
                "error": None,
                "findings": findings,
                "score": self.runner.score(case, findings, revised_labels=True),
                "attempts": attempts,
            })
        return runs

    def test_comparator_validates_retry_records(self) -> None:
        policy = self.v11["infrastructure_retry"]
        runs = self.synthetic_retry_runs()
        summary = self.runner.infrastructure_retry_summary(runs)
        self.assertEqual(
            {
                "scheduled_calls": 30,
                "total_attempts": 31,
                "retried_calls": 1,
                "retries": 1,
                "retries_by_reason": {
                    "timeout": 1,
                    "runner_nonzero_exit_with_usage_limit_text": 0,
                    "malformed_json_output": 0,
                },
                "scored_after_retry": 1,
                "unscoreable_with_retryable_reason": 0,
            },
            summary,
        )
        report = {
            "infrastructure_retry": policy,
            "infrastructure_retry_summary": summary,
            "runs": runs,
        }
        self.comparator.validate_retry_records(report, policy)

        def mutated(change) -> dict:
            data = copy.deepcopy(report)
            change(data)
            return data

        rejected = {
            "three attempts": lambda data: data["runs"][0]["attempts"].append(
                {"attempt": 3, "reason": None, "exit_code": 0, "error": None}
            ),
            "no attempts": lambda data: data["runs"][1].update({"attempts": []}),
            "retried without reason": lambda data: data["runs"][0]["attempts"][0].update(
                {"reason": None}
            ),
            "unlisted reason": lambda data: data["runs"][0]["attempts"][0].update(
                {"reason": "runner_nonzero_exit"}
            ),
            "misnumbered": lambda data: data["runs"][0]["attempts"][1].update({"attempt": 3}),
            "final mismatch": lambda data: data["runs"][1]["attempts"][0].update(
                {"exit_code": 1}
            ),
            "scored with reason": lambda data: data["runs"][1]["attempts"][0].update(
                {"reason": "timeout"}
            ),
            "stopped early": lambda data: (
                data["runs"][1].update({"exit_code": 124, "error": "timeout", "score": None}),
                data["runs"][1]["attempts"][0].update(
                    {"reason": "timeout", "exit_code": 124, "error": "timeout"}
                ),
            ),
            "policy drift": lambda data: data.update(
                {"infrastructure_retry": {**policy, "max_attempts_per_call": 3}}
            ),
            "missing summary": lambda data: data.pop("infrastructure_retry_summary"),
            "extra attempt key": lambda data: data["runs"][1]["attempts"][0].update(
                {"stderr": "x"}
            ),
        }
        for name, change in rejected.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.comparator.validate_retry_records(mutated(change), policy)
        # A protocol without the policy refuses every retry field.
        for name, change in {
            "attempts": lambda data: (
                data.pop("infrastructure_retry"), data.pop("infrastructure_retry_summary")
            ),
            "policy": lambda data: [run.pop("attempts") for run in data["runs"]]
            and data.pop("infrastructure_retry_summary"),
            "summary": lambda data: [run.pop("attempts") for run in data["runs"]]
            and data.pop("infrastructure_retry"),
        }.items():
            with self.subTest(f"no policy: {name}"), self.assertRaisesRegex(
                ValueError, "no retry policy"
            ):
                self.comparator.validate_retry_records(mutated(change), None)
        # recompute_report runs the check and re-derives the summary.
        source = inspect.getsource(self.comparator.recompute_report)
        self.assertIn("validate_retry_records(report, retry_policy)", source)
        self.assertIn('checks["infrastructure_retry_summary"]', source)
        self.assertEqual(
            {"infrastructure_retry", "infrastructure_retry_summary"},
            self.comparator.REPORT_OPTIONAL_KEYS
            & {"infrastructure_retry", "infrastructure_retry_summary"},
        )
        rows = self.comparator.retry_count_rows(
            [{"prompt_profile": "full", "runner": "codex", "model": "gpt-5.6-sol", "runs": runs}]
        )
        self.assertEqual(summary, rows[0]["infrastructure_retry_summary"])

    def test_retried_then_scored_runs_are_ordinary_case_rows(self) -> None:
        runs = self.synthetic_retry_runs()
        report = {
            "protocol_id": PROTOCOL_ID,
            "prompt_profile": "full",
            "runner": "codex",
            "model": "gpt-5.6-sol",
            "primary_metrics": {"stability": {"required_hits": 1}},
            "runs": runs,
        }
        rows = self.comparator.report_case_metric_rows(report, self.v10_cases)
        plain = copy.deepcopy(report)
        for run in plain["runs"]:
            run.pop("attempts")
        self.assertEqual(rows, self.comparator.report_case_metric_rows(plain, self.v10_cases))

    def test_single_host_comparator_is_decisive_for_v11(self) -> None:
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
        for step in self.v11["arm_comparison"]["execution_order"]:
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
                reports, cases, "a" * 64, self.v11, "b" * 64,
                "public-development", "development",
            )
        self.assertEqual("PASS", result["status"])
        self.assertEqual(
            "exact-three-profiles-by-one-host", result["metrics"]["comparison_unit"]
        )

    # Documentation ---------------------------------------------------------

    def test_readme_documents_preregistration_and_exact_rerun(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn("# Reviewer holdout v11", readme.splitlines()[0])
        # The official run was stopped when gpt-5.6-sol was retired.
        self.assertIn(
            "Status: preregistered; the official run was stopped during the full arm "
            "when gpt-5.6-sol was retired, and v12 (gpt-6-sol) replaces it. "
            "No v11 result is claimed.",
            readme,
        )
        calls = len(self.v10_cases) * 5 * 3
        self.assertEqual(450, calls)
        for contract in (
            f"{calls} scheduled model calls",
            "scripts/evals/reviewer-holdout-v10.json",
            "scripts/evals/reviewer-validation-protocol-v11.json",
            EXPECTED_CASES_FILE_SHA256,
            EXPECTED_CORPUS_SHA256,
            EXPECTED_PROTOCOL_SHA256,
            "codex-cli 0.155.1",
            "gpt-5.6-sol",
            "--compare-arms",
            'test -z "$(git status --porcelain)"',
            "## Why v11 exists",
            "## Infrastructure-retry policy",
            "## Claim limits",
            "about 0.012",
            "about 0.033 at 80% power",
            '"max_attempts_per_call": 2',
            *EXPECTED_RETRY_REASONS,
            "never retried",
        ):
            self.assertIn(contract, readme)
        self.assertEqual(3, readme.count("--repetitions 5"))
        self.assertEqual(0, readme.count("--repetitions 3"))
        self.assertEqual(4, readme.count('--output "$OUT/'))
        self.assertEqual(3, len(re.findall(r"--arm (full|catalog-only|no-skill) ", readme)))
        self.assertEqual(3, readme.count("--allow-live"))
        self.assertEqual(4, readme.count("--protocol scripts/evals/reviewer-validation-protocol-v11.json"))
        self.assertEqual(4, readme.count("--cases scripts/evals/reviewer-holdout-v10.json"))
        # No report exists for a preregistered protocol.
        self.assertFalse((README_PATH.parent / "reports").exists())
        self.assertFalse((README_PATH.parent / "attempts").exists())
        self.assertIn(
            "benchmarks/reviewer-holdout-v11/README.md",
            BENCHMARK_DOC_PATH.read_text(encoding="utf-8"),
        )
        changelog = CHANGELOG_PATH.read_text(encoding="utf-8")
        release_section = changelog.split("## [2.0.0]", 1)[1].split("\n## [", 1)[0]
        added = release_section.split("### Added", 1)[1].split("\n### ", 1)[0]
        self.assertIn(PROTOCOL_ID, added)
        self.assertIn("scripts/ci/test-reviewer-holdout-v11.py", added)
        self.assertIn(
            "scripts/ci/test-reviewer-holdout-v11.py",
            CI_LOCAL_PATH.read_text(encoding="utf-8"),
        )
        self.assertIn(
            "scripts/ci/test-reviewer-holdout-v11.py",
            CONTRIBUTING_PATH.read_text(encoding="utf-8"),
        )
        # The v10 benchmark record is not rewritten by v11.
        self.assertIn("counted run is attempt 3", V10_README_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
