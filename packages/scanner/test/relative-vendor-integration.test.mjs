// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-relative-vendor-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.writeFileSync(path.join(root, 'package.json'), '{}');
  const put = (name, bytes) => {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, bytes);
    return file;
  };
  return { root, put };
}
function run(file, format = 'json') {
  return spawnSync(process.execPath, [cli, '--scan', file, '--format', format, '--fail-on', 'none'],
    { encoding: 'utf8', timeout: 30_000 });
}

test('actual assertion-contract probe source completes discovery with its opaque vendor dependency', t => {
  const { put } = fixture(t);
  const bytes = fs.readFileSync(new URL('../../../scripts/evals/run-assertion-contract-probes.cjs', import.meta.url));
  const file = put('scripts/evals/run-assertion-contract-probes.cjs', bytes);
  // No vendor installation or project execution: source discovery is the claim.
  assert.ok(bytes.includes("require('./fixtures/node_modules/@playwright/test')"));
  const result = run(file);
  assert.equal(result.status, 0, result.stderr + result.stdout);
  const report = JSON.parse(result.stdout);
  assert.equal(report.schema, 'e2e-skills-node-scan-v1');
  assert.equal(report.execution.complete, true);
  assert.deepEqual(report.execution.diagnostics, []);
  assert.equal(report.coverage.complete, false);
  assert.equal(report.project.configurationExecuted, false);
  assert.equal(report.counts.confirmed, 0);
  const text = run(file, 'text');
  assert.equal(text.status, 0, text.stderr + text.stdout);
  assert.match(text.stdout, /Coverage: BOUNDED; discovery: COMPLETE\./);
  assert.match(text.stdout, /^Summary:/m);
  assert.doesNotMatch(text.stdout, /Coverage: COMPLETE/);
});

for (const [name, declaration, expression, detector] of [
  ['ESM test', "import {test} from './node_modules/@playwright/test';", "test.only('x',()=>{});", 'focusedTests'],
  ['CommonJS test', "const {test}=require('./node_modules/@playwright/test');", "test.only('x',()=>{});", 'focusedTests'],
  ['ESM expect', "import {expect} from './node_modules/@playwright/test';", 'expect(true).toBeTruthy();', 'assertions'],
  ['CommonJS expect', "const {expect}=require('./node_modules/@playwright/test');", 'expect(true).toBeTruthy();', 'assertions'],
]) test(`${name} from a relative vendor path cannot acquire official provenance`, t => {
  const { root, put } = fixture(t);
  const marker = path.join(root, 'vendor-executed');
  put('node_modules/@playwright/test/index.js',
    `require('node:fs').writeFileSync(${JSON.stringify(marker)}, 'bad');module.exports=require('@playwright/test');`);
  const file = put('case.spec.ts', `${declaration}\n${expression}\n`);
  const result = run(file);
  assert.equal(result.status, 2, result.stderr + result.stdout);
  const report = JSON.parse(result.stdout);
  assert.equal(report.execution.complete, false);
  assert.equal(report.counts.confirmed, 0);
  assert.ok(report.execution.diagnostics.some(item => item.detector === detector && item.code === 'import-out-of-scope' && item.file === file), result.stdout);
  assert.ok(report.execution.diagnostics.every(item => item.detector !== 'importSnapshot'), result.stdout);
  assert.equal(fs.existsSync(marker), false);
  const text = run(file, 'text');
  assert.equal(text.status, 2, text.stderr + text.stdout);
  assert.doesNotMatch(text.stdout, /^Summary:/m);
});
