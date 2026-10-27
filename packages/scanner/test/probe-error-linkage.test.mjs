// SPDX-License-Identifier: Apache-2.0
// Authored native-report contract fixtures, not browser or model accuracy evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {prepare, execute} from '../scripts/run-probe.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');
const linked = {message:'expected transfer',location:{file:'test.spec.ts',line:25,column:3}};
async function probe(t, {format='playwright-json', errors=[linked], restoredErrors=errors, correct=false, observerFault, nativeFault, mode='behavior-fault', location='test.spec.ts:25:3', spec='test.spec.ts'}={}) {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'probe-linkage-')));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const source=path.join(root,'source'),out=path.join(root,'out');fs.mkdirSync(source);fs.mkdirSync(out);
  const native=`import fs from 'node:fs';
const changed=fs.readFileSync(${JSON.stringify(mode==='behavior-fault'?'app.txt':'test.spec.ts')},'utf8')==='BROKEN';
const failed=${correct?'changed':'!changed'},status=failed?'failed':'passed';
const errors=JSON.parse(JSON.stringify(failed?(process.env.E2E_PROBE_PHASE==='restored'?${JSON.stringify(restoredErrors)}:${JSON.stringify(errors)}):[]).replaceAll('{project}',process.cwd()));
const report=${JSON.stringify(format)}==='playwright-json'
 ?{config:{workers:1},suites:[{specs:[{title:'transfer',file:'test.spec.ts',tests:[{expectedStatus:'passed',results:[{status,retry:0,errors}]}]}]}]}
 :{totalTests:1,totalPending:0,totalSkipped:0,totalPassed:Number(!failed),totalFailed:Number(failed),runs:[{spec:{relative:'test.spec.ts'},tests:[{title:['transfer'],state:status,displayError:errors[0],attempts:[{state:status,error:errors[1]}]}]}]};
if (${JSON.stringify(nativeFault)}==='missing-report' && process.env.E2E_PROBE_PHASE==='fault') process.exit(0);
fs.writeFileSync(process.env.E2E_PROBE_REPORT,${JSON.stringify(nativeFault)}==='malformed-report' && process.env.E2E_PROBE_PHASE==='fault'?'not JSON':JSON.stringify(report));
process.exitCode=failed?1:0;
if (${JSON.stringify(nativeFault)}==='exit-mismatch' && process.env.E2E_PROBE_PHASE==='fault') process.exitCode=1;
if (${JSON.stringify(nativeFault)}==='timeout' && process.env.E2E_PROBE_PHASE==='fault') await new Promise(resolve=>setTimeout(resolve,30000));`.replaceAll('test.spec.ts',spec);
  const observer=`import fs from 'node:fs';import {createHash} from 'node:crypto';
const broken=fs.readFileSync('app.txt','utf8')==='BROKEN',value=JSON.stringify({actual:broken?'old':'transferred'});
fs.writeFileSync('observation.json',value);
const observation={project:process.cwd(),promised_effect:!broken,fault_reached:broken,evidence:[{path:'observation.json',sha256:createHash('sha256').update(value).digest('hex')}]};
${observerFault==='provenance'?"observation.project+='/wrong';":observerFault==='hash'?"observation.evidence[0].sha256='0'.repeat(64);":observerFault==='missing-evidence'?'observation.evidence=[];':observerFault==='contradictory-normal'?'if (!broken) observation.fault_reached=true;':''}
console.log(JSON.stringify(observation));${observerFault==='exit'?'process.exitCode=1;':''}`;
  const files={'app.txt':'WORKS',[spec]:'WORKS','README.md':'copy transfers content','native.mjs':native,'observer.mjs':observer};
  for(const [name,value] of Object.entries(files))fs.writeFileSync(path.join(source,name),value);
  const plan={version:1,source,test_selector:'transfer',test_paths:[spec],mode,promise:{path:'README.md',quote:files['README.md'],sha256:sha(files['README.md'])},edits:[{path:mode==='behavior-fault'?'app.txt':spec,before:'WORKS',after:'BROKEN',sha256:sha('WORKS'),kind:mode==='behavior-fault'?'source':'test'}],test:{argv:[process.execPath,'native.mjs'],timeout_seconds:5,source:{path:'native.mjs',sha256:sha(native)}},...(mode==='behavior-fault'?{observer:{argv:[process.execPath,'observer.mjs'],source:{path:'observer.mjs',sha256:sha(observer)}}}:{}),report:{format,path:'native-report.json'},expected_failure:{contains:'expected transfer',location}};
  if (nativeFault==='timeout') plan.test.timeout_seconds=1;
  const result=await execute(plan,prepare(plan),out);
  if (nativeFault==='timeout') {
    const receipt=JSON.parse(fs.readFileSync(path.join(out,'fault/test/command.json'),'utf8'));
    assert.equal(receipt.timeout,true);assert.equal(receipt.exit_code,null);
  }
  return result;
}
const noSignal=result=>{assert.equal(result.verdict,'CANNOT_VERIFY');assert.equal(result.behavior_comparison,undefined);assert.equal(result.behavior_proof,false);assert.equal(result.original_source_unchanged,true);};
for(const format of ['playwright-json','cypress-json']) {
  test(`${format}: linked inversion retains diagnostic without behavior proof`,async t=>{
    const r=await probe(t,{format});assert.equal(r.verdict,'CANNOT_VERIFY');assert.equal(r.behavior_comparison?.classification,'INVERTED_RESPONSE');assert.equal(r.behavior_proof,false);
  });
  test(`${format}: exact line-only anchor accepts an optional native column`,async t=>{
    const r=await probe(t,{format,location:'test.spec.ts:25'});assert.equal(r.behavior_comparison?.classification,'INVERTED_RESPONSE');
  });
  test(`${format}: legitimate behavior test still detects the fault`,async t=>{
    const r=await probe(t,{format,correct:true});assert.equal(r.verdict,'DETECTED');assert.equal(r.behavior_comparison,undefined);assert.equal(r.behavior_proof,true);
  });
  test(`${format}: matcher and location in separate errors cannot establish inversion`,async t=>{
    noSignal(await probe(t,{format,errors:[{message:'expected transfer'}, {message:'unrelated failure',location:linked.location}]}));
  });
  test(`${format}: restored failure must independently link the assertion`,async t=>{
    noSignal(await probe(t,{format,restoredErrors:[{message:'unrelated failure'}]}));
  });
  test(`${format}: line number prefix is not the same failure location`,async t=>{
    noSignal(await probe(t,{format,location:'test.spec.ts:7',errors:[{message:'expected transfer',location:{file:'test.spec.ts',line:70,column:3}}]}));
  });
  test(`${format}: column number prefix is not the same failure location`,async t=>{
    noSignal(await probe(t,{format,errors:[{message:'expected transfer',location:{file:'test.spec.ts',line:25,column:30}}]}));
  });
  test(`${format}: source snippet alone does not establish the failure matcher`,async t=>{
    noSignal(await probe(t,{format,errors:[{message:'unrelated failure',snippet:'expected transfer',location:linked.location}]}));
  });
  test(`${format}: matcher in an ANSI native message code frame is not failure evidence`,async t=>{
    noSignal(await probe(t,{format,errors:[{message:'unrelated failure\n\u001b[31m> 25 | expect(other); expect(transfer); // expected transfer\u001b[39m\n     | ^\n    at test.spec.ts:25:3'}]}));
  });
  test(`${format}: literal filename punctuation is not a regex wildcard`,async t=>{
    noSignal(await probe(t,{format,errors:[{message:'expected transfer',location:{file:'testXspecYts',line:25,column:3}}]}));
  });
  for (const file of ['other/test.spec.ts','/other/test.spec.ts','../test.spec.ts','{project}/other/test.spec.ts','other test.spec.ts','{project}/other test.spec.ts','other/at test.spec.ts','other/(test.spec.ts']) {
    test(`${format}: another file ${file} cannot satisfy a relative location anchor`,async t=>{
      noSignal(await probe(t,{format,errors:[{message:'expected transfer',location:{file,line:25,column:3}}]}));
    });
  }
  for (const file of ['{project}/test.spec.ts','./test.spec.ts']) {
    test(`${format}: matching phase file ${file} preserves linked inversion`,async t=>{
      const r=await probe(t,{format,errors:[{message:'expected transfer',location:{file,line:25,column:3}}]});
      assert.equal(r.behavior_comparison?.classification,'INVERTED_RESPONSE');
      assert.equal(r.verdict,'CANNOT_VERIFY'); assert.equal(r.behavior_proof,false);
    });
  }
  test(`${format}: delimiter-looking path inside a text-only stack cannot establish inversion`,async t=>{
    for (const error of ['expected transfer\n    at Context.run (other/at test.spec.ts:25:3)','expected transfer\nother at test.spec.ts:25:3'])
      noSignal(await probe(t,{format,errors:[error]}));
  });
  test(`${format}: an absolute phase location in a text-only stack preserves inversion`,async t=>{
    const r=await probe(t,{format,errors:['expected transfer\n    at Context.run ({project}/test.spec.ts:25:3)']});
    assert.equal(r.behavior_comparison?.classification,'INVERTED_RESPONSE');
  });
  test(`${format}: a location written in the message cannot outrank a real stack frame in another file`,async t=>{
    noSignal(await probe(t,{format,errors:['AssertionError: expected transfer at test.spec.ts:25:3\n    at Context.run (helpers.ts:3:9)']}));
  });
  for (const frame of ['at async {project}/test.spec.ts:25:3','at file://{project}/test.spec.ts:25:3'])
    test(`${format}: Node frame shape "${frame.split('{')[0]}" preserves inversion`,async t=>{
      const r=await probe(t,{format,errors:['expected transfer\n    '+frame]});
      assert.equal(r.behavior_comparison?.classification,'INVERTED_RESPONSE');
    });
  test(`${format}: genuine matching file with spaces and parentheses preserves inversion`,async t=>{
    const spec='test copy (one).spec.ts';
    const r=await probe(t,{format,spec,location:spec+':25:3',errors:[{message:'expected transfer',location:{file:'{project}/'+spec,line:25,column:3}}]});
    assert.equal(r.behavior_comparison?.classification,'INVERTED_RESPONSE');
  });
}
test('Cypress displayError string establishes the same linked inversion',async t=>{
  const r=await probe(t,{format:'cypress-json',errors:['AssertionError: expected transfer at test.spec.ts:25:3']});assert.equal(r.behavior_comparison?.classification,'INVERTED_RESPONSE');
});
test('Cypress attempts error establishes the same linked inversion',async t=>{
  const r=await probe(t,{format:'cypress-json',errors:[null,linked]});assert.equal(r.behavior_comparison?.classification,'INVERTED_RESPONSE');
});
for(const observerFault of ['exit','provenance','hash'])test(`invalid observer ${observerFault} cannot establish inversion`,async t=>noSignal(await probe(t,{observerFault})));
for(const format of ['playwright-json','cypress-json']) {
  for(const nativeFault of ['missing-report','malformed-report','exit-mismatch','timeout']) {
    test(`${format}: ${nativeFault} cannot establish inversion from an otherwise inverted run`,async t=>{
      const result=await probe(t,{format,nativeFault});noSignal(result);
      assert.equal(typeof result.error,'string');
      if (nativeFault==='missing-report') assert.match(result.error,/native report missing/);
      if (['exit-mismatch','timeout'].includes(nativeFault)) assert.match(result.error,/native exit\/report mismatch/);
    });
  }
  for(const observerFault of ['missing-evidence','contradictory-normal']) {
    test(`${format}: observer ${observerFault} cannot establish inversion`,async t=>noSignal(await probe(t,{format,observerFault})));
  }
}
test('V2 inversion-shaped outcomes cannot establish a V3 diagnostic',async t=>noSignal(await probe(t,{mode:'assertion-mutation'})));

// Captured Cypress 15.19 default-webpack frame shape, independently exercised
// by the local browser canary; authored tests below are not accuracy evidence.
for (const correct of [false,true]) test(`Cypress exact default-webpack frame supports ${correct?'fault detection':'inversion diagnosis'}`,async t=>{
  const r=await probe(t,{format:'cypress-json',correct,errors:['AssertionError: expected transfer\n    at Context.eval (webpack:///./test.spec.ts:25:3)']});
  assert.equal(r.verdict,correct?'DETECTED':'CANNOT_VERIFY');
  if (!correct) assert.equal(r.behavior_comparison?.classification,'INVERTED_RESPONSE');
});
for (const frame of ['webpack:///./other/test.spec.ts:25:3','webpack:///./../test.spec.ts:25:3','webpack://other/./test.spec.ts:25:3','webpack:///./test.spec.ts:250:3','webpack:///./test.spec.ts:25:30','webpack:///./test.spec.ts?other:25:3','webpack:///./%74est.spec.ts:25:3']) test(`Cypress nonmatching webpack frame stays unverified: ${frame}`,async t=>{
  noSignal(await probe(t,{format:'cypress-json',errors:['AssertionError: expected transfer\n    at Context.eval ('+frame+')']}));
});
test('Playwright cannot adopt a Cypress webpack source identity',async t=>{
  noSignal(await probe(t,{errors:['AssertionError: expected transfer\n    at Context.eval (webpack:///./test.spec.ts:25:3)']}));
});
