// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { prepare, parseNative, runCommand } from '../scripts/run-probe.mjs';
const sha = value => createHash('sha256').update(value).digest('hex');
const cli = new URL('../src/check-cli.mjs', import.meta.url);
const native = `import fs from 'node:fs';
const broken=fs.readFileSync('app.txt','utf8')==='BROKEN'||fs.readFileSync('test.spec.ts','utf8')==='assert impossible';
const failed=broken&&fs.readFileSync('policy.txt','utf8')==='detected';
const status=failed?'failed':'passed';
fs.writeFileSync(process.env.E2E_PROBE_REPORT,JSON.stringify({config:{workers:1},suites:[{specs:[{title:'copies content',file:'test.spec.ts',tests:[{expectedStatus:'passed',results:[{status,retry:0,errors:failed?[{message:'expected transfer at test.spec.ts:25:3'}]:[]}]}]}]}]}));
process.exitCode=failed?1:0;`;
const observer = `import fs from 'node:fs';import {createHash} from 'node:crypto';
const broken=fs.readFileSync('app.txt','utf8')==='BROKEN';fs.writeFileSync('observed.json',JSON.stringify({actual_content:broken?'old':'transferred'}));
console.log(JSON.stringify({project:process.cwd(),promised_effect:!broken,fault_reached:broken,evidence:[{path:'observed.json',sha256:createHash('sha256').update(fs.readFileSync('observed.json')).digest('hex')}]}));`;
function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'node-probe-'))); t.after(() => fs.rmSync(root,{recursive:true,force:true})); const source=path.join(root,'source');fs.mkdirSync(source);
  const entries = {'app.txt':'WORKS','test.spec.ts':'assert transfer','README.md':'copy transfers content','policy.txt':'detected','native.mjs':native,'observer.mjs':observer};
  for(const [name,value] of Object.entries(entries)) fs.writeFileSync(path.join(source,name),value);
  const plan={version:1,source,test_selector:'copies content',test_paths:['test.spec.ts'],mode:'behavior-fault',promise:{path:'README.md',quote:entries['README.md'],sha256:sha(entries['README.md'])},edits:[{path:'app.txt',before:'WORKS',after:'BROKEN',sha256:sha('WORKS'),kind:'source'}],test:{argv:[process.execPath,'native.mjs'],timeout_seconds:5,source:{path:'native.mjs',sha256:sha(native)}},observer:{argv:[process.execPath,'observer.mjs'],source:{path:'observer.mjs',sha256:sha(observer)}},report:{format:'playwright-json',path:'native-report.json'},expected_failure:{contains:'expected transfer',location:'test.spec.ts:25:3'}};
  let count=0;
  function invoke(flags=[]) { const planPath=path.join(root,'plan.json');fs.writeFileSync(planPath,JSON.stringify(plan)); const result=spawnSync(process.execPath,[cli.pathname,'probe','--plan',planPath,'--output-dir',path.join(root,`output${++count}`),...flags],{encoding:'utf8',env:{...process.env,PATH:'/no-python-or-other-executables'},timeout:15000}); assert.equal(result.error,undefined); return {code:result.status,...JSON.parse(result.stdout)}; }
  function execute() { const preview=invoke();assert.equal(preview.verdict,'PREVIEW');return invoke(['--execute','--trust-checkout','--approve-sha256',preview.approval_sha256]); }
  return {root,source,plan,invoke,execute};
}
test('Node-only npm CLI executes normal/fault/restored with PATH containing no Python',t=>{
  const f=fixture(t), result=f.execute();assert.equal(result.code,0);assert.equal(result.verdict,'DETECTED');assert.equal(result.verification.V3.verdict,'PASS');assert.equal(result.original_source_unchanged,true);assert.deepEqual(Object.keys(result.phases),['normal','fault','restored']);assert.equal(fs.readFileSync(path.join(f.source,'app.txt'),'utf8'),'WORKS');
});
test('Node-only CLI separates assertion sensitivity from behavior proof',t=>{
  const f=fixture(t);f.plan.mode='assertion-mutation';delete f.plan.observer;f.plan.edits=[{path:'test.spec.ts',before:'assert transfer',after:'assert impossible',sha256:sha('assert transfer'),kind:'test'}];const result=f.execute();assert.equal(result.verdict,'ASSERTION_SENSITIVE');assert.equal(result.verification.V2.verdict,'PASS');assert.equal(result.verification.V3.verdict,'CANNOT_VERIFY');assert.equal(result.behavior_proof,false);
});
test('Node-only probe reports survived behavior fault without claiming detection',t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.source,'policy.txt'),'survived');const result=f.execute();assert.equal(result.verdict,'SURVIVED');assert.equal(result.verification.V3.verdict,'FAIL');assert.equal(result.original_source_unchanged,true);
});
test('strict manifest, stale approval, excluded paths and symlinks fail closed',t=>{
  const f=fixture(t);const preview=f.invoke();fs.writeFileSync(path.join(f.source,'policy.txt'),'changed');assert.equal(f.invoke(['--execute','--trust-checkout','--approve-sha256',preview.approval_sha256]).verdict,'ERROR');
  for (const bad of [{...f.plan,unexpected:true},{...f.plan,version:true},{...f.plan,test_paths:'test.spec.ts'},{...f.plan,test:{...f.plan.test,timeout_seconds:true}},{...f.plan,edits:[{...f.plan.edits[0],path:'../app.txt'}]},{...f.plan,report:{format:'playwright-json',path:'node_modules/report.json'}}]) assert.throws(()=>prepare(bad));
  fs.symlinkSync(path.join(f.source,'app.txt'),path.join(f.source,'linked'));assert.throws(()=>prepare(f.plan),/symlink/);
});
test('native JSON rejects retry, skip, unlinked error and root escapes',t=>{
  const f=fixture(t),r={config:{workers:1},suites:[{specs:[{title:'copies content',file:'test.spec.ts',tests:[{expectedStatus:'passed',results:[{status:'passed',retry:0,errors:[]}]}]}]}]};const parse=v=>parseNative(v,'playwright-json','copies content',['test.spec.ts'],f.source);assert.equal(parse(r)[0],'passed');
  for(const modify of [r=>r.config.workers=2,r=>r.config.rootDir=f.root,r=>r.suites[0].specs[0].file='../test.spec.ts',r=>r.suites[0].specs[0].tests[0].results[0].status='skipped',r=>r.suites[0].specs[0].tests[0].results[0].retry=1,r=>r.suites[0].specs[0].tests[0].results[0].errors=[{message:'error on pass'}]]) {const copy=structuredClone(r);modify(copy);assert.throws(()=>parse(copy));}
});
test('timeout kills owned Node child process group and preserves receipt',async t=>{
  if(process.platform==='win32')return t.skip('POSIX process groups');const f=fixture(t),out=path.join(f.root,'command');fs.mkdirSync(out);const pidPath=path.join(f.root,'child.pid');
  const script=`import fs from 'node:fs';import {spawn} from 'node:child_process';const child=spawn(process.execPath,['-e','setTimeout(()=>{},30000)']);fs.writeFileSync(${JSON.stringify(pidPath)},String(child.pid));setTimeout(()=>{},30000);`;
  const receipt=await runCommand({argv:[process.execPath,'--input-type=module','-e',script],timeout_seconds:1,_selector:'copies content'},f.source,'fault',path.join(f.root,'unused.json'),out);assert.equal(receipt.timeout,true);assert.equal(receipt.exit_code,null);assert.equal(receipt.owned_process_group_cleanup,true);const pid=Number(fs.readFileSync(pidPath,'utf8'));await new Promise(resolve=>setTimeout(resolve,100));
  let alive=false;try{process.kill(pid,0);alive=true;}catch(e){assert.equal(e.code,'ESRCH');}if(alive&&process.platform==='linux'){const stat=fs.readFileSync(`/proc/${pid}/stat`,'utf8');alive=!['Z','X'].includes(stat.slice(stat.lastIndexOf(')')+1).trim().split(/\s/)[0]);}assert.equal(alive,false,'owned child must not remain executing');assert.deepEqual(JSON.parse(fs.readFileSync(path.join(out,'command.json'))),receipt);
});
test('snapshot pins special object-key filenames and preserves source file modes',t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.source,'__proto__'),'pinned');fs.writeFileSync(path.join(f.source,'constructor'),'also pinned');fs.chmodSync(path.join(f.source,'app.txt'),0o640);const prepared=prepare(f.plan);assert.equal(Object.hasOwn(prepared.files,'__proto__'),true);assert.equal(prepared.files.__proto__.sha256,sha('pinned'));assert.equal(prepared.files.constructor.sha256,sha('also pinned'));const result=f.execute();assert.equal(result.verdict,'DETECTED');for(const phase of ['normal','fault','restored'])assert.equal(fs.statSync(path.join(result.temporaryArtifactsRemaining,phase,'project/app.txt')).mode&0o777,0o640);assert.equal(fs.statSync(path.join(f.source,'app.txt')).mode&0o777,0o640);
});
test('excluded directory names do not silently omit regular files or included symlink files',t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.source,'reports'),'source file');assert.equal(Object.hasOwn(prepare(f.plan).files,'reports'),true);fs.unlinkSync(path.join(f.source,'reports'));fs.symlinkSync(path.join(f.source,'app.txt'),path.join(f.source,'reports'));assert.throws(()=>prepare(f.plan),/symlink/);
});
test('invalid UTF-8 promise source is rejected rather than decoded with replacement',t=>{
  const f=fixture(t);const data=Buffer.from([0xff]);fs.writeFileSync(path.join(f.source,'README.md'),data);f.plan.promise.sha256=sha(data);f.plan.promise.quote='\uFFFD';assert.throws(()=>prepare(f.plan));
});
test('native wrapper changing copied source mode cannot establish detection',t=>{
  const f=fixture(t);const altered=native+"\nfs.chmodSync('app.txt',0o700);\n";fs.writeFileSync(path.join(f.source,'native.mjs'),altered);f.plan.test.source.sha256=sha(altered);const before=fs.statSync(path.join(f.source,'app.txt')).mode&0o7777;const result=f.execute();assert.equal(result.verdict,'CANNOT_VERIFY');assert.match(result.error,/phase source mode changed/);assert.equal(result.original_source_unchanged,true);assert.equal(fs.statSync(path.join(f.source,'app.txt')).mode&0o7777,before);
});
test('command placeholders preserve dollar sequences literally in paths and selector',async t=>{
  const f=fixture(t),project=path.join(f.root,"project $& $$ $` $'"),out=path.join(f.root,'literal-command');fs.renameSync(f.source,project);fs.mkdirSync(out);const selector="title $& $$ $` $'",report=path.join(project,"report $& $$ $` $'.json");const receipt=await runCommand({argv:[process.execPath,'-e','console.log(JSON.stringify(process.argv.slice(1)))','{project}','{report}','{selector}'],_selector:selector,timeout_seconds:5},project,'normal',report,out);assert.equal(receipt.exit_code,0);assert.deepEqual(JSON.parse(fs.readFileSync(path.join(out,'stdout.txt'),'utf8')),[project,report,selector]);assert.deepEqual(receipt.argv.slice(3),[project,report,selector]);
});

test('check help describes the shipped Node runner without a Python requirement',()=>{
  const result=spawnSync(process.execPath,[cli.pathname,'--help'],{encoding:'utf8'});assert.equal(result.status,0);assert.match(result.stdout,/bundled Node\.js runner/);assert.doesNotMatch(result.stdout,/Python|--python/);
});
test('manual symlink-directory install runs preview/execution and rejects bad CLI arguments',t=>{
  const f=fixture(t),runner=new URL('../scripts/run-probe.mjs',cli),linked=path.join(f.root,'linked skill');fs.symlinkSync(path.dirname(path.dirname(fs.realpathSync(runner))),linked,'dir');const filename=path.join(linked,'scripts/run-probe.mjs'),planPath=path.join(f.root,'symlink-plan.json');fs.writeFileSync(planPath,JSON.stringify(f.plan));
  const previewDir=path.join(f.root,'symlink-preview'),preview=spawnSync(process.execPath,[filename,'--plan',planPath,'--output-dir',previewDir],{encoding:'utf8'});assert.equal(preview.status,0,preview.stderr);const evidence=JSON.parse(preview.stdout);assert.equal(evidence.verdict,'PREVIEW');assert.equal(JSON.parse(fs.readFileSync(path.join(previewDir,'result.json'),'utf8')).verdict,'PREVIEW');
  const runDir=path.join(f.root,'symlink-run'),result=spawnSync(process.execPath,[filename,'--plan',planPath,'--output-dir',runDir,'--execute','--trust-checkout','--approve-sha256',evidence.approval_sha256],{encoding:'utf8'});assert.equal(result.status,0,result.stderr);assert.equal(JSON.parse(result.stdout).verdict,'DETECTED');assert.equal(JSON.parse(fs.readFileSync(path.join(runDir,'result.json'),'utf8')).original_source_unchanged,true);
  const bad=spawnSync(process.execPath,[filename,'--unknown'],{encoding:'utf8'});assert.equal(bad.status,2);assert.equal(JSON.parse(bad.stdout).verdict,'ERROR');
});
test('module import with a nonexistent unrelated entry path executes no CLI',t=>{
  const f=fixture(t),runner=new URL('../scripts/run-probe.mjs',cli);const code=`await import(${JSON.stringify(runner.href)});console.log('imported');`;const result=spawnSync(process.execPath,['--input-type=module','-e',code,path.join(f.root,'nonexistent-entry')],{encoding:'utf8'});assert.equal(result.status,0,result.stderr);assert.equal(result.stdout,'imported\n');
});
test('output directory collision after freshness check is rejected without adopting artifacts',t=>{
  const f=fixture(t),runner=new URL('../scripts/run-probe.mjs',cli),out=path.join(f.root,'parent','collided'),planPath=path.join(f.root,'collision-plan.json');fs.writeFileSync(planPath,JSON.stringify(f.plan));
  const code=`import fs from 'node:fs';import path from 'node:path';import {main} from ${JSON.stringify(runner.href)};const output=${JSON.stringify(out)},mkdir=fs.mkdirSync;let injected=false;fs.mkdirSync=(dir,options)=>{if(dir===path.dirname(output)&&options?.recursive&&!injected){injected=true;mkdir(dir,options);mkdir(output);fs.writeFileSync(path.join(output,'sentinel.txt'),'another creator owns this');return;}return mkdir(dir,options);};process.exitCode=await main(['--plan',${JSON.stringify(planPath)},'--output-dir',output]);`;
  const result=spawnSync(process.execPath,['--input-type=module','-e',code],{encoding:'utf8'});assert.equal(result.status,2,result.stderr);const parsed=JSON.parse(result.stdout);assert.equal(parsed.verdict,'ERROR');assert.match(parsed.error,/EEXIST/);assert.equal(fs.readFileSync(path.join(out,'sentinel.txt'),'utf8'),'another creator owns this');assert.deepEqual(fs.readdirSync(out),['sentinel.txt']);
});
