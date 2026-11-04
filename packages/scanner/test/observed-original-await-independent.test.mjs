// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createScope} from '../src/scope.mjs';
import {catchHandlers} from '../src/catch-handlers.mjs';

function run(body, {prefix=''}={}) {
  const filename='/independent/rejection.spec.ts';
  const bytes=Buffer.from(`import {test,expect} from '@playwright/test';\n${prefix}\ntest('independent', async({page})=>{\n${body}\n});`);
  const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],root:{canonical:'/independent',kind:'directory'},candidates:[{path:filename,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
  return catchHandlers(bytes,filename,{scope:createScope({manifest,sources:new Map([[filename,bytes]])})});
}
const normal=`const original = page.waitForResponse('/required');\noriginal.catch(() => {});\nawait original;`;

test('independent safe guard: transparent parentheses and assertion following original await',()=>{
  const body=`const original = (page.waitForResponse('/required'));\noriginal.catch(error => { console.warn(error); });\nawait (original);\nexpect(true).toBe(true);`;
  assert.equal(run(body).findings.length,0);
});

test('independent negative guards: aliases, nested control flow and chained awaits stay candidates',()=>{
  const cases=[
    `const original=page.waitForResponse('/required');\nconst alias=original;\nalias.catch(()=>{});\nawait alias;`,
    `const original=page.waitForResponse('/required');\noriginal.catch(()=>{});\ntry {await original;} catch {}`,
    `const original=page.waitForResponse('/required');\noriginal.catch(()=>{});\nawait original.then(()=>{},()=>{});`,
    `const original=page.waitForResponse('/required');\noriginal.catch(()=>{});\nreturn original;`,
    `if (flag) { ${normal} }`,
    `const original=page.waitForResponse('/required');\nObject.defineProperty(original,'then',{value:()=>{}});\noriginal.catch(()=>{});\nawait original;`,
    `const original=page.waitForResponse('/required');\nconst alias=original;\nalias.then=()=>{};\noriginal.catch(()=>{});\nawait original;`,
  ];
  for(const body of cases) assert.ok(run(body).findings.length>0,body);
});

test('independent negative guard: observer in a helper is not a direct test statement',()=>{
  const body=`async function observer(){${normal}}\nawait observer();`;
  assert.ok(run(body).findings.length>0);
});

const sabotage = `function sabotage(p) {
  Promise.prototype.then.call(p,()=>{},()=>{});
  Object.defineProperty(p,'constructor',{value:undefined});
  p.then = resolve => typeof resolve === 'function' ? resolve('not-the-required-response') : undefined;
}`;
const siblingEscape=`const original=page.waitForResponse('/required'), escaped=sabotage(original);\noriginal.catch(()=>{});\nawait original;`;

test('independent soundness guard: sibling initializer escape must not be suppressed',()=>{
  const current=run(siblingEscape,{prefix:sabotage});
  assert.ok(current.findings.length>0,'sibling declaration can mutate the original before its observer and await');
});

test('independent runtime witness: sibling initializer can turn a rejected original into successful await',async()=>{
  function sabotage(p) {
    Promise.prototype.then.call(p,()=>{},()=>{});
    Object.defineProperty(p,'constructor',{value:undefined});
    p.then=resolve=>typeof resolve==='function'?resolve('not-the-required-response'):undefined;
  }
  const original=Promise.reject(new Error('required wait failed')), escaped=sabotage(original);
  void escaped;
  original.catch(()=>{});
  assert.equal(await original,'not-the-required-response');
});
