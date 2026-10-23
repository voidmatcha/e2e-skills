// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { assertions } from '../src/assertions.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function run(text) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-assertion-candidates-')));
  const filename = path.join(root, 'example.spec.ts');
  fs.writeFileSync(filename, text);
  const manifest = inventory(root), bytes = Buffer.from(text);
  return assertions(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
}
const body = text => "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n" + text + '\n});\n';
const candidates = result => result.findings.filter(f => ['#4a', '#4b'].includes(f.patternId));

test('#4a preserves numeric-shape P0 candidates without assuming a nonnegative subject', () => {
  const result = run(body([
    'expect(await getResultCount()).toBeGreaterThanOrEqual(0);',
    'expect(-1).toBeGreaterThanOrEqual(0);',
    'expect(-1).not.toBeGreaterThanOrEqual(0);',
    'expect(0).toBeGreaterThanOrEqual(1);',
    'expect(0).toBeGreaterThanOrEqual(zero);',
    'expect(0).toBeGreaterThanOrEqual(-0);',
    'expect(0).toBeGreaterThanOrEqual(0, extra);',
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(candidates(result).map(f => [f.patternId, f.severity, f.disposition, f.line]),
    [3, 4, 5].map(line => ['#4a', 'P0', 'candidate', line]));
});

test('#4b preserves positive attachment candidates regardless of destructive-action context', () => {
  // Shapes from assert_positive_to_be_attached_arguments_and_negation.
  const result = run(body([
    "await expect(page.locator('.plain')).toBeAttached();",
    "await expect(page.locator('.timed')).toBeAttached({timeout:250});",
    "await expect(page.locator('.nested')).toBeAttached({timeout:timeoutFor('ui')});",
    "await expect(page.locator('.gone')).not /* gap */ .toBeAttached();",
    "await expect(page.locator('.gone')).not\n.toBeAttached();",
    "await expect(page.locator('.newline')).toBeAttached\n({timeout:250});",
    "const templateExecution = `${await expect(page.locator('.expr')).toBeAttached()}`;",
    "const reference = expect(page.locator('.ref')).toBeAttached;",
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(candidates(result).map(f => [f.patternId, f.severity, f.disposition, f.line]),
    [3, 4, 5, 9, 11].map(line => ['#4b', 'P1', 'candidate', line]));
});

test('matcher candidates use imported aliases, soft expect and CommonJS proof', () => {
  for (const header of [
    "import {expect as verify,test} from '@playwright/test';",
    "const {expect:verify,test} = require('@playwright/test');",
  ]) {
    const result = run(header + "\ntest('x',()=>{\nverify(0).toBeGreaterThanOrEqual(0);\nverify.soft(subject).toBeAttached();\n});");
    assert.deepEqual(result.diagnostics, []);
    assert.deepEqual(candidates(result).map(f => f.patternId), ['#4a', '#4b']);
  }
});

test('foreign and shadowed expect, unrelated methods, optional calls and inert text are excluded', () => {
  const texts = [
    "import {expect,test} from 'vitest'; test('x',()=>{expect(0).toBeGreaterThanOrEqual(0);expect(x).toBeAttached();});",
    body('function other(expect){expect(0).toBeGreaterThanOrEqual(0);expect(x).toBeAttached();}'),
    body("const fake={toBeAttached(){},toBeGreaterThanOrEqual(){}};fake.toBeAttached();fake.toBeGreaterThanOrEqual(0);"),
    body("expect?.(0).toBeGreaterThanOrEqual(0);expect(x).toBeAttached?.();"),
    body("const text='expect(x).toBeAttached()';const rx=/toBeGreaterThanOrEqual\\(0\\)/;/* expect(x).toBeAttached(); */"),
    body('wrapper(expect)(0).toBeGreaterThanOrEqual(0);'),
  ];
  for (const text of texts) assert.deepEqual(candidates(run(text)), [], text);
});

test('unresolved and mutated expect provenance is diagnostic, never a clean candidate result', () => {
  for (const text of [
    "import {expect} from './missing';expect(0).toBeGreaterThanOrEqual(0);",
    body('expect.soft=custom;expect.soft(x).toBeAttached();'),
  ]) {
    const result = run(text);
    assert.deepEqual(candidates(result), []);
    assert.ok(result.diagnostics.length);
  }
});
