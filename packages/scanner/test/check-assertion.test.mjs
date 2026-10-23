// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { discoverAssertion as discover, bindAssertion as bind } from '../src/check-candidates.mjs';
const header = "import { test, expect } from '@playwright/test';\n";
const statement = "await expect(page.getByTestId('status')).toHaveText('Ready')";
const source = body => Buffer.from(header + "test('status contract', async ({ page }) => {\n" + body + ';\n});\n');
const find = body => discover(source(body), 'status.spec.mjs');
test('one exact awaited static literal and UTF-8 byte range', () => {
  const bytes = source('// 한글 😀\n' + statement), [candidate] = discover(bytes, 'status.spec.mjs');
  assert.equal(candidate.before, statement);
  assert.equal(bytes.subarray(candidate.range.byte_start, candidate.range.byte_end).toString(), statement);
  assert.ok(candidate.range.byte_start > candidate.range.utf16_start);
  assert.match(candidate.after, /__E2E_ASSERTION_MUTANT_/);
  assert.equal(candidate.line, 4);
});
test('comments and string contents are not candidates', () => {
  assert.deepEqual(find('// ' + statement + '\nconst example = ' + JSON.stringify(statement)), []);
});
test('reject dynamic arguments, regex, templates, unawaited, not, soft and unknown locator forms', () => {
  for (const expression of [statement.replace("'Ready'", 'expected'), statement.replace("'Ready'", '/Ready/'), statement.replace("'Ready'", '`Ready`'), statement.replace('await ', ''), statement.replace('.toHaveText', '.not.toHaveText'), statement.replace('expect(', 'expect.soft('), statement.replace('getByTestId', 'getByText'), statement.replace("'status'", 'id')]) assert.deepEqual(find(expression), [], expression);
});
test('duplicate exact source statements and shadowed expect are rejected', () => {
  assert.deepEqual(find(statement + ';\n' + statement), []);
  assert.deepEqual(find('const expect = custom;\n' + statement), []);
  assert.deepEqual(discover(Buffer.from("import { expect as other } from '@playwright/test';\n" + statement), 'a.ts'), []);
});
test('syntax errors and non UTF-8 source fail closed', () => {
  assert.throws(() => find(statement + '('), /syntax/);
  assert.throws(() => discover(Buffer.from([0xff]), 'a.ts'), /UTF-8/);
});
test('manual binding keeps pinned command and rejects source or candidate drift', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'targeted-check-'));
  // Retained tiny temp evidence by design, no outside cleanup.
  const bytes = source(statement); fs.writeFileSync(path.join(root, 'status.spec.mjs'), bytes);
  const candidate = discover(bytes, 'status.spec.mjs')[0];
  const binding = { source: root, test_selector: 'status contract', promise: { path: 'README.md', quote: 'Ready', sha256: 'manual' }, test: { argv: ['node', 'run.mjs'], source: { path: 'run.mjs', sha256: 'manual' } }, report: { format: 'playwright-json', path: 'report.json' }, expected_failure: { contains: 'toHaveText', location: 'status.spec.mjs:3' } };
  const plan = bind(candidate, binding);
  assert.deepEqual(plan.test, binding.test); assert.equal(plan.mode, 'assertion-mutation');
  assert.throws(() => bind({ ...candidate, after: 'bad' }, binding), /candidate changed/);
  fs.appendFileSync(path.join(root, 'status.spec.mjs'), '\n// drift');
  assert.throws(() => bind(candidate, binding), /source drifted/);
});
