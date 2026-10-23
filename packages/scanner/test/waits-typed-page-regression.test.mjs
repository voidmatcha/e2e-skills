// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createScope} from '../src/scope.mjs';
import {waits} from '../src/waits.mjs';
import {promises} from '../src/promises.mjs';
function scan(text,detector=waits){
 const file='/pinned-project/boundaries.spec.ts',bytes=Buffer.from(text);
 const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],root:{canonical:'/pinned-project',kind:'directory'},candidates:[{path:file,identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
 return detector(bytes,file,{scope:createScope({manifest,sources:new Map([[file,bytes]])})});
}
test('original executable wait boundary retains declared imported Page only as a review candidate',()=>{
 const result=scan([
 "import { expect, type Page } from '@playwright/test';",
 'declare const page: Page;',
 'const docs = "page.waitForTimeout(100); timeout: 0";',
 'const template = `page.waitForTimeout(200); timeout: 0`;',
 '// page.waitForTimeout(300); timeout: 0',
 '/* page.waitForTimeout(400); timeout: 0 */',
 'function test() { return { only() {} }; }',
 'const it = { only() {} };',
 "test.only('local helper');",
 "it.only('local helper');",
 'page.waitForTimeout(500);',
 'testInfo.setTimeout(0);',
 'const options = { timeout: 0 };',
 "await expect(page).toHaveURL('/done', { timeout: 0 });",
 ].join('\n'));
 assert.deepEqual(result.findings.map(f=>[f.line,f.patternId,f.disposition]),[[11,'#9','candidate']]);
 assert.equal(result.findings[0].evidence.kind,'unresolved-page');assert.deepEqual(result.diagnostics,[]);
});
test('official imported Page parameter and renamed declaration retain candidate role',()=>{
 for(const text of [
 "import {type Page as BrowserPage} from '@playwright/test';declare const screen:BrowserPage;screen.waitForTimeout(5);",
 "import {type Page} from '@playwright/test';function helper(screen:Page){screen.waitForTimeout(5);}",
 ]) assert.deepEqual(scan(text).findings.map(f=>f.disposition),['candidate']);
});
test('foreign/custom/shadow/mutable/initialized types cannot borrow declared Page candidate identity',()=>{
 for(const text of [
 "import {type Page} from 'custom';declare const page:Page;page.waitForTimeout(5);",
 'class Page{};declare const page:Page;page.waitForTimeout(5);',
 "import {type Page} from '@playwright/test';declare let page:Page;page.waitForTimeout(5);",
 "import {type Page} from '@playwright/test';const page:Page=custom;page.waitForTimeout(5);",
 "import {type Page} from '@playwright/test';declare const page:Page;page.waitForTimeout=custom;page.waitForTimeout(5);",
 "import {type Page} from '@playwright/test';declare const page:Page;function helper(page){page.waitForTimeout(5);}",
 "import {type Page} from '@playwright/test';declare const page:Page;page.waitForTimeout?.(5);",
 ]) assert.equal(scan(text).findings.length,0,text);
});
test('original v11 retry assertions are retained candidates with observed operations excluded',()=>{
 const result=scan([
 "import {test,expect} from '@playwright/test';",
 "test('promise APIs',async({page})=>{",
 'expect.poll(()=>1).toBe(1);',
 'await expect.poll(()=>1).toBe(1);',
 'expect(async()=>{}).toPass();',
 'await expect(async()=>{}).toPass();',
 "page.goto('/floating');",
 "await page.goto('/observed');",
 "page.locator('.job').waitFor();",
 "await page.locator('.job').waitFor();",
 '});',
 ].join('\n'),promises);
 assert.deepEqual(result.findings.map(f=>[f.line,f.patternId,f.disposition]),[[3,'#15','candidate'],[5,'#15','candidate'],[7,'#16','confirmed'],[9,'#16','confirmed']]);
 assert.deepEqual(result.diagnostics,[]);
});
