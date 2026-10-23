// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-static-review-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.writeFileSync(path.join(root, 'package.json'), '{}');
  return root;
}
const run = (root, ...args) => spawnSync(process.execPath, [cli, '--scan', root, ...args],
  { encoding: 'utf8', timeout: 30_000, env: { ...process.env, E2E_SMELL_FAIL_ON: 'p0' } });
const pom = "import {test,expect} from '@playwright/test';\ntest('x',()=>{\nconst settingsPage=new SettingsPage();\nexpect(settingsPage.submitButton).toBeTruthy();\n});\n";

test('static-review preserves candidate gates while linking one precise POM obligation', t => {
  const root = fixture(t); fs.writeFileSync(path.join(root, 'case.spec.ts'), pom);
  for (const [policy, exit] of [['none', 0], ['any', 0], ['p0', 0], ['p0-candidate', 1]]) {
    const result = run(root, '--fail-on', policy);
    assert.equal(result.status, exit, result.stderr + result.stdout);
    const report = JSON.parse(result.stdout);
    assert.equal(report.schema, 'e2e-skills-node-scan-v1');
    assert.equal(report.execution.complete, true);
    assert.deepEqual(report.execution.diagnostics, []);
    assert.equal(report.coverage.complete, false);
    assert.equal(report.compatibility.status, 'development');
    assert.equal(report.counts.p0, 0);
    assert.equal(report.counts.p0Candidate, 1);
    assert.equal(report.review.required, true);
    assert.equal(report.review.candidates, 1);
    assert.equal(report.review.obligations.length, 1);
    assert.equal(report.review.obligations[0].patternId, '#4f');
    assert.equal(report.review.obligations[0].causeId, 'pom-locator-truthiness');
  }
  const text = run(root, '--format', 'text', '--fail-on', 'p0-candidate');
  assert.equal(text.status, 1, text.stderr);
  assert.match(text.stdout, /Semantic review: REQUIRED/);
  assert.match(text.stdout, /Review obligations: 1/);
  assert.match(text.stdout, /^Summary: 1 total hit\(s\), 0 P0,/m);
  assert.doesNotMatch(text.stdout, /Coverage: COMPLETE/);
});

test('a retained candidate never hides a parser failure under any policy', t => {
  const root = fixture(t);
  fs.writeFileSync(path.join(root, 'case.spec.ts'), pom);
  fs.writeFileSync(path.join(root, 'broken.ts'), 'function (');
  for (const policy of ['none', 'any', 'p0', 'p0-candidate']) {
    const result = run(root, '--fail-on', policy);
    assert.equal(result.status, 2, result.stderr);
    const report = JSON.parse(result.stdout);
    assert.equal(report.status, 'INCOMPLETE');
    assert.equal(report.counts.p0Candidate, 1);
    assert.ok(report.execution.diagnostics.some(d => /parse-invalid/.test(d.code)));
  }
  const text = run(root, '--format', 'text');
  assert.equal(text.status, 2);
  assert.doesNotMatch(text.stdout, /^Summary:/m);
});

test('file scope pins sibling fixture imports without scanning helper tests or executing config', t => {
  const root = fixture(t), tests = path.join(root, 'tests'), fixtures = path.join(root, 'fixtures');
  fs.mkdirSync(tests); fs.mkdirSync(fixtures);
  const helper = path.join(fixtures, 'base.ts');
  const fixtureBytes = "import {test as base} from '@playwright/test';export const test=base.extend({});test.only('helper',()=>{});";
  fs.writeFileSync(helper, fixtureBytes);
  fs.writeFileSync(path.join(fixtures, 'index.ts'), "export {test} from './base';");
  const file = path.join(tests, 'case.spec.ts');
  fs.writeFileSync(file, "import {test} from '../fixtures';test.only('target',async({page})=>{await page.goto('/');});");
  const marker = path.join(root, 'config-executed');
  fs.writeFileSync(path.join(root, 'eslint.config.mjs'), `import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(marker)},'unexpected');export default [];`);
  const result = run(file);
  assert.equal(result.status, 1, result.stderr + result.stdout);
  const report = JSON.parse(result.stdout);
  assert.equal(report.files, 1);
  assert.equal(report.counts.p0, 1);
  assert.equal(report.findings.length, 1);
  assert.equal(report.findings[0].file, file);
  assert.equal(report.project.configurationExecuted, false);
  assert.equal(fs.existsSync(marker), false);
  assert.equal(fs.readFileSync(helper, 'utf8'), fixtureBytes);
});
