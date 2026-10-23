// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { cypressCallbacks } from '../src/cypress-callbacks.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
test('actual unchanged Cypress fixtures preserve legacy candidates; binding/body false positives are separate', { timeout: 90000 }, () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-cy-callback-diff-')));
  const names = ['cypress-command-model.cy.ts', 'cypress-action-statement-boundaries.cy.ts'];
  const originals = new Map(names.map(name => [name, fs.readFileSync(path.join(repository, 'skills/e2e-reviewer/evals/files', name))]));
  for (const [name, bytes] of originals) fs.writeFileSync(path.join(root, name), bytes);
  const falseName = 'legacy-false-positive.cy.ts';
  fs.writeFileSync(path.join(root, falseName), "function f(cy){cy.get('x').click().should('exist');}\nit('deferred',async()=>{const helper=()=>cy.get('x');});\n");
  const manifest = inventory(root);
  assert.equal(manifest.complete, true);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  const native = {};
  for (const [file, bytes] of sources) {
    const result = cypressCallbacks(bytes, file, { scope });
    assert.ok(result.findings.every(x => x.severity === 'P1' && x.disposition === 'candidate'));
    native[path.basename(file)] = Object.fromEntries(['#10d','#10f'].map(id => [id,
      [...new Set(result.findings.filter(x => x.patternId === id).map(x => x.line))]]));
  }
  assert.deepEqual(native[falseName], { '#10d': [], '#10f': [] });
  assert.deepEqual(native['cypress-command-model.cy.ts'], { '#10d': [2,6], '#10f': [16] });
  assert.deepEqual(native['cypress-action-statement-boundaries.cy.ts'], { '#10d': [], '#10f': [5,7,8,10,16] });
  const env = { ...process.env, PATH: '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
    E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1',
    E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: 'none' };
  delete env.BASH_ENV; delete env.ENV;
  const run = spawnSync('/bin/bash', ['-p', legacyOracleFile(), root],
    { cwd: repository, env, encoding: 'utf8', timeout: 75000, maxBuffer: 4000000 });
  assert.ifError(run.error);
  const output = run.stdout + run.stderr;
  assert.equal(run.status, 0, output);
  assert.doesNotMatch(output, /INCOMPLETE/);
  const legacy = Object.fromEntries([...names, falseName].map(name => [name, { '#10d': [], '#10f': [] }]));
  let active;
  for (const line of output.split('\n')) {
    if (line.startsWith('[')) active = /^\[P1\?\]\[LLM-TRIAGE\] (#10d|#10f) /.exec(line)?.[1];
    if (!active) continue;
    for (const name of [...names, falseName]) {
      const index = line.indexOf(name + ':');
      if (index < 0) continue;
      const hit = /^(\d+):/.exec(line.slice(index + name.length + 1));
      if (hit) legacy[name][active].push(Number(hit[1]));
    }
  }
  for (const name of names) assert.deepEqual(native[name], legacy[name], `${name}\n${output}`);
  assert.deepEqual(legacy[falseName], { '#10d': [2], '#10f': [1] }, 'separate lexical-scope/body false positives');
  for (const [name, bytes] of originals) {
    assert.ok(fs.readFileSync(path.join(root, name)).equals(bytes));
    assert.ok(fs.readFileSync(path.join(repository, 'skills/e2e-reviewer/evals/files', name)).equals(bytes));
  }
});
