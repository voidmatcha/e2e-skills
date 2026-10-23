// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { assertions } from '../src/assertions.mjs';
import { promises } from '../src/promises.mjs';
function analyze(body, detector=assertions, prefix="import {test,expect} from '@playwright/test';") {
  const file='/pinned-project/semantic.spec.ts';
  const bytes=Buffer.from(prefix+"\ntest('case',async({page})=>{\n"+body+'\n});');
  const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],root:{canonical:'/pinned-project',kind:'directory'},candidates:[{path:file,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
  return detector(bytes,file,{scope:createScope({manifest,sources:new Map([[file,bytes]])})});
}
test('literal destructured scalar shadow stays clean without borrowing a sibling Locator',()=>{
  const result=analyze("const locator=page.getByTestId('real');await expect(locator).toBeDefined();{const {locator}={locator:42};await expect(locator).toBeDefined();}");
  assert.equal(result.findings.length,1);assert.equal(result.findings[0].disposition,'confirmed');assert.deepEqual(result.diagnostics,[]);
  for(const value of ['42',"'text'",'true','false','null','`text`']) {
    assert.deepEqual(analyze(`const {value:locator}={value:${value}};expect(locator).toBeDefined();`),{findings:[],diagnostics:[]});
  }
});
test('destructured getter, spread, computed, default and written bindings remain unproven',()=>{
  for(const body of [
    'const {locator}={get locator(){return unknown()}};',
    'const {locator}={locator:42,...unknown};',
    "const {['locator']:locator}={locator:42};",
    'const {locator=unknown}={locator:42};',
    'const {locator}={locator:42};locator=unknown;',
    'const {locator}={locator:42,locator:unknown};',
  ]) {
    const result=analyze(body+'expect(locator).toBeDefined();');
    assert.equal(result.findings.length,0,body);assert.ok(result.diagnostics.length,body);
  }
});
test('unknown custom factory query retains source candidate and unresolved runtime diagnostic',()=>{
  for(const query of ["const app=createCustomWrapper();await expect(app.getByRole('status')).toBeTruthy();", "await expect(createCustomWrapper().getByRole('status')).toBeTruthy();"]) {
    const result=analyze(query);assert.equal(result.findings.length,1);const finding=result.findings[0];
    assert.equal(finding.patternId,'#4f');assert.equal(finding.disposition,'candidate');
    assert.deepEqual(finding.evidence,{kind:'unresolved-query',requirements:['verify-runtime-binding','verify-required-test-outcome']});
    assert.ok(result.diagnostics.length);
  }
  for(const body of [
    "const app={getByRole:()=>42};expect(app.getByRole('x')).toBeTruthy();",
    "function createCustomWrapper(){return {getByRole:()=>42}}const app=createCustomWrapper();expect(app.getByRole('x')).toBeTruthy();",
    "const app=createCustomWrapper();app.getByRole=custom;expect(app.getByRole('x')).toBeTruthy();",
    "const app=createCustomWrapper();expect(await app.getByRole('x')).toBeTruthy();",
    "const app=createCustomWrapper();expect(app.getByRole?.('x')).toBeTruthy();",
  ]) assert.equal(analyze(body).findings.length,0,body);
  const foreign=analyze("const app=createCustomWrapper();expect(app.getByRole('x')).toBeTruthy();",assertions,"import {test,expect} from 'vitest';");
  assert.equal(foreign.findings.length,0);
});
test('comma receiver takes final expect value while preserving consumption and lexical identity',()=>{
  const result=analyze("(0, expect(page.getByRole('button'))).toBeVisible();\n(expect(page.getByRole('status'))).toHaveText('ready');\nawait (0, expect(page.getByRole('main'))).toBeVisible();\nreturn (0, expect(page.getByRole('contentinfo'))).toBeVisible();",promises);
  assert.deepEqual(result.findings.map(f=>[f.line,f.patternId,f.disposition]),[[3,'#15','confirmed'],[4,'#15','confirmed']]);assert.deepEqual(result.diagnostics,[]);
  for(const body of [
    "(expect(page.getByRole('x')), custom).toBeVisible();",
    "function helper(expect){(0,expect(page.getByRole('x'))).toBeVisible();}",
    "expect=custom;(0,expect(page.getByRole('x'))).toBeVisible();",
  ]) assert.equal(analyze(body,promises).findings.length,0,body);
  assert.equal(analyze("(0,expect(page)).toBeVisible();",promises,"import {test,expect} from 'vitest';").findings.length,0);
});
