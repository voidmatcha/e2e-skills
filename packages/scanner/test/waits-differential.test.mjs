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
import { waits } from '../src/waits.mjs';

test('bounded numeric wait source locations match one actual legacy scan', { timeout: 90_000 }, () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-waits-diff-')));
  const cases = {
    'page.spec.ts': "import {test} from '@playwright/test';\ntest('sleep',async({page})=>{\n await page.waitForTimeout(20);\n const clock={waitForTimeout(){}};\n clock.waitForTimeout(20);\n});\n",
    'numeric.cy.ts': "cy.visit('/');\ncy.wait(200);\ncy.wait('@load');\ncy.wait(delay);\n",
    'foreign.spec.ts': "import {test} from 'vitest';\ntest('unit',async({page})=>{\n page.waitForTimeout(20);\n});\n",
  };
  for (const [file, text] of Object.entries(cases)) fs.writeFileSync(path.join(root, file), text);
  const manifest = inventory(root);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  const expected = [];
  for (const [file, bytes] of sources) for (const finding of waits(bytes, file, { scope }).findings) expected.push(`${finding.patternId}:${path.basename(file)}:${finding.line}:${finding.disposition}`);
  const repository = fileURLToPath(new URL('../../../', import.meta.url));
  const env = { ...process.env, E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1',
    E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: 'none' };
  delete env.BASH_ENV; delete env.ENV;
  const result = spawnSync('/bin/bash', ['-p', legacyOracleFile(), root], {
    cwd: repository, env, encoding: 'utf8', timeout: 75_000, maxBuffer: 4_000_000,
  });
  assert.ifError(result.error);
  const output = result.stdout + result.stderr;
  assert.equal(result.status, 0, output);
  assert.match(output, /^Summary:/m);
  assert.ok(!output.includes('INCOMPLETE'), output);
  const actual = [];
  let current, disposition;
  for (const line of output.split('\n')) {
    if (line.startsWith('[')) {
      current = line.match(/^\[.*?\] (#9b?) /)?.[1];
      disposition = line.includes('[LLM-TRIAGE]') ? 'candidate' : 'confirmed';
    }
    if (!current) continue;
    const hit = line.match(/([^/\s]+\.(?:cy|spec)\.ts):(\d+):/);
    if (hit) actual.push(`${current}:${hit[1]}:${hit[2]}:${disposition}`);
  }
  assert.deepEqual([...new Set(actual)].sort(), expected.sort(), output);
});
