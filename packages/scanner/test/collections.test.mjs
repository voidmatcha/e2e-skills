// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { collections } from '../src/collections.mjs';
function run(text, name = 'case.spec.ts') {
  const filename = '/pinned/' + name, bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return collections(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const body = text => `import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n${text}\n});`;
test('absence shapes remain review candidates even with positive proof or intended empty states', () => {
  const r = run(body("const row=page.getByRole('row');\nawait expect(row).toBeVisible();\nawait expect(row).not.toBeVisible();\nawait expect(row).not.toBeAttached();\nawait expect(row).toBeHidden();\nawait expect(row).toHaveCount(0);"));
  assert.deepEqual(r.diagnostics, []);
  assert.deepEqual(r.findings.map(f => [f.patternId, f.severity, f.disposition, f.line]),
    [5,6,7,8].map(line => ['#4i','P1','candidate',line]));
});
test('only actual negative/zero shapes match; positive count/attachment and inverted hidden do not', () => {
  assert.deepEqual(run(body("const row=page.locator('a');expect(row).toBeVisible();expect(row).toBeAttached();expect(row).not.toBeHidden();expect(row).not.toHaveCount(0);expect(row).toHaveCount(1);")).findings, []);
});
test('awaited locator.all and Cypress each remain candidates, not proof of skipped assertions', () => {
  const r = run(body("for(const row of await page.locator('a').all()){await row.click();}\nfor(const row of items){expect(row).toBeTruthy();}"));
  assert.deepEqual(r.findings.map(f=>f.patternId), ['#4k']);
  assert.deepEqual(r.diagnostics, []);
  const c = run("cy.get('a').should('not.exist');\ncy.get('a').should('not.be.visible');\ncy.get('a').each(item=>{});", 'case.cy.ts');
  assert.deepEqual(c.findings.map(f=>f.patternId), ['#4i','#4i','#4k']);
  assert.deepEqual(c.diagnostics, []);
});
test('foreign/shadowed bindings, custom collections and inert text cannot borrow provenance', () => {
  for (const text of [
    "import {test,expect} from 'vitest';test('x',async({page})=>{expect(page.locator('a')).not.toBeVisible();});",
    body("function helper(page,expect){expect(page.locator('a')).toBeHidden();}"),
    body("for(const row of await custom.all()){expect(row).toBeTruthy();}"),
    body("const text=\"expect(page.locator('a')).toBeHidden()\";/* for(const x of await page.locator('a').all()){} */"),
  ]) assert.deepEqual(run(text).findings, [], text);
  for (const text of ["function helper(cy){cy.get('a').each(x=>{});cy.get('a').should('not.exist');}",
    "const cy={get(){return this},each(){},should(){}};cy.get('a').each(x=>{});"])
    assert.deepEqual(run(text,'case.cy.ts').findings, []);
});
test('mutable, type-only, invalid and unavailable provenance remain incomplete', () => {
  for (const text of [body("const row=page.locator('a');row.all=custom;for(const x of await row.all()){}"),
    "import {expect,type Locator} from '@playwright/test';function f(row:Locator){expect(row).toBeHidden();}",
    'const =']) {
    const r=run(text);assert.deepEqual(r.findings,[]);assert.ok(r.diagnostics.length,text);
  }
  const c=run("cy.get=custom;cy.get('a').each(x=>{});",'case.cy.ts');
  assert.deepEqual(c.findings,[]);assert.ok(c.diagnostics.length);
  assert.match(collections(Buffer.from(''), 'x.ts').diagnostics[0].message,/pinned scope/);
});
