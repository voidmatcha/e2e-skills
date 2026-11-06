// SPDX-License-Identifier: Apache-2.0
// Node built-in imports are known non-Playwright modules. They complete
// analysis but never become a test, expect, Page or Locator source.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createScope } from '../src/scope.mjs';
import { createReceivers } from '../src/receivers.mjs';
import { walk, ts } from '../src/source.mjs';

const cli = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
function scan(t, files) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'scanner-node-builtins-')));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  const result = spawnSync(process.execPath, [cli, '--scan', root, '--fail-on', 'p0'],
    { encoding: 'utf8', timeout: 60_000, env: { ...process.env, E2E_SMELL_FAIL_ON: 'p0' } });
  const report = JSON.parse(result.stdout);
  return { status: report.status, findings: report.findings.map(item => [path.basename(item.file), item.patternId, item.disposition, item.line]),
    diagnostics: report.execution.diagnostics };
}
function kinds(text) {
  const filename = '/pinned/case.spec.ts', bytes = Buffer.from(text);
  const manifest = { schema: 'node-candidate-inventory-v1', complete: true, errors: [],
    root: { canonical: '/pinned', kind: 'directory' }, candidates: [{ path: filename,
      identity: { size: String(bytes.length), sha256: createHash('sha256').update(bytes).digest('hex') } }] };
  const receivers = createReceivers(bytes, filename, { scope: createScope({ manifest, sources: new Map([[filename, bytes]]) }) });
  const values = [];
  walk(receivers.source, node => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'inspect') values.push(receivers.expression(node.arguments[0]));
  });
  return values.map(value => [value.kind, value.complete]);
}
const GATED = `import { test, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'path';
import { execSync } from 'child_process';

test('export writes a marker', async ({ page }) => {
  const marker = '/tmp/out/marker.txt';
  const button = page.getByRole('button', { name: 'Export' });
  if ((await button.count()) > 0) {
    mkdirSync(dirname(marker), { recursive: true });
    writeFileSync(marker, 'x', 'utf8');
    execSync('true');
    await expect(page.getByText('Exported')).toBeVisible();
  }
});
`;

test('Node built-in calls in a gated branch no longer leave the file unresolved', t => {
  const result = scan(t, { 'tests/a.spec.ts': GATED });
  assert.equal(result.status, 'COMPLETE', JSON.stringify(result.diagnostics));
  // A branch with Node side effects is not proven action-only: it stays a candidate.
  assert.ok(result.findings.some(([, id, disposition, line]) => id === '#5a' && disposition === 'candidate' && line === 9));
});

test('node:assert stays unresolved and built-in exports never become Playwright sources', t => {
  const result = scan(t, { 'tests/b.spec.ts': "import { test, expect } from '@playwright/test';\nimport { ok } from 'node:assert';\n" +
    "test('x', async ({ page }) => {\n  if ((await page.getByRole('button').count()) > 0) {\n    await expect(page.getByText('a')).toBeVisible();\n" +
    "  } else {\n    ok(false);\n  }\n});\n" });
  assert.equal(result.status, 'INCOMPLETE');
  assert.ok(result.diagnostics.some(item => item.code === 'import-unpinned' && item.line === 7));
  assert.deepEqual(kinds("import { test, expect } from 'node:util';import * as fs from 'fs';\n" +
    "test('x', async ({ page }) => { inspect(page); inspect(expect); inspect(fs); inspect(fs.promises); });"),
  [['none', true], ['none', true], ['none', true], ['none', true]]);
  // The assertion module itself is not a known non-asserting module.
  assert.deepEqual(kinds("import { strict } from 'node:assert';inspect(strict);"), [['unknown', false]]);
});
