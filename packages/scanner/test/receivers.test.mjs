// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createReceivers } from '../src/receivers.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { walk, ts } from '../src/source.mjs';

function classifyAny(text) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-receivers-')));
  const file = path.join(root, 'case.spec.ts');
  fs.writeFileSync(file, text);
  const bytes = Buffer.from(text), manifest = inventory(root);
  const receivers = createReceivers(bytes, file, {scope: createScope({manifest, sources: new Map([[file, bytes]])})});
  const values = [];
  walk(receivers.source, node => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'inspect') values.push(receivers.expression(node.arguments[0]));
  });
  return values.map(x => [x.kind, x.complete]);
}
function classify(text, selected) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-receivers-')));
  const file = path.join(root, 'case.spec.ts');
  fs.writeFileSync(file, text);
  const bytes = Buffer.from(text), manifest = inventory(root);
  const scope = createScope({manifest, sources: new Map([[file, bytes]])});
  const receivers = createReceivers(bytes, file, {scope});
  const values = [];
  walk(receivers.source, node => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'inspect') {
      values.push(receivers.expression(node.arguments[0]));
    }
  });
  assert.equal(values.length, selected.length);
  assert.deepEqual(values.map(x => x.kind), selected);
  return values;
}

test('fixture Page, immutable locator chain and imported expect have shared provenance', () => {
  classify("import {test, expect as check} from '@playwright/test'; test('x',async({page: screen})=>{const row=screen.getByRole('row').filter({hasText:'a'}); inspect(screen);inspect(row.nth(0));inspect(check);});", ['page','locator','expect']);
  classify("const {test,expect: check}=require('@playwright/test'); test('x',async({page})=>{inspect(page);inspect(check);});", ['page','expect']);
});

test('unrelated, shadowed and mutated objects cannot inherit Page or expect identity', () => {
  classify("import {test} from 'vitest';test('x',async({page})=>{inspect(page)});", ['none']);
  classify("import {test,expect} from '@playwright/test'; test('x',async({page})=>{function f(page,expect){inspect(page);inspect(expect)};});", ['none','none']);
  for (const write of ['page=custom;', 'page.getByRole=custom;', '({page}=custom);']) {
    const values = classify(`import {test} from '@playwright/test';test('x',async({page})=>{${write}inspect(page)});`, ['unknown']);
    assert.equal(values[0].complete, false);
  }
  classify("import {expect} from '@playwright/test'; expect=custom;inspect(expect);", ['unknown']);
});

test('mutable locator aliases and unknown helper results remain unresolved', () => {
  classify("import {test} from '@playwright/test';test('x',async({page})=>{let row=page.locator('x');inspect(row);inspect(makePage());});", ['unknown','unknown']);
});

test('direct type annotations stay distinct from runtime receiver proof', () => {
  classify("import type {Locator as Row,Page} from '@playwright/test';function helper(row:Row,page:Page){inspect(row);inspect(page);}", ['locator-type','page-type']);
  classify("function helper(row:import('@playwright/test').Locator){inspect(row);}", ['locator-type']);
  classify("import type {Locator} from 'foreign';function helper(row:Locator){inspect(row);}", ['none']);
  classify("type Locator={click():void};function helper(row:Locator){inspect(row);}", ['none']);
});

test('official fixture registrations preserve Page proof without accepting arbitrary callbacks', () => {
  for (const registration of ['only', 'skip', 'fixme', 'fail', 'beforeEach', 'afterEach']) {
    classify(`import {test as scenario} from '@playwright/test';scenario.${registration}('x',async({page})=>{inspect(page);inspect(page.getByTestId('row'));});`, ['page','locator']);
  }
  classify("import {test} from '@playwright/test';test['only']('x',async({page})=>{inspect(page);});", ['page']);
  classify("import {test} from '@playwright/test';function other(test){test.only('x',async({page})=>{inspect(page);});}", ['none']);
  classify("import {test} from 'vitest';test.only('x',async({page})=>{inspect(page);});", ['none']);
  const mutated = classify("import {test} from '@playwright/test';test.only=custom;test.only('x',async({page})=>{inspect(page);});", ['unknown']);
  assert.equal(mutated[0].complete, false);
  for (const registration of ['describe', 'step', 'beforeAll', 'afterAll', 'arbitrary']) {
    classify(`import {test} from '@playwright/test';test.${registration}('x',async({page})=>{inspect(page);});`, ['none']);
  }
});

test('mutation through registration and Page aliases cannot confirm a fixture receiver', () => {
  for(const prefix of [
    "import {test} from '@playwright/test';const scenario=test;scenario.only=custom;",
    "import * as pw from '@playwright/test';const scenario=pw.test;scenario.only=custom;const test=pw.test;",
    "const {test}=require('@playwright/test');const scenario=test;delete scenario.only;",
  ]) classify(prefix+"test.only('x',({page})=>inspect(page));",['unknown']);
  classify("import {test} from '@playwright/test';test.only('x',({page})=>{const screen=page;screen.click=custom;inspect(page);});",['unknown']);
  classify("import {test} from '@playwright/test';const scenario=test;function f(scenario){scenario.only=custom;}test.only('x',({page})=>inspect(page));",['page']);
});

test('only the official nested fail.only registration receives test-scoped fixtures', () => {
  for(const prefix of ["import {test} from '@playwright/test';", "const {test}=require('@playwright/test');",
    "import * as pw from '@playwright/test';const test=pw.test;"]) {
    classify(prefix+"test.fail.only('x',({page})=>{inspect(page);inspect(page.getByRole('button'));});",['page','locator']);
  }
  for(const registration of ['only.only','skip.only','fail.fail.only','describe.only','arbitrary.fail.only']) {
    classify(`import {test} from '@playwright/test';test.${registration}('x',({page})=>inspect(page));`,['none']);
  }
  classify("import {test} from 'vitest';test.fail.only('x',({page})=>inspect(page));",['none']);
  classify("import {test} from '@playwright/test';function f(test){test.fail.only('x',({page})=>inspect(page));}",['none']);
  classify("import {test} from '@playwright/test';test.fail.only=custom;test.fail.only('x',({page})=>inspect(page));",['unknown']);
});

test('a custom fixture is a Page only when every use() hands down the base page fixture', () => {
  // Round 7: test.extend fixtures named other than `page`.
  classify("import {test as base} from '@playwright/test';const test=base.extend({app:async({page},use)=>{await page.goto('/');await use(page);}});test('x',async({app})=>{inspect(app);inspect(app.getByRole('row'));});", ['page','locator']);
  classify("import {test as base} from '@playwright/test';const one=base.extend({app:async({page},use)=>{await use(page);}});const test=one.extend({shell:async({app},use)=>{await use(app);}});test('x',async({shell})=>{inspect(shell);});", ['page']);
  // A new page, a wrapped object, a page overridden in the same extend object
  // and an unpinned base stay unproven.
  for (const text of [
    "import {test as base} from '@playwright/test';const test=base.extend({app:async({context},use)=>{await use(await context.newPage());}});test('x',async({app})=>{inspect(app);});",
    "import {test as base} from '@playwright/test';const test=base.extend({app:async({page},use)=>{await use({page});}});test('x',async({app})=>{inspect(app);});",
    "import {test as base} from '@playwright/test';const test=base.extend({page:async({},use)=>{await use(custom);},app:async({page},use)=>{await use(page);}});test('x',async({app})=>{inspect(app);});",
    "import {test as base} from './missing';const test=base.extend({app:async({page},use)=>{await use(page);}});test('x',async({app})=>{inspect(app);});",
  ]) assert.deepEqual(classifyAny(text), [['unknown', false]], text);
});

test('a property of a proven Page is a Playwright helper object, never a Page or Locator', () => {
  // Round 7: page.keyboard and friends were unresolved provenance.
  classify("import {test} from '@playwright/test';test('x',async({page})=>{inspect(page.keyboard);inspect(page.mouse);inspect(page.locator('a').first);});", ['none','none','none']);
  assert.deepEqual(classifyAny("import {test} from '@playwright/test';test('x',async({page})=>{page.keyboard=custom;inspect(page.keyboard);});"), [['unknown', false]]);
  assert.deepEqual(classifyAny("import {helper} from './missing';inspect(helper().keyboard);"), [['unknown', false]]);
});
