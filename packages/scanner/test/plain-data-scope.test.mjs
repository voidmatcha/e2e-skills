// SPDX-License-Identifier: Apache-2.0
// Plain-data "never a Locator" proofs for assertion subjects, and files of an
// out-of-scope runner that are listed, not analysed or counted incomplete.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function scan(t, files, args = ['--format', 'json']) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-plain-data-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0', '--allow-incomplete', ...args],
    { encoding: 'utf8', timeout: 60_000 });
  if (args.includes('text')) return { text: result.stdout };
  const report = JSON.parse(result.stdout);
  return { report, root, gaps: report.execution.diagnostics.map(item => [path.relative(root, item.file ?? ''), item.detector, item.line]) };
}
const lines = (gaps, detector) => gaps.filter(gap => gap[1] === detector).map(gap => gap[2]).sort((a, b) => a - b);

// Line numbers below are load-bearing.
const DATA = `import { test, expect, request as apiRequest } from '@playwright/test';
test('reads', async ({ page }) => {
  const loc = page.locator('a');
  const [box, text] = await Promise.all([loc.boundingBox(), loc.textContent()]);
  expect(box).not.toBeNull();
  expect(text).toBeTruthy();
  expect(page.viewportSize()).not.toBeNull();
  const u = new URL(page.url());
  expect(u.searchParams.get('x')).not.toBeNull();
});
test('responses', async ({ request, page }) => {
  const res = await request.post('/x');
  expect(res.ok()).toBeTruthy();
  expect(res.status()).toBeTruthy();
  expect(res).toBeTruthy();
  const own = await page.request.get('/x');
  expect(own.ok()).toBeTruthy();
  const ctx = await apiRequest.newContext();
  const other = await ctx.get('/x');
  expect(other.ok()).toBeTruthy();
});
`;
test('Promise.all reads, responses, viewport and URL data are proven non-Locators', t => {
  const { gaps } = scan(t, { 'tests/data.spec.ts': DATA });
  assert.deepEqual(lines(gaps, 'assertions'), [], JSON.stringify(gaps));
});

const UNPROVEN = `import { test, expect } from '@playwright/test';
test('locators', async ({ page }) => {
  const [handle] = await Promise.all([page.locator('x')]);
  expect(handle).toBeTruthy();
  const all = await page.locator('a').all();
  expect(all.find(item => item)).toBeTruthy();
});
async function check(request: any) {
  const res = await request.get('/x');
  expect(res.ok()).toBeTruthy();
}
test('reassigned', async ({ request }) => {
  let res = await request.get('/x');
  res = await request.get('/y');
  expect(res.ok()).toBeTruthy();
  await check(request);
});
`;
test('Locator elements, unproven request sources and reassigned responses stay unresolved', t => {
  const { gaps } = scan(t, { 'tests/unproven.spec.ts': UNPROVEN });
  assert.deepEqual(lines(gaps, 'assertions'), [4, 6, 10, 15], JSON.stringify(gaps));
});

test('a request fixture replaced by test.use stays unresolved', t => {
  const text = "import { test, expect } from '@playwright/test';\ntest.use({ request: makeRequest() } as any);\n" +
    "test('x', async ({ request }) => {\n  const res = await request.get('/x');\n  expect(res.ok()).toBeTruthy();\n});\n";
  const { gaps } = scan(t, { 'tests/use.spec.ts': text });
  assert.deepEqual(lines(gaps, 'assertions'), [5], JSON.stringify(gaps));
});

const RUNNER = "import { NightwatchBrowser } from 'nightwatch'\nmodule.exports = { x: function (browser: NightwatchBrowser) { browser.click('#a').waitForElementVisible('#b', 0) } }\n";
test('files of an out-of-scope runner are listed and not analysed; mixed files are analysed', t => {
  const mixed = "import type { NightwatchBrowser } from 'nightwatch';\nimport { test, expect } from '@playwright/test';\n" +
    "test('x', async ({ page }) => {\n  if (await page.locator('a').isVisible()) {\n    await expect(page.locator('a')).toBeVisible();\n  }\n});\n";
  const { report, root, gaps } = scan(t, { 'tests/runner.test.ts': RUNNER, 'tests/mixed.spec.ts': mixed });
  assert.deepEqual(report.outOfScope.map(item => [path.relative(root, item.file), item.framework]), [['tests/runner.test.ts', 'nightwatch']]);
  assert.deepEqual(gaps.filter(gap => gap[0] === 'tests/runner.test.ts'), []);
  assert.ok(report.findings.some(item => path.relative(root, item.file) === 'tests/mixed.spec.ts' && item.patternId === '#5a'));
  const { text } = scan(t, { 'tests/runner.test.ts': RUNNER }, ['--format', 'text']);
  assert.match(text, /Out of scope: 1 file\(s\)/);
});
