// SPDX-License-Identifier: Apache-2.0
// Custom test.extend fixtures re-exported from relative helpers: proven
// Playwright fixture values resolve; unknown values and bases stay unresolved.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function scan(t, files) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-fixture-extend-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0'],
    { encoding: 'utf8', timeout: 60_000, env: { ...process.env, E2E_SMELL_FAIL_ON: 'p0' } });
  const report = JSON.parse(result.stdout);
  const hits = report.findings.map(item => [path.relative(root, item.file), item.patternId, item.disposition, item.line]);
  return { status: report.status, hits, diagnostics: report.execution.diagnostics };
}
const GATED = (fixture, receiver = fixture) => `import { test, expect } from './index';
test('the only member cannot be removed', async ({ ${fixture} }) => {
  const members = ${receiver}.getByTestId('member-row');
  if ((await members.count()) === 1) {
    await expect(members.first()).toBeDisabled();
  }
});
`;
const FIXTURE_BASE = "import { test as base, expect } from '@playwright/test';\nexport const test = base.extend({});\nexport { expect };\n";
const BASE = `import { test as base, expect } from '@playwright/test';
export const test = base.extend<{ shell: import('@playwright/test').Page }>({
  page: async ({ page }, use) => {
    await page.addInitScript(() => window.localStorage.setItem('seen', '1'));
    await use(page);
  },
  shell: async ({ context }, use) => {
    const extra = await context.newPage();
    await use(extra);
    await extra.close();
  },
});
export { expect };
`;

test('a proven extend chain behind a star re-export completes and confirms the gated assertion', t => {
  const result = scan(t, { 'tests/base.ts': BASE, 'tests/index.ts': "export * from './base';\n",
    'tests/page.spec.ts': GATED('page'), 'tests/shell.spec.ts': GATED('shell') });
  assert.equal(result.status, 'COMPLETE', JSON.stringify(result.diagnostics));
  for (const file of ['tests/page.spec.ts', 'tests/shell.spec.ts'])
    assert.ok(result.hits.some(([name, id, disposition, line]) => name === file && id === '#5a' && disposition === 'confirmed' && line === 4), file);
});

test('unknown fixture values, unproven bases and replaced pages never confirm', t => {
  const cases = {
    'fixture object': { 'tests/index.ts': "import { test as base } from '@playwright/test';\nimport { Shell } from './shell';\n" +
        "export const test = base.extend<{ shell: Shell }>({ shell: async ({ page }, use) => { await use(new Shell(page)); } });\nexport { expect } from '@playwright/test';\n",
      'tests/shell.ts': 'export class Shell { constructor(readonly page: unknown) {} getByTestId(id: string) { return id; } }\n',
      'tests/d.spec.ts': GATED('shell') },
    'non-Playwright base': { 'tests/index.ts': "import { test as base } from './runner';\n" +
        "export const test = base.extend({ shell: async ({ page }, use) => { await use(page); } });\nexport { expect } from '@playwright/test';\n",
      'tests/runner.ts': 'export const test = { extend: (fixtures: unknown) => fixtures };\n',
      'tests/d.spec.ts': GATED('shell') },
    'page replaced by an unknown object': { 'tests/index.ts': "import { test as base } from '@playwright/test';\nimport { fakePage } from './fake';\n" +
        "export const test = base.extend({ page: async ({}, use) => { await use(fakePage()); } });\nexport { expect } from '@playwright/test';\n",
      'tests/fake.ts': 'export function fakePage() { return { getByTestId: (id: string) => id }; }\n',
      'tests/d.spec.ts': GATED('page') },
  };
  for (const [name, files] of Object.entries(cases)) {
    const result = scan(t, files);
    assert.equal(result.status, 'INCOMPLETE', name);
    assert.ok(!result.hits.some(([, id, disposition]) => id === '#5a' && disposition === 'confirmed'), name);
  }
});

test('layered export * graphs and branching fixtures resolve in bounded time', t => {
  const files = { 'tests/l30a.ts': FIXTURE_BASE, 'tests/l30b.ts': 'export const other = 1;\n' };
  for (let layer = 29; layer >= 0; layer--) for (const side of ['a', 'b'])
    files[`tests/l${layer}${side}.ts`] = `export * from './l${layer + 1}a';\nexport * from './l${layer + 1}b';\n`;
  files['tests/index.ts'] = "export * from './l0a';\n";
  files['tests/d.spec.ts'] = GATED('page');
  let started = Date.now();
  const layered = scan(t, files);
  assert.ok(Date.now() - started < 30_000);
  assert.ok(['COMPLETE', 'INCOMPLETE'].includes(layered.status));
  // Many fixtures handing each other down through repeated use() branches.
  const names = Array.from({ length: 14 }, (_, index) => `f${index}`);
  const definitions = names.map((name, index) => `${name}: async ({ ${index ? names[index - 1] : 'page'} }, use) => { ` +
    `${Array.from({ length: 4 }, () => `await use(${index ? names[index - 1] : 'page'});`).join(' ')} }`).join(',\n  ');
  started = Date.now();
  const branching = scan(t, { 'tests/index.ts': `import { test as base, expect } from '@playwright/test';\nexport const test = base.extend<any>({\n  ${definitions}\n});\nexport { expect };\n`,
    'tests/d.spec.ts': GATED('f13') });
  assert.ok(Date.now() - started < 30_000);
  assert.equal(branching.status, 'COMPLETE', JSON.stringify(branching.diagnostics));
});

test('a spec importing from playwright/test completes and confirms like @playwright/test', t => {
  const result = scan(t, { 'tests/index.ts': "export { test, expect } from 'playwright/test';\n", 'tests/d.spec.ts': GATED('page'),
    'tests/e.spec.ts': GATED('browser', '(await browser.newPage())') });
  assert.ok(result.hits.some(([name, id, disposition, line]) => name === 'tests/d.spec.ts' && id === '#5a' && disposition === 'confirmed' && line === 4));
  assert.ok(!result.diagnostics.some(item => item.file?.endsWith('d.spec.ts')), JSON.stringify(result.diagnostics));
});
