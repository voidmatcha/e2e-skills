// SPDX-License-Identifier: Apache-2.0
import { legacyOracleFile } from '../../../scripts/ci/fixtures/legacy-scanner/oracle.mjs';
// Actual unchanged legacy #10c versus exact original regression fixture bytes.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {accessibleNames} from '../src/accessible-names.mjs';
import {inventory} from '../src/inventory.mjs';
import {createScope} from '../src/scope.mjs';
const repo=fileURLToPath(new URL('../../../',import.meta.url)),sha=b=>createHash('sha256').update(b).digest('hex');

// Fixed installation roots only: no PATH/PYTHON override or project executable.
// -I ignores Python path/startup environment and disables user site packages.
const pythonEnv={PATH:'/usr/bin:/bin',LANG:'C.UTF-8'};
function trustedPython(){
  const project=fs.realpathSync(repo);
  for(const candidate of ['/usr/bin/python3','/usr/local/bin/python3','/opt/homebrew/bin/python3.12','/opt/homebrew/bin/python3']){
    let executable;
    try{executable=fs.realpathSync(candidate);}catch{continue;}
    if(executable===project||executable.startsWith(project+path.sep)||
      !['/usr/','/opt/homebrew/','/Library/Frameworks/Python.framework/'].some(root=>executable.startsWith(root)))continue;
    const probe=spawnSync(executable,['-I','-B','-c','import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)'],
      {env:pythonEnv,encoding:'utf8',timeout:5000});
    if(!probe.error&&probe.status===0)return executable;
  }
  throw new Error('Python >=3.10 is required in a trusted fixed system installation outside the project');
}

test('original PW/Cypress #10c fixtures compare with actual unchanged legacy',{timeout:90000},()=>{
  const regression=legacyOracleFile('regression/test-reviewer-scanner.py'),regressionBytes=fs.readFileSync(regression);
  const python=trustedPython();
  const extract=spawnSync(python,['-I','-B','-c',`import ast,json,sys
module=ast.parse(sys.stdin.read())
result={}
for name in ['assert_static_accessible_name_is_triage_only','assert_cypress_role_name_matching_boundaries']:
 fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name==name)
 call=next(n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='write_text')
 result[name]=ast.literal_eval(call.args[0])
print(json.dumps(result))`],{input:regressionBytes,encoding:'utf8',env:pythonEnv,timeout:10000});
  assert.equal(extract.status,0,extract.stderr);const originals=JSON.parse(extract.stdout);
  const base=process.env.ACCESSIBLE_NAMES_EVIDENCE_ROOT||os.tmpdir();fs.mkdirSync(base,{recursive:true});
  const root=fs.realpathSync(fs.mkdtempSync(path.join(base,'e2e-accessible-names-diff-'))),fixture=path.join(root,'fixture');fs.mkdirSync(fixture);
  const files={
    'static-name.spec.ts':Buffer.from(originals.assert_static_accessible_name_is_triage_only),
    'role.cy.ts':Buffer.from(originals.assert_cypress_role_name_matching_boundaries),
    'boundary.spec.ts':Buffer.from("import {test} from '@playwright/test';\ntest('x',async({page})=>{\npage.getByRole('link',{name:'Job',exact:true});\npage.getByRole('link',{name:'Job',exact:false});\npage.locator('nav').getByRole('link',{name:'Job'});\n});\n"),
    'foreign.spec.ts':Buffer.from("import {test} from '@playwright/test';\nfunction helper(page){\npage.getByRole('link',{name:'Job'});\n}\n"),
  };
  for(const[n,b]of Object.entries(files))fs.writeFileSync(path.join(fixture,n),b);
  const manifest=inventory(fixture);assert.equal(manifest.complete,true);
  const scope=createScope({manifest,sources:new Map(Object.entries(files).map(([n,b])=>[path.join(fixture,n),b]))});
  const owned=Object.fromEntries(Object.entries(files).map(([n,b])=>[n,accessibleNames(b,path.join(fixture,n),{scope})]));
  const scanner=legacyOracleFile(),scannerHash=sha(fs.readFileSync(scanner));
  const native=spawnSync('/bin/bash',['-p',scanner,fixture],{cwd:repo,encoding:'utf8',timeout:75000,maxBuffer:4*1024*1024,
    env:{PATH:'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',HOME:os.homedir(),E2E_SMELL_ALLOW_PROJECT_ESLINT:'0',
      E2E_SMELL_NO_ESLINT_DOWNLOAD:'1',E2E_SMELL_DISABLE_AST_GREP:'1',E2E_SMELL_NO_AST_GREP_DOWNLOAD:'1',E2E_SMELL_FAIL_ON:'none'}});
  fs.writeFileSync(path.join(root,'legacy.stdout.txt'),native.stdout||'');fs.writeFileSync(path.join(root,'legacy.stderr.txt'),native.stderr||'');
  assert.ifError(native.error);assert.equal(native.status,0,native.stderr);assert.doesNotMatch(native.stdout+native.stderr,/INCOMPLETE/);
  const legacy=Object.fromEntries(Object.keys(files).map(n=>[n,[]]));let active=false;
  for(const line of native.stdout.split('\n')){
    if(line.startsWith('['))active=/^\[P1\?\]\[LLM-TRIAGE\] #10c /.test(line);
    if(!active)continue;
    for(const name of Object.keys(files)){const i=line.indexOf(name+':');if(i<0)continue;const m=/^(\d+):/.exec(line.slice(i+name.length+1));if(m)legacy[name].push(Number(m[1]));}
  }
  const receipt={schema:'accessible-names-legacy-differential-v1',complete:false,legacyScannerSha256:scannerHash,
    regressionSourceSha256:sha(regressionBytes),pythonExecutable:python,moduleSha256:sha(fs.readFileSync(new URL('../src/accessible-names.mjs',import.meta.url))),
    sourceHashes:Object.fromEntries(Object.entries(files).map(([n,b])=>[n,sha(b)])),nativeStatus:native.status,legacyStdoutSha256:sha(native.stdout),owned,legacy,
    caveat:'P1 semantic candidates only. Preserve direct page/cy spelling, explicit exact:false exclusion and leading-^ Cypress exclusion. Source provenance removes a legacy custom receiver false positive. No full parity claim.'};
  const output=path.join(root,'receipt.json');fs.writeFileSync(output,JSON.stringify(receipt,null,2)+'\n');console.log('retained accessible-name evidence: '+root);
  assert.deepEqual(legacy['static-name.spec.ts'],[3]);assert.deepEqual(legacy['role.cy.ts'],[2]);
  assert.deepEqual(legacy['boundary.spec.ts'],[]);assert.deepEqual(legacy['foreign.spec.ts'],[3]);
  for(const name of ['static-name.spec.ts','role.cy.ts','boundary.spec.ts'])assert.deepEqual(owned[name].findings.map(f=>f.line),legacy[name]);
  assert.deepEqual(owned['foreign.spec.ts'].findings,[]);
  for(const[name,b]of Object.entries(files)){
    assert.ok(owned[name].findings.every(f=>f.patternId==='#10c'&&f.severity==='P1'&&f.disposition==='candidate'));
    assert.equal(sha(fs.readFileSync(path.join(fixture,name))),sha(b));
  }
  assert.equal(sha(fs.readFileSync(scanner)),scannerHash);assert.equal(sha(fs.readFileSync(regression)),sha(regressionBytes));
  receipt.complete=true;fs.writeFileSync(output,JSON.stringify(receipt,null,2)+'\n');
});
