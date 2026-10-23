// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createHash} from 'node:crypto';
import {createScope} from '../src/scope.mjs';
import {actions} from '../src/actions.mjs';
function run(text,name='example.spec.ts') {
  const file='/pinned-project/'+name, bytes=Buffer.from(text);
  const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],root:{canonical:'/pinned-project',kind:'directory'},candidates:[{path:file,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
  return actions(bytes,file,{scope:createScope({manifest,sources:new Map([[file,bytes]])})});
}
const header="import {test} from '@playwright/test';\ntest('x',async({page})=>{\n";
test('Playwright locator/page actions use exact option positions and force-property locations',()=>{
  const result=run(header+"await page.getByRole('button').click({force:true});\nawait page.locator('input').fill('text',{\n 'force': true\n});\nawait page.click('button',{force:true});\nawait page.locator('input').fill({force:true});\nawait page.locator('button').click({force:false});\n});");
  assert.deepEqual(result.findings.map(item=>[item.patternId,item.severity,item.disposition,item.line]),[['#5b','P1','confirmed',3],['#5b','P1','confirmed',5],['#5b','P1','confirmed',7]]);
  assert.deepEqual(result.diagnostics,[]);
});
test('unaliased Cypress cy chains require shared framework and unshadowed root',()=>{
  const result=run("cy.get('button').click({force:true});\ncy.get('input').type('text',{force:true});\ncy.get('button').click(10,20,{force:true});\ncy.get('input').type('text');\nfunction local(cy){cy.get('button').click({force:true});}\n",'example.cy.ts');
  assert.deepEqual(result.findings.map(item=>item.line),[1,2,3]);
  assert.equal(run("const cy=custom;cy.get('button').click({force:true});",'example.cy.ts').findings.length,0);
});
test('strings, nonactions, custom receivers, foreign tests and lexical page shadows do not become findings',()=>{
  for (const text of ["const text='page.click({force:true})';\n", "const custom={click(){}};custom.click({force:true});\n", "fs.rm({force:true});\n", "function local(page){page.locator('x').click({force:true});}\n"]) {
    assert.equal(run(header+text+'});').findings.length,0,text);
  }
  assert.equal(run("import {test} from 'vitest';test('unit',async({page})=>{page.locator('x').click({force:true});});").findings.length,0);
});
test('spread, duplicate, dynamic and aliased options remain diagnosed without findings',()=>{
  for(const options of ["{force:true,...other}","{...other,force:true}","{force:true,force:false}","{force:setting}",'options']) {
    const result=run(header+`await page.locator('button').click(${options});\n});`);
    assert.deepEqual(result.findings,[],options);
    assert.ok(result.diagnostics.length,options);
  }
});
test('mutable page bindings, missing scope and parse errors remain explicit',()=>{
  const result=run(header+"page=custom;await page.locator('x').click({force:true});\n});");
  assert.deepEqual(result.findings,[]);
  assert.ok(result.diagnostics.some(item=>/mutable/.test(item.message)));
  assert.ok(actions(Buffer.from(''),'/example.ts').diagnostics.length);
  assert.ok(run(header+'(').diagnostics.length);
});

test('shared Cypress mutation proof invalidates action chains without changing unrelated lexical globals',()=>{
  for(const write of ['cy=custom;', 'cy.get=custom;', '({cy}=custom);', 'globalThis.cy=custom;']) {
    const result=run(write+"\ncy.get('button').click({force:true});",'example.cy.ts');
    assert.deepEqual(result.findings,[],write);
    assert.ok(result.diagnostics.some(item=>/mutated Cypress global/.test(item.message)),write);
  }
  assert.equal(run("function f(cy){cy.get=custom;}\ncy.get('button').click({force:true});",'example.cy.ts').findings.length,1);
});
