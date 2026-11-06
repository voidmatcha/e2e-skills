// SPDX-License-Identifier: Apache-2.0
// Five ways a user object or a passing assertion became a confirmed P0, each
// from a minimal repro of an independent review, with a guard that keeps the
// proven shape confirmed. A wrong confirmation fails CI, so each case must
// end as a candidate, an unresolved analysis, or no finding.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function scan(t, files) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-confirmed-soundness-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0'],
    { encoding: 'utf8', timeout: 60_000, env: { ...process.env, E2E_SMELL_FAIL_ON: 'p0' } });
  const report = JSON.parse(result.stdout);
  return { exit: result.status, status: report.status,
    p0: report.findings.filter(item => item.severity === 'P0').map(item => [item.patternId, item.line, item.disposition]) };
}
const confirmed = result => result.p0.filter(item => item[2] === 'confirmed');
const COUNT_SPEC = (from, fixture = 'page') => `import { test, expect } from '${from}';
test('x', async ({ ${fixture} }) => {
  expect(await ${fixture}.locator('x').count()).toBeGreaterThanOrEqual(0);
});
`;
const FIXTURES = body => `import { test as base, expect } from '@playwright/test';\nexport const test = base.extend({ ${body} });\nexport { expect };\n`;

test('1: a wildcard paths alias that maps @playwright/test to a user module is not official Playwright', t => {
  const fake = 'export const test = (name: string, body: any) => body({ page: { locator: () => ({ count: async () => -1 }) } });\n' +
    'export const expect = (value: number) => ({ toBeGreaterThanOrEqual: (minimum: number) => { if (value < minimum) throw Error("negative"); } });\n';
  for (const tsconfig of ['{"compilerOptions":{"paths":{"*":["./fake/*"]}}}', '{"compilerOptions":{"baseUrl":"./fake"}}']) {
    const result = scan(t, { 'tsconfig.json': tsconfig, 'playwright.config.ts': 'export default {};\n',
      'fake/@playwright/test.ts': fake, 'x.spec.ts': COUNT_SPEC('@playwright/test') });
    assert.deepEqual(confirmed(result), [], tsconfig);
    assert.notEqual(result.exit, 1, tsconfig);
  }
  // Guard: a wildcard that finds no in-scope module leaves the official
  // package, so the proven count invariant stays confirmed.
  const official = scan(t, { 'tsconfig.json': '{"compilerOptions":{"paths":{"*":["./src/*"]}}}', 'playwright.config.ts': 'export default {};\n',
    'x.spec.ts': COUNT_SPEC('@playwright/test') });
  assert.deepEqual(confirmed(official), [['#4a', 3, 'confirmed']]);
});

test('2: test.use replacing a custom fixture or a fixture it depends on voids the Page proof', t => {
  const fixtures = FIXTURES('shell: async ({ page }, use) => { await use(page); }');
  for (const replaced of ['shell', 'page']) {
    const spec = COUNT_SPEC('./fixtures', 'shell').replace("test('x'", `test.use({ ${replaced}: { locator: () => ({ count: async () => -1 }) } as any });\ntest('x'`);
    const result = scan(t, { 'fixtures.ts': fixtures, 'x.spec.ts': spec });
    assert.deepEqual(confirmed(result), [], replaced);
  }
  // Guard: test.use with an unrelated option keeps the proof.
  const kept = scan(t, { 'fixtures.ts': fixtures,
    'x.spec.ts': COUNT_SPEC('./fixtures', 'shell').replace("test('x'", "test.use({ locale: 'de-DE' });\ntest('x'") });
  assert.deepEqual(confirmed(kept), [['#4a', 4, 'confirmed']]);
});

test('3: a replaced newPage is not a Playwright Page producer', t => {
  const patched = FIXTURES('shell: async ({ context }, use) => { context.newPage = async () => ({ locator: () => ({ count: async () => -1 }) }) as any; await use(await context.newPage()); }');
  assert.deepEqual(confirmed(scan(t, { 'fixtures.ts': patched, 'x.spec.ts': COUNT_SPEC('./fixtures', 'shell') })), []);
  // The same replacement inside a test.
  const inline = scan(t, { 'x.spec.ts': "import { test, expect } from '@playwright/test';\ntest('x', async ({ context }) => {\n" +
    "  context.newPage = async () => ({ locator: () => ({ count: async () => -1 }) }) as any;\n  const page = await context.newPage();\n" +
    "  expect(await page.locator('x').count()).toBeGreaterThanOrEqual(0);\n});\n" });
  assert.deepEqual(confirmed(inline), []);
  // Guard: the unmodified context fixture's newPage is a Page.
  const kept = FIXTURES('shell: async ({ context }, use) => { await use(await context.newPage()); }');
  assert.deepEqual(confirmed(scan(t, { 'fixtures.ts': kept, 'x.spec.ts': COUNT_SPEC('./fixtures', 'shell') })), [['#4a', 3, 'confirmed']]);
});

test('4: toBe(true) on a truthy || result is not always-pass', t => {
  const spec = body => `import { test, expect } from '@playwright/test';\ntest('x', async ({ page }) => {\n${body}\n});\n`;
  const failing = scan(t, { 'x.spec.ts': spec("const value = 'enabled';\nexpect(value || true).toBe(true);\nexpect(false || 1).toBe(true);\nexpect(value || 'yes').toBe(true);") });
  assert.deepEqual(confirmed(failing), []);
  // `value || true` may still be vacuous for a boolean value: it stays a candidate.
  assert.deepEqual(failing.p0, [['#4a', 4, 'candidate']]);
  // Guards: a provably boolean left side, `true ||`, and truthiness matchers.
  const kept = scan(t, { 'x.spec.ts': spec("const shown = await page.getByText('a').isVisible();\nexpect(shown || true).toBe(true);\n" +
    "const value = 'enabled';\nexpect(true || value).toBe(true);\nexpect(value || 'yes').toBeTruthy();\nexpect(value || 1).toBeDefined();\n" +
    "const other = await page.getByText('b').isVisible().catch(() => false);\nexpect(shown || other || true).toBe(true);") });
  assert.deepEqual(confirmed(kept).map(item => item[1]), [4, 6, 7, 8, 10]);
});

test('5: an assertion under a condition that is always true is not a confirmed bypass', t => {
  const spec = condition => `import { test, expect } from '@playwright/test';\ntest('x', async ({ page }) => {\n` +
    `  if (${condition}) {\n    await expect(page).toHaveTitle('ok');\n  }\n});\n`;
  for (const condition of ["(await page.locator('x').count()) >= 0", "await page.locator('x').isVisible() || true",
    "(await page.locator('x').count()) > -1", "0 <= (await page.locator('x').count())"]) {
    const result = scan(t, { 'x.spec.ts': spec(condition) });
    assert.deepEqual(confirmed(result), [], condition);
    assert.ok(result.p0.some(item => item[0] === '#5a'), condition);
  }
  // Guards: a condition some count or state makes false stays confirmed.
  for (const condition of ["(await page.locator('x').count()) > 0", "(await page.locator('x').count()) === 1",
    "await page.locator('x').isVisible()", "!(await page.locator('x').isVisible())", "(await page.locator('x').count()) >= 1"]) {
    const result = scan(t, { 'x.spec.ts': spec(condition) });
    assert.ok(confirmed(result).some(item => item[0] === '#5a' && item[1] === 3), condition);
  }
});

test('6: the awaited result of an unproven call is unresolved, not proven non-Locator', t => {
  const spec = body => `import { test, expect } from '@playwright/test';\nasync function banner(page: any) { return page.locator('.banner'); }\n` +
    `test('x', async ({ page }) => {\n${body}\n});\n`;
  // A helper returning a Locator, used as an always-truthy gate: never clean.
  const helper = scan(t, { 'x.spec.ts': spec("  const b = await banner(page);\n  expect(b).toBeTruthy();\n  if (b) {\n    await page.reload();\n  }") });
  assert.notEqual(helper.status, 'COMPLETE');
  assert.notEqual(helper.exit, 0);
  // Guards: awaited Playwright reads and navigation results stay resolved,
  // and the same truthiness check on a direct Locator stays confirmed.
  const data = scan(t, { 'x.spec.ts': spec("  const n = await page.locator('x').count();\n  const title = await page.title();\n" +
    "  const response = await page.goto('/');\n  expect(response!.ok()).toBe(true);\n  expect(title.length).toBe(n);") });
  assert.equal(data.status, 'COMPLETE');
  const direct = scan(t, { 'x.spec.ts': spec("  const b = page.locator('.banner');\n  expect(b).toBeTruthy();") });
  assert.deepEqual(confirmed(direct), [['#4f', 5, 'confirmed']]);
});

test('7: a fixture object spreading provably other keys keeps the base page; a Proxy or unknown spread does not', t => {
  const spec = "import { test, expect } from './fixtures';\ntest('x', async ({ page }) => {\n  expect(await page.locator('x').count()).toBeGreaterThanOrEqual(0);\n});\n";
  const factories = "export const factories = { simple: () => 1, pnpm: () => 2 };\n";
  const withSpread = spread => "import { test as base, expect } from '@playwright/test';\nimport { factories } from './factories';\n" +
    `export const test = base.extend({\n  ${spread},\n` +
    "  screenshot: [async ({ page }, use) => { await use(); await page.screenshot({ path: 'x.png' }); }, { auto: true }],\n" +
    "  log: [async ({ page }, use) => { page.on('response', () => {}); await use(); }, { auto: true }],\n});\nexport { expect };\n";
  // The netlify shape: keys come from a literal object, so `page` is untouched.
  const kept = scan(t, { 'factories.ts': factories, 'x.spec.ts': spec,
    'fixtures.ts': withSpread('...Object.fromEntries(Object.entries(factories).map(([key, make]) => [key, async ({}, use) => use(make())]))') });
  assert.deepEqual(confirmed(kept), [['#4a', 3, 'confirmed']]);
  // Guards: a Proxy around page, and a spread whose keys are unknown.
  const proxy = scan(t, { 'x.spec.ts': spec, 'fixtures.ts': "import { test as base, expect } from '@playwright/test';\n" +
    "export const test = base.extend({ page: async ({ page }, use) => { await use(new Proxy(page, {})); } });\nexport { expect };\n" });
  assert.deepEqual(confirmed(proxy), []);
  const unknown = scan(t, { 'x.spec.ts': spec, 'fixtures.ts': withSpread('...(globalThis as any).extra') });
  assert.deepEqual(confirmed(unknown), []);
  const named = scan(t, { 'factories.ts': "export const factories = { page: () => 1 };\n", 'x.spec.ts': spec,
    'fixtures.ts': withSpread('...Object.fromEntries(Object.entries(factories).map(([key, make]) => [key, async ({}, use) => use(make())]))') });
  assert.deepEqual(confirmed(named), []);
});
