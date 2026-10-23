// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { pageReads } from '../src/page-reads.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function fixture(t, entries) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'page-reads-review-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.writeFileSync(path.join(root, 'package.json'), '{}');
  for (const [name, text] of Object.entries(entries)) {
    const file = path.join(root, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, text);
  }
  const manifest = inventory(root);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  return { root, read(name) {
    const file = path.join(root, name);
    return pageReads(sources.get(file), file, { scope });
  } };
}
const cli = new URL('../src/cli.mjs', import.meta.url).pathname;
function scan(root) {
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'none'],
    { encoding: 'utf8', timeout: 30_000 });
  assert.equal(result.status, 0, result.stderr + result.stdout);
  const report = JSON.parse(result.stdout);
  assert.equal(report.execution.complete, true);
  assert.deepEqual(report.execution.diagnostics, []);
  return report;
}

// Original semantic fixture bytes: assert_expect_aliases_and_page_receiver_provenance.
const aliases = "import { expect as verify, test, type Page } from '@playwright/test';\n" +
  'let browserPage: Page;\n' +
  "test('aliases', async () => {\n" +
  "  verify(browserPage.url()).toBe('/ready');\n" +
  "  verify.soft(browserPage.getByRole('status')).toBeVisible();\n" +
  "  await browserPage.click('#legacy-selector');\n" +
  '});\n';
test('original uninitialized Page fixture retains both anchors as candidates, never runtime proof', t => {
  const { root, read } = fixture(t, { 'aliases.spec.ts': aliases });
  const result = read('aliases.spec.ts');
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.line, f.disposition]),
    [['#4h', 4, 'candidate'], ['#17', 6, 'candidate']]);
  for (const finding of result.findings) {
    assert.equal(finding.severity, 'P1');
    assert.deepEqual(finding.evidence.requirements, ['verify-runtime-binding', 'verify-required-test-outcome']);
    assert.ok(aliases.slice(finding.start, finding.end).includes('browserPage'));
  }
  const report = scan(root);
  assert.deepEqual(report.findings.filter(f => ['#4h', '#17', '#18'].includes(f.patternId))
    .map(f => [f.patternId, f.line, f.disposition]).sort(),
  [['#17', 6, 'candidate'], ['#18', 5, 'candidate'], ['#4h', 4, 'candidate']]);
  assert.equal(report.review.required, true);
  assert.ok(!report.findings.some(f => f.patternId === '#19' && f.line === 2));
});

// Original semantic fixture bytes: assert_playwright_rules_skip_cypress_only_files_but_allow_mixed_files.
const cypressOnly = "describe('cypress only', () => {\n" +
  "  it('uses an unrelated page helper', () => {\n" +
  "    cy.visit('/');\n" +
  "    page.click('#helper');\n" +
  '    page.waitForTimeout(100);\n' +
  "    test.describe.serial('helper suite', () => {});\n" +
  '  });\n});\n';
const mixed = "import { test } from '@playwright/test';\n" +
  "cy.log('mixed migration file');\n" +
  "page.click('#playwright-selector');\n";
test('original mixed Cypress file retains ambient Page candidate without changing Cypress-only negatives', t => {
  const { root, read } = fixture(t, {
    'cypress/e2e/cypress-only.cy.ts': cypressOnly,
    'cypress/e2e/mixed.cy.ts': mixed,
  });
  assert.deepEqual(read('cypress/e2e/cypress-only.cy.ts'), { findings: [], diagnostics: [] });
  const result = read('cypress/e2e/mixed.cy.ts');
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.line, f.disposition]), [['#17', 3, 'candidate']]);
  assert.equal(result.findings[0].evidence.kind, 'unresolved-page');
  const report = scan(root);
  assert.deepEqual(report.findings.map(f => [path.basename(f.file), f.patternId, f.line, f.disposition]),
    [['mixed.cy.ts', '#17', 3, 'candidate']]);
  assert.equal(report.counts.confirmed, 0);
});

test('official renamed or inline Page annotations provide only candidate evidence', t => {
  for (const declaration of [
    "import {type Page as BrowserPage} from '@playwright/test';let browserPage:BrowserPage;",
    "let browserPage:import('@playwright/test').Page;",
  ]) {
    const text = "import {test,expect} from '@playwright/test';\n" + declaration +
      "\ntest('x',()=>{expect(browserPage.url()).toBe('/');browserPage.click('#x');});";
    const result = fixture(t, { 'case.spec.ts': text }).read('case.spec.ts');
    assert.deepEqual(result.diagnostics, []);
    assert.deepEqual(result.findings.map(f => [f.patternId, f.disposition]), [['#4h', 'candidate'], ['#17', 'candidate']]);
  }
});

test('typed candidate URL reads respect proven retry wrappers and alias expect identity', t => {
  const text = "import {test,expect as verify,type Page} from '@playwright/test';let browserPage:Page;" +
    "test('x',async()=>{await verify(()=>{verify(browserPage.url()).toBe('/');}).toPass();" +
    "await verify.poll(()=>{verify(browserPage.url()).toBe('/');return browserPage.url();}).toBe('/');});";
  assert.deepEqual(fixture(t, { 'case.spec.ts': text }).read('case.spec.ts'), { findings: [], diagnostics: [] });
});

test('custom, shadowed, initialized, written and foreign types cannot enter the module Page candidate slice', t => {
  const prelude = "import {test,expect,type Page} from '@playwright/test';";
  for (const code of [
    "type LocalPage={url():string;click(s:string):void};let browserPage:LocalPage;",
    "import type {Page as OtherPage} from 'other';let browserPage:OtherPage;",
    "let browserPage:Page={url(){return '/';},click(){}};",
    "let browserPage:Page;browserPage=custom;",
    "let browserPage:Page;browserPage.click=custom;",
    "let browserPage:Page;const alias=browserPage;alias.click=custom;",
    "let browserPage:Page;Object.assign(browserPage,custom);",
  ]) {
    const text = prelude + code + "test('x',()=>{expect(browserPage.url()).toBe('/');browserPage.click('#x');});";
    assert.deepEqual(fixture(t, { 'case.spec.ts': text }).read('case.spec.ts').findings, [], code);
  }
  const shadow = prelude + "let browserPage:Page;test('x',()=>{function f(browserPage){expect(browserPage.url()).toBe('/');browserPage.click('#x');}});";
  assert.deepEqual(fixture(t, { 'case.spec.ts': shadow }).read('case.spec.ts').findings, []);
});

test('ambient Page candidates exclude foreign, shadowed, escaped, aliased and mutated roots', t => {
  const prelude = "import {test} from '@playwright/test';\n";
  for (const text of [
    "import {test} from 'vitest';page.click('#x');",
    "// @playwright/test\npage.click('#x');",
    prelude + "const page={click(){}};page.click('#x');",
    prelude + "function f(page){page.click('#x');}",
    prelude + "page=custom;page.click('#x');",
    prelude + "page.click=custom;page.click('#x');",
    prelude + "delete page.click;page.click('#x');",
    prelude + "Object.assign(page,custom);page.click('#x');",
    prelude + "const alias=page;alias.click=custom;page.click('#x');",
    prelude + "use(page);page.click('#x');",
    prelude + "page?.click('#x');",
    prelude + "page.click(42);",
  ]) assert.deepEqual(fixture(t, { 'case.spec.ts': text }).read('case.spec.ts').findings, [], text);
});

test('typed parameters and unresolved imported runtime bindings still produce explicit gaps', t => {
  const typed = "import {expect,type Page} from '@playwright/test';function f(page:Page){page.click('#x');expect(page.url()).toBe('/');}";
  const result = fixture(t, { 'case.spec.ts': typed }).read('case.spec.ts');
  assert.deepEqual(result.findings, []);
  assert.equal(result.diagnostics.length, 2);
  const missing = "import {test,expect} from './absent';test('x',({page})=>{page.click('#x');expect(page.url()).toBe('/');});";
  const unresolved = fixture(t, { 'case.spec.ts': missing }).read('case.spec.ts');
  assert.deepEqual(unresolved.findings, []);
  assert.ok(unresolved.diagnostics.length);
});
