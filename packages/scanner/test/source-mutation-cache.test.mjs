// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { sourceModel, isWritten } from '../src/source.mjs';

function model(text) {
  const result = sourceModel(Buffer.from(text), '/pinned/reused.ts');
  const symbol = result.checker.getSymbolAtLocation(result.source.statements[0].declarationList.declarations[0].name);
  return { ...result, symbol };
}

test('repeated mutation queries reuse the completed scan, including a false result', () => {
  for (const tail of ['', 'const alias=original;alias.value=1;']) {
    const {source, checker, symbol} = model('const original={};let unrelated;unrelated=1;' + tail);
    let lookups = 0;
    const countingChecker = new Proxy(checker, {get(target, key) {
      if (key === 'getSymbolAtLocation') return node => {lookups++; return target.getSymbolAtLocation(node);};
      return Reflect.get(target, key);
    }});
    assert.equal(isWritten(source, countingChecker, symbol, {properties:true}), Boolean(tail));
    const first = lookups;
    assert.ok(first > 0);
    for (let n=0; n<1000; n++) assert.equal(isWritten(source, countingChecker, symbol, {properties:true}), Boolean(tail));
    assert.equal(lookups, first, 'repeated queries must not walk symbol references again');
    const secondChecker = new Proxy(checker, {get(target, key) {
      if (key === 'getSymbolAtLocation') return node => {lookups++; return target.getSymbolAtLocation(node);};
      return Reflect.get(target, key);
    }});
    assert.equal(isWritten(source, secondChecker, symbol, {properties:true}), Boolean(tail));
    assert.ok(lookups > first, 'another checker must perform its own query');
  }
});

test('mutation cache separates properties, propertyOnly, symbol and new source identities', () => {
  for (const tail of ['original=other;', 'const alias=original;alias.value=1;']) {
    const {source,checker,symbol} = model('let original={}; const other={};' + tail);
    const propertyWrite = tail.includes('.value');
    for (const options of [{}, {properties:true}, {properties:true,propertyOnly:true}, {propertyOnly:true}]) {
      const expected = options.properties ? (!options.propertyOnly || propertyWrite) : (!options.propertyOnly && !propertyWrite);
      assert.equal(isWritten(source,checker,symbol,options), expected, JSON.stringify(options)+tail);
    }
    const other = checker.getSymbolAtLocation(source.statements[1].declarationList.declarations[0].name);
    assert.equal(isWritten(source,checker,other,{properties:true}), false);
  }
  const clean = model('const original={};');
  const changed = model('const original={}; original.value=1;');
  assert.equal(isWritten(clean.source,clean.checker,clean.symbol,{properties:true}),false);
  assert.equal(isWritten(changed.source,changed.checker,changed.symbol,{properties:true}),true);
});
