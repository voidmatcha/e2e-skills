// SPDX-License-Identifier: Apache-2.0
// The text view names relative imports that were not found; JSON is unchanged.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function tree(t, count) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-import-missing-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, 'tests'));
  const imports = Array.from({ length: count }, (_, index) => `import { h${index} } from './missing-${index}';\n`).join('');
  fs.writeFileSync(path.join(root, 'tests', 'a.spec.ts'), `import { test, expect } from '@playwright/test';\n${imports}` +
    "test('x', async ({ page }) => { await expect(page).toHaveURL('/'); });\n");
  return root;
}
const run = (root, ...args) => spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0', '--allow-incomplete', ...args],
  { encoding: 'utf8', timeout: 60_000, env: { ...process.env, E2E_SMELL_FAIL_ON: 'p0' } });

test('missing relative imports are listed per file in the text report, capped at 20 with a tail and a summary count', t => {
  const root = tree(t, 25);
  const text = run(root, '--format', 'text').stdout;
  const lines = text.split('\n').filter(line => line.startsWith('Unanalysed (import not found): '));
  assert.equal(lines.length, 21);
  assert.equal(lines[0], 'Unanalysed (import not found): "tests/a.spec.ts" -> "./missing-0"');
  assert.equal(lines[20], 'Unanalysed (import not found): +5 more; see JSON diagnostics (import-missing).');
  assert.match(text, /Summary \[INCOMPLETE\]: .* 25 relative import\(s\) not found; importing files not fully analysed\./);
  // JSON keeps location-only diagnostics: no specifier text is added.
  const report = JSON.parse(run(root).stdout);
  const missing = report.execution.diagnostics.filter(item => item.code === 'import-missing');
  assert.equal(missing.length, 25);
  assert.ok(missing.every(item => !Object.hasOwn(item, 'specifier')));
  assert.ok(!JSON.stringify(report).includes('missing-0'));
});

test('a scan without missing imports prints no import line or summary count', t => {
  const text = run(tree(t, 0), '--format', 'text').stdout;
  assert.ok(!text.includes('Unanalysed (import not found)'));
  assert.ok(!text.includes('relative import(s) not found'));
});
