// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/check-cli.mjs', import.meta.url));
const assertion = "await expect(page.getByTestId('status')).toHaveText('Ready');";
const header = "import {expect} from '@playwright/test';\n";
function check(operator, text, expectedCode) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'check-explain-'));
  const file = path.join(root, 'test.spec.mjs'); fs.writeFileSync(file, text);
  const run = explain => spawnSync(process.execPath,
    [cli, 'discover', ...(explain ? ['--explain'] : []), operator, root, 'test.spec.mjs'], { encoding: 'utf8' });
  const ordinary = run(false), explained = run(true);
  assert.equal(ordinary.status, 0, ordinary.stderr);
  assert.equal(explained.status, expectedCode ? 2 : 0, explained.stderr);
  assert.equal(explained.stderr, '');
  const result = JSON.parse(explained.stdout);
  assert.equal(result.schema, 'e2e-skills-check-discovery-v1');
  assert.equal(result.operator, operator);
  assert.equal(result.status, expectedCode ? 'NO_SUPPORTED_CANDIDATE' : 'CANDIDATES_FOUND');
  assert.deepEqual(result.candidates, JSON.parse(ordinary.stdout));
  assert.deepEqual(result.diagnostics, expectedCode ? [{ code: expectedCode }] : []);
  assert.equal(fs.readFileSync(file, 'utf8'), text);
  return result;
}

test('explanation keeps the exact assertion and POST candidates without executing source', () => {
  for (const [operator, text] of [
    ['assertion', header + `throw Error('must not execute');\nasync function f(page){${assertion}}`],
    ['post', "throw Error('must not execute');\nasync function f(){await fetch('/api/like',{method:'POST'});}"],
  ]) assert.equal(check(operator, text).candidates.length, 1);
});

test('unsupported import and expect uses are distinguished without source reason values', () => {
  check('assertion', "import {expect as custom} from '@playwright/test';\nasync function f(page){" + assertion + '}', 'expect-import-unsupported');
  const result = check('assertion', header + "const PRIVATE_ALIAS=expect;\nasync function f(page){" + assertion + '}', 'expect-use-unsupported');
  assert.doesNotMatch(JSON.stringify(result), /PRIVATE_ALIAS/);
});

test('no supported shape does not mean no assertions, no faults or a passing test', () => {
  check('assertion', header + "async function f(page){await expect(page.getByRole('status')).toHaveText('PRIVATE_TEXT');}", 'no-supported-assertion-shape');
  check('post', "async function f(){const response=await fetch('/api/private',{method:'POST'});}", 'no-supported-post-shape');
});

test('unsupported fetch references are explained without exposing names or endpoints', () => {
  const result = check('post', "const PRIVATE_ALIAS=fetch; async function f(){await fetch('/api/private',{method:'POST'});}", 'fetch-use-unsupported');
  assert.doesNotMatch(JSON.stringify(result), /PRIVATE_ALIAS|\/api\/private/);
});

test('empty files stay an explicitly unsupported result in explanation mode', () => {
  check('assertion', '', 'expect-import-unsupported');
  check('post', '', 'no-supported-post-shape');
});

test('explanation does not turn syntax or path errors into unsupported results', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'check-explain-errors-'));
  fs.writeFileSync(path.join(root, 'bad.ts'), 'function (');
  for (const relative of ['bad.ts', '../bad.ts']) {
    const result = spawnSync(process.execPath, [cli, 'discover', '--explain', 'assertion', root, relative], { encoding: 'utf8' });
    assert.equal(result.status, 2); assert.equal(result.stdout, '');
    assert.match(result.stderr, /syntax errors|safe relative/);
  }
});
