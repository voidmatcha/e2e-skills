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
  // A new page from the proven built-in context is a Page.
  classify("import {test as base} from '@playwright/test';const test=base.extend({app:async({context},use)=>{await use(await context.newPage());}});test('x',async({app})=>{inspect(app);});", ['page']);
  classify("import {test as base} from '@playwright/test';const test=base.extend({app:async({context},use)=>{const p=await context.newPage();await use(p);await p.close();}});test('x',async({app})=>{inspect(app);});", ['page']);
  classify("import {test as base} from '@playwright/test';const test=base.extend({app:async({browser},use)=>{const c=await browser.newContext();await use(await c.newPage());}});test('x',async({app,browser})=>{inspect(app);inspect(browser);inspect(await browser.newPage());});", ['page','browser','page']);
  // A wrapped object, a page overridden in the same extend object
  // and an unpinned base stay unproven.
  for (const text of [
    "import {test as base} from '@playwright/test';const test=base.extend({app:async({browser},use)=>{await use(await browser.contexts()[0].newPage());}});test('x',async({app})=>{inspect(app);});",
    "import {test as base} from '@playwright/test';const test=base.extend({context:async({},use)=>{await use(custom);},app:async({context},use)=>{await use(await context.newPage());}});test('x',async({app})=>{inspect(app);});",
    "import {test as base} from '@playwright/test';const test=base.extend({app:async({page},use)=>{const p=page;p.goto=custom;await use(p);}});test('x',async({app})=>{inspect(app);});",
    "import {test as base} from '@playwright/test';const test=base.extend({app:async({page},use)=>{await use(page);await use(makePage());}});test('x',async({app})=>{inspect(app);});",
    "import {test as base} from '@playwright/test';const test=base.extend({app:async({page},use)=>{await use({page});}});test('x',async({app})=>{inspect(app);});",
    "import {test as base} from '@playwright/test';const test=base.extend({page:async({},use)=>{await use(custom);},app:async({page},use)=>{await use(page);}});test('x',async({app})=>{inspect(app);});",
    "import {test as base} from './missing';const test=base.extend({app:async({page},use)=>{await use(page);}});test('x',async({app})=>{inspect(app);});",
  ]) assert.deepEqual(classifyAny(text), [['unknown', false]], text);
});

test('an extension that overrides a built-in fixture must prove the replacement value', () => {
  // Proven overrides keep the built-in kind, through a chain and a re-export.
  classify("import {test as base} from '@playwright/test';const test=base.extend({page:async({page},use)=>{await page.addInitScript(()=>{});await use(page);}});test('x',async({page})=>{inspect(page);inspect(page.getByRole('row'));});", ['page','locator']);
  classify("import {test as base} from '@playwright/test';const test=base.extend({page:async({context},use)=>{const p=await context.newPage();await use(p);}});test('x',async({page})=>{inspect(page);});", ['page']);
  classify("import {test as base} from '@playwright/test';const test=base.extend({saveLogs:[async({},use)=>{await use();},{auto:true}]});test('x',async({page,context,request})=>{inspect(page);inspect(context);inspect(request);inspect(await context.newPage());});", ['page','context','request','page']);
  // A plain patched member keeps the Page only where that member is never used.
  classify("import {test as base} from '@playwright/test';const test=base.extend({page:async({page},use)=>{const original=page.goto.bind(page);page.goto=async(url)=>original(url);await use(page);}});test('x',async({page})=>{inspect(page);await page.click('a');});", ['page']);
  // Where the patched member is used, only direct non-patched member uses keep the Page.
  const patched = "import {test as base} from '@playwright/test';const test=base.extend({page:async({page},use)=>{page.goto=custom;await use(page);}});";
  assert.deepEqual(classifyAny(patched + "test('x',async({page})=>{await page.goto('/');inspect(page.getByRole('row'));inspect(page);});"), [['locator', true], ['unknown', false]]);
  // An unknown replacement, a patched member in use, other mutations and a test.use override stay unresolved.
  for (const text of [
    "import {test as base} from '@playwright/test';const test=base.extend({page:async({},use)=>{await use(custom);}});test('x',async({page})=>{inspect(page);});",
    "import {test as base} from '@playwright/test';const test=base.extend({page:async({page},use)=>{page.goto=custom;await use(page);}});test('x',async({page})=>{inspect(page);await page.goto('/');});",
    "import {test as base} from '@playwright/test';const test=base.extend({page:async({page},use)=>{page.goto=custom;await use(page);}});test('x',async({page})=>{const {goto}=page;inspect(page);});",
    "import {test as base} from '@playwright/test';const test=base.extend({page:async({page},use)=>{page.goto=custom;await use(page);}});test('x',async({page})=>{inspect(page);page[name]();});",
    "import {test as base} from '@playwright/test';const test=base.extend({page:async({page},use)=>{Object.assign(page,custom);await use(page);}});test('x',async({page})=>{inspect(page);});",
    "import {test as base} from '@playwright/test';const test=base.extend({page:async({page},use)=>{page['goto']+=custom;await use(page);}});test('x',async({page})=>{inspect(page);});",
    "import {test as base} from '@playwright/test';const test=base.extend({page:async({page},use)=>{const p=page;p.click=custom;await use(page);}});test('x',async({page})=>{inspect(page);});",
    "import {test as base} from '@playwright/test';const test=base.extend({page:async({page},use)=>{await use(wrap(page));}});test('x',async({page})=>{inspect(page);});",
    "import {test as base} from '@playwright/test';const fixtures={page:async({},use)=>{await use(custom);}};const test=base.extend(fixtures);test('x',async({page})=>{inspect(page);});",
    "import {test as base} from '@playwright/test';const test=base.extend({...shared});test('x',async({page})=>{inspect(page);});",
    "import {test} from '@playwright/test';test.use({page:custom});test('x',async({page})=>{inspect(page);});",
    "import {test} from '@playwright/test';test.use(options);test('x',async({page})=>{inspect(page);});",
  ]) assert.deepEqual(classifyAny(text), [['unknown', false]], text);
  // test.use options that do not name the fixture leave it proven.
  classify("import {test} from '@playwright/test';test.use({baseURL:'/'});test('x',async({page})=>{inspect(page);});", ['page']);
});

test('an Electron window from the official _electron launcher is a Page', () => {
  classify("import {test,_electron} from '@playwright/test';import {_electron as electron} from 'playwright';test('x',async()=>{const app=await _electron.launch({args:['.']});const w=await app.firstWindow();inspect(app);inspect(w);inspect(w.getByRole('row'));const other=await electron.launch();inspect(await other.firstWindow());});", ['electron-app','page','locator','page']);
  classify("import {test as base,_electron} from '@playwright/test';const test=base.extend({electronApp:async({},use)=>{const app=await _electron.launch({args:['.']});await use(app);await app.close();},page:async({electronApp},use)=>{await use(await electronApp.firstWindow());}});test('x',async({page,electronApp})=>{inspect(page);inspect(electronApp);});", ['page','electron-app']);
  // windows()[i] may be undefined, a mutated app and other playwright exports stay unproven.
  for (const text of [
    "import {test,_electron} from '@playwright/test';test('x',async()=>{const app=await _electron.launch();inspect(app.windows()[0]);});",
    "import {test,_electron} from '@playwright/test';test('x',async()=>{const app=await _electron.launch();app.firstWindow=custom;inspect(await app.firstWindow());});",
    "import {devices} from 'playwright';inspect(devices);",
  ]) assert.deepEqual(classifyAny(text), [['unknown', false]], text);
});

test('playwright/test is the official entrypoint, and browser launchers and contexts yield proven Pages', () => {
  classify("import {test,expect,chromium} from 'playwright/test';import {firefox} from 'playwright';test('x',async({page,browser})=>{inspect(page);inspect(expect);const c=await browser.newContext();const p=await c.newPage();inspect(c);inspect(p);inspect(await browser.newPage());const b=await chromium.launch();inspect(b);inspect(await (await b.newContext()).newPage());const f=await firefox.launch();inspect(await f.newPage());const pc=await chromium.launchPersistentContext('/tmp/x');inspect(await pc.newPage());});",
    ['page','expect','context','page','page','browser','page','page','page']);
  // A user-defined browser, newPage on an unknown receiver and a non-official launcher are never proven.
  for (const text of [
    "import {test} from '@playwright/test';test('x',async()=>{const browser={newPage:async()=>fake};inspect(await browser.newPage());});",
    "import {test} from '@playwright/test';test('x',async()=>{inspect(await unknownThing.newPage());});",
    "import {test} from '@playwright/test';import {chromium} from './fake-playwright';test('x',async()=>{const b=await chromium.launch();inspect(await b.newPage());});",
    "import {test} from 'playwright-test';test('x',async({page})=>{inspect(page.getByRole('row'));});",
  ]) assert.notEqual(classifyAny(text)[0][0], 'page', text);
  assert.deepEqual(classifyAny("import {test} from '@playwright/test';test('x',async()=>{inspect(await unknownThing.newPage());});"), [['unknown', false]]);
});

test('a property of a proven Page is a Playwright helper object, never a Page or Locator', () => {
  // Round 7: page.keyboard and friends were unresolved provenance.
  classify("import {test} from '@playwright/test';test('x',async({page})=>{inspect(page.keyboard);inspect(page.mouse);inspect(page.locator('a').first);});", ['none','none','none']);
  assert.deepEqual(classifyAny("import {test} from '@playwright/test';test('x',async({page})=>{page.keyboard=custom;inspect(page.keyboard);});"), [['unknown', false]]);
  assert.deepEqual(classifyAny("import {helper} from './missing';inspect(helper().keyboard);"), [['unknown', false]]);
});
