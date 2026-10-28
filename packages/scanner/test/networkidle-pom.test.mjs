// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { networkIdle } from '../src/networkidle.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

const header = "import type {Page} from '@playwright/test';\n";
const pom = (operation, extra = '', imports = header) => imports +
  'class LoginPage { readonly page:Page; constructor(page:Page){this.page=page;}\n' +
  'async open(){' + operation + '}\n' + extra + '\n}';
const operation = "await this.page.waitForLoadState('networkidle');";
function fixture(text, check) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'networkidle-pom-')));
  try {
    const file = path.join(root, 'arbitrary.ts'), bytes = Buffer.from(text);
    fs.writeFileSync(file, bytes);
    const scope = createScope({ manifest: inventory(root), sources: new Map([[file, bytes]]) });
    return check(networkIdle(bytes, file, { scope }), file);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const scan = text => fixture(text, result => result);

test('source-linked constructor Page and direct Page annotations remain candidates with diagnostics', () => {
  for (const text of [
    pom(operation),
    pom("await this.page.goto('/',{waitUntil:'networkidle'});"),
    pom(operation).replaceAll('Page}', 'Page as Browser}').replaceAll(':Page', ':Browser'),
    header + "async function helper(page:Page){await page.waitForLoadState('networkidle');}",
    "async function helper(page:import('@playwright/test').Page){await page.waitForLoadState('networkidle');}",
  ]) {
    const result = scan(text);
    assert.equal(result.findings.length, 1, text);
    assert.deepEqual([result.findings[0].patternId, result.findings[0].disposition], ['#9c', 'candidate']);
    assert.equal(result.findings[0].evidence.kind, 'unresolved-page');
    assert.match(result.diagnostics[0].message, /does not establish runtime Page provenance/);
  }
});

test('foreign, custom, unlinked and dynamically bound this members cannot borrow Page provenance', () => {
  for (const text of [
    pom(operation, '', "import {Page} from 'foreign';\n"),
    pom(operation, '', 'class Page {}\n'),
    pom(operation).replace('this.page=page;', 'this.page=custom;'),
    pom(operation).replace('this.page=page;', 'if(ready)this.page=page;'),
    pom(operation).replace('readonly page:Page;', 'readonly page:Page=custom;'),
    pom(operation).replace('async open()', 'static async open()'),
    pom('function nested(){' + operation.replace('await ', '') + '}'),
    header + "const object={page:{waitForLoadState(){}},open(){this.page.waitForLoadState('networkidle')}};",
    header + "const page={waitForLoadState(){}};page.waitForLoadState('networkidle');",
    pom("await this.page.customWaitForLoadState('networkidle');"),
  ]) assert.deepEqual(scan(text).findings, [], text);
});

test('explicit member and alias mutations retain an incomplete diagnostic without candidates', () => {
  for (const mutation of [
    'this.page=custom;', 'this.page.waitForLoadState=custom;', "this['page']=custom;",
    "this.page['waitForLoadState']=custom;", 'delete this.page;', 'this[key]=custom;',
    'Object.assign(this.page,{waitForLoadState:custom});', 'Object.assign(this,{page:custom});',
    'const alias=this.page;alias.waitForLoadState=custom;',
    'const alias=this;alias.page=custom;',
    'const {page:alias}=this;alias.waitForLoadState=custom;',
  ]) {
    const result = scan(pom(operation, 'change(){' + mutation + '}'));
    assert.deepEqual(result.findings, [], mutation);
    assert.match(result.diagnostics[0].message, /explicit mutations/, mutation);
  }
  const changedParameter = scan(pom(operation).replace('this.page=page;', 'this.page=page;page=custom;'));
  assert.deepEqual(changedParameter.findings, []);
  assert.ok(changedParameter.diagnostics.length);
});

test('known Playwright fixtures remain confirmed; uncertain options never become candidates', () => {
  const result = scan("import {test} from '@playwright/test';test('x',async({page})=>{page.waitForLoadState('networkidle')});");
  assert.equal(result.findings[0].disposition, 'confirmed');
  assert.deepEqual(result.diagnostics, []);
  for (const statement of [
    "this.page.goto('/',{waitUntil:'networkidle',...options});",
    "this.page.waitForLoadState('networkidle',...options);",
    "this.page['waitForLoadState']('networkidle');",
  ]) {
    const result = scan(pom(statement));
    assert.deepEqual(result.findings, []);
    assert.ok(result.diagnostics.length);
  }
  assert.deepEqual(scan(pom("this.page.waitForLoadState('load');")), { findings: [], diagnostics: [] });
});

test('original LoginPage fixture retains line 33 as candidate and CLI remains INCOMPLETE', () => {
  const original = new URL('../../../scripts/evals/skills/e2e-reviewer/files/pages/login-page.ts', import.meta.url);
  const bytes = fs.readFileSync(original);
  fixture(bytes, (result, file) => {
    assert.deepEqual(result.findings.map(f => [f.patternId, f.line, f.disposition]), [['#9c', 33, 'candidate']]);
    assert.ok(result.diagnostics.length);
    const output = spawnSync(process.execPath, [new URL('../src/cli.mjs', import.meta.url).pathname,
      '--scan', file, '--fail-on', 'none'], { encoding: 'utf8' });
    assert.equal(output.status, 2, output.stderr);
    const report = JSON.parse(output.stdout);
    assert.equal(report.status, 'INCOMPLETE');
    assert.ok(report.execution.diagnostics.some(d => d.detector === 'networkIdle'));
    assert.ok(report.findings.some(f => f.patternId === '#9c' && f.line === 33 && f.disposition === 'candidate'));
  });
  assert.deepEqual(fs.readFileSync(original), bytes);
});
