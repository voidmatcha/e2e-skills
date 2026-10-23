// SPDX-License-Identifier: Apache-2.0
import { legacyOracleURL } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { promises } from '../src/promises.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function scan(text) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-promises-')));
  const file = path.join(root, 'case.spec.ts'), bytes = Buffer.from(text);
  fs.writeFileSync(file, bytes);
  const manifest = inventory(root), scope = createScope({ manifest, sources: new Map([[file, bytes]]) });
  return promises(bytes, file, { scope });
}
const wrap = body => `import {test, expect as check} from '@playwright/test';\ntest('x',async({page: screen})=>{\n${body}\n});`;
const labels = result => result.findings.map(x => [x.patternId, x.disposition]);

test('legacy direct page action and Locator alias accounting remains distinct', () => {
  const result = scan("import {test} from '@playwright/test';test('x',async({page})=>{page.locator('button').click();const button=page.locator('button');button.click();});");
  assert.deepEqual(labels(result), [['#16','confirmed'],['#16','candidate']]);
  assert.deepEqual(labels(scan("import {expect,type Locator} from '@playwright/test';function f(row:Locator){expect(row).toBeVisible();}")), [['#15','confirmed']]);
});

test('direct action and async matcher use immutable fixture, locator and expect aliases', () => {
  const result = scan(wrap(`const row=screen.getByRole('row'); const verify=check;
row.click();
verify(row).not.toBeVisible();
check.soft(row).toHaveText('saved');
check(await row).toBeVisible();
await row.click(); await check(row).toBeVisible();
check(3).toBe(3);`));
  assert.deepEqual(labels(result), [['#16','candidate'],['#15','confirmed'],['#15','confirmed'],['#15','confirmed']]);
  assert.deepEqual(result.diagnostics, []);
});

test('observed intrinsic Promise aggregates, returns and parentheses consume direct promises', () => {
  for (const method of ['all','race','allSettled','any']) {
    assert.deepEqual(labels(scan(wrap(`await Promise.${method}([(screen.click('x')), check(screen).toHaveURL('/x')]);`))), []);
    assert.deepEqual(labels(scan(wrap(`return Promise.${method}([screen.click('x')]);`))), []);
    assert.deepEqual(labels(scan(wrap(`await Promise.all([Promise.${method}([screen.click('x')])]);`))), []);
  }
  assert.deepEqual(labels(scan(wrap(`await (screen.click('x')); return (screen.click('x'));`))), []);
  assert.deepEqual(labels(scan(wrap(`const f=()=>screen.click('x');`))), []);
  // An await outside a callback cannot consume a floating call in its body.
  assert.deepEqual(labels(scan(wrap(`await check(async()=>{ screen.click('x'); }).toPass();`))), [['#16','candidate']]);
});

test('consumed unknown POM actions and assertions do not require missing-await provenance', () => {
  const result = scan(`import {test,expect} from './missing-fixture';
test('x',async({eventTypePage})=>{
  await eventTypePage.getByTestId('time').first().waitFor({state:'visible'});
  await expect(eventTypePage).toBeVisible();
  await expect.poll(()=>1).toBe(1);
  const helper=()=>eventTypePage.click('x');
  await Promise.all([eventTypePage.click('x')]);
  return eventTypePage.click('x');
});`);
  assert.deepEqual(result, { findings: [], diagnostics: [] });
});

test('unconsumed unknown receivers and unrelated callback awaits retain diagnostics', () => {
  for (const statement of [
    "eventTypePage.click('x');", "const saved=eventTypePage.click('x');",
    "await arbitrary(eventTypePage.click('x'));",
    "await run(async()=>{eventTypePage.click('x');});",
    "function f(Promise){return Promise.all([eventTypePage.click('x')]);}",
    "Promise.all=custom;await Promise.all([eventTypePage.click('x')]);",
  ]) {
    const result = scan(`import {eventTypePage} from './missing-page';${statement}`);
    assert.deepEqual(result.findings, [], statement);
    assert.ok(result.diagnostics.length, statement);
  }
  const mutable = scan(wrap("screen.click=custom;screen.click('x');"));
  assert.ok(mutable.diagnostics.length);
  assert.ok(scan('async function f(){await (').diagnostics.length);
});

test('typed, deferred, void, optional and computed calls remain candidates', () => {
  const result = scan(wrap(`const deferred=screen.click('x');
void screen.click('x');
screen.click?.('x');
screen['click']('x');
check?.(screen).toBeVisible();
check(screen)['toBeVisible']();
check(screen)?.not.toBeVisible();
check(screen)['not'].toBeVisible();
void check(screen).toBeVisible();
Promise.all([screen.click('x')]);`));
  assert.deepEqual(labels(result), [['#16','candidate'],['#16','candidate'],['#16','candidate'],['#16','candidate'],['#15','candidate'],['#15','candidate'],['#15','candidate'],['#15','candidate'],['#15','candidate'],['#16','candidate']]);
  assert.deepEqual(labels(scan("import type {Page,Locator} from '@playwright/test'; function f(p:Page,l:Locator){p.click('x'); l.click();}")), [['#16','candidate'],['#16','candidate']]);
});

test('foreign and shadowed bindings cannot become Playwright promises', () => {
  assert.deepEqual(labels(scan(`import {test,expect} from 'vitest'; test('x',async({page})=>{page.click('x');expect(page).toBeVisible();});`)), []);
  assert.deepEqual(labels(scan(wrap(`const custom={click(){}};custom.click(); function f(screen,check){screen.click('x');check(screen).toBeVisible();}`))), []);
  assert.deepEqual(labels(scan(wrap(`function f(Promise){return Promise.all([screen.click('x')]);}`))), [['#16','candidate']]);
  assert.deepEqual(labels(scan(wrap(`Promise.all=custom; await Promise.all([screen.click('x')]);`))), [['#16','candidate']]);
  const mutable=scan(wrap(`let row=screen.locator('x'); row.click();`));
  assert.deepEqual(mutable.findings, []);
  assert.ok(mutable.diagnostics.some(x=>/mutable/.test(x.message)));
});

test('retry candidates do not pretend full lifetime or POM coverage', () => {
  const result=scan(wrap(`const saved=screen.click('x'); await saved;
await arbitrary(screen.click('x'));
check.poll(()=>1).toBe(1);
check(()=>1).toPass();
this.page.click('x');`));
  assert.deepEqual(labels(result), [['#16','candidate'],['#16','candidate'],['#15','candidate'],['#15','candidate']]);
  assert.deepEqual(promises(Buffer.from('screen.click();'),'x.spec.ts').findings, []);
});

test('retry assertions preserve consumption, shadowing and callback boundaries', () => {
  const result = scan(wrap(`check.poll(()=>1).toBe(1);
check.poll(()=>1).not.toEqual(2);
check(()=>1).toPass();
await check.poll(()=>1).toBe(1);
return check(()=>1).toPass();`));
  assert.deepEqual(labels(result), Array.from({length:3},()=>['#15','candidate']));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(labels(scan(wrap(`function f(check){check.poll(()=>1).toBe(1); check(()=>1).toPass();}`))), []);
  assert.deepEqual(labels(scan("import {expect} from 'vitest'; expect.poll(()=>1).toBe(1);")), []);
  assert.deepEqual(labels(scan(wrap(`await check(async()=>{check.poll(()=>1).toBe(1);}).toPass();`))), [['#15','candidate']]);
});

test('proven Cypress command chains do not require Playwright promise provenance', () => {
  const result = scan("describe('queue',()=>{it('case',()=>{cy.get('button').click();cy.get('input').clear().type('text');});});");
  assert.deepEqual(result, { findings: [], diagnostics: [] });
  const shadow = scan(wrap("function f(cy){cy.get('button').click();}"));
  assert.deepEqual(shadow.findings, []);
});

test('all matcher and direct action spellings come from the authoritative legacy sets', () => {
  const legacy = fs.readFileSync(fileURLToPath(legacyOracleURL()), 'utf8');
  const matchers = /^PLAYWRIGHT_ASYNC_MATCHERS='([^']+)'/m.exec(legacy)[1].split('|');
  const actionRule = legacy.split('\n').find(line => line.startsWith("run_check P1 '#16' 'Missing await on Playwright action'"));
  const actions = /\\\.\(([^)]+)\)/.exec(actionRule)[1].split('|');
  const result = scan(wrap([...matchers.map(name => `check(screen).${name}();`),
    ...actions.map(name => `screen.${name}();`)].join('\n')));
  assert.equal(result.findings.filter(x => x.patternId === '#15').length, matchers.length);
  assert.equal(result.findings.filter(x => x.patternId === '#16').length, actions.length);
  assert.ok(result.findings.every(x => x.disposition === (x.patternId === '#15' ? 'confirmed' : 'candidate')));
});
