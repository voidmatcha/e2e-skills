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
test('a visibility gate is a candidate only when it gates an assertion; an action-only branch is not', () => {
  // Contract change (pattern-reference #5a): dismissing an optional blocker
  // in an assertion-free branch is not a bypass. Legacy flagged line 3.
  const r = run(body("if(await page.locator('a').isVisible()){await page.locator('a').click();}\nif(flag){await expect(page).toHaveURL('/');}\nif(await page.locator('a').isVisible()){await expect(page.locator('a')).toBeVisible();}"));
  assert.deepEqual(r.diagnostics, []);
  assert.deepEqual(r.findings.map(f=>[f.line,f.variant]), [[4,'conditional-assertion'],[5,'inline-visibility-condition'],[5,'conditional-assertion']]);
  // Assertion-free must be proven: an unresolved helper call may assert.
  const helper = run(body("if(await page.locator('a').isVisible()){await page.locator('a').hover();await snapshot(page.locator('a'));}"));
  assert.deepEqual(helper.findings.map(f=>[f.line,f.variant]), [[3,'inline-visibility-condition']]);
  assert.deepEqual(run(body("if(await page.locator('a').isVisible()){await page.keyboard.press('Escape');console.log('closed');}")).findings, []);
  assert.ok(r.findings.every(f=>f.patternId==='#5a' && f.severity==='P0' && f.disposition==='candidate'));
});
test('six multiline boolean if conditions retain the read-line anchor; other consumers are excluded', () => {
  for (const method of ['isVisible','isEnabled','isChecked','isDisabled','isEditable','isHidden']) {
    const r=run(body(`if (\n await page.locator('a').${method}()\n) await expect(page.locator('b')).toBeVisible();`));
    assert.deepEqual(r.diagnostics, []);
    assert.deepEqual(r.findings.map(f=>[f.line,f.variant]), [[4,'multiline-boolean-condition'],[3,'conditional-assertion']]);
    // An assertion-free branch is not a bypass (pattern-reference #5a).
    assert.deepEqual(run(body(`if (\n await page.locator('a').${method}()\n) console.log('state');`)).findings, []);
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
    body('if(flag){assert.ok(value);}'),
    body("if(flag){console.log('yes');}else{expect(1).toBe(1);}"),
    "import {type Locator} from '@playwright/test';function f(row:Locator){if(row.isVisible()){work();}}",
    'const =']) {
    const r=run(text);assert.deepEqual(r.findings, []);assert.ok(r.diagnostics.length,text);
  }
  assert.match(conditionalAssertions(Buffer.from(''),'x.ts').diagnostics[0].message,/pinned scope/);
});
test('same-file asserting helpers, soft and polled assertions gate like expect; an assertion-free if needs no dataflow', () => {
  // Round 7: these were diagnostics; each now has a decided outcome.
  for (const text of [body('function check(){expect(1).toBe(1);} if(flag){check();}'),
    body('if(flag){expect.soft(1).toBe(1);}'),
    body("if(flag){await expect.poll(async()=>1).toBe(1);}")]) {
    const r=run(text);assert.deepEqual(r.diagnostics, [], text);assert.deepEqual(r.findings.map(f=>f.variant), ['conditional-assertion'], text);
  }
  assert.deepEqual(run(body("const visible=await page.locator('a').isVisible();if(visible){console.log('x');}")), {findings:[],diagnostics:[]});
  assert.deepEqual(run(body("function open(){page.getByRole('button').click();} if(flag){open();}")), {findings:[],diagnostics:[]});
  // A helper calling something unproven, a configure wrapper, and a deferred callback stay diagnostic.
  for (const text of [body('function check(){other();} if(flag){check();}'), body('if(flag){expect.configure({timeout:1})(1).toBe(1);}'),
    body('if(flag){const later=()=>expect(1).toBe(1);}')]) assert.ok(run(text).diagnostics.length, text);
  // test.step runs inline; expect(fn).toPass() owns its callback.
  const step = run(body("if(flag){await test.step('s', async()=>{await expect(page.locator('a')).toBeVisible();});}"));
  assert.deepEqual(step.diagnostics, []);assert.deepEqual(step.findings.map(f=>f.variant), ['conditional-assertion']);
  const pass = run(body("if(flag){await expect(async()=>{await expect(page.locator('a')).toBeVisible();}).toPass();}"));
  assert.deepEqual(pass.diagnostics, []);assert.deepEqual(pass.findings.map(f=>f.variant), ['conditional-assertion']);
});
test('helper calls rooted in a page.route Route, plain data, standard globals or local collections are clean', () => {
  // Round 7: these helpers were transitive-assertion diagnostics.
  for (const text of [
    body("await page.route('**/api', async route => { const json = (status, data) => route.fulfill({status, body: JSON.stringify(data)});\nif (route.request().method() === 'GET') return json(200, {}); return route.continue(); });"),
    body("function jsonResponse(data, status = 200) { return { status, body: JSON.stringify(data) }; }\nconst seen = [];\nfunction note(x) { seen.push(x); console.log(x); }\nif (flag) { note(jsonResponse({})); }"),
  ]) assert.deepEqual(run(text), {findings:[],diagnostics:[]}, text);
  // A parameter or imported value may carry an asserting method (a page
  // object), and an assertion in a nested callback may run later or never.
  for (const text of [
    body("function verify(po) { po.expectLoaded(); } if (flag) { verify(loginPage); }"),
    "import {test,expect} from '@playwright/test';import {helpers} from './missing';function run(){helpers.check();}\ntest('x',async({page})=>{if(flag){run();}});",
    body("function later() { return () => expect(1).toBe(1); } if (flag) { later(); }"),
    body("function forward(route) { route.fulfill({}); } if (flag) { forward(other); }"),
  ]) {
    const r = run(text);
    assert.deepEqual(r.findings, [], text);
    assert.ok(r.diagnostics.some(d => /transitive assertion helper/.test(d.message)), text);
  }
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


test('proven assertions in both branches are not a bypass and leave no redundant else gap', () => {
  // Contract change (pattern-reference #5a): each path asserts, so no path
  // passes silently. Legacy reported one whole-if candidate here.
  for (const code of [
    "if(isMobile()){cy.getBySel('sidenav-home').should('not.exist');}else{cy.getBySel('sidenav-home').should('be.visible');}",
    "if(isMobile()){cy.getBySel('drawer').should('not.exist');}else{cy.getBySel('filter').click();cy.getBySel('range').should('not.exist');}",
    body("if(flag){expect(1).toBe(1);}else{expect(2).toBe(2);}"),
  ]) assert.deepEqual(run(code,'case.cy.ts'), { findings: [], diagnostics: [] }, code);
  // One-sided assertion driven by app state stays a candidate.
  const oneSided = run(body("if(await page.getByRole('alert').isVisible()){await expect(page.getByRole('alert')).toHaveText('Saved');}else{await page.reload();}"));
  assert.deepEqual(oneSided.findings.map(f=>f.variant), ['inline-visibility-condition', 'conditional-assertion']);
});
test('else-only assertion mapping and deferred else analysis retain their specific gaps', () => {
  for (const code of [
    "if(flag){cy.get('a').click();}else{cy.get('a').should('exist');}",
    "if(flag){cy.get('a').should('exist');}else{const later=()=>expect(1).to.equal(1);}",
    "if(flag){cy.get('a').should('exist');}else{helper();}function helper(){expect(1).to.equal(1);}",
  ]) assert.ok(run(code,'case.cy.ts').diagnostics.length,code);
  assert.deepEqual(run("if(flag){cy.get('a').click();}else{cy.get('a').should('exist');}",'case.cy.ts').findings,[]);
});
test('a getAttribute read of an attribute the CSS selector requires nonempty is always truthy', () => {
  // Round 7: getAttribute waits for the element and throws when none matches.
  const gate = locator => body(`const link = ${locator}; const href = await link.getAttribute('href');\nif (href) { await expect(page).toHaveURL(href); }`);
  for (const locator of [`page.locator('a[href^="/blog/"]').first()`, `page.locator('nav').locator("li > a[href='/x']").nth(1)`,
    `page.locator('a[data-x][HREF*=post i]').filter({hasText:'a'})`]) assert.deepEqual(run(gate(locator)), {findings:[],diagnostics:[]}, locator);
  // No attribute guarantee, an empty or negated test, a union, an engine
  // prefix, a non-CSS locator, or an attribute on an ancestor keeps the gate.
  for (const locator of [`page.locator('a').first()`, `page.locator('a[href]')`, `page.locator('a[href^=""]')`,
    `page.locator('a:not([href="/x"])')`, `page.locator('a[href="/x"], button')`, `page.locator('text=a[href="/x"]')`,
    `page.getByRole('link')`, `page.locator('a[href="/x"] span')`, `page.locator('a[href="/x"]').locator('span')`,
    `page.locator('a[title="/x"]')`]) {
    const r = run(gate(locator));
    assert.deepEqual(r.findings.map(f => f.variant), ['conditional-assertion'], locator);
  }
  // A reassigned read or a non-awaited one is not proven.
  assert.deepEqual(run(body(`let href = await page.locator('a[href="/x"]').getAttribute('href'); href = null;\nif (href) { await expect(page).toHaveURL(href); }`)).findings.map(f => f.variant), ['conditional-assertion']);
});
