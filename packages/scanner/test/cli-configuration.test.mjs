// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
const cli = new URL('../src/cli.mjs', import.meta.url);
function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-config-cli-')));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  fs.writeFileSync(path.join(root, 'package.json'), '{}');
  const file = path.join(root, 'ignored.spec.js');
  fs.writeFileSync(file, "import {test} from '@playwright/test';\ntest.only('still scanned', async()=>{});\n");
  const run = (...args) => spawnSync(process.execPath, [cli.pathname, '--scan', file, ...args], {
    encoding:'utf8', timeout:20000, env:{...process.env, E2E_SMELL_FAIL_ON:'p0'},
  });
  return {root, file, run};
}
test('configuration declarations and rule overlap are reported without executing or filtering', t => {
  const {root, file, run} = fixture(t);
  fs.writeFileSync(path.join(root, 'playwright.config.ts'), `import {defineConfig} from '@playwright/test';
export default defineConfig({testIgnore:'**/ignored.spec.js',retries:2,timeout:30000});`);
  fs.writeFileSync(path.join(root, 'eslint.config.mjs'), `export default [{files:['**/*.spec.js'],rules:{'playwright/no-focused-test':'off'}}];`);
  const output = run(); assert.equal(output.status,1,output.stderr);
  const report = JSON.parse(output.stdout);
  assert.equal(report.configurationAnalysis.runnerSelectionApplied,false);
  assert.equal(report.configurationAnalysis.effectiveConfiguration,false);
  assert.equal(report.projectEslint.executed,false);
  const pw = report.configurationAnalysis.configurations.find(item=>item.framework==='playwright');
  assert.ok(pw.observations.some(item=>item.field==='testIgnore' && item.value==='**/ignored.spec.js'));
  assert.ok(report.findings.some(item=>item.file===file && item.patternId==='#7'));
  const eslint = report.configurationAnalysis.configurations.find(item=>item.framework==='eslint');
  assert.equal(eslint.rules[0].enabled,false);
  assert.equal(report.configurationAnalysis.ruleComparison.scannerRulesDisabled,false);
  assert.ok(report.configurationAnalysis.ruleComparison.mappedRules.some(rule=>rule.ruleId==='playwright/no-focused-test' && rule.patternId==='#7'));
  const text = run('--format','text');
  assert.equal(text.status,1,text.stderr);
  assert.match(text.stdout,/Project configuration: STATIC_OBSERVATIONS/);
  assert.match(text.stdout,/effective rule states: NOT EXECUTED/);
});
test('dynamic configuration remains explicit review work without evaluating its source', t => {
  const {root,run} = fixture(t);
  const marker = path.join(root,'unexpected-config-execution');
  fs.writeFileSync(path.join(root,'playwright.config.js'), `import fs from 'node:fs';
fs.writeFileSync(${JSON.stringify(marker)},'executed');
export default {retries: process.env.PRIVATE_CONFIG_SENTINEL, ...loadPrivatePreset()};`);
  const result = run('--fail-on','none');
  assert.equal(result.status,0,result.stderr);
  const report=JSON.parse(result.stdout);
  assert.equal(report.configurationAnalysis.status,'NEEDS_REVIEW');
  assert.ok(report.configurationAnalysis.configurations[0].unknowns.length);
  assert.equal(fs.existsSync(marker),false);
  assert.equal(result.stdout.includes('PRIVATE_CONFIG_SENTINEL'),false);
  assert.equal(report.coverage.complete,false);
});
