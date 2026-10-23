#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise a copied skill launcher/runtime without checkout package resolution."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPOSITORY = Path(__file__).resolve().parents[2]
LAUNCHER = REPOSITORY / "scripts/dev/scanner-launcher.sh"
RUNTIME = REPOSITORY / "skills/e2e-reviewer/scripts/scanner"


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


class LauncherTests(unittest.TestCase):
    def test_public_entry_matches_verified_launcher(self):
        # The development-template tests cannot establish public cutover alone.
        public = REPOSITORY / 'skills/e2e-reviewer/scripts/scan.sh'
        self.assertEqual(public.read_bytes(), LAUNCHER.read_bytes(),
                         'public entry has not been replaced by the verified Node launcher')

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="scanner-launcher-test-")
        cls.root = Path(cls.temporary.name).resolve()
        cls.scripts = cls.root / "installed/e2e-reviewer/scripts"
        cls.scripts.mkdir(parents=True)
        cls.launcher = cls.scripts / "scan.sh"
        shutil.copy2(LAUNCHER, cls.launcher)
        cls.runtime = cls.scripts / "scanner"
        shutil.copytree(RUNTIME, cls.runtime)
        cls.snapshot = {str(file.relative_to(cls.scripts)): digest(file)
                        for file in cls.scripts.rglob("*") if file.is_file()}
        if any(cls.root.rglob("node_modules")):
            raise AssertionError("skill fixture must not contain node_modules")
        if any(cls.root.rglob("packages")):
            raise AssertionError("skill fixture must not contain checkout packages")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.project_temporary = tempfile.TemporaryDirectory(prefix="project-", dir=self.root)
        self.project = Path(self.project_temporary.name)
        (self.project / "package.json").write_text('{}\n')
        self.sources = {self.project / 'package.json': (self.project / 'package.json').read_bytes()}

    def tearDown(self):
        try:
            for file, expected in self.sources.items():
                self.assertEqual(file.read_bytes(), expected, "scanner changed reviewed input")
            actual = {str(file.relative_to(self.scripts)): digest(file)
                      for file in self.scripts.rglob("*") if file.is_file()}
            self.assertEqual(actual, self.snapshot, "test failed to restore isolated runtime")
        finally:
            self.project_temporary.cleanup()

    def put(self, name, text):
        file = self.project / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
        self.sources[file] = file.read_bytes()
        return file

    def run_scan(self, *arguments, expected=0, environment=None):
        env = dict(os.environ)
        for key in ("NODE_OPTIONS", "NODE_PATH", "BASH_ENV", "ENV", "E2E_SMELL_FAIL_ON"):
            env.pop(key, None)
        if environment:
            env.update(environment)
        result = subprocess.run(['/bin/bash', '-p', str(self.launcher), *map(str, arguments)],
                                cwd=self.project, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, (result.stdout, result.stderr))
        return result

    def assert_incomplete(self, result):
        self.assertIn('INCOMPLETE', result.stdout + result.stderr)
        self.assertFalse(any(line.startswith('Summary:') for line in result.stdout.splitlines()))

    @contextlib.contextmanager
    def changed(self, file, data):
        original = file.read_bytes()
        try:
            file.write_bytes(data)
            yield
        finally:
            file.write_bytes(original)

    @contextlib.contextmanager
    def absent(self, file):
        original = file.read_bytes()
        file.unlink()
        try:
            yield
        finally:
            file.write_bytes(original)

    def clean(self):
        return self.put('clean.spec.ts', "import {test,expect} from '@playwright/test';test('ok',async({page})=>{await expect(page.getByTestId('status')).toHaveText('Ready');});\n")

    def focused(self):
        return self.put('focused.spec.ts', "import {test} from '@playwright/test';test.only('focus',()=>{});\n")

    def test_clean_default_root_text_json_and_help(self):
        file = self.clean()
        self.assertIn('Summary: 0 total hit(s)', self.run_scan().stdout)
        self.assertIn('Summary: 0 total hit(s)', self.run_scan(file).stdout)
        report = json.loads(self.run_scan('--format', 'json', file).stdout)
        self.assertEqual(report['schema'], 'e2e-skills-node-scan-v1')
        self.assertTrue(report['execution']['complete'])
        self.assertEqual(report['findings'], [])
        self.assertIn('Usage:', self.run_scan('--help').stdout)
        self.assertIn('Usage:', self.run_scan('-h').stdout)

    def test_hit_and_policy_json_text(self):
        file = self.focused()
        text = self.run_scan(file, expected=1).stdout
        self.assertIn('Summary: 1 total hit(s), 1 P0', text)
        report = json.loads(self.run_scan(file, '--format', 'json', expected=1).stdout)
        self.assertEqual(report['counts']['p0'], 1)
        self.assertEqual(report['findings'][0]['patternId'], '#7')
        self.assertEqual(report['findings'][0]['file'], str(file))
        self.run_scan(file, '--fail-on', 'none')
        self.run_scan(file, environment={'E2E_SMELL_FAIL_ON': 'none'})
        self.run_scan(file, '--fail-on', 'p0', expected=1, environment={'E2E_SMELL_FAIL_ON': 'none'})

    def test_pom_candidate_preserves_review_and_candidate_policy(self):
        file = self.put('pom.spec.ts', "import {test,expect} from '@playwright/test';test('x',()=>{const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();});\n")
        report = json.loads(self.run_scan(file, '--format', 'json').stdout)
        self.assertTrue(report['execution']['complete'])
        self.assertTrue(report['review']['required'])
        self.assertTrue(report['review']['obligations'])
        self.assertEqual(report['counts']['p0'], 0)
        self.assertEqual(report['counts']['p0Candidate'], 1)
        self.assertEqual(report['findings'][0]['disposition'], 'candidate')
        self.run_scan(file, '--fail-on', 'p0-candidate', expected=1)

    def test_report_file_matches_text_and_never_overwrites(self):
        file = self.focused()
        text = self.run_scan(file, '--format', 'text', expected=1).stdout
        report = self.project / 'report.txt'
        result = self.run_scan('--report-file', report, file, expected=1)
        self.assertIn('Full report:', result.stdout)
        self.assertEqual(report.read_text(), text)
        before = report.read_bytes()
        self.run_scan('--report-file', report, file, expected=2)
        self.assertEqual(report.read_bytes(), before)
        self.run_scan('--report-file', self.project / 'invalid.txt', '--format', 'json', file, expected=2)
        self.assertFalse((self.project / 'invalid.txt').exists())

    def test_parser_error_stays_incomplete_under_none_policy(self):
        file = self.put('broken.spec.ts', "import {test} from '@playwright/test';test(")
        self.assert_incomplete(self.run_scan(file, '--fail-on', 'none', expected=2))
        report = json.loads(self.run_scan(file, '--format', 'json', '--fail-on', 'none', expected=2).stdout)
        self.assertFalse(report['execution']['complete'])

    def test_invalid_arguments_and_policy_are_rejected(self):
        file = self.clean()
        for args in [(file, '--unknown'), (file, '--fail-on', 'bad'), (file, '--format', 'bad'),
                     (file, '--fail-on'), (file, '--format'), (file, '--report-file'),
                     (file, file), (file, '--scan'), (file, '--project-eslint')]:
            self.run_scan(*args, expected=2)
        self.run_scan(file, expected=2, environment={'E2E_SMELL_FAIL_ON': 'bad'})

    def test_missing_or_corrupt_runtime_files_fail_before_import(self):
        file = self.clean()
        for name in ['src/source.mjs', 'src/cli.mjs', 'vendor/typescript/typescript.cjs', 'manifest.json']:
            target = self.runtime / name
            with self.absent(target):
                self.assert_incomplete(self.run_scan(file, expected=2))
            with self.changed(target, b'corrupted runtime'):
                self.assert_incomplete(self.run_scan(file, expected=2))

    def test_malformed_manifest_records_and_paths_fail_closed(self):
        file = self.clean()
        target = self.runtime / 'manifest.json'
        original = json.loads(target.read_text())
        for key, value in [('schema', 'wrong'), ('entrypoint', '../outside.mjs'), ('files', [])]:
            altered = dict(original, **{key: value})
            with self.changed(target, json.dumps(altered).encode()):
                self.assert_incomplete(self.run_scan(file, expected=2))
        altered = json.loads(target.read_text())
        altered['files']['src/cli.mjs']['sha256'] = 'invalid'
        with self.changed(target, json.dumps(altered).encode()):
            self.assert_incomplete(self.run_scan(file, expected=2))

    def test_omitted_manifest_module_cannot_execute_unverified_bytes(self):
        file = self.clean()
        manifest = self.runtime / 'manifest.json'
        altered = json.loads(manifest.read_text())
        del altered['files']['src/source.mjs']
        module = self.runtime / 'src/source.mjs'
        marker = self.project / 'UNVERIFIED_MODULE_EXECUTED'
        injected = ("import injectedFs from 'node:fs';injectedFs.writeFileSync(" + json.dumps(str(marker)) + ",'bad');\n").encode() + module.read_bytes()
        with self.changed(manifest, json.dumps(altered).encode()), self.changed(module, injected):
            self.assert_incomplete(self.run_scan(file, expected=2))
        self.assertFalse(marker.exists())

    def test_unlisted_runtime_file_is_rejected_without_deletion(self):
        file = self.clean()
        extra = self.runtime / 'src/unlisted.mjs'
        extra.write_text("throw new Error('unexpected');\n")
        try:
            self.assert_incomplete(self.run_scan(file, expected=2))
            self.assertEqual(extra.read_text(), "throw new Error('unexpected');\n")
        finally:
            extra.unlink()

    def test_symlink_module_manifest_and_runtime_root_fail_closed(self):
        file = self.clean()
        for name in ['src/source.mjs', 'manifest.json']:
            target = self.runtime / name
            external = self.project / 'copy'
            external.write_bytes(target.read_bytes())
            with self.absent(target):
                target.symlink_to(external)
                try:
                    self.assert_incomplete(self.run_scan(file, expected=2))
                finally:
                    target.unlink()
            external.unlink()
        moved = self.scripts / 'runtime-moved'
        self.runtime.rename(moved)
        self.runtime.symlink_to(moved, target_is_directory=True)
        try:
            self.assert_incomplete(self.run_scan(file, expected=2))
        finally:
            self.runtime.unlink()
            moved.rename(self.runtime)

    def test_project_path_and_node_startup_injections_never_execute(self):
        file = self.clean()
        marker = self.project / 'INJECTION_EXECUTED'
        poison = self.put('startup.cjs', "require('node:fs').writeFileSync(" + json.dumps(str(marker)) + ",'bad');")
        fake_bin = self.project / 'fake-bin'
        fake_bin.mkdir()
        for name in ['node', 'npm', 'npx', 'python3', 'dirname']:
            executable = self.put('fake-bin/' + name, '#!/bin/sh\ntouch "' + str(marker) + '"\nexit 9\n')
            executable.chmod(0o755)
        shell_startup = self.put('shell-startup', 'touch "' + str(marker) + '"\n')
        result = self.run_scan(file, environment={
            'PATH': str(fake_bin), 'NODE_OPTIONS': '--require=' + str(poison),
            'NODE_PATH': str(self.project / 'fake-modules'), 'BASH_ENV': str(shell_startup),
            'ENV': str(shell_startup), 'CDPATH': str(self.project),
        })
        self.assertIn('Summary: 0 total hit(s)', result.stdout)
        self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
