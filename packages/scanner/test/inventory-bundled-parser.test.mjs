// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { inventory, revalidate } from '../src/inventory.mjs';

test('only exact bundled parser bytes in self-repository directory scans are excluded', t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-parser-inventory-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const put = (name, bytes = '') => {
    const file = path.join(root, name);fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, bytes);return file;
  };
  put('AGENTS.md');put('skills/e2e-reviewer/SKILL.md');put('scripts/ci/test-reviewer-scanner.py');
  const name = 'skills/e2e-reviewer/scripts/scanner/vendor/typescript/typescript.cjs';
  const bytes = fs.readFileSync(new URL('../../../' + name, import.meta.url));
  const parser = put(name, bytes), sibling = put('vendor/ordinary.spec.ts', 'export {};');
  const baseline = inventory(root);
  assert.equal(baseline.complete, true);
  assert.ok(!baseline.candidates.some(item => item.path === parser));
  assert.ok(baseline.candidates.some(item => item.path === sibling));
  assert.ok(inventory(parser).candidates.some(item => item.path === parser), 'explicit file root remains visible');
  fs.writeFileSync(parser, Buffer.concat([bytes, Buffer.from('\n// changed')]));
  assert.ok(inventory(root).candidates.some(item => item.path === parser));
  assert.equal(revalidate(baseline).complete, false);
  fs.writeFileSync(parser, bytes);
  fs.unlinkSync(path.join(root, 'AGENTS.md'));
  assert.ok(inventory(root).candidates.some(item => item.path === parser), 'other repositories do not inherit exclusion');
  put('AGENTS.md');put('skills/package.json', '{}');
  assert.ok(inventory(path.join(root, 'skills')).candidates.some(item => item.path === parser), 'nested project stays visible');
});
