// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {assertions} from '../src/assertions.mjs';
import {inventory} from '../src/inventory.mjs';
import {createScope} from '../src/scope.mjs';
const repository=fileURLToPath(new URL('../../../',import.meta.url));
function withSource(text,callback) {
  const root=fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()),'e2e-cypress-jquery-gap-'));
  try {
    const file=path.join(root,'example.cy.ts');fs.writeFileSync(file,text);
    const manifest=inventory(root);assert.equal(manifest.complete,true,JSON.stringify(manifest.errors));
    const sources=new Map(manifest.candidates.map(item=>[item.path,fs.readFileSync(item.path)]));
    const scope=createScope({manifest,sources});callback(assertions(sources.get(file),file,{scope}),file);
  } finally {fs.rmSync(root,{recursive:true,force:true});}
}
const body=text=>`describe('x',()=>{it('x',()=>{\n${text}\n});});\n`;
test('direct Cypress jQuery truthiness with ambient expect is a P0 candidate only',()=>{
  withSource(body("expect(Cypress.$('.x')).to.exist;\nexpect(Cypress.$('.x')).to.be.ok;\nexpect(Cypress.$('.x')).toBeTruthy();"),result=>{
    assert.deepEqual(result.findings.map(item=>[item.patternId,item.severity,item.disposition,item.line]),
      [2,3,4].map(line=>['#4f','P0','candidate',line]));
    assert.deepEqual(result.diagnostics,[]);
  });
});
test('foreign imports, namespaces, lexical shadows and unrelated subjects do not become Cypress gaps',()=>{
  for(const text of [
    "import {expect} from 'vitest';\n"+body("expect(Cypress.$('.x')).to.exist;"),
    "import * as chai from 'chai';\n"+body("chai.expect(Cypress.$('.x')).to.exist;"),
    "import * as Cypress from 'other';\n"+body("expect(Cypress.$('.x')).to.exist;"),
    body("function f(expect){expect(Cypress.$('.x')).to.exist;}"),
    body("function f(Cypress){expect(Cypress.$('.x')).to.exist;}"),
    body("expect(custom.$('.x')).to.exist;expect(Cypress.$('.x')).not.to.exist;"),
    body("expect(Cypress.$('.x').length).to.exist;expect(Cypress.$('.x').is(':visible')).to.be.ok;"),
    body("const expect=x=>x;expect(Cypress.$('.x')).to.exist;"),
  ]) withSource(text,result=>{assert.deepEqual(result.findings,[],text);assert.deepEqual(result.diagnostics,[],text);});
});
test('Cypress runtime mutations remain incomplete without promoting a candidate',()=>{
  for(const prefix of ['Cypress.$=custom;','Object.assign(Cypress,{$:custom});',
    'globalThis.Cypress=custom;', 'const alias=Cypress;alias.$=custom;',
    'expect=custom;', 'globalThis.expect=custom;', 'Object.assign(expect,{custom});',
    'const alias=expect;alias.custom=1;', 'let alias;alias=expect;Reflect.set(alias,"custom",1);',
    'const {expect:alias}=globalThis;Object.assign(alias,{custom});']) {
    withSource(body(prefix+"expect(Cypress.$('.x')).to.exist;"),result=>{
      assert.deepEqual(result.findings,[]);assert.ok(result.diagnostics.length,prefix);
    });
  }
});
test('bounded CLI preserves candidate policy without claiming complete coverage',()=>{
  withSource(body("expect(Cypress.$('.missing')).to.exist;"),(_result,file)=>{
    for(const [policy,status] of [['p0',0],['p0-candidate',1]]) {
      const result=spawnSync(process.execPath,[path.join(repository,'packages/scanner/src/cli.mjs'),'--bounded-static','--fail-on',policy,file],{cwd:repository,encoding:'utf8',timeout:20000});
      assert.equal(result.status,status,result.stderr);const output=JSON.parse(result.stdout);
      assert.equal(output.execution.complete,true);assert.equal(output.execution.exitCode,status);
      assert.equal(output.coverage.complete,false);assert.equal(output.status,'PARTIAL');
      assert.equal(output.findings.length,1);assert.equal(output.findings[0].disposition,'candidate');
    }
  });
});
