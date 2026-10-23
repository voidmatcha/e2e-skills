// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { pageReads } from '../src/page-reads.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function run(text, extra = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-page-reads-')));
  for (const [name, content] of Object.entries({ 'example.spec.ts': text, ...extra })) fs.writeFileSync(path.join(root, name), content);
  const manifest = inventory(root);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const filename = path.join(root, 'example.spec.ts');
  return pageReads(sources.get(filename), filename, { scope: createScope({ manifest, sources }) });
}
const body = text => "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n" + text + '\n});\n';

test('#4h semicolonless statements and multiline matchers remain P1 confirmed', () => {
  const result = run(body([
    "expect(page.url()).toBe('/ready')", "expect(page.url()).toEqual('/ready')",
    "expect(page.url())\n .not\n .toContain('/away')", 'expect(page.url())',
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.line, f.severity, f.disposition]),
    [3, 4, 5].map(line => ['#4h', line, 'P1', 'confirmed']));
});

test('#4h excludes proven toPass/poll callbacks without a lexical line-window limit', () => {
  const result = run(body([
    'await expect(async()=>{', '\n'.repeat(35), "expect(page.url()).toBe('/ready');",
    '\n'.repeat(35), '}).toPass();',
    "await expect.poll(()=>{expect(page.url()).toBe('/ready');return page.url();}).toBe('/ready');",
    "await expect.poll(()=>page.url()).toBe('/ready');",
    "expect(async()=>{expect(page.url()).toBe('/ready');}).toPass;",
    "expect(()=>{expect(page.url()).toBe('/ready');}).toBeDefined();",
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.equal(result.findings.length, 2, 'uncalled toPass and nonretry matchers are not retry containers');
});

test('retry aliases/reexports are proven while shadowed retry helpers cannot suppress #4h', () => {
  const result = run("import {test,verify} from './fixture';\ntest('x',async({page})=>{\n" +
    "await verify(async()=>{verify(page.url()).toBe('/ready');}).toPass();\n" +
    "function custom(expect){expect(()=>{verify(page.url()).toBe('/ready');}).toPass();}\n});",
  { 'fixture.ts': "export {test,expect as verify} from '@playwright/test';" });
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.line]), [['#4h', 4]]);
});

test('#17 direct selector API set preserves P1 confirmed and excludes Locator actions', () => {
  const names = ['click', 'dblclick', 'tap', 'fill', 'type', 'press', 'check', 'uncheck',
    'setChecked', 'selectOption', 'setInputFiles', 'hover', 'focus', 'dispatchEvent', 'dragAndDrop'];
  const result = run(body(names.map(name => `await page.${name}('#target');`).join('\n') +
    "\nawait page.getByRole('button').click();await page.goto('/');"));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.severity, f.disposition]),
    names.map(() => ['#17', 'P1', 'confirmed']));
});

test('foreign/shadowed Page and expect, wrappers, optional calls and inert text stay excluded', () => {
  for (const text of [
    "import {test,expect} from 'vitest';test('x',async({page})=>{page.click('x');expect(page.url()).toBe('x');});",
    body("function custom(page){page.click('x');expect(page.url()).toBe('x');}"),
    body("const pageLike={url:()=>'',click(){}};pageLike.click('x');expect(pageLike.url()).toBe('x');"),
    body("function custom(expect){expect(page.url()).toBe('x');}"),
    body("page?.click('x');page.click?.('x');expect(page?.url()).toBe('x');expect?.(page.url()).toBe('x');"),
    body("expect(String(page.url())).toBe('x');expect(page.url).toBe('x');expect(page.url()).toBe;"),
    body("const text=\"page.click('x');expect(page.url()).toBe('x')\";/* page.click('x'); */"),
  ]) assert.deepEqual(run(text).findings, [], text);
});

test('type-only receivers remain gaps; proven aliases and identifier selectors stay P1 candidates', () => {
  const result = run("import {expect,type Page} from '@playwright/test';\n" +
    "function helper(page:Page){page.click('x');expect(page.url()).toBe('x');}");
  assert.deepEqual(result.findings, []);
  assert.equal(result.diagnostics.length, 2);
  const unsupported = run(body("const screen=page;screen.click('x');page.click(selector);"));
  assert.deepEqual(unsupported.findings.map(f => [f.patternId, f.severity, f.disposition]),
    [['#17', 'P1', 'candidate'], ['#17', 'P1', 'candidate']]);
  assert.deepEqual(unsupported.diagnostics, []);
});

test('unresolved/mutable provenance and invalid source never produce a clean result', () => {
  for (const text of [
    "import {test,expect} from './missing';test('x',async({page})=>{page.click('x');expect(page.url()).toBe('x');});",
    body("page.click=custom;page.click('x');"),
    'function (',
  ]) {
    const result = run(text);
    assert.deepEqual(result.findings, []);
    assert.ok(result.diagnostics.length);
  }
  assert.match(pageReads(Buffer.from(''), 'x.ts').diagnostics[0].message, /pinned scope/);
});

// Candidate means a syntactic selector possibility, not a proven string value.
test('#17 aliases, renamed fixtures and variable selectors never become confirmed', () => {
  const result = run(body([
    "const screen=page;const second=screen;const selector='#target';",
    "screen.click('#target');", "second.fill(selector,'x');",
    "page.click(selector);", "page.click(externalSelector);",
    "let mutableSelector='#old';mutableSelector='#new';page.click(mutableSelector);",
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.equal(result.findings.length, 5);
  assert.ok(result.findings.every(f => f.patternId === '#17' && f.severity === 'P1' && f.disposition === 'candidate'));
  const renamed = run("import {test} from '@playwright/test';test('x',async({page:screen})=>{screen.click('#x');});");
  assert.deepEqual(renamed.findings.map(f => f.disposition), ['candidate']);
});

test('#17 alias receiver shadow, reassignment and property mutation fail closed', () => {
  for (const code of [
    "const screen=page;function f(screen){screen.click('#x');}",
    "let screen=page;screen.click('#x');",
    "const screen=page;screen.click=custom;screen.click('#x');",
    "const screen=page;page.click=custom;screen.click('#x');",
    "const screen={click(){}};screen.click(selector);",
    "const screen=page.getByRole('button');screen.click(selector);",
  ]) assert.deepEqual(run(body(code)).findings, [], code);
});

test('#17 arbitrary selector expressions remain diagnosed gaps and cannot be confirmed', () => {
  const result = run(body("page.click(42);page.click(...selectors);page.click(selectors[0]);page.click(getSelector());"));
  assert.deepEqual(result.findings, []);
  assert.equal(result.diagnostics.length, 4);
});
