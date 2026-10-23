// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createScope} from '../src/scope.mjs';
import {timeoutZero} from '../src/timeout-zero.mjs';
function scan(text){
 const file='/pinned-project/boundaries.spec.ts',bytes=Buffer.from(text);
 const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],root:{canonical:'/pinned-project',kind:'directory'},candidates:[{path:file,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
 return timeoutZero(bytes,file,{scope:createScope({manifest,sources:new Map([[file,bytes]])})});
}
const header="import {expect,type Page,type Locator} from '@playwright/test';\n";
test('original executable boundary line14 retains official declared Page timeout as candidate only',()=>{
 const result=scan([
 "import { expect, type Page } from '@playwright/test';",
 'declare const page: Page;',
 'const docs = "page.waitForTimeout(100); timeout: 0";',
 'const template = `page.waitForTimeout(200); timeout: 0`;',
 '// page.waitForTimeout(300); timeout: 0',
 '/* page.waitForTimeout(400); timeout: 0 */',
 'function test() { return { only() {} }; }',
 'const it = { only() {} };',
 "test.only('local helper');", "it.only('local helper');",
 'page.waitForTimeout(500);', 'testInfo.setTimeout(0);', 'const options = { timeout: 0 };',
 "await expect(page).toHaveURL('/done', { timeout: 0 });",
 ].join('\n'));
 assert.deepEqual(result.findings.map(f=>[f.line,f.patternId,f.disposition]),[[14,'#4g','candidate']]);
 assert.equal(result.findings[0].evidence.kind,'unresolved-page');assert.equal(result.diagnostics.length,1);
 assert.match(result.diagnostics[0].message,/type annotation alone/);
});
test('official Page and Locator annotations select matching assertion candidates, never action proof',()=>{
 for(const text of [
 header+"declare const page:Page;expect(page).toHaveTitle('done',{timeout:0});",
 header+"declare const row:Locator;expect(row).toBeVisible({timeout:0});",
 header+"function f(row:Locator){expect.soft(row).not.toBeVisible({timeout:0});}",
 "import {expect,type Page as P} from '@playwright/test';declare const screen:P;expect(screen).toHaveURL('/',{timeout:0});",
 ]) {const result=scan(text);assert.equal(result.findings.length,1,text);assert.equal(result.findings[0].disposition,'candidate');assert.ok(result.diagnostics.length,text);}
 assert.equal(scan(header+"declare const page:Page;page.goto('/',{timeout:0});").findings.length,0);
});
test('foreign, custom, shadowed, mutated, mismatched, optional and retry cases never borrow typed candidates',()=>{
 for(const text of [
 "import {expect} from '@playwright/test';import type {Page} from 'custom';declare const page:Page;expect(page).toHaveURL('/',{timeout:0});",
 "import {expect} from '@playwright/test';class Page{};declare const page:Page;expect(page).toHaveURL('/',{timeout:0});",
 header+"declare const page:Page;function f(expect){expect(page).toHaveURL('/',{timeout:0});}",
 header+"declare const page:Page;function f(page){expect(page).toHaveURL('/',{timeout:0});}",
 header+"declare const page:Page;page.goto=custom;expect(page).toHaveURL('/',{timeout:0});",
 header+"declare const page:Page;expect=custom;expect(page).toHaveURL('/',{timeout:0});",
 header+"declare let page:Page;expect(page).toHaveURL('/',{timeout:0});",
 header+"const page:Page=custom;expect(page).toHaveURL('/',{timeout:0});",
 header+"declare const page:Page;expect(page).toBeVisible({timeout:0});",
 header+"declare const page:Page;expect(page).toHaveURL?.('/',{timeout:0});",
 header+"declare const page:Page;expect?.(page).toHaveURL('/',{timeout:0});",
 header+"declare const page:Page;expect.poll(()=>page,{timeout:0}).toBe(page);",
 header+"declare const page:Page;expect(()=>page).toPass({timeout:0});",
 "import {expect} from 'vitest';import type {Page} from '@playwright/test';declare const page:Page;expect(page).toHaveURL('/',{timeout:0});",
 ]) assert.equal(scan(text).findings.length,0,text);
});
test('typed candidates require exact literal-zero options without spreads, duplicate keys or dynamic values',()=>{
 for(const option of ['{timeout:500}','options','{...options,timeout:0}','{timeout:0,timeout:5}','{[key]:0}','{timeout:zero}'])
 assert.equal(scan(header+`declare const page:Page;expect(page).toHaveURL('/',${option});`).findings.length,0,option);
 const unknown=scan("import {expect} from './missing';expect(subject).toHaveURL('/',{timeout:0});");
 assert.equal(unknown.findings.length,0);assert.ok(unknown.diagnostics.length);
});
