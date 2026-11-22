// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { prepare, execute, parseNative, runCommand } from '../scripts/run-probe.mjs';
const sha = value => createHash('sha256').update(value).digest('hex');
const cli = new URL('../src/check-cli.mjs', import.meta.url);
const native = `import fs from 'node:fs';
const broken=fs.readFileSync('app.js','utf8').includes('BROKEN')||fs.readFileSync('test.spec.ts','utf8')==='assert impossible';
const failed=broken&&fs.readFileSync('policy.txt','utf8')==='detected';
const status=failed?'failed':'passed';
fs.writeFileSync(process.env.E2E_PROBE_REPORT,JSON.stringify({config:{workers:1},suites:[{specs:[{title:'copies content',file:'test.spec.ts',tests:[{expectedStatus:'passed',results:[{status,retry:0,errors:failed?[{message:'AssertionError: expected transfer but received old at test.spec.ts:25:3'}]:[]}]}]}]}]}));
process.exitCode=failed?1:0;`;
const observer = `import fs from 'node:fs';import {createHash} from 'node:crypto';
const broken=fs.readFileSync('app.js','utf8').includes('BROKEN');fs.writeFileSync('observed.json',JSON.stringify({actual_content:broken?'old':'transferred'}));
// Synthetic runtime receipt; not browser execution evidence.
const reachability=JSON.parse(process.env.E2E_PROBE_REACHABILITY??'null');
if(broken&&reachability) fs.appendFileSync(reachability.artifact,JSON.stringify({token:reachability.token,path:reachability.path,edit_index:0,phase:reachability.phase,project:reachability.project,url:'synthetic://fixture'})+'\\n');
console.log(JSON.stringify({project:process.cwd(),promised_effect:!broken,fault_reached:broken,evidence:[{path:'observed.json',sha256:createHash('sha256').update(fs.readFileSync('observed.json')).digest('hex')}]}));`;
function fixture(t) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'node-probe-'))); t.after(() => fs.rmSync(root,{recursive:true,force:true})); const source=path.join(root,'source');fs.mkdirSync(source);
  const entries = {'app.js':'function action() { WORKS; }','test.spec.ts':'assert transfer','README.md':'copy transfers content','policy.txt':'detected','native.mjs':native,'observer.mjs':observer};
  for(const [name,value] of Object.entries(entries)) fs.writeFileSync(path.join(source,name),value);
  const plan={version:1,source,test_selector:'copies content',test_paths:['test.spec.ts'],mode:'behavior-fault',reachability:{kind:'browser-binding',edit_path:'app.js'},promise:{path:'README.md',quote:entries['README.md'],sha256:sha(entries['README.md'])},edits:[{path:'app.js',before:'WORKS;',after:'BROKEN;',sha256:sha('function action() { WORKS; }'),kind:'source'}],test:{argv:[process.execPath,'native.mjs'],timeout_seconds:5,source:{path:'native.mjs',sha256:sha(native)}},observer:{argv:[process.execPath,'observer.mjs'],source:{path:'observer.mjs',sha256:sha(observer)}},report:{format:'playwright-json',path:'native-report.json'},expected_failure:{spec:'test.spec.ts',title:'copies content',locator:{location:'test.spec.ts:25:3'},kind:'assertion',values:{expected:{type:'string',value:'transfer'},actual:{type:'string',relation:'different'}}}};
  let count=0;
  function invoke(flags=[]) { const planPath=path.join(root,'plan.json');fs.writeFileSync(planPath,JSON.stringify(plan)); const result=spawnSync(process.execPath,[cli.pathname,'probe','--plan',planPath,'--output-dir',path.join(root,`output${++count}`),...flags],{encoding:'utf8',env:{...process.env,PATH:'/no-python-or-other-executables'},timeout:15000}); assert.equal(result.error,undefined);assert.ok(result.stdout.trim(),result.stderr); return {code:result.status,...JSON.parse(result.stdout)}; }
  function execute() { const preview=invoke();assert.equal(preview.verdict,'PREVIEW');return invoke(['--execute','--trust-checkout','--approve-sha256',preview.approval_sha256]); }
  return {root,source,plan,invoke,execute};
}
test('Node-only npm CLI executes normal/fault/restored with PATH containing no Python',t=>{
  const f=fixture(t), result=f.execute();assert.equal(result.code,0);assert.equal(result.verdict,'DETECTED');assert.equal(result.verification.V3.verdict,'PASS');assert.equal(result.original_source_unchanged,true);assert.deepEqual(Object.keys(result.phases),['normal','fault','restored']);assert.equal(fs.readFileSync(path.join(f.source,'app.js'),'utf8'),'function action() { WORKS; }');
});
test('Node-only CLI separates assertion sensitivity from behavior proof',t=>{
  const f=fixture(t);f.plan.mode='assertion-mutation';delete f.plan.observer;delete f.plan.reachability;f.plan.edits=[{path:'test.spec.ts',before:'assert transfer',after:'assert impossible',sha256:sha('assert transfer'),kind:'test'}];const result=f.execute();assert.equal(result.verdict,'ASSERTION_SENSITIVE');assert.equal(result.verification.V2.verdict,'PASS');assert.equal(result.verification.V3.verdict,'CANNOT_VERIFY');assert.equal(result.behavior_proof,false);
});
test('Node-only probe reports survived behavior fault without claiming detection',t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.source,'policy.txt'),'survived');const result=f.execute();assert.equal(result.verdict,'SURVIVED');assert.equal(result.verification.V3.verdict,'FAIL');assert.equal(result.original_source_unchanged,true);
});
const cypressSource = 'cypress/tests/ui/new-transaction.spec.ts';
for (const [name,frame,expected,manifestName='cypress-realworld-app'] of [
  ['named project source',`webpack://cypress-realworld-app/./${cypressSource}:183:30`,'DETECTED'],
  ['wrong project namespace',`webpack://other/./${cypressSource}:183:30`,'CANNOT_VERIFY'],
  ['missing pinned manifest',`webpack://cypress-realworld-app/./${cypressSource}:183:30`,'CANNOT_VERIFY',null],
  ['different pinned manifest',`webpack://cypress-realworld-app/./${cypressSource}:183:30`,'CANNOT_VERIFY','another-app'],
  ['empty project namespace',`webpack:///./${cypressSource}:183:30`,'DETECTED'],
  ['unrelated source','webpack://cypress-realworld-app/./other/new-transaction.spec.ts:183:30','CANNOT_VERIFY'],
  ['wrong line',`webpack://cypress-realworld-app/./${cypressSource}:184:30`,'CANNOT_VERIFY'],
  ['wrong column',`webpack://cypress-realworld-app/./${cypressSource}:183:31`,'CANNOT_VERIFY'],
  ['traversal alias',`webpack://cypress-realworld-app/./elsewhere/../${cypressSource}:183:30`,'CANNOT_VERIFY'],
  ['escaped traversal',`webpack://cypress-realworld-app/./%2e%2e/${cypressSource}:183:30`,'CANNOT_VERIFY'],
  ['runtime frame','webpack://cypress-realworld-app/./__cypress/runner/cypress_runner.js:183:30','CANNOT_VERIFY'],
]) {
  test(`Cypress webpack location accepts only exact selected coordinates: ${name}`,async t=>{
    const f=fixture(t);fs.mkdirSync(path.dirname(path.join(f.source,cypressSource)),{recursive:true});fs.renameSync(path.join(f.source,'test.spec.ts'),path.join(f.source,cypressSource));
    if (manifestName !== null) fs.writeFileSync(path.join(f.source,'package.json'),JSON.stringify({name:manifestName}));
    f.plan.test_paths=[cypressSource];f.plan.report.format='cypress-json';f.plan.expected_failure={spec:cypressSource,title:'copies content',locator:{location:`${cypressSource}:183:30`},kind:'assertion',values:{expected:{type:'string',value:'$1,459.53'},actual:{type:'string',relation:'exact',value:'$1,484.53'}}};
    const failure=`AssertionError: expected '$1,459.53' but received '$1,484.53'\n    at Context.eval (${frame})`;
    const script=`import fs from 'node:fs';const failed=fs.readFileSync('app.js','utf8').includes('BROKEN');const state=failed?'failed':'passed';const error=failed?${JSON.stringify(failure)}:undefined;fs.writeFileSync(process.env.E2E_PROBE_REPORT,JSON.stringify({totalTests:1,totalPending:0,totalSkipped:0,totalPassed:Number(!failed),totalFailed:Number(failed),runs:[{spec:{relative:${JSON.stringify(cypressSource)}},tests:[{title:['copies content'],state,displayError:error,attempts:[{state,error}]}]}]}));process.exitCode=failed?1:0;`;
    fs.writeFileSync(path.join(f.source,'native.mjs'),script);f.plan.test.source.sha256=sha(script);const result=await execute(f.plan,prepare(f.plan),path.join(f.root,'output'));assert.equal(result.verdict,expected);assert.deepEqual(Object.keys(result.phases),['normal','fault','restored']);if(expected==='CANNOT_VERIFY')assert.match(result.error,/expected_failure.locator mismatched/);
  });
}
function invertedFixture(t, {unlinked=false, restoredPass=false, noFault=false, mutate=false} = {}) {
  const f=fixture(t);
  let script=native.replace("const failed=broken&&fs.readFileSync('policy.txt','utf8')==='detected';",
    `const failed=!broken${restoredPass ? "&&process.env.E2E_PROBE_PHASE!=='restored'" : ''};`);
  if(unlinked) script=script.replace('AssertionError: expected transfer but received old at test.spec.ts:25:3','unrelated setup failure');
  if(mutate) script+="\nfs.writeFileSync('app.js','changed');\n";
  fs.writeFileSync(path.join(f.source,'native.mjs'),script);f.plan.test.source.sha256=sha(script);
  if(noFault) {const text=observer.replace('if(broken&&reachability)', 'if(false&&reachability)');fs.writeFileSync(path.join(f.source,'observer.mjs'),text);f.plan.observer.source.sha256=sha(text);}
  return f;
}
test('inverted assertion response is review evidence, never a successful V3 probe',t=>{
  const result=invertedFixture(t).execute();
  assert.equal(result.verdict,'CANNOT_VERIFY');assert.equal(result.code,2);
  assert.equal(result.verification.V3.verdict,'CANNOT_VERIFY');assert.equal(result.behavior_proof,false);
  assert.deepEqual(result.behavior_comparison,{
    classification:'INVERTED_RESPONSE',requires_review:true,
    reason:'The same test passed with the observed promise violation and failed with the pinned failure text and location in both promise-holding phases. Confirm that the reported error is the intended assertion failure and review it against the sourced requirement; text linkage alone does not establish assertion execution, author intent or a catalog finding.',
  });
  assert.equal(result.original_source_unchanged,true);
});
for(const [name,options] of Object.entries({unrelated_failure:{unlinked:true},unstable_recovery:{restoredPass:true},unreached_fault:{noFault:true},source_mutation:{mutate:true}})) {
  test(`no inverted-response diagnosis for ${name}`,t=>{
    const result=invertedFixture(t,options).execute();
    assert.equal(result.verdict,'CANNOT_VERIFY');assert.equal(result.behavior_comparison,undefined);
  });
}
test('strict manifest, stale approval, excluded paths and symlinks fail closed',t=>{
  const f=fixture(t);const preview=f.invoke();fs.writeFileSync(path.join(f.source,'policy.txt'),'changed');assert.equal(f.invoke(['--execute','--trust-checkout','--approve-sha256',preview.approval_sha256]).verdict,'ERROR');
  for (const bad of [{...f.plan,unexpected:true},{...f.plan,version:true},{...f.plan,test_paths:'test.spec.ts'},{...f.plan,test:{...f.plan.test,timeout_seconds:true}},{...f.plan,edits:[{...f.plan.edits[0],path:'../app.js'}]},{...f.plan,report:{format:'playwright-json',path:'node_modules/report.json'}}]) assert.throws(()=>prepare(bad));
  fs.symlinkSync(path.join(f.source,'app.js'),path.join(f.source,'linked'));assert.throws(()=>prepare(f.plan),/symlink/);
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
  const f=fixture(t);fs.writeFileSync(path.join(f.source,'__proto__'),'pinned');fs.writeFileSync(path.join(f.source,'constructor'),'also pinned');fs.chmodSync(path.join(f.source,'app.js'),0o640);const prepared=prepare(f.plan);assert.equal(Object.hasOwn(prepared.files,'__proto__'),true);assert.equal(prepared.files.__proto__.sha256,sha('pinned'));assert.equal(prepared.files.constructor.sha256,sha('also pinned'));const result=f.execute();assert.equal(result.verdict,'DETECTED');for(const phase of ['normal','fault','restored'])assert.equal(fs.statSync(path.join(result.temporaryArtifactsRemaining,phase,'project/app.js')).mode&0o777,0o640);assert.equal(fs.statSync(path.join(f.source,'app.js')).mode&0o777,0o640);
});
test('excluded directory names do not silently omit regular files or included symlink files',t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.source,'reports'),'source file');assert.equal(Object.hasOwn(prepare(f.plan).files,'reports'),true);fs.unlinkSync(path.join(f.source,'reports'));fs.symlinkSync(path.join(f.source,'app.js'),path.join(f.source,'reports'));assert.throws(()=>prepare(f.plan),/symlink/);
});
test('ordinary cache-named runtime modules remain in every phase copy',t=>{
  const f=fixture(t),module='dist/core/cache/config.js';
  fs.mkdirSync(path.dirname(path.join(f.source,module)),{recursive:true});
  fs.writeFileSync(path.join(f.source,module),'export const cacheConfig = true;');
  const withModule=native+`\nif(!fs.existsSync('${module}'))throw new Error('runtime module missing from phase');\n`;
  fs.writeFileSync(path.join(f.source,'native.mjs'),withModule);
  f.plan.test.source.sha256=sha(withModule);
  fs.mkdirSync(path.join(f.source,'.cache'));
  fs.writeFileSync(path.join(f.source,'.cache','transient'),'ignored');
  const prepared=prepare(f.plan);
  assert.equal(Object.hasOwn(prepared.files,module),true);
  assert.equal(Object.hasOwn(prepared.files,'.cache/transient'),false);
  const result=f.execute();
  assert.equal(result.verdict,'DETECTED',result.error);
  for(const phase of ['normal','fault','restored'])
    assert.equal(fs.readFileSync(path.join(result.temporaryArtifactsRemaining,phase,'project',module),'utf8'),'export const cacheConfig = true;');
});
test('invalid UTF-8 promise source is rejected rather than decoded with replacement',t=>{
  const f=fixture(t);const data=Buffer.from([0xff]);fs.writeFileSync(path.join(f.source,'README.md'),data);f.plan.promise.sha256=sha(data);f.plan.promise.quote='\uFFFD';assert.throws(()=>prepare(f.plan));
});
test('native wrapper changing copied source mode cannot establish detection',t=>{
  const f=fixture(t);const altered=native+"\nfs.chmodSync('app.js',0o700);\n";fs.writeFileSync(path.join(f.source,'native.mjs'),altered);f.plan.test.source.sha256=sha(altered);const before=fs.statSync(path.join(f.source,'app.js')).mode&0o7777;const result=f.execute();assert.equal(result.verdict,'CANNOT_VERIFY');assert.match(result.error,/phase source mode changed/);assert.equal(result.original_source_unchanged,true);assert.equal(fs.statSync(path.join(f.source,'app.js')).mode&0o7777,before);
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

// These fixtures synthesize runtime receipts solely to exercise executor contracts.
function replaceObserver(f, transform) {
  const text=transform(observer);fs.writeFileSync(path.join(f.source,'observer.mjs'),text);f.plan.observer.source.sha256=sha(text);
}
test('a boolean or injected source text alone cannot establish runtime reachability',t=>{
  const f=fixture(t);replaceObserver(f,text=>text.replace('if(broken&&reachability)','if(false&&reachability)'));
  const result=f.execute();assert.equal(result.verdict,'CANNOT_VERIFY');assert.equal(result.behavior_proof,false);
});
test('matching runtime receipt establishes reachability independently of observer boolean',t=>{
  const f=fixture(t);replaceObserver(f,text=>text.replace('fault_reached:broken','fault_reached:false'));
  assert.equal(f.execute().verdict,'DETECTED');
});
test('behavior fault requires exactly one source edit and matching reachability path',t=>{
  const f=fixture(t);
  const missing=structuredClone(f.plan);delete missing.reachability;assert.throws(()=>prepare(missing));
  assert.throws(()=>prepare({...f.plan,reachability:{kind:'browser-binding',edit_path:'different.txt'}}));
  assert.throws(()=>prepare({...f.plan,edits:[...f.plan.edits,{path:'policy.txt',before:'detected',after:'survived',sha256:sha('detected'),kind:'source'}]}));
});
test('exact mutable data permits phase writes while original input and approval stay pinned',t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.source,'mocked-db.json'),'{}');f.plan.mutable_runtime_files=['mocked-db.json'];
  const script=native+"\nfs.writeFileSync('mocked-db.json',JSON.stringify({phase:process.env.E2E_PROBE_PHASE}));\n";
  fs.writeFileSync(path.join(f.source,'native.mjs'),script);f.plan.test.source.sha256=sha(script);
  const result=f.execute();assert.equal(result.verdict,'DETECTED');assert.equal(result.original_source_unchanged,true);assert.equal(fs.readFileSync(path.join(f.source,'mocked-db.json'),'utf8'),'{}');
  const preview=f.invoke();fs.writeFileSync(path.join(f.source,'mocked-db.json'),'{"tampered":true}');
  assert.equal(f.invoke(['--execute','--trust-checkout','--approve-sha256',preview.approval_sha256]).verdict,'ERROR');
});
test('mutable data declarations cannot hide source, tests, wrappers, promises or configuration',t=>{
  const f=fixture(t);
  for(const name of ['app.js','test.spec.ts','native.mjs','observer.mjs','README.md','package.json','tsconfig.json','../mocked-db.json','mocked-*.json'])
    assert.throws(()=>prepare({...f.plan,mutable_runtime_files:[name]}),name);
  assert.throws(()=>prepare({...f.plan,mutable_runtime_files:['mocked-db.json','mocked-db.json']}));
});
test('saved preview resumes approved environment across PATH drift and rejects receipt tampering',t=>{
  const f=fixture(t),runner=new URL('../scripts/run-probe.mjs',cli),planPath=path.join(f.root,'saved-plan.json');
  const script=native+"\nif(process.env.PATH!=='/approved/path') throw new Error('approved PATH was not reused');\n";
  fs.writeFileSync(path.join(f.source,'native.mjs'),script);f.plan.test.source.sha256=sha(script);fs.writeFileSync(planPath,JSON.stringify(f.plan));
  let call=0;
  const invoke=(args,PATH)=>{const r=spawnSync(process.execPath,[runner.pathname,'--output-dir',path.join(f.root,`resume-${++call}`),...args],{encoding:'utf8',env:{...process.env,PATH},timeout:15000});assert.equal(r.error,undefined);return {code:r.status,...JSON.parse(r.stdout)};};
  const preview=invoke(['--plan',planPath],'/approved/path');assert.equal(preview.verdict,'PREVIEW');
  const saved=path.join(preview.temporaryArtifactsRemaining,'preview.json'),digest=preview.approval_sha256;
  const flags=['--approved-preview',saved,'--execute','--trust-checkout','--approve-sha256',digest];
  const result=invoke(flags,'/different/turn/path');assert.equal(result.verdict,'DETECTED');assert.equal(result.code,0);
  assert.equal(JSON.parse(fs.readFileSync(path.join(result.temporaryArtifactsRemaining,'preview.json'),'utf8')).approval_sha256,digest);
  const untrusted=invoke(flags.filter(flag=>flag!=='--trust-checkout'),'/different/turn/path');assert.equal(untrusted.verdict,'ERROR');
  const changedPlan={...f.plan,test_selector:'different test'};fs.writeFileSync(planPath,JSON.stringify(changedPlan));
  assert.equal(invoke([...flags,'--plan',planPath],'/different/turn/path').verdict,'ERROR');
  const captured=JSON.parse(fs.readFileSync(saved,'utf8'));captured.effective_environment.PATH='/tampered/path';fs.writeFileSync(saved,JSON.stringify(captured));
  const tampered=invoke(flags,'/different/turn/path');assert.equal(tampered.verdict,'ERROR');assert.equal(fs.existsSync(path.join(f.root,`resume-${call}`,'normal')),false);
});

for(const field of ['token','path','phase','project']) test(`runtime reachability rejects mismatched ${field}`,t=>{
  const f=fixture(t);replaceObserver(f,text=>text.replace(`${field}:reachability.${field}`,`${field}:'wrong'`));
  const result=f.execute();assert.equal(result.verdict,'CANNOT_VERIFY');assert.equal(result.behavior_proof,false);
});
test('a runtime receipt in a normal phase cannot manufacture behavior proof',t=>{
  const f=fixture(t);replaceObserver(f,text=>text.replace('if(broken&&reachability)','if(reachability)'));
  const result=f.execute();assert.equal(result.verdict,'CANNOT_VERIFY');assert.match(result.error,/outside the fault phase/);
});
test('undeclared runtime data writes remain a source-integrity failure',t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.source,'mocked-db.json'),'{}');
  const script=native+"\nfs.writeFileSync('mocked-db.json',JSON.stringify({changed:true}));\n";
  fs.writeFileSync(path.join(f.source,'native.mjs'),script);f.plan.test.source.sha256=sha(script);
  const result=f.execute();assert.equal(result.verdict,'CANNOT_VERIFY');assert.equal(result.original_source_unchanged,true);assert.match(result.error,/phase source/);
});

for(const [name,source,before] of [
  ['unbraced conditional','function action() { if (ready) WORKS; }','WORKS;'],
  ['unbraced loop','function action() { while (ready) WORKS; }','WORKS;'],
  ['function declaration','function action() { WORKS; }','function action() { WORKS; }'],
  ['partial expression','function action() { send(WORKS); }','WORKS'],
]) test(`runtime marker refuses ${name} edit`,t=>{
  const f=fixture(t);fs.writeFileSync(path.join(f.source,'app.js'),source);
  f.plan.edits=[{path:'app.js',before,after:'BROKEN;',sha256:sha(source),kind:'source'}];
  assert.throws(()=>prepare(f.plan));
});
