// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {discoverPost,bindPost} from '../src/check-candidates.mjs';
const cli=fileURLToPath(new URL('../src/check-cli.mjs',import.meta.url));
const operator='omit-post-promise-chain-statement-v1';
const rootCall="fetch('/api/runtime', {method:'POST',body:JSON.stringify({query:'movies'})})";
const chain=rootCall+'.then(response=>response.json()).then(setFavoriteMovies)';
const source=body=>Buffer.from('function handleClick(){\n'+body+'\n}\n');
const find=body=>discoverPost(source(body),'app/routes/_index.tsx');
function fixture(callback){
 const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'check-post-chain-')));
 try {
  fs.mkdirSync(path.join(root,'app/routes'),{recursive:true});
  const rel='app/routes/_index.tsx';fs.writeFileSync(path.join(root,rel),source(chain));
  const candidate=discoverPost(source(chain),rel)[0];
  const binding={source:root,test_selector:'POST response updates movies',test_paths:['tests/runtime.spec.ts'],
   promise:{path:'README.md',quote:'movies update',sha256:'reviewed'},test:{argv:['never-run-test']},
   observer:{argv:['never-run-observer']},report:{format:'playwright-json',path:'native.json'},expected_failure:{contains:'movies'}};
  const json=(name,value)=>{const file=path.join(root,name);fs.writeFileSync(file,JSON.stringify(value));return file;};
  const run=(...args)=>spawnSync(process.execPath,[cli,...args],{encoding:'utf8',timeout:20000});
  callback({root,rel,candidate,binding,json,run});
 }finally{fs.rmSync(root,{recursive:true,force:true});}
}
test('one to three direct then calls omit the entire unique POST chain and callbacks',()=>{
 for(let count=1;count<=3;count++){
  const expression=rootCall+'.then(callback)'.repeat(count)+';';const [c]=find(expression);
  assert.equal(c.operator,operator);assert.equal(c.endpoint,'/api/runtime');assert.equal(c.line,2);
  assert.equal(c.before,expression);assert.equal(c.after,'void 0;');assert.match(c.claim,/request and all then callbacks/);
  const text=source(expression).toString();assert.equal(text.slice(c.range.utf16_start,c.range.utf16_end),expression);
  assert.equal(source(expression).subarray(c.range.byte_start,c.range.byte_end).toString(),expression);
 }
 const [c]=find(chain);assert.equal(c.before,chain);assert.ok(c.before.includes('.then(setFavoriteMovies)'));
});
test('consumed, optional, computed, aliased, extended and dynamic forms are not chain candidates',()=>{
 for(const body of [
  'await '+chain,'const result='+chain,'return '+chain,'void '+chain,'('+chain+')',
  chain.replace('fetch(','fetch?.('),chain.replace('.then(','.then?.('),chain.replace('.then(',"['then']("),
  chain+'.then(next).then(last)',rootCall+'.catch(onError)',chain+'.finally(cleanup)',
  rootCall+'.then(makeCallback())',rootCall+'.then(ok,fail)',rootCall+'.then(...callbacks)',
  rootCall+'.then()',chain.replace("'POST'","'GET'"),chain.replace("'POST'",'method'),
  chain.replace("'/api/runtime'",'endpoint'),chain.replace("'/api/runtime'","'https://example.com/api'"),
  chain.replace("method:'POST'","...options,method:'POST'"),chain.replace("method:'POST'","method:'POST',method:'GET'"),
  'const fetch=custom;'+chain,'function other(fetch){}\n'+chain,"import {fetch} from 'other';\n"+chain,
  'const request=fetch;'+chain.replace('fetch(','request('),chain.replace('fetch(','globalThis.fetch('),
  chain+';\n'+chain+';','// '+chain+'\nconst x='+JSON.stringify(chain),
 ]) assert.deepEqual(find(body),[],body);
});
test('awaited operator bytes and replacement remain unchanged and bare nonawaited POST remains unsupported',()=>{
 const expression='await '+rootCall;const [c]=find(expression+';');
 assert.equal(c.operator,'omit-awaited-post-statement-v1');assert.equal(c.before,expression);
 assert.equal(c.after,'await Promise.resolve(undefined)');assert.deepEqual(find(rootCall+';'),[]);
});
test('chain binder requires independent observer and test paths and rejects altered/source-drifted candidates',()=>fixture(({root,rel,candidate,binding})=>{
 const plan=bindPost(candidate,binding);assert.equal(plan.mode,'behavior-fault');
 assert.deepEqual(plan.observer,binding.observer);assert.deepEqual(plan.test_paths,binding.test_paths);
 assert.deepEqual(plan.edits,[{path:rel,sha256:candidate.source_sha256,before:chain,after:'void 0;',kind:'source'}]);
 assert.throws(()=>bindPost(candidate,{...binding,observer:null}),/observer/);
 assert.throws(()=>bindPost(candidate,{...binding,test_paths:[rel]}),/must not be a test/);
 assert.throws(()=>bindPost({...candidate,after:'bad'},binding),/candidate changed/);
 fs.appendFileSync(path.join(root,rel),'// drift\n');assert.throws(()=>bindPost(candidate,binding),/source drifted/);
}));
test('CLI discovers and binds the new operator without running test or observer',()=>fixture(({root,rel,candidate,binding,json,run})=>{
 const discover=run('discover','post',root,rel);assert.equal(discover.status,0,discover.stderr);assert.deepEqual(JSON.parse(discover.stdout),[candidate]);
 const candidateFile=json('candidate.json',candidate);
 const bind=run('bind',candidateFile,json('binding.json',binding));assert.equal(bind.status,0,bind.stderr);
 assert.deepEqual(JSON.parse(bind.stdout),bindPost(candidate,binding));
 const missing=run('bind',candidateFile,json('missing.json',{source:root}));assert.equal(missing.status,2,missing.stderr);
 const result=JSON.parse(missing.stdout);assert.equal(result.status,'NEEDS_INPUT');assert.equal(result.operator,operator);
 assert.deepEqual(result.requirements.map(item=>item.field),['test_selector','test_paths','promise','test','observer','report','expected_failure']);
 const bad=run('bind',candidateFile,json('bad.json',{source:root,test_paths:[rel]}));assert.equal(bad.status,2);assert.match(bad.stderr,/invalid POST test_paths/);
}));
