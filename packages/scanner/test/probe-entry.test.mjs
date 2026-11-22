// SPDX-License-Identifier: Apache-2.0
// Contract tests use a synthetic CLI; the opt-in native test uses real Playwright.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fetchJson,runCommand} from '../scripts/run-probe.mjs';
const runner = new URL('../scripts/run-probe.mjs',import.meta.url).href;
function fixture(t, policy = 'one') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'probe-entry-')));
  t.after(() => fs.rmSync(root,{recursive:true,force:true}));
  const project = path.join(root,'project'), out = path.join(root,'phase');
  fs.mkdirSync(project); fs.mkdirSync(out); fs.mkdirSync(path.join(project,'node_modules'));
  fs.writeFileSync(path.join(project,'selected.spec.ts'),'// synthetic declaration\n');
  const cli = `import fs from 'node:fs';
const list=process.argv.includes('--list');
fs.appendFileSync('calls.jsonl',JSON.stringify(process.argv.slice(2))+'\\n');
const spec={id:'id',title:'nested [literal] title',file:'selected.spec.ts',line:${policy === 'wrong-line' ? 8 : 7},column:1,tests:[{projectName:${JSON.stringify(policy === 'wrong-project' ? 'firefox' : 'chromium')},results:list?[]:[{status:'passed',retry:0}]}]};
const specs=${policy === 'zero' ? '[]' : policy === 'multiple' ? '[spec,spec]' : '[spec]'};
if (!list && ${JSON.stringify(policy)} === 'drift') spec.id='other';
fs.writeFileSync(process.env.PLAYWRIGHT_JSON_OUTPUT_NAME,JSON.stringify({config:{rootDir:process.cwd(),workers:1},suites:[{specs}],errors:[]}));
`;
  fs.writeFileSync(path.join(project,'node_modules/cli.mjs'),cli);
  const selection = {cli:'node_modules/cli.mjs',file:'selected.spec.ts',line:7,project:'chromium'};
  function run(change = {}) {
    const selected = {...selection,...change};
    const config = {selection:selected,project,phase:'normal',report:path.join(project,'report.json'),out};
    return spawnSync(process.execPath,['--input-type=module','-e',`import {runPlaywright} from ${JSON.stringify(runner)};process.exitCode=await runPlaywright();`],
      {cwd:project,env:{PATH:process.env.PATH,E2E_PROBE_SELECTOR:'nested [literal] title',E2E_PROBE_PLAYWRIGHT:JSON.stringify(config)},encoding:'utf8',timeout:15000});
  }
  return {project,out,run};
}
test('native helper owns file:line, exact-one preflight and matching execution',t => {
  const f=fixture(t), r=f.run(); assert.equal(r.status,0,r.stderr);
  const calls=fs.readFileSync(path.join(f.project,'calls.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  assert.equal(calls.length,2); assert.ok(calls[0].includes('--list')); assert.ok(!calls[1].includes('--list'));
  assert.ok(calls[0].includes('selected\\.spec\\.ts:7'));
  for (const flag of ['--workers=1','--retries=0','--repeat-each=1','--no-deps']) assert.ok(calls[1].includes(flag));
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.out,'native-selection.json'))).selected.line,7);
});
for (const policy of ['zero','multiple','wrong-line','wrong-project','drift']) test(`native selection refuses ${policy}`,t=>{
  const f=fixture(t,policy),r=f.run(); assert.notEqual(r.status,0);
  assert.match(r.stderr,/selected|selection/);
  assert.equal(fs.readFileSync(path.join(f.project,'calls.jsonl'),'utf8').trim().split('\n').length,policy==='drift'?2:1);
  assert.equal(fs.existsSync(path.join(f.out,'native-selection.json')),false);
});
test('full title is escaped and anchored once including hierarchy and tags',t=>{
  const f=fixture(t),r=f.run({line:undefined,full_title:'chromium selected.spec.ts outer nested [literal] title @smoke'});
  assert.equal(r.status,0,r.stderr);
  const calls=fs.readFileSync(path.join(f.project,'calls.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  assert.ok(calls[0].includes('--grep=^chromium selected\\.spec\\.ts outer nested \\[literal\\] title @smoke$'));
});
test('fetchJson handles Node boolean ok and reports HTTP failure',async()=>{
  const original=globalThis.fetch;
  try {
    globalThis.fetch=async()=>({ok:true,status:201,json:async()=>({id:1})});
    assert.deepEqual(await fetchJson('http://fixture.invalid'),{id:1});
    globalThis.fetch=async()=>({ok:false,status:503,json:async()=>({})});
    await assert.rejects(fetchJson('http://fixture.invalid'),/HTTP 503.*ok is a boolean/);
  } finally {globalThis.fetch=original;}
});

test('outer wrapper timeout kills nested native helper and its child', {skip:process.platform==='win32'},async t=>{
  const f=fixture(t), pidFile=path.join(f.project,'child.pid');
  const cli=path.join(f.project,'node_modules/cli.mjs');
  fs.appendFileSync(cli,`
if(!list){const {spawn}=await import('node:child_process');const child=spawn(process.execPath,['-e','setTimeout(()=>{},30000)']);fs.writeFileSync('child.pid',String(child.pid));await new Promise(resolve=>setTimeout(resolve,30000));}`);
  const output=path.join(f.out,'wrapper');fs.mkdirSync(output);
  const env={PATH:process.env.PATH,E2E_PROBE_PLAYWRIGHT:JSON.stringify({selection:{cli:'node_modules/cli.mjs',file:'selected.spec.ts',line:7,project:'chromium'},project:f.project,phase:'normal',report:path.join(f.project,'report.json'),out:f.out})};
  const receipt=await runCommand({argv:[process.execPath,'--input-type=module','-e',`import {runPlaywright} from ${JSON.stringify(runner)};await runPlaywright();`],timeout_seconds:2,_selector:'nested [literal] title',_environment:env},f.project,'normal',path.join(f.project,'report.json'),output);
  assert.equal(receipt.timeout,true);assert.ok(fs.existsSync(pidFile));
  const pid=Number(fs.readFileSync(pidFile,'utf8'));await new Promise(resolve=>setTimeout(resolve,100));
  let alive=false;try{process.kill(pid,0);alive=true;}catch(error){assert.equal(error.code,'ESRCH');}
  if(alive&&process.platform==='linux'){const stat=fs.readFileSync(`/proc/${pid}/stat`,'utf8');alive=!['Z','X'].includes(stat.slice(stat.lastIndexOf(')')+1).trim().split(/\s/)[0]);}
  if(alive)process.kill(pid,'SIGKILL');
  assert.equal(alive,false,'nested native descendant escaped outer timeout');
});

// Run explicitly with existing dependencies; CI's offline synthetic contracts do
// not claim browser integration. No download, server, or user checkout is needed.
test('real Playwright selection and a runtime binding survive JSX comment removal',{
  skip:!process.env.E2E_PROBE_NATIVE_DEPS
},async t=>{
  const deps=process.env.E2E_PROBE_NATIVE_DEPS;
  const f=fixture(t);
  fs.rmSync(path.join(f.project,'node_modules'),{recursive:true});
  fs.symlinkSync(deps,path.join(f.project,'node_modules'),'dir');
  fs.writeFileSync(path.join(f.project,'playwright.config.cjs'),"module.exports={testDir:'.',projects:[{name:'chromium',use:{browserName:'chromium'}}]};");
  fs.writeFileSync(path.join(f.project,'selected.spec.ts'),"import {test,expect} from '@playwright/test';\ntest.describe('outer [suite]',()=>{\n test('one + literal',async()=>{expect(1).toBe(1)});\n test('other',async()=>{expect(2).toBe(2)});\n});\n");
  const r=f.run({cli:'node_modules/@playwright/test/cli.js',line:3});
  assert.equal(r.status,0,r.stderr);
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.out,'native-selection.json'))).selected.title,'one + literal');
  for(const name of ['native-selection','native-run','native-selection.json'])fs.rmSync(path.join(f.out,name),{recursive:true,force:true});
  fs.unlinkSync(path.join(f.project,'report.json'));
  const full=f.run({cli:'node_modules/@playwright/test/cli.js',line:undefined,full_title:'chromium selected.spec.ts outer [suite] one + literal'});
  assert.equal(full.status,0,full.stderr);

  const {chromium}=await import(new URL('playwright/index.mjs',new URL('file://' + deps + '/')));
  const {attachReachability}=await import(runner);
  const tsPath=process.env.E2E_PROBE_TYPESCRIPT;
  assert.ok(tsPath,'set E2E_PROBE_TYPESCRIPT to the trusted bundled typescript.cjs');
  const {default:ts}=await import(new URL('file://' + tsPath));
  const source=`function fault(){ globalThis['__probe_jsx']?.('runtime-token',0); /* LOST_MARKER */ return <span>broken</span>; }`;
  const transformed=ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.React,removeComments:true,target:ts.ScriptTarget.ES2022}}).outputText;
  assert.ok(!transformed.includes('LOST_MARKER'));
  const artifact=path.join(f.out,'runtime.jsonl'), prior=process.env.E2E_PROBE_REACHABILITY;
  process.env.E2E_PROBE_REACHABILITY=JSON.stringify({binding:'__probe_jsx',token:'runtime-token',path:'app.jsx',edit_count:1,phase:'fault',project:f.project,artifact});
  const browser=await chromium.launch({headless:true});
  try {
    const page=await browser.newPage();await attachReachability(page);
    await page.goto('about:blank');await page.addScriptTag({content:transformed});
    assert.equal(fs.existsSync(artifact),false,'loading source is not a runtime hit');
    await page.evaluate(async()=>{globalThis.React={createElement:()=>null};fault();await new Promise(resolve=>setTimeout(resolve,30));});
    const hit=JSON.parse(fs.readFileSync(artifact,'utf8').trim());
    assert.equal(hit.token,'runtime-token');assert.equal(hit.path,'app.jsx');assert.equal(hit.edit_index,0);assert.equal(hit.phase,'fault');
  } finally {await browser.close();if(prior===undefined)delete process.env.E2E_PROBE_REACHABILITY;else process.env.E2E_PROBE_REACHABILITY=prior;}
});
