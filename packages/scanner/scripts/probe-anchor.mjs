// SPDX-License-Identifier: Apache-2.0
// Remain the owned process-group leader until the parent terminates the group.
import {spawn} from 'node:child_process';
const keepAlive = setInterval(() => {}, 1000);
const send = value => { if (process.connected) process.send(value); };
process.once('message', ({argv,cwd}) => {
  const child = spawn(argv[0],argv.slice(1),{cwd,env:process.env,stdio:'inherit'});
  child.once('spawn',()=>send({kind:'spawn',pid:child.pid}));
  child.once('error',error=>send({kind:'terminal',code:null,signal:null,error:{code:error.code,message:error.message}}));
  child.once('exit',(code,signal)=>send({kind:'terminal',code,signal}));
});
// A disconnected parent cannot request cleanup. Terminate this owned group.
process.once('disconnect',()=>{clearInterval(keepAlive);try{process.kill(-process.pid,'SIGKILL');}catch(error){console.error('Owned group cleanup failed after parent disconnect:',error.code,error.message);process.exit(2);}});
