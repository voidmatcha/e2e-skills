#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Scope helper regressions; shell-wrapper checks use the frozen legacy oracle."""
import importlib.util
from pathlib import Path
import tempfile
import shutil
import subprocess
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.legacy_scanner_oracle import legacy_scanner_file

SCRIPT = Path(__file__).resolve().parents[2] / 'skills/e2e-reviewer/scripts/scope-graph.py'
spec = importlib.util.spec_from_file_location('scope_graph', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScopeGraphTests(unittest.TestCase):
    def test_depth_precedes_shared_visited_and_siblings_share_it(self):
        edges = {'root': ['n1', 'n32']}
        edges.update({f'n{i}': [f'n{i+1}'] for i in range(1, 33)})
        class Graph:
            def direct(self, node): return node == 'n33'
            def imports(self, node): return edges.get(node, [])
            def resolve(self, node, item): return [item]
        visited = set()
        self.assertFalse(module.walk(Graph(), 'root', visited, 0, lambda _: None))
        self.assertNotIn('n33', visited)
        edges['root'][-1] = 'n33'
        self.assertTrue(module.walk(Graph(), 'root', set(), 0, lambda _: None))

    def test_cycle_and_lazy_later_import(self):
        calls = []
        class Graph:
            def direct(self, node): return node == 'hit'
            def imports(self, node): return {'root': ['cycle', 'hit', 'unreachable'], 'cycle': ['root']}.get(node, [])
            def resolve(self, node, item):
                calls.append(item)
                if item == 'unreachable': raise AssertionError('eager resolution')
                return [item]
        self.assertTrue(module.walk(Graph(), 'root', set(), 0, lambda _: None))
        self.assertEqual(calls, ['cycle', 'root', 'hit'])

    def test_changed_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.ts'; path.write_text('old')
            witnesses = module.Witnesses({})
            witnesses.watch(str(path))
            path.write_text('new')
            with self.assertRaises(module.ScopeError): witnesses.validate()

    def test_new_candidate_fails_closed_via_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            witnesses = module.Witnesses({})
            witnesses.watch(str(Path(tmp) / 'missing.ts'))
            (Path(tmp) / 'missing.ts').write_text('new')
            with self.assertRaises(module.ScopeError): witnesses.validate()

    def test_parent_symlink_swap_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / 'a'; a.mkdir(); (a / 'x.ts').write_text('source')
            b = Path(tmp) / 'b'; b.mkdir(); (b / 'x.ts').write_text('source')
            link = Path(tmp) / 'link'; link.symlink_to(a, target_is_directory=True)
            witnesses = module.Witnesses({}); witnesses.watch(str(link / 'x.ts'))
            link.unlink(); link.symlink_to(b, target_is_directory=True)
            with self.assertRaises(module.ScopeError): witnesses.validate()

    def test_ancestor_witness_upgrade_retains_full_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / 'parent'; parent.mkdir()
            witnesses = module.Witnesses({})
            witnesses.watch(str(parent / 'missing.ts'))
            self.assertEqual(len(witnesses.data[str(parent)]), 3)
            witnesses.watch(str(parent))
            self.assertEqual(len(witnesses.data[str(parent)]), 6)
            (parent / 'new.ts').write_text('new')
            with self.assertRaises(module.ScopeError): witnesses.validate()

    def test_shell_wrapper_distinguishes_negative_from_interpreter_crash(self):
        scanner = legacy_scanner_file().read_text()
        start = scanner.index('scope_graph_call() {')
        end = scanner.index('\n}\n', start) + 3
        function = scanner[start:end]
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            fake = base / 'interpreter'
            for code, expected, error_marker in ((3, 1, False), (1, 2, True)):
                fake.write_text('#!/bin/sh\nexit ' + str(code) + '\n')
                fake.chmod(0o700)
                command = function + '\n' + \
                    'PYTHON3_BIN="$1"; SCANNER_TEMP_ROOT="$2"; SCANNER_DIR_REAL="$2"; ' + \
                    'PROJECT_ROOT_REAL="$2"; RG_BIN=/usr/bin/false; RG_RUNTIME_ERROR_FILE="$2/rg-errors"; ' + \
                    'scope_graph_call node visited 0'
                result = subprocess.run(['/bin/bash', '-p', '-c', command, 'scope-test', str(fake), str(base)], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual((base / 'scope-errors').exists(), error_marker)

    def test_unwritable_error_marker_aborts_parent_despite_later_validation_success(self):
        scanner = legacy_scanner_file().read_text()
        def function(name):
            start = scanner.index(name + '() {')
            end = scanner.index('\n}\n', start) + 3
            return scanner[start:end]
        functions = '\n'.join(function(name) for name in (
            'scope_graph_call', 'scope_graph_validate', 'scope_status',
            'abort_on_rg_error', 'abort_on_scope_signal'))
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ('in', 'out', 'rg-errors', 'scope-errors'):
                (base / name).touch()
            fake = base / 'interpreter'
            fake.write_text('#!/bin/sh\nfor arg in "$@"; do [ "$arg" = validate ] && exit 0; done\nexit 1\n')
            fake.chmod(0o700)
            command = functions + r'''
SCANNER_TEMP_ROOT="$1"; SCANNER_DIR_REAL="$1"; PROJECT_ROOT_REAL="$1"
SCOPE_STATE_DIR="$1"; RG_RUNTIME_ERROR_FILE="$1/rg-errors"
PYTHON3_BIN="$1/interpreter"; RG_BIN="$1/interpreter"
trap abort_on_scope_signal USR1
# Real kernel write failures without filling the machine's disk. Ignoring the
# file-size signal makes failed printf return, as ENOSPC does, so the parent
# scope-status conditional must not hide the missing error record.
trap '' XFSZ
ulimit -f 0
file_in_e2e_scope() { scope_graph_call "$1" visited 0; }
status="$(scope_status target)"
scope_graph_validate || exit 2
abort_on_rg_error
printf 'Summary: NORMAL\n'
'''
            result = subprocess.run(['/bin/bash', '-p', '-c', command, 'scope-test', str(base)], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn('Summary:', result.stdout)
            self.assertIn('scope graph failure could not be recorded', result.stderr)
            self.assertEqual((base / 'scope-errors').stat().st_size, 0)

    def test_corrupt_cache_is_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'cache.json'; cache.write_text('{invalid'); cache.chmod(0o600)
            with self.assertRaises(module.ScopeError): module.read_cache(str(cache), '/project')


class ScopeGraphCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='scope-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.project = self.base / 'project with spaces'
        self.project.mkdir()
        self.cache = self.base / 'cache.json'
        self.helper = SCRIPT.with_name('scope-source.sh')
        self.visited = self.base / 'visited'
        self.rg = shutil.which('rg')
        if not self.rg:
            self.skipTest('ripgrep is required for scope lexical integration')
        self.initialize_cache()

    def invoke(self, *arguments):
        return subprocess.run([
            sys.executable, '-I', '-B', str(SCRIPT), '--cache', str(self.cache),
            '--project', str(self.project), '--helper', str(self.helper),
            '--rg', self.rg, '--rg-errors', str(self.base / 'rg-errors'),
            '--errors', str(self.base / 'errors'), *arguments,
        ], capture_output=True, text=True, timeout=10)

    def initialize_cache(self):
        result = self.invoke('--init')
        self.assertEqual(result.returncode, 0, result.stderr)

    def query(self, source, depth=0, initial=''):
        self.visited.write_text(initial)
        return self.invoke(str(source), str(self.visited), str(depth))

    def test_real_chain_cold_warm_preserve_existing_visited(self):
        source = self.project / 'entry.ts'
        support = self.project / 'support.ts'
        source.write_text("import { test } from './support.js';\n")
        support.write_text("export { test } from '@playwright/test';\n")
        for _ in range(2):
            result = self.query(source, initial='already-visited\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.visited.read_text().splitlines(), ['already-visited', str(source), str(support)])
        support.write_text("export const test = {};\n")
        result = self.query(source)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('scope dependency changed', result.stderr)
        self.assertTrue((self.base / 'errors').read_text())

    def test_carriage_return_path_in_existing_visited_is_exact(self):
        source = self.project / 'entry\rname.ts'
        source.write_text("import { test } from '@playwright/test';\n")
        initial = str(source) + '\n'
        result = self.query(source, initial=initial)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(self.visited.read_bytes(), initial.encode())

    def test_missing_edge_added_after_negative_cache_rejected(self):
        source = self.project / 'entry.ts'
        source.write_text("import { test } from './missing';\n")
        self.assertEqual(self.query(source).returncode, 3)
        (self.project / 'missing.ts').write_text("export { test } from '@playwright/test';\n")
        self.assertEqual(self.query(source).returncode, 2)

    def test_deleted_cache_cannot_be_recreated_by_next_query(self):
        source = self.project / 'entry.ts'
        source.write_text("import { test } from '@playwright/test';\n")
        self.assertEqual(self.query(source).returncode, 0)
        self.cache.unlink()
        self.assertEqual(self.query(source).returncode, 2)

    def test_initialization_cannot_replace_existing_witnesses(self):
        source = self.project / 'entry.ts'
        source.write_text("import { test } from '@playwright/test';\n")
        self.assertEqual(self.query(source).returncode, 0)
        before = self.cache.read_bytes()
        self.assertEqual(self.invoke('--init').returncode, 2)
        self.assertEqual(self.cache.read_bytes(), before)

    def test_unrelated_historical_witness_still_fails_final_validation(self):
        first = self.project / 'first.ts'
        second = self.project / 'second.ts'
        for source in (first, second):
            source.write_text("import { test } from '@playwright/test';\n")
            self.assertEqual(self.query(source).returncode, 0)
        first.write_text('export const test = {};\n')
        # Eager global validation may reject earlier; lazy query validation
        # may proceed, but neither may lose the historical final check.
        self.assertIn(self.query(second).returncode, (0, 2))
        self.assertEqual(self.invoke('--validate').returncode, 2)

    def test_changed_helper_cannot_pass_final_validation(self):
        self.cache.unlink()
        copied = self.base / 'scope-source.sh'
        shutil.copyfile(self.helper, copied)
        self.helper = copied
        self.initialize_cache()
        source = self.project / 'entry.ts'
        source.write_text("import { test } from '@playwright/test';\n")
        self.assertEqual(self.query(source).returncode, 0)
        with copied.open('a') as stream:
            stream.write('\n# changed helper\n')
        self.assertEqual(self.invoke('--validate').returncode, 2)

    def test_deleted_cache_cannot_pass_final_validation(self):
        source = self.project / 'entry.ts'
        source.write_text("import { test } from '@playwright/test';\n")
        self.assertEqual(self.query(source).returncode, 0)
        self.cache.unlink()
        result = subprocess.run([
            sys.executable, '-I', '-B', str(SCRIPT), '--cache', str(self.cache),
            '--project', str(self.project), '--helper', str(SCRIPT.with_name('scope-source.sh')),
            '--rg', self.rg, '--rg-errors', str(self.base / 'rg-errors'),
            '--errors', str(self.base / 'errors'), '--validate',
        ], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_support_outside_scan_subdirectory_and_escape_rejected(self):
        nested = self.project / 'tests'; nested.mkdir()
        source = nested / 'entry.ts'
        support = self.project / 'support.ts'
        source.write_text("import { test } from '../support';\n")
        support.write_text("export { test } from '@playwright/test';\n")
        self.assertEqual(self.query(source).returncode, 0)
        self.cache.unlink()
        self.initialize_cache()
        outside = self.base / 'outside.ts'
        outside.write_text("export { test } from '@playwright/test';\n")
        source.write_text("import { test } from '../../outside';\n")
        self.assertEqual(self.query(source).returncode, 3)
        self.cache.unlink()
        self.initialize_cache()
        link = self.project / 'linked.ts'; link.symlink_to(outside)
        source.write_text("import { test } from '../linked';\n")
        self.assertEqual(self.query(source).returncode, 3)

    def test_depth_guard_does_not_mark_visited_or_read_source(self):
        missing = self.project / 'missing.ts'
        result = self.query(missing, depth=33, initial='existing\n')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(self.visited.read_text(), 'existing\n')


if __name__ == '__main__': unittest.main()
