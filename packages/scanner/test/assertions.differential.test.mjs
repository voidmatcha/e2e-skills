// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {assertions} from '../src/assertions.mjs';
import {inventory} from '../src/inventory.mjs';
import {createScope} from '../src/scope.mjs';
const repository=fileURLToPath(new URL('../../../',import.meta.url));

test('optional/computed #4f compares identical inputs and original legacy regression fixture bytes', {timeout:90000}, t=>{
  const root=fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()),'e2e-truthiness-variants-'));
  try {
    const extract=spawnSync('python3',['-c',[
      'import ast,json,sys',
      'tree=ast.parse(open(sys.argv[1]).read());fixtures={}',
      'for call in ast.walk(tree):',
      " if not(isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and call.func.attr=='write_text'):continue",
      ' try:text=ast.literal_eval(call.args[0])',
      ' except (ValueError,TypeError):continue',
      ' if not isinstance(text,str):continue',
      " if 'template focus' in text and 'computed focus' in text:fixtures['computed.spec.ts']=text",
      " if \"const truthyMatcher = 'toBeTruthy';\" in text:fixtures['computed-cjs.spec.ts']=text",
      'print(json.dumps(fixtures))',
    ].join('\n'),legacyOracleFile('regression/test-reviewer-scanner.py')],{encoding:'utf8'});
    assert.ifError(extract.error);assert.equal(extract.status,0,extract.stderr);
    const files=JSON.parse(extract.stdout);
    assert.deepEqual(Object.keys(files).sort(),['computed-cjs.spec.ts','computed.spec.ts']);
    files['variants.spec.ts']="import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n"+
      "expect?.(page.locator('optional')).toBeTruthy();\n"+
      "expect(page.locator('literal'))['toBeDefined']();\n"+
      "const matcher='toBeTruthy';\nexpect(page.locator('immutable'))[matcher]();\n"+
      "expect(page.locator('optional-matcher')).toBeTruthy?.();\n"+
      "});\n";
    for(const [name,text] of Object.entries(files))fs.writeFileSync(path.join(root,name),text);
    const manifest=inventory(root);
    assert.equal(manifest.complete,true,JSON.stringify(manifest.errors));
    const sources=new Map(manifest.candidates.map(item=>[item.path,fs.readFileSync(item.path)]));
    const scope=createScope({manifest,sources}),expected=[];
    for(const [file,bytes] of sources) {
      const result=assertions(bytes,file,{scope});
      const hits=result.findings.filter(hit=>hit.patternId==='#4f');
      assert.ok(hits.every(hit=>hit.severity==='P0'&&hit.disposition==='candidate'),file);
      if(path.basename(file)==='computed-cjs.spec.ts') {
        assert.equal(hits.length,0,'unbound Page in the unchanged legacy fixture is not runtime proof');
        assert.ok(result.diagnostics.length,'unproven Page/mutable key gaps remain visible');
      } else assert.deepEqual(result.diagnostics,[],file);
      for(const hit of hits)expected.push(`${path.basename(file)}:${hit.line}`);
    }
    assert.deepEqual(expected.sort(),['computed.spec.ts:5','variants.spec.ts:3','variants.spec.ts:4','variants.spec.ts:6','variants.spec.ts:7']);
    const env={...process.env,E2E_SMELL_ALLOW_PROJECT_ESLINT:'0',E2E_SMELL_NO_ESLINT_DOWNLOAD:'1',E2E_SMELL_DISABLE_AST_GREP:'1',E2E_SMELL_NO_AST_GREP_DOWNLOAD:'1',E2E_SMELL_FAIL_ON:'none'};
    delete env.BASH_ENV;delete env.ENV;
    const legacy=spawnSync('/bin/bash',['-p',legacyOracleFile(),root],{cwd:repository,env,encoding:'utf8',timeout:75000,maxBuffer:4000000});
    assert.ifError(legacy.error);
    const output=legacy.stdout+legacy.stderr;
    assert.equal(legacy.status,0,output);assert.doesNotMatch(output,/INCOMPLETE/);
    let active=false;
    const observed=[];
    for(const line of output.split('\n')) {
      if(line.startsWith('['))active=/^\[P0\?\]\[LLM-TRIAGE\] #4f /.test(line);
      if(!active)continue;
      const hit=line.match(/([^/\s]+\.spec\.ts):(\d+):/);
      if(hit)observed.push(`${hit[1]}:${hit[2]}`);
    }
    const unique=[...new Set(observed)].sort();
    const gaps=['computed-cjs.spec.ts:5'];
    const falseNegatives=['variants.spec.ts:7'];
    for(const hit of gaps)assert.ok(unique.includes(hit),output);
    for(const hit of falseNegatives)assert.ok(!unique.includes(hit),output);
    assert.deepEqual(unique.filter(hit=>!gaps.includes(hit)),expected.filter(hit=>!falseNegatives.includes(hit)),output);
    t.diagnostic(JSON.stringify({status:'EXPLICIT_COVERAGE_GAP',legacyFindings:gaps,nodeFindings:[],reason:'unchanged fixture has no runtime-proven Page binding'}));
    t.diagnostic(JSON.stringify({status:'KNOWN_LEGACY_FALSE_NEGATIVES',legacyFindings:[],nodeFindings:falseNegatives,reason:'optional matcher invocation is not collected by the legacy matcher regex'}));
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
