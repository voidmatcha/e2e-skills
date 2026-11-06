// SPDX-License-Identifier: Apache-2.0
// Two false-clean paths, each with RED repros (clean before this change) and
// GREEN guards for the proven shapes.
// 1. `this.x` inside a class method was "not a Locator" whatever x held. It is
//    now the kind a closed-world class-body analysis proves: a constructor
//    chain on a proven argument, a declared (type-only) Page/Locator, plain
//    data of a closed class, or unresolved.
// 2. An exported #5a helper gate moved to its traced callers even when other
//    callers could not be seen: a scan of a subdirectory of the repository, or
//    a bare-name import of the helper's own package. The gate now stays at the
//    helper unless every importer is visible; a workspace package that the
//    project root declares is resolved and traced by name.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
// files: { relative: text }; `target` is the scanned directory under root.
function scan(t, files, target = '.') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-this-importer-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, text] of Object.entries(files)) {
    if (name.endsWith('/')) { fs.mkdirSync(path.join(root, name), { recursive: true }); continue; }
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  const result = spawnSync(process.execPath, [cli, '--scan', path.join(root, target), '--fail-on', 'p0', '--allow-incomplete'],
    { encoding: 'utf8', timeout: 60_000 });
  const report = JSON.parse(result.stdout);
  const hits = report.findings.map(item => [path.relative(root, item.file), item.patternId, item.disposition, item.line]);
  const gaps = report.execution.diagnostics.map(item => [path.relative(root, item.file ?? ''), item.detector, item.line]);
  return { hits, gaps, status: report.status };
}
const at = ({ hits, gaps }, file, line) => ({
  hits: hits.filter(hit => hit[0] === file && hit[3] === line), gaps: gaps.filter(gap => gap[0] === file && gap[2] === line) });
const notClean = (result, file, line) => { const found = at(result, file, line); return found.hits.length + found.gaps.length > 0; };

const PW = "import { test, expect, type Page, type Locator } from '@playwright/test';";
const spec = (...lines) => ({ 'x.spec.ts': [PW, ...lines].join('\n') + '\n' });

// ---- 1. `this` members ----
for (const [name, lines] of [
  ['an exported class with an untyped constructor argument',
    ["export class P { constructor(page) { this.submit = page.locator('x'); } check() { expect(this.submit).toBeTruthy(); } }",
      "test('t', async ({ page }) => { new P(page).check(); });"]],
  ['a field assigned outside the constructor',
    ["class P { constructor(page) { this.page = page; } open() { this.dialog = this.page.locator('d'); } check() { expect(this.dialog).toBeTruthy(); } }",
      "test('t', async ({ page }) => { const p = new P(page); p.open(); p.check(); });"]],
  ['a literal field written from outside the class',
    ["class P { label = 'Save'; check() { expect(this.label).toBeTruthy(); } }",
      "test('t', async ({ page }) => { const p = new P(); p.label = page.locator('x'); p.check(); });"]],
  ['a literal field a subclass replaces',
    ["class B { label = 'Save'; check() { expect(this.label).toBeTruthy(); } }",
      "class S extends B { constructor(page) { super(); this.label = page.locator('x'); } }",
      "test('t', async ({ page }) => { new S(page).check(); });"]],
  ['a method rebound with call()',
    ["class P { constructor(page) { this.submit = page.locator('x'); } check() { expect(this.submit).toBeTruthy(); } }",
      "test('t', async ({ page }) => { const p = new P(page); p.check.call({ submit: page.locator('y') }); });"]],
  ['a constructor that calls a method before the field exists',
    ["class P { constructor(page) { this.check(); this.submit = page.locator('x'); } check() { expect(this.submit).toBeTruthy(); } }",
      "test('t', async ({ page }) => { new P(page); });"]],
  ['a static method',
    ["export class P { static submit; static check() { expect(this.submit).toBeTruthy(); } }",
      "test('t', async ({ page }) => { P.check(); });"]],
]) {
  test(`this member: ${name} is never a clean pass`, t => {
    const result = scan(t, spec(...lines));
    assert.ok(notClean(result, 'x.spec.ts', 2), JSON.stringify(result));
    assert.deepEqual(result.hits.filter(hit => hit[2] === 'confirmed'), []);
  });
}
test('this member: a declared Locator built in the constructor is a #4f candidate, never confirmed', t => {
  const result = scan(t, spec(
    "export class P { readonly submit: Locator; constructor(page: Page) { this.submit = page.locator('x'); } check() { expect(this.submit).toBeTruthy(); } }",
    "test('t', async ({ page }) => { new P(page).check(); });"));
  assert.deepEqual(at(result, 'x.spec.ts', 2).hits.map(hit => [hit[1], hit[2]]), [['#4f', 'candidate']]);
});
test('this member: a closed class built only from the Page fixture confirms #4f', t => {
  const result = scan(t, spec(
    "class P { constructor(page) { this.submit = page.locator('x'); } check() { expect(this.submit).toBeTruthy(); } }",
    "test('t', async ({ page }) => { new P(page).check(); });"));
  assert.deepEqual(at(result, 'x.spec.ts', 2).hits.map(hit => [hit[1], hit[2]]), [['#4f', 'confirmed']]);
});
test('this member guards: literal data of a closed class and a declared Page member stay resolved', t => {
  const data = scan(t, spec("class P { label = 'Save'; check() { expect(this.label).toBeTruthy(); } }",
    "test('t', async () => { const p = new P(); p.check(); });"));
  assert.deepEqual(at(data, 'x.spec.ts', 2), { hits: [], gaps: [] });
  // The POM selector anchor survives as one candidate with no gap.
  const selector = scan(t, spec("export class P { constructor(private readonly page: Page) {} async save() { await this.page.fill('#name', 'Ada'); } }"));
  assert.equal(selector.status, 'COMPLETE', JSON.stringify(selector));
  assert.deepEqual(at(selector, 'x.spec.ts', 2).hits.map(hit => [hit[1], hit[2]]), [['#17', 'candidate']]);
});

// ---- 2. exported helper gates and their importers ----
const GATE = "import { expect, type Page } from '@playwright/test';\n" +
  "export async function check(page: Page, ok: boolean) { if (ok) { await expect(page.locator('x')).toHaveText('required'); } }\n";
const CALL = from => "import { test } from '@playwright/test';\n" + `import { check } from '${from}';\n` +
  "test('x', async ({ page }) => { await check(page, await page.locator('x').isVisible()); });\n";
const gateAt = result => result.hits.filter(hit => hit[1] === '#5a').map(hit => [hit[0], hit[3]]);
test('helper gate: a full-root scan traces a relative importer to the test call (guard)', t => {
  const result = scan(t, { '.git/': '', 'helpers/check.ts': GATE, 'tests/x.spec.ts': CALL('../helpers/check') });
  assert.deepEqual(gateAt(result), [['tests/x.spec.ts', 3]]);
});
test('helper gate: a subdirectory scan cannot see importers elsewhere, so the gate stays at the helper', t => {
  const files = { '.git/': '', 'e2e/helpers/check.ts': GATE, 'e2e/tests/x.spec.ts': CALL('../helpers/check'), 'other/y.spec.ts': CALL('../e2e/helpers/check') };
  assert.deepEqual(gateAt(scan(t, files, 'e2e/helpers')), [['e2e/helpers/check.ts', 2]]);
  assert.ok(gateAt(scan(t, files, 'e2e')).some(hit => hit[0] === 'e2e/helpers/check.ts'));
});
const WORKSPACE = (rootPackage, extra = {}) => ({ '.git/': '', 'package.json': JSON.stringify(rootPackage),
  'playwright.config.ts': 'export default {};\n', 'tsconfig.json': '{"compilerOptions":{"strict":true}}\n',
  'packages/helpers/package.json': JSON.stringify({ name: '@acme/helpers', main: 'src/index.ts' }),
  'packages/helpers/src/index.ts': GATE, 'e2e/x.spec.ts': CALL('@acme/helpers'), ...extra });
test('helper gate: a bare import of the helper package that is not resolved keeps the gate at the helper', t => {
  for (const files of [
    WORKSPACE({ name: 'root', private: true }), // no workspace declaration
    WORKSPACE({ name: 'root', workspaces: ['packages/*'] }, { 'packages/helpers/package.json': JSON.stringify({ name: '@acme/helpers', exports: { '.': './src/index.ts' } }) }),
    WORKSPACE({ name: 'root', workspaces: ['packages/**'] }),
  ]) assert.deepEqual(gateAt(scan(t, files)), [['packages/helpers/src/index.ts', 2]], files['package.json']);
});
test('helper gate: a declared workspace package resolves by name and is traced to the test call', t => {
  assert.deepEqual(gateAt(scan(t, WORKSPACE({ name: 'root', workspaces: ['packages/*'] }))), [['e2e/x.spec.ts', 3]]);
  assert.deepEqual(gateAt(scan(t, WORKSPACE({ name: 'root', private: true }, { 'pnpm-workspace.yaml': "packages:\n  - 'packages/*'\n" }))),
    [['e2e/x.spec.ts', 3]]);
});
test('this member guard: a closed class that is never constructed keeps its earlier verdict (its code never runs)', t => {
  const result = scan(t, spec("class P { constructor(readonly page) {} save(selector) { this.page.click(selector); } }"));
  assert.equal(result.status, 'COMPLETE', JSON.stringify(result));
});
