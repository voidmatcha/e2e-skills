// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {accessibleNames} from '../src/accessible-names.mjs';
import {inventory} from '../src/inventory.mjs';
import {createScope} from '../src/scope.mjs';
function run(text,name='example.spec.ts'){
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'e2e-accessible-names-'))),filename=path.join(root,name),bytes=Buffer.from(text);
  fs.writeFileSync(filename,bytes);const manifest=inventory(root),scope=createScope({manifest,sources:new Map([[filename,bytes]])});
  return accessibleNames(bytes,filename,{scope});
}
const body=text=>`import {test} from '@playwright/test';\ntest('x',async({page})=>{\n${text}\n});`;
test('direct page accessible-name methods retain P1 candidate disposition',()=>{
  const result=run(body("page.getByRole('link',{name:'Job'});\npage.getByLabel('x',{name:'Job'});\npage.getByPlaceholder('x',{name:/Job/});"));
  assert.deepEqual(result.diagnostics,[]);assert.deepEqual(result.findings.map(f=>[f.line,f.patternId,f.severity,f.disposition]),[3,4,5].map(n=>[n,'#10c','P1','candidate']));
});
test('literal exact true/false and already-scoped locators retain legacy exclusions',()=>{
  const result=run(body("page.getByRole('link',{name:'Job',exact:true});\npage.getByRole('link',{name:'Job',exact:false});\npage.locator('nav').getByRole('link',{name:'Job'});\npage.getByRole('link');"));
  assert.deepEqual(result,{findings:[],diagnostics:[]});
});
test('Cypress only nominates direct unanchored regex role names',()=>{
  const result=run("cy.findByRole('link',{name:/Job/});\ncy.findByRole('link',{name:'Job'});\ncy.findByRole('link',{name:/^Job$/});\ncy.findByRole('link',{name:/^Job/});\ncy.findByLabelText('Job');\ncy.findByRole('link',{name:/Job/,exact:true});",'example.cy.ts');
  assert.deepEqual(result.diagnostics,[]);assert.deepEqual(result.findings.map(f=>f.line),[1,6]);
});
test('shadowed/foreign/type-only receivers and inert examples cannot be candidates',()=>{
  for(const text of [body("function helper(page){page.getByRole('link',{name:'Job'});}"),
    "const page={getByRole(){}};page.getByRole('link',{name:'Job'});",
    "import type {Page} from '@playwright/test';function helper(page:Page){page.getByRole('link',{name:'Job'});}",
    body("// page.getByRole('link',{name:'Job'});\nconst s=\"page.getByRole('link',{name:'Job'})\";"),
    "function helper(cy){cy.findByRole('link',{name:/Job/});}"])
    assert.deepEqual(run(text,'guard.cy.ts').findings,[],text);
});
test('spread/duplicate/computed/accessor options and dynamic exact produce diagnostics, not candidates',()=>{
  for(const options of ['options',"{name:'Job',...rest}","{name:'Job',name:'Other'}","{[key]:'Job'}","{name:'Job',exact:flag}","{get name(){return 'Job'}}"]){
    const result=run(body(`page.getByRole('link',${options});`));assert.deepEqual(result.findings,[]);assert.ok(result.diagnostics.length,options);
  }
});
test('Playwright dynamic names without exact are inexact candidates; with exact they are excluded',()=>{
  for(const name of ['value','`Edit ${value}`',"'Edit '+value",'labels[6]!','new RegExp(`^${value}$`)']){
    const result=run(body(`page.getByRole('link',{name:${name}});`));
    assert.deepEqual(result.diagnostics,[],name);assert.deepEqual(result.findings.map(f=>[f.line,f.patternId,f.disposition]),[[3,'#10c','candidate']],name);
    assert.deepEqual(run(body(`page.getByRole('link',{name:${name},exact:true});`)),{findings:[],diagnostics:[]},name);
  }
  // Cypress string names are exact; a dynamic Cypress name stays unresolved.
  const cy=run("cy.findByRole('link',{name:value});",'example.cy.ts');
  assert.deepEqual(cy.findings,[]);assert.match(cy.diagnostics[0].message,/dynamic accessible name/);
});
test('mutated Cypress global and Cypress multiline boundary remain diagnostic; Playwright multiline is a candidate',()=>{
  const mutated=run("cy.findByRole=custom;cy.findByRole('link',{name:/Job/});",'example.cy.ts');
  assert.deepEqual(mutated.findings,[]);assert.ok(mutated.diagnostics.length);
  const cyMultiline=run("cy.findByRole('link',{\nname:/Job/});",'example.cy.ts');
  assert.deepEqual(cyMultiline.findings,[]);assert.match(cyMultiline.diagnostics[0].message,/same-line/);
  const multiline=run(body("page\n.getByRole('link',{\nname:'Job'});"));
  assert.deepEqual(multiline.diagnostics,[]);assert.deepEqual(multiline.findings.map(f=>[f.line,f.patternId]),[[3,'#10c']]);
});
test('missing scope and malformed source stay diagnostic',()=>{
  assert.match(accessibleNames(Buffer.from(''),'example.ts').diagnostics[0].message,/pinned scope/);
  assert.ok(run('function (').diagnostics.length);
});
