// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {spawn} from 'node:child_process';
import {runOwnedCommand,startOwned,withServices} from '../scripts/probe-lifecycle.mjs';
const config=script=>({argv:[process.execPath,'-e',script],cwd:process.cwd(),env:{PATH:process.env.PATH},timeoutMs:1500});
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function assertStopped(pid) {
  const deadline=Date.now()+2000;
  while(Date.now()<deadline) {
    try { process.kill(pid,0); }
    catch(error) { if(error.code==='ESRCH')return; throw error; }
    // Linux containers can retain a dead orphan until PID 1 reaps it.
    if(process.platform==='linux') {
      try { if(/\) Z /.test(fs.readFileSync(`/proc/${pid}/stat`,'utf8')))return; }
      catch(error) { if(error.code==='ENOENT')return; throw error; }
    }
    await sleep(20);
  }
  assert.fail(`owned process ${pid} remained live`);
}
test('normal completion preserves native status and kills live group anchor',async()=>{
  const result=await runOwnedCommand(config('process.exit(7)'));assert.equal(result.terminal.code,7);assert.equal(result.cleanup.complete,true);assert.equal(result.grouped,process.platform!=='win32');
});
test('signal terminal with null exitCode never waits for an already-fired event',async()=>{
  const owned=startOwned({...config("process.kill(process.pid,'SIGTERM')"),inheritGroup:true});const terminal=await owned.terminal;assert.equal(terminal.code,null);assert.equal(terminal.signal,'SIGTERM');await sleep(20);const cleanup=await owned.stop();assert.equal(cleanup.complete,true);assert.equal(cleanup.already_exited,true);
});
test('concurrent stop calls share one idempotent cleanup',async()=>{
  const owned=startOwned(config('setInterval(()=>{},1000)'));const a=owned.stop(),b=owned.stop();assert.equal(a,b);assert.equal((await a).complete,true);assert.equal(owned.receipt.cleanup.attempts.length,1);
});
test('timeout kills owned descendants and records timeout separately',async t=>{
  if(process.platform==='win32')return t.skip('POSIX groups');const root=fs.mkdtempSync(path.join(os.tmpdir(),'lifecycle-draft-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const pidFile=path.join(root,'pid');
  const script=`const {spawn}=require('node:child_process');const fs=require('node:fs');const child=spawn(process.execPath,['-e','setInterval(()=>{},1000)'],{stdio:'ignore'});fs.writeFileSync(${JSON.stringify(pidFile)},String(child.pid));setInterval(()=>{},1000)`;
  const receipt=await runOwnedCommand({...config(script),timeoutMs:300});assert.equal(receipt.timeout,true);assert.equal(receipt.terminal.code,null);assert.equal(receipt.terminal.signal,null);assert.equal(receipt.cleanup.complete,true);const pid=Number(fs.readFileSync(pidFile));await assertStopped(pid);
});
test('spawn failure has a terminal and cleanup receipt',async()=>{
  const result=await runOwnedCommand({...config(''),argv:['/no/such/lifecycle-command']});assert.equal(result.terminal.error.code,'ENOENT');assert.equal(result.cleanup.complete,true);
});
test('persistent injected EPERM remains an explicit cleanup failure',async()=>{
  const result=await runOwnedCommand({...config('process.exit(0)'),killGroup(){const error=Error('permission denied');error.code='EPERM';throw error;}});assert.equal(result.terminal.code,0);assert.equal(result.cleanup.complete,false);assert.equal(result.cleanup.error.code,'EPERM');assert.equal(result.cleanup.attempts[0].error.code,'EPERM');
});
async function unusedPort(){for(let port=4600;port<=4639;port++){const server=net.createServer();try{await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',resolve);});await new Promise(resolve=>server.close(resolve));return port;}catch(error){if(error.code!=='EADDRINUSE')throw error;}}throw Error('lane ports unavailable');}
test('HTTP service ready callback and shutdown retain service receipt',async()=>{
  const port=await unusedPort();const script=`require('node:http').createServer((q,r)=>r.end('ready')).listen(${port},'127.0.0.1')`;const result=await withServices([{...config(script),ready:{url:`http://127.0.0.1:${port}`,timeoutMs:2000}}],async receipts=>{assert.equal(receipts[0].ready.status,200);return 'done';});assert.equal(result.value,'done');assert.equal(result.services[0].cleanup.complete,true);
});
test('startup failure and callback failure both include shutdown receipts',async()=>{
  const port=await unusedPort();await assert.rejects(withServices([{...config('process.exit(3)'),ready:{url:`http://127.0.0.1:${port}`,timeoutMs:1000}}],()=>assert.fail('must not run')),error=>{assert.equal(error.serviceReceipts[0].cleanup.complete,true);return true;});
  const script=`require('node:http').createServer((q,r)=>r.end('ready')).listen(${port},'127.0.0.1')`;await assert.rejects(withServices([{...config(script),ready:{url:`http://127.0.0.1:${port}`,timeoutMs:2000}}],()=>{throw Error('callback failed');}),error=>{assert.equal(error.message,'callback failed');assert.equal(error.serviceReceipts[0].cleanup.complete,true);return true;});
});
test('readiness timeout always cleans started service',async()=>{
  const port=await unusedPort();await assert.rejects(withServices([{...config('setInterval(()=>{},1000)'),ready:{url:`http://127.0.0.1:${port}`,timeoutMs:120}}],()=>assert.fail('must not run')),error=>{assert.match(error.message,/readiness deadline/);assert.equal(error.serviceReceipts[0].cleanup.complete,true);return true;});
});
test('service death after readiness cannot become successful callback result',async()=>{
  const port=await unusedPort();const script=`require('node:http').createServer((q,r)=>{r.end('ready');setTimeout(()=>process.exit(4),50);}).listen(${port},'127.0.0.1')`;await assert.rejects(withServices([{...config(script),ready:{url:`http://127.0.0.1:${port}`,timeoutMs:2000}}],async()=>{await sleep(180);return 'done';}),error=>{assert.match(error.message,/service exited/);assert.equal(error.serviceReceipts[0].terminal.code,4);assert.equal(error.serviceReceipts[0].cleanup.complete,true);return true;});
});
test('all service definitions validate before any spawn including external URL refusal',async t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'lifecycle-draft-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const marker=path.join(root,'spawned');const good={...config(`require('node:fs').writeFileSync(${JSON.stringify(marker)},'started')`),ready:{url:'http://127.0.0.1:4600'}};
  for(const bad of [{...good,ready:{url:'https://example.com/'}},{...good,ready:{...good.ready,timeoutMs:Infinity}},{...good,cleanupMs:0},{...good,ready:{...good.ready,status:700}}]){
    await assert.rejects(withServices([good,bad],()=>assert.fail('must not run')),error=>{assert.equal(error.serviceReceipts.length,0);return true;});assert.equal(fs.existsSync(marker),false);
  }
});
test('occupied readiness port is refused before spawn',async t=>{
  const port=await unusedPort();const server=net.createServer();await new Promise(resolve=>server.listen(port,'127.0.0.1',resolve));t.after(()=>new Promise(resolve=>server.close(resolve)));
  await assert.rejects(withServices([{...config('process.exit(0)'),ready:{url:`http://127.0.0.1:${port}`}}],()=>assert.fail('must not run')),error=>{assert.equal(error.code,'EADDRINUSE');assert.equal(error.serviceReceipts.length,0);return true;});
});
test('readiness never follows redirects',async()=>{
  const port=await unusedPort();const script=`require('node:http').createServer((q,r)=>{if(q.url==='/target')r.end('ready');else {r.statusCode=302;r.setHeader('location','/target');r.end();}}).listen(${port},'127.0.0.1')`;
  await assert.rejects(withServices([{...config(script),ready:{url:`http://127.0.0.1:${port}`,timeoutMs:350}}],()=>assert.fail('must not run')),error=>{assert.match(error.message,/readiness deadline/);assert.equal(error.serviceReceipts[0].cleanup.complete,true);return true;});
});
test('direct ENOENT returns both terminal and cleanup receipts',async()=>{
  const receipt=await runOwnedCommand({...config('unused'),argv:['/missing/lifecycle-command'],inheritGroup:true});assert.equal(receipt.terminal.error.code,'ENOENT');assert.equal(receipt.cleanup.complete,true);
});
test('ESRCH at cleanup is admitted only with observed supervisor termination',async()=>{
  const receipt=await runOwnedCommand({...config('process.exit(0)'),killGroup(target,signal){process.kill(target,signal);const error=Error('already gone');error.code='ESRCH';throw error;}});assert.equal(receipt.cleanup.complete,true);assert.equal(receipt.cleanup.attempts[0].error.code,'ESRCH');
});
test('early stop never launches command after supervisor shutdown starts',async t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'lifecycle-draft-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const marker=path.join(root,'spawned');const owned=startOwned(config(`require('node:fs').writeFileSync(${JSON.stringify(marker)},'started')`));assert.equal((await owned.stop()).complete,true);assert.equal(fs.existsSync(marker),false);
});
test('parent disconnect kills detached service group',async t=>{
  if(process.platform==='win32')return t.skip('POSIX groups');const root=fs.mkdtempSync(path.join(os.tmpdir(),'lifecycle-draft-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));const marker=path.join(root,'server-pid');const moduleUrl=new URL('../scripts/probe-lifecycle.mjs',import.meta.url).href;
  const script=`import {startOwned} from ${JSON.stringify(moduleUrl)};import fs from 'node:fs';const owned=startOwned(${JSON.stringify(config(`require('node:fs').writeFileSync(${JSON.stringify(marker)},String(process.pid));setInterval(()=>{},1000)`))});while(!fs.existsSync(${JSON.stringify(marker)}))await new Promise(r=>setTimeout(r,10));process.exit(0);`;
  const parent=spawn(process.execPath,['--input-type=module','-e',script],{stdio:'ignore'});await new Promise((resolve,reject)=>{parent.once('error',reject);parent.once('exit',code=>code===0?resolve():reject(Error('fixture parent failed')));});const pid=Number(fs.readFileSync(marker));await assertStopped(pid);
});
test('duplicate loopback readiness ports are rejected before service or callback starts',async t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'lifecycle-duplicate-port-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const marker=path.join(root,'started');let callbacks=0;
  const command=config(`require('node:fs').appendFileSync(${JSON.stringify(marker)},'started');setInterval(()=>{},1000)`);
  for(const [first,second] of [['localhost','127.0.0.1'],['127.0.0.1','[::1]'],['[::1]','localhost'],['127.0.0.1','127.0.0.1']]){
    await assert.rejects(withServices([
      {...command,ready:{url:`http://${first}:4600/health`,timeoutMs:100}},
      {...command,ready:{url:`http://${second}:4600/different-path`,timeoutMs:100}},
    ],()=>{callbacks++;}),error=>{assert.match(error.message,/ports must be distinct/);assert.deepEqual(error.serviceReceipts,[]);return true;});
    assert.equal(fs.existsSync(marker),false);assert.equal(callbacks,0);
  }
});
