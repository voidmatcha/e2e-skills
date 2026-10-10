#!/usr/bin/env python3
"""Offline Docker transport isolation and evidence checks. Apache-2.0."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("container_adapter", ROOT / "scripts/evals/generator_codex_container_adapter.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def stream(final=None):
    answer = final or {"spec_files": ["tests/new.spec.mjs"], "status": "complete", "summary": "done"}
    return "\n".join(json.dumps(event) for event in [
        {"type": "item.completed", "item": {"type": "command_execution", "command": "node_modules/.bin/playwright test --repeat-each=3"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(answer)}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 3}},
    ])


class ContainerAdapter(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.work = self.base / "work"
        self.project = self.work / "project"
        self.project.mkdir(parents=True)
        (self.project / "node_modules").symlink_to(self.base / "fixture-modules")
        self.engine = SimpleNamespace(
            CODEX_TRANSCRIPTS=self.base / "transcripts", CODEX_DOCKER="/trusted/docker",
            CODEX_DOCKER_CONTEXT="colima", CODEX_CONTAINER_IMAGE="sha256:" + "a" * 64,
            FRAME="Task: {task}", SKILL_LINE=" Read {gen} and {rev}", OUTPUT_SCHEMA={"type": "object"},
            sanitize=lambda text, paths: self.sanitize(text, paths),
            stage_skills=Mock(return_value=(self.work / "skill/generator", self.work / "skill/reviewer")))
        self.helper = SimpleNamespace(clean_env=Mock(return_value={"PATH": "/bin", "HOME": "/trusted/client-home"}),
                                      stage_codex_auth=Mock())
        self.proc = Mock(pid=12345, returncode=0)
        self.proc.communicate.return_value = (stream(), "")
        self.removal = Mock(returncode=0, stderr="")

    @staticmethod
    def sanitize(text, paths):
        for path in sorted(paths, key=len, reverse=True):
            text = text.replace(path, "<private>")
        return text

    def call(self, arm="no-skill", task="Write a test"):
        with patch.object(adapter.shared, "helpers", return_value=self.helper), \
             patch.object(adapter.subprocess, "Popen", return_value=self.proc) as launch, \
             patch.object(adapter.subprocess, "run", return_value=self.removal) as cleanup:
            result = adapter.configure(self.engine)(self.project, self.work, arm, task, "gpt-5.5", 5, 4)
        self.launch, self.cleanup = launch, cleanup
        return result

    def test_docker_enforces_identity_mounts_and_capabilities(self):
        result = self.call()
        self.assertFalse(result["infrastructure_error"])
        argv = self.launch.call_args.args[0]
        self.assertEqual(argv[:4], ["/trusted/docker", "--context", "colima", "run"])
        self.assertEqual(argv[argv.index("--user") + 1], f"{os.getuid()}:{os.getgid()}")
        self.assertEqual(argv[argv.index("--cap-drop") + 1], "ALL")
        self.assertIn("no-new-privileges", argv)
        self.assertIn("--read-only", argv)
        self.assertIn("bridge", argv)
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("--publish", argv)
        self.assertNotIn("host", argv)
        mounts = [argv[index + 1] for index, item in enumerate(argv) if item == "--mount"]
        self.assertEqual(len(mounts), 2)
        self.assertEqual(mounts[0], f"type=bind,src={self.work},dst=/work")
        self.assertTrue(mounts[1].endswith(",dst=/auth-source,readonly"))
        self.assertFalse(any("docker.sock" in item for item in argv))
        self.assertIn("danger-full-access", argv)
        self.assertIn("--ignore-user-config", argv)
        self.assertIn('web_search="disabled"', argv)
        self.assertIn("HOME=/codex-home", argv)
        self.assertTrue(any(arg.startswith("/codex-home:rw,nosuid,nodev,mode=0700,uid=") for arg in argv))
        self.assertFalse(any("/trusted/client-home" in item for item in argv))
        self.assertEqual(argv[-1], "-")
        name = argv[argv.index("--name") + 1]
        self.assertEqual(self.cleanup.call_args.args[0], ["/trusted/docker", "--context", "colima", "rm", "--force", name])

    def test_prompt_is_stdin_not_shell_interpolation(self):
        task = "$(touch /tmp/unsafe); `echo secret` '\""
        self.call(task=task)
        self.assertNotIn(task, self.launch.call_args.args[0])
        self.assertEqual(self.proc.communicate.call_args.args[0], "Task: " + task)
        self.assertIn('exec /usr/bin/codex "$@"', adapter.START)

    def test_full_fixed_exact_snapshot_paths_remapped_only(self):
        self.call("full-fixed")
        self.engine.stage_skills.assert_called_once_with(self.work, "full-fixed")
        prompt = self.proc.communicate.call_args.args[0]
        self.assertIn("/work/skill/generator/SKILL.md", prompt)
        self.assertIn("/work/skill/reviewer/SKILL.md", prompt)
        self.assertNotIn(str(self.work), prompt)

    def test_usage_and_indicators_never_claim_independent_verification(self):
        result = self.call()
        self.assertIsNone(result["cost_usd"])
        self.assertEqual(result["usage"]["input_tokens"], 10)
        self.assertEqual(result["compliance"]["repeat_each_runs"], 1)
        self.assertEqual(result["compliance"]["semantic_compliance"], "unverified")
        self.assertFalse(result["compliance"]["legitimate_complete"])
        self.assertIsNone(result["compliance"]["read_generator_skill"])
        self.assertTrue(Path(result["transcript_path"]).is_file())

    def test_failures_and_schema_are_strict(self):
        cases = [(stream() + "\ninvalid", 0), (stream(), 1), ('{"type":"thread.started"}', 0),
                 (stream({"spec_files": [], "status": "complete", "summary": 5}), 0)]
        for stdout, code in cases:
            self.proc.returncode = code
            self.proc.communicate.return_value = (stdout, "")
            with self.subTest(code=code, stdout=stdout):
                self.assertTrue(self.call()["infrastructure_error"])

    def test_rate_limit_stops_but_task_mention_does_not(self):
        self.proc.communicate.return_value = ('{"type":"error","message":"usage limit reached"}', "")
        self.assertTrue(self.call()["fatal_infrastructure"])
        self.proc.communicate.return_value = (stream({"spec_files": [], "status": "complete", "summary": "usage limit tested"}), "")
        self.assertFalse(self.call()["infrastructure_error"])

    def test_timeout_and_interrupt_kill_client_and_exact_container(self):
        for interrupt in (subprocess.TimeoutExpired("docker", 5), KeyboardInterrupt()):
            self.proc.communicate.side_effect = [interrupt, (stream(), "")]
            with patch.object(adapter.shared.os, "killpg") as kill:
                if isinstance(interrupt, KeyboardInterrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        self.call()
                else:
                    self.assertTrue(self.call()["timeout"])
            kill.assert_called_once_with(12345, adapter.shared.signal.SIGKILL)
            # call() raises before assigning attributes on interruption, but previous
            # timeout cleanup already proves the exact generated name is used.
        self.assertEqual(len(list((self.base / "transcripts").glob("*.jsonl"))), 2)

    def test_fixture_link_restored_for_host_scoring(self):
        original = os.readlink(self.project / "node_modules")
        def run_in_container(*args, **kwargs):
            modules = self.project / "node_modules"
            modules.unlink()
            modules.symlink_to("/opt/fixtures/node_modules")
            return stream(), ""
        self.proc.communicate.side_effect = run_in_container
        self.call()
        self.assertEqual(os.readlink(self.project / "node_modules"), original)

    def test_model_modified_module_path_is_never_deleted(self):
        def run_in_container(*args, **kwargs):
            modules = self.project / "node_modules"
            modules.unlink()
            modules.write_text("model changed infrastructure")
            return stream(), ""
        self.proc.communicate.side_effect = run_in_container
        self.call()
        self.assertEqual((self.project / "node_modules").read_text(), "model changed infrastructure")

    def test_cleanup_error_retains_transcript(self):
        self.removal.returncode, self.removal.stderr = 1, "daemon error"
        self.assertTrue(self.call()["infrastructure_error"])
        self.assertEqual(len(list((self.base / "transcripts").glob("*.jsonl"))), 1)

    def test_mutable_images_relative_client_and_nonfixture_mount_refused(self):
        for image in ("latest", "repository:version", "sha256:abc"):
            self.engine.CODEX_CONTAINER_IMAGE = image
            self.assertTrue(self.call()["infrastructure_error"])
        self.engine.CODEX_CONTAINER_IMAGE = "sha256:" + "a" * 64
        self.engine.CODEX_DOCKER = "docker"
        self.assertTrue(self.call()["infrastructure_error"])
        with self.assertRaisesRegex(ValueError, "disposable"):
            adapter.configure(self.engine)(ROOT, ROOT.parent, "no-skill", "task", "model", 5, 4)


if __name__ == "__main__":
    unittest.main()
