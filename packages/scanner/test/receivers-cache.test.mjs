// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { createReceivers } from '../src/receivers.mjs';
import { walk, ts } from '../src/source.mjs';

function pinned(text) {
  const filename='/pinned/case.ts', bytes=Buffer.from(text);
  const manifest={schema:'node-candidate-inventory-v1',complete:true,errors:[],
    root:{canonical:'/pinned',kind:'directory'},candidates:[{path:filename,
      identity:{size:String(bytes.length),sha256:createHash('sha256').update(bytes).digest('hex')}}]};
  const scope=createScope({manifest,sources:new Map([[filename,bytes]])});
  let queries=0;
  const counted={...scope,expression(...args){queries++;return scope.expression(...args);}};
  const receivers=createReceivers(bytes,filename,{scope:counted});
  const statements=[];
  walk(receivers.source,node=>{if(ts.isExpressionStatement(node)) statements.push(node.expression);});
  return {...receivers,statements,queries:()=>queries};
}

test('repeated literal member queries resolve once per lexical binding and path', () => {
  const r=pinned("import * as pw from '@playwright/test';\n"+'pw.expect;\n'.repeat(1000)+'pw.test;\npw.expect;');
  for(const node of r.statements.slice(0,1000)) assert.equal(r.expression(node).kind,'expect');
  assert.equal(r.queries(),1,'same source binding/path must not repeat pinned provenance lookup');
  assert.equal(r.expression(r.statements[1000]).kind,'none');
  assert.equal(r.queries(),2,'different member paths must not share results');
  assert.equal(r.expression(r.statements[1001]).kind,'expect');
  assert.equal(r.queries(),2);
});

test('same spelling in a shadow scope and a fresh snapshot does not reuse identity', () => {
  const r=pinned("import * as pw from '@playwright/test';pw.expect;function f(pw){pw.expect;}pw.expect;");
  assert.deepEqual(r.statements.map(n=>r.expression(n).kind),['expect','none','expect']);
  const changed=pinned('const pw={expect:custom};pw.expect;');
  assert.notEqual(changed.expression(changed.statements[0]).kind,'expect');
});

test('unknown provenance and mutated bindings keep their reasons without leaking mutable result objects', () => {
  const r=pinned("import {expect as verify} from './missing';verify;verify;");
  const first=r.expression(r.statements[0]);
  assert.equal(first.complete,false);
  const expected=structuredClone(first);
  first.kind='expect';first.reasons.length=0;
  assert.deepEqual(r.expression(r.statements[1]),expected);
  assert.equal(r.queries(),1);
  const changed=pinned("import {expect as verify} from '@playwright/test';verify;verify.custom=custom;verify;");
  for(const node of [changed.statements[0],changed.statements.at(-1)])
    assert.deepEqual(changed.expression(node),{kind:'unknown',complete:false,reasons:['mutable receiver binding']});
});

test('computed, optional and unbound queries retain their original resolution path', () => {
  const r=pinned("import * as pw from '@playwright/test';pw['expect'];pw['expect'];pw?.expect;pw?.expect;unbound;unbound;");
  for(const node of r.statements) r.expression(node);
  assert.equal(r.queries(),6,'non-keyed expressions must not borrow a static binding/path result');
});

test('outer query caching cannot bypass depth or cyclic receiver guards', () => {
  let text="import {expect} from '@playwright/test';const a0=expect;";
  for(let n=1;n<=70;n++) text+=`const a${n}=a${n-1};`;
  text+='a0;a70;a0;a70;';
  const r=pinned(text);
  assert.equal(r.expression(r.statements[0]).kind,'expect');
  const deep=r.expression(r.statements[1]);
  assert.equal(deep.complete,false);
  assert.match(deep.reasons.join(';'),/excessive|depth/);
  assert.equal(r.expression(r.statements[2]).kind,'expect');
  assert.deepEqual(r.expression(r.statements[3]),deep);
  const cyclic=pinned('const a=b;const b=a;a;b;a;');
  for(const node of cyclic.statements) {
    const result=cyclic.expression(node);
    assert.equal(result.complete,false);
    assert.match(result.reasons.join(';'),/cyclic/);
  }
});
