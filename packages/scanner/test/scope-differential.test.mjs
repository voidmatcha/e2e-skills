// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
// One actual legacy scan verifies supported bindings and records one known gap.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { createScope } from '../src/scope.mjs';
import { inventory } from '../src/inventory.mjs';
import { focusedTests } from '../src/focused-tests.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
test('ESM/CJS/import-equals legacy comparison retains the separate legacy false-negative fixture', { timeout: 90_000 }, () => {
  const directory = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'e2e-scope-diff-'));
  try {
    const files = {
      'fixture.ts': "import { test as base } from '@playwright/test';\nexport const test = base.extend({});\nexport const custom = {only(){}};\n",
      'barrel.ts': "export { test, test as default, custom } from './fixture';\n",
      'example.spec.ts': "import { test as scenario, custom } from './barrel';\nimport defaultTest from './barrel';\nimport * as fixtures from './barrel';\nscenario.only('renamed',()=>{});\ndefaultTest.only('default',()=>{});\nfixtures.test.only('namespace',()=>{});\ncustom.only('not playwright',()=>{});\n",
      'direct.spec.cjs': "const pw = require('@playwright/test');\nconst direct = require('@playwright/test').test;\nconst {test: scenario} = require('@playwright/test');\npw.test.describe.only('namespace',()=>{});\ndirect.only('property',()=>{});\nscenario.only('destructured',()=>{});\nconst {it} = require('mocha');\nit.only('foreign',()=>{});\n",
      'whole-module.cjs': "module.exports = require('@playwright/test');\n",
      'fixture-module.cjs': "module.exports = require('./fixture');\n",
      'transitive.spec.cjs': "const {test: scenario} = require('./whole-module.cjs');\nscenario.only('transitive',()=>{});\n",
      // Legacy misses the second distinct destructured test alias in one file.
      // Retain the exact context, not a reduced case that changes its behavior.
      // This false-negative witness is never a successful parity cell.
      'legacy-false-negative.spec.cjs': "const {test: scenario} = require('./whole-module.cjs');\nscenario.only('transitive',()=>{});\nconst {test: fixtureTest, custom} = require('./fixture-module.cjs');\nfixtureTest.only('extended fixture',()=>{});\ncustom.only('not playwright',()=>{});\n",
      'equals.spec.ts': "import pw = require('@playwright/test');\npw.test.only('direct equals',()=>{});\nimport fixtures = require('./whole-module.cjs');\nfixtures.test.only('relative equals',()=>{});\n",
    };
    for (const [file, text] of Object.entries(files)) fs.writeFileSync(path.join(directory, file), text);
    const manifest = inventory(directory);
    assert.equal(manifest.complete, true);
    const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
    const scope = createScope({ manifest, sources });
    const target = path.join(directory, 'example.spec.ts');
    assert.equal(scope.binding(target, 'scenario').kind, 'playwright-test');
    assert.equal(scope.binding(target, 'defaultTest').kind, 'playwright-test');
    assert.equal(scope.binding(target, 'fixtures').kind, 'module-namespace');
    assert.equal(scope.binding(target, 'custom').kind, 'none');
    const expected = { 'example.spec.ts': [4, 5, 6], 'direct.spec.cjs': [4, 5, 6], 'transitive.spec.cjs': [2], 'equals.spec.ts': [2, 4], 'legacy-false-negative.spec.cjs': [2, 4] };
    const expectedLegacy = { ...expected, 'legacy-false-negative.spec.cjs': [2] };
    for (const [file, lines] of Object.entries(expected)) {
      const absolute = path.join(directory, file);
      const actual = focusedTests(sources.get(absolute), absolute, { scope });
      assert.deepEqual(actual.findings.map(item => item.line), lines, file);
      assert.deepEqual(actual.diagnostics, [], file);
    }
    assert.equal(scope.validate().complete, true);
    const env = { ...process.env, E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1',
      E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: 'none' };
    delete env.BASH_ENV; delete env.ENV;
    const result = spawnSync('/bin/bash', ['-p', legacyOracleFile(), directory], {
      cwd: repository, env, encoding: 'utf8', timeout: 75_000, maxBuffer: 4_000_000,
    });
    assert.ifError(result.error);
    const output = result.stdout + result.stderr;
    assert.equal(result.status, 0, output);
    assert.match(output, /^Summary:/m);
    assert.ok(!output.includes('INCOMPLETE'), output);
    let focus = false;
    const lines = Object.fromEntries(Object.keys(expected).map(file => [file, []]));
    for (const line of output.split('\n')) {
      if (line.startsWith('[')) focus = /^\[P0\] #7 Focused test committed/.test(line);
      if (!focus) continue;
      for (const file of Object.keys(expected)) {
        const suffix = line.slice(line.indexOf(`${file}:`) + file.length + 1);
        if (line.includes(`${file}:`) && /^\d+:/.test(suffix)) lines[file].push(Number(suffix.split(':')[0]));
      }
    }
    for (const file of Object.keys(expectedLegacy)) assert.deepEqual(lines[file].sort((a, b) => a - b), expectedLegacy[file], output);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
