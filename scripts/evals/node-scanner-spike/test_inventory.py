#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Inventory differential tests against the explicitly frozen shell oracle.

Only the test oracle invokes bash, rg and Python fingerprinting. The Node
implementation invokes none of them and does not run project configuration.
"""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/ci'))
from lib.legacy_scanner_oracle import legacy_scanner_file

SOURCE = legacy_scanner_file().read_text()
NODE = Path(__file__).with_name('inventory.mjs')


def function(name):
    found = re.search(r'^' + re.escape(name) + r'\(\) \{\n.*?^\}', SOURCE, re.M | re.S)
    if not found:
        raise AssertionError('oracle function missing: ' + name)
    return found.group()


def legacy(target, work):
    requested = str(target.absolute())
    if target.is_symlink():
        return 2, [], 'symbolic-link root'
    pinned = str(target.resolve())
    manifest = work / 'manifest'
    names = work / 'names'
    values = {
        'ROOT': pinned, 'REQUESTED_ROOT': requested,
        'REQUESTED_ROOT_REAL': pinned,
        'REQUESTED_ROOT_KIND': 'directory' if target.is_dir() else 'file',
        'RG_BIN': shutil.which('rg'), 'FIND_BIN': shutil.which('find'),
        'PYTHON3_BIN': shutil.which('python3'),
        'CODE_EXTENSIONS': 'ts,js,tsx,jsx,mts,mjs,cts,cjs',
        'ALL_CODE_GLOB': '*.{ts,js,tsx,jsx,mts,mjs,cts,cjs}',
    }
    script = '\n'.join(f'{key}={shlex.quote(value)}' for key, value in values.items())
    script += '\nEVAL_FIXTURE_EXCLUDES=()\n'
    # allocate_temp must assign the caller-local destination, like scan.sh.
    script += 'allocate_temp() { printf -v "$1" "%s" "$(mktemp)"; }\n'
    script += 'sanitize_evidence() { cat; }\n'
    for name in ['file_is_scanner_excluded', 'special_entry_can_hide_scanner_source',
                 'validate_scan_root_identity', 'preflight_scanner_tree',
                 'discover_candidate_files', 'validate_candidate_filenames', 'record_candidate_manifest']:
        script += function(name) + '\n'
    script += 'preflight_scanner_tree\n'
    script += f'discover_candidate_files {shlex.quote(str(names))}\n'
    script += f'validate_candidate_filenames {shlex.quote(str(names))}\n'
    script += f'record_candidate_manifest {shlex.quote(str(names))} {shlex.quote(str(manifest))}\n'
    # mktemp artifacts are only test-owned; use a separate TMPDIR.
    env = dict(os.environ, TMPDIR=str(work))
    result = subprocess.run(['/bin/bash', '-p', '-c', script], capture_output=True, text=True, env=env, timeout=10)
    records = []
    if manifest.exists():
        fields = manifest.read_bytes().split(b'\0')[:-1]
        for name, value in zip(fields[::2], fields[1::2]):
            items = value.decode('ascii').split(':')
            records.append({'path': os.fsdecode(name), 'identity': dict(zip(['dev', 'ino', 'mode', 'size', 'mtimeNs', 'ctimeNs', 'sha256'], items))})
    return result.returncode, records, result.stderr


def node(*args):
    result = subprocess.run(['node', str(NODE), *map(str, args)], capture_output=True, text=True, timeout=10)
    return result.returncode, json.loads(result.stdout)


class DifferentialInventory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.tree = self.base / 'tree'
        self.tree.mkdir()
        self.work = self.base / 'oracle'
        self.work.mkdir()

    def put(self, name, content='export const value = 1;\n'):
        dest = self.tree / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        return dest

    def compare(self, target=None):
        target = target or self.tree
        code, records, stderr = legacy(target, self.work)
        actual_code, report = node(target)
        self.assertEqual(actual_code, code, stderr + '\n' + json.dumps(report))
        self.assertEqual(report['complete'], code == 0)
        if code == 0:
            self.assertEqual(report['candidates'], records)
        return report

    def test_discovery_identity_and_exclusions(self):
        for ext in ['ts', 'js', 'tsx', 'jsx', 'mts', 'mjs', 'cts', 'cjs']:
            self.put(f'tests/{ext}.{ext}')
        for name in ['.hidden.ts', '.ignored/test.ts', 'z.ts', 'A.ts', 'é.ts', 'space name.ts']:
            self.put(name)
        self.put('.gitignore', '.ignored/\n')
        for name in ['node_modules/a.ts', '.git/a.ts', 'playwright-report/a.ts', 'cypress/reports/a.ts', 'test-results/a.ts', 'dist/a.ts', 'build/a.ts', '.next/a.ts', 'out/a.ts', 'coverage/a.ts', '.yarn/a.ts', '.pnp.cjs', '.pnp.loader.mjs', 'x.min.js', 'x.min.ts', 'ordinary.txt', 'folder.min.js/a.ts']:
            self.put(name)
        report = self.compare()
        self.assertEqual(len(report['candidates']), 14)
        for name in ['ordinary.txt', '.pnp.cjs', 'x.min.js']:
            self.compare(self.tree / name)

    def test_filename_transport(self):
        for name in ['colon:name.ts', 'line\nbreak.js']:
            target = self.put(name)
            with self.subTest(name=name):
                self.compare(target)
        # Unsupported names in excluded trees do not poison discovery.
        self.put('node_modules/a:b.ts')
        self.compare(self.tree / 'node_modules')

    def test_special_entries_follow_source_boundary(self):
        self.put('a.ts')
        self.put('assets/logo.png')
        (self.tree / 'assets/current.png').symlink_to('logo.png')
        os.mkfifo(self.tree / 'asset.pipe')
        self.compare()  # Unrelated asset links/FIFOs are permitted.
        # Minified discovery globs do not erase preflight's source-link check.
        self.put('folder.min.js/a.ts')
        nested_link = self.tree / 'folder.min.js/b.ts'
        nested_link.symlink_to('a.ts')
        self.compare()
        nested_link.unlink()
        for name, target in [('source.ts', 'a.ts'), ('directory', 'assets'), ('tests', 'missing'), ('dangling.mjs', 'missing')]:
            with self.subTest(name=name):
                link = self.tree / name
                link.symlink_to(target)
                self.compare()
                link.unlink()
        fifo = self.tree / 'source.js'
        os.mkfifo(fifo)
        self.compare()
        root_link = self.base / 'root-link'
        root_link.symlink_to(self.tree, target_is_directory=True)
        self.compare(root_link)
        # The legacy scanner permits a symlink in a parent component, then pins
        # the resolved root. Only a symlink at the requested root is refused.
        self.compare(root_link / 'a.ts')

    def test_revalidation_detects_changes_and_additions(self):
        source = self.put('a.ts')
        baseline = self.compare()
        stored = self.base / 'baseline.json'
        stored.write_text(json.dumps(baseline))
        self.assertEqual(node('--revalidate', stored)[0], 0)
        source.write_text('export const value = 2;\n')
        legacy_code, changed_records, _ = legacy(self.tree, self.work)
        self.assertEqual(legacy_code, 0)
        self.assertNotEqual(changed_records, baseline['candidates'])
        code, report = node('--revalidate', stored)
        self.assertEqual(code, 2)
        self.assertIn('identity-drift', [item['code'] for item in report['errors']])
        baseline = node(self.tree)[1]
        stored.write_text(json.dumps(baseline))
        self.put('late.js')
        legacy_code, added_records, _ = legacy(self.tree, self.work)
        self.assertEqual(legacy_code, 0)
        self.assertEqual(len(added_records), len(baseline['candidates']) + 1)
        code, report = node('--revalidate', stored)
        self.assertEqual(code, 2)
        self.assertIn('added', [item['code'] for item in report['errors']])

    def test_late_fingerprint_error_is_not_clean(self):
        self.put('a.ts')
        locked = self.put('zz_last.ts')
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o644)
        if os.access(locked, os.R_OK):
            self.skipTest('privileged user can read chmod(000); permission oracle unavailable')
        report = self.compare()
        self.assertFalse(report['complete'])
        self.assertEqual(len(report['candidates']), 1)
        self.assertEqual(report['errors'][0]['path'], str(locked))


if __name__ == '__main__':
    unittest.main(verbosity=2)
