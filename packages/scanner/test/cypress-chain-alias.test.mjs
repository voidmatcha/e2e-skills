// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { cypressCallbacks } from '../src/cypress-callbacks.mjs';
import { cypressAssignment } from '../src/cypress-assignment.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function scan(text) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-cy-chain-alias-')));
  try {
    const file = path.join(root, 'commands.cy.ts'), bytes = Buffer.from(text);
    fs.writeFileSync(file, bytes);
    const scope = createScope({ manifest: inventory(root), sources: new Map([[file, bytes]]) });
    return { ...cypressCallbacks(bytes, file, { scope }), assignments: cypressAssignment(bytes, file, { scope }).findings };
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const continued = result => result.findings.filter(hit => hit.patternId === '#10f');
const callback = body => `it('case', async () => {${body}});`;

test('original S6 retains continued aliased action alongside async and assignment findings', () => {
  const result = scan(`it('bad command model', async () => {
  const button = cy.get('[data-cy=save]');
  await button.type('Ada').should('have.value', 'Ada');
});

it('safe command model', () => {
  const expected = 'Saved';
  cy.get('[data-cy=save]').should('be.enabled').click();
  cy.get('[role=status]').should('have.text', expected);
});
`);
  assert.deepEqual(result.findings.map(hit => hit.patternId), ['#10d', '#10f']);
  assert.deepEqual(result.assignments.map(hit => hit.patternId), ['#10e']);
  assert.equal(continued(result)[0].line, 3);
  assert.equal(continued(result)[0].disposition, 'candidate');
  assert.equal(continued(result)[0].severity, 'P1');
  assert.deepEqual(result.diagnostics, []);
});

test('typed and multiline callback-local chains preserve action anchors, not safe terminal actions', () => {
  const result = scan(`beforeEach(() => {
const button: Cypress.Chainable = cy.get('button').find('input');
button.type('text')
.should('have.value', 'text');
button.should('be.enabled').click();
});`);
  assert.deepEqual(continued(result).map(hit => hit.line), [3]);
  assert.deepEqual(result.diagnostics, []);
});

test('mutable and escaped proven chain aliases remain uncertain with diagnostics', () => {
  for (const body of [
    "let button=cy.get('x');button.click().should('exist');",
    "const button=cy.get('x');button=other;button.click().should('exist');",
    "const button=cy.get('x');button.click=other;button.click().should('exist');",
    "const button=cy.get('x');Object.assign(button,{click:other});button.click().should('exist');",
    "const button=cy.get('x');mutate(button);button.click().should('exist');",
    "const button=cy.get('x');const saved={button};button.click().should('exist');",
    "const button=cy.get('x');const other=button;button.click().should('exist');",
    "const button=cy.get('x');button.click().should('exist');return button;",
    "const button=cy.get('x');function nested(){button.click().should('exist');}",
    "const button=cy.get('x');button?.click().should('exist');",
    "const button=cy.get('x');button['click']().should('exist');",
    "const button=cy['get']('x');button.click().should('exist');",
    "const button=cy.get?.('x');button.click().should('exist');",
  ]) {
    const result = scan(callback(body));
    assert.deepEqual(continued(result), [], body);
    assert.ok(result.diagnostics.length > 0, body);
  }
});

test('shadowed globals, foreign objects and callback identities never borrow Cypress proof', () => {
  for (const source of [
    "function f(cy){it('x',()=>{const button=cy.get('x');button.click().should('exist');});}",
    "cy.get=custom;it('x',()=>{const button=cy.get('x');button.click().should('exist');});",
    "function f(it){it('x',()=>{const button=cy.get('x');button.click().should('exist');});}",
    "import {it} from 'vitest';it('x',()=>{const button=cy.get('x');button.click().should('exist');});",
    callback("const button=custom.get('x');button.click().should('exist');"),
    callback("const button={click(){return this},should(){}};button.click().should('exist');"),
    callback("const button=cy.get('x');function nested(button){button.click().should('exist');}"),
    callback("const button=cy;button.click().should('exist');"),
    callback("const button=cy.spy(object,'method');button.click().should('exist');"),
    "const button=cy.get('x');button.click().should('exist');",
  ]) assert.deepEqual(continued(scan(source)), [], source);
});
