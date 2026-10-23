// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { justifiedCoverage, applyJustified } from '../src/justified.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
const scanner = legacyOracleFile();
const source = fs.readFileSync(scanner, 'utf8');
const start = source.indexOf('_justified_lines_in_file() {');
const end = source.indexOf('\nJUSTIFIED_CACHE_KEYS=()', start);
assert.ok(start >= 0 && end > start, 'legacy helper extraction boundary');
const helper = source.slice(start, end);
const env = { ...process.env, E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1',
  E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: 'none' };
delete env.BASH_ENV; delete env.ENV;

test('actual extracted legacy lexical helper agrees across markers, chains, callbacks and boundaries', () => {
  const directory = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'e2e-justified-diff-'));
  try {
    const file = path.join(directory, 'source.ts');
    const fixtures = [
      '// JUSTIFIED: immediate\nwork();', '// JUSTIFIED: CRLF\r\nwork();\r\n',
      '// JUSTIFIED: two\n// second comment\nwork();',
      '/* // JUSTIFIED: block */\nwork();', '/*\n// JUSTIFIED: block\n*/\nwork();',
      'const s = "// JUSTIFIED: string";\nwork();', 'const s = `\n// JUSTIFIED: template\n`;\nwork();',
      '// JUSTIFIED: chain\nroot()\n.then()\n.click();',
      '// JUSTIFIED: no\nroot();\n.click();', '// JUSTIFIED: no\nroot()\nother()\n.click();',
      '// JUSTIFIED: blank\n\nroot()\n.click();', '// JUSTIFIED: options\nroot({a: 1})\n.click();',
      '// JUSTIFIED: callback\npage.evaluate(() => {\nwork();\n});\nafter();',
      '// JUSTIFIED: callback\npage.waitForFunction(\n() => {\nwork();\n});\nafter();',
      '// JUSTIFIED: no block scope\ntest("x", () => {\nwork();\n});',
      '// JUSTIFIED: no block scope\ndescribe("x", () => {\nwork();\n});',
      'const rx = /["\']/;\n// JUSTIFIED: regex\nwork();',
      '// JUSTIFIED: nested\npage.evaluate(() => {\nif (ready) {\nwork();\n}\n});\nafter();',
      '// JUSTIFIED: braces in strings match legacy lexical counting\npage.evaluate(() => {\nconst s = "}";\nwork();\n});',
      '// JUSTIFIED: bounded chain\nroot()\n' + '.step()\n'.repeat(10),
      '// JUSTIFIED: bounded callback\npage.evaluate(() => {\n' + 'work();\n'.repeat(26) + '});',
    ];
    for (const marker of ['// JUSTIFIED:', '// JUSTIFIED: ', '// NOT JUSTIFIED: no', 'call(); // JUSTIFIED: trailing', '// JUSTIFIED: reason']) fixtures.push(marker + '\nwork();');
    for (const text of fixtures) {
      fs.writeFileSync(file, text);
      const legacy = spawnSync('/bin/bash', ['-p', '-c', helper + '\n_justified_lines_in_file "$1"', 'legacy-oracle', file], { env, encoding: 'utf8', timeout: 5000 });
      assert.ifError(legacy.error);
      assert.equal(legacy.status, 0, legacy.stderr);
      const actual = justifiedCoverage(Buffer.from(text), file);
      assert.deepEqual(actual.diagnostics, [], text);
      const expected = legacy.stdout.trim() ? legacy.stdout.trim().split('\n').map(Number) : [];
      assert.deepEqual(actual.coverage.map(item => item.line), expected, text);
    }
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});

test('actual full legacy scan suppresses P1, routes P0 to review, and retains focused #7', { timeout: 90_000 }, () => {
  const directory = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'e2e-justified-account-'));
  try {
    const file = path.join(directory, 'example.spec.ts');
    const text = "import {test, expect} from '@playwright/test';\n// JUSTIFIED: intentional focus still forbidden\ntest.only('x', async ({page}) => {\n// JUSTIFIED: timing measurement\nawait page.waitForTimeout(100);\n// JUSTIFIED: intentional object check needs review\nexpect(page.locator('button')).toBeTruthy();\n});\n";
    fs.writeFileSync(file, text);
    const result = spawnSync('/bin/bash', ['-p', scanner, directory], { cwd: repository, env, encoding: 'utf8', timeout: 75_000, maxBuffer: 4_000_000 });
    assert.ifError(result.error);
    const output = result.stdout + result.stderr;
    assert.equal(result.status, 0, output);
    assert.doesNotMatch(output, /INCOMPLETE/);
    assert.match(output, /\[P0\] #7 Focused test committed \(1 hit\)/);
    assert.match(output, /\[P0\?\]\[JUSTIFIED-REVIEW\][^\n]*\(1 candidate\)/);
    assert.match(output, /Suppressed by JUSTIFIED: 2 unique candidate location/);
    assert.doesNotMatch(output, /\[P[12]\] #1 /);
    const make = (line, severity, patternId) => ({file, line, severity, patternId, disposition: 'confirmed', origin: 'heuristic'});
    const native = applyJustified(Buffer.from(text), file, [make(3, 'P0', '#7'), make(5, 'P1', '#1'), make(7, 'P0', '#4f')]);
    assert.deepEqual(native.findings.map(item => [item.patternId, item.disposition]), [['#7', 'confirmed'], ['#4f', 'justified-review']]);
    assert.deepEqual(native.suppressed.map(item => item.line), [5]);
    assert.deepEqual(native.diagnostics, []);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
