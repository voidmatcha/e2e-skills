// SPDX-License-Identifier: Apache-2.0
// tsconfig/jsconfig `paths` aliases for test/expect, resolved as Playwright's
// loader does, only from pinned in-scope configuration and files.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function scan(t, files, scanned = '.') {
  const outer = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-tsconfig-paths-')));
  t.after(() => fs.rmSync(outer, { recursive: true, force: true }));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(outer, name)), { recursive: true });
    fs.writeFileSync(path.join(outer, name), text);
  }
  const root = path.join(outer, scanned);
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0'],
    { encoding: 'utf8', timeout: 60_000, env: { ...process.env, E2E_SMELL_FAIL_ON: 'p0' } });
  const report = JSON.parse(result.stdout);
  return { status: report.status, confirmed: report.findings.filter(item => item.disposition === 'confirmed').map(item => [item.patternId, item.line]),
    diagnostics: report.execution.diagnostics };
}
const SPEC = (specifier = '@e2e/fixtures') => `import { test, expect } from '${specifier}';
test('the only member cannot be removed', async ({ page }) => {
  const members = page.getByTestId('member-row');
  if ((await members.count()) === 1) {
    await expect(members.first()).toBeDisabled();
  }
});
`;
const FIXTURES = "import { test as base, expect } from '@playwright/test';\nexport const test = base.extend({});\nexport { expect };\n";
const CONFIG = "import { defineConfig } from '@playwright/test';\nexport default defineConfig({ testDir: './tests' });\n";
const project = (overrides = {}) => ({
  'app/tsconfig.base.json': '{\n  // JSONC comments and trailing commas\n  "compilerOptions": { "paths": { "@e2e/*": ["./tests/support/*"], }, },\n}\n',
  'app/tsconfig.json': '{ "extends": "./tsconfig.base.json", "compilerOptions": { "strict": true } }\n',
  'app/playwright.config.ts': CONFIG,
  'app/tests/support/fixtures.ts': FIXTURES,
  'app/tests/flows/d.spec.ts': SPEC(),
  ...overrides,
});
const gated = result => result.confirmed.some(([id, line]) => id === '#5a' && line === 4);

test('a paths alias from the nearest in-scope tsconfig and its extends chain resolves test and expect', t => {
  const result = scan(t, project(), 'app');
  assert.equal(result.status, 'COMPLETE', JSON.stringify(result.diagnostics));
  assert.ok(gated(result));
  // baseUrl-relative mapping in a jsconfig with an explicit allowJs .js spec.
  const js = scan(t, { 'app/jsconfig.json': '{ "compilerOptions": { "baseUrl": "./tests", "paths": { "#support/*": ["support/*"] } } }\n',
    'app/playwright.config.js': CONFIG, 'app/tests/support/fixtures.js': FIXTURES.replace('base.extend({})', 'base'),
    'app/tests/flows/d.spec.js': SPEC('#support/fixtures') }, 'app');
  assert.equal(js.status, 'COMPLETE', JSON.stringify(js.diagnostics));
  assert.ok(gated(js));
});

test('aliases outside scope, without Playwright evidence or with unknown configuration stay unresolved', t => {
  const cases = {
    'target outside the scan root': [project({ 'app/tsconfig.base.json': '{ "compilerOptions": { "paths": { "@e2e/*": ["../shared/*"] } } }\n',
      'shared/fixtures.ts': FIXTURES }), 'app'],
    'config outside the scan root': [project({ 'app/tsconfig.json': undefined, 'tsconfig.json': '{ "compilerOptions": { "paths": { "@e2e/*": ["./app/tests/support/*"] } } }\n' }), 'app'],
    'no Playwright configuration': [project({ 'app/playwright.config.ts': undefined }), 'app'],
    'single tsconfig option': [project({ 'app/playwright.config.ts': CONFIG.replace("testDir: './tests'", "testDir: './tests', tsconfig: './tsconfig.e2e.json'") }), 'app'],
    'package extends': [project({ 'app/tsconfig.json': '{ "extends": "@tsconfig/node20/tsconfig.json", "compilerOptions": { "paths": { "@e2e/*": ["./tests/support/*"] } } }\n' }), 'app'],
    'project references': [project({ 'app/tsconfig.json': '{ "extends": "./tsconfig.base.json", "references": [{ "path": "./tests" }] }\n' }), 'app'],
    'JavaScript importer without allowJs': [project({ 'app/tests/flows/d.spec.ts': undefined, 'app/tests/flows/d.spec.js': SPEC() }), 'app'],
    'ambiguous target': [project({ 'app/tests/support/fixtures/index.ts': FIXTURES }), 'app'],
    'non-Playwright alias target': [project({ 'app/tests/support/fixtures.ts': "export const test = (name: string, body: unknown) => body;\nexport const expect = (value: unknown) => value;\n" }), 'app'],
    'mapped @playwright/test shadow': [project({ 'app/tsconfig.base.json': '{ "compilerOptions": { "paths": { "@playwright/test": ["./fake/pw.ts"] } } }\n',
      'app/fake/pw.ts': 'export const test = (name: string, body: unknown) => body;\nexport const expect = (value: unknown) => value;\n',
      'app/tests/flows/d.spec.ts': SPEC('@playwright/test') }), 'app'],
  };
  for (const [name, [files, scanned]] of Object.entries(cases)) {
    for (const key of Object.keys(files)) if (files[key] === undefined) delete files[key];
    const result = scan(t, files, scanned);
    assert.ok(!gated(result), name);
    if (name !== 'non-Playwright alias target' && name !== 'mapped @playwright/test shadow') assert.equal(result.status, 'INCOMPLETE', name);
  }
});

test('tsconfig reads have their own budget and never add helper-limit diagnostics', t => {
  const files = { 'playwright.config.ts': CONFIG };
  for (let index = 0; index < 300; index++) {
    files[`apps/a${index}/tsconfig.json`] = '{ "compilerOptions": { "paths": { "@x/*": ["./x/*"] } } }\n';
    files[`apps/a${index}/t.spec.ts`] = "import { test, expect } from '@playwright/test';\nimport { other } from 'some-package';\n" +
      "test('x', async ({ page }) => { await expect(page).toHaveURL('/'); });\n";
  }
  const result = scan(t, files);
  assert.ok(!result.diagnostics.some(item => /^import-(file|byte)-limit$/.test(item.code)), JSON.stringify(result.diagnostics.slice(0, 3)));
});

test('oversized or hostile paths maps complete quickly and stay unresolved', t => {
  const many = Object.fromEntries(Array.from({ length: 5000 }, (_, index) => [`@k${index}/*`, ['./tests/support/*']]));
  const wide = { '@e2e/*': Array.from({ length: 100000 }, (_, index) => `./d${index}/*`) };
  const probes = Object.fromEntries(Array.from({ length: 64 }, (_, index) => [`@p${index}/*`, Array.from({ length: 8 }, (_, v) => `./x${index}-${v}/*`)]));
  for (const [name, paths] of Object.entries({ many, wide, probes })) {
    const imports = Array.from({ length: 64 }, (_, index) => `import { h${index} } from '@p${index}/helper';\n`).join('');
    const started = Date.now();
    const result = scan(t, project({ 'app/tsconfig.base.json': JSON.stringify({ compilerOptions: { paths } }),
      'app/tests/flows/d.spec.ts': imports + SPEC() }), 'app');
    assert.ok(Date.now() - started < 30_000, name);
    assert.ok(!gated(result), name);
    assert.equal(result.status, 'INCOMPLETE', name);
  }
});

test('framework specifiers follow wildcard mappings like Playwright and alias targets honor the credential deny list', t => {
  // Playwright's resolver applies a wildcard or baseUrl entry to
  // @playwright/test too: an in-scope match is a user module, never official.
  const wildcard = scan(t, project({ 'app/tsconfig.base.json': '{ "compilerOptions": { "baseUrl": ".", "paths": { "*": ["./fake/*"] } } }\n',
    'app/fake/@playwright/test.ts': 'export const test = (n: string, b: unknown) => b;\nexport const expect = (v: unknown) => v;\n',
    'app/tests/flows/d.spec.ts': SPEC('@playwright/test') }), 'app');
  assert.ok(!gated(wildcard));
  // A wildcard with no in-scope match leaves the official package.
  const unmatched = scan(t, project({ 'app/tsconfig.base.json': '{ "compilerOptions": { "baseUrl": ".", "paths": { "*": ["./fake/*"] } } }\n',
    'app/tests/flows/d.spec.ts': SPEC('@playwright/test') }), 'app');
  assert.ok(gated(unmatched));
  const denied = scan(t, project({ 'app/tsconfig.base.json': '{ "compilerOptions": { "paths": { "@e2e/*": ["./.auth/*"] } } }\n',
    'app/.auth/fixtures.ts': FIXTURES }), 'app');
  assert.ok(!gated(denied));
  assert.equal(denied.status, 'INCOMPLETE');
});
