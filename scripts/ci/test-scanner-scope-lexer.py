#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import sys
sys.dont_write_bytecode = True
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import importlib.util
import shutil
import signal
import threading
from types import SimpleNamespace
from unittest import mock

BASE = Path(__file__).resolve().parents[2] / 'skills/e2e-reviewer/scripts'
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
lexer = load('lexer', BASE/'scope-lexer.py')
def resolve_rg():
    configured = os.environ.get('E2E_SMELL_RG_BIN')
    paths = [configured] if configured else ['/opt/homebrew/bin/rg','/usr/local/bin/rg','/usr/bin/rg','/bin/rg']
    for item in paths:
        path = Path(item)
        if path.is_absolute() and path.is_file() and os.access(path, os.X_OK): return str(path)
    raise RuntimeError('Set E2E_SMELL_RG_BIN to an absolute executable ripgrep path')
RG = resolve_rg()
CASES = [b'', b'const x = 1;\n', b"import {test} from '@playwright/test';",
 b"import {test} from '\\u0040playwright/test';", b"export {test} from `@playwright/test`;",
 b"// import {test} from '@playwright/test';\nimport './a';",
 b"const x = /import from '@playwright\\/test'/; import './b';",
 b"const x = `template ${require('@playwright/test')} tail`;",
 b"import {test} from '@play\\\nwright/test'; import './a\\\nb';",
 b"const a = 'one\ntwo'; /* block\n */ export {x} from '../a';",
 b"import x from './a'; import y from './b'; require('../z');",
 b"import x from './__E2E_STR__b'; import('./c');",
 b"require('\\x40playwright/test'); require('\\u{40}playwright/test');",
 b"require('\\u{}playwright/test'); require('\\8playwright/test');",
 b"if (x) /a[b/]c/.test(x); export * from './x';",
 b"const x = `outer ${`inner ${require('@playwright/test')}`} tail`;",
 b"import {x}\r\nfrom './a';\r\n",
]


# Deliberately include malformed JavaScript: equivalence is to the shell
# state machines, not a standards-compliant JavaScript parser.
for escaped in (r'\u0040', r'\u{40}', r'\x40', r'\u040', r'\u004G', r'\u{}',
                r'\u{xyz}', r'\u{000040}', r'\u{100000}', r'\x4', r'\xGG',
                r'\0', r'\07', r'\8', r'\n', r'\t', r'\v', r'\@'):
    CASES.append(("require('"+escaped+"playwright/test'); import './after';").encode())
for prefix in ('return ', 'throw ', 'case ', 'yield ', 'x => ', 'if (x) ',
               'while (x) ', 'for (;;) ', 'with (x) ', 'x / ', 'x = ', ''):
    CASES.append((prefix+"/[/\\\\]import('./phantom')/g; import './after';").encode())
for ref in ('./a', '../a', './a\\b', './a__E2E_STR__b', './a__E2E_END__b',
            './a; import __E2E_STR__../b', './a\rb', './a\tb'):
    for form in ("import X from '%s';", "require('%s');", "import('%s');", "import '%s';"):
        CASES.append((form % ref).encode())
CASES.extend([
 b"import/*gap*/x/*gap*/from/*gap*/'./a';",
 b"import x from './a' // tail\nexport * from '../b'",
 b"const x = 'open\\\nclose'; require('./a');",
 b"const x = `literal ${ /* comment } */ require('./a') } tail`;",
 b"const x = `literal ${ { key: `nested ${require('./b')}` } } tail`;",
 b"const x = `unclosed ${ 'quote }';\nrequire('./a')",
 b"/* open\n comment */ import x from './a'; /* no close",
 b"// one\\\nimport x from './a';",
 b"const x = /[a\\/\n]b/; import './a';",
 b"const x = /unterminated\nimport './a';",
 b"fooimport X from './a'; rexport X from './b'; myrequire('./c');",
 b"import x from './a' import y from './b' export z from './c'",
 b"import x from './a'; from './b'; import y from './c'",
 b"import x from `./a${require('./b')}`;",
 b"import x from './a\\'; import y from './b';",
 b"import x from '\\u002e/a'; require(`../b`);",
 b"require('./x');\vimport\f'./y';\rrequire\t('../z');",
])

class Equivalence(unittest.TestCase):
    def test_tiny_shell_differential(self):
        for locale in ('C', 'C.UTF-8'):
            with self.subTest(locale=locale): self.shell_differential(locale)

    def shell_differential(self, locale):
        with tempfile.TemporaryDirectory(prefix='lexer-',dir=str(Path('/tmp').resolve())) as tmp:
            path = Path(tmp)/'entry.ts'
            for source in CASES:
                with self.subTest(source=source):
                    path.write_bytes(source)
                    script = '''source "$1"
scanner_rg() { "$RG_BIN" "$@"; }
source_executable_code "$2" @playwright/test
'''
                    result = subprocess.run(['/bin/bash','-p','-c',script,'bash',str(BASE/'scope-source.sh'),str(path)],env={'PATH':'/usr/bin:/bin','LC_ALL':locale,'RG_BIN':RG},capture_output=True,check=True)
                    self.assertEqual(result.stdout,lexer.executable(source).encode('latin1'))
                    script = '''source "$1"
scanner_rg() { "$RG_BIN" "$@"; }
if source_has_playwright_module_reference "$2"; then printf '1\\n'; else printf '0\\n'; fi
source_relative_module_references "$2"
'''
                    result = subprocess.run(['/bin/bash','-p','-c',script,'bash',str(BASE/'scope-source.sh'),str(path)],env={'PATH':'/usr/bin:/bin','LC_ALL':locale,'RG_BIN':RG},capture_output=True)
                    lines = result.stdout.decode().split('\n')
                    if lines[-1] == '': lines.pop()
                    self.assertEqual(lexer.metadata(source, allow_positive_for_differential=True),(lines[0]=='1',lines[1:]))
    def test_unproved_transport_falls_back(self):
        for source in (b'\0',b'\xff',b'x'*32769,b"require('@playwright/test')"):
            with self.assertRaises(lexer.Fallback): lexer.metadata(source)


class DenseInputBudget(unittest.TestCase):
    def test_dense_inputs_fall_back_within_subprocess_budget(self):
        # A hung regex cannot hang CI: the child has a generous hard deadline.
        # Assert behavior, not host-dependent millisecond performance.
        program = r"""
import importlib.util, sys
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('scope_lexer', sys.argv[1])
lexer = importlib.util.module_from_spec(spec); spec.loader.exec_module(lexer)
cases = [
    (b'import '*4681, 'dense module tokens'),
    (b'/ '*16384, 'dense slash tokens'),
    (b'im/**/port '*32 + b'import '*33, 'dense executable module tokens'),
    (b'im/**/port '*31 + b'import '*34 + b" require('@playwright/test')", 'dense executable module tokens'),
]
for source, reason in cases:
    try: lexer.metadata(source)
    except lexer.Fallback as error:
        assert reason in str(error), str(error)
    else: raise AssertionError('dense input did not fall back')
source = b'import '*64
source += b'x'*(32768-len(source))
assert lexer.metadata(source) == (False, [])
assert lexer.metadata(b'/ '*64) == (False, [])
print('dense fallback and 64-token boundaries passed')
"""
        result = subprocess.run([sys.executable,'-I','-B','-c',program,str(BASE/'scope-lexer.py')],
                                capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('64-token boundaries passed', result.stdout)


# scan.sh provenance lexers that carry their own awk program, with the
# arguments after the source path that make each one reach that program.
SCAN_PROVENANCE_LEXERS = (
    ('source_has_unresolved_test_import', ()),
    ('source_imports_playwright_test_binding', ('test',)),
    ('source_imports_playwright_namespace_binding', ('pw',)),
    ('source_imports_playwright_expect_binding', ('expect',)),
    ('source_imports_relative_binding', ('test',)),
    ('source_relative_module_references_for_binding', ('test',)),
    ('source_relative_module_references_for_named_binding', ('check', 'expect')),
    ('source_relative_binding_lineage_edges', ('test',)),
)


def scan_function(name):
    scanner = (BASE/'scan.sh').read_text()
    start = scanner.index('\n' + name + '() {\n') + 1
    return scanner[start:scanner.index('\n}\n', start) + 3]


class LexerFailure(unittest.TestCase):
    """A failed lexer awk is a recorded runtime failure, never a clean negative."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='lexer-failure-', dir=str(Path('/tmp').resolve()))
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.errors = self.base/'errors'
        self.errors.write_bytes(b'')

    # scan.sh runs under `set -uo pipefail`. A caller may also start it with
    # SIGPIPE inherited as ignored, where awk reports a closed pipe as an
    # ordinary write error (exit 2) instead of dying from SIGPIPE (141).
    MODES = {
        'plain': (False, False),
        'pipefail': (True, False),
        'pipefail, SIGPIPE ignored': (True, True),
    }

    def run_shell(self, script, path, pipefail=False, sigpipe_ignored=False, timeout=60):
        prelude = 'source "$1"\nscanner_rg() { "$RG_BIN" "$@"; }\n'
        if pipefail:
            prelude = 'set -uo pipefail\n' + prelude

        def ignore_sigpipe():
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)

        return subprocess.run(['/bin/bash', '-p', '-c', prelude + script, 'bash', str(BASE/'scope-source.sh'), str(path)],
                              env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'RG_BIN': RG,
                                   'RG_RUNTIME_ERROR_FILE': str(self.errors)},
                              capture_output=True, timeout=timeout,
                              preexec_fn=ignore_sigpipe if sigpipe_ignored else None,
                              restore_signals=not sigpipe_ignored)

    def assert_awk_failures(self, count):
        records = self.errors.read_text().splitlines()
        self.assertEqual(len(records), count, records)
        for record in records:
            self.assertRegex(record, r'^awk [1-9][0-9]*$')

    def test_scope_source_lexers_record_unreadable_source(self):
        script = '''if source_has_playwright_module_reference "$2"; then printf '1\\n'; else printf '0\\n'; fi
source_relative_module_references "$2"
'''
        for mode, (pipefail, sigpipe_ignored) in self.MODES.items():
            with self.subTest(mode=mode):
                self.errors.write_bytes(b'')
                result = self.run_shell(script, self.base/'missing.spec.ts', pipefail, sigpipe_ignored)
                self.assertEqual(result.stdout, b'0\n')
                self.assertEqual(result.stderr, b'')
                self.assert_awk_failures(2)

    def test_scan_provenance_lexers_record_unreadable_source(self):
        # Silence the shared lexer so each record can only come from the
        # function's own awk program.
        functions = ''.join(scan_function(name) for name, _ in SCAN_PROVENANCE_LEXERS)
        functions += 'source_executable_code() { :; }\n'
        for name, arguments in SCAN_PROVENANCE_LEXERS:
            with self.subTest(function=name):
                self.errors.write_bytes(b'')
                call = ' '.join((name, '"$2"') + arguments)
                result = self.run_shell(functions + call + ' >/dev/null\n', self.base/'missing.spec.ts')
                self.assertEqual(result.stderr, b'')
                self.assert_awk_failures(1)

    def test_reader_that_stops_early_is_not_a_lexer_failure(self):
        # rg -q and head stop reading at their first answer. The rest of a
        # large lexer output then meets a closed pipe, which is not an awk
        # failure and must not abort the scan, whether awk dies from SIGPIPE
        # or, with SIGPIPE ignored, exits on the write error.
        path = self.base/'large.spec.ts'
        path.write_bytes(b"import { test } from '@playwright/test';\n" +
                         b"import './relative';\n" * 20000)
        verdict = '''if source_has_playwright_module_reference "$2"; then printf '1\\n'; else printf '0\\n'; fi
'''
        script = '''source_executable_code "$2" | head -n 1
source_relative_module_references "$2" | head -n 1
source_has_unresolved_test_import "$2" && printf 'unresolved\\n'
source_relative_binding_lineage_edges "$2" test | head -n 1 >/dev/null
'''
        functions = scan_function('source_has_unresolved_test_import') + \
            scan_function('source_relative_binding_lineage_edges')
        for mode, (pipefail, sigpipe_ignored) in self.MODES.items():
            with self.subTest(mode=mode):
                self.errors.write_bytes(b'')
                if pipefail:
                    # Under pipefail a Boolean verdict on a large source still
                    # depends on pipe transport, as it did before failures were
                    # recorded; only the failure record is pinned here.
                    result = self.run_shell(functions + script, path, pipefail, sigpipe_ignored)
                    self.assertEqual(result.stdout, b'import { test } from ;\n./relative\n')
                else:
                    result = self.run_shell(functions + verdict + script, path)
                    self.assertEqual(result.stdout, b'1\nimport { test } from ;\n./relative\n')
                    self.assertEqual(result.stderr, b'')
                self.assertNotIn(b'awk', result.stderr)
                self.assert_awk_failures(0)

    def test_reader_that_stops_early_ends_the_lexer_early(self):
        # The lexer streams its output. Once head has its line, the next lexer
        # write meets the closed pipe and ends awk before it reads the rest of
        # the source. This FIFO never reaches end of input, so a lexer that
        # buffered its whole output before writing would hang here.
        fifo = self.base/'streaming.spec.ts'
        os.mkfifo(fifo)
        done = threading.Event()

        def feed():
            descriptor = os.open(fifo, os.O_WRONLY)
            try:
                chunk = b"import './relative';\n" * 4096
                for _ in range(64):
                    os.write(descriptor, chunk)
            except BrokenPipeError:
                pass
            finally:
                done.wait(120)
                os.close(descriptor)

        writer = threading.Thread(target=feed, daemon=True)
        writer.start()
        try:
            result = self.run_shell('source_executable_code "$2" | head -n 1\n', fifo, pipefail=True, timeout=60)
        finally:
            done.set()
            writer.join(10)
        self.assertEqual(result.stdout, b'import ;\n')
        self.assert_awk_failures(0)


class GraphGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='lexer-guard-', dir=str(Path('/tmp').resolve()))
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        for name in ('scope-graph.py','scope-source.sh','scope-lexer.py'):
            shutil.copyfile(BASE/name, self.base/name)
        self.engine = load('scope_graph_guards', self.base/'scope-graph.py')
        self.node = self.base/'source.ts'; self.node.write_text("import './relative';\n")
        self.args = SimpleNamespace(helper=str(self.base/'scope-source.sh'),project=str(self.base),rg=RG,rg_errors=str(self.base/'errors'))
        env = dict(os.environ); env.pop('E2E_SMELL_RG_BIN', None); env['LC_ALL'] = 'C'
        self.environment = mock.patch.dict(os.environ, env, clear=True)
        self.environment.start(); self.addCleanup(self.environment.stop)

    def graph(self):
        graph = self.engine.Graph(self.args, {'version':1,'project':str(self.base),'nodes':{},'edges':{},'witnesses':{}})
        self.addCleanup(graph.close)
        return graph

    def test_negative_eager_imports_without_helper(self):
        graph = self.graph(); self.assertIsNotNone(graph.lexer)
        with mock.patch.object(graph, 'request', side_effect=AssertionError('unexpected helper')):
            self.assertFalse(graph.direct(str(self.node)))
            self.assertEqual(graph.imports(str(self.node)), ['./relative'])
        graph.witnesses.validate()

    def test_ineligible_source_uses_original_request(self):
        for source in (b"require('@playwright/test')", b'// \xff', b'x'*32769):
            with self.subTest(source=source[:40]):
                self.node.write_bytes(source); graph = self.graph()
                with mock.patch.object(graph, 'request', return_value=['0']) as request:
                    self.assertFalse(graph.direct(str(self.node)))
                    request.assert_called_once_with('direct',str(self.node))

    def test_explicit_rg_or_unsupported_locale_disables(self):
        for updates in ({'E2E_SMELL_RG_BIN':RG},{'LC_ALL':'en_US.UTF-8'}):
            with mock.patch.dict(os.environ,updates): self.assertIsNone(self.graph().lexer)
        self.args.rg = str(self.base/'wrapper-rg')
        self.assertIsNone(self.graph().lexer)

    def test_changed_helper_disables(self):
        with Path(self.args.helper).open('a') as stream: stream.write('\n# wrapper\n')
        self.assertIsNone(self.graph().lexer)

    def test_source_mutation_after_fast_read_fails_validation(self):
        graph = self.graph(); self.assertFalse(graph.direct(str(self.node)))
        self.node.write_text('changed source')
        with self.assertRaises(self.engine.ScopeError): graph.witnesses.validate()

    def test_lexer_module_mutation_fails_validation(self):
        graph = self.graph(); self.assertIsNotNone(graph.lexer)
        with (self.base/'scope-lexer.py').open('a') as stream: stream.write('\n# mutation\n')
        with self.assertRaises(self.engine.ScopeError): graph.witnesses.validate()

    def test_symlink_source_rejected(self):
        graph = self.graph(); link = self.base/'link.ts'; link.symlink_to(self.node)
        with self.assertRaises((self.engine.ScopeError, OSError)): graph.direct(str(link))

if __name__ == '__main__': unittest.main()
