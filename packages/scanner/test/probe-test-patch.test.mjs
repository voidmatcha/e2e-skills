// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { prepare } from '../scripts/run-probe.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');
const runner = new URL('../scripts/run-probe.mjs', import.meta.url);
const native = `import fs from 'node:fs';
console.log(JSON.stringify({captured_path:process.env.PATH}));
const strong=fs.readFileSync('test.spec.ts','utf8')==='assert saved transfer';
const broken=fs.readFileSync('app.js','utf8').includes("'BROKEN'");
const policy=fs.readFileSync('policy.txt','utf8');
const failed=strong&&(policy==='break-normal'||(broken&&policy!=='survive'));
const status=failed?'failed':'passed';
const message=policy==='unlinked'?'unrelated setup failure':'AssertionError: expected saved transfer but received old at test.spec.ts:25:3';
fs.writeFileSync(process.env.E2E_PROBE_REPORT,JSON.stringify({config:{workers:1},suites:[{specs:[{title:'copies content',file:'test.spec.ts',tests:[{expectedStatus:'passed',results:[{status,retry:0,errors:failed?[{message}]:[]}]}]}]}]}));
if(strong&&policy==='mutate') fs.writeFileSync('app.js','tampered');
process.exitCode=failed?1:0;`;
const app = "function action() { return 'WORKS'; }";
const observer = `import fs from 'node:fs';import vm from 'node:vm';import {createHash} from 'node:crypto';
const {attachReachability}=await import(process.env.E2E_PROBE_RUNNER);
// Synthetic page exercises the executor-injected statement; this is not browser evidence.
const context=vm.createContext({});let binding;
await attachReachability({exposeBinding:async(name,callback)=>{binding=(...args)=>callback({frame:{url:()=> 'synthetic://loop-fixture'}},...args);context[name]=binding;}});
const broken=vm.runInContext(fs.readFileSync('app.js','utf8')+';action()',context)==='BROKEN';
const unexpectedReachability=false;
if(unexpectedReachability) binding(JSON.parse(process.env.E2E_PROBE_REACHABILITY).token,0);
fs.writeFileSync('observed.json',JSON.stringify({actual_content:broken?'old':'transferred'}));
console.log(JSON.stringify({project:process.cwd(),promised_effect:!broken,fault_reached:broken,evidence:[{path:'observed.json',sha256:createHash('sha256').update(fs.readFileSync('observed.json')).digest('hex')}]}));`;

function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'probe-test-patch-')));
  t.after(() => fs.rmSync(root,{recursive:true,force:true}));
  const source=path.join(root,'source'); fs.mkdirSync(source);
  const entries={'app.js':app,'test.spec.ts':'assert transfer','README.md':'copy transfers content','policy.txt':'detect','native.mjs':native,'observer.mjs':observer};
  for(const [name,value] of Object.entries(entries)) fs.writeFileSync(path.join(source,name),value);
  const expected_failure={spec:'test.spec.ts',title:'copies content',locator:{location:'test.spec.ts:25:3'},kind:'assertion',values:{expected:{type:'string',value:'saved transfer'},actual:{type:'string',relation:'different'}}};
  const plan={version:1,source,test_selector:'copies content',test_paths:['test.spec.ts'],mode:'behavior-fault',reachability:{kind:'browser-binding',edit_path:'app.js'},promise:{path:'README.md',quote:entries['README.md'],sha256:sha(entries['README.md'])},edits:[{path:'app.js',before:"return 'WORKS';",after:"return 'BROKEN';",sha256:sha(app),kind:'source'}],test:{argv:[process.execPath,'native.mjs'],timeout_seconds:5,source:{path:'native.mjs',sha256:sha(native)}},observer:{argv:[process.execPath,'observer.mjs'],source:{path:'observer.mjs',sha256:sha(observer)}},report:{format:'playwright-json',path:'native-report.json'},expected_failure};
  const patch={version:1,edits:[{path:'test.spec.ts',before:'assert transfer',after:'assert saved transfer',sha256:sha('assert transfer'),kind:'test'}],expected_failure};
  let count=0;
  function invoke(flags=[],raw=JSON.stringify(patch)) {
    const planPath=path.join(root,'plan.json'),patchPath=path.join(root,'patch.json'),out=path.join(root,`output${++count}`);
    fs.writeFileSync(planPath,JSON.stringify(plan)); fs.writeFileSync(patchPath,raw);
    const processResult=spawnSync(process.execPath,[runner.pathname,'--plan',planPath,'--test-patch',patchPath,'--output-dir',out,...flags],{encoding:'utf8',timeout:20000});
    assert.equal(processResult.error,undefined);
    return {code:processResult.status,out,...JSON.parse(processResult.stdout)};
  }
  function execute() {
    const preview=invoke(); assert.equal(preview.verdict,'PREVIEW',preview.error);
    return invoke(['--execute','--trust-checkout','--approve-sha256',preview.approval_sha256]);
  }
  return {root,source,plan,patch,invoke,execute};
}

test('patch loop proves original survival then detection with the same fault and immutable checkout',t=>{
  const f=fixture(t),result=f.execute();
  assert.equal(result.code,0,result.error); assert.equal(result.verdict,'FIX_VERIFIED');
  assert.equal(result.probe_verdict,'DETECTED'); assert.equal(result.original_probe.verdict,'SURVIVED');
  assert.equal(result.verification.V3.verdict,'PASS'); assert.equal(result.original_source_unchanged,true);
  assert.equal(result.test_patch_sha256,sha(JSON.stringify(f.patch)));
  for(const phase of ['normal','fault','restored']) {
    const original=path.join(result.out,'original',phase,'project'),patched=path.join(result.out,phase,'project');
    assert.equal(fs.readFileSync(path.join(original,'test.spec.ts'),'utf8'),'assert transfer');
    assert.equal(fs.readFileSync(path.join(patched,'test.spec.ts'),'utf8'),'assert saved transfer');
    for(const project of [original,patched]) {
      const code=fs.readFileSync(path.join(project,'app.js'),'utf8');
      if(phase==='fault') { assert.match(code,/globalThis\[/); assert.match(code,/return 'BROKEN';/); }
      else assert.equal(code,app);
      assert.equal(fs.readFileSync(path.join(project,'README.md'),'utf8'),'copy transfers content');
    }
  }
  const diff=fs.readFileSync(path.join(result.out,'proposed-test-fix.diff'),'utf8');
  assert.match(diff,/test\.spec\.ts/); assert.match(diff,/-assert transfer/); assert.match(diff,/\+assert saved transfer/);
  const applyCopy=path.join(f.root,'apply-copy'); fs.cpSync(f.source,applyCopy,{recursive:true});
  for(const args of [['apply','--check'],['apply']]) {
    const applied=spawnSync('git',[...args,path.join(result.out,'proposed-test-fix.diff')],{cwd:applyCopy,encoding:'utf8'});
    assert.equal(applied.status,0,applied.stderr);
  }
  assert.equal(fs.readFileSync(path.join(applyCopy,'test.spec.ts'),'utf8'),'assert saved transfer','offered diff preserves absent final newline');
  assert.equal(fs.readFileSync(path.join(applyCopy,'app.js'),'utf8'),app);
  assert.equal(fs.readFileSync(path.join(f.source,'test.spec.ts'),'utf8'),'assert transfer');
  assert.equal(fs.readFileSync(path.join(f.source,'app.js'),'utf8'),app);
});

test('raw patch bytes are previewed and bound into approval, including formatting',t=>{
  const f=fixture(t),raw=JSON.stringify(f.patch),preview=f.invoke([],raw);
  assert.equal(preview.verdict,'PREVIEW',preview.error); assert.equal(preview.test_patch_sha256,sha(raw));
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(preview.out,'preview.json'),'utf8')).test_patch,f.patch);
  const changedRaw=JSON.stringify(f.patch,null,2),changed=f.invoke([],changedRaw);
  assert.equal(changed.test_patch_sha256,sha(changedRaw)); assert.notEqual(changed.approval_sha256,preview.approval_sha256);
  const stale=f.invoke(['--execute','--trust-checkout','--approve-sha256',preview.approval_sha256],changedRaw);
  assert.equal(stale.code,2); assert.equal(stale.verdict,'ERROR');
  assert.equal(fs.existsSync(path.join(stale.out,'normal')),false);
});

test('approved preview replays the raw test patch and pinned environment and refuses tampering',t=>{
  const f=fixture(t),planPath=path.join(f.root,'replay-plan.json'),patchPath=path.join(f.root,'replay-patch.json');
  const raw=JSON.stringify(f.patch,null,2)+'\n',previewDir=path.join(f.root,'replay-preview');
  fs.writeFileSync(planPath,JSON.stringify(f.plan));fs.writeFileSync(patchPath,raw);
  function call(args,output,searchPath) {
    const run=spawnSync(process.execPath,[runner.pathname,...args,'--output-dir',output],{encoding:'utf8',env:{...process.env,PATH:searchPath},timeout:20000});
    assert.equal(run.error,undefined);assert.ok(run.stdout.trim(),run.stderr);
    return {code:run.status,...JSON.parse(run.stdout)};
  }
  const preview=call(['--plan',planPath,'--test-patch',patchPath],previewDir,'/approved/loop-path');
  assert.equal(preview.verdict,'PREVIEW',preview.error);
  const saved=path.join(previewDir,'preview.json'),receipt=JSON.parse(fs.readFileSync(saved,'utf8'));
  assert.equal(receipt.test_patch_text,raw);assert.equal(receipt.test_patch_sha256,sha(raw));
  fs.unlinkSync(planPath);fs.unlinkSync(patchPath);
  const executeFlags=['--execute','--trust-checkout','--approve-sha256',preview.approval_sha256];
  const output=path.join(f.root,'replayed-loop');
  const replay=call(['--approved-preview',saved,...executeFlags],output,'/later/loop-path');
  assert.equal(replay.code,0,replay.error);assert.equal(replay.verdict,'FIX_VERIFIED');
  assert.equal(replay.original_probe.verdict,'SURVIVED');assert.equal(replay.probe_verdict,'DETECTED');
  assert.equal(fs.readFileSync(path.join(output,'test-patch.json'),'utf8'),raw);
  for(const runRoot of [output,path.join(output,'original')]) {
    for(const phase of ['normal','fault','restored']) {
      const stdout=fs.readFileSync(path.join(runRoot,phase,'test','stdout.txt'),'utf8');
      assert.equal(JSON.parse(stdout).captured_path,'/approved/loop-path');
    }
  }
  for(const [name,alter] of [
    ['patch',r=>{r.test_patch_text+=' ';}],
    ['environment',r=>{r.effective_environment.PATH='/tampered/loop-path';}],
  ]) {
    const tampered=structuredClone(receipt);alter(tampered);
    const filename=path.join(f.root,`tampered-${name}.json`),out=path.join(f.root,`refused-${name}`);
    fs.writeFileSync(filename,JSON.stringify(tampered));
    const refused=call(['--approved-preview',filename,...executeFlags],out,'/later/loop-path');
    assert.equal(refused.code,2);assert.equal(refused.verdict,'ERROR');
    assert.match(refused.error,/stale or missing approval digest/);
    assert.equal(fs.existsSync(path.join(out,'normal')),false);
    assert.equal(fs.existsSync(path.join(out,'original')),false);
  }
});

for(const [policy,wanted,probe,verification] of [
  ['survive','FIX_NOT_DETECTING','SURVIVED','FAIL'],
  ['break-normal','FIX_BREAKS_NORMAL','CANNOT_VERIFY','CANNOT_VERIFY'],
  ['unlinked','CANNOT_VERIFY','CANNOT_VERIFY','CANNOT_VERIFY'],
  ['mutate','CANNOT_VERIFY','CANNOT_VERIFY','CANNOT_VERIFY'],
]) test(`patch loop reports ${policy} without claiming a verified fix`,t=>{
  const f=fixture(t); fs.writeFileSync(path.join(f.source,'policy.txt'),policy);
  const result=f.execute(); assert.equal(result.code,2,result.error); assert.equal(result.verdict,wanted,result.error);
  assert.equal(result.original_probe.verdict,'SURVIVED'); assert.equal(result.probe_verdict,probe);
  assert.equal(result.verification.V3.verdict,verification); assert.equal(result.original_source_unchanged,true);
  assert.equal(fs.readFileSync(path.join(f.source,'test.spec.ts'),'utf8'),'assert transfer');
});

test('patch validation rejects malformed, ambiguous, undeclared and source edits',t=>{
  const f=fixture(t),edit=f.patch.edits[0],invalid=[
    {...f.patch,unexpected:true}, {...f.patch,version:true}, {...f.patch,edits:[]},
    {...f.patch,edits:[edit,edit]}, {...f.patch,edits:[{...edit,after:edit.before}]},
    {...f.patch,edits:[{...edit,sha256:sha('stale')}]},
    {...f.patch,edits:[{...edit,before:'not present'}]},
    {...f.patch,edits:[{...edit,path:'../test.spec.ts'}]},
    {...f.patch,edits:[{...edit,path:'app.js',before:app,after:'BROKEN',sha256:sha(app),kind:'source'}]},
    {...f.patch,expected_failure:{contains:'',location:'test.spec.ts:25:3'}},
  ];
  for(const patch of invalid) assert.throws(()=>prepare(f.plan,JSON.stringify(patch)),JSON.stringify(patch));
  assert.throws(()=>prepare(f.plan,'not json'));
  fs.writeFileSync(path.join(f.source,'test.spec.ts'),'assert transfer; assert transfer');
  f.patch.edits[0].sha256=sha('assert transfer; assert transfer');
  assert.throws(()=>prepare(f.plan,JSON.stringify(f.patch)));
});

for(const name of ['native.mjs','observer.mjs','README.md']) test(`patch cannot change pinned ${name} even if declared a test`,t=>{
  const f=fixture(t),before=fs.readFileSync(path.join(f.source,name),'utf8');
  f.plan.test_paths.push(name);
  f.patch.edits=[{path:name,before,after:before+'\n',sha256:sha(before),kind:'test'}];
  assert.throws(()=>prepare(f.plan,JSON.stringify(f.patch)));
});

test('test patch is rejected in assertion-mutation mode',t=>{
  const f=fixture(t); f.plan.mode='assertion-mutation'; delete f.plan.observer;
  f.plan.edits=[{...f.patch.edits[0],after:'assert impossible'}];
  assert.throws(()=>prepare(f.plan,JSON.stringify(f.patch)));
});

test('original detection cannot be relabeled as a verified repair',t=>{
  const f=fixture(t); fs.writeFileSync(path.join(f.source,'test.spec.ts'),'assert saved transfer');
  f.patch.edits=[{path:'test.spec.ts',before:'assert saved transfer',after:'assert transfer',sha256:sha('assert saved transfer'),kind:'test'}];
  const result=f.execute(); assert.equal(result.code,2); assert.equal(result.original_probe.verdict,'DETECTED');
  assert.notEqual(result.verdict,'FIX_VERIFIED'); assert.notEqual(result.verification.V3.verdict,'PASS');
  assert.equal(fs.existsSync(path.join(result.out,'normal')),false,'must stop before running the proposed patch');
});

for(const phase of ['normal','restored']) {
  for(const patchedOnly of [false,true]) test(`contradictory ${phase} observation in ${patchedOnly?'patched':'original'} run cannot verify a fix`,t=>{
    const f=fixture(t),condition=patchedOnly?"fs.readFileSync('test.spec.ts','utf8')==='assert saved transfer'":'true';
    const changed=observer.replace('const unexpectedReachability=false;',`const unexpectedReachability=process.env.E2E_PROBE_PHASE==='${phase}'&&(${condition});`);
    fs.writeFileSync(path.join(f.source,'observer.mjs'),changed); f.plan.observer.source.sha256=sha(changed);
    const result=f.execute();
    assert.equal(result.code,2); assert.equal(result.verdict,'CANNOT_VERIFY');
    assert.equal(result.verification.V3.verdict,'CANNOT_VERIFY');
    assert.equal(result.original_source_unchanged,true);
    const evidence=patchedOnly?result:result.original_probe;
    assert.match(evidence.error,/runtime marker unexpectedly executed outside the fault phase/);
    const hits=fs.readFileSync(path.join(result.out,...(patchedOnly?[]:['original']),phase,'reachability.jsonl'),'utf8').trim().split('\n');
    assert.equal(hits.length,1,'contradictory runtime hit is retained as evidence');
    if(!patchedOnly) assert.equal(fs.existsSync(path.join(result.out,'normal')),false,'contradictory original evidence must gate patched execution');
    else assert.equal(result.original_probe.verdict,'SURVIVED');
  });
}

test('test patch failure location must select an exact declared test and positive integer coordinates',t=>{
  const f=fixture(t);
  for(const location of [
    'other.spec.ts:25:3','../test.spec.ts:25:3','/test.spec.ts:25:3',
    'test.spec.ts','test.spec.ts:0:3','test.spec.ts:25:0','test.spec.ts:-1:3',
    'test.spec.ts:2.5:3','test.spec.ts:25:3:4','test.spec.ts:25:3 trailing',
    'test.spec.ts:1e2:3','test.spec.ts:25:NaN',
  ]) {
    const patch={...f.patch,expected_failure:{...f.patch.expected_failure,locator:{location}}};
    assert.throws(()=>prepare(f.plan,JSON.stringify(patch)),`must reject ${location}`);
  }
});

for(const name of ['app.js','test.spec.ts']) test(`patched native command changing ${name} mode invalidates evidence`,t=>{
  const f=fixture(t),filename=path.join(f.source,name),beforeMode=fs.statSync(filename).mode&0o7777;
  const changed=native+`\nif(strong) fs.chmodSync(${JSON.stringify(name)},0o700);\n`;
  fs.writeFileSync(path.join(f.source,'native.mjs'),changed); f.plan.test.source.sha256=sha(changed);
  const result=f.execute();
  assert.equal(result.code,2); assert.equal(result.verdict,'CANNOT_VERIFY');
  assert.equal(result.original_probe.verdict,'SURVIVED');
  assert.equal(result.probe_verdict,'CANNOT_VERIFY');
  assert.equal(result.verification.V3.verdict,'CANNOT_VERIFY');
  assert.match(result.error,/phase source mode changed/);
  assert.equal(result.original_source_unchanged,true);
  assert.equal(fs.statSync(filename).mode&0o7777,beforeMode);
});
