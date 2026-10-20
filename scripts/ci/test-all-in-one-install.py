#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Setup collision, preservation and routing tests; never write the real home."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if sys.version_info < (3, 11):
    print("SKIP: all-in-one installer requires Python 3.11+ (documented prerequisite)")
    raise SystemExit(0)
import tomllib

spec = importlib.util.spec_from_file_location("e2e_setup", ROOT / "scripts/dev/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def setUp(self):
        # Retain the temporary path even on failure until the test cleanup runs.
        self.temp = tempfile.TemporaryDirectory(prefix="e2e setup tests ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / "home"
        self.home.mkdir()
        self.project = self.base / "project with spaces"
        self.project.mkdir()
        self.config = self.project / "playwright.config.cjs"
        self.config.write_text("throw Error('PROJECT CONFIG MUST NOT EXECUTE DURING INSTALL');\n")
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", "CODEX_HOME": str(self.home / ".codex"), "CLAUDE_CONFIG_DIR": str(self.home / ".claude")}
        package = self.project / "node_modules/playwright"
        package.mkdir(parents=True)
        (package / "package.json").write_text('{"name":"playwright","version":"fixture"}')
        self.cli = package / "cli.js"
        self.cli.write_text("throw Error('dry-run must never execute project CLI');")

    def fake_run(self, command, cwd, env):
        if command[-1] == "--help":
            return subprocess.CompletedProcess(command, 0, "choices: claude, codex", "")
        host = command[-1].split("=")[-1]
        folder = Path(cwd) / (".codex/agents" if host == "codex" else ".claude/agents")
        folder.mkdir(parents=True)
        for role in ("planner", "generator", "healer"):
            if host == "codex":
                text = f'name = "playwright_test_{role}"\ndeveloper_instructions = "official fixture"\n\n[mcp_servers.playwright-test]\ncommand = "npx"\nargs = ["playwright", "run-test-mcp-server"]\nenabled_tools = ["generator_write_test"]\n'
                name = f"playwright_test_{role}.toml"
            else:
                text = f"---\nname: playwright-test-{role}\n---\nofficial fixture\n"
                name = f"playwright-test-{role}.md"
            (folder / name).write_text(text)
        return subprocess.CompletedProcess(command, 0, "generated", "")

    def plan(self, host="codex", dry=False):
        with patch.object(setup, "run", side_effect=self.fake_run):
            return setup.project_plan(self.project, host, self.env, dry)

    def test_codex_real_config_is_not_executed_and_children_match(self):
        plan = self.plan()
        setup.apply_plan(plan)
        config = tomllib.loads((self.project / ".codex/config.toml").read_text())
        parent = config["mcp_servers"]["playwright-test"]
        self.assertEqual(parent["args"][-1], str(self.config))
        self.assertTrue(parent["required"])
        for path in (self.project / ".codex/agents").glob("*.toml"):
            child = tomllib.loads(path.read_text())["mcp_servers"]["playwright-test"]
            self.assertEqual(child["command"], parent["command"])
            self.assertEqual(child["args"], parent["args"])
            self.assertIn("generator_write_test", child["enabled_tools"])
        self.assertFalse((self.project / "tests").exists())
        self.assertFalse((self.project / "specs").exists())

    def test_codex_preserves_existing_config_and_is_idempotent(self):
        target = self.project / ".codex/config.toml"
        target.parent.mkdir()
        before = b'# keep comment\nmodel = "example"\n[mcp_servers.other]\ncommand = "other"\n'
        target.write_bytes(before)
        plan = self.plan()
        setup.preflight_backups(plan)
        setup.apply_plan(plan)
        self.assertTrue(target.read_bytes().startswith(before.rstrip()))
        self.assertEqual(target.with_name(target.name + ".e2e-skills-backup").read_bytes(), before)
        self.assertEqual(target.with_name(target.name + ".e2e-skills-backup").stat().st_mode & 0o777, 0o600)
        after = target.read_bytes()
        setup.apply_plan(self.plan())
        self.assertEqual(target.read_bytes(), after)

    def test_claude_preserves_other_mcp_and_is_idempotent(self):
        target = self.project / ".mcp.json"
        target.write_text('{"mcpServers":{"other":{"command":"keep"}},"custom":42}')
        setup.apply_plan(self.plan("claude"))
        after = target.read_bytes()
        parsed = json.loads(after)
        self.assertEqual(parsed["mcpServers"]["other"], {"command": "keep"})
        self.assertEqual(parsed["custom"], 42)
        setup.apply_plan(self.plan("claude"))
        self.assertEqual(target.read_bytes(), after)

    def test_foreign_mcp_conflict_changes_nothing(self):
        for host, relative, content in (("codex", ".codex/config.toml", '[mcp_servers.playwright-test]\ncommand="foreign"\n'), ("claude", ".mcp.json", '{"mcpServers":{"playwright-test":{"command":"foreign"}}}')):
            with self.subTest(host=host):
                target = self.project / relative
                target.parent.mkdir(exist_ok=True)
                target.write_text(content)
                with self.assertRaisesRegex(ValueError, "MCP differs"):
                    self.plan(host)
                self.assertEqual(target.read_text(), content)

    def test_foreign_agent_conflict_changes_nothing(self):
        target = self.project / ".codex/agents/playwright_test_planner.toml"
        target.parent.mkdir(parents=True)
        target.write_text("foreign sentinel")
        with self.assertRaisesRegex(ValueError, "existing file differs"):
            self.plan()
        self.assertEqual(target.read_text(), "foreign sentinel")
        self.assertFalse((self.project / ".codex/config.toml").exists())

    def test_symlinked_mcp_parent_is_rejected(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.project / ".codex").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked destination"):
            self.plan()
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_backup_rejected_before_install(self):
        target = self.project / ".mcp.json"
        target.write_text('{}')
        backup = target.with_name(target.name + ".e2e-skills-backup")
        backup.write_text("keep recovery")
        with self.assertRaisesRegex(ValueError, "backup already exists"):
            setup.preflight_backups(self.plan("claude"))
        self.assertEqual(target.read_text(), '{}')
        self.assertEqual(backup.read_text(), "keep recovery")

    def test_concurrent_change_rejected(self):
        plan = self.plan()
        target = self.project / ".codex/config.toml"
        target.parent.mkdir(parents=True)
        target.write_text("foreign writer")
        with self.assertRaisesRegex(ValueError, "changed during installation"):
            setup.apply_plan(plan)
        self.assertEqual(target.read_text(), "foreign writer")

    def test_dry_run_does_not_execute_project_or_write(self):
        with patch.object(setup, "run", side_effect=AssertionError("project executed")):
            plan = setup.project_plan(self.project, "codex", self.env, True)
        self.assertEqual(len(plan), 1)
        self.assertFalse((self.project / ".codex").exists())

    def test_unsupported_loop_fails_before_global_installs(self):
        with patch.object(setup, "run", return_value=subprocess.CompletedProcess([], 0, "choices: claude", "")):
            with self.assertRaisesRegex(ValueError, "does not advertise"):
                setup.project_plan(self.project, "codex", self.env, False)
        self.assertFalse((self.project / ".codex").exists())

    def test_backup_config_filename_not_accepted(self):
        self.config.rename(self.project / "playwright.config.ts.bak")
        with self.assertRaisesRegex(ValueError, "directory containing"):
            self.plan()

    def test_main_routes_host_and_dry_run(self):
        for host in ("codex", "claude"):
            with self.subTest(host=host), patch.object(setup, "clean_env", return_value=self.env.copy()), patch.object(setup.subprocess, "run") as call:
                self.assertEqual(setup.main(["--host", host, "--dry-run"]), 0)
                call.assert_not_called()
                self.assertEqual(setup.main(["--host", host]), 0)
                self.assertEqual(call.call_count, 1 if host == "codex" else 2)
                env = call.call_args_list[0].kwargs["env"]
                self.assertEqual(env["E2E_SKILLS_AGENTS"], "-a codex" if host == "codex" else "-a claude-code -a codex")
                self.assertEqual(env["E2E_SKILLS_INSTALL_CODEX_AGENTS"], "1" if host == "codex" else "0")


if __name__ == "__main__":
    unittest.main()
