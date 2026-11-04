// SPDX-License-Identifier: Apache-2.0
// Shapes from a field scan of public Playwright suites, as minimal
// reductions: trailing cleanup catches, re-verified waits, browser-side
// search results, polled invariants, data-row gates, self-checking gates,
// if/else assertions and an additive expect.extend.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { assertions } from '../src/assertions.mjs';
import { catchHandlers } from '../src/catch-handlers.mjs';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';

const head = "import { test, expect } from '@playwright/test';\n";
function run(detector, text, prefix = head) {
  const filename = '/pinned/case.spec.ts', bytes = Buffer.from(prefix + text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  const result = detector(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
  return { ...result, hits: result.findings.map(f => [f.patternId, f.line, f.disposition]) };
}
const spec = body => `test('t', async ({ page }) => {\n${body}\n});\n`;
const p0 = result => result.hits.filter(([id]) => ['#3', '#4a', '#5a'].includes(id));

test('#3 skips a trailing cleanup catch in a test finally block or an after hook', () => {
  const finallyTail = run(catchHandlers, spec("const app = page;\ntry {\n  await expect(page.getByRole('main')).toBeVisible();\n} finally {\n" +
    "  await app.close().catch(() => {});\n  await fetch('/api/reset').catch(() => undefined);\n}"));
  assert.deepEqual(p0(finallyTail), []);
  const hook = run(catchHandlers, "test.afterEach(async ({ page }) => {\n  await page.close().catch(() => {});\n});\n" + spec("await expect(page).toHaveTitle('x');"));
  assert.deepEqual(p0(hook), []);
  // An assertion after the swallowed operation, a swallowed assertion, or a
  // try that is not the last statement keeps the candidate.
  for (const [label, text, line] of [
    ['later assertion', spec("try {\n  await page.goto('/');\n} finally {\n  await page.reload().catch(() => {});\n  await expect(page).toHaveTitle('x');\n}"), 6],
    ['swallowed assertion', spec("try {\n  await page.goto('/');\n} finally {\n  await expect(page).toHaveTitle('x').catch(() => {});\n}"), 6],
    ['not the last statement', spec("try {\n  await page.goto('/');\n} finally {\n  await page.reload().catch(() => {});\n}\nawait page.goto('/b');"), 6],
    ['hook with a later assertion', "test.afterEach(async ({ page }) => {\n  await page.reload().catch(() => {});\n  await expect(page).toHaveTitle('x');\n});\n", 3],
  ]) assert.ok(p0(run(catchHandlers, text)).some(([, hit]) => hit === line), label);
});

test('#3 skips a swallowed wait that the next hard assertion re-checks on the same locator', () => {
  const same = run(catchHandlers, spec("const shell = page.getByTestId('loading');\nawait shell.waitFor({ state: 'hidden' }).catch(() => {});\n" +
    "await page.goto('/');\nawait expect(shell).toBeHidden();"));
  assert.deepEqual(p0(same), []);
  const other = run(catchHandlers, spec("const shell = page.getByTestId('loading');\nawait shell.waitFor({ state: 'hidden' }).catch(() => {});\n" +
    "await expect(page.getByRole('main')).toBeVisible();"));
  assert.deepEqual(p0(other).map(([id, line]) => [id, line]), [['#3', 4]]);
});

test('#4a skips an evaluateAll search result and flags a polled >= 0 invariant', () => {
  const search = run(assertions, spec("const options = page.getByRole('menuitemradio');\n" +
    "const index = await options.evaluateAll(items => items.findIndex(item => item.getAttribute('aria-checked') === 'true'));\n" +
    "expect(index).toBeGreaterThanOrEqual(0);"));
  assert.deepEqual(p0(search), []);
  const kept = run(assertions, spec("const options = page.getByRole('menuitemradio');\n" +
    "const count = await options.evaluateAll(items => items.length);\nexpect(count).toBeGreaterThanOrEqual(0);"));
  assert.deepEqual(p0(kept), [['#4a', 5, 'candidate']]);
  const poll = run(assertions, spec("await expect.poll(async () => page.getByRole('row').count(), { timeout: 180000 }).toBeGreaterThanOrEqual(0);"));
  assert.deepEqual(p0(poll), [['#4a', 3, 'candidate']]);
});

test('#5a skips data-row gates that run, if/else assertions and self-checking gates', () => {
  const rows = run(conditionalAssertions, "const VARIANTS = [{ skin: 'dark', width: 2 }, { skin: 'light', width: 1 }];\n" +
    spec("for (const variant of VARIANTS) {\n  if (variant.skin === 'dark') await expect(page.getByRole('main')).toHaveClass(/dark/);\n}"));
  assert.deepEqual(p0(rows), []);
  const passedRows = run(conditionalAssertions, "const CAPS = [{ browser: 'chrome' }, { browser: 'safari' }];\n" +
    "async function check(page: any, caps: { browser: string }) {\n  if (caps.browser === 'safari') await expect(page.getByRole('main')).toBeVisible();\n}\n" +
    spec("for (const caps of CAPS) await check(page, caps);"));
  assert.deepEqual(p0(passedRows), []);
  const bothBranches = run(conditionalAssertions, spec("const value = await page.getByLabel('A').inputValue();\n" +
    "if (value) await expect(page.getByRole('status')).toHaveText('set');\nelse await expect(page.getByRole('status')).toHaveText('empty');"));
  // An if/else that asserts on both paths is not a bypass (pattern-reference #5a).
  assert.deepEqual(p0(bothBranches), []);
  const self = run(conditionalAssertions, spec("const failed = (await page.locator('.error').allTextContents());\n" +
    "if (failed.length > 0) expect(failed).toHaveLength(0);\nif (failed.length) expect(failed.length).toBe(0);"));
  assert.deepEqual(p0(self), []);
  for (const [label, text, line] of [
    ['never-matching data row', "const VARIANTS = [{ skin: 'light' }];\n" + spec("for (const variant of VARIANTS) {\n  if (variant.skin === 'dark') await expect(page.getByRole('main')).toHaveClass(/dark/);\n}"), 5],
    ['mutated data rows', "const VARIANTS = [{ skin: 'dark' }];\nVARIANTS.push({ skin: 'x' });\n" + spec("for (const variant of VARIANTS) {\n  if (variant.skin === 'dark') await expect(page.getByRole('main')).toBeVisible();\n}"), 6],
    ['fixture discriminant', "test('t', async ({ page, browserName }) => {\n  if (browserName === 'webkit') await expect(page.getByRole('main')).toBeVisible();\n});\n", 3],
    ['different asserted value', spec("const failed = await page.locator('.error').allTextContents();\nif (failed.length > 0) expect(failed).toHaveLength(1);"), 4],
    ['app-state gate', spec("if (await page.getByRole('alert').isVisible()) await expect(page.getByRole('alert')).toHaveText('Saved');"), 3],
  ]) assert.ok(p0(run(conditionalAssertions, text)).some(([, hit]) => hit === line), label);
});

test('an additive expect.extend keeps Playwright expect provenance; a redefined built-in does not', () => {
  const additive = "import { test, expect as base } from '@playwright/test';\nconst expect = base.extend({\n  async toHavePath(page: any, path: string) { return { pass: true, message: () => path }; },\n});\n";
  const weak = run(assertions, spec("expect(page.getByRole('main')).toBeTruthy();"), additive);
  assert.deepEqual(weak.diagnostics, []);
  assert.deepEqual(weak.hits, [['#4f', 6, 'confirmed']]);
  const redefined = "import { test, expect as base } from '@playwright/test';\nconst expect = base.extend({\n  toBeTruthy() { return { pass: true, message: () => '' }; },\n});\n";
  const result = run(assertions, spec("expect(page.getByRole('main')).toBeTruthy();"), redefined);
  assert.deepEqual(result.hits, []);
  assert.ok(result.diagnostics.length);
});
