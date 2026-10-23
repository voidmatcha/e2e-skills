// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createScope} from '../src/scope.mjs';
import {promises} from '../src/promises.mjs';
import {focusedTests} from '../src/focused-tests.mjs';
const file='/pinned-export/custom.spec.ts',fixture='/pinned-export/fixtures.ts';
const original="import { expect, test } from './fixtures';\ntest('custom fixture', async ({ status }) => {\n  expect(\n    status,\n  ).toBeVisible();\n});\nexport const glob = '**/*';\n";
function scan(fixtureText,text=original){
 const sources=new Map([[file,Buffer.from(text)],[fixture,Buffer.from(fixtureText)]]);
 const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],root:{canonical:'/pinned-export',kind:'directory'},candidates:[...sources].map(([path,bytes])=>({path,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}))};
 const scope=createScope({manifest,sources});return {scope,promise:promises(sources.get(file),file,{scope}),focus:focusedTests(sources.get(file),file,{scope})};
}
test('unchanged original ast-scope fixture retains dynamic namespace destructured exports and missing await',()=>{
 const result=scan("const playwright = await import('@playwright/test');\nexport const { expect, test } = playwright;\n");
 assert.equal(result.scope.binding(file,'expect').kind,'playwright-expect');
 assert.equal(result.scope.binding(file,'test').kind,'playwright-test');
 assert.deepEqual(result.promise.findings.map(f=>[f.line,f.patternId,f.disposition]),[[3,'#15','confirmed']]);assert.deepEqual(result.promise.diagnostics,[]);
});
test('direct awaited export destructuring and renamed namespace leaves keep exact lexical bindings',()=>{
 for(const fixtureText of [
 "export const {expect,test}=await import(`@playwright/test`);",
 "const pw=await import('@playwright/test');const alias=pw;export const {expect:check,test:scenario}=alias;export {check as expect,scenario as test};",
 "const pw=await import('@playwright/test');export const {expect,test}=pw;",
 ]) {
 const result=scan(fixtureText,original+"\ntest.only('focus',()=>{});\n");
 assert.equal(result.promise.findings.length,1,fixtureText);assert.equal(result.focus.findings.length,1,fixtureText);
 }
});
test('mutable, unawaited, computed, rest, nested, default and nonliteral export origins cannot be false clean',()=>{
 for(const fixtureText of [
 "const pw=await import('@playwright/test');export let {expect,test}=pw;",
 "const pw=await import('@playwright/test');export const {expect,test}=pw;expect=custom;",
 "const pw=await import('@playwright/test');pw.expect=custom;export const {expect,test}=pw;",
 "const pw=import('@playwright/test');export const {expect,test}=pw;",
 "const pw=await import(moduleName);export const {expect,test}=pw;",
 "const pw=await import(`@playwright/${suffix}`);export const {expect,test}=pw;",
 "const pw=await import('@playwright/test');export const {['expect']:expect,test}=pw;",
 "const pw=await import('@playwright/test');export const {...expect}=pw;export const test=pw.test;",
 "const pw=await import('@playwright/test');export const {nested:{expect},test}=pw;",
 "const pw=await import('@playwright/test');export const {expect=custom,test}=pw;",
 "const pw=await import('@playwright/test');export const [expect,test]=pw;",
 ]) {
 const result=scan(fixtureText);assert.equal(result.promise.findings.length,0,fixtureText);
 assert.ok(result.promise.diagnostics.length,fixtureText);
 }
});
test('foreign dynamic modules and lexical imported-expect shadows never borrow official async semantics',()=>{
 const foreign=scan("const pw=await import('vitest');export const {expect,test}=pw;");
 assert.equal(foreign.promise.findings.length,0);assert.ok(foreign.promise.diagnostics.length);
 const shadow=scan("const pw=await import('@playwright/test');export const {expect,test}=pw;", "import {test,expect} from './fixtures';function helper(expect){expect(subject).toBeVisible();}");
 assert.deepEqual(shadow.promise.findings,[]);assert.deepEqual(shadow.promise.diagnostics,[]);
});
