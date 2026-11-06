// SPDX-License-Identifier: Apache-2.0
// #4a confirmed invariant predicates: an always-truthy `||` subject and a
// proven Locator count compared against a bound no count can violate.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { assertions } from '../src/assertions.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';

function run(text, additional = {}) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-node-invariants-')));
  const filename = path.join(root, 'example.spec.ts');
  for (const [name, content] of Object.entries({ 'example.spec.ts': text, ...additional })) {
    fs.writeFileSync(path.join(root, name), content);
  }
  const manifest = inventory(root);
  assert.equal(manifest.complete, true, JSON.stringify(manifest.errors));
  const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
  const scope = createScope({ manifest, sources });
  return assertions(sources.get(filename), filename, { scope });
}

const header = "import {test, expect} from '@playwright/test';\n";
const body = text => header + `test('x',async({page})=>{\n${text}\n});\n`;
const rows = result => result.findings.filter(f => f.patternId === '#4a')
  .map(f => [f.patternId, f.severity, f.disposition, f.line]);

test('#4a confirms an always-truthy || subject under truthiness matchers', () => {
  const result = run(body([
    "const isVisible = await page.getByText('a').isVisible();",
    'expect(isVisible || true).toBeTruthy(); // Always pass for now',
    'expect(isVisible || true).toBe(true);',
    'expect(isVisible || 1).toBeDefined();',
    "expect(isVisible || 'yes').toBeTruthy();",
    'expect(true || isVisible).toBeTruthy();',
    'expect.soft(isVisible || true).toBeTruthy();',
    'expect(isVisible ?? false).toBeDefined();',
  ].join('\n')));
  assert.deepEqual(rows(result), [4, 5, 6, 7, 8, 9].map(line => ['#4a', 'P0', 'confirmed', line]));
});

test('#4a always-truthy guards: non-literal operand, other matchers, nesting, falsy literals', () => {
  const result = run(body([
    "const a = await page.getByText('a').isVisible();",
    "const b = await page.getByText('b').isVisible();",
    'expect(a || b).toBeTruthy();',
    'expect(a || true).toBe(false);',
    'expect(`${a || true}`).toBeTruthy();',
    'expect(() => a || true).toBeTruthy();',
    "expect(a || '').toBeTruthy();",
    'expect(a || 0).toBeTruthy();',
    'expect(a ?? true).toBeTruthy();',
    'expect(a || true).not.toBeTruthy();',
    'expect(a && true).toBeTruthy();',
  ].join('\n')));
  assert.deepEqual(rows(result), []);
});

test('#4a always-truthy needs Playwright expect provenance', () => {
  const unproven = run("import {test} from '@playwright/test';\nimport {check} from 'assertion-kit';\n" +
    "test('x',async({page})=>{\nconst a = await page.getByText('a').isVisible();\ncheck(a || true).toBeTruthy();\n});\n");
  assert.deepEqual(rows(unproven), []);
  const unit = run("import {test, expect} from 'vitest';\ntest('x',()=>{\nconst a = Math.random() > 1;\nexpect(a || true).toBeTruthy();\n});\n");
  assert.deepEqual(rows(unit), []);
});

test('#4a confirms count >= 0 and > -1 on a proven Locator', () => {
  const result = run(body([
    "const items = page.locator('.row');",
    'expect(await items.count()).toBeGreaterThanOrEqual(0);',
    'const n = await items.count();',
    'expect(n).toBeGreaterThanOrEqual(0);',
    "expect(await page.getByRole('row').count()).toBeGreaterThan(-1);",
    'expect(n).toBeGreaterThan(-1);',
  ].join('\n')));
  assert.deepEqual(rows(result), [4, 6, 7, 8].map(line => ['#4a', 'P0', 'confirmed', line]));
});

test('#4a count guards: >= 1, .not, arithmetic and user objects stay unconfirmed', () => {
  const result = run(body([
    "const items = page.locator('.row');",
    'expect(await items.count()).toBeGreaterThanOrEqual(1);',
    'expect(await items.count()).not.toBeGreaterThanOrEqual(0);',
    'expect((await items.count()) - 1).toBeGreaterThanOrEqual(0);',
    'const store = { count: async () => 3 };',
    'expect(await store.count()).toBeGreaterThanOrEqual(0);',
    'expect(await store.count()).toBeGreaterThan(-1);',
    'let m = await items.count();',
    'm = m - 2;',
    'expect(m).toBeGreaterThanOrEqual(0);',
  ].join('\n')));
  // Unproven >= 0 shapes stay the existing #4a candidate; > -1 on a user
  // object is not a candidate surface at all.
  assert.deepEqual(rows(result), [[ '#4a', 'P0', 'candidate', 5 ], [ '#4a', 'P0', 'candidate', 6 ],
    [ '#4a', 'P0', 'candidate', 8 ], [ '#4a', 'P0', 'candidate', 12 ]]);
});

test('#4a count const declared in another function stays a candidate', () => {
  const result = run(header + "let shared;\ntest.beforeEach(async({page})=>{\nconst c = await page.locator('.row').count();\nshared = c;\n});\n" +
    "test('x',async({page})=>{\nconst c = await page.locator('.row').count();\nconst check = () => expect(c).toBeGreaterThanOrEqual(0);\ncheck();\n});\n");
  assert.deepEqual(rows(result), [['#4a', 'P0', 'candidate', 9]]);
});
