// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { createScope } from '../src/scope.mjs';
import { catchHandlers } from '../src/catch-handlers.mjs';

function run(body, prefix = "import {test,expect} from '@playwright/test';\n", name = 'recovery.spec.ts') {
  const filename = '/pinned-project/' + name, bytes = Buffer.from(prefix + body);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return catchHandlers(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const severities = body => run(body).findings.map(f => f.severity);

test('conservative state/count fallbacks in retry guards retain P1 review candidates', () => {
  for (const body of [
    'if (await button.isVisible().catch(() => false)) return;',
    'if (!(await button.isDisabled().catch(() => true))) return;',
    'if ((await option.count().catch(() => 0)) > 0) return;',
    'if ((await option.count().catch(() => 0)) === 0) continue;',
  ]) {
    const result = run(`async function recover(){ for (;;) { ${body} await retry(); } }`);
    assert.equal(result.findings.length, 1, body);
    assert.equal(result.findings[0].severity, 'P1', body);
    assert.equal(result.findings[0].disposition, 'candidate');
    assert.equal(result.findings[0].evidence.kind, 'conservative-observation-fallback');
  }
});

test('success fallbacks, returned observations and swallowed hard assertions remain P0', () => {
  for (const body of [
    'if (await button.isVisible().catch(() => true)) return;',
    'if ((await option.count().catch(() => 1)) > 0) return;',
    'return await button.isVisible().catch(() => false);',
    'await expect(button).toBeVisible().catch(() => false);',
  ]) assert.deepEqual(severities(`async function recover(){ ${body} }`), ['P0'], body);
  assert.deepEqual(severities("test('case', async ({page}) => { if (await page.getByRole('button').isVisible().catch(() => false)) { await page.getByRole('button').click(); } await expect(page.getByRole('dialog')).toBeVisible(); });"), ['P0']);
});

test('helper network-idle settling before a later hard operation is P1 and remains visible', () => {
  const result = run("async function open(){ await page.waitForLoadState('networkidle').catch(() => {}); await row.waitFor({state:'visible'}); }");
  assert.equal(result.findings.length, 1);
  assert.equal(result.findings[0].severity, 'P1');
  assert.equal(result.findings[0].evidence.kind, 'helper-settle-before-outcome');
  for (const tail of ['', 'if (ready) await row.waitFor();', 'await row.waitFor().catch(() => {});']) {
    assert.equal(run(`async function open(){ await page.waitForLoadState('networkidle').catch(() => {}); ${tail} }`).findings[0].severity, 'P0', tail);
  }
  assert.deepEqual(severities("test('case', async ({page}) => { await page.waitForLoadState('networkidle').catch(() => {}); await page.locator('x').waitFor(); });"), ['P0']);
});

test('forwarding a catch to an executor reject remains P1 pending caller proof', () => {
  for (const ctor of ['Promise', 'Cypress.Promise']) {
    const result = run(`new ${ctor}((resolve, reject) => { load().catch(error => { reject(new Error(error.message)); }); });`, ctor === 'Cypress.Promise' ? '' : undefined, ctor === 'Cypress.Promise' ? 'recovery.cy.ts' : undefined);
    assert.equal(result.findings.length, 1, ctor);
    assert.equal(result.findings[0].severity, 'P1', ctor);
    assert.equal(result.findings[0].evidence.kind, 'executor-rejection-forwarding');
  }
});

test('resolving, shadowing or replacing reject and custom constructors retain P0', () => {
  for (const body of [
    'new Promise((resolve,reject) => { load().catch(error => { resolve(error); }); });',
    'new Custom((resolve,reject) => { load().catch(error => { reject(error); }); });',
    'new Promise((resolve,reject) => { reject=custom; load().catch(error => { reject(error); }); });',
    'new Promise((resolve,reject) => { load().catch(reject => { reject(); }); });',
    'new Promise((resolve,reject) => { load().catch(error => { if (ready) reject(error); }); });',
    'const Promise=Custom; new Promise((resolve,reject) => { load().catch(error => { reject(error); }); });',
  ]) assert.deepEqual(severities(body), ['P0'], body);
});
