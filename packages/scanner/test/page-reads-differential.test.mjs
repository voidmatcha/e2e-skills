// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { pageReads } from '../src/page-reads.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));

test('unchanged legacy #4h/direct #17 fixtures match, with retry-window differences separate', { timeout: 90_000 }, t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-page-reads-diff-')));
  for (const name of ['semicolonless-url.spec.ts', 'settings.spec.ts', 'dashboard.spec.ts']) {
    fs.copyFileSync(path.join(repository, 'skills/e2e-reviewer/evals/files', name), path.join(root, name));
  }
  const retries = {
    'long-retry.spec.ts': "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\nawait expect(async()=>{\n" +
      '\n'.repeat(35) + "expect(page.url()).toBe('x');\n" + '\n'.repeat(35) + '}).toPass();\n});\n',
    'alias-retry.spec.ts': "import {test,expect as verify} from '@playwright/test';\ntest('x',async({page})=>{\nawait verify(async()=>{\nverify(page.url()).toBe('x');\n}).toPass();\n});\n",
  };
  for (const [name, text] of Object.entries(retries)) fs.writeFileSync(path.join(root, name), text);
  const manifest = inventory(root);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  const expected = [];
  for (const [file, bytes] of sources) {
    const result = pageReads(bytes, file, { scope });
    assert.deepEqual(result.diagnostics, [], file);
    for (const finding of result.findings) {
      expected.push(`${finding.patternId}:${path.basename(file)}:${finding.line}:${finding.severity}:${finding.disposition}`);
    }
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
  const observed = [];
  let current;
  for (const line of output.split('\n')) {
    if (line.startsWith('[')) current = line.match(/^\[P1\] (#4h|#17) /)?.[1];
    if (!current) continue;
    const hit = line.match(/([^/\s]+\.spec\.ts):(\d+):/);
    if (hit) observed.push(`${current}:${hit[1]}:${hit[2]}:P1:confirmed`);
  }
  const differences = ['#4h:long-retry.spec.ts:39:P1:confirmed', '#4h:alias-retry.spec.ts:4:P1:confirmed'];
  for (const finding of differences) assert.ok(observed.includes(finding), output);
  const parity = [...new Set(observed.filter(item => !differences.includes(item)))].sort();
  assert.equal(parity.length, 14, output);
  assert.deepEqual(parity, expected.sort(), output);
  t.diagnostic(JSON.stringify({ status: 'KNOWN_LEGACY_FALSE_POSITIVES', legacyFindings: differences,
    nodeFindings: [], reason: 'proven retry callbacks exceed the legacy window or use an imported expect alias' }));
});
