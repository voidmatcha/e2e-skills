// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { test } from 'node:test';
import { stateReads } from '../src/state-reads.mjs';
import { createScope } from '../src/scope.mjs';

function run(text) {
  const filename = '/pinned-project/example.spec.ts', bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned-project', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  return stateReads(bytes, filename, {scope: createScope({manifest, sources: new Map([[filename, bytes]])})});
}
const scenario = expression => "import {test,expect} from '@playwright/test';\n" +
  `test('status',async({page})=>{ const a=page.getByTestId('ready'); const b=page.getByTestId('cached'); ${expression} });`;

test('original either-status assertion retains its exact source anchor as a candidate', () => {
  const bytes = fs.readFileSync(new URL('../../../skills/e2e-reviewer/evals/files/assertion-contracts.spec.ts', import.meta.url));
  const result = run(bytes.toString('utf8'));
  assert.ok(result.findings.some(f => f.patternId === '#4c-4e' && f.line === 17 && f.disposition === 'candidate'));
  assert.deepEqual(result.diagnostics, []);
});

test('AND and OR state reads remain candidates, while retries and custom values do not borrow this lane', () => {
  for (const operator of ['&&', '||']) {
    const result = run(scenario(`expect((await a.isVisible()) ${operator} (await b.isVisible())).toBe(true);`));
    assert.equal(result.findings.length, 1);
    assert.deepEqual(result.diagnostics, []);
  }
  for (const expression of [
    "expect((await a.isVisible()) || await flags.isEnabled('x')).toBe(true);",
    "expect((await a.isVisible()) || true).toBe(true);",
    "expect((await a.isVisible()) + (await b.isVisible())).toBe(true);",
    "expect(a.isVisible() || b.isVisible()).toBe(true);",
    "await expect.poll(async()=> (await a.isVisible()) || (await b.isVisible())).toBe(true);",
    "const expect=custom; expect((await a.isVisible()) || (await b.isVisible())).toBe(true);",
  ]) assert.deepEqual(run(scenario(expression)).findings, [], expression);
});

test('the original custom FeatureFlagService is not a Locator state-read candidate', () => {
  const bytes = fs.readFileSync(new URL('../../../skills/e2e-reviewer/evals/files/documented-exclusions.spec.ts', import.meta.url));
  assert.ok(!run(bytes.toString('utf8')).findings.some(f => f.line === 24));
});
