// SPDX-License-Identifier: Apache-2.0
// Run unchanged legacy #18 against the exact existing alias regression bytes.
// External receipts retain raw output and explicit awaited/inline discovery gaps.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {softAssertions} from '../../../../packages/scanner/src/soft-assertions.mjs';
import {inventory} from '../../../../packages/scanner/src/inventory.mjs';
import {createScope} from '../../../../packages/scanner/src/scope.mjs';
const repo=fileURLToPath(new URL('../../../../',import.meta.url));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');

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

const regression=path.join(repo,'scripts/ci/test-reviewer-scanner.py');
const scanner=path.join(repo,'skills/e2e-reviewer/scripts/scan.sh');
const regressionBytes=fs.readFileSync(regression),scannerBytes=fs.readFileSync(scanner);
// Parse Python's AST; never import/execute the regression or a target config.
const python=trustedPython();
const extract=spawnSync(python,['-I','-B','-c',`import ast,sys
module=ast.parse(sys.stdin.read())
fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='assert_expect_aliases_and_page_receiver_provenance')
call=next(n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='write_text')
sys.stdout.write(ast.literal_eval(call.args[0]))`],{input:regressionBytes,encoding:'utf8',env:pythonEnv,timeout:10000});
assert.equal(extract.status,0,extract.stderr);
const base=process.env.SOFT_ASSERTIONS_EVIDENCE_ROOT || path.join(os.homedir(),'.cache/e2e-skills-bench');
fs.mkdirSync(base,{recursive:true});const root=fs.realpathSync(fs.mkdtempSync(path.join(base,'soft-assertions-diff-')));
const fixture=path.join(root,'fixture');fs.mkdirSync(fixture);
const files={
  'aliases.spec.ts':Buffer.from(extract.stdout),
  'boundary.spec.ts':Buffer.from("import {expect} from '@playwright/test';\nimport * as pw from '@playwright/test';\nexpect.soft(form).toBeVisible();\nawait expect.soft(form).toBeVisible();\nfunction helper(){return expect.soft(form).toBeVisible();}\npw.expect.soft(form).toBeVisible();\nexpect\n.soft(form).toBeVisible();\nexpect.soft(a).toBeVisible(); expect.soft(b).toBeVisible();\n"),
  'guards.spec.ts':Buffer.from("import {expect} from '@playwright/test';\n// expect.soft(item)\nconst s='expect.soft(item)';\nfunction helper(expect){\nexpect.soft(item).toBeVisible();\n}\nexpect(item).toBeVisible();\n"),
};
for(const [name,bytes]of Object.entries(files))fs.writeFileSync(path.join(fixture,name),bytes);
const manifest=inventory(fixture),sources=new Map(Object.entries(files).map(([n,b])=>[path.join(fixture,n),b]));
assert.equal(manifest.complete,true);const scope=createScope({manifest,sources});
const owned=Object.fromEntries(Object.keys(files).map(name=>[name,softAssertions(files[name],path.join(fixture,name),{scope})]));
const native=spawnSync('/bin/bash',['-p',scanner,fixture],{cwd:repo,encoding:'utf8',timeout:75000,maxBuffer:4*1024*1024,
  env:{PATH:'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',HOME:os.homedir(),E2E_SMELL_ALLOW_PROJECT_ESLINT:'0',
    E2E_SMELL_NO_ESLINT_DOWNLOAD:'1',E2E_SMELL_DISABLE_AST_GREP:'1',E2E_SMELL_NO_AST_GREP_DOWNLOAD:'1',E2E_SMELL_FAIL_ON:'none'}});
fs.writeFileSync(path.join(root,'legacy.stdout.txt'),native.stdout || '');fs.writeFileSync(path.join(root,'legacy.stderr.txt'),native.stderr || '');
assert.ifError(native.error);assert.equal(native.status,0,native.stderr);assert.doesNotMatch(native.stdout+native.stderr,/INCOMPLETE/);
const legacy=Object.fromEntries(Object.keys(files).map(name=>[name,[]]));let active=false;
for(const line of native.stdout.split('\n')){
  if(line.startsWith('['))active=/^\[P1\?\]\[LLM-TRIAGE\] #18 /.test(line);
  if(!active)continue;
  for(const name of Object.keys(files)){const i=line.indexOf(name+':');if(i<0)continue;const m=/^(\d+):/.exec(line.slice(i+name.length+1));if(m)legacy[name].push(Number(m[1]));}
}
const receipt={schema:'soft-assertions-legacy-differential-v1',complete:false,legacyScannerSha256:sha(scannerBytes),
  regressionSourceSha256:sha(regressionBytes),pythonExecutable:python,extractedFunction:'assert_expect_aliases_and_page_receiver_provenance',
  moduleSha256:sha(fs.readFileSync(new URL('../../../../packages/scanner/src/soft-assertions.mjs',import.meta.url))),
  sourceHashes:Object.fromEntries(Object.entries(files).map(([n,b])=>[n,sha(b)])),nativeStatus:native.status,
  legacyStdoutSha256:sha(native.stdout),owned,legacy,
  caveat:'Candidate only. Preserve legacy unawaited line-start boundary; awaited/return/multiline/later-inline are diagnostic gaps, not expanded candidates. No semantic dependency verdict.'};
fs.writeFileSync(path.join(root,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
console.log(root);
assert.deepEqual(legacy['aliases.spec.ts'],[5]);assert.deepEqual(legacy['boundary.spec.ts'],[3,6,9]);assert.deepEqual(legacy['guards.spec.ts'],[]);
for(const name of Object.keys(files)){
  assert.deepEqual(owned[name].findings.map(f=>f.line),legacy[name],name);
  assert.ok(owned[name].findings.every(f=>f.patternId==='#18'&&f.severity==='P1'&&f.disposition==='candidate'));
  assert.equal(sha(fs.readFileSync(path.join(fixture,name))),sha(files[name]));
}
assert.equal(owned['boundary.spec.ts'].diagnostics.length,4);
assert.equal(sha(fs.readFileSync(regression)),sha(regressionBytes));assert.equal(sha(fs.readFileSync(scanner)),sha(scannerBytes));
receipt.complete=true;
fs.writeFileSync(path.join(root,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
console.log('PASS: unchanged legacy original-byte regression + boundary/FP guards');
