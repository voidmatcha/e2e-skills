// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
// Compare policy decisions with the actual legacy scanner, not copied expected
// exit values. No project ESLint, downloaded tool or project code is executed.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { summarize } from '../src/report.mjs';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const scanner = legacyOracleFile();
const prefix = "import { test, expect } from '@playwright/test';\n";
const cases = {
  confirmed: prefix + "test.only('focus', async ({ page }) => {\n  await expect(page.getByTestId('ready')).toBeVisible();\n});\n",
  candidate: prefix + "test('attached', async ({ page }) => {\n  await expect(page.getByTestId('ready')).toBeAttached();\n});\n",
  p1: prefix + "test('sleep', async ({ page }) => {\n  await page.waitForTimeout(100);\n});\n",
};

for (const [name, source] of Object.entries(cases)) {
  test(`legacy policy parity: ${name}`, { timeout: 120_000 }, () => {
    const directory = fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()), 'e2e-policy-'));
    const filename = path.join(directory, 'case.spec.ts');
    fs.writeFileSync(filename, source);
    // Retain all output until this test finishes, even if an assertion fails.
    try {
      for (const failOn of ['none', 'any', 'p0', 'p0-candidate']) {
        const env = { ...process.env, E2E_SMELL_ALLOW_PROJECT_ESLINT: '0',
          E2E_SMELL_NO_ESLINT_DOWNLOAD: '1', E2E_SMELL_DISABLE_AST_GREP: '1',
          E2E_SMELL_NO_AST_GREP_DOWNLOAD: '1', E2E_SMELL_FAIL_ON: failOn };
        delete env.BASH_ENV; delete env.ENV;
        const result = spawnSync('/bin/bash', ['-p', scanner, filename], {
          cwd: root, env, encoding: 'utf8', timeout: 25_000, maxBuffer: 4_000_000,
        });
        assert.ifError(result.error);
        const output = result.stdout + result.stderr;
        assert.ok(!output.includes('INCOMPLETE'), output);
        const summary = output.match(/^Summary: (\d+) total hit\(s\), (\d+) P0, (\d+) P1\/P2 heuristic, (\d+) LLM-triage, (\d+) P0 candidate; (\d+) AST-origin/m);
        assert.ok(summary, output);
        const findings = [];
        for (const match of output.matchAll(/^\[(P[012])(\?)?\](?:\[LLM-TRIAGE\])? #[^\n]+\((\d+) hits?\)$/gm)) {
          for (let index = 0; index < Number(match[3]); index++) {
            findings.push({ severity: match[1], disposition: match[2] ? 'candidate' : 'confirmed', origin: 'heuristic' });
          }
        }
        assert.ok(findings.length > 0, output);
        const actual = summarize(findings, { failOn });
        assert.deepEqual([actual.counts.total, actual.counts.p0, actual.counts.p1p2,
          actual.counts.triage, actual.counts.p0Candidate, actual.counts.ast], summary.slice(1).map(Number), output);
        assert.equal(actual.exitCode, result.status, output);
      }
    } finally {
      fs.rmSync(directory, { recursive: true, force: true });
    }
  });
}
