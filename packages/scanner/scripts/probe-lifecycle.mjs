// SPDX-License-Identifier: Apache-2.0
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import net from 'node:net';
const anchor = fileURLToPath(new URL('./probe-anchor.mjs',import.meta.url));
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
const failure = error => ({code:error.code ?? null,message:error.message});
function deferred(){let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
async function bounded(promise,ms){let timer;try{return await Promise.race([promise,new Promise(resolve=>{timer=setTimeout(()=>resolve(null),ms);})]);}finally{clearTimeout(timer);}}
function duration(value,fallback,max){const result=value??fallback;if(!Number.isInteger(result)||result<1||result>max)throw Error('invalid bounded deadline');return result;}
function validateCommand(config){
  if(!config||!Array.isArray(config.argv)||!config.argv.length||config.argv.some(arg=>typeof arg!=='string'||!arg||arg.includes('\0')))throw Error('argv required');
  if(typeof config.cwd!=='string'||!config.cwd)throw Error('cwd required');
  duration(config.timeoutMs,120000,300000);duration(config.cleanupMs,2000,10000);
}
function validateService(config){
  validateCommand(config);if(!config.ready)throw Error('readiness required');
  const url=new URL(config.ready.url);
  if(url.protocol!=='http:'||!['localhost','127.0.0.1','[::1]'].includes(url.hostname)||url.username||url.password||url.hash)throw Error('readiness must use loopback HTTP');
  duration(config.ready.timeoutMs,30000,300000);
  const status=config.ready.status??200;if(!Number.isInteger(status)||status<100||status>599)throw Error('invalid readiness status');
  return url;
}
async function unusedEndpoint(url){
  const hosts=url.hostname==='localhost'?['127.0.0.1','::1']:[url.hostname.replace(/^\[|\]$/g,'')];
  for(const host of hosts)await new Promise((resolve,reject)=>{
    const server=net.createServer();server.once('error',reject);server.listen({host,port:Number(url.port||80),exclusive:true},()=>server.close(resolve));
  });
}

// fds belong to the caller; this module never closes them. Tests may inject killGroup.
export function startOwned(config) {
  validateCommand(config);
  const {argv,cwd,env,stdout='ignore',stderr='ignore',inheritGroup=false,killGroup=process.kill.bind(process),cleanupMs=2000}=config;
  const grouped=process.platform!=='win32'&&!inheritGroup;
  const terminal=deferred(),closed=deferred();let terminalValue,stopPromise,stopping=false;
  const receipt={argv,cwd,grouped,events:[],cleanup:{complete:false,attempts:[]}};
  const child=grouped?spawn(process.execPath,[anchor],{cwd,env,detached:true,stdio:['ignore',stdout,stderr,'ipc']}):spawn(argv[0],argv.slice(1),{cwd,env,stdio:['ignore',stdout,stderr]});
  receipt.supervisor_pid=child.pid ?? null;
  function finish(value){if(terminalValue)return;terminalValue=value;receipt.terminal=value;terminal.resolve(value);}
  child.once('error',error=>{receipt.events.push({kind:'spawn-error',...failure(error)});finish({code:null,signal:null,error:failure(error)});});
  child.once('exit',(code,signal)=>{receipt.events.push({kind:'supervisor-exit',code,signal});closed.resolve({code,signal});if(!terminalValue)finish(grouped&&stopping?{code:null,signal:null,terminated_by_cleanup:true}:{code,signal,...(grouped?{error:{message:'supervisor exited before command completion'}}:{})});});
  if(grouped){child.on('message',message=>{receipt.events.push(message);if(message.kind==='terminal')finish(message);});child.once('spawn',()=>{if(!stopping)child.send({argv,cwd},error=>{if(error)finish({code:null,signal:null,error:failure(error)});});});}
  function stop(){return stopPromise??=(async()=>{
    stopping=true;
    const cleanup=receipt.cleanup;
    // A direct child has no owned group; never signal it after terminal completion.
    if(!grouped&&terminalValue){cleanup.complete=true;cleanup.already_exited=true;return cleanup;}
    if(!child.pid){cleanup.complete=true;cleanup.not_started=true;return cleanup;}
    const target=grouped?-child.pid:child.pid;
    try{killGroup(target,'SIGKILL');cleanup.attempts.push({target,signal:'SIGKILL',result:'sent'});}
    catch(error){cleanup.attempts.push({target,signal:'SIGKILL',error:failure(error)});if(error.code!=='ESRCH')cleanup.error=failure(error);}
    // Preserve permission errors. Direct fallback stops the supervisor but cannot prove descendant cleanup.
    if(cleanup.error)try{child.kill('SIGKILL');}catch{}
    const ended=(child.exitCode!==null||child.signalCode!==null)?{code:child.exitCode,signal:child.signalCode}:await bounded(closed.promise,cleanupMs);
    cleanup.complete=!cleanup.error&&ended!==null;
    if(!ended)cleanup.error??={message:'termination deadline exceeded'};
    return cleanup;
  })();}
  return {receipt,terminal:terminal.promise,stop};
}

export async function runOwnedCommand(config){
  const owned=startOwned(config);let timer;
  try{const timeout=new Promise(resolve=>{timer=setTimeout(()=>resolve(null),config.timeoutMs??120000);});const ended=await Promise.race([owned.terminal,timeout]);if(!ended){owned.receipt.timeout=true;owned.receipt.terminal={code:null,signal:null};}}
  finally{clearTimeout(timer);await owned.stop();}
  return owned.receipt;
}

// Callback runs only after every service responds with its approved status.
// Each service owns a separate group; shutdown is sequential and reverse-order.
export async function withServices(configs,callback){
  const services=[];let value,error;
  try{
    if(!Array.isArray(configs)||typeof callback!=='function')throw Error('service configs and callback required');
    const urls=configs.map(validateService);
    const ports=new Set();
    for(const url of urls){
      const port=Number(url.port||80);
      if(ports.has(port))throw Error('service readiness ports must be distinct across loopback hosts');
      ports.add(port);
    }
    // Check all configs and endpoints before starting any service. This is a
    // preflight, not a port reservation; strict service bind failures stay fatal.
    for(const url of urls)await unusedEndpoint(url);
    for(const [index,config] of configs.entries()){
      const owned=startOwned(config);services.push(owned);
      const url=urls[index];
      const deadline=Date.now()+(config.ready.timeoutMs??30000);let ready=false,ended;
      owned.terminal.then(value=>{ended=value;});
      while(Date.now()<deadline){
        if(ended)throw Error('service exited before readiness');
        try{const response=await fetch(url,{method:'GET',redirect:'error',signal:AbortSignal.timeout(Math.min(500,Math.max(1,deadline-Date.now())))});await response.body?.cancel();if(response.status===(config.ready.status??200)){ready=true;break;}}catch{}
        await delay(Math.min(50,Math.max(1,deadline-Date.now())));
      }
      if(!ready)throw Error('service readiness deadline exceeded');
      owned.receipt.ready={url:url.href,status:config.ready.status??200};
    }
    value=await callback(services.map(service=>service.receipt));
  }catch(caught){error=caught;}
  finally{for(const service of services.reverse()){
    if(service.receipt.terminal)error??=Error('service exited during callback');
    await service.stop();
  }}
  const receipts=services.reverse().map(service=>service.receipt);
  if(error||receipts.some(receipt=>!receipt.cleanup.complete)){const caught=error??Error('service cleanup incomplete');caught.serviceReceipts=receipts;throw caught;}
  return {value,services:receipts};
}
