// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadParser } from './candidate.mjs';
import { discoverPost, bindPost } from './post-candidate.mjs';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const parser=loadParser(process.env.TARGETED_CHECK_TYPESCRIPT);
const statement="await fetch('/api/like', {method:'POST', body: JSON.stringify({liked:true})})";
const find=body=>discoverPost(Buffer.from('async function likeArticle() {\n'+body+';\n}'), 'client.js', parser);
test('standalone awaited literal POST has exact unique source edit',()=>{const [c]=find(statement);assert.equal(c.before,statement);assert.equal(c.after,'await Promise.resolve(undefined)');assert.equal(c.endpoint,'/api/like');assert.equal(c.line,2);});
test('reject dynamic method/path, GET, spreads, duplicate method and consumed result',()=>{
  for(const expression of [statement.replace("'POST'",'method'),statement.replace("'/api/like'",'endpoint'),statement.replace("'POST'","'GET'"),statement.replace("method:'POST'","...options, method:'POST'"),statement.replace("method:'POST'","method:'POST',method:'GET'"),'const response = '+statement,statement.replace("'/api/like'","'https://example.com/api/like'")]) assert.deepEqual(find(expression),[],expression);
});
test('reject comment/string matches, duplicate exact statements, shadowed and optional fetch',()=>{
  for(const body of ['// '+statement+'\nconst text='+JSON.stringify(statement),statement+';\n'+statement,'const fetch=custom;\n'+statement,statement.replace('fetch(','fetch?.(')]) assert.deepEqual(find(body),[],body);
});

test('behavior binding requires observer, excludes test edits and rejects source drift',()=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'targeted-post-'));
  const bytes=Buffer.from('async function save() { '+statement+'; }');
  fs.writeFileSync(path.join(root,'client.js'),bytes);
  const candidate=discoverPost(bytes,'client.js',parser)[0];
  const binding={source:root,test_selector:'strong write',test_paths:['strong.spec.mjs'],promise:{path:'README.md',quote:'persist',sha256:'manual'},test:{argv:['node','run.mjs'],source:{path:'run.mjs',sha256:'manual'}},observer:{argv:['node','observer.mjs'],source:{path:'observer.mjs',sha256:'manual'}},report:{format:'playwright-json',path:'native.json'},expected_failure:{contains:'toBe',location:'strong.spec.mjs:10'}};
  assert.equal(bindPost(candidate,binding,parser).mode,'behavior-fault');
  assert.deepEqual(bindPost(candidate,binding,parser).observer,binding.observer);
  assert.throws(()=>bindPost(candidate,{...binding,observer:null},parser),/observer/);
  assert.throws(()=>bindPost(candidate,{...binding,test_paths:['client.js']},parser),/must not be a test/);
  assert.throws(()=>bindPost({...candidate,after:'bad'},binding,parser),/candidate changed/);
  fs.appendFileSync(path.join(root,'client.js'),'\n// drift');
  assert.throws(()=>bindPost(candidate,binding,parser),/source drifted/);
});
