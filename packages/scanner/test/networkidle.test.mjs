// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { networkIdle } from '../src/networkidle.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function run(text, additional = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-networkidle-')));
  const filename = path.join(root, 'example.spec.ts');
  for (const [name, source] of Object.entries({ 'example.spec.ts': text, ...additional })) fs.writeFileSync(path.join(root, name), source);
  const manifest = inventory(root), sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  return networkIdle(sources.get(filename), filename, { scope });
}
const body = text => `import {test} from '@playwright/test';\ntest('x',async({page})=>{\n${text}\n});\n`;

test('direct literal load state and exact known navigation options produce raw #9c', () => {
  const lines = ["await page.waitForLoadState('networkidle');", "await page.goto('/', {waitUntil:'networkidle'});",
    "await page.waitForURL('/', {waitUntil:'networkidle'});", "await page.reload({waitUntil:'networkidle'});",
    "await page.goBack({waitUntil:'networkidle'});", "await page.goForward({'waitUntil':'networkidle'});"];
  const result = run(body(lines.join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.severity, f.disposition, f.origin, f.line]),
    lines.map((_, index) => ['#9c', 'P1', 'confirmed', 'ast', index + 3]));
  assert.ok(result.findings.every(f => f.end > f.start && f.column === 7));
});

test('renamed fixture and immutable Page alias retain provenance', () => {
  const result = run("import {test} from './fixture'; test('x',async({page: screen})=>{ const p=screen; p.waitForLoadState('networkidle'); });",
    { 'fixture.ts': "export {test} from '@playwright/test';" });
  assert.equal(result.findings.length, 1);
  assert.deepEqual(result.diagnostics, []);
});

test('custom receivers, lexical shadows, foreign tests, config objects and text are excluded', () => {
  for (const source of [
    "const page={waitForLoadState(){}}; page.waitForLoadState('networkidle');",
    "import {test} from 'vitest'; test('x',async({page})=>{page.waitForLoadState('networkidle')});",
    body("function f(page){page.waitForLoadState('networkidle')}"),
    body("{ const page=custom; page.goto('/',{waitUntil:'networkidle'}); }"),
    body("const config={waitUntil:'networkidle'};"),
    body("// page.waitForLoadState('networkidle');\nconst s=\"page.waitForLoadState('networkidle')\";"),
    body("page.custom('/',{waitUntil:'networkidle'});"),
  ]) assert.deepEqual(run(source).findings, [], source);
});

test('dynamic literals, templates, options aliases and optional calls stay explicitly outside the slice', () => {
  const result = run(body([
    "const state='networkidle'; page.waitForLoadState(state);",
    "page.waitForLoadState('network'+'idle');", 'page.waitForLoadState(`networkidle`);',
    "const options={waitUntil:'networkidle'}; page.goto('/',options);",
    "page.goto('/',{waitUntil:state});", "page.waitForLoadState?.('networkidle');",
    "page?.waitForLoadState('networkidle');", "page.waitForLoadState('load');",
  ].join('\n')));
  assert.deepEqual(result.findings, []);
  assert.deepEqual(result.diagnostics, []);
});

test('spread, duplicate, computed and accessor options never receive confirmation', () => {
  for (const options of ["{waitUntil:'networkidle', ...more}", "{...more, waitUntil:'networkidle'}",
    "{waitUntil:'networkidle',waitUntil:'load'}", "{waitUntil:'load',waitUntil:'networkidle'}",
    "{waitUntil:'networkidle',[key]:'load'}", "{waitUntil:'networkidle',get waitUntil(){return 'load'}}"]) {
    const result = run(body(`page.goto('/',${options});`));
    assert.deepEqual(result.findings, [], options);
    assert.match(result.diagnostics[0].message, /effective value is unresolved/, options);
  }
});

test('custom navigation with complex options does not create Page diagnostics', () => {
  const result = run("const custom={goto(){}}; custom.goto('/',{waitUntil:'networkidle',...more});");
  assert.deepEqual(result, {findings: [], diagnostics: []});
});

test('mutable and unresolved Page provenance stays diagnostic', () => {
  for (const write of ['page=custom;', 'page.goto=custom;']) {
    const result = run(body(`${write} page.goto('/',{waitUntil:'networkidle'});`));
    assert.deepEqual(result.findings, []);
    assert.match(result.diagnostics[0].message, /mutable receiver/);
  }
  const result = run("import {test} from './missing'; test('x',async({page})=>{page.waitForLoadState('networkidle')});");
  assert.deepEqual(result.findings, []);
  assert.ok(result.diagnostics.length);
});

test('syntax and absent scope cannot report complete findings', () => {
  assert.ok(run('function (').diagnostics.length);
  assert.match(networkIdle(Buffer.from(''), 'example.ts').diagnostics[0].message, /scope is required/);
});
