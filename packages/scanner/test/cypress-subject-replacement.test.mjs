// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pageReads } from '../src/page-reads.mjs';
import { domQueries } from '../src/dom-queries.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function scan(text, detector, name = 'case.cy.ts') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-cypress-subject-')));
  try {
    const file = path.join(root, name), bytes = Buffer.from(text);
    fs.writeFileSync(file, bytes);
    const manifest = inventory(root);
    assert.equal(manifest.complete, true);
    const scope = createScope({ manifest, sources: new Map([[file, bytes]]) });
    return detector(bytes, file, { scope });
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}

test('proven Cypress command actions do not require Playwright Page provenance', () => {
  const result = scan([
    "cy.getBySel('signup-first-name').type(userInfo.firstName);",
    "cy.getBySelLike('user-list-item').contains(name).click({force:true});",
    "cy.get('.row').find('input').type(value);",
    "cy.wrap(value).type('x');cy.task('db').then(handler).click('x');",
  ].join('\n'), pageReads);
  assert.deepEqual(result, { findings: [], diagnostics: [] });
});

test('Cypress applicability does not suppress Playwright or unknown receiver diagnostics', () => {
  const mixed = scan("import {test} from '@playwright/test';test('x',({page:cy})=>{cy.click('#x');});", pageReads);
  assert.equal(mixed.findings.length, 1);
  assert.equal(mixed.findings[0].patternId, '#17');
  for (const prefix of [
    'cy=custom;', 'cy.getBySel=custom;', 'Object.assign(cy,{getBySel:custom});',
    'const alias=cy;alias.getBySel=custom;', 'globalThis.cy=custom;',
  ]) {
    const result = scan(prefix+"cy.getBySel('x').type('value');", pageReads);
    assert.deepEqual(result.findings, [], prefix);
    assert.ok(result.diagnostics.length, prefix);
  }
  const unknown = scan("import {screen} from './missing';screen.get('x').type('value');", pageReads);
  assert.ok(unknown.diagnostics.length);
});

test('custom Cypress positional calls retain exact source locations and unresolved subject evidence', () => {
  const result = scan([
    "cy.getBySel('row').first();",
    "cy.getBySelLike('item').find('button').last();",
    "cy.customRows('row').customFilter().first();",
    "cy.get('.row').customTransform().nth(2);",
  ].join('\n'), domQueries);
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId,f.severity,f.disposition,f.line]),
    [1,2,3,4].map(line => ['#10a','P1','candidate',line]));
  for (const finding of result.findings) assert.deepEqual(finding.evidence, {
    kind: 'unresolved-cypress-subject',
    requirements: ['verify-cypress-command-subject', 'verify-positional-selection-intent'],
  });
  const known = scan("cy.get('.row').find('button').first();", domQueries);
  assert.equal(known.findings.length, 1);
  assert.equal(known.findings[0].evidence, undefined);
});

test('custom Cypress subject candidates require positional syntax, never arbitrary custom commands', () => {
  const result = scan("cy.getBySel('row').click();cy.customRows().should('exist');", domQueries);
  assert.deepEqual(result, { findings: [], diagnostics: [] });
  for (const text of [
    "cy.getBySel('row').first?.();", "cy.getBySel('row')['first']();",
    "cy['getBySel']('row').first();", "cy?.getBySel('row').first();",
    "cy.getBySel(...args).first();", "cy.getBySel('row').first('unsupported');",
  ]) {
    const result = scan(text, domQueries);
    assert.deepEqual(result.findings, [], text);
    assert.ok(result.diagnostics.length, text);
  }
});

test('array helper first/last arguments are outside the positional Locator operation', () => {
  const result = scan("import _ from 'lodash';_.last(url.split('?'));_.first(values);", domQueries);
  assert.deepEqual(result, { findings: [], diagnostics: [] });
});

test('known subject replacements never become unresolved custom DOM candidates', () => {
  for (const text of [
    "cy.wrap([]).first();", "cy.task('db').customRows().first();",
    "cy.customRows().then(handler).first();", "cy.customRows().invoke('text').first();",
    "cy.get('.row').its('length').first();", "cy.request('/api').first();",
    "cy.wait('@items').first();", "cy.readFile('file').first();",
  ]) {
    const result = scan(text, domQueries);
    assert.deepEqual(result.findings, [], text);
    assert.ok(result.diagnostics.length, text);
  }
});

test('foreign, shadowed and mutated cy cannot establish custom subject candidates', () => {
  for (const text of [
    "import {cy} from 'other';cy.getBySel('x').first();",
    "function f(cy){cy.getBySel('x').first();}",
    "const cy={getBySel:()=>({first(){}})};cy.getBySel('x').first();",
    "cy.getBySel=custom;cy.getBySel('x').first();",
    "const alias=cy;Object.assign(alias,{getBySel:custom});cy.getBySel('x').first();",
    "globalThis.cy=custom;cy.getBySel('x').first();",
    "database.query().first();",
  ]) assert.deepEqual(scan(text, domQueries).findings, [], text);
});
