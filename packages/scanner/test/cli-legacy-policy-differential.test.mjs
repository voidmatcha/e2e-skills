// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
const prefix = "import {test, expect} from '@playwright/test';\n";
const cases = {
  clean: "test('clean', async ({page}) => {\n await expect(page.getByTestId('ready')).toBeVisible();\n});\n",
  confirmed: "test.only('focus', async ({page}) => {\n await expect(page.getByTestId('ready')).toBeVisible();\n});\n",
  candidate: "test('attached', async ({page}) => {\n await expect(page.getByTestId('ready')).toBeAttached();\n});\n",
  p1: "test('sleep', async ({page}) => {\n await page.waitForTimeout(100);\n});\n",
};
const key = hit => `${hit.patternId}:${hit.line}:${hit.severity}:${hit.disposition}`;

for (const [name, body] of Object.entries(cases)) {
  test(`actual CLI versus frozen shell findings and four policies: ${name}`, { timeout: 180_000 }, t => {
    const root = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'cli-legacy-policy-'));
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    const file = path.join(root, 'case.spec.ts');
    const bytes = Buffer.from(prefix + body);
    fs.writeFileSync(file, bytes);
    const env = { PATH: '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin',
      HOME: root, LANG: 'C', LC_ALL: 'C' };
    for (const policy of ['none', 'any', 'p0', 'p0-candidate']) {
      const legacy = spawnSync('/bin/bash', ['-p', legacyOracleFile(), file], {
        env: { ...env, E2E_SMELL_ALLOW_PROJECT_ESLINT: '0', E2E_SMELL_NO_ESLINT_DOWNLOAD: '1',
          E2E_SMELL_DISABLE_AST_GREP: '1', E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: policy },
        encoding: 'utf8', timeout: 30_000, maxBuffer: 4_000_000,
      });
      assert.ifError(legacy.error);
      assert.ok([0, 1].includes(legacy.status), legacy.stdout + legacy.stderr);
      assert.doesNotMatch(legacy.stdout + legacy.stderr, /INCOMPLETE/);
      assert.match(legacy.stdout, /^Summary:/m);
      const observed = [];
      let header;
      for (const line of legacy.stdout.split('\n')) {
        if (line.startsWith('[')) header = line.match(/^\[(P[012])(\?)?\](?:\[LLM-TRIAGE\])? (#[\w-]+) /);
        if (!header || !line.startsWith(`  ${file}:`)) continue;
        const location = line.slice(`  ${file}:`.length).match(/^(\d+):/);
        assert.ok(location, line);
        observed.push(key({ patternId: header[3], line: Number(location[1]),
          severity: header[1], disposition: header[2] ? 'candidate' : 'confirmed' }));
      }
      const node = spawnSync(process.execPath, [cli, '--scan', file, '--fail-on', policy], {
        env, encoding: 'utf8', timeout: 30_000, maxBuffer: 4_000_000,
      });
      assert.ifError(node.error);
      const report = JSON.parse(node.stdout);
      assert.equal(report.status, 'COMPLETE', node.stdout + node.stderr);
      assert.deepEqual(report.execution.diagnostics, []);
      assert.equal(node.status, legacy.status, `${name}/${policy}`);
      // Compare multiplicity as well as locations; no Set or allowed differences.
      assert.deepEqual(report.findings.map(key).sort(), observed.sort(), `${name}/${policy}`);
      assert.equal(report.counts.total, observed.length);
      assert.deepEqual(fs.readFileSync(file), bytes);
    }
  });
}
