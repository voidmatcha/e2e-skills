// SPDX-License-Identifier: Apache-2.0
// #3 swallowed waits: a `.catch` can only swallow a TimeoutError when the
// wait has a finite timeout. Playwright Test defaults actionTimeout and
// navigationTimeout to 0 (no limit), so with neither an explicit `timeout`
// nor a configured one, a target that never arrives fails the test at its
// test timeout. That provable case is a P2 diagnostics candidate, not a P0
// silent-pass candidate. A finite or unknown timeout keeps the P0 candidate.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
// The doory a11y shape (frontend/e2e/app/a11y.spec.ts:93), on the fixture page.
const DOORY = `import { test, expect } from '@playwright/test';
test('menu a11y', async ({ page }) => {
  await page.getByRole('button', { name: 'Account' }).click();
  await page.getByRole('menuitem').first().waitFor({ state: 'visible' }).catch(() => undefined);
  expect(await page.title()).toBe('Doory');
});
`;
const config = use => `import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './e2e', timeout: 90_000, use: { ${use} } });
`;
function scan(t, files, target = 'e2e') {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-wait-timeout-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.mkdirSync(path.join(root, '.git'));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  const result = spawnSync(process.execPath, [cli, '--scan', path.join(root, target), '--fail-on', 'none', '--allow-incomplete', '--format', 'json'],
    { encoding: 'utf8', timeout: 60_000 });
  const report = JSON.parse(result.stdout);
  return new Map(report.findings.filter(item => item.patternId === '#3').map(item => [item.line, item]));
}

test('FP guard: doory shape with no finite timeout is a P2 diagnostics candidate, not P0', t => {
  const hits = scan(t, { 'playwright.config.ts': config(`baseURL: 'http://localhost:3000'`), 'e2e/a11y.spec.ts': DOORY });
  const hit = hits.get(4);
  assert.equal(hit.severity, 'P2');
  assert.equal(hit.disposition, 'candidate');
  assert.equal(hit.triage.timeout.effective, 'none');
  assert.equal(hit.triage.timeout.inert, true);
  assert.match(hit.triage.hint, /^no finite timeout: cannot swallow a timeout/);
  assert.match(hit.triage.hint, /fails at the test timeout instead of passing silently/);
});

test('TP: config use.actionTimeout > 0 keeps the P0 candidate', t => {
  const hits = scan(t, { 'playwright.config.ts': config(`actionTimeout: 10_000`), 'e2e/a11y.spec.ts': DOORY });
  assert.equal(hits.get(4).severity, 'P0');
  assert.deepEqual(hits.get(4).triage.timeout, { effective: 'finite', source: 'playwright.config.ts use.actionTimeout', ms: 10000 });
  assert.match(hits.get(4).triage.hint, /finite timeout 10000 ms/);
  // Scanning the project root also reads the config as a source; its own
  // actionTimeout must not turn the interpreted value into an unknown.
  const rooted = [...scan(t, { 'playwright.config.ts': config(`actionTimeout: 10_000`), 'e2e/a11y.spec.ts': DOORY }, '.').values()]
    .find(item => item.triage?.shape === 'swallowed-wait');
  assert.equal(rooted.triage.timeout.effective, 'finite');
});

test('TP: an explicit timeout option keeps the P0 candidate even with no config timeout', t => {
  const spec = DOORY.replace("{ state: 'visible' }", "{ state: 'visible', timeout: 3000 }");
  const hits = scan(t, { 'playwright.config.ts': config(`baseURL: 'http://localhost:3000'`), 'e2e/a11y.spec.ts': spec });
  assert.equal(hits.get(4).severity, 'P0');
  assert.deepEqual(hits.get(4).triage.timeout, { effective: 'finite', source: 'option', ms: 3000 });
});

test('navigation waits read navigationTimeout, not actionTimeout; goto is never downgraded', t => {
  const spec = `import { test, expect } from '@playwright/test';
test('nav', async ({ page }) => {
  await page.waitForURL('**/done').catch(() => {});
  await page.goto('/next').catch(() => {});
  expect(await page.title()).toBe('x');
});
`;
  const hits = scan(t, { 'playwright.config.ts': config(`actionTimeout: 10_000`), 'e2e/nav.spec.ts': spec });
  // actionTimeout does not bound navigation: Playwright Test passes navigationTimeout || 0.
  assert.equal(hits.get(3).severity, 'P2');
  assert.equal(hits.get(3).triage.timeout.effective, 'none');
  // goto rejects at once on a network error, so no timeout does not refute it.
  assert.equal(hits.get(4).severity, 'P0');
  assert.equal(hits.get(4).triage.timeout.effective, 'none');
  assert.equal(hits.get(4).triage.timeout.inert, undefined);
  const finite = scan(t, { 'playwright.config.ts': config(`navigationTimeout: 15_000`), 'e2e/nav.spec.ts': spec });
  assert.equal(finite.get(3).severity, 'P0');
  assert.equal(finite.get(3).triage.timeout.ms, 15000);
});

test('unknown effective timeout keeps the P0 candidate with a hint', t => {
  const cases = {
    'env-dependent actionTimeout': { 'playwright.config.ts': config(`actionTimeout: process.env.CI ? 10_000 : 0`), 'e2e/a11y.spec.ts': DOORY },
    'alternate config file': { 'playwright.config.ts': config(`baseURL: 'x'`), 'playwright.app.config.ts': config(`actionTimeout: 5000`), 'e2e/a11y.spec.ts': DOORY },
    'no config': { 'e2e/a11y.spec.ts': DOORY },
    'setDefaultTimeout in scope': { 'playwright.config.ts': config(`baseURL: 'x'`),
      'e2e/a11y.spec.ts': DOORY.replace("test('menu a11y', async ({ page }) => {", "test.beforeEach(({ page }) => page.setDefaultTimeout(5000));\ntest('menu a11y', async ({ page }) => {") },
    'projects not interpreted': { 'playwright.config.ts': `import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir: './e2e', projects: [{ name: 'c', use: { actionTimeout: 5000 } }] });
`, 'e2e/a11y.spec.ts': DOORY },
    'non-literal options': { 'playwright.config.ts': config(`baseURL: 'x'`), 'e2e/a11y.spec.ts': DOORY.replace("{ state: 'visible' }", 'options') },
  };
  for (const [name, files] of Object.entries(cases)) {
    const hit = [...scan(t, files).values()].find(item => item.triage?.shape === 'swallowed-wait');
    assert.equal(hit?.severity, 'P0', name);
    assert.equal(hit.triage.timeout.effective, 'unknown', name);
    assert.match(hit.triage.hint, /effective timeout unknown/, name);
  }
});

test('explicit timeout: 0 is provably no timeout', t => {
  const spec = DOORY.replace("{ state: 'visible' }", "{ state: 'visible', timeout: 0 }");
  const hits = scan(t, { 'e2e/a11y.spec.ts': spec });
  assert.equal(hits.get(4).severity, 'P2');
  assert.equal(hits.get(4).triage.timeout.source, 'option timeout: 0');
});
