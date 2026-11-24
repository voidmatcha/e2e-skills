// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { controlFlow } from '../src/control-flow.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function run(text, name = 'example.cy.ts', additional = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-node-control-flow-')));
  for (const [file, content] of Object.entries({ [name]: text, ...additional })) fs.writeFileSync(path.join(root, file), content);
  const manifest = inventory(root);
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  return controlFlow(sources.get(path.join(root, name)), path.join(root, name), { scope });
}

test('#3b keeps blanket, scoped, asserting and referenced handlers as P0 candidates', () => {
  const result = run([
    "cy.on('uncaught:exception', () => false);",
    "Cypress.on('uncaught:exception', err => { if(err.message==='known') return false; });",
    "cy.on('uncaught:exception', err => { expect(err.message).to.equal('expected'); });",
    "Cypress.on('uncaught:exception', existingHandler);",
  ].join('\n'), 'support.ts');
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.severity, f.disposition, f.line]),
    [1, 2, 3, 4].map(line => ['#3b', 'P0', 'candidate', line]));
});

test('#11c retains reasoned and conditional skip candidates without semantic promotion', () => {
  const result = run("import {test} from '@playwright/test';\n" + [
    "test.skip('unexplained',async()=>{});",
    '// Tracked in ISSUE-123; expires next week.',
    "test.skip('documented',async()=>{});",
    "test.skip(({browserName})=>browserName==='webkit', 'unsupported clipboard');",
    "test.fixme('later',async()=>{});",
  ].join('\n'), 'example.spec.ts');
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.severity, f.disposition, f.line]),
    [2, 4, 5, 6].map(line => ['#11c', 'P2', 'candidate', line]));
});

test('Cypress skip, suite and x-prefixed shorthands require unshadowed framework globals', () => {
  const result = run("it.skip('x',()=>{});\ndescribe.skip('x',()=>{});\nsuite.skip('x',()=>{});\nxit('x',()=>{});\nxdescribe('x',()=>{});\n");
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(result.findings.map(f => [f.patternId, f.line]), [1, 2, 3, 4, 5].map(line => ['#11c', line]));
});

test('local/imported Cypress lookalikes, foreign tests, comments and strings are excluded', () => {
  for (const text of [
    "function other(cy,Cypress){cy.on('uncaught:exception',()=>false);Cypress.on('uncaught:exception',()=>false);}",
    "const cy={on(){}}; cy.on('uncaught:exception',()=>false);",
    "import {Cypress} from './helper'; Cypress.on('uncaught:exception',()=>false);",
    "import {test,it,describe} from 'vitest'; test.skip('x',()=>{}); it.skip('x',()=>{}); describe.skip('x',()=>{});",
    "function other(it,suite,xit,xdescribe){it.skip('x',()=>{});suite.skip('x',()=>{});xit('x',()=>{});xdescribe('x',()=>{});}",
    "// cy.on('uncaught:exception',()=>false);\nconst text=\"cy.on('uncaught:exception',()=>false);\";",
  ]) assert.deepEqual(run(text).findings, [], text);
});

test('other Cypress events are excluded while dynamic events remain diagnostic', () => {
  const known = run("cy.on('window:before:load',()=>{});\nCypress.on('fail',()=>false);\n");
  assert.deepEqual(known, { findings: [], diagnostics: [] });
  const dynamic = run('Cypress.on(eventName,()=>false);');
  assert.deepEqual(dynamic.findings, []);
  assert.match(dynamic.diagnostics[0].message, /event name is not statically known/);
});

test('optional calls and method references are outside the direct call slice', () => {
  const result = run("cy?.on('uncaught:exception',()=>false);\ncy.on?.('uncaught:exception',()=>false);\nconst on=cy.on;\nconst skip=it.skip;\n");
  assert.deepEqual(result.findings, []);
});

test('Playwright aliases/reexports use shared scope and unresolved roots remain diagnostic', () => {
  const aliased = run("import {scenario} from './fixture';\nscenario.skip('x',()=>{});\n", 'example.spec.ts',
    { 'fixture.ts': "export {test as scenario} from '@playwright/test';" });
  assert.deepEqual(aliased.diagnostics, []);
  assert.deepEqual(aliased.findings.map(f => [f.patternId, f.line]), [['#11c', 2]]);
  const unknown = run("import {test} from './missing';\ntest.skip('x',()=>{});", 'example.spec.ts');
  assert.deepEqual(unknown.findings, []);
  assert.ok(unknown.diagnostics.length);
  assert.ok(run('function (').diagnostics.length);
  assert.match(controlFlow(Buffer.from('it.skip()'), 'example.cy.ts').diagnostics[0].message, /scope is required/);
});

test('runtime and test-shorthand mutations remain diagnostic through shared Cypress proof', () => {
  for(const text of ["cy=custom;cy.on('uncaught:exception',()=>false);", "Cypress.on=custom;Cypress.on('uncaught:exception',()=>false);",
    "({Cypress}=custom);Cypress.on('uncaught:exception',()=>false);", "it.skip=custom;it.skip('x',()=>{});", "suite=custom;suite.skip('x',()=>{});", "xit=custom;xit('x',()=>{});"]) {
    const result=run(text);
    assert.deepEqual(result.findings,[],text);
    assert.ok(result.diagnostics.some(item=>/mutated Cypress global/.test(item.message)),text);
  }
  assert.equal(run("function f(Cypress){Cypress.on=custom;}\nCypress.on('uncaught:exception',()=>false);").findings.length,1);
});
