// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {assertions} from '../src/assertions.mjs';
import {inventory} from '../src/inventory.mjs';
import {createScope} from '../src/scope.mjs';
const cli=fileURLToPath(new URL('../src/cli.mjs',import.meta.url));
const message='#4f POM member truthiness requires unsupported runtime Locator provenance';
const header="import {test,expect} from '@playwright/test';\n";
const body=text=>header+"test('audit',async({page})=>{\n"+text+"\n});\n";
function scan(text,callback){
 const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'e2e-assertion-pom-gap-')));
 try{
  const file=path.join(root,'example.spec.ts'),bytes=Buffer.from(text);fs.writeFileSync(file,bytes);
  const manifest=inventory(root);assert.equal(manifest.complete,true,JSON.stringify(manifest.errors));
  const sources=new Map([[file,bytes]]),scope=createScope({manifest,sources});
  const result=assertions(bytes,file,{scope});callback?.(result,file);return result;
 }finally{fs.rmSync(root,{recursive:true,force:true});}
}
// Unchanged legacy-compat-audit corpus/23-pom-member.spec.ts bytes.
const audited=body('const settingsPage=new SettingsPage();\nexpect(settingsPage.submitButton).toBeTruthy();');
test('audited unknown Page instance member truthiness is incomplete, never confirmed',()=>{
 const result=scan(audited);assert.deepEqual(result.findings,[]);assert.equal(result.diagnostics.length,1);
 assert.equal(result.diagnostics[0].message,message);assert.equal(audited.slice(result.diagnostics[0].start,result.diagnostics[0].start+result.diagnostics[0].length),'settingsPage.submitButton');
});
test('POM class handles and instance assertions preserve scalar sibling exclusions',()=>{
 const text=header+"class ProbePage {submitButton=createHandle();response={ok:true};verify(){expect(this.submitButton).toBeTruthy();expect(this.response).toBeTruthy();}}\n"+
 "test('x',()=>{const settingsPage=new ProbePage();expect(settingsPage.submitButton).not.toBeNull();expect(settingsPage.response).toBeTruthy();});\n";
 const result=scan(text);assert.deepEqual(result.findings,[]);assert.equal(result.diagnostics.length,2);
 assert.ok(result.diagnostics.every(item=>item.message===message));
});
test('ordinary objects, shadowed constructors/expect, scalar fields and non-E2E contexts stay excluded',()=>{
 for(const text of [
  body("const settingsPage={submitButton:true};expect(settingsPage.submitButton).toBeTruthy();"),
  body("const settingsPage=new SettingsPage();function f(settingsPage){expect(settingsPage.submitButton).toBeTruthy();}"),
  body("function f(SettingsPage){const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();}"),
  body("function f(expect){const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();}"),
  body("function SettingsPage(){return {submitButton:true};}const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();"),
  header+"class SettingsPage {submitButton=true;verify(){expect(this.submitButton).toBeTruthy();}}\n"+"test('x',()=>{const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();});\n",
  "import {test,expect} from 'vitest';test('x',()=>{const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();});",
  "import {expect} from '@playwright/test';class SettingsPage {verify(){expect(this.submitButton).toBeTruthy();}}const settingsPage=new SettingsPage();expect(settingsPage.submitButton).toBeTruthy();",
  body("const settingsPage=new SettingsPage();expect(settingsPage.response).toBeTruthy();"),
 ]){const result=scan(text);assert.deepEqual(result.findings,[],text);assert.deepEqual(result.diagnostics,[],text);}
});
test('awaited subject, inverse assertions and runtime Locator proof keep their existing meaning',()=>{
 const result=scan(body("const settingsPage=new SettingsPage();\nexpect(await settingsPage.submitButton).toBeTruthy();\nexpect(settingsPage.submitButton).not.toBeTruthy();\nexpect(page.locator('x')).toBeTruthy();\nawait expect(settingsPage.submitButton).toBeDefined();"));
 assert.deepEqual(result.findings.map(item=>[item.patternId,item.disposition]),[['#4f','confirmed']]);
 assert.equal(result.diagnostics.length,1);assert.equal(result.diagnostics[0].message,message);
});
test('bounded CLI retains the POM review candidate, provenance diagnostic and exit 2',()=>{
 scan(audited,(_result,file)=>{
  const result=spawnSync(process.execPath,[cli,'--bounded-static',file],{encoding:'utf8',timeout:20000});
  assert.equal(result.status,2,result.stderr);const json=JSON.parse(result.stdout);
  assert.equal(json.execution.complete,false);
  const expression='expect(settingsPage.submitButton)',start=audited.indexOf(expression);
  assert.deepEqual(json.findings,[{
   patternId:'#4f',severity:'P0',disposition:'candidate',origin:'ast',file,
   line:4,column:1,start,end:start+expression.length,
   evidence:{kind:'unresolved-locator',requirements:['verify-runtime-binding','verify-required-test-outcome']},
  }]);
  assert.ok(json.execution.diagnostics.some(item=>item.detector==='assertions'&&item.code==='provenance-unsupported'));
 });
});
