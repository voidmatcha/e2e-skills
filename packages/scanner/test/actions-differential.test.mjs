// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';
import {inventory} from '../src/inventory.mjs';
import {createScope} from '../src/scope.mjs';
import {actions} from '../src/actions.mjs';
const repository=fileURLToPath(new URL('../../../',import.meta.url));
test('actual legacy #5b comparison retains parity and separate custom/shadow false positives', {timeout:90000},()=>{
  const directory=fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()),'e2e-actions-diff-'));
  try {
    const files={
      'example.spec.ts':"import {test} from '@playwright/test';\ntest('x',async({page})=>{\nawait page.locator('button').click({force:true});\nawait page.locator('input').fill('text',{\n 'force':true\n});\nawait page.click('button',{force:true});\nawait page.locator('button').click({force:false});\n});\n",
      'example.cy.ts':"cy.get('button')\n.click({force:true});\ncy.get('input').type('text',{\nforce:true\n});\ncy.get('button').click(10,20,{force:true});\n",
      'foreign.spec.ts':"import {test} from 'vitest';test('unit',async({page})=>{page.locator('button').click({force:true});});\n",
      // Known legacy false positives: E2E file membership does not prove the
      // custom .click object or the locally shadowed page receiver.
      'legacy-false-positive.spec.ts':"import {test} from '@playwright/test';\nconst custom={click(){}};\ncustom.click({force:true});\nfunction local(page){\npage.locator('button').click({force:true});\n}\n",
    };
    for(const [name,text] of Object.entries(files))fs.writeFileSync(path.join(directory,name),text);
    const manifest=inventory(directory);
    assert.equal(manifest.complete,true);
    const sources=new Map(manifest.candidates.map(item=>[item.path,fs.readFileSync(item.path)]));
    const scope=createScope({manifest,sources});
    const expected={'example.spec.ts':[3,5,7],'example.cy.ts':[2,4,6],'foreign.spec.ts':[],'legacy-false-positive.spec.ts':[]};
    for(const [file,lines] of Object.entries(expected)) {
      const absolute=path.join(directory,file),result=actions(sources.get(absolute),absolute,{scope});
      assert.deepEqual(result.findings.map(item=>item.line),lines,file);
      if(file==='example.spec.ts'||file==='example.cy.ts')assert.deepEqual(result.diagnostics,[],file);
      else assert.ok(result.diagnostics.every(item=>item.message==='unsupported provenance-producing call'),file);
      for(const finding of result.findings)assert.deepEqual([finding.patternId,finding.severity,finding.disposition],['#5b','P1','confirmed']);
    }
    const env={...process.env,E2E_SMELL_ALLOW_PROJECT_ESLINT:'0',E2E_SMELL_NO_ESLINT_DOWNLOAD:'1',E2E_SMELL_DISABLE_AST_GREP:'1',E2E_SMELL_NO_AST_GREP_DOWNLOAD:'1',E2E_SMELL_FAIL_ON:'none'};
    delete env.BASH_ENV;delete env.ENV;
    const result=spawnSync('/bin/bash',['-p',legacyOracleFile(),directory],{cwd:repository,env,encoding:'utf8',timeout:75000,maxBuffer:4000000});
    assert.ifError(result.error);
    const output=result.stdout+result.stderr;
    assert.equal(result.status,0,output);
    assert.doesNotMatch(output,/INCOMPLETE/);
    const actual=Object.fromEntries(Object.keys(files).map(file=>[file,[]]));
    let active=false;
    for(const line of output.split('\n')) {
      if(line.startsWith('['))active=/^\[P1\] #5b Forced actionability bypass/.test(line);
      if(!active)continue;
      for(const file of Object.keys(files)) {
        const index=line.indexOf(file+':');
        if(index<0)continue;
        const hit=/^(\d+):/.exec(line.slice(index+file.length+1));
        if(hit)actual[file].push(Number(hit[1]));
      }
    }
    assert.deepEqual(actual,{...expected,'legacy-false-positive.spec.ts':[3,5]},output);
  }finally{fs.rmSync(directory,{recursive:true,force:true});}
});
