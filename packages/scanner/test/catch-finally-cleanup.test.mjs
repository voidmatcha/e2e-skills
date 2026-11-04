// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { createScope } from '../src/scope.mjs';

const header = "import {test,expect} from '@playwright/test';\n";
const assertion = "await expect(page.locator('#target')).toHaveText('Target');";
const navigation = "await page.goto('/'); await page.locator('a').click();";
const scenario = body => `test('navigation', async ({page}) => { ${body} });`;
function run(body, prefix = header) {
  const filename = '/pinned-project/cleanup.spec.ts', bytes = Buffer.from(prefix + body);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return catchHandlers(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}

test('single-fetch style cleanup preserves failures across a multi-statement try', () => {
  for (const cleanup of ['stop()', 'server.stop()']) {
    const result = run(scenario(`try { ${navigation} ${assertion}
      await page.locator('button').click(); ${assertion} } finally { ${cleanup}; }`));
    assert.deepEqual(result, { findings: [], diagnostics: [] }, cleanup);
  }
});

test('plain cleanup preserves pending errors and a cleanup throw still fails', async () => {
  const pending = new Error('assertion failed'), cleanupError = new Error('cleanup failed');
  for (const [stop, expected] of [[() => {}, pending], [() => { throw cleanupError; }, cleanupError]]) {
    await assert.rejects(async () => {
      try { await Promise.resolve(); throw pending; } finally { stop(); }
    }, error => error === expected);
  }
});

test('supported cleanup cannot hide a separate swallowed assertion candidate', () => {
  const result = run(scenario(`try { ${navigation} ${assertion} } finally { stop(); }
    try { ${assertion} } catch {}`));
  assert.deepEqual(result.findings.map(({ patternId, variant }) => [patternId, variant]),
    [['#3', 'try-empty-catch']]);
  assert.deepEqual(result.diagnostics, []);
});

test('finally return stays a candidate for a direct assertion and unresolved for larger try bodies', () => {
  const direct = run(scenario(`try { ${assertion} } finally { return stop(); }`));
  assert.deepEqual(direct.findings.map(finding => finding.variant), ['finally-return']);
  assert.deepEqual(direct.diagnostics, []);
  const multiple = run(scenario(`try { ${navigation} ${assertion} } finally { return stop(); }`));
  assert.deepEqual(multiple.findings, []);
  assert.ok(multiple.diagnostics.some(diagnostic => diagnostic.message.includes('finally')));
});

test('a finally that can complete abruptly keeps a diagnostic; a catch clause keeps its own', () => {
  for (const tail of [
    'finally { label: { break label; } }',
    'finally { while (ready) { continue; } }',
    'finally { if (ready) return; }',
  ]) {
    const result = run(scenario(`try { ${navigation} ${assertion} } ${tail}`));
    assert.deepEqual(result.findings, [], tail);
    assert.ok(result.diagnostics.some(diagnostic => diagnostic.message.includes('finally')), tail);
  }
  const caught = run(scenario(`try { ${navigation} ${assertion} } catch {} finally { stop(); }`));
  assert.deepEqual(caught.findings, []);
  assert.ok(caught.diagnostics.some(diagnostic => diagnostic.message.includes('try/catch')));
});

test('a finally with no return, break or continue rethrows the pending error and needs no diagnostic', () => {
  // Any statements may run; if they complete normally the original failure
  // still propagates, and a throw from them still fails the test.
  for (const tail of [
    'finally { await stop(); }',
    'finally { if (ready) stop(); }',
    'finally { stop(); other(); }',
    'finally { stop?.(); }',
    'finally { server["stop"](); }',
    'finally { (async () => { await stop(); })(); }',
    'finally { const cleanup = () => { return; }; cleanup(); }',
  ]) assert.deepEqual(run(scenario(`try { ${navigation} ${assertion} } ${tail}`)), { findings: [], diagnostics: [] }, tail);
});

test('a plain finally needs no framework registration; an abrupt one keeps its diagnostic anywhere', () => {
  for (const [body, prefix] of [
    [`other('navigation', async ({page}) => { try { ${navigation} } finally { stop(); } });`, header],
    [scenario(`async function nested() { try { ${navigation} } finally { stop(); } }`), header],
    [scenario(`try { ${navigation} } finally { stop(); }`), "import {test} from '@workspace/fixtures';\n"],
    [`test=other; ${scenario(`try { ${navigation} } finally { stop(); }`)}`, header],
  ]) {
    const result = run(body, prefix);
    assert.deepEqual(result.findings, [], body);
    assert.ok(!result.diagnostics.some(diagnostic => diagnostic.message.includes('finally')), body);
    // An abrupt finally stays unresolved (an unpinned test import is already).
    const abrupt = run(body.replace('finally { stop(); }', 'finally { if (ready) return; }'), prefix);
    assert.ok(abrupt.diagnostics.length, body);
  }
});

test('a caught error pushed to a local array that is later asserted empty is re-reported, not swallowed', () => {
  // Round 7: eighteen field false positives collected cleanup errors this way.
  const collect = (chain, after = 'expect(errors).toEqual([]);', before = '') => scenario(`const errors = [];${before}
    try { ${assertion} } finally {
      await page.request.post('/reset')${chain};
      for (const error of errors) console.log(String(error));
    }
    ${after}`);
  for (const [chain, after] of [['.catch((error) => { errors.push(error); })', undefined],
    ['.then((r) => expect(r.ok()).toBe(true)).catch(error => errors.push(error))', 'expect(errors).toHaveLength(0);'],
    ['.catch(e => { errors.push(e); })', 'expect(errors).toStrictEqual([]);']]) {
    assert.deepEqual(run(collect(chain, after)).findings, [], chain);
  }
  // No later assertion, a non-empty or soft-skippable check, a return before
  // it, another use of the array, or a pushed value other than the error
  // keeps the #3 candidate.
  for (const [chain, after, before] of [['.catch(e => { errors.push(e); })', 'console.log(errors);'],
    ['.catch(e => { errors.push(e); })', "expect(errors).toEqual(['x']);"],
    ['.catch(e => { errors.push(e); })', 'if (flag) return; expect(errors).toEqual([]);'],
    ['.catch(e => { errors.push(e); })', 'errors.length = 0; expect(errors).toEqual([]);'],
    ['.catch(e => { errors.push(String(e)); })', 'expect(errors).toEqual([]);'],
    ['.catch(e => { errors.push(e); })', 'if (flag) { expect(errors).toEqual([]); }'],
    ['.catch(e => { errors.push(e); })', 'expect(errors).toEqual([]);', 'const other = errors;']]) {
    const result = run(collect(chain, after, before));
    assert.ok(result.findings.some(f => f.patternId === '#3'), `${chain} ${after} ${before ?? ''}`);
  }
  // Unawaited, the push can land after the assertion.
  assert.ok(run(scenario(`const errors = []; page.request.post('/reset').catch(e => { errors.push(e); }); expect(errors).toEqual([]);`))
    .findings.some(f => f.patternId === '#3'));
});
