// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {reviewCandidates} from '../src/review-candidates.mjs';
import {inventory} from '../src/inventory.mjs';
import {createScope} from '../src/scope.mjs';
const cli=fileURLToPath(new URL('../src/cli.mjs',import.meta.url));
function scan(text,inspect){
 const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'computed-review-')));
 try{
  const file=path.join(root,'example.spec.ts'),bytes=Buffer.from(text);fs.writeFileSync(file,bytes);
  const manifest=inventory(root),scope=createScope({manifest,sources:new Map([[file,bytes]])});
  const result=reviewCandidates(bytes,file,{scope});inspect?.(result,file);return result;
 }finally{fs.rmSync(root,{recursive:true,force:true});}
}
const original = "const pw = require('@playwright/test');\nconst expect = pw.expect;\nconst truthyMatcher = 'toBeTruthy';\nlet mutableMatcher = 'toBeTruthy';\nexpect(page.locator('.ready'))[truthyMatcher]();\nexpect(page.locator('.mutable'))[mutableMatcher]();\n";
test('original immutable computed matcher retains only line 5 and both original diagnostics',()=>{
 assert.equal(createHash('sha256').update(original).digest('hex'),"8ae6ff396ed5fb0bdfc04c0c76b1e1a069dae172c5d8f4e84a602dcbed88dbe4");
 scan(original,(result,file)=>{
  assert.deepEqual(result.diagnostics,[]);
  assert.equal(result.findings.length,1);
  const hit=result.findings[0];
  assert.equal(hit.patternId,'#4f');assert.equal(hit.line,5);assert.equal(hit.disposition,'candidate');
  assert.equal(original.slice(hit.start,hit.end),"expect(page.locator('.ready'))");
  assert.deepEqual(hit.evidence,{kind:'unresolved-locator',requirements:['verify-runtime-binding','verify-required-test-outcome']});
  const run=spawnSync(process.execPath,[cli,'--scan',file,'--fail-on','none'],{encoding:'utf8',timeout:20000});
  assert.equal(run.status,2,run.stderr);const report=JSON.parse(run.stdout);
  assert.equal(report.status,'INCOMPLETE');
  assert.deepEqual(report.execution.diagnostics,[
   {code:'provenance-unsupported',detector:'assertions',file,start:144},
   {code:'shape-unsupported',detector:'assertions',file,start:186},
  ]);
  assert.deepEqual(report.findings.filter(item=>item.patternId==='#4f').map(item=>[item.line,item.disposition]),[[5,'candidate']]);
 });
});
test('computed source candidate excludes foreign, shadowed, mutable, custom and optional variants',()=>{
 const header="const pw=require('@playwright/test');const expect=pw.expect;";
 const call="expect(page.locator('x'))[matcher]();";
 for(const text of [
  header+"let matcher='toBeTruthy';"+call,
  header+"const matcher='toBeTruthy';matcher=custom;"+call,
  header+"const matcher=dynamic;"+call,
  header+"const matcher='toBeFalsy';"+call,
  header+"const matcher='toBeTruthy';page=custom;"+call,
  header+"const matcher='toBeTruthy';const page={locator(){return true}};"+call,
  header+"const matcher='toBeTruthy';function helper(expect){"+call+"}",
  header+"const matcher='toBeTruthy';function helper(page){"+call+"}",
  "const pw=require('vitest');const expect=pw.expect;const matcher='toBeTruthy';"+call,
  "function helper(require){"+header+"const matcher='toBeTruthy';"+call+"}",
  header+"const matcher='toBeTruthy';expect(page?.locator('x'))[matcher]();",
  header+"const matcher='toBeTruthy';expect(page.locator('x'))?.[matcher]();",
  header+"const matcher='toBeTruthy';expect(page.locator('x'))[matcher]?.();",
  header+"const matcher='toBeTruthy';expect(page['locator']('x'))[matcher]();",
  header+"const matcher='toBeTruthy';expect(await page.locator('x'))[matcher]();",
 ])assert.deepEqual(scan(text).findings,[],text);
});
