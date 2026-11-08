// SPDX-License-Identifier: Apache-2.0
// Opt-in --allow-incomplete CI mode and user-declared --trust-module mappings.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function project(t, files) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-ci-trust-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  return root;
}
const scan = (target, ...args) => {
  const result = spawnSync(process.execPath, [cli, '--scan', target, '--fail-on', 'p0', ...args], { encoding: 'utf8', timeout: 30_000 });
  let report = null;
  try { report = JSON.parse(result.stdout); } catch {}
  return { status: result.status, report, stdout: result.stdout, stderr: result.stderr };
};
// A Locator array from .all() through a helper stays unresolved by design.
const unresolved = "import { test, expect } from '@playwright/test';\n" +
  "async function rows(page: any) { return page.getByRole('row').all(); }\n" +
  "test('t', async ({ page }) => {\n  const list = await rows(page);\n  expect(list[0]).toBeTruthy();\n";

test('--allow-incomplete exits by the policy on analyzed findings and reports what was not analyzed', t => {
  const clean = project(t, { 'tests/a.spec.ts': unresolved + '});\n' });
  assert.equal(scan(clean, '--format', 'json').status, 2);
  const allowed = scan(clean, '--format', 'json', '--allow-incomplete');
  assert.equal(allowed.status, 0);
  assert.equal(allowed.report.status, 'INCOMPLETE');
  assert.equal(allowed.report.execution.complete, false);
  assert.equal(allowed.report.execution.exitCode, 0);
  assert.deepEqual(allowed.report.execution.allowIncomplete, { applied: true, unanalyzed: { files: 1, locations: allowed.report.execution.diagnostics.length } });
  const text = scan(clean, '--format', 'text', '--allow-incomplete');
  assert.equal(text.status, 0);
  assert.match(text.stdout, /^ALLOW-INCOMPLETE: 1 file\(s\) with \d+ unresolved location\(s\) were NOT fully analyzed; that code is NOT checked\.$/m);
  assert.match(text.stdout, /^Summary \[INCOMPLETE\]:/m);
  // The same one-line warning goes to stderr in either format, and tops the text report.
  const warning = /^INCOMPLETE: \d+ locations? in 1 file (?:was|were) not analysed \u2014 this is not a clean result\.\n$/;
  assert.match(text.stderr, warning);
  assert.match(allowed.stderr, warning);
  assert.equal(text.stdout.split('\n')[2], text.stderr.trimEnd());
  assert.equal(scan(clean, '--format', 'text').stderr, '');

  const weak = project(t, { 'tests/a.spec.ts': unresolved + "  expect(page.getByRole('main')).toBeTruthy();\n});\n" });
  const failing = scan(weak, '--format', 'json', '--allow-incomplete');
  assert.equal(failing.status, 1);
  assert.equal(failing.report.counts.p0, 1);
  assert.equal(scan(weak, '--format', 'text', '--allow-incomplete').status, 1);
});

test('--allow-incomplete never tolerates inventory failures or other scan modes', t => {
  const root = project(t, { 'tests/a.spec.ts': unresolved + '});\n' });
  fs.symlinkSync(path.join(root, 'tests', 'a.spec.ts'), path.join(root, 'tests', 'link.spec.ts'));
  const broken = scan(root, '--format', 'json', '--allow-incomplete');
  assert.equal(broken.status, 2);
  assert.equal(broken.report.execution.allowIncomplete.applied, false);
  const bounded = spawnSync(process.execPath, [cli, '--bounded-static', root, '--allow-incomplete'], { encoding: 'utf8' });
  assert.equal(bounded.status, 2);
  assert.match(bounded.stderr, /--allow-incomplete requires --scan/);
});

const library = {
  'lib/src/index.ts': "export { test, expect } from './fixture';\n",
  'lib/src/fixture.ts': "import { test as base } from '@playwright/test';\nexport { expect } from './expect';\n" +
    "export const test = base.extend<{ user: string }>({ user: async ({}, use) => { await use('admin'); } });\n",
  'lib/src/expect.ts': "import { expect as baseExpect } from '@playwright/test';\n" +
    "export const expect = baseExpect.extend({ async toHavePath(page: any, path: string) { return { pass: true, message: () => path }; } });\n",
  'specs/channel.spec.ts': "import { expect, test } from '@acme/playwright-lib';\n" +
    "test('t', async ({ page }) => {\n  await page.goto('/');\n  expect(page.getByRole('button', { name: 'Post', exact: true })).toBeTruthy();\n});\n",
};

test('--trust-module resolves a workspace package that re-exports Playwright test and expect', t => {
  const root = project(t, library);
  const plain = scan(root, '--format', 'json');
  assert.equal(plain.status, 2);
  assert.ok(plain.report.execution.diagnostics.some(item => item.code === 'import-unpinned'));
  const trusted = scan(root, '--format', 'json', '--trust-module', '@acme/playwright-lib=lib/src/index.ts');
  assert.equal(trusted.status, 1, trusted.stderr);
  assert.equal(trusted.report.status, 'COMPLETE');
  assert.deepEqual(trusted.report.findings.map(f => [f.patternId, f.disposition, f.line]), [['#4f', 'confirmed', 4]]);
  assert.deepEqual(trusted.report.trustedModules, [{ specifier: '@acme/playwright-lib', path: path.join(root, 'lib/src/index.ts') }]);
  assert.match(scan(root, '--format', 'text', '--trust-module', '@acme/playwright-lib=lib/src/index.ts').stdout,
    /^Trusted modules: "@acme\/playwright-lib" -> "lib\/src\/index.ts" \(declared by --trust-module\)\.$/m);
});

test('--trust-module rejects paths outside the root, non-source files, links and unsafe specifiers', t => {
  const root = project(t, { ...library, 'lib/data.json': '{}' });
  const outside = path.join(path.dirname(root), path.basename(root) + '-outside.ts');
  fs.writeFileSync(outside, 'export {};\n');
  t.after(() => fs.rmSync(outside, { force: true }));
  for (const [value, message] of [
    [`@acme/x=../${path.basename(outside)}`, /leaves the scan root/],
    ['@acme/x=lib/data.json', /not a JavaScript or TypeScript source file/],
    ['@acme/x=lib/src/missing.ts', /path not found/],
    ['@acme/x=lib/src', /regular file/],
    ['./local=lib/src/index.ts', /unsupported or duplicate specifier/],
    ['@playwright/test=lib/src/index.ts', /unsupported or duplicate specifier/],
    ['@acme/x', /requires <specifier>=<path/],
  ]) {
    const result = scan(root, '--format', 'json', '--trust-module', value);
    assert.equal(result.status, 2, value);
    assert.match(result.stderr, message, value);
  }
  const twice = scan(root, '--format', 'json', '--trust-module', '@acme/x=lib/src/index.ts', '--trust-module', '@acme/x=lib/src/expect.ts');
  assert.match(twice.stderr, /duplicate/);
  assert.match(scan(path.join(root, 'specs/channel.spec.ts'), '--trust-module', '@acme/x=lib/src/index.ts').stderr, /directory scan root/);
  fs.symlinkSync(path.join(root, 'lib/src/index.ts'), path.join(root, 'lib/src/alias.ts'));
  const linked = scan(root, '--format', 'json', '--trust-module', '@acme/x=lib/src/alias.ts');
  assert.equal(linked.status, 2);
});

test('--allow-incomplete tolerates a missing relative import but never import-snapshot drift', async t => {
  const root = project(t, { 'tests/a.spec.ts': "import { test, expect } from '@playwright/test';\nimport { helper } from './missing';\n" +
    "test('t', async ({ page }) => {\n  await helper(page);\n  await expect(page.getByRole('main')).toBeVisible();\n});\n" });
  const plain = scan(root, '--format', 'json');
  assert.equal(plain.status, 2);
  assert.ok(plain.report.execution.incomplete.includes('relative import snapshot validation incomplete'));
  const allowed = scan(root, '--format', 'json', '--allow-incomplete');
  assert.equal(allowed.status, 0, JSON.stringify(allowed.report.execution.incomplete));
  const { summarize } = await import('../src/report.mjs');
  const reasons = ['relative import snapshot incomplete', 'relative import snapshot validation incomplete'];
  assert.equal(summarize([], { incomplete: reasons, allowIncomplete: true, diagnostics: [{ code: 'import-missing' }] }).exitCode, 0);
  assert.equal(summarize([], { incomplete: reasons, allowIncomplete: true, diagnostics: [{ code: 'import-snapshot-drift' }] }).exitCode, 2);
  assert.equal(summarize([], { incomplete: ['candidate unavailable: x: gone'], allowIncomplete: true }).exitCode, 2);
});
