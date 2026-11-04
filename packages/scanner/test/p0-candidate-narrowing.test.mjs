// SPDX-License-Identifier: Apache-2.0
// #4a and #5a P0 candidates that are provably not the defect: a search result
// that can be -1, a gate fixed by the test's own literal data, and an
// assertion-free visibility branch. True positives stay candidates.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { assertions } from '../src/assertions.mjs';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';

const head = "import { test, expect, type Page } from '@playwright/test';\n";
function run(detector, text) {
  const filename = '/pinned/case.spec.ts', bytes = Buffer.from(head + text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  const result = detector(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
  return { ...result, hits: result.findings.filter(f => ['#4a', '#5a'].includes(f.patternId)).map(f => [f.patternId, f.line, f.variant ?? null]) };
}
const spec = body => `test('t', async ({ page }) => {\n${body}\n});\n`;

test('#4a skips a built-in search result on plain data and keeps count/length >= 0', () => {
  for (const search of ["labels.indexOf('Mon')", "labels.findIndex(l => l === 'Mon')", "labels.join(',').search(/Mon/)", "labels.lastIndexOf('Mon')"]) {
    const result = run(assertions, spec(`const labels = await page.locator('.day').allTextContents();\nconst idx = ${search};\nexpect(idx).toBeGreaterThanOrEqual(0);`));
    assert.deepEqual(result.hits, [], search);
  }
  // A matcher argument only reads the binding; a custom-matcher file or a
  // non-matcher call keeps it unproven, so the #4a candidate stays.
  const matcherUse = "const pressed = await page.locator('.day').evaluateAll(bs => bs.map(b => b.getAttribute('aria-pressed')));\n" +
    "const idx = pressed.indexOf('false');\nexpect(idx).toBeGreaterThanOrEqual(0);\n";
  assert.deepEqual(run(assertions, spec(matcherUse + "expect(await page.locator('.day').count()).toBe(1);\nexpect(['x']).toEqual(pressed);\nawait expect(page.locator('.day')).not.toHaveText(pressed as string[]);")).hits.filter(h => h[1] === 5), []);
  for (const use of ["expect.extend({ toEqual() { return { pass: true, message: () => '' }; } });\nexpect(['x']).toEqual(pressed);", "expect(['x']).custom(pressed);", "record(pressed);"])
    assert.ok(run(assertions, spec(matcherUse + use)).hits.some(h => h[1] === 5), use);
  const kept = run(assertions, spec("expect(await page.locator('.day').count()).toBeGreaterThanOrEqual(0);\n" +
    "const labels = await page.locator('.day').allTextContents();\nexpect(labels.length).toBeGreaterThanOrEqual(0);\n" +
    "expect(custom.indexOf('x')).toBeGreaterThanOrEqual(0);\nlet idx = labels.indexOf('x'); idx = 1;\nexpect(idx).toBeGreaterThanOrEqual(0);"));
  assert.deepEqual(kept.hits.map(h => h[1]), [3, 5, 6, 8]);
});

test('#5a skips gates fixed by literal loop constants or literal helper arguments that run at least once', () => {
  const loop = run(conditionalAssertions, spec("for (const n of [4, 5, 6]) {\n  if (n < 6) await expect(page.getByTestId('low')).toHaveText('2');\n}"));
  assert.deepEqual(loop.hits, []);
  const helper = run(conditionalAssertions, "async function stats(page: Page, total: string, low?: string) {\n" +
    "  await expect(page.getByTestId('total')).toHaveText(total);\n  if (low !== undefined) await expect(page.getByTestId('low')).toHaveText(low);\n}\n" +
    spec("await stats(page, '3', '1');\nawait stats(page, '4');"));
  assert.deepEqual(helper.hits, []);
  // Always-false gates, app-state arguments, escaped helpers and app-state
  // conditions keep the P0 candidate.
  for (const [label, text, line] of [
    ['never true', spec("for (const n of [1, 2]) {\n  if (n > 5) await expect(page.getByTestId('low')).toHaveText('2');\n}"), 4],
    ['app-state argument', "async function stats(page: Page, low?: string | null) {\n  if (low) await expect(page.getByTestId('low')).toHaveText(low);\n}\n" +
      spec("await stats(page, await page.getByTestId('seed').textContent());"), 3],
    ['exported helper', "export async function stats(page: Page, low?: string) {\n  if (low) await expect(page.getByTestId('low')).toHaveText(low);\n}\n" +
      spec("await stats(page, '1');"), 3],
    ['outer parameter in a nested callback', "async function stats(page: Page, low?: string) {\n  await page.waitForTimeout(1).then(async () => { if (low) await expect(page.getByTestId('low')).toHaveText(low); });\n}\n" +
      spec("await stats(page, '1');"), 3],
    ['loop over a named array', spec("const values = [4, 5];\nfor (const n of values) {\n  if (n < 6) await expect(page.getByTestId('low')).toHaveText('2');\n}"), 5],
    ['app state', spec("if (await page.getByRole('alert').isVisible()) await expect(page.getByRole('alert')).toHaveText('Saved');"), 3],
  ]) assert.ok(run(conditionalAssertions, text).hits.some(h => h[1] === line), label);
});

test('#5a inline visibility gate is a candidate only when it gates an assertion', () => {
  const action = run(conditionalAssertions, spec("const alertBox = page.getByRole('alert');\n" +
    "if (await alertBox.isVisible()) await page.getByRole('button', { name: 'Dismiss', exact: true }).click();\n" +
    "await expect(page.getByTestId('total')).toHaveText('3');"));
  assert.deepEqual(action.hits, []);
  const asserting = run(conditionalAssertions, spec("if (await page.getByRole('alert').isVisible()) await expect(page.getByRole('alert')).toHaveText('Saved');"));
  assert.deepEqual(asserting.hits.map(h => h[2]).sort(), ['conditional-assertion', 'inline-visibility-condition']);
});

test('#4a skips the x/y of a proven Locator boundingBox, which is negative off-screen', () => {
  // Round 7: four field false positives were viewport checks on box.x / box.y.
  const box = run(assertions, spec("const dialog = page.getByRole('dialog');\nconst bounds = await dialog.boundingBox();\n" +
    "expect(bounds!.x).toBeGreaterThanOrEqual(0);\nexpect(bounds?.y).toBeGreaterThanOrEqual(0);"));
  assert.deepEqual(box.hits, []);
  // Width/height cannot be negative; an unproven owner, a reassigned box or
  // a modifier keeps the candidate.
  const kept = run(assertions, spec("const bounds = await page.getByRole('dialog').boundingBox();\nexpect(bounds!.width).toBeGreaterThanOrEqual(0);\n" +
    "const other = await custom.boundingBox();\nexpect(other!.x).toBeGreaterThanOrEqual(0);\n" +
    "let moved = await page.getByRole('dialog').boundingBox(); moved = { x: 1, y: 1 };\nexpect(moved.x).toBeGreaterThanOrEqual(0);\n" +
    "expect(bounds!.x).not.toBeGreaterThanOrEqual(0);"));
  assert.deepEqual(kept.hits.map(h => h[1]), [4, 6, 8, 9]);
});
