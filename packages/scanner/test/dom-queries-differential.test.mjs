// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { domQueries } from '../src/dom-queries.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { applyJustified } from '../src/justified.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
test('unchanged real legacy fixtures match after shared suppression; legacy false positives stay separate', { timeout: 90000 }, () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-dom-diff-')));
  const names = ['raw-dom-context.spec.ts', 'dashboard.spec.ts', 'products.cy.ts'];
  const originals = new Map(names.map(name => [name, fs.readFileSync(path.join(repository, 'scripts/evals/skills/e2e-reviewer/files', name))]));
  for (const [name, bytes] of originals) fs.writeFileSync(path.join(root, name), bytes);
  const falseName = 'legacy-false-positive.spec.ts';
  fs.writeFileSync(path.join(root, falseName), "import {test} from '@playwright/test';\nconst database={query:()=>({first(){}})};\ndatabase.query().first();\nfunction f(document){document.querySelector('.custom');}\n");
  const manifest = inventory(root);
  assert.equal(manifest.complete, true);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  const native = {};
  for (const [file, bytes] of sources) {
    const raw = domQueries(bytes, file, { scope });
    assert.ok(raw.findings.every(x => x.severity === 'P1' && x.disposition === 'candidate'));
    const suppressed = applyJustified(bytes, file, raw.findings);
    assert.deepEqual(suppressed.diagnostics, []);
    native[path.basename(file)] = Object.fromEntries(['#6','#10a'].map(id => [id,
      [...new Set(suppressed.findings.filter(x => x.patternId === id).map(x => x.line))]]));
    if (path.basename(file) === 'raw-dom-context.spec.ts') {
      assert.equal(raw.findings.length, 6);
      assert.equal(suppressed.suppressed.length, 0);
    }
  }
  assert.deepEqual(native[falseName], { '#6': [], '#10a': [] });
  assert.deepEqual(native['dashboard.spec.ts'], { '#6': [44], '#10a': [28,29] });
  assert.deepEqual(native['raw-dom-context.spec.ts'], { '#6': [5,11,12,19,26], '#10a': [] });
  assert.deepEqual(native['products.cy.ts'], { '#6': [], '#10a': [19,25,30,34,42,43,59] });

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
  const legacy = Object.fromEntries([...names, falseName].map(name => [name, { '#6': [], '#10a': [] }]));
  let active;
  for (const line of output.split('\n')) {
    if (line.startsWith('[')) active = /^\[P1\?\]\[LLM-TRIAGE\] (#6|#10a) /.exec(line)?.[1];
    if (!active) continue;
    for (const name of [...names, falseName]) {
      const index = line.indexOf(name + ':');
      if (index < 0) continue;
      const hit = /^(\d+):/.exec(line.slice(index + name.length + 1));
      if (hit) legacy[name][active].push(Number(hit[1]));
    }
  }
  for (const name of names) assert.deepEqual(native[name], legacy[name], `${name}\n${output}`);
  assert.deepEqual(legacy[falseName], { '#6': [4], '#10a': [3] }, 'intentional legacy binding false positives');
  for (const [name, bytes] of originals) {
    assert.ok(fs.readFileSync(path.join(root, name)).equals(bytes));
    assert.ok(fs.readFileSync(path.join(repository, 'scripts/evals/skills/e2e-reviewer/files', name)).equals(bytes));
  }
});
