// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { inventory } from '../src/inventory.mjs';
import { readCandidate } from '../src/read-candidate.mjs';

const cli = new URL('../src/cli.mjs', import.meta.url);
function fixture() {
  // Keep owned test evidence outside the checkout.
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-node-cli-')));
  const file = path.join(root, 'focus.spec.ts');
  fs.writeFileSync(file, "import {test} from '@playwright/test';\ntest.only('example', async () => {});\n");
  return { root, file };
}
const run = args => spawnSync(process.execPath, [cli.pathname, ...args], { encoding: 'utf8' });

test('CLI reports raw candidates and always marks this preview incomplete', () => {
  const { root } = fixture();
  const marker = path.join(root, 'config-executed');
  fs.writeFileSync(path.join(root, 'eslint.config.mjs'), `import fs from 'node:fs'; fs.writeFileSync(${JSON.stringify(marker)}, 'bad'); export default [];`);
  for (const policy of ['none', 'any', 'p0', 'p0-candidate']) {
    const result = run(['--experimental-focused', root, '--fail-on', policy]);
    assert.equal(result.status, 2, result.stderr);
    const report = JSON.parse(result.stdout);
    assert.equal(report.complete, false);
    assert.equal(report.findings.length, 1);
    assert.equal(report.findings[0].patternId, '#7');
    assert.equal(report.failOn, policy);
    assert.equal(report.project.configurationExecuted, false);
    assert.ok(report.project.configurationFiles.some(item => item.path === path.join(root, 'eslint.config.mjs') && /^[a-f0-9]{64}$/.test(item.sha256)));
    assert.match(report.incomplete[0], /parity/);
  }
  assert.equal(fs.existsSync(marker), false);
});

test('empty, invalid, malformed and help inputs cannot become clean scans', () => {
  const { root, file } = fixture();
  fs.writeFileSync(file, 'export const example = true;\n');
  let result = run(['--experimental-focused', root]);
  assert.equal(result.status, 2);
  assert.equal(JSON.parse(result.stdout).findings.length, 0);
  fs.writeFileSync(file, 'function (');
  result = run(['--experimental-focused', root]);
  assert.equal(result.status, 2);
  assert.ok(JSON.parse(result.stdout).incomplete.some(reason => reason.startsWith('analysis incomplete:')));
  for (const args of [[], [root], ['--experimental-focused', root, '--fail-on', 'unknown'],
    ['--experimental-focused', root, '--fail-on', 'none', '--fail-on', 'p0']]) assert.equal(run(args).status, 2);
  result = run(['--help']);
  assert.equal(result.status, 0);
  assert.match(result.stdout, /Development preview/);
});

test('CLI follows pinned fixture and re-export provenance without loading project code', () => {
  const { root, file } = fixture();
  fs.writeFileSync(path.join(root, 'fixture.ts'), "import {test as base} from '@playwright/test';\nexport const test = base.extend({});\n");
  fs.writeFileSync(path.join(root, 'barrel.ts'), "export {test} from './fixture';\n");
  fs.writeFileSync(file, "import {test} from './barrel';\ntest.only('example', async () => {});\nfunction f(test) { test.only('shadow'); }\n");
  const result = run(['--experimental-focused', root]);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.findings.map(item => [item.line, path.basename(item.file)]), [[2, 'focus.spec.ts']]);
  fs.writeFileSync(path.join(root, 'fixture.js'), "export const test = custom;\n");
  const ambiguous = JSON.parse(run(['--experimental-focused', root]).stdout);
  assert.equal(ambiguous.findings.length, 0);
  assert.ok(ambiguous.incomplete.some(reason => reason.includes('could not establish its contract')));
});

test('parser bytes must match the inventoried regular file', () => {
  const { root, file } = fixture();
  const candidate = inventory(root).candidates[0];
  assert.equal(readCandidate(candidate).toString(), fs.readFileSync(file, 'utf8'));
  fs.writeFileSync(file, 'changed');
  assert.throws(() => readCandidate(candidate), /drift/);
  assert.throws(() => readCandidate({ path: file, identity: {} }), /invalid candidate/);
});

test('static preview retains focus and candidates while recording justified waits', () => {
  const {root, file} = fixture();
  fs.writeFileSync(file, "import {test} from '@playwright/test';\n// JUSTIFIED: never excludes focus\ntest.only('focused',async()=>{});\ntest('wait',async({page})=>{\n// JUSTIFIED: deliberate reproduction delay\nawait page.waitForTimeout(1);\nawait page.waitForTimeout(2);\n});\n");
  const cypress = path.join(root, 'sleep.cy.ts');
  fs.writeFileSync(cypress, 'cy.visit("/");\ncy.wait(delay);\n');
  const result = run(['--experimental-static', root, '--fail-on', 'none']);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.implementedPatterns, ['#7','#9','#9b','#8c','#4f','#10b','#19','#3b','#11c','#9c','#5b','#8a','#8b','#4a','#4b','#15','#16','#4h','#17','#10e','#6','#10a','#3','#4g','#18','#10d','#10f','#4c-4e','#4i','#4k','#10c','#5a','#14']);
  assert.equal(report.findings.filter(x => x.patternId === '#7').length, 1);
  assert.equal(report.findings.filter(x => x.patternId === '#9').length, 1);
  assert.equal(report.findings.find(x => x.patternId === '#9b').disposition, 'candidate');
  assert.equal(report.suppressed.length, 1);
  assert.deepEqual(report.suppressed[0].justification, { line: 6, markerLine: 5, kind: 'previous-line' });
  assert.equal(report.counts.confirmed, 2);
  assert.equal(report.counts.triage, 1);
  assert.equal(report.complete, false);
});

test('static preview keeps JUSTIFIED P0 as a review candidate', () => {
  const {root, file} = fixture();
  fs.writeFileSync(file, "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n// JUSTIFIED: intentional weak assertion reproduction\nexpect(page.locator('x')).toBeTruthy();\nexpect(page.locator('x')).toBeVisible;\n});\n");
  const result = run(['--experimental-static', root]);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.findings.map(x => [x.patternId,x.disposition]), [['#8c','confirmed'],['#4f','justified-review']]);
  assert.equal(report.counts.p0, 1);
  assert.equal(report.counts.p0Candidate, 1);
  assert.equal(report.suppressed.length, 0);
});

test('public JSON preserves justification positions without copying credential literals or comments', () => {
  const { root, file } = fixture();
  const sentinel = 'FAKE_ONLY_NOT_A_CREDENTIAL_310_SENTINEL';
  const source = "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n" +
    `// JUSTIFIED: ${sentinel}\nawait page.waitForTimeout(1);\n` +
    `// JUSTIFIED: ${sentinel}\nexpect(page.locator('x')).toBeTruthy();\n` +
    `await page.getByLabel('Password').fill('${sentinel}');\n});\n`;
  fs.writeFileSync(file, source);
  const result = run(['--experimental-static', root]);
  assert.equal(result.status, 2, result.stderr);
  assert.ok(!result.stdout.includes(sentinel));
  assert.ok(!result.stderr.includes(sentinel));
  const report = JSON.parse(result.stdout);
  assert.ok(report.findings.some(f => f.patternId === '#14' && f.disposition === 'candidate'));
  assert.ok(report.findings.some(f => f.patternId === '#4f' && f.disposition === 'justified-review' &&
    f.justification.markerLine === 5 && !('reason' in f.justification)));
  assert.ok(report.suppressed.some(f => f.patternId === '#9' && f.justification.markerLine === 3 &&
    !('reason' in f.justification)));
  assert.equal(fs.readFileSync(file, 'utf8'), source);
});

test('public incomplete diagnostics do not interpolate parser tokens or import source values', () => {
  const { root } = fixture();
  const sentinel = 'SYNTHETIC_ONLY_310_DIAGNOSTIC_CANARY';
  const file = path.join(root, 'invalid.spec.tsx');
  for (const source of [`const view = <${sentinel}>;`,
    `import {test} from '${sentinel}';test.only('x',()=>{});`]) {
    fs.writeFileSync(file, source);
    const result = run(['--experimental-static', root]);
    assert.equal(result.status, 2);
    assert.ok(!result.stdout.includes(sentinel), result.stdout);
    assert.ok(!result.stderr.includes(sentinel), result.stderr);
    assert.equal(JSON.parse(result.stdout).complete, false);
    assert.equal(fs.readFileSync(file, 'utf8'), source);
  }
});

test('static preview retains numeric and attachment candidates without promoting them', () => {
  const {root, file} = fixture();
  fs.writeFileSync(file, "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\nexpect(await page.locator('li').count()).toBeGreaterThanOrEqual(0);\nawait expect(page.locator('li')).toBeAttached();\n});\n");
  const result = run(['--experimental-static', root, '--fail-on', 'any']);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.findings.map(x => [x.patternId,x.severity,x.disposition]),
    [['#4a','P0','candidate'],['#4b','P1','candidate'],['#4c-4e','P1','candidate']]);
  assert.equal(report.counts.confirmed, 0);
  assert.equal(report.counts.triage, 3);
  assert.equal(report.complete, false);
});

test('static preview separates floating operations from awaited aggregate controls', () => {
  const {root, file} = fixture();
  fs.writeFileSync(file, "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\nconst row=page.getByTestId('row');\nrow.click();\nexpect(row).toBeVisible();\nawait Promise.all([row.click(),expect(row).toBeVisible()]);\n});\n");
  const result = run(['--experimental-static', root]);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.findings.map(x => [x.patternId,x.line,x.disposition]),
    [['#16',4,'candidate'],['#15',5,'confirmed']]);
  assert.equal(report.counts.confirmed, 1);
  assert.equal(report.counts.triage, 1);
  assert.equal(report.complete, false);
});

test('static preview combines Page reads and Cypress assignment with source provenance', () => {
  const {root, file} = fixture();
  fs.writeFileSync(file, "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\nexpect(page.url()).toContain('/done');\nawait page.click('button');\nawait expect.poll(()=>page.url()).toContain('/done');\n});\n");
  fs.writeFileSync(path.join(root,'chain.cy.ts'), "const saved=cy.get('button');\nfunction shadow(cy){const ignored=cy.get('button');}\n");
  const result = run(['--experimental-static', root]);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.findings.map(x => [x.patternId,path.basename(x.file),x.line]),
    [['#10e','chain.cy.ts',1],['#4h','focus.spec.ts',3],['#17','focus.spec.ts',4]]);
  assert.equal(report.counts.confirmed, 3);
  assert.equal(report.complete, false);
});

test('static preview retains DOM and swallowed-error candidates for semantic review', () => {
  const {root, file} = fixture();
  fs.writeFileSync(file, "import {test} from '@playwright/test';\ntest('x',async({page})=>{\nawait page.evaluate(()=>document.querySelector('button'));\nawait setup().catch(()=>{});\n});\n");
  const result = run(['--experimental-static', root]);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.findings.map(x => [x.patternId,x.severity,x.disposition]),
    [['#6','P1','candidate'],['#3','P0','candidate']]);
  assert.equal(report.counts.confirmed, 0);
  assert.equal(report.counts.triage, 2);
  assert.equal(report.complete, false);
});

test('static preview reports proven Playwright timeout zero without inventing a Cypress verdict', () => {
  const {root, file} = fixture();
  fs.writeFileSync(file, "import {test} from '@playwright/test';\ntest('x',async({page})=>{\nawait page.getByTestId('save').click({timeout:0});\n});\n");
  fs.writeFileSync(path.join(root,'deadline.cy.ts'), "cy.get('button',{timeout:0}).should('be.visible');\n");
  const result = run(['--experimental-static', root]);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.findings.map(x => [x.patternId,path.basename(x.file),x.severity,x.disposition]),
    [['#4g','focus.spec.ts','P1','confirmed']]);
  assert.equal(report.complete, false);
});

test('focused registration retains receiver-dependent findings inside its callback', () => {
  const {root, file} = fixture();
  fs.writeFileSync(file, "import {test,expect} from '@playwright/test';\ntest.only('x',async({page})=>{\nconst row=page.getByTestId('row');\nrow.click();\nexpect(row).toBeVisible();\nawait row.click({timeout:0});\n});\n");
  const result = run(['--experimental-static', root]);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.deepEqual(report.findings.map(x => [x.patternId,x.disposition]),
    [['#7','confirmed'],['#16','candidate'],['#15','confirmed'],['#4g','confirmed']]);
  assert.equal(report.complete, false);
});


test('CLI accounts after structural dedupe and keeps unclassified variants separate', () => {
  const { root, file } = fixture();
  fs.writeFileSync(file, "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\nawait page.waitForTimeout(1); await page.waitForTimeout(2);\nexpect(page.getByTestId('a')).toBeVisible(); page.click('a');\nawait page.waitForLoadState('networkidle'); await page.waitForLoadState('networkidle');\n});\n");
  const result = run(['--experimental-static', root]);
  assert.equal(result.status, 2, result.stderr);
  const report = JSON.parse(result.stdout);
  assert.equal(report.findings.filter(x => x.patternId === '#9').length, 1);
  assert.equal(report.findings.filter(x => ['#15','#16'].includes(x.patternId)).length, 1);
  assert.equal(report.findings.filter(x => x.patternId === '#9c').length, 2);
  assert.equal(report.duplicates.length, 2);
  assert.equal(report.counts.total, report.findings.length);
  assert.deepEqual(report.duplicates.map(x => x.ruleClass), ['playwright-wait','missing-playwright-await']);
});

test('bounded static clean execution is PARTIAL coverage, never a complete full scan', () => {
  const {root,file}=fixture();
  fs.writeFileSync(file,"import {test,expect} from '@playwright/test';\ntest('clean',async({page})=>{await expect(page.getByRole('button')).toBeVisible();});\n");
  const result=run(['--bounded-static',root]);
  assert.equal(result.status,0,result.stderr||result.stdout);
  const report=JSON.parse(result.stdout);
  assert.equal(report.schema,'e2e-skills-node-bounded-v1');
  assert.equal(report.status,'PARTIAL');
  assert.deepEqual(report.execution,{complete:true,exitCode:0,incomplete:[],diagnostics:[]});
  assert.equal(report.coverage.complete,false);
  assert.equal(report.coverage.ruleSlices.length,33);
  assert.ok(report.coverage.limitations.some(reason=>/69 legacy call variants/.test(reason)));
  for(const field of ['complete','exitCode','incomplete','implementedPatterns']) assert.ok(!(field in report),field);
  assert.equal(report.findings.length,0);
  const preview=JSON.parse(run(['--experimental-static',root]).stdout);
  assert.equal(preview.schema,'e2e-skills-node-preview-v1');assert.equal(preview.complete,false);assert.equal(preview.exitCode,2);
});

test('bounded static confirmed and candidate policies use the existing accounting without promotion', () => {
  const {root,file}=fixture();
  for(const [source,policies,expected] of [
    ["import {test} from '@playwright/test';test.only('x',()=>{});",['none','any','p0','p0-candidate'],[0,1,1,1]],
    ["import {test,expect} from '@playwright/test';test('x',async({page})=>{expect(await page.locator('li').count()).toBeGreaterThanOrEqual(0);});",['any','p0','p0-candidate'],[0,0,1]],
  ]) {
    fs.writeFileSync(file,source);
    for(let index=0;index<policies.length;index++) {
      const result=run(['--bounded-static',root,'--fail-on',policies[index]]),report=JSON.parse(result.stdout);
      assert.equal(result.status,expected[index],result.stdout);
      assert.equal(report.execution.complete,true);assert.equal(report.execution.exitCode,expected[index]);
      assert.equal(report.status,'PARTIAL');assert.equal(report.coverage.complete,false);
      assert.equal(report.failOn,policies[index]);
    }
  }
});

test('bounded diagnostics remain execution errors under none, including parse and uncertain provenance', () => {
  const {root,file}=fixture();
  for(const source of ['function (',"import {test} from './missing';test.only('x',()=>{});",
    "import {test} from '@playwright/test';const alias=test;alias.only=custom;test.only('x',()=>{});"]) {
    fs.writeFileSync(file,source);
    const result=run(['--bounded-static',root,'--fail-on','none']),report=JSON.parse(result.stdout);
    assert.equal(result.status,2,result.stdout);assert.equal(report.execution.complete,false);
    assert.ok(report.execution.incomplete.some(reason=>reason.startsWith('analysis incomplete:')));
    assert.ok(report.execution.incomplete.every(reason=>!reason.startsWith('development preview:')));
  }
  assert.equal(run(['--bounded-static',path.join(root,'missing'),'--fail-on','none']).status,2);
});

test('bounded static catches real source drift at the final revalidation boundary', () => {
  const {root,file}=fixture();
  const hookRoot=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'e2e-node-cli-drift-hook-')));
  const hook=path.join(hookRoot,'hook.mjs');
  // Test-only loader changes source at the precise pre-revalidation boundary.
  // The actual inventory/read/analysis/revalidate implementations still run.
  fs.writeFileSync(hook,`import {registerHooks} from 'node:module';\nregisterHooks({load(url,context,next){const result=next(url,context);if(url.endsWith('/src/inventory.mjs')){const source=Buffer.from(result.source).toString('utf8');return {...result,source:source.replace('export function revalidate(expected) {',${JSON.stringify('export function revalidate(expected) { fs.appendFileSync('+JSON.stringify(file)+', "\\n// drift at boundary\\n");')})};}return result;}});\n`);
  const result=spawnSync(process.execPath,['--import',hook,cli.pathname,'--bounded-static',root,'--fail-on','none'],{encoding:'utf8'});
  assert.equal(result.status,2,result.stderr||result.stdout);
  const report=JSON.parse(result.stdout);
  assert.equal(report.execution.complete,false);
  assert.ok(report.execution.incomplete.some(reason=>reason.startsWith('identity-drift:')),result.stdout);
  assert.ok(report.execution.diagnostics.some(item=>item.code==='identity-drift' && item.detector==='revalidate' && item.file===file));
  assert.match(fs.readFileSync(file,'utf8'),/drift at boundary/);
});

test('bounded static preserves privacy and never executes project configuration or probes', () => {
  const {root,file}=fixture(),marker=path.join(root,'executed');
  const sentinel='SYNTHETIC_ONLY_BOUNDED_SECRET';
  fs.writeFileSync(path.join(root,'eslint.config.mjs'),`import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(marker)},'bad');export default [];`);
  fs.writeFileSync(file,"import {test} from '@playwright/test';\ntest('x',async({page})=>{\n"+
    `// JUSTIFIED: ${sentinel}\nawait page.waitForTimeout(1);\nawait page.getByLabel('Password').fill('${sentinel}');\n});\n`);
  const source=fs.readFileSync(file,'utf8');
  const result=run(['--bounded-static',root,'--fail-on','none']);
  // Non-assertion calls do not require assertion provenance; privacy and no-execution still hold.
  assert.equal(result.status,0,result.stderr||result.stdout);
  assert.ok(!result.stdout.includes(sentinel));assert.ok(!result.stderr.includes(sentinel));
  const report=JSON.parse(result.stdout);
  assert.equal(report.execution.complete,true);
  assert.deepEqual(report.execution.diagnostics,[]);
  assert.equal(report.project.configurationExecuted,false);assert.equal(fs.existsSync(marker),false);
  assert.equal(report.suppressed.length,1);assert.equal(report.findings[0].patternId,'#14');
  assert.equal(fs.readFileSync(file,'utf8'),source);
});


test('bounded diagnostics classify parser, imports, mutation and shape without source values', () => {
  const { root, file } = fixture();
  const sentinel = 'SYNTHETIC_ONLY_STRUCTURED_DIAGNOSTIC_SECRET';
  for (const [source, code] of [
    [`const view = <${sentinel}>;`, 'parse-invalid'],
    [`import {test} from '${sentinel}';test.only('x',()=>{});`, 'import-unpinned'],
    [`import {test} from './${sentinel}';test.only('x',()=>{});`, 'import-missing'],
    [`import {test} from '../${sentinel}';test.only('x',()=>{});`, 'import-out-of-scope'],
    [`import {test as ${sentinel}} from '@playwright/test';${sentinel}.only=custom;${sentinel}.only('x',()=>{});`, 'binding-mutable'],
    [`import {test,expect} from '@playwright/test';test('x',async({page})=>{let ${sentinel}='toBeTruthy';expect(page.locator('x'))[${sentinel}]();});`, 'shape-unsupported'],
  ]) {
    fs.writeFileSync(file, source);
    const result = run(['--bounded-static', root, '--fail-on', 'none']);
    assert.equal(result.status, 2, result.stderr || result.stdout);
    assert.ok(!result.stdout.includes(sentinel), result.stdout);
    assert.ok(!result.stderr.includes(sentinel), result.stderr);
    const report = JSON.parse(result.stdout);
    assert.equal(report.execution.complete, false);
    assert.ok(report.execution.diagnostics.some(item => item.code === code), result.stdout);
    for (const item of report.execution.diagnostics) {
      assert.equal(item.file, file);
      assert.deepEqual(Object.keys(item).sort(), ('start' in item ? ['code','detector','file','start'] : ['code','detector','file']));
    }
    const preview = JSON.parse(run(['--experimental-static', root]).stdout);
    assert.ok(!('execution' in preview));
    assert.ok(!('diagnostics' in preview));
  }
});
