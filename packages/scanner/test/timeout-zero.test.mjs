// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { timeoutZero } from '../src/timeout-zero.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
function run(text, name = 'example.spec.ts') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-timeout-zero-')));
  const filename = path.join(root, name); fs.writeFileSync(filename, text);
  const bytes = Buffer.from(text), manifest = inventory(root);
  return timeoutZero(bytes, filename, {scope:createScope({manifest,sources:new Map([[filename,bytes]])})});
}
const body = text => `import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n${text}\n});\n`;

test('argument-free helpers need no timeout receiver proof; possible options still do', () => {
  const absent = run(body("unknownHelper().click(); unknownMatcher().toBeVisible();"));
  assert.deepEqual(absent, { findings: [], diagnostics: [] });
  for (const args of ['{timeout:0}', 'options', '...args']) {
    const possible = run(body(`unknownHelper().click(${args});`));
    assert.deepEqual(possible.findings, []);
    assert.ok(possible.diagnostics.length, args);
  }
});

test('absent or finite timeout options do not demand unknown POM or expect identity', () => {
  const result = run(`import {eventTypePage,expect} from './missing-fixture';
await eventTypePage.getByTestId('time').first().waitFor({state:'visible'});
await eventTypePage.goto('/');
await eventTypePage.goto('/',{timeout:500});
await eventTypePage.fill('input','text');
await expect(eventTypePage).toHaveText('ready');
await expect(eventTypePage).toHaveText('ready',{timeout:500});
await expect(eventTypePage).toBeVisible({visible:true});
await expect(eventTypePage).toBe(1);`);
  assert.deepEqual(result, { findings: [], diagnostics: [] });
});

test('option position filtering retains relevant unknown and mutated receiver diagnostics', () => {
  for (const statement of [
    "eventTypePage.waitFor({timeout:0});", "eventTypePage.goto('/',{timeout:0});",
    "eventTypePage.fill('input','text',{timeout:0});", "eventTypePage.waitFor(options);",
    "expect(eventTypePage).toHaveText('ready',{timeout:0});",
  ]) {
    const result=run(`import {eventTypePage,expect} from './missing-fixture';${statement}`);
    assert.deepEqual(result.findings,[],statement);
    assert.ok(result.diagnostics.length,statement);
  }
  // A zero object in the URL argument is not navigation options.
  assert.deepEqual(run("import {eventTypePage} from './missing';eventTypePage.goto({timeout:0});"),
    { findings: [], diagnostics: [] });
  const mutated=run(body("page.goto=custom;page.goto('/',{timeout:0});"));
  assert.deepEqual(mutated.findings,[]);
  assert.ok(mutated.diagnostics.length);
});

test('literal zero on proven Page/Locator assertions is raw P1; not an immediate-check claim', () => {
  const result = run(body([
    "await expect(page.locator('a')).toHaveText('ready',{timeout:0});",
    "await expect(page.locator('a')).toHaveCount(0,{'timeout':0});",
    "await expect.soft(page.locator('a')).not.toBeVisible({timeout : 0});",
    "await expect(page).toHaveURL('/done',{timeout:0});",
    "await expect(page).toHaveTitle('Done',{timeout:0});",
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f=>[f.patternId,f.severity,f.disposition,f.line]),
    [3,4,5,6,7].map(line=>['#4g','P1','confirmed',line]));
});

test('literal action and navigation options use method-specific argument positions', () => {
  const result = run(body([
    "await page.goto('/',{timeout:0});", "await page.locator('a').click({timeout:0});",
    "await page.fill('input','text',{timeout:0});", "await page.locator('input').fill('text',{timeout:0});",
    "await page.waitForNavigation({timeout:0});", "await page.waitForLoadState('load',{timeout:0});",
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.equal(result.findings.length, 6);
});

test('finite timeouts, standalone options, foreign assertions and shadowed receivers are not #4g', () => {
  for (const text of [body("const options={timeout:0}; await page.goto('/',{timeout:50});"),
    body("test.setTimeout(0); const client={request(){}};client.request({timeout:0});"),
    body("// await expect(page).toHaveURL('/',{timeout:0});\nconst s=\"timeout:0\";"),
    "import {expect} from 'vitest'; expect(custom).toHaveText('x',{timeout:0});",
    body("function helper(page){ page.goto('/',{timeout:0}); }"),
    body("{const expect=custom;expect(page).toHaveURL('/',{timeout:0});}"),
  ]) assert.deepEqual(run(text).findings, [], text);
});

test('Cypress immediate-query semantics stay Phase 2, including the archived probe shape', () => {
  const result = run("cy.get('#status',{timeout:0}).should('have.text','ready');\ncy.get('#missing',{timeout:0}).should('exist');", 'example.cy.ts');
  assert.deepEqual(result, {findings:[],diagnostics:[]});
});

test('Cypress action exclusion shares global provenance and mutation diagnostics', () => {
  assert.deepEqual(run("cy.get('button').click({timeout:0});", 'example.cy.ts'), {findings:[],diagnostics:[]});
  for (const text of [
    "function helper(cy){cy.get('button').click({timeout:0});}",
    "const cy={click(){}};cy.click({timeout:0});",
  ]) assert.deepEqual(run(text, 'example.cy.ts').findings, [], text);
  const mutated = run("cy.click=custom;cy.click({timeout:0});", 'example.cy.ts');
  assert.deepEqual(mutated.findings, []);
  assert.ok(mutated.diagnostics.some(value => /mutated Cypress global: cy/.test(value.message)));
});

test('spread, duplicate, dynamic and computed options remain diagnostic', () => {
  for (const options of ["{timeout:0,...more}","{...more,timeout:0}","{timeout:0,timeout:50}",
    "{timeout:0,[key]:50}","{timeout:value}","{...more}","{[key]:0}","{get timeout(){return 0}}",'options']) {
    const result = run(body(`page.goto('/',${options});`));
    assert.deepEqual(result.findings, [], options);
    assert.match(result.diagnostics[0].message,/literal options/,options);
  }
});

test('type annotations remain candidates; retry wrappers and unsupported matcher signatures are never promoted', () => {
  // Official type provenance selects a review candidate, not a runtime Page.
  // Preserve the original diagnostic and prohibit confirmed promotion.
  const typed = run("import {expect,type Page} from '@playwright/test';function helper(page:Page){expect(page).toHaveURL('/',{timeout:0});}");
  assert.deepEqual(typed.findings.map(item => [item.patternId, item.disposition]), [['#4g', 'candidate']]);
  assert.ok(typed.diagnostics.some(item => item.message === 'type annotation alone does not prove the runtime timeout receiver'));
  assert.equal(typed.findings.filter(item => item.disposition === 'confirmed').length, 0);
  for (const text of [
    body("await expect(async()=>{}).toPass({timeout:0});"),
    body("await expect.poll(()=>1,{timeout:0}).toBe(1);"),
    body("await expect(page.locator('a')).toHaveAttribute('a','b',{timeout:0});"),
  ]) {
    const result=run(text);assert.deepEqual(result.findings,[],text);assert.ok(result.diagnostics.length,text);
  }
});

test('zero within a retry wrapper is still a deadline hazard; #4h retry exclusion is not copied', () => {
  const result = run(body("await expect(async()=>{ await expect(page).toHaveURL('/',{timeout:0}); }).toPass({timeout:1000});"));
  assert.equal(result.findings.length,1);
  assert.deepEqual(result.diagnostics,[]);
});

test('legacy eight-line options lookback and unsupported source stay diagnostic', () => {
  const result = run(body("page.goto('/',{\n"+'\n'.repeat(9)+"timeout:0});"));
  assert.deepEqual(result.findings,[]);assert.match(result.diagnostics[0].message,/eight-line/);
  assert.ok(run('function (').diagnostics.length);
  assert.match(timeoutZero(Buffer.from(''), 'example.ts').diagnostics[0].message,/scope is required/);
});
