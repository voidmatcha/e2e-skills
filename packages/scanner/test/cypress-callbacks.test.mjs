// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { cypressCallbacks } from '../src/cypress-callbacks.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function scan(text, name = 'case.cy.ts') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-cy-callback-')));
  const file = path.join(root, name), bytes = Buffer.from(text);
  fs.writeFileSync(file, bytes);
  const manifest = inventory(root), scope = createScope({ manifest, sources: new Map([[file, bytes]]) });
  return cypressCallbacks(bytes, file, { scope });
}
const ids = result => result.findings.map(x => x.patternId);

test('async test callbacks queue Cypress commands; native-only and nested helpers do not', () => {
  const result = scan(`it('arrow',async()=>{await cy.get('x')});
test('expression',async()=>cy.visit('/'));
specify('function',async function named(){cy.get('x')});
it('native-only',async()=>{await Promise.resolve(1)});
it('deferred',async()=>{const helper=()=>cy.get('x');});
it('no async',()=>{cy.get('x')});
it('no sibling bleed',async()=>Promise.resolve(1));
it('later',()=>cy.get('x'));`);
  assert.deepEqual(ids(result), ['#10d','#10d','#10d']);
  assert.ok(result.findings.every(x => x.severity === 'P1' && x.disposition === 'candidate'));
});

test('async callbacks and commands require unshadowed, unmodified shared Cypress globals', () => {
  for (const source of [
    "import {it} from 'vitest';it('foreign',async()=>cy.get('x'));",
    "import {test} from '@playwright/test';test('pw',async({page})=>page.click('x'));",
    "function f(it){it('local',async()=>cy.get('x'));}",
    "function f(cy){it('local',async()=>cy.get('x'));}",
    "cy.get=custom;it('changed',async()=>cy.get('x'));",
    "it=custom;it('changed',async()=>cy.get('x'));",
  ]) assert.deepEqual(ids(scan(source)), [], source);
  assert.deepEqual(ids(scan("const text=\"it('fake',async()=>cy.get('x'))\"; /* cy.get('x').click().should('exist'); */")), []);
});

test('all legacy action/continuation spellings remain P1 candidates', () => {
  const actions = ['click','type','check','uncheck','select','selectFile','trigger','scrollIntoView'];
  const continuations = ['should','and','click','type','check','uncheck','select','trigger'];
  const result = scan(actions.map(action => `cy.get('x').${action}().should('exist');`).join('\n') + '\n' +
    continuations.map(next => `cy.get('x').click().${next}();`).join('\n'));
  assert.equal(result.findings.length, actions.length + continuations.length);
  assert.ok(result.findings.every(x => x.patternId === '#10f' && x.disposition === 'candidate' && x.severity === 'P1'));
});

test('continued chains follow AST statement boundaries and balanced arguments', () => {
  const result = scan(`cy.get('first').click();
cy.get('second').click().should('exist');
cy.get('third').click()
cy.get('fourth').should('exist')
cy.get('multi')
.type(fn(1,{a:2}))
.and('exist');
cy.get('single').click();cy.get('same-line').click().should('exist');`);
  assert.deepEqual(result.findings.map(x => x.line), [2,6,8]);
  assert.deepEqual(ids(scan("cy.get('x').should('exist').click();cy.get('x').click().then(()=>{});")), []);
});

test('foreign, shadowed and mutable action roots cannot inherit Cypress chain identity', () => {
  for (const source of [
    "const custom={click(){return this},should(){}};custom.click().should();",
    "function f(cy){cy.get('x').click().should('exist');}",
    "cy=custom;cy.get('x').click().should('exist');",
    "cy.get=custom;cy.get('x').click().should('exist');",
    "const alias=cy.get('x');alias.click().should('exist');",
  ]) assert.deepEqual(ids(scan(source)), [], source);
});

test('optional/computed action shapes and absent pinned scope are not coverage claims', () => {
  const result = scan("cy.get('x').click?.().should('exist');cy['get']('x').click().should('exist');cy.get('x')['click']().should('exist');");
  assert.deepEqual(result.findings, []);
  assert.ok(result.diagnostics.length >= 3);
  assert.deepEqual(cypressCallbacks(Buffer.from("cy.get('x').click().should('exist');"),'x.cy.ts').findings, []);
});

test('async hooks use the distinct shared Cypress hook identity and preserve guards', () => {
  for (const hook of ['before','beforeEach','after','afterEach']) {
    assert.deepEqual(ids(scan(`${hook}(async()=>{await cy.visit('/settings')});`)), ['#10d']);
    assert.deepEqual(ids(scan(`function f(${hook}){${hook}(async()=>cy.get('x'));}`)), []);
    assert.deepEqual(ids(scan(`${hook}=custom;${hook}(async()=>cy.get('x'));`)), []);
  }
});
