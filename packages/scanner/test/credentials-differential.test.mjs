// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { credentials } from '../src/credentials.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
test('unchanged actual auth fixtures preserve the legacy #14 candidate locations', { timeout: 90000 }, () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-credentials-diff-')));
  const names = ['auth.spec.ts','cy-env-login.cy.ts','login-request.cy.ts','pages/login-page.ts'];
  const originals = new Map(names.map(name => [name, fs.readFileSync(path.join(repository, 'skills/e2e-reviewer/evals/files', name))]));
  const native = {};
  for (const [name, bytes] of originals) {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, bytes);
    const result = credentials(bytes, file);
    assert.deepEqual(result.diagnostics, []);
    assert.ok(result.findings.every(x => x.patternId === '#14' && x.severity === 'P1' && x.disposition === 'candidate'));
    native[name] = result.findings.map(x => x.line);
  }
  assert.deepEqual(native, {'auth.spec.ts':[8,15,33],'cy-env-login.cy.ts':[6,12,13],'login-request.cy.ts':[],'pages/login-page.ts':[]});
  const env = { ...process.env, PATH: '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
    E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1',
    E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: 'none' };
  delete env.BASH_ENV; delete env.ENV;
  const run = spawnSync('/bin/bash', ['-p', legacyOracleFile(), root],
    { cwd: repository, env, encoding: 'utf8', timeout: 75000, maxBuffer: 4000000 });
  assert.ifError(run.error);
  const output = run.stdout + run.stderr;
  // Do not dump source-bearing scanner stdout when an assertion fails.
  assert.equal(run.status, 0, 'legacy scanner did not complete');
  assert.ok(!/INCOMPLETE/.test(output), 'legacy scanner was incomplete');
  const legacy = Object.fromEntries(names.map(name => [name, []]));
  let active;
  for (const line of output.split('\n')) {
    if (line.startsWith('[')) active = /^\[P1\?\]\[LLM-TRIAGE\] #14 /.test(line);
    if (!active || !line.includes('[REDACTED credential candidate]')) continue;
    for (const name of names) {
      const index = line.indexOf(name + ':');
      if (index < 0) continue;
      const hit = /^(\d+):/.exec(line.slice(index + name.length + 1));
      if (hit) legacy[name].push(Number(hit[1]));
    }
  }
  assert.deepEqual(native, legacy, 'credential candidate locations differ');
  for (const [name, bytes] of originals) {
    assert.ok(fs.readFileSync(path.join(root, name)).equals(bytes));
    assert.ok(fs.readFileSync(path.join(repository, 'skills/e2e-reviewer/evals/files', name)).equals(bytes));
  }
});
