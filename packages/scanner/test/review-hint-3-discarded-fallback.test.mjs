// SPDX-License-Identifier: Apache-2.0
// #3 review hint: `await x.act().catch(() => undefined);` whose result nothing
// reads, on a call that is not a state check, wait, count or matcher. Every
// other #3 shape, and every swallowed wait, keeps its existing tier.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { createScope } from '../src/scope.mjs';
import { catchHandlers } from '../src/catch-handlers.mjs';

function run(lines) {
  const filename = '/pinned-project/example.spec.ts';
  const bytes = Buffer.from("import {test,expect} from '@playwright/test';\ntest('x', async ({page, request}) => {\n" + lines.join('\n') + '\n});\n');
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [], root: { canonical: '/pinned-project', kind: 'directory' },
    candidates: [{ path: filename, identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return catchHandlers(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const rows = result => result.findings.map(f => [f.line, f.severity, f.reviewHint?.rule ?? null]);

test('#3 discarded undefined fallback on a non-check call is a review hint (sweep-200 / random-60 FP shapes)', () => {
  const result = run([
    "await page.getByRole('button', { name: 'Close' }).click().catch(() => undefined);", // 3
    'await context.close().catch(() => undefined);',                                     // 4
    'await api.deleteTask(taskId).catch(() => undefined);',                              // 5 kandev cleanup
    'await apiClient.rawRequest("DELETE", path).catch(() => undefined);',                // 6
    "await route.abort('failed').catch(() => undefined);",                              // 7
    'void page.screenshot({ path: file }).catch(() => undefined);',                     // 8
    'await (page.keyboard.press("Escape").catch(() => undefined));',                    // 9
    'await handle.dispose().catch(() => undefined);',                                   // 10
  ]);
  assert.deepEqual(rows(result), [3, 4, 5, 6, 7, 8, 9, 10].map(line => [line, 'P2', 'discarded-fallback']));
  assert.ok(result.findings.every(f => f.patternId === '#3' && f.disposition === 'candidate' && f.variant === 'fallback'));
});

test('#3 true-positive and adjacent shapes keep P0', () => {
  const result = run([
    "await page.getByRole('button').click().catch(() => {});",                     // 3 empty body (random-60 TP shape)
    "const visible = await page.getByText('a').isVisible().catch(() => false);",   // 4 state probe
    "await page.getByText('a').isVisible().catch(() => undefined);",              // 5 state probe
    'const n = await rows.count().catch(() => undefined);',                         // 6 count, stored
    'await rows.count().catch(() => undefined);',                                   // 7 count
    "await expect(page.getByText('a')).toBeVisible().catch(() => undefined);",    // 8 matcher
    'await expect(async () => { expect(1).toBe(1); }).toPass().catch(() => undefined);', // 9 toPass
    "await expect.poll(() => read()).toBe(1).catch(() => undefined);",            // 10 matcher on poll
    "await test.step('s', async () => { expect(1).toBe(1); }).catch(() => undefined);", // 11 step callback
    'await po.verifySaved().catch(() => undefined);',                               // 12 assertion-named helper
    'await po.expectSaved().catch(() => undefined);',                               // 13
    'await Promise.all([a(), b()]).catch(() => undefined);',                        // 14 combinator
    'await doThing().then(check).catch(() => undefined);',                          // 15 then
    'const body = await response.json().catch(() => undefined);',                   // 16 stored
    'return await save().catch(() => undefined);',                                  // 17 returned
    'await savePromise.catch(() => undefined);',                                    // 18 not a direct call
    'await save().catch(() => null);',                                              // 19 other fallback
    "await page.getByRole('row').click().catch(() => cleanup());",                 // 20 executable fallback
  ]);
  assert.deepEqual(rows(result), [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20].map(line => [line, 'P0', null]));
});

test('#3 swallowed waits are left to the wait-timeout triage, never a discarded-fallback hint', () => {
  const result = run([
    "await page.waitForURL('**/done').catch(() => undefined);",                   // 3
    "await page.getByText('a').waitFor({ timeout: 2000 }).catch(() => undefined);", // 4
    "await page.waitForResponse('**/api').catch(() => undefined);",               // 5
    "await page.goto('/').catch(() => undefined);",                                 // 6
    "await page.waitForRequest('**/x', { timeout: 15000 }).catch(() => undefined);", // 7
    'await page.waitForTimeout(100).catch(() => undefined);',                       // 8
  ]);
  assert.equal(result.findings.length, 6);
  assert.ok(result.findings.every(f => !f.reviewHint), JSON.stringify(rows(result)));
  assert.ok(result.findings.filter(f => f.line !== 8).every(f => f.triage?.shape === 'swallowed-wait'));
});
