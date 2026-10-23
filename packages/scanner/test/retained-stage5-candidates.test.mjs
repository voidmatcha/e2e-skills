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
function scan(text,name='example.spec.ts',inspect){
 const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'retained-stage5-')));
 try{
  const file=path.join(root,name),bytes=Buffer.from(text);fs.writeFileSync(file,bytes);
  const manifest=inventory(root),scope=createScope({manifest,sources:new Map([[file,bytes]])});
  const result=reviewCandidates(bytes,file,{scope});inspect?.(result,file);return result;
 }finally{fs.rmSync(root,{recursive:true,force:true});}
}
// Exact original stage5 source bytes, including trailing newline.
const fixtures = [
  {
    "name": "position.spec.ts",
    "text": "import { test } from '@playwright/test';\ntest('mixed first calls', async ({ page }) => {\n  await database.query().first();\n  await page.getByRole('row').first().click();\n});\n",
    "sha256": "59ca9e30b9075016e54ef8816015a6c0397d660e52645639ec12f68866cbaeef",
    "pattern": "#10a",
    "kind": "unresolved-positional-subject",
    "diagnostic": {
      "code": "provenance-unsupported",
      "detector": "domQueries",
      "start": 97
    }
  },
  {
    "name": "wrapped-locator.spec.ts",
    "text": "import { expect, test } from '@playwright/test';\nconst wrapper = (value: unknown) => value;\nexpect(wrapper(page.locator('.ready'))).toBeTruthy();\n",
    "sha256": "2818e2590f3fac101d31085ab6ffd35fea44235e365f809587f550a16a428df3",
    "pattern": "#4f",
    "kind": "unresolved-locator",
    "diagnostic": {
      "code": "provenance-unsupported",
      "detector": "assertions",
      "start": 99
    }
  },
  {
    "name": "unresolved-numeric.ts",
    "text": "import { expect, test } from '@/fixtures';\ntest('numeric', async () => {\n  expect(0).toBeGreaterThanOrEqual(0);\n});\n",
    "sha256": "e195572698117a7c11213e56b8a769dd52141c93898e7657146ef327ef3d3ab3",
    "pattern": "#4a",
    "kind": "unresolved-fixture",
    "diagnostic": {
      "code": "import-unpinned",
      "detector": "assertions",
      "start": 75
    }
  }
];
for(const fixture of fixtures)test('original '+fixture.name+' retains a candidate and every hard diagnostic',()=>{
 assert.equal(createHash('sha256').update(fixture.text).digest('hex'),fixture.sha256);
 scan(fixture.text,fixture.name,(result,file)=>{
  assert.deepEqual(result.diagnostics,[]);
  assert.equal(result.findings.length,1);
  const hit=result.findings[0];
  assert.equal(hit.patternId,fixture.pattern);assert.equal(hit.line,3);assert.equal(hit.disposition,'candidate');
  assert.deepEqual(hit.evidence,{kind:fixture.kind,requirements:['verify-runtime-binding','verify-required-test-outcome']});
  assert.ok(fixture.text.slice(hit.start,hit.end).length>0);
  const run=spawnSync(process.execPath,[cli,'--scan',file,'--fail-on','none'],{encoding:'utf8',timeout:20000});
  assert.equal(run.status,2,run.stderr);const report=JSON.parse(run.stdout);
  assert.equal(report.status,'INCOMPLETE');
  assert.deepEqual(report.execution.diagnostics,[{...fixture.diagnostic,file}]);
  assert.ok(report.findings.some(item=>item.patternId===fixture.pattern&&item.line===3&&item.disposition==='candidate'));
 });
});
const pw="import {expect,test} from '@playwright/test';\n";
const body=text=>pw+"test('case',async({page})=>{"+text+"});";
test('query position review lane excludes known custom, foreign, shadowed, mutated and dynamic shapes',()=>{
 for(const text of [
  body('const database={query(){return {first(){}}}};database.query().first();'),
  "import {database} from 'custom';"+body('database.query().first();'),
  body('function nested(database){database.query().first();}'),
  body('database=custom;database.query().first();'),
  body('database.query=custom;database.query().first();'),
  body('database?.query().first();'),body('database.query()?.first();'),
  body("database['query']().first();"),body("database.query()['first']();"),
  body('database.query(value).first();'),body('database.query().first(1);'),
  body('database.query().nth(dynamic);'),
  "import {test} from 'vitest';test('x',()=>database.query().first());",
  "database.query().first();",
 ])assert.deepEqual(scan(text).findings,[],text);
});
test('transparent wrapper review lane excludes custom semantics, shadowed bindings, mutation and optional calls',()=>{
 const wrap=(wrapper,subject="page.locator('x')")=>pw+wrapper+"expect(wrapper("+subject+")).toBeTruthy();";
 for(const text of [
  wrap('const wrapper=value=>true;'),wrap('const wrapper=value=>({value});'),
  wrap('const wrapper=async value=>value;'),wrap('let wrapper=value=>value;'),
  wrap('const wrapper=value=>value;wrapper=custom;'),wrap('const wrapper=(value=other)=>value;'),
  wrap('const wrapper=(...value)=>value;'),
  wrap('const page={locator(){return true}};const wrapper=value=>value;'),
  wrap('const wrapper=value=>value;page=custom;'),
  wrap('const wrapper=value=>value;',"page?.locator('x')"),
  wrap('const wrapper=value=>value;',"page['locator']('x')"),
  wrap('const wrapper=value=>value;').replace('expect(wrapper(', 'expect(wrapper?.('),
  wrap('const wrapper=value=>value;').replace("'@playwright/test'","'vitest'"),
  wrap('const expect=custom;const wrapper=value=>value;'),
 ])assert.deepEqual(scan(text).findings,[],text);
});
test('unresolved numeric assertion needs same fixture context and exact nonnegativity shape',()=>{
 const prefix="import {expect,test} from '@/fixtures';";
 for(const text of [
  "import {expect,test} from 'vitest';test('x',()=>expect(0).toBeGreaterThanOrEqual(0));",
  prefix+"test('x',(expect)=>expect(0).toBeGreaterThanOrEqual(0));",
  prefix+"expect=custom;test('x',()=>expect(0).toBeGreaterThanOrEqual(0));",
  "import {test} from '@/fixtures';import {expect} from 'foreign';test('x',()=>expect(0).toBeGreaterThanOrEqual(0));",
  prefix+"expect(0).toBeGreaterThanOrEqual(0);",
  prefix+"test('x',()=>expect(0).not.toBeGreaterThanOrEqual(0));",
  prefix+"test('x',()=>expect(0).toBeGreaterThanOrEqual(1));",
  prefix+"test('x',()=>expect(value).toBeGreaterThanOrEqual(0));",
  prefix+"test('x',()=>expect(0)?.toBeGreaterThanOrEqual(0));",
 ])assert.deepEqual(scan(text).findings,[],text);
});
