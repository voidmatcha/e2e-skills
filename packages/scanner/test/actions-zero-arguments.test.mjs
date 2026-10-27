// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {test} from 'node:test';
import {actions} from '../src/actions.mjs';
import {createScope} from '../src/scope.mjs';

function run(text, name = 'zero-arguments.spec.ts') {
  const file = '/pinned-project/' + name, bytes = Buffer.from(text);
  const manifest = {
    schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: {canonical: '/pinned-project', kind: 'directory'},
    candidates: [{path: file, identity: {
      size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex'),
    }}],
  };
  return actions(bytes, file, {scope: createScope({manifest, sources: new Map([[file, bytes]])})});
}

test('unresolved no-argument action cannot contain a force option', () => {
  const result = run('makeButton().click();');
  assert.deepEqual(result, {findings: [], diagnostics: []});
});

test('POM parameter-property no-argument action needs no receiver proof', () => {
  const result = run(`import {Page} from '@playwright/test';
class LoginPage {
  constructor(private page: Page) {}
  async submit() { await this.page.getByRole('button', {name: 'Submit'}).click(); }
}`);
  assert.deepEqual(result, {findings: [], diagnostics: []});
});

test('unresolved action with literal force stays diagnosed', () => {
  const result = run('makeButton().click({force:true});');
  assert.deepEqual(result.findings, []);
  assert.ok(result.diagnostics.some(item => /unsupported/.test(item.message)));
});

test('proven Playwright literal force remains a confirmed finding beside no-argument action', () => {
  const result = run(`import {test} from '@playwright/test';
test('submit', async ({page}) => {
  makeButton().click();
  await page.getByRole('button').click({force:true});
});`);
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(item => [item.patternId, item.severity, item.disposition, item.line]),
    [['#5b', 'P1', 'confirmed', 4]]);
});

test('unresolved spread arguments still require receiver proof', () => {
  const result = run('makeButton().click(...options);');
  assert.deepEqual(result.findings, []);
  assert.ok(result.diagnostics.length);
});

test('proven Playwright spread options remain diagnosed', () => {
  const result = run(`import {test} from '@playwright/test';
test('submit', async ({page}) => {
  await page.getByRole('button').click({...options});
});`);
  assert.deepEqual(result.findings, []);
  assert.ok(result.diagnostics.some(item => /spread/.test(item.message)));
});

test('mutated Cypress chain no-argument action cannot contain a force option', () => {
  const result = run("cy.get=custom; cy.get('button').click();", 'zero-arguments.cy.ts');
  assert.deepEqual(result, {findings: [], diagnostics: []});
});

test('mutated Cypress chain with literal force stays diagnosed', () => {
  const result = run("cy.get=custom; cy.get('button').click({force:true});", 'zero-arguments.cy.ts');
  assert.deepEqual(result.findings, []);
  assert.ok(result.diagnostics.length);
});
