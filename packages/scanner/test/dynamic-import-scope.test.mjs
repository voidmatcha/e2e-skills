// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { createScope } from '../src/scope.mjs';
import { focusedTests } from '../src/focused-tests.mjs';
import { promises } from '../src/promises.mjs';
const root = '/pinned-dynamic-import';
function scan(text) {
  const file = path.join(root, 'syntax.spec.ts'), bytes = Buffer.from(text);
  const manifest = {schema:'node-candidate-inventory-v1',complete:true,errors:[],
    root:{canonical:root,requested:root,kind:'directory'},
    candidates:[{path:file,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
  const scope=createScope({manifest,sources:new Map([[file,bytes]])});
  return {file,scope,focus:focusedTests(bytes,file,{scope}),promise:promises(bytes,file,{scope})};
}
const original = [
  'const { test: pwTest, expect: pwExpect } = await import(`@playwright/test`);',
  "pwTest /* comment */ . /* comment */ only?.('comment focus', async () => {});",
  "`${pwTest.only('template focus', async () => {})}`;",
  'function localTest(test: any) {',
  "  test.only('local', () => {});",
  '}',
  'function localExpect(expect: Function, locator: unknown) {',
  '  expect(locator).toBeVisible();',
  '}',
  'pwExpect({}).toBeVisible();',
].join('\n');
test('exact legacy v10 dynamic-import syntax preserves real bindings and lexical shadow guards', () => {
  const result=scan(original);
  assert.equal(result.scope.binding(result.file,'pwTest').kind,'playwright-test');
  assert.equal(result.scope.binding(result.file,'pwExpect').kind,'playwright-expect');
  assert.deepEqual(result.focus.findings.map(item=>[item.line,item.disposition]),[[2,'confirmed'],[3,'confirmed']]);
  assert.equal(result.promise.findings.some(item=>item.line===8),false);
  assert.equal(result.promise.findings.some(item=>item.line===10&&item.patternId==='#15'),true);
  assert.deepEqual(result.scope.framework(result.file).frameworks,['playwright']);
});
test('literal strings, templates, immutable namespace aliases and destructured export aliases share pinned identity', () => {
  for(const text of [
    "const {test: scenario}=await import('@playwright/test');scenario.only('x',()=>{});",
    'const {test: scenario}=await import(`@playwright/test`);scenario.only("x",()=>{});',
    "const namespace=await import('@playwright/test');const {test:scenario}=namespace;scenario.only('x',()=>{});",
    "const namespace=await import('@playwright/test');const alias=namespace;alias.test.only('x',()=>{});",
    "const namespace=await import('@playwright/test');const scenario=namespace.test;scenario.only('x',()=>{});",
  ]) assert.equal(scan(text).focus.findings.length,1,text);
});
test('unawaited, nested, conditional, dynamic, foreign and import-options shapes stay unproven', () => {
  for(const text of [
    "const {test}=import('@playwright/test');test.only('x',()=>{});",
    "async function setup(){const {test}=await import('@playwright/test');test.only('x',()=>{});}",
    "if(enabled){const {test}=await import('@playwright/test');test.only('x',()=>{});}",
    "const {test}=enabled?await import('@playwright/test'):other;test.only('x',()=>{});",
    "const {test}=await import(moduleName);test.only('x',()=>{});",
    "const {test}=await import(`@playwright/${suffix}`);test.only('x',()=>{});",
    "const {test}=await import('vitest');test.only('x',()=>{});",
    "const {test}=await import('./custom');test.only('x',()=>{});",
    "const {test}=await import('@playwright/test',{with:{type:'json'}});test.only('x',()=>{});",
    "const {['test']:test}=await import('@playwright/test');test.only('x',()=>{});",
    "const {test=custom}=await import('@playwright/test');test.only('x',()=>{});",
  ]) {
    const result=scan(text);
    assert.deepEqual(result.focus.findings,[],text);
    assert.ok(result.focus.diagnostics.length,text);
  }
});
test('namespace, extracted binding and alias writes cannot borrow dynamic-import identity', () => {
  for(const text of [
    "let {test}=await import('@playwright/test');test.only('x',()=>{});",
    "const {test}=await import('@playwright/test');test=custom;test.only('x',()=>{});",
    "const {test}=await import('@playwright/test');test.only=custom;test.only('x',()=>{});",
    "const pw=await import('@playwright/test');pw.test=custom;pw.test.only('x',()=>{});",
    "const pw=await import('@playwright/test');const alias=pw;alias.test=custom;pw.test.only('x',()=>{});",
  ]) {
    const result=scan(text);assert.deepEqual(result.focus.findings,[],text);assert.ok(result.focus.diagnostics.length,text);
  }
  const shadow=scan("const {test}=await import('@playwright/test');function local(test){test.only('x',()=>{});}");
  assert.deepEqual(shadow.focus.findings,[]);
});

test('ordinary awaited POM factories do not acquire module errors or framework identity', () => {
  const result=scan("import {test} from '@playwright/test';test('x',async({bookingPage})=>{const eventTypePage=await bookingPage.previewEventType();});");
  const binding=result.scope.binding(result.file,'eventTypePage');
  assert.equal(binding.kind,'none');
  assert.equal(binding.complete,true);
  assert.deepEqual(binding.reasons,[]);
});
