#!/usr/bin/env python3
"""Deterministic contract tests for the generator model-evaluation runner."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "scripts/evals/run-generator-faultkill.py"
PROTOCOL_PATH = ROOT / "scripts/evals/generator-validation-protocol-v2.json"
REFERENCE_PATH = (
    ROOT / "scripts/evals/files/generator-faultkill-v1/reference-predictions.json"
)


def load_runner(name: str = "generator_faultkill_runner"):
    spec = importlib.util.spec_from_file_location(name, RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_runner()


FAKE_RUNNER = r'''#!/usr/bin/env python3
import json
from pathlib import Path
import sys

if "--version" in sys.argv:
    name = Path(sys.argv[0]).name
    print("codex-cli 0.146.0" if "codex" in name else "2.1.220 (Claude Code)")
    raise SystemExit(0)

prompt = sys.stdin.read()
model = sys.argv[sys.argv.index("--model") + 1]
reference = json.loads(Path(__REFERENCE__).read_text())["predictions"]
arm = next(line.split(": ", 1)[1] for line in prompt.splitlines() if line.startswith("Arm: "))
mode = __MODE__

if mode == "malformed":
    print("```json\n{}\n```")
    raise SystemExit(0)
if mode == "wrong-model":
    model = "unexpected-model"
if mode == "workspace-drift":
    Path("model-created.txt").write_text("forbidden")

predictions = json.loads(json.dumps(reference))
by_id = {item["case_id"]: item for item in predictions}
if mode == "lift":
    misses = {
        "full-skill": [],
        "rules-only": ["pw-authenticated-account", "pw-increment-request"],
        "no-skill": [
            "pw-increment-accessible-name",
            "pw-authenticated-account",
            "pw-increment-request",
        ],
    }[arm]
elif mode == "flat":
    misses = []
else:
    misses = []
for case_id in misses:
    item = by_id[case_id]
    item["oracles"] = ["status-count-zero"]
print(json.dumps({"schema_version": 1, "model": model, "predictions": predictions}))
'''


class GeneratorFaultkillRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="generator-runner-test-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def fake_runner(self, name: str, mode: str = "lift") -> Path:
        path = self.root / name
        source = (
            FAKE_RUNNER.replace("__REFERENCE__", repr(str(REFERENCE_PATH)))
            .replace("__MODE__", repr(mode))
        )
        path.write_text(source, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def execute(
        self,
        mode: str = "lift",
        protocol: Path = PROTOCOL_PATH,
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        codex = self.fake_runner("fake-codex", mode)
        claude = self.fake_runner("fake-claude", mode)
        report = self.root / f"{mode}-report.json"
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--codex-runner-path",
                str(codex),
                "--claude-runner-path",
                str(claude),
                "--protocol",
                str(protocol),
                "--output",
                str(report),
                "--timeout",
                "10",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={
                **os.environ,
                "CLAUDE_CODE_OAUTH_TOKEN": (
                    "claude-oauth-fixture-token-123456789"
                ),
            },
        )
        self.assertTrue(report.is_file(), result.stderr)
        return result, json.loads(report.read_text(encoding="utf-8"))

    def valid_output(self, model: str = "gpt-5.6-sol") -> str:
        predictions = json.loads(REFERENCE_PATH.read_text())["predictions"]
        return json.dumps(
            {"schema_version": 1, "model": model, "predictions": predictions}
        )

    def test_three_prompt_arms_share_tasks_schema_and_output_contract(self) -> None:
        corpus = MODULE.V1.load_strict_json(MODULE.CORPUS_PATH)
        prompts = {
            arm: MODULE.render_prompt(corpus, arm, "gpt-5.6-sol")
            for arm in MODULE.ARMS
        }
        for prompt in prompts.values():
            self.assertIn("BEGIN_TASK_BUNDLE", prompt)
            self.assertIn("BEGIN_CLOSED_DSL_LEGEND", prompt)
            self.assertIn("generator-playwright-only", prompt)
            self.assertIn('"model":"gpt-5.6-sol"', prompt)
            for case in corpus["cases"]:
                self.assertIn(case["id"], prompt)
                self.assertIn(case["task"], prompt)
        self.assertIn("BEGIN_GENERATOR_SKILL SKILL.md", prompts["full-skill"])
        self.assertNotIn("BEGIN_GENERATOR_SKILL SKILL.md", prompts["rules-only"])
        self.assertIn(
            "BEGIN_GENERATOR_SKILL code-rules.md", prompts["rules-only"]
        )
        self.assertNotIn("BEGIN_GENERATOR_SKILL", prompts["no-skill"])
        self.assertIn("not token-free", prompts["no-skill"])

    def test_strict_parser_rejects_unsafe_or_ambiguous_outputs(self) -> None:
        valid = self.valid_output()
        attacks = [
            "```json\n" + valid + "\n```",
            valid + "\nrun: rm -rf /",
            valid.replace('"schema_version": 1', '"schema_version":NaN', 1),
            valid.replace(
                '"schema_version": 1',
                '"schema_version":1,"schema_version":1',
                1,
            ),
            valid.replace(
                '"actions": ["navigate-counter", "click-increment"]',
                '"actions":["navigate-counter","evaluate-javascript"]',
                1,
            ),
            valid.replace(
                '"predictions": [',
                '"command":"npm test","predictions":[',
                1,
            ),
        ]
        for attack in attacks:
            with self.subTest(attack=attack[:40]):
                with self.assertRaises(ValueError):
                    MODULE.parse_output(attack, "gpt-5.6-sol")

    def test_parser_rejects_model_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "model identity mismatch"):
            MODULE.parse_output(self.valid_output("opus"), "gpt-5.6-sol")

    def test_descriptive_arm_differences_pass_and_persist_outputs(self) -> None:
        result, report = self.execute("lift")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("PASS", report["status"])
        self.assertTrue(report["complete"])
        self.assertEqual(27, len(report["runs"]))
        self.assertTrue(all(run["raw_output"] for run in report["runs"]))
        self.assertTrue(all(run["raw_output_sha256"] for run in report["runs"]))
        weighted = report["metrics"]["equal_provider_family_weighted"]
        self.assertEqual(1.0, weighted["full-skill"]["planning_accuracy"])
        self.assertEqual(0.5, weighted["rules-only"]["planning_accuracy"])
        self.assertEqual(0.25, weighted["no-skill"]["planning_accuracy"])
        self.assertEqual(
            0.5,
            weighted["full-skill"]["descriptive_difference_vs_rules_only"],
        )
        self.assertEqual(
            0.75,
            weighted["full-skill"]["descriptive_difference_vs_no_skill"],
        )
        self.assertEqual("INCONCLUSIVE", report["comparative_inference"]["status"])
        self.assertIsNone(report["comparative_inference"]["lower_bound"])
        self.assertEqual(
            4, report["comparative_inference"]["unique_scored_cases"]
        )
        self.assertNotIn("causal", report["measurement_claim"].lower())
        self.assertIn(
            "causal skill-effect or general skill-lift claims",
            report["limitations"],
        )
        self.assertTrue(report["provenance"]["pre_post_equal"])
        for key in (
            "protocol_sha256",
            "prompt_sha256",
            "skill_sha256",
            "corpus_sha256",
            "schema_sha256",
            "evaluator_sha256",
            "source_sha256",
            "runtime_evidence_sha256",
            "runner_cli",
            "model_matrix_sha256",
            "schedule_sha256",
            "schedule",
        ):
            self.assertIn(key, report["provenance"])
        self.assertEqual(
            report["protocol"]["schedule"]["sha256"],
            report["provenance"]["schedule_sha256"],
        )

    def test_flat_arms_are_complete_failure_with_exit_one(self) -> None:
        result, report = self.execute("flat")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertEqual("FAIL", report["status"])
        self.assertTrue(report["complete"])
        self.assertFalse(
            report["threshold_checks"][
                "descriptive_difference_full_minus_no_skill_min"
            ]["passed"]
        )

    def test_schedule_is_seeded_pinned_and_counterbalanced(self) -> None:
        protocol = MODULE.validate_protocol(MODULE.load_strict(PROTOCOL_PATH))
        first = MODULE.build_schedule(protocol)
        second = MODULE.build_schedule(protocol)
        self.assertEqual(first, second)
        self.assertEqual(
            protocol["schedule"]["sha256"], MODULE.canonical_sha256(first)
        )
        self.assertEqual(27, len(first))
        self.assertEqual(
            27,
            len(
                {
                    (
                        cell["configuration_id"],
                        cell["arm"],
                        cell["repetition"],
                    )
                    for cell in first
                }
            ),
        )
        for config in protocol["matrix"]:
            blocks = {
                repetition: [
                    cell["arm"]
                    for cell in first
                    if cell["configuration_id"] == config["configuration_id"]
                    and cell["repetition"] == repetition
                ]
                for repetition in range(1, 4)
            }
            for arms in blocks.values():
                self.assertEqual(set(MODULE.ARMS), set(arms))
            for arm in MODULE.ARMS:
                self.assertEqual(
                    [0, 1, 2],
                    sorted(arms.index(arm) for arms in blocks.values()),
                )

    def test_codex_auth_is_staged_for_official_style_js_symlink(self) -> None:
        codex_js = self.fake_runner("codex.js")
        launcher = self.root / "codex"
        launcher.symlink_to(codex_js)
        runner_home = self.root / "runner-home"
        runner_home.mkdir()
        workspace = self.root / "workspace"
        workspace.mkdir()
        staged = runner_home / "staged-codex"
        with (
            mock.patch.object(MODULE.REVIEWER, "clean_env", return_value={}),
            mock.patch.object(
                MODULE.REVIEWER,
                "stage_codex_auth",
                return_value=staged,
            ) as stage_auth,
        ):
            environment = MODULE.clean_environment(
                workspace, "codex", launcher.resolve(), runner_home, {}
            )
        stage_auth.assert_called_once_with(runner_home)
        self.assertEqual(str(staged), environment["CODEX_HOME"])

    def test_claude_call_uses_one_minimal_oauth_snapshot_and_redacts_it(
        self,
    ) -> None:
        token = "claude-oauth-test-token-123456789"
        credentials = {"CLAUDE_CODE_OAUTH_TOKEN": token}
        workspace = self.root / "claude-workspace"
        workspace.mkdir()
        executable = self.fake_runner("claude-auth-test")
        command = MODULE.runner_invocation(
            "claude", executable, "claude-opus-5"
        )
        with (
            mock.patch.object(
                MODULE.REVIEWER,
                "claude_runner_credentials",
                return_value=credentials,
            ) as credential_lookup,
            mock.patch.object(
                MODULE,
                "run_process",
                return_value=(0, token, 7),
            ) as process,
        ):
            returncode, raw, sanitized, elapsed, detected = (
                MODULE.run_model_call(
                    command,
                    "prompt",
                    workspace,
                    10,
                    "claude",
                    executable,
                )
            )
        credential_lookup.assert_called_once_with()
        process.assert_called_once_with(
            command,
            "prompt",
            workspace,
            10,
            "claude",
            executable,
            credentials,
        )
        self.assertEqual(0, returncode)
        self.assertEqual(token, raw)
        self.assertEqual("<redacted-credential>", sanitized)
        self.assertEqual(7, elapsed)
        self.assertTrue(detected)

    def test_claude_environment_contains_only_minimal_oauth_auth(
        self,
    ) -> None:
        workspace = self.root / "claude-environment-workspace"
        workspace.mkdir()
        runner_home = self.root / "claude-runner-home"
        runner_home.mkdir()
        executable = self.fake_runner("claude-environment")
        token = "claude-oauth-test-token-987654321"
        base = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(runner_home),
            "LANG": "C",
        }
        with mock.patch.object(MODULE.REVIEWER, "clean_env", return_value=base):
            environment = MODULE.clean_environment(
                workspace,
                "claude",
                executable,
                runner_home,
                {"CLAUDE_CODE_OAUTH_TOKEN": token},
            )
        self.assertEqual(token, environment["CLAUDE_CODE_OAUTH_TOKEN"])
        self.assertEqual(str(runner_home), environment["HOME"])
        self.assertNotIn("ANTHROPIC_API_KEY", environment)
        self.assertNotIn("CLAUDE_CONFIG_DIR", environment)
        with self.assertRaisesRegex(ValueError, "minimal OAuth"):
            MODULE.clean_environment(
                workspace,
                "claude",
                executable,
                runner_home,
                {
                    "CLAUDE_CODE_OAUTH_TOKEN": token,
                    "ANTHROPIC_API_KEY": "forbidden-extra-secret",
                },
            )

    def test_claude_invocation_disables_settings_tools_and_persistence(
        self,
    ) -> None:
        executable = self.fake_runner("claude-command")
        command = MODULE.runner_invocation(
            "claude", executable, "claude-opus-5"
        )
        self.assertEqual("", command[command.index("--setting-sources") + 1])
        self.assertEqual("", command[command.index("--tools") + 1])
        self.assertIn("--strict-mcp-config", command)
        self.assertIn("--no-session-persistence", command)

    def test_incomplete_call_is_persisted_and_exits_two(self) -> None:
        result, report = self.execute("malformed")
        self.assertEqual(2, result.returncode)
        self.assertEqual("INCONCLUSIVE", report["status"])
        self.assertFalse(report["complete"])
        self.assertEqual(1, len(report["runs"]))
        self.assertIn("```json", report["runs"][0]["raw_output"])
        self.assertIn("strict JSON", report["runs"][0]["error"])

    def test_workspace_drift_is_inconclusive(self) -> None:
        result, report = self.execute("workspace-drift")
        self.assertEqual(2, result.returncode)
        self.assertEqual("INCONCLUSIVE", report["status"])
        self.assertIn("workspace changed", report["runs"][0]["error"])

    def test_cli_version_mismatch_is_inconclusive_without_model_calls(self) -> None:
        protocol = json.loads(PROTOCOL_PATH.read_text())
        protocol["matrix"][0]["expected_cli_version"] = "codex-cli 9.9.9"
        changed = self.root / "changed-protocol.json"
        changed.write_text(json.dumps(protocol), encoding="utf-8")
        codex = self.fake_runner("fake-codex", "lift")
        claude = self.fake_runner("fake-claude", "lift")
        report = self.root / "version-report.json"
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--codex-runner-path",
                str(codex),
                "--claude-runner-path",
                str(claude),
                "--protocol",
                str(changed),
                "--output",
                str(report),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("fixed model/CLI matrix drifted", result.stderr)

    def test_runtime_cli_mismatch_is_reported_inconclusive(self) -> None:
        wrong = self.fake_runner("fake-codex", "lift")
        source = wrong.read_text().replace(
            'print("codex-cli 0.146.0" if "codex" in name else "2.1.220 (Claude Code)")',
            'print("codex-cli 0.145.0" if "codex" in name else "2.1.220 (Claude Code)")',
        )
        wrong.write_text(source)
        claude = self.fake_runner("fake-claude", "lift")
        report_path = self.root / "cli-report.json"
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--codex-runner-path",
                str(wrong),
                "--claude-runner-path",
                str(claude),
                "--output",
                str(report_path),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        report = json.loads(report_path.read_text())
        self.assertEqual(2, result.returncode)
        self.assertEqual("INCONCLUSIVE", report["status"])
        self.assertEqual("cli-version-mismatch", report["failures"][0]["kind"])
        self.assertEqual([], report["runs"])
        self.assertTrue(report["provenance"]["pre_post_equal"])
        self.assertEqual(
            report["provenance"]["pre"], report["provenance"]["post"]
        )

    def test_provider_families_are_equal_weighted_after_family_mean(self) -> None:
        protocol = MODULE.validate_protocol(MODULE.load_strict(PROTOCOL_PATH))
        report = {"runs": []}

        def score(value: float) -> dict:
            return {
                "summary": {
                    "planning_accuracy": value,
                    "fault_mode_accuracy": {
                        "auth": value,
                        "behavior": value,
                        "label": value,
                        "write": value,
                    },
                    "fault_mode_macro_accuracy": value,
                    "worst_case_fault_mode_accuracy": value,
                    "cypress_controls": 5,
                    "cypress_controls_passed": 5,
                },
                "results": [
                    {
                        "case_id": case_id,
                        "case_score": value,
                        "scored": True,
                    }
                    for case_id in (
                        "pw-counter-transition",
                        "pw-increment-accessible-name",
                        "pw-authenticated-account",
                        "pw-increment-request",
                    )
                ],
            }

        for config, value in zip(protocol["matrix"], (1.0, 1.0, 0.0)):
            for arm in MODULE.ARMS:
                report["runs"].append(
                    {
                        "valid": True,
                        "configuration_id": config["configuration_id"],
                        "arm": arm,
                        "score": score(value),
                    }
                )
        MODULE.aggregate(report, protocol)
        metrics = report["metrics"]
        self.assertEqual(
            0.5,
            metrics["provider_family"]["anthropic"]["arms"]["full-skill"][
                "planning_accuracy"
            ],
        )
        self.assertEqual(
            0.75,
            metrics["equal_provider_family_weighted"]["full-skill"][
                "planning_accuracy"
            ],
        )
        self.assertNotEqual(
            2 / 3,
            metrics["equal_provider_family_weighted"]["full-skill"][
                "planning_accuracy"
            ],
        )

    def test_output_path_rejects_sources_symlinks_hardlinks_and_unsafe_parent(
        self,
    ) -> None:
        codex = self.fake_runner("output-codex")
        claude = self.fake_runner("output-claude")
        runners = {"codex": codex.resolve(), "claude": claude.resolve()}
        with self.assertRaisesRegex(ValueError, "outside"):
            MODULE.validate_output_path(
                MODULE.CORPUS_PATH, PROTOCOL_PATH, runners
            )
        target = self.root / "target.json"
        target.write_text("{}")
        alias = self.root / "alias.json"
        alias.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlink"):
            MODULE.validate_output_path(alias, PROTOCOL_PATH, runners)
        hardlink = self.root / "hardlink.json"
        hardlink.hardlink_to(codex)
        with self.assertRaisesRegex(ValueError, "aliases"):
            MODULE.validate_output_path(hardlink, PROTOCOL_PATH, runners)
        parent_target = self.root / "real-parent"
        parent_target.mkdir()
        parent_alias = self.root / "parent-alias"
        parent_alias.symlink_to(parent_target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "parent"):
            MODULE.validate_output_path(
                parent_alias / "report.json", PROTOCOL_PATH, runners
            )

    def test_version_probe_drift_records_actual_post_snapshot(self) -> None:
        codex = self.fake_runner("probe-codex")
        source = codex.read_text().replace(
            'print("codex-cli 0.146.0" if "codex" in name else "2.1.220 (Claude Code)")',
            'print("codex-cli 0.146.0" if "codex" in name else "2.1.220 (Claude Code)"); '
            'Path(sys.argv[0]).write_text(Path(sys.argv[0]).read_text() + "\\n# drift")',
        )
        codex.write_text(source)
        codex.chmod(codex.stat().st_mode | stat.S_IXUSR)
        claude = self.fake_runner("probe-claude")
        report_path = self.root / "probe-drift.json"
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--codex-runner-path",
                str(codex),
                "--claude-runner-path",
                str(claude),
                "--output",
                str(report_path),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        report = json.loads(report_path.read_text())
        self.assertEqual(2, result.returncode)
        self.assertEqual([], report["runs"])
        self.assertFalse(report["provenance"]["pre_post_equal"])
        self.assertNotEqual(
            report["provenance"]["pre"]["runner_cli_sha256"],
            report["provenance"]["post"]["runner_cli_sha256"],
        )
        self.assertEqual(
            "input-drift-during-version-probe",
            report["failures"][0]["kind"],
        )

    def test_pinned_runtime_matrix_proves_all_36_cells(self) -> None:
        self.assertEqual(
            {"operators": 12, "cells_expected": 36, "cells_matched": 36},
            MODULE.validate_full_runtime_matrix(),
        )

    def test_source_and_skill_drift_stop_the_live_schedule(self) -> None:
        for function_name, message in (
            ("source_snapshot", "benchmark source changed"),
            ("skill_snapshot", "generator skill changed"),
        ):
            with self.subTest(function_name=function_name):
                codex = self.fake_runner(f"{function_name}-codex", "lift")
                claude = self.fake_runner(f"{function_name}-claude", "lift")
                report_path = self.root / f"{function_name}.json"
                original = getattr(MODULE, function_name)
                baseline = original()
                calls = 0

                def drifting_snapshot():
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        return baseline
                    changed = dict(baseline)
                    changed[next(iter(changed))] = "0" * 64
                    return changed

                old_argv = sys.argv
                setattr(MODULE, function_name, drifting_snapshot)
                sys.argv = [
                    str(RUNNER_PATH),
                    "--codex-runner-path",
                    str(codex),
                    "--claude-runner-path",
                    str(claude),
                    "--output",
                    str(report_path),
                    "--timeout",
                    "10",
                ]
                try:
                    with mock.patch.dict(
                        os.environ,
                        {
                            "CLAUDE_CODE_OAUTH_TOKEN": (
                                "claude-oauth-fixture-token-987654321"
                            )
                        },
                    ):
                        exit_code = MODULE.main()
                finally:
                    sys.argv = old_argv
                    setattr(MODULE, function_name, original)
                report = json.loads(report_path.read_text())
                self.assertEqual(2, exit_code)
                self.assertEqual("INCONCLUSIVE", report["status"])
                self.assertEqual(1, len(report["runs"]))
                self.assertIn(message, report["runs"][0]["error"])


if __name__ == "__main__":
    unittest.main()
