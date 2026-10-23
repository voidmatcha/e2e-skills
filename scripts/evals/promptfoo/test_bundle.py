#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Portable evidence integrity and no-model restoration regressions."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from bundle import export, restore, verify
from config import write_config
from canary import fresh_external_output, ROOT
from provider import project


class BundleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        self.report = self.source / 'holdout.json'
        self.report.write_text(json.dumps({'status': 'INCONCLUSIVE', 'complete': False,
                                          'runs': [{'case': 'one', 'output': 'unaltered', 'score': {'fp': 1}}]}))
        for name in ('command.json', 'harness.stdout.txt', 'harness.stderr.txt'):
            (self.source / name).write_text('original log\n')
        self.config = self.source / 'config.json'
        write_config(self.report, 'one', self.config)
        self.bundle = self.root / 'bundle'

    def make_bundle(self):
        return export(self.source, self.config, 'one', self.bundle)

    def test_deterministic_export_and_different_root_restore(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        first = self.make_bundle()
        other = self.root / 'another-bundle'
        export(self.source, self.config, 'one', other)
        self.assertEqual((self.bundle / 'manifest.json').read_bytes(), (other / 'manifest.json').read_bytes())
        restored = self.root / 'new-root'
        receipt = restore(self.bundle, restored)
        self.assertEqual(receipt['manifest_sha256'], first['manifest_sha256'])
        self.assertEqual(verify(restored), first)
        request = json.loads(json.loads(Path(receipt['restored_config']).read_text())['tests'][0]['vars']['request'])
        self.assertEqual(project(request)['cell'], first['cell'])
        self.assertEqual(request['report'], str(restored / 'evidence/holdout.json'))
        self.assertEqual(receipt['model_calls_by_restore'], 0)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir()})

    def test_modified_file_rejected(self):
        self.make_bundle()
        (self.bundle / 'evidence/holdout.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'hash'):
            restore(self.bundle, self.root / 'restore')
        self.assertFalse((self.root / 'restore').exists())

    def test_nested_restore_rejected_without_source_mutation(self):
        verified = self.make_bundle()
        alias = self.root / 'bundle-alias'
        alias.symlink_to(self.bundle, target_is_directory=True)
        before = {p.relative_to(self.bundle).as_posix(): p.read_bytes() if p.is_file() else None
                  for p in self.bundle.rglob('*')}
        for output in (self.bundle / 'child', self.bundle / 'evidence/../child', alias / 'child'):
            with self.subTest(output=output):
                with self.assertRaisesRegex(ValueError, 'overlap'):
                    restore(self.bundle, output)
                self.assertFalse(output.exists())
                self.assertFalse(output.with_name(output.name + '-view.json').exists())
                self.assertFalse(output.with_name(output.name + '-receipt.json').exists())
                self.assertEqual(before, {p.relative_to(self.bundle).as_posix(): p.read_bytes() if p.is_file() else None
                                          for p in self.bundle.rglob('*')})
                self.assertEqual(verify(self.bundle), verified)

    def test_source_ancestor_restore_rejected(self):
        verified = self.make_bundle()
        with self.assertRaisesRegex(ValueError, 'overlap'):
            restore(self.bundle, self.root)
        self.assertEqual(verify(self.bundle), verified)

    def test_generated_restore_outputs_cannot_overlap_source(self):
        for suffix in ('-view.json', '-receipt.json'):
            with self.subTest(suffix=suffix):
                source = self.root / ('restore' + suffix)
                verified = export(self.source, self.config, 'one', source)
                before = {p.relative_to(source).as_posix(): p.read_bytes() if p.is_file() else None
                          for p in source.rglob('*')}
                output = self.root / 'restore'
                with self.assertRaisesRegex(ValueError, 'overlap'):
                    restore(source, output)
                self.assertFalse(output.exists())
                self.assertEqual(before, {p.relative_to(source).as_posix(): p.read_bytes() if p.is_file() else None
                                          for p in source.rglob('*')})
                self.assertEqual(verify(source), verified)

    def test_generated_restore_symlink_cannot_overlap_source(self):
        verified = self.make_bundle()
        for suffix in ('-view.json', '-receipt.json'):
            with self.subTest(suffix=suffix):
                output = self.root / ('restore' + suffix)
                output.with_name(output.name + suffix).symlink_to(self.bundle / 'manifest.json')
                with self.assertRaisesRegex(ValueError, 'overlap'):
                    restore(self.bundle, output)
                self.assertFalse(output.exists())
                self.assertEqual(verify(self.bundle), verified)

    def test_derived_destination_collision_preserves_existing_file(self):
        self.make_bundle()
        existing = self.root / 'restore-view.json'
        existing.write_text('existing view')
        with self.assertRaises(FileExistsError):
            restore(self.bundle, self.root / 'restore')
        self.assertFalse((self.root / 'restore').exists())
        self.assertEqual(existing.read_text(), 'existing view')

    def test_raw_log_mutation_rejected(self):
        self.make_bundle()
        (self.bundle / 'evidence/logs/harness.stdout.txt').write_text('changed log')
        with self.assertRaisesRegex(ValueError, 'hash'):
            verify(self.bundle)

    def test_path_traversal_and_absolute_path_rejected(self):
        self.make_bundle()
        path = self.bundle / 'manifest.json'
        original = path.read_text()
        for name in ('../outside', '/tmp/outside', 'evidence/../outside', 'a\\b', './x'):
            manifest = json.loads(original)
            manifest['files'][name] = {'sha256': 'x', 'bytes': 0}
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'unsafe'):
                verify(self.bundle)

    def test_bundle_and_source_symlinks_rejected(self):
        (self.source / 'alias').symlink_to(self.report)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            export(self.source, self.source / 'alias', 'one', self.bundle)
        self.make_bundle()
        (self.bundle / 'extra-link').symlink_to(self.report)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            verify(self.bundle)

    def test_unlisted_files_and_existing_destination_rejected(self):
        self.make_bundle()
        with self.assertRaises(FileExistsError):
            export(self.source, self.config, 'one', self.bundle)
        extra = self.bundle / 'extra'
        extra.write_text('unlisted')
        with self.assertRaisesRegex(ValueError, 'unlisted'):
            verify(self.bundle)

    def test_wrong_frozen_config_rejected(self):
        config = json.loads(self.config.read_text())
        request = json.loads(config['tests'][0]['vars']['request'])
        request['sha256'] = '0' * 64
        config['tests'][0]['vars']['request'] = json.dumps(request)
        self.config.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError, 'frozen report'):
            self.make_bundle()
        self.assertFalse(self.bundle.exists())

    def test_symlink_ancestor_rejected(self):
        link = self.root / 'alias-root'
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            export(link, self.config, 'one', self.bundle)

    def test_canary_output_symlink_and_checkout_rejected(self):
        link = self.root / 'checkout-alias'
        link.symlink_to(ROOT, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            fresh_external_output(link / 'must-not-write')
        with self.assertRaisesRegex(ValueError, 'outside'):
            fresh_external_output(ROOT / 'must-not-write')
        self.assertEqual(fresh_external_output(self.root / 'safe-new'), self.root / 'safe-new')

    def test_bundled_code_never_executed(self):
        self.make_bundle()
        code = self.bundle / 'adapter/provider.py'
        code.write_text('raise RuntimeError("must never run")\n')
        manifest_path = self.bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['files']['adapter/provider.py'] = {'sha256': hashlib.sha256(code.read_bytes()).hexdigest(), 'bytes': code.stat().st_size}
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'trusted local adapter'):
            restore(self.bundle, self.root / 'restored')


if __name__ == '__main__':
    unittest.main()
