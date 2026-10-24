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

test('catch clauses, control flow and unsupported cleanup syntax retain diagnostics', () => {
  for (const tail of [
    'catch {} finally { stop(); }',
    'finally { await stop(); }',
    'finally { if (ready) stop(); }',
    'finally { stop(); other(); }',
    'finally { stop?.(); }',
    'finally { server["stop"](); }',
    'finally { (async () => { await stop(); })(); }',
    'finally { label: { break label; } }',
    'finally { while (ready) { continue; } }',
  ]) {
    const result = run(scenario(`try { ${navigation} ${assertion} } ${tail}`));
    assert.deepEqual(result.findings, [], tail);
    assert.ok(result.diagnostics.some(diagnostic => diagnostic.message.includes('finally')), tail);
  }
});

test('cleanup exemption retains framework registration and direct callback boundaries', () => {
  for (const [body, prefix] of [
    [`other('navigation', async ({page}) => { try { ${navigation} } finally { stop(); } });`, header],
    [scenario(`async function nested() { try { ${navigation} } finally { stop(); } }`), header],
    [scenario(`try { ${navigation} } finally { stop(); }`), "import {test} from '@workspace/fixtures';\n"],
    [`test=other; ${scenario(`try { ${navigation} } finally { stop(); }`)}`, header],
  ]) {
    const result = run(body, prefix);
    assert.deepEqual(result.findings, [], body);
    assert.ok(result.diagnostics.length, body);
  }
});
