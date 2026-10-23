#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Path fast paths preserve the original utility and physical-root contracts."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.legacy_scanner_oracle import legacy_scanner_file

SOURCE = legacy_scanner_file("scope-source.sh")
ENV = dict(os.environ, LC_ALL="C", LANG="C", PATH="/usr/bin:/bin:/usr/sbin:/sbin")
SPEC = importlib.util.spec_from_file_location('scope_graph', SOURCE.with_name('scope-graph.py'))
GRAPH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRAPH)

# Frozen utility-based oracle: intentionally independent of the optimized helpers.
ORACLE = r'''
source_relative_module_candidate_paths() {
  local f="$1" import_path="$2" module_path module_base
  module_path="$(dirname "$f")/$import_path"
  module_base="$module_path"
  case "$module_path" in
    *.js|*.jsx|*.mjs|*.cjs) module_base="${module_path%.*}" ;;
  esac
  printf '%s\n' \
    "$module_path" \
    "$module_base.ts" "$module_base.tsx" "$module_base.js" "$module_base.jsx" \
    "$module_base.mts" "$module_base.mjs" "$module_base.cts" "$module_base.cjs" \
    "$module_path/index.ts" "$module_path/index.tsx" \
    "$module_path/index.js" "$module_path/index.jsx" \
    "$module_path/index.mts" "$module_path/index.mjs" \
    "$module_path/index.cts" "$module_path/index.cjs"
}

resolve_relative_module_candidates() {
  local f="$1" import_path="$2" candidate candidate_dir candidate_real
  while IFS= read -r candidate; do
    [[ -f "$candidate" && ! -L "$candidate" ]] || continue
    candidate_dir=$(cd "$(dirname "$candidate")" 2>/dev/null && pwd -P) || continue
    candidate_real="$candidate_dir/$(basename "$candidate")"
    case "$candidate_real" in
      "$PROJECT_ROOT_REAL"/*) printf '%s\n' "$candidate_real" ;;
    esac
  done < <(source_relative_module_candidate_paths "$f" "$import_path")
}

'''


class ScopePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scope-paths-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "root"
        self.root.mkdir()
        (self.root / "real" / "deep").mkdir(parents=True)
        self.outside = self.root.parent / "outside"
        self.outside.mkdir()
        (self.root / "alias").symlink_to(self.root / "real" / "deep", target_is_directory=True)
        (self.root / "escape").symlink_to(self.outside, target_is_directory=True)
        for parent in (self.root, self.root / "real", self.root / "real" / "deep", self.outside):
            for name in ("target.ts", "target.js", "a b.ts", "line\nname.ts"):
                (parent / name).write_text("")
        (self.root / "target").mkdir()
        for extension in ("ts", "tsx", "js", "jsx", "mts", "mjs", "cts", "cjs"):
            (self.root / "target" / ("index." + extension)).write_text("")
        (self.root / "final.ts").symlink_to(self.root / "target.ts")
        (self.root / "dangling.ts").symlink_to(self.root / "missing.ts")

    def shell(self, body, arguments=(), oracle=False):
        definitions = ORACLE if oracle else 'source "$1";'
        result = subprocess.run(
            ["/bin/bash", "-p", "-c", definitions + '\nshift; ' + body,
             "scope-path-test", str(SOURCE), *map(str, arguments)],
            cwd=self.root, env=ENV, capture_output=True, timeout=10,
        )
        return result.returncode, result.stdout, result.stderr

    def compare(self, body, arguments):
        expected = self.shell(body, arguments, oracle=True)
        actual = self.shell(body, arguments)
        self.assertEqual(actual, expected)
        return actual[1]

    def candidates(self, source, imported):
        return self.compare('source_relative_module_candidate_paths "$1" "$2"',
                            (source, imported))

    def resolve(self, imported, source=None):
        return self.compare(
            'PROJECT_ROOT_REAL="$1"; resolve_relative_module_candidates "$2" "$3"',
            (self.root, source or self.root / "test.ts", imported),
        )

    def test_dirname_edge_paths_match_utilities(self):
        paths = ("", "file.ts", "/file.ts", "//file.ts", "///file.ts", "/", "//",
                 "a/file.ts", "a//file.ts", "a///file.ts", "a//b/file.ts",
                 "a/file.ts/", "a/", "a/b///", "a/./file.ts", "a/../file.ts",
                 "a b/tab\t.ts", "unicode-é/file.ts", "a\\b/c.ts",
                 "a\n/b.ts", "a/b\n.ts", "a/b.ts\n")
        for path in paths:
            with self.subTest(path=path):
                self.candidates(path, "./target")

    def test_leading_hyphen_preserves_utility_option_handling(self):
        # Removing the leading-hyphen fallback fails here on BSD dirname.
        for source in ("-a/file.ts", "--/file.ts", "--help/file.ts"):
            with self.subTest(source=source):
                self.candidates(source, "./target")

    def test_all_seventeen_candidates_keep_order_and_duplicates(self):
        prefix = str(self.root) + "/./target"
        output = self.candidates(self.root / "test.ts", "./target.ts")
        extensions = ("ts", "tsx", "js", "jsx", "mts", "mjs", "cts", "cjs")
        expected = ([prefix + ".ts"] +
                    [prefix + ".ts." + ext for ext in extensions] +
                    [prefix + ".ts/index." + ext for ext in extensions])
        self.assertEqual(output.decode().splitlines(), expected)
        output = self.candidates(self.root / "test.ts", "./target.js")
        expected = ([prefix + ".js"] + [prefix + "." + ext for ext in extensions] +
                    [prefix + ".js/index." + ext for ext in extensions])
        self.assertEqual(output.decode().splitlines(), expected)
        self.assertEqual(expected.count(prefix + ".js"), 2)
        self.assertEqual(self.resolve("./target.js").splitlines().count(
            os.fsencode(self.root / "target.js")), 2)

    def test_import_suffixes_slashes_and_newlines_preserve_raw_bytes(self):
        for imported in ("./target", "../target", "./target.jsx", "./target.mjs",
                         "./target.cjs", "./target/", "./a//target", "././target",
                         "./a b", "./line\nname", "./trailing\n", "./\n\nname"):
            with self.subTest(imported=imported):
                self.candidates(self.root / "test.ts", imported)
                self.resolve(imported)

    def test_logical_cd_and_symlink_parent_resolution_are_preserved(self):
        # cd defaults to logical traversal: alias/.. returns root, although the
        # preceding -f check traverses the symlink physically. Keep both steps.
        self.assertEqual(self.resolve("./alias/../target.ts"),
                         os.fsencode(self.root / "target.ts") + b"\n")
        self.assertEqual(self.resolve("./alias/target.ts"),
                         os.fsencode(self.root / "real" / "deep" / "target.ts") + b"\n")
        self.assertEqual(self.resolve("./target.ts", source="test.ts"),
                         os.fsencode(self.root / "target.ts") + b"\n")

    def test_outside_parent_and_final_symlinks_are_rejected(self):
        for imported in ("./escape/target", "./final", "./dangling", "./missing/target"):
            with self.subTest(imported=imported):
                self.assertEqual(self.resolve(imported), b"")

    def test_newline_read_and_nul_framing_remain_identical(self):
        body = r'''PROJECT_ROOT_REAL="$1"
while IFS= read -r value; do printf '%s\0' "$value"; done \
  < <(resolve_relative_module_candidates "$2" "$3")
printf '\0'
'''
        for imported in ("./line\nname", "./target\n", "./target\n./target",
                         "./target\n\n./target", "./target/"):
            with self.subTest(imported=imported):
                self.compare(body, (self.root, self.root / "test.ts", imported))

    def graph(self, helper=SOURCE):
        args = SimpleNamespace(helper=str(helper), project=str(self.root),
                               rg='/custom-ripgrep-wrapper', rg_errors=str(self.root / 'errors'))
        graph = GRAPH.Graph(args, {'nodes': {}, 'edges': {}, 'witnesses': {}})
        self.addCleanup(graph.close)
        return graph

    def test_python_candidates_match_independent_shell_oracle(self):
        graph = self.graph()
        self.assertTrue(graph.paired_paths)
        # A custom rg path disables the lexer, not this pure string operation.
        self.assertIsNone(graph.lexer)
        for source in ('/file.ts', 'a/b.ts', 'a//b/file.ts', 'a/../file.ts',
                       'a b/tab\t.ts', str(self.root / 'test.ts')):
            for imported in ('./target', '../target', './target.ts', './target.js',
                             './target.jsx', './target.mjs', './target.cjs',
                             './target/', './a//target', './alias/../target.ts'):
                with self.subTest(source=source, imported=imported):
                    expected = self.shell('source_relative_module_candidate_paths "$1" "$2"',
                                          (source, imported), oracle=True)
                    self.assertEqual(expected[0], 0)
                    with patch.object(graph, 'request', side_effect=AssertionError('unexpected fallback')):
                        actual = graph.candidate_paths(source, imported)
                    self.assertEqual(b''.join(os.fsencode(value) + b'\n' for value in actual), expected[1])

    def test_python_candidates_fall_back_on_unproved_paths(self):
        graph = self.graph()
        pairs = [(source, './target') for source in (
            '', 'file.ts', '//file.ts', 'a//file.ts', 'a/file.ts/', '-a/file.ts',
            'a\n/b.ts', 'unicode-é/file.ts', 'a/\udcff.ts')]
        pairs += [('a/file.ts', imported) for imported in (
            './line\nname', './café', './\udcff', 'package', '/absolute', './nul\0')]
        for source, imported in pairs:
            with self.subTest(source=source, imported=imported):
                with patch.object(graph, 'request', return_value=['fallback']) as request:
                    self.assertEqual(graph.candidate_paths(source, imported), ['fallback'])
                    request.assert_called_once_with('candidates', source, imported)

    def test_unknown_helper_keeps_original_candidate_request(self):
        helper = self.root / 'alternate.sh'
        helper.write_bytes(SOURCE.read_bytes() + b'\n# alternate helper\n')
        graph = self.graph(helper)
        self.assertFalse(graph.paired_paths)
        with patch.object(graph, 'request', return_value=['alternate']) as request:
            self.assertEqual(graph.candidate_paths('a/file.ts', './target'), ['alternate'])
            request.assert_called_once_with('candidates', 'a/file.ts', './target')

    def test_paired_helper_mutation_fails_before_candidate_use(self):
        helper = self.root / 'paired.sh'
        helper.write_bytes(SOURCE.read_bytes())
        graph = self.graph(helper)
        self.assertTrue(graph.paired_paths)
        helper.write_bytes(helper.read_bytes() + b'\n# mutated\n')
        with self.assertRaisesRegex(GRAPH.ScopeError, 'scope dependency changed'):
            graph.resolve(str(self.root / 'test.ts'), './target')

    def test_python_enumeration_preserves_resolver_and_ordered_witnesses(self):
        graph = self.graph()
        node = str(self.root / 'test.ts')
        for imported in ('./target.js', './alias/../target.ts', './alias/target.ts', './missing'):
            paths = graph.candidate_paths(node, imported)
            expected = self.resolve(imported).splitlines()
            with patch.object(graph, 'request', wraps=graph.request) as request:
                with patch.object(graph.witnesses, 'watch', wraps=graph.witnesses.watch) as watch:
                    actual = graph.resolve(node, imported)
            self.assertEqual(list(map(os.fsencode, actual)), expected)
            request.assert_called_once_with('resolve', node, imported)
            self.assertEqual([call.args[0] for call in watch.call_args_list],
                             [str(SOURCE)] + paths + paths)

    def test_candidate_created_during_resolution_fails_post_witness(self):
        graph = self.graph()
        node = str(self.root / 'test.ts')
        def changed(operation, source, imported):
            self.assertEqual(operation, 'resolve')
            (self.root / 'new.ts').write_text('export {};')
            return []
        with patch.object(graph, 'request', side_effect=changed):
            with self.assertRaisesRegex(GRAPH.ScopeError, 'scope dependency changed'):
                graph.resolve(node, './new')


if __name__ == "__main__":
    unittest.main()
