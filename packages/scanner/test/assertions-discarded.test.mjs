// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { assertions } from '../src/assertions.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function run(text) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-discarded-')));
  const filename = path.join(root, 'example.spec.ts');
  fs.writeFileSync(filename, text);
  const manifest = inventory(root), bytes = Buffer.from(text);
  const scope = createScope({ manifest, sources: new Map([[filename, bytes]]) });
  return assertions(bytes, filename, { scope });
}
const body = text => "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n" + text + '\n});\n';

test('#8a and #8b stay P0 candidates even when a real assertion already exists', () => {
  const result = run(body([
    "await expect(page.locator('ready')).toBeVisible();",
    "page.locator('unused');", "await page.getByRole('button');",
    "const status=page.getByTestId('status');", 'await status.isVisible();',
    "await page.isHidden('hidden');",
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.severity, f.disposition, f.line]), [
    ['#8a', 'P0', 'candidate', 4], ['#8a', 'P0', 'candidate', 5],
    ['#8b', 'P0', 'candidate', 7], ['#8b', 'P0', 'candidate', 8],
  ]);
});

test('all six existing boolean state methods require a discarded awaited call', () => {
  const names = ['isVisible', 'isEnabled', 'isChecked', 'isDisabled', 'isEditable', 'isHidden'];
  const result = run(body(names.map(name => `await page.locator('a').${name}();`).join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => f.patternId), names.map(() => '#8b'));
  const unawaited = run(body("page.locator('a').isVisible();"));
  assert.deepEqual(unawaited.findings, []);
});

test('assignment, arguments, conditions, return and chained consumers are excluded', () => {
  const result = run(body([
    "const status=page.locator('a');", 'const visible=await status.isVisible();',
    'if (\n await status.isVisible()\n) console.log(visible);',
    'while (\n await status.isEnabled()\n) break;',
    'report(\n await status.isChecked()\n);',
    'await status.isVisible().catch(()=>false);',
    'await status.isVisible() && report(true);',
    "page.locator('b')\n.click();", "await page.locator('c')\n.first()\n.click();",
    "page.getByRole('button')\n// continuation\n?.click();",
    'return await status.isHidden();',
  ].join('\n')));
  assert.deepEqual(result.findings, []);
});

test('ASI boundaries retain actual discarded locators without treating .5 as a chain', () => {
  const result = run(body([
    "page.locator('no-semicolon')", "await page.locator('clicked').click();",
    "page.locator('with-semicolon');", '.5;', "page.getByText('last-line')",
  ].join('\n')));
  assert.deepEqual(result.findings.map(f => [f.patternId, f.line]), [['#8a', 3], ['#8a', 5], ['#8a', 7]]);
});

test('foreign tests, shadowed and unrelated receivers, strings and comments stay excluded', () => {
  for (const text of [
    "import {test} from 'vitest'; test('x',async({page})=>{page.locator('x');await page.isVisible('x');});",
    body("async function f(page){page.locator('x');await page.isVisible('x');}"),
    body("const clock={isVisible(){return true;}}; await clock.isVisible();"),
    body("const text=\"page.locator('x');\"; // await page.isVisible('x');"),
    "cy.get('x'); cy.get('x').should('be.visible');",
  ]) assert.deepEqual(run(text).findings, [], text);
});

test('mutable and unresolved fixture receivers produce diagnostics instead of candidates', () => {
  const mutable = run(body("page.locator=custom; page.locator('x');"));
  assert.deepEqual(mutable.findings, []);
  assert.match(mutable.diagnostics[0].message, /mutable receiver/);
  const unknown = run("import {test} from './missing'; test('x',async({page})=>{page.locator('x');await page.isVisible('x');});");
  assert.deepEqual(unknown.findings, []);
  assert.ok(unknown.diagnostics.length);
});

test('direct Playwright Page/Locator annotations support #8b candidates without confirming #4f', () => {
  const result = run("import {expect, type Locator, type Page as BrowserPage} from '@playwright/test';\n" +
    "async function typed(locator:Locator,page:BrowserPage){\nawait locator.isHidden();\nawait page.isVisible('x');\nexpect(locator).toBeTruthy();\n}\n" +
    "async function inline(locator:import('@playwright/test').Locator){\nawait locator.isEnabled();\n}\n" +
    "type LocalLocator={isVisible():Promise<boolean>};\nasync function local(locator:LocalLocator){await locator.isVisible();}\n");
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.line, f.disposition]),
    [['#8b', 3, 'candidate'], ['#8b', 4, 'candidate'], ['#8b', 8, 'candidate']]);
});
