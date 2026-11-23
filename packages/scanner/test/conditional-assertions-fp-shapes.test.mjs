// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';

function run(text, name = 'case.cy.ts') {
  const filename = '/pinned/' + name, bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return conditionalAssertions(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const gates = result => result.findings.filter(f => f.variant === 'conditional-assertion');
const tiers = result => gates(result).map(f => f.severity);
const pw = text => "import {test, expect} from '@playwright/test';\n" + text;

test('declaration gates retain P1 coverage candidates; executing environment gates retain P0 (P001-P004/P007/P017 vs P018)', () => {
  for (const body of [
    "if(Cypress.env('AUTH')) describe('auth',()=>{ it('works',()=>{cy.get('main').should('exist');}); });",
    "describe('mobile',()=>{if(isMobile()) it('works',()=>{cy.get('main').should('exist');});});",
  ]) {
    const result = run(body);
    assert.deepEqual(tiers(result), ['P1']);
    assert.equal(gates(result)[0].evidence.kind, 'conditional-test-registration');
  }
  assert.deepEqual(tiers(run("it('privacy',()=>{if(Cypress.env('GOV_CLOUD')) {cy.get('input').should('be.disabled');}});")), ['P0']);
  // Playwright registration callbacks already remain outside the inline
  // assertion slice; preserve that diagnostic instead of inventing a row.
  const playwright = run(pw("if(flag) test.describe('d',()=>{test('t',async({page})=>{await expect(page).toHaveTitle('ok');});});"), 'case.spec.ts');
  assert.deepEqual(tiers(playwright), []);
  assert.ok(playwright.diagnostics.some(item => /deferred function/.test(item.message)));
  assert.deepEqual(tiers(run("it('outer',()=>{if(flag) it('inner',()=>{cy.get('x').should('exist');});});")), ['P0']);
  assert.deepEqual(tiers(run("if(flag) { cy.get('main').should('exist'); describe('d',()=>{it('t',()=>cy.get('x').should('exist'));}); }")), ['P0']);
  // A shadowed registration cannot borrow framework provenance.
  assert.deepEqual(tiers(run("function f(describe){if(flag) describe('d',()=>{cy.get('x').should('exist');});}")), []);
});

test('assertion dispatch with an unconditional returned matcher remains P1; an assertion-free return remains P0 (P060)', () => {
  const dispatch = "function check(el, state){if(state.includes('visible')) return expect(el).toBeVisible();\n" +
    "if(state.includes('checked')) return expect(el).toBeChecked();\nreturn expect(el).toBeVisible();}";
  const result = run(pw(dispatch), 'helper.ts');
  assert.deepEqual(tiers(result), ['P1', 'P1']);
  assert.ok(gates(result).every(f => f.disposition === 'candidate' && f.evidence.kind === 'assertion-dispatch-fallthrough'));
  assert.deepEqual(tiers(run(pw(dispatch.replace('return expect(el).toBeVisible();}', 'return;}')), 'helper.ts')), ['P0', 'P0']);
  assert.deepEqual(tiers(run(pw("function f(el,state){if(state) return expect(el).toBeVisible(); if(other) return; return expect(el).toBeVisible();}"), 'helper.ts')), ['P0']);
});

test('helper input option with independent proof remains P1; product-row reads and lone option oracles retain P0 (P009/P013-P015 vs P020)', () => {
  const prefix = "function edit(options){";
  const gate = "if(options.description != undefined) cy.get('textarea').should('be.visible').type(options.description);";
  const result = run(prefix + gate + "cy.url().should('include','/done');}");
  assert.deepEqual(tiers(result), ['P1']);
  assert.equal(gates(result)[0].evidence.kind, 'input-option-with-independent-assertion');
  assert.deepEqual(tiers(run(prefix + gate + '}')), ['P0']);
  assert.deepEqual(tiers(run(prefix + gate + "flag && cy.url().should('include','/done');}")), ['P0']);
  assert.deepEqual(tiers(run("function check(property){cy.get('tr').should('exist').each(($row)=>{if($row.text().includes(property)) cy.wrap($row).should('exist');});}")), ['P0']);
  assert.deepEqual(tiers(run("function check(options){options.description = read();" + gate + "cy.url().should('include','/done');}")), ['P0']);
});
