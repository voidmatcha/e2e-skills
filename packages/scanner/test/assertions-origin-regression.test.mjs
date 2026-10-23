// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createScope} from '../src/scope.mjs';
import {assertions} from '../src/assertions.mjs';
function scan(text){
 const file='/pinned-project/origin.spec.ts',bytes=Buffer.from(text);
 const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],root:{canonical:'/pinned-project',kind:'directory'},candidates:[{path:file,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
 return assertions(bytes,file,{scope:createScope({manifest,sources:new Map([[file,bytes]])})});
}
const wrap=body=>"import {test,expect,type Locator} from '@playwright/test';test('x',async({page})=>{"+body+'});';
test('original immutable custom expect factory shadow is not a Playwright provenance gap',()=>{
 const result=scan("import { test } from '@playwright/test';\nconst expect = makeCustomExpect();\ntest('shadowed', async ({ page }) => {\n  expect(page.getByRole('status')).toBeVisible;\n});\n");
 assert.deepEqual(result,{findings:[],diagnostics:[]});
 // An unknown imported/forwarded or mutated binding must remain diagnostic.
 for(const text of [
 "import {expect} from './missing';expect(subject).toBeVisible;",
 "const expect=makeCustomExpect();expect=unknownExpect;expect(subject).toBeVisible;",
 ]) {const value=scan(text);assert.equal(value.findings.length,0);assert.ok(value.diagnostics.length,text);}
});
test('original resourceLocator factory is a source candidate, never confirmed runtime Locator',()=>{
 const result=scan([
 "import { expect, test, type Locator } from '@playwright/test';",
 "test('locator provenance', async ({ page }) => {",
 '  const resourceLocator = createResourceHandle();',
 '  expect(resourceLocator).toBeTruthy();',
 "  const typedResource: Locator = page.locator('.resource');",
 '  expect(typedResource).toBeTruthy();',
 "  const saveButton = page.getByRole('button', { name: 'Save' });",
 '  expect(saveButton).toBeTruthy();',
 '});',
 ].join('\n'));
 assert.deepEqual(result.findings.map(f=>[f.line,f.disposition]),[[4,'candidate'],[6,'confirmed'],[8,'confirmed']]);
 assert.equal(result.findings[0].evidence.kind,'unresolved-locator');assert.equal(result.diagnostics.length,1);
});
test('ordinary scalar/custom/foreign/mutated or shadowed identifiers cannot borrow suffix candidates',()=>{
 for(const body of [
 'const resourceLocator=42;expect(resourceLocator).toBeTruthy();',
 'function createResourceHandle(){return 42}const resourceLocator=createResourceHandle();expect(resourceLocator).toBeTruthy();',
 'const resourceLocator=createResourceHandle();resourceLocator=custom;expect(resourceLocator).toBeTruthy();',
 'const resourceLocator=createResourceHandle();function helper(resourceLocator){expect(resourceLocator).toBeTruthy();}',
 'const resourceLocator=createResourceHandle();expect(await resourceLocator).toBeTruthy();',
 'const resource=createResourceHandle();expect(resource).toBeTruthy();',
 ]) assert.equal(scan(wrap(body)).findings.length,0,body);
 assert.equal(scan("import {expect,test} from 'vitest';test('x',()=>{const resourceLocator=createResourceHandle();expect(resourceLocator).toBeTruthy();});").findings.length,0);
});
