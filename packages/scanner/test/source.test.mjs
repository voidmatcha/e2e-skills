// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { sourceModel, MAX_SOURCE_BYTES } from '../src/source.mjs';
import { discoverAssertion, discoverPost } from '../src/check-candidates.mjs';

test('oversized source is rejected before parsing through every source entry point', () => {
  const bytes = Buffer.alloc(MAX_SOURCE_BYTES + 1, 32);
  for (const parse of [sourceModel, discoverAssertion, discoverPost]) {
    assert.throws(() => parse(bytes, 'oversized.ts'), /16 MiB parser limit/);
    assert.throws(() => parse('not bytes', 'invalid.ts'), /source must be bytes/);
  }
});

test('explicit assignment aliases invalidate shared objects only on property mutation', async () => {
  const { isWritten } = await import('../src/source.mjs');
  function written(body) {
    const { source, checker } = sourceModel(Buffer.from('const original={};' + body), 'alias.ts');
    const symbol = checker.getSymbolAtLocation(source.statements[0].declarationList.declarations[0].name);
    return isWritten(source, checker, symbol, { properties: true });
  }
  for (const body of [
    'let alias;alias=original;alias.locator=custom;',
    'let alias;alias=original;let next;next=alias;delete next.locator;',
    'let alias;alias=original;Object.assign(alias,{locator:custom});',
    'let alias;alias=original;Reflect.set(alias,"locator",custom);',
  ]) assert.equal(written(body), true, body);
  for (const body of [
    'let alias;alias=original;', 'let alias;alias=original;alias=custom;',
    'let alias;alias=original;[alias]=custom;',
    'let alias;alias=original;function f(alias){alias.locator=custom;}',
    'function f(original){let alias;alias=original;alias.locator=custom;}',
  ]) assert.equal(written(body), false, body);
});

test('explicit Object/Reflect mutation invalidates target rather than unrelated source arguments', async () => {
  const { isWritten } = await import('../src/source.mjs');
  for (const statement of [
    'Object.assign(original,{locator:custom});',
    'Object.defineProperty(original,"locator",{value:custom});',
    'Object.defineProperties(original,{locator:{value:custom}});',
    'Object.setPrototypeOf(original,custom);',
    'Reflect.set(original,"locator",custom);',
    'Reflect.deleteProperty(original,"locator");',
    'Reflect.defineProperty(original,"locator",{value:custom});',
    'Reflect.setPrototypeOf(original,custom);',
    'Object["assign"](original,{locator:custom});',
    'function f(Object){Object.assign(original,custom);}',
  ]) {
    const { source, checker } = sourceModel(Buffer.from('const original={};const other={};' + statement), 'mutation.ts');
    const original = checker.getSymbolAtLocation(source.statements[0].declarationList.declarations[0].name);
    const other = checker.getSymbolAtLocation(source.statements[1].declarationList.declarations[0].name);
    assert.equal(isWritten(source, checker, original, { properties: true }), true, statement);
    assert.equal(isWritten(source, checker, other, { properties: true }), false, statement);
    assert.equal(isWritten(source, checker, original), false, 'property writes do not rebind the target');
  }
  for (const statement of ['Object.assign(other,original);','Object.assign(original);','Object.keys(original);','arbitrary(original);']) {
    const { source, checker } = sourceModel(Buffer.from('const original={};const other={};'+statement), 'no-mutation.ts');
    const symbol = checker.getSymbolAtLocation(source.statements[0].declarationList.declarations[0].name);
    assert.equal(isWritten(source, checker, symbol, { properties: true }), false, statement);
  }
});

test('#4f canaries cannot confirm Page identity after assignment-alias or Object.assign mutation', async () => {
  const { assertions } = await import('../src/assertions.mjs');
  const { createScope } = await import('../src/scope.mjs');
  const { createHash } = await import('node:crypto');
  function check(body) {
    const filename = '/pinned-project/canary.spec.ts';
    const bytes = Buffer.from("import {test,expect} from '@playwright/test';test('x',async({page})=>{" + body +
      "expect(page.locator('a')).toBeTruthy();});");
    const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
      root: { canonical: '/pinned-project', requested: '/pinned-project', kind: 'directory' },
      candidates: [{ path: filename, identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
    const scope = createScope({ manifest, sources: new Map([[filename, bytes]]) });
    return assertions(bytes, filename, { scope });
  }
  for (const body of ['let alias;alias=page;alias.locator=()=>null;', 'Object.assign(page,{locator:()=>null});']) {
    const result = check(body);
    assert.deepEqual(result.findings.filter(f => f.patternId === '#4f'), [], body);
    assert.ok(result.diagnostics.length, body);
  }
  const control = check('let alias;alias=page;alias=custom;');
  assert.deepEqual(control.diagnostics, []);
  assert.equal(control.findings.filter(f => f.patternId === '#4f').length, 1);
});
