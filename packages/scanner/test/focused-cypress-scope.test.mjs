// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createHash} from 'node:crypto';
import {createScope} from '../src/scope.mjs';
import {focusedTests} from '../src/focused-tests.mjs';
function run(text) {
  const file='/pinned-project/example.cy.ts',bytes=Buffer.from(text);
  const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],root:{canonical:'/pinned-project',kind:'directory'},candidates:[{path:file,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
  return focusedTests(bytes,file,{scope:createScope({manifest,sources:new Map([[file,bytes]])})});
}
test('scoped focused tests share Cypress global mutation and lexical guards',()=>{
  for(const write of ['it=custom;', 'it.only=custom;', '({it}=custom);', 'globalThis.it=custom;']) {
    const result=run(write+"\nit.only('x',()=>{});");
    assert.deepEqual(result.findings,[],write);
    assert.ok(result.diagnostics.some(item=>/mutated Cypress global/.test(item.message)),write);
  }
  const result=run("function f(it){it.only=custom;}\nit.only('x',()=>{});");
  assert.deepEqual(result.findings.map(item=>item.line),[2]);
  assert.deepEqual(result.diagnostics,[]);
});
