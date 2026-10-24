// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { promises } from '../src/promises.mjs';
import { createScope } from '../src/scope.mjs';

function scan(body) {
  const filename = '/pinned-project/action-catch.spec.ts';
  const bytes = Buffer.from(`import {test} from '@playwright/test';
test('action catch', async ({page}) => {
${body}
});`);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return promises(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const labels = result => result.findings.map(({ patternId, disposition }) => [patternId, disposition]);

test('awaited, returned and aggregated direct action catch chains consume the action promise', () => {
  for (const body of [
    "await page.goto('/').catch(() => {});",
    "await (page.goto('/')).catch(() => {}).catch(() => {});",
    "return page.goto('/').catch(() => {});",
    "const navigate = () => page.goto('/').catch(() => {});",
    "await Promise.all([page.goto('/').catch(() => {})]);",
    "await page.getByRole('button').click().catch(() => {});",
    "const button = page.locator('button'); await button.click().catch(() => {});",
  ]) assert.deepEqual(scan(body), { findings: [], diagnostics: [] }, body);
});

test('floating, saved, wrapped, optional and computed catch chains remain candidates', () => {
  for (const body of [
    "page.goto('/').catch(() => {});",
    "void page.goto('/').catch(() => {});",
    "const saved = page.goto('/').catch(() => {}); await saved;",
    "await wrapper(page.goto('/').catch(() => {}));",
    "await page.goto('/').catch?.(() => {});",
    "await page.goto('/')['catch'](() => {});",
    "await page.goto?.('/').catch(() => {});",
    "await page['goto']('/').catch(() => {});",
    "Promise.all([page.goto('/').catch(() => {})]);",
    "const Promise = custom; await Promise.all([page.goto('/').catch(() => {})]);",
  ]) assert.deepEqual(labels(scan(body)), [['#16', 'candidate']], body);
});

test('nested action callbacks cannot borrow the outer catch await', () => {
  for (const body of [
    "await page.goto('/').catch(() => { page.locator('button').click(); });",
    "await page.goto('/').catch(() => { page.goto('/next').catch(() => {}); });",
    "await page.goto('/').catch(() => wrapper(page.goto('/next')));",
  ]) {
    const result = scan(body);
    assert.equal(result.findings.length, 1, body);
    assert.equal(result.findings[0].patternId, '#16', body);
    assert.equal(result.findings[0].line, 3, body);
    assert.equal(result.findings[0].column, body.lastIndexOf('page.') + 1, body);
  }
  assert.deepEqual(labels(scan("await page.goto('/').catch(() => { page.goto('/next'); });")),
    [['#16', 'confirmed']]);
  assert.deepEqual(labels(scan("await page.goto('/').catch(() => page.goto('/next'));")), []);
});

test('custom and shadowed action receivers gain no Playwright promise findings', () => {
  for (const body of [
    "const custom = {goto() {}}; custom.goto().catch(() => {});",
    "function nested(page) { page.goto('/').catch(() => {}); }",
    "const custom = {click() {}}; await custom.click().catch(() => { page.goto('/next'); });",
  ]) {
    const result = scan(body);
    if (body.includes('/next')) assert.deepEqual(labels(result), [['#16', 'confirmed']]);
    else assert.deepEqual(result.findings, [], body);
  }
});
