// SPDX-License-Identifier: Apache-2.0
// #5a review hint: a gate that reads only run configuration is listed at P2.
// G (resolved-project gates) still drops a gate that every project runs;
// product-state gates and confirmed gates keep their P0 tier.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createScope } from '../src/scope.mjs';
import { conditionalAssertions } from '../src/conditional-assertions.mjs';

const head = "import { test, expect } from '@playwright/test';\n";
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
function run(files) {
  const entries = Object.entries(typeof files === 'string' ? { 'case.spec.ts': files } : files)
    .map(([name, text]) => [`/pinned/${name}`, Buffer.from(name.endsWith('.config.ts') ? text : head + text)]);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' },
    projectContext: { complete: true, requested: { kind: 'directory' }, scanRoot: '/pinned', projectRoot: '/pinned' },
    candidates: entries.map(([path, bytes]) => ({ path, identity: { size: String(bytes.length), sha256: digest(bytes) } })) };
  const scope = createScope({ manifest, sources: new Map(entries) });
  const [filename, bytes] = entries[0];
  return conditionalAssertions(bytes, filename, { scope }).findings.filter(f => f.patternId === '#5a')
    .map(f => [f.line, f.severity, f.disposition, f.reviewHint?.rule ?? null]);
}
const spec = (body, params = '{ page }') => `test('t', async (${params}) => {\n${body}\n});\n`;
const hint = line => [line, 'P2', 'candidate', 'run-configuration-gate'];
const p0 = line => [line, 'P0', 'candidate', null];

test('#5a gates on run configuration are review hints (sweep-200 / random-60 FP shapes)', () => {
  const rows = run(spec([
    "if (process.env.CI) await expect(page).toHaveURL(/done/);",                                // 3
    "if (process.env['VISUAL'] === '1') await expect(page).toHaveScreenshot();",               // 4
    "if (browserName === 'webkit') await expect(page.getByText('a')).toBeVisible();",          // 5
    "if (!isMobile) { await expect(page.getByRole('navigation')).toBeVisible(); }",            // 6
    "if (testInfo.project.name.includes('mobile')) await expect(page).toHaveTitle('m');",      // 7
    "const viewport = page.viewportSize();",                                                   // 8
    "if (viewport && viewport.width < 768) await expect(page.getByRole('button')).toBeVisible();", // 9
    "if (process.platform === 'darwin') await expect(page).toHaveTitle('mac');",               // 10
    "if (test.info().project.use.isMobile) await expect(page).toHaveTitle('m');",              // 11
    "const isCI = !!process.env.CI;",                                                          // 12
    "if (!isCI) await expect(page).toHaveScreenshot();",                                       // 13
    "['chromium', 'firefox'].includes(browserName) && await expect(page).toHaveTitle('a');",   // 14
    "process.env.SMOKE ? await expect(page).toHaveTitle('a') : await page.goto('/');",         // 15
  ].join('\n'), '{ page, browserName, isMobile }, testInfo'));
  assert.deepEqual(rows, [3, 4, 5, 6, 7, 9, 10, 11, 13, 14, 15].map(hint));
});

test('#5a product-state gates and mixed conditions keep P0', () => {
  const rows = run(spec([
    "const box = await page.getByRole('dialog').boundingBox();",                                // 3
    "if (box) await expect(page.getByRole('dialog')).toHaveText('x');",                        // 4 truthiness of a value
    "if (process.env.CI && await page.getByText('a').isVisible()) await expect(page).toHaveTitle('a');", // 5 mixed
    "const isMobile = await page.locator('.mobile-nav').isVisible();",                         // 6
    "if (isMobile) await expect(page.getByRole('navigation')).toBeVisible();",                 // 7 local product read named isMobile
    "if (data.project.enabled) await expect(page).toHaveTitle('a');",                          // 8 not testInfo
    "if (process.env.CI || flag) await expect(page).toHaveTitle('a');",                        // 9 unknown operand
    "if (getEnv('CI')) await expect(page).toHaveTitle('a');",                                  // 10 unknown call
    "let mode = process.env.MODE; mode = await read();",                                       // 11
    "if (mode === 'x') await expect(page).toHaveTitle('a');",                                  // 12 written binding
  ].join('\n')));
  assert.deepEqual(rows.filter(row => row[1] === 'P2'), []);
  assert.ok(rows.some(row => row[0] === 4) && rows.some(row => row[0] === 7) && rows.some(row => row[0] === 12), JSON.stringify(rows));
});

test('#5a confirmed gate stays confirmed', () => {
  const rows = run(spec("if (await page.locator('.row').count()) { await expect(page.locator('.row').first()).toHaveText('a'); }"));
  assert.deepEqual(rows.filter(row => row[2] === 'confirmed').map(row => row[1]), ['P0']);
  assert.ok(rows.every(row => row[3] === null));
});

test('G still drops a resolved-project gate; an unresolved one becomes a hint, not a duplicate', () => {
  const config = body => "import { defineConfig, devices } from '@playwright/test';\nexport default defineConfig(" + body + ");\n";
  const gates = spec("if (testInfo.project.name === 'production') await expect(page).toHaveURL(/lab/);\n" +
    "if (browserName === 'webkit') await expect(page).toHaveURL(/lab/);", '{ page, browserName }, testInfo');
  const two = config("{ testDir: '.', use: { ...devices['Desktop Chrome'] }, projects: [{ name: 'dev' }, { name: 'production', use: { ...devices['Desktop Safari'] } }] }");
  assert.deepEqual(run({ 'case.spec.ts': gates, 'playwright.config.ts': two }), []);
  assert.deepEqual(run({ 'case.spec.ts': gates, 'playwright.config.ts': config("{ projects: [{ name: 'dev' }] }") }), [hint(3), hint(4)]);
  // No config at all: G cannot decide, the hint applies.
  assert.deepEqual(run(gates), [hint(3), hint(4)]);
});
