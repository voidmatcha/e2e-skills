// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { waits } from '../src/waits.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function run(text, name = 'example.spec.ts') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-node-waits-')));
  const filename = path.join(root, name);
  fs.writeFileSync(filename, text);
  const manifest = inventory(root), bytes = Buffer.from(text);
  const scope = createScope({ manifest, sources: new Map([[filename, bytes]]) });
  return waits(bytes, filename, { scope });
}

test('exact Playwright page fixture, including renamed binding, proves sleep receiver', () => {
  const result = run("import {test} from '@playwright/test';\ntest('x',async({page: screen})=>{\nawait screen.waitForTimeout(10);\n});");
  assert.deepEqual(result.findings.map(item => [item.patternId, item.severity, item.line]), [['#9', 'P1', 3]]);
  assert.equal(result.diagnostics.length, 0);
});

test('unrelated receivers, foreign tests, strings and lexical shadows are not Page fixtures', () => {
  for (const text of ["const page={waitForTimeout(){}}; page.waitForTimeout(10);",
    "import {test} from 'vitest'; test('unit',async({page})=>{page.waitForTimeout(10)});",
    "import {test} from '@playwright/test'; test('x',async({page})=>{function f(page){page.waitForTimeout(10)}});",
    "import {test} from '@playwright/test'; test('x',async({page})=>{ const s='page.waitForTimeout(10)'; });"]) {
    assert.equal(run(text).findings.length, 0, text);
  }
});

test('Cypress numeric sleep differs from alias waits and unresolved variable triage', () => {
  const result = run("cy.visit('/');\ncy.wait(1000);\ncy.wait('@load');\ncy.wait(delay);\nfunction f(cy){cy.wait(1000);}", 'example.cy.ts');
  assert.deepEqual(result.findings.map(item => [item.patternId, item.line, item.disposition]),
    [['#9b', 2, 'confirmed'], ['#9b', 4, 'candidate']]);
});

test('assignments and assignment patterns invalidate page fixture provenance', () => {
  for (const write of ['page = custom;', '({page} = custom);', '[page] = custom;', 'for(page of custom) {}',
    'page.waitForTimeout = custom;', "page['waitForTimeout'] = custom;"]) {
    const result = run(`import {test} from '@playwright/test'; test('x',async({page})=>{${write} page.waitForTimeout(10);});`);
    assert.equal(result.findings.length, 0, write);
    assert.match(result.diagnostics[0].message, /mutable receiver/);
  }
  const result = run("import {test} from '@playwright/test'; test('x',async({page})=>{function other(page){page=custom;} page.waitForTimeout(10);});");
  assert.equal(result.findings.length, 1, 'a different lexical binding cannot invalidate the fixture');
});

test('invalid source and absent pinned scope remain incomplete', () => {
  assert.ok(run('function (').diagnostics.length);
  assert.match(waits(Buffer.from('cy.wait(1)'), 'example.cy.ts').diagnostics[0].message, /scope is required/);
});

test('Cypress global writes invalidate numeric waits through shared scope', () => {
  for(const write of ['cy=custom;', 'cy.wait=custom;', '({cy}=custom);', 'globalThis.cy=custom;']) {
    const result=run(write+'\ncy.wait(100);','example.cy.ts');
    assert.deepEqual(result.findings,[],write);
    assert.ok(result.diagnostics.some(item=>/mutated Cypress global/.test(item.message)),write);
  }
  assert.equal(run('function f(cy){cy.wait=custom;}\ncy.wait(100);','example.cy.ts').findings.length,1);
});
