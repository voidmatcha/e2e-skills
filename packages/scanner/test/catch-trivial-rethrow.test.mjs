// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { createScope } from '../src/scope.mjs';

function run(body) {
  const file = '/pinned/rethrow.spec.ts';
  const bytes = Buffer.from("import {test} from '@playwright/test';\n" + body);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [{ path: file,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return catchHandlers(bytes, file, { scope: createScope({ manifest, sources: new Map([[file, bytes]]) }) });
}
const propagation = result => result.diagnostics.filter(d => d.message === 'unsupported #3 try/catch propagation context');

test('ordinary and async helpers preserve a direct same-error rethrow', () => {
  for (const prefix of ['', 'async ']) {
    const result = run(`${prefix}function helper(){try{work();}catch(error){throw error;}}`);
    assert.deepEqual(result.findings, []);
    assert.deepEqual(result.diagnostics, []);
  }
});

test('nontrivial catches and generator helpers remain outside the exclusion', () => {
  for (const body of [
    'catch(error){throw other;}', 'catch({message}){throw message;}', 'catch{throw error;}',
    'catch(error){throw (error);}', 'catch(error){console.error(error);throw error;}',
    'catch(error){if(ready)throw error;}', 'catch(error){return;}',
    'catch(error){throw error;}finally{cleanup();}',
  ]) assert.equal(propagation(run(`function helper(){try{work();}${body}}`)).length, 1, body);
  for (const prefix of ['function*', 'async function*'])
    assert.equal(propagation(run(`${prefix} helper(){try{work();}catch(error){throw error;}}`)).length, 1);
});

test('outer swallowing and finally evidence survive an inner rethrow exclusion', () => {
  const caught = run('function helper(){try{try{work();}catch(inner){throw inner;}}catch(outer){}}');
  assert.equal(propagation(caught).length, 1);
  const final = run('function helper(){try{try{work();}catch(inner){throw inner;}}finally{return;}}');
  assert.equal(propagation(final).length, 0);
  assert.ok(final.diagnostics.some(d => d.message === 'unsupported #3 finally context'));
  const nested = run('function* outer(){function helper(){try{work();}catch(error){throw error;}}}');
  assert.deepEqual(nested.diagnostics, []);
});
