#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Setup collision, preservation and routing tests; never write the real home."""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
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


    def snapshot(self):
        return {str(path.relative_to(self.base)): path.read_bytes()
                for path in self.base.rglob("*") if path.is_file()}

    def installed_config(self, host):
        setup.apply_plan(self.plan(host))
        return self.project / (".codex/config.toml" if host == "codex" else ".mcp.json")

    def assert_unverified(self, report):
        self.assertEqual(report["session"], "unverified")
        self.assertEqual(report["approval"], "unknown")

    def test_check_absent_config_preserves_all_files_both_hosts(self):
        for host in ("codex", "claude"):
            with self.subTest(host=host):
                before = self.snapshot()
                with patch.object(setup, "project_plan") as plan, patch.object(setup, "mcp_tools") as tools:
                    report = setup.check_setup(self.project, host, self.env)
                self.assertEqual(report["status"], "CONFIG_MISSING")
                self.assert_unverified(report)
                plan.assert_not_called()
                tools.assert_not_called()
                self.assertEqual(self.snapshot(), before)

    def test_check_invalid_config_and_foreign_command_never_execute(self):
        for host in ("codex", "claude"):
            target = self.project / (".codex/config.toml" if host == "codex" else ".mcp.json")
            target.parent.mkdir(exist_ok=True)
            sentinel = self.base / "foreign-command-ran"
            foreign = [sys.executable, "-c", f"from pathlib import Path; Path({str(sentinel)!r}).touch()"]
            if host == "codex":
                content = '[mcp_servers.playwright-test]\ncommand = ' + json.dumps(foreign[0]) + '\nargs = ' + json.dumps(foreign[1:]) + '\n'
            else:
                content = json.dumps({"mcpServers": {"playwright-test": {"command": foreign[0], "args": foreign[1:]}}})
            for text in ("not valid configuration [", content):
                with self.subTest(host=host, foreign=text == content):
                    target.write_text(text)
                    before = self.snapshot()
                    with patch.object(setup, "mcp_tools", side_effect=AssertionError("foreign command executed")):
                        report = setup.check_setup(self.project, host, self.env)
                    self.assertEqual(report["status"], "CONFIG_ERROR")
                    self.assert_unverified(report)
                    self.assertEqual(self.snapshot(), before)
                    self.assertFalse(sentinel.exists())

    def test_check_disabled_and_filtered_tools_do_not_start_server(self):
        for host in ("codex", "claude"):
            target = self.installed_config(host)
            original = target.read_text()
            for setting, status in (("enabled = false", "CONFIG_DISABLED"),
                                    ('enabled_tools = ["browser_navigate"]', "TOOLS_BLOCKED"),
                                    ('disabled_tools = ["generator_write_test"]', "TOOLS_BLOCKED")):
                with self.subTest(host=host, setting=setting):
                    key, value = setting.split(" = ", 1)
                    if host == "codex":
                        # Replace the generated allowlist before adding a custom one.
                        lines = [line for line in original.splitlines() if not line.startswith(key + " = ")]
                        target.write_text("\n".join(lines) + "\n" + setting + "\n")
                    else:
                        parsed = json.loads(original)
                        parsed["mcpServers"]["playwright-test"][key] = json.loads(value)
                        target.write_text(json.dumps(parsed))
                    before = self.snapshot()
                    with patch.object(setup, "mcp_tools") as tools, patch.object(setup, "project_plan") as plan:
                        report = setup.check_setup(self.project, host, self.env)
                    self.assertEqual(report["status"], status)
                    self.assert_unverified(report)
                    tools.assert_not_called()
                    plan.assert_not_called()
                    self.assertEqual(self.snapshot(), before)
            target.write_text(original)

    def test_check_claude_project_settings_disable_server(self):
        self.installed_config("claude")
        for relative in (".claude/settings.json", ".claude/settings.local.json"):
            with self.subTest(relative=relative):
                target = self.project / relative
                target.parent.mkdir(exist_ok=True)
                target.write_text('{"disabledMcpjsonServers":["playwright-test"]}')
                with patch.object(setup, "mcp_tools") as tools:
                    report = setup.check_setup(self.project, "claude", self.env)
                self.assertEqual(report["status"], "CONFIG_DISABLED")
                tools.assert_not_called()
                target.unlink()

    def test_check_discovery_results_never_infer_session_or_approval(self):
        required = {"planner_setup_page", "planner_save_plan", "generator_setup_page", "generator_write_test"}
        for host in ("codex", "claude"):
            target = self.installed_config(host)
            for result, status in ((TimeoutError("approval denied (untrusted server text)"), "SERVER_ERROR"),
                                   (required - {"generator_write_test"}, "TOOLS_MISSING"),
                                   (required | {"browser_navigate"}, "SERVER_VERIFIED")):
                with self.subTest(host=host, status=status):
                    kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
                    before = self.snapshot()
                    with patch.object(setup, "run", side_effect=AssertionError("agent generation ran")), patch.object(setup, "mcp_tools", **kwargs) as tools:
                        report = setup.check_setup(self.project, host, self.env)
                    self.assertEqual(report["status"], status)
                    self.assert_unverified(report)
                    tools.assert_called_once()
                    configured = (tomllib.loads(target.read_text())["mcp_servers"]["playwright-test"] if host == "codex"
                                  else json.loads(target.read_text())["mcpServers"]["playwright-test"])
                    tools.assert_called_once_with([configured["command"], *configured["args"]], self.project, self.env)
                    self.assertEqual(self.snapshot(), before)
                    if status == "TOOLS_MISSING":
                        self.assertEqual(report["missing_tools"], ["generator_write_test"])
                    if status == "SERVER_ERROR":
                        self.assertNotIn("approval denied", json.dumps(report))

    def test_check_cli_requires_project_and_excludes_dry_run(self):
        for arguments in (("--check",), ("--check", "--project", str(self.project), "--dry-run")):
            with self.subTest(arguments=arguments), contextlib.redirect_stderr(io.StringIO()), patch.object(setup, "clean_env") as env:
                with self.assertRaises(SystemExit) as raised:
                    setup.main(["--host", "codex", *arguments])
                self.assertEqual(raised.exception.code, 2)
                env.assert_not_called()

    def test_check_cli_skips_installers_preflight_and_writes(self):
        for host in ("codex", "claude"):
            for status, code in (("SERVER_VERIFIED", 0), ("CONFIG_MISSING", 1)):
                with self.subTest(host=host, status=status):
                    before = self.snapshot()
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output), patch.object(setup, "clean_env", return_value=self.env), patch.object(setup, "check_setup", return_value={"status": status}) as check, patch.object(setup, "dedicated_preflight", side_effect=AssertionError("preflight ran")), patch.object(setup, "apply_plan", side_effect=AssertionError("write attempted")), patch.object(setup.subprocess, "run", side_effect=AssertionError("installer ran")):
                        self.assertEqual(setup.main(["--host", host, "--project", str(self.project), "--check"]), code)
                    check.assert_called_once_with(self.project, host, self.env)
                    self.assertEqual(json.loads(output.getvalue())["status"], status)
                    self.assertEqual(self.snapshot(), before)

    def fake_mcp(self, body):
        script = self.base / "fake_mcp.py"
        transcript = self.base / "mcp-transcript.jsonl"
        pidfile = self.base / "mcp-pid"
        script.write_text("import json, os, sys, time\nfrom pathlib import Path\n"
                          f"Path({str(pidfile)!r}).write_text(str(os.getpid()))\n"
                          f"log = open({str(transcript)!r}, 'a', buffering=1)\n"
                          "def receive():\n"
                          "    message = json.loads(sys.stdin.readline())\n"
                          "    log.write(json.dumps(message) + '\\n')\n"
                          "    return message\n"
                          "def respond(message, result):\n"
                          "    print(json.dumps({'jsonrpc':'2.0', 'id':message['id'], 'result':result}), flush=True)\n"
                          + body)
        return [sys.executable, str(script)], transcript, pidfile

    def assert_child_reaped(self, pidfile):
        pid = int(pidfile.read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_mcp_stdio_handshake_pagination_and_no_tool_execution(self):
        command, transcript, pidfile = self.fake_mcp(
            "init = receive()\n"
            "assert init['method'] == 'initialize'\n"
            "respond(init, {'capabilities': {'tools': {}}})\n"
            "assert receive()['method'] == 'notifications/initialized'\n"
            "first = receive()\n"
            "assert first['method'] == 'tools/list'\n"
            "respond(first, {'tools':[{'name':'planner_setup_page'}], 'nextCursor':'page2'})\n"
            "second = receive()\n"
            "assert second['method'] == 'tools/list' and second['params']['cursor'] == 'page2'\n"
            "respond(second, {'tools':[{'name':'generator_write_test'}, {'name':'planner_setup_page'}]})\n"
            "while True: receive()\n")
        self.assertEqual(setup.mcp_tools(command, self.project, self.env, timeout=3),
                         {"planner_setup_page", "generator_write_test"})
        messages = [json.loads(line) for line in transcript.read_text().splitlines()]
        self.assertEqual([message["method"] for message in messages],
                         ["initialize", "notifications/initialized", "tools/list", "tools/list"])
        self.assert_child_reaped(pidfile)

    def test_mcp_timeout_and_output_limit_reap_child(self):
        for body, error in (("receive()\ntime.sleep(30)\n", TimeoutError),
                            ("receive()\nsys.stdout.write('x' * (5 * 1024 * 1024))\nsys.stdout.flush()\ntime.sleep(30)\n", ValueError)):
            with self.subTest(error=error.__name__):
                command, transcript, pidfile = self.fake_mcp(body)
                start = time.monotonic()
                with self.assertRaises(error):
                    setup.mcp_tools(command, self.project, self.env, timeout=1)
                self.assertLess(time.monotonic() - start, 5)
                self.assert_child_reaped(pidfile)
                self.assertNotIn('"method": "tools/call"', transcript.read_text())

    def test_mcp_request_backpressure_obeys_deadline_and_reaps_child(self):
        # Queue valid replies without consuming requests: escaped NUL cursors
        # expand each next request enough to fill the client's stdin pipe.
        command, transcript, pidfile = self.fake_mcp(
            "respond(receive(), {'capabilities': {'tools': {}}})\n"
            "assert receive()['method'] == 'notifications/initialized'\n"
            "for request_id in range(2, 102):\n"
            "    prefix = str(request_id)\n"
            "    cursor = prefix + chr(0) * (4096 - len(prefix))\n"
            "    respond({'id': request_id}, {'tools': [], 'nextCursor': cursor})\n"
            "time.sleep(30)\n")
        # A separate caller provides a watchdog even if the implementation
        # regresses to a blocking stdin.write/flush outside its own deadline.
        caller = (
            "import importlib.util, json, pathlib, sys, time\n"
            f"spec = importlib.util.spec_from_file_location('setup_under_test', {str(ROOT / 'scripts/dev/setup.py')!r})\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
            "start = time.monotonic()\n"
            "try:\n"
            f"    module.mcp_tools({command!r}, pathlib.Path({str(self.project)!r}), {self.env!r}, timeout=0.5)\n"
            "except TimeoutError:\n"
            "    print(json.dumps({'timed_out': True, 'elapsed': time.monotonic() - start}))\n"
            "else:\n"
            "    raise AssertionError('backpressure must exhaust the shared deadline')\n")
        try:
            try:
                result = subprocess.run([sys.executable, "-c", caller], cwd=self.project,
                                        env=self.env, capture_output=True, text=True, timeout=7)
            except subprocess.TimeoutExpired:
                self.fail("MCP blocked writing a request beyond the external watchdog")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["timed_out"])
            self.assertLess(report["elapsed"], 4)
            self.assert_child_reaped(pidfile)
            self.assertNotIn('"method": "tools/call"', transcript.read_text())
        finally:
            # The MCP starts its own process group, so a watchdog failure must
            # explicitly clean up that group after subprocess.run reaps caller.
            if pidfile.exists():
                try:
                    os.killpg(int(pidfile.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_mcp_invalid_catalog_and_repeated_cursor_fail_closed(self):
        for result in ({"tools": "invalid"}, {"tools": [{"name": 42}]},
                       {"tools": [], "nextCursor": "repeat"}):
            with self.subTest(result=result):
                body = ("respond(receive(), {'capabilities':{'tools':{}}})\n"
                        "receive()\n"
                        f"result = {result!r}\n"
                        "while True: respond(receive(), result)\n")
                command, _, pidfile = self.fake_mcp(body)
                with self.assertRaises(ValueError):
                    setup.mcp_tools(command, self.project, self.env, timeout=3)
                self.assert_child_reaped(pidfile)


if __name__ == "__main__":
    unittest.main()
