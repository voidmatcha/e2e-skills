#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Necessary #5a discovery, lexical parity and fail-closed identity tests."""
import hashlib
import importlib.util
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'skills/e2e-reviewer/scripts/conditional-discovery.py'
SPEC = importlib.util.spec_from_file_location('conditional_discovery', HELPER)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
SOURCE = (ROOT / 'skills/e2e-reviewer/scripts/scan.sh').read_text()


def function(source, name):
    return re.search(r'^' + name + r'\(\) \{\n.*?^\}\n', source, re.M | re.S)[0]


def identity(path):
    info = path.stat()
    return (':'.join(str(getattr(info, key)) for key in helper.FIELDS) + ':' +
            hashlib.sha256(path.read_bytes()).hexdigest()).encode()


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='conditional-discovery-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'source.ts'

    def invoke(self, sources=(), paths=None, manifest=None):
        names = []
        entries = []
        for index, source in enumerate(sources):
            path = self.root / ('source' + str(index) + '.ts')
            path.write_bytes(source)
            name = os.fsencode(path)
            names.append(name)
            entries.extend((name, identity(path)))
        (self.root / 'paths').write_bytes(paths if paths is not None else b''.join(n + b'\0' for n in names))
        (self.root / 'manifest').write_bytes(manifest if manifest is not None else b''.join(n + b'\0' for n in entries))
        result = subprocess.run([sys.executable, '-I', '-B', str(HELPER), '--paths',
                                 str(self.root / 'paths'), '--manifest', str(self.root / 'manifest'),
                                 '--output', str(self.root / 'output')], capture_output=True, timeout=10)
        return result, (self.root / 'output').read_bytes() if (self.root / 'output').exists() else b''

    def test_ordered_flags_and_empty(self):
        result, flags = self.invoke([b'if (x) return;', b'if (x) expect(x);', b'if (x) "expect(x)";'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(flags, b'0\0' + b'1\0' + b'0\0')
        self.assertEqual(self.invoke()[0].returncode, 0)
        self.assertEqual((self.root / 'output').read_bytes(), b'')

    def test_window_boundary(self):
        self.assertTrue(helper.retain(b'if (x) {\n' + b'\n' * 39 + b'expect(x);'))
        self.assertFalse(helper.retain(b'if (x) {\n' + b'\n' * 40 + b'expect(x);'))

    def test_comments_and_strings(self):
        for source in (b'/*\nif (x) expect(x);\n*/', b'"\nif (x) expect(x);\n"',
                       b'if (x) { // expect(x);\n}', b'if (x) `expect(x)`;'):
            self.assertFalse(helper.retain(source), source)
        self.assertTrue(helper.retain(b'if (x) ex/**/pect(x);'))
        self.assertTrue(helper.retain(b'/*\n*/ if (x) {}\nif (x) assert.ok(x);'))

    def test_alias_and_unsupported_bypass(self):
        for source in (b"import { test, expect as __STR__ } from 'custom-e2e';\nif(x) 'v'();",
                       b'import { expect as check } from "x";\nif(x) check(x);',
                       b'if(x) return;\x00', b'if(x) return; // \xff'):
            self.assertTrue(helper.retain(source))

    def test_utf8_conservative_discovery(self):
        for prefix in ('\u00a0', '\u2003', '\u202f', '한글'):
            self.assertTrue(helper.retain((prefix + 'if(x) expect(x);').encode()))
        self.assertTrue(helper.retain('ifé(x) expect(x);'.encode()))
        self.assertFalse(helper.retain('if(x) return; // 한글'.encode()))
        self.assertFalse(helper.retain('/* 한글\nif(x) expect(x);\n*/'.encode()))
        self.assertFalse(helper.retain('if(x) "한글 expect(x)";'.encode()))
        self.assertTrue(helper.retain('if(x) "한글"; ex/**/pect(x);'.encode()))
        self.assertFalse(helper.retain('if(x) "\\한글 expect(x)";'.encode()))
        self.assertTrue(helper.retain(('if(x) ' + '한' * 22000).encode()))
        self.assertTrue(helper.retain('한\n'.encode() + b'x' * 65537))
        self.assertTrue(helper.retain(b'if(x) return; \xc0\xaf'))

    @unittest.skipUnless(shutil.which('awk'), 'awk required')
    def test_utf8_production_lexer_differential_across_locales(self):
        fn = function(SOURCE, 'conditional_assertion_hit_matches')
        lexer = fn[fn.index('    function executable_source'):fn.index('    NR < target')]
        source = ('/* 한글 */\n\u00a0if(x) ex/**/pect(x);\n'
                  'ifé(x) "é expect(x)";\n'
                  'if(x) "\\한글 expect(x)"; assert.ok(x);\n'
                  'if(x) "한\\\n글"; expect(x);\n'
                  '`é\nif(x) expect(x);\n`\n'
                  '// 한글\nif(x) cy.get(x).should(x);\n').encode()
        self.path.write_bytes(source)
        available = subprocess.check_output(['locale', '-a'], text=True).splitlines()
        utf8 = [value for value in available if value.lower().replace('-', '').endswith('.utf8')]
        if not utf8:
            self.skipTest('no UTF-8 locale installed')
        locales = ['C', next((value for value in utf8 if value.lower().startswith('en_us.')), utf8[0])]
        for locale in locales:
            env = dict(os.environ, LC_ALL=locale)
            result = subprocess.run(['awk', lexer + '\n{ print executable_source($0, 1) }', str(self.path)],
                                    capture_output=True, timeout=10, check=True, env=env)
            python_rows = list(helper.executable_lines(source))[:-1]
            self.assertEqual(result.stdout, b'\n'.join(python_rows) + b'\n', locale)

    def test_oversized_row_keeps_state(self):
        source = b'if(x) {\n' + b' ' * 65537 + b'/*\nexpect(x);\n*/\n}'
        self.assertFalse(helper.retain(source))
        source = b'/*' + b' ' * 65537 + b'*/\nif(x) expect(x);'
        self.assertTrue(helper.retain(source))

    def test_large_source_fallback_still_checks_digest(self):
        self.path.write_bytes(b'x' * (helper.MAX_SOURCE + 1))
        expected = identity(self.path)
        self.assertTrue(helper.inspect_source(os.fsencode(self.path), expected))
        with self.assertRaises(ValueError):
            helper.inspect_source(os.fsencode(self.path), expected[:-1] + b'z')

    def test_weird_paths(self):
        path = self.root / '-colon: newline\n tab\t한글.ts'
        path.write_bytes(b'if(x) expect(x);')
        name = os.fsencode(path)
        result, flags = self.invoke(paths=name+b'\0', manifest=name+b'\0'+identity(path)+b'\0')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(flags, b'1\0')

    def test_malformed_records_and_unknown_paths(self):
        for paths, manifest in ((b'a', b''), (b'\0', b''), (b'a\0', b''),
                                (b'', b'a\0'), (b'', b'a\0bad\0'),
                                (b'', b'\0x\0')):
            self.assertEqual(self.invoke(paths=paths, manifest=manifest)[0].returncode, 2)

    def test_duplicate_paths_and_manifest(self):
        self.path.write_bytes(b'if(x) expect(x);')
        name = os.fsencode(self.path)
        entry = name + b'\0' + identity(self.path) + b'\0'
        self.assertEqual(self.invoke(paths=(name+b'\0')*2, manifest=entry)[0].returncode, 2)
        self.assertEqual(self.invoke(paths=name+b'\0', manifest=entry*2)[0].returncode, 2)

    def test_deleted_symlink_directory_and_modified_sources(self):
        self.path.write_bytes(b'if(x) expect(x);')
        expected = identity(self.path)
        self.path.write_bytes(b'if(x) return;')
        with self.assertRaises(ValueError):
            helper.inspect_source(self.path, expected)
        self.path.unlink()
        with self.assertRaises(OSError):
            helper.inspect_source(self.path, expected)
        self.path.symlink_to(self.root / 'missing')
        with self.assertRaises(OSError):
            helper.inspect_source(self.path, expected)
        with self.assertRaises(ValueError):
            helper.inspect_source(self.root, expected)

    def test_mutation_during_read_and_path_replacement(self):
        for replacement in (False, True):
            self.path.write_bytes(b'if(x) expect(x);')
            expected = identity(self.path)
            original_read = os.read
            mutated = False
            def changing_read(fd, count):
                nonlocal mutated
                chunk = original_read(fd, count)
                if chunk and not mutated:
                    mutated = True
                    if replacement:
                        other = self.root / 'replacement'
                        other.write_bytes(chunk)
                        other.replace(self.path)
                    else:
                        self.path.write_bytes(b'if(x) return;')
                return chunk
            with mock.patch.object(helper.os, 'read', changing_read):
                with self.assertRaises(ValueError):
                    helper.inspect_source(self.path, expected)

    @unittest.skipUnless(shutil.which('awk'), 'awk required')
    def test_exact_production_lexer_differential(self):
        fn = function(SOURCE, 'conditional_assertion_hit_matches')
        lexer = fn[fn.index('    function executable_source'):fn.index('    NR < target')]
        rng = random.Random(59041)
        fragments = [b'abc', b'ex/**/pect(x)', b'/*', b'*/', b'//', b'"', b"'", b'`',
                     b'\\', b' ', b'assert', b'.should', b'if(x)', b'\t', b'\r']
        source = b'\n'.join(b''.join(rng.choice(fragments) for _ in range(12)) for _ in range(200))
        source += b'\n' + b'x' * 65537 + b'/*\n*/ expect(x);\n'
        self.path.write_bytes(source)
        result = subprocess.run(['awk', lexer + '\n{ print executable_source($0, 1) }', str(self.path)],
                                capture_output=True, timeout=10, check=True)
        python_rows = list(helper.executable_lines(source))
        if source.endswith(b'\n'):
            python_rows.pop()
        self.assertEqual(result.stdout, b'\n'.join(python_rows) + b'\n')

    @unittest.skipUnless(shutil.which('rg'), 'rg required')
    def test_original_classifier_accepted_candidates_survive(self):
        shell = 'scanner_rg() { ' + shlex.quote(shutil.which('rg')) + ' "$@"; }\n'
        scope_source = (ROOT / 'skills/e2e-reviewer/scripts/scope-source.sh').read_text()
        for name in ('run_source_lexer', 'source_executable_code'):
            shell += function(scope_source, name)
        for name in ('source_has_unresolved_test_import', 'source_binding_shadowed_at', 'conditional_assertion_hit_matches'):
            shell += function(SOURCE, name)
        controls = [
            (b'if(x) {\n' + b'\n'*39 + b'expect(x);\n}', 1, True),
            (b'if(x) {\n' + b'\n'*40 + b'expect(x);\n}', 1, False),
            (b'if(x) ex/**/pect(x);', 1, True),
            (b"import { test, expect as __STR__ } from 'custom-e2e';\nif(x) 'v'();", 2, True),
            (b"import { test, expect as check } from 'custom-e2e';\nif(x) check(x);", 2, True),
            (b'if(x) {}\nexpect(x);', 1, False),
            (b'/*\nif(x) expect(x);\n*/', 2, False),
            (b'if(x) assert.ok(x);', 1, True),
            (b'if(x) cy.get(x).should(x);', 1, True),
        ]
        for source, line, expected in controls:
            self.path.write_bytes(source)
            hit = str(self.path) + ':' + str(line) + ':if(x)'
            result = subprocess.run(['/bin/bash', '-p', '-c', shell + shlex.join(['conditional_assertion_hit_matches', hit])],
                                    capture_output=True, timeout=10)
            self.assertIn(result.returncode, (0, 1), result.stderr)
            self.assertEqual(result.returncode == 0, expected, source)
            if expected:
                self.assertTrue(helper.retain(source), source)


if __name__ == '__main__':
    unittest.main()
