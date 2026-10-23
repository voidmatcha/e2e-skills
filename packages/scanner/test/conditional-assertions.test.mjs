// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';
function run(text, name = 'case.spec.ts') {
  const filename = '/pinned/' + name, bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return conditionalAssertions(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const body = text => `import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n${text}\n});`;
test('inline visibility and assertion branches remain independent P0 candidates', () => {
  const r = run(body("if(await page.locator('a').isVisible()){await page.locator('a').click();}\nif(flag){await expect(page).toHaveURL('/');}\nif(await page.locator('a').isVisible()){await expect(page.locator('a')).toBeVisible();}"));
  assert.deepEqual(r.diagnostics, []);
  assert.deepEqual(r.findings.map(f=>[f.line,f.variant]), [[3,'inline-visibility-condition'],[4,'conditional-assertion'],[5,'inline-visibility-condition'],[5,'conditional-assertion']]);
  assert.ok(r.findings.every(f=>f.patternId==='#5a' && f.severity==='P0' && f.disposition==='candidate'));
});
test('six multiline boolean if conditions retain the read-line anchor; other consumers are excluded', () => {
  for (const method of ['isVisible','isEnabled','isChecked','isDisabled','isEditable','isHidden']) {
    const r=run(body(`if (\n await page.locator('a').${method}()\n) console.log('state');`));
    assert.deepEqual(r.diagnostics, []);
    assert.deepEqual(r.findings.map(f=>[f.line,f.variant]), [[4,'multiline-boolean-condition']]);
  }
  assert.deepEqual(run(body("while(\n await page.locator('a').isVisible()\n) break;\nconst x=await page.locator('a').isVisible();\nif(await page.locator('a').isEnabled()) console.log('state');")).findings, []);
});
test('logical and ternary branches accept proven aliased expect and Cypress should', () => {
  const r=run("import {expect as verify} from '@playwright/test';\nflag && verify(1).toBe(1);\nflag ? recover() : verify(1).toBe(1);\nflag || verify(1).toBe(1);");
  assert.deepEqual(r.findings.map(f=>[f.line,f.variant]), [[2,'logical-assertion'],[3,'ternary-assertion']]);
  assert.deepEqual(r.diagnostics, []);
  assert.deepEqual(run("if(flag){cy.get('a').should('exist');}\nflag && cy.get('a').should('exist');",'case.cy.ts').findings.map(f=>f.variant), ['conditional-assertion','logical-assertion']);
});
test('foreign, shadowed, custom and inert assertion/receiver shapes cannot borrow provenance', () => {
  for (const text of [
    "import {test,expect} from 'vitest';test('x',async({page})=>{if(await page.locator('a').isVisible()){expect(1).toBe(1);}});",
    body("function helper(expect,page){if(await page.locator('a').isVisible()){expect(1).toBe(1);}}"),
    body("const custom={isVisible(){return true}};if(custom.isVisible()) console.log('x');"),
    body('const text="if(flag) expect(1).toBe(1)"; /* flag && expect(1).toBe(1); */'),
    body("if(flag){const result=expect;}"),
  ]) assert.deepEqual(run(text).findings, [], text);
  assert.deepEqual(run("function helper(cy){if(flag){cy.get('a').should('exist');}}",'case.cy.ts').findings, []);
});
test('deferred helpers, generic assert, awaited dataflow and type-only receiver gaps are diagnostic', () => {
  for (const text of [body('if(flag){const later=()=>expect(1).toBe(1);}'),
    "import {expect as verify} from '@playwright/test';if(flag){const later=()=>verify(1).toBe(1);}",
    body('function check(){expect(1).toBe(1);} if(flag){check();}'),
    body('if(flag){assert.ok(value);}'),
    body('if(flag){expect.soft(1).toBe(1);}'),
    body("if(flag){console.log('yes');}else{expect(1).toBe(1);}"),
    body("const visible=await page.locator('a').isVisible();if(visible){console.log('x');}"),
    "import {type Locator} from '@playwright/test';function f(row:Locator){if(row.isVisible()){work();}}",
    'const =']) {
    const r=run(text);assert.deepEqual(r.findings, []);assert.ok(r.diagnostics.length,text);
  }
  assert.match(conditionalAssertions(Buffer.from(''),'x.ts').diagnostics[0].message,/pinned scope/);
});
test('mutated receiver and Cypress runtime identity fail closed with diagnostics', () => {
  for (const [text,name] of [[body("page.locator=custom;if(page.locator('a').isVisible()) work();"),'case.spec.ts'],
    ["cy.get=custom;if(flag){cy.get('a').should('exist');}",'case.cy.ts']]) {
    const r=run(text,name);assert.deepEqual(r.findings,[]);assert.ok(r.diagnostics.length);
  }
});

test('Cypress inline then and conditional registration retain review candidates', () => {
  for (const code of [
    "if(!isMobile()){cy.get('balance').invoke('text').then(x=>expect(startBalance).to.match(/balance/));}",
    "if(isMobile()){it('mobile',()=>{cy.get('row').should('be.visible');});}",
    "if(flag){cy.get('row').should(row=>expect(row).to.exist);}",
    "if(flag){describe('group',()=>{it('case',()=>{expect(value).to.equal(1);});});}",
    "if(flag){cy.get('row').then(function(row){expect(row).to.exist;});}",
  ]) {
    const result=run(code,'case.cy.ts');
    assert.deepEqual(result.diagnostics, [],code);
    assert.deepEqual(result.findings.map(f=>[f.patternId,f.severity,f.disposition,f.variant]), [['#5a','P0','candidate','conditional-assertion']],code);
  }
});
test('Cypress callbacks and ambient Chai cannot borrow local or foreign provenance', () => {
  for (const code of [
    "if(flag){custom.then(x=>expect(x).to.exist);}",
    "function helper(cy){if(flag){cy.get('a').then(x=>expect(x).to.exist);}}",
    "function helper(expect){if(flag){cy.get('a').then(x=>expect(x).to.exist);}}",
    "function helper(it){if(flag){it('x',()=>expect(1).to.equal(1));}}",
    "import {expect} from 'vitest';if(flag){cy.get('a').then(x=>expect(x).toBe(1));}",
    "const expect=x=>x;if(flag){cy.get('a').then(x=>expect(x));}",
    "const it=custom;if(flag){it('x',()=>expect(1).to.equal(1));}",
    "if(flag){cy['get']('a').then(x=>expect(x).to.exist);}",
    "if(flag){cy.get('a')?.then(x=>expect(x).to.exist);}",
    "if(flag){cy.get('a').then?.(x=>expect(x).to.exist);}",
    "if(flag){cy.get('a').then(()=>{const later=()=>expect(1).to.equal(1);});}",
  ]) assert.deepEqual(run(code,'case.cy.ts').findings,[],code);
  assert.deepEqual(run("if(flag){expect(1).to.equal(1);}").findings,[]);
  assert.deepEqual(run("import {expect} from 'vitest';if(flag){expect(1).toBe(1);}",'case.cy.ts').findings,[]);
});
test('Cypress mutable globals and ambient Chai writes fail closed', () => {
  for (const prefix of [
    'expect=custom;', 'expect.to=custom;', 'globalThis.expect=custom;',
    "Object.assign(expect,{to:custom});", "Reflect.set(globalThis,'expect',custom);",
    'const alias=expect;alias.to=custom;', 'const alias=globalThis;alias.expect=custom;',
    'const {expect:alias}=globalThis;alias.to=custom;',
    'let alias;alias=expect;alias.to=custom;',
    'delete window.expect;',
  ]) {
    const result=run(prefix+"if(flag){cy.get('a').then(x=>expect(x).to.exist);}",'case.cy.ts');
    assert.deepEqual(result.findings,[],prefix);
    assert.ok(result.diagnostics.length,prefix);
  }
  for (const code of [
    "cy.get=custom;if(flag){cy.get('a').then(x=>expect(x).to.exist);}",
    "it=custom;if(flag){it('x',()=>expect(1).to.equal(1));}",
  ]) {const result=run(code,'case.cy.ts');assert.deepEqual(result.findings,[]);assert.ok(result.diagnostics.length);}
});
test('irrelevant callbacks do not create assertion-analysis gaps, deferred assertions still do', () => {
  assert.deepEqual(run("if(flag){cy.get('a').then(x=>x.text());}",'case.cy.ts').diagnostics,[]);
  assert.deepEqual(run(body("if(flag){const later=()=>42;}")).diagnostics,[]);
  for (const code of [
    "if(flag){custom.then(x=>expect(x).to.exist);}",
    "if(flag){const later=()=>expect(1).to.equal(1);}",
    "function helper(){expect(1).to.equal(1);}if(flag){helper();}",
  ]) assert.ok(run(code,'case.cy.ts').diagnostics.length,code);
});


test('proven assertions in both branches share the whole-if candidate without redundant else gaps', () => {
  for (const code of [
    "if(isMobile()){cy.getBySel('sidenav-home').should('not.exist');}else{cy.getBySel('sidenav-home').should('be.visible');}",
    "if(isMobile()){cy.getBySel('drawer').should('not.exist');}else{cy.getBySel('filter').click();cy.getBySel('range').should('not.exist');}",
    body("if(flag){expect(1).toBe(1);}else{expect(2).toBe(2);}"),
  ]) {
    const result=run(code,'case.cy.ts');
    assert.deepEqual(result.diagnostics,[],code);
    assert.equal(result.findings.length,1,code);
    const finding=result.findings[0];
    assert.equal(finding.variant,'conditional-assertion');
    assert.ok(code.slice(finding.start,finding.end).includes('else'));
    assert.equal(finding.disposition,'candidate');
  }
});
test('else-only assertion mapping and deferred else analysis retain their specific gaps', () => {
  for (const code of [
    "if(flag){cy.get('a').click();}else{cy.get('a').should('exist');}",
    "if(flag){cy.get('a').should('exist');}else{const later=()=>expect(1).to.equal(1);}",
    "if(flag){cy.get('a').should('exist');}else{helper();}function helper(){expect(1).to.equal(1);}",
  ]) assert.ok(run(code,'case.cy.ts').diagnostics.length,code);
  assert.deepEqual(run("if(flag){cy.get('a').click();}else{cy.get('a').should('exist');}",'case.cy.ts').findings,[]);
});
