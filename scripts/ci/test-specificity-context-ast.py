#!/usr/bin/env python3
"""Apache-2.0. Optional pinned-parser integration; no downloads or target execution."""
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import json
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ast_replay', ROOT / 'scripts/evals/replay-specificity-context-ast.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def main():
    contract = {'source_sha256': {}, 'context_completeness_proven': False, 'evaluation_allowed': False,
                'version': 'typescript-context-v1', 'parser_version': '6.0.3',
                'limitations': ['static-bindings-do-not-prove-execution-or-postconditions', 'staged-files-not-whole-repository', 'configuration-not-executed'],
                **{k: [] for k in ('imports', 'calls', 'exports', 'configs', 'unresolved')}}
    M.validate_report(contract, {})
    for key, value in [('evaluation_allowed', True), ('context_completeness_proven', True),
                       ('source_sha256', {'a': 'bad'}), ('version', 'other'), ('parser_version', 'other'),
                       ('limitations', []), ('calls', 'invalid')]:
        try:
            M.validate_report({**contract, key: value}, {})
        except ValueError:
            pass
        else:
            raise AssertionError('invalid AST contract accepted: ' + key)
    print('AST wrapper contract: pass')
    parser = os.environ.get('E2E_SPECIFICITY_TYPESCRIPT')
    if not parser:
        print('SKIP AST integration: set E2E_SPECIFICITY_TYPESCRIPT to trusted TypeScript 6.0.3 lib/typescript.js')
        return
    node = os.environ.get('E2E_SPECIFICITY_NODE') or shutil.which('node')
    assert node, 'Node required for explicit AST integration'
    files = {
        'tests/helper.ts': "export function login() {}\nexport function unused() {}",
        'tests/barrel.ts': "export { login as authenticate } from './helper';",
        'tests/a.spec.ts': "import { authenticate as signIn } from './barrel';\nsignIn();\nconst s = `fakeCall(); import('./fake')`;\nfunction local(signIn: () => void) { signIn(); }",
        'playwright.config.ts': "import { defineConfig as config } from '@playwright/test';\nexport default config({testDir: 'tests', projects: [{name:'setup'}, {name:'browser', dependencies:['setup'], teardown:'cleanup'}, {name:'cleanup'}]});",
    }
    r = M.analyze(files, parser, node)
    assert not r['context_completeness_proven'] and not r['evaluation_allowed']
    calls = [c for c in r['calls'] if c['path'] == 'tests/a.spec.ts']
    assert len(calls) == 2, calls
    assert calls[0]['declaration']['path'] == 'tests/helper.ts', calls
    assert calls[1]['declaration']['path'] == 'tests/a.spec.ts', 'shadowed parameter must not bind to import'
    assert calls[0]['execution_proven'] is False
    assert r['staged_reverse_imports']['tests/helper.ts'][0]['path'] == 'tests/barrel.ts'
    assert any(k.startswith('tests/helper.ts:') for k in r['staged_reverse_call_bindings'])
    assert r['configs'][0]['declarations_resolved']
    assert r['configs'][0]['edges'] == [
        {'project': 'browser', 'dependency': 'setup', 'kind': 'setup'},
        {'project': 'browser', 'dependency': 'cleanup', 'kind': 'teardown'}]
    assert r == M.analyze(dict(reversed(list(files.items()))), parser, node)
    for config, reason in [
        ("export default {projects:[{name:'a', dependencies:['missing']}]}", 'missing-project-dependency'),
        ("export default {projects:[{name:'a', dependencies:['a']}]}", 'project-dependency-cycle'),
        ("export default {...process.env}", 'spread-method-or-computed-config'),
        ("export default {globalSetup: process.env.SETUP}", 'globalSetup:nonliteral-expression'),
        ("export default {projects:[{name:'a'}, {name:'a'}]}", 'missing-or-duplicate-project-name'),
    ]:
        out = M.analyze({'playwright.config.ts': config}, parser, node)
        assert reason in [u['reason'] for u in out['unresolved']], out
        assert not out['context_completeness_proven']
    missing = M.analyze({'a.ts': "import { f } from './absent'; f();"}, parser, node)
    assert any(u['reason'] == 'unstaged-module' for u in missing['unresolved'])
    broken = M.analyze({'a.ts': 'export function {'}, parser, node)
    assert any(u['reason'] == 'syntax-error' for u in broken['unresolved'])
    ambiguous = M.analyze({'a.ts': "import './b';", 'b.ts': '', 'b.js': ''}, parser, node)
    assert any(u['reason'] == 'ambiguous-module' for u in ambiguous['unresolved'])
    regex = M.analyze({'playwright.config.ts': "export default {projects:[{name:'setup',testMatch:/setup\\.ts/}, {name:'test',dependencies:['setup']}]};"}, parser, node)
    assert regex['configs'][0]['projects'][0]['testMatch']['kind'] == 'regex-literal'
    assert regex['configs'][0]['declarations_resolved'] and not regex['configs'][0]['execution_proven']
    type_only = M.analyze({'a.ts': "import type { H } from './helper'; export type { H } from './helper';", 'helper.ts': 'export interface H {}'}, parser, node)
    assert all(r['type_only'] for r in type_only['imports']) and not type_only['staged_reverse_imports']
    bad_setup = M.analyze({'playwright.config.ts': "export default {globalSetup:'./missing.ts'};"}, parser, node)
    assert not bad_setup['configs'][0]['declarations_resolved']
    type_config = M.analyze({'playwright.config.ts': "import type {defineConfig} from '@playwright/test'; export default defineConfig({});"}, parser, node)
    assert not type_config['configs']
    good_setup = M.analyze({'playwright.config.ts': "export default {globalSetup:'./setup.ts'};", 'setup.ts': 'export default function setup() {}'}, parser, node)
    assert good_setup['configs'][0]['declarations_resolved']
    for bad in ({'../escape.ts': ''}, {'a.ts': 'x' * 500001}, {'a.ts': 'f();' * 5001}):
        try:
            M.analyze(bad, parser, node)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid input accepted')
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        sentinel = base / 'executed'
        M.analyze({'a.ts': f"require('node:fs').writeFileSync({json.dumps(str(sentinel))}, 'bad');"}, parser, node)
        assert not sentinel.exists(), 'target code executed'
        source, output = base / 'source', base / 'output'
        staged = source / 'sources' / 'case'
        staged.mkdir(parents=True)
        (staged / 'a.ts').write_text('export function f() {}')
        intake = {'cases': [{'id': 'case', 'repository': 'fixture/repo', 'commit': 'a' * 40,
                             'source_sha256': {'a.ts': M.sha((staged / 'a.ts').read_bytes())}}]}
        (source / 'context-report.json').write_text(json.dumps(intake))
        argv = ['replay', '--source', str(source), '--output', str(output), '--typescript', parser, '--node', node]
        with mock.patch.object(sys, 'argv', argv):
            M.main()
        assert json.loads((output / 'ast-context-report.json').read_text())['model_calls'] == 0
        with mock.patch.object(sys, 'argv', argv):
            try:
                M.main()
            except ValueError:
                pass
            else:
                raise AssertionError('existing output overwritten')
        argv[argv.index('--output') + 1] = str(base / 'tampered')
        (staged / 'a.ts').write_text('changed')
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(M, 'analyze', side_effect=AssertionError('parser must not run')):
            try:
                M.main()
            except ValueError as e:
                assert 'hash mismatch' in str(e)
            else:
                raise AssertionError('tampered input accepted')
        for cases in ([], [intake['cases'][0], intake['cases'][0]]):
            (source / 'context-report.json').write_text(json.dumps({'cases': cases}))
            with mock.patch.object(sys, 'argv', argv):
                try:
                    M.main()
                except ValueError as e:
                    assert 'nonempty unique' in str(e)
                else:
                    raise AssertionError('empty or duplicate case replay accepted')
    print('AST integration: alias/reexport binding, shadowing, inert strings, project dependencies, unknowns and budgets passed')


if __name__ == '__main__':
    main()
