// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { reviewCandidates } from '../src/review-candidates.mjs';
import { domQueries } from '../src/dom-queries.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
import { applyJustified } from '../src/justified.mjs';
const header = "import type {Page,Locator} from '@playwright/test';\n";
function scan(text, callback) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'typed-pom-review-')));
  try {
    const file = path.join(root, 'page.ts'), bytes = Buffer.from(text);
    fs.writeFileSync(file, bytes);
    const manifest = inventory(root), scope = createScope({ manifest, sources: new Map([[file, bytes]]) });
    const result = reviewCandidates(bytes, file, { scope });
    callback?.(result, { file, bytes, scope });
    return result;
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const page = (body, prefix = header) => prefix + `class OrdersPage { constructor(private readonly page:Page) {}\n${body}\n}`;
test('original typed POM fixtures retain exact positional review anchors without runtime proof', () => {
  for (const [relative, lines] of [
    ['diff-review/orders-page.ts', [11]],
    ['positional-pom/admin-rooms.ts', [11]],
    ['pages/checkout-page.ts', [28, 34]],
  ]) {
    const text = fs.readFileSync(new URL('../../../skills/e2e-reviewer/evals/files/' + relative, import.meta.url), 'utf8');
    scan(text, (result, { bytes, file, scope }) => {
      const findings = result.findings.filter(item => item.patternId === '#10a');
      assert.deepEqual(findings.map(item => item.line), lines, relative);
      for (const finding of findings) {
        assert.equal(finding.disposition, 'candidate');
        assert.equal(finding.evidence.kind, 'unresolved-locator');
        assert.deepEqual(finding.evidence.requirements, ['verify-runtime-binding', 'verify-required-test-outcome']);
        assert.equal(bytes.toString().slice(finding.start, finding.end).includes('nth('), true);
      }
      assert.ok(domQueries(bytes, file, { scope }).diagnostics.length, 'strict uncertainty must remain');
      if (relative === 'pages/checkout-page.ts') {
        // Keep the existing suppression contract. This lane does not judge
        // whether the shipping rationale establishes the required outcome.
        const justified = applyJustified(bytes, file, findings);
        assert.deepEqual(justified.suppressed.map(item => item.line), [34]);
        assert.deepEqual(justified.findings.map(item => item.line), [28]);
      }
    });
  }
});
test('field constructor links, import aliases and lexical arrow this retain candidates', () => {
  for (const text of [
    header + 'class PageObject { readonly page:Page; constructor(page:Page){this.page=page;} row():Locator{return this.page.getByRole("row").first();}}',
    "import type {Page as BrowserPage, Locator as Handle} from '@playwright/test';" +
      'class PageObject { constructor(private page:BrowserPage){} row():Handle{return this.page.locator("x").last();}}',
    page('rows():Locator{return this.page.locator("x");} row():Locator{return this.rows().nth(2);}'),
    page('row(){ return (()=>this.page.locator("x").first())(); }'),
  ]) assert.equal(scan(text).findings.filter(item => item.patternId === '#10a').length, 1, text);
});
test('foreign, shadowed, custom, array and unlinked annotations do not borrow POM anchors', () => {
  for (const text of [
    page('row(){return this.page.locator("x").nth(2);}', "import type {Page} from 'foreign';\n"),
    'type Page={locator(x:string):any};class P {constructor(private page:Page){} row(){return this.page.locator("x").first();}}',
    header + 'class P {page:Page;constructor(page:Page){} row(){return this.page.locator("x").first();}}',
    page('rows(){return this.page.locator("x");} row(){return this.rows().first();}'),
    page('rows():Locator{return [1,2];} row(){return this.rows().first();}'),
    page('rows():Locator{return this.page.locator("x").all();} row(){return this.rows().first();}'),
    page('row(){const items=[1,2];return items.nth(2);}'),
    page('row(){function nested(){return this.page.locator("x").first();}return nested();}'),
    page('static row(){return this.page.locator("x").first();}'),
    page('row(this:Foreign){return this.page.locator("x").first();}'),
    page('row(){return this.page.locator("x").first();}')+'\nOrdersPage.prototype.row=foreign;',
    page('row(){return this.page.locator("x").first(2);}'),
    page('row(){return this.page.locator("x").last(...args);}'),
    page('row(){return this.page["locator"]("x").first();}'),
    header + 'class P extends Custom {constructor(private page:Page){super();} row(){return this.page.locator("x").first();}}',
  ]) assert.deepEqual(scan(text).findings, [], text);
});
test('mutated or escaping this and mutated constructor arguments fail closed', () => {
  for (const body of [
    'mutate(){this.page=other;} row(){return this.page.locator("x").first();}',
    'mutate(){this.page.locator=foreign;} row(){return this.page.locator("x").first();}',
    'mutate(){const self=this;self.page=other;} row(){return this.page.locator("x").first();}',
    'mutate(){const tab=this.page;tab.locator=other;} row(){return this.page.locator("x").first();}',
    'mutate(){custom(this);} row(){return this.page.locator("x").first();}',
    'mutate(){delete this.page;} row(){return this.page.locator("x").first();}',
    'rows():Locator{return this.page.locator("x");} mutate(){this.rows=other;} row(){return this.rows().first();}',
  ]) assert.deepEqual(scan(page(body)).findings, [], body);
  assert.deepEqual(scan(header + 'class P {readonly page:Page;constructor(page:Page){page=other;this.page=page;}row(){return this.page.locator("x").first();}}').findings, []);
});
test('original typed Page parameters and Locator fields retain remaining eval anchors', () => {
  for (const [relative, required] of [
    ['missing-await-contexts.spec.ts', [['#10c', 7], ['#16', 11]]],
    ['swallowed-try-catch.spec.ts', [['#10c', 13]]],
  ]) {
    const text = fs.readFileSync(new URL('../../../skills/e2e-reviewer/evals/files/' + relative, import.meta.url), 'utf8');
    const result = scan(text);
    for (const [pattern, line] of required) {
      const hits = result.findings.filter(item => item.patternId === pattern && item.line === line);
      assert.equal(hits.length, 1, relative + ':' + line);
      assert.equal(hits[0].disposition, 'candidate');
      assert.deepEqual(hits[0].evidence.requirements, ['verify-runtime-binding', 'verify-required-test-outcome']);
    }
  }
});
test('typed accessible-name lane excludes foreign, custom, shadowed, mutable and nonliteral options', () => {
  const parameter = (body, prefix = header) => prefix + `function helper(page:Page){${body}}`;
  for (const text of [
    parameter('page.getByRole("button",{name:"Save"});', "import type {Page} from 'custom';"),
    parameter('page.getByRole("button",{name:"Save"});', 'type Page=any;'),
    parameter('page=other;page.getByRole("button",{name:"Save"});'),
    parameter('page.getByRole=other;page.getByRole("button",{name:"Save"});'),
    parameter('function nested(page){page.getByRole("button",{name:"Save"});}'),
    parameter('page.getByRole("button",{name:"Save",exact:true});'),
    parameter('page.getByRole("button",{name:"Save",exact:false});'),
    parameter('page.getByRole("button",{name:dynamic});'),
    parameter('page.getByRole("button",{name:"Save",...options});'),
    parameter('page.getByRole("button",{name:"Save",name:"Other"});'),
    parameter('page["getByRole"]("button",{name:"Save"});'),
    parameter('page?.getByRole("button",{name:"Save"});'),
  ]) assert.deepEqual(scan(text).findings, [], text);
  const result = scan(parameter('page.getByRole("button",{name:"Save"});'));
  assert.deepEqual(result.findings.map(item => [item.patternId, item.disposition, item.evidence.kind]),
    [['#10c', 'candidate', 'unresolved-page']]);
});
test('typed Locator field actions require exact constructor linkage and bare unobserved action', () => {
  const locator = (body, assignment = 'this.button=page.getByRole("button");', prefix = header) =>
    prefix + `class P {readonly button:Locator; constructor(page:Page){${assignment}} ${body}}`;
  for (const text of [
    locator('run(){this.button.click();}'),
    locator('run(){this.button.click();}', 'this.button=page.getByRole("button");',
      "import type {Page,Locator} from '@playwright/test';"),
  ]) assert.deepEqual(scan(text).findings.filter(item => item.patternId === '#16').map(item => item.disposition), ['candidate']);
  for (const text of [
    locator('async run(){await this.button.click();}'),
    locator('run(){return this.button.click();}'),
    locator('async run(){await Promise.all([this.button.click()]);}'),
    locator('run(){this.button.click();}', 'this.button=custom();'),
    locator('run(){this.button.click();}', 'this.button=page.getByRole("button").all();'),
    locator('run(){this.button.click();}', '', header),
    locator('run(){this.button.click();}', 'this.button=page.getByRole("button");', "import type {Page,Locator} from 'foreign';"),
    locator('mutate(){this.button=other;}run(){this.button.click();}'),
    locator('mutate(){const button=this.button;button.click=other;}run(){this.button.click();}'),
    locator('run(){function nested(){this.button.click();}nested();}'),
    locator('run(){this.button?.click();}'),
  ]) assert.deepEqual(scan(text).findings.filter(item => item.patternId === '#16'), [], text);
});
