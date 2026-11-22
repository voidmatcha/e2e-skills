// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {withServices,runCommand} from '../scripts/run-probe.mjs';
async function port(){for(let p=4600;p<=4639;p++){const server=net.createServer();try{await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(p,'127.0.0.1',resolve);});await new Promise(resolve=>server.close(resolve));return p;}catch(error){if(error.code!=='EADDRINUSE')throw error;}}throw Error('lane ports unavailable');}
function fixture(t){const root=fs.mkdtempSync(path.join(fs.realpathSync(os.tmpdir()),'probe-service-export-'));const old=process.env.E2E_PROBE_SERVICES_DIR;process.env.E2E_PROBE_SERVICES_DIR=path.join(root,'receipts');t.after(()=>{if(old===undefined)delete process.env.E2E_PROBE_SERVICES_DIR;else process.env.E2E_PROBE_SERVICES_DIR=old;fs.rmSync(root,{recursive:true,force:true});});return root;}
function receipts(root){return fs.readdirSync(path.join(root,'receipts')).map(name=>JSON.parse(fs.readFileSync(path.join(root,'receipts',name))));}
test('export owns fresh stdout/stderr log descriptors and records successful shutdown',async t=>{
  const root=fixture(t),p=await port();const script=`console.log('service output');console.error('service error');require('node:http').createServer((q,r)=>r.end('ready')).listen(${p},'127.0.0.1')`;
  assert.equal(await withServices([{cwd:root,argv:[process.execPath,'-e',script],stdout:'output.log',stderr:'error.log',ready:{url:`http://127.0.0.1:${p}`,timeoutMs:2000}}],()=>7),7);
  assert.match(fs.readFileSync(path.join(root,'output.log'),'utf8'),/service output/);assert.match(fs.readFileSync(path.join(root,'error.log'),'utf8'),/service error/);assert.equal(receipts(root)[0].services[0].cleanup.complete,true);
});
test('startup failure retains logs and cleanup receipt',async t=>{
  const root=fixture(t),p=await port();await assert.rejects(withServices([{cwd:root,argv:[process.execPath,'-e',"console.error('startup failed');process.exit(4)"],stdout:'output.log',stderr:'error.log',ready:{url:`http://127.0.0.1:${p}`,timeoutMs:1000}}],()=>assert.fail('must not run')));assert.match(fs.readFileSync(path.join(root,'error.log'),'utf8'),/startup failed/);assert.equal(receipts(root)[0].services[0].cleanup.complete,true);
});
test('all log destinations validate before spawn; traversal and symlink refused',async t=>{
  const root=fixture(t),p=await port(),marker=path.join(root,'spawned');const config={cwd:root,argv:[process.execPath,'-e',`require('node:fs').writeFileSync(${JSON.stringify(marker)},'started')`],ready:{url:`http://127.0.0.1:${p}`,timeoutMs:100}};
  await assert.rejects(withServices([config,{...config,stdout:'../outside.log'}],()=>assert.fail('must not run')),/inside cwd/);assert.equal(fs.existsSync(marker),false);
  fs.symlinkSync(root,path.join(root,'link'));await assert.rejects(withServices([{...config,stdout:'link/output.log'}],()=>assert.fail('must not run')),/symlink/);assert.equal(fs.existsSync(marker),false);
});
for (const abrupt of [false,true]) test(`command verifies detached service receipt after ${abrupt?'abrupt':'normal'} wrapper exit`,async t=>{
  const root=fixture(t),p=await port(),out=path.join(root,'command');fs.mkdirSync(out);
  const runner=new URL('../scripts/run-probe.mjs',import.meta.url).href;
  const service=`require('node:http').createServer((q,r)=>r.end('ready')).listen(${p},'127.0.0.1')`;
  const code=`import {withServices} from ${JSON.stringify(runner)};await withServices([{cwd:${JSON.stringify(root)},argv:[process.execPath,'-e',${JSON.stringify(service)}],ready:{url:'http://127.0.0.1:${p}',timeoutMs:2000}}],()=>{${abrupt?'process.exit(0)':'return 0'}});`;
  const run=runCommand({argv:[process.execPath,'--input-type=module','-e',code],timeout_seconds:5,_selector:'owned'},root,'normal',path.join(root,'report.json'),out);
  if(abrupt)await assert.rejects(run,/service cleanup is unverified/);else assert.equal((await run).exit_code,0);
  const receipt=JSON.parse(fs.readFileSync(path.join(out,'command.json'),'utf8'));
  assert.equal(receipt.exit_code,0);assert.equal(receipt.services[0].status,abrupt?'STARTED':'COMPLETE');
  if(abrupt)assert.match(receipt.error,/cleanup is unverified/);else assert.equal(receipt.services[0].services[0].cleanup.complete,true);
});
