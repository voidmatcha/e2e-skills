#!/usr/bin/env python3
"""Offline Codex generator transport checks. Apache-2.0."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("adapter", ROOT / "scripts/evals/generator_codex_adapter.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def stream(final=None):
    answer = final or {"spec_files": ["tests/new.spec.mjs"], "status": "complete", "summary": "done"}
    return "\n".join(json.dumps(event) for event in [
        {"type": "item.completed", "item": {"type": "command_execution", "command": "node_modules/.bin/playwright test --repeat-each=3"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(answer)}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 3}},
    ])


class Adapter(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.engine = SimpleNamespace(
            CODEX_TRANSCRIPTS=self.base / "transcripts", FRAME="Task: {task}",
            SKILL_LINE="Read {gen} and {rev}", OUTPUT_SCHEMA={"type": "object"},
            sanitize=lambda text, paths: self.sanitize(text, paths),
            stage_skills=Mock(return_value=(self.base / "generator", self.base / "reviewer")))
        self.helper = SimpleNamespace(clean_env=Mock(side_effect=lambda runner, home: {"PATH": "/bin", "HOME": home}),
                                      stage_codex_auth=Mock(return_value=self.base / "private-auth"))
        self.proc = Mock(pid=12345, returncode=0)
        self.proc.communicate.return_value = (stream(), "")

    @staticmethod
    def sanitize(text, paths):
        for path in sorted(paths, key=len, reverse=True):
            text = text.replace(path, "<private>")
        return text

    def call(self, arm="no-skill"):
        with patch.object(adapter, "helpers", return_value=self.helper), \
             patch.object(adapter, "browser_cache", return_value=self.base / "browsers"), \
             patch.object(adapter.shutil, "which", return_value="/bin/codex"), \
             patch.object(adapter.subprocess, "Popen", return_value=self.proc) as launch:
            result = adapter.configure(self.engine)(self.base / "project", self.base / "work", arm,
                                                    "Write a test", "gpt-6.1-sol", 5, 4)
        self.launch = launch
        return result

    def test_success_uses_isolated_sandbox_and_records_usage(self):
        result = self.call()
        self.assertFalse(result["infrastructure_error"])
        self.assertEqual(result["usage"]["input_tokens"], 10)
        self.assertIsNone(result["cost_usd"])
        self.assertEqual(result["structured_output"]["status"], "complete")
        command = self.launch.call_args.args[0]
        for flag in ("--json", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--output-schema"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertIn("sandbox_workspace_write.network_access=true", command)
        self.assertIn('web_search="disabled"', command)
        self.assertNotIn("tools.web_search=false", command)
        self.assertIn('shell_environment_policy.set.PATH="/bin"', command)
        self.assertIn(f'shell_environment_policy.set.PLAYWRIGHT_BROWSERS_PATH={json.dumps(str(self.base / "browsers"))}', command)
        self.assertTrue(any(arg.startswith('shell_environment_policy.set.HOME=') for arg in command))
        self.assertEqual(self.launch.call_args.kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"], str(self.base / "browsers"))
        self.assertTrue(Path(result["transcript_path"]).is_file())
        self.engine.stage_skills.assert_not_called()
        self.helper.clean_env.assert_called_once()
        self.assertTrue(self.launch.call_args.kwargs["start_new_session"])

    def test_full_fixed_stages_exact_engine_snapshot(self):
        self.call("full-fixed")
        self.engine.stage_skills.assert_called_once_with(self.base / "work", "full-fixed")
        self.assertIn("SKILL.md", self.proc.communicate.call_args.args[0])

    def test_process_indicators_not_semantic_compliance(self):
        result = self.call()
        self.assertEqual(result["compliance"]["playwright_test_runs"], 1)
        self.assertEqual(result["compliance"]["repeat_each_runs"], 1)
        self.assertEqual(result["compliance"]["agent_spawns"], 0)
        self.assertFalse(result["compliance"]["legitimate_complete"])
        self.assertIsNone(result["compliance"]["read_generator_skill"])

    def test_rate_limit_is_fatal(self):
        self.proc.communicate.return_value = ('{"type":"error","message":"usage limit reached"}', "")
        result = self.call()
        self.assertTrue(result["infrastructure_error"])
        self.assertTrue(result["fatal_infrastructure"])

    def test_app_rate_limit_mention_is_not_infrastructure(self):
        self.proc.communicate.return_value = (stream({"spec_files": [], "status": "complete",
                                                     "summary": "Verified usage limit behavior"}), "")
        self.assertFalse(self.call()["infrastructure_error"])

    def test_nonzero_malformed_and_missing_completion_refused(self):
        for stdout, code in [(stream() + "\nnot-json", 0), (stream(), 1), ('{"type":"thread.started"}', 0)]:
            self.proc.returncode = code
            self.proc.communicate.return_value = (stdout, "")
            with self.subTest(stdout=stdout):
                self.assertTrue(self.call()["infrastructure_error"])

    def test_invalid_final_schema_refused(self):
        self.proc.communicate.return_value = (stream({"spec_files": [], "status": "complete", "summary": 1}), "")
        self.assertTrue(self.call()["infrastructure_error"])

    def test_timeout_kills_process_group_and_retains_evidence(self):
        self.proc.communicate.side_effect = [subprocess.TimeoutExpired("codex", 5), (stream(), "")]
        with patch.object(adapter.os, "killpg") as kill:
            result = self.call()
        kill.assert_called_once_with(12345, adapter.signal.SIGKILL)
        self.assertTrue(result["timeout"])
        self.assertFalse(result["infrastructure_error"])
        self.assertTrue(Path(result["transcript_path"]).is_file())

    def test_interrupt_kills_process_group(self):
        self.proc.communicate.side_effect = [KeyboardInterrupt(), ('{"type":"thread.started"}', "")]
        with patch.object(adapter.os, "killpg") as kill:
            with self.assertRaises(KeyboardInterrupt):
                self.call()
        kill.assert_called_once_with(12345, adapter.signal.SIGKILL)
        self.assertEqual(len(list((self.base / "transcripts").glob("*.jsonl"))), 1)

    def test_checkout_transcripts_refused(self):
        self.engine.CODEX_TRANSCRIPTS = ROOT / "reports"
        with self.assertRaisesRegex(ValueError, "outside"):
            self.call()


if __name__ == "__main__":
    unittest.main()
