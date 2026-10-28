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
import { assertions } from '../src/assertions.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
const fixtures = ['auth.spec.ts', 'dashboard.spec.ts', 'fp-guards.spec.ts'];

test('legacy #8a/#8b fixture candidates match with explicit shadow false-positive guards', { timeout: 90_000 }, t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-discarded-diff-')));
  for (const name of fixtures) fs.copyFileSync(path.join(repository, 'scripts/evals/skills/e2e-reviewer/files', name), path.join(root, name));
  const shadow = "import {test} from '@playwright/test';\nasync function custom(page){\npage.locator('x');\nawait page.isVisible('x');\n}\n";
  fs.writeFileSync(path.join(root, 'shadow.spec.ts'), shadow);
  // The existing multiline-consumer regression ends with this inline typed
  // helper. Keep it as an independent candidate rather than claiming runtime
  // receiver proof from a TypeScript annotation.
  fs.writeFileSync(path.join(root, 'typed.spec.ts'),
    "async function discarded(locator: import('@playwright/test').Locator) {\n  await locator.isHidden();\n}\n");
  const manifest = inventory(root);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  const expected = [];
  for (const [file, bytes] of sources) {
    const result = assertions(bytes, file, { scope });
    for (const finding of result.findings.filter(f => ['#8a', '#8b'].includes(f.patternId))) {
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
    if (line.startsWith('[')) current = line.match(/^\[P0\?\]\[LLM-TRIAGE\] (#8a|#8b) /)?.[1];
    if (!current) continue;
    const hit = line.match(/([^/\s]+\.spec\.ts):(\d+):/);
    if (hit) observed.push(`${current}:${hit[1]}:${hit[2]}:P0:candidate`);
  }
  const differences = ['#8a:shadow.spec.ts:3:P0:candidate', '#8b:shadow.spec.ts:4:P0:candidate'];
  for (const finding of differences) assert.ok(observed.includes(finding), output);
  const parity = [...new Set(observed.filter(item => !differences.includes(item)))].sort();
  assert.equal(parity.length, 4, output);
  assert.deepEqual(parity, expected.sort(), output);
  t.diagnostic(JSON.stringify({ status: 'KNOWN_LEGACY_FALSE_POSITIVES', source: shadow,
    legacyFindings: differences, nodeFindings: [], reason: 'the local untyped parameter does not prove a Playwright Page receiver' }));
});
