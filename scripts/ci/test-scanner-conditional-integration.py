#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check conditional discovery at the actual scanner/worker boundary."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

spec = importlib.util.spec_from_file_location(
    "worker_test_support", Path(__file__).with_name("test-scanner-worker-integration.py")
)
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


class ConditionalIntegrationTests(unittest.TestCase):
    setUp = support.ScannerWorkerIntegrationTests.setUp
    cleanup_processes = support.ScannerWorkerIntegrationTests.cleanup_processes
    pids = support.ScannerWorkerIntegrationTests.pids

    def run_scanner(self, mode: str) -> tuple[int, str, str]:
        ordinary = self.project / "ordinary.ts"
        ordinary.write_text("if (ready) { work(); }\n")
        fixture = self.project / "tests/conditional.spec.ts"
        fixture.write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('conditional', async ({ page }) => {\n"
            "  if (await page.isVisible('button')) {\n"
            "    expect(true).toBe(true);\n"
            "  }\n"
            "});\n"
        )
        # This earlier #7 candidate records a missing graph dependency. The
        # negative #5a file must still validate that witness at its boundary.
        (self.project / "tests/unresolved.spec.ts").write_text(
            "import { test } from '../missing';\n"
            "test.only('unresolved', () => {});\n"
        )
        marker = self.directory / (mode + "-guard-ran")
        mutated = self.directory / (mode + "-mutated")
        wrapper = self.directory / (mode + "-python")
        wrapper.write_text(
            f"#!{support.PYTHON}\n"
            "import os, subprocess, sys\nfrom pathlib import Path\n"
            "args = sys.argv[1:]\n"
            f"mode = {mode!r}\nmarker = Path({str(marker)!r})\n"
            "if any(a.endswith('/conditional-discovery.py') for a in args):\n"
            "    marker.touch()\n"
            "    if mode == 'helper-error': raise SystemExit(2)\n"
            f"    rc = subprocess.call([{support.PYTHON!r}, *args])\n"
            "    if rc: raise SystemExit(rc)\n"
            "    if mode == 'reference':\n"
            "        output = Path(args[args.index('--output') + 1])\n"
            "        flags = output.read_bytes()\n"
            "        output.write_bytes(flags.replace(b'0\\0', b'1\\0'))\n"
            "    if mode == 'source-mutation':\n"
            f"        Path({str(ordinary)!r}).write_text('if (ready) expect(true);\\n')\n"
            f"        Path({str(mutated)!r}).touch()\n"
            "    raise SystemExit(0)\n"
            "if mode == 'witness-mutation' and marker.exists() and 'client' in args and '--op' in args and args[args.index('--op') + 1] == 'ping':\n"
            f"    Path({str(self.project / 'missing.ts')!r}).write_text(\"export {{ test }} from '@playwright/test';\\n\")\n"
            f"    Path({str(mutated)!r}).touch()\n"
            f"os.execv({support.PYTHON!r}, [{support.PYTHON!r}, *args])\n"
        )
        wrapper.chmod(0o700)
        process = subprocess.Popen(
            ["/bin/bash", "-p", str(support.SCANNER), str(self.project)],
            env={**self.environment, "E2E_SMELL_PYTHON_BIN": str(wrapper)},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,
        )
        self.addCleanup(self.cleanup_processes, process)
        stdout, stderr = process.communicate(timeout=120)
        self.assertTrue(marker.exists(), stdout + stderr)
        if mode.endswith("mutation"):
            self.assertTrue(mutated.exists(), stdout + stderr)
        return process.returncode, stdout, stderr

    def test_findings_summary_and_exit_match_unpruned_reference(self) -> None:
        before = self.run_scanner("reference")
        after = self.run_scanner("optimized")
        self.assertEqual(before[0], 1, before[1] + before[2])
        self.assertEqual(after[0], before[0], after[1] + after[2])
        # The number of examined OUT files may shrink: impossible candidates
        # are not falsely relabeled as out-of-scope. Findings/order stay exact.
        def normalize(text: str) -> str:
            return re.sub(r"(?m)^Scope filter: .*\n", "", text)
        self.assertEqual(normalize(before[1]), normalize(after[1]))
        self.assertRegex(after[1], r"(?m)^Summary:")
        self.assertIn("#5a Conditional branch contains assertion", after[1])
        self.assertNotIn("INCOMPLETE", after[1] + after[2])

    def test_repeated_ping_flushes_match_per_file_reference(self) -> None:
        for i in range(130):
            (self.project / f'a{i:03}.ts').write_text('if (ready) work();\n')
        for i in range(2):
            (self.project / f'z{i}.ts').write_text('if (ready) work();\n')
        (self.project / 'tests/conditional.spec.ts').write_text(
            "import { test, expect } from '@playwright/test';\n"
            "test('x', () => {\nif (ready) { expect(true).toBe(true); }\n});\n")
        copied = self.directory / 'scanner'
        shutil.copytree(support.SCANNER.parent, copied)
        worker = copied / 'scope-worker.py'
        log = self.directory / 'repeat-log'
        text = worker.read_text().replace(
            "        if args.repeat is not None and",
            f"        with open({str(log)!r}, 'a') as recorded: recorded.write(str(args.repeat) + '\\n')\n"
            "        if args.repeat is not None and")
        worker.write_text(text)
        def run(explicit):
            env = dict(self.environment)
            env.pop('E2E_SMELL_PYTHON_BIN', None)
            if explicit: env['E2E_SMELL_PYTHON_BIN'] = support.PYTHON
            result = subprocess.run(['/bin/bash', '-p', str(copied / 'scan.sh'), str(self.project)],
                                    env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r'(?m)^Summary:')
            return result
        before = run(True)
        self.assertNotIn('64', log.read_text().splitlines())
        log.write_text('')
        after = run(False)
        self.assertEqual(after.stdout, before.stdout)
        self.assertEqual([int(n) for n in log.read_text().splitlines() if n != 'None'], [64, 64, 2, 2])
        worker.write_text(worker.read_text().replace(
            '        if args.repeat is not None and',
            "        if args.repeat is not None: raise WorkerError('injected repeated ping failure')\n"
            '        if args.repeat is not None and'))
        env = dict(self.environment)
        env.pop('E2E_SMELL_PYTHON_BIN', None)
        failed = subprocess.run(['/bin/bash', '-p', str(copied / 'scan.sh'), str(self.project)],
                                env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(failed.returncode, 2, failed.stdout + failed.stderr)
        self.assertNotRegex(failed.stdout, r'(?m)^Summary:')
        self.assertIn('injected repeated ping failure', failed.stderr)

    def test_repeated_ping_failure_stops_loop_before_summary(self) -> None:
        source = support.SCANNER.read_text()
        start = source.index('  local _conditional_pending=0')
        stop = source.index('  capture_bounded_command', start)
        paths = self.directory / 'negative-paths'
        flags_file = self.directory / 'negative-flags'
        paths.write_bytes(b'ordinary.ts\0' * 65)
        flags_file.write_bytes(b'0\0' * 65)
        script = (
            "set -uo pipefail\nrun() {\n"
            "flags=',conditional-assertion,'\n"
            "E2E_SMELL_PYTHON_BIN=''\n"
            + '_matched_paths=' + repr(str(paths)) + '\n'
            + '_conditional_flags=' + repr(str(flags_file)) + '\n'
            + "scope_graph_call() { [[ \"$2\" == 64 ]] || exit 9; return 2; }\n"
            + source[start:stop] + "printf 'Summary: must not run\\n'\n}\nrun\n")
        result = subprocess.run(['/bin/bash', '-p', '-c', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertNotIn('Summary:', result.stdout)

    def test_flag_input_open_failure_cannot_continue_to_summary(self) -> None:
        source = support.SCANNER.read_text()
        start = source.index("  while IFS= read -r -d '' _prepass_file; do")
        stop = source.index("  capture_bounded_command", start)
        loop = source[start:stop]
        paths = self.directory / "paths"
        paths.write_bytes(b"ordinary.ts\0")
        script = (
            "set -uo pipefail\n"
            + "flags=',conditional-assertion,'\n"
            + "_matched_paths=" + repr(str(paths)) + "\n"
            + "_conditional_flags=" + repr(str(self.directory / "missing-flags")) + "\n"
            + loop + "printf 'Summary: must not run\\n'\n"
        )
        result = subprocess.run(["/bin/bash", "-p", "-c", script],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertNotIn("Summary:", result.stdout)

    def test_helper_failure_has_no_summary(self) -> None:
        code, stdout, stderr = self.run_scanner("helper-error")
        self.assertEqual(code, 2, stdout + stderr)
        self.assertNotRegex(stdout, r"(?m)^Summary:")
        self.assertIn("conditional assertion discovery failed", stderr)

    def test_excluded_source_mutation_has_no_summary(self) -> None:
        code, stdout, stderr = self.run_scanner("source-mutation")
        self.assertEqual(code, 2, stdout + stderr)
        self.assertNotRegex(stdout, r"(?m)^Summary:")
        self.assertIn("changed", stderr)

    def test_excluded_file_missing_dependency_created_mid_scan_fails_closed(self) -> None:
        # Excluded-file pings only confirm the worker is alive; the created
        # dependency is caught at the next checkpoint, by whichever check runs
        # first there (candidate manifest or scope witnesses), before any Summary.
        code, stdout, stderr = self.run_scanner("witness-mutation")
        self.assertEqual(code, 2, stdout + stderr)
        self.assertNotRegex(stdout, r"(?m)^Summary:")
        self.assertRegex(stderr, r"scope dependency changed|scanner candidate changed")
        self.assertIn("missing.ts", stderr)


if __name__ == "__main__":
    unittest.main()
