// SPDX-License-Identifier: Apache-2.0
// #4c-4e: Playwright ignores the timeout option of isVisible/isHidden, so the
// call is a one-shot read even when the code looks like it waits.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { stateReads } from '../src/state-reads.mjs';
import { inventory } from '../src/inventory.mjs';
import { createScope } from '../src/scope.mjs';
function run(text) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'e2e-ignored-timeout-')));
  try {
    fs.writeFileSync(path.join(root, 'example.spec.ts'), text);
    const manifest = inventory(root);
    const sources = new Map(manifest.candidates.map(item => [item.path, fs.readFileSync(item.path)]));
    const filename = path.join(root, 'example.spec.ts');
    return stateReads(sources.get(filename), filename, { scope: createScope({ manifest, sources }) });
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
const body = text => "import {test,expect} from '@playwright/test';\ntest('x',async({page})=>{\n" + text + '\n});\n';
const rows = result => result.findings.map(f => [f.patternId, f.line, f.severity, f.disposition, f.variant ?? null]);

test('#4c-4e confirms isVisible/isHidden timeout options on a proven Locator or Page', () => {
  const result = run(body([
    "const banner = page.getByRole('banner');",
    'if (await banner.isVisible({ timeout: 5000 })) await banner.click();',
    "const hidden = await page.locator('.spinner').isHidden({ 'timeout': 3000 });",
    "expect(await banner.isVisible({ timeout: 1000 })).toBe(true);",
    "const gone = await page.isHidden('.toast', { timeout: 2000 });",
    'const timeout = 10_000;',
    'await banner.isVisible({ timeout }).catch(() => false);',
  ].join('\n')));
  assert.deepEqual(result.diagnostics, []);
  assert.deepEqual(rows(result), [4, 5, 6, 7, 9].map(line => ['#4c-4e', line, 'P1', 'confirmed', 'ignored-timeout']));
});

test('#4c-4e ignored-timeout guards: no timeout, waiting APIs, retry wrappers and unproven receivers', () => {
  const result = run(body([
    "const banner = page.getByRole('banner');",
    'if (await banner.isVisible()) await banner.click();',
    'await expect(banner).toBeVisible({ timeout: 5000 });',
    "await banner.waitFor({ state: 'visible', timeout: 5000 });",
    'await expect.poll(() => banner.isVisible({ timeout: 100 })).toBe(true);',
    'const widget = { isVisible: async (options) => true };',
    'await widget.isVisible({ timeout: 5000 });',
    'await banner.isVisible({ strict: true });',
  ].join('\n')));
  assert.deepEqual(rows(result).filter(row => row[4] === 'ignored-timeout'), []);
});
