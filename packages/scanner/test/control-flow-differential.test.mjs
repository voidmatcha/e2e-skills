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
import { controlFlow } from '../src/control-flow.mjs';

const repository = fileURLToPath(new URL('../../../', import.meta.url));
const fixtures = ['products.cy.ts', 'reasonless-skip.spec.ts'];

test('legacy fixture candidates match; unrelated and dynamic event differences stay explicit', { timeout: 90_000 }, t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-control-flow-diff-')));
  for (const name of fixtures) fs.copyFileSync(path.join(repository, 'scripts/evals/skills/e2e-reviewer/files', name), path.join(root, name));
  const differenceSource = "Cypress.on('window:before:load',()=>{});\nCypress.on(eventName,()=>false);\n";
  fs.writeFileSync(path.join(root, 'event-boundaries.cy.ts'), differenceSource);
  const manifest = inventory(root);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  const expected = [];
  for (const [file, bytes] of sources) {
    const result = controlFlow(bytes, file, { scope });
    if (path.basename(file) === 'event-boundaries.cy.ts') {
      assert.deepEqual(result.findings, []);
      assert.equal(result.diagnostics.length, 1);
      assert.match(result.diagnostics[0].message, /event name is not statically known/);
    } else assert.deepEqual(result.diagnostics, []);
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
  const observed = [];
  let current;
  for (const line of output.split('\n')) {
    if (line.startsWith('[')) current = line.match(/^\[(P0|P2)\?\]\[LLM-TRIAGE\] (#3b|#11c) /);
    if (!current) continue;
    const hit = line.match(/([^/\s]+\.(?:cy|spec)\.ts):(\d+):/);
    if (hit) observed.push(`${current[2]}:${hit[1]}:${hit[2]}:${current[1]}:candidate`);
  }
  const unrelated = '#3b:event-boundaries.cy.ts:1:P0:candidate';
  const dynamic = '#3b:event-boundaries.cy.ts:2:P0:candidate';
  assert.ok(observed.includes(unrelated), output);
  assert.ok(observed.includes(dynamic), output);
  const parity = [...new Set(observed.filter(item => item !== unrelated && item !== dynamic))].sort();
  assert.equal(parity.length, 6, output);
  assert.deepEqual(parity, expected.sort(), output);
  t.diagnostic(JSON.stringify({ status: 'KNOWN_LEGACY_FALSE_POSITIVE', source: differenceSource.split('\n')[0],
    legacyFinding: unrelated, nodeFinding: null, reason: 'a window lifecycle listener is not uncaught:exception suppression' }));
  t.diagnostic(JSON.stringify({ status: 'EXPLICIT_UNRESOLVED_EVENT', source: differenceSource.split('\n')[1],
    legacyFinding: dynamic, nodeFinding: null, nodeDiagnostic: 'Cypress event name is not statically known' }));
});
