#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the scanner's scope worker ownership and fail-closed integration."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT / "skills/e2e-reviewer/scripts/scan.sh"
PYTHON = str(Path(sys.executable).resolve())


def resolve_rg() -> str:
    configured = os.environ.get("E2E_SMELL_RG_BIN")
    candidates = [configured] if configured else [
        "/opt/homebrew/bin/rg", "/usr/local/bin/rg", "/usr/bin/rg", "/bin/rg",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.is_absolute() and path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise RuntimeError("Set E2E_SMELL_RG_BIN to an absolute executable ripgrep path")


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class ScannerWorkerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="scanner-worker-integration-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.project = self.directory / "project"
        self.scan_root = self.project
        (self.project / "support").mkdir(parents=True)
        (self.project / "tests").mkdir()
        (self.project / "package.json").write_text(
            json.dumps({"devDependencies": {"@playwright/test": "1.55.0"}}),
            encoding="utf-8",
        )
        (self.project / "support/base.ts").write_text(
            "import { test, expect } from '@playwright/test';\n"
            "export { test, expect };\n",
            encoding="utf-8",
        )
        (self.project / "support/index.ts").write_text(
            "export { test, expect } from './base';\n", encoding="utf-8",
        )
        (self.project / "tests/example.spec.ts").write_text(
            "import { test, expect } from '../support';\n"
            "test.only('assertion', async ({ page }) => {\n"
            "  await expect(page.getByText('Hello')).toBeVisible();\n"
            "});\n",
            encoding="utf-8",
        )
        self.worker_pids = self.directory / "worker-pids"
        self.helper_pids = self.directory / "helper-pids"
        self.crashed_client = self.directory / "crashed-client"
        self.environment = {
            **os.environ,
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LC_ALL": "C",
            "LC_CTYPE": "C",
            "LANG": "C",
            "E2E_SMELL_RG_BIN": resolve_rg(),
            "E2E_SMELL_DISABLE_AST_GREP": "1",
            "E2E_SMELL_NO_AST_GREP_DOWNLOAD": "1",
            "E2E_SMELL_NO_ESLINT_DOWNLOAD": "1",
        }

    def interpreter(self, *, crash_query: bool = False, mutation: str = "", mutation_op: str = "validate") -> Path:
        helper = self.directory / "helper-wrapper.sh"
        helper.write_text(
            "#!/bin/sh\n"
            + 'printf "%s\\n" "$$" >> ' + shlex.quote(str(self.helper_pids)) + "\n"
            + "exec /bin/bash -p "
            + shlex.quote(str(SCANNER.parent / "scope-source.sh")) + ' "$@"\n',
            encoding="utf-8",
        )
        wrapper = self.directory / "python-wrapper"
        # All ordinary Python operations exec the real interpreter. Only the
        # worker's helper path is instrumented, and the failure case kills a
        # real query client before it can contact the worker.
        wrapper.write_text(
            f"#!{PYTHON}\n"
            "import os, signal, sys\n"
            "from pathlib import Path\n"
            "args = sys.argv[1:]\n"
            "if 'serve' in args:\n"
            f"    with Path({str(self.worker_pids)!r}).open('a') as stream:\n"
            "        stream.write(str(os.getpid()) + '\\n')\n"
            "    args[args.index('--helper') + 1] = " + repr(str(helper)) + "\n"
            + (
                "if 'client' in args and '--op' in args and args[args.index('--op') + 1] == 'query':\n"
                f"    Path({str(self.crashed_client)!r}).write_text(str(os.getpid()))\n"
                "    os.kill(os.getpid(), signal.SIGKILL)\n"
                if crash_query else ""
            )
            + (
                # Fire once, on the first matching client call (the second for
                # a query, so the first query has cached the dependency).
                "if ('client' in args and '--op' in args and args[args.index('--op') + 1] == "
                + repr(mutation_op)
                + f" and not Path({str(self.directory / 'mutation-applied')!r}).exists()):\n"
                + f"    with Path({str(self.directory / 'op-count')!r}).open('a') as counter:\n"
                + "        counter.write('x')\n"
                + f"    if len(Path({str(self.directory / 'op-count')!r}).read_text()) >= "
                + ("2" if mutation_op == "query" else "1") + ":\n"
                + "        " + mutation + "\n"
                + f"        Path({str(self.directory / 'mutation-applied')!r}).touch()\n"
                if mutation else ""
            )
            + f"os.execv({PYTHON!r}, [{PYTHON!r}, *args])\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        return wrapper

    def pids(self, path: Path) -> list[int]:
        return [int(line) for line in path.read_text().splitlines()] if path.exists() else []

    def start(self, *, crash_query: bool = False, mutation: str = "", mutation_op: str = "validate") -> subprocess.Popen[str]:
        # Each scan gets its own one-shot mutation, even when a test starts several.
        for marker in ("mutation-applied", "op-count"):
            (self.directory / marker).unlink(missing_ok=True)
        environment = {
            **self.environment,
            "E2E_SMELL_PYTHON_BIN": str(self.interpreter(crash_query=crash_query, mutation=mutation, mutation_op=mutation_op)),
        }
        process = subprocess.Popen(
            ["/bin/bash", "-p", str(SCANNER), str(self.scan_root)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self.addCleanup(self.cleanup_processes, process)
        return process

    def cleanup_processes(self, process: subprocess.Popen[str]) -> None:
        # Signal only this test's process group and its explicitly recorded
        # lexical-helper group, including when an assertion or timeout fails.
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                # A child can exit between poll() and killpg() on macOS. Only
                # suppress that race; a live group that cannot be signalled is
                # a real cleanup failure and must remain visible to CI.
                if process.poll() is None:
                    raise
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            for pid in self.pids(self.helper_pids):
                if process_exists(pid):
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            process.communicate(timeout=5)

    def test_cleanup_of_completed_process_does_not_signal_its_group(self) -> None:
        process = subprocess.Popen(
            ["/usr/bin/true"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        process.wait(timeout=5)
        with mock.patch.object(
            os,
            "killpg",
            side_effect=AssertionError("completed process group was signalled"),
        ):
            self.cleanup_processes(process)

    def assert_reaped(self, path: Path, *, expected_count: int | None = None) -> None:
        pids = self.pids(path)
        self.assertTrue(pids, f"No process was recorded in {path.name}")
        if expected_count is not None:
            self.assertEqual(len(pids), expected_count, pids)
        deadline = time.monotonic() + 5
        while any(process_exists(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual([pid for pid in pids if process_exists(pid)], [], path.name)

    def test_barrel_scope_starts_one_worker_and_reaps_it(self) -> None:
        process = self.start()
        stdout, stderr = process.communicate(timeout=60)
        self.assertEqual(process.returncode, 1, stdout + stderr)
        self.assertRegex(stdout, r"(?m)^Summary:")
        self.assertIn("[P0] #7 Focused test committed", stdout)
        self.assertIn("example.spec.ts:2:", stdout)
        self.assertNotIn("INCOMPLETE", stdout + stderr)
        self.assert_reaped(self.worker_pids, expected_count=1)
        self.assert_reaped(self.helper_pids, expected_count=1)

    def test_strict_scope_watch_preserves_stable_findings(self) -> None:
        outputs = []
        for mode in ('off', 'strict'):
            self.environment['E2E_SMELL_SCOPE_WATCH'] = mode
            process = self.start()
            stdout, stderr = process.communicate(timeout=60)
            self.assertEqual(process.returncode, 1, stdout + stderr)
            outputs.append((stdout, stderr))
        self.assertEqual(outputs[0], outputs[1])

    def test_invalid_scope_watch_mode_fails_before_scan(self) -> None:
        self.environment['E2E_SMELL_SCOPE_WATCH'] = 'unsafe'
        process = self.start()
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 2, stdout + stderr)
        self.assertNotIn('Summary:', stdout)
        self.assertIn('E2E_SMELL_SCOPE_WATCH', stderr)

    def test_query_client_crash_fails_closed_and_reaps_worker(self) -> None:
        process = self.start(crash_query=True)
        stdout, stderr = process.communicate(timeout=60)
        self.assertTrue(self.crashed_client.exists(), "No actual query client was interrupted")
        self.assertEqual(process.returncode, 2, stdout + stderr)
        self.assertNotRegex(stdout, r"(?m)^Summary:")
        self.assertIn("scope", stderr.lower())
        self.assert_reaped(self.worker_pids, expected_count=1)

    def assert_terminal_mutation_rejected(self, mutation: str, mutation_op: str = "validate") -> None:
        process = self.start(mutation=mutation, mutation_op=mutation_op)
        stdout, stderr = process.communicate(timeout=90)
        self.assertTrue((self.directory / "mutation-applied").exists(), stdout + stderr)
        self.assertEqual(process.returncode, 2, stdout + stderr)
        self.assertNotRegex(stdout, r"(?m)^Summary:")
        self.assertIn("scope", stderr.lower())
        self.assert_reaped(self.worker_pids, expected_count=1)

    def test_cached_positive_barrel_mutation_before_summary_fails_closed(self) -> None:
        barrel = self.project / "support/base.ts"
        self.assert_terminal_mutation_rejected(
            f"Path({str(barrel)!r}).write_text('export const test = null;\\n')"
        )

    def test_cached_missing_resolution_created_before_summary_fails_closed(self) -> None:
        (self.project / "tests/unresolved.spec.ts").write_text(
            "import { test } from '../missing';\n"
            + "test.only('unresolved', () => {});\n", encoding="utf-8",
        )
        missing = self.project / "missing.ts"
        self.assert_terminal_mutation_rejected(
            f"Path({str(missing)!r}).write_text(\"export {{ test }} from '@playwright/test';\\n\")"
        )

    def test_cached_barrel_mutation_mid_scan_fails_closed(self) -> None:
        barrel = self.project / "support/base.ts"
        self.assert_terminal_mutation_rejected(
            f"Path({str(barrel)!r}).write_text('export const test = null;\\n')",
            mutation_op="query",
        )

    def test_cached_missing_resolution_created_mid_scan_fails_closed(self) -> None:
        (self.project / "tests/unresolved.spec.ts").write_text(
            "import { test } from '../missing';\n"
            + "test.only('unresolved', () => {});\n", encoding="utf-8",
        )
        missing = self.project / "missing.ts"
        self.assert_terminal_mutation_rejected(
            f"Path({str(missing)!r}).write_text(\"export {{ test }} from '@playwright/test';\\n\")",
            mutation_op="query",
        )

    def test_cached_symlink_parent_retargeted_before_summary_fails_closed(self) -> None:
        # The initial tree preflight rejects symlinks inside the requested
        # root. This dependency lives outside that root, inside the project.
        self.scan_root = self.project / "tests"
        support = self.project / "support"
        for name in ("first", "second"):
            directory = support / name
            directory.mkdir()
            (directory / "base.ts").write_text(
                "export { test, expect } from '@playwright/test';\n", encoding="utf-8",
            )
        link = support / "alias"
        link.symlink_to("first", target_is_directory=True)
        (support / "index.ts").write_text(
            "export { test, expect } from './alias/base';\n", encoding="utf-8",
        )
        self.assert_terminal_mutation_rejected(
            f"Path({str(link)!r}).unlink(); Path({str(link)!r}).symlink_to('second', target_is_directory=True)"
        )

    def test_scanner_termination_reaps_started_worker_and_helper(self) -> None:
        process = self.start()
        deadline = time.monotonic() + 30
        while not self.pids(self.helper_pids) and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(self.pids(self.helper_pids), "Lexical helper never started")
        self.assertIsNone(process.poll(), "Scanner exited before the termination control")
        process.terminate()
        stdout, stderr = process.communicate(timeout=15)
        self.assertNotEqual(process.returncode, 0, stdout + stderr)
        self.assertNotRegex(stdout, r"(?m)^Summary:")
        self.assert_reaped(self.worker_pids, expected_count=1)
        self.assert_reaped(self.helper_pids, expected_count=1)


class StrictScannerWorkerIntegrationTests(ScannerWorkerIntegrationTests):
    """Exercise the same mutation and ownership contracts with strict watches."""

    def setUp(self) -> None:
        super().setUp()
        self.environment['E2E_SMELL_SCOPE_WATCH'] = 'strict'

    @unittest.skipUnless(sys.platform == 'darwin', 'local APFS event backend')
    def test_transient_sibling_change_rejects_only_in_strict_mode(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location('scope_watch', SCANNER.with_name('scope-watch.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            probe = module.filesystem_probe()
        except (OSError, AttributeError):
            self.skipTest('APFS probe unavailable')
        fd = os.open(self.project, os.O_RDONLY)
        try:
            if not probe(fd):
                self.skipTest('local APFS required')
        finally:
            os.close(fd)
        source = self.project / 'tests/example.spec.ts'
        source.write_text("import { unused } from './missing-optional';\n" + source.read_text())
        sibling = self.project / 'tests/transient.bin'
        mutation = f"Path({str(sibling)!r}).touch(); Path({str(sibling)!r}).unlink()"
        for mode, expected in (('off', 1), ('strict', 2)):
            self.environment['E2E_SMELL_SCOPE_WATCH'] = mode
            process = self.start(mutation=mutation)
            stdout, stderr = process.communicate(timeout=90)
            self.assertEqual(process.returncode, expected, stdout + stderr)
            if mode == 'strict':
                self.assertNotRegex(stdout, r'(?m)^Summary:')
                self.assertIn('scope watch failure', stderr)
            else:
                self.assertRegex(stdout, r'(?m)^Summary:')


if __name__ == "__main__":
    unittest.main()
