// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {prepare} from '../scripts/run-probe.mjs';
const sha = text => createHash('sha256').update(text).digest('hex');
const runner = new URL('../scripts/run-probe.mjs',import.meta.url).pathname;
function fixture(t, {line = 16, column = 42} = {}) {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'probe-preapproval-')));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const source=path.join(root,'source');fs.mkdirSync(source);
  const quote="await expect(page.getByText('My bio')).toBeVisible();";
  const text='\n'.repeat(15)+quote+'\n';
  const native=String.raw`import fs from 'node:fs';
const failed=fs.readFileSync('test.spec.ts','utf8').includes('Bad bio');
fs.writeFileSync(process.env.E2E_PROBE_REPORT,JSON.stringify({config:{workers:1},suites:[{specs:[{title:'profile',file:'test.spec.ts',tests:[{results:[{status:failed?'failed':'passed',errors:failed?[{message:'toBeVisible failed\nExpected: visible\nReceived: hidden',location:{file:'test.spec.ts',line:${line},column:${column}}}]:[]}]}]}]}]}));process.exitCode=failed?1:0;`;
  for (const [name,value] of Object.entries({'test.spec.ts':text,'native.mjs':native,'README.md':'profile displays bio'}))fs.writeFileSync(path.join(source,name),value);
  const plan={version:1,source,test_selector:'profile',test_paths:['test.spec.ts'],mode:'assertion-mutation',promise:{path:'README.md',quote:'profile displays bio',sha256:sha('profile displays bio')},edits:[{path:'test.spec.ts',before:'My bio',after:'Bad bio',sha256:sha(text),kind:'test'}],test:{argv:[process.execPath,'native.mjs'],source:{path:'native.mjs',sha256:sha(native)}},report:{format:'playwright-json',path:'native.json'},expected_failure:{spec:'test.spec.ts',title:'profile',locator:{assertion:{path:'test.spec.ts',quote}},kind:'visibility',values:{expected:{type:'boolean',value:true},actual:{type:'boolean',relation:'exact',value:false}}}};
  const planPath=path.join(root,'plan.json');let counter=0;
  function invoke(extra=[],out=path.join(root,'out'+ ++counter),cwd=root) {
    fs.writeFileSync(planPath,JSON.stringify(plan));
    const child=spawnSync(process.execPath,[runner,'--plan',planPath,'--output-dir',out,...extra],{cwd,encoding:'utf8',timeout:15000});
    assert.equal(child.error,undefined);return {code:child.status,out,...JSON.parse(child.stdout)};
  }
  return {root,source,quote,plan,invoke};
}
test('preview derives real assertion span instead of guessed off-by-one line',t=>{
  const f=fixture(t),prepared=prepare(f.plan);
  assert.deepEqual(prepared.expectedFailure.start,{line:16,column:1});
  assert.deepEqual(prepared.expectedFailure.end,{line:16,column:f.quote.length});
  const preview=f.invoke(),result=f.invoke(['--execute','--trust-checkout','--approve-sha256',preview.approval_sha256]);
  assert.equal(result.verdict,'ASSERTION_SENSITIVE',result.error);
  assert.deepEqual(result.expected_failure_target,prepared.expectedFailure);
});
test('changed or ambiguous source assertion is refused before any target command',t=>{
  const f=fixture(t);
  for (const quote of ['missing();',"page.getByText('My bio')",f.quote+'\nmissing();']) {
    f.plan.expected_failure.locator.assertion.quote=quote;
    assert.throws(()=>prepare(f.plan),/failure assertion/);
  }
  f.plan.expected_failure.locator.assertion.quote=f.quote;
  fs.appendFileSync(path.join(f.source,'test.spec.ts'),f.quote);
  f.plan.edits[0].sha256=sha(fs.readFileSync(path.join(f.source,'test.spec.ts')));
  f.plan.edits[0].before='\n'+f.quote+'\n';f.plan.edits[0].after='\n'+f.quote.replace('My bio','Bad bio')+'\n';
  assert.throws(()=>prepare(f.plan),/exactly once/);
});
test('whole callback body and conflicting manual coordinates cannot widen source linkage',t=>{
  const f=fixture(t);f.plan.expected_failure.locator.location='test.spec.ts:17';
  assert.throws(()=>prepare(f.plan),/locator must choose/);delete f.plan.expected_failure.locator.location;
  const body="test('profile', async () => { await expect(1).toBe(1); });";
  fs.writeFileSync(path.join(f.source,'test.spec.ts'),body);
  Object.assign(f.plan.edits[0],{sha256:sha(body),before:'toBe(1)',after:'toBe(2)'});
  f.plan.expected_failure.locator.assertion.quote=body;
  assert.throws(()=>prepare(f.plan),/callbacks or a whole test/);
});
test('relative sibling output works while traversed symlinks and source overlap refuse',t=>{
  const f=fixture(t),preview=f.invoke([],'../preview',f.source);
  assert.equal(preview.verdict,'PREVIEW',preview.error);
  assert.equal(fs.existsSync(path.join(f.root,'preview/preview.json')),true);
  assert.equal(f.invoke([],'../source/inside',f.source).verdict,'ERROR');
  fs.symlinkSync(f.source,path.join(f.root,'alias'),'dir');
  const bad=f.invoke([],'alias/../escape');assert.equal(bad.verdict,'ERROR');assert.match(bad.error,/symlink/);
  assert.equal(fs.existsSync(path.join(f.root,'escape')),false);
});

for (const coordinate of [{line:17,column:42},{line:16,column:99},{line:15,column:42}]) {
  test(`native location ${coordinate.line}:${coordinate.column} outside the approved source span stays unverified`, t => {
    const f=fixture(t,coordinate),preview=f.invoke();
    const result=f.invoke(['--execute','--trust-checkout','--approve-sha256',preview.approval_sha256]);
    assert.equal(result.verdict,'CANNOT_VERIFY');
    assert.equal(result.verification.V2.verdict,'CANNOT_VERIFY');
  });
}

test('saved preview and output both accept checked sibling CLI paths', t => {
  const f=fixture(t),preview=f.invoke([],'../preview',f.source);
  const child=spawnSync(process.execPath,[runner,'--approved-preview','../preview/preview.json','--output-dir','../execution','--execute','--trust-checkout','--approve-sha256',preview.approval_sha256],{cwd:f.source,encoding:'utf8',timeout:15000});
  assert.equal(child.status,0,child.stderr+child.stdout);
  assert.equal(JSON.parse(child.stdout).verdict,'ASSERTION_SENSITIVE');
});
