// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';
import { applyJustified, justifiedCoverage } from '../src/justified.mjs';

const original = fileURLToPath(new URL('../../../scripts/ci/test-scanner-try-catch-v1.py', import.meta.url));
const extracted = spawnSync('python3', ['-c', [
  'import ast,json,sys',
  'tree=ast.parse(open(sys.argv[1],encoding="utf-8").read())',
  'header=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="SPEC_HEADER" for t in n.targets))',
  'fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=="test_flags_try_after_apostrophe_in_jsx_text")',
  'call=next(n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="scan")',
  'fixtures={ast.literal_eval(k):header+ast.literal_eval(v.right) for k,v in zip(call.args[0].keys,call.args[0].values)}',
  'print(json.dumps(fixtures))',
].join('\n'), original], { encoding: 'utf8', timeout: 10000 });
assert.ifError(extracted.error);
assert.equal(extracted.status, 0, extracted.stderr);
const fixture = JSON.parse(extracted.stdout);
const file = '/source/example.spec.tsx';
const finding = line => ({ file, line, patternId: '#9', severity: 'P1', disposition: 'confirmed' });
const coverage = text => justifiedCoverage(Buffer.from(text), file);

test('original apostrophe JSX fixture has no lexical diagnostic and keeps its #3 candidate', () => {
  const [name, text] = Object.entries(fixture)[0];
  assert.equal(name, 'jsx-apostrophe.spec.tsx');
  const hit = { file: name, line: 8, severity: 'P0', patternId: '#3', disposition: 'candidate' };
  const result = applyJustified(Buffer.from(text), name, [hit]);
  assert.deepEqual(result, { findings: [hit], suppressed: [], diagnostics: [] });
});

test('JSX text quotes, apparent comments and markers cannot change JavaScript suppression', () => {
  for (const extension of ['tsx', 'jsx']) {
    const text = [
      'const view = <section>',
      'Don\'t "quote" `prose` /* unclosed comment-looking text',
      '// JUSTIFIED: this is visible JSX prose',
      '{page.waitForTimeout(1)}',
      '</section>;',
      'page.waitForTimeout(2);',
      '// JUSTIFIED: actual JS comment',
      'page.waitForTimeout(3);',
    ].join('\n');
    const filename = '/source/prose.' + extension;
    const hits = [4, 6, 8].map(line => ({ ...finding(line), file: filename }));
    const result = applyJustified(Buffer.from(text), filename, hits);
    assert.deepEqual(result.diagnostics, []);
    assert.deepEqual(result.findings.map(f => f.line), [4, 6]);
    assert.deepEqual(result.suppressed.map(f => f.line), [8]);
  }
});

test('JSX attributes and embedded JavaScript retain string, template, regex and real-comment guards', () => {
  const text = [
    'const view = <section title="// JUSTIFIED: attribute" data-label={"Don\'t"}>',
    '{`',
    '// JUSTIFIED: template content',
    '`}',
    '{/["\']/ .test(value) && "// JUSTIFIED: string content"}',
    '{/*',
    '// JUSTIFIED: block comment content',
    '*/}',
    '{(() => {',
    '// JUSTIFIED: real JS inside JSX expression',
    'page.waitForTimeout(1);',
    'return null;',
    '})()}',
    '</section>;',
    'page.waitForTimeout(2);',
  ].join('\n');
  const result = applyJustified(Buffer.from(text), file, [finding(11), finding(15)]);
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.suppressed.map(f => f.line), [11]);
  assert.deepEqual(result.findings.map(f => f.line), [15]);
  assert.deepEqual(coverage(text).coverage.map(f => f.line), [11]);
});

test('masking preserves physical CRLF lines and UTF-16 positions around astral JSX prose', () => {
  const text = 'const view = <p>😀 Don\'t\r\n/* prose</p>;\r\n// JUSTIFIED: exact next line\r\npage.waitForTimeout(1);\r\n';
  const result = coverage(text);
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.coverage.map(f => [f.line, f.markerLine]), [[4, 3]]);
});

test('JSX parse errors preserve findings and never enable suppression', () => {
  for (const text of [
    '// JUSTIFIED: no\nconst view = <p>unclosed;',
    '// JUSTIFIED: no\nconst view = <p>{"unterminated}</p>;',
    '// JUSTIFIED: no\nconst view = <p title="unterminated>text</p>;',
    '// JUSTIFIED: no\nconst view = <p>{`unterminated}</p>;',
    '// JUSTIFIED: no\nconst view = <p>{/* unterminated}</p>;',
  ]) {
    const hit = finding(2), result = applyJustified(Buffer.from(text), file, [hit]);
    assert.deepEqual(result.findings, [hit], text);
    assert.deepEqual(result.suppressed, [], text);
    assert.ok(result.diagnostics.some(d => d.code === 'parse-invalid'), text);
  }
});

test('non-JSX files retain the existing lexical diagnostic rather than guessing JSX syntax', () => {
  const text = Buffer.from("const view = <p>Don't panic</p>;");
  for (const name of ['/source/prose.ts', '/source/prose.js']) {
    assert.ok(justifiedCoverage(text, name).diagnostics.some(d => d.code === 'unterminated-lexical-context'));
  }
});
