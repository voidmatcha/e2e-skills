// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { domQueries } from '../src/dom-queries.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function scan(text, name = 'case.spec.ts') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-dom-')));
  const file = path.join(root, name), bytes = Buffer.from(text);
  fs.writeFileSync(file, bytes);
  const manifest = inventory(root), scope = createScope({ manifest, sources: new Map([[file, bytes]]) });
  return domQueries(bytes, file, { scope });
}
const wrap = body => `import {test} from '@playwright/test';\ntest('x',async({page})=>{\n${body}\n});`;
const ids = result => result.findings.map(x => x.patternId);

test('raw DOM calls remain P1 review candidates, including complex and justified use', () => {
  const result = scan(wrap(`await page.evaluate(()=>document.querySelector('.x'));
await page.waitForFunction(()=>document.querySelectorAll('.item').length>2);
document.getElementById('x');
// JUSTIFIED: cross-element identity requires DOM access
await page.evaluate(()=>document.querySelector('.a')===document.querySelector('.b'));`));
  assert.deepEqual(ids(result), ['#6','#6','#6','#6','#6']);
  assert.ok(result.findings.every(x => x.severity === 'P1' && x.disposition === 'candidate'));
  assert.deepEqual(result.diagnostics, []);
});

test('DOM globals require framework scope and cannot borrow shadowed document identity', () => {
  assert.deepEqual(ids(scan("import {test} from 'vitest'; document.querySelector('.x');")), []);
  assert.deepEqual(ids(scan(wrap(`function f(document){document.querySelector('.x');}
const custom={querySelector(){}};custom.querySelector('x');
const text="document.querySelector('.fake')";
/* document.getElementById('fake'); */`))), []);
  assert.deepEqual(ids(scan(wrap(`const document={querySelector(){}};document.querySelector('.x');`))), []);
  const mutated = scan(wrap(`document.querySelector=custom;document.querySelector('.x');`));
  assert.deepEqual(mutated.findings, []);
  assert.ok(mutated.diagnostics.some(x => /mutated/.test(x.message)));
});

test('positional methods on locator aliases remain candidates, never confirmed', () => {
  const result = scan(wrap(`const rows=page.getByRole('row');
rows.nth(2); rows.first(); rows.last();
page.locator('.row').filter({hasText:'a'}).first();
page.locator('.class'); page.first();`));
  assert.deepEqual(ids(result), ['#10a','#10a','#10a','#10a']);
  assert.ok(result.findings.every(x => x.disposition === 'candidate' && x.severity === 'P1'));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(ids(scan("import type {Locator} from '@playwright/test';function f(row:Locator){row.nth(1)}")), ['#10a']);
});

test('foreign, locally shadowed, mutable and non-locator first methods do not become findings', () => {
  const result = scan(wrap(`database.query().first();
const list={first(){},last(){},nth(){}};list.first();list.last();list.nth(1);
function f(page){page.locator('x').first();}
let row=page.locator('x');row.first();
const literal='.first()'; // .nth(4)`));
  assert.deepEqual(result.findings, []);
  assert.ok(result.diagnostics.length);
  assert.deepEqual(ids(scan("import {test} from 'vitest';test('x',({page})=>page.locator('x').first());")), []);
});

test('bounded Cypress element-producing chains reuse shared global identity', () => {
  const result = scan(`cy.get('.row').first();
cy.get('.row').find('button').last();
cy.contains('Save').filter('.active').first();
cy.task('db').first();
cy.wrap({first(){}}).first();
function f(cy){cy.get('x').first();}`, 'case.cy.ts');
  assert.deepEqual(ids(result), ['#10a','#10a','#10a']);
  assert.ok(result.diagnostics.some(x => /subject producer/.test(x.message)));
  assert.deepEqual(ids(scan("cy.get=custom;cy.get('x').first();", 'case.cy.ts')), []);
});

test('optional/computed calls and document-property provenance are explicitly outside this slice', () => {
  const result = scan(wrap(`document?.querySelector('x'); document['querySelector']('x');
window.document.querySelector('x');
page.locator('x').first?.();page.locator('x')['nth'](1);
page.locator('x').first('unsupported');`));
  assert.deepEqual(result.findings, []);
  assert.ok(result.diagnostics.length >= 6);
  assert.deepEqual(domQueries(Buffer.from('document.querySelector("x");'), 'x.spec.ts').findings, []);
});
