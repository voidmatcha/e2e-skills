#!/usr/bin/env python3
"""Validate the public F1-F15 debugger holdout and its zero-tool runner."""

from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "scripts/evals/debugger-holdout-v1.json"
PROTOCOL_PATH = ROOT / "scripts/evals/debugger-validation-protocol-v1.json"
SOURCE_ROOT = ROOT / "scripts/evals/files/debugger-holdout-v1"
RUNNER_PATH = ROOT / "scripts/evals/run-debugger-holdout.py"
COMPARATOR_PATH = ROOT / "scripts/evals/compare-debugger-holdouts.py"
BENCHMARK_DOC_PATH = ROOT / "docs/debugger-benchmark/README.md"

EXPECTED_CORPUS_SHA256 = "17a3efeb8fc812ce250a4b25254cafb95f5d7dc51e96c10481fed3d39bb59f5c"
EXPECTED_PROTOCOL_SHA256 = "53635f244ca17223ba159afcd507e94420c381a78b479b6f4074b68070f7200c"
EXPECTED_SOURCE_TREE_SHA256 = "381042c2a4d8d30bd3f57dbe9d87fadacc05111ba0d425ef1cdde59666f0dc41"
EXPECTED_CODES = {f"F{number}" for number in range(1, 16)}
SOURCE_LEAKAGE = re.compile(
    r"\b(?:F(?:[1-9]|1[0-5])|product_regression|test_defect|"
    r"selector broken|network dependency|assertion mismatch|missing then|"
    r"condition branch missing|test isolation failure|environment mismatch|"
    r"data dependency|auth / session|async order assumption|"
    r"command queue / intercept race|locator drift|selector drift|"
    r"error swallowing|animation race|hydration race)\b",
    re.IGNORECASE,
)


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


class DebuggerHoldoutV1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = json.loads(CASES_PATH.read_text(encoding="utf-8"))
        cls.protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        cls.runner = load_module("debugger_holdout_v1_runner", RUNNER_PATH)

    def test_contains_one_case_per_category_per_framework(self) -> None:
        pairs = Counter(
            (case["framework"], case["expected"]["f_code"])
            for case in self.corpus["cases"]
        )
        self.assertEqual(30, len(self.corpus["cases"]))
        self.assertEqual(
            {(framework, code) for framework in ("playwright", "cypress") for code in EXPECTED_CODES},
            set(pairs),
        )
        self.assertTrue(all(count == 1 for count in pairs.values()))

    def test_cases_use_exact_schema_and_explicit_independent_axes(self) -> None:
        for case in self.corpus["cases"]:
            self.assertEqual({"id", "framework", "artifact", "expected"}, set(case))
            self.assertEqual({"source", "sha256"}, set(case["artifact"]))
            self.assertEqual(
                {
                    "f_code",
                    "confidence",
                    "diagnosis",
                    "product_impact",
                    "test_reliability_urgency",
                    "test_quality_severity",
                },
                set(case["expected"]),
            )
            expected = case["expected"]
            self.assertIn(expected["confidence"], {"high", "medium", "low"})
            self.assertIn(expected["diagnosis"], {"product_regression", "test_defect", "unknown"})
            self.assertIn(expected["product_impact"], {"none", "low", "medium", "high", "critical", "unknown"})
            self.assertIn(expected["test_reliability_urgency"], {"critical", "high", "medium", "low"})
            self.assertIn(expected["test_quality_severity"], {"P0", "P1", "P2", "N/A"})
            if expected["diagnosis"] != "test_defect":
                self.assertEqual("N/A", expected["test_quality_severity"])

    def test_artifact_manifest_is_complete_unique_and_digest_locked(self) -> None:
        manifested = set()
        digests = set()
        for case in self.corpus["cases"]:
            relative = case["artifact"]["source"]
            self.assertRegex(relative, r"^files/debugger-holdout-v1/case-[0-9]{3}/report\.json$")
            path = ROOT / "scripts/evals" / relative
            self.assertTrue(path.is_file(), case["id"])
            self.assertEqual(case["artifact"]["sha256"], sha256(path), case["id"])
            manifested.add(path)
            digests.add(case["artifact"]["sha256"])
        self.assertEqual(
            {path for path in SOURCE_ROOT.rglob("*") if path.is_file()},
            manifested,
        )
        self.assertEqual(30, len(digests))

    def test_source_artifacts_are_parseable_and_do_not_leak_answers(self) -> None:
        cases_by_source = {
            ROOT / "scripts/evals" / case["artifact"]["source"]: case
            for case in self.corpus["cases"]
        }
        for path in sorted(candidate for candidate in SOURCE_ROOT.rglob("*") if candidate.is_file()):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn(payload["framework"], {"playwright", "cypress"})
            self.assertEqual(cases_by_source[path]["framework"], payload["framework"])
            self.assertIsNone(SOURCE_LEAKAGE.search(path.relative_to(SOURCE_ROOT).as_posix()))
            self.assertIsNone(SOURCE_LEAKAGE.search(path.read_text(encoding="utf-8")))
            self.assertNotIn("expected", payload)
            self.assertNotIn("classification", payload)

    def test_corpus_protocol_and_source_tree_are_frozen(self) -> None:
        self.assertEqual(EXPECTED_CORPUS_SHA256, sha256(CASES_PATH))
        self.assertEqual(EXPECTED_PROTOCOL_SHA256, sha256(PROTOCOL_PATH))
        self.assertEqual(EXPECTED_SOURCE_TREE_SHA256, source_tree_sha256(SOURCE_ROOT))

    def test_protocol_declares_repetition_matrix_thresholds_and_limits(self) -> None:
        self.assertEqual("public-pre-publication-development", self.protocol["evidence_scope"])
        self.assertEqual(3, self.protocol["default_repetitions"])
        self.assertEqual(
            {
                ("codex", "gpt-5.6-sol", "openai"),
                ("claude", "claude-opus-5", "anthropic"),
                ("claude", "claude-fable-5", "anthropic"),
            },
            {
                (entry["runner"], entry["model"], entry["provider_family"])
                for entry in self.protocol["host_matrix"]
            },
        )
        self.assertEqual(
            {
                "rule": "strict-majority",
                "repetitions": 3,
                "classification_fields": sorted(self.runner.EXPECTED_KEYS),
            },
            self.protocol["stability"],
        )
        self.assertEqual(
            {"method": "wilson", "confidence": 0.95, "unit": "unique_case"},
            self.protocol["confidence_intervals"],
        )
        self.assertTrue(
            self.protocol["cross_host_comparison"]["provider_family_balance_required"]
        )
        self.assertEqual(
            {
                "require_explicit_runner_path": True,
                "expected_cli_versions": {
                    "codex": "codex-cli 0.146.0",
                    "claude": "Claude Code 2.1.220",
                },
                "attestation_limit": (
                    "The explicit canonical path, binary digest, and version output "
                    "are provenance evidence, not cryptographic attestation."
                ),
            },
            self.protocol["execution_identity"],
        )
        self.assertGreaterEqual(
            self.protocol["thresholds"]["unique_f_code_accuracy_min"], 0.9
        )
        self.assertEqual(0.0, self.protocol["thresholds"]["invalid_output_rate_max"])
        self.assertTrue(any("public" in item for item in self.protocol["limitations"]))
        self.assertTrue(any("not full browser reports" in item for item in self.protocol["limitations"]))
        self.assertTrue(any("author-created synthetic" in item for item in self.protocol["limitations"]))
        self.assertTrue(any("independent oracle audit" in item for item in self.protocol["limitations"]))
        self.assertIn("not independently adjudicated", self.corpus["description"])

    def test_benchmark_documentation_preserves_development_limitations(self) -> None:
        text = " ".join(BENCHMARK_DOC_PATH.read_text(encoding="utf-8").split())
        self.assertIn("not a release benchmark", text)
        self.assertIn("author-created synthetic", text)
        self.assertIn("not full Playwright or Cypress reports", text)
        self.assertIn("Wilson 95% intervals use only the 30 unique cases", text)
        self.assertIn("--runner-path", text)
        self.assertIn("no symlink or traversal components", text)

    def test_runner_enforces_exact_host_matrix(self) -> None:
        self.runner.validate_host_pair(self.protocol, "codex", "gpt-5.6-sol")
        self.runner.validate_host_pair(self.protocol, "claude", "claude-opus-5")
        with self.assertRaises(ValueError):
            self.runner.validate_host_pair(self.protocol, "codex", "claude-opus-5")
        with self.assertRaises(ValueError):
            self.runner.validate_host_pair(self.protocol, "claude", None)

    def test_runner_cli_requires_explicit_runner_path_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(RUNNER_PATH),
                    "--runner",
                    "codex",
                    "--model",
                    "gpt-5.6-sol",
                    "--output",
                    str(output),
                    "--allow-live",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("requires an explicit --runner-path", result.stdout)

    def test_runner_path_rejects_symlink_and_noncanonical_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            executable = directory / "codex"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o700)
            self.assertEqual(
                executable,
                self.runner.validate_runner_path(executable),
            )
            symlink = directory / "codex-link"
            symlink.symlink_to(executable)
            with self.assertRaisesRegex(ValueError, "canonical"):
                self.runner.validate_runner_path(symlink)
            noncanonical = directory / "nested" / ".." / "codex"
            with self.assertRaisesRegex(ValueError, "canonical"):
                self.runner.validate_runner_path(noncanonical)

    def test_runner_identity_rejects_wrong_executable_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            executable = directory / "codex"
            executable.write_text(
                "#!/bin/sh\nprintf '%s\\n' 'codex-cli 0.145.0'\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            with self.assertRaisesRegex(ValueError, "does not match"):
                self.runner.runner_cli_identity(
                    "codex",
                    executable,
                    "codex-cli 0.146.0",
                )

    def test_runner_identity_captures_explicit_trusted_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            executable = directory / "claude"
            executable.write_text(
                "#!/bin/sh\nprintf '%s\\n' '2.1.220 (Claude Code)'\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            path, identity = self.runner.runner_cli_identity(
                "claude",
                executable,
                "Claude Code 2.1.220",
            )
        self.assertEqual(str(executable), path)
        self.assertEqual(str(executable), identity["path"])
        self.assertEqual("2.1.220 (Claude Code)", identity["version_output"])

    def test_runner_rejects_zero_repetitions_instead_of_falling_back(self) -> None:
        self.assertEqual(3, self.runner.select_repetitions(None, 3))
        self.assertEqual(2, self.runner.select_repetitions(2, 3))
        with self.assertRaises(ValueError):
            self.runner.select_repetitions(0, 3)

    def test_runner_requires_wrapper_for_non_pinned_inputs(self) -> None:
        self.assertTrue(
            self.runner.is_pinned_builtin_input(CASES_PATH, PROTOCOL_PATH)
        )
        self.assertIsNone(
            self.runner.isolation_prefix_for_inputs(
                CASES_PATH,
                PROTOCOL_PATH,
                None,
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            custom_cases = Path(temporary) / CASES_PATH.name
            custom_protocol = Path(temporary) / PROTOCOL_PATH.name
            shutil.copy2(CASES_PATH, custom_cases)
            shutil.copy2(PROTOCOL_PATH, custom_protocol)
            self.assertFalse(
                self.runner.is_pinned_builtin_input(custom_cases, custom_protocol)
            )
            with self.assertRaisesRegex(ValueError, "require --isolation-wrapper"):
                self.runner.isolation_prefix_for_inputs(
                    custom_cases,
                    custom_protocol,
                    None,
                )
            wrapper = Path(temporary).resolve() / "wrapper"
            wrapper.write_text("#!/bin/sh\nexec \"$@\"\n", encoding="utf-8")
            wrapper.chmod(0o700)
            self.assertEqual(
                [str(wrapper)],
                self.runner.isolation_prefix_for_inputs(
                    custom_cases,
                    custom_protocol,
                    wrapper,
                ),
            )

    def test_runner_snapshots_all_prompt_inputs_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = self.runner.snapshot_inputs(
                CASES_PATH,
                PROTOCOL_PATH,
                self.runner.FRAMEWORK_SKILLS,
                Path(temporary),
            )
            self.assertEqual(34, len(snapshot["manifest"]))
            self.assertEqual(
                self.runner.sha256(snapshot["cases_path"]),
                snapshot["manifest"]["corpus"]["sha256"],
            )
            self.assertEqual(
                self.runner.sha256(snapshot["protocol_path"]),
                snapshot["manifest"]["protocol"]["sha256"],
            )
            for framework, path in snapshot["skill_paths"].items():
                self.assertEqual(
                    self.runner.sha256(path),
                    snapshot["manifest"][f"skill:{framework}"]["sha256"],
                )
            self.runner.verify_snapshot(snapshot)
            post = self.runner.snapshot_post_digests(snapshot)
            self.assertEqual(34, len(post))
            for name, entry in snapshot["manifest"].items():
                self.assertEqual(entry["sha256"], entry["source_pre_sha256"])
                self.assertEqual(entry["sha256"], entry["snapshot_pre_sha256"])
                self.assertEqual(entry["sha256"], post[name]["source_sha256"])
                self.assertEqual(entry["sha256"], post[name]["snapshot_sha256"])

    def test_runner_schedule_and_prompt_set_digests_are_deterministic(self) -> None:
        cases = self.corpus["cases"][:4]
        first = self.runner.build_schedule(cases, 3, 99)
        second = self.runner.build_schedule(cases, 3, 99)
        different = self.runner.build_schedule(cases, 3, 100)
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertEqual(list(range(1, 13)), [entry["ordinal"] for entry in first])
        self.assertEqual(
            self.runner.canonical_digest(first),
            self.runner.canonical_digest(second),
        )
        prompt_digest = self.runner.prompt_set_digest(
            cases,
            CASES_PATH,
            self.runner.FRAMEWORK_SKILLS,
        )
        self.assertRegex(prompt_digest, r"^[0-9a-f]{64}$")

    def test_runner_loader_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            duplicate = Path(temporary) / "cases.json"
            duplicate.write_text(
                '{"schema_version":1,"schema_version":1,"corpus_id":"x",'
                '"status":"x","description":"x","cases":[]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate"):
                self.runner.load_corpus(duplicate)

    def test_runner_prompt_excludes_evaluator_only_expected_values(self) -> None:
        case = self.corpus["cases"][3]
        artifact = ROOT / "scripts/evals" / case["artifact"]["source"]
        prompt = self.runner.render_prompt(
            case["framework"],
            artifact.read_text(encoding="utf-8"),
            (ROOT / "skills/playwright-debugger/SKILL.md").read_text(encoding="utf-8"),
        )
        self.assertIn(artifact.read_text(encoding="utf-8"), prompt)
        self.assertNotIn(json.dumps(case["expected"], sort_keys=True), prompt)
        self.assertNotIn("case-004", prompt)
        self.assertIn('"f_code"', prompt)

    def test_runner_uses_shared_prompt_complete_no_tool_invocations(self) -> None:
        shared = self.runner.load_shared_runner()
        codex_command, _ = shared.runner_invocation("codex", "/bin/codex", "prompt", "model")
        claude_command, _ = shared.runner_invocation("claude", "/bin/claude", "prompt", "model")
        self.assertIn("shell_tool", codex_command)
        self.assertIn("tools.web_search=false", codex_command)
        self.assertIn("--ignore-user-config", codex_command)
        tools_index = claude_command.index("--tools")
        self.assertEqual("", claude_command[tools_index + 1])
        self.assertIn("--strict-mcp-config", claude_command)

    def test_runner_parser_requires_one_strict_exact_prediction(self) -> None:
        valid = {
            "f_code": "F13",
            "confidence": "high",
            "diagnosis": "test_defect",
            "product_impact": "none",
            "test_reliability_urgency": "critical",
            "test_quality_severity": "P0",
            "root_cause": "A blanket exception handler suppresses the application error.",
        }
        self.assertEqual(valid, self.runner.parse_prediction(json.dumps(valid)))
        with self.assertRaises(ValueError):
            self.runner.parse_prediction(json.dumps({**valid, "extra": True}))
        with self.assertRaises(ValueError):
            self.runner.parse_prediction(
                '{"f_code":"F13","f_code":"F1","confidence":"high",'
                '"diagnosis":"test_defect","product_impact":"none",'
                '"test_reliability_urgency":"critical","test_quality_severity":"P0",'
                '"root_cause":"x"}'
            )
        with self.assertRaises(ValueError):
            self.runner.parse_prediction("prefix\n" + json.dumps(valid))

    def test_runner_case_executes_through_injected_zero_tool_surface(self) -> None:
        case = self.corpus["cases"][12]
        prediction = {**case["expected"], "root_cause": "A helper discards a required failure."}

        class FakeSharedRunner:
            @staticmethod
            def run_once(
                runner,
                prompt,
                timeout,
                workspace,
                model,
                isolation_prefix=None,
                runner_executable=None,
                runner_credentials=None,
            ):
                self.assertEqual("codex", runner)
                self.assertEqual("model-under-test", model)
                self.assertIsNone(isolation_prefix)
                self.assertEqual("/bin/codex", runner_executable)
                self.assertEqual({}, runner_credentials)
                self.assertTrue((workspace / "report.json").is_file())
                self.assertIn("<skill_contract>", prompt)
                return 0, json.dumps(prediction), 7

            @staticmethod
            def sanitize_model_output(output, runner_credentials):
                self.assertEqual({}, runner_credentials)
                return output, False

        record = self.runner.run_case(
            FakeSharedRunner(),
            "codex",
            "model-under-test",
            case,
            CASES_PATH,
            30,
            self.runner.FRAMEWORK_SKILLS,
            None,
            "/bin/codex",
        )
        self.assertTrue(record["valid"])
        self.assertEqual(prediction, record["prediction"])
        self.assertEqual(7, record["elapsed_ms"])
        self.assertEqual(
            hashlib.sha256(json.dumps(prediction).encode("utf-8")).hexdigest(),
            record["raw_output_sha256"],
        )
        self.assertEqual(json.dumps(prediction), record["raw_output"])
        self.assertTrue(record["workspace_integrity"]["verified"])

    def test_runner_scores_code_and_axes_separately(self) -> None:
        case = self.corpus["cases"][12]
        exact = {**case["expected"], "root_cause": "A helper discards a required failure."}
        wrong_axis = {**exact, "product_impact": "unknown"}
        score = self.runner.score_predictions(
            [
                {"case": case, "prediction": exact, "valid": True},
                {"case": case, "prediction": wrong_axis, "valid": True},
            ]
        )
        self.assertEqual(1.0, score["repeated"]["f_code_accuracy"])
        self.assertEqual(1.0, score["repeated"]["diagnosis_accuracy"])
        self.assertLess(score["repeated"]["axis_exact_match"], 1.0)

    def test_runner_counts_invalid_outputs_as_misses(self) -> None:
        case = self.corpus["cases"][0]
        score = self.runner.score_predictions(
            [{"case": case, "valid": False, "error": "invalid output"}]
        )
        self.assertEqual(1.0, score["invalid_output_rate"])
        self.assertEqual(0.0, score["repeated"]["f_code_accuracy"])
        self.assertEqual(
            0.0, score["repeated"]["framework_accuracy"]["playwright"]
        )

    def test_runner_uses_strict_majority_for_unique_case_metrics(self) -> None:
        first, second = self.corpus["cases"][:2]
        exact_first = {
            **first["expected"],
            "root_cause": "The first failure has the expected mechanism.",
        }
        exact_second = {
            **second["expected"],
            "root_cause": "The second failure has the expected mechanism.",
        }
        wrong_second = {**exact_second, "f_code": "F3"}
        records = [
            {"case": first, "valid": True, "prediction": exact_first},
            {"case": first, "valid": True, "prediction": exact_first},
            {"case": first, "valid": True, "prediction": {**exact_first, "f_code": "F2"}},
            {"case": second, "valid": True, "prediction": exact_second},
            {"case": second, "valid": True, "prediction": wrong_second},
            {"case": second, "valid": False, "error": "invalid output"},
        ]
        score = self.runner.score_predictions(records)
        self.assertEqual(2, score["unique_cases"]["total_cases"])
        self.assertEqual(1, score["unique_cases"]["stable_cases"])
        self.assertEqual(0.5, score["unique_cases"]["stable_case_rate"])
        self.assertEqual(0.5, score["unique_cases"]["f_code_accuracy"])
        self.assertEqual(
            self.runner.wilson_interval(1, 2),
            score["unique_cases"]["f_code_accuracy_wilson_95"],
        )
        self.assertEqual(
            {"framework": "playwright", "accuracy": 0.5, "cases": 2},
            score["worst_slices"]["framework"],
        )

    def test_runner_reports_repeated_macro_precision_separately(self) -> None:
        first, second = self.corpus["cases"][:2]
        predicted_as_first = {
            **first["expected"],
            "root_cause": "Both calls choose the same category.",
        }
        score = self.runner.score_predictions(
            [
                {"case": first, "valid": True, "prediction": predicted_as_first},
                {"case": second, "valid": True, "prediction": predicted_as_first},
            ]
        )
        self.assertEqual(0.5, score["repeated"]["f_code_accuracy"])
        self.assertEqual(0.25, score["repeated"]["macro_precision"])

    def test_runner_marks_process_exceptions_as_infrastructure_errors(self) -> None:
        case = self.corpus["cases"][0]

        class FailingSharedRunner:
            @staticmethod
            def sanitize_model_output(output, runner_credentials):
                return output, False

            @staticmethod
            def run_once(*args, **kwargs):
                raise OSError("synthetic launch failure")

        record = self.runner.run_case(
            FailingSharedRunner(),
            "codex",
            "model-under-test",
            case,
            CASES_PATH,
            30,
            self.runner.FRAMEWORK_SKILLS,
            None,
            "/bin/codex",
        )
        self.assertFalse(record["valid"])
        self.assertTrue(record["infrastructure_error"])
        self.assertIn("synthetic launch failure", record["error"])
        self.assertTrue(record["workspace_integrity"]["verified"])

    def test_runner_passes_one_credential_snapshot_and_fails_closed_on_detection(
        self,
    ) -> None:
        case = self.corpus["cases"][0]
        secret = "oauth-secret-value-123456"
        credential_snapshots = []

        class CredentialSharedRunner:
            @staticmethod
            def runner_credentials(runner):
                self.assertEqual("claude", runner)
                snapshot = {"CLAUDE_CODE_OAUTH_TOKEN": secret}
                credential_snapshots.append(snapshot)
                return snapshot

            @staticmethod
            def run_once(*args, **kwargs):
                self.assertIs(kwargs["runner_credentials"], credential_snapshots[0])
                return 0, f'{{"token":"{secret}"}}', 2

            @staticmethod
            def sanitize_model_output(output, runner_credentials):
                self.assertIs(runner_credentials, credential_snapshots[0])
                return output.replace(secret, "<redacted-credential>"), True

        record = self.runner.run_case(
            CredentialSharedRunner(),
            "claude",
            "model-under-test",
            case,
            CASES_PATH,
            30,
            self.runner.FRAMEWORK_SKILLS,
            None,
            "/bin/claude",
        )
        self.assertEqual(1, len(credential_snapshots))
        self.assertFalse(record["valid"])
        self.assertTrue(record["infrastructure_error"])
        self.assertEqual(
            "runner output contained credential-shaped data and was redacted",
            record["error"],
        )
        self.assertNotIn(secret, json.dumps(record, sort_keys=True))
        self.assertIn("<redacted-credential>", record["raw_output"])

    def test_runner_credential_lookup_failure_is_generic_and_inconclusive(self) -> None:
        case = self.corpus["cases"][0]
        secret = "oauth-secret-value-lookup-123456"

        class LookupFailingSharedRunner:
            @staticmethod
            def runner_credentials(runner):
                raise ValueError(f"keychain exposed {secret}")

        record = self.runner.run_case(
            LookupFailingSharedRunner(),
            "claude",
            "model-under-test",
            case,
            CASES_PATH,
            30,
            self.runner.FRAMEWORK_SKILLS,
            None,
            "/bin/claude",
        )
        self.assertFalse(record["valid"])
        self.assertTrue(record["infrastructure_error"])
        self.assertEqual("runner credential lookup failed", record["error"])
        self.assertNotIn(secret, json.dumps(record, sort_keys=True))

    def test_runner_redaction_failure_never_persists_unsanitized_output(self) -> None:
        case = self.corpus["cases"][0]
        secret = "oauth-secret-value-redaction-123456"

        class RedactionFailingSharedRunner:
            @staticmethod
            def runner_credentials(runner):
                return {"CLAUDE_CODE_OAUTH_TOKEN": secret}

            @staticmethod
            def run_once(*args, **kwargs):
                return 0, f"credential={secret}", 2

            @staticmethod
            def sanitize_model_output(output, runner_credentials):
                raise ValueError(f"cannot redact {secret}")

        record = self.runner.run_case(
            RedactionFailingSharedRunner(),
            "claude",
            "model-under-test",
            case,
            CASES_PATH,
            30,
            self.runner.FRAMEWORK_SKILLS,
            None,
            "/bin/claude",
        )
        self.assertFalse(record["valid"])
        self.assertTrue(record["infrastructure_error"])
        self.assertEqual("runner output credential redaction failed", record["error"])
        self.assertEqual("", record["raw_output"])
        self.assertNotIn(secret, json.dumps(record, sort_keys=True))

    def test_runner_sanitizes_process_exception_before_persisting_error(self) -> None:
        case = self.corpus["cases"][0]
        secret = "oauth-secret-value-exception-123456"
        snapshot = {"CLAUDE_CODE_OAUTH_TOKEN": secret}

        class SecretExceptionSharedRunner:
            @staticmethod
            def runner_credentials(runner):
                return snapshot

            @staticmethod
            def run_once(*args, **kwargs):
                self.assertIs(kwargs["runner_credentials"], snapshot)
                raise OSError(f"runner echoed {secret}")

            @staticmethod
            def sanitize_model_output(output, runner_credentials):
                self.assertIs(runner_credentials, snapshot)
                return output.replace(secret, "<redacted-credential>"), True

        record = self.runner.run_case(
            SecretExceptionSharedRunner(),
            "claude",
            "model-under-test",
            case,
            CASES_PATH,
            30,
            self.runner.FRAMEWORK_SKILLS,
            None,
            "/bin/claude",
        )
        self.assertFalse(record["valid"])
        self.assertTrue(record["infrastructure_error"])
        self.assertEqual(
            "runner failed and credential-shaped data was redacted",
            record["error"],
        )
        self.assertNotIn(secret, json.dumps(record, sort_keys=True))

    def test_runner_treats_invalid_fake_output_as_a_scored_miss(self) -> None:
        case = self.corpus["cases"][0]

        class InvalidSharedRunner:
            @staticmethod
            def sanitize_model_output(output, runner_credentials):
                return output, False

            @staticmethod
            def run_once(*args, **kwargs):
                return 0, '{"not":"a prediction"}', 2

        record = self.runner.run_case(
            InvalidSharedRunner(),
            "codex",
            "model-under-test",
            case,
            CASES_PATH,
            30,
            self.runner.FRAMEWORK_SKILLS,
            None,
            "/bin/codex",
        )
        self.assertFalse(record["valid"])
        self.assertFalse(record["infrastructure_error"])
        self.assertIsNone(record["prediction"])

    def test_runner_treats_nonzero_fake_exit_as_infrastructure_failure(self) -> None:
        case = self.corpus["cases"][0]

        class ExitingSharedRunner:
            @staticmethod
            def sanitize_model_output(output, runner_credentials):
                return output, False

            @staticmethod
            def run_once(*args, **kwargs):
                return 9, "runner failed", 2

        record = self.runner.run_case(
            ExitingSharedRunner(),
            "codex",
            "model-under-test",
            case,
            CASES_PATH,
            30,
            self.runner.FRAMEWORK_SKILLS,
            None,
            "/bin/codex",
        )
        self.assertFalse(record["valid"])
        self.assertTrue(record["infrastructure_error"])
        self.assertEqual("runner exited 9", record["error"])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO requires POSIX")
    def test_runner_marks_special_workspace_nodes_as_integrity_failures(self) -> None:
        case = self.corpus["cases"][0]

        class MutatingSharedRunner:
            @staticmethod
            def sanitize_model_output(output, runner_credentials):
                return output, False

            @staticmethod
            def run_once(*args, **kwargs):
                workspace = args[3]
                os.mkfifo(workspace / "unexpected.pipe")
                return 0, "{}", 3

        record = self.runner.run_case(
            MutatingSharedRunner(),
            "codex",
            "model-under-test",
            case,
            CASES_PATH,
            30,
            self.runner.FRAMEWORK_SKILLS,
            None,
            "/bin/codex",
        )
        self.assertFalse(record["valid"])
        self.assertTrue(record["infrastructure_error"])
        self.assertFalse(record["workspace_integrity"]["verified"])

    def test_runner_derives_complete_pass_fail_and_inconclusive_states(self) -> None:
        thresholds = self.protocol["thresholds"]
        passing = self.runner.score_predictions(
            [
                {
                    "case": case,
                    "valid": True,
                    "prediction": {
                        **case["expected"],
                        "root_cause": "The report evidence identifies this mechanism.",
                    },
                }
                for case in self.corpus["cases"]
                for _ in range(3)
            ]
        )
        failing = {
            **passing,
            "unique_cases": {
                **passing["unique_cases"],
                "f_code_accuracy": 0.0,
            },
        }
        self.assertEqual(
            "PASS",
            self.runner.derive_status(True, True, [], passing, thresholds),
        )
        self.assertEqual(
            "FAIL",
            self.runner.derive_status(True, True, [], failing, thresholds),
        )
        self.assertEqual(
            "INCONCLUSIVE",
            self.runner.derive_status(False, True, [], passing, thresholds),
        )
        self.assertEqual(
            "INCONCLUSIVE",
            self.runner.derive_status(True, False, [], passing, thresholds),
        )
        self.assertEqual(
            "INCONCLUSIVE",
            self.runner.derive_status(True, True, ["runner exited 1"], passing, thresholds),
        )
        self.assertEqual({"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}, self.runner.STATUS_EXIT_CODES)


class DebuggerHoldoutComparatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = load_module("debugger_holdout_runner_for_compare", RUNNER_PATH)
        cls.comparator = load_module(
            "debugger_holdout_comparator", COMPARATOR_PATH
        )
        cls.corpus = cls.runner.load_corpus(CASES_PATH)
        cls.protocol = cls.runner.load_protocol(PROTOCOL_PATH)

    def make_report(self, runner_name: str, model: str) -> dict:
        schedule = self.runner.build_schedule(
            self.corpus["cases"], 3, self.protocol["seed"]
        )
        cases_by_id = {case["id"]: case for case in self.corpus["cases"]}
        records = []
        scoring_records = []
        for entry in schedule:
            case = cases_by_id[entry["case_id"]]
            prediction = {
                **case["expected"],
                "root_cause": "The report evidence identifies this mechanism.",
            }
            output = json.dumps(prediction, sort_keys=True)
            record = {
                **entry,
                "valid": True,
                "infrastructure_error": False,
                "prediction": prediction,
                "raw_output": output,
                "raw_output_sha256": hashlib.sha256(output.encode()).hexdigest(),
                "raw_output_bytes": len(output.encode()),
                "error": None,
                "exit_code": 0,
                "elapsed_ms": 1,
                "workspace_integrity": {
                    "before_sha256": "a" * 64,
                    "after_sha256": "a" * 64,
                    "verified": True,
                },
            }
            records.append(record)
            scoring_records.append({**record, "case": case})
        score = self.runner.score_predictions(scoring_records)
        manifest = {}
        sources = {
            "corpus": CASES_PATH,
            "protocol": PROTOCOL_PATH,
            **{
                f"skill:{framework}": path
                for framework, path in self.runner.FRAMEWORK_SKILLS.items()
            },
            **{
                f"artifact:{case['id']}": CASES_PATH.parent
                / case["artifact"]["source"]
                for case in self.corpus["cases"]
            },
        }
        for name, path in sources.items():
            digest = sha256(path)
            manifest[name] = {
                "source_path": str(path.resolve()),
                "snapshot_path": f"/expired-snapshot/{name.replace(':', '-')}",
                "sha256": digest,
                "source_pre_sha256": digest,
                "snapshot_pre_sha256": digest,
            }
        post = {
            name: {"source_sha256": row["sha256"], "snapshot_sha256": row["sha256"]}
            for name, row in manifest.items()
        }
        return {
            "schema_version": 2,
            "corpus_id": self.corpus["corpus_id"],
            "corpus_sha256": sha256(CASES_PATH),
            "protocol_sha256": sha256(PROTOCOL_PATH),
            "input_snapshot_manifest": manifest,
            "input_post_digests": post,
            "input_integrity_verified": True,
            "prompt_skill_sha256": {
                framework: sha256(path)
                for framework, path in self.runner.FRAMEWORK_SKILLS.items()
            },
            "prompt_set_sha256": self.runner.prompt_set_digest(
                self.corpus["cases"], CASES_PATH, self.runner.FRAMEWORK_SKILLS
            ),
            "schedule": schedule,
            "schedule_sha256": self.runner.canonical_digest(schedule),
            "runner": runner_name,
            "model": model,
            "runner_cli_identity": {
                "path": f"/fake/{runner_name}",
                "sha256": "b" * 64,
                "size_bytes": 1,
                "version_output": "deterministic fake runner",
            },
            "repetitions": 3,
            "execution_complete": True,
            "infrastructure_errors": [],
            "status": "PASS",
            "score": score,
            "records": records,
            "limitations": self.protocol["limitations"],
        }

    def matrix(self) -> list[dict]:
        return [
            self.make_report("codex", "gpt-5.6-sol"),
            self.make_report("claude", "claude-opus-5"),
            self.make_report("claude", "claude-fable-5"),
        ]

    def force_all_predictions_wrong(self, report: dict) -> None:
        cases_by_id = {case["id"]: case for case in self.corpus["cases"]}
        scoring_records = []
        for record in report["records"]:
            case = cases_by_id[record["case_id"]]
            prediction = {
                **case["expected"],
                "f_code": "F14" if case["expected"]["f_code"] == "F15" else "F15",
                "root_cause": "The deterministic fake runner chooses the wrong category.",
            }
            output = json.dumps(prediction, sort_keys=True)
            record["prediction"] = prediction
            record["raw_output"] = output
            record["raw_output_sha256"] = hashlib.sha256(output.encode()).hexdigest()
            record["raw_output_bytes"] = len(output.encode())
            scoring_records.append({**record, "case": case})
        report["score"] = self.runner.score_predictions(scoring_records)
        report["status"] = self.runner.derive_status(
            True, True, [], report["score"], self.protocol["thresholds"]
        )

    def test_comparator_reparses_raw_outputs_and_balances_provider_families(self) -> None:
        comparison = self.comparator.compare_reports(
            self.matrix(), self.corpus, self.protocol
        )
        self.assertEqual("VALID_DEVELOPMENT_COMPARISON", comparison["status"])
        self.assertEqual(3, comparison["matrix"]["host_count"])
        self.assertEqual(2, comparison["matrix"]["provider_family_count"])
        self.assertEqual(
            1.0,
            comparison["provider_family_balanced"]["unique_f_code_accuracy"],
        )
        self.assertTrue(comparison["raw_outputs_reparsed"])
        self.assertFalse(comparison["release_eligible"])

    def test_comparator_rejects_serialized_score_drift(self) -> None:
        reports = self.matrix()
        reports[0]["score"]["unique_cases"]["f_code_accuracy"] = 0.0
        with self.assertRaisesRegex(ValueError, "serialized score drift"):
            self.comparator.compare_reports(reports, self.corpus, self.protocol)

    def test_comparator_weights_provider_families_not_host_count(self) -> None:
        reports = self.matrix()
        self.force_all_predictions_wrong(reports[0])
        comparison = self.comparator.compare_reports(
            reports, self.corpus, self.protocol
        )
        self.assertEqual(
            0.5,
            comparison["provider_family_balanced"]["unique_f_code_accuracy"],
        )
        host_mean = sum(
            row["metrics"]["unique_f_code_accuracy"]
            for row in comparison["matrix"]["hosts"]
        ) / 3
        self.assertAlmostEqual(2 / 3, host_mean)

    def test_comparator_rejects_raw_output_digest_drift(self) -> None:
        reports = self.matrix()
        reports[0]["records"][0]["raw_output"] = "{}"
        with self.assertRaisesRegex(ValueError, "raw output"):
            self.comparator.compare_reports(reports, self.corpus, self.protocol)

    def test_comparator_rejects_duplicate_or_partial_matrix(self) -> None:
        reports = self.matrix()
        with self.assertRaisesRegex(ValueError, "fixed host matrix"):
            self.comparator.compare_reports(reports[:2], self.corpus, self.protocol)
        reports[2]["runner"] = "codex"
        reports[2]["model"] = "gpt-5.6-sol"
        with self.assertRaisesRegex(ValueError, "fixed host matrix"):
            self.comparator.compare_reports(reports, self.corpus, self.protocol)

    def test_comparator_rejects_schedule_and_provenance_drift(self) -> None:
        reports = self.matrix()
        reports[0]["schedule"][0]["case_id"] = "case-999"
        with self.assertRaisesRegex(ValueError, "schedule"):
            self.comparator.compare_reports(reports, self.corpus, self.protocol)
        reports = self.matrix()
        reports[0]["input_integrity_verified"] = False
        with self.assertRaisesRegex(ValueError, "input integrity"):
            self.comparator.compare_reports(reports, self.corpus, self.protocol)


if __name__ == "__main__":
    unittest.main()
