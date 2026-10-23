// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { justifiedCoverage, applyJustified } from '../src/justified.mjs';

const file = '/source/example.spec.ts';
const covered = text => justifiedCoverage(Buffer.from(text), file).coverage.map(item => item.line);

test('only lexical nonempty pure-line markers cover the immediately next physical line', () => {
  assert.deepEqual(covered('// JUSTIFIED: delayed by design\npage.waitForTimeout(1);'), [2]);
  for (const marker of ['// JUSTIFIED:', '// JUSTIFIED:  ', '// NOT JUSTIFIED: no', '/* JUSTIFIED: no */',
    'const text = "// JUSTIFIED: no";', 'const text = `// JUSTIFIED: no`;', 'call(); // JUSTIFIED: trailing']) {
    assert.deepEqual(covered(marker + '\npage.waitForTimeout(1);'), [], marker);
  }
  assert.deepEqual(covered('// JUSTIFIED: valid\n// another comment\npage.waitForTimeout(1);'), [2]);
  assert.deepEqual(covered('const text = `\n// JUSTIFIED: template contents\n`;\npage.waitForTimeout(1);'), []);
  assert.deepEqual(covered('/*\n// JUSTIFIED: block contents\n*/\npage.waitForTimeout(1);'), []);
});

test('fluent continuation has one root, no intervening boundary and an eight-line lookback', () => {
  assert.deepEqual(covered('// JUSTIFIED: chain\ncy.get("button")\n  .click()\n  .wait(100);'), [2, 3, 4]);
  assert.deepEqual(covered('// JUSTIFIED: stops\ncy.get("button");\n.click();'), [2]);
  assert.deepEqual(covered('// JUSTIFIED: second root\nfirst()\nsecond()\n.click();'), [2]);
  assert.deepEqual(covered('// JUSTIFIED: blank\n\ncy.get("button")\n.click();'), [2]);
  const text = '// JUSTIFIED: bounded\nroot()\n' + '.step()\n'.repeat(8);
  assert.deepEqual(covered(text), [2, 3, 4, 5, 6, 7, 8, 9]);
});

test('evaluate/waitForFunction callback coverage stops at its brace and 24-line window', () => {
  for (const name of ['evaluate', 'waitForFunction']) {
    assert.deepEqual(covered(`// JUSTIFIED: callback\nawait page.${name}(() => {\n  work();\n});\nafter();`), [2, 3]);
    const text = `// JUSTIFIED: bounded\npage.${name}(() => {\n` + ' work();\n'.repeat(25) + '});';
    assert.deepEqual(covered(text), Array.from({ length: 24 }, (_, i) => i + 2));
  }
  assert.deepEqual(covered('// JUSTIFIED: not block scope\ntest("group", () => {\n  work();\n});'), [2]);
  assert.deepEqual(covered('// JUSTIFIED: not block scope\ndescribe("group", () => {\n  work();\n});'), [2]);
});

test('regex quotes, braces in call options and CRLF preserve lexical boundaries', () => {
  assert.deepEqual(covered('const rx = /["\']/;\n// JUSTIFIED: after regex\nwork();'), [3]);
  assert.deepEqual(covered('// JUSTIFIED: options\ncy.get("button", {timeout: 100})\n.click();'), [2, 3]);
  assert.deepEqual(covered('// JUSTIFIED: CRLF\r\nwork();\r\n'), [2]);
});

test('P1/P2 suppression is retained as metadata, P0 needs review, #7 is never suppressed', () => {
  const bytes = Buffer.from('// JUSTIFIED: observable boundary\nwork();\n');
  const make = (severity, patternId) => ({ file, line: 2, patternId, severity, disposition: 'confirmed', origin: 'ast' });
  const input = [make('P1', '#1'), make('P2', '#2'), make('P0', '#4f'), make('P0', '#7')];
  const original = structuredClone(input);
  const result = applyJustified(bytes, file, input);
  assert.deepEqual(input, original);
  assert.deepEqual(result.findings.map(item => [item.patternId, item.disposition]), [['#4f', 'justified-review'], ['#7', 'confirmed']]);
  assert.deepEqual(result.suppressed.map(item => item.patternId), ['#1', '#2']);
  assert.deepEqual(result.findings[0].justification, { line: 2, markerLine: 1, reason: 'observable boundary', kind: 'previous-line' });
  assert.equal(result.findings[1].justification, undefined);
  assert.equal(result.suppressed[0].justification.reason, 'observable boundary');
  assert.deepEqual(result.diagnostics, []);
});

test('unsupported lexical context preserves findings and reports diagnostics', () => {
  for (const text of ['// JUSTIFIED: no\nconst unterminated = `', '// JUSTIFIED: no\n/* unfinished', '// JUSTIFIED:\u00a0locale\nwork();']) {
    const finding = { file, line: 2, patternId: '#1', severity: 'P1' };
    const result = applyJustified(Buffer.from(text), file, [finding]);
    assert.deepEqual(result.findings, [finding]);
    assert.deepEqual(result.suppressed, []);
    assert.ok(result.diagnostics.length);
  }
  assert.throws(() => justifiedCoverage(Buffer.from([0xff]), file), /UTF-8/);
  const result = applyJustified(Buffer.from('// JUSTIFIED: yes\nwork();'), file, [{file: '/other.ts', line: 2, severity: 'P1', patternId: '#1'}]);
  assert.equal(result.diagnostics[0].code, 'invalid-finding-context');
  const outside = applyJustified(Buffer.from('work();'), file, [{ file, line: 2, severity: 'P1', patternId: '#1' }]);
  assert.equal(outside.diagnostics[0].code, 'invalid-finding-context');
});
