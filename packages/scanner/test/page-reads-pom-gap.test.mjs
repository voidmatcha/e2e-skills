// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {pageReads} from '../src/page-reads.mjs';
import {inventory} from '../src/inventory.mjs';
import {createScope} from '../src/scope.mjs';
const cli=fileURLToPath(new URL('../src/cli.mjs',import.meta.url));
const message='#17 POM selector action requires unsupported runtime Page provenance';
const body=text=>"import {test} from '@playwright/test';\ntest('x',async({page})=>{\n"+text+'\n});\n';
function scan(text,callback){
 const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'page-reads-pom-gap-')));
 try{
  const file=path.join(root,'example.spec.ts'),bytes=Buffer.from(text);fs.writeFileSync(file,bytes);
  const manifest=inventory(root);assert.equal(manifest.complete,true,JSON.stringify(manifest.errors));
  const scope=createScope({manifest,sources:new Map([[file,bytes]])});
  const result=pageReads(bytes,file,{scope});callback?.(result,file);return result;
 }finally{fs.rmSync(root,{recursive:true,force:true});}
}
const target=body("const settingsPage=new SettingsPage();\nconst selector='button';\nawait settingsPage.click(selector);");
// Actual v4 call65 bytes: the receiver has no declaration. Keep the frozen
// receipt distinct from the earlier authored constructor canary above.
const actualV4="import { test, expect } from '@playwright/test';\ntest('canary', async ({ page }) => {\nconst selector='button';\nawait settingsPage.click(selector);\n});\n";
function expectReviewCandidate(json,file,text,line){
 const expression='settingsPage.click(selector)',start=text.indexOf(expression);
 assert.deepEqual(json.findings,[{
  patternId:'#17',severity:'P1',disposition:'candidate',origin:'ast',file,
  line,column:7,start,end:start+expression.length,
  evidence:{kind:'unresolved-page',requirements:['verify-runtime-binding','verify-required-test-outcome']},
 }]);
}
test('actual v4 call65 unbound Page receiver is incomplete rather than a clean scan',()=>{
 scan(actualV4,(result,file)=>{
  assert.deepEqual(result.findings,[]);assert.equal(result.diagnostics.length,1);
  assert.equal(result.diagnostics[0].message,message);
  const run=spawnSync(process.execPath,[cli,'--bounded-static',file],{encoding:'utf8',timeout:20000});
  assert.equal(run.status,2,run.stderr);const json=JSON.parse(run.stdout);
  assert.equal(json.execution.complete,false);expectReviewCandidate(json,file,actualV4,4);
  assert.ok(json.execution.diagnostics.some(item=>item.detector==='pageReads'&&item.code==='provenance-unsupported'));
 });
});
test('unknown const Page instance with identifier selector remains diagnosed, not a Page finding',()=>{
 const result=scan(target);assert.deepEqual(result.findings,[]);assert.equal(result.diagnostics.length,1);
 assert.equal(result.diagnostics[0].message,message);
 assert.equal(target.slice(result.diagnostics[0].start,result.diagnostics[0].start+result.diagnostics[0].length),'settingsPage');
 const alias=scan(target.replace('{test}','{test as check}').replace("test('x'","check('x'"));
 assert.equal(alias.diagnostics[0].message,message);
});
test('ordinary objects, scalars, local constructors and root/test shadows stay excluded',()=>{
 for(const text of [
  body("const selector='x';const settingsPage={click(){}};await settingsPage.click(selector);"),
  body("const selector='x';const settingsPage=42;await settingsPage.click(selector);"),
  body("const selector='x';function f(settingsPage){settingsPage.click(selector);}"),
  body("const selector='x';function f(SettingsPage){const settingsPage=new SettingsPage();settingsPage.click(selector);}"),
  body("const selector='x';function SettingsPage(){return {click(){}};}const settingsPage=new SettingsPage();settingsPage.click(selector);"),
  body("const settingsPage=new SettingsPage();await settingsPage.click('button');"),
  body("const selector='x';const settingsPage=new SettingsPage();settingsPage['click'](selector);settingsPage?.click(selector);"),
  "import {test} from 'vitest';test('x',async()=>{const selector='x';const settingsPage=new SettingsPage();await settingsPage.click(selector);});",
  "import {test} from '@playwright/test';function f(test){test('x',()=>{const selector='x';const settingsPage=new SettingsPage();settingsPage.click(selector);});}",
  "const selector='x';const settingsPage=new SettingsPage();settingsPage.click(selector);",
 ]){const result=scan(text);assert.deepEqual(result.findings,[],text);assert.deepEqual(result.diagnostics,[],text);}
});
test('known scalar, object and array selector values do not acquire this selector diagnostic',()=>{
 for(const value of ['42','true','false','null','{}','[]']){
  const result=scan(body(`const settingsPage=new SettingsPage();const selector=${value};settingsPage.click(selector);`));
  assert.deepEqual(result.findings,[]);assert.deepEqual(result.diagnostics,[],value);
 }
});
test('proven direct Page and immutable Page aliases retain confirmed and candidate accounting',()=>{
 const result=scan(body("const selector='button';const screen=page;await page.click('button');await page.click(selector);await screen.click(selector);"));
 assert.deepEqual(result.findings.map(hit=>[hit.patternId,hit.disposition]),[['#17','confirmed'],['#17','candidate'],['#17','candidate']]);
 assert.deepEqual(result.diagnostics,[]);
});
test('bounded CLI retains the awaited POM selector candidate, provenance diagnostic and exit 2',()=>{
 scan(target,(_result,file)=>{
  const result=spawnSync(process.execPath,[cli,'--bounded-static',file],{encoding:'utf8',timeout:20000});
  assert.equal(result.status,2,result.stderr);const json=JSON.parse(result.stdout);
  assert.equal(json.execution.complete,false);expectReviewCandidate(json,file,target,5);
  assert.ok(json.execution.diagnostics.some(item=>item.detector==='pageReads'&&item.code==='provenance-unsupported'));
 });
});
