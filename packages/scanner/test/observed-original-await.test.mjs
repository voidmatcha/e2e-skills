// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createScope} from '../src/scope.mjs';
import {catchHandlers} from '../src/catch-handlers.mjs';
function run(code) {
 const filename='/pinned/case.spec.ts';
 const bytes=Buffer.from(`import {test,expect} from '@playwright/test';\ntest('authored', async({page})=>{\n${code}\n});`);
 const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],root:{canonical:'/pinned',kind:'directory'},candidates:[{path:filename,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
 return catchHandlers(bytes,filename,{scope:createScope({manifest,sources:new Map([[filename,bytes]])})});
}
test('original known wait remains awaited after a detached observer',()=>{
 for(const method of ['waitForURL','waitForResponse','waitForRequest','waitForEvent']){
  const r=run(`const original=page.${method}('/target');\noriginal.catch(()=>{});\nawait original;`);
  assert.deepEqual(r,{findings:[],diagnostics:[]},method);
 }
});
test('swallowed/derived/unawaited/conditional originals remain candidates',()=>{
 const codes=[
 `const original=page.waitForURL('/target'), escaped=passElsewhere(original);\noriginal.catch(()=>{});\nawait original;`,
 `const original=page.waitForURL('/target');\nawait original.catch(()=>{});`,
 `const original=page.waitForURL('/target');\noriginal.catch(()=>{});\nawait original.catch(()=>{});`,
 `const original=page.waitForURL('/target');\noriginal.catch(()=>{});`,
 `const original=page.waitForURL('/target');\noriginal.catch(()=>{});\nif(flag) await original;`,
 `const original=page.waitForURL('/target');\noriginal.catch(()=>{});\nawait Promise.race([original,Promise.resolve()]);`,
 `let original=page.waitForURL('/target');\noriginal.catch(()=>{});\nawait original;`,
 `const original=custom.waitForURL('/target');\noriginal.catch(()=>{});\nawait original;`,
 `const original=page.waitForURL('/target');\noriginal.catch=()=>Promise.resolve();\noriginal.catch(()=>{});\nawait original;`,
 `const original=page.waitForURL('/target');\npassElsewhere(original);\noriginal.catch(()=>{});\nawait original;`,
 `const original=page.waitForURL('/target').catch(()=>{});\noriginal.catch(()=>{});\nawait original;`,
 ];
 for(const code of codes)assert.ok(run(code).findings.length>0,code);
});
test('native rejected Promise still rejects after a detached observer',async()=>{
 const original=Promise.reject(new Error('authored-failure'));
 original.catch(()=>{});
 await assert.rejects(original,/authored-failure/);
});
