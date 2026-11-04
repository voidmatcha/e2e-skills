// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createScope } from '../src/scope.mjs';
import { createReceivers } from '../src/receivers.mjs';
import { accessibleNames } from '../src/accessible-names.mjs';
import { walk, ts } from '../src/source.mjs';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function scan(t, text) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-helper-provenance-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, 'tests'));
  fs.writeFileSync(path.join(root, 'tests', 'feature.spec.ts'), text);
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0'],
    { encoding: 'utf8', timeout: 30_000, env: { ...process.env, E2E_SMELL_FAIL_ON: 'p0' } });
  return { status: result.status, report: JSON.parse(result.stdout), stderr: result.stderr };
}
function pinned(text, filename = '/pinned/case.spec.ts') {
  const bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  const scope = createScope({ manifest, sources: new Map([[filename, bytes]]) });
  return { bytes, filename, scope, receivers: createReceivers(bytes, filename, { scope }) };
}
// Kind of the first `expect(<subject>)` argument in source order.
function subject(text, filename) {
  const { receivers } = pinned(text, filename);
  let node;
  walk(receivers.source, item => {
    if (!node && ts.isCallExpression(item) && ts.isIdentifier(item.expression) && item.expression.text === 'expect') node = item.arguments[0];
  });
  return receivers.expression(node);
}
const head = "import { test, expect, type Page } from '@playwright/test';\n";

test('same-file helpers called with the fixture Page resolve, so helper specs complete', t => {
  const clean = head +
    "const nameField = (page: Page) => page.getByLabel('Name');\n" +
    "function row(page: Page, name: string) { return page.locator('#list li').filter({ has: page.getByRole('heading', { name, exact: true }) }); }\n" +
    "function card(page: Page, title: string) {\n  const root = page.locator('.card');\n  return root.filter({ hasText: title });\n}\n" +
    "async function addItem(page: Page, name: string) { await nameField(page).fill(name); }\n" +
    "test('helper', async ({ page }) => {\n  await page.goto('/');\n  await addItem(page, 'a');\n" +
    "  await expect(row(page, 'a')).toBeVisible();\n  await expect(card(page, 'a')).toHaveCount(1);\n});\n";
  const { status, report } = scan(t, clean);
  assert.equal(status, 0, JSON.stringify(report.execution));
  assert.equal(report.execution.complete, true);
  assert.deepEqual(report.execution.diagnostics, []);
  assert.deepEqual(report.findings, []);
});

test('a weak assertion through a resolved helper is still a confirmed #4f finding', t => {
  for (const helper of [
    "function row(page: Page, name: string) { return page.locator('#list li').filter({ hasText: name }); }\n",
    "const row = (page: Page, name: string) => page.locator('#list li').filter({ hasText: name });\n"]) {
    const { status, report } = scan(t, head + helper +
      "test('tp', async ({ page }) => {\n  await page.goto('/');\n  expect(row(page, 'a')).toBeTruthy();\n});\n");
    assert.equal(status, 1, JSON.stringify(report.execution));
    assert.equal(report.execution.complete, true);
    assert.deepEqual(report.findings.map(f => [f.patternId, f.severity, f.disposition, f.line]), [['#4f', 'P0', 'confirmed', 5]]);
  }
});

test('helper parameters and results resolve only for closed, consistently called helpers', () => {
  const helper = "function row(page: Page) { return page.locator('li'); }\n";
  const call = "test('x', async ({ page }) => { expect(row(page)).toBeTruthy(); });\n";
  assert.equal(subject(head + helper + call).kind, 'locator');
  assert.equal(subject(head + "const row = function (page: Page) { return page.locator('li').first(); };\n" + call).kind, 'locator');
  // Escapes, exports, mixed or missing arguments, spreads, recursion, async
  // and value-less completions keep the previous unresolved result.
  for (const [label, text] of [
    ['exported', head + 'export ' + helper + call],
    ['escaped as a value', head + helper + call + 'const alias = row;\n'],
    ['shorthand escape', head + helper + 'export const helpers = { row };\n' + call],
    ['export specifier', head + helper + call + 'export { row };\n'],
    ['mixed arguments', head + helper + call + "test('y', async ({ page }) => { row(page.locator('x')); });\n"],
    ['unproven argument', head + helper + call + 'function other(p: Page) { row(p); }\n'],
    ['missing argument', head + "function row(page?: Page) { return page.locator('li'); }\n" + call + 'row();\n'],
    ['spread argument', head + helper + call + 'const args: [Page] = [] as any; row(...args);\n'],
    ['recursive', head + "function row(page: Page): any { return row(page); }\n" + call],
    ['async result', head + "async function row(page: Page) { return page.locator('li'); }\n" + call],
    ['bare return', head + "function row(page: Page) { if (page) return; return page.locator('li'); }\n" + call],
    ['fall-through', head + "function row(page: Page) { if (page) return page.locator('li'); }\n" + call],
    ['reassigned parameter', head + "function row(page: Page) { page = page; return page.locator('li'); }\n" + call],
    ['overloaded', head + "function row(page: Page): any;\nfunction row(page: Page) { return page.locator('li'); }\n" + call],
  ]) {
    const value = subject(text);
    assert.notEqual(value.kind, 'locator', label);
  }
  // Outside an ES module a top-level function may be a global other files call.
  const script = "const { test, expect } = require('@playwright/test');\nfunction row(page) { return page.locator('li'); }\n" +
    "test('x', async ({ page }) => { expect(row(page)).toBeTruthy(); });\n";
  assert.notEqual(subject(script, '/pinned/case.spec.js').kind, 'locator');
  assert.equal(subject(script.replace('row(page)).', "page.locator('li')).").replace('function row', 'function unused'),
    '/pinned/case.spec.js').kind, 'locator');
});

test('mutually recursive helpers terminate and stay unresolved', () => {
  const text = head + "function a(page: Page): any { return b(page); }\nfunction b(page: Page): any { return a(page); }\n" +
    "test('x', async ({ page }) => { expect(a(page)).toBeTruthy(); });\n";
  assert.notEqual(subject(text).kind, 'locator');
});

test('loop-variable names are Playwright #10c candidates without exact and excluded with it', () => {
  const run = text => { const { bytes, filename, scope } = pinned(head + text); return accessibleNames(bytes, filename, { scope }); };
  for (const loop of ["['A', 'B']", 'names', '[`A${x}`]']) {
    const result = run(`const names = ['A'];\ntest('x', async ({ page }) => {\nfor (const n of ${loop}) page.getByRole('heading', { name: n });\n});`);
    assert.deepEqual(result.diagnostics, [], loop);
    assert.deepEqual(result.findings.map(f => [f.patternId, f.disposition, f.line]), [['#10c', 'candidate', 4]], loop);
    const exact = run(`const names = ['A'];\ntest('x', async ({ page }) => {\nfor (const n of ${loop}) page.getByRole('heading', { name: n, exact: true });\n});`);
    assert.deepEqual(exact, { findings: [], diagnostics: [] }, loop);
  }
});
