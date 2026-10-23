#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline copied-runtime regression budget, not a scanner speed comparison."""
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPOSITORY = Path(__file__).resolve().parents[2]
CPU_BUDGET_SECONDS = 30
HANG_TIMEOUT_SECONDS = 900  # Wall time is only a hang bound, never the CPU budget.


def digest_tree(root):
    return {str(file.relative_to(root)): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted(root.rglob('*')) if file.is_file()}


def child_cpu():
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime


class NodePerformanceTests(unittest.TestCase):
    def test_original_sixteen_file_workload(self):
        # Fail closed on stale shipping bytes; checking is offline and installs nothing.
        current = subprocess.run(
            [sys.executable, str(REPOSITORY / 'scripts/dev/build-scanner-runtime.py'), '--check'],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(current.returncode, 0, 'runtime freshness required: ' + current.stderr)
        with tempfile.TemporaryDirectory(prefix='scanner-node-performance-') as temporary:
            root = Path(temporary).resolve()
            scripts = root / 'skill/scripts'
            scripts.mkdir(parents=True)
            shutil.copytree(REPOSITORY / 'skills/e2e-reviewer/scripts/scanner', scripts / 'scanner')
            shutil.copy2(REPOSITORY / 'scripts/dev/scanner-launcher.sh', scripts / 'scan.sh')
            runtime_before = digest_tree(scripts)
            project = root / 'project'
            project.mkdir()
            # Exact original workload: test-reviewer-scanner.py:1698-1713.
            for index in range(16):
                (project / f'flow-{index}.spec.ts').write_text(
                    "import { expect, test } from '@playwright/test';\n"
                    "async function login(page: unknown, path: string, account?: unknown) {}\n"
                    f"test('safe flow {index}', async ({{ page }}) => {{\n"
                    "  await login(page, '/', FORM_E2E_TEST_ACCOUNT2);\n"
                    "  await login(page, '/');\n"
                    "  await page.goto('/');\n"
                    "  await expect(page).toHaveURL('/');\n"
                    "});\n", encoding='utf-8')
            before = digest_tree(project)
            env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
                   'HOME': str(root / 'home')}
            Path(env['HOME']).mkdir()
            cpu_started, wall_started = child_cpu(), time.monotonic()
            result = subprocess.run(
                ['/bin/bash', '-p', str(scripts / 'scan.sh'), str(project),
                 '--format', 'json', '--fail-on', 'none'],
                cwd=root, env=env, capture_output=True, text=True, timeout=HANG_TIMEOUT_SECONDS)
            cpu, wall = child_cpu() - cpu_started, time.monotonic() - wall_started
            after = digest_tree(project)
            runtime_after = digest_tree(scripts)
            # Print reproducible identity/measurement even when a semantic assertion fails.
            print(json.dumps({'schema': 'scanner-node-performance-v1',
                              'claim': 'fixed-workload CPU regression budget only',
                              'runtimeSha256': runtime_before, 'cpuSeconds': cpu,
                              'wallSeconds': wall, 'inputPreSha256': before,
                              'inputPostSha256': after, 'returncode': result.returncode}, sort_keys=True))
            self.assertEqual(before, after, 'scanner changed input bytes or inventory')
            self.assertEqual(runtime_before, runtime_after, 'copied runtime changed')
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report['schema'], 'e2e-skills-node-scan-v1')
            self.assertEqual(report['status'], 'COMPLETE')
            self.assertIs(report['execution']['complete'], True)
            self.assertEqual(report['execution']['exitCode'], 0)
            self.assertEqual(report['execution']['incomplete'], [])
            self.assertEqual(report['execution']['diagnostics'], [])
            self.assertEqual(report.get('errors', []), [])
            self.assertFalse(any(item['patternId'] == '#14' for item in report['findings']),
                             'FORM_E2E_TEST_ACCOUNT2 is not a hardcoded credential')
            self.assertLess(cpu, CPU_BUDGET_SECONDS,
                            f'16-file workload used {cpu:.2f}s child CPU across {wall:.2f}s wall')

    def test_cpu_budget_does_not_charge_scheduler_wait(self):
        started = child_cpu()
        subprocess.run(['/bin/sleep', '0.05'], check=True, timeout=5)
        self.assertLess(child_cpu() - started, 0.02)


if __name__ == '__main__':
    unittest.main()
