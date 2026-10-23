// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { cypressAssignment } from '../src/cypress-assignment.mjs';
const repository = fileURLToPath(new URL('../../../', import.meta.url));
test('unchanged legacy #10e parity and explicitly separated lexical false positives', { timeout: 90000 }, () => {
  const directory = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'e2e-cypress-assignment-'));
  try {
    const files = {
      'example.cy.ts': "const el = cy.get('button');\nlet count: Cypress.Chainable<number> = cy.get('x').its('length');\nvar value = cy.wrap(1);\nconst property = cy.foo;\nconst spy = cy.spy();\nconst stub = cy.stub(obj,'f');\nconst asyncValue =\ncy.get('split');\n",
      'foreign.spec.ts': "import {test} from 'vitest';\nconst value = 1;\n",
      // The legacy regex has no lexical receiver or executable-source filter.
      'legacy-false-positive.cy.ts': "cy.visit('/');\nfunction f(cy) { const el = cy.get('x'); }\nconst text = `const copied = cy.get('x')`;\n/* const commented = cy.get('x'); */\nconst spacedSpy = cy.spy ();\n",
    };
    for (const [name, text] of Object.entries(files)) fs.writeFileSync(path.join(directory, name), text);
    const manifest = inventory(directory);
    assert.equal(manifest.complete, true);
    const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
    const scope = createScope({ manifest, sources });
    const expected = { 'example.cy.ts': [1,2,3,4], 'foreign.spec.ts': [], 'legacy-false-positive.cy.ts': [] };
    for (const [file, lines] of Object.entries(expected)) {
      const absolute = path.join(directory, file);
      const result = cypressAssignment(sources.get(absolute), absolute, { scope });
      assert.deepEqual(result.findings.map(item => item.line), lines, file);
      if (file === 'example.cy.ts') assert.deepEqual(result.diagnostics.map(x => x.message), ['unsupported Cypress assignment declaration layout']);
      else assert.deepEqual(result.diagnostics, []);
    }
    const env = { ...process.env, E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1', E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: 'none' };
    delete env.BASH_ENV; delete env.ENV;
    const result = spawnSync('/bin/bash', ['-p', legacyOracleFile(), directory], { cwd: repository, env, encoding: 'utf8', timeout: 75000, maxBuffer: 4000000 });
    assert.ifError(result.error);
    const output = result.stdout + result.stderr;
    assert.equal(result.status, 0, output);
    assert.doesNotMatch(output, /INCOMPLETE/);
    assert.match(output, /Summary/);
    const actual = Object.fromEntries(Object.keys(files).map(file => [file, []]));
    let active = false;
    for (const line of output.split('\n')) {
      if (line.startsWith('[')) active = /^\[P1\] #10e Cypress return value assigned outside the command chain/.test(line);
      if (!active) continue;
      for (const file of Object.keys(files)) {
        const index = line.indexOf(file + ':');
        if (index < 0) continue;
        const hit = /^(\d+):/.exec(line.slice(index + file.length + 1));
        if (hit) actual[file].push(Number(hit[1]));
      }
    }
    assert.deepEqual(actual, { ...expected, 'legacy-false-positive.cy.ts': [2,3,4,5] }, output);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});
