// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
// One bounded legacy scan checks #7 source locations against the Node detector.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { focusedTests } from '../src/focused-tests.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
const cases = {
  'direct.cy.ts': "// JUSTIFIED: focused calls remain findings\nit.only('a',()=>{});\ndescribe.only('b',()=>{});\n",
  'legacy-false-positive.cy.ts': fs.readFileSync(new URL('./fixtures/focused-legacy-false-positive.cy.ts', import.meta.url), 'utf8'),
  'foreign.cy.ts': "import { it } from 'vitest';\nit.only('unit',()=>{});\ndescribe.only('unit suite',()=>{});\n",
  'mixed.spec.ts': "import { it } from 'mocha';\ncy.visit('/');\nit.only('foreign',()=>{});\ndescribe.only('cypress',()=>{});\n",
  'runtime.spec.ts': "cy.visit('/');\nit.only('runtime',()=>{});\n",
  'alias.cy.ts': "const focused = it.only;\nfocused('a',()=>{});\nconst { only: suite } = describe;\nsuite('b',()=>{});\nconst custom = { only() {} };\nconst wrong = it.only.bind(custom);\nwrong('guard',()=>{});\n",
  'alias.spec.ts': "import { test } from '@playwright/test';\nconst focused = test.only;\nfocused('a',()=>{});\nconst { only } = test;\nonly('b',()=>{});\nconst bound = test.only.bind(test);\nbound('c',()=>{});\n",
};

test('bounded #7 differential preserves one explicit legacy shadow false positive', { timeout: 90_000 }, t => {
  const directory = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'e2e-focus-diff-'));
  try {
    const expected = [];
    for (const [name, text] of Object.entries(cases)) {
      const filename = path.join(directory, name);
      fs.writeFileSync(filename, text);
      const result = focusedTests(Buffer.from(text), filename);
      assert.deepEqual(result.diagnostics, []);
      expected.push(...result.findings.map(item => `${path.basename(item.file)}:${item.line}`));
    }
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
    const observed = [];
    let focused = false;
    for (const line of output.split('\n')) {
      if (line.startsWith('[')) focused = /^\[P0\] #7 Focused test (?:alias )?committed/.test(line);
      if (!focused) continue;
      const hit = line.match(/([^/\s]+\.(?:cy|spec)\.ts):(\d+):/);
      if (hit) observed.push(`${hit[1]}:${hit[2]}`);
    }
    assert.ok(observed.length >= 10, output);
    // Legacy's line-based shadow guard misses a same-line parameter. Preserve
    // the evidence as an explicit difference; do not reproduce that false positive.
    assert.ok(observed.includes('legacy-false-positive.cy.ts:1'), output);
    assert.ok(!expected.includes('legacy-false-positive.cy.ts:1'));
    t.diagnostic(JSON.stringify({ status: 'KNOWN_LEGACY_FALSE_POSITIVE',
      fixture: 'fixtures/focused-legacy-false-positive.cy.ts',
      source: cases['legacy-false-positive.cy.ts'].split('\n')[0],
      legacyFinding: 'P0 #7 legacy-false-positive.cy.ts:1', nodeFinding: null,
      reason: 'same-line function parameter shadows Cypress it' }));
    assert.ok(observed.includes('direct.cy.ts:2'), '#7 must ignore JUSTIFIED suppression');
    assert.deepEqual([...new Set(observed.filter(item => item !== 'legacy-false-positive.cy.ts:1'))].sort(), [...new Set(expected)].sort(), output);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
