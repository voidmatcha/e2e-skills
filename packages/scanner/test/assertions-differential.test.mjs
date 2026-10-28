// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
// Compare this bounded slice with actual legacy output on unchanged fixtures.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { assertions } from '../src/assertions.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
const fixtures = ['uncalled-matcher.spec.ts', 'always-true-locator.spec.ts', 'awaited-locator-truthiness.spec.ts'];

test('confirmed #8c and direct Locator #4f match actual legacy fixtures', { timeout: 90_000 }, () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-assertions-diff-')));
  for (const name of fixtures) fs.copyFileSync(path.join(repository, 'scripts/evals/skills/e2e-reviewer/files', name), path.join(root, name));
  const manifest = inventory(root);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  const expected = [];
  for (const [file, bytes] of sources) {
    const result = assertions(bytes, file, { scope });
    for (const finding of result.findings) expected.push(`${finding.patternId}:${path.basename(file)}:${finding.line}:${finding.severity}:${finding.disposition}`);
  }
  const env = { ...process.env, E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1',
    E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: 'none' };
  delete env.BASH_ENV; delete env.ENV;
  const run = spawnSync('/bin/bash', ['-p', legacyOracleFile(), root], {
    cwd: repository, env, encoding: 'utf8', timeout: 75_000, maxBuffer: 4_000_000,
  });
  assert.ifError(run.error);
  const output = run.stdout + run.stderr;
  assert.equal(run.status, 0, output);
  assert.match(output, /^Summary:/m);
  assert.ok(!output.includes('INCOMPLETE'), output);
  const actual = [];
  let current;
  for (const line of output.split('\n')) {
    if (line.startsWith('[')) current = line.match(/^\[P0\] (#8c|#4f) /)?.[1];
    if (!current) continue;
    const hit = line.match(/([^/\s]+\.spec\.ts):(\d+):/);
    if (hit) actual.push(`${current}:${hit[1]}:${hit[2]}:P0:confirmed`);
  }
  assert.ok(actual.some(item => item.startsWith('#8c:')), output);
  assert.ok(actual.some(item => item.startsWith('#4f:')), output);
  assert.equal(new Set(actual).size, 7, output);
  assert.deepEqual([...new Set(actual)].sort(), expected.sort(), output);
});
