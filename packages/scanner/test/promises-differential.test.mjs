// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { promises } from '../src/promises.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
test('actual legacy missing-await fixture: direct slice, consumed guards and declared POM gap', { timeout: 90000 }, () => {
  const file = path.join(repository, 'skills/e2e-reviewer/evals/files/missing-await-contexts.spec.ts');
  const bytes = fs.readFileSync(file), text = bytes.toString('utf8');
  const manifest = inventory(file), scope = createScope({ manifest, sources: new Map([[file, bytes]]) });
  const actual = promises(bytes, file, { scope });
  assert.deepEqual(actual.findings.filter(x => x.patternId === '#15').map(x => x.line), [24]);
  const lines = actual.findings.filter(x => x.patternId === '#16').map(x => x.line);
  assert.deepEqual(lines, [25,32,108,114,117,118,119,120,121,122,123,124,127,129,130,131,132,133,134,135,136,167,169,194,195]);
  for (const line of [16,43,47,55,61,68,73,78,84,92,99,140,141,144,160,161,162,163,170,171,193,197]) assert.ok(!lines.includes(line), String(line));
  assert.deepEqual(actual.findings.filter(x => x.disposition === 'candidate').map(x => x.line), [32,108,127,129,130,131,132,133,134,135,136,169,194,195]);
  // Shared receiver analysis deliberately does not prove POM property fields.
  assert.ok(!lines.includes(11));

  const env = { ...process.env, PATH: '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
    E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1',
    E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: 'none' };
  delete env.BASH_ENV; delete env.ENV;
  const run = spawnSync('/bin/bash', ['-p', legacyOracleFile(), file],
    { cwd: repository, env, encoding: 'utf8', timeout: 75000, maxBuffer: 4000000 });
  assert.ifError(run.error);
  const output = run.stdout + run.stderr;
  assert.equal(run.status, 0, output);
  assert.doesNotMatch(output, /INCOMPLETE/);
  const legacy = { '#15': new Set(), '#16': new Set() };
  const legacyDisposition = new Map();
  let active, disposition;
  for (const line of output.split('\n')) {
    if (line.startsWith('[')) {
      active = /^\[P1(?:\?)?\](?:\[LLM-TRIAGE\])? (#15|#16) /.exec(line)?.[1];
      disposition = line.startsWith('[P1?]') ? 'candidate' : 'confirmed';
    }
    if (!active) continue;
    const hit = /missing-await-contexts\.spec\.ts:(\d+):/.exec(line);
    if (hit) {
      legacy[active].add(Number(hit[1]));
      legacyDisposition.set(`${active}:${hit[1]}`, disposition);
    }
  }
  assert.ok(legacy['#15'].has(24), output);
  assert.ok(legacy['#16'].has(11), 'legacy retains the known POM triage gap');
  for (const [id, line, expected] of [['#16',25,'confirmed'],['#16',32,'candidate'],['#15',24,'confirmed']]) {
    assert.equal(legacyDisposition.get(`${id}:${line}`), expected, 'actual legacy disposition');
    assert.equal(actual.findings.find(x => x.patternId === id && x.line === line).disposition, expected, 'Node preserves original disposition');
  }
  for (const finding of actual.findings) {
    // AST anchors a multiline call at its receiver; regex anchors its method.
    const endLine = text.slice(0, finding.end).split('\n').length;
    assert.ok([...legacy[finding.patternId]].some(line => line >= finding.line && line <= endLine), `${finding.patternId}:${finding.line}\n${output}`);
  }
  assert.ok(fs.readFileSync(file).equals(bytes), 'original fixture is immutable');
});
