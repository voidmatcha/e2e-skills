// SPDX-License-Identifier: Apache-2.0
// A member read or an awaited value is "not a Locator" only on proof. Members
// of an unproven `new X()` instance, unsummarized page-object members, `this`
// members in a class method, awaited helper results read through a property
// and awaited non-thenable values stay unresolved (or are found), never a
// clean pass. Proven shapes keep their verdicts.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function scan(t, files) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-member-reads-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0', '--allow-incomplete'],
    { encoding: 'utf8', timeout: 60_000 });
  const report = JSON.parse(result.stdout);
  const hits = report.findings.map(item => [path.relative(root, item.file), item.patternId, item.disposition, item.line]);
  const gaps = report.execution.diagnostics.map(item => [path.relative(root, item.file ?? ''), item.detector, item.line]);
  return { hits, gaps };
}
// Found (any disposition) or left unresolved at the line, never clean.
function notClean({ hits, gaps }, file, line) {
  return hits.some(hit => hit[0] === file && hit[3] === line) || gaps.some(gap => gap[0] === file && gap[2] === line);
}
const atLine = ({ hits, gaps }, file, line) => ({
  hits: hits.filter(hit => hit[0] === file && hit[3] === line), gaps: gaps.filter(gap => gap[0] === file && gap[2] === line) });

const WIDGET = `import { type Page } from '@playwright/test';
function build(page: Page) { return page.getByTestId('box'); }
export class Widget {
  box: any;
  label = 'Widget';
  constructor(page: Page) { this.box = build(page); }
}
`;
// Line numbers in the specs below are load-bearing.
const HOLES = `import { test, expect } from '@playwright/test';
import { Widget } from './widget';
import { Unknown } from 'some-package';
async function make(page) { return { box: page.getByTestId('box') }; }
test('instance and awaited member reads', async ({ page }) => {
  const w = new Widget(page);
  expect(w.box).toBeTruthy();
  const u = new Unknown(page);
  expect(u.box).toBeTruthy();
  const h = await make(page);
  expect(h.box).toBeTruthy();
  expect((await make(page)).box).toBeTruthy();
  expect(w.box)?.toBeTruthy();
  expect(await w.box).toBeTruthy();
  if (await w.box.isVisible()) {
    await expect(w.box).toBeVisible();
  }
  if (await h.box.isVisible()) {
    await expect(h.box).toBeVisible();
  }
});
`;
test('members of unproven instances and awaited helper results are never clean', t => {
  const result = scan(t, { 'tests/widget.ts': WIDGET, 'tests/holes.spec.ts': HOLES });
  for (const line of [7, 9, 11, 12, 13, 14, 15, 18]) assert.ok(notClean(result, 'tests/holes.spec.ts', line), `line ${line}`);
  assert.deepEqual(result.hits.filter(hit => hit[2] === 'confirmed'), []);
});

const PANEL = `import { test, expect } from '@playwright/test';
class Panel {
  constructor(page) { this.page = page; }
  get title() { return this.page.getByTestId('t'); }
  label = 'x';
  verify() {
    expect(this.title).toBeTruthy();
    expect(this.label).toBeTruthy();
    expect(this.missing).toBeTruthy();
  }
}
test('awaited Locator chains', async ({ page }) => {
  const l = await page.getByTestId('x');
  expect(l).toBeTruthy();
  expect(await page.getByTestId('y').first()).toBeTruthy();
  expect(await page.title()).toBeTruthy();
  const box = await page.getByTestId('x').boundingBox();
  expect(box).toBeTruthy();
  new Panel(page).verify();
});
`;
test('awaited Locator chains are Locators; awaited data stays data; class data members stay data', t => {
  const result = scan(t, { 'tests/panel.spec.ts': PANEL });
  const file = 'tests/panel.spec.ts';
  assert.deepEqual(atLine(result, file, 8), { hits: [], gaps: [] }, 'a literal field is data');
  assert.deepEqual(atLine(result, file, 9), { hits: [], gaps: [] }, 'an undeclared member of a proven class is undefined');
  assert.deepEqual(atLine(result, file, 14).hits.map(hit => hit.slice(1, 3)), [['#4f', 'confirmed']]);
  assert.deepEqual(atLine(result, file, 15).hits.filter(hit => hit[1] === '#4f').map(hit => hit.slice(1, 3)), [['#4f', 'confirmed']]);
  assert.deepEqual(atLine(result, file, 16), { hits: [], gaps: [] });
  assert.deepEqual(atLine(result, file, 18), { hits: [], gaps: [] });
});

const PROVEN = `import { test, expect } from '@playwright/test';
import { SettingsPage } from './settings';
function Literal() { return { flag: true }; }
test('proven shapes', async ({ page }) => {
  const po = new SettingsPage(page);
  expect(po.saveButton).toBeTruthy();
  expect(po.title).toBeTruthy();
  expect(po.open).toBeTruthy();
  const literal = new Literal();
  expect(literal.flag).toBeTruthy();
  const data = { name: 'x' };
  expect(data.name).toBeTruthy();
  expect(new URL(page.url()).pathname).toBeTruthy();
  const settled = await Promise.all([page.title()]);
  expect(settled[0]).toBeTruthy();
});
`;
const SETTINGS = `import { type Page, type Locator } from '@playwright/test';
export class SettingsPage {
  readonly saveButton: Locator;
  readonly title = 'Settings';
  constructor(private readonly page: Page) {
    this.saveButton = page.getByRole('button', { name: 'Save' });
  }
  async open() { await this.page.goto('/settings'); }
}
`;
test('proven page-object members, plain-data members and literal objects keep their verdicts', t => {
  const result = scan(t, { 'tests/settings.ts': SETTINGS, 'tests/proven.spec.ts': PROVEN });
  const file = 'tests/proven.spec.ts';
  assert.deepEqual(atLine(result, file, 6).hits.map(hit => hit.slice(1, 3)), [['#4f', 'confirmed']]);
  for (const line of [7, 8, 10, 12, 13, 15]) assert.deepEqual(atLine(result, file, line), { hits: [], gaps: [] }, `line ${line}`);
});

// Codex review 2 repros. Each must be found or stay unresolved; none may be
// a confirmed P0 built on an unproven value, or a clean pass.
test('codex review 2: Object.assign instance, awaited promise variable and conditional stay unresolved', t => {
  const result = scan(t, { 'tests/x.spec.ts': `import {test,expect} from '@playwright/test';
class X { constructor(p) { Object.assign(this,{button:p.locator('button')}); } }
async function helper(p){return p.locator('x');}
test('a',async({page})=>{const x=new X(page); expect(x.button).toBeTruthy();});
test('b',async({page})=>{const promise=helper(page);const x=await promise;expect(x).toBeTruthy();});
test('c',async({page})=>{const x=await (true ? helper(page):helper(page)); expect(x).toBeTruthy();});
test('d',async({page})=>{const x=await page.locator('button'); expect(x).toBeTruthy();});
` });
  for (const line of [4, 5, 6]) assert.ok(notClean(result, 'tests/x.spec.ts', line), `line ${line}`);
  assert.deepEqual(result.hits.filter(hit => hit[2] === 'confirmed').map(hit => hit.slice(1, 4)), [['#4f', 'confirmed', 7]]);
});
test('codex review 2: a helper or constructor that hands its Page argument to other code proves no summary', t => {
  const mutate = "function mutate(p){p.locator=()=>({count:async()=>-1});}\n";
  const result = scan(t, {
    'tests/helper.ts': "export function helper(p){ mutate(p); return p.locator('x'); }\n" + mutate +
      "export class C {constructor(p){mutate(p);this.button=p.locator('x');}}\n" +
      "export class D {constructor(p){this.page=p;mutate(this.page);this.button=this.page.locator('x');}}\n",
    'tests/x.spec.ts': `import {test,expect} from '@playwright/test';
import {helper,C,D} from './helper';
test('a',async({page})=>{expect(await helper(page).count()).toBeGreaterThanOrEqual(0);});
test('b',async({page})=>{const x=new C(page); expect(await x.button.count()).toBeGreaterThanOrEqual(0);});
test('c',async({page})=>{const x=new D(page); expect(await x.button.count()).toBeGreaterThanOrEqual(0);});
` });
  for (const line of [3, 4, 5]) assert.ok(notClean(result, 'tests/x.spec.ts', line), `line ${line}`);
  assert.deepEqual(result.hits.filter(hit => hit[2] === 'confirmed'), []);
});
test('codex review 2: a helper gate called through a namespace import moves to the test call', t => {
  const result = scan(t, {
    'tests/helper.ts': "import {expect} from '@playwright/test';\nexport async function check(page,ok){if(ok){await expect(page.locator('x')).toHaveText('required');}}\n",
    'tests/x.spec.ts': "import {test} from '@playwright/test';\nimport * as h from './helper';\ntest('x',async({page})=>{await h.check(page,await page.locator('x').isVisible());});\n" });
  assert.ok(result.hits.some(hit => hit[0] === 'tests/x.spec.ts' && hit[1] === '#5a' && hit[3] === 3), JSON.stringify(result.hits));
});
// An exported helper's gate leaves the helper only when every pinned
// importer calls it in a shape the caller-side rule traces. Any other use
// (alias, element access, export *, import(), .call, a non-test wrapper or a
// callback) keeps the candidate at the helper instead of losing it.
const GATE_HELPER = "import {expect} from '@playwright/test';\nexport async function check(page,ok){if(ok){await expect(page.locator('x')).toHaveText('required');}}\n";
const READ = "await page.locator('x').isVisible()";
for (const [name, spec, extra] of [
  ['alias', `import {check} from './helper';\nconst f = check;\ntest('x',async({page})=>{await f(page,${READ});});`],
  ['element access', `import * as h from './helper';\ntest('x',async({page})=>{await h['check'](page,${READ});});`],
  ['export * barrel', `import * as h from './index';\ntest('x',async({page})=>{await h.check(page,${READ});});`, { 'tests/index.ts': "export * from './helper';\n" }],
  ['dynamic import', `test('x',async({page})=>{const {check}=await import('./helper'); await check(page,${READ});});`],
  ['call()', `import {check} from './helper';\ntest('x',async({page})=>{await check.call(null,page,${READ});});`],
  ['non-test wrapper', `import {check} from './helper';\nasync function w(page){ await check(page,${READ}); }\ntest('x',async({page})=>{await w(page);});`],
  ['map callback', `import {check} from './helper';\ntest('x',async({page})=>{const v=${READ}; await Promise.all([page].map(p=>check(p,v)));});`],
]) {
  test(`exported #5a helper gate stays at the helper when an importer uses it as: ${name}`, t => {
    const result = scan(t, { 'tests/helper.ts': GATE_HELPER, 'tests/x.spec.ts': `import {test} from '@playwright/test';\n${spec}\n`, ...extra });
    assert.ok(result.hits.some(hit => hit[1] === '#5a'), `${name}: ${JSON.stringify(result.hits)}`);
    assert.ok(result.hits.some(hit => hit[0] === 'tests/helper.ts' && hit[1] === '#5a' && hit[3] === 2), `${name}: ${JSON.stringify(result.hits)}`);
  });
}
test('exported #5a helper gate still moves through a named re-export, and literal-only callers stay quiet', t => {
  const barrel = scan(t, { 'tests/helper.ts': GATE_HELPER, 'tests/index.ts': "export {check} from './helper';\n",
    'tests/x.spec.ts': `import {test} from '@playwright/test';\nimport {check} from './index';\ntest('x',async({page})=>{await check(page,${READ});});\n` });
  assert.deepEqual(barrel.hits.filter(hit => hit[1] === '#5a').map(hit => [hit[0], hit[3]]), [['tests/x.spec.ts', 3]]);
  const literal = scan(t, { 'tests/helper.ts': GATE_HELPER,
    'tests/x.spec.ts': "import {test} from '@playwright/test';\nimport {check} from './helper';\ntest('x',async({page})=>{await check(page,true);});\n" });
  assert.deepEqual(literal.hits.filter(hit => hit[1] === '#5a'), []);
});
