#!/usr/bin/env python3
"""Adversarial tests for the Playwright debugger JSON publisher."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "skills/playwright-debugger/scripts/publish-json-report.py"
MINIMAL_VALID_REPORT = {
    "suites": [],
    "stats": {
        "expected": 0,
        "skipped": 0,
        "unexpected": 0,
        "flaky": 0,
    },
}
OLD_VALID_REPORT = {
    **MINIMAL_VALID_REPORT,
    "metadata": {"sentinel": "preserve-these-bytes"},
}


def load_helper_module():
    spec = importlib.util.spec_from_file_location(
        "publish_json_report_under_test",
        HELPER,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load publish-json-report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SafeReportPublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_helper(
        self,
        output: str,
        program: str,
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        pass_env: tuple[str, ...] = (),
        timeout_seconds: float | None = None,
        watchdog_seconds: float = 15,
    ) -> subprocess.CompletedProcess[str]:
        if timeout_seconds is None:
            command = [
                sys.executable,
                str(HELPER),
                *[
                    argument
                    for name in pass_env
                    for argument in ("--pass-env", name)
                ],
                output,
                "--",
                sys.executable,
                "-c",
                program,
            ]
        else:
            loader = "\n".join(
                [
                    "import importlib.util",
                    (
                        "spec = importlib.util.spec_from_file_location("
                        f"'publish_json_report', {str(HELPER)!r})"
                    ),
                    "module = importlib.util.module_from_spec(spec)",
                    "spec.loader.exec_module(module)",
                    f"module.MAX_COMMAND_SECONDS = {timeout_seconds!r}",
                    (
                        "raise SystemExit(module.main("
                        f"[{output!r}, '--', {sys.executable!r}, '-c', {program!r}]))"
                    ),
                ]
            )
            command = [sys.executable, "-c", loader]
        return subprocess.run(
            command,
            cwd=cwd or self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=watchdog_seconds,
        )

    def test_process_group_permission_probe_means_group_may_still_exist(self) -> None:
        module = load_helper_module()
        original_killpg = module.os.killpg
        try:
            module.os.killpg = lambda *_: (_ for _ in ()).throw(
                PermissionError("operation not permitted")
            )

            self.assertTrue(module.process_group_exists(12345))
        finally:
            module.os.killpg = original_killpg

    def test_final_sigkill_permission_error_accepts_proven_group_exit(self) -> None:
        module = load_helper_module()
        original_killpg = module.os.killpg
        original_grace = module.TERMINATION_GRACE_SECONDS
        signals: list[int] = []

        state = {"final_attempted": False}

        class Process:
            pid = 12345
            poll_calls = 0

            def poll(self) -> None:
                self.poll_calls += 1
                return None

        process = Process()

        def killpg(_process_group: int, signal_number: int) -> None:
            signals.append(signal_number)
            if signal_number == 0 and state["final_attempted"]:
                raise ProcessLookupError
            if signal_number == module.signal.SIGKILL:
                state["final_attempted"] = True
                raise PermissionError("operation not permitted")

        try:
            module.os.killpg = killpg
            module.TERMINATION_GRACE_SECONDS = 0

            cleanup_error = module.terminate_process_group(process)
        finally:
            module.os.killpg = original_killpg
            module.TERMINATION_GRACE_SECONDS = original_grace

        self.assertEqual(
            [item for item in signals if item != 0],
            [module.signal.SIGTERM, module.signal.SIGKILL],
        )
        self.assertIsNone(cleanup_error)
        self.assertGreaterEqual(process.poll_calls, 2)

    def test_initial_sigterm_permission_error_still_attempts_sigkill(self) -> None:
        module = load_helper_module()
        original_killpg = module.os.killpg
        original_grace = module.TERMINATION_GRACE_SECONDS
        signals: list[int] = []

        state = {"killed": False}

        class Process:
            pid = 12345
            poll_calls = 0

            def poll(self) -> None:
                self.poll_calls += 1
                return None

        process = Process()

        def killpg(_process_group: int, signal_number: int) -> None:
            signals.append(signal_number)
            if signal_number == 0 and state["killed"]:
                raise ProcessLookupError
            if signal_number == module.signal.SIGTERM:
                raise PermissionError("operation not permitted")
            if signal_number == module.signal.SIGKILL:
                state["killed"] = True

        try:
            module.os.killpg = killpg
            module.TERMINATION_GRACE_SECONDS = 0

            cleanup_error = module.terminate_process_group(process)
        finally:
            module.os.killpg = original_killpg
            module.TERMINATION_GRACE_SECONDS = original_grace

        self.assertEqual(
            [item for item in signals if item != 0],
            [module.signal.SIGTERM, module.signal.SIGKILL],
        )
        self.assertIsNone(cleanup_error)
        self.assertGreaterEqual(process.poll_calls, 2)

    def test_permission_denied_signals_report_a_live_process_group(self) -> None:
        module = load_helper_module()
        original_killpg = module.os.killpg
        original_grace = module.TERMINATION_GRACE_SECONDS

        class Process:
            pid = 12345
            args = ("fixture",)

            def poll(self) -> None:
                return None

            def wait(self, timeout: float | None = None) -> None:
                return None

        def killpg(_process_group: int, signal_number: int) -> None:
            if signal_number in (module.signal.SIGTERM, module.signal.SIGKILL):
                raise PermissionError("operation not permitted")

        try:
            module.os.killpg = killpg
            module.TERMINATION_GRACE_SECONDS = 0

            cleanup_error = module.cleanup_process_group(Process())
        finally:
            module.os.killpg = original_killpg
            module.TERMINATION_GRACE_SECONDS = original_grace

        self.assertIsNotNone(cleanup_error)
        self.assertIn("SIGTERM", cleanup_error)
        self.assertIn("SIGKILL", cleanup_error)
        self.assertIn("remained alive", cleanup_error)

    def test_termination_waits_for_a_ready_descendant_group_to_exit(self) -> None:
        module = load_helper_module()
        ready = self.root / "ready-descendant"
        program = "\n".join(
            [
                "import os, pathlib, signal, time",
                f"ready = pathlib.Path({str(ready)!r})",
                "if os.fork() == 0:",
                "    signal.signal(signal.SIGTERM, signal.SIG_IGN)",
                "    ready.write_text('yes')",
                "    time.sleep(10)",
                "    os._exit(0)",
                "while not ready.exists():",
                "    time.sleep(0.01)",
                "os._exit(0)",
            ]
        )
        process = subprocess.Popen(
            [sys.executable, "-c", program],
            start_new_session=True,
        )
        deadline = time.monotonic() + 2
        try:
            while not ready.exists():
                if time.monotonic() >= deadline:
                    self.fail("descendant readiness handshake timed out")
                time.sleep(0.01)
            process.wait(timeout=2)
            self.assertTrue(module.process_group_exists(process.pid))

            module.terminate_process_group(process)

            self.assertFalse(module.process_group_exists(process.pid))
        finally:
            try:
                os.killpg(process.pid, module.signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)

    def test_final_sigkill_permission_error_reports_a_live_group(self) -> None:
        module = load_helper_module()
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            start_new_session=True,
        )
        original_killpg = module.os.killpg
        original_grace = module.TERMINATION_GRACE_SECONDS

        def deny_only_final_kill(_process_group: int, signal_number: int) -> None:
            if signal_number == module.signal.SIGKILL:
                raise PermissionError("operation not permitted")

        try:
            module.os.killpg = deny_only_final_kill
            module.TERMINATION_GRACE_SECONDS = 0.05

            cleanup_error = module.cleanup_process_group(process)
            self.assertIsNotNone(cleanup_error)
            self.assertIn("remained alive", cleanup_error)
            self.assertIsNone(process.poll())
        finally:
            module.os.killpg = original_killpg
            module.TERMINATION_GRACE_SECONDS = original_grace
            try:
                original_killpg(process.pid, module.signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)

    def test_cleanup_timeout_does_not_mask_original_timeout_diagnostic(self) -> None:
        module = load_helper_module()
        report = self.root / "temporary.json"
        descriptor = os.open(report, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        original_cleanup = module.cleanup_process_group
        original_timeout = module.MAX_COMMAND_SECONDS
        cleanup_calls = 0
        try:
            module.MAX_COMMAND_SECONDS = 0

            def cleanup_timeout(process) -> None:
                nonlocal cleanup_calls
                cleanup_calls += 1
                try:
                    os.killpg(process.pid, module.signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
                raise subprocess.TimeoutExpired(process.args, 0)

            module.cleanup_process_group = cleanup_timeout
            with self.assertRaises(ValueError) as caught:
                module.capture_stdout(
                    descriptor,
                    [sys.executable, "-c", "import time; time.sleep(1)"],
                    {"PATH": os.defpath},
                )
        finally:
            module.cleanup_process_group = original_cleanup
            module.MAX_COMMAND_SECONDS = original_timeout
            os.close(descriptor)

        message = str(caught.exception)
        self.assertIn("command timed out after", message)
        self.assertIn("cleanup failed", message)
        self.assertEqual(message.count("cleanup failed"), 1)
        self.assertEqual(cleanup_calls, 1)

    def test_nonzero_leader_with_live_group_attempts_cleanup_once(self) -> None:
        module = load_helper_module()
        report = self.root / "temporary.json"
        descriptor = os.open(report, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        original_cleanup = module.cleanup_process_group
        cleanup_calls = 0
        try:
            def cleanup(process) -> str:
                nonlocal cleanup_calls
                cleanup_calls += 1
                try:
                    os.killpg(process.pid, module.signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return "process group remained alive after leader exit"

            module.cleanup_process_group = cleanup
            with self.assertRaises(ValueError) as caught:
                module.capture_stdout(
                    descriptor,
                    [
                        sys.executable,
                        "-c",
                        "import os, sys, time\n"
                        "if os.fork() == 0:\n"
                        "    os.close(1)\n"
                        "    time.sleep(5)\n"
                        "    sys.exit(0)\n"
                        "sys.exit(7)\n",
                    ],
                    {"PATH": os.defpath},
                )
        finally:
            module.cleanup_process_group = original_cleanup
            os.close(descriptor)

        self.assertIn("exit status 7", str(caught.exception))
        self.assertIn("cleanup failed", str(caught.exception))
        self.assertEqual(cleanup_calls, 1)

    def test_zero_leader_with_live_group_fails_closed(self) -> None:
        module = load_helper_module()
        report = self.root / "temporary.json"
        marker = self.root / "ready"
        descriptor = os.open(report, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        original_cleanup = module.cleanup_process_group
        cleanup_calls = 0
        try:
            def cleanup(process) -> str:
                nonlocal cleanup_calls
                cleanup_calls += 1
                try:
                    os.killpg(process.pid, module.signal.SIGKILL)
                except ProcessLookupError:
                    pass
                return "process group remained alive after leader exit"

            module.cleanup_process_group = cleanup
            with self.assertRaises(ValueError) as caught:
                module.capture_stdout(
                    descriptor,
                    [
                        sys.executable,
                        "-c",
                        "import os, sys, time\n"
                        "marker = sys.argv[1]\n"
                        "if os.fork() == 0:\n"
                        "    open(marker, 'w').close()\n"
                        "    os.close(1)\n"
                        "    time.sleep(5)\n"
                        "    sys.exit(0)\n"
                        "while not os.path.exists(marker):\n"
                        "    time.sleep(0.01)\n"
                        "print('{}')\n",
                        str(marker),
                    ],
                    {"PATH": os.defpath},
                )
        finally:
            module.cleanup_process_group = original_cleanup
            os.close(descriptor)

        message = str(caught.exception)
        self.assertIn("command left live descendants", message)
        self.assertEqual(message.count("cleanup failed"), 1)
        self.assertEqual(cleanup_calls, 1)

    def test_skill_routes_json_writes_through_publisher(self) -> None:
        skill = (ROOT / "skills/playwright-debugger/SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("> playwright-report/results.json", skill)
        self.assertGreaterEqual(skill.count("publish-json-report.py"), 3)
        self.assertIn("do not replace it with `mkdir` plus shell", skill)
        self.assertIn("--pass-env PATH", skill)
        self.assertIn("/usr/bin/env -i PATH=\"$PATH\"", skill)
        self.assertIn("name and current value of every variable", skill)

    def test_publishes_valid_json_and_replaces_regular_destination(self) -> None:
        destination = self.root / "playwright-report/results.json"
        destination.parent.mkdir()
        destination.write_text(json.dumps(OLD_VALID_REPORT), encoding="utf-8")

        result = self.run_helper(
            "playwright-report/results.json",
            f"import json; print(json.dumps({MINIMAL_VALID_REPORT!r}))",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(destination.read_text()), MINIMAL_VALID_REPORT)
        self.assertEqual(list(destination.parent.glob(".*.tmp")), [])

    def test_child_environment_is_minimal_and_pass_env_is_explicit(self) -> None:
        observed = self.root / "observed-environment.json"
        parent_environment = os.environ.copy()
        canaries = {
            "AWS_SECRET_ACCESS_KEY": "aws-canary",
            "NODE_OPTIONS": "--require=/definitely/not-loaded.js",
            "NPM_CONFIG_USERCONFIG": "/tmp/npm-canary",
            "BASH_ENV": "/tmp/bash-canary",
            "PYTHONPATH": "/tmp/python-canary",
            "E2E_APPROVED_CANARY": "approved-value",
        }
        parent_environment.update(canaries)
        program = (
            "import json, os, pathlib; "
            f"pathlib.Path({str(observed)!r}).write_text("
            "json.dumps(dict(os.environ)), encoding='utf-8'); "
            f"print(json.dumps({MINIMAL_VALID_REPORT!r}))"
        )

        result = self.run_helper(
            "playwright-report/results.json",
            program,
            env=parent_environment,
            pass_env=("E2E_APPROVED_CANARY",),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        child_environment = json.loads(observed.read_text(encoding="utf-8"))
        self.assertEqual(
            child_environment["E2E_APPROVED_CANARY"],
            "approved-value",
        )
        for name in canaries:
            if name != "E2E_APPROVED_CANARY":
                self.assertNotIn(name, child_environment)
        self.assertEqual(
            json.loads(
                (self.root / "playwright-report/results.json").read_text(
                    encoding="utf-8"
                )
            ),
            MINIMAL_VALID_REPORT,
        )

    def test_pass_env_rejects_invalid_duplicate_and_missing_names(self) -> None:
        invalid_commands = (
            ["--pass-env", "BAD-NAME"],
            ["--pass-env", "E2E_DUPLICATE", "--pass-env", "E2E_DUPLICATE"],
            ["--pass-env", "E2E_MISSING_ENV_FOR_PUBLISHER_TEST"],
        )
        environment = os.environ.copy()
        environment["E2E_DUPLICATE"] = "present"
        environment.pop("E2E_MISSING_ENV_FOR_PUBLISHER_TEST", None)

        for options in invalid_commands:
            with self.subTest(options=options):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(HELPER),
                        *options,
                        "playwright-report/results.json",
                        "--",
                        sys.executable,
                        "-c",
                        f"print({json.dumps(MINIMAL_VALID_REPORT)!r})",
                    ],
                    cwd=self.root,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "playwright-report/results.json").exists())

    def test_reader_invalid_reports_preserve_valid_destination(self) -> None:
        destination = self.root / "playwright-report/results.json"
        destination.parent.mkdir()
        original = json.dumps(OLD_VALID_REPORT, separators=(",", ":"))
        too_deep: dict[str, object] = {}
        cursor = too_deep
        for _ in range(101):
            child: dict[str, object] = {}
            cursor["child"] = child
            cursor = child
        invalid_documents = {
            "schema-invalid": {
                "suites": [],
                "stats": {
                    "expected": 0,
                    "skipped": 0,
                    "unexpected": 0,
                },
            },
            "contradictory-outcome": {
                "suites": [
                    {
                        "suites": [],
                        "specs": [
                            {
                                "ok": True,
                                "tests": [
                                    {
                                        "status": "expected",
                                        "results": [{"status": "failed"}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "stats": {
                    "expected": 1,
                    "skipped": 0,
                    "unexpected": 0,
                    "flaky": 0,
                },
            },
            "contradictory-stats": {
                "suites": [],
                "stats": {
                    "expected": 1,
                    "skipped": 0,
                    "unexpected": 0,
                    "flaky": 0,
                },
            },
            "depth-limit": {
                **MINIMAL_VALID_REPORT,
                "metadata": too_deep,
            },
        }

        for name, document in invalid_documents.items():
            with self.subTest(name=name):
                destination.write_text(original, encoding="utf-8")
                result = self.run_helper(
                    "playwright-report/results.json",
                    f"import json; print(json.dumps({document!r}))",
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(destination.read_text(encoding="utf-8"), original)
                self.assertEqual(list(destination.parent.glob(".*.tmp")), [])

        destination.write_text(original, encoding="utf-8")
        node_limit_result = self.run_helper(
            "playwright-report/results.json",
            (
                f"import json; report = {MINIMAL_VALID_REPORT!r}; "
                "report['metadata'] = [None] * 200_000; "
                "print(json.dumps(report))"
            ),
        )
        self.assertNotEqual(node_limit_result.returncode, 0)
        self.assertIn("node limit", node_limit_result.stderr)
        self.assertEqual(destination.read_text(encoding="utf-8"), original)
        self.assertEqual(list(destination.parent.glob(".*.tmp")), [])

    def test_invalid_json_preserves_existing_destination(self) -> None:
        destination = self.root / "playwright-report/results.json"
        destination.parent.mkdir()
        destination.write_text('{"old": true}', encoding="utf-8")

        result = self.run_helper(
            "playwright-report/results.json", 'print("not json")'
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(destination.read_text(), '{"old": true}')
        self.assertEqual(list(destination.parent.glob(".*.tmp")), [])

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(self) -> None:
        destination = self.root / "playwright-report/results.json"
        destination.parent.mkdir()

        invalid_documents = {
            "duplicate": '{"value": 1, "value": 2}',
            "nan": '{"value": NaN}',
            "infinity": '{"value": Infinity}',
            "negative-infinity": '{"value": -Infinity}',
            "overflow-float": '{"value": 1e400}',
        }
        for name, document in invalid_documents.items():
            with self.subTest(name=name):
                destination.write_text('{"old": true}', encoding="utf-8")
                result = self.run_helper(
                    "playwright-report/results.json",
                    f"import sys; sys.stdout.write({document!r})",
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("json", result.stderr.lower())
                self.assertEqual(destination.read_text(), '{"old": true}')
                self.assertEqual(list(destination.parent.glob(".*.tmp")), [])

    def test_stdout_overflow_terminates_child_and_preserves_destination(self) -> None:
        destination = self.root / "playwright-report/results.json"
        destination.parent.mkdir()
        destination.write_text('{"old": true}', encoding="utf-8")
        child_pid = self.root / "child-pid"
        completed = self.root / "completed"
        program = "\n".join(
            [
                "import os, pathlib, sys, time",
                f"child_pid = pathlib.Path({str(child_pid)!r})",
                f"completed = pathlib.Path({str(completed)!r})",
                "child_pid.write_text(str(os.getpid()))",
                "sys.stdout.buffer.write(b'x' * (8 * 1024 * 1024 + 1))",
                "sys.stdout.buffer.flush()",
                "time.sleep(10)",
                "completed.write_text('yes')",
            ]
        )

        result = self.run_helper("playwright-report/results.json", program)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("8388608-byte", result.stderr)
        self.assertTrue(child_pid.exists())
        with self.assertRaises(ProcessLookupError):
            os.kill(int(child_pid.read_text(encoding="utf-8")), 0)
        self.assertFalse(completed.exists())
        self.assertEqual(destination.read_text(), '{"old": true}')
        self.assertEqual(list(destination.parent.glob(".*.tmp")), [])

    def test_silent_reporter_times_out_and_preserves_destination(self) -> None:
        destination = self.root / "playwright-report/results.json"
        destination.parent.mkdir()
        destination.write_text('{"old": true}', encoding="utf-8")
        completed = self.root / "silent-completed"
        program = "\n".join(
            [
                "import pathlib, time",
                f"completed = pathlib.Path({str(completed)!r})",
                "time.sleep(10)",
                "completed.write_text('yes')",
            ]
        )

        result = self.run_helper(
            "playwright-report/results.json",
            program,
            timeout_seconds=0.25,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr.lower())
        self.assertFalse(completed.exists())
        self.assertEqual(destination.read_text(), '{"old": true}')
        self.assertEqual(list(destination.parent.glob(".*.tmp")), [])

    def test_timeout_kills_forked_descendant_holding_stdout_open(self) -> None:
        destination = self.root / "playwright-report/results.json"
        destination.parent.mkdir()
        destination.write_text('{"old": true}', encoding="utf-8")
        ready = self.root / "descendant-ready"
        completed = self.root / "descendant-completed"
        program = "\n".join(
            [
                "import os, pathlib, signal, time",
                f"ready = pathlib.Path({str(ready)!r})",
                f"completed = pathlib.Path({str(completed)!r})",
                "if os.fork() == 0:",
                "    signal.signal(signal.SIGTERM, signal.SIG_IGN)",
                "    ready.write_text('yes')",
                "    time.sleep(10)",
                "    completed.write_text('yes')",
                "    os._exit(0)",
                "while not ready.exists():",
                "    time.sleep(0.01)",
                "print('{}', flush=True)",
                "os._exit(0)",
            ]
        )

        result = self.run_helper(
            "playwright-report/results.json",
            program,
            timeout_seconds=0.25,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr.lower())
        self.assertFalse(completed.exists())
        self.assertEqual(destination.read_text(), '{"old": true}')
        self.assertEqual(list(destination.parent.glob(".*.tmp")), [])

    def test_command_failure_preserves_existing_destination(self) -> None:
        destination = self.root / "playwright-report/results.json"
        destination.parent.mkdir()
        destination.write_text('{"old": true}', encoding="utf-8")

        result = self.run_helper(
            "playwright-report/results.json",
            'print("{}"); raise SystemExit(23)',
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(destination.read_text(), '{"old": true}')

    def test_rejects_symlinked_report_root_without_running_command(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "playwright-report").symlink_to(outside, target_is_directory=True)
        marker = self.root / "command-ran"

        result = self.run_helper(
            "playwright-report/results.json",
            f'from pathlib import Path; Path({str(marker)!r}).write_text("yes"); print("{{}}")',
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertFalse((outside / "results.json").exists())

    def test_rejects_symlink_destination_without_running_command(self) -> None:
        outside = self.root / "outside.json"
        outside.write_text('{"outside": true}', encoding="utf-8")
        report = self.root / "playwright-report"
        report.mkdir()
        (report / "results.json").symlink_to(outside)
        marker = self.root / "command-ran"

        result = self.run_helper(
            "playwright-report/results.json",
            f'from pathlib import Path; Path({str(marker)!r}).write_text("yes"); print("{{}}")',
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertTrue((report / "results.json").is_symlink())
        self.assertEqual(outside.read_text(), '{"outside": true}')

    def test_rejects_traversal_and_absolute_paths(self) -> None:
        marker = self.root / "command-ran"
        program = (
            f'from pathlib import Path; Path({str(marker)!r}).write_text("yes"); '
            'print("{}")'
        )

        traversal = self.run_helper("../outside.json", program)
        absolute = self.run_helper(str(self.root / "outside.json"), program)

        self.assertNotEqual(traversal.returncode, 0)
        self.assertNotEqual(absolute.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertFalse((self.root.parent / "outside.json").exists())

    def test_directory_descriptor_pins_parent_during_path_swap(self) -> None:
        report = self.root / "playwright-report"
        report.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        release = self.root / "release"
        command = [
            sys.executable,
            str(HELPER),
            "playwright-report/results.json",
            "--",
            sys.executable,
            "-c",
            (
                "import json, pathlib, time; "
                f"release=pathlib.Path({str(release)!r}); "
                "time.sleep(0.5); "
                f"print(json.dumps({MINIMAL_VALID_REPORT!r}))"
            ),
        ]
        process = subprocess.Popen(
            command,
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(100):
            if list(report.glob(".*.tmp")):
                break
            import time

            time.sleep(0.01)
        moved = self.root / "moved-report"
        report.rename(moved)
        report.symlink_to(outside, target_is_directory=True)
        stdout, stderr = process.communicate(timeout=5)

        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(
            json.loads((moved / "results.json").read_text()),
            MINIMAL_VALID_REPORT,
        )
        self.assertFalse((outside / "results.json").exists())


if __name__ == "__main__":
    unittest.main()
