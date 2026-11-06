// SPDX-License-Identifier: Apache-2.0
// Page-object use-site proofs and helper return summaries: members, getters,
// methods and helper results proven from the constructor or call arguments
// resolve; unknown sources, writes, dynamic names, non-Page arguments and
// recursion stay unresolved and never confirm.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function scan(t, files) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-page-objects-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0', '--allow-incomplete'],
    { encoding: 'utf8', timeout: 60_000 });
  const report = JSON.parse(result.stdout);
  const hits = report.findings.map(item => [path.relative(root, item.file), item.patternId, item.disposition, item.line]);
  const gaps = report.execution.diagnostics.map(item => [path.relative(root, item.file ?? ''), item.detector, item.code, item.line]);
  return { report, hits, gaps };
}
const has = (hits, file, id, disposition, line) =>
  hits.some(hit => hit[0] === file && hit[1] === id && hit[2] === disposition && hit[3] === line);
const confirmedIn = (hits, file) => hits.filter(hit => hit[0] === file && hit[2] === 'confirmed');

const SETTINGS = `import { type Page, type Locator } from '@playwright/test';
export class SettingsPage {
  readonly saveButton: Locator;
  constructor(private readonly page: Page) {
    this.saveButton = page.getByRole('button', { name: 'Save' });
  }
  get banner() { return this.page.getByTestId('banner'); }
  row(name: string) { return this.page.getByRole('row', { name }).first(); }
  async open() { await this.page.goto('/settings'); }
}
`;
// Line numbers in the spec below are load-bearing.
const SPEC = `import { test, expect } from '@playwright/test';
import { SettingsPage } from './pages/settings';
test('gated save', async ({ page }) => {
  const po = new SettingsPage(page);
  await page.goto('/settings');
  if (await po.saveButton.isVisible()) {
    await expect(po.saveButton).toBeEnabled();
  }
});
test('members', async ({ page }) => {
  const po = new SettingsPage(page);
  await po.banner.click({ force: true });
  await po.row('a').click({ force: true });
  expect(po.saveButton).toBeTruthy();
});
`;

test('page-object fields, getters and methods from a proven page resolve and confirm', t => {
  const { hits, gaps } = scan(t, { 'tests/pages/settings.ts': SETTINGS, 'tests/settings.spec.ts': SPEC });
  assert.ok(has(hits, 'tests/settings.spec.ts', '#5a', 'confirmed', 6), JSON.stringify(hits));
  assert.ok(has(hits, 'tests/settings.spec.ts', '#5b', 'confirmed', 12), JSON.stringify(hits));
  assert.ok(has(hits, 'tests/settings.spec.ts', '#5b', 'confirmed', 13), JSON.stringify(hits));
  assert.ok(has(hits, 'tests/settings.spec.ts', '#4f', 'confirmed', 14), JSON.stringify(hits));
  assert.deepEqual(gaps.filter(gap => gap[0] === 'tests/settings.spec.ts'), []);
});

test('a page-object method that may assert keeps the gate a candidate', t => {
  const spec = SPEC.replace("await page.goto('/settings');", 'await po.open();');
  const { hits } = scan(t, { 'tests/pages/settings.ts': SETTINGS, 'tests/settings.spec.ts': spec });
  assert.ok(has(hits, 'tests/settings.spec.ts', '#5a', 'candidate', 6), JSON.stringify(hits));
  assert.ok(!has(hits, 'tests/settings.spec.ts', '#5a', 'confirmed', 6), JSON.stringify(hits));
});

test('a proven base class with super(page), and a use(new C(page)) fixture, resolve', t => {
  const base = `import type { Page } from '@playwright/test';
export class BasePage { constructor(protected readonly page: Page) {} get header() { return this.page.locator('header'); } }
`;
  const derived = `import { BasePage } from './base';
import type { Page } from '@playwright/test';
export class HomePage extends BasePage {
  readonly cta = this.page.getByRole('link', { name: 'Start' });
  constructor(page: Page) { super(page); }
}
`;
  const fixtures = `import { test as base, expect } from '@playwright/test';
import { HomePage } from './pages/home';
export const test = base.extend<{ home: HomePage }>({
  home: async ({ page }, use) => { await use(new HomePage(page)); },
});
export { expect };
`;
  const spec = `import { test } from './fixtures';
import { HomePage } from './pages/home';
test('derived', async ({ page }) => {
  const home = new HomePage(page);
  await home.header.click({ force: true });
  await home.cta.click({ force: true });
});
test('fixture', async ({ home }) => {
  await home.cta.click({ force: true });
});
`;
  const { hits, gaps } = scan(t, { 'tests/pages/base.ts': base, 'tests/pages/home.ts': derived, 'tests/fixtures.ts': fixtures, 'tests/home.spec.ts': spec });
  for (const line of [5, 6, 9]) assert.ok(has(hits, 'tests/home.spec.ts', '#5b', 'confirmed', line), `${line} ${JSON.stringify(hits)}`);
  assert.deepEqual(gaps.filter(gap => gap[0] === 'tests/home.spec.ts'), []);
});

test('an exported Locator helper, also through a barrel, resolves from the call-site argument', t => {
  const helpers = `import type { Page } from '@playwright/test';
export function getRow(page: Page, index: number) { return page.getByRole('row').nth(index); }
export const clickSave = (page: Page) => page.getByRole('button', { name: 'Save' });
`;
  const spec = `import { test } from '@playwright/test';
import { getRow, clickSave } from './lib';
test('rows', async ({ page }) => {
  await getRow(page, 1).click({ force: true });
  await clickSave(page).click({ force: true });
});
`;
  const { hits, gaps } = scan(t, { 'tests/lib/helpers.ts': helpers, 'tests/lib/index.ts': "export * from './helpers';\n", 'tests/rows.spec.ts': spec });
  assert.ok(has(hits, 'tests/rows.spec.ts', '#5b', 'confirmed', 4), JSON.stringify(hits));
  assert.ok(has(hits, 'tests/rows.spec.ts', '#5b', 'confirmed', 5), JSON.stringify(hits));
  assert.deepEqual(gaps.filter(gap => gap[0] === 'tests/rows.spec.ts'), []);
});

// Each guard must leave its use site unresolved: no confirmed finding in the
// spec and at least one diagnostic there, never a silent clean. The use is a
// method call, which is unresolved without a proof; a plain member read of an
// unproven page object keeps the scanner's existing (non-Locator) verdict.
const GUARD_SPEC = (setup, use = 'await po.row().click({ force: true });') => `import { test } from '@playwright/test';
import { Probe } from './probe';
test('guard', async ({ page }) => {
  ${setup}
  ${use}
});
`;
const PROBE = body => `import type { Page } from '@playwright/test';
export class Probe {
  ${body}
}
`;
const GUARDS = {
  'unknown page source': { 'tests/probe.ts': PROBE("constructor(private readonly page: Page) {}\n  row() { return this.page.getByTestId('b'); }"),
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(makePage());') },
  'field reassigned later': { 'tests/probe.ts': PROBE("constructor(private page: Page) {}\n  row() { return this.page.getByTestId('b'); }\n  swap(other: Page) { this.page = other; }"),
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page);') },
  'instance field written by the test': { 'tests/probe.ts': PROBE("constructor(public page: Page) {}\n  row() { return this.page.getByTestId('b'); }"),
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page);\n  po.page = page;') },
  'dynamic property name': { 'tests/probe.ts': PROBE("constructor(private page: Page, key: string) { this[key] = page; }\n  row() { return this.page.getByTestId('b'); }"),
    'tests/guard.spec.ts': GUARD_SPEC("const po = new Probe(page, 'page');") },
  'conditional storage': { 'tests/probe.ts': PROBE("page: Page;\n  constructor(page: Page, ok: boolean) { if (ok) this.page = page; }\n  row() { return this.page.getByTestId('b'); }"),
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page, true);') },
  'initializer before body assignment': { 'tests/probe.ts': PROBE("page: Page;\n  check = this.page.getByTestId('c');\n  constructor(page: Page) { this.page = page; }"),
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page);', 'await po.check.first().click({ force: true });') },
  'async member': { 'tests/probe.ts': PROBE("constructor(private page: Page) {}\n  async row() { return this.page.getByTestId('b'); }"),
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page);', 'await (await po.row()).click({ force: true });') },
  'decorated class': { 'tests/probe.ts': "import type { Page } from '@playwright/test';\nconst tag = (c: any) => c;\n@tag\nexport class Probe {\n  constructor(private page: Page) {}\n  row() { return this.page.getByTestId('b'); }\n}\n",
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page);') },
  'mixin base': { 'tests/probe.ts': "import type { Page } from '@playwright/test';\nconst Mixin = (B: any) => class extends B {};\nclass Root { constructor(protected page: Page) {} }\nexport class Probe extends Mixin(Root) {\n  row() { return this.page.getByTestId('b'); }\n}\n",
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page);') },
  'package class': { 'tests/probe.ts': "export { Probe } from 'some-page-objects';\n",
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page);') },
  'escaping this': { 'tests/probe.ts': PROBE("constructor(private page: Page) { register(this); }\n  row() { return this.page.getByTestId('b'); }"),
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page);') },
  'prototype patch elsewhere': { 'tests/probe.ts': PROBE("constructor(private page: Page) {}\n  row() { return this.page.getByTestId('b'); }"),
    'tests/patch.ts': "import { Probe } from './probe';\nObject.defineProperty(Probe.prototype, 'row', { get() { return null; } });\n",
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page);') },
  'instance passed away': { 'tests/probe.ts': PROBE("constructor(private page: Page) {}\n  row() { return this.page.getByTestId('b'); }"),
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe(page);\n  mutate(po);') },
  'recursive members': { 'tests/probe.ts': PROBE("row(): any { return this.other().first(); }\n  other(): any { return this.row().first(); }"),
    'tests/guard.spec.ts': GUARD_SPEC('const po = new Probe();') },
  'helper with a non-Page argument': { 'tests/probe.ts': "export class Probe {}\nexport function row(owner: any) { return owner.getByRole('row').first(); }\n",
    'tests/guard.spec.ts': "import { test } from '@playwright/test';\nimport { row } from './probe';\ntest('guard', async () => {\n  await row({ getByRole: () => null }).click({ force: true });\n});\n" },
  'recursive helper': { 'tests/probe.ts': "export class Probe {}\nexport function row(page: any): any { return row(page).first(); }\n",
    'tests/guard.spec.ts': "import { test } from '@playwright/test';\nimport { row } from './probe';\ntest('guard', async ({ page }) => {\n  await row(page).click({ force: true });\n});\n" },
  'helper with a non-Locator return': { 'tests/probe.ts': "export class Probe {}\nexport function row(page: any, raw: boolean) { if (raw) return page; return page.getByRole('row').first(); }\n",
    'tests/guard.spec.ts': "import { test } from '@playwright/test';\nimport { row } from './probe';\ntest('guard', async ({ page }) => {\n  await row(page, false).click({ force: true });\n});\n" },
  'async helper': { 'tests/probe.ts': "export class Probe {}\nexport async function row(page: any) { return page.getByRole('row').first(); }\n",
    'tests/guard.spec.ts': "import { test } from '@playwright/test';\nimport { row } from './probe';\ntest('guard', async ({ page }) => {\n  await (await row(page)).click({ force: true });\n});\n" },
  'reassigned helper parameter': { 'tests/probe.ts': "export class Probe {}\nexport function row(page: any) { page = page.other; return page.getByRole('row').first(); }\n",
    'tests/guard.spec.ts': "import { test } from '@playwright/test';\nimport { row } from './probe';\ntest('guard', async ({ page }) => {\n  await row(page).click({ force: true });\n});\n" },
  'CommonJS helper': { 'tests/probe.ts': "module.exports = { row: (page) => page.getByRole('row').first() };\n",
    'tests/guard.spec.ts': "import { test } from '@playwright/test';\nimport { row } from './probe';\ntest('guard', async ({ page }) => {\n  await row(page).click({ force: true });\n});\n" },
};
// An awaited call result keeps the scanner's existing awaited-value verdict,
// so these two only must never confirm.
const AWAITED = new Set(['async member', 'async helper']);
for (const [name, files] of Object.entries(GUARDS)) {
  test(`stays unresolved: ${name}`, t => {
    const { hits, gaps } = scan(t, files);
    assert.deepEqual(confirmedIn(hits, 'tests/guard.spec.ts'), [], JSON.stringify(hits));
    if (!AWAITED.has(name)) assert.ok(gaps.some(gap => gap[0] === 'tests/guard.spec.ts'), `${name}: ${JSON.stringify(gaps)}`);
  });
}
