#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Model/network-free checks of the external Node CI runner's trust boundary."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('node_scanner_ci', Path(__file__).with_name('test-node-scanner.py'))
assert SPEC and SPEC.loader
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class NodeScannerGuards(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='node-ci-guards-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.source = self.base / 'repo'
        self.source.mkdir()
        self.env = HELPER.environment(self.base, self.base)
        self.git('init', '-q')

    def git(self, *args):
        return subprocess.run(['/usr/bin/git', *args], cwd=self.source, env=self.env,
                              capture_output=True, check=True)

    def put(self, name, data='source\n', mode=0o644):
        file = self.source / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(data)
        file.chmod(mode)
        return file

    def package(self):
        self.put('.gitignore', 'node_modules/\n')
        self.put('packages/scanner/package.json', json.dumps({
            'name': 'scanner-test', 'version': '0.0.0', 'dependencies': {'typescript': '6.0.3', 'commander': '14.0.3'},
        }))
        self.put('packages/scanner/package-lock.json', json.dumps({
            'lockfileVersion': 3, 'packages': {
                '': {'dependencies': {'typescript': '6.0.3', 'commander': '14.0.3'}},
                'node_modules/commander': {'version': '14.0.3',
                    'resolved': 'https://registry.npmjs.org/commander/-/commander-14.0.3.tgz',
                    'integrity': 'sha512-dGVzdA=='},
                'node_modules/typescript': {'version': '6.0.3',
                    'resolved': 'https://registry.npmjs.org/typescript/-/typescript-6.0.3.tgz',
                    'integrity': 'sha512-dGVzdA=='},
            },
        }))
        self.put('packages/scanner/test/example.test.mjs', 'export {};\n')
        self.put('packages/scanner/src/example.mjs', 'export {};\n')

    def test_current_tracked_untracked_deleted_and_modes_preserved_without_ignored_dependencies(self):
        self.put('.gitignore', 'node_modules/\n')
        changed = self.put('src/tracked.mjs', 'old\n')
        deleted = self.put('deleted.mjs')
        self.git('add', '.')
        changed.write_text('current bytes\n')
        changed.chmod(0o751)
        deleted.unlink()
        self.put('new\nfile.mjs', 'untracked\n', 0o640)
        self.put('node_modules/dep/index.js', 'ignored\n')
        (self.source / 'node_modules/link').symlink_to('dep/index.js')
        view = self.base / 'view'
        original = HELPER.copy_source(self.source, view, self.env)
        self.assertEqual((view / 'src/tracked.mjs').read_text(), 'current bytes\n')
        self.assertEqual((view / 'src/tracked.mjs').stat().st_mode & 0o777, 0o751)
        self.assertEqual((view / 'new\nfile.mjs').read_text(), 'untracked\n')
        self.assertEqual(original['deleted.mjs'], {'deleted': True})
        self.assertFalse((view / 'deleted.mjs').exists())
        self.assertFalse((view / 'node_modules').exists())
        self.assertEqual(list((view / '.git').iterdir()), [])
        HELPER.verify_view(view, original)

    def test_symlink_leaf_parent_and_escaping_paths_are_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'secret').write_text('not copied')
        (self.source / 'leaf').symlink_to(outside / 'secret')
        (self.source / 'parent').symlink_to(outside, target_is_directory=True)
        for name in ('leaf', 'parent/secret', '../outside/secret', '/etc/passwd'):
            with self.subTest(name=name), self.assertRaises((OSError, HELPER.GateError)):
                HELPER.source_file(self.source, name)

    def test_source_drift_during_copy_and_extra_or_changed_test_source_are_rejected(self):
        target = self.put('source.mjs', 'before')
        original_reader = HELPER.source_file
        reads = 0

        def racing(source, name):
            nonlocal reads
            reads += 1
            if reads == 2:
                target.write_text('changed')
            return original_reader(source, name)

        with patch.object(HELPER, 'source_file', side_effect=racing):
            with self.assertRaisesRegex(HELPER.GateError, 'drift'):
                HELPER.copy_source(self.source, self.base / 'racing', self.env)
        view = self.base / 'view'
        original = HELPER.copy_source(self.source, view, self.env)
        (view / 'source.mjs').chmod(0o600)
        with self.assertRaisesRegex(HELPER.GateError, 'changed'):
            HELPER.verify_view(view, original)
        (view / 'extra.mjs').write_text('unexpected')
        with self.assertRaisesRegex(HELPER.GateError, 'inventory'):
            HELPER.verify_view(view, original)

    def test_runtime_absolute_external_mode_and_version_guards(self):
        node = self.base / 'node'
        node.write_text('runtime placeholder')
        node.chmod(0o755)
        local = self.put('node', mode=0o755)
        for raw in ('node', str(local)):
            with self.assertRaises(HELPER.GateError):
                HELPER.trusted_file(raw, self.source, executable=True)
        node.chmod(0o777)
        with self.assertRaises(HELPER.GateError):
            HELPER.trusted_file(node, self.source, executable=True)
        node.chmod(0o755)
        for version in ('v21.9.0\n', 'not a Node version'):
            with patch.object(HELPER.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, version, '')):
                with self.assertRaisesRegex(HELPER.GateError, '>=22'):
                    HELPER.node_runtime(str(node), self.source, self.env, self.base)
        with patch.object(HELPER.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'v22.0.0\n', '')):
            self.assertEqual(HELPER.node_runtime(str(node), self.source, self.env, self.base), node)

    def test_npm_resolution_uses_node_prefix_and_never_ambient_path(self):
        node = self.base / 'prefix/bin/node'
        npm = self.base / 'prefix/lib/node_modules/npm/bin/npm-cli.js'
        npm.parent.mkdir(parents=True)
        npm.write_text('trusted npm placeholder')
        npm.chmod(0o644)
        with patch.dict(os.environ, {'PATH': str(self.source)}):
            self.assertEqual(HELPER.npm_runtime(node, self.source), npm)

    def test_install_stage_excludes_project_config_and_refuses_unpinned_inputs(self):
        self.package()
        self.put('packages/scanner/.npmrc', 'registry=https://untrusted.invalid\n')
        view = self.base / 'view'
        HELPER.copy_source(self.source, view, self.env)
        install = self.base / 'install'
        HELPER.prepare_install(view, install)
        self.assertEqual({p.name for p in install.iterdir()}, {'package.json', 'package-lock.json'})
        self.assertTrue((view / 'packages/scanner/.npmrc').exists(), 'source config is preserved as inert bytes')
        lockfile = view / 'packages/scanner/package-lock.json'
        lock = json.loads(lockfile.read_text())
        for name in ('typescript', 'commander'):
            with self.subTest(dependency=name):
                dependency = lock['packages']['node_modules/' + name]
                original_url = dependency['resolved']
                dependency['resolved'] = 'file:/tmp/untrusted'
                lockfile.write_text(json.dumps(lock))
                with self.assertRaisesRegex(HELPER.GateError, 'public-registry'):
                    HELPER.prepare_install(view, self.base / ('bad-install-' + name))
                dependency['resolved'] = original_url

    def test_full_orchestration_uses_clean_env_actual_tests_and_propagates_failure(self):
        self.package()
        self.put('.npmrc', 'registry=https://untrusted.invalid\n')
        calls = []

        def command(argv, cwd, env, timeout):
            calls.append((argv, cwd, env))
            for variable in ('NODE_OPTIONS', 'NODE_PATH', 'NPM_TOKEN', 'npm_config_registry', 'HTTP_PROXY', 'BASH_ENV'):
                self.assertNotIn(variable, env)
            self.assertNotEqual(Path(env['HOME']), self.source)
            if 'ci' in argv:
                self.assertFalse((cwd / '.npmrc').exists())
                self.assertIn('--ignore-scripts', argv)
                self.assertIn('--registry=https://registry.npmjs.org', argv)
                for prefix in ('--userconfig=', '--globalconfig='):
                    file = Path(next(value[len(prefix):] for value in argv if value.startswith(prefix)))
                    self.assertEqual(file.read_bytes(), b'')
                (cwd / 'node_modules').mkdir()
            else:
                self.assertIn('--test-concurrency=2', argv)
                self.assertEqual(Path(argv[-1]).name, 'example.test.mjs')
                self.assertTrue(Path(argv[-1]).is_file())
                raise HELPER.GateError('intentional test failure')

        with patch.dict(os.environ, {'NODE_OPTIONS': '--require=/untrusted', 'NPM_TOKEN': 'must-not-forward',
                                     'npm_config_registry': 'https://untrusted.invalid', 'BASH_ENV': '/untrusted'}), \
             patch.object(HELPER, 'node_runtime', return_value=Path('/trusted/node')), \
             patch.object(HELPER, 'npm_runtime', return_value=Path('/trusted/npm-cli.js')), \
             patch.object(HELPER, 'command', side_effect=command):
            with self.assertRaisesRegex(HELPER.GateError, 'intentional test failure'):
                HELPER.run(self.source, '/trusted/node')
        self.assertEqual(len(calls), 2)
        self.assertFalse((self.source / 'packages/scanner/node_modules').exists())
        self.assertTrue((self.source / '.npmrc').exists())
        self.assertTrue(all(not cwd.exists() for _, cwd, _ in calls), 'only owned temporary workspaces are cleaned')

    def test_command_failure_and_timeout_cannot_report_success(self):
        child = Mock(pid=12345)
        child.wait.return_value = 7
        with patch.object(HELPER.subprocess, 'Popen', return_value=child) as spawn:
            with self.assertRaisesRegex(HELPER.GateError, 'exit 7'):
                HELPER.command(['/trusted/node'], self.base, self.env, 1)
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        child.wait.side_effect = [subprocess.TimeoutExpired(['/trusted/node'], 1), -9]
        with patch.object(HELPER.subprocess, 'Popen', return_value=child), \
             patch.object(HELPER.os, 'killpg') as terminate:
            with self.assertRaisesRegex(HELPER.GateError, 'timed out'):
                HELPER.command(['/trusted/node'], self.base, self.env, 1)
            terminate.assert_called_once_with(child.pid, HELPER.signal.SIGKILL)


if __name__ == '__main__':
    unittest.main()
