#!/usr/bin/env python3
"""Adversarial tests for the Cypress Mochawesome report publisher."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
# Resolve the temp root so mkdtemp never returns a symlinked path.
# macOS /tmp is a symlink to /private/tmp and the bundled launchers reject
# symlinked roots; hardcoding /private/tmp broke every non-macOS runner.
tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())


ROOT = Path(__file__).resolve().parents[2]
HELPER = (
    ROOT
    / "skills/cypress-debugger/scripts/publish-mochawesome-report.py"
)
VALID_REPORT = {
    "stats": {
        "suites": 0,
        "tests": 0,
        "passes": 0,
        "pending": 0,
        "failures": 0,
        "skipped": 0,
        "duration": 0,
    },
    "results": [],
}


def load_helper_module():
    spec = importlib.util.spec_from_file_location(
        "publish_mochawesome_report_under_test",
        HELPER,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load publish-mochawesome-report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MochawesomePublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="e2e-cypress-publisher-",
        )
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_helper(
        self,
        program: str,
        *,
        output: str = "cypress/reports/merged.json",
        helper: Path = HELPER,
        env: dict[str, str] | None = None,
        pass_env: tuple[str, ...] = (),
        watchdog_seconds: float = 15,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(helper),
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
            ],
            cwd=self.root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=watchdog_seconds,
        )

    def assert_no_temporary(self) -> None:
        reports = self.root / "cypress/reports"
        if reports.is_dir():
            self.assertEqual(list(reports.glob(".merged.json.*.tmp")), [])

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

    def test_run_helper_has_an_outer_watchdog(self) -> None:
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_helper(
                "import time; time.sleep(10)",
                watchdog_seconds=0.01,
            )

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

    def test_valid_schema_atomically_replaces_regular_destination(self) -> None:
        destination = self.root / "cypress/reports/merged.json"
        destination.parent.mkdir(parents=True)
        destination.write_text('{"old":true}', encoding="utf-8")

        result = self.run_helper(
            f"import sys; sys.stdout.write({json.dumps(VALID_REPORT)!r})"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(destination.read_text()), VALID_REPORT)
        self.assert_no_temporary()

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
            f"print(json.dumps({VALID_REPORT!r}))"
        )

        result = self.run_helper(
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
                (self.root / "cypress/reports/merged.json").read_text(
                    encoding="utf-8"
                )
            ),
            VALID_REPORT,
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
                        "cypress/reports/merged.json",
                        "--",
                        sys.executable,
                        "-c",
                        f"print({json.dumps(VALID_REPORT)!r})",
                    ],
                    cwd=self.root,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "cypress/reports/merged.json").exists())

    def test_invalid_mochawesome_schema_preserves_prior_report(self) -> None:
        destination = self.root / "cypress/reports/merged.json"
        destination.parent.mkdir(parents=True)
        destination.write_text('{"old":true}', encoding="utf-8")

        result = self.run_helper("print('{}')")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mochawesome schema", result.stderr.lower())
        self.assertEqual(destination.read_text(), '{"old":true}')
        self.assert_no_temporary()

    def test_merger_cannot_replace_validator_before_validation(self) -> None:
        trusted_scripts = self.root / "trusted-scripts"
        trusted_scripts.mkdir()
        helper = trusted_scripts / HELPER.name
        reader = trusted_scripts / "read-cypress-artifact.py"
        shutil.copy2(HELPER, helper)
        shutil.copy2(HELPER.with_name(reader.name), reader)
        shutil.copy2(
            HELPER.with_name("redact_artifact.py"),
            trusted_scripts / "redact_artifact.py",
        )
        shutil.copy2(
            HELPER.with_name("residual_credentials.py"),
            trusted_scripts / "residual_credentials.py",
        )
        destination = self.root / "cypress/reports/merged.json"
        destination.parent.mkdir(parents=True)
        destination.write_text('{"old":true}', encoding="utf-8")

        replacement = (
            "def load_json(raw):\n"
            "    return {}\n\n"
            "def mochawesome_output(report):\n"
            "    return report\n"
        )
        result = self.run_helper(
            (
                "from pathlib import Path; "
                f"Path({str(reader)!r}).write_text({replacement!r}); "
                "print('{}')"
            ),
            helper=helper,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mochawesome schema", result.stderr.lower())
        self.assertEqual(destination.read_text(), '{"old":true}')
        self.assert_no_temporary()

    def test_nonzero_merger_preserves_prior_report(self) -> None:
        destination = self.root / "cypress/reports/merged.json"
        destination.parent.mkdir(parents=True)
        destination.write_text('{"old":true}', encoding="utf-8")

        result = self.run_helper(
            f"print({json.dumps(VALID_REPORT)!r}); raise SystemExit(23)"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(destination.read_text(), '{"old":true}')
        self.assert_no_temporary()

    def test_rejects_symlinked_report_root_before_running_merger(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "cypress").mkdir()
        (self.root / "cypress/reports").symlink_to(
            outside,
            target_is_directory=True,
        )
        marker = self.root / "merger-ran"

        result = self.run_helper(
            (
                "from pathlib import Path; "
                f"Path({str(marker)!r}).write_text('yes'); "
                f"print({json.dumps(VALID_REPORT)!r})"
            )
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertFalse((outside / "merged.json").exists())

    def test_rejects_symlink_destination_before_running_merger(self) -> None:
        outside = self.root / "outside.json"
        outside.write_text('{"outside":true}', encoding="utf-8")
        reports = self.root / "cypress/reports"
        reports.mkdir(parents=True)
        (reports / "merged.json").symlink_to(outside)
        marker = self.root / "merger-ran"

        result = self.run_helper(
            (
                "from pathlib import Path; "
                f"Path({str(marker)!r}).write_text('yes'); "
                f"print({json.dumps(VALID_REPORT)!r})"
            )
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertTrue((reports / "merged.json").is_symlink())
        self.assertEqual(outside.read_text(), '{"outside":true}')

    def test_stdout_limit_preserves_prior_report(self) -> None:
        destination = self.root / "cypress/reports/merged.json"
        destination.parent.mkdir(parents=True)
        destination.write_text('{"old":true}', encoding="utf-8")

        result = self.run_helper(
            "import sys; sys.stdout.buffer.write(b'x' * (8 * 1024 * 1024 + 1))"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("8388608-byte", result.stderr)
        self.assertEqual(destination.read_text(), '{"old":true}')
        self.assert_no_temporary()

    def test_skill_never_uses_raw_merge_redirection(self) -> None:
        skill = (ROOT / "skills/cypress-debugger/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("> cypress/reports/merged.json", skill)
        self.assertIn("publish-mochawesome-report.py", skill)
        self.assertIn("--pass-env PATH", skill)
        self.assertIn("/usr/bin/env -i PATH=\"$PATH\"", skill)
        self.assertIn("name and current value of every variable", skill)


if __name__ == "__main__":
    unittest.main()
